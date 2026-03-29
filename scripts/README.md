# Scripts

## run_data_preprocessing.sh

Run the preprocessing notebooks in [data_preprocessing](../data_preprocessing) end-to-end.

Execution order:
1. 00_glossary_formatter.ipynb
2. 01_hatexplain_formatting.ipynb
3. 02_mhs_formatting.ipynb
4. 03_elsherief_formatting.ipynb
5. 04_union_and_dedup.ipynb
6. 05_target_label_analysis_and_filtering.ipynb

### Why this script exists

- Automates the full preprocessing flow so it can be rerun consistently.
- Stops immediately on the first notebook failure.
- Keeps preprocessing outputs split by stage:
- Notebook 00 writes glossary files to [outputs/glossary](../outputs/glossary).
- Notebooks 01-03 write standardized files to [outputs/preprocessing](../outputs/preprocessing).
- Notebooks 04-05 write union/filter files to [outputs/unioned_data](../outputs/unioned_data).

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
scripts/run_data_preprocessing.sh --from 01 --to 04
```

Stage values accepted by `--from`/`--to`: `00`, `01`, `02`, `03`, `04`, `05`.
