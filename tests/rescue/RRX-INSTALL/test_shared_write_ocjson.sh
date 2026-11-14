#!/usr/bin/env bash
# tests/rescue/RRX-INSTALL/test_shared_write_ocjson.sh
# ─────────────────────────────────────────────────────────────────────────────
# RRX-105: the configuration writer never destroys what it could not read.
#
# `_shared_write_ocjson` in install.sh used to start from an empty object when
# openclaw.json did not parse, then write that empty object over the whole
# configuration. This test extracts the helper from install.sh by reading it
# (function start to its closing brace) and runs it against three fixtures:
#
#   1. a valid file        -> the value is set and every other key survives;
#   2. an unparseable file  -> byte-identical afterwards, a warning is printed,
#                              and the helper's exit status is non-fatal;
#   3. a value already set  -> byte-identical and the modification time is
#                              untouched (the file is not rewritten at all).
#
# Fully offline. Exit 0 = all assertions pass.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
INSTALL="$REPO_ROOT/install.sh"

PASS=0
FAIL=0
ERRORS=()

ok()   { echo "  PASS: $1"; PASS=$((PASS + 1)); }
bad()  { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); ERRORS+=("$1"); }

echo ""
echo "=== RRX-105 _shared_write_ocjson: never clobber what it could not read ==="
echo ""

if [ ! -f "$INSTALL" ]; then
    echo "  FAIL: $INSTALL not found"
    exit 1
fi

# Every temp file stays on the portable drive: TMPDIR must be set by the runner.
if [ -z "${TMPDIR:-}" ]; then
    echo "  FAIL: TMPDIR is not set; refusing to write outside the portable drive"
    exit 1
fi
WORK="$(mktemp -d "$TMPDIR/rrx-install-105.XXXXXX")" || {
    echo "  FAIL: could not create a scratch folder under TMPDIR"
    exit 1
}
trap 'rm -rf "$WORK"' EXIT

HELPER="$WORK/helper.sh"

# ── Extract the helper from install.sh ───────────────────────────────────────
# Start at the `_shared_write_ocjson() {` line. Its body holds a python heredoc
# whose braces must not be counted, so the end is the first line that is exactly
# four spaces and a closing brace AFTER the heredoc terminator.
python3 - "$INSTALL" > "$HELPER" <<'PYEXTRACT'
import sys

path = sys.argv[1]
with open(path, encoding='utf-8') as fh:
    lines = fh.read().splitlines()

start = None
for i, line in enumerate(lines):
    if '_shared_write_ocjson() {' in line:
        start = i
        break
if start is None:
    sys.stderr.write('install.sh: _shared_write_ocjson() { not found\n')
    sys.exit(1)

for j in range(start, len(lines)):
    if lines[j].strip() == 'PYEOF':
        for k in range(j + 1, len(lines)):
            if lines[k] == '    }':
                sys.stdout.write('\n'.join(lines[start:k + 1]) + '\n')
                sys.exit(0)
        break

sys.stderr.write('install.sh: closing brace of _shared_write_ocjson not found\n')
sys.exit(1)
PYEXTRACT

if [ ! -s "$HELPER" ]; then
    echo "  FAIL: could not extract _shared_write_ocjson from install.sh"
    exit 1
fi
ok "extracted _shared_write_ocjson from install.sh"

# Run the helper in an isolated subshell with stubbed warn/success.
# $1 = json path, $2 = variable name, $3 = value, $4 = file to collect warnings.
run_helper() {
    (
        set +e
        # Hoist $4: inside warn(), $4 would mean warn's own 4th arg (unbound
        # under set -u), so the redirect failed and warn returned non-zero.
        _warnfile="$4"
        OC_JSON="$1"
        warn() { printf '%s\n' "$*" >> "$_warnfile"; return 0; }
        success() { return 0; }
        export OC_JSON
        # shellcheck disable=SC1090
        . "$HELPER"
        _shared_write_ocjson "$2" "$3"
    )
}

