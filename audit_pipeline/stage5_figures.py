"""Stage 5: publication-oriented figures for the audit outputs.

The plotting code is organized by reporting view so each figure family can be
rerun or restyled without changing the upstream metric computations.

Pass a PipelineVariant to run() to select which stage-1 through stage-4
outputs to read from and where stage-5 figures are written.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from pandas.errors import EmptyDataError

from audit_pipeline.config import (
    DI_THRESHOLD,
    VARIANT_FULL,
    PipelineVariant,
    resolve_variant,
)
from audit_pipeline.helpers import ensure_dirs

# ── Global style ──────────────────────────────────────────────────────────────
mpl.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "DejaVu Sans"],
        "font.size": 10,
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
        "axes.labelsize": 9,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.linewidth": 0.8,
        "axes.grid": True,
        "axes.grid.axis": "x",
        "grid.color": "#e0e0e0",
        "grid.linewidth": 0.6,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 8,
        "legend.framealpha": 0.7,
        "legend.edgecolor": "#cccccc",
        "figure.facecolor": "white",
        "axes.facecolor": "#fafafa",
        "savefig.facecolor": "white",
    }
)

# Shared palettes
_BLUE = "#4C78A8"
_GREEN = "#54A24B"
_ORANGE = "#F28E2B"
_RED = "#E15759"
_PURPLE = "#B279A2"
_TEAL = "#72B7B2"

# Coding-level accent colors used for facet titles / highlights
_CL_COLOR: dict[str, str] = {
    "L1": "#E15759",
    "L2": "#F28E2B",
    "L3": "#4C78A8",
    "L4": "#B279A2",
}


def _cl_color(cl: str) -> str:
    """Return the accent color assigned to a coding level label."""
    return _CL_COLOR.get(str(cl), "#777777")


# ── Shared helpers ────────────────────────────────────────────────────────────


def _read(path):
    """Read a TSV artifact, returning an empty frame when absent or empty."""
    try:
        return pd.read_csv(path, sep="\t", low_memory=False)
    except (FileNotFoundError, EmptyDataError):
        return pd.DataFrame()


def _save(fig, path):
    """Save a figure with shared layout and export settings."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _filter_self_ref(df: pd.DataFrame) -> pd.DataFrame:
    """Drop self-referential dogwhistle rows when the flag is available."""
    if "is_self_referential" not in df.columns:
        return df.copy()
    return df[~df["is_self_referential"].fillna(False)].copy()


def _top_n(df: pd.DataFrame, by: str, n: int) -> pd.DataFrame:
    """Return the top ``n`` rows by a metric column if that column exists."""
    if df.empty or by not in df.columns:
        return df
    return df.sort_values(by, ascending=False).head(n).copy()


def _style_ax(ax, grid_axis: str = "x") -> None:
    """Remove top/right spines, set tick params."""
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(length=3, width=0.7)
    ax.grid(True, axis=grid_axis, color="#e0e0e0", linewidth=0.6, zorder=0)


def _facet_title(ax, label: str) -> None:
    """Colour-coded panel title for coding-level facets."""
    color = _cl_color(label)
    ax.set_title(label, color=color, fontweight="bold", fontsize=11, pad=6, loc="left")


# ── Level-stratified figures ──────────────────────────────────────────────────


