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
# REGISTERED / ABSENT / UNKNOWN. NO first-match fallback for skill 06 (a
# missing aggregate must fail loudly, never silently revert to 1-of-4).
# REPORT SEMANTICS: ABSENT is claimed only with proven full-visibility
# (feature-detected status flag); a disabled-invisible job reads UNKNOWN,
# never ABSENT (D10). Installer rc 2 (repo defect) propagates as rc 2 — it is
# never masked as advisory rc 3.
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

# ---- 1. shipped wiring ----------------------------------------------------
echo "--- wiring (shipped files) ---"
if [ -x "$HELPER" ]; then pass "aggregate installer present + executable"; else fail "aggregate installer missing: $HELPER"; fi
for i in $INSTALLERS; do
  grep -q "$i" "$HELPER" && pass "helper names $i" || fail "helper does not name $i"
  [ -x "$SKILL/scripts/$i" ] && pass "installer on disk + executable: $i" || fail "missing/non-executable: scripts/$i"
done

# ---- 2. sandbox -----------------------------------------------------------
SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX" 2>/dev/null || true' EXIT
case "$SANDBOX" in */.openclaw|*/.openclaw/*) echo "REFUSING: sandbox inside a real .openclaw"; exit 2 ;; esac

BIN="$SANDBOX/bin"; mkdir -p "$BIN"
printf '#!/usr/bin/env bash\nexec python3 "%s" "$@"\n' "$FIXTURE" > "$BIN/openclaw"; chmod +x "$BIN/openclaw"

SK="$SANDBOX/skill"
build_skill() {
  rm -rf "$SK"; mkdir -p "$SK/scripts"
  cp "$HELPER" "$SK/scripts/"
  for i in $INSTALLERS; do cp "$SKILL/scripts/$i" "$SK/scripts/"; done
  cp -r "$SKILL/schedule" "$SK/"
}
build_skill

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

# ---- 3. update-skills.sh discovery block BEHAVES (extracted and run) -------
# A grep of update-skills.sh proves only that a line exists — not that the
# first-match loop is skipped, and not that a missing aggregate refuses
# instead of silently reverting to 1-of-4 installers. Extract the real
# discovery block and drive it through a fake SKILL_DIR tree instead.
echo "--- update-skills.sh discovery (extracted block) ---"
BLOCK="$SANDBOX/discovery-block.sh"
if python3 - "$UPDATE" "$BLOCK" <<'PYEOF'
import sys
lines = open(sys.argv[1], encoding="utf-8").read().splitlines()
try:
    start = next(i for i, l in enumerate(lines) if l == '    SKILL_INSTALLER=""')
    end = next(i for i, l in enumerate(lines[start:], start)
               if l == '    if [ -n "$SKILL_INSTALLER" ]; then')
except StopIteration:
    sys.stderr.write("discovery block anchors not found in update-skills.sh\n")
    sys.exit(1)
open(sys.argv[2], "w", encoding="utf-8").write("\n".join(lines[start:end]) + "\n")
PYEOF
then
  pass "discovery block extracted from update-skills.sh"
else
  fail "could not extract the discovery block from update-skills.sh (anchors moved?)"
fi

discover() { # <skill-name> <skill-dir> -> prints RESULT|<installer-or-EMPTY>|<failed-flag>
  SKILL_NAME="$1" SKILL_DIR="$2" bash -c '
    set -u
    . "$1"
    echo "RESULT|${SKILL_INSTALLER:-EMPTY}|${_INSTALLER_FAILED}"
  ' _ "$BLOCK" 2>&1
}
mkstub() { # <dir> <name> — executable no-op installer
  mkdir -p "$1"; printf '#!/usr/bin/env bash\nexit 0\n' > "$1/$2"; chmod +x "$1/$2"
}

D="$SANDBOX/disc"
for i in $INSTALLERS; do
  mkstub "$D/withagg/scripts" "$i"; mkstub "$D/noagg/scripts" "$i"
  mkstub "$D/noexec/scripts" "$i"
done
cp "$HELPER" "$D/withagg/scripts/"; chmod +x "$D/withagg/scripts/$(basename "$HELPER")"
cp "$HELPER" "$D/noexec/scripts/"; chmod -x "$D/noexec/scripts/$(basename "$HELPER")"
mkstub "$D/archiveonly/scripts" "install-github-archive-reconcile-cron.sh"
mkstub "$D/s15/scripts" "install-remote-rescue.sh"

out="$(discover 06-ghl-install-pages "$D/withagg")"
case "$out" in
  *"RESULT|$D/withagg/scripts/install-skill6-maintenance-crons.sh|0"*)
    pass "skill 06 routes to the aggregate installer" ;;
  *) fail "skill 06 aggregate routing broken: [$(_one_line "$out")]" ;;
esac
out="$(discover 06-ghl-install-pages "$D/noagg")"
case "$out" in
  *"RESULT|EMPTY|1"*)
    pass "skill 06 without the aggregate: no installer chosen, sentinel withheld (no first-match fallback)" ;;
  *) fail "skill 06 fell back to a first-match installer: [$(_one_line "$out")]" ;;
esac
case "$out" in
  *'refusing the first-match fallback'*)
    pass "skill 06 refusal is loud (message printed)" ;;
  *) fail "skill 06 refusal message missing: [$(_one_line "$out")]" ;;
esac
out="$(discover 06-ghl-install-pages "$D/noexec")"
case "$out" in
  *"RESULT|EMPTY|1"*)
    pass "skill 06 with a non-executable aggregate: refused, not silently routed" ;;
  *) fail "skill 06 non-executable aggregate not refused: [$(_one_line "$out")]" ;;
esac
out="$(discover 06-ghl-install-pages "$D/archiveonly")"
case "$out" in
  *"RESULT|EMPTY|1"*)
    pass "finding-27 regression guard: archive-only tree is refused, never first-match" ;;
  *) fail "first-match discovery still wins on an archive-only tree: [$(_one_line "$out")]" ;;
esac
out="$(discover 15-remote-rescue "$D/s15")"
case "$out" in
  *"RESULT|$D/s15/scripts/install-remote-rescue.sh|0"*)
    pass "other skills keep first-match discovery (skill 15 -> install-remote-rescue.sh)" ;;
  *) fail "skill 15 discovery changed: [$(_one_line "$out")]" ;;
esac

# ---- 4. every installer actually runs, and registration is reported --------
echo "--- behaviour (fake openclaw) ---"
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

run garbage '[]' --check-only; rc=$?
[ "$rc" -eq 3 ] && pass "garbage (non-JSON) cron list: rc 3" || fail "garbage cron list: rc $rc (expected 3)"
[ "$(grep -c 'UNKNOWN' "$OUT")" -eq 4 ] && pass "garbage cron list: four UNKNOWN lines" \
  || fail "garbage cron list: $(grep -c 'UNKNOWN' "$OUT") UNKNOWN line(s), expected 4"
grep -q 'ABSENT' "$OUT" && fail "garbage cron list: reported ABSENT (D10 violation)" \
  || pass "garbage cron list: no ABSENT claim"

PRESENT="$(printf '{"name":"%s","id":"1"},' $JOBS)"
run '' "[${PRESENT%,}]" --check-only; rc=$?
[ "$(adds)" -eq 0 ] && pass "--check-only: ran no installer" || fail "--check-only: $(adds) add(s)"
[ "$rc" -eq 0 ] && pass "--check-only: all present -> rc 0" || fail "--check-only: rc $rc (expected 0)"
grep -q 'registration: 4/4' "$OUT" && pass "--check-only: reports 4/4 registered" || fail "--check-only: report wrong"

# ---- 5. negative: disabled (hidden) jobs never read ABSENT ------------------
# The fixture's default CLI IGNORES --all (a flag it never advertised) and
# hides disabled jobs — exactly the live shape this report must survive. A
# disabled-but-present job is UNKNOWN, never ABSENT; only a feature-detected
# full-visibility flag earns an ABSENT claim.
echo "--- negative: disabled jobs and full-visibility detection ---"
HIDDEN="$(printf '{"name":"%s","hidden":true},' $JOBS)"
run '' "[${HIDDEN%,}]" --check-only; rc=$?
[ "$rc" -eq 3 ] && pass "disabled jobs, no status flag: rc 3" || fail "disabled jobs, no status flag: rc $rc (expected 3)"
[ "$(grep -c 'UNKNOWN' "$OUT")" -eq 4 ] && pass "disabled jobs, no status flag: four UNKNOWN lines" \
  || fail "disabled jobs, no status flag: $(grep -c 'UNKNOWN' "$OUT") UNKNOWN line(s), expected 4"
grep -q 'ABSENT' "$OUT" && fail "FALSE ABSENT: a disabled job read as absent on a partial listing (D10 violation)" \
  || pass "disabled jobs, no status flag: no false ABSENT"

export FAKE_OC_ADVERTISE_STATUS_FLAG=1
run '' "[${HIDDEN%,}]" --check-only; rc=$?
unset FAKE_OC_ADVERTISE_STATUS_FLAG
[ "$rc" -eq 0 ] && pass "status flag advertised: feature-detected, disabled jobs read REGISTERED -> rc 0" \
  || fail "status flag advertised: rc $rc (expected 0)"
grep -q 'cron list --status all --json' "$CALLS" 2>/dev/null \
  && pass "status flag advertised: --status all actually used on the list call" \
  || fail "status flag advertised but list call used no full-visibility flag: [$(_one_line "$(cat "$CALLS" 2>/dev/null)")]"
grep -q 'registration: 4/4' "$OUT" && pass "status flag advertised: report says 4/4" || fail "status flag advertised: report wrong"

# ABSENT stays reachable when (and only when) full visibility is proven.
export FAKE_OC_ADVERTISE_STATUS_FLAG=1
THREE="$(printf '{"name":"%s","id":"1"},' $(printf '%s\n' $JOBS | head -3))"
run '' "[${THREE%,}]" --check-only; rc=$?
unset FAKE_OC_ADVERTISE_STATUS_FLAG
[ "$rc" -eq 3 ] && pass "one truly absent job (full visibility): rc 3" || fail "one truly absent job: rc $rc (expected 3)"
[ "$(grep -c 'ABSENT' "$OUT")" -eq 1 ] && pass "one truly absent job (full visibility): exactly one ABSENT line" \
  || fail "one truly absent job: $(grep -c 'ABSENT' "$OUT") ABSENT line(s), expected 1"

# ---- 6. negative: installer failure semantics ------------------------------
echo "--- negative: installer exit-code semantics ---"
build_skill
printf '#!/usr/bin/env bash\nexit 2\n' > "$SK/scripts/install-page-inventory-lifecycle-cron.sh"
run '' '[]' --idempotent; rc=$?
[ "$rc" -eq 2 ] && pass "installer rc 2 (repo defect): aggregate exits 2, not advisory 3" \
  || fail "installer rc 2 masked: aggregate rc $rc (expected 2)"
grep -q 'REPO DEFECT rc=2' "$OUT" && pass "installer rc 2: reported as REPO DEFECT" \
  || fail "installer rc 2: no REPO DEFECT line: [$(_one_line "$(tail -3 "$OUT" 2>/dev/null)")]"
grep -q 're-run backfills' "$OUT" && fail "installer rc 2: wrongly promised a re-run backfill" \
  || pass "installer rc 2: no false re-run promise"

build_skill
printf '#!/usr/bin/env bash\nexit 3\n' > "$SK/scripts/install-routing-drift-check-cron.sh"
run '' '[]' --idempotent; rc=$?
[ "$rc" -eq 3 ] && pass "installer rc 3 (advisory): aggregate exits 3" || fail "installer rc 3: aggregate rc $rc (expected 3)"
grep -q 'ADVISORY rc=3' "$OUT" && pass "installer rc 3: reported as ADVISORY" || fail "installer rc 3: no ADVISORY line"

build_skill
rm -f "$SK/scripts/install-selector-drift-probe-cron.sh"
run '' '[]' --idempotent; rc=$?
[ "$rc" -eq 3 ] && pass "installer file missing: aggregate exits 3" || fail "installer file missing: rc $rc (expected 3)"
grep -q 'FAIL installer missing: scripts/install-selector-drift-probe-cron.sh' "$OUT" \
  && pass "installer file missing: FAIL names the file" || fail "installer file missing: no FAIL line"

# ---- 7. negative: repo-defect and argument handling ------------------------
echo "--- negative: schedule entries and arguments ---"
build_skill
printf '{"bogus":1}' > "$SK/schedule/skill6-page-inventory-lifecycle.cron.json"
run '' '[]' --idempotent; rc=$?
[ "$rc" -eq 2 ] && pass "unparsable shipped schedule entry: rc 2 (repo defect)" \
  || fail "unparsable schedule entry: rc $rc (expected 2)"

build_skill
run '' '[]' --bogus-flag; rc=$?
[ "$rc" -eq 0 ] && pass "unknown argument: run still completes (rc 0)" || fail "unknown argument: rc $rc (expected 0)"
grep -q 'WARN ignoring unknown argument: --bogus-flag' "$OUT" \
  && pass "unknown argument: warned and ignored" || fail "unknown argument: no WARN line"
grep -q -- '--bogus-flag' "$CALLS" 2>/dev/null \
  && fail "unknown argument leaked to an installer/cron call" \
  || pass "unknown argument never forwarded to an installer"

echo "=== $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ]
