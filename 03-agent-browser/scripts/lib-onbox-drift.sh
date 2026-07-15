#!/usr/bin/env bash
# lib-onbox-drift.sh — Skill 03 (agent-browser) — GK-28/U90 step (a): dual
# source-of-truth drift gate.
#
# ROOT CAUSE THIS CLOSES: SKILL.md defers to
# ~/clawd/skills/agent-browser/SKILL.md as "the source of truth" WHEN PRESENT
# (03:SKILL.md:19-25), but nothing ever checked whether that on-box copy had
# silently changed. That file lives OUTSIDE this repo (box-local, evolves
# independently of the wrapper) — there is nothing in-repo to byte-diff it
# against (unlike agent-browser.skill's four packaged docs, which DO have a
# same-repo on-disk source — see lib-archive-diff.sh). So the mechanism here
# is a PINNED sha256 BASELINE instead of a live source diff: an operator
# explicitly captures a known-good hash of the on-box file
# (scripts/pin-onbox-source-of-truth.sh), and every QC run re-hashes the live
# file and compares against that pin. Same shape as lib-archive-diff.sh
# (a pure report function; the caller decides PASS/FAIL), reused here so the
# wrapper and the machine copy can never silently diverge again.
#
# CONTRACT
#   agent_browser_onbox_drift <onbox-skillmd-path> <pin-file>
#     Prints exactly one line to stdout:
#       ""                              — <onbox-skillmd-path> does not
#                                          exist. Nothing to check (this
#                                          skill's SKILL.md already documents
#                                          the on-box copy is OPTIONAL — "if
#                                          that path exists").
#       "MATCH"                         — the on-box file's sha256 matches
#                                          the pinned baseline.
#       "NO-BASELINE-PINNED"            — the on-box file exists but no
#                                          baseline has ever been captured
#                                          (pin file missing, empty, or still
#                                          the UNCAPTURED placeholder).
#                                          FAIL-CLOSED: an unknown state is
#                                          treated as a gap to close, never a
#                                          silent pass.
#       "DRIFT sha256=<pinned> -> <live>"
#                                        — the on-box file exists, a baseline
#                                          IS pinned, and the live hash no
#                                          longer matches it.
#     Returns 0 always (pure report function — same convention as
#     agent_browser_archive_diff in lib-archive-diff.sh). Returns 2 only on an
#     environment failure (no sha256 tool available), with an "ERROR: …" line.
agent_browser_onbox_drift() {
  local onbox="$1" pinfile="$2"

  if [ -z "$onbox" ] || [ -z "$pinfile" ]; then
    echo "ERROR: agent_browser_onbox_drift requires <onbox-path> <pin-file>"
    return 2
  fi
  if [ ! -f "$onbox" ]; then
    echo ""
    return 0
  fi

  local live_hash
  if command -v sha256sum >/dev/null 2>&1; then
    live_hash="$(sha256sum "$onbox" 2>/dev/null | awk '{print $1}')"
  elif command -v shasum >/dev/null 2>&1; then
    live_hash="$(shasum -a 256 "$onbox" 2>/dev/null | awk '{print $1}')"
  else
    echo "ERROR: neither sha256sum nor shasum is available on PATH"
    return 2
  fi
  if [ -z "$live_hash" ]; then
    echo "ERROR: could not hash $onbox"
    return 2
  fi

  local pinned_hash=""
  if [ -f "$pinfile" ]; then
    pinned_hash="$(grep -v '^[[:space:]]*#' "$pinfile" 2>/dev/null | grep -v '^[[:space:]]*$' | head -1 | awk '{print $1}')"
  fi

  if [ -z "$pinned_hash" ] || [ "$pinned_hash" = "UNCAPTURED" ]; then
    echo "NO-BASELINE-PINNED"
    return 0
  fi

  if [ "$pinned_hash" = "$live_hash" ]; then
    echo "MATCH"
  else
    echo "DRIFT sha256=${pinned_hash} -> ${live_hash}"
  fi
  return 0
}
