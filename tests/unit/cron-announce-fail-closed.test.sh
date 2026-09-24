#!/usr/bin/env bash
# tests/unit/cron-announce-fail-closed.test.sh
#
# Acceptance tests for fix/cron-announce-fail-closed.
#
# THE DEFECT (found live on rescue-leanne-dolce, 2026-09-22, and reproduced on
# rescue-karen-vaughn + rescue-stephanie-wall):
#
#   `bootstrap-validate-daily` had failed 4x and could not tell anyone. Its
#   delivery was `announce -> last`, and OpenClaw 2026.9.x fail-CLOSES on that
#   shape for an isolated cron:
#     "Refusing implicit isolated cron delivery: the target would be inherited
#      from the shared agent-main session bucket's last recipient ..."
#   A job that fails repeatedly and cannot report it is a silent failure.
#
#   Two causes, both in scripts/ensure-pipeline-crons.sh:
#     (1) BIRTH. `openclaw cron add` DEFAULTS a job to announce+last.
#         _register_command_cron's modern (--command) branch never passed
#         --no-deliver, so every command cron was born LOUD. The script's
#         "Silent (no --channel/--to)" comment was only true because
#         _reconcile_managed_crons stripped it afterwards.
#     (2) REPAIR. MANAGED_RECONCILE_CRONS — the ONLY list reconcile may edit —
#         was never updated when v14.2.0 added bootstrap-validate-daily and
#         bootstrap-compact-weekly to the registrars and the audit list. So
#         those two were born loud and were never repaired. Forever.
#
#   A3 is the regression case: after a full run, NO managed cron may be left in
#   the fail-closing shape. A1/A2 pin the two causes separately so a partial
#   revert cannot go green.
#
# A4/A5 cover the other half: silence must not mean unheard. A FAILING
# bootstrap-validate-daily escalates to the OPERATOR (Rescue Rangers webhook —
# the same channel scripts/disk-usage-alert.sh uses) and NEVER to a client
# chat; with no operator route configured it says so LOUDLY rather than
# failing quietly.
#
# Hermetic: private $HOME, fake `openclaw` (tests/fixtures/fake-openclaw-cron.py)
# and fake `curl` on PATH. No network, never touches a real ~/.openclaw.
#
# Exit 0 = all pass. Exit 1 = one or more failed (CI FAIL).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FIXTURE="$REPO_ROOT/tests/fixtures/fake-openclaw-cron.py"
ENSURE="$REPO_ROOT/scripts/ensure-pipeline-crons.sh"
VALIDATE="$REPO_ROOT/scripts/bootstrap-validate-daily.sh"

PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== cron-announce-fail-closed.test.sh ==="
echo ""

