# Renderer Routing: Skill 72 Motion Graphics V2

This file is the routing authority for Skill 72 V2. It decides which
production adapter renders a job, and what happens when the preferred engine
cannot do what the job requires. The executable half of this contract lives
in `runtime/src/adapters/` (`routing.ts`, `capabilities.ts`, `dispatch.ts`);
this document and that code state the same rules, and the adapter contract
tests in `runtime/tests/run-adapters.ts` hold them to it.

Skill 72 V2 renders through two production adapters, Hyperframes and
Remotion, provisioned by the shared rendering runtime. The legacy V1
deterministic stack exists only as an explicit compatibility path. Which
adapter a job uses is decided here. What each adapter can do on a given
machine is recorded in `references/renderer-capabilities.json`.

## The adapter contract

Both production engines expose the same typed interface (Directive
Section 5.5): `probeRuntime`, `validate`, `renderStill`, `renderPreview`,
`renderFinal`, `inspectMotion`, and `cancel`. Adapters receive only jobs
that have passed the V2 contracts validation layer, and every result they
return is structured evidence that names the engine and the exact runtime
(engine version and runtime-lock identity) that produced it. A result that
cannot name its runtime is not a receipt.

Frame ranges are half-open, `[startFrame, endFrameExclusive)`, everywhere
inside this layer. Engine APIs that count frames inclusively are adapted
inside the engine adapters, never by callers.

One orchestration dispatcher (`MotionDispatcher`) sits between callers and
adapters. For every render operation it validates the job, routes it,
checks capabilities, resolves the owning adapter, and invokes it under a
timeout and cancellation contract. Callers do not invoke adapters directly.

## Routing table

Routing is per scene, driven by what the scene needs. The delivery mode
(PowerPoint, desktop VSL, mobile VSL, standalone) never decides the engine
by itself: a PowerPoint chart routes to Remotion, and a PowerPoint image
reveal routes to Hyperframes.

| Primary scene requirement | Default engine | Override behavior |
|---|---|---|
| Editorial imagery, product footage or UI, spatial reveals, parallax | Hyperframes | Honor an explicit supported Remotion selection |
| Data-driven charts, repeated data variants, parameterized infographics | Remotion | Hyperframes is valid when its implemented component meets the same contract |
| Substantial React-based scene already exists | Remotion | Do not convert just to standardize aesthetics |
| Existing Hyperframes composition | Hyperframes | Port only for a documented requirement |
| 3D explanatory composition | Engine with the required installed, qualified integration | Choose by supported feature and source, not brand name; record GPU/CPU compatibility and actual evidence |
| Mixed multi-scene program | Prefer one engine for coherent sequences | Different engines are allowed for independent scene assets; see the handoff rule below |

## Choice precedence

For each scene, the engine is chosen in this order:

1. An explicit engine recorded on the scene itself (the V2 scene spec
   carries an engine field).
2. An explicit engine choice made for the job by the caller.
3. The routing table's preservation rows: an existing React scene stays
   with Remotion and an existing Hyperframes composition stays with
   Hyperframes. These rows describe what the scene already is, so they
   bind more strongly than a generic default.
4. The job manifest's `rendering.default_engine`.
5. The routing table default for the scene requirement.
6. For a scene with no classifiable requirement and no choice above, the
   first production engine (Hyperframes).

Three-dimensional scenes are the exception to this order: qualified
feature support decides (see the capability rules), and an explicit name
is a preference among engines that confirm the feature, not an override.

An explicit compatible choice wins over the scene-type default. Choices are
honored, never silently replaced: if the chosen engine cannot confirm a
capability the job requires, routing fails with an explicit error (see
below). When the choice came only from the routing table default, the other
production engine may take the scene when it confirms every requirement,
and the decision records that the substitution was capability-driven.

## Capability rules

The capability matrix records, per engine: supported codecs, transparency
and alpha support, media types, qualified 3D features, platform evidence,
installed version, and probe status.

- Baseline capabilities are contractual, not matrix-confirmed: both
  production engines are contracted to deliver the Section 4 mode outputs
  (H.264 MP4, poster PNG, source package), to consume image and font media,
  and to render the registered components.
- Requirements beyond the baseline must be confirmed by a capability
  record whose probe status is `ready`: alpha-carrying exports
  (`prores_4444_alpha`, `vp9_alpha`), codecs beyond H.264, media types
  beyond image and font, and any 3D feature.
- An `unprobed` or `unavailable` record confirms nothing. If no engine can
  confirm a required capability, routing returns `MG_CAPABILITY_MISSING`
  and no render starts.
- Missing required capability is an explicit error. It is never permission
  to downgrade imagery, drop alpha, change the delivery profile, or use a
  different renderer quietly. The fix is to provision the runtime, qualify
  the integration, or change the job with the owner's knowledge.
- 3D scenes route by supported feature and source, never by brand name.
  The routing decision records which engine's record confirmed the
  feature, the version and probe timestamp behind it, and the evidence
  notes, including GPU or CPU compatibility where the record states it.

