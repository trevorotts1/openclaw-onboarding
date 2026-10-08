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

# ── 999-setup refresh (every box carries 999) ───────────────────────────────
# Every roll must leave a CLEAN, current trevorotts1/999-setup checkout and the
# bundled skills linked to it (NFX001 owner order). Steps:
#  1. Find every checkout (HOME/999-setup, Documents/999-setup, .claude-nine,
#     installed skill-link parents). Clean ones are pulled --ff-only. Dirty or
#     diverged ones are left UNTOUCHED (the owner's work is never overwritten)
#     and named in one log line.
#  2. If no clean checkout exists, clone one to $HOME/999-setup (never the full
#     installer; never 9Router config/models/credentials/.env/providers).
#  3. Link the skills from the clean checkout, per skill: a hand-managed real
#     directory is skipped alone, every other skill is linked; symlinks that
#     pointed at an untouched copy are repointed. Symlinks only, nothing deleted.
frontdoor_update_999() {
  local _home canon cand real repo="" origin before after pull_out
  local _seen=" " _fail=0 _untouched=""
  _home="$HOME"
  [ -d /data/.openclaw ] && _home="/data"
  canon="$_home/999-setup"
  local _cands link
  _cands="$canon
$HOME/999-setup
$canon-clean
$HOME/Documents/999-setup
$HOME/.claude-nine/../999-setup
$HOME/.claude-nine"
  for link in "$HOME/.claude/skills/nine-router-setup" \
              "$HOME/.claude-nine/skills/nine-router-setup" \
              "$_home/.claude/skills/nine-router-setup"; do
    if [ -L "$link" ]; then
      cand="$(cd "$link" 2>/dev/null && cd ../../.. 2>/dev/null && pwd -P)" || continue
      _cands="$_cands
$cand"
    fi
  done
  while IFS= read -r cand; do
    [ -n "$cand" ] && [ -d "$cand/.git" ] || continue
    { [ -f "$cand/AGENT_INSTALL.md" ] && [ -f "$cand/CONTROL/bundled-skills.txt" ] \
      && [ -f "$cand/.claude/skills/nine-router-setup/scripts/setup-macos.sh" ]; } || continue
    real="$(cd "$cand" && pwd -P)"
    case "$_seen" in *" $real "*) continue ;; esac
    _seen="$_seen$real "
    origin="$(git -C "$real" config --get remote.origin.url 2>/dev/null || echo "")"
    case "$origin" in
      *trevorotts1/999-setup*) : ;;
      *) echo "[front-door] 999-setup at $real: origin is not trevorotts1/999-setup — not touched"; continue ;;
    esac
    if [ -n "$(git -C "$real" status --porcelain --untracked-files=no 2>/dev/null)" ]; then
      _untouched="$_untouched $real (local changes)"; continue
    fi
    before="$(git -C "$real" rev-parse HEAD || true)"
    if ! pull_out="$(git -C "$real" pull --ff-only --quiet 2>&1)"; then
      if [ "$(git -C "$real" rev-list --count '@{u}..HEAD' 2>/dev/null || echo 0)" != 0 ] \
         && [ "$(git -C "$real" rev-list --count 'HEAD..@{u}' 2>/dev/null || echo 0)" != 0 ]; then
        _untouched="$_untouched $real (diverged)"; continue
      fi
      echo "[front-door] 999-setup: git pull --ff-only FAILED at $real — left unchanged: ${pull_out:0:200}" >&2
      _fail=1
    else
      after="$(git -C "$real" rev-parse HEAD || true)"
      [ "$after" = "$before" ] && echo "[front-door] 999-setup: $real already current (${after:0:12})" \
                               || echo "[front-door] 999-setup: $real ${before:0:12} -> ${after:0:12}"
    fi
    [ -n "$repo" ] || repo="$real"
  done <<FDEOF
