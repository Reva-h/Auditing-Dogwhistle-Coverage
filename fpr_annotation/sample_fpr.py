"""
FPR annotation sampler — draws 75 rows per coding level (L2/L3/L4).

If LOCKED_ANNOTATIONS points to a TSV of completed annotations (from a
prior worksheet version), those rows are guaranteed to appear in the new
sample.  The remaining per-level budget is drawn uniformly from the
residual pool.  A personal copy of the new worksheet is written for the
locked annotator with her existing judgments pre-filled.
"""

from pathlib import Path
import pandas as pd

# ── paths ─────────────────────────────────────────────────────────────────────

REPO_ROOT      = Path(__file__).resolve().parent.parent
MATCHES_TSV    = REPO_ROOT / "outputs" / "stage1" / "s1_matches.tsv"
OUT_DIR        = Path(__file__).resolve().parent
WORKSHEET_OUT  = OUT_DIR / "fpr_annotation_worksheet.csv"
JOIN_TABLE_OUT = OUT_DIR / "fpr_join_table.csv"
JING_OUT       = OUT_DIR / "jing_inprogress_new.tsv"

# Set to None to disable locked-row seeding
LOCKED_ANNOTATIONS = OUT_DIR / "jing_inprogress.tsv"

# ── constants ─────────────────────────────────────────────────────────────────

BUDGET_PER_LEVEL  = 75
RANDOM_STATE      = 42
LEVELS            = ["L2", "L3", "L4"]
EXCLUDED_TARGETS  = {"referential_white_supremacist", "unknown", "minority"}

WORKSHEET_COLS = ["row_id", "text_dedup_key", "dataset", "benchmark_label",
                  "matched_surface_form", "post_text",
                  "judgment", "annotator_notes"]

JOIN_COLS = ["row_id", "text_dedup_key", "dogwhistle",
             "matched_surface_form", "coding_level",
             "all_target_groups", "binary_hate", "dataset"]


# ── step 1: load and filter ───────────────────────────────────────────────────

def load_and_filter(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep="\t")
    df = df[~df["is_self_referential"]]
    df = df[~df["target"].isin(EXCLUDED_TARGETS)]
    print(f"After exclusions: {len(df):,} rows")
    return df


# ── step 2: deduplicate on (text_dedup_key, dogwhistle) ──────────────────────

def dedup(df: pd.DataFrame) -> pd.DataFrame:
    n_before = len(df)

    df = df.sort_values(["text_dedup_key", "dogwhistle", "target"]).reset_index(drop=True)

    passthrough = ["coding_level", "found_forms", "text", "dataset", "binary_hate"]
    agg = {col: (col, "first") for col in passthrough}
    agg["all_target_groups"] = ("target", lambda x: "|".join(x))

    deduped = (
        df.groupby(["text_dedup_key", "dogwhistle"], sort=False)
        .agg(**agg)
        .reset_index()
    )

    n_after     = len(deduped)
    n_collapsed = deduped["all_target_groups"].str.contains("|", regex=False).sum()

    print("\nDeduplication on (text_dedup_key, dogwhistle):")
    print(f"  Original rows : {n_before:,}")
    print(f"  After dedup   : {n_after:,}")
    print(f"  Rows collapsed (had multiple targets): {n_collapsed:,}")

    print("\n  Top 10 most common all_target_groups combinations:")
    combos = (
        deduped.loc[deduped["all_target_groups"].str.contains("|", regex=False),
                    "all_target_groups"]
        .value_counts()
        .head(10)
    )
    for combo, cnt in combos.items():
        print(f"    {cnt:>4}  {combo}")

    return deduped


# ── step 3: verify level pools ────────────────────────────────────────────────

def verify_pools(deduped: pd.DataFrame) -> None:
    print("\nAvailable rows per coding level after dedup:")
    for level in LEVELS:
        n = (deduped["coding_level"] == level).sum()
        shortfall = "" if n >= BUDGET_PER_LEVEL else f"  ← shortfall, will use all {n}"
        print(f"  {level}: {n:,} rows available{shortfall}")


# ── step 3b: load locked annotations from prior worksheet version ─────────────

