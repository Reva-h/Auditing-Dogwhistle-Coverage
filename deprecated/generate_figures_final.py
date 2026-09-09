#!/usr/bin/env python3
# ============================================================================
# DEPRECATED (as of 2026-07-03): DO NOT RUN THIS FILE DIRECTLY.
#
# audit_pipeline/notebooks/figures_consolidated.ipynb is now the canonical,
# permanent figure generator for this project. This file writes to the same
# output paths that notebook owns (outputs/figures_final/**), so running it
# directly will SILENTLY OVERWRITE the notebook's current styled output with
# a stale, unstyled version -- no error, no visible sign anything went wrong.
# This matters more than for a typical deprecated script: the figures this
# file produces are live, actively-used figures in the paper right now, not
# legacy dead code.
#
# Kept in the repo for reference/rollback only, not for regular use. Direct
# execution (`python generate_figures_final.py`) now requires an explicit
# opt-in -- see the `if __name__ == "__main__":` guard at the bottom of this
# file. Importing from this module (e.g.
# `from generate_figures_final import STYLE, _read, _save, apply_style`, as
# generate_fig2_annotation_di_pairwise.py does) is unaffected and continues
# to work normally.
# ============================================================================
"""
generate_figures_final.py
Publication-ready figures for the dogwhistle benchmarking audit.
ACL/EMNLP 2026 WOAH workshop submission.

Usage:
    python generate_figures_final.py [--data-dir outputs/] [--figures 1,2,3]

All figures are saved as PDF to outputs/figures_final/.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib as mpl
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, Normalize

# ── Shared style ─────────────────────────────────────────────────────────────

STYLE = {
    "title": None,
    "axis_label_fontsize": 10,
    "tick_label_fontsize": 8,
    "legend_fontsize": 8,
    "annotation_fontsize": 8,
    "panel_label_fontsize": 10,
    "colors": {
        "L2": "#E69F00",
        "L3": "#56B4E9",
        "L4": "#CC79A7",
        "correct": "#009E73",
        "failure": "#D55E00",
        "case_a": "#009E73",
        "case_b": "#D55E00",
        "presence": "#0072B2",
        "type_cov": "#56B4E9",
        "pass": "#0072B2",
        "fail": "#D55E00",
        "delta_pos": "#009E73",
        "delta_neg": "#D55E00",
        "neutral": "#999999",
    },
    "dpi": 300,
    "format": "pdf",
    "bbox_inches": "tight",
    "pad_inches": 0.05,
    "columnwidth_in": 3.35,
    "textwidth_in": 6.97,
}


def apply_style():
    """Apply ACL/EMNLP rcParams at the start of every figure function."""
    mpl.rcParams.update(
        {
            "font.size": STYLE["tick_label_fontsize"],
            "axes.labelsize": STYLE["axis_label_fontsize"],
            "xtick.labelsize": STYLE["tick_label_fontsize"],
            "ytick.labelsize": STYLE["tick_label_fontsize"],
            "legend.fontsize": STYLE["legend_fontsize"],
            "axes.spines.top": False,
            "axes.spines.right": False,
            "figure.dpi": STYLE["dpi"],
        }
    )


# ── Shared helpers ────────────────────────────────────────────────────────────


def _read(path: str | Path) -> pd.DataFrame:
    """Read a TSV file; return empty DataFrame with a warning if missing."""
    p = Path(path)
    if not p.exists():
        print(f"WARNING: Missing file {p}")
        return pd.DataFrame()
    return pd.read_csv(p, sep="\t", low_memory=False)


def _need(paths: list[str | Path], fig_name: str) -> bool:
    """Return True iff every path exists; print warnings for any missing."""
    missing = [p for p in paths if not Path(p).exists()]
    for m in missing:
        print(f"WARNING: Skipping {fig_name}: missing {m}")
    return len(missing) == 0


def _save(fig: plt.Figure, path: str | Path) -> None:
    """Save figure as PDF with ACL standard settings, then close.

    Calls tight_layout only for figures that do NOT use constrained_layout
    (constrained_layout handles its own spacing; calling tight_layout on top
    of it overrides it and breaks legend placement).
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not fig.get_constrained_layout():
        # fig1 uses manual add_axes; tight_layout skips incompatible axes silently
        try:
            fig.tight_layout(pad=0.4)
        except Exception:
            pass
    fig.savefig(str(p), format="pdf", bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)
    print(f"Generated: {p}")


def _panel_label(ax: plt.Axes, label: str, color: str) -> None:
    """Place a level label (L2 / L3 / L4) just above the upper-left corner."""
    ax.text(
        0.03,
        1.01,
        label,
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=STYLE["panel_label_fontsize"],
        fontweight="bold",
        color=color,
        clip_on=False,
    )


# ── Figure 1 — Coverage heatmap ───────────────────────────────────────────────


