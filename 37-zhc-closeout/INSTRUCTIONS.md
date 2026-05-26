# Skill 37 — Runtime Instructions

This is the execution guide. Use it when `.workforce-build-state.json` shows the closeout is due (or in flight). Follow the steps EXACTLY in order. The state file is the contract — never skip a state write.

---

## 0. Pre-flight Checks

Before starting Step 1, verify ALL of the following:

1. `.workforce-build-state.json` exists and has:
   - `buildCompletedAt != null` — Skill 23 is actually done.
   - `closeoutStatus` is `pending` or `generating` (NOT `done` and NOT `sent`).
2. `KIE_API_KEY` env var is set.
3. `NOTION_API_TOKEN` env var is set.
4. `openclaw message send` works (gateway healthy).
5. `jq` is on PATH.
6. The 6 scripts in `scripts/` exist and are executable.

If ANY check fails, write `closeoutStatus: "failed"` + `closeoutFailureReason: "preflight: <which check>"` to the state file and STOP. The resume cron will try again on its next fire (every 15 min). If preflight has been failing for 3 consecutive resume invocations, escalate to the operator's Telegram chat (`env.vars.OPERATOR_TELEGRAM_CHAT_ID`, default `5252140759`). Resolve via:
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
  generating  ← Skill 37 sets this BEFORE Step 1
   ↓
  sent        ← Skill 37 sets this after Step 6's last Telegram message is delivered
   ↓
  done        ← Skill 37 sets this after final state-file write + log line
                (done is the terminal happy-path state)

  failed      ← Set on any step that has exhausted retries
                Sub-field closeoutFailureReason captures WHY
                The resume cron will retry from generating on its next fire
```

`closeoutStartedAt` is set on first transition `pending → generating`.
`closeoutCompletedAt` is set on transition `sent → done`.

---

## 2. The 6-Step Pipeline

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

1. If `infographic1Url` already set, skip.
2. Read `templates/infographic-1-prompt.md`. Fill placeholders from state file + `workforce-interview-answers.md`:
   - `{{COMPANY_NAME}}` — from interview answers
   - `{{OWNER_NAME}}` — `state.ownerName`
   - `{{AGENT_NAME}}` — `state.agentName` (the CEO agent name)
   - `{{DEPT_LIST}}` — joined list of `state.departments[].name`
   - `{{ROLE_COUNT}}` — sum of `state.departments[].rolesDone`
   - `{{BRAND_COLOR}}` — from interview if asked; else `#1a1a1a` + accent `#D4AF37` (BlackCEO gold)
3. Invoke `scripts/generate-infographics.sh structure "<filled-prompt>"`. The script POSTs to KIE.AI `/jobs/createTask` with `model: "gpt-image-2"`, `aspect_ratio: "16:9"`, `resolution: "2K"`, polls for completion, and returns the result URL.
4. On success: write `infographic1Url` to state file, atomic.
5. **Fallback:** If `gpt-image-2` returns a 422 / model-unavailable error, retry once with `model: "nano-banana-pro"`. Aspect ratio + resolution params are compatible.

**Retries:** 3 total (each retry uses a different seed by appending a random suffix to the prompt). If still failing: `closeoutFailureReason: "infographic-1: <last error>"`, mark `closeoutStatus: "failed"`, STOP.

### Step 3 — Generate Infographic #2 (How Work Flows)

Same shape as Step 2 but for the workflow diagram.

1. If `infographic2Url` already set, skip.
2. Fill `templates/infographic-2-prompt.md` with the same placeholders + one extra:
   - `{{EXAMPLE_TASK}}` — pulled from `workforce-interview-answers.md`; if not present, use a generic task seeded by the client's industry (e.g. "Launch a new email campaign" for a marketing-heavy client; "Onboard a new patient" for a healthcare client).
3. Invoke `scripts/generate-infographics.sh workflow "<filled-prompt>"`.
4. Write `infographic2Url` to state file.

**Retries:** 3 (with same fallback). Failure path same as Step 2.

### Step 4 — Generate Celebration Video

