#!/usr/bin/env bash
# browser_manager.sh — THE single mandatory gateway for every agent-browser
# (Vercel Labs, 0.27.0) invocation in Skill 06. SINGLETON POOLED BROWSER — one
# session, lock=1, TTL, guaranteed teardown, reaper backstop.
#
# WHY THIS EXISTS (verified live damage, operator box, 2026-06-23):
#   22 orphan ~/.agent-browser/*.engine descriptors (357M, ZERO *.pid files) —
#   the names show per-ITERATION sessions the agent invented on each retry
#   (-diag / -diag2 / -clone / -clone2 / -clonefix / -fixprobe / -revcheck …).
#   The 06 tools had ZERO teardown anywhere and a fresh session name per attempt,
#   so every aborted build leaked a Chromium + its engine descriptor. This
#   gateway kills BOTH root causes:
#     (1) ONE deterministic canonical session per box (bm_session_name) — no more
#         per-iteration multiplication.
#     (2) GUARANTEED teardown via `trap _bm_teardown EXIT INT TERM HUP` — every
#         non-zero abort (inject-ghl-auth.sh aborts at its lines 317/331/419/424)
#         now ALWAYS closes the session + clears its state.
#   Plus a true box-wide singleton LOCK (lock=1), a per-call + per-session
#   TIMEOUT, a pool CEILING, and a CIRCUIT-BREAKER that PARKS a flaky build
#   (loud STOP, never re-fired) — so an unbounded retry storm can never recur.
#
# PORTABILITY (decisive — fleet is half Macs): `flock` is ABSENT on macOS;
#   `/usr/bin/shlock` is present. The lock is flock-if-present, else an
#   atomic-mkdir fallback with a dead-PID stale-lock reclaim (mirrors how
#   scripts/orphan-temp-sweep.sh handles BSD-vs-GNU `stat`). Liveness keys off
#   PROCESS + descriptor mtime, NEVER a .pid file (there are none on the box).
#
# AUTH MODEL UNCHANGED: this gateway is purely a lifecycle wrapper. It does NOT
#   touch the D7 token-only auth model and re-uses the D6 headless guard VERBATIM
#   (the same unset+force AGENT_BROWSER_HEADED=false / exit-75 refusal / AB()
#   wrapper that lived in inject-ghl-auth.sh lines 53-83).
#
# USAGE (callers source this, never invoke agent-browser directly):
#   source "$(dirname "$0")/browser_manager.sh"
#   SESSION="$(bm_session_name)"      # ONE canonical name per box
#   bm_ensure                         # breaker-check → lock → lease → TTL → open → trap
#   AB --session "$SESSION" eval ...  # thin, lock-asserting pass-through
#   # teardown is automatic via the EXIT trap bm_ensure installed.
#
# VERBS (when run as a standalone command, e.g. via update-skills file set):
#   bash browser_manager.sh ensure
#   bash browser_manager.sh eval|open|snapshot|wait|find|fill -- <args...>
#   bash browser_manager.sh run-detached -- <cmd...>
#   bash browser_manager.sh teardown
#   bash browser_manager.sh session-name
#   bash browser_manager.sh auth-age [-- <session>]    # F5-b: seconds since last seed (-1=unknown)
#   bash browser_manager.sh auth-stale [-- <session>]  # F5-b: exit 0=STALE, 1=FRESH
#
# Version marker (kept in sync by scripts/bump-version.sh):
BROWSER_MANAGER_VERSION="v19.14.0"

# B1 VERSION-GATE FLOOR (v14.1.4) — the version where the BOX-LEVEL headless LOCK
# landed (install.sh pins AGENT_BROWSER_HEADED=false in the gateway-inherited env,
# the headed config scrub, and this very gate). The build path (bm_ensure) REFUSES
# to launch a browser through a browser_manager.sh OLDER than this floor — an
# old-guard box could otherwise open a VISIBLE window. This is a FIXED floor (NOT a
# rolled marker — it has no _VERSION suffix, so bump-version.sh never touches it);
# raise it deliberately in future to force-refuse builds below a new safety
# baseline. It also blocks the legacy silent-hourly-agentTurn furnace shape: any
# auto-fired build must pass through bm_ensure → this gate.
BM_HEADLESS_LOCK_FLOOR="v14.1.4"

# Do NOT `set -e` at source time — sourcing into a caller that already set its
# own options must not be clobbered. inject-ghl-auth.sh keeps its own
# `set -euo pipefail`. We rely on explicit return-code checks here.

