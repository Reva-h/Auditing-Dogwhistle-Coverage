"""Tier-1+2 robustness check: compares the primary (all-tier) analysis
against the tier-1+2-restricted analysis, per pair and per coding level,
plus a properly pooled-across-levels comparison.

Reads only the already-computed Stage 4 outputs for two ``PipelineVariant``s
(default: ``VARIANT_FULL`` vs. ``VARIANT_TIER12``) -- it does not re-run
Stage 1-4 and does not re-derive metrics from raw preprocessed data.

Covers both:

* fine-grained / raw-taxonomy-target pairs (``stage4/by_level_group``,
  "s4b" -- e.g. ``race:black`` vs. ``race:middle_eastern``)
* collapsed reporting-group pairs (``stage4/by_group``, "s4a" -- e.g.
  ``LGB`` vs. ``Trans/NB``)

On "pooled"
-----------
The paper's cited pooled DI figures (e.g. LGB vs. Trans/NB pooled coverage
DI = 0.482) are reproduced by summing each group's raw counts
(``distinct_dogwhistles_found`` / ``total_glossary_dogwhistles``,
``distinct_types_found`` / ``total_glossary_types``) across *all* coding
levels first, then computing *one* DI ratio from the pooled rates. This is
not the same computation as ``generate_figures_final.py``'s (deprecated)
``appD_worst_di_and_label_gap_pooled``, which takes ``min()`` of each
level's own DI ratio -- for LGB vs. Trans/NB that gives 0.417, not 0.482.
The two are different, non-interchangeable definitions of "pooled"; this
module implements the one that matches what the paper actually cites
(verified against the compiled paper this project).

Staleness note
---------------
This reads whatever full/tier12 Stage 4 outputs currently sit on disk. If
the two variants were produced by separate, out-of-sync runs, the
comparison will silently reflect stale data -- rerun both variants together
(``python -m audit_pipeline.run_all``), or rerun this module afterward, if
in doubt.

Can be run standalone once both variants have been produced::

    python -m audit_pipeline.robustness_check

or called programmatically -- invoked automatically by ``run_all.py`` when
both variants are run together in the same invocation.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from audit_pipeline.config import (
    DI_THRESHOLD,
    VARIANT_FULL,
    VARIANT_TIER12,
    PipelineVariant,
    WORKDIR,
)
from audit_pipeline.helpers import ensure_dirs, safe_di_ratio, safe_float, write_tsv

OUT_ROBUSTNESS = WORKDIR / "outputs" / "robustness_check"

# (granularity label, coverage-table path, pairwise-table path) -- both
# relative to variant.out_s4.
_GRANULARITIES = (
    (
        "fine",
        "by_level_group/s4b_coverage_by_level_group.tsv",
        "by_level_group/s4b_pairwise_disparity_by_level_group.tsv",
    ),
    (
        "collapsed",
        "by_group/s4a_coverage_by_group.tsv",
        "by_group/s4a_pairwise_disparity_by_group.tsv",
    ),
)


def _read(variant: PipelineVariant, relative_path: str) -> pd.DataFrame:
    return pd.read_csv(variant.out_s4 / relative_path, sep="\t", low_memory=False)


def compute_pooled_coverage_di(
    coverage_df: pd.DataFrame, target_a: str, target_b: str
) -> dict[str, float]:
    """Pool a pair's raw counts across all coding levels, then compute one
    coverage-DI ratio from the pooled rates.

    ``coverage_df`` must have ``report_target``, ``distinct_dogwhistles_found``,
    ``total_glossary_dogwhistles``, ``distinct_types_found``,
    ``total_glossary_types`` columns (the schema shared by
    ``s4a_coverage_by_group.tsv`` and ``s4b_coverage_by_level_group.tsv``).
    See the module docstring for why summing counts first, rather than
    taking min() of each level's own ratio, is the correct pooling method.
    """
    sub = coverage_df[coverage_df["report_target"].isin([target_a, target_b])]
    agg = sub.groupby("report_target").agg(
        found=("distinct_dogwhistles_found", "sum"),
        total=("total_glossary_dogwhistles", "sum"),
        types_found=("distinct_types_found", "sum"),
        types_total=("total_glossary_types", "sum"),
    )

    def _rate(target: str, found_col: str, total_col: str) -> float:
        if target not in agg.index:
            return float("nan")
        total = agg.loc[target, total_col]
        if total <= 0:
            return float("nan")
        return safe_float(agg.loc[target, found_col]) / total

    pr_a = _rate(target_a, "found", "total")
    pr_b = _rate(target_b, "found", "total")
    tc_a = _rate(target_a, "types_found", "types_total")
    tc_b = _rate(target_b, "types_found", "types_total")

    pr_di = safe_di_ratio(pr_a, pr_b)
    tc_di = safe_di_ratio(tc_a, tc_b)
    worst_di = min(pr_di, tc_di) if pd.notna(pr_di) and pd.notna(tc_di) else float("nan")

    return {
        "presence_rate_a": pr_a,
        "presence_rate_b": pr_b,
        "presence_rate_di_ratio": pr_di,
        "type_coverage_a": tc_a,
        "type_coverage_b": tc_b,
        "type_coverage_di_ratio": tc_di,
        "worst_di_ratio": worst_di,
    }


def _passes(value: float) -> object:
    if pd.isna(value):
        return pd.NA
    return bool(value >= DI_THRESHOLD)


def _direction(value_a: float, value_b: float) -> object:
    if pd.isna(value_a) or pd.isna(value_b):
        return pd.NA
    if value_b > value_a:
        return "less_disparate"
    if value_b < value_a:
        return "more_disparate"
    return "unchanged"


def _conclusion_changed(passes_a: object, passes_b: object) -> object:
    if passes_a is pd.NA or passes_b is pd.NA:
        return pd.NA
    return bool(passes_a != passes_b)


def _comparison_row(
    granularity: str,
    report_level: str,
    level: str,
    metric: str,
    target_a: str,
    target_b: str,
    value_a: float,
    value_b: float,
    unstable_a: bool,
    unstable_b: bool,
) -> dict[str, object]:
    passes_a = _passes(value_a)
    passes_b = _passes(value_b)
    return {
        "granularity": granularity,
        "report_level": report_level,
        "target_a": target_a,
        "target_b": target_b,
        "level": level,
        "metric": metric,
        "value_a": value_a,
        "value_b": value_b,
        "passes_4_5_a": passes_a,
        "passes_4_5_b": passes_b,
        "conclusion_changed": _conclusion_changed(passes_a, passes_b),
        "direction": _direction(value_a, value_b),
        "unstable_small_n_a": unstable_a,
        "unstable_small_n_b": unstable_b,
    }


def _per_level_rows(
    granularity: str, pairwise_a: pd.DataFrame, pairwise_b: pd.DataFrame
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if pairwise_a.empty or pairwise_b.empty:
        return rows

    key_cols = ["target_a", "target_b", "coding_level"]
    merged = pairwise_a.merge(
        pairwise_b, on=key_cols, how="inner", suffixes=("_a", "_b")
    )

    for _, row in merged.iterrows():
        report_level = row.get("report_level_a", row.get("report_level", ""))
        common = dict(
            granularity=granularity,
            report_level=report_level,
            level=row["coding_level"],
            target_a=row["target_a"],
            target_b=row["target_b"],
            unstable_a=bool(row["unstable_small_n_a"]),
            unstable_b=bool(row["unstable_small_n_b"]),
        )
        rows.append(
            _comparison_row(
                metric="coverage",
                value_a=safe_float(row["worst_di_ratio_a"]),
                value_b=safe_float(row["worst_di_ratio_b"]),
                **common,
            )
        )
        rows.append(
            _comparison_row(
                metric="annotation",
                value_a=safe_float(row["annotation_di_ratio_a"]),
                value_b=safe_float(row["annotation_di_ratio_b"]),
                **common,
            )
        )
    return rows


def _pooled_rows(
    granularity: str, coverage_a: pd.DataFrame, coverage_b: pd.DataFrame, pairs: pd.DataFrame
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()

    for _, row in pairs.iterrows():
        target_a, target_b = row["target_a"], row["target_b"]
        pair_key = (target_a, target_b)
        if pair_key in seen:
            continue
        seen.add(pair_key)

        pooled_a = compute_pooled_coverage_di(coverage_a, target_a, target_b)
        pooled_b = compute_pooled_coverage_di(coverage_b, target_a, target_b)

        # Pooled stability: unstable if the pair was unstable at every level
        # examined in either variant (mirrors the "no stable pairs" case
        # rq_reporting.py used to flag).
        unstable_a = bool(row.get("_all_unstable_a", False))
        unstable_b = bool(row.get("_all_unstable_b", False))

        rows.append(
            _comparison_row(
                granularity=granularity,
                report_level=row.get("report_level", ""),
                level="pooled",
                metric="coverage",
                target_a=target_a,
                target_b=target_b,
                value_a=pooled_a["worst_di_ratio"],
                value_b=pooled_b["worst_di_ratio"],
                unstable_a=unstable_a,
                unstable_b=unstable_b,
            )
        )
    return rows


def build_comparison_table(
    variant_a: PipelineVariant = VARIANT_FULL,
    variant_b: PipelineVariant = VARIANT_TIER12,
) -> pd.DataFrame:
    """Build the full Tier-1+2 vs. full-glossary comparison table.

    One row per (pair, level, metric) present in both variants' Stage 4
    outputs, covering both fine-grained/raw-target pairs and collapsed
    reporting-group pairs, at every coding level plus one pooled-coverage-DI
    row per pair. Not restricted to any specific pairs named in the paper --
    general over everything both variants have in common.
    """
    all_rows: list[dict[str, object]] = []

    for granularity, coverage_rel, pairwise_rel in _GRANULARITIES:
        pairwise_a = _read(variant_a, pairwise_rel)
        pairwise_b = _read(variant_b, pairwise_rel)
        coverage_a = _read(variant_a, coverage_rel)
        coverage_b = _read(variant_b, coverage_rel)

        all_rows.extend(_per_level_rows(granularity, pairwise_a, pairwise_b))

        if pairwise_a.empty or pairwise_b.empty:
            continue

        # One representative row per pair (regardless of level) to drive the
        # pooled comparison, annotated with whether the pair was unstable at
        # every level present for that variant.
        pair_cols = ["target_a", "target_b", "report_level"]
        pairs = (
            pairwise_a[pair_cols]
            .drop_duplicates(["target_a", "target_b"])
            .merge(
                pairwise_b[["target_a", "target_b"]].drop_duplicates(),
                on=["target_a", "target_b"],
                how="inner",
            )
        )
        stability_a = pairwise_a.groupby(["target_a", "target_b"])[
            "unstable_small_n"
        ].all()
        stability_b = pairwise_b.groupby(["target_a", "target_b"])[
            "unstable_small_n"
        ].all()
        pairs["_all_unstable_a"] = pairs.apply(
            lambda r: stability_a.get((r["target_a"], r["target_b"]), True), axis=1
        )
        pairs["_all_unstable_b"] = pairs.apply(
            lambda r: stability_b.get((r["target_a"], r["target_b"]), True), axis=1
        )

        all_rows.extend(_pooled_rows(granularity, coverage_a, coverage_b, pairs))

    return pd.DataFrame(all_rows)


def write_manifest(base_dir: Path) -> None:
    manifest = base_dir / "README.md"
    text = """# Tier-1+2 Robustness Check Output

