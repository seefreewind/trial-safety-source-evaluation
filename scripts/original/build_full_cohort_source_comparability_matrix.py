#!/usr/bin/env python3
"""Build full-cohort pairwise source-comparability rows."""

from __future__ import annotations

import csv
import itertools
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"
PROCESSED = ROOT / "data" / "processed"
TABLES = ROOT / "tables"
PROTOCOL = ROOT / "protocol"

OUT_MATRIX = PROCESSED / "full_cohort_source_comparability_matrix.csv"
OUT_SUMMARY = TABLES / "full_cohort_source_comparability_summary.csv"
REPORT_OUT = PROTOCOL / "full_cohort_source_comparability_report.zh.md"

CONCEPT_ALIASES = {
    "adverse_event_discontinuation": "adverse_event_leading_to_discontinuation",
    "adverse_event_dose_reduction": "dose_reduction",
    "adverse_event_dose_interruption": "dose_interruption",
    "grade 3 adverse_event": "grade_3_or_higher_adverse_event",
    "grade 4 adverse_event": "grade_4_or_higher_adverse_event",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def normalize_concept(concept: str) -> str:
    return CONCEPT_ALIASES.get(concept, concept)


def add_source(rows: list[dict[str, str]], source_name: str) -> list[dict[str, str]]:
    out = []
    for row in rows:
        copied = dict(row)
        copied["source_name"] = source_name
        copied["normalized_concept"] = normalize_concept(copied.get("canonical_safety_concept") or copied.get("safety_concept", ""))
        out.append(copied)
    return out


def as_float(value: str) -> float | None:
    try:
        if value in {"", None}:  # type: ignore[comparison-overlap]
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def same_text(a: str, b: str) -> str:
    return "yes" if (a or "").strip().lower() == (b or "").strip().lower() else "no"


def denominator_difference_percent(a: str, b: str) -> str:
    da = as_float(a)
    db = as_float(b)
    if da is None or db is None or max(da, db) == 0:
        return ""
    return f"{abs(da - db) / max(da, db) * 100:.2f}"


def numeric_difference(a: str, b: str) -> str:
    fa = as_float(a)
    fb = as_float(b)
    if fa is None or fb is None:
        return ""
    return f"{abs(fa - fb):.2f}"


def populations_look_same(a: str, b: str) -> str:
    aa = (a or "").strip().lower()
    bb = (b or "").strip().lower()
    if aa and bb and aa == bb:
        return "yes"
    if not aa or not bb:
        return "unknown"
    return "no"


def definitions_align(a: dict[str, str], b: dict[str, str]) -> bool:
    same_grade = same_text(a.get("grade_category", ""), b.get("grade_category", "")) == "yes"
    same_causality = same_text(a.get("causality", ""), b.get("causality", "")) == "yes"
    if not same_grade or not same_causality:
        return False

    concept = a["normalized_concept"]
    if concept == "dose_interruption":
        left = (a.get("seriousness", "") or "").lower()
        right = (b.get("seriousness", "") or "").lower()
        return left in {"dose_interruption", "dose_delay"} and right in {"dose_interruption", "dose_delay"}
    return same_text(a.get("seriousness", ""), b.get("seriousness", "")) == "yes"


def grade_pair(a: dict[str, str], b: dict[str, str]) -> tuple[str, str, str]:
    reasons: list[str] = []
    concept = a["normalized_concept"]
    if a.get("arm_id") and b.get("arm_id") and a.get("arm_id") != b.get("arm_id"):
        return "C", "descriptive_only", "different treatment arms or dose cohorts"

    same_definition = definitions_align(a, b)
    denom_pct_value = as_float(denominator_difference_percent(a.get("denominator", ""), b.get("denominator", "")))
    same_population = populations_look_same(a.get("analysis_population", ""), b.get("analysis_population", ""))
    same_arm = same_text(a.get("arm_id", ""), b.get("arm_id", "")) == "yes"

    if concept == "fatal_adverse_event" and "ClinicalTrials.gov" in {a["source_name"], b["source_name"]}:
        return "C", "descriptive_only", "CT.gov all-cause mortality is not directly comparable with fatal AE without adjudication."

    if "ClinicalTrials.gov" in {a["source_name"], b["source_name"]}:
        ctgov_row = a if a["source_name"] == "ClinicalTrials.gov" else b
        notes = (ctgov_row.get("notes", "") or "").lower()
        if "maximum" in notes or "up to" in notes:
            return "C", "descriptive_only", "CT.gov adverse-event time window may differ from publication or FDA primary analysis cutoff."

    if same_definition and denom_pct_value == 0 and same_population == "yes":
        return "A", "primary_analysis", "Same concept definition, denominator, and named analysis population."
    if same_definition and denom_pct_value == 0 and same_arm:
        return "A", "primary_analysis", "Same concept definition, treatment arm, and denominator; analysis population inferred as aligned pending manual confirmation."
    if same_definition and denom_pct_value is not None and denom_pct_value <= 5:
        if same_population == "no":
            reasons.append("analysis population names differ")
        if denom_pct_value > 0:
            reasons.append("denominator differs by <=5%")
        return "B", "sensitivity_analysis", "; ".join(reasons) or "Minor source differences only."

    if not same_definition:
        reasons.append("grade/seriousness/causality definition differs")
    if denom_pct_value is None:
        reasons.append("denominator missing in at least one source")
    elif denom_pct_value > 5:
        reasons.append("denominator differs by >5%")
    if same_population == "no":
        reasons.append("analysis population differs")
    if any("pool" in (row.get("analysis_population", "").lower()) for row in [a, b]):
        reasons.append("approval-review pooled population may not match trial-specific source")
    return "C", "descriptive_only", "; ".join(dict.fromkeys(reasons)) or "Manual review required before comparison."


def main() -> None:
    rows = (
        add_source(read_csv(INTERIM / "publication_core_safety_combined_seed.csv"), "publication")
        + add_source(read_csv(INTERIM / "ctgov_core_safety_expansion_seed.csv"), "ClinicalTrials.gov")
        + add_source(read_csv(INTERIM / "fda_core_safety_combined_seed.csv"), "FDA review")
    )

    indexed: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        concept = row.get("normalized_concept", "")
        if concept:
            indexed[(row.get("trial_id", ""), concept)].append(row)

    matrix_rows: list[dict[str, str]] = []
    seq = 1
    for (trial_id, concept), grouped in sorted(indexed.items()):
        for left, right in itertools.combinations(grouped, 2):
            if left["source_name"] == right["source_name"]:
                continue
            grade, use, reason = grade_pair(left, right)
            matrix_rows.append({
                "comparison_id": f"FULLCOMP{seq:06d}",
                "trial_id": trial_id,
                "arm_id_1": left.get("arm_id", ""),
                "arm_id_2": right.get("arm_id", ""),
                "ae_concept": concept,
                "source_1": left.get("source_name", ""),
                "source_2": right.get("source_name", ""),
                "source_document_id_1": left.get("document_id", ""),
                "source_document_id_2": right.get("document_id", ""),
                "number_patients_1": left.get("number_patients", ""),
                "number_patients_2": right.get("number_patients", ""),
                "denominator_1": left.get("denominator", ""),
                "denominator_2": right.get("denominator", ""),
                "percentage_1": left.get("percentage", ""),
                "percentage_2": right.get("percentage", ""),
                "absolute_percentage_difference": numeric_difference(left.get("percentage", ""), right.get("percentage", "")),
                "comparability_grade": grade,
                "same_trial": "yes",
                "same_arm": same_text(left.get("arm_id", ""), right.get("arm_id", "")),
                "same_population": populations_look_same(left.get("analysis_population", ""), right.get("analysis_population", "")),
                "same_ae_definition": "yes" if "definition differs" not in reason else "no",
                "denominator_difference_percent": denominator_difference_percent(left.get("denominator", ""), right.get("denominator", "")),
                "reason": reason,
                "analysis_use": use,
                "review_status": "auto_needs_review",
            })
            seq += 1

    OUT_MATRIX.parent.mkdir(parents=True, exist_ok=True)
    with OUT_MATRIX.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(matrix_rows[0]))
        writer.writeheader()
        writer.writerows(matrix_rows)

    by_grade = Counter(row["comparability_grade"] for row in matrix_rows)
    by_pair = Counter(" vs ".join(sorted([row["source_1"], row["source_2"]])) for row in matrix_rows)
    summary_rows = []
    for trial_id in sorted({row["trial_id"] for row in matrix_rows}):
        trial_rows = [row for row in matrix_rows if row["trial_id"] == trial_id]
        summary_rows.append({
            "trial_id": trial_id,
            "comparison_count": str(len(trial_rows)),
            "grade_A": str(sum(1 for row in trial_rows if row["comparability_grade"] == "A")),
            "grade_B": str(sum(1 for row in trial_rows if row["comparability_grade"] == "B")),
            "grade_C": str(sum(1 for row in trial_rows if row["comparability_grade"] == "C")),
            "source_pairs": ";".join(sorted({" vs ".join(sorted([row["source_1"], row["source_2"]])) for row in trial_rows})),
            "ae_concepts": ";".join(sorted({row["ae_concept"] for row in trial_rows})),
        })

    OUT_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    with OUT_SUMMARY.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary_rows[0]))
        writer.writeheader()
        writer.writerows(summary_rows)

    REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT_OUT.write_text(
        "\n".join([
            "# Full-cohort source comparability matrix 报告",
            "",
            "日期：2026-06-18",
            "",
            "## 输出",
            "",
            "- `data/processed/full_cohort_source_comparability_matrix.csv`",
            "- `tables/full_cohort_source_comparability_summary.csv`",
            "",
            "## 覆盖",
            "",
            f"- 比较配对总数：{len(matrix_rows)}",
            f"- 覆盖 trial：{len(summary_rows)}",
            f"- A 级配对：{by_grade.get('A', 0)}",
            f"- B 级配对：{by_grade.get('B', 0)}",
            f"- C 级配对：{by_grade.get('C', 0)}",
            "",
            "## 来源配对",
            "",
            *[f"- {pair}: {count}" for pair, count in sorted(by_pair.items())],
            "",
            "## 解释",
            "",
            "该矩阵是自动预分级。A 级表示定义、分母和治疗臂高度一致，可进入主分析候选；B 级建议敏感性分析；C 级仅作描述或需要人工裁决。",
        ]) + "\n",
        encoding="utf-8",
    )

    print(f"Wrote {OUT_MATRIX.relative_to(ROOT)}")
    print(f"Wrote {OUT_SUMMARY.relative_to(ROOT)}")
    print(f"Wrote {REPORT_OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
