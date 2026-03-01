╔══════════════════════════════════════════════════════════════╗
  MANDATORY TSP CHECK - READ THIS BEFORE ANYTHING ELSE
  DO NOT SKIP. DO NOT PROCEED UNTIL THIS CHECK IS COMPLETE.
╚══════════════════════════════════════════════════════════════╝

STEP 1: CHECK IF YOU HAVE BEEN TAUGHT THE TEACH YOURSELF PROTOCOL (TSP)

Before you read, learn, or execute ANY instruction in this document, you must
verify that you have already been taught the Teach Yourself Protocol (TSP).

HOW TO CHECK:
- Look in your AGENTS.md, TOOLS.md, or MEMORY.md for any mention of:
  "Teach Yourself Protocol" or "TSP"
- Look in your session context for prior TSP training
- Look for a tab called "Teach Yourself Protocol" in this same document

IF YOU HAVE BEEN TAUGHT TSP:
Proceed to the instructions below. Follow the TSP file storage structure.

IF YOU HAVE NOT BEEN TAUGHT TSP:
STOP IMMEDIATELY. Do not read further. Do not attempt to learn or execute
anything in this document. Tell the user exactly this:

  "I have not been taught the Teach Yourself Protocol yet. I cannot safely
   learn or execute these instructions until I have been taught TSP first.
   Please share the Teach Yourself Protocol tab with me before we proceed.
   Without TSP, I will bloat your core .md files and waste your tokens."

DO NOT PROCEED PAST THIS POINT WITHOUT TSP CONFIRMED.

══════════════════════════════════════════════════════════════════
  TSP FILE STORAGE INSTRUCTIONS (only read this if TSP confirmed)
══════════════════════════════════════════════════════════════════

WHEN LEARNING THIS DOCUMENT, FOLLOW THIS STRUCTURE:

1. SAVE FULL DOCUMENTATION TO MASTER FILES FOLDER
   Find the OpenClaw master files folder in ~/Downloads/. It may be named:
   - OpenClaw Master Files
   - OpenClaw Master Documents
   - OpenClaw Documents
   - openclaw-master-files
   - openclaw master files
   - OpenClaw Files
   - openclaw-documents
   - Any variation of "openclaw" + "master" or "files" or "documents"
   Search case-insensitively. One word or two words. Plural or singular.
   If no folder is found, create: ~/Downloads/OpenClaw Master Files/

   Save this full document content as a .md file in that folder.
   Example: ~/Downloads/OpenClaw Master Files/kie-ai-reference.md

2. DO NOT DUMP FULL CONTENT INTO CORE .MD FILES
   AGENTS.md, TOOLS.md, and MEMORY.md must stay lean.
   Only add a brief summary and a file path reference to where the full
   documentation lives. Never paste thousands of lines into core files.

3. USE THE LABELED SECTIONS BELOW TO KNOW WHAT GOES WHERE
   Look for sections marked:
   [ADD TO AGENTS.md]
   [ADD TO TOOLS.md]
   [ADD TO MEMORY.md]
   Only add what is labeled. Nothing else goes into core files.

EXECUTION DISCIPLINE - MANDATORY BEFORE YOU START
╚══════════════════════════════════════════════════════════════╝

These rules apply every single time you execute instructions from this document.
No exceptions. No shortcuts. No improvising.

RULE 1: READ EVERYTHING BEFORE YOU TOUCH ANYTHING
Read this entire document from top to bottom before executing a single step.
Do not start executing while still reading. Finish reading first. Then start.

RULE 2: DO NOT CHANGE TREVOR'S INTENT
These instructions say exactly what to do. Execute them exactly as written.
- Do NOT reinterpret steps
- Do NOT "improve" the instructions
- Do NOT skip steps because they seem unnecessary
- Do NOT add steps that are not in the document
- Do NOT change the order of steps
If a step says do X, do X. Not Y. Not a better version of X. X.

RULE 3: NEVER MODIFY THESE WITHOUT PERMISSION
- API keys - copy them exactly, character for character
- Terminal commands - run them exactly as written, no edits
- Config values - use the exact values specified
- Model names - use the exact names specified, spelling matters
- File paths - use the exact paths specified
If you are unsure whether something should be changed, the answer is NO.
Ask Trevor first. Do not guess. Do not assume.

RULE 4: BUILD YOUR CHECKLIST BEFORE EXECUTING
Before you run a single command or make a single change, create a numbered
checklist of every action this document requires you to take. Write it out.
Show it to the user before starting. Get confirmation. Then execute.

RULE 5: CHECK YOURSELF AGAINST THE CHECKLIST WHEN DONE
When you believe you are finished, go back to your checklist.
Verify every single item was completed. Check it off explicitly.
If anything was missed, complete it before telling the user you are done.
Do NOT tell the user you are done until the checklist is 100% complete.

RULE 6: REPORT WHAT YOU DID
When finished, give the user a clear summary:
- What was completed
- What commands were run
- What files were changed
- Any errors encountered and how they were resolved
- Confirmation that the checklist was fully satisfied

══════════════════════════════════════════════════════════════════

