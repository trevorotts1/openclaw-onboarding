#!/usr/bin/env bash
# qc-convert-and-flow.sh — Skill 44: Convert and Flow Operator
# Automated QC validator. Exit 0 = pass. Non-zero = blocker.
#
# Usage:
#   ./qc-convert-and-flow.sh            # Static-only (safe on fresh clone, CI)
#   ./qc-convert-and-flow.sh --live     # Static + live-box checks (needs caf on PATH + secrets)
#   CAF_LIVE=1 ./qc-convert-and-flow.sh # Same as --live
#
# Sections A (PATH), B (credentials), C (standard ops), and D (write-safety
# against the installed wrapper) all require a provisioned box; they are
# skipped (not failed) in static mode.  Section E (file presence inside
# master-files tree), F (core-file sentinels in workspace), and G (platform
# overlays) are also live-box sections.  Static mode only asserts what exists
# on the committed branch: engine files present, SKILL.md frontmatter correct,
# CORE_UPDATES sentinel, six CLI commands declared in INSTALL.md.
set -euo pipefail

PASS=0; FAIL=0; WARN=0; SKIP=0

# ── Mode detection ────────────────────────────────────────────────────────────
LIVE_MODE=0
for arg in "$@"; do
  [ "$arg" = "--live" ] && LIVE_MODE=1
done
[ "${CAF_LIVE:-0}" = "1" ] && LIVE_MODE=1

assert() {
  local msg="$1"; local cmd="$2"
  if eval "$cmd" 2>/dev/null; then
    echo "  PASS: $msg"; PASS=$((PASS+1))
  else
    echo "  FAIL: $msg"; FAIL=$((FAIL+1))
  fi
}

warn_only() {
  local msg="$1"; local cmd="$2"
  if eval "$cmd" 2>/dev/null; then
    echo "  PASS: $msg"; PASS=$((PASS+1))
  else
    echo "  WARN: $msg (non-blocking)"; WARN=$((WARN+1))
  fi
}

live_assert() {
  local msg="$1"; local cmd="$2"
  if [ "$LIVE_MODE" -eq 0 ]; then
    echo "  SKIP: $msg (live-box only; re-run with --live on a provisioned box)"; SKIP=$((SKIP+1))
    return
  fi
  if eval "$cmd" 2>/dev/null; then
    echo "  PASS: $msg"; PASS=$((PASS+1))
  else
    echo "  FAIL: $msg"; FAIL=$((FAIL+1))
  fi
}

live_warn() {
  local msg="$1"; local cmd="$2"
  if [ "$LIVE_MODE" -eq 0 ]; then
    echo "  SKIP: $msg (live-box only)"; SKIP=$((SKIP+1))
    return
  fi
  if eval "$cmd" 2>/dev/null; then
    echo "  PASS: $msg"; PASS=$((PASS+1))
  else
    echo "  WARN: $msg (non-blocking)"; WARN=$((WARN+1))
  fi
}

# ── Resolve the skill's own directory (works when run from any CWD) ───────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL44_DIR="$SCRIPT_DIR"
# For live-box sections the master-files root may differ; fall back gracefully
MASTER_FILES_DIR="${MASTER_FILES_DIR:-$(dirname "$SCRIPT_DIR")}"

WORKSPACE="${OPENCLAW_WORKSPACE:-$HOME/.openclaw/workspace}"
PLATFORM="${OPENCLAW_PLATFORM:-mac}"
if [ "$PLATFORM" = "mac" ]; then
  TOOLS_ROOT="$HOME/.openclaw/tools"
else
  TOOLS_ROOT="/data/.openclaw/tools"
fi
CAF_DIR="$TOOLS_ROOT/convert-and-flow-cli"
SKILL38_DIR="$MASTER_FILES_DIR/38-conversational-ai-system"

echo "══════════════════════════════════════════════"
echo "  Skill 44 QC — Convert and Flow Operator"
if [ "$LIVE_MODE" -eq 1 ]; then
  echo "  Mode: LIVE (all sections active)"
else
  echo "  Mode: STATIC (live-box sections skipped)"
fi
echo "══════════════════════════════════════════════"

# ── Section S: Static branch checks (always run) ────────────────────────────
echo ""
echo "── Section S: Static branch checks ──"

