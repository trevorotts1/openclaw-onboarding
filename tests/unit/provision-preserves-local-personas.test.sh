#!/usr/bin/env bash
# tests/unit/provision-preserves-local-personas.test.sh
# ─────────────────────────────────────────────────────────────────────────────
# F2.1 acceptance test — client-box updates must NOT destroy client-locally-
# added personas.
#
# Two mechanisms compounded the original defect:
#   (1) reconcile_persona_assets blind-copied the shipped seed
#       persona-categories.json over the workspace copy → a client persona
#       (added by running Skill-22 on the client's OWN book) was DEREGISTERED
#       from the selector's universe (selector universe = categories keys).
#   (2) provision_persona_index gate condition (c) required chunk_count ==
#       manifest EXACTLY → a canonical index carrying the manifest asset PLUS
#       the client's own locally-embedded persona (more chunks) was judged
#       NON-canonical and the whole DB was re-downloaded, DESTROYING the
#       client's persona vectors.
#
# This test proves the F2.1 fix end-to-end:
#   (A) UNION MERGE preserves a box-local persona (origin:local) while seed
#       slugs still win; a box with NO local persona still hashes to the exact
#       canonical persona_set_md5 (byte-identical copy — no drift).
#   (B) The gate treats a canonical+LOCAL-DELTA index (superset) as canonical
#       and SKIPS the re-download — the client persona is not clobbered.
#   (C) The gate still RE-PROVISIONS a genuine SUBSET (same persona set, short
#       index) — the convergence the gate was built for is preserved.
#   (D) The local-row export → re-insert round-trip carries a client persona's
#       embeddings rows across a whole-DB replace.
#
# Fully offline: PROVISION_DRY_RUN=1 stops the gate before any network I/O; the
# export/re-insert helpers operate on local sqlite fixtures only.
# Requires python3 with the stdlib sqlite3 module.
#
# Exit 0 = all checks pass. Exit 1 = one or more failed.
# ─────────────────────────────────────────────────────────────────────────────

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HELPER="$REPO_ROOT/shared-utils/provision-persona-index.sh"
MANIFEST="$REPO_ROOT/shared-utils/prebuilt-index/INDEX-MANIFEST.json"
SK22="$REPO_ROOT/22-book-to-persona-coaching-leadership-system"
SEED_CATS="$SK22/persona-categories.json"

# Canonical values read from the manifest so this test never hard-locks to a
# stale number (mirrors provision-idempotency.test.sh).
CANON_CAT_MD5="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["persona_set_md5"])' "$MANIFEST" 2>/dev/null || echo "")"
MANIFEST_TAG="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["release_tag"])' "$MANIFEST" 2>/dev/null || echo "prebuilt-index-v2.3.0")"
MANIFEST_CHUNKS="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["chunk_count"])' "$MANIFEST" 2>/dev/null || echo "1161")"
MANIFEST_PERSONAS="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["persona_count"])' "$MANIFEST" 2>/dev/null || echo "81")"

PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== provision-preserves-local-personas.test.sh ==="

if [ ! -f "$HELPER" ]; then echo "  FAIL: helper not found at $HELPER"; exit 1; fi
if [ ! -f "$SEED_CATS" ]; then echo "  FAIL: seed categories not found at $SEED_CATS"; exit 1; fi
# shellcheck source=/dev/null
source "$HELPER"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

LOCAL_SLUG="client-only-founder-playbook"

# ─── (A) UNION MERGE ────────────────────────────────────────────────────────
echo "--- (A) union merge preserves a box-local persona; seed slugs still win ---"

# A1: target with a box-local persona key that is NOT in the seed.
TGT_A="$WORK/cats-with-local.json"
python3 - "$SEED_CATS" "$TGT_A" "$LOCAL_SLUG" <<'PY'
import json,sys
seed=json.load(open(sys.argv[1]))
tgt=json.load(open(sys.argv[1]))          # start from the seed shape
slug=sys.argv[3]
# add a client-only persona
tgt.setdefault("personas",{})[slug]={"author":"Client Author","book":"Client Book",
    "domain":["leadership"],"perspective":[],"custom":[]}
# also mutate an existing SEED slug so we can prove the seed value WINS on merge
first=next(iter(seed["personas"]))
tgt["personas"][first]={"author":"TAMPERED","book":"TAMPERED","domain":[],"perspective":[],"custom":[]}
json.dump(tgt, open(sys.argv[2],"w"), indent=2)
print(first)
PY
SEED_FIRST="$(python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print(next(iter(d["personas"])))' "$SEED_CATS")"

STATUS_A="$(_pidx_union_merge_categories "$SEED_CATS" "$TGT_A")"
case "$STATUS_A" in
    MERGED:1) pass "A1: merge reported MERGED:1 (one box-local persona preserved)";;
    *)        fail "A1: expected MERGED:1, got '$STATUS_A'";;
esac