def fig1_coverage_heatmap(data_dir: str = "outputs/") -> None:
    """
    Heatmap of dogwhistle presence_rate for each (reporting group × coding level).

    Source files:
    - stage1/s1_coverage_by_level_target.tsv  : presence_rate, type_coverage per cell
    - unioned_data/06_glossary_label_reference.tsv : confirms entry existence per cell

    Visual encoding:
    - Sequential green (light→dark) = presence_rate 0→1
    - Gray cell = no glossary entries at that coding level for that group
    - Red border + asterisk in cell text = type_coverage < 1.0
    - Thin black separator lines between reporting dimension groups
    - Right-side italic dimension label per group
    """
    apply_style()
    base = Path(data_dir)
    s1_p = base / "stage1/s1_coverage_by_level_target.tsv"
    gl_p = base / "unioned_data/06_glossary_label_reference.tsv"
    if not _need([s1_p, gl_p], "fig1"):
        return

    s1 = _read(s1_p)
    if s1.empty:
        return

    # Map taxonomy_level → display dimension; filter to the 7 reported dimensions
    DIM_MAP = {
        "race": "race",
        "religion": "religion",
        "sexuality": "lgbtq",
        "gender": "gender",
        "origin": "origin",
        "politics": "politics",
        "disability": "disability",
    }
    DIM_ORDER = [
        "race",
        "religion",
        "lgbtq",
        "gender",
        "origin",
        "politics",
        "disability",
    ]
    LEVELS = ["L2", "L3", "L4"]
    COL_LABELS = ["L2", "L3", "L4"]

    s1 = s1[s1["taxonomy_level"].isin(DIM_MAP)].copy()
    # Explicit target exclusions: self-referential and pan-group categories excluded
    # from pipeline reporting (report_include = False).  The taxonomy_level filter
    # handles most cases, but defence-in-depth avoids silent leakage if taxonomy
    # assignment changes in a future pipeline run.
    _EXCLUDE = {"referential_white_supremacist", "minority"}
    s1 = s1[~s1["target"].isin(_EXCLUDE)].copy()
    s1["dimension"] = s1["taxonomy_level"].map(DIM_MAP)

    # Build ordered row list: DIM_ORDER, then alphabetical within each dimension
    rows: list[tuple[str, str]] = []  # (target, dimension)
    dim_ranges: dict[str, tuple[int, int]] = {}
    for dim in DIM_ORDER:
        targets = sorted(s1[s1["dimension"] == dim]["target"].unique())
        start = len(rows)
        rows.extend((t, dim) for t in targets)
        dim_ranges[dim] = (start, len(rows))

    n_rows, n_cols = len(rows), len(LEVELS)

    # Build grids (indexed [row, col])
    pr_grid = np.full((n_rows, n_cols), np.nan)
    tc_grid = np.full((n_rows, n_cols), np.nan)
    has_entry = np.zeros((n_rows, n_cols), dtype=bool)

    for i, (target, _) in enumerate(rows):
        for j, level in enumerate(LEVELS):
            mask = (s1["target"] == target) & (s1["coding_level"] == level)
            sub = s1[mask]
            if not sub.empty:
                has_entry[i, j] = True
                pr_grid[i, j] = float(sub["presence_rate"].iloc[0])
                tc_grid[i, j] = float(sub["type_coverage"].iloc[0])

    # Custom green colormap: clipped so 0% maps to light (not white) green
    base_cmap = mpl.colormaps.get_cmap("Greens")
    greens = LinearSegmentedColormap.from_list(
        "greens_clipped",
        [
            base_cmap(0.15),
            base_cmap(0.38),
            base_cmap(0.62),
            base_cmap(0.85),
            base_cmap(1.0),
        ],
    )
    greens.set_bad(color="#cccccc")  # Gray for missing cells

    pr_masked = np.ma.masked_where(~has_entry, pr_grid)

    # Figure layout: main heatmap + colorbar below
    cell_h = 0.36  # inches per row
    cbar_h = 0.55  # inches for colorbar + legend area
    main_h = n_rows * cell_h
    fig_h = main_h + cbar_h + 0.5
    fig_w = STYLE["textwidth_in"]

    fig = plt.figure(figsize=(fig_w, fig_h))

    # Reserve proportional space: [left, bottom, width, height] in figure fraction
    left_frac = 0.22
    right_pad = 0.18  # space for dimension labels
    main_width = 1.0 - left_frac - right_pad
    main_bottom = cbar_h / fig_h + 0.04
    main_height = main_h / fig_h

    ax = fig.add_axes([left_frac, main_bottom, main_width, main_height])
    ax.set_title("")

    # Draw heatmap
    im = ax.imshow(
        pr_masked,
        cmap=greens,
        vmin=0,
        vmax=1,
        aspect="auto",
        extent=[-0.5, n_cols - 0.5, n_rows - 0.5, -0.5],  # x: cols, y: rows (0 at top)
    )

    # Cell annotations and red borders
    for i in range(n_rows):
        for j in range(n_cols):
            if not has_entry[i, j]:
                continue
            pr = pr_grid[i, j]
            tc = tc_grid[i, j]
            label = f"{int(round(pr * 100))}%{'*' if tc < 1.0 else ''}"
            text_color = "white" if pr > 0.55 else "black"
            ax.text(
                j,
                i,
                label,
                ha="center",
                va="center",
                fontsize=STYLE["annotation_fontsize"],
                color=text_color,
            )
            if tc < 1.0:
                rect = mpatches.Rectangle(
                    (j - 0.5, i - 0.5),
                    1.0,
                    1.0,
                    linewidth=2,
                    edgecolor="red",
                    facecolor="none",
                    clip_on=False,
                )
                ax.add_patch(rect)

    # Dimension separator lines
    for dim in DIM_ORDER:
        _, end_idx = dim_ranges[dim]
        if end_idx < n_rows:
            ax.axhline(end_idx - 0.5, color="black", linewidth=0.9, clip_on=False)

    # Right-side dimension labels (in axes transData, extended x range)
    for dim in DIM_ORDER:
        s_idx, e_idx = dim_ranges[dim]
        mid_y = (s_idx + e_idx - 1) / 2
        ax.text(
            n_cols - 0.5 + 0.25,
            mid_y,
            dim,
            ha="left",
            va="center",
            fontsize=STYLE["tick_label_fontsize"],
            fontstyle="italic",
            transform=ax.transData,
            clip_on=False,
        )

    # Column headers (on top)
    ax.set_xticks(range(n_cols))
    ax.set_xticklabels(COL_LABELS, fontsize=STYLE["tick_label_fontsize"])
    ax.xaxis.set_ticks_position("top")
    ax.xaxis.set_label_position("top")

    # Y-axis: target names
    ax.set_yticks(range(n_rows))
    ax.set_yticklabels([t for t, _ in rows], fontsize=STYLE["tick_label_fontsize"])

    ax.set_xlim(-0.5, n_cols - 0.5 + 1.5)
    ax.set_ylim(n_rows - 0.5, -0.5)
    ax.tick_params(left=False, top=False, bottom=False)
    for spine in ax.spines.values():
        spine.set_visible(False)

    # Layout constants for the bottom strip (in inches, then converted to fractions)
    # gap_in must accommodate colorbar tick labels + "Presence rate" label beneath the bar
    legend_h_in = 0.22  # single-row legend height
    legend_bot_in = 0.04  # clearance below legend to figure bottom
    gap_in = 0.38  # gap between legend top and colorbar bottom (holds tick labels + cb label)
    cbar_h_in = 0.20  # colorbar bar height
    gap2_in = 0.12  # gap between colorbar top and main heatmap bottom
    bottom_strip = legend_bot_in + legend_h_in + gap_in + cbar_h_in + gap2_in

    legend_bot = legend_bot_in / fig_h
    cbar_bottom = (legend_bot_in + legend_h_in + gap_in) / fig_h
    cbar_ht = cbar_h_in / fig_h

    # Recalculate main heatmap bottom to clear the bottom strip
    main_bottom = bottom_strip / fig_h
    ax.set_position([left_frac, main_bottom, main_width, main_height])

    # Horizontal colorbar
    cbar_left = left_frac
    cbar_width = main_width * 0.78
    cax = fig.add_axes([cbar_left, cbar_bottom, cbar_width, cbar_ht])
    cb = mpl.colorbar.ColorbarBase(
        cax, cmap=greens, norm=Normalize(vmin=0, vmax=1), orientation="horizontal"
    )
    cb.set_ticks([0, 0.25, 0.5, 0.75, 1.0])
    cb.set_ticklabels(
        ["0%", "25%", "50%", "75%", "100%"], fontsize=STYLE["tick_label_fontsize"]
    )
    cb.set_label("Presence rate", fontsize=STYLE["axis_label_fontsize"])

    # Legend in a single horizontal row below the colorbar (no overlap)
    legend_handles = [
        mpatches.Patch(
            facecolor="#cccccc",
            edgecolor="gray",
            linewidth=0.5,
            label="No glossary entries at this level",
        ),
        mpatches.Patch(
            facecolor=greens(0.0),
            edgecolor="gray",
            linewidth=0.5,
            label="0% presence (entries exist, none found)",
        ),
        mpatches.Patch(
            facecolor="white",
            edgecolor="red",
            linewidth=2,
            label="Type coverage < 100% (* in label)",
        ),
    ]
    # Anchor to the left figure edge so the legend sits cleanly below the colorbar
    fig.legend(
        handles=legend_handles,
        loc="lower left",
        bbox_to_anchor=(0.01, legend_bot),
        ncol=1,
        fontsize=7,
        frameon=False,
        handlelength=1.2,
        handletextpad=0.4,
    )

    _save(fig, base / "figures_final/fig1_coverage_heatmap.pdf")


# ── Annotation rates by coding level ──────────────────────────────────────────
# Renamed from fig2_annotation_rates_by_level (2026-07-03): the fig2_ prefix
# collided with generate_fig2_annotation_di_pairwise.py's
# fig2_annotation_di_by_pair_level.pdf, the paper's actual Figure 2. This
# figure is currently Figure 1 in the main body (confirmed against the
# current .tex draft), but the output name is deliberately position-
# independent rather than "fig1_..." since the paper's figure order has
# already shifted more than once during this project.


def annotation_rates_by_level(data_dir: str = "outputs/") -> None:
    """
    Three-panel horizontal bar chart: correct vs. failure rates per group × level.

    Source files:
    - stage2/s2_annotation_by_level_target.tsv

    Visual encoding:
    - Teal bars = correct_labeling_rate (Case A / (A+B))
    - Vermillion bars = failure_rate (Case B / (A+B))
    - Only groups with stable match counts (stable_n == True) shown
    - Groups sorted by failure_rate descending within each panel
    - Panel labels in level colors; legend in L2 panel only
    """
    apply_style()
    base = Path(data_dir)
    s2_p = base / "stage2/s2_annotation_by_level_target.tsv"
    if not _need([s2_p], "annotation_rates_by_level"):
        return

    s2 = _read(s2_p)
    if s2.empty:
        return

    s2 = s2[s2["stable_n"].astype(bool)].copy()
    s2 = s2[~s2["is_self_referential"].astype(bool)].copy()
    # Explicit exclusion: referential_white_supremacist has is_self_referential=False
    # at L3 in the pipeline data, so the flag alone is insufficient.
    # minority is a pan-group category excluded from per-group reporting.
    _EXCLUDE = {"referential_white_supremacist", "minority"}
    s2 = s2[~s2["target"].isin(_EXCLUDE)].copy()

    LEVELS = ["L2", "L3", "L4"]
    fig, axes = plt.subplots(
        1,
        3,
        figsize=(STYLE["textwidth_in"], 5.5),
        sharey=False,
        constrained_layout=True,
    )

    BAR_H = 0.35

    for col_i, (ax, level) in enumerate(zip(axes, LEVELS)):
        ax.set_title("")
        sub = s2[s2["coding_level"] == level].sort_values(
            "failure_rate", ascending=True
        )
        if sub.empty:
            ax.axis("off")
            continue

        groups = sub["target"].tolist()
        n = len(groups)
        y = np.arange(n)

        ax.barh(
            y + BAR_H / 2,
            sub["correct_labeling_rate"].values,
            height=BAR_H,
            color=STYLE["colors"]["correct"],
            label="Correct",
        )
        ax.barh(
            y - BAR_H / 2,
            sub["failure_rate"].values,
            height=BAR_H,
            color=STYLE["colors"]["failure"],
            label="Failure",
        )

        ax.set_yticks(y)
        ax.set_yticklabels(groups, fontsize=STYLE["tick_label_fontsize"])
        ax.set_xlim(0, 1)
        ax.set_xticks([0, 0.5, 1.0])
        ax.set_xlabel("Rate", fontsize=STYLE["axis_label_fontsize"])
        ax.axvline(0, color="black", linewidth=0.5)

        _panel_label(ax, level, STYLE["colors"][level])
        ax.spines["left"].set_visible(False)
        ax.tick_params(left=False)

    legend_handles = [
        mpatches.Patch(facecolor=STYLE["colors"]["correct"], label="Correct"),
        mpatches.Patch(facecolor=STYLE["colors"]["failure"], label="Failure"),
    ]
    fig.legend(
        handles=legend_handles,
        loc="outside lower center",
        ncol=2,
        fontsize=STYLE["legend_fontsize"],
        frameon=False,
    )

    _save(fig, base / "figures_final/annotation_rates_by_level.pdf")


