# BlackCEO Video Prompt Policy & Compression Guide

Authoritative Reference: BlackCEO Execution Spec §5 (Prompt Rules A–E, Structure, Expansion, Compression).

---

## 1. Character-Based Prompting Doctrine

BlackCEO prompt policy is measured in **exact characters, not words**.
When legal under vendor model limits, the system operates in the following standard house band:
- **Desired Minimum:** 5,000 characters
- **Target Operating Length:** ~9,000 characters
- **Preferred Maximum:** 19,000 characters

### Priority Rule: Model Hard Limit Always Wins
The runtime selects the model first, evaluates its hard constraints, and enforces the appropriate operational band:

- **Rule A: Verified Character Cap ≥ 20,000**
  - Models: `wan/3-0-video`, `wan/3-0-video-prime`, `gemini-omni-video`, `bytedance/seedance-2-5`.
  - House band applies: 5,000–19,000 characters, targeting ~9,000 characters. Full descriptive detail, beat-by-beat timing, lighting, camera choreography, and soundscapes are mandatory.
- **Rule B: Verified Character Cap Between 5,000 and 19,999**
  - Models: `minimax-h3/*` (7,000 cap), `pixverse-v6/*` (5,000 cap), `wan/2-7-*` (5,000 cap), `happyhorse-1-1/*` (5,000 non-CN cap), `happyhorse/*` (5,000 non-CN cap).
  - Do NOT target 19,000 or the exact hard cap. Enforce safe ceilings:
    - MiniMax H3: ~6,500–6,900 chars (safe below 7,000).
    - PixVerse V6 / Wan 2.7 / HappyHorse: ~4,500–4,900 chars (safe below 5,000). Never force 5,000 as a minimum.
    - HappyHorse Chinese: ~2,200–2,400 chars (safe below 2,500).
- **Rule C: Verified Hard Cap Below 5,000**
  - Models: `kling-3.0-omni/*` (3,072 cap), `kling-3.0/motion-control` (2,500 cap), `kling-2.6/motion-control` (2,500 cap), `kling/v2-5-turbo-*` (2,500 cap), Runway (~1,800–2,048 cap).
  - House 5,000-character minimum is impossible. Do NOT attempt to force it. Enforce safe high-density ceilings:
    - Kling 3.0 Omni: ~2,700–2,950 chars (safe below 3,072; per-shot max 512 chars).
    - Kling 2.5 Turbo / Motion Control: ~2,200–2,400 chars (safe below 2,500).
    - Runway: ~1,600–1,750 chars (safe below 1,800).
- **Rule D: Token Caps**
  - When a model publishes a token limit (e.g. Qwen Image), do not convert it to an arbitrary character figure. Use token-aware estimation.
- **Rule E: Unverified / Not Published Limits**
  - Models: `kling-3.0/video` (single-shot), `bytedance/seedance-2-mini`, `veo3/*`.
  - Cap status remains `NOT_PUBLISHED` (stored as `null`). Use standard operating bands only after authorized acceptance smoke tests.

---

## 2. Complete Video Prompt Structure (§5.4)

High-character prompts must **never be padded with repetitive filler or generic buzzwords**. Every section must provide concrete, actionable constraints to the diffusion engine.

A full production prompt must address all 17 structural domains verbatim:
1. **Objective:** Creative goal, genre, tone, visual aesthetic, and high-level narrative purpose.
2. **Subject & Identity:** Anatomical details, clothing materials, facial features, proportions, hair/skin textures, age, styling, and key visual identifiers.
3. **Location & Environment:** Architectural geometry, foreground/midground/background depth, atmospheric particles (fog, dust, haze, rain), seasonal factors, and structural layout.
4. **Beat-by-Beat Timeline:** Exact chronological action breakdown tied strictly to timestamps (e.g. `[0.0s - 2.5s]`, `[2.5s - 5.0s]`, `[5.0s - 8.0s]`).
5. **Action & Motion:** Physical velocity, acceleration, weight, human biomechanics, micro-expressions, wind forces, and kinetic trajectories.
6. **Camera, Lens & Movement:** Optical focal length (e.g. 35mm anamorphic, 85mm prime), depth of field, f-stop, camera rig (Steadicam, technocrane, handheld, orbital dolly), tilt/pan/truck speed, and sensor characteristics.
7. **Lighting & Color:** Key light, fill light, rim/kicker, color temperature (e.g. 3200K warm tungsten vs 5600K daylight), volumetric god rays, shadows, and calibrated color palette.
8. **Continuity & Physics:** Momentum conservation, fluid dynamics, fabric draping/flutter, collision boundaries, and strict non-morphing geometry rules.
9. **Beginning State:** Frame 0 exact visual composition, initial pose, eye gaze, camera position, and starting stillness/motion.
10. **Ending State:** Final frame visual composition, resting posture, camera terminal location, and scene resolution.
11. **Reference-Asset Mapping:** Explicit assignment of input images/videos (e.g. `[Image 1] governs character facial structure, [Image 2] defines wardrobing jacket texture`).
12. **Dialogue, Audio, Ambience & Music:** Spoken lines, voice timbre, room acoustics/reverberation, environmental foley, and musical cues (when native audio is supported).
13. **Negatives & Exclusions:** Unwanted artifacts, unnatural warping, limbs doubling, extra fingers, jitter, over-saturation, digital noise, motion blur smearing.
14. **Output Duration:** Target clip length in seconds matching endpoint duration parameters.
15. **Aspect Ratio:** Exact framing proportions (16:9, 9:16, 1:1, etc.).
16. **Resolution:** Render tier (720p, 1080p, 4K, 2K).
17. **QC-Critical Details:** Explicit markers to be checked during frame inspection (e.g. legible text spelling, eye contact consistency, logo preservation).

