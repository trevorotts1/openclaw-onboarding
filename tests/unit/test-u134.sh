#!/usr/bin/env bash
# tests/unit/test-u134.sh -- U134 Fleet Tool Allowlist config-patch propagation.
set -euo pipefail

PASS=0; FAIL=0; ERRORS=()
ok()   { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); ERRORS+=("$1"); }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PATCH="$REPO_ROOT/scripts/u134-tool-allowlist-patch.sh"
US="$REPO_ROOT/update-skills.sh"
LIB="$REPO_ROOT/hooks/lib-ceo-tool-gate.sh"

# Create a mock 'openclaw' that always validates successfully, to prevent the
# u134 patch script from reverting its changes when it runs on a minimal mock
# config that the real openclaw CLI considers invalid.
MOCK_OC_DIR="$(mktemp -d)"
trap 'rm -rf "$MOCK_OC_DIR"' EXIT
cat > "$MOCK_OC_DIR/openclaw" <<'MOCK'
#!/bin/sh
if [ "$1" = "config" ] && [ "$2" = "validate" ]; then exit 0; fi
exec /usr/bin/false
MOCK
chmod +x "$MOCK_OC_DIR/openclaw"

# Helper: run the patch with PATH pointing at our mock openclaw first
run_patch() {
  local home_dir="$1"
  PATH="$MOCK_OC_DIR:$PATH" HOME="$home_dir" bash "$PATCH" >/dev/null 2>&1 || true
}

echo ""
echo "=== U134 -- Fleet Tool Allowlist config-patch propagation ==="

# ---------------------------------------------------------------------------
# (A) Existence + syntax
# ---------------------------------------------------------------------------
echo ""; echo "--- (A) Existence + syntax ---"

[ -f "$PATCH" ] && ok "(A1) u134-tool-allowlist-patch.sh exists" || fail "(A1) NOT FOUND"
bash -n "$PATCH" 2>&1 && ok "(A2) u134-tool-allowlist-patch.sh bash -n passes" || fail "(A2) bash -n FAILS"
[ -f "$LIB" ] && ok "(A3) lib-ceo-tool-gate.sh exists" || fail "(A3) lib NOT FOUND"
bash -n "$LIB" 2>&1 && ok "(A3b) lib-ceo-tool-gate.sh bash -n passes" || fail "(A3b) bash -n FAILS"

# ---------------------------------------------------------------------------
# (B) Wired into update-skills.sh
# ---------------------------------------------------------------------------
echo ""; echo "--- (B) Wired into update-skills.sh ---"

grep -q 'u134-tool-allowlist-patch.sh' "$US" && ok "(B1) u134-tool-allowlist-patch.sh referenced in update-skills.sh" || fail "(B1) NOT referenced"
grep -q 'U134' "$US" && ok "(B2) U134 label present in update-skills.sh" || fail "(B2) U134 label missing"
bash -n "$US" 2>&1 && ok "(B3) update-skills.sh bash -n passes" || fail "(B3) bash -n FAILS"

# ---------------------------------------------------------------------------
# (C) Main behavior: applies deny, allow, and byProvider to a fresh config
# ---------------------------------------------------------------------------
echo ""; echo "--- (C) Main behavior ---"

TD_C=$(mktemp -d)
trap 'rm -rf "$TD_C"' EXIT
mkdir -p "$TD_C/.openclaw"
echo '{"agents":{"list":[{"id":"main","default":true,"name":"CEO","is_master":true,"workspace":"/tmp/cws"}]}}' > "$TD_C/.openclaw/openclaw.json"

run_patch "$TD_C"

