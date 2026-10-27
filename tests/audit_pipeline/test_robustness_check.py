"""Unit tests for audit_pipeline/robustness_check.py.

All fixtures are small, hand-computed synthetic DataFrames -- never the real
(gitignored, private) outputs/ tree, so these tests are self-contained and
run on a fresh checkout with no data files present.
"""

import math
from pathlib import Path

import pandas as pd
import pytest

from audit_pipeline.config import PipelineVariant
from audit_pipeline.robustness_check import build_comparison_table, compute_pooled_coverage_di


class TestComputePooledCoverageDi:
    def test_matches_hand_computed_example(self):
        # X: 7/10 dogwhistles found across all levels, all types found.
        # Y: 26/77 dogwhistles found, 8/9 types found.
        # presence DI = min(0.7, 0.337662...) / max(...) = 0.337662.../0.7 = 0.482375...
        coverage = pd.DataFrame(
            [
                {
                    "report_target": "X",
                    "distinct_dogwhistles_found": 2,
                    "total_glossary_dogwhistles": 3,
                    "distinct_types_found": 1,
                    "total_glossary_types": 1,
                },
                {
                    "report_target": "X",
                    "distinct_dogwhistles_found": 5,
                    "total_glossary_dogwhistles": 7,
                    "distinct_types_found": 1,
                    "total_glossary_types": 1,
                },
                {
                    "report_target": "Y",
                    "distinct_dogwhistles_found": 7,
                    "total_glossary_dogwhistles": 19,
                    "distinct_types_found": 2,
                    "total_glossary_types": 2,
                },
                {
                    "report_target": "Y",
                    "distinct_dogwhistles_found": 19,
                    "total_glossary_dogwhistles": 58,
                    "distinct_types_found": 6,
                    "total_glossary_types": 7,
                },
            ]
        )
        result = compute_pooled_coverage_di(coverage, "X", "Y")
        assert result["presence_rate_a"] == pytest.approx(7 / 10)
        assert result["presence_rate_b"] == pytest.approx(26 / 77)
        assert result["worst_di_ratio"] == pytest.approx((26 / 77) / (7 / 10), abs=1e-4)

    def test_missing_target_returns_nan(self):
        coverage = pd.DataFrame(
            [
                {
                    "report_target": "X",
                    "distinct_dogwhistles_found": 5,
                    "total_glossary_dogwhistles": 10,
                    "distinct_types_found": 1,
                    "total_glossary_types": 1,
                }
            ]
        )
        result = compute_pooled_coverage_di(coverage, "X", "not_present")
        assert math.isnan(result["worst_di_ratio"])


