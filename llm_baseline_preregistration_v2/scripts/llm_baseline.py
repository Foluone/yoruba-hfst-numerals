#!/usr/bin/env python3
"""Large language model baseline for Yoruba numerals (manuscript Section 3.8).

Four steps, run in order. The protocol is frozen by `prepare` and must be
deposited publicly (commit or DOI) BEFORE `run` makes the first model call.

  prepare  select items, write prompts and config, and write a hash manifest
           (preregistration.json) over everything that defines the protocol
  verify   recompute the manifest and confirm nothing changed since `prepare`
  run      call the model for every item and condition; resumable; refuses to
           start if the manifest does not verify or the deposit field is empty
  score    score both tasks, rescore the grammar on the same verses, and apply the
           analysis plan (ANALYSIS_PLAN.md): verse-level bootstrap intervals for the
           model-minus-grammar differences and the non-inferiority decisions

Recognition task: every positive test verse of each corpus, plus a seeded sample
of up to --neg-per-corpus negative test verses. Generation task: a seeded sample
of values stratified by recursion depth (default 60/80/80/80 for depth 0..3).

Adapters to check before use (marked ADAPT below): load_gold(), the depth of a
value, and call_model(). The grammar's reader is imported from roundtrip_gate.py
(or from the harness via --reader-module) so both systems are read identically.

Example (sealed runs as gold, the sealed Pynini table, the harness as reader):
  python3 llm_baseline.py prepare --gold RUN_BIBLE=Bible RUN_QURAN=Quran RUN_MENYO=MENYO-20k RUN_BOM=BookOfMormon \
      --table RUN_BIBLE/tables/pynini.json --citation-field "cardinal|citation" \
      --reader-module score_runs.py --out run1 --model "<model id>" --provider anthropic
  # deposit run1/preregistration.json, then put its reference in run1/config.json
  python3 llm_baseline.py run   --out run1
  python3 llm_baseline.py score --out run1 --reader-module score_runs.py
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import random
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import roundtrip_gate as rg  # noqa: E402

PROTOCOL_FILES = ["config.json", "ANALYSIS_PLAN.md", "items_recognition.jsonl", "items_generation.jsonl",
                  "prompts.json", "fewshot.json"]
SCRIPT_FILES = ["llm_baseline.py", "roundtrip_gate.py"]
SHOT_OVERLAP = 0.2                     # share of a shot's five-word sequences found in a test verse that excludes it
MARGINS = {"accuracy": 5.0, "false_reading": 2.0}   # non-inferiority margins, percentage points (ANALYSIS_PLAN.md)
BOOTSTRAP = {"resamples": 4000, "seed": 20261125, "level": 0.95}
DESCRIPTIVE = ["Quran"]                # too few items for a decision; reported without one

PROMPTS = {
    "recognition_system": (
        "You read Yoruba text. List every number that the text expresses in words "
        "(not in digits), with its value as an integer. Count ordinals too: for 'the third' give 3. "
        "Do not count: the word kan when it means 'a' or 'a certain'; words such as ẹnìkan 'someone' "
        "or nǹkan 'something'; words for 'both' or 'all three' (such as méjèèjì); or words for 'once' "
        "or 'twice'. "
        "Reply with JSON only, in the form "
        '{"numbers": [{"words": "<the words as written>", "value": <integer>}]}. '
        'If the text expresses no number in words, reply {"numbers": []}.'),
    "recognition_user": "Text:\n{text}",
    "generation_system": (
        "You write Standard Yoruba. Give the numeral for the number in the form used before a noun "
        "or in counting (for example, 2 is méjì or èjì), as it would be "
        "written in Standard Yoruba orthography with full tone marks and dots below. Reply with "
        'JSON only, in the form {"yoruba": "<numeral>"}.'),
    "generation_user": "Number: {value}",
}


# --------------------------------------------------------------------------
# ADAPT: gold-set loader. Expected output, one dict per verse:
#   {"corpus": str, "verse_id": str, "split": "test"|"dev",
#    "label": "positive"|"negative", "yoruba": str, "values": [int, ...]}
# Excluded verses must be dropped here.
# --------------------------------------------------------------------------
def load_sealed_gold(run: Path, corpus: str) -> list[dict]:
    """Verse rows from a sealed run's gold.json, with the run's own splits. One gold item per distinct value."""
    verses: dict[str, dict] = {}
    for g in json.load(open(run / "gold.json", encoding="utf-8")):
        v = verses.setdefault(g["verse"], {"corpus": corpus, "verse_id": g["verse"], "split": g["split"],
                                           "yoruba": g["window"], "values": []})
        if g["value"] is not None:
            v["values"].append(int(g["value"]))
    for v in verses.values():
        assert len(v["values"]) == len(set(v["values"])), v["verse_id"]
        v["label"] = "positive" if v["values"] else "negative"
    return list(verses.values())


def load_gold(paths: list[str]) -> list[dict]:
    """Each path is a JSON-lines file in the format above, or RUN_DIR=CORPUS for a sealed run."""
    rows = []
    for p in paths:
        if "=" in p and Path(p.split("=", 1)[0], "gold.json").exists():
            run, corpus = p.split("=", 1)
            rows += load_sealed_gold(Path(run), corpus)
            continue
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    r = json.loads(line)
                    if r.get("label") in ("positive", "negative"):
                        rows.append(r)
    return rows


# --------------------------------------------------------------------------
# ADAPT: recursion depth of a value. Default: the table row carries a "depth"
# field; otherwise count operator words in the citation cardinal.
# --------------------------------------------------------------------------
def table_rows(path: str, value_field: str = "value") -> list[dict]:
    """One dict per value: the JSON-lines table, or a sealed tables/<backend>.json pivoted to that shape."""
    if path.endswith(".json"):
        rows: dict[int, dict] = {}
        for k, f in json.load(open(path, encoding="utf-8"))["table"].items():
            v, cell = k.split("|", 1)
            rows.setdefault(int(v), {value_field: int(v)})[cell] = f
        return [rows[v] for v in sorted(rows)]
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def cardinal_pairs(path: str, value_field: str, prefix) -> list[tuple]:
    """(value, form) for the cells credited in generation: those whose name starts with one of the prefixes."""
    pre = (prefix,) if isinstance(prefix, str) else tuple(prefix)
    return [(int(r[value_field]), f) for r in table_rows(path, value_field)
            for c, f in r.items() if c != value_field and c.startswith(pre) and isinstance(f, str) and f]


def depth_of(row: dict, citation_field: str = "cardinal_citation") -> int:
    if "depth" in row:
        return int(row["depth"])
    toks = row.get(citation_field, "").split()
    return sum(t in ("lé", "dín") for t in toks)


# --------------------------------------------------------------------------
# ADAPT: model call. Returns the raw text of the reply.
# --------------------------------------------------------------------------
def call_model(cfg: dict, system: str, messages: list[dict]) -> str:
    prov = cfg["provider"]
    if prov == "anthropic":
        import anthropic  # pip install anthropic
        client = anthropic.Anthropic()
        extra = {} if cfg.get("temperature") is None else {"temperature": cfg["temperature"]}
        r = client.messages.create(model=cfg["model"], max_tokens=cfg["max_tokens"],
                                   system=system, messages=messages, **extra)
        meta = {"model": r.model, "stop": r.stop_reason, "blocks": [getattr(b, "type", "?") for b in r.content],
                "tokens_in": r.usage.input_tokens, "tokens_out": r.usage.output_tokens}
        return "".join(b.text for b in r.content if getattr(b, "type", "") == "text"), meta
    if prov == "openai":
        import openai  # pip install openai
        client = openai.OpenAI()
        extra = {} if cfg.get("temperature") is None else {"temperature": cfg["temperature"]}
        r = client.chat.completions.create(model=cfg["model"], max_tokens=cfg["max_tokens"], **extra,
                                           messages=[{"role": "system", "content": system}, *messages])
        meta = {"model": r.model, "stop": r.choices[0].finish_reason,
                "tokens_in": r.usage.prompt_tokens, "tokens_out": r.usage.completion_tokens}
        return r.choices[0].message.content or "", meta
    if prov == "dry-run":   # pipeline test only: echoes an empty answer
        return ('{"numbers": []}' if "Text:" in messages[-1]["content"] else '{"yoruba": ""}'), {"model": "dry-run"}
    raise ValueError(f"unknown provider {prov}")


# --------------------------------------------------------------------------
def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def manifest(out: Path) -> dict:
    files = {f: sha256_file(out / f) for f in PROTOCOL_FILES}
    here = Path(__file__).resolve().parent
    files.update({f"script/{f}": sha256_file(here / f) for f in SCRIPT_FILES})
    blob = json.dumps(files, sort_keys=True).encode()
    return {"files": files, "protocol_sha256": hashlib.sha256(blob).hexdigest()}


def write_jsonl(p: Path, rows):
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def read_jsonl(p: Path):
    """Rows of a JSON-lines file. A last line cut off by an interrupted write is skipped (run repairs it)."""
    if not p.exists():
        return []
    lines = [l for l in open(p, encoding="utf-8") if l.strip()]
    rows = []
    for n, l in enumerate(lines):
        try:
            rows.append(json.loads(l))
        except json.JSONDecodeError:
            if n == len(lines) - 1:
                break
            raise
    return rows


def parse_json_reply(text: str):
    """The first JSON object in the reply that carries an answer key ("numbers" or "yoruba"), else the first
    JSON object; None if there is none. Text before or after the object (prose, code fences, a second object)
    is ignored."""
    if not text:
        return None
    dec, first = json.JSONDecoder(), None
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _ = dec.raw_decode(text, i)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            if "numbers" in obj or "yoruba" in obj:
                return obj
            first = first if first is not None else obj
    return first


def to_int(x):
    """An answer's value as an integer: 7, 7.0, "7", "7,000", "7 000"; None for anything else."""
    if isinstance(x, bool):
        return None
    if isinstance(x, int):
        return x
    if isinstance(x, float):
        return int(x) if x.is_integer() else None
    if isinstance(x, str):
        t = x.strip().replace(",", "").replace(" ", "").replace("\u00a0", "").replace("_", "")
        if re.fullmatch(r"\d+", t):
            return int(t)
        if re.fullmatch(r"\d+\.0+", t):
            return int(t.split(".")[0])
    return None


