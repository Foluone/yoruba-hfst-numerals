#!/usr/bin/env python3
"""
phase4.py — Canonical reference implementation
===============================================
Morphology-Aware Machine Translation Project
Yoruba Vigesimal Numeral System — Bidirectional Morphological Analyser

This file is the single authoritative point of reference for the project,
reconciling the full Python implementation (M1–M14), all post-milestone fixes
(A1–A4), and the Phase B HFST oracle (yoruba(), 1–60).

─────────────────────────────────────────────────────────────────────────────
Python milestones (M1–M14) — complete across 1–20,000
─────────────────────────────────────────────────────────────────────────────
    M1  — Tone encoding utilities (NFC/NFD, vowel/tone helpers)
    M3  — Anchor lexicon (65 entries) + Phase 1 API
    M4  — DNAS rule (both directions)
    M5  — CDEL rule (both directions)
    M6  — COAL + HARM rules (both directions)
    M7  — ASSI rule (both directions)
    M8  — CLIP rule (both directions)
    M9  — ELIS rule (both directions); bound form for anchor-10 added
    M10 — Tonal Synthesiser (TSAN); parse direction implemented (A1 fix)
    M11 — Trie Resolver + Phonological Normaliser (incl. DNAS-contracted forms)
    M12 — FST Parser passes 1–3
    M13 — FST Parser pass 4 (recursion; A3 fix applied to _parse_anchor_right)
    M14 — Full API: generate, surface, derive, trace, decompose, range,
           getMorphemes, nearestAnchors; roundtrip / validate_range

Post-milestone fixes applied (session 2025-2026):
    A1  — apply_tsan() parse direction (was NotYetImplemented)
    A2  — generate() propagates form_class to unit morpheme in all compounds
    A3  — _parse_anchor_right() recursive fallback for depth-2 compounds
    A4  — Added trace(), decompose(), derive(), range() API functions
    B1  — JS anchor type vocabulary: multiply->multiplicative, subtract->subtractive
    B2  — Anchor 300 reclassified primitive->subtractive in JS files
    B3  — Anchor 18000 surface form corrected to ẹgbàásàn-án in JS files
    C1  — Five new subtractive anchors added (11000-19000); assert 60->65
    D1  — surface() function added: downstep + DNAS + fusion for display

─────────────────────────────────────────────────────────────────────────────
Phase B HFST pipeline — compiled, validated for 1–60
─────────────────────────────────────────────────────────────────────────────
    Files:   src/lexicon.lexc, src/rules.twolc, src/build_dnas.py,
             src/compose_fst.py, Makefile, validate_hfst.py
    Output:  build/yoruba-numerals-final.hfst
    Pipeline: lexicon.lexc ∘ rules.twolc ∘ dnas-rewrite.hfst → final FST
    Validated: 60/60 roundtrip, 60/60 inversion, DNAS smoke tests (all pass)

    The yoruba(n) function at the bottom of this file is the Python oracle
    used by validate_hfst.py.  It derives directly from generate() and is
    therefore always consistent with the anchor lexicon defined here.

─────────────────────────────────────────────────────────────────────────────
Known gaps
─────────────────────────────────────────────────────────────────────────────
    HFST scope      — Phase B covers 1–60 only.  Extending the lexc/twolc
                      pipeline to the full 1–20,000 range requires additional
                      lexicon entries and recursive composition rules not yet
                      implemented.  See REQUIREMENTS.md.

    twolc rules     — COAL, ELIS, TSAN, HARM, CDEL, CLIP are implemented in
                      Python (M4–M9 below) but not yet compiled into
                      rules.twolc.  The current twolc contains only ASSI (M7),
                      which is vacuous for 1–60.  DNAS is handled via a
                      separate xfst rewrite transducer (build_dnas.py) because
                      the ní→l substitution is length-changing and cannot be
                      expressed as a two-level rule.

    Surface/underlying — morpheme objects carry identical surface and
                      underlying field values.  The two-level distinction
                      is implemented in the rule functions but not yet
                      reflected in the data structures returned by
                      getMorphemes().

    Tonal synthesiser — _apply_downstep() is a heuristic that fills
                      toneless vowel slots after a high.  The adjective
                      forms for 1–10 are still retrieved from the oracle
                      table (_ADJECTIVE) rather than computed by the
                      synthesiser.  Full autosegmental tier machinery
                      (Goldsmith 1976; Pulleyblank 1986) is not yet
                      implemented.

    OT ranker       — Rule interactions (COAL×HARM, ELIS×TSAN, CLIP×CDEL,
                      ASSI×COAL) are resolved by hardcoded precedence in the
                      rule functions, not by a formal Optimality Theory
                      evaluation module.

─────────────────────────────────────────────────────────────────────────────
Test status
─────────────────────────────────────────────────────────────────────────────
    Python:  20000 / 20000 roundtrip passing (generate->parse, full range).
             Remaining gaps documented in docs/phase4_assessment_guide.md.
    HFST:    60/60 roundtrip and inversion (Phase B, range 1–60).

─────────────────────────────────────────────────────────────────────────────
Tonal authority — anchor 9
─────────────────────────────────────────────────────────────────────────────
    Canonical form:  ẹ̀sán  (acute on a, U+0301)
    Earlier HFST oracle drafts (phase4(1).py) erroneously used ẹ̀sàn (grave).
    The _ANCHOR_RAW entry below is authoritative.  The yoruba() oracle at the
    bottom of this file derives from generate() and is therefore always
    consistent with this lexicon.

─────────────────────────────────────────────────────────────────────────────
Surface form conventions
─────────────────────────────────────────────────────────────────────────────
    generate()  — returns the canonical pre-DNAS cardinal form, e.g.
                  "ẹ̀ta dín ní ogún" for 17.  The linker is spelled "ní"
                  and remains un-contracted.  This is the linguistically
                  transparent representation and the input to apply_dnas().

    yoruba()    — returns the HFST-compatible post-DNAS surface form, e.g.
                  "ẹ̀ta dín l ogún" for 17.  The linker "ní" is replaced
                  by the standalone token "l" (with flanking spaces) to
                  match the output of the build/dnas-rewrite.hfst transducer.
                  This is the form validated by validate_hfst.py.
"""

from __future__ import annotations
import unicodedata
import bisect
import builtins          # needed so 'range' builtin survives our API function
from typing import Any


# ---------------------------------------------------------------------------
# Sentinel exception
# ---------------------------------------------------------------------------

class NotYetImplemented(Exception):
    """Raised by any stub that has not yet been implemented."""


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

MorphemeRecord   = dict[str, Any]
ParseResult      = dict[str, Any]
NormaliseResult  = dict[str, Any]
ValidationResult = dict[str, Any]


# ===========================================================================
# Milestone 1 — Tone encoding utilities
# ===========================================================================

def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)

def nfd(s: str) -> str:
    return unicodedata.normalize("NFD", s)

_ACUTE    = "\u0301"
_GRAVE    = "\u0300"
_MACRON   = "\u0304"
_UNDERDOT = "\u0323"

_OPEN_VOWELS  = set("ọẹ")
_CLOSE_VOWELS = set("oeiu")
_ALL_VOWELS   = set("aeiouọẹ")
_TONE_MARKS   = {_ACUTE, _GRAVE, _MACRON}


def get_tone(char: str) -> str | None:
    for cp in nfd(char):
        if cp in _TONE_MARKS:
            return cp
    return None

def strip_tone(char: str) -> str:
    return nfc("".join(cp for cp in nfd(char) if cp not in _TONE_MARKS))

def set_tone(char: str, tone: str) -> str:
    return nfc(strip_tone(char) + tone)

def initial_vowel(word: str) -> str | None:
    for ch in word:
        base = strip_tone(ch).lower()
        if base in _ALL_VOWELS:
            return ch
    return None

def is_mid_open(vowel: str) -> bool:
    return strip_tone(vowel).lower() in _OPEN_VOWELS

def is_mid_close(vowel: str) -> bool:
    return strip_tone(vowel).lower() in {"e", "o"}


