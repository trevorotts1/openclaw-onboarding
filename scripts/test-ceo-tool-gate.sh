#!/usr/bin/env bash
# test-ceo-tool-gate.sh — GOAL-5 Item 1 self-test for the CEO tool-gate.
#
# Asserts the four write-sites of the CEO tool-gate carry the SAME canonical
# constants (drift between them is the classic way a "fixed" box ships ungated):
#
#   1. 23-ai-workforce-blueprint/scripts/build-workforce.py  (build-time origin)
#   2. scripts/apply-routing-fix.sh  Layer 5                  (already-built boxes)
#   3. scripts/apply-fleet-standards.sh  re-assert            (fleet roll)
#   4. hooks/lib-ceo-tool-gate.sh                             (grant/verify source)
#
# Then exercises:
#   A. apply-routing-fix.sh L5 gates an ungated box (deny ⊇ canonical set).
#   B. L5 is idempotent (second run = no-op).
#   C. grant-ceo-consent.sh lifts the gate (consented) then --revoke restores it.
#   D. L5 SKIPS while an owner-consent grant is active (never revokes the owner).
#   E. verify-routing.sh G7 reports the gated box correctly (INTERIM warn / PASS).
#
# Exit 0 = all pass. Exit 1 = a drift or behavior failure (FATAL).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ONBOARDING_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_WF="$ONBOARDING_DIR/23-ai-workforce-blueprint/scripts/build-workforce.py"
APPLY_FIX="$SCRIPT_DIR/apply-routing-fix.sh"
APPLY_STD="$SCRIPT_DIR/apply-fleet-standards.sh"
GATE_LIB="$ONBOARDING_DIR/hooks/lib-ceo-tool-gate.sh"
GRANT="$SCRIPT_DIR/grant-ceo-consent.sh"
VERIFY="$SCRIPT_DIR/verify-routing.sh"

FAILS=0
_ok()   { printf '[test-ceo-tool-gate] PASS  %s\n' "$*"; }
_bad()  { printf '[test-ceo-tool-gate] FAIL  %s\n' "$*" >&2; FAILS=$((FAILS+1)); }

# Canonical expected sets (the single source of truth this test enforces).
EXPECT_DENY="apply_patch browser canvas edit ghl-community-mcp__* ghl-mcp__* image process write"
EXPECT_ALLOW="discord exec message read sessions_history sessions_list sessions_send slack telegram web_fetch web_search"
EXPECT_MCP="ghl-community-mcp ghl-mcp"

# ── 1. lib-ceo-tool-gate.sh is the reference; extract its canonical sets ───────
# shellcheck source=/dev/null
. "$GATE_LIB"
LIB_DENY=$(printf '%s\n' "${CEO_GATE_DENY_TOOLS[@]}" | sort | tr '\n' ' ' | sed 's/ $//')
LIB_ALLOW=$(printf '%s\n' "${CEO_GATE_ALLOW_TOOLS[@]}" | sort | tr '\n' ' ' | sed 's/ $//')
LIB_MCP=$(printf '%s\n' "${CEO_GATE_MCP_PROVIDERS[@]}" | sort | tr '\n' ' ' | sed 's/ $//')

[ "$LIB_DENY" = "$EXPECT_DENY" ]   && _ok "lib deny set canonical"   || _bad "lib deny drift: [$LIB_DENY] != [$EXPECT_DENY]"
[ "$LIB_ALLOW" = "$EXPECT_ALLOW" ] && _ok "lib allow set canonical" || _bad "lib allow drift: [$LIB_ALLOW] != [$EXPECT_ALLOW]"
[ "$LIB_MCP" = "$EXPECT_MCP" ]     && _ok "lib mcp set canonical"   || _bad "lib mcp drift: [$LIB_MCP] != [$EXPECT_MCP]"

# ── 2. Each write-site must mention every canonical deny token ────────────────
# Coarse but effective: a missing token in any site is a drift we must catch.
for tok in write edit apply_patch browser canvas image process "ghl-community-mcp__\*"; do
  for f in "$BUILD_WF" "$APPLY_FIX" "$APPLY_STD"; do
    if ! grep -qE "\"${tok}\"|'${tok}'" "$f"; then
      _bad "deny token '${tok}' missing from $(basename "$f")"
    fi
  done
done
_ok "deny tokens present across build-workforce.py / apply-routing-fix.sh / apply-fleet-standards.sh"

# Each site must deny BOTH GHL MCP providers.
for prov in "ghl-community-mcp" "ghl-mcp"; do
  for f in "$BUILD_WF" "$APPLY_FIX" "$APPLY_STD"; do
    grep -q "\"${prov}\"" "$f" || _bad "MCP provider '${prov}' missing from $(basename "$f")"
  done
done
_ok "both GHL MCP providers denied across all write-sites"

