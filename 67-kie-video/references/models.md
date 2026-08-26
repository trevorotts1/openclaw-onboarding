# KIE Video Models — Golden Reference Matrix & Routing Guide

Verification Date: 2026-08-26.
Authoritative Sources: First-party documentation from `docs.kie.ai` and `kie.ai` endpoints.

---

## 1. Golden Limits Matrix

| Model Family | Canonical Model ID | Prompt Hard Cap | Duration Window | Resolutions | Max Media References | Native Audio | Routing Specialist / Task |
|---|---|---|---|---|---|---|---|
| **Wan 3.0 Video** | `wan/3-0-video` | 20,000 chars | 2–30s (or -1 auto) | 480P, 720P, 1080P | 10 imgs (20MB), 5 vids (100MB, ≤15s), 5 audios (15MB, ≤15s), 1 doc/link | Yes (`audio: true`) | Long-form cinematic, rich multimodal references, document/web-driven generation |
| **Wan 3.0 Video Prime** | `wan/3-0-video-prime` | 20,000 chars | 2–30s (or -1 auto) | 480P, 720P, 1080P | 10 imgs (20MB), 5 vids (100MB, ≤15s), 5 audios (15MB, ≤15s), 1 doc/link | Yes (`audio: true`) | High-speed / high-throughput variant of Wan 3.0 with identical capability limits |
| **Kling 3.0 Omni (T2V)** | `kling-3.0-omni/text-to-video` | 3,072 chars (512/shot) | 3–15s (1–15s/shot) | 720p, 1080p, 4k | Multi-elements: ≤7 multi-image subjects / ≤3 video characters | Yes (`audio: bool`) | Multi-shot character consistency, cinematic storyboard sequencing (up to 6 shots) |
| **Kling 3.0 Omni (I2V)** | `kling-3.0-omni/image-to-video` | 3,072 chars | 3–15s | 720p, 1080p, 4k | 1 first frame OR 2 frames (first+last), ≤50MB each | Yes (`audio: bool`) | Precise first/end keyframe interpolation, 4K rendering |
| **Kling 3.0 Omni (Transform)** | `kling-3.0-omni/transformation` | 3,072 chars | 3–15.5s (input matched) | 720p, 1080p, 4k | Exactly 1 video (≤200MB) + up to 4 images (≤50MB) | Yes (`audio: bool`) | Video-to-video style transfer, subject restyling with element preservation |
| **Kling 3.0 Omni (R2V)** | `kling-3.0-omni/reference-to-video` | 3,072 chars | 3–15s | 720p, 1080p, 4k | Max 7 images (no video) OR 1 video (≤200MB, audio must be false) | Conditional (no vid: yes; vid: false) | Multimodal subject-driven generation with strict audio exclusion rules when video input present |
| **Kling 3.0 Single/Multi** | `kling-3.0/video` | NOT_PUBLISHED (null; 500/shot) | 3–15s ('3'–'15') | std (720p), pro (1080p), 4K | First frame, first+last frames, ≤3 kling_elements (2–4 imgs, 5–30s audio) | Yes (`sound: bool`, def true multi) | Standard Kling 3.0 workflow, element @mentions (37 chars/tag), up to 5 shots |
| **Kling 3.0 Motion Control** | `kling-3.0/motion-control` | 2,500 chars (optional) | 3–30s (input matched) | std (720p), pro (1080p) | 1 driving video (3–30s, ≤100MB) + 1 character image (≤10MB) | No (not exposed) | Direct puppet/motion transfer from source video to target character image |
| **Kling 2.6 Motion Control** | `kling-2.6/motion-control` | 2,500 chars | Max 10s (img orient) / 30s (vid orient) | 720p, 1080p | 1 video (3–30s, ≤100MB) + 1 image (≤10MB) | No (not exposed) | Legacy character motion transfer path |
| **Kling 2.5 Turbo (T2V Pro)** | `kling/v2-5-turbo-text-to-video-pro` | 2,500 chars | 5s or 10s ('5', '10') | Not published (aspect ratio only) | None | No (not exposed) | Fast, cost-efficient short-form video generation |
| **Kling 2.5 Turbo (I2V Pro)** | `kling/v2-5-turbo-image-to-video-pro` | 2,500 chars | 5s or 10s ('5', '10') | Not published | 1 start image (≤10MB) + 1 optional tail image | No (not exposed) | Fast image animation with optional end-frame anchoring |
| **Seedance 2.5** | `bytedance/seedance-2-5` | 30,000 chars | 4–30s (or -1 auto) | 480p, 720p, 1080p | 30 imgs (30MB), 10 vids (200MB, ≤30s total), 10 audios (15MB, ≤30s total) | Yes (`generate_audio: true`) | Extended long-duration scenes (up to 30s), massive reference library (up to 50 assets combined) |
| **Seedance 2.0 Mini** | `bytedance/seedance-2-mini` | NOT_PUBLISHED (null) | 4–15s | 480p, 720p | 9 imgs (30MB), 3 vids (50MB, ≤15s total), 3 audios (15MB, ≤15s total) | Yes (`generate_audio: true`) | High-speed, lower-cost Seedance route with web-search augmentation option |
| **PixVerse V6 (T2V)** | `pixverse-v6/text-to-video` | 5,000 chars (min 3) | 1–15s (default 5) | 360p, 540p, 720p, 1080p | None | Yes (`generate_audio_switch`) | Multi-aspect commercial video, optional multi-clip output |
| **PixVerse V6 (I2V)** | `pixverse-v6/image-to-video` | 5,000 chars (min 3) | 1–15s (default 5) | 360p, 540p, 720p, 1080p | Up to 2 images (≤20MB each) | Yes (`generate_audio_switch`) | Two-image dynamic animation |
| **PixVerse V6 (Transition)** | `pixverse-v6/transition` | 5,000 chars (min 3) | 1–15s (default 5) | 360p, 540p, 720p, 1080p | Exactly 1 first image + 1 last image (≤20MB each) | Yes (`generate_audio_switch`) | Smooth camera/scene transitions between two distinct visual states |
| **PixVerse V6 (Extend)** | `pixverse-v6/extend` | 5,000 chars (min 3) | 1–15s (default 5) | 360p, 540p, 720p, 1080p | Parent `taskId` XOR `video_url` | Yes (`generate_audio_switch`) | Iterative forward clip extension retaining source aspect ratio |
| **PixVerse V6 (R2V)** | `pixverse-v6/reference-to-video` | 5,000 chars (min 3) | 1–15s (default 5) | 360p, 540p, 720p, 1080p | 1–7 image references (`subject` or `background`) | Yes (`generate_audio_switch`) | Fusion of explicit subject and background reference assets |
| **MiniMax H3 (T2V)** | `minimax-h3/text-to-video` | 7,000 chars | 4–15s (default 6) | 768P, 2K (default 2K) | None (adaptive ratio NOT supported) | No (not exposed on KIE) | High-resolution 2K text-driven video generation |
| **MiniMax H3 (I2V)** | `minimax-h3/image-to-video` | 7,000 chars | 4–15s (default 6) | 768P, 2K (default 2K) | 1 image (first_frame_url OR last_frame_url, ≤30MB) | No (not exposed on KIE) | High-definition single-frame animation |
| **MiniMax H3 (R2V)** | `minimax-h3/reference-to-video` | 7,000 chars | 4–15s (default 6) | 768P, 2K (default 2K) | 9 imgs (30MB), 3 vids (50MB, ≤15s total), 3 audios (15MB, ≤15s total) | Audio input driving | Rich multimodal 2K generation driven by image, video, and audio assets |
| **Wan 2.7 R2V** | `wan/2-7-r2v` | 5,000 chars (+500 neg) | 2–10s (default 5) | 720p, 1080p | ≤5 images + ≤5 videos (total combined ≤5), 1 voice clip (≤15MB) | Yes (via voice/video audio) | Controlled reference-to-video with voice cloning/driving audio |
| **Wan 2.7 Video Edit** | `wan/2-7-videoedit` | 5,000 chars (+500 neg) | 0 (full length) or 2–10s | 720p, 1080p | Exactly 1 video (2–10s, ≤100MB) + 1 reference image | Yes (`audio_setting`: auto/origin) | Targeted video modification, style repainting, and element insertion |
| **Wan 2.7 T2V** | `wan/2-7-text-to-video` | 5,000 chars (+500 neg) | 2–15s (default 5) | 720p, 1080p | Optional `audio_url` | Yes (custom audio URL) | Standard text-to-video with custom soundtrack attachment |
| **Wan 2.7 I2V** | `wan/2-7-image-to-video` | 5,000 chars (+500 neg) | 2–15s (default 5) | 720p, 1080p | First frame, first+last, video continuation, driving audio | Yes (driving audio) | Multi-mode image animation and video continuation |
| **HappyHorse 1.1 (T2V)** | `happyhorse-1-1/text-to-video` | 5,000 non-CN / 2,500 CN | 3–15s (default 5) | 720p, 1080p | None | No (not exposed) | Bilingual English/Chinese text-to-video generation |
| **HappyHorse 1.1 (I2V)** | `happyhorse-1-1/image-to-video` | 5,000 non-CN / 2,500 CN | 3–15s (default 5) | 720p, 1080p | Exactly 1 image (≤20MB, ≥300px) | No (not exposed) | Bilingual image animation with 20MB source ceiling |
| **HappyHorse 1.1 (R2V)** | `happyhorse-1-1/reference-to-video` | 5,000 non-CN / 2,500 CN | 3–15s (default 5) | 720p, 1080p | 1–9 images (≤20MB each), referenced via `[Image N]` | No (not exposed) | Multi-subject composition referencing indexed images in prompt |
| **HappyHorse 1.0 (T2V)** | `happyhorse/text-to-video` | 5,000 non-CN / 2,500 CN | 3–15s (default 5) | 720p, 1080p | None | No (not exposed) | Legacy HappyHorse text generation path |
| **HappyHorse 1.0 (I2V)** | `happyhorse/image-to-video` | 5,000 non-CN / 2,500 CN | 3–15s (default 5) | 720p, 1080p | Exactly 1 image (≤10MB, ≥300px) | No (not exposed) | Legacy HappyHorse image animation (10MB limit) |
| **HappyHorse 1.0 (R2V)** | `happyhorse/reference-to-video` | 5,000 non-CN / 2,500 CN | 3–15s (default 5) | 720p, 1080p | 1–9 images (≤10MB each), referenced via `character1`, etc. | No (not exposed) | Legacy HappyHorse reference composition (10MB limit) |
| **HappyHorse 1.0 (Edit)** | `happyhorse/video-edit` | 5,000 non-CN / 2,500 CN | Source 3–60s | 720p, 1080p | Exactly 1 video (3–60s, ≤100MB) + 0–5 images (≤10MB) | Yes (`audio_setting`: auto/origin) | Legacy HappyHorse video modification workflow |
| **Gemini Omni** | `gemini-omni-video` | 20,000 chars | 4, 6, 8, 10s (auto if video) | 720p, 1080p, 4k | Slots system: imgs ≤7 (1 slot), video ≤1 (2 slots), char_ids ≤3 (1 slot); sum ≤ 7 | Built-in audio track | Character-consistent and slot-governed multimodal video synthesis |
| **Runway (Dedicated)** | `runway` | LIVE_PROBE_REQUIRED (1800 vs 2048) | 5s or 10s (10s 720p only) | 720p, 1080p (5s only) | 1 optional `imageUrl` | No (not exposed) | Dedicated `/api/v1/runway/generate` route; high cinematic motion |
| **Veo 3.1 Quality (Dedicated)** | `veo3` | NOT_PUBLISHED (null) | 4, 6, 8s (default 8) | 720p (base), 1080p / 4K upgrade | 1–2 images (1–3 for `REFERENCE_2_VIDEO`) | Yes (always-on background audio) | Dedicated `/api/v1/veo/generate` route; highest quality tier |
| **Veo 3.1 Fast (Dedicated)** | `veo3_fast` | NOT_PUBLISHED (null) | 4, 6, 8s (default 8) | 720p (base), 1080p / 4K upgrade | 1–2 images (1–3 for `REFERENCE_2_VIDEO`) | Yes (always-on background audio) | Dedicated `/api/v1/veo/generate` route; default fast generation tier |
| **Veo 3.1 Lite (Dedicated)** | `veo3_lite` | NOT_PUBLISHED (null) | 4, 6, 8s (default 8) | 720p (base), 1080p / 4K upgrade | 1–2 images (1–3 for `REFERENCE_2_VIDEO`) | Yes (always-on background audio) | Dedicated `/api/v1/veo/generate` route; lightweight cost-effective tier |

