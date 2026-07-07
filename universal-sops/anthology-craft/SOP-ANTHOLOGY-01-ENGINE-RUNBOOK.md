# SOP-ANTHOLOGY-01: ANTHOLOGY ENGINE RUNBOOK (the S0 to S9 per-participant procedure)

**Cluster:** Anthology-Craft Rules (`universal-sops/anthology-craft/`)
**Master authority:** `59-anthology-engine/SKILL.md` (the four layers and the canonical S0 to S9 pipeline table) plus the PRD Section 13 SOP plan plus SPEC.md Section 7 (the data model) and Section 7.3 (the legal-transition matrix)
**Owning role:** anthology-producer-orchestrator owns the run end to end: the ledger, the exceptions queue, escalations, and the S9 assembly machinery. anthology-approvals-steward owns gate hygiene, nudge cadence, the readiness report, and the trigger-and-sign-off flow. QC independence rule: the content QC pass never runs on the persona or model tier that drafted.
**Enforcement pointer (binding):** `59-anthology-engine/scripts/anthology_state.py` is the SOLE ledger writer and the owner of the legal-transition matrix; this is the anthology_state.py transition matrix referenced throughout this runbook. Every participant stage change and every anthology assembly-state change is recorded through this writer and no other; an illegal transition raises `LedgerError` and exits 2 before a single byte is written, an unknown producer/anthology/participant/exception key exits 3, a base-unreachable write commits the mirror and queues the base op (exits 4, never lost), and a validation or confirm-name mismatch exits 5. A stage without a recorded, legal transition through this one file is not done.
**Stage:** S0 once per participant intake, then S1 through S8 per participant, then S9 once per anthology.

---

## 0. WHY THIS SOP EXISTS, AND THE ONE LAW

A participant's journey through an anthology is a durable state machine, not a single conversation. The one law: every state change passes through `anthology_state.py`. The Anthology board, the token page, the exceptions queue, and the cost ledger all READ that one state; nothing recomputes it. A six-month pause costs nothing; a crash mid-stage loses nothing because every mutation is idempotent and a killed-and-replayed event is an acknowledged no-op.

Two writing rules bind every byte this engine produces and are Tier 1 hard-fail checks in `qc-tier1-anthology.py` (checks 5 and 6): zero em dash characters anywhere in a deliverable, and no triple-backtick or code-fence markers of any kind in a produced document, JSON, or run ledger.

## 1. TWO STORES, ONE OPERATION

The engine keeps ONE state system in two reconciled layers that `anthology_state.py` bridges in lockstep: the AUTHORITATIVE Airtable base (the "Anthology Engine State" base, referenced by base id under label `ANTHOLOGY_STATE_BASE_ID`) and a local SQLite MIRROR (WAL mode, under the engine state directory, owned by the node user). The writer writes THROUGH to both in one logical operation; THE BASE WINS ON CONFLICT. A network blip never blocks a gate action because the mirror commit is atomic and the base op only follows a committed mirror, queued on failure (exit 4, "mirror-queued"). When no base is configured (an unprovisioned box or a unit test) the writer runs MIRROR-ONLY and exits 0 with one operator note.

## 2. STATE VOCABULARY

Producers carry `status`: active or revoked. Anthologies carry `status`: setup, open, writing, ready_to_assemble, assembling, delivered, archived; plus `assembly_state`: not_ready, armed, ready_confirmed, proposed, adjusted, compiled, signed_off. Participants carry `stage_cursor`, the exact vocabulary: s0_intake, s1_avatar, s1_gate, s2_tone, s2_gate, s3_title, s3_gate, s4_blurb_outline, s4_gate_producer, s4_gate_participant, s5_chapter, s5_gate, s6_rewrite, s7_cover, s8_deliver, s9_wait_assembly, approved, delivered, held, exception. A participant at `approved` or `delivered` counts as done and frozen, awaiting assembly.

## 3. THE LEGAL TRANSITION MATRIX (exactly as the writer enforces it)

`anthology_state.py` consults ONE table for every stage change; anything not present is illegal and refused with exit 2, changing nothing.

