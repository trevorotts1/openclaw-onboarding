#!/usr/bin/env bash
set -uo pipefail
REPO_ROOT="/Users/blackceomacmini/July-23-Fixes/repos/openclaw-onboarding"
ORIG_FILE="$REPO_ROOT/35-social-media-planner/scripts/weekly-batch.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
P=0; F=0
pass() { echo "  PASS: $1"; P=$((P+1)); }
fail() { echo "  FAIL: $1"; F=$((F+1)); }
echo "=== skill35-zero-work-idle-heartbeat.test.sh (U131) ==="; echo ""

PATCHED="$TMP/patched.sh"
FAKE="$TMP/run-publishing-cycle.sh"
echo '#!/usr/bin/env bash; exit 0' > "$FAKE"; chmod +x "$FAKE"
python3 /tmp/build-u131-patch.py "$ORIG_FILE" "$PATCHED" "$FAKE" || { echo "FATAL"; exit 1; }
bash -n "$PATCHED" || { echo "FATAL syntax"; exit 1; }

run() {
  local cal="$1" scr="${2:-$PATCHED}"
  local h="$TMP/h.$$"
  rm -rf "$h" 2>/dev/null || true
  mkdir -p "$h/.openclaw/config" "$h/.openclaw/data/skill35/logs"
  [ -n "$cal" ] && cp "$cal" "$h/.openclaw/config/content-calendar.json"
  HOME="$h" bash "$scr" 2>/dev/null
  local r=$?; echo "rc:$r"; echo "hb-path:$h/.openclaw/data/skill35/last-zero-work-heartbeat"
}

echo "T1: no calendar -> ZERO_WORK_EXIT"
o1="$(run "")"; r1="$(echo "$o1" | sed -n 's/^rc://p')"
[ "$r1" = "10" ] && pass "T1 no calendar -> exit 10" || fail "T1 expected 10 got $r1"

echo "T2: no calendar -> heartbeat"
h1="$(echo "$o1" | sed -n 's/^hb-path://p')"
if [ -f "$h1" ]; then
  hc="$(cat "$h1")"
  echo "$hc" | grep -q '"status":"idle"' && echo "$hc" | grep -q '"reason":"no-calendar"' \
    && pass "T2 heartbeat with reason=no-calendar" || fail "T2 content: $hc"
else
  fail "T2 no heartbeat at $h1"
fi

echo "T3: future-only -> ZERO_WORK_EXIT"
FC="$TMP/fc.json"
python3 - "$FC" <<'PY'
import json, sys, datetime as dt
f=dt.date.today()+dt.timedelta(180); m=f-dt.timedelta(f.weekday())
es=[{"date":(m+dt.timedelta(i)).strftime("%Y-%m-%d"),"topic":f"F{i}","platforms":["x"]} for i in range(3)]
json.dump({"v":"1.0","entries":es},open(sys.argv[1],"w"))
PY
o3="$(run "$FC")"; r3="$(echo "$o3" | sed -n 's/^rc://p')"
[ "$r3" = "10" ] && pass "T3 future-only -> exit 10" || fail "T3 expected 10 got $r3"

echo "T4: heartbeat reason=no-matching-entries"
h3="$(echo "$o3" | sed -n 's/^hb-path://p')"
if [ -f "$h3" ]; then
  hc3="$(cat "$h3")"
  echo "$hc3" | grep -q '"reason":"no-matching-entries"' \
    && pass "T4 heartbeat reason=no-matching-entries" || fail "T4 content: $hc3"
else
  fail "T4 no heartbeat at $h3"
fi

echo "T5: entries this week -> exit 0"
T5C="$TMP/t5c.json"
python3 - "$T5C" <<'PY'
import json, sys, datetime as dt
t=dt.date.today(); m=t-dt.timedelta(t.weekday())
json.dump({"v":"1.0","entries":[{"date":m.strftime("%Y-%m-%d"),"topic":"Test","platforms":["x"]}]},open(sys.argv[1],"w"))
PY
t5h="$TMP/t5h"; rm -rf "$t5h" 2>/dev/null || true
mkdir -p "$t5h/.openclaw/config" "$t5h/.openclaw/data/skill35/logs"
cp "$T5C" "$t5h/.openclaw/config/content-calendar.json"
HOME="$t5h" bash "$PATCHED" 2>/dev/null; t5r=$?
[ "$t5r" = "0" ] && pass "T5 success -> exit 0" || fail "T5 expected 0 got $t5r"

echo "T6: MUTATION PROOF"
cp "$PATCHED" "$TMP/m.sh"
python3 -c "c=open('$TMP/m.sh').read(); c=c.replace('exit \$ZERO_WORK_EXIT','exit 0'); open('$TMP/m.sh','w').write(c)" 2>/dev/null
chmod +x "$TMP/m.sh"; bash -n "$TMP/m.sh" 2>/dev/null || { fail "T6 syntax error"; exit 1; }
mh="$TMP/mh"; rm -rf "$mh" 2>/dev/null || true
mkdir -p "$mh/.openclaw/config" "$mh/.openclaw/data/skill35/logs"
HOME="$mh" bash "$TMP/m.sh" 2>/dev/null; mr=$?
if [ "$mr" = "0" ]; then
  pass "T6a mutant exits 0 -- RED (mutation detected)"
elif [ "$mr" = "10" ]; then
  fail "T6a mutant still exits 10 (mutation ineffective)"
else
  fail "T6a mutant exit=$mr"
fi

oh="$TMP/oh"; rm -rf "$oh" 2>/dev/null || true
mkdir -p "$oh/.openclaw/config" "$oh/.openclaw/data/skill35/logs"
HOME="$oh" bash "$PATCHED" 2>/dev/null; or=$?
[ "$or" = "10" ] && pass "T6b original exits 10 -- GREEN restored" \
  || fail "T6b original exits $or (expected 10)"

echo ""
echo "  Result: $P passed | $F failed"
[ "$F" -gt 0 ] && { echo "FAILED"; exit 1; }
echo "PASSED"; exit 0
