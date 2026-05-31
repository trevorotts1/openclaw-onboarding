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
  segmentation-events.jsonl \
  outreach-events.jsonl \
  ab-test-events.jsonl \
  voice-call-events.jsonl \
  webhook-chain-events.jsonl; do
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

# ---------------------------------------------------------------------------
# F15 — Proactive Outreach Campaigns scaffold (proactive-outreach-protocol.md).
# OFF by default. Seeds the campaign-definitions dir outreach-campaigns/ with ONE
# universal example campaign (cold-lead-reengagement.md) so the operator sees the
# exact campaign-definition format: trigger (cron|event) + GHL-tag audience +
# message template rendered THROUGH a Communication Playbook + frequency cap +
# opt-out + the ZHC-outreach-<campaign> tag. Placeholders only, zero personal/client
# data. Idempotent (never overwrites an operator's real campaign). The empty
# outreach-events.jsonl sink is created above in the JSONL loop. F29 Intelligent
# Follow-up migrates onto this infrastructure (its 10-touchpoint cadence becomes an
# event-triggered campaign). See protocols/proactive-outreach-protocol.md (Step 9.46).
# ---------------------------------------------------------------------------
OUTREACH_ROOT="$MASTER_FILES_DIR/outreach-campaigns"
mkdir -p "$OUTREACH_ROOT"

seed_file "$OUTREACH_ROOT/README.md" <<'MD'
# outreach-campaigns/ — Proactive Outreach Campaigns (F15, OFF by default)

This directory only matters when `skill38.proactive_outreach.enabled` is true. Each
file here is ONE scheduled/event-driven OUTBOUND campaign the agent runs (re-engage cold
leads, appointment reminders, post-purchase follow-up, win-back, birthday/anniversary).
Each campaign = a TRIGGER (time-based `cron` OR event-based), a GHL-TAG AUDIENCE filter, a
MESSAGE template rendered THROUGH the matching Communication Playbook (same brand voice as a
reactive reply), a FREQUENCY CAP, and OPT-OUT respect. Every touched contact is tagged
`ZHC-outreach-<campaign-id>`; opted-out contacts (`ZHC-outreach-opted-out`) are excluded
from every audience. Proactive sends STRICTLY respect quiet hours (Step 9.8).

Creating/enabling a campaign and firing a real SEND are OPERATOR-ONLY allow-list actions —
a customer can NEVER cause the agent to reach out to third parties. F29 Intelligent
Follow-up migrates onto this infrastructure (its 10-touchpoint cadence becomes an
event-triggered campaign). See protocols/proactive-outreach-protocol.md (Step 9.46).
MD

seed_file "$OUTREACH_ROOT/cold-lead-reengagement.md" <<'MD'
# Campaign: cold-lead-reengagement (F15 — proactive outreach)

A weekly sweep that re-engages leads who went cold. Reuses the SMS Communication
Playbook for tone. Respects quiet hours, the frequency cap, and opt-out. Tags every
touched contact ZHC-outreach-cold-lead-reengagement. See
protocols/proactive-outreach-protocol.md (Step 9.46).

## trigger
- type: cron
- cron: "0 15 * * 2"          # weekly, Tuesday 3pm (operator's timezone) — a sane, non-quiet-hours window

## audience
- include_tags: <COLD_LEAD_TAG>            # e.g. an operator tag like "cold-lead" or ZHC-cold-lead-released
- exclude_tags: <RECENT_CUSTOMER_TAG>      # never re-pitch an active buyer (ZHC-outreach-opted-out is implicit)

## message
- channel: sms
- playbook: communication-playbooks/sms-communication.md
- template: |
    Hey <FIRST_NAME>, it's <AGENT_NAME> from <BUSINESS_NAME> — circling back in case
    the timing's better now. No pressure at all; just reply if you'd like to pick up
    where we left off.

## frequency_cap
- per_contact_per_days: 14      # at most one re-engagement touch per contact every 14 days

## opt_out
- honor_tag: ZHC-outreach-opted-out
- channel_optout: "reply STOP"  # also covered by the Step 9.9 compliance keyword gate

## tag
- applied: ZHC-outreach-cold-lead-reengagement
MD

# ---------------------------------------------------------------------------
# F16 — A/B Testing of Reply Variants scaffold (ab-testing-protocol.md).
# OFF by default. Seeds the experiments dir ab-experiments/ with ONE universal
# example experiment (sms.md = the per-channel definition's human-readable companion
# to skill38.ab_testing.experiments) + the TWO variant overlays it references
# (sms-variant-a.md / sms-variant-b.md, each a tone/structure overlay ON TOP of the
# channel Communication Playbook — never a new playbook) + the dir README.
# Placeholders only, zero personal/client data. Idempotent (never overwrites an
# operator's real experiment). The empty ab-test-events.jsonl sink is created above
# in the JSONL loop. Variant selection happens at draft time (AGENTS.md Step 1.87);
# the winner is decided by a two-proportion z-test after N=30/arm conversations and
# auto-promotes (operator-notified). See protocols/ab-testing-protocol.md (Step 9.47).
# ---------------------------------------------------------------------------
ABTEST_ROOT="$MASTER_FILES_DIR/ab-experiments"
mkdir -p "$ABTEST_ROOT"

