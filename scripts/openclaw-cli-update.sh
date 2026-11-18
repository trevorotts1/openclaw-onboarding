#!/bin/bash
# openclaw-cli-update.sh -- the OpenClaw CLI self-update, moved here verbatim (labels only changed) from the
# Saturday 11:59 PM cron that scripts/setup-weekly-update.sh used to write. It now runs INSIDE every
# auto-update run (shared-utils/fleet_refresh_runner.py step "openclaw-update", after the Command Center
# restart and before the health gate), under the same lease, so there is no separate Saturday cron.
# It only ever upgrades through oc-atomic-upgrade.sh (binary + config rollback of its own); exit 78 =
# BLOCKED by the pre-upgrade gate (nothing changed, marker written); a bare npm update is never used.
OC_LOG="$HOME/.openclaw/skills/.update-log"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] OpenClaw update check starting" >> "$OC_LOG"

# ---------------------------------------------------------------------------
# SHARED INSTALLATION LEASE (mac.MAC-1 / mac.MAC-2)
# ---------------------------------------------------------------------------
# This unattended upgrade is an update WRITER: it holds the SAME lease
# as update-skills.sh, self-update.sh, oc-atomic-upgrade.sh and the weekly
# content update — one regular file, one owner record (pid, process start
# identity, run id, role, install path, UTC). Liveness and staleness come from
# the RECORD only: never from the file's existence, never from its age
# (mac.MAC-13). A LIVE foreign owner means STAND DOWN — no wait loop, no retry,
# no displacement, nothing changed on this box.
# scripts/box-update-lock.sh is preferred when the box has it; the inline below
# is the same contract for a box that predates it.
OC_LEASE="${OPENCLAW_UPDATE_LEASE:-/tmp/openclaw-update.lock}"
_ocl_start() { ps -o lstart= -p "$1" 2>/dev/null | tr -s ' ' | sed 's/^ *//;s/ *$//' || true; }
_ocl_ppid()  { ps -o ppid= -p "$1" 2>/dev/null | tr -d ' ' || true; }
_ocl_rpid()  { sed -n 's/^pid=\([0-9][0-9]*\).*/\1/p' "$OC_LEASE" 2>/dev/null | head -1 || true; }
_ocl_rstart(){ sed -n 's/^start=//p' "$OC_LEASE" 2>/dev/null | head -1 || true; }
_ocl_owner_live() {
  [ -f "$OC_LEASE" ] || return 1
  _ocl_p="$(_ocl_rpid)"; [ -n "$_ocl_p" ] || return 1
  kill -0 "$_ocl_p" 2>/dev/null || return 1
  _ocl_s="$(_ocl_rstart)"
  [ -z "$_ocl_s" ] || [ "$_ocl_s" = "none" ] || [ "$(_ocl_start "$_ocl_p")" = "$_ocl_s" ] || return 1
  return 0
}
_ocl_in_tree() {
  _ocl_owner_live || return 1
  _ocl_p="$(_ocl_rpid)"; _ocl_cur="$$"; _ocl_n=0
  while [ -n "$_ocl_cur" ] && [ "$_ocl_cur" -gt 1 ] 2>/dev/null && [ "$_ocl_n" -lt 64 ]; do
    [ "$_ocl_cur" = "$_ocl_p" ] && return 0
    _ocl_cur="$(_ocl_ppid "$_ocl_cur")"; _ocl_n=$((_ocl_n + 1))
  done
  return 1
}
_ocl_release() {
  [ -f "$OC_LEASE" ] || return 0
  [ "$(_ocl_rpid)" = "$$" ] || return 0
  _ocl_s="$(_ocl_rstart)"
  if [ -z "$_ocl_s" ] || [ "$_ocl_s" = "none" ] || [ "$(_ocl_start "$$")" = "$_ocl_s" ]; then
    rm -f "$OC_LEASE" 2>/dev/null || true
  fi
}
_ocl_take() {
  _ocl_h="$HOME/.openclaw/scripts/box-update-lock.sh"
  if [ -f "$_ocl_h" ]; then
    . "$_ocl_h"
    if command -v box_update_lock_acquire >/dev/null 2>&1; then
      box_update_lock_acquire "$OC_LEASE" "oc-update-$$" "openclaw-cli-update" "$HOME/.openclaw"
      case "$?" in
        0) trap 'box_update_lock_release' EXIT; return 0 ;;
        3) return 3 ;;
        *) return 1 ;;
      esac
    fi
  fi
  _ocl_in_tree && return 0
  if [ -e "$OC_LEASE" ] && [ ! -f "$OC_LEASE" ]; then
    _ocl_owner_live && return 3
    rm -rf "$OC_LEASE" 2>/dev/null || return 1
  fi
  _ocl_owner_live && return 3
  [ -e "$OC_LEASE" ] && { rm -f "$OC_LEASE" 2>/dev/null || return 1; }
  ( set -o noclobber; : > "$OC_LEASE" ) 2>/dev/null || return 3
  printf 'pid=%s\nstart=%s\nrun_id=%s\nrole=%s\ninstall_path=%s\nutc=%s\n' \
    "$$" "$(_ocl_start "$$")" "oc-update-$$" "openclaw-cli-update" "$HOME/.openclaw" \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$OC_LEASE" 2>/dev/null || return 1
  trap '_ocl_release' EXIT
  return 0
}
_ocl_take
_ocl_rc=$?
if [ "$_ocl_rc" -eq 3 ]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] another updater owns this box (shared installation lease $OC_LEASE held by pid $(_ocl_rpid)) — STANDING DOWN, nothing changed" >> "$OC_LOG"
  exit 0
