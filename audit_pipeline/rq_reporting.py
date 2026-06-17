"""RQ reporting: compute and write all research-question outputs.

Reads directly from the data-preprocessing outputs
(``outputs/unioned_data/06_cleaned_labels_glossary_mapped.tsv`` and
``06_glossary_label_reference.tsv``) and writes figures, tables, and appendix
deltas under ``outputs/rq_reporting/``.

Can be run standalone::

    python -m audit_pipeline.rq_reporting

or as the final step via ``audit_pipeline/run_all.py``.

Functions shared with the rest of the audit pipeline
(``norm_target``, ``map_reporting_group``, ``add_reporting_columns``,
``ReportGroup``, ``write_tsv``) are imported from ``audit_pipeline.helpers``
to keep a single source of truth.

The following helpers are kept local because their signatures or return types
differ from the helpers.py versions in ways that would require updating all
call-sites throughout this module:

* ``safe_float`` / ``safe_di_ratio`` — return ``pd.NA`` (not NaN) so
  downstream ``pd.notna`` checks work correctly on Series.
* ``parse_list_like`` — handles only Python-list-literal form; the helpers.py
  version adds semicolon splitting that is not needed here.
* ``ensure_dirs`` — takes ``Iterable[Path]`` rather than ``*args``; all
  call-sites pass a list literal.
"""

from __future__ import annotations

import ast
import itertools
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import pandas as pd

from audit_pipeline.helpers import (
    ReportGroup,
    add_reporting_columns,
    map_reporting_group,
    norm_target,
    write_tsv,
)

WORKDIR = Path(__file__).resolve().parents[1]
OUTPUTS = WORKDIR / "outputs"
N_MIN = 30
DI_THRESHOLD = 0.8


# ---------------------------------------------------------------------------
# Local helpers (see module docstring for why these are not imported)
# ---------------------------------------------------------------------------

def safe_float(value: object) -> float:
    if pd.isna(value):
        return float("nan")
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def safe_di_ratio(a: float, b: float) -> float | pd._libs.missing.NAType:
    if pd.isna(a) or pd.isna(b):
        return pd.NA
    high = max(a, b)
    low = min(a, b)
    if high <= 0:
        return pd.NA
    return low / high


def parse_list_like(value: object) -> list[str]:
    if value is None:
        return []
    s = str(value).strip()
    if s == "" or s == "[]":
        return []
    try:
        parsed = ast.literal_eval(s)
    except Exception:
        return []
    if isinstance(parsed, list):
        return [str(x) for x in parsed]
    return []


def ensure_dirs(paths: Iterable[Path]) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Pairwise disparity builder (rq_reporting-specific; not in helpers.py)
# ---------------------------------------------------------------------------

def build_pairwise_disparity(
    coverage_agg: pd.DataFrame, annotation_agg: pd.DataFrame
) -> pd.DataFrame:
    merged = coverage_agg.merge(
        annotation_agg[
            [
                "report_level",
                "report_target",
                "correct_labeling_rate",
                "failure_rate",
                "total_matches",
            ]
        ],
        on=["report_level", "report_target"],
        how="left",
    )

    rows: list[dict[str, object]] = []
    for level, level_df in merged.groupby("report_level"):
        recs = level_df.to_dict("records")
        for a, b in itertools.combinations(recs, 2):
            pr_a, pr_b = safe_float(a["presence_rate"]), safe_float(b["presence_rate"])
            tc_a, tc_b = safe_float(a["type_coverage"]), safe_float(b["type_coverage"])
            cl_a, cl_b = (
                safe_float(a["correct_labeling_rate"]),
                safe_float(b["correct_labeling_rate"]),
            )
            fr_a, fr_b = safe_float(a["failure_rate"]), safe_float(b["failure_rate"])

            pr_di = safe_di_ratio(pr_a, pr_b)
            tc_di = safe_di_ratio(tc_a, tc_b)
            worst_di = (
                min(pr_di, tc_di) if pd.notna(pr_di) and pd.notna(tc_di) else pd.NA
            )
            annotation_di = safe_di_ratio(cl_a, cl_b)

            n_a = int(a["total_matches"])
            n_b = int(b["total_matches"])
            unstable_small_n = (n_a < N_MIN) or (n_b < N_MIN)

            rows.append(
                {
                    "report_level": level,
                    "target_a": a["report_target"],
                    "target_b": b["report_target"],
                    "presence_rate_a": pr_a,
                    "presence_rate_b": pr_b,
                    "presence_rate_di_ratio": pr_di,
                    "type_coverage_a": tc_a,
                    "type_coverage_b": tc_b,
                    "type_coverage_di_ratio": tc_di,
                    "worst_di_ratio": worst_di,
                    "annotation_di_ratio": annotation_di,
                    "correct_labeling_rate_a": cl_a,
                    "correct_labeling_rate_b": cl_b,
                    "labeling_rate_gap": cl_a - cl_b,
                    "labeling_rate_gap_abs": abs(cl_a - cl_b),
                    "failure_rate_a": fr_a,
                    "failure_rate_b": fr_b,
                    "failure_rate_gap": fr_a - fr_b,
                    "failure_rate_gap_abs": abs(fr_a - fr_b),
                    "total_matches_a": n_a,
                    "total_matches_b": n_b,
                    "unstable_small_n": unstable_small_n,
                    "small_n_reason": (
                        f"either_side_matched_posts<{N_MIN}" if unstable_small_n else ""
                    ),
                }
            )

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Plot helpers
# ---------------------------------------------------------------------------

