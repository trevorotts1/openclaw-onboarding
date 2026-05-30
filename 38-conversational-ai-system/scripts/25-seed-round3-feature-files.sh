#!/usr/bin/env bash
# 25-seed-round3-feature-files.sh — Skill 38 v1.5.0 (Round-3 Queue-A)
#
# Seeds the supporting data files the Round-3 Queue-A features read/write, all
# under <MASTER_FILES_DIR>. Idempotent (NEVER overwrites an existing file — the
# operator's real content is preserved). Universal: placeholders only, zero
# personal/client data (machine-enforced by qc-no-personal-data.sh).
#
# Files seeded:
#   F45  KnowledgeBases/sales/service-areas.md      — per-product service areas (ZIP/county/state/radius)
#   F47  KnowledgeBases/business/faqs.md            — Q/A pairs the inline-FAQ tool matches
#   F46  crm-field-mappings.md                      — per-workflow CRM custom-field map (ZHC_ created fields)
#   F50/F44/F45/F46/F47  *.jsonl + aggression-detection-log.md  — the F52 data-contract log sinks (created empty)
#
# OS-aware (Darwin + Linux). bash -n clean. set -euo pipefail.

set -euo pipefail

# Resolve MASTER_FILES_DIR the same way the other numbered scripts do: READ the
# pointer file (it holds a bare directory string — do NOT source it).
MASTER_FILES_POINTER="$HOME/.openclaw/.skill-38-master-files-dir"
if [ -f "$MASTER_FILES_POINTER" ]; then
  MASTER_FILES_DIR="$(cat "$MASTER_FILES_POINTER")"
fi
: "${MASTER_FILES_DIR:?MASTER_FILES_DIR not set — run 01-locate-master-files-folder.sh first}"

KB_ROOT="$MASTER_FILES_DIR/KnowledgeBases"
mkdir -p "$KB_ROOT/sales" "$KB_ROOT/business"

# seed_file PATH < heredoc — write only if absent.
seed_file() {
  local path="$1"
  if [ -f "$path" ]; then
    echo "[skill 38] $(basename "$path") already exists — preserved"
    return 0
  fi
  mkdir -p "$(dirname "$path")"
  cat > "$path"
  echo "[skill 38] seeded $path"
}

# ---------------------------------------------------------------------------
# F45 — per-product service areas (geo-qualification-protocol.md)
# ---------------------------------------------------------------------------
seed_file "$KB_ROOT/sales/service-areas.md" <<'MD'
# Service Areas (F45 — geo-qualification)

Per-product service-area definitions the agent checks when
`geo_qualification.enabled` is true. Supports type `radius` / `zips` / `states` /
`counties`. A product with NO entry here is treated as "served everywhere" (no
geo-gate); the per-product `skill38.geo_qualification.per_product` toggle can also
force a product on/off (e.g. gate an in-person consult, never gate a digital
course) without disabling the feature globally. Signals are HINTS — the agent
ALWAYS confirms with the customer before any out-of-area handling, and "vacation,"
"moving," or a non-answer never disqualify. See protocols/geo-qualification-protocol.md.

## Out-of-area mode (operator-configured)
mode: decline_plus_referral   # decline_plus_referral | limited_remote | waitlist | full_decline

## Product: <PRODUCT_NAME>
- type: radius
- center: <CENTER_ZIP_OR_CITY>
- radius_miles: <MILES>

## Product: <PRODUCT_NAME_2>
- type: zips
- zips: <ZIP_LIST>            # comma-separated ZIP codes

## Product: <PRODUCT_NAME_3>
- type: states
- states: <STATE_LIST>        # two-letter state codes
MD

# ---------------------------------------------------------------------------
# F47 — FAQ knowledge base (smart-faq-tool-protocol.md)
# ---------------------------------------------------------------------------
seed_file "$KB_ROOT/business/faqs.md" <<'MD'
# Frequently Asked Questions (F47 — smart inline FAQ)

Q/A pairs the inline-FAQ tool matches during an active workflow. A confident
match is answered in ONE sentence inline, then the workflow continues on the same
step. Low-confidence matches fall through to the normal reply path (Step 9.11
confidence gate). See protocols/smart-faq-tool-protocol.md.