# ── D6: HARD HEADLESS GUARD (VERBATIM from inject-ghl-auth.sh lines 53-83) ─────
# HEADLESS-ONLY — never open a visible window; taking over a screen is forbidden
# (esp. client boxes). agent-browser is headless by default, but an inherited
# AGENT_BROWSER_HEADED env var OR a {"headed": true} config file silently forces
# a headed window. We close that door three ways, on EVERY invocation:
#   1. Strip the inherited env   -> unset AGENT_BROWSER_HEADED
#   2. Force headless on the CLI -> AB() appends `--headed false`
#   3. Refuse to proceed if headed could still be on (case-refuse, exit 75).
unset AGENT_BROWSER_HEADED 2>/dev/null || true
export AGENT_BROWSER_HEADED=false   # belt: any child that re-reads env sees false

# Resolve AB_BIN HERE (the concept moved from inject-ghl-auth.sh line 73 so there
# is one source of truth for the binary path across every 06 caller).
AB_BIN="$(command -v agent-browser || echo "$HOME/.npm-global/bin/agent-browser")"

case "${AGENT_BROWSER_HEADED:-false}" in
  ""|0|false|False|FALSE|no|off) : ;;  # headless — OK
  *) echo "REFUSE: AGENT_BROWSER_HEADED='${AGENT_BROWSER_HEADED}' would open a VISIBLE window. Headless is mandatory (D6). Aborting." >&2; exit 75 ;;
esac

# ── Tunables (env-overridable; advisory defaults mirror openclaw.json
#    browser.agentBrowser — that config is ADVISORY-ONLY, agent-browser ignores
#    it natively, so the REAL cap lives here in the manager + the reaper). ──────
AB_LOCK_WAIT="${AB_LOCK_WAIT:-900}"          # flock -w seconds
AB_SESSION_TTL="${AB_SESSION_TTL:-1800}"     # whole-phase wall (s); self-kill timer
AB_CALL_TIMEOUT="${AB_CALL_TIMEOUT:-90}"     # per-call wall (s)
AB_MAX_SESSIONS="${AB_MAX_SESSIONS:-1}"      # pool ceiling (matches the lock) — STAYS 1
AB_SAVE_CONCURRENCY="${AB_SAVE_CONCURRENCY:-5}"  # parallel eval fan-out cap [1,5]; AB_MAX_SESSIONS STAYS 1
AB_BREAKER_WINDOW="${AB_BREAKER_WINDOW:-7200}"   # rolling window (s)
AB_BREAKER_MAX="${AB_BREAKER_MAX:-6}"        # opens-without-pass before trip
AB_MAX_OPENS_PER_HOUR="${AB_MAX_OPENS_PER_HOUR:-12}"  # advisory upper bound
AB_AUTH_REMINT_THRESHOLD_S="${AB_AUTH_REMINT_THRESHOLD_S:-2700}"  # 45min — F5(b)/gates.json token_pre_phase_remint.threshold_minutes

# ── Paths ─────────────────────────────────────────────────────────────────────
# LOCK + LEASES are EPHEMERAL by design — a lock or lease that survived a reboot
# would be a stale-lock bug (a dead PID still "owning" the box). They live under
# TMPDIR and the dead-PID stale-lock reclaim handles a crash. (Keep the literal
# `mkdir "$LOCKDIR/ab.lock.d"` — test_browser_manager_singleton.py asserts it.)
LOCKDIR="${TMPDIR:-/tmp}/agent-browser"
mkdir -p "$LOCKDIR" 2>/dev/null || true
chmod 700 "$LOCKDIR" 2>/dev/null || true
mkdir -p "$LOCKDIR/leases" 2>/dev/null || true

# ── DURABLE PARK / BREAKER STATE (v14.1.5 — survives a reboot) ─────────────────
# The circuit-breaker's PARK marker MUST outlive a reboot, otherwise a parked,
# qc-failed build silently un-parks the instant the box restarts: TMPDIR is wiped
# on boot (/var/folders/* on macOS, tmpfs /tmp on most Linux). So the breaker
# counter + BLOCKED marker, and the canonical box-level PARK marker, live in the
# box's DURABLE OpenClaw state dir, NOT TMPDIR. Detection mirrors every pipeline
# script (VPS /data first, then Mac $HOME). When no onboarded root exists (CI / a
# dev checkout) we fall back to the ephemeral LOCKDIR so the hermetic tests keep
# their old TMPDIR-only behavior.
_bm_durable_root() {
  if [ -d /data/.openclaw ]; then printf '%s' "/data/.openclaw"
  elif [ -d "${HOME:-}/.openclaw" ]; then printf '%s' "${HOME}/.openclaw"
  else printf '%s' ""; fi
}
_BM_DURABLE_ROOT="$(_bm_durable_root)"
if [ -n "$_BM_DURABLE_ROOT" ]; then
  PARK_DIR="$_BM_DURABLE_ROOT/workspace/.park"
