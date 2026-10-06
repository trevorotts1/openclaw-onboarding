#!/usr/bin/env bash
# tests/rescue/RR-030/test_escalation_tpl_snippets.sh   (RR plan fixes F15, F16)
# Extracts the two bash blocks (escalate, resolve) from the REAL template
# scripts/rescue-escalation-section.md.tpl, renders tokens, and runs each in
# `env -i bash` with a stub curl on PATH. Never touches the network.
#   F15: X-Rescue-Secret header sent exactly once by BOTH blocks when set, never when unset;
#        resolve block prints the HTTP status line.
#   F16: hostile free text (backtick, $(...), $SECRET, double quote, newline) stays literal,
#        is never executed or expanded, and the posted file is valid JSON.
#   F49: the escalate block captures the HTTP status and prints ONE state line
#        (rescue_rangers_state=...) for each canned answer, so an agent can tell
#        accepted from refused; returnTo is described as audit-only; the 25/day
#        promise is now the notificationCapped rule; no line sends agents to Trevor's
#        personal chat any more (Trevor approved D13 on 2026-10-03): the chat id
#        5252140759 must appear in NEITHER template copy.
#   Also: role-library copy is byte-identical to the canonical template.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
TPL="$REPO/scripts/rescue-escalation-section.md.tpl"
MIRROR="$REPO/23-ai-workforce-blueprint/templates/role-library/rescue-rangers/scripts/rescue-escalation-section.md.tpl"
[ -f "$TPL" ] || { echo "FATAL: $TPL missing"; exit 2; }
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ok   $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL $1"; }
W="$(mktemp -d "${TMPDIR:-/tmp}/rr030-snip-XXXXXX")"; trap 'rm -rf "$W"' EXIT
PY="$(command -v python3)" || { echo "FATAL: python3 missing"; exit 2; }

cmp -s "$TPL" "$MIRROR" && ok "role-library template is byte-identical" || bad "role-library template differs from scripts/ template"

# --- extract + render the two fenced blocks inside the marker pair ----------
"$PY" - "$TPL" "$W" <<'PY' || { echo "FATAL: extraction failed"; exit 2; }
import re, sys
tpl, w = sys.argv[1], sys.argv[2]
t = open(tpl, encoding="utf-8").read()
s = t.index("<!-- RESCUE_ESCALATION_BOXNAME_V3 -->"); e = t.index("<!-- END RESCUE_ESCALATION_BOXNAME_V3 -->")
blocks = re.findall(r"```\n(.*?)\n```", t[s:e], re.S)
esc = [b for b in blocks if "/tmp/rr-escalation.json" in b]
res = [b for b in blocks if "/tmp/rr-resolved.json" in b]
assert len(esc) == 1 and len(res) == 1, (len(esc), len(res))
tok = {"BOX_NAME": "test-box", "CLIENT": "TEST client", "AGENT": "TEST agent", "BOX_TYPE": "Mac Mini", "RETURN_TO": "0"}
def render(b):
    for k, v in tok.items(): b = b.replace("{{%s}}" % k, v)
    assert "{{" not in b
    return b
HOSTILE = 'it broke `touch $W/CANARY_BT` and $(touch $W/CANARY_CS) and $RESCUE_RANGERS_WEBHOOK_SECRET with "double quotes"\nsecond line \\ backslash'.replace("$W", w)
e = render(esc[0])
e = e.replace("<real name of the owner or end user this agent serves>", "Test Person")
e = e.replace("<one paragraph, plain text; quotes, backticks and dollar signs are safe here>", HOSTILE)
e = e.replace("<numbered list of everything you already tried, plain text>", "1. tried `id`\n2. tried $HOME")
r = render(res[0])
r = r.replace("<the incident_id journalled from the escalation response>", "TEST-INC-1")
r = r.replace("<the attempt id that produced the fix>", "att-1")
r = r.replace("<one line: what fixed it>", 'fixed with `id` and "quotes" $HOME')
open(w + "/escalate.sh", "w").write(e + "\n"); open(w + "/resolve.sh", "w").write(r + "\n")
open(w + "/hostile.txt", "w").write(HOSTILE)
PY

# --- stub curl: records argv (one per line), copies --data-binary @file, prints canned body [+ status] ---
mkdir -p "$W/bin"
cat > "$W/bin/curl" <<'STUB'
#!/bin/sh
: > "$STUB_ARGV"; wflag=0
for a in "$@"; do
  printf '%s\n' "$a" >> "$STUB_ARGV"
  case "$a" in @*) cp "${a#@}" "$STUB_BODY" ;; esac
  case "$a" in *http_code*) wflag=1 ;; esac
done
printf '%s' "$STUB_RESPONSE"
[ "$wflag" = 1 ] && printf '\n%s' "$STUB_CODE"
exit 0
STUB
chmod +x "$W/bin/curl"

