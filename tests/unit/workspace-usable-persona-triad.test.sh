#!/usr/bin/env bash
# tests/unit/workspace-usable-persona-triad.test.sh
# ─────────────────────────────────────────────────────────────────────────────
# F1.2 (FDN-5) — the WORKSPACE triad-equivalent that add-persona-from-source.sh
# runs at its terminal phase. FDN-5 does NOT ship its own contract helper: it
# reuses the ONE shared, fail-closed contract from FDN-4
# (22-…/pipeline/usable-persona-contract.sh, exit 0 = all three legs present).
# This test drives that shared script directly with the SAME semantics the
# wrapper's thin shim uses: `usable-persona-contract.sh <base> <slug>`.
#
# (The renamed sibling test tests/unit/usable-persona-contract.test.sh — from
# FDN-4 — covers the shared helper's own per-leg exit codes + the inbox-watcher
# processed/ gate. This file asserts the F1.2 "registered but not embedded"
# silent-failure class specifically, from the workspace-triad caller's angle.)
#
# Proves:
#   (A) all three legs present (blueprint + categories key + >=1 index row) => PASS
#   (B) blueprint + categories key but ZERO index rows (Phase-5 embed failed)
#       => FAIL. This is the exact case orchestrator.py now propagates as
#       EMBED_FAILED (8) and add-persona-from-source.sh refuses to mark
#       fleet-publish pending on.
#   (C) blueprint missing => FAIL.  (D) categories key missing => FAIL.
#   (E) index rows for a DIFFERENT slug only => FAIL (no cross-slug credit).
#
# Hermetic: no network, no Gemini key. Leg 3 points the shared script at a
# throwaway sqlite fixture via the PERSONA_INDEX_DB override.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONTRACT="$REPO_ROOT/22-book-to-persona-coaching-leadership-system/pipeline/usable-persona-contract.sh"

PASS=0; FAIL=0
pass() { echo "  PASS: $*"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $*"; FAIL=$((FAIL+1)); }

[ -f "$CONTRACT" ] || { echo "FATAL: missing shared contract $CONTRACT"; exit 2; }

SB="$(mktemp -d -t upt-test.XXXXXX)"
trap 'rm -rf "$SB"' EXIT

PERSONA_DIR="$SB/coaching-personas"
SLUG="fixture-author-fixture-book"
OTHER="someone-else-other-book"

# verify <slug> — runs the shared contract as the wrapper's shim does; returns
# the script's exit status (0 = all three legs present, nonzero = a leg missing).
verify() { bash "$CONTRACT" "$PERSONA_DIR" "$1" >/dev/null 2>&1; }

mk_blueprint() {  # create personas/<slug>/persona-blueprint.md
    mkdir -p "$PERSONA_DIR/personas/$1"
    printf '# Blueprint %s\n\nBody.\n' "$1" > "$PERSONA_DIR/personas/$1/persona-blueprint.md"
}

mk_categories() {  # write persona-categories.json with the given slugs as keys
    PC_OUT="$PERSONA_DIR/persona-categories.json" PC_SLUGS="$*" python3 - <<'PY'
import json, os
out = os.environ["PC_OUT"]
slugs = os.environ["PC_SLUGS"].split()
os.makedirs(os.path.dirname(out), exist_ok=True)
data = {"schemaVersion": "1.1", "domainTags": {}, "perspectiveTags": {},
        "personas": {s: {"author": "A", "book": "B", "domain": ["leadership"],
                          "perspective": [], "custom": []} for s in slugs}}
json.dump(data, open(out, "w"), indent=2)
PY
}

mk_index() {  # build a sqlite index; args = slugs that get >=1 embeddings row
    DB="$SB/gemini-index.sqlite" DB_SLUGS="$*" python3 - <<'PY'
import os, sqlite3
db = os.environ["DB"]; slugs = os.environ["DB_SLUGS"].split()
if os.path.exists(db):
    os.remove(db)
conn = sqlite3.connect(db)
conn.execute("""CREATE TABLE embeddings (
    id TEXT PRIMARY KEY, file_path TEXT, chunk_index INTEGER, content TEXT,
    vector BLOB, last_updated REAL, provider TEXT, model TEXT, dim INTEGER)""")
for s in slugs:
    fp = f"/x/coaching-personas/personas/{s}/persona-blueprint.md"
    conn.execute("INSERT INTO embeddings(id, file_path, chunk_index, content) "
                 "VALUES (?,?,?,?)", (f"{s}#0", fp, 0, "chunk"))
conn.commit(); conn.close()
PY
    export PERSONA_INDEX_DB="$SB/gemini-index.sqlite"
}

# ── (A) all three legs present => PASS ───────────────────────────────────────
mk_blueprint "$SLUG"
mk_categories "$SLUG"
mk_index "$SLUG"
if verify "$SLUG"; then
    pass "(A) all three legs present -> contract PASSES (exit 0)"
else
    fail "(A) expected PASS with blueprint+categories+index rows present"
fi

# ── (B) blueprint + categories but ZERO index rows => FAIL (EMBED_FAILED case) ─
mk_index "$OTHER"   # index has rows, but NOT for $SLUG
if verify "$SLUG"; then
    fail "(B) expected FAIL: registered-but-not-embedded must not pass"
else
    pass "(B) vector-less persona (Phase-5 embed failed) -> contract FAILS nonzero"
fi

# ── (C) blueprint missing => FAIL ────────────────────────────────────────────
rm -f "$PERSONA_DIR/personas/$SLUG/persona-blueprint.md"
mk_index "$SLUG"
if verify "$SLUG"; then
    fail "(C) expected FAIL: missing blueprint must not pass"
else
    pass "(C) missing blueprint -> contract FAILS nonzero"
fi
mk_blueprint "$SLUG"  # restore for later cases

# ── (D) categories key missing => FAIL ───────────────────────────────────────
mk_categories "$OTHER"   # $SLUG not a key
mk_index "$SLUG"
if verify "$SLUG"; then
    fail "(D) expected FAIL: unregistered persona must not pass"
else
    pass "(D) missing persona-categories.json key -> contract FAILS nonzero"
fi

# ── (E) index rows only for a DIFFERENT slug => FAIL (no cross-slug credit) ───
mk_categories "$SLUG"
mk_index "$OTHER"
if verify "$SLUG"; then
    fail "(E) expected FAIL: another slug's rows must not satisfy leg 3"
else
    pass "(E) only-other-slug index rows -> contract FAILS nonzero"
fi

echo ""
echo "── workspace-usable-persona-triad: $PASS passed, $FAIL failed ──"
[ "$FAIL" -eq 0 ] || exit 1
