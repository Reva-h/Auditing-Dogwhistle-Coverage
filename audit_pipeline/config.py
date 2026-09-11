"""Central configuration for the staged audit pipeline.

This module keeps file-system paths and shared numeric thresholds in one
location so every stage reads and writes from the same contract.

Two pipeline variants are defined:
  VARIANT_FULL   – primary analysis using all glossary tiers (1, 2, 3).
  VARIANT_TIER12 – robustness check restricted to tier-1 and tier-2 terms
                   only (explicit slurs/labels and stereotype-based terms).

Pass a PipelineVariant to each stage's run() to control which glossary terms
are active and where outputs land.  When no variant is supplied the stage
defaults to VARIANT_FULL, preserving existing behaviour.
"""

from pathlib import Path
from typing import FrozenSet, NamedTuple, Optional

# ---------------------------------------------------------------------------
# Upstream inputs (produced by pre-audit preprocessing)
# ---------------------------------------------------------------------------

WORKDIR = Path(__file__).resolve().parent.parent
DATA_PATH = WORKDIR / "outputs/unioned_data/06_cleaned_labels_glossary_mapped.tsv"
GLOSSARY_PATH = WORKDIR / "outputs/unioned_data/06_glossary_label_reference.tsv"

# ElSherief-inclusive counterpart of DATA_PATH, built by
# audit_pipeline.build_elsherief_comparison_data (which re-runs the 04-06
# preprocessing notebooks in memory with include_elsherief=True, writing to
# these paths rather than the primary, ElSherief-excluded ones above). Used
# only by stage4_rollup.py's Section 5.4 / Appendix G "union vs. Implicit
# Hate alone" comparison -- never by the primary analysis.
DATA_PATH_WITH_ELSHERIEF = (
    WORKDIR
    / "outputs/unioned_data/06_cleaned_labels_glossary_mapped_with_elsherief.tsv"
)
OUT_S1_WITH_ELSHERIEF = WORKDIR / "outputs/stage1_with_elsherief"

# ---------------------------------------------------------------------------
# Primary output roots  (shared by VARIANT_FULL and used as defaults)
# ---------------------------------------------------------------------------

OUT_S1 = WORKDIR / "outputs/stage1"
OUT_S2 = WORKDIR / "outputs/stage2"
OUT_S3 = WORKDIR / "outputs/stage3"
OUT_S4 = WORKDIR / "outputs/stage4"
OUT_S5 = WORKDIR / "outputs/stage5"

# ---------------------------------------------------------------------------
# Audit parameters
# ---------------------------------------------------------------------------

N_MIN = 30
DI_THRESHOLD = 0.8

# ElSherief dataset name as stored in the dataset column
ELSHERIEF_DATASET_NAME = "elsherief"


# ---------------------------------------------------------------------------
# Pipeline variants
# ---------------------------------------------------------------------------

class PipelineVariant(NamedTuple):
    """Bundle of all configuration that varies between the primary analysis
    and the tier-1+2 robustness check.

    Attributes
    ----------
    name : str
        Short identifier used in log output (e.g. ``"full"`` or ``"tier12"``).
    allowed_tiers : frozenset[int] or None
        Glossary tiers to include when building the surface-form matching regex
        and when computing glossary-denominator counts.  ``None`` means all
        tiers (including rows with non-numeric tier values).

        Filtering is applied at glossary-load time in Stage 1 and Stage 4 so
        that only allowed-tier surface forms enter the regex and only allowed-
        tier entries count toward the ``total_glossary_dogwhistles`` denominator.
        Filtering after matching would leave tier-3 tokens in the regex and
        produce artificially inflated match counts for the restricted variants.
    out_s1 … out_s4 : Path
        Stage output directories.
    out_s5 : Path
        Output directory for stage5-shaped figure writers (``audit_pipeline/
        figures_consolidated.ipynb`` sandboxes this via
        ``variant._replace(out_s5=...)``; ``stage5_figures.py`` itself has
        been superseded and removed from this repository).
    """

    name: str
    allowed_tiers: Optional[FrozenSet[int]]
    out_s1: Path
    out_s2: Path
    out_s3: Path
    out_s4: Path
    out_s5: Path


# Primary analysis: all glossary tiers, standard output paths.
VARIANT_FULL = PipelineVariant(
    name="full",
    allowed_tiers=None,
    out_s1=OUT_S1,
    out_s2=OUT_S2,
    out_s3=OUT_S3,
    out_s4=OUT_S4,
    out_s5=OUT_S5,
)

# Robustness check: tier-1 (explicit slurs / direct labels) and tier-2
# (stereotype-based terms) only.  Tier-3 terms (concepts, policy language,
# persona signals) require substantial in-group cultural knowledge and may
# not appear in all benchmark corpora; excluding them tests whether the
# primary findings hold on the more overtly decodable subset.
VARIANT_TIER12 = PipelineVariant(
    name="tier12",
    allowed_tiers=frozenset({1, 2}),
    out_s1=WORKDIR / "outputs/stage1_tier12",
    out_s2=WORKDIR / "outputs/stage2_tier12",
    out_s3=WORKDIR / "outputs/stage3_tier12",
    out_s4=WORKDIR / "outputs/stage4_tier12",
    out_s5=WORKDIR / "outputs/stage5_tier12",
)

# Ordered tuple of all variants; run_all.py and the shell script iterate over
# this to produce both the primary and robustness-check outputs in one run.
ALL_VARIANTS: tuple[PipelineVariant, ...] = (VARIANT_FULL, VARIANT_TIER12)

_VARIANT_BY_NAME: dict[str, PipelineVariant] = {v.name: v for v in ALL_VARIANTS}


def resolve_variant(argv: Optional[list] = None) -> PipelineVariant:
    """Return the PipelineVariant selected by ``--variant <name>`` in *argv*.

    Falls back to ``VARIANT_FULL`` when no ``--variant`` flag is present.
    Exits with an informative message on an unrecognised variant name.

    Parameters
    ----------
    argv : list[str] or None
        Argument list to parse.  Defaults to ``sys.argv[1:]`` when ``None``.
    """
    import sys

    args = sys.argv[1:] if argv is None else argv
    if "--variant" not in args:
        return VARIANT_FULL
    idx = args.index("--variant")
    if idx + 1 >= len(args):
        sys.exit("Error: --variant requires a name argument.")
    name = args[idx + 1]
    if name not in _VARIANT_BY_NAME:
        valid = ", ".join(_VARIANT_BY_NAME)
        sys.exit(f"Error: unknown variant '{name}'. Valid choices: {valid}")
    return _VARIANT_BY_NAME[name]
