"""End-to-end smoke test: stage1 -> stage2 -> stage4 -> robustness_check,
run against tiny synthetic data for two tier variants, entirely under
pytest's tmp_path (never touching the real, gitignored outputs/ tree).

Purpose: catch full-pipeline *wiring* regressions (a stage that no longer
reads what an earlier stage writes, a PipelineVariant field that stops being
respected, robustness_check no longer finding what stage4 produces) that
isolated unit tests can't catch on their own.

Mechanical note: stage1_coverage.py, stage2_annotation.py, and
stage4_rollup.py each import DATA_PATH/GLOSSARY_PATH directly from
audit_pipeline.config at module load time (`from audit_pipeline.config
import DATA_PATH, ...`). A custom PipelineVariant only redirects *output*
paths (out_s1..out_s4) -- it carries no data/glossary path. So the *input*
paths must be patched on each importing module individually; patching
audit_pipeline.config.DATA_PATH alone would not affect these already-bound
names.
"""

from pathlib import Path

import pandas as pd
import pytest

from audit_pipeline import robustness_check, stage1_coverage, stage2_annotation, stage4_rollup
from audit_pipeline.config import PipelineVariant


def _variant(name: str, tmp_path: Path, allowed_tiers) -> PipelineVariant:
    root = tmp_path / name
    return PipelineVariant(
        name=name,
        allowed_tiers=allowed_tiers,
        out_s1=root / "stage1",
        out_s2=root / "stage2",
        out_s3=root / "stage3",
        out_s4=root / "stage4",
    )


def _glossary_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "dogwhistle": "dw_black_1",
                "surface_forms": "direwolfblack",
                "taxonomy_level": "race",
                "target": "black",
                "type": "stereotype-based target group label",  # -> L2
                "tier": 1,
            },
            {
                "dogwhistle": "dw_black_2",
                "surface_forms": "direwolfblack2",
                "taxonomy_level": "race",
                "target": "black",
                "type": "stereotype-based target group label",  # -> L2
                "tier": 1,
            },
            {
                "dogwhistle": "dw_latinx_1",
                "surface_forms": "direwolflatinx",
                "taxonomy_level": "race",
                "target": "latinx",
                "type": "stereotype-based target group label",  # -> L2
                "tier": 1,
            },
            {
                "dogwhistle": "dw_latinx_2",
                "surface_forms": "direwolflatinx2",
                "taxonomy_level": "race",
                "target": "latinx",
                "type": "concept (policy)",  # -> L3, tier 3 -- excluded under tier12
                "tier": 3,
            },
        ]
    )


def _posts_df() -> pd.DataFrame:
    rows = []
    # black-targeted posts hitting dw_black_1 (L2, tier1): 4 posts, mixed labels.
    for i in range(4):
        rows.append(
            {
                "text_dedup_key": f"black1_{i}",
                "text": f"post about direwolfblack term number {i}",
                "binary_hate": 1 if i < 3 else 0,
                "targets": "black",
                "dataset": "union",
                "cleaned_label": "['race black']",
            }
        )
    # black-targeted posts hitting dw_black_2 (L2, tier1): 2 posts.
    for i in range(2):
        rows.append(
            {
                "text_dedup_key": f"black2_{i}",
                "text": f"post about direwolfblack2 term number {i}",
                "binary_hate": 0,
                "targets": "black",
                "dataset": "union",
                "cleaned_label": "['race black']",
            }
        )
    # latinx-targeted posts hitting dw_latinx_1 (L2, tier1): 4 posts.
    for i in range(4):
        rows.append(
            {
                "text_dedup_key": f"latinx1_{i}",
                "text": f"post about direwolflatinx term number {i}",
                "binary_hate": 1,
                "targets": "latinx",
                "dataset": "union",
                "cleaned_label": "['race latinx']",
            }
        )
    # latinx-targeted posts hitting dw_latinx_2 (L3, tier3 -- excluded under tier12): 2 posts.
    for i in range(2):
        rows.append(
            {
                "text_dedup_key": f"latinx2_{i}",
                "text": f"post about direwolflatinx2 term number {i}",
                "binary_hate": 1 if i == 0 else 0,
                "targets": "latinx",
                "dataset": "union",
                "cleaned_label": "['race latinx']",
            }
        )
    return pd.DataFrame(rows)


