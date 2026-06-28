#!/usr/bin/env bash
# agent-browser-reaper.sh — HOST REAPER for orphaned agent-browser lifecycle.
#
# SINGLETON POOLED BROWSER — one session, lock=1, TTL, guaranteed teardown,
# reaper backstop. This script IS the backstop.
#
# THE PROBLEM (verified live damage, operator box, 2026-06-23):
#   22 orphan ~/.agent-browser/*.engine descriptors (357M, ZERO *.pid files) +
#   leaked Chromium processes from Skill-6 builds that crashed before any
#   teardown existed in the 06 tools. The browser_manager.sh gateway now
#   guarantees teardown in the common path; THIS reaper sweeps anything a hard
#   crash (manager killed before its trap fired) still leaks — and one-shots the
#   pre-existing backlog on first contact.
#
# WHAT THIS DOES (idempotent, age-gated, runs as the box user — NEVER root):
#   (1) Expired-lease close: read every $LOCKDIR/leases/*.lease; for any past
#       started_epoch + ttl_sec → close the session + state clear + rm lease.
#   (2) agent-browser doctor --fix (auto-cleans stale socket/pid/version
#       sidecars), then state clean --older-than N (reaps dead .engine
#       descriptors).
#   (3) Dead-descriptor sweep: each ~/.agent-browser/*.engine whose lease is gone
#       AND mtime older than AB_HARD_AGE_MIN → remove (covers crashed managers).
#   (4) AB_MAX_LIVE tripwire: count Chromium procs UNDER THE AGENT-BROWSER /
#       Playwright PROFILE TREE ONLY (match --user-data-dir/profile under
#       ~/.agent-browser or the Playwright fallback dir — NEVER a bare `chrome`
#       name; the operator box runs ~23 unrelated Google Chrome / Claude procs
#       that MUST survive). If over the cap → MESSAGE Rescue Rangers + log; only
#       SIGKILL a Chromium whose owning session lease is gone AND proc age >
#       AB_PROC_HARD_AGE_MIN.
#   (5) Log reclaimed proc count + bytes. Stale atomic-mkdir lock cleanup.
#
# SAFETY (mirrors scripts/orphan-temp-sweep.sh):
#   - Platform-detect OC_ROOT (/data first then $HOME/.openclaw); dedicated log.
#   - set -u; age-gated (never touches an in-flight build); dry-run env.
#   - NEVER kills by bare `chrome`/`Chrome`/`Claude` name; ONLY Chromium bound to
#     the agent-browser/Playwright profile tree with a dead lease + age gate.
#   - Never root/sudo (root config writes freeze the gateway).
#
# EXIT CODES:
#   0  ran clean
#   2  could not run (no OpenClaw root)
#
# ENV OVERRIDES:
#   AB_REAPER_DRY_RUN=1        list/plan only, change nothing
#   AB_STATE_CLEAN_DAYS=1      agent-browser state clean --older-than (days)
#   AB_HARD_AGE_MIN=60         dead-descriptor min age (minutes) before removal
#   AB_MAX_LIVE=3              Chromium-under-profile tripwire
#   AB_PROC_HARD_AGE_MIN=60    min proc age (minutes) before a leaked Chromium SIGKILL
#   AB_REAPER_PLAYWRIGHT_DIR   extra Playwright user-data-dir to also scope to
#
# DESIGN: host-level, idempotent, platform-detected OC_ROOT, dedicated log.
#   Mirrors scripts/orphan-temp-sweep.sh (reaper shape). bash-not-zsh.
#
# BASH 3.2 COMPAT (v14.1.1 — agent-browser-reaper-announce-spam fix): macOS ships
#   the system bash as 3.2.57, and the Gateway runs command-kind crons via
#   `sh -lc`, which on macOS resolves to that bash 3.2 class. bash 3.2 has NO
#   associative arrays (`declare -A`) and NO `mapfile`/`readarray`. The earlier
#   reaper used both, so under bash 3.2 it died at `declare: -A: invalid option`
#   and then `set -u` tripped on the (never-created) array — crashing EVERY run
#   and (on boxes with failure-alerts) firing a "cron failed" notice to the
#   client. This version uses ONLY bash-3.2-safe constructs: a plain indexed
#   array of "known session" names with a small membership helper, and a
#   while-read loop in place of mapfile. It is verified to RUN clean under both
#   bash 3.2.57 and bash 5.x. Do NOT reintroduce `declare -A` / `mapfile` here.
#
# Version marker (kept in sync by scripts/bump-version.sh):
AGENT_BROWSER_REAPER_VERSION="v14.28.0"

