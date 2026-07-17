#!/usr/bin/env bash
# =============================================================================
# scripts/loop-protection-first-proof.sh
# -----------------------------------------------------------------------------
# THE OPERATOR-BOX FIRST-PROOF for the furnace / loop protection pair
#   Skill 60 (ZHC Early Warning System) + Skill 61 (Loop Protection System).
#
# This is the ONE box that proves the machinery FIRST (SKILL.md law 8: PROVE
# ON THE OPERATOR BOX, THEN HOLD). Trevor runs it on HIS box only. It never
# touches a client box, never arms without a 7-day burn-in, and never fires a
# cron off-box.
#
# Renamed from loop-protection-canary.sh (D20, operator-box-proof vocabulary);
# a one-release compatibility shim at the old filename execs this file
# unchanged.
#
# The path to live is three deliberate steps, each idempotent:
#   1. install   -> installs 60 then 61 (role=operator, UNGATED), registers the
#                   ews-tick + loop-tick crons + hourly aggregator, initializes
#                   both ledgers, and leaves the box in DRY_RUN observe-only
#                   (armed=false). Stamps the burn-in clock on first install.
#   2. verify    -> runs both skills' failable offline drill batteries.
#   3. status    -> shows armed state, burn-in days elapsed / remaining, and open
#                   findings — the observe-only ledger you review before arming.
#   4. arm       -> AFTER >= 7 days of burn-in, arms Skill 61 Tier-1 auto-fix.
#                   Refuses early unless --force; requires --yes; prints the
#                   one-line revert (disarm). Skill 60 stays detection-only.
#
# FLEET ROLLOUT IS SEPARATE and comes AFTER this first-proof run passes: flip
# 61-loop-protection-system/config/rollout.json fleet_rollout_enabled=true (or
# export OPENCLAW_LOOP_PROTECTION_ROLLOUT=1) in ONE batch on Trevor's word; the
# wiring in install.sh / update-skills.sh then activates every box (DRY_RUN,
# never armed). See scripts/activate-loop-protection.sh.
#
# USAGE:
#   loop-protection-first-proof.sh install [--skills-dir DIR] [--no-cron]
#   loop-protection-first-proof.sh verify  [--skills-dir DIR]
#   loop-protection-first-proof.sh status  [--skills-dir DIR]
#   loop-protection-first-proof.sh arm     [--yes] [--force]
#   loop-protection-first-proof.sh disarm
#   loop-protection-first-proof.sh runbook            # print the full runbook
#   loop-protection-first-proof.sh --self-test        # offline, sandboxed
# EXIT: 0 OK, 1 error, 2 usage, 3 gate refused (burn-in not met / not operator).
# =============================================================================
set -uo pipefail

SELF_PATH="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)/$(basename "${BASH_SOURCE[0]:-$0}")"
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
REPO_ROOT="$(cd "$SELF_DIR/.." && pwd)"
TAG="[loop-first-proof]"
BURN_IN_DAYS=7

EX_OK=0; EX_ERR=1; EX_USAGE=2; EX_GATE=3

CMD="${1:-runbook}"; shift || true
SKILLS_DIR_ARG=""; NO_CRON=0; YES=0; FORCE=0
while [ $# -gt 0 ]; do
    case "$1" in
        --skills-dir) SKILLS_DIR_ARG="${2:-}"; shift 2 ;;
        --no-cron)    NO_CRON=1; shift ;;
        --yes)        YES=1; shift ;;
        --force)      FORCE=1; shift ;;
        *) echo "$TAG unknown arg: $1" >&2; exit $EX_USAGE ;;
    esac
done

_note() { echo "$TAG $*"; }
_warn() { echo "$TAG WARN: $*" >&2; }
_err()  { echo "$TAG ERROR: $*" >&2; }

command -v python3 >/dev/null 2>&1 || { _err "python3 is required (loop protection is deterministic Python)."; exit $EX_ERR; }

