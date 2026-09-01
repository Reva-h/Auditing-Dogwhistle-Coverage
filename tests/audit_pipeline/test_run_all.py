"""Tests for run_all.py's variant-dispatch and robustness_check gating logic.

Stage runs and robustness_check itself are mocked out here -- this file only
tests the *wiring*: which functions get called, how many times, for which
argv. See test_pipeline_integration.py for a real (synthetic-data) run of
the underlying stages.
"""

from unittest.mock import patch

from audit_pipeline import run_all


class TestVariantDispatch:
    def test_no_args_selects_both_variants(self):
        variants = run_all._parse_args([])
        assert [v.name for v in variants] == ["full", "tier12"]

    def test_variant_flag_selects_one(self):
        variants = run_all._parse_args(["--variant", "full"])
        assert [v.name for v in variants] == ["full"]

        variants = run_all._parse_args(["--variant", "tier12"])
        assert [v.name for v in variants] == ["tier12"]


class TestRobustnessCheckGating:
    def test_robustness_check_runs_once_when_both_variants_requested(self):
        with patch.object(run_all, "run_variant") as mock_run_variant, patch.object(
            run_all.robustness_check, "main"
        ) as mock_robustness_main:
            run_all.main([])

            assert mock_run_variant.call_count == 2
            mock_robustness_main.assert_called_once_with()

    def test_robustness_check_does_not_run_for_single_variant(self):
        with patch.object(run_all, "run_variant") as mock_run_variant, patch.object(
            run_all.robustness_check, "main"
        ) as mock_robustness_main:
            run_all.main(["--variant", "full"])

            assert mock_run_variant.call_count == 1
            mock_robustness_main.assert_not_called()

    def test_robustness_check_does_not_run_for_tier12_only(self):
        with patch.object(run_all, "run_variant") as mock_run_variant, patch.object(
            run_all.robustness_check, "main"
        ) as mock_robustness_main:
            run_all.main(["--variant", "tier12"])

            assert mock_run_variant.call_count == 1
            mock_robustness_main.assert_not_called()
