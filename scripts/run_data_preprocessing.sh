#!/usr/bin/env bash
set -euo pipefail

# Run the data preprocessing notebooks end-to-end in a deterministic order.
#
# What this script does:
# 1. Executes notebooks in data_preprocessing/ from 00 -> 06.
# 2. Uses the repository root as notebook execution working directory.
# 3. Preserves the current artifact layout:
#    - Notebook 00 writes glossary files to outputs/glossary/
#    - Notebooks 01-03 write standardized files to outputs/preprocessing/
#    - Notebooks 04-06 write union/filter/annotation artifacts to outputs/unioned_data/
#
# Usage:
#   scripts/run_data_preprocessing.sh
#   scripts/run_data_preprocessing.sh --timeout 1800
#   scripts/run_data_preprocessing.sh --from 01
#   scripts/run_data_preprocessing.sh --from 01 --to 04
#
# Options:
#   --timeout <seconds>  Per-cell timeout for notebook execution (default: 1200)
#   --from <stage>       Start stage (00-06), inclusive (default: 00)
#   --to <stage>         End stage (00-06), inclusive (default: 06)
#   --help               Show help text

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
NOTEBOOK_DIR="$ROOT_DIR/data_preprocessing"
GLOSSARY_DIR="$ROOT_DIR/outputs/glossary"
PREPROCESSING_DIR="$ROOT_DIR/outputs/preprocessing"
UNIONED_DATA_DIR="$ROOT_DIR/outputs/unioned_data"

TIMEOUT=1200
FROM_STAGE="00"
TO_STAGE="06"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --timeout)
      if [[ $# -lt 2 ]]; then
        echo "Error: --timeout requires a numeric value in seconds." >&2
        exit 2
      fi
      TIMEOUT="$2"
      shift 2
      ;;
    --from)
      if [[ $# -lt 2 ]]; then
        echo "Error: --from requires a stage value (00-06)." >&2
        exit 2
      fi
      FROM_STAGE="$2"
      shift 2
      ;;
    --to)
      if [[ $# -lt 2 ]]; then
        echo "Error: --to requires a stage value (00-06)." >&2
        exit 2
      fi
      TO_STAGE="$2"
      shift 2
      ;;
    --help|-h)
      sed -n '1,50p' "$0"
      exit 0
      ;;
    *)
      echo "Error: Unknown option '$1'" >&2
      exit 2
      ;;
  esac
done

if ! [[ "$TIMEOUT" =~ ^[0-9]+$ ]]; then
  echo "Error: timeout must be a non-negative integer (seconds)." >&2
  exit 2
fi

# Fail fast with a clear message if required Python modules are missing.
if ! python3 - <<'PY' >/dev/null 2>&1
import nbformat  # noqa: F401
import nbclient  # noqa: F401
PY
then
  cat >&2 <<'EOF'
Missing Python dependencies: nbformat and/or nbclient.

Install dependencies in your active environment, then retry:
  pip install -r requirements.txt
  pip install nbclient nbformat
EOF
  exit 1
fi

NOTEBOOKS=(
  "00_glossary_formatter.ipynb"
  "01_hatexplain_formatting.ipynb"
  "02_mhs_formatting.ipynb"
  "03_elsherief_formatting.ipynb"
  "04_union_and_dedup.ipynb"
  "05_target_label_analysis_and_filtering.ipynb"
  "06_apply_annotations.ipynb"
)

STAGE_IDS=("00" "01" "02" "03" "04" "05" "06")

stage_to_index() {
  local stage="$1"
  local i
  for i in "${!STAGE_IDS[@]}"; do
    if [[ "${STAGE_IDS[$i]}" == "$stage" ]]; then
      echo "$i"
      return 0
    fi
  done
  return 1
}

if ! FROM_INDEX="$(stage_to_index "$FROM_STAGE")"; then
  echo "Error: --from must be one of 00, 01, 02, 03, 04, 05, 06." >&2
  exit 2
fi

if ! TO_INDEX="$(stage_to_index "$TO_STAGE")"; then
  echo "Error: --to must be one of 00, 01, 02, 03, 04, 05, 06." >&2
  exit 2
fi

if (( FROM_INDEX > TO_INDEX )); then
  echo "Error: --from stage must be less than or equal to --to stage." >&2
  exit 2
fi

mkdir -p "$GLOSSARY_DIR" "$PREPROCESSING_DIR" "$UNIONED_DATA_DIR"

run_notebook() {
  local in_path="$1"

  python3 - "$in_path" "$ROOT_DIR" "$TIMEOUT" <<'PY'
import sys
from pathlib import Path

import nbformat
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError

in_path = Path(sys.argv[1])
workdir = Path(sys.argv[2])
timeout = int(sys.argv[3])

with in_path.open("r", encoding="utf-8") as f:
    nb = nbformat.read(f, as_version=4)

client = NotebookClient(
    nb,
    timeout=timeout,
    kernel_name="python3",
    allow_errors=False,
    resources={"metadata": {"path": str(workdir)}},
)

try:
    client.execute()
except CellExecutionError as exc:
    print(f"Notebook execution failed: {in_path}", file=sys.stderr)
    print(str(exc), file=sys.stderr)
    sys.exit(1)

# Overwrite in place so execution metadata and outputs are preserved in-source.
with in_path.open("w", encoding="utf-8") as f:
    nbformat.write(nb, f)
PY
}

echo "Repository root: $ROOT_DIR"
echo "Notebook source directory: $NOTEBOOK_DIR"
echo "Output mode: in-place notebook execution"
echo "Notebook 00 outputs: $GLOSSARY_DIR"
echo "Notebooks 01-03 outputs: $PREPROCESSING_DIR"
echo "Notebooks 04-06 outputs: $UNIONED_DATA_DIR"
echo "Per-cell timeout: ${TIMEOUT}s"
echo "Stage range: ${FROM_STAGE} -> ${TO_STAGE}"

echo ""
echo "Starting end-to-end preprocessing run..."

for i in "${!NOTEBOOKS[@]}"; do
  if (( i < FROM_INDEX || i > TO_INDEX )); then
    continue
  fi

  nb_name="${NOTEBOOKS[$i]}"
  input_nb="$NOTEBOOK_DIR/$nb_name"

  if [[ ! -f "$input_nb" ]]; then
    echo "Error: notebook not found: $input_nb" >&2
    exit 1
  fi

  echo ""
  echo "[RUN] $nb_name"
  run_notebook "$input_nb"
  echo "[OK ] $nb_name"
done

echo ""
echo "All preprocessing notebooks completed successfully."
echo "Glossary outputs are in: $GLOSSARY_DIR"
echo "Standardized outputs are in: $PREPROCESSING_DIR"
echo "Union/filter/annotation outputs are in: $UNIONED_DATA_DIR"