def level_stratified_figures(
    level_dir: Path,
    s1_dir: Path,
    s2_dir: Path,
    s3_dir: Path,
) -> None:
    """Render the coding-level faceted figure set from Stages 1-3 outputs.

    Parameters
    ----------
    level_dir : Path
        Output directory for level-stratified figures.
    s1_dir, s2_dir, s3_dir : Path
        Input directories for the corresponding stage artifacts.
    """
    s1 = _filter_self_ref(_read(s1_dir / "s1_coverage_by_level_target.tsv"))
    s2 = _filter_self_ref(_read(s2_dir / "s2_annotation_by_level_target.tsv"))
    s3c = _read(s3_dir / "s3_coverage_disparity.tsv")
    s3a = _read(s3_dir / "s3_annotation_disparity.tsv")
    s3x = _read(s3_dir / "s3_cross_level_consistency.tsv")

    def _coding_levels(df):
        """Return coding levels in paper order, dropping absent facets."""
        return [
            c
            for c in ["L1", "L2", "L3", "L4"]
            if c in set(df["coding_level"].dropna().astype(str))
        ]

    if not s1.empty:
        cls = _coding_levels(s1)

        # -- Coverage: presence rate + type coverage, faceted by coding level --
        fig, axes = plt.subplots(2, 2, figsize=(14, 10), sharey=False)
        fig.suptitle(
            "Coverage — Presence Rate and Type Coverage by Target Group",
            fontsize=13,
            fontweight="bold",
            y=0.98,
        )
        for i, cl in enumerate(cls[:4]):
            d = _top_n(
                s1[s1["coding_level"].astype(str) == cl], "token_frequency", 10
            ).copy()
            d["label"] = d["target"].astype(str)
            ax = axes.flatten()[i]
            y = range(len(d))
            ax.barh(
                y,
                d["presence_rate"],
                color=_cl_color(cl),
                alpha=0.85,
                label="Presence rate",
                edgecolor="white",
                linewidth=0.5,
            )
            ax.barh(
                y,
                d["type_coverage"],
                color=_GREEN,
                alpha=0.55,
                label="Type coverage",
                edgecolor="white",
                linewidth=0.5,
            )
            ax.set_yticks(list(y))
            ax.set_yticklabels(d["label"], fontsize=8)
            ax.invert_yaxis()
            ax.set_xlim(0, 1.05)
            ax.xaxis.set_major_formatter(mticker.PercentFormatter(xmax=1))
            _facet_title(ax, cl)
            _style_ax(ax, grid_axis="x")
            ax.legend(loc="lower right", fontsize=7)
        for j in range(len(cls), 4):
            axes.flatten()[j].axis("off")
        _save(fig, level_dir / "s5_lev_coverage_presence_vs_type.png")

        # -- Coverage: token frequency top-10, faceted by coding level --
        fig, axes = plt.subplots(2, 2, figsize=(14, 10), sharey=False)
        fig.suptitle(
            "Coverage — Top-10 Token Frequency by Coding Level",
            fontsize=13,
            fontweight="bold",
            y=0.98,
        )
        for i, cl in enumerate(cls[:4]):
            d = _top_n(s1[s1["coding_level"].astype(str) == cl], "token_frequency", 10)
            ax = axes.flatten()[i]
            ax.barh(
                d["target"].astype(str),
                d["token_frequency"],
                color=_cl_color(cl),
                edgecolor="white",
                linewidth=0.5,
            )
            ax.invert_yaxis()
            ax.set_xlabel("Token frequency", fontsize=8)
            _facet_title(ax, cl)
            _style_ax(ax, grid_axis="x")
        for j in range(len(cls), 4):
            axes.flatten()[j].axis("off")
        _save(fig, level_dir / "s5_lev_coverage_token_frequency.png")

    if not s2.empty:
        cls = _coding_levels(s2)

        # -- Annotation rates, faceted by coding level --
        fig, axes = plt.subplots(2, 2, figsize=(15, 10), sharey=False)
        fig.suptitle(
            "Annotation Quality — Correct vs. Failure Rate by Coding Level",
            fontsize=13,
            fontweight="bold",
            y=0.98,
        )
        for i, cl in enumerate(cls[:4]):
            d = _top_n(
                s2[s2["coding_level"].astype(str) == cl], "total_matches", 8
            ).copy()
            d["label"] = (
                d["target"].astype(str) + " (" + d["coding_level"].astype(str) + ")"
            )
            ax = axes.flatten()[i]
            x = range(len(d))
            bar_w = 0.38
            ax.bar(
                x,
                d["correct_labeling_rate"],
                width=bar_w,
                label="Correct",
                color=_GREEN,
                edgecolor="white",
                linewidth=0.5,
            )
            ax.bar(
                [t + bar_w for t in x],
                d["failure_rate"],
                width=bar_w,
                label="Failure",
                color=_ORANGE,
                edgecolor="white",
                linewidth=0.5,
            )
            ax.set_xticks([t + bar_w / 2 for t in x])
            ax.set_xticklabels(d["label"], rotation=40, ha="right", fontsize=8)
            ax.set_ylim(0, 1.05)
            ax.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=1))
            ax.set_ylabel("Rate", fontsize=8)
            _facet_title(ax, cl)
            _style_ax(ax, grid_axis="y")
            ax.legend(loc="upper right")
        for j in range(len(cls), 4):
            axes.flatten()[j].axis("off")
        _save(fig, level_dir / "s5_lev_annotation_rates.png")

        # -- Case A/B stacked, faceted by coding level --
        fig, axes = plt.subplots(2, 2, figsize=(15, 10), sharey=False)
        fig.suptitle(
            "Annotation Quality — Case A vs. B Match Counts by Coding Level",
            fontsize=13,
            fontweight="bold",
            y=0.98,
        )
        for i, cl in enumerate(cls[:4]):
            d = _top_n(
                s2[s2["coding_level"].astype(str) == cl], "total_matches", 8
            ).copy()
            d["label"] = (
                d["target"].astype(str) + " (" + d["coding_level"].astype(str) + ")"
            )
            ax = axes.flatten()[i]
            ax.barh(
                d["label"],
                d["case_a_present_hateful"],
                color=_GREEN,
                label="Case A (hateful)",
                edgecolor="white",
                linewidth=0.5,
            )
            ax.barh(
                d["label"],
                d["case_b_present_nonhateful"],
                left=d["case_a_present_hateful"],
                color=_ORANGE,
                label="Case B (non-hateful)",
                edgecolor="white",
                linewidth=0.5,
            )
            ax.invert_yaxis()
            ax.set_xlabel("Match count", fontsize=8)
            _facet_title(ax, cl)
            _style_ax(ax, grid_axis="x")
            ax.legend(loc="lower right")
        for j in range(len(cls), 4):
            axes.flatten()[j].axis("off")
        _save(fig, level_dir / "s5_lev_annotation_case_ab.png")

    if not s3c.empty:
        cls = _coding_levels(s3c)

        # -- DI ratio histograms, faceted by coding level --
        fig, axes = plt.subplots(2, 2, figsize=(14, 10), sharey=False)
        fig.suptitle(
            "Disparity — Presence & Type Coverage DI Ratio Distributions by Coding Level",
            fontsize=13,
            fontweight="bold",
            y=0.98,
        )
        for i, cl in enumerate(cls[:4]):
            d = s3c[s3c["coding_level"].astype(str) == cl]
            ax = axes.flatten()[i]
            ax.hist(
                d["presence_rate_di_ratio"].dropna(),
                bins=15,
                alpha=0.75,
                color=_BLUE,
                edgecolor="white",
                linewidth=0.5,
                label="Presence DI",
            )
            ax.hist(
                d["type_coverage_di_ratio"].dropna(),
                bins=15,
                alpha=0.55,
                color=_TEAL,
                edgecolor="white",
                linewidth=0.5,
                label="Type DI",
            )
            ax.axvline(
                DI_THRESHOLD,
                color=_RED,
                linestyle="--",
                linewidth=1.2,
                label=f"4/5 threshold ({DI_THRESHOLD})",
            )
            ax.set_xlabel("DI ratio", fontsize=8)
            ax.set_ylabel("Count", fontsize=8)
            _facet_title(ax, cl)
            _style_ax(ax, grid_axis="y")
            ax.legend()
        for j in range(len(cls), 4):
            axes.flatten()[j].axis("off")
        _save(fig, level_dir / "s5_lev_disparity_di_histograms.png")

        # -- Worst DI by pair, faceted by coding level --
        fig, axes = plt.subplots(2, 2, figsize=(14, 10), sharey=False)
        fig.suptitle(
            "Disparity — Worst Coverage DI Ratio by Target Pair and Coding Level",
            fontsize=13,
            fontweight="bold",
            y=0.98,
        )
        for i, cl in enumerate(cls[:4]):
            sub = s3c[s3c["coding_level"].astype(str) == cl].copy()
            sub["pair"] = (
                sub["target_a"].astype(str) + " vs " + sub["target_b"].astype(str)
            )
            d = _top_n(sub, "worst_di_ratio", 8).sort_values(
                "worst_di_ratio", ascending=True
            )
            colors = [_RED if v < DI_THRESHOLD else _BLUE for v in d["worst_di_ratio"]]
            ax = axes.flatten()[i]
            ax.barh(
                d["pair"],
                d["worst_di_ratio"],
                color=colors,
                edgecolor="white",
                linewidth=0.5,
            )
            ax.axvline(
                DI_THRESHOLD,
                color=_RED,
                linestyle="--",
                linewidth=1.2,
                label=f"4/5 rule ({DI_THRESHOLD})",
            )
            ax.set_xlim(0, 1.05)
            ax.set_xlabel("Worst DI ratio", fontsize=8)
            _facet_title(ax, cl)
            _style_ax(ax, grid_axis="x")
            ax.legend(fontsize=7)
        for j in range(len(cls), 4):
            axes.flatten()[j].axis("off")
        _save(fig, level_dir / "s5_lev_disparity_worst_di.png")

    if not s3a.empty:
        cls = _coding_levels(s3a)

        # -- Annotation label gap, faceted by coding level --
        fig, axes = plt.subplots(2, 2, figsize=(14, 10), sharey=False)
        fig.suptitle(
            "Disparity — Annotation Labeling Rate Gap by Target Pair and Coding Level",
            fontsize=13,
            fontweight="bold",
            y=0.98,
        )
        for i, cl in enumerate(cls[:4]):
            sub = s3a[s3a["coding_level"].astype(str) == cl].copy()
            sub["pair"] = (
                sub["target_a"].astype(str) + " vs " + sub["target_b"].astype(str)
            )
            d = _top_n(sub, "labeling_rate_gap_abs", 8).sort_values(
                "labeling_rate_gap_abs", ascending=True
            )
            ax = axes.flatten()[i]
            ax.barh(
                d["pair"],
                d["labeling_rate_gap_abs"],
                color=_RED,
                edgecolor="white",
                linewidth=0.5,
            )
            ax.set_xlabel("|Correct rate gap|", fontsize=8)
            ax.xaxis.set_major_formatter(mticker.PercentFormatter(xmax=1))
            _facet_title(ax, cl)
            _style_ax(ax, grid_axis="x")
        for j in range(len(cls), 4):
            axes.flatten()[j].axis("off")
        _save(fig, level_dir / "s5_lev_annotation_label_gap.png")

    if not s3x.empty:
        d = s3x.copy()
        d["transition"] = (
            d["target"].astype(str)
            + " ("
            + d["coding_level"].astype(str)
            + ") "
            + d["level_from"].astype(str)
            + " \u2192 "
            + d["level_to"].astype(str)
        )
        d = _top_n(
            d.assign(abs_presence=d["presence_rate_delta"].abs()), "abs_presence", 20
        )
        fig, ax = plt.subplots(figsize=(13, 8))
        fig.suptitle(
            "Cross-Level Consistency — Presence and Labeling Rate \u0394 by Coding Level",
            fontsize=13,
            fontweight="bold",
            y=0.98,
        )
        y = range(len(d))
        ax.barh(
            y,
            d["presence_rate_delta"],
            color=_BLUE,
            alpha=0.85,
            label="Presence \u0394",
            edgecolor="white",
            linewidth=0.5,
        )
        ax.barh(
            y,
            d["correct_labeling_rate_delta"],
            color=_GREEN,
            alpha=0.65,
            label="Labeling \u0394",
            edgecolor="white",
            linewidth=0.5,
        )
        ax.set_yticks(list(y))
        ax.set_yticklabels(d["transition"], fontsize=8)
        ax.axvline(0, color="black", linewidth=1)
        ax.set_xlabel("Delta", fontsize=9)
        _style_ax(ax, grid_axis="x")
        ax.legend()
        _save(fig, level_dir / "s5_lev_cross_level_deltas.png")


