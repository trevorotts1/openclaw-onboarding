╔══════════════════════════════════════════════════════════════╗
  MANDATORY TYP CHECK - READ THIS BEFORE ANYTHING ELSE
  DO NOT SKIP. DO NOT PROCEED UNTIL THIS CHECK IS COMPLETE.
╚══════════════════════════════════════════════════════════════╝

IF YOU HAVE NOT BEEN TAUGHT TYP: STOP. Do not read further. Tell the user you
must be taught the Teach Yourself Protocol first.

══════════════════════════════════════════════════════════════════
KIE IMAGE - REAL EXAMPLES (copy-paste curl)
══════════════════════════════════════════════════════════════════

All bodies below come from first-party KIE docs research
(01-kie-common.md, 02-kie-image-a.md, 03-kie-image-b.md). Replace the literal
placeholder with the env var (source ~/.openclaw/secrets/.env first — see
INSTALL.md; never print the value):

  source "$HOME/.openclaw/secrets/.env" 2>/dev/null || true

Every call is ASYNC. The 200 response means the task was CREATED, not completed:

  { "code": 200, "msg": "success", "data": { "taskId": "task_..." } }

Then poll:
  curl -sS -m 30 "https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<TASK_ID>" \
    -H "Authorization: Bearer $KIE_API_KEY"

state "success" -> data.response.resultUrls[] (same list as the JSON string in
data.resultJson). Download immediately. KIE documents 14 days for generated media but its task-detail page says result URLs typically expire after 24 hours; download/persist immediately.

ALWAYS run the validators first (see INSTRUCTIONS.md step 4): select_image_model.py,
validate_prompt.py, validate_payload.py. A bad payload never reaches the API.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 1: GPT IMAGE 2.6 TEXT-TO-IMAGE (default pick, 1:1 1K)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

curl -sS https://api.kie.ai/api/v1/jobs/createTask \
  -H "Authorization: Bearer $KIE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-image-2-6/sunburst-text-to-image",
    "callBackUrl": "https://your-domain.example/kie/callback",
    "input": {
      "prompt": "A futuristic Black woman CEO standing in a glass office overlooking a neon city at dusk, cinematic lighting, 1:1",
      "aspect_ratio": "1:1",
      "resolution": "1K"
    }
  }'

Notes: resolution enum 1K/2K/4K (default 1K) with NO per-resolution ratio
exclusions. aspect_ratio enum is 16 values: auto, 1:1, 3:2, 2:3, 4:3, 3:4,
5:4, 4:5, 16:9, 9:16, 2:1, 1:2, 21:9, 9:21, 3:1, 1:3. 3:1, 1:3 and 9:21 are
served natively by this model. 27:16, 16:27, 9:8 and 8:9 are NOT in the enum
at any resolution. Model ids are slash form — a hyphenated
gpt-image-2-6-sunburst-* answers HTTP 422 "model name not supported".

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 2: GPT IMAGE 2.6 IMAGE-TO-IMAGE (16 refs max, 30MB)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

curl -sS https://api.kie.ai/api/v1/jobs/createTask \
  -H "Authorization: Bearer $KIE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-image-2-6/sunburst-image-to-image",
    "input": {
      "prompt": "Restyle the product shot to matte black on a white studio background, preserving the original geometry, lighting direction, and camera angle",
      "aspect_ratio": "4:5",
      "resolution": "2K",
      "input_urls": [ "https://example.com/product-clean.png" ]
    }
  }'

Notes: refs via input_urls, maxItems 16, max 30MB, formats JPEG/PNG/WEBP only
and publicly reachable. Probe 2026-09-10 on the 2.5 generation: the route also
accepted image_input (task 8fcde5... success, 6 credits) and has NOT been
retested on 2.6 — use input_urls.
4:5 is a native member of the 2.6 ratio enum, so this needs no substitution
and no second model. Output format on i2i is png/jpeg/webp ONLY — gif and svg
are text-to-image only. mask_url OR markup may be added, never both.
Client logo/brand work MUST be I2I with the logo as input_urls[0] (never T2I).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 3: WAN 2.7 IMAGE (5,000-char cap; bbox regions)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

curl -sS https://api.kie.ai/api/v1/jobs/createTask \
  -H "Authorization: Bearer $KIE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "wan/2-7-image-pro",
    "input": {
      "prompt": "A product hero shot: the black smartwatch on a marble table with dramatic studio lighting, 4,500-4,900 chars filled with production detail here",
      "input_urls": [ "https://example.com/table-scene.png" ],
      "bbox_list": "[[[120,80,340,360]]]",
      "n": 1,
      "resolution": "1K",
      "aspect_ratio": "1:1",
      "color_palette": [ "#0B0B0B", "#C8A96E", "#F4F1EA", "#6B7A8F" ]
    }
  }'

