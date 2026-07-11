#!/usr/bin/env bash
# tests/unit/fleet-validation-harness.test.sh
# ─────────────────────────────────────────────────────────────────────────────
# THE ACCEPTANCE TEST for AUD-58 / FLEET-FIX 4b, driven end-to-end through the
# real CLI (scripts/fleet-validate.sh) at the REAL doctrine path — /tmp/<sweep>/<box>.json.
#
#   A. a simulated 20-box FAN-OUT writes 20 per-box ledger files to
#      /tmp/<sweep>/<box>.json  (written by the bash-callable ledger CLI, exactly
#      as the roll's own fan-out loop will write them)
#   B. the validation harness runs over those same 20 boxes and is GREEN (exit 0)
#   C. with ONE deliberately-broken box (its MC_API_TOKEN store is UNREACHABLE)
#      the harness FAILS LOUDLY — exit 2, a FAIL banner, the broken box named,
#      and the other 19 boxes still individually green.  It does NOT report green.
#   D. the fan-out's install row and the harness's validation rows live in the
#      SAME per-box file — the ledger is persistent across both phases.
#   E. an undeclared expectation REFUSES the sweep (exit 4) without touching a box.
#
# Hermetic: no ssh, no network, no live box.  The `sim` backend serves canned
# probe output; the deliberately-broken box is broken IN THE FIXTURE.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VALIDATE="$REPO_ROOT/scripts/fleet-validate.sh"
LEDGER="$REPO_ROOT/shared-utils/fleet_ledger.py"