else
  PARK_DIR="$LOCKDIR/breaker"   # fallback: ephemeral (no onboarded root — CI/tests)
fi
mkdir -p "$PARK_DIR" 2>/dev/null || true
chmod 700 "$PARK_DIR" 2>/dev/null || true
# Canonical BOX-LEVEL park marker — the SINGLE file the Skill-23 resume cron
# (resume-workforce-build.sh) and the cron registrar (ensure-pipeline-crons.sh)
# both read before they re-fire a build. A breaker trip writes it; ONLY an
# operator (scripts/unpark-build.sh) clears it. Auto-resume never happens.
BM_BOX_PARK_MARKER="$PARK_DIR/workforce-build.parked"

# Stable box id (host + the agent-browser engine root) for lease provenance.
_bm_box_id() { printf '%s' "$(hostname 2>/dev/null || echo box):$HOME"; }

# ── bm_save_concurrency() — clamp AB_SAVE_CONCURRENCY to [1,5] ───────────────
# AB_MAX_SESSIONS STAYS 1 (one browser).  This is a SEPARATE cap on in-flight
# eval calls issued by parallel_saves.sh.  Hard upper bound is 5.
bm_save_concurrency() {
  local raw="${AB_SAVE_CONCURRENCY:-5}" n
  n="$(printf '%s' "$raw" | tr -cd '0-9')"
  [ -z "$n" ] && n=5
  [ "$n" -lt 1 ] 2>/dev/null && n=1
  [ "$n" -gt 5 ] 2>/dev/null && n=5
  printf '%s' "$n"
}

# Canonical session name: ONE per box, deterministic, sanitized [a-z0-9-].
# This is THE fix for the 22-distinct-name root cause. Any non-canonical session
# is REFUSED (exit 64) unless AB_SESSION_OVERRIDE=1 (recorded in the lease so the
# reaper can see overrides).
bm_session_name() {
  local raw="ghl-skill6-${GHL_LOCATION_ID:-${CLIENT_SLUG:-default}}"
  # Lowercase + collapse anything outside [a-z0-9-] to '-', trim repeats/edges.
  printf '%s' "$raw" \
    | tr '[:upper:]' '[:lower:]' \
    | sed -e 's/[^a-z0-9-]/-/g' -e 's/-\{2,\}/-/g' -e 's/^-//' -e 's/-$//'
}

# Assert a caller-supplied session matches the canonical name (else exit 64).
# Honors AB_SESSION_OVERRIDE=1 and records the override flag for the lease.
_BM_OVERRIDE=0
bm_assert_session() {
  local want canonical
  want="$1"
  canonical="$(bm_session_name)"
  if [ "$want" = "$canonical" ]; then
    _BM_OVERRIDE=0
    return 0
  fi
  if [ "${AB_SESSION_OVERRIDE:-0}" = "1" ]; then
    _BM_OVERRIDE=1
    echo "WARN: non-canonical session '$want' allowed via AB_SESSION_OVERRIDE=1 (recorded in lease)." >&2
    return 0
  fi
  echo "REFUSE: session '$want' is not the canonical '$canonical'. One session per box (kills the 22-distinct-name leak). Set AB_SESSION_OVERRIDE=1 to override." >&2
  exit 64
}

# ── AB() — the ONLY way agent-browser is invoked. Forces `--headed false` (D6),
#    wraps each call in a per-call timeout, and ASSERTS the box lock is held. ───
_BM_LOCK_HELD=0
AB() {
  if [ "$_BM_LOCK_HELD" != "1" ]; then
    echo "REFUSE: AB() called without the browser_manager lock held. Call bm_ensure first." >&2
    return 75
  fi
  # NOTE: invoke "$AB_BIN" DIRECTLY (it is always an absolute path resolved at
  # load via `command -v agent-browser`, never the bare word, so there is no
  # function-shadowing to guard against). Do NOT prefix with the `command`
  # builtin: under `timeout` that makes the kernel try to exec a program literally
  # named "command" — which exists on macOS (/usr/bin/command) but NOT on Linux,
  # so on every VPS box `timeout command agent-browser …` failed exec (127), the
  # `|| true` swallowed it, and `AB session list --json` returned EMPTY — silently
  # defeating the pool-ceiling count. Calling "$AB_BIN" directly is portable.
  if command -v timeout >/dev/null 2>&1; then
    timeout "$AB_CALL_TIMEOUT" "$AB_BIN" --headed false "$@"
  else
    # graceful no-op if `timeout` is missing on the box (older macOS)
    "$AB_BIN" --headed false "$@"
  fi
}

