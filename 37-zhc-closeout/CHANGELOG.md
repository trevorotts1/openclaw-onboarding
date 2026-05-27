# Changelog - Skill 37: ZHC Closeout

## [1.1.2] - 2026-05-27 - Infographics upgraded to 10/10 (shipped with onboarding v10.14.9 / v10.15.9)

Re-graded the two closeout infographics against a true 10/10 bar after Teresa Pelham's launch.

### A. Org chart: true reporting tree with visible connector lines
`templates/workforce-org-chart/index.html.template` rebuilt. Previously four flat cluster cards with a single stub line under the CEO; it read as a grid, not an org chart. Now: Owner -> CEO -> horizontal bus -> each cluster header -> per-cluster branch spine down to every department, with junction dots. Lines are drawn by measuring real positions (getBoundingClientRect) so the tree is correct for any dept count. New fitDeptCards() auto-sizes cards so dense clusters (5+ depts) never overflow the canvas. render.mjs / cluster-classifier.js unchanged.

### B. Flow diagram: industry-aware prompt, no gift box
`templates/infographic-2-prompt.md` rewritten to template in {{INDUSTRY}} and {{WHAT_THEY_DELIVER}} so imagery is business-specific. Stage 5 is now an APPROVED / FINISHED deliverable with an explicit no-gift-box / no-present directive, plus full-canvas composition and a reusable 7.5-to-10 guidance block. `scripts/generate-infographics.sh` derives WHAT_THEY_DELIVER from state (.whatYouDeliver / .whatTheyDeliver / .coreDeliverable) with an industry-keyed fallback and substitutes the new token.


## [1.1.1] - 2026-05-26 - Skill 37 v4 production bug fixes (shipped with onboarding v10.14.4 / v10.15.4)

Five bugs caught when re-firing Evelyn's phantom-completed closeout against v10.X.3.

### A. Inf #2 model slug
`gemini-3-1-flash-image` returned 422 from KIE; corrected to `nano-banana-2`. Confirmed accepted against `api.kie.ai/api/v1/jobs/createTask` 2026-05-26. Fallback `gpt-image-2-text-to-image` unchanged.

### B. Gemini Omni Video aspect_ratio
`submit_gemini_omni()` now always includes `aspect_ratio` in input (default `16:9`). KIE was returning 422 "Aspect ratio only supports [16:9, 9:16]" without it. New env override `ZHC_CELEBRATION_VIDEO_ASPECT` accepts `16:9` or `9:16`.

### C. Veo3 poll timeout + transient 500s
Bumped `poll_veo` and `poll_gemini_omni` timeout 900s -> 1800s (env override `ZHC_VIDEO_POLL_TIMEOUT_SEC`). Treats HTTP 5xx OR body-level `errorCode: 500` as transient with 30s backoff, max 3 consecutive 500s before giving up. New log lines: `step=celebration-video poll for <id>: in-progress (elapsed=Ns)` and `VEO poll got 500 (transient, attempt N/3), retrying in 30s`.

### D. Step-level idempotency in run-closeout.sh
Each step (Inf1, Inf2, Video, Notion, Telegram) runs independently with its own try/catch. `STEP_<NAME>_STATUS` tracks ok/failed/skipped. Final closeoutStatus = `done` (5-or-6 success), `partial` (only Notion or Video failed, with `closeoutPartialArtifacts` enumerated), or `failed` (any of Inf1/Inf2/Telegram failed). Telegram slot 4 reads exported `ZHC_VIDEO_STATUS` and sends a text-only "deferred for tonight, vendor congestion" notice when video failed.

### E. Notion parent-page fallback
Was: env var OR BlackCEO/OpenClaw search; otherwise abort. Now: env var -> BlackCEO -> OpenClaw -> prior-run "Your Zero-Human Company" search -> workspace root (`parent.type=workspace, workspace=true`). `PARENT_KIND` is logged for operator visibility.


## [1.1.0] - 2026-05-26 - Skill 37 v3 closeout fixes (shipped with onboarding v10.14.3 / v10.15.3)

Codifies 4 lessons from Maria Anderson / Marico Consulting closeout (2026-05-26):

