#!/usr/bin/env bash
# scripts/ensure-heartbeat-defaults.sh
# Set sane heartbeat defaults and keep the box out of the "wake every agent"
# furnace, ONLY on OpenClaw builds that still accept heartbeat config keys.
#
# CAPABILITY GATE (runs before any write). OpenClaw 2026.11.5 retired heartbeat
# configuration: its schema has no agents.defaults.heartbeat and no per-agent
# .heartbeat, so a config carrying either fails validation, every CLI command
# that loads config refuses to run, and the gateway refuses to start until
# `openclaw doctor --fix` (gateway stopped) migrates the keys into heartbeat
# Automations. So this script first asks the installed build (HB_KEYS):
#   accepted : `openclaw config schema` lists agents.defaults.heartbeat (or,
#              with no schema answer, the version is below 2026.11.5)
#   retired  : the schema has no agents.defaults.heartbeat (or the version is
#              2026.11.5 or later)
#   unknown  : neither answered
# retired and unknown WRITE NOTHING and print one capability line. Both probes
# run isolated (home, state dir and config path all pointed at a throwaway
# scratch dir, stdin from /dev/null), never against the live state dir: Big
# Fleet Roll error #25, the same env as oc_validate_isolated() in
# update-skills.sh. No config is put there: neither probe reads one, so the live
# config (and its secrets) is never copied.
#
# Runtime contract on builds that ACCEPT the keys (2026.11.4 and earlier; see
# resolveHeartbeatAgents in openclaw):
#   * If ANY agent in the roster (agents.entries on OpenClaw 2026.9.x, else the
#     legacy agents.list) has a .heartbeat block -> ALLOWLIST mode:
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
#       primary agent (agent with default==true, else the first roster
#       entry) with a cheap
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
#   FLEET_OC_VERSION_OVERRIDE - pins the OpenClaw version for deterministic
#               tests (same variable as apply-fleet-standards.sh). It replaces
#               the detected version; a schema answer still wins.

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
HAVE_OC=0
command -v openclaw >/dev/null 2>&1 && HAVE_OC=1

# ---------- probe the config (single pass) ---------------------------------
# Emits one line, fields separated by US (0x1f) so empty fields are preserved:
#   OK <has_block> <primary_idx> <primary_id> <hb_model> <hb_every> <should_raise> <shape> <has_defaults_hb>
# or "PARSEFAIL" for an existing-but-unparseable config.
# has_block   : 1 if any agent already has a .heartbeat block (allowlist active)
# primary_*   : primary agent (default==true, else index 0); empty if none
# hb_model    : cheap SOVEREIGN model derived from defaults.model.fallbacks
#               (ollama/ollama-cloud + cheap tier only; empty if none derivable)
# hb_every    : interval to write on the per-agent block (>=6h; current if the
#               operator already dialled up, else "6h")
# should_raise: 1 if agents.defaults.heartbeat.every is unset or < 6h
# shape       : "entries" (agents.entries, keyed by id -- OpenClaw 2026.9.x) or
#               "list" (legacy agents.list[]). Writes go to the SAME shape:
#               creating agents.list on an entries box is `Unrecognized key`.
# has_defaults_hb: 1 if agents.defaults.heartbeat is present
PROBE=""
if [ "$HAVE_PY" = "1" ]; then
  PROBE=$(OC_JSON="$OC_JSON" python3 - <<'PYEOF' 2>/dev/null
import json, os, re, sys

def emit(*fields):
    sys.stdout.write("\x1f".join(str(f) for f in fields) + "\n")

oc = os.environ.get("OC_JSON", "")
if not oc or not os.path.exists(oc):
    # No config yet: treat as fresh (no block, no primary, raise to 6h).
    emit("OK", "0", "", "", "", "6h", "1", "list", "0")
    sys.exit(0)
try:
    with open(oc) as fh:
        cfg = json.load(fh)
except Exception:
    emit("PARSEFAIL")
    sys.exit(0)

agents = cfg.get("agents", {})
agents = agents if isinstance(agents, dict) else {}
# entries wins when present (same precedence as materialize-dept-agents.sh);
# in entries mode the id is the KEY, never a field of the entry.
entries = agents.get("entries")
if isinstance(entries, dict) and entries:
    shape = "entries"
    roster = [(str(k), v) for k, v in entries.items()]
else:
    shape = "list"
    lst = agents.get("list", [])
    lst = lst if isinstance(lst, list) else []
    roster = [(str(a.get("id", "") or "") if isinstance(a, dict) else "", a) for a in lst]
defaults = agents.get("defaults", {})
defaults = defaults if isinstance(defaults, dict) else {}
has_defaults_hb = 0 if defaults.get("heartbeat") is None else 1

# Allowlist mode active? (matches runtime hasExplicitHeartbeatAgents: any
# agent with a non-null heartbeat value.)
has_block = 1 if any(
    isinstance(a, dict) and a.get("heartbeat") is not None for _, a in roster
) else 0

# Primary agent: first with truthy `default`, else the first roster entry
# (matches runtime resolveDefaultAgentId).
p_idx = ""
p_id = ""
if roster:
    sel = None
    for i, (_, a) in enumerate(roster):
        if isinstance(a, dict) and a.get("default"):
            sel = i
            break
    if sel is None:
        sel = 0
    if isinstance(roster[sel][1], dict):
        p_idx = str(sel)
        p_id = roster[sel][0]

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

emit("OK", has_block, p_idx, p_id, hb_model, hb_every, should_raise, shape, has_defaults_hb)
PYEOF
) || true
fi

