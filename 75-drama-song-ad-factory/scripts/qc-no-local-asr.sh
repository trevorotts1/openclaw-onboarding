#!/usr/bin/env bash
# qc-no-local-asr.sh — F17 static check (manual Part F F17, Critical;
# ADDENDUM 5; same lock as F14's qc-no-direct-kie.sh).
#
# Fails when a non-test file in a run folder or a scripts/core module is a
# hand-written whisper/asr/transcription script. Builders may never write
# their own transcription scripts: every check that needs words or word
# timing calls scripts/core/audio_c3/lyric_timing.py (the one transcription
# step). Cause: 2026-10-08 08:55 — six agent-written copies of the banned
# whisper stack ("medium.en") started at once (~3.5 GB each) and crashed the
# operator Mac at 09:00.
#
# Banned .py surfaces ('import whisper', 'import openai_whisper',
# 'from whisper import', 'from openai_whisper import', 'whisper.load(',
# 'openai-whisper') in run folders + scripts/core non-test files. The ONLY
# permitted local-ASR import is faster_whisper, and it lives ONLY in
# lyric_timing.py — a second faster_whisper importer in core is an offender
# too (the one transcription step owns the load and the Part D load guard).
# Prose is never an offender: only .py files that run are scanned.
#
# Scope: this skill tree (onboarding). The 999 copy is W3-A's — scanning it
# is their unit's job, not ours.
#
# Env: DRAMA75_CORE=<scripts/core dir> (default: resolve from this file),
# DRAMA75_RUN_DIRS=<colon-or-space-separated run folders> (default: none).
# Exit 0 = clean; 2 = offender found (paths printed); 1 = usage error.
set -u

here="$(cd "$(dirname "$0")" 2>/dev/null && pwd)"
core="${DRAMA75_CORE:-$here/core}"
run_dirs="${DRAMA75_RUN_DIRS:-}"
if [ ! -d "$core" ]; then
  echo "qc-no-local-asr: no core dir at $core (set DRAMA75_CORE)" >&2
  exit 1
fi

hits="$(mktemp "${TMPDIR:-/tmp}/qcnla-hits.XXXXXX")"
trap 'rm -f "$hits"' EXIT

# Run folders: banned surfaces in any .py file (tests exempt). The one
# transcription step lives in scripts/core, never inside a run folder.
if [ -n "$run_dirs" ]; then
  for d in $run_dirs; do
    [ -d "$d" ] || continue
    grep -rIlnE \
      --include='*.py' \
      --exclude-dir=__pycache__ --exclude-dir=.git --exclude-dir=node_modules \
      --exclude='test_*.py' --exclude='*_test.py' --exclude='conftest.py' \
      -e '(^|[^a-z_])import +whisper *($|#|$)' \
      -e '(^|[^a-z_])import +openai_whisper' \
      -e '(^|[^a-z_])from +whisper +import' \
      -e '(^|[^a-z_])from +openai_whisper +import' \
      -e 'whisper\.load' \
      -e 'openai-whisper' \
      "$d" 2>/dev/null >> "$hits" || true
  done
fi

# scripts/core non-test .py files: banned surfaces anywhere, plus a second
# faster_whisper importer (lyric_timing.py is the ONLY importer).
grep -rIlnE \
  --include='*.py' \
  --exclude-dir=__pycache__ --exclude-dir=.git \
  --exclude='test_*.py' --exclude='*_test.py' --exclude='conftest.py' \
  -e '(^|[^a-z_])import +whisper *($|#|$)' \
  -e '(^|[^a-z_])import +openai_whisper' \
  -e '(^|[^a-z_])from +whisper +import' \
  -e '(^|[^a-z_])from +openai_whisper +import' \
  -e 'whisper\.load' \
  -e 'openai-whisper' \
  "$core" 2>/dev/null >> "$hits" || true
grep -rIlnE \
  --include='*.py' \
  --exclude-dir=__pycache__ --exclude-dir=.git \
  --exclude='test_*.py' --exclude='*_test.py' --exclude='conftest.py' \
  -e 'faster_whisper' \
  "$core" 2>/dev/null \
| grep -vE '/audio_c3/lyric_timing\.py$' >> "$hits" || true

if [ -s "$hits" ]; then
  echo "qc-no-local-asr: HAND-WRITTEN WHISPER/ASR SURFACE — FAIL" >&2
  while IFS= read -r f; do
    echo "  offender: $f" >&2
  done < "$hits"
  exit 2
fi
echo "qc-no-local-asr: clean — the one transcription step is lyric_timing.py ($core)"
exit 0