# ── LOCK (portable, value=1, true singleton per box) ──────────────────────────
_BM_LOCK_MODE=""   # "flock" | "mkdir"
_bm_lock_acquire() {
  if command -v flock >/dev/null 2>&1; then
    _BM_LOCK_MODE="flock"
    exec 9>"$LOCKDIR/ab.lock"
    if ! flock -w "$AB_LOCK_WAIT" 9; then
      echo "REFUSE: another agent-browser build holds the lock (waited ${AB_LOCK_WAIT}s)." >&2
      exit 75
    fi
  else
    # macOS / BSD: atomic-mkdir lock with dead-PID stale reclaim.
    _BM_LOCK_MODE="mkdir"
    local waited=0
    while :; do
      if mkdir "$LOCKDIR/ab.lock.d" 2>/dev/null; then
        printf '%s' "$$" > "$LOCKDIR/ab.lock.d/pid" 2>/dev/null || true
        break
      fi
      # Lock dir exists — is its owner still alive?
      local pid=""
      pid="$(cat "$LOCKDIR/ab.lock.d/pid" 2>/dev/null || echo '')"
      if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        if [ "$waited" -ge "$AB_LOCK_WAIT" ]; then
          echo "REFUSE: another agent-browser build holds the lock (pid $pid, waited ${AB_LOCK_WAIT}s)." >&2
          exit 75
        fi
        sleep 1; waited=$((waited + 1))
      else
        # Stale lock (owner dead) — reclaim and retry.
        echo "INFO: reclaiming stale agent-browser lock (dead pid '${pid:-none}')." >&2
        rmdir "$LOCKDIR/ab.lock.d" 2>/dev/null || rm -rf "$LOCKDIR/ab.lock.d" 2>/dev/null || true
      fi
    done
  fi
  _BM_LOCK_HELD=1
}

# ── LEASE (Approach 0 graft) — process+mtime liveness, never .pid ─────────────
_bm_now() { date -u +%s; }
_bm_write_lease() {
  local session="$1"
  printf '{"session":"%s","manager_pid":%s,"started_epoch":%s,"ttl_sec":%s,"box_id":"%s","override":%s}\n' \
    "$session" "$$" "$(_bm_now)" "$AB_SESSION_TTL" "$(_bm_box_id)" "$_BM_OVERRIDE" \
    > "$LOCKDIR/leases/${session}.lease" 2>/dev/null || true
}

# ── AUTH-AGE STAMP (F5-b, SKILL-6-BULLETPROOF-SPEC-v1) ────────────────────────
# The reactive 401-recovery (inject-ghl-auth.sh's ONE bounded re-mint) already
# exists. This is the PROACTIVE half: a durable, per-session stamp of "when was
# this session's id_token last (re-)minted", so a long build can check the
# token's AGE before starting a multi-minute phase and re-mint ahead of the
# ~60min expiry instead of waiting for a 401. Lives alongside the lease (same
# LOCKDIR, same lifetime) — NOT the durable PARK_DIR (an auth stamp has no
# business surviving a reboot; a fresh session always re-seeds+re-stamps).
_bm_auth_stamp_file() {
  local session="${1:-$(bm_session_name)}"
  printf '%s' "$LOCKDIR/leases/${session}.auth-seeded-at"
}

# bm_record_auth_seeded [session] — called by inject-ghl-auth.sh immediately
# after EVERY confirmed seed+activate (the initial seed AND the bounded 401
# re-mint), so the age clock always reflects the token actually in the browser.
bm_record_auth_seeded() {
  local session="${1:-$(bm_session_name)}"
  printf '%s' "$(_bm_now)" > "$(_bm_auth_stamp_file "$session")" 2>/dev/null || true
}

