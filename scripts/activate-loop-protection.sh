#!/usr/bin/env bash
# =============================================================================
# scripts/activate-loop-protection.sh
# -----------------------------------------------------------------------------
# CANONICAL, idempotent activation of the fleet's furnace / loop protection:
#   Skill 60 (ZHC Early Warning System) + Skill 61 (Loop Protection System).
# ONE definition, called by BOTH install.sh (onboarding) and update-skills.sh
# (updater) so the wiring never drifts between the two paths (the same reason
# ensure-heartbeat-defaults.sh / ensure-pipeline-crons.sh are shared).
#
# WHAT IT DOES  (GRAPHICS-FURNACE-CONTEXT-RESCUE-SPEC Topic 2, §2.3 item 2):
#   --role client    GATED. Runs the 60-then-61 per-box installers ONLY when the
#                    fleet rollout gate is enabled. Default = HELD (skip with a
#                    note) per SKILL.md law 8 (PROVE ON THE OPERATOR BOX, THEN
#                    HOLD) + the 7-03 HOLD.
#   --role operator  UNGATED. Always runs — this is the operator's own box; it
#                    proves first (used by scripts/loop-protection-first-proof.sh).
#
# ORDERING: Skill 60 FIRST, then Skill 61 ONLY IF 60 installed cleanly. Skill 61
#   consumes Skill 60's ledger read-only, so 60 is a hard prerequisite (the safe
#   branch of spec §2.3 open-question 5). If 60 is absent/older-bundle, 61 is
#   skipped too (they roll together).
#
# NEVER ARMS: both installers leave the box in DRY_RUN observe-only (armed=false).
#   Tier-1 arming is the operator's own first-proof box's separate, post-burn-in
#   action. This helper asserts armed==false afterward and WARNS (never silently)
#   if it isn't.
#
# NON-FATAL: every failure is a warning, never an abort — activation is
#   best-effort so it can never change its caller's exit status. On VPS the
#   caller runs as the box user inside the container (docker exec -u node), the
#   same context every other cron-registering step here already assumes; the
#   skill installers hard-refuse root (LP-B5 / EWS root-refusal) and this helper
#   surfaces that as a warning + the docker-exec hint.
#
# USAGE:
#   activate-loop-protection.sh [--role client|operator] [--skills-dir DIR]
#                               [--no-cron] [--self-test]
# EXIT: 0 for the caller (best-effort); --self-test returns 0 pass / 1 fail.
# =============================================================================
set -uo pipefail

SELF_PATH="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)/$(basename "${BASH_SOURCE[0]:-$0}")"
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
REPO_ROOT="$(cd "$SELF_DIR/.." && pwd)"
TAG="[loop-activate]"

ROLE="client"; SKILLS_DIR=""; NO_CRON=0; SELFTEST=0
while [ $# -gt 0 ]; do
    case "$1" in
        --role)       ROLE="${2:-client}"; shift 2 ;;
        --skills-dir) SKILLS_DIR="${2:-}"; shift 2 ;;
        --no-cron)    NO_CRON=1; shift ;;
        --self-test)  SELFTEST=1; shift ;;
        -h|--help)
            echo "$TAG usage: activate-loop-protection.sh [--role client|operator] [--skills-dir DIR] [--no-cron] [--self-test]"
            exit 0 ;;
        *) echo "$TAG unknown arg: $1" >&2; exit 0 ;;
    esac
done

_note() { echo "$TAG $*"; }
_warn() { echo "$TAG WARN: $*" >&2; }

# ---- resolve the skills dir (--skills-dir > OC_SKILLS_DIR > platform default) -
resolve_skills_dir() {
    if [ -n "$SKILLS_DIR" ] && [ -d "$SKILLS_DIR" ]; then echo "$SKILLS_DIR"; return 0; fi
    if [ -n "${OC_SKILLS_DIR:-}" ] && [ -d "${OC_SKILLS_DIR:-}" ]; then echo "$OC_SKILLS_DIR"; return 0; fi
    if [ -d "/data/.openclaw/skills" ]; then echo "/data/.openclaw/skills"; return 0; fi
    if [ -d "$HOME/.openclaw/skills" ]; then echo "$HOME/.openclaw/skills"; return 0; fi
    # Last resort: this repo checkout (60-*/61-* live at the repo root).
    echo "$REPO_ROOT"
}

