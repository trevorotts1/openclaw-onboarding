# Approvals and gates (MG-025)

Approvals are enforced in the executable production path, not recorded
as decoration. This document is the contract for the gate layer in
`runtime/src/orchestrator/` (TypeScript) and its Python mirror in
`scripts/check_approvals.py`. Both evaluators implement the same rules
and produce identical revision digests and verdicts; the shared
fixtures under `tests/fixtures/approvals/` are the parity proof
(their approvals were signed by one implementation and are verified
by both, with golden digests pinned in
`tests/evidence/mg025/measurements.json`).

Normative basis: Directive MG-025 and Sections 16.7 (approval trust
and revision hashing), 16.8 (lifecycle and approval order), and 16.9
(stable categories and exit classes).

## Phase states and the three gates

The orchestrator tracks the Section 16.8 states (`orchestrator/phases.ts`):
CREATED, SCHEMA_VALID, INPUTS_READY, DESIGN_APPROVED, SCENES_READY,
PREVIEW_READY, PREVIEW_APPROVED, FINAL_RENDERED, FINAL_QC_PASSED,
PACKAGED, DELIVERED. Three transitions are approval gates:

| Gate | Requires | Admits |
|---|---|---|
| design | trusted design approval for the current design revision | DESIGN_APPROVED |
| render | contracts validation clean, catalog consult clean, design gate passed, trusted preview approval for the current full revision | PREVIEW_APPROVED |
| delivery | production context, trusted preview and delivery approvals current for the full revision, delivery approval naming the final artifact at its actual on-disk hash, passing final-QC record for those exact bytes | FINAL_QC_PASSED (ready to package) |

No render gate depends on QC of output it has not yet created, and no
delivery gate accepts preview QC. A material change returns affected
work to the earliest invalidated phase by construction: the change
moves a revision digest, and every approval bound to the old digest is
stale.

`buildApprovedJob` in `orchestrator/gate.ts` is the trusted
construction path for an `ApprovedMotionJob` (Section 16.7): it runs
the render gate and returns the job carrying the gate-verified preview
permit loaded from the job's own approval records. It is not a type
cast over a caller-supplied record.

## The immutable job revision

A job revision is a deterministic fingerprint over nine components.
Each component digest is the sha256 of canonical UTF-8 JSON (sorted
keys, no whitespace, defined numeric serialization: integers plain,
non-integers as shortest round-trip decimals) over sorted
`{path, sha256}` pairs, where file hashes cover raw bytes. The module
is `orchestrator/revision.ts`; `computeRevisionLock` is pure, and
`writeRevisionLock` persists `revision-lock.json` in the job directory
(the lock is never a component input, so writing it changes nothing).

| Component | Inputs |
|---|---|
| manifest | `manifest.json` bytes (job intent: mode, canvas, duration, policy, context) |
| source | the storyboard file plus every scene spec named by the manifest (the source bundle: copy, props, motion) |
| design | `design.json` bytes (tokens, layouts, type scale) |
| data | every file under `data/` plus any scene `data_path` |
| assets | `assets.json` bytes plus the on-disk bytes of every asset it names |
| fonts | the `font_requirements` records in `assets.json` (id, family alias, weights), canonicalized per requirement |
| timeline | the compiled canonical timeline plus `timeline-sidecar.json` when present (the pair list always contains the sidecar entry, null when absent, so adding a sidecar moves the digest) |
| narration | `narration.json` bytes when present; an explicit empty entry list when absent, so adding narration moves the digest |
| runtime | the runtime identity record: routed engine, its exact probed version, and the runtime-lock content id (for example `lock-314fc289b233ca9e`) |

Two digests are derived (Section 16.7):

- **Design revision**: over the design, assets, and fonts component
  digests. Design approvals bind this digest.
- **Full revision**: over all nine components. Preview and delivery
  approvals bind this digest.

What each acceptance change moves (all proven in
`runtime/tests/run-approvals.ts` and pinned in the evidence record):

