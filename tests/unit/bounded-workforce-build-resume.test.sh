#!/usr/bin/env bash
# tests/unit/bounded-workforce-build-resume.test.sh
#
# CI guard for the STUCK-BUILD PARK LOOP fix (v14.1.5,
# fix/stuck-build-park-loop-durable). The onboarding-resume cron was already
# bounded (tests/unit/bounded-resume-cron.test.sh); this is the equivalent guard
# for the workforce-build-resume cron + the agent-browser circuit-breaker, which
# were the actual token furnace.
#
# Assertion groups:
#   (1) DURABLE_PARK         -- the PARK marker lives in the box's durable state
#                               dir (workspace/.park), NOT TMPDIR, so it survives
#                               a reboot. Same relative path in every actor.
#   (2) HARD_STUCK_CAP       -- resume-workforce-build.sh defines MAX_STUCK_FIRES
#                               (consecutive no-progress fires) and it is bounded.
#   (3) STUCK_CAP_DISABLES   -- the stuck-cap branch PARKS + self_remove_cron +
#                               exit 0, with NO "never stop / slow-retry forever /
#                               NOT self-removing" language. The OLD never-stop
#                               run-accounting (MAX_RUNS_BEFORE_SELF_REMOVE /
#                               "NEVER-STOP: run #") is GONE.
#   (4) PARK_GATE_STOPS      -- an already-parked build stops immediately
#                               (park_is_set -> self_remove_cron -> exit 0).
#   (5) REGISTRAR_PARK_AWARE -- ensure-pipeline-crons.sh does NOT re-register a
#                               parked box's resume cron.
#   (6) INSTALL_PARK_AWARE   -- install.sh does NOT (re)install a parked box's
#                               resume cron.
#   (7) BREAKER_DURABLE      -- browser_manager.sh breaker/PARK state is durable
#                               (no longer hard-pinned to $LOCKDIR/breaker), the
#                               breaker READS the box park marker, and a trip
#                               WRITES it (cross-stop the resume cron).
#   (8) UNPARK_PATH          -- scripts/unpark-build.sh exists, is bash -n clean,
#                               clears the park marker, and re-registers the cron.
#
# v21.x adds FUNCTIONAL groups. These do not grep the source, they RUN
# resume-workforce-build.sh against hermetic fixtures and assert on what it
# actually did (which crons it removed, which messages it dispatched, what it
# wrote back to the state). Each is paired with a MUTATION PROOF: the same
# fixture run against a sandboxed copy of the script with ONLY that fix reverted
# must exhibit the OLD broken behavior — so none of these assertions can pass
# vacuously.
#
#   (9)  BELT_CONTRACT_GUARD -- an agent-written top-level `.status=done` while the
#                               libraries are failed and buildCompletedAt is empty
#                               must NOT self-remove the cron (even with the
#                               department floor satisfied), and the [LIBRARY-RESUME]
#                               repair lane must still dispatch. This is the defect
#                               that killed the ONLY autonomous-recovery layer on a
#                               box minutes after its interview completed.
#   (10) STATUS_VOCABULARY   -- departments written as status "complete" (the synonym
#                               agents use) are normalized to the contract word "done"
#                               so the counters, the library gate and HOP-4 can see
#                               them at all.
#   (11) QC_BUILD_ELIGIBLE   -- an interview whose QC verdict is `needs-review` (which
#                               update-interview-state.sh ALREADY accepts as complete)
#                               must be build-eligible, not a permanent dead end.
#   (12) INTERNAL_NOT_TO_OWNER -- internal resume/kick traffic routes to the operator
#                               chat, never the client's own chat.
#   (13) KICK_NOT_SUPPRESSED -- a reopened / re-completed interview on a box that
#                               already carries departments must STILL dispatch a
#                               build kick. The old guard counted department entries
#                               and swallowed the kick entirely on such a box.
#   (14) SEND_IS_NOT_A_TURN  -- `openclaw message send` rc=0 means the message was
#                               SENT, not that an agent turn RAN. A bare successful
#                               send must not set the 20-minute in-flight marker nor
#                               advance the absolute ping ceiling (which parks the
#                               build and removes this cron), or the lane suppresses
#                               its own retries on a success that triggered nothing.
#
# HERMETIC: every functional group sandboxes HOME *and* runs a COPY of the script
# from inside the sandbox, so SCRIPT_DIR-resolved siblings (department-floor.py,
# department-optout-sync.py, run-closeout.sh, ...) resolve into the fixture and NO
# real Skill-23 script and no real ~/.openclaw is ever touched.
#
# Exit 0 = all checks pass. Exit 1 = one or more failed (CI FAIL).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

RESUME="$REPO_ROOT/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh"
ENSURE="$REPO_ROOT/scripts/ensure-pipeline-crons.sh"
INSTALL="$REPO_ROOT/install.sh"
BMGR="$REPO_ROOT/06-ghl-install-pages/tools/browser_manager.sh"
UNPARK="$REPO_ROOT/scripts/unpark-build.sh"

MARKER_REL="workspace/.park/workforce-build.parked"

echo "=== bounded-workforce-build-resume.test.sh ==="
echo ""

# ---------------------------------------------------------------------------
# (1) DURABLE_PARK
# ---------------------------------------------------------------------------
echo "--- (1) DURABLE_PARK: park marker in the durable state dir, not TMPDIR ---"
if [[ -f "$RESUME" ]]; then
  if grep -q 'PARK_DIR="\$OC_ROOT/workspace/.park"' "$RESUME" \
     && grep -q "BOX_PARK_MARKER=\"\$PARK_DIR/workforce-build.parked\"" "$RESUME"; then
    pass "1a: resume-workforce-build.sh PARK_DIR is \$OC_ROOT/workspace/.park (durable)"
  else
    fail "1a: resume-workforce-build.sh PARK_DIR/BOX_PARK_MARKER not anchored to \$OC_ROOT/workspace/.park"
  fi
  if grep -qE 'BOX_PARK_MARKER=.*(TMPDIR|/tmp)' "$RESUME"; then
    fail "1b: resume-workforce-build.sh park marker references TMPDIR/tmp (would evaporate on reboot)"
  else
    pass "1b: resume-workforce-build.sh park marker does NOT use TMPDIR/tmp"
  fi
else
  fail "1: resume-workforce-build.sh not found at $RESUME"
fi

# Every actor must agree on the SAME marker path. It is composed from a durable
# dir ending in `workspace/.park` and the file `workforce-build.parked` — some
# actors build it across two assignments (PARK_DIR=…/workspace/.park then
# …/workforce-build.parked), so assert BOTH components are present.
for f in "$RESUME" "$ENSURE" "$INSTALL" "$BMGR" "$UNPARK"; do
  bn="$(basename "$f")"
  if [[ -f "$f" ]] && grep -Fq "workspace/.park" "$f" && grep -Fq "workforce-build.parked" "$f"; then
    pass "1c-$bn: composes the canonical marker path ($MARKER_REL)"
  else
    fail "1c-$bn: does NOT compose the canonical marker path ($MARKER_REL)"
  fi
