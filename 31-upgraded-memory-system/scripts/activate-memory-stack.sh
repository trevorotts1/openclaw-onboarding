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
#   - agents.defaults.memorySearch       — embedding provider is CONDITIONAL
#                                          (v13.2.1): gemini-embedding-2 @3072 when
#                                          a usable Google/Gemini key is present
#                                          (any of 3 aliases × every store + live
#                                          container env), else openai
#                                          text-embedding-3-small, else openrouter
#                                          openai/text-embedding-3-large — NEVER a
#                                          model the box has no key for. Plus
#                                          hybrid search, session-memory + sync, an
#                                          EMPTY extraPaths (memory-bloat guard),
#                                          and a capped embedding cache (512).
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
#     Model:    gemini-embedding-2 @3072  (or just "gemini")
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
  # Try common aliases — first hit wins. All three Google AI Studio aliases
  # (GOOGLE_API_KEY / GOOGLE_AI_STUDIO_API_KEY / GEMINI_API_KEY) are the SAME key.
  for alias in GOOGLE_GEMINI_API_KEY GOOGLE_API_KEY GOOGLE_AI_STUDIO_API_KEY GOOGLE_GENERATIVE_AI_API_KEY GOOGLE_AI_API_KEY; do
    val="$(grep -E "^${alias}=" "$OC_SECRETS" 2>/dev/null | tail -1 | cut -d= -f2- || true)"
    if [ -n "${val:-}" ]; then
      echo "[activate-memory-stack] canonicalizing $alias → GEMINI_API_KEY"
      printf '\nGEMINI_API_KEY=%s\n' "$val" >> "$OC_SECRETS"
      current_gemini="$val"
      break
    fi
  done
else
  echo "[activate-memory-stack] GEMINI_API_KEY already set in secrets/.env"
fi

# ─── 1b. SMART usable-Gemini-key detection (v13.2.1 CONDITIONAL default) ──────
# v13.2.0 unconditionally pinned gemini-embedding-2 as the embedding default,
# which broke boxes with NO usable Google key (it pinned a model they cannot
# serve). The default is now CONDITIONAL on a usable key. "No key" is a HIGH BAR:
# a single Google credential is the SAME key under THREE env NAMES
# (GOOGLE_API_KEY / GOOGLE_AI_STUDIO_API_KEY / GEMINI_API_KEY) and can live in
# SEVERAL stores. We check ALL of them before concluding "no key".
GEMINI_ALL_ALIASES="GEMINI_API_KEY GOOGLE_API_KEY GOOGLE_AI_STUDIO_API_KEY GOOGLE_GEMINI_API_KEY GOOGLE_GENERATIVE_AI_API_KEY GOOGLE_AI_API_KEY"
OPENAI_ALL_ALIASES="OPENAI_API_KEY OPENAI_TOKEN"
OPENROUTER_ALL_ALIASES="OPENROUTER_API_KEY OR_API_KEY"

# Real-key gate: non-empty, length ≥ 10, not an obvious placeholder. (Light
# version of install.sh's looks_like_real_key — this script has no access to it.)
_looks_real() {
  local v="$1"
  [ -z "$v" ] && return 1
  [ "${#v}" -lt 10 ] && return 1
  case "$(printf '%s' "$v" | tr '[:upper:]' '[:lower:]')" in
    *xxxxx*|*your_*|*your-*|*placeholder*|*changeme*|*change_me*|*replace_me*|*_here*|*example*|*sample*|*dummy*|none|null|true|false) return 1 ;;
  esac
  return 0
}

# _key_in_stores <space-separated-aliases> → echoes value + returns 0 if found.
_key_in_stores() {
  local aliases="$1" a v ef ctr
  # (i) live shell env
  for a in $aliases; do
    v="$(printenv "$a" 2>/dev/null || true)"
    if _looks_real "$v"; then echo "$v"; return 0; fi
  done
  # (ii) named .env stores: box secrets + workspace + clawd + host docker compose
  local STORES="$OC_SECRETS"
  STORES="$STORES $OC_ROOT/.env $OC_ROOT/workspace/.env"
  STORES="$STORES $HOME/.openclaw/secrets/.env $HOME/.openclaw/workspace/.env $HOME/clawd/secrets/.env"
  for ef in /docker/*/.env /data/docker/*/.env; do
    [ -f "$ef" ] && STORES="$STORES $ef"
  done
  for ef in $STORES; do
    [ -f "$ef" ] || continue
    for a in $aliases; do
      v="$(grep -E "^[[:space:]]*(export[[:space:]]+)?${a}=" "$ef" 2>/dev/null \
          | grep -vE "^[[:space:]]*#" \
          | sed -E "s/^[[:space:]]*(export[[:space:]]+)?${a}=//" \
          | sed -E 's/[[:space:]]*#.*$//' | head -1 || true)"
      v="${v%\"}"; v="${v#\"}"; v="${v%\'}"; v="${v#\'}"
      if _looks_real "$v"; then echo "$v"; return 0; fi
    done
  done
  # (iii) openclaw.json env.vars + models.providers.<google|openai|openrouter>.apiKey
  if [ -f "$OC_CONFIG" ]; then
    v="$(OC_CFG="$OC_CONFIG" OC_ALIASES="$aliases" python3 - <<'PYEOF' 2>/dev/null || true
