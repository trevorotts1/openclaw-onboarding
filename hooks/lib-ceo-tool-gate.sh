#!/usr/bin/env bash
# lib-ceo-tool-gate.sh — Canonical CEO tool-gate state (GOAL-5 Item 1).
#
# THE single source of truth for the two CEO tool-policy postures:
#
#   GATED      (default): the orchestrator is a pure router. Production tools
#              (write/edit/apply_patch/browser/canvas/image/process + ALL GHL MCP
#              tools) are DENIED. Only routing/conversation tools are allowed.
#
#   CONSENTED  (owner carve-out): the production denies are LIFTED so the owner
#              can tell the CEO to do the work directly. Because OpenClaw tool
#              policy is RESTRICT-ONLY (a deny cannot be un-denied in-session,
#              docs.openclaw.ai/tools/multi-agent-sandbox-tools), the carve-out
#              cannot be an in-session `allow` — it MUST be a config ENTRY SWAP.
#              That is why grant-ceo-consent.sh rewrites the CEO agent's `tools`
#              block and the gateway reloads it; the swap is reverted on revoke.
#
# This file is sourced by:
#   - scripts/grant-ceo-consent.sh  (performs / reverts the swap)
#   - scripts/verify-routing.sh G7  (asserts the GATED posture is present)
#   - 23-ai-workforce-blueprint/scripts/build-workforce.py keeps an IDENTICAL
#     copy of these lists inline (CEO_TOOL_DENY/ALLOW/MCP_DENY) for the build-time
#     origin; keep the two in sync (one test asserts they match — see
#     scripts/test-ceo-tool-gate.sh).
#
# The HARD CONSTRAINT this satisfies: never strip the CEO's abilities outright.
# GATED is a gate, not a removal — CONSENTED restores everything.

# ─── Canonical tool lists (KEEP IN SYNC WITH build-workforce.py) ───────────────

# Production tools denied on the CEO in the GATED posture. Real built-in tool
# names from docs.openclaw.ai/gateway/security, plus GHL-MCP name-globs as a
# belt-and-suspenders fallback for any gateway version that does not honor
# tools.byProvider (denies always win and are restrict-only, so the extra glob
# is harmless where byProvider IS honored).
CEO_GATE_DENY_TOOLS=(
  "write" "edit" "apply_patch" "browser" "canvas" "image" "process"
  "ghl-community-mcp__*" "ghl-mcp__*"
)

# Tools the CEO keeps in BOTH postures so it can route + converse.
# NOTE: `exec` is INTERIM — kept so the CEO can curl POST /api/tasks/ingest until
# the dedicated route-task MCP tool ships fleet-wide (verify-routing.sh G7
# FAIL-WARNs while exec is present so a box is never falsely marked clean).
CEO_GATE_ALLOW_TOOLS=(
  "read" "web_fetch" "web_search"
  "message" "telegram" "slack" "discord"
  "sessions_send" "sessions_list" "sessions_history"
  "exec"
)

# GHL MCP servers to deny by provider in the GATED posture (both live ids).
CEO_GATE_MCP_PROVIDERS=( "ghl-community-mcp" "ghl-mcp" )

