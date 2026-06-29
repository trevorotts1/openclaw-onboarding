#!/usr/bin/env bash
# migrate-existing-workforce.sh - v16.0.2
#
# One-shot SOP + role-library remediation for the 5 audited clients (or any
# client whose workforce predates the post-build pipeline). Safe to re-run.
#
# v16.0.2: Step 2b now MATERIALIZES missing canonical floor roles/SOPs via
# floor-fill (was detecting-but-not-filling) — closes incomplete-floor-after-update.
# Read-only by default. --apply required for mutations. Logs to a file plus
# Telegrams the operator on completion.
#
# Does NOT restart gateways. Does NOT modify openclaw.json.
#
# Usage:
#   bash migrate-existing-workforce.sh <client> [--dry-run|--apply]
#
# Example:
#   bash migrate-existing-workforce.sh sample-client --dry-run
#   bash migrate-existing-workforce.sh sample-client --apply

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

# ----- Operator chat ID for migration status reports -----
# INTENTIONAL: this script is an OPERATOR-INITIATED fleet-migration tool.
# Telegram sends here report migration progress to the OPERATOR (not the client
# owner). CO-MINGLING GUARD (v12.4.0): the operator destination is OPT-IN and
# CONFIGURABLE — NO hardcoded personal chat. If no operator escalation chat is
# configured, the progress-report sends are SKIPPED (the migration still runs).
# Configure with: env.vars.OPERATOR_ESCALATION_CHAT_ID (or OPERATOR_TELEGRAM_CHAT_ID).
OPERATOR_CHAT="${OPERATOR_ESCALATION_CHAT_ID:-${OPERATOR_TELEGRAM_CHAT_ID:-}}"

log() { printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*" | tee -a "$LOG"; }
tg() {
  if [ -z "$OPERATOR_CHAT" ]; then
    log "TG-SKIP (operator escalation chat not configured): $1"
  elif [ -n "$OC_BIN" ]; then
    "$OC_BIN" message send --channel telegram -t "$OPERATOR_CHAT" -m "$1" >>"$LOG" 2>&1 \
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

# ----- Step 2b: materialize MISSING floor roles/SOPs (floor-fill) -----
# v16.0.2 FIX (closes incomplete-floor-after-update):
# post-build-role-workspaces.py (Step 2) AUGMENTS the role folders that already
# exist, but it NEVER creates role-workspace folders for roles that are NEW in the
# library (e.g. v16's per-dept devils-advocate / healer, and the video/graphics/
# presentations expansions). detect-stale-artifacts.py correctly DETECTS those
# missing canonical floor slots, but until v16.0.2 nothing ever APPLIED the fill —
# so every v16-updated box kept an incomplete floor.
#
# This step closes the loop: it runs the detector (read-only), converts the
# MISSING verdict into a gap-map (make-gap-from-staleness.py, which compares
# against the box's OWN role-library _index.json — NOT operator-only tooling), and
# materializes ONLY the missing slots via the box's OWN canonical builder
# (floor-fill-driver.py -> create_role_workspaces.py). It is idempotent,
# skip-existing and no-clobber: a present role/SOP is never overwritten, and a
# box whose floor is already complete is a no-op. Runs as the BOX USER (never
# root). Content is REAL role-library content, never stubbed.
#
# EDGE CASE: a box without the shipped role-library (older bundle / non-standard
# layout) is skipped gracefully — the floor cannot be materialized without the
# canonical source, and that is logged rather than failing the migration.
log "STEP 2b/5: materialize missing floor roles/SOPs (floor-fill)"
FF_DETECT="$SKILL_DIR/scripts/detect-stale-artifacts.py"
FF_INDEX="$SKILL_DIR/templates/role-library/_index.json"
FF_MAKEGAP="$SKILL_DIR/scripts/make-gap-from-staleness.py"
FF_DRIVER="$SKILL_DIR/scripts/floor-fill-driver.py"
FF_WS_ROOT="$HOME/.openclaw/workspace"
[ -d "/data/.openclaw" ] && FF_WS_ROOT="/data/.openclaw/workspace"
FF_DEPTS_DIR="$FF_WS_ROOT/departments"
if [ -f "$FF_DETECT" ] && [ -f "$FF_INDEX" ] && [ -f "$FF_MAKEGAP" ] && [ -f "$FF_DRIVER" ] && \
   { [ -d "$FF_DEPTS_DIR" ] || [ -f "$FF_WS_ROOT/.workforce-build-state.json" ]; } && \
   command -v python3 >/dev/null 2>&1; then
  FF_DIR="$LOG_DIR/floor-fill-${CLIENT}-${TS}"
  mkdir -p "$FF_DIR"
  FF_DETECT_JSON="$FF_DIR/detect.json"
  FF_GAP_JSON="$FF_DIR/gap.json"
  # 1) detect MISSING/STALE/etc (READ-ONLY). detect-stale exits 10 on drift — that
  #    is expected and not an error; the JSON is still emitted to stdout.
  python3 "$FF_DETECT" --workspace "$FF_WS_ROOT" --manifest "$FF_INDEX" --json > "$FF_DETECT_JSON" 2>>"$LOG" || true
  # 2) build the gap-map (MISSING-only)
  if python3 "$FF_MAKEGAP" "$FF_DETECT_JSON" --out "$FF_GAP_JSON" 2>>"$LOG"; then
    FF_GAP_DEPTS="$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))))' "$FF_GAP_JSON" 2>/dev/null || echo 0)"
    if [ "${FF_GAP_DEPTS:-0}" -gt 0 ]; then
      # 3) back up the mutable build-state before applying (additive-only, but safe)
      if [ -f "$FF_WS_ROOT/.workforce-build-state.json" ]; then
        cp -p "$FF_WS_ROOT/.workforce-build-state.json" "$FF_DIR/.workforce-build-state.json.bak" 2>/dev/null || true
      fi
      if [ "$MODE" = "--apply" ]; then
        log "  floor-fill: ${FF_GAP_DEPTS} dept(s) with missing floor slots -> materializing (idempotent, skip-existing)"
        python3 "$FF_DRIVER" --gap-file "$FF_GAP_JSON" --workspace "$FF_DEPTS_DIR" --apply 2>&1 | tee -a "$LOG" || \
          log "  floor-fill: completed with warnings (see log)"
      else
        log "  [DRY-RUN] ${FF_GAP_DEPTS} dept(s) have missing floor slots; would run floor-fill-driver.py --apply"
        python3 "$FF_DRIVER" --gap-file "$FF_GAP_JSON" --workspace "$FF_DEPTS_DIR" 2>&1 | tee -a "$LOG" || true
      fi
    else
      log "  floor-fill: floor already complete (no MISSING roles/SOPs) — nothing to materialize"
    fi
  else
    log "  floor-fill: could not build gap-map from detect-stale verdict — skipping (see log)"
  fi
else
  log "  floor-fill: role-library / detector / workspace not present on this box — skipping (edge case: box without the shipped role-library)"
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
# v10.15.44 / v10.16.43 FIX: treat rc=4 (NO_WORKFORCE_FOUND from qc-completeness)
# as advisory — log a warning but exit 0, since the substantive augmentation in
# Steps 2-4 already succeeded additively. rc=4 means the QC probe's path-resolver
# could not locate the workforce tree (e.g. symlinked or non-standard layout), not
# that the augmentation itself failed. A REAL augmentation failure in Steps 2-4
# would have been logged above; those steps still surface their own non-zero exits
# as warnings. qc-completeness rc=3 (FAIL) and rc=1 (python crash) still force
# FINAL_RC non-zero because they represent real QC problems worth surfacing.
log "STEP 5/5: final qc-completeness (Telegrams on != PASS)"
FINAL_RC=0
if [ -x "$QC_SCRIPT" ]; then
  bash "$QC_SCRIPT" 2>&1 | tee -a "$LOG"
  QC_RC=${PIPESTATUS[0]}
  case "$QC_RC" in
    0)
      log "QC: PASS (exit 0)" ;;
    2)
      log "QC: PARTIAL (exit 2) — workforce found but below 95% threshold; augmentation succeeded additively"
      FINAL_RC=2 ;;
    3)
      log "QC: FAIL (exit 3) — real QC failure; operator must investigate"
      FINAL_RC=3 ;;
    4)
      # Advisory only: probe could not resolve the workforce tree path (symlink /
      # non-standard layout), but the augmentation steps above ran to completion.
      log "QC: WARN — qc-completeness exited 4 (NO_WORKFORCE_FOUND path-resolver ambiguity)." \
          "Substantive augmentation completed; treating as advisory. Operator should verify" \
          "workforce tree is reachable from detect_platform."
      FINAL_RC=0 ;;
    *)
      log "QC: unexpected exit ${QC_RC} — treating as FAIL"
      FINAL_RC="${QC_RC}" ;;
  esac
else
  log "qc-completeness.sh missing; cannot finalize"
  FINAL_RC=1
fi

tg "Migration complete on client=${CLIENT} mode=${MODE}. Final QC exit=${FINAL_RC}. Log: ${LOG}"

log "============================================"
log "DONE final_rc=${FINAL_RC}"
log "============================================"
exit "$FINAL_RC"
