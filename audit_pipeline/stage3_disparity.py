"""Stage 3: pairwise disparity and cross-level consistency checks.

This stage compares target groups within the same taxonomy/coding partitions,
then adds context for when differing base rates imply unavoidable fairness
tradeoffs.
"""

from __future__ import annotations

import pandas as pd

from audit_pipeline.config import N_MIN, OUT_S1, OUT_S2, OUT_S3
from audit_pipeline.helpers import build_pairwise_rows, ensure_dirs, write_tsv


def _level_rank(level_value: str) -> int:
    """Normalize taxonomy-level labels to a sortable numeric rank."""
    # Accept values like 'l1', 'L2', '1', etc.
    s = str(level_value).strip().lower()
    if s.startswith("l") and s[1:].isdigit():
        return int(s[1:])
    if s.isdigit():
        return int(s)
    return 999


def run() -> None:
    """Build Stage 3 disparity tables from Stage 1 and Stage 2 outputs."""
    ensure_dirs(OUT_S3)

    coverage = pd.read_csv(
        OUT_S1 / "s1_coverage_by_level_target.tsv", sep="\t", low_memory=False
    )
    annotation = pd.read_csv(
        OUT_S2 / "s2_annotation_by_level_target.tsv", sep="\t", low_memory=False
    )
    if "base_rate_q_a" not in annotation.columns:
        annotation["base_rate_q_a"] = pd.NA
    if "total_target_group_posts" not in annotation.columns:
        annotation["total_target_group_posts"] = pd.NA

    merged = coverage.merge(
        annotation[
            [
                "taxonomy_level",
                "target",
                "coding_level",
                "correct_labeling_rate",
                "failure_rate",
                "total_matches",
                "total_target_group_posts",
                "base_rate_q_a",
            ]
        ],
        on=["taxonomy_level", "target", "coding_level"],
        how="left",
    )

    # Build pairwise comparisons inside each taxonomy level and coding level so
    # groups are only compared against peers at the same abstraction level.
    pair_rows = []
    for (taxonomy_level, coding_level), grp in merged.groupby(
        ["taxonomy_level", "coding_level"]
    ):
        r = build_pairwise_rows(
            group_df=grp.assign(_pair_key=f"{taxonomy_level}||{coding_level}"),
            presence_col="presence_rate",
            type_cov_col="type_coverage",
            labeling_col="correct_labeling_rate",
            failure_col="failure_rate",
            matches_col="total_matches",
            level_col="_pair_key",
            target_col="target",
            n_min=N_MIN,
        )
        for row in r:
            row["taxonomy_level"] = taxonomy_level
            row["coding_level"] = coding_level
        pair_rows.extend(r)
    pairwise = pd.DataFrame(pair_rows)
    if not pairwise.empty:
        pairwise = pairwise.drop(columns=["_pair_key"], errors="ignore")
        # Reattach per-group base rates so pairwise rows can explicitly mark the
        # impossibility-theorem setting: different base rates with stable group
        # sizes make simultaneous calibration/equalized-odds parity infeasible.
        base_ref = (
            merged[
                [
                    "taxonomy_level",
                    "coding_level",
                    "target",
                    "base_rate_q_a",
                    "total_target_group_posts",
                ]
            ]
            .drop_duplicates(["taxonomy_level", "coding_level", "target"])
            .copy()
        )
        left_base = base_ref.rename(
            columns={
                "target": "target_a",
                "base_rate_q_a": "base_rate_q_a_a",
                "total_target_group_posts": "total_target_group_posts_a",
            }
        )
        right_base = base_ref.rename(
            columns={
                "target": "target_b",
                "base_rate_q_a": "base_rate_q_a_b",
                "total_target_group_posts": "total_target_group_posts_b",
            }
        )
        pairwise = pairwise.merge(
            left_base,
            on=["taxonomy_level", "coding_level", "target_a"],
            how="left",
        ).merge(
            right_base,
            on=["taxonomy_level", "coding_level", "target_b"],
            how="left",
        )
        pairwise["base_rate_gap"] = (
            pairwise["base_rate_q_a_a"] - pairwise["base_rate_q_a_b"]
        )
        pairwise["base_rate_gap_abs"] = pairwise["base_rate_gap"].abs()
        pairwise["impossibility_tradeoff_flag"] = (
            (pairwise["total_target_group_posts_a"] >= N_MIN)
            & (pairwise["total_target_group_posts_b"] >= N_MIN)
            & pairwise["base_rate_gap_abs"].notna()
            & (pairwise["base_rate_gap_abs"] > 0)
        )
        pairwise["impossibility_tradeoff_note"] = pairwise[
            "impossibility_tradeoff_flag"
        ].map(
            lambda v: (
                "Base rates differ across groups; calibration and equalized-odds parity cannot generally be simultaneously satisfied."
                if bool(v)
                else pd.NA
            )
        )

    if pairwise.empty:
        coverage_disparity = pd.DataFrame(
            columns=[
                "taxonomy_level",
                "coding_level",
                "target_a",
                "target_b",
                "presence_rate_a",
                "presence_rate_b",
                "presence_rate_di_ratio",
                "type_coverage_a",
                "type_coverage_b",
                "type_coverage_di_ratio",
                "worst_di_ratio",
                "total_matches_a",
                "total_matches_b",
                "unstable_small_n",
                "base_rate_q_a_a",
                "base_rate_q_a_b",
                "base_rate_gap",
                "base_rate_gap_abs",
                "impossibility_tradeoff_flag",
                "impossibility_tradeoff_note",
            ]
        )
        annotation_disparity = pd.DataFrame(
            columns=[
                "taxonomy_level",
                "coding_level",
                "target_a",
                "target_b",
                "correct_labeling_rate_a",
                "correct_labeling_rate_b",
                "annotation_di_ratio",
                "labeling_rate_gap",
                "labeling_rate_gap_abs",
                "failure_rate_a",
                "failure_rate_b",
                "failure_rate_gap",
                "failure_rate_gap_abs",
                "total_matches_a",
                "total_matches_b",
                "unstable_small_n",
                "base_rate_q_a_a",
                "base_rate_q_a_b",
                "base_rate_gap",
                "base_rate_gap_abs",
                "impossibility_tradeoff_flag",
                "impossibility_tradeoff_note",
            ]
        )
    else:
        coverage_disparity = pairwise[
            [
                "taxonomy_level",
                "coding_level",
                "target_a",
                "target_b",
                "presence_rate_a",
                "presence_rate_b",
                "presence_rate_di_ratio",
                "type_coverage_a",
                "type_coverage_b",
                "type_coverage_di_ratio",
                "worst_di_ratio",
                "total_matches_a",
                "total_matches_b",
                "unstable_small_n",
                "base_rate_q_a_a",
                "base_rate_q_a_b",
                "base_rate_gap",
                "base_rate_gap_abs",
                "impossibility_tradeoff_flag",
                "impossibility_tradeoff_note",
            ]
        ].copy()

        annotation_disparity = pairwise[
            [
                "taxonomy_level",
                "coding_level",
                "target_a",
                "target_b",
                "correct_labeling_rate_a",
                "correct_labeling_rate_b",
                "annotation_di_ratio",
                "labeling_rate_gap",
                "labeling_rate_gap_abs",
                "failure_rate_a",
                "failure_rate_b",
                "failure_rate_gap",
                "failure_rate_gap_abs",
                "total_matches_a",
                "total_matches_b",
                "unstable_small_n",
                "base_rate_q_a_a",
                "base_rate_q_a_b",
                "base_rate_gap",
                "base_rate_gap_abs",
                "impossibility_tradeoff_flag",
                "impossibility_tradeoff_note",
            ]
        ].copy()

    # Cross-level consistency compares adjacent taxonomy levels for the same
    # target and coding level to surface abrupt metric shifts across the coding
    # hierarchy rather than across different targets.
    cov_ann = coverage.merge(
        annotation[
            [
                "taxonomy_level",
                "target",
                "coding_level",
                "correct_labeling_rate",
                "failure_rate",
            ]
        ],
        on=["taxonomy_level", "target", "coding_level"],
        how="left",
    )

    cross_rows = []
    for (target, coding_level), tdf in cov_ann.groupby(["target", "coding_level"]):
        tdf = tdf.copy()
        tdf["_rank"] = tdf["taxonomy_level"].apply(_level_rank)
        tdf = tdf.sort_values("_rank")
        for i in range(len(tdf) - 1):
            a = tdf.iloc[i]
            b = tdf.iloc[i + 1]
            cross_rows.append(
                {
                    "target": target,
                    "coding_level": coding_level,
                    "level_from": a["taxonomy_level"],
                    "level_to": b["taxonomy_level"],
                    "presence_rate_from": a["presence_rate"],
                    "presence_rate_to": b["presence_rate"],
                    "presence_rate_delta": b["presence_rate"] - a["presence_rate"]
                    if pd.notna(a["presence_rate"]) and pd.notna(b["presence_rate"])
                    else pd.NA,
                    "type_coverage_from": a["type_coverage"],
                    "type_coverage_to": b["type_coverage"],
                    "type_coverage_delta": b["type_coverage"] - a["type_coverage"]
                    if pd.notna(a["type_coverage"]) and pd.notna(b["type_coverage"])
                    else pd.NA,
                    "correct_labeling_rate_from": a["correct_labeling_rate"],
                    "correct_labeling_rate_to": b["correct_labeling_rate"],
                    "correct_labeling_rate_delta": b["correct_labeling_rate"]
                    - a["correct_labeling_rate"]
                    if pd.notna(a["correct_labeling_rate"])
                    and pd.notna(b["correct_labeling_rate"])
                    else pd.NA,
                    "failure_rate_from": a["failure_rate"],
                    "failure_rate_to": b["failure_rate"],
                    "failure_rate_delta": b["failure_rate"] - a["failure_rate"]
                    if pd.notna(a["failure_rate"]) and pd.notna(b["failure_rate"])
                    else pd.NA,
                }
            )

    cross = pd.DataFrame(cross_rows)

    p_cov = OUT_S3 / "s3_coverage_disparity.tsv"
    p_ann = OUT_S3 / "s3_annotation_disparity.tsv"
    p_xlv = OUT_S3 / "s3_cross_level_consistency.tsv"
    write_tsv(coverage_disparity, p_cov)
    write_tsv(annotation_disparity, p_ann)
    write_tsv(cross, p_xlv)

    print("[Stage 3] Disparity complete")
    print(f"  wrote {len(coverage_disparity):,} rows -> {p_cov}")
    print(f"  wrote {len(annotation_disparity):,} rows -> {p_ann}")
    print(f"  wrote {len(cross):,} rows -> {p_xlv}")


if __name__ == "__main__":
    run()