set -u

# ─── Platform detection (VPS /data first, Mac fallback) ───────────────────────
if [[ -d /data/.openclaw ]]; then
  OC_ROOT=/data/.openclaw
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  echo "[agent-browser-reaper] no OpenClaw root found; nothing to do" >&2
  exit 2
fi

REAP_LOG="$OC_ROOT/agent-browser-reaper.log"
DRY_RUN="${AB_REAPER_DRY_RUN:-0}"
STATE_CLEAN_DAYS="${AB_STATE_CLEAN_DAYS:-1}"
HARD_AGE_MIN="${AB_HARD_AGE_MIN:-60}"
MAX_LIVE="${AB_MAX_LIVE:-3}"
PROC_HARD_AGE_MIN="${AB_PROC_HARD_AGE_MIN:-60}"

# agent-browser engine root + lock/lease dirs (match browser_manager.sh).
AB_ENGINE_DIR="$HOME/.agent-browser"
LOCKDIR="${TMPDIR:-/tmp}/agent-browser"
LEASE_DIR="$LOCKDIR/leases"
PLAYWRIGHT_DIR="${AB_REAPER_PLAYWRIGHT_DIR:-$HOME/.cache/ms-playwright-ghl}"

AB_BIN="$(command -v agent-browser || echo "$HOME/.npm-global/bin/agent-browser")"

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() {
  printf '%s [%-5s] %s\n' "$(ts)" "$1" "$2" >> "$REAP_LOG" 2>/dev/null || true
  printf '%s [%-5s] %s\n' "$(ts)" "$1" "$2"
}

# Portable file mtime epoch (macOS stat -f%m, GNU stat -c%Y).
_mtime() { stat -f%m "$1" 2>/dev/null || stat -c%Y "$1" 2>/dev/null || echo 0; }
# Portable file size (macOS stat -f%z, GNU stat -c%s).
_size() { stat -f%z "$1" 2>/dev/null || stat -c%s "$1" 2>/dev/null || echo 0; }
_now() { date -u +%s; }

# Headless-forced agent-browser call (D6) — the reaper also never opens a window.
_AB() { command "$AB_BIN" --headed false "$@"; }

