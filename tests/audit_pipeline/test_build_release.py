"""Tests for audit_pipeline/build_release.py.

The unit tests use small synthetic DataFrames, so they run on a fresh
checkout. TestReleasedFiles checks the tracked release/ tree itself: the
column check always runs, and the full post-text scan runs whenever the
(gitignored) standardized corpora are present locally.
"""

import pandas as pd
import pytest

from audit_pipeline.build_release import (
    GENERATED_DIRS,
    POST_TEXT_COLUMNS,
    RELEASE_DIR,
    STANDARDIZED_TEXT_PATHS,
    build_corpus,
    build_matches,
    find_post_text_leaks,
    load_corpus_texts,
    load_fpr_annotator,
    post_ids_by_key,
    read_tsv,
)

POST = "the quick brown fox jumps over the lazy dog near the old river bank"


def _corpus():
    return pd.DataFrame(
        {
            "post_id": ["p2", "p1", "p3", "1"],
            "text": [POST, POST, "other post", "other post"],
            "raw_label": ["0.9", "0.9", "normal", "-1.2"],
            "binary_hate": ["1", "1", "0", "0"],
            "targets": ["race_black", "race_black", "", "gender_women"],
            "dataset": ["mhs", "mhs", "hatexplain", "mhs"],
            "text_dedup_key": ["k1", "k1", "k2", "k2"],
            "n_annotations": ["3", "3", "", "4"],
            "cleaned_label": ["['race_black']", "['race_black']", "[]", "['gender_women']"],
        }
    )


class TestPostIdsByKey:
    def test_joins_every_id_sharing_a_key_within_a_dataset(self):
        ids = post_ids_by_key(_corpus())
        assert ids[("mhs", "k1")] == "p1;p2"

    def test_keeps_datasets_apart(self):
        ids = post_ids_by_key(_corpus())
        assert ids[("hatexplain", "k2")] == "p3"
        assert ids[("mhs", "k2")] == "1"


class TestBuildCorpus:
    def test_drops_text_and_prefixes_source_columns(self):
        out = build_corpus(_corpus())
        assert POST_TEXT_COLUMNS.isdisjoint(out.columns)
        assert list(out.columns) == [
            "post_id",
            "dataset",
            "source_raw_label",
            "source_targets",
            "source_n_annotations",
            "binary_hate",
            "cleaned_label",
        ]

    def test_values_unchanged(self):
        out = build_corpus(_corpus())
        assert out["source_raw_label"].tolist() == ["0.9", "0.9", "normal", "-1.2"]
        assert out["cleaned_label"].tolist() == _corpus()["cleaned_label"].tolist()


class TestBuildMatches:
    def _matches(self, key="k1"):
        return pd.DataFrame(
            {
                "text_dedup_key": [key],
                "text": [POST],
                "binary_hate": ["1"],
                "targets": ["race_black"],
                "dataset": ["mhs"],
                "dogwhistle": ["fox"],
            }
        )

    def test_replaces_text_key_with_post_ids(self):
        out = build_matches(self._matches(), post_ids_by_key(_corpus()))
        assert out.iloc[0]["post_ids"] == "p1;p2"
        assert list(out.columns) == ["post_ids", "dataset", "binary_hate", "source_targets", "dogwhistle"]

    def test_raises_on_key_missing_from_corpus(self):
        with pytest.raises(ValueError, match="no post ID"):
            build_matches(self._matches(key="unseen"), post_ids_by_key(_corpus()))


class TestLoadFprAnnotator:
    def test_standard_layout(self, tmp_path):
        path = tmp_path / "a1.tsv"
        path.write_text("row_id\tpost_text\tjudgment\tannotator_notes\n1\tsome post\tHateful\tok\n")
        out = load_fpr_annotator(path)
        assert out.to_dict("records") == [{"row_id": "1", "judgment": "Hateful"}]

    def test_uses_second_copy_of_duplicated_headers(self, tmp_path):
        path = tmp_path / "a2.tsv"
        path.write_text(
            "row_id\tjudgement\tannotator_notes\tjudgement\tannotator_notes\n"
            "1\t\t\tNot Hateful\tsarcastic\n"
        )
        out = load_fpr_annotator(path)
        assert out.to_dict("records") == [{"row_id": "1", "judgment": "Not Hateful"}]


class TestFindPostTextLeaks:
    def _write(self, tmp_path, **columns):
        path = tmp_path / "f.tsv"
        pd.DataFrame(columns).to_csv(path, sep="\t", index=False)
        return path

    def test_flags_text_column_by_name(self, tmp_path):
        path = self._write(tmp_path, post_id=["1"], text_dedup_key=["k1"])
        assert any("text_dedup_key" in p for p in find_post_text_leaks([path], [POST]))

    def test_flags_reformatted_post_chunk_in_any_column(self, tmp_path):
        chunk = " ".join(POST.split()[2:11]).upper()
        path = self._write(tmp_path, notes=[f"annotator wrote: {chunk}!"])
        assert find_post_text_leaks([path], [POST]) == [f"{path}: column 'notes' contains post text"]

    def test_ignores_short_overlaps(self, tmp_path):
        path = self._write(tmp_path, notes=[" ".join(POST.split()[:7])])
        assert find_post_text_leaks([path], [POST]) == []

    def test_checks_non_tabular_files_whole(self, tmp_path):
        path = tmp_path / "metrics.txt"
        path.write_text(f"example: {POST}\n")
        assert find_post_text_leaks([path], [POST]) == [f"{path}: contains post text"]


class TestReleasedFiles:
    def _released(self):
        files = sorted(p for name in GENERATED_DIRS for p in (RELEASE_DIR / name).rglob("*") if p.is_file())
        if not files:
            pytest.skip("release/ has not been built")
        return files

    def test_no_post_text_columns(self):
        for path in self._released():
            if path.suffix == ".tsv":
                assert POST_TEXT_COLUMNS.isdisjoint(read_tsv(path).columns), path

    def test_no_post_text_anywhere(self):
        if not all(p.exists() for p in STANDARDIZED_TEXT_PATHS):
            pytest.skip("standardized corpora not available locally")
        assert find_post_text_leaks(self._released(), load_corpus_texts()) == []
