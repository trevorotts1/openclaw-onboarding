# Skill 37 — Runtime Instructions

PRD-2.8: GATED PIPELINE. Seven explicit per-deliverable legs. Pre-flight validates KEYS AND TELEGRAM before generation starts. Org-chart connector-tree is ASSERTED programmatically (not just documented). Dedicated closeout-resume cron (loop registry). Fleet sweep for re-delivery.

This is the execution guide. Use it when `.workforce-build-state.json` shows the closeout is due (or in flight). Follow the steps EXACTLY in order. The state file is the contract — never skip a state write.

---

## MANDATORY: Rate + QC every deliverable (the 8.5 Quality Gate)

**Rate + QC every closeout deliverable; do not deliver below 8.5; iterate until it passes. See QUALITY-GATE.md.**

Before any artifact reaches the client (Telegram, media library, GHL, Drive), the agent MUST self-rate it 1-10 against the rubric in `QUALITY-GATE.md` and QC it. The per-artifact workflow is: generate -> self-rate 1-10 -> QC checks -> if score < 8.5 OR any QC check fails, iterate/regenerate and re-rate -> only when >= 8.5 AND all QC checks pass, deliver. The agent writes its score + QC verdict + a one-line justification into `.qualityRatings.<org_chart|flow_diagram|closeout_docs>.{score,qc,note}` in the state file; `run-closeout.sh` loops the generator up to `ZHC_QUALITY_MAX_ATTEMPTS` (default 3) and HOLDS (does not deliver) anything that cannot clear `ZHC_QUALITY_MIN` (default 8.5), flagging it for human review. The org chart's #1 requirement is a TRUE reporting tree with visible connector lines (Owner -> CEO -> clusters -> departments), not a grid of cards. Below 8.5 is never shipped.

---

## 0. Pre-flight Checks (PRD-2.8: FAIL LOUD at start, not silently mid-way)

`run-closeout.sh` validates ALL of the following BEFORE any KIE.AI/Notion/Telegram call fires. A missing key discovered after infographic generation would waste credits and leave the client with a broken experience. The pre-flight is the mandatory gate.

Before starting Step 1, verify ALL of the following:

1. `.workforce-build-state.json` exists and has:
   - `buildCompletedAt != null` — Skill 23 is actually done.
   - `closeoutStatus` is `pending` or `generating` (NOT `done` and NOT `sent`).
2. `KIE_API_KEY` env var is set — **LOUD FAIL** if empty.
3. `NOTION_API_TOKEN` env var is set — **LOUD FAIL** if empty.
4. **Telegram gateway health** (`openclaw gateway status` returns healthy/running/ok) — **LOUD FAIL** if gateway unreachable. Sending 6 celebration messages to a non-functional gateway is the exact silent mid-way failure mode this gate prevents. Set `ZHC_SKIP_TG_PREFLIGHT=1` only in unit tests.
5. `jq` is on PATH.
6. `curl` and `openclaw` CLI are on PATH.
7. The scripts in `scripts/` exist and are executable.

If ANY check fails, write `closeoutStatus: "failed"` + `closeoutFailureReason: "preflight: <which check>"` to the state file and STOP. The dedicated closeout-resume cron will retry on its next fire (every 15 min). If preflight has been failing for 3 consecutive resume invocations, escalate to the operator's Telegram chat (`env.vars.OPERATOR_TELEGRAM_CHAT_ID`, default `5252140759`). Resolve via:
```bash
source "$(if [ -d /data/.openclaw ]; then echo /data/.openclaw; else echo $HOME/.openclaw; fi)/skills/shared-utils/operator-chat-id.sh"
openclaw message send --channel telegram --target "$OPERATOR_CHAT_ID" --message "..."
```

---

## 1. State Machine

