#!/usr/bin/env bash
# activate-memory-stack.sh — Idempotent activator for the 8-layer memory +
# dreaming + embeddings stack on OpenClaw 2026.5.20+.
#
# Why a script and not `openclaw config set`:
#   On OpenClaw 2026.5.20+ the schema validator rejects deeply-nested keys via
#   `openclaw config set` ("Invalid input") because the parent path doesn't
#   exist yet. The supported pattern is a direct JSON merge against
#   openclaw.json, then `openclaw config validate`. This script ships the
#   canonical block verified live on multiple client boxes.
#
# What it sets (canonical fleet-verified config):
#   - agents.defaults.memorySearch       — gemini provider, openai fallback,
#                                          gemini-embedding-001, hybrid search,
#                                          session-memory + sync, an EMPTY
#                                          extraPaths (memory-bloat guard), and a
#                                          capped embedding cache (maxEntries=512).
#   - agents.list[main].memorySearch     — the shared master-files corpus is
#                                          attached HERE, to the single "main"
#                                          agent, embedded ONCE (never in
#                                          agents.defaults, which the runtime
#                                          unions onto every dept agent → N copies
#                                          of the corpus → multi-GB-per-box bloat).
#   - plugins.entries.memory-core        — enabled + dreaming.enabled = true.
#   - memory.backend                     — "builtin".
#   - secrets/.env GEMINI_API_KEY        — canonicalized from any of
#                                          GOOGLE_API_KEY / GOOGLE_GEMINI_API_KEY
#                                          if GEMINI_API_KEY isn't set.
#
# Idempotent: re-running on an already-activated box is a no-op (Python
# deep-merge is order-preserving and only writes when the file changes).
#
# Path detection:
#   - If /data/.openclaw/openclaw.json exists  → VPS container layout.
#   - Else                                     → $HOME/.openclaw/openclaw.json
#                                                (Mac mini layout).
#
# Verification (success criteria):
#   openclaw memory status   must show
#     Provider: gemini (requested: gemini)
#     Model:    gemini-embedding-001  (or just "gemini")
#     Dreaming: 0 3 * * *
#   openclaw config validate must exit clean.

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
OC_SECRETS="$OC_ROOT/secrets/.env"

echo "[activate-memory-stack] config:  $OC_CONFIG"
echo "[activate-memory-stack] secrets: $OC_SECRETS"

# ─── 1. Canonicalize GEMINI_API_KEY in secrets/.env ──────────────────────────
mkdir -p "$(dirname "$OC_SECRETS")"
touch "$OC_SECRETS"

current_gemini="$(grep -E '^GEMINI_API_KEY=' "$OC_SECRETS" 2>/dev/null | tail -1 | cut -d= -f2- || true)"
if [ -z "${current_gemini:-}" ]; then
  # Try common aliases — first hit wins.
  for alias in GOOGLE_GEMINI_API_KEY GOOGLE_API_KEY; do
    val="$(grep -E "^${alias}=" "$OC_SECRETS" 2>/dev/null | tail -1 | cut -d= -f2- || true)"
    if [ -n "${val:-}" ]; then
      echo "[activate-memory-stack] canonicalizing $alias → GEMINI_API_KEY"
      printf '\nGEMINI_API_KEY=%s\n' "$val" >> "$OC_SECRETS"
      break
    fi
  done
else
  echo "[activate-memory-stack] GEMINI_API_KEY already set in secrets/.env"
fi

# ─── 2. Deep-merge the canonical memory block into openclaw.json ─────────────
python3 - "$OC_CONFIG" <<'PYEOF'
import json
import sys
from pathlib import Path

cfg_path = Path(sys.argv[1])
cfg = json.loads(cfg_path.read_text())
before = json.dumps(cfg, sort_keys=True)

