#!/usr/bin/env python3
"""Gate H4: round trip between generation and recognition.

For every cell of the paradigm table (value v, form f) and every normalisation
level, reading f with the inverted index built at that level must return exactly
one span, covering the whole of f, that maps to exactly {v}.

Three checks, each exhaustive:
  H4a  isolated:  READ(f) == [tokens(f)] and index[tokens(f)] == {v}
  H4b  context:   the same, with f embedded between two carrier tokens that occur
                  in no index key at that level
  H4c  variants:  each listed variant reads as its value in the configuration with
                  variants, and is not a key of the canonical index
  H4d  cross-class: each cross-class reading (a canonical form of the same value used in
                  another cell's place) reads as its value in that configuration

The table is JSON lines (one row per value) or a sealed run's tables/<backend>.json; from
the latter the recorded variants and cross-class readings are used unless --variants is given.

The reader must be the one the evaluation used. Pass --reader-module to import
normalise() and tokens() from the scoring harness (e.g. score_runs.py). Without
it, a reference re-implementation of the ladder (Table 7 of the manuscript) is
used and the log says so: that run tests the reference, not the harness.

Standard library only. Exit status 0 only if every check passes.

Usage (one run per backend table):
  python3 roundtrip_gate.py --table RUN/tables/pynini.json \
      --reader-module /path/to/score_runs.py --log h4_pynini.log
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

LEVELS = ["L0", "L1", "L2", "L3", "L4", "L4d", "L5", "L5d"]

# --------------------------------------------------------------------------
# Reference normalisation ladder and tokeniser (used only without --reader-module)
# --------------------------------------------------------------------------
# Aligned with the evaluated harness (score_runs.py, the notebook's ladder): the same zero-width set and the
# same eight typographic replacements. A wider map (U+2010 hyphen, primes, other spaces) changes the tokens
# of 36 corpus verses at L3 and above, so it would not be the ladder that produced the sealed results.
_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\ufeff"), None)
_TYPO = {ord("\u2018"): "'", ord("\u2019"): "'", ord("\u201c"): '"', ord("\u201d"): '"',
         ord("\u2013"): "-", ord("\u2014"): "-", ord("\u2212"): "-", ord("\u00a0"): " "}
_TONE = {"̀", "́", "̄"}       # grave, acute, macron
_DOT_BELOW = "̣"


def _nfd_map(text: str, fn) -> str:
    return unicodedata.normalize("NFC", fn(unicodedata.normalize("NFD", text)))


def ref_normalise(text: str, level: str) -> str:
    if level == "L0":
        return text
    t = unicodedata.normalize("NFC", text)                                   # L1
    if level == "L1":
        return t
    t = _nfd_map(t, lambda s: s.replace("̩", _DOT_BELOW).replace("̱", _DOT_BELOW))  # L2
    if level == "L2":
        return t
    t = t.translate(_ZERO_WIDTH).translate(_TYPO)                            # L3
    if level == "L3":
        return t
    t = t.replace("-", "")                                                   # L4
    if level == "L4":
        return t
    if level in ("L4d", "L5d"):
        t = _nfd_map(t, lambda s: s.replace(_DOT_BELOW, ""))
    if level in ("L5", "L5d"):
        t = _nfd_map(t, lambda s: "".join(ch for ch in s if ch not in _TONE))
    return t


_NONWORD = re.compile(r"[^\w\u0300-\u036f\-]+")


def ref_tokens(text: str) -> list[str]:
    # as the harness: word characters, the combining marks U+0300-U+036F and the hyphen; all else splits
    return _NONWORD.sub(" ", text).casefold().split()


def load_reader(path: str | None, norm_name: str, tok_name: str):
    if not path:
        return ref_normalise, ref_tokens, "reference re-implementation (NOT the harness)"
    spec = importlib.util.spec_from_file_location("harness_reader", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    if not hasattr(mod, norm_name) and hasattr(mod, "RUNGS"):
        # score_runs.py: RUNGS[level](text) normalises; tokens(text, rung) normalises and tokenises, and
        # its rung L0 is the identity, so tokens(text, "L0") tokenises already-normalised text
        return (lambda t, lv: mod.RUNGS[lv](t)), (lambda t: mod.tokens(t, "L0")), \
            f"{path}: RUNGS[level](), tokens(text, 'L0')"
    return getattr(mod, norm_name), getattr(mod, tok_name), f"{path}: {norm_name}(), {tok_name}()"


# --------------------------------------------------------------------------
# Index and greedy reader (Algorithms 4.5 and 4.6 of the thesis)
# --------------------------------------------------------------------------
def build_index(pairs, level, normalise, tokens):
    index: dict[tuple, set] = defaultdict(set)
    for v, f in pairs:
        k = tuple(tokens(normalise(f, level)))
        if k:
            index[k].add(v)
    return index


def read(tok: list[str], index: dict, max_len: int) -> list[tuple]:
    spans, i = [], 0
    while i < len(tok):
        m = 0
        for L in range(min(max_len, len(tok) - i), 0, -1):
            if tuple(tok[i:i + L]) in index:
                m = L
                break
        if m:
            spans.append(tuple(tok[i:i + m]))
            i += m
        else:
            i += 1
    return spans


# --------------------------------------------------------------------------
def load_sealed(path):
    """A sealed run's tables/<backend>.json: cells, recorded variants, cross-class readings."""
    t = json.load(open(path, encoding="utf-8"))
    pairs = [(int(k.split("|", 1)[0]), f) for k, f in t["table"].items() if f]
    variants = [(int(v), f) for v, _c, f, *_ in (t.get("variants") or [])]
    cross = [(int(v), f) for v, _c, f, *_ in (t.get("cross_class") or [])]
    return pairs, variants, cross


