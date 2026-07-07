# QC PROTOCOL AND MATRIX, ANTHOLOGY ENGINE
### The two gates, spelled out separately, plus the QC-gated push law and the stage-by-stage check matrix
### Version 3.0, Fable, 2026-07-06 (revision 3, aligned to the revision-3 spine: producer experience relocated INSIDE the client's own Command Center as a seeded Anthology department/board; participant token page rows added; home tiles corrected to Anthology, Podcast, and Interview; prompt source of record moved to the Downloads JSON exports with the zero-[UNCHANGED] proof and the JSON-export-absence scan; the QC-gated push and the incremental persistence law spelled out in full; v19.0.0 repo target).

Doctrine on this protocol: move in silence (operator-verbose, never client-facing); no Anthropic in any runtime file including any judge tier; credentials by label and location only, never by value; the platform is Convert and Flow in every client surface; config writes as the node user, never root; ONLY sub-agents build; zero client personally identifiable information in this document or the repo; zero em dashes and zero code fences in produced deliverables.

THE CARDINAL RULE: there are TWO quality control gates in this project and they are never conflated, never substituted, and never averaged into each other. GATE A decides whether BUILD WORK merges. GATE B decides whether a PIECE OF CONTENT (a per-participant deliverable or the assembled anthology) ships. A build unit scoring 9.0 says nothing about a chapter, and a perfect chapter says nothing about merge readiness.

---

## 1. WHO SCORES, AND WHEN (the execution model this protocol rides on)

- ONLY sub-agents do the work; the orchestrator delegates everything and never builds or scores in its own loop.
- Up to 50 agents per wave, ONE wave at a time, dispatch staggered inside the wave; waves are never stacked. Heavy parallelism runs on BOTH sides of every wave: execution agents in front, an equally parallel bank of QC agents behind them.
- Every Gate A score is issued by an INDEPENDENT QC agent, never by the unit's author as the final word. Every Gate B semantic judgment runs on a judge tier distinct from the writer tier, and the QC persona is never the drafting persona.
- A sub-agent's claim of done is a HYPOTHESIS until the wave's independent verification confirms it.
- On any failure or rate limit, the agent is re-dispatched with state passed forward (resumeFromRunId); the loop never stops until CHECKLIST.md Part C is fully green.

---

## 2. THE QC-GATED PUSH AND THE INCREMENTAL PERSISTENCE LAW (binding on every build unit)

Every feature or slice moves through exactly this loop, no exceptions and no batching of un-QCed work:

1. BUILD: an execution sub-agent builds the unit on a branch.
2. QC: an independent QC agent scores it on the fleet 10-category rubric (Gate A).
3. BELOW 8.5: the work goes back, gets FIXED, and is RE-QCed, autonomously, as many rounds as it takes. Nobody ships a 7.9, and nobody asks the founder to bless one either.
4. AT OR ABOVE 8.5: the unit is COMMITTED AND PUSHED to the repo immediately (canary-first on the operator box; strictly serial single merge-writer for every merge; annotated tags only).
5. PERSISTENCE, THE MOMENT THE PUSH LANDS: the SAME agent that passed the gate updates CHECKLIST.md (tick the item), updates TODO.md (mark the task done), appends the SESSION-LOG.md row (timestamp, agent, wave/task, evidence paths, the gate score), and appends the CHANGE-LOG.md row (the commit). This is a single atomic ritual with the push, never deferred, never delegated to a later cleanup pass.

WHY THE LAW EXISTS (anti session-limit loss): completed-and-pushed work is NEVER lost to a session limit. On any cold resume, the unchecked CHECKLIST.md and TODO.md items ARE the remaining work; nothing gets rebuilt, nothing gets re-litigated. Work that passed QC but was not pushed and not ticked does not count as done. If the repo is not updated, it is NOT done.

---

## 3. GATE A: THE BUILD/MERGE GATE (fleet standard, binding on /goal execution)

