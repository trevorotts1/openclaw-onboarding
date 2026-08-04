#!/usr/bin/env bash
# operator-chat-id.sh — resolve the operator ESCALATION Telegram chat ID.
#
# CO-MINGLING GUARD (v12.4.0):
#   This resolver NEVER bakes in a personal chat ID. The destination for
#   operator escalations/monitoring is OPT-IN and CONFIGURABLE. If no operator
#   escalation chat is configured, this returns the EMPTY STRING and every
#   caller MUST treat that as "escalation destination not configured" and NO-OP
#   the send (log only). A client box that ships without this env set will
#   therefore never proactively message any operator's personal Telegram.
#
# Source this file (or call it directly) to get $OPERATOR_CHAT_ID populated
# (possibly empty).
#
# DEAD-GATEWAY RESILIENCE (circular-alerting-dependency fix):
#   `openclaw config get` requires a LIVE gateway websocket connection. Proven
#   live 2026-08-03: during a ~20h gateway outage the CLI failed with "1006
#   abnormal closure" on every call, this resolver's old CLI-only lookup
#   returned empty for every key, and 79 consecutive watchdog alerts blanked —
#   the alerting path depended on the exact thing it existed to report as
#   broken. This resolver now ALSO reads the on-disk openclaw.json directly
#   (env.vars.<KEY>) whenever the CLI path comes back empty, so a dead or
#   unreachable gateway can no longer blank the destination as long as the
#   value was persisted to disk — which `openclaw config set` does immediately
#   (see scripts/configure-operator-telegram.sh), independent of the gateway
#   process being alive.
#   TRADEOFF: this is a second, independent read path (a hand-rolled env.vars
#   reader) that must be kept in sync with the CLI's config shape by hand
#   instead of going through one code path. It is deliberately narrow — only
#   env.vars.<KEY>, nothing else in the schema — to minimize what can drift.
#   The alternative (cache the resolved value to a file at WRITE time and read
#   the cache on failure) was rejected: it would require every writer of these
#   keys to also remember to refresh the cache, and a stale cache surviving a
#   config change is a worse failure mode (a silently WRONG destination) than
#   a slightly duplicated reader (a silently MISSING one). Reading the live
#   config file directly can never go stale.
#
# FAIL LOUD, NEVER SILENT:
#   An empty result is the correct, INTENTIONAL default for a client box that
#   never opted in (see CO-MINGLING GUARD above) — that case stays silent, on
#   purpose, unchanged. But if the openclaw CLI showed a connection/gateway-
#   level failure signature (the "1006 abnormal closure" class of error) AND
#   the on-disk config file itself could not even be read/parsed, this
#   resolver cannot tell "not configured" from "every path to the answer is
#   broken" — and in that case it refuses to return a silent empty string that
#   looks identical to a deliberate opt-out. It logs unmistakably to stderr and
#   to a durable log file (<OC_ROOT>/workspace/.operator-alert-resolution.log)
#   instead. Callers that want to also try an alternate channel (e.g. a
#   webhook) on an unresolved destination should do so — this resolver only
#   answers "what is the Telegram chat", it does not own alternate channels.
#
# Lookup order (first non-empty wins; ALL operator-supplied, none hardcoded):
#   1. env.vars.OPERATOR_ESCALATION_CHAT_ID   (openclaw config — primary, new)
#   2. env.vars.OPERATOR_TELEGRAM_CHAT_ID     (openclaw config — back-compat)
#   3. env.vars.OPERATOR_HELP_CHAT_ID         (openclaw config — back-compat;
#                                              scripts/configure-operator-telegram.sh
#                                              writes this key alongside #1 on
#                                              every run, but nothing read it
#                                              until now — proven live: a box
#                                              with ONLY this key set resolved
#                                              empty)
#   Each of 1-3 is tried via the openclaw CLI first, then (if that comes back
#   empty) via a direct read of openclaw.json on disk — see DEAD-GATEWAY
#   RESILIENCE above.
#   4. $OPERATOR_ESCALATION_CHAT_ID           (environment variable — primary)
#   5. $OPERATOR_TELEGRAM_CHAT_ID             (environment variable — back-compat)
#   6. $OPERATOR_HELP_CHAT_ID                 (environment variable — back-compat)
#   7. $ZHC_OPERATOR_CHAT_ID                  (environment variable — closeout legacy)
#   8. "" (EMPTY — escalation no-ops; this is the safe default for client boxes)
#
# To OPT IN to operator escalation on a box (operator box, or a client that has
# explicitly authorized operator monitoring):
#   openclaw config set env.vars.OPERATOR_ESCALATION_CHAT_ID "<operator chat id>" --strict-json
#
# Usage:
#   source /path/to/shared-utils/operator-chat-id.sh
#   if [[ -n "$OPERATOR_CHAT_ID" ]]; then
#     openclaw message send --channel telegram --target "$OPERATOR_CHAT_ID" --message "..."
#   else
#     echo "operator escalation chat not configured — skipping send"
#   fi