# ── Figure 3 — Case A vs B absolute counts by coding level ───────────────────


def fig3_case_ab_counts_by_level(data_dir: str = "outputs/") -> None:
    """
    Three-panel horizontal stacked bar: total matches (Case A + Case B) per group × level.

    Source files:
    - stage2/s2_annotation_by_level_target.tsv

    Visual encoding:
    - Green segment = Case A (hateful context, correct identification)
    - Vermillion segment = Case B (non-hateful context, false positive)
    - Top 10 groups per panel by total match count
    - If one bar dominates (>3× the 90th percentile of top-10), x-axis is
      truncated and the bar is annotated with its actual count
    """
    apply_style()
    base = Path(data_dir)
    s2_p = base / "stage2/s2_annotation_by_level_target.tsv"
    if not _need([s2_p], "fig3"):
        return

    s2 = _read(s2_p)
    if s2.empty:
        return

    s2 = s2[~s2["is_self_referential"].astype(bool)].copy()
    _EXCLUDE = {"referential_white_supremacist", "minority"}
    s2 = s2[~s2["target"].isin(_EXCLUDE)].copy()

    LEVELS = ["L2", "L3", "L4"]
    fig, axes = plt.subplots(
        1, 3, figsize=(STYLE["textwidth_in"], 5.0), constrained_layout=True
    )

    for ax, level in zip(axes, LEVELS):
        ax.set_title("")
        sub = (
            s2[s2["coding_level"] == level]
            .dropna(subset=["total_matches"])
            .nlargest(10, "total_matches")
            .sort_values("total_matches", ascending=True)
        )

        if sub.empty:
            ax.axis("off")
            continue

        groups = sub["target"].tolist()
        n = len(groups)
        y = np.arange(n)
        totals = sub["total_matches"].values
        ca = sub["case_a_present_hateful"].values
        cb = sub["case_b_present_nonhateful"].values

        # Determine x axis limit; truncate if one bar dominates
        pct90 = np.percentile(totals, 90) if len(totals) > 1 else totals[0]
        x_max = totals.max() * 1.05
        truncate = False
        if totals.max() > 3 * pct90 and len(totals) > 2:
            sorted_t = np.sort(totals)
            x_max = sorted_t[-2] * 1.5
            truncate = True

        ax.barh(y, ca, color=STYLE["colors"]["case_a"], label="Case A (hateful)")
        ax.barh(
            y,
            cb,
            left=ca,
            color=STYLE["colors"]["case_b"],
            label="Case B (non-hateful)",
        )

        # Annotate truncated bars: place text just outside the clipped bar end
        if truncate:
            for yi, tot in enumerate(totals):
                if tot > x_max:
                    ax.text(
                        x_max * 1.01,
                        yi,
                        f"{tot:,}",
                        ha="left",
                        va="center",
                        fontsize=STYLE["annotation_fontsize"],
                        color="black",
                        clip_on=False,
                    )

        ax.set_yticks(y)
        ax.set_yticklabels(groups, fontsize=STYLE["tick_label_fontsize"])
        ax.set_xlim(0, x_max)
        ax.set_xlabel("Match count", fontsize=STYLE["axis_label_fontsize"])

        _panel_label(ax, level, STYLE["colors"][level])
        ax.spines["left"].set_visible(False)
        ax.tick_params(left=False)

    # Legend below all panels
    legend_handles = [
        mpatches.Patch(facecolor=STYLE["colors"]["case_a"], label="Case A (hateful)"),
        mpatches.Patch(
            facecolor=STYLE["colors"]["case_b"], label="Case B (non-hateful)"
        ),
    ]
    fig.legend(
        handles=legend_handles,
        loc="outside lower center",
        ncol=2,
        fontsize=STYLE["legend_fontsize"],
        frameon=False,
    )

    _save(fig, base / "figures_final/fig3_case_ab_counts_by_level.pdf")


# ── Figure 4 — DI ratio histograms by coding level ───────────────────────────


def fig4_di_histograms_by_level(data_dir: str = "outputs/") -> None:
    """
    Three-panel overlapping histograms of pairwise DI ratios (presence and type-coverage).

    Source files:
    - stage4/by_level_group/s4b_pairwise_disparity_by_level_group.tsv

    Visual encoding:
    - Blue histogram = presence_rate_di_ratio (alpha=0.7)
    - Sky-blue histogram = type_coverage_di_ratio (alpha=0.7)
    - Dashed red vertical line at DI = 0.80 (4/5 rule threshold)
    - Only stable pairs (unstable_small_n == False) included
    """
    apply_style()
    base = Path(data_dir)
    s4b_p = base / "stage4/by_level_group/s4b_pairwise_disparity_by_level_group.tsv"
    if not _need([s4b_p], "fig4"):
        return

    df = _read(s4b_p)
    if df.empty:
        return

    df = df[~df["unstable_small_n"].astype(bool)].copy()

    LEVELS = ["L2", "L3", "L4"]
    fig, axes = plt.subplots(
        1, 3, figsize=(STYLE["textwidth_in"], 3.2), constrained_layout=True
    )

    # DI ratios are bounded [0, 1]; extend slightly to 1.05 to catch floating-point edge
    # values and avoid a spurious spike at the histogram's right edge.
    BINS = np.linspace(0, 1.05, 22)

    for col_i, (ax, level) in enumerate(zip(axes, LEVELS)):
        ax.set_title("")
        sub = df[df["coding_level"] == level]
        pr_di = sub["presence_rate_di_ratio"].dropna()
        tc_di = sub["type_coverage_di_ratio"].dropna()

        ax.hist(
            pr_di,
            bins=BINS,
            color=STYLE["colors"]["presence"],
            alpha=0.7,
            label="Presence DI",
        )
        ax.hist(
            tc_di,
            bins=BINS,
            color=STYLE["colors"]["type_cov"],
            alpha=0.7,
            label="Type-cov. DI",
        )

        ax.axvline(0.80, color="red", linewidth=1.2, linestyle="--")

        ax.set_xlim(0, 1.05)
        ax.set_xlabel("DI ratio", fontsize=STYLE["axis_label_fontsize"])
        ax.set_ylabel(
            "Count" if col_i == 0 else "", fontsize=STYLE["axis_label_fontsize"]
        )
        # Force integer y-axis ticks: with few stable pairs (L3 has 4, L4 has 1),
        # auto-scaling produces fractional counts like 0.25, 0.50 which are meaningless.
        ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))

        _panel_label(ax, level, STYLE["colors"][level])

        if col_i == 0:
            ax.legend(fontsize=STYLE["legend_fontsize"], frameon=False)

    _save(fig, base / "figures_final/fig4_di_histograms_by_level.pdf")


# ── Figure 5 — Worst coverage DI by fine-grained pair and level ──────────────