import json, os
cfg = {}
try: cfg = json.load(open(os.environ["OC_CFG"]))
except Exception: pass
aliases = os.environ["OC_ALIASES"].split()
ev = cfg.get("env", {}).get("vars", {}) or {}
for a in aliases:
    if ev.get(a):
        print(ev[a]); raise SystemExit
provs = cfg.get("models", {}).get("providers", {}) or {}
# map alias-set → provider key
pk = "google" if "GEMINI_API_KEY" in aliases else ("openai" if "OPENAI_API_KEY" in aliases else ("openrouter" if "OPENROUTER_API_KEY" in aliases else None))
for cand in ([pk, "gemini"] if pk == "google" else [pk]):
    if cand and provs.get(cand, {}).get("apiKey"):
        print(provs[cand]["apiKey"]); raise SystemExit
PYEOF
)"
    if _looks_real "$v"; then echo "$v"; return 0; fi
  fi
  # (iv) live container env (VPS): docker exec <openclaw container> printenv
  if command -v docker >/dev/null 2>&1; then
    ctr="$(docker ps --format '{{.Names}}' 2>/dev/null | grep -iE 'openclaw|clawd' | head -1 || true)"
    if [ -n "$ctr" ]; then
      for a in $aliases; do
        v="$(docker exec "$ctr" printenv "$a" 2>/dev/null | head -1 || true)"
        if _looks_real "$v"; then echo "$v"; return 0; fi
      done
    fi
  fi
  return 1
}

GEMINI_OK=0; OPENAI_OK=0; OPENROUTER_OK=0
if _key_in_stores "$GEMINI_ALL_ALIASES" >/dev/null 2>&1; then GEMINI_OK=1; fi
if _key_in_stores "$OPENAI_ALL_ALIASES" >/dev/null 2>&1; then OPENAI_OK=1; fi
if _key_in_stores "$OPENROUTER_ALL_ALIASES" >/dev/null 2>&1; then OPENROUTER_OK=1; fi

# Decide the embedding provider/model THIS box can actually serve.
if [ "$GEMINI_OK" = "1" ]; then
  EMBED_PROVIDER="gemini";     EMBED_MODEL="gemini-embedding-2";              EMBED_DIM=3072
  echo "[activate-memory-stack] usable Google/Gemini key FOUND → embedding default = gemini-embedding-2 @3072 (fleet standard)"
elif [ "$OPENAI_OK" = "1" ]; then
  EMBED_PROVIDER="openai";     EMBED_MODEL="text-embedding-3-small";          EMBED_DIM=1536
  echo "[activate-memory-stack] NO usable Gemini key (3 aliases × every store) → embedding default = openai/text-embedding-3-small (never pin a keyless model)"
elif [ "$OPENROUTER_OK" = "1" ]; then
  EMBED_PROVIDER="openrouter"; EMBED_MODEL="openai/text-embedding-3-large";   EMBED_DIM=3072
  echo "[activate-memory-stack] NO usable Gemini key → embedding default = openrouter/openai/text-embedding-3-large (never pin a keyless model)"
else
  EMBED_PROVIDER=""; EMBED_MODEL=""; EMBED_DIM=0
  echo "[activate-memory-stack] NO embedding-capable key (Gemini/OpenAI/OpenRouter) → leaving existing memorySearch provider/model untouched (no forced gemini pin)"
fi
export EMBED_PROVIDER EMBED_MODEL EMBED_DIM GEMINI_OK

