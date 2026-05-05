"""Run the full audit pipeline stages 1-5 in sequence.

The pipeline is deliberately orchestrated as separate Python modules so each
stage can also be rerun independently during debugging.
"""

import subprocess
import sys

stages = [
    "pipeline.stage1_coverage",
    "pipeline.stage2_annotation",
    "pipeline.stage3_disparity",
    "pipeline.stage4_rollup",
    "pipeline.stage5_figures",
]


# Each stage writes the artifacts consumed by the next stage.  Running them in
# this order reproduces all downstream tables and plots from raw staged inputs.
for stage in stages:
    print(f"\n{'=' * 60}\nRunning {stage}\n{'=' * 60}")
    subprocess.run([sys.executable, "-m", stage], check=True)
