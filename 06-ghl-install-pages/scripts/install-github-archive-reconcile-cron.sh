#!/usr/bin/env bash
# install-github-archive-reconcile-cron.sh — INSTALL-TIME registrar for the
# GitHub archival reconciliation sweep (Skill 06, U24/B-U10 item 2).
#
# WHY THIS EXISTS:
#   B-U10 acceptance (d) requires "the maintenance-window schedule entry
#   EXISTS and its first run writes a dated log" — a real installed cron, not
#   documentation of one. The U24 rebuild found the PRIOR attempt only
#   documented a paste-ready `openclaw cron create` snippet in SKILL.md,
#   which was ALSO WRONG in two ways that would have made it fail outright
#   if anyone actually pasted it:
#     1. `--schedule` DOES NOT EXIST on the OpenClaw CLI (the real flag is
#        `--cron`) — this exact bug was already found and fixed once before
#        in this same repo, see 37-zhc-closeout/scripts/
#        install-closeout-resume-cron.sh:85-90 (FIX-XC-08a). This script
#        follows that file's proven pattern instead of re-discovering it.
#     2. `cron add` with an agent `--message` (or `--command`) payload
#        defaults `delivery=announce` unless `--no-deliver` is passed — an
#        omitted `--no-deliver` here would announce sweep output into
#        whatever chat the box's default delivery channel resolves to,
#        every night (the standing "operator-verbose, never client" rule;
#        mirrors the prior qc-completeness.sh Telegram-leak incident).
#
#   This script installs a COMMAND-mode cron (no agent/model needed, no
#   owner-chat target required — mirrors install-closeout-resume-cron.sh)
#   that runs `ghl_github_reconcile.py --sweep-base --retry` against the
#   INSTALLED skill copy on this box, once daily in the maintenance window.
#
# IDEMPOTENT: skips if the cron already exists. Safe to re-run (e.g. on
# every skill update).
#
# EXIT CODES:
#   0  cron present (already, or registered this run), OR an honest skip
#      (no CLI on this box yet / script not found at the installed path) —
#      install must never abort on this, this is plumbing, not a build gate.
#   1  registration was attempted but failed (caller warns; continues), OR
#      the CLI on this box predates --no-deliver — refused rather than
#      installed unsafely (see feature-detect block below; never retry
#      without --no-deliver just to force a registration through).
#
# Usage:
#   bash install-github-archive-reconcile-cron.sh [--evidence-base-flag-check]
#   (the flag above is test-only — see tests/test_install_github_archive_
#   reconcile_cron.py, which stubs `openclaw` on PATH and asserts the exact
#   argv this script builds, so `--schedule`-class regressions fail CI
#   instead of failing silently on an operator's box at 4am.)
set -u

CRON_NAME="skill6-github-archive-reconcile-sweep"

_log() { echo "[install-github-archive-reconcile-cron] $*"; }

if ! command -v openclaw >/dev/null 2>&1; then
  _log "openclaw CLI not on PATH — skipping (re-run later, e.g. on next skill update)."
  exit 0
fi

# Already present? idempotent no-op.
if openclaw cron list 2>/dev/null | grep -qi "$CRON_NAME"; then
  _log "$CRON_NAME cron already installed — skipping (idempotent)."
  exit 0
fi

# Locate the INSTALLED reconcile tool (this script itself lives in the
# installed skill's scripts/ dir once a fleet roll deploys it — mirror
# install-closeout-resume-cron.sh's own-dir-first resolution).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
RECONCILE_PY=""
for _cand in \
  "$SCRIPT_DIR/../tools/ghl_github_reconcile.py" \
  "${HOME}/.openclaw/skills/06-ghl-install-pages/tools/ghl_github_reconcile.py" \
  "/data/.openclaw/skills/06-ghl-install-pages/tools/ghl_github_reconcile.py"; do
  if [[ -f "$_cand" ]]; then
    RECONCILE_PY="$(cd "$(dirname "$_cand")" && pwd)/$(basename "$_cand")"
    break
  fi
done

if [[ -z "$RECONCILE_PY" ]]; then
  _log "ghl_github_reconcile.py not found at any known install path — cron NOT installed (Skill 06 not yet deployed on this box?)."
  exit 0
fi

# Feature-detect --no-deliver (same defensive pattern as
# install-closeout-resume-cron.sh:91-95 — never assume a CLI flag exists).
# Unlike that pattern, a stale CLI here must REFUSE, not degrade to a
# warning: installing without --no-deliver risks announcing sweep output
# into whatever chat the box's default delivery channel resolves to, every
# night (the standing "operator-verbose, never client" rule; mirrors the
# prior qc-completeness.sh Telegram-leak incident cited above).
_cron_add_help="$(openclaw cron add --help 2>&1 || true)"
if ! printf '%s' "$_cron_add_help" | grep -qE '(^|[[:space:]])--no-deliver([[:space:]]|$)'; then
  _log "ERROR: this CLI does not advertise --no-deliver — refusing to install"
  _log "  $CRON_NAME (installing without it risks announcing sweep output into"
  _log "  an unintended delivery channel). Upgrade OpenClaw and re-run."
  exit 1
fi
NO_DELIVER_FLAG=(--no-deliver)

# Bare --sweep-base (no directory argument) auto-resolves the canonical
# evidence base on THIS box via cc_board.resolve_evidence_base() inside
# ghl_github_reconcile.py itself — the installer never hardcodes a path, so
# no operator-specific directory string is baked into the cron's argv (the
# exact class of leak that poisoned this repo's main branch once already;
# see ledgers/evidence/*/README.md scrub note).
COMMAND_ARGV_JSON=$(python3 -c "
import json
print(json.dumps(['sh', '-lc',
    'python3 \"$RECONCILE_PY\" --sweep-base --retry --json']))
")

OUT=$(openclaw cron add \
    --name "$CRON_NAME" \
    --cron "0 4 * * *" \
    --tz "America/New_York" \
    --session isolated \
    --command-argv "$COMMAND_ARGV_JSON" \
    "${NO_DELIVER_FLAG[@]}" \
    --json 2>/dev/null) || OUT=""

# NOTE: deliberately NO retry-without-no-deliver fallback here. A rejected
# combined argv must surface as the "creation failed" path below, not
# silently drop the one flag that keeps sweep output out of an unintended
# delivery channel.

# Success is decided from `cron add`'s OWN JSON response (an "id" field),
# not a follow-up `cron list` grep — the list read can lag the write by a
# beat on some Gateway backends, which would otherwise report a false
# failure for a registration that actually succeeded.
NEW_ID=$(printf '%s' "$OUT" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get('id') or d.get('uuid') or '')
except Exception:
    print('')
" 2>/dev/null)

if [[ -n "$NEW_ID" ]]; then
  _log "$CRON_NAME cron installed (id=$NEW_ID; daily 04:00 America/New_York, command mode, --sweep-base auto-resolve, --no-deliver — GitHub archival reconcile sweep, U24/B-U10)."
  _log "  Verify: openclaw cron list | grep $CRON_NAME"
  _log "  Fire once by hand to confirm the first dated log lands: openclaw cron run $NEW_ID"
  exit 0
fi

_log "$CRON_NAME cron creation failed (non-fatal — plumbing, not a build gate)."
_log "  Manual: openclaw cron add --name $CRON_NAME --cron '0 4 * * *' --tz America/New_York --session isolated --command-argv '$COMMAND_ARGV_JSON' --no-deliver --json"
exit 1