# ─── 2. STAGE both configuration mutations into ONE temporary file ───────────
#
# SK1-30 / T2-28 — WHY A STAGING FILE. The two mutations below (the canonical
# memory block, then the corpus attachment) each used to rewrite the LIVE
# openclaw.json in place, and `openclaw config validate` ran afterwards. An
# interruption between the two writes, or a validation failure after them, left
# the box holding a configuration that was never validated and could not be
# restored. This is the file the gateway reads at start.
#
# Both mutations now apply to a staging copy in the SAME directory as the live
# config (so the final replace is an atomic same-filesystem rename). The staged
# file is validated, a timestamped backup of the original is written, and only
# then is the staged file moved into place. If the runtime validator rejects the
# result, the backup is restored and the run exits non-zero.
OC_STAGED="$OC_ROOT/.openclaw.json.staging.$$"
OC_BACKUP="$OC_ROOT/openclaw.json.bak.$(date -u +%Y%m%dT%H%M%SZ)"
cleanup_staged() { [ -f "$OC_STAGED" ] && rm -f "$OC_STAGED" 2>/dev/null || true; }
trap cleanup_staged EXIT

cp "$OC_CONFIG" "$OC_STAGED"

EMBED_PROVIDER="$EMBED_PROVIDER" EMBED_MODEL="$EMBED_MODEL" EMBED_DIM="$EMBED_DIM" GEMINI_OK="$GEMINI_OK" \
python3 - "$OC_STAGED" <<'PYEOF'
import json
import os
import sys
from pathlib import Path

cfg_path = Path(sys.argv[1])
cfg = json.loads(cfg_path.read_text())
before = json.dumps(cfg, sort_keys=True)

# v13.2.1 CONDITIONAL embedding default — provider/model/dimensions are decided
# in bash (step 1b) from the keys this box can ACTUALLY serve, then passed in.
# Empty EMBED_PROVIDER ⇒ no embedding-capable key ⇒ leave existing config alone.
EMBED_PROVIDER = os.environ.get("EMBED_PROVIDER", "").strip()
EMBED_MODEL    = os.environ.get("EMBED_MODEL", "").strip()
try:
    EMBED_DIM = int(os.environ.get("EMBED_DIM", "0") or "0")
except ValueError:
    EMBED_DIM = 0
GEMINI_OK = os.environ.get("GEMINI_OK", "0").strip() == "1"

# memorySearch fields that are ALWAYS canonical (independent of the provider).
_MS_BASE = {
    "enabled": True,
    "sources": ["memory", "sessions"],
    "experimental": {"sessionMemory": True},
    "sync": {
        "onSessionStart": True,
        "onSearch": True,
        "watch": True,
        "watchDebounceMs": 1200,
        "sessions": {"deltaBytes": 20000, "deltaMessages": 10},
    },
    "query": {
        "maxResults": 50,
        "minScore": 0.18,
        "hybrid": {"enabled": True},
    },
    # MEMORY-BLOAT GUARD (system-memory-fix): the shared master-files corpus must
    # NEVER be listed here, in agents.defaults.memorySearch. The OpenClaw runtime
    # UNIONS each agent's extraPaths onto agents.defaults — so a corpus path in
    # defaults gets re-embedded into EVERY department's DB (multi-GB-per-box
    # bloat). The corpus is attached ONCE, to the single "main" agent (step 2b).
    "extraPaths": [],
    # EMBEDDING-CACHE CAP (system-memory-fix): bound the in-RAM embedding cache.
    "cache": {"enabled": True, "maxEntries": 512},
}

# Provider/model/dimensions/fallback are CONDITIONAL (v13.2.1). Only set them
# when we actually resolved a provider the box can serve. fallback is openai
# only when gemini is primary AND we have openai as a second provider — but to
# preserve prior behavior we keep the legacy "openai" string when gemini is
# primary (install.sh writes the structured fallback object).
_ms_canon = dict(_MS_BASE)
if EMBED_PROVIDER:
    _ms_canon["provider"] = EMBED_PROVIDER
    _ms_canon["model"] = EMBED_MODEL
    _ms_canon["dimensions"] = EMBED_DIM
    if EMBED_PROVIDER == "gemini":
        _ms_canon["fallback"] = "openai"

# SK1-30 / T2-27 — the REQUIRED Layer-8 settings. SKILL.md:14 states
# "ACTIVE MEMORY IS REQUIRED - Layer 8 (Active Memory) requires memory-core with
# autoCapture: true and autoRecall: true. This is NOT optional", and SKILL.md's
# "Active Memory Configuration (Layer 8)" block documents the activeMemory
# object beside it. Neither was in the configuration this script applied, so the
# only supported activation path could not produce the state the skill declares
# mandatory: the layer reported active and captured nothing.
_MEMORY_REQUIRED = {
    "autoCapture": True,
    "autoRecall": True,
}
_ACTIVE_MEMORY_REQUIRED = {
    "enabled": True,
    "flushIntervalMinutes": 30,
    "contextInjection": {
        "memoryWiki": True,
        "cognee": True,
    },
}

