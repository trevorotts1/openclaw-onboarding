#!/usr/bin/env bash
# test-resume-does-not-reopen-finished-box.sh — BU-100 (closes WF-121, D-11):
# the 15-minute resume job NEVER re-opens a closed-out box.
#
# BEFORE: every fire ran workforce_completion.finalize() unconditionally, and
# finalize() DELETES buildCompletedAt whenever evaluate() reports any unmet
# requirement (workforce_completion.py L93-95) and demotes
# closeoutStatus done|sent -> "partial". A finished box was therefore re-opened
# and redispatched on the next tick, forever.
#
# AFTER: the completion re-check is skipped while closeoutStatus is done|sent.
# A box that is not closed out (any other value, or no closeoutStatus at all)
# keeps the old behaviour.
#
# Four assertions:
#   C1-BEFORE (pre-change script, the C1 fixture): closeoutStatus ends
#       "partial" and buildCompletedAt is GONE — recorded first, as the
#       unchanged-behaviour baseline.
#   C1   (real script, same fixture): closeoutStatus stays "done" and
#       buildCompletedAt is UNCHANGED.
#   C1b  the log records the skip decision.
#   C2   (real script, closeoutStatus "partial"): buildCompletedAt is gone —
#       the old re-check still runs on a box that is not closed out.
#
# Hermetic: fresh $HOME per case holding .openclaw/workspace, a stub `openclaw`
# first on PATH that records its arguments and exits 0, no network, no live
# box. Exit 0 = pass.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESUME="$SCRIPT_DIR/resume-workforce-build.sh"