def filter_disability_unspecific_for_plots(df: pd.DataFrame) -> pd.DataFrame:
    keep = (df["report_level"] != "disability") | (df["report_target"] == "unspecific")
    return df[keep].copy()


def make_rq1_plots(coverage_agg: pd.DataFrame, base_dir: Path) -> None:
    main_dir = base_dir / "rq1" / "main"
    appendix_dir = base_dir / "rq1" / "appendix"
    ensure_dirs([main_dir, appendix_dir])

    cov_main = coverage_agg.copy()

    fig, ax = plt.subplots(figsize=(10, 6))
    for level, level_df in cov_main.groupby("report_level"):
        ax.scatter(
            level_df["presence_rate"],
            level_df["type_coverage"],
            label=level,
            s=55,
            alpha=0.85,
        )
    ax.set_xlabel("Presence Rate")
    ax.set_ylabel("Type Coverage")
    ax.set_title("RQ1 Main: Presence Rate vs Type Coverage")
    ax.set_xlim(0, 1.02)
    ax.set_ylim(0, 1.02)
    ax.grid(alpha=0.25)
    ax.legend(title="Group level", fontsize=8)
    fig.tight_layout()
    fig.savefig(main_dir / "rq1_presence_vs_type_collapsed.png", dpi=180)
    plt.close(fig)

    freq = coverage_agg.sort_values("token_frequency", ascending=False)
    top = freq.head(20).copy()
    top["label"] = top["report_level"] + ": " + top["report_target"]

    fig, ax = plt.subplots(figsize=(12, 7))
    ax.barh(top["label"], top["token_frequency"], color="#516B8B")
    ax.set_title("RQ1 Appendix: Top-20 Token Frequency")
    ax.set_xlabel("Token Frequency")
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(appendix_dir / "rq1_token_frequency_top20.png", dpi=180)
    plt.close(fig)


