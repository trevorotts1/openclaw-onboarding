╔══════════════════════════════════════════════════════════════╗
  MANDATORY TYP CHECK - READ THIS BEFORE ANYTHING ELSE
  DO NOT SKIP. DO NOT PROCEED UNTIL THIS CHECK IS COMPLETE.
╚══════════════════════════════════════════════════════════════╝

IF YOU HAVE NOT BEEN TAUGHT TYP: STOP. Do not read further. Tell the user you
must be taught the Teach Yourself Protocol first.

══════════════════════════════════════════════════════════════════
KIE VIDEO - REAL EXAMPLES (copy-paste curl)
══════════════════════════════════════════════════════════════════

All bodies below come from first-party KIE API research dated 2026-08-26.
Replace placeholder credentials by sourcing the environment (never print the value):

  source "$HOME/.openclaw/secrets/.env" 2>/dev/null || true

Every call is ASYNC. The 200 response means the task was CREATED, not completed:
  { "code": 200, "msg": "success", "data": { "taskId": "task_..." } }

ALWAYS run the validators first (select_video_model.py, validate_prompt.py,
validate_payload.py). A bad payload never reaches the API.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 1: WAN 3.0 VIDEO (LONG-FORM 20s, NATIVE AUDIO, 1080P)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

curl -sS https://api.kie.ai/api/v1/jobs/createTask \
  -H "Authorization: Bearer $KIE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "wan/3-0-video",
    "callBackUrl": "https://callback.blackceo.com/api/kie/callback",
    "input": {
      "prompt": "OBJECTIVE: Cinematic nature documentary sequence...\n[0.0s - 5.0s]: Aerial pan across glacier valley...\n[5.0s - 12.0s]: Camera tracks down to running river...\n[12.0s - 20.0s]: Sun breaks through cloud cover illuminating peaks...\nCAMERA: 35mm anamorphic, slow technocrane descent\nLIGHTING: Natural 5600K mountain daylight\nAUDIO: Crisp rushing water foley and ambient wind",
      "duration": 20,
      "resolution": "1080P",
      "aspect_ratio": "16:9",
      "audio": true
    }
  }'

Notes: duration window 2–30s (or -1 auto); resolutions 480P/720P/1080P;
supports up to 10 images (20MB), 5 videos (100MB, <=15s), 5 audios (15MB, <=15s), 1 doc.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 2: KLING 3.0 OMNI MULTI-SHOT (5 SHOTS, STORYBOARD)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

curl -sS https://api.kie.ai/api/v1/jobs/createTask \
  -H "Authorization: Bearer $KIE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "kling-3.0-omni/text-to-video",
    "input": {
      "prompt": "Shot 1: Detective enters dimly lit office, rain beating against window.\nShot 2: Close-up on desk showing ancient leather journal and magnifying glass.\nShot 3: Medium shot as detective picks up journal and opens to marked page.\nShot 4: Over-the-shoulder view of coded cipher written in faded ink.\nShot 5: Detective looks up toward door as shadow falls across frosted glass.",
      "duration": 15,
      "resolution": "1080p",
      "aspect_ratio": "16:9",
      "audio": true
    }
  }'

Notes: prompt hard cap 3,072 chars (max 512 chars/shot); up to 6 shots;
supports multi-element consistency (<=7 multi-image subjects / <=3 video characters).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 3: GOOGLE VEO 3.1 FAST (DEDICATED ENDPOINT, 8s, 16:9)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

curl -sS https://api.kie.ai/api/v1/veo/generate \
  -H "Authorization: Bearer $KIE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "veo3_fast",
    "prompt": "Documentary aerial footage sweeping across sand dunes in the Sahara desert at golden hour, sharp undulating ridges casting deep geometric shadows, warm amber twilight glow.",
    "generationType": "TEXT_2_VIDEO",
    "duration": 8,
    "aspectRatio": "16:9",
    "callBackUrl": "https://callback.blackceo.com/api/veo"
  }'

Notes: Dedicated endpoint (`/api/v1/veo/generate`). Model enums: veo3, veo3_fast, veo3_lite.
Duration: 4, 6, 8s (default 8). Native background audio is always-on.
Query status: `GET /api/v1/veo/record-info?taskId=<TASK_ID>`.
Post-generation 1080P/4K upgrade: `GET /api/v1/veo/get-1080p-video` / `POST /api/v1/veo/get-4k-video`.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 4: RUNWAY DEDICATED (GEN-3, 5s, 1080P)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

curl -sS https://api.kie.ai/api/v1/runway/generate \
  -H "Authorization: Bearer $KIE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Cinematic low-angle tracking shot through a neon-lit Tokyo alleyway in the rain, vibrant reflections on wet asphalt, steam rising from street vents.",
    "duration": 5,
    "quality": "1080p",
    "aspectRatio": "16:9",
    "callBackUrl": "https://callback.blackceo.com/api/runway"
  }'

Notes: Dedicated endpoint (`/api/v1/runway/generate`). No `model` field in request body.
Duration: 5 or 10. 1080p is STRICTLY limited to 5s (10s restricted to 720p).
Query status: `GET /api/v1/runway/record-detail?taskId=<TASK_ID>`.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 5: PIXVERSE V6 TRANSITION (START & END KEYFRAME INTERPOLATION)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

curl -sS https://api.kie.ai/api/v1/jobs/createTask \
  -H "Authorization: Bearer $KIE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "pixverse-v6/transition",
    "input": {
      "prompt": "Smooth seamless camera dolly forward transitioning from the modern skyscraper interior to the historical garden pavilion outside.",
      "image_url": "https://domain.com/start_frame.jpg",
      "last_frame_url": "https://domain.com/end_frame.jpg",
      "duration": 5,
      "resolution": "1080p",
      "aspect_ratio": "16:9",
      "generate_audio_switch": true
    }
  }'

Notes: prompt cap 5,000 chars VERIFIED; requires exactly 1 start frame + 1 last frame (<=20MB each);
durations 1–15s (default 5); resolutions 360p/540p/720p/1080p.
