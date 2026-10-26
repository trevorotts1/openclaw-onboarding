#!/usr/bin/env bash
# install-github-archive-reconcile-cron.sh — U24/B-U10 item 2: register the
# daily maintenance-window sweep of the Skill-6 GitHub archival rail.
#
# WHAT THIS DOES
# ---------------
# Reads the schedule ENTRY file this repo ships
# (schedule/skill6-github-archive-reconcile-sweep.cron.json — the single
# source of truth both this installer and SKILL.md's doctrine text describe)
# and registers it as an `openclaw` cron, idempotently, by NAME. Never
# duplicates: if a cron with the entry's name already exists, this is a
# no-op. Never fatal: a missing `openclaw` CLI, a missing `jq`/`python3`
# parser, or a registration failure is logged and exits non-fatally (3) so
# install.sh/update-skills.sh callers can continue and retry on the next run
# — mirrors scripts/ensure-pipeline-crons.sh's fail-open discipline.
#
# THIS IS THE LIVE-PROOF LEG'S INSTALLER, NOT ITS PROOF. B-U10's offline
# CODE-MERGE gate (amended 2026-07-15) only requires the schedule ENTRY file
# to exist and name the reconcile sweep with --retry (asserted by name,
# proven in tests/test_github_archive_maintenance_schedule.py) — this
# installer is the mechanism that would register it live on an operator box;
# actually firing it and confirming the first dated log is DEFERRED TO U22.
#
# CLI
# ---
#   bash scripts/install-github-archive-reconcile-cron.sh [flags] [evidence-base-dir]
#
# Flags (SK6001): a leading --flag is NEVER the evidence directory. The
# generic wiring loop in update-skills.sh runs the first scripts/install-*.sh
# of a skill as `bash <installer> --idempotent`; the old `${1:-...}` took that
# flag as the directory and registered `--sweep-base "--idempotent"`, which
# argparse rejects (exit 2, every night, on every box that rolled). Now:
#   --idempotent / --reconcile-only   accepted, no-ops (the installer is
#                                     always idempotent)
#   --evidence-base DIR | =DIR        explicit directory
#   -h | --help                       usage, exit 0
#   --                                end of flags
#   any other --flag                  logged and ignored (never the directory)
# Directory precedence: positional/--evidence-base, $SKILL6_EVIDENCE_BASE, then
# tools/cc_board.py `evidence-base` (SK6002 -- the one resolver Command Center
# reconcile also uses): $SKILL6_EVIDENCE_BASE_DIR, else the PERSISTENT path for
# the platform: Mac $HOME/clawd/skill6-fix; Hostinger Docker
# /data/clawd/skill6-fix; Contabo Docker $HOME/.openclaw/clawd/skill6-fix
# (/home/node is thrown away on a container recreate, only ~/.openclaw
# survives). The directory is created if missing (the sweep itself also
# creates it). An existing job whose command carries a flag (or nothing) after
# --sweep-base, or on Docker a non-persistent $HOME path, is repaired in place
# with `openclaw cron edit` (Contabo ~/.openclaw and Hostinger /data alike, SK6003);
# a healthy persistent job is left alone. On Contabo and Hostinger
# $HOME/clawd/skill6-fix is pointed at the persistent folder (symlink, or a
# one-time non-destructive copy if it is already a real folder) because the
# Command Center health probe still reads that path.
#
# EXIT CODES
#   0  cron already present, or registered this run
#   2  the schedule entry file itself is missing/unparsable (repo defect)
#   3  `openclaw` CLI absent, or registration failed (advisory, non-fatal —
#      caller should warn; a future run backfills)
set -u