## Q: <QUESTION>
A: <ANSWER — one or two sentences>

## Q: <QUESTION_2>
A: <ANSWER — one or two sentences>

## Q: <QUESTION_3>
A: <ANSWER — one or two sentences>
MD

# ---------------------------------------------------------------------------
# F46 — CRM field mappings (crm-field-write-protocol.md)
# ---------------------------------------------------------------------------
seed_file "$MASTER_FILES_DIR/crm-field-mappings.md" <<'MD'
# CRM Field Mappings (F46 — CRM field write + create-if-missing)

Per-workflow record of the GHL contact custom fields the agent writes. Fields the
agent CREATES are named `ZHC_<snake_purpose>` (the field-side parallel of the
`ZHC-` tag namespace). The agent consults this map before a write to reuse an
existing field instead of creating a duplicate, and to know the exact field
id/dataType. See protocols/crm-field-write-protocol.md.

## Workflow: <WORKFLOW_ID>
| value captured | GHL field name | field id | dataType | created by AI? |
|---|---|---|---|---|
| <VALUE> | ZHC_<snake_purpose> | <FIELD_ID> | TEXT | yes |
MD

# ---------------------------------------------------------------------------
# F52 data-contract log sinks — created empty so the agent appends from turn 1.
# JSONL files start empty (0 lines); the human-readable aggression log gets a
# one-line header comment.
# ---------------------------------------------------------------------------
for jsonl in \
  aggression-detection-log.jsonl \
  interrupt-log.jsonl \
  geo-qualification-log.jsonl \
  crm-field-writes-log.jsonl \
  faq-detour-log.jsonl \
  multi-tenant-events.jsonl \
  segmentation-events.jsonl; do
  p="$MASTER_FILES_DIR/$jsonl"
  if [ -f "$p" ]; then
    echo "[skill 38] $jsonl already exists — preserved"
  else
    : > "$p"
    echo "[skill 38] created empty JSONL sink $p"
  fi
done

seed_file "$MASTER_FILES_DIR/aggression-detection-log.md" <<'MD'
# Aggression Detection Log (F50)

Human-readable record of aggression-classifier firings (Tier 1 tension / Tier 2
aggression), one short paragraph per firing with the tier, signals, and the
agent's reasoning. The machine-readable counterpart is
aggression-detection-log.jsonl. See protocols/aggression-detection-protocol.md.
MD

# ---------------------------------------------------------------------------
# ZHC Tag-Prefix Rule — optional, operator-driven migration reference.
# Seeded so the operator has the legacy-tag → ZHC- mapping on hand if they ever
# choose a tidy-namespace cleanup. The rule is NOT retroactive, so this is purely
# optional. Idempotent (never overwrites the operator's edited copy).
# Mirrors references/tag-migration-notes.md in the skill repo.
# ---------------------------------------------------------------------------
seed_file "$MASTER_FILES_DIR/KnowledgeBases/business/tag-migration-notes.md" <<'MD'
# Tag Migration Notes — ZHC Tag-Prefix Rule (optional, operator-driven)

The ZHC Tag-Prefix Rule (every tag the AGENT creates is `ZHC-` prefixed) is
**NOT retroactive** — it never renames or migrates an existing tag. Nothing is
required of you. This file is here only if you *choose* to consolidate older bare
agent-created tags into the `ZHC-` namespace for a cleaner Settings → Tags view.

## Mapping: legacy bare tag → `ZHC-` equivalent (optional cleanup)