def fig5_worst_di_by_pair_level(data_dir: str = "outputs/") -> None:
    """
    Three-panel horizontal bar chart: worst (minimum) DI ratio per stable group pair × level.

    Source files:
    - stage4/by_level_group/s4b_pairwise_disparity_by_level_group.tsv

    Visual encoding:
    - Blue bar (pass color) = DI >= 0.80 (passes 4/5 rule)
    - Red bar (fail color) = DI < 0.80 (fails 4/5 rule)
    - Dashed red vertical line at DI = 0.80
    - Only stable pairs (unstable_small_n == False) shown
    - Sorted ascending (worst DI at top)
    """
    apply_style()
    base = Path(data_dir)
    s4b_p = base / "stage4/by_level_group/s4b_pairwise_disparity_by_level_group.tsv"
    if not _need([s4b_p], "fig5"):
        return

    df = _read(s4b_p)
    if df.empty:
        return

    df = df[~df["unstable_small_n"].astype(bool)].dropna(subset=["worst_di_ratio"])

    LEVELS = ["L2", "L3", "L4"]
    fig, axes = plt.subplots(
        1, 3, figsize=(STYLE["textwidth_in"], 5.5), constrained_layout=True
    )

    for ax, level in zip(axes, LEVELS):
        ax.set_title("")
        sub = df[df["coding_level"] == level].sort_values(
            "worst_di_ratio", ascending=True
        )

        if sub.empty:
            ax.axis("off")
            continue

        pairs = [f"{a} vs {b}" for a, b in zip(sub["target_a"], sub["target_b"])]
        di = sub["worst_di_ratio"].values
        n = len(pairs)
        y = np.arange(n)

        colors = [
            STYLE["colors"]["pass"] if v >= 0.80 else STYLE["colors"]["fail"]
            for v in di
        ]

        ax.barh(y, di, color=colors)
        ax.axvline(0.80, color="red", linewidth=1.2, linestyle="--")

        ax.set_yticks(y)
        ax.set_yticklabels(pairs, fontsize=max(5, STYLE["tick_label_fontsize"] - 1))
        ax.set_xlim(0, 1.1)
        ax.set_xlabel("Worst DI ratio", fontsize=STYLE["axis_label_fontsize"])

        _panel_label(ax, level, STYLE["colors"][level])
        ax.spines["left"].set_visible(False)
        ax.tick_params(left=False)

    _save(fig, base / "figures_final/fig5_worst_di_by_pair_level.pdf")


# ── Figure 6 — ElSherief annotation delta ────────────────────────────────────


def fig6_elsherief_annotation_delta(data_dir: str = "outputs/") -> None:
    """
    Horizontal bar chart: Δ correct labeling rate (union − ElSherief) per reporting group.

    Source files:
    - stage4/elsherief/s4c_annotation_delta_union_vs_elsherief.tsv

    Visual encoding:
    - Green bar = Δ > 0 (union improves on ElSherief alone)
    - Red bar = Δ < 0 (ElSherief alone outperforms union)
    - Sorted ascending (most negative delta at top)

    Data treatment: the source file has one row per (coding_level, report_level, report_target).
    We aggregate across coding levels by summing the underlying case counts (A and B) for both
    the union and ElSherief corpora, then recompute rates from the pooled totals — rates must
    not be averaged directly because denominators differ across levels.  Groups with fewer than
    20 pooled union matches or with zero ElSherief matches are excluded.
    """
    apply_style()
    base = Path(data_dir)
    s4c_p = base / "stage4/elsherief/s4c_annotation_delta_union_vs_elsherief.tsv"
    if not _need([s4c_p], "fig6"):
        return

    df = _read(s4c_p)
    if df.empty:
        return
    required = {
        "report_level",
        "report_target",
        "case_a_present_hateful_union",
        "case_b_present_nonhateful_union",
        "case_a_present_hateful_elsherief",
        "case_b_present_nonhateful_elsherief",
    }
    missing_cols = required - set(df.columns)
    if missing_cols:
        print(f"WARNING: fig6: skipping — missing columns {missing_cols}")
        return

    # Pool across coding levels: sum case counts, then recompute rates
    agg = df.groupby(["report_level", "report_target"], as_index=False).agg(
        ca_u=("case_a_present_hateful_union", "sum"),
        cb_u=("case_b_present_nonhateful_union", "sum"),
        ca_e=("case_a_present_hateful_elsherief", "sum"),
        cb_e=("case_b_present_nonhateful_elsherief", "sum"),
    )
    agg["total_u"] = agg["ca_u"] + agg["cb_u"]
    agg["total_e"] = agg["ca_e"] + agg["cb_e"]
    # Require stable pooled count in union (≥ 20) and at least one ElSherief match
    agg = agg[(agg["total_u"] >= 20) & (agg["total_e"] > 0)]
    agg["rate_u"] = agg["ca_u"] / agg["total_u"]
    agg["rate_e"] = agg["ca_e"] / agg["total_e"]
    agg["delta"] = agg["rate_u"] - agg["rate_e"]
    agg = agg.dropna(subset=["delta"])

    agg = agg.sort_values("delta", ascending=True)
    agg["label"] = agg["report_level"].str.title() + ": " + agg["report_target"]

    labels = agg["label"].tolist()
    deltas = agg["delta"].values
    n = len(labels)
    y = np.arange(n)

    fig, ax = plt.subplots(
        figsize=(STYLE["columnwidth_in"], max(3.5, n * 0.32 + 0.8)),
        constrained_layout=True,
    )
    ax.set_title("")

    colors = [
        STYLE["colors"]["delta_pos"] if d >= 0 else STYLE["colors"]["delta_neg"]
        for d in deltas
    ]
    ax.barh(y, deltas, color=colors)
    ax.axvline(0, color="black", linewidth=0.8)

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=STYLE["tick_label_fontsize"])
    ax.set_ylim(-0.5, n - 0.5)
    # Two-line label to fit within column width (3.35 in)
    ax.set_xlabel(
        "Correct labeling rate Δ\n(union − ElSherief)",
        fontsize=STYLE["axis_label_fontsize"],
    )
    ax.spines["left"].set_visible(False)
    ax.tick_params(left=False)

    _save(fig, base / "figures_final/fig6_elsherief_annotation_delta.pdf")


# ── Figure 7 — ElSherief coverage delta ──────────────────────────────────────


def fig7_elsherief_coverage_delta(data_dir: str = "outputs/") -> None:
    """
    Horizontal bar chart: Δ presence rate (union − ElSherief) per reporting group.

    Source files:
    - stage4/elsherief/s4c_coverage_delta_union_vs_elsherief.tsv

    Visual encoding:
    - All bars green (union always extends or equals ElSherief coverage)
    - Sorted ascending (largest gain at top)
    - Only groups with a positive coverage gain are shown

    Data treatment: the source file has one row per (coding_level, report_level, report_target).
    We aggregate across coding levels by summing distinct_dogwhistles_found and
    total_glossary_dogwhistles for both corpora, then recompute presence rates from pooled
    counts.  Where ElSherief has no glossary entries for a group, its presence rate is 0.
    Groups with no union glossary entries are excluded.
    """
    apply_style()
    base = Path(data_dir)
    s4c_p = base / "stage4/elsherief/s4c_coverage_delta_union_vs_elsherief.tsv"
    if not _need([s4c_p], "fig7"):
        return

    df = _read(s4c_p)
    if df.empty:
        return
    required = {
        "report_level",
        "report_target",
        "distinct_dogwhistles_found_union",
        "total_glossary_dogwhistles_union",
        "distinct_dogwhistles_found_elsherief",
        "total_glossary_dogwhistles_elsherief",
    }
    missing_cols = required - set(df.columns)
    if missing_cols:
        print(f"WARNING: fig7: skipping — missing columns {missing_cols}")
        return

    # Pool across coding levels: sum dogwhistle counts, then recompute rates
    agg = df.groupby(["report_level", "report_target"], as_index=False).agg(
        found_u=("distinct_dogwhistles_found_union", "sum"),
        total_u=("total_glossary_dogwhistles_union", "sum"),
        found_e=("distinct_dogwhistles_found_elsherief", "sum"),
        total_e=("total_glossary_dogwhistles_elsherief", "sum"),
    )
    agg = agg[agg["total_u"] > 0]  # must have union glossary entries
    agg["rate_u"] = agg["found_u"] / agg["total_u"]
    # If ElSherief has no glossary entries, its presence rate is 0 by definition
    agg["rate_e"] = agg.apply(
        lambda r: r["found_e"] / r["total_e"] if r["total_e"] > 0 else 0.0, axis=1
    )
    agg["delta"] = agg["rate_u"] - agg["rate_e"]
    agg = agg[agg["delta"] > 0]  # keep only groups where union extends coverage
    agg = agg.sort_values(
        "delta", ascending=True
    )  # ascending → smallest at y=0 (bottom), largest at y=n-1 (top)
    agg["label"] = agg["report_level"].str.title() + ": " + agg["report_target"]

    labels = agg["label"].tolist()
    deltas = agg["delta"].values
    n = len(labels)
    y = np.arange(n)

    fig, ax = plt.subplots(
        figsize=(STYLE["columnwidth_in"], max(3.5, n * 0.28 + 0.8)),
        constrained_layout=True,
    )
    ax.set_title("")

    ax.barh(y, deltas, color=STYLE["colors"]["delta_pos"])
    ax.axvline(0, color="black", linewidth=0.8)

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=STYLE["tick_label_fontsize"])
    ax.set_ylim(-0.5, n - 0.5)
    # Two-line label to fit within column width (3.35 in)
    ax.set_xlabel(
        "Presence rate Δ\n(union − ElSherief)", fontsize=STYLE["axis_label_fontsize"]
    )
    ax.spines["left"].set_visible(False)
    ax.tick_params(left=False)

    _save(fig, base / "figures_final/fig7_elsherief_coverage_delta.pdf")