run_block() { # run_block <script> <secret-or-empty> <response> <code>  -> stdout in $W/out
  rm -f "$W/argv" "$W/body" "$W/out"
  if [ -n "$2" ]; then
    env -i PATH="$W/bin:$(dirname "$PY"):/usr/bin:/bin" HOME="$W" STUB_ARGV="$W/argv" STUB_BODY="$W/body" STUB_RESPONSE="$3" STUB_CODE="$4" \
      RESCUE_RANGERS_WEBHOOK_URL="http://stub.invalid/hook" RESCUE_RANGERS_WEBHOOK_SECRET="$2" FLEET_STANDING_BOX_SLUG="test-box" \
      bash "$1" > "$W/out" 2>"$W/err"
  else
    env -i PATH="$W/bin:$(dirname "$PY"):/usr/bin:/bin" HOME="$W" STUB_ARGV="$W/argv" STUB_BODY="$W/body" STUB_RESPONSE="$3" STUB_CODE="$4" \
      RESCUE_RANGERS_WEBHOOK_URL="http://stub.invalid/hook" FLEET_STANDING_BOX_SLUG="test-box" \
      bash "$1" > "$W/out" 2>"$W/err"
  fi
}
SECRET="synthetic-secret-VALUE-123"
hdr_count() { grep -c '^X-Rescue-Secret: ' "$W/argv" 2>/dev/null || true; }
jcheck() { "$PY" - "$W/body" "$W/hostile.txt" "$1" <<'PY'
import json, sys
b = json.load(open(sys.argv[1])); hostile = open(sys.argv[2]).read(); mode = sys.argv[3]
if mode == "escalate":
    assert b["problem"] == hostile, b["problem"]
    assert b["person"] == "Test Person" and b["boxName"] == "test-box" and b["clientName"] == "TEST client"
    assert b["alreadyTried"] == "1. tried `id`\n2. tried $HOME", b["alreadyTried"]
    assert b["returnTo"] == "0" and b["boxType"] == "Mac Mini" and b["agentName"] == "TEST agent"
    assert set(b) == {"action","person","clientName","agentName","boxName","boxType","openclawVersion","problem","alreadyTried","returnTo"}, sorted(b)
else:
    assert b["problem"] == 'RESOLVED: fixed with `id` and "quotes" $HOME', b["problem"]
    assert b["incident_id"] == "TEST-INC-1" and b["boxName"] == "test-box" and b["runtime_id"] == "test-box"
    assert b["attempt_id"] == "att-1" and b["operation_id"].startswith("res-TEST-INC-1-") and b["result_digest"].startswith("sha256-")
PY
}

echo "== escalate block (F15 header, F16 hostile text) =="
run_block "$W/escalate.sh" "$SECRET" '{"accepted":true,"ticketId":"TEST-T-9"}' 200
[ "$(hdr_count)" = 1 ] && ok "escalate: X-Rescue-Secret sent exactly once when secret set" || bad "escalate: header count $(hdr_count) != 1"
grep -qx "X-Rescue-Secret: $SECRET" "$W/argv" && ok "escalate: header carries the secret value" || bad "escalate: header value wrong"
jcheck escalate 2>"$W/jerr" && ok "escalate: file is valid JSON; hostile text literal; action + nine fields" || { bad "escalate: JSON/literal check ($(tail -1 "$W/jerr"))"; }
[ ! -e "$W/CANARY_BT" ] && [ ! -e "$W/CANARY_CS" ] && ok "escalate: backtick and \$(...) NOT executed" || bad "escalate: pasted text was executed"
grep -q "$SECRET" "$W/body" && bad "escalate: secret value leaked into posted JSON" || ok "escalate: secret value not expanded into posted JSON"
grep -qx 'incident_id=TEST-T-9' "$W/out" && ok "escalate: prints incident_id from response" || bad "escalate: incident_id line missing"
[ ! -e /tmp/rr-escalation.json ] || [ -n "${RR030_ALLOW_PRESENT:-}" ] && ok "escalate: temp file removed (or pre-existing, not ours)" || bad "escalate: /tmp/rr-escalation.json left behind"
run_block "$W/escalate.sh" "" '{"accepted":true}' 200
[ "$(hdr_count)" = 0 ] && ok "escalate: no header when secret unset" || bad "escalate: header sent with no secret"

echo "== resolve block (F15 header + status line, F16) =="
run_block "$W/resolve.sh" "$SECRET" '{"accepted":false,"error":"forbidden"}' 403
[ "$(hdr_count)" = 1 ] && ok "resolve: X-Rescue-Secret sent exactly once when secret set" || bad "resolve: header count $(hdr_count) != 1"
grep -qx "X-Rescue-Secret: $SECRET" "$W/argv" && ok "resolve: header carries the secret value" || bad "resolve: header value wrong"
tail -n 1 "$W/out" | grep -qx 403 && ok "resolve: prints HTTP status 403 as last line" || bad "resolve: status line missing (out: $(tail -c 120 "$W/out"))"
jcheck resolve 2>"$W/jerr" && ok "resolve: file is valid JSON; hostile text literal" || bad "resolve: JSON/literal check ($(tail -1 "$W/jerr"))"
run_block "$W/resolve.sh" "" '{"accepted":true}' 200
[ "$(hdr_count)" = 0 ] && ok "resolve: no header when secret unset" || bad "resolve: header sent with no secret"
tail -n 1 "$W/out" | grep -qx 200 && ok "resolve: prints HTTP status 200" || bad "resolve: 200 status line missing"

