# Technical QC (MG-034)

How final artifacts are technically verified for Skill 72 V2, what
the QC report means, and how downstream items consume it. The
implementation is `scripts/qc.py`; `scripts/qc.sh` is a thin wrapper
that keeps both invocation paths working. The report format is
versioned at `references/qc-schema.json` (schema_version 1.0).

## Why this replaced the old sweeps

The legacy qc.sh had three structural holes (defect register
D-QC-FALSE-GREEN):

- Its contact sheet step ran a Python heredoc whose failure was
  never checked; the shell printed PASS for the sheet
  unconditionally.
- Its blackdetect and freezedetect sweeps counted grep matches of
  ffmpeg output. An ffmpeg failure prints nothing matchable, so a
  broken sweep read as zero defects and passed.
- Its duration check compared the output's audio stream against the
  output's video stream, so a final that was wrong in the same way
  in both streams passed against itself.

The replacement is built so none of those shapes can recur. Every
check emits an explicit result, tool errors propagate as named
failures, and the artifact is validated against the planned truth,
never against itself.

## Running it

```
bash scripts/qc.sh --job-dir job/
python3 scripts/qc.py check --job-dir job/ [--final PATH] [--out REPORT]
python3 scripts/qc.py check --plan plan.json --sidecar sidecar.json \
    --media media.json --final final.mp4 --coverage coverage.json
bash scripts/qc.sh --manifest run/manifest.json --workdir work \
    --final final.mp4        (legacy V1 lane)
```

In job-dir mode the report is also written to
`<job-dir>/qc/final-qc.json`, the path the MG-025 delivery gate
reads. The report is printed to stdout in every mode. Exit codes
follow directive Section 16.9 through the same category map the
delivery gate uses: 0 pass; 9 foreign job or hash mismatch; 2
schema, mode, or timeline invalid; 3 input missing; 5 encode
failed; 6 QC failed or coverage incomplete; 1 internal error (the
report still prints, with a named `qc.internal` failure; QC never
exits traceback-only).

## The result vocabulary

Every check produces exactly one of:

- `PASS`: the measurement ran and the artifact satisfies it.
- `FAIL`: the measurement ran (or its evidence was inspected) and
  the artifact violates it, or required evidence is absent or
  bound to different bytes. Carries a stable `QC_*` code and a
  Section 16.9 category.
- `SKIPPED_WITH_REASON`: the check does not apply to this job, and
  the reason is recorded (for example loudness on a job whose audio
  mode has no loudness target). A skip is never a pass wearing a
  different name; the legacy script's "skipped, therefore PASS"
  per-beat sheet line is the pattern this vocabulary exists to
  kill.
- `NOT_RUN`: the check could not execute because a prerequisite
  failed (the tool is missing, the probe failed, the plan did not
  load). The reason names the prerequisite.

Each check carries the command run, its exit status, the observed
values (expected versus measured), and an evidence pointer.

The gate rule: the verdict is `pass` only when no check FAILs and
no mandatory check is NOT_RUN. A missing mandatory check fails the
gate by construction; there is no path where absent evidence
averages out.

## What is checked (V2 package mode)

Setup: `tools.available` (ffmpeg and ffprobe answer `-version`;
a missing FFmpeg fails the gate here, by name), `inputs.plan`
(manifest, compiled timeline and sidecar, and media registry load
and agree on job id, fps, totals, and the sidecar sample rule;
the MG-023 audio plan is resolved once, here).

Artifact: `artifact.exists`, `artifact.hash` (the sha256 that
every other record must bind), `artifact.probe` (ffprobe parses
the container and finds a video stream; corrupt media fails
here), `artifact.decode` (a full decode with zero error lines).

