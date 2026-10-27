# Audit Pipeline

Computes every audit metric in the paper from the annotated corpus written by
[`data_preprocessing/06_apply_annotations.ipynb`](../data_preprocessing/README.md),
then draws the figures and builds the data release.

## Inputs

| File | Written by |
|---|---|
| `outputs/unioned_data/06_cleaned_labels_glossary_mapped.tsv` | `data_preprocessing/06_apply_annotations.ipynb` |
| `outputs/unioned_data/06_glossary_label_reference.tsv` | `data_preprocessing/06_apply_annotations.ipynb` |
| `outputs/unioned_data/06_cleaned_labels_glossary_mapped_with_elsherief.tsv`, `outputs/stage1_with_elsherief/` | `build_elsherief_comparison_data.py` (needed only for the Implicit Hate comparison) |

## Modules

| Module | What it does |
|---|---|
| `config.py` | Paths, thresholds, and the two pipeline variants |
| `helpers.py` | Parsing, group mapping, and disparity helpers shared by the stages |
| `stage1_coverage.py` | Stage 1 (RQ1): matches glossary surface forms against posts; presence rate and type coverage per group |
| `stage2_annotation.py` | Stage 2 (RQ2): whether matched posts are labeled hateful (Case A) or not (Case B), per group |
| `stage3_disparity.py` | Stage 3 (RQ3): pairwise disparate-impact (DI) ratios within each taxonomy level, and cross-level consistency |
| `stage4_rollup.py` | Stage 4: rolls Stages 1–3 up to reporting groups and coding levels, and compares the union with Implicit Hate |
| `run_all.py` | Runs Stages 1–4 for both variants, then the robustness check |
| `robustness_check.py` | Compares the two variants' Stage 4 outputs pair by pair, per level and pooled |
| `generate_robustness_table_for_paper.py` | Renders the pairs the paper discusses as Table 3 |
| `build_elsherief_comparison_data.py` | Builds the Implicit Hate–inclusive corpus and its Stage 1 matches (see below) |
| `figures_consolidated.ipynb` | Draws Figures 1–13 into `outputs/figures_final/` |
| `build_release.py` | Exports the ID-only data release to [`release/`](../release/README.md) |

## Running

From the repository root:

```bash
python -m audit_pipeline.run_all                      # both variants, then the robustness check
python -m audit_pipeline.run_all --variant full       # primary analysis only
python -m audit_pipeline.stage1_coverage --variant tier12   # one stage, one variant
python -m audit_pipeline.robustness_check             # needs both variants' Stage 4 outputs
python -m audit_pipeline.generate_robustness_table_for_paper   # after robustness_check
```

`scripts/run_audit_pipeline.sh` wraps `run_all` with `--from`/`--to` stage
selection; see [`scripts/README.md`](../scripts/README.md).

### The Implicit Hate comparison

The primary audit covers HateXplain and MHS only, so the primary corpus
contains no Implicit Hate posts. The comparison in Section 5.4 and
Appendix G needs them, so `build_elsherief_comparison_data.py` runs
preprocessing notebooks 04–06 in memory with Implicit Hate included, writes
that corpus to separate `*_with_elsherief` files, and runs Stage 1 on it.
The primary outputs are not touched. Run it after preprocessing, then rerun
Stage 4:

```bash
python -m audit_pipeline.build_elsherief_comparison_data
python -m audit_pipeline.stage4_rollup
```

Without this step, the Implicit Hate side of `outputs/stage4/elsherief/` is
empty.

### The data release

```bash
python -m audit_pipeline.build_release
```

Run it after everything above. It drops post text, replaces each post's
normalized-text key with its source post ID, writes `release/`, and fails
if any released file contains post text (a text column, or any 8 consecutive
words of a post). The FPR files are rebuilt only when the completed FPR
worksheets are present; they contain post text and are not distributed, so
on a fresh clone the released FPR files are kept as they are.

## Pipeline variants

| Variant | Glossary entries used | Outputs |
|---|---|---|
| `full` (primary) | All 340 | `outputs/stage1/` … `outputs/stage4/` |
| `tier12` (robustness check, Appendix A) | Tiers 1 and 2 only (152) | `outputs/stage1_tier12/` … `outputs/stage4_tier12/` |

Tiers describe the provenance of each glossary entry's source:

| Tier | Entries | Source |
|---|---|---|
| 1 | 89 | Peer-reviewed publishers, established journalism, civil-society organizations |
| 2 | 63 | Named authors without formal editorial review, including advocacy sources |
| 3 | 180 | Community-edited sources (179 from rationalwiki.org, 1 from Wikipedia) |
| unknown | 8 | No source URL; excluded from `tier12` |