# ===========================================================================
# Milestone 3 — Anchor lexicon (65 entries)
# Type breakdown: Primitive 15 · Multiplicative 24 · Subtractive 21
# Correction (v3): 300 (ọ̀ọ́dúnrún) reclassified Primitive → Subtractive
#   Derivation: 400 − 100.  Stored as anchor because the arithmetic
#   engine uses it as a reference point for values near 300.
# ===========================================================================
#
# Anchor 9 canonical form: ẹ̀sán (ACUTE on a).
# Earlier drafts of the HFST oracle used ẹ̀sàn (grave) in error.
# The entry below is authoritative across all form classes.

_ANCHOR_RAW: dict[int, tuple[str, str]] = {
    # Primitive (15)
    1:      ("ọ̀kan",           "primitive"),
    2:      ("èjì",             "primitive"),
    3:      ("ẹ̀ta",             "primitive"),
    4:      ("ẹ̀rin",            "primitive"),
    5:      ("àrún",            "primitive"),
    6:      ("ẹ̀fà",             "primitive"),
    7:      ("èje",             "primitive"),
    8:      ("ẹ̀jọ",             "primitive"),
    9:      ("ẹ̀sán",            "primitive"),   # acute on a — authoritative
    10:     ("ẹ̀wá",             "primitive"),
    20:     ("ogún",            "primitive"),
    30:     ("ọgbọ̀n",           "primitive"),
    200:    ("igba",            "primitive"),
    400:    ("irinwó",          "primitive"),
    2000:   ("ẹgbàá",           "primitive"),
    # 20-series multiplicative
    40:     ("ogójì",           "multiplicative"),
    60:     ("ọgọ́ta",           "multiplicative"),
    80:     ("ọgọ́rin",          "multiplicative"),
    100:    ("ọgọ́rùn-ún",      "multiplicative"),
    120:    ("ọgọ́fà",           "multiplicative"),
    140:    ("ogóje",           "multiplicative"),
    160:    ("ọgọ́jọ",           "multiplicative"),
    180:    ("ọgọ́sàn-án",       "multiplicative"),
    # 20-series subtractive
    50:     ("àádọ́ta",          "subtractive"),
    70:     ("àádọ́rin",         "subtractive"),
    90:     ("àádọ́rùn-ún",     "subtractive"),
    110:    ("àádọ́fà",          "subtractive"),
    130:    ("àádọ́je",          "subtractive"),
    150:    ("àádọ́jọ",          "subtractive"),
    170:    ("àádọ́sàn-án",      "subtractive"),
    190:    ("àádọ́wàá",         "subtractive"),
    # igba-series multiplicative
    600:    ("ẹgbẹ̀ta",          "multiplicative"),
    800:    ("ẹgbẹ̀rin",         "multiplicative"),
    1000:   ("ẹgbẹ̀rún",         "multiplicative"),
    1200:   ("ẹgbẹ̀fà",          "multiplicative"),
    1400:   ("egbèje",          "multiplicative"),
    1600:   ("ẹgbẹ̀jọ",          "multiplicative"),
    1800:   ("ẹgbẹ̀sán",         "multiplicative"),
    # igba-series subtractive (includes 300 = 400 − 100)
    300:    ("ọ̀ọ́dúnrún",       "subtractive"),  # 400 − 100
    500:    ("ẹ̀ẹ́dẹ́gbẹ̀ta",     "subtractive"),
    700:    ("ẹ̀ẹ́dẹ́gbẹ̀rin",    "subtractive"),
    900:    ("ẹ̀ẹ́dẹ́gbẹ̀rún",    "subtractive"),
    1100:   ("ẹ̀ẹ́dẹ́gbẹ̀fà",     "subtractive"),
    1300:   ("ẹ̀ẹ́dẹ́gbèje",      "subtractive"),
    1500:   ("ẹ̀ẹ́dẹ́gbẹ̀jọ",     "subtractive"),
    1700:   ("ẹ̀ẹ́dẹ́gbẹ̀sán",    "subtractive"),
    1900:   ("ẹ̀ẹ́dẹ́gbẹ̀wá",     "subtractive"),
    # ẹgbàá-series multiplicative
    4000:   ("ẹgbàájì",         "multiplicative"),
    6000:   ("ẹgbàáta",         "multiplicative"),
    8000:   ("ẹgbàárin",        "multiplicative"),
    10000:  ("ẹgbàárùn-ún",    "multiplicative"),
    12000:  ("ẹgbàáfà",         "multiplicative"),
    14000:  ("ẹgbàáje",         "multiplicative"),
    16000:  ("ẹgbàájọ",         "multiplicative"),
    18000:  ("ẹgbàásàn-án",     "multiplicative"),
    20000:  ("ẹgbàáwàá",        "multiplicative"),
    # ẹgbàá-series subtractive
    3000:   ("ẹ̀ẹ́dẹ́gbàájì",      "subtractive"),
    5000:   ("ẹ̀ẹ́dẹ́gbàáta",      "subtractive"),
    7000:   ("ẹ̀ẹ́dẹ́gbàárin",     "subtractive"),
    9000:   ("ẹ̀ẹ́dẹ́gbàárùn-ún",  "subtractive"),
    # ẹgbàá-series subtractive (newly attested, native speaker 2026)
    11000:  ("ẹ̀ẹ́dẹ́gbàáfà",      "subtractive"),   # 12000 − 1000
    13000:  ("ẹ̀ẹ́dẹ́gbàáje",      "subtractive"),   # 14000 − 1000
    15000:  ("ẹ̀ẹ́dẹ́gbàájọ",      "subtractive"),   # 16000 − 1000
    17000:  ("ẹ̀ẹ́dẹ́gbàásàn-án",  "subtractive"),   # 18000 − 1000
    19000:  ("ẹ̀ẹ́dẹ́gbàáwàá",     "subtractive"),   # 20000 − 1000
}

ANCHORS: dict[int, dict[str, str]] = {
    v: {"surface": nfc(s), "type": t, "underlying": nfc(s)}
    for v, (s, t) in _ANCHOR_RAW.items()
}

_ANCHOR_VALUES: list[int] = sorted(ANCHORS)
assert len(ANCHORS) == 65, f"Expected 65 anchors, got {len(ANCHORS)}"

# Oracle tables for form classes that cannot be derived mechanically.
# Anchor 9 adjective/ordinal/numismatic forms carry sàn-án (grave + suffix)
# while the cardinal carries sán (acute only) — these are distinct tonal
# realisations of the same root in different morphological environments.
_ADJECTIVE: dict[int, str] = {
    1: "mọ́kan",    2: "méjì",     3: "mẹ́ta",     4: "mẹ́rin",
    5: "márùn-ún",  6: "mẹ́fà",    7: "méje",     8: "mẹ́jọ",
    9: "mẹ́sàn-án", 10: "mẹ́wàá",
}
_ORDINAL: dict[int, str] = {
    1: "ìkínnì",     2: "ìkejì",     3: "ìkẹta",     4: "ìkẹrin",
    5: "ìkarùn-ún",  6: "ìkẹfà",    7: "ìkeje",     8: "ìkẹjọ",
    9: "ìkẹsàn-án",  10: "ìkẹwàá",
}
_NUMISMATIC: dict[int, str] = {
    1:  "oókan",     2:  "eéjì",     3:  "ẹẹ́ta",     4:  "ẹẹ́rin",
    5:  "aárùn-ún",  6:  "ẹẹ́fà",    7:  "eéje",     8:  "ẹẹ́jọ",
    9:  "ẹẹ́sàn-án", 10: "ẹẹ́wàá",   20: "okòó",
}
_ADJECTIVE   = {k: nfc(v) for k, v in _ADJECTIVE.items()}
_ORDINAL     = {k: nfc(v) for k, v in _ORDINAL.items()}
_NUMISMATIC  = {k: nfc(v) for k, v in _NUMISMATIC.items()}

# Compound (bound) forms — anchor surfaces that lengthen in compound context.
# Anchor 10 (ẹ̀wá) lengthens to ẹ̀wàá when it carries the operator syllable
# (lé ní) before DNAS contraction.  This produces the correct CLIP target
# lélẹ́wàá → lá for 11–14.  Evidence: _ADJECTIVE[10] = "mẹ́wàá" not "mẹ́wá".
_COMPOUND_ANCHOR_FORMS: dict[int, str] = {
    10: nfc("ẹ̀wàá"),
}


# ===========================================================================
# Milestone 3 — Phase 1 API
# ===========================================================================