1. If `celebrationVideoUrl` already set, skip.
2. Fill `templates/veo-prompt.txt` with `{{COMPANY_NAME}}`, `{{OWNER_NAME}}`, `{{AGENT_NAME}}`, `{{INDUSTRY}}`.
3. Invoke `scripts/generate-celebration-video.sh "<filled-prompt>"`. The script POSTs to KIE.AI `/veo/generate` with:
   - `model: "veo3_fast"` (cost-conscious default; ~$0.40)
   - `prompt`: the filled prompt
   - `aspect_ratio: "9:16"` (vertical — Telegram delivery target)
   - `duration: 8` (Veo accepts 4, 6, or 8; default 8). Override via `ZHC_VIDEO_DURATION` env. Invalid values are snapped to 8 with a WARN log.
   - `generate_audio: true`
4. Poll `/veo/record-info?taskId=...` per KIE skill polling guidance (2s / 5s / 15s escalation). Max wait: 15 minutes.
5. On success: write `celebrationVideoUrl` to state file.

**Retries:** 2 (videos are expensive). On exhaustion: `closeoutFailureReason: "celebration-video: <last error>"`, mark `closeoutStatus: "failed"`, STOP.

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

1. Invoke `scripts/send-telegram-celebration.sh`. The script reads state and sends 6 sequenced messages to `ownerChat`:

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

   **Message 6 — Command Center URL (sendMessage):**
   ```
   🎛️ Your BlackCEO Command Center:
   {{COMMAND_CENTER_URL}}

   This is where you'll talk to your CEO (me), watch tasks move across
   the Kanban board, and check in on every department. Open it in your
   browser and bookmark it.

   When you're ready, just message me with the first thing you want done.
   I'm standing by.
   ```

2. After Message 6 successfully delivers:
   - Set `closeoutStatus: "sent"`, atomic write.
   - Then set `closeoutCompletedAt: <now-ISO-8601>` and `closeoutStatus: "done"`, atomic write.

**Retries per message:** 3 (with 2s/4s/8s backoff). If a message fails 3x:
- If it's Message 1 (the announcement), abort the whole delivery, mark `closeoutStatus: "failed"`, set `closeoutFailureReason: "telegram-message-1: <error>"`. Resume cron will retry on next fire.
- If it's Messages 2–6, log the failure but CONTINUE to the next message. After all 6 attempted, if any failed, set `closeoutStatus: "failed"` with a summary listing which messages failed. The resume cron will pick up failed messages individually on its next fire (Step 6 is idempotent per-message via a `messagesDelivered: [1,2,3,4,5,6]` array in the state file).

---

## 3. State-File Schema Additions (v10.14.17)

Skill 37 adds these top-level fields to `.workforce-build-state.json`:

```json
{
  "closeoutStatus": "pending|generating|sent|done|failed",
  "closeoutStartedAt": "2026-05-23T20:30:00Z",
  "closeoutCompletedAt": "2026-05-23T20:45:00Z",
  "closeoutFailureReason": "command-center: <last error>",

  "commandCenterStatus": "pending|building|done|failed",
  "commandCenterUrl": "http://localhost:4000",

  "n8nStatus": "pending|wired|skipped|failed",
  "n8nUrl": "https://client.n8n.cloud",

  "infographic1Url": "https://tempfile.kie.ai/...",
  "infographic2Url": "https://tempfile.kie.ai/...",
  "celebrationVideoUrl": "https://tempfile.kie.ai/...",
  "notionRootPageUrl": "https://www.notion.so/...",

  "messagesDelivered": [1, 2, 3, 4, 5, 6]
}
```

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
| 6 (Telegram delivery) | Track `messagesDelivered: [1,2,...]`. Each message in [1..6] is sent only if its number isn't in that array. |

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

## 8. Logging

Append-only log at `$OC_ROOT/workspace/.zhc-closeout.log` with line format:

```
2026-05-23T20:31:14Z [INFO ] step=1 command-center: building...
2026-05-23T20:32:01Z [INFO ] step=1 command-center: done url=http://localhost:4000
2026-05-23T20:32:02Z [INFO ] step=2 infographic-1: submitted taskId=abc123
2026-05-23T20:33:45Z [INFO ] step=2 infographic-1: ready url=https://tempfile.kie.ai/xxx.png
...
```

Logs are NEVER truncated. Trevor uses them for post-mortems.
