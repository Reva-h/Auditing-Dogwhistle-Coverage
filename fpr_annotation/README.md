# FPR Annotation

Estimates how often a dogwhistle match is a false positive, meaning the
matched post uses the term without its hateful coded meaning (Limitations
section, Table 2, and Appendix H). Two annotators judged 225 matched posts,
75 per coding level (L2, L3, L4).

## Files

| File | Contents |
|---|---|
| `fpr_iaa_analysis.ipynb` | Computes FPR per level, annotator agreement, and annotator-vs-benchmark agreement. Writes Figures 14–16 and the Table 2 numbers to `outputs/` |
| `sample_fpr.py` | The script that drew the sample (see below) |
| `worksheet_materials/fpr_annotator_instructions.md`, `.pdf` | The instructions the annotators were given |

The judgments themselves are released, keyed by post ID, in
[`release/fpr/fpr_judgments.tsv`](../release/README.md#fprfpr_judgmentstsv).
The annotation worksheets, the sampler's join table and the completed
worksheets are not distributed, because they contain post text.

## Running the analysis

```bash
jupyter nbconvert --to notebook --execute --inplace fpr_annotation/fpr_iaa_analysis.ipynb
```

The notebook reads only `release/fpr/fpr_judgments.tsv`, so it runs on a
fresh clone without the source datasets. It writes:

| File | Paper |
|---|---|
| `outputs/fpr_reportable_metrics.txt` | Table 2 and the FPR numbers in the text |
| `outputs/fig14_fpr_by_level.pdf` | Figure 14 |
| `outputs/fig15_fpr_agreement_matrix.pdf` | Figure 15 |
| `outputs/fig16_fpr_annotator_vs_benchmark.pdf` | Figure 16 |
| `outputs/fig_unused_fpr_unclear_rate.pdf` | Not in the paper |

## The task

For each post, annotators judged whether the matched term was used with its
dogwhistle meaning: **Hateful**, **Not Hateful**, or **Unknown** (called
"Unclear" in the paper) when the post alone did not settle it. They were told
to ignore the benchmark's own label.

The two judgments are combined per post as follows:

- both definitive and equal: that label;
- one Unknown and one definitive: the definitive label;
- both Unknown, or Hateful against Not Hateful: excluded.

FPR is the share of retained posts resolved as Not Hateful, with Wilson 95%
confidence intervals.

## How the sample was drawn

`sample_fpr.py` read the Stage 1 matches, dropped self-referential
dogwhistles and the target groups `referential_white_supremacist`,
`unknown` and `minority`, kept one row per (post, dogwhistle), and drew 75
rows per coding level with `random_state=42`. Rows one annotator had already
judged in an earlier version of the worksheet were kept in the sample, and
the rest of each level's budget was drawn at random.

Running the script on the current outputs does not reproduce the sample, for
two reasons. The sample was drawn while the corpus still included Implicit
Hate, so 47 of the 225 posts come from Implicit Hate, which the primary
audit excludes. And the earlier worksheet it kept rows from is not
distributed. The script is included as a record of the procedure.
