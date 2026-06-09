# Changelog - Social Media Planner (Skill 35)

## v2.6.0 - June 9, 2026

### Fix — Wire row-logging to new social-planner-row-append webhook (fleet-wide planner bug fix)

**Why:** Content never landed in clients' Google Sheet planners. The only n8n webhook (`social-planner-sheet-create`) CREATES a new sheet on every call and has no row-append path. After produce → GHL upload → get CDN link, the row-log step had nowhere to write.

**What:**
- Built new n8n workflow `social-planner-row-append` (ID: `myXde6jbIIkaG5zW`) on `main.blackceoautomations.com`:
  - `POST /webhook/social-planner-row-append` with body `{sheetId, row: {Week Of, Theme of the Week, ..., Notes}}`
  - Code node maps `body.row.*` fields to the 20-column order of the **Weekly Overview** tab
  - HTTP Request node calls `sheets.googleapis.com/v4/spreadsheets/{sheetId}/values/Weekly%20Overview!A:T:append` with the operator's Google Sheets OAuth2 credential (`4IoTZHAybRblm172` — management blackceo Google Sheets account)
  - Returns `{success: true, sheetId, updatedRange}` on success
  - Workflow is ACTIVE; webhook path is production-ready
- **SKILL.md Media Delivery Contract step 4**: rewrote from vague "Log a row" to explicit `social-planner-row-append` curl call with full payload contract. Added clear note: `social-planner-sheet-create` is for first-time creation ONLY.
- **INSTALL.md Step 7 section 4f**: Clarified the two-webhook architecture — `sheet-create` (once, at install) vs `row-append` (every publish cycle). Explicit payload contract for each. No client Google credentials required — both run via operator service account.

**Verified:** Test row successfully appended to Angeleen's sheet `1RKgS5l-i6NBtf_vON49nBPdHe-F5W67RF9ym-S67L2c` Row 6 `'Weekly Overview'!A6:T6` — all 20 columns correctly populated.

**Risk:** Low. Additive webhook + documentation change. No existing publish, schedule, or GHL logic altered.

---

## v2.5.0 - June 9, 2026

### Fix 1 — Remove private operator tool reference; replace with OpenClaw subagent runtime
**Why:** SKILL.md instructed the agent to spawn via a private operator CLI tool (`node ~/.openclaw/workspace/.../cli.js workflow run content-publishing-engine ...`) that must not appear in client-facing skill files. The frontmatter also contained a `workflow_id` field with a comment explaining its origin in that private tool.
**What:**
- Removed all references to the private operator CLI tool from SKILL.md (both repos).
- Removed the `workflow_id: content-publishing-engine` frontmatter field and its private-tool comment. Replaced with `pipeline_id: content-publishing-engine` (neutral identifier, no private-tool language).
- Rewrote the `## Usage` section: primary path is now `sessions_spawn task="Run Content Publishing Engine on [topic]" runtime="subagent" model="ollama/minimax-m2.7:cloud"` (OpenClaw subagent runtime). Fallback model documented. Subagent pipeline behavior described.

### Fix 2 — Content sheet: agent always knows the link; graceful-degrade on Sheets write
**Why:** Agent responded "gws is not authenticated — can't create the Google Sheet content calendar" and "I don't have the social-media-planner spreadsheet link." Root cause: (a) no stored pointer to the content sheet, and (b) the skill tried to call Google Sheets API directly using an OAuth path it doesn't have credentials for.
**What:**
- Added `content_sheet_id` and `content_sheet_url` fields to the skill config contract in SKILL.md. Agent reads these before every run and can answer "what's my social media planner link?" instantly.
- INSTALL.md Step 7 rewritten: adopt-existing-sheet-first logic (check MEMORY.md → check onboarding-provided ID → create via webhook). Angeleen's existing sheet `1RKgS5l-i6NBtf_vON49nBPdHe-F5W67RF9ym-S67L2c` adopted if present, never duplicated.
- Step 7 now records `content_sheet_id` + `content_sheet_url` in MEMORY.md and wires them into `openclaw config env.vars.SKILL35_CONTENT_SHEET_ID/URL` so the agent has them at runtime.
- Added Step 7 sub-section 4f documenting the auth path: the agent does NOT call Google Sheets API directly and never needs `client_secret.json`. All sheet creation goes through the `https://main.blackceoautomations.com/webhook/social-planner-sheet-create` n8n webhook (BlackCEO Automations service account). If the webhook is unavailable the agent logs to a local `.jsonl` file and queues retry — never dead-ends with "gws is not authenticated."
- CORE_UPDATES.md MEMORY.md section: `content_sheet_id` and `content_sheet_url` fields added.
- Completion checklist: 4 new assertions covering sheet ID, sheet URL, link-answer test, and media delivery.
- Step 11 client confirmation message: "Content calendar sheet: [link]" replaces the generic "Google Sheet created" line.