# ---- the fleet rollout gate (client role only) ------------------------------
# Returns 0 = ENABLED, 1 = HELD. Precedence: env override > rollout.json > held.
rollout_enabled() {
    local _sd="$1" _env _val _cfg
    _env="${OPENCLAW_LOOP_PROTECTION_ROLLOUT:-}"
    if [ -n "$_env" ]; then
        _val="$(printf '%s' "$_env" | tr '[:upper:]' '[:lower:]')"
        case "$_val" in 1|true|yes|on|enabled) return 0 ;; *) return 1 ;; esac
    fi
    _cfg="$_sd/61-loop-protection-system/config/rollout.json"
    [ -f "$_cfg" ] || _cfg="$REPO_ROOT/61-loop-protection-system/config/rollout.json"
    if [ -f "$_cfg" ] && command -v python3 >/dev/null 2>&1; then
        _val="$(CFG="$_cfg" python3 - <<'PY' 2>/dev/null || echo error
import json, os
try:
    d = json.load(open(os.environ["CFG"]))
    print("enabled" if d.get("fleet_rollout_enabled") is True else "held")
except Exception:
    print("error")
PY
)"
        case "$_val" in enabled) return 0 ;; *) return 1 ;; esac
    fi
    return 1
}

# ---- run one skill's per-box installer (best-effort, non-fatal) -------------
# $1 skill-dir-name  $2 human label. Returns the installer's rc (0 on skip-missing).
run_skill_installer() {
    local _dir="$1" _label="$2" _sd="$3" _inst _rc=0 _args
    _inst="$_sd/$_dir/install.sh"
    if [ ! -f "$_inst" ]; then
        _warn "$_label installer not found ($_inst) — older bundle; skipping."
        return 1
    fi
    _args="--role $ROLE"
    [ "$NO_CRON" -eq 1 ] && _args="$_args --no-cron"
    _note "installing $_label (role=$ROLE, DRY_RUN observe-only, never arms)..."
    # shellcheck disable=SC2086
    bash "$_inst" $_args || _rc=$?
    if [ "$_rc" -eq 0 ]; then
        _note "$_label install OK."
    elif [ "$_rc" -eq 4 ]; then
        _warn "$_label install REFUSED (running as root). On VPS run this inside the container as the box user: docker exec -u node <ctr> bash <path>. Skipping (non-fatal)."
    else
        _warn "$_label install returned rc=$_rc (see output above) — continuing (non-fatal)."
    fi
    return $_rc
}

# ---- assert the box was NOT armed (defense-in-depth; installers never arm) ---
assert_not_armed() {
    local _sd="$1" _ledger _armed
    _ledger="$_sd/61-loop-protection-system/scripts/loop_ledger.py"
    [ -f "$_ledger" ] && command -v python3 >/dev/null 2>&1 || return 0
    _armed="$(python3 "$_ledger" init 2>/dev/null | python3 -c 'import json,sys
try: print(str(json.load(sys.stdin).get("armed")))
except Exception: print("?")' 2>/dev/null || echo "?")"
    if [ "$_armed" = "True" ]; then
        _warn "Loop Protection ledger reports armed=true after activation. Activation NEVER arms — a box is only armed by the operator's own first-proof run after burn-in. Investigate (this may be a prior operator arm)."
    fi
}

do_activate() {
    local _sd; _sd="$(resolve_skills_dir)"

    if [ "$ROLE" = "client" ]; then
        if rollout_enabled "$_sd"; then
            _note "fleet rollout gate: ENABLED — activating loop protection on this client box."
        else
            _note "fleet rollout gate: HELD (default). Loop Protection (Skill 60 + 61) is WIRED but NOT activated on this client box."
            _note "  To roll fleet-wide (ONE batch, on the operator's word): set fleet_rollout_enabled=true in 61-loop-protection-system/config/rollout.json, or export OPENCLAW_LOOP_PROTECTION_ROLLOUT=1."
            _note "  The operator box proves it FIRST: bash scripts/loop-protection-first-proof.sh install (SKILL.md law 8: PROVE ON THE OPERATOR BOX, THEN HOLD)."
            return 0
        fi
    else
        _note "role=operator — first-proof path (UNGATED): activating loop protection on the operator box."
    fi

    # 60 FIRST (hard prerequisite), then 61 only if 60 installed cleanly.
    local _rc60=0
    run_skill_installer "60-zhc-early-warning-system" "Skill 60 (Early Warning System)" "$_sd" || _rc60=$?
    if [ "$_rc60" -eq 0 ]; then
        run_skill_installer "61-loop-protection-system" "Skill 61 (Loop Protection System)" "$_sd" || true
    else
        _warn "Skill 60 did not install cleanly (rc=$_rc60); SKIPPING Skill 61 (60 is a hard prerequisite — 61 consumes 60's ledger read-only)."
    fi

    assert_not_armed "$_sd"
    _note "activation complete (DRY_RUN observe-only; box is NOT armed). Arm only via the operator's own first-proof run after the 7-day burn-in."
    return 0
}

