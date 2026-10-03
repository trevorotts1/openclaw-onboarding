#!/usr/bin/env bash
# tests/rescue/RR-030/test_escalation_tpl_snippets.sh   (RR plan fixes F15, F16)
# Extracts the two bash blocks (escalate, resolve) from the REAL template
# scripts/rescue-escalation-section.md.tpl, renders tokens, and runs each in
# `env -i bash` with a stub curl on PATH. Never touches the network.
#   F15: X-Rescue-Secret header sent exactly once by BOTH blocks when set, never when unset;
#        resolve block prints the HTTP status line.
#   F16: hostile free text (backtick, $(...), $SECRET, double quote, newline) stays literal,
#        is never executed or expanded, and the posted file is valid JSON.
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

echo; echo "RR-030 escalation-template snippets: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
