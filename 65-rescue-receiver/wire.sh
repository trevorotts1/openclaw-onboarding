#!/usr/bin/env bash
# 65-rescue-receiver/wire.sh — idempotent box-side wiring for the RR coaching poll.
# Registers the */2-minute command cron ONLY when the box is enrolled
# (RR_RECEIVER_URL + RR_BOX_TOKEN present in <ocroot>/secrets/.env).
#
# RR-027 credential hygiene: enrollment values are PARSED out of the store
# with the SHARED dotenv parser (shared-utils/rescue-env.sh) — this script
# no longer executes the store as shell and no longer exports it (`set -a;
# . file` put every credential in the file into this process's exported
# env, inherited by every child from `cron list` onward). Only the two
# required enrollment values are read, into NON-exported variables; nothing
# else in the store is touched. Malformed config fails visibly (rc from the
# parser, reason on stderr) instead of a silent empty value.
#
# RR-028 readiness + reconciliation (shared-utils/rr-readiness.sh):
#   * The cron is no longer "present or not" by a text grep. It is reconciled
#     (duplicates removed, command/schedule/enabled/delivery flags compared)
#     and then READ BACK before anything is reported.
#   * This script reports an EXPLICIT readiness state with an explicit reason:
#     UNENROLLED / ENROLLED_PENDING / SCHEDULED / VERIFIED (see the engine).
#   * Version-independent by construction: reconciliation reads NO version
#     marker (not ONBOARDING_VERSION, not a `.wired-<version>` sentinel), so
#     the verdict is identical across a software version change and a cron an
#     operator removed is reconciled again on the next pass.
#
# EXIT CODE CONTRACT — this is the INSTALLER's claim, and it is about WIRING:
#   0  files installed / box correctly not enrolled; reconciliation ran and the
#      readiness line states exactly what was and was not proven
#   1  a retryable wiring/config failure: malformed enrollment store, no
#      openclaw CLI, or a cron mutation command that itself failed
# It NEVER means "receiver ready": that claim needs a safe test claim receipt
# in the intended runtime (`rr-readiness.sh --probe`).
#
# WHICH RECONCILE OUTCOMES ARE NON-ZERO (RR-028 review M-2). The reconciler's
# return code is mapped deliberately, not by fall-through:
#   3 readback unavailable  -> 1  NOTHING WAS PROVEN. This script cannot say the
#                                  cron exists, so it must not report success.
#   4 desired job not proven -> 1  the ladder ran (or the add was invisible) and
#                                  the readback still does not show the job —
#                                  including `add_not_read_back`. This is the
#                                  exact failure RR-028 exists to end; a roll
#                                  that printed ✓ here would green-light a box
#                                  with no cron at all.
#   5 openclaw CLI unresolved -> 1 (unchanged, retryable)
#   7 a mutation command failed -> 1 (unchanged, retryable)
#   6 tombstoned / disabled by owner -> 0  DELIBERATELY ZERO. Nothing failed and
#                                  nothing was attempted: the operator's own
#                                  signal is being respected, which is the
#                                  documented success of this path, not an
#                                  error. A tombstone or an operator-disabled
#                                  job must not turn a fleet roll red forever.
#   8 visibility insufficient -> 0  DELIBERATELY ZERO. The fail-closed refusal:
#                                  no mutation was attempted and none is
#                                  claimed, so there is no wiring failure to
#                                  report — the readiness line carries the
#                                  honest `cron_state_unverifiable`. Treating it
#                                  as retryable would make every roll warn on a
#                                  box whose CLI simply cannot see disabled jobs.
# Any other code is unexpected and is treated as a failure (1), never as success.
set -u

_RECONCILE_ONLY=0
for _arg in "$@"; do
  [ "$_arg" = "--reconcile-only" ] && _RECONCILE_ONLY=1
done

