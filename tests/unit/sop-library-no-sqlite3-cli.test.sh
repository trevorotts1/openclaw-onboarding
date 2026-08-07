#!/usr/bin/env bash
# tests/unit/sop-library-no-sqlite3-cli.test.sh
# ---------------------------------------------------------------------------
# Proves the fix for a live 2026-08 Hostinger VPS finding: the shared base
# image ghcr.io/hostinger/hvps-openclaw:latest (the shared base across the
# Hostinger VPS fleet) ships libsqlite3-0 (the LIBRARY) but NOT the `sqlite3`
# CLI BINARY. ingest-sop-library.sh's population-verification used to shell
# out to that CLI; "command not found" went to stderr (swallowed by
# `2>/dev/null`) and the accompanying `|| echo 0` silently substituted a
# FALSE ZERO for "the query never ran". The post-ingest gate then read that
# false zero as "the ingest produced 0 rows" and FATALed (exit 7) a run that
# had actually landed all 2,640 rows -- independently confirmed the same
# night via python3's stdlib sqlite3 module against the exact same database,
# against a canonical threshold of 2,555.
#
# THE FIX. python3's stdlib sqlite3 module (always present alongside python3,
# which this script already hard-depends on for its manifest reader) is now
# the PRIMARY path for every row-count read; the sqlite3 CLI is kept only as
# a fallback. True "neither tool available" prints the literal, distinguish-
# able sentinel SQLITE_UNAVAILABLE and FATALs with an honest message -- NEVER
# a numeric 0.
#
# METHOD. A "clean bin" directory is built containing ONLY the binaries this
# script actually needs (python3, curl-stub, shasum, gunzip, tr, wc, date,
# cp, mktemp, rm, dirname) resolved from the real PATH -- WITHOUT sqlite3 --
# and PATH is set to EXACTLY that directory (no `:$PATH` suffix) for the
# ingest subprocess, so the real sqlite3 CLI (present on this dev/CI
# machine) is genuinely unreachable, reproducing the VPS condition. The
# test's own verification oracle (count_sops_via_python) runs OUTSIDE that
# restricted PATH, in the test's normal environment.
#
# FULLY OFFLINE. `curl` is stubbed on the restricted PATH and serves a LOCAL
# fixture asset. Nothing here touches the network, a real release, or any
# real box.
# ---------------------------------------------------------------------------
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INGEST_SH="$REPO_ROOT/32-command-center-setup/scripts/ingest-sop-library.sh"

PASS=0
FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ✓ $1"; }
bad() { FAIL=$((FAIL+1)); echo "  ✗ $1"; }

[ -f "$INGEST_SH" ] || { echo "FATAL: $INGEST_SH not found"; exit 2; }

TMP="$(mktemp -d -t sop-lib-no-cli-test-XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

LIB_RECORDS=12
STARTER_ROWS=1
CANON=$LIB_RECORDS

# ---------------------------------------------------------------------------
# Fixture: a $LIB_RECORDS-record library asset + a DB holding only
# $STARTER_ROWS pre-existing row(s) -- under-populated, so ingest actually runs.
# ---------------------------------------------------------------------------
build_fixture() {
  local dir="$1"
  mkdir -p "$dir"
  python3 - "$dir" "$LIB_RECORDS" "$STARTER_ROWS" <<'PYEOF'
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
for i in range(starters):
    con.execute("INSERT INTO sops (id,name,slug,steps) VALUES (?,?,?,'[]')",
                (f"starter_{i}", f"Starter {i}", f"starter-{i}"))
con.commit(); con.close()
PYEOF
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
make_curl_stub() {
  local bindir="$1" fixture="$2"
  cat > "$bindir/curl" <<EOF
#!/usr/bin/env bash
out=""
while [ \$# -gt 0 ]; do
  case "\$1" in
    -o) out="\$2"; shift 2 ;;
    *) shift ;;
  esac
done
cp "$fixture" "\$out"
exit 0
EOF
  chmod +x "$bindir/curl"
}

