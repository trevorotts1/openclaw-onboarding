#!/usr/bin/env bash
# tests/unit/sop-embeddings-independent-gate.test.sh
# ---------------------------------------------------------------------------
# Proves Bug D's fix: update-skills.sh's Step U6c2 provisions the shipped
# SOP-embeddings asset using its OWN signal (`sop_embeddings` row count vs
# SOP-EMBEDDINGS-MANIFEST.json's sop_count) -- completely INDEPENDENT of
# U6c's content row-count gate.
#
# THE DEFECT UNDER TEST. Both update-skills.sh's U6c ("touch nothing" branch
# when `sops` content is already at/above canonical) and
# ingest-sop-library.sh's own ALREADY-POPULATED SKIP GATE never invoke
# provision_sop_embeddings.py for a box whose SOP content is already fully
# ingested. A box can therefore hold all 2555 SOP rows with a permanently
# EMPTY sop_embeddings table -- semantic SOP search stays keyword-only
# forever, even though the embeddings asset is free, already published, and
# sha256-pinned. This test proves U6c2 closes that gap by reading a signal
# that does not care what U6c decided.
#
# METHOD. Like scripts/test-updater-traps-1-and-3.sh, this does NOT
# reimplement any logic: it extracts the real U6c2 block VERBATIM from
# update-skills.sh between the U6C2-SOP-EMBEDDINGS markers and sources it. If
# those markers drift or vanish the suite fails loudly (exit 2) rather than
# silently testing nothing.
#
# FULLY OFFLINE. The manifest's asset_url is a local file:// path built
# in-process (mirrors tests/unit/provision-sop-embeddings-idempotency.test.py's
# pattern for the same underlying script). Nothing here touches the network,
# a real release, or any real box.
# ---------------------------------------------------------------------------
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UPDATER="$REPO_ROOT/update-skills.sh"
REAL_PROVISION_PY="$REPO_ROOT/shared-utils/sop-embed-once/provision_sop_embeddings.py"

PASS=0
FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ✓ $1"; }
bad() { FAIL=$((FAIL+1)); echo "  ✗ $1"; }

[ -f "$UPDATER" ] || { echo "FATAL: $UPDATER not found"; exit 2; }
[ -f "$REAL_PROVISION_PY" ] || { echo "FATAL: $REAL_PROVISION_PY not found"; exit 2; }

WORK="$(mktemp -d -t u6c2-sop-embed-test-XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

# --- verbatim extraction between markers, mirroring test-updater-traps-1-and-3.sh
extract_block() {
  awk -v b=">>> $1-BEGIN" -v e="<<< $1-END" '
    index($0, b) { p=1; next }
    index($0, e) { p=0 }
    p { print }
  ' "$UPDATER"
}
extract_block "U6C2-SOP-EMBEDDINGS" > "$WORK/u6c2.inc"
if [ ! -s "$WORK/u6c2.inc" ]; then
  echo "FATAL: marker block 'U6C2-SOP-EMBEDDINGS' not found in update-skills.sh (marker drift?)"
  exit 2
fi
{
  echo 'u6c2_block() {'
  cat "$WORK/u6c2.inc"
  echo '}'
} > "$WORK/u6c2-wrapped.sh"
bash -n "$WORK/u6c2-wrapped.sh" || { echo "FATAL: extracted U6c2 block does not parse"; exit 2; }

echo "== static: U6c2 is wired into update-skills.sh and stays advisory =="
grep -q "Step U6c2: SOP-embeddings population check" "$UPDATER" \
  && ok "update-skills.sh contains Step U6c2" || bad "Step U6c2 missing from update-skills.sh"
# The extracted block must NEVER set U6c's stamp-gating failure flag, and
# must never call exit -- this step is advisory only, by contract.
if grep -qE '_U6C_SOPLIB_FAIL[[:space:]]*=' "$WORK/u6c2.inc"; then
  bad "U6c2 block ASSIGNS the U6c stamp-gating failure flag (should be fully independent)"
else
  ok "U6c2 block never assigns U6c's stamp-gating failure flag"
fi
if grep -qE '(^|[^_a-zA-Z])exit[[:space:]]' "$WORK/u6c2.inc"; then
  bad "U6c2 block calls exit (must be advisory-only, never abort the roll)"
