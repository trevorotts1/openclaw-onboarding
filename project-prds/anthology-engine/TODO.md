# TODO, ANTHOLOGY ENGINE BUILD (LIVE WAVE-BY-WAVE TASK LIST)
### Version 3.0, Fable, 2026-07-06 (revision 3, aligned to PRD.md, SPEC.md, WAVE-PLAN.md, and GOAL-COMMAND.txt at revision 3: 50-agents-per-wave single-wave model; producer experience inside the client's own Command Center as the seeded Anthology department/board; prompt ingestion from the Downloads JSON exports; participant token page; v19.0.0 target).
### This file is the RESUME INDEX. On any cold resume, the unchecked items below ARE the remaining work. Task numbering here matches WAVE-PLAN.md exactly; SPEC.md Section 16 traceability depends on these ids, never renumber.

## HOW THIS LIST IS WORKED (binding)
1. ONLY SUB-AGENTS BUILD. The orchestrator delegates everything and never builds in its own loop. Execution sub-agents run Opus; QC sub-agents are independent of the authors they score.
2. WAVE MODEL: up to 50 agents per wave INCLUDING the QC bank, ONE wave at a time, dispatch STAGGERED inside the wave to stay under rate limits; waves are NEVER stacked. A wave is complete only when every one of its items is DONE (pushed) or explicitly carried forward with a logged reason.
3. THE 8.5 BUILD GATE (Gate A) PER ITEM: built, then scored by an independent QC agent on the fleet 10-category rubric. Below 8.5: fix and re-QC, autonomously, as many rounds as it takes. At or above 8.5: COMMIT AND PUSH immediately.
4. INCREMENTAL PERSISTENCE LAW (anti session-limit loss): the MOMENT an item passes QC and is pushed, the SAME agent (a) flips the item below to [x] DONE with gate score, verifier, and commit reference, (b) ticks the matching CHECKLIST.md item, (c) appends SESSION-LOG.md and CHANGE-LOG.md, (d) appends one row to the progress log at the bottom of this file. Completed-and-pushed work is NEVER lost to a session limit.
5. NEVER STOP: on any failure or rate limit, re-dispatch the agent with state passed forward (resumeFromRunId); a sub-agent's claim of done is a hypothesis until independently verified.
6. GITHUB, EVERY OPERATION: canary-first on the operator box; strictly SERIAL single merge-writer; commit and push after each QC pass; ANNOTATED tags only (git tag -a); version v19.0.0 (locked, NOT v18); fresh-clone verification. Command Center repo changes ride THAT repo's own serial train, same laws.
7. DOCTRINE ON EVERY TASK: move in silence (operator-verbose, never client-facing); NOTHING Anthropic in any runtime file; credentials by label and location only, never value; the platform is Convert and Flow in every surface; config writes as the node user, never root; zero client personally identifiable information in any repo; the NINE Downloads JSON exports are NEVER committed; the legacy n8n stays alive and untouched.

STATUS VOCABULARY: PENDING / IN-PROGRESS(agent) / BLOCKED(reason) / GATE-FAIL(score) / CARRIED-FORWARD(reason) / DONE(score; verified-by; commit). Flip status in place on the item line; never delete or reorder items.

HARD DEPENDENCIES (from WAVE-PLAN.md): W0.2 before W1.3 and W1.12; W0.7 before Wave 3; W1.7 before Wave 3 and W1.15; Waves 1+2+3+4 all green before Wave 5; Wave 5 fully green before Wave 6; Wave 6 before Wave 7. Wave 0 completes before anything downstream starts.

---

