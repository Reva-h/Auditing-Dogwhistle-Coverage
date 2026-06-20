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
| `config.py` | Central path, threshold constants, and pipeline variant definitions |
| `helpers.py` | Pure helper functions shared across stages (parsing, mapping, I/O) |
| `stage1_coverage.py` | Dogwhistle presence and type-coverage metrics per group |
| `stage2_annotation.py` | Case A/B annotation quality metrics per group |
| `stage3_disparity.py` | Pairwise disparate-impact ratios within taxonomy levels |
| `stage4_rollup.py` | Group-level rollup tables from stage1–3 outputs |
| `stage5_figures.py` | Publication-ready figures from rolled-up data |
| `rq_reporting.py` | RQ1/RQ2/RQ3 outputs (figures, tables, ElSherief appendix deltas) |
| `run_all.py` | Orchestrator: runs stages 1–5 then rq_reporting for all active variants |

## Pipeline Variants

The pipeline runs in two *variants*:

| Variant | Tiers included | Output directories |
|---|---|---|
| `full` (primary) | All glossary tiers (1, 2, 3) | `outputs/stage1/` … `outputs/rq_reporting/` |
| `tier12` (robustness check) | Tiers 1 and 2 only | `outputs/stage1_tier12/` … `outputs/rq_reporting_tier12/` |

**Why tier filtering is done at the glossary level (Stage 1 and Stage 4), not
post-match:** the glossary drives both (a) which surface-form tokens appear in
the regex and (b) the `total_glossary_dogwhistles` denominator for
`presence_rate`.  Filtering after matching would leave tier-3 tokens in the
regex and inflate match counts for the restricted variant, while also producing
a misleadingly low `presence_rate` because the denominator would still include
tier-3 entries.

The tier distribution in the current glossary is:

| Tier | Terms | Description |
|---|---|---|
| 1 | ~140 | Explicit slurs and direct labels (least cultural decoding required) |
| 2 | ~96 | Stereotype-based terms (cultural knowledge required) |
| 3 | ~239 | Concepts, policy language, persona signals (in-group knowledge required) |

## Stage Outputs

Each stage writes its artifacts to a dedicated subdirectory of `outputs/`.
The `full` variant uses the primary paths; the `tier12` variant appends `_tier12`.

| Stage | Full output directory | Tier-12 output directory |
|---|---|---|
| stage1 | `outputs/stage1/` | `outputs/stage1_tier12/` |
| stage2 | `outputs/stage2/` | `outputs/stage2_tier12/` |
| stage3 | `outputs/stage3/` | `outputs/stage3_tier12/` |
| stage4 | `outputs/stage4/` | `outputs/stage4_tier12/` |
| stage5 | `outputs/stage5/` | `outputs/stage5_tier12/` |
| rq_reporting | `outputs/rq_reporting/` | `outputs/rq_reporting_tier12/` |

## Running the Pipeline

Run both variants (primary + robustness check) from the repository root:

```bash
python -m audit_pipeline.run_all
```

Run a single variant:

```bash
python -m audit_pipeline.run_all --variant full
python -m audit_pipeline.run_all --variant tier12
```

Run a single stage independently (defaults to `full` variant):

```bash
python -m audit_pipeline.stage1_coverage
python -m audit_pipeline.rq_reporting
```

Run a single stage for the tier-1+2 robustness check:

```bash
python -m audit_pipeline.stage1_coverage --variant tier12
python -m audit_pipeline.rq_reporting --variant tier12
```

## Key Constants (`config.py`)

| Constant | Default | Meaning |
|---|---|---|
| `N_MIN` | 30 | Minimum matched-post count for stable per-group estimates |
| `DI_THRESHOLD` | 0.8 | Disparate-impact ratio threshold (80% rule) |
| `VARIANT_FULL` | — | Primary variant (all tiers, standard output paths) |
| `VARIANT_TIER12` | — | Robustness variant (tiers 1+2 only, `*_tier12` output paths) |
| `ALL_VARIANTS` | `(VARIANT_FULL, VARIANT_TIER12)` | Ordered tuple iterated by `run_all.py` |

## PipelineVariant

`PipelineVariant` is a `NamedTuple` defined in `config.py` that bundles:

- `name` — short identifier (`"full"` or `"tier12"`)
- `allowed_tiers` — `frozenset[int] | None` (None = all tiers)
- `out_s1` … `out_s5`, `rq_out` — output path for each stage

Pass a `PipelineVariant` to any stage's `run()` function to control which
tiers are active and where outputs land.  The `resolve_variant()` helper parses
a `--variant <name>` flag from `sys.argv` for use in `__main__` blocks.

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
