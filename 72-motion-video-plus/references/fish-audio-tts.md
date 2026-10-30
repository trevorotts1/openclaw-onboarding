# Fish Audio TTS: Skill 72 Voiceover Rules

These are the provider rules for `scripts/tts.py`, the narration
tooling. They apply only when a job's resolved audio plan calls for
Fish Audio narration: a narrated `standalone_video` job
(`audio.mode` `own`, stage 6 of `INSTRUCTIONS.md`) or a job on the
legacy compatibility path. Audio ownership is decided by the mode
and resolved once by the MG-023 audio policy
(`references/audio-policy.md`). PowerPoint jobs are silent and VSL
inserts inherit the parent's audio: those jobs produce no narration,
consult no TTS credential, and `tts.py` run against a silent job
exits cleanly with a recorded no-narration result before any
credential check. Narration is measured, never assumed: the
durations this tooling measures are what the timeline is compiled
from.

## Models

From Fish Audio's OpenAPI spec, the TTS model enum is: `s1`, `s2-pro`, `s2.1-pro`, `s2.1-pro-free`, and `drama-3`.

- **Tooling default: `drama-3`.** This is the model `scripts/tts.py` requests when the job does not configure another (manifest `tts` settings). `s2.1-pro` is the prior-gen fallback. It is a provider setting for this tool, recorded in the narration fingerprint; it is not an authoring-model prescription, and a job may configure a different listed model.
- **Prior gen: `s2.1-pro`.** A job may configure this explicitly when Drama-3 is unavailable. There is no product literally called "Fish Audio 3"; the model string is `drama-3`.
- `s2.1-pro-free` exists in the enum but the free tier is forbidden for client voice work; do not use it.

## The silent-fallback rule (critical)

The spec says an unrecognized model value SILENTLY falls back to `s2.1-pro` instead of erroring. That means if an API key lacks `drama-3` access, the request may quietly return S2.1 Pro audio while the operator believes they got Drama 3.

The skill MUST verify which model actually served each request:

1. After every TTS request, read the response metadata for the serving model (must read `drama-3` when requested).
2. Compare it to the requested model.
3. On mismatch, STOP the voiceover stage and surface it to the operator plainly: requested X, served Y. Never silently accept the fallback.
4. `scripts/tts.py` implements this check and exits non-zero on mismatch. If the served model cannot be determined, it refuses unless `--allow-unverified` is passed, and says so plainly.

## Pricing (exact)

- **Drama-3 API list: $50/M chars; launch window Oct 13 - Nov 12 2026: $10/M chars (80% off).** S2.1 Pro is $15 per 1M UTF-8 bytes (about $0.20 per 15 minutes of voiceover, about $1.56 per 2 hours). Do not use any other figures.
- **Drama-3 launch pricing (80% off) runs Oct 13 - Nov 12 2026.** Document the invoiced rate in the run notes; never guess.

## Chunking rules

Chunking is transport, not scene structure (MG-020/MG-023):

- Narration text is split at sentence boundaries and packed into
  provider-limited transport chunks. A chunk is one API request,
  never a visual scene and never a per-scene quota.
- The per-request cap is a named, configurable maximum: 4,000
  characters by default (`DEFAULT_MAX_CHARS_PER_REQUEST` in
  `scripts/tts.py`), overridable per job via manifest
  `tts.max_chars_per_request` or per run via `--max-chars`. It is a
  ceiling only. There is NO minimum chunk size and NO padding: a
  short scene produces one short chunk, and a long scene produces
  as many chunks as the cap requires. Never cut mid-sentence.
- Same `reference_id` voice model on every request.
- Temperature 0.3 to 0.5 for delivery consistency.
- Identical model and settings on each call; the settings are part
  of the narration fingerprint, so changing them invalidates the
  compiled timeline and its approvals.
- Send requests concurrently with bounded parallelism (default 5,
  the starter-tier concurrent-request limit; tune with
  `--max-workers`), each with exponential backoff on 429. Chunks
  are fetched independently and joined in narration order.
- Join chunks with short crossfades in assembly.
- AUDIO-FIRST TIMING: chunk durations are measured with ffprobe
  and summed per scene into `durations.json`. In the narrated
  branch the timeline is compiled from these measured durations;
  the picture is timed to the audio, never the reverse.

## Multi-speaker (preview)

The spec confirms multi-speaker dialogue synthesis for `drama-3`. Note it as a capability for multi-voice long-form content (for example interview or conversation scenes). It is marked preview: verify output quality on a short sample before committing a full run to it.

## Credentials

The API key comes from the `FISH_AUDIO_API_KEY` environment variable. Never write it into the skill directory, the manifest, or any repo file. A job with no narration never reaches the credential check.
