"""Shared helpers for the dogwhistle audit pipeline.

The functions in this module are intentionally pure or near-pure so the stage
scripts can stay focused on I/O and table assembly.
"""

import ast
import itertools
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

# Mapping from Mendelsohn dogwhistle type strings to coding sophistication levels.
# L1 – explicit slurs/labels (no decoding required)
# L2 – stereotype-based terms (cultural knowledge required)
# L3 – concept/policy/values language (ideological context required)
# L4 – persona signals and arbitrary group labels (in-group membership required)
TYPE_TO_CODING_LEVEL: dict[str, str] = {
    "direct slur": "L1",
    "explicit label": "L1",
    "stereotype-based target group label": "L2",
    "stereotype-based descriptor": "L2",
    "phonetic-based target group label": "L2",
    "concept (policy)": "L3",
    "concept (values)": "L3",
    "concept (other)": "L3",
    "representative (bogeyman)": "L3",
    "persona signal (symbol)": "L4",
    "persona signal (shared culture)": "L4",
    "persona signal (self-referential)": "L4",
    "persona signal (in-group label)": "L4",
    "arbitrary target group label": "L4",
    "humor/mockery/sarcasm": "L4",
}


def map_type_to_coding_level(type_str: str) -> str:
    """Map a Mendelsohn dogwhistle type string to coding level (L1–L4).
    Unknown types return 'unknown'.
    """
    return TYPE_TO_CODING_LEVEL.get(str(type_str).strip().lower(), "unknown")


def norm_target(value: str) -> str:
    """Lowercase, collapse whitespace, replace _ and - with space.
    Maps 'nonbinary' -> 'non binary'. Used before map_reporting_group.
    """
    s = str(value).replace("_", " ").replace("-", " ").strip().lower()
    s = " ".join(s.split())
    if s == "nonbinary":
        return "non binary"
    return s


def parse_labels(value) -> frozenset:
    """Parse comma-separated label string into frozenset of stripped labels.
    NaN, empty string, and '_unknown' all return frozenset().
    """
    if value is None or pd.isna(value):
        return frozenset()
    s = str(value).strip()
    if s == "" or s == "_unknown":
        return frozenset()
    labels = [x.strip() for x in s.split(",") if x.strip() and x.strip() != "_unknown"]
    return frozenset(labels)


def parse_list_like(value) -> list[str]:
    """Parse list-like strings used in pipeline artifacts into a list of strings."""
    if value is None or pd.isna(value):
        return []
    s = str(value).strip()
    if s == "" or s == "[]":
        return []
    # Python-list literal form from notebook exports.
    if s.startswith("[") and s.endswith("]"):
        try:
            parsed = ast.literal_eval(s)
        except Exception:
            parsed = None
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
    # Semicolon-delimited fallback.
    if ";" in s:
        return [x.strip() for x in s.split(";") if x.strip()]
    return [s]


@dataclass(frozen=True)
class ReportGroup:
    report_level: str
    report_target: str
    include: bool


def map_reporting_group(level: str, target: str) -> ReportGroup:
    """Map (taxonomy_level, target) to (report_level, report_target)."""
    level_n = norm_target(level)
    target_n = norm_target(target)

    lgb_terms = {"lesbian", "gay", "bisexual"}
    trans_nb_terms = {
        "transgender men",
        "transgender women",
        "transgender unspecified",
        "non binary",
    }

    if level_n == "sexuality" and target_n in lgb_terms:
        return ReportGroup("lgbtq", "LGB", True)
    if level_n == "gender" and target_n in trans_nb_terms:
        return ReportGroup("lgbtq", "Trans/NB", True)
    if level_n == "gender" and target_n in {"men", "women", "other"}:
        return ReportGroup("gender", target_n, True)
    if level_n == "sexuality":
        return ReportGroup("sexuality", target_n, False)

    allowed_levels = {"race", "religion", "politics", "disability", "origin"}
    if level_n in allowed_levels:
        return ReportGroup(level_n, target_n, True)

    return ReportGroup(level_n, target_n, False)