done

# ---------------------------------------------------------------------------
# (2) HARD_STUCK_CAP
# ---------------------------------------------------------------------------
echo ""
echo "--- (2) HARD_STUCK_CAP: MAX_STUCK_FIRES defined + bounded ---"
if [[ -f "$RESUME" ]]; then
  cap_line="$(grep 'MAX_STUCK_FIRES=' "$RESUME" | grep -v '^[[:space:]]*#' | head -1 || true)"
  if [[ -z "$cap_line" ]]; then
    fail "2a: MAX_STUCK_FIRES not defined in resume-workforce-build.sh"
  else
    pass "2a: MAX_STUCK_FIRES defined ($cap_line)"
    # The literal default must be an integer within a sane range (2..96).
    def_val="$(printf '%s' "$cap_line" | grep -oE ':-[0-9]+' | grep -oE '[0-9]+' | head -1 || true)"
    if [[ -z "$def_val" ]]; then
      fail "2b: could not parse MAX_STUCK_FIRES default integer"
    elif (( def_val < 2 || def_val > 96 )); then
      fail "2b: MAX_STUCK_FIRES default $def_val out of safe range 2..96"
    else
      pass "2b: MAX_STUCK_FIRES default $def_val within safe range (2..96)"
    fi
  fi
fi

# ---------------------------------------------------------------------------
# (3) STUCK_CAP_DISABLES + old never-stop furnace removed
# ---------------------------------------------------------------------------
echo ""
echo "--- (3) STUCK_CAP_DISABLES: cap branch parks + self_remove_cron + exit 0 ---"
if [[ -f "$RESUME" ]]; then
  cap_block="$(awk '/_stuck >= MAX_STUCK_FIRES/,/exit 0/' "$RESUME" 2>/dev/null | head -60 || true)"
  if [[ -z "$cap_block" ]]; then
    fail "3a: could not extract the stuck-cap branch"
  else
    echo "$cap_block" | grep -q 'park_set'        && pass "3a: stuck-cap branch PARKS (park_set)"        || fail "3a: stuck-cap branch does NOT park_set"
    echo "$cap_block" | grep -q 'self_remove_cron' && pass "3b: stuck-cap branch self_remove_cron"        || fail "3b: stuck-cap branch does NOT self_remove_cron"
    echo "$cap_block" | grep -q 'exit 0'          && pass "3c: stuck-cap branch exit 0 (bounded)"        || fail "3c: stuck-cap branch does not exit 0"
    if echo "$cap_block" | grep -qiE 'NOT self.remov|slow.retry|never stop|keep retrying'; then
      fail "3d: stuck-cap branch contains perpetual-loop language"
    else
      pass "3d: stuck-cap branch has no perpetual-loop language"
    fi
  fi
  # The OLD never-stop run-accounting furnace must be GONE.
  if grep -qE 'MAX_RUNS_BEFORE_SELF_REMOVE|NEVER-STOP: run #' "$RESUME"; then
    fail "3e: OLD never-stop run-accounting still present (MAX_RUNS_BEFORE_SELF_REMOVE / 'NEVER-STOP: run #')"
  else
    pass "3e: OLD never-stop run-accounting furnace removed"
  fi
fi

# ---------------------------------------------------------------------------
# (4) PARK_GATE_STOPS
# ---------------------------------------------------------------------------
echo ""
echo "--- (4) PARK_GATE_STOPS: already-parked build stops immediately ---"
if [[ -f "$RESUME" ]]; then
  gate_block="$(awk '/if park_is_set; then/,/^fi$/' "$RESUME" 2>/dev/null | head -8 || true)"
  if echo "$gate_block" | grep -q 'self_remove_cron' && echo "$gate_block" | grep -q 'exit 0'; then
    pass "4a: park gate calls self_remove_cron + exit 0 when parked"
  else
    fail "4a: park gate does not stop (self_remove_cron + exit 0) when parked"
  fi
fi

# ---------------------------------------------------------------------------
# (5) REGISTRAR_PARK_AWARE
# ---------------------------------------------------------------------------
echo ""
echo "--- (5) REGISTRAR_PARK_AWARE: ensure-pipeline-crons.sh skips a parked box ---"
if [[ -f "$ENSURE" ]]; then
  reg_block="$(awk '/_ensure_workforce_build_resume\(\)/,/_cron_present "workforce-build-resume"/' "$ENSURE" 2>/dev/null | head -20 || true)"
  if echo "$reg_block" | grep -q 'BOX_PARK_MARKER' && echo "$reg_block" | grep -qi 'PARKED'; then
    pass "5a: _ensure_workforce_build_resume checks BOX_PARK_MARKER and skips when parked"
  else
    fail "5a: _ensure_workforce_build_resume is NOT park-aware (would resurrect a parked cron)"
  fi
else
  fail "5: ensure-pipeline-crons.sh not found"
fi

# ---------------------------------------------------------------------------
# (6) INSTALL_PARK_AWARE
# ---------------------------------------------------------------------------
echo ""
echo "--- (6) INSTALL_PARK_AWARE: install.sh skips a parked box ---"
if [[ -f "$INSTALL" ]]; then
  inst_block="$(awk '/install_workforce_resume_cron\(\)/,/workforce-build-resume" *; then/' "$INSTALL" 2>/dev/null | head -25 || true)"
  if echo "$inst_block" | grep -q 'workforce-build.parked'; then
    pass "6a: install_workforce_resume_cron checks the park marker before installing"
  else
    fail "6a: install_workforce_resume_cron is NOT park-aware"
  fi
else
  fail "6: install.sh not found"
fi

