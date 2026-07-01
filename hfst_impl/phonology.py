"""phonology.py — Compiled phonological rules (Option B, H2)
=============================================================
Yoruba Vigesimal Numeral System — HFST reimplementation

This module holds the only pieces of the system that are allowed to touch
phonology. Per the design doc's Option B split: arithmetic.py decides *what*
morphemes compose (pure Python, no phonology); everything here decides how
they surface, and every rule is a genuine compiled finite-state transducer
built with Pynini (composition/union/cross-product of string relations) --
not an imperative rewrite in Python control flow.

Encoding note (important, and non-obvious)
-------------------------------------------
Building these rules with Pynini's token_type="utf8" produced silently
corrupted output under `cdrewrite` in this environment (pynini 2.1.7) --
non-ASCII-derived symbols simply failed to be replaced, and in some
configurations the decoded output was garbage. This was verified with
minimal repro cases (see project notes) and traced to the interaction
between per-call auto-built utf8 symbol tables and cdrewrite's internal
marker-symbol allocation, not to anything specific to Yoruba text.

The whole numeral system (all 20,000 values x 4 form classes) only ever
uses 23 distinct NFD codepoints: 20 plain ASCII letters/space/hyphen, plus
three combining marks (grave U+0300, acute U+0301, dot-below U+0323).
Rather than fight the utf8 token type, this module remaps those three
combining marks onto three unused byte values (0x80-0x82) and does all FST
construction in Pynini's default ("byte") token type, which is the
best-tested code path in the library. `encode`/`decode` do the remapping;
every rule below operates on encoded strings, and callers should only see
real Unicode in and out.
"""

from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

import pynini
from pynini.lib import rewrite

sys.path.insert(0, str(Path(__file__).parent / "reference"))
import phase4 as _oracle  # noqa: E402  (reference lexicon + verified helpers)

# ---------------------------------------------------------------------------
# Encoding layer (byte-safe stand-in for the project's 23-codepoint alphabet)
# ---------------------------------------------------------------------------

_MARK_TO_BYTE: dict[int, int] = {
    0x0300: 0x80,  # combining grave accent
    0x0301: 0x81,  # combining acute accent
    0x0323: 0x82,  # combining dot below
}
_BYTE_TO_MARK: dict[int, str] = {v: chr(k) for k, v in _MARK_TO_BYTE.items()}


def encode(s: str) -> str:
    """NFD-normalise *s* and remap its three combining marks onto private
    byte code points so the string can be fed to a byte-mode Pynini FST."""
    out = []
    for ch in unicodedata.normalize("NFD", s):
        cp = ord(ch)
        out.append(chr(_MARK_TO_BYTE[cp]) if cp in _MARK_TO_BYTE else ch)
    return "".join(out)


def decode(s: str) -> str:
    """Reverse of encode(): restore combining marks and NFC-normalise."""
    out = []
    for ch in s:
        cp = ord(ch)
        out.append(_BYTE_TO_MARK.get(cp, ch))
    return unicodedata.normalize("NFC", "".join(out))


def _sigma_star(strings: list[str]) -> "pynini.Fst":
    """Closure over every (encoded) character appearing in *strings*."""
    chars = sorted({c for s in strings for c in s})
    sigma = pynini.union(*[pynini.accep(c) for c in chars])
    return sigma.closure()


# ---------------------------------------------------------------------------
# H2a -- DNAS (simplified / Phase-B-equivalent)
#
# This is the *general* rule: an unconditional, length-changing substitution
# of the linker token " ní " with the standalone token " l ", exactly
# matching the semantics of the already-validated build/dnas-rewrite.hfst
# (see phase4.yoruba(), which does the same thing with Python's str.replace
# for n in 1-60). This version is a real compiled FST and is not bounded to
# 1-60: it is context-general and applies correctly no matter how many
# " ní " tokens appear in a skeleton string, which matters once numbers
# need 2-3 levels of nested compounding (see design doc, Known Gaps).
#
# Note this is deliberately the *simplified* DNAS (no H-tone spreading onto
# the following vowel) so that it can be checked, unmodified, against the
# existing oracle. The fuller DNAS with H-spreading (phase4.apply_dnas) is
# only exercised by the narrow CLIP_11_14 table below and is not yet a
# general rule -- see IMPLEMENTATION_NOTES.md for what's deferred.
# ---------------------------------------------------------------------------

