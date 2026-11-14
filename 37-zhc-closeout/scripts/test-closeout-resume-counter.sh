#!/usr/bin/env bash
# test-closeout-resume-counter.sh -- BU-68 acceptance fixture (WF-088).
#
# The closeout-retry cron must not spend its run budget -- and above all must
# not remove itself -- while the build has not finished. The run-count block
# used to sit ABOVE "Kill condition 1", so every fire on a box whose build had
# not completed still incremented the cap; after ZHC_CLOSEOUT_MAX_CRON_RUNS
# fires the cron deleted its own registration, long before the closeout it
# exists to retry ever had work to do.
#
# Strategy: a fake OpenClaw box in a temp dir holds copies of the real scripts
# under skills/. `openclaw` is a stub whose only recorded call is the one that
# matters (`cron rm`): it touches a marker file, so "was the job removed?" is
# proven by a file's absence rather than by reading log text.
#
# EXIT: 0 all PASS, 1 any FAIL, 2 environment.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SKILL_DIR/.." && pwd)"
SRC37="$SCRIPT_DIR"
SRC23="$REPO_ROOT/23-ai-workforce-blueprint/scripts"
SRCSU="$REPO_ROOT/shared-utils"

for _bin in bash jq python3; do
  command -v "$_bin" >/dev/null 2>&1 || { echo "env: $_bin not found" >&2; exit 2; }
done

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); printf '\033[32mPASS\033[0m %s\n' "$1"; }
fail() { FAIL=$((FAIL+1)); printf '\033[31mFAIL\033[0m %s\n' "$1"; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/bu68-resume-counter.XXXXXX")"
trap 'if [[ -z "${KEEP_WORK:-}" ]]; then rm -rf "$WORK"; fi' EXIT
echo "    fixture work dir: $WORK"

BOX="$WORK/box"
OC="$BOX/.openclaw"
SK="$OC/skills"
mkdir -p "$SK/37-zhc-closeout/scripts" "$SK/23-ai-workforce-blueprint/scripts" \
         "$SK/shared-utils" "$OC/workspace" "$BOX/bin"

cp "$SRC37/resume-closeout-cron.sh" "$SRC37/lib-closeout-state.sh" "$SRC37/cleanup-closeout.py" \
   "$SK/37-zhc-closeout/scripts/" || { echo "fixture: copy S37 failed" >&2; exit 1; }
cp "$SRC23/lib-workforce-state.sh" "$SRC23/workforce_state.py" "$SRC23/workforce_completion.py" \
   "$SK/23-ai-workforce-blueprint/scripts/" || { echo "fixture: copy S23 failed" >&2; exit 1; }
cp "$SRCSU/owner_sends_hold.py" "$SRCSU/resolve-oc-root.sh" "$SK/shared-utils/" \
   || { echo "fixture: copy shared-utils failed" >&2; exit 1; }

STATE="$OC/workspace/.workforce-build-state.json"
COUNTER="$OC/workspace/.closeout-resume-runs.count"
CRON_RM_MARKER="$WORK/cron-rm.called"
CRON="$SK/37-zhc-closeout/scripts/resume-closeout-cron.sh"

cat > "$BOX/bin/openclaw" <<'STUB'
#!/usr/bin/env bash
# Stub gateway CLI. The only call this fixture cares about is the cron removal
# self_remove_cron() issues; record it as a file so the assertion is an
# absence of a side effect, never a text search.
if [[ "${1:-}" == "cron" && "${2:-}" == "rm" ]]; then
  : > "${OPENCLAW_STUB_CRON_RM_MARKER:?}"
fi
exit 0
STUB
chmod +x "$BOX/bin/openclaw"

run_cron() {
  env -i \
    PATH="$BOX/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
    HOME="$BOX" \
    OC_ROOT="$OC" \
    TMPDIR="${TMPDIR:-/tmp}" \
    WORKFORCE_RUNNER_OWNER="$$" \
    OPENCLAW_STUB_CRON_RM_MARKER="$CRON_RM_MARKER" \
    bash "$CRON" >> "$WORK/cron.out" 2>&1
}

# ---- leg 1: build not completed yet -> the cron must not spend its budget ----
jq -n '{
  "version": 1,
  "companySlug": "fixture-co",
  "companyName": "Fixture Co",
  "interviewComplete": true,
  "interviewQc": {"status": "pass", "reasons": []},
  "closeoutStatus": "pending",
  "departments": []
}' > "$STATE"
rm -f "$COUNTER" "$CRON_RM_MARKER"

fails=0
for (( i = 1; i <= 50; i++ )); do
  run_cron || fails=$((fails + 1))
done

if [[ "$fails" -eq 0 ]]; then
  pass "50 fires with no buildCompletedAt all exited 0"
else
  fail "$fails of 50 fires exited non-zero (log: $WORK/cron.out)"
fi

if [[ ! -f "$COUNTER" ]]; then
  pass "no run counter written while the build has not completed"
else
  got_count="$(tr -d '[:space:]' < "$COUNTER" 2>/dev/null || true)"
  if [[ "$got_count" == "0" ]]; then
    pass "run counter stays 0 while the build has not completed"
  else
    fail "run counter=$got_count after 50 fires on an unbuilt box (expected absent or 0)"
  fi
fi

if [[ ! -f "$CRON_RM_MARKER" ]]; then
  pass "openclaw cron rm was never asked for on an unbuilt box"
else
  fail "openclaw cron rm was called on an unbuilt box"
fi

# ---- leg 2: build completed -> the cap still runs, and nothing removes the job ----
jq '.buildCompletedAt = "2026-06-01T00:00:00Z"' "$STATE" > "$STATE.tmp" && mv "$STATE.tmp" "$STATE"
rm -f "$COUNTER" "$CRON_RM_MARKER"

rc=0
run_cron || rc=$?
if [[ "$rc" -eq 0 ]]; then
  pass "a fire with buildCompletedAt set exited 0"
else
  fail "a fire with buildCompletedAt set exited $rc (log: $WORK/cron.out)"
fi

got_count="$(tr -d '[:space:]' < "$COUNTER" 2>/dev/null || true)"
if [[ "$got_count" == "1" ]]; then
  pass "the run counter advances once the build is complete (the cap still works)"
else
  fail "run counter='$got_count' after one completed-build fire (expected 1)"
fi

if [[ ! -f "$CRON_RM_MARKER" ]]; then
  pass "openclaw cron rm was not called on the first completed-build fire"
else
  fail "openclaw cron rm was called on the first completed-build fire"
fi

printf '\nTotal: %d passed, %d failed\n' "$PASS" "$FAIL"
if [[ "$FAIL" -eq 0 ]]; then exit 0; else exit 1; fi
