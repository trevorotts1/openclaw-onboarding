#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENGINE="$SKILL_ROOT/tools/playbook_engine.py"
TEMPLATE="$SKILL_ROOT/templates/appointment-booking-playbook-template.md"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/skill38-playbook-gate.XXXXXX")" || exit 1
trap 'rm -rf "$TMP_DIR"' EXIT HUP INT TERM

PASS_COUNT=0
FAIL_COUNT=0

assert_result() {
  name="$1"
  passed="$2"
  if [ "$passed" -eq 1 ]; then
    printf '[PASS] %s\n' "$name"
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    printf '[FAIL] %s\n' "$name"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
}

run_capture() {
  CAPTURE_OUT="$TMP_DIR/capture.out"
  "$@" >"$CAPTURE_OUT" 2>&1
  CAPTURE_RC=$?
  return 0
}

mkdir -p "$TMP_DIR/positive" "$TMP_DIR/negative" "$TMP_DIR/vacuous"

# 1. Shipped template validates.
run_capture python3 -I "$ENGINE" validate "$TEMPLATE"
assert_result "template validates" "$([ "$CAPTURE_RC" -eq 0 ] && echo 1 || echo 0)"

# 2. Shipped template lints clean.
run_capture python3 -I "$ENGINE" lint "$TEMPLATE"
assert_result "template lints clean" "$([ "$CAPTURE_RC" -eq 0 ] && echo 1 || echo 0)"

# 3. Content-identical zero-phase files are legacy by rule and are surfaced
# as NEEDS-MIGRATION, never PASS. Craft gate independently rejects vacuous content.
VACUOUS_DIR="$TMP_DIR/vacuous"
cat >"$VACUOUS_DIR/zero-phase.md" <<'PLAYBOOK'
# Conversation Playbook: X

## When to invoke

## Behavior (Layer 2)

## Guardrails
PLAYBOOK
cat >"$VACUOUS_DIR/registry.md" <<'REGISTRY'
# Registry

| ID | Name |
|---|---|
| zero-phase | Zero phase |
REGISTRY

export AGENTS_MD=/nonexistent
VACUOUS_OK=1
for GATE in \
  "$SKILL_ROOT/scripts/qc-tool-gating.sh" \
  "$SKILL_ROOT/scripts/qc-workflow-exits.sh" \
  "$SKILL_ROOT/scripts/qc-playbook-declares.sh" \
  "$SKILL_ROOT/scripts/qc-playbook-doc.sh"
do
  if [ ! -f "$GATE" ]; then
    VACUOUS_OK=0
    continue
  fi
  run_capture bash "$GATE" --dir "$VACUOUS_DIR"
  if [ "$CAPTURE_RC" -ne 0 ] || ! grep -q "NEEDS-MIGRATION" "$CAPTURE_OUT" || grep -q "RESULT: PASS" "$CAPTURE_OUT"; then
    VACUOUS_OK=0
  fi
done

CRAFT_GATE="$SKILL_ROOT/scripts/qc-playbook-craft.sh"
if [ ! -f "$CRAFT_GATE" ]; then
  VACUOUS_OK=0
else
  run_capture bash "$CRAFT_GATE" --dir "$VACUOUS_DIR"
  if [ "$CAPTURE_RC" -eq 0 ]; then
    VACUOUS_OK=0
  fi
fi
assert_result "vacuous gate regression" "$VACUOUS_OK"

# 4. Duplicate phase numbers must be rejected.
DUPLICATE="$TMP_DIR/duplicate-phase.md"
cp "$TEMPLATE" "$DUPLICATE" || true
python3 - "$DUPLICATE" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
match = re.search(r"(?m)^### Phase 1 - .+$", text)
if match:
    text = text[:match.start()] + "### Phase 2 - duplicated" + text[match.end():]
else:
    match = re.search(r"(?m)^### Phase 1\b.*$", text)
    if match:
        text = text[:match.start()] + "### Phase 2 - duplicated" + text[match.end():]
path.write_text(text, encoding="utf-8")
PY
run_capture python3 -I "$ENGINE" validate "$DUPLICATE"
DUPLICATE_OK=0
if [ "$CAPTURE_RC" -eq 1 ] && grep -qi "duplicate phase numbers" "$CAPTURE_OUT"; then
  DUPLICATE_OK=1
fi
assert_result "duplicate phase rejected" "$DUPLICATE_OK"

