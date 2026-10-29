#!/usr/bin/env python3
"""Separate source existence/retrieval/extraction/comparability status."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "tables"
MANUSCRIPT = ROOT / "manuscript"
PROTOCOL = ROOT / "protocol"

COMPLETENESS = TABLES / "core_safety_reporting_completeness_by_trial_source.csv"
SOURCE_INV = TABLES / "source_citation_inventory.csv"
SOURCE_STATUS = TABLES / "full_cohort_expansion_source_status.csv"
FIVE_STATE = TABLES / "five_state_source_reporting_status.csv"

TRIAL_SOURCE_OUT = TABLES / "source_flow_status_by_trial_source.csv"
SOURCE_SUMMARY_OUT = TABLES / "source_flow_status_summary.csv"
CONCEPT_OUT = TABLES / "source_flow_status_by_trial_source_concept.csv"
MANUSCRIPT_OUT = MANUSCRIPT / "source_flow_status_summary.en.md"
REPORT_OUT = PROTOCOL / "source_flow_status_report.zh.md"

CONCEPTS = [
    "any_adverse_event",
    "grade_3_or_higher_adverse_event",
    "serious_adverse_event",
    "fatal_adverse_event",
    "adverse_event_leading_to_discontinuation",
    "dose_interruption",
    "dose_reduction",
]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def yes(value: str) -> bool:
    return value.strip().lower() in {"yes", "true", "1"}


def inv_by_trial() -> dict[str, dict[str, str]]:
    return {row["trial_id"]: row for row in read_rows(SOURCE_INV)}


def status_by_trial() -> dict[str, dict[str, str]]:
    return {row["trial_id"]: row for row in read_rows(SOURCE_STATUS)}


def comparable_concepts() -> set[tuple[str, str, str]]:
    out = set()
    for row in read_rows(FIVE_STATE):
        if row["five_state_status"] not in {"comparable_and_concordant", "comparable_but_discordant"}:
            continue
        source_pair = row["source_pair"]
        sources = []
        if "publication" in source_pair:
            sources.append("publication")
        if "ClinicalTrials.gov" in source_pair:
            sources.append("ClinicalTrials.gov")
        if "FDA review" in source_pair:
            sources.append("FDA review")
        for source in sources:
            out.add((row["trial_id"], source, row["safety_concept"]))
    return out


def source_presence(row: dict[str, str], inv: dict[str, str], status: dict[str, str]) -> tuple[str, str]:
    source = row["source_type"]
    if source == "publication":
        if inv.get("local_main_article_files"):
            return "source_retrieved", "Publication-anchored cohort; local main article is available."
        return "source_available_but_not_retrieved", "Publication reference exists but local main article file is missing."
    if source == "ClinicalTrials.gov":
        if inv.get("ctgov_local_json"):
            if status.get("ctgov_ae_status") == "has_ae_module":
                return "source_retrieved", "ClinicalTrials.gov JSON and adverse-events module are available."
            return "source_retrieved_concept_module_absent", "ClinicalTrials.gov JSON is available but the adverse-events module is absent."
        return "source_unavailable_or_not_linked", "No local ClinicalTrials.gov JSON was linked."
    if source == "FDA review":
        if inv.get("structured_fda_document_ids"):
            return "source_retrieved", "FDA review document has structured core safety extraction."
        if int(status.get("fda_p1_present_count_for_drug") or 0) > 0:
            return "source_retrieved_no_structured_core_values", "FDA P1 documents exist locally for the drug, but no trial-specific structured core safety values were extracted."
        if int(status.get("fda_p1_missing_count_for_drug") or 0) > 0:
            return "source_available_but_not_retrieved", "FDA P1 documents were identified but at least one priority file is missing."
        return "source_unavailable_or_not_linked", "No usable FDA review source was linked to this trial."
    return "unknown", ""


def main() -> None:
    inv = inv_by_trial()
    status = status_by_trial()
    comparable = comparable_concepts()
    trial_source_rows = []
    concept_rows = []

    for row in read_rows(COMPLETENESS):
        trial = row["trial_id"]
        source = row["source_type"]
        source_state, source_note = source_presence(row, inv.get(trial, {}), status.get(trial, {}))
        structured_rows = int(row["core_safety_rows"] or 0)
        if structured_rows > 0:
            extraction_state = "structured_value_extracted"
        elif source_state.startswith("source_retrieved"):
            extraction_state = "source_retrieved_no_structured_core_values"
        else:
            extraction_state = source_state
        trial_source_rows.append({
            "trial_id": trial,
            "short_trial_name": row["short_trial_name"],
            "source_type": source,
            "source_flow_state": source_state,
            "extraction_state": extraction_state,
            "core_concepts_reported_count": row["core_concepts_reported_count"],
            "core_safety_rows": row["core_safety_rows"],
            "source_note": source_note,
        })
        for concept in CONCEPTS:
            reported = yes(row[f"reports_{concept}"])
            comparable_flag = (trial, source, concept) in comparable
            if comparable_flag:
                concept_state = "cross_source_comparable"
            elif reported and structured_rows > 0:
                concept_state = "structured_value_extracted"
            elif source_state.startswith("source_retrieved"):
                concept_state = "source_retrieved_concept_not_structured"
            else:
                concept_state = source_state
            concept_rows.append({
                "trial_id": trial,
                "short_trial_name": row["short_trial_name"],
                "source_type": source,
                "safety_concept": concept,
                "source_flow_state": source_state,
                "concept_reported_in_structured_seed": "yes" if reported else "no",
                "concept_flow_state": concept_state,
            })

    write_csv(TRIAL_SOURCE_OUT, trial_source_rows, list(trial_source_rows[0]))
    write_csv(CONCEPT_OUT, concept_rows, list(concept_rows[0]))

    summary_counts: dict[tuple[str, str], int] = defaultdict(int)
    for row in trial_source_rows:
        summary_counts[(row["source_type"], row["extraction_state"])] += 1
    summary = [
        {
            "source_type": source,
            "extraction_state": state,
            "trial_source_count": str(count),
        }
        for (source, state), count in sorted(summary_counts.items())
    ]
    write_csv(SOURCE_SUMMARY_OUT, summary, list(summary[0]))

    pub_structured = sum(row["source_type"] == "publication" and row["extraction_state"] == "structured_value_extracted" for row in trial_source_rows)
    ctgov_structured = sum(row["source_type"] == "ClinicalTrials.gov" and row["extraction_state"] == "structured_value_extracted" for row in trial_source_rows)
    fda_structured = sum(row["source_type"] == "FDA review" and row["extraction_state"] == "structured_value_extracted" for row in trial_source_rows)
    fda_docs_present_no_values = sum(row["source_type"] == "FDA review" and row["extraction_state"] == "source_retrieved_no_structured_core_values" for row in trial_source_rows)

    manuscript = [
        "# Source-flow status summary",
        "",
        (
            "The cohort was publication-anchored; therefore, availability of a primary publication for "
            "all 23 included trials was expected by design rather than a source-coverage finding."
        ),
        "",
        (
            f"Structured publication safety values were extracted for {pub_structured} of 23 trials. "
            f"Structured ClinicalTrials.gov adverse-events module values were extracted for {ctgov_structured} "
            f"trials. Structured FDA review values were extracted for {fda_structured} trials; in another "
            f"{fda_docs_present_no_values} trial-source records, FDA priority documents were present locally "
            "at the drug level but did not yet yield trial-specific structured core safety values."
        ),
        "",
        "This source-flow framing separates source retrieval from concept reporting, structured extraction, and cross-source comparability.",
    ]
    MANUSCRIPT_OUT.write_text("\n".join(manuscript) + "\n", encoding="utf-8")

    report = [
        "# Source-flow status 拆分报告",
        "",
        f"- 已生成：`{TRIAL_SOURCE_OUT.relative_to(ROOT)}`",
        f"- 已生成：`{CONCEPT_OUT.relative_to(ROOT)}`",
        f"- 已生成：`{SOURCE_SUMMARY_OUT.relative_to(ROOT)}`",
        f"- publication structured extraction：{pub_structured}/23",
        f"- ClinicalTrials.gov structured extraction：{ctgov_structured}/23",
        f"- FDA review structured extraction：{fda_structured}/23",
        f"- FDA documents present but no structured trial-specific core values：{fda_docs_present_no_values}/23",
    ]
    REPORT_OUT.write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report))


if __name__ == "__main__":
    main()
