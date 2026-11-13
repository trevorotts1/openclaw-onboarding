#!/usr/bin/env bash
# Folded from .github/workflows/content-pipeline-fail-closed-guard.yml (job "T0-62/T2-36: merge inputs are probed and --dry-run exists"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Install FFmpeg (the skills declared requirement)
echo "--- step: Install FFmpeg (the skills declared requirement)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards content-pipeline-fail-closed-guard--video-editor-merge: step \"Install FFmpeg (the skills declared requirement)\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
sudo apt-get update -qq
sudo apt-get install -y -qq ffmpeg
ffprobe -version | head -n 1
)
( # step: Syntax-check
echo "--- step: Syntax-check"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards content-pipeline-fail-closed-guard--video-editor-merge: step \"Syntax-check\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
bash -n 27-video-editor/scripts/merge-broll.sh
bash -n 27-video-editor/scripts/broll-workflow.sh
bash -n 27-video-editor/test/test-merge-input-validation.sh
echo "OK: shell syntax"
)
( # step: The workflows embedded manifest writer compiles
echo "--- step: The workflows embedded manifest writer compiles"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards content-pipeline-fail-closed-guard--video-editor-merge: step \"The workflows embedded manifest writer compiles\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
# The heredoc body is Python; extract and compile it separately so a
# syntax error inside it cannot hide behind `bash -n`.
awk '/^python3 - "\$MANIFEST"/{flag=1;next} /^PYTHON_EOF$/{flag=0} flag' \
  27-video-editor/scripts/broll-workflow.sh > /tmp/manifest_writer.py
test -s /tmp/manifest_writer.py
python3 -m py_compile /tmp/manifest_writer.py
echo "OK: the manifest writer compiles"
)
( # step: Bad inputs abort with named errors; real merges still run
echo "--- step: Bad inputs abort with named errors; real merges still run"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards content-pipeline-fail-closed-guard--video-editor-merge: step \"Bad inputs abort with named errors; real merges still run\" failed (exit $fg_rc)"' EXIT
bash 27-video-editor/test/test-merge-input-validation.sh
)
( # step: The workflow stages no zero-byte placeholders
echo "--- step: The workflow stages no zero-byte placeholders"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards content-pipeline-fail-closed-guard--video-editor-merge: step \"The workflow stages no zero-byte placeholders\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
if grep -nE '^\s*touch "\$TEMP_DIR/broll_' 27-video-editor/scripts/broll-workflow.sh; then
  echo "FAIL: the workflow is creating empty files at the merge destination paths again (T0-62)"
  exit 1
fi
echo "OK: expected inputs are declared, not fabricated"
)
