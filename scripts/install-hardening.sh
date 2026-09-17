#!/usr/bin/env bash
# install-hardening.sh (Mac) — defensive checks/fixes from 2-day forensics
# (2026-05-23 / 2026-05-24). Mac-applicable subset of the VPS bundle.
#
# Each function is independently safe (idempotent, no-op when already correct).
# All functions return 0 unconditionally — hardening is best-effort.
#
# Mac-applicable findings this script implements:
#   #13  hooks.token auto-generate when hooks.enabled is true without one
#   #16  brew (not apt) — guard any package-install assumption
#   #20  yt-dlp + whisper-cpp + ffmpeg backfill if missing (Skill 22)
set -uo pipefail

_oc_root() {
    if [[ -d "$HOME/.openclaw" ]]; then
        echo "$HOME/.openclaw"
    else
        echo ""
    fi
}

_log() { echo "[install-hardening] $*"; }

# ─── #13: hooks.token auto-generate ──────────────────────────────────────────
harden_hooks_token() {
    local oc_root
    oc_root="$(_oc_root)"
    [ -z "$oc_root" ] && return 0
    local cfg="$oc_root/openclaw.json"
    [ -f "$cfg" ] || return 0

    python3 - "$cfg" <<'PYEOF' || true
import json, sys, secrets, os
p = sys.argv[1]
try:
    d = json.load(open(p))
except Exception as e:
    print(f"[install-hardening] hooks.token check: cannot parse {p}: {e}", file=sys.stderr)
    sys.exit(0)
hooks = d.get("hooks") or {}
if not hooks.get("enabled"):
    sys.exit(0)
if hooks.get("token"):
    sys.exit(0)
hooks["token"] = secrets.token_hex(32)
d["hooks"] = hooks
tmp = p + ".tmp-hardening"
with open(tmp, "w") as f:
    json.dump(d, f, indent=2)
    f.write("\n")
os.replace(tmp, p)
print(f"[install-hardening] hooks.enabled=true but hooks.token was missing — generated one (64 hex chars).")
PYEOF
    return 0
}

# ─── #16: brew assumption guard ──────────────────────────────────────────────
# Mac uses Homebrew, NOT apt. If a previous install.sh edit accidentally
# called apt, we'd silently fail. This function asserts brew is the package
# manager and warns clearly if it's not.
harden_brew_check() {
    if [ "$(uname -s)" != "Darwin" ]; then return 0; fi
    if ! command -v brew >/dev/null 2>&1; then
        _log "WARNING: Homebrew not on PATH. Mac install assumes brew is the package manager."
        _log "WARNING: Install brew from https://brew.sh before running Skill 22 (book-to-persona)."
    fi
    return 0
}

# ─── #20: yt-dlp + whisper + ffmpeg backfill (Skill 22 dependency) ───────────
# These tools power the YouTube/local-video branch of Skill 22's
# add-persona-from-source.sh. They were not previously installed on Mac
# by default. Use brew (Mac) — never apt.
#
# BOUNDED, NON-INTERACTIVE BREW (defect fix, 2026-09-17). `brew install` used to
# run unbounded with inherited stdin. On a client Mac a dependency postinstall
# wedged in a pseudo-terminal read loop and never returned: three generations of
# orphaned Ruby processes, one pegging a core for two days, and because this
# script never returned, the caller's EXIT trap never fired and the update lock
# stayed held for days. Hardening is best-effort and must NEVER be able to hold
# the roll open, so every brew install now runs:
#   • NONINTERACTIVE=1                  -- brew never prompts
#   • HOMEBREW_NO_AUTO_UPDATE=1         -- no implicit `brew update` (the slow path)
#   • HOMEBREW_NO_INSTALL_CLEANUP=1     -- no post-install cleanup sweep
#   • HOMEBREW_NO_ENV_HINTS=1           -- quiet
#   • stdin from /dev/null              -- any read() gets EOF instead of blocking
#   • a bounded watchdog                -- macOS ships no coreutils `timeout`
# Timeout is HARDENING_BREW_TIMEOUT_SECS seconds (default 600).
HARDENING_BREW_TIMEOUT_SECS="${HARDENING_BREW_TIMEOUT_SECS:-600}"

