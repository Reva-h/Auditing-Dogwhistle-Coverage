"""
filter_glossary.py
==================
Parses data/glossary.md and annotates every entry with a provenance tier
based on the domain of its Description source URL.

Tier rationale
--------------
Tier 1 – High provenance
    Peer-reviewed journals (Springer, T&F, Brill), major mainstream news
    outlets (NYT, WaPo, Guardian, Vox, FiveThirtyEight, Slate), established
    civil-rights watchdogs (ADL, AJC, NCCM, antisemitism.org.uk), and
    academic/institutional sources (CUNY Law, TAMU, USIH, Ian Haney López's
    own site, Contemporary Rhetoric journal).  Google Books links to López
    (2014) "Dog Whistle Politics" (OUP) are handled via TIER_1_OVERRIDES
    because the URL resolves to books.google.com rather than the publisher.

Tier 2 – Moderate provenance
    Advocacy organisations, progressive media, and subject-matter blogs that
    are broadly credible but lack the editorial standards or scholarly
    peer-review of Tier 1.

Tier 3 – Low provenance / community wikis
    Crowd-edited wikis (RationalWiki, Wikipedia).  Useful for coverage but
    treated with higher scepticism in downstream analyses.

Unknown
    Any domain not mapped above.  These are printed as warnings so a human
    can assign a tier manually.

Outputs
-------
outputs/glossary/glossary.tsv          – original columns + 'source_domain' + 'tier'
outputs/glossary/glossary_tier_summary.txt – counts and breakdowns
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urlparse, unquote

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
WORKDIR = Path(__file__).resolve().parent.parent
GLOSSARY_MD_PATH = WORKDIR / "data" / "glossary.md"
OUTPUT_DIR = WORKDIR / "outputs" / "glossary"
OUTPUT_TSV = OUTPUT_DIR / "glossary.tsv"
OUTPUT_SUMMARY = OUTPUT_DIR / "glossary_tier_summary.txt"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Tier domain sets
# ---------------------------------------------------------------------------
TIER_1_DOMAINS = {
    "link.springer.com", "www.tandfonline.com", "www.taylorfrancis.com", "brill.com",
    "www.nytimes.com", "www.washingtonpost.com", "www.theguardian.com", "www.vox.com",
    "fivethirtyeight.com", "slate.com", "prospect.org", "foreignpolicy.com",
    "www.adl.org", "www.ajc.org", "www.nccm.ca", "antisemitism.org.uk",
    "ianhaneylopez.com", "contemporaryrhetoric.com", "today.tamu.edu",
    "www.law.cuny.edu", "s-usih.org",
}

TIER_2_DOMAINS = {
    "colorofchange.org", "queervegan.com", "everydayfeminism.com",
    "thedemlabs.org", "blmgrassroots.org", "medium.com", "helenldecruz.medium.com",
    "www.theroot.com", "theconversation.com", "politicalresearch.org",
    "forward.com", "www.dailykos.com", "talkingpointsmemo.com",
    "www.salon.com", "nymag.com", "www.sapiens.org", "www.patheos.com",
    "www.usnews.com", "www.newsweek.com", "www.thedailybeast.com",
    "www.csmonitor.com", "www.latimes.com", "www.haaretz.com",
    "www.jta.org", "storyful.com", "hyperallergic.com", "money.cnn.com",
    "www.ourspectrum.com", "www.cpreview.org", "electionsos.com",
}

TIER_3_DOMAINS = {
    "rationalwiki.org", "en.wikipedia.org",
}

# google.com/books redirects to López (2014) "Dog Whistle Politics" (OUP).
# Verified manually; treated as Tier 1.
TIER_1_OVERRIDES: set[str] = {
    "affirmative action",
    "gangbanger",
    "freedom of association",
    "food stamp president",
}

# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _extract_link_url(text: str) -> str:
    """
    Return the first URL found inside a Markdown link, or ''.

    Handles two edge cases found in this glossary:
    - URLs missing the http(s):// prefix (e.g. jacksonfreepress.com/...)
    - URLs whose closing ')' is on the following line (multiline markdown link)
    Both cases are normalised to a full https:// URL before returning.
    """
    # Standard case: https?:// URL, possibly spanning to next line before ')'
    m = re.search(r"\]\((https?://[^)]+)\)", text, re.S)
    if m:
        return unquote(m.group(1).strip())
    # Fallback: URL-like string without scheme prefix (e.g. "domain.com/path")
    m = re.search(r"\]\(([a-zA-Z0-9][-a-zA-Z0-9.]*\.[a-zA-Z]{2,}[^)]*)\)", text, re.S)
    if m:
        raw_url = m.group(1).strip()
        return unquote("https://" + raw_url)
    return ""


def _parse_label(block: str, label: str) -> str:
    """
    Extract the value of an italicised label like _Label_: value
    from a multi-line block.  Stops at the next label or end-of-string.
    """
    pattern = rf"_{re.escape(label)}_:\s*(.*?)(?=\s*_[^_]+_:|$)"
    m = re.search(pattern, block, re.S)
    if not m:
        return ""
    return re.sub(r"\s+", " ", m.group(1)).strip()


def parse_glossary_md(path: Path) -> pd.DataFrame:
    """
    Parse glossary.md into a DataFrame with one row per term.

    Handles the backslash soft-wrap artifacts from the original HTML source
    by normalising \\<newline><whitespace> sequences before splitting.
    """
    raw = path.read_text(encoding="utf-8", errors="ignore")
    # Collapse backslash line-continuations (e.g. "\_Persona_:\\ \n                 racist")
    raw = re.sub(r"\\\n\s*", "\n", raw)

    # Split into per-term blocks at each **bold-term** heading
    entries = re.split(r"\n(?=\*\*)", raw)

    rows: list[dict] = []
    for entry in entries:
        term_m = re.match(r"\*\*([^*]+)\*\*", entry.strip())
        if not term_m:
            continue
        term = term_m.group(1).strip()

        # --- Surface forms ---
        sf_m = re.search(r"_Surface forms_:\s*([^\n]+)", entry)
        surface_forms_raw = sf_m.group(1).strip() if sf_m else ""
        surface_forms_list = [s.strip() for s in surface_forms_raw.split(";") if s.strip()]

        # --- Persona/In-Group block (ends at Description or Example or EOF) ---
        persona_block_m = re.search(
            r"_Persona/In-Group_:.*?(?=\nDescription|\nExample|\Z)", entry, re.S
        )
        persona_block = persona_block_m.group(0) if persona_block_m else ""

        persona_raw = _parse_label(persona_block, "Persona/In-Group")
        # Split multi-group values on "/" and strip whitespace
        persona_list = [p.strip() for p in persona_raw.split("/") if p.strip()]
        persona = " / ".join(persona_list)  # canonical form

        covert_meaning = _parse_label(persona_block, "Covert (in-group) meaning")
        dogwhistle_type = _parse_label(persona_block, "Type")
        register = _parse_label(persona_block, "Register")

        # --- Description source URL ---
        # Use re.S so the match spans newlines: some entries place the closing
        # ')) on a separate line (or even after a blank line) from the URL.
        desc_header_m = re.search(
            r"Description \(from\s+\[_Source_\]\((.*?)\)\)", entry, re.S
        )
        description_source = ""
        if desc_header_m:
            raw_url = desc_header_m.group(1).strip()
            if raw_url:
                # Normalise: add https:// if the scheme is absent
                if not raw_url.startswith(("http://", "https://")):
                    raw_url = "https://" + raw_url
                description_source = unquote(raw_url)
            else:
                print(
                    f"WARNING: missing/malformed description URL for term '{term}'",
                    file=sys.stderr,
                )
        else:
            print(
                f"WARNING: no Description header found for term '{term}'",
                file=sys.stderr,
            )

        # --- Description body ---
        desc_body_m = re.search(
            r"Description \(from [^\n]+\n(.*?)(?=\nExample context|\Z)", entry, re.S
        )
        description = (
            re.sub(r"\s+", " ", desc_body_m.group(1)).strip() if desc_body_m else ""
        )

        # --- Examples ---
        examples, ex_sources, ex_speakers, ex_dates = [], [], [], []
        for ex_m in re.finditer(
            r"Example context \(in ([^\n]+)\n(.*?)(?=\nExample context|\Z)", entry, re.S
        ):
            source_url = _extract_link_url(ex_m.group(1))
            body = ex_m.group(2)
            speaker = _parse_label(body, "Speaker")
            date = _parse_label(body, "Date")
            ex_text = re.sub(r"_Speaker_:.*", "", body, flags=re.S).strip()
            ex_text = re.sub(r"\s+", " ", ex_text).strip()
            if ex_text:
                examples.append(ex_text)
                ex_sources.append(source_url)
                ex_speakers.append(speaker)
                ex_dates.append(date)

        rows.append(
            {
                "term": term,
                "surface_forms": surface_forms_raw,
                "surface_forms_list": surface_forms_list,
                "persona_in_group": persona,
                "covert_meaning": covert_meaning,
                "type": dogwhistle_type,
                "register": register,
                "description": description,
                "description_source": description_source,
                "example_count": len(examples),
                "examples": " || ".join(examples),
                "example_sources": " ; ".join(s for s in ex_sources if s),
                "example_speakers": " ; ".join(s for s in ex_speakers if s),
                "example_dates": " ; ".join(s for s in ex_dates if s),
            }
        )

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tier classification
# ---------------------------------------------------------------------------

def extract_domain(url: str) -> str:
    """Return the netloc of a URL, lower-cased, with trailing spaces stripped."""
    if not url:
        return ""
    try:
        return urlparse(url.strip()).netloc.lower()
    except Exception:
        return ""


def classify_tier(term: str, domain: str) -> str:
    """
    Return '1', '2', '3', or 'unknown'.

    google.com links are assumed to point to López (2014) (OUP) for the
    terms listed in TIER_1_OVERRIDES; all other google.com links fall through
    to 'unknown'.
    """
    if not domain:
        return "unknown"

    if domain in TIER_1_DOMAINS:
        return "1"
    if domain in TIER_2_DOMAINS:
        return "2"
    if domain in TIER_3_DOMAINS:
        return "3"

    # Manual override: google.com/books → López 2014 (OUP)
    if domain == "www.google.com" and term in TIER_1_OVERRIDES:
        return "1"

    return "unknown"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    df = parse_glossary_md(GLOSSARY_MD_PATH)

    # Derive domain and tier
    df["source_domain"] = df["description_source"].map(extract_domain)
    df["tier"] = df.apply(
        lambda row: classify_tier(row["term"], row["source_domain"]), axis=1
    )

    # Warn on unknown domains (excluding empty/missing)
    unknown_mask = (df["tier"] == "unknown") & (df["source_domain"] != "")
    unknown_domains = df.loc[unknown_mask, "source_domain"].unique()
    for dom in sorted(unknown_domains):
        terms = df.loc[df["source_domain"] == dom, "term"].tolist()
        print(
            f"WARNING: unknown domain '{dom}' — {len(terms)} term(s): "
            + ", ".join(f"'{t}'" for t in terms),
            file=sys.stderr,
        )

    # Drop the list column (not suitable for TSV)
    df_out = df.drop(columns=["surface_forms_list"])
    df_out.to_csv(OUTPUT_TSV, sep="\t", index=False)
    print(f"Wrote {len(df_out):,} rows → {OUTPUT_TSV}")

    # -----------------------------------------------------------------------
    # Summary report
    # -----------------------------------------------------------------------
    lines: list[str] = []

    lines.append("=" * 60)
    lines.append("GLOSSARY PROVENANCE TIER SUMMARY")
    lines.append("=" * 60)
    lines.append("")

    # --- Total counts per tier ---
    tier_counts = df["tier"].value_counts().reindex(["1", "2", "3", "unknown"], fill_value=0)
    lines.append("Total entries per tier")
    lines.append("-" * 30)
    for tier, count in tier_counts.items():
        lines.append(f"  Tier {tier}: {count:>4d} entries")
    lines.append(f"  TOTAL  : {len(df):>4d} entries")
    lines.append("")

    # --- Breakdown of Tier 3 domains ---
    tier3_df = df[df["tier"] == "3"]
    lines.append("Tier 3 — domain breakdown")
    lines.append("-" * 30)
    if tier3_df.empty:
        lines.append("  (none)")
    else:
        for dom, cnt in tier3_df["source_domain"].value_counts().items():
            lines.append(f"  {dom}: {cnt}")
    lines.append("")

    # --- Breakdown of unknown domains ---
    unknown_df = df[df["tier"] == "unknown"]
    lines.append("Unknown — domain breakdown")
    lines.append("-" * 30)
    if unknown_df.empty:
        lines.append("  (none)")
    else:
        for dom, cnt in unknown_df["source_domain"].value_counts().items():
            label = dom if dom else "(no URL)"
            lines.append(f"  {label}: {cnt}")
    lines.append("")

    # --- Per persona × tier entry counts ---
    lines.append("Per persona/in-group × tier entry counts")
    lines.append("-" * 50)

    # Explode multi-group personas so each group gets counted independently
    exploded = df.copy()
    exploded["persona_split"] = exploded["persona_in_group"].str.split(" / ")
    exploded = exploded.explode("persona_split")
    exploded["persona_split"] = exploded["persona_split"].str.strip().replace("", "unknown")

    pivot = (
        exploded.groupby(["persona_split", "tier"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=["1", "2", "3", "unknown"], fill_value=0)
    )
    pivot["total"] = pivot.sum(axis=1)
    pivot = pivot.sort_values("total", ascending=False)

    header = f"  {'Persona/In-Group':<35s}  {'T1':>4}  {'T2':>4}  {'T3':>4}  {'?':>4}  {'tot':>4}"
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))
    for persona, row in pivot.iterrows():
        lines.append(
            f"  {str(persona):<35s}  "
            f"{row.get('1', 0):>4d}  "
            f"{row.get('2', 0):>4d}  "
            f"{row.get('3', 0):>4d}  "
            f"{row.get('unknown', 0):>4d}  "
            f"{row['total']:>4d}"
        )
    lines.append("")

    report = "\n".join(lines)
    OUTPUT_SUMMARY.write_text(report, encoding="utf-8")
    print(f"Wrote summary → {OUTPUT_SUMMARY}")
    print()
    print(report)


if __name__ == "__main__":
    main()
