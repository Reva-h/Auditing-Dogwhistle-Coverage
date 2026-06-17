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
| `merged_labels.tsv` | Union-merged label annotations for the labels task |
| `merged_glossary.tsv` | Union-merged inferred-target annotations + `source_domain` and `tier` columns from `outputs/glossary/glossary.tsv` |

### `inter_annotator_agreement.ipynb`

Computes inter-annotator agreement (IAA) between Reva and Ryan for both tasks.

**Metrics computed:**

- Exact match %
- Mean Jaccard similarity
- Macro-averaged Cohen's κ (per-label binary formulation)
- Krippendorff's α with Jaccard distance

Also reports a top-20 per-label κ breakdown and sanity checks against
benchmark values.

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

`merged_labels.tsv` and `merged_glossary.tsv` are consumed by
`data_preprocessing/06_apply_annotations.ipynb`, which applies the merged
annotation schemas to the full corpus and produces
`outputs/unioned_data/06_cleaned_labels.tsv`.
