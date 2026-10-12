#!/usr/bin/env bash
# tests/unit/mc-route-task-mode.test.sh
#
# JEV-503 (review step 2) — `mc-route.sh task "<short title>" "<owner's exact words>"`.
# The CEO AI has already decided the message is work; the helper must post ONE
# typed card to the CC ingest door with NO department_slug (CC picks the
# department, then General Task), the owner's exact words as the description,
# print the same ROUTED line as auto mode, fail loudly, and be idempotent per call.
#
# Drives the REAL scripts/mc-route.sh with a stub `curl` that behaves like the CC
# ingest door's dedupe: a new idempotency_key makes a new card (201), a key it has
# already seen returns the existing card (200 deduped). CARDS counts real cards.
#
# Cases:
#   (a) task mode makes exactly one card; payload = title + exact words, no department_slug, no message.
#   (b) two calls for two jobs (same owner message, two titles) make two cards.
#   (c) a retry with the same title + words within 60 s makes no duplicate.
#   (d) the same job after the 60 s window is a new card (the window really expires).
#   (e) failure is loud: transport failure, HTTP 500, and a 2xx with no task_id all exit non-zero with FAILED + ESCALATE.
#   (f) a card with no workspace prints ROUTED plus an ESCALATE warning.
#   (g) auto mode is unchanged: still posts {message} only and prints JEV_ANSWER_DIRECTLY.
#   (h) with a stable MC_ROUTE_EVENT_ID a retry dedupes and two jobs from one event stay two cards.
#
# FAIL-FIRST: on origin/main (v25.2.19) `task` is parsed as a department slug,
# so the payload carries department_slug "task" and the title is the second arg;
# (a) fails, and the retry case makes a second card because every call mints a
# fresh random operation key.

set -uo pipefail

PASS=0
FAIL=0
ERRORS=()
ok()   { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); ERRORS+=("$1"); }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MC_ROUTE="$REPO_ROOT/scripts/mc-route.sh"
[ -f "$MC_ROUTE" ] || { echo "  FAIL: $MC_ROUTE not found"; exit 1; }

echo ""
echo "=== mc-route.sh task mode (JEV-503) ==="
echo ""

WORK="$(mktemp -d "${TMPDIR:-/tmp}/mc-route-task-test.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/bin" "$WORK/home" "$WORK/state"
cat > "$WORK/bin/curl" <<'STUB'
#!/usr/bin/env bash
# Stub CC ingest door. STUB_MODE: dedupe (default) | down | http500 | notaskid | noworkspace
body=""
for a in "$@"; do case "$a" in @*) body="$(cat "${a#@}")" ;; esac; done
printf '%s\n' "$body" >> "$STUB_DIR/posted.jsonl"
case "${STUB_MODE:-dedupe}" in
  down) exit 7 ;;
  http500) printf '{"error":"boom"}\n500'; exit 0 ;;
  notaskid) printf '{"ok":true}\n200'; exit 0 ;;
  noworkspace) printf '{"ok":true,"task_id":"t-x","workspace_id":null,"resolved_by":"->unrouted"}\n201'; exit 0 ;;
esac
key="$(printf '%s' "$body" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("idempotency_key",""))')"
touch "$STUB_DIR/keys"
if grep -qxF "$key" "$STUB_DIR/keys"; then
  printf '{"ok":true,"deduped":true,"task_id":"t-dup","workspace_id":"marketing","resolved_by":"auto-route:marketing"}\n200'
else
  printf '%s\n' "$key" >> "$STUB_DIR/keys"
  printf '{"ok":true,"deduped":false,"task_id":"t-%s","workspace_id":"general-task","resolved_by":"auto-route:general-task-fallback"}\n201' "$(wc -l < "$STUB_DIR/keys" | tr -d ' ')"
fi
STUB
chmod +x "$WORK/bin/curl"

OUT=""; RC=0
run() {  # run the real helper; STUB_MODE may be set by the caller
  OUT="$(env PATH="$WORK/bin:$PATH" HOME="$WORK/home" STUB_DIR="$WORK" STUB_MODE="${STUB_MODE:-dedupe}" \
      MC_ROUTE_STATE_DIR="$WORK/state" MC_ROUTE_MAX_RETRIES=0 \
      MC_ROUTE_INGEST_URL="http://127.0.0.1:4000/api/tasks/ingest" \
      bash "$MC_ROUTE" "$@" 2>&1)"
  RC=$?
}
cards() { [ -f "$WORK/keys" ] && wc -l < "$WORK/keys" | tr -d ' ' || echo 0; }
last_post() { tail -n 1 "$WORK/posted.jsonl"; }
field() { last_post | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('$1', '<absent>'))"; }

WORDS="Refund the Smith order and change the webinar date to the 15th"