Notes: prompt hard cap 5,000 chars VERIFIED ("with a minimum of 1 characters
and a maximum of 5,000 characters") — target 4,500–4,900; validate_prompt.py
hard-fails above 5,000. bbox_list is a JSON-as-string, parallel to input_urls;
"Each image supports up to 2 boxes." Input refs max 9, max 10MB, "at least 240
pixels in length and width". n: 1–4; gallery mode (enable_sequential) allows
1–12, "the actual value is determined by the model". Pro 4K is text-to-image
only ("That 4K support applies to text-to-image only"). thinking_mode is only
available with gallery off and no uploaded images.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 4: SEEDREAM 5.0 PRO IMAGE-TO-IMAGE (30MB; quality tiers)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

curl -sS https://api.kie.ai/api/v1/jobs/createTask \
  -H "Authorization: Bearer $KIE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "seedream/5-pro-image-to-image",
    "input": {
      "prompt": "Recompose this street photo into a rain-soaked cyberpunk night, preserving the street layout, camera angle, and building silhouettes",
      "quality": "High",
      "aspect_ratio": "16:9",
      "output_format": "png",
      "image_urls": [ "https://example.com/street-day.png" ]
    }
  }'

Notes: refs "Supported formats: JPEG, PNG, WEBP Maximum file size: 30MB;
Maximum files: 10". quality Basic/High/Ultra (Ultra is Lite-only); Pro Basic=1K,
High=2K; Lite Basic=2K/High=3K/Ultra=4K; 4.5 Basic=2K/High=4K. Seedream 4.5
has NO output_format field. Single image per request — no n.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 5: NANO BANANA 2 IMAGE-TO-IMAGE (14 refs, 30MB)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

curl -sS https://api.kie.ai/api/v1/jobs/createTask \
  -H "Authorization: Bearer $KIE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nano-banana-2",
    "input": {
      "prompt": "Keep the subject identical, change the background to a warm beige studio backdrop with soft gradient lighting",
      "image_input": [ "https://example.com/subject.png" ],
      "aspect_ratio": "4:5",
      "resolution": "2K",
      "output_format": "PNG"
    }
  }'

Notes: refs via image_input (not input_urls), 14 @ 30MB, JPEG/PNG/WEBP;
resolution 1K/2K/4K; output_format JPG|PNG; 15-ratio enum. NB2 Lite is the
3-fields-only variant (prompt, image_urls 10 @ 30MB, aspect_ratio — no
resolution/output_format). NB Pro: 8 @ 30MB, NO 1:4/4:1/1:8/8:1 ratios.
Legacy google/nano-banana edits: image_urls REQUIRED, 10 @ 10MB (not 30MB).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMMON MISTAKES TO AVOID
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MISTAKE 1: Treating createTask 200 as the finished image.
  The 200 is the CREATED receipt with a taskId. Only recordInfo
  state=="success" (or the callback) carries the result URLs (resultJson / response).

MISTAKE 2: Skipping the validators.
  validate_prompt.py + validate_payload.py run BEFORE dispatch. Wan >5,000
  chars, a GPT Image 2 excluded ratio at 2K/4K, a ratio outside the GPT Image
  2.6 enum, more than 20,000 chars on 2.6, >16 refs, wrong 30MB vs 10MB
  limits — all rejected locally, never charged.

MISTAKE 3: Inventing a prompt cap.
  Seedream, Nano Banana, FLUX.2, Z-Image: vendor cap NOT published. Do not
  claim a number; the limit comes from Skill 74 (live schema), and with none
  known validate_prompt.py refuses a pass (UNKNOWN_MAX). No fixed 19,000 ceiling.

MISTAKE 4: Converting Qwen's "4.5K token inputs" into a 4,500-char rule.
  Tokens are not characters. Rule D. Use token estimation; docs schema
  maxLength 5000 chars sits alongside (recorded as a known inconsistency).

MISTAKE 5: Forgetting the ratio rules — and mixing up which model they
belong to (operator ruling 2026-09-09, two SEPARATE rule sets):
  GPT Image 2 (legacy, own unchanged rules): auto -> 1K only; 1:1 never
  4K; 5:4/4:5/3:1/1:3/9:21 excluded at 2K/4K.
  GPT Image 2.6 (default): NO per-resolution exclusions — every enum member
  is legal at 1K, 2K and 4K. Its enum is auto, 1:1, 3:2, 2:3, 4:3, 3:4, 5:4,
  4:5, 16:9, 9:16, 2:1, 1:2, 21:9, 9:21, 3:1, 1:3, so 5:4, 4:5, 2:1, 1:2, 3:1,
  1:3 and 9:21 need no substitution and no second model. 27:16/16:27/9:8/8:9
  are not enum members at all and are rejected at every resolution.

MISTAKE 6: Text-to-image for a client logo.
  Logo/brand-mark work must be I2I with the logo as a reference. A T2I model
  invents a lookalike. QC checks I2I was actually used.

MISTAKE 7: Requesting 4K on Wan Pro image-to-image.
  Pro 4K resolution applies to text-to-image only.

MISTAKE 8: Passing a private input URL.
  Reference URLs must be publicly reachable (no login/cookies).