resolve_skills_dir() {
    if [ -n "$SKILLS_DIR_ARG" ] && [ -d "$SKILLS_DIR_ARG" ]; then echo "$SKILLS_DIR_ARG"; return; fi
    if [ -n "${SKILLS_DIR:-}" ] && [ -d "${SKILLS_DIR:-}" ]; then echo "$SKILLS_DIR"; return; fi
    if [ -n "${OC_SKILLS_DIR:-}" ] && [ -d "${OC_SKILLS_DIR:-}" ]; then echo "$OC_SKILLS_DIR"; return; fi
    if [ -d "/data/.openclaw/skills" ]; then echo "/data/.openclaw/skills"; return; fi
    if [ -d "$HOME/.openclaw/skills" ]; then echo "$HOME/.openclaw/skills"; return; fi
    echo "$REPO_ROOT"
}

SD="$(resolve_skills_dir)"
LP_DIR="$SD/61-loop-protection-system"
EWS_DIR="$SD/60-zhc-early-warning-system"
LP_LEDGER="$LP_DIR/scripts/loop_ledger.py"

# The 61 state dir (where loop.db and the burn-in marker live), resolved from the
# ledger itself so Mac (~/.openclaw/loop-protection) and VPS (/data/...) both work.
lp_state_dir() {
    [ -f "$LP_LEDGER" ] || { echo ""; return; }
    python3 "$LP_LEDGER" init 2>/dev/null | python3 -c 'import json,sys,os
try: print(os.path.dirname(json.load(sys.stdin).get("db","")))
except Exception: print("")' 2>/dev/null || echo ""
}

# D20 NOTE: the on-disk marker FILENAME (.canary-installed-ts) is deliberately
# left unchanged by the U93 rename. It is stored state, not doctrine text — a
# box that already stamped its burn-in clock under the old script must keep
# reading the same marker, or the rename would silently reset an in-progress
# 7-day burn-in. Same rationale as the untouched system_status.probe_type
# default in heartbeat-embedding-probe.py.
marker_path() { local s; s="$(lp_state_dir)"; [ -n "$s" ] && echo "$s/.canary-installed-ts" || echo ""; }

# meta 'role' via a tiny import (the ledger CLI does not expose it directly).
ledger_role() {
    [ -f "$LP_LEDGER" ] || { echo "?"; return; }
    python3 - "$LP_DIR/scripts" <<'PY' 2>/dev/null || echo "?"
import sys; sys.path.insert(0, sys.argv[1])
try:
    from loop_ledger import Ledger
    led = Ledger(); print(led.get_meta("role","?") or "?"); led.close()
except Exception:
    print("?")
PY
}

ledger_armed() {
    [ -f "$LP_LEDGER" ] || { echo "?"; return; }
    python3 "$LP_LEDGER" init 2>/dev/null | python3 -c 'import json,sys; print(str(json.load(sys.stdin).get("armed")))' 2>/dev/null || echo "?"
}

burn_in_days_elapsed() {
    local m ts now; m="$(marker_path)"
    [ -n "$m" ] && [ -f "$m" ] || { echo "-1"; return; }
    ts="$(cat "$m" 2>/dev/null | tr -dc '0-9')"
    [ -n "$ts" ] || { echo "-1"; return; }
    now="$(date +%s)"
    echo "$(( (now - ts) / 86400 ))"
}

# --------------------------------------------------------------------------- #
cmd_install() {
    local _act="$SD/scripts/activate-loop-protection.sh"
    [ -f "$_act" ] || _act="$REPO_ROOT/scripts/activate-loop-protection.sh"
    [ -f "$_act" ] || { _err "activate-loop-protection.sh not found (looked in $SD/scripts and $REPO_ROOT/scripts)."; return $EX_ERR; }
    _note "operator-box first-proof install: Skill 60 + 61 (role=operator, UNGATED, DRY_RUN observe-only)..."
    local _args="--role operator --skills-dir $SD"
    [ "$NO_CRON" -eq 1 ] && _args="$_args --no-cron"
    # shellcheck disable=SC2086
    bash "$_act" $_args || _warn "activation returned non-zero (see output) — continuing to stamp burn-in."

    # Stamp the burn-in clock ONCE (never reset on re-install => burn-in keeps counting).
    local m; m="$(marker_path)"
    if [ -n "$m" ]; then
        if [ -f "$m" ]; then
            _note "burn-in clock already stamped ($(cat "$m")); NOT resetting (idempotent)."
        else
            date +%s > "$m" 2>/dev/null && _note "burn-in clock stamped: $(date -u +%Y-%m-%dT%H:%M:%SZ) (arm after ${BURN_IN_DAYS} days)." \
                || _warn "could not write burn-in marker at $m"
        fi
    else
        _warn "could not resolve the 61 state dir; burn-in marker not stamped (install the skill first)."
    fi
    echo ""
    _note "NEXT: bash $SELF_PATH verify   # run the offline drill batteries"
    _note "THEN: let it observe for ${BURN_IN_DAYS} days, then: bash $SELF_PATH status && bash $SELF_PATH arm --yes"
    return $EX_OK
}

