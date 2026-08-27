# KIE Speech-to-Text — ADVERTISED_NOT_YET_VERIFIED (no endpoint, no dispatch)

**Status: `ADVERTISED_NOT_YET_VERIFIED`. `dispatch_enabled: false`. `active: false`.**

KIE's Market overview page advertises an ElevenLabs speech-to-text capability.
This skill does NOT ship an endpoint for it, because the implementation
requirement (SPEC section 9.3) is: locate the exact first-party callable
endpoint/schema BEFORE enabling an STT route. That endpoint was not located on
2026-08-26, and this file must never be "fixed" by inventing one.

## Negative-result trail (2026-08-26, first-party probe)

What WAS searched:

1. Full `https://docs.kie.ai/sitemap.xml` (EN + CN, ~460 URLs) for:
   `stt`, `asr`, `transcribe`, `transcription`, `whisper`, `speech-to-text`,
   `deepgram`, `google/speech` — **zero matches**.
2. Full elevenlabs directory on KIE docs = exactly 4 models:
   `audio-isolation`, `text-to-dialogue-v3`, `text-to-speech-multilingual-v2`,
   `text-to-speech-turbo-2-5`. All four are TTS or audio separation;
   **none is speech-to-text**.
3. Additional probes: `https://kie.ai/market` — **HTTP 403 Forbidden** to
   WebFetch (could not read the market overview claim directly);
   `https://docs.kie.ai/market/` — 404; `https://docs.kie.ai/market/elevenlabs/` — 404.
4. WebSearch for "kie.ai elevenlabs speech-to-text" and variants — zero results
   each time (search tool returned empty result sets; reported as such, not as
   evidence — but combined with zero sitemap hits the conclusion is unchanged).

What was NOT checked (and why it cannot be ruled in or out):

- Whether KIE sells STT OUTSIDE the docs — off-doc endpoints cannot be ruled in
  or out from a docs search. The `kie.ai/market` page (the one place the claim
  appears) is 403-blocked to WebFetch.

Exclusion note: Gemini Omni Audio (`POST https://api.kie.ai/api/v1/omni/audio/create`)
is TTS voice creation, NOT STT — recorded as excluded from this conclusion.

## Dispatch rule

`dispatch_enabled: false`. Any attempt to dispatch a transcription request
through Skill 68 is REJECTED by the bundled validator —
`python3 scripts/validate_audio_request.py --domain stt --payload <file.json>`
— exit 2 with the negative-result reference. An STT request must NEVER be
silently routed to a TTS engine or to an invented transcription path.

## How to re-prove (when the page appears)

1. Find the first-party STT model page in docs.kie.ai (sitemap or market).
2. Confirm a callable endpoint + request/response schema on the page itself.
3. Smoke test with a real audio file ON THE OPERATOR ACCOUNT (never a client
   box, never a client feed — operator-account testing rule).
4. Update: `models.json` (stt entry), this file, `SKILL.md` STT section,
   `CHANGELOG.md`, and bump `skill-version.txt`.
