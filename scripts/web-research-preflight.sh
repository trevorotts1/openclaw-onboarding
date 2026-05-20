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
# Detail-extraction helper — scrape a model page body for
# context-window / max-output / pricing hints. Best-effort grep.
# Returns a JSON object string (or {} if nothing found).
# --------------------------------------------------------
extract_details() {
  local body_file="$1"
  [ ! -s "$body_file" ] && { echo "{}"; return; }
  python3 - "$body_file" <<'PYEOF' 2>/dev/null || echo "{}"
import json, re, sys
try:
    body = open(sys.argv[1], encoding='utf-8', errors='ignore').read(200000)
except Exception:
    print("{}"); sys.exit(0)
out = {}
# Context window: look for "context", "ctx", "tokens" near a K/M number
ctx_patterns = [
    r"context\s*(?:length|window|size)?\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*([KMkm])",
    r"(\d+(?:\.\d+)?)\s*([KMkm])\s*(?:token|ctx|context)",
    r"\"context_length\"\s*:\s*(\d+)",
    r"\"max_tokens?\"\s*:\s*(\d+)",
]
for p in ctx_patterns:
    m = re.search(p, body, re.IGNORECASE)
    if m:
        if len(m.groups()) >= 2 and m.group(2):
            n = float(m.group(1))
            unit = m.group(2).upper()
            multiplier = 1000 if unit == "K" else 1_000_000
            out["context_window_tokens"] = int(n * multiplier)
            out["context_window_raw"] = f"{m.group(1)}{unit}"
        else:
            out["context_window_tokens"] = int(m.group(1))
            out["context_window_raw"] = m.group(1)
        break
# Max output (less common): look for "max output", "output tokens"
out_patterns = [
    r"(?:max\s*output|output\s*tokens?)\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*([KMkm])",
    r"(?:max\s*output|output\s*tokens?)\s*[:\-]?\s*(\d+)",
]
for p in out_patterns:
    m = re.search(p, body, re.IGNORECASE)
    if m:
        if len(m.groups()) >= 2 and m.group(2):
            n = float(m.group(1))
            unit = m.group(2).upper()
            mult = 1000 if unit == "K" else 1_000_000
            out["max_output_tokens"] = int(n * mult)
        else:
            out["max_output_tokens"] = int(m.group(1))
        break
# Pricing hints — best-effort (openrouter pages list "$X / 1M input/output")
price = re.search(r'\$?\s*(\d+(?:\.\d+)?)\s*/\s*1M\s*(?:input|in)', body, re.IGNORECASE)
if price:
    out["input_price_per_1m_usd"] = float(price.group(1))
price_out = re.search(r'\$?\s*(\d+(?:\.\d+)?)\s*/\s*1M\s*(?:output|out)', body, re.IGNORECASE)
if price_out:
    out["output_price_per_1m_usd"] = float(price_out.group(1))
print(json.dumps(out))
PYEOF
}

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
    body_tmp=$(mktemp)
    if curl -fsSL --max-time 12 -o "$body_tmp" -w "%{http_code}" "$URL" 2>/dev/null | grep -q "^200$"; then
      st="ok"
      details=$(extract_details "$body_tmp")
    else
      st="unreachable"
      details="{}"
    fi
    rm -f "$body_tmp"
    LOOKUPS_JSON="${LOOKUPS_JSON}{\"model_id\":\"$model_id\",\"url\":\"$URL\",\"status\":\"$st\",\"details\":${details}},"
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
    body_tmp=$(mktemp)
    if curl -fsSL --max-time 12 -o "$body_tmp" -w "%{http_code}" "$URL" 2>/dev/null | grep -q "^200$"; then
      st="ok"
      details=$(extract_details "$body_tmp")
    else
      st="unreachable"
      details="{}"
    fi
    rm -f "$body_tmp"
    OR_JSON="${OR_JSON}{\"model_id\":\"$model_id\",\"url\":\"$URL\",\"status\":\"$st\",\"details\":${details}},"
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
