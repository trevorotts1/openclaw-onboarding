#!/usr/bin/env bash
# tests/unit/skill6-maintenance-installers-all-run.test.sh
#
# FINDING 27: update-skills.sh discovered a skill's installer with
#   for _c in "$SKILL_DIR"/scripts/install-*.sh; do [ -x "$_c" ] && break; done
# Skill 06 ships four maintenance-cron installers; the glob sorts, so only
# install-github-archive-reconcile-cron.sh ever ran. Live cron list showed 55
# jobs, the archive job present, the inventory / routing-drift /
# selector-drift jobs absent.
#
# Contract now: skill 06 routes to install-skill6-maintenance-crons.sh, which
# names all four installers explicitly and then reports which jobs are
# REGISTERED / ABSENT / UNKNOWN.
#
# Hermetic: private $HOME, sandboxed copies of the scripts + schedule entries,
# fake `openclaw` (tests/fixtures/fake-openclaw-cron.py).
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FIXTURE="$REPO_ROOT/tests/fixtures/fake-openclaw-cron.py"
SKILL="$REPO_ROOT/06-ghl-install-pages"
HELPER="$SKILL/scripts/install-skill6-maintenance-crons.sh"
UPDATE="$REPO_ROOT/update-skills.sh"

PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
_one_line() { printf '%s' "$1" | tr '\n' ' '; }

INSTALLERS="install-github-archive-reconcile-cron.sh
install-page-inventory-lifecycle-cron.sh
install-routing-drift-check-cron.sh
install-selector-drift-probe-cron.sh"
JOBS="skill6-github-archive-reconcile-sweep
skill6-page-inventory-lifecycle
skill6-routing-drift-check
skill6-selector-drift-probe"

echo "=== skill6-maintenance-installers-all-run.test.sh ==="

# ---- 1. the update path routes skill 06 to the aggregate -------------------
echo "--- wiring ---"
if [ -x "$HELPER" ]; then pass "aggregate installer present + executable"; else fail "aggregate installer missing: $HELPER"; fi
if grep -q 'SKILL_NAME" = "06-ghl-install-pages".*install-skill6-maintenance-crons\.sh' "$UPDATE"; then
  pass "update-skills.sh selects the aggregate for skill 06 before the first-match glob"
else
  fail "update-skills.sh does not route skill 06 to install-skill6-maintenance-crons.sh (first-match discovery still wins)"
fi
for i in $INSTALLERS; do
  grep -q "$i" "$HELPER" && pass "helper names $i" || fail "helper does not name $i"
  [ -x "$SKILL/scripts/$i" ] && pass "installer on disk + executable: $i" || fail "missing/non-executable: scripts/$i"
done

# ---- 2. every installer actually runs, and registration is reported --------
echo "--- behaviour (fake openclaw) ---"
SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX" 2>/dev/null || true' EXIT
case "$SANDBOX" in */.openclaw|*/.openclaw/*) echo "REFUSING: sandbox inside a real .openclaw"; exit 2 ;; esac

BIN="$SANDBOX/bin"; mkdir -p "$BIN"
printf '#!/usr/bin/env bash\nexec python3 "%s" "$@"\n' "$FIXTURE" > "$BIN/openclaw"; chmod +x "$BIN/openclaw"

SK="$SANDBOX/skill"; mkdir -p "$SK/scripts"
cp "$HELPER" "$SK/scripts/"
for i in $INSTALLERS; do cp "$SKILL/scripts/$i" "$SK/scripts/"; done
cp -r "$SKILL/schedule" "$SK/"

HOME_D="$SANDBOX/home"; mkdir -p "$HOME_D"
JOBS_FILE="$SANDBOX/jobs.json"; CALLS="$SANDBOX/calls.log"; OUT="$SANDBOX/out.log"

run() { # <mode> <jobs-json> <args...>
  local mode="$1" jobs="$2"; shift 2
  printf '%s' "$jobs" > "$JOBS_FILE"; : > "$CALLS"
  HOME="$HOME_D" PATH="$BIN:$PATH" \
    FAKE_OC_LIST_MODE="$mode" FAKE_OC_JOBS_FILE="$JOBS_FILE" FAKE_OC_CALLS_FILE="$CALLS" \
    SKILL6_EVIDENCE_BASE="$SANDBOX/evidence" \
    bash "$SK/scripts/install-skill6-maintenance-crons.sh" "$@" >"$OUT" 2>&1
}
rerun() { # same, but keeps the persisted cron state from the previous run
  local mode="$1"; shift
  : > "$CALLS"
  HOME="$HOME_D" PATH="$BIN:$PATH" \
    FAKE_OC_LIST_MODE="$mode" FAKE_OC_JOBS_FILE="$JOBS_FILE" FAKE_OC_CALLS_FILE="$CALLS" \
    SKILL6_EVIDENCE_BASE="$SANDBOX/evidence" \
    bash "$SK/scripts/install-skill6-maintenance-crons.sh" "$@" >"$OUT" 2>&1
}
adds() { grep -cE '^cron (add|create) ' "$CALLS" 2>/dev/null || true; }
added_names() { grep -E '^cron (add|create) ' "$CALLS" 2>/dev/null | sed -n 's/.*--name \([^ ]*\).*/\1/p' | sort; }

