#!/usr/bin/env bash
# qc-assert-skill-version-agreement.sh — VGD-002 per-skill VERSION agreement gate.
#
# Fails (exit 1) if ANY skill directory that carries its own `VERSION` file has
# that VERSION disagree with its sibling `skill-version.txt` or — when the
# sibling SKILL.md carries a top-level frontmatter `version:` field — with that
# field too. All three markers must agree pairwise.
#
# This closes the gap VGD-001 found: NO guard reads a skill's own VERSION file.
# CI G3 (version-consistency.yml) bumps skill-version.txt, and the frontmatter
# guard checks SKILL.md against skill-version.txt, so a stale VERSION ships
# with CI green. Measured 2026-11-09 on origin/main 28bdf14ebac9:
# 49-signature-funnel/VERSION read v2.1.48 while skill-version.txt AND the
# SKILL.md frontmatter both read v2.1.49.
#
# Rules:
#   * A guarded pair = any directory containing BOTH a file named exactly
#     `VERSION` and a sibling `skill-version.txt`. Discovered from the actual
#     files — no hard-coded skill list. A lone VERSION with no sibling
#     skill-version.txt (e.g. shared-utils/manifest/VERSION) is NOT a skill
#     version record and is skipped, never failed.
#   * If the dir's SKILL.md has NO top-level `version:` field in its YAML
#     frontmatter, only VERSION <-> skill-version.txt is compared (same skip
#     semantics as the frontmatter guard — e.g. a version nested under
#     `metadata:` stays exempt with no exemption list to maintain).
#   * Leading `v` is normalized before comparison, so `v1.0.2` == `1.0.2`.
#   * This guard is ADDITIVE. G1, G1b, G2, G3, the newline guard and the
#     frontmatter guard are untouched and keep running exactly as before.
#
# Exit codes:
#   0  — every guarded pair agrees (or no guarded pair exists — nothing to check)
#   1  — INVARIANT VIOLATED (one or more skills disagree)
#   2  — could not resolve a repo root (environment)
#
# Usage:
#   bash scripts/qc-assert-skill-version-agreement.sh            # scan repo root
#   bash scripts/qc-assert-skill-version-agreement.sh --root DIR # scan DIR
#   bash scripts/qc-assert-skill-version-agreement.sh --self-test # embedded test
#
# Wired into:
#   - .github/workflows/version-consistency.yml (push/PR, always runs)
#
# v1.0.0 (VGD-002)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Extract the TOP-LEVEL frontmatter `version:` value from a SKILL.md ─────────
# Same semantics as qc-assert-skill-frontmatter-version.sh: prints the raw value
# or nothing when there is no column-0 `version:` inside the first ---...--- block.
extract_frontmatter_version() {
  awk '
    BEGIN { fence = 0 }
    {
      if ($0 == "---") {
        fence++
        if (fence >= 2) exit      # end of frontmatter block
        next
      }
      if (fence == 1 && $0 ~ /^version:/) {
        val = $0
        sub(/^version:[ \t]*/, "", val)
        print val
        exit
      }
    }
  ' "$1"
}