SANDBOX="$(mktemp -d)"
cleanup() { rm -rf "$SANDBOX" 2>/dev/null || true; }
trap cleanup EXIT
case "$SANDBOX" in
  */.openclaw|*/.openclaw/*) echo "REFUSING: sandbox resolved into a real .openclaw ($SANDBOX)"; exit 2 ;;
esac

# The managed command crons ensure-pipeline-crons.sh registers via
# _ensure_health_cron. Each needs its script present in the persistent dir or
# the registrar SKIPs it.
HEALTH_SCRIPTS=(
  index-model-drift-check.sh orphan-temp-sweep.sh disk-usage-alert.sh
  pre-july14-embedding-migration-check.sh toolsearch-drift-guard.sh
  agent-browser-reaper.sh bootstrap-validate-daily.sh bootstrap-compact-weekly.sh
)

_mk_env() { # <tag> -> echoes "HOME BIN JOBS CALLS"
  local tag="$1"
  local h="$SANDBOX/home-$tag" b="$SANDBOX/bin-$tag"
  local j="$SANDBOX/jobs-$tag.json" c="$SANDBOX/calls-$tag.log"
  mkdir -p "$h/.openclaw/scripts" "$h/clawd" "$b"
  local s
  for s in "${HEALTH_SCRIPTS[@]}"; do
    printf '#!/usr/bin/env bash\nexit 0\n' > "$h/.openclaw/scripts/$s"
    chmod +x "$h/.openclaw/scripts/$s"
  done
  printf '%s' '{}' > "$h/.openclaw/openclaw.json"
  cat > "$b/openclaw" <<SHIM
#!/usr/bin/env bash
exec python3 "$FIXTURE" "\$@"
SHIM
  chmod +x "$b/openclaw"
  printf '[]' > "$j"; : > "$c"
  echo "$h $b $j $c"
}

_run_ensure() { # <home> <bin> <jobs> <calls> [logfile]
  HOME="$1" PATH="$2:$PATH" FAKE_OC_JOBS_FILE="$3" FAKE_OC_CALLS_FILE="$4" \
    bash "$ENSURE" > "${5:-/dev/null}" 2>&1
  return 0
}

# ---------------------------------------------------------------------------
# A1 — BIRTH: every command cron is registered SILENT.
#      Fails on the unfixed tree: --no-deliver was never passed on the
#      --command branch, so the CLI default (announce+last) stands.
# ---------------------------------------------------------------------------
echo "--- A1: command crons are born silent (--no-deliver at registration) ---"
read -r H1 B1 J1 C1 <<<"$(_mk_env a1)"
_run_ensure "$H1" "$B1" "$J1" "$C1" "$SANDBOX/a1.log"

LOUD_AT_BIRTH="$(python3 - "$J1" <<'PY'
import json,sys
jobs=json.load(open(sys.argv[1]))
bad=[j["name"] for j in jobs
     if j.get("kind")=="command" and (j.get("delivery") or {}).get("mode")=="announce"]
print(",".join(sorted(bad)))
PY
)"
if [ -z "$LOUD_AT_BIRTH" ]; then
  pass "A1: no command cron was registered with delivery mode=announce"
else
  fail "A1: registered LOUD (mode=announce) — these fail-close on 2026.9.x and cannot report their own failure: $LOUD_AT_BIRTH"
fi

ADD_NO_DELIVER="$(grep -c -- "^cron add.*--no-deliver.*--command" "$C1" 2>/dev/null || true)"; ADD_NO_DELIVER="${ADD_NO_DELIVER:-0}"
if [ "$ADD_NO_DELIVER" -gt 0 ]; then
  pass "A1b: 'cron add --command' calls carry --no-deliver ($ADD_NO_DELIVER calls)"
else
  fail "A1b: no 'cron add --command' call passed --no-deliver — silence depends entirely on the reconcile pass"
fi

# ---------------------------------------------------------------------------
# A2 — REPAIR: a PRE-EXISTING cron already in the announce+last shape is
#      repaired by the reconcile pass. This is the exact live state of
#      bootstrap-validate-daily on rescue-leanne-dolce.
#      Fails on the unfixed tree: the name is not in MANAGED_RECONCILE_CRONS,
#      so _reconcile_rows filters it out and nothing ever touches it.
# ---------------------------------------------------------------------------
echo ""
echo "--- A2: a pre-existing announce+last cron is repaired by reconcile ---"
read -r H2 B2 J2 C2 <<<"$(_mk_env a2)"
python3 - "$J2" "$H2" <<'PY'
import json,sys
jobs_file, home = sys.argv[1], sys.argv[2]
def seeded(name, expr):
    return {"name": name, "cron": expr, "agent": "", "message": "",
            "command": "bash %s/.openclaw/scripts/%s.sh" % (home, name),
            "kind": "command", "id": "pre-%s" % name,
            # The exact live shape read off rescue-leanne-dolce 2026-09-22.
            "delivery": {"mode": "announce", "channel": "last", "to": None},
            "payload": {"kind": "command"}, "schedule": {"expr": expr}}
json.dump([seeded("bootstrap-validate-daily", "0 5 * * *"),
           seeded("bootstrap-compact-weekly", "30 4 * * 0")], open(jobs_file, "w"))
PY
_run_ensure "$H2" "$B2" "$J2" "$C2" "$SANDBOX/a2.log"

for NAME in bootstrap-validate-daily bootstrap-compact-weekly; do
  MODE="$(python3 - "$J2" "$NAME" <<'PY'
import json,sys
jobs=json.load(open(sys.argv[1]))
m=[(j.get("delivery") or {}).get("mode") for j in jobs if j.get("name")==sys.argv[2]]
print(m[0] if m else "ABSENT")
PY
)"
  if [ "$MODE" = "none" ]; then
    pass "A2: $NAME repaired to delivery mode=none by the reconcile pass"
  else
    fail "A2: $NAME left at delivery mode=$MODE — reconcile never touched it (name missing from MANAGED_RECONCILE_CRONS)"
  fi
done

# ---------------------------------------------------------------------------
# A3 — THE REGRESSION CASE. After a full run, NO managed cron may be left in
#      the fail-closing shape (mode=announce + channel=last on an isolated
#      job). That shape is precisely what makes a failing job refuse to
#      announce: a loud failure becomes a silent one.
# ---------------------------------------------------------------------------
echo ""
echo "--- A3: no managed cron is left in the fail-closing announce+last shape ---"
FAILCLOSED="$(python3 - "$J2" <<'PY'
import json,sys
jobs=json.load(open(sys.argv[1]))
bad=[]
for j in jobs:
    d=j.get("delivery") or {}
    # An isolated cron with an unresolvable route: the runner refuses to
    # deliver, so a failure of the job itself is never surfaced to anyone.
    if d.get("mode")=="announce" and d.get("channel")=="last" and not d.get("to"):
        bad.append(j.get("name",""))
print(",".join(sorted(bad)))
PY
)"
if [ -z "$FAILCLOSED" ]; then
  pass "A3: zero crons in the unresolvable announce->last shape after a full run"
else
  fail "A3: still fail-closing (a failing run will be SILENTLY refused, not reported): $FAILCLOSED"
fi

# ---------------------------------------------------------------------------
# A4 — LOUD FAILURE. A failing validation with NO operator route configured
#      must say so on stderr and still exit non-zero. Silence is the bug.
# ---------------------------------------------------------------------------
echo ""
echo "--- A4: a failing run with no operator route fails LOUDLY, not silently ---"
WS="$SANDBOX/ws"; mkdir -p "$WS"
STUB_VALIDATOR="$SANDBOX/stub-validator.py"
cat > "$STUB_VALIDATOR" <<'PY'
import sys
# Mimics validate-core-references.py on a FAILING workspace.
print('{"ok": false, "errors": ["AGENTS.md: unbalanced code fence"]}')
sys.exit(1)
PY
mkdir -p "$SANDBOX/home-a4/.openclaw"
printf '%s' '{}' > "$SANDBOX/home-a4/.openclaw/openclaw.json"

set +e
A4_ERR="$(HOME="$SANDBOX/home-a4" OC_ROOT="$SANDBOX/home-a4/.openclaw" \
  OC_CONFIG="$SANDBOX/home-a4/.openclaw/openclaw.json" \
  OC_WORKSPACES="$WS" VALIDATOR="$STUB_VALIDATOR" \
  RESCUE_RANGERS_WEBHOOK_URL="" \
  bash "$VALIDATE" --quiet 2>&1 >/dev/null)"
A4_RC=$?
set +e

if [ "$A4_RC" -ne 0 ]; then
  pass "A4a: failing validation still exits non-zero (rc=$A4_RC)"
else
  fail "A4a: failing validation exited 0 — the failure is invisible to the scheduler"
fi
if printf '%s' "$A4_ERR" | grep -q 'ALERT-UNDELIVERED'; then
  pass "A4b: unescalated failure is announced LOUDLY on stderr (ALERT-UNDELIVERED)"
else
  fail "A4b: no ALERT-UNDELIVERED on stderr — a failure with no operator route is silently swallowed"
fi

# ---------------------------------------------------------------------------
# A5 — OPERATOR ONLY. With a route configured the alert goes to the Rescue
#      Rangers operator webhook, and to nothing else. A client chat is never
#      a destination for a technical failure.
# ---------------------------------------------------------------------------
echo ""
echo "--- A5: the alert reaches the OPERATOR webhook and no client channel ---"
CURLBIN="$SANDBOX/bin-a5"; mkdir -p "$CURLBIN"
CURL_LOG="$SANDBOX/curl-a5.log"
cat > "$CURLBIN/curl" <<SHIM
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$CURL_LOG"
exit 0
SHIM
chmod +x "$CURLBIN/curl"
: > "$CURL_LOG"

set +e
A5_ERR="$(HOME="$SANDBOX/home-a4" OC_ROOT="$SANDBOX/home-a4/.openclaw" \
  OC_CONFIG="$SANDBOX/home-a4/.openclaw/openclaw.json" \
  OC_WORKSPACES="$WS" VALIDATOR="$STUB_VALIDATOR" \
  RESCUE_RANGERS_WEBHOOK_URL="https://operator.example/rr-hook" \
  PATH="$CURLBIN:$PATH" \
  bash "$VALIDATE" --quiet 2>&1 >/dev/null)"
set +e

if grep -q 'operator.example/rr-hook' "$CURL_LOG" 2>/dev/null; then
  pass "A5a: failure POSTed to the operator (rescue-rangers) webhook"
else
  fail "A5a: nothing was POSTed to the operator webhook — the failure reached no one"
fi
if grep -q 'bootstrap-validate-daily' "$CURL_LOG" 2>/dev/null; then
  pass "A5b: the escalation payload identifies the failing job"
else
  fail "A5b: escalation payload does not name the job"
fi
# The destination must be the operator webhook and NOTHING else. A telegram
# send from this script would be a client-facing alert.
if grep -qE 'message send|--channel telegram|sendMessage' "$CURL_LOG" 2>/dev/null; then
  fail "A5c: a client-facing delivery path was used — a technical alert must never reach a client"
else
  pass "A5c: no client channel used (operator webhook only)"
fi
if grep -qE 'message send|channels\.telegram' "$VALIDATE" 2>/dev/null; then
  fail "A5d: bootstrap-validate-daily.sh contains a direct chat-send path (client-leak risk)"
else
  pass "A5d: bootstrap-validate-daily.sh has no direct chat-send path"
fi

# ---------------------------------------------------------------------------
# A6 — CONVERGENCE. A second run must issue NO further `cron edit`: everything
#      is already silent. Guards the fix against reconcile churn (an edit on
#      every run would re-write the fleet's crons forever).
# ---------------------------------------------------------------------------
echo ""
echo "--- A6: reconcile converges (a second run edits nothing) ---"
read -r H6 B6 J6 C6 <<<"$(_mk_env a6)"
_run_ensure "$H6" "$B6" "$J6" "$C6" "$SANDBOX/a6-run1.log"
: > "$C6"
_run_ensure "$H6" "$B6" "$J6" "$C6" "$SANDBOX/a6-run2.log"
EDITS2="$(grep -c "^cron edit" "$C6" 2>/dev/null || true)"; EDITS2="${EDITS2:-0}"
if [ "$EDITS2" -eq 0 ]; then
  pass "A6: second run issued 0 'cron edit' calls (converged)"
else
  fail "A6: second run issued $EDITS2 'cron edit' calls — reconcile churns on every roll"
fi

echo ""
echo "=== $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
exit 0
