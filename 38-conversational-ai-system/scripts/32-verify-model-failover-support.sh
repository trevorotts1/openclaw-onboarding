#!/usr/bin/env bash
# 32-verify-model-failover-support.sh (U-8) - the Mode A vs Mode B preflight for
# the model fallback chain.
#
# HONEST RUNTIME DEPENDENCY: per-reply model failover (Mode A, FULL) requires the
# installed OpenClaw gateway to support selecting an ALTERNATE model for a hook
# session AFTER a provider error. That capability MUST be verified, never assumed.
# This script inspects the installed version + CLI for a per-session / per-mapping
# model override and resolves ONE of two modes:
#
#   full     - per-session override supported: on a provider error the hook session
#              retries once on primary then fails over to the next chain model for
#              THAT reply, logs model_failover, notifies after 3 failovers/hour.
#   degraded - override NOT supported (or cannot be verified): the chain still
#              exists, but failover is a monitor-and-switch loop that rewrites the
#              mapping model to the next chain entry (config-safe) and restarts the
#              gateway (launchctl kickstart on Mac / docker compose restart on VPS).
#              Recovery to primary is operator-approved only (Saturday freshness cron).
#
# It records failover_mode in the run manifest so the client doc and QC know which
# behavior is live, and (optionally) writes the skill38.model_chain config keys via
# the config-safe pattern when --primary is supplied.
#
# NON-FATAL: this is a preflight/report; it never blocks the install (always exit 0).
# Idempotent. OS-aware (Darwin + Linux). bash -n clean.
#
# Usage:
#   bash scripts/32-verify-model-failover-support.sh
#   bash scripts/32-verify-model-failover-support.sh --primary "ollama/deepseek-v4-pro:cloud" \
#        --fallback "openrouter/kimi" --fallback "<provider/model>"
#   bash scripts/32-verify-model-failover-support.sh --mode degraded   # force (testing/override)
#   bash scripts/32-verify-model-failover-support.sh --json

set -uo pipefail

PRIMARY=""
FALLBACKS=()
FORCE_MODE=""
JSON_MODE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --primary)  PRIMARY="$2"; shift 2 ;;
    --fallback) FALLBACKS+=("$2"); shift 2 ;;
    --mode)     FORCE_MODE="$2"; shift 2 ;;
    --json)     JSON_MODE=1; shift ;;
    -h|--help)  sed -n '1,40p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

# Allow an operator env override in addition to --mode.
[ -z "$FORCE_MODE" ] && FORCE_MODE="${SKILL38_FAILOVER_MODE:-}"

# --- Resolve MASTER_FILES_DIR from the pointer (bare path, never source it). ---
MASTER_FILES_POINTER="$HOME/.openclaw/.skill-38-master-files-dir"
MASTER_FILES_DIR="${MASTER_FILES_DIR:-}"
if [ -z "$MASTER_FILES_DIR" ] && [ -f "$MASTER_FILES_POINTER" ]; then
  MASTER_FILES_DIR="$(head -n1 "$MASTER_FILES_POINTER")"
fi

# --- Capability detection (verify, never assume). ------------------------------
# We resolve Mode A (full) ONLY when we can positively confirm the installed CLI
# documents a per-session / per-mapping model override; otherwise we CONSERVATIVELY
# resolve Mode B (degraded), which is always safe (the chain works via
# monitor-and-switch even without a per-session override).
OPENCLAW_VERSION="unknown"
CAP_EVIDENCE="none"
MODE="degraded"

if [ -n "$FORCE_MODE" ]; then
  case "$FORCE_MODE" in
    full|degraded) MODE="$FORCE_MODE"; CAP_EVIDENCE="forced ($FORCE_MODE)" ;;
    *) echo "[skill 38] WARN: --mode must be full|degraded; ignoring '$FORCE_MODE'" >&2 ;;
  esac
fi

if [ -z "$FORCE_MODE" ] || { [ "$MODE" != "full" ] && [ "$MODE" != "degraded" ]; }; then
  if command -v openclaw >/dev/null 2>&1; then
    OPENCLAW_VERSION="$(openclaw --version 2>/dev/null | head -n1 | tr -d '[:space:]' || echo unknown)"
    # Probe the CLI help surfaces for a per-session / per-mapping model override.
    # A positive hit is the ONLY thing that promotes to Mode A (full).
    HELP_BLOB="$( { openclaw hooks --help; openclaw config --help; openclaw agents --help; } 2>/dev/null )"
    if printf '%s' "$HELP_BLOB" | grep -qiE 'per-session model|session model override|per-mapping model|model[- ]override|fallback[- ]model'; then
      MODE="full"
      CAP_EVIDENCE="cli help documents a per-session/per-mapping model override"
    else
      MODE="degraded"
      CAP_EVIDENCE="no per-session model override found in cli help; conservative degraded"
    fi
  else
    MODE="degraded"
    CAP_EVIDENCE="openclaw not on PATH; cannot verify; conservative degraded"
  fi
