#!/usr/bin/env bash
# Negative self-test for qc-assert-no-full-env-dump.py
# Plants two fixtures — a bare shell `pm2 jlist` and a Python list-form
# `subprocess.run(["pm2","jlist"],...)` — and asserts the guard reports
# both with --enforce, exiting 1.
#
# This is the "blind spot is closed" proof: the text-based regex cannot see
# the Python list form, but the guard's syntax-tree walk must, and this
# fixture proves it for both the shell form AND the list form.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
GUARD="$(cd "$SCRIPT_DIR/.." && pwd)/qc-assert-no-full-env-dump.py"

if [ ! -f "$GUARD" ]; then
  echo "FAIL: guard script not found at $GUARD"
  exit 2
fi

TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

cd "$TMPDIR"
git init --quiet
git config user.email "test@example.com"
git config user.name "Test"

# ── Fixture 1: bare shell pm2 jlist ────────────────────────────────────
cat > BAD_SHELL.sh <<'EOF'
#!/bin/bash
echo "doing stuff"
pm2 jlist 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin))"
echo "done"
EOF

# ── Fixture 2: Python list-form subprocess.run(["pm2","jlist"]) ────────
cat > BAD_LIST.py <<'EOF'
import subprocess, json
out = subprocess.run(["pm2", "jlist"], capture_output=True, text=True)
recs = json.loads(out.stdout)
for r in recs:
    print(r.get("pm2_env", {}).get("status"))
EOF

# ── Fixture 3: a safe .md file that should NOT be reported ─────────────
mkdir -p docs
cat > docs/README.md <<'EOF'
# Guide
Use `pm2 jlist` carefully — it dumps process environments.
Always filter through filter_pm2_record() before printing.
EOF

# ── Road a safe JSON note that should NOT be reported ─────────────
cat > config.json <<'EOF'
{"note": "pm2 jlist must always be filtered before logging"}
EOF

git add -A
git commit --quiet -m "test fixtures"

# Run guard with --enforce on the test repo; must exit 1
RC=0
python3 "$GUARD" "$TMPDIR" --enforce 2>&1 || RC=$?
EXPECTED=1
if [ "$RC" -ne "$EXPECTED" ]; then
  echo "FAIL: guard with --enforce on planted fixtures exited $RC, expected $EXPECTED"
  exit 1
fi

# Re-run to capture output for assertion
OUTPUT="$(python3 "$GUARD" "$TMPDIR" --enforce 2>&1)" || true

SHELL_REPORTED=0
LIST_REPORTED=0
MD_REPORTED=0
JSON_REPORTED=0

if echo "$OUTPUT" | grep -qF 'BAD_SHELL.sh'; then
  SHELL_REPORTED=1
fi
if echo "$OUTPUT" | grep -qF 'BAD_LIST.py'; then
  LIST_REPORTED=1
fi
if echo "$OUTPUT" | grep -qF 'README.md'; then
  MD_REPORTED=1
fi
if echo "$OUTPUT" | grep -qF 'config.json'; then
  JSON_REPORTED=1
fi

ERR=0
if [ "$SHELL_REPORTED" -eq 0 ]; then
  echo "FAIL: shell fixture BAD_SHELL.sh was NOT reported"
  ERR=1
fi
if [ "$LIST_REPORTED" -eq 0 ]; then
  echo "FAIL: Python list-form fixture BAD_LIST.py was NOT reported"
  ERR=1
fi
if [ "$MD_REPORTED" -eq 1 ]; then
  echo "FAIL: .md prose fixture README.md was incorrectly reported as a violation"
  ERR=1
fi
if [ "$JSON_REPORTED" -eq 1 ]; then
  echo "FAIL: JSON note fixture config.json was incorrectly reported as a violation"
  ERR=1
fi

if [ "$ERR" -eq 0 ]; then
  echo "PASS: both fixtures reported (shell + Python list-form) and safe fixtures excluded and the guard exited 1"
fi

exit $ERR
