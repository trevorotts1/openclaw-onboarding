#!/usr/bin/env bash
# pin-onbox-source-of-truth.sh — GK-28/U90 step (a): the ONLY sanctioned way
# to capture/update the sha256 baseline pin for the on-box "source of truth"
# agent-browser SKILL.md this skill's own SKILL.md defers to when present
# (~/clawd/skills/agent-browser/SKILL.md). Never hand-edit the .pin file.
#
# USAGE
#   pin-onbox-source-of-truth.sh              capture (or update) the pin
#                                              from the CURRENT on-box file —
#                                              an explicit, dated, deliberate
#                                              action; never run automatically
#                                              by QC.
#   pin-onbox-source-of-truth.sh --check       verify the live on-box file
#                                              still matches the pinned
#                                              baseline; never writes. Same
#                                              pass/fail semantics as
#                                              qc-agent-browser.sh's own gate.
#
# ENV OVERRIDE (testing only): AGENT_BROWSER_ONBOX_SKILLMD points at an
# alternate path instead of the real ~/clawd/skills/agent-browser/SKILL.md,
# so tests never touch a real machine's actual on-box copy.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PIN_FILE="$SKILL_DIR/references/onbox-agent-browser-skillmd.pin"
ONBOX="${AGENT_BROWSER_ONBOX_SKILLMD:-$HOME/clawd/skills/agent-browser/SKILL.md}"

# shellcheck source=./lib-onbox-drift.sh
source "$SCRIPT_DIR/lib-onbox-drift.sh"

MODE="capture"
[ "${1:-}" = "--check" ] && MODE="check"

if [ ! -f "$ONBOX" ]; then
  echo "INFO: no on-box source-of-truth file at $ONBOX — nothing to pin. (This skill's SKILL.md documents that path as OPTIONAL.)"
  exit 0
fi

if [ "$MODE" = "check" ]; then
  DRIFT="$(agent_browser_onbox_drift "$ONBOX" "$PIN_FILE")"
  case "$DRIFT" in
    MATCH)
      echo "PASS — $ONBOX matches the pinned baseline"
      exit 0 ;;
    NO-BASELINE-PINNED)
      echo "FAIL — no baseline pinned yet for $ONBOX. Review it, then run without --check to capture one." >&2
      exit 1 ;;
    DRIFT*)
      echo "FAIL — $ONBOX has DRIFTED from the pinned baseline: $DRIFT" >&2
      echo "       Review the change, then re-run without --check to re-pin (if accepted)." >&2
      exit 1 ;;
    ERROR:*)
      echo "FAIL — $DRIFT" >&2
      exit 1 ;;
    *)
      echo "PASS — nothing to check ($ONBOX not present)"
      exit 0 ;;
  esac
fi

HASH=""
if command -v sha256sum >/dev/null 2>&1; then
  HASH="$(sha256sum "$ONBOX" | awk '{print $1}')"
elif command -v shasum >/dev/null 2>&1; then
  HASH="$(shasum -a 256 "$ONBOX" | awk '{print $1}')"
else
  echo "ERROR: neither sha256sum nor shasum is available on PATH" >&2
  exit 2
fi
BYTES="$(wc -c < "$ONBOX" | tr -d ' ')"
DATE="$(date -u +%Y-%m-%d)"
mkdir -p "$(dirname "$PIN_FILE")"
{
  echo "# Pinned sha256 baseline for the on-box \"source of truth\" agent-browser"
  echo "# SKILL.md this skill's own SKILL.md defers to when present:"
  echo "#   ~/clawd/skills/agent-browser/SKILL.md"
  echo "# Captured explicitly by scripts/pin-onbox-source-of-truth.sh — never"
  echo "# auto-updated. Format: <sha256>  <byte-count>  <captured-date>"
  echo "$HASH  $BYTES  $DATE"
} > "$PIN_FILE"
echo "OK — pinned $ONBOX -> $PIN_FILE (sha256=$HASH, ${BYTES} bytes, $DATE)"
