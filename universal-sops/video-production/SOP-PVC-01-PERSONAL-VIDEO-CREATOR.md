# Personal Video Creator SOP (v2.0 — Hardened)

**Document type:** AI-facing Standard Operating Procedure
**Primary executor:** OpenClaw agent, ChatGPT agent, or another tool-using AI agent
**Version:** 2.0 (hardened)
**Base version:** 1.0 (Verified July 23, 2026)
**Re-verified:** July 23, 2026
**Owning department:** `video` (Director of Video / Head of Video Production)
**SOP cluster:** `universal-sops/video-production/`
**Canonical machine spine:** `47-movie-producer/` (DMAIC driver) + `63-agnes-image/` + `64-agnes-video/` + `30-fish-audio-api-reference/`
**Persona hints (persona-selector-v2.py `sops.persona_hints`):** `vsevolod-pudovkin-film-technique`, `thorne-youtube-unlocked`, `video-funnels`
**Purpose:** Create polished videos featuring a consenting person's likeness and Fish Audio voice while preventing lip-sync drift, identity inconsistency, broken scene transitions, mismatched durations, and poor audio mixing.

> **What changed in v2.0.** Every QC gate now has a measurable pass/fail number or a probe script. Every critical tool has a fallback hierarchy and an error-recovery ladder. Credentials are SecretRef-only (never hardcoded). The 5,000–19,000 stripped-char image-prompt band is enforced on every likeness/reference prompt. Research-backed identity-preservation, lip-sync-input, and motion-policy best practices are folded into each phase. A Command Center integration section routes the job to the `video` department card. Nothing in this SOP may be satisfied by "the agent will figure it out" — if a step cannot be automated, it names the exact human attestation required.

---

## 0. Master Directive to the AI Executor

You are the production agent responsible for completing this workflow from project intake through final quality control.

Follow these rules without exception:

1. **The final narration is the master timeline.**
2. Create the script first, then create one continuous master narration in Fish Audio.
3. Divide the narration into scene segments only after the master audio has been generated.
4. Create Agnes videos to fit the narration segments. Do not force narration into arbitrary 15-second video blocks.
5. Never assume that matching the video duration to the audio creates lip sync.
6. Every visible talking-head segment must pass through a dedicated lip-sync process unless the source video was already generated from the exact final audio by a verified audio-driven avatar model.
7. FFmpeg is the assembly, conversion, timing, caption, and mixing layer. FFmpeg is not a generative lip-sync engine.
8. Do not lip-sync B-roll, product footage, text screens, screenshots, scenery, or shots where the speaker's mouth is not visible.
9. Do not merge all scenes before lip-syncing. Lip-sync and approve each talking-head scene separately.
10. Preserve the original continuous Fish Audio narration as the authoritative final voice track.
11. Log all prompts, model names, seeds, file paths, durations, retries, and QC decisions.
12. Never expose API keys, tokens, voice IDs, private likeness assets, or temporary signed URLs in a public file or final deliverable. All credentials resolve through SecretRef (see §3.3) — never hardcoded, never in prompts, filenames, logs, or Git.
13. Do not use a person's likeness or cloned voice without documented authorization.
14. Do not mark the job complete until all acceptance gates in this SOP pass.
15. **A rule not auto-failed at a gate does not exist.** Wherever this SOP names a probe script (`universal-sops/video-production/scripts/*.py`), run it and treat a non-zero exit as a HARD STOP. A self-attested "looks good" never substitutes for a probe pass.

When a tool, skill, connector, or model is unavailable, do not silently skip the stage. Use the fallback hierarchy in this document and record the substitution in `00_admin/production_log.md`.

---

# 1. Supported Production Stack

This SOP is designed around the following stack. Each capability lists a **primary** and an ordered **fallback hierarchy** (see §34 for the consolidated fallback table).

## 1.1 Required capabilities

- **Script and orchestration**
  - Primary: OpenClaw
  - Fallback 1: ChatGPT
  - Fallback 2: Another AI agent capable of reading/writing files and calling tools

- **Likeness image creation or editing**
  - Primary: GPT Image 2 (`gpt-image-2`) in ChatGPT or the OpenAI API
  - Fallback 1: Agnes Image 2.1 Flash (`agnes-image-2.1-flash`) in image-to-image mode
  - Fallback 2: Kie.ai/Kai.ai image-generation access
  - Fallback 3: Another image model that supports high-fidelity image-to-image identity preservation
  - **Rule:** always image-to-image from an authorized reference photograph; never rebuild a face from text when a reference exists.

- **Video generation**
  - Primary: Agnes Video V2.0 — Model ID `agnes-video-v2.0`
  - Fallback (only if Agnes is down and the client approves a substitute in writing): Kie `gemini-omni-video` default / `veo3_fast` fallback via Skill 47. Record the substitution. Do **not** silently swap to a native provider — the Movie Producer provider-audit gate (`AF-VID-PROVIDER-AUDIT`) requires Kie-only sovereignty on client boxes.

- **Voice generation**
  - Primary: Fish Audio S2.1-Pro — production model ID `s2.1-pro`
  - Fallback 1 (development / cost): `s2.1-pro-free`
  - Fallback 2 (provider down): ElevenLabs or the client's configured TTS via Skill 30 — record substitution; re-run the full audio QC gate (§10.4) because cadence and timestamps change.

- **Lip-sync correction**
  - Preferred managed default: Sync Labs `lipsync-2-pro`
  - Premium escalation: Sync Labs `sync-3`
  - Standard-cost fallback: Sync Labs `lipsync-2`
  - Self-hosted fallback: MuseTalk 1.5 or another approved audio-driven lip-sync model (see §15.2 environment caveat)

- **Media processing**
  - FFmpeg, FFprobe (mandatory; verify with `ffmpeg -version` and `ffprobe -version` at intake)

- **Optional music**
  - Suno or another properly licensed music-generation service; normally instrumental.

## 1.2 Verified current model notes

### Agnes Video V2.0

Supports text-to-video, image-to-video, and keyframe workflows.

- Maximum `num_frames`: `441`
- `num_frames` must follow the `8n + 1` rule
- Supported `frame_rate`: `1-60`
- Duration formula: `duration_seconds = num_frames / frame_rate`
- At 24 fps: `441 / 24 = 18.375 seconds` — the API-level maximum.

**Production policy (research-backed).** State-of-the-art talking-head models accumulate identity drift and expression flattening on long single generations; the reliable natural-motion window is short. Target **6–12 seconds** per talking-head scene. Permit **12–15 seconds** when the sentence and performance justify it. Use **15–18.375 seconds** only after confirming the exact interface accepts it and the shot is simple, frontal, and stable. A specific Agnes skill, interface, or wrapper may expose a 15-second preset; always treat the returned `seconds`, `size`, and normalized metadata as the source of truth.

### Agnes Image 2.1 Flash — model ID `agnes-image-2.1-flash`

Supports text-to-image and image-to-image. Use image-to-image mode when preserving a specific person's appearance.

### GPT Image 2 — API model ID `gpt-image-2`

Use image editing or high-fidelity image inputs to preserve identity. Do not rebuild the face from a text description when an authorized reference photograph is available. GPT-image is prone to identity drift across iterative edits (research, §35.5) — regenerate from the original reference at low variation strength rather than editing an edit.

### Fish Audio S2.1-Pro — production model ID `s2.1-pro`

Accepts natural-language performance directions in square brackets, e.g. `[calm and confident]`, `[brief thoughtful pause]`, `[laughs warmly]`. Not limited to a fixed emotion-tag vocabulary. Keep directions concise and internally consistent; use no more than three combined performance directions in one sentence unless a test proves the voice remains natural.

---

# 2. Non-Negotiable Production Principle

## 2.1 The correct dependency order

