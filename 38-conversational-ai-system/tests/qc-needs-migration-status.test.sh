#!/usr/bin/env bash
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
CHECKLIST="$ROOT/scripts/11-run-qc-checklist.sh"
GATE="$ROOT/scripts/qc-tool-gating.sh"
LEGACY_DIR="$ROOT/tools/tests/fixtures/legacy"
TEMPLATE="$ROOT/templates/appointment-booking-playbook-template.md"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/qc38-status-test.XXXXXX")" || exit 1
trap 'rm -rf "$TMP"' EXIT

FAILS=0
ok() { echo "ok   $1"; }
fail() { echo "FAIL $1"; FAILS=$((FAILS + 1)); }

command -v python3 >/dev/null 2>&1 || { echo "FAIL python3 unavailable"; exit 1; }
[ -f "$GATE" ] || { echo "FAIL qc-tool-gating.sh missing"; exit 1; }
[ -f "$CHECKLIST" ] || { echo "FAIL checklist missing"; exit 1; }

# a) Legacy playbook produces machine-readable migration status.
RC=0
bash "$GATE" --dir "$LEGACY_DIR" --status-file "$TMP/legacy.json" >/dev/null 2>&1 || RC=$?
if [ "$RC" -eq 0 ] && python3 -I - "$TMP/legacy.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    d = json.load(f)
assert d["verdict"] == "NEEDS-MIGRATION"
assert d["legacy_needs_migration"] == 1
assert "video-edit-door.md" in d["legacy_files"]
assert d["new_style_failures"] == 0
assert set(d) == {"gate","legacy_needs_migration","new_style_failures","verdict","legacy_files","workflows_dir"}
PY
then
  ok "legacy status contract"
else
  fail "legacy status contract (rc=$RC)"
fi

# b) A current template must pass without migration.
mkdir "$TMP/current" || exit 1
if [ -f "$TEMPLATE" ]; then
  cp "$TEMPLATE" "$TMP/current/appointment-booking-playbook-template.md"
  RC=0
  bash "$GATE" --dir "$TMP/current" --status-file "$TMP/current.json" >/dev/null 2>&1 || RC=$?
  if [ "$RC" -eq 0 ] && python3 -I - "$TMP/current.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    d = json.load(f)
assert d["verdict"] == "PASS"
assert d["legacy_needs_migration"] == 0
assert d["new_style_failures"] == 0
PY
  then
    ok "current playbook status contract"
  else
    fail "current playbook status contract (rc=$RC)"
  fi
else
  fail "appointment booking template missing"
fi

# c) Extract and exercise the shipped status reader.
sed -n '/^# >>> QC_READ_STATUS$/,/^# <<< QC_READ_STATUS$/p' "$CHECKLIST" |
  sed '1d;$d' > "$TMP/read-status.sh"
if [ -s "$TMP/read-status.sh" ]; then
  (
    eval "$(cat "$TMP/read-status.sh")"
    qc_read_status "$TMP/absent.json"
  ) >/dev/null 2>&1
  RC=$?
  if [ "$RC" -eq 1 ]; then
    ok "missing status rejected"
  else
    fail "missing status rejected (rc=$RC)"
  fi
else
  fail "status reader markers missing"
fi

# d) Unwritable status destination must not change the gate exit code.
RC=0
bash "$GATE" --dir "$LEGACY_DIR" --status-file "$TMP/missing-dir/status.json" >/dev/null 2>&1 || RC=$?
if [ "$RC" -eq 0 ]; then
  ok "unwritable status destination preserves gate exit code"
else
  fail "unwritable status destination (expected rc=0, got $RC)"
fi

# e) Exercise the exact completion gate shipped in the checklist.
sed -n '/^# >>> QC_COMPLETION_GATE$/,/^# <<< QC_COMPLETION_GATE$/p' "$CHECKLIST" |
  sed '1d;$d' > "$TMP/completion-gate.sh"
if [ -s "$TMP/completion-gate.sh" ]; then
  (
    eval "$(cat "$TMP/completion-gate.sh")"

    expect_gate() {
      local fail_count="$1" legacy_count="$2" expected="$3" expected_rc="$4"
      local actual actual_rc=0
      actual="$(qc_completion_gate "$fail_count" "$legacy_count")" || actual_rc=$?
      if [ "$actual" != "$expected" ] || [ "$actual_rc" -ne "$expected_rc" ]; then
        echo "FAIL completion ($fail_count,$legacy_count): got $actual/$actual_rc; expected $expected/$expected_rc"
        return 1
      fi
      echo "ok   completion ($fail_count,$legacy_count) -> $actual/$actual_rc"
    }

    expect_gate 0 0 PASS 0 || exit 1
    expect_gate 0 2 NEEDS-MIGRATION 3 || exit 1
    expect_gate 4 0 FAIL 1 || exit 1
  )
  RC=$?
  [ "$RC" -eq 0 ] || FAILS=$((FAILS + 1))
else
  fail "completion gate markers missing"
fi

if [ "$FAILS" -ne 0 ]; then
  echo "qc-needs-migration-status.test.sh: $FAILS failure(s)"
  exit 1
fi

echo "qc-needs-migration-status.test.sh: all cases passed"
exit 0