def load_locked_rows(path: Path, deduped: pd.DataFrame) -> pd.DataFrame:
    """
    Read completed annotations from a previous-version worksheet TSV and
    match them to rows in the current deduped pool.

    Old worksheet uses 'dogwhistle_term'; new pool uses 'dogwhistle'.
    Only rows with a non-empty 'judgement' value are treated as locked.

    Returns a subset of deduped with two extra columns: 'judgment' and
    'annotator_notes' (carried over from the annotator's file).
    """
    raw       = pd.read_csv(path, sep="\t")
    completed = raw[raw["judgement"].notna() & (raw["judgement"].str.strip() != "")].copy()

    print(f"\nLocked annotations from {path.name}:")
    print(f"  Completed rows to lock: {len(completed)}")

    # Join deduped pool → completed annotations on (text_dedup_key, dogwhistle)
    locked = deduped.merge(
        completed[["text_dedup_key", "dogwhistle_term", "judgement", "annotator_notes"]],
        left_on=["text_dedup_key", "dogwhistle"],
        right_on=["text_dedup_key", "dogwhistle_term"],
        how="inner",
    ).drop(columns=["dogwhistle_term"])

    locked = locked.rename(columns={"judgement": "judgment"})
    locked["annotator_notes"] = locked["annotator_notes"].fillna("")

    # Deduplicate on (text_dedup_key, dogwhistle): the old worksheet used
    # found_forms as its dedup key, so the same post×dogwhistle could appear
    # twice if it matched two surface forms.  Keep the row with annotator_notes
    # if one exists, otherwise keep the first.
    locked = (
        locked
        .sort_values("annotator_notes", ascending=False)   # non-empty notes sort first
        .drop_duplicates(subset=["text_dedup_key", "dogwhistle"], keep="first")
        .reset_index(drop=True)
    )

    n_missing = len(completed) - len(locked)
    if n_missing:
        print(f"  Warning: {n_missing} annotated rows not found in new pool (skipped)")

    print("  Locked rows by level:")
    for lv in LEVELS:
        n = (locked["coding_level"] == lv).sum()
        print(f"    {lv}: {n}")

    return locked.reset_index(drop=True)


# ── step 4: sample ────────────────────────────────────────────────────────────

