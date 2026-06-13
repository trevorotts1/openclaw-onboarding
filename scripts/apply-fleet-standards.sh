#!/usr/bin/env bash
# apply-fleet-standards.sh — Idempotent enforcer for the OpenClaw fleet standard:
#   • Sub-agents fully permitted (spawn + exec + read/write across all agents)
#   • tools.exec: security=full, ask=off (TOP-LEVEL only — valid on 2026.6.1+)
#   • Telegram media limit 50 MB (inbound + outbound)
#
# NOTE (v11.3.1): agents.defaults.tools.exec is INVALID on OpenClaw 2026.6.1+
#   and causes "agents.defaults: Invalid input" / auto-revert by doctor --fix.
#   Only the top-level tools.exec is valid. Generation depts get per-agent
#   tools.allow set by build-workforce.py, not by this canonical block.
#
# Why a script and not `openclaw config set`:
#   Per-agent overrides in agents.list[] override global defaults. The schema
#   validator (2026.5.20+) rejects deep nested keys via CLI. The supported
#   pattern is direct JSON merge against openclaw.json, then validate. This
#   script ships the canonical block verified on Sheila Reynolds' Mac (2026.6.1).
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
#   - Live test on OpenClaw 2026.6.1 (Sheila Reynolds' Mac mini, v11.3.1 fix)
#
# v11.3.1 FIX: agents.defaults.tools.exec is REMOVED from this block.
#   On OpenClaw 2026.6.1 the schema validator rejects it with
#   "agents.defaults: Invalid input" and openclaw doctor --fix auto-reverts it.
#   The exec policy lives at TOP-LEVEL tools.exec only.
#   Generation departments get per-agent tools.allow via build-workforce.py.
#
# Key insight: per-agent settings override global defaults. So we must:
#   1. Set top-level tools.exec for the gateway-wide exec policy.
#   2. Set agents.defaults.subagents.allowAgents to ["*"] for full spawn perm.
#   3. Iterate all agents and set their explicit allowAgents to ["*"] OR
#      delete their per-agent allowAgents so they inherit the global default.

