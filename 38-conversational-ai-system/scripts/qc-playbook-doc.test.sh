#!/usr/bin/env bash
# qc-playbook-doc.test.sh — fixture tests for qc-playbook-doc.sh.
#
# Proves the per-playbook human-facing doc gate actually fires against BOTH
# registry shapes a real install can contain:
#   (A) the canonical TABLE form (protocol §F) — with a trailing
#       "Doc (Notion/Docs/text)" column, and
#   (B) the BULLET form (- <id>: <desc>  [doc: <url-or-path>]) that
#       09-install-conversation-workflows.sh documents under "## Active workflows".
#
# Each shape is exercised with a fixture that has:
#   * a playbook WITH a recorded doc (Notion URL / Google Docs URL / .md path), and
#   * a playbook with NO recorded doc (empty / n/a / placeholder cell) — the
#     skipped-doc regression this gate exists to catch.
# Plus: an empty registry (no playbooks) must exit 2, never a blind PASS.
#
# Exit 0 = all assertions pass; 1 = a failure.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VALIDATOR="$SCRIPT_DIR/qc-playbook-doc.sh"

PASS=0
FAIL=0

ok()  { PASS=$((PASS+1)); printf '  [PASS] %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  [FAIL] %s\n' "$1"; }

# Assert the validator's --json verdict for fixture dir $1 equals $2.
assert_verdict() {
  local dir="$1" want="$2" label="$3"
  local out got
  out="$(bash "$VALIDATOR" --dir "$dir" --json 2>/dev/null)"
  got="$(printf '%s' "$out" | python3 -c "import json,sys; print(json.load(sys.stdin)['verdict'])" 2>/dev/null)"
  if [ "$got" = "$want" ]; then
    ok "$label: verdict is $want"
  else
    bad "$label: expected verdict $want, got '$got'"
    printf '%s\n' "$out" | sed 's/^/        /'
  fi
}

# Assert the validator's process exit code for fixture dir $1 equals $2.
assert_exit() {
  local dir="$1" want="$2" label="$3"
  local rc=0
  bash "$VALIDATOR" --dir "$dir" >/dev/null 2>&1 || rc=$?
  if [ "$rc" = "$want" ]; then
    ok "$label: exit code is $want"
  else
    bad "$label: expected exit $want, got $rc"
  fi
}