# bm_auth_age_s [session] — seconds since the last recorded seed. Prints -1
# (unknown) when no stamp exists yet — callers MUST treat -1 as stale (fail
# TOWARD a re-mint, never toward trusting an unconfirmed session).
bm_auth_age_s() {
  local session="${1:-$(bm_session_name)}" f stamp
  f="$(_bm_auth_stamp_file "$session")"
  if [ ! -f "$f" ]; then
    printf '%s' "-1"
    return 0
  fi
  stamp="$(cat "$f" 2>/dev/null || echo 0)"
  case "$stamp" in ''|*[!0-9]*) printf '%s' "-1"; return 0 ;; esac
  printf '%s' "$(( $(_bm_now) - stamp ))"
}

# bm_auth_is_stale [session] — true (exit 0) iff the token is older than
# AB_AUTH_REMINT_THRESHOLD_S (default 2700s/45min) OR its age is unknown.
bm_auth_is_stale() {
  local session="${1:-$(bm_session_name)}" age
  age="$(bm_auth_age_s "$session")"
  if [ "$age" -lt 0 ] 2>/dev/null; then return 0; fi
  [ "$age" -ge "$AB_AUTH_REMINT_THRESHOLD_S" ]
}

# ── POOL CEILING (Approach 1 graft) — never exceed AB_MAX_SESSIONS open ───────
# Before any open, count active sessions; if at/over ceiling, close the oldest
# idle one; if STILL at ceiling, REFUSE (exit 75). Ceiling=1 matches the lock.
_bm_active_session_count() {
  # `AB session list --json` shape varies by build; count session objects/lines
  # defensively. Fall back to counting live lease files if list is unavailable.
  # EXCLUDE this manager's OWN canonical session — bm_ensure writes its lease
  # before the ceiling check, so counting our own lease would self-trip.
  local out own count
  own="$(bm_session_name)"
  out="$(AB session list --json 2>/dev/null || true)"
  if [ -n "$out" ]; then
    # Count "session" keys (json), minus our own if it appears — portable grep.
    count="$(printf '%s' "$out" | grep -o '"session"' | wc -l | tr -d '[:space:]')"
    if printf '%s' "$out" | grep -q "\"$own\""; then
      count=$((count - 1))
    fi
    [ "$count" -lt 0 ] && count=0
    echo "$count"
  else
    # Count live lease files OTHER than our own.
    count=0
    local f base
    for f in "$LOCKDIR/leases/"*.lease; do
      [ -f "$f" ] || continue
      base="$(basename "$f" .lease)"
      [ "$base" = "$own" ] && continue
      count=$((count + 1))
    done
    echo "$count"
  fi
}

_bm_pool_ceiling_check() {
  local active
  active="$(_bm_active_session_count)"
  [ -z "$active" ] && active=0
  if [ "$active" -ge "$AB_MAX_SESSIONS" ]; then
    # Try to close the oldest idle session (best-effort), then re-count.
    local oldest
    oldest="$(ls -1t "$LOCKDIR/leases/"*.lease 2>/dev/null | tail -1)"
    if [ -n "$oldest" ]; then
      local os
      os="$(basename "$oldest" .lease)"
      if [ "$os" != "$(bm_session_name)" ]; then
        AB close --session "$os" 2>/dev/null || true
        AB state clear "$os" 2>/dev/null || true
        rm -f "$oldest" 2>/dev/null || true
      fi
    fi
    active="$(_bm_active_session_count)"; [ -z "$active" ] && active=0
    if [ "$active" -ge "$AB_MAX_SESSIONS" ]; then
      echo "REFUSE: pool ceiling reached (active=$active >= AB_MAX_SESSIONS=$AB_MAX_SESSIONS)." >&2
      exit 75
    fi
  fi
}

# ── CIRCUIT-BREAKER (Approach 0+1 graft) ──────────────────────────────────────
# Rolling-window open counter per location. After AB_BREAKER_MAX opens (or the
# advisory AB_MAX_OPENS_PER_HOUR) WITHOUT a verified QC pass in the window, the
# breaker OPENS: REFUSE (exit 75), write a DURABLE BLOCKED/qc-failed marker AND
# the canonical box-level PARK marker (both under PARK_DIR, which survives a
# reboot) that the */15 resume cron (resume-workforce-build.sh) + the registrar
# (ensure-pipeline-crons.sh) BOTH read and STOP on (parked, NOT re-fired —
# FAIL-LOUD doctrine), and escalate to Rescue Rangers. The per-location breaker
# resets on window-clear or a verified gate pass (bm_breaker_pass); the box-level
# PARK marker is operator-cleared ONLY (scripts/unpark-build.sh) — auto-resume
# never happens silently.
_bm_breaker_file() { printf '%s' "$PARK_DIR/agent-browser-${GHL_LOCATION_ID:-default}.count"; }
_bm_breaker_marker() { printf '%s' "$PARK_DIR/agent-browser-${GHL_LOCATION_ID:-default}.BLOCKED"; }

