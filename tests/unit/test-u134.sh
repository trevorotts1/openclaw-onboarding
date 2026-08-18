#!/usr/bin/env bash
# tests/unit/test-u134.sh -- u134-tool-allowlist-patch.sh INERT-CONTRACT guard.
#
# REWRITTEN 2026-08-05. This test used to assert that the patch script APPLIED
# the CEO production-tool deny (browser/write/edit/... in tools.deny) to a box's
# openclaw.json. That gate was retired per Trevor because denying `write` while
# memoryFlush demanded a memory write created a self-blocking loop that ate
# Telegram messages for two weeks. scripts/u134-tool-allowlist-patch.sh is now a
# deliberately INERT 10-line no-op, so the old assertions tested behavior that had
# been removed on purpose: the test sat at 9 PASS / 12 FAIL. It is referenced by
# NO GitHub workflow (verified: `git grep test-u134 -- .github/` returns no
# matches), so it was failing silently and nobody would have noticed.
#
# What this now guards is the INVERSE, which is the thing that actually matters:
# the script must STAY inert. If someone re-teaches it to write a production deny
# into a box config, the two-week outage comes back — and section D below fails.
#
# Exit 0 = GREEN. Exit 1 = RED.
set -euo pipefail

PASS=0; FAIL=0; ERRORS=()
ok()   { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); ERRORS+=("$1"); }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PATCH="$REPO_ROOT/scripts/u134-tool-allowlist-patch.sh"

# Mock `openclaw` so nothing reaches a real gateway or a real config.
MOCK_OC_DIR="$(mktemp -d)"
trap 'rm -rf "$MOCK_OC_DIR"' EXIT
cat > "$MOCK_OC_DIR/openclaw" <<'MOCK'
#!/bin/sh
if [ "$1" = "config" ] && [ "$2" = "validate" ]; then exit 0; fi
exec /usr/bin/false
MOCK
chmod +x "$MOCK_OC_DIR/openclaw"

# NEVER run against a real HOME — every invocation gets a throwaway one.
run_patch() {
  local home_dir="$1"
  PATH="$MOCK_OC_DIR:$PATH" HOME="$home_dir" bash "$PATCH" 2>&1 || true
}

_mk_box() {
  local d; d="$(mktemp -d)"; mkdir -p "$d/.openclaw"
  printf '%s\n' '{"agents":{"list":[{"id":"main","default":true,"name":"CEO","is_master":true,"workspace":"/tmp/ws"}]}}' \
    > "$d/.openclaw/openclaw.json"
  printf '%s' "$d"
}

echo ""
echo "=== U134 -- u134-tool-allowlist-patch.sh inert-contract guard ==="

# ---------------------------------------------------------------------------
# (A) Existence + syntax
# ---------------------------------------------------------------------------
echo ""; echo "--- (A) Existence + syntax ---"
[ -f "$PATCH" ] && ok "(A1) u134-tool-allowlist-patch.sh exists" || fail "(A1) NOT FOUND"
bash -n "$PATCH" 2>/dev/null && ok "(A2) bash -n clean" || fail "(A2) syntax error"

# ---------------------------------------------------------------------------
# (B) Inert contract: exits 0 and self-reports the SKIP
# ---------------------------------------------------------------------------
echo ""; echo "--- (B) Inert contract ---"
TD_B="$(_mk_box)"
B_OUT="$(run_patch "$TD_B")"
B_RC=0
PATH="$MOCK_OC_DIR:$PATH" HOME="$TD_B" bash "$PATCH" >/dev/null 2>&1 || B_RC=$?
[ "$B_RC" -eq 0 ] && ok "(B1) exits 0" || fail "(B1) exit code $B_RC (must be 0)"
printf '%s' "$B_OUT" | grep -q 'CANONICAL_SKIP' \
  && ok "(B2) reports STATUS: tool-allowlist=CANONICAL_SKIP" \
  || fail "(B2) did not report CANONICAL_SKIP — out=[$B_OUT]"

# ---------------------------------------------------------------------------
# (C) It has NO callers left (so a future edit cannot silently reach the fleet)
# ---------------------------------------------------------------------------
echo ""; echo "--- (C) No live call sites ---"
if grep -q 'u134-tool-allowlist-patch' "$REPO_ROOT/install.sh" "$REPO_ROOT/update-skills.sh" 2>/dev/null; then
  fail "(C1) still wired into install.sh/update-skills.sh — an inert script should not be invoked, and a NON-inert one must never reach a box"
