"""Regression tests for the 740f187 _top_n sort-direction fix.

_top_n(df, by, n) used to hard-code `ascending=False`, which is correct for
metrics where higher = worse/more-notable (token frequency, label gaps,
abs_presence, case_b counts -- the 8 call sites that were never buggy) but
wrong for worst_di_ratio, where *lower* = more disparate/worse. The fix adds
an explicit `ascending` parameter (default False, unchanged for the 8
existing call sites) so the two worst_di_ratio call sites can pass
ascending=True.
"""

import pandas as pd

from audit_pipeline.stage5_figures import _top_n


def _sample_df():
    return pd.DataFrame(
        {
            "label": ["a", "b", "c", "d", "e"],
            "worst_di_ratio": [0.9, 0.3, 0.7, 0.1, 0.5],
        }
    )


def test_default_ascending_false_selects_highest_values():
    # Correct behaviour for metrics where higher = more extreme (e.g. token
    # frequency, label gaps) -- must remain unchanged by the fix.
    out = _top_n(_sample_df(), "worst_di_ratio", 2)
    assert set(out["label"]) == {"a", "c"}  # 0.9, 0.7


def test_explicit_ascending_true_selects_lowest_values():
    # The fix: worst_di_ratio call sites now pass ascending=True so "top n"
    # means "n most disparate", not "n with the highest raw ratio".
    out = _top_n(_sample_df(), "worst_di_ratio", 2, ascending=True)
    assert set(out["label"]) == {"d", "b"}  # 0.1, 0.3


def test_empty_dataframe_returned_unchanged():
    empty = pd.DataFrame(columns=["label", "worst_di_ratio"])
    out = _top_n(empty, "worst_di_ratio", 2, ascending=True)
    assert out.empty


def test_missing_column_returns_input_unchanged():
    df = _sample_df()
    out = _top_n(df, "not_a_real_column", 2, ascending=True)
    assert out is df
