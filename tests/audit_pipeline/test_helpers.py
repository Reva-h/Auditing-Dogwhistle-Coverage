"""Unit tests for the pure helper functions in audit_pipeline/helpers.py."""

import math

import pandas as pd
import pytest

from audit_pipeline.helpers import (
    build_pairwise_rows,
    map_reporting_group,
    norm_target,
    safe_di,
    safe_di_ratio,
    safe_float,
)


class TestSafeFloat:
    def test_valid_numeric_string(self):
        assert safe_float("0.5") == 0.5

    def test_none_returns_nan(self):
        assert math.isnan(safe_float(None))

    def test_pd_na_returns_nan(self):
        assert math.isnan(safe_float(pd.NA))

    def test_unconvertible_returns_nan(self):
        assert math.isnan(safe_float("not-a-number"))


class TestSafeDiRatio:
    def test_basic_ratio(self):
        assert safe_di_ratio(0.4, 0.8) == 0.5

    def test_nan_propagates(self):
        assert math.isnan(safe_di_ratio(float("nan"), 0.8))

    def test_zero_max_returns_nan(self):
        assert math.isnan(safe_di_ratio(0.0, 0.0))


class TestSafeDi:
    def test_stable_pair_computes_ratio(self):
        assert safe_di(0.4, 0.8, n_a=40, n_b=40, n_min=30) == 0.5

    def test_below_n_min_on_either_side_returns_nan(self):
        assert math.isnan(safe_di(0.4, 0.8, n_a=10, n_b=40, n_min=30))
        assert math.isnan(safe_di(0.4, 0.8, n_a=40, n_b=10, n_min=30))

    def test_zero_high_value_returns_nan(self):
        assert math.isnan(safe_di(0.0, 0.0, n_a=40, n_b=40, n_min=30))


class TestNormTarget:
    def test_lowercases_and_strips(self):
        assert norm_target("  RACE  ") == "race"

    def test_underscore_and_hyphen_become_space(self):
        assert norm_target("middle_eastern") == "middle eastern"
        assert norm_target("middle-eastern") == "middle eastern"

    def test_collapses_internal_whitespace(self):
        assert norm_target("non   binary") == "non binary"

    def test_nonbinary_special_case(self):
        assert norm_target("nonbinary") == "non binary"


class TestMapReportingGroup:
    @pytest.mark.parametrize("target", ["lesbian", "gay", "bisexual"])
    def test_sexuality_lgb_collapses_to_lgb(self, target):
        g = map_reporting_group("sexuality", target)
        assert (g.report_level, g.report_target, g.include) == ("lgbtq", "LGB", True)

    @pytest.mark.parametrize(
        "target",
        ["transgender men", "transgender women", "transgender unspecified", "non binary"],
    )
    def test_gender_trans_nb_collapses_to_trans_nb(self, target):
        g = map_reporting_group("gender", target)
        assert (g.report_level, g.report_target, g.include) == ("lgbtq", "Trans/NB", True)

    def test_gender_men_women_other_pass_through(self):
        g = map_reporting_group("gender", "women")
        assert (g.report_level, g.report_target, g.include) == ("gender", "women", True)

    def test_sexuality_non_lgb_excluded(self):
        g = map_reporting_group("sexuality", "asexual")
        assert g.include is False

    @pytest.mark.parametrize(
        "level", ["race", "religion", "politics", "disability", "origin"]
    )
    def test_allowed_taxonomy_levels_included(self, level):
        g = map_reporting_group(level, "some_target")
        assert (g.report_level, g.include) == (level, True)

    def test_unrecognized_level_excluded(self):
        g = map_reporting_group("something_else", "x")
        assert g.include is False


class TestBuildPairwiseRows:
    def _make_group_df(self):
        return pd.DataFrame(
            [
                {
                    "coding_level": "L2",
                    "target": "a",
                    "presence_rate": 0.8,
                    "type_coverage": 1.0,
                    "correct_labeling_rate": 0.6,
                    "failure_rate": 0.4,
                    "total_matches": 40,
                },
                {
                    "coding_level": "L2",
                    "target": "b",
                    "presence_rate": 0.4,
                    "type_coverage": 0.5,
                    "correct_labeling_rate": 0.3,
                    "failure_rate": 0.7,
                    "total_matches": 40,
                },
                {
                    "coding_level": "L2",
                    "target": "c",
                    "presence_rate": 0.9,
                    "type_coverage": 1.0,
                    "correct_labeling_rate": 0.5,
                    "failure_rate": 0.5,
                    "total_matches": 5,  # below n_min -> pairs with c are unstable
                },
            ]
        )

    def test_produces_one_row_per_combination_within_level(self):
        rows = build_pairwise_rows(
            self._make_group_df(),
            presence_col="presence_rate",
            type_cov_col="type_coverage",
            labeling_col="correct_labeling_rate",
            failure_col="failure_rate",
            matches_col="total_matches",
            level_col="coding_level",
            target_col="target",
            n_min=30,
        )
        # 3 targets in one level -> C(3, 2) = 3 pairwise rows.
        assert len(rows) == 3

    def test_worst_di_ratio_is_min_of_presence_and_type_coverage(self):
        rows = build_pairwise_rows(
            self._make_group_df(),
            presence_col="presence_rate",
            type_cov_col="type_coverage",
            labeling_col="correct_labeling_rate",
            failure_col="failure_rate",
            matches_col="total_matches",
            level_col="coding_level",
            target_col="target",
            n_min=30,
        )
        row_ab = next(
            r
            for r in rows
            if {r["target_a"], r["target_b"]} == {"a", "b"}
        )
        # presence DI = 0.4/0.8 = 0.5, type-coverage DI = 0.5/1.0 = 0.5 -> worst = 0.5
        assert row_ab["worst_di_ratio"] == pytest.approx(0.5)
        assert row_ab["annotation_di_ratio"] == pytest.approx(0.3 / 0.6)

    def test_small_n_pair_flagged_unstable_and_di_is_nan(self):
        rows = build_pairwise_rows(
            self._make_group_df(),
            presence_col="presence_rate",
            type_cov_col="type_coverage",
            labeling_col="correct_labeling_rate",
            failure_col="failure_rate",
            matches_col="total_matches",
            level_col="coding_level",
            target_col="target",
            n_min=30,
        )
        row_ac = next(
            r
            for r in rows
            if {r["target_a"], r["target_b"]} == {"a", "c"}
        )
        assert row_ac["unstable_small_n"] is True
        assert math.isnan(row_ac["worst_di_ratio"])
