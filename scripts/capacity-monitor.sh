#!/usr/bin/env bash
# capacity-monitor.sh — hardware-aware agent-concurrency + heartbeat-stagger monitor.
#
# THE PROBLEM (WS-8, 2026-06-01):
#   Concurrency was governed by THREE conflicting numbers, none of them tied to
#   the box's actual strength:
#     1. install.sh writes  agents.defaults.subagents.maxConcurrent = 100  on
#        EVERY box — a base 8GB Mac mini and a 64GB VPS get the identical 100.
#     2. force-update.sh prose says "Max 10 concurrent on Mac, max 5 on VPS".
#     3. scripts/check-wave-concurrency.sh hard-codes a binary Mac=10 / VPS=5.
#   A weak box told to run 100 concurrent agents (each with its own heartbeat
#   cron firing on the same cadence) collides, thrashes RAM, and crashes the
#   gateway — exactly the failure WS-8 exists to prevent. None of the three
#   numbers knows whether this is a 4GB / 2-core micro-VPS or a 32GB / 12-core
#   M2 Pro Mac mini.
#
# WHAT THIS DOES (the capacity model):
#   1. Detect real hardware — physical CPU cores + total RAM (GB) — using
#      sysctl on macOS and /proc on Linux/VPS (no external deps beyond coreutils).
#   2. Compute a SAFE max-concurrent-agents from a RAM-first model:
#        safe = min( floor(usableRAM_GB / RAM_PER_AGENT_GB),
#                    cores * CORES_MULT )
#      clamped to [MIN_AGENTS, MAX_AGENTS]. RAM is the binding constraint for
#      LLM agent processes, so it leads; cores cap parallel CPU pressure.
#   3. Compute a HEARTBEAT STAGGER: spread N agent heartbeats across a window so
#      they never all fire in the same minute (the collision Trevor described).
#        stagger_seconds = max( MIN_STAGGER_SEC,
#                               floor(HEARTBEAT_WINDOW_SEC / max(1, safe)) )
#   4. Write the computed maxConcurrent into BOTH concurrency keys:
#        agents.defaults.maxConcurrent            ← cap on ALL agent runs
#        agents.defaults.subagents.maxConcurrent  ← cap on subagent fanout
#      ONLY when either differs, with a timestamped backup + atomic write.
#      Reconciles the "100 everywhere" bug down to the box's real capacity.
#
#      WHY BOTH (incident 2026-08-01 — the 5-day unhealed cap):
#        This script used to reconcile ONLY the subagents key. On the operator
#        box BOTH keys were set to 500 out-of-band on 2026-07-27. The 15-minute
#        tick dutifully healed subagents 500 -> 12 and reported success, while
#        agents.defaults.maxConcurrent — the TOP-LEVEL cap governing every agent
#        run — stayed at 500 for five days, managed by NOTHING. A 12-core/24GB
#        box allowing 500 concurrent runs exhausted RAM, thrashed swap, and made
#        every response crawl. Repeated manual fixes "did not stick" because the
#        healer was blind to the key that mattered. Fleet-wide blind spot: this
#        script ships to every box.
#
#      PRESENT-ONLY HEAL for agents.defaults.maxConcurrent (deliberate):
#        The runtime's AgentDefaultsSchema is .strict(). Injecting this key into
#        a config on a runtime that predates it would make the runtime reject
#        the box's ENTIRE config. So the top-level key is reconciled when it is
#        PRESENT and never created when absent — an absent key means the runtime
#        applies its own default and there is nothing to clobber. The subagents
#        key is created as before (install.sh already writes it fleet-wide).
#   5. Write a machine-readable .capacity-profile.json next to openclaw.json so
#      check-wave-concurrency.sh, the heartbeat scheduler, and the fleet
#      heartbeat can all read ONE source of truth instead of three.
#
# DESIGN: mirrors scripts/telegram-offset-healthcheck.sh — host-level, idempotent,
#   platform-detected OC_ROOT, logs to a dedicated file, backup-before-write,
#   clear exit-code contract. Safe to run from a 15-minute host cron.
#
# OVERRIDES (env vars — operator escape hatches; all optional):
#   OC_CAP_RAM_PER_AGENT_GB   RAM budgeted per concurrent agent   (default 1.5)
#   OC_CAP_CORES_MULT         agents allowed per core             (default 2)
#   OC_CAP_MIN_AGENTS         hard floor                          (default 2)
#   OC_CAP_MAX_AGENTS         hard ceiling                        (default 12 Mac / 8 VPS)
#   OC_CAP_RAM_RESERVE_GB     RAM kept for OS + gateway           (default 2)
#   OC_CAP_HEARTBEAT_WINDOW   stagger window, seconds             (default 1800 = 30m)
#   OC_CAP_MIN_STAGGER_SEC    min seconds between heartbeats      (default 20)
#   OC_CAP_FORCE              "1" = rewrite config even if unchanged
#   OC_CAP_DRY_RUN            "1" = compute + log, never write
#
#   The overrides are the DELIBERATE-RAISE path and are intentionally kept
#   (OC_CAP_MAX_AGENTS is how an operator raises a cap on purpose). Three
#   independent checks make an absurd cap impossible to miss on the 15-minute
#   tick — none of them clamps or fails:
#     RUNAWAY CAP (computed)   the value this tick will write is above
#                              min(cores*4, 64)
#     RUNAWAY CAP (requested)  an EXPLICIT OC_CAP_MAX_AGENTS / OC_CAP_MIN_AGENTS
#                              is above that ceiling. Needed because
#                              OC_CAP_MAX_AGENTS is a CLAMP: raising it can never
#                              push the computed value above cores*CORES_MULT,
#                              so before 2026-08-02 the documented knob could not
#                              reach the guard at all (OC_CAP_MAX_AGENTS=500 on a
#                              12-core box warned exactly zero times).
#     ABSURD CAP IN CONFIG     the value FOUND in openclaw.json is above the
#                              ceiling. This is the case that actually happened:
#                              a hand-written 500 the script never computed,
#                              while the computed value was a healthy 12.
#   Platform defaults (12 Mac / 8 VPS) never warn, so the guard stays credible.
#
# Exit codes:
#   0  computed successfully (config in sync, or updated, or dry-run)
#   2  could not run (no OpenClaw root / no python3 / unreadable config) — non-fatal
#
# Wiring (see INSTALL / CHANGELOG):
#   - a 15-minute host cron, same shape as the offset healthcheck watchdog
#   - re-run after any hardware change (VPS resize, Mac upgrade)