- Instrument: the fleet 10-category QC rubric (the binding OpenClaw QC protocol).
- Threshold: 8.5. Below 8.5 the unit is fixed and re-QCed per Section 2; at or above 8.5 it pushes and merges. The rubric decides quality; nobody asks the founder for a green light the rubric already grants.
- Scope: every merged unit of the build: the orchestrator skill, each Skill 54 extension, each guardrail script, the intake router and webhook layer, the ledger and state layer, the delivery adapters, the producer board experience (the seeded Anthology department, the board contract wiring, the Assembly card), the home-screen tiles code edit, the participant token page, each SOP, the department/role/persona/floor wiring, and the docs.
- Administered per feature/slice by the wave's independent QC bank; logged per unit in SESSION-LOG.md with the score.

MECHANICAL MERGE GATES RIDING WITH GATE A (each one binary, each one blocks):
1. guard-no-anthropic-runtime.py: zero Anthropic identifiers across the full engine file set INCLUDING every Command Center edit (department config, the tiles edit, the token route).
2. guard-prompt-pins.py: every baked prompt matches its sha256 pin, zero truncation, ZERO remaining [UNCHANGED] placeholders (the formatter's ten restored from the CSV HTML Book record), and zero runtime prompt-base references.
3. JSON-EXPORT-ABSENCE SCAN: none of the nine Downloads JSON exports, in whole, in part, or in fixture form, and no key-shaped content from them, exists anywhere in either repo; re-run against the fresh clone.
4. guard-cron-inventory.py: exactly the one daily tick; no heartbeat entry ever; churn leaves zero recurring jobs.
5. CONTENT-HASH GATE: _index.json content_sha restamped via hash-content-manifest.py for every touched file.
6. G1 TAG GATE: the ANNOTATED tag v19.0.0 (git tag -a) exists BEFORE the merge; a bare tag is rejected; the repo version target is v19.0.0, locked, NOT v18.
7. FLEET-WIDE REPO GREP: zero client identifiers and zero client personally identifiable information in either repo; the n8n design doc stays operator-side.
8. update.sh CHECK: the new skill directory REGISTERED and the skill count corrected (the change every new-skill merge makes).
9. verify_tone_core_sync.py: the shared tone core untouched and byte-identical across 53, 54, and the orchestrator.
10. SKILL 53 REGRESSION: Skill 53 untouched and passing its own checks.

WHERE THE RIDERS RUN: at every QC-gated push as applicable, in full as the Wave 5 gate battery (W5.8), and AGAIN on the Wave 6 serial merge train, followed by fresh-clone verification from GitHub (version, tag, skill count, content hashes, clean install via the standard updater, and the JSON-export-absence scan on the fresh clone). Command Center repo changes ride THAT repo's own serial train under the same laws, cross-referenced in CHANGE-LOG.md.

---

## 4. GATE B: THE CONTENT GATE (binding at runtime, shipped inside the skill)

Gate B runs on every deliverable at two scopes: PER PIECE (avatar, tone, titles, blurb, outline, chapter, rewrite, cover prompt) and PER ANTHOLOGY (the S9 assembled manuscript). Same instruments, scope-specific checks. S5 and S6 run the full battery BEFORE their gate opens; S1 to S4 and S7 to S8 run their subset per the matrix; S9 runs assembly mode.

### Instrument 1, Tier 1 hard-fail checks (binary; any single failure means NOT deliverable)

Deterministic checks, executed by qc-tier1-anthology.py at zero model cost:
1. WORD BAND HONESTY: the chapter (and any rewrite) is 2,000 to 3,500 MEASURED stripped words; the tone document is at least 3,000 measured words; self-reported counts are ignored and misreporting is an absolute failure.
2. TITLE LOCK: the locked title and subtitle appear byte-exact in the outline, the chapter, every rewrite, and the cover prompt.
3. STORY PLACEMENT: every personal story supplied by the participant appears placed in the outline and the chapter.
4. ZERO TRUNCATION: the generating prompt matched its sha256 pin, and the output ends on a complete sentence with closing structure present.
5. ZERO EM DASH characters anywhere in the deliverable.
6. NO MARKDOWN ARTIFACTS OR CODE FENCES in prose deliverables; no stage labels, no system-prompt leakage.
7. PDF FONT FLOOR: no rendered font below 14 point in any designed PDF (guard-font-floor.py over the RENDERED file, never the template).
8. IDENTITY INTEGRITY: the deliverable belongs to the correct contact_id and anthology_id; no cross-participant or cross-anthology content bleed; participant name and details match the ledger.
9. NO INTAKE CONTAMINATION: hidden field values, form mechanics, emails, and phone numbers never appear in the deliverable.
10. NO FABRICATION OF THE PARTICIPANT: the chapter never invents biography, quotes, or stories the participant did not supply; avatar research claims are sourced from the web-search pass, never invented.
11. NAMING: client-visible surfaces say Convert and Flow; no internal tool names, no model names, no plumbing (the client-clean serializer enforces this on every card field, token page response, and nudge).
12. RUN LEDGER CLEANLINESS: zero Anthropic model identifiers in the run ledger; the model used is recorded honestly, substitutions named.

Semantic checks (13 fabrication nuance, 14 voice fidelity to the tone document, 15 outline fidelity of the chapter) run on a judge tier (Minimax V3 or Gemini 3.5 Flash), NEVER on the writer model.

ASSEMBLY-SCOPE ADDITIONS (S9 manuscript only): every approved chapter present exactly once and byte-identical (sha256) to its frozen approved version; chapter order matches the curated order; the editor's introduction references only real contributors and is built from producer-supplied inputs only; contributor bios match ledger identities; front and back matter complete; one continuous 14-point-floor PDF.

### Instrument 2, Tier 2 rubric (scored only after Tier 1 fully passes)

Ten dimensions, each 8 or higher, NO averaging: 1 Voice Fidelity to the blended tone, 2 Avatar Resonance (speaks to the stated ideal avatar), 3 Goal Alignment (serves the stated primary goal), 4 Opening Power, 5 Closing Power, 6 Narrative Craft and story integration, 7 Fidelity to the Participant's ideas, 8 Clarity and Readability at the 14-point designed format, 9 Chapter-in-Anthology Fit (theme and pacing), 10 Editorial Polish. The judge tier is distinct from the writer tier; the QC persona is never the drafting persona.

### Instrument 3, the strike cap (two counters, never confused)

- PARTICIPANT REWRITE BUDGET: 2. Each Request-rewrite with notes consumes one; the notes feed chapter_updates verbatim; the rewrite RE-ENTERS the chapter gate; at budget exhaustion the gate offers Approve as-is or escalate to the producer, never a silent third rewrite (an illegal transition the writer refuses).
- INTERNAL QC ATTEMPTS: 3 per deliverable. Targeted revision only (failing checks and dimensions; the avatar and research package is frozen and reused). At three failed attempts: HOLD the participant, notify the founder ONCE through alert-dedup.py with the failing checks and the best draft. Standards are never relaxed to clear a strike.
- Cost bounds: all attempts share one per-deliverable token budget enforced by anthology-cost-ledger.py; the ceiling blocks the call, never silently degrades the check.

### The board surfacing rule (how Gate B meets the Command Center, without conflating the gates)

The producer sees Gate B through the client's own Command Center: the seeded Anthology department board's review column IS the chapter-approval queue; the existing board contract routes producer-facing output to review, and ONLY the independent QC scorer at or above 8.5 promotes a card from review to done. For anthology cards, that promotion is the Gate B verdict surfacing on the board; the engine NEVER self-promotes a card. This shared surface changes nothing about the cardinal rule: Gate A and Gate B remain distinct instruments with distinct scopes, and neither substitutes for the other.

---

## 5. THE MATRIX: EVERY STAGE AND BUILD DELIVERABLE MAPPED TO ITS CHECKS

### 5.1 Runtime matrix (per participant, per anthology)

| Stage / deliverable | Checks applied | Proving instrument |
|---|---|---|
| S0 intake | Hidden-field presence, tenant check, contact_id keying, dedup no-op, exceptions capture, sub-2-second acknowledge | Deterministic router plus fixture tests; T1 to T9 |
| S1 avatar | Pinned prompts, search-tool detection or flagged degradation, Tier 1 checks 4 to 12, producer gate on the board card (review column) | guard-prompt-pins.py, qc-tier1-anthology.py, gate log |
| S2 tone | Tone core byte-identity, 3,000 measured words, ledger-verified recipient email, producer gate (review column) | verify_tone_core_sync.py, measured prover, ledger email check |
| S3 title | Titles doc pair, participant selection captured ON THE TOKEN PAGE, TITLE LOCK recorded byte-exact and one-way | Title-lock prover, token-page gate log |
| S4 blurb and outline | Story placement, title lock carry, producer board gate then participant outline approval on the token page, no re-upload path exists | Placement prover, gate log, static route check |
| S5 chapter | Full Tier 1, full rubric, BEFORE the gate opens; two-action gate (Approve as-is or Request rewrite with notes) served on the token page; card lands in review | qc-tier1-anthology.py, judge tier, qc-strike-gate.py |
| S6 rewrite | Band held, notes applied via chapter_updates, gate re-entry, budget 2 | qc-strike-gate.py counters |
| S7 cover | Pinned cover prompt, Kie.ai GPT-image-2 PORTRAIT 1024x1536 via the W0.6-verified text-to-image endpoint (never the 16:9 presentation recipe), callback completion, PNG in Drive, no hardcoded key | Static key scan, callback relay log |
| S8 deliver | Doc plus PDF pairs, font floor, media upload reachability, exact field keys keyed by contact_id, read-back byte-for-byte, per-gate pipeline-stage update, certificate; card to review, done only via the QC scorer | guard-font-floor.py, upload probe, field read-back, board contract log |
| S9 assembly | Producer ready-to-assemble trigger fired from EITHER door (Assembly card or readiness nudge deep link, one endpoint, s9_ready approvals row) with all guards held (own producer, approved-or-excluded roster, minimum frozen chapter count, typed confirm-name, one-way); assembly-scope Tier 1 additions; rubric on the manuscript; producer final sign-off (gate s9_producer) | anthology_state.py transition matrix and gate log, qc-tier1-anthology.py assembly mode |
| Participant token page | Single-gate scope; foreign, expired, and replayed tokens refused; both doors hit the same endpoint and writer subcommand; client-clean serializer on every response | gate_engine.py mint-and-verify (label ANTHOLOGY_GATE_TOKEN_SECRET), refusal drill log |
| Every stage | Transition legality, cost metering, credit-out hold, alert dedup, zero Anthropic at call time | anthology_state.py, anthology-cost-ledger.py, alert-dedup.py, guard-no-anthropic-runtime deny patterns |
| Daily per client | Funded reachability at or under one cent, hold-queue age check | anthology-smoke-test.py self-metered |

### 5.2 Build matrix (per /goal deliverable; every row also obeys Section 2's push-and-persist law)

| Build deliverable (wave) | Gate A rubric | Additional mechanical gates and proofs |
|---|---|---|
| Prompt ingestion from the JSON exports (W0.2) | 8.5 | Four largest prompts plus Primary Goal extraction pulled VERBATIM from the Downloads exports; the formatter's ten [UNCHANGED] placeholders restored from the CSV HTML Book record; word band normalized to 2,000 to 3,500; Make.com variables mapped to canonical fields; sha256 pins stamped; zero truncation and zero remaining [UNCHANGED] proven; ingestion evidence in SESSION-LOG.md |
| Secret hygiene (W0.3) | n/a (mechanical) | Both exposed credentials rotated BY LABEL (values never printed); the payload-carried routing key re-homed as an ENV credential by label; the nine exports confirmed outside every repo working tree; the JSON-export-absence scan added to the merge gate |
| Orchestrator skill runbook and configs (W1.1) | 8.5 | Content gate exercised on the golden fixture; prompt-pin scan |
| Skill 54 extensions (W1.2 to W1.4) | 8.5 | All existing AF-AW provers green; tone-core sync green; Skill 53 regression green |
| Intake router and webhook layer (W1.5, W1.6) | 8.5 | Fixture tests; T1 to T9 executed on the canary including the real public URL test |
| Ledger and state layer (W1.7, W1.19, W1.20) | 8.5 | Kill-and-resume drill; transition-matrix violation refused; mirror lockstep check; direct-base-write repo scan (the writer is the sole path) |
| Registry and pipeline auto-provisioning (W1.8) | 8.5 | Standard Anthology pipeline auto-created in the client's own Convert and Flow account with the client's own token; stage map bound at provisioning, nothing hardcoded |
| Model routing and search ladder (W1.9, W1.10) | 8.5 | Forced-failure drill walks the whole chain to the durable hold plus gateway alert; Anthropic deny patterns refuse at call time; degradation flagged |
| Delivery adapters (Drive, PDF, Convert and Flow, Kie.ai) (W1.11 to W1.14) | 8.5 | Font-floor proof on rendered output; read-back proof; reachability probes incl. the existing Drive root; static key scan; portrait endpoint proof from W0.6 |
| Gate and nudge engine plus strike gate (W1.15, W1.16) | 8.5 | Both-door single-endpoint proof; token mint/verify with foreign, expired, and replayed refusals; budget counters trip correctly |
| Content QC harness (W1.17) | 8.5 | Forced Tier 1 failure blocks; forced rubric failure blocks; strike cap trips and alerts deduped; judge tier verified distinct from writer tier |
| S9 assembly module (W1.18) | 8.5 | Every PRD 3.11 guard force-tested (non-producer refused, blocking list shown, below-minimum refused, confirm-name mismatch refused, double-fire no-op); frozen-chapter byte-identity |
| Guardrail suite (Wave 2) | 8.5 | Each script's failure modes forced and observed; exit codes match the SPEC 3.4 inventory; a shipped script missing from that table fails the gate |
| Anthology department seeding and board contract (W3.1, Command Center repo serial train) | 8.5 | Department seeded via add-department.sh / POST /api/departments create:true; cards ingest via mc_board.py to POST /api/tasks/ingest (HMAC plus Bearer, fail-soft proven: board unreachability never blocks the pipeline); one card per participant mirroring stage_cursor; review column = approval queue; ONLY the QC scorer promotes review to done; the Assembly card carries trigger and sign-off; the Skill 53 never-seeded books-department defect documented and NOT repeated |
| Home-screen tiles (W3.2, Command Center repo serial train) | 8.5 | Anthology, Podcast, and Interview tiles added to the hardcoded array in src/app/page.tsx matching the existing tile shape; the Anthology tile deep-links to the Anthology department board; nothing Anthropic, nothing client-identifying |
| Participant token page (W3.3, Command Center repo serial train) | 8.5 | Route registered in the middleware.ts bypass list (the /api/health mechanism); token/PIN minted by gate_engine.py under the label ANTHOLOGY_GATE_TOKEN_SECRET; serves ONLY the participant's open gate (S3, S4, S5/S6); refusal drills pass; client-clean serializer on every response |
| Department, role, persona, floor wiring (Wave 4) | 8.5 | Seeded Anthology department registered in the fleet floor files (books/publishing floor grouping on the fleet side); floor check pass; board card observed moving; persona binding proof per the PRD Section 13 table; master-agent routing dispatches anthology events to the anthology orchestrator role ONLY |
| SOP set and doc updates (Wave 4) | 8.5 | Six SOPs each with an enforcement pointer present; revocation content appended to the fleet runbook, never a competing doc; cross-references resolve |
| Canary drills (Wave 5) | 8.5 per unit | W5.3 to W5.8 observed on the operator box: golden fixture S0 to S8 from BOTH doors, force-failure battery, two-anthology drill, S9 drill, full gate battery; below 8.5 loops back autonomously |
| Repo mechanics (Wave 6) | n/a (mechanical) | update.sh registration plus corrected count, content_sha restamp, annotated tag v19.0.0 BEFORE merge, version bump to v19.0.0, strictly serial single-writer merge, fresh-clone verify, fleet-wide grep, JSON-export-absence scan on the fresh clone |
| Post-merge canary and hold (Wave 7) | n/a | W5.3 to W5.8 re-run from the MERGED repos; freeze posture recorded; fleet rollout HELD at repo-only until the operator OK, the hold recorded in the session log |
| Whole build | n/a | CHECKLIST.md Part C, all 26 items, independently verified on the canary; if a repo is not updated, it is NOT done |
