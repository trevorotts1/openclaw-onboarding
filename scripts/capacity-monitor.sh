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
#   4. Write the computed maxConcurrent into
#        agents.defaults.subagents.maxConcurrent
#      (the SAME schema-valid key install.sh already uses — verified valid on
#      2026.5.22) ONLY when it differs, with a timestamped backup + atomic write.
#      Reconciles the "100 everywhere" bug down to the box's real capacity.
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

sub = cfg.setdefault("agents", {}).setdefault("defaults", {}).setdefault("subagents", {})
prev = sub.get("maxConcurrent")

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

changed = (prev != safe)
if not changed and not force:
    print(f"OK\tmaxConcurrent already {safe} (in sync); profile written")
    sys.exit(0)
if dry:
    print(f"DRY\twould set maxConcurrent {prev} -> {safe} (dry-run)")
    sys.exit(0)

# Backup + atomic write of openclaw.json.
try:
    backup = f"{cfg_file}.bak.capacity.{now.replace(':','').replace('-','')}"
    with open(backup, "w") as b:
        json.dump(cfg, b, indent=2)
except Exception:
    backup = "(backup failed)"
sub["maxConcurrent"] = safe
try:
    fd, tmp = tempfile.mkstemp(prefix=".openclaw.", suffix=".json.tmp",
                               dir=os.path.dirname(cfg_file))
    with os.fdopen(fd, "w") as f:
        json.dump(cfg, f, indent=2); f.write("\n")
    os.replace(tmp, cfg_file)
    print(f"HEAL\tmaxConcurrent {prev} -> {safe}; backup {backup}")
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