set -u

# ─── Tunables (env-overridable) ───────────────────────────────────────────────
RAM_PER_AGENT_GB="${OC_CAP_RAM_PER_AGENT_GB:-1.5}"
CORES_MULT="${OC_CAP_CORES_MULT:-2}"
MIN_AGENTS="${OC_CAP_MIN_AGENTS:-2}"
RAM_RESERVE_GB="${OC_CAP_RAM_RESERVE_GB:-2}"
HEARTBEAT_WINDOW="${OC_CAP_HEARTBEAT_WINDOW:-1800}"
MIN_STAGGER_SEC="${OC_CAP_MIN_STAGGER_SEC:-20}"
FORCE="${OC_CAP_FORCE:-0}"
DRY_RUN="${OC_CAP_DRY_RUN:-0}"

# ─── Platform detection (VPS /data first, Mac fallback) ───────────────────────
if [[ -d /data/.openclaw ]]; then
  OC_ROOT=/data/.openclaw
  PLATFORM=vps
  MAX_AGENTS_DEFAULT=8
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
  PLATFORM=mac
  MAX_AGENTS_DEFAULT=12
else
  echo "[capacity-monitor] no OpenClaw root found; nothing to do" >&2
  exit 2
fi
MAX_AGENTS="${OC_CAP_MAX_AGENTS:-$MAX_AGENTS_DEFAULT}"

CONFIG_FILE="$OC_ROOT/openclaw.json"
PROFILE_FILE="$OC_ROOT/.capacity-profile.json"
CAP_LOG="$OC_ROOT/capacity-monitor.log"

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() {
  printf '%s [%-5s] %s\n' "$(ts)" "$1" "$2" >> "$CAP_LOG" 2>/dev/null || true
  printf '%s [%-5s] %s\n' "$(ts)" "$1" "$2"
}

