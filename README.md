# OpenClaw Onboarding — Mac mini

> **Version:** see `/version` - this repo at v10.15.36.
> Every release MUST agree across the version-tracked files; run `./scripts/bump-version.sh vX.Y.Z` to update them atomically. Drift is caught in CI (`.github/workflows/version-consistency.yml`).
>
> **NOTE (v10.15.36) — TYP hardening: explicit storage path, pointer format, mandatory no-paste rule.** `01-teach-yourself-protocol` INSTRUCTIONS.md and the full doc (Section 13 + Section 17) now specify the canonical Mac storage path (`~/Downloads/openclaw-master-files/<subfolder>/`), mandatory pointer format (full path + "when to go deeper"), and a non-negotiable no-paste rule: long docs are NEVER pasted into bootstrap files. Shared bootstrap templates (AGENTS.md, TOOLS.md, USER.md, SOUL.md, IDENTITY.md) all carry a short mandatory TYP rule so every agent reads it on session start. TYP skill-version.txt → v6.5.7. Per-release version history lives in [CHANGELOG.md](CHANGELOG.md). VPS (10.16.x) and Mac (10.15.x) sequences remain intentionally independent.
>
> **After every release:** `git tag vX.Y.Z && git push --tags && gh release create vX.Y.Z --notes-from-tag` so the GitHub Releases page mirrors the CHANGELOG.

**A complete onboarding package for setting up a fully operational OpenClaw agent on macOS.**

**Current Version: v10.15.36** — See [CHANGELOG.md](CHANGELOG.md) for the full per-release history.

This repo is **Mac-only**. The Hostinger Docker VPS installer lives at https://github.com/trevorotts1/openclaw-onboarding-vps.