STATUS=""; HAS_BLOCK=""; PRIMARY_IDX=""; PRIMARY_ID=""; HB_MODEL=""; HB_EVERY="6h"; SHOULD_RAISE="1"; SHAPE="list"; HAS_DEFAULTS_HB=""
if [ -n "$PROBE" ]; then
  IFS=$'\x1f' read -r STATUS HAS_BLOCK PRIMARY_IDX PRIMARY_ID HB_MODEL HB_EVERY SHOULD_RAISE SHAPE HAS_DEFAULTS_HB <<<"$PROBE" || true
fi
# CLI path of the primary agent in the box's OWN roster shape.
if [ "$SHAPE" = "entries" ]; then
  PRIMARY_PATH="agents.entries.$PRIMARY_ID"
else
  PRIMARY_PATH="agents.list[$PRIMARY_IDX]"
fi

if [ "$STATUS" = "PARSEFAIL" ]; then
  echo "  ⚠ openclaw.json is unparseable — skipping heartbeat defaults (safe-skip)" >&2
  exit 0
fi

# ---------- capability gate: does this build accept heartbeat keys? -------
# Nothing below this block writes unless HB_KEYS=accepted.
HB_RETIRED_VERSION="2026.11.5"
HB_KEYS="unknown"; HB_BASIS=""; OC_VERSION=""; _hb_scratch=""

# _ver_ge A B -> 0 if version A >= version B (numeric YYYY.M.P compare).
_ver_ge() {
  printf '%s\n%s\n' "$2" "$1" | sort -t. -k1,1n -k2,2n -k3,3n -C
}

# Run openclaw with home, state dir and config path all in the scratch dir.
_oc_iso() {
  OPENCLAW_HOME="$_hb_scratch" OPENCLAW_STATE_DIR="$_hb_scratch" \
    OPENCLAW_CONFIG_PATH="$_hb_scratch/openclaw.json" OPENCLAW_SKIP_UPDATE_CHECK=1 \
    openclaw "$@" </dev/null
}

if [ "$HAVE_OC" = "1" ]; then
  _hb_scratch="$(mktemp -d "${TMPDIR:-/tmp}/hb-capability.XXXXXX" 2>/dev/null)" || _hb_scratch=""
fi
if [ -n "$_hb_scratch" ]; then
  # (a) the build's own schema: is agents.defaults.heartbeat still a key?
  if [ "$HAVE_PY" = "1" ] && _oc_iso config schema > "$_hb_scratch/schema.json" 2>>"$LOG_FILE"; then
    python3 -I - "$_hb_scratch/schema.json" > "$_hb_scratch/verdict" 2>>"$LOG_FILE" <<'PYEOF' || true
import json, sys

# ponytail: inline "properties" only, no $ref following. A $ref'd schema prints
# nothing here and the version check decides; follow $ref if a build ever needs it.
def props(node):
    found = node.get("properties") if isinstance(node, dict) else None
    return found if isinstance(found, dict) else None