echo "--- (a) one task call = exactly one card, no department ---"
run task "Refund the Smith order" "$WORDS"
[ "$RC" -eq 0 ] && ok "(a) exit 0" || fail "(a) exit $RC: $OUT"
[ "$(cards)" = 1 ] && ok "(a) exactly one card" || fail "(a) expected 1 card, got $(cards)"
[ "$(field title)" = "Refund the Smith order" ] && ok "(a) title is the short title" || fail "(a) title=$(field title)"
[ "$(field description)" = "$WORDS" ] && ok "(a) description is the owner's exact words" || fail "(a) description=$(field description)"
[ "$(field department_slug)" = "<absent>" ] && ok "(a) no department_slug (CC picks)" || fail "(a) department_slug=$(field department_slug)"
[ "$(field message)" = "<absent>" ] && ok "(a) not the raw message door" || fail "(a) message field present"
printf '%s\n' "$OUT" | grep -qx 'ROUTED workspace=general-task department=general-task resolved_by=auto-route:general-task-fallback' \
  && ok "(a) prints the ROUTED line" || fail "(a) ROUTED line missing: $OUT"
printf '%s\n' "$OUT" | grep -q 'ESCALATE' && fail "(a) must not escalate: $OUT" || ok "(a) no ESCALATE"

echo "--- (b) two jobs in one message = two cards ---"
run task "Change the webinar date to the 15th" "$WORDS"
[ "$RC" -eq 0 ] && [ "$(cards)" = 2 ] && ok "(b) second job made a second card" || fail "(b) rc=$RC cards=$(cards)"

echo "--- (c) retry with the same words within 60 s = no duplicate ---"
run task "Refund the Smith order" "$WORDS"
[ "$RC" -eq 0 ] && [ "$(cards)" = 2 ] && ok "(c) retry deduped, still two cards" || fail "(c) rc=$RC cards=$(cards)"
printf '%s\n' "$OUT" | grep -q '^ROUTED ' && ok "(c) retry still prints ROUTED" || fail "(c) $OUT"

echo "--- (d) same job after the 60 s window = a new card ---"
age_state() {  # push every window file 2 minutes into the past
  python3 - "$WORK/state" <<'AGE'
import os, sys, time
d = sys.argv[1]
for n in os.listdir(d):
    os.utime(os.path.join(d, n), (time.time() - 120, time.time() - 120))
AGE
}
age_state
run task "Refund the Smith order" "$WORDS"
[ "$RC" -eq 0 ] && [ "$(cards)" = 3 ] && ok "(d) window expired, new card" || fail "(d) rc=$RC cards=$(cards)"

echo "--- (h) stable MC_ROUTE_EVENT_ID: retry dedupes, two jobs stay two cards ---"
before="$(cards)"
MC_ROUTE_EVENT_ID=tg-msg-42 run task "Job one" "Do job one and job two"
age_state  # the event id, not the 60 s window, must carry the dedupe
MC_ROUTE_EVENT_ID=tg-msg-42 run task "Job one" "Do job one and job two"
MC_ROUTE_EVENT_ID=tg-msg-42 run task "Job two" "Do job one and job two"
[ "$(cards)" = "$((before + 2))" ] && ok "(h) event id: 3 calls, 2 jobs, 2 cards" || fail "(h) expected $((before + 2)) cards, got $(cards)"

echo "--- (e) failure is loud ---"
for mode in down http500 notaskid; do
  STUB_MODE=$mode run task "Pay the electric bill" "Pay the electric bill"
  if [ "$RC" -ne 0 ] && printf '%s\n' "$OUT" | grep -q 'mc-route: FAILED' && printf '%s\n' "$OUT" | grep -q 'ESCALATE_TO_OPERATOR' \
     && ! printf '%s\n' "$OUT" | grep -q '^ROUTED '; then
    ok "(e) $mode -> non-zero, FAILED + ESCALATE, no ROUTED"
  else
    fail "(e) $mode -> rc=$RC out=$OUT"
  fi
done
run task "" ""
[ "$RC" -ne 0 ] && printf '%s\n' "$OUT" | grep -q 'mc-route: FAILED' && ok "(e) empty task -> loud failure" || fail "(e) empty task rc=$RC: $OUT"

echo "--- (f) card with no workspace -> ROUTED + ESCALATE warning ---"
STUB_MODE=noworkspace run task "Pay the electric bill" "Pay the electric bill"
[ "$RC" -eq 0 ] && printf '%s\n' "$OUT" | grep -q '^ROUTED ' && printf '%s\n' "$OUT" | grep -q 'ESCALATE_TO_OPERATOR' \
  && ok "(f) unrouted card is reported, not silent" || fail "(f) rc=$RC: $OUT"

echo "--- (g) auto mode unchanged ---"
cat > "$WORK/bin/curl" <<'STUB'
#!/usr/bin/env bash
for a in "$@"; do case "$a" in @*) cat "${a#@}" > "$STUB_DIR/auto.json" ;; esac; done
printf '{"created":false,"intent":"answer_only"}\n200'
STUB
run auto "what time is our next call?"
auto_keys="$(python3 -c 'import json,sys; print(",".join(sorted(json.load(open(sys.argv[1])))))' "$WORK/auto.json")"
[ "$auto_keys" = "external_session_id,idempotency_key,message,priority,source" ] && ok "(g) auto posts {message} only" || fail "(g) auto keys=$auto_keys"
[ "$RC" -eq 0 ] && printf '%s\n' "$OUT" | grep -qx 'JEV_ANSWER_DIRECTLY intent=answer_only' \
  && ok "(g) auto still prints JEV_ANSWER_DIRECTLY" || fail "(g) rc=$RC: $OUT"

echo ""
echo "=== mc-route task mode: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  for e in "${ERRORS[@]}"; do echo "  - $e"; done
  exit 1
fi
exit 0
