# How to Trigger OpenClaw Onboarding

Welcome. This document shows you exactly how to start (or restart) your OpenClaw onboarding install. There is more than one way to do it because every client uses their computer differently. Pick the version below that matches your setup.

---

## Which version should I use?

Answer these two questions, then jump to the matching section:

**Question 1 — Which kind of machine are you installing on?**
- A **Mac Mini, Mac laptop, or Mac desktop** → your install is the "Mac" version (Section A or B below)
- A **VPS, Hostinger box, or rented cloud server** → your install is the "VPS" version (Section C or D below)

**Question 2 — Are you comfortable opening Terminal and pasting a command?**
- **Yes, I can open Terminal and paste a command** → use Section A (Mac) or Section C (VPS)
- **No, I prefer to just talk to my agent on Telegram and let the agent do the work** → use Section B (Mac) or Section D (VPS). Note: this requires that your OpenClaw and Telegram are already set up so you have an agent to talk to.

**Special case — already onboarded with us in the past?**
You're not doing a fresh install. You just need to pull the latest updates. Go to **Section E — Existing Client Update**.

---

## Section A — Mac, using Terminal

**For:** clients on a Mac who are comfortable opening Terminal.
**Time:** about 5–15 minutes depending on your internet speed.
**What it does:** downloads every skill, sets up your OpenClaw, installs everything in waves with quality control, then tells your agent what to do next.

### Step 1: Open Terminal on your Mac

1. Press **Command (⌘) + Space** at the same time to open Spotlight Search
2. Type the word **Terminal**
3. Press **Return / Enter**
4. A black or white window will open with text. That's Terminal. You're in the right place.

### Step 2: Copy and paste this exact command

Copy the line between the markers, paste it into Terminal, and press **Return / Enter**:

```
curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/install.sh | bash
```

You will see lines of progress scrolling by. Do NOT close Terminal while this is happening. The whole install takes about 5–15 minutes.

### Step 3: When it finishes, look at the bottom of the Terminal window

When the install is done, Terminal will print a big box that says **"BACKUP — IF YOU DID NOT GET A TELEGRAM NOTE"** with instructions inside. That box is your safety net.

Two things will happen at the same time:

1. **Your Telegram should ding** with a message from your OpenClaw bot. It will look something like:
   *"OpenClaw Onboarding install complete. Paste this to your agent: [block of instructions]."*
   If you got that ding, just copy what it tells you to paste, paste it back to your agent on Telegram, and your agent will take over from there.

2. **If your Telegram did NOT ding** (for any reason), look at the box at the bottom of the Terminal window. Copy the instruction between the `>>>` and `<<<` markers, then paste it to your agent in whatever app you normally use to talk to your agent (Telegram, web chat, whatever).

Either way, the agent reads your AGENTS.md file, sees the UPDATE PENDING flag at the top, and walks through the rest of the setup automatically. You do not have to type any more commands.

### Step 4: Confirm the install is fully active

Ask your agent (in Telegram or wherever you talk to it):

> *"Are all my skills activated? Give me a summary."*

You should get back a list of skills with their statuses. If anything failed, the agent will tell you and propose a fix.

---

## Section B — Mac, using Telegram (no Terminal)

**For:** clients on a Mac who prefer to not touch Terminal. Requires that you already have OpenClaw + Telegram set up so you have an agent to message.
**Time:** about 5–15 minutes.
**What it does:** your existing Telegram agent runs the install for you locally on your Mac.

### Step 1: Open your Telegram chat with your OpenClaw agent

Open Telegram. Find your conversation with your OpenClaw bot (the one you normally chat with).

### Step 2: Paste this exact message to your agent

Copy everything between the `>>>` and `<<<` markers below. Paste it as a single message to your agent. Send it.

