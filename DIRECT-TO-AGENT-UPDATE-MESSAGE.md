# Direct-to-Agent Update Message Template
# Version 1.0 | March 22, 2026
# 
# Copy-paste this to any client's agent on Telegram via Skill 15 (BlackCEO Management).
# Works for clients on ANY version (v2, v3, v4, v5).

---

There is a major update available for your BlackCEO system. The latest version is v6.0.1. Follow these instructions carefully.

**FIRST: Check your current version.** Look at the "version" file in your onboarding installation. This tells you how far behind you are.

**SECOND: Go to https://github.com/trevorotts1/openclaw-onboarding and download the full repo.**

**THIRD: Open UPDATE-PLAYBOOK.md and follow every step exactly. Do not skip steps.**

The playbook will walk you through: backup first, read the changelog, check credentials, check dependencies, risk assessment, apply updates, handle core file changes. Follow it step by step.

---

## IMPORTANT: QMD Migration Check

Before doing ANYTHING else, check if you are running the old QMD (Qdrant) retrieval system:
- Is there a ~/.cache/qmd folder?
- Does your openclaw.json mention "qmd" as a memory backend?
- Does the command "qmd" exist on your system?

If YES to any of these: you MUST migrate to Gemini Embedding 2 FIRST before this update. Open MIGRATION.md in the downloaded repo and follow every step. Do NOT proceed with the update until migration is complete. This is HIGH RISK. If you skip this, things will break.

If NO to all of these: you are already on Gemini Embedding 2 or never had QMD. Proceed with the update.

---

## What Changed (Summary by Version)

Read the full CHANGELOG.md for details. Here is a summary so you know what to expect:

**If you are on v2.x:**
Everything below applies to you. This is the biggest jump. Pay close attention to the department restructure and QMD migration.

**If you are on v3.x:**
- Department restructure (v4): Creative split into creative (written only), graphics, video, audio
- Voice Call Plugin removed from onboarding (now installed separately via npm)
- Fish Audio renumbered to Skill 30

**If you are on v4.x:**
- Skill 14 (Google Workspace) completely rewritten
- Skill 15 (Team Management) fixed
- Skill 31 (5-layer memory) is new
- Legacy retrieval replaced with Gemini Embedding 2
- Onboarding watchdog added

**If you are on v5.x:**
- Skill 22 updated (40 books, model fallback chain)
- Skill 23 rewritten to v2.3 (dynamic departments, plain English, Skills 33/34 merged in)
- install.sh fixes (workspace paths, sub-agent config, model allow list)

**All versions get these new additions:**
- Skill 30: Fish Audio API Reference
- Skill 31: Upgraded Memory System (5-layer architecture)
- Skill 32: BlackCEO Command Center (live dashboard, Kanban, department agents, KPI tracking)
- Sub-agent limits: maxConcurrent 20, maxChildrenPerAgent 20, maxSpawnDepth 4
- Model allow list: 10 models (Kimi K2.5, MiMo V2 Pro, MiMo V2 Omni, MiniMax M2.7, Gemini 3.1 Flash Lite, Gemini 3 Flash, GPT 5.4, Perplexity Sonar Pro Search, Perplexity Sonar, Kimi K2.5 via OpenRouter)

---

## Skill 32 (Command Center) - Special Rules

The Command Center ONLY installs after Skill 23 (AI Workforce Blueprint) interview is complete. The agent checks for department folders to verify this.

**If Skill 23 interview is NOT complete:**
Do NOT install Skill 32. Instead, add this to your HEARTBEAT.md:

"Twice daily (9 AM and 2 PM), remind your client to complete the AI Workforce questions:
- Morning: Hey, just checking in. We still have some questions to finish for your AI Workforce setup. Want to knock those out today? It only takes about 15 minutes and once it is done, your Command Center goes live.
- Afternoon: Quick reminder - your AI Workforce questions are still waiting. Once we finish those, I can build out your full Command Center dashboard. Ready to continue?"

When all questions are answered:
- Remove the reminder from HEARTBEAT.md
- Automatically proceed to install Skill 32
- Clone the Command Center from https://github.com/trevorotts1/blackceo-command-center
- Use the department folders created by Skill 23 to build the dashboard
- Report back when the Command Center is live

**If Skill 23 interview IS complete:**
Proceed directly to Skill 32 installation.

---

## After the Update

Report back with:
1. What version you were on before
2. What was updated (list each skill)
3. What was skipped and why
4. What credentials are missing (blocked skills)
5. Whether the client needs to finish workforce questions
6. Whether QMD migration was needed and its status
7. Whether a gateway restart is recommended
