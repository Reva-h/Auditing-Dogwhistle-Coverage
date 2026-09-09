"""Regression tests for the c92ea92 stage3 cross-level-consistency fix.

Before c92ea92, cross-level rows were grouped by (target, coding_level) and
ranked by taxonomy_level -- but a given target belongs to exactly one
taxonomy_level, so every group collapsed to a single row, the "adjacent
level" loop never fired, and s3_cross_level_consistency.tsv came out
silently empty (0 rows, no error). The fix groups by
(taxonomy_level, target) and ranks by coding_level instead.
"""

from pathlib import Path

import pandas as pd
import pytest

from audit_pipeline import stage3_disparity
from audit_pipeline.config import PipelineVariant


def _make_variant(tmp_path: Path) -> PipelineVariant:
    return PipelineVariant(
        name="test",
        allowed_tiers=None,
        out_s1=tmp_path / "stage1",
        out_s2=tmp_path / "stage2",
        out_s3=tmp_path / "stage3",
        out_s4=tmp_path / "stage4",
        out_s5=tmp_path / "stage5",
    )


def _write_inputs(variant: PipelineVariant, coverage_rows, annotation_rows) -> None:
    variant.out_s1.mkdir(parents=True, exist_ok=True)
    variant.out_s2.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(coverage_rows).to_csv(
        variant.out_s1 / "s1_coverage_by_level_target.tsv", sep="\t", index=False
    )
    pd.DataFrame(annotation_rows).to_csv(
        variant.out_s2 / "s2_annotation_by_level_target.tsv", sep="\t", index=False
    )


def _two_target_three_level_rows():
    """race:black and race:latinx, each present at L2/L3/L4 -- exercises both
    the pairwise-disparity path (2 targets per level) and the cross-level
    path (3 levels per target) in the same run.
    """
    coverage_rows = []
    annotation_rows = []
    presence = {"black": [0.6, 0.5, 0.4], "latinx": [0.9, 0.8, 0.7]}
    correct = {"black": [0.3, 0.35, 0.4], "latinx": [0.6, 0.55, 0.5]}
    for target in ("black", "latinx"):
        for i, level in enumerate(("L2", "L3", "L4")):
            coverage_rows.append(
                {
                    "taxonomy_level": "race",
                    "target": target,
                    "coding_level": level,
                    "presence_rate": presence[target][i],
                    "type_coverage": 1.0,
                }
            )
            annotation_rows.append(
                {
                    "taxonomy_level": "race",
                    "target": target,
                    "coding_level": level,
                    "correct_labeling_rate": correct[target][i],
                    "failure_rate": 1.0 - correct[target][i],
                    "total_matches": 40,
                }
            )
    return coverage_rows, annotation_rows


def test_cross_level_consistency_nonempty_with_correct_from_to_labels(tmp_path):
    variant = _make_variant(tmp_path)
    coverage_rows, annotation_rows = _two_target_three_level_rows()
    _write_inputs(variant, coverage_rows, annotation_rows)

    stage3_disparity.run(variant)

    cross = pd.read_csv(variant.out_s3 / "s3_cross_level_consistency.tsv", sep="\t")

    # 2 targets x (L2->L3, L3->L4) = 4 transition rows.
    assert len(cross) == 4
    assert set(cross["taxonomy_level"]) == {"race"}
    assert set(cross["target"]) == {"black", "latinx"}
    # Each target must show both transitions, correctly labeled L2->L3 and L3->L4 --
    # this is exactly what the taxonomy_level/coding_level swap bug broke.
    for target in ("black", "latinx"):
        sub = cross[cross["target"] == target].sort_values("coding_level_from")
        assert list(zip(sub["coding_level_from"], sub["coding_level_to"])) == [
            ("L2", "L3"),
            ("L3", "L4"),
        ]

    row_l2_l3 = cross[
        (cross["target"] == "black") & (cross["coding_level_from"] == "L2")
    ].iloc[0]
    assert row_l2_l3["presence_rate_from"] == pytest.approx(0.6)
    assert row_l2_l3["presence_rate_to"] == pytest.approx(0.5)
    assert row_l2_l3["presence_rate_delta"] == pytest.approx(-0.1)


def test_guard_fires_when_no_target_has_more_than_one_level(tmp_path):
    """Every target present at exactly one coding_level -> the adjacent-level
    loop legitimately has nothing to do, cross-level output is legitimately
    empty, and the c92ea92-adjacent `assert not cross.empty` guard (1c7b724)
    must stop the run instead of silently writing an empty table.
    """
    variant = _make_variant(tmp_path)
    coverage_rows = [
        {
            "taxonomy_level": "race",
            "target": "black",
            "coding_level": "L2",
            "presence_rate": 0.6,
            "type_coverage": 1.0,
        },
        {
            "taxonomy_level": "race",
            "target": "latinx",
            "coding_level": "L2",
            "presence_rate": 0.9,
            "type_coverage": 1.0,
        },
    ]
    annotation_rows = [
        {
            "taxonomy_level": "race",
            "target": "black",
            "coding_level": "L2",
            "correct_labeling_rate": 0.3,
            "failure_rate": 0.7,
            "total_matches": 40,
        },
        {
            "taxonomy_level": "race",
            "target": "latinx",
            "coding_level": "L2",
            "correct_labeling_rate": 0.6,
            "failure_rate": 0.4,
            "total_matches": 40,
        },
    ]
    _write_inputs(variant, coverage_rows, annotation_rows)

    with pytest.raises(AssertionError):
        stage3_disparity.run(variant)