| Change | Components moved | Design revision | Approvals staled |
|---|---|---|---|
| headline (scene `copy.headline`) | source | unchanged | preview, delivery |
| image (asset bytes, declared hash updated to match) | assets | changes | design, preview, delivery |
| duration (manifest, timeline, scene, consistently) | manifest, source, timeline | unchanged | preview, delivery |
| font (font requirement family alias) | assets, fonts | changes | design, preview, delivery |
| dataset (one row value) | data | unchanged | preview, delivery |
| narration text | narration | unchanged | preview, delivery |

An asset whose on-disk bytes disagree with the sha256 declared in
`assets.json` is reported as MG_HASH_MISMATCH (exit 9): the assets
record does not describe the asset, independent of any approval.

Excluded from every digest, by construction: approval records and
review receipts, the revision lock itself, output files, timestamps,
progress logs, absolute machine paths. Writing an approval therefore
never changes the revision it approves (the suites assert this).

## Issuer trust: how an approver is recognized

Section 16.7: do not invent a trust boundary. An approval counts only
when all of the following hold (`orchestrator/issuers.ts`,
`orchestrator/gate.ts`):

1. **The record is canonical and bound.** The approval validates
   against the `approval` $def in `contracts-v2.schema.json`, names
   this job and company (anything else is MG_FOREIGN_JOB, exit 9,
   reported ahead of every other class), carries decision `approved`,
   and its `subject_revision` equals the current revision for its
   scope (design approvals bind the design revision; preview and
   delivery bind the full revision). A mismatch is MG_APPROVAL_STALE.
2. **The issuer is recognized under the job's declared policy.** The
   evaluator consults an issuer registry held OUTSIDE the job package:
   `MOTION_ISSUER_REGISTRY` points at a JSON file the trusted workflow
   controls, listing `{actor_id, role, policies}` with role `owner` or
   `authorized_reviewer` for the production policy
   `owner_or_existing_authorized_reviewer`. The built-in default
   registry recognizes exactly one issuer, the fixture test issuer, so
   on an installation with no configured trust source a production
   approval reports MG_APPROVAL_AUTHORITY_UNAVAILABLE rather than
   trusting job JSON. No new authentication service is built here; the
   registry and keyring are configuration the existing trusted
   workflow supplies.
3. **The source event authenticates the record.** The approval's
   `source_event_ref` names a detached event artifact inside the job
   package. The approval must bind that artifact in `artifact_refs`
   with its exact sha256 (a missing binding is MG_SECURITY_VIOLATION;
   a wrong hash is MG_HASH_MISMATCH). The event repeats the approval's
   binding fields (approval id, job, company, scope, decision,
   revision, actor) and the artifact refs the approver approved (the
   approval record carries those same refs plus the event binding
   entry; an event cannot bind its own hash). The event carries an
   HMAC-SHA256 signature over its canonical JSON, keyed with the
   issuer's key from the keyring (`MOTION_APPROVER_KEYS`, also held
   outside the job package). A signature that does not verify is
   MG_SECURITY_VIOLATION.

The forgery property follows from where the key lives: an authoring
agent can write any JSON it likes into a job directory, including a
record claiming `actor_id` of the owner with `authority_status`
`verified`, but without the issuer's key it cannot produce an event
the evaluator accepts. The tests prove both halves: an event re-signed
with an attacker-chosen key fails as MG_SECURITY_VIOLATION, and an
unregistered actor under default trust fails as
MG_APPROVAL_AUTHORITY_UNAVAILABLE. The residual limit is the one
Section 16.7 names: this is front-door discipline around a configured
trusted source, not protection against an actor who already holds the
issuer key or the registry files. Key custody belongs to the trusted
workflow, not to this gate.

The MG-010 fixture pattern is generalized, not replaced: fixture jobs
(the manifest `execution_context` is `fixture`, policy `fixture_only`)
accept exactly one issuer, `fixture-test-issuer`, whose key is a
published test constant. Production jobs reject that issuer outright.

## Diagnostic context

Fixture execution follows the same gates with test-only authority and
its results are labeled `diagnostic: true`. Diagnostic results carry
no production delivery privilege: the delivery gate refuses fixture
jobs outright (MG_APPROVAL_AUTHORITY_UNAVAILABLE), so a fixture render
can never be promoted as client-ready, and a fixture job never reaches
a production DELIVERED state.

