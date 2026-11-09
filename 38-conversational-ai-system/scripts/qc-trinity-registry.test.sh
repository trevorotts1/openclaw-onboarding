#!/usr/bin/env bash
# qc-trinity-registry.test.sh - fixture tests for qc-trinity-registry.sh.
#
# Proves registry-vs-disk reconciliation against BOTH registry shapes:
#   (A) canonical TABLE form, and
#   (B) BULLET form emitted under "## Active workflows".
#
# Also tests four-leg validation, empty registries, stale/missing build
# contracts, slug filtering, and legacy prompt warnings.
#
# Exit 0 = all assertions pass; 1 = a failure.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VALIDATOR="$SCRIPT_DIR/qc-trinity-registry.sh"
ENGINE="$SKILL_ROOT/tools/playbook_engine.py"

PASS=0
FAIL=0

note() { printf '  %s\n' "$1"; }
ok()   { PASS=$((PASS+1)); printf '  [PASS] %s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  [FAIL] %s\n' "$1"; }

if [ ! -f "$ENGINE" ]; then
  printf '[FAIL] Canonical playbook engine unavailable: %s\n' "$ENGINE" >&2
  exit 1
fi

# Generate contract beside playbook using canonical engine.
# A playbook handed to `playbook_engine build-contract` has to declare its own
# dependencies: the writer refuses to emit a contract whose acceptance.must_pass
# would be empty, because such a contract validates nothing. A bare `# title`
# fixture therefore cannot produce a contract at all, and the four-leg check it
# was meant to exercise never ran.
declared_playbook() {
  local title="$1" path="$2"
  cat > "$path" <<DECLARED_EOF
# $title

declares
tools-used: update_tags
exits-used: talk-to-human
pipeline: sales-pipeline
stage-map: qualified: STAGE_QUALIFIED

## Phase 1 - Opening
Say hello.

## Exit rules

exit-when-tag: talk-to-human, action: handoff
DECLARED_EOF
}

write_contract() {
  local playbook="$1"
  if ! python3 "$ENGINE" build-contract "$playbook" >/dev/null; then
    printf '[FAIL] Could not generate build contract for %s\n' "$playbook" >&2
    exit 1
  fi
  local contract="${playbook%.md}--build-contract.json"
  if [ ! -f "$contract" ]; then
    printf '[FAIL] Engine did not create expected contract: %s\n' "$contract" >&2
    exit 1
  fi
}

