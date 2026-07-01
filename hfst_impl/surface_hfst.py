"""surface_hfst.py -- Same as surface.py, wired to phonology_hfst/arithmetic_hfst.

Identical recursive-fusion design to surface.py (H3): applies downstep,
suffix truncation, and full DNAS at every compound boundary, bottom-up,
generalising past phase4.surface()'s outermost-boundary-only behaviour.
The only difference from surface.py is the phonology backend (real HFST
instead of Pynini).
"""

from __future__ import annotations

import arithmetic_hfst as arithmetic
import phonology_hfst as phonology


def surface_extended(n: int, form_class: str = "cardinal") -> str:
    if not (1 <= n <= 20000):
        raise ValueError(f"n={n} out of range [1, 20000]")

    if form_class == "adjective" and n in arithmetic._ADJECTIVE:
        return arithmetic._ADJECTIVE[n]
    if form_class == "ordinal" and n in arithmetic._ORDINAL:
        return arithmetic._ORDINAL[n]
    if form_class == "numismatic" and n in arithmetic._NUMISMATIC:
        return arithmetic._NUMISMATIC[n]
    if n in arithmetic.ANCHORS:
        return arithmetic.ANCHORS[n]["surface"]
    if form_class in ("cardinal", "adjective", "numismatic") and 11 <= n <= 14:
        unit = n - 10
        unit_form = surface_extended(unit, form_class)
        return phonology.apply_clip_11_14(unit_form)

    info = arithmetic.nearest_anchors(n)
    lower, upper = info["lower_anchor"], info["upper_anchor"]
    dist_lo, dist_up = info["dist_lower"], info["dist_upper"]

    if dist_up <= dist_lo:
        unit, anchor_v, op = upper - n, upper, "dín"
    else:
        unit, anchor_v, op = n - lower, lower, "lé"

    unit_surface = surface_extended(unit, form_class)
    anchor_form = arithmetic.ANCHORS[anchor_v]["surface"]

    spaced = f"{unit_surface} {op} ní {anchor_form}"
    downstepped = phonology.apply_downstep(spaced)
    truncated = phonology.apply_suffix_truncation(downstepped)
    fused = phonology.apply_dnas_full(truncated)
    return fused.replace(" ", "")