_PAIRWISE_COLUMNS = [
    "target_a",
    "target_b",
    "coding_level",
    "report_level",
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
_COVERAGE_COLUMNS = [
    "report_target",
    "distinct_dogwhistles_found",
    "total_glossary_dogwhistles",
    "distinct_types_found",
    "total_glossary_types",
]


def _frame(rows: list[dict], columns: list[str]) -> pd.DataFrame:
    """Like pd.DataFrame(rows), but keeps the real schema's column headers
    even when *rows* is empty -- matching how write_tsv always writes a
    header row, even for an empty table, in the real pipeline.
    """
    return pd.DataFrame(rows, columns=columns) if rows else pd.DataFrame(columns=columns)


def _write_s4(
    out_s4: Path,
    pairwise_fine: list[dict],
    pairwise_collapsed: list[dict],
    coverage_fine: list[dict],
    coverage_collapsed: list[dict],
) -> None:
    fine_dir = out_s4 / "by_level_group"
    collapsed_dir = out_s4 / "by_group"
    fine_dir.mkdir(parents=True, exist_ok=True)
    collapsed_dir.mkdir(parents=True, exist_ok=True)
    _frame(pairwise_fine, _PAIRWISE_COLUMNS).to_csv(
        fine_dir / "s4b_pairwise_disparity_by_level_group.tsv", sep="\t", index=False
    )
    _frame(coverage_fine, _COVERAGE_COLUMNS).to_csv(
        fine_dir / "s4b_coverage_by_level_group.tsv", sep="\t", index=False
    )
    _frame(pairwise_collapsed, _PAIRWISE_COLUMNS).to_csv(
        collapsed_dir / "s4a_pairwise_disparity_by_group.tsv", sep="\t", index=False
    )
    _frame(coverage_collapsed, _COVERAGE_COLUMNS).to_csv(
        collapsed_dir / "s4a_coverage_by_group.tsv", sep="\t", index=False
    )


def _variant(name: str, tmp_path: Path) -> PipelineVariant:
    return PipelineVariant(
        name=name,
        allowed_tiers=None,
        out_s1=tmp_path / name / "stage1",
        out_s2=tmp_path / name / "stage2",
        out_s3=tmp_path / name / "stage3",
        out_s4=tmp_path / name / "stage4",
    )


def _pairwise_row(target_a, target_b, coding_level, report_level, worst_di, ann_di, unstable):
    return {
        "target_a": target_a,
        "target_b": target_b,
        "coding_level": coding_level,
        "report_level": report_level,
        "presence_rate_a": 0.5,
        "presence_rate_b": 0.5,
        "presence_rate_di_ratio": worst_di,
        "type_coverage_a": 1.0,
        "type_coverage_b": 1.0,
        "type_coverage_di_ratio": 1.0,
        "worst_di_ratio": worst_di,
        "correct_labeling_rate_a": 0.5,
        "correct_labeling_rate_b": 0.5,
        "annotation_di_ratio": ann_di,
        "labeling_rate_gap": 0.0,
        "labeling_rate_gap_abs": 0.0,
        "failure_rate_a": 0.5,
        "failure_rate_b": 0.5,
        "failure_rate_gap": 0.0,
        "failure_rate_gap_abs": 0.0,
        "total_matches_a": 40,
        "total_matches_b": 40,
        "unstable_small_n": unstable,
    }


class TestBuildComparisonTable:
    def test_fail_to_pass_flip_is_flagged(self, tmp_path):
        variant_a = _variant("full", tmp_path)
        variant_b = _variant("tier12", tmp_path)

        fine_row_a = _pairwise_row(
            "x", "y", "L3", "race", worst_di=0.9, ann_di=0.70, unstable=False
        )
        fine_row_b = _pairwise_row(
            "x", "y", "L3", "race", worst_di=0.9, ann_di=0.95, unstable=False
        )
        _write_s4(
            variant_a.out_s4,
            pairwise_fine=[fine_row_a],
            pairwise_collapsed=[],
            coverage_fine=[],
            coverage_collapsed=[],
        )
        _write_s4(
            variant_b.out_s4,
            pairwise_fine=[fine_row_b],
            pairwise_collapsed=[],
            coverage_fine=[],
            coverage_collapsed=[],
        )

        table = build_comparison_table(variant_a, variant_b)
        row = table[
            (table["granularity"] == "fine")
            & (table["metric"] == "annotation")
            & (table["level"] == "L3")
        ].iloc[0]

        assert row["value_a"] == pytest.approx(0.70)
        assert row["value_b"] == pytest.approx(0.95)
        assert row["passes_4_5_a"] is False
        assert row["passes_4_5_b"] is True
        assert row["conclusion_changed"] is True
        assert row["direction"] == "less_disparate"

    def test_fail_to_fail_is_not_flagged_as_changed(self, tmp_path):
        variant_a = _variant("full", tmp_path)
        variant_b = _variant("tier12", tmp_path)

        row_a = _pairwise_row("p", "q", "L2", "lgbtq", worst_di=0.5, ann_di=0.5, unstable=False)
        row_b = _pairwise_row("p", "q", "L2", "lgbtq", worst_di=0.6, ann_di=0.6, unstable=False)
        _write_s4(
            variant_a.out_s4,
            pairwise_fine=[],
            pairwise_collapsed=[row_a],
            coverage_fine=[],
            coverage_collapsed=[],
        )
        _write_s4(
            variant_b.out_s4,
            pairwise_fine=[],
            pairwise_collapsed=[row_b],
            coverage_fine=[],
            coverage_collapsed=[],
        )

        table = build_comparison_table(variant_a, variant_b)
        row = table[
            (table["granularity"] == "collapsed") & (table["metric"] == "coverage")
        ].iloc[0]
        assert row["passes_4_5_a"] is False
        assert row["passes_4_5_b"] is False
        assert row["conclusion_changed"] is False
        assert row["direction"] == "less_disparate"

    def test_pair_unstable_in_one_variant_has_na_conclusion(self, tmp_path):
        variant_a = _variant("full", tmp_path)
        variant_b = _variant("tier12", tmp_path)

        # Stable in variant_a, unstable (NaN DI values, matching safe_di's
        # real behaviour for small-n pairs) in variant_b.
        row_a = _pairwise_row("m", "n", "L2", "race", worst_di=0.7, ann_di=0.7, unstable=False)
        row_b = _pairwise_row(
            "m", "n", "L2", "race", worst_di=float("nan"), ann_di=float("nan"), unstable=True
        )
        _write_s4(
            variant_a.out_s4,
            pairwise_fine=[row_a],
            pairwise_collapsed=[],
            coverage_fine=[],
            coverage_collapsed=[],
        )
        _write_s4(
            variant_b.out_s4,
            pairwise_fine=[row_b],
            pairwise_collapsed=[],
            coverage_fine=[],
            coverage_collapsed=[],
        )

        table = build_comparison_table(variant_a, variant_b)
        row = table[
            (table["granularity"] == "fine") & (table["metric"] == "coverage")
        ].iloc[0]
        assert bool(row["unstable_small_n_b"]) is True
        assert row["passes_4_5_b"] is pd.NA
        assert row["conclusion_changed"] is pd.NA

    def test_pooled_row_present_for_each_pair(self, tmp_path):
        variant_a = _variant("full", tmp_path)
        variant_b = _variant("tier12", tmp_path)

        row_a = _pairwise_row("p", "q", "L3", "lgbtq", worst_di=0.42, ann_di=0.87, unstable=False)
        row_b = _pairwise_row("p", "q", "L3", "lgbtq", worst_di=0.50, ann_di=0.94, unstable=False)
        coverage_a = [
            {
                "report_target": "p",
                "distinct_dogwhistles_found": 4,
                "total_glossary_dogwhistles": 5,
                "distinct_types_found": 2,
                "total_glossary_types": 2,
            },
            {
                "report_target": "q",
                "distinct_dogwhistles_found": 7,
                "total_glossary_dogwhistles": 21,
                "distinct_types_found": 2,
                "total_glossary_types": 2,
            },
        ]
        coverage_b = [
            {
                "report_target": "p",
                "distinct_dogwhistles_found": 3,
                "total_glossary_dogwhistles": 5,
                "distinct_types_found": 2,
                "total_glossary_types": 2,
            },
            {
                "report_target": "q",
                "distinct_dogwhistles_found": 2,
                "total_glossary_dogwhistles": 4,
                "distinct_types_found": 1,
                "total_glossary_types": 2,
            },
        ]
        _write_s4(
            variant_a.out_s4,
            pairwise_fine=[],
            pairwise_collapsed=[row_a],
            coverage_fine=[],
            coverage_collapsed=coverage_a,
        )
        _write_s4(
            variant_b.out_s4,
            pairwise_fine=[],
            pairwise_collapsed=[row_b],
            coverage_fine=[],
            coverage_collapsed=coverage_b,
        )

        table = build_comparison_table(variant_a, variant_b)
        pooled = table[
            (table["granularity"] == "collapsed") & (table["level"] == "pooled")
        ]
        assert len(pooled) == 1
        assert pooled.iloc[0]["metric"] == "coverage"

    def test_empty_inputs_produce_empty_table(self, tmp_path):
        variant_a = _variant("full", tmp_path)
        variant_b = _variant("tier12", tmp_path)
        _write_s4(variant_a.out_s4, [], [], [], [])
        _write_s4(variant_b.out_s4, [], [], [], [])

        table = build_comparison_table(variant_a, variant_b)
        assert table.empty
