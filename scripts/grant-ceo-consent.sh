#!/usr/bin/env bash
# grant-ceo-consent.sh — Hardened owner-consent writer (the ONLY write path).
#
# Goal doc line 91: "Consent-flag write path must be hardened." This is the SOLE
# writer of the single shared consent sidecar that the PreToolUse hook, the
# Layer-1 tool-deny carve-out, and the Layer-4 QC state-gate all read.
#
# It is invoked BY THE OWNER (console or via an owner-only Telegram/ops path) —
# never by the CEO agent. The CEO agent's own toolset cannot reach this:
#   • the sidecar lives outside any agent-writable workspace, and
#   • the agent's `write`/`edit`/`exec` are denied by Layer 1, and
#   • this script REQUIRES the owner's literal consent phrase as confirmation.
#
# Usage:
#   bash grant-ceo-consent.sh <scope> --phrase "<owner consent text>"
#   bash grant-ceo-consent.sh --revoke
#
#   <scope> is one of:
#     task:<uuid>      consent for exactly one task id
#     session:<id>     consent for one CEO session id
#     until:<iso8601>  consent until an instant, e.g. until:2026-06-20T18:00:00Z
#     global           consent for any direct work (widest — time-box manually)
#
# The --phrase is REQUIRED for a grant and must be non-trivial (>= 4 chars). It
# is stored verbatim in the record as the audit trail of what the owner said.
#
# THE TOOL CARVE-OUT (GOAL-5 HARD CONSTRAINT — never strip the CEO outright):
#   OpenClaw tool policy is RESTRICT-ONLY — a deny cannot be un-denied in-session.
#   So consent alone (the sidecar) is not enough to let the CEO actually DO the
#   work: Layer-1's hard deny would still block it. This script therefore also
#   performs a CONFIG ENTRY SWAP on grant — it lifts the production-tool deny on
#   the CEO agent in openclaw.json and reloads the gateway — and REVERTS the swap
#   (restores the GATED posture) on --revoke. Pass --no-config to write/clear the
#   sidecar ONLY (e.g. for the Layer-3 QC gate on a box you can't reload here).
#
# Exit codes: 0 ok · 1 usage/validation error · 2 write error

set -euo pipefail

_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_ONBOARDING_DIR="$(cd "$_SCRIPT_DIR/.." && pwd)"

# Pull in the SAME path resolver the reader uses, so writer and reader agree.
_CONSENT_LIB=""
for _cand in \
  "$_ONBOARDING_DIR/hooks/lib-ceo-consent.sh" \
  "/data/.openclaw/hooks/lib-ceo-consent.sh" \
  "$HOME/.openclaw/hooks/lib-ceo-consent.sh"; do
  [ -f "$_cand" ] && _CONSENT_LIB="$_cand" && break
done
if [ -z "$_CONSENT_LIB" ]; then
  echo "[grant-ceo-consent] ERROR: lib-ceo-consent.sh not found — install the hooks first" >&2
  exit 1
fi
# shellcheck source=/dev/null
. "$_CONSENT_LIB"

# Pull in the canonical CEO tool-gate state (the GATED `tools` block to RESTORE
# on revoke). Same source of truth verify-routing.sh G7 asserts against.
_GATE_LIB=""
for _cand in \
  "$_ONBOARDING_DIR/hooks/lib-ceo-tool-gate.sh" \
  "/data/.openclaw/hooks/lib-ceo-tool-gate.sh" \
  "$HOME/.openclaw/hooks/lib-ceo-tool-gate.sh"; do
  [ -f "$_cand" ] && _GATE_LIB="$_cand" && break
done
if [ -n "$_GATE_LIB" ]; then
  # shellcheck source=/dev/null
  . "$_GATE_LIB"
fi

