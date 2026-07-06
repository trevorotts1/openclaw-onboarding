#!/usr/bin/env bash
# Run the Podcast Production Engine delivery-and-queue slice tests (W1.26 to W1.28):
# delivery_report.py, credit_queue.py, personal_spreadsheet.py.
#
# Usage:
#   ./run-delivery-queue-tests.sh            run with pytest (preferred)
#   ./run-delivery-queue-tests.sh -k queue   filter to matching tests
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

if python3 -m pytest --version >/dev/null 2>&1; then
  exec python3 -m pytest -q "$@"
fi

echo "pytest not found; falling back to unittest discovery." >&2
exec python3 -m unittest discover -s "$HERE" -p 'test_*.py' -v
