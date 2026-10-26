"""Build the public, ID-only data release under ``release/``.

The release makes every post-level result in the paper inspectable without
redistributing post text: posts are identified by their source dataset's own
ID, and readers retrieve the text from the original datasets themselves (see
``release/README.md``).

Post IDs per dataset:
  hatexplain  HateXplain post ID (e.g. ``1179055004553900032_twitter``)
  mhs         Measuring Hate Speech ``comment_id``
  elsherief   0-based data-row index into Implicit Hate's
              ``implicit_hate_v1_stg1_posts.tsv``. The Implicit Hate authors
              deliberately release post text without tweet IDs, so this
              release never maps rows to tweet IDs.

Label columns copied unchanged from a source dataset are prefixed
``source_``; every other label column is derived by this project's pipeline.

Pipeline-internal files identify matched posts by ``text_dedup_key``
(normalized post text). This module maps those keys back to post IDs at
export time and modifies no pipeline stage, so building the release cannot
change any result.

Run after the full pipeline and the FPR annotation export are in place:

    python -m audit_pipeline.build_release
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Iterable

import pandas as pd

from audit_pipeline.config import (
    DATA_PATH,
    DATA_PATH_WITH_ELSHERIEF,
    GLOSSARY_PATH,
    OUT_S1,
    OUT_S1_WITH_ELSHERIEF,
    WORKDIR,
)
from audit_pipeline.helpers import map_type_to_coding_level

RELEASE_DIR = WORKDIR / "release"
OUTPUTS_DIR = WORKDIR / "outputs"
FPR_DIR = WORKDIR / "fpr_annotation"

# Generated subdirectories of release/; rebuilt from scratch on every run.
# release/README.md is hand-written and never touched.
GENERATED_DIRS = ("corpus", "matches", "glossary", "fpr", "audit_results")

# Columns holding post text, or text derived from it. None may be released.
POST_TEXT_COLUMNS = frozenset({"text", "post", "post_text", "text_dedup_key"})

# Fields copied unchanged from the source datasets, renamed so they can't be
# mistaken for this project's derived labels.
SOURCE_COLUMNS = {
    "raw_label": "source_raw_label",
    "targets": "source_targets",
    "n_annotations": "source_n_annotations",
}

FPR_JOIN_TABLE_PATH = FPR_DIR / "fpr_join_table.csv"
FPR_ANNOTATOR_PATHS = {
    "annotator1": FPR_DIR / "completed_labels" / "annotator1.tsv",
    "annotator2": FPR_DIR / "completed_labels" / "annotator2.tsv",
}
FPR_METRICS_PATH = FPR_DIR / "outputs" / "fpr_reportable_metrics.txt"

# Audit-pipeline output directories released verbatim, minus s1_matches.tsv
# (which carries post text and is released ID-keyed under matches/ instead).
AUDIT_RESULT_DIRS = (
    "stage1",
    "stage1_tier12",
    "stage1_with_elsherief",
    "stage2",
    "stage2_tier12",
    "stage3",
    "stage3_tier12",
    "stage4",
    "stage4_tier12",
    "robustness_check",
)
AUDIT_RESULT_SUFFIXES = frozenset({".tsv", ".tex", ".md"})

# Standardized post text for every dataset; read only by the leak check.
STANDARDIZED_TEXT_PATHS = (
    OUTPUTS_DIR / "preprocessing" / "01_hatexplain_standardized.tsv",
    OUTPUTS_DIR / "preprocessing" / "02_mhs_standardized.tsv",
    OUTPUTS_DIR / "preprocessing" / "03_elsherief_standardized.tsv",
)

# A released value sharing any run of this many consecutive words with a
# corpus post counts as leaked post text. Long enough that glossary phrases,
# label strings and annotator notes don't collide with posts by chance.
LEAK_NGRAM_WORDS = 8


def read_tsv(path: Path) -> pd.DataFrame:
    """Read a TSV with every cell as an unaltered string."""
    return pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False)


def write_tsv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, sep="\t", index=False)


def post_ids_by_key(corpus: pd.DataFrame) -> pd.Series:
    """Map (dataset, text_dedup_key) to the ';'-joined post IDs sharing it.

    Identical normalized text can appear under several IDs (e.g. reposts).
    The pipeline counts such posts once, so the release lists every ID rather
    than picking one.
    """
    return corpus.groupby(["dataset", "text_dedup_key"], sort=False)["post_id"].agg(
        lambda ids: ";".join(sorted(set(ids)))
    )


def _lookup_post_ids(df: pd.DataFrame, ids_by_key: pd.Series, what: str) -> pd.Series:
    keys = pd.MultiIndex.from_frame(df[["dataset", "text_dedup_key"]])
    post_ids = ids_by_key.reindex(keys)
    missing = int(post_ids.isna().sum())
    if missing:
        raise ValueError(f"{missing} {what} rows have no post ID in the corpus")
    return pd.Series(post_ids.to_numpy(), index=df.index)


def _drop_text_and_mark_sources(df: pd.DataFrame, lead: list[str]) -> pd.DataFrame:
    out = df.drop(columns=[c for c in df.columns if c in POST_TEXT_COLUMNS])
    out = out.rename(columns=SOURCE_COLUMNS)
    lead = [c for c in lead if c in out.columns]
    return out[lead + [c for c in out.columns if c not in lead]]


def build_corpus(corpus: pd.DataFrame) -> pd.DataFrame:
    """One row per post: IDs, source-dataset labels, then derived labels."""
    return _drop_text_and_mark_sources(corpus, ["post_id", "dataset", *SOURCE_COLUMNS.values()])


def build_matches(matches: pd.DataFrame, ids_by_key: pd.Series) -> pd.DataFrame:
    """Stage 1 dogwhistle matches with text keys replaced by post IDs."""
    out = matches.copy()
    out["post_ids"] = _lookup_post_ids(out, ids_by_key, "Stage 1 match")
    return _drop_text_and_mark_sources(out, ["post_ids", "dataset"])


def build_glossary_mapping(reference: pd.DataFrame) -> pd.DataFrame:
    """Glossary term -> target mapping, plus the coding level the pipeline
    derives from each term's dogwhistle type."""
    out = reference.copy()
    out.insert(
        out.columns.get_loc("type") + 1,
        "coding_level",
        out["type"].map(map_type_to_coding_level),
    )
    return out