EVIDENCE_ARG=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) sed -n '/^# CLI/,/^# EXIT CODES/p' "${BASH_SOURCE[0]}" | sed '$d'; exit 0 ;;
    --idempotent|--reconcile-only) ;;
    --evidence-base) EVIDENCE_ARG="${2:-}"; shift ;;
    --evidence-base=*) EVIDENCE_ARG="${1#--evidence-base=}" ;;
    --) shift; [[ -n "${1:-}" && -z "$EVIDENCE_ARG" ]] && EVIDENCE_ARG="$1"; break ;;
    -*) echo "[install-github-archive-reconcile-cron] ignoring unknown flag: $1" ;;
    *) [[ -z "$EVIDENCE_ARG" ]] && EVIDENCE_ARG="$1" ;;
  esac
  shift
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENTRY_FILE="$ROOT/schedule/skill6-github-archive-reconcile-sweep.cron.json"

_log() { echo "[install-github-archive-reconcile-cron] $*"; }

if [[ ! -f "$ENTRY_FILE" ]]; then
  _log "FAIL schedule entry file not found: $ENTRY_FILE"
  exit 2
fi

# Shared idempotency + silent-delivery helpers (full-visibility presence
# check, disabled-job tombstones, delivery validation). Sourced after the
# entry-file check so a tampered/relocated tree still reports its own defect.
CRON_LIB="$ROOT/scripts/lib-cron-presence.sh"
[[ -f "$CRON_LIB" ]] || { _log "FAIL shared cron helper missing: $CRON_LIB (repo defect)"; exit 2; }
# shellcheck source=./lib-cron-presence.sh
source "$CRON_LIB"

command -v python3 >/dev/null 2>&1 || { _log "FAIL python3 not available to parse the schedule entry"; exit 2; }

# Parse the entry file (name/schedule/tz/command) via python3 — no jq
# dependency for the entry file itself (it's small, fixed-shape JSON we ship).
ENTRY_JSON="$(python3 - "$ENTRY_FILE" <<'PYEOF'
import json, sys
with open(sys.argv[1]) as fh:
    d = json.load(fh)
for k in ("name", "schedule", "tz", "command"):
    if k not in d:
        print(f"MISSING:{k}", file=sys.stderr)
        sys.exit(1)
print(d["name"])
print(d["schedule"])
print(d["tz"])
print(d["command"])
PYEOF
)" || { _log "FAIL schedule entry file is missing a required field (name/schedule/tz/command)"; exit 2; }

CRON_NAME="$(printf '%s\n' "$ENTRY_JSON" | sed -n '1p')"
CRON_SCHEDULE="$(printf '%s\n' "$ENTRY_JSON" | sed -n '2p')"
CRON_TZ="$(printf '%s\n' "$ENTRY_JSON" | sed -n '3p')"
CRON_COMMAND_TEMPLATE="$(printf '%s\n' "$ENTRY_JSON" | sed -n '4p')"

# Substitute the evidence-base dir (precedence in the CLI header above).
EVIDENCE_BASE="${EVIDENCE_ARG:-${SKILL6_EVIDENCE_BASE:-}}"
if [[ -z "$EVIDENCE_BASE" ]]; then
  EVIDENCE_BASE="$(python3 "$ROOT/tools/cc_board.py" evidence-base 2>/dev/null | tail -n 1)"
  [[ -n "$EVIDENCE_BASE" ]] || EVIDENCE_BASE="${HOME:+$HOME/clawd/skill6-fix}"