def nearestAnchors(n: int) -> dict[str, Any]:
    if not (1 <= n <= 20000):
        raise ValueError(f"n={n} out of range [1, 20000]")
    if n in ANCHORS:
        return {"lower_anchor": n, "upper_anchor": n, "dist_lower": 0, "dist_upper": 0}
    pos   = bisect.bisect_left(_ANCHOR_VALUES, n)
    lower = _ANCHOR_VALUES[pos - 1]
    upper = _ANCHOR_VALUES[pos]
    return {"lower_anchor": lower, "upper_anchor": upper,
            "dist_lower": n - lower, "dist_upper": upper - n}


# ---------------------------------------------------------------------------
# Internal helper: downstep the final vowel of a word (used before CLIP).
# In 11–14 clipped forms the unit's final vowel takes a low (grave) tone
# before the clipped suffix lá is fused.  This also enables apply_clip's
# rìn→ìn substitution for 14 (mẹ́rin → mẹ́rìn → mẹ́ìnlá).
# ---------------------------------------------------------------------------

def _downstep_final_vowel(form: str) -> str:
    """Set the final vowel of *form* to low (grave) tone.  Returns NFC string."""
    nfd_f = list(nfd(form))
    i = len(nfd_f) - 1
    while i >= 0:
        if unicodedata.combining(nfd_f[i]):
            i -= 1
            continue
        base = nfd_f[i].lower()
        if base in _ALL_VOWELS:
            j = i + 1
            trailing_marks = []
            while j < len(nfd_f) and unicodedata.combining(nfd_f[j]):
                if nfd_f[j] not in _TONE_MARKS:
                    trailing_marks.append(nfd_f[j])
                j += 1
            rebuilt = nfd_f[:i+1] + trailing_marks + [_GRAVE] + nfd_f[j:]
            return nfc("".join(rebuilt))
        i -= 1
    return form


def generate(n: int, form_class: str = "cardinal") -> str:
    """Generate the Yoruba surface form of integer *n* in the given *form_class*.

    form_class: 'cardinal' (default) | 'adjective' | 'ordinal' | 'numismatic'

    Returns the pre-DNAS canonical form — the linker is spelled "ní" and
    remains un-contracted.  To obtain the HFST surface form (with standalone
    "l" in place of "ní"), call yoruba(n) or apply
    form.replace(" ní ", " l ") to the cardinal output.

    A2 fix: form_class is propagated to the unit morpheme in all compounds.
    """
    if not (1 <= n <= 20000):
        raise ValueError(f"n={n} out of range [1, 20000]")

    # ── Oracle table lookups (1–10, and numismatic 20) ──────────────────────
    if form_class == "adjective"   and n in _ADJECTIVE:   return _ADJECTIVE[n]
    if form_class == "ordinal"     and n in _ORDINAL:     return _ORDINAL[n]
    if form_class == "numismatic"  and n in _NUMISMATIC:  return _NUMISMATIC[n]

    # ── Pure anchors (cardinal surface, all form classes) ────────────────────
    if n in ANCHORS:
        return ANCHORS[n]["surface"]

    # ── CLIP path: 11–14 for adjective and numismatic ────────────────────────
    if form_class in ("adjective", "numismatic") and 11 <= n <= 14:
        unit         = n - 10
        unit_form    = generate(unit, form_class)
        unit_form_ds = _downstep_final_vowel(unit_form)
        anchor_bound = _COMPOUND_ANCHOR_FORMS[10]
        spaced       = f"{unit_form_ds} lé ní {anchor_bound}"
        dnas_form    = apply_dnas(spaced, direction="generate")
        try:
            clip_form = apply_clip(dnas_form, direction="generate")
            _LA = nfc("lá")
            return nfc(clip_form.replace(" " + _LA, _LA))
        except Exception:
            return spaced

    # ── General compound decomposition ──────────────────────────────────────
    # Returns the pre-DNAS canonical spaced form.  Call surface() to obtain
    # the everyday fused form (downstep + DNAS + space removal applied).
    info             = nearestAnchors(n)
    lower, upper     = info["lower_anchor"], info["upper_anchor"]
    dist_lo, dist_up = info["dist_lower"],   info["dist_upper"]

    if dist_up <= dist_lo:
        unit      = upper - n
        unit_form = generate(unit, form_class)
        return f"{unit_form} dín ní {generate(upper, 'cardinal')}"
    else:
        unit      = n - lower
        unit_form = generate(unit, form_class)
        return f"{unit_form} lé ní {generate(lower, 'cardinal')}"


def getMorphemes(n: int) -> list[MorphemeRecord]:
    if not (1 <= n <= 20000):
        raise ValueError(f"n={n} out of range [1, 20000]")
    if n in ANCHORS:
        anchor = ANCHORS[n]
        return [{"surface": anchor["surface"], "underlying": anchor["underlying"],
                 "role": "anchor", "value": n,
                 "rules": [], "rules_applied": [], "anchor_type": anchor["type"]}]
    info             = nearestAnchors(n)
    lower, upper     = info["lower_anchor"], info["upper_anchor"]
    dist_lo, dist_up = info["dist_lower"],   info["dist_upper"]
    if dist_up <= dist_lo:
        unit, anchor_v = upper - n, upper
        op_surface, op_underlying, op_role = "dín ní", "dín nί", "operator-subtract"
    else:
        unit, anchor_v = n - lower, lower
        op_surface, op_underlying, op_role = "lé ní", "lé nί", "operator-add"
    unit_morphemes = getMorphemes(unit)
    for m in unit_morphemes:
        if m["role"] == "anchor":
            m["role"]         = "unit"
            m["rules"]        = ["ELIS", "TSAN"]
            m["rules_applied"] = ["ELIS", "TSAN"]
    op_morpheme = {"surface": op_surface, "underlying": op_underlying,
                   "role": op_role, "value": None,
                   "rules": ["DNAS"], "rules_applied": ["DNAS"], "anchor_type": None}
    anchor_rec = ANCHORS[anchor_v]
    anchor_morpheme = {"surface": anchor_rec["surface"], "underlying": anchor_rec["underlying"],
                       "role": "anchor", "value": anchor_v,
                       "rules": [], "rules_applied": [], "anchor_type": anchor_rec["type"]}
    return unit_morphemes + [op_morpheme, anchor_morpheme]


# ===========================================================================
# Synthesise  (M9–M10)
# ===========================================================================

def _morphemes_to_int(morphemes: list[MorphemeRecord]) -> int:
    op_idx = next((i for i, m in enumerate(morphemes)
                   if m["role"] in ("operator-add", "operator-subtract")), None)
    if op_idx is None:
        return morphemes[0]["value"]
    unit_v   = next((m["value"] for m in morphemes[:op_idx]  if m["value"] is not None), 0)
    anchor_v = next((m["value"] for m in morphemes[op_idx+1:] if m["value"] is not None), 0)
    return anchor_v - unit_v if morphemes[op_idx]["role"] == "operator-subtract" \
           else anchor_v + unit_v


def synthesise(morphemes: list[MorphemeRecord], form_class: str = "cardinal") -> str:
    return generate(_morphemes_to_int(morphemes), form_class=form_class)


# ===========================================================================
# M4 — DNAS helpers + apply_dnas
# ===========================================================================

def _spread_h_to_initial(word: str) -> str:
    nfd_w  = nfd(word)
    result = []
    applied = False
    i = 0
    while i < len(nfd_w):
        ch   = nfd_w[i]
        base = ch.lower()
        if not applied and (base in _ALL_VOWELS):
            comb = []
            j = i + 1
            while j < len(nfd_w) and unicodedata.combining(nfd_w[j]):
                if nfd_w[j] not in _TONE_MARKS:
                    comb.append(nfd_w[j])
                j += 1
            # VV-onset guard: long-vowel syllables (àá-, ẹ̀ẹ́-, ọ̀ọ́-…) carry a
            # lexically-specified tone on their first mora.  H-spreading from
            # DNAS contraction does not overwrite it — the linker l docks but
            # the following tone melody is preserved.
            next_base = nfd_w[j].lower() if j < len(nfd_w) else ""
            if next_base in _ALL_VOWELS:
                # Copy first mora verbatim (preserving existing tone mark).
                result.append(ch)
                k = i + 1
                while k < len(nfd_w) and unicodedata.combining(nfd_w[k]):
                    result.append(nfd_w[k])
                    k += 1
                i = k; applied = True; continue
            result.append(ch); result.extend(comb); result.append(_ACUTE)
            i = j; applied = True; continue
        result.append(ch); i += 1
    return nfc("".join(result))


