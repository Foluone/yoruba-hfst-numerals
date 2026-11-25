# Analysis plan: LLM baseline for Yorùbá numerals

Fixed before the first model call. `prepare` copies this file into the run folder, and its hash is part of the
preregistered manifest. `score` applies it as written.

## Question

Does a general-purpose language model, prompted zero-shot and five-shot, recognise Yorùbá numerals in the sealed
test verses of the four corpora as well as the grammar does, on the same verses and scored the same way? And how
well does it write Standard Yorùbá numerals (described, not compared)?

## Items

- Recognition: every positive test verse of the four sealed runs (Bible, Qur'an, MENYO-20k, Book of Mormon) and
  2,000 negative test verses per corpus, drawn with the recorded seed. Gold values come from the English side;
  verses whose English says "one" or "first" were excluded when the gold sets were sealed, so the value 1 is
  never gold.
- Generation: 300 values from 1–20,000, drawn with the recorded seed, 60/80/80/80 at depth 0/1/2/3 (depth =
  number of lé and dín in the citation cardinal).
- Five shots for the five-shot condition, drawn from development verses that the grammar reads completely and
  that share less than 20% of their five-word sequences with any test verse.

## Model and settings

One model (config.json), at most 8,192 output tokens (the model may spend some on reasoning before it answers), one retry when a reply holds no JSON. No temperature is
sent: the model chosen rejects the setting, so it samples at its default and its answers are not deterministic.
To measure that, 300 recognition items, drawn with their own seed, are asked a second time (zero-shot, the same
request), and the share of identical answers is reported. The model name the API reports for each call is
recorded; `score` warns if more than one appears.

## Measures (per corpus and pooled, per condition)

Grammar: the sealed Pynini table, canonical configuration, read at L2 by the scoring harness (hash recorded).

1. **Accuracy**: gold values read, over gold values (one item per distinct value in a verse).
2. **Accuracy, words found** (model only): a value counts only if the model's entry for it quotes words that
   occur in the verse (compared at L5d). For the grammar this equals accuracy.
3. **False readings**: negative verses on which a system reads a number, a reading of 1 alone not counted
   (value 1 is never gold), and a reply that cannot be parsed counted as a false reading.
4. Reported, not decided on: raw false readings (1 counted); precision on positive verses (read values other
   than 1 that are gold, over all read values other than 1); unparsed replies.

Pooled: accuracy over all positive verses; false readings as the mean of the corpus rates weighted by each
corpus's number of test negatives (20,214; 4,373; 11,052; 4,731), not by the sample.

## Primary endpoints and decisions

Co-primary, pooled, each condition separately: (2) accuracy with words found and (3) false readings.
Accuracy (1) is reported with the same rule.

For each, the difference model minus grammar (false readings: grammar minus model, so that a positive difference
favours the model) gets a 95% interval from a verse-level bootstrap within corpus (4,000 resamples, seed
20261125). Decision, with margin M = 5 points for accuracy and 2 points for false readings:

- **model better**: the lower limit is above 0;
- **model not worse (within margin)**: the lower limit is above −M;
- **model worse**: the upper limit is below 0 and the lower limit is at or below −M;
- **inconclusive**: otherwise.

The baseline "does as well as the grammar" only if both co-primary endpoints reach "model not worse" or
"model better" in the same condition. Per-corpus decisions are reported for the Bible, MENYO-20k and the Book of
Mormon; the Qur'an (120 values in 97 verses) is described without a decision. No correction for multiple
comparisons: per-corpus results are exploratory.

## Generation

Scored against the grammar's own table, so the grammar is correct by construction: the task describes the model,
it is not a comparison. Classes: canonical (a cardinal or pre-noun form at L2), variant or untoned (a recorded
variant, or the canonical form without tone and dot below), other cell (a form of the value in another cell, such
as an ordinal), read in parts (a phrase the grammar reads only as several numbers, such as a decimal-style
form), other value, unread, unparsed. Every output that is not canonical (unparsed aside) goes, blind and
in random order, to a native-speaker checker who did not build the grammar, who judges it standard, an acceptable
variant, or wrong. With two checkers, agreement is reported as Cohen's kappa and disagreements are settled by the
consultant; with one, the judgements are reported as one person's.

## Limitations stated in advance

The texts are very likely in the model's training data; gold comes from the English side; 64% of gold values are
10 or less; the model's answers vary between identical calls (measured by the repeat check); the negatives are a sample (the grammar's rates on all
negatives are reported beside).