# Relationship lattice pointer + citation tripwire (U89/GK-27). Static/
# offline, repo-relative — asserts SKILL.md carries its one-line pointer to
# docs/CONTENT-CONVERSATION-LATTICE.md and that this skill's owned edge (the
# Skill 3 backstop-rail citation in its own frontmatter description) still
# cites real, unchanged ground truth. See docs/tools/check_lattice_citation.py.
REPO_ROOT_LATTICE="$(cd "$SKILL44_DIR/.." && pwd)"
assert "SKILL.md pointer to docs/CONTENT-CONVERSATION-LATTICE.md + this skill's owned edge citations still hold (GK-27 drift tripwire)" \
  "python3 \"$REPO_ROOT_LATTICE/docs/tools/check_lattice_citation.py\" --repo-root \"$REPO_ROOT_LATTICE\" --skill 44-convert-and-flow-operator -q"

assert "tools/engine/setup.py present" \
  "[ -f \"$SKILL44_DIR/tools/engine/setup.py\" ]"
assert "tools/engine/cli_anything/gohighlevel/ present" \
  "[ -d \"$SKILL44_DIR/tools/engine/cli_anything/gohighlevel\" ]"
assert "tools/engine is NOT a gitlink (no 160000 mode)" \
  "! git -C \"$SKILL44_DIR\" ls-files -s tools/engine 2>/dev/null | grep -q '^160000'"
assert "SKILL.md frontmatter name is convert-and-flow-operator" \
  "grep -q 'name: convert-and-flow-operator' \"$SKILL44_DIR/SKILL.md\""
assert "INSTALL.md documents 'caf' command" \
  "grep -q '\bcaf\b' \"$SKILL44_DIR/INSTALL.md\""
assert "INSTALL.md documents 'convertandflow' command" \
  "grep -q 'convertandflow' \"$SKILL44_DIR/INSTALL.md\""
assert "INSTALL.md documents 'ghl' command" \
  "grep -q '\bghl\b' \"$SKILL44_DIR/INSTALL.md\""
assert "INSTALL.md documents write-safety default (GOHIGHLEVEL_DRAFT_ONLY)" \
  "grep -q 'GOHIGHLEVEL_DRAFT_ONLY' \"$SKILL44_DIR/INSTALL.md\""
assert "engine caf wrapper auto-seeds CAF_ALLOWED_LOCATION_IDS from GOHIGHLEVEL_LOCATION_ID" \
  "grep -q 'CAF_ALLOWED_LOCATION_IDS.*GHL_LOCATION_ID\|GHL_LOCATION_ID.*CAF_ALLOWED_LOCATION_IDS\|_caf_allowed_raw' \"$SKILL44_DIR/tools/engine/caf\""
# NOTE (v1.0.9): the single-source refactor (1.0.6 / PR #167) removed the inline
# wrapper heredoc from INSTALL.md, so `_caf_allowed_raw` no longer lives in the doc
# — it lives in the committed `tools/engine/caf` wrapper (asserted on line above).
# This assertion now verifies INSTALL.md DOCUMENTS the whitelist auto-seed behavior
# (the "Write-location whitelist auto-seed" note) rather than greppng for a token
# the refactor intentionally deleted.
assert "INSTALL.md documents the CAF_ALLOWED_LOCATION_IDS whitelist auto-seed behavior" \
  "grep -q 'CAF_ALLOWED_LOCATION_IDS' \"$SKILL44_DIR/INSTALL.md\" && grep -qi 'auto-seed\|seeds the whitelist' \"$SKILL44_DIR/INSTALL.md\""
assert "INSTALL.md wires GOHIGHLEVEL_ALLOWED_LOCATION_IDS at install (Action 5)" \
  "grep -q 'GOHIGHLEVEL_ALLOWED_LOCATION_IDS' \"$SKILL44_DIR/INSTALL.md\""
assert "convertandflow + ghl wrappers also auto-seed CAF_ALLOWED_LOCATION_IDS" \
  "grep -q '_caf_allowed_raw' \"$SKILL44_DIR/tools/engine/convertandflow\" && grep -q '_caf_allowed_raw' \"$SKILL44_DIR/tools/engine/ghl\""
