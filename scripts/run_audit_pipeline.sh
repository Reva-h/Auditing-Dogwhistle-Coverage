#!/usr/bin/env bash
set -euo pipefail

# Run the audit pipeline stages end-to-end in a deterministic order.
#
# By default two passes are executed:
#   1. Primary analysis  – all glossary tiers (outputs/stage1/ … outputs/rq_reporting/)
#   2. Robustness check  – tier-1 and tier-2 terms only
#                          (outputs/stage1_tier12/ … outputs/rq_reporting_tier12/)
#
# Use --no-robustness to skip the second pass and run only the primary analysis.
# Use --variant <name> to run a single variant (full | tier12) instead of both.
#
# What this script does:
# 1. Runs audit_pipeline stages 1-5 then rq_reporting as Python modules,
#    once per active variant.
# 2. Each stage reads from the previous stage's outputs under outputs/.
# 3. Artifact layout per variant:
#    full    → outputs/stage1/  … outputs/stage5/  outputs/rq_reporting/
#    tier12  → outputs/stage1_tier12/ … outputs/stage5_tier12/ outputs/rq_reporting_tier12/
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
#   scripts/run_audit_pipeline.sh --no-robustness
#   scripts/run_audit_pipeline.sh --variant tier12
#   scripts/run_audit_pipeline.sh --from stage2
#   scripts/run_audit_pipeline.sh --from stage1 --to stage3
#
# Options:
#   --from <stage>     Start stage (inclusive). One of: stage1 stage2 stage3 stage4 stage5 rq_reporting
#   --to   <stage>     End stage (inclusive).   One of: stage1 stage2 stage3 stage4 stage5 rq_reporting
#   --no-robustness    Run only the primary (full-tier) analysis; skip tier-1+2 pass
#   --variant <name>   Run a single variant only (full | tier12)
#   --help             Show help text

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

FROM_STAGE="stage1"
TO_STAGE="rq_reporting"
NO_ROBUSTNESS=0
SINGLE_VARIANT=""

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
    --no-robustness)
      NO_ROBUSTNESS=1
      shift
      ;;
    --variant)
      if [[ $# -lt 2 ]]; then
        echo "Error: --variant requires a name (full | tier12)." >&2
        exit 2
      fi
      SINGLE_VARIANT="$2"
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

# Validate --variant when provided.
if [[ -n "$SINGLE_VARIANT" ]]; then
  if [[ "$SINGLE_VARIANT" != "full" && "$SINGLE_VARIANT" != "tier12" ]]; then
    echo "Error: --variant must be 'full' or 'tier12'." >&2
    exit 2
  fi
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

# Determine which variants to run.
# --variant overrides --no-robustness; both flags together are also fine
# (--variant tier12 --no-robustness is redundant but accepted).
if [[ -n "$SINGLE_VARIANT" ]]; then
  VARIANTS=("$SINGLE_VARIANT")
elif (( NO_ROBUSTNESS )); then
  VARIANTS=("full")
else
  VARIANTS=("full" "tier12")
fi

echo "Variants:         ${VARIANTS[*]}"

# ── Helper: run one pass for a single variant ─────────────────────────────────

run_variant() {
  local variant="$1"
  local variant_args=""
  if [[ "$variant" != "full" ]]; then
    # Pass --variant to each Python module so it writes to the correct dirs.
    variant_args="--variant $variant"
  fi

  echo ""
  echo "┌─────────────────────────────────────────────────────────"
  echo "│ Variant: $variant"
  echo "└─────────────────────────────────────────────────────────"

  for i in "${!STAGE_IDS[@]}"; do
    if (( i < FROM_INDEX || i > TO_INDEX )); then
      continue
    fi

    local stage="${STAGE_IDS[$i]}"
    local module
    module="$(stage_to_module "$stage")"

    echo ""
    echo "[RUN] $module  (variant: $variant)"
    # shellcheck disable=SC2086
    python3 -m "$module" $variant_args
    echo "[OK ] $module"
  done
}

# ── Main loop ────────────────────────────────────────────────────────────────

echo ""
echo "Starting audit pipeline run..."

for variant in "${VARIANTS[@]}"; do
  run_variant "$variant"
done

echo ""
echo "Audit pipeline completed successfully."
echo ""
echo "Primary outputs:      $ROOT_DIR/outputs/{stage1..stage5,rq_reporting}/"
if [[ " ${VARIANTS[*]} " == *" tier12 "* ]]; then
  echo "Robustness outputs:   $ROOT_DIR/outputs/{stage1_tier12..stage5_tier12,rq_reporting_tier12}/"
fi