@pytest.fixture
def synthetic_paths(tmp_path, monkeypatch):
    """Write synthetic glossary/data TSVs and patch every stage module's
    DATA_PATH/GLOSSARY_PATH name to point at them.
    """
    data_path = tmp_path / "06_cleaned_labels_glossary_mapped.tsv"
    glossary_path = tmp_path / "06_glossary_label_reference.tsv"
    _posts_df().to_csv(data_path, sep="\t", index=False)
    _glossary_df().to_csv(glossary_path, sep="\t", index=False)

    for module in (stage1_coverage, stage2_annotation, stage4_rollup):
        monkeypatch.setattr(module, "DATA_PATH", data_path, raising=True)
    for module in (stage1_coverage, stage4_rollup):
        monkeypatch.setattr(module, "GLOSSARY_PATH", glossary_path, raising=True)

    return data_path, glossary_path


def _run_stages(variant: PipelineVariant) -> None:
    stage1_coverage.run(variant)
    stage2_annotation.run(variant)
    stage4_rollup.run(variant)


class TestPipelineIntegration:
    def test_full_and_tier12_variants_run_without_error(self, synthetic_paths, tmp_path):
        variant_full = _variant("full", tmp_path, allowed_tiers=None)
        variant_tier12 = _variant("tier12", tmp_path, allowed_tiers=frozenset({1, 2}))

        _run_stages(variant_full)
        _run_stages(variant_tier12)

        # Stage1/2/4's headline artifacts must exist for both variants.
        for variant in (variant_full, variant_tier12):
            assert (variant.out_s1 / "s1_coverage_by_level_target.tsv").exists()
            assert (variant.out_s2 / "s2_annotation_by_level_target.tsv").exists()
            assert (
                variant.out_s4 / "by_group" / "s4a_pairwise_disparity_by_group.tsv"
            ).exists()
            assert (
                variant.out_s4
                / "by_level_group"
                / "s4b_pairwise_disparity_by_level_group.tsv"
            ).exists()

    def test_tier12_excludes_tier3_glossary_entries(self, synthetic_paths, tmp_path):
        variant_full = _variant("full", tmp_path, allowed_tiers=None)
        variant_tier12 = _variant("tier12", tmp_path, allowed_tiers=frozenset({1, 2}))

        _run_stages(variant_full)
        _run_stages(variant_tier12)

        cov_full = pd.read_csv(
            variant_full.out_s1 / "s1_coverage_by_level_target.tsv", sep="\t"
        )
        cov_tier12 = pd.read_csv(
            variant_tier12.out_s1 / "s1_coverage_by_level_target.tsv", sep="\t"
        )
        # Full variant sees both L2 and L3 (dw_latinx_2 is tier-3, type "concept (policy)").
        assert "L3" in set(cov_full["coding_level"])
        # tier12 excludes tier-3 entries entirely -- the L3 row should not exist.
        assert "L3" not in set(cov_tier12["coding_level"])

    def test_robustness_check_runs_against_produced_stage4_outputs(
        self, synthetic_paths, tmp_path
    ):
        variant_full = _variant("full", tmp_path, allowed_tiers=None)
        variant_tier12 = _variant("tier12", tmp_path, allowed_tiers=frozenset({1, 2}))

        _run_stages(variant_full)
        _run_stages(variant_tier12)

        table = robustness_check.build_comparison_table(variant_full, variant_tier12)

        assert not table.empty
        expected_columns = {
            "granularity",
            "report_level",
            "target_a",
            "target_b",
            "level",
            "metric",
            "value_a",
            "value_b",
            "passes_4_5_a",
            "passes_4_5_b",
            "conclusion_changed",
            "direction",
            "unstable_small_n_a",
            "unstable_small_n_b",
        }
        assert expected_columns.issubset(table.columns)
        # black vs latinx must appear at L2, since both are present (and
        # tier-eligible) in both variants.
        black_latinx = table[
            (
                ((table["target_a"] == "black") & (table["target_b"] == "latinx"))
                | ((table["target_a"] == "latinx") & (table["target_b"] == "black"))
            )
            & (table["level"] == "L2")
        ]
        assert not black_latinx.empty