Generated by `audit_pipeline/robustness_check.py`.

- `robustness_comparison.tsv`: one row per (pair, level, metric), comparing
  the primary (all-tier) analysis against the tier-1+2-restricted analysis.
  Covers both fine-grained/raw-taxonomy-target pairs (e.g.
  `race:black` vs. `race:middle_eastern`) and collapsed reporting-group
  pairs (e.g. `LGB` vs. `Trans/NB`), at every coding level plus one
  pooled-coverage-DI row per pair.

Columns:
- `granularity`: `fine` (raw taxonomy targets) or `collapsed` (reporting
  groups).
- `level`: a coding level (`L2`/`L3`/`L4`) or `pooled`.
- `metric`: `coverage` or `annotation`.
- `value_a`/`value_b`: the DI ratio under the full-glossary analysis /
  tier-1+2-restricted analysis respectively.
- `passes_4_5_a`/`passes_4_5_b`: whether each value clears the 0.8
  disparate-impact threshold. `NA` when the underlying value is `NA`.
- `conclusion_changed`: whether the pass/fail conclusion differs between the
  two analyses. `NA` when either side's pass/fail status is unknown.
- `direction`: `less_disparate`, `more_disparate`, or `unchanged`, comparing
  the tier-1+2 value against the full-glossary value.
