"""Build the ElSherief-inclusive corpus needed for the Section 5.4 /
Appendix G "union vs. Implicit Hate alone" comparison.

The primary analysis (``outputs/unioned_data/06_cleaned_labels_glossary_mapped.tsv``,
config.DATA_PATH) correctly excludes ElSherief entirely -- see
``data_preprocessing/04_union_and_dedup.ipynb``'s ``UnionConfig.include_elsherief``,
which defaults to ``False`` per the paper's Methods (Section 3.2: the primary
audit is HateXplain+MHS only). But Section 5.4 needs ElSherief's own matches
to compare against, and Stage 1 surface-form matching only ever searches
whatever corpus it's given -- since ElSherief posts never enter the primary
corpus, there is nothing for ``stage4_rollup.py``'s
``compute_rollup(dataset_filter="elsherief", ...)`` to filter for. Every row
of ``s4c_*_delta_union_vs_elsherief.tsv`` in every variant currently comes
out all-NaN on the ElSherief side as a result.

This module produces a second, parallel corpus that *does* include
ElSherief, entirely independent of the primary one:

1. Runs ``04_union_and_dedup.ipynb``, ``05_target_label_analysis_and_filtering.ipynb``,
   and ``06_apply_annotations.ipynb`` **in memory** with ``include_elsherief=True``
   and alternate output paths (each notebook's ``cfg`` object overridden via
   one injected cell placed right after its existing config cell). The
   notebook *files* on disk are read but never written back to, and the
   primary (ElSherief-excluded) files they normally produce are never
   touched -- this is a fully separate output tree.
2. Runs Stage 1 surface-form matching (``stage1_coverage.run``) against the
   resulting corpus, writing to ``config.OUT_S1_WITH_ELSHERIEF``.

``stage4_rollup.py``'s ElSherief-delta computation reads from
``config.DATA_PATH_WITH_ELSHERIEF`` / ``config.OUT_S1_WITH_ELSHERIEF`` for
its one ElSherief-only ``compute_rollup`` call; every other call in the
pipeline is untouched by any of this.

Run once before regenerating Stage 4 (which then picks this up automatically):

    python -m audit_pipeline.build_elsherief_comparison_data
    python -m audit_pipeline.stage4_rollup
"""

from __future__ import annotations

from pathlib import Path

import nbformat
from nbclient import NotebookClient

from audit_pipeline.config import (
    DATA_PATH_WITH_ELSHERIEF,
    OUT_S1_WITH_ELSHERIEF,
    VARIANT_FULL,
    WORKDIR,
)

DATA_PREPROCESSING_DIR = WORKDIR / "data_preprocessing"
UNIONED_DIR = WORKDIR / "outputs" / "unioned_data"

# Alternate (ElSherief-inclusive) intermediate artifacts -- parallel to, and
# never overwriting, the primary pipeline's 04/05/06 outputs.
UNION_OUTPUT_WE = UNIONED_DIR / "04_union_primary_with_elsherief.tsv"
DEDUP_OUTPUT_WE = UNIONED_DIR / "04_dedup_primary_with_elsherief.tsv"
SUMMARY_OUTPUT_WE = UNIONED_DIR / "04_union_dedup_summary_with_elsherief.tsv"
FILTERED_UNION_OUTPUT_WE = UNIONED_DIR / "05_union_primary_filtered_with_elsherief.tsv"
FILTERED_DEDUP_OUTPUT_WE = UNIONED_DIR / "05_dedup_primary_filtered_with_elsherief.tsv"
CLEANED_OUTPUT_WE = UNIONED_DIR / "06_cleaned_labels_with_elsherief.tsv"
GLOSSARY_LABEL_REF_OUTPUT_WE = UNIONED_DIR / "06_glossary_label_reference_with_elsherief.tsv"

KERNEL_NAME = "python3"


def _run_notebook_with_injected_cell(
    notebook_path: Path, injected_source: str, after_cell_index: int
) -> None:
    """Execute *notebook_path* in memory with one extra code cell inserted
    after cell *after_cell_index*. Never writes back to *notebook_path* --
    the .ipynb file on disk, and whatever it normally produces, are
    untouched; only the paths reassigned in *injected_source* are written.
    """
    nb = nbformat.read(notebook_path, as_version=4)
    injected = nbformat.v4.new_code_cell(source=injected_source)
    nb.cells.insert(after_cell_index + 1, injected)
    client = NotebookClient(
        nb, timeout=1800, kernel_name=KERNEL_NAME, resources={"metadata": {"path": str(DATA_PREPROCESSING_DIR)}}
    )
    client.execute()