# ── Appendix A — Presence rate and type coverage stacked bar ─────────────────


def appA_coverage_presence_vs_type_by_level(data_dir: str = "outputs/") -> None:
    """
    Three-panel horizontal stacked bar: presence_rate (dark) and type_coverage gap.

    Source files:
    - stage4/by_level_group/s4b_coverage_by_level_group.tsv

    Visual encoding:
    - Dark blue segment = presence_rate (fraction of dogwhistle surface forms found)
    - Medium blue gap = type_coverage − presence_rate (found types but not all forms)
    - Light gray gap = 1 − type_coverage (entire categories absent from corpus)
    - Only non-self-referential rows shown
    """
    apply_style()
    base = Path(data_dir)
    s4b_p = base / "stage4/by_level_group/s4b_coverage_by_level_group.tsv"
    if not _need([s4b_p], "appA"):
        return

    df = _read(s4b_p)
    if df.empty:
        return

    df = df[~df["is_self_referential"].astype(bool)].copy()
    df = df.dropna(subset=["presence_rate", "type_coverage"])

    LEVELS = ["L2", "L3", "L4"]
    fig, axes = plt.subplots(
        1, 3, figsize=(STYLE["textwidth_in"], 5.5), constrained_layout=True
    )

    for ax, level in zip(axes, LEVELS):
        ax.set_title("")
        sub = df[df["coding_level"] == level].sort_values(
            "type_coverage", ascending=True
        )

        if sub.empty:
            ax.axis("off")
            continue

        groups = sub["report_target"].tolist()
        n = len(groups)
        y = np.arange(n)

        pr = sub["presence_rate"].values
        tc = sub["type_coverage"].values
        gap_form = np.clip(tc - pr, 0, None)  # form-level gap; 0 when tc < pr
        # Third segment must start where second ends regardless of float quirks
        seg2_end = pr + gap_form  # == max(pr, tc) element-wise
        gap_type = np.clip(1.0 - seg2_end, 0, None)  # categorical absence

        ax.barh(y, pr, color=STYLE["colors"]["presence"], label="Presence rate")
        ax.barh(y, gap_form, left=pr, color="#7EB9DD", label="Type found, form gap")
        ax.barh(
            y, gap_type, left=seg2_end, color="#cccccc", label="Categorical absence"
        )

        ax.set_yticks(y)
        ax.set_yticklabels(groups, fontsize=STYLE["tick_label_fontsize"])
        ax.set_xlim(0, 1.0)
        ax.set_xlabel("Coverage", fontsize=STYLE["axis_label_fontsize"])

        _panel_label(ax, level, STYLE["colors"][level])
        ax.spines["left"].set_visible(False)
        ax.tick_params(left=False)

    legend_handles = [
        mpatches.Patch(facecolor=STYLE["colors"]["presence"], label="Presence rate"),
        mpatches.Patch(facecolor="#7EB9DD", label="Type found, form gap"),
        mpatches.Patch(facecolor="#cccccc", label="Categorical absence"),
    ]
    fig.legend(
        handles=legend_handles,
        loc="outside lower center",
        ncol=3,
        fontsize=STYLE["legend_fontsize"],
        frameon=False,
    )

    _save(fig, base / "figures_final/appA_coverage_presence_vs_type_by_level.pdf")


# ── Appendix B — Token frequency top-10 by level ─────────────────────────────


def appB_token_frequency_by_level(data_dir: str = "outputs/") -> None:
    """
    Three-panel horizontal bar: top-10 groups by token frequency per coding level.

    Source files:
    - stage1/s1_coverage_by_level_target.tsv (token_frequency column)

    Visual encoding:
    - Bar color matches level color (Okabe-Ito orange/sky-blue/pink)
    - Top 10 groups per level by raw token match count
    """
    apply_style()
    base = Path(data_dir)
    s1_p = base / "stage1/s1_coverage_by_level_target.tsv"
    if not _need([s1_p], "appB"):
        return

    s1 = _read(s1_p)
    if s1.empty:
        return

    s1 = s1[~s1["is_self_referential"].astype(bool)]

    LEVELS = ["L2", "L3", "L4"]
    fig, axes = plt.subplots(
        1, 3, figsize=(STYLE["textwidth_in"], 4.5), constrained_layout=True
    )

    for ax, level in zip(axes, LEVELS):
        ax.set_title("")
        sub = (
            s1[s1["coding_level"] == level]
            .nlargest(10, "token_frequency")
            .sort_values("token_frequency", ascending=True)
        )

        if sub.empty:
            ax.axis("off")
            continue

        groups = sub["target"].tolist()
        freqs = sub["token_frequency"].values
        y = np.arange(len(groups))

        ax.barh(y, freqs, color=STYLE["colors"][level])
        ax.set_yticks(y)
        ax.set_yticklabels(groups, fontsize=STYLE["tick_label_fontsize"])
        ax.set_xlabel("Token frequency", fontsize=STYLE["axis_label_fontsize"])

        _panel_label(ax, level, STYLE["colors"][level])
        ax.spines["left"].set_visible(False)
        ax.tick_params(left=False)

    _save(fig, base / "figures_final/appB_token_frequency_by_level.pdf")


# ── Appendix C — Annotation rates pooled across levels ───────────────────────


def appC_annotation_rates_pooled(data_dir: str = "outputs/") -> None:
    """
    Pooled correct vs. failure rate bar chart (all groups, all levels combined).

    Source files:
    - stage4/by_level_group/s4b_annotation_by_level_group.tsv

    Visual encoding:
    - Same style as Figure 2 but with data pooled across L2/L3/L4
    - Aggregate by summing case_a and case_b counts, then recomputing rates
    - Only groups with at least 20 total matches after pooling
    """
    apply_style()
    base = Path(data_dir)
    s4b_p = base / "stage4/by_level_group/s4b_annotation_by_level_group.tsv"
    if not _need([s4b_p], "appC"):
        return

    df = _read(s4b_p)
    if df.empty:
        return

    df = df[~df["is_self_referential"].astype(bool)].copy()

    # Pool across levels
    agg = df.groupby("report_target", as_index=False).agg(
        case_a=("case_a_present_hateful", "sum"),
        case_b=("case_b_present_nonhateful", "sum"),
    )
    agg["total"] = agg["case_a"] + agg["case_b"]
    agg = agg[agg["total"] >= 20]
    agg["correct_rate"] = agg["case_a"] / agg["total"]
    agg["failure_rate"] = agg["case_b"] / agg["total"]
    agg = agg.sort_values("failure_rate", ascending=True)

    if agg.empty:
        print("WARNING: appC has no pooled groups with n >= 20")
        return

    groups = agg["report_target"].tolist()
    n = len(groups)
    y = np.arange(n)
    BAR_H = 0.35

    fig, ax = plt.subplots(
        figsize=(STYLE["textwidth_in"] / 1.5, max(4.0, n * 0.38 + 1.0)),
        constrained_layout=True,
    )
    ax.set_title("")

    ax.barh(
        y + BAR_H / 2,
        agg["correct_rate"].values,
        height=BAR_H,
        color=STYLE["colors"]["correct"],
        label="Correct",
    )
    ax.barh(
        y - BAR_H / 2,
        agg["failure_rate"].values,
        height=BAR_H,
        color=STYLE["colors"]["failure"],
        label="Failure",
    )

    ax.set_yticks(y)
    ax.set_yticklabels(groups, fontsize=STYLE["tick_label_fontsize"])
    ax.set_xlim(0, 1)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_xlabel("Rate", fontsize=STYLE["axis_label_fontsize"])
    ax.axvline(0, color="black", linewidth=0.5)
    ax.legend(fontsize=STYLE["legend_fontsize"], frameon=False, loc="lower right")
    ax.spines["left"].set_visible(False)
    ax.tick_params(left=False)

    _save(fig, base / "figures_final/appC_annotation_rates_pooled.pdf")


