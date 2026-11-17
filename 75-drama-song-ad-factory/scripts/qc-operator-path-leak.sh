#!/usr/bin/env bash
# Manual 02 B6 static check — no operator/build-workspace paths in core code.
#
# Fails when any non-test file under 75-drama-song-ad-factory/scripts/core/
# (paths not matching test_*.py) contains:
#   • 'Downloads'
#   • 'drama-song-factory-build'
#   • the path-like occurrence 'openclaw-onboarding/'
#
# Why. B3/B6: the operator Mac is a contaminated test bed — code in
# scripts/core/ looked into ~/Downloads and the build workspace, so the
# green suite on that box proved nothing about a client box. The C3 unit
# removed the operator-home defaults; this guard keeps them out: any
# reintroduction of an operator path as a load-bearing search root is a red
# build, not a silent pass. test_*.py files are exempt (they plant the
# needles at run time to prove the ban bites); generated __pycache__ is
# skipped; binary-ish files are skipped.
#
# Fails closed: no scanned files found == fail (a moved/deleted tree must
# not produce a green check). No network; no writes. The scan itself is done
# by qc_static_checks.py (S75-013), which opens every file and treats an
# unreadable one as a failure instead of a silent pass — a Python parse, so
# the old bash >= 4 / mapfile requirement is gone.
#
# Exit numbers are THIS script's historical ones, which the workflow and the
# manual are written against: 0 clean, 1 offender(s), 2 could not run or no
# files found. qc_static_checks.py uses the shared 0/2/1 contract, so the
# mapping is done here, not there.
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CORE="$SKILL_DIR/scripts/core"

if [ ! -d "$CORE" ]; then
  echo "operator-path-leak: FAIL — scripts/core/ not found at $CORE (fail closed)"
  exit 2
fi

rc=0
python3 -I "$SKILL_DIR/scripts/qc_static_checks.py" no-operator-paths --core "$CORE" || rc=$?
case "$rc" in
  0) exit 0 ;;   # clean
  2) exit 1 ;;   # offender(s) found
  *) exit 2 ;;   # could not run: missing/unreadable files, empty tree, bad args
esac
