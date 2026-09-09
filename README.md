# benchmarking_dogwhistles

Benchmark audit for Section 4.1 of the dogwhistle project — preprocessing,
annotation, and programmatic RQ analysis.

## Repository Structure

| Directory | Purpose |
|---|---|
| [`data_preprocessing/`](data_preprocessing/README.md) | Notebook pipeline: parse glossary → standardize datasets → union/dedup → apply annotations |
| [`annotations/`](annotations/README.md) | Annotator TSVs, merge notebook, IAA notebook |
| [`annotation_results/`](annotation_results/) | Raw annotation output TSVs from each annotator (Ryan's glossary and label files) |
| [`audit_pipeline/`](audit_pipeline/README.md) | Python pipeline: coverage → annotation quality → disparity → rollup → robustness check |
| [`fpr_annotation/`](fpr_annotation/) | False-positive-rate annotation task: sampler script, annotator worksheets, and collected judgments |
| [`scripts/`](scripts/README.md) | Shell entry points for running the data-preprocessing and audit pipelines end-to-end |
| [`deprecated/`](deprecated/README.md) | Superseded/orphaned code kept for reference only — not part of the reproducible pipeline |
| `scratch/` | Personal working notes and exploratory drafts — not part of the reproducible pipeline |

## End-to-End Workflow

### Step 1 — Data Preprocessing

Runs notebooks `00` through `06` in order.  Output: cleaned, annotated corpus under `outputs/`.

```bash
scripts/run_data_preprocessing.sh
```

Notebook `06` reads the raw per-annotator files (`annotations/reva_labels.tsv`,
`ryan_labels.tsv`, `reva_glossary.tsv`, `ryan_glossary.tsv`) directly and
derives its own union — `annotations/merge_annotation_union.ipynb` is **not**
a prerequisite for this step. That notebook is a separate analysis producing
`merged_*.tsv` / `merged_*_resolved.tsv`, consumed only by
`annotations/inter_annotator_agreement.ipynb` (see
[Annotation Agreement](#annotation-agreement) below).

### Step 2 — Audit Pipeline (RQ metrics and figures)

Reads from Step 1 outputs.  Runs two passes by default, then compares them:

- **Primary analysis** (all glossary tiers) → `outputs/stage1/` … `outputs/stage4/`
- **Tier-1+2 robustness check** (explicit slurs and stereotype-based terms only) → `outputs/stage1_tier12/` … `outputs/stage4_tier12/`
- **Comparison** — once both passes have run, `audit_pipeline/robustness_check.py` compares their Stage 4 outputs pair-by-pair, per level and pooled → `outputs/robustness_check/`

```bash
python -m audit_pipeline.run_all
```

Run only the primary analysis (skip the robustness check and its comparison):

```bash
scripts/run_audit_pipeline.sh --no-robustness
```

Individual stages can be rerun independently (defaults to full variant):

```bash
python -m audit_pipeline.stage1_coverage
python -m audit_pipeline.stage1_coverage --variant tier12
python -m audit_pipeline.robustness_check
```

## Preprocessing Pipeline Summary

The primary pipeline is the modular notebook sequence in [data_preprocessing](data_preprocessing), documented in detail at [data_preprocessing/README.md](data_preprocessing/README.md).

Run order:
1. [data_preprocessing/00_glossary_formatter.ipynb](data_preprocessing/00_glossary_formatter.ipynb)
2. [data_preprocessing/01_hatexplain_formatting.ipynb](data_preprocessing/01_hatexplain_formatting.ipynb)
3. [data_preprocessing/02_mhs_formatting.ipynb](data_preprocessing/02_mhs_formatting.ipynb)
4. [data_preprocessing/03_elsherief_formatting.ipynb](data_preprocessing/03_elsherief_formatting.ipynb)
5. [data_preprocessing/04_union_and_dedup.ipynb](data_preprocessing/04_union_and_dedup.ipynb)
6. [data_preprocessing/05_target_label_analysis_and_filtering.ipynb](data_preprocessing/05_target_label_analysis_and_filtering.ipynb)
7. [data_preprocessing/06_apply_annotations.ipynb](data_preprocessing/06_apply_annotations.ipynb) — reads the raw per-annotator files directly and derives its own union; does not depend on `annotations/merge_annotation_union.ipynb`

At a high level, this pipeline:
1. Builds glossary artifacts from glossary source files into [outputs/glossary](outputs/glossary).
2. Standardizes each source dataset into a shared post-level schema.
3. Unions standardized outputs and deduplicates with ID-first, text-key fallback logic.
4. Normalizes/analyzes target labels and optionally filters low-support groups.
5. Applies human annotation schemas and writes cleaned labels.
6. Writes stage outputs under [outputs/glossary](outputs/glossary), [outputs/preprocessing](outputs/preprocessing), and [outputs/unioned_data](outputs/unioned_data).

Shared schema used throughout the notebook:
- `post_id`
- `text`
- `raw_label`
- `binary_hate`
- `targets`
- `dataset`
- `text_dedup_key`

For MHS post-level aggregation, the notebook also keeps:
- `n_annotations`

## Expected Directory Structure

Expected project layout for a successful run:

```text
benchmarking_dogwhistles/
	data_preprocessing/       # notebook pipeline (stages 00–06)
	annotations/              # annotator TSVs + merge + IAA notebooks
	annotation_results/       # raw per-annotator output TSVs
	audit_pipeline/           # Python RQ analysis pipeline
	fpr_annotation/           # FPR annotation task (sampler, worksheets, judgments)
	scripts/                  # shell entry points for data_preprocessing and audit_pipeline
	deprecated/               # superseded/orphaned code, kept for reference only
	scratch/                  # personal working notes (gitignored)
	data/
		glossary.md
		hatexplain.json
		measuring_hate_speech.parquet
		implicit-hate-corpus/
			implicit_hate_v1_stg1_posts.tsv
			implicit_hate_v1_stg3_posts.tsv
			...
	outputs/
		glossary/
			glossary.tsv                         # master term list with tier, targets, persona
			glossary_persona_by_tier.tsv         # persona/target breakdown aggregated by tier
			glossary_pipeline_groups_by_tier.tsv # pipeline group mapping by tier
			glossary_sparse_t12.tsv              # glossary restricted to tiers 1+2 (robustness variant)
			glossary_tier_summary.txt            # human-readable term counts per tier
		preprocessing/
			01_hatexplain_standardized.tsv       # HateXplain in shared schema
			02_mhs_standardized.tsv              # MHS in shared schema
			03_elsherief_standardized.tsv        # ElSherief in shared schema (optional)
		unioned_data/
			04_union_primary.tsv                 # all datasets unioned before dedup
			04_dedup_primary.tsv                 # deduplicated corpus (canonical set)
			04_union_dedup_summary.tsv           # dedup statistics and collision counts
			05_union_primary_filtered.tsv        # union after low-support group filtering
			05_dedup_primary_filtered.tsv        # dedup after filtering
			05_raw_label_counts_for_annotation.tsv # per-label counts sent to annotators
			06_cleaned_labels.tsv                # normalized target labels post-annotation
			06_cleaned_labels_glossary_mapped.tsv # labels joined to glossary term metadata
			06_glossary_label_reference.tsv      # reference table: raw label → glossary term
		stage1/                                  # coverage audit outputs (all glossary tiers)
		stage1_tier12/                           # same, restricted to tiers 1+2
		stage2/                                  # annotation quality outputs
		stage2_tier12/
		stage3/                                  # disparity outputs
		stage3_tier12/
		stage4/                                  # rollup outputs (group and level×group)
		stage4_tier12/
		robustness_check/                        # full-vs-tier12 comparison table (see below)
		group_labels.tsv                         # canonical group label reference
```

Notes:
- [data/measuring_hate_speech.parquet](data/measuring_hate_speech.parquet) is used as a local cache and can be auto-created by the notebook.
- ElSherief is optional and controlled with `include_elsherief` in the config cell.
- Every `stageN/` directory has a parallel `stageN_tier12/` containing identical outputs computed on the tier-1+2-only glossary variant.

## Environment Setup

Set up a virtual environment and install dependencies from [requirements.txt](requirements.txt):

```bash
cd /Users/RevaH/Documents/COS534/benchmarking_dogwhistles
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Then select the `.venv` interpreter as the notebook kernel in VS Code before running notebooks.

## Running the Data Preprocessing Notebooks

Use the stage-by-stage notebooks in [data_preprocessing](data_preprocessing):

1. Run [data_preprocessing/00_glossary_formatter.ipynb](data_preprocessing/00_glossary_formatter.ipynb)
2. Run [data_preprocessing/01_hatexplain_formatting.ipynb](data_preprocessing/01_hatexplain_formatting.ipynb)
3. Run [data_preprocessing/02_mhs_formatting.ipynb](data_preprocessing/02_mhs_formatting.ipynb)
4. Run [data_preprocessing/03_elsherief_formatting.ipynb](data_preprocessing/03_elsherief_formatting.ipynb)
5. Run [data_preprocessing/04_union_and_dedup.ipynb](data_preprocessing/04_union_and_dedup.ipynb)
6. Run [data_preprocessing/05_target_label_analysis_and_filtering.ipynb](data_preprocessing/05_target_label_analysis_and_filtering.ipynb)

For detailed stage behavior and inputs/outputs, see [data_preprocessing/README.md](data_preprocessing/README.md).

## Annotation Agreement

Inter-annotator agreement (IAA) is computed separately in [annotations/inter_annotator_agreement.ipynb](annotations/inter_annotator_agreement.ipynb), alongside the annotation TSV files it reads.

The IAA notebook computes agreement between Reva and Ryan for both target-label mapping and dogwhistle inferred-target annotation tasks using:

- Exact Match %
- Mean Jaccard Similarity
- Macro-averaged Cohen's kappa (per-label binary formulation)
- Krippendorff's alpha with Jaccard distance

It also includes a top-20 per-label kappa breakdown and built-in sanity checks against expected benchmark values.

## FPR Annotation

The `fpr_annotation/` directory contains the false-positive-rate (FPR) annotation task, which asks human annotators to judge whether each corpus post is using a matched dogwhistle term genuinely (as coded hate speech), as counter-speech, journalistically, or in an unclear way.

The task samples 75 posts per coding level (L2 / L3 / L4) from `outputs/stage1/s1_matches.tsv`, stratified to avoid excluded target groups (`referential_white_supremacist`, `unknown`, `minority`).

| File | Contents |
|---|---|
| `sample_fpr.py` | Sampler script: draws the 75-per-level budget, seeds locked rows from a prior annotator's completed worksheet, and writes the worksheet/join-table outputs |
| `worksheet_materials/fpr_annotation_worksheet_blank.csv` | Annotator-facing worksheet: `row_id`, `post_text`, `matched_surface_form`, `benchmark_label`, blank `judgment` and `annotator_notes` columns |
| `worksheet_materials/fpr_annotator_instructions.md` / `.pdf` | Annotator briefing sheet explaining the judgment task and options |
| `fpr_join_table.csv` | Join table linking each `row_id` to its glossary metadata (`row_id`, `text_dedup_key`, `dogwhistle`, `matched_surface_form`, `coding_level`, `all_target_groups`, `binary_hate`, `dataset`) |
| `completed_labels/annotator1.tsv`, `annotator2.tsv` | Collected raw annotations: `row_id`, `text_dedup_key`, `dataset`, `benchmark_label`, `matched_surface_form`, `post_text`, `judgment`, `annotator_notes` |
| `fpr_iaa_analysis.ipynb` | Computes FPR rates and inter-annotator agreement from `completed_labels/`; produces the paper's FPR figures and numbers (see below) |
| `outputs/fpr_iaa_fig1_fpr_by_level.pdf`, `fpr_iaa_fig2_agreement_matrix.pdf`, `fpr_iaa_fig4_annotator_vs_benchmark.pdf` | Figures cited in the paper (`fpr_iaa_fig3_unclear_rate.pdf` is also generated but currently commented out in the paper) |
| `outputs/fpr_reportable_metrics.txt` | Headline FPR/agreement numbers cited in the paper's text |

## Glossary Stage

The glossary formatter is stage `00` of the modular pipeline:

- [data_preprocessing/00_glossary_formatter.ipynb](data_preprocessing/00_glossary_formatter.ipynb)

Outputs written to [outputs/glossary/](outputs/glossary/):

| File | Contents |
|---|---|
| `glossary.tsv` | Master term list: dogwhistle term, surface forms, persona/covert meaning, type, register, description + provenance, and tier |
| `glossary_persona_by_tier.tsv` | Persona and target-group breakdown aggregated by tier |
| `glossary_pipeline_groups_by_tier.tsv` | Mapping of pipeline-normalized group names by tier |
| `glossary_sparse_t12.tsv` | Glossary restricted to tiers 1+2 — input to the robustness (`tier12`) pipeline variant |
| `glossary_tier_summary.txt` | Human-readable term and target counts per tier |

## Configuration

Edit the config cells in the modular notebooks under [data_preprocessing](data_preprocessing):

- [data_preprocessing/01_hatexplain_formatting.ipynb](data_preprocessing/01_hatexplain_formatting.ipynb): HateXplain input path and hate majority threshold.
- [data_preprocessing/02_mhs_formatting.ipynb](data_preprocessing/02_mhs_formatting.ipynb): local/remote MHS source, refresh behavior, and primary threshold.
- [data_preprocessing/03_elsherief_formatting.ipynb](data_preprocessing/03_elsherief_formatting.ipynb): stage-1/stage-3 ElSherief source paths.
- [data_preprocessing/04_union_and_dedup.ipynb](data_preprocessing/04_union_and_dedup.ipynb): `include_elsherief` and union/dedup output paths.
- [data_preprocessing/05_target_label_analysis_and_filtering.ipynb](data_preprocessing/05_target_label_analysis_and_filtering.ipynb): filtering controls and filtered export paths.

Audit pipeline thresholds and pipeline variants (full vs. tier-1+2 robustness check) are set in [`audit_pipeline/config.py`](audit_pipeline/config.py).

## Output Files

### Preprocessing outputs

From [outputs/preprocessing/](outputs/preprocessing/):

| File | Contents |
|---|---|
| `01_hatexplain_standardized.tsv` | HateXplain posts in shared schema (post_id, text, binary_hate, targets, dataset, text_dedup_key) |
| `02_mhs_standardized.tsv` | MHS posts in shared schema, with `n_annotations` from post-level aggregation |
| `03_elsherief_standardized.tsv` | ElSherief posts in shared schema (only present when ElSherief is included) |

From [outputs/unioned_data/](outputs/unioned_data/):

| File | Contents |
|---|---|
| `04_union_primary.tsv` | All three datasets unioned before deduplication |
| `04_dedup_primary.tsv` | Deduplicated corpus — canonical input to all downstream stages |
| `04_union_dedup_summary.tsv` | Dedup statistics: per-dataset row counts, ElSherief inclusion, cross-dataset conflict-key/row counts, deduplicated row count, and label-conflict count (flat metric/value table, not broken out by dataset pair) |
| `05_union_primary_filtered.tsv` | Union after filtering out target groups below the support threshold |
| `05_dedup_primary_filtered.tsv` | Deduplicated version of the filtered union |
| `05_raw_label_counts_for_annotation.tsv` | Per-label counts extracted for the human annotation task |
| `06_cleaned_labels.tsv` | Normalized target labels after applying human annotation decisions |
| `06_cleaned_labels_glossary_mapped.tsv` | `06_cleaned_labels.tsv` plus `glossary_mapped_taxonomy_levels`, `glossary_mapped_targets`, `glossary_mapped_types` |
| `06_glossary_label_reference.tsv` | Reference table mapping each raw corpus label to its canonical glossary term |

### Audit pipeline outputs

Each stage writes to `outputs/stageN/` for the primary (all-tier) run and `outputs/stageN_tier12/` for the tier-1+2 robustness check.

#### Stage 1 — Coverage ([outputs/stage1/](outputs/stage1/))

| File | Contents |
|---|---|
| `s1_matches.tsv` | All matches of glossary terms against corpus posts: one row per (post, term, surface form) match |
| `s1_coverage_detailed.tsv` | Per-(level, target, dogwhistle) match detail: matched-post count and a self-referential flag. (Presence-rate/type-coverage figures live in `s1_coverage_by_level_target.tsv`, not here.) |
| `s1_coverage_by_level_target.tsv` | Coverage aggregated by coding level × target group |
| `s1_coverage_missing.tsv` | Glossary terms with zero corpus matches |

#### Stage 2 — Annotation Quality ([outputs/stage2/](outputs/stage2/))

| File | Contents |
|---|---|
| `s2_annotation_by_level_target.tsv` | Annotation rates (% labeled, correct, failure) by coding level × target group |
| `s2_form_labeling_detail.tsv` | Per-dogwhistle annotation label breakdown (case A/B counts; all matched surface forms for that dogwhistle collapsed into one semicolon-joined row) |

#### Stage 3 — Disparity ([outputs/stage3/](outputs/stage3/))

| File | Contents |
|---|---|
| `s3_annotation_disparity.tsv` | Annotation label disparity between group pairs |
| `s3_coverage_disparity.tsv` | Coverage rate disparity between group pairs |
| `s3_cross_level_consistency.tsv` | Cross-level consistency check: whether the same term is covered/labeled consistently across L2/L3/L4 |

#### Stage 4 — Rollup ([outputs/stage4/](outputs/stage4/))

Rollup outputs are organized into three sub-directories:

**`by_group/`** — metrics collapsed to target group:

| File | Contents |
|---|---|
| `s4a_annotation_by_group.tsv` | Annotation rates aggregated per target group |
| `s4a_coverage_by_group.tsv` | Coverage rates aggregated per target group |
| `s4a_pairwise_disparity_by_group.tsv` | Pairwise disparity index (DI) between all group pairs |
| `s4a_pass_fail_summary.tsv` | Per-group pass/fail audit verdict across coverage and annotation thresholds |

**`by_level_group/`** — metrics stratified by coding level × group:

| File | Contents |
|---|---|
| `s4b_annotation_by_level_group.tsv` | Annotation rates by level × group |
| `s4b_coverage_by_level_group.tsv` | Coverage rates by level × group |
| `s4b_pairwise_disparity_by_level_group.tsv` | Pairwise DI by level × group |

**`elsherief/`** — delta tables comparing union corpus vs. ElSherief-only:

| File | Contents |
|---|---|
| `s4c_annotation_delta_union_vs_elsherief.tsv` | Per-group annotation rate delta between union and ElSherief-only |
| `s4c_coverage_delta_union_vs_elsherief.tsv` | Per-group coverage rate delta |
| `s4c_pairwise_delta_union_vs_elsherief.tsv` | Pairwise DI delta |

### Robustness check output ([outputs/robustness_check/](outputs/robustness_check/))

Written once, after both the `full` and `tier12` variants have completed —
compares their Stage 4 outputs directly (does not re-run Stage 1-4 or
re-derive anything from raw preprocessed data):

| File | Contents |
|---|---|
| `robustness_comparison.tsv` | One row per (pair, level, metric): full-glossary value, tier-1+2 value, whether the pair passes the 4/5 rule under each, whether that conclusion changes, and the direction of the shift. Covers both fine-grained/raw-taxonomy-target pairs and collapsed reporting-group pairs, at every coding level plus one pooled-coverage-DI row per pair. |
| `README.md` | Column reference and the pooled-DI methodology note (see below). |

**Pooled DI:** computed by summing each group's raw counts across *all*
coding levels first, then computing one DI ratio from the pooled rates —
not by taking `min()` of each level's own ratio (a different, older
methodology used by `generate_figures_final.py`'s now-deprecated
`appD_worst_di_and_label_gap_pooled`, which gives a different number for
the same pair). See `audit_pipeline/robustness_check.py`'s module
docstring for the full explanation and a concrete example.

### Annotation results ([annotation_results/](annotation_results/))

Raw per-annotator output files before merge:

| File | Contents |
|---|---|
| `ryan_glossary_annotations.tsv` | Ryan's raw annotations for the glossary-mapping task |
| `ryan_label_annotations.tsv` | Ryan's raw annotations for the target-label task |

Reva's counterpart files live in [annotations/](annotations/) alongside the merge and IAA notebooks.

## Rerunning with ElSherief

When ElSherief data is available:
1. Ensure both stage files exist locally:
	- [data/implicit-hate-corpus/implicit_hate_v1_stg1_posts.tsv](data/implicit-hate-corpus/implicit_hate_v1_stg1_posts.tsv)
	- [data/implicit-hate-corpus/implicit_hate_v1_stg3_posts.tsv](data/implicit-hate-corpus/implicit_hate_v1_stg3_posts.tsv)
2. Run [data_preprocessing/03_elsherief_formatting.ipynb](data_preprocessing/03_elsherief_formatting.ipynb).
3. Set `include_elsherief = True` in [data_preprocessing/04_union_and_dedup.ipynb](data_preprocessing/04_union_and_dedup.ipynb).
4. Re-run [data_preprocessing/04_union_and_dedup.ipynb](data_preprocessing/04_union_and_dedup.ipynb) and [data_preprocessing/05_target_label_analysis_and_filtering.ipynb](data_preprocessing/05_target_label_analysis_and_filtering.ipynb).

## Notes

- MHS fetch is one-time unless `refresh_mhs_local_copy=True`.
- Dedup prioritizes `post_id` and falls back to `text_dedup_key`.
- Sensitivity analysis with `sensitivity_thresholds` is available in `scratch/preprocessing_pipeline.ipynb` (exploratory draft, not part of the reproducible pipeline).