```text
PROJECT BRIEF
    ↓
SCRIPT
    ↓
ONE CONTINUOUS FISH AUDIO MASTER
    ↓
TIMESTAMPS + AUDIO-LED STORYBOARD
    ↓
LIKENESS REFERENCE IMAGES
    ↓
SEGMENTED AGNES VIDEO GENERATION
    ↓
SCENE-BY-SCENE LIP-SYNC CORRECTION
    ↓
SCENE QC
    ↓
FFMPEG ASSEMBLY ON THE MASTER AUDIO TIMELINE
    ↓
B-ROLL + CAPTIONS + MUSIC
    ↓
FINAL TECHNICAL AND CREATIVE QC
```

## 2.2 Why the audio must come first

Speech determines the exact duration, word/phoneme timing, breaths, sentence endings, emotional changes, cut locations, caption timing, music transitions, and where B-roll should cover difficult visual moments.

Agnes can create a person who appears to speak, but Agnes Video V2.0 does not use the Fish Audio narration as a documented phoneme-driving input. A 10-second Agnes clip plus a separate 10-second Fish Audio clip does **not** make the mouth movements correspond to the words. The video must be generated to fit the audio timeline and then corrected by an audio-driven lip-sync model.

## 2.3 What FFmpeg can and cannot do

FFmpeg **can**: inspect media, split audio, trim clips, normalize frame rates, scale/pad video, reset timestamps, join scenes, replace/remove audio, mix voice and music, burn captions, encode final files.

FFmpeg **cannot**: infer spoken phonemes and redraw the lips, correct wrong mouth shapes, create matching teeth/tongue positions, preserve identity through generative video, or repair a completely wrong facial performance.

Do not attempt to solve generative lip-sync errors using only `-itsoffset`, `adelay`, `setpts`, `atempo`, or video stretching. Those align start times but cannot fix incorrect mouth formation.

---

# 3. Ethics, Consent, Rights, and Security Gate

Before producing any likeness or cloned voice, create `00_admin/CONSENT.md` (or a project record) confirming:

- Subject's full name
- Subject authorized use of their likeness
- Subject authorized voice cloning or use of their Fish Audio voice model
- Intended platforms and campaign
- Commercial or non-commercial use
- Approval expiration, if any
- Prohibited topics or contexts
- Whether the subject must approve each final video
- Who owns the source photos, voice recordings, scripts, and final output

**Enforcement:** `scripts/probe_consent.py` (in the cluster) parses `00_admin/CONSENT.md` / `project_manifest.yaml` and HARD-FAILS (`AF-PVC-CONSENT`) unless `consent_verified: true` AND likeness + voice authorization are both present. No generation call may precede this pass.

## 3.1 Hard stop conditions

Stop the workflow and request authorized input when: the subject did not consent; the source image was scraped, stolen, or taken from an unapproved account; the voice model belongs to another person; the project impersonates a public figure or private individual without authorization; the content falsely represents the subject's statements, endorsements, actions, or location; the content is deceptive, fraudulent, defamatory, or intended to bypass identity controls; or the project asks the AI to hide that the video is synthetic where disclosure is legally or contractually required.

## 3.2 Asset security (expanded per repo standards)

- Store likeness and voice files in a private project directory (`01_likeness/`, `03_audio/`) outside any Git working tree.
- Never place secrets in prompts, filenames, logs, or Git repositories.
- **Never commit `.env` files.** Confirm `.gitignore` covers `.env`, `*.secret`, `01_likeness/source_photos/`, and `03_audio/*_raw.wav` before any commit.
- Redact signed URLs before sharing logs (replace with `[REDACTED_SIGNED_URL]`).
- Delete temporary public image URLs after the project if the provider permits it.
- Preserve the final consent record with the deliverable.
- Likeness/voice assets are **client data**: do not copy them into shared skill folders, do not embed them in examples, and do not reuse them across projects.

## 3.3 Credential / API handling (SecretRef — repo standard)

All credentials resolve through a **SecretRef** — the triple `{ source, provider, id }` — never an inlined value. This mirrors the repo's podcast/anthology webhook standard (`universal-sops/podcast-craft/SOP-PODCAST-02-CLIENT-ONBOARDING.md`).

| Secret | Env label | Purpose |
|---|---|---|
| Fish Audio API key | `FISH_AUDIO_API_KEY` | Voice master + timestamps |
| OpenAI / GPT-image key | `OPENAI_API_KEY` | Likeness reference images |
| Agnes / Kie key | `KIE_API_KEY` (client box) | Agnes image + video generation |
| Sync Labs key | `SYNC_LABS_API_KEY` | Lip-sync correction |
| Suno credential | `SUNO_CREDENTIAL` | Optional music |
| Fish voice model ID | `FISH_VOICE_REFERENCE_ID` | Cloned/approved voice (treat as secret) |

Rules:

1. Store each secret in the client env store or a `0600` secrets file (`~/.openclaw/secrets/<name>.secret`, mode 0600, owned by the runtime user). Verify SET in the **live process environment**, not just in a file.
2. Reference by `${ENV_LABEL}` in any config; the runtime resolves it. The plaintext value transits **no chat, no document, no repo, no log.**
3. In `project_manifest.yaml`, write `fish_reference_id: "STORE_AS_SECRET_REFERENCE"` and resolve the real ID from `FISH_VOICE_REFERENCE_ID` at call time.
4. `scripts/probe_no_secrets.py` scans the project tree (prompts, manifests, logs) for accidental secret/URL leakage and HARD-FAILS (`AF-PVC-SECRET-LEAK`) on any hit.

---

# 4. Project Folder and Naming Standard

Create this structure before generation (identical to v1.0 — `00_admin/` … `12_delivery/`). The full tree is preserved in the cluster README. Naming pattern:

```text
scene_###_<type>_<status>_v##.<ext>
```

Examples: `scene_001_talking_raw_v01.mp4`, `scene_001_talking_lipsync_v02.mp4`, `scene_001_talking_approved_v02.mp4`, `scene_004_broll_approved_v01.mp4`. Do not overwrite prior generations — increment the version number.

---

# 5. Create the Project Manifest

Create `00_admin/project_manifest.yaml` before writing the script. In addition to the v1.0 fields, v2.0 adds the highlighted blocks:

```yaml
project:
  id: "PVC-YYYYMMDD-CLIENT-SLUG"
  title: ""
  subject_name: ""
  consent_verified: false          # probe_consent.py HARD gate
  intended_use: ""
  target_platforms: ["Instagram Reels"]
  orientation: "9:16"
  width: 1080
  height: 1920
  fps: 24
  target_duration_seconds: 60
  language: "en-US"

models:
  script_model: ""
  image_provider: "gpt-image-2|agnes-image-2.1-flash|kie-ai|other"
  video_model: "agnes-video-v2.0"
  voice_model: "s2.1-pro"
  lip_sync_model_default: "lipsync-2-pro"
  lip_sync_model_escalation: "sync-3"
  music_provider: "suno|none|other"

# v2.0 — fallback hierarchies recorded so a substitution is explicit, never silent
fallbacks:
  image: ["gpt-image-2", "agnes-image-2.1-flash", "kie-ai"]
  video: ["agnes-video-v2.0", "kie-gemini-omni-video", "kie-veo3_fast"]
  voice: ["s2.1-pro", "s2.1-pro-free", "elevenlabs"]
  lip_sync: ["lipsync-2-pro", "sync-3", "lipsync-2", "musetalk-1.5"]
  substitutions_used: []            # append {capability, from, to, reason, approved_by}

voice:
  fish_reference_id: "STORE_AS_SECRET_REFERENCE"   # resolved from FISH_VOICE_REFERENCE_ID
  speed: 1.0
  volume_adjustment: 0
  temperature: 0.65
  top_p: 0.7
  output_format: "wav"
  sample_rate: 48000

production_limits:
  agnes_max_frames: 441
  agnes_fps: 24
  agnes_api_max_seconds_at_24fps: 18.375
  preferred_talking_scene_seconds_min: 6
  preferred_talking_scene_seconds_max: 12
  normal_hard_scene_cap_seconds: 15
  lip_sync_tolerance_frames: 2
  max_generation_attempts_per_scene: 3

audio_targets:
  final_integrated_lufs: -16
  final_true_peak_db: -1.5
  music_ducking_db_range: "8-12"

# v2.0 — Command Center routing
command_center:
  department_slug: "video"
  card_campaign: "PVC-YYYYMMDD-CLIENT-SLUG"
  approval_authority: "head-of-video-production"   # Rule-Zero + final sign-off

status:
  script_approved: false
  audio_approved: false
  storyboard_approved: false
  picture_lock: false
  final_qc_passed: false
```

