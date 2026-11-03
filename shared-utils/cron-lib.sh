#!/usr/bin/env bash
# cron-lib.sh — shared helpers for idempotent `openclaw cron` presence checks.
#
# WHY THIS EXISTS (fix/industry-gate-and-idempotent-crons, 2026-07-11):
# `openclaw cron list`'s TEXT TABLE truncates names longer than ~22 chars
# (appends "..."). A positive-presence check via `grep -qF "<full-name>"`
# against that text table FALSE-NEGATIVES on any longer name — the guard thinks
# the cron is absent and a duplicate is registered on every re-run/wire. This is
# the confirmed root cause of the 6x-duplicate-cron incident in the
# real-estate-playbook (Skill 39: re-open-house-followup-scan,
# re-post-close-anniversary) and the conversational-ai-system (Skill 38:
# conversation-log-summarizer, proactive-suggestions-scan, etc.) — every one of
# those names exceeds ~22 chars.
#
# scripts/ensure-pipeline-crons.sh already fixed this for its own registrars in
# v13.0.2 (JSON exact-name match, no text-table fallback). This file extracts
# and generalizes that helper (`_cron_present` there -> `oc_cron_present` here)
# so every OTHER registrar can share the fix instead of re-copy-pasting the
# buggy text-grep. scripts/ensure-pipeline-crons.sh is left untouched (it is
# already correct and is the reference implementation this file mirrors).
#
# SECOND DEFECT — DISABLED JOBS INVISIBLE TO `cron list --json` (added same
# day, live-VPS finding): on a live box, `openclaw cron list --json` was
# observed returning 16 jobs against 31 rows actually present in the gateway's
# cron store — the 15 missing rows were DISABLED jobs. docs.openclaw.ai/cli/cron
# documents `cron list` with only `--agent` and `--json`; no `--all` /
# `--include-disabled` / `--status` filter is documented, and the docs do not
# state whether disabled jobs appear in the default listing (they DO document a
# computed per-job `status` field with a `disabled` value, which is ambiguous
# either way). Since this cannot be verified against a live gateway from this
# repo, `oc_cron_present` below does NOT assume any specific flag exists — it
# ONLY uses one if `cron list --help` itself advertises a full/all-status
# listing flag (feature-detected, exactly like every other CLI-shape probe in
# this codebase). That is a best-effort improvement only: on a CLI build with
# no such flag, a disabled+invisible job is still genuinely unseeable via
# `cron list --json` and no client-side JSON trick can recover it.
#
# The ACTUAL fix for "a disabled cron gets silently resurrected by the next
# install/update run" is therefore independent of CLI visibility: a DURABLE
# TOMBSTONE (oc_cron_tombstone / oc_cron_tombstoned below), mirroring the
# already-proven BOX_PARK_MARKER pattern (scripts/ensure-pipeline-crons.sh /
# resume-workforce-build.sh) that already durably prevents workforce-build-resume
# from being resurrected after an operator parks it. A registrar that checks
# oc_cron_tombstoned() before adding will never resurrect a cron an operator
# (or a future fleet-cleanup tool) has deliberately tombstoned — regardless of
# what `cron list --json` does or doesn't show. This does NOT retroactively fix
# already-disabled-and-invisible crons on already-affected boxes (that is
# live-box remediation, out of this branch's scope); it makes this repo's OWN
# registrars durably respect a tombstone going forward once one is written
# (by scripts/tombstone-cron.sh, an operator, or a future cleanup tool).
#
# DELIBERATELY NOT DONE — auto-dedup of EXISTING duplicate crons: a registrar
# in this file only ever decides add-or-skip for ITS OWN managed names; it
# never enumerates and collapses pre-existing duplicates found on a box. That
# is a mutating, box-wide cleanup action with its own audit/approval story
# (the live fleet-cleanup workflow already running in parallel) and is out of
# scope for an idempotent "presence check" library. Documented here as a
# deliberate judgment call, not an oversight.
#
# USAGE: `source` this file, then call `oc_cron_present "<name>"` in place of
#   `openclaw cron list | grep -q "<name>"`. Returns 0 = present, 1 = absent
#   (list read and parsed, name not in it), 2 = UNKNOWN (CLI failed or output
#   not parseable JSON). On 2 callers must NOT register (D10: failed list ->
#   "absent" -> duplicate crons); use `oc_cron_present X || [ $? -eq 2 ]` to
#   mean "present or unknown: skip registration". Callers
#   that manage a durable cron's lifecycle should ALSO check
#   `oc_cron_tombstoned "<name>"` before registering.
#
# bash-not-zsh.