# ─── CANONICAL ROUTER IDENTITY (v13.2.2 — closes the v13.1.3 PA-freeze defect) ─
# THE single source of truth for "is this agent the router/CEO that must be
# gated?". The CEO tool-gate (production-tool deny) and the PreToolUse intent-gate
# may ONLY fire on a ROUTER (master-orchestrator / CEO / dept-executive-office)
# — NEVER on a hands-on personal-assistant or owner agent.
#
# WHY THIS EXISTS (the v13.1.3 regression):
#   v13.1.3 DEFECT-2 broadened the gate target from `id=="main"` to "whatever
#   agent is default:true". That is WRONG on boxes whose default agent is a
#   hands-on personal assistant (not a router): the broadened target clamped the
#   CEO production-lock onto the PA and FROZE it. The fix: gate the default agent
#   ONLY when it is also a ROUTER (by explicit marker or a known router id).
#
# An agent is a ROUTER when ANY of these hold (checked in this order):
#   1. is_master === true            (explicit boolean marker — preferred)
#   2. role     === "router"         (explicit string marker)
#   3. id ∈ ROUTER_IDS               (known router ids, the historical convention)
#
# Anything else — most importantly a default:true personal-assistant — is NOT a
# router and is NEVER gated. build-workforce.py already gates by router dept_id
# only ("ceo"/"master-orchestrator"/"dept-ceo"); this list is the post-build /
# verify-side mirror of that same intent, plus dept-executive-office and
# dept-master-orchestrator (the two router default-agent ids that a real router
# box may use), which were the legitimate v13.1.3 cases the broadening was meant
# to catch.
#
# Personal-assistant default-agent ids the gate must NEVER clamp (informational —
# the logic is "router => gate, else skip"; these are the known PA-default ids so
# the intent is auditable):
#   personal-assistant · pa · assistant · main-assistant · owner-assistant
CEO_ROUTER_IDS=(
  "main" "ceo" "dept-ceo"
  "master-orchestrator" "dept-master-orchestrator"
  "dept-executive-office"
)

# Newline-joined router-id list for the python helper (single source for both
# shell and python callers). Keep IN SYNC with verify-routing.sh / apply-*.sh,
# which embed an identical ROUTER_IDS list (test-ceo-tool-gate.sh asserts match).
ceo_router_ids_joined() { printf '%s\n' "${CEO_ROUTER_IDS[@]}"; }

# ceo_agent_is_router <agent-json>
#   stdin/arg: a JSON object for ONE agent entry.
#   exit 0 (true)  → the agent is a router/CEO and MUST be gated.
#   exit 1 (false) → the agent is NOT a router (e.g. a personal assistant) and
#                    MUST NOT be gated.
ceo_agent_is_router() {
  local _agent_json="$1"
  CEO_AGENT_JSON="$_agent_json" CEO_ROUTER_IDS="${CEO_ROUTER_IDS[*]}" python3 - <<'PYEOF'
import json, os, sys
try:
    ag = json.loads(os.environ.get("CEO_AGENT_JSON") or "{}")
except Exception:
    sys.exit(1)
if not isinstance(ag, dict):
    sys.exit(1)
router_ids = set((os.environ.get("CEO_ROUTER_IDS") or "").split())
if ag.get("is_master") is True:
    sys.exit(0)
if isinstance(ag.get("role"), str) and ag.get("role").strip().lower() == "router":
    sys.exit(0)
if ag.get("id") in router_ids:
    sys.exit(0)
sys.exit(1)
PYEOF
}

# Emit the canonical GATED `tools` object as JSON on stdout. The grant script
# uses this to RESTORE the gate on --revoke, and build-time/L5 use the identical
# shape. byProvider denies all tools from each GHL MCP server.
ceo_gate_tools_json() {
  python3 - "$@" <<'PYEOF'
import json, os
deny = os.environ["CEO_GATE_DENY"].split()
allow = os.environ["CEO_GATE_ALLOW"].split()
providers = os.environ["CEO_GATE_MCP"].split()
by_provider = {p: {"deny": ["*"]} for p in providers}
print(json.dumps({"deny": deny, "allow": allow, "byProvider": by_provider}))
PYEOF
}

# Convenience wrapper that exports the arrays into the env the python above reads.
ceo_gate_tools() {
  CEO_GATE_DENY="${CEO_GATE_DENY_TOOLS[*]}" \
  CEO_GATE_ALLOW="${CEO_GATE_ALLOW_TOOLS[*]}" \
  CEO_GATE_MCP="${CEO_GATE_MCP_PROVIDERS[*]}" \
  ceo_gate_tools_json
}
