# Scripts

Shell entry points for running the two pipelines. Both scripts must be run
from the repository root with the virtual environment activated.

## run_audit_pipeline.sh

Run the [audit_pipeline](../audit_pipeline/README.md) stages end-to-end.

**Prerequisite:** `run_data_preprocessing.sh` must have completed successfully
(requires `outputs/unioned_data/06_cleaned_labels_glossary_mapped.tsv` and
`06_glossary_label_reference.tsv`).

By default the script runs **two passes**: the primary analysis (all glossary
tiers) followed by the tier-1+2 robustness check, then compares them.  Use
`--no-robustness` or `--variant` to restrict to a single pass (which also
skips the comparison, since it has nothing to compare against).

### Variants and output directories

| Variant | Tiers | Output directories |
|---|---|---|
| `full` (primary) | All (1, 2, 3) | `outputs/stage1/` … `outputs/stage5/` |
| `tier12` (robustness) | 1 and 2 only | `outputs/stage1_tier12/` … `outputs/stage5_tier12/` |
| — (comparison) | both, compared | `outputs/robustness_check/` |

### Execution order (per variant)

| Stage | Module | Full output | Tier-12 output |
|---|---|---|---|
| stage1 | `audit_pipeline.stage1_coverage` | `outputs/stage1/` | `outputs/stage1_tier12/` |
| stage2 | `audit_pipeline.stage2_annotation` | `outputs/stage2/` | `outputs/stage2_tier12/` |
| stage3 | `audit_pipeline.stage3_disparity` | `outputs/stage3/` | `outputs/stage3_tier12/` |
| stage4 | `audit_pipeline.stage4_rollup` | `outputs/stage4/` | `outputs/stage4_tier12/` |
| stage5 | `audit_pipeline.stage5_figures` | `outputs/stage5/` | `outputs/stage5_tier12/` |

`robustness_check` (`audit_pipeline.robustness_check`) is **not** part of
this per-variant table — it runs once, after both variants above have
completed, comparing their Stage 4 outputs. It writes a single output,
`outputs/robustness_check/`, not a per-variant pair of directories.

`audit_pipeline.rq_reporting` is deprecated (see that module's docstring)
and is no longer part of this script's execution order.

### Usage

```bash
# Full run — both primary analysis and tier-1+2 robustness check, then compare (default)
scripts/run_audit_pipeline.sh

# Primary analysis only (all tiers, skip the robustness check and comparison)
scripts/run_audit_pipeline.sh --no-robustness

# Robustness check only (tier 1+2) -- no comparison, since there's only one variant to compare
scripts/run_audit_pipeline.sh --variant tier12

# Start from a specific stage (applies to all active variants)
scripts/run_audit_pipeline.sh --from stage3

# Run a bounded range (inclusive) for the primary analysis only
scripts/run_audit_pipeline.sh --no-robustness --from stage1 --to stage3

# Re-run only the comparison step, assuming both variants' Stage 4 outputs
# already exist on disk
scripts/run_audit_pipeline.sh --from robustness_check --to robustness_check
```

Stage values accepted by `--from`/`--to`: `stage1`, `stage2`, `stage3`, `stage4`, `stage5`, `robustness_check`.

---

## run_data_preprocessing.sh

Run the preprocessing notebooks in [data_preprocessing](../data_preprocessing) end-to-end.

Execution order:
1. 00_glossary_formatter.ipynb
2. 01_hatexplain_formatting.ipynb
3. 02_mhs_formatting.ipynb
4. 03_elsherief_formatting.ipynb
5. 04_union_and_dedup.ipynb
6. 05_target_label_analysis_and_filtering.ipynb
7. 06_apply_annotations.ipynb

### Why this script exists

- Automates the full preprocessing flow so it can be rerun consistently.
- Stops immediately on the first notebook failure.
- Keeps preprocessing outputs split by stage:
- Notebook 00 writes glossary files to [outputs/glossary](../outputs/glossary).
- Notebooks 01-03 write standardized files to [outputs/preprocessing](../outputs/preprocessing).
- Notebooks 04-06 write union/filter/annotation files to [outputs/unioned_data](../outputs/unioned_data).

### Prerequisites

From the repository root:

```bash
source .venv/bin/activate
pip install -r requirements.txt
pip install nbclient nbformat
```

### Usage

From the repository root:

```bash
scripts/run_data_preprocessing.sh
```

Optional flags:

```bash
# Increase per-cell timeout to 30 minutes
scripts/run_data_preprocessing.sh --timeout 1800

# Run from stage 01 through the end
scripts/run_data_preprocessing.sh --from 01

# Run a bounded stage range (inclusive)
scripts/run_data_preprocessing.sh --from 01 --to 06
```

Stage values accepted by `--from`/`--to`: `00`, `01`, `02`, `03`, `04`, `05`, `06`.
