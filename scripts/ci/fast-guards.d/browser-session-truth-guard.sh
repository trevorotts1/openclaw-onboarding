#!/usr/bin/env bash
# Folded from .github/workflows/browser-session-truth-guard.yml (job "Open status + detached ownership + live verification session"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Syntax-check what the suites cover
set -e -o pipefail
set -euo pipefail
bash -n 06-ghl-install-pages/tools/browser_manager.sh
bash -n tests/unit/browser-manager-open-status-and-detach-ownership.test.sh
python3 -m py_compile 06-ghl-install-pages/tools/ghl_verify.py
python3 -m py_compile 06-ghl-install-pages/tools/ghl_builder.py
python3 -m py_compile 06-ghl-install-pages/tools/browser_manager.py
python3 -m py_compile tests/unit/ghl-verify-live-browser-session.test.py
echo "syntax OK"
)
( # step: T0-16 / T0-17 — open status and detached ownership
set -e -o pipefail
bash tests/unit/browser-manager-open-status-and-detach-ownership.test.sh
)
( # step: T2-01 — live verification holds a managed browser session
set -e -o pipefail
export AGENT_BROWSER_HEADED='false'
python3 tests/unit/ghl-verify-live-browser-session.test.py
)
( # step: Assert the fixes are still the fixes, not their descriptions
set -e -o pipefail
set -euo pipefail
# A guard that only ever passes has not been observed. These are the
# exact lines the three findings named; if any of them comes back, the
# suites above must have been changed to tolerate it.
if grep -q 'open .*|| true' 06-ghl-install-pages/tools/browser_manager.sh; then
  echo "FAIL: bm_ensure discards the browser open's exit status again (T0-16)." >&2
  exit 1
fi
if ! grep -q 'the child owns lock+lease+TTL+teardown' 06-ghl-install-pages/tools/browser_manager.sh; then
  echo "FAIL: run-detached no longer states that the CHILD owns the session (T0-17)." >&2
  exit 1
fi
if ! grep -q '_live_browser_session' 06-ghl-install-pages/tools/ghl_verify.py; then
  echo "FAIL: the live verification session bracket was removed (T2-01)." >&2
  exit 1
fi
echo "PASS: all three sites still carry their fix."
)