Machine-driven edges (a stage runner calls advance-stage): s0_intake to s1_avatar; s1_avatar to s1_gate; s2_tone to s2_gate; s3_title to s3_gate; s4_blurb_outline to s4_gate_producer; s5_chapter to s5_gate; s6_rewrite to s5_gate (a rewrite always re-enters the gate); s7_cover to s8_deliver; s8_deliver to s9_wait_assembly; s9_wait_assembly to approved; approved to delivered (at S9 manuscript delivery, gate s9_producer).

Gate-decision edges (record-approval performs these atomically with the approvals audit row, never advance-stage): s1_gate to s2_tone on s1_producer approve; s2_gate to s3_title on s2_producer approve; s3_gate to s4_blurb_outline on s3_selection approve (the title lock stamps here); s4_gate_producer to s4_gate_participant on s4_producer approve; s4_gate_participant to s5_chapter on s4_participant approve; s5_gate to s7_cover on s5_participant approve (the chapter freezes here); s5_gate to s6_rewrite on s5_participant request_rewrite (the rewrite budget enforces here).

`advance-stage` (the machine-driven channel) REFUSES every gate-decision edge, so a stage runner can never step past a producer or participant gate without the approvals row and its per-gate guards (title lock, rewrite budget, the s5 chapter freeze) firing. There is deliberately NO edge FROM `held` in the matrix; a held participant returns to its exact recorded cursor only through `resume`, never through `advance`.

The anthology-scope assembly machine moves not_ready to armed, armed to ready_confirmed, ready_confirmed to proposed or adjusted or compiled, proposed to adjusted or compiled, adjusted to compiled, compiled to signed_off; a producer-initiated reopen from any in-progress state back to not_ready voids an in-progress assembly. Full detail lives in SOP-ANTHOLOGY-04 (Assembly).

Exit codes for every subcommand (SPEC Section 3.4 row 1, identical across the file): 0 verified success including an idempotent replay no-op; 1 unexpected error; 2 illegal transition, nothing changed; 3 unknown key; 4 base unreachable, mirror committed and the base op queued; 5 validation or confirm-name mismatch, nothing changed.

## 4. THE CANONICAL S0 TO S9 PIPELINE

| Stage | What happens | Gate |
|---|---|---|
| S0 intake and routing | create or advance the participant keyed by contact_id plus anthology_id; provision the Drive path; card the participant onto the Anthology board; an unroutable submission lands in the exceptions queue with the raw payload and a typed reason | none, deterministic |
| S1 avatar | the Skill 52 handoff, Questions 1 to 30 then 31 and 32 with the auto-detected web search tool, then Rewrite, then Primary Goal extraction; Avatar Doc plus PDF | producer, board review column |
| S2 tone | the shared tone core 04 to 08 byte-identical; Write Tone Style 1 to 4 and Blended Tone; 3,000 measured words; Tone Doc plus PDF | producer |
| S3 title | Suggested Titles; the participant picks title and subtitle on the token page; TITLE LOCK stamped byte-exact, one-way | participant selection |
| S4 blurb and outline | Book Blurb then single-chapter Create Outline placing every personal story; Docs plus PDFs | producer, then participant outline approval |
| S5 chapter | one complete chapter, 2,000 to 3,500 measured stripped words, title locked, every story placed; the full Gate B battery runs BEFORE the gate opens | participant: Approve as-is OR Request rewrite with notes |
| S6 chapter rewrite | optional, budget 2; notes become chapter_updates verbatim; the Thornfield persona rewrites inside the band; re-enters the S5 gate | re-enters S5 |
| S7 cover image | the cover prompt generator, then Kie.ai GPT-image-2 PORTRAIT 1024x1536 via Skills 07 and 46; PNG to Drive | none |
| S8 package and deliver | Google Doc plus 14-point-floor PDF; Convert and Flow media upload; exact-key field writes by contact_id read back byte-for-byte; control fields; per-gate pipeline-stage update; signed process certificate; card to review | card to review, the QC scorer owns review to done |
| S9 anthology assembly | fired ONLY by the producer ready-to-assemble trigger; order curation, editor's introduction in the producer's voice, front and back matter, contributor bios; compile from FROZEN approved chapters byte-identical; full manuscript Doc plus PDF; producer sign-off closes it | s9_ready then s9_producer |