_usage() {
  cat >&2 <<'EOF'
Usage:
  grant-ceo-consent.sh <scope> --phrase "<owner consent text>" [--no-config]
  grant-ceo-consent.sh --revoke [--no-config]

  <scope>:     task:<uuid> | session:<id> | until:<iso8601> | global
  --no-config: write/clear the consent sidecar ONLY; do NOT swap the CEO agent's
               tool policy in openclaw.json or reload the gateway. Use when the
               box can't be reloaded from this context (the Layer-3 QC gate still
               honors the sidecar).
EOF
}

REVOKE=0
SCOPE=""
PHRASE=""
NO_CONFIG=0
while [ $# -gt 0 ]; do
  case "$1" in
    --revoke) REVOKE=1; shift ;;
    --phrase) PHRASE="${2:-}"; shift 2 ;;
    --no-config) NO_CONFIG=1; shift ;;
    -h|--help) _usage; exit 0 ;;
    task:*|session:*|until:*|global) SCOPE="$1"; shift ;;
    *) echo "[grant-ceo-consent] ERROR: unrecognized arg: $1" >&2; _usage; exit 1 ;;
  esac
done

# ─── CEO tool-policy swap (the carve-out that actually re-grants abilities) ─────
# Locate openclaw.json the same way the rest of the onboarding does.
_oc_config_path() {
  if [ -f /data/.openclaw/openclaw.json ]; then
    printf '%s\n' "/data/.openclaw/openclaw.json"
  elif [ -f "$HOME/.openclaw/openclaw.json" ]; then
    printf '%s\n' "$HOME/.openclaw/openclaw.json"
  else
    return 1
  fi
}

# Reload the gateway so a tool-policy change takes effect. Best-effort + quiet:
# the master agent may restart its own Mac gateway; on VPS this is a no-op here
# and the operator reloads during the roll.
_reload_gateway() {
  if command -v openclaw >/dev/null 2>&1; then
    openclaw gateway reload >/dev/null 2>&1 \
      || openclaw config reload >/dev/null 2>&1 \
      || true
  fi
}