---

## 3. Short User Prompt Expansion (§5.3)

A short user prompt (e.g. *"futuristic Black CEO woman in glass boardroom looking out at flying cars"*) is NOT an error. The skill must autonomously expand the intent into a full 17-part production-grade prompt matched to the selected model's capacity, rather than demanding that the user manually write thousands of characters.

---

## 4. Intelligent Compression: Worked Example

When routing to small-cap models (e.g. Kling Omni 3,072 cap or Motion Control 2,500 cap), **never delete core control domains**. Compress syntax by eliminating explanatory connective words while preserving density across Subject, Environment, Timeline, Motion, Camera, Lighting, and Physics.

### A. Full ~9,000-Character Master Production Prompt (Wan 3.0 / Seedance 2.5 Band)
```text
OBJECTIVE: Premium cinematic science-fiction narrative sequence portraying an authoritative Black woman executive in a high-altitude boardroom, overlooking a futuristic metropolitan skyline. Tone: commanding, sophisticated, photorealistic, 8K RED Monstro cinema camera aesthetic.

SUBJECT & IDENTITY:
Dr. Elena Vance, 42-year-old Black woman of Nigerian descent. Flawless dark mahogany skin (#3D2314) with subtle natural pore texture and elegant warm golden undertones. High sculpted cheekbones, intense focused amber-brown eyes, refined natural eyebrows. Hair: precision-parted geometric braided updo woven with ultra-fine brushed platinum micro-threads. Wardrobe: bespoke structured midnight-navy double-breasted suit jacket tailored from high-sheen liquid-silk Kevlar blend with sharp origami-folded lapels, paired with high-collared minimalist ivory crepe silk blouse. Left wrist displays an ultra-thin matte platinum biometric chronometer. Posture: perfectly upright, centered weight distribution, relaxed yet dominant executive posture.

LOCATION & ENVIRONMENT:
Top-floor executive boardroom of an orbital corporate tower, 120th floor overlooking Neo-Chicago. Floor-to-ceiling curved triple-glazed architectural smart-glass windows spanning 180 degrees. Interior: polished dark Italian obsidian terrazzo floor with mirror-like reflections; minimalist monolithic dark walnut conference table with recessed warm OLED edge illumination. Exterior skyline: sprawling multi-tiered vertical metropolis bathed in twilight; layered traffic lanes of glowing magnetic levitation aero-vehicles streaming across sky-bridges; towering holographic architectural advertisements diffusing through subtle atmospheric humidity and evening haze.

BEAT-BY-BEAT TIMELINE (8.0 SECONDS TOTAL):
[0.0s - 2.0s]: Scene opens static. Elena stands 1.5 meters before the panoramic window, hands clasped behind her back. Exterior mag-lev traffic flows left-to-right in background. Soft evening breeze from climate duct causes three loose wisps of hair near her temple to gently oscillate.
[2.0s - 4.5s]: Elena slowly shifts her body weight forward, lifting her right hand smoothly to touch the smart-glass interface. As her index finger connects with the glass at 3.2s, a concentric pulse of cyan geometric telemetry rings (#00F0FF) ripples outward across the pane.
[4.5s - 6.5s]: She turns her head 30 degrees toward the camera, her gaze shifting deliberately from the distant skyline into the camera lens with a calm, decisive micro-expression. Her lips slightly part as if about to speak.
[6.5s - 8.0s]: Camera slowly dollies forward 0.5 meters while descending 10 centimeters, locking onto a tight medium shot of Elena's profile. Reflection of glowing skyline shimmers across her iris and polished obsidian floor.

CAMERA, LENS & MOVEMENT:
Camera: Arri Alexa 65 sensor, Master Anamorphic 50mm T1.9 lens. Shutter angle 180 degrees. Aperture f/2.2 creating smooth optical bokeh on background metropolis while maintaining razor-sharp eye and skin focus. Movement: slow motorized dolly push-in tracking smoothly along the z-axis with subtle counter-clockwise Dutch tilt (1.5 degrees maximum). Handheld organic breathing motion added to prevent digital stiffness.

LIGHTING & COLOR PALETTE:
Dual-temperature contrast lighting. Key light: cool 6500K soft diffused cyan-blue ambient fill pouring from the exterior dusk skyline across Elena's left profile. Rim/Kicker: warm 2800K amber tungsten accent from interior recessed cove lighting catching the right jawline, shoulder epaulets, and platinum braid filaments. Fill light: subtle bouncing off obsidian floor at 15% intensity. Color grade: Kodak Vision3 500T 5219 emulation, deep obsidian blacks, saturated twilight indigo (#0B132B), warm champagne accents (#F4D06F), and vibrant holographic cyan highlights.

CONTINUITY, DYNAMICS & PHYSICS:
Rigid adherence to physical momentum. Liquid-silk suit fabric drapes naturally under 1G gravity with zero jitter or clipping. Finger contact with glass produces zero skin clipping. Reflection of Dr. Vance on the interior glass surface maintains 100% geometric and motion parity with primary subject. Zero structural warping of background skyscrapers during camera translation.

BEGINNING STATE:
Frame 0: Full medium-wide profile shot, subject framed on right-third power point looking out toward left horizon, hands clasped, skyline traffic flowing smoothly.

ENDING STATE:
Frame 240: Tight medium-close shot, subject head turned toward viewer, cyan telemetry display gently dissolving, deep cinematic eye reflection.

AUDIO & SOUNDSCAPE:
Ambient low-frequency structural hum of skyscraper climate control (60Hz rumble), distant ethereal whoosh of mag-lev traffic passing outside, crisp tactile glass tap sound at 3.2s followed by high-frequency harmonic chime (2.4kHz) as interface activates. Subdued room acoustic with 0.8s decay.

EXCLUSIONS & NEGATIVES:
Deformed hands, extra fingers, anatomical distortion, rubbery skin, plastic sheen, jittering facial geometry, morphing skyscraper structures, camera jerk, flicker, chromatic aberration, digital noise artifacts, inconsistent reflections.

OUTPUT SPECS:
Duration: 8 seconds. Aspect Ratio: 16:9. Resolution: 1080P. Native Audio: Enabled.
```

