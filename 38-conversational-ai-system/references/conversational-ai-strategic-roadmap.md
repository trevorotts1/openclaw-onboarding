# Conversational AI System — Strategic Feature Roadmap

This document tracks the features built into the Convert and Flow conversational AI system, plus the remaining features under consideration.

**Audience:** the system owner and their AI agents reading this for context on what's done, what's coming, and why.

**Status legend:**
- ✅ **Implemented** — feature is live and shipped (the per-feature "shipped in vX.Y" tags below record the playbook version each feature first landed in; all ✅ features are consolidated into the current v6.0 playbook)
- 📋 **Documented** — design is finalized, ready to build
- 💡 **Under consideration** — concept is sound, design pending

**Last updated:** May 30, 2026 (aligned with v6.0 of the main playbook — the consolidated, conflict-free release that supersedes the v5.x line — and Round 3: skill 38 Features 44-52 + the System Rule + the two vertical skills 39/40 + the three QC-enforced standards)

---

# Part 1 — Completed Features

All 18 features below are now implemented as setup steps in the main playbook (`openclaw-cloudflare-tunnel-prompt.md`).

## Round 1 — original strategic features (Features 1-13)

| # | Feature | Implemented in | Step |
|---|---|---|---|
| 1 | High-volume activity warning | v5.0 | 9.5 |
| 2 | Long-conversation pause with owner review | v5.0 | 9.5 |
| 3 | Bot-detection protocol | v5.0 | 9.5 |
| 4 | Sentiment monitoring and emotional escalation | v5.0 | 9.6 |
| 5 | PII scrubbing in conversation logs | v5.0 | 9.7 |
| 6 | Quiet hours | v5.0 | 9.8 |
| 7 | Compliance keyword detection | v5.0 | 9.9 |
| 8 | Multi-language detection and matching | v5.0 | 9.10 |
| 9 | Confidence threshold escalation | v5.0 | 9.11 |
| 10 | Conversation export on customer request | v5.0 | 9.12 |
| 11 | Conversational drift detection | v5.1 | 9.13 |
| 12 | Knowledge Sources system | v5.1 | 9.14 |
| 13 | Prompt injection protection | v5.2 | 9.15 |

## Round 2 features promoted to implemented in v5.3-5.4

| # | Feature | Implemented in | Step |
|---|---|---|---|
| 19 | Multi-channel operator notifications (Slack/Discord/Email/SMS/Webhook) | v5.3 | 9.16 |
| 20 | Conversation analytics dashboard (weekly + monthly) | v5.3 | 9.17 |
| 22 | Document generation actions (quotes/proposals/contracts) | v5.3 | 9.18 |
| 24 | Smart Booking system + calendar setup wizard (supersedes Feature 23) | v5.3 | 9.19 |
| 25 | Conversation Workflow Builder (3-layer architecture in v5.4) | v5.3 / v5.4 rebuild | 9.20 |

**Notes:**
- Feature 23 (Smart Unavailability) merged into Feature 24 (Smart Booking) in v5.3
- Feature 25 (Conversation Workflow Builder) was significantly upgraded in v5.4 to a 3-layer architecture covering Layer 0 (routing check), Layer 1 (GHL side with auto-tag creation + Workflow AI prompt + verification checklist), Layer 2 (OpenClaw playbook)

---

# Part 2 — Remaining Features (ordered by priority)

Sixteen features remain unimplemented. Build order reflects revenue impact and strategic value, with the Conversational Sales AI cluster slotted FIRST since sales-driven outcomes are the primary value driver for Convert and Flow's client base.

---

# Sales AI Cluster (Features 26-31) — TOP PRIORITY

## ✅ Feature 26 — Conversational Sales AI Best Practices Module (shipped in v5.7)

**Status:** Implemented in Step 9.23 of the main playbook.

**What it does:** The sales BRAIN. Six conversation phases (Open / Discover / Present / Handle Objections / Close / Follow Up). Three discovery frameworks (BANT, MEDDIC, SPICED) — operator picks per product. Six objection patterns with response templates. Buyer signal recognition. Pricing reveal timing rules. Trial-close phrasing. Honesty floor (never fabricate, never deceive, never false urgency). Reads client-specific content from `knowledgebases/sales/`. AGENTS.md Step 1.8 activates this layer when sales context detected.

## ✅ Feature 27 — Product Knowledge Layer (subsumed by Feature 38 in v5.6)