The AI must update the status fields as gates pass. `scripts/probe_manifest.py` validates required fields and the SecretRef discipline (`AF-PVC-MANIFEST`).

---

# 6. Phase One: Project Intake

Create `00_admin/project_brief.md` capturing the 18 v1.0 items (goal, audience, CTA, length, platform, orientation, brand colors, wardrobe, background, tone, required words/names/URLs/offers, forbidden claims, required disclosures, B-roll, music, captions, deadline, final approver).

**Preflight probe:** `scripts/probe_environment.py` verifies `ffmpeg`/`ffprobe` on PATH, confirms each required SecretRef resolves in the live environment, and confirms `.gitignore` covers the private asset dirs. Exit non-zero = `AF-PVC-ENV` HARD STOP before any paid call.

## 6.1 Default platform settings

Vertical 9:16 `1080x1920`, landscape 16:9 `1920x1080`, square 1:1 `1080x1080` — all `fps: 24`, `H.264`, `yuv420p`, `AAC`, `48000` Hz. Do not mix orientations inside one project unless the final design intentionally places one format inside another.

---

# 7. Phase Two: Build the Likeness Reference System (research-hardened)

The likeness reference is the visual anchor for every talking-head scene. Identity consistency across clips is the #1 failure mode in multi-scene AI video (research §35.1, §35.4); the reference system is the primary control.

## 7.1 Source photo requirements

Prefer 3–8 authorized photographs: high resolution; face fully visible; neutral/natural expression; even lighting; no beauty filters; no sunglasses; no hand covering the mouth; minimal motion blur; multiple angles including front and slight three-quarter; current hairstyle and facial hair; accurate skin tone; clear teeth if the person often smiles; wardrobe references when consistency matters.

Reject source images with: heavy compression; extreme wide-angle distortion; strong shadow across the mouth; deep profile as the only reference; another person's face in frame; watermarks; face-altering filters; cropped chin; obstructed lips.

**Research note (§35.1):** a single reference is the weakest configuration. Provide a front + both three-quarters so the model has a multi-view identity anchor; this measurably reduces cross-scene drift versus a single portrait.

## 7.2 Create an identity bible

Create `01_likeness/identity_bible.md` recording immutable facial characteristics (face shape, skin tone, eye shape/color, nose, lips, smile, teeth, eyebrows, hair, facial hair, age range), wardrobe, accessories, camera defaults (framing, lens feel, camera height, eye line, background, lighting), and identity-failure indicators. The identity bible is the **single source of truth** every prompt is built from.

## 7.3 Create the master talking-head reference — 5,000–19,000-char prompt band

**MANDATORY (repo standard, from the Agnes/GPT-image prompt-band fix):** every likeness/reference image prompt — GPT-image-2 or Agnes image-to-image — MUST clear the **5,000–19,000 stripped-character band** before it is sent to the image provider. This is the same two-floor gate the Graphics/Sales-Page/Avatar skills enforce (`prove_sp_prompt_floor.py`). A short prompt cannot carry the identity specificity needed to prevent face drift.

**Enforcement:** `scripts/probe_prompt_band.py` measures the stripped length of every prompt in `01_likeness/*/prompt.txt` (and the Agnes/GPT-image prompt ledgers) and HARD-FAILS:
- `AF-PVC-PROMPT-FLOOR` if `< 5,000` stripped chars
- `AF-PVC-PROMPT-CEILING` if `> 19,000` stripped chars
- `AF-PVC-PROMPT-IDENTITY` if the identity-anchor + negative blocks are missing

The templates below are **scaffolds**. Each `[BRACKET]` is filled from the identity bible, and the prompt is then expanded with the subject's specific, non-repeating identity detail until it clears 5,000 stripped chars. Padding by repeating one paragraph is caught by the distinct-words density floor in the probe.

### GPT Image 2 reference prompt template (expand to ≥ 5,000 stripped chars)

```text
Use the supplied authorized reference images as the IDENTITY SOURCE and treat
identity preservation as the single most important instruction in this prompt.

Create a photorealistic vertical 9:16 medium close-up of the SAME person.
Preserve the person's EXACT facial identity, skin tone, age, hairstyle,
hairline, facial hair, eye shape, eye color, nose, lips, teeth, and body
proportions. [IDENTITY BIBLE DUMP: face shape, exact skin tone description,
eye shape and color, nose structure, lip shape, smile characteristics, teeth
shape and alignment, eyebrow shape and density, hair color/style/length,
facial hair description, age range to preserve — write each as its own
detailed clause so the prompt carries the subject's real, non-generic detail.]

The person is centered, facing the camera, with the mouth fully visible.
Use soft professional key lighting, natural skin texture with visible pores,
realistic eyes with accurate catchlights, a clean [BACKGROUND DESCRIPTION],
and [WARDROBE from the identity bible].

Framing: chest-up, camera at eye level, moderate lens perspective, no
wide-angle facial distortion. Expression: calm, alert, approachable.

IDENTITY ANCHOR: this is the same individual as the reference photographs.
Do not change identity. Do not beautify into a different person. Do not alter
age, ethnicity, facial proportions, teeth, hairline, facial hair, or skin tone.
Match the reference face geometry, not a generic attractive face.

NEGATIVE BLOCK: Do not produce a different person, identity drift, face morph,
swapped face, altered features, new hair, different eyes, changed nose,
different mouth, skin-tone change, age change, asymmetric eyes, crossed eyes,
beauty-filter skin, plastic skin, warped face, deformed mouth, text, watermark,
extra people, obstructed mouth, distorted hands, or an exaggerated smile.
```

### Agnes Image 2.1 Flash reference prompt template (expand to ≥ 5,000 stripped chars)

```text
Image-to-image edit using the supplied reference image as the IDENTITY SOURCE.

Preserve the original subject's identity and facial structure EXACTLY.
Create a [9:16 / 16:9 / 1:1] photorealistic professional talking-head frame.
The subject faces the camera with visible lips, natural expression, eye-level
camera, stable lighting, [WARDROBE], and [BACKGROUND].

Keep the subject's face, skin tone, hairstyle, facial hair, eyes, nose, mouth,
age, and proportions unchanged. [IDENTITY BIBLE DUMP — every immutable
characteristic as its own clause.] Preserve composition consistency across the
frame.

IDENTITY ANCHOR: same individual as the reference; match reference face
geometry, not a generic face.

NEGATIVE BLOCK: Do not allow face drift, beauty-filter skin, asymmetrical eyes,
changed teeth, changed hairline, identity change, different person, face morph,
altered features, text, watermark, extra people, or mouth obstruction.
```

## 7.4 Reference approval gate (measurable)

The master reference must pass **all** of: identity similarity to the authorized subject (human-attested side-by-side); accurate skin tone; accurate hair and facial hair; mouth visible; no facial distortion; correct orientation; correct framing; no unwanted text; no extra people; no accessories that complicate mouth tracking. `scripts/probe_reference_image.py` validates orientation/resolution/framing from the file; identity similarity is a named human attestation recorded in `11_qc/scene_qc.csv`. If the face is not clearly the authorized subject, reject it — do not proceed to video.

## 7.5 Create controlled reference variants

Create only the variants the storyboard needs: front-facing neutral; front-facing warm smile; slight three-quarter left; slight three-quarter right; alternate wardrobe only when the storyboard calls for it; B-roll pose/environment. Every new outfit, background, lens, and angle increases continuity risk (research §35.4) — minimize variants.