### Fix 3 — Media delivery via GHL CDN public link (eliminates Telegram size-cap failures)
**Why:** Finished media (Reels, podcast MP3s, image sets) was being sent as raw Telegram attachments, hitting the Bot API size cap, or the agent said "stored locally, I don't have a URL." Clients received no usable media link.
**What:**
- Added `## Media Delivery Contract` section to SKILL.md (both repos) documenting the mandatory delivery path:
  1. Produce file locally.
  2. Upload to client's own GHL Media Library via `POST https://services.leadconnectorhq.com/medias/upload-file` with `Authorization: Bearer [GOHIGHLEVEL_API_KEY]`, `Version: 2021-07-28`, multipart form fields `file`, `hosted=true`, `fileProcessingOpts={"forceReprocess":true}`. Response contains a `url` field.
  3. CDN URL format: `https://assets.cdn.filesafe.space/[LOCATION_ID]/media/[filename]` — confirmed from Skill 28 (cinematic-forge) which documents the same endpoint and CDN format.
  4. Log row in content sheet: CDN link + title + type + platform + date + status.
  5. Reply to owner with CDN link only.
- 10 MB size threshold: files over 10 MB MUST go through GHL CDN; smaller files may only go direct if operator explicitly sets `direct_attach_under_10mb=true` in MEMORY.md.
- GHL upload failure handling: retry once after 30 s; if still failing, notify owner and do NOT fall back to raw attachment.
- Variable reference updated: `GOHIGHLEVEL_API_KEY` (canonical name) + `content_sheet_id`/`content_sheet_url` added.

**Risk:** Low. All changes are additive documentation + config contract. No existing publish schedule, GHL posting, or social API logic altered.

---

## v2.4.0 - June 9, 2026

### Fix — Autonomous podcast audio generation via Fish Audio S2-Pro; removes "record yourself" punt

Mirrors the same problem fixed for video in v2.3.0 — the podcast step had no autonomous audio generation pipeline, only a vague "Synthesize MP3 via Fish Audio" instruction that caused agents to punt with "audio generation didn't produce a file — you can record it yourself." Agent now executes the full pipeline end-to-end. Client self-recording is a hard last resort only.

**What:**
- **references/playbook.md Section 15** — Added "Autonomous Audio Generation Pipeline" subsection with:
  - Verified Fish Audio API facts (model `s2-pro`, endpoint `POST https://api.fish.audio/v1/tts`, auth `Authorization: Bearer`, model via header `model: s2-pro`, synchronous binary stream response — no polling).
  - Step-by-step pipeline: write script → tag heavily with S2-Pro emotion tags → select model (default s2-pro, check for newer) → generate via helper script → ffprobe verify (duration 600-900s, non-zero size, no errors) → retry/diagnose on failure → last-resort fallback message only after 3 attempts and operator notified.
  - Verified S2-Pro emotion tag syntax: [square brackets], 64+ categories, free-form natural language supported. S1 used parentheses — never mix syntax.
  - 4 concrete tagged-script examples demonstrating expressive delivery.
  - Client self-record fallback message to send only as last resort.
- **CORE_UPDATES.md — Podcast Publishing Process** — Rewrote the 14-step list to match the full autonomous pipeline (tag → model → generate → verify → retry → diagnose) with inline API call reference.
- **scripts/generate_podcast_audio.sh** (new, chmod +x) — Parameterized script: `bash generate_podcast_audio.sh <script_file> <voice_id> [model] [output_mp3]`. Sources `secrets/.env` if `FISH_AUDIO_API_KEY` not in env. Makes up to 3 attempts with per-failure diagnosis (401/403/404/422/429/503/network). ffprobe verifies duration (≥30s check; caller should confirm 600-900s). Exits 0 on success, 1 after 3 failures with diagnostic checklist, 2 on bad args/missing key.

**Risk:** Low. Additive documentation and new helper script. No scheduling, posting, or publish-webhook logic altered.

---

## v2.3.0 - June 9, 2026

### Fix — Multi-clip storyboard + FFmpeg merge for full-length Reels; removes false "record yourself" punt