PASS=0; FAIL=0
pass() { echo "  PASS: $*"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $*"; FAIL=$((FAIL+1)); }

for f in "$VALIDATE" "$LEDGER"; do
    [ -f "$f" ] || { echo "FATAL: missing $f"; exit 2; }
done

SWEEP="aud58-selftest-$$-$RANDOM"
SWEEP_DIR="/tmp/$SWEEP"                     # the DOCTRINE path — deliberately not a tempdir
WORK="$(mktemp -d -t aud58.XXXXXX)"
trap 'rm -rf "$WORK" "$SWEEP_DIR"' EXIT

BOXES="$WORK/boxes.json"
EXPECT="$WORK/expectations.json"
FIXTURE_OK="$WORK/fixture-all-green.json"
FIXTURE_BROKEN="$WORK/fixture-one-broken.json"

# ── fixtures: 20 boxes; box-07 is the deliberately-broken one ────────────────
BOXES="$BOXES" EXPECT="$EXPECT" FIXTURE_OK="$FIXTURE_OK" FIXTURE_BROKEN="$FIXTURE_BROKEN" python3 - <<'PY'
import json, os

names = [f"box-{i:02d}" for i in range(1, 21)]
SHA = "002f8333aaaabbbbccccddddeeeeffff00001111"
VER = "v19.44.0"

json.dump([{"name": n, "ssh_target": f"svc@{n}.internal"} for n in names],
          open(os.environ["BOXES"], "w"))

json.dump({
    "repo_version": VER,
    "repo_sha": SHA,
    "openclaw_min_version": "2026.5.22",
    "run_retries_max": 3,
    "writeback_url": "http://127.0.0.1:4000/api/tasks/ingest",
}, open(os.environ["EXPECT"], "w"))

def healthy():
    return {
        # exit 3 == NEEDS_BLOCK == HEALTHY for MC_API_TOKEN (it is not a provider key)
        "token_store": {"rc": 3, "stdout": json.dumps(
            {"verdict": "NEEDS_BLOCK", "where_found": ["~/.openclaw/secrets/.env"],
             "live_env_checked": True})},
        "writeback": {"rc": 0, "stdout": "401"},
        "browser": {"rc": 0, "stdout": "Agent Browser preflight: ALL CHECKS PASS"},
        "openclaw_version": {"rc": 0, "stdout": "2026.5.22"},
        "run_retries": {"rc": 0, "stdout": "3"},
        "repo_stamp": {"rc": 0, "stdout": f"{VER}\n{SHA}"},
    }

ok = {"boxes": {n: {"probes": healthy()} for n in names}}
json.dump(ok, open(os.environ["FIXTURE_OK"], "w"))

broken = {"boxes": {n: {"probes": healthy()} for n in names}}
# box-07: the MC_API_TOKEN store is UNREACHABLE — the token is in no store at all.
broken["boxes"]["box-07"]["probes"]["token_store"] = {
    "rc": 1,
    "stdout": json.dumps({"verdict": "GENUINELY-ABSENT", "where_found": [], "live_env_checked": True}),
}
json.dump(broken, open(os.environ["FIXTURE_BROKEN"], "w"))
PY

echo "=============================================================="
echo "A. simulated 20-box FAN-OUT -> /tmp/<sweep>/<box>.json"
echo "=============================================================="
for i in $(seq -w 1 20); do
    python3 "$LEDGER" record --sweep-id "$SWEEP" --box "box-$i" \
        --check install --status PASS \
        --reason "update-skills.sh | bash -s (fresh checkout) applied v19.44.0" >/dev/null || \
        fail "ledger record failed for box-$i"
done
COUNT="$(ls -1 "$SWEEP_DIR"/box-*.json 2>/dev/null | wc -l | tr -d ' ')"
if [ "$COUNT" = "20" ]; then
    pass "fan-out wrote 20 per-box ledger files to $SWEEP_DIR/<box>.json"
else
    fail "expected 20 ledger files in $SWEEP_DIR, found $COUNT"
fi
[ -f "$SWEEP_DIR/box-07.json" ] && pass "canonical path exists: $SWEEP_DIR/box-07.json" \
                                || fail "missing $SWEEP_DIR/box-07.json"

echo
echo "=============================================================="
echo "B. validation harness — all 20 boxes healthy"
echo "=============================================================="
OUT_OK="$(bash "$VALIDATE" --sweep-id "$SWEEP" --boxes-file "$BOXES" --expectations "$EXPECT" \
            --backend sim --sim-fixture "$FIXTURE_OK" 2>&1)"
RC_OK=$?
echo "$OUT_OK" | sed 's/^/    | /'
[ "$RC_OK" = "0" ] && pass "all-green wave exits 0" || fail "all-green wave exited $RC_OK (want 0)"
echo "$OUT_OK" | grep -q "FLEET VALIDATION: PASS" && pass "prints the PASS banner" \
                                                  || fail "no PASS banner"

echo
echo "=============================================================="
echo "C. ONE deliberately-broken box (box-07: MC_API_TOKEN store UNREACHABLE)"
echo "=============================================================="
OUT_BAD="$(bash "$VALIDATE" --sweep-id "$SWEEP" --boxes-file "$BOXES" --expectations "$EXPECT" \
            --backend sim --sim-fixture "$FIXTURE_BROKEN" 2>&1)"
RC_BAD=$?
echo "$OUT_BAD" | sed 's/^/    | /'

[ "$RC_BAD" = "2" ] && pass "broken box makes the wave exit 2 (NOT green)" \
                    || fail "broken box exited $RC_BAD (want 2)"
echo "$OUT_BAD" | grep -q "FLEET VALIDATION: FAIL" && pass "FAILS LOUDLY (FAIL banner printed)" \
                                                   || fail "no FAIL banner — this is the fail-open bug"
echo "$OUT_BAD" | grep -q "THE FLEET ROLL IS BLOCKED" && pass "states the roll is BLOCKED" \
                                                      || fail "did not say the roll is blocked"
echo "$OUT_BAD" | grep -q "box-07" && pass "names the broken box" || fail "did not name box-07"
echo "$OUT_BAD" | grep -qi "UNREACHABLE" && pass "states the ROOT CAUSE (token store unreachable)" \
                                         || fail "did not state the root cause"

STATUS_07="$(python3 -c "import json,sys;print(json.load(open('$SWEEP_DIR/box-07.json'))['status'])")"
[ "$STATUS_07" = "FAIL" ] && pass "box-07 ledger status = FAIL" || fail "box-07 ledger status = $STATUS_07"

GREEN_COUNT=0
for i in $(seq -w 1 20); do
    [ "$i" = "07" ] && continue
    S="$(python3 -c "import json;print(json.load(open('$SWEEP_DIR/box-$i.json'))['status'])")"
    [ "$S" = "PASS" ] && GREEN_COUNT=$((GREEN_COUNT+1))
done
[ "$GREEN_COUNT" = "19" ] && pass "the other 19 boxes are individually PASS (per-box isolation)" \
                          || fail "expected 19 healthy boxes, got $GREEN_COUNT"

VERDICT="$(python3 -c "import json;print(json.load(open('$SWEEP_DIR/_sweep.json'))['verdict'])")"
[ "$VERDICT" = "FAIL" ] && pass "sweep rollup verdict = FAIL" || fail "sweep rollup verdict = $VERDICT"

echo
echo "=============================================================="
echo "D. the ledger is PERSISTENT across fan-out + validation"
echo "=============================================================="
HAS_BOTH="$(python3 -c "
import json
d = json.load(open('$SWEEP_DIR/box-07.json'))
ck = d['checks']
print('yes' if ('install' in ck and 'mc_api_token_store' in ck and 'repo_stamp' in ck) else 'no')")"
[ "$HAS_BOTH" = "yes" ] && pass "box-07.json holds BOTH the fan-out install row and all 5 validation rows" \
                        || fail "the fan-out row and the validation rows are not in the same file"

NO_SECRET="$(python3 - "$SWEEP_DIR" <<'PY'
import pathlib, re, sys
# Assert NO secret-shaped VALUE reached any ledger row. (Scans the ledger the
# sweep just wrote — never a credential store.)
pat = re.compile(r"(?:sk|pit|pat|ghp)-[A-Za-z0-9_\-]{4,}|Bearer\s+\S{6,}|eyJ[A-Za-z0-9_\-]{8,}\.")
hits = [str(p) for p in pathlib.Path(sys.argv[1]).glob("*.json") if pat.search(p.read_text())]
print(len(hits))
PY
)"
[ "$NO_SECRET" = "0" ] && pass "no secret-shaped value anywhere in the ledger" \
                       || fail "a secret-shaped value reached the ledger ($NO_SECRET file(s))"