def build_union_and_dedup() -> None:
    """Re-run 04_union_and_dedup.ipynb's cfg with include_elsherief=True."""
    override = f"""
# --- injected by build_elsherief_comparison_data.py ---
cfg.include_elsherief = True
cfg.union_output = Path(r"{UNION_OUTPUT_WE}")
cfg.dedup_output = Path(r"{DEDUP_OUTPUT_WE}")
cfg.summary_output = Path(r"{SUMMARY_OUTPUT_WE}")
cfg.union_output.parent.mkdir(parents=True, exist_ok=True)
"""
    _run_notebook_with_injected_cell(
        DATA_PREPROCESSING_DIR / "04_union_and_dedup.ipynb", override, after_cell_index=1
    )


def build_target_filtering() -> None:
    """Re-run 05's cfg pointed at the ElSherief-inclusive 04 outputs."""
    override = f"""
# --- injected by build_elsherief_comparison_data.py ---
cfg.union_input = Path(r"{UNION_OUTPUT_WE}")
cfg.dedup_input = Path(r"{DEDUP_OUTPUT_WE}")
cfg.filtered_union_output = Path(r"{FILTERED_UNION_OUTPUT_WE}")
cfg.filtered_dedup_output = Path(r"{FILTERED_DEDUP_OUTPUT_WE}")
cfg.filtered_union_output.parent.mkdir(parents=True, exist_ok=True)
"""
    _run_notebook_with_injected_cell(
        DATA_PREPROCESSING_DIR / "05_target_label_analysis_and_filtering.ipynb",
        override,
        after_cell_index=1,
    )


def build_annotations() -> None:
    """Re-run 06's cfg pointed at the ElSherief-inclusive 05 output."""
    override = f"""
# --- injected by build_elsherief_comparison_data.py ---
cfg.input_path = Path(r"{FILTERED_UNION_OUTPUT_WE}")
cfg.output_path = Path(r"{CLEANED_OUTPUT_WE}")
cfg.mapped_output_path = Path(r"{DATA_PATH_WITH_ELSHERIEF}")
cfg.glossary_label_reference_output_path = Path(r"{GLOSSARY_LABEL_REF_OUTPUT_WE}")
cfg.output_path.parent.mkdir(parents=True, exist_ok=True)
"""
    _run_notebook_with_injected_cell(
        DATA_PREPROCESSING_DIR / "06_apply_annotations.ipynb", override, after_cell_index=1
    )


def build_stage1() -> None:
    """Run Stage 1 surface-form matching against the ElSherief-inclusive
    corpus, using the same tier scope (all tiers) as VARIANT_FULL. Only
    stage1_coverage.DATA_PATH is monkeypatched, and only for this one call
    -- it's restored immediately after, so nothing else observes the swap.
    """
    from audit_pipeline import stage1_coverage

    variant = VARIANT_FULL._replace(name="with_elsherief", out_s1=OUT_S1_WITH_ELSHERIEF)
    original_data_path = stage1_coverage.DATA_PATH
    stage1_coverage.DATA_PATH = DATA_PATH_WITH_ELSHERIEF
    try:
        stage1_coverage.run(variant)
    finally:
        stage1_coverage.DATA_PATH = original_data_path


def main() -> None:
    print("[1/4] Union + dedup, ElSherief included ...")
    build_union_and_dedup()
    print("[2/4] Target label analysis + filtering ...")
    build_target_filtering()
    print("[3/4] Annotation cleanup + glossary mapping ...")
    build_annotations()
    print("[4/4] Stage 1 matching against the ElSherief-inclusive corpus ...")
    build_stage1()
    print()
    print("Done. ElSherief-inclusive corpus:", DATA_PATH_WITH_ELSHERIEF)
    print("ElSherief-inclusive Stage 1 output:", OUT_S1_WITH_ELSHERIEF)
    print()
    print("Next: rerun `python -m audit_pipeline.stage4_rollup` to pick this up.")


if __name__ == "__main__":
    main()