**Why:** The previous video pipeline was ambiguous about how to handle the fact that AI video tools generate clips of at most 8-10 seconds. An agent could (and did) tell clients "the AI video tools have a hard limit of 8-12 seconds per clip, so a 55-60 second Reel can't be generated in one pass — you should record the video yourself." This is wrong behavior. The agent is capable of handling the full pipeline end-to-end.

**What:**

- **references/playbook.md Section 16** — Replaced the vague "generate 7-8 segments, merge with FFmpeg" instructions with a fully explicit, agent-followable pipeline:
  - **Step A: Storyboard** — compute `scene_count = ceil(target_seconds / clip_limit_seconds)` (e.g. ceil(60/8) = 8), write a visual prompt per scene with continuity cues (consistent subject, wardrobe, setting, color grade, camera style), and mark each scene's incoming transition as `cut` or `crossfade`.
  - **Step B: Generate clips** — one clip per scene via kie.ai Veo 3.1 Lite, retry any failed clip up to 3 times.
  - **Step C: Voiceover** — ONE continuous VO track from the full script via Fish Audio S2 (preferred for natural delivery).
  - **Step D: Normalize (mandatory)** — run every raw clip through a normalize pass (`scale=1080:1920, fps=30, libx264, yuv420p, aac 48kHz`) before any concat to prevent codec/resolution mismatch failures.
  - **Step E: Merge** — Recipe 2a (jump cuts via concat demuxer) or Recipe 2b (crossfades via xfade filter with `offset = clip_duration - xfade_duration`); storyboard declares the choice.
  - **Step F: VO overlay** — `ffmpeg -map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -shortest`.
  - **Step G: QC** — ffprobe checks duration (55-60s), resolution (1080x1920), codec (h264); retry failed clips before declaring failure.
  - Moved client self-recording to an explicit last-resort fallback (only after all clip retries exhausted), with a specific message the agent must send instead of a silent punt.

- **CORE_UPDATES.md — Video Production Process** — Rewrote the step list to match the new pipeline (storyboard → generate → normalize → merge → VO → QC), with inline FFmpeg commands and a reference to `merge_reel.sh`.

- **scripts/merge_reel.sh** (new, chmod +x) — Parameterized shell script implementing Steps D-G: normalizes all raw clips, merges (cut or crossfade), overlays voiceover, runs ffprobe QC checks. Usage: `bash merge_reel.sh clips_list.txt voiceover.mp3 final_reel.mp4 [cut|crossfade]`.

**Risk:** Low. Additive changes to documentation and a new helper script. No scheduling, posting, or API logic altered.

---

## v2.2.0 - June 8, 2026

follow-up: fixed QC accounts-grep false positive + added --announce delivery to weekly cron

### Fix #1 — Connection status: LIVE GHL check only (no guessing)
**Why:** An agent told a client "nothing is connected" when their GHL Social Planner had channels live. The root cause was reporting connection status from memory/vault absence rather than a live API call.
**What:** Added a `## Reporting connection status — LIVE GHL CHECK ONLY (no guessing)` section to INSTRUCTIONS.md with (a) an explicit ban on guessing/memory-based status, (b) a `check-social-connections` query block for both MCP-first and direct-API routing modes, and (c) clear notes that GHL Social Planner is the primary path, direct-platform tokens are optional add-ons, and Fish Audio / podcast is also optional and never blocks the skill. Added QC assertion in Section I of both `qc-skill35.sh` and `qc-social-media-planner.sh` to verify the rule is present in INSTRUCTIONS.md.
**Risk:** None — additive documentation change only. No existing publish logic altered.

### Fix #2 — Weekly trigger: CRON, not heartbeat (enforcement)
**Why:** A client's Saturday theme question never fired because the weekly trigger was implemented only as a HEARTBEAT.md prose entry. Heartbeat timing drifts and silently skips the prompt when the heartbeat cycle slips.
**What:** Added a `## Weekly trigger — CRON, not heartbeat (enforcement)` section to INSTRUCTIONS.md with (a) an explicit rule banning heartbeat-only weekly triggers, (b) a concrete `openclaw cron add` block for cron name `skill35-weekly-theme` on `0 8 * * 6` (Saturdays 8 AM) with idempotency via `~/.openclaw/data/skill35/weekly-theme-last-run.json`, and (c) a note that the HEARTBEAT.md entry from INSTALL.md Step 9 is informational context only — the cron is the enforcement mechanism. Added QC assertions in Section I of both QC scripts to verify the cron registration block is present and confirm the heartbeat-drift warning exists.
**Risk:** Low — the HEARTBEAT.md Step 9 entry is preserved (not deleted) and noted as informational. The cron is registered idempotently; existing installs that already have the cron name skip silently. No publishing logic altered.