# build_clean_bin <bindir> <fixture_dir> <include_sqlite3:0|1> <include_python3:0|1>
# Builds a PATH-restricted bin dir carrying ONLY what ingest-sop-library.sh
# needs, resolved from THIS shell's real PATH, with sqlite3/python3 included
# or excluded on demand. No `:$PATH` suffix is ever used at the call site, so
# nothing outside this directory is reachable.
build_clean_bin() {
  local bindir="$1" fixture_dir="$2" want_sqlite3="$3" want_python3="$4"
  mkdir -p "$bindir"
  local tool
  for tool in bash env shasum sha256sum awk gunzip tr wc date cp mktemp rm dirname mkdir cat basename sed sleep; do
    local real
    real="$(command -v "$tool" 2>/dev/null || true)"
    [ -n "$real" ] && ln -sf "$real" "$bindir/$tool"
  done
  if [ "$want_python3" = "1" ]; then
    local realpy
    realpy="$(command -v python3 2>/dev/null || true)"
    [ -n "$realpy" ] && ln -sf "$realpy" "$bindir/python3"
  fi
  if [ "$want_sqlite3" = "1" ]; then
    local realsq
    realsq="$(command -v sqlite3 2>/dev/null || true)"
    [ -n "$realsq" ] && ln -sf "$realsq" "$bindir/sqlite3"
  fi
  make_curl_stub "$bindir" "$fixture_dir/sops-library-v2.jsonl.gz"
}

# count_sops_via_python <db> — the test's OWN oracle, independent of both the
# sqlite3 CLI and of ingest-sop-library.sh's own internal counting, run in
# the test's NORMAL (unrestricted) environment.
count_sops_via_python() {
  python3 -c "
import sqlite3
con = sqlite3.connect('$1')
print(con.execute('SELECT COUNT(*) FROM sops').fetchone()[0])
"
}

run_ingest_restricted_path() {  # <dir> <bindir> ; echoes rc
  local dir="$1" bindir="$2"
  PATH="$bindir" \
  MISSION_CONTROL_DB="$dir/mission-control.db" \
  SOP_LIB_MANIFEST="$dir/SOP-LIBRARY-MANIFEST.json" \
    bash "$INGEST_SH" testclient > "$dir/out.log" 2>&1
  echo $?
}

echo "== sanity: sqlite3 CLI genuinely exists on THIS machine (so excluding it below is a real test, not a no-op) =="
if command -v sqlite3 >/dev/null 2>&1; then
  ok "sqlite3 CLI is present in the ambient environment ($(command -v sqlite3))"
else
  bad "sqlite3 CLI is NOT present on this test machine — the 'no CLI' scenario below is not actually exercising anything"
fi

echo ""
echo "== (a) VPS-LIKE: python3 present, sqlite3 CLI ABSENT from PATH -> ingest still succeeds with the TRUE count =="
A="$TMP/a"; build_fixture "$A"
BIN_A="$A/bin-no-sqlite3"; build_clean_bin "$BIN_A" "$A" 0 1
[ ! -e "$BIN_A/sqlite3" ] && ok "(a) fixture PATH genuinely carries no sqlite3 binary" || bad "(a) sqlite3 leaked into the restricted PATH"
[ -x "$BIN_A/python3" ] && ok "(a) fixture PATH carries python3" || bad "(a) python3 missing from restricted PATH — test setup is broken"
RC_A="$(run_ingest_restricted_path "$A" "$BIN_A")"
TRUE_COUNT_A="$(count_sops_via_python "$A/mission-control.db")"
EXPECT_A=$((LIB_RECORDS + STARTER_ROWS))
[ "$RC_A" = "0" ] && ok "(a) ingest exits 0 with NO sqlite3 CLI on PATH (python3 stdlib carries the verification)" \
  || { bad "(a) ingest rc=$RC_A (expected 0) — a missing CLI must never FATAL a genuinely successful ingest"; sed 's/^/      /' "$A/out.log" | tail -15; }
[ "$TRUE_COUNT_A" = "$EXPECT_A" ] && ok "(a) the TRUE row count is $TRUE_COUNT_A ($LIB_RECORDS library + $STARTER_ROWS starter), matching what the script itself must report" \
  || bad "(a) expected $EXPECT_A true rows, oracle found $TRUE_COUNT_A"
grep -q "population verified: $EXPECT_A sops rows" "$A/out.log" \
  && ok "(a) script's own log reports the TRUE count ($EXPECT_A), not a false 0" \
  || { bad "(a) script log does not report the true population count"; sed 's/^/      /' "$A/out.log" | tail -15; }