def _strip_h_from_initial(word: str) -> str:
    nfd_w   = nfd(word)
    result  = []
    removed = False
    i = 0
    while i < len(nfd_w):
        ch   = nfd_w[i]
        base = ch.lower()
        if not removed and (base in _ALL_VOWELS):
            comb = []
            j = i + 1
            while j < len(nfd_w) and unicodedata.combining(nfd_w[j]):
                if nfd_w[j] != _ACUTE:
                    comb.append(nfd_w[j])
                j += 1
            result.append(ch); result.extend(comb)
            i = j; removed = True; continue
        result.append(ch); i += 1
    return nfc("".join(result))


def apply_dnas(underlying: str, direction: str = "generate") -> str:
    """DNAS — Denasalisation / nasal-lateral alternation.  (M4)

    Generate direction: fuses ní + vowel-initial word → l + H-spread vowel,
    collapsing the three tokens into one.  This is the linguistically full
    Python version; the Phase B HFST pipeline implements a simpler
    unconditional ní→l substitution (without H-spreading) via build_dnas.py.

    Parse direction: splits a l-initial token back into ní + bare vowel form.
    """
    if direction == "generate":
        tokens = underlying.split(" ")
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if tok in ("nί", "ní"):
                if i + 1 < len(tokens):
                    next_tok = tokens[i + 1]
                    base = strip_tone(next_tok[0]).lower() if next_tok else ""
                    if base in _ALL_VOWELS:
                        fused = "l" + _spread_h_to_initial(next_tok)
                        if i > 0:
                            tokens[i - 1] = tokens[i - 1] + fused
                            tokens.pop(i); tokens.pop(i)
                        else:
                            tokens[i] = fused; tokens.pop(i + 1)
                        continue
            i += 1
        return " ".join(tokens)
    elif direction == "parse":
        tokens = underlying.split(" ")
        out = []
        for tok in tokens:
            if len(tok) > 1 and tok[0] == "l":
                rest = tok[1:]
                base = strip_tone(rest[0]).lower() if rest else ""
                if base in _ALL_VOWELS:
                    out.extend(["nί", _strip_h_from_initial(rest)]); continue
            out.append(tok)
        return " ".join(out)
    else:
        raise ValueError(f"direction must be 'generate' or 'parse', got {direction!r}")


# ===========================================================================
# M5 — CDEL
# ===========================================================================

def apply_cdel(underlying: str,
               environment: str = "inter-vocalic-rounded",
               direction: str = "generate") -> str:
    """CDEL — Consonant deletion.  (M5)

    Parse direction for 'word-final' is lossy (the deleted consonant + syllable
    cannot be recovered from the surface form) and returns the input unchanged.
    """
    if direction == "generate":
        if environment == "inter-vocalic-rounded":
            s = underlying
            if " owó" in s:
                return nfc(s.replace(" owó", "wó"))
            parts = s.split(" ", 1)
            if len(parts) == 2:
                for i, ch in enumerate(parts[1]):
                    base = strip_tone(ch).lower()
                    if base in _ALL_VOWELS:
                        return nfc(parts[0] + parts[1][i:])
            return nfc(s)
        elif environment == "word-final":
            s     = underlying
            nfd_s = nfd(s)
            _NASALS = {"n", "m"}
            lv_start = None
            for i in builtins.range(len(nfd_s) - 1, -1, -1):
                ch = nfd_s[i]
                if unicodedata.combining(ch): continue
                if ch.lower() in _ALL_VOWELS:
                    lv_start = i; break
            if lv_start is None or lv_start == 0:
                return nfc(s)
            clip = lv_start
            pos  = lv_start - 1
            while pos >= 0:
                ch = nfd_s[pos]
                if unicodedata.combining(ch): break
                base = ch.lower()
                if base in _ALL_VOWELS: break
                if base in _NASALS: break
                clip = pos; pos -= 1
            return nfc(nfd_s[:clip])
        else:
            raise ValueError(f"Unknown environment: {environment!r}")
    elif direction == "parse":
        if environment == "inter-vocalic-rounded":
            s = underlying
            if s.endswith("wó"):
                return nfc(s[:-2] + " owó")
            return nfc(s)
        elif environment == "word-final":
            return nfc(underlying)   # lossy — cannot recover deleted material
        else:
            raise ValueError(f"Unknown environment: {environment!r}")
    else:
        raise ValueError(f"direction must be 'generate' or 'parse', got {direction!r}")


# ===========================================================================
# M6 — COAL + HARM
# ===========================================================================

def _get_initial_vowel_with_marks(form: str) -> str:
    nfc_f = nfc(form)
    for i, ch in enumerate(nfc_f):
        if unicodedata.combining(ch): continue
        base = strip_tone(ch).lower()
        if base in _ALL_VOWELS:
            j = i + 1
            while j < len(nfc_f) and unicodedata.combining(nfc_f[j]): j += 1
            return nfc_f[i:j]
    return ""


def _drop_initial_vowel(form: str) -> str:
    nfc_f = nfc(form)
    for i, ch in enumerate(nfc_f):
        if unicodedata.combining(ch): continue
        base = strip_tone(ch).lower()
        if base in _ALL_VOWELS:
            j = i + 1
            while j < len(nfc_f) and unicodedata.combining(nfc_f[j]): j += 1
            return nfc_f[j:]
    return form


def select_harm_prefix(root: str) -> str:
    """HARM — select harmonic ogún-series prefix.  (M6)

    Returns 'ogó-' if the root's first vowel is mid-close [e, o],
    'ọgọ́-' if it is mid-open [ɛ, ɔ].
    """
    for ch in nfc(root):
        if unicodedata.combining(ch): continue
        base = strip_tone(ch).lower()
        if base in _ALL_VOWELS:
            return "ogó-" if is_mid_close(ch) else "ọgọ́-"
    return "ọgọ́-"


def apply_coal(underlying_1: str, underlying_2: str = "",
               direction: str = "generate"):
    """COAL — Vowel coalescence.  (M6)

    Generate: (base, multiplier) → coalesced compound surface form.
    Parse:    surface → (base_string, multiplier_string) tuple.
    """
    if direction == "generate":
        u1, u2 = nfc(underlying_1), nfc(underlying_2)
        if u1 == "ogún":
            prefix = select_harm_prefix(u2)
            return nfc(prefix.rstrip("-") + _drop_initial_vowel(u2))
        elif u1 == "igba":
            v1 = _get_initial_vowel_with_marks(u2)
            return nfc("ẹgb" + v1 + _drop_initial_vowel(u2))
        elif u1 == "ẹgbàá":
            return nfc("ẹgbàá" + _drop_initial_vowel(u2))
        else:
            raise ValueError(f"apply_coal: unrecognised base {u1!r}")
    elif direction == "parse":
        surface = nfc(underlying_1)
        ọgọ́ = nfc("ọgọ́"); ogó = nfc("ogó"); ẹgb = nfc("ẹgb")
        if surface.startswith(ọgọ́):
            rem = surface[len(ọgọ́):]
            for n in builtins.range(1, 11):
                if _drop_initial_vowel(ANCHORS[n]["surface"]) == rem:
                    return ("ogún", ANCHORS[n]["surface"])
            raise ValueError(f"apply_coal parse (mid-open): no anchor for {rem!r}")
        elif surface.startswith(ogó):
            rem = surface[len(ogó):]
            for n in builtins.range(1, 11):
                if _drop_initial_vowel(ANCHORS[n]["surface"]) == rem:
                    return ("ogún", ANCHORS[n]["surface"])
            raise ValueError(f"apply_coal parse (mid-close): no anchor for {rem!r}")
        elif surface.startswith(ẹgb):
            after = surface[len(ẹgb):]
            v1    = _get_initial_vowel_with_marks(after)
            rem   = _drop_initial_vowel(after)
            return ("igba", nfc(v1 + rem))
        else:
            raise ValueError(f"apply_coal parse: unrecognised surface {surface!r}")
    else:
        raise ValueError(f"direction must be 'generate' or 'parse', got {direction!r}")


