#!/usr/bin/env python3
"""Build three-layer availability, comparability, and concordance tables."""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
TABLES = ROOT / "tables"
MANUSCRIPT = ROOT / "manuscript"
PROTOCOL = ROOT / "protocol"

CORE_CONCEPTS = [
    "any_adverse_event",
    "grade_3_or_higher_adverse_event",
    "serious_adverse_event",
    "fatal_adverse_event",
    "adverse_event_leading_to_discontinuation",
    "dose_interruption",
    "dose_reduction",
]

SOURCES = ["publication", "ClinicalTrials.gov", "FDA review"]
SOURCE_PAIRS = [
    ("publication", "FDA review"),
    ("publication", "ClinicalTrials.gov"),
    ("FDA review", "ClinicalTrials.gov"),
]

CONCEPT_ALIASES = {
    "adverse_event_discontinuation": "adverse_event_leading_to_discontinuation",
    "adverse_event_dose_reduction": "dose_reduction",
    "adverse_event_dose_interruption": "dose_interruption",
}


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def normalize_concept(row: dict[str, str]) -> str:
    concept = row.get("canonical_safety_concept") or row.get("safety_concept", "")
    return CONCEPT_ALIASES.get(concept, concept)


def source_rows() -> list[dict[str, str]]:
    files = [
        (DATA / "interim" / "publication_core_safety_combined_seed.csv", "publication"),
        (DATA / "interim" / "ctgov_core_safety_expansion_seed.csv", "ClinicalTrials.gov"),
        (DATA / "interim" / "fda_core_safety_combined_seed.csv", "FDA review"),
    ]
    rows: list[dict[str, str]] = []
    for path, source in files:
        for row in read_rows(path):
            copied = dict(row)
            copied["source_name"] = source
            copied["normalized_concept"] = normalize_concept(copied)
            rows.append(copied)
    return rows


def yes_no(value: bool) -> str:
    return "yes" if value else "no"