The dispatcher's `renderFinal` mirrors this split. For fixture jobs it
keeps the MG-004 contract (an approved delivery-scope record, the test
runner's own diagnostic record) so diagnostic renders proceed exactly
as the earlier suites exercise them. For production jobs it requires
the MG-025 render gate to pass and the presented record to be the
gate-verified preview permit (see the next section). Low-level adapter
calls can always produce diagnostic bytes; production promotion goes
through the delivery gate or it does not happen (Section 16.7).

## The production render permit is the preview approval

Section 16.8 and test T34 fix the order: `render` checks the declared
approval policy and the current PREVIEW approval before the final
render; final QC and the DELIVERY approval occur afterward. The
shipped MG-004 dispatcher check required a delivery-scope record
before `renderFinal`, which conflated the two decisions and, read
literally against 16.8, would demand a delivery decision before the
final bytes exist to QC. MG-025 resolves the tension in favor of the
lifecycle text for production jobs: the production render permit is
the gate-verified preview approval for the current full revision, and
the delivery approval is enforced at the delivery gate, after final
QC. Fixture behavior (the only path the earlier suites exercise) is
unchanged. Consumers that present a delivery-scope record to a
production `renderFinal` are refused with MG_APPROVAL_REQUIRED naming
the permit the gate verified.

## The delivery gate is the promotion check

`evaluateDeliveryGate` (and its throwing form
`assertDeliveryPromotable`) is where delivery is claimed; MG-035 and
MG-036 consumers call it before packaging or handing off. It requires,
for the exact artifact presented:

- a production execution context (fixture is refused, above);
- preview and delivery approvals valid for the current full revision
  through the trusted path;
- the delivery approval naming the artifact's job-relative path with
  the sha256 of the bytes actually on disk (an artifact that changed
  after approval is MG_APPROVAL_STALE; a presented hash that disagrees
  with the disk is MG_HASH_MISMATCH);
- a final-QC record (`{artifact_path, artifact_sha256, verdict}`)
  naming the same path and hash with verdict `pass` (missing is
  MG_INPUT_MISSING; a record naming other bytes or a failing verdict
  is MG_QC_FAILED, exit 6). Preview QC is not delivery evidence.

## Catalog consult wiring (settlement B)

The dispatcher (`adapters/dispatch.ts`, `loadValidatedJob`) and the
render gate consult the MG-018 component registry
(`ComponentRegistry.createDefault().validateSceneProps`) for every
scene, alongside the canonical contracts validation and never instead
of it, before any adapter is resolved or called:

- A scene naming a component the catalog has registered but marked
  unavailable (C01, C02, C03, C10, C11, C12 today) is refused as
  MG_CAPABILITY_UNSUPPORTED (CatalogError, exit 3) when the contracts
  layer's only complaint about the job is its component
  classification. At the render gate the same consult contributes its
  finding alongside the contracts finding.
- A scene naming a component the catalog has never registered is
  MG_UNKNOWN_COMPONENT (exit 2), identical to the contracts layer.
- The C05 path is unchanged: a valid C05 job passes both layers
  exactly as before.

Honest limit, stated plainly: the canonical scene $def is closed on
C05, so any non-C05 scene, including catalog-available C04 and
C06-C09 scenes with well-formed props, still fails canonical job
validation as MG_UNKNOWN_COMPONENT before dispatch. Catalog
availability does not make a component job-dispatchable today; it only
sharpens the refusal category for components the catalog knows are
not yet dispatchable, and it stands ready for the contracts revision
that registers the other scene shapes. The Python evaluator does not
repeat the catalog consult (the catalog is a TypeScript runtime
artifact); it enforces the contracts layer through
`motion_contracts.validate_job`, which classifies the same scenes as
MG_UNKNOWN_COMPONENT.

## The V2 narration source (settlement C)

The frozen canonical contracts carry no narration text field, while
the V1 pipeline's `scripts/tts.py` consumes per-scene `voiceover_text`
from a V1 manifest. The V2 convention, settled at the job-package
layer the orchestrator owns (the canonical schema is not edited):

- A narrating V2 job carries **`narration.json`** at the job root, the
  narration script record: `{schema_version: "1.0", job_id,
  kind: "narration_script", scenes: [{scene_id, text, measured,
  voice_ref}]}`. `measured` is the spoken range in samples at the
  compiled rate of 48000 Hz (`{start_sample, end_sample}`), or null
  before MG-020 measurement has run.
- The record is a revision component (above): editing text or
  measured timing stales preview and delivery approvals.
- Measured ranges flow into the MG-021 compiler as
  `NarrationSegmentInput` values through
  `orchestrator/narration.ts` `toNarrationSegments`, using the
  compiler's own sample/frame helpers; the compiler owns placement
  and fails an overrun as TIMELINE_NARRATION_EXCEEDS_PICTURE. The
  render gate validates the record's structure (job binding, known
  scenes, non-empty text, integer measured ranges) as
  MG_SCHEMA_INVALID findings.