---

# 8. Phase Three: Write the Script

## 8.1 Script length

Default professional delivery range: **135–150 spoken words per minute.** Planning targets: 15s→32–38 words, 30s→65–75, 45s→100–112, 60s→135–150, 90s→200–225. These are planning targets; the generated Fish Audio duration is the final authority.

## 8.2 Write for speech, not for reading

Short sentences; contractions where natural; avoid dense lists; one idea per sentence; punctuation that supports breathing; spell out unusual acronyms; pronunciation notes for names; avoid long spoken URLs; avoid tongue-twister clusters; avoid multiple difficult proper nouns in one line; strongest line early; end with one clear action.

## 8.3 Mark visual intent

Use `[TALKING HEAD]`, `[B-ROLL: …]`, `[ON-SCREEN TEXT]` labels in the draft. These labels are removed from the Fish Audio narration unless meant to be spoken.

## 8.4 Create a pronunciation dictionary (model-compatibility notes)

Create `02_script/pronunciation_dictionary.yaml`:

```yaml
BlackCEO:   { spoken_as: "Black C E O" }
FFmpeg:     { spoken_as: "F F m peg" }
Agnes:      { spoken_as: "AG-ness" }
client_name: { spoken_as: "" }
```

**Model-compatibility notes (v2.0):**
- Fish Audio S2.1-Pro reads phonetic respelling in the Fish-tagged script; keep the correctly spelled version in captions.
- If a word is repeatedly mispronounced, prefer a phonetic spelling that preserves syllable stress (e.g. `AG-ness`), not just letter separation.
- Do not place a strong emotional Fish tag immediately before a difficult proper noun (the model may distort the name).
- Test any dictionary entry in isolation before committing it to the full master.

---

# 9. Phase Four: Add Fish Audio Performance Directions

Create `02_script/script_fish_tagged.md`; keep a clean version separately.

## 9.1 Fish Audio S2.1-Pro tag syntax

Square brackets: `[calm, confident, and conversational]`, `[brief pause]`, `[laughs lightly]`. Do not use legacy S1-style parentheses unless the actual model is S1.

## 9.2 Recommended performance direction library

(Professional authority, Excitement, Empathy, Urgency, Reflection, Emphasis, Human reactions — the v1.0 library is preserved verbatim in the cluster file.)

## 9.3 Tagging rules

1. Set a base delivery at the beginning. 2. Change performance only where meaning changes. 3. Do not tag every sentence. 4. Do not stack conflicting directions. 5. Avoid stage directions the voice model might speak literally. 6. Keep laughter/gasps/sighs rare. 7. Keep strong emotional changes away from difficult proper nouns. 8. Use punctuation together with tags. 9. No more than three combined emotion/performance directions per sentence. 10. Regenerate if tags create slurred words, exaggerated breaths, or unnatural pitch changes.

## 9.5 Fish generation settings

```yaml
model: "s2.1-pro"
format: "wav"
sample_rate: 48000
temperature: 0.60-0.70
top_p: 0.70
speed: 1.0
normalize: true
latency: "normal"
```

Lower temperature for steadier corporate narration; raise only when too flat; keep speed near 1.0; edit the script before resorting to speed changes; never time-stretch a final voice more than a few percent without listening for artifacts.

---

# 10. Phase Five: Generate One Continuous Fish Audio Master

## 10.1 Mandatory rule

Generate the full narration as one continuous file (`03_audio/fish_master_raw.wav`) whenever the service permits. Do not generate one unrelated clip per scene unless the narration is intentionally episodic or a service limit forces segmentation.

## 10.2 Use timestamps

Use Fish Audio's timestamped TTS; save `03_audio/fish_timestamps.json` and `03_audio/fish_alignment.csv` (word, start, end, sentence, segment, confidence, absolute offset).

## 10.3 Reconstructing timestamped streamed audio

Concatenate `audio_base64` chunks in arrival order; for each `chunk_seq` replace the prior alignment snapshot (do not append duplicates); add `chunk_audio_offset_sec` to local segment times for absolute timestamps; export one complete WAV master and one normalized alignment file.

## 10.4 Audio QC gate (measurable)

Listen to the entire narration with headphones. Reject and regenerate on any: mispronounced name, missing word, repeated phrase, slurred consonant, unexpected voice change, unnatural emotional jump, excessive breath, audible click, harsh clipping, unwanted laughter, tag spoken aloud, robotic pause, tempo too fast/slow.

**Automated checks** (`scripts/probe_audio_master.py`):
- Integrated loudness within `-16 ± 1` LUFS, true peak `<= -1.5 dBTP` (via `ffmpeg loudnorm` print or `ebur128`).
- No digital clipping (true peak never above `-1.0 dBTP` on the raw master).
- Duration within `±2%` of the target derived from the approved word count at 135–150 wpm.
- Sample rate exactly `48000`, mono or stereo as configured.

Record:

```yaml
audio_qc:
  duration_seconds: 0
  integrated_lufs: 0
  true_peak_dbtp: 0
  pronunciation_pass: false
  emotion_pass: false
  continuity_pass: false
  clipping_pass: false
  approved: false
```

## 10.5 Normalize the master voice only after approval

```bash
ffmpeg -y -i 03_audio/fish_master_raw.wav \
  -af "loudnorm=I=-16:LRA=7:TP=-1.5" -ar 48000 \
  03_audio/fish_master_qc.wav
```

For final delivery, a two-pass `loudnorm` is preferred. Normalize the continuous master or final mix — never individual scene segments separately.

---

# 11. Phase Six: Build the Audio-Led Storyboard

## 11.1 Never cut by equal time blocks

Do not auto-create `0-15 / 15-30 / 30-45 / 45-60`. Cut at sentence endings, breath pauses, intentional rhetorical pauses, topic changes, B-roll transitions, emotional transitions.

## 11.2 Scene duration policy

Talking-head — preferred `6-12s`, acceptable `10-15s`, conditional `15-18.375s` (only when the Agnes interface accepts it, the speaker stays easy to track, mouth visible, near-frontal angle, no complicated hand movement, and the sentence cannot be divided). B-roll — preferred `2-8s`; may span multiple phrases.

**Research note (§35.3):** keeping talking-head scenes in the 6–12s band is also the strongest defense against within-clip identity drift and motion repetition; long single generations flatten expression and warp the face.

## 11.3 Segment boundary algorithm

For each proposed scene: find the final word of a complete thought; find the silence/breath after it; place the cut inside the silence; keep the spoken portion below the chosen Agnes duration; add visual handles (0.15–0.30s before the first phoneme, 0.20–0.40s after the final phoneme); ensure the generated video is long enough to include handles; do not include a video hold while speech is active; do not cut on a visible plosive (P/B/M) unless the next scene begins with the same framing and continuity is intentional.

## 11.4 Scene types

`TALKING_HEAD`, `BROLL_GENERATED`, `BROLL_LICENSED`, `PRODUCT_DEMO`, `SCREEN_RECORDING`, `TEXT_CARD`, `LOGO_CARD`, `TRANSITION`, `CTA_CARD`.

## 11.5 Scene manifest template

Create `04_storyboard/scene_manifest.yaml` (v1.0 schema preserved: per-scene `id`, `order`, `type`, `audio_start/end`, `spoken_duration`, handles, `required_video_duration`, clean + fish text, `visual_summary`, `reference_image`, `agnes{model,fps,target_seconds,num_frames_requested,prompt_file,negative_prompt_file,seed}`, `lip_sync{required,model,escalation_model,audio_segment}`, `qc{...}`).

## 11.6 Agnes frame planning

`8n + 1` frames. `raw_frames = required_seconds × fps`, then round to the nearest `8n + 1`. At 24 fps: ~5s→121 (5.0417s), ~8s→193, ~10s→241, ~12s→289, ~15s→361, API max→441 (18.375s). Always inspect the returned `seconds` value — Agnes may normalize parameters. `scripts/probe_frame_plan.py` validates every scene's `num_frames_requested` satisfies `8n+1` and `<= 441`, and that `required_video_duration` covers the spoken duration plus handles (`AF-PVC-FRAMEPLAN`).

