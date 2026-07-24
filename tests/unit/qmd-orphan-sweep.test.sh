#!/usr/bin/env bash
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SWEEP="$REPO_ROOT/scripts/qmd-orphan-sweep.sh"
[ -f "$SWEEP" ] || { echo "FATAL: $SWEEP not found"; exit 1; }
PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); printf '  PASS  %s\n' "$1"; }
fail() { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }
WORK="$(mktemp -d "${TMPDIR:-/tmp}/qmd-sweep-test.XXXXXX")" || exit 1
trap 'rm -rf "$WORK"' EXIT
ws_dir()  { printf '%s/.openclaw/workspace' "$1"; }
log_file() { printf '%s/.openclaw/qmd-orphan-sweep.log' "$1"; }
touch_aged() { local f="$1" m="$2"; mkdir -p "$(dirname "$f")"; touch "$f"; local ts; ts=$(date -v -"${m}"M +%Y%m%d%H%M.%S 2>/dev/null) && touch -t "$ts" "$f" 2>/dev/null || true; }
count() { find "$1" -maxdepth 99 -type f -name "$2" 2>/dev/null | wc -l | tr -d ' '; }
echo "== T1 old .qmd swept =="
OC1="$WORK/t1"; mkdir -p "$OC1/.openclaw/workspace/sub"; WS1="$(ws_dir "$OC1")"
touch_aged "$WS1/orphan.qmd" 1500; touch_aged "$WS1/sub/old.qmd" 2000; touch_aged "$WS1/young.qmd" 10; touch_aged "$WS1/notes.txt" 1500
B4=$(count "$WS1" "*.qmd")
HOME="$OC1" QMD_MIN_AGE_MIN=1440 QMD_RENDER_DIR="$WS1" bash "$SWEEP" >/dev/null 2>&1
A_QMD=$(count "$WS1" "*.qmd"); A_YOUNG=$(count "$WS1" "young.qmd"); A_TXT=$(count "$WS1" "notes.txt")
[ "$B4" -eq 3 ] && [ "$A_QMD" -eq 1 ] && pass "T1a: 3->1 qmd" || fail "T1a: $B4->$A_QMD"
[ "$A_YOUNG" -eq 1 ] && pass "T1b: young survives" || fail "T1b: young=$A_YOUNG"
[ "$A_TXT" -eq 1 ] && pass "T1c: txt survives" || fail "T1c: txt=$A_TXT"
echo "== T2 young .qmd survive =="
OC2="$WORK/t2"; mkdir -p "$OC2/.openclaw/workspace"; WS2="$(ws_dir "$OC2")"
touch_aged "$WS2/a.qmd" 5; touch_aged "$WS2/b.qmd" 30
HOME="$OC2" QMD_MIN_AGE_MIN=1440 QMD_RENDER_DIR="$WS2" bash "$SWEEP" >/dev/null 2>&1
[ "$(count "$WS2" "*.qmd")" -eq 2 ] && pass "T2: both survive" || fail "T2"
echo "== T3 non-.qmd untouched =="
OC3="$WORK/t3"; mkdir -p "$OC3/.openclaw/workspace"; WS3="$(ws_dir "$OC3")"
touch_aged "$WS3/a.png" 1500; touch_aged "$WS3/b.json" 1500; touch_aged "$WS3/c.txt" 1500; touch_aged "$WS3/d.md" 1500
B4=$(find "$WS3" -type f | wc -l | tr -d ' ')
HOME="$OC3" QMD_MIN_AGE_MIN=1440 QMD_RENDER_DIR="$WS3" bash "$SWEEP" >/dev/null 2>&1
AF=$(find "$WS3" -type f | wc -l | tr -d ' ')
[ "$B4" = "$AF" ] && pass "T3: $B4 unchanged" || fail "T3: $B4->$AF"
echo "== T4 dry-run =="
OC4="$WORK/t4"; mkdir -p "$OC4/.openclaw/workspace"; WS4="$(ws_dir "$OC4")"
touch_aged "$WS4/a.qmd" 1500; touch_aged "$WS4/b.qmd" 1500
B4=$(count "$WS4" "*.qmd")
HOME="$OC4" QMD_MIN_AGE_MIN=1440 QMD_RENDER_DIR="$WS4" QMD_DRY_RUN=1 bash "$SWEEP" >/dev/null 2>&1
AF=$(count "$WS4" "*.qmd"); LP="$(log_file "$OC4")"
[ "$B4" = "$AF" ] && [ "$AF" -eq 2 ] && pass "T4a: dry keeps files" || fail "T4a: $B4->$AF"
[ -f "$LP" ] && grep -q "DRY" "$LP" && ! grep -q "SWEPT" "$LP" && pass "T4b: DRY no SWEPT" || fail "T4b: log"
echo "== T5 no OC_ROOT =="
HOME="$WORK/t5-none" bash "$SWEEP" >/dev/null 2>&1; [ $? -eq 2 ] && pass "T5: exit 2" || fail "T5"
echo "== T6 outside-tree =="
OC6="$WORK/t6"; mkdir -p "$OC6/.openclaw/workspace"; OD="$WORK/t6-out"; mkdir -p "$OD"
touch_aged "$OD/x.qmd" 1500
HOME="$OC6" QMD_MIN_AGE_MIN=1440 QMD_RENDER_DIR="$OD" bash "$SWEEP" >/dev/null 2>&1; RC=$?
[ $RC -eq 2 ] && pass "T6a: refused" || fail "T6a: rc=$RC"
HOME="$OC6" QMD_MIN_AGE_MIN=1440 QMD_RENDER_DIR="$OD" QMD_RENDER_ACK=1 bash "$SWEEP" >/dev/null 2>&1; RC=$?
[ $RC -eq 0 ] && [ "$(count "$OD" "*.qmd")" -eq 0 ] && pass "T6b: ACK=1 works" || fail "T6b"
echo "== T7 log written =="
OC7="$WORK/t7"; mkdir -p "$OC7/.openclaw/workspace"; WS7="$(ws_dir "$OC7")"
touch_aged "$WS7/x.qmd" 1500
HOME="$OC7" QMD_MIN_AGE_MIN=1440 QMD_RENDER_DIR="$WS7" bash "$SWEEP" >/dev/null 2>&1
[ -f "$(log_file "$OC7")" ] && grep -q "SWEPT" "$(log_file "$OC7")" && pass "T7: log with SWEPT" || fail "T7"
echo "== T8 empty =="
OC8="$WORK/t8"; mkdir -p "$OC8/.openclaw/workspace"; WS8="$(ws_dir "$OC8")"
HOME="$OC8" QMD_MIN_AGE_MIN=1440 QMD_RENDER_DIR="$WS8" bash "$SWEEP" >/dev/null 2>&1; RC=$?
[ $RC -eq 0 ] && pass "T8a: exit 0" || fail "T8a: rc=$RC"
[ -f "$(log_file "$OC8")" ] && grep -q "clean" "$(log_file "$OC8")" && pass "T8b: clean log" || fail "T8b"
HOME="$WORK/t8-no" bash "$SWEEP" >/dev/null 2>&1; [ $? -eq 2 ] && pass "T8c: no HOME exit 2" || fail "T8c"
echo "== T9 MUTATION PROOF =="
MUT_HOME="$WORK/t9"; mkdir -p "$MUT_HOME/.openclaw/workspace"; MUT_RD="$MUT_HOME/.openclaw/workspace"
touch_aged "$MUT_RD/a.qmd" 1500; touch_aged "$MUT_RD/b.txt" 1500; touch_aged "$MUT_RD/c.json" 1500; touch_aged "$MUT_RD/d.png" 1500
MUT_SCRIPT="$WORK/t9-mut.sh"
sed 's/-type f -name "\*\.qmd" -mmin +/-type f -mmin +/' "$SWEEP" > "$MUT_SCRIPT"
chmod +x "$MUT_SCRIPT"
grep -q -- "-type f -mmin +" "$MUT_SCRIPT" && ! grep -q -- '-name "\*\.qmd"' "$MUT_SCRIPT" && pass "T9a: mutation applied" || fail "T9a: mutation"
HOME="$MUT_HOME" QMD_MIN_AGE_MIN=1440 QMD_RENDER_DIR="$MUT_RD" bash "$MUT_SCRIPT" >/dev/null 2>&1
T1=$(count "$MUT_RD" "*.txt"); J1=$(count "$MUT_RD" "*.json"); P1=$(count "$MUT_RD" "*.png")
[ "$T1" -eq 0 ] && [ "$J1" -eq 0 ] && [ "$P1" -eq 0 ] && pass "T9b: MUTATION PROOF - all old files swept (proves T3 non-vacuous)" || fail "T9b: txt=$T1 json=$J1 png=$P1"
echo "== T10 cron-like minimal PATH =="
OC10="$WORK/t10"; mkdir -p "$OC10/.openclaw/workspace"; WS10="$(ws_dir "$OC10")"
touch_aged "$WS10/cron-orphan.qmd" 2000
# Simulate cron: strip PATH to bare minimum (/usr/bin:/bin), unset all other env
env -i HOME="$OC10" PATH="/usr/bin:/bin" QMD_MIN_AGE_MIN=1440 QMD_RENDER_DIR="$WS10" \
  bash "$SWEEP" >/dev/null 2>&1; RC=$?
