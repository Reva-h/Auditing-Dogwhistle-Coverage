"""Generate the paper's Table 3 (Tier-1+2 robustness comparison) from
``robustness_comparison.tsv`` instead of hand-typing it.

The previous version of this table (``robustness_table_for_paper.tsv``) was
hand-built by copying numbers out of an old run rather than generated from
code -- that's how it drifted out of sync with the underlying data after the
ElSherief-inclusion fix. This module is the fix for *that*: it selects the
specific pair/level/metric rows the paper discusses by name from
``outputs/robustness_check/robustness_comparison.tsv`` (see
``audit_pipeline/robustness_check.py``, which must be run first) and
re-derives both a clean TSV and a ready-to-paste LaTeX table every time.

The row selection (``PAPER_ROWS`` below) encodes an editorial decision --
which pairs the paper discusses by name -- and is the one thing that must be
kept in sync by hand when the paper's prose changes. Everything downstream
of that selection (the actual DI values, pass/fail verdicts, which cells get
bolded as flips, and the row/flip counts quoted in the caption) is derived,
not typed.

Can be run standalone once ``robustness_check.py`` has been run::

    python -m audit_pipeline.generate_robustness_table_for_paper
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from audit_pipeline.config import DI_THRESHOLD, N_MIN
from audit_pipeline.helpers import ensure_dirs, write_tsv
from audit_pipeline.robustness_check import OUT_ROBUSTNESS

# Each entry is one row of the paper's Table 3, in display order.
# ``block`` groups rows for \addlinespace insertion (mirrors the level
# groupings the paper's table uses: L2, L3-annotation, L3-coverage, L4,
# pooled).
PAPER_ROWS: list[dict[str, object]] = [
    dict(block=1, report_level="race", target_a="black", target_b="latinx", level="L2", metric="annotation", granularity="fine"),
    dict(block=1, report_level="race", target_a="black", target_b="middle eastern", level="L2", metric="annotation", granularity="fine"),
    dict(block=1, report_level="race", target_a="latinx", target_b="middle eastern", level="L2", metric="annotation", granularity="fine"),
    dict(block=1, report_level="religion", target_a="jewish", target_b="muslim", level="L2", metric="annotation", granularity="fine"),
    dict(block=1, report_level="race", target_a="black", target_b="middle eastern", level="L2", metric="coverage", granularity="fine"),

    dict(block=2, report_level="race", target_a="black", target_b="latinx", level="L3", metric="annotation", granularity="fine"),
    dict(block=2, report_level="race", target_a="black", target_b="middle eastern", level="L3", metric="annotation", granularity="fine"),
    dict(block=2, report_level="race", target_a="latinx", target_b="middle eastern", level="L3", metric="annotation", granularity="fine"),
    dict(block=2, report_level="religion", target_a="jewish", target_b="muslim", level="L3", metric="annotation", granularity="fine"),
    dict(block=2, report_level="lgbtq", target_a="LGB", target_b="Trans/NB", level="L3", metric="annotation", granularity="collapsed"),

    dict(block=3, report_level="race", target_a="black", target_b="latinx", level="L3", metric="coverage", granularity="fine"),
    dict(block=3, report_level="race", target_a="black", target_b="middle eastern", level="L3", metric="coverage", granularity="fine"),
    dict(block=3, report_level="race", target_a="latinx", target_b="middle eastern", level="L3", metric="coverage", granularity="fine"),
    dict(block=3, report_level="religion", target_a="jewish", target_b="muslim", level="L3", metric="coverage", granularity="fine"),
    dict(block=3, report_level="lgbtq", target_a="LGB", target_b="Trans/NB", level="L3", metric="coverage", granularity="collapsed"),

    dict(block=4, report_level="politics", target_a="liberal", target_b="republican", level="L4", metric="annotation", granularity="fine"),

    dict(block=5, report_level="lgbtq", target_a="LGB", target_b="Trans/NB", level="pooled", metric="coverage", granularity="collapsed"),
    dict(block=5, report_level="race", target_a="latinx", target_b="middle eastern", level="pooled", metric="coverage", granularity="fine"),
    dict(block=5, report_level="politics", target_a="liberal", target_b="republican", level="pooled", metric="coverage", granularity="fine"),
]


def _parse_bool(value: object) -> bool | None:
    """Coerce a TSV-round-tripped boolean/NA cell to True/False/None."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("true", "1"):
        return True
    if text in ("false", "0"):
        return False
    return None


def _tex_target_name(report_level: str, target: str) -> str:
    """Format e.g. ("race", "middle eastern") -> "race:middle\\mbox{\\_}eastern"."""
    slug = target.replace(" ", "_").replace("_", r"\mbox{\_}")
    return f"{report_level}:{slug}"