_DNAS_LHS = encode(" ní ")
_DNAS_RHS = encode(" l ")
_DNAS_ALPHABET = [
    encode(v["surface"]) for v in _oracle.ANCHORS.values()
] + [encode(v) for v in _oracle._ADJECTIVE.values()] \
  + [encode(v) for v in _oracle._ORDINAL.values()] \
  + [encode(v) for v in _oracle._NUMISMATIC.values()] \
  + [_DNAS_LHS, _DNAS_RHS, encode(" dín "), encode(" lé ")]

_DNAS_SIMPLE_RULE = pynini.cdrewrite(
    pynini.cross(_DNAS_LHS, _DNAS_RHS),
    "", "",
    _sigma_star(_DNAS_ALPHABET),
).optimize()


def apply_dnas_simple(text: str) -> str:
    """Generalised, full-range equivalent of phase4.yoruba()'s ' ní '->' l '
    substitution. Exact match with phase4.yoruba() for n in 1-60 is the H2
    regression test; this function is what extends that behaviour past 60."""
    enc = encode(text)
    out = rewrite.top_rewrite(enc, _DNAS_SIMPLE_RULE)
    return decode(out)


# ---------------------------------------------------------------------------
# H2b -- CLIP_11_14 (narrow, table-compiled -- NOT a general rule yet)
#
# generate(n, "adjective"|"numismatic") for n in 11-14 is the one place the
# *current* Python reference already bakes phonology (downstep + full DNAS
# with H-spread + CLIP) directly into generate() itself, collapsing
# "<unit> lé ní ẹ̀wàá" down to "<downstepped-unit>lá". Only 8 input strings
# are possible (units 1-4, x2 form classes), so this is compiled as an
# 8-entry finite lookup transducer (built once from phase4's own verified
# `_downstep_final_vowel`, not re-derived) rather than a productive
# cdrewrite rule. It is a real FST (a lookup table is a valid finite-state
# transducer), but it is intentionally narrow: generalising downstep into a
# rule that works for *any* compound boundary is H3+ work, tracked in
# IMPLEMENTATION_NOTES.md, and is needed anyway once the general surface()
# fusion pipeline (not just this branch) is tackled.
# ---------------------------------------------------------------------------

def _build_clip_11_14_table() -> dict[str, str]:
    table: dict[str, str] = {}
    tables_by_fc = {
        "adjective": _oracle._ADJECTIVE,
        "numismatic": _oracle._NUMISMATIC,
        "cardinal": {u: _oracle.ANCHORS[u]["surface"] for u in range(1, 5)},
    }
    for fc, tbl in tables_by_fc.items():
        for unit in range(1, 5):
            unit_form = tbl[unit]
            downstepped = _oracle._downstep_final_vowel(unit_form)
            table[unit_form] = unicodedata.normalize("NFC", downstepped + "lá")
    return table


_CLIP_11_14_TABLE = _build_clip_11_14_table()
_CLIP_11_14_FST = pynini.string_map(
    [(encode(k), encode(v)) for k, v in _CLIP_11_14_TABLE.items()]
).optimize()


def apply_clip_11_14(unit_form: str) -> str:
    """unit_form must be one of the 8 known adjective/numismatic forms for
    units 1-4 (i.e. exactly phase4._ADJECTIVE[1..4] or _NUMISMATIC[1..4]).
    Returns the downstepped+clipped fused form, e.g. 'mọ́kan' -> 'mọ́kànlá'."""
    enc = encode(unit_form)
    out = rewrite.top_rewrite(enc, _CLIP_11_14_FST)
    return decode(out)


# ---------------------------------------------------------------------------
# H3 -- General downstep, suffix truncation, and full (H-spreading) DNAS.
#
# These three, composed, generalise phase4.surface()'s fusion logic to
# EVERY compound boundary recursively, not just the outermost one. Of the
# 20,000 values in range, only 1,856 (pure anchors plus single-level
# compounds) have just one boundary; the other 18,144 (90.7%) need 2-3
# levels of nested compounding, and phase4.surface() only ever downsteps
# the outermost unit. See IMPLEMENTATION_NOTES.md for the measurement.
# surface.py calls these once per recursion level.
#
# Unlike CLIP_11_14 (table-compiled over a small closed set of left-hand
# inputs), these are genuine productive cdrewrite rules stated over
# vowel/consonant classes, so they apply to any unit surface form the
# recursion produces.
# ---------------------------------------------------------------------------