try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        raw = fh.read()
    doc = json.loads(raw[raw.index("{"):])  # skip any banner printed before the JSON
except Exception:
    sys.exit(0)  # no answer: the version check decides
agents = (props(doc) or {}).get("agents")
defaults = props((props(agents) or {}).get("defaults"))
if defaults is not None:
    print("accepted" if "heartbeat" in defaults else "retired")
PYEOF
    _hb_v="$(cat "$_hb_scratch/verdict" 2>/dev/null || true)"
    case "$_hb_v" in
      accepted|retired) HB_KEYS="$_hb_v"; HB_BASIS="openclaw config schema" ;;
    esac
  fi
  # (b) no schema answer: read the version. Scan the FULL output, never only
  # line 1 (a startup banner can come first; apply-fleet-standards.sh 2026-11-06).
  if [ "$HB_KEYS" = "unknown" ]; then
    _hb_out="$(_oc_iso --version 2>/dev/null | tr -d '\r' || true)"
    OC_VERSION="$(printf '%s\n' "$_hb_out" | grep -oE '20[0-9]{2}\.[0-9]+\.[0-9]+' | head -n1 || true)"
    if [ -z "$OC_VERSION" ]; then
      _hb_out="$(_oc_iso --version 2>&1 | tr -d '\r' || true)"
      OC_VERSION="$(printf '%s\n' "$_hb_out" | grep -oE '20[0-9]{2}\.[0-9]+\.[0-9]+' | head -n1 || true)"
    fi
  fi
  rm -rf "$_hb_scratch"
fi
# With no openclaw CLI on PATH the only version source is the override, so a
# CLI-less host stays "unknown" and writes nothing. Never fall back to
# meta.lastTouchedVersion: it is the build that last WROTE the config and can
# lag the installed binary (an upgraded box would read as "accepted").
OC_VERSION="$(printf '%s\n' "${FLEET_OC_VERSION_OVERRIDE:-$OC_VERSION}" | grep -oE '20[0-9]{2}\.[0-9]+\.[0-9]+' | head -n1 || true)"
if [ "$HB_KEYS" = "unknown" ] && [ -n "$OC_VERSION" ]; then
  if _ver_ge "$OC_VERSION" "$HB_RETIRED_VERSION"; then HB_KEYS="retired"; else HB_KEYS="accepted"; fi
  HB_BASIS="OpenClaw $OC_VERSION, cutoff $HB_RETIRED_VERSION"
fi

case "$HB_KEYS" in
  accepted)
    echo "  ✓ Heartbeat config keys accepted by this OpenClaw build ($HB_BASIS)"
    ;;
  retired)
    if [ "$HAS_BLOCK" = "1" ] || [ "$HAS_DEFAULTS_HB" = "1" ]; then
      echo "  ⚠ Legacy heartbeat config present, and this OpenClaw build refuses it ($HB_BASIS). Nothing written. Run: openclaw doctor --fix (with the gateway stopped)" >&2
    else
      echo "  ✓ Heartbeat config is retired on this OpenClaw build ($HB_BASIS): heartbeat monitors are Automations (openclaw automations list --all). Nothing to do, nothing written"
    fi
    exit 0
    ;;
  *)
    echo "  ⚠ Heartbeat capability unknown (no config schema answer, no readable OpenClaw version): nothing written, box left as is" >&2
    exit 0
    ;;
esac

echo "  Ensuring heartbeat furnace guard (allowlist on primary + cheap sovereign model) and 6h interval default..."

# ---------- (B) per-agent block: keep the box in allowlist mode ------------
if [ "$HAS_BLOCK" = "1" ]; then
  echo "  ✓ An agent already has an explicit heartbeat block — allowlist mode active, no per-agent change"
