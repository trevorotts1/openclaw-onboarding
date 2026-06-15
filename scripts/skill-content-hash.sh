#!/usr/bin/env bash
# ============================================================
#  skill-content-hash.sh — Shared Content-Hash Helper (Fix A1)
#
#  PURPOSE: Produce a deterministic per-skill content manifest
#  from a skills root directory. Used by update-skills.sh to
#  gate the version-stamp write on actual content parity, not
#  just a string match.
#
#  USAGE:
#    bash skill-content-hash.sh <skills-root-dir>
#
#  OUTPUT (to stdout):
#    One line per non-archived skill:
#      <skill-name>|<sha256-of-sorted-file-list-and-contents>
#    Final line:
#      __TREE_SHA__|<rollup-hash-over-all-per-skill-digests>
#
#  EXIT CODES:
#    0  — success
#    1  — skills-root-dir argument missing or not a directory
#    9  — neither shasum nor sha256sum is available
# ============================================================
set -euo pipefail

SKILLS_ROOT="${1:-}"
if [[ -z "$SKILLS_ROOT" || ! -d "$SKILLS_ROOT" ]]; then
  echo "ERROR: skill-content-hash.sh requires a skills root directory as \$1" >&2
  exit 1
fi

# ----------------------------------------------------------
# Detect SHA-256 tool once; fail loud if neither is present.
# ----------------------------------------------------------
_SHA_CMD=""
if command -v shasum >/dev/null 2>&1; then
  _SHA_CMD="shasum -a 256"
elif command -v sha256sum >/dev/null 2>&1; then
  _SHA_CMD="sha256sum"
else
  echo "ERROR: neither 'shasum' nor 'sha256sum' found — cannot compute content hashes" >&2
  exit 9
fi

# Helper: hash bytes from stdin
_hash_stdin() {
  $_SHA_CMD | awk '{print $1}'
}

# ----------------------------------------------------------
# Volatile / local-only files to exclude from content hash.
# ----------------------------------------------------------
_should_exclude() {
  local f="$1"
  local base
  base="$(basename "$f")"
  case "$base" in
    .wired-*|skill-version.txt|.onboarding-version|.onboarding-content-manifest.json)
      return 0 ;;
    *.bak|*.bak-pre-*)
      return 0 ;;
  esac
  case "$f" in
    */.git/*) return 0 ;;
  esac
  return 1
}

# ----------------------------------------------------------
# Iterate each non-archived numbered skill folder.
# ----------------------------------------------------------
ALL_SKILL_DIGESTS=""

while IFS= read -r -d '' SKILL_DIR; do
  skill_name="$(basename "$SKILL_DIR")"
  case "$skill_name" in *ARCHIVED*) continue ;; esac

  # Collect all non-excluded regular files, sorted deterministically.
  FILE_HASH_INPUT=""
  while IFS= read -r -d '' fpath; do
    _should_exclude "$fpath" && continue
    rel_path="${fpath#"$SKILL_DIR/"}"
    file_content_hash=$(LC_ALL=C $_SHA_CMD "$fpath" 2>/dev/null | awk '{print $1}')
    FILE_HASH_INPUT="${FILE_HASH_INPUT}${rel_path}:${file_content_hash}"$'\n'
  done < <(find "$SKILL_DIR" -type f -print0 2>/dev/null | LC_ALL=C sort -z)

  if [[ -z "$FILE_HASH_INPUT" ]]; then
    skill_digest="empty"
  else
    skill_digest=$(printf '%s' "$FILE_HASH_INPUT" | $_SHA_CMD | awk '{print $1}')
  fi

  echo "${skill_name}|${skill_digest}"
  ALL_SKILL_DIGESTS="${ALL_SKILL_DIGESTS}${skill_name}:${skill_digest}"$'\n'

done < <(find "$SKILLS_ROOT" -maxdepth 1 -mindepth 1 -type d -name '[0-9]*' -print0 2>/dev/null \
         | LC_ALL=C sort -z)

# Rollup hash
if [[ -z "$ALL_SKILL_DIGESTS" ]]; then
  TREE_SHA="empty"
else
  TREE_SHA=$(printf '%s' "$ALL_SKILL_DIGESTS" | $_SHA_CMD | awk '{print $1}')
fi

echo "__TREE_SHA__|${TREE_SHA}"