# ===========================================================================
# M7 — ASSI
# ===========================================================================

def apply_assi(igba_form: str, multiplier: str = "",
               direction: str = "generate") -> str:
    """ASSI — Non-contiguous regressive vowel assimilation.  (M7)

    The /i/ of igba- assimilates to the first vowel of the multiplier across
    the /gb/ cluster.  This rule is also encoded in rules.twolc (Phase B) as
    n:m before /b/, though that context is vacuous for the 1–60 range.
    """
    if direction == "generate":
        u2  = nfc(multiplier)
        v1  = _get_initial_vowel_with_marks(u2)
        rem = _drop_initial_vowel(u2)
        first   = nfc(v1)[0] if v1 else ""
        prefix  = "e" if is_mid_close(first) else "ẹ"
        return nfc(prefix + "gb" + v1 + rem)
    elif direction == "parse":
        surface = nfc(igba_form)
        ẹgb = nfc("ẹgb")
        if not surface.startswith(ẹgb):
            raise ValueError(f"apply_assi parse: {surface!r} does not begin with ẹgb")
        after = surface[len(ẹgb):]
        v1    = _get_initial_vowel_with_marks(after)
        rem   = _drop_initial_vowel(after)
        return ("igba", nfc(v1 + rem))
    else:
        raise ValueError(f"direction must be 'generate' or 'parse', got {direction!r}")


# ===========================================================================
# M8 — CLIP
# ===========================================================================

def apply_clip(underlying: str, direction: str = "generate") -> str:
    """CLIP — Clipping in the 11–14 range.  (M8)

    The sequence lélẹ́wàá ("surpasses ten") is contracted to the suffix lá.
    Strictly bounded to integers 11–14; does not apply elsewhere.
    Note: CDEL (rìn→ìn) was previously applied here for n=14 but is now
    suppressed — user-confirmed that ẹ̀rìnlá / mẹ́rìnlá (with r) are the
    correct everyday forms.
    """
    _TARGET  = nfc("lélẹ́wàá")
    _CLIPPED = nfc("lá")
    if direction == "generate":
        s = nfc(underlying)
        if _TARGET not in s:
            raise ValueError(
                f"apply_clip: 'lélẹ́wàá' not found in {underlying!r}; "
                f"CLIP bounded to integers 11–14")
        return s.replace(_TARGET, _CLIPPED)
    elif direction == "parse":
        s = nfc(underlying)
        if not s.endswith(_CLIPPED):
            raise ValueError(f"apply_clip parse: {underlying!r} does not end with 'lá'")
        prefix = s[:-len(_CLIPPED)]
        # CDEL reverse (ìn→rìn) removed — r is always preserved in surface forms.
        return nfc(prefix + _TARGET)
    else:
        raise ValueError(f"direction must be 'generate' or 'parse', got {direction!r}")


# ===========================================================================
# M9 — ELIS
# ===========================================================================

# Bound (compound) forms: the citation form maps to the form used inside
# a compound before ELIS/DNAS apply.
# Anchor 10 (ẹ̀wá) lengthens to ẹ̀wàá in compound context — evidenced by
# _ADJECTIVE[10] = "mẹ́wàá" and the CLIP target "lélẹ́wàá" for 11–14.
_ELIS_COMPOUND_ROOTS: dict[str, str] = {
    nfc("àrún"):  nfc("àrùn-ún"),
    nfc("ẹ̀sán"): nfc("ẹ̀sàn-án"),   # acute cardinal → grave+suffix in compound
    nfc("ẹ̀wá"):  nfc("ẹ̀wàá"),
}
_ELIS_COMPOUND_SKELETON_TO_ROOT: dict[str, str] = {
    nfc("rùn-ún"):  nfc("àrún"),
    nfc("sàn-án"):  nfc("ẹ̀sán"),
    nfc("wàá"):     nfc("ẹ̀wá"),
}


def apply_elis(prefix: str, root: str = "", direction: str = "generate") -> str:
    """ELIS — Vowel elision and floating H-tone docking.  (M9)

    Generate: mú + root → m + H-spread(compound_form_of_root)
    Parse:    m-initial surface → "mú <canonical_root>"  (A1 fix)
    """
    if direction == "generate":
        r          = nfc(root)
        r_compound = _ELIS_COMPOUND_ROOTS.get(r, r)
        return nfc("m" + _spread_h_to_initial(r_compound))
    elif direction == "parse":
        surface = nfc(prefix)
        if not surface.startswith("m"):
            raise ValueError(f"apply_elis parse: {surface!r} doesn't start with 'm'")
        after_m  = surface[1:]
        stripped = _strip_h_from_initial(after_m)
        skeleton = _drop_initial_vowel(stripped)
        if skeleton in _ELIS_COMPOUND_SKELETON_TO_ROOT:
            canonical = _ELIS_COMPOUND_SKELETON_TO_ROOT[skeleton]
            return f"mú {canonical}"
        for n in builtins.range(1, 11):
            cand = ANCHORS[n]["surface"]
            if _drop_initial_vowel(cand) == skeleton:
                return f"mú {cand}"
        raise ValueError(f"apply_elis parse: cannot recover root from {surface!r}")
    else:
        raise ValueError(f"direction must be 'generate' or 'parse', got {direction!r}")


# ===========================================================================
# M10 — TSAN
# ===========================================================================

def _apply_downstep(form: str) -> str:
    """Heuristic downstep: sets toneless vowels to low after a high vowel.

    Note: this is a simplified approximation of the full autosegmental
    tonal sandhi cascade.  The complete implementation would require a
    separate tonal tier with association lines and floating-tone docking
    (Goldsmith 1976; Pulleyblank 1986).  See known gaps in module docstring.
    """
    nfd_f = list(nfd(form))
    out: list[str] = []
    prev_was_H = False
    i = 0
    while i < len(nfd_f):
        ch = nfd_f[i]
        if not unicodedata.combining(ch):
            base = ch.lower()
            if base in _ALL_VOWELS:
                j     = i + 1
                while j < len(nfd_f) and unicodedata.combining(nfd_f[j]): j += 1
                marks = nfd_f[i + 1: j]
                tone  = next((m for m in marks if m in _TONE_MARKS), None)
                if tone == _ACUTE:
                    prev_was_H = True
                    out.append(ch); out.extend(marks)
                elif tone == _GRAVE:
                    prev_was_H = False
                    out.append(ch); out.extend(marks)
                else:
                    if prev_was_H:
                        out.append(ch)
                        out.extend(m for m in marks if m not in _TONE_MARKS)
                        out.append(_GRAVE); prev_was_H = False
                    else:
                        out.append(ch); out.extend(marks)
                i = j; continue
        out.append(ch); i += 1
    return nfc("".join(out))


def apply_tsan(morpheme_sequence: list[str], direction: str = "generate") -> str:
    """TSAN — Tonal sandhi cascade.  (M10)

    Generate direction
    ------------------
    Takes a morpheme list (e.g. ["mú", "ẹ̀ta"]) and returns the ELIS-elided,
    downstepped, DNAS-contracted surface string.

    Parse direction  (A1 fix)
    ---------------
    Takes a list whose first element is the TSAN-fused surface form
    (e.g. ["mẹ́ta"]) and returns the reconstructed underlying morpheme
    sequence as a space-separated string (e.g. "mú ẹ̀ta").

    Scope: only the ELIS context (mú- prefix) is tonal-sandhi-active in
    this domain.  The full four-boundary sandhi chain of mọ́kànlélógún (21)
    is handled by the FST parser via _split_compound + DNAS reversal, not
    through this function.
    """
    _GREEK_IOTA_TONOS = "\u03AF"
    _LATIN_I_ACUTE    = "\u00ED"

    if direction == "generate":
        tokens = [nfc(t) for t in morpheme_sequence]
        if not tokens or tokens[0] != "mú":
            joined = " ".join(tokens)
            return joined.replace(_GREEK_IOTA_TONOS, _LATIN_I_ACUTE)
        if len(tokens) < 2:
            return tokens[0]
        elided      = apply_elis("mú", tokens[1], direction="generate")
        downstepped = _apply_downstep(elided)
        remaining   = tokens[2:]
        if remaining:
            contracted = apply_dnas(" ".join(remaining), direction="generate")
            fused      = contracted.replace(" ", "")
        else:
            fused = ""
        return nfc(downstepped + fused)

    elif direction == "parse":
        if not morpheme_sequence:
            return ""
        surface = nfc(morpheme_sequence[0])
        if surface.startswith("m") and len(surface) > 1:
            try:
                recovered     = apply_elis(surface, direction="parse")
                result_tokens = recovered.split(" ")
            except Exception:
                result_tokens = [surface]
        else:
            result_tokens = [surface]
        remaining = [apply_dnas(tok, direction="parse") for tok in morpheme_sequence[1:]]
        return " ".join(result_tokens + remaining)

    else:
        raise ValueError(f"direction must be 'generate' or 'parse', got {direction!r}")


