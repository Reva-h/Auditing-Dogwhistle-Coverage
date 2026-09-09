# Data Preprocessing Pipeline

This directory contains the modular notebook pipeline that builds the unified corpus used by downstream audits.

## Pipeline Overview

The pipeline runs in seven stages:

1. `00_glossary_formatter.ipynb`
2. `01_hatexplain_formatting.ipynb`
3. `02_mhs_formatting.ipynb`
4. `03_elsherief_formatting.ipynb` (optional in downstream union)
5. `04_union_and_dedup.ipynb`
6. `05_target_label_analysis_and_filtering.ipynb`
7. `06_apply_annotations.ipynb`

Stage `00` produces glossary artifacts under `outputs/glossary`. Stages `01`-`03` standardize individual source datasets into a shared schema. Stage `04` unions and deduplicates those standardized tables. Stage `05` normalizes target labels, analyzes distributions, and optionally filters low-support groups. Stage `06` applies the human annotation schemas and exports cleaned labels for downstream analysis.

## Notebook Stages In Detail

### 00 Glossary Formatter

Notebook: `00_glossary_formatter.ipynb`

What it does:

1. Parses glossary source files in `data/`.
2. Produces a consolidated glossary TSV.
3. Computes grouped metrics and visualization summaries in notebook cells.

Outputs:

- `outputs/glossary/glossary.tsv` — master term list (columns: `term`, `surface_forms`, `persona_in_group`, `covert_meaning`, `type`, `register`, `description`, `description_source`, `example_count`, `examples`, `example_sources`, `example_speakers`, `example_dates`, `source_domain`, `tier`)
- `outputs/glossary/glossary_tier_summary.txt` — human-readable term/target counts per tier
- `outputs/glossary/glossary_pipeline_groups_by_tier.tsv` — pipeline-normalized group names by tier
- `outputs/glossary/glossary_sparse_t12.tsv` — glossary restricted to tiers 1+2 (input to the `tier12` robustness variant)
- `outputs/glossary/glossary_persona_by_tier.tsv` — persona/target breakdown aggregated by tier

## Shared Schema

The standardized outputs use this core schema:

- `post_id`
- `text`
- `raw_label`
- `binary_hate`
- `targets`
- `dataset`
- `text_dedup_key`

Additional columns may appear for specific sources (for example, `n_annotations` in the MHS standardized output).

### 01 HateXplain Formatting

Notebook: `01_hatexplain_formatting.ipynb`

What it does:

1. Loads HateXplain JSON from `data/hatexplain.json`.
2. Normalizes text and target fields.
3. Computes `binary_hate` using a positive-only majority rule from annotator labels.
4. Exports one standardized row per post.

Output:

- `outputs/preprocessing/01_hatexplain_standardized.tsv`

### 02 MHS Formatting

Notebook: `02_mhs_formatting.ipynb`

What it does:

1. Loads MHS from local parquet cache `data/measuring_hate_speech.parquet`.
2. Optionally refreshes from the configured Hugging Face parquet URI.
3. Harmonizes annotator-level rows into the shared schema.
4. Aggregates to one post-level row and computes `binary_hate` from the post-level mean score threshold.

Outputs:

- `outputs/preprocessing/02_mhs_standardized.tsv`
- Optional local cache refresh: `data/measuring_hate_speech.parquet`

### 03 ElSherief Formatting

Notebook: `03_elsherief_formatting.ipynb`

What it does:

1. Uses `data/implicit-hate-corpus/implicit_hate_v1_stg1_posts.tsv` as the base post table.
2. Uses `data/implicit-hate-corpus/implicit_hate_v1_stg3_posts.tsv` to recover target annotations.
3. Merges/normalizes fields into the shared schema.
4. Keeps posts with no stage-3 target annotation and assigns `unknown` target.

Output:

- `outputs/preprocessing/03_elsherief_standardized.tsv`

### 04 Union and Dedup

Notebook: `04_union_and_dedup.ipynb`

Inputs:

- `outputs/preprocessing/01_hatexplain_standardized.tsv`
- `outputs/preprocessing/02_mhs_standardized.tsv`
- `outputs/preprocessing/03_elsherief_standardized.tsv` (optional via config)

What it does:

1. Loads available standardized datasets.
2. Enforces required columns.
3. Unions selected datasets.
4. Deduplicates with an ID-first strategy, then `text_dedup_key` fallback.
5. Writes a compact run summary.

Outputs:

- `outputs/unioned_data/04_union_primary.tsv`
- `outputs/unioned_data/04_dedup_primary.tsv`
- `outputs/unioned_data/04_union_dedup_summary.tsv`

### 05 Target Label Analysis and Filtering

Notebook: `05_target_label_analysis_and_filtering.ipynb`

Inputs:

- `outputs/unioned_data/04_union_primary.tsv`
- `outputs/unioned_data/04_dedup_primary.tsv`

What it does:

1. Parses raw target labels and logs unique labels by dataset.
2. Maps raw labels to canonical standardized labels (`target_std`).
3. Reports target label breakdowns for all rows and for `binary_hate == 1`.
4. Optionally filters low-support groups based on positive-hate support thresholds.
5. Exports filtered datasets and a raw-label count table for annotation.

Outputs:

- `outputs/unioned_data/05_union_primary_filtered.tsv`
- `outputs/unioned_data/05_dedup_primary_filtered.tsv`
- `outputs/unioned_data/05_raw_label_counts_for_annotation.tsv`

### 06 Apply Annotations

Inputs:

- `outputs/unioned_data/05_union_primary_filtered.tsv`
- `annotations/reva_labels.tsv`, `annotations/ryan_labels.tsv`
- `annotations/reva_glossary.tsv`, `annotations/ryan_glossary.tsv`
- `outputs/glossary/glossary.tsv`
- `outputs/group_labels.tsv`

What it does:

1. Loads the raw per-annotator label and glossary TSVs directly from `annotations/` (not the pre-merged `merged_*.tsv` files there — this notebook derives its own union independently of `annotations/merge_annotation_union.ipynb`).
2. Aggregates direct raw-target annotations and glossary-term annotations into a future-proof annotator-aware structure.
3. Resolves disagreements by taking the union of assigned labels.
4. Applies those annotations into a new `cleaned_label` column.
5. Maps matched glossary terms to taxonomy-level and target labels for downstream audits.
6. Reports raw label counts split across hate and non-hate rows and renders summary figures.

Outputs:

- `outputs/unioned_data/06_cleaned_labels.tsv`
- `outputs/unioned_data/06_cleaned_labels_glossary_mapped.tsv` — `06_cleaned_labels.tsv` plus `glossary_mapped_taxonomy_levels`, `glossary_mapped_targets`, `glossary_mapped_types`
- `outputs/unioned_data/06_glossary_label_reference.tsv`

## Typical Execution Order

Run notebooks from `00` to `06` in order. If you only need glossary outputs, run `00` only. If you only need the unioned corpus and dedup outputs, you can run `01` to `05`.

## Configuration Notes

- `02_mhs_formatting.ipynb`: controls local-vs-remote MHS loading and threshold settings.
- `04_union_and_dedup.ipynb`: `include_elsherief` controls whether stage `03` output is included.
- `05_target_label_analysis_and_filtering.ipynb`: controls filtering behavior and export of filtered outputs.
- `06_apply_annotations.ipynb`: controls how direct annotations, glossary annotations, and legacy target backfills are merged into `cleaned_label`.

The glossary stage writes all outputs to `outputs/glossary/`.

## Quick Start

From the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Then open the notebooks in this folder and run them top-to-bottom in stage order.