# swap_ceo_tools <mode>   mode = "consented" (lift denies) | "gated" (restore)
# Rewrites ONLY the CEO/main agent's `tools` block. Never touches other agents.
swap_ceo_tools() {
  local _mode="$1"
  local _cfg
  _cfg="$(_oc_config_path)" || {
    echo "[grant-ceo-consent] WARN: openclaw.json not found — sidecar written, but the CEO tool-policy was NOT swapped. Re-run on the box, or pass --no-config to silence." >&2
    return 0
  }

  local _gated_json=""
  if command -v ceo_gate_tools >/dev/null 2>&1; then
    _gated_json="$(ceo_gate_tools)"
  elif [ "$_mode" = "gated" ]; then
    echo "[grant-ceo-consent] WARN: lib-ceo-tool-gate.sh not found and no stashed backup — cannot RESTORE the gate automatically. Re-run apply-routing-fix.sh (Layer 5) to re-gate the CEO." >&2
  fi

  # The gated `tools` block is stashed in a SIDECAR (next to the consent file),
  # NOT inside openclaw.json — the strict AgentEntrySchema would reject an
  # unknown key on the agent entry and fail config validate.
  local _gate_backup="${STATE_DIR}/ceo-tools-gated.bak.json"

  local _bak
  _bak="${_cfg}.bak-ceo-consent-$(date +%Y%m%d%H%M%S)"
  cp "$_cfg" "$_bak"

  MODE="$_mode" GATED_JSON="$_gated_json" GATE_BACKUP="$_gate_backup" python3 - "$_cfg" <<'PYEOF'
import json, os, sys
from pathlib import Path

mode = os.environ["MODE"]
gated_json = os.environ.get("GATED_JSON", "")
gate_backup = Path(os.environ["GATE_BACKUP"])
cfg_path = Path(sys.argv[1])
cfg = json.loads(cfg_path.read_text())
agents = cfg.get("agents", {}).get("list", []) or []

# v16.1.3 SELF-HEAL — sessions/agentToAgent are ROOT `tools` keys, NEVER per-agent
# (AgentEntry.tools is additionalProperties:false and REJECTS them → config
# validate fails). On both the consent swap and the revoke restore, strip any
# such keys from the CEO's per-agent tools block and migrate the value up to ROOT
# `tools` so a grant/revoke cycle on a previously-corrupted box never re-writes
# the schema-invalid keys. Idempotent.
def _heal_routing_keys(_cfg, _ceo):
    _rt = _cfg.setdefault("tools", {})
    if not isinstance(_rt, dict):
        _rt = {}
        _cfg["tools"] = _rt
    _t = _ceo.get("tools")
    if not isinstance(_t, dict):
        return
    for _k in ("sessions", "agentToAgent"):
        if _k in _t:
            if _k not in _rt and isinstance(_t[_k], (dict, list)):
                _rt[_k] = _t[_k]
            del _t[_k]

CEO_IDS = ("main", "dept-ceo", "ceo", "master-orchestrator", "dept-master-orchestrator")
ceo = None
for ag in agents:
    if isinstance(ag, dict) and ag.get("id") == "main":
        ceo = ag; break
if ceo is None:
    for ag in agents:
        if isinstance(ag, dict) and ag.get("default") is True:
            ceo = ag; break
if ceo is None:
    for ag in agents:
        if isinstance(ag, dict) and ag.get("id") in CEO_IDS:
            ceo = ag; break
if ceo is None:
    print("NO_CEO"); sys.exit(0)

ceo_id = ceo.get("id", "<unknown>")

if mode == "consented":
    # Lift the production-tool gate: drop the deny + byProvider so the CEO can
    # do the work directly. Keep skills:[] untouched (the deck skill stays off;
    # owner-direct production goes through the now-allowed built-in tools).
    tools = ceo.get("tools")
    if isinstance(tools, dict):
        # Stash the EXACT gated block to the sidecar so revoke restores precisely
        # what was there, even if this box had extra denies beyond the canonical.
        try:
            gate_backup.parent.mkdir(parents=True, exist_ok=True)
            gate_backup.write_text(json.dumps(tools, indent=2) + "\n")
        except Exception:
            pass
        tools = dict(tools)
        tools.pop("deny", None)
        tools.pop("byProvider", None)
        # Drop allow too so the agent gets its profile/default toolset back.
        tools.pop("allow", None)
        if tools:
            ceo["tools"] = tools
        else:
            ceo.pop("tools", None)
    print(f"CONSENTED:{ceo_id}")
else:  # gated
    # Restore the GATED posture. Prefer the exact stashed sidecar block from a
    # prior grant; else fall back to the canonical lib JSON.
    restored = None
    try:
        if gate_backup.exists():
            restored = json.loads(gate_backup.read_text())
    except Exception:
        restored = None
    if not isinstance(restored, dict):
        try:
            restored = json.loads(gated_json) if gated_json else None
        except Exception:
            restored = None
    if isinstance(restored, dict):
        ceo["tools"] = restored
        try:
            if gate_backup.exists():
                gate_backup.unlink()
        except Exception:
            pass
        print(f"GATED:{ceo_id}")
    else:
        print(f"GATE_RESTORE_FAILED:{ceo_id}")
        sys.exit(0)

# v16.1.3: keep the per-agent block schema-clean and routing tools on root.
_heal_routing_keys(cfg, ceo)

cfg_path.write_text(json.dumps(cfg, indent=2) + "\n")
PYEOF

  # Validate; roll back the swap (not the sidecar) if the config is now invalid.
  if command -v openclaw >/dev/null 2>&1; then
    if ! openclaw config validate >/dev/null 2>&1; then
      echo "[grant-ceo-consent] ERROR: openclaw config invalid after CEO tool swap — rolling back config to $_bak (sidecar unchanged)" >&2
      cp "$_bak" "$_cfg"
      return 2
    fi
  fi
  _reload_gateway
  return 0
}

CONSENT_FILE="$(ceo_consent_file)"
STATE_DIR="$(dirname "$CONSENT_FILE")"