grep -q "FATAL: post-ingest population is 0" "$A/out.log" \
  && bad "(a) THE LIVE DEFECT REPRODUCED: script reported a FALSE ZERO and FATALed despite a genuinely successful ingest" \
  || ok "(a) no false-zero FATAL — the exact live incident does NOT reproduce post-fix"

echo ""
echo "== (b) BOTH tools present (python3 AND sqlite3 CLI) -> SAME true count, same rc =="
B="$TMP/b"; build_fixture "$B"
BIN_B="$B/bin-both"; build_clean_bin "$BIN_B" "$B" 1 1
[ -x "$BIN_B/sqlite3" ] && ok "(b) fixture PATH carries sqlite3 this time" || bad "(b) sqlite3 missing from PATH — test setup broken"
RC_B="$(run_ingest_restricted_path "$B" "$BIN_B")"
TRUE_COUNT_B="$(count_sops_via_python "$B/mission-control.db")"
[ "$RC_B" = "0" ] && ok "(b) ingest exits 0 with sqlite3 CLI present" || { bad "(b) rc=$RC_B"; sed 's/^/      /' "$B/out.log" | tail -15; }
[ "$TRUE_COUNT_B" = "$EXPECT_A" ] && ok "(b) reaches the identical true count ($TRUE_COUNT_B) as scenario (a) — CLI-present and CLI-absent agree" \
  || bad "(b) expected $EXPECT_A, got $TRUE_COUNT_B"
[ "$RC_A" = "$RC_B" ] && ok "(b) identical exit code with vs without the CLI ($RC_A == $RC_B) — presence/absence of the CLI never changes the verdict" \
  || bad "(b) exit codes differ: no-CLI=$RC_A vs with-CLI=$RC_B"

echo ""
echo "== (c) NEITHER python3 NOR sqlite3 available -> honest, distinguishable FAIL, never a numeric 0 =="
C="$TMP/c"; build_fixture "$C"
BIN_C="$C/bin-neither"; build_clean_bin "$BIN_C" "$C" 0 0
[ ! -e "$BIN_C/python3" ] && [ ! -e "$BIN_C/sqlite3" ] \
  && ok "(c) fixture PATH carries neither python3 nor sqlite3" || bad "(c) setup leaked a sqlite reader"
BEFORE_C="$(count_sops_via_python "$C/mission-control.db")"
RC_C="$(run_ingest_restricted_path "$C" "$BIN_C")"
AFTER_C="$(count_sops_via_python "$C/mission-control.db")"
[ "$RC_C" != "0" ] && ok "(c) ingest exits non-zero (rc=$RC_C) when it genuinely cannot verify anything — never a silent green" \
  || bad "(c) ingest exited 0 with no way to have verified anything"
grep -qi "cannot verify" "$C/out.log" \
  && ok "(c) script states plainly it cannot verify (honest, distinguishable message)" \
  || { bad "(c) no 'cannot verify' message"; sed 's/^/      /' "$C/out.log" | tail -15; }
# The exact PRE-FIX phrasing this script used to FATAL with when a false-0
# was misread as a real result (see ingest-sop-library.sh's FINAL_COUNT
# gate). Must NOT appear here — the no-tool case is a distinct, honestly
# labeled failure, never dressed up as a measured "0 rows" result. (The
# fix's OWN disclaimer text deliberately contains the substring "0 rows" as
# part of "NOT the same as '0 rows'" — that reassurance is not a claim of
# zero, so the check below targets the specific pre-fix FATAL phrasing only.)
grep -q "post-ingest population is 0 rows\|post-ingest population is 0," "$C/out.log" \
  && bad "(c) script phrased the no-tool case as a measured '0 rows' result — this is exactly the banned false-zero framing" \
  || ok "(c) script never phrases 'cannot check' as a measured '0 rows' result"
[ "$AFTER_C" = "$BEFORE_C" ] \
  && ok "(c) DB left untouched when verification is impossible ($BEFORE_C rows, unchanged)" \
  || bad "(c) DB was modified despite being unable to verify the result"

echo ""
echo "----------------------------------------"
echo "  PASS: $PASS    FAIL: $FAIL"
echo "----------------------------------------"
[ "$FAIL" -eq 0 ] || exit 1
