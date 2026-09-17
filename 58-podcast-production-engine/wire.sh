#!/usr/bin/env bash
# =============================================================================
# PODCAST PRODUCTION ENGINE (skill 58) :: wire.sh
# The per-skill wiring entry point update-skills.sh and install.sh call.
# -----------------------------------------------------------------------------
# THE GAP THIS CLOSES. Until this file existed, NOTHING on a client box ever
# activated the podcast engine. install.sh's roll-3 block only COPIES the
# activation files; update-skills.sh has no podcast branch at all, and its
# per-skill wiring loop runs wire.sh, install.sh, scripts/install.sh or
# setup-*.sh, none of which skill 58 shipped. Activation therefore happened in
# exactly one place, provision-podcast-client.sh, and only for a client being
# provisioned for the first time. Every box provisioned before the activation
# layer existed, and every box whose provision aborted, stayed dark: intake
# lands, the ledger says received, the dashboard says Received, and nothing
# ever runs. update-skills.sh now picks this file up automatically, by name.
#
# WHAT IT DOES (idempotent, box-user, never destructive):
#   1. Resolves the client slug (env PODCAST_CLIENT_SLUG, else the slug already
#      recorded in this box's registered podcast intake route, else
#      PODCAST_INTAKE_ROUTE_ID from the gateway runtime env).
#   2. Resolves the intake hook secret LABEL state (SET / NOT SET only, never a
#      value) from the live environment, else the box secrets file.
#   3. With both: install-podcast-department.sh --client-slug <slug>, then
#      register-podcast-hook.sh --client-slug <slug>, then
#      guard-activation-health.py --client-slug <slug> --json.
#   4. With either missing: prints a LOUD WARN naming SOP-PODCAST-07
#      (ACTIVATION RESCUE) and exits 0. A skills roll must not fail because a
#      box has no podcast client on it; most boxes do not.
#
# EXIT: 0 wired, or nothing to wire (slug/secret absent, or engine not installed)
#       1 a real activation failure on a box that HAS a podcast client
#       2 refused (running as root)
#
# NEVER: restarts the gateway (the restart doctrine is box-type-specific and
# operator-owned), prints a secret value, writes as root, or touches a client's
# credentials.
#
# USAGE: wire.sh [--idempotent] [--dry-run]
#   --idempotent   Accepted for the updater's calling convention. Every path in
#                  this script is idempotent regardless.
#   --dry-run      Resolve and print the plan; run nothing.
# =============================================================================
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS_DIR="$SKILL_DIR/scripts"
PROG="$(basename "$0")"

DRY_RUN=0
while [ $# -gt 0 ]; do
  case "$1" in
    --idempotent) shift ;;
    --dry-run)    DRY_RUN=1; shift ;;
    -h|--help)    sed -n '2,46p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 0 ;;
    *)            shift ;;
  esac
done

log()  { printf '[podcast-wire] %s\n' "$*" >&2; }
warn() { printf '[podcast-wire] WARN: %s\n' "$*" >&2; }

# Root guard, same rule as the helpers: a root-owned openclaw.json freezes the
# gateway, so config writes run as the node runtime user or not at all.
if [ "$(id -u)" = "0" ]; then
  warn "refusing to run as root; podcast activation writes openclaw.json and must run as the node runtime user"
  warn "re-run as the node user: sudo -u \"\${PODCAST_NODE_USER:-node}\" $SKILL_DIR/$PROG --idempotent"
  exit 2
fi

INSTALLER="$SCRIPTS_DIR/install-podcast-department.sh"
REGISTRAR="$SCRIPTS_DIR/register-podcast-hook.sh"
HEALTH="$SCRIPTS_DIR/guard-activation-health.py"

for f in "$INSTALLER" "$REGISTRAR"; do
  if [ ! -f "$f" ]; then
    warn "$(basename "$f") is not present in this build; the activation layer cannot run on this box yet (nothing wired, not a failure)"
    exit 0
  fi
done