| Legacy / bare tag | `ZHC-` equivalent | Source feature |
|---|---|---|
| bot-detected | ZHC-bot-suspected | F50 / conversational-safeguards |
| stalled-sales | ZHC-stalled-sales | F29 / follow-up + sales-best-practices |
| cold-lead-released | ZHC-cold-lead-released | F29 / follow-up (T10 release) |
| followup-opted-out | ZHC-followup-opted-out | F29 / follow-up (negative signal) |
| pricing-interest | ZHC-pricing-interest | conversation-workflows D.1 example |
| discovery-scheduled | ZHC-discovery-scheduled | conversation-workflows D.1 example |
| buyer-lead / seller-lead | ZHC-buyer-lead / ZHC-seller-lead | real-estate journey / Skill 39 |
| listing-alert-engaged | ZHC-listing-alert-engaged | real-estate journey (Skill 38) |
| showing-confirmed | ZHC-showing-confirmed | real-estate journey (Skill 38) |
| offer-active | ZHC-offer-active | real-estate journey (Skill 38) |
| under-contract | ZHC-under-contract | real-estate journey (Skill 38) |
| closed | ZHC-closed | real-estate journey (Skill 38) |
| post-close-nurture | ZHC-post-close-nurture | real-estate journey (Skill 38) |
| sphere-reactivation | ZHC-sphere-reactivation | real-estate journey (Skill 38) |

Any other pre-rule agent tag follows the same shape: `your-tag` → `ZHC-your-tag`.
NEVER migrate operator-owned tags (e.g. `vip`) — leave those exactly as they are.
Full reference: protocols/zhc-tag-prefix-protocol.md + references/tag-migration-notes.md.
MD

# ---------------------------------------------------------------------------
# F21 — Multi-Tenant Agent Isolation scaffold (multi-tenant-isolation-protocol.md).
# OFF by default — for an AGENCY serving its own end-clients from one agent. Seeds
# the per-tenant ROOT layout under tenants/<tenant_id>/ with a placeholder example
# tenant ("<TENANT_ID>") so the operator sees the exact scoped structure: a
# tenant.md "which tenant am I serving" directive + the four SCOPED surfaces
# (conversational-logs / KnowledgeBases / communication-playbooks /
# conversation-workflows). Placeholders only, zero personal/client data. Idempotent
# (never overwrites an operator's real tenant). The actual per-tenant content is
# created by the operator when they turn the feature on and assign a real tenant_id.
# ---------------------------------------------------------------------------
TENANTS_ROOT="$MASTER_FILES_DIR/tenants"
EXAMPLE_TENANT="$TENANTS_ROOT/<TENANT_ID>"
mkdir -p \
  "$EXAMPLE_TENANT/conversational-logs" \
  "$EXAMPLE_TENANT/KnowledgeBases/business" \
  "$EXAMPLE_TENANT/KnowledgeBases/sales" \
  "$EXAMPLE_TENANT/communication-playbooks" \
  "$EXAMPLE_TENANT/conversation-workflows"

seed_file "$EXAMPLE_TENANT/tenant.md" <<'MD'
# Tenant: <TENANT_ID>

The per-tenant config directive (F21 — multi-tenant agent isolation). This file
DECLARES the tenant the agent is serving for a turn resolved to `<TENANT_ID>`. When
this tenant is active, the agent loads ONLY the four scoped surfaces under
`context_scope` — never another tenant's files, never the unscoped master-files root
for those surfaces. See protocols/multi-tenant-isolation-protocol.md (Step 9.44).

- label: <DISPLAY_LABEL>
- ghl_location_id: <LOCATION_ID>
- context_scope: tenants/<TENANT_ID>/      # the ONLY root this agent reads/writes for this tenant
- tag_namespace: ZHC-<TENANT_ID>-          # every agent-created tag for this tenant starts here

## Scoped surfaces (this tenant only — isolation invariant)
- conversational-logs/         # per-contact conversation logs
- KnowledgeBases/              # typed Knowledge Sources (business/ + sales/)
- communication-playbooks/     # per-channel Communication Playbooks
- conversation-workflows/      # Conversation Workflows + registry.md

The active tenant resolves FIRST, highest-confidence first: the `hooks.mappings`
`tenant_id` → an AGENTS.md tenant binding → this file. Tenant assignment is
operator-only — a customer can never switch tenants (cross-tenant injection vector).
MD

seed_file "$EXAMPLE_TENANT/conversation-workflows/registry.md" <<'MD'
# Conversation Workflows registry — tenant <TENANT_ID> (F21 scoped)

