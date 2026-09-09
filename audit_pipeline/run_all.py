"""Run the full audit pipeline for all variants in sequence.

By default this runs two passes: the primary analysis (all tiers) followed by
the tier-1+2 robustness check.  Pass ``--variant <name>`` to run a single
variant instead.

Execution order per variant:

  stage1_coverage   – dogwhistle presence and type-coverage metrics
  stage2_annotation – case A/B annotation quality metrics
  stage3_disparity  – pairwise disparate-impact ratios
  stage4_rollup     – group-level rollup tables

When both variants are run in the same invocation (the default, no-flag
case), ``robustness_check`` runs once afterward -- comparing the two
variants' Stage 4 outputs -- since it is inherently a full-vs-tier12
comparison, not a per-variant stage. It does not run under ``--variant``
(only one variant exists to compare against in that case).

Each module can also be run independently, e.g.::

    python -m audit_pipeline.stage1_coverage
    python -m audit_pipeline.stage1_coverage --variant tier12
    python -m audit_pipeline.robustness_check
"""

from __future__ import annotations

import sys

from audit_pipeline import (
    robustness_check,
    stage1_coverage,
    stage2_annotation,
    stage3_disparity,
    stage4_rollup,
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


def _parse_args(argv: list[str] | None = None) -> list[PipelineVariant]:
    """Return the list of variants to run based on *argv* (defaults to sys.argv)."""
    args = sys.argv[1:] if argv is None else argv
    if "--variant" in args:
        idx = args.index("--variant")
        if idx + 1 >= len(args):
            sys.exit("Error: --variant requires a name argument.")
        name = args[idx + 1]
        if name not in _VARIANT_BY_NAME:
            valid = ", ".join(_VARIANT_BY_NAME)
            sys.exit(f"Error: unknown variant '{name}'. Valid choices: {valid}")
        return [_VARIANT_BY_NAME[name]]
    # Default: run all variants (primary then robustness check)
    return list(ALL_VARIANTS)


def main(argv: list[str] | None = None) -> None:
    """Run the requested variant(s), then the robustness check if both ran."""
    variants = _parse_args(argv)
    for v in variants:
        run_variant(v)
    if variants == list(ALL_VARIANTS):
        print(f"\n{'=' * 60}")
        print("Robustness check: comparing full vs. tier12")
        print(f"{'=' * 60}")
        robustness_check.main()


if __name__ == "__main__":
    main()
