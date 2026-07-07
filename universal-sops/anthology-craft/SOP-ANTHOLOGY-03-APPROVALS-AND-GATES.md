# SOP-ANTHOLOGY-03: ANTHOLOGY APPROVALS AND GATES (both doors, one endpoint)

**Cluster:** Anthology-Craft Rules (`universal-sops/anthology-craft/`)
**Master authority:** SPEC.md Section 11 (the Command Center integration contract) and Section 11.3 (the participant token page); QC-PROTOCOL-AND-MATRIX.md (Gate B instruments); PRD Section 12 (the two QC gates)
**Owning role:** anthology-approvals-steward owns gate hygiene, the nudge cadence, the readiness report, and the trigger-and-sign-off flow. Producer decisions are the producer's own; participant decisions are the participant's own; this role never substitutes a decision.
**Enforcement pointer (binding):** `59-anthology-engine/scripts/qc-strike-gate.py` plus the board contract (SPEC Section 11.2), together the enforcement pointer for this SOP. `qc-strike-gate.py` owns the two counters (participant rewrite budget 2, internal QC attempt cap 3) and is READ-ONLY for the ledger; every mutation persists through `anthology_state.py set-counter` and `hold`. The board contract is enforced by `mc_board.py` (fail-soft board client, HMAC plus Bearer, never self-promotes review to done) and `gate_engine.py` (the single both-door gate endpoint and the scoped token mint and verify).
**Stage:** cross-cutting, every gate from S1 through S9.

---

## 0. WHY THIS SOP EXISTS

Every gate in this engine is a decision, not a formality, and every decision must be recorded exactly once, from exactly one of two doors, through exactly one writer. This SOP is the human-readable face of the machinery that makes that true: `gate_engine.py` resolves which gate is open and mints the tokens; `qc-strike-gate.py` counts rewrites and internal attempts and decides retry versus hold; `mc_board.py` projects the ledger onto the Anthology board; `anthology_state.py record-approval` is the sole place a decision is written. A standard operating procedure without a gate is a suggestion, so every rule below names its script and its exit code.

## 1. BOTH DOORS, ONE ENDPOINT

Every gate decision reaches the engine through exactly one of two doors and lands on the identical endpoint: door `board` is the producer's Command Center card view (own session, own-producer auth, recorded as door `dashboard`); door `token` is the participant token page reached by the emailed nudge link (requires a valid scoped token or PIN, recorded as door `nudge_link`). Both doors resolve to the SAME call, `gate_engine.py decide`, which shells the SAME sole-writer subcommand, `anthology_state.py record-approval`. No gate decision is ever written twice or from two code paths.

`gate_engine.py` mints a NEW single-purpose participant token or PIN per open gate: HMAC-SHA256 over participant_key, gate id, and expiry, keyed by the per-producer secret under label `ANTHOLOGY_GATE_TOKEN_SECRET`. Tokens are single-gate-scoped, expire on gate closure, and a foreign, expired, or replayed token is refused (AF-AE-TOKEN-REFUSED). The participant token page serves ONLY that participant's open gate: title and subtitle selection at S3, outline approval at S4, chapter Approve-as-is or Request-rewrite-with-notes at S5 and S6.

## 2. THE GATE VOCABULARY

Approval gates: s1_producer, s2_producer, s3_selection, s4_producer, s4_participant, s5_participant, s9_ready, s9_producer. Actors: producer, participant. Decisions: approve, request_rewrite, escalate, hold, exclude, ready_to_assemble. Doors: dashboard, nudge_link. The chapter gate (s5_participant) exposes EXACTLY TWO actions to the participant: Approve as-is, or Request rewrite with notes; notes feed `chapter_updates` verbatim.

Two gate-specific guards fire inside `record-approval` itself, never in the UI: the s3_selection decision stamps the TITLE LOCK (byte-exact title and subtitle), which is one-way, a later change requires a producer exception; and the s5_participant approve decision FREEZES the current chapter artifact (sha256-stable), the exact artifact S9 later compiles from.

## 3. THE STRIKE GATE: TWO COUNTERS, NEVER CONFUSED