# --------------------------------------------------------------------------
def cmd_prepare(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=False)
    rng = random.Random(a.seed)
    gold = [g for g in load_gold(a.gold) if g["split"] == "test"]
    dev = [g for g in load_gold(a.gold) if g["split"] == "dev" and g["label"] == "positive"]

    items = []
    by_corpus = defaultdict(lambda: {"positive": [], "negative": []})
    for g in gold:
        by_corpus[g["corpus"]][g["label"]].append(g)
    for corpus, d in sorted(by_corpus.items()):
        pos = sorted(d["positive"], key=lambda g: g["verse_id"])
        neg = sorted(d["negative"], key=lambda g: g["verse_id"])
        neg = rng.sample(neg, min(a.neg_per_corpus, len(neg)))
        if a.pos_per_corpus:                    # a seeded sample of positive verses (reduced design)
            pos = sorted(rng.sample(pos, min(a.pos_per_corpus, len(pos))), key=lambda g: g["verse_id"])
        for g in pos + sorted(neg, key=lambda g: g["verse_id"]):
            items.append({"id": f"{corpus}:{g['verse_id']}", "corpus": corpus, "label": g["label"],
                          "yoruba": g["yoruba"], "values": sorted(set(g.get("values", [])))})
    write_jsonl(out / "items_recognition.jsonl", items)

    # five-shot examples from the development split, fixed by seed; the words of each
    # answer are the span the grammar reads for that value (empty if it reads none)
    # The words shown are the span the grammar reads for each value, so a shot is kept only if the grammar
    # reads every gold value of the verse: otherwise the exemplar would teach an empty or wrong span (gold
    # noise, a value the verse does not express). Candidates are drawn in seeded order until five pass.
    # A candidate is also skipped if it repeats a test verse, wholly or in large part (SHOT_OVERLAP or more of
    # its five-word sequences occur in some test verse, compared at L5d): the model must not be shown a test item.
    normalise, tokens, _ = rg.load_reader(a.reader_module, "normalise", "tokens")
    ix = rg.build_index(rg.load_table(a.table, a.value_field, None), "L2", normalise, tokens)
    mx = max(len(k) for k in ix)

    def grams(text):
        t = tokens(normalise(text, "L5d"))
        return {tuple(t[i:i + 5]) for i in range(len(t) - 4)} or {tuple(t)}
    test_grams = set().union(*(grams(g["yoruba"]) for g in gold))
    fewshot, skipped = [], []
    pool = sorted(dev, key=lambda g: (g["corpus"], g["verse_id"]))
    for s in rng.sample(pool, len(pool)):
        if len(fewshot) == 5:
            break
        gs = grams(s["yoruba"])
        overlap = len(gs & test_grams) / len(gs)
        if overlap >= SHOT_OVERLAP:
            skipped.append({"corpus": s["corpus"], "verse_id": s["verse_id"], "overlap_with_test": round(overlap, 3)})
            continue
        spans = rg.read(tokens(normalise(s["yoruba"], "L2")), ix, mx)
        words = {next(iter(ix[k])): " ".join(k) for k in spans if len(ix[k]) == 1}
        if not all(v in words for v in s["values"]):
            continue
        fewshot.append({"text": s["yoruba"], "corpus": s["corpus"], "verse_id": s["verse_id"],
                        "overlap_with_test": round(overlap, 3),
                        "answer": {"numbers": [{"words": words[v], "value": v} for v in sorted(set(s["values"]))]}})
    (out / "fewshot.json").write_bytes((json.dumps(fewshot, ensure_ascii=False, indent=1)).encode("utf-8"))

    # generation sample, stratified by depth
    rows = table_rows(a.table, a.value_field)
    strata = defaultdict(list)
    for r in rows:
        strata[depth_of(r, a.citation_field)].append(int(r[a.value_field]))
    quota = dict(zip(range(4), a.gen_quota))
    gen = []
    for dpt in range(4):
        pool = sorted(strata.get(dpt, []))
        for v in sorted(rng.sample(pool, min(quota[dpt], len(pool)))):
            gen.append({"id": f"gen:{v}", "value": v, "depth": dpt})
    write_jsonl(out / "items_generation.jsonl", gen)

    (out / "prompts.json").write_bytes((json.dumps(PROMPTS, ensure_ascii=False, indent=1)).encode("utf-8"))
    plan = Path(a.plan) if a.plan else Path(__file__).resolve().parent / "ANALYSIS_PLAN.md"
    (out / "ANALYSIS_PLAN.md").write_bytes(plan.read_bytes())
    negatives_total = {c: len(d["negative"]) for c, d in sorted(by_corpus.items())}
    positives_total = {c: sum(len(set(g["values"])) for g in d["positive"]) for c, d in sorted(by_corpus.items())}
    # repeat check: a seeded subset of recognition items asked a second time (zero-shot), to measure how far
    # the model's answers vary between identical calls. Its own generator, so the items above are unchanged.
    rep_rng = random.Random(a.seed + 1)
    repeat_ids = sorted(i["id"] for i in rep_rng.sample(items, min(a.repeat_subset, len(items))))
    cfg = {"provider": a.provider, "model": a.model, "temperature": a.temperature, "max_tokens": a.max_tokens,
           "repeat_ids": repeat_ids,
           "conditions": a.conditions, "seed": a.seed, "pos_per_corpus": a.pos_per_corpus,
           "positives_total": positives_total,
           "neg_per_corpus": a.neg_per_corpus, "gen_quota": a.gen_quota,
           "table": Path(os.path.relpath(a.table, out)).as_posix(), "table_sha256": sha256_file(Path(a.table)),
           "variants": a.variants and Path(os.path.relpath(a.variants, out)).as_posix(),
           "variants_sha256": a.variants and sha256_file(Path(a.variants)),
           "value_field": a.value_field, "cardinal_prefixes": a.cardinal_prefix,
           "headline_level": "L2", "generation_level_loose": "L5d",
           "reader": a.reader_module and os.path.basename(a.reader_module),
           "reader_sha256": a.reader_module and sha256_file(Path(a.reader_module)),
           "negatives_total": negatives_total, "shots_skipped_as_test_overlap": skipped,
           "shot_overlap_threshold": SHOT_OVERLAP,
           "margins_points": MARGINS, "bootstrap": BOOTSTRAP, "descriptive_only": DESCRIPTIVE,
           "parse_retries": 1, "deposit_reference": ""}
    (out / "config.json").write_bytes((json.dumps(cfg, indent=1)).encode("utf-8"))
    m = manifest(out)
    m["created"] = datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
    (out / "preregistration.json").write_bytes((json.dumps(m, indent=1)).encode("utf-8"))
    n_pos = sum(i["label"] == "positive" for i in items)
    print(f"prepared {len(items)} verses ({n_pos} positive), {len(gen)} generation values")
    print(f"protocol_sha256 {m['protocol_sha256']}")
    print("Deposit preregistration.json (and the files it hashes) publicly, then set "
          "deposit_reference in config.json via `verify --set-deposit <reference>`.")