# ─── Preflight ────────────────────────────────────────────────────────────────
if ! command -v python3 >/dev/null 2>&1; then
  log "WARN" "python3 not on PATH — required for JSON math + write; skipping"
  exit 2
fi
if [[ ! -f "$CONFIG_FILE" ]]; then
  log "WARN" "config not found: $CONFIG_FILE — skipping (box not onboarded yet)"
  exit 2
fi

# ─── 1. Detect hardware (cross-platform; no external deps) ────────────────────
CORES=""
RAM_GB=""
if [[ "$(uname -s)" == "Darwin" ]]; then
  CORES=$(sysctl -n hw.physicalcpu 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null)
  RAM_BYTES=$(sysctl -n hw.memsize 2>/dev/null)
  [[ -n "$RAM_BYTES" ]] && RAM_GB=$(python3 -c "print(round(${RAM_BYTES}/1024/1024/1024, 2))" 2>/dev/null)
else
  # Linux / VPS (containers expose /proc; respect a cgroup CPU quota if present)
  CORES=$(nproc 2>/dev/null || grep -c ^processor /proc/cpuinfo 2>/dev/null)
  MEMKB=$(awk '/MemTotal/{print $2}' /proc/meminfo 2>/dev/null)
  [[ -n "$MEMKB" ]] && RAM_GB=$(python3 -c "print(round(${MEMKB}/1024/1024, 2))" 2>/dev/null)
  # cgroup v2 / v1 RAM limit (Docker often caps below host RAM) — take the lower.
  for cg in /sys/fs/cgroup/memory.max /sys/fs/cgroup/memory/memory.limit_in_bytes; do
    if [[ -r "$cg" ]]; then
      LIMIT=$(cat "$cg" 2>/dev/null)
      if [[ "$LIMIT" =~ ^[0-9]+$ ]] && [[ "$LIMIT" -gt 0 ]] && [[ "$LIMIT" -lt 1000000000000000 ]]; then
        CG_GB=$(python3 -c "print(round(${LIMIT}/1024/1024/1024, 2))" 2>/dev/null)
        RAM_GB=$(python3 -c "print(min(${RAM_GB:-9999}, ${CG_GB}))" 2>/dev/null)
      fi
    fi
  done
fi

# Sane fallbacks if detection failed.
[[ "$CORES" =~ ^[0-9]+$ ]] || CORES=2
python3 -c "float('${RAM_GB:-x}')" >/dev/null 2>&1 || RAM_GB=4

# ─── 2/3. Compute safe maxConcurrent + heartbeat stagger ──────────────────────
read -r SAFE STAGGER <<EOF
$(python3 - "$RAM_GB" "$CORES" "$RAM_PER_AGENT_GB" "$CORES_MULT" "$MIN_AGENTS" "$MAX_AGENTS" "$RAM_RESERVE_GB" "$HEARTBEAT_WINDOW" "$MIN_STAGGER_SEC" <<'PYEOF'
import sys, math
ram_gb, cores, ram_per, cores_mult, min_a, max_a, reserve, window, min_stag = (
    float(sys.argv[1]), int(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]),
    int(sys.argv[5]), int(sys.argv[6]), float(sys.argv[7]), int(sys.argv[8]), int(sys.argv[9]),
)
usable_ram = max(0.0, ram_gb - reserve)
by_ram = math.floor(usable_ram / ram_per) if ram_per > 0 else max_a
by_cpu = math.floor(cores * cores_mult)
safe = min(by_ram, by_cpu)
safe = max(min_a, min(max_a, safe))
stagger = max(min_stag, window // max(1, safe))
print(f"{safe} {stagger}")
PYEOF
)
EOF
[[ "$SAFE" =~ ^[0-9]+$ ]] || { log "WARN" "capacity math failed (RAM=$RAM_GB cores=$CORES) — skipping"; exit 2; }