---

# 12. Phase Seven: Extract Audio Segments from the Master

The master audio remains authoritative; scene WAVs are temporary lip-sync inputs.

## 12.2 Extract a precise scene WAV

```bash
ffmpeg -y -i 03_audio/fish_master_qc.wav \
  -af "atrim=start=0.000:end=8.740,asetpts=PTS-STARTPTS" \
  -ar 48000 -ac 1 03_audio/segments/scene_001.wav
```

Do not add MP3 compression between Fish Audio and lip sync.

## 12.3 Validate extracted segment

`ffprobe` the segment; its duration must equal `audio_end - audio_start` within minimal container rounding. `scripts/probe_segment_duration.py` enforces `±0.05s` (`AF-PVC-SEGMENT-DUR`).

## 12.4 Do not destroy the master

Never rebuild the master by concatenating temporary scene WAVs unless the original master is unavailable. The final voice track comes from the original continuous master.

---

# 13. Phase Eight: Generate Agnes Talking-Head Video (research-hardened)

## 13.1 Use image-to-video for likeness work

`authorized reference image → Agnes image-to-video`. Do not rely on text-to-video to recreate a person from a name or description.

## 13.2 Talking-head prompt formula

`IDENTITY + FRAMING + SPEAKING MOTION + BODY MOTION + CAMERA + LIGHTING + BACKGROUND + STABILITY REQUIREMENTS`

## 13.3 Talking-head prompt template (research-backed motion policy baked in)

```text
Animate the supplied authorized portrait of the SAME person.

The person is speaking naturally to the camera throughout the shot, with subtle
conversational mouth movement, realistic blinking (roughly once every 4-6
seconds, varied duration), small natural head movements (amplitude about 5
degrees of pitch/yaw, never a full turn), and restrained facial expression.
The lips remain visible and unobstructed. The person maintains direct eye
contact with the camera, with natural occasional gaze micro-movements rather
than a fixed stare.

Framing: [CHEST-UP / SHOULDERS-UP], eye-level camera, stable [9:16 / 16:9]
composition. No camera shake. Lighting remains soft and consistent. Background
remains unchanged. Wardrobe, hairstyle, facial hair, skin tone, facial
proportions, eyes, nose, lips, teeth, and age remain consistent with the
reference.

Motion should be natural, controlled, and NON-REPEATING — no looped gesture,
not exaggerated. No sudden head turn, no profile view, no hand crossing the
mouth, no object covering the lower face, no extra people, no face morphing,
no wardrobe change, no background change, no text, no watermark.

The person should visibly appear to be speaking for the duration, because the
footage will be corrected to the final narration using a dedicated audio-driven
lip-sync process.
```

## 13.4 Negative prompt template

```text
identity drift, different person, face morphing, changed skin tone, changed age,
altered nose, altered lips, altered teeth, asymmetrical eyes, crossed eyes,
beauty filter, plastic skin, warped face, deformed mouth, frozen mouth, fully
closed mouth for the entire clip, exaggerated jaw, extreme head turn, profile
view, hands covering mouth, microphone blocking face, extra people, duplicate
person, flicker, frame jitter, looping repeated gesture, wardrobe change, hair
change, beard change, background change, camera shake, zoom jump, text,
subtitles, logo, watermark
```

## 13.5 Motion policy (research §35.3 — state of the art)

- Stable camera; minimal body movement; no complicated hand gestures near the face; avoid walking while speaking; avoid extreme smiles; avoid rapid turns; avoid profile views.
- Keep the face large enough for lip-sync (the face should occupy roughly 30–50% of frame height; lip-sync models need a minimum face resolution).
- Do not make the input completely frozen — include "speaking naturally" and subtle micro-motion.
- Natural head motion ≈ 5° pitch/yaw; blinks every 4–6s; non-repeating gestures. These are the strongest uncanny-valley defenses.
- 24 fps is the project standard and is acceptable for talking heads; avoid fast head turns at 24 fps (jerkiness). Do not chase 60 fps — it does not improve perceived naturalness and can highlight glitches.

## 13.6 Why the person must appear to speak

Many lip-sync models perform best when the source already contains natural speaking motion. A completely static face produces weak/generic results. The source mouth motion need not match the words, but the face should look alive and conversational.

## 13.7 Agnes task execution

Submit the task; store `task_id` and `video_id`; poll using the documented result method; record requested frames, returned duration, returned size, normalized size mapping, output URL, seed, prompt, negative prompt; download the result immediately to the project folder; do not depend on a temporary hosted URL remaining available.

## 13.8 Agnes visual QC before lip sync (measurable + human)

Reject the clip before spending lip-sync credits if: identity drifts; face becomes a different person; mouth obstructed; person silent/frozen for most of the scene; strong profile angle; teeth/beard smear; face flickers; background changes; wardrobe changes; another face appears; camera framing jumps; clip shorter than required; wrong orientation.

**Automated:** `scripts/probe_video_clip.py` ffprobes each raw clip for orientation, resolution, constant frame rate, and duration `>= required_video_duration - 0.05s` (`AF-PVC-CLIP-TECH`). Identity/motion are named human attestations. Only approved raw clips proceed to lip sync.

---

# 14. Phase Nine: Generate B-Roll

B-roll supports narration while reducing visible talking-head lip sync.

## 14.1–14.5 (v1.0 preserved)

Use cases, planning rule (every B-roll maps to narration timestamps), B-roll prompt template, careful use of the subject's likeness (brief face exposure, over-the-shoulder/side/wide/action shots, no second speaking face), and transition policy (straight cut on a pause, J-cut, L-cut, short crossfade, motion-matched cut; avoid excessive transitions).

---

# 15. Phase Ten: Mandatory Lip-Sync Correction (research-hardened)

## 15.1 Required inputs per scene

`Approved Agnes video clip + exact WAV segment from the Fish master = lip-synced scene.`

## 15.2 Preferred model hierarchy + ideal input specs (research §35.2)

**Ideal inputs for all Sync Labs models (verify before upload):**
- Video: 24–30 fps, MP4/MOV, H.264, a clearly visible unobstructed face covering ~30–50% of frame height, minimum face resolution ~256×256 px, good lighting on the mouth.
- Audio: clean, isolated voice — **no background music, no cross-talk** — 16 kHz or 48 kHz sample rate, WAV preferred.
- Face visible and unobstructed for the great majority of the clip; extreme head rotation degrades every model.

**Default `lipsync-2-pro`** — standard front-facing talking heads, beards, visible teeth, medium close-ups, premium output, scenes with natural speaking motion. *Limits:* struggles past ~30° head rotation; needs clean isolated audio and well-lit face.

**Escalation `sync-3`** — strong face turns (handles up to ~45° better), partial obstruction, close-up mouth detail, challenging angles, nearly-static source, chunk-boundary artifacts from the default, image-instead-of-video source. *Limits:* still imperfect past ~45°; artifacts on very fast speech/overlapping audio; minimum face resolution required.

**Cost-controlled `lipsync-2`** — straightforward front-facing scenes, smaller faces, internal drafts, high-volume production.

**Self-hosted MuseTalk 1.5** — GPU environment available, team accepts extra setup/QC, managed cost must be reduced. **Do not assume a 24 GB Apple Silicon Mac mini performs like an NVIDIA CUDA production server** — verify the supported environment and benchmark before committing the workflow.

## 15.3 Lip-sync input preparation

Normalize raw Agnes video (fps=24, scale/pad to project resolution, yuv420p, `-an`, libx264 crf 18) and audio (`asetpts=PTS-STARTPTS`, 48000, mono) before upload. Exact commands preserved from v1.0.

## 15.4 Duration mismatch policy

