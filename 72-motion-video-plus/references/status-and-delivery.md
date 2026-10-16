# Status, recovery, and delivery evidence (MG-046)

One task identity from intake through delivery. A motion job does
not invent a second task when it renders, fails, resumes, or
delivers: the identity is derived once from the job manifest, the
structured status ledger lives in the job directory, and the
existing Skill 47 surfaces (the Command Center board transport in
`cc_board.py` and the phase attestation manifest written by
`executive_producer.py`) carry it from there. This document is the
integration contract for that model (integration target I01, with
V01 and V02 consumed as they stand; V03, the render dependency
provisioner, needs no change because MG-046 reuses identifiers
only and provisions nothing new).

## Task identity

The tracker (`runtime/src/status/`) derives identity from the
validated manifest:

- A standalone job is its own task: `taskId` and `boardJobId` are
  the manifest `job_id`.
- An insert (a manifest with a `parent`, the MG-037 VSL handoff
  shape) reports under its parent: `taskId` is the parent's
  `task_id`, `boardJobId` is the parent's `job_id`, and the board
  stage slug is `motion-<job_id>`, a stage on the parent's existing
  campaign. An insert never creates a campaign of its own and
  never writes a campaign marker; the parent job keeps its own
  identity, its own completion gates, and its own receipt.

Reopening a job directory whose status document names the same
`job_id` resumes the same task: the document is kept, the event
sequence continues from the events file, and the reopen is itself
recorded as a resumed phase transition. An unreadable or foreign
document starts a fresh ledger rather than corrupting the old one.

## Three axes, kept separate

- **Production status**: `RENDERED`, `QC_PASSED`, `APPROVED`,
  `DELIVERED`, advanced only on evidence (below). Before any
  evidence exists the status is unset; the phase axis carries
  `CREATED`.
- **Phase**: the MG-025 phase vocabulary (`CREATED` through
  `DELIVERED` in `runtime/src/orchestrator/phases.ts`).
- **Release and build status**: a separate axis. The status
  document carries `releaseStatus`, starting unset, and no
  production code path in this layer writes it. The delivery
  receipt carries it as its own nullable field, pinned apart from
  `production_status`, so a release event can never be mistaken
  for a production state or the reverse.

**Production approval is not code-review approval.** The only
approvals this layer records are production approvals verified by
the MG-025 gates (design, render, delivery), stored with kind
`production_approval`, the gate, the scope, the approval id, and
the gate's authority basis. The tracker is the ledger, never the
authority: it records a gate result only when the gate passed and
named a verified approval id. The delivery receipt schema
structurally excludes any other approval kind.

## The ledger

Inside the job directory, mirroring Skill 47 conventions:

- `working/checkpoints/motion-status.json`: the current status
  document (identity, axes, artifacts, approvals, QC record,
  recovery context, missing mandatory names, board sync state).
  Written atomically (temporary file plus rename).
- `working/checkpoints/motion-status-events.jsonl`: the
  append-only event ledger. Event kinds: `phase_transition`,
  `progress`, `render_receipt`, `review_verdict`,
  `approval_event`, `recovery_point`, `artifact_location`,
  `failure`, `delivery_blocked`, `delivered`. Each event carries
  the task identity, the phase, the production status, and a
  monotonically increasing sequence number.
- `working/checkpoints/delivery-receipt.json`: written only when
  the job reaches `DELIVERED`.

## Advancement is evidence-only

- A render receipt (adapter evidence with measured artifact
  hashes) sets `RENDERED` and phase `FINAL_RENDERED`.
- A passing final-QC verdict over the rendered artifact sets
  `QC_PASSED` and phase `FINAL_QC_PASSED`. A failing verdict is
  recorded and advances nothing; a pass recorded before any render
  advances nothing.
- A passed delivery gate while `QC_PASSED` records the production
  delivery approval and sets `APPROVED`.
- `deliver()` sets `DELIVERED` (below).

## Delivery

`deliver()` evaluates, in order:

1. **The MG-025 delivery gate** (production context only): the
   trusted delivery approval current for the full job revision,
   binding the final artifact at its on-disk hash, plus the
   passing final-QC record for those exact bytes. A pass is
   recorded as the delivery approval event.
2. **Readiness by measurement**: every mandatory artifact kind in
   `manifest.delivery.required` must be recorded and must measure
   on disk (present, size and full sha256 matching the record; a
   missing or changed file counts as missing, by kind), the final
   QC must be a pass, a delivery approval must be recorded, and
   the context must be production.

Anything missing blocks delivery BY NAME: a `delivery_blocked`
event and a `StatusError` (`MG_DELIVERY_INCOMPLETE`, exit class
6) whose `missing` list names each absent artifact kind plus, as
applicable, `final_qc`, `delivery_approval`, `production_context`,
and `delivery_gate:<category>` when the gate itself blocks.
Fixture-context jobs are diagnostic and can never be delivered as
production: `production_context` always names that block.

On success the receipt is built from measured facts only and
validated against `references/delivery-receipt-schema.json`, this
layer's own schema (the layer-owned pattern of MG-032 through
MG-037; the canonical `contracts-v2.schema.json` is not edited).
Its `missing_mandatory` is pinned empty, and every approval on it
is a production approval.

