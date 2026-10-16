#!/usr/bin/env bash
# Skill 72 critique bundle assembler (MG-031).
#
# Thin wrapper: the real implementation is scripts/critique_bundle.py,
# which builds a coverage-indexed review bundle (paginated samples
# across the entire runtime, targeted frames from the compiled
# timeline, full-resolution and destination-size frames, and a
# coverage.json whose verdict fails loudly on missing coverage).
# This wrapper exists so the historical invocation keeps working:
#
#   bash scripts/critique-bundle.sh --video preview.mp4 --outdir review/r1 \
#       [--beats work/audio/beats.json]
#
# Any critique_bundle.py build flags may be passed through as well
# (--job-id, --timeline, --sidecar, --review-record, --interval,
# --destination, --sheet-columns, --tile-width). The exit code is the
# Python tool's Section 16.9 exit code, unchanged.
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/critique_bundle.py" build "$@"