def load_fpr_annotator(path: Path) -> pd.DataFrame:
    """Return ``row_id``, raw ``judgment`` and ``notes`` from one annotator's
    completed FPR worksheet.

    Annotator 2's sheet went through an Excel round-trip that duplicated its
    headers; the filled-in columns are the second copies (``judgement.1``,
    ``annotator_notes.1``), as in ``fpr_iaa_analysis.ipynb``.
    """
    df = read_tsv(path)
    if "judgement.1" in df.columns:
        df = df.rename(columns={"judgement.1": "judgment", "annotator_notes.1": "notes"})
    else:
        df = df.rename(columns={"annotator_notes": "notes"})
    return df[["row_id", "judgment", "notes"]]


def build_fpr(join_table: pd.DataFrame, annotators: dict[str, pd.DataFrame], ids_by_key: pd.Series) -> pd.DataFrame:
    """One row per FPR sample item: post IDs, match metadata, and each
    annotator's raw judgment and notes.

    Post IDs come from the join table's ``text_dedup_key``, which the sampler
    copied from Stage 1; the annotators' own copies of that key were altered
    by the spreadsheet round-trip for a few rows.
    """
    out = join_table.copy()
    out.insert(1, "post_ids", _lookup_post_ids(out, ids_by_key, "FPR sample"))
    out = out.drop(columns=["text_dedup_key"])
    for name, ann in annotators.items():
        ann = ann.rename(columns={"judgment": f"judgment_{name}", "notes": f"notes_{name}"})
        out = out.merge(ann, on="row_id", how="left", validate="one_to_one")
        if out[f"judgment_{name}"].isna().any():
            raise ValueError(f"FPR sample rows missing from {name}'s worksheet")
    return out


def copy_audit_results(release_dir: Path = RELEASE_DIR) -> None:
    for name in AUDIT_RESULT_DIRS:
        src = OUTPUTS_DIR / name
        for path in sorted(src.rglob("*")):
            if not path.is_file() or path.suffix not in AUDIT_RESULT_SUFFIXES:
                continue
            if path.name == "s1_matches.tsv":
                continue
            dest = release_dir / "audit_results" / name / path.relative_to(src)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)


