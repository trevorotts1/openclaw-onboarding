# ANTHOLOGY ENGINE, TECHNICAL SPECIFICATION (SPEC)
### The buildable, node-level companion to PRD.md. Execution sub-agents implement FROM this document; the PRD states what and why, this SPEC states exactly how.
### Version 3.0, authored by Fable, 2026-07-06 (revision 3: the producer experience relocated INSIDE the client's own Command Center as a seeded Anthology department/board per the verified Command Center repo read; the prompt source of record moved to the Downloads JSON exports; participant token page added; v19.0.0 target). Status: PLANNING ONLY. No build is triggered by this document.

TERMINOLOGY BINDING (revision 3, normative over every older line in this SPEC, and aligned with design/dashboard-design.md v3.0): there is NO standalone Anthology Mission Control app and NO producer role in any Command Center code. Wherever this SPEC says "dashboard", "Assembly panel", or "Mission Control", it MEANS: the Anthology DEPARTMENT BOARD inside the client's own Command Center (per-client, single-owner, white-label, on the client's own box, unlocked by the AI Workforce Interview, Skill 23 leading to Skill 32), seeded by Skill 32's add-department.sh (POST /api/departments with create:true), whose review column is the chapter-approval queue (the existing board contract routes producer output to review; ONLY the independent QC scorer at or above 8.5 promotes review to done), whose task cards are the participant kanban, and whose dedicated Assembly card carries the ready-to-assemble trigger and the final sign-off; PLUS, for external co-author participants, the NEW token-scoped public route added to the Command Center middleware.ts bypass list (Section 11). Cards ingest via mc_board.py posting to POST /api/tasks/ingest (HMAC plus Bearer, fail-soft).

DOCUMENT CONTROL. This SPEC sits beside PRD.md at /Users/blackceomacmini/clawd/projects/Anthology-Engine/ and is subordinate to it: where this SPEC and the PRD could ever be read to disagree, the PRD governs and this SPEC gets fixed. This document is IDENTIFIER-SCRUBBED: legacy workflows, bases, and tables are referenced by LABEL only (LEGACY-MAIN, LEGACY-AVATAR, LEGACY-TONE, LEGACY-TITLE, LEGACY-OUTLINE, LEGACY-CHAPTER, LEGACY-REWRITER, LEGACY-COVER; LEGACY-PROMPT-BASE, LEGACY-SYSTEMS-BASE); Wave 0 resolves each label live (n8n REST API by workflow name and webhook path; Airtable metadata API by base name) into the build-state file on the operator box, which never enters the repo. Zero client personally identifiable information appears in this document, by law.

DOCTRINE BINDING (identical to the PRD, restated because build agents read this file directly): MOVE IN SILENCE, operator-verbose and never client-facing; NOTHING Anthropic ships in any runtime file, including the dashboard and every config template; every credential is referenced by LABEL and LOCATION only, never by value, and no key, token, email address, or personally identifying value is hardcoded anywhere in this document or in anything built from it; the client-facing platform name is Convert and Flow in every surface; config writes run as the node user, never root; only sub-agents build; zero em dash characters and zero code fences in any produced client deliverable (and, by house convention, in this document, which uses indented blocks instead of fences).

---

## 1. VERIFIED GROUND TRUTH THIS SPEC IS BUILT ON

Everything below was verified live on 2026-07-06 during the authoring of this SPEC (read-only; metadata only; no secret value was printed or copied). Wave 0 re-verifies all of it before build, because live systems drift.

1.1 THE LEGACY N8N ESTATE (instance per design/n8n-integration-design.md Section 1; all eight workflows confirmed ACTIVE via the n8n REST API, node counts matching the Downloads exports byte-for-byte at the graph level; identifiers by LABEL, resolved live at Wave 0; the main orchestrator's display name carries a person's first name and is scrubbed here, resolvable by its unique webhook path):

| Workflow (label) | Nodes | Role in legacy pipeline |
|---|---|---|
| LEGACY-MAIN (main orchestrator; resolvable by POST webhook path anthology) | 81 | POST /webhook/anthology intake, folder tree, stage gates, sub-agent dispatch |
| LEGACY-AVATAR (display name Avatar Agent) | 29 | Avatar Questions 1 to 30, 31 to 32 (web search), rewrite, primary goal, HTML |
| LEGACY-TONE (Tone Agent) | 36 | Tone Styles 1 to 4, Blended Tone, HTML |
| LEGACY-TITLE (Title Writer Agent) | 15 | Suggested Titles, HTML |
| LEGACY-OUTLINE (Outline Agent) | 19 | Book Blurb, single-chapter Create Outline, HTML |
| LEGACY-CHAPTER (Chapter Agent) | 15 | Write Chapter (2,000 to 3,500 words), HTML |
| LEGACY-REWRITER (Chapter Re-Writer Agent) | 15 | Thornfield editorial rewrite, Book-to-HTML |
| LEGACY-COVER (Single Chapter Cover Image Gen) | 11 | Cover prompt generation, legacy image API render |

Node-level facts verified in the exports and confirmed live: the main webhook is POST path anthology; the opportunity lookup is getAll with limit 1 filtered by one hardcoded pipeline identifier (a client pipeline identifier; it appears in NO planning document and never in the repo; Wave 0 resolves it live into the build-state file); ELEVEN Gmail sendAndWait gates exist in the main orchestrator (Avatar Confirmation, Tone Confirmation, Tone Form, Title Form, Producer Avatar Confirmation, Title Confirmation, Outline Form, Outline Confirmation, Chapter Form, the chapter Approve-or-Rewrite gate named Gmail, Re-Write Form), each with limitWaitTime 45 days; the webhook payload carries a routing credential inside customData (field name confirmed; value never read), which is Gap 3 of the PRD; the legacy cover workflow carries a LITERAL authorization header on its image-generation node (presence and length confirmed, value untouched), also Gap 3; pinData with captured live payloads is present in the Downloads exports, which is why the exports are scrubbed or deleted at Wave 0 after prompt rescue.

1.2 THE LEGACY AIRTABLE ESTATE (both bases enumerated via the metadata API, schema only):

Base LEGACY-PROMPT-BASE (display name AI Prompt Database -2025 (n8n); id resolved live at Wave 0): five prompt tables, ALL sharing the identical four-column shape Prompt, System, User, Assistant (all multilineText): Sales Page Writer Prompts, Avatar Alchemist BI Prompts (label LEGACY-TBL-AVATAR, the anthology's only runtime prompt source, 40 records of mixed IP of which eight are anthology prompts), 4x3x3 Book Writer plus its copy, and Full Book Prompts (28 records, eight of them truncated at the platform's 32,767-character ceiling, ALL eight belonging to the twelve-chapter full-book product, out of anthology scope by ratified decision).

Base LEGACY-SYSTEMS-BASE (display name BlackCEO-Ai-System; id resolved live at Wave 0): E-Books, Prompts, Book Creator (a full-book state table: Stage1 to Stage6 status, book_id, folder_id, per-book chapter links), chapters, plus landing-page, signature-presentation, and X-Days-Challenge tables. VERDICT, confirmed by enumeration: this base is the state store of the OTHER product families (the 4x3x3 full book, signature presentations, challenges). The anthology pipeline holds ZERO durable state in Airtable; its only state lives in suspended n8n executions and Convert and Flow opportunity stage positions, which is exactly the fragility the engine's new ledger replaces (PRD Section 5, design/data-model-design.md Section 1). No Anthology Engine runtime file will ever reference either legacy base (static scan at merge).

1.3 THE FLEET REPO (canonical remote verified via git remote get-url: the trevorotts1 onboarding repository; live content version at authoring time v17.0.17):

| Asset | Verified version/state | Relevance |
|---|---|---|
| 54-anthology-writer | skill-version 1.0.0; ANTHOLOGY-MANIFEST.json with P0 to P7 phase machine, AF-AW autofail table, sha256 source_prompt_pins for assets/prompts/06 to 10; provers prove_aw_intake.py, prove_aw_fidelity.py, prove_aw_tone.py, prove_aw_chapter.py, aw_build_check.py, verify_tone_core_sync.py; run_anthology.py; anthology-entry.sh; model-map.template.json (HEAVY-WRITER, MID-WRITER, RESEARCHER, IMAGE tiers, never Anthropic); intake/aw-intake-schema.json (anthology_title, first_name, last_name, chapter_premise required); golden plus attack fixtures | The authoring core. NOTE: any Skill 54 version figure in the planning set is a stale snapshot; Wave 0 records the live number and the extension lands as the next minor above it |
| 53-book-writer | skill-version 1.0.3 | Sibling, UNTOUCHED (Section 14) |
| 52-avatar-alchemist | SKILL.md version 1.1.2; prompts 01-avatar-questions-1-30, 02-avatar-questions-31-32, 03-rewrite-avatar (plus the shared tone core copies 04 to 08) | S1 source IP via formal handoff |
| shared-utils/tone-writing-core | present with tone-core-manifest.json; lockstep enforced by verify_tone_core_sync.py | S2, byte-identical, never forked |
| 07-kie-setup, 46-kie-callback-relay | present | S7 covers |
| 14-google-workspace-integration | present | Drive and Docs adapter |
| 29-ghl-convert-and-flow, 36-ghl-mcp-setup, 44-convert-and-flow-operator | present | Convert and Flow data plane |
| 32-command-center-setup, 50-email-engine | present | Board cards; nudge delivery fallback |
| 54-anthology-writer/roles/anthology-writer.role.md | declares the books/publishing department binding | Department wiring reuse (W4.3) |

A striking already-built fact the build must exploit: Skill 54's manifest tier table ALREADY names aw-11 (cover prompt) and aw-12 slots in its MID-WRITER role description, meaning the manifest anticipated exactly the prompt extensions this build adds. The extension work is completion, not surgery.

1.4 PROMPT SOURCES (Downloads): ANTHOLOGY_PROMPTS_AVATAR_TONE_VERBATIM.md carries the eight avatar and tone prompts complete (source table LEGACY-TBL-AVATAR); ANTHOLOGY_PROMPTS_INLINE_VERBATIM.md carries Write Chapter and the Chapter HTML formatter complete and, for the four largest inline prompts, carries POINTERS only. THE SOURCE OF RECORD for those four (single-chapter Create Outline; the Thornfield Chapter Re-Writer persona; the Book-to-HTML formatter; the Cover Image prompt generator) is the JSON EXPORTS THEMSELVES: Outline Agent.json, Chapter Re-Writer Agent.json, and Single Chapter Cover Image Gen.json in /Users/blackceomacmini/Downloads/anthology project/. Wave 0 INGESTS them directly from these files (no live n8n dependency), with three repair laws: the formatter's 10 literal [UNCHANGED] placeholders are RESTORED from the CSV record named HTML Book in Full Book Prompts-Grid view.csv before pinning (a pin containing [UNCHANGED] is a hard failure); the Write Chapter word-count contradiction NORMALIZES to 2,000 to 3,500; Make.com variable syntax maps to canonical field names (Section 6.2). SECURITY LAW: the nine exports carry LIVE keys (an OpenAI key in the cover node's literal Authorization header; an OpenRouter key at customData.Openrouter_Api_Key in the webhook payload) and are NEVER committed to any repo; both keys rotate at Wave 0 and the payload-carried key becomes an ENV credential by label. Measured node payload sizes, so the rescue can prove zero truncation by byte count: Create Outline system 7,251 and assistant 11,191 and user template 2,435; HTML Outline system 3,016 and assistant 12,795; Thornfield rewriter system 7,113 and assistant 30,626; Book-to-HTML formatter system 4,987 and assistant 10,262; cover prompt generator system 2,135 and assistant 11,904; Write Chapter system 6,025 and assistant 49,756 (already captured verbatim); Suggested Titles inline assistant 70,321 (the largest single prompt in the estate, already baked as Skill 54 asset 06, byte-equality verified at Wave 0).