══════════════════════════════════════════════════════════════════
KIE.AI - HOW TO USE THE API (DAILY USAGE GUIDE)
══════════════════════════════════════════════════════════════════

This document explains how to use KIE.ai day to day. It covers the main
things you will do: generate images, generate videos, check on jobs, check
your credits, and upload files. If you have not set up KIE.ai yet, go to
INSTALL.md first.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOW KIE.AI WORKS (THE BIG PICTURE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

KIE.ai works like a job queue. Here is the basic flow:

1. You SUBMIT a job (for example, "generate an image of a sunset").
2. KIE.ai says "Got it, here is your job ID" and starts working on it.
3. You CHECK on the job using that job ID to see if it is done.
4. When it is done, you DOWNLOAD the result (an image URL or video URL).

This is called an "asynchronous" workflow. It means KIE.ai does not give
you the result immediately. It takes a few seconds to a few minutes
depending on what you asked for.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IMPORTANT: API ENDPOINTS ARE NOT OPENAI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

KIE.ai uses its OWN endpoints. Do NOT use OpenAI-style endpoints.

CORRECT endpoints:

| What You Want To Do     | Method | URL                                              |
|-------------------------|--------|--------------------------------------------------|
| Generate an image       | POST   | https://api.kie.ai/api/v1/jobs/createTask        |
| Check image/video job   | GET    | https://api.kie.ai/api/v1/jobs/recordInfo?taskId=XXX |
| Generate a VEO video    | POST   | https://api.kie.ai/api/v1/veo/generate           |
| Check VEO video status  | GET    | https://api.kie.ai/api/v1/veo/task?taskId=XXX    |
| Check credit balance    | GET    | https://api.kie.ai/api/v1/chat/credit            |
| Upload a file (base64)  | POST   | https://kieai.redpandaai.co/api/file-base64-upload |
| Upload a file (URL)     | POST   | https://kieai.redpandaai.co/api/file-url-upload  |
| Get download URL        | POST   | https://api.kie.ai/api/v1/common/download-url    |

WRONG - NEVER USE: /v1/images/generations (that is OpenAI format, not KIE.ai)

All requests require this header:
  Authorization: Bearer YOUR_API_KEY

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GENERATING IMAGES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

To generate an image, send a POST request to the createTask endpoint with
a model name and your prompt.

Available image models:

| Model Name          | What It Does                          | Cost    |
|---------------------|---------------------------------------|---------|
| nano-banana-pro     | Best image model. Text-to-image and   | ~$0.09  |
|                     | image-to-image. Supports references.  |         |
| google/nano-banana  | Text-to-image only. Simpler model.    | Varies  |
| google/nano-banana-edit | Edit existing images with prompts. | Varies  |
| flux-1.1-pro        | High quality image generation.        | Varies  |
| gpt-image-1.5       | GPT-based image generation.           | Varies  |

The most common model you will use is "nano-banana-pro". This is the
recommended default for all image generation.

How to submit an image job:

1. Send a POST request to: https://api.kie.ai/api/v1/jobs/createTask
2. Include the model name, your prompt, and optional settings like
   aspect ratio and resolution.
3. You will get back a taskId.
4. Use that taskId to check on the job (see "Checking Job Status" below).

Key settings for image generation:
- prompt: What you want the image to show (up to 10,000 characters for
  nano-banana-pro)
- aspect_ratio: The shape of the image. Options include:
  1:1 (square), 16:9 (widescreen), 9:16 (tall/portrait), 3:2, 2:3,
  4:3, 3:4, 4:5, 5:4, 21:9
- resolution: How detailed the image is. Options: 1K, 2K, 4K
- output_format: png or jpg
- image_input: (Optional) Up to 8 reference images as URLs. Use this
  when you want the AI to base the new image on existing images.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GENERATING VIDEOS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

KIE.ai supports several video models. The two main categories are:

VEO Videos (Google's VEO 3.1):
- Use the VEO-specific endpoint: POST https://api.kie.ai/api/v1/veo/generate
- Check status at: GET https://api.kie.ai/api/v1/veo/task?taskId=XXX
- Models: veo3 (Quality) and veo3_fast (Fast)
- Cost: about $0.40 per clip

Market Videos (Kling, Sora, Wan, etc.):
- Use the general endpoint: POST https://api.kie.ai/api/v1/jobs/createTask
- Check status at: GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=XXX
- Models include:
  - kling-3.0/video (Kling 3.0) - text-to-video, image-to-video, multi-shot
  - sora2 (Sora 2) - $0.15 per clip
  - sora2-pro (Sora 2 Pro) - $0.75 per clip
  - wan-2.1 (Wan video generation)

Key settings for VEO videos:
- model: "veo3" or "veo3_fast"
- prompt: What you want the video to show
- aspect_ratio: "16:9", "9:16", or "1:1"
- duration: Length of video in seconds
- generate_audio: true or false (whether to include AI-generated audio)

Key settings for Kling 3.0 videos:
- prompt: What you want the video to show
- duration: "3" through "15" (seconds, as a string)
- aspect_ratio: "16:9", "9:16", or "1:1"
- mode: "std" (standard) or "pro" (higher quality)
- sound: true or false
- image_urls: (Optional) Reference images for first/last frame
- multi_shots: true or false (for multi-scene videos)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CHECKING JOB STATUS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

After you submit a job, you need to check on it to see when it is done.

For images and market videos:
  GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=YOUR_TASK_ID

For VEO videos:
  GET https://api.kie.ai/api/v1/veo/task?taskId=YOUR_TASK_ID

The response will include a "state" field. Here is what each state means:

| State      | What It Means                                    |
|------------|--------------------------------------------------|
| waiting    | Your job is in line, waiting to start.            |
| queuing    | Your job is about to start processing.            |
| generating | Your job is being worked on right now.             |
| success    | Done! Your result is ready to download.            |
| fail       | Something went wrong. Check failCode and failMsg. |

Polling best practices (how often to check):
- First 30 seconds: Check every 2 to 3 seconds
- After 30 seconds: Check every 5 to 10 seconds
- After 2 minutes: Check every 15 to 30 seconds
- After 10 to 15 minutes: Something is probably wrong. Stop polling and
  investigate.

Rate limit for checking: Maximum 10 checks per second per API key.
Recommended: Wait 2 to 5 seconds between checks.

When the job succeeds, look for "resultJson" in the response. It contains
the URLs where you can download your generated content.

IMPORTANT: Generated file URLs typically expire after 24 hours. Download
your results as soon as they are ready.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CHECKING YOUR CREDIT BALANCE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

To see how many credits you have left:

  GET https://api.kie.ai/api/v1/chat/credit

The response will look like this:
  {"code":200,"msg":"success","data":100}

The number after "data" is your remaining credit balance.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
UPLOADING FILES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Some tasks (like image-to-video or editing images) require you to upload
a file first. KIE.ai has a separate upload service.

Upload via base64:
  POST https://kieai.redpandaai.co/api/file-base64-upload

  Send the file as base64 data in the request body along with an upload
  path and optional filename.

Upload via URL:
  POST https://kieai.redpandaai.co/api/file-url-upload

  Send a publicly accessible URL and KIE.ai will download the file.

Important notes about uploads:
- Uploaded files are temporary. They are automatically deleted after 3 days.
- Maximum recommended file size: 100 MB
- Supported formats: JPEG, PNG, WebP for images; MP4, MOV for videos

After uploading, you get back a download URL. Use that URL as the
"image_urls" or "input_urls" value in your generation requests.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GETTING DOWNLOAD URLS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

If you have a KIE-generated file URL and need a temporary download link:

  POST https://api.kie.ai/api/v1/common/download-url

  Send the original URL in the request body:
  {"url": "https://tempfile.xxx..."}

This gives you a temporary download URL that is valid for 20 minutes.
Only works with KIE-generated URLs, not external URLs.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RATE LIMITS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

KIE.ai has rate limits to prevent overloading their servers:

- Creating jobs: Up to 20 new requests per 10 seconds per account
- Checking job status: Up to 10 checks per second per API key
- If you exceed limits, you get a 429 error (rate limited). Wait a few
  seconds and try again.
- You can have about 100 or more jobs running at the same time.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ERROR CODES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

When something goes wrong, KIE.ai returns an error code. Here is what
each one means:

| Code | What It Means                                     |
|------|---------------------------------------------------|
| 200  | Success. Everything worked.                        |
| 401  | Unauthorized. Your API key is missing or wrong.    |
| 402  | Not enough credits. Add more at kie.ai/pricing.    |
| 404  | Not found. The task ID does not exist.              |
| 422  | Validation error. Something in your request is      |
|      | wrong (bad parameter, missing required field).      |
| 429  | Rate limited. You are sending too many requests.    |
|      | Wait a few seconds and try again.                   |
| 455  | Service unavailable. KIE.ai is down for maintenance.|
| 500  | Server error. Something broke on KIE.ai's side.     |
| 501  | Generation failed. The AI could not create what you  |
|      | asked for. Try a different prompt.                   |
| 505  | Feature disabled. This feature is not currently      |
|      | available.                                           |

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USING WEBHOOKS (ADVANCED)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Instead of checking on jobs manually (polling), you can set up a webhook.
A webhook is a URL on your server that KIE.ai will call when a job is done.

To use webhooks:
1. Include "callBackUrl" in your job creation request.
2. KIE.ai will POST to that URL when the job completes.
3. Verify the webhook signature using your webhookHmacKey from
   https://kie.ai/settings

Signature verification:
- Algorithm: HMAC SHA256
- Data to sign: taskId + "." + timestampSeconds
- Result is base64 encoded
- Check the X-Webhook-Timestamp and X-Webhook-Signature headers

This is optional. Polling works fine for most use cases.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FULL API REFERENCE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

For the complete API documentation with every model, every parameter, and
every endpoint, refer to the master reference file:

  kie-setup-full.md (in this same folder)

That file contains the full 176K+ character API documentation covering
all models: Kling 3.0, Kling 2.6, Sora 2, VEO 3.1, Flux, Nano Banana,
GPT Image, Wan, Hailuo, Pika, and more.
