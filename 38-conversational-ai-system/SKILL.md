# Skill 38: Conversational AI System

## MANDATORY - Teach Yourself Protocol (TYP)

**Before using this skill, complete the Teach Yourself Protocol (Skill 01) on this folder.**

Required read order:
1. SKILL.md (this file)
2. INSTALL.md — one-time setup: prerequisites + the numbered install scripts (`00`–`23`) + QC linters in `scripts/`
3. INSTRUCTIONS.md — the v5.14 playbook organized by Phase 0 through Phase 7 (the operator's runtime walkthrough)
4. CORE_UPDATES.md — what gets appended to AGENTS.md + MEMORY.md
5. references/conversational-ai-strategic-roadmap.md — strategic context (what's ✅ shipped vs 📋 pending)
6. CHANGELOG.md — change history

Per N3 ("read before act"), do not skip. Per N4, follow steps in declared order.


## Governing protocol (binding for this skill and all skills in the repo)

This skill is governed by `../QC-PROTOCOL.md` (repo root) — the Sub-Agent Handoff and Mandatory QC Protocol. Every install, every PR, every multi-file change runs the 10-category QC rubric (8.5 threshold) BEFORE declaring done. Sub-agents receive full instructions (never summaries). See `QC-PROTOCOL.md` Part 5 for the sub-agent contract.

## What This Skill Is

**Skill 38 is the conversational AI BRAIN that runs on top of skill 29 (GHL Convert and Flow).** Skill 29 installs Convert and Flow and the basic GHL integration. Skill 38 adds the brain layer: sales best practices, intelligent follow-up, dual-mode customer service + support, typed knowledge bases, intelligent routing, weekly + monthly self-tuning, model version freshness checking, and the rest of the 32 protocols from v5.14 (see the SELF-COUNTS note under "What This Skill Ships").

These two skills are SIBLINGS, not duplicates. **Skill 29 is a hard prerequisite.**

## Upstream trigger — Skill 23 (AI Workforce Blueprint) hands off to this skill

When **Skill 23** builds an AI workforce that includes a **Communications, Sales, or Customer-Support**
department, its post-build closeout is REQUIRED to hand off here to scaffold the matching comms
automations. This is an ENFORCED cross-skill chain (not prose): Skill 23 tracks it via the
`commsAutomationStatus` field in its `build-state-schema.json` and re-fires a `[COMMS-AUTOMATION-RESUME]`
self-ping (in `resume-workforce-build.sh`) until this skill has registered at least the appointment-booking
starter playbook + its Build-with-AI prompt (THE TRINITY), verifiable via
`scripts/qc-trinity-registry.sh`. So when you're invoked off a `[COMMS-AUTOMATION-RESUME]` message, the
upstream is Skill 23: read its `INSTRUCTIONS.md → "Moment 3.8"`, then build the trinity here. See
`23-ai-workforce-blueprint/SKILL.md → "Cross-skill chain → Skill 38"`.

## Prerequisites (ALL required; install scripts check at runtime)

- Skill 05 — GHL Setup
- Skill 10 — GitHub Setup (latest version)
- Skill 19 — Humanizer (used ALWAYS-ON; skill 38 does NOT duplicate)
- Skill 29 — GHL Convert and Flow (Convert and Flow CONNECTED to operator's GHL location)

## What This Skill Ships

<!-- SELF-COUNTS: re-verify on EVERY version bump — see scripts/bump-version.sh "Skill 38 self-count
     re-verification" note. Counts as of v1.5.4 (Round-3 canonical reconciliation Mac ↔ VPS): protocols/=39
     (*.md — v1.5.2 added zhc-pixel-protocol.md for F49; v1.5.0 added the 6 Round-3 Queue-A CORE protocols:
     aggression-detection, smart-playbook-switching (F44 detour-and-return), geo-qualification,
     crm-field-write, smart-faq, zhc-tag-prefix), scripts/=55 (*.sh — v1.5.4 added qc-f45-f47-substance;
     v1.5.3 Round-3 reconciliation added 3:
     25-seed-round3-feature-files, qc-backend-ready, qc-feature-logs; v1.5.2 added 6 for F49:
     26-verify-pixel-prerequisites, 27-render-pixel-js, 28-configure-pixel-hook, 29-deploy-pixel-cloudflare,
     qc-zhc-pixel, qc-zhc-pixel.test; the v1.5.1 standards wave added 3 standard gates:
     qc-communications-playbook-standard, qc-ghl-raw-body-standard, qc-notion-doc-standard;
     v1.5.0 added qc-zhc-tag-prefix.sh), references/=18 (*.md — the v1.5.1 standards wave added 2:
     ghl-raw-body-json-standard.md + notion-client-doc-standard.md (communications-playbook-standard.md was
     ELEVATED in place, not added); F49 added 0 references), journey templates=8 dirs (unchanged since
     v1.4.15). Verify: ls -1 protocols/*.md scripts/*.sh references/*.md | per-dir wc -l. -->
<!-- Prior wave note (kept for history): the v1.5.1 skill38-three-qc-standards wave moved scripts 42→45 and
     references 16→18 (file count); F49 (v1.5.2) then moved scripts 45→51 and added the zhc-pixel protocol;
     v1.5.3 (Round-3 reconciliation) then moved scripts 51→54; v1.5.4 (F45/F47 deep-fix) moved scripts 54→55.
     Run: ls -1 protocols/*.md scripts/*.sh references/*.md | per-dir wc -l. -->
- 39 protocol files under `protocols/` (humanizer is intentionally NOT here — skill 19 owns it; v1.5.2 added `zhc-pixel-protocol.md` for F49)
- **8 customer journey templates** under `templates/journey-templates/` (coach + all 7 verticals fully detailed: consulting, course-creator, e-commerce, real-estate, saas, service-provider, wellness)
- **55 scripts** under `scripts/` (idempotent, OS-aware: Darwin + Linux) — the numbered install scripts `00`–`29` (v1.5.4 added `qc-f45-f47-substance`; v1.5.3 Round-3 reconciliation added `25-seed-round3-feature-files`, `qc-backend-ready`, `qc-feature-logs`; v1.5.2 F49 added `26-verify-pixel-prerequisites`, `27-render-pixel-js`, `28-configure-pixel-hook`, `29-deploy-pixel-cloudflare`, `qc-zhc-pixel`, `qc-zhc-pixel.test`) (incl. `22-notify-client-doc.sh` — the MANDATORY Telegram delivery of the client's setup-doc LINK: discovers the chat from the TRANSCRIPTS `agents/*/sessions/*.jsonl`, sends via the gateway, records `clientDocDelivered`, LOUD-fails on no chat — every client gets their link via Telegram, no matter what) plus `skill38-calendar-sync.sh`, the eight QC linters `qc-23-key-bodies.sh` (machine-enforces the 23-key GHL body rule, including the v6.0 playbook) + `qc-trinity-registry.sh` (machine-enforces THE TRINITY against both the table and bullet registry forms) + `qc-send-directive.sh` (machine-enforces the mandatory GHL send-directive on every inbound server messageTemplate — drafting != sending) + `qc-conversation-memory.sh` (machine-enforces the conversation-memory read-before/append-after steps on every inbound server messageTemplate — single-turn hook sessions remember only via the per-contact log) + `qc-playbook-doc.sh` (machine-enforces the MANDATORY per-playbook human-facing doc — Notion → Google Docs → text — recorded in the client's `registry.md`; FAILs any registered playbook with no recorded doc, exits 2 if none exist) + `qc-notify-client-doc.sh` (machine-enforces the MANDATORY Telegram doc-delivery — that `22-notify-client-doc.sh` exists, sends via the gateway, discovers the chat from the transcripts, LOUD-fails on no chat, and is wired into the binding instructions) + `qc-reference-sheet.sh` (machine-enforces that the generated client reference sheet carries the Bearer token + a copyable ```json GHL Raw Body + the hook URL, and with `--require-manual-fill` that it is BULLETPROOF: a "🚀 Quick Start" section FIRST + a full explanation/reference section AFTER it, the Authorization header split into SEPARATE key + value code blocks (each its own copy button) — and the VALUE block must be ONLY `Bearer <token>`, never a combined `Authorization: Bearer <token>` copy block — the create-tags-FIRST instruction + Settings → Tags pointer, the manual Custom-Webhook fill instructions, the POST-BUILD verification — trigger/tag-exists + custom webhook + Published-not-Draft — AND the enriched "Your Communication Playbooks" section: where playbooks are stored (conversation-workflows/ + mirrored to Notion) + the "Want another communication playbook? Just ask me!" / "Help me build a [purpose] playbook" CTA with examples + the brainstorm→create→store→matching-Workflow-AI-prompt walkthrough + the Convert-and-Flow abilities (create tags, update calendar, create/book appointments) + the explicit "connected to your Convert and Flow account … just ask" statement + the NEW-playbook creation experience: a personal trigger word ("Alexa"/"Hey Siri" style), the "I Do / You Do" process with the ~15-30-minute expectation, and the brainstorm "what to think about" prep + reassurance — AND, as of v1.4.18, the "⚙️ Things to consider when installing: VPS (Hostinger Docker) vs Mac mini" section: with `--require-manual-fill` the gate FAILs the build unless the generated doc carries BOTH the VPS points (host `/docker/<project>/.env` + `docker compose up -d --force-recreate` + container `/data/.openclaw/secrets/.env` for GHL creds + the `OPENCLAW_HOOKS_TOKEN`/hooks.token-rewrite-on-boot persistence point) AND the Mac points (provider keys in the `openclaw.json` top-level env block + `launchctl kickstart -k gui/$(id -u)/ai.openclaw.gateway`)) + `qc-config-schema-safety.sh` (machine-enforces that no install script writes a config-invalidating shape — no `agents.defaults.async/.batch`, no `cron.jobs` JSON, no jq-1.7-invalid `//= ;`, no pointer-sourcing, no hardcoded legacy skill path) + `qc-f45-f47-substance.sh` (machine-enforces the BEHAVIORAL substance of F45 geo-qualification + F47 smart FAQ from the protocol files — F47: parallel layer alongside the workflow, a SENTENCE not a sub-flow, the "By the way…Coming back to" handoff, sales-vs-ops `faq-scope.md`, `faqs.md` match, the explicit F44-vs-F47 difference, the `ZHC-faq-detoured` hand-off for bigger questions, `ZHC-faq-answered`, `faq-detour-log.jsonl`; F45: default-OFF + the per-product toggle, pixel/IP→area-code→form→ask priority, ALWAYS-confirm + the exact confirmation question + all 5 branches (here/elsewhere/vacation/moving/no-engagement=do-not-disqualify), the 4 out-of-area modes, `service-areas.md` (radius/zips/states/counties), the 3 ZHC tags, and the `geo-qualification-log.jsonl` confirmed_with_customer invariant; negative-tested), and the fixture tests `qc-trinity-registry.test.sh` (TRINITY reconciliation) + `qc-playbook-doc.test.sh` (per-playbook doc gate)
- 18 reference documents under `references/` (deep-dives + the full v6.0 source playbook + the communications-playbook & workflow-AI/Build-with-AI standards + the **Cloudflare & GoDaddy Setup Guide** from School of AI — the client-facing walk-through for the missing-CF-token halt path — + the **VPS-vs-Mac install-considerations** reference, the authoritative source for the "⚙️ Things to consider when installing: VPS (Hostinger Docker) vs Mac mini" section the client doc emits and `qc-reference-sheet.sh --require-manual-fill` enforces) — F49 adds no new reference doc (the ZHC Pixel detail lives in `protocols/zhc-pixel-protocol.md`)
- **3 QC-enforced standards (each with its own mandatory-checklist headline + machine gate):** `references/communications-playbook-standard.md` ("EVERY COMMUNICATION PLAYBOOK MUST INCLUDE ALL OF THE FOLLOWING" — channel/persona, opening, goal, mandatory SEND, conversation-memory, escalation+honesty-floor, quiet-hours/compliance, ZHC- tag-prefix, per-channel formatting; gate `scripts/qc-communications-playbook-standard.sh`); `references/ghl-raw-body-json-standard.md` ("EVERY GHL CUSTOM WEBHOOK RAW BODY MUST BE THE FULL 23-KEY FLAT JSON — 23 is the minimum AND the standard, never fewer, never nested"; codifies `references/GHL-INBOUND-AND-PLAYBOOKS.md` §0-§2; gate `scripts/qc-ghl-raw-body-standard.sh`, composes `qc-23-key-bodies.sh`); `references/notion-client-doc-standard.md` ("EVERY CLIENT NOTION SETUP DOC MUST INCLUDE ALL OF THE FOLLOWING, IN THIS ORDER" — Quick-Start-first → URL → two-block Authorization → Content-Type split → FLAT 23-key body → tags-first+manual-fill+post-build VERIFY → Communication Playbooks → VPS-vs-Mac → how-it-works LAST → every-value-its-own-block → Telegram delivery → UNIVERSAL; gate `scripts/qc-notion-doc-standard.sh`, composes `qc-reference-sheet.sh --require-manual-fill`). All three wired into `scripts/11-run-qc-checklist.sh` + CI `.github/workflows/qc-static.yml` and negative-tested.
- **AGENTS.md updates:** Steps 1.7, 1.8, 1.9, 2.8 inserted; Step 1.75 upgraded; **(v1.5.0 Round-3 Queue-A)** Step 1.35 (PRE-routing aggression scan, F50), Step 1.42 (always-listening interrupts F44 + inline FAQ F47), Step 2.0 (geo-qualification F45), Step 2.5 (CRM field write F46), and the ZHC tag-prefix behavioral note — all via marker blocks in `scripts/05-update-agents-md.sh`
- **MEMORY.md design rules 6-19** appended; **(v1.5.0)** rules 20-25 appended in a new marker block (20 ZHC tag-prefix, 21 aggression, 22 interrupts/detour-and-return, 23 geo-qualification, 24 CRM field write, 25 smart FAQ)
- **4 cron jobs registered:** Sunday 2am tune-up; Saturday 11pm proactive scan + 11:30pm model freshness; 1st-of-month comprehensive review
- **(v1.5.0 Round-3 Queue-A CORE):** 6 new protocols — `aggression-detection-protocol.md` (F50, two-tier, EXTENDS the safeguards family — does not rebuild bot-detection), `smart-playbook-switching-protocol.md` (F44, DETOUR-AND-RETURN always-listening interrupts — DISTINCT from Step 9.33 route-and-stay), `geo-qualification-protocol.md` (F45, OFF by default, signals-are-hints/always-ask), `crm-field-write-protocol.md` (F46, write any contact field + create-if-missing with `ZHC_` prefix), `smart-faq-tool-protocol.md` (F47, inline one-sentence FAQ), `zhc-tag-prefix-protocol.md` (every programmatic tag is `ZHC-` prefixed, not retroactive); INSTRUCTIONS Steps 9.37-9.42 + the F52 JSONL data-contract table; `openclaw.json` toggles under `skill38.{aggression_detection, smart_playbook_switching, geo_qualification, crm_field_write, smart_faq}`; the new QC gate `qc-zhc-tag-prefix.sh` (wired into `11-run-qc-checklist.sh` + CI)
- **(v1.5.2 F49 ZHC Pixel — flagship):** a per-client private visitor-signal pixel — `protocols/zhc-pixel-protocol.md` (INSTRUCTIONS **Step 9.43**). Every client gets THEIR OWN pixel that POSTs anonymous-but-persistent visitor signals to THEIR OpenClaw via THEIR existing CF tunnel (`pixel.<CLIENT_DOMAIN>` → hook `pixel-visitor-signal`), NOT a shared service. Ships: the pixel JS template `templates/zhc-pixel/zhc-pixel.template.js` (first-party cookie + soft fingerprint + batched POST; GDPR/CCPA/DNT/deletion built in) + the per-client generator `scripts/27-render-pixel-js.sh`; the hook + scoped **Pixel Concierge** agent (`scripts/28-configure-pixel-hook.sh`, AGENTS.md **Step 1.45** `STEP_1_45_PIXEL_CONCIERGE`) with operator-configurable behavioral trigger rules (bot-drop-first/pricing-dwell/return-visit/contact-click/cart-abandon/comparison-shop/known-customer); the scope-gated CF deploy `scripts/29-deploy-pixel-cloudflare.sh` (tunnel hostname + CF Pages + optional edge Worker + Workers Route) + the precheck `scripts/26-verify-pixel-prerequisites.sh` (HALTS if Pages:Edit / Workers Scripts:Edit / Workers Routes:Edit are missing — same scopes F52 needs — pointing to the token-instructions Google Doc; **code ships, live deploy GATED**); the F52 JSONL data contract `<MASTER_FILES_DIR>/pixel-events/YYYY-MM-DD.jsonl`; tags `ZHC-pixel-visitor`/`-returning-visitor`/`-high-intent` + fields `ZHC_first_visit_date`/`_total_visits`/`_pages_viewed`/`_high_intent_signal`; toggle `skill38.zhc_pixel.{enabled, triggers.*}`; the new QC gate `qc-zhc-pixel.sh` (+ `qc-zhc-pixel.test.sh` negative test) wired into `11-run-qc-checklist.sh` + CI. **Identification is first-party only — the agent NEVER fabricates a name; cold-anonymous/Gmail/Facebook/IP→person lookups are documented as NOT possible.** MVP/scaffold: the live per-client CF deploy is gated on scopes; the edge Worker + nightly identity-backfill/deletion-purge are light scaffolds (see the protocol's "MVP vs production follow-ups").

## What This Skill Does NOT Do

- Does NOT modify skill 17 (self-improving-agent), 18 (proactive-agent), 31 (upgraded-memory-system), 19 (humanizer), or 29 (ghl-convert-and-flow). Each runs independently.
- Does NOT implement pending roadmap features (F14 Voice, F15 Proactive Outreach Campaigns, F16 A/B Testing, F17 Segmentation, F18 Webhook Chaining, F21 Multi-Tenant Isolation).
- Does NOT auto-update primary models. Model version checks SUGGEST; operator approves.
- Does NOT generate discount codes outside per-product policy.
- Does NOT promise refunds/exceptions without operator approval (honesty floor enforced).

## When the Agent Should Invoke This Skill

After skills 05, 10, 19, 29 are installed AND the operator is ready to wire up the full conversational AI brain. Estimated install time: 60-90 minutes (per v5.14 playbook).