# 5. Escalation content must affect the playbook hash.
HASH_A="$TMP_DIR/hash-a.md"
HASH_B="$TMP_DIR/hash-b.md"
cp "$TEMPLATE" "$HASH_A" || true
cp "$TEMPLATE" "$HASH_B" || true
python3 - "$HASH_B" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
heading = "## On escalation"
if heading not in text:
    text += "\n\n## On escalation\n\nEscalate to operator for manual review.\n"
else:
    start = text.index(heading) + len(heading)
    text = text[:start] + "\n\nEscalate to operator for manual review." + text[start:]
path.write_text(text, encoding="utf-8")
PY
run_capture python3 -I "$ENGINE" hash "$HASH_A"
HASH_A_RC="$CAPTURE_RC"
HASH_A_OUT="$(cat "$CAPTURE_OUT")"
run_capture python3 -I "$ENGINE" hash "$HASH_B"
HASH_B_RC="$CAPTURE_RC"
HASH_B_OUT="$(cat "$CAPTURE_OUT")"
HASH_OK=0
if [ "$HASH_A_RC" -eq 0 ] && [ "$HASH_B_RC" -eq 0 ] && [ "$HASH_A_OUT" != "$HASH_B_OUT" ]; then
  HASH_OK=1
fi
assert_result "hash sees escalation" "$HASH_OK"

# 6. Craft gate accepts shipped template and rejects removed craft sections.
CRAFT_POS="$TMP_DIR/positive"
CRAFT_NEG="$TMP_DIR/negative"
cp "$TEMPLATE" "$CRAFT_POS/appointment-booking.md" || true
cp "$TEMPLATE" "$CRAFT_NEG/appointment-booking.md" || true
cat >"$CRAFT_POS/registry.md" <<'REGISTRY'
# Registry

| ID | Name |
|---|---|
| appointment-booking | Appointment Booking |
REGISTRY
cp "$CRAFT_POS/registry.md" "$CRAFT_NEG/registry.md" || true
python3 - "$CRAFT_NEG/appointment-booking.md" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
for heading in ("Objection library", "Golden transcript"):
    pattern = re.compile(
        r"(?ms)^#{2,4}\s+.*" + re.escape(heading) + r".*$"
        r".*?(?=^#{2,4}\s|\Z)"
    )
    text = pattern.sub("", text)
path.write_text(text, encoding="utf-8")
PY
CRAFT_GATE="$SKILL_ROOT/scripts/qc-playbook-craft.sh"
run_capture bash "$CRAFT_GATE" --dir "$CRAFT_POS"
CRAFT_POS_OK=0
[ "$CAPTURE_RC" -eq 0 ] && CRAFT_POS_OK=1
run_capture bash "$CRAFT_GATE" --dir "$CRAFT_NEG"
CRAFT_NEG_OK=0
[ "$CAPTURE_RC" -eq 1 ] && CRAFT_NEG_OK=1
CRAFT_OK=0
if [ "$CRAFT_POS_OK" -eq 1 ] && [ "$CRAFT_NEG_OK" -eq 1 ]; then
  CRAFT_OK=1
fi
assert_result "craft gate positive and negative" "$CRAFT_OK"

# 7. New-style playbook without declares must fail and name the missing block.
NO_DECL="$TMP_DIR/no-declares"
mkdir -p "$NO_DECL"
cp "$TEMPLATE" "$NO_DECL/appointment-booking.md" || true
cat >"$NO_DECL/registry.md" <<'REGISTRY'
# Registry

| ID | Name |
|---|---|
| appointment-booking | Appointment Booking |
REGISTRY
python3 - "$NO_DECL/appointment-booking.md" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
text = re.sub(
    r"(?ms)^declares\s*\n.*?(?=^## When to invoke this workflow\s*$)",
    "",
    text,
    count=1,
)
path.write_text(text, encoding="utf-8")
PY
run_capture bash "$SKILL_ROOT/scripts/qc-playbook-declares.sh" --dir "$NO_DECL"
NO_DECL_OK=0
if [ "$CAPTURE_RC" -eq 1 ] && grep -qi "no declares block" "$CAPTURE_OUT"; then
  NO_DECL_OK=1
fi
assert_result "declares tags-used required" "$NO_DECL_OK"

if [ "$FAIL_COUNT" -eq 0 ]; then
  printf 'RESULT: PASS\n'
  exit 0
fi

printf 'RESULT: FAIL - %s assertion(s)\n' "$FAIL_COUNT"
exit 1