# =============================================================================
# self-test: fully offline, sandboxed, no cron, no network, no model.
# Proves: (a) client role is HELD by default (no ledger), (b) client role with
# the env override activates both ledgers, (c) operator role activates ungated,
# (d) the box is left DRY_RUN (armed=false), (e) the gate reads rollout.json.
# =============================================================================
self_test() {
    echo "$TAG self-test: sandboxed activation (offline, no cron)"
    command -v python3 >/dev/null 2>&1 || { echo "$TAG self-test SKIP: python3 required" >&2; return 0; }
    local rc=0 td
    td="$(mktemp -d)"

    _run_sandbox() {  # $1 role, $2 env-override(0/1) -> runs activation into $td/state-$RANDOM
        local _role="$1" _ovr="$2" _sdir; _sdir="$td/state-$_role-$_ovr"
        mkdir -p "$_sdir"
        EWS_STATE_DIR="$_sdir/ews" EWS_OPENCLAW_ROOT="$_sdir/oc" EWS_CONFIG_PATH="$_sdir/openclaw.json" \
        LOOP_STATE_DIR="$_sdir/loop-protection" LOOP_OPENCLAW_ROOT="$_sdir/oc" \
        OPENCLAW_LOOP_PROTECTION_ROLLOUT="$_ovr" \
        bash "$SELF_PATH" --role "$_role" --skills-dir "$REPO_ROOT" --no-cron >/dev/null 2>&1 || true
        echo "$_sdir"
    }

    # (a) client + gate HELD (rollout.json default false, env override empty->held)
    local d_held; d_held="$(_run_sandbox client "" )"
    if [ ! -f "$d_held/loop-protection/loop.db" ] && [ ! -f "$d_held/ews/ews.db" ]; then
        echo "  held case: PASS (client role, gate HELD -> no ledger installed)"
    else
        echo "  held case: FAIL (client role activated while gate HELD)" >&2; rc=1
    fi

    # (b) client + env override -> activates both
    local d_ovr; d_ovr="$(_run_sandbox client "1")"
    if [ -f "$d_ovr/ews/ews.db" ] && [ -f "$d_ovr/loop-protection/loop.db" ]; then
        echo "  override case: PASS (client + OPENCLAW_LOOP_PROTECTION_ROLLOUT=1 -> both ledgers)"
    else
        echo "  override case: FAIL (env override did not activate both skills)" >&2; rc=1
    fi

    # (c) operator role -> ungated, activates both
    local d_op; d_op="$(_run_sandbox operator "")"
    if [ -f "$d_op/ews/ews.db" ] && [ -f "$d_op/loop-protection/loop.db" ]; then
        echo "  operator case: PASS (role=operator ungated -> both ledgers)"
    else
        echo "  operator case: FAIL (operator role did not activate)" >&2; rc=1
    fi

    # (d) DRY_RUN: the operator activation must NOT have armed the box
    local _armed
    _armed="$(LOOP_STATE_DIR="$d_op/loop-protection" python3 "$REPO_ROOT/61-loop-protection-system/scripts/loop_ledger.py" init 2>/dev/null \
              | python3 -c 'import json,sys; print(str(json.load(sys.stdin).get("armed")))' 2>/dev/null || echo "?")"
    if [ "$_armed" = "False" ]; then
        echo "  dry-run case: PASS (activation left the box in DRY_RUN observe-only; armed=false)"
    else
        echo "  dry-run case: FAIL (activation armed the box: armed=$_armed)" >&2; rc=1
    fi

    # (e) gate reader honors rollout.json
    if rollout_enabled "$REPO_ROOT"; then
        echo "  gate case: FAIL (rollout.json default should be HELD/false)" >&2; rc=1
    else
        echo "  gate case: PASS (rollout.json default fleet_rollout_enabled=false -> HELD)"
    fi

    rm -rf "$td"
    if [ "$rc" -eq 0 ]; then echo "$TAG self-test: PASS"; else echo "$TAG self-test: FAIL" >&2; fi
    return $rc
}

if [ "$SELFTEST" -eq 1 ]; then self_test; exit $?; fi
do_activate
exit 0
