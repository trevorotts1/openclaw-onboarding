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
# 'from whisper import', 'from openai_whisper import', dynamic
# import_module('whisper')) in run folders + scripts/core non-test files.
# The ONLY permitted local-ASR import is faster_whisper, and it lives ONLY
# in lyric_timing.py — a second faster_whisper importer in core is an
# offender too (the one transcription step owns the load and the Part D load
# guard). Prose is never an offender: only .py files are parsed.
#
# Scope: this skill tree (onboarding). The 999 copy is W3-A's — scanning it
# is their unit's job, not ours.
#
# Env: DRAMA75_CORE=<scripts/core dir> (default: resolve from this file),
# DRAMA75_RUN_DIRS=<colon-or-space-separated run folders> (default: none).
# A listed entry that is itself a folder is ONE path even when it contains
# spaces ("/mnt/Work Disk/runs/..."); a named folder that does not exist is
# a usage error, never a silent skip (a skipped folder is an unscanned one).
# Exit 0 = clean; 2 = offender found (paths printed); 1 = usage error.
#
# The decision itself is made by qc_static_checks.py, which reads and parses
# every file instead of reading grep output (S75-013): a file it cannot read
# or parse is a failure (exit 1), never a silent "clean".
set -u

here="$(cd "$(dirname "$0")" 2>/dev/null && pwd)"
core="${DRAMA75_CORE:-$here/core}"
run_dirs="${DRAMA75_RUN_DIRS:-}"
if [ ! -d "$core" ]; then
  echo "qc-no-local-asr: no core dir at $core (set DRAMA75_CORE)" >&2
  exit 1
fi

set -- no-local-asr --core "$core"
# Split on ':' and newlines only -- an unquoted `for d in $run_dirs` split a
# spaced path into fragments that were not folders and skipped them, so a
# planted script under any spaced TMPDIR scanned clean. Legacy
# space-separated lists still work: an entry that is not a folder is re-split
# on whitespace (globbing off). A piece that is not a folder is handed to the
# checker, which fails closed (exit 1) rather than skipping it.
if [ -n "$run_dirs" ]; then
  while IFS= read -r entry; do
    [ -n "$entry" ] || continue
    if [ -d "$entry" ]; then
      set -- "$@" --run-dir "$entry"
      continue
    fi
    set -f
    for d in $entry; do
      set -- "$@" --run-dir "$d"
    done
    set +f
  done < <(printf '%s\n' "$run_dirs" | tr ':' '\n')
fi

exec python3 -I "$here/qc_static_checks.py" "$@"