# ── Group-collapsed figures ───────────────────────────────────────────────────


def group_collapsed_figures(group_dir: Path, s4_dir: Path) -> None:
    """Render reporting-group figures from Stage 4 collapsed outputs.

    Parameters
    ----------
    group_dir : Path
        Output directory for group-collapsed figures.
    s4_dir : Path
        Input directory containing Stage 4 artifacts.
    """
    # Use by-level-group coverage so duplicated taxonomy mappings can be deduplicated
    # explicitly by report group + coding level for a stable heatmap matrix.
    cov = _read(s4_dir / "by_level_group/s4b_coverage_by_level_group.tsv")
    ann = _filter_self_ref(_read(s4_dir / "by_group/s4a_annotation_by_group.tsv"))
    pair = _read(s4_dir / "by_group/s4a_pairwise_disparity_by_group.tsv")

    if not cov.empty:
        d = cov.copy()
        d["group_label"] = (
            d["report_level"].astype(str).str.strip()
            + ": "
            + d["report_target"].astype(str).str.strip()
        )
        d["coding_level"] = d["coding_level"].astype(str).str.strip()

        # Keep only primary coding levels used in paper-facing visuals.
        d = d[d["coding_level"].isin(["L2", "L3", "L4"])].copy()
        # Some groups may appear in multiple taxonomy rows; keep first group-level row.
        d = d.drop_duplicates(subset=["group_label", "coding_level"], keep="first")

        group_order = [
            "disability: unspecific",
            "gender: men",
            "gender: women",
            "lgbtq: LGB",
            "lgbtq: Trans/NB",
            "origin: specific country",
            "origin: undocumented",
            "origin: immigrant",
            "origin: migrant worker",
            "politics: communist",
            "politics: democrat",
            "politics: libertarian",
            "politics: leftist",
            "politics: liberal",
            "politics: conservative",
            "politics: republican",
            "race: asian",
            "race: black",
            "race: latinx",
            "race: middle eastern",
            "race: white",
            "religion: jewish",
            "religion: muslim",
        ]
        existing_groups = set(d["group_label"].astype(str))
        group_labels = [g for g in group_order if g in existing_groups]
        remaining = sorted(existing_groups - set(group_labels))
        group_labels.extend(remaining)
        coding_levels = ["L2", "L3", "L4"]

        presence_mat = d.pivot(
            index="group_label", columns="coding_level", values="presence_rate"
        ).reindex(index=group_labels, columns=coding_levels)
        type_mat = d.pivot(
            index="group_label", columns="coding_level", values="type_coverage"
        ).reindex(index=group_labels, columns=coding_levels)

        # Distinguish structural missing (NaN) from true 0% presence cells.
        cmap = LinearSegmentedColormap.from_list(
            "presence_rate",
            [
                (0.0, "#CBD4D0"),
                (0.35, "#8FC6A2"),
                (0.7, "#3B956F"),
                (1.0, "#14523A"),
            ],
        )
        cmap.set_bad(color="#E8E8E8")

        fig_h = max(7, len(group_labels) * 0.42 + 2.8)
        fig, ax = plt.subplots(figsize=(8.4, fig_h))
        fig.suptitle(
            "Coverage Heatmap — Presence Rate by Reporting Group × Coding Level",
            fontsize=13,
            fontweight="bold",
            y=0.99,
        )

        data = presence_mat.values.astype(float)
        masked = np.ma.array(data, mask=np.isnan(data))
        im = ax.imshow(
            masked,
            aspect="auto",
            cmap=cmap,
            vmin=0.0,
            vmax=1.0,
            interpolation="none",
        )

        flagged = []
        for r, grp in enumerate(group_labels):
            for c, cl in enumerate(coding_levels):
                pr = presence_mat.loc[grp, cl]
                tc = type_mat.loc[grp, cl]

                if pd.isna(pr):
                    ax.text(
                        c,
                        r,
                        "-",
                        ha="center",
                        va="center",
                        fontsize=8,
                        color="#8a8a8a",
                    )
                    continue

                has_type_gap = pd.notna(tc) and 0.0 < tc < 0.999
                txt_color = "white" if pr > 0.5 else "#1a1a1a"
                label = f"{pr:.0%}"
                if has_type_gap:
                    label = label + "$^{*}$"
                ax.text(
                    c,
                    r,
                    label,
                    ha="center",
                    va="center",
                    fontsize=8.5,
                    fontweight="bold",
                    color=txt_color,
                )

                if has_type_gap:
                    flagged.append(
                        f"{grp} / {cl}: type_coverage={tc:.3f}, presence_rate={pr:.3f}"
                    )
                    ax.add_patch(
                        mpatches.FancyBboxPatch(
                            (c - 0.47, r - 0.47),
                            0.94,
                            0.94,
                            boxstyle="square,pad=0",
                            linewidth=1.9,
                            edgecolor="#C0392B",
                            facecolor="none",
                            zorder=3,
                        )
                    )

        ax.set_xticks(range(len(coding_levels)))
        ax.set_xticklabels(
            [
                "L2\n(Stereotype-based)",
                "L3\n(Concept / policy)",
                "L4\n(Persona signals)",
            ],
            fontsize=8.5,
        )
        ax.xaxis.set_ticks_position("top")
        ax.xaxis.set_label_position("top")
        ax.set_yticks(range(len(group_labels)))
        ax.set_yticklabels(group_labels, fontsize=8.2)
        ax.tick_params(axis="both", which="both", length=0)
        ax.grid(False)

        cbar = fig.colorbar(im, ax=ax, fraction=0.032, pad=0.01, aspect=30)
        cbar.set_label("Presence rate", fontsize=8.5, labelpad=6)
        cbar.set_ticks([0.0, 0.25, 0.5, 0.75, 1.0])
        cbar.ax.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=1))
        cbar.ax.tick_params(labelsize=8)

        # Taxonomy section lines and right-side labels.
        section_order = [
            ("disability", "Disability"),
            ("gender", "Gender / LGBTQ"),
            ("lgbtq", "Gender / LGBTQ"),
            ("origin", "Origin"),
            ("politics", "Politics"),
            ("race", "Race"),
            ("religion", "Religion"),
        ]
        section_key_rank = {k: i for i, (k, _) in enumerate(section_order)}

        def _section_key(label: str) -> str:
            return str(label).split(":", 1)[0].strip()

        section_rows = {}
        for i, label in enumerate(group_labels):
            k = _section_key(label)
            section_rows.setdefault(k, []).append(i)

        ordered_sections = sorted(
            [(k, rows) for k, rows in section_rows.items()],
            key=lambda x: section_key_rank.get(x[0], 999),
        )

        # Draw lines between contiguous section blocks.
        for idx_sec in range(len(ordered_sections) - 1):
            last_row = max(ordered_sections[idx_sec][1])
            ax.axhline(last_row + 0.5, color="white", linewidth=1.5, zorder=4)

        ax2 = ax.twinx()
        ax2.set_ylim(ax.get_ylim())
        ax2.set_yticks([])
        section_display = {k: disp for k, disp in section_order}
        for k, rows in ordered_sections:
            mid = (min(rows) + max(rows)) / 2.0
            y = 1 - (mid / max(1, len(group_labels) - 1))
            ax2.text(
                1.02,
                y,
                section_display.get(k, k.title()),
                transform=ax2.transAxes,
                va="center",
                ha="left",
                fontsize=7.5,
                color="#555555",
            )

        legend_handles = [
            mpatches.Patch(
                facecolor="#E8E8E8",
                edgecolor="#cfcfcf",
                label="No glossary entries at this level",
            ),
            mpatches.Patch(
                facecolor="#CBD4D0",
                edgecolor="none",
                label="0% presence (entries exist, none found)",
            ),
            mpatches.FancyBboxPatch(
                (0, 0),
                1,
                1,
                boxstyle="square,pad=0",
                linewidth=1.5,
                edgecolor="#C0392B",
                facecolor="#d8d8d8",
                label="Type coverage < 100% (border + *)",
            ),
        ]
        ax.legend(
            handles=legend_handles,
            loc="lower left",
            bbox_to_anchor=(0, -0.13),
            fontsize=7.5,
            framealpha=0.9,
            ncol=1,
            handlelength=1.3,
            borderpad=0.6,
        )

        note = (
            "Cells marked * have partial type coverage (0 < type_coverage < 1.0). "
            "Gray cells are no-glossary combinations."
        )
        fig.text(
            0.012, 0.01, note, ha="left", va="bottom", fontsize=7.8, color="#555555"
        )

        _save(fig, group_dir / "s5_grp_coverage_scatter.png")

    if not ann.empty:
        ann_plot = ann[
            (ann["report_level"] != "disability")
            | (ann["report_target"] == "unspecific")
        ].copy()
        ann_plot["label"] = (
            ann_plot["report_level"].astype(str)
            + ": "
            + ann_plot["report_target"].astype(str)
            + " ("
            + ann_plot["coding_level"].astype(str)
            + ")"
        )
        ann_plot = ann_plot.sort_values("label")

        # -- Annotation rates bar chart --
        fig, ax = plt.subplots(figsize=(15, 6))
        fig.suptitle(
            "Annotation Quality — Correct vs. Failure Rate by Reporting Group",
            fontsize=13,
            fontweight="bold",
            y=0.98,
        )
        x = range(len(ann_plot))
        bar_w = 0.38
        ax.bar(
            x,
            ann_plot["correct_labeling_rate"],
            width=bar_w,
            color=_GREEN,
            label="Correct",
            edgecolor="white",
            linewidth=0.5,
        )
        ax.bar(
            [v + bar_w for v in x],
            ann_plot["failure_rate"],
            width=bar_w,
            color=_ORANGE,
            label="Failure",
            edgecolor="white",
            linewidth=0.5,
        )
        ax.set_xticks([v + bar_w / 2 for v in x])
        ax.set_xticklabels(ann_plot["label"], rotation=45, ha="right", fontsize=7.5)
        ax.set_ylim(0, 1.05)
        ax.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=1))
        ax.set_ylabel("Rate", fontsize=9)
        _style_ax(ax, grid_axis="y")
        ax.legend()
        _save(fig, group_dir / "s5_grp_annotation_rates.png")

        # -- Case A/B stacked horizontal bar --
        d = _top_n(ann_plot, "case_b_present_nonhateful", 20).sort_values(
            "case_b_present_nonhateful", ascending=True
        )
        fig, ax = plt.subplots(figsize=(13, max(6, 1 + 0.35 * len(d))))
        fig.suptitle(
            "Annotation Quality — Case A vs. B Match Counts by Reporting Group",
            fontsize=13,
            fontweight="bold",
            y=0.98,
        )
        ax.barh(
            d["label"],
            d["case_a_present_hateful"],
            color=_GREEN,
            label="Case A (hateful)",
            edgecolor="white",
            linewidth=0.5,
        )
        ax.barh(
            d["label"],
            d["case_b_present_nonhateful"],
            left=d["case_a_present_hateful"],
            color=_ORANGE,
            label="Case B (non-hateful)",
            edgecolor="white",
            linewidth=0.5,
        )
        ax.set_xlabel("Match count", fontsize=9)
        _style_ax(ax, grid_axis="x")
        ax.legend()
        _save(fig, group_dir / "s5_grp_case_ab_counts.png")

    if not pair.empty:
        # -- DI ratio histograms --
        fig, axes = plt.subplots(1, 2, figsize=(13, 5))
        fig.suptitle(
            "Disparity — Pairwise Coverage DI Ratio Distributions by Reporting Group",
            fontsize=13,
            fontweight="bold",
            y=0.98,
        )
        for ax, col, label, color in [
            (axes[0], "presence_rate_di_ratio", "Presence DI", _BLUE),
            (axes[1], "type_coverage_di_ratio", "Type-Coverage DI", _TEAL),
        ]:
            ax.hist(
                pair[col].dropna(),
                bins=20,
                alpha=0.85,
                color=color,
                edgecolor="white",
                linewidth=0.5,
            )
            ax.axvline(
                DI_THRESHOLD,
                color=_RED,
                linestyle="--",
                linewidth=1.2,
                label="4/5 threshold",
            )
            ax.set_xlabel("DI ratio", fontsize=8)
            ax.set_ylabel("Count", fontsize=8)
            ax.set_title(label, fontweight="bold")
            _style_ax(ax, grid_axis="y")
            ax.legend(fontsize=7)
        _save(fig, group_dir / "s5_grp_di_histograms.png")

        # -- Worst DI + labeling gap panel --
        pair_plot = pair.copy()
        pair_plot["pair"] = (
            pair_plot["target_a"].astype(str)
            + " vs "
            + pair_plot["target_b"].astype(str)
        )
        left = _top_n(pair_plot, "worst_di_ratio", 20).sort_values(
            "worst_di_ratio", ascending=True
        )
        right = _top_n(pair_plot, "labeling_rate_gap_abs", 20).sort_values(
            "labeling_rate_gap_abs", ascending=True
        )

        fig, axes = plt.subplots(1, 2, figsize=(17, 10))
        fig.suptitle(
            "Disparity — Worst Pairwise DI and Annotation Gap by Reporting Group",
            fontsize=13,
            fontweight="bold",
            y=0.98,
        )
        left_colors = [
            _RED if v < DI_THRESHOLD else _BLUE for v in left["worst_di_ratio"]
        ]
        axes[0].barh(
            left["pair"],
            left["worst_di_ratio"],
            color=left_colors,
            edgecolor="white",
            linewidth=0.5,
        )
        axes[0].axvline(
            DI_THRESHOLD,
            color=_RED,
            linestyle="--",
            linewidth=1.2,
            label=f"4/5 rule ({DI_THRESHOLD})",
        )
        axes[0].set_xlabel("Worst DI ratio", fontsize=8)
        axes[0].set_title("Worst DI pairs", fontweight="bold")
        _style_ax(axes[0], grid_axis="x")
        axes[0].legend(fontsize=7)

        axes[1].barh(
            right["pair"],
            right["labeling_rate_gap_abs"],
            color=_RED,
            edgecolor="white",
            linewidth=0.5,
        )
        axes[1].xaxis.set_major_formatter(mticker.PercentFormatter(xmax=1))
        axes[1].set_xlabel("|Correct rate gap|", fontsize=8)
        axes[1].set_title("Largest labeling gaps", fontweight="bold")
        _style_ax(axes[1], grid_axis="x")
        _save(fig, group_dir / "s5_grp_worst_di_and_label_gap.png")