# ── Appendix D — Worst DI and label gap by reporting group pair (pooled) ─────


def appD_worst_di_and_label_gap_pooled(data_dir: str = "outputs/") -> None:
    """
    Two-panel figure: worst pooled DI ratio (left) and largest label gap (right).

    Source files:
    - stage4/by_level_group/s4b_pairwise_disparity_by_level_group.tsv

    Visual encoding:
    - Left panel: worst (min) DI ratio across levels per pair — colored pass/fail
    - Right panel: largest (max) absolute label gap across levels per pair — all red
    - Only stable pairs (unstable_small_n == False) considered
    """
    apply_style()
    base = Path(data_dir)
    s4b_p = base / "stage4/by_level_group/s4b_pairwise_disparity_by_level_group.tsv"
    if not _need([s4b_p], "appD"):
        return

    df = _read(s4b_p)
    if df.empty:
        return

    df = df[~df["unstable_small_n"].astype(bool)].copy()

    # Pool across levels: take min DI and max label gap per pair
    pooled = df.groupby(["target_a", "target_b"], as_index=False).agg(
        worst_di=("worst_di_ratio", "min"), max_gap=("labeling_rate_gap_abs", "max")
    )
    pooled = pooled.dropna(subset=["worst_di"]).sort_values("worst_di", ascending=True)

    pairs = [f"{a} vs {b}" for a, b in zip(pooled["target_a"], pooled["target_b"])]
    n = len(pairs)
    y = np.arange(n)

    fig, (ax_di, ax_gap) = plt.subplots(
        1,
        2,
        figsize=(STYLE["textwidth_in"], max(4.0, n * 0.32 + 1.0)),
        constrained_layout=True,
    )

    # Left: worst DI
    ax_di.set_title("")
    di_colors = [
        STYLE["colors"]["pass"] if v >= 0.80 else STYLE["colors"]["fail"]
        for v in pooled["worst_di"].values
    ]
    ax_di.barh(y, pooled["worst_di"].values, color=di_colors)
    ax_di.axvline(0.80, color="red", linewidth=1.2, linestyle="--")
    ax_di.set_yticks(y)
    ax_di.set_yticklabels(pairs, fontsize=max(5, STYLE["tick_label_fontsize"] - 1))
    ax_di.set_xlim(0, 1.1)
    ax_di.set_xlabel("Worst DI ratio (pooled)", fontsize=STYLE["axis_label_fontsize"])
    ax_di.spines["left"].set_visible(False)
    ax_di.tick_params(left=False)

    # Right: largest label gap — NaN means no stable label estimate for that pair
    ax_gap.set_title("")
    gap_vals = pooled["max_gap"].values  # NaN for pairs without stable gap
    gap_plot = np.where(np.isnan(gap_vals), 0, gap_vals)  # 0-length bars for NaN pairs
    ax_gap.barh(y, gap_plot, color=STYLE["colors"]["fail"])
    ax_gap.set_yticks(y)
    ax_gap.set_yticklabels(pairs, fontsize=max(5, STYLE["tick_label_fontsize"] - 1))
    # Dynamic xlim: cap at 1.0, add 10% headroom above observed max
    gap_max = float(np.nanmax(gap_vals)) if np.any(~np.isnan(gap_vals)) else 0.5
    ax_gap.set_xlim(0, min(1.0, gap_max * 1.1))
    ax_gap.set_xlabel(
        "Largest label gap (pooled)", fontsize=STYLE["axis_label_fontsize"]
    )
    ax_gap.spines["left"].set_visible(False)
    ax_gap.tick_params(left=False)

    _save(fig, base / "figures_final/appD_worst_di_and_label_gap_pooled.pdf")


# ── Appendix E — Annotation label gap by fine-grained pair and level ─────────


def appE_annotation_label_gap_by_level(data_dir: str = "outputs/") -> None:
    """
    Three-panel horizontal bar: absolute correct-labeling-rate gap per pair × level.

    Source files:
    - stage4/by_level_group/s4b_pairwise_disparity_by_level_group.tsv

    Visual encoding:
    - All bars in red (labeling gaps are always negative findings)
    - Sorted descending (largest gap at top)
    - Only stable pairs (unstable_small_n == False) with non-null gap
    """
    apply_style()
    base = Path(data_dir)
    s4b_p = base / "stage4/by_level_group/s4b_pairwise_disparity_by_level_group.tsv"
    if not _need([s4b_p], "appE"):
        return

    df = _read(s4b_p)
    if df.empty:
        return

    df = df[~df["unstable_small_n"].astype(bool)].dropna(
        subset=["labeling_rate_gap_abs"]
    )

    LEVELS = ["L2", "L3", "L4"]
    fig, axes = plt.subplots(
        1, 3, figsize=(STYLE["textwidth_in"], 5.5), constrained_layout=True
    )

    for ax, level in zip(axes, LEVELS):
        ax.set_title("")
        sub = df[df["coding_level"] == level].sort_values(
            "labeling_rate_gap_abs", ascending=False
        )

        if sub.empty:
            ax.axis("off")
            continue

        pairs = [f"{a} vs {b}" for a, b in zip(sub["target_a"], sub["target_b"])]
        gaps = sub["labeling_rate_gap_abs"].values
        y = np.arange(len(pairs))

        ax.barh(y, gaps, color=STYLE["colors"]["fail"])
        ax.set_yticks(y)
        ax.set_yticklabels(pairs, fontsize=max(5, STYLE["tick_label_fontsize"] - 1))
        ax.set_xlabel(
            "Label gap\n(|Δ correct rate|)", fontsize=STYLE["axis_label_fontsize"]
        )

        _panel_label(ax, level, STYLE["colors"][level])
        ax.spines["left"].set_visible(False)
        ax.tick_params(left=False)

    _save(fig, base / "figures_final/appE_annotation_label_gap_by_level.pdf")


# ── Appendix F — Cross-level consistency deltas ───────────────────────────────


def _declutter_labels(
    ax: plt.Axes,
    fig: plt.Figure,
    end_points: list[tuple[str, float, float, str]],
    fontsize: float,
    x_pad_px: float = 6.0,
) -> None:
    """Place a direct end-of-line label per group, greedily decluttered in
    pixel space so labels closer than ~one line-height collapse into a
    vertically stacked, non-overlapping column.

    end_points: list of (label_text, x_final_data, y_final_data, color).
    Decluttering must happen in *display* pixels, not data coordinates,
    because the data only spans [0, 1] while actual visual separation is
    governed by rendered font size at the figure's draw DPI.
    """
    if not end_points:
        return

    fig.canvas.draw()
    dpi = fig.dpi
    # One line-height at the render DPI, plus a little leading, is the
    # minimum gap that avoids glyphs from adjacent labels touching.
    min_gap_px = fontsize * (dpi / 72.0) * 1.25
    edge_margin_px = min_gap_px * 0.4

    bbox = ax.get_window_extent()
    top_bound = bbox.y1 - edge_margin_px
    bottom_bound = bbox.y0 + edge_margin_px

    items = []
    for label_text, x_final, y_final, color in end_points:
        px, py = ax.transData.transform((x_final, y_final))
        items.append([label_text, x_final, y_final, color, px, py])

    # Top to bottom on screen = descending pixel y.
    items.sort(key=lambda it: -it[5])

    # Pass 1 (top-down): push each label below the one above it, clamped to
    # the axes' top edge.
    resolved_py = []
    prev_py = None
    for it in items:
        py = min(it[5], top_bound)
        cur = py if prev_py is None else min(py, prev_py - min_gap_px)
        resolved_py.append(cur)
        prev_py = cur

    # Pass 2 (bottom-up): if the stack ran past the bottom edge, pull labels
    # back up so the whole column fits within the axes.
    if resolved_py[-1] < bottom_bound:
        resolved_py[-1] = bottom_bound
        for i in range(len(resolved_py) - 2, -1, -1):
            resolved_py[i] = max(resolved_py[i], resolved_py[i + 1] + min_gap_px)

    inv = ax.transData.inverted()
    for it, py_resolved in zip(items, resolved_py):
        label_text, x_final, y_final, color, px, _py = it
        x_label, y_label = inv.transform((px + x_pad_px, py_resolved))
        ax.annotate(
            label_text,
            xy=(x_final, y_final),
            xycoords="data",
            xytext=(x_label, y_label),
            textcoords="data",
            ha="left",
            va="center",
            fontsize=fontsize,
            color=color,
            clip_on=False,
            zorder=4,
        )