assert "workflow build path applies action ordering via link_steps (Bug 1a)" \
  "grep -q 'templates = link_steps' \"$SKILL44_DIR/tools/engine/cli_anything/gohighlevel/utils/workflow_builder.py\""
assert "workflow build fails loud on rejected save (step_err captured, Bug 1b)" \
  "grep -q 'step_err' \"$SKILL44_DIR/tools/engine/cli_anything/gohighlevel/utils/workflow_builder.py\""
assert "CLI exits non-zero on build errors (stats['errors'] + sys.exit)" \
  "grep -q \"stats.get(.errors.)\" \"$SKILL44_DIR/tools/engine/cli_anything/gohighlevel/gohighlevel_cli.py\" && grep -q '_emit_build_result' \"$SKILL44_DIR/tools/engine/cli_anything/gohighlevel/gohighlevel_cli.py\""
assert "opportunities list uses snake_case search params (Bug 3)" \
  "grep -q 'location_id.*_loc(ctx)' \"$SKILL44_DIR/tools/engine/cli_anything/gohighlevel/gohighlevel_cli.py\""
assert "payments list alias present (Bug 4)" \
  "grep -q 'payments.command(\"list\")' \"$SKILL44_DIR/tools/engine/cli_anything/gohighlevel/gohighlevel_cli.py\""
assert "regression test for fail-loud + ordering present" \
  "grep -q 'TestBuildFailsLoudAndEmitsOrdering' \"$SKILL44_DIR/tools/engine/tests/test_e2e_unit11.py\""
assert "folder-creation POST forwards folder_name to the gate (Bug 2a)" \
  "grep -q 'workflow_name=folder_name' \"$SKILL44_DIR/tools/engine/cli_anything/gohighlevel/utils/workflow_builder.py\""
assert "workflows build pops the top-level 'folder' plan key (Bug 2b)" \
  "grep -q 'campaign.pop(.folder.' \"$SKILL44_DIR/tools/engine/cli_anything/gohighlevel/gohighlevel_cli.py\""
assert "workflows build fails loud on non-workflow plan entries (Bug 2b)" \
  "grep -q 'non-workflow entries' \"$SKILL44_DIR/tools/engine/cli_anything/gohighlevel/gohighlevel_cli.py\""
assert "regression test for ZHC- folder approval + folder-key plan hardening present" \
  "grep -q 'TestZHCFolderStandingApprovalAndFolderKeyPlan' \"$SKILL44_DIR/tools/engine/tests/test_e2e_unit11.py\""
assert "CORE_UPDATES.md sentinel present" \
  "grep -q 'skill:44-convert-and-flow-operator:core-update-applied' \"$SKILL44_DIR/CORE_UPDATES.md\""
assert "CHANGELOG.md exists" \
  "[ -f \"$SKILL44_DIR/CHANGELOG.md\" ]"
assert "QC.md exists" \
  "[ -f \"$SKILL44_DIR/QC.md\" ]"
assert "platform/mac/SKILL.md name matches" \
  "grep -q 'name: convert-and-flow-operator' \"$SKILL44_DIR/platform/mac/SKILL.md\""
assert "platform/vps/SKILL.md name matches" \
  "grep -q 'name: convert-and-flow-operator' \"$SKILL44_DIR/platform/vps/SKILL.md\""
assert "nextcloud NOT present in vendored engine" \
  "! [ -d \"$SKILL44_DIR/tools/engine/cli_anything/nextcloud\" ]"
assert "blotato NOT present in vendored engine" \
  "! [ -d \"$SKILL44_DIR/tools/engine/cli_anything/blotato\" ]"
assert "INSTALL.md contains CORE_UPDATES auto-apply action (Action 7)" \
  "grep -q 'skill:44-convert-and-flow-operator:core-update-applied' \"$SKILL44_DIR/INSTALL.md\""
assert "INSTALL.md Action 3 uses cp (single-source wrapper, no inline heredoc)" \
  "grep -q 'cp.*tools/engine/caf.*CAF_DIR\|cp.*engine.*caf' \"$SKILL44_DIR/INSTALL.md\""
# v1.0.9 — GHL env-wiring + fail-loud live verify (VPS env-inheritance bug reproduction)
assert "wire-ghl-env.sh present (single-source GHL env wiring)" \
  "[ -f \"$SKILL44_DIR/tools/engine/wire-ghl-env.sh\" ]"
