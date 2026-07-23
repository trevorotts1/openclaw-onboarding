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
#   SYNC NOTE (mc-route ship): CEO_GATE_ALLOW_TOOLS now carries the shipped
#   `mc-route__route_task` routing tool (below). This canonical source LEADS; the
#   write-sites that actually stamp the config onto boxes — build-workforce.py and
#   scripts/apply-routing-fix.sh / scripts/apply-fleet-standards.sh (whose inline
#   allow lists still read `"exec"  # INTERIM — replace with mc-route__route_task
#   once that MCP tool ships`) — must be re-synced by their owners to add
#   mc-route__route_task so a real box's G7 clears. Until then boxes stay in the
#   PRE-EXISTING INTERIM state (no regression). See docs/MC-ROUTE.md.
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
#
# `mc-route__route_task` is the SHIPPED routing tool (scripts/mc-route.sh is its
# signed implementation — the general form of route-presentation.sh: signs Bearer
# + HMAC, POSTs /api/tasks/ingest for ANY <department_slug>). The CEO routes by
# CALLING this tool — a structured tool call, no shell — so routing NO LONGER
# depends on `exec`. Its presence CLEARS the verify-routing.sh G7 INTERIM
# classification: G7 treats exec-in-allow as a hole ONLY when NO `*__route_task`
# tool is present (verify-routing.sh:500-503).
#
# `exec` is RETAINED (not removed) ONLY as the execution channel for the two
# ANCHORED, intent-gate-carved sanctioned shell helpers — route-presentation.sh
# (REFLEX V2 STEP 1) and mc-route.sh — NOT as a general routing path. OpenClaw's
# config-layer exec policy is {security,ask} and CANNOT command-allowlist, so the
# command-level "only the sanctioned helpers" restriction is enforced by the
# PreToolUse intent-gate (hooks/ceo-intent-gate.sh), which default-DENIES every
# other exec. Dropping exec HERE would deny the CEO the route-presentation.sh
# helper the reflex mandates (a documented flow), because a config-layer deny is
# restrict-only and cannot be un-denied by the hook. exec is retired outright ONLY
# once the reflex migrates route-presentation.sh onto mc-route__route_task
# (AGENTS.md + apply-*.sh — see docs/MC-ROUTE.md "Follow-ups for other owners").
#
# FABLE-5 FIX — PLUGIN / OPERATIONAL TOOLS (the over-restrictive-allowlist bug):
# The original list carried ONLY routing/conversation tools. Because OpenClaw
# resolves an explicit per-agent `tools.allow` as a HARD allowlist, ANY tool not
# named here was stripped from the CEO — including the tools its PLUGINS call.
# active-memory calls `memory_search` + `memory_get`; with neither in the allow
# list the plugin's tool calls resolved to nothing and the gateway errored
# "No callable tools remain after resolving explicit tool allowlist." The fix is
# to admit the plugin + operational tools the CEO legitimately needs to FUNCTION
# (memory, cron scheduling, gateway/node introspection) while the PRODUCTION tools
# stay DENIED below — routing-to-departments remains behavioral DOCTRINE (AGENTS.md
# / SOUL.md), not a tool-removal. This is additive: the deny list is untouched, so
# verify-routing.sh G7 still PASSES (exec + mc-route__route_task both present).
CEO_GATE_ALLOW_TOOLS=(
  "read" "web_fetch" "web_search"
  "message" "telegram" "slack" "discord"
  "sessions_send" "sessions_list" "sessions_history"
  "mc-route__route_task"
  "exec"
  # Plugin tools — active-memory (and the memory layer generally) needs these to
  # recall/persist. Without them the plugin's tool calls resolve to nothing.
  "memory_search" "memory_get"
  # Operational tools the orchestrator needs to run itself (schedule heartbeats,
  # introspect the gateway/nodes) — NOT production content tools.
  "cron" "gateway" "nodes"
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

# Emit the canonical GATED PER-AGENT `tools` object as JSON on stdout. The grant
# script uses this to RESTORE the gate on --revoke, and build-time/L5 use the
# identical shape. byProvider denies all tools from each GHL MCP server.
#
# v16.1.3 FIX — this is the PER-AGENT tools block, which is additionalProperties:
# false (allowed keys: allow/alsoAllow/byProvider/codeMode/deny/elevated/exec/fs/
# loopDetection/message/profile/sandbox/toolsBySender). It therefore carries ONLY
# deny/allow/byProvider. The cross-agent routing tools — sessions.visibility and
# agentToAgent — are ROOT `tools` keys (config["tools"]); emitting them here put
# them on the per-agent block and failed `openclaw config validate` (reload
# skipped → cron engine down on router-default boxes). They are now set on ROOT
# `tools` by apply-routing-fix.sh / apply-fleet-standards.sh / build-workforce.py.
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
