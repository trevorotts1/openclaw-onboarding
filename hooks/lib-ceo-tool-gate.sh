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