def load_table(path, value_field, form_fields):
    if str(path).endswith(".json"):
        return load_sealed(path)[0]
    pairs = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            v = int(row[value_field])
            fields = form_fields or [k for k, x in row.items() if k != value_field and isinstance(x, str)]
            for k in fields:
                if row.get(k):
                    pairs.append((v, row[k]))
    return pairs


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--table", required=True, help="paradigm table as JSON lines, one row per value")
    ap.add_argument("--value-field", default="value")
    ap.add_argument("--form-fields", nargs="*", default=None,
                    help="columns holding forms (default: every string column except the value)")
    ap.add_argument("--variants", help='JSON list of {"form": str, "value": int}')
    ap.add_argument("--reader-module", help="path to the scoring harness to import the reader from")
    ap.add_argument("--normalise-name", default="normalise")
    ap.add_argument("--tokens-name", default="tokens")
    ap.add_argument("--carriers", nargs="*", default=["qqqa", "zzzb", "qzqc", "zqzd"],
                    help="candidate carrier tokens; the first two absent from every key are used")
    ap.add_argument("--levels", nargs="*", default=LEVELS)
    ap.add_argument("--log", default="h4_gate.log")
    ap.add_argument("--max-report", type=int, default=20)
    a = ap.parse_args()

    normalise, tokens, reader_desc = load_reader(a.reader_module, a.normalise_name, a.tokens_name)
    pairs = load_table(a.table, a.value_field, a.form_fields)
    variants, cross = [], []
    if a.table.endswith(".json"):
        _, variants, cross = load_sealed(a.table)
    if a.variants:
        variants = [(int(x["value"]), x["form"]) for x in json.load(open(a.variants, encoding="utf-8"))]

    lines = [f"H4 round-trip gate",
             f"table   {a.table}  sha256 {sha256(a.table)}",
             f"cells   {len(pairs)}",
             f"reader  {reader_desc}"]
    if a.variants:
        lines.append(f"variants {a.variants}  sha256 {sha256(a.variants)}  ({len(variants)} forms)")
    elif variants or cross:
        lines.append(f"variants from the table: {len(variants)} recorded variants, {len(cross)} cross-class")
    if not a.reader_module:
        lines.append("WARNING  no --reader-module: this run checks the reference reader only")

    failures, totals = [], defaultdict(lambda: [0, 0])  # key -> [passed, checked]

    def fail(check, level, config, v, f, got):
        failures.append(f"{check} {level} {config} value={v} form={f!r} got={got}")

    for level in a.levels:
        configs = {"canonical": pairs}
        if variants or cross:
            configs["with-variants"] = pairs + variants + cross
        indexes = {c: build_index(p, level, normalise, tokens) for c, p in configs.items()}
        for config, index in indexes.items():
            max_len = max(len(k) for k in index)
            key_tokens = {t for k in index for t in k}
            carriers = [c for c in (tokens(normalise(x, level)) for x in a.carriers)
                        if len(c) == 1 and c[0] not in key_tokens][:2]
            if len(carriers) < 2:
                sys.exit(f"{level} {config}: fewer than two carrier tokens are absent from the index")
            left, right = carriers[0][0], carriers[1][0]
            for v, f in pairs:
                k = tuple(tokens(normalise(f, level)))
                if not k:
                    totals[("H4a", level, config)][1] += 1
                    fail("H4a", level, config, v, f, "empty after normalisation")
                    continue
                # H4a isolated
                got = read(list(k), index, max_len)
                ok = got == [k] and index.get(k) == {v}
                totals[("H4a", level, config)][0] += ok
                totals[("H4a", level, config)][1] += 1
                if not ok:
                    fail("H4a", level, config, v, f, (got, sorted(index.get(k, ()))))
                # H4b in context
                got = read([left, *k, right], index, max_len)
                ok = got == [k]
                totals[("H4b", level, config)][0] += ok
                totals[("H4b", level, config)][1] += 1
                if not ok:
                    fail("H4b", level, config, v, f, got)
        # H4c variants
        # H4d cross-class readings: a canonical form of the same value used in another cell's place
        # (10 as a cardinal written as the numismatic form). It must read as its value; it IS a key of the
        # canonical index by construction, so H4c's "not canonical" condition does not apply to it.
        if cross:
            withv = indexes["with-variants"]
            mx = max(len(k) for k in withv)
            for v, f in cross:
                k = tuple(tokens(normalise(f, level)))
                ok = read(list(k), withv, mx) == [k] and withv.get(k) == {v}
                totals[("H4d", level, "cross-class")][0] += ok
                totals[("H4d", level, "cross-class")][1] += 1
                if not ok:
                    fail("H4d", level, "cross-class", v, f, sorted(withv.get(k, ())))
        if variants:
            canon, withv = indexes["canonical"], indexes["with-variants"]
            mx = max(len(k) for k in withv)
            for v, f in variants:
                k = tuple(tokens(normalise(f, level)))
                ok = read(list(k), withv, mx) == [k] and withv.get(k) == {v} and k not in canon
                totals[("H4c", level, "variants")][0] += ok
                totals[("H4c", level, "variants")][1] += 1
                if not ok:
                    fail("H4c", level, "variants", v, f,
                         ("in canonical index" if k in canon else sorted(withv.get(k, ()))))

    lines.append("")
    lines.append(f"{'check':6} {'level':5} {'config':14} {'passed':>10} / {'checked':<10}")
    for (check, level, config), (p, n) in sorted(totals.items(), key=lambda x: (x[0][0], LEVELS.index(x[0][1]), x[0][2])):
        lines.append(f"{check:6} {level:5} {config:14} {p:>10} / {n:<10}")
    agg = defaultdict(lambda: [0, 0])
    for (check, _, config), (p, n) in totals.items():
        agg[(check, config)][0] += p
        agg[(check, config)][1] += n
    lines.append("")
    for (check, config), (p, n) in sorted(agg.items()):
        lines.append(f"TOTAL {check} {config}: {p}/{n}")
    if failures:
        lines.append("")
        lines.append(f"FAILURES ({len(failures)}; first {a.max_report}):")
        lines.extend("  " + x for x in failures[:a.max_report])
    lines.append("")
    lines.append(f"RESULT {'PASS' if not failures else 'FAIL'}  failures={len(failures)}")
    text = "\n".join(lines)
    Path(a.log).write_text(text + "\n", encoding="utf-8")
    print(text)
    sys.exit(0 if not failures else 1)


if __name__ == "__main__":
    main()
