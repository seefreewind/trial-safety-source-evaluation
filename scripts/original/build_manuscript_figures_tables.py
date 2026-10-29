#!/usr/bin/env python3
"""Build manuscript figures and a trial-characteristics table."""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "tables"
FIGURES = ROOT / "figures" / "manuscript"
MANUSCRIPT = ROOT / "manuscript"
PROTOCOL = ROOT / "protocol"


PALETTE = {
    "blue": "#2F6B9A",
    "teal": "#2A9D8F",
    "green": "#6A994E",
    "amber": "#DDA15E",
    "red": "#BC4749",
    "gray": "#8D99AE",
    "light": "#F3F6F8",
    "dark": "#1F2933",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def savefig(fig: plt.Figure, stem: str) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES / f"{stem}.png", dpi=300, bbox_inches="tight")
    fig.savefig(FIGURES / f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)


def build_table1() -> list[dict[str, str]]:
    completeness = read_csv(TABLES / "core_safety_reporting_completeness_by_trial.csv")
    source_rows = read_csv(TABLES / "source_flow_status_by_trial_source.csv")
    source_by_trial = {
        (row["trial_id"], row["source_type"]): row for row in source_rows
    }
    fields = [
        "trial_id",
        "short_trial_name",
        "nct_number",
        "phase",
        "design",
        "publication_status",
        "ctgov_status",
        "fda_review_status",
        "core_concepts_reported_any_source_count",
    ]
    rows = []
    for row in completeness:
        design_bits = []
        if row["randomized"] == "yes":
            design_bits.append("randomized")
        if row["controlled"] == "yes":
            design_bits.append("controlled")
        if row["single_arm"] == "yes":
            design_bits.append("single-arm")
        design = ", ".join(design_bits) if design_bits else "not classified"

        def source_status(source: str) -> str:
            state = source_by_trial.get((row["trial_id"], source), {}).get("extraction_state", "")
            if state == "structured_value_extracted":
                return "structured values"
            if state == "source_retrieved_no_structured_core_values":
                return "retrieved, no structured core values"
            if state == "source_unavailable_or_not_linked":
                return "not linked/unavailable"
            return "not classified"

        rows.append(
            {
                "trial_id": row["trial_id"],
                "short_trial_name": row["short_trial_name"],
                "nct_number": row["nct_number"],
                "phase": row["phase"],
                "design": design,
                "publication_status": source_status("publication"),
                "ctgov_status": source_status("ClinicalTrials.gov"),
                "fda_review_status": source_status("FDA review"),
                "core_concepts_reported_any_source_count": row["core_concepts_reported_any_source_count"],
            }
        )
    write_csv(TABLES / "table1_included_trial_characteristics.csv", rows, fields)
    return rows


def fig1_study_flow() -> None:
    fig, ax = plt.subplots(figsize=(7.2, 4.4), constrained_layout=True)
    ax.axis("off")
    boxes = [
        ("23 included pivotal ADC trials", 0.5, 0.86, PALETTE["blue"]),
        ("Source-flow layer\nPublication 23/23\nClinicalTrials.gov 19/23\nFDA review structured values 6/23", 0.5, 0.62, PALETTE["teal"]),
        ("Comparability layer\n53 jointly reported strata\n17 directly comparable strata", 0.27, 0.36, PALETTE["green"]),
        ("Value-pair screen\n269 generated pairings\n28 analysis-ready pairs", 0.73, 0.36, PALETTE["amber"]),
        ("Numeric-concordance layer\n21 primary + 7 sensitivity pairs\nPair- and trial-weighted summaries", 0.5, 0.12, PALETTE["red"]),
    ]
    for text, x, y, color in boxes:
        ax.text(
            x,
            y,
            text,
            ha="center",
            va="center",
            fontsize=8.5,
            color="white",
            bbox=dict(boxstyle="round,pad=0.45", facecolor=color, edgecolor=color),
            transform=ax.transAxes,
        )
    arrows = [
        ((0.5, 0.79), (0.5, 0.70)),
        ((0.44, 0.55), (0.30, 0.45)),
        ((0.56, 0.55), (0.70, 0.45)),
        ((0.31, 0.27), (0.45, 0.19)),
        ((0.69, 0.27), (0.55, 0.19)),
    ]
    for start, end in arrows:
        ax.annotate(
            "",
            xy=end,
            xytext=start,
            xycoords=ax.transAxes,
            arrowprops=dict(arrowstyle="->", lw=1.6, color=PALETTE["dark"]),
        )
    ax.set_title("Study flow and analysis layers", loc="left", fontsize=10.5, weight="bold", color=PALETTE["dark"])
    savefig(fig, "figure1_study_flow")


