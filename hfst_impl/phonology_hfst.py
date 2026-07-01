"""phonology_hfst.py -- Compiled phonological rules, REAL HFST (Option B, H2/H3)
==================================================================================
Yoruba Vigesimal Numeral System -- HFST reimplementation

This replaces phonology.py's Pynini backend with the literal Helsinki
Finite-State Toolkit (hfst >= 3.15, via the `hfst` Python bindings backed by
libhfst). Same rule set, same validated linguistic behaviour, same function
names/signatures as phonology.py -- pipeline.py and surface.py can be
repointed at this module with no other changes.

Requires setup_hfst.sh to have been sourced first (sets PATH,
LD_LIBRARY_PATH, PYTHONPATH so `import hfst` resolves to the real libhfst,
not a stub). See that script for why this is a per-session setup step
rather than a one-time install.

Unlike the Pynini version, NO byte-remapping workaround is needed here --
real HFST's regex/transducer-construction API handles arbitrary Unicode
(including our NFD combining marks) natively. Strings are NFD-normalised
before being fed to any rule (consistent with the design doc's alphabet
decision) and NFC-normalised on the way out; that's the only encoding
bookkeeping required.

Rule-construction pattern used throughout: build the mapping as a list of
(input_transducer, output_transducer) pairs and the context as a list of
(left_transducer, right_transducer) pairs, then
`hfst.xerox_rules.Rule(mapping_pairs, context_pairs, ReplaceType.REPL_UP)`
followed by `hfst.xerox_rules.replace(rule, False)`. This mirrors
Pynini's `cdrewrite(tau, left, right, sigma_star)` but does not need an
explicit sigma_star alphabet -- unlike Pynini's cdrewrite, HFST's replace
operator handles "elsewhere identity" without it, which is one fewer thing
to get wrong per rule (Pynini's version needed a hand-built alphabet for
every single rule; forgetting a character there was a real bug we hit).
"""

from __future__ import annotations

import sys
import json
import unicodedata
from pathlib import Path

import hfst
from hfst import xerox_rules as xr

sys.path.insert(0, str(Path(__file__).parent / "reference"))
import phase4 as _oracle  # noqa: E402  (only for the two verified helpers used
                           # to bootstrap build-time tables -- see module note
                           # in phonology.py; same policy here)

HERE = Path(__file__).parent
with open(HERE / "lexicon.json", encoding="utf-8") as _f:
    _LEXICON = json.load(_f)

NFD = lambda s: unicodedata.normalize("NFD", s)  # noqa: E731
NFC = lambda s: unicodedata.normalize("NFC", s)  # noqa: E731


def _lookup(transducer: "hfst.HfstTransducer", text: str) -> str:
    """NFD-normalise, look up, take the best (lowest-weight) result, strip
    the epsilon-symbol artifact HFST's lookup leaves in text output, and
    NFC-normalise the result. Every rule function below is a thin wrapper
    around this."""
    results = transducer.lookup(NFD(text))
    if not results:
        raise ValueError(f"no lookup result for {text!r} (transducer rejected input)")
    best = min(results, key=lambda r: r[1])
    return NFC(best[0].replace(hfst.EPSILON, ""))


def _optimize(t: "hfst.HfstTransducer") -> "hfst.HfstTransducer":
    """Convert to optimized-lookup format. Lookup on the default (OpenFst
    tropical) format goes through composition every call and measured
    ~1,450 lookups/sec; OLW format measured ~27,000/sec in the same test --
    an ~18x difference that matters a great deal over a 20,000-value
    exhaustive validation sweep. Every rule transducer in this module is
    optimized before use for this reason."""
    t.convert(hfst.ImplementationType.HFST_OLW_TYPE)
    return t


def _context_free_rule(pairs: list[tuple[str, str]]) -> "hfst.HfstTransducer":
    """A rule that fires anywhere in the string, no context restriction --
    the real-HFST equivalent of Pynini's cdrewrite(tau, "", "", sigma_star).
    """
    mapping_pairs = [(hfst.fst(NFD(a)), hfst.fst(NFD(b))) for a, b in pairs]
    empty = hfst.epsilon_fst()
    rule = xr.Rule(mapping_pairs, [(empty, empty)], xr.ReplaceType.REPL_UP)
    return _optimize(xr.replace(rule, False))


# ---------------------------------------------------------------------------
# H2a -- DNAS (simplified / Phase-B-equivalent): unconditional " ni " -> " l "
# ---------------------------------------------------------------------------

_DNAS_SIMPLE_RULE = _context_free_rule([(" ní ", " l ")])


def apply_dnas_simple(text: str) -> str:
    return _lookup(_DNAS_SIMPLE_RULE, text)


# ---------------------------------------------------------------------------
# H2b -- CLIP_11_14 (narrow, table-compiled). Covers cardinal, adjective,
# and numismatic units 1-4 (12 entries) -- ordinal is deliberately excluded,
# matching phase4.generate()/surface(), which don't clip ordinal 11-14 either.
# ---------------------------------------------------------------------------