```
closeoutStatus values (state-file enum):

  pending     ← Skill 23 master orchestrator sets this when buildCompletedAt is written
   ↓
  generating  ← Skill 37 sets this BEFORE Step 1; ALSO registers the dedicated
                closeout-resume cron (resume-closeout-cron.sh, every 15 min, loop registry)
   ↓
  sent        ← Skill 37 sets this after Step 6's last Telegram message is delivered
   ↓
  done        ← Skill 37 sets this after ALL 7 closeoutDeliverables legs confirmed +
                resume cron self-removed (loop-registry kill condition)

  partial     ← Soft-only failures (video/notion/n8n). Telegram delivered.
                closeoutPartialArtifacts lists what failed. Resume cron retries.

  failed      ← Hard failures (infographic-1/2, Telegram) or telegram-unconfirmed.
                closeoutFailureReason captures the specific step.
                The dedicated closeout-resume cron retries every 15 min.

  blocked-floor-incomplete    ← verify-zhc-standard rc=3 (dept floor not met on disk)
  blocked-libraries-incomplete ← verify-zhc-standard rc=4/5 (role/SOP library not done)
```

`closeoutStartedAt` is set on first transition `pending → generating`.
`closeoutCompletedAt` is set on transition `sent → done`.

### PRD-2.8: 7 per-deliverable leg fields (`.closeoutDeliverables`)

Each field is written as the corresponding step completes. The dedicated resume cron fires until all 7 are non-null and non-false. This makes the pipeline observable and resumable at leg granularity.

| Field | Written when | Type |
|-------|-------------|------|
| `notionTreeUrl` | Notion step passes 8.5 gate | string URL |
| `infographic1Url` | Org chart passes 8.5 gate + connector-tree assertion | string URL |
| `infographic2Url` | Flow diagram passes 8.5 gate | string URL |
| `celebrationVideoUrl` | Video generated + byte-downloaded | string URL |
| `telegramSequenceSent` | All 6 Telegram messages delivered + confirmed | boolean |
| `ccUrlDelivered` | CC URL present and included in Message 6 | boolean |
| `n8nWired` | n8n webhook POST confirmed, or `"skipped"` if N8N_WEBHOOK_URL absent | bool/string |

### PRD-2.8: Dedicated Closeout Resume Cron (Loop Registry)

`resume-closeout-cron.sh` is registered via `openclaw cron add` at the `generating` transition (separate from the Skill 23 `workforce-build-resume` cron):

- **Trigger:** every 15 minutes
- **Goal check:** reads `.closeoutDeliverables` — cheap, zero tokens
- **Decision:** if any of the 7 legs is incomplete, dispatches `[CLOSEOUT-RESUME]` self-ping
- **Kill condition:** self-removes when all 7 legs are done|waived OR max runs (48 = 12h) exceeded
- **Loop registry entry:** `.closeoutResumeUuid` in state (used for self-removal)
- **Escalation:** operator Telegram alert every 3rd consecutive resume attempt

---

## 2. The 7-Step Pipeline

All steps run via `scripts/run-closeout.sh` as the top-level orchestrator. You CAN invoke individual scripts manually for debugging, but normal flow goes through `run-closeout.sh`.

### Step 1 — Fire Skill 32 (Command Center)

**Goal:** Ensure the Command Center is built and capture its URL.

1. Read `commandCenterStatus` from state file.
2. If `commandCenterStatus == "done"` AND `commandCenterUrl` is set, skip to Step 2.
3. Otherwise: set `commandCenterStatus: "building"`, atomic write.
4. Invoke Skill 32's installer per `~/.openclaw/skills/32-command-center-setup/INSTRUCTIONS.md` (run `setup-command-center.sh` if present, else follow the documented manual flow).
5. On success: read the Command Center URL (typically `http://localhost:4000` on Mac, or the published URL on VPS). Capture into `commandCenterUrl`.
6. Set `commandCenterStatus: "done"`, atomic write.

**Retries:** 3 total. If Skill 32 fails 3 times, set `commandCenterStatus: "failed"` and `closeoutFailureReason: "command-center: <last error>"`, then STOP. Do NOT proceed to Step 2 — the Notion doc and the final Telegram message both reference the Command Center URL, and the celebration is broken without it.

### Step 2 — Generate Infographic #1 (Workforce Structure)

**Goal:** Produce a branded org-chart visualization for the client.

**This step uses local HTML + Playwright Chromium, NOT an AI image model.** Diffusion models cannot reliably render small text labels (early fleet closeout attempts came back with garbled department names). HTML + CSS gives perfect text, is free per render, and is fully deterministic.

