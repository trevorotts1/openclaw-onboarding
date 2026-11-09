#!/usr/bin/env bash
# qc-assert-skill-frontmatter-version.sh — P1-4 frontmatter/skill-version drift gate.
#
# Fails (exit 1) if ANY skill directory that has BOTH a SKILL.md carrying a
# top-level frontmatter `version:` field AND a sibling `skill-version.txt` has
# those two versions DISAGREE. This closes the gap that let 6 campaign skills
# (49,50,51,52,53,55) silently drift: CI G3 (version-consistency.yml) only
# bumps/enforces skill-version.txt and NOTHING checked it against the SKILL.md
# frontmatter the human-facing skill loader reads.
#
# Rules:
#   * A skill dir = any directory containing a `skill-version.txt`.
#   * If that dir's SKILL.md has NO top-level `version:` field in its YAML
#     frontmatter, the skill is SKIPPED (reported, never failed). This naturally
#     exempts skills whose version lives elsewhere (e.g. 06-ghl-install-pages,
#     whose version is nested under `metadata:`) with no hard-coded exemption
#     list to maintain.
#   * Leading `v` is normalized before comparison, so `v1.0.2` == `1.0.2`.
#   * A skill whose frontmatter version already agrees (e.g. 23-ai-workforce-
#     blueprint at 17.0.3 == 17.0.3) passes with no special-casing.
#   * A sibling `VERSION` file (skills 49/71/83 carry one) is a third release
#     stamp and must also equal skill-version.txt. It is checked even when the
#     SKILL.md has no top-level `version:` field, because that skip is about the
#     SKILL.md pair, not about VERSION. RES-002: Skill 49's VERSION sat at
#     v2.1.48 against a skill-version.txt of v2.1.49 (commit d0855b696 rolled
#     skill-version.txt + SKILL.md by hand and skipped VERSION) TWICE, and no
#     gate compared the two, so the split shipped silently both times.
#
# Exit codes:
#   0  — every checked skill's frontmatter `version:` == skill-version.txt
#        (and VERSION, when present, == skill-version.txt)
#   1  — INVARIANT VIOLATED (one or more skills drifted)
#   2  — could not resolve a repo root / no skill-version.txt found (environment)
#
# Usage:
#   bash scripts/qc-assert-skill-frontmatter-version.sh            # scan repo root
#   bash scripts/qc-assert-skill-frontmatter-version.sh --root DIR # scan DIR
#   bash scripts/qc-assert-skill-frontmatter-version.sh --self-test # embedded test
#
# Wired into:
#   - .github/workflows/skill-frontmatter-version-guard.yml (push/PR)
#
# v1.0.0 (P1-4 / July-3-Fixes)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Extract the TOP-LEVEL frontmatter `version:` value from a SKILL.md ─────────
# Prints the raw value (quotes/whitespace intact) or nothing if there is no
# top-level `version:` inside the first `---`…`---` YAML frontmatter block.
# "Top-level" = the `version:` token is at column 0, so a nested
# `metadata:\n  version: …` is deliberately NOT matched.
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
  # trim leading/trailing whitespace
  v="${v#"${v%%[![:space:]]*}"}"
  v="${v%"${v##*[![:space:]]}"}"
  # strip one layer of surrounding quotes
  case "$v" in
    \"*\") v="${v#\"}"; v="${v%\"}" ;;
    \'*\') v="${v#\'}"; v="${v%\'}" ;;
  esac
  # trim again in case the quotes wrapped padding
  v="${v#"${v%%[![:space:]]*}"}"
  v="${v%"${v##*[![:space:]]}"}"
  # strip a single leading v/V when followed by a digit
  case "$v" in
    [vV][0-9]*) v="${v#?}" ;;
  esac
  printf '%s' "$v"
}

# ── Scan a root directory for frontmatter/skill-version drift ──────────────────
# Returns: 0 = all agree, 1 = drift found, 2 = no skill-version.txt under root.
scan_root() {
  local root="$1"
  local vf dir smd fmraw svraw fmver svver base vfile vraw vver
  local -a drifted=()
  local -a vdrifted=()
  local -a skipped=()
  local checked=0 found=0

  while IFS= read -r vf; do
    found=$((found + 1))
    dir="$(dirname "$vf")"
    smd="$dir/SKILL.md"
    base="$(basename "$dir")"
    svraw="$(cat "$vf")"
    svver="$(normalize_version "$svraw")"

    # Third release stamp: a sibling VERSION file must equal skill-version.txt.
    # Checked before the SKILL.md skip below — that skip governs the SKILL.md
    # pair only, and a VERSION split is a defect whether or not SKILL.md
    # carries a top-level `version:` field.
    vfile="$dir/VERSION"
    if [ -f "$vfile" ]; then
      vraw="$(cat "$vfile")"
      vver="$(normalize_version "$vraw")"
      if [ "$vver" != "$svver" ]; then
        vdrifted+=("${base}|${vver}|${svver}")
      fi
    fi

    [ -f "$smd" ] || continue        # skill-version.txt with no SKILL.md → not ours
    fmraw="$(extract_frontmatter_version "$smd")"
    if [ -z "$fmraw" ]; then
      skipped+=("$base")
      continue
    fi
    fmver="$(normalize_version "$fmraw")"
    checked=$((checked + 1))
    if [ "$fmver" != "$svver" ]; then
      drifted+=("${base}|${fmver}|${svver}")
    fi
  done < <(find "$root" -type f -name skill-version.txt -not -path '*/node_modules/*' -not -path '*/.git/*' 2>/dev/null | LC_ALL=C sort)

  if [ "$found" -eq 0 ]; then
    echo "CANNOT RESOLVE — no skill-version.txt found under: $root" >&2
    return 2
  fi

  if [ "${#skipped[@]}" -gt 0 ]; then
    echo "SKIPPED (${#skipped[@]}) — SKILL.md has no top-level frontmatter version: ${skipped[*]}"
  fi

  if [ "${#drifted[@]}" -eq 0 ] && [ "${#vdrifted[@]}" -eq 0 ]; then
    echo "PASS — ${checked} skill(s) checked; every SKILL.md frontmatter version == skill-version.txt (and every VERSION == skill-version.txt)"
    return 0
  fi

  local rec name fm sv
  if [ "${#drifted[@]}" -gt 0 ]; then
    echo "INVARIANT VIOLATED — SKILL.md frontmatter <-> skill-version.txt drift on ${#drifted[@]} skill(s):" >&2
    for rec in "${drifted[@]}"; do
      name="${rec%%|*}"
      fm="${rec#*|}"; fm="${fm%%|*}"
      sv="${rec##*|}"
      printf '  %-45s SKILL.md version=%-10s != skill-version.txt=%s\n' "$name" "$fm" "$sv" >&2
    done
    echo "  Remedy: roll each SKILL.md frontmatter \`version:\` to match its skill-version.txt (or bump both together)." >&2
  fi
  if [ "${#vdrifted[@]}" -gt 0 ]; then
    echo "INVARIANT VIOLATED — VERSION <-> skill-version.txt drift on ${#vdrifted[@]} skill(s):" >&2
    for rec in "${vdrifted[@]}"; do
      name="${rec%%|*}"
      fm="${rec#*|}"; fm="${fm%%|*}"
      sv="${rec##*|}"
      printf '  %-45s VERSION=%-10s != skill-version.txt=%s\n' "$name" "$fm" "$sv" >&2
    done
    echo "  Remedy: roll the VERSION file to match skill-version.txt (never lower skill-version.txt); \`scripts/batch-prep.sh\` rolls every stamp a skill's own gate compares." >&2
  fi
  return 1
}

# ── Embedded self-test: proves FAIL-on-mismatch + PASS-on-match ───────────────
run_self_test() {
  local tmp fails=0 rc
  tmp="$(mktemp -d)"
  # shellcheck disable=SC2064
  trap "rm -rf '$tmp'" RETURN

  # Fixture A — MATCH tree (expect exit 0):
  #   70: plain match, 71: skip (no top-level version), 72: v-prefix normalizes equal,
  #   73: VERSION stamp agrees, 74: VERSION stamp agrees even where SKILL.md is skipped
  mkdir -p "$tmp/good/70-match" "$tmp/good/71-skip" "$tmp/good/72-vprefix" \
           "$tmp/good/73-vstamp" "$tmp/good/74-vstamp-skip"
  printf -- '---\nname: match\nversion: 1.2.3\n---\nbody\n' > "$tmp/good/70-match/SKILL.md"
  printf '1.2.3\n' > "$tmp/good/70-match/skill-version.txt"
  printf -- '---\nname: skip\nmetadata:\n  version: "9.9.9"\n---\nbody\n' > "$tmp/good/71-skip/SKILL.md"
  printf '4.5.6\n' > "$tmp/good/71-skip/skill-version.txt"
  printf -- '---\nversion: v2.0.0\n---\n' > "$tmp/good/72-vprefix/SKILL.md"
  printf '2.0.0\n' > "$tmp/good/72-vprefix/skill-version.txt"
  printf -- '---\nname: vstamp\nversion: 3.0.0\n---\n' > "$tmp/good/73-vstamp/SKILL.md"
  printf '3.0.0\n' > "$tmp/good/73-vstamp/skill-version.txt"
  printf 'v3.0.0\n' > "$tmp/good/73-vstamp/VERSION"
  printf -- '---\nname: vstamp-skip\nmetadata:\n  version: "1.1.1"\n---\n' > "$tmp/good/74-vstamp-skip/SKILL.md"
  printf '5.0.0\n' > "$tmp/good/74-vstamp-skip/skill-version.txt"
  printf '5.0.0\n' > "$tmp/good/74-vstamp-skip/VERSION"

  # Fixture B — MISMATCH tree (expect exit 1):
  mkdir -p "$tmp/bad/80-drift"
  printf -- '---\nname: drift\nversion: 1.0.0\n---\n' > "$tmp/bad/80-drift/SKILL.md"
  printf '1.0.2\n' > "$tmp/bad/80-drift/skill-version.txt"

  # Fixture C — VERSION-only split (expect exit 1): SKILL.md and skill-version.txt
  # agree, so ONLY the new VERSION dimension can fail this. This is the RES-002
  # shape (49: VERSION v2.1.48 vs skill-version.txt v2.1.49).
  mkdir -p "$tmp/badver/81-vdrift"
  printf -- '---\nname: vdrift\nversion: 1.0.2\n---\n' > "$tmp/badver/81-vdrift/SKILL.md"
  printf '1.0.2\n' > "$tmp/badver/81-vdrift/skill-version.txt"
  printf '1.0.1\n' > "$tmp/badver/81-vdrift/VERSION"

  # Fixture D — VERSION-only split where SKILL.md has no top-level version:
  # the skip must not bypass the VERSION comparison (expect exit 1).
  mkdir -p "$tmp/badver2/82-vdrift-skip"
  printf -- '---\nname: vdrift-skip\nmetadata:\n  version: "1.0.2"\n---\n' > "$tmp/badver2/82-vdrift-skip/SKILL.md"
  printf '1.0.2\n' > "$tmp/badver2/82-vdrift-skip/skill-version.txt"
  printf '1.0.1\n' > "$tmp/badver2/82-vdrift-skip/VERSION"

  echo "== self-test =="

  scan_root "$tmp/good" >/dev/null 2>&1; rc=$?
  if [ "$rc" -eq 0 ]; then
    echo "  [PASS] match fixture returns exit 0 (agree + v-normalize + skip + VERSION all handled)"
  else
    echo "  [FAIL] match fixture should PASS (exit 0) but returned $rc"; fails=$((fails + 1))
  fi

  scan_root "$tmp/bad" >/dev/null 2>&1; rc=$?
  if [ "$rc" -eq 1 ]; then
    echo "  [PASS] mismatch fixture returns exit 1 (drift detected, fail-closed)"
  else
    echo "  [FAIL] mismatch fixture should FAIL (exit 1) but returned $rc"; fails=$((fails + 1))
  fi

  scan_root "$tmp/badver" >/dev/null 2>&1; rc=$?
  if [ "$rc" -eq 1 ]; then
    echo "  [PASS] VERSION-split fixture returns exit 1 (third stamp compared, fail-closed)"
  else
    echo "  [FAIL] VERSION-split fixture should FAIL (exit 1) but returned $rc"; fails=$((fails + 1))
  fi

  scan_root "$tmp/badver2" >/dev/null 2>&1; rc=$?
  if [ "$rc" -eq 1 ]; then
    echo "  [PASS] VERSION split with skipped SKILL.md still returns exit 1 (skip does not bypass)"
  else
    echo "  [FAIL] VERSION split with skipped SKILL.md should FAIL (exit 1) but returned $rc"; fails=$((fails + 1))
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
  scan_root "$root"
  exit $?
}

main "$@"
