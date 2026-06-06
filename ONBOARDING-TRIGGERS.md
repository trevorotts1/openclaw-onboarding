# How to Trigger OpenClaw Onboarding

This document shows you exactly how to start a fresh OpenClaw install or run an update on an existing install. There are **8 different ways to do it**, depending on (1) what kind of machine you have, (2) whether this is your first install or an update, and (3) whether you'd rather use Terminal or your Telegram agent.

---

## 🔴 N22 — Triple-Fire Trigger Semantics (Unconditional)

Every install kickoff in this document, regardless of which of the 8 blocks below is used, fires **ALL THREE** triggers in `fire_install_kickoff_triplet()`:

1. **Telegram message** — sent via `openclaw message send`. If the CLI isn't on PATH yet (first-time install), falls back to `scripts/send-telegram.sh` helper, otherwise logs the reason and defers delivery to the first post-install agent session. **The attempt is unconditional.**
2. **AGENTS.md flag** — appends `<!-- OPENCLAW_ONBOARDING_KICKOFF:<version> --> ... <!-- OPENCLAW_ONBOARDING_KICKOFF_END -->` to `$HOME/.openclaw/AGENTS.md` (Mac) or `/data/.openclaw/AGENTS.md` (VPS). Parent dir auto-created with `mkdir -p` if missing. **The attempt is unconditional.**
3. **Terminal block** — printed via `cat <<TERMEOF` with no guard. **Always fires, always visible in the terminal.**

This is **not "any one of three"** — all three attempts MUST happen on every install kickoff (and every Sunday-update detection, see `cron-prompt.txt` RULE 5.5 + `check-updates.sh`). Best-effort delivery with reason logging when a path fails, but the **attempt** is unconditional. This is the N22 binding.

The same triple-fire pattern applies to:
- Install kickoff: `install.sh::fire_install_kickoff_triplet()` (both Mac + VPS repos)
- Update detection: `check-updates.sh` appends to AGENTS.md when `has_repo_update=true` or `has_skill_updates=true`
- Force-update: `force-update.sh` (manual command at repo root) fires all three on demand

If you see a kickoff where only one of three fired and no `reason` was logged in the terminal block — that's a bug, file it.

---

Pick the one block below that matches your exact situation. Each block is self-contained — you don't need to read the others.

---

## Quick block selector