# ---------------------------------------------------------------------------
# (7) BREAKER_DURABLE
# ---------------------------------------------------------------------------
echo ""
echo "--- (7) BREAKER_DURABLE: agent-browser breaker/PARK state is durable + cross-stops ---"
if [[ -f "$BMGR" ]]; then
  # The breaker marker functions must NOT be pinned to the ephemeral TMPDIR dir.
  if grep -qE '_bm_breaker_marker\(\).*LOCKDIR/breaker' "$BMGR"; then
    fail "7a: breaker marker still hard-pinned to \$LOCKDIR/breaker (TMPDIR — evaporates on reboot)"
  else
    pass "7a: breaker marker no longer hard-pinned to \$LOCKDIR/breaker"
  fi
  grep -q 'BM_BOX_PARK_MARKER=' "$BMGR" \
    && pass "7b: browser_manager.sh defines the canonical BM_BOX_PARK_MARKER" \
    || fail "7b: browser_manager.sh missing BM_BOX_PARK_MARKER"
  # bm_breaker_check must READ the box park marker.
  bc_block="$(awk '/bm_breaker_check\(\)/,/^}/' "$BMGR" 2>/dev/null || true)"
  echo "$bc_block" | grep -q 'BM_BOX_PARK_MARKER' \
    && pass "7c: bm_breaker_check READS the box park marker (breaker honors the marker)" \
    || fail "7c: bm_breaker_check does NOT read the box park marker"
  # A trip must WRITE the box park marker (so the resume cron stops too).
  if echo "$bc_block" | grep -q '> "\$BM_BOX_PARK_MARKER"'; then
    pass "7d: a breaker trip WRITES the box park marker (cross-stops the resume cron)"
  else
    fail "7d: a breaker trip does NOT write the box park marker"
  fi
else
  fail "7: browser_manager.sh not found"
fi

# ---------------------------------------------------------------------------
# (8) UNPARK_PATH
# ---------------------------------------------------------------------------
echo ""
echo "--- (8) UNPARK_PATH: operator un-park script present + sound ---"
if [[ -f "$UNPARK" ]]; then
  if bash -n "$UNPARK" 2>/dev/null; then
    pass "8a: unpark-build.sh is bash -n clean"
  else
    fail "8a: unpark-build.sh has a syntax error"
  fi
  grep -q 'rm -f "\$BOX_PARK_MARKER"' "$UNPARK" \
    && pass "8b: unpark-build.sh clears the park marker" \
    || fail "8b: unpark-build.sh does NOT clear the park marker"
  grep -q 'ensure-pipeline-crons.sh' "$UNPARK" \
    && pass "8c: unpark-build.sh re-registers the resume cron" \
    || fail "8c: unpark-build.sh does NOT re-register the resume cron"
else
  fail "8: scripts/unpark-build.sh not found"
fi

# ===========================================================================
# FUNCTIONAL GROUPS (9)-(12) — run the script, assert on behavior
# ===========================================================================

FAKE_OC="$REPO_ROOT/tests/fixtures/fake-openclaw-cron.py"
FUNCTIONAL=1
if [[ ! -f "$FAKE_OC" ]]; then
  echo ""
  echo "!! functional groups SKIPPED: $FAKE_OC not found"
  FUNCTIONAL=0
fi
if [[ -d /data/.openclaw ]]; then
  # resume-workforce-build.sh resolves OC_ROOT as /data/.openclaw FIRST and offers
  # no override. On a host that has one we cannot guarantee the fixture is isolated,
  # so we refuse to run rather than risk writing into a real workspace.
  echo ""
  echo "!! functional groups SKIPPED: /data/.openclaw exists on this host — cannot guarantee fixture isolation"
  FUNCTIONAL=0
fi
if ! command -v jq >/dev/null 2>&1; then
  echo ""
  echo "!! functional groups SKIPPED: jq not installed"
  FUNCTIONAL=0
fi

if (( FUNCTIONAL == 1 )); then

# The functional groups below assert EXPLICITLY on outcomes, and several of them
# deliberately run commands that are expected to exit non-zero (a refused
# --complete, a script with a fix reverted). errexit would abort the whole file on
# the first one, so it is disabled for this section only; every check below is an
# explicit pass()/fail() and nothing is silently ignored.
set +e