Tiers are filtered on the glossary itself, before matching, because the
glossary sets both which surface forms are matched and the denominator of
the presence rate. Filtering matches afterwards would leave both
unchanged.

A variant is a `PipelineVariant` (in `config.py`): a name, the allowed
tiers (`None` for all), and the output directory of each stage. Every
stage's `run()` takes one, and `--variant <name>` selects one on the command
line.

## Key constants (`config.py`)

| Constant | Value | Meaning |
|---|---|---|
| `N_MIN` | 30 | Minimum matched posts for a group's estimate to count as stable |
| `DI_THRESHOLD` | 0.8 | Four-fifths rule threshold for DI ratios |

## Outputs

Every stage writes one directory per variant: `outputs/stageN/` for `full`,
`outputs/stageN_tier12/` for `tier12`. All of these tables except
`s1_matches.tsv` are copied unchanged into
[`release/audit_results/`](../release/README.md).

### Stage 1: coverage (`outputs/stage1/`)

| File | Contents |
|---|---|
| `s1_matches.tsv` | One row per (post, dogwhistle, target) match. Contains post text, so it is released as `release/matches/` with post IDs instead |
| `s1_coverage_detailed.tsv` | Matched-post count per (level, target, dogwhistle), with a self-referential flag |
| `s1_coverage_by_level_target.tsv` | Presence rate and type coverage per coding level and target group |
| `s1_coverage_missing.tsv` | Glossary dogwhistles with no match in the corpus |

`outputs/stage1_with_elsherief/` has the same files for the Implicit
Hate–inclusive corpus.

### Stage 2: annotation quality (`outputs/stage2/`)

| File | Contents |
|---|---|
| `s2_annotation_by_level_target.tsv` | Case A (labeled hateful) and Case B (not labeled hateful) counts and rates per coding level and target group |
| `s2_form_labeling_detail.tsv` | Case A/B counts per dogwhistle, with its matched surface forms |

### Stage 3: disparity (`outputs/stage3/`)

| File | Contents |
|---|---|
| `s3_coverage_disparity.tsv` | Pairwise coverage DI between target groups within each level |
| `s3_annotation_disparity.tsv` | Pairwise annotation DI between target groups within each level |
| `s3_cross_level_consistency.tsv` | Change in each group's presence rate, type coverage, and labeling rates from L2 to L3 and from L3 to L4 |

### Stage 4: rollup (`outputs/stage4/`)

| File | Contents |
|---|---|
| `by_group/s4a_coverage_by_group.tsv` | Coverage per reporting group, pooled over levels |
| `by_group/s4a_annotation_by_group.tsv` | Annotation rates per reporting group, pooled over levels |
| `by_group/s4a_pairwise_disparity_by_group.tsv` | Pairwise DI per reporting-group pair |
| `by_group/s4a_pass_fail_summary.tsv` | Per coding level and reporting group: its worst pairwise coverage and annotation DI, and whether each passes the four-fifths rule |
| `by_level_group/s4b_coverage_by_level_group.tsv` | Coverage per coding level and reporting group |
| `by_level_group/s4b_annotation_by_level_group.tsv` | Annotation rates per coding level and reporting group |
| `by_level_group/s4b_pairwise_disparity_by_level_group.tsv` | Pairwise DI per coding level and reporting-group pair |
| `elsherief/s4c_coverage_delta_union_vs_elsherief.tsv` | Presence-rate difference, union minus Implicit Hate, per group |
| `elsherief/s4c_annotation_delta_union_vs_elsherief.tsv` | Correct-labeling-rate difference, union minus Implicit Hate, per group |
| `elsherief/s4c_pairwise_delta_union_vs_elsherief.tsv` | Pairwise DI difference, union minus Implicit Hate |

### Robustness check (`outputs/robustness_check/`)

| File | Contents |
|---|---|
| `robustness_comparison.tsv` | One row per (group pair, level, metric): the `full` and `tier12` values, the four-fifths verdict under each, and whether it flips. Includes one pooled coverage-DI row per pair |
| `robustness_table_for_paper.tsv`, `.tex` | Table 3: the rows of `robustness_comparison.tsv` the paper discusses, selected by `PAPER_ROWS` in `generate_robustness_table_for_paper.py` |
| `README.md` | Column reference |

Pooled coverage DI sums each group's counts over all coding levels before
taking one ratio; it is not the minimum of the per-level ratios. The
`robustness_check.py` docstring explains why, with an example.
