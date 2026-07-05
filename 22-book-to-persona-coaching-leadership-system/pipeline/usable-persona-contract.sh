#!/bin/bash
# usable-persona-contract.sh — v1.0.0
#
# Skill 22 — the ONE shared "is this persona actually usable on this box?"
# contract. A book is only a real persona when ALL THREE legs are present in
# the WORKSPACE:
#
#   1. BLUEPRINT   — personas/<slug>/persona-blueprint.md exists and is non-empty
#   2. CATEGORIES  — <slug> is a key under .personas in persona-categories.json
#                    (without it, list_available_personas() cannot see the
#                    persona, so the selector's universe excludes it)
#   3. INDEX ROWS  — >= 1 row in the Gemini embedding index (gemini-index.sqlite,
#                    table `embeddings`) whose file_path is under
#                    coaching-personas/personas/<slug>/ (without it the persona
#                    is matchable-but-vector-less: Layer-5 degrades to keyword
#                    overlap and Stage-C retrieval never surfaces it)
#
# This is the fail-closed gate modelled on Skill 23 SOP-07's
# assert_persona_grounded(): a caller that cannot prove all three legs MUST NOT
# treat the book as processed. It is deliberately implemented ONCE and called
# from every consumer (persona-inbox-watcher.sh success branch;
# add-persona-from-source.sh terminal check) so the contract has exactly one
# source of truth.
#
# USAGE:
#   usable-persona-contract.sh <coaching-personas-base-dir> <slug> [db_path]
#
#   <coaching-personas-base-dir>  the coaching-personas dir that holds
#                                 personas/ and persona-categories.json
#   <slug>                        the persona slug to verify
#   [db_path]                     optional explicit gemini-index.sqlite path;
#                                 env PERSONA_INDEX_DB also honored; otherwise a
#                                 small candidate list is probed.
#
# EXIT CODES (distinct so callers/tests can tell WHICH leg is missing):
#   0  usable — all three legs present
#   2  blueprint missing or empty
#   3  categories key missing
#   4  zero index rows for the slug
#   5  usage error (bad args)
#
# Prints a one-line PASS/FAIL diagnostic per leg to stderr; no stdout on success
# other than the final "USABLE" marker (callers may ignore stdout entirely).

set -uo pipefail

_uc_err() { printf '%s\n' "$*" >&2; }

BASE="${1:-}"
SLUG="${2:-}"
DB_ARG="${3:-}"

if [ -z "$BASE" ] || [ -z "$SLUG" ]; then
    _uc_err "usable-persona-contract: usage: $0 <coaching-personas-base-dir> <slug> [db_path]"
    exit 5
fi

PERSONAS_DIR="$BASE/personas"
CATEGORIES_JSON="$BASE/persona-categories.json"
BLUEPRINT="$PERSONAS_DIR/$SLUG/persona-blueprint.md"

_ok=true

# ── Leg 1: blueprint present and non-empty ───────────────────────────────────
if [ -s "$BLUEPRINT" ]; then
    _uc_err "usable-persona-contract[$SLUG]: PASS leg1 blueprint ($BLUEPRINT)"
else
    _uc_err "usable-persona-contract[$SLUG]: FAIL leg1 blueprint missing/empty ($BLUEPRINT)"
    _ok=false
    _fail_code="${_fail_code:-2}"
fi

# ── Leg 2: categories key present ────────────────────────────────────────────
# A well-formed categories entry is a key under .personas. We only assert
# PRESENCE here (schema-lint is the publisher's job); absence = invisible to the
# selector universe.
_cat_present() {
    CAT_JSON_ENV="$CATEGORIES_JSON" SLUG_ENV="$SLUG" python3 - <<'PY'
import json, os, sys
path = os.environ["CAT_JSON_ENV"]
slug = os.environ["SLUG_ENV"]
try:
    with open(path) as f:
        data = json.load(f)
except (OSError, ValueError):
    sys.exit(1)
personas = data.get("personas")
if not isinstance(personas, dict):
    sys.exit(1)
sys.exit(0 if slug in personas else 1)
PY
}
if _cat_present; then
    _uc_err "usable-persona-contract[$SLUG]: PASS leg2 categories key present"
else
    _uc_err "usable-persona-contract[$SLUG]: FAIL leg2 categories key absent ($CATEGORIES_JSON)"
    _ok=false
    _fail_code="${_fail_code:-3}"
fi

# ── Leg 3: >= 1 index row for the slug ───────────────────────────────────────
# Resolve the embedding DB. embedding_engine.py writes it under
# WORKSPACE_ROOT/data/coaching-personas/gemini-index.sqlite, which is NOT always
# co-located with <base> (on VPS <base> is master-files/coaching-personas but
# the DB lives under workspace/data/coaching-personas). Probe a small candidate
# list; first existing wins.
_resolve_db() {
    local c
    for c in \
        "$DB_ARG" \
        "${PERSONA_INDEX_DB:-}" \
        "$BASE/gemini-index.sqlite" \
        "$HOME/.openclaw/workspace/data/coaching-personas/gemini-index.sqlite" \
        "/data/.openclaw/workspace/data/coaching-personas/gemini-index.sqlite"
    do
        [ -n "$c" ] && [ -f "$c" ] && { printf '%s' "$c"; return 0; }
    done
    return 1
}

_index_rows() {
    local db="$1"
    DB_ENV="$db" SLUG_ENV="$SLUG" python3 - <<'PY'
import os, sqlite3, sys
db = os.environ["DB_ENV"]
slug = os.environ["SLUG_ENV"]
try:
    conn = sqlite3.connect(db, timeout=10.0)
    cur = conn.cursor()
    # Parameterized LIKE. The trailing slash after the slug prevents a prefix
    # slug (foo) from matching a sibling (foo-bar): '/personas/foo/' is not a
    # substring of '/personas/foo-bar/'. Slugs are kebab-case [a-z0-9-] so they
    # carry no LIKE wildcards.
    pattern = "%/coaching-personas/personas/{}/%".format(slug)
    cur.execute(
        "SELECT COUNT(*) FROM embeddings WHERE file_path LIKE ?",
        (pattern,),
    )
    n = cur.fetchone()[0]
    conn.close()
except sqlite3.Error:
    sys.exit(2)  # table/DB unusable -> treat as zero rows (fail-closed)
print(int(n))
sys.exit(0 if n and n > 0 else 1)
PY
}

if _DB="$(_resolve_db)"; then
    if _rows="$(_index_rows "$_DB")"; then
        _uc_err "usable-persona-contract[$SLUG]: PASS leg3 index rows=$_rows ($_DB)"
    else
        _uc_err "usable-persona-contract[$SLUG]: FAIL leg3 zero index rows ($_DB)"
        _ok=false
        _fail_code="${_fail_code:-4}"
    fi
else
    _uc_err "usable-persona-contract[$SLUG]: FAIL leg3 no gemini-index.sqlite found (probed base/workspace/VPS candidates)"
    _ok=false
    _fail_code="${_fail_code:-4}"
fi

if [ "$_ok" = "true" ]; then
    echo "USABLE $SLUG"
    exit 0
fi
exit "${_fail_code:-2}"
