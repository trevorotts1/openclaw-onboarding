#!/usr/bin/env bash
# tests/unit/sop-library-update-path-ingest.test.sh
# ---------------------------------------------------------------------------
# Proves the SOP V2 library is actually WIRED INTO THE UPDATE PATH and that the
# ingester is safe to run on every box on every roll.
#
# THE DEFECT UNDER TEST. The updater synced FILES but never populated the SOP
# DATABASE: a box ran the update, received every file, reported a green
# "update complete", and still held a demo-fixture-sized `sops` table (24 rows
# where the canonical library is 2555). The ingestion script existed but was
# invoked by NO update path -- and the one place it was reachable
# (run-full-install.sh phase 6i, via update-skills.sh's CC refresh) had its
# failure swallowed into an advisory "⚠ reported errors" line.
#
# FULLY OFFLINE. `curl` is stubbed on $PATH and serves a LOCAL fixture asset.
# Nothing here touches the network, a real release, or any real box.
#
# Run: bash tests/unit/sop-library-update-path-ingest.test.sh
# ---------------------------------------------------------------------------
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INGEST_SH="$REPO_ROOT/32-command-center-setup/scripts/ingest-sop-library.sh"
UPDATER="$REPO_ROOT/update-skills.sh"

PASS=0
FAIL=0
ok()   { PASS=$((PASS+1)); echo "  ✓ $1"; }
bad()  { FAIL=$((FAIL+1)); echo "  ✗ $1"; }

TMP="$(mktemp -d -t sop-lib-test-XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

LIB_RECORDS=12
STARTER_ROWS=3
CANON=$LIB_RECORDS   # fixture canonical population (12 distinct slugs -> 12 rows)

# ---------------------------------------------------------------------------
# Fixture: a 12-record library asset + a DB holding only a 3-row demo seed.
# ---------------------------------------------------------------------------
build_fixture() {
  local dir="$1" starters="${2:-$STARTER_ROWS}"
  mkdir -p "$dir"
  python3 - "$dir" "$LIB_RECORDS" "$starters" <<'PYEOF'
import json, sqlite3, gzip, os, sys
d, n, starters = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
recs = [{
    "slug": f"fixture-sop-{i:03d}", "name": f"Fixture SOP {i}", "description": "d",
    "version": 1, "department": "ops", "cadence": "daily", "source_role": "r",
    "confidence": 0.9, "confidence_tier": "high", "estimated_minutes": 10,
    "time_of_day": "am", "source_file_url": "u", "task_keywords": "k",
    "steps": ["a", "b"], "success_criteria": "s", "prerequisites": None,
    "persona_hints": [], "template_vars_used": [], "layer_version": "v2",
    "dependencies_upstream": [], "dependencies_downstream": [],
} for i in range(n)]
p = os.path.join(d, "lib.jsonl")
with open(p, "w") as fh:
    fh.write("\n".join(json.dumps(r) for r in recs) + "\n")
with open(p, "rb") as fh, gzip.open(os.path.join(d, "sops-library-v2.jsonl.gz"), "wb") as g:
    g.write(fh.read())
db = os.path.join(d, "mission-control.db")
con = sqlite3.connect(db)
con.executescript("""
CREATE TABLE sops (id TEXT PRIMARY KEY, name TEXT NOT NULL, slug TEXT NOT NULL UNIQUE,
 description TEXT, version INTEGER DEFAULT 1, department TEXT, task_keywords TEXT,
 steps TEXT NOT NULL, success_criteria TEXT, persona_hints TEXT, source TEXT,
 deleted_at TEXT, created_at TEXT, updated_at TEXT);
CREATE TABLE _migrations (id TEXT PRIMARY KEY, name TEXT);
CREATE TABLE sop_embeddings (sop_id TEXT PRIMARY KEY, embedding BLOB NOT NULL,
 embedding_model TEXT NOT NULL DEFAULT 'm', embedding_dims INTEGER NOT NULL DEFAULT 3072,
 embedded_at TEXT NOT NULL DEFAULT (datetime('now')));
""")
# "client-authored" rows must survive every ingest -- id-space disjoint from the
# library, exactly like the real CC autoSeedStarterSOPs boot seed.
for i in range(starters):
    con.execute("INSERT INTO sops (id,name,slug,steps) VALUES (?,?,?,'[]')",
                (f"starter_{i}", f"Starter {i}", f"starter-{i}"))
con.commit(); con.close()
PYEOF
  # manifest pinned to the FIXTURE asset (sha256 computed from it)
  local sha
  sha="$(shasum -a 256 "$dir/sops-library-v2.jsonl.gz" | awk '{print $1}')"
  cat > "$dir/SOP-LIBRARY-MANIFEST.json" <<EOF
{
  "asset": "sops-library-v2.jsonl.gz",
  "release_tag": "fixture-tag",
  "sha256": "$sha",
  "canonical_sop_count": $CANON
}
EOF
}

