#!/usr/bin/env bash
# qc-trinity-registry.test.sh — fixture tests for qc-trinity-registry.sh.
#
# Proves the registry-vs-disk reconciliation actually fires against BOTH registry
# shapes a real install can contain:
#   (A) the canonical TABLE form (protocol §F), and
#   (B) the BULLET form (- <id>: <desc>) that 09-install-conversation-workflows.sh
#       documents/emits under "## Active workflows".
#
# Each shape is exercised with a fixture that has:
#   * a REGISTERED-BUT-MISSING-FILES row (in the registry, no files on disk), and
#   * a FILE-PRESENT-BUT-UNREGISTERED slug (files on disk, not in the registry).
# Before the bullet-aware parser, the bullet fixture silently passed (the parser
# only read the table) — these tests lock that regression shut.
#
# Exit 0 = all assertions pass; 1 = a failure.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VALIDATOR="$SCRIPT_DIR/qc-trinity-registry.sh"

PASS=0
FAIL=0

note() { printf '  %s\n' "$1"; }
ok()   { PASS=$((PASS+1)); printf '  [PASS] %s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  [FAIL] %s\n' "$1"; }

# Assert that the validator's --json output, for fixture dir $1, FAILs and that
# its `incomplete` problems include a registered-but-no-files entry for slug $2
# AND a not-registered entry for slug $3.
assert_reconciles() {
  local dir="$1" missing_slug="$2" unreg_slug="$3" label="$4"
  local out verdict
  out="$(bash "$VALIDATOR" --dir "$dir" --json 2>/dev/null)"
  verdict="$(printf '%s' "$out" | python3 -c "import json,sys; print(json.load(sys.stdin)['verdict'])" 2>/dev/null)"

  if [ "$verdict" != "FAIL" ]; then
    bad "$label: expected verdict FAIL, got '$verdict'"
    printf '%s\n' "$out" | sed 's/^/        /'
    return
  fi
  ok "$label: verdict is FAIL"

  # registered-but-no-files for $missing_slug
  if printf '%s' "$out" | python3 -c "
import json,sys
d=json.load(sys.stdin)
slug='$missing_slug'
hit=any(r['slug']==slug and any('no files on disk' in p for p in r['problems']) for r in d['incomplete'])
sys.exit(0 if hit else 1)
"; then
    ok "$label: caught registered-but-no-files row ($missing_slug)"
  else
    bad "$label: did NOT catch registered-but-no-files row ($missing_slug)"
    printf '%s\n' "$out" | sed 's/^/        /'
  fi

  # file-present-but-unregistered for $unreg_slug
  if printf '%s' "$out" | python3 -c "
import json,sys
d=json.load(sys.stdin)
slug='$unreg_slug'
hit=any(r['slug']==slug and any('not registered' in p for p in r['problems']) for r in d['incomplete'])
sys.exit(0 if hit else 1)
"; then
    ok "$label: caught file-present-but-unregistered slug ($unreg_slug)"
  else
    bad "$label: did NOT catch file-present-but-unregistered slug ($unreg_slug)"
    printf '%s\n' "$out" | sed 's/^/        /'
  fi
}

# Assert a clean, fully-consistent registry PASSes.
assert_pass() {
  local dir="$1" label="$2"
  local out verdict
  out="$(bash "$VALIDATOR" --dir "$dir" --json 2>/dev/null)"
  verdict="$(printf '%s' "$out" | python3 -c "import json,sys; print(json.load(sys.stdin)['verdict'])" 2>/dev/null)"
  if [ "$verdict" = "PASS" ]; then
    ok "$label: clean registry verdict is PASS"
  else
    bad "$label: expected PASS, got '$verdict'"
    printf '%s\n' "$out" | sed 's/^/        /'
  fi
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# ---------------------------------------------------------------------------
# Fixture (B): BULLET form (what 09-install-conversation-workflows.sh documents)
# ---------------------------------------------------------------------------
B="$TMP/bullet/conversation-workflows"
mkdir -p "$B"
cat > "$B/registry.md" <<'EOF'
# Conversation Workflows — Registry

## How to invoke the builder

- "Help me build a conversation playbook"
- "Build me a workflow for <X>"

## Active workflows

- pricing-inquiry: New lead asks about pricing
- ghost-workflow: Registered but nobody wrote the files

<!-- the line above (ghost-workflow) has NO pricing-inquiry-style files -->
EOF
# pricing-inquiry: registered AND has both files (complete).
printf '# pricing playbook\n' > "$B/pricing-inquiry.md"
printf '# pricing prompt\n'   > "$B/pricing-inquiry--build-with-ai-prompt.md"
# ghost-workflow: registered but NO files (registered-but-no-files).
# rogue-slug: files on disk but NOT in registry (file-present-but-unregistered).
printf '# rogue playbook\n' > "$B/rogue-slug.md"
printf '# rogue prompt\n'   > "$B/rogue-slug--build-with-ai-prompt.md"

assert_reconciles "$B" "ghost-workflow" "rogue-slug" "bullet-form"

# ---------------------------------------------------------------------------
# Fixture (A): TABLE form (protocol §F canonical shape)
# ---------------------------------------------------------------------------
A="$TMP/table/conversation-workflows"
mkdir -p "$A"
cat > "$A/registry.md" <<'EOF'
# Conversation Workflows Registry

## Active workflows

| ID | Name | Trigger summary | Layer 1? | OpenClaw playbook | GHL prompt | Verification checklist |
|---|---|---|---|---|---|---|
| pricing-inquiry | New lead asks about pricing | "price","cost" | No (uses existing inbound) | pricing-inquiry.md | n/a | n/a |
| ghost-workflow | Registered, no files | new tag | Yes | ghost-workflow.md | ghost-workflow--build-with-ai-prompt.md | ghost-workflow--verification-checklist.md |
EOF
# pricing-inquiry: Layer 1 = No, so playbook-only is complete.
printf '# pricing playbook\n' > "$A/pricing-inquiry.md"
# ghost-workflow: registered but NO files.
# rogue-slug: files on disk but NOT in registry.
printf '# rogue playbook\n' > "$A/rogue-slug.md"
printf '# rogue prompt\n'   > "$A/rogue-slug--build-with-ai-prompt.md"

assert_reconciles "$A" "ghost-workflow" "rogue-slug" "table-form"

# ---------------------------------------------------------------------------
# Fixture (C): clean bullet registry — everything registered + on disk → PASS
# ---------------------------------------------------------------------------
C="$TMP/clean/conversation-workflows"
mkdir -p "$C"
cat > "$C/registry.md" <<'EOF'
# Conversation Workflows — Registry

## Active workflows

- pricing-inquiry: New lead asks about pricing
- booking: Lead wants to book a call
EOF
printf '# pb\n' > "$C/pricing-inquiry.md"
printf '# pr\n' > "$C/pricing-inquiry--build-with-ai-prompt.md"
printf '# pb\n' > "$C/booking.md"
printf '# pr\n' > "$C/booking--build-with-ai-prompt.md"

assert_pass "$C" "bullet-form-clean"

echo ""
echo "qc-trinity-registry tests: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
