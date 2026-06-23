# FPR Annotation Task — Briefing Sheet

## What you are doing
You will read 225 social media posts and judge whether a specific word or phrase
in each post is being used as a dogwhistle (coded hate speech) or not.

## The judgment you are making
For each post, a specific word or phrase is identified in the `matched_surface_form`
column. This word or phrase is a documented dogwhistle term. Your job is to judge
how it is being used IN THIS SPECIFIC POST.

Choose one of three options in the `judgment` column:

**Hateful** — The term appears to be used with its dogwhistle meaning, targeting
a group. The post seems to be expressing coded hate or bias.

**Not Hateful** — The term appears in a context that is not hateful — for example,
counter-speech criticizing the term's use, a journalistic or academic discussion,
or neutral factual description.

**Unknown** — You cannot tell from the post text alone whether this is genuine
dogwhistle use or a non-hateful context. Use this when genuinely uncertain —
do not guess.

## What to ignore
- Do not look up the post or try to find additional context
- Do not consider the `benchmark_label` column when making your judgment —
  that is what we are evaluating, not what you should rely on
- Focus only on the post text itself

## Important notes
- Some posts contain slurs and offensive language. This is expected.
- Some posts are ambiguous. Use "Unknown" freely — it is a valid answer.
- If a post contains `<number>` or `<percent>`, these are placeholders for
  numbers that were anonymized in the original dataset.
- Aim for roughly 2 minutes per post. Total task time: approximately 7–8 hours.
  You do not need to complete this in one sitting.

## Questions
If you are unsure whether a post qualifies as "Hateful" vs. "Not Hateful",
ask yourself: is the author of this post expressing or amplifying a hateful
view toward a group, or critiquing it?
