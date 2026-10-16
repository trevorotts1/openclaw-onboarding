# Motion Video Plus: Skill 72 Master Integration Contract

## Purpose

Skill 72 is the OpenClaw-native home of governed motion-graphics
production in four delivery modes: `powerpoint_graphic`,
`vsl_desktop`, `vsl_mobile`, and `standalone_video`. Every job runs
one canonical pipeline (mode-first intake, a schema-validated job
package, typed component scenes, a compiled timeline, gated preview
and approvals, render, technical QC, and measured delivery) behind
two first-class production renderers, Hyperframes and Remotion,
provisioned by the shared rendering runtime and reached only through
the adapter layer and its routing contract. The legacy V1
`window.__setTime(t)` renderer survives only as an explicit
compatibility adapter for migrated V1 jobs; it is not the pipeline,
not a default, and not a fallback.

Engine boundaries (directive Section 3.3, binding):

- Never nest one engine's renderer inside the other. Hyperframes and
  Remotion exchange qualified media artifacts and manifests at a
  boundary, never hidden live runtime state, and transitions and
  audio mixing are never double-applied across a boundary.
- The legacy `__setTime` path is a compatibility adapter only. New
  jobs do not silently fall back to it, and a V2 job's manifest pins
  `rendering.allow_legacy_fallback` to false.

## Boundary with existing video skills

| Request | Canonical owner |
|---|---|
| Motion graphics in the four modes above (animated charts, explainers, product or brand pieces from code-driven animation) | **Skill 72** |
| AI video-model generation (Kie.ai) | **Skill 67** |
| Documentary montage / whole VSL / talking-head pipelines (OpenMontage) | **Skill 47** |
| Hands-on editing of existing footage | video-editor craft |
| Captions on a finished video | Skill 26 |

A plain request to "make me a promo video" routes by method: code-driven motion graphics goes to Skill 72; generative footage goes to Skill 67; montage goes to Skill 47. A user does not need to know the skill number or name.

Skill 72 supplies the motion graphics a VSL needs; the VSL itself,
including its narration and music, stays owned by its producer
(Skill 47), and VSL inserts are handed back to that parent through
the shipped handoff contracts (`references/vsl-desktop-handoff.md`,
`references/vsl-mobile-handoff.md`). Presentation decks consume
Skill 72 components through the existing presentation pipeline
(`references/integration-contracts.md`); Skill 72 builds no deck of
its own.

## Department ownership

Primary department: `video`
Primary role: `video-editor`
Secondary roles: `storyboard-pre-production-specialist`, `head-of-video-production`

This uses the repo's existing native-skill invocation architecture; do not create a new department or duplicate role merely for Skill 72.

## Execution seams

- Skill 72 owns the canonical contracts, the timeline compiler, the
  two production adapters and their routing, the component catalog,
  the approvals and gates, the audio policy, technical QC, the
  mode producers (PowerPoint packaging, VSL handoffs, standalone
  build), and the status, recovery, and delivery layer
  (`references/status-and-delivery.md`), including the delivery
  receipt.
- Skill 47 owns the OpenMontage pipelines when documentary montage
  or a whole VSL is selected instead. Its shipped bridges consume
  Skill 72 work without owning it: `47-movie-producer/scripts/vsl_handoff.py`
  files and assembles returned inserts, and
  `47-movie-producer/scripts/motion_status.py` carries the Skill 72
  status ledger onto the parent's board and attestation manifest.
  An insert reports under its parent's task identity and never
  creates a task of its own.
- Skill 45 (Design Intelligence) owns image style analysis and
  style cards. The only crossing is the explicit bridge in
  `references/design-intelligence-bridge.md`: a reference goes to a
  Style Analyst, a style card comes back as analysis only, and
  Skill 72 never re-scores it.
- Skill 67 owns Kie.ai video-model routing when generative footage is selected instead.
- Skill 26 owns captioning on the finished MP4.
- PowerPoint playback is UNVERIFIED on every platform. Skill 72
  proves the embed structure, the poster, and artifact hashes
  (`references/powerpoint-packaging.md`); it never claims playback
  was tested in PowerPoint.
- Client providers only at runtime; operator keys never touch a client box.
- Authoring-model freedom: no model vendor is banned or prescribed for this pipeline. Each job resolves its authoring model in order (explicit job choice, existing task choice, client configuration or configured default, then one question) and records the actual model, provider, and harness identifiers. A recommendation may be offered with reasons as guidance only; it is never a hidden prescription or default. Rendering approved source is local and needs no LLM credential.
