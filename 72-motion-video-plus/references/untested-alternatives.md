# Renderer Status: Skill 72

This file keeps its historical filename so existing links resolve. It is no longer a list of untested alternatives. It records the current status of every renderer Skill 72 knows about, and what "ready" means.

## Production adapters (Skill 72 V2)

- **Hyperframes**: a production adapter of Skill 72 V2.
- **Remotion**: a production adapter of Skill 72 V2.

Neither adapter is ready on a given machine because a document says so. Readiness is proven by records in the shared rendering runtime: a capability record stating what the adapter can do on that machine, and a launch record from an actual successful render launch. The capability matrix is `references/renderer-capabilities.json`; the routing authority that decides which adapter a job uses is `references/renderer-routing.md`. If a machine has no current capability and launch records for an adapter, treat that adapter as not ready on that machine until the shared runtime produces them.

## Proven local path

- FFmpeg (frame encode, concat, sidechain ducking, final MP4)
- Headless Chromium (frame screenshots)
- Node frame driver with `playwright-core` (`scripts/render.js`)
- Fish Audio TTS (`scripts/tts.py`)

This deterministic local path remains the proven route for the V1 HTML scene contract (`window.__setTime(t)`).

## Still untested (each with its specific gap)

- **Diffusion Studio**: timeline-based web renderer. Gap: never integrated with this skill's scene contract, manifest, or QC gates, and no capability or launch record exists for it in the shared runtime. It is not a production adapter, and it is not grouped with the two production engines above.
- **Fleet rendering across multiple machines**: frame ranges are independent units, so splitting a render across several boxes is architecturally plausible. Gap: never run end to end; no multi-machine render has been executed or measured. It is future work, not a capability the skill offers today, and it must never be presented to a client or operator as available.

If the operator asks to trial an untested item: run it on a single short test scene first, compare the output against a production path, and record the result before any client work touches it.
