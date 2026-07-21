---
name: zhc-closeout
description: Delivers the full ZeroHumanWorkforce closeout experience — KIE.ai infographics, Veo celebration video, 9-section Notion page tree, 7-message Telegram sequence, Command Center fire, and n8n wire-up. Every deliverable must pass the 8.5 quality gate before delivery.
---

# Skill 37: ZHC Closeout

## MANDATORY - Teach Yourself Protocol (TYP)

**Before using this skill, complete the Teach Yourself Protocol (Skill 01) on this folder.**

Required read order:
1. SKILL.md (this file)
2. QUALITY-GATE.md - the MANDATORY 8.5 rate + QC gate every deliverable must pass
3. INSTRUCTIONS.md — runtime execution guide + state machine + 6-step pipeline
4. INSTALL.md — one-time setup steps (KIE_API_KEY, NOTION_API_TOKEN, budget caps)
5. CORE_UPDATES.md — what gets appended to AGENTS.md
6. CHANGELOG.md — change history

Per N3 ("read before act"), do not skip. Per N4, follow steps in declared order.

## MANDATORY: The 8.5 Quality Gate

**Rate + QC EVERY closeout deliverable; do not deliver below 8.5; iterate until it passes. See QUALITY-GATE.md.**

This is a systemic, non-optional requirement from Trevor. No closeout artifact (workforce org chart, how-work-flows diagram, Notion closeout docs) may be delivered to a client until the running agent has RATED it 1-10 against the rubric in `QUALITY-GATE.md` and it scores at least **8.5** AND passes its QC checks. If an artifact scores below 8.5, the agent MUST iterate/regenerate (edit the HTML/CSS for the org chart, re-prompt or switch model for the AI flow image, rewrite for docs) and re-rate until it reaches 8.5 or higher, THEN deliver. If it still cannot pass after the max attempts, HOLD the artifact (do not deliver it) and flag for human review. The org-chart rubric's #1 requirement is a TRUE reporting tree with visible connector lines (Owner -> CEO -> clusters -> departments), not a grid of cards. Below 8.5 is never shipped.

## What This Skill Is About

**Skill 37 is the closeout layer for the AI Workforce build pipeline.** It is what actually CLOSES THE LOOP with the client after Skill 23 (AI Workforce Blueprint) finishes building their zero-human workforce.

Before v10.14.17, the pipeline had no enforced closeout:
- Skill 23 finished writing department folders, flipped `buildCompletedAt` — and that was it.
- Skill 32 (Command Center) was "supposed" to fire next via documentation alone, but documentation is not enforcement.
- The owner often heard nothing. No celebration. No infographics. No closeout doc. No Command Center URL. No nothing.

Skill 37 fixes that by making the closeout STATE-MACHINE-DRIVEN, just like the build-resume layer fixed the build-interruption gap in v10.14.16.

## How Skill 37 Fits In the Pipeline

```
Owner says "build my company"
   │
   ▼
Skill 23 interview (Katie Couric / Oprah persona) ──────► workforce-interview-answers.md
   │
   ▼
Skill 23 build (departments + roles) ─────────────────► .workforce-build-state.json
   │  (every department: pending → building → done)
   │  (final dept done → buildCompletedAt set)
   ▼
🆕 Skill 37 ZHC Closeout (THIS SKILL) ─────────────────► closeoutStatus: pending → generating → sent → done
   │
   ├── Step 1: Run Skill 32 (Command Center) ────────► commandCenterUrl captured
   ├── Step 2: Generate Infographic #1 (Structure) ──► infographic1Url captured
   ├── Step 3: Generate Infographic #2 (Workflow) ───► infographic2Url captured
   ├── Step 4: Generate Celebration Video ───────────► celebrationVideoUrl captured
   ├── Step 5: Build Notion Page Tree (9 sections) ──► notionRootPageUrl captured
   └── Step 6: Telegram Delivery (7-message sequence)► closeoutCompletedAt set
```