_GRAVE, _ACUTE, _DOT = encode("̀"), encode("́"), encode("̣")
_VOWELS = "aeiou"
_DOTTED_VOWELS = "eo"  # vowels that may additionally carry a dot-below (ẹ, ọ)
_CONSONANTS = "bdfgjklmnrstw"
_OP_WORDS = ("dín", "lé")


def _bare_vowel_syllables():
    out = []
    for v in _VOWELS:
        out.append(v)
        if v in _DOTTED_VOWELS:
            out.append(v + _DOT)
    return out


def _op_right_context():
    cons_union = pynini.union(*[pynini.accep(c) for c in _CONSONANTS])
    op_union = pynini.union(*[pynini.accep(encode(w)) for w in _OP_WORDS])
    return cons_union.ques + pynini.accep(" ") + op_union + pynini.accep(" ")


def _build_downstep_rule():
    pairs = []
    for syll in _bare_vowel_syllables():
        pairs.append((syll, syll + _GRAVE))
        pairs.append((syll + _ACUTE, syll + _GRAVE))
    tau = pynini.union(*[pynini.cross(a, b) for a, b in pairs])
    alphabet = list("abcdefghijklmnopqrstuvwxyz -") + [_GRAVE, _ACUTE, _DOT]
    sigma_star = _sigma_star(alphabet)
    return pynini.cdrewrite(tau, "", _op_right_context(), sigma_star).optimize()


def _build_truncation_rule():
    right_ctx = pynini.accep(" ") + pynini.union(
        *[pynini.accep(encode(w)) for w in _OP_WORDS]
    ) + pynini.accep(" ")
    vowels = _bare_vowel_syllables()
    tau = pynini.union(*[
        pynini.cross(encode("-") + v + _GRAVE + "n", "") for v in vowels
    ])
    alphabet = list("abcdefghijklmnopqrstuvwxyz -") + [_GRAVE, _ACUTE, _DOT]
    sigma_star = _sigma_star(alphabet)
    return pynini.cdrewrite(tau, "", right_ctx, sigma_star).optimize()


def _build_dnas_full_rule():
    # sigma_star must cover the FULL project alphabet, not just the
    # characters appearing in the 65 anchor forms -- cdrewrite needs every
    # symbol that could appear anywhere in the input (e.g. the preceding
    # unit morpheme's letters), not just the ones local to this rule's own
    # lhs/rhs. Building sigma_star from only the anchors' own characters
    # was a real bug (composition failure on any unit starting with a
    # letter no anchor happens to use, e.g. "m" in adjective forms).
    pairs = []
    for anchor in _oracle.ANCHORS.values():
        surf = anchor["surface"]
        spread = _oracle._spread_h_to_initial(surf)
        lhs = encode(" ní " + surf)
        rhs = encode(" l" + spread)
        pairs.append((lhs, rhs))
    tau = pynini.union(*[pynini.cross(a, b) for a, b in pairs])
    alphabet = list("abcdefghijklmnopqrstuvwxyz -") + [_GRAVE, _ACUTE, _DOT]
    sigma_star = _sigma_star(alphabet)
    return pynini.cdrewrite(tau, "", "", sigma_star).optimize()


_DOWNSTEP_RULE = _build_downstep_rule()
_TRUNCATION_RULE = _build_truncation_rule()
_DNAS_FULL_RULE = _build_dnas_full_rule()


def apply_downstep(text: str) -> str:
    return decode(rewrite.top_rewrite(encode(text), _DOWNSTEP_RULE))


def apply_suffix_truncation(text: str) -> str:
    return decode(rewrite.top_rewrite(encode(text), _TRUNCATION_RULE))


def apply_dnas_full(text: str) -> str:
    return decode(rewrite.top_rewrite(encode(text), _DNAS_FULL_RULE))
