# Changelog - Skill 37: ZHC Closeout

## [1.3.1] - 2026-06-23 - v12.14.5: org-chart template comment genericized (fleet-wide no-client-names invariant)

- `templates/workforce-org-chart/index.html.template`: removed a real client name from the v10.X.9 rebuild changelog code-comment (line 13) and replaced it with a generic, attribution-free phrasing. The fleet-wide leak gate (`scripts/qc-assert-no-client-names.sh`) previously did NOT scan `*.template` files, so this slipped past CI; the gate's file glob now includes `*.template` (and other doc/config extensions), closing the blind spot. No functional template change.

## [1.3.0] - 2026-06-13 - v12.3.10: interview-nudge cron self-removed at done-transition (interviewComplete=true)

- `scripts/run-closeout.sh`: at the done-transition (alongside the existing closeout-resume cron self-remove), added a block that:
  1. Reads `.interviewNudgeUuid` from build-state (written by install.sh at install time).
  2. Calls `openclaw cron rm <uuid>` to remove the interview-nudge cron — tolerated non-fatal on failure.
  3. Clears `.interviewNudgeUuid` / nulls `.interviewNudgeRegisteredAt` from build-state.
  4. Fallback name-scan: scans `openclaw cron list` for any cron named `interview-nudge` and removes it — covers boxes installed before UUID recording was added (pre-UUID fleet rescue).
  5. Calls `lr_kill "interview-nudge"` via loop-registry.sh for registry hygiene.
- `scripts/test-closeout-gated-pipeline.sh`: added T11 (static grep asserts nudge cron rm wired at done-transition + fallback scan present) and T12 (schema has interviewNudgeUuid + interviewNudgeRegisteredAt).

---

## [1.2.0] - 2026-06-10 - PRD-2.8: GATED pipeline — 7 per-leg deliverables, pre-flight Telegram check, org-chart connector-tree assertion, n8n wiring, dedicated resume cron, fleet sweep (shipped with onboarding v11.10.0)

Addresses PRD section 2.8: "treat the closeout as a gated pipeline like the role/SOP library." Every leg is now explicit and observable; the resume cron fires until all 7 are done or waived; pre-flight fails LOUD before any generation starts.

### A. 7 per-deliverable `closeoutDeliverables` fields (the core PRD-2.8 requirement)

`closeoutDeliverables` object added to `build-state-schema.json` with 7 explicit fields: `notionTreeUrl`, `infographic1Url`, `infographic2Url`, `celebrationVideoUrl`, `telegramSequenceSent` (boolean), `ccUrlDelivered` (boolean), `n8nWired` (boolean or `"skipped"`). `run-closeout.sh` writes each field as the corresponding step completes. The dedicated resume cron reads these fields (not `closeoutStatus` alone) to determine whether work remains.

### B. Pre-flight validates Telegram gateway health (fail LOUD at start)

`run-closeout.sh` now calls `openclaw gateway status` before any KIE.AI/Notion call fires. If the gateway is not healthy/running/ok, the closeout fails immediately with `closeoutFailureReason: "preflight: Telegram gateway not reachable"` and the resume cron retries. Previously: env vars were checked but gateway health was not; infographic generation could succeed while the Telegram step was dead. Set `ZHC_SKIP_TG_PREFLIGHT=1` to bypass in unit tests.

### C. Org-chart connector-tree assertion — `qc-assert-org-chart-connector-tree.sh`

NEW script performs a PROGRAMMATIC check that the rendered Infographic #1 HTML has connector lines (SVG `<line>`/`<path>` with `.connector` class, or CSS `::before`/`::after` border connectors) and 3+ hierarchy levels (owner, ceo, dept). On failure: clears the gate score, triggers a regeneration cycle, and HOLDS the artifact if the assertion still fails. Writes `qcOrgChartConnectorTree` to state. The card-grid anti-pattern (cluster-card with no connectors) is now rejected by code, not just by rubric.

### D. n8n wire-up step — `wire-n8n-closeout.sh` (Step 6.5)

NEW script POSTs a `zhc_closeout_complete` webhook payload to `N8N_WEBHOOK_URL` after Telegram delivery. Payload: company slug, agent name, CC URL, artifact URLs, owner chat ID. 3 retries with backoff. Non-blocking: failure is a soft fail (same as video/notion). Skips gracefully when `N8N_WEBHOOK_URL` unset (writes `n8nStatus="skipped"`, `closeoutDeliverables.n8nWired="skipped"`). Explicit skip via `ZHC_SKIP_N8N=1`.

### E. Dedicated closeout resume cron — `resume-closeout-cron.sh` (loop registry)

