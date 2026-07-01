"""pipeline_hfst.py -- Same as pipeline.py, wired to the real-HFST backend."""

from __future__ import annotations

import arithmetic_hfst as arithmetic
import phonology_hfst as phonology


def generate(n: int, form_class: str = "cardinal") -> str:
    return arithmetic.decompose_skeleton(n, form_class)


def yoruba_extended(n: int) -> str:
    skeleton = arithmetic.decompose_skeleton(n, "cardinal")
    return phonology.apply_dnas_simple(skeleton)