# Record one open (called by bm_ensure after a successful open).
_bm_breaker_record_open() {
  local f now
  f="$(_bm_breaker_file)"; now="$(_bm_now)"
  printf '%s\n' "$now" >> "$f" 2>/dev/null || true
}

# Clear the breaker on a verified QC pass (callers invoke `bm_breaker_pass`).
bm_breaker_pass() {
  rm -f "$(_bm_breaker_file)" "$(_bm_breaker_marker)" 2>/dev/null || true
}

# Count opens still inside the rolling window.
_bm_breaker_window_count() {
  local f now cutoff cnt=0 line
  f="$(_bm_breaker_file)"
  [ -f "$f" ] || { echo 0; return 0; }
  now="$(_bm_now)"; cutoff=$((now - AB_BREAKER_WINDOW))
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    if [ "$line" -ge "$cutoff" ] 2>/dev/null; then cnt=$((cnt + 1)); fi
  done < "$f"
  echo "$cnt"
}

bm_breaker_check() {
  # PARK is durable + cross-honored. Refuse immediately if EITHER:
  #   (a) this location's breaker BLOCKED marker exists, OR
  #   (b) the canonical box-level PARK marker exists (an operator park, or a
  #       Skill-23 stuck-build park) — so a parked box never opens a browser.
  if [ -f "$(_bm_breaker_marker)" ] || [ -f "$BM_BOX_PARK_MARKER" ]; then
    echo "REFUSE: build is PARKED (durable marker present). Parked != re-fired — the */15 resume cron (resume-workforce-build.sh) and the cron registrar both read this SAME marker and STOP too. Un-park is operator-only: scripts/unpark-build.sh." >&2
    exit 75
  fi
  local cnt limit
  cnt="$(_bm_breaker_window_count)"
  limit="$AB_BREAKER_MAX"
  [ "$AB_MAX_OPENS_PER_HOUR" -lt "$limit" ] 2>/dev/null && limit="$AB_MAX_OPENS_PER_HOUR"
  if [ "$cnt" -ge "$limit" ]; then
    # Trip the breaker — write BOTH the per-location BLOCKED marker AND the
    # canonical box-level PARK marker (both durable), so the Skill-23 resume cron
    # and the registrar STOP re-firing this box's build, not just the browser path.
    printf 'BLOCKED: %s opens in %ss window without a verified QC pass (location=%s)\n' \
      "$cnt" "$AB_BREAKER_WINDOW" "${GHL_LOCATION_ID:-default}" > "$(_bm_breaker_marker)" 2>/dev/null || true
    printf 'PARKED %s: agent-browser circuit-breaker tripped (%s opens / %ss, location=%s). Un-park: scripts/unpark-build.sh\n' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$cnt" "$AB_BREAKER_WINDOW" "${GHL_LOCATION_ID:-default}" > "$BM_BOX_PARK_MARKER" 2>/dev/null || true
    # close --all is reserved for the reaper / a breaker trip (blast-radius safety).
    AB close --all 2>/dev/null || true
    # Escalate to Rescue Rangers via the n8n webhook — the ONLY path the rescue
    # agent reads. Never use openclaw message send to a Telegram group for escalation:
    # bots cannot read other bots, so that path is silently dropped.
    if [ -n "${RESCUE_RANGERS_WEBHOOK_URL:-}" ]; then
      local _bm_msg="browser_manager circuit-breaker OPEN: $cnt agent-browser opens in ${AB_BREAKER_WINDOW}s without a QC pass (location=${GHL_LOCATION_ID:-default}). Skill-6 build PARKED (qc-failed) + box-level PARK marker written, so the */15 resume cron will STOP too. Needs a human — un-park with scripts/unpark-build.sh."
      local _bm_esc="${_bm_msg//\\/\\\\}"; _bm_esc="${_bm_esc//\"/\\\"}"
      curl -s -X POST "${RESCUE_RANGERS_WEBHOOK_URL}" \
        -H 'Content-Type: application/json' \
        -d "{\"action\":\"escalate\",\"client\":\"$(hostname 2>/dev/null||echo box)\",\"agent\":\"browser_manager\",\"message\":\"${_bm_esc}\"}" \
        --max-time 15 >/dev/null 2>&1 || true
    fi
    echo "REFUSE: circuit-breaker TRIPPED ($cnt opens / ${AB_BREAKER_WINDOW}s). Build PARKED (qc-failed) — durable box-level PARK written; the resume cron will STOP. Escalated to Rescue Rangers. STOP." >&2
    exit 75
  fi
}

