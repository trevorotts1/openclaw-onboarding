## [1.4.21] - 2026-05-30 - Reply on the SAME channel the message arrived on: channel-mirroring + contactId-threaded send-directive (no hardcoded SMS, no conversationId-on-send) + conversation READ endpoints + extended QC gates

Surgical correction to how the conversational agent SENDS its reply, against the authoritative GoHighLevel
official OpenAPI `SendMessageBodyDto`. Universal, zero personal/client data. The send goes through ONE
endpoint (`POST /conversations/messages`), the reply `type` MIRRORS the inbound channel (NOT a hardcoded
SMS), and the send is threaded into the contact's conversation BY `contactId` — `conversationId` is the
READ key only, never a send-body field.

### Changed — the MANDATORY send-directive (channel-mirroring, contactId-threaded)
- `scripts/15-configure-hooks-mappings.sh` canonical SERVER-mapping `messageTemplate` (Layer 1) rewritten:
  "SEND on the SAME channel the message arrived on, do not just draft: read the inbound channel
  (`{{channel}}`) and SEND via the GHL Conversations API — `POST conversations/messages` — with `type` = the
  MIRRORED channel value (SMS→SMS, Email→Email, Facebook→FB, Instagram→IG, WhatsApp→WhatsApp,
  Live Chat→Live_Chat); do NOT hardcode SMS. Send body = `{type:<mirrored>, contactId:{{contact_id}},
  locationId:{{location_id}}, message:<reply>}` (Email also subject+html+emailFrom+emailTo). GHL threads it
  into the contact's conversation BY `contactId`." Adds the READ path for prior thread history
  (GET `conversations/search?locationId=&contactId=` → GET `conversations/{conversationId}/messages`).
  Preserves the existing drafting-is-NOT-sending clause, the do-not-end-turn-until-messageId clause, and the
  READ-before / APPEND-after conversation-log memory steps.
- The installer's FAIL-CLOSED guard now also refuses any hook whose `messageTemplate` lacks
  `SAME channel` / `do NOT hardcode SMS` / `conversations/search`.
- Same correction applied to the two reference SERVER-mapping examples
  (`references/GHL-INBOUND-AND-PLAYBOOKS.md` §4, `references/v6.0-source-playbook.md`).

### Changed — `references/ghl-api-quick-reference.md` (MESSAGING)
- MESSAGING section retitled "MIRROR the inbound channel's `type`"; adds the explicit mirror map and the
  complete `SendMessageBodyDto` enum note (`SMS`/`Email`/`FB`/`IG`/`WhatsApp`/`Live_Chat`; also valid but
  rare `RCS`/`Custom`/`TIKTOK`). GMB is **inbound-only** (not a send type — cannot reply via this endpoint);
  TikTok inbound is workflow-action-only. Send body shows `{type, contactId, locationId, message}` (NEVER
  `conversationId`). Adds a **MESSAGING (READ)** sub-table — GET `/conversations/search` (find the thread by
  contact) + GET `/conversations/<conversationId>/messages` (read history), scope `conversations.readonly`
  (added to the scopes summary). Enum already used the short codes `FB`/`IG`.
- `references/GHL-INBOUND-AND-PLAYBOOKS.md` §7-8 mirrored to the same enum + READ ops + threading note.

### Changed — `references/workflow-ai-instructions-standard.md`
- Adds a concise **Critical Design Pattern** subsection (one endpoint, mirror the inbound channel as the
  reply `type`, send by `contactId` — GHL threads automatically, `conversationId` is read-only for history)
  and a one-line threading note next to the canonical 23-key RAW BODY. **The 23-key body is UNCHANGED** (no
  key changes); the note just records that the thread is preserved by `contactId` on send and `conversationId`
  is looked up only to READ history.

### Changed — QC gates (extended + negative-tested)
- `scripts/qc-send-directive.sh` now also asserts each GHL inbound SERVER `messageTemplate` is
  channel-mirroring (references the mirrored `type` values / "same channel" / "do not hardcode" — not
  SMS-only), threads the send BY `contactId`, and references GET `conversations/search` for reads.
- `scripts/qc-tools-md-ghl-ref.sh` now also asserts the send enum uses the short codes `FB`/`IG` (and FAILS
  on a long-form `Facebook`/`Instagram`/`Webchat` presented as a valid send `type`), FAILS if
  `conversationId` appears as a send-body field, and requires the READ ops (`/conversations/search` +
  `/conversations/<conversationId>/messages`) and the `conversations.readonly` scope. CHAR_BUDGET 6000→6500
  for the legitimate new READ content (120-line guard unchanged).
- Negative-tested: each new assertion was proven to FAIL when its target is regressed (hardcoded SMS,
  dropped search read, long-form `Facebook` send type, `conversationId` in the send body, dropped
  `conversations.readonly` scope, dropped search op).

## [1.4.20] - 2026-05-30 - Preload the CLIENT TOOLS.md with a concise, verified GHL Convert-and-Flow API quick-reference (faster agent replies; core-context request shapes) + installer step + machine-enforced QC gate

The conversational agent now ships with the exact GHL request shapes in its CORE context, so it replies FAST
without digging through the dense full reference at runtime. The block goes into the client **TOOLS.md** (NOT
AGENTS.md) — AGENTS.md = WHAT-TO-DO (rules/behavior); TOOLS.md = WHERE-THINGS-LIVE (tools, endpoints, API
reference), which is where request shapes belong. Universal, zero personal/client data, machine-enforced.

### Added — `references/ghl-api-quick-reference.md` (the canonical, concise block)
- The single source of truth the installer injects verbatim. Grouped: **MESSAGING** (one
  `POST /conversations/messages` endpoint, one row per channel `type` — SMS, Email, FB, IG, Live Chat, Chat
  Widget→Live_Chat, WhatsApp — plus the explicit **All-in-One unified-inbox note** that EVERY channel flows
  through the same endpoint, and the VALID/INVALID `type` enum: GMB is NOT a send type) / **CALENDARS** (list,
  get, create, free-slots) / **APPOINTMENTS** (book, reschedule, cancel) / **INVOICES** (create + send). A
  one-line **Required PIT scopes** summary at the top: `conversations/message.write`, `calendars.readonly`,
  `calendars.write`, `calendars/events.readonly`, `calendars/events.write`, `invoices.write`. Every op carries
  method + full URL + the 3 headers + the JSON body shape (placeholder fields) + the required scope.
- **Verified, not invented.** Shapes confirmed against `references/GHL-INBOUND-AND-PLAYBOOKS.md` §7-9 and
  `29-ghl-convert-and-flow/references/{conversations,calendars,payments}.md`. Notable corrections vs. naive
  seeds: the `Version` header is **`2021-04-15`** (not `2021-07-28`); EVERY send requires **`locationId`**;
  the 6 valid send types are `SMS`/`Email`/`FB`/`IG`/`WhatsApp`/`Live_Chat` (**GMB is rejected** as a send
  type; the website Chat Widget routes through `Live_Chat` — there is no distinct widget type); Email requires
  `subject`/`html`/`emailFrom`/`emailTo`; reschedule = `PUT /calendars/events/appointments/<eventId>`, cancel
  = `DELETE /calendars/events/<eventId>`; free-slots takes epoch **milliseconds**.

### Added — `scripts/24-update-tools-md.sh` (installer step that injects the block into the client TOOLS.md)
- OS-aware target (Darwin `$HOME/clawd/TOOLS.md`, Linux `/data/clawd/TOOLS.md`; override via `$TOOLS_MD` /
  `$OPENCLAW_WORKSPACE`), mirroring `06-append-memory-rules.sh`. **Idempotent** (skips if the
  `SKILL38: GHL_API_QUICK_REFERENCE` marker is already present), **append-only** (never overwrites operator
  content), timestamped backup before any write, creates TOOLS.md if absent. Emits `$PUBLIC_HOSTNAME` ONLY as
  an orientation comment — never a token, never client data. Wired into `INSTRUCTIONS.md` as **Step 7.5**
  (Phase 4) and into the install QC checklist.

### Added — `scripts/qc-tools-md-ghl-ref.sh` (machine-enforced gate, negative-tested)
- FAILS if the block is missing any listed operation (each messaging channel type SMS/Email/FB/IG/Live_Chat —
  **row-anchored** so prose short codes can't mask a dropped channel row — plus calendars list/get/create,
  free-slots, appointment book/reschedule/cancel, send invoice) or any required scope; if it exceeds the
  concise size budget (120 lines / 6000 chars — guards against core-file bloat); or if any personal/client
  identifier appears (real email, real phone, a concrete `contactId`/`locationId`/etc. value, or a real
  client host). Wired into `scripts/11-run-qc-checklist.sh` (gate + a runtime assertion that the block is
  present in the installed client TOOLS.md) and into `.github/workflows/qc-static.yml`. Negative-tested:
  drop-operation, drop-scope, bloat, and three personal-data variants all FAIL; the shipped block PASSes
  (76 lines / 5308 chars; zero personal data).

## v1.4.19 — standardized workflow-AI output + AI backend self-test + UNIVERSAL (zero personal data)

Driven by operator feedback: the workflow-AI output was (a) not standardized (wildly different each run),
(b) too light on the GHL Build-with-AI Custom Webhook instructions, and (c) leaked personal/client data into
a UNIVERSAL skill. The GHL body stays EXACTLY 23 keys, flat (non-negotiable).

- **STANDARDIZATION (REQ 1).** `references/workflow-ai-instructions-standard.md` now opens with a hard
  "EVERY workflow-AI instruction set MUST INCLUDE ALL OF THE FOLLOWING" block (a numbered mandatory
  checklist): (1) workflow name + PUBLISH; (2) Trigger type + sub-option + filters in exact order;
  (3) Settings -> Allow Re-entry = ON (the workflow must re-fire per contact); (4) Custom Webhook — every
  field; (5) Save -> Publish toggle ON -> Save. `scripts/21-generate-client-reference-sheet.sh` and
  `templates/sms-workflow-ai-prompt-template.md` emit this EXACT structure every run, so every client gets
  the SAME experience.
- **EXHAUSTIVE BUILD-WITH-AI WEBHOOK (REQ 2).** The prompt + verification spell out every Custom Webhook
  field with the exact value: EVENT=CUSTOM; METHOD=POST; URL=the exact hook URL; AUTHORIZATION dropdown=None
  (token goes in headers); HEADERS via Add item (Authorization / Bearer <token>, then Content-Type /
  application/json) with the value box ONLY "Bearer <token>" (never the word Authorization); RAW BODY=full
  FLAT 23-key JSON; plus Settings -> Allow Re-entry = ON. Every copyable value is its own code block.
- **CONCISE 60-YEAR-OLD VERIFICATION (REQ 3).** The generator's post-build verification is now dead-simple
  and per-area: one short imperative line per check + the exact value in a COPY CODE BLOCK + a one-line
  "if you do not see it, paste this." Covers, in order: open workflow; Trigger; Allow Re-entry; URL; Headers;
  Raw Body; Save; Publish; Save.
