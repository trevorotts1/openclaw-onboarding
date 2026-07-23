#!/usr/bin/env bash
# test-sop-canonical-membership-skip.sh — U079 regression + functional test.
#
# THE BUG THIS GUARDS AGAINST: ingest-sop-library.sh's already-populated skip
# gate keyed ONLY on total row count (CURRENT_COUNT >= CANONICAL_SOP_COUNT). A
# database holding at least the threshold number of rows from ANY source — client-
# authored SOPs, starter seeds, or a different library version — satisfied the
# check, so the canonical library was never downloaded and never written. The box
# reported "already populated" over a library it did not actually hold.
#
# THE FIX: verify canonical MEMBERSHIP, not just population. The gate now samples
# a fixed set of canonical identifiers (canonical_sample_slugs in the manifest)
# and requires their presence before taking the skip branch. Count met but sample
# missing => do NOT skip, proceed to download.
#
# Tests (hermetic: temp DBs + a test manifest with a low canonical count and two
# sample slugs; no network, no live GitHub):
#   T1  count met AND sample slugs present  -> SKIP (exit 0, "skipped — already populated")
#   T2  count met BUT sample slugs MISSING  -> do NOT skip ("downloading" attempted)  [THE FIX]
#   T3  count BELOW canonical               -> do NOT skip ("downloading" attempted)
#   T4  MUTATION PROOF: drop the membership check from the skip condition -> T2 turns
#       RED (the missing-sample box now incorrectly SKIPs); revert -> GREEN.
#
# Run:  bash test-sop-canonical-membership-skip.sh

set -uo pipefail
P="[test-sop-canonical-membership-skip]"
PASS=0
FAIL=0
ok()  { echo "$P ok   — $1"; PASS=$((PASS+1)); }
bad() { echo "$P FAIL — $1"; FAIL=$((FAIL+1)); }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INGEST="$SCRIPT_DIR/ingest-sop-library.sh"
[ -f "$INGEST" ] || { echo "$P FATAL: ingest script not found at $INGEST"; exit 1; }

WORK="$(mktemp -d -t u079-XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

# --- Test manifest: low canonical count (5) + two sample slugs ----------------
TEST_MANIFEST="$WORK/manifest.json"
cat > "$TEST_MANIFEST" <<'JSON'
{
  "asset": "sops-library-v2.jsonl.gz",
  "release_tag": "vTEST",
  "sha256": "",
  "canonical_sop_count": 5,
  "canonical_sample_slugs": ["canonical-slug-alpha", "canonical-slug-beta"]
}
JSON

# --- Helper: build a temp DB with N sops rows from a given slug list ----------
# Usage: make_db <db-path> <slug1> <slug2> ...  (creates `sops` with id+slug cols)
make_db() {
  local db="$1"; shift
  sqlite3 "$db" "CREATE TABLE sops (id TEXT PRIMARY KEY, slug TEXT NOT NULL, name TEXT);"
  local i=0
  for slug in "$@"; do
    i=$((i+1))
    sqlite3 "$db" "INSERT INTO sops (id, slug, name) VALUES ('sop_${slug}', '${slug}', 'name-${i}');"
  done
}

# --- Helper: run the ingester's skip gate and report whether it SKIPPED -------
# Returns 0 if the script took the SKIP branch, 1 if it proceeded to download.
# We detect via output: "skipped — already populated" == SKIP; "downloading" == proceed.
# The download itself fails (no network / bad URL) but that is AFTER the decision.
run_gate() {
  local db="$1"
  local out
  out="$(MISSION_CONTROL_DB="$db" SOP_LIB_MANIFEST="$TEST_MANIFEST" \
         bash "$INGEST" test-client 2>&1 || true)"
  if printf '%s' "$out" | grep -q "skipped — already populated"; then
    return 0   # SKIP branch taken
  elif printf '%s' "$out" | grep -q "downloading"; then
    return 1   # proceeded to download
  else
    # Neither marker — surface the output for debugging
    echo "$out" | sed 's/^/    | /'
    return 2
  fi
}

echo "$P === U079: canonical-membership skip gate ==="

# --- T1: count met AND sample present -> SKIP ---------------------------------
DB1="$WORK/t1.db"
# 5 rows (meets canonical 5), INCLUDING both sample slugs
make_db "$DB1" "canonical-slug-alpha" "canonical-slug-beta" "other-1" "other-2" "other-3"
if run_gate "$DB1"; then
  ok "T1: count met + sample slugs present -> SKIP (already populated)"
else
  bad "T1: expected SKIP when count met and sample present"
fi

# --- T2: count met BUT sample MISSING -> do NOT skip (THE FIX) ----------------
DB2="$WORK/t2.db"
# 5 rows (meets canonical 5) but NONE are the sample slugs — rows from another source
make_db "$DB2" "foreign-1" "foreign-2" "foreign-3" "foreign-4" "foreign-5"
if run_gate "$DB2"; then
  bad "T2: count met but sample MISSING must NOT skip (bug: skipped a foreign library)"
else
  ok "T2: count met but sample slugs MISSING -> do NOT skip (proceeds to download) [THE FIX]"
fi

# --- T3: count BELOW canonical -> do NOT skip ---------------------------------
DB3="$WORK/t3.db"
# Only 2 rows (below canonical 5), even though sample slugs present
make_db "$DB3" "canonical-slug-alpha" "canonical-slug-beta"
if run_gate "$DB3"; then
  bad "T3: count below canonical must NOT skip"
else
  ok "T3: count below canonical -> do NOT skip (proceeds to download)"
fi

# --- T4: MUTATION PROOF -------------------------------------------------------
# Mutate the skip condition to drop the membership check (revert to the bug):
# remove `&& [ "$CANONICAL_MEMBERSHIP_OK" = "true" ]` from the skip gate.
cp "$INGEST" "$WORK/ingest.orig"
python3 - "$INGEST" <<'PY'
import sys, pathlib
p = pathlib.Path(sys.argv[1])
s = p.read_text(encoding="utf-8")
needle = ' ] 2>/dev/null && [ "$CANONICAL_MEMBERSHIP_OK" = "true" ]; then'
repl   = ' ] 2>/dev/null; then'
assert needle in s, "mutation target not found"
# Only mutate the SKIP gate occurrence (the first one), not the membership-check block.
s = s.replace(needle, repl, 1)
p.write_text(s, encoding="utf-8")
PY

# With the mutation, T2's missing-sample box should now incorrectly SKIP (RED).
DB4="$WORK/t4.db"
make_db "$DB4" "foreign-1" "foreign-2" "foreign-3" "foreign-4" "foreign-5"
if run_gate "$DB4"; then
  ok "T4 RED: with membership check removed, missing-sample box incorrectly SKIPs (bug reproduced)"
else
  bad "T4 RED: mutation did not reproduce the bug (missing-sample box still did not skip)"
fi

# Revert and confirm GREEN (T2 behavior restored).
cp "$WORK/ingest.orig" "$INGEST"
if run_gate "$DB4"; then
  bad "T4 GREEN: after revert, missing-sample box still SKIPs (revert failed)"
else
  ok "T4 GREEN: after revert, missing-sample box does NOT skip (fix restored)"
fi

# Sanity: bash -n on the (restored) script still passes.
if bash -n "$INGEST" 2>/dev/null; then
  ok "restored script passes bash -n"
else
  bad "restored script FAILS bash -n"
fi

echo "$P === $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
exit 0