elif [ "$_ocl_rc" -ne 0 ]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] REFUSED: could not take the shared installation lease at $OC_LEASE — nothing changed" >> "$OC_LOG"
  exit 1
fi

# Check if gateway is busy (agent is active)
# Skip if a user session was active in the last 30 minutes
# This prevents interrupting active work
if [ -f "$HOME/.openclaw/skills/.update-pending" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Update already pending from earlier — skipping OpenClaw update" >> "$OC_LOG"
    exit 0
fi

# ---------------------------------------------------------------------------
# PRE-UPGRADE GATE: legacy `agents.list` schema
# ---------------------------------------------------------------------------
# THIS IS THE MOST DANGEROUS STEP IN THE FLEET. An OpenClaw upgrade runs here
# UNATTENDED, on every auto-update run, and it is the thing that actually moves
# a box onto a new OpenClaw build. (It used to be a bare `npm update -g
# openclaw`; since BFR error #21 it is ONLY the atomic procedure, below.)
#
# The 2026.7.2-beta line REJECTS the legacy `agents.list` key:
#     Gateway failed to start: Invalid config at ~/.openclaw/openclaw.json:
#     agents: Unrecognized key: "list"
# The gateway then exits 78 (EX_CONFIG) ~0.4s after start, launchd's KeepAlive +
# ThrottleInterval=10 respawns it every ~11s (701 boots in 10 days on the box
# this was measured on), and the crash-loop breaker eventually latches channel
# auto-start OFF -- at which point the box is COMPLETELY DARK. 24 queued
# deliveries were permanently lost that way.
#
# AND NOBODY SEES IT. The gateway LaunchAgent is written by the upstream
# openclaw CLI, and on boxes provisioned before the log-path fix it sets
# StandardErrorPath = /dev/null -- so the startup exception is DISCARDED. It
# survives only in /tmp/openclaw/openclaw-<date>.log. Ten days of investigation
# missed it for exactly that reason.
#
# A config that is FINE on the current build and FATAL on the next one is only
# ever catchable BEFORE the upgrade. So: migrate first, and if the migration
# cannot be proven good, DO NOT UPGRADE. A box left one version stale is
# recoverable; a box that is dark and silent is not.
#
# ⚠️ `openclaw doctor --fix` IS NOT THE MIGRATION, AND THIS SCRIPT NO LONGER
# CALLS IT. It was called here because the gateway's own error text prescribes
# it. Measured on 12 boxes: the config's SHA-256 was BYTE-IDENTICAL before and
# after. `openclaw config schema` on 2026.7.1 / 2026.7.1-2 lists the `agents`
# properties as exactly ["defaults","list"] -- there is no `entries` to migrate
# to. It also silently rewrote `agents.defaults.models` pins on one box. So the
# old path could only ever fail its own re-validation, and it risked model pins
# doing so.
#
# THE MIGRATION MUST HAPPEN INSIDE THE UPGRADE WINDOW. `additionalProperties:
# false` is set on `agents` in BOTH versions, so no config is valid on both; the
# currently installed runtime has NO `entries` reader, so migrating early
# enumerates ZERO agents (a silent total outage, worse than the crash-loop); and
# a running gateway re-serializes openclaw.json about once a minute from an
# in-memory model that only knows `agents.list`, reverting anything written
# while it is up. Only one procedure satisfies all of that, and this cron now
# delegates the whole upgrade to it: <oc-root>/scripts/oc-atomic-upgrade.sh.
#
# THREE-WAY DECISION, in order of preference:
#   1. the atomic tool is on this box  -> it performs the ENTIRE upgrade
#      (quiesce and prove it, install, migrate, verify, restart, prove stable,
#      roll back binary AND config on any failure).
#   2. the tool is absent (config clean, or no config to inspect) -> NO
#      UPGRADE THIS RUN. The bare `npm update -g openclaw` is gone: a clean
#      config does not make it safe. Big Fleet Roll error #21 -- npm rewrites
#      the package tree under a gateway that launchd KeepAlive keeps
#      respawning, the respawn imports a half-written tree ("Cannot find module
#      .../openclaw/dist/index.js"), dies, respawns, and the box never settles
#      (Sonatta: rolled back, then dark). The Sunday content update delivers
#      the atomic tool (update-skills.sh); the next Saturday then upgrades
#      through it. A box left one build stale is recoverable.
#   3. anything else -- legacy key present, unreadable config, no python3,
#      detector error -> BLOCK. An absence that cannot be proven is not an
#      absence, and a box left one build stale is recoverable.
OC_CFG="$HOME/.openclaw/openclaw.json"
[ -f "/data/.openclaw/openclaw.json" ] && OC_CFG="/data/.openclaw/openclaw.json"
OC_ROOT_DIR="$HOME/.openclaw"
[ -d "/data/.openclaw" ] && OC_ROOT_DIR="/data/.openclaw"
OC_ATOMIC="$OC_ROOT_DIR/scripts/oc-atomic-upgrade.sh"
OC_GATE_BLOCK=""
OC_UPGRADE_DONE=0

# ---------------------------------------------------------------------------
# R0 REGISTRY-PARITY GATE (2026-08-11) -- 'pre' snapshot, before the binary
# changes. Compact inline counterpart of registry_parity_gate() in
# update-skills.sh (same two checks, same rationale -- see that file's block
# comment for the full incident writeup). This IS the entry point that
# actually moves a box's OpenClaw version, so it is the single most
# important place in the fleet for this gate to run. Self-contained: this
# generated script has no shared function library to source from.
#
# PLACEMENT IS LOAD-BEARING (merge of origin/main, 2026-08-11): this block
# sits ABOVE the `agents.list` detect/atomic-upgrade section on purpose.
# That section can now delegate the ENTIRE upgrade to
# scripts/oc-atomic-upgrade.sh, which rewrites openclaw.json in place. If
# the 'pre' snapshot were taken after it, the baseline would already be
# post-migration and the 'post' regression check would be comparing a
# changed config against itself -- silently unable to see a loss caused by
# the very upgrade it exists to police. Taken here, 'pre' is the box
# exactly as the cron found it, and the absolute-floor check also refuses
# to hand an already-stripped box to the upgrade procedure at all.
# ---------------------------------------------------------------------------
OC_AGENTS_DIR="$HOME/.openclaw/agents"
[ -d "/data/.openclaw/agents" ] && OC_AGENTS_DIR="/data/.openclaw/agents"

oc_registry_snapshot() {
    # Prints "<verdict>|<count>|<ids>" for $1 (an openclaw.json path).
    local cfg="$1" py out rc
    if [ ! -f "$cfg" ]; then printf 'NO-CONFIG|0|\n'; return 0; fi
    if ! command -v python3 >/dev/null 2>&1; then printf 'UNDETERMINED|0|python3 not on PATH\n'; return 0; fi
    py="$(mktemp "${TMPDIR:-/tmp}/oc-registry-snapshot.XXXXXX")" || { printf 'UNDETERMINED|0|could not create a temp file\n'; return 0; }
    cat > "$py" <<'PYSNAP'
import json, sys
try:
    with open(sys.argv[1], encoding='utf-8') as fh:
        cfg = json.load(fh)
except Exception as e:
    print('UNDETERMINED|0|cannot parse as JSON: %s' % e); raise SystemExit(0)
if not isinstance(cfg, dict):
    print('UNDETERMINED|0|top level is not a JSON object'); raise SystemExit(0)
agents = cfg.get('agents')
if agents is None:
    print('ABSENT|0|no agents block'); raise SystemExit(0)
if not isinstance(agents, dict):
    print('UNDETERMINED|0|agents is not an object'); raise SystemExit(0)
has_entries = isinstance(agents.get('entries'), dict)
has_list = isinstance(agents.get('list'), list)
if not has_entries and not has_list:
    print('ABSENT|0|no agents.list or agents.entries key'); raise SystemExit(0)
ids = set()
if has_entries:
    for k in agents['entries'].keys():
        ids.add(str(k))
if has_list:
    for item in agents['list']:
        if isinstance(item, dict) and item.get('id'):
            ids.add(str(item['id']))
ids_sorted = sorted(ids)
print('OK|%d|%s' % (len(ids_sorted), ','.join(ids_sorted)))
PYSNAP
    rc=0
    out="$(python3 "$py" "$cfg" 2>&1)" || rc=$?
    rm -f "$py"
    if [ "$rc" -ne 0 ] || [ -z "$out" ]; then printf 'UNDETERMINED|0|detector exited %s\n' "$rc"; return 0; fi
    printf '%s\n' "$out"
}

oc_registry_dir_count() {
    local dir="$1" n=0 f
    if [ ! -d "$dir" ]; then printf '0'; return 0; fi
    for f in "$dir"/*/; do
        [ -d "$f" ] || continue
        n=$((n + 1))
    done
    printf '%s' "$n"
}

oc_registry_parity_check() {
    # $1 = "pre" or "post". Sets OC_GATE_BLOCK and returns non-zero on a
    # parity violation. Reads OC_REG_PRE_COUNT/OC_REG_PRE_IDS globals when
    # phase=post (set by the phase=pre call earlier in this same run).
    local phase="$1" snap verdict count ids dircount
    snap="$(oc_registry_snapshot "$OC_CFG")"
    verdict="${snap%%|*}"
    count="$(printf '%s' "$snap" | cut -d'|' -f2)"
    ids="$(printf '%s' "$snap" | cut -d'|' -f3-)"
    dircount="$(oc_registry_dir_count "$OC_AGENTS_DIR")"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [registry-parity:$phase] registry=$verdict count=$count ids=[${ids:-<none>}] agents-dir-count=$dircount" >> "$OC_LOG"

    if [ "$verdict" = "UNDETERMINED" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] [registry-parity:$phase] config unreadable -- count checks SKIPPED this phase (not silently passed)" >> "$OC_LOG"
        [ "$phase" = "pre" ] && OC_REG_PRE_VERDICT="UNDETERMINED"
        return 0
    fi
    case "$verdict" in ABSENT|NO-CONFIG) count=0 ;; esac

    if [ "$count" -le 1 ] && [ "$dircount" -gt 2 ]; then
        OC_GATE_BLOCK="registry-parity ABSOLUTE FLOOR ($phase): the registry declares only $count agent(s) while $OC_AGENTS_DIR holds $dircount agent subdirectories -- the exact signature of the 2026-08-11 registry-strip incident. This is the single most consequential gate in the fleet, because this cron is what actually moves a box's OpenClaw version -- refusing here, unattended at 23:59, is deliberately more conservative than the roll's own report-only detector."
        return 78
    fi

    if [ "$phase" = "pre" ]; then
        OC_REG_PRE_VERDICT="$verdict"; OC_REG_PRE_COUNT="$count"; OC_REG_PRE_IDS="$ids"
        return 0
    fi

    if [ -z "${OC_REG_PRE_VERDICT:-}" ] || [ "$OC_REG_PRE_VERDICT" = "UNDETERMINED" ] || [ "$OC_REG_PRE_VERDICT" = "NO-CONFIG" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] [registry-parity:post] no usable pre snapshot -- regression check skipped" >> "$OC_LOG"
        return 0
    fi
    if [ "$count" -lt "$OC_REG_PRE_COUNT" ]; then
        OC_GATE_BLOCK="registry-parity REGRESSION (post): the registry held $OC_REG_PRE_COUNT agent(s) before this upgrade and holds only $count now (pre ids=[${OC_REG_PRE_IDS:-<none>}] post ids=[${ids:-<none>}]). The binary version may already have changed -- this box needs a human, not an automated retry."
        return 78
    fi
    local missing="" id_pre save_ifs
    save_ifs="$IFS"; IFS=','
    for id_pre in $OC_REG_PRE_IDS; do
        IFS="$save_ifs"
        [ -z "$id_pre" ] && continue
        case ",${ids}," in
            *",${id_pre},"*) : ;;
            *) if [ -z "$missing" ]; then missing="$id_pre"; else missing="$missing,$id_pre"; fi ;;
        esac
        IFS=','
    done
    IFS="$save_ifs"
    if [ -n "$missing" ]; then
        OC_GATE_BLOCK="registry-parity IDENTITY LOSS (post): agent id(s) present before this upgrade are gone now: [$missing] (pre ids=[${OC_REG_PRE_IDS:-<none>}] post ids=[${ids:-<none>}]). Count alone did not catch this."
        return 78
    fi
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [registry-parity:post] no loss: pre=$OC_REG_PRE_COUNT post=$count, all pre ids still present" >> "$OC_LOG"
    return 0
}

OC_REG_RC=0
oc_registry_parity_check pre || OC_REG_RC=$?
if [ "$OC_REG_RC" -ne 0 ] && [ -n "$OC_GATE_BLOCK" ]; then
    {
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ############################################################"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] OPENCLAW UPGRADE BLOCKED (registry-parity, pre) on $(hostname 2>/dev/null || uname -n)"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')]   Reason: $OC_GATE_BLOCK"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')]   The OpenClaw upgrade was NOT run. \`openclaw config validate\`"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')]   would PASS on this box right now -- validity is not health."
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ############################################################"
    } >> "$OC_LOG"
    printf 'OPENCLAW UPGRADE BLOCKED %s\n  reason: %s\n  config: %s\n' \
        "$(date '+%Y-%m-%d %H:%M:%S')" "$OC_GATE_BLOCK" "$OC_CFG" \
        > "$HOME/.openclaw/skills/.openclaw-upgrade-blocked" 2>/dev/null
    exit 78
fi
if [ ! -f "$OC_CFG" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [agents-list] no config at $OC_CFG -- nothing to migrate" >> "$OC_LOG"
elif ! command -v python3 >/dev/null 2>&1; then
    # Cannot read the config, so cannot prove the key is absent. An unprovable
    # absence is not an absence -- refuse the upgrade rather than assume clean.
    OC_GATE_BLOCK="python3 unavailable -- the config could not be inspected at all"
else
    OC_DETECT_PY="$(mktemp "${TMPDIR:-/tmp}/oc-agents-list.XXXXXX")"
    cat > "$OC_DETECT_PY" <<'PYDETECT'
import json, sys
try:
    with open(sys.argv[1], encoding='utf-8') as fh:
        cfg = json.load(fh)
except Exception as e:
    print('UNDETERMINED|cannot parse as JSON: %s' % e); raise SystemExit(0)
if not isinstance(cfg, dict):
    print('UNDETERMINED|top level is not a JSON object'); raise SystemExit(0)
agents = cfg.get('agents')
if agents is None:
    print('ABSENT|no agents block'); raise SystemExit(0)
if not isinstance(agents, dict):
    print('UNDETERMINED|agents is not an object'); raise SystemExit(0)
print('ABSENT|no legacy list key' if 'list' not in agents else 'PRESENT|legacy agents.list key is present')
PYDETECT
    OC_VERDICT="$(python3 "$OC_DETECT_PY" "$OC_CFG" 2>&1)"
    OC_DETECT_RC=$?

    if [ "$OC_DETECT_RC" -ne 0 ] || [ -z "$OC_VERDICT" ]; then
        OC_GATE_BLOCK="the schema detector failed (rc=$OC_DETECT_RC): ${OC_VERDICT:-no output}"
    else
        case "${OC_VERDICT%%|*}" in
            ABSENT)
                echo "[$(date '+%Y-%m-%d %H:%M:%S')] [agents-list] clean -- no legacy agents.list key" >> "$OC_LOG"
                # Even with nothing to migrate, prefer the atomic path when it is
                # here: it stops the gateway before changing the binary, proves
                # it came back and STAYED up, and rolls the binary back if it did
                # not. A plain `npm update -g openclaw` does none of that -- it
                # swaps the binary under a running gateway and never looks again.
                if [ -f "$OC_ATOMIC" ]; then
                    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [agents-list] clean box, but using the atomic path anyway for its quiesce + rollback + stability proof" >> "$OC_LOG"
                    bash "$OC_ATOMIC" --upgrade >> "$OC_LOG" 2>&1
                    OC_ATOMIC_RC=$?
                    case "$OC_ATOMIC_RC" in
                        0)  OC_UPGRADE_DONE=1 ;;
                        78) OC_GATE_BLOCK="the atomic upgrade REFUSED and rolled back (exit 78) on a CLEAN box. This box is exactly as it was." ;;
                        70) OC_GATE_BLOCK="the atomic upgrade's ROLLBACK ITSELF FAILED (exit 70) on a CLEAN box. THIS BOX NEEDS A HUMAN NOW." ;;
                        *)  OC_GATE_BLOCK="the atomic upgrade exited $OC_ATOMIC_RC (undetermined) on a CLEAN box." ;;
                    esac
                else
                    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [agents-list] clean config, but the atomic tool is not on this box (looked for $OC_ATOMIC) -- NOT upgrading with a bare npm update (BFR error #21); the Sunday content update delivers the tool" >> "$OC_LOG"
                fi
                ;;
            PRESENT)
                echo "[$(date '+%Y-%m-%d %H:%M:%S')] [agents-list] LEGACY SCHEMA DETECTED -- this box cannot take a plain npm upgrade" >> "$OC_LOG"
                if [ ! -f "$OC_ATOMIC" ]; then
                    OC_GATE_BLOCK="legacy agents.list is present and the atomic upgrade procedure is NOT on this box (looked for $OC_ATOMIC). Run update-skills.sh once to deliver it, then this cron can migrate."
                else
                    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [agents-list] delegating the ENTIRE upgrade to $OC_ATOMIC --upgrade" >> "$OC_LOG"
                    bash "$OC_ATOMIC" --upgrade >> "$OC_LOG" 2>&1
                    OC_ATOMIC_RC=$?
                    case "$OC_ATOMIC_RC" in
                        0)
                            OC_UPGRADE_DONE=1
                            echo "[$(date '+%Y-%m-%d %H:%M:%S')] [agents-list] ATOMIC UPGRADE COMPLETE -- binary installed, config migrated to agents.entries, gateway proven stable" >> "$OC_LOG"
                            ;;
                        78)
                            OC_GATE_BLOCK="the atomic upgrade REFUSED and rolled back (exit 78). This box is exactly as it was -- old binary, old config, gateway running. See the log above for the step that refused."
                            ;;
                        70)
                            OC_GATE_BLOCK="the atomic upgrade's ROLLBACK ITSELF FAILED (exit 70). THIS BOX NEEDS A HUMAN NOW -- it may be on a build its config does not match. See the log above for the exact repair commands."
                            ;;
                        *)
                            OC_GATE_BLOCK="the atomic upgrade exited $OC_ATOMIC_RC (undetermined). Nothing is assumed about this box's state; the upgrade is treated as NOT done."
                            ;;
                    esac
                fi
                ;;
            *)
                OC_GATE_BLOCK="the config could not be inspected: ${OC_VERDICT#*|}"
                ;;
        esac
    fi
    rm -f "$OC_DETECT_PY"
fi

if [ -n "$OC_GATE_BLOCK" ]; then
    # Fail closed. Do NOT upgrade. Leave a marker where a human and the Sunday
    # content roll will both trip over it -- a line in a log nobody reads is how
    # this stayed invisible for ten days.
    {
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ############################################################"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] OPENCLAW UPGRADE BLOCKED on $(hostname 2>/dev/null || uname -n)"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')]   Reason: $OC_GATE_BLOCK"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')]   Config: $OC_CFG"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')]   The OpenClaw upgrade was NOT run. This box stays on its"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')]   current build ON PURPOSE: upgrading it with a legacy"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')]   'agents.list' config makes the gateway exit 78 every ~11s"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')]   until the crash-loop breaker latches channels OFF and the"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')]   box goes completely dark."
        echo "[$(date '+%Y-%m-%d %H:%M:%S')]   FIX:    bash $OC_ATOMIC --upgrade"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')]   NOT 'openclaw doctor --fix' -- measured on 12 boxes, the"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')]   config SHA-256 was IDENTICAL before and after, and it"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')]   silently rewrote agents.defaults.models pins on one box."
        echo "[$(date '+%Y-%m-%d %H:%M:%S')]   VERIFY: bash scripts/qc-assert-legacy-agents-list.sh"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ############################################################"
    } >> "$OC_LOG"
    printf 'OPENCLAW UPGRADE BLOCKED %s\n  reason: %s\n  config: %s\n  fix:    bash %s --upgrade\n  note:   `openclaw doctor --fix` does NOT perform this migration.\n' \
        "$(date '+%Y-%m-%d %H:%M:%S')" "$OC_GATE_BLOCK" "$OC_CFG" "$OC_ATOMIC" \
        > "$HOME/.openclaw/skills/.openclaw-upgrade-blocked" 2>/dev/null
    exit 78
fi

# The box is clear. Remove any stale block marker from a previous run.
rm -f "$HOME/.openclaw/skills/.openclaw-upgrade-blocked" 2>/dev/null


# The OpenClaw CLI is upgraded ONLY by the atomic procedure above
# (<oc-root>/scripts/oc-atomic-upgrade.sh --upgrade): it boots the gateway job
# out of launchd and proves it stopped (so KeepAlive cannot respawn it into a
# half-written tree), installs the binary, proves the gateway came back and
# STAYED up, and rolls the binary back otherwise. A bare `npm update -g openclaw` does none of that
# and is never run from here (BFR error #21). When the atomic procedure did not
# run (tool absent, or no config to inspect) nothing is installed this run.
if [ "$OC_UPGRADE_DONE" = "1" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] OpenClaw upgraded by the atomic procedure" >> "$OC_LOG"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] No OpenClaw upgrade this run: the atomic procedure did not run (tool absent or no config), and a bare npm update is never used" >> "$OC_LOG"
fi
OC_VERSION=$(openclaw --version 2>/dev/null)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] OpenClaw is at: $OC_VERSION" >> "$OC_LOG"

# R0 REGISTRY-PARITY GATE -- 'post' snapshot, after the binary has changed and
# the gateway has had a chance to touch the config. A violation here fires
# AFTER npm has already run -- there is no "undo" available to this cron (it
# does not restart the gateway or touch the binary), so this is a LOUD
# escalation-quality alarm, not a preventive block: the box's next state is
# whatever npm + the gateway left it in, and a human needs to know NOW.
OC_REG_POST_RC=0
oc_registry_parity_check post || OC_REG_POST_RC=$?
if [ "$OC_REG_POST_RC" -ne 0 ] && [ -n "$OC_GATE_BLOCK" ]; then
    {
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ############################################################"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] REGISTRY-PARITY VIOLATION AFTER UPGRADE on $(hostname 2>/dev/null || uname -n)"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')]   OpenClaw WAS updated to: $OC_VERSION -- this alarm fires AFTER that,"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')]   because a registry loss can only be measured once it has happened."
        echo "[$(date '+%Y-%m-%d %H:%M:%S')]   Reason: $OC_GATE_BLOCK"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')]   THIS BOX NEEDS A HUMAN NOW. Do not assume the roster loss is safe"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')]   just because the upgrade itself reported success."
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ############################################################"
    } >> "$OC_LOG"
    printf 'REGISTRY-PARITY VIOLATION AFTER UPGRADE %s\n  reason: %s\n  config: %s\n  openclaw_version: %s\n' \
        "$(date '+%Y-%m-%d %H:%M:%S')" "$OC_GATE_BLOCK" "$OC_CFG" "$OC_VERSION" \
        > "$HOME/.openclaw/skills/.openclaw-upgrade-blocked" 2>/dev/null
fi