def cmd_verify(a, quiet=False):
    out = Path(a.out)
    reg = json.loads((out / "preregistration.json").read_text(encoding="utf-8"))
    cfg_path = out / "config.json"
    if getattr(a, "set_deposit", None):
        # the deposit reference is the one field allowed to change after prepare
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        cfg["deposit_reference"] = a.set_deposit
        cfg_path.write_bytes((json.dumps(cfg, indent=1)).encode("utf-8"))
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    # config.json is hashed as prepare wrote it, with the deposit reference empty (computed in memory: no file)
    probe = json.dumps(dict(cfg, deposit_reference=""), indent=1).encode("utf-8")
    files = {f: (hashlib.sha256(probe).hexdigest() if f == "config.json" else sha256_file(out / f))
             for f in PROTOCOL_FILES}
    here = Path(__file__).resolve().parent
    files.update({f"script/{f}": sha256_file(here / f) for f in SCRIPT_FILES})
    ok = files == reg["files"]
    if not quiet:
        print("manifest", "VERIFIED" if ok else "CHANGED", reg["protocol_sha256"])
        for k in files:
            if files[k] != reg["files"].get(k):
                print("  changed:", k)
    return ok, cfg


def transient(e: Exception) -> bool:
    """Worth retrying: rate limits, overload, server errors, timeouts and dropped connections."""
    status = getattr(e, "status_code", None)
    if status is not None:
        return status in (408, 409, 429) or status >= 500
    name = type(e).__name__
    return any(w in name for w in ("Connection", "Timeout", "RateLimit", "Overloaded", "InternalServer"))


