#!/usr/bin/env bash
# ============================================================
# verify-ghl-live.sh — Skill 44 fail-loud post-install verify gate
# ============================================================
#
# WHY THIS EXISTS (Evelyn VPS reproduction, 2026-06-11):
#   The skill-44 installer reported success while `caf` could not reach GHL at
#   all — the creds were only in secrets/.env (which the gateway process never
#   loads) and the docker env_file held empty placeholders that masked them. A
#   "skill installed" flag is NOT proof the tool works. This gate runs a REAL
#   read against GHL and FAILS LOUDLY if it errors, so we never again report
#   skill-44 success when caf is dead.
#
# WHAT IT DOES:
#   Runs a real read (`caf workflows list`, falling back to `caf contacts list`)
#   using ONLY the inherited process env — it deliberately does NOT source any
#   secrets file. This reproduces exactly what the gateway/agent process sees.
#   The caf wrapper itself still sources secrets/.env, so this also confirms the
#   wrapper's own resolution path works; what we forbid is THIS gate hand-feeding
#   env that the gateway would not have.
#
# OUTCOMES:
#   exit 0  — a real read succeeded. caf can reach GHL. Skill 44 is LIVE.
#   exit 2  — required creds are genuinely ABSENT (not wired anywhere). The
#             caller marks the skill installed-with-missing-prereqs and lists
#             exactly which vars. This is NOT a silent success and NOT a hard
#             failure — it is an honest "installed, needs creds" state.
#   exit 1  — creds appear present but the live read FAILED (auth rejected,
#             network, wiring not inherited, etc.). This FAILS the install step.
#
# Inputs / overrides:
#   CAF_BIN          — path to the caf wrapper (auto-detected otherwise)
#   OC_SECRETS_ENV   — secrets file path, used ONLY to decide present-vs-absent
#                      for the missing-prereqs classification (never fed to caf)
# ============================================================

set -uo pipefail   # NOT -e: we want to capture caf's exit code, not abort.

log() { echo "[verify-ghl-live] $*"; }

# ─── Locate the caf wrapper ──────────────────────────────────────────────────
CAF_BIN="${CAF_BIN:-}"
if [ -z "$CAF_BIN" ]; then
  if command -v caf >/dev/null 2>&1; then
    CAF_BIN="$(command -v caf)"
  elif [ -x /data/.openclaw/tools/convert-and-flow-cli/caf ]; then
    CAF_BIN="/data/.openclaw/tools/convert-and-flow-cli/caf"
  elif [ -x "$HOME/.openclaw/tools/convert-and-flow-cli/caf" ]; then
    CAF_BIN="$HOME/.openclaw/tools/convert-and-flow-cli/caf"
  fi
fi
if [ -z "$CAF_BIN" ] || [ ! -x "$CAF_BIN" ]; then
  log "FAIL: caf wrapper not found / not executable (looked on PATH and the"
  log "      convert-and-flow-cli tool dir). Install step 2/3 did not complete."
  exit 1
fi
log "caf: $CAF_BIN"

# ─── Classify present-vs-absent for required creds (for the exit-2 path) ─────
if [ -z "${OC_SECRETS_ENV:-}" ]; then
  if [ -d /data/.openclaw ]; then OC_SECRETS_ENV="/data/.openclaw/secrets/.env"
  else OC_SECRETS_ENV="$HOME/.openclaw/secrets/.env"; fi
fi

cred_present() {
  # present if set non-empty in the process env OR in secrets/.env
  local var="$1"
  local fromenv; fromenv="$(eval "printf '%s' \"\${$var:-}\"")"
  [ -n "$fromenv" ] && return 0
  [ -f "$OC_SECRETS_ENV" ] || return 1
  grep -qE "^[[:space:]]*(export[[:space:]]+)?${var}=[^[:space:]].*" "$OC_SECRETS_ENV" 2>/dev/null
}

MISSING=""
cred_present GOHIGHLEVEL_API_KEY     || MISSING="$MISSING GOHIGHLEVEL_API_KEY"
cred_present GOHIGHLEVEL_LOCATION_ID || MISSING="$MISSING GOHIGHLEVEL_LOCATION_ID"
if [ -n "$MISSING" ]; then
  log "MISSING-PREREQS: required GHL cred(s) absent everywhere:${MISSING}"
  log "  Skill 44 is INSTALLED-WITH-MISSING-PREREQS. The CLI is in place but"
  log "  cannot reach GHL until these are provided in $OC_SECRETS_ENV and"
  log "  wired (run tools/engine/wire-ghl-env.sh). NOT marking install success."
  exit 2
fi

# ─── Run a REAL read using ONLY inherited process env ────────────────────────
# Deliberately no `source` of any secrets file here — caf must succeed on the
# env the gateway/agent process actually has + what the wrapper sources itself.
run_read() {
  local label="$1"; shift
  log "live read: caf $* ..."
  local out rc
  out="$("$CAF_BIN" "$@" 2>&1)"; rc=$?
  if [ $rc -eq 0 ]; then
    log "OK: '$label' read succeeded (caf can reach GHL)."
    return 0
  fi
  LAST_ERR="$out"
  log "  '$label' read failed (exit $rc)."
  return 1
}

LAST_ERR=""
if run_read "workflows list" workflows list; then
  log "PASS: skill 44 verified LIVE against GHL."
  exit 0
fi

# Firebase-dependent endpoints can legitimately fail without the token; fall
# back to a PIT-only read (contacts) to confirm core reachability.
if run_read "contacts list" contacts list --limit 1; then
  log "PASS: skill 44 verified LIVE against GHL (workflows read needs the"
  log "      Firebase token; PIT-only contacts read succeeded — core is LIVE)."
  exit 0
fi

# Both reads failed even though creds are present → wiring/auth/network problem.
log "FAIL: caf could not reach GHL even though required creds are present."
log "      This is the Evelyn failure mode (creds not inherited by the process,"
log "      or empty docker env_file placeholders masking them, or auth rejected)."
log "      Last caf error:"
printf '        %s\n' "$LAST_ERR" | sed 's/^/      /' | head -20
log "  FIX: re-run tools/engine/wire-ghl-env.sh, then on VPS force-recreate the"
log "       container (env_file is only re-read on recreate), or on Mac restart"
log "       the gateway. Verify the value is real (PIT shape, location id)."
exit 1
