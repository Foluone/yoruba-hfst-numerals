"""arithmetic_hfst.py -- Same as arithmetic.py, wired to phonology_hfst.

Identical logic to arithmetic.py (H1, pure Python recursive decomposition,
no phonology of its own); the only difference is the narrow adjective/
numismatic/cardinal 11-14 branch delegates to phonology_hfst.py (real HFST)
instead of phonology.py (Pynini). Kept as a separate file rather than
making arithmetic.py's phonology backend pluggable, since the duplication
is small and it keeps the two backends (Pynini vs real HFST) fully
independent and separately runnable/comparable.
"""

from __future__ import annotations

import bisect
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "reference"))
import phase4 as _oracle  # noqa: E402  (anchor lexicon + paradigm tables only)

import phonology_hfst as phonology  # noqa: E402

ANCHORS = _oracle.ANCHORS
_ANCHOR_VALUES = sorted(ANCHORS)
_ADJECTIVE = _oracle._ADJECTIVE
_ORDINAL = _oracle._ORDINAL
_NUMISMATIC = _oracle._NUMISMATIC
_COMPOUND_ANCHOR_FORMS = _oracle._COMPOUND_ANCHOR_FORMS

_NFC = lambda s: unicodedata.normalize("NFC", s)  # noqa: E731


def nearest_anchors(n: int) -> dict[str, int]:
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
    if not (1 <= n <= 20000):
        raise ValueError(f"n={n} out of range [1, 20000]")

    if form_class == "adjective" and n in _ADJECTIVE:
        return _ADJECTIVE[n]
    if form_class == "ordinal" and n in _ORDINAL:
        return _ORDINAL[n]
    if form_class == "numismatic" and n in _NUMISMATIC:
        return _NUMISMATIC[n]

    if n in ANCHORS:
        return ANCHORS[n]["surface"]

    if form_class in ("adjective", "numismatic") and 11 <= n <= 14:
        unit = n - 10
        unit_form = decompose_skeleton(unit, form_class)
        return phonology.apply_clip_11_14(unit_form)

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
