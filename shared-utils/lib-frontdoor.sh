#!/usr/bin/env bash
# lib-frontdoor.sh — the ONE shared pipeline behind every update route (issue #10).
# ============================================================================
# WHAT IT DOES
#   After the onboarding updater has run (and on a route that owns it, after
#   any installed 999-setup has refreshed), this runs the shared tail every
#   route must never skip:
#
#     1. the repair runner      (OCT4 issues #5, #6, #7, #9, then
#                                author-missing-sops.py for the remaining gaps)
#     2. the health gate        (OCT4 issue #11: scripts/health/library-gate-check.sh)
#
#   A regression the gate sees IS the route's rollback signal: the calling
#   route rolls back on failure (the Sunday/operator routes already snapshot
#   first; force-update arms the pending flag and tells the box's agent, which
#   holds the rollback decision for its own route).
#
# CALLED BY (all three routes source this file):
#   update-skills.sh (repo root)          — the onboarding updater's own tail
#   scripts/weekly-full-update.sh         — the Sunday update's fallback path
#   force-update.sh                       — the "machine was off" manual path
#
# WHY A LIBRARY AND NOT THREE COPIES: three routes hand-written their tails
# independently and routes drifted (issue #10's whole defect). One module,
# sourced, is the only shape that cannot drift.
#
# FAIL-SOFT ON THE SHARED STAGE, NEVER SILENT: a stage that cannot run because
# a callee script is not installed on this box is reported as a KNOWN GAP
# ("incomplete-gaps"), printed to the log, and surfaced in the summary — it is
# never read as a pass, and never aborts a route that otherwise converged
# (the callee scripts arrive with the SAME release that ships this wiring;
# before that release lands, every box's route would hard-fail at the tail
# and roll back for nothing).
#
# Maintenance traffic only: OPENCLAW_MAINTENANCE_SILENT=1 is exported for the
# callees (same suppression the fleet roll uses) — nothing here may reach a
# client chat.
# ============================================================================
# shellcheck shell=bash

# Resolve the skills dir the same way the platform layer does: OPENCLAW_ROOT
# first (the fleet-refresh export), then /data/.openclaw (VPS), then ~/.openclaw,
# with the legacy ~/clawd/skills as a Mac fallback when the standard tree is
# absent.
frontdoor_skills_dir() {
  local r="${OPENCLAW_ROOT:-}"
  [ -n "$r" ] || { [ -d /data/.openclaw ] && r=/data/.openclaw; }
  [ -n "$r" ] || r="$HOME/.openclaw"
  if [ -d "$r/skills" ]; then printf '%s' "$r/skills"; return 0; fi
  if [ -d "$HOME/clawd/skills" ]; then printf '%s' "$HOME/clawd/skills"; return 0; fi
  printf '%s' "$r/skills"
}

