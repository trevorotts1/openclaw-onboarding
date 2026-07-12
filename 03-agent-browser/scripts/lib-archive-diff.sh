#!/usr/bin/env bash
# lib-archive-diff.sh — Skill 03 (agent-browser) — P3-06 SINGLE source of truth
# for "does agent-browser.skill match the on-disk docs it is packaged from".
#
# WHY A SHARED HELPER (not duplicated in the packer AND the QC gate): the
# P3-06 root cause was a hand-packaged archive with NO regeneration step and
# NO drift check, so `agent-browser.skill` silently fell behind INSTALL.md/
# CORE_UPDATES.md. Two independent ad-hoc diff implementations (one in the
# packer's --check, one in qc-agent-browser.sh) would be exactly the kind of
# duplication that drifts again later. This file is sourced by both.
#
# CONTRACT
#   agent_browser_archive_diff <archive-zip-path> <source-dir>
#     Unzips <archive-zip-path> to a scratch dir, then for each of the four
#     canonical docs (INSTALL.md, SKILL.md, CHANGELOG.md, CORE_UPDATES.md)
#     compares the archived copy against <source-dir>/<doc> byte-for-byte.
#     Prints one line per differing (or missing-from-archive) file to stdout,
#     e.g.:
#       INSTALL.md
#       CORE_UPDATES.md (missing from archive)
#     Prints nothing on stdout when the archive is fully in sync.
#     Returns 0 always (this is a pure diff/report function — callers decide
#     PASS/FAIL/exit code from whether stdout was empty). Returns 2 only on an
#     environment failure (archive missing / unzip unavailable / unzip failed)
#     with a single line "ERROR: <reason>" on stdout so callers can surface it.
#
# The four docs this checks are the exact set INSTALL.md's TYP header + the
# CONFLICT RULE describe as this skill's shipped content — SKILL.md is the
# skill manifest, INSTALL.md/CORE_UPDATES.md/CHANGELOG.md are its docs. If a
# fifth doc is ever added to the skill folder and meant to ship in the
# archive, add its name to AGENT_BROWSER_ARCHIVE_DOCS below (ONE place).
AGENT_BROWSER_ARCHIVE_DOCS=(INSTALL.md SKILL.md CHANGELOG.md CORE_UPDATES.md)

agent_browser_archive_diff() {
  local archive="$1" src_dir="$2"
  local tmp inner_dir doc

  if [ -z "$archive" ] || [ -z "$src_dir" ]; then
    echo "ERROR: agent_browser_archive_diff requires <archive-path> <source-dir>"
    return 2
  fi
  if [ ! -f "$archive" ]; then
    echo "ERROR: archive not found: $archive"
    return 2
  fi
  if ! command -v unzip >/dev/null 2>&1; then
    echo "ERROR: 'unzip' is not available on PATH"
    return 2
  fi

  tmp="$(mktemp -d)" || { echo "ERROR: mktemp -d failed"; return 2; }

  if ! unzip -o -q "$archive" -d "$tmp" 2>/dev/null; then
    echo "ERROR: could not unzip $archive"
    rm -rf "$tmp"
    return 2
  fi

  # The shipped archive stores its docs one level down, under an
  # "agent-browser/" directory (the skill's own extraction convention).
  # Tolerate either that layout or a flat one, so this helper still works if
  # that convention ever changes.
  inner_dir="$tmp"
  if [ ! -f "$tmp/${AGENT_BROWSER_ARCHIVE_DOCS[0]}" ]; then
    local candidate
    candidate="$(find "$tmp" -mindepth 1 -maxdepth 1 -type d | head -1)"
    [ -n "$candidate" ] && inner_dir="$candidate"
  fi

  for doc in "${AGENT_BROWSER_ARCHIVE_DOCS[@]}"; do
    if [ ! -f "$inner_dir/$doc" ]; then
      echo "$doc (missing from archive)"
      continue
    fi
    if [ ! -f "$src_dir/$doc" ]; then
      echo "$doc (missing from on-disk source: $src_dir/$doc)"
      continue
    fi
    if ! diff -q "$inner_dir/$doc" "$src_dir/$doc" >/dev/null 2>&1; then
      echo "$doc"
    fi
  done

  rm -rf "$tmp"
  return 0
}
