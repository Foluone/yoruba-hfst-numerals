"""surface.py — Recursive everyday-fused surface form (H3)
=============================================================
Yoruba Vigesimal Numeral System — HFST reimplementation

phase4.surface() applies downstep + suffix truncation + DNAS + space-fusion
exactly once, to the outermost compound boundary only. That's correct for
the 1,856 values in 1-20000 that are pure anchors or single-level compounds,
but 18,144 values (90.7% of the range) need 2-3 levels of nested
compounding, and every boundary but the outermost one is left un-downstepped
by the current Python reference (see IMPLEMENTATION_NOTES.md for the
measurement).

surface_extended() applies the same three phonological operations
(phonology.apply_downstep / apply_suffix_truncation / apply_dnas_full)
recursively, bottom-up, at every boundary -- so a 3-level number gets its
inner-most unit fused first, then that result is downstepped/truncated
before being fused into the next level up, and so on. Deliberately
generalises past what phase4.surface() currently does, rather than
reproducing its gap -- see the design doc's open-questions log for the
reasoning; this is the one place in H0-H3 where a design decision was made
rather than a pure match-the-oracle exercise, since no independently
correct oracle exists for the deep cases.
"""

from __future__ import annotations

import arithmetic
import phonology


def surface_extended(n: int, form_class: str = "cardinal") -> str:
    if not (1 <= n <= 20000):
        raise ValueError(f"n={n} out of range [1, 20000]")

    # Base cases: already fully realised, nothing further to fuse.
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

    # General case: recurse on the unit first, THEN apply phonology at
    # this boundary, so nested compounds get every boundary treated.
    info = arithmetic.nearest_anchors(n)
    lower, upper = info["lower_anchor"], info["upper_anchor"]
    dist_lo, dist_up = info["dist_lower"], info["dist_upper"]

    if dist_up <= dist_lo:
        unit, anchor_v, op = upper - n, upper, "dín"
    else:
        unit, anchor_v, op = n - lower, lower, "lé"

    unit_surface = surface_extended(unit, form_class)
    anchor_form = arithmetic.ANCHORS[anchor_v]["surface"]

    # Downstep and suffix-truncation both need the operator immediately to
    # their right to fire (that's the environment they're defined over), so
    # build the full boundary string BEFORE applying them -- applying them
    # to unit_surface in isolation (missing the right context) was a real
    # bug caught by validate.py's H3-shallow check.
    spaced = f"{unit_surface} {op} ní {anchor_form}"
    downstepped = phonology.apply_downstep(spaced)
    truncated = phonology.apply_suffix_truncation(downstepped)
    fused = phonology.apply_dnas_full(truncated)
    return fused.replace(" ", "")  # orthographic word-fusion, not phonology