cmd_verify() {
    local rc=0
    if [ -f "$EWS_DIR/verify.sh" ]; then
        _note "Skill 60 drill battery..."; bash "$EWS_DIR/verify.sh" || { rc=1; _warn "Skill 60 verify FAILED"; }
    else _warn "Skill 60 verify.sh not found at $EWS_DIR"; fi
    if [ -f "$LP_DIR/verify.sh" ]; then
        _note "Skill 61 drill battery (11 offline drills)..."; bash "$LP_DIR/verify.sh" || { rc=1; _warn "Skill 61 verify FAILED"; }
    else _warn "Skill 61 verify.sh not found at $LP_DIR"; fi
    [ "$rc" -eq 0 ] && _note "verify: ALL PASS" || _err "verify: FAILURES (do NOT arm until green)"
    return $rc
}

cmd_status() {
    local armed role days open m
    armed="$(ledger_armed)"; role="$(ledger_role)"; days="$(burn_in_days_elapsed)"; m="$(marker_path)"
    open="$(python3 "$LP_LEDGER" open-findings 2>/dev/null | python3 -c 'import json,sys
try: print(len(json.load(sys.stdin).get("findings",[])))
except Exception: print("?")' 2>/dev/null || echo "?")"
    echo "== Loop Protection operator-box status =="
    echo "  skills dir     : $SD"
    echo "  61 state dir   : $(lp_state_dir)"
    echo "  role (meta)    : $role"
    echo "  61 armed       : $armed        (false = DRY_RUN observe-only; true = Tier-1 auto-fix live)"
    echo "  60 ledger      : $( [ -f "$EWS_DIR/scripts/ews_ledger.py" ] && python3 "$EWS_DIR/scripts/ews_ledger.py" init >/dev/null 2>&1 && echo present || echo 'absent/older-bundle' )"
    echo "  open findings  : $open"
    if [ "$days" -ge 0 ] 2>/dev/null; then
        echo "  burn-in        : ${days}/${BURN_IN_DAYS} days elapsed ($( [ "$days" -ge "$BURN_IN_DAYS" ] && echo 'READY TO ARM' || echo "$((BURN_IN_DAYS - days)) day(s) remaining" ))"
    else
        echo "  burn-in        : not stamped (run: bash $SELF_PATH install)"
    fi
    echo ""
    if [ "$armed" = "True" ]; then
        echo "  This box is ARMED. Revert with: bash $SELF_PATH disarm"
    elif [ "$days" -ge "$BURN_IN_DAYS" ] 2>/dev/null; then
        echo "  Burn-in complete. Review findings above, then: bash $SELF_PATH arm --yes"
    else
        echo "  Observe-only. Arm is gated until burn-in completes (or use --force with intent)."
    fi
    return $EX_OK
}