echo "== escalate block (F49 answer table: canned body + status -> printed state line) =="
state_of() { # state_of <body> <code>  -> first rescue_rangers_state line (or empty)
  run_block "$W/escalate.sh" "$SECRET" "$1" "$2"
  grep -m1 '^rescue_rangers_state=' "$W/out" || true
}
expect_state() { # expect_state <label> <body> <code> <state> <ticket-or-none>
  local got; got="$(state_of "$2" "$3")"
  [ "$got" = "rescue_rangers_state=$4 http=$3 ticket=$5" ] && ok "F49: $1 -> $4" || bad "F49: $1 -> got '$got'"
}
expect_state "200 + ticketId"                  '{"accepted":true,"ticketId":"TEST-T-1","status":"accepted"}' 200 accepted TEST-T-1
expect_state "200 duplicate_ignored"           '{"accepted":true,"ticketId":"TEST-T-1","status":"duplicate_ignored"}' 200 already_being_worked TEST-T-1
expect_state "200 accepted_human_followup"     '{"accepted":true,"ticketId":"TEST-T-2","status":"accepted_human_followup","message":"A person will follow up."}' 200 relay_message_and_stop TEST-T-2
expect_state "200 held_account_standing"       '{"accepted":true,"ticketId":"TEST-T-3","status":"held_account_standing","message":"Account on hold."}' 200 relay_message_and_stop TEST-T-3
expect_state "200 non_incident"                '{"accepted":true,"ticketId":null,"status":"non_incident"}' 200 not_an_incident none
expect_state "403 unauthorized (no ticketId)"  '{"status":"unauthorized"}' 403 secret_problem none
expect_state "400 invalid_payload"             '{"accepted":false,"status":"invalid_payload"}' 400 fix_payload none
expect_state "429 rate_limited"                '{"accepted":false,"status":"rate_limited","retryAfterSeconds":60}' 429 retry_once_in_2_minutes none
expect_state "503 admission_unavailable"       '{"accepted":false,"status":"admission_unavailable"}' 503 retry_once_in_2_minutes none
expect_state "200 with an unparseable body"    '<html>oops</html>' 200 unknown_do_not_assume_accepted none
run_block "$W/escalate.sh" "$SECRET" '{"accepted":true,"ticketId":"TEST-T-4","status":"accepted","notificationCapped":true}' 200
grep -qx 'rescue_rangers_capped=true' "$W/out" && ok "F49: notificationCapped:true prints rescue_rangers_capped=true" || bad "F49: capped line missing"
run_block "$W/escalate.sh" "$SECRET" '{"accepted":true,"ticketId":"TEST-T-5","status":"accepted_human_followup","message":"A person will follow up."}' 200
grep -qx 'rescue_rangers_message=A person will follow up.' "$W/out" && ok "F49: server message is relayed verbatim" || bad "F49: message line missing"
grep -qx 'incident_id=TEST-T-5' "$W/out" && ok "F49: incident_id still journalled for human-followup tickets" || bad "F49: incident_id line missing"
# the curl invocation asked for the status code
grep -q 'http_code' "$W/argv" && ok "F49: escalate curl captures the HTTP status (-w http_code)" || bad "F49: escalate curl does not capture the status"

echo "== template wording (F49) =="
grep -q 'Audit only' "$TPL" && ok "F49: returnTo described as audit-only" || bad "F49: returnTo still described as an answer channel"
grep -q 'must be posted' "$TPL" && bad "F49: stale 'answer must be posted' wording remains" || ok "F49: no 'answer must be posted' promise remains"
grep -q 'Hard cap: 25 exchanges' "$TPL" && bad "F49: old 25-exchange promise remains" || ok "F49: old 25-exchange promise removed"
grep -q 'notificationCapped' "$TPL" && ok "F49: notificationCapped rule present" || bad "F49: notificationCapped rule missing"
grep -q '5252140759' "$TPL" && bad "F49/D13: 5252140759 still appears in the canonical template" || ok "F49/D13: 5252140759 absent from the canonical template"
grep -q '5252140759' "$MIRROR" && bad "F49/D13: 5252140759 still appears in the role-library template" || ok "F49/D13: 5252140759 absent from the role-library template"
grep -q "Trevor's chat" "$TPL" && bad "F49/D13: a 'Trevor's chat' routing line remains" || ok "F49/D13: no line routes agents to Trevor's chat"
grep -q 'do NOT message any personal chat' "$TPL" && ok "F49/D13: missing-env guidance points to the owner, not a personal chat" || bad "F49/D13: missing-env guidance wording absent"

echo; echo "RR-030 escalation-template snippets: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
