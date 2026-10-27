#!/bin/bash
# gate-added-paths.sh — repo path guard. Bans host-specific absolute paths in a
# branch's ADDED lines only (owner decision D-27, 2026-10-27).
#
# BANNED in added lines:  /Volumes/   /Users/
# NOT banned, on purpose:  /home/   /private/
#   /home/ appears in 166 files on main (599 hits /home/hatch, 228 /home/node,
#   110 /home/.openclaw) and /private/ in 61 files (77 /private/tmp). Those are
#   Docker and VPS paths the fleet depends on; a blanket ban turns main red.
#
# Added-lines-only: /Volumes/ already appears in 42 files on main, so a
# whole-tree scan would fail on main. Only what a change ADDS is judged.
#
# Usage: gate-added-paths.sh <repo> <base> <head> [--positive-control]
# Exit:  0 clean | 1 hits | 2 INSTRUMENT_ERROR (bad repo, bad/missing argument,
#        git failure, or a scan that cannot run). Never 0 when the scan failed.
set -uo pipefail

_die() { echo "INSTRUMENT_ERROR: $*" >&2; exit 2; }

repo="${1:-}"; base="${2:-}"; head="${3:-}"; mode="${4:-}"
if [ -z "$repo" ] || [ -z "$base" ] || [ -z "$head" ]; then
  echo "usage: gate-added-paths.sh <repo> <base> <head> [--positive-control]" >&2
  exit 2
fi
[ -d "$repo" ] || _die "repo is not a directory: $repo"
git -C "$repo" rev-parse --git-dir >/dev/null 2>&1 || _die "not a git repo: $repo"
git -C "$repo" rev-parse --verify --quiet "$base^{commit}" >/dev/null 2>&1 \
  || _die "cannot resolve base ref: $base"
git -C "$repo" rev-parse --verify --quiet "$head^{commit}" >/dev/null 2>&1 \
  || _die "cannot resolve head ref: $head"

if ! diff_out="$(git -C "$repo" diff -U0 "$base...$head" 2>&1)"; then
  _die "git diff failed for $base...$head: $(printf '%s' "$diff_out" | head -2 | tr '\n' ' ')"
fi

# A non-empty diff that carries no file headers means the format is not what
# this parser understands — fail closed instead of reporting "clean".
if [ -n "$diff_out" ]; then
  case "$diff_out" in
    *"diff --git "*) : ;;
    *) _die "diff output carries no file headers — scan cannot run" ;;
  esac
fi

added_lines=0; vol_hits=0; users_hits=0; detail=""
if [ -n "$diff_out" ]; then
  while IFS= read -r line; do
    # Strip file headers BEFORE the leading '+', or '+++ b/x' is miscounted
    # as an added line (ordering bug this project has been bitten by).
    case "$line" in
      '+++'*|'---'*) continue ;;
      '+'*) line="${line#+}" ;;
      *) continue ;;
    esac
    added_lines=$((added_lines + 1))
    case "$line" in
      *"/Volumes/"*) vol_hits=$((vol_hits + 1)); detail+="  VOLUMES ${line:0:200}"$'\n' ;;
    esac
    case "$line" in
      *"/Users/"*) users_hits=$((users_hits + 1)); detail+="  USERS   ${line:0:200}"$'\n' ;;
    esac
  done <<EOF
$diff_out
EOF
fi

echo "base=$base head=$head added_lines=$added_lines users_hits=$users_hits volumes_hits=$vol_hits"

if [ "$mode" = "--positive-control" ]; then
  [ "$added_lines" -gt 0 ] || _die "zero added lines — control cannot discriminate"
  echo "CONTROL: ok, instrument parsed $added_lines added lines"
  exit 0
fi

if [ "$vol_hits" -ne 0 ] || [ "$users_hits" -ne 0 ]; then
  printf '%s' "$detail"
  echo "GATE FAIL: banned absolute paths (/Volumes/, /Users/) present in added lines"
  exit 1
fi
echo "GATE PASS: 0 banned absolute paths in added lines"
exit 0