# Run the shared tail. Sets FRONTDOOR_STATUS + FRONTDOOR_JSON:
#   status: ok | ran-with-notes | incomplete-gaps | gate-failed | gate-undetermined | failed
#   json:   the stage report (one line of JSON on the caller's stdout fd 9)
# Nothing here exits; the caller decides from the status.
frontdoor_run_stage() {
  local lib="$1"                       # path to shared-utils/oct4_frontdoor.py
  local py="${OC_FRONTDOOR_PYTHON:-python3}"
  FRONTDOOR_STATUS="failed"
  FRONTDOOR_JSON=""
  [ -f "$lib" ] || {
    echo "[front-door] FATAL: shared stage module missing: $lib" >&2
    FRONTDOOR_STATUS="failed"
    echo "{\"frontdoor\":{\"status\":\"failed\",\"reason\":\"module missing: $lib\"}}"
    return 1
  }
  local report
  report="$(OC_FRONTDOOR_PYTHON="$py" "$py" "$lib" --json 2>/dev/null)" || {
    echo "[front-door] WARN: shared stage could not run (module errored): $lib" >&2
    FRONTDOOR_STATUS="failed"
    echo "{\"frontdoor\":{\"status\":\"failed\",\"reason\":\"module errored: $lib\"}}"
    return 1
  }
  FRONTDOOR_JSON="$report"
  FRONTDOOR_STATUS="$(printf '%s' "$report" | OC_FRONTDOOR_PYTHON="$py" "$py" -c '
import json,sys
try:
    d=json.load(sys.stdin)
    print(d.get("status","failed"))
except Exception:
    print("failed")
')"
  echo "$report" | OC_FRONTDOOR_PYTHON="$py" "$py" -c '
import json,sys
d=json.load(sys.stdin)
rep=d.get("repair") or {}
steps=rep.get("steps") or {}
for name,s in steps.items():
    if not s.get("present"):
        print("[front-door]   repair %-22s NOT INSTALLED (%s)" % (name, s.get("path","")), file=sys.stderr)
        continue
    print("[front-door]   repair %-22s %s" % (name, s.get("meaning","?")), file=sys.stderr)
print("[front-door]   health-gate            %s" % (d.get("gate") or {}).get("meaning","absent"), file=sys.stderr)
print("[front-door] stage status: %s" % d.get("status","failed"), file=sys.stderr)
' >&2
  case "$FRONTDOOR_STATUS" in
    ok|ran-with-notes|incomplete-gaps) return 0 ;;
    *) return 1 ;;
  esac
}