log "INFO" "platform=$PLATFORM cores=$CORES ram=${RAM_GB}GB → safe maxConcurrent=$SAFE, heartbeat stagger=${STAGGER}s (window=${HEARTBEAT_WINDOW}s)"

# ─── Runaway guard (incident 2026-08-01; reachability repaired 2026-08-02) ────
# THE SAFETY CEILING: min(cores*4, 64).
WARN_CEILING=$(( CORES * 4 ))
[[ "$WARN_CEILING" -gt 64 ]] && WARN_CEILING=64

# WHY THIS GUARD IS NOW THREE CHECKS, NOT ONE
# -------------------------------------------
# The original guard tested ONLY the COMPUTED value, and was therefore
# UNREACHABLE through its own documented override:
#
#   safe = max(MIN_AGENTS, min(MAX_AGENTS, min(by_ram, cores*CORES_MULT)))
#
# OC_CAP_MAX_AGENTS is a CLAMP. Raising it can never push `safe` above
# cores*CORES_MULT (default cores*2), while the guard fires above cores*4. So
# on a 12-core box `OC_CAP_MAX_AGENTS=500` yielded safe=14 and ZERO warnings;
# even `OC_CAP_RAM_PER_AGENT_GB=0.01` only reached 24, still silent. The only
# knob that could ever trip it was OC_CAP_MIN_AGENTS — a floor, applied last —
# which the rationale never mentions and no operator would reach for. The guard
# read as protection while protecting nothing through the documented path.
#
#   (1) COMPUTED    — the value this tick will write.
#   (2) REQUESTED   — an EXPLICIT OC_CAP_MAX_AGENTS / OC_CAP_MIN_AGENTS above
#                     the ceiling. An operator who asks for 500 has asked for
#                     500 and must be told so, whether or not today's RAM/core
#                     model happens to grant it. Only explicit overrides count:
#                     the platform defaults (12 Mac / 8 VPS) must never warn.
#   (3) FOUND       — see the config scan below; that is the case that actually
#                     happened.
# None of the three clamps or fails: OC_CAP_* is a deliberate escape hatch. They
# make a raise impossible to miss on the 15-minute tick.
RUNAWAY_WHY=""
[[ "$SAFE" -gt "$WARN_CEILING" ]] && RUNAWAY_WHY="computed maxConcurrent=$SAFE"
if [[ -n "${OC_CAP_MAX_AGENTS:-}" && "$MAX_AGENTS" =~ ^[0-9]+$ && "$MAX_AGENTS" -gt "$WARN_CEILING" ]]; then
  RUNAWAY_WHY="${RUNAWAY_WHY:+$RUNAWAY_WHY, }OC_CAP_MAX_AGENTS=$MAX_AGENTS requested"
fi
if [[ -n "${OC_CAP_MIN_AGENTS:-}" && "$MIN_AGENTS" =~ ^[0-9]+$ && "$MIN_AGENTS" -gt "$WARN_CEILING" ]]; then
  RUNAWAY_WHY="${RUNAWAY_WHY:+$RUNAWAY_WHY, }OC_CAP_MIN_AGENTS=$MIN_AGENTS requested"
fi
if [[ -n "$RUNAWAY_WHY" ]]; then
  log "WARN" "RUNAWAY CAP: $RUNAWAY_WHY exceeds the safety ceiling $WARN_CEILING (min(cores*4=$((CORES * 4)), 64)) on a ${CORES}-core/${RAM_GB}GB box. Only OC_CAP_* env overrides can produce this. A cap this high lets cron storms, heartbeat waves and subagent fanout exhaust RAM and thrash swap (live incident 2026-08-01: 500 on a 12-core box crushed it for 5 days). Confirm this is a DELIBERATE operator raise, or unset the OC_CAP_* overrides."
fi