# ===========================================================================
# M11 — Trie Resolver + Phonological Normaliser
# ===========================================================================

def _build_trie() -> dict[str, int]:
    tbl: dict[str, int] = {}
    for n, rec in ANCHORS.items():
        tbl[nfc(rec["surface"])] = n
    for n, s in _ADJECTIVE.items():
        tbl[nfc(s)] = n
    for n, s in _ORDINAL.items():
        tbl[nfc(s)] = n
    for n, s in _NUMISMATIC.items():
        tbl[nfc(s)] = n
    for n in builtins.range(1, 31):
        tbl[nfc(generate(n, "cardinal"))] = n
    return tbl

_TRIE: dict[str, int] = _build_trie()


def _strip_diacritics(s: str) -> str:
    return nfc("".join(ch for ch in nfd(s)
                       if ch not in _TONE_MARKS and ch != _UNDERDOT))


def _build_stripped_trie() -> dict[str, list[int]]:
    tbl: dict[str, list[int]] = {}
    for surface, n in _TRIE.items():
        key = _strip_diacritics(surface).lower()
        tbl.setdefault(key, [])
        if n not in tbl[key]:
            tbl[key].append(n)
    return tbl

_STRIPPED_TRIE: dict[str, list[int]] = _build_stripped_trie()


def trie_resolve(string: str) -> int | None:
    return _TRIE.get(nfc(string), None)


def normalise(string: str) -> NormaliseResult:
    """Phonological Normaliser — five-tier fallback chain.  (M11)

    Returns a dict with keys: form (normalised string), confidence (0.0–1.0),
    candidates (list of integer values).  Confidence tiers:
        1.0  — exact trie hit
        0.95 — CLIP expansion hit
        0.90 — DNAS reversal hit
        0.80 — stripped-diacritic single match
        0.50 — stripped-diacritic ambiguous match
        0.75 — operator skeleton decomposition
        0.0  — no candidate found
    """
    s = nfc(string.strip())

    n = trie_resolve(s)
    if n is not None:
        return {"form": s, "confidence": 1.0, "candidates": [n]}

    _LA = nfc("lá")
    if s.endswith(_LA):
        try:
            expanded = apply_clip(s, direction="parse")
            n2 = trie_resolve(expanded)
            if n2 is not None:
                return {"form": expanded, "confidence": 0.95, "candidates": [n2]}
        except Exception:
            pass

    reversed_dnas = apply_dnas(s, direction="parse")
    if reversed_dnas != s:
        n3 = trie_resolve(reversed_dnas)
        if n3 is not None:
            return {"form": reversed_dnas, "confidence": 0.90, "candidates": [n3]}

    stripped       = _strip_diacritics(s).lower()
    stripped_parse = _strip_diacritics(apply_dnas(s, direction="parse")).lower()
    candidates_set: list[int] = []
    for key in (stripped, stripped_parse):
        for h in _STRIPPED_TRIE.get(key, []):
            if h not in candidates_set:
                candidates_set.append(h)
    if candidates_set:
        best_n    = candidates_set[0]
        best_form = nfc(generate(best_n, "cardinal"))
        conf      = 0.8 if len(candidates_set) == 1 else 0.5
        return {"form": best_form, "confidence": conf, "candidates": candidates_set}

    s_low = stripped
    for op_sk, operation in (("dini", "SUBTRACT"), ("dinl", "SUBTRACT"),
                              ("din",  "SUBTRACT"), ("le",   "ADD")):
        idx = s_low.find(op_sk)
        if idx <= 0:
            continue
        unit_sk  = s_low[:idx]
        after_op = s_low[idx + len(op_sk):]
        anchor_sk = after_op[1:] if after_op.startswith("l") else after_op
        u_hits = [h for h in _STRIPPED_TRIE.get(unit_sk,   []) if 1 <= h <= 20000]
        a_hits = [h for h in _STRIPPED_TRIE.get(anchor_sk, []) if h in ANCHORS]
        if not a_hits:
            a_hits = [h for h in _STRIPPED_TRIE.get(after_op, []) if h in ANCHORS]
        if u_hits and a_hits:
            u_val = u_hits[0]; a_val = a_hits[0]
            result_n = (a_val - u_val) if operation == "SUBTRACT" else (a_val + u_val)
            if 1 <= result_n <= 20000:
                best_form = nfc(generate(result_n, "cardinal"))
                return {"form": best_form, "confidence": 0.75, "candidates": [result_n]}

    return {"form": s, "confidence": 0.0, "candidates": []}


# ===========================================================================
# M12–M13 — FST Parser (four passes)
# ===========================================================================

_ANCHOR_SURFACE_SORTED: list[tuple[str, int]] = sorted(
    ((nfc(rec["surface"]), n) for n, rec in ANCHORS.items()),
    key=lambda x: len(x[0]), reverse=True)

_ORACLE_SURFACE: dict[str, int] = {}
_ORACLE_SURFACE.update({v: k for k, v in _ADJECTIVE.items()})
_ORACLE_SURFACE.update({v: k for k, v in _ORDINAL.items()})
_ORACLE_SURFACE.update({v: k for k, v in _NUMISMATIC.items()})


def _anchor_scan(surface: str) -> int | None:
    s = nfc(surface.strip())
    for anchor_surface, n in _ANCHOR_SURFACE_SORTED:
        if s == anchor_surface:
            return n
    return None


def _oracle_lookup(surface: str) -> int | None:
    return _ORACLE_SURFACE.get(nfc(surface.strip()), None)


def _split_compound(surface: str) -> tuple[str, str, str] | None:
    s = nfc(surface.strip())
    for op in ("dín ní", "lé ní"):
        positions = []
        idx = 0
        while True:
            pos = s.find(op, idx)
            if pos < 0: break
            positions.append(pos); idx = pos + 1
        for pos in reversed(positions):
            left  = s[:pos].strip()
            right = s[pos + len(op):].strip()
            if left and right:
                return left, op, right
    # Fused DNAS markers: try all positions rightmost-first so that depth-3+
    # surface forms split at the outermost (rightmost) operator, not the inner one.
    _dínl = nfc("dínl"); _lél = nfc("lél")
    for marker, op_label in ((_dínl, "dín ní"), (_lél, "lé ní")):
        positions = []
        idx = 0
        while True:
            pos = s.find(marker, idx)
            if pos < 0: break
            positions.append(pos); idx = pos + 1
        for pos in reversed(positions):
            if pos > 0:
                left     = s[:pos]
                rw       = s[pos + len(marker):]
                dnas_rev = apply_dnas("l" + rw, direction="parse")
                parts    = dnas_rev.split(" ", 1)
                right    = parts[1] if len(parts) > 1 else parts[0]
                return left, op_label, right
    return None


def _consonant_skeleton(form: str) -> str:
    result = []
    for ch in nfd(form):
        if unicodedata.combining(ch): continue
        base = ch.lower()
        if base not in _ALL_VOWELS:
            result.append(base)
    return "".join(result)


def _build_anchor_skeleton() -> dict[str, list[int]]:
    tbl: dict[str, list[int]] = {}
    for n, rec in ANCHORS.items():
        sk = _consonant_skeleton(rec["surface"])
        tbl.setdefault(sk, [])
        if n not in tbl[sk]:
            tbl[sk].append(n)
    return tbl

_ANCHOR_SKELETON: dict[str, list[int]] = _build_anchor_skeleton()


_DOT_BELOW = "\u0323"  # Unicode combining dot below (ẹ, ọ, ụ …)