## WAVE 0: INGEST, HYGIENE, AND LIVE VERIFICATION (up to 12 execution agents + QC bank; W0.1 gates entry; outputs land in the operator-side build-state file, never the repo)
- [ ] W0.1 Repo baseline snapshot: live content version (verify main below v19.0.0), gate inventory, update.sh skill count, _index.json layout, Skills 52/53/54 and tone-core state, next free skill number, project-prds/ location. PENDING
- [ ] W0.2 PROMPT INGESTION FROM THE JSON EXPORTS (highest priority; no live n8n dependency): parse Outline Agent.json (Create Outline), Chapter Re-Writer Agent.json (Thornfield rewriter + Book-to-HTML formatter), Single Chapter Cover Image Gen.json (cover prompt generator) in <OPERATOR_HOME>/Downloads/anthology project/, plus Primary Goal extraction from Avatar Agent.json; extract VERBATIM; RESTORE the formatter's 10 literal [UNCHANGED] placeholders from the CSV record HTML Book (Full Book Prompts-Grid view.csv); NORMALIZE the Write Chapter word band to 2,000 to 3,500; MAP Make.com variable syntax to canonical field names; sha256-pin everything; prove zero truncation and zero remaining [UNCHANGED]; record ingestion evidence in SESSION-LOG.md. PENDING
- [ ] W0.3 SECRET HYGIENE: rotate both exposed credentials by label (the legacy image-service key in the cover node Authorization header; the routing key at customData.Openrouter_Api_Key); re-home the payload-carried key as an ENV credential by label; confirm the nine JSON exports sit OUTSIDE every repo working tree; add the merge-gate scan that keeps them out; values never printed anywhere. PENDING
- [ ] W0.4 LIVE-VERIFY the OpenClaw inbound webhook and skill packaging against the installed gateway version on the operator box. PENDING
- [ ] W0.5 LIVE-VERIFY the Convert and Flow surfaces: media upload, custom-field create/write/read-back, contact lookups by contact_id, form hidden-field behavior, pipeline and stage provisioning through a private integration token (Skills 44 and 29 patterns). PENDING
- [ ] W0.6 LIVE-VERIFY the Kie.ai TEXT-TO-IMAGE PORTRAIT endpoint at 1024x1536 with GPT-image-2 (NOT the 16:9 presentation recipe; verify the portrait endpoint shape fresh) plus the Skill 46 callback relay; DIRECT Drive and Docs API access with the operator's EXISTING service account (clawd/google-api.js pattern, GOOGLE_IMPERSONATE_USER label) including view-only sharing AND reachability of the existing shared delivery root (PRD 3.7); the deterministic HTML-to-PDF toolchain with a 14-point-floor render probe. PENDING
- [ ] W0.7 COMMAND CENTER GROUND-TRUTH VERIFY (read-only, operator box checkout): the add-department.sh / POST /api/departments create:true seeding path; the POST /api/tasks/ingest HMAC-plus-Bearer contract and its fail-soft client in mc_board.py; the review-column board contract and QC-scorer review-to-done promotion; the hardcoded tile array in src/app/page.tsx; the middleware.ts bypass-list mechanism; pin file paths and shapes into the build-state file. PENDING
- [ ] W0.8 Reuse-asset inventory pinned: exact paths and versions of the Skill 54 provers and prompts, the Skill 52 avatar pipeline, the tone core, mc_board.py, Skills 44, 36, 29, 14, 07, 46, 50, 32. PENDING
- [ ] W0.9 Balance-endpoint discovery pinned to config (Ollama Cloud, OpenRouter, Gemini, Minimax, Kie.ai); PRD set copied into the onboarding branch at project-prds/anthology-engine/ (scrubbed; the n8n design doc stays operator-side). PENDING