`difference = video_duration - audio_duration`. Video longer: 0.00–0.50s trim after lip sync in a silent handle; 0.50–1.50s only if the extra is silent pre/post-roll; >1.50s regenerate or re-cut. Video shorter: 0.00–0.20s after speech → final-frame hold acceptable; 0.00–0.20s during active speech → regenerate; >0.20s → regenerate or move the boundary. Never slow the talking-head video significantly to fit.

## 15.5 Sync-mode rules

Prefer exact input duration; cut-off only for intentional post-roll; no bounce/loop during visible speech; no full-scene remap unless the mismatch is extremely small and passes QC; record the selected mode in the manifest.

## 15.6 Multi-face scenes

Avoid them. When unavoidable: identify the intended speaker; use active-speaker selection; crop/mask non-speaker faces; never let the model animate the wrong person; escalate to manual review.

## 15.7 Lip-sync QC gate (measurable)

Inspect: beginning consonant, first open vowel, P/B/M closures, F/V lower-lip contact, S/SH continuity, final word, smiles, teeth, beard edge, chin/jawline, any ~2-second model chunk boundaries, any cutaway transition.

**Internal production tolerance:** preferred offset `0-1 frame`; maximum accepted offset `2 frames at 24 fps` (≈83 ms). This is the internal QC threshold, not a provider guarantee. Research target: audio-to-visual offset below ~20 ms is imperceptible; the 2-frame (83 ms) ceiling is the reject line.

**Automated drift check:** `scripts/probe_lipsync_offset.py` measures the A/V onset offset at the scene head and (where a waveform/phoneme marker is available) at the tail, and HARD-FAILS (`AF-PVC-LIPSYNC-OFFSET`) if head offset `> 2 frames` or if head-to-tail drift `> 1 frame`. Reject if: mouth starts before voice; voice starts while lips frozen; drift increases over time; teeth flicker; lip texture blurs; beard melts; jaw shape changes; face resolution drops; mouth closes on an open vowel; face changes identity.

## 15.8 Lip-sync retry ladder (error recovery)

- **Attempt 1:** default model with exact-duration clean inputs.
- **Attempt 2:** re-normalize input, crop face slightly larger, remove obstructions, verify active speaker, retry same model.
- **Attempt 3:** escalate (`lipsync-2`→`lipsync-2-pro`, or `lipsync-2-pro`→`sync-3`).
- **Attempt 4 (source repair):** regenerate the Agnes source with a more frontal angle, larger face, visible mouth, simpler movement, explicit natural speaking motion.
- **Terminal:** if still failing after the retry budget (§26.2), do NOT keep paying to lip-sync a bad source — execute the scene-level fallback (§15.9).

## 15.9 Scene-level fallback when lip-sync is exhausted (v2.0)

If a talking-head scene cannot pass lip-sync within the retry budget:
1. Replace the visible-speaking portion with B-roll over the phrase (audio stays on the master).
2. Or re-cut to a shorter, more frontal talking-head take.
3. Or rewrite/split the sentence and regenerate audio + scene (only with approver sign-off, since the master changes).
4. Record the decision and approver in `11_qc/revision_notes.md`. Never ship a clip where the wrong person's mouth is animated or the sync is visibly wrong.

---

# 16. Phase Eleven: Normalize Approved Scenes

Every scene shares identical technical characteristics before concatenation. Inspect with ffprobe; normalize vertical (fps=24, scale/pad 1080×1920, yuv420p, `-an`, libx264 crf 18, `+faststart`) or landscape (1920×1080). Remove scene audio — the final continuous Fish master is authoritative; lip-sync output audio may carry re-encoding, added silence, resampling, timing changes, different loudness, or compression artifacts. Exception: if the provider intentionally altered audio timing, inspect and document; prefer correcting visual duration so the master stays usable.

---

# 17. Phase Twelve: Assemble the Picture

Build `10_assembly/concat.txt` with absolute paths. Concatenate with `-c copy` when stream parameters are identical; re-encode if stream-copy fails or produces timestamp problems. Verify picture duration against the master audio.

**Acceptance rule:** `absolute(video_duration - audio_duration) <= 1 frame` (1 frame = 0.041667s at 24 fps). `scripts/probe_picture_duration.py` enforces this (`AF-PVC-DURATION`). If the picture includes intentional pre/post-roll, record the design and align the master audio accordingly. Do not use `-shortest` as a repair strategy — only as a final safety option after duration QC.

---

# 18. Phase Thirteen: Add B-Roll and Overlays

Method A (preferred): B-roll as normal timeline scenes (already in `scene_manifest.yaml`, normalized, in `concat.txt`). Method B: overlay B-roll over an existing talking-head picture lock (exact `filter_complex` preserved from v1.0). Overlay safety: do not cover essential text; no second visible speaking face; no B-roll contradicting the narration; no unlicensed footage; do not cover the face during lip-sync QC review (retain the clean source for audit); keep cuts on meaningful words/pauses.

---

# 19. Phase Fourteen: Create and Add Music

Instrumental by default. Create a music brief; generate longer than the final video, then trim and fade. **Rights gate:** confirm commercial-use plan; save generation date, plan level, song ID, rights note; a later paid subscription does not grant retroactive commercial rights to free-plan music; record the source in `08_music/license_notes.md`. Prepare music (48k WAV), trim/fade to the actual master duration, and mix voice + music with sidechain ducking (exact `filter_complex` preserved). Music acceptance: every word intelligible; music does not mask S/F/T/P; 8–12 dB lower during speech; may rise slightly during B-roll/title cards; no abrupt cut; no accidental vocal; no clipping; final true peak at/below target. `scripts/probe_audio_master.py` re-verifies the final mix loudness/true-peak.

---

# 20. Phase Fifteen: Captions

Optional unless required by platform/client, but strongly recommended. Build captions from the Fish alignment (not a second transcription) unless timestamps are missing/inaccurate. Rules: correct spelling over phonetic TTS spelling; one or two lines; avoid covering the mouth; safe margins; break by meaning; no emotion tags; no production notes; verify names/branded terms; timing matches the master audio. Burn with `subtitles=` filter; if fonts are missing, use a known installed font or deliver soft captions — never silently substitute a broken style.

---

# 21. Phase Sixteen: Attach Final Audio

Attach the approved voice/voice-music mix to the chosen picture source (`-c:v copy -c:a aac -b:a 192k -ar 48000 +faststart`). Do not add `-shortest` until duration QC proves it will not remove wanted content. Final social encode (libx264 crf 20, yuv420p, 24 fps, AAC 192k, 48000, `+faststart`).

---

# 22. Quality Control System (four levels, hardened)

## 22.1 Level 1: Asset QC
Consent, identity reference, voice model, script, pronunciation, music rights, brand assets. `probe_consent.py` + `probe_no_secrets.py` enforce the binary items.

## 22.2 Level 2: Scene QC
Each scene gets one status: `PASS`, `RETRY_LIPSYNC`, `REGENERATE_AGNES`, `REPLACE_WITH_BROLL`, `MANUAL_REVIEW`, `REJECT`. Create `11_qc/scene_qc.csv` (columns: scene_id, scene_type, audio_start, audio_end, duration, identity_pass, mouth_visible, source_motion_pass, lip_sync_offset_frames, lip_sync_drift, teeth_pass, beard_pass, background_pass, continuity_pass, technical_pass, decision, notes, approved_version). `scripts/probe_scene_qc.py` verifies every `TALKING_HEAD` scene has a `PASS` decision and a recorded `lip_sync_offset_frames <= 2` (`AF-PVC-SCENE-QC`).

## 22.3 Level 3: Full timeline QC
Watch with sound; muted; audio only; normal speed; 0.5x around suspect lip-sync; phone-sized display; desktop display; headphones; ordinary speakers.