# local persona survived AND is stamped origin:local
LOCAL_KEPT="$(python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));e=d["personas"].get(sys.argv[2]);print("yes" if e else "no")' "$TGT_A" "$LOCAL_SLUG")"
LOCAL_ORIGIN="$(python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print(d["personas"].get(sys.argv[2],{}).get("origin",""))' "$TGT_A" "$LOCAL_SLUG")"
[ "$LOCAL_KEPT" = "yes" ] && pass "A2: box-local persona '$LOCAL_SLUG' PRESERVED in merged categories" || fail "A2: box-local persona lost"
[ "$LOCAL_ORIGIN" = "local" ] && pass "A3: box-local persona stamped origin:local" || fail "A3: origin!=local (got '$LOCAL_ORIGIN')"

# seed value WON for the tampered seed slug
SEED_AUTHOR="$(python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print(d["personas"][sys.argv[2]]["author"])' "$TGT_A" "$SEED_FIRST")"
[ "$SEED_AUTHOR" != "TAMPERED" ] && pass "A4: seed WINS seed slug (tampered author overwritten by seed)" || fail "A4: seed slug still TAMPERED — seed did not win"

# merged set = seed count + 1 local
MERGED_COUNT="$(python3 -c 'import json,sys;print(len(json.load(open(sys.argv[1]))["personas"]))' "$TGT_A")"
EXPECT_COUNT=$((MANIFEST_PERSONAS + 1))
[ "$MERGED_COUNT" = "$EXPECT_COUNT" ] && pass "A5: merged persona count = manifest+1 ($EXPECT_COUNT)" || fail "A5: merged count=$MERGED_COUNT (expected $EXPECT_COUNT)"

# A6: NO local persona → byte-identical copy → canonical md5 preserved
TGT_B="$WORK/cats-no-local.json"
echo '{"categories":"OLD-STUB"}' > "$TGT_B"
STATUS_B="$(_pidx_union_merge_categories "$SEED_CATS" "$TGT_B")"
NOLOCAL_MD5="$(_pidx_md5 "$TGT_B")"
[ "$STATUS_B" = "COPIED" ] && pass "A6a: no-local-persona merge reported COPIED" || fail "A6a: expected COPIED, got '$STATUS_B'"
if [ -n "$CANON_CAT_MD5" ]; then
    [ "$NOLOCAL_MD5" = "$CANON_CAT_MD5" ] && pass "A6b: no-local copy md5 == canonical persona_set_md5 (no drift)" || fail "A6b: md5=$NOLOCAL_MD5 != canonical $CANON_CAT_MD5"
else
    fail "A6b: manifest persona_set_md5 unreadable"
fi

# ─── helpers to build fixture indexes ───────────────────────────────────────
# _mk_index_slugs <db> <total_rows> <n_seed_personas> [extra_local_slug]
# Rows are spread across n_seed_personas seed dirs; when a local slug is given,
# 10 extra rows are added for it (so both the row count AND the distinct-persona
# count exceed the manifest → a genuine client LOCAL DELTA).
_mk_index_slugs() {
    python3 - "$1" "$2" "$3" "${4:-}" <<'PY'
import sqlite3,sys
p,total,nseed,local=sys.argv[1],int(sys.argv[2]),int(sys.argv[3]),sys.argv[4]
c=sqlite3.connect(p)
c.execute("CREATE TABLE embeddings(id TEXT PRIMARY KEY, file_path TEXT, section_number INTEGER, mode TEXT)")
rid=0
for i in range(total):
    slug="seed-%d" % (i % nseed)
    c.execute("INSERT INTO embeddings VALUES(?,?,?,?)",
              (str(rid), f"/ws/coaching-personas/personas/{slug}/f.md", 3, "both")); rid+=1
if local:
    for j in range(10):
        c.execute("INSERT INTO embeddings VALUES(?,?,?,?)",
                  (str(rid), f"/ws/coaching-personas/personas/{local}/f.md", 3, "both")); rid+=1
c.commit(); c.close()
PY
}
_mk_persona_dirs() {
    local d="$1" n="$2"; shift 2
    mkdir -p "$d/personas"
    for i in $(seq 1 "$n"); do mkdir -p "$d/personas/seed-$i"; done
    for s in "$@"; do mkdir -p "$d/personas/$s"; done
}

export PROVISION_DRY_RUN=1

# ─── (B) canonical + LOCAL DELTA index → SKIP (client persona NOT clobbered) ─
echo "--- (B) canonical + local-delta index is treated canonical (superset) → SKIP ---"
DB="$WORK/box-superset"; mkdir -p "$DB"
# manifest chunks spread over manifest personas, PLUS 10 rows for one local persona
_mk_index_slugs "$DB/gemini-index.sqlite" "$MANIFEST_CHUNKS" "$MANIFEST_PERSONAS" "$LOCAL_SLUG"
printf '%s\n' "$MANIFEST_TAG" > "$DB/.prebuilt-index-version"
# manifest persona dirs + 1 local dir = superset
_mk_persona_dirs "$DB" "$MANIFEST_PERSONAS" "$LOCAL_SLUG"
OUTB="$(provision_persona_index "$MANIFEST" "$DB" 2>&1)"
( echo "$OUTB" | grep -qE "already canonical|content-canonical" ) \
    && pass "B1: superset (canonical+local) index recognized canonical → SKIP" \
    || fail "B1: superset index NOT recognized (out: $OUTB)"
