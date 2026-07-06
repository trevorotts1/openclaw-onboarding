Podcast Production Engine, EPISODE ASSET PACK CERTIFICATE

Skill: 58 (podcast-production-engine)
Gate: BUILD document and media quality control (Gate A posture), NOT the episode gate
Brand slug: first-light-show (fictional regression brand, never a fleet client)
Preset: episode_asset_pack
Operates on existing job key: pd-cH3mR9tSASHA0002-d801ca33e3ad0a79 (the golden Interview episode)
Job key (this run): pd-cH3mR9tSASHA0002-c5818065dc1f41fe
Idempotent against the ledger: True

Regenerated: cover at print resolution, Episode Package document, book teaser PDF
Skipped idempotently: script rewrite, audio render, Podbean publish, enrollment
Reason skipped: the ledger already holds the audio and the Podbean permalink for the existing episode, so those steps are structurally not repeated.
Cover spec: JPEG, RGB, square, within the fourteen hundred to three thousand range.
Teaser: re-typeset only, text not rewritten, no font below fourteen point.
Media upload: Tier 3 REST, public URLs HEAD-verified.
ZERO Anthropic in run: True
Models used: gpt-image-2, glm-5.2, gemini-3.1-flash-lite
Client-facing messages emitted: 0; Convert and Flow owns all customer messaging
Secrets printed: 0
State: complete

Certificate SHA: 2ce0085a7a5b8eb2eb94acca9d96cae537150e9cf9bfdc22cd8c07541d4f111c

Episode Asset Pack regenerates assets for an already-delivered episode. Because the script is not rewritten, this run is checked by document and media quality control, not the full episode gate. No new EPISODE certificate is minted; the original episode certificate still governs the script. The build gate (Gate A) and the episode gate (Gate B) are never conflated. This preset is also the sanctioned handoff for Skill 57 social packaging.