CANONICAL = {
    "agents": {
        "defaults": {
            "memorySearch": _ms_canon,
            "memory": _MEMORY_REQUIRED,
            "activeMemory": _ACTIVE_MEMORY_REQUIRED,
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

# ── EMBEDDING-PREVENTION BUNDLE item 3: PROVIDER-SELF-LOOP GUARDRAIL ──────────
# No agent's embedding provider/model/fallback may be the literal 'none' (a
# cycled-then-cleared provider lands on 'none' and silently breaks the embed
# index). Sweep defaults AND every per-agent memorySearch block; repair 'none'
# provider/model — and (v13.2.1) repair to a provider/model THE BOX CAN SERVE,
# never unconditionally to gemini (that was the keyless-pin regression).
#
# Repair target = the conditional default we resolved in step 1b (EMBED_*). If
# this box has no embedding-capable key at all (EMBED_PROVIDER==""), a 'none'
# provider is dropped rather than re-pinned to an unservable model.
if EMBED_PROVIDER:
    CANON_PROVIDER = EMBED_PROVIDER
    CANON_MODEL    = EMBED_MODEL
else:
    CANON_PROVIDER = None
    CANON_MODEL    = None
# Truly dying gemini models we always migrate away from (HARD-SHUTS-DOWN
# 2026-07-14 / retired experimental). text-embedding-3-small is a serveable
# OpenAI model — NOT migrated away from on a no-gemini box (the v13.2.0 bug).
DYING_MODELS   = {"gemini-embedding-001", "gemini-embedding-exp-03-07"}

def _heal_ms(ms, where):
    if not isinstance(ms, dict):
        return
    if str(ms.get("provider")).lower() == "none":
        if CANON_PROVIDER:
            ms["provider"] = CANON_PROVIDER
            print(f"[activate-memory-stack] {where}.provider was 'none' → repaired to {CANON_PROVIDER!r} (provider-self-loop guard)")
        else:
            ms.pop("provider", None)
            print(f"[activate-memory-stack] {where}.provider was 'none' → removed (no embedding-capable key; not pinning an unservable provider)")
    m = ms.get("model")
    if str(m).lower() == "none":
        if CANON_MODEL:
            ms["model"] = CANON_MODEL
            print(f"[activate-memory-stack] {where}.model was 'none' → repaired to {CANON_MODEL!r} (provider-self-loop guard)")
        else:
            ms.pop("model", None)
            print(f"[activate-memory-stack] {where}.model was 'none' → removed (no embedding-capable key)")
    elif m in DYING_MODELS:
        # A dying GEMINI model. Only migrate it when this box can serve the
        # replacement; if it has no gemini key, fall back to the resolved model.
        if CANON_MODEL:
            ms["model"] = CANON_MODEL
            if CANON_PROVIDER:
                ms["provider"] = CANON_PROVIDER
            print(f"[activate-memory-stack] {where}.model migrated {m!r} → {CANON_MODEL!r} (pre-2026-07-14 shutdown guard)")
    fb = ms.get("fallback")
    if isinstance(fb, str) and fb.lower() == "none":
        ms.pop("fallback", None)
        print(f"[activate-memory-stack] {where}.fallback was 'none' → removed (provider-self-loop guard)")
    elif isinstance(fb, dict) and str(fb.get("provider")).lower() == "none":
        ms.pop("fallback", None)
        print(f"[activate-memory-stack] {where}.fallback.provider was 'none' → fallback removed (provider-self-loop guard)")

_heal_ms(cfg.get("agents", {}).get("defaults", {}).get("memorySearch"), "agents.defaults.memorySearch")
for _a in cfg.get("agents", {}).get("list", []) or []:
    if isinstance(_a, dict):
        _heal_ms(_a.get("memorySearch"), f"agents.list[{_a.get('id','?')}].memorySearch")

# POSTCONDITION on the staged file: the settings the skill declares mandatory
# must be present in what we are about to install. This is asserted here, on the
# staged copy, so a merge that silently failed to apply them can never reach the
# live configuration.
_d = cfg.get("agents", {}).get("defaults", {})
_missing = []
if _d.get("memory", {}).get("autoCapture") is not True:
    _missing.append("agents.defaults.memory.autoCapture")
if _d.get("memory", {}).get("autoRecall") is not True:
    _missing.append("agents.defaults.memory.autoRecall")
if _d.get("activeMemory", {}).get("enabled") is not True:
    _missing.append("agents.defaults.activeMemory.enabled")
if cfg.get("plugins", {}).get("entries", {}).get("memory-core", {}).get("enabled") is not True:
    _missing.append("plugins.entries.memory-core.enabled")
if cfg.get("memory", {}).get("backend") != "builtin":
    _missing.append("memory.backend=builtin")
if _missing:
    print("[activate-memory-stack] FATAL: the staged configuration is missing required "
          "Layer-8 settings: " + ", ".join(_missing), file=sys.stderr)
    raise SystemExit(1)

after = json.dumps(cfg, sort_keys=True)

# The staged file is always written (the corpus step below merges into the SAME
# file); whether anything actually CHANGED versus the live config is decided
# once, at the replace step, so an unchanged run is still a clean no-op.
cfg_path.write_text(json.dumps(cfg, indent=2) + "\n")
if before == after:
    print("[activate-memory-stack] canonical memory block already present — no change")
else:
    print("[activate-memory-stack] canonical memory block staged")
PYEOF
if [ $? -ne 0 ]; then
  echo "ERROR: staging the canonical memory block failed — the live configuration was NOT touched." >&2
  exit 1
fi

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
  OC_CORPUS_DIR="$CORPUS_DIR" python3 - "$OC_STAGED" <<'PYEOF'
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
cfg_path.write_text(json.dumps(cfg, indent=2) + "\n")
if before == after:
    print("[activate-memory-stack] corpus attachment already canonical — no change")
else:
    print("[activate-memory-stack] corpus staged onto agents.list[main].memorySearch.extraPaths")
PYEOF
  if [ $? -ne 0 ]; then
    echo "ERROR: staging the corpus attachment failed — the live configuration was NOT touched." >&2
    exit 1
  fi
else
  echo "[activate-memory-stack] no shared master-files corpus found — skipping corpus attach (no-op)"
fi

# ─── 2c. Validate the STAGED file, back up, then replace atomically ──────────
if ! python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$OC_STAGED"; then
  echo "ERROR: the staged configuration is not valid JSON — the live configuration was NOT touched." >&2
  exit 1
fi

if cmp -s "$OC_CONFIG" "$OC_STAGED"; then
  echo "[activate-memory-stack] configuration already canonical — no write needed (no-op)"
  rm -f "$OC_STAGED"
else
  cp -p "$OC_CONFIG" "$OC_BACKUP" || {
    echo "ERROR: could not write the backup $OC_BACKUP — refusing to replace the live configuration without one." >&2
    exit 1
  }
  # Same-directory rename: the live file is either the original or the fully
  # updated one, never a partial write, at every instant.
  mv -f "$OC_STAGED" "$OC_CONFIG" || {
    echo "ERROR: could not install the staged configuration; the original is intact at $OC_CONFIG (backup: $OC_BACKUP)." >&2
    exit 1
  }
  echo "[activate-memory-stack] configuration replaced atomically → $OC_CONFIG (backup: $OC_BACKUP)"
fi

# ─── 3. Chown back to the OpenClaw runtime user (VPS container only) ─────────
if [ "$OC_ROOT" = "/data/.openclaw" ]; then
  chown "$OC_USER:$OC_USER" "$OC_CONFIG" 2>/dev/null || true
  chown "$OC_USER:$OC_USER" "$OC_SECRETS" 2>/dev/null || true
fi

# ─── 4. Validate + verify the RUNTIME postconditions ─────────────────────────
echo ""
echo "[activate-memory-stack] running: openclaw config validate"
if ! openclaw config validate; then
  echo "ERROR: openclaw config validate failed — see output above." >&2
  if [ -f "$OC_BACKUP" ]; then
    cp -p "$OC_BACKUP" "$OC_CONFIG" && \
      echo "ERROR: restored the pre-activation configuration from $OC_BACKUP." >&2
  fi
  exit 1
fi

# SK1-30 / T0-45 — WHY THIS IS NO LONGER `|| true`.
#
# This used to be:
#     openclaw memory status || true
#     echo "[activate-memory-stack] DONE. Verify the output above shows:"
#     echo "  • Provider: gemini (requested: gemini)"
# The verification command's failure was discarded, so the script could not
# distinguish a healthy memory stack from one that cannot start — and it then
# printed a completion banner whose stated success criteria named Gemini even on
# the branch (step 1b) that resolved NO provider at all. The operator was told to
# confirm output the run may never have been able to produce, and the run had
# already declared DONE.
#
# The status call is now a real postcondition: its output and exit code are
# captured, a non-zero exit is fatal, and the criteria printed below are
# generated from the provider this box actually resolved.
echo ""
echo "[activate-memory-stack] running: openclaw memory status"
MEM_STATUS=""
MEM_RC=0
MEM_STATUS="$(openclaw memory status 2>&1)" || MEM_RC=$?
printf '%s\n' "$MEM_STATUS"
if [ "$MEM_RC" -ne 0 ]; then
  echo "" >&2
  echo "ERROR: 'openclaw memory status' exited $MEM_RC — the memory stack did not come up." >&2
  echo "       The configuration is installed at $OC_CONFIG (backup: ${OC_BACKUP:-none})," >&2
  echo "       but activation has NOT been verified, so this run is NOT done." >&2
  exit 1
fi

if [ -z "$(printf '%s' "$MEM_STATUS" | tr -d '[:space:]')" ]; then
  echo "" >&2
  echo "ERROR: 'openclaw memory status' produced no output — the activation postcondition" >&2
  echo "       could not be evaluated. A check that cannot run is not a pass." >&2
  exit 1
fi

# Resolve what the postcondition should be. EMBED_PROVIDER is what step 1b
# decided this box can serve; when it is empty the box has no embedding-capable
# key and the existing provider was deliberately left untouched, so we read the
# provider from the installed configuration instead of asserting a hard-coded one.
RESOLVED_PROVIDER="$EMBED_PROVIDER"
RESOLVED_MODEL="$EMBED_MODEL"
if [ -z "$RESOLVED_PROVIDER" ]; then
  RESOLVED_PROVIDER="$(python3 -c '
import json, sys
try:
    cfg = json.load(open(sys.argv[1]))
except Exception:
    raise SystemExit
ms = cfg.get("agents", {}).get("defaults", {}).get("memorySearch", {}) or {}
print(ms.get("provider") or "")
' "$OC_CONFIG" 2>/dev/null || true)"
  RESOLVED_MODEL="$(python3 -c '
import json, sys
try:
    cfg = json.load(open(sys.argv[1]))
except Exception:
    raise SystemExit
ms = cfg.get("agents", {}).get("defaults", {}).get("memorySearch", {}) or {}
print(ms.get("model") or "")
' "$OC_CONFIG" 2>/dev/null || true)"
fi

STATUS_LC="$(printf '%s' "$MEM_STATUS" | tr '[:upper:]' '[:lower:]')"

# A provider reported as literally "none" is the cycled-then-cleared state this
# skill exists to prevent — it is a failure whatever else the output says.
if printf '%s' "$STATUS_LC" | grep -Eq 'provider[^a-z0-9]+none'; then
  echo "" >&2
  echo "ERROR: the memory runtime reports Provider: none — the embedding index is dead." >&2
  exit 1
fi

if [ -n "$RESOLVED_PROVIDER" ]; then
  if printf '%s' "$STATUS_LC" | grep -qF "$(printf '%s' "$RESOLVED_PROVIDER" | tr '[:upper:]' '[:lower:]')"; then
    echo "[activate-memory-stack] postcondition OK: the runtime reports the resolved provider '$RESOLVED_PROVIDER'."
  else
    echo "" >&2
    echo "ERROR: this box resolved the embedding provider '$RESOLVED_PROVIDER', but" >&2
    echo "       'openclaw memory status' does not report it. Activation did not take." >&2
    exit 1
  fi
else
  echo "" >&2
  echo "ERROR: no embedding provider is resolvable for this box (no Gemini/OpenAI/OpenRouter" >&2
  echo "       key found in any store, and none configured), so Layer 4 cannot run." >&2
  echo "       Add an embedding-capable key and re-run — this script is idempotent." >&2
  exit 1
fi

echo ""
echo "[activate-memory-stack] DONE — verified. This box resolved:"
echo "  • Provider: $RESOLVED_PROVIDER"
if [ -n "$RESOLVED_MODEL" ]; then
  echo "  • Model:    $RESOLVED_MODEL${EMBED_DIM:+ @$EMBED_DIM}"
fi
echo "  • Dreaming: enabled (plugins.entries.memory-core.config.dreaming.enabled)"
echo "  • Active Memory: autoCapture + autoRecall + activeMemory.enabled are set"
