#!/usr/bin/env bash
# migrate-existing-workforce.sh - v10.15.5 (Mac) / v10.16.5 (VPS)
#
# One-shot SOP + role-library remediation for the 5 audited clients (or any
# client whose workforce predates the post-build pipeline). Safe to re-run.
# Read-only by default. --apply required for mutations. Logs to a file plus
# Telegrams the operator on completion.
#
# Does NOT restart gateways. Does NOT modify openclaw.json.
#
# Usage:
#   bash migrate-existing-workforce.sh <client> [--dry-run|--apply]
#
# Example:
#   bash migrate-existing-workforce.sh kofi --dry-run
#   bash migrate-existing-workforce.sh kofi --apply

set -uo pipefail

CLIENT="${1:-unknown}"
MODE="${2:---dry-run}"
case "$MODE" in
  --dry-run|--apply) ;;
  *) MODE="--dry-run" ;;
esac

TS="$(date +%Y%m%d-%H%M%S)"
LOG_DIR="$HOME/.openclaw/logs"
[ -d "/data/.openclaw" ] && LOG_DIR="/data/.openclaw/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/migrate-${CLIENT}-${TS}.log"

# ----- Resolve skill 23 install dir -----
SKILL_DIR=""
for cand in \
  "$HOME/.openclaw/skills/23-ai-workforce-blueprint" \
  "/data/.openclaw/skills/23-ai-workforce-blueprint" \
  "$HOME/Downloads/openclaw-master-files/23-ai-workforce-blueprint"; do
  if [ -d "$cand" ]; then SKILL_DIR="$cand"; break; fi
done
if [ -z "$SKILL_DIR" ]; then
  echo "FATAL: skill 23 not installed (checked ~/.openclaw, /data/.openclaw, ~/Downloads/openclaw-master-files)" | tee "$LOG"
  exit 1
fi

# ----- Resolve openclaw binary -----
OC_BIN=""
for cand in "${OPENCLAW_BIN:-}" "$(command -v openclaw 2>/dev/null)" \
            "/opt/homebrew/bin/openclaw" "/usr/local/bin/openclaw" \
            "$HOME/.openclaw/bin/openclaw" "/data/.npm-global/bin/openclaw" \
            "/data/linuxbrew/.linuxbrew/bin/openclaw"; do
  if [ -n "${cand:-}" ] && [ -x "$cand" ]; then OC_BIN="$cand"; break; fi
done

# ----- Trevor's chat ID (per memory fleet-chat-id-discovery) -----
TREVOR_CHAT="5252140759"

log() { printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*" | tee -a "$LOG"; }
tg() {
  if [ -n "$OC_BIN" ]; then
    "$OC_BIN" message send --channel telegram -t "$TREVOR_CHAT" -m "$1" >>"$LOG" 2>&1 \
      && log "TG sent" \
      || log "TG send FAILED (see log)"
  else
    log "TG-SKIP (no openclaw bin): $1"
  fi
}

log "============================================"
log "migrate-existing-workforce.sh client=$CLIENT mode=$MODE ts=$TS"
log "skill_dir=$SKILL_DIR"
log "openclaw_bin=${OC_BIN:-MISSING}"
log "log=$LOG"
log "============================================"

tg "Starting workforce migration on client=${CLIENT} mode=${MODE}. Log: ${LOG}"

# ----- Step 1: completeness baseline (read-only) -----
log "STEP 1/5: baseline qc-completeness (read-only)"
QC_SCRIPT="$SKILL_DIR/scripts/qc-completeness.sh"
if [ -x "$QC_SCRIPT" ]; then
  bash "$QC_SCRIPT" --quiet 2>&1 | tee -a "$LOG" || true
else
  log "qc-completeness.sh not installed at $QC_SCRIPT (Release 1 didn't land?)"
fi

# ----- Step 2: re-run post-build augmentation -----
log "STEP 2/5: post-build-role-workspaces ${MODE}"
POST_BUILD="$SKILL_DIR/scripts/post-build-role-workspaces.py"
if [ -f "$POST_BUILD" ]; then
  if [ "$MODE" = "--apply" ]; then
    python3 "$POST_BUILD" 2>&1 | tee -a "$LOG"
  else
    python3 "$POST_BUILD" --dry-run 2>&1 | tee -a "$LOG" || true
  fi
else
  log "post-build-role-workspaces.py not found at $POST_BUILD"
fi

# ----- Step 3: populate SOPs from manifest if one exists -----
log "STEP 3/5: populate-sops-from-manifest"
COMPANY_DIR="$(python3 - <<PYEOF 2>>"$LOG" || echo ""
import os, sys, json
from pathlib import Path
for p in ("$SKILL_DIR/lib", "$SKILL_DIR/../shared-utils", "$SKILL_DIR/shared-utils"):
    sys.path.insert(0, p)
try:
    from detect_platform import get_openclaw_paths
    paths = get_openclaw_paths()
    print(paths.get("active_zhc_company") or paths.get("zhc_company_root") or "")
except Exception as e:
    print("", file=sys.stderr)
PYEOF
)"
log "company_dir=${COMPANY_DIR:-NOT_FOUND}"
MANIFEST=""
if [ -n "$COMPANY_DIR" ] && [ -f "$COMPANY_DIR/sop-research-manifest.json" ]; then
  MANIFEST="$COMPANY_DIR/sop-research-manifest.json"
fi
POPULATE="$SKILL_DIR/scripts/populate-sops-from-manifest.py"
if [ -n "$MANIFEST" ] && [ -f "$POPULATE" ]; then
  if [ "$MODE" = "--apply" ]; then
    OPENCLAW_BIN="$OC_BIN" python3 "$POPULATE" --manifest "$MANIFEST" \
      --max-parallel 5 --timeout 1800 2>&1 | tee -a "$LOG" || true
  else
    log "[DRY-RUN] would invoke: python3 $POPULATE --manifest $MANIFEST --max-parallel 5 --timeout 1800"
  fi
else
  log "no manifest found (or populate script missing); skipping SOP populate"
fi

# ----- Step 4: reconcile legacy tree -----
log "STEP 4/5: reconcile-legacy-tree ${MODE}"
RECONCILE="$SKILL_DIR/scripts/reconcile-legacy-tree.py"
if [ -f "$RECONCILE" ]; then
  if [ "$MODE" = "--apply" ]; then
    python3 "$RECONCILE" --apply 2>&1 | tee -a "$LOG" || true
  else
    python3 "$RECONCILE" 2>&1 | tee -a "$LOG" || true
  fi
else
  log "reconcile-legacy-tree.py not installed (Release 2 didn't land?)"
fi

# ----- Step 5: final completeness check with Telegram on != PASS -----
log "STEP 5/5: final qc-completeness (Telegrams on != PASS)"
FINAL_RC=0
if [ -x "$QC_SCRIPT" ]; then
  bash "$QC_SCRIPT" 2>&1 | tee -a "$LOG"
  FINAL_RC=${PIPESTATUS[0]}
else
  log "qc-completeness.sh missing; cannot finalize"
  FINAL_RC=1
fi

tg "Migration complete on client=${CLIENT} mode=${MODE}. Final QC exit=${FINAL_RC}. Log: ${LOG}"

log "============================================"
log "DONE final_rc=${FINAL_RC}"
log "============================================"
exit "$FINAL_RC"
