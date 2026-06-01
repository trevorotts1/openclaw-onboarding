# Changelog - Skill 37: ZHC Closeout

## [1.1.4] - 2026-05-31 - Telegram delivery confirmed against the gateway sent-registry (anti-faking) (shipped with onboarding v10.15.19)

The closeout could be marked `done`/`sent` purely on the `openclaw message send` COMMAND EXIT CODE. But that command can exit 0 while the message never reaches Telegram (silent Telegram-offset-corruption; fresh-VPS "scope upgrade pending approval"). So a closeout could claim delivery that never happened — the exact "faked closeout" we forbid. This release makes delivery PROVABLE end-to-end.

### A. Capture the REAL messageId on every send — `send-telegram-celebration.sh`
Every `openclaw message send` now runs with `--json` and a new `extract_message_id()` pulls the real gateway `messageId` (`.messageId` → `.payload.messageId` → `.result/.data.messageId`, with a best-effort regex fallback for installs where `--json` is absent/garbled — but ALWAYS requiring a non-empty id; never exit-code-only). `state.messagesDelivered` is now an **array of objects** `{n, messageId, chatId, ts}` instead of bare integers. A send that returns no messageId records `{n, status:"send-failed", reason}` and is **not** counted delivered; `is_delivered()` only treats a slot as delivered when it carries a non-empty messageId, so a retry upgrades a `send-failed` slot. (Backward-safe: `verify-zhc-standard.sh` reads `.messagesDelivered | length`, which still works for the object array.)

### B. NEW `verify-telegram-delivery.sh` — cross-check against the sent-registry
After the sends, this reads the gateway sent-registry `agents/main/sessions/sessions.json.telegram-sent-messages.json` (`{ "<chatId>": { "<messageId>": <ts-ms> } }`; resolves Mac `~/.openclaw` vs VPS `/data/.openclaw`) and requires EACH required messageId be present under the owner's chatId. Accounts for the rolling-window/aging behavior: a missing-but-recent id (younger than `ZHC_TG_REGISTRY_TTL_SEC`, default 86400s) is a real FAIL (rc 3); a missing-but-aged-out id is treated as legitimately rotated (PASS). A required slot with no captured id at all → rc 4. Required slots default to the three must-land text messages (1,6,7; override `ZHC_TG_REQUIRED_SLOTS`); media/Notion slots are verified-if-present. Writes a per-id pass/fail breakdown to `state.telegramDeliveryVerification`. Env overrides (`ZHC_STATE_FILE`/`ZHC_LOG_FILE`/`ZHC_TG_REGISTRY`) let it run against a fixture with no live install.

### C. Gate `done` on confirmation — `run-closeout.sh`
The phantom-closeout guard now counts only messages with a real (non-empty) messageId. A NEW delivery-confirmation gate then runs `verify-telegram-delivery.sh` before `closeoutStatus=done` may be written: if any required messageId is unconfirmed, the closeout is marked `failed` with `closeoutFailureReason="telegram-unconfirmed: msg <n>"` and the recurring resume cron retries (never-stop). The phantom guard is kept as an additional layer.

### D. Smoke test + CI — `test-verify-telegram-delivery.sh`
New self-contained smoke test proves: required id present in registry → pass; missing+recent → fail(3); no captured id → fail(4); missing+aged-out → pass; send-failed-only records count as 0 real deliveries. Wired into `qc-static.yml` as the "Skill 37 Telegram delivery-confirmation gate (anti-faking)" step, which also statically asserts `--json` usage, the non-empty-messageId requirement, the verify invocation, and the `telegram-unconfirmed` failure path so the anti-faking wiring can never silently regress. skill-version.txt 1.1.3 → 1.1.4.


## [1.1.3] - 2026-05-27 - Mandatory 8.5 quality gate (shipped with onboarding v10.14.10)

Systemic requirement from Trevor: every ZHC closeout must RATE + QC each deliverable and only deliver to the client when it scores at least 8.5/10.

### A. New QUALITY-GATE.md
The mandatory 8.5 rubric + per-artifact workflow: generate -> self-rate 1-10 -> QC checks -> if score < 8.5 OR any QC check fails, iterate/regenerate and re-rate -> only when >= 8.5 AND all QC pass, deliver. Org Chart rubric REQUIRES visible connector-line reporting hierarchy (Owner -> CEO -> cluster headers -> department boxes) reading as a true org chart, not a grid of cards (the #1 historical failure), plus legible labels, role pills, full branding, full-canvas no-overflow, deterministic HTML/Playwright render. Flow Diagram rubric: industry-specific imagery, numbered 5-step left-to-right, finished/approved deliverable (no gift box), branding. Docs rubric: all 9 doctrine sections, real client-specific content (no placeholders), client-specific DMAIC, Book-to-Persona scoring matrix, brand voice, resolving links.

### B. Gate wired into run-closeout.sh
New ZHC_QUALITY_MIN (default 8.5) + ZHC_QUALITY_MAX_ATTEMPTS (default 3) env knobs and a generate_rate_gate() helper. Steps 2 (org chart), 3 (flow diagram), and 5 (Notion docs) now run a RATE + QC + GATE loop: the agent writes .qualityRatings.<org_chart|flow_diagram|closeout_docs>.{score,qc,note}; the artifact is deliver-eligible only at score >= 8.5 with qc=pass; below the bar it regenerates up to the max attempts, then is HELD (added to .qualityHeld, operator escalated) rather than delivered. The Telegram step exports the held list so held artifacts are skipped, never shipped subpar.

### C. generate-infographics.sh + SKILL.md + INSTRUCTIONS.md
generate-infographics.sh header + both success paths reference QUALITY-GATE.md and log a self-rate reminder. SKILL.md and INSTRUCTIONS.md gained a prominent MANDATORY section pointing to QUALITY-GATE.md. skill-version.txt 1.1.0 -> 1.1.3.


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