cmd_arm() {
    local role days
    role="$(ledger_role)"; days="$(burn_in_days_elapsed)"

    if [ "$role" != "operator" ] && [ "$FORCE" -ne 1 ]; then
        _err "this ledger's role is '$role', not 'operator'. This first-proof script arms the OPERATOR box only."
        _err "On client boxes, protection rolls via the fleet gate (rollout.json / OPENCLAW_LOOP_PROTECTION_ROLLOUT) and stays DRY_RUN."
        _err "If you truly intend to arm this box, re-run with --force."
        return $EX_GATE
    fi
    if [ "$days" -lt 0 ] 2>/dev/null; then
        _err "no burn-in marker — run 'bash $SELF_PATH install' first (the 7-day observe-only clock starts there)."
        return $EX_GATE
    fi
    if [ "$days" -lt "$BURN_IN_DAYS" ] 2>/dev/null && [ "$FORCE" -ne 1 ]; then
        _err "burn-in not met: ${days}/${BURN_IN_DAYS} days. Arm is refused until the box has observed for ${BURN_IN_DAYS} days (SKILL.md law 7: DRY_RUN, THEN ARM)."
        _err "Review findings first: bash $SELF_PATH status. To override with intent: --force."
        return $EX_GATE
    fi
    if [ "$YES" -ne 1 ]; then
        _err "arming enables Skill 61 Tier-1 auto-fix (config-free process-park applies for real; every config-touching class stays PREPARE-then-apply-on-box)."
        _err "Re-run with --yes to confirm. Revert any time with: bash $SELF_PATH disarm"
        return $EX_GATE
    fi
    [ "$FORCE" -eq 1 ] && [ "$days" -lt "$BURN_IN_DAYS" ] 2>/dev/null && _warn "--force: arming with only ${days}/${BURN_IN_DAYS} days of burn-in."

    _note "arming Skill 61 Tier-1 auto-fix..."
    if bash "$LP_DIR/loop-companion.sh" arm >/dev/null 2>&1; then
        _note "ARMED. Skill 61 Tier-1 auto-fix is live (Skill 60 remains detection-only)."
        _note "Revert (one line): bash $SELF_PATH disarm   (or: bash $LP_DIR/loop-companion.sh disarm)"
        return $EX_OK
    fi
    _err "arm command failed (see: bash $LP_DIR/loop-companion.sh arm)"
    return $EX_ERR
}

cmd_disarm() {
    if bash "$LP_DIR/loop-companion.sh" disarm >/dev/null 2>&1; then
        _note "DISARMED — back to DRY_RUN observe-only."
        return $EX_OK
    fi
    _err "disarm failed (see: bash $LP_DIR/loop-companion.sh disarm)"
    return $EX_ERR
}

cmd_runbook() {
    cat <<RB
============================================================================
 LOOP PROTECTION OPERATOR-BOX FIRST-PROOF RUNBOOK  (operator box only — Trevor runs this)
============================================================================
 Skill 60 (Early Warning System) + Skill 61 (Loop Protection System) are the
 fleet's furnace / crash-loop reflex arc. They are WIRED into onboarding +
 the updater but HELD fleet-wide (rollout.json). This script proves them on
 the operator box FIRST (SKILL.md law 8: PROVE ON THE OPERATOR BOX, THEN HOLD).

 STEP 1 - INSTALL (idempotent, DRY_RUN observe-only, never arms):
     bash scripts/loop-protection-first-proof.sh install
   Registers ews-tick + loop-tick crons (*/15, --no-deliver, operator target)
   + the hourly aggregator, initializes both ledgers, stamps the 7-day clock.
   On VPS run inside the container as the box user:
     docker exec -u node <ctr> bash /data/.openclaw/skills/.../loop-protection-first-proof.sh install

 STEP 2 - VERIFY (failable, fully offline drill batteries):
     bash scripts/loop-protection-first-proof.sh verify

 STEP 3 - BURN IN 7 DAYS, then review the observe-only ledger:
     bash scripts/loop-protection-first-proof.sh status

 STEP 4 - ARM Tier-1 auto-fix (only after burn-in; requires --yes):
     bash scripts/loop-protection-first-proof.sh arm --yes
   Revert any time:
     bash scripts/loop-protection-first-proof.sh disarm

 AFTER THIS FIRST-PROOF RUN PASSES — FLEET ROLLOUT (separate, operator-timed, ONE batch):
   Flip 61-loop-protection-system/config/rollout.json fleet_rollout_enabled=true
   (or export OPENCLAW_LOOP_PROTECTION_ROLLOUT=1), commit as ONE batch, then the
   install.sh / update-skills.sh wiring activates every box in DRY_RUN (never
   armed). Verify RESCUE_RANGERS_WEBHOOK_URL per box during the roll
   (validate-config-after-fanout doctrine): the 30-min unacked-P1 escalation
   path depends on it.
============================================================================
RB
    return $EX_OK
}

