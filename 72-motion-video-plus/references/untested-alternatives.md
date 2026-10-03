# Untested Alternatives: Skill 72

These tools exist and may one day serve this pipeline. They are UNTESTED for it. Never present them as proven, never build a client run on them without the operator's explicit opt-in, and never let an untested renderer silently replace the proven stack.

## Proven (use freely)

- FFmpeg (frame encode, concat, sidechain ducking, final MP4)
- Headless Chromium (frame screenshots)
- Node frame driver with `playwright-core` (`scripts/render.js`)
- Fish Audio TTS (`scripts/tts.py`)

## Untested (documented here so nobody mistakes them for proven)

- **Diffusion Studio**: timeline-based web renderer. Not tested with the `window.__setTime(t)` contract.
- **Hyperframes**: frame-oriented renderer. Not tested with this pipeline's resume and cleanup flow.
- **Remotion**: React-based video framework. Not tested as a replacement for the HTML/JS plus Chromium screenshot path.

## Frontier (architecturally free, UNTESTED)

- **Fleet rendering across multiple machines.** Frame ranges are independent units, so splitting a render across several boxes is architecturally free: 4 boxes at 8 workers each is roughly a 3-minute frame render, about 20 minutes total for a 5-minute video. This has NEVER been tested. It is future work, not a capability. Never present it to a client or operator as something the skill can do today.

If the operator asks to trial one: run it on a single 6-second test scene first, compare frames against the Chromium path, and record the result before any client work touches it.
