#!/usr/bin/env bash
# Run the independent Podcast Production Engine webhook layer tests.
#
# Default system under test is the executable-specification oracle in
# spec_reference/. To run the SAME tests against the shipped mapper (the
# independent-check role), export PODCAST_WEBHOOK_SUT to an importable module that
# exposes map_payload, compute_job_key, Ledger, and intake, or drop a
# podcast_webhook_sut adapter module on PYTHONPATH. See README.md.
#
# Usage:
#   ./run-webhook-tests.sh            run with pytest (preferred)
#   ./run-webhook-tests.sh -k job_key filter to matching tests
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

if python3 -m pytest --version >/dev/null 2>&1; then
  exec python3 -m pytest -q "$@"
fi

echo "pytest not found; falling back to unittest discovery (pytest fixtures are skipped)." >&2
exec python3 -m unittest discover -s "$HERE" -p 'test_webhook_*.py' -v
