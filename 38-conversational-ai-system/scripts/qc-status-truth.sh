#!/usr/bin/env bash
# Proves roadmap pending-feature claims agree with shipped stamps in SKILL.md
# and protocol titles. Proves document agreement, not that a feature works.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROADMAP="$ROOT/references/conversational-ai-strategic-roadmap.md"
SKILL="$ROOT/SKILL.md"
PROTOCOLS="$ROOT/protocols"

unverified() {
  printf 'UNVERIFIED: %s\n' "$1" >&2
  exit 2
}

[ -r "$ROADMAP" ] || unverified "roadmap missing or unreadable: references/conversational-ai-strategic-roadmap.md"
[ -r "$SKILL" ] || unverified "SKILL.md missing or unreadable"

HEADINGS="$(grep -E '^##[[:space:]]*(✅|📋)[[:space:]]*Feature[[:space:]]+[0-9]+' "$ROADMAP" || true)"
[ -n "$HEADINGS" ] || unverified "roadmap contains no recognized implemented or pending feature headings"

PENDING="$(printf '%s\n' "$HEADINGS" |
  grep -E '^##[[:space:]]*📋[[:space:]]*Feature[[:space:]]+[0-9]+' |
  sed -E 's/^##[[:space:]]*📋[[:space:]]*Feature[[:space:]]+([0-9]+).*/\1/' |
  sort -nu || true)"

# Pass 1: scan tokens left-to-right; associate each feature with the latest
# preceding version, recording each feature only once.
FEATURE_VERSIONS="$(awk '
{
  line = $0
  latest = ""
  while (match(line, /v1\.5\.[0-9]+|F[0-9]+/)) {
    token = substr(line, RSTART, RLENGTH)
    line = substr(line, RSTART + RLENGTH)
    if (token ~ /^v1\.5\.[0-9]+$/) {
      latest = token
    } else if (latest != "") {
      feature = substr(token, 2)
      if (!(feature in seen)) {
        seen[feature] = 1
        print feature "|" latest
      }
    }
  }
}' "$SKILL")"

# Pass 2: for features not paired in pass 1, accept a following version
# only when no other feature token occurs between the feature and version.
ALL_FEATURES="$(grep -Eo 'F[0-9]+' "$SKILL" |
  sed 's/^F//' |
  sort -nu || true)"

for feature in $ALL_FEATURES; do
  if printf '%s\n' "$FEATURE_VERSIONS" |
    grep -E "^${feature}\|" >/dev/null; then
    continue
  fi

  following_version="$(awk -v target="F${feature}" '
  {
    original = $0
    line = $0

    while (match(line, /F[0-9]+|v1\.5\.[0-9]+/)) {
      token = substr(line, RSTART, RLENGTH)
      pos = RSTART
      line = substr(line, RSTART + RLENGTH)

      if (token != target) {
        continue
      }

      remainder = substr(original, pos + length(target))
      if (match(remainder, /F[0-9]+/)) {
        remainder = substr(remainder, 1, RSTART - 1)
      }

      if (match(remainder, /v1\.5\.[0-9]+/)) {
        print substr(remainder, RSTART, RLENGTH)
        exit
      }
    }
  }' "$SKILL")"

  if [ -n "$following_version" ]; then
    FEATURE_VERSIONS="${FEATURE_VERSIONS}${FEATURE_VERSIONS:+
}${feature}|${following_version}"
  fi
done

[ -n "$FEATURE_VERSIONS" ] ||
  unverified "SKILL.md yields an empty feature-to-version table"

checked=0
contradictions=0

for feature in $PENDING; do
  checked=$((checked + 1))
  skill_version="$(printf '%s\n' "$FEATURE_VERSIONS" |
    grep -E "^${feature}\|" |
    head -n 1 |
    cut -d '|' -f 2 || true)"
  protocol_evidence=""

  if [ -d "$PROTOCOLS" ]; then
    for protocol in "$PROTOCOLS"/*.md; do
      [ -f "$protocol" ] || continue
      first_line="$(sed -n '1p' "$protocol")"
      if printf '%s\n' "$first_line" |
        grep -E "\(F${feature}[,\)]" >/dev/null; then
        protocol_evidence="${protocol#$ROOT/}"
        break
      fi
    done
  fi

  if [ -n "$skill_version" ] || [ -n "$protocol_evidence" ]; then
    printf 'CONTRADICTION: roadmap marks Feature %s 📋 pending, but' "$feature"
    if [ -n "$skill_version" ]; then
      printf ' SKILL.md carries a shipped stamp (%s)' "$skill_version"
    fi
    if [ -n "$protocol_evidence" ]; then
      if [ -n "$skill_version" ]; then
        printf ' and'
      fi
      printf ' %s names it' "$protocol_evidence"
    fi
    printf '\n'
    contradictions=$((contradictions + 1))
  fi
done

if [ "$contradictions" -gt 0 ]; then
  exit 1
fi

printf 'PASS: %s pending feature(s) checked, no shipped-evidence contradiction\n' "$checked"
exit 0