# curl stub: serves the local fixture instead of the network.
# STUB_MODE=ok    -> copy the fixture asset
# STUB_MODE=fail  -> simulate a network/asset outage (non-zero, no file)
# STUB_MODE=corrupt -> serve a corrupted asset (sha256 mismatch)
make_curl_stub() {
  local bindir="$1" fixture="$2"
  mkdir -p "$bindir"
  cat > "$bindir/curl" <<EOF
#!/usr/bin/env bash
touch "$bindir/.curl-was-called"
out=""
while [ \$# -gt 0 ]; do
  case "\$1" in
    -o) out="\$2"; shift 2 ;;
    *) shift ;;
  esac
done
case "\${STUB_MODE:-ok}" in
  fail)    echo "curl: (22) simulated outage" >&2; exit 22 ;;
  corrupt) printf 'CORRUPTED-NOT-A-GZIP' > "\$out"; exit 0 ;;
  *)       cp "$fixture" "\$out"; exit 0 ;;
esac
EOF
  chmod +x "$bindir/curl"
}

count_sops() { sqlite3 "file:$1?mode=ro" "SELECT COUNT(*) FROM sops;" 2>/dev/null || echo -1; }

run_ingest() {  # run_ingest <dir> ; echoes rc
  local dir="$1"; shift
  local bindir="$dir/bin"
  make_curl_stub "$bindir" "$dir/sops-library-v2.jsonl.gz"
  PATH="$bindir:$PATH" \
  MISSION_CONTROL_DB="$dir/mission-control.db" \
  SOP_LIB_MANIFEST="$dir/SOP-LIBRARY-MANIFEST.json" \
    bash "$INGEST_SH" testclient > "$dir/out.log" 2>&1
  echo $?
}

echo "== (a) under-populated box reaches canonical population =="
A="$TMP/a"; build_fixture "$A"
BEFORE_A="$(count_sops "$A/mission-control.db")"
RC_A="$(run_ingest "$A")"
AFTER_A="$(count_sops "$A/mission-control.db")"
EXPECT_A=$(( LIB_RECORDS + STARTER_ROWS ))
[ "$BEFORE_A" = "$STARTER_ROWS" ] && ok "FAIL-BEFORE: box starts demo-fixture-sized ($BEFORE_A rows, canonical $CANON)" \
  || bad "expected $STARTER_ROWS starting rows, got $BEFORE_A"
[ "$RC_A" = "0" ] && ok "ingest exits 0" || { bad "ingest rc=$RC_A"; sed 's/^/      /' "$A/out.log" | tail -8; }
[ "$AFTER_A" = "$EXPECT_A" ] \
  && ok "PASS-AFTER: reached canonical population ($BEFORE_A → $AFTER_A rows = $LIB_RECORDS library + $STARTER_ROWS pre-existing)" \
  || bad "expected $EXPECT_A rows after ingest, got $AFTER_A"
[ "$(sqlite3 "$A/mission-control.db" "SELECT COUNT(*) FROM sops WHERE id LIKE 'starter_%';")" = "$STARTER_ROWS" ] \
  && ok "pre-existing (client-authored / boot-seed) rows PRESERVED, not clobbered" \
  || bad "pre-existing rows were lost"

echo "== (b) re-run is idempotent (no duplicates) =="
RC_B="$(SOP_LIB_FORCE=1 run_ingest "$A")"
AFTER_B="$(count_sops "$A/mission-control.db")"
[ "$RC_B" = "0" ] && ok "forced re-ingest exits 0" || bad "forced re-ingest rc=$RC_B"
[ "$AFTER_B" = "$EXPECT_A" ] \
  && ok "IDEMPOTENT: forced re-ingest left the count identical ($AFTER_A → $AFTER_B, zero duplicates)" \
  || bad "re-ingest changed the count: $AFTER_A → $AFTER_B (duplicates!)"
DUPES="$(sqlite3 "$A/mission-control.db" "SELECT COUNT(*) FROM (SELECT slug FROM sops GROUP BY slug HAVING COUNT(*)>1);")"
[ "$DUPES" = "0" ] && ok "zero duplicate slugs in the table" || bad "$DUPES duplicated slug(s)"