The per-stage thin runners are `scripts/stage_s0_intake.py` through `scripts/stage_s9_assembly.py`; each composes the pinned prompts, calls Layer 1 (Skill 54, the authoring core) or the router, runs its provers, records artifacts through `anthology_state.py`, and opens its gate. The engine never re-implements a Skill 54 phase; Layer 1 is invoked as a local subprocess through `54-anthology-writer/anthology-entry.sh --run-dir RUN_DIR`, and the engine itself runs only through its own sanctioned entry, `59-anthology-engine/anthology-engine-entry.sh --stage sN`.

## 5. FAILURE HANDLING (every failure has a typed handler; nothing is silently dropped)

Held reasons carried on a participant row: credit_out (a model-chain provider ran out of credit), callback_lost (a Kie.ai cover callback lost after the bounded re-poll), strike_out (three failed internal QC attempts). `hold_queue.py` reads the mirror read-only and shells `anthology_state.py hold` and `resume`; it never writes state directly. Once daily the smoke test (SOP-ANTHOLOGY-05) probes funded-reachability and calls the age tick, which resumes every clearable hold to its EXACT recorded pre-hold cursor; credit_out clears when any model-chain provider is funded, callback_lost clears when Kie.ai is reachable, and strike_out NEVER auto-resumes (a content strike-out is a human decision the operator clears explicitly). The rewrite budget (2) and the internal QC attempt cap (3) are `qc-strike-gate.py`'s policy; full detail lives in SOP-ANTHOLOGY-03 (Approvals and Gates).

## 6. TWO HARD BOUNDARIES

Layer 2 (the router, the ledger, the gates) is the ONLY layer that touches state. Layer 1 (Skill 54) performs no network I/O beyond its own model calls and returns artifacts plus its run ledger and prover verdicts; its certification model (hash gate, nonce, fail-closed provers) is preserved untouched. Layer 3 delivery adapters are stateless functions whose every external write is followed by a read-back in the same job. Layer 4 (the Command Center board and the token page) holds NO base credential; its only write path is shelling `anthology_state.py`.

Silence: this engine emits zero client-facing messages except the three sanctioned nudge templates in `config/nudge-templates/`, and the recipient is ALWAYS resolved from the ledger row, never a literal. Operator and founder surfaces are rich; client surfaces are silent.

## 7. RUNTIME MODEL ROUTING (no Anthropic ever ships in runtime)

The HEAVY-WRITER tier resolves GLM 5.2 on Ollama Cloud (provider id ollama-cloud, baseUrl slotting not apiKey, thinking high, temperature 0.3) first, then OpenRouter GLM 5.2, then Gemini 3.5 Flash, then a durable HOLD plus exactly ONE deduped founder Telegram alert through the OpenClaw gateway, never bypassed. The LIGHT tier resolves Minimax V3. The JUDGE tier always resolves to a DIFFERENT resolution than whichever tier drafted (`judge_harness.py` enforces this and refuses to let a model grade its own homework). The LONGCTX tier (DeepSeek V4 Pro or Kimi 2.6, roughly 1M context) is used at S9 assembly only when the client configured a key; otherwise S9 chunks on HEAVY-WRITER. No Anthropic model id, provider, package, key, or host ever ships in a runtime file; `guard-no-anthropic-runtime.py` enforces this at the merge gate over every shipped file including every Command Center edit.

## 8. DEFINITION OF DONE

A participant run is deliverable through S8 only when every Gate B check passes for every produced artifact (SOP-ANTHOLOGY-03), the field read-backs verify byte-for-byte, and the participant's stage_cursor reaches `approved` through legal transitions recorded by `anthology_state.py`. An anthology is done only when S9 fires through the producer trigger, the manuscript compiles from frozen approved chapters, assembly-scope Gate B passes, and the producer's sign-off closes it. Anything less is not delivered.