# oc_cron_list_json_flags
#
# Feature-detects a "show every status, not just enabled" flag on `cron list`
# by grepping `cron list --help` for common candidate flag names. Prints the
# flag (with no argument — every candidate here is a boolean switch) if one is
# advertised, else prints nothing. NEVER invents/assumes a flag that --help
# doesn't literally show — see the "SECOND DEFECT" note above for why.
oc_cron_list_json_flags() {
  local help
  help="$(openclaw cron list --help 2>&1 || true)"
  local cand
  for cand in --all --include-disabled --show-disabled --status; do
    if printf '%s' "$help" | grep -qE -- "(^|[[:space:]])${cand}([[:space:]=<]|\$)"; then
      if [[ "$cand" == "--status" ]]; then
        printf -- '--status all'
      else
        printf '%s' "$cand"
      fi
      return 0
    fi
  done
  return 1
}

# oc_cron_present <name>
#
# Exact JSON `.name == <name>` match against `openclaw cron list --json`
# (plus a feature-detected full-visibility flag when the CLI advertises one —
# see oc_cron_list_json_flags above). Strategy (most to least reliable):
#   1. jq      — exact match against `--json` output.
#   2. python3 — same, via json.load (no jq dependency).
#   3. NEVER falls back to a positive text-table match — that is the root-cause
#      path. If neither JSON parser is available, returns 2 (UNKNOWN) so
#      callers neither claim false presence off a possibly-truncated table nor
#      register a duplicate.
#
# NOTE: this alone does NOT guarantee visibility of a disabled-and-invisible
# job on a CLI with no full-visibility flag (see header). Callers that need a
# disable to be DURABLE against re-registration must also honor
# oc_cron_tombstoned() — that check does not depend on list visibility at all.
oc_cron_present() {
  local name="$1"
  local -a extra_flags=()
  local detected
  if detected="$(oc_cron_list_json_flags)" && [[ -n "$detected" ]]; then
    # shellcheck disable=SC2206  # intentional word-split: "--status all" is 2 argv tokens
    extra_flags=( $detected )
  fi
  local raw
  # NOTE: `${extra_flags[@]+"${extra_flags[@]}"}` — safe empty-array expansion
  # under `set -u` on stock bash 3.2 (macOS default); a bare "${extra_flags[@]}"
  # on an empty array is an "unbound variable" error there.
  # D10: a failed CLI call is UNKNOWN (2), never "absent" — a slow/restarting
  # gateway used to read as "job absent" and every caller registered a duplicate.
  raw=$(openclaw cron list --json ${extra_flags[@]+"${extra_flags[@]}"} 2>/dev/null) || return 2
  [[ -n "$raw" ]] || return 2

  if command -v jq >/dev/null 2>&1; then
    # Prints true/false only for an array or {jobs:[...]}; anything else (log
    # noise, an error object, truncated JSON) prints nothing -> UNKNOWN.
    local verdict
    verdict=$(printf '%s' "$raw" | jq -r --arg n "$name" '
        ( if type == "array" then . elif (type == "object" and (.jobs | type) == "array") then .jobs else empty end )
        | map(select(.name == $n))
        | length > 0
      ' 2>/dev/null) || return 2
    [[ "$verdict" == "true" ]] && return 0
    [[ "$verdict" == "false" ]] && return 1
    return 2
  fi

  if command -v python3 >/dev/null 2>&1; then
    # NOTE: JSON is passed via env var, not a pipe — `python3 -` already reads
    # its OWN script text from stdin via the heredoc below, so a pipe feeding
    # the SAME stdin would be silently overridden (shellcheck SC2259) and
    # `sys.stdin.read()` inside the script would see EOF, not the JSON.
    OC_CRON_RAW="$raw" python3 - "$name" 2>/dev/null <<'PYEOF'
import json, os, sys
name = sys.argv[1]
try:
    data = json.loads(os.environ.get("OC_CRON_RAW", ""))
    jobs = data if isinstance(data, list) else data["jobs"]
    if not isinstance(jobs, list):
        raise ValueError
except Exception:
    sys.exit(2)
sys.exit(0 if any(isinstance(j, dict) and j.get("name") == name for j in jobs) else 1)
PYEOF
    return $?
  fi

  echo "[cron-lib] WARN oc_cron_present($name): jq and python3 both unavailable — cannot do a JSON exact-name match; returning UNKNOWN (2) so callers do not register a duplicate." >&2
  return 2
}

# ---------------------------------------------------------------------------
# DURABLE TOMBSTONE — makes a disable/removal survive re-registration
# REGARDLESS of whether `cron list --json` shows disabled jobs (see the
# "SECOND DEFECT" header note). Mirrors the proven BOX_PARK_MARKER pattern
# already used by scripts/ensure-pipeline-crons.sh /
# 23-ai-workforce-blueprint/scripts/resume-workforce-build.sh — a plain file
# under the box's durable state dir, checked before every (re)registration.
#
# oc_cron_tombstone_dir
#   Resolves <OC_ROOT>/workspace/.cron-tombstones (creating it best-effort).
#   OC_ROOT detection mirrors every other pipeline script: /data/.openclaw
#   (VPS) first, then $HOME/.openclaw (Mac). Prints the dir path, or nothing
#   if neither root resolves (callers then treat tombstone checks as "not
#   tombstoned" — fail OPEN on lookup, exactly like a missing OC_ROOT anywhere
#   else in this pipeline is a soft no-op, never a hard abort).
# ---------------------------------------------------------------------------
oc_cron_tombstone_dir() {
  local root
  if [[ -d /data/.openclaw ]]; then
    root="/data/.openclaw"
  elif [[ -d "${HOME}/.openclaw" ]]; then
    root="${HOME}/.openclaw"
  else
    return 1
  fi
  local dir="$root/workspace/.cron-tombstones"
  mkdir -p "$dir" 2>/dev/null || true
  printf '%s' "$dir"
  return 0
}

# oc_cron_tombstone_path <name> — the marker file for a given cron name.
# Sanitizes the name to a safe filename (cron names in this codebase are
# already kebab-case identifiers, but this guards against any stray char).
oc_cron_tombstone_path() {
  local name="$1" dir
  dir="$(oc_cron_tombstone_dir)" || return 1
  local safe
  safe="$(printf '%s' "$name" | tr -c 'A-Za-z0-9_.-' '_')"
  printf '%s/%s' "$dir" "$safe"
}

# oc_cron_tombstoned <name>
# Returns 0 if this cron name has a durable tombstone marker (an operator or
# tool deliberately removed/disabled it and it must NOT be re-registered),
# else 1. Fails OPEN (returns 1 = "not tombstoned") if OC_ROOT can't resolve —
# consistent with every other lookup in this file never hard-aborting a
# registrar over an unusual environment.
oc_cron_tombstoned() {
  local name="$1" path
  path="$(oc_cron_tombstone_path "$name")" || return 1
  [[ -f "$path" ]]
}

# oc_cron_tombstone <name> <reason>
# Writes the durable tombstone marker. Best-effort (never fatal to the
# caller). Intended callers: scripts/tombstone-cron.sh (operator-facing), any
# future fleet-cleanup tool that disables/removes a cron and wants that
# decision to survive the next install/update run, and (optionally) a
# registrar itself if it ever detects a cron in a disabled state it should
# stop managing.
oc_cron_tombstone() {
  local name="$1" reason="${2:-no reason given}" path
  path="$(oc_cron_tombstone_path "$name")" || return 1
  {
    printf 'TOMBSTONED %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)"
    printf 'name: %s\n' "$name"
    printf 'reason: %s\n' "$reason"
    printf 'host: %s\n' "$(hostname 2>/dev/null || echo box)"
  } > "$path" 2>/dev/null || return 1
  return 0
}

# oc_cron_untombstone <name> — operator-only un-tombstone (mirrors
# scripts/unpark-build.sh's un-park). Removes the marker so the registrar may
# register this name again on its next run.
oc_cron_untombstone() {
  local name="$1" path
  path="$(oc_cron_tombstone_path "$name")" || return 1
  rm -f "$path" 2>/dev/null || true
  return 0
}

# oc_cron_minute_jitter <name> <max-minutes (default 15)>
#
# Deterministic 0..(max-1) minute offset derived from this box's hostname +
# the cron name — STABLE across repeated installs/wires on the SAME box (never
# re-randomizes and so never itself causes a reschedule-diff loop), but differs
# box-to-box. Used so daily/hourly crons sharing a base schedule across the
# fleet don't all fire in the exact same wall-clock minute against a shared
# backend (belt-and-suspenders once Fix B has already made duplicates
# impossible by construction).
oc_cron_minute_jitter() {
  local name="$1" max="${2:-15}"
  case "$max" in ''|*[!0-9]*) max=15 ;; esac
  [[ "$max" -lt 1 ]] && max=1
  local seed hash
  seed="$(hostname 2>/dev/null || echo box)-$name"
  hash=$(printf '%s' "$seed" | cksum | awk '{print $1}')
  echo $(( hash % max ))
}

