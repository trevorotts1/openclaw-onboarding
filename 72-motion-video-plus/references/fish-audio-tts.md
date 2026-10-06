# Fish Audio TTS: Skill 72 Voiceover Rules

## Models

From Fish Audio's OpenAPI spec, the TTS model enum is: `s1`, `s2-pro`, `s2.1-pro`, `s2.1-pro-free`, and `drama-3-preview`.

- **Default: `s2.1-pro`.** This is the proven model from the reference run and stays the default for every voiceover unless the operator opts in to something else.
- **Opt-in: `drama-3-preview`.** This is the new model. There is no product literally called "Fish Audio 3". Request it with the model string `drama-3-preview`.
- `s2.1-pro-free` exists in the enum but the free tier is forbidden for client voice work; do not use it.

## The silent-fallback rule (critical)

The spec says an unrecognized model value SILENTLY falls back to `s2.1-pro` instead of erroring. That means if an API key lacks `drama-3-preview` access, the request may quietly return S2.1 Pro audio while the operator believes they got Drama 3.

The skill MUST verify which model actually served each request:

1. After every TTS request, read the response metadata for the serving model.
2. Compare it to the requested model.
3. On mismatch, STOP the voiceover stage and surface it to the operator plainly: requested X, served Y. Never silently accept the fallback.
4. `scripts/tts.py` implements this check and exits non-zero on mismatch.

## Pricing (exact)

- **S2.1 Pro is free through Nov 30 2026**, then $15 per 1M UTF-8 bytes. That works out to about $0.20 per 15 minutes of voiceover and about $1.56 per 2 hours. Do not use any other figures.
- **drama-3-preview pricing is unknown.** There is no published pricing row for it. Document any quote the operator receives in the run notes; never guess.

## Chunking rules

- One request per scene, 2,000 to 4,000 characters.
- Split at scene or paragraph boundaries. Never cut mid-sentence.
- Same `reference_id` voice model on every request.
- Temperature 0.3 to 0.5 for delivery consistency.
- Identical model and settings on each call.
- Send requests SEQUENTIALLY with exponential backoff on 429 (concurrency-based rate limits: 5 concurrent on the starter tier).
- Join chunks with short crossfades in assembly.
- AUDIO-FIRST TIMING: each chunk's measured audio duration sets its scene's timeline. Render the animation to the audio, not the other way around.

## Multi-speaker (preview)

The spec confirms multi-speaker dialogue synthesis for `drama-3-preview`. Note it as a capability for multi-voice long-form content (for example interview or conversation scenes). It is marked preview: verify output quality on a short sample before committing a full run to it.

## Credentials

The API key comes from the `FISH_AUDIO_API_KEY` environment variable. Never write it into the skill directory, the manifest, or any repo file.
