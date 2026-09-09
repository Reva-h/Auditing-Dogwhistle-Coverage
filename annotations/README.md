# Annotations

Human annotation files and merge/IAA notebooks for the dogwhistle benchmark audit.

## Annotators

Two annotators (Reva and Ryan) independently labeled two tasks:

| Task | Key | Description |
|---|---|---|
| Label mapping | `dataset` + `raw_target_label` | Map each raw dataset target label to one or more schema labels |
| Glossary inference | `term` | Infer the target group for each dogwhistle glossary entry |

## Raw Annotation Files

| File | Task | Contents |
|---|---|---|
| `reva_labels.tsv` | Label mapping | Reva's `dest_label` assignments per `(dataset, raw_target_label)` |
| `ryan_labels.tsv` | Label mapping | Ryan's `dest_label` assignments per `(dataset, raw_target_label)` |
| `reva_glossary.tsv` | Glossary inference | Reva's `inferred_target` assignments per `term` |
| `ryan_glossary.tsv` | Glossary inference | Ryan's `inferred_target` assignments per `term` |

Labels are comma-separated schema strings (e.g. `race_black, origin_specific country`).
Blank or NaN entries are treated as `_unknown`.

## Notebooks

### `merge_annotation_union.ipynb`

Merges Reva and Ryan's annotations using a union strategy, enriches the glossary
output with provenance tier data, and runs a disagreement analysis.

**Merge strategy:**

1. Parse each annotator's labels into a set.
2. Take the union of the two sets.
3. Remove `_unknown` from the union when at least one real label exists.
4. Serialize deterministically (alphabetical, comma-joined).

**Disagreement analysis:**

Classifies every item into one of five relationship categories:

| Class | Meaning |
|---|---|
| `exact_agreement` | Both annotators assigned identical real labels |
| `both_unknown` | Neither assigned any real labels |
| `additive` | Real labels differ; one set ⊆ the other (union is benign) |
| `partial_overlap` | Intersection non-empty; neither set is a subset |
| `disjoint` | No shared labels (union merges incompatible judgements) |

Results and figures are reported separately for the labels task and the
glossary task.

**Outputs written:**

| File | Description |
|---|---|
| `merged_labels.tsv` | Naive union-merged label annotations for the labels task |
| `merged_glossary.tsv` | Naive union-merged inferred-target annotations + `source_domain` and `tier` columns from `outputs/glossary/glossary.tsv` |

**Disagreement resolution (same notebook, later section):** the naive union
handles several disagreement patterns poorly (e.g. specificity explosion,
transgender-label granularity mismatches). A set of rule-based resolutions
is applied on top of the naive merge, plus manual, hand-filled-in decisions
for the small number of cases (~30) no rule resolves. Writes:

| File | Description |
|---|---|
| `merged_glossary_resolved.tsv` | `merged_glossary.tsv` with `inferred_target_merged` replaced by the rule/manual resolution, plus `merge_method` and `merge_flag` columns |
| `merged_labels_resolved.tsv` | Same, for the labels task |

### `inter_annotator_agreement.ipynb`

Computes inter-annotator agreement (IAA) between Reva and Ryan for both tasks.
Reads the raw `reva_*.tsv`/`ryan_*.tsv` files directly (not the merged files).

**Metrics computed:**

- Exact match %
- Mean Jaccard similarity
- Macro-averaged Cohen's κ (per-label binary formulation)
- Krippendorff's α with Jaccard distance

Also reports a top-20 per-label κ breakdown and sanity checks against
benchmark values.

**Resolution before/after diff (later section):** reads `merged_labels.tsv`,
`merged_glossary.tsv`, and their `_resolved` counterparts (all four, written
by `merge_annotation_union.ipynb`) to quantify how much the rule/manual
resolution changed the naive union merge. Running this section requires
`merge_annotation_union.ipynb` to have been run first; the headline IAA
metrics above do not.

## Merged Output Schema

### `merged_labels.tsv`

Columns from `reva_labels.tsv` (all reva columns as base) plus:

| Column | Description |
|---|---|
| `dest_label_reva` | Reva's original label string |
| `dest_label_ryan` | Ryan's original label string |
| `dest_label_merged` | Union-merged label string |

### `merged_glossary.tsv`

Columns from `reva_glossary.tsv` plus:

| Column | Description |
|---|---|
| `inferred_target_reva` | Reva's original inferred target string |
| `inferred_target_ryan` | Ryan's original inferred target string |
| `inferred_target_merged` | Union-merged inferred target string |
| `source_domain` | Domain of the description source URL (from `glossary.tsv`) |
| `tier` | Provenance tier: `1` (high), `2` (moderate), `3` (wiki), `unknown` |

## Downstream Use

`data_preprocessing/06_apply_annotations.ipynb` does **not** read the merged
files in this directory — it reads `reva_labels.tsv`, `ryan_labels.tsv`,
`reva_glossary.tsv`, and `ryan_glossary.tsv` directly and derives its own
union in-notebook, then applies the result to the full corpus to produce
`outputs/unioned_data/06_cleaned_labels.tsv`.

`merged_labels.tsv`, `merged_glossary.tsv`, and their `_resolved`
counterparts are consumed only by `inter_annotator_agreement.ipynb`'s
resolution before/after diff section (see above) — they are not an input to
the main preprocessing pipeline.
