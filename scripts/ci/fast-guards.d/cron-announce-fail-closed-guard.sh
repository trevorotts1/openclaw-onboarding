#!/usr/bin/env bash
# Folded from .github/workflows/cron-announce-fail-closed-guard.yml (job "Cron delivery born silent + reconcile lockstep"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set +e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
fg_rc=0
if [ "$fg_rc" -eq 0 ]; then
( # step: C1 — command-cron registration passes --no-deliver (static)
echo "--- step: C1 — command-cron registration passes --no-deliver (static)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards cron-announce-fail-closed-guard: step \"C1 — command-cron registration passes --no-deliver (static)\" failed (exit $fg_rc)"' EXIT
H="scripts/ensure-pipeline-crons.sh"
# Every `openclaw cron add ... --command` in the registrar must carry
# --no-deliver. The only exemption is the documented last-resort retry
# for a CLI that rejects the flag, which logs a WARN naming reconcile.
if ! grep -q -- '--no-deliver' "$H"; then
  echo "FAIL C1: no --no-deliver anywhere in $H — command crons are born announce+last and fail-close on 2026.9.x"
  exit 1
fi
if ! grep -B2 -A2 -- '--command "bash \$script" --json' "$H" | grep -q -- '--no-deliver'; then
  echo "FAIL C1: the --command registration path does not pass --no-deliver"
  echo "  -> every command cron is born LOUD; a failing job cannot report itself."
  exit 1
fi
echo "PASS C1: --command registration passes --no-deliver"
)
[ $? -eq 0 ] || fg_rc=1
fi
if [ "$fg_rc" -eq 0 ]; then
( # step: C2 — registrar/reconcile lockstep (no managed cron left unrepairable)
echo "--- step: C2 — registrar/reconcile lockstep (no managed cron left unrepairable)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards cron-announce-fail-closed-guard: step \"C2 — registrar/reconcile lockstep (no managed cron left unrepairable)\" failed (exit $fg_rc)"' EXIT
# Extract the names main() audits (the authoritative managed set) and
# the names MANAGED_RECONCILE_CRONS may repair; every audited name
# must be reconcilable. A name in one list and not the other is the
# defect class this guard exists for.
python3 - <<'PY'
import re, sys
src = open("scripts/ensure-pipeline-crons.sh").read()

m = re.search(r'MANAGED_RECONCILE_CRONS=\(\n(.*?)\n\)', src, re.S)
if not m:
    print("FAIL C2: MANAGED_RECONCILE_CRONS block not found"); sys.exit(1)
reconcile = set(re.findall(r'^\s*"([^"]+)"', m.group(1), re.M))

a = re.search(r'for _n in ((?:"[^"]+"\s*\\?\s*)+); do', src)
if not a:
    print("FAIL C2: main() audit list not found"); sys.exit(1)
audited = set(re.findall(r'"([^"]+)"', a.group(1)))

missing = sorted(audited - reconcile)
if missing:
    print("FAIL C2: managed cron(s) absent from MANAGED_RECONCILE_CRONS: " + ", ".join(missing))
    print("  -> the registrars only ADD a missing cron. Only MANAGED_RECONCILE_CRONS")
    print("     REPAIRS an existing one, so these are born announce+last and stay that")
    print("     way on every box that already has them. A failing job then refuses to")
    print("     announce: 'Refusing implicit isolated cron delivery'.")
    sys.exit(1)
print("PASS C2: all %d audited managed crons are reconcilable" % len(audited))
PY
)
[ $? -eq 0 ] || fg_rc=1
fi
if [ "$fg_rc" -eq 0 ]; then
( # step: C3 — a failing validation is never silently swallowed (static)
echo "--- step: C3 — a failing validation is never silently swallowed (static)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards cron-announce-fail-closed-guard: step \"C3 — a failing validation is never silently swallowed (static)\" failed (exit $fg_rc)"' EXIT
H="scripts/bootstrap-validate-daily.sh"
MISS=""
grep -q 'ALERT-UNDELIVERED' "$H"            || MISS="$MISS no-loud-unescalated-path"
grep -q 'RESCUE_RANGERS_WEBHOOK_URL' "$H"   || MISS="$MISS no-operator-escalation"
# A technical alert must never reach a client chat.
if grep -qE 'message send|channels\.telegram|sendMessage' "$H"; then
  MISS="$MISS client-chat-send-path"
fi
if [ -n "$MISS" ]; then
  echo "FAIL C3: bootstrap-validate-daily.sh failure reporting:$MISS"
  exit 1
fi
echo "PASS C3: failing runs escalate to the operator webhook, or say so loudly; no client path"
)
[ $? -eq 0 ] || fg_rc=1
fi
if [ "$fg_rc" -eq 0 ]; then
( # step: C4 — acceptance tests (offline, hermetic)
echo "--- step: C4 — acceptance tests (offline, hermetic)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards cron-announce-fail-closed-guard: step \"C4 — acceptance tests (offline, hermetic)\" failed (exit $fg_rc)"' EXIT
chmod +x tests/unit/cron-announce-fail-closed.test.sh
bash tests/unit/cron-announce-fail-closed.test.sh
)
[ $? -eq 0 ] || fg_rc=1
fi
if [ "$fg_rc" -eq 0 ]; then
( # step: C5 — existing cron-fixture consumers still green (no weakened tests)
echo "--- step: C5 — existing cron-fixture consumers still green (no weakened tests)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards cron-announce-fail-closed-guard: step \"C5 — existing cron-fixture consumers still green (no weakened tests)\" failed (exit $fg_rc)"' EXIT
# The fixture now models delivery. Re-run every consumer so that
# change can never silently break one.
FAILED=""
for t in pipeline-cron-idempotency cron-tombstone-durability \
         closeout-resume-cron-routing closeout-resume-exhausted-silent-d25 weekly-cron-message-refresh \
         standard-first-cron-awareness workforce-resume-cheap-command-mode \
         real-estate-industry-gate skill39-cron-path-and-retire; do
  if ! bash "tests/unit/$t.test.sh" >/tmp/"$t".log 2>&1; then
    FAILED="$FAILED $t"
    echo "--- $t ---"; tail -20 /tmp/"$t".log
  fi
done
if [ -n "$FAILED" ]; then
  echo "FAIL C5: fixture-consuming tests regressed:$FAILED"
  exit 1
fi
echo "PASS C5: all cron-fixture consumers still green"
)
[ $? -eq 0 ] || fg_rc=1
fi
( # step: Summary
echo "--- step: Summary"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards cron-announce-fail-closed-guard: step \"Summary\" failed (exit $fg_rc)"' EXIT
echo "cron-announce-fail-closed guard complete."
echo "C1 born-silent registration; C2 registrar/reconcile lockstep;"
echo "C3 loud failure + operator-only escalation; C4 acceptance tests;"
echo "C5 no existing fixture consumer weakened."
)
[ $? -eq 0 ] || fg_rc=1
exit "$fg_rc"
