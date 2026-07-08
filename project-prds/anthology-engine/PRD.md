# ANTHOLOGY ENGINE, PRODUCT REQUIREMENTS DOCUMENT
## The True, Hyper-Extensive PRD for the Anthology Engine OpenClaw Skill and Delivery System
### Version 3.0, authored by Fable, 2026-07-06 (revision 3: the producer experience relocated INSIDE the client's own Command Center as a department/board, per the verified Command Center repo read; prompt source of record moved to the nine Downloads JSON exports; 50-agents-per-wave single-wave execution model; incremental-persistence law; v19.0.0 target). Status: READY FOR /goal EXECUTION (planning only; no build triggered by this document).

Document control: this is the TRUE PRD. During the build, the execution agents copy this PRD set (PRD, SPEC, CHECKLIST, TODO, WAVE-PLAN, SESSION-LOG, CHANGE-LOG, QC-PROTOCOL-AND-MATRIX) into the onboarding repo master files at project-prds/anthology-engine/ and keep both copies in sync, with one exception: design/n8n-integration-design.md stays OPERATOR-SIDE ONLY. Every document in this set is identifier-scrubbed: legacy workflow, base, table, and pipeline identifiers appear as LABELS only (LEGACY-MAIN, LEGACY-AVATAR, and so on). Zero client personally identifiable information (participant or producer names, emails, account or pipeline identifiers) may appear in any document in this set; credentials and identifiers are referenced by LABEL and LOCATION only. This folder at <OPERATOR_HOME>/clawd/projects/Anthology-Engine/ remains the operator-side working copy. The design/ subfolder holds the five design specs, including design/dashboard-design.md at revision 3 (v3.0), the aligned Layer 4 design for the Command Center department/board and the participant token page; where any design doc could ever disagree with this revision 3, THIS PRD governs.

Technical companion: SPEC.md (same folder, revision 3) is the buildable, node-level technical specification; it deepens this PRD and is subordinate to it.

Doctrine binding on this document, on the build, and on everything the engine ever produces: MOVE IN SILENCE (operator-verbose, never client-facing); NOTHING Anthropic ships in any runtime file; every credential is referenced by LABEL and LOCATION only, never by value; the client-facing platform name is Convert and Flow, always, in every surface; config writes run as the node user, never root; ONLY SUB-AGENTS BUILD (the orchestrator delegates everything); zero em dash characters and zero triple-backtick fences in any produced deliverable.

---

## 1. SOURCE DOCUMENTS AND THE PROMPT SOURCE OF RECORD

Primary companions, all in <OPERATOR_HOME>/Downloads/anthology project/:

1. ANTHOLOGY_OPENCLAW_SKILL_SPEC.md: the prior session's full skill specification. Its Sections 0 to 11 survive as PRD source with the corrections in Section 9 of this document. Its Section 12 claims every prompt is embedded verbatim but embeds only 14 blocks; that gap is closed in this build (Section 9, Gap 1).
2. ANTHOLOGY_CLAUDE_CODE_BUILD_BRIEF.md: the build orchestration brief. Its "deprecate the older BookWriter skill" directive is STALE and is corrected by the deprecation plan (Section 8 and design/deprecation-plan.md).
3. Two prompt companions: ANTHOLOGY_PROMPTS_AVATAR_TONE_VERBATIM.md is complete; ANTHOLOGY_PROMPTS_INLINE_VERBATIM.md is complete for Write Chapter and the chapter formatter, and carries POINTERS for the four largest prompts.
4. The operator's prior conversation transcript: the primary intent evidence. Every ratified decision in Section 3 traces to it.
5. THE NINE n8n WORKFLOW JSON EXPORTS plus the truncated prompt-library CSV: the PROMPT SOURCE OF RECORD for this build. The four largest prompts (single-chapter Create Outline; the Chapter Re-Writer editorial persona, Thornfield; the Book-to-HTML formatter; the Cover Image prompt generator) exist ONLY inside these exports: Outline Agent.json, Chapter Re-Writer Agent.json, and Single Chapter Cover Image Gen.json. The BUILD INGESTS THEM DIRECTLY FROM THE JSONs and bakes them in, zero truncation, sha256-pinned; no live n8n dependency exists on the prompt path. Two repair laws ride the ingestion: (a) the live Chapter/Book-to-HTML formatter text carries 10 literal [UNCHANGED] placeholders; the full text is RESTORED from the CSV record named HTML Book in Full Book Prompts-Grid view.csv before pinning; (b) the Write Chapter word-count contradiction is NORMALIZED to 2,000 to 3,500 words everywhere; (c) legacy Make.com variable syntax in the prompt bodies is MAPPED to the canonical field names (SPEC Section 6.2), the prompt prose itself untouched.

SECURITY LAW ON THE EXPORTS (binding, scored): the nine JSON exports carry LIVE credentials: an OpenAI key in a literal Authorization header on the cover-generation node, and an OpenRouter key riding inside the webhook payload at customData.Openrouter_Api_Key. These files must NEVER be committed to the onboarding or fleet repo, in whole, in part, or in fixture form; the build reads them in place, extracts prompt text only, and the payload-carried routing key becomes a proper ENV credential referenced by label. A repo scan for any export content or key shape rides the merge gate.