_OCROOT=""
[ -d /data/.openclaw ] && _OCROOT="/data/.openclaw"
[ -z "$_OCROOT" ] && [ -d "$HOME/.openclaw" ] && _OCROOT="$HOME/.openclaw"

# Locate the shared helper beside the skills tree (installed copy) or beside
# this script in the repo tree (repo-side runs / self-tests). Sourced, never
# executed; it defines only functions and exports nothing.
_SHARED_HELPERS=""
for _cand in "$_OCROOT/skills/shared-utils/rescue-env.sh" \
             "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/shared-utils/rescue-env.sh" \
             "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../shared-utils/rescue-env.sh"; do
  [ -n "$_cand" ] && [ -f "$_cand" ] && { _SHARED_HELPERS="$_cand"; break; }
done
[ -n "$_SHARED_HELPERS" ] || { echo "65-rescue-receiver: shared-utils/rescue-env.sh not found (required helper missing)" >&2; exit 0; }
# shellcheck disable=SC1090
. "$_SHARED_HELPERS"

# RR-028 requirement 6: the ONE host/container descriptor owns the runtime
# identity. Sourced from the SAME shared-utils bundle; when it is absent the
# runtime stays UNRESOLVED and the readiness report says so instead of guessing
# (a receipt from an unnamed runtime could never verify anything anyway).
_SHARED_DIR="$(cd "$(dirname "$_SHARED_HELPERS")" && pwd)"
if [ -f "$_SHARED_DIR/oc-env-descriptor.sh" ]; then
  # shellcheck disable=SC1090
  . "$_SHARED_DIR/oc-env-descriptor.sh"
fi

[ -n "$_OCROOT" ] || { echo "65-rescue-receiver: no openclaw root; nothing to wire" >&2; exit 0; }
_SECRETS="$_OCROOT/secrets/.env"
_POLL="$_OCROOT/skills/65-rescue-receiver/rescue-poll.sh"
if command -v ocd_target >/dev/null 2>&1; then
  # Only the parts the reconciler needs: root, platform, the ONE exact
  # service/container target, and the state DB. Deliberately NOT ocd_init —
  # that also resolves the gateway PORT (which can shell a live
  # `openclaw gateway status`), and a wiring pass has no use for a port.
  if [ -z "${OC_CONFIG_ROOT:-}" ]; then OC_CONFIG_ROOT="$_OCROOT"; fi
  ocd_root || true
  ocd_platform
  ocd_target
  ocd_state_db || true
fi

if [ ! -f "$_SECRETS" ] || [ ! -f "$_POLL" ]; then
  echo "65-rescue-receiver: secrets file or rescue-poll.sh missing; nothing to wire" >&2
  exit 0
fi

# Parse ONLY the required enrollment values — never the whole store, never
# an execution, never an export. rc=2 file missing/unreadable, rc=1/3
# malformed lines (fail visibly per RR-027).
RR_RECEIVER_URL=""
RR_BOX_TOKEN=""
RR_BOX_SLUG=""
_rc_url=0; _rc_tok=0; _rc_slug=0
RR_RECEIVER_URL=$(rescue_env_get "$_SECRETS" RR_RECEIVER_URL); _rc_url=$?
RR_BOX_TOKEN=$(rescue_env_get "$_SECRETS" RR_BOX_TOKEN); _rc_tok=$?
RR_BOX_SLUG=$(rescue_env_get "$_SECRETS" RR_BOX_SLUG); _rc_slug=$?
case "$_rc_url$_rc_tok$_rc_slug" in
  *2*)
    echo "65-rescue-receiver: secrets store unreadable ($_SECRETS) — poll cron NOT registered" >&2
    exit 0
    ;;