CANONICAL = {
    "agents": {
        "defaults": {
            "memorySearch": {
                "enabled": True,
                "sources": ["memory", "sessions"],
                "provider": "gemini",
                "fallback": "openai",
                "experimental": {"sessionMemory": True},
                "sync": {
                    "onSessionStart": True,
                    "onSearch": True,
                    "watch": True,
                    "watchDebounceMs": 1200,
                    "sessions": {"deltaBytes": 20000, "deltaMessages": 10},
                },
                "model": "gemini-embedding-001",
                "query": {
                    "maxResults": 50,
                    "minScore": 0.18,
                    "hybrid": {"enabled": True},
                },
                # MEMORY-BLOAT GUARD (system-memory-fix): the shared master-files
                # corpus must NEVER be listed here, in agents.defaults.memorySearch.
                # The OpenClaw runtime UNIONS each agent's extraPaths onto
                # agents.defaults — so a corpus path placed in defaults (or in any
                # per-dept agent's extraPaths) gets re-embedded into EVERY
                # department's memory DB, producing multi-GB-per-box bloat (one
                # full copy of the corpus per dept). The corpus is attached ONCE,
                # to the single "main" agent only — see step 2b below. Keep this
                # empty so new dept agents inherit an empty extraPaths set.
                "extraPaths": [],
                # EMBEDDING-CACHE CAP (system-memory-fix): bound the in-RAM
                # embedding cache so it cannot run away again. maxEntries is the
                # fleet-confirmed schema knob (KNOWN-ISSUES.md §1; also written by
                # install.sh). Unconditional cap (independent of fallback config).
                "cache": {"enabled": True, "maxEntries": 512},
            },
            # v10.x.6 recovery knob: hard agent-turn timeout in SECONDS. Schema
            # confirmed against dist 2026.5.20 (agents.defaults.timeoutSeconds,
            # number().int().positive().optional()). 600s = 10 min: generous
            # enough for legit long-thinking calls (deepseek thinking=high runs
            # 2-5 min), short enough to recover from a true hang. Also drives the
            # internal CLI stall watchdog window (noOutputTimeoutRatio scaled,
            # clamped 180-600s) so a stalled session recovers instead of hanging.
            "timeoutSeconds": 600,
        }
    },
    "plugins": {
        "entries": {
            "memory-core": {
                "enabled": True,
                "config": {"dreaming": {"enabled": True}},
            }
        }
    },
    "memory": {"backend": "builtin"},
}


def deep_merge(dst, src):
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst


deep_merge(cfg, CANONICAL)
after = json.dumps(cfg, sort_keys=True)

if before == after:
    print("[activate-memory-stack] config already canonical — no-op")
else:
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n")
    print("[activate-memory-stack] config merged → " + str(cfg_path))
PYEOF

# ─── 2b. Attach the shared master-files corpus to the MAIN agent ONLY ────────
# Why: the corpus must be embedded ONCE, into a single index, not unioned into
# every department's DB. agents.defaults.memorySearch.extraPaths is left EMPTY
# (step 2 above) precisely because the runtime unions defaults onto every agent.
# Here we place the corpus path on the single agents.list[] entry with id="main"
# (and create that entry if it is somehow absent), so exactly one DB embeds it.
#
# Corpus discovery (in priority order, first hit wins):
#   1. $OC_ROOT/.skill-38-master-files-dir  (pointer file written by Skill 38)
#   2. env MASTER_FILES_DIR                  (operator override)
#   3. ~/Downloads/*openclaw*master* / *openclaw*onboarding*  (Mac default)
# If no corpus dir is found, this step is a clean no-op (the box just has no
# extra corpus to index yet) — it never fails the activation.
CORPUS_DIR=""
POINTER="$OC_ROOT/.skill-38-master-files-dir"
if [ -f "$POINTER" ]; then
  CORPUS_DIR="$(head -n1 "$POINTER" 2>/dev/null || true)"
fi
if [ -z "${CORPUS_DIR:-}" ] && [ -n "${MASTER_FILES_DIR:-}" ]; then
  CORPUS_DIR="$MASTER_FILES_DIR"
