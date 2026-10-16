# Caching and Resume (MG-027)

Content-addressed caching and crash-safe resume for the V2 motion
runtime. Implemented in `runtime/src/cache/` (types, keys, state,
verify, session) and proven by `runtime/tests/run-cache.ts` against
real renders of the shipped C05 fixture jobs. This document is the
human-readable authority for the cache layer's contracts.

## Why this exists: defect D-RESUME-KEY

The legacy renderer's resume state (`scripts/render.js`,
`.render-state.json`) records a scene id, fps, width, height, and a
done-through frame counter, and a later `--resume` run trusts any
frames on disk whose numbers fall below that counter. Nothing in the
state says which assets, scene source, data, fonts, timing, export
settings, or tool versions produced those frames. Change any of them
and the resume silently reuses frames rendered for a different
revision of the job.

The V2 rule is the opposite: **reuse is earned, never assumed.** A
scene's output may be reused only when (1) a cache key derived from
every input that can change its pixels matches the current job
revision, and (2) the recorded artifact still verifies against its
record at the moment of reuse. State files that cannot establish
both are rejected with named findings, and the worst case is always
a re-render, never a silent reuse.

## Cache keys

A scene key is a sha256 over a versioned envelope
(`mg027-scene-key-v1`) of per-class digests. Each class digest is a
sha256 of that class's canonical form (object keys sorted
recursively; hash maps as sorted id-to-digest pairs), so key
equality means every class matches, and a mismatch can name exactly
which classes changed.

| Class | Covers |
| --- | --- |
| scene_source | The scene spec / scene source bytes. |
| props | The exact props payload the engine consumes, canonically serialized. |
| assets | Id-to-sha256 for every asset the scene declares (asset file contents). |
| fonts | Id-to-sha256 for every font the scene resolves (the resolved font files, per weight). |
| data | Id-to-sha256 for every data document the scene consumes. |
| timing | The compiled timing for the job: the MG-021 canonical timeline document plus its sidecar, canonically serialized. Timing is a job-level input; a timing change re-keys every scene it can move. |
| geometry | Width, height, fps. |
| export_settings | The export settings record (container, video profile, codec and quality settings) as declared by the caller. |
| versions | Engine name, exact adapter version, timeline compiler version. |
| runtime | The shared runtime lock id the render executes under. |

Two supporting rules:

- **Absent inputs are explicit.** If an input file is missing at
  derivation time, an absent sentinel is hashed in its place and a
  `MG_CACHE_INPUT_ABSENT` finding is emitted. Absence changes the
  key; it never quietly drops out of it. The render that follows
  fails on the missing input in the open.
- **The job key** (`mg027-job-key-v1`) binds the ordered scene keys,
  the job timing hash, the export settings digest, and the runtime
  lock id. It names a whole job revision; per-scene staleness is
  decided by scene keys.

## Work directory layout

One session work directory serves one job:

```
render-state.json            current state generation
render-state.json.prev       previous generation (recovery)
artifacts/<sceneId>/<key>/<file>     verified completed artifacts
chunks/<sceneId>/<key>/...           in-progress frame chunks
quarantine/<sceneId>/<oldKey>-<file> superseded artifacts (bounded)
```

Artifact and chunk paths embed the cache key. A path minted for one
revision can never be the path of another revision, so stale frames
cannot leak into a new output through path reuse; the hash
verification below then proves the bytes at the current path are
the bytes that were verified at completion.

## State format and atomicity

`render-state.json` is the `CacheState` document (see
`runtime/src/cache/types.ts`): job id, job key, a monotonic
generation, one record per scene (key, per-class digests, status
`in_progress | complete | failed`, completed chunk indexes, the
verified artifact record or null, bounded failure records), and the
registered review evidence list.

Completed artifacts and in-progress chunks are tracked as different
kinds of thing: an artifact record exists only after verification,
while chunk progress exists only while a scene renders. There is no
state in which a scene is "complete" on the strength of chunks.

Writes are atomic, write-temp-then-rename:

1. Serialize the full document to a temporary file in the same
   directory and fsync it.
2. Rotate the current `render-state.json` to
   `render-state.json.prev`.
3. Rename the temporary file over `render-state.json`; fsync the
   directory (best effort).

A reader therefore always sees a complete document: the previous
generation or the new one. The failure cases are all named:

- Main file torn or unparseable, previous generation valid:
  recover it, emit `MG_CACHE_STATE_TORN_RECOVERED`. At most the
  last chunk update is lost, which only ever costs a re-render.
- Main file missing (crash between the renames): same recovery.
- No readable generation: start empty, emit
  `MG_CACHE_STATE_UNREADABLE`.
- Main file in the legacy render.js shape (scene, fps,
  doneThrough, no content keys): reject it with
  `MG_CACHE_STATE_LEGACY_SHAPE`. It is never used as resume
  evidence; this is the D-RESUME-KEY shape, including when scene id
  and fps happen to match the current job.
