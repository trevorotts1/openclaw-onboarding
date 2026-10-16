#!/usr/bin/env bash
# assemble.sh: compatibility wrapper (MG-022). The assembly
# implementation lives in assemble.py next to this script; this
# wrapper only preserves the historical command line:
#
#   assemble.sh --manifest M --workdir W --voiceover V --out O
#               [--score S] [--beats B] [--sfx-dir D]
#
# Exit codes are assemble.py's: 0 ok, 2 usage, 3 input missing,
# 4 plan invalid or media/plan mismatch, 5 ffmpeg failed,
# 6 output verification failed. Failures print a structured JSON
# finding on stderr and leave the ffmpeg log in the workdir; see
# references/assembly.md.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$DIR/assemble.py" --legacy "$@"
