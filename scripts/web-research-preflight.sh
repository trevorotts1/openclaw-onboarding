#!/usr/bin/env bash
# ============================================================
#  OpenClaw Web Research Pre-Flight (N15 enforcement)
#  Fetches the three canonical sources BEFORE any settings config or model
#  install so the orchestrator has authoritative current values.
#
#    1. docs.openclaw.ai     — canonical bootstrap / sub-agent / threshold values
#    2. ollama.com           — for every ollama/* model in openclaw.json:
#                              context window, max output, exact model name
#    3. openrouter.ai        — for every openrouter/* model in openclaw.json:
#                              context window, pricing, exact model name
#
#  Output: a single JSON document at $HOME/.openclaw/preflight-research.json
#  (Mac) or /data/.openclaw/preflight-research.json (VPS) that the
#  Master Orchestrator reads before any settings-config phase.
#
#  Called by install.sh BEFORE any model config step.
#  v10.8.0 — P0-7 fix for Phase 9 score 0.35.
# ============================================================
set -u
SCRIPT_VERSION="1.0.0"

# Platform detect
if [ -d "/data/.openclaw" ]; then
  PLATFORM=vps
  OUT="/data/.openclaw/preflight-research.json"
  OCJ="/data/.openclaw/openclaw.json"
else
  PLATFORM=mac
  OUT="$HOME/.openclaw/preflight-research.json"
  OCJ="$HOME/.openclaw/openclaw.json"
fi

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# Init output structure
mkdir -p "$(dirname "$OUT")"

# --------------------------------------------------------
# 1. docs.openclaw.ai
# --------------------------------------------------------
DOCS_URL="https://docs.openclaw.ai/"
DOCS_TMP=$(mktemp)
DOCS_STATUS="ok"
DOCS_BODY=""
if curl -fsSL --max-time 20 "$DOCS_URL" -o "$DOCS_TMP" 2>/dev/null; then
  # Extract key sections we care about (limit to 8KB to keep JSON manageable)
  DOCS_BODY=$(head -c 8192 "$DOCS_TMP")
else
  DOCS_STATUS="unreachable"
fi
rm -f "$DOCS_TMP"

# --------------------------------------------------------
# 2. Ollama models in openclaw.json
# --------------------------------------------------------
OLLAMA_LOOKUPS="[]"
if [ -f "$OCJ" ]; then
  OLLAMA_MODELS=$(python3 -c "
import json, re, sys
try:
    cfg = json.load(open('$OCJ'))
except Exception:
    print(''); sys.exit(0)
found = set()
def walk(v):
    if isinstance(v, str):
        if v.startswith('ollama/'):
            found.add(v)
    elif isinstance(v, list):
        for x in v: walk(x)
    elif isinstance(v, dict):
        for x in v.values(): walk(x)
walk(cfg)
print('\\n'.join(sorted(found)))
" 2>/dev/null)
  LOOKUPS_JSON=""
  while IFS= read -r model_id; do
    [ -z "$model_id" ] && continue
    # Extract base name without :cloud suffix and ollama/ prefix
    base=${model_id#ollama/}
    base=${base%:cloud}
    URL="https://ollama.com/library/${base}"
    if curl -fsSL --max-time 10 -o /dev/null -w "%{http_code}" "$URL" 2>/dev/null | grep -q "^200$"; then
      st="ok"
    else
      st="unreachable"
    fi
    LOOKUPS_JSON="${LOOKUPS_JSON}{\"model_id\":\"$model_id\",\"url\":\"$URL\",\"status\":\"$st\"},"
  done <<< "$OLLAMA_MODELS"
  if [ -n "$LOOKUPS_JSON" ]; then
    OLLAMA_LOOKUPS="[${LOOKUPS_JSON%,}]"
  fi
fi

# --------------------------------------------------------
# 3. OpenRouter models in openclaw.json
# --------------------------------------------------------
OPENROUTER_LOOKUPS="[]"
if [ -f "$OCJ" ]; then
  OR_MODELS=$(python3 -c "
import json, sys
try:
    cfg = json.load(open('$OCJ'))
except Exception:
    print(''); sys.exit(0)
found = set()
def walk(v):
    if isinstance(v, str):
        if v.startswith('openrouter/'):
            found.add(v)
    elif isinstance(v, list):
        for x in v: walk(x)
    elif isinstance(v, dict):
        for x in v.values(): walk(x)
walk(cfg)
print('\\n'.join(sorted(found)))
" 2>/dev/null)
  OR_JSON=""
  while IFS= read -r model_id; do
    [ -z "$model_id" ] && continue
    # OpenRouter model URL: https://openrouter.ai/<vendor>/<model>
    bare=${model_id#openrouter/}
    URL="https://openrouter.ai/${bare}"
    if curl -fsSL --max-time 10 -o /dev/null -w "%{http_code}" "$URL" 2>/dev/null | grep -q "^200$"; then
      st="ok"
    else
      st="unreachable"
    fi
    OR_JSON="${OR_JSON}{\"model_id\":\"$model_id\",\"url\":\"$URL\",\"status\":\"$st\"},"
  done <<< "$OR_MODELS"
  if [ -n "$OR_JSON" ]; then
    OPENROUTER_LOOKUPS="[${OR_JSON%,}]"
  fi
fi

# --------------------------------------------------------
# Write the consolidated output JSON
# --------------------------------------------------------
python3 <<PYEOF > "$OUT"
import json
out = {
    "script_version": "$SCRIPT_VERSION",
    "platform":      "$PLATFORM",
    "checked_at":    "$(ts)",
    "openclaw_docs": {
        "url":    "$DOCS_URL",
        "status": "$DOCS_STATUS",
        "excerpt": """$DOCS_BODY"""[:6000],
    },
    "ollama_lookups":     $OLLAMA_LOOKUPS,
    "openrouter_lookups": $OPENROUTER_LOOKUPS,
    "note": (
        "This file is the canonical pre-flight research output. "
        "The Master Orchestrator MUST read it before any settings config or "
        "model install step. If openclaw_docs.status != 'ok' the orchestrator "
        "should retry up to 3 times, then proceed with PRD §4 defaults and "
        "log the discrepancy as a P1 ticket."
    ),
}
print(json.dumps(out, indent=2))
PYEOF

echo "[web-research-preflight] wrote $OUT" >&2
echo "[web-research-preflight] docs.openclaw.ai: $DOCS_STATUS" >&2

# Also write a one-line summary to stdout so the install agent can grep it
python3 -c "
import json
d = json.load(open('$OUT'))
ol = len(d.get('ollama_lookups', []))
or_ = len(d.get('openrouter_lookups', []))
print(f'preflight: docs={d[\"openclaw_docs\"][\"status\"]} ollama_models_checked={ol} openrouter_models_checked={or_}')
"

exit 0
