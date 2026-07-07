# SOP-ANTHOLOGY-04: ANTHOLOGY ASSEMBLY (S9, the producer-fired manuscript compile)

**Cluster:** Anthology-Craft Rules (`universal-sops/anthology-craft/`)
**Master authority:** PRD Section 3.11 (the producer trigger) and the S9 stage description; SPEC.md Section 11.2 (the Assembly card) and the assembly_state machine in `anthology_state.py`
**Owning role:** anthology-producer-orchestrator drives S9, speaking the Anthology Editor voice (prompts ae-01 through ae-04), ALWAYS subordinate to the producer's own supplied inputs. anthology-approvals-steward owns the readiness report and the nudge that tells the producer the anthology is ready.
**Enforcement pointer (binding):** the S9 checks, meaning the six PRD Section 3.11 trigger guards plus the assembly-scope Gate B battery, both enforced by `59-anthology-engine/scripts/anthology_state.py`'s assembly_state machine and `59-anthology-engine/scripts/stage_s9_assembly_logic.py`; the module never writes state directly, every mutation shells the sole writer. `qc-tier1-anthology.py --mode assembly` runs the manuscript-scope additions to Gate B.
**Stage:** S9, fired at most once per anthology per collection cycle, after every contributor has reached S8.

---

## 0. WHY THIS SOP EXISTS

An anthology is many contributors writing one chapter each, curated by an editor; S9 is the stage that makes this an anthology ENGINE rather than a batch of independent chapters. Assembly never starts on a mere all-approved condition; it is fired ONLY by the producer's own explicit trigger, and every guard below is enforced by the writer, never by the UI, so a card click or a malformed request can never assemble an anthology the producer did not actually ask to assemble.

## 1. THE ASSEMBLY STATE MACHINE

The anthology-scope `assembly_state` moves: not_ready to armed; armed to ready_confirmed; ready_confirmed to proposed, adjusted, or compiled; proposed to adjusted or compiled; adjusted to compiled; compiled to signed_off. A producer-initiated reopen is legal from armed, ready_confirmed, proposed, adjusted, or compiled back to not_ready, and voids an in-progress assembly. States counted as "the trigger already fired" (a double-fire is an acknowledged no-op): ready_confirmed, proposed, adjusted, compiled, signed_off.

`assembly-advance` (the subcommand the assembly module calls) owns exactly two targets: compiled (its own staging plus sha256 re-proof plus a readiness re-check) and not_ready (the producer-initiated reopen). Every other assembly_state is reached ONLY through its own guarded channel: armed through auto-arm or the trigger fire; ready_confirmed through the trigger fire alone (own-producer auth plus confirm-name plus the readiness checks); proposed and adjusted through `assembly-set-order` (a validated permutation of the staged chapter set); signed_off through the producer's own sign-off. No second, unguarded door exists into any of these states.

The anthology arms automatically the moment its last contributor reaches `approved` (`anthology_state.py advance-stage` calls `_maybe_arm` on that transition), moving not_ready to armed and queuing the readiness nudge to the producer.

## 2. THE SIX TRIGGER GUARDS (PRD Section 3.11, all enforced by the writer)

The producer fires the ready-to-assemble trigger from the Assembly card on the Anthology board OR the readiness nudge deep link, both doors, ONE endpoint, which shells `anthology_state.py record-approval --gate s9_ready`. The writer enforces, in order:

1. Own-producer authentication (the box owner's Command Center session or a producer-scoped token); a non-producer caller is refused (exit 5).
2. Every participant is at `approved` OR carries an explicit `exclude` approvals row; an unapproved, non-excluded participant blocks the trigger and the block names them.
3. At least `min_chapters` frozen approved chapters exist (the per-anthology configurable floor, MIN_CHAPTERS_FLOOR = 2; a value below the floor is refused at anthology setup, exit 5).
4. Typed anthology-name confirmation, echoed as `--confirm-name`; a mismatch exits 5, nothing changes.
5. One-way: re-firing an already-fired trigger is an acknowledged no-op, never a second assembly job.
6. Assembly NEVER starts on a mere all-approved condition; the explicit producer fire is the only door in.

On success the anthology moves to ready_to_assemble (or the assembly_state to ready_confirmed) and the assembly job spawns.

## 3. WHAT RUNS BETWEEN THE TWO PRODUCER DECISIONS

Two distinct producer decisions bracket S9: the ready-to-assemble trigger (gate s9_ready, Section 2 above) opens it, and the final manuscript sign-off (gate s9_producer) closes it. Between them, `stage_s9_assembly_logic.py` drives the machinery in order:

1. ORDER CURATION (prompt ae-01): a strong opener and closer, long-short alternation, tone pacing, subtheme grouping; producer adjustments are recorded and re-enter through `assembly-set-order` while assembly_state is proposed or adjusted.
2. EDITOR'S INTRODUCTION (prompt ae-02) in the producer's OWN voice, built from producer-supplied inputs ONLY, never invented.
3. FRONT AND BACK MATTER (prompt ae-04).
4. CONTRIBUTOR BIOS (prompt ae-03) from ledger identities, never guessed.
5. COMPILE from FROZEN approved chapters, sha256 byte-identical to the version frozen at the S5 approve gate; whole-manuscript on the LONGCTX tier when the client configured a key, else chunked on HEAVY-WRITER.
6. ASSEMBLY-SCOPE GATE B: `qc-tier1-anthology.py --mode assembly` proves every approved chapter present exactly once and byte-identical to its frozen version, chapter order matches the curated order, the editor introduction references only real contributors, contributor bios match ledger identities, front and back matter are complete, and the whole is one continuous 14-point-floor PDF.
7. HAND TO `stage_s8_deliver.py` for the manuscript Doc plus PDF, delivered the same way every other artifact is delivered (Section 4 of SOP-ANTHOLOGY-01).

The persona speaking every S9 prompt is the Anthology Editor voice, ALWAYS subordinate to the producer's supplied inputs; prompts never name a model, only a tier.

## 4. THE FINAL SIGN-OFF (gate s9_producer)

The producer signs off on the Assembly card once the compiled manuscript is reviewed; this shells `record-approval --gate s9_producer`, moving the participant-scope `approved` rows to `delivered` and closing the anthology (status delivered). This is the ONLY door that reaches `signed_off`; own-producer auth applies here exactly as it does at the trigger.

## 5. FAILURE HANDLING AT S9

A prover, Gate B, order-integrity, or frozen-chapter-integrity failure holds S9 for a targeted revision, never a silent pass (exit 2, an internal QC attempt under the same strike-gate discipline as any other deliverable, SOP-ANTHOLOGY-03). A missing collaborator, an unresolved credit hold, or a lost callback holds the anthology at its current assembly_state (exit 3) rather than failing outward; the daily smoke test's age tick resumes it once the dependency clears (SOP-ANTHOLOGY-05). An unresolved prompt slot is AF-AE-SLOT-UNRESOLVED, refused before any content ships (exit 5).

## 6. DEFINITION OF DONE FOR ASSEMBLY

S9 is done only when: the trigger fired through the writer with all six guards satisfied and recorded; the manuscript compiled from frozen approved chapters, sha256-proven; assembly-scope Gate B passed in full; the producer's own sign-off closed the anthology through gate s9_producer; and the manuscript Doc and PDF delivered and read back exactly as every other artifact does. A manuscript assembled without the trigger, or signed off by anyone but the producer, is not done, it is a defect.
