#!/usr/bin/env bash
# Folded from .github/workflows/social-planner-suite-guard.yml (job "social planner contract + failure-injection suite"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Validate exported workflows with the n8n parser
set -e
npm ci --ignore-scripts --prefix tests/social-planner/fixtures/n8n-expression-parser
node tests/social-planner/fixtures/n8n-expression-parser/verify.cjs
python3 35-social-media-planner/config/n8n/sync-create-code.py --check
python3 35-social-media-planner/config/n8n/verify-exports.py
)
( # step: Install pytest (proof-file runner; tests themselves stay offline)
set -e
python3 -m pip install --quiet pytest
)
( # step: Run the social-planner suite (hermetic, offline)
set -e -o pipefail
# Full-fidelity failure evidence. The Actions default shell is
# `bash -e`: a failing python3 aborts the script BEFORE `rc1=$?` and
# the log echo ever run (seen live: zero step output + bare exit 1).
# So: set +e explicitly, capture every rc with ||-guards, and ALWAYS
# print the log before exiting. The file is the ground truth.
set -o pipefail
set +e
SUITE_LOG="$RUNNER_TEMP/social-planner-suite.log"
: >"$SUITE_LOG"
python3 -u -m unittest discover -s tests/social-planner -p 'test_*.py' -v \
  >>"$SUITE_LOG" 2>&1
rc1=$?
python3 35-social-media-planner/scripts/test_run_publishing_cycle.py \
  >>"$SUITE_LOG" 2>&1
rc2=$?
python3 -m pytest 35-social-media-planner/scripts/test_prove_content_conversation_loop.py -q \
  >>"$SUITE_LOG" 2>&1
rc3=$?
(cd 35-social-media-planner/scripts && python3 test_kie_media_plan.py && python3 test_validate_podcast_publish_payload.py) \
  >>"$SUITE_LOG" 2>&1
rc4=$?
echo "=== suite rcs: discover=$rc1 cycle-test=$rc2 pytest=$rc3 media-podcast=$rc4 ==="
cat "$SUITE_LOG"
if [ "$rc1" -ne 0 ] || [ "$rc2" -ne 0 ] || [ "$rc3" -ne 0 ] || [ "$rc4" -ne 0 ]; then
  echo "::error::social-planner suite failed (discover=$rc1 cycle=$rc2 pytest=$rc3 media-podcast=$rc4)"
  exit 1
fi
)
