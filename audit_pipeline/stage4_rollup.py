"""Stage 4: reporting-group rollups and benchmark subset deltas.

This stage collapses target-level outputs into reporting groups, computes the
four-fifths pass/fail summary, and measures deltas for the ElSherief subset.

Pass a PipelineVariant to run() to select which glossary tiers are active and
where outputs are written.  The glossary is re-filtered here (using the same
allowed_tiers as Stage 1) so that the ``total_glossary_dogwhistles`` denominator
used to compute presence_rate is consistent with the tier-filtered match set.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from audit_pipeline.config import (
    DATA_PATH,
    DATA_PATH_WITH_ELSHERIEF,
    DI_THRESHOLD,
    ELSHERIEF_DATASET_NAME,
    GLOSSARY_PATH,
    N_MIN,
    OUT_S1_WITH_ELSHERIEF,
    VARIANT_FULL,
    PipelineVariant,
    resolve_variant,
)
from audit_pipeline.helpers import (
    add_reporting_columns,
    build_pairwise_rows,
    ensure_dirs,
    map_reporting_group,
    map_type_to_coding_level,
    norm_target,
    parse_list_like,
    write_tsv,
)


def _load_filtered_matches(
    dataset_filter: str | None,
    s1_dir: Path,
) -> pd.DataFrame:
    """Load Stage 1 matches, optionally restricted to a dataset name.

    Parameters
    ----------
    dataset_filter : str or None
        When provided, keep only rows whose ``dataset`` column matches this
        string (case-insensitive).
    s1_dir : Path
        Directory containing the Stage 1 ``s1_matches.tsv`` artifact.
    """
    matches = pd.read_csv(s1_dir / "s1_matches.tsv", sep="\t", low_memory=False)
    if dataset_filter:
        matches = matches[
            matches["dataset"].astype(str).str.lower() == dataset_filter.lower()
        ].copy()
    return matches


def _dataset_row_count(dataset_filter: str | None) -> int:
    """Count source rows for a dataset filter.

    This is used to distinguish a genuinely empty subset from a subset that
    merely produces no dogwhistle matches.
    """
    if not dataset_filter:
        return -1
    data = pd.read_csv(DATA_PATH, sep="\t", usecols=["dataset"], low_memory=False)
    return int(
        (data["dataset"].astype(str).str.lower() == dataset_filter.lower()).sum()
    )


def _build_target_posts(
    dataset_filter: str | None, include_taxonomy_level: bool
) -> pd.DataFrame:
    """Construct the post-level denominator table for rollup annotation rates."""
    data = pd.read_csv(DATA_PATH, sep="\t", low_memory=False)
    if dataset_filter:
        data = data[
            data["dataset"].astype(str).str.lower() == dataset_filter.lower()
        ].copy()

    rows = []
    for _, row in data.iterrows():
        key = str(row.get("text_dedup_key", ""))
        if not key:
            continue
        labels = parse_list_like(row.get("cleaned_label"))
        mapped = set()
        for label in labels:
            lab = norm_target(label)
            if " " not in lab:
                continue
            level, target = lab.split(" ", 1)
            grp = map_reporting_group(level, target)
            if not grp.include:
                continue
            if include_taxonomy_level:
                mapped.add((level, grp.report_level, grp.report_target))
            else:
                mapped.add((grp.report_level, grp.report_target))

        for m in mapped:
            if include_taxonomy_level:
                taxonomy_level, report_level, report_target = m
                rows.append(
                    {
                        "text_dedup_key": key,
                        "taxonomy_level": taxonomy_level,
                        "report_level": report_level,
                        "report_target": report_target,
                    }
                )
            else:
                report_level, report_target = m
                rows.append(
                    {
                        "text_dedup_key": key,
                        "report_level": report_level,
                        "report_target": report_target,
                    }
                )

    out = pd.DataFrame(rows)
    if not out.empty:
        dedup_cols = ["text_dedup_key", "report_level", "report_target"]
        if include_taxonomy_level:
            dedup_cols.insert(1, "taxonomy_level")
        out = out.drop_duplicates(dedup_cols)
    return out


def _load_glossary_ref(
    allowed_tiers: frozenset[int] | None,
) -> pd.DataFrame:
    """Load and optionally tier-filter the glossary reference table.

    The returned DataFrame is used to compute ``total_glossary_dogwhistles``
    and ``total_glossary_types`` denominators.  Applying the same tier filter
    here as in Stage 1 ensures that presence_rate = found / total uses a
    consistent denominator: only the tiers that were actually searched for.

    Parameters
    ----------
    allowed_tiers : frozenset[int] or None
        When provided, keep only glossary rows whose ``tier`` parses to an
        integer in this set.  ``None`` retains all rows.
    """
    glossary_ref = pd.read_csv(GLOSSARY_PATH, sep="\t", low_memory=False)
    if allowed_tiers is not None and "tier" in glossary_ref.columns:
        tier_int = pd.to_numeric(glossary_ref["tier"], errors="coerce")
        glossary_ref = glossary_ref[tier_int.isin(allowed_tiers)].copy()
    return glossary_ref


def compute_rollup(
    dataset_filter: str | None,
    include_taxonomy_level: bool,
    s1_dir: Path,
    allowed_tiers: frozenset[int] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Compute coverage, annotation, and pairwise rollups for one reporting view.

    ``include_taxonomy_level`` toggles between the group-collapsed outputs (4a)
    and the taxonomy-preserving outputs (4b).

    Parameters
    ----------
    dataset_filter : str or None
        When provided, restrict to rows from this dataset (e.g. ``"elsherief"``).
    include_taxonomy_level : bool
        Whether to keep the taxonomy_level dimension in group keys.
    s1_dir : Path
        Directory containing the Stage 1 match artifact for this variant.
    allowed_tiers : frozenset[int] or None
        Tier filter applied to the glossary denominator to match the one used
        in Stage 1.  Passing ``None`` uses all tiers.
    """
    matches = _load_filtered_matches(dataset_filter, s1_dir)
    dataset_rows = _dataset_row_count(dataset_filter)

    # Filter the glossary denominator by the same tiers used in Stage 1 so
    # that presence_rate = found/total is computed over a consistent universe.
    glossary_ref = _load_glossary_ref(allowed_tiers)
    glossary_ref = add_reporting_columns(glossary_ref, "taxonomy_level", "target")
    glossary_ref = glossary_ref[glossary_ref["report_include"]].copy()
    glossary_ref["coding_level"] = glossary_ref["type"].apply(map_type_to_coding_level)

    matches = add_reporting_columns(matches, "taxonomy_level", "target")
    matches = matches[matches["report_include"]].copy()

    # If dataset-filtered subset is truly empty, return empty frames so delta merges yield NaN.
    if dataset_filter and dataset_rows == 0:
        if include_taxonomy_level:
            cov_cols = [
                "taxonomy_level",
                "coding_level",
                "report_level",
                "report_target",
                "total_glossary_dogwhistles",
                "total_glossary_types",
                "is_self_referential",
                "distinct_dogwhistles_found",
                "distinct_types_found",
                "token_frequency",
                "presence_rate",
                "type_coverage",
            ]
            ann_cols = [
                "taxonomy_level",
                "coding_level",
                "report_level",
                "report_target",
                "is_self_referential",
                "case_a_present_hateful",
                "case_b_present_nonhateful",
                "total_matches",
                "total_target_group_posts",
                "case_c_absent",
                "correct_labeling_rate",
                "failure_rate",
                "stable_n",
                "case_b_c_ratio",
            ]
            pair_cols = [
                "taxonomy_level",
                "coding_level",
                "report_level",
                "target_a",
                "target_b",
                "presence_rate_a",
                "presence_rate_b",
                "presence_rate_di_ratio",
                "type_coverage_a",
                "type_coverage_b",
                "type_coverage_di_ratio",
                "worst_di_ratio",
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
            ]
        else:
            cov_cols = [
                "coding_level",
                "report_level",
                "report_target",
                "total_glossary_dogwhistles",
                "total_glossary_types",
                "is_self_referential",
                "distinct_dogwhistles_found",
                "distinct_types_found",
                "token_frequency",
                "presence_rate",
                "type_coverage",
            ]
            ann_cols = [
                "coding_level",
                "report_level",
                "report_target",
                "is_self_referential",
                "case_a_present_hateful",
                "case_b_present_nonhateful",
                "total_matches",
                "total_target_group_posts",
                "case_c_absent",
                "correct_labeling_rate",
                "failure_rate",
                "stable_n",
                "case_b_c_ratio",
            ]
            pair_cols = [
                "coding_level",
                "report_level",
                "target_a",
                "target_b",
                "presence_rate_a",
                "presence_rate_b",
                "presence_rate_di_ratio",
                "type_coverage_a",
                "type_coverage_b",
                "type_coverage_di_ratio",
                "worst_di_ratio",
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
            ]
        return (
            pd.DataFrame(columns=cov_cols),
            pd.DataFrame(columns=ann_cols),
            pd.DataFrame(columns=pair_cols),
        )

    if include_taxonomy_level:
        group_keys = ["taxonomy_level", "coding_level", "report_level", "report_target"]
        glossary_group_keys = [
            "taxonomy_level",
            "coding_level",
            "report_level",
            "report_target",
        ]
    else:
        group_keys = ["coding_level", "report_level", "report_target"]
        glossary_group_keys = ["coding_level", "report_level", "report_target"]

    glossary_totals = (
        glossary_ref.groupby(glossary_group_keys, as_index=False)
        .agg(
            total_glossary_dogwhistles=("dogwhistle", "nunique"),
            total_glossary_types=("type", "nunique"),
            is_self_referential=(
                "type",
                lambda s: bool(
                    s.astype(str).str.contains("self-referential", na=False).any()
                ),
            ),
        )
        .sort_values(glossary_group_keys)
    )

    if matches.empty:
        found = glossary_totals[glossary_group_keys].copy()
        found["distinct_dogwhistles_found"] = 0
        found["distinct_types_found"] = 0
        found["token_frequency"] = 0
        ab = glossary_totals[glossary_group_keys].copy()
        ab["case_a_present_hateful"] = 0
        ab["case_b_present_nonhateful"] = 0
        ab["total_matches"] = 0
    else:
        # One count per post x dogwhistle x group.
        dedup = matches.drop_duplicates(["text_dedup_key", "dogwhistle"] + group_keys)

        found = (
            dedup.groupby(group_keys, as_index=False)
            .agg(
                distinct_dogwhistles_found=("dogwhistle", "nunique"),
                distinct_types_found=("type", "nunique"),
                token_frequency=("dogwhistle", "count"),
            )
            .sort_values(group_keys)
        )

        ab = (
            dedup.groupby(group_keys, as_index=False)
            .agg(
                case_a_present_hateful=("binary_hate", lambda s: int((s == 1).sum())),
                case_b_present_nonhateful=(
                    "binary_hate",
                    lambda s: int((s == 0).sum()),
                ),
                total_matches=("binary_hate", "count"),
            )
            .sort_values(group_keys)
        )

    coverage = glossary_totals.merge(found, on=glossary_group_keys, how="left")
    for c in ["distinct_dogwhistles_found", "distinct_types_found", "token_frequency"]:
        coverage[c] = coverage[c].fillna(0).astype(int)

    coverage["presence_rate"] = coverage["distinct_dogwhistles_found"] / coverage[
        "total_glossary_dogwhistles"
    ].where(coverage["total_glossary_dogwhistles"] > 0, pd.NA)
    coverage["type_coverage"] = coverage["distinct_types_found"] / coverage[
        "total_glossary_types"
    ].where(coverage["total_glossary_types"] > 0, pd.NA)

    target_posts = _build_target_posts(dataset_filter, include_taxonomy_level)
    tc_keys = [k for k in group_keys if k != "coding_level"]
    if target_posts.empty:
        tc = glossary_totals[tc_keys].copy()
        tc["total_target_group_posts"] = 0
    else:
        tc = (
            target_posts.groupby(tc_keys, as_index=False)
            .agg(total_target_group_posts=("text_dedup_key", "nunique"))
            .sort_values(tc_keys)
        )

    annotation = glossary_totals[glossary_group_keys + ["is_self_referential"]].merge(
        ab, on=glossary_group_keys, how="left"
    )
    annotation = annotation.merge(tc, on=tc_keys, how="left")
    for c in [
        "case_a_present_hateful",
        "case_b_present_nonhateful",
        "total_matches",
        "total_target_group_posts",
    ]:
        annotation[c] = annotation[c].fillna(0).astype(int)

    annotation["case_c_absent"] = (
        annotation["total_target_group_posts"] - annotation["total_matches"]
    ).clip(lower=0)

    ab_sum = (
        annotation["case_a_present_hateful"] + annotation["case_b_present_nonhateful"]
    )
    annotation["correct_labeling_rate"] = annotation[
        "case_a_present_hateful"
    ] / ab_sum.where(ab_sum > 0, pd.NA)
    annotation["failure_rate"] = annotation["case_b_present_nonhateful"] / ab_sum.where(
        ab_sum > 0, pd.NA
    )
    annotation["stable_n"] = annotation["total_matches"] >= N_MIN
    # case_b (posts) and case_c (terms) are different units; their sum is not
    # meaningful.  Preserve the column for schema compatibility but leave it NA.
    annotation["case_b_c_ratio"] = pd.NA

    merged = coverage.merge(
        annotation[
            group_keys + ["correct_labeling_rate", "failure_rate", "total_matches"]
        ],
        on=group_keys,
        how="left",
    )

    if include_taxonomy_level:
        # Pairwise within each taxonomy_level + coding_level + report_level partition.
        pair_rows = []
        for (taxonomy_level, coding_level, report_level), grp in merged.groupby(
            ["taxonomy_level", "coding_level", "report_level"]
        ):
            r = build_pairwise_rows(
                group_df=grp.assign(
                    _pair_level=f"{taxonomy_level}||{coding_level}||{report_level}"
                ),
                presence_col="presence_rate",
                type_cov_col="type_coverage",
                labeling_col="correct_labeling_rate",
                failure_col="failure_rate",
                matches_col="total_matches",
                level_col="_pair_level",
                target_col="report_target",
                n_min=N_MIN,
            )
            for row in r:
                row["taxonomy_level"] = taxonomy_level
                row["coding_level"] = coding_level
                row["report_level"] = report_level
            pair_rows.extend(r)
        pairwise = pd.DataFrame(pair_rows)
        if not pairwise.empty:
            pairwise = pairwise.drop(columns=["_pair_level"], errors="ignore")
    else:
        pair_rows = []
        for (coding_level, report_level), grp in merged.groupby(
            ["coding_level", "report_level"]
        ):
            r = build_pairwise_rows(
                group_df=grp.assign(_pair_key=f"{coding_level}||{report_level}"),
                presence_col="presence_rate",
                type_cov_col="type_coverage",
                labeling_col="correct_labeling_rate",
                failure_col="failure_rate",
                matches_col="total_matches",
                level_col="_pair_key",
                target_col="report_target",
                n_min=N_MIN,
            )
            for row in r:
                row["coding_level"] = coding_level
                row["report_level"] = report_level
            pair_rows.extend(r)
        pairwise = pd.DataFrame(pair_rows)
        if not pairwise.empty:
            pairwise = pairwise.drop(columns=["_pair_key"], errors="ignore")

    return (
        coverage.sort_values(group_keys),
        annotation.sort_values(group_keys),
        pairwise,
    )


