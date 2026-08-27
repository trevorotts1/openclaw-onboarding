# KIE Video API Integration Patterns & Protocol Reference

Authoritative Source: First-party research dated 2026-08-26 (`docs.kie.ai`, curl-verified).

---

## 1. Unified Market API (`api_family: "kie-market"`)

All generic KIE video models (Wan, Kling, Seedance, PixVerse, MiniMax, HappyHorse, Gemini Omni) share a standardized asynchronous job protocol.

### A. Create Task: `POST https://api.kie.ai/api/v1/jobs/createTask`
- **Headers:**
  - `Authorization: Bearer $KIE_API_KEY`
  - `Content-Type: application/json`
- **Payload Structure:**
  ```json
  {
    "model": "wan/3-0-video",
    "callBackUrl": "https://callback.blackceo.com/api/kie/callback",
    "input": {
      "prompt": "Full production prompt string...",
      "duration": 5,
      "resolution": "1080P",
      "aspect_ratio": "16:9",
      "audio": true
    }
  }
  ```
- **Response Shape (HTTP 200 Accepted):**
  ```json
  {
    "code": 200,
    "msg": "success",
    "data": {
      "taskId": "task_wan3_1765187774173"
    }
  }
  ```
- **Semantics:** HTTP 200 indicates task **acceptance and queuing**, NOT generation completion. All video jobs are asynchronous.

### B. Query Task: `GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId={taskId}`
- **Headers:** `Authorization: Bearer $KIE_API_KEY`
- **Task Lifecycle States:**
  - `waiting`: Task registered, awaiting execution slot.
  - `queuing`: Queued in provider inference scheduler.
  - `generating`: Active diffusion/rendering.
  - `success`: Video generation complete; `resultJson` is populated.
  - `fail`: Job failed; `failCode` and `failMsg` are populated.
- **Success Response Data Fields:**
  ```json
  {
    "code": 200,
    "msg": "success",
    "data": {
      "taskId": "task_wan3_1765187774173",
      "model": "wan/3-0-video",
      "state": "success",
      "param": "{\"prompt\":\"...\"}",
      "resultJson": "{\"resultUrls\":[\"https://file.aiquick.net/videos/20260826/out.mp4\"]}",
      "failCode": "",
      "failMsg": "",
      "costTime": 42150,
      "completeTime": 1771987654000,
      "creditsConsumed": 12
    }
  }
  ```

---

## 2. Dedicated API Families

Dedicated families **must never be routed through `createTask`**. They employ dedicated endpoint paths, distinct request shapes, and custom status methods.

### A. Runway API (`api_family: "runway-dedicated"`)
- **Endpoints:**
  - Create: `POST https://api.kie.ai/api/v1/runway/generate`
  - Query: `GET https://api.kie.ai/api/v1/runway/record-detail?taskId={taskId}`
  - Extend: `POST https://api.kie.ai/api/v1/runway/extend`
- **Create Payload:**
  ```json
  {
    "prompt": "Cinematic sequence...",
    "imageUrl": "https://domain.com/start_frame.jpg",
    "duration": 5,
    "quality": "1080p",
    "aspectRatio": "16:9",
    "waterMark": "",
    "callBackUrl": "https://callback.blackceo.com/api/runway"
  }
  ```
- **Rules & Constraints:**
  - `duration`: `5` or `10`. `1080p` only supports `5` seconds (`10` seconds is restricted to `720p`).
  - `aspectRatio`: Invalid when `imageUrl` is provided (image aspect ratio takes precedence).
  - `model`: No model field in request payload.

### B. Veo 3.1 API (`api_family: "veo-dedicated"`)
- **Endpoints:**
  - Create: `POST https://api.kie.ai/api/v1/veo/generate`
  - Query: `GET https://api.kie.ai/api/v1/veo/record-info?taskId={taskId}`
  - 1080P Upgrade: `GET https://api.kie.ai/api/v1/veo/get-1080p-video?taskId={taskId}&index=0`
  - 4K Upgrade: `POST https://api.kie.ai/api/v1/veo/get-4k-video` (`{"taskId": "...", "index": 0}`)
  - Extend: `POST https://api.kie.ai/api/v1/veo/extend`
- **Create Payload:**
  ```json
  {
    "model": "veo3_fast",
    "prompt": "Documentary aerial...",
    "generationType": "TEXT_2_VIDEO",
    "duration": 8,
    "aspectRatio": "16:9",
    "callBackUrl": "https://callback.blackceo.com/api/veo"
  }
  ```
- **Model Enums:** `veo3` (Quality), `veo3_fast` (Fast, default), `veo3_lite` (Lite).
- **Generation Types:** `TEXT_2_VIDEO`, `FIRST_AND_LAST_FRAMES_2_VIDEO`, `REFERENCE_2_VIDEO` (1–3 images, `veo3_fast`/`veo3_lite` only, 8s only).
- **Audio:** Always-on background audio; no toggle parameter.
- **Credit Upgrade Notice:** 4K generation requires dedicated post-processing via `POST /api/v1/veo/get-4k-video` and consumes ~2x Fast mode credits.

---

## 3. Webhook Callback Protocol (Skill 46 Relay)

Production environments should prefer public HTTPS callbacks over polling.

### A. Payload & HMAC Verification
- **Header:** `X-Webhook-Signature: {Base64_HMAC_SHA256}`
- **Header:** `X-Webhook-Timestamp: {Unix_Timestamp_Seconds}`
- **Signature Calculation:**
  ```python
  import hmac, hashlib, base64

  expected = base64.b64encode(
      hmac.new(
          webhook_secret.encode("utf-8"),
          f"{task_id}.{timestamp}".encode("utf-8"),
          hashlib.sha256
      ).digest()
  ).decode("utf-8")
  ```
- **Callback Response Requirement:** Endpoint must return `{"code": 200, "msg": "success"}` within 15 seconds. After 3 failed delivery attempts, KIE halts webhook retries.

---

## 4. Polling Strategy & Backoff Intervals

When webhooks are unavailable, poll using stepped exponential backoff:

```
[Dispatch] ──(Wait 3s)──► [Check 1] ──(Wait 5s)──► [Check 2] ──(Wait 10s)──► [Check 3+] ──(Wait 15s)──► [Timeout]
```

- **Generic Market Video:** Initial delay 3.0s; backoff: 5s, 10s, 15s; max wait: 15 minutes.
- **Runway Dedicated:** Recommended polling interval: ~30s.
- **Veo 1080P / 4K Upgrades:** Recommended interval: 20–30s for 1080P (1–3 min total); 30–60s for 4K (5–10 min total).
- **429 Handling:** HTTP 429 means rate-limited at the account level (limit: 20 requests per 10s). Sleep minimum 5 seconds before retrying. Never hammer endpoints sub-second.

---

## 5. Rate Limits & Media Retention

- **Account Rate Limit:** Up to 20 generation requests per 10 seconds; 100+ concurrent running tasks.
- **Media Retention Policy:**
  - Generated video files are retained on KIE storage for **14 days**, after which they are permanently deleted (`expireFlag: 1`).
  - Temporary download URLs expire in **~24 hours**.
  - **Storage Rule:** Downstream pipelines must immediately download and persist generated media to permanent storage (S3 / R2 / local disk) upon completion.