Counter 1, the PARTICIPANT REWRITE BUDGET (2, with gate re-entry). A participant may Request-rewrite at the S5 chapter gate at most twice; each rewrite re-enters the SAME S5 gate. At budget exhaustion the gate offers exactly Approve-as-is or escalate-to-producer, never a silent third rewrite; a third rewrite is an illegal transition the writer itself refuses. `qc-strike-gate.py` is the decision authority that tells the gate which two actions remain and how much budget is left; it is READ-ONLY for this counter, the increment is written exactly once, by `anthology_state.py record-approval` on s5_participant/request_rewrite.

Counter 2, INTERNAL QC ATTEMPTS (3 per deliverable, then hold plus one deduped founder alert). Each machine-internal deliverable (a chapter draft, a rewrite draft) gets at most three targeted-revision attempts; a failed prover or rubric pass counts one attempt. After the third failed attempt the participant is HELD (reason strike_out) and the founder is notified EXACTLY ONCE through `alert-dedup.py`, carrying the failing checks and a reference to the best draft. Standards are NEVER relaxed to clear a strike. All attempts for one deliverable share ONE token budget (owned by `anthology-cost-ledger.py`, not this gate); a failed and re-run deliverable does not get a fresh budget.

Every counter mutation and every hold persists THROUGH `anthology_state.py` (`set-counter`, `hold`); this gate never writes the ledger directly. The founder alert path is always `alert-dedup.py`, never bypassed.

## 4. GATE B, THE CONTENT GATE (never the 8.5 build gate)

Before any gate opens, the produced deliverable runs the full Gate B battery: `qc-tier1-anthology.py`, twelve deterministic zero-model-cost checks (word band honesty measured not self-reported, title lock byte-exact, story placement, zero truncation, zero em dash, no code-fence or system-prompt leakage, the 14-point PDF floor, identity integrity, no intake contamination, no fabricated links, Convert and Flow naming only, a clean run ledger with no Anthropic identifier); then `judge_harness.py` on the JUDGE tier, the three semantic checks (fabrication nuance, voice fidelity, outline fidelity) plus the ten-dimension rubric, each dimension scored 8 or higher with NO averaging, always on a tier and persona distinct from whichever drafted (AF-AE-JUDGE-INDEPENDENCE; a harness that would let a model grade its own homework refuses instead). Gate B is NEVER Gate A, the fleet 10-category build/merge rubric at 8.5; a 9.0 build unit says nothing about a chapter, and a perfect chapter says nothing about merge readiness. The two gates are never conflated, substituted, or averaged into each other.

## 5. THE BOARD CONTRACT (the producer experience)

Every participant is exactly ONE task card on the Anthology board, created and advanced by `mc_board.py` posting to `POST /api/tasks/ingest` with HMAC plus Bearer auth, reusing Skill 32's EXISTING auth pair, never a new one. FAIL-SOFT by construction: board unreachability, an auth rejection, or a schema hiccup never blocks the pipeline; the ledger remains the truth and the card reconciles on the daily tick; every board outcome, even unreachable, returns exit 0 so a stage runner is never held on the board.

Card status mirrors `Participants.stage_cursor`. Active authoring cursors sit the card in `in_progress`; a produced deliverable awaiting a producer or participant decision sits the card in `review`, the review column IS the chapter-approval queue. `held` and `exception` escalate the card to `blocked`. ONLY the independent QC scorer at or above 8.5 promotes a card from review to done; `mc_board.py`'s own status map carries NO `done`, and its guard refuses to ever emit one. The engine never self-promotes a card. One dedicated Assembly card per anthology carries the readiness report, the ready-to-assemble trigger, the order-adjustment surface, and the final manuscript sign-off; full detail lives in SOP-ANTHOLOGY-04.

## 6. NUDGES AND STUCK CADENCE

The only client-facing surfaces this SOP touches are the three sanctioned templates in `config/nudge-templates/` (gate-open, stuck-renudge, completion); the recipient is ALWAYS resolved from the ledger row for the given contact_id, never a literal. A gate stuck past its configured age fires ONE deduped automatic re-nudge, never a storm; `nudge_send.py` is the sole sender and it never bypasses the OpenClaw gateway.

## 7. DEFINITION OF DONE FOR A GATE

A gate is closed only when: the decision arrived through one of the two doors and was recorded through `gate_engine.py decide` and `anthology_state.py record-approval`; every per-gate guard that applies (title lock, rewrite budget, chapter freeze) fired correctly; the Gate B battery passed before the gate opened in the first place; and the board card reflects the resulting stage_cursor. Anything less is not gated, it is guessed.