```
>>>
I need you to run the OpenClaw onboarding install on my Mac and follow these rules exactly.

CONTRACT (do not deviate):
1. Open my Terminal yourself using your shell-exec capability. Run this command exactly as written, do not change a single character:
   curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/install.sh | bash

2. Watch the install output. Tell me progress every 5 skills (or every 2 minutes, whichever comes first). Use plain English, not jargon.

3. Stop telling me about technical details I don't need. I want headlines: "5 of 35 skills installed," "Phase A complete," "QC running." Not raw error logs.

4. When the install finishes, my Mac will write an UPDATE PENDING flag at the top of my AGENTS.md file. Read that flag carefully. Follow the 5-Phase Processing Order written in it EXACTLY. Do not improvise. Do not skip phases.

5. Process skills in waves the way the flag says: Phase A = parallel install in 5 waves, Phase B = activate foundation (Skill 31 memory + Skill 22 persona), Phase C = interactive (Skill 23 + Skill 35), Phase D = ready/waiting, Phase E = QC + report.

6. Spin up sub-agents within the configured limits: max 50 concurrent, queue 10, spawn depth 4. Do not exceed these.

7. Run the QC checks for every skill. If any skill scores below 8 out of 10 on QC, do not silently move on — tell me which skill failed and what the failure was.

8. For Skill 36 (GHL MCP Setup): you MUST run its bundled qc-ghl-setup.sh script after install. Do not declare GHL set up until that script exits with status 0.

9. If you hit ANY of these situations, stop immediately and ask me before doing anything:
   - A skill needs my API key, password, or other credential you cannot find in my .env files
   - A skill says it needs my intervention or input
   - A QC check fails and you don't have a clear fix
   - You're about to push to GitHub or send a message to someone other than me
   - You think a step is unnecessary and want to skip it (don't — ask first)

10. Do NOT take shortcuts:
    - Never use --break-system-packages
    - Never use --force
    - Never use --no-verify
    - Never substitute a model name for one you "think is better"
    - Never invent a step that's not in the install script or the UPDATE PENDING flag

11. When the entire install AND activation are complete:
    - Remove the UPDATE PENDING section from my AGENTS.md
    - Add a one-line entry to my MEMORY.md under "## System Updates" with today's date and the version installed
    - Send me a final summary: "Install complete. [N] skills active. Memory: 8 layers verified. Personas: [M] available. Anything that needs my attention: [list]."

12. Total time budget: aim for under 30 minutes from start to final summary. If you're over 30 minutes, send me a progress note explaining where you're stuck.

Match my communication preferences: I am over 60, I want plain English, no acronyms unless you explain them, headlines first, details only if I ask. Confirm you understand by replying with "Got it — starting your install" and a brief plain-English summary of what you're about to do. Then start.
<<<
```

### Step 3: Wait and watch

Your agent will reply confirming it understands, then start running the install on your Mac. You'll get progress updates every few minutes. The whole thing usually takes 15–30 minutes for a fresh install.

When done, your agent will send you a summary message. Read it. If anything needs your attention, the agent will list it clearly.

### Step 4: If something goes wrong

If your agent stops responding or sends an error you don't understand, send this:

> *"Something seems wrong. Tell me in plain English what just happened, what the error is, and what you need from me to keep going. Do not move on without asking."*

---

## Section C — VPS, using Terminal (SSH)

**For:** clients who manage their own VPS / Hostinger box and can SSH into it.
**Time:** about 10–20 minutes.
**What it does:** same as Section A, but uses the VPS-specific repo so paths land in `/data/` (the persistent volume on a VPS) instead of `~/Downloads/`.

### Step 1: SSH into your VPS

In Terminal on your Mac (or Windows Terminal / PowerShell on Windows), connect to your VPS:

```
ssh root@YOUR.VPS.IP.ADDRESS
```

Replace `YOUR.VPS.IP.ADDRESS` with the actual IP your hosting provider gave you. Enter your password when asked.

### Step 2: Paste the VPS install command

Once you're logged in to the VPS, paste this command and press **Return**:

```
curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding-vps/main/install.sh | bash
```

You'll see progress scrolling. Don't close the SSH session.

### Step 3: When it finishes

Same as Section A:

1. **Your Telegram should ding** with a paste-ready message for your agent
2. **If it didn't,** the Terminal will show a big box labeled **"BACKUP — IF YOU DID NOT GET A TELEGRAM NOTE"** with instructions to copy and paste to your agent

