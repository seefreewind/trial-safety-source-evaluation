# Public trial safety source evaluation

Data and code supporting **Interpreting safety outcomes across public sources in pivotal antibody-drug conjugate trials**.

This release provides the archived aggregate extraction data, descriptive reanalysis,
source-audit annotations and execution outputs used in the revised study. The
collection contains 23 trials and 28 retained source-row records. Publications,
ClinicalTrials.gov results and regulatory reviews contribute different reporting
contexts; matching counts alone do not establish interchangeable outcomes.

## Reproduce the analysis

Use Python 3.12 (previously tested with Python 3.12.14). From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r environment/requirements.txt
python scripts/run_reproduction.py --output-dir outputs/my_rerun
```

The output directory must be new or empty. The runner requires no API key,
network request, original PDF or author-specific local directory. It regenerates
descriptive numerical outputs from the archived inputs, then checks those outputs.
Expected tables are used for comparison after calculation, not as calculated results.

## Files and result mapping

| Location | Contents and use |
| --- | --- |
| `data/data/interim/` | Original publication, registry and regulatory extraction seeds |
| `data/data/processed/` | Original trial master and candidate-comparison matrices |
| `data/data/raw/clinicaltrials/` | Archived public registry JSON for all 23 trials |
| `data/tables/` | Original trial characteristics, confirmation inputs, retained packet and source inventories |
| `data/revision_inputs/` | Source-audit annotations, trial matrix and reconciliation inputs |
| `data/revision_audits/` | Editable numerical/source audit workbooks and trial evidence matrix |
| `data/historical_versions/` | Official DREAMM-8 historical records and field comparison |
| `scripts/run_reproduction.py` | Portable entry point for the descriptive reanalysis |
| `scripts/original/` | Unmodified original analysis builders invoked by the runner |
| `scripts/revision_original/` | Original revision scripts retained as provenance, not portable entry points |
| `outputs/final_run/table2_regenerated.csv` | Main Table 2 subgroup summary |
| `outputs/final_run/source_coverage_counts.csv` | Source-extraction coverage underlying Figure 2 |
| `outputs/final_run/r1_reanalysis/reappraised_28_record_inventory.csv` | Annotated retained record inventory underlying Supplementary Table S3 |
| `outputs/final_run/trial_level_summary.csv` | Trial-level coverage supporting Supplementary Tables S1 and S5 |
| `outputs/final_run/historical_screening_counts.csv` | Historical screening units supporting Supplementary Table S2 |
| `provenance/data_dictionary.csv` | Variable definitions and file-level metadata |
| `provenance/source_access_map.csv` | Normalized primary-source access information |
| `SHA256SUMS.txt` | Integrity manifest for the released files |

The nested `data/data/` layout is intentional: it preserves the input paths used by
the portable runner. Source-citation inventories and historical scripts can contain
original local path strings for provenance. The runner does not open those paths.
The original source-verification date is 25 October 2026. Public release preparation
on 29 October 2026 does not change source dates, inclusion rules or scientific values.

## Verification and interpretation boundaries

The supplied execution passed 70 of 70 computation checks, including a relocated
archive rerun. These checks verify regeneration from extracted data and supplied
annotations. They do not repeat independent primary-source extraction or human
adjudication. The supplied A-E classifications are audit inputs. Four interpretation
judgments were VERIFIED and 24 PARTIALLY_VERIFIED; no retained record was certified
fully reporting-context-aligned. No participant-level data or matched person-time
denominators are included.

Historical outputs under `outputs/final_run/tables/`, `manuscript/` and `protocol/`
retain terminology from the original screening workflow. They are provenance, not
the revised A-E categories or a recommendation to restore withdrawn agreement
estimates. Registry all-cause mortality remains distinct from fatal adverse events.
The historical fatal-event search label must not be interpreted as a harmonized
fatal-adverse-event endpoint. The three DESTINY-Breast01 records retain missing arm
IDs without invented replacements; their population differences remain category D.
The cause of the documented count and percentage-display differences remains
unresolved where the source audit did not establish an explanation.

## Rights and exclusions

The authors' analytic materials continue the CC BY 4.0 terms of the original public
deposit. Third-party data and documents retain their applicable original terms.
No rights to third-party material are granted by this repository. Public registry
records and short extracted aggregate values are included with source identifiers.
Copyrighted article full texts, publisher supplements, FDA PDFs, local full-text
extractions, manuscripts, reviewer correspondence, credentials and participant-level
records are excluded. See `RIGHTS.md`.

## Versioning and citation

This repository is an independent release of the revised study materials. The earlier
project is preserved at https://github.com/seefreewind/adc-safety-lifecycle and
https://doi.org/10.5281/zenodo.20768718. Those earlier records do not contain the
present revision package. This release does not overwrite them.

Lin, Da and Zhang, Yu (2026). Interpreting safety outcomes across public sources in pivotal antibody-drug conjugate trials: data and code.
Version 1.0.0. https://github.com/seefreewind/trial-safety-source-evaluation.

`CITATION.cff` supplies citation metadata. `.zenodo.json` describes this release for
GitHub-Zenodo integration. A Zenodo DOI should be cited only after the release has
actually been archived and its public record verified.
