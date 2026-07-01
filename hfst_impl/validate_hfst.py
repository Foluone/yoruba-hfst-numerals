"""validate_hfst.py -- Same exhaustive acceptance checks as validate.py,
run against the real-HFST backend (pipeline_hfst / surface_hfst) instead
of the Pynini backend. Same acceptance criteria throughout; see validate.py
for the full rationale (exhaustive, no sampling, exact pass counts).

Requires setup_hfst.sh to have been sourced first.
"""

from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "reference"))
import phase4 as oracle  # noqa: E402

import pipeline_hfst as pipeline  # noqa: E402
import surface_hfst as surface  # noqa: E402

NFC = lambda s: unicodedata.normalize("NFC", s)  # noqa: E731
FORM_CLASSES = ("cardinal", "adjective", "ordinal", "numismatic")


def _depth(n: int) -> int:
    s = oracle.generate(n, "cardinal")
    return s.count(" dín ní ") + s.count(" lé ní ")


def run_h1(start=1, end=20000):
    total = 0
    failed = []
    per_class = {fc: [0, 0] for fc in FORM_CLASSES}
    for n in range(start, end + 1):
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


def run_h2_extension(start=1, end=20000):
    failed = []
    for n in range(start, end + 1):
        expected = NFC(oracle.generate(n, "cardinal").replace(" ní ", " l "))
        got = NFC(pipeline.yoruba_extended(n))
        if got != expected:
            failed.append((n, expected, got))
    return failed


def run_h3_shallow(start=1, end=20000):
    total = 0
    failed = []
    for n in range(start, end + 1):
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


def run_h3_deep(start, end):
    total = 0
    errors = []
    for n in range(start, end + 1):
        if _depth(n) < 2:
            continue
        for fc in FORM_CLASSES:
            total += 1
            try:
                surface.surface_extended(n, fc)
            except Exception as e:
                errors.append((n, fc, str(e)))
    return total, errors


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("check", choices=["h1", "h2", "h3shallow", "h3deep"])
    p.add_argument("--start", type=int, default=1)
    p.add_argument("--end", type=int, default=20000)
    args = p.parse_args()

    if args.check == "h1":
        total, failed, per_class = run_h1(args.start, args.end)
        for fc in FORM_CLASSES:
            pc, f = per_class[fc]
            print(f"  {fc:12s} {pc:5d}/{pc+f:5d} pass")
        print(f"TOTAL {total-len(failed)}/{total}")
        for f in failed[:10]:
            print("  FAIL", f)
    elif args.check == "h2":
        r = run_h2_regression()
        print(f"H2-regression: {60-len(r)}/60")
        for f in r[:10]:
            print("  FAIL", f)
        e = run_h2_extension(args.start, args.end)
        n_total = args.end - args.start + 1
        print(f"H2-extension [{args.start}-{args.end}]: {n_total-len(e)}/{n_total}")
        for f in e[:10]:
            print("  FAIL", f)
    elif args.check == "h3shallow":
        total, failed = run_h3_shallow(args.start, args.end)
        print(f"H3-shallow [{args.start}-{args.end}]: {total-len(failed)}/{total}")
        for f in failed[:10]:
            print("  FAIL", f)
    elif args.check == "h3deep":
        total, errors = run_h3_deep(args.start, args.end)
        print(f"H3-deep [{args.start}-{args.end}]: {total-len(errors)}/{total} completed without error")
        for e in errors[:10]:
            print("  ERROR", e)