Follow whichever path your install actually gave you.

### Step 4: Confirm in Telegram

Ask your agent the same question:

> *"Are all my skills activated? Give me a summary."*

---

## Section D — VPS, using Telegram (no SSH)

**For:** clients who have a VPS but don't want to SSH in. Your VPS's OpenClaw needs to already be running so Telegram can reach it.
**Time:** about 15–30 minutes.
**What it does:** the OpenClaw agent running ON your VPS receives your Telegram message and runs the install locally on the VPS itself.

### Step 1: Open Telegram

Open Telegram. Find your conversation with your VPS's OpenClaw agent. (If you have BOTH a Mac and a VPS, make sure you're sending this to the VPS bot, not the Mac bot.)

### Step 2: Paste this exact message

Copy everything between `>>>` and `<<<`. Paste it as one message. Send.

```
>>>
I need you to run the OpenClaw onboarding install on this VPS and follow these rules exactly.

CONTRACT (do not deviate):
1. Run this command on the VPS using your shell-exec capability. Run it exactly as written, do not change a single character:
   curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding-vps/main/install.sh | bash

2. The VPS install puts skills under /data/ — the persistent volume. Mac paths like ~/Downloads do not exist on a VPS. The script knows this. Do not try to override paths.

3. Watch the install output. Tell me progress every 5 skills (or every 2 minutes, whichever comes first). Plain English headlines only.

4. When the install finishes, an UPDATE PENDING flag will be written to the top of my AGENTS.md file (the workspace AGENTS.md on the VPS, not the Mac one). Read that flag carefully. Follow the 5-Phase Processing Order EXACTLY. No improvising.

5. Process skills in the waves the flag describes: Phase A parallel install, Phase B foundation, Phase C interactive, Phase D ready/waiting, Phase E QC.

6. Sub-agent limits: max 50 concurrent, queue 10, spawn depth 4. Do not exceed.

7. QC every skill. Anything scoring below 8/10 — stop, tell me what failed, propose a fix.

8. Skill 36 (GHL MCP) must run its bundled qc-ghl-setup.sh and exit 0 before you call GHL done.

9. Stop and ask me if:
   - A skill needs a credential you can't find in /data/.openclaw/secrets/.env or openclaw.json env.vars
   - A skill asks for owner input
   - A QC check fails without a clear fix
   - You're about to push to GitHub or message someone other than me
   - You think a step is unnecessary

10. Forbidden shortcuts:
    - No --break-system-packages
    - No --force
    - No --no-verify
    - No model substitutions

11. When complete:
    - Remove the UPDATE PENDING section from AGENTS.md
    - Append to MEMORY.md under "## System Updates": today's date + version
    - Final summary: skills active, memory layers verified, personas available, anything pending my attention

12. Budget: 30 minutes. If you're over, send a progress note.

Confirm with "Got it — starting your VPS install" and a brief plain-English summary, then start.
<<<
```

### Step 3: Watch and wait

Your VPS agent will run the install. You'll get Telegram updates as it progresses. Whole thing usually 20–40 minutes for a fresh VPS install.

### Step 4: Confirm

> *"Are all my skills activated on the VPS? Give me a summary."*

---

## Section E — Existing Client Update (you've onboarded with us before)

**For:** anyone who has ANY previous version of OpenClaw onboarding installed — doesn't matter if it was last week, last year, or two years ago. The update script checks what skills you have and intelligently updates only what changed.
**Time:** usually 3–10 minutes.
**What it does:** pulls the latest skills from GitHub, replaces older versions with newer ones, leaves unchanged skills alone, installs any brand-new skills you didn't have before.

The update is **non-destructive**. Your existing settings, credentials, and core .md files are kept. Only the skill folders themselves get refreshed.

### Mac update via Terminal

```
curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/update-skills.sh | bash
```

### VPS update via Terminal

```
curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding-vps/main/update-skills.sh | bash
```

### Either platform via Telegram

Paste this to your agent:

```
>>>
Please run the OpenClaw skills updater on this machine. Use the curl command from the README for whichever repo matches my system (openclaw-onboarding for Mac, openclaw-onboarding-vps for VPS — you should already know which I'm on).

After the script finishes, read the UPDATE PENDING flag the script wrote at the top of my AGENTS.md. For any NEW skills the script installed (the flag will list them by name), follow each skill's full activation:
- Read SKILL.md, INSTALL.md, CORE_UPDATES.md, QC.md
- Check prerequisites + look for credentials in my .env files before asking me
- Execute the activation steps in INSTALL.md
- Apply CORE_UPDATES.md surgically (no full file dumps)
- Run the QC checks; reach a passing score before moving on
- For Skill 36 specifically: run qc-ghl-setup.sh and confirm exit 0

For skills that were just UPDATED (not new), assume they activated cleanly via the file replacement. No re-activation needed unless I ask.

Send me a summary at the end with what was newly installed, what was updated, and anything needing my attention.
<<<
```

After the update, ask your agent:

> *"What's new in this update? Anything I should know about?"*

---

## Troubleshooting

### "I didn't get a Telegram notification after the install"

The install script will always print a backup instruction block to your Terminal at the end. Look for the box with `╔` and `╠` border characters. Copy the lines between `>>>` and `<<<` from inside that box and paste them to your agent in any chat you use.

If you used the Telegram method (Section B or D) instead of Terminal, your agent already has the instructions baked into the contract you sent.

### "My agent didn't see the UPDATE PENDING flag in AGENTS.md"

This usually means your agent's session loaded BEFORE the install finished writing the flag. Try one of these:

1. **Telegram method:** type `/restart` to your bot — that reloads the agent's context
2. **Terminal method:** the install script triggers a gateway restart automatically. Wait 30 seconds, then chat with your agent again — it will reload the file.
3. **If neither works:** ask your agent: *"Please re-read my AGENTS.md file right now and process anything new at the top."*

### "It says 'openclaw command not found'"

Your OpenClaw CLI isn't installed yet, or isn't on your PATH. If this is a brand-new install, that's normal — the install script will install it for you. If it's not a fresh install, you may need to reinstall OpenClaw before running the updater.

### "Something else went wrong"

Send your agent this message:

> *"The install just produced this error: [paste the last 10–20 lines of red text from Terminal]. Read it, tell me in plain English what happened, and propose the next step. Do NOT just try the install again — diagnose first."*

---

## What happens after onboarding finishes

After everything is installed and activated, your agent has 36 skills available. Some highlights:

- **Skill 05 + 36 (GHL):** Your agent can manage your GoHighLevel / Convert and Flow account — search contacts, send messages, manage products, create invoices, schedule recurring billing, and more. Skill 36 specifically adds the 5-tier access chain so your agent always uses the most efficient path.
- **Skill 22 + 23 (Personas + Workforce):** Your agent picks the right persona for each task based on a 5-layer alignment check.
- **Skill 31 (Memory):** 8-layer memory system so your agent remembers things across sessions.
- **Skill 35 (Social Media Planner):** Weekly content production across 8 platforms.

Each skill has its own SKILL.md file describing what it does. If you want to know more about any one of them, ask your agent:

> *"What does Skill [number] do? Plain English please."*

---

## Privacy and security

- Your Private Integration Tokens, API keys, and passwords are stored in `~/.openclaw/secrets/.env` on Mac or `/data/.openclaw/secrets/.env` on VPS. These files are set to permissions `600` — only you can read them.
- The install script never sends credentials anywhere except to the services they're for (GHL, Google, Stripe, etc.).
- The Telegram notifications use your own bot — no third party sees them.
- Everything is logged to `/tmp/openclaw-install-*.log` for troubleshooting. Logs do NOT contain your secrets.

---

## Getting help

If you're stuck, tell your agent in plain English what's happening and what you've tried. Agents are good at diagnosing. If your agent is also stuck, message Trevor or his team and include:

1. Which section above you were using (A, B, C, D, or E)
2. The last 5–10 lines of output you saw
3. What you expected to happen vs what actually happened

That's it. You're set up.
