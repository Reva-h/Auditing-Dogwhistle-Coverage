"""Stage 1: glossary coverage and surface-form matching.

This stage joins standardized benchmark posts to glossary surface forms and
produces the foundational match table used by later annotation and disparity
audits.
"""

from __future__ import annotations

import re

import pandas as pd

from audit_pipeline.config import DATA_PATH, GLOSSARY_PATH, OUT_S1
from audit_pipeline.helpers import (
    build_surface_form_pattern,
    ensure_dirs,
    map_type_to_coding_level,
    normalize_surface_forms,
    parse_list_like,
    write_tsv,
)


def _load_glossary() -> tuple[pd.DataFrame, pd.DataFrame, re.Pattern]:
    """Load and normalize the glossary plus a compiled matching regex.

    Returns the raw normalized glossary, the expanded one-row-per-surface-form
    table, and a single alternation regex used to scan benchmark text.
    """
    glossary = pd.read_csv(GLOSSARY_PATH, sep="\t", low_memory=False)
    required = {"dogwhistle", "surface_forms", "taxonomy_level", "target", "type"}
    missing = sorted(required - set(glossary.columns))
    if missing:
        raise ValueError(f"Glossary missing required columns: {missing}")

    glossary = glossary[list(required)].copy()
    glossary["dogwhistle"] = glossary["dogwhistle"].astype(str).str.strip().str.lower()
    glossary["taxonomy_level"] = (
        glossary["taxonomy_level"].astype(str).str.strip().str.lower()
    )
    glossary["target"] = glossary["target"].astype(str).str.strip().str.lower()
    glossary["type"] = glossary["type"].astype(str).str.strip().str.lower()
    glossary["is_self_referential"] = glossary["type"].str.contains(
        "self-referential", na=False
    )

    rows = []
    all_forms = []
    for _, r in glossary.iterrows():
        forms = normalize_surface_forms(r["surface_forms"])
        for f in forms:
            rows.append(
                {
                    "dogwhistle": r["dogwhistle"],
                    "surface_form": f,
                    "taxonomy_level": r["taxonomy_level"],
                    "target": r["target"],
                    "type": r["type"],
                    "coding_level": map_type_to_coding_level(r["type"]),
                    "is_self_referential": bool(r["is_self_referential"]),
                }
            )
            all_forms.append(f)

    glossary_expanded = pd.DataFrame(rows).drop_duplicates(
        [
            "dogwhistle",
            "surface_form",
            "taxonomy_level",
            "target",
            "type",
            "coding_level",
        ]
    )
    pattern = build_surface_form_pattern(all_forms)
    return glossary, glossary_expanded, pattern


def _extract_matches(data: pd.DataFrame, pattern: re.Pattern) -> pd.DataFrame:
    """Extract matched glossary surface forms from benchmark text.

    If a precomputed matched-terms column exists, prefer it. Otherwise scan the
    free-text column directly with the compiled glossary regex.
    """
    has_precomputed = "matched_glossary_terms" in data.columns

    if has_precomputed:
        data = data.copy()
        data["found_forms"] = data["matched_glossary_terms"].apply(parse_list_like)
    else:
        data = data.copy()
        data["found_forms"] = (
            data["text"]
            .fillna("")
            .astype(str)
            .apply(lambda t: pattern.findall(t.lower()))
        )

    exploded = data.explode("found_forms")
    exploded = exploded.dropna(subset=["found_forms"]).copy()
    exploded["found_forms"] = (
        exploded["found_forms"].astype(str).str.strip().str.lower()
    )
    exploded = exploded[exploded["found_forms"] != ""]
    return exploded


