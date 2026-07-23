#!/usr/bin/env bash
# tests/unit/sop-library-membership-check.test.sh
# U120: proves SOP library skip gate verifies canonical membership by identifier
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INGEST_SH="$REPO_ROOT/32-command-center-setup/scripts/ingest-sop-library.sh"

PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); echo "  ok $1"; }
bad()  { FAIL=$((FAIL+1)); echo "  FAIL $1"; }

TMP="$(mktemp -d -t sop-member-test-XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

LIB_RECORDS=12; STARTER_ROWS=3; CANON=$LIB_RECORDS

build_non_library_fixture() {
  local dir="$1" total="${2:-$CANON}"
  mkdir -p "$dir"
  python3 - "$dir" "$LIB_RECORDS" "$total" <<'PYEOF'
import json, sqlite3, gzip, os, sys
d, n, total = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
recs = [{"slug": f"fixture-sop-{i:03d}", "name": f"Fixture SOP {i}", "description": "d", "version": 1, "department": "ops", "cadence": "daily", "source_role": "r", "confidence": 0.9, "confidence_tier": "high", "estimated_minutes": 10, "time_of_day": "am", "source_file_url": "u", "task_keywords": "k", "steps": ["a", "b"], "success_criteria": "s", "prerequisites": None, "persona_hints": [], "template_vars_used": [], "layer_version": "v2", "dependencies_upstream": [], "dependencies_downstream": []} for i in range(n)]
p = os.path.join(d, "lib.jsonl")
with open(p, "w") as fh: fh.write("\n".join(json.dumps(r) for r in recs) + "\n")
with open(p, "rb") as fh, gzip.open(os.path.join(d, "sops-library-v2.jsonl.gz"), "wb") as g: g.write(fh.read())
db = os.path.join(d, "mission-control.db")
con = sqlite3.connect(db)
con.executescript("CREATE TABLE sops (id TEXT PRIMARY KEY, name TEXT NOT NULL, slug TEXT NOT NULL UNIQUE, description TEXT, version INTEGER DEFAULT 1, department TEXT, task_keywords TEXT, steps TEXT NOT NULL, success_criteria TEXT, persona_hints TEXT, source TEXT, deleted_at TEXT, created_at TEXT, updated_at TEXT); CREATE TABLE _migrations (id TEXT PRIMARY KEY, name TEXT); CREATE TABLE sop_embeddings (sop_id TEXT PRIMARY KEY, embedding BLOB NOT NULL, embedding_model TEXT NOT NULL DEFAULT 'm', embedding_dims INTEGER NOT NULL DEFAULT 3072, embedded_at TEXT NOT NULL DEFAULT (datetime('now')));")
for i in range(total): con.execute("INSERT INTO sops (id,name,slug,steps) VALUES (?,?,?,'[]')", (f"starter_{i}", f"Starter {i}", f"starter-{i}"))
con.commit(); con.close()
PYEOF
  local sha; sha="$(shasum -a 256 "$dir/sops-library-v2.jsonl.gz" | awk '{print $1}')"
  printf '{"asset":"sops-library-v2.jsonl.gz","release_tag":"fixture-tag","sha256":"%s","canonical_sop_count":%d,"probe_sop_ids":["sop_fixture_sop_000"]}\n' "$sha" "$CANON" > "$dir/SOP-LIBRARY-MANIFEST.json"
}