elif [ -n "$PRIMARY_IDX" ] && [ -n "$PRIMARY_ID" ]; then
  echo "  Adding per-agent heartbeat block to primary agent '$PRIMARY_ID' (index $PRIMARY_IDX)..."
  _added=0
  if command -v openclaw >/dev/null 2>&1; then
    # list: CLI array access requires a numeric index (id-bracket is
    # unsupported). entries: the id is the key.
    if openclaw config set "$PRIMARY_PATH.heartbeat.every" "$HB_EVERY" 2>>"$LOG_FILE"; then
      _added=1
      if [ -n "$HB_MODEL" ]; then
        openclaw config set "$PRIMARY_PATH.heartbeat.model" "$HB_MODEL" 2>>"$LOG_FILE" || true
        openclaw config set "agents.defaults.heartbeat.model" "$HB_MODEL" 2>>"$LOG_FILE" || true
      fi
    fi
  fi
  if [ "$_added" = "1" ]; then
    if [ -n "$HB_MODEL" ]; then
      echo "  ✓ Per-agent heartbeat: $PRIMARY_PATH ($PRIMARY_ID).heartbeat={every:$HB_EVERY, model:$HB_MODEL}"
    else
      echo "  ✓ Per-agent heartbeat: $PRIMARY_PATH ($PRIMARY_ID).heartbeat.every=$HB_EVERY (no cheap sovereign model derivable — model pin skipped)"
    fi
  elif [ "$HAVE_OC" = "1" ]; then
    # The CLI is here and REFUSED the key: never write a value the build
    # rejected. (A Python fallback after a refusal is what rewrote retired keys
    # on OpenClaw 2026.11.5 and took the gateway down on every roll.)
    echo "  ⚠ openclaw refused the per-agent heartbeat block for '$PRIMARY_ID': nothing written (details: $LOG_FILE)" >&2
  elif [ -f "$OC_JSON" ] && [ "$HAVE_PY" = "1" ]; then
    # Fallback ONLY when the openclaw CLI is absent (HB_KEYS=accepted then came
    # from FLEET_OC_VERSION_OVERRIDE). Direct Python JSON edit: resolves the
    # primary itself, never overwrites an existing block, writes a temp file in
    # the same dir, re-reads it, keeps the file's mode and owner, then swaps it
    # in atomically. Any failure leaves openclaw.json untouched.
    # ponytail: no schema validation here; like safe_json_edit in
    # update-skills.sh, validation needs the CLI, so a CLI-less edit is only
    # checked for well-formed JSON. Add an isolated validate if that ever changes.
    OC_JSON="$OC_JSON" HB_EVERY="$HB_EVERY" HB_MODEL="$HB_MODEL" python3 - <<'PYEOF' 2>>"$LOG_FILE" \
      && echo "  ✓ Per-agent heartbeat block written via Python fallback (openclaw CLI absent)" \
      || echo "  ⚠ Fallback: could not write per-agent heartbeat block (openclaw.json unchanged)" >&2
import json, os, sys, tempfile

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
# Same shape rule as the probe: agents.entries (keyed by id) wins, else the
# legacy agents.list[]. Never create the other shape.
entries = agents.get("entries")
if isinstance(entries, dict) and entries:
    lst = list(entries.values())
else:
    lst = agents.get("list", [])
if not isinstance(lst, list) or not lst:
    sys.exit(0)  # no agents -> safe skip

# Never overwrite an existing deliberate block; if any exists we are already in
# allowlist mode.
if any(isinstance(a, dict) and a.get("heartbeat") is not None for a in lst):
    sys.exit(0)

# Primary: first with truthy `default`, else the first roster entry.
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
lst[sel]["heartbeat"] = block  # live dict inside cfg in both shapes

if hb_model:
    defaults = agents.setdefault("defaults", {})
    if isinstance(defaults, dict):
        hbd = defaults.setdefault("heartbeat", {})
        if isinstance(hbd, dict):
            hbd["model"] = hb_model

st = os.stat(oc)
fd, tmp = tempfile.mkstemp(prefix=".hb-fallback.", dir=os.path.dirname(os.path.abspath(oc)))
try:
    with os.fdopen(fd, "w") as fh:
        json.dump(cfg, fh, indent=2)
        fh.write("\n")
    with open(tmp) as fh:
        if json.load(fh) != cfg:
            raise ValueError("round-trip mismatch")
    os.chmod(tmp, st.st_mode & 0o7777)
    if os.geteuid() == 0:
        os.chown(tmp, st.st_uid, st.st_gid)
    os.replace(tmp, oc)
except BaseException:
    try:
        os.unlink(tmp)
    except OSError:
        pass
    raise
PYEOF
  else
    echo "  ⚠ Cannot add per-agent heartbeat block (no openclaw CLI / no python3) — manual: openclaw config set '$PRIMARY_PATH.heartbeat.every' $HB_EVERY" >&2
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
