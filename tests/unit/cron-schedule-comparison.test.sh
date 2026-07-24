#!/usr/bin/env bash
# tests/unit/cron-schedule-comparison.test.sh
# U129 — Cron registrar schedule comparison
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REGISTRAR="$REPO_ROOT/35-social-media-planner/scripts/register-weekly-cron.sh"

PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); echo "  ok  - $*"; }
fail() { FAIL=$((FAIL+1)); echo "  FAIL - $*" >&2; }
assert_eq() { if [ "$2" = "$3" ]; then ok "$1"; else fail "$1 (want '$2', got '$3')"; fi; }

echo "== static =="
bash -n "$REGISTRAR" && ok "script parses" || fail "script does not parse"

SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/u129-cron-schedule-test.XXXXXX")"
trap 'rm -rf "$SANDBOX"' EXIT
export HOME="$SANDBOX/home"; mkdir -p "$HOME"
STATE="$SANDBOX/state"; mkdir -p "$STATE"
: > "$STATE/gateway.txt"; : > "$STATE/adds.txt"
MOCKBIN="$SANDBOX/bin"; mkdir -p "$MOCKBIN"

cat > "$MOCKBIN/openclaw" <<'MOCKEOF'
#!/usr/bin/env bash
SD="$(dirname "$0")/../state"; GW="$SD/gateway.txt"; ADDS="$SD/adds.txt"
case "${1:-} ${2:-}" in
  "cron list")
      i=0
      while IFS='|' read -r n s t st; do
          [ -z "$n" ] && continue; i=$((i+1))
          id="$(printf '%08d-1111-2222-3333-%012d' "$i" "$i")"
          printf '%s  %s  %s  %s  sessionTarget=%s
' "$id" "$n" "$s" "${st:-active}" "$t"
      done < "$GW"
      exit 0 ;;
  "cron add")
      shift 2; n="" s="" t=""
      while [ $# -gt 0 ]; do
          case "$1" in
              --name) n="$2"; shift ;;
              --cron) s="$2"; shift ;;
              --session-target) t="$2"; shift ;;
          esac
          shift
      done
      [ -n "$n" ] || exit 1
      echo "$n|$s|$t|active" >> "$GW"
      echo "$n|$s|$t" >> "$ADDS"
      exit 0 ;;
  "cron delete")
      shift 2; bn=""
      while [ $# -gt 0 ]; do case "$1" in --name) bn="$2"; shift ;; esac; shift; done
      tmp="$GW.tmp"; : > "$tmp"
      while IFS='|' read -r n s t st; do
          [ -z "$n" ] && continue; [ -n "$bn" ] && [ "$n" = "$bn" ] && continue
          echo "$n|$s|$t|$st" >> "$tmp"
      done < "$GW"; mv "$tmp" "$GW"
      exit 0 ;;
  "config validate") exit 0 ;;
  *) exit 0 ;;
esac
MOCKEOF
chmod +x "$MOCKBIN/openclaw"
export PATH="$MOCKBIN:$PATH"
mkdir -p "$HOME/.openclaw/data/skill35"