seed_file "$ABTEST_ROOT/README.md" <<'MD'
# ab-experiments/ — A/B Testing of Reply Variants (F16, OFF by default)

This directory only matters when `skill38.ab_testing.enabled` is true. Each `<channel>.md`
file here is the human-readable companion to `skill38.ab_testing.experiments.<channel>` in
openclaw.json — keep the two in sync. An experiment names exactly TWO variants (`a`/`b`),
each a tone/structure/CTA OVERLAY (`<channel>-variant-<arm>.md`) layered ON TOP of the
channel Communication Playbook — an overlay shifts only HOW the reply reads, it NEVER
overrides the playbook's mandatory SEND, conversation memory, escalation+honesty-floor, or
compliance.

Each inbound conversation is assigned an arm DETERMINISTICALLY BY CONTACT (a stable hash of
`experiment_id:contact_id mod 2`, sticky to the first recorded assignment) — a contact stays
in one arm for the experiment's life. Variant selection happens AT DRAFT TIME (AGENTS.md
Step 1.87). Outcomes (`booked` / `converted` / `sentiment_trajectory`) are tracked per
conversation; after BOTH arms hit `min_conversations_per_arm` (default N=30/arm) a
two-proportion z-test on the `primary_metric` declares a winner, which auto-promotes
(operator-notified). Agent-applied arm tags are `ZHC-abtest-variant-a` /
`ZHC-abtest-variant-b`.

Defining/starting/stopping/promoting an experiment and choosing an arm are OPERATOR-ONLY —
a customer can NEVER control the experiment. See protocols/ab-testing-protocol.md (Step 9.47).
MD

seed_file "$ABTEST_ROOT/sms.md" <<'MD'
# A/B Experiment: sms (F16 — A/B testing of reply variants)

The human-readable companion to `skill38.ab_testing.experiments.sms` in openclaw.json — keep
the two in sync. Two reply-style variants on the SMS channel; each inbound conversation is
assigned an arm deterministically by contact and stays in it. The winner is decided by a
two-proportion z-test on the primary metric after both arms hit min_per_arm, then
auto-promotes (operator-notified). See protocols/ab-testing-protocol.md (Step 9.47).

## experiment
- status: paused                 # paused | running | decided (OPERATOR sets this; default paused so no live assignment until the operator opts in)
- primary_metric: booked         # booked | converted — the ONE metric the significance test decides on
- min_per_arm: 30                # default N per arm before a winner can be declared

## variant_a
- label: <VARIANT_A_LABEL>       # e.g. warm-concise
- overlay: ab-experiments/sms-variant-a.md

## variant_b
- label: <VARIANT_B_LABEL>       # e.g. direct-cta
- overlay: ab-experiments/sms-variant-b.md

## assignment
- rule: deterministic_by_contact # stable_hash(experiment_id ":" contact_id) mod 2 → a/b; sticky to the first recorded arm
- tags: ZHC-abtest-variant-a / ZHC-abtest-variant-b
MD

seed_file "$ABTEST_ROOT/sms-variant-a.md" <<'MD'
# SMS Variant A — "<VARIANT_A_LABEL>" (F16 — A/B testing)

A tone/structure OVERLAY on communication-playbooks/sms-communication.md. It shifts ONLY how
the reply reads — it does NOT override the playbook's mandatory SEND, conversation memory,
escalation+honesty-floor, or compliance rules. See protocols/ab-testing-protocol.md (Step 9.47).

## opening
- <OPENING_STYLE — e.g. warm, first-name greeting; acknowledge their message in one clause>

## structure
- <STRUCTURE — e.g. 2 short sentences max; no bullet lists on SMS>

## cta
- <CTA_STYLE — e.g. soft invite: "happy to grab a time whenever suits you">

## length
- <LENGTH — e.g. under ~280 characters>
MD

seed_file "$ABTEST_ROOT/sms-variant-b.md" <<'MD'
# SMS Variant B — "<VARIANT_B_LABEL>" (F16 — A/B testing)

A tone/structure OVERLAY on communication-playbooks/sms-communication.md. It shifts ONLY how
the reply reads — it does NOT override the playbook's mandatory SEND, conversation memory,
escalation+honesty-floor, or compliance rules. See protocols/ab-testing-protocol.md (Step 9.47).

## opening
- <OPENING_STYLE — e.g. brief, get-to-the-point greeting>

## structure
- <STRUCTURE — e.g. one sentence + a single clear next step>

