"""extract_lexicon.py — One-time extraction of phase4.py's lexicon data.

Per the design doc's Option B decision (kept for now): phase4.py remains a
*data* dependency until this JSON file exists, at which point it becomes
the canonical source and phase4.py is no longer imported at runtime.
This script performs that extraction; run it once (or whenever phase4.py's
lexicon changes) to regenerate lexicon.json. Nothing downstream should
import phase4.py after this -- arithmetic.py, phonology.py/rules, and the
lexc build should all read lexicon.json instead.
"""

import json
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "reference"))
import phase4  # noqa: E402

NFC = lambda s: unicodedata.normalize("NFC", s)  # noqa: E731

data = {
    "_comment": "Extracted from phase4.py's lexicon tables. Canonical source "
                "of truth going forward -- phase4.py should not need to be "
                "imported once this file exists, except as a validation "
                "oracle in tests.",
    "anchors": {
        str(k): {"surface": NFC(v["surface"]), "type": v["type"]}
        for k, v in phase4.ANCHORS.items()
    },
    "adjective": {str(k): NFC(v) for k, v in phase4._ADJECTIVE.items()},
    "ordinal": {str(k): NFC(v) for k, v in phase4._ORDINAL.items()},
    "numismatic": {str(k): NFC(v) for k, v in phase4._NUMISMATIC.items()},
    "compound_anchor_forms": {
        str(k): NFC(v) for k, v in phase4._COMPOUND_ANCHOR_FORMS.items()
    },
}

out_path = Path(__file__).parent / "lexicon.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)

print(f"Wrote {out_path}")
print(f"  anchors: {len(data['anchors'])}")
print(f"  adjective: {len(data['adjective'])}")
print(f"  ordinal: {len(data['ordinal'])}")
print(f"  numismatic: {len(data['numismatic'])}")
print(f"  compound_anchor_forms: {len(data['compound_anchor_forms'])}")