---

## 2. Model Selection & Routing Doctrine

When an explicit model is specified by the user, department manifest, or workflow SOP, **that model must be honored**. When routing autonomously, apply the following capability-matched hierarchy:

```
                          ┌──────────────────────────────────────────────┐
                          │         Incoming Video Request               │
                          └──────────────────────┬───────────────────────┘
                                                 │
                   ┌─────────────────────────────┴─────────────────────────────┐
                   ▼                                                           ▼
         [Dedicated API Explicit]                                    [Generic KIE Market]
                   │                                                           │
        ┌──────────┴──────────┐                                                ▼
        ▼                     ▼                                  ┌───────────────────────────┐
     [Runway]               [Veo 3.1]                            │ Multimodal / Long-Form    │
  /api/v1/runway/        /api/v1/veo/                            │ Requirements (>15s / refs)│
  - 5s/10s clips         - 4/6/8s clips                          └─────────────┬─────────────┘
  - 720p/1080p           - Always-on audio                                     │
  - Strict dedicated     - 1080p/4k upgrades                                   ├─────────────────────────────┐
    endpoints              via dedicated endpoints                             ▼                             ▼
                                                                       [Wan 3.0 Video]               [Seedance 2.5]
                                                                       - Up to 30s / -1 auto         - Up to 30s / -1 auto
                                                                       - 20,000 char prompt band     - 30,000 char prompt cap
                                                                       - 10 img, 5 vid, 5 aud refs   - 30 img, 10 vid, 10 aud refs
                                                                       - Wan 3.0 Prime for speed     - Native audio generation
                                                                               │
                                                 ┌─────────────────────────────┼─────────────────────────────┐
                                                 ▼                             ▼                             ▼
                                         [Cinematic / Multi-Shot]     [High Resolution 2K]        [Character Consistency]
                                                 │                             │                             │
                                                 ▼                             ▼                             ▼
                                         [Kling 3.0 Omni]              [MiniMax H3]                  [Gemini Omni]
                                         - Up to 6 shots / 15s         - Up to 15s / 2K native       - Slot-based (sum ≤ 7)
                                         - 3,072 char prompt cap       - 7,000 char prompt cap       - Character IDs (≤3)
                                         - First/last keyframes        - Multimodal R2V (9 img/3 vid)- 4/6/8/10s duration
                                                 │
                                                 ├─────────────────────────────┬─────────────────────────────┐
                                                 ▼                             ▼                             ▼
                                         [Video Editing / Mod]        [Bilingual / Reference]       [Puppet Motion Transfer]
                                                 │                             │                             │
                                                 ▼                             ▼                             ▼
                                         [Wan 2.7 Video Edit]          [HappyHorse 1.1]              [Kling 3.0 Motion Control]
                                         - Exactly 1 video (≤100MB)    - 5K non-CN / 2.5K CN cap     - Driving video + image
                                         - Style & element repainting  - R2V with [Image N] syntax   - 0–2,500 char prompt
```