## 22.4 Level 4: Technical QC
`ffprobe -show_format -show_streams -of json` on `12_delivery/final_master.mp4`. `scripts/probe_final_technical.py` enforces: correct resolution + orientation; constant frame rate; expected duration (±1 frame of master); H.264; `yuv420p`; AAC; 48 kHz; audio present; no extra unintended streams; fast-start enabled; file opens and seeks (`AF-PVC-FINAL-TECH`).

---

# 23. Detailed Lip-Sync QC Procedure

Visual phoneme test (P/B/M closures, F/V contact, O rounding, EE widening, TH in close-ups); beginning test (no voice over motionless mouth, no mouth-before-voice, neutral pre-roll, first phoneme not clipped); ending test (final mouth movement matches final word, natural settle, no cut on open mouth, short post-roll, no final-frame distortion); drift test (compare beginning/middle/end — drift is not fixed by a global delay; correct duration or regenerate); extract QC frames at 6 fps around a suspect scene and inspect the waveform.

---

# 24. Identity and Continuity QC (research §35.4)

## 24.1 Identity continuity
Across scenes confirm: same person, age, skin tone, face shape, hairline, hairstyle, facial hair, eye color, teeth, wardrobe (unless intentionally changed), accessories, lighting family, background (when scenes are meant to be continuous).

## 24.2 Acceptable variation
Only when the storyboard specifies: new location, wardrobe change, time change, deliberate camera-angle change, B-roll, graphic interlude.

## 24.3 Continuity repair hierarchy (research-backed ordering)
1. Use the same approved reference image (multi-view anchor).
2. Reuse the same prompt.
3. Reuse the same seed when supported.
4. Simplify motion.
5. Match camera framing.
6. Match lighting (lighting continuity between independently generated scenes often needs a post pass — grade to match, but never grade to hide a different face).
7. Use a clean cut or B-roll bridge at the boundary.
8. Regenerate the inconsistent scene.
9. Do not attempt to hide a different face with color grading.

**Research note:** identity drift is the #1 multi-scene failure and worsens past ~5 scenes; human review at scene boundaries remains standard practice — there is no fully automated fix.

---

# 25. Edge-Case Playbook

The v1.0 edge cases (25.1–25.20) are preserved verbatim in the cluster file: Agnes 15s wrapper limit; sentence longer than the video limit; no natural pause; Agnes person does not move mouth; lip-sync drift; mouth before audio; mouth begins late; beard/teeth flicker; hands cross face; speaker turns to profile; multiple faces; generated clip contains audio; scene a few frames too short/long; bad word after video generated; music too loud; music ends too early; captions mismatch; final duration differs; API job fails/times out.

**v2.0 additions:**
- **25.21 Model/provider down.** Follow the §34 fallback hierarchy; record the substitution; re-run every downstream QC gate affected by the swap (duration, timestamps, and lip-sync all change when the voice or video provider changes). Never silently skip the stage.
- **25.22 Lip-sync fails on attempt 3.** Escalate per §15.8 Attempt 4 (source repair); if still failing, execute §15.9 scene-level fallback. Do not burn credits retrying a fundamentally bad source.
- **25.23 Identity drifts mid-clip on a long generation.** Split the scene at a natural pause and regenerate two shorter clips (research §35.3); do not try to salvage a drifting 15s+ take.

---

# 26. Automation State Machine

Track each scene through: `PLANNED → AUDIO_SEGMENT_READY → REFERENCE_READY → AGNES_SUBMITTED → AGNES_COMPLETE → AGNES_VISUAL_QC (FAIL→REGENERATE_AGNES | PASS) → LIPSYNC_SUBMITTED → LIPSYNC_COMPLETE → LIPSYNC_QC (FAIL_SOURCE→REGENERATE_AGNES | FAIL_MODEL→RETRY_OR_ESCALATE | FAIL_TIMING→REBUILD_AUDIO_SEGMENT | PASS) → NORMALIZED → TIMELINE_ASSEMBLED → FINAL_QC → APPROVED`.

## 26.1 Do not skip states
The agent must not mark a scene `APPROVED` because a file exists. A successful API response is not a QC pass.

## 26.2 Retry policy
`agnes_attempts_max: 3`, `lip_sync_attempts_per_model_max: 2`, `model_escalations_max: 1`. After these limits: replace with B-roll, simplify the shot, request human review, rewrite the scene, or use a different approved reference.

---

# 27. AI Execution Pseudocode

(The v1.0 pseudocode is preserved: load manifest → verify consent → verify tools/credentials → verify FFmpeg/FFprobe → create folders → identity bible → approve reference → write scripts → generate continuous Fish master → audio QC → audio-led storyboard → per-scene Agnes + visual QC + lip-sync + lip-sync QC → normalize → assemble → duration verify → overlays/captions → music mix → attach audio → full QC → export + delivery manifest.)

---

# 28. Final QC Checklist

Create `11_qc/final_qc.md` (Authorization, Script/audio, Likeness, Lip sync, Picture, Captions, Music, Technical, Human review — the full v1.0 checklist is preserved). `scripts/probe_final_qc.py` verifies every binary item is attested and every probe passed before the job may be marked complete (`AF-PVC-FINAL-QC`).

---

# 29. Delivery Manifest

Create `12_delivery/delivery_manifest.md` (Project, Final files, Specifications, Models, Rights, Notes — v1.0 preserved). Add a `substitutions` section listing any fallback used and its approver.

---

# 30. Recommended Standard Configuration

The v1.0 standard config is preserved (9:16 1080×1920 24fps libx264 crf 18/20 yuv420p; Agnes image-to-video 6–12s preferred, 15s cap, 18.375s API max, natural speaking motion required; Fish s2.1-pro wav 48k temp 0.65 top_p 0.7 speed 1.0 one continuous master + timestamps; lip-sync default lipsync-2-pro escalation sync-3 scene-by-scene with the original Fish master authoritative; audio -16 LUFS -1.5 dBTP instrumental ducking 8–12 dB; QC max lip offset 2 frames, duration diff 1 frame, human review required).

---

# 31. One-Minute Example

(Preserved: 59.840s master; 7-scene storyboard with 4 talking-head scenes requiring lip sync and 3 B-roll/text scenes; scene visuals total exactly 59.840s; the original Fish master runs continuously underneath; music mixed underneath the master voice.)

---

# 32. Common Mistakes This SOP Prevents

(Preserved, plus v2.0 additions:) Do not send a likeness/reference image prompt under 5,000 stripped chars; do not hardcode an API key or voice ID anywhere; do not route the job outside the `video` department card; do not swap a provider without recording the substitution and re-running downstream QC; do not retry lip-sync past the budget on a bad source.

---

# 33. Definition of Done

The project is complete only when all 14 v1.0 conditions hold **and** every cluster probe script exits 0 (`probe_consent`, `probe_no_secrets`, `probe_manifest`, `probe_environment`, `probe_prompt_band`, `probe_frame_plan`, `probe_segment_duration`, `probe_video_clip`, `probe_lipsync_offset`, `probe_picture_duration`, `probe_audio_master`, `probe_scene_qc`, `probe_final_technical`, `probe_final_qc`).

---

# 34. Consolidated Fallback + Error-Recovery Table (v2.0)

| Capability | Primary | Fallback 1 | Fallback 2 | Fallback 3 | On substitution |
|---|---|---|---|---|---|
| Script/orchestration | OpenClaw | ChatGPT | other tool-using agent | — | record in log |
| Likeness image | `gpt-image-2` | `agnes-image-2.1-flash` (img2img) | Kie.ai | other img2img | re-run reference QC + prompt-band probe |
| Video | `agnes-video-v2.0` | Kie `gemini-omni-video` | Kie `veo3_fast` | — | written client approval; provider-audit gate; re-run clip QC |
| Voice | `s2.1-pro` | `s2.1-pro-free` | ElevenLabs (Skill 30) | — | re-run full audio QC + regenerate timestamps |
| Lip-sync | `lipsync-2-pro` | `sync-3` | `lipsync-2` | MuseTalk 1.5 (self-host) | re-run lip-sync QC; benchmark MuseTalk first |
| Music | Suno (licensed) | other licensed service | none (drop music) | — | record license in `08_music/license_notes.md` |