def add_reporting_columns(
    df: pd.DataFrame, level_col: str, target_col: str
) -> pd.DataFrame:
    """Add report_level/report_target/report_include columns to dataframe."""
    mapped = df[[level_col, target_col]].apply(
        lambda r: map_reporting_group(r[level_col], r[target_col]), axis=1
    )
    out = df.copy()
    out["report_level"] = [m.report_level for m in mapped]
    out["report_target"] = [m.report_target for m in mapped]
    out["report_include"] = [m.include for m in mapped]
    return out


def normalize_surface_forms(raw: str) -> list[str]:
    """Split semicolon-delimited forms and drop numeric-suffix duplicates."""
    if raw is None or pd.isna(raw):
        return []
    forms = [x.strip().lower() for x in str(raw).split(";") if x.strip()]
    if not forms:
        return []

    form_set = set(forms)
    cleaned: list[str] = []
    for f in forms:
        base = re.sub(r"\s+\d+$", "", f)
        if base != f and base in form_set:
            continue
        cleaned.append(f)

    # Preserve order while deduping.
    out = []
    seen = set()
    for f in cleaned:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


def build_surface_form_pattern(forms: list[str]) -> re.Pattern:
    """Compile token-boundary case-insensitive regex over all forms.

    Uses whitespace/string-edge boundaries instead of \\b so that
    non-alphanumeric terms (e.g. '((()))') are matched correctly.  The right
    boundary also accepts common punctuation so matched forms survive sentence
    punctuation while still blocking run-on word matches.
    """
    uniq = sorted(set(forms), key=len, reverse=True)
    if not uniq:
        return re.compile(r"$^")
    alternation = "|".join(map(re.escape, uniq))
    return re.compile(
        r"(?:^|(?<=\s))(" + alternation + r")(?=$|\s|[.,!?;:()\[\]{}\"'])",
        flags=re.IGNORECASE,
    )


def safe_float(value) -> float:
    """Return float(value), or nan on failure or missing."""
    if value is None or pd.isna(value):
        return float("nan")
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def safe_di_ratio(a: float, b: float) -> float:
    """Disparate impact ratio min(a,b)/max(a,b). Does not enforce n_min.

    Prefer safe_di() for all disparity calculations that have sample counts.
    """
    if np.isnan(a) or np.isnan(b):
        return float("nan")
    high = max(a, b)
    if high == 0:
        return float("nan")
    return min(a, b) / high


def safe_di(
    val_a: float,
    val_b: float,
    n_a: int,
    n_b: int,
    n_min: int = 30,
) -> float:
    """Disparate impact ratio with sparse-data guard.

    Returns NaN when either group's sample size is below n_min or when
    max(val_a, val_b) == 0, preventing misleading results from sparse data.
    """
    if n_a < n_min or n_b < n_min:
        return float("nan")
    if np.isnan(val_a) or np.isnan(val_b):
        return float("nan")
    high = max(val_a, val_b)
    if high == 0:
        return float("nan")
    return min(val_a, val_b) / high


