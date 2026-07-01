"""pipeline.py — Wires arithmetic.py + phonology.py together (Option B)
=========================================================================
Yoruba Vigesimal Numeral System — HFST reimplementation

Two public entry points:

  generate(n, form_class)  -- matches phase4.generate(n, form_class) exactly
                               for all n in 1-20000, all 4 form classes.
                               (H1 acceptance target.)

  yoruba_extended(n)       -- matches phase4.yoruba(n) exactly for n in
                               1-60 (regression), and extends the same
                               "post-DNAS, spaces-preserved" surface
                               convention to the full 1-20000 range (the
                               concrete ask in the design doc's Known Gaps:
                               "Extending the lexc/twolc pipeline to the
                               full 1-20,000 range").

Both are thin: arithmetic.decompose_skeleton() already does the recursive
composition (delegating the one phonology-dependent branch to phonology.py
itself), so generate() here is a pure passthrough. yoruba_extended() adds
exactly one more compiled-FST step (DNAS) on top.
"""

from __future__ import annotations

import arithmetic
import phonology


def generate(n: int, form_class: str = "cardinal") -> str:
    return arithmetic.decompose_skeleton(n, form_class)


def yoruba_extended(n: int) -> str:
    skeleton = arithmetic.decompose_skeleton(n, "cardinal")
    return phonology.apply_dnas_simple(skeleton)