def fig2_source_heatmap() -> None:
    rows = read_csv(TABLES / "source_flow_status_by_trial_source.csv")
    trial_names = []
    for row in rows:
        label = f"{row['trial_id']} {row['short_trial_name']}"
        if label not in trial_names:
            trial_names.append(label)
    sources = ["publication", "ClinicalTrials.gov", "FDA review"]
    value_map = {
        "source_unavailable_or_not_linked": 0,
        "source_retrieved_no_structured_core_values": 1,
        "structured_value_extracted": 2,
    }
    label_map = {0: "Not linked", 1: "Retrieved", 2: "Structured"}
    by_key = {(f"{r['trial_id']} {r['short_trial_name']}", r["source_type"]): r for r in rows}
    matrix = np.zeros((len(trial_names), len(sources)))
    for i, trial in enumerate(trial_names):
        for j, source in enumerate(sources):
            matrix[i, j] = value_map.get(by_key.get((trial, source), {}).get("extraction_state", ""), 0)
    colors = ["#D9DEE6", "#F2C879", "#4C956C"]
    cmap = plt.matplotlib.colors.ListedColormap(colors)
    fig, ax = plt.subplots(figsize=(7.0, 8.4), constrained_layout=True)
    ax.imshow(matrix, aspect="auto", cmap=cmap, vmin=0, vmax=2)
    ax.set_xticks(range(len(sources)), sources, fontsize=9)
    ax.set_yticks(range(len(trial_names)), trial_names, fontsize=7)
    ax.set_title("Source-flow status by included trial", loc="left", fontsize=10.5, weight="bold", color=PALETTE["dark"])
    ax.set_xticks(np.arange(-0.5, len(sources), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(trial_names), 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=1.5)
    ax.tick_params(which="minor", bottom=False, left=False)
    for i in range(len(trial_names)):
        for j in range(len(sources)):
            ax.text(j, i, label_map[int(matrix[i, j])], ha="center", va="center", fontsize=6.5, color=PALETTE["dark"])
    handles = [plt.Rectangle((0, 0), 1, 1, color=colors[i]) for i in range(3)]
    ax.legend(handles, [label_map[i] for i in range(3)], loc="lower center", bbox_to_anchor=(0.5, -0.08), ncol=3, frameon=False)
    savefig(fig, "figure2_source_flow_heatmap")


def fig3_reporting_states() -> None:
    rows = read_csv(TABLES / "five_state_source_reporting_status_summary.csv")
    order = [
        ("comparable_and_concordant", "Comparable,\nconcordant", PALETTE["green"]),
        ("comparable_but_discordant", "Comparable,\ndiscordant", PALETTE["red"]),
        ("reported_but_non_comparable", "Reported,\nnon-comparable", PALETTE["amber"]),
        ("not_reported_in_both_sources", "Not reported\nin both", PALETTE["gray"]),
        ("unavailable", "Unavailable", "#CAD2C5"),
    ]
    counts = {row["five_state_status"]: int(row["stratum_count"]) for row in rows}
    labels = [item[1] for item in order]
    values = [counts.get(item[0], 0) for item in order]
    colors = [item[2] for item in order]
    fig, ax = plt.subplots(figsize=(7.2, 4.3), constrained_layout=True)
    bars = ax.bar(labels, values, color=colors)
    ax.set_ylabel("Trial-concept-source-pair strata")
    ax.set_title("Five-state source reporting status", loc="left", fontsize=10.5, weight="bold", color=PALETTE["dark"])
    ax.spines[["top", "right"]].set_visible(False)
    total = sum(values)
    for bar, value in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max(values) * 0.02,
            f"{value}\n({value / total * 100:.1f}%)",
            ha="center",
            va="bottom",
            fontsize=9,
        )
    savefig(fig, "figure3_five_state_reporting_status")