def _build_suffix_stripped_map() -> dict[str, int]:
    """Map suffix-stripped anchor surface forms back to their integer values.

    surface() strips the syllable-length suffix (-ùn, -àn) from anchor forms
    used as mid-compound units (e.g. ọgọ́rùn-ún → ọgọ́rùn after downstep).
    This table lets the parser recover the correct anchor integer from those
    stripped forms, preventing the consonant-skeleton fallback from returning
    a wrong match (e.g. ọgọ́rùn skeleton "grn" collides with ọgọ̀rin = 80).

    Three key variants are stored per affected anchor so that the lookup
    succeeds regardless of how many diacritics the caller has preserved:

      1. Full diacritics  (ọgọ́rùn)  — standard parse() input
      2. Vowels stripped  (ogórùn)   — dot-below removed, tones intact
      3. Fully stripped   (ogorun)   — all diacritics removed (SMS / ASCII text)
    """
    result: dict[str, int] = {}
    for n, rec in ANCHORS.items():
        surf = nfc(rec["surface"])
        ds = _downstep_final_vowel(surf)
        for suf in (nfc("-\u00f9n"), nfc("-\u00e0n")):  # -ùn, -àn
            if ds.endswith(suf):
                base = nfc(ds[:-len(suf)])

                # Variant 1: full diacritics (original form)
                if base not in result:
                    result[base] = n

                # Variant 2: vowel-quality stripped — remove dot-below only
                vq = nfc("".join(
                    ch for ch in unicodedata.normalize("NFD", base)
                    if ch != _DOT_BELOW
                ))
                if vq not in result:
                    result[vq] = n

                # Variant 3: fully stripped — remove all combining marks
                fs = _strip_diacritics(base)
                if fs not in result:
                    result[fs] = n

                break
    return result

_SUFFIX_STRIPPED_MAP: dict[str, int] = _build_suffix_stripped_map()


def _parse_unit(surface: str) -> int | None:
    s = nfc(surface.strip())
    n = _anchor_scan(s)
    if n is not None: return n
    n = _oracle_lookup(s)
    if n is not None: return n
    if s.startswith("m"):
        try:
            root_str = apply_elis(s, direction="parse").split(" ", 1)[1]
            n = _anchor_scan(root_str)
            if n is not None: return n
        except Exception:
            pass
    n = _SUFFIX_STRIPPED_MAP.get(s)
    if n is not None: return n
    try:
        rec = parse(s)
        return rec["integer"]
    except Exception:
        pass
    return None


def _parse_anchor_right(surface: str) -> int | None:
    """A3 fix: cascading fallback strategy for anchor recovery in parse pass 4."""
    s = nfc(surface.strip())
    n = _anchor_scan(s)
    if n is not None: return n
    key  = _strip_diacritics(s).lower()
    hits = [h for h in _STRIPPED_TRIE.get(key, []) if h in ANCHORS]
    if hits: return hits[0]
    h_stripped = _strip_h_from_initial(s)
    if h_stripped != s:
        n = _anchor_scan(h_stripped)
        if n is not None: return n
        hkey  = _strip_diacritics(h_stripped).lower()
        hits2 = [h for h in _STRIPPED_TRIE.get(hkey, []) if h in ANCHORS]
        if hits2: return hits2[0]
    n = _SUFFIX_STRIPPED_MAP.get(s)
    if n is not None: return n
    sk      = _consonant_skeleton(s)
    sk_hits = [h for h in _ANCHOR_SKELETON.get(sk, []) if h in ANCHORS]
    if len(sk_hits) == 1: return sk_hits[0]
    if len(sk_hits) > 1:
        for h in sk_hits:
            if key.startswith(_strip_diacritics(ANCHORS[h]["surface"]).lower()[:3]):
                return h
        return sk_hits[0]
    dnas_candidate = apply_dnas("l" + s, direction="parse")
    parts = dnas_candidate.split(" ", 1)
    if len(parts) == 2:
        recovered = parts[1]
        n = _anchor_scan(recovered)
        if n is not None: return n
        rsk_hits = [h for h in _ANCHOR_SKELETON.get(_consonant_skeleton(recovered), [])
                    if h in ANCHORS]
        if rsk_hits: return rsk_hits[0]
    try:
        rec = parse(s)
        return rec["integer"]
    except Exception:
        pass
    return None


def parse(string: str) -> ParseResult:
    """FST Parser — four-pass bidirectional morphological analyser.  (M12–13)

    Pass 1: direct anchor scan + oracle table lookup
    Pass 2: _split_compound with spaced and contracted operator forms
    Pass 3: normalise() fallback for under-diacritised / variant inputs
    Pass 4: DNAS-reversal for l-initial contracted forms

    Returns a ParseResult dict with keys: integer, operation, form, morphemes.
    """
    s_raw = nfc(string.strip())

    _LA = nfc("lá")
    if s_raw.endswith(_LA):
        try:
            expanded = apply_clip(s_raw, direction="parse")
            return parse(expanded)
        except Exception:
            pass

    n = _anchor_scan(s_raw)
    if n is not None:
        return {"integer": n, "operation": "ANCHOR", "form": s_raw,
                "morphemes": getMorphemes(n)}

    n = _oracle_lookup(s_raw)
    if n is not None:
        return {"integer": n, "operation": "ANCHOR", "form": s_raw,
                "morphemes": getMorphemes(n)}

    split = _split_compound(s_raw)
    if split is not None:
        left, op_token, right = split
        unit_n   = _parse_unit(left)
        anchor_n = _parse_anchor_right(right)
        if unit_n is not None and anchor_n is not None:
            if "dín" in op_token:
                integer = anchor_n - unit_n; operation = "SUBTRACT"
            else:
                integer = anchor_n + unit_n; operation = "ADD"
            if 1 <= integer <= 20000:
                return {"integer": integer, "operation": operation,
                        "form": s_raw, "morphemes": getMorphemes(integer)}

    norm_result = normalise(s_raw)
    if norm_result["confidence"] > 0.0 and norm_result["form"] != s_raw:
        try:
            return parse(norm_result["form"])
        except Exception:
            pass

    if s_raw and s_raw[0] == "l":
        dnas_rev = apply_dnas(s_raw, direction="parse")
        if dnas_rev != s_raw:
            parts = dnas_rev.split(" ", 1)
            if len(parts) == 2:
                n_anchor = _parse_anchor_right(parts[1])
                if n_anchor is not None:
                    return {"integer": n_anchor, "operation": "PARTIAL",
                            "form": s_raw, "morphemes": getMorphemes(n_anchor)}

    raise ValueError(f"parse: cannot parse {string!r}")


# ===========================================================================
# M14 — Full API
# ===========================================================================

def roundtrip(n: int) -> bool:
    try:
        surface = generate(n, "cardinal")
        result  = parse(surface)
        return result["integer"] == n
    except (ValueError, KeyError):
        return False


def validate_range(start: int, end: int) -> ValidationResult:
    """Run roundtrip() for every integer in [start, end] and report results."""
    passed = failed = 0
    failures: list[dict] = []
    for n in builtins.range(start, end + 1):
        if roundtrip(n):
            passed += 1
        else:
            failed += 1
            try:
                surface = generate(n, "cardinal")
            except Exception as e:
                surface = f"(generate error: {e})"
            failures.append({"n": n, "surface": surface})
    return {"passed": passed, "failed": failed, "total": end - start + 1,
            "failures": failures}