run '' '[]' --idempotent; rc=$?
[ "$rc" -eq 0 ] && pass "empty list: rc 0" || fail "empty list: rc $rc (expected 0)"
[ "$(adds)" -eq 4 ] && pass "empty list: all four installers registered a job (4 adds)" \
  || fail "empty list: $(adds) add(s), expected 4 — an installer did not run"
expected="$(printf '%s\n' $JOBS | sort)"
[ "$(added_names)" = "$expected" ] && pass "empty list: exactly the four intended job names" \
  || fail "empty list: registered [$(_one_line "$(added_names)")], expected [$(_one_line "$expected")]"
grep -q 'registration: 4/4 intended Skill 6 maintenance jobs registered' "$OUT" \
  && pass "empty list: report says 4/4 registered" || fail "empty list: report does not say 4/4"
grep -q '^cron .*--idempotent' "$CALLS" 2>/dev/null \
  && fail "--idempotent was forwarded to an installer as an argument" \
  || pass "--idempotent consumed by the aggregate, never forwarded"

rerun '' --idempotent; rc=$?
[ "$rc" -eq 0 ] && pass "rerun: rc 0" || fail "rerun: rc $rc"
[ "$(adds)" -eq 0 ] && pass "rerun: idempotent, 0 adds" || fail "rerun: $(adds) add(s), expected 0"
grep -q 'registration: 4/4' "$OUT" && pass "rerun: still reports 4/4 registered" || fail "rerun: report wrong"

run fail '[]' --idempotent; rc=$?
[ "$(adds)" -eq 0 ] && pass "unreadable cron list: no add (would risk duplicates)" \
  || fail "unreadable cron list: $(adds) add(s) on an unreadable list"
[ "$rc" -eq 3 ] && pass "unreadable cron list: rc 3 (advisory)" || fail "unreadable cron list: rc $rc (expected 3)"
[ "$(grep -c 'UNKNOWN' "$OUT")" -eq 4 ] && pass "unreadable cron list: all four reported UNKNOWN, never ABSENT" \
  || fail "unreadable cron list: $(grep -c 'UNKNOWN' "$OUT") UNKNOWN line(s), expected 4"
grep -q 'ABSENT' "$OUT" && fail "unreadable cron list: reported ABSENT (D10 violation)" \
  || pass "unreadable cron list: no ABSENT claim"

PRESENT="$(printf '{"name":"%s","id":"1"},' $JOBS)"
run '' "[${PRESENT%,}]" --check-only; rc=$?
[ "$(adds)" -eq 0 ] && pass "--check-only: ran no installer" || fail "--check-only: $(adds) add(s)"
[ "$rc" -eq 0 ] && pass "--check-only: all present -> rc 0" || fail "--check-only: rc $rc (expected 0)"
grep -q 'registration: 4/4' "$OUT" && pass "--check-only: reports 4/4 registered" || fail "--check-only: report wrong"

echo "=== $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ]