Why this build exists: the operator is retiring n8n for the Anthology Book Project and converting it into an OpenClaw skill plus a delivery system. The prior n8n system is effectively down (model billing failures, zombie waits stuck since late 2025, a hardcoded test inbox receiving real participants' forms). The product must become universal, durable, and multi-anthology, not welded to one client's subaccount.

---

## 2. PRODUCT DEFINITION AND DESIGN INTENT

### 2.0 WHAT AN ANTHOLOGY IS (binding on scope)

An anthology is a MULTI-CONTRIBUTOR, curated collection: many authors each contribute one piece around a shared theme, and an EDITOR (here, the producer) selects, orders, and frames the contributions editorially: an editor's introduction in the editor's own voice; a curated chapter ORDER built on established anthology craft; front matter; contributor bios; back matter. HOW THIS DIFFERS FROM SKILL 53: the book-writer product is a SINGLE author writing a full twelve-chapter book; the anthology is MANY authors writing ONE chapter each. That is why Skill 53 stays untouched, why Skill 54 (the per-chapter writer) is the authoring core, and why the genuinely new surface is the curation-and-assembly layer (S9) plus the multi-participant orchestration around it. Anything single-author or twelve-chapter shaped is Skill 53 territory and out of this product.

### 2.1 THE PRODUCT AND ITS PEOPLE

The Anthology Engine turns one participant's universal Convert and Flow form submission into ONE gated, quality-controlled, 2,000 to 3,500 word anthology chapter (never twelve), with every deliverable shipped as BOTH a Google Doc and a designed PDF (no font below 14 point), links pushed to standardized Convert and Flow contact custom fields keyed by contact_id, never email.

THE PRODUCER IS THE OPENCLAW BOX OWNER: the client who completed the AI Workforce Interview, passed into every run via the Convert and Flow webhook payload. There is NO separate producer identity system and NO producer role in any Command Center code; the producer IS the Command Center owner. A producer runs multiple anthologies; each anthology has many participants; the same person in two anthologies is two participant records sharing one contact_id, separated by anthology_id. PARTICIPANTS are EXTERNAL CO-AUTHORS with no box, no Command Center login, and no OpenClaw identity; they are served by forms, nudges, and the new participant token page (Section 3.16).

DESIGN INTENT (layer, do not rebuild): the fleet already owns the authoring core. Skill 54 anthology-writer shipped with exactly the per-chapter pipeline this product needs: the P0 to P7 phase machine, sha256-pinned baked prompts, fail-closed measured provers, the shared tone core, a client-tier model map with no Anthropic identifiers, rewrite budget 2, a signed process certificate, and a Command Center card. The genuinely new work is: intake routing, durable multi-participant state, Convert and Flow and Drive and PDF delivery, the Command Center department/board producer experience, the participant token page, and anthology assembly. The engine is FOUR LAYERS (Section 4). Reuse before rebuild is a scored requirement of the build gate.

The stage that makes this an anthology ENGINE: S9 ANTHOLOGY ASSEMBLY, fired ONLY by the producer's explicit "I'm ready to assemble" trigger (Section 3.11) and closed by the producer's final sign-off. Two distinct producer decisions bracket S9.

---

## 3. NON-NEGOTIABLE GROUNDING DECISIONS

Settled from the operator's ratified words, fleet doctrine, and the verified Command Center repo read. Execution agents do not relitigate them.

1. ONE CHAPTER PER PARTICIPANT, never twelve. The truncated twelve-chapter full-book prompts belong to Skill 53's product and are permanently OUT of anthology scope.
2. ARCHITECTURE: the Anthology Engine is a NEW ORCHESTRATOR SKILL (working id anthology-engine; number resolved at Wave 0 as the next free slot) that CALLS Skill 54 as its authoring core and owns ALL external input and output. Skill 54 gets three bounded extensions: the Skill 52 avatar handoff, the newly pinned prompts, and intake fields ideal_avatar, niche, primary_goal. A duplicate anthology skill is a build failure. Deprecating Skill 53 is a build failure (Section 8).
3. RUNTIME MODELS, exact chain, client's own keys only, never the operator's: primary GLM 5.2 on Ollama Cloud (provider id ollama-cloud, needs baseUrl slotting, not apiKey), thinking high, temperature 0.3; fallback 1 OpenRouter GLM 5.2; fallback 2 Gemini 3.5 Flash; on chain exhaustion the job HOLDS durably and the founder is Telegram-alerted through the OpenClaw gateway, never bypassed. Minimax V3 handles light and tool-shaped tasks. DeepSeek V4 Pro and Kimi 2.6 are OPTIONAL 1M-context tiers, primarily for S9. NOTHING Anthropic ships in any runtime file; guard-no-anthropic-runtime.py enforces at merge and runtime deny patterns refuse substitutions.
4. PROMPTS ARE BAKED INTO THE SKILL, sha256-pinned, complete, zero truncation, INGESTED FROM THE JSON EXPORTS per Section 1.5: the four largest prompts come out of Outline Agent.json, Chapter Re-Writer Agent.json, and Single Chapter Cover Image Gen.json; the formatter's 10 [UNCHANGED] placeholders are restored from the CSV HTML Book record; the word-count contradiction normalizes to 2,000 to 3,500; Make.com variable syntax maps to canonical field names. The engine NEVER calls any prompt base at runtime. guard-prompt-pins.py proves every pin and that no prompt ends at a truncation boundary.
5. KEYING: everything keys off contact_id, never email. Every form carries hidden contact_id, anthology_id, and stage fields. Unroutable submissions land in the exceptions queue, never silently dropped.
6. APPROVALS (revised to the Command Center ground truth): the system of record for producer approvals is the client's own COMMAND CENTER BOARD (Section 3.15): the Anthology department board's review column IS the chapter-approval queue; the existing board contract already routes producer-facing output to review, and ONLY the independent QC scorer at or above 8.5 promotes review to done; a short email nudge deep-links to the board card (producer) or the participant token page (participant). The chapter gate offers exactly two actions: Approve as-is, or Request rewrite with notes feeding chapter_updates. Rewrite budget is 2.
7. DELIVERY: every deliverable ships as BOTH a Google Doc and a designed PDF with no font below 14 point, produced by deterministic Python HTML-to-PDF rendering with a provable font-floor gate; the five legacy LLM HTML-formatter calls are retired. Documents live in the operator's EXISTING BlackCEO-controlled Google Drive tree under the EXISTING shared root the operator already set anyone-can-read: https://drive.google.com/drive/folders/1gVdZ3_cx7Sv7VAfARL_LsGh5IcVB6iZw, organized Root, then Producer, then Anthology, then Participant; per-document sharing anyone-with-link VIEW only. The engine calls the Google Drive and Docs APIs DIRECTLY using the operator's EXISTING service account (clawd/google-api.js: service-account JWT with domain-wide impersonation via the GOOGLE_IMPERSONATE_USER label, full Drive scope); NOTHING new is provisioned in Google. Files also upload to Convert and Flow media storage and the hosted links push to the standardized custom fields (Section 6).
8. COVERS: the client's own Kie.ai, model GPT-image-2, PORTRAIT 1024x1536, via Skills 07 and 46. The build VERIFIES the Kie text-to-image portrait endpoint before shipping and NEVER reuses the 16:9 presentation image recipe. Web search for Avatar Questions 31 and 32 auto-detects the client's enabled OpenClaw search tool, preferring Perplexity, degrading gracefully with a Telegram flag when absent.
9. CADENCE REALITY: participants take weeks between stages. Every stage is an idempotent, resumable job against a durable ledger; a crash, a credit outage, or a six-month pause costs nothing. One giant blocking execution is forbidden. The Convert and Flow pipeline-stage update fires at EACH gate (the legacy behavior the operator wants kept), driven from the registry stage map, never hardcoded.
10. FLEET DOCTRINE: single merge-writer, strictly serial merge train, annotated tag (git tag -a) BEFORE merge; canary on the operator box FIRST, no client box touched; fleet rollout HELD at repo-only until the operator OK; repo is fleet-wide, zero client names or identifiers, grep every pull request; never print secret values; never commingle clients; config writes as the node user; sub-agents do ALL build work.
11. THE PRODUCER "I'M READY TO ASSEMBLE" TRIGGER (locked): S9 is producer-gated on BOTH ends. The producer fires the trigger explicitly when chapter collection is done, from either door: the Assembly card on the Anthology board, or the readiness nudge deep link; both doors hit the SAME endpoint and shell anthology_state.py record-approval with gate s9_ready. GUARDS, enforced by the writer's legal-transition matrix, never by UI alone: (a) only the anthology's own producer (the box owner's Command Center session or the producer-scoped token); (b) every participant approved or EXPLICITLY excluded (decision exclude); (c) minimum 2 frozen approved chapters (floor 2, configurable up); (d) typed anthology-name confirmation; (e) one-way. Firing moves the anthology to ready_to_assemble, runs S9, then the SECOND decision, final-manuscript sign-off (gate s9_producer), closes it.
12. AUTO-PROVISIONED STANDARD PIPELINE (locked): onboarding auto-provisions a standard Anthology pipeline in EACH client's own Convert and Flow account, created through the CLIENT'S OWN private integration token, by provision-anthology-client.sh; the registry binds anthology to pipeline at creation; pre-existing-pipeline binding is an override, never the default.
13. GOOGLE DELIVERY REUSE (locked): decision 7's existing service account and existing anyone-can-read root are the delivery plane; no new Google plumbing.
14. VERSION (locked): the onboarding repo ships this build as v19.0.0 with the ANNOTATED tag v19.0.0 created before the merge. NOT v18. Wave 0 verifies live main is below v19.0.0.
15. THE PRODUCER EXPERIENCE LIVES INSIDE THE CLIENT'S OWN COMMAND CENTER (locked; supersedes every standalone-dashboard line in older revisions and in design/dashboard-design.md). Ground truth from the Command Center repo read: the COMMAND CENTER is a PER-CLIENT, SINGLE-OWNER, WHITE-LABEL product running on the client's OWN box, unlocked by the AI Workforce Interview (Skill 23 leading to Skill 32); it is NOT a BlackCEO fleet tool, NOT multi-tenant, and there is NO producer role anywhere in its code. Therefore: NO standalone Anthology Mission Control app is built, and no BlackCEO-hosted producer surface exists. Instead the producer experience is a DEPARTMENT/BOARD inside the client's own Command Center: the build SEEDS an Anthology department via Skill 32's add-department.sh (equivalently POST /api/departments with create:true); the participant kanban is the department board's task cards (one card per participant, status mirroring stage_cursor); the chapter-approval queue IS the board's review column, using the EXISTING board contract that routes producer-facing output to review and lets ONLY the independent QC scorer at or above 8.5 promote review to done; the ready-to-assemble trigger and the assembly sign-off are further status transitions plus a dedicated Assembly card. Cards ingest via mc_board.py posting to POST /api/tasks/ingest (HMAC plus Bearer, fail-soft: board unreachability never blocks the pipeline). HARD LESSON ENCODED: Skill 53 book-writer currently cards to a books department that was NEVER SEEDED, so its cards fall to the CEO catch-all; the Anthology Engine MUST seed its own department, first, as a scored build item.
16. HOME-SCREEN TILES (locked): the Command Center home screen is a HARDCODED tile array in command-center src/app/page.tsx; adding the Anthology tile, the Podcast tile, and the Interview tile is a CODE EDIT to that array, executed by an Opus sub-agent on the Command Center repo's own serial train. The Anthology tile deep-links to the Anthology department board.
17. EXTERNAL CO-AUTHOR PARTICIPANT ACCESS (locked): participants have no Command Center login, and no public route exists for them today. The build adds a NEW TOKEN-SCOPED PUBLIC ROUTE to the Command Center: registered in the middleware.ts bypass list (the same mechanism as /api/health), protected by a NEW single-purpose token/PIN scheme minted per participant per gate by gate_engine.py; the page serves ONLY that participant's open gate (title selection, outline approval, chapter Approve-or-Rewrite with notes) and nothing else; foreign, expired, or replayed tokens are refused.

---

## 4. FULL ARCHITECTURE: FOUR LAYERS

    Convert and Flow universal form (visible: name, email, phone, Q1 ideal avatar, Q2 niche,
    Q3 primary goal; hidden: contact_id, anthology_id, stage)
      -> POST inbound webhook (Cloudflare Tunnel -> OpenClaw gateway route, per-client secret)
        -> deterministic intake router (no model call): parse, validate, tenant check,
           route by hidden fields; unroutable -> exceptions queue; fast acknowledge
          -> LAYER 2 ORCHESTRATION: durable participant ledger keyed contact_id + anthology_id
             (design/data-model-design.md); advance exactly ONE stage; persist; stop
            -> LAYER 1 AUTHORING CORE: Skill 54 anthology-writer phases (extended with the
               Skill 52 avatar handoff and the newly pinned prompts), model chain per
               Section 3.3, measured provers, rewrite budget 2
              -> LAYER 3 DELIVERY ADAPTERS: Google Docs via DIRECT Drive API calls with the
                 operator's existing service account into the existing shared root (3.7);
                 deterministic HTML-to-PDF with the 14-point floor; Convert and Flow media
                 upload and custom-field writes keyed by contact_id plus the per-gate
                 pipeline-stage update; Kie.ai portrait covers (Skills 07/46); email nudges;
                 Telegram alerts through the gateway only
                -> LAYER 4 PRODUCER AND PARTICIPANT SURFACES, ALL INSIDE OR THROUGH THE
                   CLIENT'S OWN COMMAND CENTER: the seeded Anthology department board
                   (cards via mc_board.py -> POST /api/tasks/ingest, HMAC + Bearer,
                   fail-soft; review column = approval queue; QC scorer >= 8.5 promotes
                   review -> done; Assembly card for the S9 trigger and sign-off);
                   the home-screen tiles (page.tsx code edit); the NEW participant
                   token page (middleware bypass route, token/PIN scoped)

Component inventory: pipeline and stage machine (design/pipeline-design.md); data model (design/data-model-design.md); legacy harvest and retirement (design/n8n-integration-design.md, OPERATOR-SIDE ONLY); deprecation (design/deprecation-plan.md); the Layer 4 Command Center integration (this PRD Sections 3.15 to 3.17 and SPEC Section 11, aligned with design/dashboard-design.md v3.0's Command Center department/board and participant token page design, reusing its gate semantics and acceptance intents). The complete enumerated script inventory, every new script with purpose and exit codes, is normative in SPEC.md Section 3.4; a script missing from that table does not ship, and a shipped script not in that table fails the build gate.

---

## 5. THE CANONICAL PIPELINE: STAGES S0 TO S9

Every stage is one idempotent job: an event arrives, the router advances exactly one stage, persists, and stops. No stage ever blocks waiting for a human. At EVERY gate the registry-bound Convert and Flow pipeline-stage update fires (decision 3.9).

S0 INTAKE AND ROUTING. The universal form hits the inbound webhook. Create or advance the participant record (contact_id plus anthology_id); provision the Drive folder path; card the participant onto the Anthology board; unroutable submissions go to the exceptions queue with the raw payload preserved. Keys on contact_id directly, never an opportunity list-then-filter.

S1 AVATAR. Avatar Questions 1 to 30, then 31 and 32 with auto-detected web search (prefer Perplexity; degrade plus flag), then Rewrite Avatar Niche and Primary Goal, then Primary Goal extraction; deliver Avatar Doc plus PDF. Gate: producer approval on the board card (review column). Reuses Skill 52 avatar-alchemist via the formal handoff.

S2 TONE. Tone form (speaking style plus four influences), Write Tone Style 1 to 4, Write Blended Tone; 3,000 MEASURED words per Skill 54's prover; Tone Doc plus PDF. Gate: producer, review column. Tone core reused byte-identically; forking it is a build failure.

S3 TITLE. Title form (chapter_about plus personal_stories), Suggested Titles, Titles Doc plus PDF; the participant picks title and subtitle ON THE PARTICIPANT TOKEN PAGE; TITLE LOCK: byte-exact carry per the existing prover, one-way.

S4 BLURB PLUS OUTLINE. Book Blurb plus single-chapter Create Outline (strategically placing every personal story), Docs plus PDFs. Gates: producer (board), then participant outline approval (token page). NO manual outline re-upload exists anywhere.

S5 CHAPTER. Write Chapter: ONE complete chapter, 2,000 to 3,500 MEASURED stripped words (the normalized band; self-report ignored), title locked, every story placed; Chapter Doc plus PDF. The card lands in review. Gate: participant chooses Approve as-is OR Request rewrite with notes, on the token page; producer visibility rides the review column.

S6 CHAPTER REWRITE (optional, budget 2). Notes become chapter_updates; the Thornfield editorial persona (newly pinned from Chapter Re-Writer Agent.json) rewrites inside the band; the result RE-ENTERS the S5 gate.

S7 COVER IMAGE. Cover prompt generator (pinned from Single Chapter Cover Image Gen.json), then Kie.ai GPT-image-2 PORTRAIT 1024x1536 via Skills 07 and 46 with the callback pattern, against the VERIFIED text-to-image portrait endpoint (never the 16:9 presentation recipe); PNG to Drive; links captured.

S8 PACKAGE AND DELIVER. Deterministic HTML-to-PDF (14-point floor, guard-font-floor.py proven) for every deliverable; upload to Convert and Flow media storage; push Doc-link and PDF-link pairs into the Section 6 fields keyed by contact_id; per-gate pipeline-stage update; completion notices via sanctioned templates only; signed process certificate; the board card moves per the board contract (review, then done only via the QC scorer).

S9 ANTHOLOGY ASSEMBLY. Fired ONLY by the producer trigger (3.11), from the Assembly card or the nudge deep link, both doors one endpoint, all guards writer-enforced. Then: curate chapter ORDER (strong opener and closer, long-short alternation, tone pacing, subtheme grouping); editor's introduction in the producer's voice from producer-supplied inputs only; front matter; contributor bios; back matter; compile from FROZEN approved chapters (sha256 byte-identical); full manuscript Doc plus PDF; assembly-scope content QC; producer final sign-off (gate s9_producer) closes the anthology.

Cross-cutting at every stage: anthology_state.py records every transition (the board card and any rollup read it, never recompute); anthology-cost-ledger.py meters every billable call; insufficient-credits HOLDS durably with ONE deduped founder alert; duplicate webhook deliveries acknowledge without a second run.

---

## 6. THE STANDARDIZED CONVERT AND FLOW CUSTOM FIELD LIST

Exact contact-level field keys, one Doc-link and PDF-link pair per deliverable, plus control fields. Provisioning creates or verifies these per client; missing fields stop SETUP with an operator surface, never a silent create at runtime.

| Deliverable | Doc link field | PDF link field |
|---|---|---|
| Avatar | contact.anthology_avatar_doc_url | contact.anthology_avatar_pdf_url |
| Tone | contact.anthology_tone_doc_url | contact.anthology_tone_pdf_url |
| Titles | contact.anthology_titles_doc_url | contact.anthology_titles_pdf_url |
| Blurb | contact.anthology_blurb_doc_url | contact.anthology_blurb_pdf_url |
| Outline | contact.anthology_outline_doc_url | contact.anthology_outline_pdf_url |
| Chapter | contact.anthology_chapter_doc_url | contact.anthology_chapter_pdf_url |
| Cover | contact.anthology_cover_image_url | contact.anthology_cover_drive_url |
| Manuscript | contact.anthology_manuscript_doc_url | contact.anthology_manuscript_pdf_url |

Control fields: contact.anthology_active_id, contact.anthology_stage, contact.anthology_rewrite_count. Fields carry the ACTIVE anthology's links; history lives in the ledger and Drive. Every write is keyed by contact_id, read back, and verified.

---

## 7. THE REUSE MAP (SCORED AT THE BUILD GATE)

1. Skill 54 anthology-writer: REUSE AS-IS the phase machine, provers, entry script, hash gate, baked prompts, model-map template, mc_board.py. EXTEND with the avatar handoff, the newly pinned prompts, and the intake fields.
2. shared-utils/tone-writing-core: REUSE UNTOUCHED; never fork.
3. Skill 52 avatar-alchemist: REUSE for S1 via formal handoff.
4. Skill 53 book-writer: DO NOT DEPRECATE (Section 8); untouched.
5. Skills 44, 36, 29: the Convert and Flow data plane.
6. Google delivery plane: the operator's existing service account and existing shared root (3.7); direct Drive and Docs API calls; Skill 14 as pattern reference only.
7. Skills 07 and 46 plus the verified Kie.ai pipeline: S7 covers (portrait endpoint verified fresh, 3.8).
8. Skill 32 command-center-setup plus mc_board.py: the department seeding path (add-department.sh / POST /api/departments) and the card ingest path (POST /api/tasks/ingest, HMAC plus Bearer, fail-soft); the board reads the same ledger, never a second state store.
9. Skill 50 email-engine or gateway notifications: nudges and completion notices; Telegram through the gateway only.
10. Legacy n8n JSON exports: HARVEST ONLY the prompts, form field labels, stage and gate semantics; never committed (Section 1 security law); discard every sendAndWait, duplicated-branch, and folder-node plumbing.

---

## 8. DEPRECATION STANCE (FULL TEXT IN design/deprecation-plan.md)

1. Skill 53 book-writer is NOT deprecated; different product; sibling of Skill 54; a pull-request check proves its files untouched.
2. Skill 54 is NOT deprecated; it is PROMOTED to the authoring core and extended, nothing more.
3. What retires: the legacy n8n anthology stack, in phases HARVEST (prompt ingestion from the JSON exports; secrets rotated), FREEZE, PARALLEL CANARY, RETIRE (deactivate, never delete, ninety-day retention). Legacy stays alive until the retirement criteria pass AND the operator OKs. Legacy participant migration is OUT OF CORE SCOPE (Section 18).
4. Retirement criteria: one synthetic participant S0 through S9 on the canary from the merged repo; both exposed keys rotated; zero runtime references to any legacy prompt base; the board reflecting truth against the ledger; the operator's explicit OK.

---

## 9. GAP REGISTER: EVERY KNOWN DEFECT AND ITS CLOSURE

| # | Defect or gap (verified) | Closed by |
|---|---|---|
| 1 | Four largest prompts exist only inside the JSON exports, violating the zero-truncation law if not captured | Wave 0 ingestion from Outline Agent.json, Chapter Re-Writer Agent.json, Single Chapter Cover Image Gen.json; sha256 pins; guard-prompt-pins.py at merge |
| 2 | Book-to-HTML formatter carries 10 literal [UNCHANGED] placeholders | Full text restored from the CSV HTML Book record before pinning; a pin containing [UNCHANGED] is a hard failure |
| 3 | Live keys in the exports (OpenAI in the cover Authorization header; OpenRouter at customData.Openrouter_Api_Key) | Keys rotated at Wave 0; payload-carried key becomes an ENV credential by label; the nine JSONs NEVER committed; repo scan at merge |
| 4 | Write Chapter word-count contradiction across sources | Normalized to 2,000 to 3,500 MEASURED words everywhere |
| 5 | Make.com variable syntax inside prompt bodies | Deterministic mapping to canonical field names (SPEC 6.2); composer refuses unresolved slots |
| 6 | Brief orders a from-scratch skill and a BookWriter deprecation | Sections 3.2 and 8; scored build failures |
| 7 | One fragile blocking execution (45-day sendAndWait, zombie waits, credit deaths) | Durable ledger; idempotent one-stage jobs; fallback chain; hold-and-resume; alert dedup |
| 8 | Hardcoded test inbox receiving real participants' forms | No literal recipient exists anywhere in the engine; recipients resolve from the ledger row |
| 9 | Single-client hardcoding (pipeline and stage identifiers in nodes) | Registry binds per anthology per client at provisioning; standard pipeline AUTO-PROVISIONED with the client's own token |
| 10 | Opportunity lookup race (getAll limit 1) | contact_id keying everywhere |
| 11 | One-shot rewrite; duplicated branches | Rewrite budget 2 with gate re-entry; single code path per stage |
| 12 | Manual outline re-upload | Deleted; the ledger carries the outline |
| 13 | No anthology-level product | Stage S9 plus the Assembly card |
| 14 | Skill 53 cards to a never-seeded books department (CEO catch-all) | The engine SEEDS its own Anthology department (3.15) as a scored item |
| 15 | No participant-facing surface exists in the Command Center | The new token-scoped public route (3.17) |

---

## 10. LOOP ENGINEERING: CONTINUOUS AND SELF-CORRECTING

1. THE PARTICIPANT LOOP (runtime): every participant is a durable state machine; quality failures loop through the strike gate; credit-out holds and resumes; a six-month pause is a normal state; crashes resume idempotently; nothing is silently dropped. The daily smoke test (balance endpoints, at or under one cent) is the heartbeat substitute.
2. THE BUILD LOOP (/goal execution): ONLY sub-agents work; up to 50 agents per wave, ONE wave at a time, staggered, waves never stacked; heavy parallelism on BOTH the execution side and the QC side of each wave. Each feature or slice is built, then QC'd against the 8.5 build gate: below 8.5 it is fixed and re-QC'd; at or above 8.5 it is PUSHED to the repo. INCREMENTAL PERSISTENCE LAW (anti session-limit loss): the MOMENT a feature passes QC and is pushed, the SAME agent updates CHECKLIST.md (tick the item), TODO.md (mark done), and appends SESSION-LOG.md and CHANGE-LOG.md, so completed-and-pushed work is NEVER lost to a session limit; on resume, the unchecked items ARE the remaining work. Failed or rate-limited sub-agents re-dispatch with state passed forward; the loop never stops.
3. THE FLEET LOOP (post-build): canary on the operator box, hold at repo-only, config validation after any future fan-out, cron-inventory sweeps, and the QC matrix re-runnable as a regression gate.

---

## 11. THE TWO QC GATES (FULL TEXT IN QC-PROTOCOL-AND-MATRIX.md)

GATE A, BUILD/MERGE: the fleet 10-category rubric, threshold 8.5, administered per feature/slice by an independent QC agent (heavy QC parallelism, never the author scoring itself as final word). Below 8.5: fix and re-QC. At or above 8.5: PUSH, then tick CHECKLIST/TODO and append the logs (Section 10.2). Nobody asks the founder for a green light the rubric already grants.

GATE B, CONTENT: decides whether a deliverable ships to a producer or participant. Tier 1 hard-fail checks (binary, deterministic where possible, any single failure blocks), then the 10-dimension content rubric at 8 or higher per dimension with no averaging, then the strike cap (rewrite budget 2 at the participant gate; three internal QC attempts per deliverable, then hold and founder alert). The S9 manuscript runs its own Gate B pass plus assembly-specific checks. Gate B's pass at or above threshold is ALSO what the board contract consumes: the independent QC scorer's promotion of a card from review to done is the Gate B verdict surfacing on the board. The two gates are never conflated, substituted, or averaged into each other.

---

## 12. VERSIONING, TAGGING, AND EVERY GITHUB OPERATION

1. GitHub is the source of truth. Every GitHub operation in this build follows one law: CANARY-FIRST on the operator box; strictly SERIAL single merge-writer for every merge; COMMIT AND PUSH after each QC pass (the incremental persistence law rides every push); ANNOTATED tags only (git tag -a; a bare tag is rejected by G1); version bump to v19.0.0; FRESH-CLONE verification after merge.
2. All build work happens on branches and pull requests against the live onboarding repo. Command Center changes (department seeding config, page.tsx tiles, middleware.ts route) ride the Command Center repo's OWN serial train, same laws.
3. Before the merge: update.sh REGISTERS the new skill directory AND corrects the skill count it asserts; hash-content-manifest.py restamps _index.json content_sha for every touched skill and role file; the annotated tag v19.0.0 is created BEFORE the merge.
4. Merge order: Skill 54 extensions first, then the orchestrator skill directory, then wiring (department, roles, personas, floor), then SOPs and docs, then the PRD folder sync, then version bump and tag, then merge, then fresh-clone verification.
5. Post-merge: canary the merged repo on the operator box end to end. Fleet rollout HELD at repo-only. No client box touched. Fleet-wide grep for client identifiers on every pull request; the nine JSON exports and the n8n design doc never enter the repo.

---

## 13. DEPARTMENTS, ROLES, PERSONAS, AND SOP PLAN

DEPARTMENT (corrected by the Command Center ground truth): the build SEEDS A NEW ANTHOLOGY DEPARTMENT in the client's Command Center via Skill 32's add-department.sh (equivalently POST /api/departments with create:true). This is MANDATORY, not optional: Skill 53's books department was never seeded and its cards fall to the CEO catch-all; the Anthology Engine does not repeat that defect. On the FLEET side, the skill registers under the books/publishing floor grouping for routing (Skill 54's existing role binding), while the CLIENT-side board identity is the seeded Anthology department. The master agent's routing doctrine gains the rule: inbound anthology events dispatch to the anthology orchestrator role ONLY.

ROLES: anthology-chapter-author (exists, authoring core); anthology-producer-orchestrator (new: owns the run end to end, the ledger, the exceptions queue, escalations, S9 machinery); anthology-approvals-steward (new: owns gate hygiene, nudge cadence, the readiness report, the trigger and sign-off flow). QC independence rule: the content QC pass never runs on the persona or model tier that drafted.

PERSONA MATCHING (stage by stage; stamped into the persona-matching config at wiring so the client's workforce self-invokes the right operator per stage):

| Stage | Operating role | Named persona (lives in the pinned prompt) |
|---|---|---|
| S0 intake and routing | anthology-producer-orchestrator | none (deterministic code) |
| S1 avatar | anthology-chapter-author | the Avatar Profiler (Skill 52, pins aa-01 to aa-03) |
| S2 tone | anthology-chapter-author | the Tone Analysts and Blender (tone core 04 to 08) |
| S3 title | anthology-chapter-author | the Senior Title Strategist (aw-06) |
| S4 blurb plus outline | anthology-chapter-author | the Blurb Copywriter (aw-07) and the Outline Architect (aw-08) |
| S5 chapter | anthology-chapter-author | the Anthology Chapter Author (aw-09) |
| S6 rewrite | anthology-chapter-author | Dr. Margaret Thornfield, editorial revisionist (aw-10) |
| S7 cover | anthology-producer-orchestrator | the Senior Book-Cover Design Specialist (aw-11) |
| S8 package and deliver | anthology-producer-orchestrator | none (deterministic rendering and delivery) |
| All gates, nudges, readiness report | anthology-approvals-steward | none (gate logic; sanctioned templates only) |
| S9 assembly | anthology-producer-orchestrator | the Anthology Editor voice (ae-01 to ae-04), subordinate to producer inputs |
| Content QC (Gate B judge) | anthology-approvals-steward | the independent Editorial Judge on the JUDGE tier |

DEPARTMENT WIRING: the seeded Anthology department's how-to doc (the per-department owner guide) explains: when an anthology intake, gate event, or assembly trigger arrives, the department invokes the orchestrator skill through its entry script; cards flow via mc_board.py to POST /api/tasks/ingest; review-column semantics and QC promotion; the Assembly card. Marketing and social get READ-ONLY on published links; every other department, no access. Client humans interact only through the board, the forms, the token page, and Convert and Flow.

SOPs TO ADD (each with an enforcement pointer): Anthology Engine Runbook (anthology_state.py transition matrix); Anthology Client Onboarding (provisioning gate plus T1 to T9); Anthology Approvals and Gates (qc-strike-gate.py plus the board contract); Anthology Assembly (S9 checks); Anthology Credit Health and Queue (smoke test plus guard-cron-inventory.py); Anthology Revocation and Churn (appended to the fleet revocation runbook). SOPs TO UPDATE: Skill 54 SKILL.md; Skill 53 sibling boundary; Skill 52 handoff; the department how-to; persona matching; the floor expectations file; update-skills count.

---

## 14. PER-CLIENT CREDENTIAL NEEDS (LABELS AND LOCATIONS ONLY, NEVER VALUES)

All are the NAMED CLIENT'S OWN accounts; verification is SET or NOT SET plus a behavior probe; values never printed anywhere.

| Credential (label) | Purpose | Expected location |
|---|---|---|
| Ollama Cloud key | Primary GLM 5.2 chain | Client env stores (all three, live process env first); ollama-cloud needs baseUrl slotting |
| OpenRouter key | Fallback 1 | Client env stores; the pilot's payload-exposed key ROTATED at Wave 0 and re-homed as an ENV credential |
| Gemini key | Fallback 2 (one key, three alias names) | Client env stores per the three-alias rule |
| Minimax key | Light-task tier | Client env stores |
| DeepSeek or Kimi key (optional) | 1M-context S9 tier | Client env stores, only when configured |
| Convert and Flow private integration token (prefix pit-) | Media upload, custom fields, contacts, pipeline provisioning | Client env stores via the shared alias resolver |
| Convert and Flow Location ID | Tenant check on every call | Client env; must equal the webhook payload location |
| Kie.ai key | S7 covers | Client env stores |
| Operator's EXISTING Google service account (GOOGLE_IMPERSONATE_USER label, full Drive scope) | Drive and Docs delivery into the existing shared root (3.7) | Operator-managed, already provisioned; per-box placement decided at onboarding; NOTHING new created |
| ANTHOLOGY_INTAKE_HOOK_SECRET | Webhook route auth | Generated at provisioning, client env store or 0600 secrets file |
| ANTHOLOGY_GATE_TOKEN_SECRET | Participant token page HMAC | Generated at provisioning, client env store |
| Board ingest HMAC and Bearer (Skill 32's existing pair) | mc_board.py -> /api/tasks/ingest | Already provisioned by Command Center setup; reused, never duplicated |
| Perplexity or configured search tool key | Avatar Questions 31 and 32 | Client env; auto-detected, degrade plus flag when absent |

---

## 15. FOUNDER CONFIRMATIONS: ONBOARDING INPUTS, NOT BUILD BLOCKERS

Captured per client at onboarding; none blocks the build: (1) per-box placement of the operator-managed Google credential; (2) S9 scope sign-off per anthology (the producer fires the trigger and approves the final book, in the Assembly card, as the default); (3) the operator's awareness note that the engine is built AS an evolution of Skill 54, surfaced in the final report.

---

## 16. RISKS AND MITIGATIONS

1. Colliding duplicate skill or wrong deprecation: Sections 3.2 and 8 are scored gate items.
2. Prompt loss or truncation: the JSON exports are static files already in hand; ingestion happens at Wave 0; pins prove completeness forever; a pin containing [UNCHANGED] hard-fails.
3. Live key abuse: both exposed credentials rotate at Wave 0; the nine JSONs never enter the repo; merge-gate scan.
4. Merge-train collision: single merge-writer, serial train, annotated tag before merge, fresh-clone verification.
5. Rate-limit trips: one wave at a time, staggered inside the 50-agent wave cap; re-dispatch and resume; never stop the loop.
6. Anthropic leakage: guard-no-anthropic-runtime.py at merge plus runtime deny patterns.
7. Client-facing leakage: silence doctrine in every script; nudge templates are the only sanctioned client-facing copy.
8. Cross-client contamination: per-client secrets, tenant checks, contact_id keying, anti-commingling fingerprint.
9. Session-limit loss: the incremental persistence law (Section 10.2); pushed work plus ticked checklists mean any cold resume knows exactly what remains.
10. False done: independent verification at every layer; a sub-agent's claim is a hypothesis until verified; the canary drives a synthetic participant through every gate including a rewrite round, an exception, and a producer-fired assembly.

---

## 17. SUCCESS CRITERIA (DEFINITION OF DONE = SUCCESS)

The build is DONE only when every item in CHECKLIST.md Part C (all 26) passes, and in summary: the orchestrator skill built and the Skill 54 extensions landed, wired, and MERGED with the annotated pre-merge tag v19.0.0; update.sh registering the new skill with the corrected count; the four prompts ingested from the JSON exports, pinned, proven untruncated, [UNCHANGED] fully restored from the CSV; both exposed credentials rotated and the nine JSONs verifiably absent from the repo; the ledger, exceptions queue, and multi-anthology keying proven; the Drive tree under the existing shared root via the existing service account, the PDF font floor, media uploads, the full Section 6 field list, and the per-gate pipeline-stage updates proven with read-back; the PRODUCER COMMAND CENTER EXPERIENCE live: the Anthology department seeded, cards ingesting via mc_board.py to /api/tasks/ingest, the review-column approval queue with QC-scorer promotion proven, the Assembly card exercising the ready-to-assemble trigger with its guards and the final sign-off; the HOME-SCREEN TILES (Anthology, Podcast, Interview) merged into src/app/page.tsx on the Command Center repo's train; the PARTICIPANT TOKEN PAGE live on the new middleware-bypass route with token/PIN scoping proven (foreign and expired tokens refused); S0 through S9 proven end to end on the operator box (canary) with a synthetic participant, a rewrite round, an exception reconciliation, a producer-fired trigger, and an assembly run; Skill 53 untouched and passing its own checks; both QC gates demonstrably distinct; every persona, department, SOP, and script from Section 13 and SPEC 3.4 done; zero client-facing messages, zero secrets printed, zero Anthropic references in shipped runtime, zero client personally identifiable information in the repo; fleet rollout HELD at repo-only until the operator OK; the legacy n8n still alive pending the retirement criteria. IF THE REPO IS NOT UPDATED, IT IS NOT DONE. The build loop re-dispatches and resumes on any failure or rate limit until every item is TRUE.

---

## 18. APPENDIX: OPTIONAL LEGACY RECONCILIATION (OUT OF CORE SCOPE, NEVER A WAVE)

If the operator ever chooses to move an in-flight legacy participant into the engine, the sanctioned path is a manual, operator-initiated entry through the standard exceptions queue (reason legacy_reconciliation); no bridge workflow, migration script, or reconciliation tooling ships with the skill.