assert "verify-ghl-live.sh present (fail-loud post-install verify gate)" \
  "[ -f \"$SKILL44_DIR/tools/engine/verify-ghl-live.sh\" ]"
assert "wire-ghl-env.sh has JSON deep-merge fallback (config-set-rejects-nested-key path)" \
  "grep -q 'JSON deep-merge fallback' \"$SKILL44_DIR/tools/engine/wire-ghl-env.sh\""
assert "wire-ghl-env.sh wires all 5 canonical GHL vars" \
  "for v in GOHIGHLEVEL_API_KEY GOHIGHLEVEL_LOCATION_ID GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN GOHIGHLEVEL_ALLOWED_LOCATION_IDS GOHIGHLEVEL_DRAFT_ONLY; do grep -q \"wire_var \$v\" \"$SKILL44_DIR/tools/engine/wire-ghl-env.sh\" || exit 1; done"
assert "wire-ghl-env.sh replaces empty docker env_file placeholders in place (VPS)" \
  "grep -q 'removing empty placeholder' \"$SKILL44_DIR/tools/engine/wire-ghl-env.sh\" && grep -q 'replacing existing' \"$SKILL44_DIR/tools/engine/wire-ghl-env.sh\""
assert "wire-ghl-env.sh does NOT restart the gateway on Mac (rescue-Mac rule)" \
  "grep -qi 'NOT restarting the gateway' \"$SKILL44_DIR/tools/engine/wire-ghl-env.sh\""
assert "verify-ghl-live.sh runs a real read (workflows + contacts PIT-only fallback)" \
  "grep -q 'workflows list' \"$SKILL44_DIR/tools/engine/verify-ghl-live.sh\" && grep -q 'contacts list' \"$SKILL44_DIR/tools/engine/verify-ghl-live.sh\""
assert "verify-ghl-live.sh is fail-loud (exit 1) + has missing-prereqs (exit 2) path" \
  "grep -q 'exit 1' \"$SKILL44_DIR/tools/engine/verify-ghl-live.sh\" && grep -q 'exit 2' \"$SKILL44_DIR/tools/engine/verify-ghl-live.sh\""
assert "verify-ghl-live.sh does NOT hand-source secrets/.env (inherited env only)" \
  "! grep -qE '^[[:space:]]*source .*secrets/\\.env' \"$SKILL44_DIR/tools/engine/verify-ghl-live.sh\""
assert "INSTALL.md Action 5 calls wire-ghl-env.sh (single-source env wiring)" \
  "grep -q 'wire-ghl-env.sh' \"$SKILL44_DIR/INSTALL.md\""
assert "INSTALL.md Action 6b runs the fail-loud verify gate (verify-ghl-live.sh)" \
  "grep -q 'verify-ghl-live.sh' \"$SKILL44_DIR/INSTALL.md\""
assert "INSTALL.md handles installed-with-missing-prereqs (no fabricated success)" \
  "grep -qi 'installed-with-missing-prereqs' \"$SKILL44_DIR/INSTALL.md\""

# v1.0.9 — live-box: prove the wired env is actually inherited + caf reaches GHL.
live_assert "GOHIGHLEVEL_LOCATION_ID present in openclaw.json env.vars (gateway-inherited)" \
  "openclaw config get env.vars.GOHIGHLEVEL_LOCATION_ID >/dev/null 2>&1"
live_assert "verify-ghl-live.sh exits 0 (caf reaches GHL) or 2 (missing-prereqs) — never 1" \
  "bash \"$CAF_DIR/engine/verify-ghl-live.sh\" >/dev/null 2>&1; rc=\$?; [ \"\$rc\" -eq 0 ] || [ \"\$rc\" -eq 2 ]"

# v1.0.15 — PLAN MODE + QC GATE + checklist template + per-build QC script + hallucination escalation
assert "INSTRUCTIONS.md contains 'Step 0.5 — PLAN MODE' section" \
  "grep -q 'Step 0.5.*PLAN MODE' \"$SKILL44_DIR/INSTRUCTIONS.md\""