# Kill a watchdogged brew and everything it forked.
# Group-kills ONLY when the child is confirmed to be its own process-group
# leader (pgid == pid). If that cannot be confirmed we must NOT group-kill:
# that group would be the UPDATER'S OWN, and we would kill the caller.
_brew_kill_tree() {
    local pid="$1" sig="$2" pgid=""
    # -dc '0-9' keeps digits ONLY. `tr -d '[:space:]'` is ambiguous across tr
    # implementations (BSD vs GNU bracket handling); a pgid is digits, so ask
    # for digits.
    pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -dc '0-9')"
    if [ -n "$pgid" ] && [ "$pgid" = "$pid" ]; then
        kill "-${sig}" "-${pgid}" 2>/dev/null || true
    else
        pkill "-${sig}" -P "$pid" 2>/dev/null || true
        kill "-${sig}" "$pid" 2>/dev/null || true
    fi
    return 0
}

# _brew_install_bounded <pkg>
# Returns the brew exit code, or 124 on timeout (mirrors coreutils `timeout`).
# Never returns non-zero to a caller that is not prepared for it -- callers log.
_brew_install_bounded() {
    local pkg="$1"
    local limit="$HARDENING_BREW_TIMEOUT_SECS"
    case "$limit" in ''|*[!0-9]*) limit=600 ;; esac
    [ "$limit" -gt 0 ] 2>/dev/null || limit=600

    local rcfile
    rcfile="$(mktemp "${TMPDIR:-/tmp}/install-hardening-brew.XXXXXX" 2>/dev/null)" || rcfile=""

    # Job control ON only across the launch, so the subshell becomes its own
    # process-group leader and _brew_kill_tree can reap the whole tree. Restore
    # the caller's setting immediately -- the already-created job keeps its pgid.
    local _had_monitor=""
    case "$-" in *m*) _had_monitor=1 ;; esac
    set -m 2>/dev/null || true
    (
        NONINTERACTIVE=1 \
        HOMEBREW_NO_AUTO_UPDATE=1 \
        HOMEBREW_NO_INSTALL_CLEANUP=1 \
        HOMEBREW_NO_ENV_HINTS=1 \
        brew install "$pkg" </dev/null >/dev/null 2>&1
        _rc=$?
        [ -n "$rcfile" ] && printf '%s\n' "$_rc" > "$rcfile" 2>/dev/null
        exit "$_rc"
    ) &
    local pid=$!
    [ -n "$_had_monitor" ] || set +m 2>/dev/null || true

    local waited=0
    while kill -0 "$pid" 2>/dev/null; do
        if [ "$waited" -ge "$limit" ]; then
            _brew_kill_tree "$pid" TERM
            local grace=0
            while [ "$grace" -lt 5 ] && kill -0 "$pid" 2>/dev/null; do
                sleep 1
                grace=$((grace + 1))
            done
            _brew_kill_tree "$pid" KILL
            wait "$pid" 2>/dev/null || true
            [ -n "$rcfile" ] && rm -f "$rcfile" 2>/dev/null
            _log "  brew install $pkg timed out after ${limit} s, skipped"
            return 124
        fi
        sleep 1
        waited=$((waited + 1))
    done
    wait "$pid" 2>/dev/null || true

    # Read the status the subshell recorded. `wait` on an already-reaped job is
    # not a reliable status source here, and an EXIT-CODE FAILURE IS NOT AN
    # EMPTY RESULT: an unreadable/absent rcfile means "unknown", not "success".
    local rc=1
    if [ -n "$rcfile" ] && [ -s "$rcfile" ]; then
        rc="$(tr -dc '0-9' < "$rcfile" 2>/dev/null)"
        case "$rc" in ''|*[!0-9]*) rc=1 ;; esac
    fi
    [ -n "$rcfile" ] && rm -f "$rcfile" 2>/dev/null
    return "$rc"
}