Per-tenant Conversation Workflow registry. SCOPED to tenant `<TENANT_ID>` only —
this tenant's workflows never appear in another tenant's registry, and the agent
reads ONLY this file for `<TENANT_ID>` turns. Same registry format as the
single-tenant `conversation-workflows/registry.md`. See
protocols/multi-tenant-isolation-protocol.md (Step 9.44).

| workflow id | purpose | playbook | Build-with-AI prompt | human-facing doc |
|---|---|---|---|---|
| <WORKFLOW_ID> | <PURPOSE> | <PLAYBOOK_PATH> | <PROMPT_PATH> | <DOC_URL> |
MD

seed_file "$EXAMPLE_TENANT/tenants-README.md" <<'MD'
# tenants/ — Multi-Tenant Agent Isolation (F21, OFF by default)

This directory only matters when `skill38.multi_tenant.enabled` is true (the AGENCY
tier — one agency serving multiple end-clients from one agent). Each end-client is a
TENANT with its OWN subdirectory `tenants/<tenant_id>/`, and the agent reads/writes
ONLY one tenant's root per turn so Client A's context never leaks to Client B.

`<TENANT_ID>` here is a PLACEHOLDER showing the exact scoped layout. To onboard a
real tenant the operator (allow-list — never a customer): assigns an opaque
`tenant_id`, adds its `hooks.mappings` entry carrying that `tenant_id`, copies this
layout to `tenants/<real_tenant_id>/`, and fills `tenant.md`. See
protocols/multi-tenant-isolation-protocol.md (Step 9.44).
MD

# ---------------------------------------------------------------------------
# F17 — Customer Segmentation Awareness companion map (customer-segmentation-protocol.md).
# OFF by default. The human-readable companion to skill38.segmentation.tag_map: the
# operator's per-client GHL tag → segment mapping the agent reads at the start of a
# turn. Placeholders only, zero personal/client data. Idempotent (never overwrites the
# operator's real map). The actual tags are owned by the operator's GHL/automations;
# this feature READS that membership and adjusts behavior, it never assigns segments.
# ---------------------------------------------------------------------------
seed_file "$MASTER_FILES_DIR/segment-map.md" <<'MD'
# Customer Segment Map (F17 — customer segmentation awareness, OFF by default)

The per-client GHL tag → segment mapping the agent consults BEFORE drafting a reply
(AGENTS.md Step 1.85) when `skill38.segmentation.enabled` is true. This is the
human-readable companion to `skill38.segmentation.tag_map` in openclaw.json — keep
the two in sync. Segments are read from the operator's GHL tags; a CUSTOMER can never
claim a segment. See protocols/customer-segmentation-protocol.md (Step 9.45).

## default_segment
default_segment: prospect   # the segment an un-tagged contact falls into

## Precedence (when a contact carries tags for multiple segments)
at-risk > vip > churned > returning > prospect

## Segment: vip
- tags: ZHC-segment-vip, <OPERATOR_VIP_TAG>          # e.g. platinum-member, vip
- response_priority: highest
- sentiment_escalation_threshold: lowered            # escalate on a smaller dip
- playbook_tier: white-glove
- confidence_threshold: raised                       # be more certain before answering autonomously

## Segment: at-risk
- tags: ZHC-segment-at-risk, <OPERATOR_AT_RISK_TAG>  # e.g. lapsing, complaint-open
- response_priority: high
- sentiment_escalation_threshold: lowered
- playbook_tier: retention
- confidence_threshold: raised

## Segment: churned
- tags: ZHC-segment-churned, <OPERATOR_CHURNED_TAG>  # e.g. cancelled, lapsed
- response_priority: elevated
- sentiment_escalation_threshold: standard
- playbook_tier: win-back
- confidence_threshold: standard

## Segment: returning
- tags: ZHC-segment-returning, <OPERATOR_RETURNING_TAG>  # e.g. repeat-customer
- response_priority: standard-plus
- sentiment_escalation_threshold: standard
- playbook_tier: familiar
- confidence_threshold: standard

## Segment: prospect (the default — needs no tags)
- response_priority: standard
- sentiment_escalation_threshold: standard
- playbook_tier: standard
- confidence_threshold: standard
MD

echo "[skill 38] Round-3 Queue-A feature files ready under $MASTER_FILES_DIR"