1. If `infographic1Url` already set, skip.
2. Invoke `scripts/generate-infographics.sh structure`. The script:
   - Reads `companyName`, `ownerName`, `agentName`, and the full department list from `.workforce-build-state.json` (tolerates both array and keyed-object shapes for `.departments`).
   - Writes a renderer input JSON to `$OC_ROOT/workspace/.zhc-inf1-input.json`.
   - Invokes `node templates/workforce-org-chart/render.mjs --input <input.json> --output <output.png>`.
   - The renderer fills `templates/workforce-org-chart/index.html.template`, classifies each department into one of 4 visual clusters via `cluster-classifier.js` (Operations / Revenue / Creative / Technology), and screenshots at 1920x1080 via Playwright Chromium.
3. On success:
   - Writes `infographic1Url = "file://<output.png>"` AND `infographic1LocalPath = "<output.png>"` to state, atomic.
   - The Telegram step prefers the local path and uploads bytes via `openclaw message send --media`, which gets inline rendering on Telegram.

**Prerequisite (one-time, per container):**
```bash
(cd ~/.openclaw/skills/37-zhc-closeout/templates/workforce-org-chart && npm install && npx playwright install chromium)
```
The install.sh / update-skills.sh paths run this automatically on fresh installs.

**Retries:** the renderer is deterministic - it either succeeds or fails on environment (no Node / no Chromium). On failure: `closeoutFailureReason: "infographic-1: <last error>"`, mark `closeoutStatus: "failed"`, STOP.

### Step 3 — Generate Infographic #2 (How Work Flows)

Stylized flow diagram. Less text-heavy than Step 2, so AI image gen is still appropriate.

1. If `infographic2Url` already set, skip.
2. Fill `templates/infographic-2-prompt.md` with the same placeholders + one extra:
   - `{{EXAMPLE_TASK}}` — pulled from `workforce-interview-answers.md`; if not present, use a generic task seeded by the client's industry (e.g. "Launch a new email campaign" for a marketing-heavy client; "Onboard a new patient" for a healthcare client).
3. Invoke `scripts/generate-infographics.sh workflow`. The script POSTs to KIE.AI `/jobs/createTask` with:
   - Primary model: `gemini-3-1-flash-image` (Nano Banana 2) - much better at text rendering than the prior `gpt-image-2`. Override via env `ZHC_IMAGE_MODEL`.
   - Fallback model (attempt 3): `gpt-image-2-text-to-image`.
4. Write `infographic2Url` to state file.

**Retries:** 3 total (attempts 1-2 primary, attempt 3 fallback). Failure path same as Step 2.

### Step 4 — Generate Celebration Video

**Model selection (read this carefully):**

- **Default for THIS skill (Skill 37 celebration):** `gemini-omni-video` via KIE.ai. Endpoint: `POST /api/v1/jobs/createTask` + `GET /api/v1/jobs/recordInfo`. Reason: Gemini Omni accepts an image reference (we hand it the just-rendered workforce-chart PNG via `image_urls`), so brand colors and the CEO agent name carry through into the video.
- **Fallback (and the general-purpose default elsewhere in OpenClaw):** `veo3_fast` (or `veo3`) via KIE.ai. Endpoint: `POST /api/v1/veo/generate` + `GET /api/v1/veo/record-info`. Veo 3.1 cannot accept image guidance, which is why it is the fallback here even though it is the project-wide default everywhere else.

Override via env `ZHC_CELEBRATION_VIDEO_MODEL` (default `gemini-omni-video`; also accepts `veo3` / `veo3_fast`).

1. If `celebrationVideoUrl` already set AND `celebrationVideoLocalPath` exists on disk, skip.
2. Fill `templates/veo-prompt.txt` with `{{COMPANY_NAME}}`, `{{OWNER_NAME}}`, `{{AGENT_NAME}}`, `{{INDUSTRY}}`.
3. Invoke `scripts/generate-celebration-video.sh`. The script:
   - Picks the model based on `ZHC_CELEBRATION_VIDEO_MODEL` (default `gemini-omni-video`).
   - Snaps `ZHC_VIDEO_DURATION` to a valid value for the chosen model (Gemini Omni: 4-8, default 4; Veo: 4/6/8, default 8).
   - If using `gemini-omni-video` AND `infographic1Url` is a real public URL (not `file://`), passes it as `input.image_urls[0]` so brand carries through.
   - Submits the job, polls the appropriate endpoint until success.
   - On attempt 3, if primary was `gemini-omni-video`, falls back to `veo3_fast`.