## The legacy renderer

The legacy V1 stack is reachable only through the declared compatibility
path: the job manifest must set `rendering.allow_legacy_fallback` to true
(this contracts version of the manifest schema fixes that field to false,
so V2 jobs cannot declare it yet) and a caller must choose the legacy
engine explicitly for the scene or job. Routing never produces the legacy
engine from a table default, and a capability failure never falls back to
it. A legacy request without the declared path fails with
`MG_CAPABILITY_MISSING`.

## Mixed-engine programs

A multi-scene program may route different scenes to different engines when
the scenes are independent assets. The rules:

- Prefer one engine for coherent sequences; split only where scenes are
  genuinely independent.
- Engines exchange normalized scene assets and timeline metadata, never
  hidden live runtime state. Do not nest a Hyperframes render inside
  Remotion or the reverse, and do not double-apply transitions or audio
  mixing at a boundary.
- Shared handoffs must match timing, codec, color, audio, and dimensions.
- Exactly one engine owns final assembly for the program: the routing
  decision names it (the primary engine, the engine of the program's first
  scene), and every dispatch outcome carries the per-scene assignments so
  the handoff is explicit.

## The capability matrix: production and refresh

`references/renderer-capabilities.json` is generated and verified, never
hand-asserted. The flow is:

1. The shared runtime provisioner (MG-003) provisions the engines and runs
   real launch probes. Its runtime lock records measured versions, the
   browser revision, FFmpeg version, and per-engine probe results.
2. The refresh function in `runtime/src/adapters/capabilities.ts`
   (`refreshCapabilityMatrix`, also used by the contract tests) converts
   probe records into matrix records. An engine becomes `ready` only when
   a probe measured its version AND a launch succeeded. A probe without a
   successful launch records `unavailable`.
3. The matrix validator enforces the honesty rules structurally: a `ready`
   record must carry a version, a runtime-lock identity, a probe timestamp,
   and at least one evidence note; an `unprobed` record must carry null
   version fields and confirm no capabilities. A matrix that violates these
   rules is rejected as `MG_SCHEMA_INVALID` before routing reads it.

Current state, stated plainly: the shared runtime provisioner (MG-003) has
landed and its probe has run on this machine. The checked-in matrix was
refreshed from that probe record (runtime lock `lock-314fc289b233ca9e`,
2026-10-14) and now records Remotion 4.0.535 and Hyperframes 0.8.155 as
`ready` with the evidence the probe actually produced: the probe rendered
a real Remotion PNG still and ran the Hyperframes CLI doctor check. It
measured no video codec, no transparency, and no 3D capability, so those
lists stay empty and the matrix confirms none of them; the legacy stack
remains `unprobed`. Baseline routing works (the table above decides the
engine); any job that requires a beyond-baseline capability still fails
with `MG_CAPABILITY_MISSING` until a probe record confirms it. The matrix
is the record; read it rather than trusting this paragraph, and refresh it
through the refresh function whenever a new runtime lock lands.

## Error behavior

All failures are structured `AdapterError` values carrying a stable
category and a Section 16.9 exit class. Nothing fails silently.

| Category | Exit class | Meaning |
|---|---|---|
| `MG_SCHEMA_INVALID`, `MG_UNKNOWN_COMPONENT`, `MG_MODE_MISMATCH`, `MG_TIMELINE_INVALID` | 2 | The job failed the contracts validation layer; no adapter was invoked |
| `MG_ENGINE_MISSING` | 3 | No adapter is registered for the routed engine, or the capability matrix itself is missing |
| `MG_CAPABILITY_MISSING` | 3 | A required capability is confirmed by no suitable engine, or legacy was requested without the declared compatibility path |
| `MG_APPROVAL_REQUIRED` | 4 | Final render was attempted without an approved delivery approval record |
| `MG_RENDER_FAILED` | 5 | The adapter failed the operation; the original message and any stderr log are preserved on the error |
| `MG_TIMEOUT` | 5 | The operation exceeded its timeout; the dispatcher invoked the adapter's cancel for the job |
| `MG_CANCELLED` | 8 | The operation was cancelled before it started or while running; the dispatcher invoked the adapter's cancel for the job |

Timeouts: every dispatcher call carries a timeout (five minutes by
default; render finals pass an explicit budget). Adapters receive a call
context with an abort signal and a deadline, and pass the signal to their
subprocesses. Cancellation: a caller may cancel through its own abort
signal or through `MotionDispatcher.cancel(jobId)`; the dispatcher aborts
the in-flight call and notifies the owning adapter.

## Authoring models

Routing decides render engines only. Which model authors a job's scene
code is a separate concern governed by the authoring-model freedom rule in
SKILL.md and INSTRUCTIONS.md: the client's selection or their configured
default applies, and any recommendation is guidance only. This document
prescribes no authoring model, and rendering approved source needs no
model credential.
