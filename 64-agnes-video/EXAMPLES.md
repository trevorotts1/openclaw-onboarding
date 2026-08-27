╔══════════════════════════════════════════════════════════════╗
  MANDATORY TYP CHECK - READ THIS BEFORE ANYTHING ELSE
  DO NOT SKIP. DO NOT PROCEED UNTIL THIS CHECK IS COMPLETE.
╚══════════════════════════════════════════════════════════════╝

STEP 1: CHECK IF YOU HAVE BEEN TAUGHT THE TEACH YOURSELF PROTOCOL (TYP)

Before you read, learn, or execute ANY instruction in this document, you must
verify that you have already been taught the Teach Yourself Protocol (TYP). If
you have not, STOP and tell the user you cannot proceed until you are taught TYP.

══════════════════════════════════════════════════════════════════
AGNES VIDEO — REAL EXAMPLES (2.5 FLASH + V2.0)
══════════════════════════════════════════════════════════════════

Copy-paste curl commands. They read the key from the environment as
`$AGNES_AI_API_KEY` — never paste the key value inline, never print it.

Every example is the SAME two steps: (1) route/choose, (2) create a task,
(3) poll by `video_id`.

STEP 0 — ROUTE FIRST, EVERY TIME:

echo '{"requested_seconds":"5","size":"720P","intent":"text"}' \
  | python3 scripts/select_agnes_video_model.py

Expected: {"model": "agnes-video-2.5-flash", "valid": true, "mode": "text", ...}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 1: FLASH TEXT-TO-VIDEO (~5s, 720P)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Note the STRING "seconds" and "720P" size.

curl -X POST https://apihub.agnes-ai.com/v1/videos \
  -H "Authorization: Bearer $AGNES_AI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-video-2.5-flash",
    "prompt": "A cinematic shot of a cat walking on the beach at sunset, soft ocean waves, warm golden lighting, realistic motion",
    "mode": "text",
    "seconds": "5",
    "size": "720P",
    "aspect_ratio": "16:9",
    "seed": 42
  }'

Expected response (QUEUED — no video yet):

{
  "task_id": "task_abc123",
  "video_id": "video_abc123",
  "object": "video",
  "model": "agnes-video-2.5-flash",
  "status": "queued",
  "progress": 0
}

Poll — ALWAYS with model_name for Flash:

curl --location --request GET \
  'https://apihub.agnes-ai.com/agnesapi?video_id=video_abc123&model_name=agnes-video-2.5-flash' \
  --header "Authorization: Bearer $AGNES_AI_API_KEY"

When done: "status" is "completed", the video URL is in "metadata.url".
Download it right away.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 2: FLASH KEYFRAME
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

first_frame and/or last_frame. NO images/audios arrays. Route verdict: Flash
keyframe. Poll with model_name (REQUIRED in keyframe mode).

curl -X POST https://apihub.agnes-ai.com/v1/videos \
  -H "Authorization: Bearer $AGNES_AI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-video-2.5-flash",
    "prompt": "Pan slowly right from the first frame and settle into the last frame, cinematic motion",
    "mode": "keyframe",
    "seconds": "10",
    "size": "720P",
    "first_frame": "https://example.com/frame_a.png",
    "last_frame": "https://example.com/frame_b.png"
  }'

Poll: GET /agnesapi?video_id=<ID>&model_name=agnes-video-2.5-flash

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 3: FLASH REFERENCE (IMAGES, MAX 5)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Reference mode uses "images" array (max 5) with <Picture N> placeholders.
"videos" is NEVER accepted here (HTTP 400).

curl -X POST https://apihub.agnes-ai.com/v1/videos \
  -H "Authorization: Bearer $AGNES_AI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-video-2.5-flash",
    "prompt": "Keep <Picture 1> character identity exactly; animate a subtle smile",
    "mode": "reference",
    "seconds": "5",
    "size": "720P",
    "images": [
      "https://example.com/character.png"
    ]
  }'

Poll: GET /agnesapi?video_id=<ID>&model_name=agnes-video-2.5-flash

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 4: V2.0 TEXT-TO-VIDEO (~5s)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

V2.0 duration is frame-driven: seconds = num_frames / frame_rate. 121/24 ≈ 5s.

curl -X POST https://apihub.agnes-ai.com/v1/videos \
  -H "Authorization: Bearer $AGNES_AI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-video-v2.0",
    "prompt": "A cinematic shot of a cat walking on the beach at sunset, soft ocean waves, warm golden lighting, realistic motion",
    "height": 768,
    "width": 1152,
    "num_frames": 121,
    "frame_rate": 24
  }'

Step 2 — poll by video_id (model_name optional for V2.0):

curl --location --request GET \
  'https://apihub.agnes-ai.com/agnesapi?video_id=video_abc123' \
  --header "Authorization: Bearer $AGNES_AI_API_KEY"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 5: V2.0 IMAGE-TO-VIDEO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Top-level "image" string. Route verdict: V2.0.

