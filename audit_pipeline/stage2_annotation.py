"""Stage 2: annotation quality metrics for matched dogwhistles.

This stage converts Stage 1 matches into Case A/B/C counts, per-group labeling
rates, and dogwhistle-level detail tables for error analysis.

Pass a PipelineVariant to run() to select which stage-1 outputs to read from
and where stage-2 outputs are written.
"""

from __future__ import annotations

import pandas as pd

from audit_pipeline.config import (
    DATA_PATH,
    N_MIN,
    VARIANT_FULL,
    PipelineVariant,
    resolve_variant,
)
from audit_pipeline.helpers import ensure_dirs, write_tsv


def _target_contains(row_targets: str, specific_target: str) -> bool:
    """Exact membership check against comma-separated target tokens.

    Prevents substring inflation such as matching 'men' inside 'women'.
    """
    target_set = {t.strip().lower() for t in str(row_targets).split(",") if t.strip()}
    return str(specific_target).strip().lower() in target_set


def run(variant: PipelineVariant = VARIANT_FULL) -> None:
    """Aggregate annotation-quality metrics from Stage 1 match artifacts.

    Parameters
    ----------
    variant : PipelineVariant
        Controls where stage-1 inputs are read from (``variant.out_s1``) and
        where stage-2 outputs are written (``variant.out_s2``).
    """
    ensure_dirs(variant.out_s2)

    matches = pd.read_csv(variant.out_s1 / "s1_matches.tsv", sep="\t", low_memory=False)
    coverage = pd.read_csv(
        variant.out_s1 / "s1_coverage_by_level_target.tsv", sep="\t", low_memory=False
    )
    data = pd.read_csv(DATA_PATH, sep="\t", low_memory=False)

    # Keyed by (taxonomy_level, target, coding_level) for O(1) lookup inside the loop.
    coverage_lookup = {
        (r.taxonomy_level, r.target, r.coding_level): r
        for _, r in coverage.iterrows()
    }

    if matches.empty:
        annotation = pd.DataFrame(
            columns=[
                "taxonomy_level",
                "target",
                "coding_level",
                "case_a_present_hateful",
                "case_b_present_nonhateful",
                "case_c_absent",
                "correct_labeling_rate",
                "failure_rate",
                "total_matches",
                "total_target_group_posts",
                "base_rate_q_a",
                "stable_n",
                "case_b_c_ratio",
                "is_self_referential",
            ]
        )
        detail = pd.DataFrame(
            columns=[
                "taxonomy_level",
                "target",
                "coding_level",
                "dogwhistle",
                "matched_surface_forms",
                "case_a_count",
                "case_b_count",
                "labeling_accuracy",
                "type",
                "is_self_referential",
            ]
        )
    else:
        dedup_hits = matches.drop_duplicates(
            ["taxonomy_level", "target", "coding_level", "text_dedup_key", "dogwhistle"]
        ).copy()

        rows = []
        detail_rows = []

        for (level, target, coding_level), group in dedup_hits.groupby(
            ["taxonomy_level", "target", "coding_level"]
        ):
            # Case A/B are defined over matched dogwhistles only.
            case_a = int((group["binary_hate"] == 1).sum())
            case_b = int((group["binary_hate"] == 0).sum())
            total_matches = case_a + case_b

            # The denominator for group prevalence must use exact target-token
            # membership, not substring containment, to avoid target inflation.
            target_mask = (
                data["targets"]
                .fillna("")
                .astype(str)
                .apply(lambda row_targets: _target_contains(row_targets, str(target)))
            )
            target_group_posts = data[target_mask]

            # case_c counts glossary TERMS (not posts) with zero corpus matches for
            # this (taxonomy_level, target, coding_level) cell.  It is a term-level
            # count and is incommensurable with case_a / case_b (which are post-level
            # counts): do not add A + B + C into a single total.
            cov_row = coverage_lookup.get((level, target, coding_level))
            if cov_row is not None:
                case_c = int(cov_row["total_glossary_dogwhistles"]) - int(
                    cov_row["distinct_dogwhistles_found"]
                )
            else:
                # Coverage file has no entry for this cell (can happen for cells
                # whose glossary type is unmapped).  Fall back to zero; the
                # discrepancy will already be visible in the coverage audit.
                case_c = 0

            # q_a is the actual prevalence of hateful ground truth inside the
            # target-group population, not a rate derived from matched hits.
            base_rate_q_a = (
                target_group_posts["binary_hate"].mean()
                if len(target_group_posts) > 0
                else pd.NA
            )

            correct_rate = case_a / total_matches if total_matches > 0 else pd.NA
            failure_rate = case_b / total_matches if total_matches > 0 else pd.NA
            # case_b (posts) and case_c (terms) are different units; their sum is
            # not meaningful.  Set to NA so downstream tables don't silently mix units.
            b_c_ratio = pd.NA

            rows.append(
                {
                    "taxonomy_level": level,
                    "target": target,
                    "coding_level": coding_level,
                    "case_a_present_hateful": case_a,
                    "case_b_present_nonhateful": case_b,
                    "case_c_absent": case_c,
                    "correct_labeling_rate": correct_rate,
                    "failure_rate": failure_rate,
                    "total_matches": total_matches,
                    "total_target_group_posts": int(len(target_group_posts)),
                    "base_rate_q_a": base_rate_q_a,
                    "stable_n": bool(total_matches >= N_MIN),
                    "case_b_c_ratio": b_c_ratio,
                    "is_self_referential": bool(group["is_self_referential"].max()),
                }
            )

            for dogwhistle, dog_group in group.groupby("dogwhistle"):
                # Preserve dogwhistle-level detail so later writeups can inspect
                # which forms drive Case B errors inside each target slice.
                case_a_dw = int((dog_group["binary_hate"] == 1).sum())
                case_b_dw = int((dog_group["binary_hate"] == 0).sum())
                ab_dw = case_a_dw + case_b_dw
                acc_dw = case_a_dw / ab_dw if ab_dw > 0 else pd.NA
                matched_forms = "; ".join(
                    sorted(
                        set(
                            matches[
                                (matches["taxonomy_level"] == level)
                                & (matches["target"] == target)
                                & (matches["coding_level"] == coding_level)
                                & (matches["dogwhistle"] == dogwhistle)
                            ]["found_forms"]
                            .dropna()
                            .astype(str)
                        )
                    )
                )

                detail_rows.append(
                    {
                        "taxonomy_level": level,
                        "target": target,
                        "coding_level": coding_level,
                        "dogwhistle": dogwhistle,
                        "matched_surface_forms": matched_forms,
                        "case_a_count": case_a_dw,
                        "case_b_count": case_b_dw,
                        "labeling_accuracy": acc_dw,
                        "type": str(dog_group["type"].iloc[0])
                        if len(dog_group)
                        else "",
                        "is_self_referential": bool(
                            dog_group["is_self_referential"].max()
                        ),
                    }
                )

        annotation = pd.DataFrame(rows).sort_values(
            ["taxonomy_level", "target", "coding_level"]
        )
        detail = pd.DataFrame(detail_rows).sort_values(
            [
                "taxonomy_level",
                "target",
                "coding_level",
                "case_b_count",
                "case_a_count",
            ],
            ascending=[True, True, True, False, False],
        )

    p_ann = variant.out_s2 / "s2_annotation_by_level_target.tsv"
    p_det = variant.out_s2 / "s2_form_labeling_detail.tsv"
    write_tsv(annotation, p_ann)
    write_tsv(detail, p_det)

    print(f"[Stage 2 – {variant.name}] Annotation quality complete")
    print(f"  wrote {len(annotation):,} rows -> {p_ann}")
    print(f"  wrote {len(detail):,} rows -> {p_det}")

    if not annotation.empty:
        unstable = int((~annotation["stable_n"]).sum())
        print(f"  unstable groups (<{N_MIN} matches): {unstable}")


if __name__ == "__main__":
    run(resolve_variant())