set -u

# ── CLI lookup (fast path when the gateway is alive) ─────────────────────────
# _oc_gateway_failure_signature TEXT — 0 (match) if TEXT looks like a
# connection/gateway-level failure (the class of error a dead gateway throws),
# NOT a clean "key not found" business response. Matching this is what lets
# _oc_cfg_get tell "nothing configured" apart from "couldn't even ask".
_oc_gateway_failure_signature() {
  printf '%s' "$1" | grep -qiE \
    '1006|abnormal closure|econnrefused|econnreset|etimedout|ehostunreach|socket hang up|websocket|gateway (is )?(down|unreachable|not running|offline)|connection (refused|reset|closed)|failed to connect'
}

# _oc_cfg_get KEY — resolves an `openclaw config get` value via the CLI ONLY.
# Sets the global _OC_LAST_VALUE (may be empty) and, on a gateway/connection-
# level failure, sets _OC_CLI_GATEWAY_FAILURE=1. Deliberately does NOT return
# via stdout/command-substitution: this is called from deep inside a resolution
# chain, and command substitution runs in a subshell — any flag it set would be
# lost the instant the subshell exited, silently defeating the loud-failure
# path this whole function exists to support. Called as a plain statement, its
# global-variable side effects survive.
_oc_cfg_get() {
  local key="$1" raw rc v
  _OC_LAST_VALUE=""
  command -v openclaw >/dev/null 2>&1 || return 0
  raw="$(openclaw config get "$key" 2>&1)"; rc=$?
  if _oc_gateway_failure_signature "$raw"; then
    _OC_CLI_GATEWAY_FAILURE=1
    return 0
  fi
  # v16.2.13: a non-zero exit is ALSO the documented, normal "no operator chat
  # configured" path (the CLI exits non-zero on an absent key) — that is NOT a
  # failure signature, just an empty answer. Never treat non-zero-exit output
  # as a candidate value either way.
  (( rc != 0 )) && return 0
  v="$(printf '%s' "$raw" | tail -1 | tr -d '[:space:]')"
  case "$v" in
    ""|*"not found"*|*"Error"*|*"undefined"*|null) v="" ;;
  esac
  _OC_LAST_VALUE="$v"
}

# ── On-disk fallback (works with NO gateway at all) ───────────────────────────
# _oc_disk_get KEY — reads env.vars.<KEY> directly out of openclaw.json at
# $_OC_CHAT_ROOT, independent of the openclaw CLI / gateway entirely. Sets the
# global _OC_LAST_VALUE (may be empty) and _OC_LAST_DISK_RC:
#   0 = config file read/parsed cleanly (value may legitimately be absent —
#       that is a real, trustworthy "not configured" answer)
#   2 = no OC_ROOT resolved, or no openclaw.json at that root
#   3 = openclaw.json present but unreadable / not valid JSON
# Only rc=0 lets a caller trust an empty result as "confirmed not configured";
# rc 2/3 mean the question could not actually be answered from disk.
_oc_disk_get() {
  local key="$1" cfg
  _OC_LAST_VALUE=""
  _OC_LAST_DISK_RC=2
  [[ -n "${_OC_CHAT_ROOT:-}" ]] || return 0
  cfg="${_OC_CHAT_ROOT}/openclaw.json"
  [[ -f "$cfg" ]] || return 0
  if command -v python3 >/dev/null 2>&1; then
    local out rc
    out="$(OC_CFG_PATH="$cfg" OC_CFG_KEY="$key" python3 - <<'PY' 2>/dev/null
import json, os, sys
try:
    with open(os.environ["OC_CFG_PATH"]) as fh:
        cfg = json.load(fh)
except Exception:
    sys.exit(3)
v = (cfg.get("env") or {}).get("vars") or {}
val = v.get(os.environ["OC_CFG_KEY"])
sys.stdout.write("" if val is None else str(val))
sys.exit(0)
PY
)"
    rc=$?
    _OC_LAST_DISK_RC=$rc
    [[ "$rc" == "0" ]] && _OC_LAST_VALUE="$out"
    return 0
  fi
  # No python3 (rare — python3 is guaranteed inside the OpenClaw container, but
  # not on every bare Mac shell). Best-effort line-scan fallback: the config is
  # always written with `indent=2` (one "KEY": "value" pair per line), so a
  # direct grep for the key is a reasonable approximation. Cannot detect a
  # malformed file this way, so only an EMPTY file is reported unreadable (3);
  # any other miss is read as "key absent" (0) rather than "unreadable" (3),
  # since that is more often true than not for a hand-written fallback.
  if [[ ! -s "$cfg" ]]; then
    _OC_LAST_DISK_RC=3
    return 0
  fi
  _OC_LAST_VALUE="$(sed -nE "s/.*\"${key}\"[[:space:]]*:[[:space:]]*\"([^\"]*)\".*/\1/p" "$cfg" 2>/dev/null | head -1)"
  _OC_LAST_DISK_RC=0
}

