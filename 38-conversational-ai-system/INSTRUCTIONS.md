# Skill 38 — Conversational AI System: Operator Instructions

These instructions walk an operator through the conversational AI setup on a fresh OpenClaw install. The full source playbook lives at `references/v6.0-source-playbook.md` (the canonical source of truth, verbatim from the operator's playbook work). Treat that file as the canonical source of truth. This INSTRUCTIONS.md is the navigational guide — it tells you which Phase to do when and which file owns the detail.

> **Read first:**
> 1. `SKILL.md` (you read it)
> 2. `INSTALL.md` (prerequisites + scripts run order)
> 3. `references/conversational-ai-strategic-roadmap.md` (✅ shipped vs 📋 pending)
> 4. `references/v6.0-source-playbook.md` — the entire thing, in order. Pay special attention to Phase 0 Self-orientation (Steps O.1-O.7), Phase 5 (Steps 9.5-9.36 — the bulk of v5.14), and the Phase 7 Checkpoint F final verification.
> 5. `CORE_UPDATES.md` (what gets appended to workspace AGENTS.md + MEMORY.md)
>
> Per N3, read before act. Per N4, follow steps in declared order. **Do NOT skip a step because "skill X already does something similar."** The operator has reviewed the existing skills and made the call: v5.14's versions ship in full (see SKILL.md for the only intentional exception — humanizer-protocol.md is NOT shipped; skill 19 owns it).

---

## Phase 0 — Self-orientation (Steps O.1 through O.7)

Source: `references/v6.0-source-playbook.md` lines covering Phase 0 (Steps O.1-O.7).

Key automation in skill 38:

- `scripts/00-verify-prerequisites.sh` — Step O.1 prerequisite verification (skills 05, 10, 19, 29).
- `scripts/01-locate-master-files-folder.sh` — Step O.2 hardened semantic master-folder discovery. If multiple candidates exist, disambiguate; only CREATE a new folder as a last resort with operator approval.
- `scripts/18-locate-secrets-env.sh` — Step O.5 secrets/env discovery.

> **Step O.5 — Mac env note.** Unlike a VPS (Docker), which keeps env in `/docker/<project>/.env`, a **Mac**
> install stores secrets in **BOTH `~/clawd/secrets/.env` AND `~/.openclaw/.env`**. Check (and add keys to)
> BOTH — never claim a key is missing without checking both. `scripts/18-locate-secrets-env.sh` searches
> both Mac locations; see `references/GHL-INBOUND-AND-PLAYBOOKS.md` §1 for the full 4-token map.

After Phase 0: you have `MASTER_FILES_DIR` set, prerequisites verified, embeddings configured per O.6.

## Phase 1 — Build Network Plumbing (Steps 1-2)

Source: `references/v6.0-source-playbook.md` Steps 1-2 + `references/cloudflare-tunnel-troubleshooting.md` (failure-mode map).

- Step 1 — Create the Cloudflare tunnel via API (remotely-managed; per-tunnel connector token).
- Step 2 — Install cloudflared as a persistent system service (Mac: launchd via `sudo cloudflared service install <TOKEN>`. Linux: systemd post-install of apt package).
- Checkpoint B — tunnel verified end-to-end.

Skill 38 does NOT manage cloudflared installation; that's Phase 1 of the playbook itself. Skill 38 builds the BRAIN that sits behind the tunnel.

## Phase 2 — Configure OpenClaw (Steps 3 through 4)

Source: `references/v6.0-source-playbook.md` Steps 3, 3.5, 4.

- Step 3 — Configure OpenClaw's `hooks.mappings` for GHL inbound.
- Step 3.5 — Model selection wizard (REAL-TIME vs ASYNC tier). Recommend HIGHEST-REASONING available (DeepSeek V4 Pro thinking:max, Kimi 2.6+, etc. — see source playbook for the current recommendation list).
- Step 4 — End-to-end test through the public tunnel.
- Checkpoint C — OpenClaw responds to inbound webhooks.

## Phase 3 — Persist Credentials + Deliverables (Steps 5-6)

Source: `references/v6.0-source-playbook.md` Steps 5-6.

- Step 5 — Save secrets to the env file (per the v5.14 playbook block).
- Step 6 — Generate the Client Reference Sheet (Notion-first; fall back to markdown if no Notion). `scripts/21-generate-client-reference-sheet.sh` builds it AND delivers the link to the client over Telegram.
- Step 6.5 — **MANDATORY TELEGRAM DOC-DELIVERY (un-skippable, state-gated).** Every client gets their setup-doc LINK via Telegram, NO MATTER WHAT. The install is NOT complete until the client has been SENT their Quick-Start / Notion doc link via Telegram (`openclaw message send --channel telegram -t <chat>`). `scripts/22-notify-client-doc.sh` resolves the client's chat id (the `CLIENT_TELEGRAM_CHAT_ID` env first; if empty it DISCOVERS the chat by GREPPING THE TRANSCRIPTS `agents/*/sessions/*.jsonl` — the `"chat":{"id":<n>` / `telegram:direct:<n>` / `"chatId":<n>` / `"from":{"id":<n>` shapes, taking the most-frequent NON-operator id; reading `sessions.json` keys alone misses paired chats — a hard-won live-client lesson), sends the link, and records `clientDocDelivered=true` in the run-state file. If NO chat is found it FLAGS LOUDLY (stderr banner + `clientDocDelivered=false`) and exits non-zero — the install is marked incomplete; it NEVER silently skips. Machine-enforced at QC by `scripts/qc-notify-client-doc.sh`.
- Step 6.6 — **MANDATORY BACKEND SELF-TEST (un-skippable, state-gated).** After the hook is configured and BEFORE the client is told to test, the agent MUST self-test the full inbound -> reply chain BY GROUND TRUTH via `scripts/12-self-test-hook.sh`: (a) confirm readiness (hooks.enabled, a live `hooks.mappings` entry for the hook with `deliver:false` + a working model, GHL creds in `secrets/.env` incl. the location, `conversational-logs/` writable, `/healthz` 200); (b) POST a SYNTHETIC flat 23-key GHL inbound (channel sms, a throwaway test contact, the REAL Bearer token) to the OWN public hook URL; (c) verify by ground truth — hook returns 200/{ok:true}, the session ran on the configured model with NO 401/429, the agent read the conversation log, and the GHL Conversations API returned 200/201 with a messageId (creating + deleting a temporary test contact for the real send, with cleanup); (d) on any failure, FIX (creds/location/model/DND/secrets placement) and RE-TEST until green; (e) it records `selfTestPassed=true` — the install is NOT complete and the client is NOT told to test until then. Machine-enforced by `scripts/qc-self-test.sh` + the `selfTestPassed=true` assertion in `scripts/11-run-qc-checklist.sh`. Standard: `references/GHL-INBOUND-AND-PLAYBOOKS.md` §15.
- Checkpoint D — operator has copy-paste materials, the backend self-test passed by ground truth (`selfTestPassed=true`), AND the client has been sent their doc link via Telegram (`clientDocDelivered=true`). All three are required; the install is NOT complete until all three are true.

## Phase 4 — Install Agent Behavior (Steps 7-9)

Source: `references/v6.0-source-playbook.md` Steps 7, 8, 9.

- Step 7 — Install inbound message classification rules into AGENTS.md (skill 38's `scripts/05-update-agents-md.sh` handles part of this; the channel-classifying body is in the playbook).
- Step 7.5 — **Preload the client TOOLS.md with the GHL API quick-reference.** `scripts/24-update-tools-md.sh` appends the concise, verified GHL Convert-and-Flow API quick-reference (the canonical source: `references/ghl-api-quick-reference.md`) into the client's workspace **TOOLS.md** (NOT AGENTS.md — AGENTS.md = WHAT-TO-DO / behavior; TOOLS.md = WHERE-THINGS-LIVE / tools + endpoints + API reference, where request shapes belong). This puts the exact request shapes (one `/conversations/messages` endpoint with the per-channel `type` enum, calendars list/get/create + free-slots, appointment book/reschedule/cancel, invoice create + send) in the agent's CORE context so it replies FAST without digging through the dense full reference at runtime. **Idempotent** (skips if the `SKILL38: GHL_API_QUICK_REFERENCE` marker is already present), **append-only** (never overwrites operator content), backs up first, and emits `PUBLIC_HOSTNAME` only as an orientation comment — never a token, never client data. The block is **concise** (a cheat sheet, not the whole API) and machine-enforced at QC by `scripts/qc-tools-md-ghl-ref.sh`. Verified shapes per `references/GHL-INBOUND-AND-PLAYBOOKS.md` §7-9 (Version: `2021-04-15`; the 6 valid send types `SMS`/`Email`/`FB`/`IG`/`WhatsApp`/`Live_Chat`; GMB is NOT a send type) + `29-ghl-convert-and-flow/references/{conversations,calendars,payments}.md`.
- Step 8 — Scaffold the eight channel communication playbooks in Notion (SMS, Email, FB DM, FB Comments, Instagram DM, LinkedIn, Live Chat, All-in-One Chat).
- Step 9 — Set up the conversation log system. Owned by `protocols/conversation-log-protocol.md` (verbatim from playbook).

## Phase 5 — Install Advanced Features (Steps 9.5 through 9.36) — THE BULK OF v5.14

This is where the 27 protocols ship. The mapping table:

| Step | Protocol file in `protocols/` |
|---|---|
| 9.5  | `conversational-safeguards.md` (high-volume, long-conversation pause, bot-detection) |
| 9.6  | `sentiment-monitoring-protocol.md` |
| 9.7  | `pii-scrubbing-protocol.md` |
| 9.8  | `protocols/quiet-hours-protocol.md` (verbatim from playbook lines 2327-2401); AGENTS.md Step 0.5 inserted by `scripts/05-update-agents-md.sh` |
| 9.9  | `protocols/compliance-keyword-detection-protocol.md` (verbatim from playbook lines 2403-2497, FCC STOP/UNSUB + email unsubscribe + GDPR + HIPAA + FINRA/SEC blocks); AGENTS.md Step 0.7 inserted by `scripts/05-update-agents-md.sh` |
| 9.10 | `protocols/multi-language-detection-protocol.md` (verbatim from playbook lines 2499-2545); also `protocols/conversation-log-protocol.md` adds the `preferred_language` header field; also surfaced as Section 7 of `templates/agent-capabilities-playbook-template.md` |
| 9.11 | `confidence-threshold-protocol.md` |
| 9.12 | `conversation-export-protocol.md` |
| 9.13 | `drift-detection-protocol.md` |
| 9.14 | `knowledge-source-protocol.md` (older v5.1; preserved alongside v5.6's typed-knowledge-bases-protocol.md) |
| 9.15 | `prompt-injection-protection-protocol.md` |
| 9.16 | `notification-routing-protocol.md` |
| 9.17 | `conversation-analytics-protocol.md` |
| 9.18 | `document-generation-protocol.md` |
| 9.19 | `smart-booking-protocol.md` |
| 9.20 | **Conversation Playbook Builder** (the system's differentiator) — `protocols/conversation-workflows-protocol.md`. Now an explicit **3-PART build** every time: Part 1 = Workflow AI instruction set (Build-with-AI prompt + manual-build fallback + verification checklist), Part 2 = the conversation playbook (Layer 2 markdown → `conversation-workflows/<id>.md`, registered in `registry.md`), Part 3 = the brainstorm trigger (on the client's FIRST build, OFFER a personal **trigger word** — "Alexa"/"Hey Siri" style, e.g. "Playbook time!", remembered in USER.md + the registry's `trigger-word` header — then present the **"I Do / You Do"** overview so the client knows responsibilities + that a good playbook takes ~15-30 min, then the friendly proactive Q&A — NOT 50 questions — using Typed KBs + USER.md + MEMORY.md to brainstorm the PERFECT playbook around the "things to think about" (goal, audience, channel, offer/hook, tone, timing/follow-up, win action), then a concise "is this what you want?" confirmation → build → human-facing doc → register). Agent-behavior detail in `protocols/conversation-workflows-protocol.md` §I.1a/§I.1b/§I.2. Registry scaffolded by `scripts/09-install-conversation-workflows.sh`; brainstorm trigger phrases wired into AGENTS.md Step 1.85 by `scripts/05-update-agents-md.sh`. **THE TRINITY:** a GHL workflow/automation + a communications playbook + a workflow-AI prompt travel together — building one implies the other two (protocol Section "THE TRINITY"). **BINDING — per-playbook human-facing doc (un-skippable, state-gated):** when a playbook is created (the base install creates the FIRST one — appointment booking, F.7), the install is NOT complete until that playbook's human-facing doc has been created in the CLIENT's OWN account in the fallback order **Notion → Google Docs → plain-text** and its URL/path recorded in the registry's `Doc (Notion/Docs/text)` column + the Run Manifest. The installer `scripts/09-install-conversation-workflows.sh` creates + records it and RETRIES (verify/resume) any doc that fails — never silently skipped — and it is machine-enforced at QC by `scripts/qc-playbook-doc.sh` (Phase 7). This is the deliverable an agent skipped on a live client (files scaffolded locally, install reported "clean," no client doc). **Standards:** `references/communications-playbook-standard.md` (now LEADS with the hard "EVERY COMMUNICATION PLAYBOOK MUST INCLUDE ALL OF THE FOLLOWING" mandatory checklist — channel/persona, opening, goal, mandatory SEND, conversation-memory, escalation+honesty-floor, quiet-hours/compliance, ZHC- tag-prefix, per-channel formatting + the mandatory human-facing doc + Notion→Google Docs→plain-text storage; machine-enforced by `qc-communications-playbook-standard.sh` + `qc-playbook-doc.sh`); `references/workflow-ai-instructions-standard.md` (workflow-AI must-appear checklist + WHERE = Build-with-AI button in Automations + field-by-field Custom Webhook + multi-action + verification checklist); `references/ghl-raw-body-json-standard.md` (the FLAT 23-key body as THE single standard — 23 is the minimum AND the standard, never fewer, never nested; machine-enforced by `qc-ghl-raw-body-standard.sh` + `qc-23-key-bodies.sh`); and `references/notion-client-doc-standard.md` (the ordered client Quick-Start Notion doc structure — Quick-Start-first → URL → two-block Authorization → Content-Type split → FLAT 23-key body → tags-first+manual-fill+post-build VERIFY → Communication Playbooks → VPS-vs-Mac → how-it-works LAST → Telegram delivery → UNIVERSAL; machine-enforced by `qc-notion-doc-standard.sh` + `qc-reference-sheet.sh`). **Cross-refs:** Step 9.33 (router) + Step 9.34 (proactive engine) — see protocol Section K. **GHL note:** Automations have NO API/MCP — the only build path is the **Build with AI** button. |
| 9.21 | **Humanizer** — skill 19 (NOT shipped here; ALWAYS-ON via skill 38's AGENTS.md Step 2.8) |
| 9.22 | `typed-knowledge-bases-protocol.md` |
| 9.23 | `sales-best-practices-protocol.md` + `references/sales-frameworks-deep-dive.md` |
| 9.24 | `web-scraper-protocol.md` |
| 9.25 | `intelligent-followup-protocol.md` (the 10 touchpoints; first 5 in first 72 hours) |
| 9.26 | `discount-code-protocol.md` + `references/ghl-coupons-api.md` + `references/stripe-coupons-api.md` |
| 9.27 | `stripe-integration-protocol.md` + `references/stripe-webhooks-reference.md` (operator opt-in via `scripts/07-stripe-setup-wizard.sh`) |
| 9.28 | Customer Journey Templates — `templates/journey-templates/` (coach + 7 stubs + `registry.md`) |
| 9.29 | `business-logic-workflow-suggestions-protocol.md` |
| 9.30 | `customer-service-support-protocol.md` (dual-mode) |
| 9.31 | `shopify-integration-protocol.md` + `references/shopify-graphql-reference.md` (operator opt-in via `scripts/08-shopify-setup-wizard.sh`) |
| 9.32 | `weekly-tune-up-protocol.md` (Sunday 2am cron via `scripts/04-register-crons.sh`) |
| 9.33 | `intelligent-routing-protocol.md` — **Intelligent Playbook Routing**: cross-playbook TRANSITIONS (a customer who starts in one playbook gets moved to another based on responses; agent detects the shift each message, max 3 switches, soft transitions). The destinations are the playbooks built by Step 9.20. Cross-ref Step 9.20 Section K. |
| 9.34 | `proactive-suggestions-protocol.md` (Saturday 11pm cron) — **Proactive Features Suite**: sub-feature 34.1 is the pattern-based "I've seen N customers ask about X with no playbook — want one?" engine; on YES it drafts a playbook *via the Step 9.20 builder*. Cross-ref Step 9.20 Section K. |
| 9.35 | `monthly-comprehensive-review-protocol.md` (1st-of-month cron) |
| 9.36 | `model-version-freshness-protocol.md` (bundled into Saturday 11:30pm cron) |
| 9.37 | **Aggression Detection (F50)** — `aggression-detection-protocol.md`. EXTENDS the safeguards family (Step 9.5) with a two-tier hostility classifier that runs PRE-routing (AGENTS.md Step 1.35 — before workflow match, before any LLM spend). Tier 1 TENSION (multiple irritation words / 3+ message streak / `!!!`\|`???`) → tag `ZHC-tension-detected`, heighten attention, NO reroute. Tier 2 AGGRESSION (profanity-AT-agent / threats legal-physical-public / ALLCAPS+profanity+direct-address / 3+ signals in one message) → tag `ZHC-aggression-detected`, route to aggression-handler, notify operator. **ALL CAPS ALONE never fires.** Reuses bot-detection (now `ZHC-bot-suspected`), does NOT rebuild it. Toggle `skill38.aggression_detection.{enabled (default true), sensitivity (lenient\|standard\|strict, default standard)}`. Logs to `aggression-detection-log.md` + `aggression-detection-log.jsonl`. |
| 9.38 | **Smart Playbook Switching / Always-Listening Interrupts (F44)** — `smart-playbook-switching-protocol.md`. **DISTINCT from Step 9.33** (F33 = route-and-stay; **F44 = DETOUR-AND-RETURN**). An always-listening layer parallel to the active workflow; on a trigger (operator-urgent keywords, FAQ types, compliance redirects, F50 aggression, F49 pixel-priority) it SAVEs workflow state (step + gathered data + context) → EXECUTEs the sub-flow → RETURNs to the saved step with a soft transition ("Coming back to where we were…"). Max 2 levels deep then escalate. Multiple triggers: highest priority first, queue the rest. Tags `ZHC-interrupt-handled` / `ZHC-faq-detoured` / `ZHC-aggression-handled-and-resumed`. AGENTS.md Step 1.42. Toggle `skill38.smart_playbook_switching.{enabled (default true), max_interrupt_depth (default 2)}`. Logs to `interrupt-log.jsonl`. |
| 9.39 | **Geo-Qualification (F45, OFF by default)** — `geo-qualification-protocol.md`. Per-client toggle `skill38.geo_qualification.enabled` (default FALSE). Detect location priority pixel/IP (if F49) → phone area code → form address → explicit ask. **CRITICAL: signals are HINTS; ALWAYS ASK to confirm before any disqualification.** Out-of-area handling operator-configured (decline+referral / limited-remote / waitlist / full decline). Service areas per product in `KnowledgeBases/sales/service-areas.md` (ZIP/county/state/radius). Tags `ZHC-out-of-service-area` / `ZHC-service-area-confirmed` / `ZHC-service-area-flexible`. AGENTS.md Step 2.0. Logs to `geo-qualification-log.jsonl`. |
| 9.40 | **CRM Field Write + Create-If-Missing (F46)** — `crm-field-write-protocol.md`. The agent writes ANY GHL contact custom field mid-convo, type-aware (text/number/date/dropdown), discovering via `GET /locations/{locationId}/customFields`, validating before write, logging writes. CREATE-IF-MISSING: if no matching field, create via `POST /locations/{locationId}/customFields` with the `ZHC_` prefix (e.g. `ZHC_budget_range`), notify operator, record the per-workflow mapping in `crm-field-mappings.md`. Field creation is an ALLOW-LIST action — operator-approved, NEVER customer-invoked. F35 weekly tune-up reviews field usage. AGENTS.md Step 2.5. Toggle `skill38.crm_field_write.{enabled (default true), create_if_missing (default true), created_field_prefix (default "ZHC_")}`. Logs to `crm-field-writes-log.jsonl`. |
| 9.41 | **Smart FAQ Tool (F47)** — `smart-faq-protocol.md`. The LIGHTWEIGHT sibling of F44: a SENTENCE, not a sub-flow. A parallel FAQ-match layer matches `KnowledgeBases/business/faqs.md`; a confident match yields a brief inline answer then RETURNs to the current step in the SAME reply ("By the way, [answer]. Coming back to [topic]…"). Per-workflow scope in `conversation-workflows/<id>/faq-scope.md`. Bigger FAQ questions hand off to F44. Tag `ZHC-faq-answered`. Wired into AGENTS.md Step 1.42. Toggle `skill38.smart_faq.enabled` (default true). Logs to `faq-detour-log.jsonl`. |
| 9.42 | **ZHC Tag-Prefix Rule** — `zhc-tag-prefix-protocol.md`. Every tag the agent creates PROGRAMMATICALLY (via the GHL skill `create_tag` or the fallback `POST /locations/{id}/tags` — the Section D.1 / Section-6 mechanism, REUSED not replaced) carries the `ZHC-` prefix. NOT retroactive — never rename existing or operator-owned tags. Bot tag → `ZHC-bot-suspected` going forward. Companion: programmatically created CRM fields use `ZHC_` (Step 9.40). AGENTS.md `SKILL38_ZHC_TAG_PREFIX` block + MEMORY Rule 20. |
| 9.43 | **ZHC Pixel (F49) — per-client visitor-signal pixel + Pixel Concierge** — `zhc-pixel-protocol.md`. Every client gets THEIR OWN private pixel that POSTs anonymous-but-persistent visitor signals (pages/time/scroll/clicks/return-visits) to THEIR OpenClaw via THEIR existing CF tunnel (`pixel.<CLIENT_DOMAIN>` → tunnel → hook `pixel-visitor-signal`), NOT a shared service. **Components:** (1) the pixel JS template `templates/zhc-pixel/zhc-pixel.template.js` (browser-fingerprint + first-party cookie + batched POST every ~5s), rendered per-client by `scripts/26-render-pixel-js.sh` (placeholders → their tunnel URL / `<SITE_ID>` / `<AGENT_ID>`); (2) **identification** that is legally compliant — first-party form linkage (ever-filled-a-form → `visitor_id` tied to a GHL contact forever), cross-device (same email = same person), anonymous→known retroactive; NOT possible: cold-anonymous name lookup, Gmail/Facebook/social direct lookup, IP→person — the agent NEVER fabricates identity; (3) the OpenClaw hook `pixel-visitor-signal` routed to (4) the **Pixel Concierge** agent (a NEW agent with a scoped allow-list — `hook:pixel:*` only — registered by `scripts/27-configure-pixel-hook.sh`; AGENTS.md **Step 1.45** `STEP_1_45_PIXEL_CONCIERGE` block), with operator-configurable **behavioral trigger rules** (bot-like → silently drop with ZERO model spend FIRST; pricing-page >3min → chat widget; 4th return to same page → soft outreach; contact-click → preempt widget; known customer on account page → no engagement; cart abandonment → +1h email; comparison-shopping 3+ service pages → consultation offer); (5) a **scope-gated Cloudflare deploy** (`scripts/28-deploy-pixel-cloudflare.sh`: add `pixel.<CLIENT_DOMAIN>` to the existing tunnel + CF Pages project hosting the JS + deploy via API + optional edge Worker for batching/rate-limit + Workers Route) preceded by the **precheck** `scripts/25-verify-pixel-prerequisites.sh` that inspects the CF token scopes and HALTS if Pages:Edit / Workers Scripts:Edit / Workers Routes:Edit are missing (same scopes F52 needs), pointing the operator to the token-instructions Google Doc — **the code ships, the live per-client deploy is GATED**; (6) **privacy compliance** (non-negotiable): GDPR consent banner (defer until consent), CCPA opt-out, Do-Not-Track hard-stop (no fingerprint/cookie/POST if DNT=1), data deletable via `delete_request`, privacy-policy note; (7) **auto-install** that provisions when token+tunnel+domain+scopes are all present and PAUSES with an exact-needs message otherwise (no silent failure), plus a one-line `<script>` paste-snippet; (8) the **F52 JSONL data contract** at `<MASTER_FILES_DIR>/pixel-events/YYYY-MM-DD.jsonl`. Tags `ZHC-pixel-visitor` / `ZHC-pixel-returning-visitor` / `ZHC-pixel-high-intent`; fields `ZHC_first_visit_date` / `ZHC_total_visits` / `ZHC_pages_viewed` / `ZHC_high_intent_signal` (F46 create-if-missing). Toggle `skill38.zhc_pixel.{enabled (default true), triggers.*}`. New gate `scripts/qc-zhc-pixel.sh` (+ `qc-zhc-pixel.test.sh` negative test) wired into `11-run-qc-checklist.sh` + CI. **MVP/scaffold honesty:** the live CF deploy is gated on scopes; the edge Worker + nightly identity-backfill/deletion-purge are light scaffolds (see the protocol's "MVP vs production follow-ups"). |

## Phase 5 data contract — JSONL event logs (F52)

Every Round-3 Queue-A feature that emits machine-readable events writes a JSONL log (one
JSON object per line) at a documented path under `<MASTER_FILES_DIR>`. Every line carries a
`timestamp` (ISO-8601 UTC), an `event_type`, and the event's data fields. These are the
F52 data contract — downstream analytics/F52 consumes them.

| Feature | JSONL path (`<MASTER_FILES_DIR>/`) | `event_type` values | Key data fields |
|---|---|---|---|
| F50 Aggression | `aggression-detection-log.jsonl` | `tension_detected`, `aggression_detected` | `tier`, `contact_id`, `channel`, `signals[]`, `sensitivity`, `reasoning`, `action` |
| F44 Interrupts | `interrupt-log.jsonl` | `interrupt_saved`, `interrupt_executed`, `interrupt_returned` | `contact_id`, `trigger`, `priority`, `depth`, `saved_workflow`/`saved_step`/`gathered_data_keys[]` (on save), `sub_flow` (on execute), `resumed_workflow`/`resumed_step`/`soft_transition`/`tag` (on return) |
| F45 Geo | `geo-qualification-log.jsonl` | `geo_qualified` | `contact_id`, `product`, `signal_used`, `signal_value_hint`, `confirmed_by_ask` (always true on any disqualifying decision), `confirmed_location_hint`, `in_area`, `handling_mode`, `tag` |
| F46 CRM field write | `crm-field-writes-log.jsonl` | `field_write`, `field_created`, `field_write_skipped` | `contact_id`, `workflow`, `field_key`, `field_type`, `value_written` (write), `operator_notified` (create), `validated`, `reason` (skip) |
| F47 Smart FAQ | `faq-detour-log.jsonl` | `faq_answered_inline` | `contact_id`, `workflow`, `current_step`, `faq_matched`, `in_scope`, `answered_inline`, `tag` |
| F49 ZHC Pixel | `pixel-events/YYYY-MM-DD.jsonl` (daily file) | `pageview`, `scroll`, `click`, `page_hidden`, `delete_request` | `site_id`, `agent_id`, `visitor_id` (anonymous-but-persistent, NOT a person), `fingerprint` (null under DNT), `path`, `referrer`, `seconds_on_page`, `total_visits`, `first_visit_date`, `data` (`depth_pct`/`intent_hint`/`text`/`href`) |

F50 also keeps a human-readable mirror at `aggression-detection-log.md`. Each protocol file
shows a worked JSONL example; this table is the index.

## Phase 6 — Document Agent Capabilities (Step 10)

Source: `references/v6.0-source-playbook.md` Step 10.

Generates the agent-capabilities-playbook.md the operator references during day-to-day use.

## Phase 7 — Full QC + Hand-off (Step 11)

Source: `references/v6.0-source-playbook.md` Step 11 (Checkpoint F).

Full pre-handoff QC checklist. Do NOT declare done until every item passes. Refer to the playbook for the checklist contents — verbatim, no summarization, no condensation. `scripts/11-run-qc-checklist.sh` runs the machine-enforced gates, including:

- `scripts/qc-playbook-doc.sh` — every registered conversation playbook MUST have a recorded human-facing doc (Notion → Google Docs → text) in the client's account or QC FAILS.
- `scripts/qc-notify-client-doc.sh` — the **mandatory Telegram doc-delivery** step (Step 6.5) MUST be present + wired (`scripts/22-notify-client-doc.sh` exists, sends via the gateway, discovers the chat from the transcripts, LOUD-fails on no chat) or QC FAILS. At runtime the checklist ALSO asserts the run-state field `clientDocDelivered=true` — if the client was never sent their link, the install is not complete.
- `scripts/qc-tools-md-ghl-ref.sh` — the **GHL API quick-reference** preloaded into the client TOOLS.md (Step 7.5) MUST carry every listed operation (each messaging channel type SMS/Email/FB/IG/Live_Chat, calendars list/get/create, free-slots, appointment book/reschedule/cancel, send invoice) AND its required PIT scope, MUST stay within the concise size budget (no core-file bloat), and MUST contain ZERO personal/client data — or QC FAILS. At runtime the checklist ALSO asserts the `SKILL38: GHL_API_QUICK_REFERENCE` block is actually present in the installed client TOOLS.md (run `scripts/24-update-tools-md.sh` if missing).
- **DOC + BACKEND READINESS + SELF-TEST gates (completion, not just file existence) — HARD BLOCK.** The install CANNOT be marked COMPLETE (every gate exits non-zero otherwise) until ALL pass: (1) the client Notion doc was CREATED with the canonical FLAT 23-key body + Quick-Start structure + split Authorization key/value blocks + playbooks/trigger/I-Do-You-Do + VPS-vs-Mac + the "How to test your system" section (`scripts/qc-reference-sheet.sh --require-manual-fill` + `scripts/qc-23-key-bodies.sh`) AND DELIVERED via Telegram (`scripts/qc-notify-client-doc.sh` + runtime `clientDocDelivered=true`); (2) the backend is ready to RECEIVE — `hooks.mappings` live with `deliver:false`, a working `model`, `/healthz` 200; (3) the agent's own BACKEND SELF-TEST passed by ground truth (`scripts/qc-self-test.sh` + runtime `selfTestPassed=true`, Step 6.6); and (4) the skill carries NO personal/client data (`scripts/qc-no-personal-data.sh`). **Testing by the client only happens AFTER all of these pass** — never tell the client to test before the doc is delivered, the backend confirmed receiving, and the agent's self-test is green.

---

## Cron schedule shipped by skill 38

| Cron | Schedule | What it runs |
|---|---|---|
| `weekly-tune-up` | `0 2 * * 0` (Sunday 2am) | `protocols/weekly-tune-up-protocol.md` |
| `proactive-suggestions-scan` | `0 23 * * 6` (Saturday 11pm) | `protocols/proactive-suggestions-protocol.md` |
| `model-version-freshness` | `30 23 * * 6` (Saturday 11:30pm) | `protocols/model-version-freshness-protocol.md` |
| `monthly-comprehensive-review` | `0 3 1 * *` (1st of month 3am) | `protocols/monthly-comprehensive-review-protocol.md` |

Sunday 2am is intentional: it runs BEFORE Dreaming's 3am nightly pass, so the tune-up gets the freshest week of data without conflicting with consolidation.

---

## Hard rules (NON-NEGOTIABLE)

- **Honesty floor** (per `sales-best-practices-protocol.md` + `customer-service-support-protocol.md`): never fabricate, never deceive, never false urgency, never promise refunds/exceptions without operator approval.
- **Cost caps** (per `web-scraper-protocol.md`): scrapes estimated over $5 require double-confirmation; over $25 are refused.
- **Operator approval requirements** (per `model-version-freshness-protocol.md`): never auto-update primary models. Always surface, always ask, always wait for YES/NO/DEFER.
- **Allow-list actions** (numbered 1-17 in the playbook): the agent's actions are gated to this list. Adding a new action requires updating both AGENTS.md and the relevant protocol file.

## Room for future features (per the strategic roadmap)

The roadmap shows 6 features pending after v5.14 (F14 Voice, F15 Proactive Outreach Campaigns, F16 A/B Testing, F17 Segmentation, F18 Webhook Chaining, F21 Multi-Tenant Isolation). The skill's structure is designed to absorb them without restructuring:

- `scripts/` folder is numbered 00-08 with room to grow (09 voice-setup, 10 outreach-campaigns, etc.).
- `protocols/` folder lists by name, not number — new protocols slot in alphabetically without reflow.
- `references/` accommodates new deep-dives without disturbing existing ones.
- `CORE_UPDATES.md` is semver-tagged at v1.0 so future v1.1/v1.2 land naturally.

Do NOT try to implement any of the pending features inside skill 38. They are explicitly out of scope for v5.14.