# ─── Revoke ───────────────────────────────────────────────────────────────────
if [ "$REVOKE" = "1" ]; then
  if [ -f "$CONSENT_FILE" ]; then
    rm -f "$CONSENT_FILE"
    echo "[grant-ceo-consent] consent REVOKED — removed $CONSENT_FILE"
  else
    echo "[grant-ceo-consent] no consent record present ($CONSENT_FILE) — nothing to revoke"
  fi
  # Re-gate the CEO's tools unless the operator asked sidecar-only.
  if [ "$NO_CONFIG" = "0" ]; then
    if swap_ceo_tools gated; then
      echo "[grant-ceo-consent] CEO tool-gate RESTORED (production tools denied again)"
    fi
  else
    echo "[grant-ceo-consent] --no-config: left CEO tool policy unchanged"
  fi
  exit 0
fi

# ─── Validate grant ───────────────────────────────────────────────────────────
if [ -z "$SCOPE" ]; then
  echo "[grant-ceo-consent] ERROR: a <scope> is required for a grant" >&2
  _usage; exit 1
fi
if [ "${#PHRASE}" -lt 4 ]; then
  echo "[grant-ceo-consent] ERROR: --phrase is required and must be the owner's literal consent text (>= 4 chars)" >&2
  echo "[grant-ceo-consent]        this is the hardening guard — the CEO agent cannot supply this" >&2
  exit 1
fi

# Validate until: is a parseable ISO instant in the future.
if printf '%s' "$SCOPE" | grep -q '^until:'; then
  _ISO="${SCOPE#until:}"
  if ! ISO="$_ISO" python3 - <<'PYEOF'
import os, sys
from datetime import datetime, timezone
s = os.environ["ISO"].strip()
if s.endswith("Z"):
    s = s[:-1] + "+00:00"
try:
    dt = datetime.fromisoformat(s)
except Exception:
    sys.exit(1)
if dt.tzinfo is None:
    dt = dt.replace(tzinfo=timezone.utc)
sys.exit(0 if dt > datetime.now(timezone.utc) else 2)
PYEOF
  then
    echo "[grant-ceo-consent] ERROR: until:<iso8601> must parse and be in the future (e.g. until:2026-06-20T18:00:00Z)" >&2
    exit 1
  fi
fi

# ─── Write the record (atomic) ────────────────────────────────────────────────
mkdir -p "$STATE_DIR"
TMP_FILE="$(mktemp "${STATE_DIR}/.ceo-consent.XXXXXX")"
SCOPE="$SCOPE" PHRASE="$PHRASE" python3 - "$TMP_FILE" <<'PYEOF'
import json, os, sys
from datetime import datetime, timezone
rec = {
    "granted": True,
    "scope": os.environ["SCOPE"],
    "granted_at": datetime.now(timezone.utc).isoformat(),
    "granted_by": "owner",
    "phrase": os.environ["PHRASE"],
}
with open(sys.argv[1], "w") as fh:
    json.dump(rec, fh, indent=2)
    fh.write("\n")
PYEOF
chmod 600 "$TMP_FILE" 2>/dev/null || true
mv "$TMP_FILE" "$CONSENT_FILE"

echo "[grant-ceo-consent] consent GRANTED"
echo "[grant-ceo-consent]   scope: $SCOPE"
echo "[grant-ceo-consent]   file:  $CONSENT_FILE"

# Lift the CEO tool-gate so the owner-consented direct work can actually run
# (the carve-out — restrict-only policy means this MUST be a config swap, not an
# in-session allow). --no-config writes the sidecar only.
if [ "$NO_CONFIG" = "0" ]; then
  if swap_ceo_tools consented; then
    echo "[grant-ceo-consent] CEO tool-gate LIFTED — production tools re-granted for direct work"
    echo "[grant-ceo-consent]   IMPORTANT: re-gate when done →  bash grant-ceo-consent.sh --revoke"
  fi
else
  echo "[grant-ceo-consent] --no-config: sidecar written; CEO tool policy left GATED"
  echo "[grant-ceo-consent]   (Layer-3 QC gate honors this consent; tools stay denied)"
fi
