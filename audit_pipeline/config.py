"""Central configuration for the staged audit pipeline.

This module keeps file-system paths and shared numeric thresholds in one
location so every stage reads and writes from the same contract.
"""

from pathlib import Path

# Upstream inputs (produced by pre-audit preprocessing)
WORKDIR = Path(__file__).resolve().parent.parent
DATA_PATH = WORKDIR / "outputs/unioned_data/06_cleaned_labels_glossary_mapped.tsv"
GLOSSARY_PATH = WORKDIR / "outputs/unioned_data/06_glossary_label_reference.tsv"

# Output roots
OUT_S1 = WORKDIR / "outputs/stage1"
OUT_S2 = WORKDIR / "outputs/stage2"
OUT_S3 = WORKDIR / "outputs/stage3"
OUT_S4 = WORKDIR / "outputs/stage4"
OUT_S5 = WORKDIR / "outputs/stage5"

# Audit parameters
N_MIN = 30
DI_THRESHOLD = 0.8

# ElSherief dataset name as stored in the dataset column
ELSHERIEF_DATASET_NAME = "elsherief"