This repo contains **41 numbered skill folders (01 through 41)** — 38 active plus 3 archived (13, 33, 34) — plus an install script and update script. See the [Skill Inventory](#skill-inventory-folder-names) below for the full live list.

> **First time installing or updating?** Read **[ONBOARDING-TRIGGERS.md](ONBOARDING-TRIGGERS.md)** — it shows exactly how to start a fresh install or run an update via Terminal or Telegram.

> **Release history:** Per-release "What's New" notes for v6.x through the current v10.15.x line live in **[CHANGELOG.md](CHANGELOG.md)**. This README shows live state only.

---

## Quick Install (Recommended)

Run this one command on the target machine:

```bash
curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/install.sh | bash
```

What it does:
1. Downloads the latest onboarding package
2. Copies skills into `~/.openclaw/skills/`
3. Installs Gemini Engine early (required by skill 22 and skill 23)
4. Asks for missing API keys with a skip option (does not block optional skills)
5. Prints the next step

---

## Next Step After Install

Open:

- `~/.openclaw/skills/Start Here.md`

That file is the master instruction file. It contains:
- prerequisites
- exact skill install order
- the required file read order per skill
- verification rules
- what to do on failures

---

## Skill Inventory (Folder Names)

| Folder | Skill |
|--------|-------|
| 01-teach-yourself-protocol | Teach Yourself Protocol |
| 02-back-yourself-up-protocol | Back Yourself Up Protocol |
| 03-agent-browser | Agent Browser |
| 04-superpowers | Superpowers |
| 05-ghl-setup | GHL Setup |
| 06-ghl-install-pages | GHL Install Pages |
| 07-kie-setup | KIE Setup |
| 08-vercel-setup | Vercel Setup |
| 09-context7 | Context7 Setup |
| 10-github-setup | GitHub Setup |
| 11-superdesign | Superdesign |
| 12-openrouter-setup | OpenRouter Setup |
| 13-google-workspace-setup-ARCHIVED | Google Workspace Setup (ARCHIVED — replaced by skill 14) |
| 14-google-workspace-integration | Google Workspace Integration |
| 15-blackceo-team-management | BlackCEO Team Management |
| 16-summarize-youtube | Summarize YouTube |
| 17-self-improving-agent | Self-Improving Agent |
| 18-proactive-agent | Proactive Agent |
| 19-humanizer | Humanizer |
| 20-youtube-watcher | YouTube Watcher |
| 21-tavily-search | Tavily Search |
| 22-book-to-persona-coaching-leadership-system | Book-to-Persona Coaching Leadership System |
| 23-ai-workforce-blueprint | AI Workforce Blueprint |
| 24-storyboard-writer | Storyboard Writer |
| 25-video-creator | Video Creator |
| 26-caption-creator | Caption Creator |
| 27-video-editor | Video Editor |
| 28-cinematic-forge | Cinematic Forge |
| 29-ghl-convert-and-flow | GHL Convert and Flow (Tier 3 API reference for skill 36) |
| 30-fish-audio-api-reference | Fish Audio API Reference |
| 31-upgraded-memory-system | Upgraded Memory System |
| 32-command-center-setup | Command Center Setup |
| 33-department-heads-ARCHIVED | Department Heads (ARCHIVED) |
| 34-intelligent-staffing-ARCHIVED | Intelligent Staffing (ARCHIVED) |
| 35-social-media-planner | Social Media Planner — FFmpeg ≥4.0 + kie.ai key required. Routes GHL operations through skill 36 MCPs when installed. |
| 36-ghl-mcp-setup | **GHL MCP Setup** — 5-tier GHL access chain: Official MCP (36 tools) → Community MCP (588 tools) → REST API (skill 29) → Playwright → Codex Computer Use. Sets `$GHL_COMMUNITY_MCP_URL`, installs launchd plist (macOS), wires cardinal rules into SOUL.md/AGENTS.md/TOOLS.md/MEMORY.md, includes 20-assertion QC script. |
| 37-zhc-closeout | **ZHC Closeout** — the zero-human-company build-completion sequence: closeout infographics + celebration video, the multi-section Notion page tree in the client's own workspace, the owner Telegram sequence, the Command Center fire, and n8n wire-up. |
| 38-conversational-ai-system | **Conversational AI System (v10.15.36)** — the conversational AI BRAIN on top of skill 29 (GHL Convert and Flow). 45 protocols (sales brain, intelligent follow-up, dual-mode customer service + support, typed knowledge bases, intelligent routing, weekly + monthly self-tuning, model version freshness, ZHC tag-prefix, F45 geo-qualification, F46 CRM field write, F47 inline smart-FAQ, F49 ZHC Pixel, plus the Round-2 6: F21 multi-tenant isolation, F17 segmentation, F15 proactive outreach, F16 A/B testing, F14 voice/phone, F18 webhook chaining — all default-OFF, etc.). 8 customer journey templates. 68 idempotent OS-aware scripts. 19 references. Sunday 2am + Saturday 11pm + 1st-of-month crons. Skills 05/10/19/29 required as prerequisites. Its `skill-version.txt` versions independently of the repo line. |
| 39-real-estate-playbook | **Real Estate Playbook & Property Intelligence (v10.15.36)** — the real-estate VERTICAL on top of skill 38. Provider-abstraction property intelligence (keyless US Census geocoding + optional Google/Mapbox/RentCast/MLS — honest gap, NEVER fabricated), buyer/seller/investor qualification, showing scheduler (lockbox/MLS rules), 50-state + DC disclosure pointer matrix, lead routing by agent specialty, open-house + pre-foreclosure outreach (pairs with skill 40), and an ADDITIVE Sales-Brain RE extension (RE objections + CMA pricing-reveal timing + SPICED-RE) that drops into skill 38 without editing its own protocol. Emits `real-estate-events.jsonl`. ZHC tags: buyer/seller/investor-lead, pre-foreclosure-prospect. Skill 38 required as prerequisite. |
| 40-zhc-public-records-scraper | **ZHC Public Records Scraper (v10.15.36)** — tiered, compliance-first public-records intelligence and the data sibling of skill 39. address/ZIP → county+state → Tier 1 (curated configs for 21 major counties: Cook, LA, Maricopa, Harris, San Diego, Orange, Miami-Dade, Kings, Dallas, King, Clark, Santa Clara, Tarrant, Riverside, Wayne, Broward, Bexar, Sacramento, San Bernardino, Hillsborough, Pierce) → Tier 2 (platform-adapter framework + Tyler/GovOS example adapters) → Tier 3 (operator-buildable, validated config) → else Tier 4 (HONEST GAP, never fabricated). robots.txt respected, ToS per target, source+timestamp attribution; cost cap + per-day + per-target rate limits with bulk cost confirm; 30-day cache. Emits `public-records-queries.jsonl` (F52 PII-free contract: opaque query_ref/target_ref, record TYPES + counts only). RE use cases (pre-foreclosure/NOD, tax delinquency, comps, permits, tax, ownership). Never runs outreach (that's skill 39). |
| 41-build-with-ai-playbook | **Build With AI Playbook Generator (v10.15.36)** — generates GoHighLevel "Build With AI" conversation playbooks: dependency-ordered build steps, webhook/trigger configuration, prompt-completeness + no-fabrication + no-personal-data + zhc-tag-prefix QC gates (each with a passing negative self-test), and OS-aware (uname -s) install scripts. Templates + protocols for repeatable, verified GHL workflow generation. Installer scripts 00-04 run at client-install time only. |

**Total: 41 numbered skill folders** (01 through 41) — **38 active + 3 archived** (13, 33, 34). This matches the live tree on `main`.

> **Note:** The Voice Call Plugin (`@openclaw/voice-call`) is installed separately via `openclaw plugins install @openclaw/voice-call`. It is NOT part of the onboarding skill sequence — installing it as a skill caused double-install conflicts.

---

## What Is Inside a Skill Folder

Each skill folder contains a subset of these files:
- `SKILL.md`
- `INSTALL.md`
- `INSTRUCTIONS.md`
- `EXAMPLES.md`
- `CORE_UPDATES.md`
- `*.skill` (the OpenClaw install descriptor)

Some skills also include:
- `*-full.md` (a full reference guide)
- `upstream-original/` (for imported skills)
- `scripts/`, `templates/`, `references/`

---

## Notes

- Gemini Engine is installed by `install.sh` before platform skills. There is no separate Gemini Engine skill folder.
- If you fork this repo for client delivery, update `install.sh` to point at your fork.