build_canonical_fixture() {
  local dir="$1"
  mkdir -p "$dir"
  python3 - "$dir" "$LIB_RECORDS" "$STARTER_ROWS" <<'PYEOF'
import json, sqlite3, gzip, os, sys
d, n, starters = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
recs = [{"slug": f"fixture-sop-{i:03d}", "name": f"Fixture SOP {i}", "description": "d", "version": 1, "department": "ops", "cadence": "daily", "source_role": "r", "confidence": 0.9, "confidence_tier": "high", "estimated_minutes": 10, "time_of_day": "am", "source_file_url": "u", "task_keywords": "k", "steps": ["a", "b"], "success_criteria": "s", "prerequisites": None, "persona_hints": [], "template_vars_used": [], "layer_version": "v2", "dependencies_upstream": [], "dependencies_downstream": []} for i in range(n)]
p = os.path.join(d, "lib.jsonl")
with open(p, "w") as fh: fh.write("\n".join(json.dumps(r) for r in recs) + "\n")
with open(p, "rb") as fh, gzip.open(os.path.join(d, "sops-library-v2.jsonl.gz"), "wb") as g: g.write(fh.read())
db = os.path.join(d, "mission-control.db")
con = sqlite3.connect(db)
con.executescript("CREATE TABLE sops (id TEXT PRIMARY KEY, name TEXT NOT NULL, slug TEXT NOT NULL UNIQUE, description TEXT, version INTEGER DEFAULT 1, department TEXT, task_keywords TEXT, steps TEXT NOT NULL, success_criteria TEXT, persona_hints TEXT, source TEXT, deleted_at TEXT, created_at TEXT, updated_at TEXT); CREATE TABLE _migrations (id TEXT PRIMARY KEY, name TEXT); CREATE TABLE sop_embeddings (sop_id TEXT PRIMARY KEY, embedding BLOB NOT NULL, embedding_model TEXT NOT NULL DEFAULT 'm', embedding_dims INTEGER NOT NULL DEFAULT 3072, embedded_at TEXT NOT NULL DEFAULT (datetime('now')));")
for i in range(n): con.execute("INSERT INTO sops (id,name,slug,steps) VALUES (?,?,?,'[]')", (f"sop_fixture_sop_{i:03d}", f"Fixture SOP {i}", f"fixture-sop-{i:03d}"))
for i in range(starters): con.execute("INSERT INTO sops (id,name,slug,steps) VALUES (?,?,?,'[]')", (f"starter_{i}", f"Starter {i}", f"starter-{i}"))
con.commit(); con.close()
PYEOF
  local sha; sha="$(shasum -a 256 "$dir/sops-library-v2.jsonl.gz" | awk '{print $1}')"
  printf '{"asset":"sops-library-v2.jsonl.gz","release_tag":"fixture-tag","sha256":"%s","canonical_sop_count":%d,"probe_sop_ids":["sop_fixture_sop_000"]}\n' "$sha" "$CANON" > "$dir/SOP-LIBRARY-MANIFEST.json"
}

make_curl_stub() {
  local bindir="$1" fixture="$2"
  mkdir -p "$bindir"
  cat > "$bindir/curl" <<CURLSTUB
#!/usr/bin/env bash
touch "$bindir/.curl-was-called"
out=""; while [ \$# -gt 0 ]; do case "\$1" in -o) out="\$2"; shift 2 ;; *) shift ;; esac; done
case "\${STUB_MODE:-ok}" in
  fail) echo "curl: (22) simulated outage" >&2; exit 22 ;;
  corrupt) printf 'CORRUPTED-NOT-A-GZIP' > "\$out"; exit 0 ;;
  *) cp "$fixture" "\$out"; exit 0 ;;
esac
CURLSTUB
  chmod +x "$bindir/curl"
}

count_sops() { sqlite3 "file:$1?mode=ro" "SELECT COUNT(*) FROM sops;" 2>/dev/null || echo -1; }
count_members() { sqlite3 "file:$1?mode=ro" "SELECT COUNT(*) FROM sops WHERE id LIKE 'sop\_%' ESCAPE '\';" 2>/dev/null || echo -1; }

run_ingest() {
  local dir="$1"
  local bindir="$dir/bin"
  make_curl_stub "$bindir" "$dir/sops-library-v2.jsonl.gz"
  PATH="$bindir:$PATH" MISSION_CONTROL_DB="$dir/mission-control.db" SOP_LIB_MANIFEST="$dir/SOP-LIBRARY-MANIFEST.json" bash "$INGEST_SH" testclient > "$dir/out.log" 2>&1
  echo $?
}

echo "== (a) non-library DB at canonical count does NOT skip =="
A="$TMP/a"; build_non_library_fixture "$A" "$CANON"
BEFORE_A="$(count_sops "$A/mission-control.db")"
MEMBER_BEFORE="$(count_members "$A/mission-control.db")"
RC_A="$(run_ingest "$A")"
AFTER_A="$(count_sops "$A/mission-control.db")"