harden_skill22_media_tools() {
    if [ "$(uname -s)" != "Darwin" ]; then return 0; fi
    if ! command -v brew >/dev/null 2>&1; then return 0; fi

    local need=()
    command -v yt-dlp     >/dev/null 2>&1 || need+=(yt-dlp)
    # The Homebrew FORMULA is named `whisper-cpp` (keg `whisper.cpp`), but the
    # BINARIES it installs are whisper-cli, whisper-server, whisper-bench,
    # whisper-stream, whisper-command, whisper-quantize, whisper-talk-llama,
    # whisper-lsp, whisper-vad-speech-segments. Verified against an installed
    # keg (whisper.cpp 1.9.2, `brew list whisper-cpp`): there is NO binary named
    # `whisper-cpp`, and NO binary named `whisper`. A bare `whisper` on PATH
    # comes from the SEPARATE `openai-whisper` formula, which most client boxes
    # do not have. So on a box that already has whisper-cpp installed, the old
    # `command -v whisper-cpp || command -v whisper` probe ALWAYS failed: `need`
    # gained whisper-cpp every pass and `brew install whisper-cpp` re-fired on
    # every roll, forever. Probe the real binary names, current first.
    command -v whisper-cli >/dev/null 2>&1 \
        || command -v whisper-cpp >/dev/null 2>&1 \
        || command -v whisper     >/dev/null 2>&1 \
        || need+=(whisper-cpp)
    command -v ffmpeg     >/dev/null 2>&1 || need+=(ffmpeg)

    if [ "${#need[@]}" -eq 0 ]; then
        return 0
    fi

    _log "Skill 22 media tools missing on Mac: ${need[*]} -- installing via brew (non-blocking, ${HARDENING_BREW_TIMEOUT_SECS}s cap each)"
    for pkg in "${need[@]}"; do
        _brew_install_bounded "$pkg"
        _brew_rc=$?
        case "$_brew_rc" in
            0)   _log "  brew install $pkg ok" ;;
            124) : ;;  # already logged by the watchdog
            *)   _log "  brew install $pkg failed rc=$_brew_rc (non-blocking)" ;;
        esac
    done
    return 0
}

# ─── v10.13.28 #19: Stuck *-resume cron sweep ────────────────────────────────
# Mac mirror of the VPS v10.14.36 safety net for the workforce-build-resume
# self-stop bug (2026-05-24 incident: cron looped every 15 min
# for 6+ hours burning DeepSeek-V4-Pro tokens on a completed build).
#
# Sweeps `openclaw cron list` for any cron whose name ends in `-resume` AND
# whose last_fired (if reported) is >24h old AND whose created (if reported)
# is >7d old. Those crons are almost certainly stuck pings against a
# long-finished state file. We remove them.
#
# Idempotent. Conservative: only touches names ending in `-resume`; requires
# BOTH age conditions to be reported with concrete timestamps; missing data
# means "we don't know" → skip (no false-positive removes).
harden_check_cron_loops() {
    command -v openclaw >/dev/null 2>&1 || return 0
    local listing
    listing=$(openclaw cron list 2>/dev/null) || return 0
    [ -z "$listing" ] && return 0

    local json
    json=$(openclaw cron list --json 2>/dev/null || true)
    if [ -n "$json" ] && command -v python3 >/dev/null 2>&1; then
        local candidates
        candidates=$(python3 - "$json" <<'PY'
import json, sys, datetime as dt
raw = sys.argv[1]
try:
    data = json.loads(raw)
except Exception:
    sys.exit(0)
items = data if isinstance(data, list) else data.get("crons") or data.get("items") or []
now = int(dt.datetime.utcnow().timestamp())
def to_epoch(s):
    if not s: return None
    try:
        return int(dt.datetime.fromisoformat(str(s).replace("Z","+00:00")).timestamp())
    except Exception:
        return None
for c in items:
    name = c.get("name") or ""
    if not name.endswith("-resume"):
        continue
    uuid = c.get("id") or c.get("uuid") or name
    lf = to_epoch(c.get("lastFiredAt") or c.get("last_fired") or c.get("lastRunAt"))
    cr = to_epoch(c.get("createdAt") or c.get("created") or c.get("createdOn"))
    if lf is None or cr is None:
        continue
    age_h = (now - lf) // 3600
    age_d = (now - cr) // 86400
    if age_h > 24 and age_d > 7:
        print(f"{uuid}|{name}|{age_h}")
PY
)
        if [ -n "$candidates" ]; then
            while IFS='|' read -r uuid name age_h; do
                [ -z "$uuid" ] && continue
                _log "harden_check_cron_loops: removing stale resume cron $name ($uuid, last fired ${age_h}h ago)"
                if openclaw cron rm "$uuid" >/dev/null 2>&1; then
                    _log "harden_check_cron_loops: removed $uuid"
                else
                    _log "harden_check_cron_loops: rm $uuid FAILED (continuing)"
                fi
            done <<<"$candidates"
            return 0
        fi
    fi

    # Plaintext fallback (older openclaw without --json). Conservative:
    # only acts when we can parse a clear "Nd" age token next to a -resume
    # name; otherwise no-op rather than risk removing a healthy cron.
    local line uuid days_token days
    while IFS= read -r line; do
        [[ "$line" =~ -resume ]] || continue
        uuid=$(echo "$line" | awk '{ for (i=1;i<=NF;i++) if ($i ~ /^[0-9a-fA-F-]{8,}$/) { print $i; exit } }')
        [ -z "$uuid" ] && continue
        days_token=$(echo "$line" | grep -oE '[0-9]+d' | head -1)
        [ -z "$days_token" ] && continue
        days="${days_token%d}"
        if [ "$days" -ge 7 ]; then
            _log "harden_check_cron_loops (plaintext): removing stale resume cron $uuid (${days}d old)"
            if openclaw cron rm "$uuid" >/dev/null 2>&1; then
                _log "harden_check_cron_loops: removed $uuid"
            else
                _log "harden_check_cron_loops: rm $uuid FAILED (continuing)"
            fi
        fi
    done <<<"$listing"
    return 0
}

