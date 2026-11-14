#!/usr/bin/env bash
# tests/rescue/RR-030/test_escalation_tpl_snippets.sh   (RRX-020)
# The escalation section now teaches ONE command (rr_escalate.py) instead of
# hand-built curl requests. This test reads the REAL template
# scripts/rescue-escalation-section.md.tpl and asserts the shape an agent is
# taught:
#   - the marked block carries the RESCUE_ESCALATION_BOXNAME_V3 marker pair;
#   - its SECOND line is the rescue-identity line, carrying all four keys the
#     fleet roll harvests (clientName, agentName, boxType, returnTo);
#   - every fenced block that starts with RR_ROOT= is valid bash (`bash -n`);
#   - no line starting with `curl ` remains inside the marked block;
#   - the {{CLIENT}}, {{AGENT}} and {{BOX_TYPE}} tokens are still present.
# Kept from the previous version (they are not about the old snippets):
#   - the role-library copy is byte-identical to the canonical template;
#   - the operator's personal chat id appears in NEITHER copy;
#   - no line routes agents to Trevor's chat.
# Never touches the network.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
TPL="$REPO/scripts/rescue-escalation-section.md.tpl"
MIRROR="$REPO/23-ai-workforce-blueprint/templates/role-library/rescue-rangers/scripts/rescue-escalation-section.md.tpl"
[ -f "$TPL" ] || { echo "FATAL: $TPL missing"; exit 2; }
[ -f "$MIRROR" ] || { echo "FATAL: $MIRROR missing"; exit 2; }
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ok   $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL $1"; }
W="$(mktemp -d "${TMPDIR:-/tmp}/rr030-snip-XXXXXX")"; trap 'rm -rf "$W"' EXIT
PY="$(command -v python3)" || { echo "FATAL: python3 missing"; exit 2; }

echo "== template copies =="
cmp -s "$TPL" "$MIRROR" && ok "role-library template is byte-identical" || bad "role-library template differs from scripts/ template"

echo "== marked block shape =="
grep -qxF '<!-- RESCUE_ESCALATION_BOXNAME_V3 -->' "$TPL" && ok "start marker is RESCUE_ESCALATION_BOXNAME_V3 (own line)" || bad "start marker line missing or changed"
grep -qxF '<!-- END RESCUE_ESCALATION_BOXNAME_V3 -->' "$TPL" && ok "end marker is RESCUE_ESCALATION_BOXNAME_V3 (own line)" || bad "end marker line missing or changed"

echo "== rescue-identity contract =="
"$PY" - "$TPL" <<'PY'
import json, re, sys
t = open(sys.argv[1], encoding="utf-8").read()
lines = t.splitlines()
i = lines.index("<!-- RESCUE_ESCALATION_BOXNAME_V3 -->")
j = lines.index("<!-- END RESCUE_ESCALATION_BOXNAME_V3 -->")
assert i < j, "END marker must come after the start marker"
ident_line = lines[i + 1]
print("  second line: " + ident_line)
assert ident_line.startswith("<!-- rescue-identity"), "line after the start marker must be the rescue-identity line"
m = re.search(r"rescue-identity.*?:\s*(\{.*\})\s*-->", ident_line)
assert m, "rescue-identity line must carry a JSON object"
ident = json.loads(m.group(1))
expected = {"boxName", "clientName", "agentName", "boxType", "returnTo"}
assert set(ident) == expected, "identity keys are %r, expected %r" % (sorted(ident), sorted(expected))
assert ident["boxName"] == "{{BOX_NAME}}", "boxName token is not {{BOX_NAME}}"
assert ident["clientName"] == "{{CLIENT}}", "clientName token is not {{CLIENT}}"
assert ident["agentName"] == "{{AGENT}}", "agentName token is not {{AGENT}}"
assert ident["boxType"] == "{{BOX_TYPE}}", "boxType token is not {{BOX_TYPE}}"
assert ident["returnTo"] == "{{RETURN_TO}}", "returnTo token is not {{RETURN_TO}}"
blocks = [b for b in re.findall(r"```[^\n]*\n(.*?)\n```", t, re.S) if "rr_escalate.py" in b and " send " in b]
assert blocks, "the template no longer teaches an rr_escalate.py send command"
send = blocks[0]
assert "--person" in send, "the taught send command lost its --person flag"
assert "--client" in send and "--agent" in send and "--box-type" in send, "the taught send command lost its identity flags"
assert "--problem-file" in send and "--tried-file" in send, "the taught send command lost its problem/tried file flags"
assert not [ln for ln in t.splitlines() if ln.startswith("curl ")], "a hand-built curl line is back in the template"
PY
if [ $? -eq 0 ]; then ok "identity line and taught send command match the contract"; else bad "identity line or taught send command broke the contract"; fi

echo "== fenced RR_ROOT= blocks are valid bash =="
NB="$("$PY" - "$TPL" "$W" <<'PY'
import os, re, sys
tpl, w = sys.argv[1], sys.argv[2]
t = open(tpl, encoding="utf-8").read()
blocks = re.findall(r"```[^\n]*\n(.*?)\n```", t, re.S)
sel = [b for b in blocks if b.startswith("RR_ROOT=")]
out = os.path.join(w, "blocks")
os.makedirs(out, exist_ok=True)
for i, b in enumerate(sel):
    with open(os.path.join(out, "%02d.sh" % i), "w", encoding="utf-8") as fh:
        fh.write(b + "\n")
print(len(sel))
PY
)"
NB="${NB:-0}"
[ "$NB" -ge 3 ] && ok "found $NB fenced RR_ROOT= blocks (send, status, resolve at least)" || bad "found only $NB fenced RR_ROOT= blocks, expected at least 3"
n=0
for f in "$W"/blocks/*.sh; do
  [ -f "$f" ] || continue
  n=$((n+1))
  if bash -n "$f" 2>"$W/n.err"; then ok "block $(basename "$f") passes bash -n"; else bad "block $(basename "$f") fails bash -n: $(tail -1 "$W/n.err")"; fi
done
[ "$n" -ge 3 ] && ok "checked $n blocks" || bad "checked only $n blocks"

echo "== no hand-built curl inside the marked block =="
"$PY" - "$TPL" > "$W/curllines" <<'PY'
import sys
t = open(sys.argv[1], encoding="utf-8").read()
s = t.index("<!-- RESCUE_ESCALATION_BOXNAME_V3 -->")
e = t.index("<!-- END RESCUE_ESCALATION_BOXNAME_V3 -->")
bad = [ln for ln in t[s:e].splitlines() if ln.startswith("curl ")]
for ln in bad:
    print(ln)
PY
if [ -s "$W/curllines" ]; then bad "the marked block still starts a line with 'curl ' ($(wc -l < "$W/curllines" | tr -d ' ') line(s))"; else ok "no line inside the marked block starts with 'curl '"; fi

echo "== render tokens present =="
for _tok in '{{CLIENT}}' '{{AGENT}}' '{{BOX_TYPE}}'; do
  grep -qF "$_tok" "$TPL" && ok "template carries $_tok" || bad "template is missing $_tok"
done

echo "== D13 wording ==="
grep -q '5252140759' "$TPL" && bad "D13: 5252140759 still appears in the canonical template" || ok "D13: 5252140759 absent from the canonical template"
grep -q '5252140759' "$MIRROR" && bad "D13: 5252140759 still appears in the role-library template" || ok "D13: 5252140759 absent from the role-library template"
grep -q "Trevor's chat" "$TPL" && bad "D13: a 'Trevor's chat' routing line remains" || ok "D13: no line routes agents to Trevor's chat"

echo; echo "RR-030 escalation-template snippets: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