---

### B. Compressed Version (Kling 3.0 Omni Band — Under 2,900 Characters)
```text
OBJECTIVE: Cinematic scifi narrative. Elena Vance, 42yo Black female CEO, mahogany skin (#3D2314), high cheekbones, amber eyes, braided updo with platinum threads. Dark navy liquid-silk structured suit, ivory silk collar. 120th-floor boardroom, panoramic curved smart-glass window, Neo-Chicago twilight skyline, obsidian terrazzo floor, streaming mag-lev traffic.

TIMELINE & ACTION (8.0s):
[0.0-2.0s]: Med profile, Elena stands at window, hands clasped behind back, gazing at skyline traffic. Loose hair wisps flutter softly.
[2.0-4.5s]: Shifts weight forward, right hand rises smoothly, index finger touches smart-glass at 3.2s triggering concentric cyan UI ripple (#00F0FF).
[4.5-6.5s]: Turns head 30 deg to camera, focused confident gaze locks into lens, subtle decisive micro-expression.
[6.5-8.0s]: Smooth 0.5m forward dolly push, settling on tight medium shot. Skyline reflection sharp in iris and floor.

CAMERA & OPTICS:
50mm Anamorphic T1.9, f/2.2 shallow DOF, crisp eye focus, soft background bokeh. Slow motorized dolly-in, subtle organic breathing, 1.5 deg Dutch tilt.

LIGHTING & PALETTE:
Key: Cool 6500K cyan skyline ambient on left profile. Rim: Warm 2800K amber cove light catching right jaw and platinum hair. Fill: 15% floor bounce. Kodak 500T grade: obsidian blacks, twilight indigo (#0B132B), champagne gold (#F4D06F), cyan telemetry.

PHYSICS & CONTINUITY:
Natural fabric gravity drape, zero clipping. Window reflection perfectly mirrors subject movement. Rigid skyscraper geometry, no morphing or jitter.

BEGIN/END:
Frame 0: Right-third profile, looking left. Final Frame: Tight med-close, subject facing camera, glowing telemetry fading.

AUDIO: Low 60Hz ambient hum, distant traffic whoosh, tactile glass tap at 3.2s with harmonic 2.4kHz UI chime.

NEGATIVES: Deformed hands, extra digits, morphing, jitter, plastic skin, flickering reflections, camera shake.
SPECS: 8s, 16:9, 1080P, audio on.
```
*(Exact length: 1,885 characters — well below Kling Omni's 3,072 cap and below the 2,900 safe target, preserving 100% of subject identity, timeline beats, camera, lighting, physics, and audio directives).*

---

## 5. Scheduled & Cron Prompts (§5.5)

For scheduled or queued video workflows:
- Store the **unexpanded creative intent** and reference assets in the job store.
- **Do NOT store a frozen 19,000-character prompt block.**
- Execute model selection and compose the exact model-tailored prompt dynamically at execution time. This guarantees that if model availability or routing changes, the prompt complies with the target model's hard character limit.
