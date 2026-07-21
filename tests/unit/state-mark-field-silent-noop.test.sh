#!/usr/bin/env bash
# tests/unit/state-mark-field-silent-noop.test.sh
# ─────────────────────────────────────────────────────────────────────────────
# oc_state_mark_field silent-no-op regression lock (v20.0.86).
#
# THE BUG THIS LOCKS. lib-onboarding-state.sh's oc_state_mark_field carried
# `except Exception: return` inside its python heredoc -- a `return` outside any
# function. Python raises SyntaxError at COMPILE time, before the first
# statement executes, so the function never wrote a field on ANY path, INCLUDING
# the healthy one. The call site's `2>/dev/null || true` hid the error and
# forced rc 0, so every caller saw success. `bash -n` does not parse heredoc
# bodies, so no static check caught it either.
#
# It mattered in BOTH directions, because oc_wave_goal_check reads these fields:
#   * coreUpdatesSentinelPresent stayed at its seeded `false` forever -> check
#     (c) reported a missing sentinel for every skill shipping CORE_UPDATES.md.
#     A permanent FALSE FAILURE.
#   * qcExit stayed at its seeded `null` forever -> check (d) could never fire.
#     A permanently DEAD check that let a nonzero qc script clear the wave gate.
#
# WHAT THIS TEST PROVES (each assertion FAILS against the pre-fix lib, so none
# of them is vacuous -- run it against origin/main to see all of T1..T5 fail):
#   T1  the embedded python COMPILES at all              (the SyntaxError itself)
#   T2  HEALTHY file  -> the field is really written, verified by reading it BACK
#                        (not by grepping for the field NAME, which a seeded
#                        default would satisfy without any write happening)
#   T3  CORRUPT file  -> LOUD: rc 1 + a diagnostic on stderr
#   T4  ABSENT file   -> tolerated: rc 0, no crash, nothing created
#   T5  the wave gate consequence: with a real qcExit recorded, oc_wave_goal_check
#       actually fails a wave whose skill's qc script exited nonzero
#
# Hermetic: its own mktemp -d sandbox. No ~/.openclaw is touched, no network,
# no fleet box. bash 3.2-safe (macOS system bash). Exit 0 = all pass.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LIB="$REPO_ROOT/lib-onboarding-state.sh"

PASS=0
FAIL=0
ok()  { printf '  ✓ %s\n' "$1"; PASS=$((PASS + 1)); }
bad() { printf '  ✗ %s\n' "$1"; FAIL=$((FAIL + 1)); }
hdr() { printf '\n== %s ==\n' "$1"; }

[ -f "$LIB" ] || { echo "FATAL: $LIB not found"; exit 2; }

SANDBOX="$(mktemp -d)"
cleanup() { rm -rf "$SANDBOX"; }
trap cleanup EXIT

# ─────────────────────────────────────────────────────────────────────────────
hdr "T1 — the embedded python in oc_state_mark_field COMPILES"
# Extract the heredoc body of oc_state_mark_field and compile it. `compile()`,
# NOT ast.parse(): ast.parse ACCEPTS `return` outside a function and would have
# missed the exact defect this test exists to lock.
BODY="$SANDBOX/mark_field_body.py"
python3 - "$LIB" "$BODY" <<'EXTRACT'
import re, sys
src  = open(sys.argv[1], encoding="utf-8").read()
func = re.search(r"^oc_state_mark_field\(\)\s*\{(.*?)^\}", src, re.S | re.M)
if not func:
    sys.stderr.write("could not locate oc_state_mark_field in the lib\n")
    raise SystemExit(2)
m = re.search(r"<<-?\s*'?([A-Za-z_][A-Za-z0-9_]*)'?[^\n]*\n(.*?)^\1\s*$",
              func.group(1), re.S | re.M)
if not m:
    sys.stderr.write("oc_state_mark_field has no heredoc body\n")
    raise SystemExit(2)
open(sys.argv[2], "w", encoding="utf-8").write(m.group(2))
EXTRACT
if [ $? -ne 0 ]; then
  bad "could not extract the heredoc body"
else
  COMPILE_ERR="$(python3 -c 'import sys; compile(open(sys.argv[1]).read(), sys.argv[1], "exec")' "$BODY" 2>&1)"
  if [ $? -eq 0 ]; then
    ok "oc_state_mark_field's python body compiles"
  else
    bad "oc_state_mark_field's python body does NOT compile: $COMPILE_ERR"
  fi
fi

# ─────────────────────────────────────────────────────────────────────────────
hdr "T2 — HEALTHY state file: the field is actually written (read back)"
export OC_CONFIG="$SANDBOX/oc"
export OC_SKILLS_DIR="$SANDBOX/oc/skills"
mkdir -p "$OC_SKILLS_DIR"
export ONBOARDING_STATE_FILE="$SANDBOX/oc/.onboarding-state.json"
# shellcheck disable=SC1090
source "$LIB" >/dev/null 2>&1

printf '%s\n' '{"skills":{"01-demo":{"status":"qc-passed","qcExit":null}}}' > "$ONBOARDING_STATE_FILE"