# --------------------------------------------------------------------------- #
# Resolve the gateway config (same order the helpers use) so the slug can be
# read back off an already-registered route.
# --------------------------------------------------------------------------- #
CONFIG_FILE="${PODCAST_OPENCLAW_CONFIG:-}"
if [ -z "$CONFIG_FILE" ] && command -v openclaw >/dev/null 2>&1; then
  CONFIG_FILE="$(openclaw config file 2>/dev/null || true)"
fi
if [ -z "$CONFIG_FILE" ]; then
  if [ -f "$HOME/.openclaw/openclaw.json" ]; then CONFIG_FILE="$HOME/.openclaw/openclaw.json"
  elif [ -f "/data/.openclaw/openclaw.json" ]; then CONFIG_FILE="/data/.openclaw/openclaw.json"; fi
fi

# --------------------------------------------------------------------------- #
# 1. Client slug
# --------------------------------------------------------------------------- #
SLUG="${PODCAST_CLIENT_SLUG:-}"
SLUG_SOURCE="PODCAST_CLIENT_SLUG"
if [ -z "$SLUG" ] && [ -n "$CONFIG_FILE" ] && [ -f "$CONFIG_FILE" ] && command -v python3 >/dev/null 2>&1; then
  SLUG="$(WIRE_CONFIG="$CONFIG_FILE" python3 - <<'PY' 2>/dev/null || true
import json, os, sys
try:
    with open(os.environ["WIRE_CONFIG"], encoding="utf-8") as fh:
        cfg = json.load(fh)
except Exception:
    raise SystemExit(0)
routes = (((cfg.get("plugins") or {}).get("entries") or {}).get("webhooks") or {}).get("config") or {}
routes = routes.get("routes") or {}
slugs = sorted(
    rid[len("podcast-intake-"):]
    for rid in routes
    if isinstance(rid, str) and rid.startswith("podcast-intake-") and len(rid) > len("podcast-intake-")
)
# Exactly one podcast client per box is the model. With more than one, the env
# must say which; guessing would wire the wrong client.
if len(slugs) == 1:
    sys.stdout.write(slugs[0])
PY
)"
  [ -n "$SLUG" ] && SLUG_SOURCE="the registered intake route in $CONFIG_FILE"
fi
if [ -z "$SLUG" ] && [ -n "${PODCAST_INTAKE_ROUTE_ID:-}" ]; then
  case "$PODCAST_INTAKE_ROUTE_ID" in
    podcast-intake-*) SLUG="${PODCAST_INTAKE_ROUTE_ID#podcast-intake-}"; SLUG_SOURCE="PODCAST_INTAKE_ROUTE_ID" ;;
  esac
fi

# --------------------------------------------------------------------------- #
# 2. Intake hook secret. Presence only: this script never reads, prints, or
#    passes the value. When the label is absent from the live environment the
#    box secrets file is consulted for PRESENCE of the key, and the value is
#    exported into this process only so the registrar's own SET check passes.
# --------------------------------------------------------------------------- #
SECRETS_ENV_FILE="${SECRETS_ENV_FILE:-$HOME/.openclaw/secrets.env}"
SECRET_STATE="NOT SET"
if [ -n "${PODCAST_INTAKE_HOOK_SECRET:-}" ]; then
  SECRET_STATE="SET"
elif [ -f "$SECRETS_ENV_FILE" ] && grep -qE '^[[:space:]]*(export[[:space:]]+)?PODCAST_INTAKE_HOOK_SECRET=.' "$SECRETS_ENV_FILE" 2>/dev/null; then
  # shellcheck disable=SC2016  # single quotes intentional: the value is sourced inside the inner shell and never interpolated into this command string
  _s="$(bash -c 'set -a; . "$0" >/dev/null 2>&1; printf "%s" "${PODCAST_INTAKE_HOOK_SECRET:-}"' "$SECRETS_ENV_FILE" 2>/dev/null)"
  if [ -n "$_s" ]; then export PODCAST_INTAKE_HOOK_SECRET="$_s"; SECRET_STATE="SET"; fi
  unset _s
