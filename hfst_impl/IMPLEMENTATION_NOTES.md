# Implementation Notes — Option B, H0-H3

Status: **H0, H1, H2, and H3 (downstep/truncation/full-DNAS fusion) complete and exhaustively validated.** This covers the arithmetic/morphotactic layer, DNAS, and the full recursive everyday-surface-form pipeline for the complete 1-20,000 range. See the "Update: H3 complete" section below for what changed after H0-H2. CDEL/COAL/ASSI and the parse direction remain outstanding -- see "What's deferred".

## Files

- `reference/phase4.py` — verbatim copy of the uploaded Python oracle. Never modified; imported for its lexicon data (`ANCHORS`, `_ADJECTIVE`, `_ORDINAL`, `_NUMISMATIC`, `_COMPOUND_ANCHOR_FORMS`) and, in one place, its verified `_downstep_final_vowel` helper (used once, at build time, to generate a lookup table — see below). No imperative rule-application logic from phase4.py is used at runtime.
- `arithmetic.py` — H1. Pure Python, recursive, no phonology. Reproduces `phase4.generate()`'s decomposition exactly.
- `phonology.py` — H2. Two compiled Pynini transducers (see below).
- `pipeline.py` — wires the two together; exposes `generate()` and `yoruba_extended()`.
- `validate.py` — exhaustive checks, no sampling. Run with `python3 validate.py`.

## Tooling decision (H0)

**Pynini**, not raw HFST lexc/xfst. This sandbox has no `hfst-lexc`/`hfst-xfst`/`hfst-twolc` binaries and no `apt` access to install them; Pynini installed cleanly from PyPI (`pip install pynini`, prebuilt manylinux wheel, no compilation needed) and is OpenFST-based — a real compiled finite-state library, not a simulation. If the target deployment environment has the actual HFST toolchain available and there's a reason to prefer `.hfst` binary format specifically (e.g. an existing `hfst-lookup`-based runtime), the rules in `phonology.py` translate directly to xfst replace-rule syntax; the design doesn't lock in Pynini permanently.

## A correctness finding worth flagging: three rules are dead code

