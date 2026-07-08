#!/usr/bin/env bash
# scripts/ensure-heartbeat-defaults.sh
# Set sane heartbeat defaults and keep the box out of the "wake every agent"
# furnace.
#
# Runtime contract (see resolveHeartbeatAgents in openclaw):
#   * If ANY agent in agents.list has a .heartbeat block -> ALLOWLIST mode:
#     only those agents heartbeat.  (safe)
#   * Else if agents.defaults.heartbeat exists -> EVERY agent heartbeats
#     (FURNACE), at agents.defaults.heartbeat.every or a 30m fallback.
#   * Else -> only the default agent heartbeats.
# So the durable furnace guard is: whenever NO agent has an explicit .heartbeat
# block, add ONE to the primary agent.  That flips the box to allowlist mode
# regardless of the defaults.heartbeat.every value.
#
# This script therefore does two INDEPENDENT things:
#   (B) Per-agent block  — if no agent has a .heartbeat block, add one to the
#       primary agent (agent with default==true, else index 0) with a cheap
#       SOVEREIGN heartbeat model derived from the box's own provider config.
#       Runs REGARDLESS of the current interval (decoupled from the gate below).
#   (A) Interval default  — raise agents.defaults.heartbeat.every to 6h ONLY
#       when it is unset or converts to < 6h.  An operator who deliberately
#       dialled up to e.g. "12h"/"1d" is never reset.
#
# Idempotent + safe: if any agent already has a heartbeat block the per-agent
# step is a no-op (an existing deliberate block is never overwritten); an
# unparseable config is left untouched.
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

HAVE_PY=0
command -v python3 >/dev/null 2>&1 && HAVE_PY=1

# ---------- probe the config (single pass) ---------------------------------
# Emits one line, fields separated by US (0x1f) so empty fields are preserved:
#   OK <has_block> <primary_idx> <primary_id> <hb_model> <hb_every> <should_raise>
# or "PARSEFAIL" for an existing-but-unparseable config.
# has_block   : 1 if any agent already has a .heartbeat block (allowlist active)
# primary_*   : primary agent (default==true, else index 0); empty if none
# hb_model    : cheap SOVEREIGN model derived from defaults.model.fallbacks
#               (ollama/ollama-cloud + cheap tier only; empty if none derivable)
# hb_every    : interval to write on the per-agent block (>=6h; current if the
#               operator already dialled up, else "6h")
# should_raise: 1 if agents.defaults.heartbeat.every is unset or < 6h
PROBE=""
if [ "$HAVE_PY" = "1" ]; then
  PROBE=$(OC_JSON="$OC_JSON" python3 - <<'PYEOF' 2>/dev/null
import json, os, re, sys

def emit(*fields):
    sys.stdout.write("\x1f".join(str(f) for f in fields) + "\n")

oc = os.environ.get("OC_JSON", "")
if not oc or not os.path.exists(oc):
    # No config yet: treat as fresh (no block, no primary, raise to 6h).
    emit("OK", "0", "", "", "", "6h", "1")
    sys.exit(0)
try:
    with open(oc) as fh:
        cfg = json.load(fh)
except Exception:
    emit("PARSEFAIL")
    sys.exit(0)

agents = cfg.get("agents", {})
agents = agents if isinstance(agents, dict) else {}
lst = agents.get("list", [])
lst = lst if isinstance(lst, list) else []
defaults = agents.get("defaults", {})
defaults = defaults if isinstance(defaults, dict) else {}

# Allowlist mode active? (matches runtime hasExplicitHeartbeatAgents: any
# agent with a non-null heartbeat value.)
has_block = 1 if any(
    isinstance(a, dict) and a.get("heartbeat") is not None for a in lst
) else 0

# Primary agent: first with truthy `default`, else index 0 (matches runtime
# resolveDefaultAgentId).
p_idx = ""
p_id = ""
if lst:
    sel = None
    for i, a in enumerate(lst):
        if isinstance(a, dict) and a.get("default"):
            sel = i
            break
    if sel is None:
        sel = 0
    if isinstance(lst[sel], dict):
        p_idx = str(sel)
        p_id = str(lst[sel].get("id", "") or "")

# Interval: should we raise, and what interval belongs on the per-agent block?
hb = defaults.get("heartbeat", {})
val = hb.get("every", "") if isinstance(hb, dict) else ""
val = str(val).strip() if val else ""
should_raise = "1"
hb_every = "6h"
m = re.fullmatch(r"(\d+)(m|h|d)", val) if val else None
if m:
    n, unit = int(m.group(1)), m.group(2)
    mins = n * (1 if unit == "m" else 60 if unit == "h" else 1440)
    if mins >= 360:
        should_raise = "0"
        hb_every = val  # honour a deliberate >= 6h dial-up

# Cheap SOVEREIGN model from the box's own fallbacks. Never introduce a
# paid/Anthropic provider; if nothing cheap+sovereign is derivable, leave empty
# so the caller safely skips the model pin.
hb_model = ""
md = defaults.get("model")
fbs = []
if isinstance(md, dict) and isinstance(md.get("fallbacks"), list):
    fbs = [x for x in md["fallbacks"] if isinstance(x, str) and x.strip()]
if fbs:
    SOVEREIGN = ("ollama", "ollama-cloud")
    PAID = ("anthropic", "claude", "openai", "gpt-", "azure")
    CHEAP = ("flash", "mini", "lite", "small", "nano", "air", "free", "haiku")
    cands = []
    for mm in fbs:
        ml = mm.lower().strip()
        prov = ml.split("/", 1)[0]
        if prov not in SOVEREIGN:
            continue
        if any(tok in ml for tok in PAID):
            continue
        cands.append(mm.strip())
    cheap = [c for c in cands if any(k in c.lower() for k in CHEAP)]
    if cheap:
        hb_model = cheap[-1]

emit("OK", has_block, p_idx, p_id, hb_model, hb_every, should_raise)
PYEOF
) || true
fi

