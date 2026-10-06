#!/usr/bin/env bash
# tests/unit/mc-route-auto-intake.test.sh
#
# JGT103 — mc-route.sh AUTO mode (JEV live routing via the CC ingest raw door).
# `mc-route.sh auto "<owner message verbatim>"` posts {message} alone (no title,
# description or department_slug) to the same signed ingest endpoint slug mode
# uses, and turns the JSON response into a one-line stdout contract for the CEO
# agent: JEV_ANSWER_DIRECTLY (answer, create nothing) or ROUTED (one card now
# exists). It reuses the identical signing/secret/retry code path as slug mode —
# this test drives the REAL scripts/mc-route.sh end-to-end with a stubbed `curl`
# that both captures the exact JSON body posted and returns a per-case canned
# response, the same harness shape as mc-route-requester-payload.test.sh.
#
# Cases:
#   (a) auto mode posts 'message' with no title or department_slug.
#   (b) {created:false,intent:'answer_only'} -> JEV_ANSWER_DIRECTLY intent=answer_only, rc 0.
#   (c) a created card with workspace marketing -> ROUTED workspace=marketing, no ESCALATE.
#   (d) 403 control_probe_never_creates -> JEV_ANSWER_DIRECTLY intent=unresolved, rc 0.
#   (e) slug 'legal' landing general-task, resolved_by unrecognized-slug->general -> INFO,
#       no ESCALATE_TO_OPERATOR.
#   (f) slug 'legal' landing ceo, resolved_by ->ceo -> ESCALATE is still printed.
#
# FAIL-FIRST: against the pre-JGT103 helper (no `auto` mode, no General-Task
# catch-all guard) every case below fails — (a)-(d) because `auto` is parsed as
# a literal department_slug and the helper builds a title/description/
# department_slug payload instead of {message}; (e) because the pre-JGT103
# workspace-mismatch guard has no General-Task exception and always warns +
# escalates on any mismatch. With the fix they pass.

set -uo pipefail

PASS=0
FAIL=0
ERRORS=()

ok()   { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); ERRORS+=("$1"); }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MC_ROUTE="$REPO_ROOT/scripts/mc-route.sh"

echo ""
echo "=== mc-route.sh auto-mode JEV live-routing guard (JGT103) ==="
echo ""

if [ ! -f "$MC_ROUTE" ]; then
  echo "  FAIL: scripts/mc-route.sh not found at $MC_ROUTE"
  exit 1
fi

# ── Hermetic sandbox: a stub `curl` that captures the POSTed body and replies
#    with whatever STUB_BODY/STUB_CODE the test case exports; an empty HOME so
#    the helper's secret resolution reads NO real dotenv store. ────────────────
WORK="$(mktemp -d "${TMPDIR:-/tmp}/mc-route-auto-test.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
CAPTURE="$WORK/captured-body.json"

mkdir -p "$WORK/bin" "$WORK/home"
cat > "$WORK/bin/curl" <<'STUB'
#!/usr/bin/env bash
# Stub curl: find the --data-binary @<file> argument, copy its contents to the
# capture path, and emit "body\n%{http_code}" (the real helper's -w format) from
# the STUB_BODY/STUB_CODE env vars the test case set, so the caller's response-
# parsing logic runs against a canned response instead of a live network call.
# JEV-601: slug mode first checks the department exists on the board.
case " $* " in *'/api/workspaces '*) printf '[{"id":"ws-legal","slug":"legal","name":"Legal"}]\n200'; exit 0 ;; esac
CAP="$CAPTURE"
prev=""
for a in "$@"; do
  case "$a" in
    @*) cp "${a#@}" "$CAP" 2>/dev/null || true ;;
  esac
  case "$prev" in
    --data-binary|-d|--data) case "$a" in @*) cp "${a#@}" "$CAP" 2>/dev/null || true ;; esac ;;
  esac
  prev="$a"
done
printf '%s\n%s' "$STUB_BODY" "${STUB_CODE:-200}"
STUB
chmod +x "$WORK/bin/curl"

# Run the real helper with the stub curl first on PATH and a clean HOME. Captures
# stdout/stderr/rc into globals so each case can assert on them independently.
LAST_OUT=""
LAST_RC=0
run_helper() {
  rm -f "$CAPTURE"
  LAST_OUT="$(env PATH="$WORK/bin:$PATH" HOME="$WORK/home" \
      MC_ROUTE_INGEST_URL="http://127.0.0.1:4000/api/tasks/ingest" \
      CAPTURE="$CAPTURE" STUB_BODY="$STUB_BODY" STUB_CODE="$STUB_CODE" \
      bash "$MC_ROUTE" "$@" 2>&1)"
  LAST_RC=$?
}

# ── (a) auto mode posts 'message' with no title or department_slug ──────────
echo "--- (a) auto mode posts 'message', omits title/description/department_slug ---"
STUB_BODY='{"created":true,"workspace_id":"general-task"}' STUB_CODE=200
run_helper auto "please look into the client complaint"
if [ ! -f "$CAPTURE" ]; then
  fail "(a) helper produced no captured payload (stub curl not invoked)"