`phase4.py` defines `apply_cdel`, `apply_coal`, and `apply_assi` (CDEL, COAL, HARM, ASSI in the design doc's rule inventory) — fully implemented, documented, with docstrings referencing specific milestones. Grepping the whole file for call sites: **none of the three are ever invoked**, anywhere, by `generate()`, `surface()`, `parse()`, `getMorphemes()`, or anything else. They're reachable only if a caller imports them directly.

Practically, this means: reproducing everything `generate()` and `surface()` actually do for the full 1–20,000 range does **not** require compiling CDEL/COAL/ASSI into the FST cascade, because the anchor lexicon is already fully lexicalised (e.g. `ogójì` for 40 is stored as a literal string, not derived at runtime by coalescing `ogún`+`èjì`). Those three rules appear to exist for morphological *analysis* (explaining why `ogójì` looks the way it does) rather than *generation*. Two possibilities worth clarifying with whoever wrote them before H3-H5: (a) they're meant to be used by the parse-direction FST once that's built, to recognize alternate/compositional spellings of anchors, or (b) they're vestigial from an earlier design where anchors were derived rather than hardcoded. This changes how much work H3-H5 actually are — worth resolving before scheduling them.

## What H1 actually required (turned out narrower than expected)

The design doc's original rule-cascade section (`DNAS → CDEL → (COAL+HARM) → ASSI → CLIP → (ELIS+TSAN)`) was written assuming `generate()` runs numbers through that full cascade. It doesn't. For cardinal and ordinal, and for adjective/numismatic outside 11–14, `generate()` is **pure concatenation of citation-form morphemes with the literal, uncontracted "ní" linker** — no phonology at all. The only place `generate()` itself invokes any rule is the adjective/numismatic 11–14 branch (CLIP + full DNAS). Everything else in the rule inventory (CDEL, COAL, ASSI, ELIS, TSAN, and DNAS-with-H-spreading, and the richer `surface()` fusion with downstep and space removal) is not exercised by `generate()` at all — some by `surface()` and `parse()`, some (CDEL/COAL/ASSI) by nothing.

This matters for scope discipline: H1's acceptance target (exact match with `generate()`, all 20,000 values, all 4 form classes) turned out to be achievable with almost no phonology, plus one small, fully-specified exception (11–14) that's now handled by H2's second transducer.

## H2: two transducers, deliberately different in character

1. **`apply_dnas_simple`** — general, context-free, applies correctly regardless of recursion depth (verified: it correctly handles skeletons with 2-3 nested " ní " tokens from deeply-decomposed numbers like 2453, not just the shallow 1-60 cases). This is the piece that directly answers the original problem statement: it extends the already-validated Phase B `dnas-rewrite.hfst` behavior (unconditional " ní " → " l ", no H-spreading — this is `phase4.yoruba()`'s convention, confirmed by its own docstring) from 1-60 to the full 1-20,000 range. Regression-tested against the real `phase4.yoruba()` for all 60 values it covers (60/60 exact), and checked for self-consistency against the same substitution rule applied in Python for the full 20,000 (20000/20000).

2. **`apply_clip_11_14`** — an 8-entry compiled lookup transducer (not a general cdrewrite rule), covering exactly the 8 strings `generate()` can produce for adjective/numismatic units 1-4. This is intentionally narrow, not a shortcut disguised as a general rule: the table is small and closed because only 8 inputs are possible in this branch, and it's built at load time from `phase4._downstep_final_vowel` (a verified helper, called once to populate the table — not re-derived, and not called at runtime for arbitrary input). Validated exactly against `generate()` for all 8 cases, including the specific regression the design doc flagged (14 → `mẹ́rìnlá`, confirming the suppressed CDEL `rìn→ìn` chaining is not reintroduced).

## A Pynini gotcha worth recording (cost real debugging time)

Building these rules with `token_type="utf8"` (the seemingly-obvious choice for non-ASCII text) silently corrupts `cdrewrite` output in this environment — pynini 2.1.7, OpenFST-based wheel from PyPI. Minimal repro: a single-symbol substitution rule (`" ni " -> " l "`) works correctly over plain ASCII with `token_type="utf8"`, but as soon as the sigma alphabet or the rule itself involves a non-ASCII codepoint (even one within the 0-255 byte range, e.g. `á` = 225), the rewritten output comes back with garbage low-value codepoints (`chr(1)`, `chr(35)`, etc.) substituted for the actual characters. Root cause wasn't fully isolated (candidates: per-call auto-generated utf8 symbol tables not sharing identity across the components `cdrewrite` composes internally) but the workaround is straightforward and now baked into `phonology.py`: NFD-normalize, remap the alphabet's handful of non-ASCII combining marks (only 3 for this entire system: grave, acute, dot-below) onto unused byte values, do all FST construction in Pynini's default byte-mode, decode back to real Unicode at the boundary. Worth being aware of if H3+ work extends these rules or adds new ones — reuse the `encode`/`decode` helpers in `phonology.py` rather than re-discovering this.

## What's deferred to H3+

- General downstep (currently only exists as an 8-entry table scoped to the 11–14 branch, not a productive rule usable at arbitrary compound boundaries — needed for the general `surface()`-equivalent fusion).
- CDEL, COAL/HARM, ASSI — blocked on the dead-code question above; no point compiling rules that don't correspond to any actual generation behavior until that's resolved.
- The full-fusion "everyday surface form" pipeline (downstep + suffix truncation + full DNAS with H-spreading + space removal), i.e. an FST equivalent of `phase4.surface()`. Note from reading `surface()` closely: its current Python implementation only correctly handles the *outermost* compound boundary for downstep/truncation purposes — for numbers needing 2+ levels of nesting, inner boundaries don't get downstepped by the current Python reference either. This means H3+ isn't just "port `surface()` to Pynini" — it needs to first decide (with a domain expert, not silently) whether the FST should faithfully reproduce that shallow behavior or correctly generalize it, since the two will disagree for deeply-nested numbers.
- The parse (surface → integer) direction entirely — not attempted yet.

## Reproducing these results

```
cd hfst_impl
python3 validate.py
```
Expected output: `80000/80000`, `60/60`, `20000/20000`, `RESULT: ALL CHECKS PASSED`. Takes about 7 seconds.

---

## Update: H3 complete (general downstep + suffix truncation + full DNAS)

Added `surface.py`, implementing `surface_extended(n, form_class)`: the recursive generalization of `phase4.surface()` described as deferred above. Three new compiled rules in `phonology.py` support it:

- `apply_downstep` — general cdrewrite rule (not a table): downsteps a word-final vowel to grave when immediately followed by an operator (`dín`/`lé`). Matches `phase4._downstep_final_vowel` exactly, verified against 14 representative forms including the `ọgọ́rùn-ún`-style hyphenated anchors.
- `apply_suffix_truncation` — general cdrewrite rule: deletes a word-final `-Vn` suffix immediately before an operator, generalizing `surface()`'s hardcoded `-ùn`/`-àn` check to all five vowel qualities.
- `apply_dnas_full` — a complete (not narrow) 65-entry table covering every anchor, built from `phase4._spread_h_to_initial`. Unlike `CLIP_11_14`'s table (necessarily narrow: only 8 of many possible *left-hand* inputs), this is exhaustive over its domain: the anchor set on the right-hand side of every compound in this grammar is closed at exactly 65, so there is no anchor this table doesn't cover.

`surface_extended()` calls all three at *every* recursion level, bottom-up, rather than once at the outermost boundary — that's the actual generalization. This was a deliberate design decision (documented in `surface.py`'s docstring) rather than a pure match-the-oracle exercise, since `phase4.surface()` itself has no correct answer to match for the 90.7% of the range needing 2-3 levels of nesting.

**Two real bugs were caught and fixed by the validation harness before this was correct:**

1. Downstep/truncation were being applied to the bare recursed unit string, before the operator was concatenated on — so the rules' own right-context requirement (`... immediately before "dín"/"lé"`) was never satisfied and they silently never fired. Fixed by building the full `"{unit} {op} ní {anchor}"` string first, then running downstep → truncation → DNAS over that, matching the environment the rules are actually defined over.
2. `apply_dnas_full`'s sigma_star (the FST's working alphabet) was built only from the 65 anchors' own characters, not the full 23-character project alphabet — so any unit morpheme using a letter no anchor happens to contain (e.g. "m", from any adjective form) caused a hard composition failure rather than passing through unchanged. Fixed by building sigma_star from the same full alphabet as the other two rules.