4. **Always downloads the MP4 bytes to disk** at `$OC_ROOT/workspace/.zhc-celebration-video.mp4` via `curl -fL --max-time 180`, verifies size > 0, and (if `file` is on PATH) sniff-checks for `ISO Media`. Writes both `celebrationVideoUrl` (remote) and `celebrationVideoLocalPath` (local) to state.
5. The Telegram step ALWAYS prefers the local path and uploads bytes via `openclaw message send --media`, which produces an inline `sendVideo` upload rather than a download-card-style link preview.

**Why the local download is mandatory:** the KIE CDN at `tempfile.aiquickdraw.com` returns `content-disposition: attachment`, which makes Telegram render the message as a download card if a URL is passed directly. Uploading bytes via multipart `sendVideo` is the only way to guarantee inline playback.

**Retries:** 3 with model fallback. On exhaustion: `closeoutFailureReason: "celebration-video: <last error>"`, mark `closeoutStatus: "failed"`, STOP.

### Step 5 — Build the Notion Page Tree

1. If `notionRootPageUrl` already set, skip.
2. Read `templates/notion-page-tree.json`. This is the 9-section spec. Fill placeholders from state + interview answers + the infographic URLs from Steps 2–3.
3. Invoke `scripts/create-notion-closeout.sh`. The script:
   - Reads `NOTION_API_TOKEN` from env.
   - Resolves the **destination parent page**:
     - First: env var `NOTION_CLOSEOUT_PARENT_PAGE_ID` (if set)
     - Else: searches Notion for a page titled "OpenClaw" or "BlackCEO" in the client's workspace and uses that
     - Else: creates a new top-level page in the workspace root
   - Idempotency check: searches for an existing page titled `"Your Zero-Human Company — {{COMPANY_NAME}}"`. If found, returns its URL (skip create).
   - Creates the root page, then iterates 9 sections + nested department/role sub-pages.
   - Embeds infographics #1 and #2 via the Notion `image` block (external URL = KIE.AI result URL).
   - Returns the root page URL.
4. Write `notionRootPageUrl` to state file.

**Retries:** 3 per page-create call (Notion API can transient-fail). On total exhaustion: `closeoutFailureReason: "notion: <last error>"`, mark `closeoutStatus: "failed"`, STOP.

### Step 6 — Telegram Delivery (the celebration)

This is the only step that the OWNER sees. **All prior steps were silent.** Goal: paced, celebratory, not a spam dump.

**Every artifact resolves to a REAL openable LINK in the message — never "we saved it in folder X."** Each image and the video are sent as INLINE media (local bytes via multipart, so they render in-thread, not as a download card), and each one ALSO carries a durable "🔗 Open it directly:" link — the GHL media-library PUBLIC URL (`storage.googleapis.com/msgsndr/...`, openable with no GHL login) when the client has GHL, falling back to the remote artifact URL otherwise. The Notion page, Command Center, and GHL media library are posted as plain openable URLs.