fi

# --- Optionally persist the chain via the CONFIG-SAFE pattern. ------------------
# Written ONLY via `openclaw config set skill38.model_chain.*` (never a jq //= ;
# mutation, never a .cron.jobs / agents.defaults.* shape). qc-config-schema-safety.sh
# sanctions this shape (its ALLOW-KNOWLEDGE note). No-op when openclaw is absent.
CHAIN_WRITTEN="no"
if [ -n "$PRIMARY" ] && command -v openclaw >/dev/null 2>&1; then
  if openclaw config set skill38.model_chain.primary "$PRIMARY" >/dev/null 2>&1; then
    CHAIN_WRITTEN="primary"
    if [ "${#FALLBACKS[@]}" -gt 0 ]; then
      FB_JSON="$(printf '%s\n' "${FALLBACKS[@]}" | python3 -c 'import json,sys; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))' 2>/dev/null || echo '[]')"
      if openclaw config set skill38.model_chain.fallbacks "$FB_JSON" >/dev/null 2>&1; then
        CHAIN_WRITTEN="primary+fallbacks"
      fi
    fi
  fi
elif [ -n "$PRIMARY" ]; then
  CHAIN_WRITTEN="skipped (openclaw not on PATH)"
fi

# --- Record failover_mode in the run manifest. ---------------------------------
MANIFEST_RECORDED="no"
if [ -n "$MASTER_FILES_DIR" ] && [ -d "$MASTER_FILES_DIR" ]; then
  RUN_MANIFEST="$(ls -1t "$MASTER_FILES_DIR"/run-manifest-*.md 2>/dev/null | head -n1 || true)"
  if [ -z "$RUN_MANIFEST" ]; then
    RUN_MANIFEST="$MASTER_FILES_DIR/run-manifest-$(date -u +%Y%m%dT%H%M%SZ).md"
  fi
  {
    echo ""
    echo "## Model failover preflight (U-8)"
    echo ""
    echo "- failover_mode: $MODE"
    echo "- openclaw_version: $OPENCLAW_VERSION"
    echo "- capability_evidence: $CAP_EVIDENCE"
    echo "- model_chain_written: $CHAIN_WRITTEN"
    echo "- reference: references/model-fallback-chain.md"
  } >> "$RUN_MANIFEST" 2>/dev/null && MANIFEST_RECORDED="$RUN_MANIFEST"

  # PII-free preflight line into the failover sink (created empty by script 25).
  SINK="$MASTER_FILES_DIR/model-failover-events.jsonl"
  if [ -f "$SINK" ]; then
    TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf '{"timestamp":"%s","event_type":"model_failover_preflight","failover_mode":"%s","openclaw_version":"%s"}\n' \
      "$TS" "$MODE" "$OPENCLAW_VERSION" >> "$SINK" 2>/dev/null || true
  fi
fi

# --- Report. -------------------------------------------------------------------
if [ "$JSON_MODE" -eq 1 ]; then
  python3 - "$MODE" "$OPENCLAW_VERSION" "$CAP_EVIDENCE" "$CHAIN_WRITTEN" "$MANIFEST_RECORDED" <<'PYEOF'
import json, sys
mode, ver, ev, chain, man = sys.argv[1:6]
print(json.dumps({
    "preflight": "model-failover-support",
    "failover_mode": mode,
    "openclaw_version": ver,
    "capability_evidence": ev,
    "model_chain_written": chain,
    "manifest_recorded": man,
}, indent=2))
PYEOF
else
  echo "=== 32-verify-model-failover-support: model fallback chain preflight (U-8) ==="
  echo "  failover_mode      : $MODE"
  echo "  openclaw version   : $OPENCLAW_VERSION"
  echo "  capability evidence: $CAP_EVIDENCE"
  echo "  model_chain written: $CHAIN_WRITTEN"
  echo "  manifest recorded  : $MANIFEST_RECORDED"
  if [ "$MODE" = "full" ]; then
    echo "  -> Mode A (FULL): per-reply failover is live; the chain fails over per reply and self-heals."
  else
    echo "  -> Mode B (DEGRADED): monitor-and-switch. On a sustained outage the mapping is rewritten to"
    echo "     the next chain model and the gateway is restarted (Mac: launchctl kickstart -k"
    echo "     gui/\$(id -u)/ai.openclaw.gateway ; VPS: docker compose restart). Recovery to primary is"
    echo "     operator-approved via the Saturday freshness cron. See references/model-fallback-chain.md."
  fi
fi

exit 0