echo "== (c) an already-populated box is left completely intact =="
C="$TMP/c"; build_fixture "$C"
# bring it to canonical first
run_ingest "$C" >/dev/null
FULL_C="$(count_sops "$C/mission-control.db")"
SUM_BEFORE="$(shasum -a 256 "$C/mission-control.db" | awk '{print $1}')"
rm -f "$C/bin/.curl-was-called"
RC_C="$(run_ingest "$C")"
SUM_AFTER="$(shasum -a 256 "$C/mission-control.db" | awk '{print $1}')"
[ "$RC_C" = "0" ] && ok "populated box: ingest exits 0" || bad "populated box rc=$RC_C"
[ ! -f "$C/bin/.curl-was-called" ] \
  && ok "populated box: NO download attempted (skip gate short-circuits before any network I/O)" \
  || bad "populated box still downloaded the asset"
[ "$SUM_BEFORE" = "$SUM_AFTER" ] \
  && ok "populated box: DB byte-for-byte UNCHANGED (not clobbered, not re-ingested)" \
  || bad "populated box DB was modified ($SUM_BEFORE -> $SUM_AFTER)"
grep -q "SKIP — this box already holds" "$C/out.log" \
  && ok "populated box: reports an explicit SKIP" || bad "no SKIP message"
[ "$(count_sops "$C/mission-control.db")" = "$FULL_C" ] && ok "populated box: row count preserved ($FULL_C)" || bad "row count changed"

echo "== (d) unavailable / corrupt ingestion FAILS LOUD (never green) =="
D="$TMP/d"; build_fixture "$D"
BEFORE_D="$(count_sops "$D/mission-control.db")"
RC_D="$(STUB_MODE=fail run_ingest "$D")"
[ "$RC_D" != "0" ] && ok "network/asset outage => NON-ZERO exit (rc=$RC_D), never a green result" \
  || bad "outage still exited 0 — this is the false-green defect"
[ "$(count_sops "$D/mission-control.db")" = "$BEFORE_D" ] \
  && ok "outage left the DB untouched ($BEFORE_D rows)" || bad "DB mutated on a failed ingest"

E="$TMP/e"; build_fixture "$E"
RC_E="$(STUB_MODE=corrupt run_ingest "$E")"
[ "$RC_E" != "0" ] && ok "corrupt asset (sha256 mismatch) => NON-ZERO exit (rc=$RC_E)" \
  || bad "corrupt asset exited 0"
grep -q "sha256 mismatch" "$E/out.log" && ok "corrupt asset: sha256 hard gate names the mismatch" \
  || bad "no sha256 mismatch message"
[ "$(count_sops "$E/mission-control.db")" = "$STARTER_ROWS" ] \
  && ok "corrupt asset left the DB untouched" || bad "DB mutated on a corrupt asset"

echo "== (f) the updater actually WIRES this in and gates on it =="
grep -q "Step U6c: SOP V2 LIBRARY INGESTION" "$UPDATER" \
  && ok "update-skills.sh contains Step U6c" || bad "Step U6c missing from update-skills.sh"
grep -q 'bash "\$_U6C_INGEST_SH"' "$UPDATER" \
  && ok "Step U6c invokes ingest-sop-library.sh" || bad "Step U6c never invokes the ingester"
grep -q '_U6C_SOPLIB_FAIL=1' "$UPDATER" \
  && ok "Step U6c latches a failure flag" || bad "no failure latch"
grep -qF '${_U6C_SOPLIB_FAIL:-0}" -eq 1' "$UPDATER" \
  && ok "the failure latch feeds the content-completeness gate (stamp withheld, exit 1)" \
  || bad "failure latch is never consumed by the gate"
# the gate block must sit in the STAMP-GATING set, not the advisory set
if awk '/CONTENT-COMPLETENESS GATE FAILED/{found=1} END{exit !found}' "$UPDATER"; then
  ok "content-completeness gate exists and exits non-zero without stamping"
else
  bad "content-completeness gate not found"
fi

echo "== (g) ingestion performs ZERO embedding API calls (no client cost) =="
grep -qE 'genai|generativelanguage|api_key|GEMINI_API_KEY' "$INGEST_SH" \
  && bad "ingester references an embedding API/key" \
  || ok "ingest-sop-library.sh contains no embedding API/key reference"
grep -q "ZERO embedding" "$INGEST_SH" \
  && ok "ingester states the zero-cost contract explicitly" || bad "no zero-cost statement"
grep -q "NOTE (operator)" "$A/out.log" \
  && ok "ingester surfaces an explicit operator note that ingested rows are UNEMBEDDED" \
  || bad "no unembedded-rows operator note"

echo ""
echo "----------------------------------------"
echo "  PASS: $PASS    FAIL: $FAIL"
echo "----------------------------------------"
[ "$FAIL" -eq 0 ] || exit 1
