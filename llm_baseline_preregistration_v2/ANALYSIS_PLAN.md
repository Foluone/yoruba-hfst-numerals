# Analysis plan, version 2 (amendment): reduced LLM baseline for Yorùbá numerals

Fixed before the first model call of this version. `prepare` copies this file into the run folder, and its hash is
part of the preregistered manifest. `score` applies it as written.

## Why there is a version 2

Version 1 (protocol 8898bd8b…, deposited at commit fdeb34c of github.com/Foluone/yoruba-hfst-numerals) called for
22,948 model calls. It was stopped for cost on 25 November 2026 after 1,243 zero-shot calls, all on positive Bible
verses (the run went corpus by corpus). Before stopping, only the number of replies, their token counts, their
stop reasons and whether they parsed were looked at; no answer was compared with the gold values. Those 1,243
replies are not used in version 2 and are not reported as results.

Version 2 keeps the question, model, prompts, scoring, measures, margins and decision rule of version 1, and
reduces the design to fit the remaining budget:

- zero-shot only. In the pilot (development verses only, not reported), the five-shot condition gave the same
  values as zero-shot on all 80 verses, so it adds cost without information;
- a seeded sample of 200 positive test verses per corpus (all 97 for the Qur'an) instead of all of them;
- 200 negative test verses per corpus instead of 2,000;
- 100 generation values (25 at each depth) instead of 300;
- 50 repeat-check items instead of 300.

About 1,600 calls in all.

## Question

Does a general-purpose language model, prompted zero-shot, recognise Yorùbá numerals in the sealed test verses of
the four corpora as well as the grammar does, on the same verses and scored the same way? And how well does it
write Standard Yorùbá numerals (described, not compared)?

## Items

- Recognition: 200 positive test verses per corpus (Bible, MENYO-20k, Book of Mormon; all 97 of the Qur'an) and 200
  negative test verses per corpus, drawn with the recorded seed. Gold values come from the English side; verses
  whose English says "one" or "first" were excluded when the gold sets were sealed, so the value 1 is never gold.
- Generation: 100 values from 1–20,000, 25 at each depth 0/1/2/3 (depth = number of lé and dín in the citation
  cardinal), drawn with the recorded seed.

## Model and settings

claude-sonnet-5-5 (Anthropic API), at most 8,192 output tokens (the model may spend some on reasoning before it
answers), one retry when a reply holds no JSON. No temperature is sent: the model rejects the setting, so it
samples at its default and its answers are not deterministic. To measure that, 50 recognition items, drawn with
their own seed, are asked a second time with the same request, and the share of identical answers is reported.
The model name the API reports for each call is recorded; `score` warns if more than one appears.

## Measures (per corpus and pooled)

Grammar: the sealed Pynini table, canonical configuration, read at L2 by the scoring harness (hash recorded).

1. **Accuracy**: gold values read, over gold values (one item per distinct value in a verse).
2. **Accuracy, words found** (model only): a value counts only if the model's entry for it quotes words that
   occur in the verse (compared at L5d). For the grammar this equals accuracy.
3. **False readings**: negative verses on which a system reads a number, a reading of 1 alone not counted
   (value 1 is never gold), and a reply that cannot be parsed counted as a false reading.
4. Reported, not decided on: raw false readings (1 counted); precision on positive verses (read values other
   than 1 that are gold, over all read values other than 1); unparsed replies.

Pooled: accuracy as the mean of the corpus rates weighted by each corpus's number of test gold values (1,850;
389; 1,498; 120), since positives are sampled; false readings as the mean of the corpus rates weighted by each
corpus's number of test negatives (20,214; 4,731; 11,052; 4,373). Neither is weighted by the sample.

## Primary endpoints and decisions

Co-primary, pooled: (2) accuracy with words found and (3) false readings. Accuracy (1) is reported with the same
rule.

For each, the difference model minus grammar (false readings: grammar minus model, so that a positive difference
favours the model) gets a 95% interval from a verse-level bootstrap within corpus (4,000 resamples, seed
20261125). Decision, with margin M = 5 points for accuracy and 2 points for false readings:

- **model better**: the lower limit is above 0;
- **model not worse (within margin)**: the lower limit is above −M;
- **model worse**: the upper limit is below 0 and the lower limit is at or below −M;
- **inconclusive**: otherwise.

The baseline "does as well as the grammar" only if both co-primary endpoints reach "model not worse" or
"model better". Per-corpus decisions are reported for the Bible, MENYO-20k and the Book of Mormon; the Qur'an
(120 values in 97 verses) is described without a decision. No correction for multiple comparisons: per-corpus
results are exploratory. With 200 verses per corpus the intervals are wide, so
"inconclusive" is a likely outcome unless the difference is large; that is a consequence of the budget.

## Generation

Scored against the grammar's own table, so the grammar is correct by construction: the task describes the model,
it is not a comparison. Classes: canonical (a cardinal or pre-noun form at L2), variant or untoned (a recorded
variant, or the canonical form without tone and dot below), other cell (a form of the value in another cell, such
as an ordinal), read in parts (a phrase the grammar reads only as several numbers, such as a decimal-style form),
other value, unread, unparsed. Every output that is not canonical (unparsed aside) goes, blind and in random order,
to a native-speaker checker who did not build the grammar, who judges it standard, an acceptable variant, or
wrong. With two checkers, agreement is reported as Cohen's kappa and disagreements are settled by the consultant;
with one, the judgements are reported as one person's.

## Limitations stated in advance

Smaller samples than version 1 (wider intervals; zero-shot only); the texts are very likely in the model's
training data; gold comes from the English side; 64% of gold values are 10 or less; the model's answers vary
between identical calls (measured by the repeat check); the negatives are a sample (the grammar's rates on all
negatives are reported beside).