## WAVE 1: CORE ENGINE AUTHORING (up to 50 agents: about 24 execution + matching QC bank; fully parallel on branches)
- [ ] W1.1 Orchestrator SKILL.md runbook: S0 to S9, layer boundaries, silence rules, the Skill 54 call contract, sibling boundaries (53/54). PENDING
- [ ] W1.2 Skill 54 extension 1: the Skill 52 avatar handoff (S1); every existing AF-AW prover stays green. PENDING
- [ ] W1.3 Skill 54 extension 2: the W0.2-pinned prompts wired (outline, Thornfield rewriter, cover prompt, primary-goal extraction) into the phase machine; zero truncation, zero [UNCHANGED]. PENDING
- [ ] W1.4 Skill 54 extension 3: intake schema fields ideal_avatar, niche, primary_goal; prove_aw_intake.py still rejects credential-shaped keys. PENDING
- [ ] W1.5 Intake router (intake_router.py): deterministic parse, hidden-field validation, tenant check, contact_id keying, dedup no-op, exceptions capture, fast acknowledge. PENDING
- [ ] W1.6 Webhook layer: route template, per-client secret, the T1 to T9 verifier (verify-webhook-t1-t9.sh), fixture payloads and unit tests. PENDING
- [ ] W1.7 anthology_state.py, the sole ledger writer: base schema, local mirror, legal-transition matrix, all subcommands including s9_ready with every PRD 3.11 guard, reconcile. PENDING
- [ ] W1.8 Anthology registry and provisioning bindings (anthology_registry.py): AUTO-PROVISION the standard Anthology pipeline in the client's own Convert and Flow account with the client's own token (PRD 3.12; existing-pipeline binding only as explicit override); per-anthology stage map (drives the per-gate pipeline-stage update); form registration; Section 6 field create-or-verify artifact. PENDING
- [ ] W1.9 Model routing (model_router.py): GLM 5.2 on Ollama Cloud (thinking high, temperature 0.3), then OpenRouter GLM 5.2, then Gemini 3.5 Flash, then durable hold plus gateway Telegram alert; Minimax V3 light tier; optional DeepSeek V4 Pro / Kimi 2.6 1M-context tier; Anthropic deny patterns. PENDING
- [ ] W1.10 Web-search detection ladder (search_detect.py): prefer Perplexity; degrade gracefully plus Telegram flag. PENDING
- [ ] W1.11 Drive delivery adapter (drive_adapter.py + drive-tree-provision.py): Doc creation via DIRECT Drive API with the existing service account, Root/Producer/Anthology/Participant tree under the EXISTING root, view-only sharing, export bundle; never creates new Google plumbing. PENDING
- [ ] W1.12 PDF renderer (pdf_render.py): deterministic HTML-to-PDF, house templates seeded from the harvested formatter content rules (the [UNCHANGED]-restored text), guard-font-floor.py over the RENDERED file. PENDING
- [ ] W1.13 Convert and Flow delivery adapter (caf_delivery.py): media upload with verification, exact-key field writes keyed by contact_id, byte-for-byte read-back, the three control fields, the per-gate pipeline-stage update. PENDING
- [ ] W1.14 Cover module (cover_render.py): pin aw-11, Kie.ai GPT-image-2 portrait 1024x1536 via the W0.6-verified endpoint, Skills 07/46 callback handling with bounded re-poll, Drive landing. PENDING
- [ ] W1.15 Gate and nudge engine (gate_engine.py + nudge_send.py): gate state machine, the three sanctioned nudge templates, participant token/PIN mint and verify under ANTHOLOGY_GATE_TOKEN_SECRET (single-gate scope, expiry, refusal of foreign/expired/replayed tokens), both-door single-endpoint contract, 7-day stuck re-nudge, ledger-resolved recipients only. PENDING
- [ ] W1.16 Strike gate (qc-strike-gate.py): participant rewrite budget 2 with gate re-entry, internal QC attempts 3, hold-and-alert. PENDING
- [ ] W1.17 Content QC (qc-tier1-anthology.py + judge_harness.py): the full Tier 1 check set, assembly mode, the judge harness on the JUDGE tier (never the drafting tier). PENDING
- [ ] W1.18 S9 assembly module (stage_s9_assembly.py): readiness report, arming, the s9_ready trigger machinery with every PRD 3.11 guard in the writer, order curation (ae-01), editor's introduction (ae-02), bios (ae-03), front/back matter (ae-04), chunked and 1M-context compile paths from FROZEN chapters, assembly-scope checks. PENDING
- [ ] W1.19 Exceptions queue mechanics (exceptions.py): capture, list, resolve-and-replay through S0, legacy_reconciliation entry type. PENDING
- [ ] W1.20 Credit-out hold queue (hold_queue.py): durable hold, daily age tick, resume from exact cursor. PENDING
- [ ] W1.21 Cost ledger (anthology-cost-ledger.py): metering choke point, ceilings, per-deliverable budgets shared across QC attempts. PENDING
- [ ] W1.22 Smoke test (anthology-smoke-test.py): balance endpoints only, total spend at or under one cent, hold-queue aging. PENDING
- [ ] W1.23 Golden fixtures: full synthetic participant (all stages plus one rewrite round), two-anthology contact, exception fixture, assembly fixture with three synthetic chapters, attack variants per guard. PENDING
- [ ] W1.24 Delivery report generator and signed process certificate, operator channel only. PENDING