else
  body="$(cat "$CAPTURE")"
  if printf '%s' "$body" | grep -q '"message":"please look into the client complaint"'; then
    ok "(a) payload carries the verbatim message"
  else
    fail "(a) payload MUST carry the verbatim message — got: $body"
  fi
  if printf '%s' "$body" | grep -q '"title"' || printf '%s' "$body" | grep -q '"description"' \
     || printf '%s' "$body" | grep -q '"department_slug"'; then
    fail "(a) auto-mode payload MUST NOT contain title/description/department_slug — got: $body"
  else
    ok "(a) auto-mode payload omits title, description and department_slug"
  fi
fi

# ── (b) created:false -> JEV_ANSWER_DIRECTLY ─────────────────────────────────
echo "--- (b) {created:false,intent:answer_only} -> JEV_ANSWER_DIRECTLY intent=answer_only ---"
STUB_BODY='{"created":false,"intent":"answer_only"}' STUB_CODE=200
run_helper auto "what time is our next call?"
if [ "$LAST_RC" -ne 0 ]; then
  fail "(b) expected exit 0, got $LAST_RC — output: $LAST_OUT"
elif printf '%s' "$LAST_OUT" | grep -q '^JEV_ANSWER_DIRECTLY intent=answer_only$'; then
  ok "(b) prints JEV_ANSWER_DIRECTLY intent=answer_only and exits 0"
else
  fail "(b) expected JEV_ANSWER_DIRECTLY intent=answer_only — got: $LAST_OUT"
fi

# ── (c) a created card with workspace marketing -> ROUTED, no ESCALATE ──────
echo "--- (c) created card, workspace marketing -> ROUTED workspace=marketing ---"
STUB_BODY='{"created":true,"workspace_id":"marketing","resolved_department":"marketing","resolved_by":"keyword-match"}' STUB_CODE=200
run_helper auto "run the new ad campaign for the spring launch"
if [ "$LAST_RC" -ne 0 ]; then
  fail "(c) expected exit 0, got $LAST_RC — output: $LAST_OUT"
elif printf '%s' "$LAST_OUT" | grep -q 'ROUTED workspace=marketing'; then
  if printf '%s' "$LAST_OUT" | grep -q 'ESCALATE'; then
    fail "(c) ROUTED output MUST NOT also print ESCALATE — got: $LAST_OUT"
  else
    ok "(c) prints ROUTED workspace=marketing with no ESCALATE"
  fi
else
  fail "(c) expected ROUTED workspace=marketing — got: $LAST_OUT"
fi

# ── (d) 403 control_probe_never_creates -> JEV_ANSWER_DIRECTLY intent=unresolved ──
echo "--- (d) HTTP 403 control_probe_never_creates -> JEV_ANSWER_DIRECTLY intent=unresolved ---"
STUB_BODY='{"error":"control_probe_never_creates"}' STUB_CODE=403
run_helper auto "this is a control probe message"
if [ "$LAST_RC" -ne 0 ]; then
  fail "(d) expected exit 0, got $LAST_RC — output: $LAST_OUT"
elif printf '%s' "$LAST_OUT" | grep -q '^JEV_ANSWER_DIRECTLY intent=unresolved$'; then
  ok "(d) prints JEV_ANSWER_DIRECTLY intent=unresolved and exits 0"
else
  fail "(d) expected JEV_ANSWER_DIRECTLY intent=unresolved — got: $LAST_OUT"
fi

# ── (e) slug 'legal' lands on general-task via the documented catch-all -> INFO ──
echo "--- (e) slug legal lands general-task, resolved_by unrecognized-slug->general -> INFO ---"
STUB_BODY='{"workspace_id":"general-task","resolved_by":"unrecognized-slug->general"}' STUB_CODE=200
run_helper legal "Legal review" "a client needs a contract reviewed"
if [ "$LAST_RC" -ne 0 ]; then
  fail "(e) expected exit 0, got $LAST_RC — output: $LAST_OUT"
elif printf '%s' "$LAST_OUT" | grep -q 'ESCALATE_TO_OPERATOR'; then
  fail "(e) landing on General Task via the catch-all MUST NOT escalate — got: $LAST_OUT"
elif printf '%s' "$LAST_OUT" | grep -q 'mc-route: INFO'; then
  ok "(e) prints INFO, no ESCALATE_TO_OPERATOR, for the documented General Task catch-all"
else
  fail "(e) expected an INFO line — got: $LAST_OUT"
fi

# ── (f) slug 'legal' lands on ceo -> ESCALATE is still printed ──────────────
echo "--- (f) slug legal lands ceo, resolved_by ->ceo -> ESCALATE is still printed ---"
STUB_BODY='{"workspace_id":"ceo","resolved_by":"->ceo"}' STUB_CODE=200
run_helper legal "Legal review" "a client needs a contract reviewed"
if printf '%s' "$LAST_OUT" | grep -q 'ESCALATE_TO_OPERATOR'; then
  ok "(f) a genuine mismatch (->ceo) still escalates"
else
  fail "(f) a ->ceo mismatch MUST still escalate — got: $LAST_OUT"
fi

echo ""
echo "=== mc-route auto-intake guard: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  echo ""
  echo "Failures:"
  for e in "${ERRORS[@]}"; do echo "  - $e"; done
  exit 1
fi
exit 0