### 1. Workforce-structure infographic is now HTML + Playwright (no AI image model)
- New `templates/workforce-org-chart/` directory: `index.html.template`, `render.mjs`, `cluster-classifier.js`, `package.json`, `README.md`.
- Renders deterministically at 1920x1080 via headless Chromium. Perfect text labels (dept names, role count pills, footer totals), free per render.
- Cluster classifier maps department slugs into 4 visual clusters with brand-locked colors: Operations (navy `#1B2A4E`), Revenue (gold `#C9A14B`), Creative (teal `#2E8B8B`), Technology (burgundy `#7B2D3A`). Unmapped slugs default to Technology so no department is silently dropped.
- `generate-infographics.sh structure` no longer hits KIE.AI for Infographic #1.

### 2. Celebration video is downloaded as MP4 bytes before Telegram send
- `generate-celebration-video.sh` now ALWAYS downloads the result MP4 to `$OC_ROOT/workspace/.zhc-celebration-video.mp4` via `curl -fL --max-time 180` after the KIE job completes.
- Writes `celebrationVideoLocalPath` into state alongside `celebrationVideoUrl`.
- `send-telegram-celebration.sh` `send_video` / `send_photo` prefer `--media <local-path>` over `--photo`/`--video` `<url>` so the bot uploads bytes via Telegram's multipart `sendVideo` / `sendPhoto` endpoint. Inline player, not a download card.
- Root cause: the KIE CDN at `tempfile.aiquickdraw.com` returns `content-disposition: attachment`, which Telegram renders as a download card when given the raw URL.

### 3. Celebration video DEFAULT model switched to Gemini Omni Video
- `gemini-omni-video` via KIE.ai (`POST /api/v1/jobs/createTask`, `GET /api/v1/jobs/recordInfo`) is now the default for THIS skill's celebration video. Reason: Gemini Omni accepts an image reference (the just-rendered workforce-chart PNG), so brand carries through into the video.
- Veo 3.1 / `veo3_fast` remains the general-purpose video model elsewhere in OpenClaw and is the documented fallback for Skill 37 (auto-falls-back on attempt 3 if Gemini Omni is unavailable).
- Env override: `ZHC_CELEBRATION_VIDEO_MODEL` (default `gemini-omni-video`; accepts `veo3` / `veo3_fast`).
- Duration is snapped per model (Gemini Omni: 4-8, default 4; Veo: 4/6/8, default 8).

### 4. Workforce chart shows role-count pills + footer totals
- Per-department role-count pill (`2 roles`, `4 roles`, etc.).
- Footer center: `<N> Departments · <M> Specialist Roles · Zero Human Company`.
- Footer right: `Built by BlackCEO · 2026`.
- CEO agent card now shows agent name + `Routes all work · Reports to <Owner>` sub-line.
- All sourced from state file at render time; the only hand-edited values are `companyName`, `ownerName`, and `agentName`.

### Cost envelope
~$0.45 / client in KIE credits (worst case) - Infographic #1 is now free; Infographic #2 + celebration video are the only paid steps.

## [1.0.0] — 2026-05-23 — Initial release (shipped with onboarding v10.14.17)

### What's in this release
- `SKILL.md`, `INSTRUCTIONS.md`, `INSTALL.md`, `CORE_UPDATES.md`
- `scripts/run-closeout.sh` — top-level orchestrator
- `scripts/generate-infographics.sh` — KIE.AI gpt-image-1 (fallback nano-banana-pro)
- `scripts/generate-celebration-video.sh` — KIE.AI Veo 3.1 (veo3_fast default)
- `scripts/create-notion-closeout.sh` — Notion API 9-section page tree
- `scripts/send-telegram-celebration.sh` — 6-message paced delivery
- `templates/infographic-1-prompt.md`, `infographic-2-prompt.md`, `veo-prompt.txt`, `notion-page-tree.json`
- `skill-version.txt = 1.0.0`

### Why this exists
Before v10.14.17, the post-build pipeline had NO enforced closeout. Skill 23 wrote `buildCompletedAt`, then nothing — Skill 32 was supposed to fire by documentation, but documentation is not enforcement. Diagnosed today on Evelyn Bethune's VPS: build completed at 20:22, the client heard nothing. No celebration, no infographics, no closeout doc, no Command Center URL.

This skill is the state-machine-driven closeout layer. Same architectural pattern as the build-resume layer fixed the build-interruption gap in v10.14.16.

### What it delivers to the client
6 paced Telegram messages: announcement, structure infographic, workflow infographic, celebration video, Notion closeout doc link, Command Center URL. Plus a 9-section Notion page tree in the client's own workspace.

### Cost envelope
~$0.60 / client in KIE credits (worst case).