## WAVE 2: GUARDRAIL AND ENFORCEMENT COMPLETIONS (up to 50: about 8 execution + QC bank; parallel)
- [ ] W2.1 guard-prompt-pins.py: every pin matches, zero truncation, zero [UNCHANGED], zero runtime references to any legacy prompt base. PENDING
- [ ] W2.2 guard-no-anthropic-runtime.py over the FULL engine file set including every Command Center edit (department config, tiles, token route). PENDING
- [ ] W2.3 caf_credential_gate.py: label resolution across all three env stores live-process-first, pairing proof, anti-commingling fingerprint; reports SET or NOT SET only. PENDING
- [ ] W2.4 alert-dedup.py: keying, windows, storm cap, gateway-only Telegram path. PENDING
- [ ] W2.5 guard-cron-inventory.py: exactly the one daily tick, no heartbeat entry ever; churn leaves zero recurring jobs. PENDING
- [ ] W2.6 provision-anthology-client.sh: the full SPEC 13.1 provisioning including pipeline auto-provision and Anthology department seeding; config writes as the node user. PENDING
- [ ] W2.7 revoke-anthology-client.sh: token invalidation, board archival, Drive share revocation, route disable, export bundle, verification probe, zero recurring jobs left. PENDING
- [ ] W2.8 Static scans: no-secret scan, no-client-identifier grep, no-JSON-export-content scan, Skill 53 untouched check. PENDING

## WAVE 3: COMMAND CENTER INTEGRATION (Command Center repo, its OWN serial train; 3 execution Opus agents + QC bank; needs W0.7 and W1.7)
- [ ] W3.1 SEED THE ANTHOLOGY DEPARTMENT AND WIRE THE BOARD CONTRACT: add-department.sh / POST /api/departments create:true seeding in provisioning (idempotent, read back to verify); mc_board.py card ingest to POST /api/tasks/ingest (HMAC plus Bearer, fail-soft, board unreachability never blocks the pipeline); one card per participant with status mirroring stage_cursor; the review column as the chapter-approval queue on the EXISTING board contract (producer output routes to review; ONLY the independent QC scorer at or above 8.5 promotes review to done, the engine never self-promotes); the dedicated Assembly card carrying the readiness report, the ready-to-assemble trigger, and the final sign-off as status transitions plus writer approvals rows. Skill 53's never-seeded books-department defect documented and NOT repeated. PENDING
- [ ] W3.2 HOME-SCREEN TILES (code edit by an Opus agent): edit the hardcoded tile array in command-center src/app/page.tsx to add the ANTHOLOGY tile (deep-link to the Anthology department board), the PODCAST tile, and the INTERVIEW tile, matching the existing tile shape; nothing Anthropic, nothing client-identifying. PENDING
- [ ] W3.3 PARTICIPANT TOKEN PAGE (new code): one token-scoped public route added to the middleware.ts bypass list (the /api/health mechanism) plus its page, serving ONLY the participant's open gate (S3 title selection, S4 outline approval, S5 approve-or-rewrite with notes); token/PIN minted by gate_engine.py under ANTHOLOGY_GATE_TOKEN_SECRET; foreign, expired, and replayed tokens refused; the client-clean serializer on every response. PENDING

