# Export Profiles: Verified Transparency and Intermediate Exports (MG-040)

This document is the operator-facing record for the export layer in
`runtime/src/export/`. It states what each delivery profile is, which
route delivers it on each engine, what was probed on this machine to
qualify that route, and what the packaging metadata guarantees. The
proof suite is `runtime/tests/run-export-profiles.ts`; the live probe
record it produces is `tests/evidence/mg040/export-capabilities.json`
with measured alpha statistics in
`tests/evidence/mg040/alpha-measurements.json`.

## The profiles (data, not flags)

Profiles are defined as data in `runtime/src/export/profiles.ts`.
Their ids are exactly the manifest contract's `delivery.video_profile`
enum in `references/contracts-v2.schema.json`; the suite asserts the
two lists stay identical.

| Profile | Container | Stream codec | Alpha | Purpose |
| --- | --- | --- | --- | --- |
| `h264_opaque` | .mp4 | h264, yuv420p | none | The default delivery profile and the PowerPoint path. Unchanged historical behavior on both engines. |
| `prores_4444_alpha` | .mov | prores, yuva444p | yes | Alpha delivery at mezzanine grade (4:4:4, no chroma subsampling). |
| `vp9_alpha` | .webm | vp9, yuva420p with alpha | yes | Alpha delivery for web targets; alpha travels as WebM stream metadata (see the decoder note below). |

## Routes per engine

