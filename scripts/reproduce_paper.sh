#!/usr/bin/env bash
set -euo pipefail

# Regenerate every number, table and figure in the paper from the source
# datasets, then rebuild the ID-only data release.
#
# Prerequisites: the virtual environment is active and the source datasets
# are in data/ (see the repository README, "Getting the source data").
#
# Usage, from the repository root:
#   scripts/reproduce_paper.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

run_notebook() {
  jupyter nbconvert --to notebook --execute --inplace "$1"
}

step() {
  echo
  echo "=== $1"
}

step "Preprocessing (notebooks 00-06)"
bash scripts/run_data_preprocessing.sh

step "Annotation merge and inter-annotator agreement (Table 4)"
run_notebook annotations/merge_annotation_union.ipynb
run_notebook annotations/inter_annotator_agreement.ipynb

step "Audit pipeline, primary analysis and tier-1+2 robustness check"
bash scripts/run_audit_pipeline.sh

step "Implicit Hate comparison (Section 5.4, Appendix G)"
python -m audit_pipeline.build_elsherief_comparison_data
python -m audit_pipeline.stage4_rollup

step "Robustness table (Table 3)"
python -m audit_pipeline.generate_robustness_table_for_paper

step "Figures 1-13"
run_notebook audit_pipeline/figures_consolidated.ipynb

step "FPR estimates (Table 2, Figures 14-16)"
run_notebook fpr_annotation/fpr_iaa_analysis.ipynb

step "Data release"
python -m audit_pipeline.build_release

echo
echo "Done. Figures: outputs/figures_final/ and fpr_annotation/outputs/"