json_field() {  # $1 = json path; reads env.vars.<field> given as $2
    python3 - "$1" "$2" <<'PYFIELD'
import json, sys
with open(sys.argv[1], encoding='utf-8') as fh:
    data = json.load(fh)
value = data.get('env', {}).get('vars', {}).get(sys.argv[2], '<missing>')
sys.stdout.write('' if value == '<missing>' else str(value))
PYFIELD
}

file_mtime() {  # BSD stat first, then GNU stat
    stat -f %m "$1" 2>/dev/null || stat -c %Y "$1" 2>/dev/null
}

# ── Case 1: a valid file keeps every other key ───────────────────────────────
cat > "$WORK/valid.json" <<'JSON'
{
  "env": {
    "vars": {
      "KEEP_ME": "untouched"
    }
  },
  "gateway": {
    "port": 4000
  }
}
JSON

if run_helper "$WORK/valid.json" "NEW_KEY" "new-value" "$WORK/valid.warn"; then
    ok "1: helper exits 0 on a valid file"
else
    bad "1: helper exited non-zero on a valid file"
fi

[ "$(json_field "$WORK/valid.json" NEW_KEY)" = "new-value" ] \
    && ok "1: the requested value was set" \
    || bad "1: the requested value was NOT set"

[ "$(json_field "$WORK/valid.json" KEEP_ME)" = "untouched" ] \
    && ok "1: the sibling env.vars key survived" \
    || bad "1: the sibling env.vars key was lost"

if python3 - "$WORK/valid.json" <<'PYGATEWAY'
import json, sys
with open(sys.argv[1], encoding='utf-8') as fh:
    data = json.load(fh)
sys.exit(0 if data.get('gateway', {}).get('port') == 4000 else 1)
PYGATEWAY
then
    ok "1: unrelated top-level keys and their values are still present"
else
    bad "1: unrelated top-level keys were lost or changed"
fi

# ── Case 2: an unparseable file is left alone ───────────────────────────────
printf '{ // comment\n' > "$WORK/broken.json"
cp "$WORK/broken.json" "$WORK/broken.before"
: > "$WORK/broken.warn"

run_helper "$WORK/broken.json" "NEW_KEY" "new-value" "$WORK/broken.warn"
broken_rc=$?

if [ "$broken_rc" -eq 0 ]; then
    ok "2: the helper's exit status is non-fatal on an unparseable file"
else
    bad "2: the helper returned $broken_rc on an unparseable file (expected non-fatal)"
fi

if cmp -s "$WORK/broken.json" "$WORK/broken.before"; then
    ok "2: the unparseable file is byte-identical afterwards"
else
    bad "2: the unparseable file was MODIFIED"
fi

if [ -s "$WORK/broken.warn" ]; then
    ok "2: a warning was printed"
else
    bad "2: no warning was printed for the unparseable file"
fi

# ── Case 3: an already-set value is a true no-op ────────────────────────────
cat > "$WORK/same.json" <<'JSON'
{
  "env": {
    "vars": {
      "ALREADY": "set"
    }
  }
}
JSON
touch -t 200001010000 "$WORK/same.json"
cp -p "$WORK/same.json" "$WORK/same.before"
mtime_before="$(file_mtime "$WORK/same.json")"
: > "$WORK/same.warn"

run_helper "$WORK/same.json" "ALREADY" "set" "$WORK/same.warn"
same_rc=$?

if [ "$same_rc" -eq 0 ]; then
    ok "3: the helper exits 0 when the value is already set"
else
    bad "3: the helper returned $same_rc when the value was already set"
fi

if cmp -s "$WORK/same.json" "$WORK/same.before"; then
    ok "3: the already-set file is byte-identical afterwards"
else
    bad "3: the already-set file was rewritten"
fi

mtime_after="$(file_mtime "$WORK/same.json")"
if [ -n "$mtime_before" ] && [ "$mtime_before" = "$mtime_after" ]; then
    ok "3: the modification time is unchanged (the file was not rewritten)"
else
    bad "3: the modification time changed ($mtime_before -> $mtime_after)"
fi

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
    echo ""
    echo "Failures:"
    for e in "${ERRORS[@]}"; do echo "  - $e"; done
    exit 1
fi
echo "PASS: all assertions passed"
exit 0