**Status:** Implemented as the `products/` typed knowledge base inside Feature 38 (Step 9.22).

## ✅ Feature 28 — Discount Code Generation (GHL + Stripe) (shipped in v5.10)

**Status:** Implemented in Step 9.26.

## ✅ Feature 29 — Intelligent Follow-up (shipped in v5.9)

**Status:** Implemented in Step 9.25.

## ✅ Feature 30 — Stripe Integration (full) (shipped in v5.10)

**Status:** Implemented in Step 9.27.

## ✅ Feature 31 — Shopify Integration (shipped in v5.12)

**Status:** Implemented in Step 9.31.

---

# Cross-Cutting Conversational AI Features (Features 32-34)

## ✅ Feature 32 — Humanizer Skill Integration (shipped in v5.5)

**Status:** Implemented in Step 9.21. ALWAYS-ON via skill 19. Bans Tier 1 AI vocabulary (delve, tapestry, vibrant, crucial, robust, seamless, etc.). Bypassed for compliance messages and pure technical communications. Skill 38 does NOT ship its own humanizer; references skill 19.

## ✅ Feature 33 — Intelligent Playbook Routing (shipped in v5.13)

**Status:** Implemented in Step 9.33. Cosine similarity 0.3 advantage to switch. Max 3 switches per conversation.

## ✅ Feature 34 — Proactive Features Suite (shipped in v5.13)

**Status:** Implemented in Step 9.34. Seven sub-features on a single Saturday 11pm cron.

---

# System Health & Tuning Cluster (Features 35-37)

## ✅ Feature 35 — Weekly Conversation AI Tune-up (shipped in v5.12)

**Status:** Implemented in Step 9.32. Sunday 2am cron.

## ✅ Feature 36 — Monthly Comprehensive Playbook Review (shipped in v5.14)

**Status:** Implemented in Step 9.35. 1st-of-month 9am audit.

## ✅ Feature 37 — Model Version Freshness Checker (shipped in v5.14)

**Status:** Implemented in Step 9.36. Bundled into Saturday 11pm.

---

# Knowledge Architecture Cluster (Features 38-39)

## ✅ Feature 38 — Typed Knowledge Bases (shipped in v5.6)

**Status:** Implemented in Step 9.22. Four bases: business/, products/, sales/, conversations/.

## ✅ Feature 39 — Web Scraper for Knowledge Base Building (shipped in v5.8)

**Status:** Implemented in Step 9.24. Default extraction model: minimax/minimax-2.7. Cost-estimated; hard cap $5 double-confirm, $25 refused.

---

# Customer Experience Cluster (Features 40-42)

## ✅ Feature 40 — Customer Service & Support Playbooks (dual-mode) (shipped in v5.12)

**Status:** Implemented in Step 9.30.

## ✅ Feature 41 — Business-Logic Workflow Suggestions (shipped in v5.11)

**Status:** Implemented in Step 9.29.

## ✅ Feature 42 — Customer Journey Templates Library (shipped in v5.11)

**Status:** Implemented in Step 9.28. 8 business types; coach fully detailed; others stubbed.

---

# Round 3 — Conversational Depth + Verticals (Features 44-52, shipped in skill 38 v1.5.x / playbook v6.x)

Round 3 adds conversational DEPTH (a hostile message is screened before routing; a workflow
can be interrupted and resumed without losing state; a quick FAQ is answered inline; locations
are qualified before disqualifying; CRM fields are written and created mid-conversation; a
per-client website pixel feeds the agent) plus two VERTICAL skills (real estate + public-records
sourcing). Every programmatic tag any of these creates is `ZHC-` prefixed; every feature that
emits machine-readable events writes a JSONL log under the F52 data contract. Each entry below
is expanded from the in-repo protocol/skill file named as its **Source**.

## System Rule — ZHC Tag-Prefix Convention

**Status:** Shipped (Step 9.42). Every tag the agent creates **programmatically** (via the GHL
skill `create_tag` or the fallback `POST /locations/{id}/tags` — the conversation-workflows §D.1
/ workflow-AI §6 mechanism, REUSED not replaced) carries the `ZHC-` prefix, giving the operator
one unambiguous namespace for "tags the AI made." **NOT retroactive** — existing and
operator-owned tags are never renamed; the bot tag becomes `ZHC-bot-suspected` going forward
while legacy `bot-detected` is honored at read time. The companion rule: CRM custom **fields**
the agent creates carry the parallel `ZHC_` (underscore) prefix (fields and tags are different
GHL objects). MEMORY Rule 20; AGENTS.md marker `SKILL38_ZHC_TAG_PREFIX`.
**Source:** `protocols/zhc-tag-prefix-protocol.md`. QC: `scripts/qc-zhc-tag-prefix.sh`.

