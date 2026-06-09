#!/usr/bin/env bash
# apply-fleet-standards.sh — Idempotent enforcer for the OpenClaw fleet standard:
#   • Sub-agents fully permitted (spawn + exec + read/write across all agents)
#   • agents.defaults.tools.exec: security=full, ask=off (PR1: spawned sub-agents unlocked)
#   • Telegram media limit 50 MB (inbound + outbound)
#
# Why a script and not `openclaw config set`:
#   Per-agent overrides in agents.list[] override global defaults. The schema
#   validator (2026.5.20+) rejects deep nested keys via CLI. The supported
#   pattern is direct JSON merge against openclaw.json, then validate. This
#   script ships the canonical block verified on Sheila Reynolds' Mac (2026.5.28).
#
# Idempotent: re-running is a no-op if config already matches canonical block.
#
# Path detection:
#   - If /data/.openclaw/openclaw.json exists  → VPS container layout.
#   - Else                                     → $HOME/.openclaw/openclaw.json
#                                                (Mac mini layout).
#
# Verification (success criteria):
#   openclaw config validate must exit clean.
#
# Logs before/after state and reports idempotent status.

set -euo pipefail

# ─── Path detection ──────────────────────────────────────────────────────────
if [ -f /data/.openclaw/openclaw.json ]; then
  OC_ROOT="/data/.openclaw"
  OC_USER="node"
elif [ -f "$HOME/.openclaw/openclaw.json" ]; then
  OC_ROOT="$HOME/.openclaw"
  OC_USER="$(whoami)"
else
  echo "ERROR: cannot find openclaw.json in /data/.openclaw or $HOME/.openclaw" >&2
  exit 1
fi

OC_CONFIG="$OC_ROOT/openclaw.json"
TIMESTAMP=$(date +%Y%m%d%H%M%S)
OC_BACKUP="$OC_CONFIG.bak-fleet-$TIMESTAMP"

echo "[apply-fleet-standards] config: $OC_CONFIG"

# ─── 1. Backup the current config ────────────────────────────────────────────
cp "$OC_CONFIG" "$OC_BACKUP"
echo "[apply-fleet-standards] backed up to: $OC_BACKUP"

# ─── 2. Deep-merge the canonical fleet block into openclaw.json ──────────────
python3 - "$OC_CONFIG" <<'PYEOF'
import json
import sys
from pathlib import Path

cfg_path = Path(sys.argv[1])
cfg = json.loads(cfg_path.read_text())
before_json = json.dumps(cfg, sort_keys=True, indent=2)

# CANONICAL FLEET STANDARD BLOCK
# Verified against:
#   - docs.openclaw.ai/tools/subagents (allowAgents wildcard, per-agent override)
#   - docs.openclaw.ai/gateway/security (exec.security, exec.ask, sandbox)
#   - docs.openclaw.ai/tools/multi-agent-sandbox-tools (agent-specific policy)
#   - Live test on OpenClaw 2026.5.28 (Sheila Reynolds' Mac mini, session logs)
#   - PR1 (2026-06-09): agents.defaults.tools.exec added so SPAWNED sub-agents
#     also inherit full execution policy (without this the platform default
#     narrows spawned sub-agents to a minimal read-only tool set).
#
# Key insight: per-agent settings override global defaults. So we must:
#   1. Set the global default to ["*"]
#   2. Iterate all agents and set their explicit allowAgents to ["*"] OR
#      delete their per-agent allowAgents so they inherit the global default.
#   3. Set agents.defaults.tools.exec so ALL spawned sub-agents run at full exec.

CANONICAL = {
    "tools": {
        "exec": {
            "security": "full",
            "ask": "off"
        }
    },
    "agents": {
        "defaults": {
            "tools": {
                "exec": {
                    "security": "full",
                    "ask": "off"
                }
            },
            "subagents": {
                "allowAgents": ["*"],
                "requireAgentId": False
            }
        }
    },
    "channels": {
        "telegram": {
            "mediaMaxMb": 50
        }
    }
}

def deep_merge(dst, src):
    """Recursively merge src into dst, returning dst."""
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst

# Apply the canonical block.
deep_merge(cfg, CANONICAL)

# Fix per-agent subagents overrides: any agent with an explicit allowAgents
# that is NOT ["*"] should be set to ["*"]. This is the critical piece that
# was missing in earlier partial fixes.
if "agents" in cfg and "list" in cfg["agents"]:
    for agent in cfg["agents"]["list"]:
        if "subagents" in agent and "allowAgents" in agent["subagents"]:
            if agent["subagents"]["allowAgents"] != ["*"]:
                agent_name = agent.get("name", "unknown")
                print(f"[apply-fleet-standards] fixing agent '{agent_name}' allowAgents → ['*']")
                agent["subagents"]["allowAgents"] = ["*"]

after_json = json.dumps(cfg, sort_keys=True, indent=2)

if before_json == after_json:
    print("[apply-fleet-standards] config already canonical — no-op")
else:
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n")
    print("[apply-fleet-standards] config merged → " + str(cfg_path))

# Print before/after for audit.
print("\n[apply-fleet-standards] BEFORE (canonical block only):")
canonical_before = {k: v for k, v in json.loads(before_json).items()
                    if k in CANONICAL}
print(json.dumps(canonical_before, indent=2))

print("\n[apply-fleet-standards] AFTER (canonical block only):")
canonical_after = {k: v for k, v in json.loads(after_json).items()
                   if k in CANONICAL}
print(json.dumps(canonical_after, indent=2))

PYEOF

# ─── 3. Chown back to the OpenClaw runtime user (VPS container only) ─────────
if [ "$OC_ROOT" = "/data/.openclaw" ]; then
  chown "$OC_USER:$OC_USER" "$OC_CONFIG" 2>/dev/null || true
fi

# ─── 4. Validate + report ────────────────────────────────────────────────────
echo ""
echo "[apply-fleet-standards] running: openclaw config validate"
if ! openclaw config validate; then
  echo "ERROR: openclaw config validate failed — see output above" >&2
  echo "[apply-fleet-standards] rolling back to: $OC_BACKUP"
  cp "$OC_BACKUP" "$OC_CONFIG"
  exit 1
fi

echo ""
echo "[apply-fleet-standards] config standards applied"

# ─── 5a. Inject ROLE DISCIPLINE into the agent's active AGENTS.md (PR2) ────────
# This is the role-scoped governance block from CANONICAL-ORCHESTRATOR-RULE.md.
# It is injected at the TOP of AGENTS.md (before existing content) so every
# agent — CEO and specialists alike — sees the role mandate on first read.
# Idempotent: guarded by <!-- ROLE_DISCIPLINE_V1 --> marker.
#
# Workspace resolution mirrors section 5 below.