gw_count()      { grep -c "^$1|" "$STATE/gateway.txt" 2>/dev/null || echo 0; }
gw_schedule_of(){ grep "^$1|" "$STATE/gateway.txt" 2>/dev/null | head -1 | cut -d'|' -f2 || true; }
adds_count()    { local c; c=$(grep -c "^$1|" "$STATE/adds.txt" 2>/dev/null) || c=0; printf '%s' "$c"; }
seed_monday()   { printf '%s|%s|%s|%s
' "skill35-weekly-theme" "0 8 * * 1" "main" "active" > "$STATE/gateway.txt"; : > "$STATE/adds.txt"; }
seed_saturday() { printf '%s|%s|%s|%s
' "skill35-weekly-theme" "0 8 * * 6" "main" "active" > "$STATE/gateway.txt"; : > "$STATE/adds.txt"; }
seed_error()    { printf '%s|%s|%s|%s
' "skill35-weekly-theme" "0 8 * * 6" "main" "error" > "$STATE/gateway.txt"; : > "$STATE/adds.txt"; }
seed_empty()    { : > "$STATE/gateway.txt"; : > "$STATE/adds.txt"; }

echo "== T1 schedule mismatch (Monday => re-register Saturday) =="
seed_monday
set +e; bash "$REGISTRAR" >"$SANDBOX/t1.out" 2>&1; rc=$?; set -e 2>/dev/null || true
assert_eq "exits 0" "0" "$rc"
assert_eq "one entry after fix" "1" "$(gw_count skill35-weekly-theme)"
assert_eq "schedule corrected to Sat 8AM" "0 8 * * 6" "$(gw_schedule_of skill35-weekly-theme)"
assert_eq "one re-registration" "1" "$(adds_count skill35-weekly-theme)"
grep -q "wrong schedule" "$SANDBOX/t1.out" && ok "wrong-schedule notice" || fail "no wrong-schedule notice"

echo "== T2 schedule match (Saturday => already healthy) =="
seed_saturday
set +e; bash "$REGISTRAR" >"$SANDBOX/t2.out" 2>&1; rc=$?; set -e 2>/dev/null || true
assert_eq "exits 0" "0" "$rc"
assert_eq "still one entry" "1" "$(gw_count skill35-weekly-theme)"
assert_eq "schedule unchanged" "0 8 * * 6" "$(gw_schedule_of skill35-weekly-theme)"
[ "$(adds_count skill35-weekly-theme)" -eq 0 ] && ok "no re-registration" || fail "re-registration called"
grep -q "correct schedule" "$SANDBOX/t2.out" && ok "correct-schedule notice" || fail "no correct-schedule notice"

echo "== T3 erroring cron => still re-registers =="
seed_error
set +e; bash "$REGISTRAR" >"$SANDBOX/t3.out" 2>&1; rc=$?; set -e 2>/dev/null || true
assert_eq "exits 0" "0" "$rc"
assert_eq "one entry after fix" "1" "$(gw_count skill35-weekly-theme)"
assert_eq "schedule remains Sat" "0 8 * * 6" "$(gw_schedule_of skill35-weekly-theme)"
assert_eq "one re-registration" "1" "$(adds_count skill35-weekly-theme)"

echo "== T4 empty gateway => fresh registration =="
seed_empty
set +e; bash "$REGISTRAR" >"$SANDBOX/t4.out" 2>&1; rc=$?; set -e 2>/dev/null || true
assert_eq "exits 0" "0" "$rc"
assert_eq "one entry after fresh reg" "1" "$(gw_count skill35-weekly-theme)"
assert_eq "schedule is Sat" "0 8 * * 6" "$(gw_schedule_of skill35-weekly-theme)"
assert_eq "one registration" "1" "$(adds_count skill35-weekly-theme)"

echo "== T5 duplicate => cleanup + one correct reg =="
printf '%s|%s|%s|%s
' "skill35-weekly-theme" "0 8 * * 1" "main" "active" > "$STATE/gateway.txt"
printf '%s|%s|%s|%s
' "skill35-weekly-theme" "0 8 * * 6" "main" "active" >> "$STATE/gateway.txt"
: > "$STATE/adds.txt"
set +e; bash "$REGISTRAR" >"$SANDBOX/t5.out" 2>&1; rc=$?; set -e 2>/dev/null || true
assert_eq "exits 0" "0" "$rc"
assert_eq "one entry after cleanup" "1" "$(gw_count skill35-weekly-theme)"
assert_eq "final schedule is Sat" "0 8 * * 6" "$(gw_schedule_of skill35-weekly-theme)"
assert_eq "one registration" "1" "$(adds_count skill35-weekly-theme)"

echo "== T6 mutation proof =="
MUTATED="$(mktemp "${TMPDIR:-/tmp}/u129-mutated.XXXXXX")"
trap 'rm -f "$MUTATED"; rm -rf "$SANDBOX"' EXIT
cp "$REGISTRAR" "$MUTATED"
sed -i '' 's/_schedule_ok="\$(echo.*grep -cF.*CRON_EXPR.*"/_schedule_ok=1  # MUTATED/' "$MUTATED" 2>/dev/null || sed -i 's/_schedule_ok="\$(echo.*grep -cF.*CRON_EXPR.*"/_schedule_ok=1  # MUTATED/' "$MUTATED"
bash -n "$MUTATED" || { fail "mutated script does not parse"; }
seed_monday
set +e; HOME="$SANDBOX/home" PATH="$MOCKBIN:$PATH" bash "$MUTATED" >"$SANDBOX/t6.out" 2>&1; rc=$?; set -e 2>/dev/null || true
grep -q "nothing to do" "$SANDBOX/t6.out" && [ "$rc" -eq 0 ] && ok "mutation: Monday accepted (old bug)" || fail "mutation: Monday NOT accepted (exit=$rc)"
[ "$(gw_schedule_of skill35-weekly-theme)" = "0 8 * * 1" ] && ok "mutation: schedule NOT corrected" || fail "mutation: schedule corrected"
[ "$(adds_count skill35-weekly-theme)" -eq 0 ] && ok "mutation: no re-registration" || fail "mutation: re-registration called"
seed_monday
set +e; bash "$REGISTRAR" >"$SANDBOX/t6b.out" 2>&1; rc=$?; set -e 2>/dev/null || true
assert_eq "original fixes schedule" "0" "$rc"
[ "$(gw_schedule_of skill35-weekly-theme)" = "0 8 * * 6" ] && ok "original corrected to Sat" || fail "original did NOT correct"

echo ""
echo "== U129 cron-schedule-comparison: $PASS passed, $FAIL failed =="
[ "$FAIL" -eq 0 ] || exit 1
exit 0