def sample_levels(deduped: pd.DataFrame,
                  locked: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    For each coding level, draw BUDGET_PER_LEVEL rows total.

    If locked rows exist for a level they are included first; the remaining
    budget is filled by uniform random draw from the residual pool (the pool
    with locked rows removed to prevent double-drawing).
    """
    parts: list[pd.DataFrame] = []

    for level in LEVELS:
        pool = deduped[deduped["coding_level"] == level].copy()

        level_locked = (
            locked[locked["coding_level"] == level].copy()
            if locked is not None and len(locked) > 0
            else pd.DataFrame(columns=list(pool.columns) + ["judgment", "annotator_notes"])
        )

        # Remove locked rows from pool so they are not drawn again
        if len(level_locked) > 0:
            locked_keys = set(zip(level_locked["text_dedup_key"], level_locked["dogwhistle"]))
            pool = pool[~pool.apply(
                lambda r: (r["text_dedup_key"], r["dogwhistle"]) in locked_keys,
                axis=1,
            )]

        n_draw = min(BUDGET_PER_LEVEL - len(level_locked), len(pool))
        drawn  = pool.sample(n=n_draw, random_state=RANDOM_STATE).copy()
        drawn["judgment"]        = ""
        drawn["annotator_notes"] = ""

        if len(level_locked) > 0:
            parts.append(level_locked)
        parts.append(drawn)

    combined = pd.concat(parts, ignore_index=True)

    # Shuffle so locked and new rows are interleaved
    combined = combined.sample(frac=1, random_state=RANDOM_STATE).reset_index(drop=True)
    combined.insert(0, "row_id", range(1, len(combined) + 1))
    return combined


# ── step 5: write outputs ─────────────────────────────────────────────────────

def write_outputs(sample: pd.DataFrame) -> None:
    sample = sample.copy()
    sample["matched_surface_form"] = sample["found_forms"]
    sample["post_text"]            = sample["text"]
    sample["benchmark_label"]      = sample["binary_hate"].map({1: "hateful", 0: "non-hateful"})

    # Blank worksheet — all judgment/annotator_notes empty, for any annotator
    ws_blank = sample.copy()
    ws_blank["judgment"]        = ""
    ws_blank["annotator_notes"] = ""
    ws_blank[WORKSHEET_COLS].to_csv(WORKSHEET_OUT, index=False)

    # Join table — pipeline metadata, no annotation content
    sample[JOIN_COLS].to_csv(JOIN_TABLE_OUT, index=False)

    # Jing's personal copy — locked rows have her existing judgment pre-filled
    sample[WORKSHEET_COLS].to_csv(JING_OUT, sep="\t", index=False)


# ── step 6: validation ────────────────────────────────────────────────────────

def validate() -> None:
    ws = pd.read_csv(WORKSHEET_OUT)
    jt = pd.read_csv(JOIN_TABLE_OUT)
    jing_new = pd.read_csv(JING_OUT, sep="\t")

    print(f"\n{'═'*60}")
    print("  VALIDATION")
    print(f"{'═'*60}")

    print(f"\nWorksheet shape       : {ws.shape}  (expected (225, 8))")

    print("\ncoding_level distribution (join table):")
    level_counts = jt["coding_level"].value_counts().reindex(LEVELS, fill_value=0)
    for lv, cnt in level_counts.items():
        flag = "" if cnt == BUDGET_PER_LEVEL else "  ← MISMATCH"
        print(f"  {lv}: {cnt}{flag}")

    assert ws["judgment"].fillna("").eq("").all(),        "worksheet judgment column is not blank"
    assert ws["annotator_notes"].fillna("").eq("").all(), "worksheet annotator_notes column is not blank"
    print("\nBlank worksheet judgment/annotator_notes: all empty ✓")

    assert ws["row_id"].is_unique, "row_id not unique in worksheet"
    print("row_id unique in worksheet              : ✓")

    dupes = jt.duplicated(subset=["text_dedup_key", "dogwhistle"]).sum()
    assert dupes == 0, f"{dupes} duplicate (text_dedup_key, dogwhistle) pairs in join table"
    print("(text_dedup_key, dogwhistle) unique in join table: ✓")

    jing_filled = jing_new["judgment"].notna() & (jing_new["judgment"].str.strip() != "")
    print(f"\nJing's copy ({JING_OUT.name}):")
    print(f"  Rows with judgment pre-filled: {jing_filled.sum()} / {len(jing_new)}")
    print(f"  Unique judgment values       : {jing_new.loc[jing_filled, 'judgment'].value_counts().to_dict()}")

    print("\n5 sample rows (row_id | surface_form | post_text[:80]):")
    for _, row in ws.sample(5, random_state=RANDOM_STATE).sort_values("row_id").iterrows():
        preview = str(row["post_text"])[:80].replace("\n", " ")
        print(f"  [{int(row['row_id']):>3}] {str(row['matched_surface_form']):<22}  \"{preview}\"")

    max_len    = int(ws["post_text"].str.len().max())
    max_idx    = ws["post_text"].str.len().idxmax()
    max_row_id = ws.at[max_idx, "row_id"]
    flag       = "  ← LONG (>500 chars)" if max_len > 500 else ""
    print(f"\nLongest post_text: row_id={max_row_id}  chars={max_len}{flag}")


# ── step 7: summary ───────────────────────────────────────────────────────────

def print_summary(sample: pd.DataFrame) -> None:
    jt = pd.read_csv(JOIN_TABLE_OUT)
    counts = jt["coding_level"].value_counts().reindex(LEVELS)

    print(f"\n{'═'*60}")
    print("  SUMMARY")
    print(f"{'═'*60}")
    print(f"\nWorksheet saved to   : {WORKSHEET_OUT}")
    print(f"Join table saved to  : {JOIN_TABLE_OUT}")
    print(f"Jing's copy saved to : {JING_OUT}")
    print(f"Total rows           : {len(sample)}")
    print(f"L2: {counts['L2']} | L3: {counts['L3']} | L4: {counts['L4']}")
    print(f"Unique posts in sample          : {jt['text_dedup_key'].nunique()}")
    print(f"Unique dogwhistle terms in sample: {jt['dogwhistle'].nunique()}")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    df      = load_and_filter(MATCHES_TSV)
    deduped = dedup(df)
    verify_pools(deduped)

    locked = None
    if LOCKED_ANNOTATIONS and LOCKED_ANNOTATIONS.exists():
        locked = load_locked_rows(LOCKED_ANNOTATIONS, deduped)

    sample = sample_levels(deduped, locked)
    write_outputs(sample)
    validate()
    print_summary(sample)


if __name__ == "__main__":
    main()