# ── TTL self-kill timer ───────────────────────────────────────────────────────
# IMPORTANT: the timer subshell must NOT inherit the caller's stdout/stderr — a
# detached `( sleep … ) &` that keeps those FDs open holds a parent pipe open and
# can wedge a non-interactive caller (e.g. subprocess.run) until the TTL elapses.
# We redirect all three FDs so the parent can exit the instant its trap kills us.
_TTL_PID=""
_bm_start_ttl() {
  local session="$1"
  ( sleep "$AB_SESSION_TTL"; command "$AB_BIN" --headed false close --session "$session" >/dev/null 2>&1 || true ) </dev/null >/dev/null 2>&1 &
  _TTL_PID=$!
  # Disown so a normal shell does not wait on it at exit (the EXIT trap kills it).
  disown "$_TTL_PID" 2>/dev/null || true
}

# ── GUARANTEED TEARDOWN ───────────────────────────────────────────────────────
# Closes ONLY the canonical session (NEVER close --all — blast-radius safety,
# Approach 3 tradeoff; close --all is reserved for the reaper / breaker trip).
_BM_SESSION=""
_bm_teardown() {
  [ -n "$_TTL_PID" ] && kill "$_TTL_PID" 2>/dev/null || true
  flock -u 9 2>/dev/null || true
  if [ "$_BM_LOCK_MODE" = "mkdir" ]; then
    rmdir "$LOCKDIR/ab.lock.d" 2>/dev/null || true
  fi
  if [ -n "$_BM_SESSION" ]; then
    command "$AB_BIN" --headed false close --session "$_BM_SESSION" 2>/dev/null || true
    command "$AB_BIN" --headed false state clear "$_BM_SESSION" 2>/dev/null || true
    rm -f "$LOCKDIR/leases/${_BM_SESSION}.lease" 2>/dev/null || true
    # Clear the auth-age stamp too — the session's real IndexedDB/cookies just got
    # wiped by `state clear`, so a stale stamp must never let a FUTURE session
    # skip re-seeding. (inject-ghl-auth.sh always re-seeds+re-stamps at the start
    # of a session regardless; this is hygiene, not a correctness dependency.)
    rm -f "$(_bm_auth_stamp_file "$_BM_SESSION")" 2>/dev/null || true
  fi
  _BM_LOCK_HELD=0
}

# ── B1 VERSION-GATE — refuse to launch a browser build through an old/headed guard
# Portable dotted-numeric "is $1 < $2" (BSD + GNU awk; bash 3.2 safe). Returns 0
# (true) only when strictly less-than; equal or greater → 1.
_bm_ver_lt() {
  awk -v a="${1#v}" -v b="${2#v}" 'BEGIN{
    na=split(a,A,"."); nb=split(b,B,".");
    n=(na>nb)?na:nb;
    for(i=1;i<=n;i++){x=(i<=na)?A[i]+0:0; y=(i<=nb)?B[i]+0:0;
      if(x<y) exit 0; if(x>y) exit 1}
    exit 1   # equal -> not less-than
  }'
}

# bm_require_current_guard — called FIRST in bm_ensure, BEFORE any lock/open. Two
# refusals, either of which means "do NOT open a browser on this box":
#   (1) HEADLESS LOCK active: AGENT_BROWSER_HEADED must resolve falsey (the source
#       guard forced it; re-assert here as the build-path belt). A truthy value
#       would open a VISIBLE window → refuse (75).
#   (2) GUARD FRESHNESS: this browser_manager.sh must be at/above BM_HEADLESS_LOCK_FLOOR.
#       An older guard predates the box-level lock + scrub + this gate, so the build
#       path must NOT launch through it (76). On a truly pre-lock bundle this very
#       function is absent and the gateway-inherited AGENT_BROWSER_HEADED=false pin
#       (install.sh) is the backstop; once the current bundle lands, this gate is
#       the in-build belt.
bm_require_current_guard() {
  case "${AGENT_BROWSER_HEADED:-false}" in
    ""|0|false|False|FALSE|no|off) : ;;
    *) echo "REFUSE: AGENT_BROWSER_HEADED='${AGENT_BROWSER_HEADED}' would open a VISIBLE window. Box-level headless lock is mandatory (B1/D6). Aborting." >&2; return 75 ;;
  esac
  if [ -z "${BROWSER_MANAGER_VERSION:-}" ]; then
    echo "REFUSE: BROWSER_MANAGER_VERSION missing — this browser_manager.sh predates the headless lock (B1). Update Skill 06 before any browser build." >&2
    return 76
  fi
  if _bm_ver_lt "$BROWSER_MANAGER_VERSION" "$BM_HEADLESS_LOCK_FLOOR"; then
    echo "REFUSE: browser_manager.sh $BROWSER_MANAGER_VERSION is older than the headless-lock floor $BM_HEADLESS_LOCK_FLOOR (B1). An old guard could open a VISIBLE window — refusing to launch. Update Skill 06." >&2
    return 76
  fi
  return 0
}

