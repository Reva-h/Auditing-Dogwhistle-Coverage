"""Run the full audit pipeline in sequence.

Execution order:

  stage1_coverage   – dogwhistle presence and type-coverage metrics
  stage2_annotation – case A/B annotation quality metrics
  stage3_disparity  – pairwise disparate-impact ratios
  stage4_rollup     – group-level rollup tables
  stage5_figures    – publication figures from rolled-up data
  rq_reporting      – RQ1/RQ2/RQ3 outputs (figures, tables, appendix deltas)

Each module can also be run independently, e.g.::

    python -m audit_pipeline.stage1_coverage
    python -m audit_pipeline.rq_reporting
"""

import subprocess
import sys

stages = [
    "audit_pipeline.stage1_coverage",
    "audit_pipeline.stage2_annotation",
    "audit_pipeline.stage3_disparity",
    "audit_pipeline.stage4_rollup",
    "audit_pipeline.stage5_figures",
    "audit_pipeline.rq_reporting",
]

for stage in stages:
    print(f"\n{'=' * 60}\nRunning {stage}\n{'=' * 60}")
    subprocess.run([sys.executable, "-m", stage], check=True)