def _build_pass_fail(
    pairwise: pd.DataFrame, coverage: pd.DataFrame, annotation: pd.DataFrame
) -> pd.DataFrame:
    """Summarise four-fifths outcomes per reporting group.

    The worst stable pair touching each reporting target is retained as the
    explanatory note so the summary table stays interpretable.
    """
    keys = ["coding_level", "report_level", "report_target"]
    base = coverage[keys].drop_duplicates().copy()

    rows = []
    for _, row in base.iterrows():
        cl, rl, rt = row["coding_level"], row["report_level"], row["report_target"]

        stable_cov = pairwise[
            (pairwise["coding_level"] == cl)
            & (pairwise["report_level"] == rl)
            & (~pairwise["unstable_small_n"])
            & ((pairwise["target_a"] == rt) | (pairwise["target_b"] == rt))
        ]

        if stable_cov.empty:
            worst_cov = pd.NA
            worst_ann = pd.NA
            pass_cov = pd.NA
            pass_ann = pd.NA
            unstable_any = True
            worst_cov_note = "no_stable_pairs"
            worst_ann_note = "no_stable_pairs"
        else:
            worst_cov = stable_cov["worst_di_ratio"].min()
            worst_ann = stable_cov["annotation_di_ratio"].min()
            pass_cov = bool(pd.notna(worst_cov) and worst_cov >= DI_THRESHOLD)
            pass_ann = bool(pd.notna(worst_ann) and worst_ann >= DI_THRESHOLD)
            unstable_any = bool(
                pairwise[
                    (pairwise["coding_level"] == cl)
                    & (pairwise["report_level"] == rl)
                    & ((pairwise["target_a"] == rt) | (pairwise["target_b"] == rt))
                ]["unstable_small_n"].any()
            )
            wc = stable_cov.sort_values("worst_di_ratio", ascending=True).iloc[0]
            wa = stable_cov.sort_values("annotation_di_ratio", ascending=True).iloc[0]
            worst_cov_note = f"{wc['target_a']} vs {wc['target_b']}"
            worst_ann_note = f"{wa['target_a']} vs {wa['target_b']}"

        rows.append(
            {
                "coding_level": cl,
                "report_level": rl,
                "report_target": rt,
                "worst_pairwise_coverage_di_ratio": worst_cov,
                "worst_pairwise_annotation_di_ratio": worst_ann,
                "passes_four_fifths_coverage": pass_cov,
                "passes_four_fifths_annotation": pass_ann,
                "unstable_small_n_any": unstable_any,
                "worst_coverage_pair_note": worst_cov_note,
                "worst_annotation_pair_note": worst_ann_note,
            }
        )

    out = pd.DataFrame(rows).sort_values(keys)
    out = out.merge(
        annotation[["coding_level", "report_level", "report_target", "total_matches"]],
        on=["coding_level", "report_level", "report_target"],
        how="left",
    )
    return out


