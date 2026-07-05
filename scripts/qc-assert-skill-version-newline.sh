#!/usr/bin/env bash
# qc-assert-skill-version-newline.sh — FIX-IMG-09 (iv) trailing-newline lint.
#
# Fails (exit 1) if ANY skill directory's `skill-version.txt` does NOT end with a
# single trailing newline (`\n`). A missing trailing newline is what let
# `56/skill-version.txt` concatenate with an adjacent write into the corrupt
# `1.0.1v17.0.25` token observed in the image-delivery analysis: a tool that
# appends to (or `cat`s together) version files silently glued two versions into
# one because the first file had no terminating newline. This lint makes that
# class of corruption impossible to reintroduce.
#
# Rules:
#   * A skill dir = any directory containing a `skill-version.txt`.
#   * The file MUST be non-empty AND its final byte MUST be `\n`.
#   * node_modules / .git are excluded.
#
# Exit codes:
#   0  — every skill-version.txt ends with exactly one trailing newline
#   1  — INVARIANT VIOLATED (one or more files missing the trailing newline)
#   2  — could not resolve a repo root / no skill-version.txt found (environment)
#
# Usage:
#   bash scripts/qc-assert-skill-version-newline.sh            # scan repo root
#   bash scripts/qc-assert-skill-version-newline.sh --root DIR # scan DIR
#   bash scripts/qc-assert-skill-version-newline.sh --self-test # embedded test
#
# Wired into:
#   - .github/workflows/skill-version-newline-guard.yml (push/PR)
#
# v1.0.0 (FIX-IMG-09 / Wave-0 T-06)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Does a file end with exactly one trailing newline? ────────────────────────
# Returns 0 (true) when the file is non-empty AND its last byte is 0x0a.
ends_with_newline() {
  local f="$1"
  [ -s "$f" ] || return 1                 # empty file is a violation
  local last
  last="$(tail -c1 "$f")"
  # When the final byte is a newline, command substitution strips it and $last
  # is empty; any other final byte leaves $last non-empty.
  [ -z "$last" ]
}

# ── Scan a root directory for skill-version.txt files missing a trailing \n ────
scan_root() {
  local root="$1"
  local vf base
  local -a offenders=()
  local found=0

  while IFS= read -r vf; do
    found=$((found + 1))
    if ! ends_with_newline "$vf"; then
      base="$(basename "$(dirname "$vf")")"
      offenders+=("$base")
    fi
  done < <(find "$root" -type f -name skill-version.txt \
             -not -path '*/node_modules/*' -not -path '*/.git/*' 2>/dev/null \
           | LC_ALL=C sort)

  if [ "$found" -eq 0 ]; then
    echo "CANNOT RESOLVE — no skill-version.txt found under: $root" >&2
    return 2
  fi

  if [ "${#offenders[@]}" -eq 0 ]; then
    echo "PASS — ${found} skill-version.txt file(s) checked; every one ends with a trailing newline"
    return 0
  fi

  echo "INVARIANT VIOLATED — ${#offenders[@]} skill-version.txt file(s) missing a trailing newline:" >&2
  local name
  for name in "${offenders[@]}"; do
    printf '  %s/skill-version.txt\n' "$name" >&2
  done
  echo "" >&2
  echo "FIX: re-write each file WITH a trailing newline, e.g.:" >&2
  echo "  printf '%s\\n' \"\$(cat <dir>/skill-version.txt)\" > <dir>/skill-version.txt" >&2
  return 1
}

# ── Self-test: prove the gate fails on a no-newline fixture, passes on a good one
self_test() {
  local tmp
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN

  mkdir -p "$tmp/99-good-skill" "$tmp/98-bad-skill"
  printf '1.2.3\n' > "$tmp/99-good-skill/skill-version.txt"      # good (has \n)
  printf '4.5.6'    > "$tmp/98-bad-skill/skill-version.txt"      # bad  (no \n)

  # Must FAIL on the bad fixture.
  if scan_root "$tmp" >/dev/null 2>&1; then
    echo "SELF-TEST FAIL — gate PASSED on a no-newline fixture (should have failed)" >&2
    return 1
  fi

  # Must PASS once the bad fixture is fixed.
  printf '4.5.6\n' > "$tmp/98-bad-skill/skill-version.txt"
  if ! scan_root "$tmp" >/dev/null 2>&1; then
    echo "SELF-TEST FAIL — gate FAILED on an all-good fixture (should have passed)" >&2
    return 1
  fi

  echo "SELF-TEST PASS — gate fails on a missing-newline fixture and passes on a clean one"
  return 0
}

main() {
  local root="$REPO_ROOT"
  while [ $# -gt 0 ]; do
    case "$1" in
      --self-test) self_test; exit $? ;;
      --root) shift; root="${1:-$REPO_ROOT}" ;;
      *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
    shift
  done
  scan_root "$root"
  exit $?
}

main "$@"