- TTS synthesis keeps consuming the V1 shape on V1 jobs. On V2 jobs
  the record is the text source; `projectToVoiceoverTexts` projects
  it to the per-scene `voiceover_text` shape at the synthesis
  boundary, rather than the V2 manifest growing a field the frozen
  schema forbids.

Contracts-revision candidate, recorded rather than actioned: if a
future contracts revision wants narration inside the canonical
documents, the candidate is a `narration` $def carrying per-scene text
and measured sample ranges, referenced from the manifest. Until then
the job-package record above is the convention, and it joins the
MG-009 planner fields, MG-011 provenance sidecar, MG-015 dataset
extensions, and MG-021 timeline sidecar on the contracts-revision
decision list.

## Evaluator entry points

TypeScript (`runtime/src/orchestrator/`):

- `computeRevisionLock(jobDir, runtime)` / `writeRevisionLock`:
  the fingerprint and the persisted `revision-lock.json`.
- `evaluateDesignGate(jobDir)`, `evaluateRenderGate(jobDir, runtime)`,
  `evaluateDeliveryGate(jobDir, runtime, artifact, qc)`,
  `assertDeliveryPromotable(...)`, `buildApprovedJob(jobDir, runtime)`.
- `loadIssuerTrust(env)`: registry and keyring resolution
  (`MOTION_ISSUER_REGISTRY`, `MOTION_APPROVER_KEYS`).
- `signApprovalEvent(event, key)`: the trusted workflow's import-time
  signing helper.
- The runtime identity argument is `{engine, engineVersion,
  runtimeLockId}`. The dispatcher derives it from the routed engine's
  probed capability record and refuses production finals when no ready
  probe record exists (MG_RUNTIME_UNAVAILABLE).

Python (`scripts/check_approvals.py`): `check <job_dir> --gate
design|render|delivery --runtime runtime.json [--registry ...]
[--keyring ...] [--final-artifact ...] [--qc ...]`, printing one JSON
report in the same shape as the TypeScript GateResult and exiting
with the Section 16.9 class. Unit tests live in
`tests/unit/test_check_approvals.py`.

No `scripts/motion_pipeline.py` exists in the tree (verified at
MG-025 build time): the executable production path is the TypeScript
dispatcher plus the standalone Python gate CLIs, so no parallel
pipeline file was invented. The Python evaluator exists because the
Python consumers (assembly, QC, and the presentation seam) need the
same verdicts without a Node sidecar.

## Exit classes (Section 16.9)

0 pass; 2 contract family (MG_SCHEMA_INVALID, MG_UNKNOWN_COMPONENT,
MG_MODE_MISMATCH, MG_TIMELINE_INVALID); 3 dependency family
(MG_INPUT_MISSING, MG_CAPABILITY_UNSUPPORTED, MG_RUNTIME_UNAVAILABLE);
4 approval family (MG_APPROVAL_REQUIRED, MG_APPROVAL_STALE,
MG_APPROVAL_AUTHORITY_UNAVAILABLE); 6 MG_QC_FAILED; 9 security family
(MG_FOREIGN_JOB, MG_HASH_MISMATCH, MG_SECURITY_VIOLATION). When several
findings exist, all are reported and the first blocking class follows
the Section 16.9 order: security, validation, dependency, authority,
execution, QC, delivery.
