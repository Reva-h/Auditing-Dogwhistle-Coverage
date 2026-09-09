# Data Auditing Pipeline

This directory contains a three-stage notebook pipeline that calculates auditing metrics from the cleaned stage-06 dataset and glossary.

Default upstream inputs:

- `../outputs/unioned_data/06_cleaned_labels_glossary_mapped.tsv` (used by stage 00 and stage 01)
- `../outputs/unioned_data/06_glossary_label_reference.tsv` (used by stage 00)

Glossary schema used by this pipeline:

- Primary key: `dogwhistle`
- `surface_forms`: semicolon-separated variants for that dogwhistle

All auditing metrics are computed with equal dogwhistle weighting. A dogwhistle with many surface forms does not receive extra weight versus a dogwhistle with one form.

## Pipeline Overview

Run notebooks in this order:

1. `00_coverage_audit.ipynb`
2. `01_annotation_quality_audit.ipynb`
3. `02_disparity_audit.ipynb`
4. `03_audit_visualizations.ipynb`

## Stages

### Stage 00: Coverage Audit

Notebook: `00_coverage_audit.ipynb`

Detects which glossary dogwhistles appear in the benchmark dataset, then aggregates hit counts into per–(taxonomy\_level, target) metrics.

**What it computes** (per taxonomy\_level × target group):

- **Presence rate** — fraction of glossary dogwhistles for that group that appear at least once in the benchmark: `distinct_dogwhistles_found / total_glossary_dogwhistles`
- **Type coverage** — fraction of dogwhistle types for that group represented in the benchmark: `distinct_types_found / total_glossary_types`
- **Token frequency** — total number of (post, dogwhistle) hit pairs found

Matching works by expanding each dogwhistle's `surface_forms` into individual phrases, running a whole-word regex over all post text, then collapsing matches back to the dogwhistle level so that each dogwhistle counts once per post regardless of how many surface forms it has.

**Exported files:**

| File | Description |
|---|---|
| `audit_metrics.tsv` | One row per (taxonomy\_level, target). Columns: `taxonomy_level`, `target`, `total_glossary_dogwhistles`, `total_glossary_types`, `distinct_dogwhistles_found`, `distinct_types_found`, `presence_rate`, `type_coverage`, `token_frequency`. |
| `audit_detailed.tsv` | One row per (taxonomy\_level, target, dogwhistle) that was found. Columns: `taxonomy_level`, `target`, `dogwhistle`, `matched_posts`. |
| `audit_missing.tsv` | One row per glossary dogwhistle with no match in the benchmark. Columns: `taxonomy_level`, `target`, `dogwhistle`, `status` (always `not_found`). Only written when at least one dogwhistle is missing. |
| `audit_matches.tsv` | Row-level artifact consumed by stage 01. One row per (post, surface\_form, dogwhistle) match. Columns: `text_dedup_key`, `text`, `binary_hate`, `targets`, `found_forms`, `dogwhistle`, `taxonomy_level`, `target`, `type`. |

---

### Stage 01: Annotation Quality Audit

Notebook: `01_annotation_quality_audit.ipynb`

Using the row-level matches from stage 00, classifies each matched post into one of three cases and computes labeling quality metrics.

**Case taxonomy** (per matched post × dogwhistle):

- **Case A** — dogwhistle surface form present in text and post labeled hateful (`binary_hate = 1`): correct detection
- **Case B** — dogwhistle surface form present but post labeled non-hateful (`binary_hate = 0`): annotator failure
- **Case C** — target-group post with no matching dogwhistle hit: collection gap (form not in benchmark)

**What it computes** (per taxonomy\_level × target group):

- **Correct labeling rate** — `case_a / (case_a + case_b)`: fraction of matched posts that were correctly labeled hateful
- **Annotator failure ratio** — `case_b / (case_a + case_b)`: fraction of matched posts that were mislabeled as non-hateful
- **Case B/C ratio** — `case_b / (case_b + case_c)`: diagnostic to distinguish annotation failure (ratio → 1) from collection failure (ratio → 0)
- **Per-dogwhistle labeling accuracy** — same case\_a / (case\_a + case\_b) breakdown broken out at the individual dogwhistle level

Consumes:

- `../outputs/coverage_audits/audit_matches.tsv`
- `../outputs/coverage_audits/audit_metrics.tsv`

**Exported files:**