fi
if [[ -z "$EVIDENCE_BASE" || "$EVIDENCE_BASE" == -* || "$EVIDENCE_BASE" == *[\"\$\`]* ]]; then
  _log "FAIL no usable evidence directory (got '${EVIDENCE_BASE}'; need a path with no quote, dollar or backtick that does not start with '-')"
  exit 2
fi
mkdir -p "$EVIDENCE_BASE" 2>/dev/null || _log "WARN could not create $EVIDENCE_BASE (the sweep treats a missing directory as nothing to do)"

# SK6002 Contabo compatibility: Command Center reads $HOME/clawd/skill6-fix.
# When the persistent folder lives under ~/.openclaw (Contabo) or /data
# (Hostinger, SK6003), make that path reach it.
_legacy="${HOME:-}/clawd/skill6-fix"
if [[ -n "${HOME:-}" && ( "$EVIDENCE_BASE" == "$HOME/.openclaw/"* || "$EVIDENCE_BASE" == "${SKILL6_DATA_ROOT:-/data}/"* ) && "$_legacy" != "$EVIDENCE_BASE" ]]; then
  if [[ -L "$_legacy" ]]; then
    :
  elif [[ -d "$_legacy" ]]; then
    cp -Rn "$_legacy/." "$EVIDENCE_BASE/" 2>/dev/null && _log "copied existing $_legacy into $EVIDENCE_BASE (originals kept)"
  elif mkdir -p "$HOME/clawd" 2>/dev/null && ln -s "$EVIDENCE_BASE" "$_legacy" 2>/dev/null; then
    _log "linked $_legacy -> $EVIDENCE_BASE"
  fi
fi
CRON_COMMAND="${CRON_COMMAND_TEMPLATE//\$\{SKILL6_EVIDENCE_BASE\}/$EVIDENCE_BASE}"

if ! command -v openclaw >/dev/null 2>&1; then
  _log "SKIP openclaw CLI not on PATH — cannot register '$CRON_NAME'. Re-run once the CLI is installed."
  exit 3
fi

# SK6001/SK6002 repair: print the id of an existing job that needs fixing:
# its --sweep-base is missing or flag-shaped (the "--idempotent" defect), or it
# points at a non-persistent $HOME path while the resolved folder lives under
# $HOME/.openclaw (Contabo) or /data (Hostinger). Shape-agnostic: scans every string in the job
# object. Prints nothing for a healthy job. Queries --all so a disabled job is
# still visible to the scan (findings 29/30).
_broken_job_id() {
  OC_CRON_RAW="$(openclaw cron list --all --json 2>/dev/null)" python3 - "$CRON_NAME" "${HOME:-}" "$EVIDENCE_BASE" "${SKILL6_DATA_ROOT:-/data}" <<'PYEOF' 2>/dev/null
import json, os, re, sys
name, home, want, droot = sys.argv[1], sys.argv[2].rstrip("/"), sys.argv[3], sys.argv[4].rstrip("/")
try:
    data = json.loads(os.environ.get("OC_CRON_RAW", ""))
except Exception:
    sys.exit(0)
jobs = data if isinstance(data, list) else data.get("jobs", [])
def strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from strings(v)
def stale(v):
    if not v or v.startswith("-"):
        return True
    # SK6003: persistent = ~/.openclaw (Contabo) or the /data volume (Hostinger).
    # A job under $HOME but outside both is thrown away on recreate, but only
    # when the wanted folder is itself persistent (Mac stays untouched).
    persist = (home + "/.openclaw/", droot + "/")
    return bool(home) and want.startswith(persist) and v != want \
        and v.startswith(home + "/") and not v.startswith(persist)
for j in jobs:
    if j.get("name") != name:
        continue
    for s in strings(j):
        # Quoted alternative first: a --sweep-base path containing SPACES must
        # be captured whole. The old `(\S*)` truncated at the first space, so
        # a stale spaced path read as healthy and the SK6001/2 repair silently
        # no-op'd (false OK — the two SK6002 suite failures under a
        # space-containing TMPDIR).
        m = re.search(r'--sweep-base(?:\s+|=)(?:"([^"]*)"|\'([^\']*)\'|(\S*))', s)
        if m and stale(next((g for g in m.groups() if g is not None), "").strip('"\'')):
            print(j.get("id") or j.get("jobId") or "")
            sys.exit(0)
PYEOF
}

# D10: a failed/unparseable `cron list --all --json` is UNKNOWN, not
# "absent" — adding on it creates duplicates. A DISABLED match is a
# TOMBSTONE: report it, never resurrect it. An ENABLED match is validated for
# delivery mode (finding 29) and repaired in place only where broken.
_cron_state "$CRON_NAME"; _cp_rc=$?
case "$_cp_rc" in
  0)
    _bad_id="$(_broken_job_id)"
    if [[ -n "$_bad_id" ]]; then
      # DONE only when the repaired job VERIFIEDLY reads back silent — the
      # "delivery silent" claim is checked, not assumed from the edit's rc
      # (a CLI that drops --no-deliver would otherwise get a false DONE).
      if openclaw cron edit "$_bad_id" --command "$CRON_COMMAND" --no-deliver >/dev/null 2>&1 \
         && _cron_state "$CRON_NAME" && _cron_delivery_silent; then
        _log "DONE '$CRON_NAME' cron repaired in place (job $_bad_id): --sweep-base now $EVIDENCE_BASE, delivery silent"
        exit 0
      fi
      _log "FAIL could not repair '$CRON_NAME' (job $_bad_id; openclaw cron edit rc!=0, or delivery still announces — this CLI may be ignoring --no-deliver). Non-fatal, re-run to retry."
      exit 3
    fi
    if _cron_ensure_silent "$CRON_NAME"; then
      _log "OK  '$CRON_NAME' cron already present (delivery silent), nothing to do"
      exit 0
    fi
    _log "FAIL '$CRON_NAME' cron already present but its delivery announces into client chat (job '${OC_CRON_JOB_ID:-?}') and the in-place repair failed. Non-fatal — fix: openclaw cron edit ${OC_CRON_JOB_ID:-<id>} --no-deliver"
    exit 3
    ;;
  1)
    : # absent — fall through and register
    ;;
  3)
    _log "OK  '$CRON_NAME' cron present but DISABLED (tombstone: deliberately disabled or auto-disabled after failures) — leaving it disabled, NOT resurrecting"
    exit 0
    ;;
  *)
    _log "FAIL could not determine a single '$CRON_NAME' job from 'openclaw cron list --all --json' (listing unreadable, or duplicate names an operator must dedupe) — NOT registering (would risk a duplicate). Non-fatal — re-run to backfill."
    exit 3
    ;;