def make_rq2_outputs(annotation_agg: pd.DataFrame, base_dir: Path) -> None:
    main_dir = base_dir / "rq2" / "main"
    supporting_dir = base_dir / "rq2" / "supporting"
    table_dir = base_dir / "rq2" / "tables"
    ensure_dirs([main_dir, supporting_dir, table_dir])

    ann_main = annotation_agg.copy()
    ann_main = filter_disability_unspecific_for_plots(ann_main)
    ann_main = ann_main.sort_values("correct_labeling_rate", ascending=False)
    ann_main["label"] = ann_main["report_level"] + ": " + ann_main["report_target"]

    fig, ax = plt.subplots(figsize=(12, 7))
    x = range(len(ann_main))
    ax.bar(
        x, ann_main["correct_labeling_rate"], width=0.45, label="Correct (Case A/(A+B))"
    )
    ax.bar(
        [i + 0.45 for i in x],
        ann_main["failure_rate"],
        width=0.45,
        label="Failure (Case B/(A+B))",
    )
    ax.set_xticks([i + 0.225 for i in x])
    ax.set_xticklabels(ann_main["label"], rotation=60, ha="right")
    ax.set_ylim(0, 1.02)
    ax.set_ylabel("Rate")
    ax.set_title("RQ2 Main: Correct vs Failure Rates")
    ax.legend()
    fig.text(
        0.01,
        0.01,
        "Note: Disability panel shows only 'unspecific'; other disability subgroups had matched_posts < 30.",
        ha="left",
        va="bottom",
        fontsize=9,
    )
    fig.tight_layout()
    fig.savefig(main_dir / "rq2_correct_vs_failure_rates.png", dpi=180)
    plt.close(fig)

    support = (
        ann_main.sort_values("case_b_present_nonhateful", ascending=False)
        .head(20)
        .copy()
    )
    fig, ax = plt.subplots(figsize=(12, 7))
    x = range(len(support))
    ax.bar(x, support["case_a_present_hateful"], label="Case A", color="#2E8B57")
    ax.bar(
        x,
        support["case_b_present_nonhateful"],
        bottom=support["case_a_present_hateful"],
        label="Case B",
        color="#C45B5B",
    )
    ax.set_xticks(list(x))
    ax.set_xticklabels(support["label"], rotation=60, ha="right")
    ax.set_ylabel("Matched Posts")
    ax.set_title("RQ2 Supporting: Case A/B Counts (Top 20 by Case B)")
    ax.legend()
    fig.text(
        0.01,
        0.01,
        "Note: Disability panel shows only 'unspecific'; other disability subgroups had matched_posts < 30.",
        ha="left",
        va="bottom",
        fontsize=9,
    )
    fig.tight_layout()
    fig.savefig(supporting_dir / "rq2_case_ab_counts_top20.png", dpi=180)
    plt.close(fig)

    rq2_table = annotation_agg[
        [
            "report_level",
            "report_target",
            "case_a_present_hateful",
            "case_b_present_nonhateful",
            "failure_rate",
            "total_matches",
            "stable_n",
            "unstable_small_n",
            "small_n_reason",
        ]
    ].copy()
    rq2_table = rq2_table.rename(columns={"failure_rate": "case_b_over_a_plus_b_ratio"})
    write_tsv(rq2_table, table_dir / "rq2_case_b_over_a_plus_b_by_group.tsv")