else
  ok "U6c2 block never calls exit -- advisory only"
fi

# --- fixture builders ------------------------------------------------------
make_client_db() {  # make_client_db <path> <sop_slugs...>
  # Schema mirrors the real mission-control.db shape (migration 057): `sops`
  # PLUS an already-migrated, empty `sop_embeddings` table -- every real box
  # has both; provision_sop_embeddings.py only INSERTs into sop_embeddings,
  # it does not create the table itself.
  local db="$1"; shift
  python3 - "$db" "$@" <<'PYEOF'
import sqlite3, sys
db, slugs = sys.argv[1], sys.argv[2:]
con = sqlite3.connect(db)
con.executescript("""
CREATE TABLE sops (id TEXT PRIMARY KEY, name TEXT NOT NULL, slug TEXT NOT NULL UNIQUE,
 steps TEXT NOT NULL);
CREATE TABLE sop_embeddings (sop_id TEXT PRIMARY KEY, embedding BLOB NOT NULL,
 embedding_model TEXT NOT NULL DEFAULT 'm', embedding_dims INTEGER NOT NULL DEFAULT 3072,
 embedded_at TEXT NOT NULL DEFAULT (datetime('now')));
""")
for s in slugs:
    sop_id = "sop_" + s.replace("-", "_")
    con.execute("INSERT INTO sops (id,name,slug,steps) VALUES (?,?,?,'[]')", (sop_id, s, s))
con.commit(); con.close()
PYEOF
}

make_shipped_asset() {  # make_shipped_asset <dir> <sop_ids...> ; prints "gz_path sha256"
  local dir="$1"; shift
  python3 - "$dir" "$@" <<'PYEOF'
import gzip, hashlib, shutil, sqlite3, sys
from pathlib import Path
dir_, ids = sys.argv[1], sys.argv[2:]
db_path = str(Path(dir_) / "sop-embeddings.sqlite")
con = sqlite3.connect(db_path)
con.execute("CREATE TABLE sop_embeddings (sop_id TEXT PRIMARY KEY, embedding BLOB NOT NULL, "
            "embedding_model TEXT NOT NULL, embedding_dims INTEGER NOT NULL, embedded_at TEXT NOT NULL)")
blob = b"\x00" * 32
for sop_id in ids:
    con.execute("INSERT INTO sop_embeddings VALUES (?,?,?,?,datetime('now'))",
                (sop_id, blob, "gemini-embedding-2", 3072))
con.commit(); con.close()
gz_path = str(Path(dir_) / "sop-embeddings.sqlite.gz")
with open(db_path, "rb") as fsrc, gzip.open(gz_path, "wb") as fdst:
    shutil.copyfileobj(fsrc, fdst)
sha256 = hashlib.sha256(Path(gz_path).read_bytes()).hexdigest()
print(f"{gz_path} {sha256}")
PYEOF
}

make_manifest() {  # make_manifest <path> <sop_count> <asset_url> <sha256>
  cat > "$1" <<EOF
{
  "model": "gemini-embedding-2",
  "dims": 3072,
  "provider": "gemini",
  "sop_count": $2,
  "release_tag": "fixture-embed-tag",
  "asset_url": "$3",
  "sha256": "$4",
  "asset_rebuild_required": false
}
EOF
}

run_u6c2() {  # run_u6c2 <embed_dir> <db_path> ; runs the extracted block, captures output
  local embed_dir="$1" db="$2"
  (
    # shellcheck source=/dev/null
    source "$WORK/u6c2-wrapped.sh"
    SKILLS_DIR="$WORK/skills-dir-unused"
    # shellcheck disable=SC2034  # read by u6c2_block (dynamically sourced above), not this scope
    EXTRACTED_DIR="$embed_dir/.."
    _U6C_DB="$db"
    # shellcheck disable=SC2034  # read by u6c2_block (dynamically sourced above), not this scope
    LOG_FILE="$WORK/log.txt"
    mkdir -p "$SKILLS_DIR/shared-utils/sop-embed-once"
    cp "$embed_dir/SOP-EMBEDDINGS-MANIFEST.json" "$SKILLS_DIR/shared-utils/sop-embed-once/"
    cp "$REAL_PROVISION_PY" "$SKILLS_DIR/shared-utils/sop-embed-once/"
    u6c2_block
  )
}