---

## v2.1.0 - May 24, 2026 (Track M — mirror of VPS v10.14.33)

### Added — the three trigger paths INSTRUCTIONS.md has always referenced
- `scripts/run-publishing-cycle.sh` — single-topic orchestrator with full
  `--topic / --platforms / --schedule / --dry-run / --help` interface.
- `scripts/weekly-batch.sh` — cron-driven (`0 9 * * 1`) batch runner.
- `scripts/content-calendar.example.json` — schema starter.

Mirrors the VPS-side v10.14.33 PR. See the VPS CHANGELOG entry for the
full rationale + behavior contract.

---

## v1.4.0 - April 14, 2026

### Added/Updated
- Complete video production pipeline: kie.ai Veo 3.1 Lite generation + FFmpeg crossfade transitions and spec conformance (1080x1920, 9:16, H.264/AAC/30fps)
- Expanded to 8 platforms for video posts: Facebook, Instagram, LinkedIn, YouTube, TikTok, Pinterest, Threads, X (Twitter)
- HTML email newsletters with embedded images/links
- Scaled production to 15 sub-agents + 6 dedicated QC agents
- Podbean podcast publishing webhook integration
- FFmpeg for all video post-processing (crossfades, specs, optimization)

## v1.3.0 - April 13, 2026

### Changed
- Updated all webhook payload examples to use explicit variable references from identity.md
- Google Sheet webhook: `brandName` now references "[from identity.md: brand name]"
- Google Sheet webhook: `clientEmail` now references "[from identity.md: owner email]"
- Skill 32 tunnel webhook: `clientName` now references "[company slug from identity.md, lowercase, no spaces]"
- Skill 32 tunnel webhook: `companyName` now references "[from identity.md: company display name]"
- Skill 32 tunnel webhook: `contactEmail` now references "[from identity.md: owner email]"

### Added
- Full Podbean Podcast Publishing webhook documentation in CORE_UPDATES.md TOOLS.md section
- Detailed payload example for podcast publishing with all required fields
- Google Sheet Creation Webhook section with payload documentation

## v1.1.0 - April 13, 2026

### Changed
- Google Sheet creation now uses n8n webhook instead of Google Workspace API
- Webhook endpoint: `POST https://main.blackceoautomations.com/webhook/social-planner-sheet-create`
- Fields: `brandName`, `clientEmail`
- Response: `sheetUrl`, `sheetId`, `sheetName`
- No client credentials required for sheet creation
- Added Google Sheet Verification checklist to QC.md

## v1.0.0 - April 13, 2026

Initial release.

- 7-part weekly content series across Facebook, Instagram, LinkedIn, YouTube, TikTok, Pinterest
- Television Show Framework with pitch intensity scaling (4/10 to 10/10 over 7 days)
- 8 parallel sub-agents for content production
- 40+ item QC checklist across 8 categories (text, comments, images, scheduling, blog, podcast, audio, video)
- GoHighLevel (Convert and Flow) Social Planner API integration using Private Integration Token
- Image generation via kie.ai Nano Banana 2 at platform-correct ratios
- Video production via kie.ai Veo 3.1 Lite + FFmpeg merge
- Podcast production via Fish Audio S2 with inline emotion tags (depends on Skill 30)
- Blog post and email newsletter production
- Thursday carousel strategy with cross-platform image reuse (4:5 shared across FB, IG, LinkedIn)
- LinkedIn PDF carousel generation via ImageMagick/Pillow
- Google Sheet logging with 19 worksheets and horizontal 7-day storyboard layout
- Heartbeat-driven weekly theme request (Saturday 8AM, Noon, 6PM, Sunday 7AM)
- First Run Client Setup Protocol (reads core .md files, asks only for missing info)
- Persona integration with 5-layer alignment and client override option
- Memory-core integration for theme tracking, performance logging, and Dreaming insights (depends on Skill 31)
- Complete GHL API request body examples for regular posts, carousels, videos, and comments
- Image + content always bundled in one API call via mediaUrls field
- Comments always posted as separate call 1-2 minutes after parent post with action link
- Teach Yourself Protocol requirement
- Error handling with 3 retries and Telegram > Email > Text notification chain