- **CLIENT SELF-TEST SECTION (REQ 4).** The generated client doc now has a "How to test your system" section:
  Contacts -> search your name -> open your record -> text yourself -> reply on your phone -> Automations ->
  open the workflow -> Execution Logs -> every step green (especially the Custom Webhook); red = failure.
- **AI BACKEND SELF-TEST (REQ 5).** New `scripts/12-self-test-hook.sh`: after the agent configures the hook
  and BEFORE the client is told to test, the agent self-tests the full chain by ground truth — readiness
  (hooks.enabled, live mapping deliver:false + model, GHL creds + location in secrets/.env,
  conversational-logs writable, /healthz 200); POST a SYNTHETIC flat 23-key inbound (channel sms, throwaway
  test contact, real Bearer) to its OWN hook URL; verify 200/{ok:true} + configured model with no 401/429 +
  a conversation-log read + a GHL Conversations API 200/201 messageId (temp-contact create/delete + cleanup);
  fix-and-retest on failure; records `selfTestPassed=true`. Standard documented in
  `references/GHL-INBOUND-AND-PLAYBOOKS.md` §15. Statically enforced by new `scripts/qc-self-test.sh` and
  wired as a BLOCKING readiness gate (`selfTestPassed=true`) in `scripts/11-run-qc-checklist.sh`.
- **NOTION DOC HEAVILY ENFORCED (REQ 6).** The install cannot be marked COMPLETE unless the client doc was
  created (Quick Start + 23-key body + split Authorization + playbooks/trigger/I-Do-You-Do + VPS-vs-Mac +
  the How-to-test section) AND delivered via Telegram. The doc-delivery + readiness + self-test gates hard
  -block completion (non-zero exit).
- **UNIVERSAL — ALL PERSONAL/CLIENT DATA STRIPPED (REQ 7).** Every real personal/client identifier across
  the entire skill tree was genericized — real names (operator + live clients), real hostnames, the
  operator's chat id, operator email/domain, and worked-example business names -> generic placeholders
  (<CLIENT_BUSINESS_NAME>, <PUBLIC_HOSTNAME>, <HOOKS_TOKEN>, <LOCATION_ID>, <OPERATOR_TELEGRAM_CHAT_ID>,
  "the operator", "your setup admin", "a live client"). The hardcoded operator Telegram chat id default was
  removed from `scripts/21` + `scripts/22`. New gate `scripts/qc-no-personal-data.sh` FAILS if any banned
  identifier appears in the skill or in generated output (scans the tree + drives the generator offline).
- `38-conversational-ai-system/skill-version.txt`: 1.4.18 -> 1.4.19.

## [1.4.18] - 2026-05-30 - Audit + prune (phantom-file QC bug, stale counts/line-numbers, stale version pin) + new VPS-vs-Mac install-considerations section (client doc + reference doc + QC gate)

Full audit + prune of Skill 38, plus a new prominent "⚙️ Things to consider when installing: VPS (Hostinger
Docker) vs Mac mini" section in the generated client doc, mirrored to a reference doc and machine-enforced.
The 23-key FLAT GHL RAW BODY rule, the split Authorization (Key/Value) blocks, the Quick-Start-first ordering,
the "Your Communication Playbooks" section (trigger word + "I Do / You Do" + brainstorm), and the mandatory
Telegram doc-delivery are all preserved intact.

### Fixed — `scripts/11-run-qc-checklist.sh` referenced THREE files that do not ship (phantom-file FAILs)
- The install QC checklist hard-listed `protocols/qc-protocol.md`, `protocols/handoff-protocol.md`, and
  `templates/journey-template.md` as required files — **none of which exist in the skill** — so a clean
  install reported 3 spurious `[FAIL] MISSING:` lines every time. Replaced them with the files that actually
  ship: the skill's own `protocols/pre-handoff-qc-protocol.md` + the repo-root governing `../QC-PROTOCOL.md`
  (SKIP, not FAIL, when the skill is installed standalone outside the onboarding repo); and, for journey
  templates, `templates/journey-templates/registry.md` + a count assertion that all 8 per-vertical `journey.md`
  files are present (coach + 7 verticals). Also added `templates/client-reference-sheet-template.md` to the
  template existence check. The file-existence section now reports all PASS on a clean checkout.

### Fixed — stale counts + line-numbers + a stale version pin (audit/prune)
- **`SKILL.md`** — removed the stale **`(v5.14)`** version pin from the H1 title (the skill ships at 1.4.18 and
  the source playbook was long-since renamed to `v6.0-source-playbook.md`; the title pinned a number that
  contradicts both). The lineage references to the operator's v5.14 playbook work elsewhere are accurate history and
  are kept.
- **`INSTALL.md`** — corrected the install-script counts that contradicted `SKILL.md`: "24 numbered scripts …
  (27 `.sh` files total)" → **25 numbered install scripts** (`00`–`23`, noting the TWO `22-` scripts:
  `22-init-run-manifest.sh` + `22-notify-client-doc.sh`) and **36 `.sh` files total**, with the full list of
  the 10 QC linters/fixtures (the old text named only 2). Removed the stale **"8,797-line"** source-playbook
  line count (the file is now ~9,490 lines — replaced with a version-agnostic description).
- **`INSTRUCTIONS.md`** — removed the same stale **"8,797 lines"** source-playbook line count.

### Added — "⚙️ Things to consider when installing: VPS (Hostinger Docker) vs Mac mini" section
- **`scripts/21-generate-client-reference-sheet.sh`** — emits a new section into the generated client doc,
  placed AFTER the Quick Start + "Your Communication Playbooks" and BEFORE the deep Full Reference. It covers
  BOTH install targets — **VPS:** env vars in host `/docker/<project>/.env`; apply with
  `docker compose up -d --force-recreate` (plain `restart` ignores `env_file`); GHL/provider creds ALSO in
  container `/data/.openclaw/secrets/.env`; the `/hostinger/server.mjs` wrapper rewrites `hooks.token` to
  `hooks_${OPENCLAW_GATEWAY_TOKEN}` each boot UNLESS `OPENCLAW_HOOKS_TOKEN` is set in the host `.env`; the
  gateway port is often NOT 18789 (read `PORT` / `openclaw gateway status`); public hook via a `cloudflared`
  tunnel (PM2 + `pm2 save`) OR an existing Traefik `*.hstgr.cloud` route; `apt` is a brew shim (use
  `/data/linuxbrew/.linuxbrew/bin/brew`). **Mac mini:** PROVIDER keys MUST go in the `openclaw.json` TOP-LEVEL
  `env` block (the launchd service-env file does NOT carry them; `~/.openclaw/.env` alone is insufficient); GHL
  creds still in `~/.openclaw/secrets/.env`; restart via `launchctl kickstart -k gui/$(id -u)/ai.openclaw.gateway`;
  remote access via Cloudflare tunnel + Access service token (`zsh -lc` wrap); public hook via
  `sudo cloudflared service install <token>`. **Common to both:** FLAT 23-key body; conversational-logs
  node-owned; GHL creds in `secrets/.env`; `deliver:false`; Ollama Cloud `:cloud` models hard-cap `maxTokens`
  at 65536.
- **`references/vps-vs-mac-install-considerations.md` (NEW)** — the authoritative reference doc the generated
  section mirrors (references/=14 → **15**). Cross-linked from `references/communications-playbook-standard.md`
  §7 (a new MANDATORY, machine-enforced checklist item).

### Changed — QC enforces the VPS-vs-Mac section
- **`scripts/qc-reference-sheet.sh --require-manual-fill`** now ALSO FAILS the build when the generated doc is
  missing the VPS-vs-Mac section or any of its load-bearing points: the section heading; the VPS
  `/docker/<project>/.env` + `docker compose up -d --force-recreate` (plain-restart-ignores-env_file) +
  container `/data/.openclaw/secrets/.env` + `hooks.token` rewrite-on-boot + `OPENCLAW_HOOKS_TOKEN` points; the
  Mac `openclaw.json` TOP-LEVEL `env` block + `launchctl kickstart` points; the COMMON FLAT-23-key /
  node-owned-logs / `deliver:false` / 65536 points; and the AFTER-Quick-Start / BEFORE-Full-Reference ordering.
  **Negative-tested:** removing any one of these from the generated sheet FAILs the gate (six negative cases,
  all FAIL as expected); the positive (full) sheet PASSes.

### QC
- All Skill 38 CI gates pass locally: `qc-23-key-bodies.sh` (23 bodies, 0 failures), `qc-trinity-registry.test.sh`,
  `qc-send-directive.sh`, `qc-conversation-memory.sh`, `qc-playbook-doc.test.sh`, `qc-reference-sheet.sh`
  (default + `--require-manual-fill`), `qc-config-keys.sh`, `qc-notify-client-doc.sh`. `11-run-qc-checklist.sh`
  file-existence section reports all PASS on a clean checkout. Six negative tests confirm the new VPS-vs-Mac
  enforcement FAILs when its content is removed.

### Version
- **`skill-version.txt`** 1.4.17 → 1.4.18; **`SKILL.md`** SELF-COUNTS re-verified (protocols/=32, scripts/=36,
  references/=**15** — added `references/vps-vs-mac-install-considerations.md`, journeys=8). No repo-tracked
  (8-location) version file changed, so the repo version is unaffected and `scripts/bump-version.sh` is not run
  (matches the v1.4.15 / v1.4.16 / v1.4.17 precedent).

## [1.4.17] - 2026-05-29 - New-playbook creation experience: trigger word + "I Do / You Do" + brainstorm prep (agent behavior + client doc + QC)

Adds the AGENT BEHAVIOR and client-facing content for how a NEW communication playbook gets created.
Three pieces, in the agent-behavior files AND the generated client doc, and machine-enforced.

### Added — agent behavior in the playbook-CREATION flow (Step 9.20 Part 3)
- **`protocols/conversation-workflows-protocol.md`** — extended the Part 3 brainstorm flow (not duplicated):
  - **§I.1a (NEW) — personal TRIGGER WORD.** On the client's FIRST playbook build, the agent OFFERS to set a
    personal trigger word, explained like **"Alexa" / "Hey Siri"** (e.g. *"Playbook time!"*): asks for it,
    confirms it back, and **REMEMBERS it** — persists it to the client's `USER.md` AND the
    `conversation-workflows/registry.md` `trigger-word` header so future builds recognize it (never co-mingle
    clients). The standard *"Help me build a [purpose] playbook"* phrasing always still works.
  - **§I.1b (NEW) — the "I Do / You Do" process.** When a build starts the agent presents the 8-step
    YOU/AI-DO overview so the client knows responsibilities + that a good playbook takes **~15-30 minutes**
    (trigger → AI brainstorms a few Qs → YOU answer → AI drafts → YOU review → AI finalizes/stores/wires the
    Workflow AI prompt → AI wires actions → YOU approve, go live).
  - **§I.2 — brainstorm "what to think about".** The agent's JOB is to BRAINSTORM the PERFECT playbook; gives
    the client the things to think about — **goal** (book a call / recover a sale / get a review / FAQ),
    **who it's for**, the **channel(s)**, the **offer/hook**, the **tone/brand voice**, **timing & follow-up
    cadence**, and the **"win" action** (booked / replied / tagged / purchased) — with the reassurance
    *"if you're unsure, that's what I'm here to brainstorm."*
  - **§J + the 3-PART build table + Part 3 prose** — AGENTS.md Step 1.85 now also recognizes the stored
    trigger word; the table/prose reflect the trigger-word offer + "I Do / You Do".