# Assert that fixture dir $1 FAILs AND the missing-doc problem is attributed to slug $2.
assert_missing_doc() {
  local dir="$1" slug="$2" label="$3"
  local out
  out="$(bash "$VALIDATOR" --dir "$dir" --json 2>/dev/null)"
  if printf '%s' "$out" | python3 -c "
import json,sys
d=json.load(sys.stdin)
slug='$slug'
hit=any(r['slug']==slug and any('no recorded human-facing doc' in p for p in r['problems']) for r in d['playbooks'])
sys.exit(0 if hit else 1)
"; then
    ok "$label: caught missing-doc playbook ($slug)"
  else
    bad "$label: did NOT catch missing-doc playbook ($slug)"
    printf '%s\n' "$out" | sed 's/^/        /'
  fi
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# ---------------------------------------------------------------------------
# Fixture (A): TABLE form — one playbook WITH a Notion doc, one with NO doc.
# ---------------------------------------------------------------------------
A="$TMP/table/conversation-workflows"
mkdir -p "$A"
cat > "$A/registry.md" <<'EOF'
# Conversation Workflows Registry

## Active workflows

| ID | Name | Trigger summary | Layer 1? | OpenClaw playbook | GHL prompt | Verification checklist | Doc (Notion/Docs/text) |
|---|---|---|---|---|---|---|---|
| appointment-booking | First playbook | "book","schedule" | No (uses existing inbound) | appointment-booking.md | n/a | n/a | https://www.notion.so/client/appointment-booking-abc123 |
| pricing-inquiry | Lead asks pricing | "price","cost" | No (uses existing inbound) | pricing-inquiry.md | n/a | n/a | n/a |
EOF
printf '# appointment booking playbook\n' > "$A/appointment-booking.md"
printf '# pricing playbook\n'             > "$A/pricing-inquiry.md"

assert_verdict     "$A" "FAIL" "table-form"
assert_exit        "$A" "1"    "table-form"
assert_missing_doc "$A" "pricing-inquiry" "table-form"

# ---------------------------------------------------------------------------
# Fixture (B): BULLET form — one playbook with [doc: ...], one with none.
# ---------------------------------------------------------------------------
B="$TMP/bullet/conversation-workflows"
mkdir -p "$B"
cat > "$B/registry.md" <<'EOF'
# Conversation Workflows — Registry

## How to invoke the builder

- "Help me build a conversation playbook"

## Active workflows

- appointment-booking: First playbook [doc: https://docs.google.com/document/d/xyz/edit]
- win-back: Re-engage cold leads
EOF
printf '# appointment booking playbook\n' > "$B/appointment-booking.md"
printf '# win-back playbook\n'            > "$B/win-back.md"

assert_verdict     "$B" "FAIL" "bullet-form"
assert_exit        "$B" "1"    "bullet-form"
assert_missing_doc "$B" "win-back" "bullet-form"

# ---------------------------------------------------------------------------
# Fixture (C): clean TABLE registry — every playbook has a doc → PASS (exit 0).
# ---------------------------------------------------------------------------
C="$TMP/clean/conversation-workflows"
mkdir -p "$C"
cat > "$C/registry.md" <<'EOF'
# Conversation Workflows Registry

## Active workflows

| ID | Name | Trigger summary | Layer 1? | OpenClaw playbook | GHL prompt | Verification checklist | Doc (Notion/Docs/text) |
|---|---|---|---|---|---|---|---|
| appointment-booking | First playbook | "book" | No (uses existing inbound) | appointment-booking.md | n/a | n/a | https://www.notion.so/client/appt-abc |
| pricing-inquiry | Lead asks pricing | "price" | No (uses existing inbound) | pricing-inquiry.md | n/a | n/a | /Users/<user>/master-files/conversation-workflows/pricing-inquiry-doc.md |
EOF
printf '# appt\n'    > "$C/appointment-booking.md"
printf '# pricing\n' > "$C/pricing-inquiry.md"

assert_verdict "$C" "PASS" "clean-table"
assert_exit    "$C" "0"    "clean-table"

# ---------------------------------------------------------------------------
# Fixture (D): empty registry (no playbooks) → NO_PLAYBOOKS, exit 2 (never blind PASS).
# ---------------------------------------------------------------------------
D="$TMP/empty/conversation-workflows"
mkdir -p "$D"
cat > "$D/registry.md" <<'EOF'
# Conversation Workflows — Registry

## Active workflows

| ID | Name | Trigger summary | Layer 1? | OpenClaw playbook | GHL prompt | Verification checklist | Doc (Notion/Docs/text) |
|---|---|---|---|---|---|---|---|

<!-- workflows: none yet -->
EOF

assert_verdict "$D" "NO_PLAYBOOKS" "empty-registry"
assert_exit    "$D" "2"            "empty-registry"

# ---------------------------------------------------------------------------
# Fixture (E): playbook on disk but NOT registered → FAIL (no doc can be recorded).
# ---------------------------------------------------------------------------
E="$TMP/orphan/conversation-workflows"
mkdir -p "$E"
cat > "$E/registry.md" <<'EOF'
# Conversation Workflows — Registry

## Active workflows

<!-- nothing registered -->
EOF
printf '# orphan playbook\n' > "$E/rogue-slug.md"

assert_verdict     "$E" "FAIL" "orphan-on-disk"
assert_exit        "$E" "1"    "orphan-on-disk"
assert_missing_doc "$E" "rogue-slug" "orphan-on-disk"

echo ""
echo "qc-playbook-doc tests: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