curl -X POST https://apihub.agnes-ai.com/v1/videos \
  -H "Authorization: Bearer $AGNES_AI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-video-v2.0",
    "prompt": "The woman slowly turns around and looks back at the camera, natural facial expression, cinematic camera movement",
    "image": "https://example.com/image.png",
    "num_frames": 121,
    "frame_rate": 24
  }'

Then poll by video_id exactly like Example 4.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 6: V2.0 KEYFRAME ANIMATION (extra_body)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Keyframes go in extra_body.image ARRAY + extra_body.mode "keyframes".

curl -X POST https://apihub.agnes-ai.com/v1/videos \
  -H "Authorization: Bearer $AGNES_AI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-video-v2.0",
    "prompt": "Generate a smooth cinematic transition between the keyframes, maintaining visual consistency and natural camera movement",
    "extra_body": {
      "image": [
        "https://example.com/keyframe1.png",
        "https://example.com/keyframe2.png"
      ],
      "mode": "keyframes"
    },
    "num_frames": 121,
    "frame_rate": 24
  }'

Then poll by video_id exactly like Example 4.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 7: LONGER CLIP (>12s) — V2.0 DERIVED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Flash max is 12s. The router derives 18s @ 24fps -> 433 frames (8n+1, <= 441,
18.04s):

echo '{"requested_seconds":18,"frame_rate":24,"size":"1080p"}' \
  | python3 scripts/select_agnes_video_model.py

Expected: V2.0 valid with derived num_frames 433.

curl -X POST https://apihub.agnes-ai.com/v1/videos \
  -H "Authorization: Bearer $AGNES_AI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-video-v2.0",
    "prompt": "A young astronaut walking across a red desert planet, dust blowing in the wind, slow cinematic tracking shot, dramatic sunset lighting, realistic sci-fi style",
    "num_frames": 433,
    "frame_rate": 24,
    "seed": 12345
  }'

20s @ 24fps = 480 frames > 441: router returns valid=false — split clips or
lower frame_rate (e.g. 18s max at 24fps; 20s needs frame_rate 22 -> 441 frames
exactly).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 8: POLL FORMS + NORMALIZATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

V2.0 with explicit model_name (optional but explicit):

curl --location --request GET \
  'https://apihub.agnes-ai.com/agnesapi?video_id=video_abc123&model_name=agnes-video-v2.0' \
  --header "Authorization: Bearer $AGNES_AI_API_KEY"

Legacy path by task_id (V2.0):

curl --location --request GET \
  'https://apihub.agnes-ai.com/v1/videos/task_abc123' \
  --header "Authorization: Bearer $AGNES_AI_API_KEY"

Read resolution/duration from the RESPONSE, not the request — V2.0 normalizes
(e.g. requested 1024x576 comes back as "480p/16:9 (832x448)" in
metadata.size_mapping).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMMON MISTAKES TO AVOID
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MISTAKE 0: Choosing the model by hand.
  Run scripts/select_agnes_video_model.py. Explicit model wins; never silently
  switch; the semantic guard refuses 6+ refs -> V2.0 keyframes reinterpretation.

MISTAKE 1: Treating video like the synchronous image endpoint.
  Video is ASYNC. A 200 on POST /v1/videos means QUEUED. You must poll.

MISTAKE 2: Sending Flash seconds as a number, or "13"/"3".
  Flash seconds is the STRING enum "4"-"12". Anything else is HTTP 400.

MISTAKE 3: Sending Flash size 1080p — or width/height/num_frames to Flash.
  Flash is 720P only and has no width/height/num_frames/frame_rate/
  negative_prompt/inference_steps.

MISTAKE 4: Polling Flash by video_id alone.
  Keyframe/reference tasks require &model_name=agnes-video-2.5-flash. Use the
  safe form always.

MISTAKE 5: 6+ image refs in reference mode.
  Flash max is 5 (HTTP 400). The router refuses to auto-convert to V2.0
  keyframes — re-ask or use KIE Video.

MISTAKE 6: Video references into Agnes.
  Neither model supports them (HTTP 400 videos is not supported). Hand to
  KIE Video when permitted.

MISTAKE 7: Reading duration/resolution from your REQUEST.
  V2.0 normalizes. Read "size", "seconds", "metadata.size_mapping" from the
  RESPONSE.

MISTAKE 8: An invalid num_frames.
  Must be <= 441 AND on the 8n+1 grid (81, 121, 241, 441, ...). 120 is wrong;
  121 is right.

MISTAKE 9: Sending a local file for image/keyframe inputs.
  Agnes needs a PUBLIC URL, not a file path or base64 bytes.

MISTAKE 10: Hardcoding a rate limit.
  Agnes meters BOTH requests-per-minute and a daily/weekly quota, and the limit
  depends on the account tier. Treat HTTP 429 as the live truth and back off.

MISTAKE 11: Auto-selecting full agnes-video-2.5.
  It is PAID and not in the token plan. Only flash and v2.0 are approved.

MISTAKE 12: Printing the key.
  Never echo/cat/log AGNES_AI_API_KEY. Send it only as the Bearer token.