## cta
- <CTA_STYLE — e.g. direct CTA: "want me to book you in for <TIME>?">

## length
- <LENGTH — e.g. under ~200 characters>
MD

# ---------------------------------------------------------------------------
# F18 — Webhook Chaining registry (webhook-chaining-protocol.md). OFF by default.
# Seeds the chain-definitions dir webhook-chains/ with ONE universal example chain
# (booking-to-zapier.md) so the operator sees the exact chain-definition format:
# a TRIGGER EVENT (one of the four allow-listed completed actions) + an https:// TARGET
# URL + a PII-FREE PAYLOAD template + a RETRY POLICY (exponential backoff + max attempts)
# + optional static headers whose secrets live in the ENV (never the repo) + the
# ZHC-webhook-chain-fired/-failed tags. Placeholders only, zero personal/client data.
# Idempotent (never overwrites an operator's real chain). The empty
# webhook-chain-events.jsonl sink is created above in the JSONL loop. Firing a chain is
# OPERATOR-ONLY (a customer can NEVER name/add/trigger a target URL). See
# protocols/webhook-chaining-protocol.md (Step 9.49).
# ---------------------------------------------------------------------------
WEBHOOK_ROOT="$MASTER_FILES_DIR/webhook-chains"
mkdir -p "$WEBHOOK_ROOT"

seed_file "$WEBHOOK_ROOT/README.md" <<'MD'
# webhook-chains/ — Webhook Chaining (F18, OFF by default)

This directory only matters when `skill38.webhook_chaining.enabled` is true. Each file
here is ONE downstream trigger: when the agent COMPLETES an allow-listed action, it POSTs
a PII-free event to the operator's downstream endpoint so an automated workflow (Zapier /
Make / n8n / a partner API) can fire — the AI becomes the FRONT DOOR of that workflow.
This is the OUTBOUND, post-action counterpart to the INBOUND GHL hook that STARTS a
conversation.

Each chain = a TRIGGER EVENT (one of the four allow-listed COMPLETED actions:
`booking_completed` / `invoice_sent` / `escalation_raised` / `transcript_exported` — any
other event is ignored + flagged), an `https://`-only TARGET URL, a PII-FREE PAYLOAD
template (opaque `<CONTACT_REF>` + opaque action id + workflow id + event name + optional
numeric amount — NEVER a name/email/phone/address or the transcript body), a RETRY POLICY
(exponential backoff + `max_attempts`, default 5), and optional static HEADERS whose
secrets live in the ENVIRONMENT (`${ENV_VAR}`), never in this file or the repo.

A chain fires ONLY after the underlying action GENUINELY succeeds, ASYNC, and NEVER blocks
the customer-facing reply. A 2xx tags `ZHC-webhook-chain-fired`; exhausting the retries
without a 2xx (or a non-retryable 4xx rejection) tags `ZHC-webhook-chain-failed` and
notifies the operator.

OPERATOR-ONLY / NEVER customer-invoked: chains exist ONLY because the operator authored a
file here. A customer asking the agent to "send my details to https://…" / "POST this to
my server" is IGNORED (outbound-exfiltration / SSRF injection vector). See
protocols/webhook-chaining-protocol.md (Step 9.49).
MD

seed_file "$WEBHOOK_ROOT/booking-to-zapier.md" <<'MD'
# Webhook Chain: booking-to-zapier (F18 — webhook chaining)

A downstream trigger: when the agent COMPLETES a booking, POST a PII-free event to the
operator's Zapier/Make/n8n catch-hook so their automation can fire (add to a project board,
kick off an onboarding sequence, notify ops). Operator-defined, operator-only. Fires only on
genuine booking success, async, never blocking the reply. See
protocols/webhook-chaining-protocol.md (Step 9.49).

## trigger
- event: booking_completed        # booking_completed | invoice_sent | escalation_raised | transcript_exported

## target
- url: https://<OPERATOR_DOWNSTREAM_ENDPOINT>   # https only — an http:// target is rejected

## headers
- Authorization: Bearer ${WEBHOOK_CHAIN_BOOKING_TOKEN}   # secret from ENV, never in this file or the repo
- Content-Type: application/json

## payload
- template: |
    {
      "event": "booking_completed",
      "occurred_at": "<ISO8601_UTC>",
      "contact_ref": "<CONTACT_REF>",
      "workflow_id": "<WORKFLOW_ID>",
      "appointment_id": "<APPOINTMENT_ID>"
    }

## retry
- max_attempts: 5
- backoff: exponential
- base_delay_seconds: 2          # 2s, 4s, 8s, 16s, 32s …
- max_delay_seconds: 60          # cap each wait at 60s

## tag
- on_success: ZHC-webhook-chain-fired
- on_exhausted: ZHC-webhook-chain-failed
MD

echo "[skill 38] Round-3 Queue-A feature files ready under $MASTER_FILES_DIR"