# Assert registry-vs-disk reconciliation for fixture dir $1.
assert_reconciles() {
  local dir="$1" missing_slug="$2" unreg_slug="$3" label="$4"
  local out verdict

  out="$(bash "$VALIDATOR" --dir "$dir" --json 2>&1)"
  verdict="$(printf '%s' "$out" | python3 -c "import json,sys; print(json.load(sys.stdin)['verdict'])" 2>/dev/null)"

  if [ "$verdict" != "FAIL" ]; then
    bad "$label: expected verdict FAIL, got '$verdict'"
    printf '%s\n' "$out" | sed 's/^/        /'
    return
  fi
  ok "$label: verdict is FAIL"

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

assert_pass() {
  local dir="$1" label="$2"
  local out verdict

  out="$(bash "$VALIDATOR" --dir "$dir" --json 2>&1)"
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

# Fixture B: bullet registry with registered missing files and orphan files.
B="$TMP/bullet/conversation-workflows"
mkdir -p "$B"
cat > "$B/registry.md" <<'EOF'
# Conversation Workflows - Registry

## How to invoke the builder

- "Help me build a conversation playbook"
- "Build me a workflow for <X>"

## Active workflows

- pricing-inquiry: New lead asks about pricing
- ghost-workflow: Registered but nobody wrote the files

<!-- ghost-workflow has no pricing-inquiry-style files -->
EOF

declared_playbook "Pricing inquiry" "$B/pricing-inquiry.md"
printf '# pricing prompt\n' > "$B/pricing-inquiry--build-with-ai-prompt.md"
write_contract "$B/pricing-inquiry.md"

printf '# rogue playbook\n' > "$B/rogue-slug.md"
printf '# rogue prompt\n' > "$B/rogue-slug--build-with-ai-prompt.md"

assert_reconciles "$B" "ghost-workflow" "rogue-slug" "bullet-form"

# Fixture A: table registry, Layer 1 No exempts prompt only.
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

declared_playbook "Pricing inquiry" "$A/pricing-inquiry.md"
write_contract "$A/pricing-inquiry.md"

printf '# rogue playbook\n' > "$A/rogue-slug.md"
printf '# rogue prompt\n' > "$A/rogue-slug--build-with-ai-prompt.md"

assert_reconciles "$A" "ghost-workflow" "rogue-slug" "table-form"

# Fixture C: clean bullet registry, all workflows complete.
C="$TMP/clean/conversation-workflows"
mkdir -p "$C"
cat > "$C/registry.md" <<'EOF'
# Conversation Workflows - Registry

## Active workflows

- pricing-inquiry: New lead asks about pricing
- booking: Lead wants to book a call
EOF

declared_playbook "Pricing inquiry" "$C/pricing-inquiry.md"
printf '# pricing prompt\n' > "$C/pricing-inquiry--build-with-ai-prompt.md"
write_contract "$C/pricing-inquiry.md"

declared_playbook "Booking" "$C/booking.md"
printf '# booking prompt\n' > "$C/booking--build-with-ai-prompt.md"
write_contract "$C/booking.md"

assert_pass "$C" "bullet-form-clean"

# SLUG_OK: registered slug with valid four-leg fixture passes filtered check.
if out="$(bash "$VALIDATOR" --dir "$C" --slug pricing-inquiry 2>&1)"; then
  ok "SLUG_OK: --slug pricing-inquiry exits 0"
else
  status=$?
  bad "SLUG_OK: expected exit 0, got $status"
  printf '%s\n' "$out" | sed 's/^/        /'
fi

# EMPTY: existing folder with no registry and no files must fail with exit 3.
EMPTY="$TMP/empty/conversation-workflows"
mkdir -p "$EMPTY"

out="$(bash "$VALIDATOR" --dir "$EMPTY" 2>&1)"
status=$?
if [ "$status" -eq 3 ] && printf '%s' "$out" | grep -q 'zero registered playbooks'; then
  ok "EMPTY: empty folder exits 3 with zero registered playbooks message"
else
  bad "EMPTY: expected exit 3 and zero registered playbooks message, got $status"
  printf '%s\n' "$out" | sed 's/^/        /'
fi

# JSON mode must preserve expected exit 3 while reporting EMPTY_REGISTRY.
out="$(bash "$VALIDATOR" --dir "$EMPTY" --json 2>&1)"
status=$?
verdict="$(printf '%s' "$out" | python3 -c "import json,sys; print(json.load(sys.stdin)['verdict'])" 2>/dev/null)"
if [ "$status" -eq 3 ] && [ "$verdict" = "EMPTY_REGISTRY" ]; then
  ok "EMPTY JSON: exit 3 with verdict EMPTY_REGISTRY"
else
  bad "EMPTY JSON: expected exit 3 and EMPTY_REGISTRY, got exit $status and verdict '$verdict'"
  printf '%s\n' "$out" | sed 's/^/        /'
fi

# STALE: change playbook structure after generating the contract.
STALE="$TMP/stale/conversation-workflows"
mkdir -p "$STALE"
cp "$C/registry.md" "$STALE/registry.md"
cp "$C/pricing-inquiry--build-with-ai-prompt.md" "$STALE/pricing-inquiry--build-with-ai-prompt.md"
cp "$C/pricing-inquiry--build-contract.json" "$STALE/pricing-inquiry--build-contract.json"
cat > "$STALE/pricing-inquiry.md" <<'EOF'
# pricing playbook
model-tier: reasoning-max
EOF

if out="$(bash "$VALIDATOR" --dir "$STALE" --slug pricing-inquiry 2>&1)"; then
  bad "STALE: expected exit 1"
  printf '%s\n' "$out" | sed 's/^/        /'
else
  status=$?
  if [ "$status" -eq 1 ] && printf '%s' "$out" | grep -q 'build contract is stale'; then
    ok "STALE: changed playbook invalidates contract"
  else
    bad "STALE: expected exit 1 and stale-contract message, got $status"
    printf '%s\n' "$out" | sed 's/^/        /'
  fi
fi

# NO_CONTRACT: remove contract from otherwise complete fixture.
NO_CONTRACT="$TMP/no-contract/conversation-workflows"
mkdir -p "$NO_CONTRACT"
cp "$C/registry.md" "$NO_CONTRACT/registry.md"
cp "$C/pricing-inquiry.md" "$NO_CONTRACT/pricing-inquiry.md"
cp "$C/pricing-inquiry--build-with-ai-prompt.md" "$NO_CONTRACT/pricing-inquiry--build-with-ai-prompt.md"

if out="$(bash "$VALIDATOR" --dir "$NO_CONTRACT" --slug pricing-inquiry 2>&1)"; then
  bad "NO_CONTRACT: expected exit 1"
  printf '%s\n' "$out" | sed 's/^/        /'
else
  status=$?
  if [ "$status" -eq 1 ] && printf '%s' "$out" | grep -q 'build contract MISSING'; then
    ok "NO_CONTRACT: missing contract fails validation"
  else
    bad "NO_CONTRACT: expected exit 1 and missing-contract message, got $status"
    printf '%s\n' "$out" | sed 's/^/        /'
  fi
fi

# SLUG_MISSING: requested slug absent from registry and disk.
if out="$(bash "$VALIDATOR" --dir "$C" --slug ghost-workflow 2>&1)"; then
  bad "SLUG_MISSING: expected exit 4"
  printf '%s\n' "$out" | sed 's/^/        /'
else
  status=$?
  if [ "$status" -eq 4 ] && printf '%s' "$out" | grep -q 'SLUG_NOT_REGISTERED: ghost-workflow'; then
    ok "SLUG_MISSING: absent slug exits 4 with diagnostic"
  else
    bad "SLUG_MISSING: expected exit 4 and SLUG_NOT_REGISTERED, got $status"
    printf '%s\n' "$out" | sed 's/^/        /'
  fi
fi

# LEGACY_WARN: legacy prompt filename satisfies leg 2 but emits warning.
LEGACY="$TMP/legacy/conversation-workflows"
mkdir -p "$LEGACY"
cat > "$LEGACY/registry.md" <<'EOF'
# Conversation Workflows - Registry

## Active workflows

- pricing-inquiry: New lead asks about pricing
EOF
declared_playbook "Pricing inquiry" "$LEGACY/pricing-inquiry.md"
printf '# legacy prompt\n' > "$LEGACY/pricing-inquiry--workflow-ai-prompt.md"
write_contract "$LEGACY/pricing-inquiry.md"

if out="$(bash "$VALIDATOR" --dir "$LEGACY" --slug pricing-inquiry 2>&1)"; then
  if printf '%s' "$out" | grep -q 'legacy prompt filename'; then
    ok "LEGACY_WARN: legacy prompt passes with warning"
  else
    bad "LEGACY_WARN: expected warning text"
    printf '%s\n' "$out" | sed 's/^/        /'
  fi
else
  status=$?
  bad "LEGACY_WARN: expected exit 0, got $status"
  printf '%s\n' "$out" | sed 's/^/        /'
fi

# SLUG_SCOPED: --slug restricts validation to the requested slug(s); a
# complete requested slug must not inherit a neighbour's problems.
MIXED="$TMP/mixed/conversation-workflows"
mkdir -p "$MIXED"
cat > "$MIXED/registry.md" <<'EOF'
# Conversation Workflows - Registry

## Active workflows

- keep-me: Requested slug that is complete
- broken-other: Registered but nobody wrote the files
EOF

declared_playbook "Keep me" "$MIXED/keep-me.md"
printf '# keep-me prompt\n' > "$MIXED/keep-me--build-with-ai-prompt.md"
write_contract "$MIXED/keep-me.md"

out="$(bash "$VALIDATOR" --dir "$MIXED" --slug keep-me 2>&1)"
status=$?
if [ "$status" -eq 0 ] && printf '%s' "$out" | grep -q '\[OK\]   keep-me'; then
  ok "SLUG_SCOPED: complete requested slug exits 0"
else
  bad "SLUG_SCOPED: expected exit 0 for keep-me, got $status"
  printf '%s\n' "$out" | sed 's/^/        /'
fi

if printf '%s' "$out" | grep -q 'broken-other'; then
  bad "SLUG_SCOPED: filtered run leaked unrequested slug broken-other"
else
  ok "SLUG_SCOPED: filtered run ignores other workflows' problems"
fi

# The same fixture unfiltered must still fail on the broken neighbour, so the
# pass above is scoping, not blindness.
out="$(bash "$VALIDATOR" --dir "$MIXED" 2>&1)"
status=$?
if [ "$status" -eq 1 ] && printf '%s' "$out" | grep -q 'broken-other'; then
  ok "SLUG_SCOPED: unfiltered run still fails on the broken neighbour"
else
  bad "SLUG_SCOPED: unfiltered run expected exit 1 naming broken-other, got $status"
  printf '%s\n' "$out" | sed 's/^/        /'
fi

# Repeated --slug accumulates rather than overwriting.
out="$(bash "$VALIDATOR" --dir "$MIXED" --slug keep-me --slug broken-other 2>&1)"
status=$?
if [ "$status" -eq 1 ] && printf '%s' "$out" | grep -q 'broken-other'; then
  ok "SLUG_SCOPED: repeated --slug accumulates requested slugs"
else
  bad "SLUG_SCOPED: repeated --slug expected exit 1 naming broken-other, got $status"
  printf '%s\n' "$out" | sed 's/^/        /'
fi

# --slug with no value is a usage error, not a validation result.
out="$(bash "$VALIDATOR" --dir "$C" --slug 2>&1)"
status=$?
if [ "$status" -eq 2 ] && printf '%s' "$out" | grep -q 'Missing value for --slug'; then
  ok "SLUG_NO_VALUE: dangling --slug exits 2"
else
  bad "SLUG_NO_VALUE: expected exit 2 and Missing value message, got $status"
  printf '%s\n' "$out" | sed 's/^/        /'
fi

# The JSON branch of the missing-slug diagnostic.
out="$(bash "$VALIDATOR" --dir "$C" --slug ghost-workflow --json 2>&1)"
status=$?
verdict="$(printf '%s' "$out" | python3 -c "import json,sys; print(json.load(sys.stdin)['verdict'])" 2>/dev/null)"
missing="$(printf '%s' "$out" | python3 -c "import json,sys; print(','.join(json.load(sys.stdin)['missing_slugs']))" 2>/dev/null)"
if [ "$status" -eq 4 ] && [ "$verdict" = "SLUG_NOT_REGISTERED" ] && [ "$missing" = "ghost-workflow" ]; then
  ok "SLUG_MISSING JSON: exit 4, verdict SLUG_NOT_REGISTERED, names the slug"
else
  bad "SLUG_MISSING JSON: expected exit 4/SLUG_NOT_REGISTERED/ghost-workflow, got $status/$verdict/$missing"
  printf '%s\n' "$out" | sed 's/^/        /'
fi

# HASH: a contract generated from the playbook passes; replacing the playbook
# with a DIFFERENT but still parseable structure must fail on the hash compare
# itself, not on a parse exception.
HASHFX="$TMP/hash/conversation-workflows"
mkdir -p "$HASHFX"
cat > "$HASHFX/registry.md" <<'EOF'
# Conversation Workflows - Registry

## Active workflows

- hash-check: Workflow whose contract tracks playbook structure
EOF

declared_playbook "Hash check" "$HASHFX/hash-check.md"
printf '# hash-check prompt\n' > "$HASHFX/hash-check--build-with-ai-prompt.md"
write_contract "$HASHFX/hash-check.md"

out="$(bash "$VALIDATOR" --dir "$HASHFX" --slug hash-check 2>&1)"
status=$?
if [ "$status" -eq 0 ]; then
  ok "HASH_MATCH: contract whose hash matches the playbook passes"
else
  bad "HASH_MATCH: expected exit 0, got $status"
  printf '%s\n' "$out" | sed 's/^/        /'
fi

cat > "$HASHFX/hash-check.md" <<'EOF'
# Hash check

declares
tools-used: update_tags
exits-used: talk-to-human
pipeline: sales-pipeline
stage-map: qualified: STAGE_QUALIFIED

## Phase 1 - Opening differently
Say hello.

## Exit rules

exit-when-tag: talk-to-human, action: handoff
EOF

out="$(bash "$VALIDATOR" --dir "$HASHFX" --slug hash-check 2>&1)"
status=$?
if [ "$status" -eq 1 ] \
  && printf '%s' "$out" | grep -q 'playbook_structure_hash does not match' \
  && printf '%s' "$out" | grep -q 'hash-check'; then
  ok "HASH_MISMATCH: differing-but-parseable playbook fails naming the slug"
else
  bad "HASH_MISMATCH: expected exit 1 with mismatch message naming hash-check, got $status"
  printf '%s\n' "$out" | sed 's/^/        /'
fi

# Malformed contract payloads must not pass the fourth leg.
BADFX="$TMP/bad-contract/conversation-workflows"
mkdir -p "$BADFX"
cp "$C/registry.md" "$BADFX/registry.md"
cp "$C/pricing-inquiry.md" "$BADFX/pricing-inquiry.md"
cp "$C/pricing-inquiry--build-with-ai-prompt.md" "$BADFX/pricing-inquiry--build-with-ai-prompt.md"

printf '{not json\n' > "$BADFX/pricing-inquiry--build-contract.json"
out="$(bash "$VALIDATOR" --dir "$BADFX" --slug pricing-inquiry 2>&1)"
status=$?
if [ "$status" -eq 1 ] && printf '%s' "$out" | grep -q 'build contract is unreadable JSON'; then
  ok "CONTRACT_UNREADABLE: malformed JSON fails"
else
  bad "CONTRACT_UNREADABLE: expected exit 1 and unreadable-JSON message, got $status"
  printf '%s\n' "$out" | sed 's/^/        /'
fi

printf '{"playbook_id": "pricing-inquiry"}\n' > "$BADFX/pricing-inquiry--build-contract.json"
out="$(bash "$VALIDATOR" --dir "$BADFX" --slug pricing-inquiry 2>&1)"
status=$?
if [ "$status" -eq 1 ] && printf '%s' "$out" | grep -q 'missing playbook_structure_hash'; then
  ok "CONTRACT_NO_HASH: contract without playbook_structure_hash fails"
else
  bad "CONTRACT_NO_HASH: expected exit 1 and missing-hash message, got $status"
  printf '%s\n' "$out" | sed 's/^/        /'
fi

# Engine unavailable is a hard fail, never a silent pass on leg 4.
NOENG="$TMP/no-engine"
mkdir -p "$NOENG/scripts"
cp "$VALIDATOR" "$NOENG/scripts/qc-trinity-registry.sh"
out="$(cd "$NOENG" && bash scripts/qc-trinity-registry.sh --dir "$C" --slug pricing-inquiry 2>&1)"
status=$?
if [ "$status" -eq 1 ] && printf '%s' "$out" | grep -q 'cannot be verified'; then
  ok "ENGINE_UNAVAILABLE: missing playbook_engine fails leg 4"
else
  bad "ENGINE_UNAVAILABLE: expected exit 1 and cannot-be-verified message, got $status"
  printf '%s\n' "$out" | sed 's/^/        /'
fi

echo ""
echo "qc-trinity-registry tests: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