## WAVE 4: WIRING, ROLES, SOPS, DOCS (up to 50: about 12 execution + QC bank; needs the Wave 1 shape settled)
- [ ] W4.1 Department wiring: the seeded Anthology department registered in the fleet floor files; the department how-to doc (per-department owner guide) gains the self-invocation entry (intake, gate events, and the assembly trigger invoke the orchestrator skill through its entry script); the floor check passes. PENDING
- [ ] W4.2 Roles: anthology-producer-orchestrator and anthology-approvals-steward added; the PRD Section 13 stage-to-role-to-persona matching table stamped into the persona-matching config; QC independence wired (the content judge never runs on the drafting tier). PENDING
- [ ] W4.3 Board wiring, engine side: the mc_board.py card vocabulary mapped to stage_cursor and the review/done contract of W3.1. PENDING
- [ ] W4.4 SOP: Anthology Engine Runbook (enforcement pointer: the anthology_state.py transition matrix). PENDING
- [ ] W4.5 SOP: Anthology Client Onboarding (enforcement pointer: the provisioning gate plus T1 to T9). PENDING
- [ ] W4.6 SOP: Anthology Approvals and Gates (enforcement pointer: qc-strike-gate.py plus the board contract). PENDING
- [ ] W4.7 SOP: Anthology Assembly (enforcement pointer: the S9 checks). PENDING
- [ ] W4.8 SOP: Anthology Credit Health and Queue (enforcement pointer: the smoke test plus guard-cron-inventory.py). PENDING
- [ ] W4.9 SOP: Anthology Revocation and Churn, APPENDED to the fleet revocation runbook, never a competing document. PENDING
- [ ] W4.10 Doc updates: Skill 54 SKILL.md (extensions and the orchestrator relationship), the Skill 53 sibling boundary, the Skill 52 handoff, floor expectations, how-to docs. PENDING
- [ ] W4.11 Master agent routing rule: inbound anthology events dispatch to the anthology orchestrator role ONLY. PENDING
- [ ] W4.12 update.sh registration prepared (the new skill directory plus the corrected skill count), staged for the Wave 6 train. PENDING

## WAVE 5: CANARY INTEGRATION ON THE OPERATOR BOX (up to 50: about 8 execution + QC bank; drills run SERIAL on the one canary box; needs Waves 1 to 4)
- [ ] W5.1 Branch build installed on the operator box (canary; the operator box is separate from the fleet; no client box touched). PENDING
- [ ] W5.2 Operator box provisioned as a synthetic producer: own secrets, own route, the Anthology department seeded and visible, tiles rendering, one synthetic anthology with three synthetic participants. PENDING
- [ ] W5.3 T1 to T9 EXECUTED AND OBSERVED, including the real public URL test through the named Cloudflare Tunnel; results recorded. PENDING
- [ ] W5.4 Golden participant end to end S0 through S8: every gate exercised from BOTH doors (board card and token page); Doc plus PDF pairs verified; field read-backs verified; per-gate pipeline-stage updates observed; the card observed landing in review and promoting to done ONLY via the QC scorer. PENDING
- [ ] W5.5 Force-failure drills: forced Tier 1 failure blocks; forced rubric failure blocks; strike cap trips and alerts (deduped); rewrite budget exhausts correctly; credit-out holds and resumes; duplicate webhook no-ops; wrong-tenant and unroutable submissions land in exceptions and reconcile; kill-and-resume mid-stage loses nothing; board unreachable does not block the pipeline (fail-soft proven); foreign and expired participant tokens refused. PENDING
- [ ] W5.6 Two-anthology drill: the same test contact in two anthologies, two participant records, one contact_id, cleanly separated by anthology_id. PENDING
- [ ] W5.7 S9 assembly drill: the ready-to-assemble trigger exercised from BOTH doors with every guard forced (non-producer refused; unapproved-participant blocking list shown; below-minimum chapter count refused; confirm-name mismatch refused; double-fire no-op), one explicit exclusion recorded, then three synthetic chapters ordered, introduction and matter generated, manuscript compiled, sign-off on the Assembly card, manuscript fields pushed and read back. PENDING
- [ ] W5.8 Gate battery: anthropic guard, prompt-pin guard (incl. zero [UNCHANGED]), font-floor guard, cron inventory, credential gate, silence and secrecy audit, fleet-wide client-identifier grep, JSON-export-absence scan, Skill 53 regression, tone-core sync; every unit Gate-A scored; below 8.5 loops back autonomously. PENDING