C_OUT="$(HOME="$TD_C" python3 -c "
import json; c = json.load(open('$TD_C/.openclaw/openclaw.json'))
ag = next(a for a in c['agents']['list'] if a.get('id') == 'main')
t = ag.get('tools', {}); al = t.get('allow', []); de = t.get('deny', []); bp = t.get('byProvider', {})
print('AL=%d DE=%d BP=%d READ=%s BRW=%s GHL=%s' % (
    len(al), len(de), len(bp), 'read' in al, 'browser' in de, 'ghl-community-mcp' in bp
))
")"
echo "$C_OUT" | grep -qE 'AL=1[2-9]' && ok "(C1) allow count >= 12: $C_OUT" || fail "(C1) allow count wrong: $C_OUT"
echo "$C_OUT" | grep -qE 'DE=[7-9]' && ok "(C2) deny count >= 7: $C_OUT" || fail "(C2) deny count wrong: $C_OUT"
echo "$C_OUT" | grep -qE 'BP=2' && ok "(C3) MCP byProvider has 2 entries: $C_OUT" || fail "(C3) MCP count wrong: $C_OUT"
echo "$C_OUT" | grep -q 'READ=True' && ok "(C4) 'read' in allow list" || fail "(C4) 'read' NOT in allow: $C_OUT"
echo "$C_OUT" | grep -q 'BRW=True' && ok "(C5) 'browser' in deny list" || fail "(C5) 'browser' NOT in deny: $C_OUT"
echo "$C_OUT" | grep -q 'GHL=True' && ok "(C6) ghl-community-mcp in byProvider" || fail "(C6) ghl-community-mcp NOT in byProvider: $C_OUT"

# ---------------------------------------------------------------------------
# (D) No-op idempotency: re-run on already-canonical config
# ---------------------------------------------------------------------------
echo ""; echo "--- (D) No-op idempotency ---"

run_patch "$TD_C"
D_OUT="$(HOME="$TD_C" python3 -c "
import json; c = json.load(open('$TD_C/.openclaw/openclaw.json'))
ag = next(a for a in c['agents']['list'] if a.get('id') == 'main')
t = ag.get('tools', {}); al = t.get('allow', []); de = t.get('deny', []); bp = t.get('byProvider', {})
print('AL=%d DE=%d BP=%d READ=%s BRW=%s' % (
    len(al), len(de), len(bp), 'read' in al, 'browser' in de
))
")"
echo "$D_OUT" | grep -qE 'AL=1[2-9]' && ok "(D1) no-op re-run preserves allow count: $D_OUT" || fail "(D1) allow count changed: $D_OUT"
echo "$D_OUT" | grep -qE 'DE=[7-9]' && ok "(D2) no-op re-run preserves deny count: $D_OUT" || fail "(D2) deny count changed: $D_OUT"
echo "$D_OUT" | grep -q 'BRW=True' && ok "(D3) no-op re-run 'browser' still denied" || fail "(D3) 'browser' missing: $D_OUT"

# ---------------------------------------------------------------------------
# (E) Local-only tools preserved (custom entries in allow/deny)
# ---------------------------------------------------------------------------
echo ""; echo "--- (E) Local-only preserved ---"

TD_E=$(mktemp -d); mkdir -p "$TD_E/.openclaw"
echo '{"agents":{"list":[{"id":"main","default":true,"name":"CEO","is_master":true,"workspace":"/tmp/ews","tools":{"allow":["read","message","local-custom","local-probe"],"deny":["local-deny"]}}]}}' > "$TD_E/.openclaw/openclaw.json"

run_patch "$TD_E"

E_OUT="$(HOME="$TD_E" python3 -c "
import json; c = json.load(open('$TD_E/.openclaw/openclaw.json'))
ag = next(a for a in c['agents']['list'] if a.get('id') == 'main')
t = ag.get('tools', {}); al = t.get('allow', []); de = t.get('deny', [])
print('%s %s %s %s' % ('local-custom' in al, 'local-probe' in al, 'local-deny' in de, 'read' in al))
")"
echo "$E_OUT" | grep -q 'True True True True' && ok "(E1) local tools preserved" || fail "(E1) local tools LOST: $E_OUT"

# ---------------------------------------------------------------------------
# (F) PA / non-router agent is skipped (no tools block added)
# ---------------------------------------------------------------------------
echo ""; echo "--- (F) Non-router (PA) skip ---"

TD_F=$(mktemp -d); mkdir -p "$TD_F/.openclaw"
echo '{"agents":{"list":[{"id":"personal-assistant","default":true,"name":"Assistant","is_master":false,"workspace":"/tmp/fws"}]}}' > "$TD_F/.openclaw/openclaw.json"