SANDBOX="$(mktemp -d)"
cleanup_sandbox() { rm -rf "$SANDBOX" 2>/dev/null || true; }
trap cleanup_sandbox EXIT
case "$SANDBOX" in
  */.openclaw|*/.openclaw/*) echo "REFUSING: sandbox resolved into a real .openclaw ($SANDBOX)"; exit 2 ;;
esac

RESUME_CRON_UUID="aabbccdd-1122-3344-5566-778899aabbcc"

# Build one hermetic box. Echoes the box HOME.
#   $1 = box name   $2 = build-state JSON   $3 = space-separated dept ids needing
#                                                a real how-to.md on disk
_mkbox() {
  local name="$1" state_json="$2" depts="${3:-}"
  local h="$SANDBOX/$name"
  local skill="$h/.openclaw/skills/23-ai-workforce-blueprint/scripts"
  mkdir -p "$skill" "$h/.openclaw/workspace" "$h/bin"

  # The script under test runs FROM the sandbox, so every SCRIPT_DIR sibling it
  # probes resolves inside the fixture. Only the stub floor checker is provided.
  cp "$RESUME" "$skill/resume-workforce-build.sh"
  cat > "$skill/department-floor.py" <<'PYEOF'
import sys
# Stub: department floor SATISFIED (rc=0). The point of group (9) is that a
# satisfied floor must STILL not license self-removal on an open contract.
sys.exit(0)
PYEOF

  cat > "$h/bin/openclaw" <<SHIM
#!/usr/bin/env bash
exec python3 "$FAKE_OC" "\$@"
SHIM
  chmod +x "$h/bin/openclaw"

  printf '%s' "$state_json" > "$h/.openclaw/workspace/.workforce-build-state.json"
  printf '[{"name":"workforce-build-resume","id":"%s","kind":"command"}]' "$RESUME_CRON_UUID" \
    > "$h/jobs.json"
  : > "$h/calls.log"

  # The DISK-REALITY stale-state reset demotes any department claiming done that
  # has no substantial how-to.md on disk. Give the ones we want to stay 'done' a
  # real file (>= 256 bytes, no [PENDING marker) so the fixture is not silently
  # rewritten out from under the assertions.
  local d
  for d in $depts; do
    mkdir -p "$h/.openclaw/workspace/departments/$d/lead"
    { echo "# how-to"; for _ in $(seq 1 12); do
        echo "Operating procedure line for the $d department role workspace."
      done; } > "$h/.openclaw/workspace/departments/$d/lead/how-to.md"
  done
  printf '%s' "$h"
}

# Run a box. $1 = box home, $2 = script to execute, rest = extra env assignments.
_runbox() {
  local h="$1" script="$2"; shift 2
  env -i \
    PATH="$h/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin" \
    HOME="$h" \
    TMPDIR="${TMPDIR:-/tmp}" \
    FAKE_OC_JOBS_FILE="$h/jobs.json" \
    FAKE_OC_CALLS_FILE="$h/calls.log" \
    OPERATOR_ESCALATION_CHAT_ID="555000111" \
    "$@" \
    bash "$script" >"$h/run.out" 2>&1
  return 0
}

# Revert exactly one fix in a sandboxed copy, to prove an assertion discriminates.
# $1 = copy path, $2 = python heredoc body performing the anchored replacement.
_mutate() {
  local target="$1"; shift
  python3 - "$target" "$@"
}

STATE_ALL_DONE_SOP_FAILED='{
  "interviewComplete": true,
  "interviewQc": {"status": "pass"},
  "status": "done",
  "closeoutStatus": "pending",
  "roleLibraryStatus": "done",
  "sopLibraryStatus": "failed",
  "ownerChat": "111222333",
  "agentName": "TestOrchestrator",
  "departments": [
    {"id": "alpha", "status": "done"},
    {"id": "bravo", "status": "done"},
    {"id": "charlie", "status": "done"}
  ]
}'

# ---------------------------------------------------------------------------
# (9) BELT_CONTRACT_GUARD
# ---------------------------------------------------------------------------
echo ""
echo "--- (9) BELT_CONTRACT_GUARD: agent-written .status=done + failed library must NOT self-remove ---"
BOX9="$(_mkbox box9 "$STATE_ALL_DONE_SOP_FAILED" "alpha bravo charlie")"
_runbox "$BOX9" "$BOX9/.openclaw/skills/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh"
CALLS9="$BOX9/calls.log"
SLOG9="$BOX9/.openclaw/workspace/.workforce-build-state.log"

if grep -q "^cron rm" "$CALLS9" 2>/dev/null; then
  fail "9a: the cron was SELF-REMOVED on an open contract (closeout=pending, buildCompletedAt unset, sopLibraryStatus=failed)"
else
  pass "9a: cron NOT self-removed while the delivery contract is open"
fi

if grep -q "LIBRARY-RESUME" "$CALLS9" 2>/dev/null; then
  pass "9b: the [LIBRARY-RESUME] repair lane still dispatched (recovery layer alive)"
else
  fail "9b: no [LIBRARY-RESUME] dispatch — the repair lane did not run"
fi

if grep -q "REFUSING to treat this build as terminal" "$SLOG9" 2>/dev/null; then
  pass "9c: the belt logged WHY it refused the terminal state"
else
  fail "9c: the belt did not log a refusal reason"
fi

# ---------------------------------------------------------------------------
# (9-MUT) the same fixture against the pre-fix belt MUST self-remove
# ---------------------------------------------------------------------------
echo ""
echo "--- (9-MUT) MUTATION PROOF: pre-fix belt on the SAME fixture self-removes and never repairs ---"
BOX9M="$(_mkbox box9m "$STATE_ALL_DONE_SOP_FAILED" "alpha bravo charlie")"
MUT9="$BOX9M/.openclaw/skills/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh"
_mutate "$MUT9" <<'PYEOF'
import sys
path = sys.argv[1]
src = open(path).read()
start = src.index("    done|complete)\n      # Honor the agent-written word ONLY")
end = src.index("    failed)\n      _terminal=1 ;;", start)
old = src[start:end]
new = "    done|complete)\n      _terminal=1 ;;\n"
open(path, "w").write(src[:start] + new + src[end:])
PYEOF
mut9_rc=$?
if (( mut9_rc != 0 )); then
  fail "9-MUT: could not revert the belt contract guard — cannot prove 9a/9b discriminate"
else
  _runbox "$BOX9M" "$MUT9"
  CALLS9M="$BOX9M/calls.log"
  if grep -q "^cron rm $RESUME_CRON_UUID" "$CALLS9M" 2>/dev/null; then
    pass "9-MUT-a: pre-fix belt DOES self-remove the cron on this fixture — 9a is a real, non-vacuous check"
  else
    fail "9-MUT-a: pre-fix belt did not self-remove — the mutation harness or fixture is wrong, 9a proves nothing"
  fi
  if grep -q "LIBRARY-RESUME" "$CALLS9M" 2>/dev/null; then
    fail "9-MUT-b: pre-fix belt still dispatched [LIBRARY-RESUME] — 9b proves nothing"
  else
    pass "9-MUT-b: pre-fix belt made NO repair dispatch — 9b is a real, non-vacuous check"
  fi
fi

# ---------------------------------------------------------------------------
# (10) STATUS_VOCABULARY
# ---------------------------------------------------------------------------
echo ""
echo "--- (10) STATUS_VOCABULARY: departments written as 'complete' are normalized to 'done' ---"
STATE_VOCAB='{
  "interviewComplete": true,
  "interviewQc": {"status": "pass"},
  "closeoutStatus": "pending",
  "roleLibraryStatus": "complete",
  "sopLibraryStatus": "pending",
  "ownerChat": "111222333",
  "agentName": "TestOrchestrator",
  "departments": [
    {"id": "alpha", "status": "complete"},
    {"id": "bravo", "status": "complete"},
    {"id": "charlie", "status": "complete"}
  ]
}'
BOX10="$(_mkbox box10 "$STATE_VOCAB" "alpha bravo charlie")"
_runbox "$BOX10" "$BOX10/.openclaw/skills/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh"
ST10="$BOX10/.openclaw/workspace/.workforce-build-state.json"
n_done10=$(jq -r '[.departments[] | select(.status == "done")] | length' "$ST10" 2>/dev/null || echo 0)
rl10=$(jq -r '.roleLibraryStatus // ""' "$ST10" 2>/dev/null || echo "")
[ "$n_done10" = "3" ] && pass "10a: all 3 departments normalized 'complete' -> 'done'" \
                      || fail "10a: only $n_done10/3 departments normalized to 'done'"
[ "$rl10" = "done" ] && pass "10b: roleLibraryStatus normalized 'complete' -> 'done'" \
                     || fail "10b: roleLibraryStatus is '$rl10' (expected 'done')"
if grep -q "LIBRARY-RESUME" "$BOX10/calls.log" 2>/dev/null; then
  pass "10c: with the synonym resolved the library gate armed and dispatched [LIBRARY-RESUME]"
else
  fail "10c: no [LIBRARY-RESUME] dispatch — the gate still cannot see the departments"
fi

echo ""
echo "--- (10-MUT) MUTATION PROOF: without the normalizer the same box does nothing at all ---"
BOX10M="$(_mkbox box10m "$STATE_VOCAB" "alpha bravo charlie")"
MUT10="$BOX10M/.openclaw/skills/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh"
_mutate "$MUT10" <<'PYEOF'
import sys
path = sys.argv[1]
src = open(path).read()
anchor = "\nnormalize_status_vocabulary\n"
if anchor not in src:
    sys.exit(1)
open(path, "w").write(src.replace(anchor, "\n", 1))
PYEOF
mut10_rc=$?
if (( mut10_rc != 0 )); then
  fail "10-MUT: could not remove the normalizer call — cannot prove 10a-c discriminate"
else
  _runbox "$BOX10M" "$MUT10"
  ST10M="$BOX10M/.openclaw/workspace/.workforce-build-state.json"
  n_done10m=$(jq -r '[.departments[] | select(.status == "done")] | length' "$ST10M" 2>/dev/null || echo 0)
  if [ "$n_done10m" = "0" ] && ! grep -q "LIBRARY-RESUME" "$BOX10M/calls.log" 2>/dev/null; then
    pass "10-MUT: without the normalizer every counter reads done=0 and NOTHING is dispatched — 10a-c are real checks"
  else
    fail "10-MUT: un-normalized box still counted $n_done10m done / dispatched — 10a-c prove nothing"
  fi
fi

# ---------------------------------------------------------------------------
# (11) QC_BUILD_ELIGIBLE — needs-review must not be a dead end
# ---------------------------------------------------------------------------
echo ""
echo "--- (11) QC_BUILD_ELIGIBLE: interviewQc=needs-review is build-eligible, not a permanent strand ---"
STATE_NEEDS_REVIEW='{
  "interviewComplete": true,
  "interviewQc": {"status": "needs-review"},
  "closeoutStatus": "pending",
  "roleLibraryStatus": "pending",
  "sopLibraryStatus": "pending",
  "ownerChat": "111222333",
  "agentName": "TestOrchestrator",
  "departments": [{"id": "alpha", "status": "pending"}]
}'
BOX11="$(_mkbox box11 "$STATE_NEEDS_REVIEW")"
_runbox "$BOX11" "$BOX11/.openclaw/skills/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh"
if grep -q "WORKFORCE-RESUME" "$BOX11/calls.log" 2>/dev/null; then
  pass "11a: a needs-review interview dispatched a build resume (the build lane proceeds)"
else
  fail "11a: no build dispatch for a needs-review interview — still a dead end"
fi
if grep -q "QC-RESUME" "$BOX11/calls.log" 2>/dev/null; then
  fail "11b: the QC gate still blocked a needs-review interview"
else
  pass "11b: the QC gate did not block needs-review"
fi

echo ""
echo "--- (11-MUT) MUTATION PROOF: the strict pass-only gate strands the same box ---"
BOX11M="$(_mkbox box11m "$STATE_NEEDS_REVIEW")"
MUT11="$BOX11M/.openclaw/skills/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh"
_mutate "$MUT11" <<'PYEOF'
import sys
path = sys.argv[1]
src = open(path).read()
old = '_qc_build_eligible() { case "${1:-}" in pass|needs-review) return 0 ;; *) return 1 ;; esac; }'
new = '_qc_build_eligible() { case "${1:-}" in pass) return 0 ;; *) return 1 ;; esac; }'
if old not in src:
    sys.exit(1)
open(path, "w").write(src.replace(old, new, 1))
PYEOF
mut11_rc=$?
if (( mut11_rc != 0 )); then
  fail "11-MUT: could not narrow the eligibility predicate — cannot prove 11a/11b discriminate"
else
  _runbox "$BOX11M" "$MUT11"
  if grep -q "WORKFORCE-RESUME" "$BOX11M/calls.log" 2>/dev/null; then
    fail "11-MUT: pass-only gate still dispatched a build — 11a proves nothing"
  else
    pass "11-MUT: pass-only gate strands the box (no build dispatch) — 11a/11b are real checks"
  fi
fi

# ---------------------------------------------------------------------------
# (12) INTERNAL_NOT_TO_OWNER
# ---------------------------------------------------------------------------
echo ""
echo "--- (12) INTERNAL_NOT_TO_OWNER: internal resume traffic must not go to the client's chat ---"
# Box 9 had BOTH an operator chat (env) and an ownerChat (state) available.
if grep -E "^message send .*-t 111222333" "$CALLS9" >/dev/null 2>&1; then
  fail "12a: an internal resume message was delivered to the OWNER chat while an operator chat was configured"
else
  pass "12a: no internal resume message was delivered to the owner chat"
fi
if grep -E "^message send .*-t 555000111" "$CALLS9" >/dev/null 2>&1; then
  pass "12b: internal resume traffic routed to the operator escalation chat"
else
  fail "12b: internal resume traffic did not route to the operator chat"
fi

# update-interview-state.sh must resolve the operator chat BEFORE .ownerChat.
UPD="$REPO_ROOT/23-ai-workforce-blueprint/scripts/update-interview-state.sh"
if [[ -f "$UPD" ]]; then
  first_kick_src="$(grep -n 'KICK_CHAT=' "$UPD" | grep -v '^[[:space:]]*#' | head -1 || true)"
  case "$first_kick_src" in
    *OPERATOR_ESCALATION_CHAT_ID*)
      pass "12c: update-interview-state.sh resolves the OPERATOR chat first for the internal build kick" ;;
    *ownerChat*)
      fail "12c: update-interview-state.sh still resolves .ownerChat FIRST — internal build-kick text is delivered to the client" ;;
    *)
      fail "12c: could not determine the build-kick chat resolution order in update-interview-state.sh" ;;
  esac
  # The kick must NOT be suppressed merely because department ENTRIES exist. Assert
  # on live code, not comments (the defect is described in a comment above the fix).
  if grep -vE '^\s*#' "$UPD" | grep -q 'active_depts'; then
    fail "12d: the build kick is still gated on active_depts — a reopened interview on a box with existing departments gets NO kick"
  else
    pass "12d: the build kick is no longer gated on the presence of department entries"
  fi
else
  fail "12: update-interview-state.sh not found at $UPD"
fi

# ---------------------------------------------------------------------------
# (13) KICK_NOT_SUPPRESSED_BY_EXISTING_DEPTS — functional
# A reopened / re-completed interview on a box that already carries departments
# MUST still dispatch a build kick. This is the case that silently got nothing.
# ---------------------------------------------------------------------------
echo ""
echo "--- (13) KICK_NOT_SUPPRESSED: departments present + buildCompletedAt empty MUST still kick ---"
LIBRL="$REPO_ROOT/23-ai-workforce-blueprint/scripts/lib-interview-rate-limit.sh"
if [[ ! -f "$UPD" || ! -f "$LIBRL" ]]; then
  fail "13: update-interview-state.sh or lib-interview-rate-limit.sh missing — cannot run"
else
  # Hermetic box for the interview writer: its own scripts dir, its own HOME.
  # qc-interview-completion.py is STUBBED (the real one is a Skill-23 script and is
  # never executed here); it writes the verdict the evidence gate reads.
  _mkupdbox() {
    local name="$1" state_json="$2" verdict="$3"
    local h="$SANDBOX/$name"
    local skill="$h/.openclaw/skills/23-ai-workforce-blueprint/scripts"
    mkdir -p "$skill" "$h/.openclaw/workspace" "$h/bin"
    cp "$UPD" "$skill/update-interview-state.sh"
    cp "$LIBRL" "$skill/lib-interview-rate-limit.sh"
    cat > "$skill/qc-interview-completion.py" <<PYEOF
import json, sys
# Stub QC gate: stamps the verdict this fixture is exercising, then exits 0 (PASS).
p = sys.argv[sys.argv.index("--state") + 1]
d = json.load(open(p))
d.setdefault("interviewQc", {})["status"] = "$verdict"
json.dump(d, open(p, "w"), indent=2)
sys.exit(0)
PYEOF
    cat > "$h/bin/openclaw" <<SHIM
#!/usr/bin/env bash
exec python3 "$FAKE_OC" "\$@"
SHIM
    chmod +x "$h/bin/openclaw"
    printf '%s' "$state_json" > "$h/.openclaw/workspace/.workforce-build-state.json"
    printf '[]' > "$h/jobs.json"
    : > "$h/calls.log"
    printf '%s' "$h"
  }

  # Departments already present from a prior partial build; build NOT complete.
  STATE_REOPENED='{
    "interviewComplete": false,
    "ownerChat": "111222333",
    "agentName": "TestOrchestrator",
    "closeoutStatus": "pending",
    "departments": [
      {"id": "alpha", "status": "done"},
      {"id": "bravo", "status": "building"},
      {"id": "charlie", "status": "pending"}
    ]
  }'
  BOX13="$(_mkupdbox box13 "$STATE_REOPENED" pass)"
  env -i PATH="$BOX13/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin" HOME="$BOX13" \
    TMPDIR="${TMPDIR:-/tmp}" FAKE_OC_JOBS_FILE="$BOX13/jobs.json" \
    FAKE_OC_CALLS_FILE="$BOX13/calls.log" OPERATOR_ESCALATION_CHAT_ID="555000111" \
    bash "$BOX13/.openclaw/skills/23-ai-workforce-blueprint/scripts/update-interview-state.sh" \
      --complete --phase 6 --question-number 30 --asked-by tester >"$BOX13/run.out" 2>&1
  if grep -q "WORKFORCE-RESUME" "$BOX13/calls.log" 2>/dev/null; then
    pass "13a: the build kick dispatched even though 3 departments already existed"
  else
    fail "13a: NO build kick with departments already present — the strand is still open ($(tail -2 "$BOX13/run.out" | tr '\n' ' '))"
  fi
  if grep -E "^message send .*-t 111222333" "$BOX13/calls.log" >/dev/null 2>&1; then
    fail "13b: the internal build kick was delivered to the OWNER chat"
  else
    pass "13b: the internal build kick avoided the owner chat"
  fi

  echo ""
  echo "--- (13-MUT) MUTATION PROOF: the old active_depts guard swallows this kick ---"
  BOX13M="$(_mkupdbox box13m "$STATE_REOPENED" pass)"
  MUT13="$BOX13M/.openclaw/skills/23-ai-workforce-blueprint/scripts/update-interview-state.sh"
  _mutate "$MUT13" <<'PYEOF'
import sys
path = sys.argv[1]
src = open(path).read()
old = '  if [ "$qc_kick_eligible" = true ] && [ -z "$kick_blocked_reason" ]; then'
new = ('  active_depts=$(jq -r \'[.departments[]? | select(.status != "pending")] | length\' "$STATE" 2>/dev/null || echo 0)\n'
       '  if [ "$qc_kick_eligible" = true ] && [ "${active_depts:-0}" = "0" ]; then')
if old not in src:
    sys.exit(1)
open(path, "w").write(src.replace(old, new, 1))
PYEOF
  mut13_rc=$?
  if (( mut13_rc != 0 )); then
    fail "13-MUT: could not restore the active_depts guard — cannot prove 13a discriminates"
  else
    env -i PATH="$BOX13M/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin" HOME="$BOX13M" \
      TMPDIR="${TMPDIR:-/tmp}" FAKE_OC_JOBS_FILE="$BOX13M/jobs.json" \
      FAKE_OC_CALLS_FILE="$BOX13M/calls.log" OPERATOR_ESCALATION_CHAT_ID="555000111" \
      bash "$MUT13" --complete --phase 6 --question-number 30 --asked-by tester >"$BOX13M/run.out" 2>&1
    if grep -q "WORKFORCE-RESUME" "$BOX13M/calls.log" 2>/dev/null; then
      fail "13-MUT: the old guard still dispatched — 13a proves nothing"
    else
      pass "13-MUT: the old active_depts guard swallows the kick entirely — 13a is a real, non-vacuous check"
    fi
  fi
fi

# ---------------------------------------------------------------------------
# (14) SEND_IS_NOT_A_TURN — a successful outbound send must not suppress retries
# `openclaw message send` rc=0 means the message was SENT, not that an agent turn
# RAN. Counting it as a turn made this lane set a 20-minute in-flight marker and
# advance the absolute ping ceiling (which parks the build and removes the cron)
# on dispatches that triggered nothing.
# ---------------------------------------------------------------------------
echo ""
echo "--- (14) SEND_IS_NOT_A_TURN: a successful send must not set the in-flight marker or the ping ceiling ---"
BOX14="$(_mkbox box14 "$STATE_ALL_DONE_SOP_FAILED" "alpha bravo charlie")"
_runbox "$BOX14" "$BOX14/.openclaw/skills/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh"
WS14="$BOX14/.openclaw/workspace"
if grep -q "LIBRARY-RESUME" "$BOX14/calls.log" 2>/dev/null; then
  pass "14a: the dispatch did happen (precondition for the rest of group 14)"
else
  fail "14a: no dispatch — group 14 cannot conclude anything"
fi
if [[ -f "$WS14/.workforce-build-resume.inflight" ]]; then
  fail "14b: a successful SEND set the in-flight marker — the next fire is suppressed waiting on a turn that never ran"
else
  pass "14b: no in-flight marker set by a bare successful send (next fire free to retry)"
fi
if [[ -f "$WS14/.workforce-build-resume-runs.count" ]]; then
  fail "14c: a successful SEND advanced the ping ceiling — no-op sends would eventually PARK the build and remove the cron"
else
  pass "14c: the ping ceiling was NOT advanced by a bare successful send"
fi
if [[ -f "$WS14/.workforce-build-resume-sends.count" ]]; then
  pass "14d: the send WAS recorded in the observability-only send counter ($(cat "$WS14/.workforce-build-resume-sends.count"))"
else
  fail "14d: the send was not recorded anywhere — dispatch history is now invisible"
fi

echo ""
echo "--- (14-MUT) MUTATION PROOF: the historical send-implies-turn behavior does set both ---"
BOX14M="$(_mkbox box14m "$STATE_ALL_DONE_SOP_FAILED" "alpha bravo charlie")"
_runbox "$BOX14M" "$BOX14M/.openclaw/skills/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh" \
  WORKFORCE_RESUME_SEND_IMPLIES_TURN=1
WS14M="$BOX14M/.openclaw/workspace"
if [[ -f "$WS14M/.workforce-build-resume.inflight" && -f "$WS14M/.workforce-build-resume-runs.count" ]]; then
  pass "14-MUT: with SEND_IMPLIES_TURN=1 both the marker and the ceiling advance — 14b/14c are real, non-vacuous checks"
else
  fail "14-MUT: the historical path did not set marker+ceiling — 14b/14c prove nothing"
fi

# ---------------------------------------------------------------------------
# (16) NEVER_TO_OWNER_EVEN_WITH_NO_OPERATOR_CHAT
# The operator escalation chat is OPT-IN and is empty by default on a stock box, so
# "prefer operator, else owner" silently degrades straight back into "send to the
# client". With NO operator chat configured and an ownerChat present, a belt must
# send NOTHING rather than fall through to the client.
# ---------------------------------------------------------------------------
echo ""
echo "--- (16) NEVER_TO_OWNER: with NO operator chat configured, internal traffic must go nowhere ---"

# Same as _runbox but with the operator chat deliberately UNSET.
_runbox_no_operator() {
  local h="$1" script="$2"; shift 2
  env -i \
    PATH="$h/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin" \
    HOME="$h" \
    TMPDIR="${TMPDIR:-/tmp}" \
    FAKE_OC_JOBS_FILE="$h/jobs.json" \
    FAKE_OC_CALLS_FILE="$h/calls.log" \
    "$@" \
    bash "$script" >"$h/run.out" 2>&1
  return 0
}

BOX16="$(_mkbox box16 "$STATE_ALL_DONE_SOP_FAILED" "alpha bravo charlie")"
_runbox_no_operator "$BOX16" "$BOX16/.openclaw/skills/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh"
if grep -E "^message send .*-t 111222333" "$BOX16/calls.log" >/dev/null 2>&1; then
  fail "16a: with no operator chat the resume lane fell back to the OWNER chat — the client receives internal build text"
else
  pass "16a: resume lane sent NOTHING rather than falling back to the client"
fi
if grep -q "SKIPPING the internal self-ping rather than sending it to the client" \
     "$BOX16/.openclaw/workspace/.workforce-build-state.log" 2>/dev/null; then
  pass "16b: the skip is logged loudly with the remedy (configure the operator chat)"
else
  fail "16b: the lane went quiet without explaining why nothing was sent"
fi

# Same rule for the interview build-kick.
if [[ -f "$UPD" && -f "$LIBRL" ]]; then
  BOX16B="$(_mkupdbox box16b "$STATE_REOPENED" pass)"
  env -i PATH="$BOX16B/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin" HOME="$BOX16B" \
    TMPDIR="${TMPDIR:-/tmp}" FAKE_OC_JOBS_FILE="$BOX16B/jobs.json" \
    FAKE_OC_CALLS_FILE="$BOX16B/calls.log" \
    bash "$BOX16B/.openclaw/skills/23-ai-workforce-blueprint/scripts/update-interview-state.sh" \
      --complete --phase 6 --question-number 30 --asked-by tester >"$BOX16B/run.out" 2>&1
  if grep -E "^message send .*-t 111222333" "$BOX16B/calls.log" >/dev/null 2>&1; then
    fail "16c: with no operator chat the build kick fell back to the OWNER chat"
  else
    pass "16c: build kick sent NOTHING rather than falling back to the client"
  fi
fi

echo ""
echo "--- (16-MUT) MUTATION PROOF: an owner-chat fallback would reach the client ---"
BOX16M="$(_mkbox box16m "$STATE_ALL_DONE_SOP_FAILED" "alpha bravo charlie")"
MUT16="$BOX16M/.openclaw/skills/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh"
_mutate "$MUT16" <<'PYEOF'
import sys
path = sys.argv[1]
src = open(path).read()
old = 'TARGET_CHAT="$(resolve_operator_chat_id)"\n'
new = ('TARGET_CHAT="$(resolve_operator_chat_id)"\n'
       '[[ -z "$TARGET_CHAT" ]] && TARGET_CHAT="$owner_chat"\n')
if old not in src:
    sys.exit(1)
open(path, "w").write(src.replace(old, new, 1))
PYEOF
mut16_rc=$?
if (( mut16_rc != 0 )); then
  fail "16-MUT: could not reinstate the owner fallback — cannot prove 16a discriminates"
else
  _runbox_no_operator "$BOX16M" "$MUT16"
  if grep -E "^message send .*-t 111222333" "$BOX16M/calls.log" >/dev/null 2>&1; then
    pass "16-MUT: the reinstated fallback DOES deliver internal text to the client chat — 16a is a real, non-vacuous check"
  else
    fail "16-MUT: the reinstated fallback sent nothing — 16a proves nothing"
  fi
fi

# ---------------------------------------------------------------------------
# (17) NO_LASTATTEMPTAT_VISIBILITY
# A department can end up at status="building" with NO lastAttemptAt key at
# all (e.g. the DEFECT #5 honesty floor in refresh-build-state-from-index.py
# demotes a false "done" back to "building" without ever stamping
# lastAttemptAt). Such an entry is invisible to BOTH the pending lane
# (status != pending/failed) and the stale-timeout lane (requires
# lastAttemptAt to compare "older than N minutes" against) — with every OTHER
# department done, total_attention lands on 0 and the cron logs "nothing to
# do" and exits clean forever. The fix routes a building-with-no-timestamp
# department through the pending lane instead.
# ---------------------------------------------------------------------------
echo ""
echo "--- (17) NO_LASTATTEMPTAT_VISIBILITY: a stuck building-dept with no lastAttemptAt must still get a resume dispatch ---"
STATE_STUCK_NO_TIMESTAMP='{
  "interviewComplete": true,
  "interviewQc": {"status": "pass"},
  "closeoutStatus": "pending",
  "roleLibraryStatus": "pending",
  "sopLibraryStatus": "pending",
  "ownerChat": "111222333",
  "agentName": "TestOrchestrator",
  "departments": [
    {"id": "alpha", "slug": "alpha", "status": "done"},
    {"id": "bravo", "slug": "bravo", "status": "done"},
    {"id": "charlie", "slug": "charlie", "status": "building"}
  ]
}'
BOX17="$(_mkbox box17 "$STATE_STUCK_NO_TIMESTAMP" "alpha bravo")"
_runbox "$BOX17" "$BOX17/.openclaw/skills/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh"
CALLS17="$BOX17/calls.log"

if grep -q "WORKFORCE-RESUME" "$CALLS17" 2>/dev/null; then
  pass "17a: a [WORKFORCE-RESUME] dispatch fired for the stuck no-timestamp department"
else
  fail "17a: NO dispatch at all — the stuck department is still invisible (silent strand)"
fi
if grep -q "charlie" "$CALLS17" 2>/dev/null; then
  pass "17b: the dispatched message names the stuck department (charlie) so the agent knows what to build"
else
  fail "17b: the dispatch did not name the stuck department"
fi
if grep -q "no pending/stale departments" "$BOX17/.openclaw/workspace/.workforce-build-state.log" 2>/dev/null; then
  fail "17c: the log still claims 'no pending/stale departments' while one is stuck at building/no-timestamp"
else
  pass "17c: the log does not falsely claim there is nothing to do"
fi

echo ""
echo "--- (17-MUT) MUTATION PROOF: pre-fix selection on the SAME fixture dispatches nothing ---"
BOX17M="$(_mkbox box17m "$STATE_STUCK_NO_TIMESTAMP" "alpha bravo")"
MUT17="$BOX17M/.openclaw/skills/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh"
_mutate "$MUT17" <<'PYEOF'
import sys
path = sys.argv[1]
src = open(path).read()

old_count = '''jq -r '
  [.departments[]
    | select((.status == "pending" or .status == "failed")
             or (.status == "building" and .lastAttemptAt == null))
  ] | length
' "$STATE_FILE")'''
new_count = '''jq -r '[.departments[] | select(.status == "pending" or .status == "failed")] | length' "$STATE_FILE")'''

old_list = '''jq -r '
  [.departments[]
    | select((.status == "pending" or .status == "failed")
             or (.status == "building" and .lastAttemptAt == null))
    | .slug] | join(", ")
' "$STATE_FILE")'''
new_list = '''jq -r '[.departments[] | select(.status == "pending" or .status == "failed") | .slug] | join(", ")' "$STATE_FILE")'''

if old_count not in src or old_list not in src:
    sys.exit(1)
src = src.replace(old_count, new_count, 1)
src = src.replace(old_list, new_list, 1)
open(path, "w").write(src)
PYEOF
mut17_rc=$?
if (( mut17_rc != 0 )); then
  fail "17-MUT: could not revert the pending-lane selection — cannot prove 17a-c discriminate"
else
  _runbox "$BOX17M" "$MUT17"
  CALLS17M="$BOX17M/calls.log"
  # doctor/config-get calls are unconditional preflight noise unrelated to the
  # pending-lane selection under test; the discriminating signal is whether an
  # actual resume message got dispatched.
  if grep -q "^message send" "$CALLS17M" 2>/dev/null; then
    fail "17-MUT: pre-fix selection still dispatched a message — 17a proves nothing ($(cat "$CALLS17M"))"
  else
    pass "17-MUT: pre-fix selection dispatches NO message on this fixture (silent strand reproduced) — 17a is a real, non-vacuous check"
  fi
  if grep -q "no pending/stale departments" "$BOX17M/.openclaw/workspace/.workforce-build-state.log" 2>/dev/null; then
    pass "17-MUT: pre-fix log falsely claims 'no pending/stale departments' — 17c is a real, non-vacuous check"
  else
    fail "17-MUT: pre-fix log did not reproduce the false 'nothing to do' claim — 17c proves nothing"
  fi
fi

fi  # FUNCTIONAL

# ---------------------------------------------------------------------------
# (15) HOP4_DOC_CODE_LOCKSTEP
# INSTRUCTIONS.md claimed "HOP-4 requires `wiring_dirty == 0` before writing
# buildCompletedAt -- so no stub department can ever silently close out." The code
# does not check wiring_dirty at all (the variable is never computed; its only
# assignment is the `${wiring_dirty:-0}` default, so it is permanently 0 and the
# [WIRING-RESUME] branch is unreachable). A doc that overstates an enforcement gate
# sends the next person debugging a stuck buildCompletedAt down the wrong path.
# This asserts the two stay in lockstep in EITHER direction.
# ---------------------------------------------------------------------------
echo ""
echo "--- (15) HOP4_DOC_CODE_LOCKSTEP: the wiring-gate claim must match the code ---"
INSTR="$REPO_ROOT/23-ai-workforce-blueprint/INSTRUCTIONS.md"
if [[ ! -f "$RESUME" || ! -f "$INSTR" ]]; then
  fail "15: resume-workforce-build.sh or INSTRUCTIONS.md not found"
else
  # The HOP-4 condition is the `if` that guards the AUTO-COMPLETE (HOP-4) log line.
  hop4_cond="$(grep -B8 'AUTO-COMPLETE (HOP-4): all' "$RESUME" | grep -A8 '^if ((' || true)"
  # Is wiring_dirty genuinely computed anywhere (an assignment that is not the
  # `${wiring_dirty:-0}` default and not a comment)?
  wiring_computed=0
  # -F on the last grep: the default value contains {..}, which BRE reads as a
  # repetition interval ("invalid repetition count(s)") rather than literal braces.
  if grep -vE '^\s*#' "$RESUME" | grep -E 'wiring_dirty=' | grep -qvF 'wiring_dirty=${wiring_dirty:-0}'; then
    wiring_computed=1
  fi
  doc_claims_enforced=0
  grep -q 'HOP-4 requires `wiring_dirty == 0`' "$INSTR" && doc_claims_enforced=1

  if [[ "$hop4_cond" == *wiring_dirty* ]] && (( wiring_computed == 1 )); then
    # Gate is genuinely enforced -> the doc is allowed (and expected) to say so.
    (( doc_claims_enforced == 1 )) \
      && pass "15a: wiring IS enforced by HOP-4 and INSTRUCTIONS.md says so (lockstep)" \
      || fail "15a: HOP-4 now enforces wiring but INSTRUCTIONS.md no longer documents it"
  else
    # Gate is NOT enforced -> the doc must not claim it is.
    if (( doc_claims_enforced == 1 )); then
      fail "15a: INSTRUCTIONS.md claims HOP-4 requires wiring_dirty == 0, but HOP-4 does not check it (wiring_dirty computed=$wiring_computed) — doc overstates an enforcement gate"
    else
      pass "15a: HOP-4 does not enforce wiring and INSTRUCTIONS.md does not claim it does (lockstep)"
    fi
    if grep -q 'KNOWN GAP' "$INSTR"; then
      pass "15b: the unenforced wiring gate is documented as a known gap, not left silent"
    else
      fail "15b: the wiring gate is unenforced and INSTRUCTIONS.md does not flag it as a gap"
    fi
  fi
fi

# ---------------------------------------------------------------------------
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if (( FAIL > 0 )); then
  echo "FAIL: $FAIL check(s) failed — CI guard triggered"
  exit 1
fi
echo "PASS: all bounded-workforce-build-resume checks pass"
exit 0
