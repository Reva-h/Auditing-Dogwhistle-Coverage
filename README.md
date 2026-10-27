# Who Let the Dogs Out? Auditing Dogwhistle Coverage in Hate Speech Benchmarks Across Target Groups

Code and data for the WOAH 2026 paper of the same name.

The paper audits whether hate speech benchmarks contain dogwhistles (coded
hateful language) and label them correctly, and whether that varies by target
group. It matches the 340 dogwhistles of the [Mendelsohn et al.
(2023)](https://www.semanticscholar.org/paper/a5731b32060909bfc8848fa5f7e1e14ca3b53240)
glossary against the union of
[HateXplain](https://github.com/hate-alert/HateXplain) and [Measuring Hate
Speech](https://huggingface.co/datasets/ucberkeley-dlab/measuring-hate-speech)
(MHS), and compares that union with [Implicit
Hate](https://github.com/SALT-NLP/implicit-hate) alone. The audit asks three
questions:

1. **Coverage:** are dogwhistles aimed at each group present in the benchmarks?
2. **Annotation quality:** when they are, are the posts labeled hateful?
3. **Fairness:** do coverage and labeling differ between groups, under the
   four-fifths rule?

## Released data

[`release/`](release/README.md) holds the post-level data behind every
result, **identified by post ID only, with no post text**. It contains the
benchmark union with our target-group labels, every dogwhistle match, our
glossary-to-taxonomy mapping, the false-positive-rate (FPR) annotations, and
every audit result table. To read the posts, get each source dataset from its
authors and join on `dataset` and `post_id`; [`release/README.md`](release/README.md)
explains how.

You can use the release without running any code.

## Repository layout

| Path | Contents |
|---|---|
| [`release/`](release/README.md) | ID-only data release (start here for the data) |
| [`data_preprocessing/`](data_preprocessing/README.md) | Notebooks 00–06: parse the glossary, standardize each dataset, union and deduplicate, apply the human annotations |
| [`annotations/`](annotations/README.md) | Both annotators' target-label and glossary annotations, the merge notebook, and the inter-annotator agreement notebook |
| [`audit_pipeline/`](audit_pipeline/README.md) | Stages 1–4 of the audit (coverage, annotation quality, disparity, rollup), the robustness check, the paper figures, and the release builder |
| [`fpr_annotation/`](fpr_annotation/README.md) | The FPR annotation task: sampler, annotator instructions, and the analysis notebook |
| [`scripts/`](scripts/README.md) | Shell entry points, including one that reproduces the whole paper |
| [`tests/`](tests/) | Unit and integration tests (`pytest`) |
| `data/` | Source datasets go here (not distributed, except the glossary) |
| `outputs/` | Pipeline outputs (regenerated locally, not distributed; `group_labels.tsv` is a hand-made input) |

## Setup

Tested with Python 3.12.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Getting the source data

The datasets are not redistributed here. Place them under `data/`:

| Dataset | Where to get it | Put it at |
|---|---|---|
| HateXplain | `Data/dataset.json` in [hate-alert/HateXplain](https://github.com/hate-alert/HateXplain) | `data/hatexplain.json` |
| Measuring Hate Speech | Downloaded automatically from [Hugging Face](https://huggingface.co/datasets/ucberkeley-dlab/measuring-hate-speech) on the first run | `data/measuring_hate_speech.parquet` (cached) |
| Implicit Hate | [SALT-NLP/implicit-hate](https://github.com/SALT-NLP/implicit-hate) (the authors ask you to fill in a short form) | `data/implicit-hate-corpus/implicit_hate_v1_stg1_posts.tsv` and `implicit_hate_v1_stg3_posts.tsv` |
| Dogwhistle glossary | Already included | `data/glossary.md` |

Implicit Hate (ElSherief et al., 2021) is called `elsherief` in the code,
file names and the release.

## Reproducing the paper

With the data in place, from the repository root:

```bash
scripts/reproduce_paper.sh
```

It runs these steps in order; each can also be run on its own:

| Step | Command | Produces |
|---|---|---|
| 1. Preprocessing | `scripts/run_data_preprocessing.sh` | The annotated corpus in `outputs/unioned_data/` |
| 2. Annotation agreement | Run `annotations/merge_annotation_union.ipynb`, then `annotations/inter_annotator_agreement.ipynb` | Table 4 |
| 3. Audit | `scripts/run_audit_pipeline.sh` | `outputs/stage1/`–`stage4/`, the tier-1+2 robustness check (`*_tier12/`), and `outputs/robustness_check/` |
| 4. Implicit Hate comparison | `python -m audit_pipeline.build_elsherief_comparison_data`, then `python -m audit_pipeline.stage4_rollup` | `outputs/stage4/elsherief/` (Section 5.4, Appendix G) |
| 5. Robustness table | `python -m audit_pipeline.generate_robustness_table_for_paper` | Table 3 |
| 6. Figures | Run `audit_pipeline/figures_consolidated.ipynb` | Figures 1–13, in `outputs/figures_final/` |
| 7. FPR | Run `fpr_annotation/fpr_iaa_analysis.ipynb` | Table 2 and Figures 14–16, in `fpr_annotation/outputs/` |
| 8. Release | `python -m audit_pipeline.build_release` | `release/` |

Step 7 reads only `release/fpr/`, so it runs on a fresh clone with no source
data. Step 4 is separate from step 3 because the primary corpus excludes
Implicit Hate (the paper's primary audit covers HateXplain and MHS only);
it builds a second corpus that includes it, leaving the primary outputs
untouched.

Run a notebook non-interactively with
`jupyter nbconvert --to notebook --execute --inplace <notebook>`.

### Where each figure and table comes from

| Paper | Output file | Generated from |
|---|---|---|
| Figure 1 (§5.2) | `outputs/figures_final/fig01_annotation_rates_by_level.pdf` | Stage 2 |
| Figure 2 (§5.3) | `outputs/figures_final/fig02_annotation_di_by_pair_level.pdf` | Stage 4 |
| Figure 3 (§5.3) | `outputs/figures_final/fig03_di_histograms_by_level.pdf` | Stage 4 |
| Figure 4a, 4b (§5.4) | `outputs/figures_final/fig04a_elsherief_annotation_delta.pdf`, `fig04b_elsherief_coverage_delta.pdf` | Stage 4, Implicit Hate comparison |
| Table 2 (Limitations) | `fpr_annotation/outputs/fpr_reportable_metrics.txt` | FPR notebook |
| Table 3 (App. A) | `outputs/robustness_check/robustness_table_for_paper.tex` | Robustness check |
| Figures 5–7 (App. B) | `outputs/figures_final/fig05_coverage_heatmap.pdf`, `fig06_coverage_presence_vs_type_by_level.pdf`, `fig07_token_frequency_by_level.pdf` | Stages 1 and 4 |
| Figures 8–9 (App. C) | `outputs/figures_final/fig08_annotation_rates_pooled.pdf`, `fig09_case_ab_counts_by_level.pdf` | Stages 2 and 4 |
| Table 4 (App. D) | Printed by `annotations/inter_annotator_agreement.ipynb` | Raw annotator files |
| Figures 10–11 (App. E) | `outputs/figures_final/fig10_worst_di_by_pair_level.pdf`, `fig11_annotation_label_gap_by_level.pdf` | Stage 4 |
| Figure 12 (App. F) | `outputs/figures_final/fig12_cross_level_deltas.pdf` | Stage 3 |
| Figure 13 (App. G) | `outputs/figures_final/fig13_elsherief_pairwise_di_delta.pdf` | Stage 4, Implicit Hate comparison |
| Figures 14–16 (App. H) | `fpr_annotation/outputs/fig14_fpr_by_level.pdf`, `fig15_fpr_agreement_matrix.pdf`, `fig16_fpr_annotator_vs_benchmark.pdf` | FPR notebook |

The figures regenerated here contain exactly the data shown in the paper.
Some of the paper's figures were exported before a final styling pass, so
fonts and colors can differ slightly. Files named `fig_unused_*` are
generated but not in the paper.

## Notes on reproducing the paper

- **Disagreement resolution.** The paper describes annotator disagreements
  as resolved by four rules plus adjudication by the lead annotator. The
  audit does not apply those resolutions:
  `data_preprocessing/06_apply_annotations.ipynb` takes the plain union of
  both annotators' labels, and the paper's results were computed from that
  union. The resolved labels are produced separately by
  `annotations/merge_annotation_union.ipynb`. See
  [`annotations/README.md`](annotations/README.md#note-on-disagreement-resolution-vs-the-paper)
  for the items that differ.
- **FPR sample.** The FPR sample was drawn while the corpus still included
  Implicit Hate, so 47 of its 225 posts come from Implicit Hate, although
  the primary audit excludes it.

## Tests

```bash
pytest
```

The tests use small synthetic data, so they run on a fresh clone. The
release's post-text check also scans the real release against the
standardized corpora when those exist locally.
