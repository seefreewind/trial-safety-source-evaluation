#!/usr/bin/env python3
"""Create structured audit packets for CT.gov candidates and confirmed pairs."""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
TABLES = ROOT / "tables"
PROTOCOL = ROOT / "protocol"

CTGOV_PACKET_IN = TABLES / "ctgov_full_module_manual_review_packet.csv"
CONFIRMED_IN = TABLES / "analysis_ready_comparison_set_confirmed.csv"
MATRIX = DATA / "processed" / "full_cohort_source_comparability_matrix_detail.csv"
AUDIT = TABLES / "final_analysis_audit_index.csv"

CTGOV_CORE_OUT = TABLES / "ctgov_incremental_core_candidate_adjudication_packet.csv"
PAIR_REVIEW_OUT = TABLES / "confirmed_pair_structured_audit_packet.csv"
AUDIT_SUMMARY_OUT = TABLES / "structured_audit_no_duplicate_review_statement.csv"
REPORT_OUT = PROTOCOL / "manual_adjudication_packets_report.zh.md"


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def detail_by_comp_id() -> dict[str, dict[str, str]]:
    out = {}
    for row in read_rows(MATRIX):
        comp_id = row["comparison_id"].replace("FULLDET", "FULLCOMP")
        out[comp_id] = row
    return out


def audit_by_id() -> dict[str, dict[str, str]]:
    return {row["comparison_id"]: row for row in read_rows(AUDIT)}


def build_ctgov_packet() -> list[dict[str, str]]:
    rows = []
    for row in read_rows(CTGOV_PACKET_IN):
        if row["triage_class"] != "core_candidate_needs_manual_mapping":
            continue
        rows.append({
            "trial_id": row["trial_id"],
            "short_trial_name": row["short_trial_name"],
            "nct_number": row["nct_number"],
            "mapped_safety_concept": row["mapped_safety_concept"],
            "candidate_rows": row["candidate_rows"],
            "outcome_titles": row["outcome_titles"],
            "groups_or_arms": row["groups_or_arms"],
            "unit_of_measure": row["unit_of_measure"],
            "value_range": row["value_range"],
            "denominator_range": row["denominator_range"],
            "calculated_percentage_range": row["calculated_percentage_range"],
            "time_frames": row["time_frames"],
            "review_priority": "high",
            "review_question": "Can this candidate be mapped to a prespecified core safety concept, ADC analysis arm, safety denominator, and aligned time window?",
            "structured_review_decision": "",
            "eligible_for_future_comparison_grade": "",
            "review_notes": "",
        })
    return rows


def build_pair_review_packet() -> list[dict[str, str]]:
    detail = detail_by_comp_id()
    audit = audit_by_id()
    rows = []
    for row in read_rows(CONFIRMED_IN):
        d = detail.get(row["comparison_id"], {})
        a = audit.get(row["comparison_id"], {})
        rows.append({
            "comparison_id": row["comparison_id"],
            "trial_id": row["trial_id"],
            "ae_concept": row["ae_concept"],
            "source_pair": f"{row['source_1']} vs {row['source_2']}",
            "analysis_tier_current": row["analysis_tier"],
            "grade_basis_current": row["grade_basis"],
            "arm_id_1": row["arm_id_1"],
            "arm_id_2": row["arm_id_2"],
            "term_1": d.get("term_1", ""),
            "term_2": d.get("term_2", ""),
            "locator_1": d.get("locator_1", ""),
            "locator_2": d.get("locator_2", ""),
            "number_patients_1": d.get("number_patients_1", ""),
            "number_patients_2": d.get("number_patients_2", ""),
            "denominator_1": row["denominator_1"],
            "denominator_2": row["denominator_2"],
            "percentage_1": row["percentage_1"],
            "percentage_2": row["percentage_2"],
            "absolute_percentage_difference": row["absolute_percentage_difference"],
            "analysis_population_1": d.get("analysis_population_1", ""),
            "analysis_population_2": d.get("analysis_population_2", ""),
            "visual_audit_status": a.get("final_audit_status", ""),
            "structured_audit_concept_mapping": "prespecified_core_concept",
            "structured_audit_arm_match": "recorded_from_matrix",
            "structured_audit_denominator_check": "recorded_from_matrix",
            "structured_audit_source_confirmation": row["source_confirmation_status"],
            "structured_audit_visual_status": a.get("final_audit_status", ""),
            "final_current_analysis_tier": row["analysis_tier"],
            "audit_notes": "Structured audit trail only; independent duplicate reviewer fields were not collected.",
        })
    return rows


def build_no_duplicate_review_statement() -> list[dict[str, str]]:
    return [
        {
            "item": "independent_duplicate_adjudication",
            "status": "not_performed",
            "manuscript_handling": "Report structured audit trail and sensitivity analyses; do not report inter-reviewer agreement.",
        },
        {
            "item": "cohen_kappa",
            "status": "not_applicable",
            "manuscript_handling": "Do not calculate or report Cohen's kappa because no independent reviewer columns were collected.",
        },
        {
            "item": "ctgov_incremental_core_candidates",
            "status": "manual_extension_queue_only",
            "manuscript_handling": "Do not merge the 9 CT.gov incremental core candidates into the primary analysis without future structured review.",
        },
    ]


def main() -> None:
    ctgov_rows = build_ctgov_packet()
    write_csv(CTGOV_CORE_OUT, ctgov_rows, list(ctgov_rows[0]))

    pair_rows = build_pair_review_packet()
    write_csv(PAIR_REVIEW_OUT, pair_rows, list(pair_rows[0]))

    statement_rows = build_no_duplicate_review_statement()
    write_csv(AUDIT_SUMMARY_OUT, statement_rows, list(statement_rows[0]))

    report = [
        "# 结构化审计包生成报告",
        "",
        f"- CT.gov 新增核心候选结构化审核队列：`{CTGOV_CORE_OUT.relative_to(ROOT)}`，{len(ctgov_rows)} 行 trial-concept。",
        f"- 28 对 confirmed pairs 结构化审计包：`{PAIR_REVIEW_OUT.relative_to(ROOT)}`，{len(pair_rows)} 行。",
        f"- 无双审/不计算 κ 的方法学说明表：`{AUDIT_SUMMARY_OUT.relative_to(ROOT)}`。",
        "",
        "说明：当前版本采用 prespecified structured audit trail、source confirmation、visual audit 和稳健性分析作为替代方案；未执行 independent duplicate adjudication，因此不报告双人一致率或 Cohen's κ。",
    ]
    REPORT_OUT.write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report))


if __name__ == "__main__":
    main()