esac

# --no-deliver: a maintenance-window sweep is an operator-internal tick, not
# a client-facing announcement — without this flag `openclaw cron add`
# defaults the new job's delivery mode to "announce", which would fan a
# routine reconciliation pass out as a visible notification every night. Fixed
# here at the source (U24 rebuild, 2026-07-18) rather than repeating the drift
# this exact installer previously shipped without it — see
# scripts/install-page-inventory-lifecycle-cron.sh (U31/B-U17), which carries
# the same fix, and the FIX-XC-08a incident
# (37-zhc-closeout/scripts/install-closeout-resume-cron.sh:85-90) this class
# of bug was first caught and named in.
if openclaw cron add --name "$CRON_NAME" --cron "$CRON_SCHEDULE" --tz "$CRON_TZ" \
     --command "$CRON_COMMAND" --no-deliver >/dev/null 2>&1 \
   && _cron_state "$CRON_NAME"; then
  # PROVE the --no-deliver above took before calling it DONE: a CLI that
  # accepts and silently ignores the flag would otherwise get a green
  # install while the fresh job announces into client chat (finding 29's
  # exact harm).
  if _cron_ensure_silent "$CRON_NAME"; then
    _log "DONE '$CRON_NAME' cron registered ($CRON_SCHEDULE $CRON_TZ)"
    exit 0
  fi
  _log "FAIL '$CRON_NAME' was registered but its delivery announces into client chat (job '${OC_CRON_JOB_ID:-?}') and the in-place repair failed — this CLI may be ignoring --no-deliver. Non-fatal — fix: openclaw cron edit ${OC_CRON_JOB_ID:-<id>} --no-deliver"
  exit 3
fi

_log "FAIL could not register '$CRON_NAME' (openclaw cron add rc!=0, or --command/--no-deliver unsupported on this CLI build). Non-fatal — re-run to backfill."
exit 3