| Your machine | Full onboarding or update? | Terminal or Telegram? | Jump to |
|---|---|---|---|
| Mac (Mac Mini, MacBook, iMac, Mac Pro) | Full onboarding | Terminal | [Block 1](#block-1--mac-full-onboarding-via-terminal) |
| Mac (Mac Mini, MacBook, iMac, Mac Pro) | Full onboarding | Telegram ⭐ | [Block 2](#block-2--mac-full-onboarding-via-telegram) |
| VPS / Hostinger / cloud server | Full onboarding | Terminal | [Block 3](#block-3--vps-full-onboarding-via-terminal) |
| VPS / Hostinger / cloud server | Full onboarding | Telegram ⭐ | [Block 4](#block-4--vps-full-onboarding-via-telegram) |
| Mac (Mac Mini, MacBook, iMac, Mac Pro) | Update | Terminal | [Block 5](#block-5--mac-update-via-terminal) |
| Mac (Mac Mini, MacBook, iMac, Mac Pro) | Update | Telegram | [Block 6](#block-6--mac-update-via-telegram) |
| VPS / Hostinger / cloud server | Update | Terminal | [Block 7](#block-7--vps-update-via-terminal) |
| VPS / Hostinger / cloud server | Update | Telegram | [Block 8](#block-8--vps-update-via-telegram) |

⭐ = Standard path. Every client arrives with a baseline OpenClaw + Telegram agent already configured; Block 2 (Mac) or Block 4 (VPS) is what lifts that baseline to the full 36-skill package. Terminal blocks (1, 3) are for self-service or bootstrap scenarios.

**Not sure if it's a full onboarding or an update?**
- If this is a new client being lifted from the baseline OpenClaw + Telegram setup to the full 36-skill onboarding package, it's a **full onboarding** (Blocks 1–4).
- If they already have the full package and you just want the latest skills + bug fixes, it's an **update** (Blocks 5–8).

**Not sure if your machine is a Mac or a VPS?**
- A Mac is the computer sitting on your desk or in your home/office. You sit in front of it.
- A VPS (Virtual Private Server) is a computer you rented from a cloud provider like Hostinger or DigitalOcean. You connect to it remotely — it lives somewhere else.

---

## What actually gets installed

A fresh install lays down **43 numbered skill folders** (40 active, 3 archived) plus the agent runtime, memory architecture, and persona system. The headline pieces:

- **Skill 01 — Teach Yourself Protocol** — governs how the agent stores new knowledge
- **Skill 02 — Back Yourself Up Protocol** — config + secret backups before any change
- **Skill 05 — GHL Setup** — discovers and stores your GoHighLevel Private Integration Token + Location ID at the canonical secrets path
- **Skill 22 — Book-to-Persona** — main-orchestrator-only; converts books into voice personas
- **Skill 23 — AI Workforce Blueprint** — main-orchestrator-only; designs your AI team
- **Skill 29 — GHL Convert and Flow** — reference files for every GHL REST endpoint (used as the Tier 3 fallback in the 5-tier chain)
- **Skill 31 — Upgraded Memory System** — 8-layer memory architecture foundation
- **Skill 32 — Trade Show Mode** — event-on, event-off automation
- **Skill 35 — Social Media Planner** — posts to GHL Social Planner / Blog / Media Library, MCP-first
- **Skill 36 — GHL MCP Setup** — wires the **5-tier GHL access chain** (Official MCP → Community MCP on port 8765 → Direct REST → Playwright → Codex), runs a local Node server under launchd (Mac) or systemd (VPS), and installs the disclosure-header protocol so every GHL response shows which tier it used. Bundles a standalone `qc-ghl-mcp-setup.sh` validator that probes live rate-limit quota.

The rest are domain skills (CRM ops, calendars, content, payments, observability, etc.). Your agent reads every skill's `SKILL.md`, `INSTALL.md`, `INSTRUCTIONS.md`, and `QC.md` and walks through activation in dependency-aware waves.

---

## 🔴 Before you trigger GHL work — read this

GoHighLevel enforces strict per-location rate limits that apply to **every install block on this page** the moment a GHL-touching skill runs its QC:

- **Burst:** 100 requests per 10 seconds, per location
- **Daily:** 200,000 requests per day, per location
- **Shared bucket:** Skill 36's three MCP tiers (Official MCP, Community MCP, Direct REST) all hit the same backend. Switching tiers does NOT bypass the cap.

If you trigger a fresh install or update while your daily quota is nearly burned (this happened on 2026-05-13 — a single bulk run torched all 200k calls), Skill 36's QC script will detect it and refuse to proceed until quota resets the next day. That is by design. If you see the message "GHL daily quota is low / I skipped GHL verification" in your agent's report, that is the protection working. Wait until the daily reset clock the agent gives you, then re-run.

---

## BLOCK 1 — Mac, Full Onboarding, via Terminal

### What this does
Installs the full OpenClaw onboarding package on your Mac: all 36 skills, your agent setup, memory architecture, persona system, GHL MCPs — everything. About 5–15 minutes depending on internet speed.

### Before you start
- Make sure your Mac is connected to the internet
- Make sure you can find your Mac's Terminal app (we'll show you how below)
- Have your GHL Private Integration Token and Location ID ready if you want GHL connected during install (otherwise the script will let you skip and add them later)

### Step 1 — Open Terminal on your Mac

1. Press **Command (⌘) + Space** at the same time. A search bar appears in the middle of your screen.
2. Type the word **Terminal**.
3. Press **Return / Enter** on your keyboard.
4. A black or white window opens with some text. That's Terminal. You're in the right place.

### Step 2 — Paste this command and press Return

Copy the entire line between the markers, paste it into Terminal, and press **Return / Enter**:

```
curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/install.sh | bash
```

### What you'll see while it runs

Lines of progress will scroll by. You'll see messages like:

- `Step 1: ...` / `Step 2: ...` / etc. — the script works through about 11 steps
- Skills being copied into `~/.openclaw/skills/`
- `Silent Credential Discovery` — the script looks for any API keys or PITs you already have stored
- `Configuring Active Memory (Layer 8)` — memory system being set up
- `Sub-agent concurrency configured at install time (50 concurrent, 10 queue, 4 depth)`
- `UPDATE PENDING flag written to AGENTS.md` — this is what your agent will read after install

The whole run takes **5–15 minutes**. Don't close Terminal while it's running.

### When it finishes

Two things happen at the end of the install:

1. **A big ASCII box prints in your Terminal window** that looks like this:
   ```
   ╔════════════════════════════════════════════════════════════════════╗
   ║   BACKUP — IF YOU DID NOT GET A TELEGRAM NOTE                      ║
   ╠════════════════════════════════════════════════════════════════════╣
   ║   ... instructions for what to paste to your agent ...             ║
   ╚════════════════════════════════════════════════════════════════════╝
   ```
   This box is your safety net. We'll come back to it.

2. **Your Telegram should ding** with a message from your OpenClaw bot containing the exact instructions to paste to your agent.

### Success looks like this

- Terminal ends with `✓ OpenClaw Onboarding v9.1.x installed` and a green status line: `✓ Telegram completion note sent to [YOUR_CHAT_ID]`
- You receive a Telegram message from your OpenClaw bot. It starts with `✅ OpenClaw Onboarding v9.1.x install complete` and contains a `▶` arrow followed by the instruction to paste to your agent
- Copy the instruction inside the Telegram message and paste it back to your agent on Telegram. Your agent reads your AGENTS.md, sees the UPDATE PENDING flag, and walks through the rest of the setup automatically. You do not have to type any more commands.

### If something looks wrong

- **Terminal shows `⚠ Telegram skipped — no telegram.allowFrom configured`** — your Telegram isn't set up to receive notifications from your OpenClaw. Use the backup ASCII box at the bottom of Terminal: copy the instruction between `>>>` and `<<<`, paste it to your agent in whatever app you use to talk to your agent.
- **Terminal shows `⚠ Telegram completion note FAILED`** — Telegram is configured but the send failed. Same fix: use the backup ASCII box.
- **You didn't get a Telegram note AND you don't see the backup ASCII box** — scroll up in Terminal. The box is near the bottom, just before the gateway restart message. If you genuinely don't see it, the install didn't complete; re-run the curl command from Step 2.

### How to verify it worked

Wait about 30 seconds after Terminal finishes (gateway needs to restart), then ask your agent (in Telegram, web chat, or however you talk to it):

> *"Are all my skills activated? Give me a summary."*

You should get back a list of skills with statuses. If anything failed, your agent will tell you and propose a fix.

**What "done" actually means (v10.15.48 — onboarding honesty gate).** Files on
disk are NOT "installed". Onboarding tracks every skill in a state file
`~/.openclaw/workspace/.onboarding-state.json` (`pending → downloaded → wired →
qc-passed`) and a skill counts INSTALLED only when it is registered
(`openclaw skills info`), its CORE_UPDATES landed, and its QC passes. The `✅`
message is now sent ONLY when that gate passes — otherwise you get an honest
"X/Y verified, Z still being activated" message. An `onboarding-resume` cron
re-fires activation + QC every 15 minutes until every skill passes, so an
interrupted install finishes itself. To see the live truth, ask your agent:

> *"Run the onboarding verification gate (obs_gate_summary) and tell me the exact verified count."*

---

## BLOCK 2 — Mac, Full Onboarding, via Telegram

### What this does
Tells your existing OpenClaw Telegram agent to run the full onboarding package install on your Mac for you. You don't open Terminal yourself — the agent does it via its shell-exec capability. End result: all 36 skills, the full memory architecture, personas, and tooling are deployed on top of your baseline OpenClaw + Telegram setup. This is the **standard onboarding path** — clients arrive with a minimal OpenClaw + Telegram bot already configured, and this block lifts them to the full package.

### Before you start
- You have an existing OpenClaw + Telegram agent you currently chat with (the standard pre-onboarding baseline)
- The agent has shell-exec permissions (standard for OpenClaw)
- Have your GHL Private Integration Token and Location ID ready in case the install asks for them

### Step 1 — Open Telegram

Open the Telegram app on your phone or computer. Find your existing conversation with your OpenClaw bot.

### Step 2 — Paste this exact message to your agent

Copy everything between the `>>>` and `<<<` markers below. Paste it as a single message to your agent. Send.

```
>>>
I need you to run the OpenClaw onboarding fresh install on my Mac and follow these rules exactly. This is a long but complete instruction set — read it all before you start.

RULE 1 — Run this command on my Mac using your shell-exec capability. Run it exactly as written, character for character, no edits:
  curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/install.sh | bash

RULE 2 — Do not modify the command. Do not change the URL. Do not add flags. Do not pipe to anything other than bash. If you think the command needs a tweak, ask me first — do not assume.

RULE 3 — Watch the install output continuously. You should never lose track of which step the install is on. Capture stdout AND stderr.

RULE 4 — Send me progress updates every 5 skills installed OR every 2 minutes, whichever comes first. Plain English headlines only, no raw error logs unless I ask.

RULE 5 — When the install completes, my system writes an UPDATE PENDING flag at the top of my workspace AGENTS.md file. Read that flag completely before doing anything else.

RULE 6 — Follow the 5-Phase Processing Order in the UPDATE PENDING flag EXACTLY. Do not improvise. Do not skip phases. Do not reorder phases.

RULE 7 — Phase A: parallel install of all skills in 5 waves. Timeout: 600 seconds (10 minutes). Wave 1 = Skills 01–06, Wave 2 = 07–12, Wave 3 = 13–18, Wave 4 = 19–24, Wave 5 = 25–36.

RULE 8 — Phase B: activate foundation skills (Skill 31 Upgraded Memory System and Skill 22 Book-to-Persona). Timeout: 900 seconds.

RULE 9 — Phase C: process interactive skills (Skill 23 AI Workforce Blueprint, Skill 35 Social Media Planner). Timeout: 1200 seconds. EXCEPTION: Skill 23 requires live owner answers — if the owner is not actively present in this session when Skill 23 runs, write INTERVIEW_PENDING to interview-handoff.md and move to the next skill. NEVER run Option B autonomously. NEVER fabricate interview answers.

RULE 10 — Phase D: validate all skill installations and run QC. Timeout: 1800 seconds.

RULE 11 — Phase E: final QC and report to me. No timeout.

RULE 12 — Sub-agent concurrency limits: max 50 concurrent sub-agents, queue depth 10, spawn depth 4. NEVER exceed these.

RULE 13 — Run the bundled QC checks for every single skill. Each skill has a QC.md file with a 0–10 scoring rubric. Aim for 8 out of 10 or higher. If a skill scores below 8, stop and tell me which skill failed and why.

RULE 14 — Skills 22 and 23 are MAIN ORCHESTRATOR ONLY. Never delegate them to sub-agents. You must process those yourself.

RULE 15 — Skill 36 (GHL MCP Setup) has a special bundled script called qc-ghl-mcp-setup.sh. You MUST run that script after install and it MUST exit with status 0 before you call GHL done. If it exits non-zero, tell me which assertion failed.

RULE 16 — STOP IMMEDIATELY and ask me before doing any of these:
  (a) A skill needs an API key, password, PIT, or credential you cannot find in my .env files OR openclaw.json env.vars
  (b) A skill explicitly asks for owner input or a decision
  (c) A QC check fails and you don't have a clear, documented fix
  (d) You're about to push to GitHub, send a message to anyone other than me, post to social media, or take any externally-visible action
  (e) You think a step is unnecessary and want to skip it (the answer is don't skip it — ask first)

RULE 17 — NEVER take these shortcuts under any circumstances:
  (a) No --break-system-packages
  (b) No --force
  (c) No --no-verify
  (d) No --no-gpg-sign
  (e) No substituting a model name for one you "think is better"
  (f) No inventing steps that aren't in the install script or the UPDATE PENDING flag

RULE 18 — Watchdog: if you go more than 10 minutes without progress on a single skill, send me an alert explaining where you're stuck.

RULE 19 — Total time budget: aim for under 30 minutes from start to final summary. If you go over 30 minutes, send a progress note explaining what's slow.

RULE 20 — Communication style: I am over 60. I want plain English, no acronyms unless you explain them, headlines first, technical details only if I ask. Never assume I know what an acronym means. Never paste raw stack traces unless I ask.

RULE 21 — When everything is complete:
  (a) Remove the entire UPDATE PENDING section from my AGENTS.md
  (b) Append one line to my MEMORY.md under "## System Updates" with today's date and the version installed
  (c) Send me a final summary in this exact shape: "Install complete. [N] skills active. Memory: 8 layers verified. Personas: [M] available. Anything that needs my attention: [bulleted list, or 'nothing']."

RULE 22 — Confirm you understand by replying with "Got it — starting your install" followed by a brief plain-English summary (2–3 sentences) of what you're about to do. Then start. Do not skip the confirmation step.
<<<
```

### What you'll see while it runs

- Your agent will reply confirming it understands. It will say "Got it — starting your install" and a short summary.
- Every few minutes you'll get a progress update: *"5 of 36 skills installed,"* *"Phase A complete, moving to Phase B,"* *"Running QC on Skill 31,"* etc.
- If the agent has a question for you (per RULE 16), it will stop and ask in plain English. Answer the question — the agent will not move on until you respond.

### Success looks like this

A final summary message from your agent that looks roughly like:

> *"Install complete. 33 skills active (3 archived skills skipped as expected). Memory: 8 layers verified. Personas: 40 available. Anything that needs my attention: nothing — everything passed QC."*

### If something looks wrong

- **Your agent stops replying for 10+ minutes** — send: *"Are you still working on the install? What's the current status?"* The watchdog rule should make this rare, but ask anyway.
- **The agent sends you an error you don't understand** — send: *"Explain that error in plain English. What does it mean and what do you need from me to keep going?"*
- **The agent says it can't find a credential** — that's expected if you don't have a PIT or API key for some service. Tell the agent to skip that credential for now and continue. You can add it later.
- **The agent tries to skip a step or take a shortcut** — say no firmly: *"Do not skip that step. Either complete it as written or stop and tell me why you can't."*

---

## BLOCK 3 — VPS, Full Onboarding, via Terminal

### What this does
Installs OpenClaw on your VPS (Hostinger, DigitalOcean, AWS, or any cloud server). Skills land at `/data/Downloads/openclaw-master-files/` because a VPS doesn't have a `~/Downloads` folder — the persistent volume is `/data/` instead. About 10–20 minutes.

### Before you start
- You need SSH access to your VPS (IP address, username, password or key)
- You'll need a terminal app on your local Mac (built-in Terminal) or Windows (built-in Windows Terminal / PowerShell)
- Have your GHL Private Integration Token and Location ID ready

### Step 1 — Open Terminal locally and SSH into your VPS

On your Mac (or Windows), open your local Terminal. Paste:

```
ssh root@YOUR.VPS.IP.ADDRESS
```

Replace `YOUR.VPS.IP.ADDRESS` with the actual IP address your hosting provider gave you (it'll look something like `177.7.42.223`). Press Return. Enter the password when prompted.

You'll know you're connected when the prompt changes to show the VPS hostname.

### Step 2 — Paste the VPS install command and press Return

```
curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding-vps/main/install.sh | bash
```

### What you'll see while it runs

Same as Block 1, but paths land under `/data/` instead of `~/`:
- `Step 1` through `Step 11`
- Skills copied to `/data/.openclaw/skills/`
- `Silent Credential Discovery` checks `/data/.openclaw/secrets/.env`
- `UPDATE PENDING flag written to /data/clawd/AGENTS.md`

10–20 minutes total. Do not close the SSH session.

### When it finishes

Same pattern as Block 1:
1. Big ASCII backup box prints in Terminal
2. Your Telegram should ding with a paste-ready message for your agent

### Success looks like this

- Terminal: `✓ OpenClaw Onboarding v9.1.x installed` + `✓ Telegram completion note sent`
- Telegram: paste-ready message from your bot
- Your VPS agent receives the paste and walks through the rest of the setup

### If something looks wrong

- **`Permission denied` during SSH** — your password or key is wrong. Check your hosting provider's control panel for the correct credentials.
- **`No space left on device`** — your VPS's `/data/` volume is full. Run `df -h /data` to check disk usage. You may need to upgrade your VPS plan or clean up old files.
- **Telegram silent fail** — same fix as Block 1: use the backup ASCII box at the bottom of Terminal.

### How to verify it worked

In Telegram, ask:

> *"Are all my skills activated on the VPS? Give me a summary."*

---

## BLOCK 4 — VPS, Full Onboarding, via Telegram

### What this does
Your VPS's own OpenClaw agent receives a Telegram message from you and runs the full onboarding package install locally on the VPS. You never SSH in. End result: all 36 skills, the full memory architecture, personas, and tooling are deployed on top of your VPS's baseline OpenClaw + Telegram setup. This is the **standard onboarding path for VPS clients**.

### Before you start
- Your VPS has the baseline OpenClaw + Telegram agent already running (standard pre-onboarding baseline)
- IMPORTANT: if you have BOTH a Mac AND a VPS, make sure you're sending this message to your **VPS** bot, not your Mac bot. They're different agents. If you send the VPS install to the Mac bot, the Mac will reject it.
- Have your GHL credentials ready

### Step 1 — Open Telegram

Open Telegram. Find your conversation with your **VPS** OpenClaw bot.

### Step 2 — Paste this exact message

```
>>>
I need you to run the OpenClaw onboarding fresh install on this VPS and follow these rules exactly. This is a long instruction set — read it all before you start.

RULE 1 — Run this command on the VPS using your shell-exec capability. Run it exactly as written, no edits:
  curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding-vps/main/install.sh | bash

RULE 2 — Do not modify the command. Do not change the URL (note the URL ends in -vps/main/install.sh — this is the VPS variant, not the Mac one). Do not add flags.

RULE 3 — VPS file paths are different from Mac. Skills land at /data/.openclaw/skills/ not ~/.openclaw/skills/. Secrets at /data/.openclaw/secrets/.env not ~/.openclaw/secrets/.env. Workspace at /data/clawd not ~/clawd. The install script knows this — do not override paths.

RULE 4 — Watch the install output continuously. Tell me progress every 5 skills OR every 2 minutes, whichever comes first.

RULE 5 — Plain English headlines only. No raw error logs unless I ask.

RULE 6 — When the install finishes, an UPDATE PENDING flag is written to the top of /data/clawd/AGENTS.md (the VPS workspace AGENTS.md, not anything on the Mac). Read the flag completely.

RULE 7 — Follow the 5-Phase Processing Order in the flag EXACTLY:
  Phase A: parallel install in 5 waves (timeout 600s)
  Phase B: activate foundation skills 31 + 22 (timeout 900s)
  Phase C: process interactive skills 23 + 35 (timeout 1200s) — EXCEPTION: Skill 23 needs live owner answers; if owner not present, write INTERVIEW_PENDING to interview-handoff.md and skip to Phase D. Never run Option B. Never fabricate.
  Phase D: validate + QC (timeout 1800s)
  Phase E: final QC + report (no timeout)

RULE 8 — Sub-agent limits: max 50 concurrent, queue 10, spawn depth 4. Never exceed.

RULE 9 — QC every skill against its bundled QC.md. Aim for 8/10 or higher. Anything below 8 — stop and tell me which skill and what failed.

RULE 10 — Skills 22 and 23: MAIN ORCHESTRATOR ONLY, never delegate.

RULE 11 — Skill 36 (GHL MCP) must run its qc-ghl-mcp-setup.sh script. The script must exit with status 0 before you call GHL done.

RULE 12 — STOP and ask me before doing any of:
  (a) Skill needs a credential not found in /data/.openclaw/secrets/.env or openclaw.json env.vars
  (b) Skill asks for owner input
  (c) QC check fails without a clear fix
  (d) You're about to push to GitHub, send a message to anyone other than me, post anywhere externally
  (e) You think a step is skippable (ask first; the answer is don't skip)

RULE 13 — NEVER use these shortcuts:
  (a) --break-system-packages
  (b) --force
  (c) --no-verify
  (d) --no-gpg-sign
  (e) Model name substitution
  (f) Steps not in the install script or UPDATE PENDING flag

RULE 14 — Watchdog: 10 minutes stalled on one skill = send me an alert.

RULE 15 — Total time budget: under 40 minutes for VPS install (slightly longer than Mac due to network latency). Send progress note if over.

RULE 16 — Communication: plain English, no acronyms unless explained, headlines first, I'm over 60.

RULE 17 — When complete:
  (a) Remove UPDATE PENDING section from /data/clawd/AGENTS.md
  (b) Append to /data/clawd/MEMORY.md under "## System Updates" with date + version
  (c) Final summary: "VPS install complete. [N] skills active. Memory: 8 layers verified. Personas: [M] available. Anything pending my attention: [list or 'nothing']."

RULE 18 — Confirm with "Got it — starting your VPS install" + 2–3 sentence plain-English summary. Then start.
<<<
```

### What you'll see while it runs

Same flow as Block 2 but the bot is your VPS bot. Progress updates, agent questions if it needs your input.

### Success looks like this

Final summary message similar to Block 2 but mentioning VPS.

### If something looks wrong

Same fixes as Block 2.

---

## BLOCK 5 — Mac, Update, via Terminal

### What this does
Updates an existing Mac OpenClaw install to the latest version. Checks what skills you currently have, compares against the GitHub repo, installs anything new, replaces anything that changed, and leaves unchanged skills alone. Non-destructive — your settings and credentials are preserved.

**This works for ANY prior version.** Doesn't matter if you're on v3.x, v6.x, v8.x, or whatever — the script figures it out.

### Before you start
- Your Mac already has OpenClaw running from a previous install
- You have internet
- You'll see a small confirmation prompt if your current version matches the latest (asking if you want to force re-install)

### Step 1 — Open Terminal

Same as Block 1: ⌘+Space → type **Terminal** → Return.

### Step 2 — Paste the update command and press Return

```
curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/update-skills.sh | bash
```

### What you'll see while it runs

- `📂 Skills directory: /Users/[you]/.openclaw/skills` (or `~/Downloads/openclaw-master-files/`)
- `Current version: vX.Y.Z` / `Latest version: v9.1.x`
- `Downloading latest skills from GitHub...`
- `Creating backup: ~/Downloads/openclaw-backups/skills-backup-YYYYMMDD-HHMMSS` — your old skills get backed up before any change
- For each skill being installed: either `Updated: NN-skill-name` (replaced in place) or `🆕 NEW SKILL DETECTED: NN-skill-name` followed by activation instructions for your agent
- At the end: `Skills updated successfully!` + UPDATE PENDING flag written + Telegram status line + backup ASCII box

3–10 minutes total.

### When it finishes

Same as install: Telegram ding + backup ASCII box in Terminal. The Telegram message lists which skills were newly installed (need activation) and which were updated in place (already working).

### Success looks like this

- Terminal: `Skills updated successfully! Version: v9.1.x`
- Terminal: `✓ Telegram sent to [YOUR_CHAT_ID]`
- Telegram: paste-ready message listing new skills + activation prompt
- Backup folder exists at `~/Downloads/openclaw-backups/` in case you need to roll back

### If something looks wrong

- **`openclaw command not found`** — the OpenClaw CLI isn't on your PATH yet. Run `which openclaw` to find it. If empty, your previous install may be broken; use Block 1 to do a fresh install instead.
- **`Already up to date`** — you already have the latest version. The script will ask if you want to force re-install. Answer `y` only if you suspect something is broken and want to refresh everything.
- **`ERROR: Could not find extracted folder`** — the download from GitHub failed or got corrupted. Re-run the update command.

### How to verify it worked

Wait 30 seconds, then ask your agent:

> *"What changed in this update? List newly installed skills and anything updated."*

---

## BLOCK 6 — Mac, Update, via Telegram

### What this does
Tells your existing OpenClaw Telegram agent to run the update on your Mac. Hands-free version of Block 5.

### Before you start
Same as Block 2 — you need a working OpenClaw + Telegram setup with shell-exec.

### Step 1 — Open Telegram

Find your conversation with your **Mac** OpenClaw bot.

### Step 2 — Paste this exact message

```
>>>
I need you to run the OpenClaw skills updater on my Mac and follow these rules exactly. Read all rules before starting.

RULE 1 — Run this command on my Mac using your shell-exec capability. Run it exactly as written, no edits:
  curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/update-skills.sh | bash

RULE 2 — Do not modify the command, URL, or add flags. If a tweak seems needed, ask me first.

RULE 3 — Watch the update output. Send me a progress note when the download finishes and when the skill copy loop completes.

RULE 4 — Plain English headlines only.

RULE 5 — When the update completes, an UPDATE PENDING flag is written at the top of my AGENTS.md. The flag lists which skills are NEW (didn't exist before) and which were UPDATED in place. Read the flag completely.

RULE 6 — For each NEW skill listed in the flag:
  (a) Read ALL files in the skill folder: SKILL.md, INSTALL.md, INSTRUCTIONS.md, EXAMPLES.md, CORE_UPDATES.md, QC.md, and any references/*.md
  (b) Check prerequisites first. Search ALL standard credential locations BEFORE asking me: ~/.openclaw/secrets/.env, openclaw.json env.vars, printenv, ~/.env, ~/clawd/secrets/.env
  (c) Execute the activation steps in INSTALL.md. Reading is NOT executing — actually run the steps.
  (d) Apply CORE_UPDATES.md surgically. Only add the sections explicitly labeled in CORE_UPDATES.md to my AGENTS.md / TOOLS.md / MEMORY.md / SOUL.md. Never dump full skill content into core files.
  (e) Run the QC checks in QC.md. Reach a passing score (8/10 or higher) before moving to the next skill.
  (f) If the skill has a bundled qc-*.sh script (like Skill 36's qc-ghl-mcp-setup.sh), run it and confirm exit 0.

RULE 7 — For UPDATED skills (already in place, just refreshed by the update script): assume activation is unchanged. Do NOT re-activate unless I explicitly ask. The file replacement is sufficient.

RULE 8 — Sub-agent limits: max 50 concurrent, queue 10, spawn depth 4. Never exceed.

RULE 9 — Skills 22 and 23 (if newly installed): MAIN ORCHESTRATOR ONLY, never delegate.

RULE 10 — Skill 36 — if newly installed OR if its launchd plist was updated by the refresh, run qc-ghl-mcp-setup.sh and confirm exit 0.

RULE 11 — STOP and ask me before:
  (a) A skill needs a credential not in my .env / openclaw.json
  (b) A skill asks for owner input
  (c) A QC check fails without a clear fix
  (d) You're about to push to GitHub, message anyone other than me, or take any external action
  (e) You think a step is skippable

RULE 12 — NEVER use: --break-system-packages, --force, --no-verify, --no-gpg-sign, model substitution, or invented steps.

RULE 13 — Watchdog: 10 minutes stalled = alert me.

RULE 14 — Time budget: 15 minutes for a typical update (much less than a fresh install). Progress note if over.

RULE 15 — Communication: plain English, no acronyms unless explained, headlines first, I'm over 60.

RULE 16 — When complete:
  (a) Remove the UPDATE PENDING section from my AGENTS.md
  (b) Append to MEMORY.md under "## System Updates" — today's date + version + list of newly-installed skills
  (c) Final summary: "Update complete. Newly installed: [list of new skills or 'none']. Updated in place: [count]. Anything needing my attention: [list or 'nothing']."

RULE 17 — Confirm with "Got it — starting your update" + 2–3 sentence summary. Then start.
<<<
```

### What you'll see while it runs

Agent confirms understanding, runs the update, sends progress notes, processes any NEW skills' activation steps.

### Success looks like this

Final summary listing newly installed skills (if any) and confirming updates landed.

### If something looks wrong

Same fixes as Block 2 — ask the agent in plain English what's happening, demand it stop and explain rather than skip.

---

## BLOCK 7 — VPS, Update, via Terminal

### What this does
Updates an existing VPS install to the latest version. Same as Block 5 but for VPS paths (`/data/.openclaw/skills/` and `/data/Downloads/openclaw-master-files/`).

### Before you start
Same as Block 3 — SSH access to your VPS.

### Step 1 — SSH into your VPS

```
ssh root@YOUR.VPS.IP.ADDRESS
```

### Step 2 — Paste the VPS update command

```
curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding-vps/main/update-skills.sh | bash
```

### What you'll see

- `📂 Skills directory: /data/.openclaw/skills` (or `/data/Downloads/openclaw-master-files/`)
- Backup created at `~/openclaw-backups/skills-backup-YYYYMMDD-HHMMSS` (note: VPS backups go to home, not Downloads)
- Skill copy loop
- UPDATE PENDING flag + Telegram + backup ASCII box at the end

3–10 minutes.

### Success looks like this

Same as Block 5 but with VPS paths in the summary.

### If something looks wrong

- **`ssh: connection refused`** — your VPS may be offline or rebooting. Check your hosting provider's control panel.
- **`No space left on device`** — VPS storage full; check `df -h /data`.
- **`openclaw command not found`** — VPS CLI missing; use Block 3 to do a fresh install.

### How to verify it worked

In Telegram (after gateway restart finishes ~30 seconds later):

> *"What changed in this VPS update? List newly installed skills."*

---

## BLOCK 8 — VPS, Update, via Telegram

### What this does
Your VPS's own agent receives a Telegram message and runs the update on the VPS. Hands-free version of Block 7.

### Before you start
Same as Block 4 — make sure you're messaging the **VPS** bot, not the Mac bot.

### Step 1 — Open Telegram

Find your **VPS** OpenClaw bot conversation.

### Step 2 — Paste this exact message

```
>>>
I need you to run the OpenClaw skills updater on this VPS and follow these rules exactly. Read all rules before starting.

RULE 1 — Run this command on the VPS using your shell-exec capability. Run it exactly as written, no edits:
  curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding-vps/main/update-skills.sh | bash

RULE 2 — Do not modify the command. The URL ends in -vps/main/update-skills.sh — confirm you're using the VPS variant, not the Mac variant.

RULE 3 — VPS paths are different from Mac. Skills at /data/.openclaw/skills/. Secrets at /data/.openclaw/secrets/.env. Workspace at /data/clawd. The update script knows this — do not override paths.

RULE 4 — Watch the update output. Send me a progress note when the download finishes and when the skill copy loop completes.

RULE 5 — Plain English headlines only.

RULE 6 — When the update completes, an UPDATE PENDING flag is written at the top of /data/clawd/AGENTS.md. The flag lists NEW skills (didn't exist before) and UPDATED skills (refreshed in place). Read the flag completely.

RULE 7 — For each NEW skill in the flag:
  (a) Read ALL files in the skill folder: SKILL.md, INSTALL.md, INSTRUCTIONS.md, EXAMPLES.md, CORE_UPDATES.md, QC.md, and any references/*.md
  (b) Check prerequisites. Search ALL standard credential locations BEFORE asking me: /data/.openclaw/secrets/.env, openclaw.json env.vars, printenv, /data/.env
  (c) Execute the activation steps in INSTALL.md (reading is not executing — actually run them)
  (d) Apply CORE_UPDATES.md surgically — only labeled sections, no full file dumps
  (e) Run QC checks; reach 8/10 or higher before moving on
  (f) If the skill has a qc-*.sh script (e.g. Skill 36's qc-ghl-mcp-setup.sh), run it and confirm exit 0

RULE 8 — For UPDATED skills (refreshed in place): no re-activation needed. The file replacement is sufficient unless I explicitly ask.

RULE 9 — Sub-agent limits: max 50 concurrent, queue 10, spawn depth 4.

RULE 10 — Skills 22 and 23 if newly installed: MAIN ORCHESTRATOR ONLY.

RULE 11 — Skill 36 — if newly installed OR if its systemd unit was refreshed, run qc-ghl-mcp-setup.sh and confirm exit 0.

RULE 12 — STOP and ask me before:
  (a) Credential not in /data/.openclaw/secrets/.env or openclaw.json
  (b) Skill asks for owner input
  (c) QC failure without clear fix
  (d) Any external action (GitHub push, message to anyone but me, etc.)
  (e) Skipping a step

RULE 13 — NEVER use --break-system-packages, --force, --no-verify, --no-gpg-sign, model substitution, or invented steps.

RULE 14 — Watchdog: 10 minutes stalled = alert me.

RULE 15 — Time budget: 20 minutes for a typical VPS update. Progress note if over.

RULE 16 — Communication: plain English, no acronyms unless explained, headlines first, I'm over 60.

RULE 17 — When complete:
  (a) Remove UPDATE PENDING section from /data/clawd/AGENTS.md
  (b) Append to /data/clawd/MEMORY.md under "## System Updates" with date + version + list of new skills
  (c) Final summary: "VPS update complete. Newly installed: [list or 'none']. Updated in place: [count]. Anything needing my attention: [list or 'nothing']."

RULE 18 — Confirm with "Got it — starting your VPS update" + 2–3 sentence summary. Then start.
<<<
```

### What you'll see, success, and troubleshooting

Same pattern as Block 6, but the bot is the VPS bot. Reference Block 6 for the troubleshooting walkthrough.

---

## Shared troubleshooting

These apply to all 8 blocks above.

### "I didn't get a Telegram notification at the end"

Every Terminal-based install (Blocks 1, 3, 5, 7) prints a backup ASCII box at the end of the run with paste-ready instructions for your agent. Look for the box bordered by `╔` and `╠` characters. Copy the instruction between `>>>` and `<<<` from inside the box and paste it to your agent in any chat you use.

If you used a Telegram block (Blocks 2, 4, 6, 8), your agent already has the instructions baked into the contract you sent.

### "My agent didn't see the UPDATE PENDING flag in AGENTS.md"

The agent's session likely loaded BEFORE the flag was written. Try one of:

1. **Telegram users:** type `/restart` to your bot (reloads the agent's context)
2. **Terminal users:** the install/update script triggers a gateway restart automatically. Wait 30 seconds, then chat with your agent again.
3. **If neither works:** ask your agent: *"Please re-read my AGENTS.md file right now and process anything new at the top."*

### "It says `openclaw: command not found`"

Your OpenClaw CLI isn't installed yet or isn't on your PATH. If this is a fresh install (Blocks 1–4), the install script will install it for you as part of the run. If this is an update (Blocks 5–8) and the CLI is missing, your previous install may be broken — use Blocks 1–4 to do a fresh install instead.

### "Something else went wrong"

Send your agent (in Telegram or whatever you use):

> *"The install/update just produced this error: [paste the last 10–20 lines of red or yellow text from Terminal]. Read it, tell me in plain English what happened, and propose the next step. Do not just retry without diagnosing first."*

### "How do I tell if I'm using the right block?"

If you're unsure, send your agent:

> *"Which one is my machine — a Mac or a VPS? And is my OpenClaw installed already, or do I need a fresh install?"*

Your agent can answer both questions instantly.

---

## Privacy and security

- Your Private Integration Tokens, API keys, and passwords are stored at `~/.openclaw/secrets/.env` (Mac) or `/data/.openclaw/secrets/.env` (VPS) with file permissions `600` — only you can read them.
- Install scripts never send credentials anywhere except the services they're for (GHL, Google, Stripe, etc.).
- Telegram notifications use your own bot — no third party sees them.
- Install logs go to `/tmp/openclaw-install-*.log` and never contain your secrets.

---

## Getting help

If you're stuck and your agent can't diagnose, message Trevor or his team and include:

1. Which block above you were using (1 through 8)
2. The last 5–10 lines of output you saw in Terminal or your last 2–3 Telegram messages
3. What you expected to happen vs what actually happened

That's it.
