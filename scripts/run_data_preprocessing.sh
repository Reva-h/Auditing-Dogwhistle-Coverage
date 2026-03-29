#!/usr/bin/env bash
set -euo pipefail

# Run the data preprocessing notebooks end-to-end in a deterministic order.
#
# What this script does:
# 1. Executes notebooks in data_preprocessing/ from 01 -> 05.
# 2. Uses the repository root as notebook execution working directory.
# 3. Preserves the current artifact layout:
#    - Notebooks 01-03 write standardized files to outputs/preprocessing/
#    - Notebooks 04-05 write union/filter artifacts to outputs/unioned_data/
#
# Usage:
#   scripts/run_data_preprocessing.sh
#   scripts/run_data_preprocessing.sh --timeout 1800
#
# Options:
#   --timeout <seconds>  Per-cell timeout for notebook execution (default: 1200)
#   --help               Show help text

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
NOTEBOOK_DIR="$ROOT_DIR/data_preprocessing"
PREPROCESSING_DIR="$ROOT_DIR/outputs/preprocessing"
UNIONED_DATA_DIR="$ROOT_DIR/outputs/unioned_data"

TIMEOUT=1200

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
    --help|-h)
      sed -n '1,40p' "$0"
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
  "01_hatexplain_formatting.ipynb"
  "02_mhs_formatting.ipynb"
  "03_elsherief_formatting.ipynb"
  "04_union_and_dedup.ipynb"
  "05_target_label_analysis_and_filtering.ipynb"
)

mkdir -p "$PREPROCESSING_DIR" "$UNIONED_DATA_DIR"

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
echo "Notebooks 01-03 outputs: $PREPROCESSING_DIR"
echo "Notebooks 04-05 outputs: $UNIONED_DATA_DIR"
echo "Per-cell timeout: ${TIMEOUT}s"

echo ""
echo "Starting end-to-end preprocessing run..."

for nb_name in "${NOTEBOOKS[@]}"; do
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
echo "Standardized outputs are in: $PREPROCESSING_DIR"
echo "Union/filter outputs are in: $UNIONED_DATA_DIR"