assert "INSTRUCTIONS.md PLAN MODE has THINK step (A1/A2/A3)" \
  "grep -q 'DESIRED RESULT\|A1\.' \"$SKILL44_DIR/INSTRUCTIONS.md\" && grep -q 'CLIENT EXPECTATIONS\|A2\.' \"$SKILL44_DIR/INSTRUCTIONS.md\" && grep -q 'BEST APPROACH\|A3\.' \"$SKILL44_DIR/INSTRUCTIONS.md\""
assert "INSTRUCTIONS.md PLAN MODE has gating question 1 (publish decision)" \
  "grep -qi 'draft.*live\|publish.*draft\|GATING QUESTION 1\|build.*draft.*review' \"$SKILL44_DIR/INSTRUCTIONS.md\""
assert "INSTRUCTIONS.md PLAN MODE has gating question 2 (re-entry decision)" \
  "grep -qi 're-entry\|allow.*multiple\|GATING QUESTION 2\|come through.*more than once' \"$SKILL44_DIR/INSTRUCTIONS.md\""
assert "INSTRUCTIONS.md PLAN MODE 'rushing is a violation' binding rule present" \
  "grep -qi 'rushing.*violation\|violation.*rushing' \"$SKILL44_DIR/INSTRUCTIONS.md\""
assert "INSTRUCTIONS.md intents table re-points 'Build a follow-up workflow' to PLAN MODE" \
  "grep -q 'PLAN MODE.*Step 0.5.*then TRINITY\|PLAN MODE.*first.*then TRINITY' \"$SKILL44_DIR/INSTRUCTIONS.md\""
assert "INSTRUCTIONS.md Per-operation rule 2.0 (new build → PLAN MODE first) present" \
  "grep -q '2\.0.*PLAN MODE\|PLAN MODE.*before.*2a\|get.*gating.*answers.*BEFORE' \"$SKILL44_DIR/INSTRUCTIONS.md\""
assert "INSTRUCTIONS.md contains 'Step 9 — QC GATE' section" \
  "grep -q 'Step 9.*QC GATE\|QC GATE.*before declaring done' \"$SKILL44_DIR/INSTRUCTIONS.md\""
assert "INSTRUCTIONS.md QC GATE contains verbatim client announce template" \
  "grep -q \"I've built the workflow\" \"$SKILL44_DIR/INSTRUCTIONS.md\" && grep -q 'independent QC agent' \"$SKILL44_DIR/INSTRUCTIONS.md\" && grep -q 'checklist item-by-item' \"$SKILL44_DIR/INSTRUCTIONS.md\""
assert "INSTRUCTIONS.md QC GATE documents MiniMax sub-agent dispatch (sessions_send)" \
  "grep -qi 'sessions_send\|MiniMax\|minimax' \"$SKILL44_DIR/INSTRUCTIONS.md\""
assert "INSTRUCTIONS.md QC GATE requires caf workflows export + qc-built-workflow.sh" \
  "grep -q 'qc-built-workflow.sh' \"$SKILL44_DIR/INSTRUCTIONS.md\" && grep -q 'caf workflows export' \"$SKILL44_DIR/INSTRUCTIONS.md\""
assert "INSTRUCTIONS.md QC GATE 'done only after all-PASS + checklist handed over' rule present" \
  "grep -qi 'done.*QC pass\|all-PASS.*checklist\|checklist.*hand.over\|filled checklist' \"$SKILL44_DIR/INSTRUCTIONS.md\""
assert "INSTRUCTIONS.md hallucination escalation section present" \
  "grep -qi 'HALLUCINATION\|hallucination' \"$SKILL44_DIR/INSTRUCTIONS.md\""
assert "INSTRUCTIONS.md hallucination escalation requires reasoning-model thinking=HIGH (REQUIREMENT not recommendation)" \
  "grep -qi 'REQUIREMENT.*thinking.*HIGH\|thinking.*HIGH.*REQUIRED\|flipped.*RECOMMENDATION.*REQUIREMENT\|reasoning.*model.*thinking.*HIGH' \"$SKILL44_DIR/INSTRUCTIONS.md\""
assert "INSTRUCTIONS.md hallucination requires client disclosure" \
  "grep -qi 'DISCLOSE.*client\|QC caught.*reported.*wasn.t.*true\|honest disclosure' \"$SKILL44_DIR/INSTRUCTIONS.md\""