def run() -> None:
    """Build Stage 1 coverage artifacts and the row-level match table."""
    ensure_dirs(OUT_S1)

    data = pd.read_csv(DATA_PATH, sep="\t", low_memory=False)
    required_data = {"text_dedup_key", "text", "binary_hate", "targets", "dataset"}
    missing = sorted(required_data - set(data.columns))
    if missing:
        raise ValueError(f"Input data missing required columns: {missing}")

    glossary, glossary_expanded, pattern = _load_glossary()
    exploded = _extract_matches(data, pattern)

    audit_df = exploded.merge(
        glossary_expanded,
        left_on="found_forms",
        right_on="surface_form",
        how="inner",
    )

    if audit_df.empty:
        s1_matches = pd.DataFrame(
            columns=[
                "text_dedup_key",
                "text",
                "binary_hate",
                "targets",
                "dataset",
                "found_forms",
                "dogwhistle",
                "taxonomy_level",
                "target",
                "type",
                "coding_level",
                "is_self_referential",
            ]
        )
    else:
        # Keep row-level artifact for stage 2 and optional dataset-filter rollups.
        s1_matches = audit_df[
            [
                "text_dedup_key",
                "text",
                "binary_hate",
                "targets",
                "dataset",
                "found_forms",
                "dogwhistle",
                "taxonomy_level",
                "target",
                "type",
                "coding_level",
                "is_self_referential",
            ]
        ].copy()

    # Equal-weight the audit at the (post, dogwhistle) level so repeated surface
    # forms in the same post do not inflate coverage or annotation counts.
    dogwhistle_hits_df = (
        s1_matches.sort_values(
            ["taxonomy_level", "target", "text_dedup_key", "dogwhistle"]
        )
        .drop_duplicates(["taxonomy_level", "target", "text_dedup_key", "dogwhistle"])
        .copy()
    )

    glossary_totals = (
        glossary_expanded.groupby(
            ["taxonomy_level", "target", "coding_level"], as_index=False
        )
        .agg(
            total_glossary_dogwhistles=("dogwhistle", "nunique"),
            total_glossary_types=("type", "nunique"),
            is_self_referential=("is_self_referential", "max"),
        )
        .sort_values(["taxonomy_level", "target"])
    )

    if dogwhistle_hits_df.empty:
        found = glossary_totals[["taxonomy_level", "target", "coding_level"]].copy()
        found["distinct_dogwhistles_found"] = 0
        found["distinct_types_found"] = 0
        found["token_frequency"] = 0
    else:
        found = (
            dogwhistle_hits_df.groupby(
                ["taxonomy_level", "target", "coding_level"], as_index=False
            )
            .agg(
                distinct_dogwhistles_found=("dogwhistle", "nunique"),
                distinct_types_found=("type", "nunique"),
                token_frequency=("dogwhistle", "count"),
            )
            .sort_values(["taxonomy_level", "target"])
        )

    coverage = glossary_totals.merge(
        found, on=["taxonomy_level", "target", "coding_level"], how="left"
    )
    for c in ["distinct_dogwhistles_found", "distinct_types_found", "token_frequency"]:
        coverage[c] = coverage[c].fillna(0).astype(int)
    coverage["presence_rate"] = coverage["distinct_dogwhistles_found"] / coverage[
        "total_glossary_dogwhistles"
    ].where(coverage["total_glossary_dogwhistles"] > 0, pd.NA)
    coverage["type_coverage"] = coverage["distinct_types_found"] / coverage[
        "total_glossary_types"
    ].where(coverage["total_glossary_types"] > 0, pd.NA)

    if dogwhistle_hits_df.empty:
        detailed = pd.DataFrame(
            columns=[
                "taxonomy_level",
                "target",
                "coding_level",
                "dogwhistle",
                "matched_posts",
                "is_self_referential",
            ]
        )
    else:
        detailed = (
            dogwhistle_hits_df.groupby(
                ["taxonomy_level", "target", "coding_level", "dogwhistle"],
                as_index=False,
            )
            .agg(
                matched_posts=("text_dedup_key", "nunique"),
                is_self_referential=("is_self_referential", "max"),
            )
            .sort_values(
                ["taxonomy_level", "target", "matched_posts"],
                ascending=[True, True, False],
            )
        )

    found_keys = set(
        zip(
            detailed["taxonomy_level"],
            detailed["target"],
            detailed["coding_level"],
            detailed["dogwhistle"],
        )
    )
    missing_rows = []
    for _, r in (
        glossary_expanded[
            [
                "taxonomy_level",
                "target",
                "coding_level",
                "dogwhistle",
                "is_self_referential",
            ]
        ]
        .drop_duplicates()
        .iterrows()
    ):
        key = (r["taxonomy_level"], r["target"], r["coding_level"], r["dogwhistle"])
        if key not in found_keys:
            missing_rows.append(
                {
                    "taxonomy_level": r["taxonomy_level"],
                    "target": r["target"],
                    "coding_level": r["coding_level"],
                    "dogwhistle": r["dogwhistle"],
                    "status": "not_found",
                    "is_self_referential": bool(r["is_self_referential"]),
                }
            )
    missing_df = pd.DataFrame(missing_rows)

    p_cov = OUT_S1 / "s1_coverage_by_level_target.tsv"
    p_det = OUT_S1 / "s1_coverage_detailed.tsv"
    p_mis = OUT_S1 / "s1_coverage_missing.tsv"
    p_mat = OUT_S1 / "s1_matches.tsv"

    write_tsv(coverage, p_cov)
    write_tsv(detailed, p_det)
    write_tsv(missing_df, p_mis)
    write_tsv(s1_matches, p_mat)

    print("[Stage 1] Coverage complete")
    print(f"  wrote {len(coverage):,} rows -> {p_cov}")
    print(f"  wrote {len(detailed):,} rows -> {p_det}")
    print(f"  wrote {len(missing_df):,} rows -> {p_mis}")
    print(f"  wrote {len(s1_matches):,} rows -> {p_mat}")


if __name__ == "__main__":
    run()
