#!/usr/bin/env bash
# Read-only verification for the launcher core. Exit 0 pass, non-zero fail.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

echo "== open and decided seams =="
python3 -m launcher_core.cli seams

echo "== unit + integration checks =="
python3 -I -m unittest discover -s tests -p 'test_*.py' -v

echo "== route invariants and adapter wiring =="
python3 -I -m unittest discover -s "$HERE/routes/tests" -p 'test_routes.py'

echo "== worked-example fixtures =="
python3 -I "$HERE/fixtures/run_fixtures.py"

echo "== 999 dependency package =="
python3 -m launcher_core.cli dependencies