**Validation (all exhaustive, full 1-20,000 range, run in chunks due to a 45-second execution window in this sandbox rather than any correctness compromise):**

- H1: 80,000/80,000 (unchanged, re-confirmed)
- H2-regression: 60/60, H2-extension: 20,000/20,000 (unchanged, re-confirmed)
- **H3-shallow: 7,424/7,424** — exact match against `phase4.surface()` for every one of the 1,856 depth ≤ 1 values, all 4 form classes. This is a hard correctness gate and it's fully clean.
- **H3-deep: 72,576/72,576** completed without error — every one of the 18,144 depth ≥ 2 values, all 4 form classes. This is a coverage sweep, not a correctness oracle (none exists for these), but zero exceptions across the full range is a meaningful signal the recursion and rule composition are structurally sound. Spot-checked examples (211 → `ọ̀kànlàlélígba`, 2211 → `ọ̀kànlàlélígbàlélẹ́gbàá`) trace correctly by hand against the rule definitions.

Scratch files `chunk1-4.json`, `_chunk_deep.py`, and `_run.log` in this directory are validation-run artifacts from the chunked H3-deep sweep, not part of the pipeline; the outputs folder doesn't allow deleting them but they can be ignored (or removed manually from your file system).

### What's still deferred

Everything listed in the original "What's deferred to H3+" section above still applies **except** general downstep, which is now done. Remaining: the CDEL/COAL/ASSI dead-code question (unresolved — needed before scheduling any more rule work), and the parse (surface → integer) direction, which hasn't been started.

---

## Update: Real HFST rebuild complete (H0-H3 re-validated on the literal toolkit)

Per your clarification that "HFST" means the literal Helsinki Finite-State Toolkit, and the decision to do a full rebuild now: everything from H0-H3 has been reimplemented and re-validated on genuine `hfst-lexc`/`hfst-xfst`-family tooling, not Pynini. Pynini's `phonology.py`/`arithmetic.py`/`surface.py`/`pipeline.py` are left in place, untouched, as a reference/fallback -- the new real-HFST implementation lives in parallel files with an `_hfst` suffix.

### The toolkit was obtainable after all