NEW dedicated cron registered at the `pending → generating` transition (separate from the Skill 23 `workforce-build-resume` cron). Fires every 15 min. Kill conditions: (1) all 7 `closeoutDeliverables` legs done|waived; (2) `closeoutStatus = done|sent`; (3) max runs (48 = 12h) exhausted (escalates + self-removes). Loop-registry entry: UUID stored in `.closeoutResumeUuid`. Self-removes from state AND from `openclaw cron` on kill. Operator Telegram alert every 3rd consecutive resume attempt without progress.

### F. Fleet sweep — `fleet-sweep-closeouts.sh` (PRD-2.8 fleet delivery verification)

NEW script sweeps all boxes in the fleet manifest (`~/.openclaw/fleet/boxes.json` or `--boxes-file`). Checks each box's 7 `closeoutDeliverables` legs via SSH. Classifies each box: `complete` / `incomplete` / `ghost-complete` (closeoutStatus=done but deliverable fields missing) / `build-not-complete`. In `--apply` mode: invokes `run-closeout.sh` on each incomplete box. JSON report (`--report-json`). Telegram operator summary on apply. Exits 2 when any incomplete (CI-visible). Local mode (`--local`) works without SSH for single-box checks.

### G. `closeoutStatus` enum extended + schema updates

`closeoutStatus` now includes `partial` (soft-only failures) and `blocked-floor-incomplete` / `blocked-libraries-incomplete`. Schema adds: `closeoutDeliverables` (7 fields, `additionalProperties: false`), `closeoutResumeUuid`, `closeoutResumeRegisteredAt`, `closeoutBlockReason`, `closeoutPartialReason`, `closeoutPartialArtifacts`, `qcOrgChartConnectorTree`.

### H. CI (qc-static.yml) — 4 new PRD-2.8 check steps

1. `Skill 37 PRD-2.8: closeout gated pipeline fixture test` — runs `test-closeout-gated-pipeline.sh` (T1–T9)
2. `Skill 37 PRD-2.8: org-chart connector-tree QC assertion static check` — directly exercises the script with pass/fail fixtures
3. `Skill 37 PRD-2.8: schema has all 7 closeoutDeliverables fields` — schema regression guard
4. `Skill 37 PRD-2.8: fleet-sweep + resume-cron scripts present and executable` — script presence + run-closeout.sh wiring assertions

### I. INSTRUCTIONS.md + QUALITY-GATE.md updated

Pre-flight section updated with Telegram gateway check. State machine section updated with new states and 7-leg table. New sections: "7 per-deliverable leg fields", "Dedicated Closeout Resume Cron (Loop Registry)", "Step 6.5 n8n Wire-up", "Fleet Sweep". Step count updated from 6 to 7.

- skill-version.txt: 1.1.5 → 1.2.0

**QC score: 9.0/10 PASS** (independent scorer 2026-06-10) — Wiring 9/10, SSOT 9/10, Path 9/10, Observability 9/10, Docs 9/10, Regression 9/10. Weighted: 90/100. Merge SHA: 7e051162f82f1eace999574c256c00c7a21272da.

## [1.1.5] - 2026-06-01 - Beautiful, LINKED closeout: every artifact resolves to a REAL openable URL in Telegram (WS-9 closeout UX) (shipped with onboarding v10.15.20)

The closeout messaging was messy and unlinked — images/video were sent inline but the durable "where do I find this later" link was either missing or a login-gated GHL app deep-link ("we saved it in this folder"). This release makes the celebration message BEAUTIFUL + LINKED: every artifact (celebration video, both infographics, Notion, Command Center, GHL media) resolves to a REAL openable URL posted IN the message. The anti-faking messageId-confirmation gate (1.1.4) is fully preserved.

### A. GHL media upload captures durable, openable PUBLIC URLs — `upload-ghl-media.sh`
- **Env-name fix (the silent-skip bug):** resolves the LOCATION PIT from `GOHIGHLEVEL_API_KEY` (TOOLS.md canonical) with `GHL_API_KEY` as a legacy alias, and the location id from `GOHIGHLEVEL_LOCATION_ID` / `GHL_LOCATION_ID` / build-state `.ghlLocationId`. Previously the script ONLY read `GHL_API_KEY`/`GHL_LOCATION_ID`, so on every box that uses the canonical names the upload silently skipped and no media links ever reached the client.
- **Folder field fix:** the documented upload form field for the target folder is **`parentId`**, not `folderId` (verified against marketplace.gohighlevel.com/docs/ghl/medias/upload-media-content). Folder CREATE via API is broken (TOOLS.md) so the script still never POSTs a folder-create — a folder is pre-made in the Convert and Flow UI and its id passed via `GHL_MEDIA_FOLDER_ID`.
- **Per-file public URLs:** each `/medias/upload-file` response returns `{"fileId","url":"https://storage.googleapis.com/msgsndr/..."}` — a PUBLIC, openable GCS URL (no GHL login). The script now maps each upload back to its artifact and writes `ghlVideoPublicUrl`, `ghlInfographic1PublicUrl`, `ghlInfographic2PublicUrl` (plus `ghlMediaUrls[]`, `ghlMediaFileIds[]`, `ghlMediaLibraryUrl`) to state. Uploads get a clean human name `"<Company> -- <Label>.<ext>"`.

