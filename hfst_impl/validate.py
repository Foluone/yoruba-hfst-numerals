"""validate.py — Exhaustive H1/H2/H3 acceptance checks
=========================================================
Yoruba Vigesimal Numeral System — HFST reimplementation

Per the design doc's testing philosophy: the domain is exactly 20,000
integers, so every check here runs the FULL range, not a sample. Reports
exact pass counts, not percentages, and prints every failure (there should
be none) rather than stopping at the first one, so a partial regression is
still fully visible.

Checks:

  H1  generate(n, fc) == phase4.generate(n, fc)
      for n in 1-20000, fc in {cardinal, adjective, ordinal, numismatic}.
      80,000 comparisons total.

  H2-regression  yoruba_extended(n) == phase4.yoruba(n)
      for n in 1-60. This is the existing, already-validated Phase B
      ground truth -- must still match exactly after the rebuild.

  H2-extension  yoruba_extended(n) == NFC(phase4.generate(n,"cardinal")
                                          .replace(" ni ", " l "))
      for n in 1-20000. Labelled "extension" rather than "oracle
      validation" because phase4.yoruba() itself only defines this
      convention up to 60 -- past that there is no independent oracle, only
      the same substitution rule phase4.yoruba() already uses, applied by a
      compiled FST instead of Python's str.replace.

  H3-shallow  surface_extended(n, fc) == phase4.surface(n, fc)
      for the 1856 values with recursion depth <= 1 (pure anchors + single-
      level compounds), where phase4.surface() is known-correct. A mismatch
      here is a real bug.

  H3-deep  coverage sweep, no independent oracle
      for the 18144 values with recursion depth >= 2, where phase4.surface()
      itself does not downstep every boundary (see IMPLEMENTATION_NOTES.md).
      Confirms surface_extended() runs cleanly on all of them and prints
      examples for manual/linguistic spot-checking.
"""

from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "reference"))
import phase4 as oracle  # noqa: E402

import pipeline  # noqa: E402
import surface  # noqa: E402

NFC = lambda s: unicodedata.normalize("NFC", s)  # noqa: E731

FORM_CLASSES = ("cardinal", "adjective", "ordinal", "numismatic")


def _depth(n: int) -> int:
    """Number of nested compound boundaries in n's cardinal decomposition.
    0 = pure anchor, 1 = single-level compound, 2-3 = nested compounds
    where phase4.surface() is known not to downstep every boundary."""
    s = oracle.generate(n, "cardinal")
    return s.count(" dín ní ") + s.count(" lé ní ")


def run_h1():
    total = 0
    failed = []
    per_class = {fc: [0, 0] for fc in FORM_CLASSES}
    for n in range(1, 20001):
        for fc in FORM_CLASSES:
            total += 1
            expected = NFC(oracle.generate(n, fc))
            try:
                got = NFC(pipeline.generate(n, fc))
            except Exception as e:
                got = f"<error: {e}>"
            if got == expected:
                per_class[fc][0] += 1
            else:
                per_class[fc][1] += 1
                failed.append((n, fc, expected, got))
    return total, failed, per_class


def run_h2_regression():
    failed = []
    for n in range(1, 61):
        expected = NFC(oracle.yoruba(n))
        got = NFC(pipeline.yoruba_extended(n))
        if got != expected:
            failed.append((n, expected, got))
    return failed


def run_h2_extension():
    failed = []
    for n in range(1, 20001):
        expected = NFC(oracle.generate(n, "cardinal").replace(" ní ", " l "))
        got = NFC(pipeline.yoruba_extended(n))
        if got != expected:
            failed.append((n, expected, got))
    return failed


def run_h3_shallow():
    total = 0
    failed = []
    for n in range(1, 20001):
        if _depth(n) > 1:
            continue
        for fc in FORM_CLASSES:
            total += 1
            expected = NFC(oracle.surface(n, fc))
            try:
                got = NFC(surface.surface_extended(n, fc))
            except Exception as e:
                got = f"<error: {e}>"
            if got == expected:
                continue
            failed.append((n, fc, expected, got))
    return total, failed


def run_h3_deep_sanity():
    total = 0
    errors = []
    examples = {2: [], 3: []}
    for n in range(1, 20001):
        d = _depth(n)
        if d < 2:
            continue
        for fc in FORM_CLASSES:
            total += 1
            try:
                got = surface.surface_extended(n, fc)
            except Exception as e:
                errors.append((n, fc, str(e)))
                continue
            if fc == "cardinal" and len(examples[d]) < 5:
                examples[d].append((n, got))
    return total, errors, examples


def main():
    print("=" * 70)
    print("H1 -- arithmetic.decompose_skeleton() vs phase4.generate()")
    print("=" * 70)
    total, failed, per_class = run_h1()
    for fc in FORM_CLASSES:
        p, f = per_class[fc]
        print(f"  {fc:12s} {p:5d}/{p+f:5d} pass")
    print(f"  TOTAL        {total - len(failed)}/{total} pass")
    if failed:
        print(f"  First failures ({min(10, len(failed))} of {len(failed)}):")
        for n, fc, exp, got in failed[:10]:
            print(f"    n={n} fc={fc} expected={exp!r} got={got!r}")

    print()
    print("=" * 70)
    print("H2-regression -- pipeline.yoruba_extended() vs phase4.yoruba() (1-60)")
    print("=" * 70)
    h2r_failed = run_h2_regression()
    print(f"  {60 - len(h2r_failed)}/60 pass")
    for n, exp, got in h2r_failed[:10]:
        print(f"    n={n} expected={exp!r} got={got!r}")

    print()
    print("=" * 70)
    print("H2-extension -- pipeline.yoruba_extended() vs generalised substitution (1-20000)")
    print("=" * 70)
    h2e_failed = run_h2_extension()
    print(f"  {20000 - len(h2e_failed)}/20000 pass")
    for n, exp, got in h2e_failed[:10]:
        print(f"    n={n} expected={exp!r} got={got!r}")

    print()
    print("=" * 70)
    print("H3-shallow -- surface.surface_extended() vs phase4.surface() (depth<=1, 1856 values x 4 fc)")
    print("=" * 70)
    h3s_total, h3s_failed = run_h3_shallow()
    print(f"  {h3s_total - len(h3s_failed)}/{h3s_total} pass")
    for n, fc, exp, got in h3s_failed[:10]:
        print(f"    n={n} fc={fc} expected={exp!r} got={got!r}")

    print()
    print("=" * 70)
    print("H3-deep -- surface.surface_extended() coverage sweep (depth>=2, no independent oracle)")
    print("=" * 70)
    h3d_total, h3d_errors, h3d_examples = run_h3_deep_sanity()
    print(f"  {h3d_total - len(h3d_errors)}/{h3d_total} completed without error")
    for n, fc, msg in h3d_errors[:10]:
        print(f"    n={n} fc={fc} ERROR: {msg}")
    for d in sorted(h3d_examples):
        print(f"  depth {d} examples (cardinal):")
        for n, s in h3d_examples[d]:
            print(f"    {n:6d} -> {s}")

    print()
    all_pass = (
        not failed and not h2r_failed and not h2e_failed
        and not h3s_failed and not h3d_errors
    )
    print("RESULT:", "ALL CHECKS PASSED" if all_pass else "FAILURES DETECTED -- see above")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