# ── bm_ensure — the one entrypoint callers use before the first open ──────────
# breaker-check → acquire lock → write lease → start TTL timer → open canonical
# session → register the EXIT/INT/TERM/HUP teardown trap.
bm_ensure() {
  bm_require_current_guard || return $?   # B1: refuse old-guard / headed launch
  local session
  session="$(bm_session_name)"
  bm_assert_session "$session"
  bm_breaker_check                 # before acquire — parked builds never start
  _bm_lock_acquire                 # true box singleton
  _BM_SESSION="$session"
  _bm_write_lease "$session"
  trap _bm_teardown EXIT INT TERM HUP
  _bm_start_ttl "$session"
  _bm_pool_ceiling_check           # never exceed AB_MAX_SESSIONS
  AB --session "$session" open "${GHL_AGENCY_URL:-https://app.convertandflow.com}/" >/dev/null 2>&1 || true
  _bm_breaker_record_open          # count this open toward the breaker window
  return 0
}

# Manual teardown verb.
bm_teardown() { _bm_teardown; }

# ── Standalone verb dispatch (only when executed, not sourced) ────────────────
# Detect "executed directly" portably: BASH_SOURCE[0] == $0.
if [ "${BASH_SOURCE[0]:-$0}" = "$0" ]; then
  _verb="${1:-}"; shift 2>/dev/null || true
  case "$_verb" in
    session-name)
      bm_session_name; echo
      ;;
    auth-age)
      # bash browser_manager.sh auth-age [-- <session>]  — prints seconds since
      # the last recorded seed (-1 = unknown/never seeded). No lock/open needed —
      # pure stamp-file read (F5-b pre-phase check callers use this to decide).
      [ "${1:-}" = "--" ] && shift
      bm_auth_age_s "${1:-}"; echo
      ;;
    auth-stale)
      # bash browser_manager.sh auth-stale [-- <session>] — exit 0 iff stale
      # (>= AB_AUTH_REMINT_THRESHOLD_S or unknown), exit 1 iff fresh.
      [ "${1:-}" = "--" ] && shift
      if bm_auth_is_stale "${1:-}"; then
        echo "STALE"; exit 0
      else
        echo "FRESH"; exit 1
      fi
      ;;
    ensure)
      bm_ensure || exit $?    # B1 gate refusal (75/76) must NOT print "ENSURED"
      echo "ENSURED: session=$(bm_session_name) lock=held ttl=${AB_SESSION_TTL}s — teardown trap installed."
      ;;
    eval|open|snapshot|wait|find|fill)
      # Thin pass-throughs: assert lock by acquiring our own (singleton) then run.
      bm_ensure || exit $?    # B1 gate refusal short-circuits before any open
      # Drop a leading literal "--" if the caller used `verb -- args`.
      [ "${1:-}" = "--" ] && shift
      AB --session "$(bm_session_name)" "$_verb" "$@"
      ;;
    run-detached)
      # Approach 0 graft: launch a build through the manager in a DETACHED subtree
      # that OWNS the lock+lease+TTL+trap, so detach-and-exit is safe (no orphan).
      [ "${1:-}" = "--" ] && shift
      bm_ensure || exit $?    # B1 gate refusal: never detach a build through an old guard
      ( "$@" ) &
      echo "DETACHED: pid=$! session=$(bm_session_name) — owns lock+lease+TTL+teardown."
      ;;
    teardown)
      # Best-effort teardown of the canonical session even with no active lease.
      _BM_SESSION="$(bm_session_name)"
      _bm_teardown
      echo "TORN-DOWN: session=$(bm_session_name)"
      ;;
    *)
      echo "usage: browser_manager.sh {ensure|eval|open|snapshot|wait|find|fill|run-detached|teardown|session-name|auth-age|auth-stale} [-- args...]" >&2
      exit 64
      ;;
  esac
fi