echo "$OUTB" | grep -q "NEEDS (re)provision" \
    && fail "B2: superset index wrongly flagged for re-provision (would clobber client persona)" \
    || pass "B2: superset index NOT re-provisioned (client persona preserved)"
echo "$OUTB" | grep -q "client local persona delta preserved" \
    && pass "B3: log names the preserved client local persona delta" \
    || fail "B3: local-delta note missing (out: $OUTB)"

# ─── (C) genuine SUBSET (same persona set, short index) → RE-PROVISION ──────
echo "--- (C) genuine subset (no local delta, short index) still re-provisions ---"
DC="$WORK/box-subset"; mkdir -p "$DC"
SHORT=$(( MANIFEST_CHUNKS - 100 ))
_mk_index_slugs "$DC/gemini-index.sqlite" "$SHORT" "$MANIFEST_PERSONAS" ""
printf '%s\n' "$MANIFEST_TAG" > "$DC/.prebuilt-index-version"
_mk_persona_dirs "$DC" "$MANIFEST_PERSONAS"
OUTC="$(provision_persona_index "$MANIFEST" "$DC" 2>&1)"
echo "$OUTC" | grep -q "NEEDS (re)provision" \
    && pass "C1: subset index triggers NEEDS (re)provision (convergence preserved)" \
    || fail "C1: subset index did NOT re-provision (out: $OUTC)"
echo "$OUTC" | grep -q "chunk-count:${SHORT}!=${MANIFEST_CHUNKS}" \
    && pass "C2: subset reason is exact chunk mismatch (no local delta → exact semantics)" \
    || fail "C2: expected exact chunk-mismatch reason (out: $OUTC)"

unset PROVISION_DRY_RUN

# ─── (D) export → re-insert round-trips client-local persona rows ───────────
echo "--- (D) local-row export → re-insert preserves client persona across a DB replace ---"
DD="$WORK/box-roundtrip"; mkdir -p "$DD"
OLDDB="$DD/old.sqlite"
NEWDB="$DD/new.sqlite"
CATS_D="$DD/persona-categories.json"
# old db: manifest personas + a local persona (10 rows)
_mk_index_slugs "$OLDDB" "$MANIFEST_CHUNKS" "$MANIFEST_PERSONAS" "$LOCAL_SLUG"
# new (freshly-downloaded) canonical db: manifest personas ONLY, no local
_mk_index_slugs "$NEWDB" "$MANIFEST_CHUNKS" "$MANIFEST_PERSONAS" ""
# categories with the local persona tagged origin:local
python3 - "$CATS_D" "$LOCAL_SLUG" <<'PY'
import json,sys
d={"personas":{"seed-0":{"author":"S","book":"B","domain":["leadership"]},
   sys.argv[2]:{"author":"C","book":"CB","domain":["leadership"],"origin":"local"}}}
json.dump(d, open(sys.argv[1],"w"))
PY

EXP="$DD/export.json"
N_EXP="$(_pidx_export_local_rows "$OLDDB" "$CATS_D" "$EXP")"
[ "$N_EXP" = "10" ] && pass "D1: exported 10 client-local persona rows from the old DB" || fail "D1: exported '$N_EXP' rows (expected 10)"

# new DB has ZERO local rows before re-insert
PRE="$(python3 -c 'import sqlite3,sys;c=sqlite3.connect(sys.argv[1]);print(c.execute("SELECT COUNT(*) FROM embeddings WHERE file_path LIKE ?", ("%/"+sys.argv[2]+"/%",)).fetchone()[0])' "$NEWDB" "$LOCAL_SLUG")"
[ "$PRE" = "0" ] && pass "D2: fresh canonical DB has 0 local persona rows pre-reinsert" || fail "D2: pre=$PRE (expected 0)"

N_RE="$(_pidx_reinsert_local_rows "$NEWDB" "$EXP")"
[ "$N_RE" = "10" ] && pass "D3: re-inserted 10 client-local persona rows into the new DB" || fail "D3: re-inserted '$N_RE' (expected 10)"

POST="$(python3 -c 'import sqlite3,sys;c=sqlite3.connect(sys.argv[1]);print(c.execute("SELECT COUNT(*) FROM embeddings WHERE file_path LIKE ?", ("%/"+sys.argv[2]+"/%",)).fetchone()[0])' "$NEWDB" "$LOCAL_SLUG")"
[ "$POST" = "10" ] && pass "D4: client persona rows present in the new DB after re-insert (survived the replace)" || fail "D4: post=$POST (expected 10)"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
    echo "FAIL: $FAIL assertion(s) failed"
    exit 1
fi
echo "PASS: all assertions passed"
exit 0
