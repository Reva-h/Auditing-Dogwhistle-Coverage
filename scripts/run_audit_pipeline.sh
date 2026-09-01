#!/usr/bin/env bash
set -euo pipefail

# Run the audit pipeline stages end-to-end in a deterministic order.
#
# By default two passes are executed, followed by a comparison step:
#   1. Primary analysis  – all glossary tiers (outputs/stage1/ … outputs/stage5/)
#   2. Robustness check  – tier-1 and tier-2 terms only
#                          (outputs/stage1_tier12/ … outputs/stage5_tier12/)
#   3. robustness_check  – compares (1) and (2) once both have run;
#                          writes outputs/robustness_check/
#
# Use --no-robustness to skip pass 2 (and therefore step 3) and run only the
# primary analysis. Use --variant <name> to run a single variant instead of
# both (step 3 is skipped in that case too, since it has nothing to compare).
#
# What this script does:
# 1. Runs audit_pipeline stages 1-5 as Python modules, once per active variant.
# 2. Each stage reads from the previous stage's outputs under outputs/.
# 3. If (and only if) both the full and tier12 variants ran in this
#    invocation, runs audit_pipeline.robustness_check once afterward,
#    comparing their Stage 4 outputs -- it is not a per-variant stage, so it
#    is not part of the per-variant loop below.
# 4. Artifact layout per variant:
#    full    → outputs/stage1/  … outputs/stage5/
#    tier12  → outputs/stage1_tier12/ … outputs/stage5_tier12/
#    (both)  → outputs/robustness_check/
#
# rq_reporting is deprecated (see audit_pipeline/rq_reporting.py) and is no
# longer part of this script's default execution order.
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
#   --from <stage>     Start stage (inclusive). One of: stage1 stage2 stage3 stage4 stage5 robustness_check
#   --to   <stage>     End stage (inclusive).   One of: stage1 stage2 stage3 stage4 stage5 robustness_check
#   --no-robustness    Run only the primary (full-tier) analysis; skip tier-1+2 pass
#   --variant <name>   Run a single variant only (full | tier12)
#   --help             Show help text

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

FROM_STAGE="stage1"
TO_STAGE="robustness_check"
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
      sed -n '1,51p' "$0"
      exit 0
      ;;
    *)
      echo "Error: Unknown option '$1'" >&2
      exit 2
      ;;
  esac
done

# Ordered list of stage identifiers. "robustness_check" is included here only
# so it can be named in --from/--to ranges -- it is NOT a per-variant stage
# (it compares two variants' outputs) and is deliberately excluded from the
# per-variant loop in run_variant() below; see the main loop at the bottom of
# this file for where it actually runs.
STAGE_IDS=(
  "stage1"
  "stage2"
  "stage3"
  "stage4"
  "stage5"
  "robustness_check"
)

# Map stage id -> audit_pipeline module name.
stage_to_module() {
  local stage="$1"
  case "$stage" in
    stage1)             echo "audit_pipeline.stage1_coverage" ;;
    stage2)             echo "audit_pipeline.stage2_annotation" ;;
    stage3)             echo "audit_pipeline.stage3_disparity" ;;
    stage4)             echo "audit_pipeline.stage4_rollup" ;;
    stage5)             echo "audit_pipeline.stage5_figures" ;;
    robustness_check)   echo "audit_pipeline.robustness_check" ;;
    *)                  return 1 ;;
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
    # robustness_check compares two variants' outputs -- it is not a
    # per-variant stage, so it is never run inside this loop. See the main
    # loop below for where it actually runs (once, after both variants).
    if [[ "$stage" == "robustness_check" ]]; then
      continue
    fi

    local module
    module="$(stage_to_module "$stage")"

    # stage5_figures.py is deprecated in favour of
    # audit_pipeline/notebooks/figures_consolidated.ipynb and refuses to run
    # via its __main__ entry point (which is exactly how this script invokes
    # it) without an explicit opt-in. This script is a legitimate,
    # intentional orchestrator -- not an accidental direct run -- so it
    # always passes the opt-in flag for this one stage.
    local module_args="$variant_args"
    if [[ "$stage" == "stage5" ]]; then
      module_args="$module_args --i-know-this-is-deprecated"
    fi

    echo ""
    echo "[RUN] $module  (variant: $variant)"
    # shellcheck disable=SC2086
    python3 -m "$module" $module_args
    echo "[OK ] $module"
  done
}

# ── Main loop ────────────────────────────────────────────────────────────────

echo ""
echo "Starting audit pipeline run..."

for variant in "${VARIANTS[@]}"; do
  run_variant "$variant"
done

# robustness_check runs once, after the per-variant loop, only when both
# variants actually ran in this invocation (--variant/--no-robustness both
# restrict to a single variant, which leaves nothing to compare) and only
# when the requested stage range reaches it.
ROBUSTNESS_CHECK_INDEX="$(stage_to_index "robustness_check")"
BOTH_VARIANTS_RAN=0
if [[ " ${VARIANTS[*]} " == *" full "* && " ${VARIANTS[*]} " == *" tier12 "* ]]; then
  BOTH_VARIANTS_RAN=1
fi

if (( TO_INDEX >= ROBUSTNESS_CHECK_INDEX )); then
  if (( BOTH_VARIANTS_RAN )); then
    echo ""
    echo "[RUN] audit_pipeline.robustness_check"
    python3 -m audit_pipeline.robustness_check
    echo "[OK ] audit_pipeline.robustness_check"
  else
    echo ""
    echo "[SKIP] audit_pipeline.robustness_check requires both variants; only ${VARIANTS[*]} ran in this invocation."
  fi
fi

echo ""
echo "Audit pipeline completed successfully."
echo ""
echo "Primary outputs:      $ROOT_DIR/outputs/{stage1..stage5}/"
if [[ " ${VARIANTS[*]} " == *" tier12 "* ]]; then
  echo "Robustness outputs:   $ROOT_DIR/outputs/{stage1_tier12..stage5_tier12}/"
fi
if (( BOTH_VARIANTS_RAN && TO_INDEX >= ROBUSTNESS_CHECK_INDEX )); then
  echo "Comparison output:    $ROOT_DIR/outputs/robustness_check/"
fi