oc_state_mark_field 01-demo qcExit 7
MF_RC=$?
[ "$MF_RC" -eq 0 ] && ok "returns 0 on a healthy file" \
                   || bad "returns $MF_RC on a healthy file (expected 0)"

# Read the VALUE back. Asserting only that the string "qcExit" appears in the
# file would pass against the broken version, because the seed already writes
# that key -- the bug was that its VALUE never changed.
READBACK="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["skills"]["01-demo"].get("qcExit"))' \
              "$ONBOARDING_STATE_FILE" 2>/dev/null)"
[ "$READBACK" = "7" ] && ok "qcExit reads back as 7" \
                      || bad "qcExit reads back as '$READBACK' (expected 7) — the write was a NO-OP"

oc_state_mark_field 01-demo registered true >/dev/null 2>&1
RB2="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["skills"]["01-demo"].get("registered"))' \
        "$ONBOARDING_STATE_FILE" 2>/dev/null)"
[ "$RB2" = "True" ] && ok "registered reads back as true (JSON bool, not the string)" \
                    || bad "registered reads back as '$RB2' (expected True)"

# A skill absent from the file must be created, not dropped.
oc_state_mark_field 02-new coreUpdatesSentinelPresent true >/dev/null 2>&1
RB3="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["skills"]["02-new"].get("coreUpdatesSentinelPresent"))' \
        "$ONBOARDING_STATE_FILE" 2>/dev/null)"
[ "$RB3" = "True" ] && ok "a new skill entry is created and recorded" \
                    || bad "new skill entry not recorded (got '$RB3')"

# ─────────────────────────────────────────────────────────────────────────────
hdr "T3 — CORRUPT state file: LOUD failure (rc 1 + stderr), never silent success"
printf '%s\n' '{"skills": {"01-demo": ' > "$ONBOARDING_STATE_FILE"   # truncated JSON
ERR_FILE="$SANDBOX/corrupt.err"
oc_state_mark_field 01-demo qcExit 0 2>"$ERR_FILE"
CRC=$?
[ "$CRC" -ne 0 ] && ok "returns nonzero (rc=$CRC) on a corrupt state file" \
                 || bad "returned 0 on a CORRUPT state file — silent success"
if [ -s "$ERR_FILE" ]; then
  ok "prints a diagnostic to stderr: $(head -1 "$ERR_FILE" | cut -c1-72)"
else
  bad "printed NOTHING to stderr on a corrupt state file"
fi

# Unreadable (present but chmod 000) must also be loud. Skipped when running as
# root, where the permission simply does not apply.
if [ "$(id -u)" -ne 0 ]; then
  printf '%s\n' '{"skills":{}}' > "$ONBOARDING_STATE_FILE"
  chmod 000 "$ONBOARDING_STATE_FILE"
  oc_state_mark_field 01-demo qcExit 0 >/dev/null 2>&1
  URC=$?
  chmod 644 "$ONBOARDING_STATE_FILE"
  [ "$URC" -ne 0 ] && ok "returns nonzero (rc=$URC) on an unreadable state file" \
                   || bad "returned 0 on an UNREADABLE state file — silent success"
else
  printf '  · skipped unreadable-file check (running as root)\n'
fi

# ─────────────────────────────────────────────────────────────────────────────
hdr "T4 — ABSENT state file: tolerated (rc 0), documented, and creates nothing"
rm -f "$ONBOARDING_STATE_FILE"
oc_state_mark_field 01-demo qcExit 0 >/dev/null 2>&1
ARC=$?
[ "$ARC" -eq 0 ] && ok "returns 0 when the state file is absent (seed owns creation)" \
                 || bad "returned $ARC on an ABSENT state file — absence must not be a hard failure"
[ ! -f "$ONBOARDING_STATE_FILE" ] && ok "does not fabricate a state file" \
                                  || bad "created a state file it does not own"

# ─────────────────────────────────────────────────────────────────────────────
hdr "T5 — consequence: a recorded nonzero qcExit really fails the wave gate"
# This is the check that was DEAD while qcExit could never leave `null`.
cat > "$ONBOARDING_STATE_FILE" <<'JSON'
{
  "skills": {
    "01-demo": { "status": "qc-passed", "hasCoreUpdates": false, "qcExit": null }
  },
  "waveGoals": {
    "wave1": { "skills": ["01-demo"], "status": "pending", "failStrikes": 0 }
  }
}
JSON
mkdir -p "$OC_SKILLS_DIR/01-demo"

oc_wave_goal_check 1 >/dev/null 2>&1
BASE_RC=$?
[ "$BASE_RC" -eq 0 ] && ok "control: the wave passes while qcExit is null" \
                     || bad "control failed (rc=$BASE_RC) — fixture is wrong, not the code"

oc_state_mark_field 01-demo qcExit 5 >/dev/null 2>&1
oc_wave_goal_check 1 >/dev/null 2>&1
GATE_RC=$?
[ "$GATE_RC" -ne 0 ] && ok "wave gate FAILS once qcExit=5 is really recorded" \
                     || bad "wave gate still PASSED with qcExit=5 — check (d) is dead"

# ─────────────────────────────────────────────────────────────────────────────
printf '\n────────────────────────────\n'
printf 'passed: %d   failed: %d\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