def appF_cross_level_deltas(data_dir: str = "outputs/") -> None:
    """
    Two-panel slope chart (stacked vertically): presence rate and
    correct-labeling rate plotted directly at each coding level, one line per
    target group connecting its values across L2 -> L3 -> L4.

    Source files:
    - stage3/s3_cross_level_consistency.tsv

    Visual encoding:
    - Top panel: presence_rate per level. Bottom panel: correct_labeling_rate
      per level. Same y-domain [0, 1] in both, sharing the x-axis.
    - One line per target group. Only groups with a non-null value at all
      three levels (L2, L3, L4) in *both* presence_rate and
      correct_labeling_rate are plotted, so every line spans the full axis
      and the group set is identical in both panels.
    - Color encodes the group's reporting dimension (race, religion, lgbtq,
      gender, origin, politics); marker shape distinguishes individual groups
      sharing a dimension. The same (color, marker) pair is used for a given
      group in both panels.
    - Each line is labeled directly at its rightmost available point instead
      of via a legend; overlapping labels are greedily separated in pixel
      space (see _declutter_labels).

    Design rationale: the previous 39-row diverging bar chart (one row per
    group x transition) required a separate delta number per group to convey
    a within-group change. Plotting the raw rates as connected lines lets the
    slope itself communicate the change, and consolidates each group into a
    single visual element spanning both panels.
    """
    apply_style()
    base = Path(data_dir)
    s3_p = base / "stage3/s3_cross_level_consistency.tsv"
    if not _need([s3_p], "appF"):
        return

    df = _read(s3_p)
    if df.empty:
        return

    # Validate required columns
    required = {
        "taxonomy_level",
        "target",
        "coding_level_from",
        "coding_level_to",
        "presence_rate_from",
        "presence_rate_to",
    }
    missing = required - set(df.columns)
    if missing:
        print(f"WARNING: appF: skipping — missing columns {missing}")
        return

    # Resolve labeling rate columns (accept either naming variant)
    if {"correct_labeling_rate_from", "correct_labeling_rate_to"} <= set(df.columns):
        lab_from_col, lab_to_col = (
            "correct_labeling_rate_from",
            "correct_labeling_rate_to",
        )
    elif {"labeling_rate_from", "labeling_rate_to"} <= set(df.columns):
        lab_from_col, lab_to_col = "labeling_rate_from", "labeling_rate_to"
    else:
        lab_from_col = lab_to_col = None
        print(
            "WARNING: appF: no labeling rate from/to columns found — "
            "right panel will be empty."
        )

    # Same group-exclusion logic as the prior delta version: pan-category and
    # self-referential targets excluded from pipeline reporting.
    EXCLUDE_TARGETS = {
        "referential_white_supremacist",
        "minority",
        "unknown_minority",
        "other",
    }
    df = df[~df["target"].isin(EXCLUDE_TARGETS)].copy()

    LEVELS = ["L2", "L3", "L4"]

    # Dimension display mapping, consistent with fig1_coverage_heatmap.
    DIM_MAP = {
        "race": "race",
        "religion": "religion",
        "sexuality": "lgbtq",
        "gender": "gender",
        "origin": "origin",
        "politics": "politics",
        "disability": "disability",
    }
    DIM_ORDER = [
        "race",
        "religion",
        "lgbtq",
        "gender",
        "origin",
        "politics",
        "disability",
    ]
    DIM_COLORS = {
        "race": "#0072B2",
        "religion": "#D55E00",
        "lgbtq": "#009E73",
        "gender": "#CC79A7",
        "origin": "#E69F00",
        "politics": "#56B4E9",
        "disability": "#999999",
    }
    MARKERS = ["o", "s", "^", "D", "v", "P", "X", "*"]

    groups: list[tuple[str, str]] = sorted(
        df[["taxonomy_level", "target"]]
        .drop_duplicates()
        .itertuples(index=False, name=None)
    )
    if not groups:
        print("WARNING: appF: no groups remain after filtering — skipping.")
        return

    # Build per-group level -> rate dicts from the from/to row pairs.
    pres_series: dict[tuple[str, str], dict[str, float]] = {}
    lab_series: dict[tuple[str, str], dict[str, float]] = {}
    for tl, tg in groups:
        sub = df[(df["taxonomy_level"] == tl) & (df["target"] == tg)]
        pres: dict[str, float] = {}
        lab: dict[str, float] = {}
        for _, row in sub.iterrows():
            pres[row["coding_level_from"]] = row["presence_rate_from"]
            pres[row["coding_level_to"]] = row["presence_rate_to"]
            if lab_from_col is not None:
                lab[row["coding_level_from"]] = row[lab_from_col]
                lab[row["coding_level_to"]] = row[lab_to_col]
        pres_series[(tl, tg)] = pres
        lab_series[(tl, tg)] = lab

    # Keep only groups with a complete L2, L3, L4 trajectory in *both* metrics,
    # so every line spans the full x-axis and the same group set appears in
    # both panels (required for cross-panel color/marker tracking).
    def _is_complete(level_dict: dict[str, float]) -> bool:
        return all(
            lvl in level_dict and not pd.isna(level_dict[lvl]) for lvl in LEVELS
        )

    groups = [
        g
        for g in groups
        if _is_complete(pres_series[g]) and _is_complete(lab_series[g])
    ]
    if not groups:
        print("WARNING: appF: no groups have complete L2/L3/L4 data in both "
              "metrics — skipping.")
        return

    # Assign (color, marker): color by dimension, marker cycles within dimension.
    group_style: dict[tuple[str, str], tuple[str, str]] = {}
    for dim in DIM_ORDER:
        dim_groups = [g for g in groups if DIM_MAP.get(g[0]) == dim]
        for i, g in enumerate(dim_groups):
            group_style[g] = (DIM_COLORS[dim], MARKERS[i % len(MARKERS)])

    fig, axes = plt.subplots(
        2,
        1,
        figsize=(STYLE["textwidth_in"], 5.5),
        constrained_layout=True,
    )

    fig.set_constrained_layout_pads(hspace=0.12, wspace=0.0)

    panel_defs = [
        ("Presence rate", pres_series, axes[0]),
        ("Correct-labeling rate", lab_series, axes[1]),
    ]

    # Stretch the inter-level spacing so the lines use more of the panel's
    # horizontal room instead of being compressed into its left half, while
    # the right-hand pad (reserved for end-of-line labels) stays small
    # enough that the longest label string still fits without overflowing.
    LEVEL_SPACING = 2.2
    RIGHT_PAD = 1.3
    x_idx = [i * LEVEL_SPACING for i in range(len(LEVELS))]
    label_fontsize = STYLE["annotation_fontsize"] + 1.5
    summaries: list[str] = []

    for title, series_map, ax in panel_defs:
        ax.set_title("")

        end_points: list[tuple[str, float, float, str]] = []
        for g in groups:
            series = series_map.get(g, {})
            ys = [series.get(lvl, np.nan) for lvl in LEVELS]
            ys = [float(v) if v is not None and not pd.isna(v) else np.nan for v in ys]
            if all(np.isnan(v) for v in ys):
                continue

            color, marker = group_style[g]
            ax.plot(
                x_idx,
                ys,
                color=color,
                marker=marker,
                markersize=4.5,
                linewidth=1.3,
                alpha=0.85,
                clip_on=False,
                zorder=3,
            )

            valid_idx = [i for i, v in enumerate(ys) if not np.isnan(v)]
            x_final = x_idx[valid_idx[-1]]
            y_final = ys[valid_idx[-1]]
            tl, tg = g
            end_points.append((f"{DIM_MAP.get(tl, tl)}:{tg}", x_final, y_final, color))

        ax.set_xlim(-0.15 * LEVEL_SPACING, x_idx[-1] + RIGHT_PAD)
        ax.set_xticks(x_idx)
        ax.set_xticklabels(LEVELS)
        ax.set_ylim(0, 1.0)
        ax.set_ylabel(title, fontsize=STYLE["axis_label_fontsize"])
        ax.tick_params(axis="x", labelsize=STYLE["tick_label_fontsize"])
        ax.tick_params(axis="y", labelsize=STYLE["tick_label_fontsize"])

        _declutter_labels(ax, fig, end_points, label_fontsize)

        summaries.append(f"  {title}: {len(end_points)} groups plotted")

    _save(fig, base / "figures_final/appF_cross_level_deltas.pdf")

    print("appF summary:")
    for s in summaries:
        print(s)