def run(variant: PipelineVariant = VARIANT_FULL) -> None:
    """Generate Stage 4 rollups for union, by-level, and ElSherief slices.

    Parameters
    ----------
    variant : PipelineVariant
        Controls where stage-1 inputs are read from (``variant.out_s1``),
        which glossary tiers seed the denominators (``variant.allowed_tiers``),
        and where stage-4 outputs are written (``variant.out_s4``).
    """
    by_group_dir = variant.out_s4 / "by_group"
    by_level_group_dir = variant.out_s4 / "by_level_group"
    els_dir = variant.out_s4 / "elsherief"
    ensure_dirs(by_group_dir, by_level_group_dir, els_dir)

    # 4a collapsed-by-group (union).
    cov_a, ann_a, pair_a = compute_rollup(
        dataset_filter=None,
        include_taxonomy_level=False,
        s1_dir=variant.out_s1,
        allowed_tiers=variant.allowed_tiers,
    )
    pass_fail = _build_pass_fail(pair_a, cov_a, ann_a)

    write_tsv(cov_a, by_group_dir / "s4a_coverage_by_group.tsv")
    write_tsv(ann_a, by_group_dir / "s4a_annotation_by_group.tsv")
    write_tsv(pair_a, by_group_dir / "s4a_pairwise_disparity_by_group.tsv")
    write_tsv(pass_fail, by_group_dir / "s4a_pass_fail_summary.tsv")

    # 4b by-level-group (union).
    cov_b, ann_b, pair_b = compute_rollup(
        dataset_filter=None,
        include_taxonomy_level=True,
        s1_dir=variant.out_s1,
        allowed_tiers=variant.allowed_tiers,
    )
    write_tsv(cov_b, by_level_group_dir / "s4b_coverage_by_level_group.tsv")
    write_tsv(ann_b, by_level_group_dir / "s4b_annotation_by_level_group.tsv")
    write_tsv(pair_b, by_level_group_dir / "s4b_pairwise_disparity_by_level_group.tsv")

    # 4c ElSherief deltas. The primary corpus (DATA_PATH / variant.out_s1)
    # excludes ElSherief entirely -- see 04_union_and_dedup.ipynb's
    # include_elsherief config -- so it has no ElSherief rows to filter for.
    # This one call is instead pointed at the ElSherief-inclusive corpus
    # built by `python -m audit_pipeline.build_elsherief_comparison_data`,
    # via a scoped swap of the module-level DATA_PATH that
    # _dataset_row_count/_build_target_posts read internally. Restored
    # immediately after so every other call in this function (and every
    # other stage) keeps using the primary, ElSherief-excluded corpus.
    #
    # Only wired up for the all-tier scope: OUT_S1_WITH_ELSHERIEF was built
    # with allowed_tiers=None (matching VARIANT_FULL), so pairing it with a
    # tier-restricted glossary denominator (e.g. VARIANT_TIER12) would mix
    # all-tier matches with a tier-1+2-only denominator -- the same
    # inconsistency this module's docstring warns against for Stage 1/4
    # tier filtering generally. The paper's Section 5.4 / Appendix G
    # ElSherief comparison is only ever reported at the primary (all-tier)
    # scope, so other variants keep the prior (empty/NaN) behavior rather
    # than a silently tier-mismatched one.
    # The "union" side of *this* comparison is not cov_a/ann_a/pair_a above
    # (the primary, two-way HateXplain+MHS union used for s4a/s4b) -- per
    # Figure 4/6's caption ("Effect of adding HateXplain and MHS to the
    # Implicit Hate corpus"), it has to be the three-way union (HateXplain+
    # MHS+ElSherief). That's dataset_filter=None against the ElSherief-
    # inclusive corpus, computed here as cov_a3/ann_a3/pair_a3 -- a separate
    # call from cov_a/ann_a/pair_a, which must keep meaning the primary
    # two-way union for every other output this function writes.
    if variant.allowed_tiers is None:
        global DATA_PATH
        _primary_data_path = DATA_PATH
        DATA_PATH = DATA_PATH_WITH_ELSHERIEF
        try:
            cov_a3, ann_a3, pair_a3 = compute_rollup(
                dataset_filter=None,
                include_taxonomy_level=False,
                s1_dir=OUT_S1_WITH_ELSHERIEF,
                allowed_tiers=variant.allowed_tiers,
            )
            cov_e, ann_e, pair_e = compute_rollup(
                dataset_filter=ELSHERIEF_DATASET_NAME,
                include_taxonomy_level=False,
                s1_dir=OUT_S1_WITH_ELSHERIEF,
                allowed_tiers=variant.allowed_tiers,
            )
        finally:
            DATA_PATH = _primary_data_path
    else:
        # Guarded off (see note above) -- no ElSherief-inclusive Stage 1
        # output exists at this tier scope, so both sides stay on the
        # primary corpus and the merge below still yields the prior
        # (empty/NaN) result rather than a tier-mismatched one.
        cov_a3, ann_a3, pair_a3 = cov_a, ann_a, pair_a
        cov_e, ann_e, pair_e = compute_rollup(
            dataset_filter=ELSHERIEF_DATASET_NAME,
            include_taxonomy_level=False,
            s1_dir=variant.out_s1,
            allowed_tiers=variant.allowed_tiers,
        )

    cov_d = cov_a3.merge(
        cov_e,
        on=["coding_level", "report_level", "report_target"],
        how="outer",
        suffixes=("_union", "_elsherief"),
    )
    cov_d["presence_rate_delta_union_minus_elsherief"] = (
        cov_d["presence_rate_union"] - cov_d["presence_rate_elsherief"]
    )
    cov_d["type_coverage_delta_union_minus_elsherief"] = (
        cov_d["type_coverage_union"] - cov_d["type_coverage_elsherief"]
    )

    ann_d = ann_a3.merge(
        ann_e,
        on=["coding_level", "report_level", "report_target"],
        how="outer",
        suffixes=("_union", "_elsherief"),
    )
    ann_d["correct_labeling_rate_delta_union_minus_elsherief"] = (
        ann_d["correct_labeling_rate_union"] - ann_d["correct_labeling_rate_elsherief"]
    )
    ann_d["failure_rate_delta_union_minus_elsherief"] = (
        ann_d["failure_rate_union"] - ann_d["failure_rate_elsherief"]
    )

    pair_d = pair_a3.merge(
        pair_e,
        on=["coding_level", "report_level", "target_a", "target_b"],
        how="outer",
        suffixes=("_union", "_elsherief"),
    )
    pair_d["worst_di_ratio_delta_union_minus_elsherief"] = (
        pair_d["worst_di_ratio_union"] - pair_d["worst_di_ratio_elsherief"]
    )
    pair_d["label_gap_abs_delta_union_minus_elsherief"] = (
        pair_d["labeling_rate_gap_abs_union"]
        - pair_d["labeling_rate_gap_abs_elsherief"]
    )

    write_tsv(cov_d, els_dir / "s4c_coverage_delta_union_vs_elsherief.tsv")
    write_tsv(ann_d, els_dir / "s4c_annotation_delta_union_vs_elsherief.tsv")
    write_tsv(pair_d, els_dir / "s4c_pairwise_delta_union_vs_elsherief.tsv")

    print(f"[Stage 4 – {variant.name}] Rollup complete")
    print(
        f"  wrote {len(cov_a):,} rows -> {by_group_dir / 's4a_coverage_by_group.tsv'}"
    )
    print(
        f"  wrote {len(ann_a):,} rows -> {by_group_dir / 's4a_annotation_by_group.tsv'}"
    )
    print(
        f"  wrote {len(pair_a):,} rows -> {by_group_dir / 's4a_pairwise_disparity_by_group.tsv'}"
    )
    print(
        f"  wrote {len(pass_fail):,} rows -> {by_group_dir / 's4a_pass_fail_summary.tsv'}"
    )
    print(
        f"  wrote {len(cov_b):,} rows -> {by_level_group_dir / 's4b_coverage_by_level_group.tsv'}"
    )
    print(
        f"  wrote {len(ann_b):,} rows -> {by_level_group_dir / 's4b_annotation_by_level_group.tsv'}"
    )
    print(
        f"  wrote {len(pair_b):,} rows -> {by_level_group_dir / 's4b_pairwise_disparity_by_level_group.tsv'}"
    )
    print(
        f"  wrote {len(cov_d):,} rows -> {els_dir / 's4c_coverage_delta_union_vs_elsherief.tsv'}"
    )
    print(
        f"  wrote {len(ann_d):,} rows -> {els_dir / 's4c_annotation_delta_union_vs_elsherief.tsv'}"
    )
    print(
        f"  wrote {len(pair_d):,} rows -> {els_dir / 's4c_pairwise_delta_union_vs_elsherief.tsv'}"
    )


if __name__ == "__main__":
    run(resolve_variant())