## ✅ Feature 50 — Aggression & Bot Detection (shipped v1.5.0)

**Status:** Shipped (Step 9.37). A two-tier hostility classifier that runs **PRE-routing** — after
the Step 0.7 compliance gate and the Step 1.4 safeguards, but BEFORE Step 1.75 workflow match and
BEFORE any reply-drafting LLM spend (AGENTS.md **Step 1.35**, marker
`STEP_1_35_AGGRESSION_PRE_ROUTING`). **Tier 1 — Tension** (multiple irritation words in one
message, a sustained 3+ message frustration streak, or `!!!`/`???`): tag `ZHC-tension-detected`,
continue the normal reply path with heightened attention, NO reroute, no operator notify. **Tier 2
— Aggression** (profanity directed AT the agent, a threat that is legal/physical/public,
ALLCAPS+profanity+direct-address, or 3+ signals in one message): tag `ZHC-aggression-detected`,
route to the aggression-handler sub-flow as an F44 detour-and-return
(`ZHC-aggression-handled-and-resumed` on return), and notify the operator. **ALL CAPS ALONE never
fires** at any sensitivity (people shout in caps). Sensitivity is operator-tunable
`lenient`/`standard`/`strict` via `openclaw.json` `skill38.aggression_detection.{enabled (default
true), sensitivity}`; severity is per-message but tension can accumulate across the log. Bot
detection (Safeguard 3) is NOT rebuilt — only its tag moves to `ZHC-bot-suspected` going forward.
Firings log to `aggression-detection-log.jsonl` (event_type `aggression_detected`/`tension_detected`)
plus a human-readable mirror `aggression-detection-log.md`. MEMORY Rule 21.
**Source:** `protocols/aggression-detection-protocol.md` + `protocols/conversational-safeguards.md`
(Safeguard 4).

## ✅ Feature 44 — Smart Playbook Switching (detour-and-return) (shipped v1.5.0)

**Status:** Shipped (Step 9.38). An always-listening interrupt layer runs parallel to the active
workflow (AGENTS.md **Step 1.42**, marker `STEP_1_42_INTERRUPTS_AND_FAQ`). On an interrupt
(operator-urgent keyword from `interrupt-triggers.md`, FAQ type, compliance redirect, F50
aggression, F49 pixel-priority) the agent **SAVES** the workflow state (`active_workflow_id`,
`active_step`, `gathered_data`, `context`), **EXECUTES** the sub-flow, then **RETURNS** to the
saved step with a soft "coming back to where we were" transition — the customer never repeats
themselves. This is **DETOUR-AND-RETURN**, DISTINCT from F33 (Step 9.33) route-and-stay: F33
switches the destination and stays; F44 takes a detour and comes back. **Max 2 levels deep**, then
escalate to a human; multiple triggers fire highest-priority-first (compliance → aggression →
operator-urgent → pixel-priority → FAQ) and queue the rest. Tags `ZHC-interrupt-handled` /
`ZHC-faq-detoured` / `ZHC-aggression-handled-and-resumed`. Toggle
`skill38.smart_playbook_switching.{enabled (default true), max_interrupt_depth (default 2)}`. Logs
to `interrupt-log.jsonl` (event_type `interrupt_detour`). MEMORY Rule 22.
**Source:** `protocols/smart-playbook-switching-protocol.md`.

## ✅ Feature 45 — Geo-Qualification (shipped v1.5.0)