def _build_clip_11_14_table() -> dict[str, str]:
    table: dict[str, str] = {}
    tables_by_fc = {
        "adjective": _LEXICON["adjective"],
        "numismatic": _LEXICON["numismatic"],
        "cardinal": {str(u): _LEXICON["anchors"][str(u)]["surface"] for u in range(1, 5)},
    }
    for fc, tbl in tables_by_fc.items():
        for unit in range(1, 5):
            unit_form = tbl[str(unit)]
            downstepped = _oracle._downstep_final_vowel(unit_form)
            table[unit_form] = NFC(downstepped + "lá")
    return table


_CLIP_11_14_TABLE = _build_clip_11_14_table()
_CLIP_11_14_RULE = _context_free_rule(list(_CLIP_11_14_TABLE.items()))


def apply_clip_11_14(unit_form: str) -> str:
    return _lookup(_CLIP_11_14_RULE, unit_form)


# ---------------------------------------------------------------------------
# H3a -- General downstep. Productive rule (vowel classes), not a table --
# fires on any word-final vowel immediately before an operator.
# ---------------------------------------------------------------------------

_GRAVE, _ACUTE, _DOT = NFD("̀"), NFD("́"), NFD("̣")
_BARE_VOWELS = ["a", "e", "e" + _DOT, "i", "o", "o" + _DOT, "u"]
_CONSONANTS = "bdfgjklmnrstw"
_OP_WORDS = ("dín", "lé")


def _op_right_context() -> "hfst.HfstTransducer":
    cons_union = hfst.empty_fst()
    for c in _CONSONANTS:
        cons_union.disjunct(hfst.fst(c))
    cons_union.minimize()
    cons_opt = hfst.HfstTransducer(cons_union)
    cons_opt.optionalize()

    op_union = hfst.fst(NFD(_OP_WORDS[0]))
    for w in _OP_WORDS[1:]:
        op_union.disjunct(hfst.fst(NFD(w)))
    op_union.minimize()

    ctx = hfst.HfstTransducer(cons_opt)
    ctx.concatenate(hfst.fst(" "))
    ctx.concatenate(op_union)
    ctx.concatenate(hfst.fst(" "))
    return ctx


def _build_downstep_rule() -> "hfst.HfstTransducer":
    mapping_pairs = []
    for v in _BARE_VOWELS:
        mapping_pairs.append((hfst.fst(v), hfst.fst(v + _GRAVE)))
        mapping_pairs.append((hfst.fst(v + _ACUTE), hfst.fst(v + _GRAVE)))
    empty_left = hfst.epsilon_fst()
    context_pairs = [(empty_left, _op_right_context())]
    rule = xr.Rule(mapping_pairs, context_pairs, xr.ReplaceType.REPL_UP)
    return _optimize(xr.replace(rule, False))


_DOWNSTEP_RULE = _build_downstep_rule()


def apply_downstep(text: str) -> str:
    return _lookup(_DOWNSTEP_RULE, text)


# ---------------------------------------------------------------------------
# H3b -- Suffix truncation. Deletes a word-final "-Vn" (grave V) suffix
# immediately before an operator.
# ---------------------------------------------------------------------------

def _build_truncation_rule() -> "hfst.HfstTransducer":
    op_union = hfst.fst(NFD(_OP_WORDS[0]))
    for w in _OP_WORDS[1:]:
        op_union.disjunct(hfst.fst(NFD(w)))
    op_union.minimize()
    right_ctx = hfst.HfstTransducer(hfst.fst(" "))
    right_ctx.concatenate(op_union)
    right_ctx.concatenate(hfst.fst(" "))

    mapping_pairs = []
    for v in _BARE_VOWELS:
        lhs = "-" + v + _GRAVE + "n"
        mapping_pairs.append((hfst.fst(lhs), hfst.epsilon_fst()))
    empty_left = hfst.epsilon_fst()
    rule = xr.Rule(mapping_pairs, [(empty_left, right_ctx)], xr.ReplaceType.REPL_UP)
    return _optimize(xr.replace(rule, False))


_TRUNCATION_RULE = _build_truncation_rule()


def apply_suffix_truncation(text: str) -> str:
    return _lookup(_TRUNCATION_RULE, text)


# ---------------------------------------------------------------------------
# H3c -- Full DNAS (H-spreading). Complete 65-entry table: " ni <anchor>"
# -> " l<H-spread(anchor)>". Complete, not narrow -- the anchor set on the
# right-hand side of every compound in this grammar is closed at 65.
# ---------------------------------------------------------------------------

def _build_dnas_full_pairs() -> list[tuple[str, str]]:
    pairs = []
    for info in _LEXICON["anchors"].values():
        surf = info["surface"]
        spread = _oracle._spread_h_to_initial(surf)
        pairs.append((" ní " + surf, " l" + spread))
    return pairs


_DNAS_FULL_RULE = _context_free_rule(_build_dnas_full_pairs())


def apply_dnas_full(text: str) -> str:
    return _lookup(_DNAS_FULL_RULE, text)