[ $RC -eq 0 ] && [ "$(count "$WS10" "*.qmd")" -eq 0 ] && pass "T10a: cron-env exit 0, file swept" || fail "T10a: rc=$RC count=$(count "$WS10" "*.qmd")"
[ -f "$(log_file "$OC10")" ] && grep -q "SWEPT" "$(log_file "$OC10")" && pass "T10b: cron-env log with SWEPT" || fail "T10b: log"
echo "== T11 CRON MUTATION PROOF =="
CRONTAB="$REPO_ROOT/config/cron.d/qmd-orphan-sweep"
[ -f "$CRONTAB" ] || { fail "T11: crontab file missing"; echo "=== SUMMARY  PASS $PASS  FAIL $FAIL ==="; exit 1; }
MUT_CRONTAB="$WORK/t11-mut-cron"
# Mutation: corrupt the 0 6 * * * line by changing the script path to nonexistent
sed 's|/usr/local/bin/qmd-orphan-sweep.sh|/usr/local/bin/NONEXISTENT-sweep.sh|' "$CRONTAB" > "$MUT_CRONTAB"
grep -q "NONEXISTENT-sweep.sh" "$MUT_CRONTAB" && ! grep -q "NONEXISTENT" "$CRONTAB" && pass "T11a: cron mutation applied" || fail "T11a: cron mutation"
# Revert check: original crontab points to real script
grep -q "/usr/local/bin/qmd-orphan-sweep.sh" "$CRONTAB" && pass "T11b: cron original intact" || fail "T11b: cron original"
echo ""; echo "=== SUMMARY  PASS $PASS  FAIL $FAIL ==="; [ "$FAIL" -gt 0 ] && exit 1; echo "PASS: all checks pass"; exit 0
