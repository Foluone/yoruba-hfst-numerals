#!/usr/bin/env bash
# setup_hfst.sh — obtain the real Helsinki Finite-State Toolkit without root.
#
# Why this exists: this project targets literal HFST (hfst-lexc, hfst-twolc,
# hfst-xfst, hfst-lookup, plus the `hfst` Python bindings), not a substitute
# library. Standard `apt-get install hfst` requires root and this sandbox
# (and possibly your deployment environment) doesn't have it. `apt-get
# download` + `dpkg-deb -x` fetches and unpacks the .deb files without ever
# needing dpkg's system-wide install step or root privileges, which is
# sufficient for our purposes (we only need the binaries + shared libraries
# on PATH/LD_LIBRARY_PATH, not a system-registered package).
#
# This directory (default: /tmp/hfst_local) is expected to be EPHEMERAL --
# re-run this script at the start of any new session/environment before
# building or running the HFST artifacts in this project. It is idempotent:
# safe to re-run, skips work if already extracted.
#
# Usage:
#   source setup_hfst.sh          # sets PATH/LD_LIBRARY_PATH/PYTHONPATH in
#                                  # the CURRENT shell (needed for hfst-* and
#                                  # `import hfst` to work)
#   ./setup_hfst.sh                # just does the extraction, prints the
#                                  # env vars to export yourself

set -euo pipefail

HFST_DIR="${HFST_DIR:-/tmp/hfst_local}"
EXTRACTED="$HFST_DIR/extracted"

if [ ! -x "$EXTRACTED/usr/bin/hfst-lexc" ]; then
    echo "Fetching HFST packages (no root required)..." >&2
    mkdir -p "$HFST_DIR"
    cd "$HFST_DIR"
    apt-get download hfst libhfst53 python3-hfst
    mkdir -p "$EXTRACTED"
    for pkg in *.deb; do
        dpkg-deb -x "$pkg" "$EXTRACTED"
    done
    echo "Extracted to $EXTRACTED" >&2
else
    echo "Already extracted at $EXTRACTED (skipping fetch)" >&2
fi

export PATH="$EXTRACTED/usr/bin:$PATH"
export LD_LIBRARY_PATH="$EXTRACTED/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}"
export PYTHONPATH="$EXTRACTED/usr/lib/python3/dist-packages:${PYTHONPATH:-}"

echo "PATH, LD_LIBRARY_PATH, PYTHONPATH updated for this shell." >&2
echo "Verify with: hfst-xfst --version   and   python3 -c 'import hfst; print(hfst.HfstTransducer)'" >&2