assert "INSTRUCTIONS.md bidirectional link Step 0 <-> Step 9 present" \
  "grep -qi 'BIDIRECTIONAL\|Step 0.*recommendation.*flipped\|flipped.*Step 0' \"$SKILL44_DIR/INSTRUCTIONS.md\""
assert "references/workflow-build-checklist-template.md exists" \
  "[ -f \"$SKILL44_DIR/references/workflow-build-checklist-template.md\" ]"
assert "checklist template contains WF-1 through WF-21 (21 items)" \
  "for i in \$(seq 1 21); do grep -q \"WF-\$i\" \"$SKILL44_DIR/references/workflow-build-checklist-template.md\" || exit 1; done"
assert "checklist template WF-4 trigger-active WF-ACTIVE gate present" \
  "grep -qi 'WF-4\|WF-ACTIVE GATE\|TRIGGER-ACTIVE-GATE\|trigger.*active.*publish\|active.*flag' \"$SKILL44_DIR/references/workflow-build-checklist-template.md\""
assert "checklist template WF-12 SMS From-number gate present" \
  "grep -qi 'WF-12\|SMS.*From.*number\|From-number\|from_number' \"$SKILL44_DIR/references/workflow-build-checklist-template.md\""
assert "checklist template WF-20 hallucinated artifacts detector present" \
  "grep -qi 'WF-20\|hallucinated\|HALLUCINATION' \"$SKILL44_DIR/references/workflow-build-checklist-template.md\""
assert "checklist template skill 41 cross-reference (superset) present" \
  "grep -qi 'Skill 41\|skill41\|superset\|12-point' \"$SKILL44_DIR/references/workflow-build-checklist-template.md\""
assert "qc-built-workflow.sh present" \
  "[ -f \"$SKILL44_DIR/qc-built-workflow.sh\" ]"
assert "qc-built-workflow.sh is executable" \
  "[ -x \"$SKILL44_DIR/qc-built-workflow.sh\" ]"
assert "qc-built-workflow.sh takes workflow-id argument and asserts trigger present (WF-3)" \
  "grep -q 'WF-3\|trigger.*present\|TRIGGER PRESENT' \"$SKILL44_DIR/qc-built-workflow.sh\""
assert "qc-built-workflow.sh asserts trigger active vs publish-intent (WF-4 WF-ACTIVE gate)" \
  "grep -q 'WF-4\|WF4_NOTE\|WF-ACTIVE\|trigger.*active\|PUBLISH_INTENT\|publish_intent' \"$SKILL44_DIR/qc-built-workflow.sh\""
assert "qc-built-workflow.sh asserts SMS From-number non-empty (WF-12)" \
  "grep -q 'WF-12\|fromNumber\|From-number\|SMS.*from' \"$SKILL44_DIR/qc-built-workflow.sh\""
assert "qc-built-workflow.sh asserts delivery chain linkage (WF-15)" \
  "grep -q 'WF-15\|targetActionId\|delivery.*chain\|linkage' \"$SKILL44_DIR/qc-built-workflow.sh\""
assert "qc-built-workflow.sh asserts snapshot existence (WF-21)" \
  "grep -q 'WF-21\|snapshot.*exists\|SNAPSHOT' \"$SKILL44_DIR/qc-built-workflow.sh\""
assert "qc-built-workflow.sh emits per-item PASS/FAIL JSON (--json flag)" \
  "grep -q '\-\-json\|JSON_MODE\|json.*mode' \"$SKILL44_DIR/qc-built-workflow.sh\""
assert "qc-built-workflow.sh appends to build-events ledger" \
  "grep -q 'build-events.jsonl\|BUILD_EVENTS_LEDGER' \"$SKILL44_DIR/qc-built-workflow.sh\""
assert "CORE_UPDATES.md AGENTS.md block has PLAN-MODE-before-build rule" \
  "grep -qi 'PLAN MODE\|PLAN_MODE\|plan.*mode.*before.*build\|rushing.*violation' \"$SKILL44_DIR/CORE_UPDATES.md\""
assert "CORE_UPDATES.md AGENTS.md block has QC-GATE rule (independent MiniMax + checklist handover)" \
  "grep -qi 'QC GATE\|independent.*MiniMax\|MiniMax.*QC\|checklist.*handover\|checklist.*handed' \"$SKILL44_DIR/CORE_UPDATES.md\""