- **`INSTRUCTIONS.md`** (Step 9.20 row) + **`references/communications-playbook-standard.md`** §6 (Build
  sequence) + **`references/workflow-ai-instructions-standard.md`** §7 — mirror the trigger-word offer, the
  "I Do / You Do" process, and the brainstorm "what to think about" so every entry point describes them the
  same way; they point at the canonical detail in §I.1a/§I.1b/§I.2.

### Added — client-facing explanation in the generated client doc
- **`scripts/21-generate-client-reference-sheet.sh`** — inside the "🗂️ Your Communication Playbooks" section
  (after Quick Start, before the deep reference), three new friendly sub-sections with emojis:
  **🔑 a personal trigger word** ("Alexa"/"Hey Siri" style, e.g. "Playbook time!"); **🤝 the "I Do / You Do"
  process ⏱️** (who does what + a good playbook takes ~15-30 minutes); and **🧠 what to think about** before
  you ask (goal/audience/channel/offer/tone/timing/win action + *"if you're unsure, that's exactly what your
  AI is here to brainstorm"*). FLAT 23-key body + Quick-Start-first ordering kept intact.

### Changed — QC enforces all three in the client doc
- **`scripts/qc-reference-sheet.sh --require-manual-fill`** now ALSO FAILS the build when the generated doc is
  missing: the **trigger-word concept** + its **"Alexa"/"Hey Siri" analogy**; the **"I Do / You Do" process**
  + the **~15-30 minute** expectation; and the brainstorm **"what to think about"** prep + its reassurance.
  Negative-tested: removing any one of these from the generated sheet FAILs the gate (six negative cases,
  all FAIL as expected); the positive (full) sheet PASSes.

### QC
- All Skill 38 CI gates pass locally: `qc-23-key-bodies.sh`, `qc-trinity-registry.test.sh`,
  `qc-send-directive.sh`, `qc-conversation-memory.sh`, `qc-playbook-doc.test.sh`, `qc-reference-sheet.sh`
  (default + `--require-manual-fill`), `qc-config-keys.sh`, `qc-notify-client-doc.sh`. Six negative tests
  confirm the new enforcement checks FAIL when their content is removed.

### Version
- **`skill-version.txt`** 1.4.16 → 1.4.17; **`SKILL.md`** SELF-COUNTS re-verified (protocols/=32, scripts/=36,
  references/=14, journeys=8 — unchanged; this release edited existing files only, added no new files) +
  the `qc-reference-sheet.sh` bullet updated. No repo-tracked (8-location) version file changed, so the repo
  version is unaffected and `scripts/bump-version.sh` is not run (matches the v1.4.15 / v1.4.16 precedent).

## [1.4.16] - 2026-05-29 - Authorization two-block bug fix + enriched "build another playbook" section + tightened QC

Two client-doc fixes driven by live pain, mirrored into the standards, and machine-enforced.

### Fixed — the Authorization header was emitted as ONE combined copy block (the second-block bug)
- **`templates/client-reference-sheet-template.md`** (rendered into the generated client doc by
  `scripts/21-generate-client-reference-sheet.sh` as the "Full Reference" body) emitted the Authorization
  header as a SINGLE combined copy block — `Authorization: Bearer <HOOKS_TOKEN>` — so a client copying that
  block pasted the whole string (including the repeated word `Authorization`) into the GHL header **Value**
  box. A GHL custom-webhook header has a separate **Key** box and **Value** box, so it is now TWO separate
  copy blocks: block 1 is exactly **`Authorization`** (paste into the **Key**/header-name box) and block 2 is
  exactly **`Bearer <HOOKS_TOKEN>`** (paste into the **Value** box) — the value block NO LONGER repeats
  `Authorization:`. Content-Type was verified already split correctly (block 1 `Content-Type`, block 2
  `application/json`). The click-by-click step (Row 1 / Row 2) was updated to match. The Quick-Start LEAD
  block in script 21 was already correct; this fix closes the gap in the template-rendered Full Reference.
  - **Before:** ` ```\nAuthorization: Bearer <HOOKS_TOKEN>\n``` `  →  **After:** ` ```\nAuthorization\n``` ` (Key) + ` ```\nBearer <HOOKS_TOKEN>\n``` ` (Value)

### Changed — enriched the "Your Communication Playbooks" section (teach the client to build MORE)
- **`scripts/21-generate-client-reference-sheet.sh`** — the "🗂️ Your Communication Playbooks" section
  (after the Quick Start, before the deep reference) now teaches the client how the AI helps them build
  ADDITIONAL communication playbooks (friendlier tone, more emojis 💬🚀🛠️📅🏷️✅): a **"Want another
  communication playbook? Just ask me!"** CTA with a concrete copyable example (*"Help me build a missed-call
  follow-up playbook"*) plus more examples (appointment-reminder, lead-nurture, review-request); a walkthrough
  of WHAT THE AI WILL DO — (1) brainstorm it with you using known business context (not a 50-question
  interrogation), (2) create the playbook, (3) store it (master-files `conversation-workflows/` folder,
  mirrored to Notion), (4) help create the matching **Workflow AI prompt** wired to **YOUR** Convert and Flow
  (GoHighLevel) account, (5) and that the AI can take real actions in Convert and Flow on the client's
  behalf — **create tags 🏷️, update the calendar 📅, create/book appointments 🗓️**; and the explicit
  *"You have an AI that is connected to your Convert and Flow account and can do these things for you — just
  ask."* Kept the FLAT 23-key body + Quick-Start-first ordering intact.

### Changed — tightened the QC gate to enforce both
- **`scripts/qc-reference-sheet.sh --require-manual-fill`** now ALSO FAILS the build when: (a) any copy line is
  a combined `Authorization: Bearer <token>` block (the second block must be ONLY `Bearer <token>` and must
  NOT repeat the word `Authorization`); and (b) the doc is missing the enriched playbook facts — the
  "just ask me / Help me build a [purpose] playbook" CTA, at least one of the additional examples
  (missed-call/appointment-reminder/lead-nurture/review-request), the where-stored fact (`conversation-workflows/`
  + mirrored to Notion), the matching Workflow AI prompt wired to the client's Convert and Flow account, the
  Convert-and-Flow abilities (create **tags**, update the **calendar**, create/book **appointments**), and the
  explicit "connected to your Convert and Flow account … just ask" statement. Both new checks are
  negative-tested (a doc with a combined Authorization block FAILs; a doc missing the playbook content FAILs).

### Standards mirrored
- **`references/communications-playbook-standard.md`** §7 now mandates the Authorization Key/Value two-block
  split (value = ONLY `Bearer <token>`, never combined) + the same split for Content-Type; §9 now spells out
  the enriched "Want another communication playbook? Just ask me!" section (CTA + examples + brainstorm/create/
  store/Workflow-AI-prompt walkthrough + Convert-and-Flow abilities + the explicit "connected … just ask"
  statement) and the gate that enforces it.
- **`references/workflow-ai-instructions-standard.md`** §3 reinforces that the Authorization **Value** box is
  ONLY `Bearer <HOOKS_TOKEN>` (not `Authorization: Bearer …`) and the Content-Type Value box is ONLY
  `application/json`; §7 mirrors the enriched playbook section.

### QC
- All Skill 38 CI gates pass locally: `qc-23-key-bodies.sh`, `qc-trinity-registry.test.sh`,
  `qc-send-directive.sh`, `qc-conversation-memory.sh`, `qc-playbook-doc.test.sh`, `qc-reference-sheet.sh`
  (default + `--require-manual-fill`), `qc-config-keys.sh`, `qc-notify-client-doc.sh`. Negative tests
  confirm the two new enforcement checks FAIL when their content is missing.

### Version
- **`skill-version.txt`** 1.4.15 → 1.4.16; **`SKILL.md`** SELF-COUNTS re-verified (protocols/=32, scripts/=36,
  references/=14, journeys=8 — unchanged; no new files added). No repo-tracked (8-location) version file
  changed, so the repo version is unaffected and `scripts/bump-version.sh` is not run (matches the v1.4.15
  precedent).

## [1.4.15] - 2026-05-29 - Mandatory Telegram doc-delivery + Communication Playbooks location section + readiness gates

Three belt-and-suspenders + machine-enforced hardenings driven by repeated live-client pain.

### Added — MANDATORY Telegram delivery of the client doc (un-skippable, state-gated)
- **`scripts/22-notify-client-doc.sh` (NEW).** Every client gets their setup-doc LINK via Telegram, NO
  MATTER WHAT — the install is not complete until the client has been SENT their Quick-Start / Notion doc
  link via `openclaw message send --channel telegram`. The script (a) resolves the client's chat id —
  `CLIENT_TELEGRAM_CHAT_ID` first, else DISCOVERS it by GREPPING THE TRANSCRIPTS `agents/*/sessions/*.jsonl`
  for the four shapes (`"chat":{"id":<n>`, `telegram:direct:<n>`, `"chatId":<n>`, `"from":{"id":<n>`) and
  taking the most-frequent NON-operator id (a hard-won live-client lesson — `sessions.json` keys alone miss paired
  chats); (b) sends the link via the gateway (never `api.telegram.org`); (c) on no chat FLAGS LOUDLY
  (stderr banner + `clientDocDelivered=false` in the run-state) and exits non-zero — NEVER silently skips.
  On success it records `clientDocDelivered=true` + chat id + link.
- **`scripts/qc-notify-client-doc.sh` (NEW QC gate).** Statically asserts 22-notify-client-doc.sh exists,
  parses, sends via the gateway (not curl to telegram), discovers from the transcripts (all four shapes,
  most-frequent non-operator), LOUD-fails on no chat, and is wired into INSTRUCTIONS.md + the v6.0 playbook
  + the comms standard. Wired into `scripts/11-run-qc-checklist.sh` AND CI `.github/workflows/qc-static.yml`.
- **Binding install step.** INSTRUCTIONS.md gains **Step 6.5**; `references/v6.0-source-playbook.md` gains a
  binding "Step 6.5 — deliver the doc LINK to the client via Telegram" section + Checkpoint D / Step 11 QC
  items; `references/communications-playbook-standard.md` gains §8. The pre-handoff checklist
  (`11-run-qc-checklist.sh`) asserts the run-state field `clientDocDelivered=true` at runtime.

### Added — DOC + BACKEND READINESS as completion gates (testing happens only after BOTH pass)
- **`scripts/11-run-qc-checklist.sh`** gains a backend-ready check: a live `hooks.mappings` entry (matched
  to `HOOK_NAME`, else any agent mapping) with `deliver:false` and a working `model`, AND `/healthz`
  returns 200 (public `PUBLIC_HOSTNAME` or localhost). The doc-structure side is already gated
  (`qc-reference-sheet.sh --require-manual-fill` + `qc-23-key-bodies.sh` assert the FLAT 23-key body +
  Quick-Start). v6.0 playbook Step 11 gains a "DOC + BACKEND READINESS" block: never test inbound before
  the doc is delivered AND the backend is confirmed receiving.

### Added — "YOUR COMMUNICATION PLAYBOOKS" section in the generated client doc
- **`scripts/21-generate-client-reference-sheet.sh`** now emits a prominent **"🗂️ Your Communication
  Playbooks"** section AFTER the Quick Start and BEFORE the deep Full Reference. It answers the client's
  first-test question — "where are my workflows / communication playbooks?" — with: WHERE they live (the
  `conversation-workflows/` master-files folder + human-facing copies in Notion → Google Docs → text), and
  in BIG BOLD **"⭐ Want a NEW communications playbook? Start here:"** the steps (just tell your AI
  "help me build a [purpose] playbook"; it brainstorms with you and builds all 3 parts — the workflow-AI
  prompt + the conversation playbook + the GHL automation — then documents + registers it).
- **`scripts/qc-reference-sheet.sh --require-manual-fill`** now also FAILS unless the generated doc carries
  the "Communication Playbooks" heading, the `conversation-workflows` + Notion location facts, the "Want a
  NEW communications playbook" CTA, the "help me build a [purpose] playbook" instruction, the brainstorm
  explanation, and the 3-part trinity note — and unless the section sits after Quick Start and before the
  deep reference. Negative-tested. Standardized in `communications-playbook-standard.md` §9 +
  `workflow-ai-instructions-standard.md` §7.

### Version
- **`skill-version.txt`** 1.4.14 → 1.4.15; **`SKILL.md`** SELF-COUNTS re-verified (protocols/=32,
  scripts/=34 → **36** (+`22-notify-client-doc.sh`, +`qc-notify-client-doc.sh`), references/=14, journeys=8)
  + the scripts bullet updated (eight QC linters now). No repo-tracked (8-location) version file changed, so
  the repo version is unaffected and `scripts/bump-version.sh` is not run.

## [1.4.14] - 2026-05-29 - Bulletproof Quick-Start + workflow-AI (where-to-paste, tag-first, post-build verify)

Belt-and-suspenders hardening of the client reference-sheet generator, the workflow-AI standard/templates,
and the QC gates — driven by live client pain (a live client + a live client). The reference sheet now leads with an
actionable Quick Start AND keeps a full explanation, splits every copyable value into its own copy block,
teaches create-the-tag-FIRST, and adds a post-build verification that catches the blank-tag trigger bug.

### Changed — `scripts/21-generate-client-reference-sheet.sh` (the generated reference sheet, now bulletproof)
- **Quick Start FIRST, then full explanation (BOTH).** The sheet now LEADS with a section literally named
  **"🚀 Quick Start"** (the actionable copy-paste items, in order) and then, AFTER it, a complete
  **"📖 Full Reference & Explanation"** section (how the inbound pipe works, what each piece is, and
  troubleshooting). Quick Start does NOT replace the explanation — both are present.
- **Every copyable value gets its OWN fenced code block (its own copy button).** The Authorization header is
  now TWO separate code blocks — one containing exactly `Authorization` (the key) and one containing exactly
  `Bearer <token>` (the value), NEVER combined. The Content-Type header is likewise split into `Content-Type`
  and `application/json`. (50+ clients copy each field individually.) The Webhook URL and the FLAT 23-key
  Raw Body JSON each keep their own block.
- **Create-tags-FIRST (new Section 0).** If the workflow uses any tag (a trigger/If-Else filter or an
  Add-Tag action), the sheet directs the client to CREATE the tag(s) FIRST (via the agent's GHL skill, or in
  GHL **Settings → Tags**) so the filter references a REAL existing tag — and tells them WHERE to check
  (Settings → Tags) and WHAT they should see.
- **Post-build VERIFICATION (new Section 5).** After Build-with-AI runs, the sheet walks the client through
  three checks, each stating WHERE to go, WHAT they should SEE, and WHAT to put if missing/wrong:
  TRIGGER (incl. the **blank/non-existent-tag-in-a-"does not contain"-filter** bug from a live client), CUSTOM
  WEBHOOK (Method=POST, URL, both headers, all 23 Raw-Body keys — Build-with-AI does NOT fill these), and
  PUBLISH (Published, not Draft).
- **Manual Custom-Webhook fill (Section 4)** now names each GHL UI box precisely (Method dropdown / URL box /
  HEADERS → Add item → Key box + Value box, twice / Content-Type field / RAW BODY box).

### Changed — workflow-AI standard + templates (explicit + bulletproof)
- **`references/workflow-ai-instructions-standard.md`** — Custom-Webhook field-by-field now names the exact
  GHL UI boxes (Method dropdown, URL box, Key/Value boxes via "Add item", RAW BODY box); Section 6 rewritten
  as **"create the tag FIRST, then use it"** with the agent path + the client path (where to check:
  Settings → Tags, what they should see); Section 4 verification gains the trigger tag-existence check
  (WHERE/SEE/PUT) calling out the blank-tag "does not contain" bug.
- **`templates/sms-workflow-ai-prompt-template.md`** — manual-fill steps name the precise GHL boxes.
- **`templates/workflow-verification-checklist-template.md`** — Trigger section gains a tag-EXISTS check
  (cross-check Settings → Tags; the blank-tag "does not contain" bug + the fix).

### Changed — QC enforcement (machine-enforced, BASH)
- **`scripts/qc-reference-sheet.sh --require-manual-fill`** now additionally FAILS unless the generated sheet
  contains: a literal **"🚀 Quick Start"** section, a complete explanation/reference section AFTER it, the
  SEPARATE `Authorization` key code block + `Bearer <token>` value code block (detected inside fences via
  awk), the create-tags-FIRST instruction + a `Settings → Tags` pointer, and the POST-BUILD verification
  section (trigger tag-existence + Published-not-Draft) — on top of the existing Bearer/```json/hook-URL/
  manual-fill/lead-order checks. Negative-tested: removing any marker fails the gate.
- **`.github/workflows/qc-static.yml`** — the manual-fill CI step is updated to describe + enforce the
  bulletproof set (it already invoked `--require-manual-fill`).

### Version
- **`skill-version.txt`** 1.4.13 → 1.4.14; **`SKILL.md`** SELF-COUNTS note re-verified (protocols/=32,
  scripts/=34, references/=14, journeys=8 — unchanged, no files added/removed) + qc-reference-sheet ship line
  updated. No repo-tracked version file changed, so the repo version (8-location) is unaffected and
  `scripts/bump-version.sh` is not run.

## [1.4.13] - 2026-05-29 - v1.4.11 install-script bug fixes (config-validity) + MANDATORY manual Custom-Webhook fill instructions

Two classes of fix, both verified against a live openclaw 2026.5.27 box.

### Fixed — install-script bugs that broke/degraded fresh installs (PART A)
- **`scripts/15-configure-hooks-mappings.sh` (Model Wizard + hooks merge):**
  - No longer writes `agents.defaults.async` / `agents.defaults.batch` — those keys are REJECTED by the
    2026.5.27 `.strict()` schema, so `openclaw config validate` FAILED on a fresh install. The real-time
    model is the only one written to `openclaw.json` (on the main agent's `agents.list[].model`); the
    async + batch tier CHOICES are persisted to `SECRETS_ENV_FILE` as `ASYNC_MODEL`/`BATCH_MODEL` (read by
    `04-register-crons.sh`).
  - The hooks merge `jq` no longer uses the top-level `.hooks //= {};` form, which jq 1.7+ REJECTS
    (`syntax error, unexpected ';'`). Rewritten to the valid `.hooks = (.hooks // {}) | …` form (same
    semantics). The corrected SERVER `messageTemplate` (read-before + append-after + mandatory SEND) is
    preserved and still validates clean.
  - The inline `system-health-heartbeat` cron is now registered via `openclaw cron add` (not the invalid
    `cron.jobs` JSON block).
- **`scripts/04-register-crons.sh`:** rewritten to register all 5 crons via `openclaw cron add` (gateway
  cron store), idempotent by name via `openclaw cron list`. The legacy `cron.jobs` JSON config block does
  NOT validate on 2026.5.27 — the script no longer touches `openclaw.json` at all. Reads `BATCH_MODEL` from
  `SECRETS_ENV_FILE` (set by the Model Wizard).
- **`scripts/02-create-knowledgebases.sh` + `scripts/03-create-journey-templates.sh`:** stop `source`-ing
  the master-files POINTER file. The pointer holds a bare PATH (a directory), so `. <pointer>` errored
  "Is a directory". Now READ it with `head -n1` into `MASTER_FILES_DIR`.
- **`scripts/12-scaffold-channel-playbooks.sh`:** resolves the skill root DYNAMICALLY from the script's own
  location instead of hardcoding the legacy `~/clawd/skills/38-openclaw-cloudflare-tunnel` path (which no
  longer exists). Same dynamic-resolution fix applied to `scripts/11-run-qc-checklist.sh`, whose expected
  cron-name list was also corrected to the names `04-register-crons.sh` actually registers.

### Added
- **`scripts/qc-config-keys.sh`** (pure BASH) — new machine-enforced QC gate that scans `scripts/*.sh` and
  FAILs (exit 1) if any install script would invalidate the 2026.5.27 config or trip the known install
  bugs: `agents.defaults.async/.batch` writes, a `cron.jobs` JSON config block, the jq-1.7-invalid
  `//= … ;` form, sourcing the master-files pointer, or a hardcoded legacy skill path. Wired into
  `scripts/11-run-qc-checklist.sh` and CI `.github/workflows/qc-static.yml`.
- **`scripts/qc-reference-sheet.sh --require-manual-fill`** — new flag that additionally enforces the
  manual Custom-Webhook fill instructions and the lead-with-values ordering on the generated reference
  sheet (CI runs both default + `--require-manual-fill`).

### Fixed — MANDATORY manual Custom-Webhook fill (PART B)
GHL's "Build with AI" only builds the workflow SHAPE (the trigger + an EMPTY Custom Webhook action); it
does NOT reliably populate the URL, the Authorization/Bearer header, the Content-Type header, or the Raw
Body JSON. The client MUST open the Custom Webhook action and paste those values by hand. Made explicit and
mandatory:
- **`scripts/21-generate-client-reference-sheet.sh`** — the generated reference sheet now LEADS with the
  copy-paste values in this exact order: (1) Webhook URL, (2) Authorization/Bearer token (revealed real
  value), (3) Raw Body JSON (fenced `json`, flat 23-key), (4) the manual Custom-Webhook fill steps
  ("Build with AI will not fill it — do it yourself"), (5) the Workflow-AI prompt. All explanation/
  reference now follows AFTER those values.
- **`references/workflow-ai-instructions-standard.md`**, **`templates/sms-workflow-ai-prompt-template.md`**,
  **`templates/workflow-verification-checklist-template.md`** — each gains a prominent "AFTER Build-with-AI
  runs, you MUST open the Custom Webhook action and MANUALLY enter Method/URL/Headers/Raw Body, then
  Save + Publish — Build with AI will NOT fill these for you; verify every field is non-empty before
  publishing" section.
- **`references/communications-playbook-standard.md`** — notes the manual-fill step is MANDATORY in every
  client doc, machine-enforced by `qc-reference-sheet.sh --require-manual-fill`.

### Changed
- **`.github/workflows/qc-static.yml`** — adds CI steps for `qc-config-keys.sh` and for
  `qc-reference-sheet.sh --require-manual-fill`.
- **`SKILL.md`** — self-counts updated (scripts 33 → 34; new `qc-config-keys.sh`); QC-linter description
  extended.

## [1.4.12] - 2026-05-29 - client reference sheet MUST include the bearer token + a copyable GHL Raw Body JSON (machine-enforced)

Root cause fixed: on a live client, the generated Client Reference Sheet
(`scripts/21-generate-client-reference-sheet.sh`) had NEITHER the hooks Bearer token NOR the GHL Custom
Webhook Raw Body as a copyable ` ```json ` fenced code block. The client opened their reference doc and
the token was simply missing, and there was no JSON to copy into GHL's Build-with-AI — which stranded the
client. The reference sheet's content came entirely from the template wrapper, where the bearer token
appeared only inside `[code block, copy button]` pseudo-markers (not a real fence) and the per-channel
Raw Body JSONs lived in a separate Part 3 documentation section, not in the reference sheet body. The
sheet MUST contain both, ALWAYS — now enforced, not left to the template.

### Fixed
- **`scripts/21-generate-client-reference-sheet.sh`** now APPENDS two authoritative, always-present
  sections to the rendered reference sheet (so they survive regardless of template wrapping):
  - **Authorization Header / Bearer Token** — resolves the real `hooks.token` in priority order
    `HOOKS_TOKEN` → `OPENCLAW_HOOKS_TOKEN` → `hooks.token` read from `openclaw.json`
    (`$OPENCLAW_CONFIG`, `~/.openclaw/openclaw.json`, `/data/.openclaw/openclaw.json`), and renders it as
    `Authorization: Bearer <token>` inside a real fenced code block. If the token cannot be resolved it
    emits a clearly-marked `REPLACE_ME__…` PLACEHOLDER and WARNs to stderr (never silently omits it).
  - **GHL Custom Webhook — Raw Body** — the canonical FLAT 23-key body as a copyable ` ```json ` fenced
    code block, plus the Method (POST), the hook URL (`https://<host>/hooks/<id>`), and Content-Type
    (`application/json`) as copyable code blocks. Body stays placeholder-free in `messageTemplate`, not
    nested, not stripped below 23 keys.

### Added
- **`scripts/qc-reference-sheet.sh`** (pure BASH, mirrors the other `qc-*.sh`) — new machine-enforced QC
  gate. Default mode drives `21-generate-client-reference-sheet.sh` in an offline sandbox (strips
  `openclaw` from PATH → Layer-3 markdown, no network/Telegram) and FAILs (exit 1) if the rendered sheet
  lacks the word `Bearer`, a line-anchored ` ```json ` fence, or a hook URL; `--sheet FILE` statically
  checks an existing sheet; exit 2 (never a blind PASS) if no sheet can be produced/located. BASH (not
  Python) so it respects qc-static's ban on claude-/anthropic strings in `.py` under 22/23.

### Changed
- **`scripts/11-run-qc-checklist.sh`** — wires `qc-reference-sheet.sh` in as a mechanical gate (and adds
  it to the script-existence list).
- **`.github/workflows/qc-static.yml`** — new CI step "Skill 38 client reference sheet copy-paste
  artifacts" runs `qc-reference-sheet.sh` on every push/PR so a template/script regression that drops the
  bearer token or the copyable Raw Body JSON fails the build.
- **`references/communications-playbook-standard.md`** — new section documenting that the bearer token +
  copyable Raw Body JSON are MANDATORY in every client reference sheet, machine-enforced by
  `qc-reference-sheet.sh`.

## [1.4.11] - 2026-05-29 - enforce the per-playbook human-facing doc deliverable (Notion → Google Docs → text) so a created playbook never ships without a client-facing reference

Root cause fixed: when a communications/conversation playbook is created (the base install creates the FIRST
one — appointment booking, F.7), the agent is ALSO supposed to create a human-facing copy of that playbook in
the CLIENT's OWN account, in the fallback order (1) the client's Notion, (2) if no Notion → Google Docs, (3) if
neither → a plain-text doc the client can access. On a recent client this step was SKIPPED — the agent
scaffolded the playbook files locally and reported the install "clean" but never created the client's Notion
doc, leaving the customer stranded with no human-facing reference of what was set up. The cause: the Notion-doc
deliverable was PROSE in the standard (`references/communications-playbook-standard.md` §4 + the protocol §I.3
step 4), not an ENFORCED gate, so the agent skipped it. "AUTOMATIC NEXT STEP" prose is NOT enforcement — it
needs a recorded state field + a verify/resume gate + a QC check, exactly like the send-directive
(`qc-send-directive.sh`) and conversation-memory (`qc-conversation-memory.sh`) gates. The per-playbook
human-facing doc is now enforced the same way, in four changes, not left optional.

### The canonical rule
Every conversation playbook registered in `<MASTER_FILES_DIR>/conversation-workflows/registry.md` MUST carry a
recorded human-facing doc — a Notion URL, a Google Docs URL, or a `.md`/`.txt` path the client can reach —
created in the client's OWN account in the fallback order Notion → Google Docs → plain-text. The reference is
recorded in the registry's new `Doc (Notion/Docs/text)` column (TABLE form) or a `[doc: …]` tail (legacy BULLET
form) and in the Run Manifest. Never co-mingle clients — always the client's own workspace.

### Added
- **CHANGE 3 — machine-enforced QC gate.** New `scripts/qc-playbook-doc.sh` (bash; mirrors
  `qc-trinity-registry.sh`) reads the client's installed `conversation-workflows/registry.md` and FAILs
  (exit 1) any registered playbook (table OR bullet form) whose doc reference is empty / `n/a` / a placeholder,
  PASSes (exit 0) when every playbook has a recorded Notion/Docs/text doc, exits 2 (NOT a blind PASS) when no
  playbooks exist, and exits 3 when no conversation-workflows folder is found. It rejects the Layer-2 playbook
  file itself and the reserved companion files (`--build-with-ai-prompt.md`, `--verification-checklist.md`,
  `--ghl-side.md`) as "the doc," and catches an on-disk-but-unregistered playbook (no doc can be recorded for
  it). New `scripts/qc-playbook-doc.test.sh` proves all of this with fixtures. Wired into BOTH
  `scripts/11-run-qc-checklist.sh` (pre-handoff QC; SKIP on exit 2/3 = nothing installed yet, FAIL on exit 1)
  AND `.github/workflows/qc-static.yml` (CI runs the fixture test on every push/PR). BASH (with an inline
  python core) so it does not trip the qc-static ban on claude-/anthropic strings in `.py` under Skills 22/23.

### Changed
- **CHANGE 1 — binding, state-gated install step.** `INSTRUCTIONS.md` (Step 9.20 + Phase 7),
  `references/v6.0-source-playbook.md` F.7 (the base SMS automation that creates the first playbook) + §H Run
  Manifest, and `protocols/conversation-workflows-protocol.md` §F/§H/§I.3/§J now state that the install is NOT
  complete until a created playbook's human-facing doc has been created in the client's account (Notion →
  Google Docs → plain-text) and its URL/path recorded in the registry + Run Manifest. An incomplete doc is
  retried (verify/resume), not silently skipped.
- **CHANGE 2 — installer action.** `scripts/09-install-conversation-workflows.sh` now adds the new
  `Doc (Notion/Docs/text)` column to the registry it scaffolds, and runs a verify/resume loop over every
  on-disk playbook: for any playbook with no recorded doc it creates one (Notion subpage under the client's
  designated parent page via `NOTION_API_KEY` + `NOTION_PARENT_PAGE_ID`/`NOTION_PARENT_SEARCH` → Google Docs
  via the Google Workspace helper → a plain-text `.md` in `<MASTER_FILES_DIR>/playbook-docs/`), records the
  resulting URL/path back into the registry, and emits a clear operator-facing line stating WHERE the doc was
  created (or which fallback was used). Idempotent — a playbook that already has a recorded doc is left as-is.
- **CHANGE 4 — standards.** `references/communications-playbook-standard.md` adds "human-facing doc created in
  client's account (Notion → Google Docs → text), URL recorded" to the §2 MUST-APPEAR checklist and strengthens
  §4 from prose to a MANDATORY, machine-enforced deliverable (naming `qc-playbook-doc.sh`).
  `protocols/conversation-workflows-protocol.md` §F adds the doc column to the registry table and marks it
  mandatory + gated; `references/GHL-INBOUND-AND-PLAYBOOKS.md` §10 (first appointment-booking playbook) marks
  the doc step mandatory + gated. SKILL.md self-counts updated (scripts 30 → 32, four QC linters → five).

## [1.4.10] - 2026-05-29 - enforce conversation-memory (read-before + append-after) so single-turn hook agents never lose context

Root cause fixed: GHL inbound hook sessions are SINGLE-TURN / stateless (confirmed: every hook run is a fresh
session, user-turns = 1). The agent has NO in-session memory of prior messages — its ONLY memory of a contact
across messages is that contact's per-contact conversation log file
(`<MASTER_FILES_DIR>/conversational-logs/<contact_id>__<name>.md`), which it must READ before replying and
APPEND to after sending. On a live client this broke because the canonical `messageTemplate` was
"simplified" during testing and lost the read/append steps, the `conversational-logs/` dir was never created
(and was root-owned, so even when present the `node` gateway could not write it), and AGENTS.md had no memory
protocol — so the agent had ZERO memory ("didn't remember anything" mid-booking). The send-directive gate
(`qc-send-directive.sh`) did NOT catch it because it only checks the SEND instruction. Conversation-memory is
now enforced exactly like the send-directive, in four layers, not left optional.

### The canonical conversation-memory steps
Every GHL inbound SERVER `messageTemplate` must contain all of: the **conversational-logs** path, a
**READ**-before-replying instruction (recover prior conversation + any in-progress booking/topic and CONTINUE
it; if missing, treat as new), and an **APPEND**-after-sending instruction (append inbound + reply to the log,
create if missing). The directive lives ONLY on the SERVER mapping — the in-GHL-body `messageTemplate` stays
placeholder-free per the 23-key rule.

### Added
- **LAYER 4 — machine-enforced QC gate.** New `scripts/qc-conversation-memory.sh` (bash; mirrors
  `qc-send-directive.sh`) scans every GHL INBOUND SERVER-mapping `messageTemplate` (installer canonical
  template + reference examples) and FAILS (exit non-zero) if any is missing the conversational-logs path, the
  READ-before instruction, or the APPEND-after instruction. It SKIPS the placeholder-free 23-key bodies and
  non-GHL (Stripe/Shopify/n8n) mappings, and exits 2 (FAIL) if zero GHL inbound server templates are found so
  it never goes silently blind. Wired into BOTH `scripts/11-run-qc-checklist.sh` (pre-handoff QC, plus a new
  conversational-logs dir presence+writability check) AND `.github/workflows/qc-static.yml` (CI on every push/PR).

### Changed
- **CHANGE 1 — installer canonical template (fail-closed).** `scripts/15-configure-hooks-mappings.sh` now
  writes the read-before + append-after conversation-log steps into the GHL inbound mapping's `messageTemplate`
  (alongside the send-directive), and a second fail-closed guard refuses to write the config (exit 9) if the
  built template is missing the conversational-logs path, the read element, or the append element — it is no
  longer possible to install a GHL hook whose server `messageTemplate` lacks the read/append steps.
- **CHANGE 2 — installer creates + chowns the conversational-logs dir.** `scripts/09-install-conversation-workflows.sh`
  (Step 9 "Set up conversation log system") now `mkdir -p`s `<MASTER_FILES_DIR>/conversational-logs/` and chowns
  it to the runtime/gateway user (`node` on VPS/Docker, the login user on Mac/Homebrew; override via
  `OPENCLAW_RUNTIME_USER`) so the agent can actually write logs — runs before the registry early-exit and warns
  loudly with the exact `sudo chown` command if it cannot.
- **CHANGE 3 — AGENTS.md Conversation Memory Protocol base rule.** `scripts/05-update-agents-md.sh` now emits a
  concise standing rule (new `CONVERSATION_MEMORY_PROTOCOL` marker block): GHL inbound is single-turn; memory =
  per-contact logs; READ before replying + CONTINUE in-progress topics + APPEND after sending; a reply that
  ignores or fails to update the log is a failure. Pointer-style, no bloat.
- **v6.0 playbook + authoritative spec.** `references/v6.0-source-playbook.md` (canonical server mapping, Step 3)
  and `references/GHL-INBOUND-AND-PLAYBOOKS.md` (canonical mapping §4 + new §4b) now carry the read-before +
  append-after steps in their canonical server `messageTemplate`, replacing the simplified template that lacked
  them. 23-key rule, FLAT bodies, no nesting, no `\n`, placeholder-free in-body templates all preserved.
- **Standards.** `references/communications-playbook-standard.md` (new conversation-memory must-appear item) and
  `references/workflow-ai-instructions-standard.md` (new machine-enforced conversation-memory callout) now state
  the read/append steps are mandatory on the SERVER mapping and how to verify them (`scripts/qc-conversation-memory.sh`).

### Version
- `skill-version.txt` → `1.4.10`; SKILL.md self-counts updated (scripts/ 29 → 30; four QC linters).

## [1.4.9] - 2026-05-29 - enforce the mandatory GHL send-directive (drafting != sending) for every client

Root cause fixed: if a GHL inbound hook's SERVER-mapping `messageTemplate` does not EXPLICITLY order the
agent to SEND its reply via the GHL Conversations API, the model drafts a reply and STOPS — drafting is NOT
sending — and the customer receives nothing. This is now enforced in three layers, not left optional.

### The canonical send-directive
The exact mandatory clause every GHL inbound SERVER `messageTemplate` must contain (all elements required:
the word SEND, the GHL Conversations API, the contact id, the channel, the drafting-is-NOT-sending clause,
and "do not end your turn until a messageId/conversationId is returned"):

> MANDATORY — SEND, do not just draft: You MUST send your reply by calling the GHL Conversations API (POST
> conversations/messages) for contact {{contact_id}} on the {{channel}} channel, per TOOLS.md. Composing or
> drafting a reply is NOT sending — the customer receives nothing unless you make the API call. Do NOT end
> your turn until the send call returns a messageId/conversationId.

### Added
- **LAYER 3 — machine-enforced QC gate.** New `scripts/qc-send-directive.sh` scans every GHL INBOUND
  SERVER-mapping `messageTemplate` (the installer's canonical template + the reference examples) and FAILS
  (exit non-zero) if any is missing the send-directive elements (SEND, GHL Conversations API /
  `conversations/messages`, drafting-is-not-sending, do-not-end-turn-until-messageId). It deliberately
  SKIPS the placeholder-free object-A 23-key bodies (those stay placeholder-free per the 23-key rule — the
  send-directive lives ONLY on the server mapping) and non-GHL server mappings (Stripe/Shopify/n8n). Exits
  2 (FAIL) if zero GHL inbound server templates are found so it never goes silently blind. Wired into BOTH
  `scripts/11-run-qc-checklist.sh` (pre-handoff QC) AND `.github/workflows/qc-static.yml` (CI on every push/PR).

### Changed
- **LAYER 1 — installer canonical template (fail-closed).** `scripts/15-configure-hooks-mappings.sh` now
  writes the strengthened send-directive into the GHL inbound mapping's `messageTemplate`, and a fail-closed
  guard refuses to write the config (exit 8) if the built template is missing any send-directive element —
  it is no longer possible to install a GHL hook whose server `messageTemplate` lacks the send-directive.
  The in-GHL-body messageTemplate (the Step-4 E2E FLAT body) stays placeholder-free per the 23-key rule.
- **LAYER 2 — AGENTS.md standing base rule (belt-and-suspenders).** `scripts/05-update-agents-md.sh` now
  emits a concise standing rule (new `GHL_SEND_MANDATORY` marker block) + strengthens Step 7C "Send the
  reply": for ANY GHL inbound hook, SENDING via the GHL Conversations API is MANDATORY; a drafted-but-unsent
  reply is a failure; always confirm a messageId/conversationId before ending the turn.
- **v6.0 playbook + authoritative spec.** `references/v6.0-source-playbook.md` (canonical server mapping,
  Step 3) and `references/GHL-INBOUND-AND-PLAYBOOKS.md` §4 (the doc that wins) now show the strengthened
  send-directive in their canonical server `messageTemplate`, replacing the softer "reply via the GHL
  Conversations API per TOOLS.md" phrasing. 23-key rule, FLAT bodies, no nesting, no `\n`, placeholder-free
  in-body templates all preserved.
- **Standards + checklist.** `references/communications-playbook-standard.md` (GHL reply mechanism item),
  `references/workflow-ai-instructions-standard.md` (new machine-enforced send-directive callout), and
  `templates/workflow-verification-checklist-template.md` (new Webhook-Action verification item) now state
  the send-directive is mandatory on the SERVER mapping and how to verify it (`scripts/qc-send-directive.sh`).

### Version
- `skill-version.txt` → `1.4.9`; SKILL.md self-counts updated (scripts/ 28 → 29; three QC linters).

## [1.4.8] - 2026-05-29 - add Skill 23 cross-reference (role/SOP gate + comms hand-off) to v6.0 playbook

### Added
- **Skill 23 cross-reference in the v6.0 playbook.** Added a "🔗 How this connects to the AI Workforce
  Blueprint (Skill 23)" section to `references/v6.0-source-playbook.md`, placed right after the TRINITY /
  standards area (Communications Playbook Standard + Workflow-AI Instructions Standard). It documents the two
  enforced connections between Skill 38 and Skill 23: the **Role Library + SOP Library auto-pull gate**
  (build-state field + verify/resume gate; multiple Six Sigma DMAIC SOPs per role under
  `departments/<dept>/sops/`, never empty/stub) and the **comms-automation hand-off** (Skill 23 → Skill 38
  via a `commsAutomationStatus` state field + resume self-ping when a Communications/Sales/Customer-Support
  department is built), and ties both back to THE TRINITY keeping every workflow, playbook, and prompt in
  lockstep.

### Version
- `skill-version.txt` → `1.4.8`.

## [1.4.7] - 2026-05-29 - Close the 2 QC gaps: TRINITY registry format match + 23-key linter now covers the v6.0 playbook

Two QC checks that *looked* like they were enforcing invariants were silently no-op'ing on real inputs.
Both are now genuinely enforced, with fixture coverage.

### Fixed
- **GAP 1 — TRINITY registry format mismatch.** `scripts/qc-trinity-registry.sh` parsed the
  conversation-workflows registry only as a markdown TABLE, but `scripts/09-install-conversation-workflows.sh`
  documents/emits the active-workflow list as BULLETS (`- <id>: <desc>`). On a real installed (bullet)
  registry the table-only parser saw ZERO rows, so registry-vs-disk reconciliation
  (registered-but-no-files / files-but-not-registered) never fired and registered slugs were even
  mis-flagged "not registered". The validator now parses BOTH shapes (table rows scoped anywhere; bullet
  rows scoped under "## Active workflows", ignoring `<placeholder>`/backtick doc lines and quoted trigger
  phrases). Bullet rows carry no Layer-1 column → disposition recorded as unknown (still counts as
  registered). `scripts/09-install-conversation-workflows.sh` now seeds the canonical TABLE shape (matching
  protocol §F + the validator) while the validator still tolerates the legacy bullet form for older installs.
- **GAP 2 — 23-key linter excluded the v6.0 playbook.** `scripts/qc-23-key-bodies.sh` skipped
  `references/v6.0-source-playbook.md` (~9,430 lines) by name — the file holding the LARGEST set of GHL RAW
  BODY examples (per-channel curl smoke tests, Build-with-AI prompt bodies, verification-checklist bodies).
  Exclusion removed; the playbook is now scanned. The single-DOTALL `FENCE_RE` was also mis-pairing fences
  across that large multi-language document (it found only 1 of the file's 12 bodies), so the fence scanner
  was rewritten as a line-state iterator that pairs `` ``` `` open/close correctly regardless of language
  tag — now catching object-A bodies in ```json, ```text, no-language Build-with-AI blocks, AND ```bash
  `curl -d '{…}'` smoke tests. Object-B server `hooks.mappings` blocks (camelCase `agentId`) are still
  skipped by the snake_case `agent_id` discriminator — not by file exclusion. Linter result on the playbook:
  **all 12 of its bodies PASS**; repo-wide **RESULT: PASS — 23 object-A bodies across 6 files** (was 10/5).

### Added
- `scripts/qc-trinity-registry.test.sh` — fixture tests proving reconciliation catches a
  registered-but-missing-files row AND a file-present-but-unregistered slug on BOTH the bullet and table
  registry forms (and that a clean bullet registry PASSes). Wired into CI (`.github/workflows/qc-static.yml`).

### Version
- `skill-version.txt` → `1.4.7`.

## [1.4.6] - 2026-05-29 - 8 rated improvements (port of VPS #47): machine-enforced 23-key + TRINITY, Build-with-AI label fix, real self-counts, fleshed journeys, Skill 23 chain

Part of repo `v10.15.9`. Six of the eight rated improvements land in this skill; the other two
(cross-skill chain enforcement + library-gate status surfacing) land in Skill 23 but reference this skill.
No stripped GHL bodies introduced — the 10 embedded object-A bodies all pass the new linter (23-key, flat,
placeholder-free).

### Added
- `scripts/qc-23-key-bodies.sh` — machine-enforces the 23-key GHL RAW BODY rule across references/ +
  templates/ + scripts/ (exactly 23 flat keys, placeholder-free `messageTemplate`, no nesting, no `\n`).
  Wired into `scripts/11-run-qc-checklist.sh` and into CI (`.github/workflows/qc-static.yml`). Excludes the
  verbatim `v6.0-source-playbook.md`; skips object-B server mappings.
- `scripts/qc-trinity-registry.sh` — machine-enforces THE TRINITY: a registry row with a communications
  playbook but no Build-with-AI prompt (or an orphan prompt) is flagged INCOMPLETE; honors the
  Layer-1-not-needed exemption. Wired into `11-run-qc-checklist.sh`; referenced from the verification
  checklist + standards.

### Changed
- **Mislabel fix (the failure this standard set out to kill):** `templates/sms-workflow-ai-prompt-template.md`,
  `templates/workflow-verification-checklist-template.md`, `scripts/21-generate-client-reference-sheet.sh`,
  `scripts/09-install-conversation-workflows.sh`, and `scripts/20-seed-design-principles.sh` now name the
  authoritative location — GHL **Automations → "Build with AI"** (top-right) on a NEW automation — instead
  of "Use Workflow AI" / "Create workflow → Workflow AI".
- **Real self-counts:** `SKILL.md` + `INSTALL.md` now state protocols=32, scripts=27, references=14,
  journeys=8 with a `SELF-COUNTS` re-verify comment; a re-verification note was added to the repo
  `scripts/bump-version.sh`.
- **7 stub journey templates fleshed out** to ≥ coach depth with vertical-specific triggers / conversation
  phases / success actions: consulting, course-creator, e-commerce, real-estate, saas, service-provider,
  wellness (107–121 lines each).
- **Distinction-map table** added at the top of `protocols/conversation-workflows-protocol.md` (channel
  communication playbook vs communications playbook vs workflow-AI prompt vs GHL automation).
- **Skill 23 upstream cross-reference** added to `SKILL.md` + the protocol's TRINITY note (Skill 23's
  comms/sales/support build now hands off here via the enforced `commsAutomationStatus` chain).

### Version
- `skill-version.txt` → `1.4.6`.

## [1.4.5] - 2026-05-29 - v6.0 clean comprehensive playbook; de-staled

### Why
The source playbook is replaced with the **clean, conflict-free v6.0** single-source-of-truth build. All GHL
hook guidance now matches the settled standard everywhere: **23-key FLAT** Raw Body, the body's own
`messageTemplate` value is **placeholder-free**, `deliver` is **`false`**, mapping-level `fallbacks` is
**never** a key (the `.strict()` schema rejects it; fallbacks live on the model-routing config only), and no
nested bodies / no stripped sub-23-key bodies anywhere. Every passage that disagreed with that standard was
removed or corrected upstream in the v6.0 content, so the repo carries **no stale or conflicting playbook
content**. The standards docs (`GHL-INBOUND-AND-PLAYBOOKS.md`, `communications-playbook-standard.md`,
`workflow-ai-instructions-standard.md`) remain their own reference docs; the playbook references them rather
than duplicating them. `skill-version.txt` bumped 1.4.4 → 1.4.5.

### Changed
- `references/v5.14-source-playbook.md` → **renamed** to `references/v6.0-source-playbook.md` (git mv) and its
  content replaced with the clean v6.0 comprehensive playbook (9,430 lines / ~452 KB). The header now stamps
  **Version 6.0 (CLEAN, CONFLICT-FREE)** and declares itself the single source of truth superseding v5.x.
- Updated every live pointer/cross-link from `v5.14-source-playbook.md` to `v6.0-source-playbook.md`:
  `scripts/01-locate-master-files-folder.sh` (both `PLAYBOOK_SRC` and the `DEST_PLAYBOOK` copy target),
  `INSTALL.md`, `INSTRUCTIONS.md`, and the reference cross-links in `GHL-INBOUND-AND-PLAYBOOKS.md`,
  `stripe-coupons-api.md`, `stripe-webhooks-reference.md`, `shopify-graphql-reference.md`,
  `sales-frameworks-deep-dive.md`, `ghl-coupons-api.md`, `cloudflare-tunnel-troubleshooting.md`,
  `cloudflare-godaddy-setup-guide.md`.
- Conflict sweep across the Skill 38 folder (nested GHL body, sub-23-key body, `deliver:true`, mapping-level
  `fallbacks`, conflicting "DATA ONLY / no messageTemplate" phrasing): **no contradictions found**. The only
  remaining `deliver:true` / "no stripped bodies" mentions are corrective prose that debunks the old patterns,
  and the standards docs already match the corrected structure — no surgical edits were needed beyond the
  playbook content + filename pointers above.

## [1.4.4] - 2026-05-29 - THE TRINITY + Communications Playbook & Workflow-AI standards

### Why
Two recurring failure surfaces hardened, with full content kept in reference/protocol docs (CORE md files
get concise pointers only — no bloat): (1) operators were building a GHL workflow OR a playbook OR a
workflow-AI prompt in isolation, leaving the other two missing; (2) GHL's Build-with-AI repeatedly fails to
populate the Custom Webhook fields, and there was no single standard spelling them out field-by-field. All
new GHL RAW BODY examples honor the 23-key rule (flat, placeholder-free `messageTemplate`, no `\n`, no
nesting, no stripped bodies). `skill-version.txt` bumped 1.4.3 → 1.4.4.

### Added
- `references/communications-playbook-standard.md` — the COMMUNICATIONS PLAYBOOK STANDARD: standardized
  format + a "must appear in EVERY playbook" checklist (slug/id, owner agent id, channel, trigger
  phrases/intent, goal, step-by-step flow, GHL Conversations-API reply mechanism per TOOLS.md,
  cross-playbook transition rules, edge cases incl. frustration/refund/legal escalation, on-success/tagging,
  tone, honesty floor); STORAGE in `conversation-workflows/` + register in `registry.md`; and the client-side
  human-readable copy fallback order **Notion → Google Docs → plain text**.
- `references/workflow-ai-instructions-standard.md` — the WORKFLOW-AI INSTRUCTIONS STANDARD: must-appear
  checklist; WHERE it goes (GHL Automations **Build with AI** button when creating a NEW automation); the
  explicit field-by-field Custom Webhook steps (EVENT=CUSTOM, METHOD=POST, real URL not sample-url,
  AUTHORIZATION=None, HEADERS via Add item → Authorization Bearer token + Content-Type json, RAW BODY = full
  23-key flat JSON via the Custom Values picker); MULTI-ACTION teaching (if/else branches, Add-Tag, tag-check,
  multiple sequential actions, create-tag-via-GHL-skill-first); and the BUILD-WITH-AI VERIFICATION CHECKLIST.

### Changed
- `protocols/conversation-workflows-protocol.md` — added **THE TRINITY** connection rule (workflow ⇄
  communications playbook ⇄ workflow-AI prompt; one implies the other two) + pointers to the two new
  standards; D.2 Build-with-AI prompt block upgraded to the field-by-field Custom Webhook format
  (EVENT/METHOD/AUTHORIZATION=None/HEADERS via Add item/Content-Type); Section E now points at the
  communications-playbook standard's checklist + Notion→Google Docs→plain-text storage order.
- `templates/sms-workflow-ai-prompt-template.md` — Action 1 rewritten to the precise field-by-field format
  (EVENT=CUSTOM, METHOD via dropdown, real URL, HEADERS via Add item, Custom Values picker) + a MULTI-ACTION
  note (if/else, Add-Tag, tag-check, multiple actions; tags created via GHL skill first).
- `templates/workflow-verification-checklist-template.md` — extended with EVENT=CUSTOM, real-URL-not-sample,
  "exactly the intended action(s)" count check, Custom-Values-picker check, and a tags/multi-action item.
- `scripts/05-update-agents-md.sh` (AGENTS.md guidance, Step 1.85) — added concise 1-2 line pointers to THE
  TRINITY + the two new standard reference docs (full content stays in the references, not inline in CORE md).
- `INSTRUCTIONS.md` — Step 9.20 row notes THE TRINITY + the two standards.

## [1.4.3] - 2026-05-29 - Enforce 23-key GHL body everywhere (no stripped bodies)

### Why
Owner directive (non-negotiable): EVERY GHL Custom Webhook RAW BODY example in this skill must contain ALL 23
keys. 23 is the MINIMUM — no stripped/short bodies (8/11/13/16-key versions) are allowed anywhere. The prior
13/16-key bodies are replaced with the full 23-key canonical body. The body stays FLAT, the body's
`messageTemplate` value is kept placeholder-free (no `{{…}}`) so GHL never mangles the JSON, and there are no
`\n` escapes inside any JSON example. Per-channel variants keep all 23 keys; only `channel` + the `session_key`
prefix differ. `skill-version.txt` bumped 1.4.2 → 1.4.3.

### The 23 keys (exact)
`id`, `match`, `action`, `agent_id`, `model`, `wakeMode`, `name`, `session_key`, `messageTemplate`, `deliver`,
`timeoutSeconds`, `channel`, `to`, `thinking`, `contact_id`, `first_name`, `last_name`, `email`, `phone`,
`subject`, `message_body`, `location_id`, `location_name`.

### Added / Changed
- `references/GHL-INBOUND-AND-PLAYBOOKS.md` — new rule (0) mandating all 23 keys (23 = minimum); canonical body
  upgraded to 23 keys + per-channel variant list; Section 4 Build-with-AI body upgraded; Section 5 checklist now
  demands all 23 keys; cardinal-rule + corrected-structure prose rewritten (body now carries a placeholder-free
  `messageTemplate` instead of "no messageTemplate").
- `references/v5.14-source-playbook.md` — every GHL Raw Body upgraded to 23 keys (Step 3C smoke test, Step 4 E2E
  test, Step 9.20-D.2 + multi-channel Build-with-AI prompts, the D.3 verification stub, all six Part 3 channel
  blocks); stripped `tags`/`workflow_id` extra-keys removed; corrected-structure notes rewritten.
- `scripts/15-configure-hooks-mappings.sh` — Step 4 E2E test PAYLOAD upgraded to the full 23-key body.
- `protocols/conversation-workflows-protocol.md` — Build-with-AI Raw Body + D.3 verification stub upgraded to 23
  keys; corrected-structure note rewritten.
- `templates/sms-workflow-ai-prompt-template.md` — SMS Raw Body upgraded to 23 keys; mistakes list updated.
- `templates/client-reference-sheet-template.md` — all six channel Raw Body blocks upgraded to 23 keys.
- `templates/workflow-verification-checklist-template.md` — Raw Body stub upgraded to the full 23-key body.
- `skill-version.txt` — 1.4.2 → 1.4.3.

## [1.4.2] - 2026-05-29 - GHL inbound hook correction: FLAT body, no nesting, server-only messageTemplate

### Why
Verified LIVE on a live client (OpenClaw 2026.5.27): the GHL Custom Webhook RAW BODY must be FLAT
(data-only). A nested `contact:{…}` / `customer_message:{…}` body makes EVERY field arrive EMPTY at the hook
(even a hardcoded `"channel"`), and a `messageTemplate` placed in the GHL body gets mangled by GHL's own
merge-field parser → webhook Skipped ("Error while parsing the object to JSON"). The `messageTemplate` is
server-side only and MUST include the reply-via-GHL-Conversations-API instruction or the agent drafts but
never sends. Content + script correction; `skill-version.txt` bumped 1.4.1 → 1.4.2.

### Added / Changed
- `references/GHL-INBOUND-AND-PLAYBOOKS.md` — new top-of-doc **CORRECTED GHL HOOK STRUCTURE (2026-05-29)**
  section (the 12-point canonical spec); Section 4 Build-with-AI body flattened; Section 5 verification
  checklist updated to demand a FLAT, no-`messageTemplate`, Custom-Values-picker body.
- `references/v5.14-source-playbook.md` — every GHL Raw Body flattened (Step 3C smoke test, Step 4 E2E test,
  Step 9.20-D.2 + multi-channel Build-with-AI prompts, all six Part 3 channel blocks); mapping `messageTemplate`
  rewritten to reference FLAT body keys + reply-via-GHL-API instruction; `deliver:false`; `sessionKey:"{{session_key}}"`;
  removed invalid `fallbacks` key from the mapping (schema is `.strict()`); schema-fields list + Checkpoint C corrected.
- `scripts/15-configure-hooks-mappings.sh` — mapping `messageTemplate` now uses FLAT body keys + GHL-API reply
  instruction; `deliver:false`; `sessionKey` default is `{{session_key}}`; E2E test PAYLOAD flattened.
- `protocols/conversation-workflows-protocol.md` — Build-with-AI Raw Body flattened + corrected-structure note.
- `templates/sms-workflow-ai-prompt-template.md` — SMS Raw Body flattened; mistakes list + placeholders updated.
- `templates/client-reference-sheet-template.md` — all six channel Raw Body blocks flattened.
- `skill-version.txt` — 1.4.1 → 1.4.2.

## [1.4.1] - 2026-05-28 - Conversation Playbook Builder enhancement (the differentiator) (repo v10.15.7)

### Why
The recurring "build me a conversation playbook" flow is the system's USP — communication-driven funnels /
automations, built by talking and brainstorming instead of click-and-drag (this is what beats CloseBot).
Step 9.20 needed to be explicitly bulletproof every time, and the MEMORY.md rules + Mac env handling needed
to back it. Content-only addition; no version files touched (repo stays v10.15.7).

### Added / Changed
- `protocols/conversation-workflows-protocol.md` — Step 9.20 reframed as an explicit **3-PART build**:
  Part 1 (Workflow AI instruction set = Build-with-AI prompt + new **manual-build fallback** D.2b +
  verification checklist, with the SHAPE-first / operator-pastes-tokens guidance); Part 2 (the conversation
  playbook → registered in registry.md, with the hook-path "how the two halves connect" note); Part 3 (new
  Section I — the friendly **brainstorm trigger**: use Typed KBs + USER.md + MEMORY.md, ask ONLY smart gaps,
  NEVER 50 questions, concise "is this what you want?" confirmation → build → Notion doc → register). New
  Section J (AGENTS.md Step 1.85 runtime hook), Section K (builder ↔ router ↔ proactive cross-references),
  Section L (Mac env note). Removed ambiguous "Workflow AI" usage referring to the GHL feature (now
  "Build with AI") and the implication that GHL Automations have an API.
- `scripts/06-append-memory-rules.sh` — adds a second idempotent block: **builder design rules 15-19**
  (Terminology, No-GHL-API, 3-PART Build, Brainstorm-Not-50-Questions, Mac Env).
- `scripts/05-update-agents-md.sh` — Step 1.85 block expanded with the communication-driven USP, the
  brainstorm-not-50-questions rule, the 3-PART build, the no-GHL-API note, and the router/proactive cross-refs.
- `scripts/18-locate-secrets-env.sh` — Step O.5: Mac now searches BOTH `~/clawd/secrets/.env` and
  `~/.openclaw/.env`; added the Mac-vs-VPS env clarity note.
- `protocols/intelligent-routing-protocol.md` (Step 9.33) + `protocols/proactive-suggestions-protocol.md`
  (Step 9.34) — reciprocal triangle cross-references to the builder.
- `INSTRUCTIONS.md` — Step 9.20 row rewritten (3-PART build, USP, no-API note); 9.33/9.34 rows annotated;
  Phase 0 Step O.5 Mac env note added.
- `CORE_UPDATES.md` — documents builder design rules 15-19 so install writes them.

## [1.4.0] - 2026-05-28 - GHL Build-with-AI hardening + calendar-sync (repo v10.15.7)

### Why
A live Mac-mini build surfaced several traps that every future Mac client would otherwise hit:
token confusion (4 distinct secrets), `deliver: true` silently breaking GHL API replies, the
`cron.jobs` JSON block failing validation on openclaw 2026.5.27, GHL having no API/MCP for building
automations (Build-with-AI is the only path), and the Mac-specific `cloudflared` launchd install
needing interactive sudo. Baked all the fixes into the skill so no Mac client stalls on them.

### Added
- `references/GHL-INBOUND-AND-PLAYBOOKS.md` (NEW) — authoritative Mac reference: 4-token table,
  one-tunnel-many-hooks model, copy-paste **Build-with-AI prompt** template (placeholders
  PUBLIC_HOSTNAME / HOOK_PATH / HOOKS_TOKEN / CHANNEL), post-build verification checklist (incl.
  real-inbound-test caveat), Reusable Tunnel Values storage rule (AGENTS.md + TOOLS.md + client
  Notion), JSON one-value-per-key rule, verified channel→`type` enum (valid: SMS/Email/FB/IG/
  WhatsApp/Live_Chat; invalid: TikTok/Call/GMB + long-forms), Conversations reply recipe, Calendar
  recipe (free-slots epoch-MILLIS, book/reschedule/cancel), first playbook = appointment booking.
- `scripts/skill38-calendar-sync.sh` (NEW) — weekly GHL calendar refresh; rewrites the
  `<!-- GHL_CALENDARS_START/END -->` block in TOOLS.md. Auto-detects Mac vs VPS env/paths. Generic
  per-client. Registered via `openclaw cron add --name skill38-calendar-sync --cron "0 9 * * 0" ...`.

### Changed (surgical edits to references/v5.14-source-playbook.md)
- Step 3C + Step 3.5G: `deliver: true` → `deliver: false` on GHL reply hooks, with corrected
  rationale (true makes the gateway try to deliver to a non-existent default chatId → reply never sends).
- Step 3A: added the 4-token disambiguation table; Mac note (no Hostinger wrapper → hooks.token in
  openclaw.json is stable; no OPENCLAW_HOOKS_TOKEN env trick).
- All cron registrations → `openclaw cron add` CLI flag form, with a banner that `cron.jobs` JSON
  does not validate on openclaw 2026.5.27.
- Step 9.20 D.2: "Workflow AI prompt" → "Build-with-AI prompt"; Build-with-AI is PRIMARY, manual
  node-build demoted to FALLBACK; verification checklist required even on success; F.6 Reusable Tunnel
  Values; F.7 base SMS automation also creates the first appointment-booking playbook and wires the
  hook to it.
- Part 2 (Client Reference Sheet / Notion-doc spec) rewritten ordering: Reusable Tunnel Values →
  Build-with-AI prompt per channel → verification checklist; manual webhook build moved to fallback.
- Rules of Engagement: added Rule 7 (one value per key — proper JSON structure).
- Standardized `GHL_PRIVATE_INTEGRATION_TOKEN` + `Version: 2021-04-15` on the Conversations/Calendar
  path (was `<GHL_PIT_TOKEN>`). `GOHIGHLEVEL_AGENCY_PIT` is not present in this repo.
- Calendar action: verified endpoints (free-slots epoch-millis; appointments required fields; PUT/DELETE).
- Mac cloudflared step: kept launchd `sudo cloudflared service install` but flagged the
  interactive-sudo requirement prominently (cannot run over non-interactive rescue SSH).

# Skill 38 — Conversational AI System: Changelog

## [1.0.0] - 2026-05-28 - Initial release (packages v5.14 playbook)

### Why
the operator's v5.14 conversational AI playbook (~8,800 lines, 14 version iterations) packaged as
an installable skill. Builds the conversational AI BRAIN on top of skill 29 (GHL Convert and Flow).

### Added
- 27 protocol files (humanizer NOT included; skill 19 owns it)
- 8 customer journey templates (coach fully detailed; 7 stubbed)
- 9 idempotent + OS-aware install scripts (00 prerequisites → 08 Shopify wizard)
- 7 reference documents including the FULL v5.14 source playbook + strategic roadmap
- SKILL.md, INSTALL.md, INSTRUCTIONS.md, EXAMPLES.md, CORE_UPDATES.md
- AGENTS.md Steps 1.7, 1.8, 1.9, 2.8; upgraded Step 1.75
- MEMORY.md design rules 6-14
- 4 cron jobs (Sunday 2am tune-up, Saturday 11pm proactive + 11:30pm model freshness, 1st-of-month review)

### Source of truth
- `references/v5.14-source-playbook.md` — the canonical 8,797-line playbook
- `references/conversational-ai-strategic-roadmap.md` — strategic context (✅ shipped vs 📋 pending)

### Out of scope (DEFERRED, not in this skill)
- F14 Voice/Phone Integration
- F15 Proactive Outreach Campaigns
- F16 A/B Testing of Reply Variants
- F17 Customer Segmentation Awareness
- F18 Webhook Chaining
- F21 Multi-Tenant Agent Isolation

The skill's structure (numbered scripts, protocols/ folder, references/) leaves room for
these to be added later without restructuring.