else
  ok "(C1) not invoked from install.sh or update-skills.sh"
fi

# ---------------------------------------------------------------------------
# (D) THE REGRESSION GUARD — it must not touch a box config at all.
#     This is what catches a re-introduced production deny.
# ---------------------------------------------------------------------------
echo ""; echo "--- (D) Does not mutate a box config ---"
TD_D="$(_mk_box)"
CFG="$TD_D/.openclaw/openclaw.json"
BEFORE="$(shasum -a 256 "$CFG" | awk '{print $1}')"
run_patch "$TD_D" >/dev/null
AFTER="$(shasum -a 256 "$CFG" | awk '{print $1}')"
[ "$BEFORE" = "$AFTER" ] \
  && ok "(D1) openclaw.json byte-identical after run (sha256 unchanged)" \
  || fail "(D1) MUTATED the box config — the CEO deny may have been re-introduced"

D_DENY="$(python3 -c "
import json
c=json.load(open('$CFG'))
ag=next((a for a in c['agents']['list'] if a.get('id')=='main'),{})
t=ag.get('tools') or {}
print(','.join(sorted(t.get('deny') or [])) or 'NONE')
")"
[ "$D_DENY" = "NONE" ] \
  && ok "(D2) no tools.deny written on the router agent" \
  || fail "(D2) tools.deny was written: [$D_DENY] — the retired production deny is back"

# Re-run: still inert, still no config churn.
run_patch "$TD_D" >/dev/null
AFTER2="$(shasum -a 256 "$CFG" | awk '{print $1}')"
[ "$BEFORE" = "$AFTER2" ] \
  && ok "(D3) idempotent — second run also leaves the config byte-identical" \
  || fail "(D3) second run mutated the config"

# ---------------------------------------------------------------------------
# (E) MUTATION PROOF — prove (D) can actually FAIL, so a green D means something.
#     Plant a script that DOES write the retired deny and confirm D's probes
#     reject it. Without this, (D) could be passing for the wrong reason.
# ---------------------------------------------------------------------------
echo ""; echo "--- (E) Mutation proof ---"
TD_E="$(_mk_box)"
CFG_E="$TD_E/.openclaw/openclaw.json"
BAD="$TD_E/u134-mutated.sh"
cat > "$BAD" <<'BADEOF'
#!/usr/bin/env bash
set -euo pipefail
python3 - "$HOME/.openclaw/openclaw.json" <<'PY'
import json,sys
p=sys.argv[1]
c=json.load(open(p))
ag=next(a for a in c["agents"]["list"] if a.get("id")=="main")
ag.setdefault("tools",{})["deny"]=["browser","write","edit"]
json.dump(c,open(p,"w"),indent=2)
PY
BADEOF
chmod +x "$BAD"
E_BEFORE="$(shasum -a 256 "$CFG_E" | awk '{print $1}')"
PATH="$MOCK_OC_DIR:$PATH" HOME="$TD_E" bash "$BAD" >/dev/null 2>&1 || true
E_AFTER="$(shasum -a 256 "$CFG_E" | awk '{print $1}')"
[ "$E_BEFORE" != "$E_AFTER" ] \
  && ok "(E1) mutation proof: a deny-writing variant DOES change the sha256, so (D1) is a real assertion" \
  || fail "(E1) mutation proof FAILED — (D1) cannot detect a config write, so its PASS is meaningless"

E_DENY="$(python3 -c "
import json
c=json.load(open('$CFG_E'))
ag=next(a for a in c['agents']['list'] if a.get('id')=='main')
print(','.join(sorted((ag.get('tools') or {}).get('deny') or [])) or 'NONE')
")"
[ "$E_DENY" != "NONE" ] \
  && ok "(E2) mutation proof: the deny-writing variant is caught by (D2)'s probe [$E_DENY]" \
  || fail "(E2) mutation proof FAILED — (D2)'s probe cannot see a written deny"

rm -rf "$TD_B" "$TD_D" "$TD_E"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""; echo "=== Summary ==="
echo "  PASS: $PASS  FAIL: $FAIL"
[ "$FAIL" -gt 0 ] && { for e in "${ERRORS[@]}"; do echo "    - $e"; done; echo "FINAL: RED"; exit 1; }
echo "FINAL: GREEN"; exit 0