def pct(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return ""
    return f"{numerator / denominator * 100:.1f}"


def source_pair(row: dict[str, str]) -> str:
    values = sorted([row.get("source_1", ""), row.get("source_2", "")])
    return " vs ".join(values)


def reason_category(reason: str) -> str:
    reason_l = (reason or "").lower()
    if "different treatment arms" in reason_l or "dose cohorts" in reason_l:
        return "different_arm_or_dose"
    if "ct.gov all-cause mortality" in reason_l:
        return "ctgov_mortality_not_fatal_ae"
    if "time window" in reason_l:
        return "ctgov_time_window_difference"
    if "definition differs" in reason_l or "causality" in reason_l:
        return "ae_definition_or_causality_mismatch"
    if "denominator" in reason_l or "population" in reason_l or "pooled population" in reason_l:
        return "denominator_or_population_mismatch"
    if "missing" in reason_l:
        return "missing_denominator_or_source_detail"
    return "other_or_manual_review"


def main() -> None:
    trials = read_rows(DATA / "processed" / "trial_master_expansion_candidates.csv")
    trial_by_id = {row["trial_id"]: row for row in trials}
    observations = source_rows()

    by_trial_source: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    by_trial_source_concept: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in observations:
        trial_id = row.get("trial_id", "")
        source = row.get("source_name", "")
        concept = row.get("normalized_concept", "")
        by_trial_source[(trial_id, source)].append(row)
        by_trial_source_concept[(trial_id, source, concept)].append(row)

    completeness_source_rows: list[dict[str, str]] = []
    for trial in sorted(trials, key=lambda r: r["trial_id"]):
        trial_id = trial["trial_id"]
        for source in SOURCES:
            rows = by_trial_source.get((trial_id, source), [])
            concept_present = {
                concept: bool(by_trial_source_concept.get((trial_id, source, concept)))
                for concept in CORE_CONCEPTS
            }
            core_rows = [
                row
                for row in rows
                if row.get("normalized_concept") in CORE_CONCEPTS
            ]
            denominator_rows = sum(1 for row in core_rows if row.get("denominator"))
            percentage_rows = sum(1 for row in core_rows if row.get("percentage"))
            population_rows = sum(1 for row in core_rows if row.get("analysis_population"))
            cutoff_rows = sum(1 for row in core_rows if row.get("data_cutoff_date"))
            causality_rows = sum(1 for row in core_rows if row.get("causality"))
            reported_count = sum(1 for value in concept_present.values() if value)
            completeness_source_rows.append({
                "trial_id": trial_id,
                "short_trial_name": trial.get("acronym", ""),
                "source_type": source,
                "source_available": yes_no(bool(rows)),
                "core_concepts_reported_count": str(reported_count),
                "core_concepts_reported_percent": pct(reported_count, len(CORE_CONCEPTS)),
                **{f"reports_{concept}": yes_no(present) for concept, present in concept_present.items()},
                "core_safety_rows": str(len(core_rows)),
                "rows_with_denominator": str(denominator_rows),
                "rows_with_percentage": str(percentage_rows),
                "rows_with_analysis_population": str(population_rows),
                "rows_with_data_cutoff": str(cutoff_rows),
                "rows_with_causality": str(causality_rows),
                "denominator_completeness_percent": pct(denominator_rows, len(core_rows)),
                "percentage_completeness_percent": pct(percentage_rows, len(core_rows)),
                "analysis_population_completeness_percent": pct(population_rows, len(core_rows)),
                "data_cutoff_completeness_percent": pct(cutoff_rows, len(core_rows)),
                "causality_completeness_percent": pct(causality_rows, len(core_rows)),
            })

    write_csv(
        TABLES / "core_safety_reporting_completeness_by_trial_source.csv",
        completeness_source_rows,
        list(completeness_source_rows[0]),
    )

    completeness_trial_rows: list[dict[str, str]] = []
    for trial in sorted(trials, key=lambda r: r["trial_id"]):
        trial_id = trial["trial_id"]
        aggregate_present = {}
        for concept in CORE_CONCEPTS:
            aggregate_present[concept] = any(
                by_trial_source_concept.get((trial_id, source, concept))
                for source in SOURCES
            )
        reported_count = sum(1 for value in aggregate_present.values() if value)
        source_count = sum(1 for source in SOURCES if by_trial_source.get((trial_id, source)))
        completeness_trial_rows.append({
            "trial_id": trial_id,
            "short_trial_name": trial.get("acronym", ""),
            "nct_number": trial.get("nct_number", ""),
            "phase": trial.get("phase", ""),
            "randomized": trial.get("randomized", ""),
            "controlled": trial.get("controlled", ""),
            "single_arm": trial.get("single_arm", ""),
            "structured_source_count": str(source_count),
            "publication_available": yes_no(bool(by_trial_source.get((trial_id, "publication")))),
            "ctgov_available": yes_no(bool(by_trial_source.get((trial_id, "ClinicalTrials.gov")))),
            "fda_review_available": yes_no(bool(by_trial_source.get((trial_id, "FDA review")))),
            "core_concepts_reported_any_source_count": str(reported_count),
            "core_concepts_reported_any_source_percent": pct(reported_count, len(CORE_CONCEPTS)),
            **{f"any_source_reports_{concept}": yes_no(present) for concept, present in aggregate_present.items()},
        })

    write_csv(
        TABLES / "core_safety_reporting_completeness_by_trial.csv",
        completeness_trial_rows,
        list(completeness_trial_rows[0]),
    )

    comparisons = read_rows(DATA / "processed" / "full_cohort_source_comparability_matrix.csv")
    confirmed_pairs = read_rows(TABLES / "analysis_ready_comparison_set_confirmed.csv")
    overall_counts = Counter(row.get("comparability_grade", "") for row in comparisons)
    auto_comparable_count = overall_counts["A"] + overall_counts["B"]
    confirmed_count = len(confirmed_pairs)
    comparability_overall = [{
        "comparison_scope": "all_potential_source_pairs",
        "comparison_count": str(len(comparisons)),
        "grade_A_count": str(overall_counts["A"]),
        "grade_B_count": str(overall_counts["B"]),
        "grade_C_count": str(overall_counts["C"]),
        "auto_comparable_AB_count": str(auto_comparable_count),
        "auto_comparability_yield_percent": pct(auto_comparable_count, len(comparisons)),
        "confirmed_analysis_ready_count": str(confirmed_count),
        "confirmed_comparability_yield_percent": pct(confirmed_count, len(comparisons)),
        "trial_count": str(len({row["trial_id"] for row in comparisons})),
        "safety_concept_count": str(len({row["ae_concept"] for row in comparisons})),
    }]
    write_csv(TABLES / "comparability_yield_overall.csv", comparability_overall, list(comparability_overall[0]))

    confirmed_by_pair = Counter(source_pair(row) for row in confirmed_pairs)
    confirmed_by_trial = Counter(row["trial_id"] for row in confirmed_pairs)
    confirmed_by_concept = Counter(row["ae_concept"] for row in confirmed_pairs)

    by_pair: dict[str, list[dict[str, str]]] = defaultdict(list)
    by_trial: dict[str, list[dict[str, str]]] = defaultdict(list)
    by_concept: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in comparisons:
        by_pair[source_pair(row)].append(row)
        by_trial[row["trial_id"]].append(row)
        by_concept[row["ae_concept"]].append(row)

    def summarize_groups(
        groups: dict[str, list[dict[str, str]]],
        key_name: str,
        confirmed_counter: Counter[str],
    ) -> list[dict[str, str]]:
        out = []
        for key, rows in sorted(groups.items()):
            counts = Counter(row.get("comparability_grade", "") for row in rows)
            auto_comparable = counts["A"] + counts["B"]
            confirmed = confirmed_counter.get(key, 0)
            out.append({
                key_name: key,
                "comparison_count": str(len(rows)),
                "grade_A_count": str(counts["A"]),
                "grade_B_count": str(counts["B"]),
                "grade_C_count": str(counts["C"]),
                "auto_comparable_AB_count": str(auto_comparable),
                "auto_comparability_yield_percent": pct(auto_comparable, len(rows)),
                "confirmed_analysis_ready_count": str(confirmed),
                "confirmed_comparability_yield_percent": pct(confirmed, len(rows)),
                "trial_count": str(len({row["trial_id"] for row in rows})),
                "safety_concept_count": str(len({row["ae_concept"] for row in rows})),
            })
        return out

    pair_rows = summarize_groups(by_pair, "source_pair", confirmed_by_pair)
    trial_rows = summarize_groups(by_trial, "trial_id", confirmed_by_trial)
    concept_rows = summarize_groups(by_concept, "safety_concept", confirmed_by_concept)
    write_csv(TABLES / "comparability_yield_by_source_pair.csv", pair_rows, list(pair_rows[0]))
    write_csv(TABLES / "comparability_yield_by_trial.csv", trial_rows, list(trial_rows[0]))
    write_csv(TABLES / "comparability_yield_by_safety_concept.csv", concept_rows, list(concept_rows[0]))

    reason_groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in comparisons:
        if row.get("comparability_grade") == "C":
            reason_groups[(reason_category(row.get("reason", "")), source_pair(row))].append(row)
    reason_rows = []
    for (category, pair), rows in sorted(reason_groups.items()):
        reason_rows.append({
            "noncomparability_category": category,
            "source_pair": pair,
            "pair_count": str(len(rows)),
            "trial_count": str(len({row["trial_id"] for row in rows})),
            "safety_concept_count": str(len({row["ae_concept"] for row in rows})),
        })
    write_csv(TABLES / "noncomparability_reason_by_source_pair.csv", reason_rows, list(reason_rows[0]))

    comparison_by_stratum: dict[tuple[str, str, tuple[str, str]], list[dict[str, str]]] = defaultdict(list)
    confirmed_by_stratum: dict[tuple[str, str, tuple[str, str]], list[dict[str, str]]] = defaultdict(list)
    for row in comparisons:
        pair_tuple = tuple(sorted([row["source_1"], row["source_2"]]))
        comparison_by_stratum[(row["trial_id"], row["ae_concept"], pair_tuple)].append(row)
    for row in confirmed_pairs:
        pair_tuple = tuple(sorted([row["source_1"], row["source_2"]]))
        confirmed_by_stratum[(row["trial_id"], row["ae_concept"], pair_tuple)].append(row)

    five_state_rows = []
    for trial in sorted(trials, key=lambda r: r["trial_id"]):
        trial_id = trial["trial_id"]
        for concept in CORE_CONCEPTS:
            for pair in SOURCE_PAIRS:
                source_a, source_b = pair
                rows_a = by_trial_source.get((trial_id, source_a), [])
                rows_b = by_trial_source.get((trial_id, source_b), [])
                concept_a = by_trial_source_concept.get((trial_id, source_a, concept), [])
                concept_b = by_trial_source_concept.get((trial_id, source_b, concept), [])
                comp_rows = comparison_by_stratum.get((trial_id, concept, tuple(sorted(pair))), [])
                confirmed_rows = confirmed_by_stratum.get((trial_id, concept, tuple(sorted(pair))), [])
                if not rows_a or not rows_b:
                    state = "unavailable"
                elif not concept_a or not concept_b:
                    state = "not_reported_in_both_sources"
                elif not comp_rows:
                    state = "reported_without_generated_pair"
                elif confirmed_rows:
                    diffs = [
                        float(row["absolute_percentage_difference"])
                        for row in confirmed_rows
                        if row.get("absolute_percentage_difference")
                    ]
                    min_diff = min(diffs) if diffs else None
                    state = "comparable_and_concordant" if min_diff is not None and min_diff <= 2 else "comparable_but_discordant"
                else:
                    comparable = [row for row in comp_rows if row["comparability_grade"] in {"A", "B"}]
                    if not comparable:
                        state = "reported_but_non_comparable"
                    else:
                        diffs = [
                            float(row["absolute_percentage_difference"])
                            for row in comparable
                            if row.get("absolute_percentage_difference")
                        ]
                        min_diff = min(diffs) if diffs else None
                        state = "comparable_and_concordant" if min_diff is not None and min_diff <= 2 else "comparable_but_discordant"
                five_state_rows.append({
                    "trial_id": trial_id,
                    "short_trial_name": trial.get("acronym", ""),
                    "safety_concept": concept,
                    "source_pair": " vs ".join(pair),
                    "five_state_status": state,
                    "generated_comparison_count": str(len(comp_rows)),
                    "grade_A_or_B_count": str(sum(1 for row in comp_rows if row.get("comparability_grade") in {"A", "B"})),
                    "confirmed_analysis_ready_count": str(len(confirmed_rows)),
                    "grade_C_count": str(sum(1 for row in comp_rows if row.get("comparability_grade") == "C")),
                })

    write_csv(TABLES / "five_state_source_reporting_status.csv", five_state_rows, list(five_state_rows[0]))
    five_counts = Counter(row["five_state_status"] for row in five_state_rows)
    five_summary_rows = [
        {
            "five_state_status": status,
            "stratum_count": str(count),
            "stratum_percent": pct(count, len(five_state_rows)),
        }
        for status, count in sorted(five_counts.items())
    ]
    write_csv(TABLES / "five_state_source_reporting_status_summary.csv", five_summary_rows, list(five_summary_rows[0]))

    trial_complete_count = sum(
        1 for row in completeness_trial_rows
        if int(row["core_concepts_reported_any_source_count"]) == len(CORE_CONCEPTS)
    )
    source_dist = Counter(row["structured_source_count"] for row in completeness_trial_rows)
    manuscript_lines = [
        "# Three-layer analysis tables",
        "",
        "## Layer 1. Availability and completeness",
        "",
        f"- All 23 trial candidates had publication-based structured safety data.",
        f"- {sum(1 for row in completeness_trial_rows if row['ctgov_available'] == 'yes')} trials had ClinicalTrials.gov structured safety data.",
        f"- {sum(1 for row in completeness_trial_rows if row['fda_review_available'] == 'yes')} trials had FDA review structured safety data.",
        f"- {trial_complete_count} trials reported all seven core safety concepts in at least one public source.",
        f"- Structured source count distribution: " + "; ".join(f"{key} sources: {value} trials" for key, value in sorted(source_dist.items())),
        "",
        "## Layer 2. Comparability yield",
        "",
        f"- The source-comparability screen generated {len(comparisons)} potential cross-source comparisons.",
        f"- Automated rules classified {overall_counts['A']} comparisons as grade A, {overall_counts['B']} as grade B, and {overall_counts['C']} as grade C.",
        f"- After adjudication and source confirmation, {confirmed_count} comparisons were retained as analysis-ready.",
        f"- The confirmed comparability yield was {pct(confirmed_count, len(comparisons))}%.",
        "",
        "| Source pair | Comparisons | Auto A/B | Confirmed analysis-ready | Confirmed yield (%) | Grade C |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in pair_rows:
        manuscript_lines.append(
            f"| {row['source_pair']} | {row['comparison_count']} | {row['auto_comparable_AB_count']} | {row['confirmed_analysis_ready_count']} | {row['confirmed_comparability_yield_percent']} | {row['grade_C_count']} |"
        )
    manuscript_lines.extend([
        "",
        "## Layer 3. Numeric concordance",
        "",
        "The confirmed numeric-concordance layer remains restricted to source-confirmed A/B candidates and is summarized separately in the confirmed concordance tables.",
    ])
    (MANUSCRIPT / "three_layer_analysis_tables.en.md").write_text("\n".join(manuscript_lines) + "\n", encoding="utf-8")

    report = [
        "# Three-layer analysis tables 生成报告",
        "",
        f"- completeness by trial/source: `tables/core_safety_reporting_completeness_by_trial_source.csv`",
        f"- completeness by trial: `tables/core_safety_reporting_completeness_by_trial.csv`",
        f"- comparability yield overall/source/trial/concept: `tables/comparability_yield_*.csv`",
        f"- five-state status: `tables/five_state_source_reporting_status.csv`",
        f"- manuscript summary: `manuscript/three_layer_analysis_tables.en.md`",
        "",
        f"- 23 个 trial 均进入 Layer 1。",
        f"- {len(comparisons)} 个潜在比较进入 Layer 2。",
        f"- confirmed comparability yield: {pct(confirmed_count, len(comparisons))}%。",
    ]
    (PROTOCOL / "three_layer_analysis_tables_report.zh.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report))


if __name__ == "__main__":
    main()