1. Invoke `scripts/send-telegram-celebration.sh`. The script reads state and sends 6 sequenced messages to `ownerChat`. Every image/video slot prefers the durable GHL public URL as its openable link (`openable_link()` resolves GHL public URL → remote http URL → none):

   **Message 1 — Announcement (10-second pause after):**
   ```
   🎉 {{OWNER_NAME}}, your zero-human company is built.

   Over the past few hours your AI workforce has been getting itself set up.
   {{N_DEPARTMENTS}} departments. {{N_ROLES}} AI employees. All hired, briefed,
   and ready to work for you.

   Here's what I want to show you:
   ```

   **Message 2 — Infographic #1 (sendPhoto, 5-second pause):**
   - Photo: `infographic1Url`
   - Caption: `"📊 Your workforce structure — how your AI company is organized."`

   **Message 3 — Infographic #2 (sendPhoto, 5-second pause):**
   - Photo: `infographic2Url`
   - Caption: `"⚙️ How the work flows — from a task you give me, all the way to a finished output."`

   **Message 4 — Celebration video (sendVideo, 8-second pause):**
   - Video: `celebrationVideoUrl`
   - Caption: `"🎬 A quick celebration — congratulations on launching {{COMPANY_NAME}}'s zero-human workforce."`

   **Message 5 — Notion doc (sendMessage, 3-second pause):**
   ```
   📕 Your full closeout doc is in your Notion workspace:
   {{NOTION_ROOT_PAGE_URL}}

   It explains your departments, your AI employees, the communication
   hierarchy, the Six Sigma framework we'll use to keep improving, the
   Book-to-Persona system that picks how each task is handled, and your
   First 7 Days action plan. Read it when you have 15 minutes.
   ```

   **Message 6 — Command Center URL + GHL media links (sendMessage):**
   ```
   🎛️ Your BlackCEO Command Center:
   {{COMMAND_CENTER_URL}}

   This is where you'll talk to your CEO (me), watch tasks move across
   the Kanban board, and check in on every department. Open it in your
   browser and bookmark it.

   📁 Your celebration media is also saved in your Convert and Flow media
   library — open any of these directly:
   - 🎬 Celebration video: {{GHL_VIDEO_PUBLIC_URL}}
   - 📊 Workforce structure: {{GHL_INFOGRAPHIC1_PUBLIC_URL}}
   - ⚙️ How work flows: {{GHL_INFOGRAPHIC2_PUBLIC_URL}}
   (Browse them all in your account: {{GHL_MEDIA_LIBRARY_URL}})

   When you're ready, just message me with the first thing you want done.
   I'm standing by.
   ```
   The GHL block is appended ONLY when the media upload produced public URLs (client has GHL). With no GHL, the message is just the Command Center URL + the standing-by close.

2. After Message 6 successfully delivers (each message records a REAL gateway messageId):
   - Set `closeoutStatus: "sent"`, atomic write.
   - **Delivery confirmation gate (anti-faking):** `run-closeout.sh` then runs `scripts/verify-telegram-delivery.sh`, which cross-checks every required captured `messageId` against the gateway sent-registry (`agents/main/sessions/sessions.json.telegram-sent-messages.json`). `done` may be written ONLY when every required messageId is confirmed present (or has legitimately aged out of the rolling window). If any required messageId is missing-and-recent, the closeout is marked `failed` with `closeoutFailureReason: "telegram-unconfirmed: msg <n>"` and the resume cron retries. A 0-exit `openclaw message send` is NOT proof of delivery.
   - Only then set `closeoutCompletedAt: <now-ISO-8601>` and `closeoutStatus: "done"`, atomic write.

### Step 5.5 — Conditional GHL media upload (runs BEFORE Telegram)

`run-closeout.sh` runs `scripts/upload-ghl-media.sh` at Step 5.5 — **before** the Telegram step — so the durable per-file public URLs are in state in time to be posted as the openable links in the celebration messages.

- **Trigger:** the client has the GHL / Convert-and-Flow skill installed OR a LOCATION PIT/location id is present. It resolves the LOCATION PIT from `GOHIGHLEVEL_API_KEY` (canonical) or `GHL_API_KEY` (legacy alias), and the location id from `GOHIGHLEVEL_LOCATION_ID` / `GHL_LOCATION_ID` / build-state `.ghlLocationId`. The PIT is verified against `GET /locations/<id>` before any upload. Media uploads REQUIRE the LOCATION PIT (the Agency PIT 401s on media ops).
- **Upload:** POSTs the real local closeout media (the two infographics + celebration video) to `POST /medias/upload-file` (`Version: 2021-07-28`) with form fields `file`, `locationId`, `name`, `hosted=false`, and `parentId=<folder>` when a folder id is set.
- **Folder:** GHL **folder CREATE via API is broken** (TOOLS.md ground truth) — the script never POSTs a folder-create. To group the media, pre-create a "ZHC Closeout — <Company>" folder in the Convert and Flow UI and export its id as `GHL_MEDIA_FOLDER_ID`; the field name on the upload is **`parentId`** (NOT `folderId`). With no folder id, files land in the media root (still fully shareable).
- **Output:** each upload returns `{"fileId","url":"https://storage.googleapis.com/msgsndr/..."}`. That `url` is a PUBLIC, openable GCS link. The script writes `ghlVideoPublicUrl`, `ghlInfographic1PublicUrl`, `ghlInfographic2PublicUrl`, `ghlMediaUrls[]`, `ghlMediaFileIds[]`, and the in-app `ghlMediaLibraryUrl` to state.
- **Skips gracefully** — writing a `ghlMediaUploaded` reason (`skipped-no-ghl` / `skipped-no-pit` / `skipped-pit-verify-failed` / `skipped-no-files`) — when GHL or a working PIT is absent. Never blocks closeout.

