# OpenClaw Onboarding

**A complete onboarding package for setting up a fully operational OpenClaw agent.**

**Current Version: v5.1.1** — See [CHANGELOG.md](CHANGELOG.md) for what's new.

This repo contains **31 skill folders** (01 through 31, with 13 archived) plus an install script.

### What's New in v5.0.3 (March 19, 2026)
- **CRITICAL FIX:** memory.backend must be "builtin" not "gemini" to prevent gateway crash on restart

### What's New in v5.0.2 (March 19, 2026)
- **Client approval UX fixed** — non-interactive runs now explain why approval could not be collected
- **Exact 2-step rerun commands shown** so clients know exactly what to do next
- **Clear no-changes-made messaging** — safer and less confusing for clients

### What's New in v5.0.1 (March 19, 2026)
- **update-skills.sh v3.0** — now works on any client machine with dynamic folder detection
- **Backup protocol built in** — backs up core files and config before updates
- **Approval workflow** — shows a plan and waits for explicit approval before changes
- **Verification step** — confirms the update completed and warns if a restart may be needed
- **Never restarts automatically** — user must trigger /restart manually if required

### What's New in v5.0.0 (March 19, 2026)
- **Skill 31: Upgraded Memory System** - 5-layer architecture (markdown files, improved flush, session indexing, Gemini Embedding 2 search, Mem0 auto-capture)
- **Skill 14 rewritten:** Google Workspace CLI (gws) replaces google-api.js and gog - single tool for Gmail and Workspace
- **Skill 23 fixed:** AI Workforce Blueprint now properly presents options A, B, C before asking questions
- **Skill 15 fixed:** BlackCEO Team Management now requires real Telegram IDs, not placeholders
- **QMD fully replaced** with Google Gemini Embedding 2 across all skills and scripts
- **Onboarding watchdog** added: 10-minute stall detection, never-stop-early, progress reporting every 5 skills
- **Mandatory file reading protocol:** agent must read ALL .md files before installing any skill
- **CONTRIBUTING.md** added: complete checklist for adding/modifying skills
- **MIGRATION.md** added: step-by-step guide for existing QMD users to migrate to Gemini Embedding 2

- Install happens in a strict order
- The agent executes the steps autonomously
- Humans only provide credentials, API keys, 2FA codes, and first time logins when required

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
| 12-openrouter-setup | OpenRouter Setup (last) |
| 13-google-workspace-setup | Google Workspace Setup |
| 14-google-workspace-integration | Google Workspace Integration |
| 15-blackceo-team-management | Team Management |
| 16-summarize-youtube | Summarize YouTube |
| 17-self-improving-agent | Self Improving Agent |
| 18-proactive-agent | Proactive Agent |
| 19-humanizer | Humanizer |
| 20-youtube-watcher | YouTube Watcher |
| 21-tavily-search | Tavily Search |
| 22-book-to-persona-coaching-leadership-system | Book to Persona Coaching Leadership System |
| 23-ai-workforce-blueprint | AI Workforce Blueprint |
| 24-storyboard-writer | Storyboard Writer |
| 25-video-creator | Video Creator |
| 26-caption-creator | Caption Creator |
| 27-video-editor | Video Editor |
| 28-cinematic-forge | Cinematic Forge |
| 29-ghl-convert-and-flow | GHL Convert and Flow |
| 30-fish-audio-api-reference | Fish Audio API Reference |

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