# ── 999-setup refresh (only where it is ALREADY installed) ──────────────────
# The same guard-fenced refresh the fleet roll's runner performs
# (shared-utils/fleet_refresh_runner.py step_update_999): a git checkout whose
# origin is trevorotts1/999-setup is pulled --ff-only (local changes are never
# overwritten), then the checkout's own skill-link installer re-links its
# skills. Never installs 999 on a box that does not have it, never touches an
# archive extract, never a hand-managed copy. Ported here so every route (not
# just the roll) refreshes 999 — issue #10's "999-setup (if installed)" stage.
frontdoor_update_999() {
  local _home repo before after
  _home="$HOME"
  [ -d /data/.openclaw ] && _home="/data"
  # Candidate checkouts: the known clone locations, then the installed skill
  # symlinks' resolved parent (the same discovery shape the runner scans).
  repo=""
  local cand
  for cand in "$HOME/.claude-nine" "$HOME/.claude-nine/../999-setup" \
              "$_home/999-setup" "$HOME/999-setup"; do
    [ -n "$cand" ] || continue
    if [ -f "$cand/AGENT_INSTALL.md" ] && [ -f "$cand/CONTROL/bundled-skills.txt" ] \
       && [ -f "$cand/.claude/skills/nine-router-setup/scripts/setup-macos.sh" ]; then
      repo="$cand"; break
    fi
  done
  if [ -z "$repo" ]; then
    # Resolve through an installed skill link when the clones are elsewhere.
    local link
    for link in "$HOME/.claude/skills/nine-router-setup" \
                "$HOME/.claude-nine/skills/nine-router-setup" \
                "$_home/.claude/skills/nine-router-setup"; do
      if [ -L "$link" ]; then
        cand="$(cd "$link" && pwd -P)/../../.."
        cand="$(cd "$cand" 2>/dev/null && pwd -P)" || continue
        if [ -f "$cand/AGENT_INSTALL.md" ] && [ -f "$cand/CONTROL/bundled-skills.txt" ]; then
          repo="$cand"; break
        fi
      fi
    done
  fi
  if [ -z "$repo" ] || [ ! -d "$repo/.git" ]; then
    # A box that RUNS 9Router (cheap signals: ~/.9router or the claude-nine
    # launcher) but has no 999-setup checkout would otherwise never get 999
    # updates (bundled skills, nine-router-setup). Fetch a read-only checkout so
    # the guarded --skills-only path below can run. The full installer is NEVER
    # used on such a box and models/credentials are never touched: the
    # skills-only step runs between two checksum snapshots. A box with no
    # 9Router signal still gets nothing installed.
    local _clone_dest="$_home/999-setup"
    [ "$_home" = "$HOME" ] && _clone_dest="$HOME/999-setup"
    if { [ -d "$HOME/.9router" ] || [ -f "$HOME/.local/bin/claude-nine" ]; } \
       && command -v git >/dev/null 2>&1 && [ ! -e "$_clone_dest" ]; then
      echo "[front-door] 999-setup: 9Router box without a checkout — cloning $_clone_dest for the guarded skills-only refresh"
      if git clone --depth 1 --quiet https://github.com/trevorotts1/999-setup.git "$_clone_dest" 2>&1 | sed 's/^/[front-door]   /'; \
         [ -f "$_clone_dest/AGENT_INSTALL.md" ] && [ -d "$_clone_dest/.git" ]; then
        repo="$_clone_dest"
      else
        rm -rf "$_clone_dest" 2>/dev/null
        echo "[front-door] 999-setup: clone failed — skipping (try again next roll)" >&2
        return 0
      fi
    else
      echo "[front-door] 999-setup: not installed (no checkout, no 9Router signal) — skipping (never installs it)"
      return 0
    fi
  fi
  local origin
  origin="$(git -C "$repo" remote get-url origin 2>/dev/null || echo "")"
  case "$origin" in
    *trevorotts1/999-setup*) : ;;
    *) echo "[front-door] 999-setup at $repo: origin is not trevorotts1/999-setup — not touched"
       return 0 ;;
  esac
  if [ -n "$(git -C "$repo" status --porcelain --untracked-files=no 2>/dev/null)" ]; then
    echo "[front-door] 999-setup at $repo has local changes — not updated (the owner's work is never overwritten)"
    return 0
  fi
  before="$(git -C "$repo" rev-parse HEAD || true)"
  echo "[front-door] 999-setup: refreshing $repo (${before:0:12}) ..."
  local pull_out
  if ! pull_out="$(git -C "$repo" pull --ff-only --quiet 2>&1)"; then
    echo "[front-door] 999-setup: git pull --ff-only FAILED — leaving $repo unchanged: ${pull_out:0:200}" >&2
    return 1
  fi
  [ -n "$pull_out" ] && printf '%s\n' "$pull_out" | sed 's/^/[front-door]   /'
  after="$(git -C "$repo" rev-parse HEAD || true)"
  [ "$after" = "$before" ] && echo "[front-door] 999-setup: already current (${after:0:12})" \
                           || echo "[front-door] 999-setup: ${before:0:12} -> ${after:0:12}"
  # A box that already runs 9Router NEVER takes the link/installer path below
  # (it replaces ~/.claude/skills/nine-router-setup and can touch the launcher).
  # It gets the 999 installer's `--skills-only` between two checksum snapshots
  # (shared-utils/nine_router_guard.py). Cheap bash-only signals first, so a
  # missing python3/guard file still keeps the box off the link path.
  local _nr_guard _nr_here
  _nr_here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  _nr_guard="$_nr_here/nine_router_guard.py"
  if [ -d "$HOME/.9router" ] || [ -f "$HOME/.local/bin/claude-nine" ] \
     || { [ -f "$_nr_guard" ] && python3 "$_nr_guard" detect >/dev/null 2>&1; }; then
    if [ ! -f "$_nr_guard" ] || ! command -v python3 >/dev/null 2>&1; then
      echo "[front-door] 999-setup: 9Router box but the guard module/python3 is missing — skill step NOT run (the full installer is never used here)"
      return 0
    fi
    local _nr_out _nr_rc=0
    _nr_out="$(python3 "$_nr_guard" skills-only --repo "$repo" 2>&1)" || _nr_rc=$?
    printf '%s\n' "$_nr_out" | sed 's/^/[front-door]   /'
    case "$_nr_rc" in
      0) echo "[front-door] 999-setup: 9Router box — skills-only done, checksums MATCH"; return 0 ;;
      4) echo "[front-door] 999-setup: 9Router box — installer predates --skills-only, skill step NOT run"; return 0 ;;
      3) # a router/launcher file changed: tell the roll's runner (labels only), fail loudly
         [ -n "${NINE_ROUTER_GUARD_MARK:-}" ] && printf '%s\n' "$_nr_out" | sed -n 's/^\[9router-guard\] MISMATCH: //p' >> "$NINE_ROUTER_GUARD_MARK" 2>/dev/null
         echo "[front-door] 999-setup: 9Router guard MISMATCH — a router/launcher file changed" >&2; return 3 ;;
      *) echo "[front-door] 999-setup: 9Router skills-only failed (rc=$_nr_rc)" >&2; return 1 ;;
    esac
  fi
  # Re-link the skills the SAME WAY the roll's installer step does — the
  # runner's _999_LINK_SCRIPT, run verbatim in its own bash so the installer's
  # `set -euo pipefail` can never leak into this shell. The link script
  # self-identifies (last line must be the main entrypoint) before anything is
  # sourced, refuses an entrypoint change, and leaves hand-managed copies alone.
  local link_script="$repo/.claude/skills/nine-router-setup/scripts/setup-macos.sh"
  if [ ! -f "$link_script" ]; then
    echo "[front-door] 999-setup: installer not found at $link_script — links not re-run"
    return 0
  fi
  local bash4
  bash4="$(command -v bash || true)"
  [ -n "$bash4" ] || { echo "[front-door] 999-setup: no bash on PATH — links not re-run" >&2; return 1; }
  echo "[front-door] 999-setup: re-running the installer's skill-link step..."
  local out rc=0
  out="$(FRONTDOOR_999_REPO="$repo" bash -c '
    set -euo pipefail
    R="$FRONTDOOR_999_REPO"; S="$R/.claude/skills/nine-router-setup/scripts/setup-macos.sh"
    [ "$(tail -n 1 "$S")" = '"'"'main "$@"'"'"' ] || { echo "installer entrypoint changed: last line of $S is not main \"\$@\"" >&2; exit 3; }
    T="$(mktemp)"; trap '"'"'rm -f "$T"'"'"' EXIT
    sed '"'"'$d'"'"' "$S" > "$T"
    . "$T"
    declare -F link_skills_into_root >/dev/null 2>&1 || { echo "installer has no link_skills_into_root" >&2; exit 3; }
    REPO_ROOT="$R"; REPO_SKILL_DIR="$R/.claude/skills/nine-router-setup"
    PRIMARY="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
    ROOTS="$PRIMARY"
    [ -f "$HOME/.claude-nine/settings.json" ] && [ "$HOME/.claude-nine" != "$PRIMARY" ] && ROOTS="$ROOTS $HOME/.claude-nine"
    hand=""
    for root in $ROOTS; do
      while IFS= read -r s; do
        [ -n "$s" ] && [ -e "$root/skills/$s" ] && [ ! -L "$root/skills/$s" ] && hand="$hand $root/skills/$s"
      done < <(bundled_skills)
    done
    if [ -n "$hand" ]; then echo "HAND-MANAGED:$hand"; exit 0; fi
    rc=0
    for root in $ROOTS; do REPO_ROOT="$R" REPO_SKILL_DIR="$R/.claude/skills/nine-router-setup" link_skills_into_root "$root" || rc=$((rc + $?)); done
    exit "$rc"' 2>&1)" || rc=$?
  printf '%s\n' "$out" | sed 's/^/[front-door]   /'
  case "$out" in
    HAND-MANAGED:*) echo "[front-door] 999-setup: skill links left alone (hand-managed copies present)"; return 0 ;;
  esac
  if [ "$rc" -ne 0 ]; then
    echo "[front-door] 999-setup: installer skill step exited $rc" >&2
    return "$rc"
  fi
  echo "[front-door] 999-setup: skill links verified"
  return 0
}