---

## 2. ARCHITECTURE: FOUR LAYERS, ONE EXECUTION MODEL

The engine is the PRD Section 4 four-layer system. This section fixes the runtime topology those layers compile to on a client box.

2.1 PROCESS TOPOLOGY (client box, everything as the node user):

    Convert and Flow form POST
      -> Cloudflare Tunnel hostname (client's ONE named tunnel)
        -> OpenClaw gateway inbound webhook route /hooks/anthology-intake
           (per-client shared secret, label ANTHOLOGY_INTAKE_HOOK_SECRET)
          -> intake_router.py (deterministic, no model call, exits in under 2 seconds)
            -> anthology_state.py (sole ledger writer; Airtable base plus SQLite mirror)
              -> stage job (one stage, idempotent, spawned detached)
                 -> Layer 1 authoring core: Skill 54 anthology-entry.sh (local-only)
                 -> Layer 3 adapters: drive_adapter, pdf_render, caf_delivery, cover_render
                 -> gate_engine.py opens the next gate, fires ONE nudge, STOPS
    The Anthology department board in the client's own Command Center is fed
    by mc_board.py -> POST /api/tasks/ingest (HMAC + Bearer, fail-soft);
    board-originated gate actions and the participant token page write ONLY
    by shelling anthology_state.py subcommands.
    Daily tick (one cron entry, registered in the cron inventory): smoke test,
    hold-queue aging, mirror reconcile, stuck-gate re-nudge policy.

2.2 EXECUTION MODEL (binding, from pipeline-design.md Section 1): an event arrives (form submission, gate decision, Kie.ai callback, daily tick, operator exception action); the router loads the participant by composite key contact_id plus anthology_id; advances EXACTLY ONE stage; persists every artifact and transition; stops. Replaying any event against current state is an acknowledged no-op. No process ever sleeps waiting for a human; the ledger holds the cursor for weeks or months at zero cost. This inverts the legacy design, whose eleven sendAndWait gates with 45-day ceilings are the proven failure (executions stuck since Oct-Nov 2025 on record).

2.3 LAYER BOUNDARIES AS CODE CONTRACTS:

- Layer 2 (orchestration) is the ONLY layer that touches the ledger, the model router, and the gates.
- Layer 1 (Skill 54) is invoked as a local subprocess through anthology-entry.sh with a working directory per participant per stage; it never performs network I/O beyond its model calls through the resolved model map; it returns artifacts on disk plus its RUN-LEDGER.json and prover verdicts. Skill 54's certification model (hash gate, nonce, fail-closed provers) is preserved untouched.
- Layer 3 adapters are stateless functions with explicit inputs; every external write is followed by a read-back verification in the same job.
- Layer 4 (dashboard) holds no write credential to the base; its only write path is the writer CLI. This is dashboard acceptance criterion 13 made structural.

---

## 3. THE OPENCLAW SKILL LAYOUT (DIRECTORIES, FILES, SCRIPTS)

3.1 THE NEW ORCHESTRATOR SKILL. Working id anthology-engine; the skill NUMBER is resolved at Wave 0 as the next free slot above the current highest (verified today: 57-social-media-in-a-box is the highest shipped; Wave 0 confirms against live main before claiming the number). Directory layout, following the certified Skill 54/52 house pattern (SKILL.md plus manifest plus entry plus provers plus fixtures):

    NN-anthology-engine/
      SKILL.md                       runbook: what it does, S0 to S9, triggers,
                                     layer boundaries, the Skill 54 call contract,
                                     silence rules, sibling boundaries (53/54)
      ENGINE-MANIFEST.json           single source of truth: stage machine S0 to S9,
                                     per-stage produces_artifact, gate table,
                                     AF-AE-* autofail codes with triggers and
                                     py_symbol per code, source_prompt_pins for
                                     engine-owned prompts, field-map reference,
                                     schema_version for the ledger
      INSTRUCTIONS.md                agent-facing operating instructions
      HOW-TO-USE.md                  producer-facing how-to (Convert and Flow naming)
      MASTERDOC.md                   the SACRED floors (bands, budget, font floor,
                                     keying law) mirrored from PRD Section 3
      REPAIRS.md                     known failure modes and sanctioned repairs
      CHANGELOG.md, skill-version.txt
      anthology-engine-entry.sh      the ONE sanctioned entry: deps check, bypass
                                     scan, manifest hash pin, nonce, fail-closed
      install.sh / preflight.sh      per-box resolution: model map, credential
                                     labels present (SET or NOT SET only), webhook
                                     route registered, cron tick registered
      verify.sh / verify-deps.sh     READ-ONLY idempotent self-verify
      config/
        engine-config.template.json  route path, registry defaults, nudge policy
                                     (7-day re-nudge), hold-queue policy
        model-map.template.json      engine tiers (Section 8), resolved per box,
                                     never an Anthropic identifier
        field-map.json               the PRD Section 6 custom-field keys, the ONLY
                                     place field keys are spelled
        nudge-templates/             the ONLY sanctioned client-facing copy:
                                     gate-open.md, completion.md, stuck-renudge.md,
                                     each with placeholder slots and zero em dashes
        pdf-house-style/             house.css plus per-deliverable HTML templates
                                     (avatar, tone, titles, blurb, outline, chapter,
                                     manuscript), all font sizes tokens at or above
                                     14pt, seeded from the harvested formatter
                                     content rules (Section 6.4)
      scripts/
        intake_router.py             S0: parse, validate hidden fields, tenant
                                     check, dedup, exceptions capture, fast ack
        anthology_state.py           sole ledger writer (Section 7.4)
        anthology_registry.py        per-anthology bindings: Convert and Flow
                                     pipeline and stage map, form ids, Drive folder
        model_router.py              the chain of Section 8 with metering hooks
        search_detect.py             the Section 9 detection ladder, cached
        stage_s1_avatar.py ... stage_s9_assembly.py
                                     one runner per stage; each composes pinned
                                     prompts, calls Layer 1 or the router, runs its
                                     provers, records artifacts, opens its gate
        gate_engine.py               gate state machine; both-door endpoint logic;
                                     scoped-token mint and verify (Section 11.3)
        nudge_send.py                sanctioned templates only; recipient ALWAYS
                                     read from the ledger row, never a literal
        drive_adapter.py             Skill 14 wrapper: Doc create, folder tree,
                                     view-only share, export bundle
        drive-tree-provision.py      idempotent Root/Producer/Anthology/Participant
        pdf_render.py                deterministic HTML-to-PDF (WeasyPrint-class)
        caf_delivery.py              Convert and Flow media upload plus exact-key
                                     custom-field writes plus byte-for-byte read-back
        cover_render.py              Kie.ai GPT-image-2 via Skills 07/46 callback
        qc-tier1-anthology.py        Gate B Tier 1 (per-piece and assembly modes)
        qc-strike-gate.py            both counters: rewrite budget 2, QC attempts 3
        judge_harness.py             Tier 1 semantic checks 13 to 15 plus Tier 2
                                     rubric on the judge tier, never the writer tier
        anthology-cost-ledger.py     metering choke point, per-deliverable budgets
        anthology-smoke-test.py      balance endpoints only, at or under one cent
        hold_queue.py                credit-out hold, age tick, resume from cursor
        exceptions.py                capture, list, resolve-and-replay
        alert-dedup.py               single deduped founder alert path, gateway only
        guard-prompt-pins.py         every pin matches, zero truncation, zero
                                     runtime references to any legacy prompt base
        guard-no-anthropic-runtime.py over the full engine file set plus dashboard
        guard-font-floor.py          proves the RENDERED PDF, not the template
        guard-cron-inventory.py      exactly the one daily tick, no heartbeat entry
        caf_credential_gate.py       label resolution across all three env stores,
                                     pairing proof, anti-commingling fingerprint
        provision-anthology-client.sh / revoke-anthology-client.sh
        verify-webhook-t1-t9.sh      the nine intake proofs (Section 13.2)
      assets/prompts/                engine-OWNED pins only (S9 and routing):
        ae-01-order-curation.md      chapter order proposal (Section 4, S9)
        ae-02-editor-introduction.md producer-voice introduction
        ae-03-contributor-bio.md     bios from ledger identities
        ae-04-front-back-matter.md   front and back matter frames
      fixtures/                      golden participant (full run plus one rewrite),
                                     two-anthology contact, unroutable submission,
                                     aged stuck gate, assembly trio of chapters,
                                     attack variants per guard
      roles/
        anthology-producer-orchestrator.role.md
        anthology-approvals-steward.role.md

3.2 SKILL 54 EXTENSIONS (bounded, exactly three, PRD Section 3.2; each lands as its own pull request in Wave 1 and every existing AF-AW prover must stay green):

1. AVATAR HANDOFF: a pre-P1 avatar phase in ANTHOLOGY-MANIFEST.json that formally delegates to Skill 52 avatar-alchemist prompts 01 to 03 (the exact handoff pattern Skill 53 already models), producing working/avatar.md consumed by P1 fidelity. No Skill 52 file is copied; the handoff references Skill 52's pinned assets.
2. PROMPT COMPLETION: assets/prompts/11-cover-image-prompt.md and 12-primary-goal-extraction.md added and pinned in source_prompt_pins (the manifest's tier table already reserves aw-11 and aw-12); Wave 0 additionally proves the existing 08-create-outline.md and 10-chapter-rewrite.md byte-equal to the corresponding node text INSIDE Outline Agent.json and Chapter Re-Writer Agent.json (the Section 1.4 source of record), and re-pins only if a diff is found (the pin inventory ends COMPLETE either way, which is the actual law; zero truncation; zero [UNCHANGED] placeholders; word band normalized to 2,000 to 3,500).
3. INTAKE FIELDS: aw-intake-schema.json gains optional ideal_avatar, niche, primary_goal (feeding the avatar phase); prove_aw_intake.py keeps rejecting credential-shaped keys.

3.3 REPO PLACEMENT AND ORDER: all Wave 6 merge-train mechanics are as PRD Section 12 (annotated tag v19.0.0 created BEFORE merge; update.sh REGISTERS the new skill directory and corrects the skill count, the change every new-skill merge makes; content_sha restamp via hash-content-manifest.py; fresh-clone verify; repo version v19.0.0, locked, NOT v18; commit and push after every QC pass per the incremental persistence law). The Command Center changes (Anthology department seeding, the home-screen tiles code edit in src/app/page.tsx, the participant token route in middleware.ts) live in the Command Center repo per its own serial train; the engine skill carries only the board and token-page CONTRACT (Section 11), never the Command Center code.

3.4 THE COMPLETE NEW-SCRIPT INVENTORY (normative; every new script the skill ships, with purpose and exit codes; a script missing here does not ship, a shipped script missing here fails Gate A). House convention unless stated: 0 success (including idempotent no-op), 1 unexpected error, 2 validation or guard refusal, 3 dependency unavailable or held, 4 enforced violation detected, 5 data or read-back mismatch.

| # | Script | Purpose | Exit codes |
|---|---|---|---|
| 1 | anthology_state.py | Sole ledger writer: schema bootstrap, transitions, approvals (incl. the s9_ready trigger), readiness report, holds, exceptions, mirror reconcile, export bundle | 0 verified success; 2 illegal transition; 3 unknown key; 4 base unreachable (mirror-queued); 5 validation or confirm-name mismatch |
| 2 | intake_router.py | S0 deterministic intake: secret check, hidden-field validation, tenant check, dedup no-op, exception capture, under-2-second acknowledge, detached stage spawn | 0 routed or no-op; 2 route-secret refusal; 3 captured to Exceptions (typed reason); 4 ledger unreachable |
| 3 | anthology_registry.py | Per-anthology bindings: auto-provisioned pipeline and stage map, form ids, Drive folder | 0; 2 unknown anthology or binding; 5 validation |
| 4 | model_router.py | The Section 8 tier chain, one call site, metering hooks, typed error classes | 0 completion; 2 deny-pattern refusal (Anthropic-shaped id); 3 chain exhausted, job held; 4 budget ceiling block |
| 5 | search_detect.py | Section 9 web-search detection ladder, cached per box | 0 tool detected and cached; 3 no tool (degrade-plus-flag path) |
| 6 | stage_s1_avatar.py through stage_s9_assembly.py (nine runners) | One idempotent runner per stage: compose pins, call Layer 1 or the router, run provers, record artifacts, open the gate | 0 stage complete and persisted; 2 prover failure (counts a QC attempt); 3 held (credits or callback); 5 unresolved prompt slot (AF-AE-SLOT-UNRESOLVED) |
| 7 | gate_engine.py | Gate state machine, both-door single endpoint, scoped-token mint and verify, s9_ready arming | 0 action recorded; 2 invalid or expired token; 3 gate not open |
| 8 | nudge_send.py | The three sanctioned templates only; ledger-resolved recipients; 7-day stuck re-nudge | 0 sent; 2 template or recipient refusal; 3 delivery path unavailable |
| 9 | drive_adapter.py | Direct Drive and Docs API calls with the existing service account (Section 10.1); Doc create, view-only share, export bundle | 0; 3 API unreachable; 5 read-back mismatch |
| 10 | drive-tree-provision.py | Idempotent Producer/Anthology/Participant tree under the EXISTING configured root; never creates a new root | 0 tree verified or created; 2 configured root unreachable; 3 API unreachable |
| 11 | pdf_render.py | Deterministic WeasyPrint-class HTML-to-PDF from the house templates, all font tokens at or above 14 point | 0 rendered; 1 render error; 2 template token below floor |
| 12 | caf_delivery.py | Convert and Flow media upload, exact-key field writes by contact_id, byte-for-byte read-back, control fields | 0 delivered and verified; 2 tenant mismatch; 3 API unreachable; 5 read-back mismatch |
| 13 | cover_render.py | Kie.ai GPT-image-2 via Skills 07 and 46, callback with bounded re-poll, PNG to Drive | 0 PNG landed; 3 callback lost after re-poll (held) |
| 14 | qc-tier1-anthology.py | Gate B Tier 1 deterministic checks, per-piece and assembly modes | 0 all pass; 2 bad invocation; 4 one or more failures (list emitted) |
| 15 | qc-strike-gate.py | Both counters: participant rewrite budget 2 with gate re-entry, internal QC attempts 3, hold-and-alert | 0 within budgets; 4 budget or attempt exhaustion (hold path) |
| 16 | judge_harness.py | Tier 1 semantic checks 13 to 15 plus the Tier 2 ten-dimension rubric on the JUDGE tier | 0 pass; 2 judge tier equals writer tier (independence violation); 4 any dimension below 8 |
| 17 | anthology-cost-ledger.py | Metering choke point, per-deliverable token budgets shared across QC attempts | 0 metered within budget; 4 ceiling exceeded (blocks the call) |
| 18 | anthology-smoke-test.py | Daily funded-reachability probe, balance endpoints ONLY, total spend at or under one cent; ages the hold queue | 0 all reachable and funded; 4 provider unreachable or unfunded (alert path) |
| 19 | hold_queue.py | Durable credit-out and callback holds, daily age tick, resume from exact cursor | 0; 3 still held |
| 20 | exceptions.py | Capture, list, resolve-and-replay through S0 | 0; 3 unknown exception id |
| 21 | alert-dedup.py | Single deduped founder alert path, OpenClaw gateway Telegram only | 0 sent or correctly suppressed; 3 gateway unreachable |
| 22 | guard-prompt-pins.py | Every baked prompt matches its sha256 pin, zero truncation, zero runtime prompt-base references | 0 clean; 4 violation |
| 23 | guard-no-anthropic-runtime.py | Zero Anthropic identifiers across the full engine file set including every Command Center edit (department config, tiles, token route) | 0 clean; 4 violation |
| 24 | guard-font-floor.py | Parses the RENDERED PDF; any glyph below 14 point fails | 0 clean; 4 violation |
| 25 | guard-cron-inventory.py | Exactly the one daily tick; no heartbeat entry ever; churn leaves zero recurring jobs | 0 clean; 4 violation |
| 26 | caf_credential_gate.py | Label resolution across all three env stores (live process env first), pairing proof, anti-commingling fingerprint; reports SET or NOT SET only | 0 all labels resolve and fingerprint clean; 2 missing label; 4 commingling detected |
| 27 | anthology-engine-entry.sh | The ONE sanctioned entry: deps check, bypass scan, manifest hash pin, nonce, fail-closed | 0 run authorized and completed; nonzero fail-closed |
| 28 | install.sh / preflight.sh | Per-box resolution: model map, credential labels, webhook route, cron tick, Drive root reachability | 0 box ready; 2 missing prerequisite (named) |
| 29 | verify.sh / verify-deps.sh | READ-ONLY idempotent self-verify | 0 verified; 4 drift found |
| 30 | provision-anthology-client.sh | Full Section 13.1 provisioning including the auto-provisioned standard pipeline; config writes as the node user | 0 pass gate; nonzero stops SETUP with an operator surface |
| 31 | revoke-anthology-client.sh | Participant gate-token invalidation, Anthology board archival, Drive share revocation, webhook route disable, data export, verification probe | 0 revoked and verified; 4 a probe still answers |
| 32 | verify-webhook-t1-t9.sh | The nine intake proofs of Section 13.2, executed and observed | 0 all nine observed; 4 failing test id emitted |

---

## 4. PIPELINE STAGES S0 TO S9: BUILDABLE CONTRACTS

Format per stage: TRIGGER, INPUTS, PROCESS, PROMPTS AND TIER, PROVERS, ARTIFACTS, GATE, LEDGER EFFECT. All prompts referenced by pin id; verbatim text lives in the baked assets (Section 6), never in this document.

S0 INTAKE AND ROUTING
- TRIGGER: POST on the intake route (universal form or any per-stage form), or an exceptions-queue replay.
- INPUTS: visible fields (first name, last name, email, phone, Q1 ideal avatar, Q2 niche, Q3 primary goal, or the stage form's own fields); hidden fields contact_id, anthology_id, stage; producer and producer_email ride the webhook payload per the anthology registry binding.
- PROCESS (intake_router.py, no model call): verify the route secret; validate hidden-field presence and shape; tenant check (payload location must equal the registry's Convert and Flow Location binding for that anthology); dedup by submission fingerprint (idempotency key: sha256 of contact_id, anthology_id, stage, and the payload body) with acknowledged no-op on replay; upsert the participant via anthology_state.py upsert-participant; stage validation against the ledger cursor (a tone form arriving for a participant at S4 is an exception, not a guess); provision the Drive path via drive-tree-provision.py on first sight; acknowledge under 2 seconds; spawn the stage job detached.
- FAILURE: any unresolvable submission goes to Exceptions with the raw payload and a typed reason (unroutable_missing_ids, unknown_anthology, stage_mismatch, tenant_mismatch); NEVER dropped, NEVER guessed.
- LEDGER EFFECT: participant created or cursor confirmed; timestamps stamped.

S1 AVATAR (gate: producer)
- INPUTS: ideal_avatar, niche, primary_goal, participant name, tone placeholder.
- PROCESS: run the Skill 52 handoff sequence: Avatar Questions 1 to 30 (pin aa-01), then the Section 9 search pass feeding Questions 31 and 32 (pin aa-02) with findings injected as context (the pinned prompt text itself is never edited at runtime), then Rewrite Avatar Niche and Primary Goal (pin aa-03), then Primary Goal extraction (pin aw-12, LIGHT tier).
- TIER: MID-WRITER for aa-01 to aa-03; LIGHT for aw-12; the search pass is a Layer 2 tool step, not a model swap.
- PROVERS: guard-prompt-pins.py (pins matched); qc-tier1-anthology.py checks 4 to 12.
- ARTIFACTS: avatar.md; Avatar Doc plus PDF at S8 standards; carried values niche_primary_goal, questions_1_30, questions_31_32.
- GATE: producer Approve or Hold in the dashboard, nudge deep-link in.

S2 TONE (gate: producer)
- INPUTS: the tone form (describe_tone plus four influences: well_known_figure, infl_2, infl_3, infl_4; legacy field labels preserved for participant continuity).
- PROCESS: Skill 54 P2 TONE using shared-utils/tone-writing-core prompts 04 to 08 byte-identically; Write Tone Style 1 to 4 then Write Blended Tone.
- PROVERS: verify_tone_core_sync.py; prove_aw_tone.py (exactly 4 influences; 3,000 MEASURED words minimum on the stripped text).
- ARTIFACTS: tone-doc.md, blended_tone; Tone Doc plus PDF.
- GATE: producer. The nudge recipient is the ledger email for this contact_id; no literal recipient exists anywhere in the engine (the legacy hardcoded-test-inbox class is structurally impossible).

S3 TITLE (gate: participant selection)
- INPUTS: chapter_about, personal_stories (title form); avatar and tone context.
- PROCESS: Skill 54 P4 with pin aw-06 (Suggested Titles); deliver Titles Doc plus PDF; the participant picks title and subtitle in the dashboard gate view (or nudge link).
- PROVERS: the AF-AW-TITLE-LOCK prover records title and subtitle byte-exact in the ledger (title_locked, subtitle_locked) and enforces the byte-exact carry through outline, chapter, every rewrite, and the cover prompt.
- LEDGER EFFECT: TITLE LOCK is a one-way transition; changing it afterward requires a producer-initiated exception.

S4 BLURB PLUS OUTLINE (gates: producer, then participant)
- INPUTS: locked title and subtitle, author name, niche_primary_goal, questions, blended_tone, chapter_about, personal_stories.
- PROCESS: Book Blurb (pin aw-07), then single-chapter Create Outline (pin aw-08) placing EVERY personal story strategically.
- PROVERS: story-placement prover (every story present in the outline); title-lock carry.
- ARTIFACTS: blurb.md, outline.md; both Docs plus PDFs.
- GATES: producer approval, then participant outline approval. THERE IS NO OUTLINE RE-UPLOAD; the approved outline is carried forward by the ledger (legacy Chapter Form's re-upload request is deleted, not ported; a static route check proves no upload path exists).

S5 CHAPTER (gate: participant, exactly two actions)
- INPUTS: everything above, from the ledger, never re-asked.
- PROCESS: Skill 54 P5 with pin aw-09 (Write Chapter): ONE complete chapter.
- PROVERS BEFORE THE GATE OPENS: prove_aw_chapter.py (2,000 to 3,500 MEASURED stripped words, self-report ignored; title lock; every story placed; no placeholder; no verify-block leakage), then Gate B Tier 1 full set, then the Tier 2 rubric on the judge tier. The participant NEVER sees an ungated draft.
- GATE: Approve as-is, or Request rewrite with notes. Notes append verbatim to chapter_updates.

S6 CHAPTER REWRITE (optional, budget 2, re-enters the S5 gate)
- INPUTS: current chapter, chapter_updates.
- PROCESS: pin aw-10 (the Thornfield editorial-revision persona) rewrites inside the band with the title lock held.
- PROVERS: same chapter provers; qc-strike-gate.py owns rewrite_count (max 2) and qc_attempts_current (max 3 internal per deliverable). At budget exhaustion the gate offers Approve as-is or escalate to producer; a silent third rewrite is an illegal transition the writer refuses.

S7 COVER IMAGE
- INPUTS: locked title and subtitle, author name, blurb.
- PROCESS: pin aw-11 (cover prompt generator, structured output: an image prompt object) on MID-WRITER; render via the client's own Kie.ai account, model GPT-image-2, PORTRAIT 1024x1536, through Skill 07 setup and Skill 46 callback relay, against the Kie TEXT-TO-IMAGE portrait endpoint VERIFIED at Wave 0 (the 16:9 presentation image recipe is a different endpoint shape and is NEVER reused here); bounded re-poll on a lost callback, then hold plus alert.
- ARTIFACTS: cover PNG in the participant's Drive folder; both link fields captured.

S8 PACKAGE AND DELIVER (runs per deliverable as each stage completes, and as a full sweep at participant completion)
- PROCESS, per deliverable: (1) Google Doc into the Drive tree via drive_adapter.py; (2) designed PDF via pdf_render.py from the house template for that deliverable type, then guard-font-floor.py over the RENDERED file (every rendered glyph at or above 14 point); (3) upload Doc export and PDF to Convert and Flow media storage; (4) push both hosted links to the exact PRD Section 6 field keys via caf_delivery.py, keyed by contact_id, then read every field back byte-for-byte; (5) update the three control fields (anthology_active_id, anthology_stage, anthology_rewrite_count); (6) completion notice through the sanctioned template; (7) at participant completion, the signed process certificate (Skill 54 P7 pattern) and the Command Center card to review via mc_board.py.
- The five legacy LLM HTML-formatter calls are RETIRED; their typography and structure rules are harvested into the house templates as deterministic CSS and markup (Section 6.4).

S9 ANTHOLOGY ASSEMBLY (new; TWO producer decisions: the ready-to-assemble trigger opens it, final sign-off closes it)
- TRIGGER (the producer "I'm ready to assemble" signal, PRD Section 3.11; never automatic): when every participant is at approved or explicitly excluded, anthology_state.py arms the trigger and the approvals steward fires ONE readiness nudge to the producer; the producer fires the trigger from the Assembly card on the Anthology board or the nudge deep link (both doors, one endpoint), which shells anthology_state.py record-approval --gate s9_ready. GUARDS enforced by the writer, not the UI: own-producer auth (the box owner's Command Center session or a producer-scoped token); every participant approved or carrying an explicit exclude approvals row; at least 2 frozen approved chapters (per-anthology configurable, floor 2); typed anthology-name confirmation echoed into the subcommand as --confirm-name (mismatch exits 5); one-way (re-firing is an acknowledged no-op; reopening collection is a producer-initiated exception that voids in-progress assembly). On success the anthology moves ready_to_assemble and the assembly job spawns.
- PROCESS: (1) ORDER CURATION (pin ae-01): propose chapter order applying the verified anthology craft: strongest pieces open and close, long-short alternation so long chapters never cluster, deliberate tone-shift management, subtheme grouping and paired contrasts; the proposal writes to the anthology record with its rationale and the producer adjusts in the dashboard; (2) editor's introduction and framing device in the producer's voice (pin ae-02) built ONLY from producer-supplied inputs, never fabricated; (3) front matter and back matter (pin ae-04); (4) contributor bios from ledger identities (pin ae-03); (5) compile the manuscript from FROZEN approved chapter artifacts, byte-identical check per chapter, on the optional 1M-context tier when configured, else chunked on the primary chain; (6) assembly-scope Gate B (every approved chapter present exactly once, order matches curation, introduction references only real contributors, one continuous 14-point-floor PDF); (7) producer sign-off; (8) manuscript Doc plus PDF delivered and manuscript fields pushed.

CROSS-CUTTING AT EVERY STAGE: every transition through anthology_state.py; every billable call metered by anthology-cost-ledger.py before and after; insufficient-credits HOLDS the job durably with one deduped founder alert (the exact class that killed the legacy system twice, on record); duplicate deliveries acknowledge without a second run; no stage blocks on a human.

---

## 5. THE NODE TO SKILL-COMPONENT MAPPING (THE HEART OF THE N8N RETIREMENT)

Every meaningful node or node cluster of the eight live workflows, mapped to its engine equivalent and disposition. Vocabulary: REPLACE (function survives, new implementation), REUSE (an existing fleet asset covers it), RETIRE (the function itself is eliminated by design), DELETE (defect or plumbing with no successor), HARVEST (content extracted at Wave 0, then retired). Node names are exact from the live graphs; workflows are referenced by their LEGACY-* labels (identifiers live only in the Wave 0 build-state file).

5.1 MAIN ORCHESTRATOR, LEGACY-MAIN (81 nodes):

| # | Node(s) | Legacy function | Engine equivalent | Disposition |
|---|---|---|---|---|
| M1 | Webhook (POST anthology) | Intake entry; secret-less; key rides in payload | Gateway route /hooks/anthology-intake with ANTHOLOGY_INTAKE_HOOK_SECRET; intake_router.py | REPLACE |
| M2 | Get Avatar Stage Anthology Opps. (getAll limit 1, pipeline filter) + Filter by Contact ID | Opportunity list-then-filter; the Gap 7 race | Direct contact_id keying in the ledger; no opportunity list-then-filter anywhere; registry binds pipeline per anthology | RETIRE |
| M3 | Producer Folder, Book ID Folder, All Chapters Folder, Client Chapter Folder (Drive fileFolder search) | Four-level folder lookups | drive-tree-provision.py idempotent get-or-create of Root/Producer/Anthology/Participant | REPLACE |
| M4 | Get/Create Folder, Get/Create Folder1..3 (if) + Create Folder, Create Folder1..3 + Get FolderID, Get FolderID1..3 + Edit Fields, 1, 3, 5, 6, 7 (folderId staplers), 16 nodes | Branchy folder create-or-reuse plumbing | Same single script, one code path | REPLACE |
| M5 | personal_folderID, book_chapter_folder (context staplers; personal_folderID also lifts the routing credential from customData) | Item-chain state; credential in payload | Ledger row is the state; credential-in-payload pattern eliminated; model calls resolve keys by label from client env stores | DELETE (credential path) / REPLACE (state) |
| M6 | Avatar Agent (executeWorkflow) | Dispatch S1 | stage_s1_avatar.py with the Skill 52 handoff | REPLACE |
| M7 | Avatar Confirmation (Gmail sendAndWait, 45-day cap) | Producer avatar gate over email | gate_engine.py S1 producer gate; dashboard system of record; nudge deep-link; no timeout, ledger holds | REPLACE |
| M8 | Update to Tone Stage1, Update to Title Stage1, Update to Outline Stage1, Update to Chapter Writer, Update to Chapter Writer1..5 (opportunity stage updates; nine hardcoded stage bindings, Gap 6) | Convert and Flow pipeline stage sync | anthology_state.py advance-stage plus contact.anthology_stage field push; optional per-anthology opportunity-stage sync via the registry caf_stage_map, bound at provisioning, nothing hardcoded | REPLACE |
| M9 | Tone Form (Gmail sendAndWait; sends to a HARDCODED TEST INBOX, the live Gap 5 defect) | Tone questionnaire by mail-wait | Convert and Flow tone form (same field labels) routed through S0; recipient always the ledger email; the legacy defect dies at FREEZE and RETIRE (no engine-side patch of legacy) | REPLACE |
| M10 | Title Form (sendAndWait) | Collects chapter_about, personal_stories | Convert and Flow title-stage form through S0 | REPLACE |
| M11 | Outline Form (sendAndWait) | Collects the title and subtitle choice | Dashboard title-selection gate (S3) plus form fallback through S0 | REPLACE |
| M12 | Chapter Form (sendAndWait) | Requests MANUAL OUTLINE RE-UPLOAD (Gap 9) | Deleted; the ledger carries the approved outline forward; static check proves no upload path | DELETE |
| M13 | Tone Confirmation, Title Confirmation, Outline Confirmation, Producer Avatar Confirmation (sendAndWait producer gates) | Stage approval gates over email | gate_engine.py producer gates S2, S3, S4; both-door endpoint | REPLACE |
| M14 | Avatar Data, Tone Data, Title Data, Title Writer4 (context staplers between stages) | Re-assemble the full variable set per stage | Ledger reads; stage runners load the participant row, nothing re-stapled | REPLACE |
| M15 | Gmail (sendAndWait Approve or Re-Write) + If | The chapter gate, one-shot | S5 two-action gate; qc-strike-gate.py budget 2 with S5 gate re-entry (legacy one-shot is Gap 8) | REPLACE |
| M16 | Re-Write Form (sendAndWait) + Title Writer2 (adds chapter_updates) | Collect rewrite notes | Notes field ON the chapter gate (dashboard or nudge link), appended verbatim to chapter_updates | REPLACE |
| M17 | Copy file, Copy file1 (Drive copy) + Create file from text, Create file from text1 | Duplicate Doc-copy plumbing on the approve and rewrite branches (Gap 8 duplication) | drive_adapter.py single path; versioned Artifact rows | REPLACE |
| M18 | Execute Workflow, Execute Workflow2 (both call Single Chapter Cover Image Gen) | Cover dispatch, duplicated per branch | stage_s7_cover.py, one path | REPLACE |
| M19 | Execute Workflow3 (calls Chapter Re-Writer Agent) | Rewrite dispatch | stage_s6_rewrite.py | REPLACE |
| M20 | Trigger Title Writing Agent1 (executeWorkflow) | Title dispatch | stage_s3_title.py | REPLACE |
| M21 | Chapter Agent, Outline Agent, Tone Agent (executeWorkflow dispatchers) | Sub-workflow dispatch | stage runners S5, S4, S2 | REPLACE |
| M22 | Producer Avatar Confirmation1, Producer Avatar Confirmation2, Gmail1, Gmail2 (completion notices, duplicated per branch) | Completion emails | S8 sanctioned completion template, one path, ledger recipient | REPLACE |
| M23 | Sticky Note, Sticky Note1, 5, 6, 7, 8, 9, 10, 11, 12 (10 nodes) | Canvas annotations | Nothing; documentation lives in SKILL.md | DELETE |
| M24 | pinData on the export (captured live payloads including credential values) | Test data | Exports scrubbed or deleted at Wave 0; fixtures are synthetic | DELETE |

5.2 AVATAR AGENT, LEGACY-AVATAR (29 nodes):

| # | Node(s) | Legacy function | Engine equivalent | Disposition |
|---|---|---|---|---|
| A1 | When Executed by Another Workflow | Sub-workflow entry | Function entry of stage_s1_avatar.py | REPLACE |
| A2 | Airtable, Airtable40, Airtable2 (search on Avatar Alchemist BI Prompts) | RUNTIME prompt fetch by record name | Baked sha256-pinned prompts aa-01, aa-02, aa-03 (Skill 52 assets); zero runtime prompt-base calls (PRD decision 3.4) | RETIRE |
| A3 | Edit Fields2, 3, 4 (user_stringify staplers) | Prompt-variable interpolation | Deterministic template fill from the ledger row (Section 6.2 variable map) | REPLACE |
| A4 | Avatar Questions 1-30 (chainLlm) + OpenRouter Chat Model (legacy Anthropic id, replaced) | Q1 to 30 generation | MID-WRITER tier call with pin aa-01 | REPLACE |
| A5 | Avatar Questions 31-32 (openAi node, web-search model gpt-4o-search-preview) | Live research for real links | Section 9 detection ladder tool step, findings injected into pin aa-02; degrade-plus-flag path when no tool | REPLACE |
| A6 | Rewrite Avatar Niche and Primary Goal (chainLlm, legacy Anthropic id) | Rewrite pass | MID-WRITER with pin aa-03 | REPLACE |
| A7 | Primary Goal (chainLlm, legacy gpt-4.1) + Edit Fields5 | Primary-goal extraction | LIGHT tier with pin aw-12 (Wave 0 rescue) | HARVEST then REPLACE |
| A8 | HTML Avatar (chainLlm, legacy gemini-3.1-pro-preview) + Edit Fields6 (system 3,016, assistant 13,953) | LLM HTML formatting | RETIRED formatter; content rules harvested into the avatar house template | HARVEST then RETIRE |
| A9 | HTTP Write Tone Style, HTTP Write Tone Style 3, HTTP Write Tone Style 4, HTTP Suggested Titles, HTTP Suggested Titles1 (raw OpenRouter completions calls using the payload-borne key; dual-wired beside the chainLlm path) | Second, credential-in-payload model path | model_router.py is the ONLY call path; keys by label; deny patterns refuse Anthropic ids | DELETE |
| A10 | Edit Fields10 (cleaned_titles) + Code2 + Google Drive11 + HTTP Request (Drive copy) + Google Drive12 (deleteFile) | HTML-to-Doc conversion dance (create, copy, delete) | drive_adapter.py single create; PDF via pdf_render.py | REPLACE |
| A11 | Edit Fields (return stapler: avatar_link, questions_1_30, questions_31_32, niche_primary_goal, primary_goal, html_avatar) | Return values | Artifact row plus Participants columns | REPLACE |

5.3 TONE AGENT, LEGACY-TONE (36 nodes):

| # | Node(s) | Legacy function | Engine equivalent | Disposition |
|---|---|---|---|---|
| T1 | When Executed by Another Workflow | Entry | stage_s2_tone.py entry | REPLACE |
| T2 | Airtable3, 4, 5, 6, 7 (five prompt fetches) | Runtime fetch of Write Tone Style 1 to 4 and Write Blended Tone | shared-utils/tone-writing-core prompts 04 to 08 via Skill 54 P2, byte-identical, lockstep-proven | RETIRE |
| T3 | Write Tone Style 1, 2, 3, 4 (chainLlm, legacy Anthropic ids) + Write Blended Tone (chainLlm) | The five tone generations | Skill 54 P2 on MID-WRITER; prove_aw_tone.py (4 influences, 3,000 measured words) | REUSE (Skill 54) |
| T4 | Edit Fields, 1, 2, 3, 4 (staplers) + HTTP Write Tone Style 1, 2, 3, 5, HTTP Write Blended Tone (raw key-in-payload calls, dual-wired) | Second model path | model_router.py only | DELETE |
| T5 | HTML Tone (chainLlm) + Edit Fields5 (system 4,005, assistant 10,492) + HTTP HTML Tone | LLM HTML formatting | Retired formatter; tone house template | HARVEST then RETIRE |
| T6 | Edit Fields11 + Code3 + Google Drive13 + HTTP Request13 + Google Drive14 | HTML-to-Doc dance | drive_adapter.py plus pdf_render.py | REPLACE |
| T7 | Return DAta (blended_tone, html_tone, tone_doc) | Return | Artifact row; blended_tone on the participant row | REPLACE |

5.4 TITLE WRITER AGENT, LEGACY-TITLE (15 nodes):

| # | Node(s) | Legacy function | Engine equivalent | Disposition |
|---|---|---|---|---|
| TI1 | When Executed by Another Workflow + Edit Fields5 (Suggested Titles prompt inline: system 2,918, assistant 70,321, the estate's largest) | Entry plus prompt staging | stage_s3_title.py with Skill 54 pin aw-06 (byte-equality to the live node proven at Wave 0) | REUSE (Skill 54) |
| TI2 | Suggested Titles (chainLlm, legacy Anthropic id) + HTTP Suggested Titles (raw path) | Title generation | MID-WRITER via Skill 54 P4 | REPLACE / DELETE (raw path) |
| TI3 | HTML Suggested Titles (chainLlm, legacy gemini-2.5-pro) + Edit Fields6 (system 3,016, assistant 18,363) + HTTP HTML Tone1 | LLM HTML formatting | Retired; titles house template | HARVEST then RETIRE |
| TI4 | Edit Fields9 + Code1 + Google Drive9 + HTTP Request12 + Google Drive10 | HTML-to-Doc dance | drive_adapter.py plus pdf_render.py | REPLACE |
| TI5 | Edit Fields (titles, html_titles, title_doc) | Return | Artifact row; TITLE LOCK recorded at the gate, not here | REPLACE |

5.5 OUTLINE AGENT, LEGACY-OUTLINE (19 nodes):

| # | Node(s) | Legacy function | Engine equivalent | Disposition |
|---|---|---|---|---|
| O1 | When Executed by Another Workflow + Edit Fields5 (Book Blurb prompt: system 541, assistant 1,607) | Entry plus blurb staging | stage_s4_blurb_outline.py with pin aw-07 | REUSE (Skill 54) |
| O2 | Book Blurb (chainLlm, legacy Anthropic id) + HTTP Suggested Titles (raw path) | Blurb generation | MID-WRITER | REPLACE / DELETE (raw) |
| O3 | Edit Fields6 (single-chapter Create Outline prompt: user 2,435, system 7,251, assistant 11,191; Wave 0 rescue target) + Create Outline (chainLlm, legacy Anthropic id) + HTTP Suggested Titles1 | Outline generation | Pin aw-08 (byte-proven or re-pinned at Wave 0); story-placement prover | HARVEST then REUSE |
| O4 | Edit Fields7 (HTML Outline prompt: system 3,016, assistant 12,795) + HTML Outline (chainLlm) + HTTP Suggested Titles2 | LLM HTML formatting | Retired; outline house template | HARVEST then RETIRE |
| O5 | Edit Fields12 + Code + Google Drive15 + HTTP Request14 + Google Drive16 | HTML-to-Doc dance | drive_adapter.py plus pdf_render.py | REPLACE |
| O6 | Edit Fields (blurb, outline, html_outline, outline_doc) | Return | Artifact rows | REPLACE |

5.6 CHAPTER AGENT, LEGACY-CHAPTER (15 nodes):

| # | Node(s) | Legacy function | Engine equivalent | Disposition |
|---|---|---|---|---|
| C1 | When Executed by Another Workflow + Edit Fields5 (Write Chapter prompt: user 773, system 6,025, assistant 49,756; already captured verbatim in the inline companion) | Entry plus prompt staging | stage_s5_chapter.py with Skill 54 pin aw-09 via P5 | REUSE (Skill 54) |
| C2 | Write Chapter (chainLlm, legacy Anthropic id) + HTTP Suggested Titles (raw path) | The chapter generation | HEAVY-WRITER (GLM 5.2 chain); prove_aw_chapter.py measures the band | REPLACE / DELETE (raw) |
| C3 | Edit Fields6 (Chapter HTML formatter: system 4,987, assistant 10,262) + HTML Outline (chainLlm; the node is misnamed in the live graph, it formats the chapter) + HTTP Suggested Titles2 | LLM HTML formatting | Retired; chapter house template | HARVEST then RETIRE |
| C4 | Edit Fields13 + Code4 + Google Drive17 + HTTP Request15 + Google Drive18 | HTML-to-Doc dance | drive_adapter.py plus pdf_render.py | REPLACE |
| C5 | Edit Fields (chapter, chapter_doc) | Return | Artifact row, frozen on approval | REPLACE |

5.7 CHAPTER RE-WRITER AGENT, LEGACY-REWRITER (15 nodes; graph-isomorphic to the Chapter Agent):

| # | Node(s) | Legacy function | Engine equivalent | Disposition |
|---|---|---|---|---|
| R1 | When Executed by Another Workflow + Edit Fields5 (Thornfield editorial persona: user 791, system 7,113, assistant 30,626; Wave 0 rescue target) | Entry plus rewrite prompt | stage_s6_rewrite.py with pin aw-10 (byte-proven or re-pinned at Wave 0) | HARVEST then REUSE |
| R2 | Write Chapter (chainLlm, legacy Anthropic id) + HTTP Suggested Titles (raw path) | Rewrite generation with chapter_updates | HEAVY-WRITER; band and title lock held; budget 2 by qc-strike-gate.py | REPLACE / DELETE (raw) |
| R3 | Edit Fields6 (Book-to-HTML formatter: system 4,987, assistant 10,262) + HTML Outline (chainLlm) + HTTP Suggested Titles1 | LLM HTML formatting | Retired; chapter house template | HARVEST then RETIRE |
| R4 | Edit Fields13 + Code4 + Google Drive17 + HTTP Request15 + Google Drive18 | HTML-to-Doc dance | drive_adapter.py plus pdf_render.py | REPLACE |
| R5 | Edit Fields (chapter, chapter_doc; legacy names the Doc Init_Chapter) | Return | New VERSION row in Artifacts; re-enters the S5 gate | REPLACE |

5.8 SINGLE CHAPTER COVER IMAGE GEN, LEGACY-COVER (11 nodes):

| # | Node(s) | Legacy function | Engine equivalent | Disposition |
|---|---|---|---|---|
| V1 | When Executed by Another Workflow + Edit Fields2 (cover prompt generator: system 2,135, assistant 11,904; Wave 0 rescue target) | Entry plus prompt staging | stage_s7_cover.py with pin aw-11 | HARVEST then REPLACE |
| V2 | Prompt Writer 2 (chainLlm, legacy gpt-4.1) + Structured Output Parser + OpenRouter Chat Model, OpenRouter Chat Model21 | Image-prompt generation, structured | MID-WRITER with structured output contract (image prompt object) | REPLACE |
| V3 | HTTP Write Tone Style 3 (raw key-in-payload path) | Second model path | model_router.py only | DELETE |
| V4 | Image Generation (OpenAI Image 1) (httpRequest to the legacy image API with a LITERAL authorization header, the Gap 3 exposed key; legacy gpt-image-1 portrait 1024x1536) | Cover render | Client's own Kie.ai, GPT-image-2, portrait, via Skills 07 and 46 callback pattern; the exposed key ROTATED at Wave 0; caf_credential_gate.py forbids literal headers | DELETE (node and key) then REPLACE |
| V5 | Convert to File + Google Drive1 | PNG to Drive | drive_adapter.py PNG landing in the participant folder | REPLACE |
| V6 | Edit Fields (image_prompt, image_file) | Return | Artifact row (type cover), both link fields | REPLACE |

5.9 MAPPING TOTALS AND THE RETIREMENT INVARIANT. 69 mapping rows cover all 221 live nodes (81 plus 29 plus 36 plus 15 plus 19 plus 15 plus 15 plus 11). Dispositions: no node survives as n8n; every generation function lands on a pinned prompt and a routed tier; every mail-wait gate becomes a ledger gate; every runtime prompt fetch becomes a baked pin; both credential-exposure paths are deleted and their keys rotated. The INVARIANT the build gate scores: for every row above, either the named engine component exists and its prover passes, or the build is not done. The build makes NO changes to any legacy n8n workflow: legacy participant migration and bridge workflows are OUT OF CORE SCOPE (PRD Section 8; the single optional line is PRD Section 18); the legacy stack is only harvested (Wave 0), frozen, and eventually retired.

---

## 6. PROMPT AND AGENT DESIGN

6.1 THE COMPLETE PIN INVENTORY (the engine's entire prompt surface; verbatim text lives ONLY in the baked assets; sha256 values are stamped into the manifests at Wave 0/W1.3 and proven by guard-prompt-pins.py at merge and at runtime):

| Pin id | Prompt | Baked location | Verbatim source of record |
|---|---|---|---|
| aa-01 | Avatar Questions 1 to 30 | Skill 52 prompts/01 (existing pin) | Avatar-tone companion doc; legacy table LEGACY-TBL-AVATAR |
| aa-02 | Avatar Questions 31 to 32 | Skill 52 prompts/02 (existing pin) | Same |
| aa-03 | Rewrite Avatar Niche and Primary Goal | Skill 52 prompts/03 (existing pin) | Same |
| tone-04..08 | Tone Styles 1 to 4, Blended Tone | shared-utils/tone-writing-core (existing pins) | Same companion; lockstep law |
| aw-06 | Suggested Titles | 54/assets/prompts/06 (existing pin; Wave 0 byte-proof vs Title Writer Agent.json Edit Fields5) | Title Writer Agent.json export |
| aw-07 | Book Blurb | 54/assets/prompts/07 (existing pin) | Outline Agent.json Edit Fields5 |
| aw-08 | Create Outline (single-chapter) | 54/assets/prompts/08 (Wave 0 byte-proof vs Outline Agent.json Edit Fields6; re-pin on diff) | Outline Agent.json export; PRD Gap 1 |
| aw-09 | Write Chapter | 54/assets/prompts/09 (existing pin; word band normalized to 2,000 to 3,500) | Inline companion (complete) |
| aw-10 | Chapter Rewrite (Thornfield persona) | 54/assets/prompts/10 (Wave 0 byte-proof vs Chapter Re-Writer Agent.json Edit Fields5; re-pin on diff; the paired Book-to-HTML formatter text has its 10 [UNCHANGED] placeholders restored from the CSV HTML Book record before its content rules are harvested) | Chapter Re-Writer Agent.json export plus Full Book Prompts-Grid view.csv; PRD Gaps 1 and 2 |
| aw-11 | Book Cover Image Prompt Generator | 54/assets/prompts/11 (NEW, Wave 0 ingestion from Single Chapter Cover Image Gen.json Edit Fields2) | Single Chapter Cover Image Gen.json export; PRD Gap 1 |
| aw-12 | Primary Goal extraction | 54/assets/prompts/12 (NEW, Wave 0 ingestion from Avatar Agent.json) | Avatar Agent.json export; PRD Gap 1 |
| ae-01..04 | Order curation, editor introduction, contributor bio, front and back matter | engine assets/prompts (NEW, authored in W1.18 from the S9 craft spec) | This SPEC Section 4 S9 |
| harvested, not pinned | The five HTML formatter prompts (avatar, tone, titles, outline, chapter/book) | NOWHERE as prompts; content rules distilled into config/pdf-house-style templates | Live nodes, HARVEST-ONLY (typography and structure rules) |

6.2 VARIABLE MAPPING (legacy interpolation to engine fields). Legacy prompts interpolate Make.com-style and n8n-style variable expressions like {{ 2.customData.Idealavatar }}, {{ $json.first_Name }}, {{ $('Avatar Agent').item.json.blended_tone }}. The engine's prompt composer maps EVERY such Make.com/n8n variable slot to its canonical field name and fills the SAME slots from the canonical field dictionary (Appendix B) via a deterministic template pass; the pinned prompt bodies are never mutated beyond slot substitution, and the composer refuses any unresolved slot (fail-closed, AF-AE-SLOT-UNRESOLVED). Canonical mapping: Idealavatar to ideal_avatar; niche to niche; primarygoal to primary_goal; firstname plus lastname to first_name, last_name; tone to blended_tone (post-S2) or the intake tone placeholder (S1); Anthologyproducer and Anthologyproduceremail to the producer record; Bookid to anthology_id (the legacy book_id concept is subsumed); chapter_about, personal_stories, title, subtitle, blurb, outline, chapter, chapter_updates map one-to-one.

6.3 PERSONA MATCHING (concrete, stage by stage; the normative table is PRD Section 13 and it binds this build the way the Podcast engine bound its stages to Skill 23 AI Workforce Blueprint roles). Personas live inside the pinned prompts, never in runtime config; each pipeline stage is OPERATED by a named books-department role and SPOKEN by a named persona: S0 and S8 by anthology-producer-orchestrator with no persona (deterministic code); S1 by anthology-chapter-author speaking the Avatar Profiler (Skill 52's marketing-psychologist, aa-01 to aa-03); S2 the Tone Analysts and Blender (tone core 04 to 08); S3 the Senior Title Strategist (aw-06); S4 the Blurb Copywriter (aw-07) and the Outline Architect (aw-08); S5 the Anthology Chapter Author (aw-09); S6 Dr. Margaret Thornfield, the editorial revisionist (aw-10); S7 by anthology-producer-orchestrator speaking the Senior Book-Cover Design Specialist (aw-11); every gate, nudge, and the readiness report by anthology-approvals-steward; S9 machinery by anthology-producer-orchestrator with the Anthology Editor voice (ae-01 to ae-04, always subordinate to the producer's supplied voice inputs); Gate B judge passes by anthology-approvals-steward as the independent Editorial Judge on the JUDGE tier. These stage-to-role-to-persona bindings are stamped into the fleet persona-matching config at W4.4 so the client's workforce self-invokes the right operator per stage. QC INDEPENDENCE LAW: the judge harness never runs a persona or tier that drafted the piece under review.

6.4 OUTPUT HYGIENE (applies after every generation, before any prover): strip stage labels and system-prompt leakage; verify zero em dash characters and zero code fences in prose deliverables (Gate B Tier 1 checks 5 and 6); reject and internally retry on violation (counts against the three QC attempts). The harvested formatter rules that survive into the house templates: Google-Docs-safe semantic HTML, heading hierarchy, no font below 14 point, generous leading and paragraph spacing, list and quote emphasis conventions, per-deliverable title blocks; implemented as CSS tokens and template structure, not as model behavior.

---

## 7. THE DATA MODEL (AIRTABLE-BACKED LEDGER PLUS LOCAL MIRROR)

This section compiles design/data-model-design.md into buildable schema. One NEW base per deployment, working name Anthology Engine State, created by provision-anthology-client.sh through the ledger writer's schema bootstrap; referenced at runtime by base id from the client env store under the label ANTHOLOGY_STATE_BASE_ID with the Airtable credential under its existing label. The legacy bases in Section 1.2 are NEVER referenced by any runtime file.

7.1 TABLES AND FIELDS (Airtable field types in brackets; the SQLite mirror uses the same names):

PRODUCERS: producer_id [singleLineText, primary], producer_email [email], display_name [singleLineText], drive_root_folder_id [singleLineText], status [singleSelect: active, revoked], created_at [dateTime].

ANTHOLOGIES: anthology_id [singleLineText, primary], producer_id [link to Producers], name [singleLineText], theme [multilineText], status [singleSelect: setup, open, writing, ready_to_assemble, assembling, delivered, archived], caf_location_binding [singleLineText, a label reference], caf_pipeline_binding [singleLineText, label reference], caf_stage_map [multilineText json], form_ids [multilineText json], drive_folder_id [singleLineText], chapter_order [multilineText json array of participant_keys], assembly_state [singleSelect: not_ready, armed, ready_confirmed, proposed, adjusted, compiled, signed_off], min_chapters [number, default 2, the ready-trigger floor], assembly_ready_at [dateTime, stamped by the s9_ready approvals row], created_at, updated_at [dateTime].

PARTICIPANTS: participant_key [singleLineText, primary, the literal composite contact_id::anthology_id], contact_id [singleLineText], anthology_id [link], first_name, last_name [singleLineText], email [email], phone [phoneNumber], ideal_avatar, niche, primary_goal [multilineText], stage_cursor [singleSelect: s0_intake, s1_avatar, s1_gate, s2_tone, s2_gate, s3_title, s3_gate, s4_blurb_outline, s4_gate_producer, s4_gate_participant, s5_chapter, s5_gate, s6_rewrite, s7_cover, s8_deliver, s9_wait_assembly, approved, delivered, held, exception], rewrite_count [number 0..2], qc_attempts_current [number 0..3], tone_inputs [multilineText json], chapter_about [multilineText], personal_stories [multilineText json], title_locked, subtitle_locked [singleLineText], chapter_updates [multilineText json, append-only], hold_reason [singleLineText], stage_timestamps [multilineText json], created_at, updated_at [dateTime]. KEYING LAW: contact_id, never email; one human in two anthologies is two rows sharing one contact_id.

ARTIFACTS: artifact_id [singleLineText, primary], participant_key [link; or anthology-scope for manuscript artifacts], type [singleSelect: avatar, tone, titles, blurb, outline, chapter, rewrite, cover, anthology_manuscript], version [number], drive_doc_id [singleLineText], doc_url, pdf_url, caf_media_url [url], custom_field_keys_written [multilineText json], sha256 [singleLineText], prompt_pin_sha256 [singleLineText], model_used [singleLineText, honest, never an Anthropic id by deny-pattern], frozen [checkbox], created_at [dateTime]. The current version is the highest per type; approval freezes the row; S9 consumes only frozen chapter rows, byte-identical by sha256.

APPROVALS (append-only): approval_id [primary], subject_key [participant_key or anthology_id], gate [singleSelect: s1_producer, s2_producer, s3_selection, s4_producer, s4_participant, s5_participant, s9_ready, s9_producer], actor [singleSelect: producer, participant], decision [singleSelect: approve, request_rewrite, escalate, hold, exclude, ready_to_assemble], notes [multilineText, feeds chapter_updates verbatim when gate is s5_participant], door [singleSelect: dashboard, nudge_link], decided_at [dateTime]. The s9_ready row (decision ready_to_assemble, actor producer) is the PRD Section 3.11 trigger of record; exclude rows (actor producer, subject a participant_key) record edition exclusions.

EXCEPTIONS: exception_id [primary], raw_submission [multilineText json], reason [singleSelect: unroutable_missing_ids, unknown_anthology, stage_mismatch, tenant_mismatch, legacy_reconciliation], status [singleSelect: open, resolved], resolved_by [singleLineText], resolved_participant_key [singleLineText], created_at, resolved_at [dateTime].

7.2 THE LOCAL MIRROR: SQLite, WAL mode, on the client box under the engine's state directory, owned by the node user; same tables and columns plus a meta table (schema_version, last_reconcile_at, base_cursor). Reads for the dashboard and the router come from the mirror; anthology_state.py writes THROUGH to base and mirror in one operation and reconciles on the daily tick; the base wins on conflict. A network blip never blocks a gate action; a dead box never loses a participant.

7.3 THE LEGAL TRANSITION MATRIX (enforced by anthology_state.py; illegal transitions exit nonzero and change NOTHING):

    s0_intake -> s1_avatar                     on valid universal submission
    s1_avatar -> s1_gate                       on avatar artifacts recorded
    s1_gate -> s2_tone                         on approvals row (s1_producer, approve)
    s2_tone -> s2_gate -> s3_title             tone prover pass, then producer approve
    s3_title -> s3_gate -> s4_blurb_outline    titles delivered, then selection recorded
                                               (TITLE LOCK stamps here, one-way)
    s4_blurb_outline -> s4_gate_producer -> s4_gate_participant -> s5_chapter
    s5_chapter -> s5_gate                      only after Tier 1 plus rubric pass
    s5_gate -> s7_cover                        on approve (chapter artifact freezes)
    s5_gate -> s6_rewrite                      on request_rewrite AND rewrite_count < 2
    s6_rewrite -> s5_gate                      always re-enters the gate
    s7_cover -> s8_deliver -> s9_wait_assembly -> approved
    approved -> delivered                      at S9 manuscript delivery of the anthology
    ANY -> held                                typed hold (credit_out, callback_lost,
                                               strike_out); resume ONLY to the recorded cursor
    ANY -> exception                           router-detected; resolution replays S0
    s9 (anthology scope): not_ready -> armed          when every participant is approved
                                                      or explicitly excluded (exclude row)
    armed -> ready_confirmed                          ONLY on the s9_ready approvals row
                                                      (the producer trigger, PRD 3.11), with
                                                      all guards revalidated by the writer:
                                                      own producer, >= min_chapters frozen
                                                      approved chapters, --confirm-name match
    ready_confirmed -> proposed -> adjusted* -> compiled -> signed_off,
    with signed_off requiring an s9_producer approvals row; firing s9_ready twice is an
    acknowledged no-op; reopening collection after ready_confirmed is a producer-initiated
    exception that resets assembly_state to not_ready and voids in-progress assembly

7.4 THE WRITER CONTRACT: anthology_state.py subcommands upsert-participant, advance-stage, record-artifact, record-approval (including the s9_ready trigger with --confirm-name), assembly-readiness-report (read-only: emits the blocking list that arms or refuses the trigger), hold, resume, exception-open, exception-resolve, assembly-set-order, reconcile-mirror, export-bundle; every subcommand takes explicit keys (participant_key or anthology_id), validates against 7.3, writes base plus mirror, and exits 0 only on verified success (nonzero codes: 2 illegal transition, 3 unknown key, 4 base unreachable with mirror-queued write, 5 validation). NO other code path writes to either store; the dashboard, the stage runners, the exceptions screen, and the revocation script all shell through it. This is enforcement, not description: a static route audit (dashboard criterion 13) and a repo scan for direct base writes ride Gate A.

7.5 THE FIELD PUSH PROJECTION: the contact's PRD Section 6 custom fields are a pushed projection of the ACTIVE anthology's artifact rows (disambiguated by contact.anthology_active_id), written by exact key from config/field-map.json, keyed by contact_id, read back byte-for-byte. History lives in the ledger and Drive, never in field archaeology.

---

## 8. RUNTIME MODEL ROUTING (CLIENT'S OWN PROVIDERS, NOTHING ANTHROPIC, EVER)

8.1 THE ENGINE TIER MAP (config/model-map.template.json, resolved per box at install by preflight.sh against the CLIENT's own configured providers and keys; every credential by label from the client env stores, live process env checked first):

| Tier | Work | Resolution chain (in order) | Parameters |
|---|---|---|---|
| HEAVY-WRITER | S1 avatar bodies, S2 tone, S3 titles, S4 blurb and outline, S5 chapter, S6 rewrite, S9 introduction and matter | (1) GLM 5.2 on Ollama Cloud, provider id ollama-cloud, which REQUIRES baseUrl slotting (not apiKey slotting) and maxTokens 65536; (2) OpenRouter GLM 5.2; (3) Gemini 3.5 Flash (operator-confirmed final fallback for THIS project; the Gemini key resolves under any of its three alias names); (4) chain exhausted: durable HOLD plus ONE deduped founder Telegram alert through the OpenClaw gateway, never bypassed | thinking high, temperature 0.3 |
| LIGHT | Extraction (aw-12), classification, routing-adjacent text chores | Minimax V3 on Ollama Cloud, then its OpenRouter counterpart, then Gemini 3.5 Flash | defaults |
| JUDGE | Gate B semantic checks and the Tier 2 rubric | Minimax V3 or Gemini 3.5 Flash, ALWAYS a different resolution than the tier that drafted the piece | temperature 0 |
| LONGCTX (optional) | S9 whole-manuscript compile | DeepSeek V4 Pro or Kimi 2.6 (about 1M context), ONLY when the client has configured a key; otherwise S9 chunks on HEAVY-WRITER | thinking high |
| IMAGE | S7 cover | Client's own Kie.ai, GPT-image-2, portrait 1024x1536 via the Wave-0-verified text-to-image portrait endpoint (never the 16:9 presentation recipe), via Skills 07 and 46 | per Skill 07 |

8.2 ROUTER SEMANTICS (model_router.py): one call site for every model turn; per-call pre-meter and post-meter through anthology-cost-ledger.py (per-deliverable token budgets shared across QC attempts); typed error classification (insufficient_credits, auth, rate_limit, timeout, refusal) with chain advance on retryable classes and durable hold on credits; DENY PATTERNS refuse any request whose resolved model matches Anthropic identifier shapes (claude-*, anthropic/*, and vendor-prefixed variants) at call time, mirroring Skill 54's AF-AW-ANTHROPIC ledger gate; the model actually used is recorded honestly on the Artifact row and the run ledger. guard-no-anthropic-runtime.py enforces the same law statically over every shipped file including the dashboard at merge. Prompts never name models (pipeline-design.md Section 2); tiers are the only vocabulary above the router.

8.3 SOVEREIGNTY: the chain is the CLIENT's own accounts under their own labels; operator keys never land on client boxes; the engine never substitutes a client's expressed model choice; alarms about a client's provider state NOTIFY, they never modify.

## 9. WEB-SEARCH DETECTION LADDER (AVATAR QUESTIONS 31 AND 32)

search_detect.py runs once per box, caches to client state, and re-detects on preflight: (1) enumerate the enabled OpenClaw web-search tools on the installed gateway (live-verified at W0.4 because tool-registration schemas drift between gateway versions); (2) prefer Perplexity when present; (3) else the best available enabled search tool (Ollama Cloud web search and the client's other enabled options rank by recency and quota state); (4) else NO TOOL: S1 produces the avatar from Questions 1 to 30 with an honest limitation note in the operator run report, the participant run CONTINUES, and ONE deduped Telegram flag goes to the founder. The search pass is a Layer 2 tool step whose findings inject into pin aa-02 as context; GLM 5.2 does not search natively and the engine never asks it to fabricate links; fabricated-link detection is Gate B Tier 1 check 10 (research claims must trace to the search pass output).

## 10. DELIVERY ADAPTERS

10.1 GOOGLE DRIVE AND DOCS (drive_adapter.py calls the Drive and Docs REST APIs DIRECTLY, PRD Section 3.13; Skill 14 is pattern reference only): auth is the operator's EXISTING service account exactly as clawd/google-api.js does it (service-account JWT, domain-wide impersonation of the account under the GOOGLE_IMPERSONATE_USER label, full Drive scope https://www.googleapis.com/auth/drive); per-box credential placement decided at onboarding per PRD Section 15; NOTHING new is provisioned. The delivery-tree ROOT is the operator's EXISTING anyone-can-read folder, wired as the root of record: https://drive.google.com/drive/folders/1gVdZ3_cx7Sv7VAfARL_LsGh5IcVB6iZw (config key drive_root_folder, engine-config.template.json; drive-tree-provision.py verifies reachability of this root at preflight and NEVER creates a new root). Tree below it: Producer display name, then Anthology name, then Participant name; provisioned idempotently by drive-tree-provision.py at S0; every Doc created inside the participant folder; per-document sharing anyone-with-link VIEW only (revocation-preserving); folder ids cached on the ledger rows; the export bundle (per-anthology ledger json plus the Drive folder) produced by export-bundle or the revocation script.

10.2 DETERMINISTIC PDF (pdf_render.py): WeasyPrint-class HTML-to-PDF; input is the deliverable's markdown-to-HTML transform through the house template for its type; all font sizes are tokens at or above 14 point; guard-font-floor.py parses the RENDERED file and fails on any glyph below 14 point (the prover inspects output, never the template). No LLM touches formatting at runtime.

10.3 CONVERT AND FLOW (caf_delivery.py over Skills 44 and 29, credential by label through the shared alias resolver, private integration token and API key being the same thing under any alias): upload Doc export and PDF to media storage; verify each hosted link reachable; write the PRD Section 6 field pairs by EXACT key from config/field-map.json, keyed by contact_id; read back byte-for-byte; update the three control fields. Missing fields at provisioning stop SETUP with an operator surface; runtime never silently creates fields. Tenant check on every call (payload location equals the registry binding).

10.4 COVERS (cover_render.py): Section 4 S7; the Kie.ai callback pattern per Skill 46 with bounded re-poll fallback; PNG lands in Drive; cover fields carry the media-storage link and the Drive link per the Section 6 pair.

10.5 NUDGES AND NOTICES (nudge_send.py): the three sanctioned templates only; recipients resolved from the ledger row for the given contact_id (participant gates) or the producer record (producer gates); delivery through Skill 50 email-engine or the gateway notification path; ONE automatic re-nudge at 7 days stuck, deduped; all other repeats are manual via the dashboard re-send button (rate-limited). The engine sends NOTHING else to any client, ever (silence doctrine).

## 11. COMMAND CENTER INTEGRATION CONTRACT (THE PRODUCER BOARD AND THE PARTICIPANT TOKEN PAGE)

Revision 3 ground truth (verified by the Command Center repo read; supersedes design/dashboard-design.md's standalone-app framing while its gate semantics and acceptance intents carry over): the Command Center is a PER-CLIENT, SINGLE-OWNER, WHITE-LABEL product on the client's OWN box, unlocked by the AI Workforce Interview (Skill 23 leading to Skill 32); it is NOT a BlackCEO fleet tool, NOT multi-tenant, and NO producer role exists in its code. The producer IS the box owner. NO standalone dashboard app is built.

11.1 DEPARTMENT SEEDING (mandatory, scored): the build seeds an ANTHOLOGY department via Skill 32's add-department.sh (equivalently POST /api/departments with create:true) during provisioning. Hard lesson encoded: Skill 53 book-writer cards to a books department that was never seeded, so its cards fall to the CEO catch-all; the engine never repeats that defect. Seeding is idempotent and verified by reading the department back.

11.2 THE BOARD CONTRACT (the producer experience):
- CARD INGEST: every participant is ONE task card on the Anthology board, created and advanced by mc_board.py posting to POST /api/tasks/ingest with HMAC plus Bearer auth, FAIL-SOFT: board unreachability never blocks the pipeline; the ledger remains the truth and the card reconciles on the daily tick.
- STATUS MAPPING: card status mirrors Participants.stage_cursor. Producer-facing deliverables land the card in the REVIEW column, which IS the chapter-approval queue; this rides the EXISTING board contract that routes producer output to review. ONLY the independent QC scorer at or above 8.5 promotes review to done; the engine never self-promotes a card.
- GATE ACTIONS: producer decisions on a card (Approve, Request rewrite with notes, Hold, Exclude) shell anthology_state.py record-approval with the door recorded as board; the board holds no base credential and never writes state directly.
- THE ASSEMBLY CARD: one dedicated card per anthology carries the readiness report, the READY TO ASSEMBLE trigger (gate s9_ready, all PRD 3.11 guards enforced by the writer, typed name confirmation), the order-adjustment surface, and the final manuscript sign-off (gate s9_producer). Trigger and sign-off are status transitions on this card plus approvals rows in the ledger.
- ROLLUPS: per-anthology rollup state (active participants, chapters pending approval, stuck items) is a projection of the same ledger; nothing is recomputed into a second store.

11.3 THE PARTICIPANT TOKEN PAGE (new code, Command Center repo, its own serial train): external co-author participants have NO Command Center login and no route exists for them today. The build adds ONE token-scoped PUBLIC route, registered in the middleware.ts bypass list exactly the way /api/health is bypassed, plus its page. Access is by a NEW single-purpose token/PIN minted by gate_engine.py: HMAC-signed over participant_key, gate id, and expiry, keyed by the per-client secret under the label ANTHOLOGY_GATE_TOKEN_SECRET; tokens are single-gate-scoped, expire on gate closure, and foreign, expired, or replayed tokens are refused. The page serves ONLY that participant's open gate: title and subtitle selection (S3), outline approval (S4), chapter Approve-as-is or Request-rewrite-with-notes (S5/S6). Both doors, the emailed nudge link and the board-side producer view, hit the SAME endpoint and the same writer subcommand.

11.4 HOME-SCREEN TILES (Command Center repo, code edit): the home screen is a HARDCODED tile array in command-center src/app/page.tsx; an Opus sub-agent edits that array to add the ANTHOLOGY tile (deep-linking to the Anthology department board), the PODCAST tile, and the INTERVIEW tile, following the existing tile shape. The tile is a window into the board, never a second surface.

11.5 CLIENT-CLEAN SERIALIZER: every client-visible payload (card fields, token page, nudges) passes the serializer that strips internal tool names, model names, plumbing, and secrets, and says Convert and Flow everywhere.

## 12. THE TWO QC GATES (WIRING POINTS ONLY; FULL PROTOCOL IN QC-PROTOCOL-AND-MATRIX.md)

GATE A (build/merge, threshold 8.5 on the fleet 10-category rubric) scores every feature/slice through an INDEPENDENT QC agent (heavy QC parallelism beside the execution side; below 8.5 fix and re-QC; at or above 8.5 PUSH, then the same agent ticks CHECKLIST.md, marks TODO.md, and appends SESSION-LOG.md and CHANGE-LOG.md per the incremental persistence law); its mechanical riders (anthropic guard, prompt pins, cron inventory, content_sha restamp, annotated-tag-before-merge, fleet-wide identifier grep, update.sh count, tone-core sync, Skill 53 regression) run in the Wave 5 gate battery and again on the Wave 6 train. GATE B (content) ships INSIDE the skill and runs at runtime: qc-tier1-anthology.py (twelve deterministic checks plus three judge-tier semantic checks; assembly mode for S9), then the ten-dimension rubric at 8 or higher per dimension with no averaging on the JUDGE tier, then qc-strike-gate.py counters. Wiring points: S5 and S6 run the full battery BEFORE their gate opens; S1 to S4 and S7 to S8 run their subset per the QC matrix; S9 runs assembly mode. The gates are never conflated: a 9.0 build unit says nothing about a chapter, and a perfect chapter says nothing about merge readiness.

## 13. PROVISIONING, VERIFICATION, REVOCATION

13.1 provision-anthology-client.sh (idempotent; config writes as the node user; every check reports SET or NOT SET, never a value): (1) caf_credential_gate.py resolves every Section 14 PRD credential by label across all three client env stores, live process env first, with pairing proof and the anti-commingling fingerprint; (2) create or verify the PRD Section 6 custom fields by exact key (stop on missing, operator surface); (3) AUTO-PROVISION the standard Anthology pipeline and stage set in the client's own Convert and Flow account through the CLIENT'S OWN private integration token (PRD Section 3.12, locked default; binding to an existing pipeline only as an explicit override), and bind it into the anthology registry; (4) register the universal and per-stage forms with their hidden fields and re-stamp behavior; (5) provision the Drive producer root; (6) bootstrap the ledger base and mirror schemas; (7) generate the webhook route and its secret (stored under label ANTHOLOGY_INTAKE_HOOK_SECRET); (8) register the ONE daily tick in the cron inventory; (9) run verify-webhook-t1-t9.sh; (10) fire one smoke test (balance endpoints only, at or under one cent).

13.2 T1 TO T9, the intake verification battery (normative definition for this build; executed and OBSERVED on the canary at W5.3, never assumed): T1 route registered on the gateway; T2 requests without the route secret are refused; T3 malformed payload lands in Exceptions with reason, never a crash; T4 valid synthetic submission acknowledges in under 2 seconds and creates the participant; T5 duplicate delivery of the same submission is a no-op acknowledge; T6 wrong-tenant payload lands in Exceptions (tenant_mismatch); T7 stage-mismatched form lands in Exceptions (stage_mismatch); T8 the REAL public URL through the named Cloudflare Tunnel accepts a submission end to end; T9 gateway restart preserves the route and the pending state (ledger intact, no lost event).

13.3 revoke-anthology-client.sh: invalidate every outstanding participant gate token, archive the Anthology board cards, revoke Drive shares and regenerate view links, disable the webhook route, produce the export bundle, archive ledger rows, verify by probing a revoked token link and the disabled route, and leave ZERO recurring jobs (guard-cron-inventory.py proves it).

## 14. REUSE AND DEPRECATION STANCE (SKILLS 53 AND 54; THE LEGACY STACK)

Verbatim posture from design/deprecation-plan.md, restated as build law with today's verified versions:

1. Skill 53 book-writer (verified 1.0.3): NOT deprecated, NOT touched. It is the twelve-chapter full-book and offer-book product feeding Skill 51; the build brief's "deprecate the older BookWriter skill" directive is STALE and executing it is a scored build failure. A pull-request check proves Skill 53 files untouched; its regression suite and the Skill 51 handoff stay green; it gains only a sibling-boundary cross-reference in docs.
2. Skill 54 anthology-writer (verified 1.0.0 live at authoring time; Wave 0 re-confirms and any planning snapshot yields to the live number): PROMOTED to the authoring core and extended per Section 3.2 of this SPEC, nothing more. Building a duplicate anthology skill is a build failure; a repo scan proves no second anthology skill directory exists beyond the orchestrator plus the extended 54.
3. shared-utils/tone-writing-core: byte-identical reuse; verify_tone_core_sync.py green across 53, 54, and the orchestrator; forking it is a build failure.
4. The ONLY retirement is the legacy n8n anthology stack (the eight Section 1.1 workflows plus inactive clones and the 37-node ancestor), in the four phases of design/deprecation-plan.md Section 3 (HARVEST, FREEZE, PARALLEL CANARY, RETIRE), gated by the retirement criteria of design/n8n-integration-design.md Section 4 INCLUDING the operator's explicit OK; deactivate never delete; ninety-day retention; scrubbed archive; rollback by reactivating the deactivated workflows at any point before archive. The n8n instance itself survives for its other automations. Legacy participant migration and bridge tooling are OUT OF CORE SCOPE (PRD Sections 8 and 18); the build never edits a legacy workflow.
5. The legacy prompt bases (Section 1.2) are demoted to the operator's private editing workspace; the eight truncated full-book records are out of anthology scope by ratified decision; zero runtime references, statically proven.

## 15. FAILURE HANDLING AND LOOP ENGINEERING (TYPED, COMPLETE)

| Failure class | Handler | Evidence it works |
|---|---|---|
| Insufficient credits on any provider | hold_queue.py: durable HOLD with full state; ONE deduped alert; daily tick retries the chain; resume from the exact cursor | W5.5 forced drill (this class killed the legacy system twice, on record) |
| Model chain exhausted | Same hold-plus-alert | W5.5 |
| Gate waiting | NO timeout exists; ledger holds indefinitely; 7-day stuck highlighting plus one deduped auto re-nudge | Aged fixture, dashboard criterion 4 |
| Kie.ai callback lost | Bounded re-poll, then hold plus alert | W5.5 |
| Content strike-out (3 QC attempts) | HOLD plus alert carrying the failing checks and best draft; standards never relaxed | W5.5 |
| Rewrite budget exhausted | Gate offers Approve as-is or producer escalation; third rewrite is an illegal transition | W5.5 |
| Unroutable or mismatched submission | Exceptions queue; dashboard reconciliation; replay through S0 | T3, T6, T7 |
| Duplicate webhook delivery | Fingerprint no-op acknowledge | T5 |
| Crash anywhere, kill mid-stage | Ledger is the truth; replay is a no-op or clean resume; no duplicate artifact | Kill-and-resume drill (data model acceptance 2) |
| Mirror divergence | Daily reconcile restores base truth | Divergence drill (acceptance 5) |
| Six-month participant pause | A normal ledger state, cost zero | Design invariant, Section 2.2 |

The three loops of PRD Section 10 (participant loop, build loop, fleet loop) bind unchanged; every self-correction above is a named executable with an exit code, not prose.

## 16. BUILD-WAVE TRACEABILITY

Every SPEC section lands through the existing WAVE-PLAN.md tasks; no new waves are introduced: Section 1 evidence re-verification is W0.1 and W0.4 to W0.8; Section 3.1 is W1.1 plus the module tasks W1.5 to W1.24; Section 3.2 is W1.2 to W1.4 (pins from W0.2); Section 3.4 is scored at the Gate A battery (inventory equals shipped set); Section 5's invariant is scored across W5.4, W5.5, and the Gate A battery; Section 6 is W0.2 plus W1.3 plus W1.12; Section 7 (including the s9_ready trigger transitions) is W1.7 plus W1.19 plus W1.20; Section 8 is W1.9; Section 9 is W1.10; Section 10 is W1.11 to W1.14 plus W1.15; Section 11 is Wave 3 in the Command Center repo (W3.1 department seeding and board contract, W3.2 home tiles page.tsx edit, W3.3 participant token route) against W1.7's schema; Section 12 is W1.16, W1.17, and the QC matrix; Section 13 is W2.3, W2.6, W2.7, W1.6, W1.8; Section 14 is W2.8 and the merge-train checks; Section 15 is W5.5. DONE remains CHECKLIST.md Part C, all 26 items, independently verified on the canary; if the repo is not updated, it is not done.

## 17. OUT OF SCOPE (SO NO AGENT BUILDS IT BY ACCIDENT)

The twelve-chapter full-book prompts and the 4x3x3 tables (Skill 53 territory); any runtime prompt fetch from any Airtable base; ANY n8n dependency in the engine and ANY legacy participant migration or bridge tooling (out of core scope entirely; the single optional line is PRD Section 18); automatic S9 firing without the producer trigger; mail-embedded wait forms and approve-by-reply; per-anthology custom-field families on the contact (rejected, Section 7.5); ANY standalone producer dashboard app, any BlackCEO-hosted producer surface, and any producer role added to Command Center code (Section 11 ground truth); engine self-promotion of a board card from review to done (the QC scorer alone promotes); committing any of the nine Downloads JSON exports or any fragment of them; any new Google service account, share, or Drive root (Section 10.1 reuses the existing ones); any heartbeat cron beyond the one daily tick; any Anthropic model anywhere at runtime; any client-facing message outside the three sanctioned templates; fleet rollout (HELD at repo-only until the operator OK).

---

## APPENDIX A: LEGACY MODEL INVENTORY AND ITS REPLACEMENT (every legacy id verified in the live node graphs; listed solely as evidence of what is REPLACED; none may appear in any runtime file)

| Legacy model id (node evidence) | Where it ran | Replaced by tier |
|---|---|---|
| anthropic/claude-sonnet-4.5 | Avatar Questions 1 to 30, Rewrite Avatar | HEAVY-WRITER (GLM 5.2 chain) |
| anthropic/claude-sonnet-4.6 | Tone Style 1, Blended Tone | HEAVY-WRITER |
| anthropic/claude-sonnet-4 | Tone Styles 2 to 4, Suggested Titles, Book Blurb | HEAVY-WRITER |
| anthropic/claude-opus-4 | Create Outline, Write Chapter, Chapter Re-Writer | HEAVY-WRITER |
| google/gemini-2.5-pro, google/gemini-3.1-pro-preview | The five HTML formatters | RETIRED (deterministic rendering) |
| openai/gpt-4.1 | Primary Goal extraction, cover Prompt Writer | LIGHT / MID work on the GLM chain and Minimax V3 |
| gpt-4o-search-preview | Avatar Questions 31 to 32 | Detection-ladder search tool step |
| gpt-image-1 (legacy image API, hardcoded key) | Cover render | Client Kie.ai GPT-image-2 via Skills 07 and 46 |

## APPENDIX B: CANONICAL PARTICIPANT DATA DICTIONARY (the single vocabulary every prompt slot, ledger column, form field, and dashboard label resolves to)

first_name, last_name, email, phone, contact_id, anthology_id, stage, producer, producer_email, ideal_avatar (Q1), niche (Q2), primary_goal (Q3), niche_primary_goal, questions_1_30, questions_31_32, tone_inputs (describe_tone plus well_known_figure, infl_2, infl_3, infl_4), blended_tone, title, subtitle, chapter_about, personal_stories, blurb, outline, chapter, chapter_updates, plus the per-deliverable doc and PDF links of PRD Section 6 and the three control fields. The legacy book_id is subsumed by anthology_id; the legacy opportunity_id is dropped (contact_id keying); the legacy api_key payload field is abolished.

CRAFT GROUNDING FOR S9 (external, non-binding, cited for the order-curation heuristics): anthology-editing practice consistently recommends opening and closing with the strongest pieces, alternating long and short works so long pieces never cluster, managing tonal shifts deliberately, and grouping or pairing by subtheme; see the John Joseph Adams Codex Q&A on anthology story order (johnjosephadams.com, 2013) and practicing-editor discussion summarized at quora.com on anthology ordering. These confirm, and do not replace, the PRD Section 5 S9 specification.

END OF SPEC. Word of control: this document plans; the /goal execution builds; the rubric decides; the operator's word overrides everything.