count_embeddings() {
  sqlite3 "file:$1?mode=ro" "SELECT COUNT(*) FROM sop_embeddings;" 2>/dev/null || echo -1
}

echo ""
echo "== (1) empty sop_embeddings + populated content -> U6c2 provisions anyway =="
D1="$WORK/case1"; mkdir -p "$D1"
make_client_db "$D1/mission-control.db" fixture-a fixture-b fixture-c
read -r GZ1 SHA1 < <(make_shipped_asset "$D1" sop_fixture_a sop_fixture_b)
make_manifest "$D1/SOP-EMBEDDINGS-MANIFEST.json" 2 "file://$GZ1" "$SHA1"
BEFORE1="$(count_embeddings "$D1/mission-control.db")"
OUT1="$(run_u6c2 "$D1" "$D1/mission-control.db" 2>&1)"
AFTER1="$(count_embeddings "$D1/mission-control.db")"
[ "$BEFORE1" = "0" ] && ok "(1) starts with 0 embedding rows" || bad "(1) expected 0 before, got $BEFORE1"
[ "$AFTER1" = "2" ] && ok "(1) provisioned the 2 shared-library rows despite content already being 'populated'" \
  || { bad "(1) expected 2 embedding rows after U6c2, got $AFTER1"; echo "$OUT1" | sed 's/^/      /'; }
echo "$OUT1" | grep -q "under-populated" && ok "(1) reports under-populated before provisioning" || bad "(1) no under-populated message"

echo ""
echo "== (2) sop_embeddings already at/above manifest sop_count -> SKIP, no re-import =="
D2="$WORK/case2"; mkdir -p "$D2"
make_client_db "$D2/mission-control.db" fixture-a fixture-b
read -r GZ2 SHA2 < <(make_shipped_asset "$D2" sop_fixture_a sop_fixture_b)
make_manifest "$D2/SOP-EMBEDDINGS-MANIFEST.json" 2 "file://$GZ2" "$SHA2"
# Pre-provision once so the box is already canonical.
run_u6c2 "$D2" "$D2/mission-control.db" >/dev/null 2>&1
MID2="$(count_embeddings "$D2/mission-control.db")"
SUM_BEFORE2="$(shasum -a 256 "$D2/mission-control.db" | awk '{print $1}')"
OUT2="$(run_u6c2 "$D2" "$D2/mission-control.db" 2>&1)"
SUM_AFTER2="$(shasum -a 256 "$D2/mission-control.db" | awk '{print $1}')"
[ "$MID2" = "2" ] && ok "(2) pre-provision reached manifest sop_count (2)" || bad "(2) pre-provision did not reach canonical, got $MID2"
[ "$SUM_BEFORE2" = "$SUM_AFTER2" ] && ok "(2) already-canonical box: DB byte-for-byte UNCHANGED on second pass" \
  || bad "(2) DB was modified on an already-canonical box"
echo "$OUT2" | grep -q "SKIP, nothing to provision" && ok "(2) reports an explicit SKIP" || bad "(2) no SKIP message"

echo ""
echo "== (3) no mission-control.db resolved -> informational SKIP, never a crash =="
OUT3="$(run_u6c2 "$D1" "" 2>&1)"; RC3=$?
[ "$RC3" = "0" ] && ok "(3) missing DB: block returns cleanly (rc=0)" || bad "(3) missing DB: rc=$RC3"
echo "$OUT3" | grep -q "no mission-control.db resolved" && ok "(3) reports informational skip" || bad "(3) no informational-skip message"

echo ""
echo "== (4) independence proof: U6c2 never references U6c's row-count variables =="
grep -qE '_U6C_BEFORE|_U6C_CANON' "$WORK/u6c2.inc" \
  && bad "(4) U6c2 reads U6c's content row-count variables (not independent)" \
  || ok "(4) U6c2 reads its OWN signal only (sop_embeddings vs manifest sop_count) -- no dependency on U6c's content gate"

echo ""
echo "----------------------------------------"
echo "  PASS: $PASS    FAIL: $FAIL"
echo "----------------------------------------"
[ "$FAIL" -eq 0 ] || exit 1