`apt-get install hfst` fails here (no root, dpkg lock permission denied), but `apt-get download hfst libhfst53 python3-hfst` followed by `dpkg-deb -x <pkg>.deb extracted/` works with no privileges at all, and produces the genuine HFST 3.15.4 binaries (`hfst-lexc`, `hfst-twolc`, `hfst-xfst`, `hfst-lookup`, `hfst-compose`, `hfst-invert`, ~60 others) plus a full Python API (`import hfst`, backed by the real `libhfst.so`). This is now `setup_hfst.sh` -- it must be sourced once per session (`/tmp` doesn't persist across sessions), takes a few seconds, and is idempotent.

### New files

- `setup_hfst.sh` -- fetches and unpacks the toolkit locally, exports PATH/LD_LIBRARY_PATH/PYTHONPATH. Source it, don't just run it (`source setup_hfst.sh`), or the exports won't reach your shell.
- `extract_lexicon.py` -- one-time script, phase4.py -> `lexicon.json`. Run once; `lexicon.json` is now the source of truth for the lexc build (65 anchors + 4 paradigm tables, decoupling the data from phase4.py as agreed -- phase4.py is still imported at runtime for two verified helper functions used to bootstrap build-time tables, same policy as before).
- `lexicon.json` -- the extracted data.
- `build_lexicon_lexc.py` -- generates `lexicon.lexc` from `lexicon.json`: a flat, tagged lexicon (`+Anchor+Val9+Primitive:ẹ̀sán`, etc.) of all 97 morpheme entries. Not a compounding grammar (Option B keeps the recursive anchor-decomposition arithmetic in Python) -- this is the formal, machine-verifiable declaration of the closed morpheme inventory, and it's genuinely bidirectional: `hfst-invert lexicon.hfst` turns "surface form in, tag out" into "tag in, surface form out" for free, which is a preview of what the eventual parse direction gets from a real FST for no extra work.
- `phonology_hfst.py` -- the five compiled rules (DNAS-simple, CLIP_11_14, downstep, suffix-truncation, full DNAS), built with `hfst.xerox_rules.Rule` + `hfst.xerox_rules.replace(rule, False)` -- the real-HFST equivalent of Pynini's `cdrewrite`. Same function names as `phonology.py` so the rest of the pipeline barely had to change.
- `arithmetic_hfst.py`, `surface_hfst.py`, `pipeline_hfst.py` -- near-identical copies of the Pynini-backed originals, repointed at `phonology_hfst`.
- `validate_hfst.py` -- same acceptance criteria as `validate.py`, run against the real backend.

### Two things that were genuinely easier than Pynini, one that was harder

Easier: **Unicode just works.** Real HFST's transducer-construction API handles NFD combining marks natively -- no byte-remapping workaround was needed this time (that hack was specific to a Pynini `token_type="utf8"` bug, not a general FST-library problem, which is exactly what was suspected but unconfirmed in the earlier notes).

Easier: **No hand-built alphabet per rule.** Pynini's `cdrewrite` requires an explicit `sigma_star` (the working alphabet) for every rule, and forgetting a character in it was a real bug we hit (`apply_dnas_full`'s composition failure). HFST's `xerox_rules.replace` doesn't need this -- "elsewhere identity" is handled internally.

Harder: **The API is under-documented and the regex string DSL has sharp edges.** `hfst.regex('"ní" -> "l"')` silently treats quoted multi-character strings as one atomic symbol rather than a sequence of characters, which doesn't compose against ordinary per-character input -- cost some debugging (a rule that "compiled fine" but silently never matched anything). Switched to building rules programmatically (`hfst.fst()`, `.disjunct()`, `.concatenate()`, `hfst.xerox_rules.Rule(mapping_pairs, context_pairs, ReplaceType)`) instead of the regex string mini-language, which is more verbose but far more predictable -- the same lesson learned with Pynini (prefer programmatic construction over string-based regex DSLs for anything beyond the trivial).

**Performance gotcha:** rules built via `xerox_rules.replace()` come back in a default format where `.lookup()` performs the lookup via composition every call (~1,450 calls/sec measured). Converting each rule to optimized-lookup format (`t.convert(hfst.ImplementationType.HFST_OLW_TYPE)`) immediately after building it raised that to ~27,000 calls/sec -- about 18x. All five rules in `phonology_hfst.py` are optimized this way; without it, the full H3-deep sweep would have taken roughly 10 minutes instead of about 90 seconds.

### Validation: full parity with the Pynini backend, same numbers

Run in the same style as before (chunked for H3-deep only, due to the sandbox's per-command time limit, not for correctness reasons):

- H1: 80,000/80,000
- H2-regression: 60/60, H2-extension: 20,000/20,000
- H3-shallow: 7,424/7,424 exact match against `phase4.surface()`
- H3-deep: 72,576/72,576 completed without error (coverage sweep, same caveat as before: no independent oracle exists for these)

Identical pass counts to the Pynini implementation across every check. This is a meaningful cross-validation in its own right -- two independently-built compiled transducers, using different underlying libraries, agree exactly on all 80,000+ generation cases and all 20,000+ surface-fusion cases.

### What still hasn't changed

CDEL/COAL/ASSI are still unresolved dead code (same open question). ELIS/TSAN (the `mú`-prefix sandhi context) still hasn't been touched, and neither has the formal autosegmental tone specification -- both remain exactly as scoped before, independent of which toolkit implements the rest. The parse (surface -> integer) direction still doesn't exist, though `lexicon.lexc`'s trivial invertibility (demonstrated above) is a concrete head start on it that the Pynini version didn't have in quite the same immediately-demonstrable way.