PASS=0
FAIL=0
ok()  { PASS=$((PASS+1)); echo "  PASS: $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }

T_HOME="$(mktemp -d -p "${TMPDIR:-$PWD}")"
FIXTURE_BIN="$(mktemp -d -p "${TMPDIR:-$PWD}")"
export STUB_LOG="$FIXTURE_BIN/calls.log"
cleanup() { rm -rf "$T_HOME" "$FIXTURE_BIN"; }
trap cleanup EXIT

if [[ ! -f "$RESUME" ]]; then
  echo "FATAL: $RESUME not found"
  exit 1
fi

# Stub CLI: records every call, never reaches a real gateway.
printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$*" >> "$STUB_LOG"\nexit 0\n' > "$FIXTURE_BIN/openclaw"
chmod +x "$FIXTURE_BIN/openclaw"

# The pre-change script: the same directory (every sibling — the lib, the
# Python modules, the floor script — reached through symlinks) with only the
# BU-100 block replaced by the single line it replaced. This is the C1-BEFORE
# baseline, and it also makes C1 non-vacuous.
build_pre_change_script() {
  local dir="$1" f
  mkdir -p "$dir" || return 1
  for f in "$SCRIPT_DIR"/*; do
    [[ -e "$f" ]] || continue
    [[ "$(basename "$f")" == "resume-workforce-build.sh" ]] && continue
    ln -sfn "$f" "$dir/$(basename "$f")" || return 1
  done
  python3 - "$RESUME" "$dir/resume-workforce-build.sh" <<'PY'
import sys
source, target = sys.argv[1], sys.argv[2]
text = open(source, encoding="utf-8").read()
block = '''# A box whose closeout is finished is never re-opened by this job.
_recheck_closeout="$(jq -r '.closeoutStatus // ""' "$STATE_FILE" 2>/dev/null || true)"
case "$_recheck_closeout" in
  done|sent)
    log "completion re-check skipped: closeoutStatus=$_recheck_closeout (a finished box is not re-opened by the resume job)" ;;
  *)
    "$WORKFORCE_PYTHON" "$COMPLETION_SCRIPT" "$STATE_FILE" >>"$LOG_FILE" 2>&1 || true ;;
esac
'''
replacement = '"$WORKFORCE_PYTHON" "$COMPLETION_SCRIPT" "$STATE_FILE" >>"$LOG_FILE" 2>&1 || true\n'
# If the block is absent the script is left unchanged: the baseline then
# behaves like the script under test, C1-BEFORE fails, and the suite goes red.
# Fail closed, never silently green.
open(target, "w", encoding="utf-8").write(text.replace(block, replacement))
PY
  local rc=$?
  chmod +x "$dir/resume-workforce-build.sh" 2>/dev/null || true
  return "$rc"
}

# Sandbox state, exactly the unit's fixture. The department carries a real
# how-to.md (>= 256 bytes, no placeholder marker) so the lane's disk-reality
# audit does not demote it and clear buildCompletedAt for an unrelated reason.
write_fixture() {
  local home="$1" closeout="$2"
  local workspace="$home/.openclaw/workspace"
  local state="$workspace/.workforce-build-state.json"
  local role_dir="$workspace/departments/marketing/seo"
  mkdir -p "$role_dir" || return 1
  {
    printf 'Fixture role how-to for BU-100. '
    local i=0
    while (( i < 8 )); do
      printf 'Padding line %d keeps this file above the 256-byte stub floor and free of placeholder markers. ' "$i"
      i=$((i + 1))
    done
    printf '\n'
  } > "$role_dir/how-to.md"
  python3 - "$state" "$closeout" <<'PY'
import json, sys
state = {
    "companySlug": "acme",
    "interviewComplete": True,
    "buildCompletedAt": "2026-06-01T00:00:00Z",
    "closeoutStatus": sys.argv[2],
    "departments": [{"slug": "marketing", "status": "done"}],
}
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    handle.write(json.dumps(state, indent=2) + "\n")
PY
}

run_case() {
  local label="$1" script="$2" closeout="$3"
  local home="$T_HOME/$label"
  local state="$home/.openclaw/workspace/.workforce-build-state.json"
  write_fixture "$home" "$closeout" || { echo "FATAL: fixture setup failed for $label" >&2; exit 1; }
  HOME="$home" PATH="$FIXTURE_BIN:$PATH" WORKFORCE_BUILD_STATE_FILE="$state" \
    bash "$script" >/dev/null 2>&1
  echo "  ($label: resume exit $?)" >&2
}

field() {
  python3 - "$1" "$2" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    state = json.load(handle)
print(state[sys.argv[2]] if sys.argv[2] in state else "ABSENT")
PY
}

# ─────────────────────────────────────────────────────────────────────────
echo "== C1-BEFORE: pre-change script on the C1 fixture re-opens the box =="

PRE_DIR="$T_HOME/pre-change-scripts"
if ! build_pre_change_script "$PRE_DIR"; then
  echo "FATAL: could not build the pre-change script baseline"
  exit 1
fi
run_case c1-before "$PRE_DIR/resume-workforce-build.sh" done
BEFORE_STATE="$T_HOME/c1-before/.openclaw/workspace/.workforce-build-state.json"
BEFORE_COMPLETED="$(field "$BEFORE_STATE" buildCompletedAt)"
BEFORE_CLOSEOUT="$(field "$BEFORE_STATE" closeoutStatus)"
if [[ "$BEFORE_COMPLETED" == "ABSENT" ]]; then
  ok "C1-BEFORE: buildCompletedAt was removed (the box was re-opened — baseline reproduced)"
else
  bad "C1-BEFORE: buildCompletedAt survived ('$BEFORE_COMPLETED') — the baseline did not reproduce, C1 would prove nothing"
fi
if [[ "$BEFORE_CLOSEOUT" == "partial" ]]; then
  ok "C1-BEFORE: closeoutStatus ends 'partial' (recorded old behaviour)"
else
  bad "C1-BEFORE: closeoutStatus ends '$BEFORE_CLOSEOUT', expected 'partial'"
fi

# ─────────────────────────────────────────────────────────────────────────
echo ""
echo "== C1: real script, closeoutStatus=done -> the finished box stays finished =="

run_case c1 "$RESUME" done
C1_STATE="$T_HOME/c1/.openclaw/workspace/.workforce-build-state.json"
C1_COMPLETED="$(field "$C1_STATE" buildCompletedAt)"
C1_CLOSEOUT="$(field "$C1_STATE" closeoutStatus)"
if [[ "$C1_COMPLETED" == "2026-06-01T00:00:00Z" ]]; then
  ok "C1: buildCompletedAt is unchanged"
else
  bad "C1: buildCompletedAt is '$C1_COMPLETED', expected the original 2026-06-01T00:00:00Z"
fi
if [[ "$C1_CLOSEOUT" == "done" ]]; then
  ok "C1: closeoutStatus is still 'done'"
else
  bad "C1: closeoutStatus is '$C1_CLOSEOUT', expected 'done'"
fi

C1_LOG="$T_HOME/c1/.openclaw/workspace/.workforce-build-state.log"
if [[ -f "$C1_LOG" ]] && python3 - "$C1_LOG" <<'PY'
import sys
text = open(sys.argv[1], encoding="utf-8", errors="replace").read()
assert "completion re-check skipped: closeoutStatus=done" in text, text[-2000:]
PY
then
  ok "C1b: the log records the skip decision"
else
  bad "C1b: the log does not record the skip decision"
fi

# ─────────────────────────────────────────────────────────────────────────
echo ""
echo "== C2: real script, closeoutStatus=partial -> old behaviour kept =="

run_case c2 "$RESUME" partial
C2_STATE="$T_HOME/c2/.openclaw/workspace/.workforce-build-state.json"
C2_COMPLETED="$(field "$C2_STATE" buildCompletedAt)"
if [[ "$C2_COMPLETED" == "ABSENT" ]]; then
  ok "C2: buildCompletedAt is gone — the completion re-check still runs on an open box"
else
  bad "C2: buildCompletedAt survived ('$C2_COMPLETED') — the re-check was skipped on an open box"
fi

# ─────────────────────────────────────────────────────────────────────────
echo ""
echo "==================================================="
echo "  test-resume-does-not-reopen-finished-box: PASS=$PASS FAIL=$FAIL"
echo "==================================================="
if (( FAIL > 0 )); then
  echo "FAIL: $FAIL check(s) failed — CI guard triggered"
  exit 1
fi
echo "PASS: all BU-100 closed-out-box checks pass"
exit 0