# ── Normalize a version string for comparison ─────────────────────────────────
# Trims whitespace/CR, strips one layer of surrounding quotes, and drops a single
# leading `v`/`V` when it precedes a digit (so `v1.0.2` compares equal to `1.0.2`).
normalize_version() {
  local v="$1"
  v="${v//$'\r'/}"
  v="${v#"${v%%[![:space:]]*}"}"
  v="${v%"${v##*[![:space:]]}"}"
  case "$v" in
    \"*\") v="${v#\"}"; v="${v%\"}" ;;
    \'*\') v="${v#\'}"; v="${v%\'}" ;;
  esac
  v="${v#"${v%%[![:space:]]*}"}"
  v="${v%"${v##*[![:space:]]}"}"
  case "$v" in
    [vV][0-9]*) v="${v#?}" ;;
  esac
  printf '%s' "$v"
}

# ── Scan a root directory for VERSION / skill-version.txt / frontmatter drift ──
# Returns: 0 = all agree, 1 = drift found.
scan_root() {
  local root="$1"
  local vf dir base svf smd vraw svraw fmraw vver svver fmver
  local -a drifted=()
  local -a skipped_nopair=()
  local checked=0 found=0

  while IFS= read -r vf; do
    found=$((found + 1))
    dir="$(dirname "$vf")"
    base="$(dirname "$vf" | sed "s|^$root/||")"
    svf="$dir/skill-version.txt"
    if [ ! -f "$svf" ]; then
      skipped_nopair+=("$base")
      continue
    fi
    smd="$dir/SKILL.md"
    vraw="$(cat "$vf")"
    svraw="$(cat "$svf")"
    vver="$(normalize_version "$vraw")"
    svver="$(normalize_version "$svraw")"
    checked=$((checked + 1))
    if [ "$vver" != "$svver" ]; then
      drifted+=("${base}|VERSION=${vver}|skill-version.txt=${svver}")
      continue
    fi
    if [ -f "$smd" ]; then
      fmraw="$(extract_frontmatter_version "$smd")"
      if [ -n "$fmraw" ]; then
        fmver="$(normalize_version "$fmraw")"
        if [ "$fmver" != "$svver" ]; then
          drifted+=("${base}|SKILL.md version=${fmver}|skill-version.txt=${svver}")
        fi
      fi
    fi
  done < <(find "$root" -type f -name VERSION -not -path '*/node_modules/*' -not -path '*/.git/*' 2>/dev/null | LC_ALL=C sort)

  if [ "${#skipped_nopair[@]}" -gt 0 ]; then
    echo "SKIPPED (${#skipped_nopair[@]}) — VERSION with no sibling skill-version.txt (not a skill record): ${skipped_nopair[*]}"
  fi

  if [ "$checked" -eq 0 ]; then
    echo "PASS — no guarded pair (VERSION + skill-version.txt) found under: $root"
    return 0
  fi

  if [ "${#drifted[@]}" -eq 0 ]; then
    echo "PASS — ${checked} skill(s) checked; VERSION == skill-version.txt == SKILL.md frontmatter everywhere"
    return 0
  fi

  echo "INVARIANT VIOLATED — per-skill VERSION disagreement on ${#drifted[@]} skill(s):" >&2
  local rec name rest
  for rec in "${drifted[@]}"; do
    name="${rec%%|*}"
    rest="${rec#*|}"
    printf '  %-45s %s\n' "$name" "$rest" >&2
  done
  echo "  Remedy: roll the stale marker to match its siblings (VERSION, skill-version.txt" >&2
  echo "  and SKILL.md frontmatter version: must all agree), then commit all together." >&2
  return 1
}

# ── Embedded self-test: proves FAIL-on-mismatch + PASS-on-match ───────────────
run_self_test() {
  local tmp fails=0 rc
  tmp="$(mktemp -d)"
  # shellcheck disable=SC2064
  trap "rm -rf '$tmp'" RETURN

  # Fixture GOOD — must PASS (exit 0):
  #   70: triple agree; 71: v-prefix normalizes equal; 72: no top-level
  #   frontmatter version -> two-file compare only; lone/: VERSION with no
  #   sibling skill-version.txt -> skipped, never failed.
  mkdir -p "$tmp/good/70-triple" "$tmp/good/71-vprefix" "$tmp/good/72-nofm" "$tmp/good/lone"
  printf -- '---\nname: triple\nversion: 1.2.3\n---\nbody\n' > "$tmp/good/70-triple/SKILL.md"
  printf '1.2.3\n' > "$tmp/good/70-triple/skill-version.txt"
  printf '1.2.3\n' > "$tmp/good/70-triple/VERSION"
  printf -- '---\nname: vp\nversion: v2.0.0\n---\n' > "$tmp/good/71-vprefix/SKILL.md"
  printf '2.0.0\n' > "$tmp/good/71-vprefix/skill-version.txt"
  printf 'v2.0.0\n' > "$tmp/good/71-vprefix/VERSION"
  printf -- '---\nname: nofm\nmetadata:\n  version: "9.9.9"\n---\nbody\n' > "$tmp/good/72-nofm/SKILL.md"
  printf '4.5.6\n' > "$tmp/good/72-nofm/skill-version.txt"
  printf '4.5.6\n' > "$tmp/good/72-nofm/VERSION"
  printf '7.7.7\n' > "$tmp/good/lone/VERSION"

  # Fixture BAD-VERSION — VERSION stale vs skill-version.txt (expect exit 1).
  mkdir -p "$tmp/badver/80-stale"
  printf -- '---\nname: stale\nversion: 1.0.2\n---\n' > "$tmp/badver/80-stale/SKILL.md"
  printf '1.0.2\n' > "$tmp/badver/80-stale/skill-version.txt"
  printf '1.0.1\n' > "$tmp/badver/80-stale/VERSION"

  # Fixture BAD-FM — skill-version.txt vs frontmatter (expect exit 1).
  mkdir -p "$tmp/badfm/81-drift"
  printf -- '---\nname: drift\nversion: 1.0.0\n---\n' > "$tmp/badfm/81-drift/SKILL.md"
  printf '1.0.2\n' > "$tmp/badfm/81-drift/skill-version.txt"
  printf '1.0.2\n' > "$tmp/badfm/81-drift/VERSION"

  echo "== self-test =="

  scan_root "$tmp/good" >/dev/null 2>&1; rc=$?
  if [ "$rc" -eq 0 ]; then
    echo "  [PASS] agree fixture returns exit 0 (triple + v-normalize + no-fm + lone-VERSION all handled)"
  else
    echo "  [FAIL] agree fixture should PASS (exit 0) but returned $rc"; fails=$((fails + 1))
  fi

  scan_root "$tmp/badver" >/dev/null 2>&1; rc=$?
  if [ "$rc" -eq 1 ]; then
    echo "  [PASS] stale-VERSION fixture returns exit 1 (drift detected, fail-closed)"
  else
    echo "  [FAIL] stale-VERSION fixture should FAIL (exit 1) but returned $rc"; fails=$((fails + 1))
  fi

  scan_root "$tmp/badfm" >/dev/null 2>&1; rc=$?
  if [ "$rc" -eq 1 ]; then
    echo "  [PASS] frontmatter-drift fixture returns exit 1 (drift detected, fail-closed)"
  else
    echo "  [FAIL] frontmatter-drift fixture should FAIL (exit 1) but returned $rc"; fails=$((fails + 1))
  fi

  if [ "$fails" -eq 0 ]; then
    echo "SELF-TEST PASS"
    return 0
  fi
  echo "SELF-TEST FAIL ($fails)" >&2
  return 1
}

# ── Entry point ───────────────────────────────────────────────────────────────
main() {
  local root="$REPO_ROOT"
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --self-test) run_self_test; exit $? ;;
      --root) shift; root="${1:?--root needs a directory}" ;;
      -h|--help)
        grep -E '^#( |$)' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
        exit 0 ;;
      *) root="$1" ;;
    esac
    shift
  done
  if [ ! -d "$root" ]; then
    echo "CANNOT RESOLVE — not a directory: $root" >&2
    exit 2
  fi
  scan_root "$root"
  exit $?
}

main "$@"