STATUS=""; HAS_BLOCK=""; PRIMARY_IDX=""; PRIMARY_ID=""; HB_MODEL=""; HB_EVERY="6h"; SHOULD_RAISE="1"
if [ -n "$PROBE" ]; then
  IFS=$'\x1f' read -r STATUS HAS_BLOCK PRIMARY_IDX PRIMARY_ID HB_MODEL HB_EVERY SHOULD_RAISE <<<"$PROBE" || true
fi

if [ "$STATUS" = "PARSEFAIL" ]; then
  echo "  ⚠ openclaw.json is unparseable — skipping heartbeat defaults (safe-skip)" >&2
  exit 0
fi

echo "  Ensuring heartbeat furnace guard (allowlist on primary + cheap sovereign model) and 6h interval default..."

# ---------- (B) per-agent block: keep the box in allowlist mode ------------
if [ "$HAS_BLOCK" = "1" ]; then
  echo "  ✓ An agent already has an explicit heartbeat block — allowlist mode active, no per-agent change"
elif [ -n "$PRIMARY_IDX" ] && [ -n "$PRIMARY_ID" ]; then
  echo "  Adding per-agent heartbeat block to primary agent '$PRIMARY_ID' (index $PRIMARY_IDX)..."
  _added=0
  if command -v openclaw >/dev/null 2>&1; then
    # CLI array access requires a numeric index (id-bracket is unsupported).
    if openclaw config set "agents.list[$PRIMARY_IDX].heartbeat.every" "$HB_EVERY" 2>>"$LOG_FILE"; then
      _added=1
      if [ -n "$HB_MODEL" ]; then
        openclaw config set "agents.list[$PRIMARY_IDX].heartbeat.model" "$HB_MODEL" 2>>"$LOG_FILE" || true
        openclaw config set "agents.defaults.heartbeat.model" "$HB_MODEL" 2>>"$LOG_FILE" || true
      fi
    fi
  fi
  if [ "$_added" = "1" ]; then
    if [ -n "$HB_MODEL" ]; then
      echo "  ✓ Per-agent heartbeat: agents.list[$PRIMARY_ID].heartbeat={every:$HB_EVERY, model:$HB_MODEL}"
    else
      echo "  ✓ Per-agent heartbeat: agents.list[$PRIMARY_ID].heartbeat.every=$HB_EVERY (no cheap sovereign model derivable — model pin skipped)"
    fi
  elif [ -f "$OC_JSON" ] && [ "$HAVE_PY" = "1" ]; then
    # Fallback: direct Python JSON edit (resolves the primary itself so it never
    # depends on a hardcoded id; never overwrites an existing block).
    OC_JSON="$OC_JSON" HB_EVERY="$HB_EVERY" HB_MODEL="$HB_MODEL" python3 - <<'PYEOF' 2>>"$LOG_FILE" \
      && echo "  ✓ Per-agent heartbeat block written via Python fallback" \
      || echo "  ⚠ Fallback: could not write per-agent heartbeat block" >&2