def make_rq3_outputs(
    pairwise: pd.DataFrame,
    base_dir: Path,
) -> pd.DataFrame:
    main_dir = base_dir / "rq3" / "main"
    supporting_dir = base_dir / "rq3" / "supporting"
    table_dir = base_dir / "rq3" / "tables"
    ensure_dirs([main_dir, supporting_dir, table_dir])

    pair_main = pairwise.copy()

    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
    axes[0].hist(
        pair_main["presence_rate_di_ratio"].dropna(),
        bins=20,
        color="#4C72B0",
        alpha=0.85,
    )
    axes[0].axvline(DI_THRESHOLD, color="red", linestyle="--", linewidth=1.2)
    axes[0].set_title("Presence DI Ratio")
    axes[0].set_xlabel("DI Ratio")
    axes[0].set_ylabel("Count")

    axes[1].hist(
        pair_main["type_coverage_di_ratio"].dropna(),
        bins=20,
        color="#55A868",
        alpha=0.85,
    )
    axes[1].axvline(DI_THRESHOLD, color="red", linestyle="--", linewidth=1.2)
    axes[1].set_title("Type-Coverage DI Ratio")
    axes[1].set_xlabel("DI Ratio")
    fig.suptitle("RQ3 Main: DI Ratio Histograms (4/5 Rule)")
    fig.tight_layout()
    fig.savefig(main_dir / "rq3_di_ratio_histograms.png", dpi=180)
    plt.close(fig)

    worst = pair_main.sort_values("worst_di_ratio", ascending=True).head(20).copy()
    worst["pair"] = (
        worst["report_level"] + ": " + worst["target_a"] + " vs " + worst["target_b"]
    )

    gap = (
        pair_main.sort_values("labeling_rate_gap_abs", ascending=False).head(20).copy()
    )
    gap["pair"] = (
        gap["report_level"] + ": " + gap["target_a"] + " vs " + gap["target_b"]
    )

    fig, axes = plt.subplots(1, 2, figsize=(16, 7))
    axes[0].barh(worst["pair"], worst["worst_di_ratio"], color="#C45B5B")
    axes[0].axvline(DI_THRESHOLD, color="black", linestyle="--", linewidth=1.0)
    axes[0].set_title("Worst Pairwise DI Ratios")
    axes[0].set_xlabel("Worst DI Ratio")
    axes[0].invert_yaxis()

    axes[1].barh(gap["pair"], gap["labeling_rate_gap_abs"], color="#6C9D5E")
    axes[1].set_title("Largest Absolute Label Gaps")
    axes[1].set_xlabel("|Correct Labeling Rate Gap|")
    axes[1].invert_yaxis()
    fig.suptitle("RQ3 Supporting: Worst DI + Label Gap")
    fig.tight_layout()
    fig.savefig(supporting_dir / "rq3_worst_di_and_label_gap_two_panel.png", dpi=180)
    plt.close(fig)

    all_involved = pd.concat(
        [
            pairwise[
                ["report_level", "target_a", "worst_di_ratio", "unstable_small_n"]
            ].rename(columns={"target_a": "report_target"}),
            pairwise[
                ["report_level", "target_b", "worst_di_ratio", "unstable_small_n"]
            ].rename(columns={"target_b": "report_target"}),
        ],
        ignore_index=True,
    )

    all_groups = (
        all_involved[["report_level", "report_target"]]
        .drop_duplicates()
        .sort_values(["report_level", "report_target"])
    )

    unstable_any = (
        all_involved.groupby(["report_level", "report_target"], as_index=False)
        .agg(unstable_small_n_any=("unstable_small_n", "max"))
        .sort_values(["report_level", "report_target"])
    )

    stable_pairs = pairwise[~pairwise["unstable_small_n"]].copy()

    stable_cov_involved = pd.concat(
        [
            stable_pairs[["report_level", "target_a", "worst_di_ratio"]].rename(
                columns={"target_a": "report_target"}
            ),
            stable_pairs[["report_level", "target_b", "worst_di_ratio"]].rename(
                columns={"target_b": "report_target"}
            ),
        ],
        ignore_index=True,
    )

    cov_summary = (
        stable_cov_involved.groupby(["report_level", "report_target"], as_index=False)
        .agg(
            worst_pairwise_coverage_di_ratio=("worst_di_ratio", "min"),
        )
        .sort_values(["report_level", "report_target"])
    )

    anno_involved = pd.concat(
        [
            stable_pairs[["report_level", "target_a", "annotation_di_ratio"]].rename(
                columns={"target_a": "report_target"}
            ),
            stable_pairs[["report_level", "target_b", "annotation_di_ratio"]].rename(
                columns={"target_b": "report_target"}
            ),
        ],
        ignore_index=True,
    )
    anno_summary = (
        anno_involved.groupby(["report_level", "report_target"], as_index=False)
        .agg(worst_pairwise_annotation_di_ratio=("annotation_di_ratio", "min"))
        .sort_values(["report_level", "report_target"])
    )
    pass_fail = all_groups.merge(
        cov_summary, on=["report_level", "report_target"], how="left"
    )
    pass_fail = pass_fail.merge(
        anno_summary, on=["report_level", "report_target"], how="left"
    )
    pass_fail = pass_fail.merge(
        unstable_any, on=["report_level", "report_target"], how="left"
    )
    pass_fail["unstable_small_n_any"] = pass_fail["unstable_small_n_any"].fillna(False)
    pass_fail["unstable_all_coverage_pairs"] = pass_fail[
        "worst_pairwise_coverage_di_ratio"
    ].isna()
    pass_fail["unstable_all_annotation_pairs"] = pass_fail[
        "worst_pairwise_annotation_di_ratio"
    ].isna()
    pass_fail["passes_four_fifths_coverage"] = pass_fail[
        "worst_pairwise_coverage_di_ratio"
    ].apply(lambda v: pd.NA if pd.isna(v) else v >= DI_THRESHOLD)
    pass_fail["passes_four_fifths_annotation"] = pass_fail[
        "worst_pairwise_annotation_di_ratio"
    ].apply(lambda v: pd.NA if pd.isna(v) else v >= DI_THRESHOLD)

    worst_pair_note = stable_pairs.copy()
    if not worst_pair_note.empty:
        worst_pair_note["pair"] = (
            worst_pair_note["target_a"] + " vs " + worst_pair_note["target_b"]
        )

    coverage_notes: list[str] = []
    annotation_notes: list[str] = []
    for _, row in pass_fail.iterrows():
        if worst_pair_note.empty:
            coverage_notes.append("")
            annotation_notes.append("")
            continue

        cand = worst_pair_note[
            (worst_pair_note["report_level"] == row["report_level"])
            & (
                (worst_pair_note["target_a"] == row["report_target"])
                | (worst_pair_note["target_b"] == row["report_target"])
            )
        ]
        if cand.empty:
            coverage_notes.append("")
            annotation_notes.append("")
        else:
            coverage_notes.append(
                cand.sort_values("worst_di_ratio", ascending=True).iloc[0]["pair"]
            )
            annotation_notes.append(
                cand.sort_values("annotation_di_ratio", ascending=True).iloc[0]["pair"]
            )

    pass_fail["worst_coverage_pair_note"] = coverage_notes
    pass_fail["worst_annotation_pair_note"] = annotation_notes
    pass_fail = pass_fail.sort_values(["report_level", "report_target"])

    write_tsv(pass_fail, table_dir / "rq3_pass_fail_summary_by_group.tsv")
    write_tsv(pairwise, table_dir / "rq3_pairwise_disparity_collapsed.tsv")

    return pass_fail