# ─── Absurd-value-IN-CONFIG guard (the case that actually happened) ───────────
# The runaway guard above watches values this script COMPUTES. The 2026-08-01
# incident was not a computed value at all — it was a hand-written
# `maxConcurrent: 500` sitting in openclaw.json, put there out-of-band. The
# computed value was a healthy 12 the whole time, so a computed-value guard
# would not have said a word about the very config that crushed the box.
#
# So: warn on what is FOUND in the config, before any heal is attempted. This
# fires even under OC_CAP_DRY_RUN=1, and even on the tick that heals it, because
# "an absurd value reached this config" is an event worth surfacing on its own —
# something wrote it, and that something will likely write it again.
read -r FOUND_SUB FOUND_DEF <<EOF
$(python3 - "$CONFIG_FILE" <<'PYEOF'
import json, sys
try:
    cfg = json.load(open(sys.argv[1]))
except Exception:
    print("- -"); raise SystemExit(0)
d = (cfg.get("agents") or {}).get("defaults") or {}
s = d.get("subagents") or {}
def norm(v):
    return str(v) if isinstance(v, int) and not isinstance(v, bool) else "-"
print(f"{norm(s.get('maxConcurrent'))} {norm(d.get('maxConcurrent'))}")
PYEOF
)
EOF
FOUND_SUB="${FOUND_SUB:--}"
FOUND_DEF="${FOUND_DEF:--}"
FOUND_WHY=""
[[ "$FOUND_SUB" =~ ^[0-9]+$ && "$FOUND_SUB" -gt "$WARN_CEILING" ]] && \
  FOUND_WHY="agents.defaults.subagents.maxConcurrent=$FOUND_SUB"
[[ "$FOUND_DEF" =~ ^[0-9]+$ && "$FOUND_DEF" -gt "$WARN_CEILING" ]] && \
  FOUND_WHY="${FOUND_WHY:+$FOUND_WHY, }agents.defaults.maxConcurrent=$FOUND_DEF"
if [[ -n "$FOUND_WHY" ]]; then
  log "WARN" "ABSURD CAP IN CONFIG: $CONFIG_FILE holds $FOUND_WHY, above the safety ceiling $WARN_CEILING for this ${CORES}-core/${RAM_GB}GB box. This script did not compute that value — something wrote it out-of-band, and whatever wrote it can write it again. This is the exact shape of the 2026-08-01 incident (a hand-written 500 that sat unhealed for five days and exhausted RAM). This tick will reconcile it to $SAFE unless dry-run; find and fix the writer."
fi

# ─── 4/5. Reconcile config + write the capacity profile (atomic, backed up) ───
export OC_CONFIG_FILE="$CONFIG_FILE" OC_PROFILE_FILE="$PROFILE_FILE"
export OC_SAFE="$SAFE" OC_STAGGER="$STAGGER" OC_PLATFORM="$PLATFORM"
export OC_CORES="$CORES" OC_RAM_GB="$RAM_GB" OC_FORCE="$FORCE" OC_DRY="$DRY_RUN"
export OC_HEARTBEAT_WINDOW="$HEARTBEAT_WINDOW"
export OC_RAM_PER_AGENT_GB="$RAM_PER_AGENT_GB"