echo
echo "=============================================================="
echo "E. an UNDECLARED expectation refuses the sweep (a gate you cannot fail is not a gate)"
echo "=============================================================="
python3 -c "
import json
d = json.load(open('$EXPECT')); d.pop('repo_sha')
json.dump(d, open('$WORK/expect-partial.json','w'))"
OUT_REFUSE="$(bash "$VALIDATE" --sweep-id "${SWEEP}-refuse" --boxes-file "$BOXES" \
                --expectations "$WORK/expect-partial.json" --backend sim \
                --sim-fixture "$FIXTURE_OK" 2>&1)"
RC_REFUSE=$?
echo "$OUT_REFUSE" | sed 's/^/    | /'
[ "$RC_REFUSE" = "4" ] && pass "undeclared expectation -> exit 4 (sweep REFUSED)" \
                       || fail "undeclared expectation exited $RC_REFUSE (want 4)"
[ ! -d "/tmp/${SWEEP}-refuse" ] && pass "a refused sweep writes NO ledger row (nothing is green)" \
                                || { fail "a refused sweep wrote ledger rows"; rm -rf "/tmp/${SWEEP}-refuse"; }

echo
echo "=============================================================="
echo "RESULT: $PASS passed, $FAIL failed"
echo "=============================================================="
[ "$FAIL" -eq 0 ] || exit 1
exit 0
