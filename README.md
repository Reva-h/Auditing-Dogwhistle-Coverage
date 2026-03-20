# benchmarking_dogwhistles

Preprocessing pipeline for Section 4.1 of the dogwhistle benchmark audit project.

## Preprocessing Pipeline Summary

The notebook [preprocessing_pipeline.ipynb](preprocessing_pipeline.ipynb) builds a unified, post-level corpus from HateXplain and Measuring Hate Speech (MHS), with optional ElSherief augmentation.

At a high level, the pipeline:
1. Loads local HateXplain JSON and local MHS parquet.
2. Falls back to Hugging Face for MHS only when the local parquet is missing (or refresh is requested).
3. Harmonizes datasets into a shared schema.
4. Standardizes granularity to one row per post (MHS is aggregated from annotator-level rows).
5. Unions datasets and deduplicates by ID and normalized text.
6. Runs threshold sensitivity summaries.
7. Validates that target annotations are preserved.
8. Exports final TSV artifacts under [outputs/preprocessing](outputs/preprocessing).

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
			hatexplain_standardized.tsv
			mhs_standardized.tsv
			union_primary.tsv
			dedup_primary.tsv
			sensitivity_summary.tsv
```

Notes:
- [data/measuring_hate_speech.parquet](data/measuring_hate_speech.parquet) is used as a local cache and can be auto-created by the notebook.
- ElSherief is optional and controlled with `include_elsherief` in the config cell.

## Requirements

Recommended Python packages:
- `pandas`
- `pyarrow`
- `fsspec`
- `huggingface_hub`

In the notebook environment:

```python
%pip install pandas pyarrow fsspec huggingface_hub
```

## Running the Notebook

Open [preprocessing_pipeline.ipynb](preprocessing_pipeline.ipynb) and run cells in order.

Stages:
1. Imports and config
2. Load helpers
3. Schema mapping and harmonization helpers
4. Primary preprocessing run (load, harmonize, aggregate, union, dedup)
5. Sensitivity analysis
6. Target integrity checks
7. Save outputs

## Configuration

Edit the config cell in [preprocessing_pipeline.ipynb](preprocessing_pipeline.ipynb):
- `hatexplain_path`
- `mhs_local_path`
- `mhs_hf_uri`
- `refresh_mhs_local_copy`
- `include_elsherief`
- `elsherief_path`
- `mhs_primary_threshold`
- `sensitivity_thresholds`

## Output Files

Primary files written to [outputs/preprocessing](outputs/preprocessing):
- `hatexplain_standardized.tsv`
- `mhs_standardized.tsv`
- `union_primary.tsv`
- `dedup_primary.tsv`
- `sensitivity_summary.tsv`

## Rerunning with ElSherief

When ElSherief data is available:
1. Place the file locally (default path: [data/implicit-hate-corpus/implicit_hate_v1_stg3_posts.tsv](data/implicit-hate-corpus/implicit_hate_v1_stg3_posts.tsv)).
2. Set `include_elsherief = True`.
3. Update `elsherief_path` if needed.
4. Re-run from the primary run cell onward.

## Notes

- MHS fetch is one-time unless `refresh_mhs_local_copy=True`.
- Dedup prioritizes `post_id` and falls back to `text_dedup_key`.
- Sensitivity analysis is controlled by `sensitivity_thresholds`.