#!/usr/bin/env bash
set -euo pipefail

# Run the audit pipeline stages end-to-end in a deterministic order.
#
# What this script does:
# 1. Runs audit_pipeline stages 1-5 then rq_reporting as Python modules.
# 2. Each stage reads from the previous stage's outputs under outputs/.
# 3. Artifact layout:
#    - stage1 writes to outputs/stage1/
#    - stage2 writes to outputs/stage2/
#    - stage3 writes to outputs/stage3/
#    - stage4 writes to outputs/stage4/
#    - stage5 writes to outputs/stage5/
#    - rq_reporting writes to outputs/rq_reporting/
#
# Prerequisites:
#   The data-preprocessing pipeline must have run successfully first:
#     scripts/run_data_preprocessing.sh
#   Required inputs:
#     outputs/unioned_data/06_cleaned_labels_glossary_mapped.tsv
#     outputs/unioned_data/06_glossary_label_reference.tsv
#
# Usage:
#   scripts/run_audit_pipeline.sh
#   scripts/run_audit_pipeline.sh --from stage2
#   scripts/run_audit_pipeline.sh --from stage1 --to stage3
#
# Options:
#   --from <stage>  Start stage (inclusive). One of: stage1 stage2 stage3 stage4 stage5 rq_reporting
#   --to   <stage>  End stage (inclusive).   One of: stage1 stage2 stage3 stage4 stage5 rq_reporting
#   --help          Show help text

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

FROM_STAGE="stage1"
TO_STAGE="rq_reporting"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --from)
      if [[ $# -lt 2 ]]; then
        echo "Error: --from requires a stage name." >&2
        exit 2
      fi
      FROM_STAGE="$2"
      shift 2
      ;;
    --to)
      if [[ $# -lt 2 ]]; then
        echo "Error: --to requires a stage name." >&2
        exit 2
      fi
      TO_STAGE="$2"
      shift 2
      ;;
    --help|-h)
      sed -n '1,30p' "$0"
      exit 0
      ;;
    *)
      echo "Error: Unknown option '$1'" >&2
      exit 2
      ;;
  esac
done

# Ordered list of stage identifiers.
STAGE_IDS=(
  "stage1"
  "stage2"
  "stage3"
  "stage4"
  "stage5"
  "rq_reporting"
)

# Map stage id -> audit_pipeline module name.
stage_to_module() {
  local stage="$1"
  case "$stage" in
    stage1)        echo "audit_pipeline.stage1_coverage" ;;
    stage2)        echo "audit_pipeline.stage2_annotation" ;;
    stage3)        echo "audit_pipeline.stage3_disparity" ;;
    stage4)        echo "audit_pipeline.stage4_rollup" ;;
    stage5)        echo "audit_pipeline.stage5_figures" ;;
    rq_reporting)  echo "audit_pipeline.rq_reporting" ;;
    *)             return 1 ;;
  esac
}

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

VALID_STAGES="${STAGE_IDS[*]}"

if ! FROM_INDEX="$(stage_to_index "$FROM_STAGE")"; then
  echo "Error: --from must be one of: $VALID_STAGES" >&2
  exit 2
fi

if ! TO_INDEX="$(stage_to_index "$TO_STAGE")"; then
  echo "Error: --to must be one of: $VALID_STAGES" >&2
  exit 2
fi

if (( FROM_INDEX > TO_INDEX )); then
  echo "Error: --from stage must be less than or equal to --to stage." >&2
  exit 2
fi

# Fail fast with a clear message if the audit_pipeline package is not importable.
if ! python3 -c "import audit_pipeline" >/dev/null 2>&1; then
  cat >&2 <<EOF
Error: audit_pipeline package not importable.

Make sure you are running from the repository root with the correct
virtual environment activated:

  source .venv/bin/activate
  pip install -r requirements.txt

Then retry from the repository root:

  scripts/run_audit_pipeline.sh
EOF
  exit 1
fi

# Check that the required upstream inputs exist before starting.
REQUIRED_INPUTS=(
  "$ROOT_DIR/outputs/unioned_data/06_cleaned_labels_glossary_mapped.tsv"
  "$ROOT_DIR/outputs/unioned_data/06_glossary_label_reference.tsv"
)

for f in "${REQUIRED_INPUTS[@]}"; do
  if [[ ! -f "$f" ]]; then
    cat >&2 <<EOF
Error: required input not found:
  $f

Run the data-preprocessing pipeline first:
  scripts/run_data_preprocessing.sh
EOF
    exit 1
  fi
done

echo "Repository root:  $ROOT_DIR"
echo "Stage range:      ${FROM_STAGE} -> ${TO_STAGE}"
echo ""
echo "Starting audit pipeline run..."

for i in "${!STAGE_IDS[@]}"; do
  if (( i < FROM_INDEX || i > TO_INDEX )); then
    continue
  fi

  stage="${STAGE_IDS[$i]}"
  module="$(stage_to_module "$stage")"

  echo ""
  echo "[RUN] $module"
  python3 -m "$module"
  echo "[OK ] $module"
done

echo ""
echo "Audit pipeline completed successfully."
echo "Stage outputs are in: $ROOT_DIR/outputs/{stage1..stage5,rq_reporting}/"