# ── Scheduled box update: Tuesday, Friday, Sunday 2:00 AM Eastern ─────────────
# The box's own update runs as a COMMAND cron job: OpenClaw runs the full
# updater (scripts/weekly-full-update.sh from main: onboarding skills, 999 where
# installed, Command Center, with snapshot + rollback) directly. No model turn is
# involved, so a dead model key or empty provider balance can never stop an
# update (2026-11-02: a box whose provider balance ran out timed out the old agent-prompt
# job), and nothing is ever sent to the client's chat (delivery none).
OC_BOX_UPDATE_CRON_NAME="weekly-onboarding-update"   # name kept: tombstones + presence checks key on it
OC_BOX_UPDATE_SCHEDULE="0 2 * * 0,2,5"               # Sun, Tue, Fri at 02:00
OC_BOX_UPDATE_TZ="America/New_York"                  # Eastern wall clock (follows daylight saving)
OC_BOX_UPDATE_COMMAND='f=$(mktemp) && curl -fsSL --max-time 120 https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/scripts/weekly-full-update.sh -o "$f" && bash "$f" >> "$HOME/.openclaw/skills/.update-log" 2>&1; rc=$?; rm -f "$f"; exit $rc'

# oc_box_update_cron_ensure
# 0 = the job is a current command job (already, or converted now)
# 1 = this OpenClaw has no command cron jobs -> caller keeps its agent-prompt path
# 2 = could not read the cron list or create the job -> caller keeps its agent-prompt path
# Old same-name jobs (the old agent-prompt job, duplicates) are removed by id
# (`openclaw cron delete --name` does not exist; `cron rm <id>` only), with
# retries: on a busy box `cron rm` can fail with a SQLite admission timeout.
# A job that still will not go away is reported loudly by id, and the next run
# keeps the current command job and removes only the leftovers (it never
# creates a second command job).
OC_BOX_UPDATE_RM_TRIES="${OC_BOX_UPDATE_RM_TRIES:-6}"
OC_BOX_UPDATE_RM_DELAY="${OC_BOX_UPDATE_RM_DELAY:-10}"

