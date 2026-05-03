# benchmarking_dogwhistles

Preprocessing pipeline for Section 4.1 of the dogwhistle benchmark audit project.

## Preprocessing Pipeline Summary

The primary pipeline is the modular notebook sequence in [data_preprocessing](data_preprocessing), documented in detail at [data_preprocessing/README.md](data_preprocessing/README.md).

Run order:
1. [data_preprocessing/00_glossary_formatter.ipynb](data_preprocessing/00_glossary_formatter.ipynb)
2. [data_preprocessing/01_hatexplain_formatting.ipynb](data_preprocessing/01_hatexplain_formatting.ipynb)
3. [data_preprocessing/02_mhs_formatting.ipynb](data_preprocessing/02_mhs_formatting.ipynb)
4. [data_preprocessing/03_elsherief_formatting.ipynb](data_preprocessing/03_elsherief_formatting.ipynb)
5. [data_preprocessing/04_union_and_dedup.ipynb](data_preprocessing/04_union_and_dedup.ipynb)
6. [data_preprocessing/05_target_label_analysis_and_filtering.ipynb](data_preprocessing/05_target_label_analysis_and_filtering.ipynb)

At a high level, this pipeline:
1. Builds glossary artifacts from glossary source files into [outputs/glossary](outputs/glossary).
2. Standardizes each source dataset into a shared post-level schema.
3. Unions standardized outputs and deduplicates with ID-first, text-key fallback logic.
4. Normalizes/analyzes target labels and optionally filters low-support groups.
5. Writes stage outputs under [outputs/glossary](outputs/glossary), [outputs/preprocessing](outputs/preprocessing), and [outputs/unioned_data](outputs/unioned_data).

Legacy notebook note:
- [preprocessing_pipeline.ipynb](preprocessing_pipeline.ipynb) is an older monolithic variant kept for reference.

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
	preprocessing_pipeline.ipynb
	data_preprocessing/
		00_glossary_formatter.ipynb
		01_hatexplain_formatting.ipynb
		02_mhs_formatting.ipynb
		03_elsherief_formatting.ipynb
		04_union_and_dedup.ipynb
		05_target_label_analysis_and_filtering.ipynb
		README.md
	README.md
	requirements.txt
	data/
		hatexplain.json
		measuring_hate_speech.parquet
		implicit-hate-corpus/
			implicit_hate_v1_stg3_posts.tsv
			...
	outputs/
		preprocessing/
			01_hatexplain_standardized.tsv
			02_mhs_standardized.tsv
			03_elsherief_standardized.tsv
		unioned_data/
			04_union_primary.tsv
			04_dedup_primary.tsv
			04_union_dedup_summary.tsv
			05_union_primary_filtered.tsv
			05_dedup_primary_filtered.tsv
			05_raw_label_counts_for_annotation.tsv
		glossary/
			glossary.tsv
```

Notes:
- [data/measuring_hate_speech.parquet](data/measuring_hate_speech.parquet) is used as a local cache and can be auto-created by the notebook.
- ElSherief is optional and controlled with `include_elsherief` in the config cell.

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

If needed, you can still run the monolithic reference notebook [preprocessing_pipeline.ipynb](preprocessing_pipeline.ipynb).

## Auditing Notebooks

Post-preprocessing audit notebooks live in [auditing](auditing) and are documented in [auditing/README.md](auditing/README.md).

Recommended run order:
1. [auditing/00_coverage_audit.ipynb](auditing/00_coverage_audit.ipynb)
2. [auditing/01_annotation_quality_audit.ipynb](auditing/01_annotation_quality_audit.ipynb)
3. [auditing/02_disparity_audit.ipynb](auditing/02_disparity_audit.ipynb)
4. [auditing/03_audit_visualizations.ipynb](auditing/03_audit_visualizations.ipynb)

## Annotation Agreement

Inter-annotator agreement (IAA) is computed separately in [annotations/inter_annotator_agreement.ipynb](annotations/inter_annotator_agreement.ipynb), alongside the annotation TSV files it reads.

The IAA notebook computes agreement between Reva and Ryan for both target-label mapping and dogwhistle inferred-target annotation tasks using:

- Exact Match %
- Mean Jaccard Similarity
- Macro-averaged Cohen's kappa (per-label binary formulation)
- Krippendorff's alpha with Jaccard distance

It also includes a top-20 per-label kappa breakdown and built-in sanity checks against expected benchmark values.

## Glossary Stage

The glossary formatter is stage `00` of the modular pipeline:

- [data_preprocessing/00_glossary_formatter.ipynb](data_preprocessing/00_glossary_formatter.ipynb)

Outputs from glossary stage:
- [outputs/glossary/glossary.tsv](outputs/glossary/glossary.tsv)

## Configuration

Edit the config cells in the modular notebooks under [data_preprocessing](data_preprocessing):

- [data_preprocessing/01_hatexplain_formatting.ipynb](data_preprocessing/01_hatexplain_formatting.ipynb): HateXplain input path and hate majority threshold.
- [data_preprocessing/02_mhs_formatting.ipynb](data_preprocessing/02_mhs_formatting.ipynb): local/remote MHS source, refresh behavior, and primary threshold.
- [data_preprocessing/03_elsherief_formatting.ipynb](data_preprocessing/03_elsherief_formatting.ipynb): stage-1/stage-3 ElSherief source paths.
- [data_preprocessing/04_union_and_dedup.ipynb](data_preprocessing/04_union_and_dedup.ipynb): `include_elsherief` and union/dedup output paths.
- [data_preprocessing/05_target_label_analysis_and_filtering.ipynb](data_preprocessing/05_target_label_analysis_and_filtering.ipynb): filtering controls and filtered export paths.

The monolithic [preprocessing_pipeline.ipynb](preprocessing_pipeline.ipynb) retains its own config cell for legacy use.

## Output Files

Primary files written by the modular pipeline:

From [outputs/preprocessing](outputs/preprocessing):
- `01_hatexplain_standardized.tsv`
- `02_mhs_standardized.tsv`
- `03_elsherief_standardized.tsv`

From [outputs/unioned_data](outputs/unioned_data):
- `04_union_primary.tsv`
- `04_dedup_primary.tsv`
- `04_union_dedup_summary.tsv`
- `05_union_primary_filtered.tsv`
- `05_dedup_primary_filtered.tsv`
- `05_raw_label_counts_for_annotation.tsv`

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
- Sensitivity analysis with `sensitivity_thresholds` is available in the legacy [preprocessing_pipeline.ipynb](preprocessing_pipeline.ipynb).