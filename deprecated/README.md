# Deprecated

Code that is no longer part of the live pipeline, kept here for
reference/rollback rather than deleted outright. Nothing in this directory
is imported or invoked by any current entry point
(`scripts/run_audit_pipeline.sh`, `scripts/run_data_preprocessing.sh`,
`audit_pipeline/run_all.py`, `audit_pipeline/notebooks/figures_consolidated.ipynb`),
and none of it is the current source of any number, table, or figure cited
in the paper — two entries below (`generate_figures_final.py`,
`generate_fig2_annotation_di_pairwise.py`) *were* that source historically;
see their row for why they no longer are.

| Path | Original location | Why it's here |
|---|---|---|
| `auditing/` | `auditing/` | Exploratory notebook pipeline (coverage → annotation quality → disparity → visualizations) that duplicates `audit_pipeline/`'s stage1-3+figures logic but without coding-level stratification. Superseded by `audit_pipeline/`; not used for any reported number. |
| `rq_reporting.py` | `audit_pipeline/rq_reporting.py` | Computed RQ metrics directly from stage-06 preprocessed outputs, duplicating stage1-4's work without coding-level stratification. Superseded by `stage1_coverage.py`-`stage4_rollup.py` plus `robustness_check.py` (which absorbed the one thing it uniquely computed: pooling across levels). Nothing reads its outputs. |
| `stage5_figures.py` | `audit_pipeline/stage5_figures.py` | Generated PNG figures (`outputs/stage5/**`) that are not cited anywhere in the paper. Figure generation for the paper is handled by `audit_pipeline/notebooks/figures_consolidated.ipynb` (see root README). |
| `figures_final.ipynb` | `figures_final.ipynb` | Orphaned notebook duplicate of `generate_figures_final.py`'s pre-refactor content; nothing imports or references it. |
| `generate_figures_final.py` | `generate_figures_final.py` | Produced 13 of the paper's 14 embedded figures until 2026-07-03, when an extended author-review styling pass (13 rounds, documented at the end of `figures_consolidated.ipynb`) diverged its logic from the notebook's copy without ever being ported back. Archived after confirming, by rendering `WOAH26_BDW.pdf` and pixel-comparing every embedded figure against a fresh run of `figures_consolidated.ipynb`, that the notebook — not this file — is what actually matches the submitted paper. |
| `generate_fig2_annotation_di_pairwise.py` | `generate_fig2_annotation_di_pairwise.py` | Produced the paper's Figure 2 until the same 2026-07-03 styling pass diverged it from `figures_consolidated.ipynb`'s copy. Its output (`fig2_annotation_di_by_pair_level.pdf`) had a stray gray annotation box and wrong aspect ratio relative to the submitted paper — confirmed by direct pixel comparison. Archived for the same reason as `generate_figures_final.py`, which it imports styling helpers from. |
| `test_stage5_figures.py` | `tests/audit_pipeline/test_stage5_figures.py` | Tests for `stage5_figures.py`. Outside `tests/` (pytest's `testpaths`), so it is no longer collected. |

Imports inside these files use absolute paths (`from audit_pipeline.config
import ...`), so they still resolve correctly from this location if you need
to run one directly for a rollback/diff check — but they are not maintained
and may drift from the current pipeline's schema over time.