$_cands
FDEOF
  if [ -z "$repo" ]; then
    local _clone_dest="$canon"
    [ -e "$_clone_dest" ] && _clone_dest="$canon-clean"
    if [ -e "$_clone_dest" ]; then
      echo "[front-door] 999-setup: no clean checkout and $_clone_dest is occupied — cannot clone" >&2
      return 1
    fi
    command -v git >/dev/null 2>&1 || { echo "[front-door] 999-setup: git missing — cannot clone" >&2; return 1; }
    echo "[front-door] 999-setup: no clean checkout — cloning $_clone_dest (links only; installer never run)"
    if git clone --depth 1 --quiet https://github.com/trevorotts1/999-setup.git "$_clone_dest" 2>&1 | sed 's/^/[front-door]   /'; \
       [ -f "$_clone_dest/AGENT_INSTALL.md" ] && [ -d "$_clone_dest/.git" ]; then
      repo="$(cd "$_clone_dest" && pwd -P)"
    else
      rm -rf "$_clone_dest" 2>/dev/null
      echo "[front-door] 999-setup: clone FAILED — 999 not refreshed this roll" >&2
      return 1
    fi
  fi
  [ -z "$_untouched" ] || echo "[front-door] 999-setup: UNTOUCHED (owner's work kept):$_untouched — using clean copy $repo for skill links"
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
  # Link the skills per skill, from the clean checkout, in a bash of their own so
  # the installer's `set -euo pipefail` never leaks here. Only the link
  # functions are taken from setup-macos.sh (entrypoint self-check kept); it is
  # sourced from its own scripts dir so its $0-derived paths resolve (B4), and
  # NINE_SETUP_SCRIPT_DIR carries the real dir for checkouts that honor it.
  local link_script="$repo/.claude/skills/nine-router-setup/scripts/setup-macos.sh"
  if [ ! -f "$link_script" ]; then
    echo "[front-door] 999-setup: installer not found at $link_script — links not re-run" >&2
    return 1
  fi
  command -v bash >/dev/null 2>&1 || { echo "[front-door] 999-setup: no bash on PATH — links not re-run" >&2; return 1; }
  echo "[front-door] 999-setup: linking skills from $repo (per skill)..."
  local out rc=0
  out="$(FRONTDOOR_999_REPO="$repo" bash -c '
    set -euo pipefail
    R="$FRONTDOOR_999_REPO"; D="$R/.claude/skills/nine-router-setup/scripts"; S="$D/setup-macos.sh"
    [ "$(tail -n 1 "$S")" = '"'"'main "$@"'"'"' ] || { echo "installer entrypoint changed: last line of $S is not main" >&2; exit 3; }
    T="$(mktemp)"; trap '"'"'rm -f "$T"'"'"' EXIT
    sed '"'"'$d'"'"' "$S" > "$T"
    cd "$D"; export NINE_SETUP_SCRIPT_DIR="$D"
    . "$T"
    declare -F link_one_skill >/dev/null 2>&1 || { echo "installer has no link_one_skill" >&2; exit 3; }
    REPO_ROOT="$R"; REPO_SKILL_DIR="$R/.claude/skills/nine-router-setup"
    PRIMARY="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
    ROOTS="$PRIMARY"
    [ -f "$HOME/.claude-nine/settings.json" ] && [ "$HOME/.claude-nine" != "$PRIMARY" ] && ROOTS="$ROOTS $HOME/.claude-nine"
    rc=0
    for root in $ROOTS; do
      mkdir -p "$root/skills"
      while IFS= read -r s; do
        [ -n "$s" ] || continue
        dst="$root/skills/$s"
        if [ -e "$dst" ] && [ ! -L "$dst" ]; then echo "skill HAND-MANAGED, skipped: $s ($dst)"; continue; fi
        src="$(resolve_skill_source "$s")"
        if [ -z "$src" ]; then echo "skill ERROR: $s: no source in $R" >&2; rc=$((rc + 1)); continue; fi
        [ "$src" != "$dst" ] || continue
        link_one_skill "$src" "$dst" "$s" || rc=$((rc + 1))
      done < <(bundled_skills)
    done
    exit "$rc"' 2>&1)" || rc=$?
  printf '%s\n' "$out" | sed 's/^/[front-door]   /'
  if [ "$rc" -ne 0 ]; then
    echo "[front-door] 999-setup: installer skill step exited $rc" >&2
    return "$rc"
  fi
  [ "$_fail" = 0 ] || { echo "[front-door] 999-setup: links done but a pull failed (see above)" >&2; return 1; }
  echo "[front-door] 999-setup: skill links verified"
  return 0
}
