"""build_lexicon_lexc.py — Generate lexicon.lexc from lexicon.json.

Per Option B, the recursive anchor-decomposition arithmetic stays in Python
(arithmetic.py) -- this lexc file is NOT a compounding grammar. Its job is
to be the formal, machine-verifiable declaration of the closed morpheme
inventory: every legitimate anchor/paradigm citation form, tagged with its
numeric value and category on the upper (lexical) side. This is what makes
the lexicon itself part of the compiled HFST artifact rather than just
Python data floating outside it, and it's what a future parse-direction
or Option A migration would build on.

Each entry: +Category+Val<N>[+Type]:surface_form # ;
e.g.        +Anchor+Val9+Primitive:ẹ̀sán # ;
            +Adjective+Val5:márùn-ún # ;
"""

import json
from pathlib import Path

HERE = Path(__file__).parent
with open(HERE / "lexicon.json", encoding="utf-8") as f:
    lex = json.load(f)

TYPE_TAG = {
    "primitive": "+Primitive",
    "multiplicative": "+Multiplicative",
    "subtractive": "+Subtractive",
}

entries = []  # (upper_tag_string, surface_form)
multichar_symbols = set()

for val_str, info in lex["anchors"].items():
    tag = f"+Anchor+Val{val_str}{TYPE_TAG[info['type']]}"
    entries.append((tag, info["surface"]))
    multichar_symbols.update(["+Anchor", f"+Val{val_str}", TYPE_TAG[info["type"]]])

for category in ("adjective", "ordinal", "numismatic"):
    cat_tag = "+" + category.capitalize()
    for val_str, surface in lex[category].items():
        tag = f"{cat_tag}+Val{val_str}"
        entries.append((tag, surface))
        multichar_symbols.update([cat_tag, f"+Val{val_str}"])

for val_str, surface in lex["compound_anchor_forms"].items():
    tag = f"+CompoundAnchor+Val{val_str}"
    entries.append((tag, surface))
    multichar_symbols.update(["+CompoundAnchor", f"+Val{val_str}"])

lines = []
lines.append("Multichar_Symbols")
for sym in sorted(multichar_symbols):
    lines.append(f"  {sym}")
lines.append("")
lines.append("LEXICON Root")
for tag, surface in entries:
    lines.append(f"  {tag}:{surface} # ;")

out_path = HERE / "lexicon.lexc"
with open(out_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

print(f"Wrote {out_path}: {len(entries)} entries, {len(multichar_symbols)} multichar symbols")