A route is either `engine_native` (the engine's own pinned encoder
path produces the artifact) or `image_sequence_encode` (the engine
supplies PNG frames and the export layer encodes them with the
profile's qualified ffmpeg encode).

| Profile | Hyperframes route | Remotion route |
| --- | --- | --- |
| `h264_opaque` | native: CLI render, default mp4 | native: renderMedia h264 / yuv420p / crf 16 |
| `prores_4444_alpha` | native: CLI `render --format mov` (the pinned CLI documents MOV as its fixed alpha-preserving ProRes 4444 profile) | native: renderMedia codec `prores`, `proResProfile` `4444`, pixelFormat `yuva444p10le` |
| `vp9_alpha` | native: CLI `render --format webm` (the pinned CLI documents WebM as a transparency-carrying format) | image-sequence encode: the adapter has no native VP9 alpha render wired, and `renderFinal` for this profile refuses by name (MG_CAPABILITY_UNSUPPORTED) rather than mislabeling; the qualified path is PNG frames plus the export layer's libvpx-vp9 encode |

Every route above that is claimed as wired was exercised end to end
by the MG-040 suite on the C05 fixture job (Hyperframes ProRes and
VP9 finals, Remotion ProRes final), in addition to the analytic
fixture exports through the sequence encode for both alpha profiles.

## Qualification evidence (probed on this machine)

Toolchain: ffmpeg 8.1.2 (the version recorded in the shared runtime
lock), Hyperframes CLI 0.8.155, Remotion 4.0.535, runtime lock
identity `lock-314fc289b233ca9e`.

- Encoder pixel formats, from the pinned ffmpeg's own encoder help:
  `prores_ks` supports `yuva444p10le`; `libvpx-vp9` supports
  `yuva420p`; `libx264` and the PNG encoder are present.
- Micro-roundtrips (`runtime/src/export/probe.ts`): a tiny analytic
  RGBA sequence with a feathered alpha edge is encoded with each
  profile's sequence encode and the decoded output is measured. Both
  alpha profiles qualify: the decoded alpha has many distinct values
  and real partial-alpha pixels. A profile whose roundtrip fails is
  not qualified, and selection treats it as undeliverable.
- Hyperframes CLI `render --help` documents `--format` values
  including `mov`, `webm`, and `png-sequence`, states that MOV/WebM
  render with transparency, and states that MOV always uses the
  fixed alpha-preserving ProRes 4444 profile. The probe captures
  this from the pinned binary at run time.
- Remotion's pinned `@remotion/renderer` 4.0.535 API accepts codec
  `prores` with a ProRes profile option and the pixel format
  `yuva444p10le`; the suite's Remotion ProRes final proves the
  combination on the real fixture job.

Two measurement facts worth knowing:

- ProRes 4444 written by `prores_ks` from `yuva444p10le` input probes
  back as pixel format `yuva444p12le` (the encoder stores a 12-bit
  alpha container). Records state the measured format.
- A VP9 alpha WebM probes as pixel format `yuv420p` with an
  `alpha_mode=1` stream tag (the tag's case varies with the muxer
  that wrote the file; the probe matches it case-insensitively).
  The native VP9 decoder drops that alpha; only the libvpx-vp9
  decoder returns it. All alpha measurement in the
  export layer (`runtime/src/export/verify.ts`) therefore selects
  the decoder from the probed codec, and any consumer measuring VP9
  alpha must do the same.

## Capability selection (before authoring)

`runtime/src/export/select.ts` is the pre-authoring gate. Given a
profile, an engine, the capability matrix, and the live toolchain
probe, it returns the one qualified route or throws
`MG_CAPABILITY_UNSUPPORTED` (Section 16.9, exit class 3, check
`export.route_qualified`) before any rendering starts.

- The opaque default is the baseline contract and always selects the
  engine-native route.
- An alpha profile selects the engine-native route only when the
  capability matrix confirms it for that engine (a probe record that
  measured alpha, folded in by the existing matrix refresh in
  `runtime/src/adapters/capabilities.ts`). The shipped matrix
  confirms no alpha today, because the adapters' runtime probes
  measured launch and stills only and say so.
- Otherwise an alpha profile selects the image-sequence route when
  the live toolchain probe qualified that encode on this machine.
- When neither confirms, selection fails by name. An opaque-only
  path is never labeled transparent downstream: the packaging layer
  below refuses the record in that case.

The dispatcher in `runtime/src/adapters/dispatch.ts` and the routing
rules in `routing.ts` are unchanged by MG-040; routing continues to
consult the capability matrix exactly as before.

MG-046 wired the selection into dispatch, opt-in at the call site:
when a caller supplies an export toolchain probe (or asks the
dispatcher to run one), `routeJob` consults `selectExportRoute` for
jobs whose delivery profile requires alpha. The first engine whose
selection succeeds is routed against an in-memory augmented copy
of the matrix carrying the selection's confirmation; the shipped
matrix file is never written and its claims are never edited, so
the probe, not the matrix, is the qualification authority at
export selection. When no route qualifies, the export layer's own
refusal (`MG_CAPABILITY_UNSUPPORTED`, check
`export.route_qualified`) is thrown before any authoring. Without
the opt-in, routing keeps the matrix-only behavior exactly,
including its `MG_CAPABILITY_MISSING` refusal for alpha jobs.
Proof lives in `runtime/tests/run-status.ts` (probe-qualified
alpha routes and renders; unqualifiable alpha refuses by name
with zero adapter calls; the shipped matrix is byte-identical
afterwards).

## The intermediate-quality policy

One policy governs every intermediate encode in the export layer
(`INTERMEDIATE_POLICY` in `runtime/src/export/profiles.ts`, id
`png-mezzanine-single-encode`):

- The mezzanine is a lossless PNG frame sequence (RGBA). Handing
  work between stages through the mezzanine adds zero drift.
- A delivery encode consumes the mezzanine (or engine frames) in
  exactly one encode at the profile's fixed settings. A delivery
  encode never consumes another delivery encode.
- When a video mezzanine is unavoidable, it is created once, from
  the PNG mezzanine, at mezzanine settings (ProRes 4444 at its
  fixed profile grade, or VP9 lossless), never at delivery settings.

The suite proves the consequence on the analytic fixture: through
two generations (encode, decode back to PNG, encode again) the
ProRes path keeps known-patch color within a mean error of 2 per
channel and the one-pixel chromatic detail region within a mean
absolute error of 1.0, and the VP9 lossless-mezzanine path keeps
patches within 5. The unmanaged chain the policy forbids (a
delivery-grade VP9 crf 40 encode used as the intermediate, encoded
again) starts at a detail-region red-channel MAE of about 105 and
compounds to about 112 by the second generation, roughly two orders
of magnitude outside the policy result. Note the honest limit of the VP9 numbers:
for extreme one-pixel chromatic detail, the RGB to yuva420p
conversion itself is the dominant first-encode cost on any VP9 path;
the policy bounds the additional, compounding loss, and ProRes 4444
(4:4:4) is the profile that preserves such detail.

## Packaging metadata (the export record)

Every adapter final, and every export-layer encode the suite
produces, is described by an export record
(`runtime/src/export/metadata.ts`), written as a sidecar beside the
artifact (`<artifact>.export-record.json`), embedded in the
Hyperframes render receipt, and carried on the render evidence as
`exportRecord`. The record states:

- the delivery profile and the route that produced the artifact;
- the artifact's SHA-256;
- the measured stream facts (codec, pixel format, dimensions, exact
  frame count, frame rate) from ffprobe on the artifact itself;
- the measured alpha verdict: `verified_alpha` (a channel with real
  partial alpha and many distinct values), `alpha_opaque_content`
  (a channel whose measured content is uniformly opaque), or
  `opaque` (no channel);
- the intermediate policy id.

The verdict is derived from measurement only, never from the
profile's promise. Truth is enforced in both directions:

- Building a record for an alpha profile over an artifact with no
  alpha channel throws MG_QC_FAILED (check
  `export.alpha_channel_present`); the mirror case throws
  `export.alpha_unexpected`. The mislabel cannot be written.
- `verifyExportRecord` re-measures any record against its artifact
  and reports named findings: `export.profile_known`,
  `export.artifact_hash`, `export.label_match` (profile versus
  measured codec and pixel format), and
  `export.alpha_verdict_match` (recorded verdict versus re-measured
  verdict). A forged record, for example one claiming
  `verified_alpha` for the opaque default artifact, fails by name.

Content note: the verdict describes the artifact, not the author's
intent, and the two engines genuinely differ on the same fixture
job. The Hyperframes ProRes final measures `verified_alpha` (the
composition renders against transparency; most of the canvas is
transparent around the chart, with tens of thousands of
partial-alpha pixels at the antialiased edges). The Remotion ProRes
final of the same job measures `alpha_opaque_content`: the channel
is present and correctly labeled, but the Remotion composition
paints an opaque background, so the measured content is uniformly
opaque. Both records are the truth, produced by the same
measurement code; a consumer that needs verified content alpha
must read the verdict, not the profile name.

## Honest limits

- Remotion has no native VP9 alpha render wired; the refusal and
  the qualified sequence route are documented above.
- The shipped capability matrix still confirms no alpha for either
  engine, because no engine probe record has measured alpha yet.
  MG-040 does not edit that matrix or either adapter's probe: the
  matrix refresh path will confirm the native routes when a future
  probe record measures them. Until then, selection routes alpha
  through the probe-qualified sequence encode at the export layer,
  and the adapters' native finals carry measured export records as
  their evidence.
- PowerPoint playback of the default profile is the historical
  h264/yuv420p mp4, unchanged. Playback inside Microsoft
  PowerPoint is UNVERIFIED on every platform; this item verified
  the export profile and its measurements, not playback.