**Status:** Shipped (Step 9.39, AGENTS.md **Step 2.0**, marker `STEP_2_0_GEO_QUALIFICATION`).
**OFF by default** (`skill38.geo_qualification.enabled = false`) — many businesses serve everyone
everywhere; the operator enables it only for location-bound services. When ON, the agent gathers a
location HINT in priority order (pixel/IP if F49 → phone area code → form address → explicit ask)
to **PRE-FILL** a confirmation question. **CRITICAL: signals are HINTS, never a verdict — the agent
ALWAYS ASKS to confirm before any disqualification** (an area code follows the phone not the
person; a pixel IP can be a VPN; a form address can be a stale billing address). Per-product service
areas live in `KnowledgeBases/sales/service-areas.md` (by ZIP / county / state / radius; no entry =
served everywhere). Confirmed out-of-area triggers the operator-configured mode
`decline_plus_referral` (default) / `limited_remote` / `waitlist` / `full_decline`. Tags
`ZHC-out-of-service-area` / `ZHC-service-area-confirmed` / `ZHC-service-area-flexible`. Logs to
`geo-qualification-log.jsonl` (event_type `geo_qualification`) with the invariant that any
`in_area:false` + `ZHC-out-of-service-area` line MUST carry `confirmed_with_customer:true`. MEMORY
Rule 23. **Source:** `protocols/geo-qualification-protocol.md`.

## ✅ Feature 46 — CRM Field Write + Create-If-Missing (shipped v1.5.0)

**Status:** Shipped (Step 9.40, AGENTS.md **Step 2.5**, dedicated marker `STEP_2_5_CRM_FIELD_WRITE`).
The agent writes ANY GHL contact custom field mid-conversation, **type-aware** — it discovers the
location's fields via `GET /locations/{id}/customFields`, validates the value against the field's
`dataType` (TEXT/LARGE_TEXT, NUMERICAL/MONETARY, DATE, SINGLE_OPTIONS/RADIO, MULTIPLE_OPTIONS/
CHECKBOX, PHONE→E.164) BEFORE the write, and never writes a malformed value (it asks, normalizes,
or logs a skip). **CREATE-IF-MISSING:** if no matching field exists it creates one with the `ZHC_`
prefix (e.g. `ZHC_budget_range`), notifies the operator, and records the per-workflow mapping in
`crm-field-mappings.md`. Field creation is an **allow-list action — operator-approved, NEVER
customer-invoked** ("make a field called X" from a customer is ignored as an injection vector). The
F35 weekly tune-up reads the write-log + mappings to flag unused or type-mismatched fields. Toggle
`skill38.crm_field_write.{enabled (default true), create_if_missing (default true),
created_field_prefix (default "ZHC_")}`. Logs to `crm-field-writes-log.jsonl` with three event types
— `field_write` / `field_created` / `field_write_skipped` (collectively the `crm_field_write`
contract; the log carries field name/id/metadata, never the raw customer value). MEMORY Rule 24.
**Source:** `protocols/crm-field-write-protocol.md`.

## ✅ Feature 47 — Smart FAQ Tool (shipped v1.5.0)