esac
if [ "$_rc_url" = 3 ] || [ "$_rc_tok" = 3 ] || [ "$_rc_slug" = 3 ] \
   || [ "$_rc_url" = 1 ] || [ "$_rc_tok" = 1 ] || [ "$_rc_slug" = 1 ]; then
  # malformed store lines OR missing required value: both fail visibly.
  # Absence keeps the historical unenrolled behavior (dark, no cron);
  # malformed lines are a NEW visible failure with the reason already on
  # stderr from the parser (line numbers named, values never printed).
  if [ "$_rc_url" = 3 ] || [ "$_rc_tok" = 3 ] || [ "$_rc_slug" = 3 ]; then
    echo "65-rescue-receiver: malformed enrollment config in $_SECRETS (see rescue-env lines above) — poll cron NOT registered" >&2
    exit 1
  fi
fi
# Enrollment values stay NON-exported for the rest of this script: the token is
# only EXISTENCE-checked here, and the poll re-reads the store itself at every
# fire (the cron carries no credential — the cron command is just the poll
# script path). The slug is not used by the wiring path at all.
#
# RR-028 requirement 4: slug AND token AND URL must all RESOLVE before a cron is
# registered. Registering a poller for a box the poll itself would dark-exit
# (rescue-poll.sh requires all three) is a false success, so the wiring gate is
# the same set the poll enforces.
if [ -z "${RR_RECEIVER_URL:-}" ] || [ -z "${RR_BOX_TOKEN:-}" ] || [ -z "${RR_BOX_SLUG:-}" ]; then
  # Report WHY, by NAME, from the engine's explicit state machine when it is
  # installed; otherwise fall back to the historical prose line.
  _ENGINE_EARLY=""
  for _cand in "$_OCROOT/skills/shared-utils/rr-readiness.sh" \
               "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/shared-utils/rr-readiness.sh"; do
    [ -n "$_cand" ] && [ -f "$_cand" ] && { _ENGINE_EARLY="$_cand"; break; }
  done
  _MISSING_EARLY=""
  [ -n "${RR_RECEIVER_URL:-}" ] || _MISSING_EARLY="$_MISSING_EARLY RR_RECEIVER_URL"
  [ -n "${RR_BOX_TOKEN:-}" ]    || _MISSING_EARLY="$_MISSING_EARLY RR_BOX_TOKEN"
  [ -n "${RR_BOX_SLUG:-}" ]     || _MISSING_EARLY="$_MISSING_EARLY RR_BOX_SLUG"
  if [ -n "$_ENGINE_EARLY" ]; then
    # shellcheck disable=SC1090
    . "$_ENGINE_EARLY"
    # Enrollment-only resolution: the cron view is NOT consulted on the dark
    # path (a box that is not enrolled must not spawn CLI probes).
    rrr_tools_resolve
    rrr_enrollment_resolve "$_SECRETS"
    rrr_evaluate
    echo "65-rescue-receiver: readiness=$RRR_STATE reason=$RRR_REASON detail=$RRR_DETAIL"
  else
    echo "65-rescue-receiver: box not enrolled (missing:${_MISSING_EARLY}) — poll cron NOT registered"
  fi
  unset RR_RECEIVER_URL RR_BOX_TOKEN RR_BOX_SLUG
  exit 0
fi
unset RR_RECEIVER_URL RR_BOX_TOKEN RR_BOX_SLUG

_NAME="rescue-rr-box-poll"
_LEGACY_NAME="rescue-rangers-poll"
# The updater invokes installers with a stripped environment; on Mac boxes
# /opt/homebrew/bin is NOT on that PATH, so `command -v openclaw` fails even
# though the CLI exists. Fall back to the standard install locations before
# giving up (a hard exit here withholds the .wired sentinel forever).
_OC_BIN=""
if command -v openclaw >/dev/null 2>&1; then
  _OC_BIN="openclaw"
elif [ -x /opt/homebrew/bin/openclaw ]; then
  _OC_BIN="/opt/homebrew/bin/openclaw"
elif [ -x /usr/local/bin/openclaw ]; then
  _OC_BIN="/usr/local/bin/openclaw"