# _oc_get_tiered KEY — CLI first, on-disk fallback second. Sets _OC_LAST_VALUE;
# returns 0 if a non-empty value was found, 1 otherwise. Tracks, across every
# call in a resolution pass, whether the disk config was ever CONFIRMED
# readable (_OC_DISK_OK_ANY=1) — that is what lets the final decision below
# tell a confirmed "not configured" apart from "we truly could not tell".
_oc_get_tiered() {
  local key="$1"
  _oc_cfg_get "env.vars.${key}"
  [[ -n "$_OC_LAST_VALUE" ]] && return 0
  _oc_disk_get "$key"
  [[ "$_OC_LAST_DISK_RC" == "0" ]] && _OC_DISK_OK_ANY=1
  [[ -n "$_OC_LAST_VALUE" ]] && return 0
  return 1
}

# _oc_log_resolution_failure — the unmistakable, loud failure path. Writes to
# stderr (visible to any caller that doesn't discard it) AND to a durable log
# file under the resolved OC_ROOT (visible even to callers/crons that redirect
# stderr away), so this can never vanish the way the 79 blanked alerts did.
_oc_log_resolution_failure() {
  local ts msg logdir logfile
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date)"
  msg="OPERATOR_CHAT_ID_RESOLUTION_FAILED: openclaw CLI showed a gateway/connection failure AND the on-disk config could not be read — cannot tell whether an operator escalation destination is configured. Check ${_OC_CHAT_ROOT:-<no OC_ROOT resolved>}/openclaw.json and gateway health. This alert would previously have vanished as a silent empty string."
  printf '[%s] [operator-chat-id] %s\n' "$ts" "$msg" >&2
  if [[ -n "${_OC_CHAT_ROOT:-}" ]]; then
    logdir="${_OC_CHAT_ROOT}/workspace"
    mkdir -p "$logdir" 2>/dev/null || true
    logfile="${logdir}/.operator-alert-resolution.log"
    printf '[%s] [operator-chat-id] %s\n' "$ts" "$msg" >>"$logfile" 2>/dev/null || true
  fi
}

_oc_resolve_operator_chat_id() {
  # Resolve the on-disk root ONCE. Honor a caller-supplied OC_ROOT (this file
  # is routinely sourced by scripts that already resolved it — see
  # closeout-readiness-watchdog.sh / run-closeout.sh's shared resolve-oc-root.sh
  # call) so the disk fallback reads the SAME tree the rest of the caller uses,
  # never a second guess.
  _OC_CHAT_ROOT="${OC_ROOT:-}"
  if [[ -z "$_OC_CHAT_ROOT" ]]; then
    if [[ -d /data/.openclaw ]]; then
      _OC_CHAT_ROOT=/data/.openclaw
    elif [[ -d "${HOME:-}/.openclaw" ]]; then
      _OC_CHAT_ROOT="${HOME}/.openclaw"
    fi
  fi
  _OC_CLI_GATEWAY_FAILURE=0
  _OC_DISK_OK_ANY=0

  if _oc_get_tiered OPERATOR_ESCALATION_CHAT_ID; then printf '%s' "$_OC_LAST_VALUE"; return 0; fi
  if _oc_get_tiered OPERATOR_TELEGRAM_CHAT_ID;   then printf '%s' "$_OC_LAST_VALUE"; return 0; fi
  if _oc_get_tiered OPERATOR_HELP_CHAT_ID;       then printf '%s' "$_OC_LAST_VALUE"; return 0; fi

  if [[ -n "${OPERATOR_ESCALATION_CHAT_ID:-}" ]]; then
    printf '%s' "$OPERATOR_ESCALATION_CHAT_ID"; return 0
  fi
  if [[ -n "${OPERATOR_TELEGRAM_CHAT_ID:-}" ]]; then
    printf '%s' "$OPERATOR_TELEGRAM_CHAT_ID"; return 0
  fi
  if [[ -n "${OPERATOR_HELP_CHAT_ID:-}" ]]; then
    printf '%s' "$OPERATOR_HELP_CHAT_ID"; return 0
  fi
  if [[ -n "${ZHC_OPERATOR_CHAT_ID:-}" ]]; then
    printf '%s' "$ZHC_OPERATOR_CHAT_ID"; return 0
  fi

  # Nothing resolved anywhere. Only shout when the disk config was NEVER
  # confirmed readable while the CLI was ALSO showing a gateway failure — that
  # is the one combination where "empty" might be a lie. A clean disk read
  # that simply found no keys set (the normal, correct opt-out case) stays
  # silent, exactly as documented above.
  if [[ "$_OC_CLI_GATEWAY_FAILURE" == "1" && "$_OC_DISK_OK_ANY" == "0" ]]; then
    _oc_log_resolution_failure
  fi
  printf '%s' ""
}

OPERATOR_CHAT_ID="$(_oc_resolve_operator_chat_id)"
export OPERATOR_CHAT_ID

# If called directly (not sourced), print the resolved value (may be empty).
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  echo "$OPERATOR_CHAT_ID"
fi