def _find_row(comparison: pd.DataFrame, spec: dict[str, object]) -> pd.Series:
    """Look up one (pair, level, metric, granularity) row, order-insensitive
    on target_a/target_b. Raises if the row is missing or ambiguous -- a
    stale/renamed pair should break this script loudly, not silently drop a
    row from the paper's table.
    """
    a, b = spec["target_a"], spec["target_b"]
    mask = (
        (comparison["granularity"] == spec["granularity"])
        & (comparison["level"] == spec["level"])
        & (comparison["metric"] == spec["metric"])
        & (
            ((comparison["target_a"] == a) & (comparison["target_b"] == b))
            | ((comparison["target_a"] == b) & (comparison["target_b"] == a))
        )
    )
    matches = comparison[mask]
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one robustness_comparison.tsv row for "
            f"{a!r} vs {b!r} ({spec['granularity']}, {spec['level']}, "
            f"{spec['metric']}), found {len(matches)}. Re-run "
            f"robustness_check.py, or update PAPER_ROWS if this pair's "
            f"naming has changed."
        )
    return matches.iloc[0]


def build_paper_table(comparison: pd.DataFrame) -> pd.DataFrame:
    records = []
    for spec in PAPER_ROWS:
        row = _find_row(comparison, spec)
        passes_full = _parse_bool(row["passes_4_5_a"])
        passes_tier12 = _parse_bool(row["passes_4_5_b"])
        flipped = (
            passes_full is not None
            and passes_tier12 is not None
            and passes_full != passes_tier12
        )
        pair_label = (
            f"{_tex_target_name(spec['report_level'], spec['target_a'])} vs.\\ "
            f"{_tex_target_name(spec['report_level'], spec['target_b'])}"
        )
        verdict_full = "pass" if passes_full else "fail" if passes_full is False else "NA"
        verdict_tier12 = "pass" if passes_tier12 else "fail" if passes_tier12 is False else "NA"
        verdict_text = f"{verdict_full} $\\to$ {verdict_tier12}"
        if flipped:
            verdict_text = f"\\textbf{{{verdict_text}}}"

        records.append(
            {
                "block": spec["block"],
                "pair": f"{spec['report_level']}:{spec['target_a']} vs. {spec['report_level']}:{spec['target_b']}",
                "pair_tex": pair_label,
                "level": "Pooled" if spec["level"] == "pooled" else spec["level"],
                "metric": spec["metric"].capitalize(),
                "full": row["value_a"],
                "tier1_2": row["value_b"],
                "verdict_full": verdict_full,
                "verdict_tier12": verdict_tier12,
                "flipped": flipped,
                "verdict_tex": verdict_text,
            }
        )
    return pd.DataFrame.from_records(records)


def render_latex_table(table: pd.DataFrame) -> str:
    n_rows = len(table)
    n_flips = int(table["flipped"].sum())
    flip_word = "flip" if n_flips == 1 else "flips"

    lines = [
        r"\begin{table*}[ht]",
        r"\centering",
        r"\small",
        r"\begin{tabular}{@{} l c l r r l @{}}",
        r"\toprule",
        r"\textbf{Pair} & \textbf{Level} & \textbf{Metric} & \textbf{Full} & "
        r"\textbf{Tier 1+2} & \textbf{4/5 rule (full $\to$ T1+2)} \\",
        r"\midrule",
    ]

    prev_block = None
    for _, r in table.iterrows():
        if prev_block is not None and r["block"] != prev_block:
            lines.append(r"\addlinespace")
        prev_block = r["block"]
        lines.append(
            f"{r['pair_tex']} & {r['level']} & {r['metric']} & "
            f"{r['full']:.3f} & {r['tier1_2']:.3f} & {r['verdict_tex']} \\\\"
        )

    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\caption{Tier 1+2 robustness comparison for every pair discussed in "
        r"the main text and \S\ref{app:provenance}, at every level where it "
        f"is stable ($n \\geq {N_MIN}$ both groups). "
        + (
            f"Pass/fail {flip_word} " + ("is" if n_flips == 1 else "are") + " bolded."
            if n_flips
            else "There are no pass/fail flips in this selection."
        )
        + f" This table covers {n_rows} pair/level/metric rows; the complete "
        r"105-row comparison across all reporting-group granularities is "
        r"available in the released code and data.}",
        r"\label{tab:robustness}",
        r"\end{table*}",
    ]
    return "\n".join(lines)


def main(base_dir: Path | None = None) -> None:
    if base_dir is None:
        base_dir = OUT_ROBUSTNESS
    ensure_dirs(base_dir)

    comparison_path = base_dir / "robustness_comparison.tsv"
    if not comparison_path.exists():
        raise FileNotFoundError(
            f"{comparison_path} not found -- run "
            f"`python -m audit_pipeline.robustness_check` first."
        )
    comparison = pd.read_csv(comparison_path, sep="\t", low_memory=False)

    table = build_paper_table(comparison)
    write_tsv(
        table.drop(columns=["pair_tex", "verdict_tex"]),
        base_dir / "robustness_table_for_paper.tsv",
    )

    tex = render_latex_table(table)
    tex_path = base_dir / "robustness_table_for_paper.tex"
    tex_path.write_text(tex + "\n", encoding="utf-8")

    print(f"Paper robustness table written to: {base_dir}")
    print(f"  {len(table)} rows -> robustness_table_for_paper.tsv")
    print(f"  {int(table['flipped'].sum())} pass/fail flip(s) -> robustness_table_for_paper.tex")
    print()
    print(tex)


if __name__ == "__main__":
    main()