def cmd_run(a):
    out = Path(a.out)
    ok, cfg = cmd_verify(a, quiet=True)
    if not ok:
        sys.exit("protocol changed since prepare; refusing to run")
    if not cfg.get("deposit_reference") and cfg["provider"] != "dry-run":
        sys.exit("deposit_reference is empty: deposit the preregistration before the first call")
    prompts = json.loads((out / "prompts.json").read_text(encoding="utf-8"))
    fewshot = json.loads((out / "fewshot.json").read_text(encoding="utf-8"))
    resp_path = out / "responses.jsonl"
    if resp_path.exists():                       # drop a last line cut off by an interrupted write
        raw = resp_path.read_bytes()
        if raw and not raw.endswith(b"\n"):
            resp_path.write_bytes(raw[:raw.rfind(b"\n") + 1])
    done = {(r["task"], r["condition"], r["id"]) for r in read_jsonl(resp_path)}
    rec = read_jsonl(out / "items_recognition.jsonl")
    gen = read_jsonl(out / "items_generation.jsonl")

    def shots_msgs():
        msgs = []
        for s in fewshot:
            msgs.append({"role": "user", "content": prompts["recognition_user"].format(text=s["text"])})
            msgs.append({"role": "assistant", "content": json.dumps(s["answer"], ensure_ascii=False)})
        return msgs

    jobs = []
    for cond in cfg["conditions"]:
        for it in rec:
            jobs.append(("recognition", cond, it["id"], prompts["recognition_system"],
                         (shots_msgs() if cond == "five-shot" else []) +
                         [{"role": "user", "content": prompts["recognition_user"].format(text=it["yoruba"])}]))
    rec_by_id = {it["id"]: it for it in rec}
    for iid in cfg.get("repeat_ids", []):      # the same zero-shot request again, for the repeat check
        jobs.append(("recognition", "repeat", iid, prompts["recognition_system"],
                     [{"role": "user", "content": prompts["recognition_user"].format(text=rec_by_id[iid]["yoruba"])}]))
    for it in gen:   # generation is zero-shot only
        jobs.append(("generation", "zero-shot", it["id"], prompts["generation_system"],
                     [{"role": "user", "content": prompts["generation_user"].format(value=it["value"])}]))

    with open(resp_path, "a", encoding="utf-8", newline="\n") as fh:
        for n, (task, cond, iid, system, msgs) in enumerate(jobs, 1):
            if (task, cond, iid) in done:
                continue
            attempts, meta = [], []
            for _ in range(1 + cfg["parse_retries"]):
                for backoff in (2, 8, 30, 120):
                    try:
                        text, m = call_model(cfg, system, msgs)
                        break
                    except Exception as e:
                        if not transient(e):     # a missing SDK or key, a wrong model name, a rejected setting
                            sys.exit(f"model call failed, and retrying will not help: {type(e).__name__}: {e}")
                        print(f"  call failed ({type(e).__name__}: {e}); retrying in {backoff}s", file=sys.stderr)
                        time.sleep(backoff)
                else:
                    sys.exit("model calls keep failing (network or rate limit); stopping. Run the same command "
                             "again later: finished items are kept.")
                attempts.append(text)
                meta.append(m)
                if parse_json_reply(text) is not None:
                    break
            fh.write(json.dumps({"task": task, "condition": cond, "id": iid, "attempts": attempts,
                                 "meta": meta, "time": datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")}, ensure_ascii=False) + "\n")
            fh.flush()
            if n % 100 == 0:
                print(f"{n}/{len(jobs)}")
    print(f"responses: {resp_path}  sha256 {sha256_file(resp_path)}")


# --------------------------------------------------------------------------
def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"),) * 3
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return 100 * p, 100 * max(0.0, c - h), 100 * min(1.0, c + h)


def decide(lo, hi, margin):
    """Decision for a difference d = model minus grammar, oriented so that a positive d favours the model,
    from its bootstrap interval [lo, hi] and the non-inferiority margin (ANALYSIS_PLAN.md)."""
    if lo > 0:
        return "model better"
    if lo > -margin:
        return "model not worse (within margin)"
    if hi < 0:
        return "model worse"
    return "inconclusive"


def cmd_score(a):
    out = Path(a.out)
    cfg = json.loads((out / "config.json").read_text(encoding="utf-8"))
    normalise, tokens, desc = rg.load_reader(a.reader_module, a.normalise_name, a.tokens_name)
    if cfg.get("reader_sha256") and (not a.reader_module or sha256_file(Path(a.reader_module)) != cfg["reader_sha256"]):
        sys.exit("the reader is not the one recorded at prepare (config.json reader_sha256)")
    table = str(out / cfg["table"].replace("\\", "/"))       # a folder prepared on Windows
    if sha256_file(Path(table)) != cfg["table_sha256"]:
        sys.exit(f"table changed since prepare: {table}")
    pairs = rg.load_table(table, cfg["value_field"], None)
    variants = []
    if cfg.get("variants"):
        variants = [(int(x["value"]), x["form"]) for x in json.load(open(out / cfg["variants"], encoding="utf-8"))]
    elif table.endswith(".json"):
        _, variants, cross = rg.load_sealed(table)
        variants += cross
    margins = cfg.get("margins_points", MARGINS)
    boot = cfg.get("bootstrap", BOOTSTRAP)
    descriptive = set(cfg.get("descriptive_only", DESCRIPTIVE))

    idx = {}
    for lvl in ("L2", "L5d"):   # canonical configuration, as in the sealed headline runs
        ix = rg.build_index(pairs, lvl, normalise, tokens)
        idx[lvl] = (ix, max(len(k) for k in ix))
    ixv = rg.build_index(pairs + variants, "L5d", normalise, tokens)   # for generation scoring
    idx["L5d+v"] = (ixv, max(len(k) for k in ixv))
    # generation: credited forms are the cells named in cardinal_prefixes (the counting cardinal and the form
    # before a noun); the loose credit adds the recorded variants and drops tone and the dot below
    card = cardinal_pairs(table, cfg["value_field"], cfg.get("cardinal_prefixes", cfg.get("cardinal_prefix", "cardinal")))
    canon_l2 = defaultdict(set)
    for v, f in card:
        canon_l2[v].add(tuple(tokens(normalise(f, "L2"))))
    loose = defaultdict(set)
    for v, f in card + variants:
        loose[v].add(tuple(tokens(normalise(f, "L5d"))))

    def grammar_read(text, lvl="L2"):
        """Spans read and the values they name (a span naming several values names none)."""
        ix, mx = idx[lvl]
        spans = rg.read(tokens(normalise(text, lvl.split("+")[0])), ix, mx)
        return spans, [ix[s] for s in spans], set().union(*[ix[s] for s in spans if len(ix[s]) == 1] or [set()])

    def found_in(words, text):
        """The listed words occur in the verse, compared at L5d (no tone, no dot below, no hyphen)."""
        w = " ".join(tokens(normalise(words or "", "L5d")))
        return bool(w) and f" {w} " in " " + " ".join(tokens(normalise(text, "L5d"))) + " "

    resp, models = {}, defaultdict(int)
    for r in read_jsonl(out / "responses.jsonl"):
        resp[(r["task"], r["condition"], r["id"])] = r["attempts"][-1]
        for m in r.get("meta", []):
            models[m.get("model")] += 1
    expected = ([("recognition", c, it["id"]) for c in cfg["conditions"] for it in read_jsonl(out / "items_recognition.jsonl")]
                + [("recognition", "repeat", i) for i in cfg.get("repeat_ids", [])]
                + [("generation", "zero-shot", it["id"]) for it in read_jsonl(out / "items_generation.jsonl")])
    missing = sum(k not in resp for k in expected)
    if missing and not a.allow_incomplete:
        sys.exit(f"run is incomplete: {missing} of {len(expected)} calls have no response in responses.jsonl. "
                 "Finish `run` first (it resumes where it stopped); a missing reply is not a model error.")

    rec = read_jsonl(out / "items_recognition.jsonl")
    corpora = sorted({it["corpus"] for it in rec})
    neg_total = cfg.get("negatives_total") or {c: 1 for c in corpora}
    report = [f"LLM baseline score  model={cfg['model']}  reader={desc}",
              f"models reported by the API: {dict(models) or 'none recorded'}"]
    if len([m for m in models if m]) > 1:
        report.append("WARNING  more than one model answered: see the meta field of responses.jsonl")
    report.append("")

    # ---- one record per verse and condition
    def verse_record(it, cond):
        text = resp.get(("recognition", cond, it["id"]))
        parsed = parse_json_reply(text) if text is not None else None
        mvals, mfound = set(), set()
        if parsed is not None:
            nums = parsed.get("numbers", []) if isinstance(parsed, dict) else []
            for x in nums if isinstance(nums, list) else []:
                v = to_int(x.get("value")) if isinstance(x, dict) else None
                if v is not None:
                    mvals.add(v)
                    if found_in(x.get("words"), it["yoruba"]):
                        mfound.add(v)
        spans, span_vals, gvals = grammar_read(it["yoruba"])
        gold = set(it["values"])
        r = {"pos": it["label"] == "positive", "unparsed": parsed is None}
        if r["pos"]:
            r.update(n=len(gold), g=len(gold & gvals), m=len(gold & mvals), mw=len(gold & mfound),
                     g_read=len(gvals - {1}), g_hit=len((gvals - {1}) & gold),
                     m_read=len(mvals - {1}), m_hit=len((mvals - {1}) & gold))
        else:
            # primary: a reading of 1 alone is not counted (value 1 is never gold); an unparsed reply counts
            r.update(g_fr=any(sv != {1} for sv in span_vals), m_fr=bool(mvals - {1}) or parsed is None,
                     g_raw=bool(spans), m_raw=bool(mvals) or parsed is None)
        return r

    def rates(recs):
        P = [r for r in recs if r["pos"]]
        Nn = [r for r in recs if not r["pos"]]
        n = sum(r["n"] for r in P)
        f = lambda k: sum(r[k] for r in P)
        out_ = {"n": n, "neg": len(Nn), "unparsed": sum(r["unparsed"] for r in recs)}
        for k in ("g", "m", "mw"):
            out_[k] = 100 * f(k) / n if n else float("nan")
        for k in ("g_fr", "m_fr", "g_raw", "m_raw"):
            out_[k] = 100 * sum(r[k] for r in Nn) / len(Nn) if Nn else float("nan")
        for s_ in ("g", "m"):
            rd = f(f"{s_}_read")
            out_[f"{s_}_prec"] = 100 * f(f"{s_}_hit") / rd if rd else float("nan")
        return out_

    # differences oriented so that positive favours the model
    DIFFS = {"accuracy": lambda R: R["m"] - R["g"], "accuracy, words found": lambda R: R["mw"] - R["g"],
             "false readings without 1": lambda R: R["g_fr"] - R["m_fr"]}
    MARGIN_OF = {"accuracy": margins["accuracy"], "accuracy, words found": margins["accuracy"],
                 "false readings without 1": margins["false_reading"]}

    def pooled(by_c):
        """Accuracy over all positive verses; false readings weighted by each corpus's test negatives."""
        allr = [r for c in by_c for r in by_c[c]]
        R = rates(allr)
        w = {c: neg_total.get(c, 1) for c in by_c}
        W = sum(w.values())
        per = {c: rates(by_c[c]) for c in by_c}
        if cfg.get("pos_per_corpus"):   # positives sampled per corpus: weight accuracy by each corpus's test values
            wp = {c: cfg["positives_total"].get(c, 1) for c in by_c if per[c]["n"]}
            WP = sum(wp.values())
            for k in ("g", "m", "mw"):
                R[k] = sum(wp[c] * per[c][k] for c in wp) / WP
        for k in ("g_fr", "m_fr", "g_raw", "m_raw"):
            R[k] = sum(w[c] * per[c][k] for c in by_c) / W
        return R

    def bootstrap(by_c, stat):
        """stat applied to verse-level resamples, drawn within each corpus."""
        rng = random.Random(boot["seed"])
        return [stat({c: [rs[rng.randrange(len(rs))] for _ in rs] for c, rs in by_c.items()})
                for _ in range(boot["resamples"])]

    def interval(xs):
        xs = sorted(x for x in xs if x == x)
        if not xs:                               # no verses of that kind (possible in a pilot)
            return float("nan"), float("nan")
        a_ = (1 - boot["level"]) / 2
        return xs[int(a_ * len(xs))], xs[int((1 - a_) * len(xs)) - 1]

    f1 = lambda x: f"{x:5.1f}"
    for cond in cfg["conditions"]:
        recs = {c: [verse_record(it, cond) for it in rec if it["corpus"] == c] for c in corpora}
        report.append(f"== Recognition, {cond} (grammar | model; differences are model minus grammar, "
                      f"false readings as grammar minus model, so positive favours the model) ==")
        report.append(f"{'corpus':14} {'values':>6} {'acc g':>6} {'acc m':>6} {'words':>6} {'neg':>5} "
                      f"{'FR g':>5} {'FR m':>5} {'prec g':>6} {'prec m':>6} {'raw FR g':>8} {'raw FR m':>8} {'unparsed':>8}")
        rows = [(c, {c: recs[c]}) for c in corpora] + [("POOLED", recs)]
        for name, sub in rows:
            R = pooled(sub) if name == "POOLED" else rates(sub[name])
            report.append(f"{name:14} {R['n']:>6} {f1(R['g']):>6} {f1(R['m']):>6} {f1(R['mw']):>6} {R['neg']:>5} "
                          f"{R['g_fr']:5.1f} {R['m_fr']:5.1f} {f1(R['g_prec']):>6} {f1(R['m_prec']):>6} "
                          f"{R['g_raw']:8.1f} {R['m_raw']:8.1f} {R['unparsed']:>8}")
        report.append("")
        report.append(f"{'corpus':14} {'measure':26} {'difference':>10} {'95% interval':>18} {'margin':>6}  decision")
        for name, sub in rows:
            stat_R = (lambda res: pooled(res)) if name == "POOLED" else (lambda res, c=name: rates(res[c]))
            R = stat_R(sub)
            draws = bootstrap(sub, stat_R)
            for meas, fn in DIFFS.items():
                lo, hi = interval([fn(D) for D in draws])
                dec = ("no items" if lo != lo else "descriptive" if name in descriptive
                       else decide(lo, hi, MARGIN_OF[meas]))
                report.append(f"{name:14} {meas:26} {fn(R):10.1f} {f'[{lo:.1f}, {hi:.1f}]':>18} "
                              f"{MARGIN_OF[meas]:6.1f}  {dec}")
        report.append("")
    report.append("Columns: acc = gold values read (recall); words = model credited only where its quoted words occur")
    report.append("in the verse (L5d); FR = negative verses with a false reading, a reading of 1 alone not counted and")
    report.append("an unparsed reply counted (primary); raw FR counts everything; prec = read values (other than 1)")
    report.append("that are gold, on positive verses. Pooled FR weights each corpus by its test negatives"
                  + ("; pooled accuracy, by its test gold values (positives were sampled)." if cfg.get("pos_per_corpus") else "."))
    report.append(f"Intervals: verse-level bootstrap within corpus, {boot['resamples']} resamples, seed {boot['seed']}.")
    report.append("Per-corpus decisions are not corrected for multiple comparisons (exploratory); see ANALYSIS_PLAN.md.")
    report.append("")

    # ---- repeat check
    if cfg.get("repeat_ids"):
        def answer(key):
            p_ = parse_json_reply(resp.get(key)) if resp.get(key) is not None else None
            if p_ is None:
                return None
            nums = p_.get("numbers", []) if isinstance(p_, dict) else []
            return frozenset(v for x in (nums if isinstance(nums, list) else [])
                             if isinstance(x, dict) and (v := to_int(x.get("value"))) is not None and v != 1)
        pairs_ = [(answer(("recognition", "zero-shot", i)), answer(("recognition", "repeat", i)))
                  for i in cfg["repeat_ids"]]
        same = sum(x == y for x, y in pairs_)
        p_, lo, hi = wilson(same, len(pairs_))
        report.append(f"== Repeat check: {len(pairs_)} recognition items asked twice, zero-shot, same request ==")
        report.append(f"identical answers (values other than 1; an unparsed reply counts as its own answer): "
                      f"{same}/{len(pairs_)} = {p_:.1f}% [{lo:.1f}, {hi:.1f}]")
        report.append("")

    # ---- generation task
    gen = read_jsonl(out / "items_generation.jsonl")
    report.append("== Generation, zero-shot (scored against the grammar's own table: describes the model only) ==")
    report.append(f"{'depth':>5} {'n':>4} {'canonical L2':>14} {'canon+var L5d':>14} "
                  f"{'other cell':>12} {'in parts':>9} {'other value':>12} {'unread':>7} {'unparsed':>8}")
    detail = []
    for dpt in sorted({g["depth"] for g in gen}) + ["all"]:
        its = gen if dpt == "all" else [g for g in gen if g["depth"] == dpt]
        c = defaultdict(int)
        for it in its:
            text = resp.get(("generation", "zero-shot", it["id"]))
            parsed = parse_json_reply(text) if text is not None else None
            form = parsed.get("yoruba") if isinstance(parsed, dict) else None
            if not form or not isinstance(form, str):
                cls = "unparsed"
            else:
                k2 = tuple(tokens(normalise(form, "L2")))
                k5 = tuple(tokens(normalise(form, "L5d")))
                spans_, _, vals = grammar_read(form, "L5d+v")
                if k2 in canon_l2[it["value"]]:
                    cls = "canonical"
                elif k5 in loose[it["value"]]:
                    cls = "variant_or_untoned"
                elif len(spans_) > 1:          # a phrase the grammar reads only in parts (e.g. 8000 ó lé 811)
                    cls = "read_in_parts"
                elif vals and it["value"] not in vals:
                    cls = "other_value"
                elif it["value"] in vals:      # a generated form of the value, but in another cell
                    cls = "other_cell"
                else:
                    cls = "unread"
            c[cls] += 1
            if dpt == "all":
                detail.append({"value": it["value"], "depth": it["depth"], "output": form, "class": cls})
        n = len(its)
        loose_n = c["canonical"] + c["variant_or_untoned"]
        report.append(f"{str(dpt):>5} {n:>4} {c['canonical']:>14} {loose_n:>14} "
                      f"{c['other_cell']:>12} {c['read_in_parts']:>9} {c['other_value']:>12} {c['unread']:>7} {c['unparsed']:>8}")
    write_jsonl(out / "generation_scored.jsonl", detail)
    # blind adjudication sheet: every output that is not canonical, in seeded random order, without its class
    adj = [d for d in detail if d["class"] not in ("canonical", "unparsed")]
    random.Random(boot["seed"]).shuffle(adj)
    with open(out / "generation_adjudication.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["item", "number", "model output", "judgement (standard / acceptable variant / wrong)", "note"])
        for i, d in enumerate(adj, 1):
            w.writerow([f"G{i:03d}", d["value"], d["output"], "", ""])
    write_jsonl(out / "generation_adjudication_key.jsonl",
                [{"item": f"G{i:03d}", **d} for i, d in enumerate(adj, 1)])
    report.append("")
    report.append(f"{len(adj)} non-canonical outputs go to blind speaker adjudication: generation_adjudication.csv "
                  "(key: generation_adjudication_key.jsonl, not for the speaker).")
    text = "\n".join(report)
    (out / "score_report.txt").write_bytes((text + "\n").encode("utf-8"))
    print(text)


def main():
    for stream in (sys.stdout, sys.stderr):   # Windows consoles default to a code page without Yoruba letters
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--gold", nargs="+", required=True)
    p.add_argument("--table", required=True)
    p.add_argument("--variants")
    p.add_argument("--value-field", default="value")
    p.add_argument("--citation-field", default="cardinal_citation",
                   help='column with the citation cardinal ("cardinal|citation" for a sealed table)')
    p.add_argument("--cardinal-prefix", nargs="+", default=["cardinal", "adjective"],
                   help="columns whose name starts with one of these hold forms credited in generation")
    p.add_argument("--reader-module", help="the scoring harness, so the few-shot words are read as in scoring")
    p.add_argument("--out", required=True)
    p.add_argument("--provider", choices=["anthropic", "openai", "dry-run"], required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--max-tokens", type=int, default=8192)
    p.add_argument("--temperature", type=float, default=None,
                   help="sampling temperature; omitted from the request by default (some models reject it)")
    p.add_argument("--repeat-subset", type=int, default=300,
                   help="recognition items asked a second time, zero-shot, to measure answer variation")
    p.add_argument("--seed", type=int, default=20261124)
    p.add_argument("--neg-per-corpus", type=int, default=2000)
    p.add_argument("--pos-per-corpus", type=int, default=0,
                   help="sample this many positive test verses per corpus (0: all of them)")
    p.add_argument("--conditions", nargs="+", default=["zero-shot", "five-shot"], choices=["zero-shot", "five-shot"])
    p.add_argument("--plan", help="analysis plan to copy into the run folder (default scripts/ANALYSIS_PLAN.md)")
    p.add_argument("--gen-quota", type=int, nargs=4, default=[60, 80, 80, 80])
    v = sub.add_parser("verify")
    v.add_argument("--out", required=True)
    v.add_argument("--set-deposit")
    r = sub.add_parser("run")
    r.add_argument("--out", required=True)
    s = sub.add_parser("score")
    s.add_argument("--out", required=True)
    s.add_argument("--reader-module")
    s.add_argument("--normalise-name", default="normalise")
    s.add_argument("--tokens-name", default="tokens")
    s.add_argument("--allow-incomplete", action="store_true",
                   help="score although some calls have no response (they count as unparsed); for testing only")
    a = ap.parse_args()
    {"prepare": cmd_prepare, "verify": lambda a: cmd_verify(a), "run": cmd_run, "score": cmd_score}[a.cmd](a)


if __name__ == "__main__":
    main()
