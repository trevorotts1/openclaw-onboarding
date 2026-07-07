# Card Lifecycle Proof Plan

How a synthetic participant's card lands on the seeded Anthology department board
and moves through the full stage_cursor vocabulary, and how the companion
Assembly card moves through the assembly_state vocabulary. This proves CHECKLIST.md
Part C item 20's board clause ("a test card observed moving through the board
vocabulary") for the department, floor, and self-invocation wiring. No em dashes,
no triple-backtick fences.

The board does not compute anything. Each checkpoint below is proven by writing
the state through the single writer `anthology_state.py` and then reading the
board through `mc_board.py`'s read-only mirror, which must show the same value.
The observed move is what proves the wiring; a stage_cursor or assembly_state the
writer accepts but the board does not render is a failure, and so is a board
column with no backing state.

## Preconditions

- The Anthology department is already SEEDED on the operator box's Command Center
  (Skill 32 add-department.sh, department_slug `anthology`), per W2.6 STEP 3.5 and
  exercised at W3.1. This proof plan does not re-seed it; it only drives cards
  through the vocabulary that seeding already made possible.
- Every event in this plan runs through the ONE sanctioned entry point,
  `anthology-engine-entry.sh` (see `HOW-TO-USE-THE-ANTHOLOGY-DEPARTMENT.md` and
  `wiring.json`'s `self_invocation` block), never a stage script called directly.
- The submission is a synthetic, _test-gated fixture so nothing destructive fires
  (no real Convert and Flow field write beyond the sandboxed run, no email to a
  real address). Move in silence throughout.
- `mc_board.py` is FAIL-SOFT: a dark board never blocks a checkpoint below from
  advancing the ledger; the checkpoint is proven again once the board reconciles.

## Checkpoints (each is one observed transition)

1. Intake lands. `bash anthology-engine-entry.sh --stage s0 --payload FILE` runs
   the deterministic router. PROVE: `anthology_state.py` writes `stage_cursor`
   `s0_intake`; `mc_board.py` creates ONE participant card in the `backlog`
   column (STATUS_BY_CURSOR maps `s0_intake` to `backlog`); the ledger and the
   board mirror agree.

2. Avatar through title, in_progress and review pairs. For each of
   `s1_avatar`/`s1_gate`, `s2_tone`/`s2_gate`, `s3_title`/`s3_gate`: firing the
   stage runner through `anthology-engine-entry.sh --stage sN` advances
   `stage_cursor`; PROVE the card sits in `in_progress` for the authoring cursor
   and moves to `review` for the paired gate cursor (a produced deliverable
   awaiting a producer or participant decision). The gate decision itself is one
   of the "gate events" this wiring documents: it reaches `gate_engine.py`'s
   shared both-door record-approval call through the SAME entry point.

3. Blurb and outline, the two-gate stage. `s4_blurb_outline` sits in
   `in_progress`; both `s4_gate_producer` and `s4_gate_participant` sit in
   `review`. PROVE both gates are observed in sequence (producer gate, then
   participant gate) before the cursor advances to `s5_chapter`.

4. Chapter and the rewrite loop. `s5_chapter` sits in `in_progress`; `s5_gate`
   sits in `review` (the chapter-approval queue). Force a "request rewrite with
   notes" decision. PROVE the cursor moves to `s6_rewrite` (`in_progress`) and
   back to `s5_gate` (`review`) on the rewrite's own gate re-entry, up to the
   rewrite budget of 2; a third rewrite request is an illegal transition and
   must be refused, not silently accepted.

5. Cover and delivery. `s7_cover` and `s8_deliver` both sit in `in_progress`.
   PROVE both cursors are observed and that no card lands in `review` again
   until the participant's track reaches its terminal state below (S8 has no
   participant-facing gate of its own).

6. Waiting on assembly. `s9_wait_assembly` sits in `review` (chapter frozen and
   delivered; the independent QC scorer owns the promotion to done from here,
   never this wiring). PROVE the card is observed in `review` and stays there
   until the Assembly track (below) reaches `signed_off`.

7. Terminal participant states, off the happy path. PROVE `held` and
   `exception` both render as `blocked` on the board (STATUS_BY_CURSOR maps
   both to `blocked`), and that `approved` and `delivered` both render as
   `review` (parked; QC-owned promotion to done, the engine never self-promotes
   a card to done).

8. Assembly readiness. On a separate Assembly card for the same anthology_id,
   force every participant to a settled state (approved, delivered, or
   explicitly excluded). PROVE the Assembly card's `assembly_state` moves from
   `not_ready` (`backlog`) to `armed` (`review`), the readiness report attached,
   without any card anywhere emitting `done`.

9. The assembly trigger, fired through the one entry point. The producer fires
   ready-to-assemble via `bash anthology-engine-entry.sh --stage s9
   --anthology-id ID`. PROVE `assembly_state` moves `armed` to
   `ready_confirmed` (`in_progress`); a second fire on an already-fired anthology
   is an observed no-op (ASSEMBLY_FIRED covers `ready_confirmed`,
   `proposed`, `adjusted`, `compiled`, `signed_off`), never a duplicate manuscript
   run.

10. Order and compile. PROVE `proposed` and `adjusted` both render
    `in_progress` (order curation and any producer adjustment), and `compiled`
    renders `review` (manuscript compiled, awaiting the producer's sign-off).

11. Final sign-off. The producer's sign-off, fired through the same entry point
    (`--stage s9`), moves `assembly_state` to `signed_off`. PROVE the Assembly
    card renders `review` (parked; the engine never self-promotes to done) and
    that `anthology_state.py` recorded `status` `delivered` alongside it.

12. Board unreachable, fail-soft. Repeat any one checkpoint above with the board
    endpoint made unreachable. PROVE `mc_board.py` exits 0 (fail-soft, never
    blocks the pipeline), the ledger still advances normally, and the card
    reconciles to the correct column once the board comes back (the daily tick
    or the next sync call).

## Pass condition

Every `stage_cursor` and `assembly_state` value the writer emits is rendered by
exactly one board column, and no column is ever driven to `done` by this engine
(review to done is the independent QC scorer's decision alone, at or above 8.5).
Every event above was fired through `anthology-engine-entry.sh`, never a direct
stage-script call. When all twelve checkpoints are observed on the operator box,
the department, floor, and self-invocation wiring is proven end to end for the
board's part of CHECKLIST.md Part C item 20. This canary run is owned by
WAVE-PLAN Wave 5; this document is the checklist that run follows.