| File | Description |
|---|---|
| `annotation_quality.tsv` | One row per (taxonomy\_level, target). Columns: `taxonomy_level`, `target`, `case_a_present_hateful`, `case_b_present_nonhateful`, `case_c_absent`, `correct_labeling_rate`, `annotator_failure_ratio`, `total_matches`, `total_target_group_posts`. |
| `case_breakdown.tsv` | Extends `annotation_quality.tsv` with two diagnostic columns: `case_b_c_ratio` and `collection_gap_prop`. |
| `form_labeling_detail.tsv` | One row per (taxonomy\_level, target, dogwhistle). Columns: `taxonomy_level`, `target`, `dogwhistle`, `matched_surface_forms`, `case_a_count`, `case_b_count`, `labeling_accuracy`, `type`. |
| `coverage_metrics_upstream.tsv` | Pass-through copy of `audit_metrics.tsv` from stage 00, forwarded to stage 02. |

---

### Stage 02: Disparity Audit

Notebook: `02_disparity_audit.ipynb`

Compares coverage and annotation quality metrics across target groups within the same taxonomy level, and tracks how those metrics change across levels for the same target group.

**What it computes:**

- **Coverage disparity** (pairwise, within-level) — for each pair of target groups at the same taxonomy level:
  - Absolute gap and disparate impact ratio (min/max) for `presence_rate` and `type_coverage`; DI ratio < 0.8 flags potential disparity under the 80% rule
  - Token frequency ratio (`token_freq_a / token_freq_b`)
- **Annotation disparity** (pairwise, within-level) — for each pair of target groups at the same taxonomy level:
  - Absolute gap in `correct_labeling_rate` and `annotator_failure_ratio`
  - Raw case counts (case A and case B) for both targets for context
- **Cross-level consistency** (within target group, across levels) — for each target group, the delta in `presence_rate`, `type_coverage`, `correct_labeling_rate`, and `annotator_failure_ratio` between consecutive taxonomy levels; sustained negative deltas indicate structural collection or annotation gaps that worsen at finer specificity levels

Consumes:

- `../outputs/annotation_audits/coverage_metrics_upstream.tsv`
- `../outputs/annotation_audits/annotation_quality.tsv`

**Exported files:**

| File | Description |
|---|---|
| `coverage_disparity.tsv` | One row per (taxonomy\_level, target\_a, target\_b) pair. Columns: presence rate and type coverage values, gaps, absolute gaps, and DI ratios for both metrics; token frequency values and ratio. |
| `annotation_disparity.tsv` | One row per (taxonomy\_level, target\_a, target\_b) pair. Columns: correct labeling rate and annotator failure ratio values, gaps, and absolute gaps for both metrics; case A and case B counts for both targets. |
| `cross_level_consistency.tsv` | One row per (target, level\_from, level\_to) transition. Columns: presence rate, type coverage, correct labeling rate, and annotator failure ratio — values at both levels and the delta (level\_to minus level\_from). `None` where a metric is unavailable for a given level. |

Notes:

- Case A/B counts are computed on unique `(post, dogwhistle)` hits.
- Multiple matched surface forms for the same dogwhistle in one post count once.

### Stage 02: Disparity Audit

Notebook: `02_disparity_audit.ipynb`

Consumes:

- `../outputs/annotation_audits/coverage_metrics_upstream.tsv`
- `../outputs/annotation_audits/annotation_quality.tsv`

Produces:

- `../outputs/disparity_audits/coverage_disparity.tsv`
- `../outputs/disparity_audits/annotation_disparity.tsv`

## Notes

- Re-run downstream stages whenever upstream outputs are regenerated.
- Stage 02 assumes one row per `(taxonomy_level, target)` in upstream metric files.
- If stage-06 outputs are regenerated (`06_cleaned_labels_glossary_mapped.tsv` and `06_glossary_label_reference.tsv`), re-run all audit notebooks in order:
  1. `00_coverage_audit.ipynb`
  2. `01_annotation_quality_audit.ipynb`
  3. `02_disparity_audit.ipynb`

### Stage 03: Visualization Audit

Notebook: `03_audit_visualizations.ipynb`

Consumes:

- `../outputs/coverage_audits/audit_metrics.tsv`
- `../outputs/coverage_audits/audit_detailed.tsv`
- `../outputs/annotation_audits/annotation_quality.tsv`
- `../outputs/annotation_audits/case_breakdown.tsv`
- `../outputs/annotation_audits/form_labeling_detail.tsv`
- `../outputs/disparity_audits/coverage_disparity.tsv`
- `../outputs/disparity_audits/annotation_disparity.tsv`
- `../outputs/disparity_audits/cross_level_consistency.tsv`

Produces PNG figures in:

- `../outputs/audit_visualizations/`