import json, os, shutil, sys

oc = os.environ.get("OC_JSON", "")
if not oc or not os.path.exists(oc):
    sys.exit(1)
hb_every = os.environ.get("HB_EVERY", "6h") or "6h"
hb_model = os.environ.get("HB_MODEL", "") or ""
with open(oc) as fh:
    cfg = json.load(fh)

agents = cfg.setdefault("agents", {})
if not isinstance(agents, dict):
    sys.exit(1)
lst = agents.get("list", [])
if not isinstance(lst, list) or not lst:
    sys.exit(0)  # no agents -> safe skip

# Never overwrite an existing deliberate block; if any exists we are already in
# allowlist mode.
if any(isinstance(a, dict) and a.get("heartbeat") is not None for a in lst):
    sys.exit(0)

# Primary: first with truthy `default`, else index 0.
sel = None
for i, a in enumerate(lst):
    if isinstance(a, dict) and a.get("default"):
        sel = i
        break
if sel is None:
    sel = 0
if not isinstance(lst[sel], dict):
    sys.exit(0)

block = {"every": hb_every}
if hb_model:
    block["model"] = hb_model
lst[sel]["heartbeat"] = block

if hb_model:
    defaults = agents.setdefault("defaults", {})
    if isinstance(defaults, dict):
        hbd = defaults.setdefault("heartbeat", {})
        if isinstance(hbd, dict):
            hbd["model"] = hb_model

tmp = oc + ".tmp"
with open(tmp, "w") as fh:
    json.dump(cfg, fh, indent=2)
    fh.write("\n")
shutil.move(tmp, oc)
PYEOF
  else
    echo "  ⚠ Cannot add per-agent heartbeat block (no openclaw CLI / no python3) — manual: openclaw config set 'agents.list[$PRIMARY_IDX].heartbeat.every' $HB_EVERY" >&2
  fi
else
  echo "  ⚠ Could not resolve a primary agent — per-agent heartbeat block not added (safe-skip)" >&2
fi

# ---------- (A) interval default: raise to 6h only when too low ------------
if [ "$SHOULD_RAISE" = "1" ]; then
  if command -v openclaw >/dev/null 2>&1; then
    _iv=1
    openclaw config set agents.defaults.heartbeat.every 6h 2>>"$LOG_FILE" || _iv=0
    openclaw config set agents.defaults.heartbeat.maxTokens 2000 2>>"$LOG_FILE" || true
    if [ "$_iv" = "1" ]; then
      echo "  ✓ Heartbeat interval default: every=6h / 2000-token cap"
    else
      echo "  ⚠ Could not set agents.defaults.heartbeat.every — manual: openclaw config set agents.defaults.heartbeat.every 6h" >&2
    fi
  else
    echo "  ⚠ openclaw not on PATH — interval default not set; run: openclaw config set agents.defaults.heartbeat.every 6h" >&2
  fi
else
  echo "  ✓ Heartbeat interval already >= 6h (agents.defaults.heartbeat.every=$HB_EVERY) — not lowered"
fi