### Step 6.5 — n8n Wire-up (PRD-2.8, optional, non-blocking)

**Goal:** Notify the client's n8n instance (webhook) that the ZHC build + closeout is complete.

Runs AFTER Telegram delivery (the owner already has their celebration). The payload carries: company slug, agent name, CC URL, infographic/video URLs, Notion URL, and owner Telegram chat ID. Fires `scripts/wire-n8n-closeout.sh`.

- **Skip conditions:** `N8N_WEBHOOK_URL` env var not set → graceful skip (writes `n8nStatus="skipped"`). `ZHC_SKIP_N8N=1` → explicit skip. `n8nStatus` already `"wired"` → idempotent skip.
- **Retry:** 3 attempts with exponential backoff. On failure: `n8nStatus="failed"` (soft — closeout continues).
- **State write:** `closeoutDeliverables.n8nWired = true|"skipped"` written by the script.
- **Non-blocking:** n8n failure is a soft failure (same as video/notion). The closeout does NOT block on n8n.

### Step 7 (success path only) -- Operator summary

After every artifact cleared the 8.5 gate, was delivered, the phantom-closeout guard passed, AND the Telegram delivery was confirmed against the sent-registry, `run-closeout.sh` runs one final step BEFORE writing `closeoutStatus: "done"`:

1. `scripts/send-operator-summary.sh`: sends Trevor (`ZHC_OPERATOR_CHAT_ID`, default `5252140759`) a single Telegram message via the OpenClaw gateway with the DURABLE openable LINK to every delivered artifact — preferring the GHL public URL, then Drive, then the remote URL — (dashboard, both infographics, celebration video, Notion page, GHL media library). Idempotent via `operatorSummarySentAt`.

**Retries per message:** 3 (with 2s/4s/8s backoff). If a message fails 3x:
- If it's Message 1 (the announcement), abort the whole delivery, mark `closeoutStatus: "failed"`, set `closeoutFailureReason: "telegram-message-1: <error>"`. Resume cron will retry on next fire.
- If it's Messages 2–6, log the failure but CONTINUE to the next message. After all attempted, if any failed, set `closeoutStatus: "failed"` with a summary listing which messages failed. The resume cron will pick up failed messages individually on its next fire (Step 6 is idempotent per-message via the `messagesDelivered` array). Each delivered slot is recorded as an OBJECT carrying its real gateway messageId — `{ "n": 1, "messageId": "51678", "chatId": "<owner>", "ts": "<iso>" }` — and a slot that the gateway accepted-but-returned-no-id is recorded as `{ "n": <slot>, "status": "send-failed" }` and is NOT counted delivered (so it is retried). A slot is "delivered" only when it carries a non-empty messageId.

---

## 3. State-File Schema Additions (v10.14.17)

Skill 37 adds these top-level fields to `.workforce-build-state.json`:

```json
{
  "closeoutStatus": "pending|generating|partial|sent|done|failed",
  "closeoutStartedAt": "2026-05-23T20:30:00Z",
  "closeoutCompletedAt": "2026-05-23T20:45:00Z",
  "closeoutFailureReason": "command-center: <last error>",

  "commandCenterStatus": "pending|building|done|failed",
  "commandCenterUrl": "http://localhost:4000",

  "n8nStatus": "pending|wired|skipped|failed",
  "n8nUrl": "https://client.n8n.cloud",

  "infographic1Url": "file:///data/.openclaw/workspace/.zhc-inf1-output.png",
  "infographic1LocalPath": "/data/.openclaw/workspace/.zhc-inf1-output.png",
  "infographic2Url": "https://tempfile.kie.ai/...",
  "celebrationVideoUrl": "https://tempfile.kie.ai/...",
  "celebrationVideoLocalPath": "/data/.openclaw/workspace/.zhc-celebration-video.mp4",
  "celebrationVideoModel": "gemini-omni-video",
  "notionRootPageUrl": "https://www.notion.so/...",

  "closeoutDeliverables": {
    "notionTreeUrl": "https://www.notion.so/...",
    "infographic1Url": "file:///data/.openclaw/workspace/.zhc-inf1-output.png",
    "infographic2Url": "https://tempfile.kie.ai/...",
    "celebrationVideoUrl": "https://tempfile.kie.ai/...",
    "telegramSequenceSent": true,
    "ccUrlDelivered": true,
    "n8nWired": "skipped"
  },

  "closeoutResumeUuid": "abc123-...",
  "closeoutResumeRegisteredAt": "2026-05-23T20:30:00Z",

  "qcOrgChartConnectorTree": {
    "verdict": "pass",
    "note": "connector-tree confirmed via HTML analysis",
    "verifiedAt": "2026-05-23T20:32:00Z",
    "rc": 0,
    "connectorFound": 1,
    "cardGridDetected": 0,
    "hierarchyLevels": 3
  },

  "messagesDelivered": [
    { "n": 1, "messageId": "51678", "chatId": "5252140759", "ts": "2026-05-23T20:44:00Z" },
    { "n": 6, "messageId": "51690", "chatId": "5252140759", "ts": "2026-05-23T20:44:40Z" }
  ],
  "telegramDeliveryVerification": {
    "status": "pass",
    "rc": 0,
    "verifiedAt": "2026-05-23T20:45:00Z",
    "requiredSlots": "1,6,7",
    "results": [ { "n": 1, "messageId": "51678", "required": true, "verdict": "pass-present", "note": "..." } ]
  }
}
```

> v10.15.19/v10.16.18: `messagesDelivered` is an ARRAY OF OBJECTS (was bare integers). Each object carries the REAL gateway `messageId` so the closeout can be cross-checked against the sent-registry before claiming `done`. `verify-zhc-standard.sh` still reads `.messagesDelivered | length`, which holds for the object array.
>
> v11.10.0 (PRD-2.8): `closeoutDeliverables` carries the 7 explicit per-leg delivery fields. `closeoutResumeUuid` is the loop-registry entry for the dedicated closeout-resume cron. `qcOrgChartConnectorTree` is the programmatic connector-tree assertion result.

See `23-ai-workforce-blueprint/build-state-schema.json` for the JSON-schema source of truth.

---

## 4. Atomic State Writes (REQUIRED)

Every state-file mutation MUST be atomic. The pattern (use jq, then mv):

```bash
STATE="$OC_ROOT/workspace/.workforce-build-state.json"
tmp=$(mktemp)
jq '.closeoutStatus = "generating" | .closeoutStartedAt = (now | strftime("%Y-%m-%dT%H:%M:%SZ"))' "$STATE" > "$tmp" && mv "$tmp" "$STATE"
```

**Never** redirect directly into `$STATE`. A crash mid-write corrupts the state file and the resume cron will not be able to recover.

---

## 5. How the Resume Cron Picks Up a Stalled Closeout

`23-ai-workforce-blueprint/scripts/resume-workforce-build.sh` is **extended in v10.14.17** to detect closeout work, not just build work. The new dirty-state check:

```
state is dirty IF:
  (interview complete AND any dept is pending/failed/stale-building)   ← v10.14.16 logic, unchanged
  OR
  (buildCompletedAt is set AND closeoutStatus NOT IN ("done", "sent")) ← v10.14.17 addition
```

When the second clause triggers, the resume script dispatches a `[CLOSEOUT-RESUME]` self-ping that tells the agent to read `resume-prompt.txt` (which now includes a section about closeout). The agent reads `closeoutStatus` + which fields are set, and skips ahead to the first un-completed step.

So if the closeout dies at Step 3, the next cron fire (within 15 min) wakes it back up at Step 3.

---

## 6. Idempotency Guarantees