# ── 3. Behavior tests in a sandbox HOME ──────────────────────────────────────
SB="$(mktemp -d)"; STUB="$(mktemp -d)"
trap 'rm -rf "$SB" "$STUB"' EXIT
export HOME="$SB"
mkdir -p "$HOME/.openclaw/workspace" "$HOME/.openclaw/state" "$HOME/projects/command-center"
# stub openclaw so `config validate` / `gateway reload` are no-ops
printf '#!/bin/sh\nexit 0\n' > "$STUB/openclaw"; chmod +x "$STUB/openclaw"
export PATH="$STUB:$PATH"
export CEO_CONSENT_FILE="$HOME/.openclaw/state/ceo-consent.json"

_write_ungated() {
  cat > "$HOME/.openclaw/openclaw.json" <<'JSON'
{ "agents": { "list": [ { "id": "main", "default": true, "skills": [] } ] } }
JSON
}

# A. apply gate
_write_ungated
bash "$APPLY_FIX" >/dev/null 2>&1 || true
if python3 - "$HOME/.openclaw/openclaw.json" <<'PYEOF'
import json,sys
m=[a for a in json.load(open(sys.argv[1]))["agents"]["list"] if a["id"]=="main"][0]
t=m.get("tools",{})
need={"write","edit","apply_patch","browser","canvas","image","process"}
ok = need.issubset(set(t.get("deny") or [])) and \
     (t.get("byProvider",{}).get("ghl-community-mcp",{}).get("deny")==["*"]) and \
     "exec" in (t.get("allow") or []) and m.get("skills")==[]
sys.exit(0 if ok else 1)
PYEOF
then _ok "A: L5 gates an ungated box (deny set + GHL MCP + skills:[] preserved)"
else _bad "A: L5 did not gate the box correctly"; fi

# B. idempotent
B_OUT=$(bash "$APPLY_FIX" 2>&1 | grep -E "L5:.*already" || true)
[ -n "$B_OUT" ] && _ok "B: L5 idempotent (no-op on re-run)" || _bad "B: L5 not idempotent"

# C. consent lifts + revoke restores
bash "$GRANT" "task:zzz" --phrase "owner says do it" >/dev/null 2>&1 || true
if python3 - "$HOME/.openclaw/openclaw.json" <<'PYEOF'
import json,sys
m=[a for a in json.load(open(sys.argv[1]))["agents"]["list"] if a["id"]=="main"][0]
t=m.get("tools",{})
# gate LIFTED: no production deny present
sys.exit(0 if "write" not in (t.get("deny") or []) else 1)
PYEOF
then _ok "C1: grant lifted the gate (production deny removed)"
else _bad "C1: grant did NOT lift the gate"; fi

bash "$GRANT" --revoke >/dev/null 2>&1 || true
if python3 - "$HOME/.openclaw/openclaw.json" <<'PYEOF'
import json,sys
m=[a for a in json.load(open(sys.argv[1]))["agents"]["list"] if a["id"]=="main"][0]
t=m.get("tools",{})
sys.exit(0 if "write" in (t.get("deny") or []) and t.get("byProvider",{}).get("ghl-community-mcp",{}).get("deny")==["*"] else 1)
PYEOF
then _ok "C2: revoke restored the gate (deny + GHL MCP back)"
else _bad "C2: revoke did NOT restore the gate"; fi

# D. L5 skips while consent active
_write_ungated
printf '{"granted":true,"scope":"global"}\n' > "$CEO_CONSENT_FILE"
D_OUT=$(bash "$APPLY_FIX" 2>&1 | grep -E "L5:.*consent.*ACTIVE|CONSENT_ACTIVE" || true)
if [ -n "$D_OUT" ] && python3 - "$HOME/.openclaw/openclaw.json" <<'PYEOF'
import json,sys
m=[a for a in json.load(open(sys.argv[1]))["agents"]["list"] if a["id"]=="main"][0]
sys.exit(0 if "tools" not in m else 1)
PYEOF
then _ok "D: L5 skipped re-gate while consent active (owner grant preserved)"
else _bad "D: L5 re-gated despite active consent"; fi
rm -f "$CEO_CONSENT_FILE"

# E. verify-routing G7 (interim) reports gated-but-not-clean without a hard fail
_write_ungated
bash "$APPLY_FIX" >/dev/null 2>&1 || true
printf '<!-- ROLE_DISCIPLINE_V1 -->\nCEO_ROUTING_NO_LOOPHOLES_V1\n' > "$HOME/.openclaw/workspace/AGENTS.md"
printf '<!-- CEO_ORCHESTRATOR_RULE_V2 -->\n' > "$HOME/.openclaw/workspace/SOUL.md"
python3 -c "import sqlite3;c=sqlite3.connect('$HOME/projects/command-center/mission-control.db');c.execute('CREATE TABLE workspaces(id TEXT)');c.executemany('INSERT INTO workspaces VALUES(?)',[('default',),('presentations',)]);c.commit()"
E_OUT=$(bash "$VERIFY" 2>&1 || true)
if printf '%s' "$E_OUT" | grep -qE "G7: CEO tool-gate INTERIM|G7: CEO tool-gate present"; then
  _ok "E: verify-routing G7 evaluated the CEO tool-gate"
