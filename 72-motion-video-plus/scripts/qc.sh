#!/usr/bin/env bash
# Skill 72 technical QC wrapper (MG-034).
#
# Thin delegation to scripts/qc.py, the fail-closed QC
# implementation. The legacy script's own checks are gone: it
# printed PASS for its contact sheet whether or not the sheet
# build succeeded, counted grep matches for its black/freeze
# sweeps (so an ffmpeg failure read as zero defects), and compared
# the output's audio stream against its video stream instead of
# the plan (defect register D-QC-FALSE-GREEN). qc.py replaces all
# of it; this wrapper only keeps the invocation paths working.
#
# Usage (V2 job package):
#   bash scripts/qc.sh --job-dir job/ [--final renders/final.mp4]
#   bash scripts/qc.sh --plan plan.json --sidecar sidecar.json \
#       --media media.json --final final.mp4 [--coverage coverage.json]
#
# Usage (legacy V1 run, the historical path):
#   bash scripts/qc.sh --manifest run/manifest.json \
#       --workdir work --final final.mp4
# The legacy flags select qc.py's legacy lane: expectations derive
# from the manifest, every tool failure fails by name, and the
# contact sheet step's failure fails the gate.
set -u
SDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

legacy=0
has_workdir=0
for a in "$@"; do
  case "$a" in
    --legacy-manifest) legacy=1 ;;
    --workdir) has_workdir=1 ;;
  esac
done
if [ "$has_workdir" -eq 1 ]; then legacy=1; fi

if [ "$legacy" -eq 1 ]; then
  # Translate the historical --manifest flag to qc.py's
  # --legacy-manifest; every other argument passes through.
  args=()
  while [ $# -gt 0 ]; do
    case "$1" in
      --manifest) args+=(--legacy-manifest "$2"); shift 2 ;;
      *) args+=("$1"); shift ;;
    esac
  done
  exec python3 "$SDIR/qc.py" check "${args[@]}"
fi

exec python3 "$SDIR/qc.py" check "$@"
