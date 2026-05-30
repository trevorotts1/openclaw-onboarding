#!/usr/bin/env bash
# qc-multi-tenant.sh — machine-enforce the Multi-Tenant Agent Isolation feature
# (F21, Round-2 backlog): the isolation protocol, the per-tenant scoping/namespacing
# scheme, the per-tenant config mechanism, the hooks.mappings tenant_id convention,
# the PII-free F52 log, the default-OFF toggle, and the operator-only guard are all
# present and wired where they must be — so a regression that drops any load-bearing
# invariant fails the build.
#
# WHY: an agency runs ONE agent for MANY end-clients; the whole point of F21 is that
# Client A's context (conversations, Knowledge Sources, Communication Playbooks,
# Conversation Workflows) NEVER leaks to Client B. That guarantee is enforced by
# path/namespace separation per tenant_id + a "which tenant am I serving" directive.
# This gate proves the skill's docs/wiring actually carry that guarantee.
#
# WHAT IT CHECKS (all from the repo alone — CI-safe, BASH-only so it respects the .py
# claude-/anthropic ban):
#   1. The protocol exists (multi-tenant-isolation-protocol.md) and states its
#      load-bearing substance: tenant_id, hooks.mappings tenant_id convention, the
#      per-tenant root tenants/<tenant_id>/, ALL FOUR scoped surfaces, the per-tenant
#      tenant.md config directive, the ZHC-<tenant_id>- tag namespace, the
#      operator-only/never-customer-invoked guard, the "Client A ... never leak ...
#      Client B" isolation invariant, and the honest "NOT a ... DB migration" scope.
#   2. AGENTS.md gets the STEP_0_8_MULTI_TENANT_ISOLATION marker block
#      (05-update-agents-md.sh).
#   3. MEMORY Rule 26 is appended (06-append-memory-rules.sh).
#   4. The F52 log multi-tenant-events.jsonl: documented in the protocol with a
#      timestamp+event_type example carrying event_type "tenant_routing", documented
#      in INSTRUCTIONS.md, and SEEDED by 25-seed-round3-feature-files.sh. The seeder
#      also scaffolds the tenants/<tenant_id>/ per-tenant root.
#   5. PII guard: the protocol's JSONL example line must NOT carry a raw customer-value
#      key (value_written/"value"/field_value/raw_value/email/phone/address) — the
#      contract is opaque keys + scope NAMES + counts only.
#   6. The toggle skill38.multi_tenant.enabled is documented DEFAULT FALSE.
#
# Exit codes: 0 = clean; 1 = at least one F21 invariant violation.
#
# Usage:
#   bash scripts/qc-multi-tenant.sh
#   bash scripts/qc-multi-tenant.sh --skill-dir /path/to/38-conversational-ai-system

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

while [ $# -gt 0 ]; do
  case "$1" in
    --skill-dir) SKILL_DIR="$2"; shift 2 ;;
    -h|--help)   sed -n '1,40p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

FAIL=0
pass() { echo "  [PASS] $1"; }
fail() { echo "  [FAIL] $1"; FAIL=1; }

echo "=== qc-multi-tenant: F21 multi-tenant agent isolation gate ==="
echo "skill_dir : $SKILL_DIR"
echo ""

PROTO="$SKILL_DIR/protocols/multi-tenant-isolation-protocol.md"
AG_SCRIPT="$SKILL_DIR/scripts/05-update-agents-md.sh"
MEM_SCRIPT="$SKILL_DIR/scripts/06-append-memory-rules.sh"
INSTR="$SKILL_DIR/INSTRUCTIONS.md"
INSTALLER="$SKILL_DIR/scripts/25-seed-round3-feature-files.sh"
JSONL="multi-tenant-events.jsonl"
EVT="tenant_routing"

