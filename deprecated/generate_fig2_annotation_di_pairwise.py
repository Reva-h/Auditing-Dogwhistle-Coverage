#!/usr/bin/env python3
"""
generate_fig2_annotation_di_pairwise.py
Pairwise annotation DI ratio figure for all stable group pairs at each coding level.

Merges two disparity sources:
  - stage4/by_level_group/s4b_pairwise_disparity_by_level_group.tsv (fine-grained pairs)
  - stage4/by_group/s4a_pairwise_disparity_by_group.tsv (collapsed groups, incl. LGB vs Trans/NB)

Style is imported directly from generate_figures_final.py so this figure matches
Figure 9 (fig5_worst_di_by_pair_level.pdf) exactly.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from generate_figures_final import STYLE, _panel_label, _read, _save, apply_style

DATA_DIR = Path("outputs/")
S4B_PATH = DATA_DIR / "stage4/by_level_group/s4b_pairwise_disparity_by_level_group.tsv"
S4A_PATH = DATA_DIR / "stage4/by_group/s4a_pairwise_disparity_by_group.tsv"
OUT_PATH = DATA_DIR / "figures_final/fig2_annotation_di_by_pair_level.pdf"

DI_THRESHOLD = 0.80
KEY_COLS = ["target_a", "target_b", "coding_level"]
LEVELS = ["L2", "L3", "L4"]


def _filter_stable(df: pd.DataFrame) -> pd.DataFrame:
    return df[~df["unstable_small_n"].astype(bool)].dropna(subset=["annotation_di_ratio"])


def load_and_merge() -> pd.DataFrame:
    s4b_stable = _filter_stable(_read(S4B_PATH)).copy()
    s4a_stable = _filter_stable(_read(S4A_PATH)).copy()
    s4b_stable["source_file"] = "s4b"
    s4a_stable["source_file"] = "s4a"

    s4b_keys = set(map(tuple, s4b_stable[KEY_COLS].values))
    s4a_keys = set(map(tuple, s4a_stable[KEY_COLS].values))
    overlap_keys = s4b_keys & s4a_keys

    print("=" * 80)
    print("OVERLAP CHECK (s4a vs s4b, stable rows only)")
    print("=" * 80)
    if overlap_keys:
        print(f"{len(overlap_keys)} pair x coding_level combination(s) appear in BOTH files. "
              f"Using s4b value (finer granularity) for these; dropping the s4a duplicate.")
        overlap_mask_a = s4a_stable[KEY_COLS].apply(tuple, axis=1).isin(overlap_keys)
        overlap_mask_b = s4b_stable[KEY_COLS].apply(tuple, axis=1).isin(overlap_keys)
        cols = KEY_COLS + ["annotation_di_ratio"]
        print("-- overlapping s4a rows (dropped) --")
        print(s4a_stable[overlap_mask_a][cols].to_string(index=False))
        print("-- overlapping s4b rows (kept) --")
        print(s4b_stable[overlap_mask_b][cols].to_string(index=False))
        s4a_stable = s4a_stable[~overlap_mask_a]
    else:
        print("No overlapping pair x coding_level combinations found.")
    print("=" * 80 + "\n")

    return pd.concat([s4b_stable, s4a_stable], ignore_index=True)


def build_pair_table(merged: pd.DataFrame) -> pd.DataFrame:
    # target_a/target_b already use the paper's canonical casing (e.g. "LGB",
    # "Trans/NB"; lowercase for everything else) — do not force-lowercase here,
    # or acronyms/proper nouns lose their casing.
    out = pd.DataFrame(
        {
            "coding_level": merged["coding_level"],
            "pair_label": [
                f"{a} vs {b}" for a, b in zip(merged["target_a"], merged["target_b"])
            ],
            "annotation_di_ratio": merged["annotation_di_ratio"],
            "passes_4_5_rule": merged["annotation_di_ratio"] >= DI_THRESHOLD,
            "source_file": merged["source_file"],
        }
    )
    level_order = {lvl: i for i, lvl in enumerate(LEVELS)}
    out = out.assign(_lvl=out["coding_level"].map(level_order))
    out = out.sort_values(["_lvl", "annotation_di_ratio"], ascending=[True, True])
    return out.drop(columns="_lvl").reset_index(drop=True)


def compute_level_candidate_counts(raw_s4b: pd.DataFrame, raw_s4a: pd.DataFrame) -> dict[str, dict[str, int]]:
    """Per-level count of all candidate pairs (pre stability-filter) vs. how many
    were excluded as unstable_small_n. Used to explain sparse panels honestly."""
    s4b = raw_s4b.copy()
    s4a = raw_s4a.copy()
    s4b_keys = set(map(tuple, s4b[KEY_COLS].values))
    s4a_unique = s4a[~s4a[KEY_COLS].apply(tuple, axis=1).isin(s4b_keys)]
    raw_merged = pd.concat([s4b, s4a_unique], ignore_index=True)

    counts = {}
    for level in LEVELS:
        sub = raw_merged[raw_merged["coding_level"] == level]
        total = len(sub)
        unstable = int(sub["unstable_small_n"].astype(bool).sum())
        counts[level] = {"total": total, "unstable": unstable, "stable": total - unstable}
    return counts


def make_figure(table: pd.DataFrame, level_counts: dict[str, dict[str, int]]) -> Path:
    apply_style()
    fig, axes = plt.subplots(
        1, 3, figsize=(STYLE["textwidth_in"], 5.5), constrained_layout=True
    )

    panel_counts: dict[str, int] = {}
    panel_fails: dict[str, list[str]] = {}

    # Max bar count across panels: used to give every bar the same physical
    # thickness regardless of panel, so a sparse panel reads as "mostly empty"
    # rather than "one giant bar" — the resulting empty rows are then labeled.
    max_n = max(
        1, max(len(table[table["coding_level"] == lvl]) for lvl in LEVELS)
    )

    for ax, level in zip(axes, LEVELS):
        ax.set_title("")
        sub = table[table["coding_level"] == level].sort_values(
            "annotation_di_ratio", ascending=True
        )
        n = len(sub)

        if sub.empty:
            ax.axis("off")
            ax.text(
                0.5,
                0.5,
                "No stable pairs\nat this level",
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=STYLE["annotation_fontsize"],
                color=STYLE["colors"]["neutral"],
            )
            _panel_label(ax, level, STYLE["colors"][level])
            panel_counts[level] = 0
            panel_fails[level] = []
            continue

        pairs = sub["pair_label"].tolist()
        di = sub["annotation_di_ratio"].values
        y = np.arange(n)

        colors = [
            STYLE["colors"]["pass"] if v >= DI_THRESHOLD else STYLE["colors"]["fail"]
            for v in di
        ]

        ax.barh(y, di, color=colors)
        ax.axvline(DI_THRESHOLD, color="red", linewidth=1.2, linestyle="--")

        ax.set_yticks(y)
        ax.set_yticklabels(pairs, fontsize=max(5, STYLE["tick_label_fontsize"] - 1))
        ax.set_xlim(0.0, 1.0)
        # Fix the y-range to the busiest panel's bar count so bar thickness is
        # consistent across panels; sparse panels get genuine blank space
        # instead of a single bar stretched to fill the whole axis.
        ax.set_ylim(-0.5, max_n - 0.5)
        ax.set_xlabel("Annotation DI ratio", fontsize=STYLE["axis_label_fontsize"])

        _panel_label(ax, level, STYLE["colors"][level])
        ax.spines["left"].set_visible(False)
        ax.tick_params(left=False)

        if n < max_n:
            counts = level_counts[level]
            note = (
                f"{counts['stable']} of {counts['total']} candidate pairs\n"
                f"stable at {level} ({counts['unstable']} excluded:\n"
                f"small-n instability). Sparse coverage\n"
                f"reflects low match volume at this\n"
                f"coding level, not annotation parity."
            )
            blank_center = (n + max_n) / 2 - 0.5
            ax.text(
                0.5,
                blank_center,
                note,
                ha="center",
                va="center",
                fontsize=STYLE["annotation_fontsize"],
                color=STYLE["colors"]["neutral"],
                linespacing=1.4,
            )

        panel_counts[level] = n
        panel_fails[level] = [p for p, v in zip(pairs, di) if v < DI_THRESHOLD]

    out_path = OUT_PATH
    if out_path.exists():
        out_path = out_path.with_name(out_path.stem + "_v2" + out_path.suffix)
        print(f"FLAG: {OUT_PATH.name} already exists — saving as {out_path.name} instead.\n")

    _save(fig, out_path)

    print(f"\nOutput file: {out_path}")
    for level in LEVELS:
        print(f"  {level}: {panel_counts[level]} bars")
    for level in LEVELS:
        fails = panel_fails[level]
        print(f"  {level} red (fail) pairs: {fails if fails else 'none'}")

    print("\nStyle parameters matched to Figure 9 (fig5_worst_di_by_pair_level.pdf):")
    print(f"  figsize = ({STYLE['textwidth_in']}, 5.5) in, dpi = {STYLE['dpi']}")
    print(
        f"  font.size (tick label) = {STYLE['tick_label_fontsize']}, "
        f"axis label fontsize = {STYLE['axis_label_fontsize']}, "
        f"panel label fontsize = {STYLE['panel_label_fontsize']}"
    )
    print(
        f"  pass (blue) color = {STYLE['colors']['pass']}, "
        f"fail (red) color = {STYLE['colors']['fail']}"
    )
    print("  threshold line: color=red, linewidth=1.2, linestyle='--'")
    print(
        f"  panel label colors: L2={STYLE['colors']['L2']}, "
        f"L3={STYLE['colors']['L3']}, L4={STYLE['colors']['L4']}"
    )
    return out_path


def main() -> None:
    merged = load_and_merge()
    table = build_pair_table(merged)
    level_counts = compute_level_candidate_counts(_read(S4B_PATH), _read(S4A_PATH))

    print("=" * 80)
    print("VERIFICATION TABLE — stable pairwise annotation DI ratios by coding level")
    print("=" * 80)
    print(table.to_string(index=False))
    print("=" * 80 + "\n")

    print("Candidate pair counts by level (context for sparse panels):")
    for level in LEVELS:
        c = level_counts[level]
        print(
            f"  {level}: {c['stable']} stable / {c['total']} candidate "
            f"({c['unstable']} excluded as unstable_small_n)"
        )
    print()

    make_figure(table, level_counts)


if __name__ == "__main__":
    main()