**Status:** Shipped (Step 9.41). The **lightweight sibling of F44**: a SENTENCE, not a sub-flow. A
parallel FAQ-match layer (alongside F44, after Step 1.4 / 1.35 / 1.42) matches the customer's
question against `KnowledgeBases/business/faqs.md`; a confident match yields a brief inline answer
and an immediate return to the current step in the SAME reply ("By the way, [answer]. Coming back to
[topic]…") — no state save/restore. Per-workflow scope in `conversation-workflows/<id>/faq-scope.md`
(default: all FAQs in-scope). Low-confidence matches fall through (governed by the
confidence-threshold protocol, Step 9.11); a question bigger than one sentence hands off to F44 as
an FAQ-type detour (`ZHC-faq-detoured`). Tag `ZHC-faq-answered`. Toggle `skill38.smart_faq.enabled`
(default true). Logs to `faq-detour-log.jsonl` (event_type `faq_answered`). MEMORY Rule 25.
**Source:** `protocols/smart-faq-tool-protocol.md`.

## ✅ Feature 49 — ZHC Pixel (shipped v1.5.2)

**Status:** Shipped (Step 9.43). Every client gets THEIR OWN private visitor-signal pixel that POSTs
anonymous-but-persistent signals (pages/time/scroll/clicks/return-visits) to THEIR OpenClaw via THEIR
existing CF tunnel (`pixel.<CLIENT_DOMAIN>` → tunnel → hook `pixel-visitor-signal`), NOT a shared
service. The pixel JS template (`templates/zhc-pixel/zhc-pixel.template.js`, first-party cookie +
persistent `visitor_id` + soft fingerprint + batched POST) is rendered per-client by
`scripts/27-render-pixel-js.sh`; the hook (`deliver:false`, bot-gate-first) routes to a NEW scoped
**Pixel Concierge** agent (allow-list `hook:pixel:*` only, registered by
`scripts/28-configure-pixel-hook.sh`; AGENTS.md **Step 1.45**, marker `STEP_1_45_PIXEL_CONCIERGE`)
with operator-configurable behavioral triggers (bot-like → silently drop with zero model spend;
pricing-page >3min → widget; 4th return → soft outreach; etc.). Identification is legally compliant —
first-party form linkage, cross-device by email, anonymous→known retroactive; the agent NEVER
fabricates identity. **Privacy is non-negotiable:** GDPR consent deferral, CCPA opt-out, Do-Not-Track
hard-stop, deletion via `delete_request`. The live CF deploy (`scripts/29-deploy-pixel-cloudflare.sh`)
is **scope-GATED** behind the precheck `scripts/26-verify-pixel-prerequisites.sh` (HALTS if Pages:Edit /
Workers Scripts:Edit / Workers Routes:Edit are missing) — the code ships, the per-client deploy is
gated. Tags `ZHC-pixel-visitor` / `ZHC-pixel-returning-visitor` / `ZHC-pixel-high-intent`; fields
`ZHC_first_visit_date` / `ZHC_total_visits` / `ZHC_pages_viewed` / `ZHC_high_intent_signal` (F46
create-if-missing). Logs to `pixel-events/YYYY-MM-DD.jsonl` (daily). Toggle `skill38.zhc_pixel.{enabled
(default true), triggers.*}`. QC: `scripts/qc-zhc-pixel.sh` (+ `qc-zhc-pixel.test.sh`).
**Source:** `protocols/zhc-pixel-protocol.md` + `templates/zhc-pixel/`.

## ✅ Feature 52 — Command Center Live Analytics Dashboard (shipped externally; consumer of the F52 contract)

**Status:** Shipped externally in the **operator's Command Center dashboard (v4.1.0)** — NOT in this
repo. It is indexed here as the **CONSUMER of the F52 JSONL data contract**: the dashboard reads the five skill-38 JSONL
sinks — `aggression-detection-log.jsonl`, `interrupt-log.jsonl`, `geo-qualification-log.jsonl`,
`crm-field-writes-log.jsonl`, `faq-detour-log.jsonl` — plus the F49 `pixel-events/YYYY-MM-DD.jsonl`.
**The data contract:** one JSON object per line, every line carrying a `timestamp` (ISO-8601 UTC), an
`event_type`, and the event's data fields, at a documented `<MASTER_FILES_DIR>` path. The sinks are
seeded idempotently by `scripts/25-seed-round3-feature-files.sh` (never overwriting operator content)
and the contract is machine-enforced by `scripts/qc-feature-logs.sh` (path + a timestamp+event_type
example documented in each protocol AND in INSTRUCTIONS.md, sink seeded by script 25).
**Source:** the JSONL schemas in each Round-3 protocol + the `INSTRUCTIONS.md` Phase-5 data-contract table.

## ✅ Skill 39 — Real Estate Playbook & Property Intelligence (shipped v1.0.0)

**Status:** Shipped as the separate top-level skill folder `39-real-estate-playbook/` — the real-estate
VERTICAL layered on Skill 38 (sibling of Skill 38, pairs with Skill 40 for pre-foreclosure sourcing).
Covers property lookup / comps / Street View (provider-gated, with an explicit MVP REAL /
PROVIDER-GATED / STUB honesty table — the agent never fabricates a property fact), buyer + seller
qualification, a showing scheduler, disclosure-compliance / fair-housing guardrails, lead routing,
open-house follow-up, and pre-foreclosure outreach (which consumes Skill 40's records). Ships its own
protocols, references (fair-housing-guardrails, property-provider-abstraction, real-estate-tags,
sales-brain-real-estate-extension, state-disclosure-matrix), an F52 real-estate events log, and the
`qc-no-fabrication.sh` + `qc-no-personal-data.sh` gates. **Source:** `39-real-estate-playbook/SKILL.md`
+ `39-real-estate-playbook/INSTRUCTIONS.md`.

## ✅ Skill 40 — ZHC Public Records Scraper (shipped v1.0.0)

**Status:** Shipped as the separate top-level skill folder `40-zhc-public-records-scraper/` — a
tiered, compliance-first public-records sourcing engine that feeds Skill 39's pre-foreclosure
outreach. **Tiered:** Tier 1 curated counties → Tier 2 vendor adapters → Tier 3 operator-buildable
config → Tier 4 honest gap (it NEVER fabricates a record). Compliance-first (a dedicated compliance
protocol), cost-capped (a cost-cap protocol + helper lib), cached (a cache protocol), with
record-type / tier routing. Ships its own protocols, per-county Tier-1 configs, Tier-2 adapter shells,
a Tier-3 config builder + target validator, the `qc-compliance.sh` + `qc-no-fabrication.sh` +
`qc-no-personal-data.sh` gates, and core-file updates (AGENTS + MEMORY + TOOLS).
**Source:** `40-zhc-public-records-scraper/SKILL.md` + `40-zhc-public-records-scraper/INSTRUCTIONS.md`.

## Round-3 QC-enforced standards

Three cross-cutting standards landed in Round 3, each codified as a reference doc and machine-enforced
by a gate wired into `scripts/11-run-qc-checklist.sh` + CI:

- **Communication-Playbook standard** — `references/communications-playbook-standard.md`, gate
  `scripts/qc-communications-playbook-standard.sh` (asserts the mandatory checklist + items (a)-(i)
  across all 8 channels: channel/persona, opening, goal, mandatory SEND via the Conversations API +
  mirror + drafting≠sending, conversation-memory read-before/append-after, escalation + honesty floor,
  quiet-hours/compliance, ZHC- tag-prefix, per-channel formatting).
- **GHL-Raw-Body-JSON standard** — `references/ghl-raw-body-json-standard.md`, gate
  `scripts/qc-ghl-raw-body-standard.sh` (codifies the FLAT 23-key body — 23 is the minimum AND the
  standard, never fewer, never nested — placeholder-free, `deliver:false`; composes `qc-23-key-bodies.sh`
  so the canonical body is proven lint-clean).
- **Notion-Client-Doc standard** — `references/notion-client-doc-standard.md`, gate
  `scripts/qc-notion-doc-standard.sh` (codifies the ordered client-doc structure 1-12: Quick-Start-first
  → URL → two-block Authorization → Content-Type split → FLAT 23-key body → tags-first + manual-fill +
  Build-with-AI-shape-only + post-build verify → Communication Playbooks → VPS-vs-Mac → how-it-works LAST
  → every-value-its-own-block → Telegram delivery → UNIVERSAL; composes
  `qc-reference-sheet.sh --require-manual-fill`).

---

# Remaining Round 2 Features (lower priority — DEFERRED, NOT in the v6.0 playbook)

## 📋 Feature 14 — Voice/Phone Integration
## 📋 Feature 15 — Proactive Outreach Campaigns
## 📋 Feature 16 — A/B Testing of Reply Variants
## 📋 Feature 17 — Customer Segmentation Awareness
## 📋 Feature 18 — Webhook Chaining (downstream triggers)
## 📋 Feature 21 — Multi-Tenant Agent Isolation

These six are explicitly NOT implemented in the v6.0 playbook and NOT in skill 38. The skill's structure
(numbered scripts, protocols/ folder, references/) leaves room for them to be added later
without restructuring.

---

# Part 3 — What's NOT on the roadmap

- Customer satisfaction surveys (low signal; sentiment monitoring covers this)
- Chatbot-style FAQ matcher (Convert and Flow snippets cover this)
- In-conversation upselling without consent (bad UX)
- Auto-translation of agent's reply (superseded by Feature 8)

---

# Implementation status (skill 38)

**Shipped in skill 38 (packages playbook v6.0 + Round 3):** All ✅ features above, including the
Round-3 wave — the ZHC tag-prefix System Rule + F44 (smart playbook switching), F45 (geo-qualification),
F46 (CRM field write + create-if-missing), F47 (smart FAQ tool), F49 (ZHC Pixel), F50 (aggression &
bot detection), and F52 (the F52 JSONL data contract this skill produces; the operator's Command Center
dashboard that consumes it ships externally at v4.1.0). Skill 38 packages 39 protocol
files (humanizer-protocol.md intentionally NOT shipped — skill 19 owns it). The two vertical skills
ship as separate top-level folders: Skill 39 (Real Estate Playbook) and Skill 40 (ZHC Public Records
Scraper).

**Pending (NOT in skill 38):** F14, F15, F16, F17, F18, F21.

---

# Portability statement

All features are platform-neutral. The protocols are markdown instruction documents. If
a client migrates from OpenClaw to another conversational AI platform, these protocols
travel intact.