CANONICAL = {
    "tools": {
        "exec": {
            "security": "full",
            "ask": "off"
        }
    },
    "agents": {
        "defaults": {
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
# PRD 1.11: Workspace resolution delegates to resolve_injected_core_files()
# (shared-utils/) when available — that is the SINGLE canonical implementation.
# The inline 3-step fallback is kept for early-boot/install-time compatibility.

_resolve_workspace_via_shared_helper() {
  # Try the shared Python helper first (PRD 1.11 single-source-of-truth).
  local SCRIPT_DIR
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  local SHARED_UTILS="$SCRIPT_DIR/../shared-utils"
  local HELPER="$SHARED_UTILS/resolve_injected_core_files.py"
  if [ -f "$HELPER" ]; then
    OC_JSON="${OC_CONFIG:-}" python3 -c "
import sys, os
sys.path.insert(0, '$SHARED_UTILS')
from resolve_injected_core_files import resolve_injected_core_files
r = resolve_injected_core_files('main')
print(r['workspace'])
" 2>/dev/null && return 0
  fi
  return 1
}

WORKSPACE_DIR=""
WORKSPACE_DIR=$(_resolve_workspace_via_shared_helper 2>/dev/null) || WORKSPACE_DIR=""

if [ -z "$WORKSPACE_DIR" ] && [ -f "$OC_CONFIG" ]; then
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

# ─── 4b. Inject CEO ROUTING — NO LOOPHOLES block into AGENTS.md ──────────────
# v11.3.2: closes the "trivial task / quick API call / spawn-a-sub-agent" loopholes
# that let the CEO self-execute even when the PRIME DIRECTIVE partially loaded.
# Injected after ROLE_DISCIPLINE (or at top when ROLE_DISCIPLINE already present).
# Idempotent: guarded by <!-- CEO_ROUTING_NO_LOOPHOLES_V1 --> marker.
CEO_ROUTING_MARKER="<!-- CEO_ROUTING_NO_LOOPHOLES_V1 -->"
if grep -qF "$CEO_ROUTING_MARKER" "$AGENTS_FILE_EARLY"; then
  echo "[apply-fleet-standards] CEO ROUTING NO LOOPHOLES already present in $AGENTS_FILE_EARLY — no-op"
else
  echo "[apply-fleet-standards] injecting CEO ROUTING NO LOOPHOLES into $AGENTS_FILE_EARLY"
  # Insert after the ROLE_DISCIPLINE block (after the first --- separator that
  # follows the ROLE_DISCIPLINE marker). Use awk to inject after first --- post-marker.
  TMPF=$(mktemp)
  awk -v marker="$ROLE_DISC_MARKER" '
    BEGIN { injected=0; in_rd=0 }
    {
      print
      if (!injected && index($0, marker)) { in_rd=1 }
      if (in_rd && !injected && /^---[[:space:]]*$/) {
        print ""
        print "<!-- CEO_ROUTING_NO_LOOPHOLES_V1 -->"
        print "## ⛔ CEO ROUTING — NO LOOPHOLES (v11.3.2 — closes all self-execution escape hatches)"
        print ""
        print "The CEO / master-orchestrator'\''s ONLY permitted routing action is:"
        print ""
        print "  **POST \`/api/tasks/ingest\` with \`department_slug: \"<slug>\"\`**"
        print ""
        print "This places the task on the department'\''s Kanban board. The DEPARTMENT assigns the specialist"
        print "and the persona. The doing belongs to the department — never to the CEO."
        print ""
        print "### Closed loopholes (these are ALL violations, no exceptions):"
        print ""
        print "| Loophole | Status |"
        print "|----------|--------|"
        print "| \"This task is trivial / simple / quick — I'\''ll just do it myself\" | ❌ VIOLATION |"
        print "| \"I know how to make this API call, I'\''ll handle it directly\" | ❌ VIOLATION |"
        print "| \"I'\''ll spawn a sub-agent and have it execute the work for me\" | ❌ VIOLATION — spawning a sub-agent to do production work IS the same as self-executing |"
        print "| \"I'\''m telling the sub-agent to call KIE.ai / Fal.ai for me\" | ❌ VIOLATION — same as above |"
        print "| \"I don'\''t know which department, so I'\''ll do it myself\" | ❌ VIOLATION — route to \`department_slug: \"general-task\"\` |"
        print "| \"The owner seemed to want a quick answer\" | ❌ VIOLATION — route and let the department respond |"
        print ""
        print "### What the CEO MAY do (exhaustive list):"
        print "- Have conversations with the owner"
        print "- POST to \`/api/tasks/ingest\` to route tasks"
        print "- Send Telegram messages"
        print "- Read workspace files"
        print "- Restart the gateway (orchestrator-only authority, N7)"
        print "- Manage agent/department config"
        print ""
        print "### Sub-agent bypass clause"
        print "Spawning a sub-agent and instructing it to execute production work IS THE SAME VIOLATION as"
        print "self-executing. If a sub-agent is spawned, it MUST read its own role files and operate via"
        print "the task board — it is NOT a production tool for the orchestrator."
        print ""
        print "### Owner-permission exception"
        print "Before the CEO would EVER do a task itself, it must FIRST seek AND RECEIVE explicit permission"
        print "and consent from the owner. Seeking permission alone is not enough — explicit consent must be"
        print "received. Without that explicit consent, the CEO routes — always."
        print ""
        print "---"
        print ""
        injected=1
      }
    }
  ' "$AGENTS_FILE_EARLY" > "$TMPF"
  # If ROLE_DISCIPLINE marker wasn't found (older box), just prepend at top
  if ! grep -qF "$CEO_ROUTING_MARKER" "$TMPF"; then
    ORIG2=$(cat "$AGENTS_FILE_EARLY")
    {
      printf '<!-- CEO_ROUTING_NO_LOOPHOLES_V1 -->\n'
      printf '## ⛔ CEO ROUTING — NO LOOPHOLES (v11.3.2 — closes all self-execution escape hatches)\n\n'
      printf 'The CEO'\''s ONLY permitted routing action: POST /api/tasks/ingest with department_slug.\n'
      printf 'No trivial-task, quick-API-call, or spawn-sub-agent exceptions. See AGENTS.md for full rule.\n\n'
      printf '---\n\n'
      printf '%s' "$ORIG2"
    } > "$TMPF"
  fi
  mv "$TMPF" "$AGENTS_FILE_EARLY"
  echo "[apply-fleet-standards] CEO ROUTING NO LOOPHOLES injected into $AGENTS_FILE_EARLY"
fi

if [ "$OC_ROOT" = "/data/.openclaw" ]; then
  chown "$OC_USER:$OC_USER" "$AGENTS_FILE_EARLY" 2>/dev/null || true
fi

# ─── 4c. Inject CREDENTIAL_CHECK_V2 (N33 + N34) into AGENTS.md ──────────────
# Idempotent: guarded by <!-- CREDENTIAL_CHECK_V2 --> marker.
# Upgrade path: if a box carries V1, strip it and inject V2 in its place.
# This is idempotent: re-running on a V2 box is a no-op.
CRED_CHECK_V2_MARKER="<!-- CREDENTIAL_CHECK_V2 -->"
CRED_CHECK_V1_MARKER="<!-- CREDENTIAL_CHECK_V1 -->"

if grep -qF "$CRED_CHECK_V2_MARKER" "$AGENTS_FILE_EARLY"; then
  echo "[apply-fleet-standards] CREDENTIAL_CHECK_V2 already present in $AGENTS_FILE_EARLY — no-op"
else
  echo "[apply-fleet-standards] injecting CREDENTIAL_CHECK_V2 (N33+N34) into $AGENTS_FILE_EARLY"
  # Remove any V1 block if present (strip from V1 marker to the next top-level ---\n heading)
  TMPF2="$(mktemp)"
  python3 - "$AGENTS_FILE_EARLY" <<'CCPYEOF'
import sys, re

path = sys.argv[1]
content = open(path).read()

# Strip V1 block if present: from <!-- CREDENTIAL_CHECK_V1 --> to next top-level ---
v1_pattern = re.compile(
    r'<!-- CREDENTIAL_CHECK_V1 -->.*?(?=\n---\n(?:\n|##|\Z))',
    re.DOTALL
)
content = v1_pattern.sub('', content)

open(path, 'w').write(content)
CCPYEOF
  # Append V2 block at end (before any trailing learned-lessons section if present)
  cat >> "$AGENTS_FILE_EARLY" <<'CCEOF'

<!-- CREDENTIAL_CHECK_V2 -->
## 🔴 N33 — Credential Check Protocol (never falsely report a key missing)

> Idempotency marker: `CREDENTIAL_CHECK_V2`. `apply-fleet-standards.sh` injects this on
> existing boxes. Do NOT add it again if the marker is already present.
> Boxes carrying `CREDENTIAL_CHECK_V1` are automatically upgraded to V2 on next run.

A credential that exists in the live process env but is absent from a flat file is **PRESENT**.
An agent that reports "missing" without the evidence triad below has made a false claim.

### The Evidence Triad (required before "missing")

Before reporting any key as absent, you MUST have completed all three steps:

1. **Live process env** — checked via `docker exec <container> printenv` (VPS) or `ps eww <gw-pid>` (Mac).
2. **MCP server headers** — checked `openclaw.json mcp.servers.<svc>.headers` + `.env`.
3. **All .env stores** — checked every store listed in the "checked" output of `check-credential.sh`.

Only after all three return empty may you say a key is **GENUINELY-ABSENT**.

Use the canonical helper:
```
~/.openclaw/skills/shared-utils/check-credential.sh <KEY_NAME>
~/.openclaw/skills/shared-utils/check-credential.sh --provider <PROVIDER_NAME> --json
```

<!-- N34 -->
## 🔴 N34 — Provider Detection Protocol (a missing config block is NEVER proof a provider is absent)

"Does box X have provider Y" = **can the gateway resolve Y's API key at runtime** — NOT "is there a `models.providers.<Y>` block."

Run `check-credential.sh --provider <Y>` (live process env FIRST). Three verdicts:

| Verdict | Exit | Action |
|---|---|---|
| `PRESENT_WITH_BLOCK` | 0 | Key live + block references it — update block |
| `NEEDS_BLOCK` | 3 | Key live, no block — HAS the provider, CREATE the block |
| `GENUINELY-ABSENT` | 1 | Only after live-env tier + all stores empty — then skip |

**Hard violations:** emitting absent/no-provider from a config-block check alone; writing `had_X: false` for a check that never ran (use `NOT_ASSESSED`). Sonnet only — never Haiku for credential checks.

Block-name matching is on the **referenced apiKey**, not the block name (`openrouter-grok` with `apiKey: $OPENROUTER_API_KEY` IS the openrouter provider).

Root cause: 2026-06-13 Kimi-2.7 sweep falsely reported 5/5 boxes as no-OpenRouter from a `models.providers`-only check while `OPENROUTER_API_KEY` was live in the container env.

CCEOF
  echo "[apply-fleet-standards] CREDENTIAL_CHECK_V2 injected into $AGENTS_FILE_EARLY"
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
# PRD 1.11: Workspace resolution delegates to resolve_injected_core_files()
# (shared-utils/) — single source of truth for the gateway-injected paths.
# The inline 3-step fallback is kept for early-boot/install-time compatibility.
# The shared helper already defined _resolve_workspace_via_shared_helper above.
#
# Priority (mirrors install.sh Step 10 exactly):
#   1. agents.list[main].workspace (per-agent override — wins if set)
#   2. agents.defaults.workspace via `openclaw config get`
#   3. $OC_ROOT/workspace (canonical OpenClaw default — Mac or VPS)
# Clawd is dead; ~/clawd is never a fallback.

WORKSPACE_DIR=""
WORKSPACE_DIR=$(_resolve_workspace_via_shared_helper 2>/dev/null) || WORKSPACE_DIR=""

if [ -z "$WORKSPACE_DIR" ]; then
  # Inline fallback (step 1)
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

# Fallback step 2: agents.defaults.workspace via CLI
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

# Fallback step 3: canonical default
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

# ─── 6. Inject PRIME DIRECTIVE into workspace/SOUL.md (v11.3.2 G5-FIX) ───────
# The gateway injects bootstrap files from the main agent's workspace path
# (agents.list[main].workspace → agents.defaults.workspace → ~/.openclaw/workspace).
# build-workforce.py was writing the PRIME DIRECTIVE to DEPARTMENTS_DIR/ceo/SOUL.md
# (the dept-ceo sub-agent workspace) — NOT the file the gateway actually reads for
# the main orchestrator. This step injects the directive into workspace/SOUL.md and
# scrubs the contradictory "personal assistant / handle it yourself" intro.
# Idempotent: guarded by <!-- CEO_ORCHESTRATOR_RULE_V2 --> marker.
CEO_ORCH_V2_MARKER="<!-- CEO_ORCHESTRATOR_RULE_V2 -->"
WS_SOUL_FILE="$WORKSPACE_DIR/SOUL.md"
touch "$WS_SOUL_FILE"

if grep -qF "$CEO_ORCH_V2_MARKER" "$WS_SOUL_FILE" 2>/dev/null; then
  echo "[apply-fleet-standards] PRIME DIRECTIVE already present in $WS_SOUL_FILE — no-op"
else
  echo "[apply-fleet-standards] injecting PRIME DIRECTIVE into $WS_SOUL_FILE"
  # Read existing, strip V1 marker if present, strip personal-assistant intro
  SOUL_EXISTING=$(cat "$WS_SOUL_FILE" 2>/dev/null || true)
  # Strip V1 block if present
  if echo "$SOUL_EXISTING" | grep -qF "<!-- CEO_ORCHESTRATOR_RULE_V1 -->"; then
    SOUL_EXISTING=$(echo "$SOUL_EXISTING" | python3 -c "
import sys, re
content = sys.stdin.read()
content = re.sub(r'<!-- CEO_ORCHESTRATOR_RULE_V1 -->.*?---\s*\n', '', content, count=1, flags=re.DOTALL)
print(content, end='')
")
  fi
  # Strip "personal assistant / handle it yourself" intro (# SOUL.md ... first ---)
  SOUL_EXISTING=$(echo "$SOUL_EXISTING" | python3 -c "
import sys, re
content = sys.stdin.read()
content = re.sub(r'^# SOUL\.md.*?^---\s*\n', '', content, count=1, flags=re.DOTALL | re.MULTILINE)
print(content.lstrip(), end='')
")
  # Write PRIME DIRECTIVE + remaining content
  {
    cat <<'PDEOF'
<!-- CEO_ORCHESTRATOR_RULE_V2 -->
## ⛔ PRIME DIRECTIVE — I AM A TASK ROUTER. I ROUTE. THIS IS NOT OPTIONAL.

1. I am the master orchestrator (CEO). My one job is to ROUTE tasks. When any task or request
   reaches me, I ROUTE it to the correct DEPARTMENT — every time. I have NO permission to decide
   not to route, to refuse a task, or to choose what I will or will not do.
2. I do NOT do the work myself, and I do NOT pick the specialist or spawn/keep control of a
   sub-agent to do it. I route to the DEPARTMENT. The DEPARTMENT decides which specialist
   sub-agent and which persona are needed; the task gets a persona assigned; the task is placed
   on the Kanban board. The doing belongs to the department and its specialist — never to me.
3. Before I would EVER do a task myself, I must FIRST seek and RECEIVE explicit permission and
   consent from the owner (the human in control). Without that explicit consent, I route — always.
   (Routing is my default and is always allowed; I never need permission to route.)
4. If I cannot determine the right department, I route to the General Tasks department. I never
   self-execute because I'm unsure, and I never hold a task to "stay in control" of it.
5. What I MAY do: have conversations, manage agents, manage departments, and route tasks.
   What I may NEVER do: refuse to route, decide who executes, execute the work myself, or
   commandeer a sub-agent to keep control.

### Routing = Creating a DEPARTMENT TASK (not spawning a sub-agent directly)

The correct routing action is POST to `/api/tasks/ingest` with `department_slug: "<slug>"`.
This places the task on the department's Kanban — the DEPARTMENT assigns the specialist.

Spawning a sub-agent and instructing it to execute production work IS THE SAME VIOLATION as
executing the work yourself. If a sub-agent is spawned, it MUST read its own role files and
operate via the task board — it is not a production tool for the orchestrator.

### Binding Rules

- **R1** Never generate images, videos, audio, or written deliverables
- **R2** Never write to files, databases, or external APIs as a production action
- **R3** Never use any skill that produces a deliverable (`skills: []` enforced in config)
- **R4** Every actionable request → `POST /api/tasks/ingest` with `department_slug`
- **R5** If CC unreachable → escalate via Telegram, do NOT execute directly
- **R6** If route is unclear → use `department_slug: "general-task"`, never self-execute
- **R7** Permitted actions only: Telegram messaging, task-ingest POST, read workspace files, gateway restart

---

PDEOF
    printf '%s' "$SOUL_EXISTING"
  } > "$WS_SOUL_FILE"
  echo "[apply-fleet-standards] PRIME DIRECTIVE written to $WS_SOUL_FILE"
fi

if [ "$OC_ROOT" = "/data/.openclaw" ]; then
  chown "$OC_USER:$OC_USER" "$WS_SOUL_FILE" 2>/dev/null || true
fi

echo ""
echo "[apply-fleet-standards] DONE"
echo "[apply-fleet-standards] Backup: $OC_BACKUP"
echo "[apply-fleet-standards] Current: $OC_CONFIG"
echo "[apply-fleet-standards] AGENTS.md: $AGENTS_FILE"
echo "[apply-fleet-standards] workspace/SOUL.md: $WS_SOUL_FILE"