# --------------------------------------------------------------------------- #
self_test() {
    echo "$TAG self-test: sandboxed first-proof (offline, no cron)"
    local rc=0 td; td="$(mktemp -d)"
    export LOOP_STATE_DIR="$td/loop-protection" LOOP_OPENCLAW_ROOT="$td/oc" \
           EWS_STATE_DIR="$td/ews" EWS_OPENCLAW_ROOT="$td/oc" EWS_CONFIG_PATH="$td/openclaw.json"
    mkdir -p "$td/oc"
    # point the script's paths at the repo checkout
    SD="$REPO_ROOT"; LP_DIR="$SD/61-loop-protection-system"; EWS_DIR="$SD/60-zhc-early-warning-system"
    LP_LEDGER="$LP_DIR/scripts/loop_ledger.py"

    # install (no cron)
    NO_CRON=1 cmd_install >/dev/null 2>&1 || true
    if [ -f "$td/loop-protection/loop.db" ]; then echo "  install case: PASS (ledger created)"; else echo "  install case: FAIL (no ledger)" >&2; rc=1; fi
    local m; m="$(marker_path)"
    if [ -n "$m" ] && [ -f "$m" ]; then echo "  marker case: PASS (burn-in clock stamped)"; else echo "  marker case: FAIL (no burn-in marker)" >&2; rc=1; fi

    # armed must be false after install
    if [ "$(ledger_armed)" = "False" ]; then echo "  dry-run case: PASS (install left box unarmed)"; else echo "  dry-run case: FAIL (install armed the box)" >&2; rc=1; fi

    # arm WITHOUT --yes -> gate refuses (exit 3)
    YES=0 FORCE=0 cmd_arm >/dev/null 2>&1; local a1=$?
    if [ "$a1" -eq $EX_GATE ]; then echo "  gate case: PASS (arm refused: burn-in 0<7 or no --yes)"; else echo "  gate case: FAIL (arm not gated, rc=$a1)" >&2; rc=1; fi

    # arm --yes but burn-in unmet -> still refused (exit 3)
    YES=1 FORCE=0 cmd_arm >/dev/null 2>&1; local a2=$?
    if [ "$a2" -eq $EX_GATE ]; then echo "  burn-in case: PASS (arm --yes refused: 0<7 days)"; else echo "  burn-in case: FAIL (burn-in gate bypassed, rc=$a2)" >&2; rc=1; fi

    # arm --yes --force -> arms
    YES=1 FORCE=1 cmd_arm >/dev/null 2>&1 || true
    if [ "$(ledger_armed)" = "True" ]; then echo "  arm case: PASS (--yes --force armed the box)"; else echo "  arm case: FAIL (force-arm did not arm)" >&2; rc=1; fi

    # disarm -> back to DRY_RUN
    cmd_disarm >/dev/null 2>&1 || true
    if [ "$(ledger_armed)" = "False" ]; then echo "  disarm case: PASS (revert to DRY_RUN)"; else echo "  disarm case: FAIL (disarm did not revert)" >&2; rc=1; fi

    unset LOOP_STATE_DIR LOOP_OPENCLAW_ROOT EWS_STATE_DIR EWS_OPENCLAW_ROOT EWS_CONFIG_PATH
    rm -rf "$td"
    if [ "$rc" -eq 0 ]; then echo "$TAG self-test: PASS"; else echo "$TAG self-test: FAIL" >&2; fi
    return $rc
}

case "$CMD" in
    install)     cmd_install; exit $? ;;
    verify)      cmd_verify;  exit $? ;;
    status)      cmd_status;  exit $? ;;
    arm)         cmd_arm;     exit $? ;;
    disarm)      cmd_disarm;  exit $? ;;
    runbook|-h|--help|"") cmd_runbook; exit $EX_OK ;;
    --self-test) self_test;   exit $? ;;
    *) _err "unknown command: $CMD"; cmd_runbook >&2; exit $EX_USAGE ;;
esac