# 1. Protocol exists + load-bearing substance.
if [ -f "$PROTO" ]; then
  pass "protocols/multi-tenant-isolation-protocol.md exists"

  grep -q 'tenant_id' "$PROTO" \
    && pass "protocol uses the opaque tenant_id key" \
    || fail "protocol must define the opaque tenant_id key"

  # hooks.mappings tenant_id convention (routing).
  grep -q 'hooks.mappings' "$PROTO" && grep -q '"tenant_id"' "$PROTO" \
    && pass "protocol documents the hooks.mappings tenant_id convention (routing)" \
    || fail "protocol must document the hooks.mappings tenant_id convention"

  # per-tenant root path/namespace.
  grep -q 'tenants/<tenant_id>/' "$PROTO" \
    && pass "protocol scopes storage to the per-tenant root tenants/<tenant_id>/" \
    || fail "protocol must scope storage to tenants/<tenant_id>/ (path/namespace per tenant)"

  # ALL FOUR scoped surfaces named.
  surf_missing=0
  for surf in 'conversational-logs' 'KnowledgeBases' 'communication-playbooks' 'conversation-workflows'; do
    grep -q "$surf" "$PROTO" || { fail "protocol must scope the surface: $surf"; surf_missing=1; }
  done
  [ "$surf_missing" -eq 0 ] && pass "protocol scopes ALL FOUR surfaces (conversational-logs / KnowledgeBases / communication-playbooks / conversation-workflows)"

  # per-tenant config directive mechanism.
  grep -q 'tenant.md' "$PROTO" \
    && pass "protocol defines the per-tenant config directive (tenant.md — which tenant am I serving)" \
    || fail "protocol must define the per-tenant config directive (tenant.md)"

  # ZHC-<tenant_id>- tag namespace.
  grep -q 'ZHC-<tenant_id>-' "$PROTO" \
    && pass "protocol namespaces tags per tenant (ZHC-<tenant_id>-…)" \
    || fail "protocol must namespace tags per tenant (ZHC-<tenant_id>-…)"

  # operator-only / never-customer-invoked guard.
  if grep -qi 'operator-only' "$PROTO" && grep -qi 'never.*customer\|customer.*never\|never-customer' "$PROTO"; then
    pass "protocol states tenant assignment is operator-only / never customer-invoked"
  else
    fail "protocol must state tenant assignment is operator-only / never customer-invoked (cross-tenant injection guard)"
  fi

  # isolation invariant: A never leaks to B.
  if grep -qi 'never leak\|never leaks\|NEVER leak' "$PROTO" && grep -qi 'Client A' "$PROTO" && grep -qi 'Client B' "$PROTO"; then
    pass "protocol states the isolation invariant (Client A's context NEVER leaks to Client B)"
  else
    fail "protocol must state the isolation invariant (Client A NEVER leaks to Client B)"
  fi

  # honest scope: NOT a runtime DB migration (tolerate markdown bold around "not").
  if grep -qiE 'not\*{0,2} a runtime database migration|not\*{0,2} a (runtime )?DB migration|not a runtime db migration' "$PROTO"; then
    pass "protocol is honest about scope (architecture/protocol feature, NOT a runtime DB migration)"
  else
    fail "protocol must be honest about scope (NOT a runtime DB migration)"
  fi
else
  fail "protocols/multi-tenant-isolation-protocol.md MISSING"
fi

echo ""

# 2. AGENTS.md marker block.
if [ -f "$AG_SCRIPT" ] && grep -q 'STEP_0_8_MULTI_TENANT_ISOLATION' "$AG_SCRIPT"; then
  pass "05-update-agents-md.sh inserts the STEP_0_8_MULTI_TENANT_ISOLATION block"
else
  fail "05-update-agents-md.sh is missing the STEP_0_8_MULTI_TENANT_ISOLATION block"
fi

# 3. MEMORY Rule 26.
if [ -f "$MEM_SCRIPT" ] && grep -qE '^26\. *Multi-Tenant Isolation Rule' "$MEM_SCRIPT"; then
  pass "06-append-memory-rules.sh appends MEMORY Rule 26 (Multi-Tenant Isolation Rule)"
