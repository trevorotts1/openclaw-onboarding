#!/usr/bin/env bash
# 19-configure-dreaming-embeddings.sh
# Skill 38 — Step O.6 (Dreaming + Embeddings configuration).
# Idempotent: skips if memory.search.provider (current OpenClaw key) or the legacy
# agents.defaults.memorySearch.provider is already set. A box on the Skill 76 local
# Ollama embedder (provider ollama on loopback) is accepted with no key needed.
# Uses Python deep-merge (NOT `openclaw config set` — that fails with
# "Invalid input" for nested keys on 2026.5.22+; see ~/clawd/MEMORY.md
# "OpenClaw 8-layer memory activation pattern").
set -euo pipefail

OS="$(uname -s)"
TS="$(date +%Y%m%d-%H%M%S)"

if [ "$OS" = "Darwin" ]; then
  OPENCLAW_DIR="$HOME/.openclaw"
else
  if [ -d "/data/.openclaw" ]; then
    OPENCLAW_DIR="/data/.openclaw"
  else
    OPENCLAW_DIR="$HOME/.openclaw"
  fi
fi
CONFIG_FILE="$OPENCLAW_DIR/openclaw.json"

if [ ! -f "$CONFIG_FILE" ]; then
  echo "[O.6] ERROR: $CONFIG_FILE not found." >&2
  exit 1
fi

# Detect provider via env file hint (or env vars) — prefer openai for memorySearch
ENV_HINT_FILE="$HOME/.openclaw/.skill-38-secrets-env-path"
ENV_FILE=""
[ -f "$ENV_HINT_FILE" ] && ENV_FILE="$(cat "$ENV_HINT_FILE" 2>/dev/null || true)"

has_key() {
  local k="$1"
  if [ -n "$ENV_FILE" ] && [ -f "$ENV_FILE" ]; then
    grep -qE "^${k}=" "$ENV_FILE" && return 0
  fi
  [ -n "${!k:-}" ] && return 0
  return 1
}

# Skill 76: a box whose memory search runs on the local Ollama embedder
# (provider ollama + remote.baseUrl on 127.0.0.1/localhost/::1) needs no OpenAI or
# Google key. Accept it before the key check instead of failing.
if python3 - "$CONFIG_FILE" <<'LEPY' 2>/dev/null
import json, sys
from urllib.parse import urlparse
c = json.load(open(sys.argv[1]))
new = (c.get("memory") or {}).get("search") if isinstance(c.get("memory"), dict) else None
new = new if isinstance(new, dict) else {}
old = ((c.get("agents") or {}).get("defaults") or {}).get("memorySearch") or {}
prov = new.get("provider") or old.get("provider")
remote = new.get("remote") or old.get("remote") or {}
host = urlparse(str(remote.get("baseUrl") or "")).hostname if isinstance(remote, dict) else ""
sys.exit(0 if str(prov or "").strip().lower() == "ollama" and host in ("127.0.0.1", "localhost", "::1") else 1)
LEPY
then
  echo "[O.6] memory search runs on the local Ollama embedder (Skill 76) — accepted, no OpenAI/Google key needed, nothing changed."
  exit 0
fi

# SK1-02: resolve a CLIENT-OWNED embedding provider for memorySearch. Anthropic is
# NEVER valid here: (1) Anthropic ships no embeddings API, so writing it to
# memorySearch.provider breaks memory search outright; (2) clients never use
# Anthropic. Choose openai or google by key presence, else FAIL LOUD — never fall
# back to Anthropic and never silently default to a provider whose key is absent.
if has_key "OPENAI_API_KEY"; then
  PROVIDER="openai"
elif has_key "GEMINI_API_KEY" || has_key "GOOGLE_API_KEY"; then
  PROVIDER="google"
else
  echo "[O.6] ERROR: no client-owned embedding provider key found (need OPENAI_API_KEY or GEMINI_API_KEY/GOOGLE_API_KEY). Anthropic has no embeddings API and is never used, so memorySearch cannot be configured. Add a valid embedding provider key and re-run." >&2
  exit 1
fi

# Idempotency check: skip if memorySearch.provider already set
EXISTING="$(python3 -c "
import json,sys
try:
  c=json.load(open('$CONFIG_FILE'))
  new=(c.get('memory') or {}).get('search') if isinstance(c.get('memory'), dict) else None
  v=(new or {}).get('provider') or c.get('agents',{}).get('defaults',{}).get('memorySearch',{}).get('provider')
  print(v if v else '')
except Exception:
  print('')
" 2>/dev/null || true)"
if [ -n "$EXISTING" ]; then
  echo "[O.6] memorySearch.provider already set to '$EXISTING' — skipping (idempotent)."
  exit 0
fi

# Backup before write
BACKUP="${CONFIG_FILE}.bak-pre-skill38-O6-${TS}"
cp "$CONFIG_FILE" "$BACKUP"
echo "[O.6] Pre-write backup: $BACKUP"

python3 - "$CONFIG_FILE" "$PROVIDER" <<'PY'
import json, sys, os
path, provider = sys.argv[1], sys.argv[2]
with open(path) as f:
    cfg = json.load(f)

def ensure(d, k):
    if k not in d or not isinstance(d[k], dict):
        d[k] = {}
    return d[k]

agents = ensure(cfg, 'agents')
defaults = ensure(agents, 'defaults')
ms = ensure(defaults, 'memorySearch')
# Per ~/clawd/MEMORY.md: fallback is a STRING "openai", timeoutSeconds (NOT agentTimeoutMs)
ms['provider'] = provider
ms['fallback'] = 'openai'
ms['timeoutSeconds'] = 600

plugins = ensure(cfg, 'plugins')
entries = ensure(plugins, 'entries')
mc = ensure(entries, 'memory-core')
mc_cfg = ensure(mc, 'config')
dreaming = ensure(mc_cfg, 'dreaming')
dreaming['enabled'] = True
dreaming['schedule'] = '0 3 * * *'
dreaming.setdefault('phases', ['light', 'rem', 'deep'])
dreaming.setdefault('thresholds', {
    'minScore': 0.8,
    'minRecallCount': 3,
    'minUniqueQueries': 3,
})

tmp = path + '.tmp'
with open(tmp, 'w') as f:
    json.dump(cfg, f, indent=2)
    f.write('\n')
os.replace(tmp, path)
print(f"[O.6] Wrote memorySearch (provider={provider}, fallback=openai, timeoutSeconds=600) + dreaming.enabled=true to {path}")
PY

echo "[O.6] OK"