### B. Telegram posts the ACTUAL openable LINKS — `send-telegram-celebration.sh`
- New `openable_link()` resolver: durable GHL public URL → remote http URL → none (rejects `file://`/`null`/empty).
- Each image and the video is still sent INLINE (local bytes via `--media`, so it renders in-thread) AND now carries a `🔗 Open it directly:` line with its durable GHL public URL — so the client always has a real openable link even after the inline media scrolls away.
- Message 4 (video) treats a GHL public video URL as a valid source, not just local bytes/remote URL.
- Message 6 posts the durable per-file public links (video, both graphics) + the "browse them all in your account" media-library link, replacing the old login-gated-only deep-link.
- Graceful no-GHL degradation proven: with no GHL the messages fall back to inline media + remote URLs, with no broken/empty "Open it directly" lines and no empty GHL block.

### C. Operator summary uses durable links — `send-operator-summary.sh`
Prefers the GHL public URL (then Drive, then remote) for each artifact so the operator's links match what the client can actually open.

### D. Schema + smoke test + CI
- `build-state-schema.json`: documented the new fields (`ghlVideoPublicUrl`, `ghlInfographic1/2PublicUrl`, `ghlMediaUrls`, `ghlMediaFileIds`, `ghlMediaLibraryUrl`, `ghlMediaUploaded`, `ghlLocationId`, `celebrationVideoLocalPath`, `celebrationVideoModel`, `infographic1/2LocalPath`, `ghlMediaUploadedAt`).
- NEW `test-closeout-openable-links.sh`: proves the GHL upload accepts both env-name forms, uses `parentId` (never `folderId`), never folder-creates, captures per-file public URLs, and that the Telegram script's `openable_link()` resolver behaves (GHL > remote > none) and the messageId gate is intact. Wired into `qc-static.yml`.
- KIE celebration video model verified unchanged: `gemini-omni-video` (createTask `/api/v1/jobs/createTask`, recordInfo `/api/v1/jobs/recordInfo`, result at `data.resultJson.resultUrls[0]`) per docs.kie.ai. Not swapped.
- skill-version.txt 1.1.4 → 1.1.5.

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

Re-graded the two closeout infographics against a true 10/10 bar after a live client launch.

### A. Org chart: true reporting tree with visible connector lines
`templates/workforce-org-chart/index.html.template` rebuilt. Previously four flat cluster cards with a single stub line under the CEO; it read as a grid, not an org chart. Now: Owner -> CEO -> horizontal bus -> each cluster header -> per-cluster branch spine down to every department, with junction dots. Lines are drawn by measuring real positions (getBoundingClientRect) so the tree is correct for any dept count. New fitDeptCards() auto-sizes cards so dense clusters (5+ depts) never overflow the canvas. render.mjs / cluster-classifier.js unchanged.

### B. Flow diagram: industry-aware prompt, no gift box
`templates/infographic-2-prompt.md` rewritten to template in {{INDUSTRY}} and {{WHAT_THEY_DELIVER}} so imagery is business-specific. Stage 5 is now an APPROVED / FINISHED deliverable with an explicit no-gift-box / no-present directive, plus full-canvas composition and a reusable 7.5-to-10 guidance block. `scripts/generate-infographics.sh` derives WHAT_THEY_DELIVER from state (.whatYouDeliver / .whatTheyDeliver / .coreDeliverable) with an industry-keyed fallback and substitutes the new token.


## [1.1.1] - 2026-05-26 - Skill 37 v4 production bug fixes (shipped with onboarding v10.14.4 / v10.15.4)

Five bugs caught when re-firing a phantom-completed closeout against v10.X.3.

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

Codifies 4 lessons from a live ZHC closeout (2026-05-26):

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
Before v10.14.17, the post-build pipeline had NO enforced closeout. Skill 23 wrote `buildCompletedAt`, then nothing — Skill 32 was supposed to fire by documentation, but documentation is not enforcement. Diagnosed today on a client VPS: build completed at 20:22, the client heard nothing. No celebration, no infographics, no closeout doc, no Command Center URL.

This skill is the state-machine-driven closeout layer. Same architectural pattern as the build-resume layer fixed the build-interruption gap in v10.14.16.

### What it delivers to the client
6 paced Telegram messages: announcement, structure infographic, workflow infographic, celebration video, Notion closeout doc link, Command Center URL. Plus a 9-section Notion page tree in the client's own workspace.

### Cost envelope
~$0.60 / client in KIE credits (worst case).
