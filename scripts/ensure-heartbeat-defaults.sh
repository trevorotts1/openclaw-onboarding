#!/usr/bin/env bash
# scripts/ensure-heartbeat-defaults.sh
# Set sane heartbeat defaults (6h interval, main-only scope, capped tokens).
#
# IDEMPOTENT + CONDITIONAL: writes ONLY when agents.defaults.heartbeat.every is
# unset OR its current value converts to fewer than 360 minutes (< 6h).  An
# operator who has deliberately dialled up to e.g. "12h" or "1d" is not reset.
#
# Extracted from install.sh Fix D / Fix D2 (v14.24.0) so the same logic can be
# called from both install.sh and the update-skills.sh apply phase.
#
# Environment:
#   OC_JSON   — path to openclaw.json (auto-detected when unset)
#   LOG_FILE  — append warnings here (defaults to /tmp/ensure-heartbeat-defaults.log)

set -euo pipefail

# ---------- resolve openclaw.json ------------------------------------------
OC_JSON="${OC_JSON:-}"
if [ -z "$OC_JSON" ]; then
  if [ -d "/data/.openclaw" ]; then
    OC_JSON="/data/.openclaw/openclaw.json"
  else
    OC_JSON="$HOME/.openclaw/openclaw.json"
  fi
fi

LOG_FILE="${LOG_FILE:-/tmp/ensure-heartbeat-defaults.log}"

# ---------- check whether current value is already >= 6h -------------------
# Returns "1" if we should set (unset or below threshold), "0" if already fine.
_should_set=1
if [ -f "$OC_JSON" ] && command -v python3 >/dev/null 2>&1; then
  _should_set=$(python3 - <<'PYEOF' 2>/dev/null || echo "1"
import json, sys, re, os
oc_json = os.environ.get('OC_JSON', '')
if not oc_json or not os.path.exists(oc_json):
    print(1)   # file missing -> treat as unset
    sys.exit(0)
try:
    with open(oc_json) as f:
        cfg = json.load(f)
    val = cfg.get('agents', {}).get('defaults', {}).get('heartbeat', {}).get('every', '')
    if not val:
        print(1)   # key absent
        sys.exit(0)
    m = re.fullmatch(r'(\d+)(m|h|d)', str(val).strip())
    if not m:
        print(1)   # unparseable -> safer to set
        sys.exit(0)
    n, unit = int(m.group(1)), m.group(2)
    mins = n * (1 if unit == 'm' else 60 if unit == 'h' else 1440)
    print(0 if mins >= 360 else 1)
except Exception:
    print(1)
PYEOF
)
fi

if [ "${_should_set:-1}" = "0" ]; then
  echo "  ✓ Heartbeat already at 6h or longer — no change (ensure-heartbeat-defaults)"
  exit 0
fi

# ---------- set defaults via openclaw CLI ----------------------------------
echo "  Setting sane heartbeat defaults (6h interval, main-only, capped tokens) + per-agent main override..."
if command -v openclaw >/dev/null 2>&1; then
  _hb_ok=1
  openclaw config set agents.defaults.heartbeat.every 6h 2>>"$LOG_FILE" || _hb_ok=0
  openclaw config set agents.defaults.heartbeat.agentsOnly '["main"]' 2>>"$LOG_FILE" || true
  openclaw config set agents.defaults.heartbeat.maxTokens 2000 2>>"$LOG_FILE" || true
  if [ "$_hb_ok" = "1" ]; then
    echo "  ✓ Heartbeat defaults: 6h / main-only / 2000-token cap"
  else
    echo "  ⚠ Could not set heartbeat.every — manual fix: openclaw config set agents.defaults.heartbeat.every 6h" >&2
  fi

  # Fix D2: explicit per-agent override so the main/ceo agent does not fall back
  # to the system default regardless of default:true.
  _hb_main_ok=1
  openclaw config set 'agents.list[main].heartbeat.every' 6h 2>>"$LOG_FILE" || _hb_main_ok=0
  if [ "$_hb_main_ok" = "1" ]; then
    echo "  ✓ Per-agent heartbeat: agents.list[main].heartbeat.every=6h"
  else
    # Fallback: direct Python JSON edit when bracket notation is unsupported.
    if [ -f "$OC_JSON" ]; then
      python3 - <<'PYEOF' 2>>"$LOG_FILE" \
        && echo "  ✓ Per-agent main heartbeat written via Python (Fix D2 fallback)" \
        || echo "  ⚠ Fix D2 fallback: could not write agents.list[main].heartbeat.every" >&2
import json, os, shutil, sys
oc_json = os.environ.get('OC_JSON', '')
if not oc_json or not os.path.exists(oc_json):
    sys.exit(1)
with open(oc_json) as f:
    cfg = json.load(f)
agents_list = cfg.get('agents', {}).get('list', [])
patched = False
for ag in agents_list:
    if isinstance(ag, dict) and ag.get('id') == 'main':
        ag.setdefault('heartbeat', {})['every'] = '6h'
        patched = True
        break
if not patched:
    sys.exit(0)   # no 'main' entry yet -- safe skip
tmp = oc_json + '.tmp'
with open(tmp, 'w') as f:
    json.dump(cfg, f, indent=2)
    f.write('\n')
shutil.move(tmp, oc_json)
PYEOF
    else
      echo "  ⚠ Fix D2: OC_JSON not found — skip per-agent override (manual: openclaw config set 'agents.list[main].heartbeat.every' 6h)" >&2
    fi
  fi
else
  echo "  ⚠ openclaw not on PATH — heartbeat defaults not set; run manually: openclaw config set agents.defaults.heartbeat.every 6h" >&2
fi