run_patch "$TD_F"

F_OUT="$(HOME="$TD_F" python3 -c "
import json; c = json.load(open('$TD_F/.openclaw/openclaw.json'))
ag = next((a for a in c['agents']['list'] if a.get('default') is True), None)
t = ag.get('tools', {}) if ag else {}
print('tools_block' if t.get('deny') or t.get('allow') else 'PA_SKIP')
")"
echo "$F_OUT" | grep -q 'PA_SKIP' && ok "(F1) PA agent skipped (no tools block added)" || fail "(F1) PA agent got tools: $F_OUT"

# ---------------------------------------------------------------------------
# (G) Mutation proof
# ---------------------------------------------------------------------------
echo ""; echo "--- (G) Mutation proof ---"

TD_G=$(mktemp -d); mkdir -p "$TD_G/.openclaw"
echo '{"agents":{"list":[{"id":"main","default":true,"name":"CEO","is_master":true,"workspace":"/tmp/gws"}]}}' > "$TD_G/.openclaw/openclaw.json"
run_patch "$TD_G"

# G1: unmutated — 'browser' should be in deny
G1="$(HOME="$TD_G" python3 -c "
import json; c = json.load(open('$TD_G/.openclaw/openclaw.json'))
ag = next(a for a in c['agents']['list'] if a.get('id') == 'main')
print('browser' in ag.get('tools', {}).get('deny', []))
")"
[ "$G1" = "True" ] && ok "(G1) unmutated GREEN: browser in deny" || fail "(G1) browser NOT in deny"

# G2: mutate the source-of-truth in the lib (remove "browser" from deny list)
# We create a temp modified lib file and modify the patch to source it.
MUT_LIB="$TD_G/lib-ceo-tool-gate-mutated.sh"
sed 's/"browser"/"browser_mutated_broken"/g' "$LIB" > "$MUT_LIB"
MUT_PATCH="$TD_G/u134-mutated.sh"
sed "s|hooks/lib-ceo-tool-gate.sh|$MUT_LIB|g" "$PATCH" > "$MUT_PATCH"
chmod +x "$MUT_PATCH"
rm -f "$TD_G/.openclaw/openclaw.json"
echo '{"agents":{"list":[{"id":"main","default":true,"name":"CEO","is_master":true,"workspace":"/tmp/gws"}]}}' > "$TD_G/.openclaw/openclaw.json"
PATH="$MOCK_OC_DIR:$PATH" HOME="$TD_G" bash "$MUT_PATCH" >/dev/null 2>&1 || true
G2="$(HOME="$TD_G" python3 -c "
import json; c = json.load(open('$TD_G/.openclaw/openclaw.json'))
ag = next(a for a in c['agents']['list'] if a.get('id') == 'main')
print('browser' in ag.get('tools', {}).get('deny', []))
")"
[ "$G2" = "False" ] && ok "(G2) mutated RED (browser missing from deny after mutation)" || fail "(G2) browser STILL in deny — mutation undetected"

# G3: reverted — run patch with original lib, browser should be back
rm -f "$TD_G/.openclaw/openclaw.json"
echo '{"agents":{"list":[{"id":"main","default":true,"name":"CEO","is_master":true,"workspace":"/tmp/gws"}]}}' > "$TD_G/.openclaw/openclaw.json"
run_patch "$TD_G"
G3="$(HOME="$TD_G" python3 -c "
import json; c = json.load(open('$TD_G/.openclaw/openclaw.json'))
ag = next(a for a in c['agents']['list'] if a.get('id') == 'main')
print('browser' in ag.get('tools', {}).get('deny', []))
")"
[ "$G3" = "True" ] && ok "(G3) reverted GREEN (browser back in deny)" || fail "(G3) browser STILL missing"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""; echo "=== Summary ==="
echo "  PASS: $PASS  FAIL: $FAIL"
[ "$FAIL" -gt 0 ] && { for e in "${ERRORS[@]}"; do echo "    - $e"; done; echo "FINAL: RED"; exit 1; }
echo "FINAL: GREEN"; exit 0
