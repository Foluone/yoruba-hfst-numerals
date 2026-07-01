"""arithmetic.py — Recursive numeral decomposition (Option B, H1)
===================================================================
Yoruba Vigesimal Numeral System — HFST reimplementation

Per the design doc's Option B split, this module is the "thin deterministic
pre-processor": it decides *which* anchor a number attaches to, whether it
adds or subtracts, and how deep the recursive compounding goes. It contains
no phonology whatsoever -- every string it returns is the literal
concatenation of citation-form morphemes with the un-contracted linker "ní"
spelled out, exactly like phase4.generate()'s output. The one exception
(documented inline) is the adjective/numismatic 11-14 branch, where
phase4.generate() itself already bakes phonology in; that piece is
delegated to phonology.apply_clip_11_14() rather than duplicated here, so
this module still never touches phonology directly.

This is a from-scratch re-derivation of the decomposition logic (not a
line-for-line port) that reuses phase4's lexicon/oracle *data* (the anchor
table and the 1-10/20 paradigm tables), since re-typing 65 anchors' worth of
combining-diacritic Yoruba by hand would risk silent transcription errors.
Reusing verified data tables is different from porting imperative rule
logic -- see the design doc, section 2.

H1 acceptance criterion: decompose_skeleton(n, fc) == phase4.generate(n, fc)
for every n in 1-20000 and every form class. See validate.py.
"""

from __future__ import annotations

import bisect
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "reference"))
import phase4 as _oracle  # noqa: E402  (anchor lexicon + paradigm tables only)

import phonology  # noqa: E402  (only used for the narrow 11-14 branch)

ANCHORS = _oracle.ANCHORS
_ANCHOR_VALUES = sorted(ANCHORS)
_ADJECTIVE = _oracle._ADJECTIVE
_ORDINAL = _oracle._ORDINAL
_NUMISMATIC = _oracle._NUMISMATIC
_COMPOUND_ANCHOR_FORMS = _oracle._COMPOUND_ANCHOR_FORMS

_NFC = lambda s: unicodedata.normalize("NFC", s)  # noqa: E731


def nearest_anchors(n: int) -> dict[str, int]:
    """Pure arithmetic: find the anchor(s) n is decomposed relative to.
    Reimplemented independently of phase4.nearestAnchors (same bisect-based
    logic) since this is math, not a linguistic rule."""
    if not (1 <= n <= 20000):
        raise ValueError(f"n={n} out of range [1, 20000]")
    if n in ANCHORS:
        return {"lower_anchor": n, "upper_anchor": n, "dist_lower": 0, "dist_upper": 0}
    pos = bisect.bisect_left(_ANCHOR_VALUES, n)
    lower = _ANCHOR_VALUES[pos - 1]
    upper = _ANCHOR_VALUES[pos]
    return {
        "lower_anchor": lower, "upper_anchor": upper,
        "dist_lower": n - lower, "dist_upper": upper - n,
    }


def decompose_skeleton(n: int, form_class: str = "cardinal") -> str:
    """Return the pre-phonology canonical form for integer n.

    Matches phase4.generate(n, form_class) exactly. Recursion depth is
    whatever nearest_anchors() requires -- values like 2453 recurse three
    levels deep (2453 -> unit 453 -> unit 47 -> unit 3== anchor), which is
    why this has to be genuinely recursive rather than a single flat lookup.
    """
    if not (1 <= n <= 20000):
        raise ValueError(f"n={n} out of range [1, 20000]")

    # Oracle table lookups (1-10, and numismatic 20) -- already fully
    # lexicalised surface forms, no composition or phonology involved.
    if form_class == "adjective" and n in _ADJECTIVE:
        return _ADJECTIVE[n]
    if form_class == "ordinal" and n in _ORDINAL:
        return _ORDINAL[n]
    if form_class == "numismatic" and n in _NUMISMATIC:
        return _NUMISMATIC[n]

    # Pure anchors: same citation surface form regardless of form class.
    if n in ANCHORS:
        return ANCHORS[n]["surface"]

    # Narrow branch: adjective/numismatic 11-14 lean on anchor 10's bound
    # compound form ("ẹ̀wàá") and phase4.generate() resolves them via
    # phonology (DNAS + CLIP) rather than plain concatenation. We replicate
    # that exactly, but delegate the phonological part to phonology.py so
    # this module stays phonology-free.
    if form_class in ("adjective", "numismatic") and 11 <= n <= 14:
        unit = n - 10
        unit_form = decompose_skeleton(unit, form_class)
        return phonology.apply_clip_11_14(unit_form)

    # General recursive compound decomposition: unit (recursively derived,
    # in the caller's form_class) + operator + anchor (always cardinal).
    info = nearest_anchors(n)
    lower, upper = info["lower_anchor"], info["upper_anchor"]
    dist_lo, dist_up = info["dist_lower"], info["dist_upper"]

    if dist_up <= dist_lo:
        unit = upper - n
        unit_form = decompose_skeleton(unit, form_class)
        anchor_form = decompose_skeleton(upper, "cardinal")
        return f"{unit_form} dín ní {anchor_form}"
    else:
        unit = n - lower
        unit_form = decompose_skeleton(unit, form_class)
        anchor_form = decompose_skeleton(lower, "cardinal")
        return f"{unit_form} lé ní {anchor_form}"