# ── ElSherief delta figures ───────────────────────────────────────────────────


def elsherief_figures(els_dir: Path, s4_dir: Path) -> None:
    """Render delta figures comparing the union benchmark to ElSherief.

    Parameters
    ----------
    els_dir : Path
        Output directory for ElSherief delta figures.
    s4_dir : Path
        Input directory containing Stage 4 ElSherief artifacts.
    """
    cov = _read(s4_dir / "elsherief/s4c_coverage_delta_union_vs_elsherief.tsv")
    ann = _read(s4_dir / "elsherief/s4c_annotation_delta_union_vs_elsherief.tsv")
    pair = _read(s4_dir / "elsherief/s4c_pairwise_delta_union_vs_elsherief.tsv")

    def _diverging_bar(ax, labels, values, xlabel):
        """Draw a horizontal bar chart where sign is encoded by color."""
        colors = [_GREEN if v >= 0 else _RED for v in values.fillna(0)]
        ax.barh(labels, values, color=colors, edgecolor="white", linewidth=0.5)
        ax.axvline(0, color="black", linewidth=1)
        ax.set_xlabel(xlabel, fontsize=9)
        _style_ax(ax, grid_axis="x")

    if not cov.empty:
        d = cov.copy()
        d["label"] = (
            d["report_level"].astype(str) + ": " + d["report_target"].astype(str)
        )
        d = d.sort_values("presence_rate_delta_union_minus_elsherief", ascending=True)
        fig, ax = plt.subplots(figsize=(13, max(6, 1 + 0.3 * len(d))))
        fig.suptitle(
            "ElSherief Subset — Presence Rate \u0394 (Union \u2212 ElSherief)",
            fontsize=13,
            fontweight="bold",
            y=0.98,
        )
        _diverging_bar(
            ax,
            d["label"],
            d["presence_rate_delta_union_minus_elsherief"],
            "Presence rate \u0394",
        )
        _save(fig, els_dir / "s5_els_coverage_delta.png")

    if not ann.empty:
        d = ann.copy()
        d["label"] = (
            d["report_level"].astype(str) + ": " + d["report_target"].astype(str)
        )
        d = d.sort_values(
            "correct_labeling_rate_delta_union_minus_elsherief", ascending=True
        )
        fig, ax = plt.subplots(figsize=(13, max(6, 1 + 0.3 * len(d))))
        fig.suptitle(
            "ElSherief Subset — Labeling Rate \u0394 (Union \u2212 ElSherief)",
            fontsize=13,
            fontweight="bold",
            y=0.98,
        )
        _diverging_bar(
            ax,
            d["label"],
            d["correct_labeling_rate_delta_union_minus_elsherief"],
            "Correct labeling rate \u0394",
        )
        _save(fig, els_dir / "s5_els_annotation_delta.png")

    if not pair.empty:
        dx = pair["worst_di_ratio_delta_union_minus_elsherief"]
        dy = pair["label_gap_abs_delta_union_minus_elsherief"]
        fig, ax = plt.subplots(figsize=(9, 7))
        fig.suptitle(
            "ElSherief Subset — Pairwise DI \u0394 vs. Label Gap \u0394",
            fontsize=13,
            fontweight="bold",
            y=0.98,
        )
        ax.scatter(
            dx, dy, alpha=0.75, s=50, c=_BLUE, edgecolors="#2c5f8a", linewidths=0.5
        )
        ax.axvline(0, color="#888888", linewidth=0.9, linestyle="--")
        ax.axhline(0, color="#888888", linewidth=0.9, linestyle="--")
        ax.set_xlabel("Worst DI \u0394 (union \u2212 ElSherief)", fontsize=9)
        ax.set_ylabel("|Label gap| \u0394 (union \u2212 ElSherief)", fontsize=9)
        _style_ax(ax, grid_axis="both")
        _save(fig, els_dir / "s5_els_pairwise_delta.png")


# ── Orchestrator ──────────────────────────────────────────────────────────────


def run(variant: PipelineVariant = VARIANT_FULL) -> None:
    """Generate all Stage 5 figure families and report the PNG count.

    Parameters
    ----------
    variant : PipelineVariant
        Controls where stage-1 through stage-4 artifacts are read from and
        where stage-5 figures are written (``variant.out_s5``).
    """
    lev_dir = variant.out_s5 / "level_stratified"
    grp_dir = variant.out_s5 / "group_collapsed"
    els_dir = variant.out_s5 / "elsherief"
    ensure_dirs(lev_dir, grp_dir, els_dir)

    level_stratified_figures(lev_dir, variant.out_s1, variant.out_s2, variant.out_s3)
    group_collapsed_figures(grp_dir, variant.out_s4)
    elsherief_figures(els_dir, variant.out_s4)

    pngs = (
        list(lev_dir.glob("*.png"))
        + list(grp_dir.glob("*.png"))
        + list(els_dir.glob("*.png"))
    )
    print(f"[Stage 5 – {variant.name}] Figures complete")
    print(f"  wrote {len(pngs):,} PNG files under {variant.out_s5}")


if __name__ == "__main__":
    run(resolve_variant())
