# Changelog - Social Media Planner (Skill 35)

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