# ── bash-3.2-safe "known live sessions" set ──────────────────────────────────
# bash 3.2 has NO associative arrays. We model the set of currently-leased
# session names as a plain indexed array (KNOWN_SESSIONS) plus three helpers:
#   _known_add NAME    — record a session name (idempotent)
#   _known_has NAME    — return 0 if NAME is recorded, 1 otherwise
#   _known_del NAME    — drop NAME from the set (rebuild without it)
#   _known_count       — echo the number of recorded sessions
# These replace `declare -A`, `KNOWN_SESSIONS[$x]=1`, `${KNOWN_SESSIONS[$x]:-}`,
# `unset 'KNOWN_SESSIONS[$x]'`, and `${#KNOWN_SESSIONS[@]}` one-for-one.
KNOWN_SESSIONS=()
_known_add() {
  local n="$1" e
  for e in ${KNOWN_SESSIONS[@]+"${KNOWN_SESSIONS[@]}"}; do
    [[ "$e" == "$n" ]] && return 0
  done
  KNOWN_SESSIONS[${#KNOWN_SESSIONS[@]}]="$n"
}
_known_has() {
  local n="$1" e
  for e in ${KNOWN_SESSIONS[@]+"${KNOWN_SESSIONS[@]}"}; do
    [[ "$e" == "$n" ]] && return 0
  done
  return 1
}
_known_del() {
  local n="$1" e rebuilt=()
  for e in ${KNOWN_SESSIONS[@]+"${KNOWN_SESSIONS[@]}"}; do
    [[ "$e" == "$n" ]] && continue
    rebuilt[${#rebuilt[@]}]="$e"
  done
  KNOWN_SESSIONS=(${rebuilt[@]+"${rebuilt[@]}"})
}
_known_count() { printf '%s' "${#KNOWN_SESSIONS[@]}"; }

reclaimed_bytes=0
reclaimed_procs=0
removed_descriptors=0
closed_sessions=0

log "INFO" "agent-browser-reaper $AGENT_BROWSER_REAPER_VERSION start (dry_run=$DRY_RUN, OC_ROOT=$OC_ROOT)"

# ── Stale atomic-mkdir lock cleanup (rmdir ab.lock.d if its pid is dead) ───────
if [[ -d "$LOCKDIR/ab.lock.d" ]]; then
  lock_pid="$(cat "$LOCKDIR/ab.lock.d/pid" 2>/dev/null || echo '')"
  if [[ -n "$lock_pid" ]] && kill -0 "$lock_pid" 2>/dev/null; then
    log "INFO" "lock held by live pid $lock_pid — a build is in flight; skipping destructive sweeps"
    LOCK_LIVE=1
  else
    if [[ "$DRY_RUN" == "1" ]]; then
      log "DRY" "would clear stale ab.lock.d (dead pid '${lock_pid:-none}')"
    else
      rmdir "$LOCKDIR/ab.lock.d" 2>/dev/null || rm -rf "$LOCKDIR/ab.lock.d" 2>/dev/null || true
      log "SWEPT" "cleared stale ab.lock.d (dead pid '${lock_pid:-none}')"
    fi
    LOCK_LIVE=0
  fi
else
  LOCK_LIVE=0
fi

# ── (1) Expired-lease close ───────────────────────────────────────────────────
# Liveness keys off started_epoch + ttl_sec (process+mtime), NEVER a .pid file.
# KNOWN_SESSIONS is a bash-3.2-safe indexed-array set (see _known_* helpers).
if [[ -d "$LEASE_DIR" ]]; then
  for lease in "$LEASE_DIR"/*.lease; do
    [[ -f "$lease" ]] || continue
    session="$(basename "$lease" .lease)"
    # Parse started_epoch + ttl_sec from the JSON (portable: python3, else grep).
    started=0; ttl=1800
    if command -v python3 >/dev/null 2>&1; then
      read -r started ttl < <(python3 - "$lease" <<'PY' 2>/dev/null || echo "0 1800"
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    print(int(d.get("started_epoch", 0)), int(d.get("ttl_sec", 1800)))
except Exception:
    print(0, 1800)
PY
)
    fi
    _known_add "$session"
    expiry=$((started + ttl))
    now="$(_now)"
    if (( started > 0 && now > expiry )); then
      if [[ "$DRY_RUN" == "1" ]]; then
        log "DRY" "would close expired-lease session: $session (age $((now - started))s > ttl ${ttl}s)"
      else
        _AB close --session "$session" 2>/dev/null || true
        _AB state clear "$session" 2>/dev/null || true
        rm -f "$lease" 2>/dev/null || true
        log "SWEPT" "closed expired-lease session: $session (age $((now - started))s > ttl ${ttl}s)"
      fi
      closed_sessions=$((closed_sessions + 1))
      _known_del "$session"
    fi
  done
fi

# ── (2) doctor --fix + state clean --older-than ───────────────────────────────
# doctor --fix auto-cleans stale socket/pid/version sidecars; state clean reaps
# dead .engine descriptors older than N days. Skip destructive steps if a build
# is in flight (lock held by a live pid).
if [[ "${LOCK_LIVE:-0}" != "1" ]]; then
  if [[ "$DRY_RUN" == "1" ]]; then
    log "DRY" "would run: agent-browser doctor --fix ; agent-browser state clean --older-than $STATE_CLEAN_DAYS"
  else
    _AB doctor --fix >/dev/null 2>&1 && log "OK" "agent-browser doctor --fix completed" || log "WARN" "agent-browser doctor --fix rc!=0 (non-fatal)"
    _AB state clean --older-than "$STATE_CLEAN_DAYS" >/dev/null 2>&1 && log "OK" "agent-browser state clean --older-than $STATE_CLEAN_DAYS completed" || log "WARN" "agent-browser state clean rc!=0 (non-fatal)"
  fi
else
  log "INFO" "skipping doctor --fix / state clean — build in flight"
fi

# ── (3) Dead-descriptor sweep ─────────────────────────────────────────────────
# Each ~/.agent-browser/*.engine with NO live lease AND mtime older than
# AB_HARD_AGE_MIN → remove (covers crashed managers whose lease vanished).
if [[ -d "$AB_ENGINE_DIR" && "${LOCK_LIVE:-0}" != "1" ]]; then
  now="$(_now)"
  cutoff=$((now - HARD_AGE_MIN * 60))
  for eng in "$AB_ENGINE_DIR"/*.engine; do
    [[ -e "$eng" ]] || continue
    base="$(basename "$eng" .engine)"
    # A live lease for this session? then it is NOT orphaned — skip.
    if _known_has "$base"; then
      continue
    fi
    mt="$(_mtime "$eng")"
    if (( mt > cutoff )); then
      continue   # too young — a build may be warming up
    fi
    sz="$(_size "$eng")"
    if [[ "$DRY_RUN" == "1" ]]; then
      log "DRY" "would remove dead descriptor ($sz bytes): $eng"
    else
      rm -rf "$eng" 2>/dev/null && log "SWEPT" "removed dead descriptor ($sz bytes): $eng" || log "WARN" "could not remove: $eng"
    fi
    removed_descriptors=$((removed_descriptors + 1))
    reclaimed_bytes=$((reclaimed_bytes + sz))
  done
fi

# ── (4) AB_MAX_LIVE tripwire — Chromium UNDER THE PROFILE TREE ONLY ───────────
# We match ONLY Chromium processes whose command line references the
# agent-browser engine dir OR the Playwright fallback profile dir. We NEVER match
# a bare `chrome`/`Chrome`/`Claude` — the operator's own Google Chrome.app /
# Claude.app must survive.
profile_pat="$AB_ENGINE_DIR"
[[ -n "$PLAYWRIGHT_DIR" ]] && profile_pat="$AB_ENGINE_DIR|$PLAYWRIGHT_DIR"

# Collect PIDs of Chromium bound to a scoped profile dir. `ps -ww` for full args.
# bash 3.2 has no `mapfile`; read line-by-line into an indexed array instead.
SCOPED_PIDS=()
while IFS= read -r _pid; do
  [[ -n "$_pid" ]] || continue
  SCOPED_PIDS[${#SCOPED_PIDS[@]}]="$_pid"
done < <(
  ps -axww -o pid=,etime=,command= 2>/dev/null \
    | grep -E "(--user-data-dir|--profile|profile-directory)[= ]?[^ ]*($AB_ENGINE_DIR|$PLAYWRIGHT_DIR)" \
    | grep -Ei 'chrom|headless_shell' \
    | grep -vi 'grep' \
    | awk '{print $1}'
)

live_count="${#SCOPED_PIDS[@]}"
log "INFO" "Chromium under agent-browser/Playwright profile tree: $live_count (cap AB_MAX_LIVE=$MAX_LIVE)"

# Durable, reboot-surviving dedup stamp under OC_ROOT (NOT volatile $TMPDIR), so
# the hourly tripwire alerts ONCE per breach episode — not every hour while the
# leak persists. Cleared when live_count drops back under cap (re-arms the alert).
TRIPWIRE_STAMP="$OC_ROOT/.agent-browser-reaper.tripwire.alerted"
if (( live_count > MAX_LIVE )); then
  msg="agent-browser-reaper tripwire: $live_count Chromium procs under the agent-browser/Playwright profile tree (cap $MAX_LIVE) on $(hostname 2>/dev/null || echo box). Possible leak."
  log "WARN" "$msg"
  if [[ ! -f "$TRIPWIRE_STAMP" ]]; then
    # Rising edge only. ESCALATE to Rescue Rangers via the n8n webhook — the ONLY
    # path the rescue agent reads. Never use openclaw message send to a Telegram group
    # for escalation: bots cannot read other bots, so that path is silently dropped.
    if [[ -n "${RESCUE_RANGERS_WEBHOOK_URL:-}" && "$DRY_RUN" != "1" ]]; then
      local _esc_msg="${msg//\\/\\\\}"; _esc_msg="${_esc_msg//\"/\\\"}"
      curl -s -X POST "${RESCUE_RANGERS_WEBHOOK_URL}" \
        -H 'Content-Type: application/json' \
        ${RESCUE_RANGERS_WEBHOOK_SECRET:+-H X-Rescue-Secret:${RESCUE_RANGERS_WEBHOOK_SECRET}} \
        -d "{\"action\":\"escalate\",\"client\":\"$(hostname 2>/dev/null||echo box)\",\"agent\":\"agent-browser-reaper\",\"message\":\"${_esc_msg}\"}" \
        --max-time 15 >/dev/null 2>&1 || log "WARN" "rescue-rangers webhook escalation failed (non-fatal)"
    fi
    [[ "$DRY_RUN" != "1" ]] && date -u +%Y-%m-%dT%H:%M:%SZ > "$TRIPWIRE_STAMP" 2>/dev/null || true
  else
    log "INFO" "tripwire still breached — alert already sent (stamp $TRIPWIRE_STAMP); not re-alerting hourly"
  fi
else
  # Condition cleared → re-arm so the NEXT breach episode alerts again.
  rm -f "$TRIPWIRE_STAMP" 2>/dev/null || true
fi

# Only SIGKILL a scoped Chromium whose owning session lease is GONE AND whose
# proc age > AB_PROC_HARD_AGE_MIN. (etime parse is best-effort; if we cannot
# confirm age we DO NOT kill — fail safe toward leaving it alive.)
if [[ "${LOCK_LIVE:-0}" != "1" ]]; then
  # bash-3.2-safe expansion of a possibly-empty array under `set -u`.
  for pid in ${SCOPED_PIDS[@]+"${SCOPED_PIDS[@]}"}; do
    [[ -n "$pid" ]] || continue
    # proc age in seconds via ps etimes (Linux) or compute from etime (mac).
    age_sec="$(ps -o etimes= -p "$pid" 2>/dev/null | tr -d '[:space:]')"
    if [[ -z "$age_sec" || ! "$age_sec" =~ ^[0-9]+$ ]]; then
      # macOS has no etimes; be conservative — skip the kill (fail safe).
      log "INFO" "pid $pid: cannot confirm age (no etimes) — NOT killing (fail safe)"
      continue
    fi
    if (( age_sec < PROC_HARD_AGE_MIN * 60 )); then
      continue   # too young — may be an in-flight build
    fi
    # Is there a live lease that could own this proc? If ANY lease is live we are
    # conservative and skip (the kill criterion is "owning session lease gone").
    if (( $(_known_count) > 0 )); then
      log "INFO" "pid $pid: a live lease exists — NOT killing (could be owned)"
      continue
    fi
    if [[ "$DRY_RUN" == "1" ]]; then
      log "DRY" "would SIGKILL leaked scoped Chromium pid $pid (age ${age_sec}s, no live lease)"
    else
      kill -9 "$pid" 2>/dev/null && log "SWEPT" "SIGKILL leaked scoped Chromium pid $pid (age ${age_sec}s, no live lease)" || log "WARN" "could not kill pid $pid"
    fi
    reclaimed_procs=$((reclaimed_procs + 1))
  done
fi

# ── (5) Log reclaimed totals ──────────────────────────────────────────────────
mb=$(python3 -c "print(round($reclaimed_bytes/1024/1024, 2))" 2>/dev/null || echo "?")
log "OK" "reaper done: closed_sessions=$closed_sessions removed_descriptors=$removed_descriptors reclaimed=~${mb}MB killed_procs=$reclaimed_procs (dry_run=$DRY_RUN)"
exit 0
