# KIE Video Quality Control (QC) Protocol & Retry Ladder

Authoritative Reference: BlackCEO Execution Spec §8.21 & §15.

---

## 1. Visual & Metadata QC Protocol

A successful API response code (`state: "success"`) indicates that rendering finished, NOT that the resulting video satisfies creative constraints. Autonomous pipelines must execute deterministic QC prior to delivering media or completing workflow tasks.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Video QC Pipeline                                 │
├───────────────────┬─────────────────────────┬───────────────────────────────┤
│ 1. Metadata Check │ 2. Multi-Frame Sampling │ 3. Temporal & Audio Analysis  │
│ - Duration        │ - Frame 0 (Start)       │ - Motion fluidity             │
│ - Dimensions/Res  │ - Frame Mid (T/2)       │ - Artifact/morphing detection │
│ - Container/Codec │ - Frame End (Final)     │ - Audio track presence & sync │
└───────────────────┴─────────────────────────┴───────────────────────────────┘
```

### Stage 1: Metadata Verification
1. **Container & Stream Inspection:** Verify video container (`mp4`/`mov`), video codec (`h264`/`h265`), and audio codec (`aac`/`mp3` when audio was requested).
2. **Duration Normalization:**
   - Verify returned duration against requested seconds.
   - *Vendor Normalization Rule:* Certain providers (e.g. Seedance, PixVerse) normalize clip durations to internal GOP boundaries. Treat the returned metadata as the source of truth, but flag deviations > 1.0s.
3. **Resolution & Aspect Ratio:**
   - Confirm pixel dimensions match the requested resolution tier (e.g., 1080P 16:9 = `1920x1080`, 9:16 = `1080x1920`, 1:1 = `1080x1080`; 720P 16:9 = `1280x720`).
   - Flag unauthorized center-cropping or aspect ratio deformation.

### Stage 2: Multi-Frame Visual Inspection
Extract and visually analyze at least three keyframes: **Opening (Frame 0)**, **Midpoint (Frame T/2)**, and **Ending (Frame N)**.
1. **Subject Identity & Anatomical Integrity:**
   - Verify facial geometry, skin tone, hair styling, and wardrobe against reference assets or prompt requirements.
   - Inspect for anatomical defects: extra limbs, warping hands/fingers, distorted facial features, or unnatural blending into background geometry.
2. **Keyframe Adherence (I2V / Keyframe Modes):**
   - For First-Frame I2V: Compare Frame 0 against the source image (target ≥ 95% structural and color fidelity).
   - For First-and-Last Keyframe: Compare Frame 0 with `first_frame_url` and Frame N with `last_frame_url`.
3. **Typography & Brand Geometry:**
   - When text, signs, or logos are requested, inspect for spelling accuracy, geometric distortion, or character mirroring.

### Stage 3: Temporal Motion & Audio Coherence
1. **Motion Dynamics:** Verify that motion vectors are smooth. Reject clips with violent frame jitter, strobing flicker, sudden spatial jumps, or rapid identity morphing between seconds.
2. **Audio Semantics:**
   - If `audio: true` or native audio was requested, verify that the audio stream is non-empty, synchronized with visible mouth movements or sound-generating actions, and free of loud static or clipping distortion.
   - If audio was disabled, confirm that the audio stream is absent or muted.

---

## 2. Five-Step Controlled Retry Ladder (§15)

When QC fails or an API error occurs, execute the controlled retry sequence. **Never enter an infinite regeneration loop or silently burn API credits across multiple models without authorization.**

```
Step 1: Same Model, Parameter Correction (prompt tweak, aspect ratio adjust, seed shift)
  │
  ▼ (If Step 1 fails)
Step 2: Same Model, Alternate Mode (e.g. switch from text-to-video to first-frame I2V)
  │
  ▼ (If Step 2 fails)
Step 3: Compatible Peer Model (Within KIE, e.g. Wan 3.0 -> Seedance 2.5, if permitted)
  │
  ▼ (If Step 3 fails)
Step 4: Alternate Provider (e.g. KIE -> Agnes Video, only if explicitly authorized)
  │
  ▼ (If Step 4 fails)
Step 5: Hard Stop & Comprehensive Diagnostic Report (Halt and escalate to operator)
```

### Detailed Ladder Specifications:
1. **Step 1 — Parameter Correction (Same Model):**
   - Retain current model.
   - Adjust prompt phrasing, emphasize missing negative constraints, re-verify prompt character count, or shift random `seed`.
   - Re-dispatch once.
2. **Step 2 — Mode / Reference Encoding Alternative (Same Model):**
   - Retain current model.
   - If pure text-to-video produces inconsistent subject geometry, anchor the scene by generating an approved still image first, then dispatching via Image-to-Video (I2V).
   - If multi-reference fusion is failing, reduce reference count to the primary subject asset.
3. **Step 3 — Compatible In-Provider Peer Model:**
   - Permissible ONLY if model selection was automatic (unpinned) or user explicitly authorized model fallback.
   - Example Fallbacks:
     - `wan/3-0-video` (quality failure) ➔ `bytedance/seedance-2-5` (alternate long-form multimodal).
     - `kling-3.0-omni/text-to-video` (motion artifact) ➔ `wan/3-0-video` (higher motion coherence).
     - `pixverse-v6/text-to-video` ➔ `minimax-h3/text-to-video`.
4. **Step 4 — Cross-Provider Fallback:**
   - Switch provider (e.g. KIE ➔ Agnes Video V2.0 / 2.5 Flash) ONLY when generic provider routing is enabled or user gives explicit approval.
5. **Step 5 — Hard Stop & Failure Escalation:**
   - If generation fails across retry attempts, halt immediately.
   - Log exact failure codes, task IDs, credit consumption, and frame QC observations. Present the diagnostic summary to the operator.