WRITE_RESULT=$(python3 <<'PYEOF'
import json, os, sys, tempfile, datetime

cfg_file = os.environ["OC_CONFIG_FILE"]
profile_file = os.environ["OC_PROFILE_FILE"]
safe = int(os.environ["OC_SAFE"])
stagger = int(os.environ["OC_STAGGER"])
force = os.environ.get("OC_FORCE", "0") == "1"
dry = os.environ.get("OC_DRY", "0") == "1"
now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

try:
    with open(cfg_file) as f:
        cfg = json.load(f)
except Exception as e:
    print(f"ERR\tconfig unreadable: {e}")
    sys.exit(0)

defaults = cfg.setdefault("agents", {}).setdefault("defaults", {})
sub = defaults.setdefault("subagents", {})

# Key 1 — agents.defaults.subagents.maxConcurrent (created if absent; install.sh
# already writes this key on every box, so it is schema-proven fleet-wide).
prev = sub.get("maxConcurrent")

# Key 2 — agents.defaults.maxConcurrent, the top-level cap on ALL agent runs.
# PRESENT-ONLY: AgentDefaultsSchema is .strict(), so creating this key on a
# runtime that predates it would reject the box's whole config. Absent = the
# runtime's own default is in force and there is nothing to reconcile.
has_defaults_key = "maxConcurrent" in defaults
prev_defaults = defaults.get("maxConcurrent")

# Always write the capacity profile (source of truth for readers).
profile = {
    "computedAt": now,
    "platform": os.environ["OC_PLATFORM"],
    "cores": int(os.environ["OC_CORES"]),
    "ramGB": float(os.environ["OC_RAM_GB"]),
    "ramPerAgentGB": float(os.environ["OC_RAM_PER_AGENT_GB"]),
    "maxConcurrentAgents": safe,
    "heartbeatStaggerSeconds": stagger,
    "heartbeatWindowSeconds": int(os.environ["OC_HEARTBEAT_WINDOW"]),
    "previousMaxConcurrent": prev,
    "previousDefaultsMaxConcurrent": prev_defaults,
    "defaultsMaxConcurrentPresent": has_defaults_key,
    "source": "capacity-monitor.sh (WS-8)",
}
if not dry:
    try:
        fd, tmp = tempfile.mkstemp(prefix=".capprofile.", suffix=".json.tmp",
                                   dir=os.path.dirname(profile_file))
        with os.fdopen(fd, "w") as f:
            json.dump(profile, f, indent=2); f.write("\n")
        os.replace(tmp, profile_file)
    except Exception as e:
        print(f"WARN\tcould not write profile: {e}")

# "changed" is true if EITHER key is out of sync. The 2026-08-01 incident is
# exactly the case where the subagents key was already healed and only the
# top-level key was still at 500 — under the old single-key test that read as
# "in sync" and the box was never healed.
sub_changed = (prev != safe)
defaults_changed = has_defaults_key and (prev_defaults != safe)
changed = sub_changed or defaults_changed

def _keysum():
    d = f"defaults.maxConcurrent {prev_defaults} -> {safe}" if has_defaults_key \
        else "defaults.maxConcurrent absent (runtime default; not created — .strict() schema)"
    return f"subagents.maxConcurrent {prev} -> {safe}; {d}"

if not changed and not force:
    seen = f"subagents.maxConcurrent={safe}" + (
        f", defaults.maxConcurrent={prev_defaults}" if has_defaults_key
        else ", defaults.maxConcurrent absent (runtime default)")
    print(f"OK\tboth concurrency keys already in sync at {safe} ({seen}); profile written")
    sys.exit(0)
if dry:
    print(f"DRY\twould set {_keysum()} (dry-run)")
    sys.exit(0)

# Backup + atomic write of openclaw.json.
try:
    backup = f"{cfg_file}.bak.capacity.{now.replace(':','').replace('-','')}"
    with open(backup, "w") as b:
        json.dump(cfg, b, indent=2)
except Exception:
    backup = "(backup failed)"
sub["maxConcurrent"] = safe
if has_defaults_key:
    defaults["maxConcurrent"] = safe
try:
    fd, tmp = tempfile.mkstemp(prefix=".openclaw.", suffix=".json.tmp",
                               dir=os.path.dirname(cfg_file))
    with os.fdopen(fd, "w") as f:
        json.dump(cfg, f, indent=2); f.write("\n")
    os.replace(tmp, cfg_file)
    print(f"HEAL\t{_keysum()}; backup {backup}")
except Exception as e:
    if os.path.exists(tmp):
        os.remove(tmp)
    print(f"ERR\tatomic write failed: {e}")
PYEOF
)

STATUS="${WRITE_RESULT%%$'\t'*}"
MSG="${WRITE_RESULT#*$'\t'}"
case "$STATUS" in
  HEAL) log "HEAL" "$MSG"; log "INFO" "restart the gateway to apply the new concurrency cap if agents are mid-flight" ;;
  OK)   log "INFO" "$MSG" ;;
  DRY)  log "INFO" "$MSG" ;;
  WARN) log "WARN" "$MSG" ;;
  ERR)  log "ERROR" "$MSG"; exit 2 ;;
  *)    log "WARN" "unexpected writer output: $WRITE_RESULT" ;;
esac

log "INFO" "capacity profile → $PROFILE_FILE"
exit 0
