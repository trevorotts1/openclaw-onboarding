# Skill 37: ZHC Closeout

## MANDATORY - Teach Yourself Protocol (TYP)

**Before using this skill, complete the Teach Yourself Protocol (Skill 01) on this folder.**

Required read order:
1. SKILL.md (this file)
2. INSTRUCTIONS.md — runtime execution guide + state machine + 6-step pipeline
3. INSTALL.md — one-time setup steps (KIE_API_KEY, NOTION_API_TOKEN, budget caps)
4. CORE_UPDATES.md — what gets appended to AGENTS.md
5. CHANGELOG.md — change history

Per N3 ("read before act"), do not skip. Per N4, follow steps in declared order.

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
   └── Step 6: Telegram Delivery (6-message sequence)► closeoutCompletedAt set
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
| 2 | Workforce Structure infographic (Telegram sendPhoto) | KIE.AI gpt-image-1 |
| 3 | How Work Flows infographic (Telegram sendPhoto) | KIE.AI gpt-image-1 |
| 4 | 15–30 sec celebration video (Telegram sendVideo) | KIE.AI Veo 3.1 |
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
| Infographic #1 | `gpt-image-1` (fallback: `nano-banana-pro`) | ~$0.04 / ~$0.09 | 3 retries |
| Infographic #2 | `gpt-image-1` (fallback: `nano-banana-pro`) | ~$0.04 / ~$0.09 | 3 retries |
| Celebration video | `veo3_fast` (Veo 3.1) | ~$0.40 | 2 retries |
| Notion pages | Notion API (free per workspace) | $0 | 3 retries per page |
| Telegram sends | openclaw message send | $0 | 3 retries per send |

Total worst-case cost per client: **~$0.60 in KIE credits**.

## Files in This Folder

| File | Purpose |
|------|---------|
| `SKILL.md` | You are here — overview, pipeline placement, page-tree spec |
| `INSTRUCTIONS.md` | Runtime guide: state machine, 6-step pipeline, retry/fail handling |
| `INSTALL.md` | One-time setup (env checks, skill registration) |
| `CORE_UPDATES.md` | Lines appended to workspace AGENTS.md |
| `CHANGELOG.md` | Version history |
| `skill-version.txt` | Currently `1.0.0` |
| `scripts/run-closeout.sh` | Top-level orchestrator |
| `scripts/generate-infographics.sh` | KIE.AI calls for both infographics |
| `scripts/generate-celebration-video.sh` | KIE.AI Veo 3.1 call |
| `scripts/create-notion-closeout.sh` | Notion API page-tree creation |
| `scripts/send-telegram-celebration.sh` | 6-message Telegram delivery |
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

The Notion page tree is created in the **client's own workspace**, using the client's own `NOTION_API_TOKEN`. We never write to Trevor's Notion. The agent never logs the token — only `${NOTION_API_TOKEN:0:8}...` if a token snippet ever shows up in log output.

The KIE.AI prompts include the company name, owner name, and department list. These are NOT secrets, but treat them as the client's PII — do not include them in CHANGELOG.md examples or in PR descriptions.

## Verification Checklist (Post-Install)

After install completes:
- [ ] `~/.openclaw/skills/37-zhc-closeout/` exists with all listed files
- [ ] `scripts/run-closeout.sh` is `chmod +x`
- [ ] `KIE_API_KEY` is set on the container (`printenv KIE_API_KEY | head -c 8` returns non-empty)
- [ ] `NOTION_API_TOKEN` is set on the container
- [ ] Workforce-build-resume cron exists AND its dirty-state detection includes `closeoutStatus` (re-run `install.sh` if it was installed pre-v10.14.17)

## Support

- INSTRUCTIONS.md — runtime
- INSTALL.md — one-time setup
- CHANGELOG.md — what changed in which version
- https://docs.openclaw.ai — platform docs