**Error-recovery ladders** are defined per stage: audio (§10.4 regenerate), Agnes visual (§13.8 reject→regenerate, max 3), lip-sync (§15.8 4-attempt ladder → §15.9 scene fallback), duration (§17 re-cut/rebuild from last correct scene), API timeout (§25.20 preserve task id, poll, exponential backoff, cap attempts).

---

# 35. Research Basis (cited sources, July 2026)

The v2.0 hardening integrates the following current best practices. Re-verify when tool behavior or model names change.

## 35.1 Character/identity consistency (reference-image-to-video)
Leading tools maintain a person's identity across clips by conditioning generation on a **reference-image face embedding** rather than a text description: Kling 1.6 "Character Identity" mode, Runway "Act-One" (reference performance mapped onto a consistent character across shots), Higgsfield reference-image-to-video with an identity-lock face embedding, and Google Veo 2/3 reference-image conditioning. Open-source stacks achieve the same via IP-Adapter / InstantID / FaceID embeddings injected into the generation pipeline. **SOP application:** always image-to-video from an approved multi-view reference (§7, §13.1); never text-to-video for a real person; reuse the same reference, prompt, and seed across scenes (§24.3).

## 35.2 Audio-driven lip sync (Sync Labs)
`lipsync-2-pro` and `sync-3` are audio-driven: they redraw the mouth region to match a supplied audio track. Best results need a clean isolated voice track (no music/cross-talk), a well-lit unobstructed face covering ~30–50% of frame, minimum face resolution (~256×256), 24–30 fps video, and 16 kHz or 48 kHz audio. `lipsync-2-pro` struggles past ~30° head rotation; `sync-3` handles steeper angles (~45°), partial occlusion, and near-static or image sources better, but still artifacts on very fast/overlapping audio. **SOP application:** §15.2 ideal-input spec, §15.3 input prep, §15.6 multi-face control, §15.8 escalation ladder.

## 35.3 Talking-head movement vs the uncanny valley
State-of-the-art naturalness comes from subtle, non-repeating micro-motion, not photorealism: small head motion (~5° pitch/yaw), blinks every 4–6s of varied duration, consistent eye gaze with natural saccades, and tight lip-sync (audio-to-visual offset below ~20 ms is imperceptible). 30 fps is the common commercial standard; 24 fps is acceptable but risks jerkiness on fast turns; 60 fps does not improve perceived naturalness. Long single generations drift — generate short (the 6–12s band) and stitch with natural transitional pauses. **SOP application:** §13.5 motion policy, §11.2 duration policy, §15.7 offset tolerance.

## 35.4 Multi-scene continuity
Identity drift is the #1 cross-cut failure and worsens past ~5 scenes; lighting continuity between independently generated scenes usually needs a post pass; there is no fully automated solution — human review at scene boundaries is standard. Pro controls: character reference sheets (multi-view), same seed + reference per scene, ControlNet/IP-Adapter anchoring, frame interpolation + face blending at boundaries, and a temporal-consistency pass. **SOP application:** §7.5 minimize variants, §24 continuity QC + repair hierarchy, §11.2 keep scenes short.

## 35.5 Prompt engineering for face preservation
Most effective: an explicit identity anchor ("same person as the reference; match reference face geometry, not a generic face"), a strong negative block (different person, identity change, face morph, swapped face, altered features, asymmetric face, age/skin-tone change), image-to-image at low variation/denoising strength, and regenerating from the original reference rather than editing an edit (GPT-image drifts across iterative edits). **SOP application:** §7.3 templates + §13.4 negative prompt + the 5,000–19,000-char band enforced by `probe_prompt_band.py`.

### Official reference links (re-check when behavior changes)
- Agnes Video V2.0: https://wiki.agnes-ai.com/en/docs/agnes-video-v20
- Agnes Image 2.1 Flash: https://wiki.agnes-ai.com/en/docs/agnes-image-21-flash
- Fish Audio models: https://docs.fish.audio/developer-guide/models-pricing/models-overview
- Fish Audio emotion control: https://docs.fish.audio/developer-guide/core-features/emotions
- Fish Audio timestamped TTS: https://docs.fish.audio/api-reference/endpoint/openapi-v1/text-to-speech-stream-with-timestamps
- OpenAI GPT Image 2: https://developers.openai.com/api/docs/models/gpt-image-2
- OpenAI image-generation guide: https://developers.openai.com/api/docs/guides/image-generation
- Sync Labs models: https://sync.so/docs/models
- Sync Labs sync-3: https://sync.so/docs/models/sync-3
- MuseTalk: https://github.com/TMElyralab/MuseTalk
- FFmpeg: https://ffmpeg.org/ffmpeg.html · FFmpeg filters: https://ffmpeg.org/ffmpeg-filters.html
- Suno commercial use: https://help.suno.com/en/articles/9601985

---

# 36. Command Center Integration (v2.0)

- **Department slug:** `video` (per `23-ai-workforce-blueprint/department-naming-map.json`). This SOP routes to the Video department card.
- **Card/campaign:** the production run is carded on the Command Center Kanban as one campaign (`PVC-YYYYMMDD-CLIENT-SLUG`) with one card per DMAIC phase, mirroring `47-movie-producer/scripts/cc_board.py`. The deterministic driver moves each attested phase card to its target.
- **Task routing:** a "personal video / talking-head video / likeness video / VSL with a real person's face + cloned voice" request routes to the `video` department; the Head of Video Production conducts it to the Movie Producer (Skill 47) pipeline operator. Disambiguation: edit supplied footage → Video Editor (Skill 27); captions only → Captioning Specialist (Skill 26); premium TTS only → Fish Audio (Skill 30); storyboard only → Storyboard Writer (Skill 24).
- **Rule-Zero:** every paid generation call (Agnes/Kie image + video, Sync Labs, Suno) requires the Rule-Zero announce + explicit human APPROVE from `head-of-video-production` before spend (`AF-VID-RULE-ZERO` / `AF-VID-APPROVAL-MISSING`), per `SOP--movie-producer-rule-zero-budget.md`.
- **SOP picker / embedding:** this SOP is registered in the cluster manifest and the SOP library with `department: video`, `task_keywords`, and `persona_hints`, so persona-selector-v2.py and the CC SOP picker surface it for video tasks.

# 37. Persona Matching (v2.0)

- **Governing personas (`sops.persona_hints`):** `vsevolod-pudovkin-film-technique` (film-editing/montage specialist — the craft primary for video-edit tasks), `thorne-youtube-unlocked` (YouTube/long-form), `video-funnels` (VSL/conversion video). persona-selector-v2.py unions these into the scoring pool and grants a bounded `sop_hint_bonus`.
- **Department domain tags:** the `video` department pre-qualifies `["video","editing","montage","visual-storytelling","copywriting","communication","marketing"]` (persona-selector-v2.py `DEPT_DOMAIN_TAGS`). A "produce/edit this talking-head video" task infers the `video-edit` category → production-craft domains → the editing/montage specialist wins over a copy persona.
- **When this persona match applies:** any task that produces a finished talking-head / likeness / personal video from a brief or script. Script-only requests route to a copy persona (`video-script` category); captions-only and TTS-only route to their own skills.

---

# 38. Final Instruction to the AI Agent

Do not optimize this process by removing the lip-sync stage. The fastest reliable workflow is: create script → generate one continuous voice master → storyboard from exact audio timing → generate short likeness-preserving Agnes scenes → lip-sync each visible speaking scene to its exact audio segment → assemble all approved visuals under the original master audio → add B-roll, captions, and licensed music → run scene-level and final QC. When a talking-head scene fails, repair that scene — do not rebuild or compromise the entire timeline.

**The audio is the clock. The storyboard is the map. The lip-sync model fixes the mouth. FFmpeg assembles the production. QC decides whether the work is finished.**