Every step is idempotent by-construction:

| Step | Idempotency mechanism |
|------|----------------------|
| 1 (Command Center) | Skip if `commandCenterStatus == "done"` AND `commandCenterUrl` set |
| 2 (Infographic #1) | Skip if `infographic1Url` set |
| 3 (Infographic #2) | Skip if `infographic2Url` set |
| 4 (Celebration video) | Skip if `celebrationVideoUrl` set |
| 5 (Notion page tree) | Skip if `notionRootPageUrl` set, OR if a Notion search finds the exact title already |
| 6 (Telegram delivery) | Track `messagesDelivered` (array of `{n, messageId, chatId, ts}` objects). A slot is sent only if it has no object carrying a non-empty `messageId`; a `status:"send-failed"` slot is retried. |
| 6.5 (Delivery confirmation) | `verify-telegram-delivery.sh` cross-checks each required messageId against the sent-registry. `done` is gated on this passing; an unconfirmed required messageId → `failed` (`telegram-unconfirmed: msg <n>`) and the cron retries. |

Re-running `run-closeout.sh` on a partially-complete closeout is safe.

---

## 7. Failure Escalation

If `closeoutStatus == "failed"` AND the resume cron has retried 3+ times without progress:
- Send escalation message to the operator's Telegram chat (`env.vars.OPERATOR_TELEGRAM_CHAT_ID`, default `5252140759`):
  ```bash
  source "$(if [ -d /data/.openclaw ]; then echo /data/.openclaw; else echo $HOME/.openclaw; fi)/skills/shared-utils/operator-chat-id.sh"
  openclaw message send --channel telegram --target "$OPERATOR_CHAT_ID" --message "🚨 Closeout stuck for {{OWNER_NAME}} ({{COMPANY_NAME}}). closeoutStatus=failed, closeoutFailureReason={{REASON}}, resumeAttempts={{N}}. State file: {{STATE_FILE_PATH}}"
  ```
- Do NOT send anything to the owner about the failure. They've heard nothing yet (Step 6 hasn't fired) — silence is fine. The operator handles it.

---

## 8. Fleet Sweep (PRD-2.8)

`scripts/fleet-sweep-closeouts.sh` sweeps every box in the fleet and verifies the 7 `closeoutDeliverables` legs are all complete. Mirrors the `fleet-refresh.sh` architecture.

```bash
# Dry-run (default — safe, read-only report):
bash 37-zhc-closeout/scripts/fleet-sweep-closeouts.sh --boxes-file ~/.openclaw/fleet/boxes.json

# Apply: re-run run-closeout.sh on every box with an incomplete closeout:
bash 37-zhc-closeout/scripts/fleet-sweep-closeouts.sh --boxes-file ~/.openclaw/fleet/boxes.json --apply

# Check this box only:
bash 37-zhc-closeout/scripts/fleet-sweep-closeouts.sh --local

# JSON report:
bash 37-zhc-closeout/scripts/fleet-sweep-closeouts.sh --boxes-file ... --report-json /tmp/closeout-sweep.json
```

**Outcome classification per box:**
- `complete` — all 7 legs done|waived
- `incomplete` — one or more legs missing (--apply re-runs `run-closeout.sh`)
- `ghost-complete` — `closeoutStatus=done` but deliverable fields are missing (PRD-2.8 exposes these)
- `build-not-complete` — `buildCompletedAt` not set yet; skipped

In `--apply` mode, a Telegram summary is sent to the operator after the sweep completes.

**Exit codes:** `0` = all complete; `1` = fatal; `2` = at least one incomplete (CI-visible nonzero)

---

## 9. Logging

Append-only log at `$OC_ROOT/workspace/.zhc-closeout.log` with line format:

```
2026-05-23T20:31:14Z [INFO ] step=1 command-center: building...
2026-05-23T20:32:01Z [INFO ] step=1 command-center: done url=http://localhost:4000
2026-05-23T20:32:02Z [INFO ] step=2 infographic-1: submitted taskId=abc123
2026-05-23T20:33:45Z [INFO ] step=2 infographic-1: ready url=https://tempfile.kie.ai/xxx.png
...
```

Logs are NEVER truncated. Trevor uses them for post-mortems.