Against the compiled plan, never stream-against-stream:
`plan.dimensions` (artifact versus the manifest or media canvas,
aspect derived from both), `plan.fps`, `plan.frame_count`
(decoded frames versus the timeline total), `plan.duration`
(container duration versus total_frames / fps, tolerance 0.12 s,
the assembler's own), `plan.streams` (audio presence versus the
resolved audio plan's expectation).

Audio, measured on the encoded output with MG-023's measurement
code (Hann-windowed band analysis and energy-weighted presence
aggregates are consumed from `scripts/audio_policy.py`, not
re-derived): `audio.decode`, `audio.duration` (decoded sample
count versus the sidecar's compiled total_samples; a shortfall is
`QC_AUDIO_TRUNCATED`), `audio.clipping` (the assembler's ceiling
rule), `audio.loudness`, `audio.final_words` (every placed
narration segment present at its dominant bands, and the final
segment present at its planned end), `audio.score_audible`,
`audio.mode_promise`.

Video content: `video.black`, `video.freeze`, `video.alpha`.

Package evidence: `review.receipt`, `package.assets` (every
declared asset present and hash-true), `package.fonts`,
`package.lint` (optional; consumes an MG-030 LintReport when one
is supplied), `package.motion_proof` (optional; consumes an
MG-032 record when one exists), `process.registry` (mandatory;
consumes this job's MG-029 process-registry file: no live render
process may remain registered to the job when QC judges the
artifact final).

## Mode-aware audio (MG-023)

Loudness is verified only where it applies: mode `own` jobs that
carry a resolved loudness target (an independent final mix). For
modes `none` and `inherited`, `audio.loudness` is
SKIPPED_WITH_REASON citing the mode, and the job is instead held
to what its mode promises by `audio.mode_promise`:

- `none`: the deliverable is silent. An audio stream is a mode
  violation.
- `inherited`: the parent owns the soundtrack. No audio stream is
  the clean pass; a carried stream must measure silent, and a
  carried audible bed fails as `QC_AUDIO_PARENT_BED_DUPLICATED`,
  because it would duplicate the parent's bed under the program.
- `own`: SKIPPED_WITH_REASON; the own-mode promises are the
  loudness, clipping, narration, and score checks themselves.

## Intent-aware black and freeze sweeps

Detected intervals (blackdetect at 0.5 s / pixel threshold 0.10,
freezedetect at 1.0 s / noise 0.003, the legacy thresholds) are
judged against approvals derived from plan data only. There is no
exemption list in the code. Approval sources, all recorded in the
check's `approval_sources`:

- Timeline `hold_start` events approve a freeze from the event
  frame to that scene's end (presenter and readable holds).
- Scene-spec motion holds (`motion.end_frame_exclusive` to
  `motion.hold_to_frame_exclusive`, mapped from source frames to
  placed frames through the sidecar) approve a freeze.
- Planner beats with `intentional_stillness` and a
  `stillness_reason` approve a freeze over the beat's scene.
- The job package's `qc-approved-intervals.json` declares
  intervals the plan names directly:

```json
{"intervals": [
  {"start_frame": 30, "end_frame_exclusive": 60,
   "kinds": ["dark", "freeze"],
   "reason": "intentional silent dark beat before the reveal",
   "source": "storyboard beat beat-dark"}
]}
```

`kinds` may be `dark`, `freeze`, or `silent_dark` (both). An
interval is approved only when an approval of the same kind fully
covers it (2 frames of edge tolerance for detector boundary
wobble). Anything uncovered at or above the sweep threshold
fails by name: `QC_BLACK_UNAPPROVED`, `QC_FREEZE_UNAPPROVED`. An
approved silent hold therefore passes with its checks PASS or
SKIPPED_WITH_REASON and the approval cited in the observed
values; the identical frames without the plan data fail.

## The review receipt (MG-031)

`review.receipt` requires the MG-031 coverage record for this
artifact: found via `--coverage` or the job's `review/` bundle
directory. It must name this job (else `QC_REVIEW_FOREIGN_JOB`),
carry verdict `complete` (else `QC_REVIEW_INCOMPLETE`, or
`QC_REVIEW_BUNDLE_FAILED` when the bundle itself failed; a
bundle whose verdict is not complete must not be scored, and no
check stands on it), and bind this artifact's exact sha256 in
its `video` record and, when QC was given the standalone
timeline document, the plan's sha256 in its timeline input
(else `QC_REVIEW_HASH_MISMATCH`; a combined plan file hashes
differently from the timeline the bundle consumed even when the
content is identical, so that one binding is enforced only for
the standalone document). A review record
labeled `rough_layout_only` fails as `QC_REVIEW_ROUGH_ONLY`:
rough layout evidence is recorded honestly by MG-031 and is
never upgraded into a final review receipt here. An absent
receipt fails as `QC_REVIEW_RECEIPT_MISSING`; when a bundle
directory exists but holds no record, the check says so, because
that is the shape of a bundle build that died before writing
its record.

## The process registry (MG-029)

The isolation layer records every render process it launches in
one JSON file per job under the process registry directory
(`MOTION_PROCESS_REGISTRY_DIR` when set, else
`$XDG_STATE_HOME` or `~/.local/state`, under
`motion-render/processes`): `{jobId, token, processes}`, each
process entry carrying its pid and the kernel start-time ticks
recorded at launch. `process.registry` reads this job's file
only (the file named by the job id, sanitized the way
`runtime/src/isolation/paths.ts` sanitizes it). Records belonging
to other jobs are never opened and never judged here; when two
job ids sanitize to the same registry segment, a file whose
`jobId` names another job is treated as that job's file and
holds no records for this one.

A `running` record counts as still live only under MG-029's own
identity rule: the pid is alive (present in /proc in a
non-zombie state) and its kernel start-time still equals the
recorded ticks, or, when no ticks were recorded, its environment
carries the job's ownership token. A pid that is dead, or alive
with a different start-time (the pid was recycled and belongs to
someone else), is stale, not live.

- Any live process registered to this job fails the gate as
  `QC_PROCESS_STILL_RUNNING`: the artifact is still being
  produced, or its render leaked processes, so QC over it
  cannot be final.
- Records exist but none are live (finished or stale): PASS,
  with the counts in `observed`.
- No registry file for this job: SKIPPED_WITH_REASON. The
  isolation layer was not in use for the job, so there are no
  registered processes to account for.
- A registry file that cannot be read, does not parse, or
  violates the documented format fails as
  `QC_PROCESS_REGISTRY_INVALID`. A malformed record cannot
  prove the job's render processes are done, so it is never
  silently ignored.

## Alpha and the export profile

`video.alpha` consumes the declared profile from the manifest's
`delivery.video_profile` (the canonical contract's names:
`h264_opaque`, `prores_4444_alpha`, `vp9_alpha`; MG-040 builds
the export machinery behind those names in parallel, and QC
reads the same declaration). No declared profile means no alpha
claim exists: SKIPPED_WITH_REASON. An alpha profile requires an
alpha pixel format whose sampled alpha plane genuinely varies
(a constant alpha plane is opaque in fact, whatever the
metadata says). An opaque profile fails an artifact carrying
genuinely varying alpha: mislabeling in either direction is
`QC_ALPHA_MISMATCH`.

## Fonts and assets

`package.assets` verifies every entry of the package assets
record: present on disk, and sha256-true where the record
declares a hash. `package.fonts` verifies every declared font
requirement: package-sourced fonts must exist as package font
assets. A runtime-registry requirement is declared by alias
token (the canonical `family_alias`): a declared name that is
itself an installed fontconfig family resolves directly. A
declared name that is not an installed family is an alias,
and resolves the way the runtime resolves it: QC parses the
alias to family map out of the runtime's shipped registry
(`runtime/src/remotion/fonts.ts`, `ALIAS_REGISTRY`) at check
time, and the resolved family must be installed. An alias
with no registry entry fails as `QC_FONT_UNRESOLVED` naming
the unknown alias; an alias whose resolved family is not
installed fails as `QC_FONT_UNRESOLVED` naming both the
resolved family and the alias it came from. If the registry
file cannot be read or parsed, the check fails as
`QC_FONT_REGISTRY_UNREADABLE`: it never falls back to
comparing the raw alias token against fontconfig families
(the comparison that false-failed canonically declared
packages) and never passes on an unproven resolution.
`MOTION_FONT_REGISTRY_PATH` overrides the registry location
(a test seam). Each font's observed values record the
resolution: declared token, resolved family, and registry
source. When fontconfig itself is unavailable the check is
NOT_RUN, which fails the gate: font completion that cannot
be proven is not font completion.

## The legacy lane

The historical invocation (`scripts/qc.sh --manifest M
--workdir W --final F`) runs qc.py's legacy lane. A V1 run has no
compiled plan, so expectations derive from the manifest, its
plan of record: per-segment decoded frame counts
(`legacy.segments`), the zero-byte sweep (`legacy.worktree`),
dimensions, fps, total frame count and duration against the
manifest's totals, stream inventory against the manifest's
declared bed and voiceover, and audio length against the
manifest's total duration (never against the video stream; the
legacy tolerance is a documented 0.25 s for the V1 mux chain).
The contact sheet is built with every extraction step checked:
any failure is `QC_CONTACT_SHEET_FAILED`, the direct closure of
the legacy false-green. The determinism backstop
(`legacy.determinism`) runs when node and the scene source files
are in the run tree and is SKIPPED_WITH_REASON otherwise; the
per-beat sheet (`legacy.beat_sheet`) is SKIPPED_WITH_REASON when
no beat grid exists. `review.receipt` is SKIPPED_WITH_REASON in
this lane: the MG-031 contract belongs to V2 job packages, and
the contact sheet is the legacy lane's review evidence.

## The report as a record

The report's top level carries `artifact_path` (job-relative in
package mode), `artifact_sha256`, and `verdict` (`pass` /
`fail`): exactly the fields the MG-025 delivery gate's final-QC
step consumes, so a passing report drops into `qc/final-qc.json`
unchanged, and a failing or absent one blocks delivery there as
it does here. `inputs` records the sha256 of every consumed
record. Validate any emitted report against
`references/qc-schema.json` with the jsonschema Draft 2020-12
validator.