# ── Appendix G — ElSherief pairwise DI delta scatter ─────────────────────────


def appG_elsherief_pairwise_di_delta(data_dir: str = "outputs/") -> None:
    """
    Scatter plot: Δ worst DI (x) vs Δ label gap (y) for group pairs comparing union to ElSherief.

    Source files:
    - stage4/elsherief/s4c_pairwise_delta_union_vs_elsherief.tsv

    Visual encoding:
    - Each point = one group pair with stable estimates in both conditions
    - Dashed gray lines at x=0 and y=0 divide the four quadrants
    - Points labeled with pair names in 7pt font
    - Points above y=0 line = worse label gap in union; below = better label gap
    """
    apply_style()
    base = Path(data_dir)
    s4c_p = base / "stage4/elsherief/s4c_pairwise_delta_union_vs_elsherief.tsv"
    if not _need([s4c_p], "appG"):
        return

    df = _read(s4c_p)
    if df.empty:
        return

    df = (
        df[
            ~df["unstable_small_n_union"].astype(bool)
            & ~df["unstable_small_n_elsherief"].astype(bool)
        ]
        .dropna(
            subset=[
                "worst_di_ratio_delta_union_minus_elsherief",
                "label_gap_abs_delta_union_minus_elsherief",
            ]
        )
        .copy()
    )

    if df.empty:
        print("WARNING: appG: no stable pairs in both conditions")
        return

    x = df["worst_di_ratio_delta_union_minus_elsherief"].values
    y_vals = df["label_gap_abs_delta_union_minus_elsherief"].values
    pair_labels = [f"{a}/{b}" for a, b in zip(df["target_a"], df["target_b"])]

    fig, ax = plt.subplots(
        figsize=(STYLE["columnwidth_in"], STYLE["columnwidth_in"]),
        constrained_layout=True,
    )
    ax.set_title("")

    ax.scatter(x, y_vals, s=30, color=STYLE["colors"]["presence"], alpha=0.8, zorder=3)

    for xi, yi, lbl in zip(x, y_vals, pair_labels):
        ax.text(xi, yi, f" {lbl}", fontsize=7, va="center", ha="left")

    ax.axvline(0, color="gray", linewidth=0.8, linestyle="--", zorder=1)
    ax.axhline(0, color="gray", linewidth=0.8, linestyle="--", zorder=1)

    # Two-line labels to fit within column width (3.35 in)
    ax.set_xlabel(
        "Δ worst DI\n(union − ElSherief)", fontsize=STYLE["axis_label_fontsize"]
    )
    ax.set_ylabel(
        "Δ label gap abs\n(union − ElSherief)", fontsize=STYLE["axis_label_fontsize"]
    )

    _save(fig, base / "figures_final/appG_elsherief_pairwise_di_delta.pdf")


# ── Main entry point ──────────────────────────────────────────────────────────

ALL_FIGURES: dict[str, tuple[str, callable]] = {
    "1": ("fig1_coverage_heatmap.pdf", fig1_coverage_heatmap),
    "2": ("annotation_rates_by_level.pdf", annotation_rates_by_level),
    "3": ("fig3_case_ab_counts_by_level.pdf", fig3_case_ab_counts_by_level),
    "4": ("fig4_di_histograms_by_level.pdf", fig4_di_histograms_by_level),
    "5": ("fig5_worst_di_by_pair_level.pdf", fig5_worst_di_by_pair_level),
    "6": ("fig6_elsherief_annotation_delta.pdf", fig6_elsherief_annotation_delta),
    "7": ("fig7_elsherief_coverage_delta.pdf", fig7_elsherief_coverage_delta),
    "A": (
        "appA_coverage_presence_vs_type_by_level.pdf",
        appA_coverage_presence_vs_type_by_level,
    ),
    "B": ("appB_token_frequency_by_level.pdf", appB_token_frequency_by_level),
    "C": ("appC_annotation_rates_pooled.pdf", appC_annotation_rates_pooled),
    "D": ("appD_worst_di_and_label_gap_pooled.pdf", appD_worst_di_and_label_gap_pooled),
    "E": ("appE_annotation_label_gap_by_level.pdf", appE_annotation_label_gap_by_level),
    "F": ("appF_cross_level_deltas.pdf", appF_cross_level_deltas),
    "G": ("appG_elsherief_pairwise_di_delta.pdf", appG_elsherief_pairwise_di_delta),
}


def main(argv: list[str] | None = None) -> None:
    """Run all figure generation functions in order."""
    parser = argparse.ArgumentParser(description="Generate publication figures.")
    parser.add_argument(
        "--data-dir",
        default="outputs/",
        help="Base directory for pipeline outputs (default: outputs/)",
    )
    parser.add_argument(
        "--figures",
        default=None,
        help="Comma-separated list of figure numbers/letters to generate "
        "(e.g. --figures 1,2,A,B).  Omit to generate all.",
    )
    args = parser.parse_args(argv)

    data_dir = args.data_dir.rstrip("/") + "/"

    if args.figures:
        keys = [k.strip().upper() for k in args.figures.split(",")]
        # Also accept lowercase and numeric-only keys
        keys = [
            k if k in ALL_FIGURES else k.lower() if k.lower() in ALL_FIGURES else k
            for k in keys
        ]
        selected = {k: ALL_FIGURES[k] for k in keys if k in ALL_FIGURES}
        unknown = [k for k in keys if k not in ALL_FIGURES]
        for u in unknown:
            print(
                f"WARNING: Unknown figure key '{u}'. Valid keys: {', '.join(ALL_FIGURES)}"
            )
    else:
        selected = ALL_FIGURES

    n_ok = 0
    for key, (filename, func) in selected.items():
        try:
            func(data_dir=data_dir)
            n_ok += 1
        except Exception as exc:
            print(f"WARNING: Figure {key} failed: {exc}")

    out_dir = Path(data_dir) / "figures_final"
    print(f"\n{n_ok}/{len(selected)} figures attempted → {out_dir}")


def _deprecation_guard() -> None:
    """Abort before writing anything unless the caller explicitly opts in.

    audit_pipeline/notebooks/figures_consolidated.ipynb now owns
    outputs/figures_final/**; running this script unattended would silently
    overwrite its current styled output -- including live, currently-used
    paper figures -- with a stale, unstyled version.
    """
    import os

    opt_in_flag = "--i-know-this-is-deprecated"
    opt_in_env = "I_KNOW_THIS_IS_DEPRECATED"
    if opt_in_flag in sys.argv:
        sys.argv.remove(opt_in_flag)
        return
    if os.environ.get(opt_in_env) == "1":
        return
    print(
        "\n"
        "################################################################\n"
        "# DEPRECATED: generate_figures_final.py should not be run       #\n"
        "# directly.                                                     #\n"
        "#                                                                #\n"
        "# audit_pipeline/notebooks/figures_consolidated.ipynb is now the #\n"
        "# canonical figure generator. Running this script would silently #\n"
        "# overwrite its current styled output at the same paths under   #\n"
        "# outputs/figures_final/** with a stale, unstyled version --     #\n"
        "# including figures that are LIVE and currently used in the      #\n"
        "# paper -- with no error and no visible sign anything went wrong.#\n"
        "#                                                                #\n"
        "# Aborting WITHOUT writing anything. To run anyway (e.g. for a   #\n"
        "# rollback/diff check), pass --i-know-this-is-deprecated or set  #\n"
        "# I_KNOW_THIS_IS_DEPRECATED=1.                                   #\n"
        "################################################################\n",
        file=sys.stderr,
    )
    sys.exit(1)


if __name__ == "__main__":
    _deprecation_guard()
    main()