def trace(n: int) -> list[dict[str, Any]]:
    """Return a step-by-step derivation trace for *n*.

    Each step dict carries: step, n, operation, anchor, unit, anchor_type,
    dist_to_lower, dist_to_upper, decision, formula, yoruba_form, depth.
    """
    if not (1 <= n <= 20000):
        raise ValueError(f"n={n} out of range [1, 20000]")

    steps: list[dict[str, Any]] = []

    def _trace(m: int, depth: int) -> str:
        if m in ANCHORS:
            surface = ANCHORS[m]["surface"]
            steps.append({
                "step":        len(steps) + 1,
                "n":           m,
                "operation":   "ANCHOR",
                "anchor":      m,
                "unit":        None,
                "anchor_type": ANCHORS[m]["type"],
                "dist_to_lower": 0,
                "dist_to_upper": 0,
                "decision":    f"{m} is a primitive anchor",
                "formula":     str(m),
                "yoruba_form": surface,
                "depth":       depth,
            })
            return surface

        info             = nearestAnchors(m)
        lower, upper     = info["lower_anchor"], info["upper_anchor"]
        dist_lo, dist_up = info["dist_lower"],   info["dist_upper"]

        if dist_up <= dist_lo:
            unit        = upper - m
            unit_form   = _trace(unit, depth + 1)
            anchor_form = ANCHORS[upper]["surface"]
            surface     = f"{unit_form} dín ní {anchor_form}"
            steps.append({
                "step":          len(steps) + 1,
                "n":             m,
                "operation":     "SUBTRACT",
                "anchor":        upper,
                "unit":          unit,
                "anchor_type":   ANCHORS[upper]["type"],
                "dist_to_lower": dist_lo,
                "dist_to_upper": dist_up,
                "decision":      (f"{m} is {dist_up} from {upper} vs {dist_lo} "
                                  f"from {lower} → subtract from upper"),
                "formula":       f"{upper} − {unit}",
                "yoruba_form":   surface,
                "depth":         depth,
            })
            return surface
        else:
            unit        = m - lower
            unit_form   = _trace(unit, depth + 1)
            anchor_form = ANCHORS[lower]["surface"]
            surface     = f"{unit_form} lé ní {anchor_form}"
            steps.append({
                "step":          len(steps) + 1,
                "n":             m,
                "operation":     "ADD",
                "anchor":        lower,
                "unit":          unit,
                "anchor_type":   ANCHORS[lower]["type"],
                "dist_to_lower": dist_lo,
                "dist_to_upper": dist_up,
                "decision":      (f"{m} is {dist_lo} from {lower} vs {dist_up} "
                                  f"from {upper} → add to lower"),
                "formula":       f"{lower} + {unit}",
                "yoruba_form":   surface,
                "depth":         depth,
            })
            return surface

    _trace(n, 0)
    return steps


def decompose(n: int) -> str:
    """Return a plain-English arithmetic decomposition of *n*.

    Example: decompose(1850) → '1850 = 1900 − 50  (àádọ́ta dín ní ẹ̀ẹ́dẹ́gbẹ̀wá)'
    """
    steps = trace(n)
    top   = steps[-1]
    if top["operation"] == "ANCHOR":
        anchor_type = ANCHORS[n]["type"]
        return f"{n} = {ANCHORS[n]['surface']}  ({anchor_type} anchor)"
    op_sym = "−" if top["operation"] == "SUBTRACT" else "+"
    return (f"{n} = {top['anchor']} {op_sym} {top['unit']}"
            f"  ({top['yoruba_form']})")


def derive(n: int) -> dict[str, Any]:
    """Return the full derivation record for *n*.

    Keys: integer, cardinal, adjective, ordinal, numismatic,
          morphemes, derivation_depth, trace.
    Primary research-facing output; referenced in §5.1 of the manuscript.
    """
    if not (1 <= n <= 20000):
        raise ValueError(f"n={n} out of range [1, 20000]")
    derivation_trace = trace(n)
    return {
        "integer":          n,
        "cardinal":         generate(n, "cardinal"),
        "adjective":        generate(n, "adjective"),
        "ordinal":          generate(n, "ordinal"),
        "numismatic":       generate(n, "numismatic"),
        "morphemes":        getMorphemes(n),
        "derivation_depth": len(derivation_trace),
        "trace":            derivation_trace,
    }


def range(start: int, end: int) -> list[dict[str, Any]]:
    """Return derive() records for every integer in [start, end].

    Note: shadows the Python builtin range; use builtins.range internally.
    """
    if not (1 <= start <= end <= 20000):
        raise ValueError(
            f"range [{start}, {end}] out of domain [1, 20000]")
    return [derive(n) for n in builtins.range(start, end + 1)]


# ===========================================================================
# Phase B compatibility — HFST oracle
# ===========================================================================
#
# yoruba(n) is the oracle function imported by validate_hfst.py:
#
#     from phase4 import yoruba as oracle
#
# It returns the HFST-compatible post-DNAS surface form for integers 1–60,
# matching the output of build/yoruba-numerals-final.hfst.  It is derived
# directly from generate() so it is always consistent with the anchor lexicon
# above — in particular, anchor 9 is always ẹ̀sán (acute), resolving the
# tonal discrepancy in earlier standalone oracle drafts.
#
# Surface form convention for yoruba() vs generate():
#   generate(17) → "ẹ̀ta dín ní ogún"    (pre-DNAS, linker spelled out)
#   yoruba(17)   → "ẹ̀ta dín l ogún"     (post-DNAS, standalone "l" token)
#
# The replacement " ní " → " l " mirrors exactly what the dnas-rewrite.hfst
# transducer does: an unconditional length-changing substitution of the
# two-character sequence ní with the single character l, preserving the
# surrounding spaces.  H-tone spreading on the following vowel (which the
# Python apply_dnas() performs) is NOT applied here, matching the HFST
# transducer's simpler behaviour.

def yoruba(n: int) -> str:
    """Return the HFST-compatible Yoruba surface form for integer *n* (1–60).

    Used by validate_hfst.py as the Python oracle against which the compiled
    transducer is checked.  The linker ní is replaced by the standalone token
    l (flanked by spaces) to match the output of dnas-rewrite.hfst.

    Raises ValueError for n outside 1–60 (the Phase B HFST coverage range).
    """
    if not (1 <= n <= 60):
        raise ValueError(
            f"yoruba(): n={n} is outside the Phase B HFST range (1–60). "
            f"Use generate(n) for the full 1–20,000 range.")
    return generate(n, "cardinal").replace(" ní ", " l ")






def surface(n: int, form_class: str = "cardinal") -> str:
    """Return the everyday fused Yoruba surface form for integer *n* (1-20000).

    Three transforms applied to generate() output in order:
      1. Downstep -- final vowel of unit morpheme lowers before the operator.
      2. DNAS     -- linker ni contracts into the anchor initial vowel.
      3. Fusion   -- all spaces removed, yielding a single word.

    generate() returns the pre-DNAS canonical form used by the parser.
    surface() is a one-way display transform; its output cannot be parsed.
    """
    if not (1 <= n <= 20000):
        raise ValueError(f"surface(): n={n} out of range [1, 20000]")

    canonical = generate(n, form_class)

    # Anchor-only and CLIP forms have no spaces and are already fully fused.
    if " " not in canonical:
        return canonical

    # Cardinal 11–14 also use CLIP in the surface form.  generate() keeps
    # the spaced canonical form so the parser is unaffected; surface()
    # applies the same CLIP path used by adjective/numismatic.
    if form_class == "cardinal" and 11 <= n <= 14:
        unit         = n - 10
        unit_form    = generate(unit, form_class)
        unit_form_ds = _downstep_final_vowel(unit_form)
        anchor_bound = _COMPOUND_ANCHOR_FORMS[10]
        spaced       = f"{unit_form_ds} lé ní {anchor_bound}"
        dnas_form    = apply_dnas(spaced, direction="generate")
        clip_form    = apply_clip(dnas_form, direction="generate")
        _LA = nfc("lá")
        return nfc(clip_form.replace(" " + _LA, _LA))

    # Build tonal operator separators.
    _DIN_SP = nfc(" dín ní ")
    _LE_SP  = nfc(" lé ní ")

    found_op = None
    for sep in [_DIN_SP, _LE_SP]:
        if sep in canonical:
            found_op = sep
            break

    if found_op:
        unit_part, _, rest = canonical.partition(found_op)
        unit_ds = _downstep_final_vowel(unit_part)
        # Strip the syllable-length suffix (-ún → -ùn, -án → -àn after
        # downstep) from the unit morpheme when it appears mid-compound.
        # Citation forms at the right edge (anchors) retain their suffix.
        for _suf in (nfc("-ùn"), nfc("-àn")):
            if unit_ds.endswith(_suf):
                unit_ds = unit_ds[:-len(_suf)]
                break
        spaced  = unit_ds + found_op + rest
    else:
        spaced = canonical

    dnas = apply_dnas(spaced, direction="generate")
    return nfc(dnas.replace(" ", ""))