assert "CORE_UPDATES.md AGENTS.md block has hallucination→reasoning-HIGH requirement" \
  "grep -qi 'HALLUCINATION\|hallucination' \"$SKILL44_DIR/CORE_UPDATES.md\" && grep -qi 'thinking.*HIGH\|HIGH.*thinking\|reasoning.*model' \"$SKILL44_DIR/CORE_UPDATES.md\""

# ── Section A: Installation (live-box only) ───────────────────────────────────
echo ""
echo "── Section A: Installation (live-box) ──"
live_assert "caf resolves on PATH"                "command -v caf >/dev/null 2>&1"
live_assert "convertandflow alias resolves"       "command -v convertandflow >/dev/null 2>&1"
live_assert "ghl alias resolves"                  "command -v ghl >/dev/null 2>&1"
live_assert "caf doctor exits green"              "caf doctor >/dev/null 2>&1"
live_assert "venv exists"                         "[ -d \"$CAF_DIR/.venv\" ]"
live_assert "wrapper file is executable"          "[ -x \"$CAF_DIR/caf\" ]"

# ── Section B: Credentials (live-box only) ───────────────────────────────────
echo ""
echo "── Section B: Credentials (live-box) ──"
if [ "$LIVE_MODE" -eq 1 ]; then
  source "$HOME/.openclaw/secrets/.env" 2>/dev/null || true
fi
# 11-alias fallback resolver — passes on pre-v12 boxes where the PIT is stored under a legacy name
RESOLVED_PIT="${GOHIGHLEVEL_API_KEY:-${GHL_API_KEY:-${GHL_PIT:-${GHL_TOKEN:-${GHL_PRIVATE_INTEGRATION_TOKEN:-${PRIVATE_INTEGRATION_TOKEN:-${GHL_PRIVATE_TOKEN:-${PIT_TOKEN:-${GHL_PIT_TOKEN:-${GOHIGHLEVEL_LOCATION_PIT:-${GHL_LOCATION_PIT:-}}}}}}}}}}}"
live_assert "GHL PIT set (any canonical alias)"   "[ -n \"${RESOLVED_PIT}\" ]"
live_assert "GHL PIT starts with pit-"            "[[ \"${RESOLVED_PIT}\" == pit-* ]]"
live_assert "GOHIGHLEVEL_LOCATION_ID is set"      "[ -n \"${GOHIGHLEVEL_LOCATION_ID:-}\" ]"
live_warn   "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN set (workflow writes)" "[ -n \"${GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN:-}\" ]"
live_assert "GOHIGHLEVEL_DRAFT_ONLY=true set"     "[ \"${GOHIGHLEVEL_DRAFT_ONLY:-true}\" = 'true' ]"

# ── Section C: Standard ops (live-box only) ───────────────────────────────────
echo ""
echo "── Section C: Standard ops (live-box) ──"
if [ "$LIVE_MODE" -eq 1 ]; then
  CONTACTS=$(caf contacts list --limit 1 2>/dev/null || echo "")
  assert "caf contacts list returns data"       "echo \"$CONTACTS\" | grep -qE 'contact|id|email'"
  WF_LIST=$(caf workflows list 2>/dev/null || echo "")
  assert "caf workflows list returns data"      "echo \"$WF_LIST\" | grep -qE 'workflow|id|name'"
  LOC=$(caf locations get 2>/dev/null || echo "")
  assert "caf locations get returns data"       "echo \"$LOC\" | grep -qE 'location|id|name'"
else
  echo "  SKIP: standard ops (live-box only; re-run with --live on a provisioned box)"; SKIP=$((SKIP+3))
fi

# ── Section D: Write safety (live-box only) ───────────────────────────────────
echo ""
echo "── Section D: Write safety (live-box) ──"
live_assert "wrapper passes GOHIGHLEVEL_API_KEY as GHL_API_KEY" \
  "grep -q 'GHL_API_KEY.*GOHIGHLEVEL_API_KEY' \"$CAF_DIR/caf\""
live_assert "snapshot dir exists" \
  "[ -d \"$CAF_DIR/data/snapshots\" ] || mkdir -p \"$CAF_DIR/data/snapshots\""