WORKSPACE_DIR=""
if [ -f "$OC_CONFIG" ]; then
  WORKSPACE_DIR=$(OC_JSON="$OC_CONFIG" python3 -c "
import json, os
try:
    cfg = json.load(open(os.environ['OC_JSON']))
    for ag in cfg.get('agents', {}).get('list', []) or []:
        if isinstance(ag, dict) and ag.get('id') == 'main':
            ws = ag.get('workspace')
            if ws:
                print(os.path.expanduser(ws)); break
except Exception:
    pass
" 2>/dev/null) || WORKSPACE_DIR=""
fi
if [ -z "$WORKSPACE_DIR" ] && command -v openclaw >/dev/null 2>&1; then
  WORKSPACE_DIR=$(openclaw config get agents.defaults.workspace 2>/dev/null \
    | head -1 | python3 -c "
import sys, json, os
try:
    raw = sys.stdin.read().strip()
    print(os.path.expanduser(json.loads(raw) if raw.startswith('\"') else raw))
except Exception:
    pass
" 2>/dev/null) || WORKSPACE_DIR=""
fi
WORKSPACE_DIR="${WORKSPACE_DIR:-$OC_ROOT/workspace}"
if [ ! -d "$WORKSPACE_DIR" ]; then
  WORKSPACE_DIR="$OC_ROOT/workspace"
fi
mkdir -p "$WORKSPACE_DIR"
AGENTS_FILE_EARLY="$WORKSPACE_DIR/AGENTS.md"
touch "$AGENTS_FILE_EARLY"

ROLE_DISC_MARKER="<!-- ROLE_DISCIPLINE_V1 -->"
if grep -qF "$ROLE_DISC_MARKER" "$AGENTS_FILE_EARLY"; then
  echo "[apply-fleet-standards] ROLE DISCIPLINE already present in $AGENTS_FILE_EARLY — no-op"
else
  echo "[apply-fleet-standards] injecting ROLE DISCIPLINE at top of $AGENTS_FILE_EARLY"
  ORIGINAL_CONTENT=$(cat "$AGENTS_FILE_EARLY")
  cat > "$AGENTS_FILE_EARLY" <<'RDEOF'
<!-- ROLE_DISCIPLINE_V1 -->
## ROLE DISCIPLINE (non-negotiable — every agent, every level)

No agent decides what it will or will not do.

- The **CEO / master-orchestrator** is a ROUTER: it routes every task to a department by posting
  to `/api/tasks/ingest` with `department_slug`; it does not execute work, pick specialists,
  or commandeer sub-agents to keep control. Before doing any task itself it must seek and
  receive explicit owner permission — routing is always allowed without permission.
- A **department specialist** EXECUTES the task assigned to it against its SOP — including
  generating graphics/video via KIE.ai / Fal.ai — and does not refuse, redefine, or bounce
  its assigned role.
- An agent that overrides its defined role gets flagged. Persistent non-compliance (>20 flags)
  = the agent is reset (identity + soul deleted and rebuilt fresh).

This rule is role-scoped so it reinforces the CEO routing mandate WITHOUT gagging executing
specialists. Both behaviors — the CEO routing and specialists executing — are equally required.

---

RDEOF
  printf '%s' "$ORIGINAL_CONTENT" >> "$AGENTS_FILE_EARLY"
  echo "[apply-fleet-standards] ROLE DISCIPLINE injected at top of $AGENTS_FILE_EARLY"
fi

if [ "$OC_ROOT" = "/data/.openclaw" ]; then
  chown "$OC_USER:$OC_USER" "$AGENTS_FILE_EARLY" 2>/dev/null || true
fi

# ─── 5. Append BIG PROJECT MODE standard to the agent's active AGENTS.md ──────
# Universal operating standard (see BIG-PROJECT-MODE.md at repo root). This is
# appended to the SAME active-workspace AGENTS.md that install.sh / update-skills
# target — not a per-role copy.
#
# IDEMPOTENCY (v2): the block is versioned via the heading
#   "## BIG PROJECT MODE (v2)"
# If the file contains ONLY the old v1 heading ("## BIG PROJECT MODE" without
# "(v2)"), the v1 block is replaced in-place with the v2 block.
# If v2 is already present, the run is a no-op.
# This ensures existing clients who received the v1 block get the updated
# Rule 0 (ECHO-BACK GATE) on the next apply-fleet-standards run.
#
# Workspace resolution mirrors install.sh Step 10 exactly:
#   1. agents.list[main].workspace (per-agent override — wins if set)
#   2. agents.defaults.workspace via `openclaw config get`
#   3. $OC_ROOT/workspace (canonical OpenClaw default — Mac or VPS)
# Clawd is dead; ~/clawd is never a fallback.

WORKSPACE_DIR=""

# Step 1: per-agent workspace override on the "main" agent
WORKSPACE_DIR=$(OC_JSON="$OC_CONFIG" python3 -c "
import json, os
try:
    cfg = json.load(open(os.environ['OC_JSON']))
    for ag in cfg.get('agents', {}).get('list', []) or []:
        if isinstance(ag, dict) and ag.get('id') == 'main':
            ws = ag.get('workspace')
            if ws:
                print(os.path.expanduser(ws)); break
except Exception:
    pass
" 2>/dev/null) || WORKSPACE_DIR=""

# Step 2: agents.defaults.workspace via CLI (non-zero exit on unset key must not
# abort under set -e — wrap with || WORKSPACE_DIR="")
if [ -z "$WORKSPACE_DIR" ] && command -v openclaw >/dev/null 2>&1; then
  WORKSPACE_DIR=$(openclaw config get agents.defaults.workspace 2>/dev/null \
    | head -1 | python3 -c "
import sys, json, os
try:
    raw = sys.stdin.read().strip()
    print(os.path.expanduser(json.loads(raw) if raw.startswith('\"') else raw))
except Exception:
    pass
" 2>/dev/null) || WORKSPACE_DIR=""
fi

# Step 3: canonical default for this layout ($OC_ROOT is /data/.openclaw on VPS
# or $HOME/.openclaw on Mac — both detected at the top of this script).
WORKSPACE_DIR="${WORKSPACE_DIR:-$OC_ROOT/workspace}"
if [ ! -d "$WORKSPACE_DIR" ]; then
  WORKSPACE_DIR="$OC_ROOT/workspace"
fi

mkdir -p "$WORKSPACE_DIR"
AGENTS_FILE="$WORKSPACE_DIR/AGENTS.md"
touch "$AGENTS_FILE"

BPM_V2_HEADING="## BIG PROJECT MODE (v2)"
BPM_V1_HEADING="## BIG PROJECT MODE"

if grep -qF "$BPM_V2_HEADING" "$AGENTS_FILE"; then
  echo "[apply-fleet-standards] BIG PROJECT MODE (v2) already present in $AGENTS_FILE — no-op"
elif grep -qF "$BPM_V1_HEADING" "$AGENTS_FILE"; then
  # Upgrade v1 block to v2: strip everything from the v1 heading to end-of-file,
  # then append the v2 block. (v1 heading is always last — appended at end.)
  echo "[apply-fleet-standards] upgrading BIG PROJECT MODE v1 → v2 in $AGENTS_FILE"
  # Find line number of v1 heading and truncate file there (keep content before it).
  V1_LINE=$(grep -n "^## BIG PROJECT MODE$" "$AGENTS_FILE" | tail -1 | cut -d: -f1)
  if [ -n "$V1_LINE" ]; then
    # Keep lines BEFORE the v1 heading (trim the blank line before it too).
    head -n "$((V1_LINE - 2))" "$AGENTS_FILE" > "${AGENTS_FILE}.v2tmp"
    mv "${AGENTS_FILE}.v2tmp" "$AGENTS_FILE"
  fi
  cat >> "$AGENTS_FILE" <<'BPMEOF'

## BIG PROJECT MODE (v2)

**Trigger:** the owner says "big project mode" or hands you a large, multi-part
build/document with many deliverables. On per-token caching models (DeepSeek
direct ~1/120th on cache hits; Anthropic; OpenAI) this cuts input cost 80-95%;
on flat-rate routes (Ollama Cloud) it is still faster with fewer timeouts and
cleaner QC. It is never wrong to use it.

0. **ECHO-BACK GATE (always first).** Before spawning ANYTHING, reply to the
   owner with: every rule restated in your own words (one line each) + the full
   work-slice list + the EXACT model strings you will use for writers and QC.
   Wait for GO. If you think a different model/route/approach would be better —
   you don't decide that. Ask.
1. **Orchestrator pastes; owners send files.** The owner sends the project
   document as a file. Read it ONCE and embed the FULL TEXT, word-for-word, at
   the TOP of every worker's birth instructions. Never tell workers to "read the
   file" (that is one full-price read PER agent instead of per fleet).
2. **Identical bytes first, unique assignment last.** Every spawn = [shared
   document, byte-identical] + [that worker's assignment at the very bottom].
   Never paraphrase the shared block; never put the assignment first. One changed
   character at the front re-prices everything behind it.
3. **Warm-up then fleet.** Spawn ONE worker, let it finish (warms the cache),
   then launch the rest in batches.
4. **Workers live short.** End every assignment with: "everything you need is
   above — do not read other files; write your deliverable, save it, return a
   one-line status." Foraging workers cost 20-50x.
5. **Skinny orchestrator.** Track progress in a LEDGER FILE on disk;
   deliverables go to disk; only one-line statuses flow through the orchestrator
   conversation. Nothing bulky ever lives in the transcript.
6. **Independent QC, real scores.** QC runs on a DIFFERENT model than the
   writers, scores 0-10 against a rubric, gates >= 8.5, defect-loops on fails
   (max 3); numeric scores recorded — never free-text "PASS" stamps.
7. **No worker dies silently.** Ledger + watchdog; restart once -> fresh worker
   -> flag. The completion gate counts delivered files, not hopes.
8. **Tokens only** in any template/master content — never real owner/client data
   the agent happens to know.

**Verify caching worked:** on DeepSeek direct the usage fields
`prompt_cache_hit_tokens` / `prompt_cache_miss_tokens` — after the warm-up
worker, hits should cover the shared document.

Full reference: `BIG-PROJECT-MODE.md` in the onboarding repo.
BPMEOF
  echo "[apply-fleet-standards] BIG PROJECT MODE (v2) written to $AGENTS_FILE"
else
  cat >> "$AGENTS_FILE" <<'BPMEOF'

## BIG PROJECT MODE (v2)

**Trigger:** the owner says "big project mode" or hands you a large, multi-part
build/document with many deliverables. On per-token caching models (DeepSeek
direct ~1/120th on cache hits; Anthropic; OpenAI) this cuts input cost 80-95%;
on flat-rate routes (Ollama Cloud) it is still faster with fewer timeouts and
cleaner QC. It is never wrong to use it.

0. **ECHO-BACK GATE (always first).** Before spawning ANYTHING, reply to the
   owner with: every rule restated in your own words (one line each) + the full
   work-slice list + the EXACT model strings you will use for writers and QC.
   Wait for GO. If you think a different model/route/approach would be better —
   you don't decide that. Ask.
1. **Orchestrator pastes; owners send files.** The owner sends the project
   document as a file. Read it ONCE and embed the FULL TEXT, word-for-word, at
   the TOP of every worker's birth instructions. Never tell workers to "read the
   file" (that is one full-price read PER agent instead of per fleet).
2. **Identical bytes first, unique assignment last.** Every spawn = [shared
   document, byte-identical] + [that worker's assignment at the very bottom].
   Never paraphrase the shared block; never put the assignment first. One changed
   character at the front re-prices everything behind it.
3. **Warm-up then fleet.** Spawn ONE worker, let it finish (warms the cache),
   then launch the rest in batches.
4. **Workers live short.** End every assignment with: "everything you need is
   above — do not read other files; write your deliverable, save it, return a
   one-line status." Foraging workers cost 20-50x.
5. **Skinny orchestrator.** Track progress in a LEDGER FILE on disk;
   deliverables go to disk; only one-line statuses flow through the orchestrator
   conversation. Nothing bulky ever lives in the transcript.
6. **Independent QC, real scores.** QC runs on a DIFFERENT model than the
   writers, scores 0-10 against a rubric, gates >= 8.5, defect-loops on fails
   (max 3); numeric scores recorded — never free-text "PASS" stamps.
7. **No worker dies silently.** Ledger + watchdog; restart once -> fresh worker
   -> flag. The completion gate counts delivered files, not hopes.
8. **Tokens only** in any template/master content — never real owner/client data
   the agent happens to know.

**Verify caching worked:** on DeepSeek direct the usage fields
`prompt_cache_hit_tokens` / `prompt_cache_miss_tokens` — after the warm-up
worker, hits should cover the shared document.

Full reference: `BIG-PROJECT-MODE.md` in the onboarding repo.
BPMEOF
  echo "[apply-fleet-standards] BIG PROJECT MODE (v2) appended to $AGENTS_FILE"
fi

# Chown AGENTS.md back to the runtime user on VPS container layout.
if [ "$OC_ROOT" = "/data/.openclaw" ]; then
  chown "$OC_USER:$OC_USER" "$AGENTS_FILE" 2>/dev/null || true
fi

echo ""
echo "[apply-fleet-standards] DONE"
echo "[apply-fleet-standards] Backup: $OC_BACKUP"
echo "[apply-fleet-standards] Current: $OC_CONFIG"
echo "[apply-fleet-standards] AGENTS.md: $AGENTS_FILE"