def _word_ngrams(text: str, n: int = LEAK_NGRAM_WORDS) -> set[int]:
    words = re.findall(r"[a-z0-9']+", text.lower())
    return {hash(" ".join(words[i : i + n])) for i in range(len(words) - n + 1)}


def find_post_text_leaks(paths: Iterable[Path], corpus_texts: Iterable[str]) -> list[str]:
    """Return a description of every way the files in *paths* expose post text.

    Flags (a) any column named in POST_TEXT_COLUMNS and (b) any value sharing a
    LEAK_NGRAM_WORDS-word run with a corpus post. Non-tabular files are
    checked as a whole.
    """
    corpus_ngrams: set[int] = set()
    for text in corpus_texts:
        corpus_ngrams |= _word_ngrams(text)

    problems = []
    for path in paths:
        if path.suffix in {".tsv", ".csv"}:
            df = read_tsv(path) if path.suffix == ".tsv" else pd.read_csv(path, dtype=str, keep_default_na=False)
            for col in sorted(POST_TEXT_COLUMNS & set(df.columns)):
                problems.append(f"{path}: has post-text column {col!r}")
            for col in df.columns:
                if any(_word_ngrams(value) & corpus_ngrams for value in df[col].unique()):
                    problems.append(f"{path}: column {col!r} contains post text")
        elif _word_ngrams(path.read_text(errors="ignore")) & corpus_ngrams:
            problems.append(f"{path}: contains post text")
    return problems


def load_corpus_texts() -> list[str]:
    return [text for path in STANDARDIZED_TEXT_PATHS for text in read_tsv(path)["text"]]


def main() -> None:
    for name in GENERATED_DIRS:
        shutil.rmtree(RELEASE_DIR / name, ignore_errors=True)

    print("[1/6] Corpora ...")
    corpus = read_tsv(DATA_PATH)
    corpus_we = read_tsv(DATA_PATH_WITH_ELSHERIEF)
    ids = post_ids_by_key(corpus)
    ids_we = post_ids_by_key(corpus_we)
    write_tsv(build_corpus(corpus), RELEASE_DIR / "corpus" / "union_primary.tsv")
    write_tsv(build_corpus(corpus_we), RELEASE_DIR / "corpus" / "union_with_implicit_hate.tsv")

    print("[2/6] Dogwhistle matches ...")
    write_tsv(
        build_matches(read_tsv(OUT_S1 / "s1_matches.tsv"), ids),
        RELEASE_DIR / "matches" / "matches_primary.tsv",
    )
    write_tsv(
        build_matches(read_tsv(OUT_S1_WITH_ELSHERIEF / "s1_matches.tsv"), ids_we),
        RELEASE_DIR / "matches" / "matches_with_implicit_hate.tsv",
    )

    print("[3/6] Glossary mapping ...")
    write_tsv(
        build_glossary_mapping(read_tsv(GLOSSARY_PATH)),
        RELEASE_DIR / "glossary" / "glossary_taxonomy_mapping.tsv",
    )

    print("[4/6] FPR annotations ...")
    join_table = pd.read_csv(FPR_JOIN_TABLE_PATH, dtype=str, keep_default_na=False)
    annotators = {name: load_fpr_annotator(path) for name, path in FPR_ANNOTATOR_PATHS.items()}
    # The FPR sample was drawn while the primary corpus still included
    # Implicit Hate, so 47 of its items are ElSherief posts that only the
    # ElSherief-inclusive corpus contains (HateXplain/MHS IDs are identical
    # in both corpora).
    write_tsv(build_fpr(join_table, annotators, ids_we), RELEASE_DIR / "fpr" / "fpr_judgments.tsv")
    shutil.copy2(FPR_METRICS_PATH, RELEASE_DIR / "fpr" / FPR_METRICS_PATH.name)

    print("[5/6] Audit result tables ...")
    copy_audit_results()

    print("[6/6] Checking the release for post text ...")
    released = sorted(p for name in GENERATED_DIRS for p in (RELEASE_DIR / name).rglob("*") if p.is_file())
    problems = find_post_text_leaks(released, load_corpus_texts())
    if problems:
        raise SystemExit("Post text found in release:\n  " + "\n  ".join(problems))
    print(f"Done: {len(released)} files in {RELEASE_DIR}, no post text found.")


if __name__ == "__main__":
    main()