# _oc_box_update_job_ids: ids of jobs named $OC_BOX_UPDATE_CRON_NAME, one per line (non-zero if the list cannot be read)
_oc_box_update_job_ids() {
  local raw
  raw="$(openclaw cron list --json 2>/dev/null)" || return 1
  OC_CRON_JSON="$raw" python3 - "$OC_BOX_UPDATE_CRON_NAME" <<'PYEOF' 2>/dev/null
import json, os, sys
raw = os.environ.get("OC_CRON_JSON", "")
data = json.loads(raw[min([i for i in (raw.find("{"), raw.find("[")) if i >= 0] or [0]):])
for j in (data if isinstance(data, list) else data.get("jobs", [])):
    if j.get("name") == sys.argv[1] and j.get("id"):
        print(j["id"])
PYEOF
}

# _oc_box_update_rm_ids <id>...: remove each id, retrying until the list no longer shows it.
# Prints a loud warning naming every id that is still present; returns 1 if any remain.
_oc_box_update_rm_ids() {
  local left="$*" try=0 id present still
  while [ -n "${left// /}" ] && [ "$try" -lt "$OC_BOX_UPDATE_RM_TRIES" ]; do
    try=$((try + 1))
    for id in $left; do openclaw cron rm "$id" >/dev/null 2>&1 || true; done
    present="$(_oc_box_update_job_ids)" || present="__unreadable__"
    still=""
    for id in $left; do
      case "$present" in *"$id"*) still="$still $id" ;; esac
    done
    left="$still"
    [ -n "${left// /}" ] && [ "$try" -lt "$OC_BOX_UPDATE_RM_TRIES" ] && sleep "$OC_BOX_UPDATE_RM_DELAY"
  done
  if [ -n "${left// /}" ]; then
    echo "  ⚠ box update cron: could NOT remove old job(s)${left} after ${try} tries (box busy?) — the next update run removes them; or run: openclaw cron rm <id>"
    return 1
  fi
  return 0
}

