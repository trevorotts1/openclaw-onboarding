╔══════════════════════════════════════════════════════════════╗
  MANDATORY TYP CHECK - READ THIS BEFORE ANYTHING ELSE
  DO NOT SKIP. DO NOT PROCEED UNTIL THIS CHECK IS COMPLETE.
╚══════════════════════════════════════════════════════════════╝

STEP 1: CHECK IF YOU HAVE BEEN TAUGHT THE TEACH YOURSELF PROTOCOL (TYP)

Before you read, learn, or execute ANY instruction in this document, you must
verify that you have already been taught the Teach Yourself Protocol (TYP).

HOW TO CHECK:
- Look in your AGENTS.md, TOOLS.md, or MEMORY.md for any mention of:
  "Teach Yourself Protocol" or "TYP"
- Look in your session context for prior TYP training
- Look for a tab called "Teach Yourself Protocol" in this same document

IF YOU HAVE BEEN TAUGHT TYP:
Proceed to the instructions below. Follow the TYP file storage structure.

IF YOU HAVE NOT BEEN TAUGHT TYP:
STOP IMMEDIATELY. Do not read further. Do not attempt to learn or execute
anything in this document. Tell the user exactly this:

  "I have not been taught the Teach Yourself Protocol yet. I cannot safely
   learn or execute these instructions until I have been taught TYP first.
   Please share the Teach Yourself Protocol tab with me before we proceed.
   Without TYP, I will bloat your core .md files and waste your tokens."

DO NOT PROCEED PAST THIS POINT WITHOUT TYP CONFIRMED.

══════════════════════════════════════════════════════════════════
KIE VIDEO - HOW TO USE IT (DAILY USAGE GUIDE)
══════════════════════════════════════════════════════════════════

This document explains the KIE Video day-to-day workflow: route, normalize,
select, validate prompt, validate payload, dispatch, wait (polling/callback),
download, and visual multi-frame QC. If the credential is not confirmed yet, go to
INSTALL.md first. For full parameter contracts, see references/api-patterns.md;
for prompt policy, references/prompt-policy.md; for the human model matrix,
references/models.md; for QC and retry ladder, references/qc.md.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
THE BIG PICTURE — EVERY TASK IS ASYNCHRONOUS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The KIE.ai API is CREATE-THEN-POLL:

1. Dispatch task:
   - Generic models: `POST https://api.kie.ai/api/v1/jobs/createTask`
   - Dedicated Runway: `POST https://api.kie.ai/api/v1/runway/generate`
   - Dedicated Veo 3.1: `POST https://api.kie.ai/api/v1/veo/generate`
2. HTTP 200 response means task was CREATED and QUEUED, NOT completed. It carries a
   `taskId`, never a video.
3. Wait: callBackUrl (Skill 46 relay) or recordInfo polling:
   - Market: `GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<TASK_ID>`
   - Runway: `GET https://api.kie.ai/api/v1/runway/record-detail?taskId=<TASK_ID>`
   - Veo 3.1: `GET https://api.kie.ai/api/v1/veo/record-info?taskId=<TASK_ID>`
4. State lifecycle: waiting -> queuing -> generating -> success | fail.
5. On success, download the generated video immediately (download URLs expire in ~24h;
   media is retained on KIE storage for 14 days).
6. Perform multi-frame visual QC (Frame 0, Midpoint, Final Frame). See references/qc.md.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 1: NORMALIZE THE ALIAS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Run normalizer on natural-language model mentions:

  python3 scripts/normalize_alias.py "<model mention from the request>"

Mappings: "Kling O3" -> kling-3.0-omni, "Wan 3 Prime" -> wan-3-0, "Seed Dance" -> bytedance,
"Mini Max" / "Hailuo" -> minimax-h3, "Happy Horse 1.1" -> happyhorse-1-1,
"Gemini Omni" -> gemini-omni-video, "Runway Gen3" -> runway, "Veo 3.1" -> veo3.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 2: SELECT THE MODEL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  python3 scripts/select_video_model.py "<natural-language video request>"

Exit 0: prints the selected canonical model ID + task mode. Exit 1: no model can serve.
Routing policy:
- Explicit user/manifest model selection is strictly honored.
- Autonomous hierarchy:
  - Long-form (>15s to 30s): `wan/3-0-video` (or `wan/3-0-video-prime`) or `bytedance/seedance-2-5`
  - Multi-shot Storyboards: `kling-3.0-omni/text-to-video` or `kling-3.0/video`
  - 2K Native Resolution: `minimax-h3/text-to-video`
  - Character Consistency / Slots: `gemini-omni-video`
  - Video Editing / Repainting: `wan/2-7-videoedit`
  - Motion Transfer (Puppeteer): `kling-3.0/motion-control`
  - Short + Cheap: `kling/v2-5-turbo-text-to-video-pro` or `bytedance/seedance-2-mini`
  - Dedicated: `runway` or `veo3` / `veo3_fast` / `veo3_lite`

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 3: EXPAND & VALIDATE THE PROMPT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Short user prompts are expanded into the full 17-part prompt structure (§5.4)
addressing objective, subject, environment, timeline, action, camera, lighting,
dynamics, frame 0/N, soundscape, and exclusions.

Validate prompt against model caps:

  python3 scripts/validate_prompt.py "<prompt text>" --model "<canonical_model_id>"

- Verified ≥20K (Rule A): 5,000–19,000 house band (target ~9,000).
- Verified 5K–19,999 (Rule B): conservative ceiling below cap (MiniMax ~6,500, PixVerse/Wan2.7 ~4,500).
- Verified <5K (Rule C): high-density compression (Kling Omni ~2,800, Kling 2.5 ~2,200).
- NOT_PUBLISHED / LIVE_PROBE_REQUIRED (Rule E): soft-pass with proposed band.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 4: VALIDATE THE PAYLOAD BEFORE DISPATCH
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Validate full payload JSON against models.json:

  python3 scripts/validate_payload.py --file payload.json

Enforces:
- Endpoint/family match (`kie-market` -> `createTask`, `runway-dedicated` -> `generate`, `veo-dedicated` -> `generate`).
- Duration within supported duration window.
- Resolution in allowed enum.
- Media reference counts and file sizes.
- Runway 1080p 5s duration ceiling.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 5: DISPATCH & WAIT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Dispatch via curl with `$KIE_API_KEY`:

  source "$HOME/.openclaw/secrets/.env" 2>/dev/null || true
  curl -sS https://api.kie.ai/api/v1/jobs/createTask \
    -H "Authorization: Bearer $KIE_API_KEY" \
    -H "Content-Type: application/json" \
    -d @payload.json

Poll using stepped backoff (3s -> 5s -> 10s -> 15s; max 15 min), or receive via webhook.
HTTP 429 = rate limited (max 20 req/10s); sleep at least 5s before retrying.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 6: REAL VISUAL QC & RETRY LADDER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Download video immediately.
2. Inspect metadata (container, codec, duration, resolution).
3. Sample 3 keyframes: Frame 0 (Start), Frame T/2 (Midpoint), Frame N (End).
4. Verify anatomical integrity, non-morphing geometry, smooth motion vectors, and audio sync.
5. If QC fails, execute 5-step retry ladder (references/qc.md):
   Step 1: Parameter correction (same model)
   Step 2: Alternate mode/reference encoding (same model, e.g. T2V -> I2V)
   Step 3: In-provider peer model fallback (if authorized)
   Step 4: Cross-provider fallback (e.g. KIE -> Agnes Video, if authorized)
   Step 5: Hard stop & diagnostic report to operator.