fi
if [ -z "${CORPUS_DIR:-}" ] && [ -d "$HOME/Downloads" ]; then
  CORPUS_DIR="$(find "$HOME/Downloads" -maxdepth 2 -type d \
    \( -iname '*openclaw*master*' -o -iname '*openclaw*onboarding*' \) 2>/dev/null \
    | head -n1 || true)"
fi

if [ -n "${CORPUS_DIR:-}" ] && [ -d "$CORPUS_DIR" ]; then
  # Resolve to an absolute path (OpenClaw resolves non-absolute extraPaths
  # relative to the workspace dir, which breaks ~/… paths).
  CORPUS_DIR="$(cd "$CORPUS_DIR" && pwd)"
  echo "[activate-memory-stack] attaching shared corpus to MAIN agent only: $CORPUS_DIR"
  OC_CORPUS_DIR="$CORPUS_DIR" python3 - "$OC_CONFIG" <<'PYEOF'
import json
import os
import sys
from pathlib import Path

cfg_path = Path(sys.argv[1])
corpus = os.environ["OC_CORPUS_DIR"]
cfg = json.loads(cfg_path.read_text())
before = json.dumps(cfg, sort_keys=True)

agents = cfg.setdefault("agents", {})
agent_list = agents.setdefault("list", [])
if not isinstance(agent_list, list):
    agent_list = []
    agents["list"] = agent_list

main = next((a for a in agent_list if isinstance(a, dict) and a.get("id") == "main"), None)
if main is None:
    main = {"id": "main"}
    agent_list.insert(0, main)

ms = main.setdefault("memorySearch", {})
paths = ms.setdefault("extraPaths", [])
if not isinstance(paths, list):
    paths = []
    ms["extraPaths"] = paths

# Defensive: strip the corpus from agents.defaults.memorySearch.extraPaths if a
# legacy/agent-driven install ever planted it there (that is the bloat source).
defaults_ms = cfg.get("agents", {}).get("defaults", {}).get("memorySearch", {})
dpaths = defaults_ms.get("extraPaths")
if isinstance(dpaths, list) and corpus in dpaths:
    defaults_ms["extraPaths"] = [p for p in dpaths if p != corpus]
    print("[activate-memory-stack] removed corpus from agents.defaults.memorySearch.extraPaths (bloat source)")

if corpus in paths:
    print("[activate-memory-stack] corpus already attached to main agent — no-op")
else:
    paths.append(corpus)

after = json.dumps(cfg, sort_keys=True)
if before == after:
    print("[activate-memory-stack] corpus attachment already canonical — no-op")
else:
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n")
    print("[activate-memory-stack] corpus attached to agents.list[main].memorySearch.extraPaths")
PYEOF
else
  echo "[activate-memory-stack] no shared master-files corpus found — skipping corpus attach (no-op)"
fi

# ─── 3. Chown back to the OpenClaw runtime user (VPS container only) ─────────
if [ "$OC_ROOT" = "/data/.openclaw" ]; then
  chown "$OC_USER:$OC_USER" "$OC_CONFIG" 2>/dev/null || true
  chown "$OC_USER:$OC_USER" "$OC_SECRETS" 2>/dev/null || true
fi

# ─── 4. Validate + report ────────────────────────────────────────────────────
echo ""
echo "[activate-memory-stack] running: openclaw config validate"
if ! openclaw config validate; then
  echo "ERROR: openclaw config validate failed — see output above" >&2
  exit 1
fi

echo ""
echo "[activate-memory-stack] running: openclaw memory status"
openclaw memory status || true

echo ""
echo "[activate-memory-stack] DONE. Verify the output above shows:"
echo "  • Provider: gemini (requested: gemini)"
echo "  • Model:    gemini-embedding-001  (or just 'gemini')"
echo "  • Dreaming: 0 3 * * *"