oc_box_update_cron_ensure() {
  command -v openclaw >/dev/null 2>&1 || return 2
  command -v python3 >/dev/null 2>&1 || return 2
  openclaw cron add --help 2>&1 | grep -qE '^[[:space:]]*--command[[:space:]<]' || return 1
  local raw state keep old
  raw="$(openclaw cron list --json 2>/dev/null)" || return 2
  state="$(OC_CRON_JSON="$raw" python3 - "$OC_BOX_UPDATE_CRON_NAME" "$OC_BOX_UPDATE_SCHEDULE" "$OC_BOX_UPDATE_TZ" "$OC_BOX_UPDATE_COMMAND" <<'PYEOF' 2>/dev/null
import json, os, sys
name, expr, tz, cmd = sys.argv[1:5]
raw = os.environ.get("OC_CRON_JSON", "")
try:
    data = json.loads(raw[min([i for i in (raw.find("{"), raw.find("[")) if i >= 0] or [0]):])
except Exception:
    print("error"); sys.exit(0)
jobs = [j for j in (data if isinstance(data, list) else data.get("jobs", [])) if j.get("name") == name and j.get("id")]
def current(j):
    s, p = j.get("schedule") or {}, j.get("payload") or {}
    return (p.get("kind") == "command" and p.get("argv") == ["sh", "-lc", cmd]
            and s.get("expr") == expr and s.get("tz") == tz and j.get("enabled", True) is not False)
good = [j for j in jobs if current(j)]
if good:
    # keep <id> [old ids to remove...]
    print(" ".join(["keep", good[0]["id"]] + [j["id"] for j in jobs if j is not good[0]]))
else:
    print(" ".join(["create"] + [j["id"] for j in jobs]))
PYEOF
)"
  case "$state" in
    keep\ *)
      keep="$(echo "$state" | awk '{print $2}')"; old="$(echo "$state" | cut -d' ' -f3-)"
      [ "$old" = "$state" ] && old=""
      if [ -z "${old// /}" ]; then
        echo "  ✓ box update cron current (Tue/Fri/Sun 2:00 AM Eastern, command job, silent)"
        return 0
      fi
      echo "  ↻ box update cron current ($keep); removing leftover old job(s): $old"
      _oc_box_update_rm_ids $old || true
      return 0 ;;
    create*) old="${state#create}" ;;
    *) return 2 ;;
  esac
  if ! openclaw cron add --name "$OC_BOX_UPDATE_CRON_NAME" --cron "$OC_BOX_UPDATE_SCHEDULE" --tz "$OC_BOX_UPDATE_TZ" --exact \
       --description "Box update Tue/Fri/Sun 2:00 AM Eastern: runs scripts/weekly-full-update.sh from main (onboarding, 999 if installed, Command Center). Silent." \
       --command "$OC_BOX_UPDATE_COMMAND" --timeout-seconds 7200 --no-output-timeout-seconds 3600 --no-deliver >/dev/null 2>&1; then
    echo "  ⚠ box update cron: command-job create failed — existing job left in place"
    return 2
  fi
  # New job is in; only now remove the old ones (never leave a box with no update job).
  if [ -n "${old// /}" ]; then
    _oc_box_update_rm_ids $old || true
  fi
  echo "  ✓ box update cron installed: Tue/Fri/Sun 2:00 AM Eastern, command job, silent (replaced:${old:- none})"
  return 0
}