[ "$BEFORE_A" = "$CANON" ] && ok "FAIL-BEFORE: $BEFORE_A rows (>= canonical $CANON) -- ALL non-library" || bad "expected $CANON, got $BEFORE_A"
[ "$MEMBER_BEFORE" = "0" ] && ok "FAIL-BEFORE: ZERO canonical-membership rows" || bad "expected 0, got $MEMBER_BEFORE"
[ "$RC_A" = "0" ] && ok "ingest exits 0 (download proceeds)" || { bad "rc=$RC_A"; sed 's/^/      /' "$A/out.log" | tail -8; }
[ "$AFTER_A" -gt "$BEFORE_A" ] && ok "PASS-AFTER: box GAINED rows ($BEFORE_A -> $AFTER_A)" || bad "no gain ($BEFORE_A -> $AFTER_A)"
grep -q "canonical-members" "$A/out.log" && ok "log: membership count" || bad "no membership count in log"
grep -q "non-library source" "$A/out.log" && ok "log: non-library source message" || bad "no non-library message"

echo "== (b) canonically-populated DB correctly skips =="
B="$TMP/b"; build_canonical_fixture "$B"
run_ingest "$B" >/dev/null
FULL_B="$(count_sops "$B/mission-control.db")"
MEMBER_FULL="$(count_members "$B/mission-control.db")"
SUM_BEFORE="$(shasum -a 256 "$B/mission-control.db" | awk '{print $1}')"
rm -f "$B/bin/.curl-was-called"
RC_B="$(run_ingest "$B")"
SUM_AFTER="$(shasum -a 256 "$B/mission-control.db" | awk '{print $1}')"

EXPECT_B=$((LIB_RECORDS + STARTER_ROWS))
[ "$FULL_B" = "$EXPECT_B" ] && ok "canonical: $FULL_B rows = $LIB_RECORDS lib + $STARTER_ROWS starters" || bad "expected $EXPECT_B, got $FULL_B"
[ "$MEMBER_FULL" = "$CANON" ] && ok "canonical: $MEMBER_FULL membership = canonical $CANON" || bad "expected $CANON, got $MEMBER_FULL"
[ "$RC_B" = "0" ] && ok "canonical: ingest exits 0" || bad "rc=$RC_B"
[ ! -f "$B/bin/.curl-was-called" ] && ok "canonical: NO download (skip gate)" || bad "downloaded"
[ "$SUM_BEFORE" = "$SUM_AFTER" ] && ok "canonical: DB UNCHANGED" || bad "DB modified"
grep -q "membership verified" "$B/out.log" && ok "canonical: membership verified" || bad "no verification"

echo "== (c) SOP_LIB_FORCE=1 bypasses membership gate =="
C="$TMP/c"; build_non_library_fixture "$C" "$CANON"
BEFORE_C="$(count_sops "$C/mission-control.db")"
RC_C="$(SOP_LIB_FORCE=1 run_ingest "$C")"
AFTER_C="$(count_sops "$C/mission-control.db")"
[ "$RC_C" = "0" ] && ok "force: ingest exits 0" || bad "rc=$RC_C"
[ "$AFTER_C" -gt "$BEFORE_C" ] && ok "force: library downloaded" || bad "no increase"

echo "== (d) under-populated (total < canonical) still downloads =="
D="$TMP/d"; build_non_library_fixture "$D" "3"
BEFORE_D="$(count_sops "$D/mission-control.db")"
RC_D="$(run_ingest "$D")"
AFTER_D="$(count_sops "$D/mission-control.db")"
EXPECT_D=$((3 + LIB_RECORDS))
[ "$RC_D" = "0" ] && ok "under: ingest exits 0" || bad "rc=$RC_D"
[ "$AFTER_D" = "$EXPECT_D" ] && ok "under: $EXPECT_D rows (was $BEFORE_D)" || bad "expected $EXPECT_D, got $AFTER_D"

echo ""
echo "PASS: $PASS  FAIL: $FAIL"
[ "$FAIL" -eq 0 ] || exit 1
