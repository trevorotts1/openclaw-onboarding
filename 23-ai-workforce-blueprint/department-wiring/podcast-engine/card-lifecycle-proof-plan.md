# Card Lifecycle Proof Plan

How a test job lands on the kanban and moves through the full state vocabulary. This
proves CHECKLIST.md Part C item 12 ("a test job appears on the kanban and moves
through the state vocabulary") for the department, persona, and kanban wiring. No em
dashes, no triple-backtick fences.

The kanban does not compute anything. Each checkpoint below is proven by writing the
status through the single writer podcast_state.py and then reading the kanban and the
dashboard, which must show the same value. The observed move is what proves the
wiring; a status the writer accepts but the board does not render is a failure, and
so is a board column with no backing status.

## Preconditions

- The synthetic client is provisioned on the operator box (WAVE-PLAN W5.2): route
  id podcast-intake-<slug>, sessionKey podcast:intake:<slug>, dashboard on loopback
  4010, podcast-engine.db created by podcast_state.py.
- The submission is _test-gated so nothing destructive fires (no real publish, no
  customer message). Move in silence throughout.
- The job_key and submission_fingerprint are computed by the webhook layer; the
  UNIQUE (client_id, submission_fingerprint) constraint guarantees one card per
  submission.

## Checkpoints (each is one observed transition)

1. Intake lands on the bound session. A signed _test submission to the real public
   hooks URL drives sessionKey podcast:intake:<slug>. The director-of-podcast agent
   picks up the TaskFlow. podcast_state.py create writes status received. PROVE: one
   card appears in the Received column; the ledger and podcast_jobs agree; the
   submitter identity renders in the client view.

2. received to researching. The engine enters the Research Assistant stage (Step 3).
   PROVE: the card moves to the Researching column; owner shown is director-of-podcast.

3. researching to writing. Steps 2 and 4 to 8 run under podcast-host. PROVE: the card
   moves to Writing; the writing column owner is podcast-host (the drafting persona).

4. writing to in_qc. Step 9 runs under qc-specialist-podcast. PROVE: the card moves to
   Quality review; the owner is qc-specialist-podcast and is a different persona from
   the drafting persona (independence rule observed on the board, not just asserted).

5. QC revision loop. Force a Tier 1 failure so in_qc returns to writing (revision).
   PROVE: the card moves back to Writing and the QC xN badge increments. A third
   failure moves the card to the Needs attention column (failed) and the founder is
   alerted once through alert-dedup.py. This exercises the qc_loop transition and the
   3-strike cap without conflating the episode gate with the build gate.

6. in_qc to generating_art to producing_audio. On a passing QC, Steps 10 and 11 run
   under audio-post-producer, supported by podcast-editor and audio-mastering-specialist
   at Step 11. PROVE: the card moves through Creating artwork then Producing audio.

7. producing_audio to publishing to enrolling. Steps 12 to 17. PROVE: the card moves
   through Publishing then Finalizing; audio-post-producer owns media QC in publishing
   and director-of-podcast owns enrolling.

8. enrolling to complete. Step 18 delivers; completed_at is set. PROVE: the card lands
   in the Live column and the nine-segment progress meter is full.

9. Hold and resume overlay. On a separate run, force an insufficient-credits error.
   PROVE: any non-terminal card moves to the On hold column (queued_credit_out,
   queue_state held) and, on restored funds, returns to its resume_stage column.

10. Age-out overlay. Simulate the 60-day cap on a held card. PROVE: the card renders
    the Expired badge on the Needs attention column (queue_state aged_out) and the
    payload is purged.

11. Idempotency on the board. Redeliver the identical webhook. PROVE: no second card
    appears (the UNIQUE constraint no-ops) and delivery_count increments on the
    existing card. Change one answer and redeliver. PROVE: a new card appears with a
    new job_key.

## Pass condition

Every status the writer emits is rendered by exactly one board column or off-board
column or overlay, and every board column shows the persona owner from wiring.json.
The board mutates nothing. When all checkpoints are observed on the operator box, the
department, persona, and kanban wiring is proven end to end. This canary run is owned
by WAVE-PLAN W5.4; this document is the checklist that run follows.
