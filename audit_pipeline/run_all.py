"""Run the full audit pipeline for all variants in sequence.

By default this runs two passes: the primary analysis (all tiers) followed by
the tier-1+2 robustness check.  Pass ``--variant <name>`` to run a single
variant instead.

Execution order per variant:

  stage1_coverage   – dogwhistle presence and type-coverage metrics
  stage2_annotation – case A/B annotation quality metrics
  stage3_disparity  – pairwise disparate-impact ratios
  stage4_rollup     – group-level rollup tables
  stage5_figures    – publication figures from rolled-up data
  rq_reporting      – RQ1/RQ2/RQ3 outputs (figures, tables, appendix deltas)

Each module can also be run independently, e.g.::

    python -m audit_pipeline.stage1_coverage
    python -m audit_pipeline.stage1_coverage --variant tier12
    python -m audit_pipeline.rq_reporting --variant tier12
"""

from __future__ import annotations

import sys

from audit_pipeline import (
    rq_reporting,
    stage1_coverage,
    stage2_annotation,
    stage3_disparity,
    stage4_rollup,
    stage5_figures,
)
from audit_pipeline.config import ALL_VARIANTS, PipelineVariant, _VARIANT_BY_NAME


def run_variant(variant: PipelineVariant) -> None:
    """Run all pipeline stages for one variant in dependency order."""
    print(f"\n{'=' * 60}")
    print(f"Variant: {variant.name}  (tiers: {sorted(variant.allowed_tiers) if variant.allowed_tiers else 'all'})")
    print(f"{'=' * 60}")
    stage1_coverage.run(variant)
    stage2_annotation.run(variant)
    stage3_disparity.run(variant)
    stage4_rollup.run(variant)
    stage5_figures.run(variant)
    rq_reporting.main(base_dir=variant.rq_out, allowed_tiers=variant.allowed_tiers)


def _parse_args() -> list[PipelineVariant]:
    """Return the list of variants to run based on sys.argv."""
    if "--variant" in sys.argv:
        idx = sys.argv.index("--variant")
        if idx + 1 >= len(sys.argv):
            sys.exit("Error: --variant requires a name argument.")
        name = sys.argv[idx + 1]
        if name not in _VARIANT_BY_NAME:
            valid = ", ".join(_VARIANT_BY_NAME)
            sys.exit(f"Error: unknown variant '{name}'. Valid choices: {valid}")
        return [_VARIANT_BY_NAME[name]]
    # Default: run all variants (primary then robustness check)
    return list(ALL_VARIANTS)


if __name__ == "__main__":
    for v in _parse_args():
        run_variant(v)
