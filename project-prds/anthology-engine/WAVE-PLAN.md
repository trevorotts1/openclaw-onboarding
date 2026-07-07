# WAVE PLAN, ANTHOLOGY ENGINE BUILD
### Execution directed acyclic graph: what runs in parallel, what MUST serialize
### Version 3.0, Fable, 2026-07-06 (revision 3: 50-agents-per-wave single-wave model; producer experience relocated into the client's own Command Center department/board; prompt ingestion from the Downloads JSON exports; incremental persistence law; v19.0.0 target)

GLOBAL RULES (binding on every wave):
1. ONLY SUB-AGENTS DO THE WORK. The orchestrator delegates EVERYTHING and never builds in its own loop. Execution sub-agents run Opus; QC sub-agents are independent of the authors they score.
2. WAVE MODEL: up to 50 agents PER WAVE, ONE wave at a time, dispatch STAGGERED inside the wave to stay under rate limits; waves are NEVER stacked (no wave starts until the previous wave's every unit is either pushed or explicitly carried forward). Heavy parallelism runs on BOTH sides of every wave: the execution agents in front, an equally parallel bank of QC agents behind them.
3. THE 8.5 QC GATE, PER FEATURE/SLICE: each unit is built, then QC'd on the fleet 10-category rubric by an independent QC agent. Below 8.5: fixed and re-QC'd, autonomously, as many rounds as it takes. At or above 8.5: COMMIT AND PUSH to the repo immediately.
4. INCREMENTAL PERSISTENCE LAW (anti session-limit loss): the MOMENT a unit passes QC and is pushed, the SAME agent updates CHECKLIST.md (tick the item), TODO.md (mark done), and appends SESSION-LOG.md and CHANGE-LOG.md. Completed-and-pushed work is NEVER lost to a session limit; on any cold resume, the unchecked CHECKLIST/TODO items ARE the remaining work.
5. GITHUB, EVERY OPERATION: canary-first on the operator box; strictly SERIAL single merge-writer for every merge; commit and push after each QC pass; ANNOTATED tags only (git tag -a); version bump to v19.0.0; fresh-clone verification. Build on branches and pull requests; the onboarding repo has ONE merge-writer and ALL merges are serial in Wave 6. Any Command Center repo change rides that repo's OWN separate serial train, same laws.
6. NEVER STOP: on any failure or rate limit, re-dispatch the agent with state passed forward (resumeFromRunId); a sub-agent's claim of done is a hypothesis until the wave's independent verification confirms it.
7. DOCTRINE: MOVE IN SILENCE, zero client-facing messages from any wave; never print a secret value, credentials by label and location only; the platform is Convert and Flow in every surface; config writes as the node user, never root; zero Anthropic in any runtime file; zero client personally identifiable information in the repo; the NINE Downloads JSON exports are NEVER committed.
8. CANARY DOCTRINE: everything is proven on the operator box first. NO client box is touched. Fleet rollout is HELD at repo-only until the operator OK. The legacy n8n stays ALIVE per the deprecation plan; NO wave edits any legacy workflow; NO bridge or migration tooling exists in this plan.

---

## WAVE 0: INGEST, HYGIENE, AND LIVE VERIFICATION (up to 12 execution agents + QC bank; serialize entry, parallel inside)

Nothing downstream starts until Wave 0's outputs are written to the build-state file (operator box only, never the repo).

- W0.1 Repo baseline snapshot: live content version (verify main is below v19.0.0), gate inventory, update.sh skill count, _index.json layout, Skill 53/54/52 and tone-core state, next free skill number, project-prds/ location.
- W0.2 PROMPT INGESTION FROM THE JSON EXPORTS (highest priority; no live n8n dependency): parse Outline Agent.json (Create Outline), Chapter Re-Writer Agent.json (the Thornfield rewriter and the Book-to-HTML formatter), and Single Chapter Cover Image Gen.json (the cover prompt generator) in /Users/blackceomacmini/Downloads/anthology project/; extract the four largest prompts VERBATIM plus Primary Goal extraction from Avatar Agent.json; RESTORE the formatter's 10 literal [UNCHANGED] placeholders from the CSV record HTML Book in Full Book Prompts-Grid view.csv; NORMALIZE the Write Chapter word band to 2,000 to 3,500; MAP Make.com variable syntax to the canonical field names; sha256-pin everything; prove zero truncation and zero remaining [UNCHANGED]; record ingestion evidence in SESSION-LOG.md.
- W0.3 SECRET HYGIENE: rotate both exposed credentials by label (the OpenAI key in the cover node's Authorization header; the OpenRouter key at customData.Openrouter_Api_Key); re-home the payload-carried key as an ENV credential by label; confirm the nine JSON exports sit OUTSIDE every repo working tree and add the merge-gate scan that keeps them out; values never printed.
- W0.4 LIVE-VERIFY OpenClaw inbound webhook and skill-packaging docs against the installed gateway version on the operator box.
- W0.5 LIVE-VERIFY the Convert and Flow surfaces: media upload, custom-field create/write/read-back, contact lookups by contact_id, form hidden-field behavior, pipeline and stage provisioning through a private integration token.
- W0.6 LIVE-VERIFY the Kie.ai TEXT-TO-IMAGE PORTRAIT endpoint at 1024x1536 with GPT-image-2 (this is NOT the 16:9 presentation recipe; verify the portrait endpoint shape fresh) plus the Skill 46 callback relay; DIRECT Drive and Docs API access with the operator's EXISTING service account (clawd/google-api.js pattern, GOOGLE_IMPERSONATE_USER label) including view-only sharing AND reachability of the existing shared delivery root (PRD 3.7 link); the deterministic HTML-to-PDF toolchain with a 14-point-floor render probe.
- W0.7 COMMAND CENTER GROUND-TRUTH VERIFY (read-only): confirm on the operator box's command-center checkout the add-department.sh / POST /api/departments create:true seeding path, the POST /api/tasks/ingest HMAC-plus-Bearer contract and its fail-soft client in mc_board.py, the review-column board contract and the QC-scorer review-to-done promotion, the hardcoded tile array in src/app/page.tsx, and the middleware.ts bypass-list mechanism; pin file paths and shapes into the build-state file.
- W0.8 Reuse-asset inventory pinned: exact paths and versions of Skill 54 provers and prompts, Skill 52 avatar pipeline, tone core, mc_board.py, Skills 44, 36, 29, 14, 07, 46, 50, 32.
- W0.9 Balance-endpoint discovery for the smoke test (Ollama Cloud, OpenRouter, Gemini, Minimax, Kie.ai) pinned to config; copy the PRD set into the onboarding branch at project-prds/anthology-engine/ (scrubbed; the n8n design doc stays operator-side).

## WAVE 1: CORE ENGINE AUTHORING (up to 50 agents: about 24 execution + matching QC bank; fully parallel on branches)

- W1.1 Orchestrator SKILL.md runbook: S0 to S9, layer boundaries, silence rules, the Skill 54 call contract, sibling boundaries (53/54).
- W1.2 Skill 54 extension: the Skill 52 avatar handoff (S1); all existing provers stay green.
- W1.3 Skill 54 extension: the newly pinned prompts wired (outline, rewriter, cover prompt, primary-goal extraction) into the phase machine, from the W0.2 ingestion.
- W1.4 Skill 54 extension: intake schema fields ideal_avatar, niche, primary_goal.
- W1.5 Intake router: deterministic parser, hidden-field validation, tenant check, contact_id keying, dedup no-op, exceptions capture, fast acknowledge.
- W1.6 Webhook layer: route template, per-client secret, T1 to T9 verifier, fixture payloads and unit tests.
- W1.7 Ledger writer anthology_state.py: base schema, mirror, legal-transition matrix, all subcommands including s9_ready with guards, reconcile.
- W1.8 Anthology registry and provisioning bindings: AUTO-PROVISION the standard Anthology pipeline in the client's own Convert and Flow account with the client's own token (override binding only by exception); stage map per anthology (drives the per-gate pipeline-stage update); form registration; field create-or-verify.
- W1.9 Model routing: the GLM 5.2 Ollama Cloud chain (thinking high, temp 0.3), OpenRouter GLM 5.2, Gemini 3.5 Flash, hold-and-alert on exhaustion; Minimax V3 light tier; optional DeepSeek V4 Pro / Kimi 2.6 1M tier; Anthropic deny patterns.
- W1.10 Web-search detection ladder (prefer Perplexity; degrade plus flag).
- W1.11 Drive delivery adapter: drive-tree-provision.py, Doc creation via direct Drive API with the existing service account, view-only sharing, export bundle.
- W1.12 PDF renderer: deterministic HTML-to-PDF, house templates seeded from the harvested formatter content rules (the [UNCHANGED]-restored text), guard-font-floor.py.
- W1.13 Convert and Flow delivery adapter: media upload with verification, exact-key field writes keyed by contact_id, byte-for-byte read-back, control fields, per-gate pipeline-stage update.
- W1.14 Cover module: pin aw-11, Kie.ai GPT-image-2 portrait 1024x1536 via the W0.6-verified endpoint, Skills 07/46 callback handling, Drive landing.
- W1.15 Gate and nudge engine: gate state machine, sanctioned nudge templates, participant token/PIN mint and verify (single-gate scope, expiry, refusal of foreign/expired/replayed tokens), both-door single-endpoint contract, 7-day stuck re-nudge.
- W1.16 Strike gate: rewrite budget 2 with gate re-entry, internal attempts 3, hold-and-alert.
- W1.17 Content QC: qc-tier1-anthology.py full check set, assembly mode, judge harness on the JUDGE tier (never the drafting tier).
- W1.18 S9 assembly module: readiness report, arming, the s9_ready trigger machinery with every PRD 3.11 guard in the writer, order curation, editor's introduction, front and back matter, bios, chunked and 1M-context compile paths, assembly-scope checks.
- W1.19 Exceptions queue mechanics: capture, reconciliation replay, legacy_reconciliation entry type.
- W1.20 Credit-out hold queue: hold, daily age tick, resume from cursor.
- W1.21 Cost ledger: metering choke point, ceilings, per-deliverable budgets.
- W1.22 Smoke test: balance endpoints only, at or under one cent, hold-queue aging.
- W1.23 Golden fixtures: full synthetic participant (all stages plus a rewrite round), two-anthology contact, exception fixture, assembly fixture with three synthetic chapters.
- W1.24 Delivery report generator and signed process certificate, operator channel only.

## WAVE 2: GUARDRAIL AND ENFORCEMENT COMPLETIONS (up to 50: about 8 execution + QC bank)

- W2.1 guard-prompt-pins.py (pins, zero truncation, zero [UNCHANGED], no runtime prompt-base references).
- W2.2 guard-no-anthropic-runtime.py over the full engine file set including every Command Center edit.
- W2.3 caf_credential_gate.py (label resolution across all three env stores live-process-first, pairing proof, anti-commingling fingerprint).
- W2.4 alert-dedup.py (keying, windows, storm cap, gateway-only Telegram).
- W2.5 guard-cron-inventory.py (exactly one daily tick; churn leaves zero recurring jobs).
- W2.6 provision-anthology-client.sh (full provisioning incl. pipeline auto-provision and Anthology department seeding; config writes as the node user).
- W2.7 revoke-anthology-client.sh (token invalidation, board archival, Drive share revocation, route disable, export, verification probe).
- W2.8 Static scans: no-secret scan, no-client-identifier grep, no-JSON-export-content scan, Skill 53 untouched check.

## WAVE 3: COMMAND CENTER INTEGRATION (Command Center repo, its OWN serial train; up to 50: 3 execution Opus agents + QC bank; starts when W1.7's schema is settled)

- W3.1 SEED THE ANTHOLOGY DEPARTMENT AND WIRE THE BOARD CONTRACT: add-department.sh / POST /api/departments create:true seeding path in provisioning; mc_board.py card ingest to POST /api/tasks/ingest (HMAC plus Bearer, fail-soft); one card per participant with status mirroring stage_cursor; the review column as the chapter-approval queue riding the EXISTING board contract (producer output routes to review; ONLY the independent QC scorer at or above 8.5 promotes review to done, the engine never self-promotes); the dedicated Assembly card carrying the readiness report, the ready-to-assemble trigger, and the final sign-off as status transitions plus writer approvals rows. PROOF: Skill 53's never-seeded books department defect documented and not repeated.
- W3.2 HOME-SCREEN TILES (code edit by an Opus agent): edit the hardcoded tile array in command-center src/app/page.tsx to add the ANTHOLOGY tile (deep-link to the Anthology board), the PODCAST tile, and the INTERVIEW tile, matching the existing tile shape; nothing Anthropic, nothing client-identifying.
- W3.3 PARTICIPANT TOKEN PAGE (new code): one token-scoped public route added to the middleware.ts bypass list (the /api/health mechanism), plus its page serving ONLY the participant's open gate (S3 title selection, S4 outline approval, S5 approve-or-rewrite with notes); token/PIN minted by gate_engine.py under ANTHOLOGY_GATE_TOKEN_SECRET; foreign, expired, and replayed tokens refused; client-clean serializer on every response.

## WAVE 4: WIRING, ROLES, SOPS, DOCS (up to 50: about 12 execution + QC bank; needs W1 shape settled)

- W4.1 Department wiring: the seeded Anthology department registered in the fleet floor files; the department how-to doc (per-department owner guide) gains the self-invocation entry (intake, gate events, assembly trigger invoke the orchestrator skill through its entry script); floor check passes.
- W4.2 Roles: anthology-producer-orchestrator and anthology-approvals-steward added; the PRD Section 13 stage-to-role-to-persona matching table stamped into the persona-matching config; QC independence wired.
- W4.3 Board wiring (engine side): mc_board.py card vocabulary mapped to stage_cursor and the review/done contract of W3.1.
- W4.4 to W4.9 The six SOPs (Runbook, Client Onboarding, Approvals and Gates, Assembly, Credit Health and Queue, Revocation and Churn appended to the fleet runbook), each with its enforcement pointer.
- W4.10 Doc updates: Skill 54 SKILL.md (extensions and orchestrator relationship), Skill 53 sibling boundary, Skill 52 handoff, floor expectations, how-to docs.
- W4.11 Master agent routing: inbound anthology events dispatch to the anthology orchestrator role ONLY.
- W4.12 update.sh registration prepared (the new skill directory plus corrected skill count), staged for the Wave 6 train.

## WAVE 5: CANARY INTEGRATION ON THE OPERATOR BOX (up to 50: about 8 execution + QC bank; mostly serial drills; needs W1 to W4)

- W5.1 Install the branch build on the operator box (canary; operator box is separate from the fleet).
- W5.2 Provision the operator box as a synthetic producer: own secrets, own route, the Anthology department seeded and visible, tiles rendering, one synthetic anthology with three synthetic participants.
- W5.3 Execute T1 to T9 including the real public URL test; record observed results.
- W5.4 Golden-fixture participant end to end S0 through S8: every gate exercised from BOTH doors (board card and token page); Doc plus PDF pairs verified; field read-backs verified; per-gate pipeline-stage updates observed; the card observed landing in review and promoting to done ONLY via the QC scorer.
- W5.5 Force-failure drills: forced Tier 1 failure blocks; forced rubric failure blocks; strike cap trips and alerts (deduped); rewrite budget exhausts correctly; credit-out holds and resumes; duplicate webhook no-ops; wrong-tenant and unroutable submissions land in exceptions and reconcile; kill-and-resume mid-stage loses nothing; board unreachable does not block the pipeline (fail-soft proven); foreign and expired participant tokens refused.
- W5.6 Two-anthology drill: same test contact in two anthologies, two records, one contact_id.
- W5.7 S9 assembly drill: the trigger exercised from BOTH doors with every guard forced (non-producer refused, unapproved-participant blocking list shown, below-minimum chapter count refused, confirm-name mismatch refused, double-fire no-op), one explicit exclusion, then three synthetic chapters ordered, introduction and matter generated, manuscript compiled, sign-off on the Assembly card, fields pushed.
- W5.8 Gate battery: anthropic guard, prompt-pin guard (incl. zero [UNCHANGED]), font-floor guard, cron inventory, credential gate, silence and secrecy audit, fleet-wide client-identifier grep, JSON-export-absence scan, Skill 53 regression, tone-core sync. Every unit Gate-A scored; below 8.5 loops back autonomously.

## WAVE 6: THE SERIAL MERGE TRAIN (ONE merge-writer agent; strictly serial; nothing else merges anywhere during it)

1. Skill 54 extensions (smallest certified surface) plus content_sha restamp.
2. The orchestrator skill directory (runbook, modules, configs, scripts, fixtures, tests).
3. Department, role, persona, floor wiring.
4. SOPs and doc updates.
5. PRD folder sync at project-prds/anthology-engine/ (scrubbed set).
6. update.sh: REGISTER the new skill directory and correct the skill count.
7. hash-content-manifest.py restamp of _index.json content_sha across every touched file.
8. Version bump to v19.0.0 (locked; Wave 0 confirmed live main below it).
9. ANNOTATED tag v19.0.0 (git tag -a) created BEFORE the merge (a bare tag is rejected).
10. Merge. Then fresh-clone verification from GitHub: version, tag, skill count, content hashes, clean install via the standard updater, and the JSON-export-absence scan against the fresh clone.

The Command Center repo changes (W3.1 to W3.3) merge on THAT repo's own serial train with the same laws (canary-first, single writer, annotated tag, fresh-clone verify), cross-referenced in CHANGE-LOG.md.

## WAVE 7: POST-MERGE CANARY, FREEZE POSTURE, AND HOLD (serial; 3 agents + QC)

- W7.1 Re-run W5.3 to W5.8 from the MERGED repos on the operator box (prove the merged artifact, not the branch).
- W7.2 Record the FREEZE posture (no new participants enter n8n once the engine intake is live); retirement criteria recorded but NOT executed; legacy stays alive and untouched.
- W7.3 Record the HOLD: fleet rollout repo-only until the operator OK. Final operator report: what merged, gate scores, canary evidence, the Skill 53 non-deprecation verdict, the architecture decision surfaced, the onboarding-inputs list, the hold. CHECKLIST.md Part C (all 26) verified item by item; memory and session log synced. DONE only when every Part C item is TRUE and both repos are updated; if a repo is not updated, it is NOT done.

---

## PARALLEL VERSUS SERIAL SUMMARY

PARALLELIZABLE (inside a single wave, branch-only): Waves 1, 2, 4 internals; Wave 0 items after W0.1; Wave 3's three units. MUST SERIALIZE: the wave sequence itself (one wave at a time, never stacked); Wave 0 entry; Wave 5 drills in order on the one canary box; the ENTIRE Wave 6 merge train; Wave 7.
HARD DEPENDENCIES: W0.2 ingestion before W1.3 and W1.12; W0.7 before Wave 3; W1.7 before Wave 3 and W1.15; W1+W2+W3+W4 before W5; W5 fully green before W6; W6 before W7.

AGENT BUDGET: every wave caps at 50 agents including its QC bank; dispatch staggered inside the wave; re-dispatch with resumeFromRunId on any failure or rate limit; the loop never stops until CHECKLIST.md Part C is fully green.
