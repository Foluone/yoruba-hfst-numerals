# Yoruba Vigesimal Numeral System — HFST Reimplementation

A compiled finite-state transducer for Yoruba numeral morphology (cardinal, adjective, ordinal, numismatic forms), covering the full 1–20,000 range. Built to replace an earlier Python-only reference implementation (`hfst_impl/reference/phase4.py`) with a genuinely compiled, machine-verifiable finite-state artifact, per [`DESIGN.md`](DESIGN.md).

This README lives at the repo root; all code is under `hfst_impl/`.

## Status

H0–H3 complete and exhaustively validated (every value in 1–20,000, all 4 form classes — no sampling). See `hfst_impl/IMPLEMENTATION_NOTES.md` for the full account, including two independently-built backends that agree exactly with each other and with the Python reference.

Outstanding: CDEL/COAL/ASSI (blocked on a dead-code question — they're defined in the reference but never actually called by anything), ELIS/TSAN (the `mú`-prefix tonal sandhi context), a formal autosegmental tone specification, and the parse (surface text → integer) direction. All tracked as milestones H4+ in `DESIGN.md`.

## Two backends, same validated behavior

This repo intentionally contains **two** independent implementations of the same rule set, kept side by side rather than one replacing the other:

- **Pynini backend** (`arithmetic.py`, `phonology.py`, `pipeline.py`, `surface.py`, `validate.py`) — OpenFST-based, installs cleanly via pip, fast to iterate on. Built first; kept as a reference/fallback.
- **Real HFST backend** (`arithmetic_hfst.py`, `phonology_hfst.py`, `pipeline_hfst.py`, `surface_hfst.py`, `validate_hfst.py`) — the literal Helsinki Finite-State Toolkit. Built second, once the toolkit was confirmed obtainable without root (see Setup below). This is the one that satisfies a literal "compiled with HFST" requirement.

Both pass the identical exhaustive validation suite with identical results. This cross-validation — two different underlying libraries agreeing on every one of 80,000+ generation cases and 20,000+ surface-fusion cases — is itself part of the correctness evidence for this project, not just a migration artifact.

## Architecture (Option B)

The numeral arithmetic (which anchor a number decomposes against, add vs. subtract, recursive multi-level decomposition for numbers like 2,453) stays as a thin, deterministic Python layer (`arithmetic.py` / `arithmetic_hfst.py`). Only the *phonological realization* — tone downstep, consonant/vowel contraction (DNAS), clipping (11–14), suffix truncation — is a genuinely compiled transducer. This split is documented and justified in `DESIGN.md` §2; the short version is that it's dramatically easier to build and validate incrementally than encoding the arithmetic itself as a recursive lexc grammar (Option A), which remains a possible future consolidation but was deliberately not pursued yet.

The lexicon (65 numeral anchors + 4 paradigm tables) has been decoupled from the Python reference into `lexicon.json`, which is now the source of truth for anything downstream. `phase4.py` remains a dependency only for two verified helper functions used to bootstrap build-time tables, and as the oracle that `validate.py`/`validate_hfst.py` check against.

## Setup

### Pynini backend
```
pip install pynini
```

### Real HFST backend
No `apt` root access is assumed. `setup_hfst.sh` fetches the toolkit without it:
```
source hfst_impl/setup_hfst.sh
```
This must be **sourced** (not just executed) so the `PATH`/`LD_LIBRARY_PATH`/`PYTHONPATH` exports reach your shell. It downloads and locally unpacks the `hfst`, `libhfst53`, and `python3-hfst` `.deb` packages into `/tmp/hfst_local` (idempotent — safe to re-run, skips work if already present). This directory does not persist across fresh environments/containers, so re-run this at the start of any new session before using the real-HFST files.

The compiled lexicon binary (`lexicon.hfst`) is a build artifact, not checked into this repo — regenerate it with:
```
hfst-lexc hfst_impl/lexicon.lexc -o hfst_impl/lexicon.hfst
```

## Running validation

```
cd hfst_impl
python3 validate.py                 # Pynini backend, full exhaustive suite
source setup_hfst.sh
python3 validate_hfst.py h1         # real-HFST backend, run one check at a time
python3 validate_hfst.py h2
python3 validate_hfst.py h3shallow
python3 validate_hfst.py h3deep --start 1 --end 5000   # chunked; see IMPLEMENTATION_NOTES.md
```

Every check is exhaustive over the full domain (the whole point of a 1–20,000-bounded problem is that you don't have to sample), and reports exact pass counts rather than percentages.

## Directory layout

```
DESIGN.md                     -- architecture, rule inventory, milestone tracker
hfst_impl/
  reference/phase4.py         -- original Python oracle (unmodified, read-only dependency)
  lexicon.json                -- canonical lexicon data, extracted from phase4.py
  extract_lexicon.py          -- the extraction script (re-run if phase4.py's lexicon changes)
  build_lexicon_lexc.py       -- generates lexicon.lexc from lexicon.json
  lexicon.lexc                -- the tagged lexc source (compile with hfst-lexc)
  setup_hfst.sh                -- fetches the real HFST toolkit without root
  arithmetic.py / arithmetic_hfst.py       -- H1: recursive decomposition (Pynini / real HFST)
  phonology.py / phonology_hfst.py         -- H2/H3: compiled phonological rules
  pipeline.py / pipeline_hfst.py           -- thin wiring, exposes generate()/yoruba_extended()
  surface.py / surface_hfst.py             -- H3: recursive everyday-surface-form fusion
  validate.py / validate_hfst.py           -- exhaustive acceptance tests
  IMPLEMENTATION_NOTES.md      -- detailed build log: findings, bugs caught and fixed, gotchas
```

## Known gotchas (see IMPLEMENTATION_NOTES.md for full detail)

- Pynini's `token_type="utf8"` silently corrupts `cdrewrite` output on non-ASCII symbols in this environment (pynini 2.1.7) — the Pynini backend works around this with a byte-remapping encode/decode layer. Not needed for the real HFST backend, which handles Unicode natively.
- Real HFST's `hfst.regex()` string DSL treats quoted multi-character strings as one atomic symbol rather than a character sequence — rules are built programmatically (`hfst.fst()`, `.disjunct()`, `hfst.xerox_rules.Rule`/`replace`) instead, which is more reliable.
- Real HFST transducers built via `xerox_rules.replace()` default to a lookup-via-composition format (~1,450 lookups/sec measured); converting to optimized-lookup format (`HFST_OLW_TYPE`) gives roughly an 18x speedup and is applied to every rule in `phonology_hfst.py`.