# ---------------------------------------------------------------------------
# Main metric computation
# ---------------------------------------------------------------------------

def compute_reporting_metrics_from_cleaned(
    dataset_name: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load preprocessed outputs, compute coverage/annotation/pairwise metrics.

    Pass ``dataset_name=""`` to use the full union dataset, or a lowercase
    dataset name (e.g. ``"elsherief"``) to filter to a single source.
    """
    cleaned = pd.read_csv(
        OUTPUTS / "unioned_data" / "06_cleaned_labels_glossary_mapped.tsv",
        sep="\t",
        low_memory=False,
    )
    glossary_ref = pd.read_csv(
        OUTPUTS / "unioned_data" / "06_glossary_label_reference.tsv", sep="\t"
    )

    if dataset_name:
        cleaned = cleaned[
            cleaned["dataset"].astype(str).str.lower() == dataset_name.lower()
        ].copy()

    glossary_ref = add_reporting_columns(glossary_ref, "taxonomy_level", "target")
    glossary_ref = glossary_ref[glossary_ref["report_include"]].copy()

    ref_grouped = glossary_ref.groupby("dogwhistle")

    hit_rows: list[dict[str, object]] = []
    target_rows: list[dict[str, object]] = []

    for _, row in cleaned.iterrows():
        key = str(row.get("text_dedup_key", ""))
        if key == "":
            continue

        binary_hate = (
            int(row.get("binary_hate", 0)) if pd.notna(row.get("binary_hate")) else 0
        )

        matched_terms = set(parse_list_like(row.get("matched_glossary_terms")))
        for term in matched_terms:
            if term not in ref_grouped.groups:
                continue
            ref_rows = ref_grouped.get_group(term)
            for _, rr in ref_rows.iterrows():
                hit_rows.append(
                    {
                        "text_dedup_key": key,
                        "binary_hate": binary_hate,
                        "dogwhistle": term,
                        "type": rr["type"],
                        "report_level": rr["report_level"],
                        "report_target": rr["report_target"],
                    }
                )

        cleaned_labels = parse_list_like(row.get("cleaned_label"))
        mapped_groups = set()
        for label in cleaned_labels:
            label_n = norm_target(label)
            if " " not in label_n:
                continue
            level, target = label_n.split(" ", 1)
            g = map_reporting_group(level, target)
            if g.include:
                mapped_groups.add((g.report_level, g.report_target))
        for rl, rt in mapped_groups:
            target_rows.append(
                {"text_dedup_key": key, "report_level": rl, "report_target": rt}
            )

    hits = pd.DataFrame(hit_rows)
    if not hits.empty:
        hits = hits.drop_duplicates(
            subset=["text_dedup_key", "dogwhistle", "report_level", "report_target"]
        )

    target_posts = pd.DataFrame(target_rows)
    if not target_posts.empty:
        target_posts = target_posts.drop_duplicates(
            subset=["text_dedup_key", "report_level", "report_target"]
        )

    glossary_totals = (
        glossary_ref.groupby(["report_level", "report_target"], as_index=False)
        .agg(
            total_glossary_dogwhistles=("dogwhistle", "nunique"),
            total_glossary_types=("type", "nunique"),
        )
        .sort_values(["report_level", "report_target"])
    )

    if hits.empty:
        coverage = glossary_totals.copy()
        coverage["distinct_dogwhistles_found"] = 0
        coverage["distinct_types_found"] = 0
        coverage["token_frequency"] = 0
    else:
        found = (
            hits.groupby(["report_level", "report_target"], as_index=False)
            .agg(
                distinct_dogwhistles_found=("dogwhistle", "nunique"),
                distinct_types_found=("type", "nunique"),
                token_frequency=("dogwhistle", "count"),
            )
            .sort_values(["report_level", "report_target"])
        )
        coverage = glossary_totals.merge(
            found, on=["report_level", "report_target"], how="left"
        )
        coverage[
            ["distinct_dogwhistles_found", "distinct_types_found", "token_frequency"]
        ] = coverage[
            ["distinct_dogwhistles_found", "distinct_types_found", "token_frequency"]
        ].fillna(0)

    coverage["presence_rate"] = coverage["distinct_dogwhistles_found"] / coverage[
        "total_glossary_dogwhistles"
    ].where(coverage["total_glossary_dogwhistles"] > 0, pd.NA)
    coverage["type_coverage"] = coverage["distinct_types_found"] / coverage[
        "total_glossary_types"
    ].where(coverage["total_glossary_types"] > 0, pd.NA)

    if hits.empty:
        annotation = glossary_totals[["report_level", "report_target"]].copy()
        annotation["case_a_present_hateful"] = 0
        annotation["case_b_present_nonhateful"] = 0
        annotation["total_matches"] = 0
    else:
        annotation = (
            hits.groupby(["report_level", "report_target"], as_index=False)
            .agg(
                case_a_present_hateful=("binary_hate", lambda s: int((s == 1).sum())),
                case_b_present_nonhateful=(
                    "binary_hate",
                    lambda s: int((s == 0).sum()),
                ),
                total_matches=("binary_hate", "count"),
            )
            .sort_values(["report_level", "report_target"])
        )

    if target_posts.empty:
        target_counts = glossary_totals[["report_level", "report_target"]].copy()
        target_counts["total_target_group_posts"] = 0
    else:
        target_counts = (
            target_posts.groupby(["report_level", "report_target"], as_index=False)
            .agg(total_target_group_posts=("text_dedup_key", "nunique"))
            .sort_values(["report_level", "report_target"])
        )

    annotation = glossary_totals[["report_level", "report_target"]].merge(
        annotation, on=["report_level", "report_target"], how="left"
    )
    annotation = annotation.merge(
        target_counts, on=["report_level", "report_target"], how="left"
    )
    annotation[
        [
            "case_a_present_hateful",
            "case_b_present_nonhateful",
            "total_matches",
            "total_target_group_posts",
        ]
    ] = annotation[
        [
            "case_a_present_hateful",
            "case_b_present_nonhateful",
            "total_matches",
            "total_target_group_posts",
        ]
    ].fillna(0)

    annotation["case_c_absent"] = (
        annotation["total_target_group_posts"] - annotation["total_matches"]
    ).clip(lower=0)
    ab = annotation["case_a_present_hateful"] + annotation["case_b_present_nonhateful"]
    annotation["correct_labeling_rate"] = annotation[
        "case_a_present_hateful"
    ] / ab.where(ab > 0, pd.NA)
    annotation["failure_rate"] = annotation["case_b_present_nonhateful"] / ab.where(
        ab > 0, pd.NA
    )
    annotation["stable_n"] = annotation["total_matches"] >= N_MIN
    annotation["unstable_small_n"] = ~annotation["stable_n"]
    annotation["small_n_reason"] = annotation["total_matches"].apply(
        lambda n: f"matched_posts<{N_MIN}" if n < N_MIN else ""
    )

    pairwise = build_pairwise_disparity(coverage, annotation)
    return coverage, annotation, pairwise


def write_appendix_deltas(
    base_dir: Path,
    primary_cov: pd.DataFrame,
    primary_ann: pd.DataFrame,
    primary_pair: pd.DataFrame,
) -> None:
    appendix_dir = base_dir / "appendix" / "elsherief"
    ensure_dirs([appendix_dir])

    els_cov, els_ann, els_pair = compute_reporting_metrics_from_cleaned("elsherief")

    cov_delta = primary_cov.merge(
        els_cov,
        on=["report_level", "report_target"],
        how="outer",
        suffixes=("_union", "_elsherief"),
    )
    cov_delta["presence_rate_delta_union_minus_elsherief"] = (
        cov_delta["presence_rate_union"] - cov_delta["presence_rate_elsherief"]
    )
    cov_delta["type_coverage_delta_union_minus_elsherief"] = (
        cov_delta["type_coverage_union"] - cov_delta["type_coverage_elsherief"]
    )
    cov_delta["token_frequency_delta_union_minus_elsherief"] = (
        cov_delta["token_frequency_union"] - cov_delta["token_frequency_elsherief"]
    )

    ann_delta = primary_ann.merge(
        els_ann,
        on=["report_level", "report_target"],
        how="outer",
        suffixes=("_union", "_elsherief"),
    )
    ann_delta["correct_labeling_rate_delta_union_minus_elsherief"] = (
        ann_delta["correct_labeling_rate_union"]
        - ann_delta["correct_labeling_rate_elsherief"]
    )
    ann_delta["failure_rate_delta_union_minus_elsherief"] = (
        ann_delta["failure_rate_union"] - ann_delta["failure_rate_elsherief"]
    )

    pair_key = ["report_level", "target_a", "target_b"]
    pair_delta = primary_pair.merge(
        els_pair,
        on=pair_key,
        how="outer",
        suffixes=("_union", "_elsherief"),
    )
    pair_delta["worst_di_ratio_delta_union_minus_elsherief"] = (
        pair_delta["worst_di_ratio_union"] - pair_delta["worst_di_ratio_elsherief"]
    )
    pair_delta["label_gap_abs_delta_union_minus_elsherief"] = (
        pair_delta["labeling_rate_gap_abs_union"]
        - pair_delta["labeling_rate_gap_abs_elsherief"]
    )

    write_tsv(cov_delta, appendix_dir / "rq1_coverage_delta_vs_union.tsv")
    write_tsv(ann_delta, appendix_dir / "rq2_annotation_delta_vs_union.tsv")
    write_tsv(pair_delta, appendix_dir / "rq3_pairwise_delta_vs_union.tsv")


def write_manifest(base_dir: Path) -> None:
    manifest = base_dir / "README.md"
    text = """# RQ Reporting Outputs

Generated by `audit_pipeline/rq_reporting.py`.

- `rq1/main`: RQ1 main figure (presence vs type coverage scatter).
- `rq1/appendix`: token frequency bars.
- `rq2/main`: correct vs failure bars. Disability displays only `unspecific`.
- `rq2/supporting`: Case A/B count bars. Disability displays only `unspecific`.
- `rq2/tables`: Case B/(A+B) by group table with small-n flags.
- `rq3/main`: DI ratio histograms with 0.8 line.
- `rq3/supporting`: combined two-panel figure (worst DI and label gap).
- `rq3/tables`: group pass/fail summary (coverage and annotation DI) and collapsed pairwise disparity table.
- `appendix/elsherief`: ElSherief replication deltas versus primary union.

Small-sample stability rule:
- Single-group estimates flagged unstable when matched posts < 30.
- Pairwise estimates flagged unstable when either side has matched posts < 30.
- RQ3 pass/fail ratios are aggregated from stable pairs only; groups with no stable pairs get `NA` for pass/fail.

Figure note applied to RQ2 plots:
- Disability panel shows only `unspecific`; remaining disability subgroups had matched posts < 30.

Delta sign convention in appendix TSVs:
- `*_delta_union_minus_elsherief = union - elsherief`.
- Negative values mean ElSherief is higher on that metric.
"""
    manifest.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    base_dir = OUTPUTS / "rq_reporting"
    ensure_dirs([base_dir])

    coverage_agg, annotation_agg, pairwise = compute_reporting_metrics_from_cleaned("")

    write_tsv(coverage_agg, base_dir / "rq1" / "tables" / "rq1_coverage_collapsed.tsv")
    write_tsv(
        annotation_agg, base_dir / "rq2" / "tables" / "rq2_annotation_collapsed.tsv"
    )

    make_rq1_plots(coverage_agg, base_dir)
    make_rq2_outputs(annotation_agg, base_dir)
    make_rq3_outputs(pairwise, base_dir)
    write_appendix_deltas(base_dir, coverage_agg, annotation_agg, pairwise)
    write_manifest(base_dir)

    print(f"Reporting outputs written to: {base_dir}")


if __name__ == "__main__":
    main()