fi

# --------------------------------------------------------------------------- #
# Nothing to wire: say exactly what is missing, name the rescue SOP, exit 0.
# --------------------------------------------------------------------------- #
if [ -z "$SLUG" ] || [ "$SECRET_STATE" != "SET" ]; then
  warn "=============================================================="
  warn "PODCAST ENGINE NOT ACTIVATED ON THIS BOX (nothing was wired)."
  [ -z "$SLUG" ] && warn "  client slug            : NOT RESOLVED (no PODCAST_CLIENT_SLUG, no registered podcast-intake-<slug> route, no PODCAST_INTAKE_ROUTE_ID)"
  [ -n "$SLUG" ] && warn "  client slug            : $SLUG (from $SLUG_SOURCE)"
  warn "  PODCAST_INTAKE_HOOK_SECRET : $SECRET_STATE"
  warn "This is EXPECTED on a box with no podcast client. On a box that HAS one,"
  warn "intake will land and never advance past 'received'. The procedure is"
  warn "universal-sops/podcast-craft/SOP-PODCAST-07-ACTIVATION-RESCUE.md."
  warn "To activate now, as the node user:"
  warn "  export PODCAST_CLIENT_SLUG=<slug>"
  warn "  export PODCAST_INTAKE_HOOK_SECRET=<the intake secret>   # openssl rand -hex 32 at onboarding"
  warn "  $SKILL_DIR/$PROG --idempotent"
  warn "=============================================================="
  exit 0
fi

log "client slug: $SLUG (from $SLUG_SOURCE); PODCAST_INTAKE_HOOK_SECRET: SET (value never read or printed)"
if [ "$DRY_RUN" = "1" ]; then
  log "dry-run plan:"
  log "  1. $INSTALLER --client-slug $SLUG"
  log "  2. $REGISTRAR --client-slug $SLUG"
  log "  3. python3 $HEALTH --client-slug $SLUG --json"
  log "dry-run: nothing executed (exit 0)"
  exit 0
fi

RC_TOTAL=0

log "1/3 department install: $(basename "$INSTALLER") --client-slug $SLUG"
if bash "$INSTALLER" --client-slug "$SLUG" >&2; then
  log "    department install OK"
else
  _rc=$?
  warn "    $(basename "$INSTALLER") exited $_rc; the podcast department is NOT confirmed installed for $SLUG (SOP-PODCAST-07 Section 2)"
  RC_TOTAL=1
fi

log "2/3 intake route + gateway hook mapping: $(basename "$REGISTRAR") --client-slug $SLUG"
if bash "$REGISTRAR" --client-slug "$SLUG" >&2; then
  log "    intake registration OK"
else
  _rc=$?
  warn "    $(basename "$REGISTRAR") exited $_rc; the intake route or its gateway hook mapping is NOT registered for $SLUG (SOP-PODCAST-07 Section 2)"
  RC_TOTAL=1
fi

if [ -f "$HEALTH" ] && command -v python3 >/dev/null 2>&1; then
  log "3/3 activation health: guard-activation-health.py --client-slug $SLUG --json"
  if python3 "$HEALTH" --client-slug "$SLUG" --json >&2; then
    log "    activation health PASS"
  else
    _rc=$?
    warn "    guard-activation-health.py exited $_rc; at least one activation layer is missing for $SLUG. Run SOP-PODCAST-07 ACTIVATION RESCUE on this box."
    RC_TOTAL=1
  fi
else
  warn "3/3 guard-activation-health.py not runnable here (missing file or python3); activation was applied but NOT independently health-checked"
fi

if [ "$RC_TOTAL" = "0" ]; then
  log "podcast engine wired for $SLUG."
  log "NEXT: apply this box's gateway restart doctrine (Mac kickstart-then-stop; Virtual Private Server compose recreate) so the new hook mapping and any new runtime env load, then confirm the gateway is healthy."
  exit 0
fi
warn "podcast wiring finished with at least one failure for $SLUG; see the lines above and SOP-PODCAST-07."
exit 1
