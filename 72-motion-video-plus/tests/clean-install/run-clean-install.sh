#!/usr/bin/env bash
# MG-043 clean-install test for Skill 72 Motion Graphics V2 (T03).
#
# Proves a fresh install works from tracked files alone:
#   1. Materialize a pristine copy of the skill and the shared render
#      runtime with `git archive HEAD` (no node_modules, no dist, no
#      .runtime, no untracked state of any kind).
#   2. npm ci the runtime package inside the copy.
#   3. Provision the shared runtime inside the copy. The provisioner
#      runs its real launch-and-render probe for both engines and only
#      promotes the install when the probe passes, so a green run is
#      engine evidence, not a file-presence check.
#   4. Smoke: build the runtime package and run the corpus and chart
#      suites against the fresh tree.
#
# The result is recorded as JSON at
# 72-motion-video-plus/tests/evidence/mg043/clean-install.json in the
# REAL tree (the copy is scratch). Exit 0 only when every stage passes;
# the failing stage and its log are named on failure.
#
# Environment: MOTION_RUNTIME_SKIP_APT is honored by the provisioner.
# On this sandbox the apt system-library step is skipped (the libraries
# are already present), and that is recorded in the result; on a bare
# machine, run without the skip so apt installs them. Scratch lives in
# this script's work/ directory (gitignored), never on /tmp.

set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPO_ROOT="$(cd "$SKILL_ROOT/.." && pwd)"
WORK_DIR="$SCRIPT_DIR/work"
TREE="$WORK_DIR/tree"
EVIDENCE_DIR="$SKILL_ROOT/tests/evidence/mg043"
RESULT="$EVIDENCE_DIR/clean-install.json"
STARTED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
START_S="$(date +%s)"

stage="materialize"
fail_detail=""

run_stage() {
  stage="$1"
  local log="$WORK_DIR/$1.log"
  shift
  echo "=== clean-install: $stage ==="
  if "$@" > "$log" 2>&1; then
    echo "PASS $stage"
    return 0
  fi
  echo "FAIL $stage (see $log)" >&2
  tail -20 "$log" >&2
  fail_detail="$stage failed; log $log"
  return 1
}

rm -rf "$WORK_DIR"
mkdir -p "$TREE" "$EVIDENCE_DIR"

ok=1
if [ "$ok" -eq 1 ]; then
  run_stage "materialize" bash -c "cd \"$REPO_ROOT\" && git archive HEAD 72-motion-video-plus shared-utils/motion-render-runtime | tar -x -C \"$TREE\"" || ok=0
fi
if [ "$ok" -eq 1 ]; then
  run_stage "npm-ci" bash -c "cd \"$TREE/72-motion-video-plus/runtime\" && npm ci" || ok=0
fi
if [ "$ok" -eq 1 ]; then
  run_stage "provision" bash -c "cd \"$TREE\" && MOTION_RUNTIME_SKIP_APT=\"${MOTION_RUNTIME_SKIP_APT:-1}\" bash shared-utils/motion-render-runtime/provision.sh" || ok=0
fi
if [ "$ok" -eq 1 ]; then
  run_stage "smoke" bash -c "cd \"$TREE/72-motion-video-plus/runtime\" && npm run build && node dist/tests/run-corpus.js && node dist/tests/run-charts.js" || ok=0
fi

LOCK_ID="unknown"
if [ -L "$TREE/shared-utils/motion-render-runtime/.runtime/current" ]; then
  # The lock identity is the current symlink's target name, the same
  # identity the adapter probes report (e.g. lock-314fc289b233ca9e).
  LOCK_ID="$(basename "$(readlink "$TREE/shared-utils/motion-render-runtime/.runtime/current")")"
fi
END_S="$(date +%s)"
python3 - "$RESULT" <<PY
import json, platform, subprocess, sys
result = {
    "test": "T03 clean-install (MG-043)",
    "status": "pass" if $ok else "fail",
    "failed_stage": None if $ok else "$stage",
    "detail": "$fail_detail",
    "started_at": "$STARTED",
    "duration_seconds": $END_S - $START_S,
    "materialization": "git archive HEAD (tracked files only)",
    "provision_skip_apt": "${MOTION_RUNTIME_SKIP_APT:-1}" == "1",
    "apt_step": "skipped via MOTION_RUNTIME_SKIP_APT; UNVERIFIED on this box" if "${MOTION_RUNTIME_SKIP_APT:-1}" == "1" else "ran",
    "runtime_lock": "$LOCK_ID",
    "node": subprocess.run(["node", "--version"], capture_output=True, text=True).stdout.strip(),
    "platform": platform.platform(),
    "smoke": "npm run build + run-corpus + run-charts against the fresh tree",
}
with open(sys.argv[1], "w") as fh:
    json.dump(result, fh, indent=2)
    fh.write("\n")
print(json.dumps(result, indent=2))
PY

if [ "$ok" -eq 1 ]; then
  echo "CLEAN-INSTALL PASS"
  exit 0
fi
echo "CLEAN-INSTALL FAIL" >&2
exit 1