def fig4_numeric_concordance() -> None:
    rows = read_csv(TABLES / "analysis_ready_comparison_set_confirmed.csv")
    primary = [r for r in rows if r["analysis_tier"] == "primary_candidate"]
    sensitivity = [r for r in rows if r["analysis_tier"] == "sensitivity_candidate"]
    fig, ax = plt.subplots(figsize=(5.8, 5.1), constrained_layout=True)
    for subset, label, color, marker in [
        (primary, "Primary", PALETTE["blue"], "o"),
        (sensitivity, "Sensitivity", PALETTE["amber"], "s"),
    ]:
        x = [float(r["percentage_1"]) for r in subset]
        y = [float(r["percentage_2"]) for r in subset]
        ax.scatter(x, y, s=52, color=color, marker=marker, label=f"{label} (n={len(subset)})", alpha=0.88, edgecolor="white", linewidth=0.6)
    all_vals = [float(r["percentage_1"]) for r in rows] + [float(r["percentage_2"]) for r in rows]
    lo, hi = max(0, min(all_vals) - 5), min(105, max(all_vals) + 5)
    ax.plot([lo, hi], [lo, hi], color=PALETTE["dark"], linewidth=1.2, linestyle="--", label="Identity line")
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_xlabel("Source 1 reported percentage")
    ax.set_ylabel("Source 2 reported percentage")
    ax.set_title("Numeric concordance among confirmed pairs", loc="left", fontsize=10.5, weight="bold", color=PALETTE["dark"])
    ax.legend(frameon=False, loc="upper left")
    ax.spines[["top", "right"]].set_visible(False)
    savefig(fig, "figure4_numeric_concordance_scatter")


def table_markdown(rows: list[dict[str, str]]) -> str:
    headers = [
        ("trial_id", "Trial ID"),
        ("short_trial_name", "Trial"),
        ("nct_number", "NCT"),
        ("phase", "Phase"),
        ("design", "Design"),
        ("publication_status", "Publication"),
        ("ctgov_status", "ClinicalTrials.gov"),
        ("fda_review_status", "FDA review"),
        ("core_concepts_reported_any_source_count", "Core concepts reported"),
    ]
    out = [
        "### Table 1. Characteristics and source-flow status of included pivotal ADC trials",
        "",
        "| " + " | ".join(label for _, label in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        out.append("| " + " | ".join(row[key] for key, _ in headers) + " |")
    out.append("")
    out.append("Note: Core concepts reported refers to the number of seven prespecified aggregate safety concepts reported in at least one public source. FDA review status distinguishes source retrieval from structured trial-specific value extraction.")
    return "\n".join(out)


def build_markdown(rows: list[dict[str, str]]) -> str:
    abs_fig = lambda name: str((FIGURES / name).resolve())
    return "\n\n".join(
        [
            "## Figures and Trial Characteristics",
            table_markdown(rows),
            "### Figure 1. Study flow and analysis layers\n\n"
            f"![Figure 1. Study flow and analysis layers]({abs_fig('figure1_study_flow.png')})\n\n"
            "Figure 1 summarizes the publication-anchored trial cohort and the three analysis layers used to separate source flow, comparability, value-pair yield, and numeric concordance.",
            "### Figure 2. Source-flow status by included trial\n\n"
            f"![Figure 2. Source-flow status by included trial]({abs_fig('figure2_source_flow_heatmap.png')})\n\n"
            "Figure 2 shows whether each source type produced structured trial-specific safety values, only a retrieved source without structured core values, or no linked source.",
            "### Figure 3. Five-state reporting and comparability status\n\n"
            f"![Figure 3. Five-state reporting and comparability status]({abs_fig('figure3_five_state_reporting_status.png')})\n\n"
            "Figure 3 shows the distribution of trial-concept-source-pair strata across concordant comparable, discordant comparable, reported but non-comparable, not reported in both sources, and unavailable states.",
            "### Figure 4. Numeric concordance among confirmed comparison pairs\n\n"
            f"![Figure 4. Numeric concordance among confirmed comparison pairs]({abs_fig('figure4_numeric_concordance_scatter.png')})\n\n"
            "Figure 4 plots source 1 versus source 2 percentages for the 28 confirmed comparison pairs. The identity line indicates perfect numerical agreement; the plot describes public reporting consistency and does not imply independent event-level validation.",
        ]
    )


def main() -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    rows = build_table1()
    fig1_study_flow()
    fig2_source_heatmap()
    fig3_reporting_states()
    fig4_numeric_concordance()
    (MANUSCRIPT / "manuscript_figures_and_table1.en.md").write_text(build_markdown(rows) + "\n", encoding="utf-8")
    report = f"""# Manuscript figure/table generation report

- Generated trial-characteristics table: `tables/table1_included_trial_characteristics.csv`
- Generated manuscript figure files in `figures/manuscript/`
- Generated manuscript insertion snippet: `manuscript/manuscript_figures_and_table1.en.md`

Figures:

1. Study flow and analysis layers
2. Source-flow status heatmap
3. Five-state reporting/comparability status
4. Numeric concordance scatter plot
"""
    (PROTOCOL / "manuscript_figures_tables_report.zh.md").write_text(report, encoding="utf-8")
    print(report.strip())


if __name__ == "__main__":
    main()