else
  _bad "E: verify-routing G7 did not evaluate the gate"
fi

# ── F. GOAL-4 D4 (4B+4C) — no-refusal baseline + CEO-deny COORDINATION ────────
# After apply-fleet-standards.sh runs, assert BOTH at once:
#   (a) agents.defaults.tools.allow == ["*"]   (no department/sub-agent refuses)
#   (b) main.tools.deny ⊇ production set        (CEO still gated — ungate did NOT
#                                                re-open the CEO via the baseline)
# This is the mechanical proof that the fleetwide ungate and the CEO tool-gate
# do not fight: the wildcard default is present AND the per-agent main deny holds.

# F0. Source-presence: the no-refusal baseline must exist in BOTH the fleet roll
#     (apply-fleet-standards.sh) and the build origin (build-workforce.py).
if grep -q 'agents.defaults.tools.allow' "$APPLY_STD" && grep -q 'agents.defaults.tools.allow' "$BUILD_WF"; then
  _ok "F0: no-refusal baseline (agents.defaults.tools.allow) present in fleet roll + build origin"
else
  _bad "F0: no-refusal baseline missing from apply-fleet-standards.sh and/or build-workforce.py"
fi

# F1. Behavior: run apply-fleet-standards.sh on an ungated sandbox box, then
#     assert the baseline AND the re-asserted CEO deny coexist.
rm -f "$CEO_CONSENT_FILE"
cat > "$HOME/.openclaw/openclaw.json" <<'JSON'
{ "agents": { "list": [ { "id": "main", "default": true, "skills": [] } ] } }
JSON
# apply-fleet-standards.sh validates via the stubbed `openclaw` (exit 0) and
# writes AGENTS.md/SOUL.md into $HOME/.openclaw/workspace (already created).
bash "$APPLY_STD" >/dev/null 2>&1 || true
if python3 - "$HOME/.openclaw/openclaw.json" <<'PYEOF'
import json,sys
cfg=json.load(open(sys.argv[1]))
# (a) defaults baseline
base = cfg.get("agents",{}).get("defaults",{}).get("tools",{}).get("allow")
base_ok = base == ["*"]
# (b) CEO still gated
m=[a for a in cfg["agents"]["list"] if a["id"]=="main"][0]
deny=set(m.get("tools",{}).get("deny") or [])
need={"write","edit","apply_patch","browser","canvas","image","process"}
ceo_ok = need.issubset(deny)
# (c) the wildcard did NOT leak into main's allow (deny-wins enforced)
main_allow=set(m.get("tools",{}).get("allow") or [])
no_leak = need.isdisjoint(main_allow) and "*" not in main_allow
sys.exit(0 if (base_ok and ceo_ok and no_leak) else 1)
PYEOF
then _ok "F1: ungate+gate coexist — agents.defaults.tools.allow==['*'] AND main.tools.deny ⊇ production set (no leak into main.allow)"
else _bad "F1: GOAL-4 D4 coordination broken — baseline absent OR CEO re-opened OR wildcard leaked into main.allow"; fi

# F2. Idempotent: a second apply-fleet-standards.sh run keeps both invariants
#     and does not duplicate the CEO deny entries.
bash "$APPLY_STD" >/dev/null 2>&1 || true
if python3 - "$HOME/.openclaw/openclaw.json" <<'PYEOF'
import json,sys
cfg=json.load(open(sys.argv[1]))
base = cfg.get("agents",{}).get("defaults",{}).get("tools",{}).get("allow")
m=[a for a in cfg["agents"]["list"] if a["id"]=="main"][0]
deny_list=m.get("tools",{}).get("deny") or []
deny=set(deny_list)
need={"write","edit","apply_patch","browser","canvas","image","process"}
no_dupes = len(deny_list)==len(deny)
sys.exit(0 if (base==["*"] and need.issubset(deny) and no_dupes) else 1)
PYEOF
then _ok "F2: apply-fleet-standards.sh idempotent (baseline stable, deny not duplicated)"
else _bad "F2: re-run drifted the baseline or duplicated the CEO deny"; fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
if [ "$FAILS" -eq 0 ]; then
  echo "[test-ceo-tool-gate] ALL PASS"
  exit 0
else
  echo "[test-ceo-tool-gate] $FAILS FAILURE(S)" >&2
  exit 1
fi