def build_pairwise_rows(
    group_df: pd.DataFrame,
    presence_col: str,
    type_cov_col: str,
    labeling_col: str,
    failure_col: str,
    matches_col: str,
    level_col: str,
    target_col: str,
    n_min: int,
) -> list[dict]:
    """Build pairwise disparity rows within each level group.

    The caller specifies which columns hold the coverage, annotation, and count
    statistics.  This keeps the pairwise disparity logic reused across Stage 3
    and Stage 4 while preserving each stage's grouping semantics.
    """
    rows: list[dict] = []

    for level_value, level_df in group_df.groupby(level_col):
        recs = level_df.to_dict("records")
        for a, b in itertools.combinations(recs, 2):
            # Read all comparable rates through safe_float so missing values are
            # consistently propagated as NaN rather than raising during math.
            pr_a = safe_float(a.get(presence_col))
            pr_b = safe_float(b.get(presence_col))
            tc_a = safe_float(a.get(type_cov_col))
            tc_b = safe_float(b.get(type_cov_col))
            cl_a = safe_float(a.get(labeling_col))
            cl_b = safe_float(b.get(labeling_col))
            fr_a = safe_float(a.get(failure_col))
            fr_b = safe_float(b.get(failure_col))
            n_a = (
                int(safe_float(a.get(matches_col)))
                if pd.notna(a.get(matches_col))
                else 0
            )
            n_b = (
                int(safe_float(b.get(matches_col)))
                if pd.notna(b.get(matches_col))
                else 0
            )

            # DI values are suppressed for sparse comparisons so downstream
            # plots and tables do not over-interpret unstable group pairs.
            pr_di = safe_di(pr_a, pr_b, n_a, n_b, n_min)
            tc_di = safe_di(tc_a, tc_b, n_a, n_b, n_min)
            worst_di = (
                min(pr_di, tc_di)
                if not np.isnan(pr_di) and not np.isnan(tc_di)
                else float("nan")
            )
            ann_di = safe_di(cl_a, cl_b, n_a, n_b, n_min)
            unstable = (n_a < n_min) or (n_b < n_min)

            rows.append(
                {
                    level_col: level_value,
                    "target_a": a.get(target_col),
                    "target_b": b.get(target_col),
                    "presence_rate_a": pr_a,
                    "presence_rate_b": pr_b,
                    "presence_rate_di_ratio": pr_di,
                    "type_coverage_a": tc_a,
                    "type_coverage_b": tc_b,
                    "type_coverage_di_ratio": tc_di,
                    "worst_di_ratio": worst_di,
                    "correct_labeling_rate_a": cl_a,
                    "correct_labeling_rate_b": cl_b,
                    "annotation_di_ratio": ann_di,
                    "labeling_rate_gap": cl_a - cl_b,
                    "labeling_rate_gap_abs": abs(cl_a - cl_b),
                    "failure_rate_a": fr_a,
                    "failure_rate_b": fr_b,
                    "failure_rate_gap": fr_a - fr_b,
                    "failure_rate_gap_abs": abs(fr_a - fr_b),
                    "total_matches_a": n_a,
                    "total_matches_b": n_b,
                    "unstable_small_n": unstable,
                }
            )

    return rows


def write_tsv(df: pd.DataFrame, path: Path) -> None:
    """Write dataframe as TSV creating parent dirs when needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, sep="\t", index=False)


def ensure_dirs(*paths: Path) -> None:
    """Create directories if they do not exist."""
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)


def calculate_metrics(
    df: pd.DataFrame,
    group_col: str,
    ground_truth_col: str = "ground_truth",
    model_output_col: str = "model_output",
    n_min: int = 30,
) -> pd.DataFrame:
    """Compute per-group fairness metrics from a scored DataFrame.

    Parameters
    ----------
    df : DataFrame with one row per example.  Must contain ``ground_truth_col``
        (the actual binary label Y) and ``model_output_col`` (the predicted
        binary label Ŷ).
    group_col : column that identifies the protected group A.
    ground_truth_col : column holding the actual label (Y).  Used for q_a.
    model_output_col : column holding the model prediction (Ŷ).
    n_min : minimum sample size for a stable estimate.

    Returns
    -------
    DataFrame with one row per group containing:
    - ``q_a``      : P(Y=1 | A=a) — base rate from *ground truth*, not predictions.
    - ``pred_rate``: P(Ŷ=1 | A=a) — model positive rate.
    - ``n``        : group sample size.
    - ``stable_n`` : whether n >= n_min.
    """
    rows = []
    for group, grp in df.groupby(group_col):
        n = len(grp)
        # q_a must use the ground_truth column — NOT model_output — so that
        # it represents the actual prevalence of the trait in the population.
        q_a = float(grp[ground_truth_col].mean())
        pred_rate = float(grp[model_output_col].mean())
        rows.append(
            {
                group_col: group,
                "n": n,
                "q_a": q_a,
                "pred_rate": pred_rate,
                "stable_n": n >= n_min,
            }
        )
    return pd.DataFrame(rows)
