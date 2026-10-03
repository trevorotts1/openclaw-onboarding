#!/usr/bin/env bash
# tests/rescue/RR-030/test_reconcile_duplicate_slug.sh   (RR plan fix F37)
#
# One duplicated slug in rr_agent_map must NOT abort the fleet-wide reconcile.
# Seed: box-dup has TWO rows, box-a has a WRONG row, box-b is absent.
#   - box-a is repaired (PATCH) and box-b inserted (POST) -- the other slugs still run
#   - box-dup is NOT written, is named, and is PENDING with reason duplicate_rows rows=2
#   - the run still ends complete=0 and exits non-zero (never reported clean)
#   - the machine line says aborted=0 duplicates=1 pending=1
#   - a second run is stable (same duplicate still pending, no further writes to box-dup)
#   - NEGATIVE CONTROL: with no duplicate, the same world ends complete=1, exit 0
# Hermetic: loopback stub of the n8n data-table API (tests/unit/fixtures/mock-rr-datatable.py),
# stub ssh/docker. The scenario harness (start_mock / write_world / run_reconcile / helpers) is
# EXTRACTED VERBATIM from tests/unit/rr031-reconcile-agent-map.test.sh between its "# Harness"
# comment and the pending_lines() helper, never reimplemented; exits 2 if those markers drift.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
SRC="$REPO/tests/unit/rr031-reconcile-agent-map.test.sh"
RECONCILE="$REPO/scripts/reconcile-rr-agent-map.sh"
LIB="$REPO/scripts/_rr_registry_lib.py"
MOCK="$REPO/tests/unit/fixtures/mock-rr-datatable.py"
TABLE="EFPgipZtKatC5xPw"
TABLE_ALT="ZZaltTableId0001"
for f in "$SRC" "$RECONCILE" "$LIB" "$MOCK"; do [ -f "$f" ] || { echo "FATAL: missing $f"; exit 2; }; done
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ok   $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL $1 ${2:-}"; }
WORK="$(mktemp -d "${TMPDIR:-/tmp}/rr030-recon-XXXXXX")"
CLEANUP_PIDS=""
cleanup() { for p in $CLEANUP_PIDS; do kill "$p" 2>/dev/null || true; done; rm -rf "$WORK"; }
trap cleanup EXIT INT TERM

START="$(grep -n '^# Harness: one mock server' "$SRC" | head -1 | cut -d: -f1)"
END="$(grep -n '^pending_lines()' "$SRC" | head -1 | cut -d: -f1)"
{ [ -n "$START" ] && [ -n "$END" ] && [ "$END" -gt "$START" ]; } || { echo "FATAL: harness markers drifted in $SRC"; exit 2; }
sed -n "${START},${END}p" "$SRC" > "$WORK/harness.sh"
# shellcheck disable=SC1090
. "$WORK/harness.sh"
type start_mock write_world run_reconcile row_for writes_log >/dev/null 2>&1 || { echo "FATAL: harness functions not defined"; exit 2; }