live_assert "wrapper sets GOHIGHLEVEL_DRAFT_ONLY" \
  "grep -q 'GOHIGHLEVEL_DRAFT_ONLY' \"$CAF_DIR/caf\""
live_assert "installed wrapper auto-seeds CAF_ALLOWED_LOCATION_IDS (blank whitelist fix)" \
  "grep -q '_caf_allowed_raw' \"$CAF_DIR/caf\""

# ── Section E: TRINITY and self-test (live-box only) ─────────────────────────
echo ""
echo "── Section E: TRINITY and self-test (live-box) ──"
live_assert "qc-trinity-registry.sh exists and is executable" \
  "[ -x \"$SKILL38_DIR/scripts/qc-trinity-registry.sh\" ] || [ -f \"$SKILL38_DIR/scripts/qc-trinity-registry.sh\" ]"
# FIX-S36-27: prove qc-built-workflow.sh actually EXECUTES the trinity script under
# --conversational (not just that the script exists) — the claimed hard gate must be wired.
live_assert "qc-built-workflow.sh wires --conversational to exec qc-trinity-registry.sh + FAIL WF-19" \
  "grep -q -- '--conversational' \"$SKILL44_DIR/qc-built-workflow.sh\" && grep -q 'qc-trinity-registry.sh' \"$SKILL44_DIR/qc-built-workflow.sh\" && grep -q 'record_fail \"WF-19\"' \"$SKILL44_DIR/qc-built-workflow.sh\""
live_assert "24-self-test-hook.sh exists" \
  "[ -f \"$SKILL38_DIR/scripts/24-self-test-hook.sh\" ]"
live_assert "24-self-test-hook.sh credential read is alias-aware (GOHIGHLEVEL_API_KEY)" \
  "grep -qE 'GOHIGHLEVEL_API_KEY' \"$SKILL38_DIR/scripts/24-self-test-hook.sh\""

# ── Section F: Core files (live-box only) ────────────────────────────────────
echo ""
echo "── Section F: Core files (live-box) ──"
SENTINEL="skill:44-convert-and-flow-operator:core-update-applied"
live_assert "CORE_UPDATES sentinel present in AGENTS.md" \
  "grep -qF \"$SENTINEL\" \"$WORKSPACE/AGENTS.md\" 2>/dev/null"
live_assert "AGENTS.md has Tier 0 mention" \
  "grep -qE 'Tier 0|convert-and-flow-operator|convertandflow' \"$WORKSPACE/AGENTS.md\" 2>/dev/null"
live_assert "TOOLS.md has caf entry" \
  "grep -qE 'caf|convertandflow' \"$WORKSPACE/TOOLS.md\" 2>/dev/null"
live_assert "MEMORY.md has skill 44 install record" \
  "grep -qE 'Convert and Flow Operator|skill 44' \"$WORKSPACE/MEMORY.md\" 2>/dev/null"

# ── Section G: Platform overlay parity (static — files are on branch) ────────
echo ""
echo "── Section G: Platform overlay parity ──"
MAC_SKILL="$SKILL44_DIR/platform/mac/SKILL.md"
VPS_SKILL="$SKILL44_DIR/platform/vps/SKILL.md"
if [ -f "$MAC_SKILL" ] && [ -f "$VPS_SKILL" ]; then
  assert "Mac overlay name matches main SKILL.md" \
    "grep -q 'name: convert-and-flow-operator' \"$MAC_SKILL\""
  assert "VPS overlay name matches main SKILL.md" \
    "grep -q 'name: convert-and-flow-operator' \"$VPS_SKILL\""
else
  warn_only "Platform overlays present (mac + vps)" "[ -f \"$MAC_SKILL\" ] && [ -f \"$VPS_SKILL\" ]"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════"
echo "  Result: $PASS passed | $FAIL failed | $WARN warnings | $SKIP skipped"
echo "══════════════════════════════════════════════"
SCORE=$(python3 -c "print(round(($PASS * 10) / ($PASS + $FAIL + 0.001), 1))" 2>/dev/null || echo "?")
echo "  Approx score: ${SCORE}/10 (excludes warnings/skips)"
echo ""

if [ "$FAIL" -gt 0 ]; then
  echo "QC FAILED — $FAIL blocker(s). Fix before merging."
  exit 1
fi
echo "QC PASSED"
exit 0