### Routing Rules by Specialty:
1. **Long-Form Narrative / Multi-Reference (>15s to 30s):**
   - **Primary:** `wan/3-0-video` (or `wan/3-0-video-prime` for high throughput). Supports up to 20K char prompts, 10 images, 5 video clips, 5 audio tracks, and structured documents/links.
   - **Alternative:** `bytedance/seedance-2-5`. Supports up to 30s, up to 30 images, 10 videos, 10 audios, and 30K char prompts.
2. **Multi-Shot Cinematic Storyboards & Sequence Control:**
   - **Primary:** `kling-3.0-omni/text-to-video` (up to 6 shots, 512 chars/shot, 3,072 total cap) or `kling-3.0/video` (up to 5 shots).
3. **High-Resolution 2K Native Output:**
   - **Primary:** `minimax-h3/text-to-video` or `minimax-h3/reference-to-video` (7,000 char cap, default 2K resolution).
4. **Slot-Governed Subject & Voice Control:**
   - **Primary:** `gemini-omni-video` (up to 3 character IDs, 7 total reference slots, 20K prompt cap).
5. **Video Modification & Style Inpainting:**
   - **Primary:** `wan/2-7-videoedit` (1 source video ≤100MB, 2–10s, optional reference image).
6. **Character Motion Transfer (Puppeteering):**
   - **Primary:** `kling-3.0/motion-control` (1 driving video + 1 character portrait).
7. **Fast Turnaround / Lower Cost:**
   - **Primary:** `bytedance/seedance-2-mini`, `kling/v2-5-turbo-text-to-video-pro`, or `pixverse-v6/text-to-video`.
8. **Dedicated Provider Endpoints:**
   - **Runway:** Must use `POST /api/v1/runway/generate` (never `createTask`).
   - **Veo 3.1:** Must use `POST /api/v1/veo/generate` with dedicated `get-1080p-video` or `get-4k-video` endpoints for post-generation resolution upgrades.