echo "== F37: duplicated slug is pending, the rest of the fleet still reconciles =="
start_mock dup '[{"box_slug":"box-dup","local_agent_id":"dept-x"},{"box_slug":"box-dup","local_agent_id":"dept-y"},{"box_slug":"box-a","local_agent_id":"dept-WRONG"}]' 50 || exit 2
printf 'box-a vps dept-a\nbox-b vps dept-b\nbox-dup vps dept-x\n' > "$WORK/dup-spec.txt"
write_world dup "$WORK/dup-spec.txt"
DW="$WORLD"
rc=$(run_reconcile "$DW" "$MOCK_PORT" "$WORK/dup-run1.out" --apply)
[ "$rc" -ne 0 ] && ok "run exits non-zero (never reported clean)" || bad "run exited $rc on a roster with a duplicate" "$(tail -5 "$WORK/dup-run1.out")"
grep -q 'aborted=0' "$WORK/dup-run1.out" && ok "machine line: aborted=0 (no fleet-wide abort)" || bad "machine line still says aborted" "$(grep 'reconcile-rr-agent-map:' "$WORK/dup-run1.out")"
grep -q 'duplicates=1' "$WORK/dup-run1.out" && ok "machine line: duplicates=1" || bad "duplicates count missing"
grep -q 'complete=0' "$WORK/dup-run1.out" && ok "machine line: complete=0" || bad "complete=0 missing"
grep -q 'pending=1' "$WORK/dup-run1.out" && ok "machine line: pending=1" || bad "pending count wrong" "$(grep 'reconcile-rr-agent-map:' "$WORK/dup-run1.out")"
grep -q 'duplicate box_slug=box-dup rows=2' "$WORK/dup-run1.out" && ok "duplicate slug and row count are named" || bad "duplicate not named"
grep -q 'pending box-dup .*reason=duplicate_rows rows=2' "$WORK/dup-run1.out" && ok "box-dup listed PENDING with owner and reason duplicate_rows rows=2" || bad "pending line for box-dup missing" "$(grep pending "$WORK/dup-run1.out")"
printf '%s' "$(row_for "$DW" box-a)" | grep -q 'dept-a' && ok "OTHER slug box-a was still repaired" || bad "box-a not repaired (fleet blocked by one duplicate)" "$(row_for "$DW" box-a)"
printf '%s' "$(row_for "$DW" box-b)" | grep -q 'dept-b' && ok "OTHER slug box-b was still inserted" || bad "box-b not inserted"
[ "$(row_for "$DW" box-dup | python3 -c 'import json,sys;print(len(json.load(sys.stdin)))')" = "2" ] && ok "box-dup rows untouched (still exactly the 2 seeded rows)" || bad "box-dup rows changed"
if writes_log "$MOCK_DIR" | grep -q 'box-dup'; then bad "a write targeted box-dup"; else ok "no write ever targeted box-dup"; fi
python3 - "$DW/state" <<'PY' && ok "pending ledger records box-dup with an owner" || bad "pending ledger missing box-dup"
import glob, json, sys
for p in glob.glob(sys.argv[1] + "/**/*.json", recursive=True):
    try: d = json.load(open(p))
    except Exception: continue
    if isinstance(d, dict) and isinstance(d.get("pending"), list):
        e = [x for x in d["pending"] if x.get("box_slug") == "box-dup"]
        if e and e[0].get("owner") and "duplicate_rows" in str(e[0].get("reason")) and d.get("complete") == 0:
            sys.exit(0)
sys.exit(1)
PY

before="$(writes_log "$MOCK_DIR" | wc -l | tr -d ' ')"
rc=$(run_reconcile "$DW" "$MOCK_PORT" "$WORK/dup-run2.out" --apply)
after="$(writes_log "$MOCK_DIR" | wc -l | tr -d ' ')"
[ "$rc" -ne 0 ] && grep -q 'pending=1' "$WORK/dup-run2.out" && ok "rerun: duplicate still pending, still non-zero" || bad "rerun not stable" "$(tail -4 "$WORK/dup-run2.out")"
[ "$before" = "$after" ] && ok "rerun: no further writes" || bad "rerun wrote again ($before -> $after)"

echo "== negative control: same world without the duplicate completes clean =="
start_mock ctl '[{"box_slug":"box-a","local_agent_id":"dept-WRONG"}]' 50 || exit 2
printf 'box-a vps dept-a\nbox-b vps dept-b\n' > "$WORK/ctl-spec.txt"
write_world ctl "$WORK/ctl-spec.txt"
rc=$(run_reconcile "$WORLD" "$MOCK_PORT" "$WORK/ctl-run.out" --apply)
{ [ "$rc" -eq 0 ] && grep -q 'complete=1' "$WORK/ctl-run.out" && grep -q 'duplicates=0' "$WORK/ctl-run.out"; } && ok "control: no duplicate -> rc=0 complete=1 duplicates=0 (the detector can pass)" || bad "control run not clean" "$(tail -4 "$WORK/ctl-run.out")"

echo; echo "RR-030 reconcile duplicate slug: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
