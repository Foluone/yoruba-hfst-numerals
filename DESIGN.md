# HFST Design Document — Yoruba Vigesimal Numeral System

**Status:** Draft for review
**Scope:** Design and milestone plan for a compiled finite-state transducer covering the full cardinal/adjective/ordinal/numismatic numeral system, 1–20,000, replacing the Phase B pipeline that currently only covers 1–60.
**Source of truth for linguistic facts:** `phase4.py` (Python oracle). This document treats `phase4.py` as the specification to reproduce, not as code to be ported line-by-line — the goal is a declarative finite-state grammar that is *equivalent in output* to `generate()`/`yoruba()`, not a translation of their control flow.

---

## 1. Problem statement

The current HFST artifacts (`lexicon.lexc`, `rules.twolc`, `build_dnas.py`, `compose_fst.py`) validate only 1–60. Two structural reasons this hasn't scaled to 1–20,000:

1. **The morphotactics aren't recursive enough.** Numeral compounding (`unit + lé-ní/dín-ní + anchor`) can nest more than once. Example: 2453 decomposes against anchor 2000 (unit 453), and 453 itself decomposes again against 400/500 (unit 47), which decomposes again against 40/50 (unit 3, an anchor — recursion stops). That's three levels of nesting. The existing parser-side fix (M13, `_parse_anchor_right`) is documented as a "recursive fallback for **depth-2** compounds" — insufficient for values that need 3+ levels.
2. **The phonological rules aren't compiled at all, or are compiled vacuously.** `rules.twolc` currently only encodes ASSI, which is vacuous for 1–60. DNAS is handled by a separate ad hoc rewrite transducer because it's length-changing (`ní` + vowel-initial word → `l` + fused vowel is not expressible as a parallel two-level constraint). CDEL, COAL, HARM, CLIP, ELIS, and TSAN exist only as imperative Python and have never been compiled.

