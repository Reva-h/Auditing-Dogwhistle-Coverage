# Audit Pipeline

Programmatic Python pipeline that computes all research-question metrics and
figures from the cleaned, annotated corpus produced by
`data_preprocessing/06_apply_annotations.ipynb`.

## Inputs

All stages read from the outputs of the data-preprocessing pipeline:

| File | Producer |
|---|---|
| `outputs/unioned_data/06_cleaned_labels_glossary_mapped.tsv` | `data_preprocessing/06_apply_annotations.ipynb` |
| `outputs/unioned_data/06_glossary_label_reference.tsv` | `data_preprocessing/06_apply_annotations.ipynb` |
| `outputs/glossary/glossary.tsv` | `data_preprocessing/00_glossary_formatter.ipynb` |

## Modules

| Module | Description |
|---|---|
| `config.py` | Central path and threshold constants shared by all stages |
| `helpers.py` | Pure helper functions shared across stages (parsing, mapping, I/O) |
| `stage1_coverage.py` | Dogwhistle presence and type-coverage metrics per group |
| `stage2_annotation.py` | Case A/B annotation quality metrics per group |
| `stage3_disparity.py` | Pairwise disparate-impact ratios within taxonomy levels |
| `stage4_rollup.py` | Group-level rollup tables from stage1–3 outputs |
| `stage5_figures.py` | Publication-ready figures from rolled-up data |
| `rq_reporting.py` | RQ1/RQ2/RQ3 outputs (figures, tables, ElSherief appendix deltas) |
| `run_all.py` | Orchestrator: runs stages 1–5 then rq_reporting in sequence |

## Stage Outputs

Each stage writes its artifacts to a dedicated subdirectory of `outputs/`:

| Stage | Output directory |
|---|---|
| stage1 | `outputs/stage1/` |
| stage2 | `outputs/stage2/` |
| stage3 | `outputs/stage3/` |
| stage4 | `outputs/stage4/` |
| stage5 | `outputs/stage5/` |
| rq_reporting | `outputs/rq_reporting/` |

## Running the Pipeline

Run the full pipeline from the repository root:

```bash
python -m audit_pipeline.run_all
```

Run a single stage independently:

```bash
python -m audit_pipeline.stage1_coverage
python -m audit_pipeline.rq_reporting
```

## Key Constants (`config.py`)

| Constant | Default | Meaning |
|---|---|---|
| `N_MIN` | 30 | Minimum matched-post count for stable per-group estimates |
| `DI_THRESHOLD` | 0.8 | Disparate-impact ratio threshold (80% rule) |

## Helper Functions (`helpers.py`)

Shared utilities used across stages. Highlights:

- `norm_target(value)` — normalise taxonomy target strings for grouping
- `map_reporting_group(level, target) -> ReportGroup` — map raw taxonomy labels to reporting groups
- `add_reporting_columns(df, level_col, target_col)` — add `report_level`, `report_target`, `report_include` to a DataFrame
- `safe_float(value)` / `safe_di_ratio(a, b)` / `safe_di(...)` — numeric helpers with sparse-data guards
- `parse_list_like(value)` / `parse_labels(value)` — parse list-valued notebook output columns
- `build_pairwise_rows(df, ...)` — assemble pairwise comparison rows for disparity tables
- `write_tsv(df, path)` / `ensure_dirs(*paths)` — I/O utilities

## Note on `rq_reporting.py`

`rq_reporting.py` computes RQ metrics directly from the stage-06 preprocessed
outputs (not from stage1–5 intermediate files). It imports shared helpers from
`audit_pipeline.helpers` but retains local copies of four helpers whose
signatures differ from the canonical versions; see the module docstring for
details. These are candidates for future consolidation.