- State belonging to a different job id: reject with
  `MG_CACHE_STATE_JOB_MISMATCH`.
- A malformed per-scene record inside a valid document: drop that
  record only, emit `MG_CACHE_STATE_RECORD_INVALID`.

State is saved after every chunk completion and every status
transition, so a kill mid-render loses at most the in-flight chunk.

## Verification before reuse

`plan()` reuses a scene only when its record is complete, its key
matches the current revision, and `verifyRecordedArtifact` passes
right now:

1. The artifact file exists (else `MG_CACHE_ARTIFACT_MISSING`).
2. Its byte size equals the record (else `MG_CACHE_ARTIFACT_CORRUPT`).
3. Its full sha256 equals the record (else `MG_CACHE_ARTIFACT_CORRUPT`).
4. Where the artifact is media (video or image by extension), an
   independent ffprobe or header probe equals the recorded facts:
   dimensions, exact decoded frame count, and frame rate as an exact
   rational (else `MG_CACHE_ARTIFACT_PROBE_MISMATCH`, including when
   the file cannot be probed at all).

At completion the session also cross-checks the renderer's own
reported probe against its independent probe and refuses the
artifact on disagreement.

A scene whose key changed is reported with
`MG_CACHE_STALE_REVISION`, and the finding names the changed input
classes (for example `assets` when one declared asset file changed,
with scene id and fps unchanged: the exact case the legacy state
silently reused).

## Session lifecycle

`CachedRenderSession.open` loads state, derives keys, and reconciles:
stale records are dropped, their artifacts quarantined, their chunk
files deleted (registered review evidence excepted). `plan()` returns
per-scene decisions. `run(rendererFor)` executes: reused scenes are
untouched; rendered scenes move `in_progress` (resuming recorded
chunk progress under the same key), then `complete` with a verified
artifact record, or `failed` with bounded evidence. One scene's
failure does not strand the others; resume is the recovery path.

Renderers are caller-supplied functions that produce the artifact at
the content-addressed path and report chunk completions. A
monolithic engine render (an adapter `renderFinal`) declares one
chunk; a frame-chunk renderer (stills plus encode) declares its
chunk count and, on resume, skips completed chunks after checking
the chunk files it relies on are actually on disk, because state
alone is never proof of bytes.

## Cleanup policy

- **After a verified successful encode** (the scene's artifact is
  complete and verified), the scene's intermediate chunk files are
  removed. A completed scene never needs its frames again: the
  artifact is the resume unit.
- **After a failure**, nothing is cleaned. The frames needed for
  resume and the bounded failure record survive; the next run
  resumes the chunks and appends to the failure history.
- **Review evidence is never cleaned.** Files registered with
  `registerReviewEvidence` (proof stills, posters, review records)
  are preserved by every cleanup, including stale-revision chunk
  removal, and their hashes stay in state so preservation itself is
  verifiable after the fact (`verifyReviewEvidence`).
- **Quarantine is bounded.** A superseded artifact moves to
  `quarantine/<sceneId>/`, keeping at most one file per scene
  (`MAX_QUARANTINE_PER_SCENE`); older quarantined artifacts are
  removed. Quarantined files are audit material only: no code path
  assembles output from quarantine.

## Failure evidence bounds

Per scene, state retains at most `MAX_FAILURE_RECORDS` (3) failure
records, newest last. Each record carries the timestamp, the
failure category, the message, and a log tail capped at
`MAX_FAILURE_LOG_CHARS` (1000) characters. The bounded history
survives a later success under the same key (the record shows the
scene failed, was resumed, and completed), and is reset when the
key changes, because a new revision's history starts with itself.

## Integration

The cache layer is engine-agnostic and ships as a library
(`runtime/src/cache/`). Two integration points are deliberately
documented follow-ups rather than silent omissions:

- **Dispatcher wiring (done by MG-046).** `MotionDispatcher.
  renderFinalCached` opens one cache session per job
  (`runtime/src/orchestrator/cache-units.ts` derives the per-scene
  key inputs from the validated job package), supplies per-scene
  renderers backed by the routed adapter (each scene renders
  through a scene-scoped staged view of the job package, because
  the production adapters are single-scene today), and assembles
  the final output only from `artifactPathFor`, which returns a
  path only for a complete, current, verified record. Interrupt
  and resume therefore work through the production path, not only
  this layer's own harness: `runtime/tests/run-status.ts` kills a
  production-path dispatch mid-render with SIGKILL and resumes it
  in a fresh process, the finished scene byte-identical and
  unre-rendered.
- **Legacy render.js.** The legacy script is dependency-free
  CommonJS and cannot import this layer (the same constraint MG-024
  recorded). Its state shape is rejected by name at this layer's
  boundary (`MG_CACHE_STATE_LEGACY_SHAPE`). Bringing the legacy path
  onto content keys means porting it to the session API or retiring
  it; until then its `--resume` remains the legacy behavior and is
  not V2 resume evidence.