The resume cron (Skill 23's `scripts/resume-workforce-build.sh`) is **extended in v10.14.17** to also fire whenever `buildCompletedAt` is set but `closeoutStatus != "done" && closeoutStatus != "sent"`. So if the closeout dies mid-way, the cron wakes the agent back up to finish it — same mechanism, same lockfile, same attempt cap.

## When This Skill Triggers

**Automatic, not manual.** The trigger is the state file, not a user instruction.

Specifically, this skill fires when:
1. `.workforce-build-state.json` has `buildCompletedAt != null` AND
2. `closeoutStatus == "pending"` (initial state set by Skill 23's master orchestrator) OR
3. `closeoutStatus == "generating"` (closeout was interrupted mid-step)

The agent gets invoked either:
- Inline at end of Skill 23 build (master orchestrator calls Skill 37 directly), or
- Via the resume cron self-pinging when state goes dirty.

## What Gets Delivered to the Client

By the end of Skill 37 execution, the client has received **all of the following** via Telegram, in order, paced (not spam-blasted):

| # | Message | Source |
|---|---------|--------|
| 1 | "🎉 Your zero-human company is built!" + summary stats | Composed from state file |
| 2 | Workforce Structure infographic (Telegram sendPhoto) | HTML + Playwright Chromium screenshot (local, deterministic text) |
| 3 | How Work Flows infographic (Telegram sendPhoto) | KIE.AI Gemini 3.1 Flash Image (Nano Banana 2) |
| 4 | 4–8 sec celebration video (Telegram sendVideo, bytes uploaded) | KIE.AI Gemini Omni Video (fallback: Veo 3.1) |
| 5 | "Your full Notion closeout doc → [link]" | Notion API |
| 6 | "Your BlackCEO Command Center → [URL]" | Skill 32 output |

Plus the Notion page tree itself (9 top-level sections + nested department/role pages).

## The Notion Page Tree Spec

Created in the **client's own Notion workspace** using their `NOTION_API_TOKEN` (already in their container env).

```
📕 Your Zero-Human Company — [Company Name]
├── 1. What Is a Zero-Human Company?
│      • Positive framing — what it IS and is NOT
│      • Not "no humans" — it's "humans freed from execution"
│      • Owner-led, AI-executed
├── 2. What Is a Zero-Human Workforce?
│      • People-equivalent framing
│      • Departments as teams, agents as employees
│      • Why this matters for delegation
├── 3. Your Workforce Structure
│      • Embed Infographic #1 (Workforce Structure org chart)
│      • Owner → CEO agent → Dept Heads → AI Employees
│      • Lists each department + role count
├── 4. How Your Workforce Runs
│      • Embed Infographic #2 (How Work Flows diagram)
│      • Task in → CEO routes → Dept Head dispatches → output
│      • Real example walkthrough
├── 5. Departments & Roles
│      └── (one sub-page per department)
│              • Department name + purpose
│              • List of roles in this department:
│                  - Name
│                  - What they do
│                  - Purpose
│                  - Ideal use cases (3-5)
│                  - Trigger phrases
├── 6. Communication Hierarchy
│      • Owner → CEO → Dept Heads → AI Employees
│      • Dept Heads spawn temporary sub-agents to get jobs done
│      • Why you talk to the CEO, not the employees, by default
├── 7. Six Sigma in Your ZHC
│      • DMAIC framework (Define / Measure / Analyze / Improve / Control)
│      • How DMAIC applies to YOUR specific departments
│      • Per-department DMAIC snapshot
├── 8. Book-to-Persona System
│      • Separate sub-page
│      • How book-to-persona governs every task
│      • The decision matrix scoring criteria (Relevance / Authority / Recency / Depth / Fit)
└── 9. Your First 7 Days
       • Day-by-day action checklist for week 1
       • What to delegate first
       • What to NOT touch yet
       • When/how to give the CEO feedback
```

The `templates/notion-page-tree.json` file defines this structure programmatically. Placeholders (`{{COMPANY_NAME}}`, `{{DEPARTMENTS}}`, `{{ROLES_BY_DEPT}}`) are filled in from `.workforce-build-state.json` + `workforce-interview-answers.md` at runtime.

## Philosophy: Why a Skill, Not Inline Code

Same reason Skill 23's build-resume layer is a separate component:

1. **Reliability via state machine.** Every step writes status to `.workforce-build-state.json` before moving on. If the agent crashes between steps, the resume cron picks up exactly where it left off — no double-sending, no skipped step.
2. **Cost control.** Each KIE.AI call (image, image, video) has a retry-with-backoff cap so a stuck job doesn't burn credits.
3. **Idempotency.** All Notion pages are created with a deterministic title prefix so re-runs detect "already done" and skip.
4. **Operator visibility.** Trevor can inspect any client's closeoutStatus + the per-step URLs and know exactly what shipped.

## Cost Envelope (Default Caps)

| Item | Model | Approx Cost | Cap |
|------|-------|-------------|-----|
| Infographic #1 | Local HTML + Playwright Chromium (no model call) | $0 | 0 retries needed (deterministic) |
| Infographic #2 | `nano-banana-2` (Nano Banana 2 / Gemini 3.1 Flash Image; fallback `gpt-image-2-text-to-image`) | ~$0.04 / ~$0.04 | 3 retries |
| Celebration video | `gemini-omni-video` (fallback `veo3_fast`) | ~$0.40 | 3 retries (with model fallback) |
| Notion pages | Notion API (free per workspace) | $0 | 3 retries per page |
| Telegram sends | openclaw message send | $0 | 3 retries per send |

Total worst-case cost per client: **~$0.45 in KIE credits** (Infographic #1 is now free; only Infographic #2 + celebration video hit KIE).

## Video Model Selection

**Default video model across OpenClaw:** Veo 3.1 via KIE.ai (model slug `veo3` or `veo3_fast`). Any video gen elsewhere in the codebase should default to Veo 3.1.

**For Skill 37 (ZHC closeout) celebration video specifically:** Gemini Omni Video via KIE.ai (model slug `gemini-omni-video`). Reason: Gemini Omni accepts an image reference (we pass the just-rendered workforce-chart PNG), so the company's brand color, monogram, and CEO agent name carry through into the video. Veo 3.1 cannot accept image guidance.

Override via env var `ZHC_CELEBRATION_VIDEO_MODEL`:

```bash
ZHC_CELEBRATION_VIDEO_MODEL=gemini-omni-video   # default (this skill)
ZHC_CELEBRATION_VIDEO_MODEL=veo3_fast           # general-purpose fallback
ZHC_CELEBRATION_VIDEO_MODEL=veo3                # higher-quality Veo
```

The script also auto-falls-back from `gemini-omni-video` to `veo3_fast` on its third attempt if the Gemini Omni endpoint is unavailable on the KIE account.

## Workforce-Structure Infographic: HTML, not AI image gen

**Infographic #1** is rendered locally via HTML + CSS + a headless Chromium screenshot (Playwright). It is NOT a diffusion-model call.

Why: diffusion models (GPT Image 2, Nano Banana, Imagen) cannot reliably render small text labels. Early fleet closeout attempts came back with garbled department names and missing role counts. HTML + CSS gives perfect text every time, is free per render, and is fully deterministic.

The renderer lives in `templates/workforce-org-chart/`. See its README for details. Infographic #2 (How Work Flows) is stylized enough that AI image gen is still appropriate, and it now uses Nano Banana 2 (KIE slug `nano-banana-2`; the marketing-name `gemini-3-1-flash-image` slug returns HTTP 422 on KIE and is NOT used), which has dramatically better text rendering than the prior `gpt-image-2`.

## Files in This Folder

| File | Purpose |
|------|---------|
| `SKILL.md` | You are here — overview, pipeline placement, page-tree spec |
| `QUALITY-GATE.md` | MANDATORY 8.5 rate + QC gate: rubrics + workflow every deliverable must pass before client delivery |
| `INSTRUCTIONS.md` | Runtime guide: state machine, 6-step pipeline, retry/fail handling |
| `INSTALL.md` | One-time setup (env checks, skill registration) |
| `CORE_UPDATES.md` | Lines appended to workspace AGENTS.md |
| `CHANGELOG.md` | Version history |
| `skill-version.txt` | Machine-readable version pin — the single source of truth for this skill's version (read it at runtime; never hardcode the version elsewhere) |
| `scripts/run-closeout.sh` | Top-level orchestrator |
| `scripts/generate-infographics.sh` | KIE.AI calls for both infographics |
| `scripts/generate-celebration-video.sh` | KIE.AI celebration video (primary `gemini-omni-video`; fallback `veo3_fast`/`veo3`) |
| `scripts/create-notion-closeout.sh` | Notion API page-tree creation |
| `scripts/send-telegram-celebration.sh` | 7-message Telegram delivery |
| `scripts/send-operator-summary.sh` | Success-path operator Telegram summary with LINKS to every delivered artifact (via OpenClaw gateway; opt-in `env.vars.OPERATOR_ESCALATION_CHAT_ID`, back-compat `ZHC_OPERATOR_CHAT_ID` — NO hardcoded default; skips send when unset). Idempotent. |
| `scripts/upload-ghl-media.sh` | Conditional GHL media-library upload of the closeout media (Version 2021-07-28, LOCATION PIT only). Skips gracefully if GHL/Convert-and-Flow + a working PIT are absent. |
| `templates/infographic-1-prompt.md` | Structure infographic prompt template |
| `templates/infographic-2-prompt.md` | Workflow infographic prompt template |
| `templates/veo-prompt.txt` | Veo video prompt template |
| `templates/notion-page-tree.json` | 9-section page-tree template |

## Prerequisites

| Prerequisite | Required | Why |
|--------------|----------|-----|
| Skill 23 build completed (`buildCompletedAt` set) | MANDATORY | Without it, no data to close out |
| Skill 32 (Command Center Setup) installed | MANDATORY | Step 1 of pipeline calls Skill 32 |
| Skill 07 (KIE.AI setup) installed + `KIE_API_KEY` env var | MANDATORY | Steps 2-4 use KIE.AI |
| `NOTION_API_TOKEN` env var on the container | MANDATORY | Step 5 uses Notion API |
| `NOTION_API_VERSION` env var (defaults to `2022-06-28` if unset) | RECOMMENDED | Notion API version pin |
| `openclaw message send` working | MANDATORY | Step 6 uses Telegram delivery |
| `jq` on PATH | MANDATORY | All scripts parse state file with jq |
| `curl` on PATH | MANDATORY | KIE.AI + Notion HTTP calls |

## Security Note

The Notion page tree is created in the **client's own workspace**, using the client's own `NOTION_API_TOKEN`. We never write to Trevor's Notion. The agent never logs the token, and never logs a prefix, suffix or any other substring of it: credential state is reported as `SET` or `NOT-SET` and nothing else. A prefix is still credential material, and terminal transcripts, agent logs and shell history retain every character printed.

The KIE.AI prompts include the company name, owner name, and department list. These are NOT secrets, but treat them as the client's PII — do not include them in CHANGELOG.md examples or in PR descriptions.

## Verification Checklist (Post-Install)

After install completes:
- [ ] `~/.openclaw/skills/37-zhc-closeout/` exists with all listed files
- [ ] `scripts/run-closeout.sh` is `chmod +x`
- [ ] `KIE_API_KEY` is set on the container — presence only, never the value: `[ -n "$KIE_API_KEY" ] && echo "KIE_API_KEY: SET" || echo "KIE_API_KEY: NOT-SET"`
- [ ] `NOTION_API_TOKEN` is set on the container — presence only, never the value: `[ -n "$NOTION_API_TOKEN" ] && echo "NOTION_API_TOKEN: SET" || echo "NOTION_API_TOKEN: NOT-SET"`
- [ ] At least ONE closeout trigger cron exists — `openclaw cron list | grep -E 'closeout-resume|workforce-build-resume'` (v12.34.0: triggers are REDUNDANT; the dedicated `closeout-resume` cron needs no owner chat). Run `scripts/qc-closeout-wiring.sh` to assert files+crons+state in one shot; re-run `update-skills.sh` (now backfills all pipeline crons via `scripts/ensure-pipeline-crons.sh`) if it FAILs.

## Support

- INSTRUCTIONS.md — runtime
- INSTALL.md — one-time setup
- CHANGELOG.md — what changed in which version
- https://docs.openclaw.ai — platform docs