## Board transport and attestation (V01, V02)

The transport of record is the Python bridge
`47-movie-producer/scripts/motion_status.py`, which consumes the
ledger the runtime writes:

- **Attestation (V01)**: status events are appended to
  `working/checkpoints/video_process_manifest.json` in
  `attest_phase`'s exact record shape, with owning role
  `skill72-motion`. A bridge state file
  (`working/checkpoints/motion-bridge-state.json`) keeps a cursor
  of attested events, so a retry never duplicates an attestation.
  The bridge never sets `finalized`; V-CONTROL remains the
  parent's own attestation.

  Attestations land under the manifest's `phase_attestations`
  key, the same key `attest_phase` appends to, so the parent's
  own readers (executive_producer's `_attestations`, feeding
  `_attested_phase_ids` and the phase precondition checks) see
  the bridge's records as first-class attestations; the bridge
  keeps no parallel ledger under any other key. Records an
  earlier bridge version appended under a `phases` key are
  left untouched as history: the bridge-state cursor counts
  attested status events regardless of the key they were
  written under, so on the first sync after this alignment
  those events count as already attested and are never
  duplicated under `phase_attestations`.
- **Board (V02)**: `cc_board` is used as it stands, fail-soft
  throughout (an unset `MISSION_CONTROL_URL` is a clean no-op;
  a board failure is recorded in the sync report and never fails
  the production). Status maps to stage states as follows:
  `DELIVERED` to `done`, `RENDERED` / `QC_PASSED` / `APPROVED` to
  `review`, any phase beyond `CREATED` to `in_progress`. All
  movement walks the board's legal transition path; there is no
  `in_progress` to `done` edge, and none is taken. A stage already
  recorded as synced to the desired state is not patched again.
- **Done is gated at the board too**: before any `done` move, the
  bridge re-checks the ledger (production status `DELIVERED`,
  `missingMandatory` empty) and the filed delivery receipt
  (present, `missing_mandatory` empty, an `mp4` artifact
  recorded). Blockers are returned BY NAME and the stage goes no
  further than `review`. On a confirmed `done`, the render
  receipt is stamped opportunistically through
  `cc_board.stamp_receipt`.
- **Idempotence**: a standalone job ensures its campaign once
  (the `cc-board.created` marker plus the server's own `job_id`
  idempotence); an insert creates nothing. The fail-then-resume
  cycle in `47-movie-producer/scripts/test_motion_status.py`
  proves the cycle against a board double with legal-transition
  enforcement: one campaign across a mid-sync transport failure,
  no duplicated attestation, no illegal jump, and `done` reached
  only through `review` with every mandatory artifact present.

The runtime side also exposes an optional `BoardTransport` hook on
the tracker, invoked after each persisted event and wrapped
fail-soft (a throwing transport is recorded in
`doc.board.lastSync` and never propagates). The Python bridge is
the transport of record; the hook exists for in-process
integrations that already speak to the board.

## Parent return

A motion component returns to its parent presentation or VSL job
instead of becoming an unrelated full production task. The status
layer consumes the MG-037 bridge contract as it stands: the
insert's manifest `parent` (job id, task id, handoff path, slot,
narration cue) is the identity source, the bridge's
`motion_inserts` ledger in the parent's `working/job-manifest.json`
remains the parent's record of the insert, and the parent's
assembly and QC gates are unchanged. Layered on top, the insert's
own status ledger reports the parent's task identity, so the board
shows one task with a motion stage, not two tasks.

## Recovery

Failure preserves the same task and its resume context:

- The dispatcher records a `failure` event and a `recovery_point`
  on any render failure, carrying the cache work directory, the
  cache session's job key, and the failed scene ids when the
  cached path was in use. Production status does not regress.
- Settlement A wiring (MG-027): `MotionDispatcher.
  renderFinalCached` opens a cache session per job, supplies
  per-scene renderers backed by the routed adapter, and assembles
  outputs only from `artifactPathFor`. A job interrupted mid-render
  resumes from the session state with finished scenes reused
  byte-identical. The contract is in
  `references/caching-and-resume.md`; the production-path proof
  (SIGKILL mid-render, resume in a fresh process) is in
  `runtime/tests/run-status.ts`.
- Settlement B wiring (MG-040): `routeJob` consults
  `selectExportRoute` when the caller supplies an export
  toolchain probe, so alpha-profile jobs are routed by the export
  layer's probed qualification instead of the shipped matrix's
  empty alpha claims, and refuse by name
  (`MG_CAPABILITY_UNSUPPORTED`) when no route qualifies. The
  shipped capability matrix is never edited. The contract is in
  `references/export-profiles.md`.

## Honest limits

- The production adapters are single-scene today, so the cached
  dispatch path decomposes a multi-scene job into staged
  scene-scoped packages (full package copies excluding the
  working tree, filtered to one scene). The decomposition is the
  orchestrator's, per the adapters' own doctrine that multi-scene
  program assembly is never faked inside an adapter.
- Cache key inputs hash the declared font requirement record from
  the design document; resolved font bytes remain an adapter
  concern.
- Fixture-context jobs can never reach `DELIVERED`. That is the
  MG-025 promotion rule restated at this layer, not a gap.