elif [ -x "$HOME/.local/bin/openclaw" ]; then
  _OC_BIN="$HOME/.local/bin/openclaw"
fi
# The CLI is a node script with a `#!/usr/bin/env node` shebang. Under the
# updater's stripped PATH, `env` cannot resolve node even when the CLI path
# is absolute — so prepend the CLI's own directory (where the toolchain's
# node symlink lives) to PATH before invoking it.
case "$_OC_BIN" in
  */*) _BIN_DIR="${_OC_BIN%/*}"; [ -d "$_BIN_DIR" ] && PATH="$_BIN_DIR:$PATH";;
esac

# ---------------------------------------------------------------------------
# RR-028 engine. Absent (an older skills bundle, or a self-test fixture that
# ships only the RR-027 helper) => keep the historical registration path and
# say plainly that readiness is UNKNOWN rather than inventing a state.
# ---------------------------------------------------------------------------
_ENGINE=""
for _cand in "$_OCROOT/skills/shared-utils/rr-readiness.sh" \
             "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/shared-utils/rr-readiness.sh" \
             "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../shared-utils/rr-readiness.sh"; do
  [ -n "$_cand" ] && [ -f "$_cand" ] && { _ENGINE="$_cand"; break; }
done

if [ -z "$_OC_BIN" ]; then
  echo "65-rescue-receiver: openclaw CLI not found" >&2
  exit 1
fi

# Legacy cleanup MUST precede the canonical reconciliation below, or boxes
# wired under the old name accumulate a second poller every time this script
# runs (both crons firing = double delivery).
if "$_OC_BIN" cron list --json 2>/dev/null | grep -q "\"name\": *\"$_LEGACY_NAME\""; then
  _LEGACY_ID="$("$_OC_BIN" cron list --json 2>/dev/null | python3 -c 'import json,sys; jobs=json.load(sys.stdin).get("jobs",[]); print(next((j["id"] for j in jobs if j.get("name")=="'"$_LEGACY_NAME"'"), ""))')"
  if [ -n "$_LEGACY_ID" ]; then
    if "$_OC_BIN" cron rm "$_LEGACY_ID" >&2; then
      echo "65-rescue-receiver: removed legacy cron $_LEGACY_NAME (id $_LEGACY_ID)"
    else
      echo "65-rescue-receiver: legacy cron $_LEGACY_NAME rm FAILED (id $_LEGACY_ID); left in place" >&2
    fi
  else
    echo "65-rescue-receiver: legacy cron $_LEGACY_NAME seen in list but id not resolvable; skipping removal" >&2
  fi
fi

if [ -n "$_ENGINE" ]; then
  # shellcheck disable=SC1090
  . "$_ENGINE"
  # The engine uses the SAME CLI this script resolved (and its runtime id
  # therefore names the same intended runtime).
  RRR_OPENCLAW_OVERRIDE="$_OC_BIN"
  # The descriptor's validated DB (ocd_state_db) first: it is the only view
  # that shows a DISABLED job. Explicit OC_STATE_DB still wins for fixtures.
  RRR_DB="${OC_STATE_DB:-${OCD_DB:-}}"
  if [ -z "$RRR_DB" ]; then
    # No descriptor (older bundle): try the canonical paths before settling
    # for a CLI-only readback.
    for _cand in "$_OCROOT/state/openclaw.sqlite" "$_OCROOT/state.sqlite" "$_OCROOT/data/openclaw.sqlite" "$_OCROOT/openclaw.sqlite"; do
      [ -s "$_cand" ] && { RRR_DB="$_cand"; break; }
    done
  fi
  rrr_init "$_OCROOT" "$_SECRETS" "$_POLL" "$_OCROOT/state/rr-receiver"
  rrr_cron_reconcile
  _recon_rc=$RRR_RECONCILE_RC
  case "$_recon_rc" in
    0) echo "65-rescue-receiver: cron $_NAME reconciled and READ BACK (action=$RRR_RECONCILE_ACTION state=$RRR_RECONCILE_STATE)" ;;
    3) echo "65-rescue-receiver: cron $_NAME could NOT be read back ($RRR_RECONCILE_STATE) — nothing claimed" >&2 ;;
    4) echo "65-rescue-receiver: cron $_NAME NOT proven after reconciliation ($RRR_RECONCILE_STATE)" >&2 ;;
    6) echo "65-rescue-receiver: cron $_NAME NOT mutated — $RRR_RECONCILE_STATE (operator intent respected)" >&2 ;;
    7) echo "65-rescue-receiver: cron mutation command FAILED ($RRR_RECONCILE_STATE)" >&2 ;;
    8) echo "65-rescue-receiver: cron $_NAME NOT registered — $RRR_RECONCILE_STATE: this readback cannot prove the name is free (a DISABLED job would be hidden), so adding could create a second ENABLED poller beside an operator-disabled one (fail-closed refusal, nothing mutated)" >&2 ;;
  esac
  # Re-observe after the reconciliation so the reported state is the state the
  # readback now shows (never the state the mutation intended).
  rrr_cron_readback || true
  rrr_cron_eval
  rrr_desired_digest || true
  if [ "$RRR_DIGEST_STATE" = "resolved" ]; then
    rrr_receipt_read "$RRR_STATE_DIR" "$RRR_DIGEST"
  fi
  rrr_evaluate
  echo "65-rescue-receiver: files-installed=1 (this installer claims INSTALLATION; receiver readiness is a separate claim)"
  [ "$_RECONCILE_ONLY" = "1" ] && echo "65-rescue-receiver: reconcile-only pass (files are copied by the roll; this pass reconciles and reports)"
  echo "65-rescue-receiver: readiness=$RRR_STATE reason=$RRR_REASON digest=${RRR_DIGEST:-none} runtime=${RRR_RUNTIME_ID:-unresolved} coverage=$RRR_COVERAGE"
  echo "65-rescue-receiver: detail=$RRR_DETAIL"
  if [ "$RRR_STATE" != "VERIFIED" ]; then
    echo "65-rescue-receiver: receiver readiness NOT verified — prove it in the intended runtime: bash $_OCROOT/skills/65-rescue-receiver/rr-readiness.sh --probe"
  fi
  # The exit code repeats the reconciler's own verdict (see the header contract):
  # 3/4/5/7 mean the desired cron is NOT proven, so this script must not exit 0;
  # 6/8 are deliberate no-mutation outcomes (operator intent respected, or a
  # fail-closed refusal) and are honestly zero. There is no fall-through: an
  # unexpected code is a failure, never a silent success.
  case "$_recon_rc" in
    0|6|8) exit 0 ;;
    *)     exit 1 ;;
  esac
fi

# ---------------------------------------------------------------------------
# Historical path (engine not installed): presence check + add. Documented as
# UNKNOWN readiness — never as success.
# ---------------------------------------------------------------------------
echo "65-rescue-receiver: readiness=UNKNOWN reason=engine_not_installed detail=shared-utils/rr-readiness.sh not found beside rescue-env.sh; registration falls back to the presence-only path (no readback)" >&2
if "$_OC_BIN" cron list --json 2>/dev/null | grep -q "\"name\": *\"$_NAME\""; then
  echo "65-rescue-receiver: cron $_NAME already registered (presence only; NOT read back)"
  exit 0
fi
if "$_OC_BIN" cron add --name "$_NAME" --cron "*/2 * * * *" --no-deliver --command "sh $_POLL" >&2; then
  :
elif "$_OC_BIN" cron add --name "$_NAME" --cron "*/2 * * * *" --command "sh $_POLL" >&2; then
  :
else
  echo "65-rescue-receiver: cron add FAILED" >&2; exit 1
fi
echo "65-rescue-receiver: registered cron $_NAME (*/2) -> sh $_POLL (presence path; NOT read back)"
