# CWE-023 intake and brief revisions

Guided intake, immutable brief revisions, freeze, preference storage,
and amendment queueing for the Council of Wise Elders (directive
Sections 9, 10, 11). This module sits on three accepted foundations
and never goes around them: brief revisions persist through the
CWE-006 scoped store, route choices resolve through the CWE-008
catalog semantics, and authorized existing business facts arrive only
through the CWE-022 retrieval boundary (the service receives them at
`begin` and checks each fact's scope before it can enter a brief).

## The flow

1. `begin` opens a draft. Supplied known facts whose scope does not
   match the intake are excluded silently; the exclusion count is the
   only trace they leave (Section 9.4: no disclosure). Facts already
   held are never re-asked (T013).
2. The client answers one question at a time (T015) in a fixed order:
   decision, options, success, constraints, facts, unknowns,
   assumptions, stakeholders, mode and panel, route, preference.
   Explicit unknowns are valid answers where the question allows
   them; material questions cannot be skipped, optional ones can.
   Every mutation requires the caller's expected intake revision; a
   stale writer gets a typed conflict, never a silent overwrite.
3. Every brief-affecting answer composes and saves the next immutable
   draft brief revision with its canonical content hash. Revisions
   are never edited. Scaffold or unconfirmed material composes into
   the brief's unknowns, never its facts (T014).
4. `reviewSummary` shows what the client sees before start: the brief
   preview, the panel with its required critical responsibilities,
   the pinned route, the evidence manifest, and what is missing.
5. `freeze` writes the session and the frozen brief revision into the
   canonical CWE-006 store and records the freeze: brief hash,
   evidence manifest hash, route snapshot, and panel assessment.
   After freeze, content edits refuse with `INTAKE_FROZEN`.

## Boundaries that hold here

- **Preference separation (Section 11.1).** The preference value
  lives only in its own `client_preference_private` record. The brief
  carries only the opaque `private_preference_ref`; the actual
  preference never appears in any brief revision, the freeze record,
  or an assembled context (CWE-022 omits the reference from Round 1;
  this module owns the storage side).
- **Panel honesty (Section 10).** Required critical responsibilities
  are computed from the decision's own structured signals before
  start. A selected or quick panel missing a responsibility keeps
  that assessment `not_assessed`, which downstream blocks GO-style
  endorsement where the assessment is necessary. The system
  recommends the responsible seat; it never changes the client's
  panel. Quick mode's Round 3 skip prerequisites and the
  `not_run_by_quick_mode_policy` ratification status are recorded
  verbatim for CWE-025, which owns the skip decision itself.
- **Route pinning (Sections 10, 13.1).** The chosen route (or the
  configured default, inherited) is pinned as a snapshot with its
  identity level and the canonical hash of the catalog entry. A later
  catalog change is reported as drift; the snapshot never moves.
- **Amendments (Section 9).** New factual input during a round is
  queued as a proposed amendment against the frozen revision. It is
  never applied to the frozen brief, so no seat ever sees half-new
  inputs. Application means a new revision in a child session, which
  is CWE-050 composition work, not this unit.

## Persistence split

Canonical brief revisions live in the CWE-006 store via
`RepositoryIntakeBriefStore`. Intake working records (drafts, draft
revisions, the private preference, freeze records, amendments) go
through the `IntakeWorkingStore` port: `MemoryIntakeWorkingStore`
for deterministic tests and `FileIntakeWorkingStore` for the
standalone composition. The split exists because the canonical store
creates a session only with its complete frozen spec; draft
revisions are therefore working records until freeze writes them
canonically. The managed Command Center draft service binds the same
port at CWE-050.

## What this unit does not do

- It does not run the council (CWE-024 executor), decide the quick
  mode Round 3 skip (CWE-025), or score anything (CWE-026).
- It does not apply amendments or create rerun child sessions
  (CWE-050).
- It does not expose HTTP routes (CWE-029) or UI (CWE-033).