- `unstable_small_n_a`/`unstable_small_n_b`: small-sample-size flags carried
  through from each variant's Stage 4 output.

**Pooled-DI methodology:** see the module docstring in
`audit_pipeline/robustness_check.py` -- raw counts are summed across all
coding levels before computing one DI ratio, which is *not* the same
methodology as `generate_figures_final.py`'s deprecated
`appD_worst_di_and_label_gap_pooled` (min of each level's own ratio).

**Staleness:** this table reflects whatever full/tier12 Stage 4 outputs
were on disk when it was generated. Rerun `python -m audit_pipeline.run_all`
(both variants together) if you suspect the two are out of sync.
"""
    manifest.write_text(text, encoding="utf-8")


def main(
    base_dir: Path | None = None,
    variant_a: PipelineVariant = VARIANT_FULL,
    variant_b: PipelineVariant = VARIANT_TIER12,
) -> None:
    """Build and write the robustness comparison table to *base_dir*.

    Parameters
    ----------
    base_dir : Path or None
        Root output directory. Defaults to ``outputs/robustness_check/``.
    variant_a, variant_b : PipelineVariant
        The two variants to compare. Defaults to the primary analysis vs.
        the tier-1+2 robustness check.
    """
    if base_dir is None:
        base_dir = OUT_ROBUSTNESS
    ensure_dirs(base_dir)

    table = build_comparison_table(variant_a, variant_b)
    write_tsv(table, base_dir / "robustness_comparison.tsv")
    write_manifest(base_dir)

    print(f"Robustness comparison written to: {base_dir}")
    print(f"  wrote {len(table):,} rows -> robustness_comparison.tsv")
    if not table.empty:
        n_changed = int(table["conclusion_changed"].fillna(False).sum())
        print(f"  {n_changed} row(s) where the 4/5-rule conclusion changed")


if __name__ == "__main__":
    main()