# ─── WS-8: hardware-aware concurrency cap (capacity-monitor) ─────────────────
# install.sh hard-writes agents.defaults.subagents.maxConcurrent=100 on EVERY
# box regardless of strength. A weak Mac mini told to run 100 concurrent agents
# (each with its own heartbeat) collides and crashes the gateway. capacity-
# monitor.sh detects real CPU/RAM and reconciles maxConcurrent down to a safe,
# hardware-derived value, and writes a .capacity-profile.json (heartbeat
# stagger + safe cap) that the wave-concurrency gate and heartbeat scheduler
# read as the single source of truth.
#
# Best-effort + idempotent: if the script is missing or hardware can't be read,
# it no-ops and the box keeps the install.sh default. Operators can install a
# 15-minute watchdog cron so resizes are picked up automatically:
#   openclaw cron create --name capacity-monitor --cron '*/15 * * * *' --tz UTC \
#     --shell "bash $HOME/Downloads/openclaw-master-files/scripts/capacity-monitor.sh"
harden_capacity_profile() {
    local oc_root
    oc_root="$(_oc_root)"
    [ -z "$oc_root" ] && return 0
    [ -f "$oc_root/openclaw.json" ] || return 0

    # Locate capacity-monitor.sh next to this hardening script (scripts/).
    local mon
    mon="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/capacity-monitor.sh"
    if [ ! -f "$mon" ]; then
        _log "capacity-monitor.sh not found next to install-hardening.sh — skipping concurrency cap"
        return 0
    fi

    _log "Computing hardware-aware concurrency cap (WS-8 capacity-monitor)…"
    bash "$mon" >/dev/null 2>&1 || _log "  capacity-monitor returned non-zero (non-blocking)"
    if [ -f "$oc_root/.capacity-profile.json" ] && command -v python3 >/dev/null 2>&1; then
        local summary
        summary=$(python3 - "$oc_root/.capacity-profile.json" <<'PY' 2>/dev/null || true
import json,sys
d=json.load(open(sys.argv[1]))
print(f"maxConcurrent={d.get('maxConcurrentAgents')} stagger={d.get('heartbeatStaggerSeconds')}s "
      f"(cores={d.get('cores')} ram={d.get('ramGB')}GB)")
PY
)
        [ -n "$summary" ] && _log "  capacity profile: $summary"
    fi
    return 0
}

# ─── Composite entrypoint ────────────────────────────────────────────────────
run_install_hardening() {
    _log "Running install hardening (Mac, 2-day forensics from 2026-05-23/24)..."
    harden_brew_check
    harden_hooks_token
    harden_skill22_media_tools
    harden_check_cron_loops
    harden_capacity_profile
    _log "Install hardening complete (best-effort; non-blocking)."
    return 0
}

if [ "${BASH_SOURCE[0]}" = "${0:-}" ]; then
    run_install_hardening
fi