## WAVE 6: THE SERIAL MERGE TRAIN (ONE merge-writer agent; strictly serial; nothing else merges anywhere during it; needs Wave 5 fully green)
- [ ] W6.1 Skill 54 extensions merged (smallest certified surface) plus content_sha restamp. PENDING
- [ ] W6.2 The orchestrator skill directory merged (runbook, modules, configs, scripts, fixtures, tests). PENDING
- [ ] W6.3 Wiring merged (department, roles, personas, floor). PENDING
- [ ] W6.4 SOPs and doc updates merged. PENDING
- [ ] W6.5 PRD folder synced at project-prds/anthology-engine/ (scrubbed set; n8n design doc stays operator-side). PENDING
- [ ] W6.6 update.sh: the new skill REGISTERED and the skill count corrected. PENDING
- [ ] W6.7 _index.json content_sha restamped via hash-content-manifest.py across every touched file. PENDING
- [ ] W6.8 Version bumped to v19.0.0 (locked, NOT v18; W0.1 confirmed live main below it). PENDING
- [ ] W6.9 ANNOTATED tag v19.0.0 (git tag -a) created BEFORE the merge (a bare tag is rejected). PENDING
- [ ] W6.10 Merge complete; fresh-clone verification from GitHub passed: version, tag, skill count, content hashes, clean install via the standard updater, JSON-export-absence scan against the fresh clone. Command Center repo changes (W3.1 to W3.3) merged on THAT repo's own serial train, same laws, cross-referenced in CHANGE-LOG.md. PENDING

## WAVE 7: POST-MERGE CANARY, FREEZE POSTURE, AND HOLD (3 agents + QC; serial)
- [ ] W7.1 Merged-repo canary re-run: W5.3 to W5.8 re-executed from the MERGED repos on the operator box (prove the merged artifact, not the branch). PENDING
- [ ] W7.2 FREEZE posture recorded: no new participants enter n8n once the engine intake is live; the legacy stack ALIVE and UNTOUCHED; retirement criteria recorded, NOT executed; no bridge or migration tooling anywhere. PENDING
- [ ] W7.3 HOLD recorded: fleet rollout repo-only until the operator OK. Final operator report (what merged, gate scores, canary evidence, the Skill 53 non-deprecation verdict, the architecture decision surfaced, the onboarding-inputs list, the hold). CHECKLIST.md Part C (all 26) verified item by item; memory and session log synced. DONE only when every Part C item is TRUE and BOTH repos are updated; if a repo is not updated, it is NOT done. PENDING

---

## AGENT PROGRESS LOG (append-only below this line; one row per status change; never edit or delete existing rows, only flip the item statuses above)
| Timestamp | Task | Agent | Status | Branch/PR (repo) | Gate score | Commit/Tag | Notes |
|---|---|---|---|---|---|---|---|