This document lays out the target architecture and a milestone sequence (`H0`–`H11`, continuing the project's existing `M`/`A`/`B`/`C`/`D` milestone numbering convention) to close both gaps.

---

## 2. Architecture decision

Two candidate designs were considered.

**Option A — Pure recursive lexc grammar.** The anchor lexicon and compounding rules are encoded directly as self-referential lexc continuation classes, so anchor-selection arithmetic (`nearestAnchors`) is baked into the automaton structure itself. Fully self-contained; parsing (surface → integer) falls out of inverting the transducer for free.

**Option B — Hybrid.** A small deterministic pre/post-processor performs the arithmetic (`nearestAnchors`, recursive decomposition into a tagged morpheme skeleton, e.g. `UNIT[453] OP[ADD] ANCHOR[2000]`), and only the *phonological realization* — DNAS, CDEL, COAL, HARM, ASSI, CLIP, ELIS, TSAN — is a compiled HFST rule cascade applied to the tagged skeleton string.

**Decision: start with Option B, treat Option A as a later consolidation target.**

Rationale: Option B mirrors the module boundary that already exists in `phase4.py` (`getMorphemes()`/`generate()` do arithmetic; `apply_*` functions do phonology), which means the Python oracle can validate each phonological rule in isolation during development. It is also much lower-risk to build incrementally. Option A is the architecturally "purer" endpoint — a single invertible transducer with no external logic — and should be revisited once Option B is fully validated, at which point the (by-then well-understood) arithmetic can be re-expressed as lexc continuation classes.

This choice should be revisited at **H0** if the implementer disagrees; it's a judgment call, not a constraint from the linguistics.

### Tooling

Either the classic HFST toolchain (`lexc` + `xfst`/`twolc` compiled via `hfst-lexc`, `hfst-xfst`, composed with `hfst-compose`) or **Pynini** (OpenFST-based, Python-hosted, purpose-built for numeral/text-normalization grammars) can implement this design. Pynini is worth serious consideration: it lets the team keep using Python as the *build-time* scripting language (which the team already knows well) while still producing a genuine compiled finite-state object — categorically different from `phase4.py`'s imperative approach, since the FST is built via composition/union/concatenation of string relations rather than runtime control flow. **This choice is a required decision at H0** and affects every subsequent milestone's file formats.

---

## 3. Component inventory

| Python construct | HFST equivalent | Notes |
|---|---|---|
| `_ANCHOR_RAW` (65 entries) | lexc lexicon entries, one sublexicon per anchor series (primitive / multiplicative / subtractive, grouped by 20-series / igba-series / ẹgbàá-series) | Static; direct port |
| `nearestAnchors()` + recursive `generate()` | Recursive lexc continuation classes (Option A) or pre-processor (Option B) | Must support 3+ levels of nesting — see §1 |
| `apply_dnas` | Ordered replace rule, length-changing | Already partially attempted (`build_dnas.py`); generalize |
| `apply_cdel` (two environments) | Two ordered replace rules | `word-final` environment is lossy in Python parse direction — see §6 |
| `apply_coal` + `select_harm_prefix` | Ordered replace rule with context-dependent output (harmonic prefix choice is conditioned on the first vowel of the following morpheme) | HARM and COAL are entangled in the Python code and should probably be compiled as one rule, not two |
| `apply_assi` | Ordered replace rule | Interacts with COAL (both touch the `ẹgb-`/`igba` boundary) |
| `apply_clip` | Ordered replace rule, string-literal contraction (`lélẹ́wàá` → `lá`), bounded to 11–14 | Must be sequenced correctly relative to CDEL (project note: CDEL's `rìn→ìn` was previously chained here and is now explicitly suppressed — do not reintroduce it) |
| `apply_elis` + `_apply_downstep` + `apply_tsan` | Ordered replace rule cascade for the `mú`-prefix tonal sandhi context | Only the ELIS context is tonal-sandhi-active per the Python docstring; the four-boundary sandhi of forms like 21 is handled elsewhere (trie/skeleton parser) and needs its own design decision (see Open Questions) |
| `yoruba()` / `validate_hfst.py` | Exhaustive test harness | Extend from 60 → 20,000 values, both directions |

---

## 4. Rule cascade and ordering

Several rules are non-length-preserving (DNAS, CDEL, CLIP), which rules out plain parallel twolc constraints for those — they require ordered composition, xfst-style. The Python docstring names four interacting rule pairs; each implies a required composition order:

- COAL × HARM — HARM's prefix choice must be resolved before/within COAL's coalescence (they should likely be one compiled rule, see §3).
- ELIS × TSAN — ELIS (elision + H-tone docking) feeds TSAN (downstep cascade); ELIS must compose before TSAN.
- CLIP × CDEL — CLIP must compose in a way that does *not* re-trigger the now-suppressed CDEL `rìn→ìn` alternation; verify with a regression test that explicitly checks 14 → `mẹ́rìnlá` (not `mẹ́ìnlá`).
- ASSI × COAL — both rewrite the `igba`/`ẹgb-` boundary; needs a single resolved precedence, not independent rules that could both fire.

Target compose order (mirrors the existing M4–M10 milestone sequence, which was presumably chosen for a reason):

`DNAS → CDEL → (COAL+HARM) → ASSI → CLIP → (ELIS+TSAN)`

This order is a starting hypothesis, not settled — **H8** includes explicitly re-deriving and documenting the correct order from test failures, since rule interaction bugs are exactly the kind of thing that won't be visible until composed.

---

## 5. Tone representation

Use **NFD** (decomposed combining characters) as the FST's working alphabet, not NFC. This matches what the Python code already does internally (`nfd()`/`nfc()` round-tripping) and means every tone rule (downstep insertion, ACUTE↔GRAVE substitution) is a single-symbol replace rule instead of requiring a full precomposed-codepoint alternation table. Convert to NFC only at the final output stage.

**Explicitly out of scope:** full autosegmental tone-tier machinery (Goldsmith 1976; Pulleyblank 1986), which the Python docstring already flags as unimplemented (`_apply_downstep` is a heuristic). Reproducing the Python's flat-diacritic heuristic is the target for this phase; a true tonal tier is a separate, larger project (see §8, H11).

---

## 6. Known lossy/ambiguous cases to resolve explicitly

- `apply_cdel(..., environment="word-final", direction="parse")` is explicitly documented as lossy in Python — the deleted consonant+syllable cannot be recovered from the surface form alone. A real invertible FST has three options: (a) accept the ambiguity and return multiple weighted candidates on inversion, disambiguated by a downstream dictionary/anchor-lookup filter; (b) constrain the rule's domain so it never applies in a context where inversion is required; (c) keep this specific case handled outside the FST (status quo, via the trie/skeleton parser). **Decision needed at H3.**
- The four-boundary tonal sandhi in compounds like 21 (`mọ́kànlélógún`) is explicitly stated in the Python docstring to bypass `apply_tsan` and go through `_split_compound` + DNAS reversal in the standalone parser instead. This needs an explicit design decision: fold into the H7 rule cascade, or keep as a separate parse-side component. **Decision needed at H7.**

---

## 7. Milestones

Each milestone lists an acceptance criterion that can be checked mechanically against the Python oracle (`generate()`/`yoruba()`/`getMorphemes()`/`decompose()`), so tracking doesn't depend on subjective sign-off.

- [x] **H0 — Spec extraction & tooling decision.** Tooling: **Pynini** (no HFST lexc/xfst binaries available in the build environment; Pynini installs cleanly from PyPI and is a real OpenFST-based compiled-FST library, not a simulation). Option B confirmed. See `hfst_impl/IMPLEMENTATION_NOTES.md` for the full writeup, including a load-bearing finding: `apply_cdel`, `apply_coal`, and `apply_assi` are defined in `phase4.py` but never actually called anywhere — dead code. This descopes H3-H5 pending a decision on why they exist (see notes) and narrows what H1/H2 actually needed to cover.

- [x] **H1 — Recursive morphotactics, structure only.** Implemented in `hfst_impl/arithmetic.py` as a pure Python recursive decomposition (not a lexc grammar — see note below). *Acceptance met: exact string match against `phase4.generate(n, fc)` for all n in 1–20,000, all 4 form classes (80,000/80,000), including 3+-level nesting cases like 2453.* Note: turned out `generate()` itself does almost no phonology outside one narrow branch (adjective/numismatic 11–14), so this milestone ended up needing far less rule-cascade support than the original design assumed — see implementation notes for what `generate()` actually does vs. what the full rule inventory would suggest.

- [x] **H2 — DNAS rule.** Two compiled Pynini transducers in `hfst_impl/phonology.py`: (1) `apply_dnas_simple` — general, context-free " ní " → " l " substitution (the *simplified*, no-H-spread variant matching the already-validated `phase4.yoruba()`/`dnas-rewrite.hfst` convention), extended from 1–60 to the full 1–20,000 range; (2) `apply_clip_11_14` — narrow 8-entry lookup transducer completing the one branch where `generate()` bakes in full DNAS+CLIP. *Acceptance met: 60/60 exact match against real `phase4.yoruba()` (regression), 20000/20000 self-consistent extension, 8/8 exact match on the CLIP branch including the `mẹ́rìnlá` regression.* The fuller H-spreading DNAS (`phase4.apply_dnas`) beyond this narrow branch is not yet a general rule — deferred to H3+ alongside general downstep.

- [x] **H3 — General downstep + suffix truncation + full DNAS (recursive surface fusion).** Not in the original plan at this position -- pulled forward from H8's "full cascade composition" because matching `phase4.surface()` at all (not just `generate()`) turned out to require it, independent of the CDEL/COAL/ASSI questions. Implemented in `hfst_impl/surface.py` (`surface_extended()`) plus three new rules in `phonology.py`: a general (not table-based) downstep cdrewrite rule, a general suffix-truncation rule, and a complete 65-entry full-DNAS-with-H-spread table. Applied recursively at every compound boundary, deliberately generalizing past `phase4.surface()`'s outermost-boundary-only behavior (measured: 90.7% of the range needs 2-3 levels of nesting, and the Python reference only downsteps the outermost one -- see implementation notes). *Acceptance met: H3-shallow 7,424/7,424 exact match against `phase4.surface()` for all depth<=1 values (the range where the oracle is trustworthy); H3-deep 72,576/72,576 completed without error across all depth>=2 values (coverage sweep, no independent oracle exists there).* Two real bugs were caught and fixed during validation (rule right-context ordering; an incomplete FST alphabet causing composition failures) -- see notes for both.

- [ ] **H4 — CDEL rule(s).** *(renumbered from H3)* Compile both environments (`inter-vocalic-rounded`, `word-final`). Resolve the lossy-parse question from Section 6. Still blocked on the dead-code question from H0: confirm whether this rule is needed for anything before building it. *Acceptance: matches `apply_cdel` generate-direction output on all applicable forms; parse-direction ambiguity handling decision documented and implemented.*

- [ ] **H5 — COAL + HARM.** *(renumbered from H4)* Compile as a single context-dependent rule (harmonic prefix selection based on following vowel). Same dead-code caveat as H4. *Acceptance: matches `apply_coal`/`select_harm_prefix` for all `ogun`-, `igba`-, `egbaa`-series compounds in range.*

- [ ] **H6 — ASSI rule.** *(renumbered from H5)* Compile the igba-series vowel assimilation. Same dead-code caveat as H4. *Acceptance: matches `apply_assi` output; regression test confirms no double-firing with COAL on the same boundary.*

- [x] **CLIP rule** *(was H6, done early as part of H2/H3)* -- `apply_clip_11_14` in `phonology.py`, covering cardinal/adjective/numismatic. Ordinal 11-14 is not clipped (matches `phase4.generate()`/`surface()`, which don't clip it either -- confirmed deliberate, not an oversight, by checking `surface()`'s branch conditions directly).

- [ ] **H7 — ELIS + TSAN.** Compile the `mu`-prefix elision/downstep cascade. Resolve the four-boundary sandhi scoping question from Section 6. *Acceptance: matches `apply_elis`/`apply_tsan` on all applicable forms; decision on 21-type compounds documented and implemented.*

- [ ] **H8 — Full cascade composition.** Largely superseded by H3 for the DNAS/downstep/truncation/CLIP portion; what remains here is folding in H4-H6 (if they turn out to be needed) and H7. *Acceptance: composed transducer's generate direction matches `generate()`/`yoruba()` for all 20,000 values, exact string match (already true as of H3 for everything except CDEL/COAL/ASSI/ELIS/TSAN, none of which are currently exercised by `generate()` -- see notes).*

- [ ] **H9 — Exhaustive validation.** Extend `validate_hfst.py` from range 60 to 20,000, and build the parse (surface -> integer) direction's test harness. Run full roundtrip (generate -> parse -> same integer) and inversion for all 20,000 values, all form classes. *Acceptance: 20,000/20,000 pass, both directions, all form classes -- no sampling. (Generate-direction parity is already exhaustively validated as of H3; what's outstanding here is specifically the parse direction, which hasn't been started.)*

- [ ] **H10 — Optimize & integrate.** Minimize the transducer, convert to optimized-lookup format, expose via `hfst-lookup` CLI and/or language bindings. Retire the heuristic trie/skeleton Python parser in favor of the inverted FST. *Acceptance: lookup latency benchmarked; parser retirement doesn't regress any H9 test.*

- [ ] **H11 — (Stretch, not scheduled) Full autosegmental tone tier.** Replace the flat-diacritic downstep heuristic with a proper tonal-tier model (Goldsmith/Pulleyblank). Out of scope until H0-H10 are stable; listed here so it isn't forgotten.