else
  fail "06-append-memory-rules.sh is missing MEMORY Rule 26 (Multi-Tenant Isolation Rule)"
fi

echo ""

# 4. F52 log: protocol example + INSTRUCTIONS + seeded.
if [ -f "$PROTO" ]; then
  grep -qF "$JSONL" "$PROTO" \
    && pass "protocol documents the JSONL path ($JSONL)" \
    || fail "protocol must document the JSONL path ($JSONL)"
  if grep -E '"timestamp"' "$PROTO" | grep -q '"event_type"'; then
    pass "protocol shows a timestamp+event_type JSONL example"
  else
    fail "protocol JSONL example must carry both \"timestamp\" and \"event_type\" on one line"
  fi
  grep -qF "$EVT" "$PROTO" \
    && pass "protocol JSONL example carries event_type value \"$EVT\"" \
    || fail "protocol JSONL example missing event_type value \"$EVT\""
fi

if [ -f "$INSTR" ]; then
  if grep -qF "$JSONL" "$INSTR" && grep -qF "$EVT" "$INSTR"; then
    pass "INSTRUCTIONS.md documents the data contract for $JSONL (path + event_type \"$EVT\")"
  else
    fail "INSTRUCTIONS.md does not document the data contract for $JSONL (path + event_type \"$EVT\")"
  fi
else
  fail "INSTRUCTIONS.md not found"
fi

if [ -f "$INSTALLER" ]; then
  grep -qF "$JSONL" "$INSTALLER" \
    && pass "25-seed-round3-feature-files.sh seeds the JSONL sink ($JSONL)" \
    || fail "25-seed-round3-feature-files.sh does not seed $JSONL"
  if grep -q 'tenants/<TENANT_ID>\|tenants/$\|tenants/"' "$INSTALLER" || grep -q 'TENANTS_ROOT' "$INSTALLER"; then
    pass "25-seed-round3-feature-files.sh scaffolds the per-tenant root tenants/<tenant_id>/"
  else
    fail "25-seed-round3-feature-files.sh must scaffold the per-tenant root tenants/<tenant_id>/"
  fi
else
  fail "scripts/25-seed-round3-feature-files.sh not found"
fi

echo ""

# 5. PII guard — the JSONL example line must not carry a raw customer-value key.
if [ -f "$PROTO" ]; then
  if grep -E '"timestamp"' "$PROTO" \
       | grep '"event_type"' \
       | grep -Eq '"(value_written|value|field_value|raw_value|email|phone|address)"[[:space:]]*:'; then
    fail "protocol JSONL example leaks a raw customer-value key (value_written/value/field_value/raw_value/email/phone/address) — the contract is opaque keys + scope NAMES + counts only"
  else
    pass "protocol JSONL example is PII-free (no raw-value key — opaque tenant_id + scope NAMES + counts only)"
  fi
fi

# 6. Toggle documented DEFAULT FALSE.
if [ -f "$PROTO" ]; then
  if grep -q 'skill38.multi_tenant.enabled\|multi_tenant' "$PROTO" \
     && grep -qiE 'default \*\*false\*\*|default `?false`?|default FALSE|default false' "$PROTO"; then
    pass "toggle skill38.multi_tenant.enabled is documented default FALSE (opt-in agency feature)"
  else
    fail "toggle skill38.multi_tenant.enabled must be documented default FALSE"
  fi
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "RESULT: PASS — F21 multi-tenant isolation is documented (protocol + AGENTS Step 0.8 + MEMORY Rule 26), the per-tenant scoping/namespacing scheme + tenant.md config + hooks.mappings tenant_id convention are all present, the PII-free multi-tenant-events.jsonl contract is documented + seeded, the per-tenant root is scaffolded, and the toggle defaults OFF."
  exit 0
else
  echo "RESULT: FAIL — an F21 multi-tenant-isolation invariant is missing (see above)."
  exit 1
fi
