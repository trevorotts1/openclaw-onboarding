# Changelog

All notable changes to the OpenClaw Onboarding package are documented here.

---

## [v6.1.4] - March 29, 2026

### Interview Persistence Protocol + Update Flow Fixes + Terminology

#### Added
- **TERMINOLOGY.md**: New repo-root file defining GHL/Convert and Flow/GoHighLevel naming rules and Private Integration Token (PIT) terminology. Required reading for all agents.
- **Skill 23 SKILL.md**: Full Interview Persistence Protocol replacing one-line flush note. 4-step mandatory flush after every question (answer to disk first, handoff update, MEMORY.md progress, then next question). Boot-time resume logic with 4-tier fallback. Edge cases: skip/circle-back, answer corrections, stale handoffs (90+ days), crash recovery, resume triggers.
- **Skill 23 CORE_UPDATES.md**: Interview Resume Protocol section for AGENTS.md — boot-time check for incomplete interviews.

#### Changed
- **scripts/update-skills.sh**: v6.1.3. Now sends Telegram notification directly to paired user using botToken and allowFrom from openclaw.json. If Telegram fails, prints clear fallback box in Terminal with exact agent instruction. AGENTS.md flag still written as backup layer.
- **install.sh**: Auto-cleanup of misplaced config keys. If `subagents` or `allow` appear under top-level `models` (where they do not belong), they are deleted automatically. Prevents config validation errors on startup.
- **UPDATE-PLAYBOOK.md**: v6.1.3. Added explicit JSON paths for subagent config (`agents.defaults.subagents`) and model allow list (`agents.defaults.models`). Added TERMINOLOGY.md reference. Warns agents not to put subagents under `models`.
- **Start Here.md**: Added TERMINOLOGY.md reference.
- **All script headers**: Synced to 6.1.3.

#### Removed
- **Perplexity sonar models** from model allow list (install.sh, deprecated-models.json, UPDATE-PLAYBOOK.md). `openrouter/perplexity/sonar-pro-search` and `openrouter/perplexity/sonar` are web search tools, not models. Allow list is now 8 models.

#### Fixed
- Script version headers were out of sync with repo version file. All 3 scripts now match `version` file. New rule: every push must bump version + headers in same commit.
- UPDATE-PLAYBOOK.md told agents to add subagent config but did not specify the JSON path, causing agents to put keys in the wrong place (`models` instead of `agents.defaults`).

---

## [v6.1.0] - March 27, 2026 (Late Evening)

### Skill 23 Persistence Hardening + Version-Proof Update System + Notification Overhaul

#### Added
- **scripts/setup-weekly-update.sh**: v4.0 rewritten. Installs a Sunday 3:00 AM cron job that uses the GitHub-hosted curl command to stage updates. Version-proof: always pulls the latest updater from GitHub, never a stale local file.
- **Skill 23 templates/company-discovery/workforce-interview-answers.md**: Default interview answer template for guaranteed persistence.
- **Skill 23 templates/company-discovery/interview-handoff.md**: Resume state template for long-running interviews.

#### Changed
- **Skill 23 build-workforce.py**: Persistence hardened. `find_master_files_folder()` now guarantees a valid path and never returns None. If the normal path doesn't exist, it falls back to `~/clawd/data/company-discovery/` with explicit warning. `log_answer()` and `create_handoff()` now print success/error to stderr. No code path where an answer is silently dropped.
- **UPDATE-PLAYBOOK.md**: Overhauled to v2.0. Added STEP 16: Client Notification Protocol with 3-channel fallback (Telegram → email → SMS). Added 4 message templates (Update Found, Update Applied, Update Blocked, SMS Fallback). Added plain-English guidance on what "staged" means. Added fallback channel protocol with email subject lines and SMS templates. Method 1 updated to use GitHub-hosted curl bootstrap command.
- **scripts/update-skills.sh**: v4.0 rewritten. Now generates a client-friendly notification message at /tmp/oc-update-notification.md instead of just saying "update staged." The notification explains what was found, what it means, what will happen if they say yes, and what they need to do. AGENTS.md flag now points agent to the notification file.
- **Version file**: v6.0.7 -> v6.1.0

## [v6.0.7] - March 27, 2026

### Persona Matching Protocol + Skill 32 Token-in-Webhook Architecture

#### Added
- **persona-matching-protocol.md** (Skill 23): New reference document defining the 5-layer persona alignment check (Company Mission, Owner Values, Company Goals/KPIs, Department Goals/KPIs, Task Fit). Layers 1-2 run once at setup to create a pre-qualified pool. Layers 3-5 run fresh for every task. Personas are matched per-task at runtime, not statically assigned per department.
- **persona-categories.json** (Skill 22): 40 personas tagged with 12 domain categories (marketing, sales, leadership, finance, operations, communication, copywriting, mindset, productivity-systems, coaching, strategy-innovation, personal-development) and 6 perspective tags (african-american-experience, womens-challenges, mens-challenges, family-relationships, faith-spirituality, love-romantic-relationships). Category-filtered matching enables efficient search across large persona libraries.

#### Changed
- **Skill 23 INSTALL.md**: Persona alignment section rewritten. governing-personas.md is now a REFERENCE GUIDE in each role folder, not a static department assignment. Added 5-layer alignment description and runtime matching instructions.
- **Skill 23 SKILL.md**: Corrected persona-matching-protocol.md reference from "3-layer" to "5-layer" (matches the protocol document and all other references).
- **Skill 32 INSTALL.md Phase 6b**: Architecture rewritten. Tunnel token now returned directly in the webhook HTTP response (JSON: tunnelToken, subdomain, tunnelId). Agent captures token programmatically, saves to ~/.openclaw/.env, starts PM2, verifies URL. Trevor still receives a backup Telegram notification with the same token. No more manual token forwarding step.
- **Skill 32 INSTALL.md Phase 6b**: cloudflared installation now built into the process. Step 6b.2 installs cloudflared via brew (Mac) or curl (Linux) before the webhook call.
- **32-command-center-setup/scripts/create-tunnel.sh**: Complete rewrite. Reduced from 147 lines to 59. Removed Cloudflare API calls, credential file management, launchctl plist generation, local tunnel config. Added auto cloudflared install, webhook POST with token capture, PM2 process management, clean verification.

#### Removed
- **Skill 32**: Manual "Wait for Trevor's Token" step (6b.3). Token now comes in webhook response.
- **Skill 32**: Manual echo CLOUDFLARE_TUNNEL_TOKEN step. Replaced with automated grep/mv in script.
- **Skill 32 create-tunnel.sh**: All Cloudflare API code (account ID, bearer token, tunnel creation via API, credential file writing, config-command-center.yml generation, launchctl plist creation). Replaced by single webhook call.

## [v6.0.2] - March 25, 2026

### Update System Fix

#### Fixed
- **scripts/update-skills.sh**: Complete rewrite. Now stages updates to /tmp and creates .update-pending flag file. No longer attempts to apply changes directly — agent follows UPDATE-PLAYBOOK.md.
- **Version comparison bug**: Eliminated. Script now reads version files directly instead of parsing changelog headers.
- **scripts/deprecated-models.json**: New file. Single source of truth for required models, deprecated model replacements, and sub-agent configuration.
- **UPDATE-PLAYBOOK.md**: Step 4d now references deprecated-models.json. Step 4e added for sub-agent config check (maxSpawnDepth: 4, maxChildrenPerAgent: 10, maxConcurrent: 20).

#### Added
- MiMo V2 Pro (openrouter/xiaomi/mimo-v2-pro) to required model list
- MiMo V2 Omni (openrouter/xiaomi/mimo-v2-omni) to required model list
- Sub-agent config validation (4, 10, 20)
- .update-pending flag file mechanism (replaces AGENTS.md bloat)

#### Changed
- update-skills.sh no longer applies changes — it stages the update and the agent follows UPDATE-PLAYBOOK.md
- Deprecated minimax-m2.5 → minimax-m2.7 tracked in deprecated-models.json

## [v6.0.1] - March 22, 2026

### Bug Fixes - Install Sequence, Skill 15, Skill 22, Gemini Engine

#### Fixed
- **install.sh**: Gemini Engine script no longer runs indexer on empty directories. Step 3b now only copies script + installs python package. Indexing deferred to after Skill 22 adds books.
- **install.sh**: Step 3b API key search now checks ~/.openclaw/.env first (OpenClaw standard) instead of hardcoded ~/clawd/secrets/.env (Trevor-specific path).
- **install.sh**: Step 3c now also sets model allow list (9 models) alongside sub-agent concurrency settings.
- **install.sh**: Step 4 now creates ~/Downloads/openclaw-master-files/ folder (coaching-personas/personas + project-prds).
- **Start Here.md**: Added Step 2.5 (sub-agent concurrency + model allow list) between backup protocol and Step 3.
- **Start Here.md**: Removed stale Skill 13 dependency. Skill 14 now runs independently.
- **Start Here.md**: Removed Skill 13 from Agent C assignment and Wave 2 install loop.
- **Skill 15**: Hard-coded team Telegram IDs (Trevor: 5252140759, LeAnne: 6663821679, E.R. Spaulding: 6771245262) back into INSTALL.md and TEAM_CONFIG.md. Previous sub-agent replaced them with placeholders.
- **Skill 15**: Removed interactive Step 0 intake questions. Step 0 now loads pre-configured data from TEAM_CONFIG.md.
- **Skill 15**: Step 2 now verifies existing sub-agent settings instead of overwriting them.
- **Skill 22**: Added model fallback chain. Primary: Kimi K2.5 via OpenRouter, then MiMo V2 Pro, then Kimi via Moonshot, then GPT Codex, then Gemini/Sonnet.
- **Skill 22**: INSTALL.md Step 4 now checks which models are available instead of requiring Moonshot API key.
- **gemini-indexer.py**: Added --status, --init, --dry-run flags. Skips missing collections gracefully. Supports multiple collections.

## [v6.0.0] - March 22, 2026

### AI Workforce Blueprint v2.3 + Skills 33/34 Merge

#### Added
- **Skill 23**: Workspace creation with core file inheritance (SOUL.md unique, TOOLS.md/AGENTS.md/USER.md inherited from CEO workspace)
- **Skill 23**: Specialist determination function (permanent vs on-call classification)
- **Skill 23**: Persona alignment via 5-layer selection (Mission, Values, KPIs, Dept Goals, Task Fit)
- **Skill 23**: ORG-CHART.md generation with model assignments
- **Skill 23**: Command Center departments.json generation
- **Skill 23**: Config safety protocol (backup before openclaw.json edits)
- **Skill 23**: interview-handoff.md auto-creation and flush after every answer
- **Skill 23**: Model check (high reasoning required) at install start
- **Skill 23**: Hesitation detection with industry research fallback (Perplexity sonar-pro-search)
- **Skill 23**: Client stop/resume with interview-handoff.md save
- **Skill 23**: 10 industry examples in INSTRUCTIONS.md
- **Skill 22**: persona-categories.json (40 personas, 12 domain + 6 perspective tags)
- **Skill 22**: Category metadata per persona (domain_tags, business_stage, ideal_user)

#### Changed
- **Skill 23**: All files rewritten to v2.3 (Start Here, SKILL.md, INSTRUCTIONS.md, build-workforce.py, INSTALL.md, CORE_UPDATES.md)
- **Skill 23**: Options presented as A/B/C with plain English descriptions (no "permanent agent"/"sub-agent")
- **Skill 23**: Interview questions are dynamic (3-7 per department, not fixed 7 with jargon)
- **Skill 23**: Department count is dynamic (any number, not hardcoded 17)
- **Skill 23**: Forbidden jargon removed from all files (handoff, tech stack, SOP, KPI, etc.)

#### Archived
- **Skill 33**: Department Heads - merged into Skill 23 (create_department_workspace, generate_soul_md, add_agent_to_config)
- **Skill 34**: Intelligent Staffing - merged into Skill 23 (determine_specialists, persona alignment)

---

## [v5.5.2] - March 21, 2026

### Skill 3 Fix + Calibre Auto-Install

#### Fixed
- **Skill 3**: Case-insensitive Gemini detection for Mem0 provider
- **Skill 3**: Onboarding path detection for Intel vs Apple Silicon Macs
- **Skill 3**: Calibre auto-installation (brew install --cask calibre)
- **Skill 3**: Completion confirmation before proceeding

---

## [v5.5.1] - March 20, 2026

### QC Agent Roles + Cloudflare Manual Setup

#### Added
- **Skill 23**: QC-ROLES-MASTER.md - 34KB master reference for QC agents
- **Skill 23**: QC agent roles added to all 17 department suggested-roles files
- **Skill 32**: Phase 8 - Manual Cloudflare Tunnel Setup (9 subsections)

#### Changed
- **Skill 31**: Mem0 config switched from OpenAI to Gemini (LLM + embedder)
- **Skill 32**: Phase 6b clarified as agent-automated path

---

## [v5.5.0] - March 20, 2026

### Command Center v1.4.0 + Multi-Company

#### Added
- **Skill 34: Intelligent Workspace Staffing** - Auto-hire/fire based on workload
- Multi-company schema support in Command Center
- Per-department memory architecture
- 17 permanent department head agents (54 total agents)

#### Changed
- **Skill 32**: v1.4.0 with KPI forms, effectiveness tracking, execution queue
- **Skill 32**: Sparklines, model pills, benchmarks

---

## [v5.4.0] - March 19, 2026

### Command Center Setup

#### Added
- **Skill 32: Command Center Setup** - Activates AI workforce as live Command Center
- Persistent department agents with Telegram topics
- Visual Kanban dashboard at localhost:3000
- Cloudflare Tunnel auto-setup (Phase 6b)

#### Changed
- Unique hostname pattern: `[company-slug]-[shortid]`
- 5-layer memory verification requirement

---

## [v5.3.0] - March 19, 2026

### Department Heads

#### Added
- **Skill 33: Department Heads** - 17 department head agents with full SOPs
- Per-department workspace architecture
- AGENTS.md, MEMORY.md, TOOLS.md templates for each dept
- agents.list configuration for department orchestration

---

## [v5.2.0] - March 19, 2026

### Command Center v1.3.0

#### Added
- KPI submission forms
- Effectiveness tracking (agent task completion rates)
- Execution queue system
- Model pills and sparklines

---

## [v5.1.0] - March 19, 2026

### Command Center Setup (Initial)

#### Added
- **Skill 32: Command Center Setup** - Initial release
- Kanban board interface
- Department agent spawning
- Telegram topic integration

---

## [v5.0.0] - March 19, 2026

### Major Release: Memory System Upgrade, Google Workspace CLI, Migration Fixes

#### New Skills
- **Skill 31: Upgraded Memory System** - 5-layer memory architecture (markdown files, improved flush, session indexing, Gemini Embedding 2 search, Mem0 auto-capture)

#### Skill Rewrites
- **Skill 14: Google Workspace Integration** - Complete rewrite. Replaced google-api.js and gog with Google Workspace CLI (gws). Single tool for both Gmail and Workspace. 81 scopes preserved.

#### Bug Fixes
- **Skill 23: AI Workforce Blueprint** - Fixed: agent was skipping the 3 options (A, B, C) and going straight to questions. Added MANDATORY OPTION PRESENTATION rule.
- **Skill 15: BlackCEO Team Management** - Fixed: agent was not writing real Telegram IDs to memory files. Added enforcement block requiring real data, not placeholders.

#### Infrastructure
- **Legacy retrieval fully replaced** with Google Gemini Embedding 2 across all skills and scripts
- **Onboarding watchdog** added to Start Here.md: 10-minute stall detection, never-stop-early, progress reporting every 5 skills
- **Mandatory file reading** protocol: agent must read ALL .md files before installing any skill
- **CONTRIBUTING.md** added: checklist for adding/modifying skills and pushing updates
- **MIGRATION.md** rewritten with correct commands, env vars, and step-by-step instructions

#### Migration Notes
- Existing users on Google Embedding 2: run the migration steps in MIGRATION.md
- The weekly update script (Sundays 2AM) will detect the version change and flag it
- No automatic changes are applied without user approval

#### Total Skills: 31 (Skill 13 archived)

---

## [v4.0.1] - March 16, 2026

### Skill Restructure — Voice Call Plugin Removed, Fish Audio Renumbered

#### Changed
- **Skill 30 (Voice Call Plugin) REMOVED** — The `@openclaw/voice-call` plugin is an official OpenClaw npm package installed via `openclaw plugins install @openclaw/voice-call`. Having it as an onboarding skill caused double-install conflicts on machines where it was already installed. Clients install it manually after onboarding.
- **Skill 31 → Skill 30 (Fish Audio API Reference)** — Renumbered. Now the final skill. Standalone reference doc so the agent knows Fish Audio endpoints, parameters, and call patterns.
- **Old Skill 30 folder archived** as `30-blackceo-voice-call-plugin-ARCHIVED`
- **README and Start Here updated** to reflect new skill numbering

---

## [v4.0.0] - March 16, 2026

### Major Release — Department Restructure, Interdepartmental Communication, Persona Mapping, Surgical Updates

#### Skill Restructure
- **Removed Skill 30** (Voice Call Plugin) — voice-call plugin is installed via OpenClaw npm (`openclaw plugins install @openclaw/voice-call`), not via onboarding. Having it in onboarding caused double-install conflicts.
- **Renamed Skill 31 → Skill 30** — Fish Audio API Reference is now Skill 30 (standalone reference doc)
- **Total skills: 30** (was 31)

#### New Departments
- **graphics-dept** — NEW separate department for all static image/visual work (KIE.ai primary, Nano Banana, OpenAI images, FAL optional)
- **video-dept** — NEW separate department for all video production (KIE.ai video endpoints, ties to Skills 24-28)
- **audio-dept** — NEW separate department for the full audio lifecycle: generate, transcribe, process, deliver (KIE.ai audio/ElevenLabs/Suno endpoints, Fish Audio, Whisper local/cloud)
- **creative-dept restructured** — now ALL written content only ("If it starts as words, it starts here"). Covers copywriting, blog posts, speeches, keynotes, presentation scripts, PowerPoint content, podcast scripts, video scripts. Creative writes — other departments produce.

#### Suggested Roles Per Department
- Added `23-ai-workforce-blueprint/suggested-roles/` folder with 15 department files
- Each file includes: role names, what each role does, core SOPs to build, persona trait suggestions, interdepartmental relationships
- CRM Specialist role documented across multiple departments (sales, marketing, creative, billing, graphics, video, audio) with department-specific SOPs for each

#### Department Folder Organization
- All department folders now live inside `openclaw-master-files/my AI company departments/`
- Company discovery subfolder: `company-discovery/workforce-interview-answers.md` and `persona-alignment-notes.md`
- Daily company logs: `daily-company-logs/YYYY-MM-DD.md` with Gemini Engine integration

#### Interdepartmental Communication System
- Added `universal-sops/cross-dept-request-template.md` — standard format for all cross-dept requests
- Added `universal-sops/interdepartmental-communication-guidelines.md` — CC model (not approval model), direct dept-to-dept communication with master orchestrator awareness
- Added `03-Activity-Log-Template.md` — running daily log format for the master orchestrator
- Pre-built cross-dept workflow SOPs for common routes (Sales→Audio, Marketing→Graphics, Video→Audio, etc.)

#### Persona 4-Layer Alignment Protocol
- Added `universal-sops/persona-re-evaluation-protocol.md`
- 4 layers: Company Alignment → Owner/CEO Alignment → Role/Functional Alignment → Beliefs/Principles Alignment
- Both Layer 3 (what they DO) and Layer 4 (WHY they do it) must pass
- Re-evaluation triggers: company goals change, new dept added, owner priorities shift, role changes, persona underperforming

#### Weekly Auto-Update System (Rebuilt)
- `scripts/update-skills.sh` rebuilt with surgical logic: changelog-first, version comparison, gap analysis, impact rating
- `scripts/check-update-impact.sh` — helper for per-file risk assessment (LOW/MEDIUM/HIGH)
- `scripts/setup-weekly-update.sh` updated to v2.0
- Impact levels: LOW (auto-apply), MEDIUM (recommend + confirm), HIGH (recommend SKIP + show diff)
- NEVER overwrites: core .md files, company dept folders, custom SOPs
- NEVER triggers gateway restart — always instructs client with restart steps

#### AI Workforce Interview Improvements
- Context-first questioning: agent checks existing files before asking any question
- Cross-department learning: answers carry forward, reducing questions as interview progresses
- Running answers document: `company-discovery/workforce-interview-answers.md` (append-only)

#### Daily Company Log System
- Master orchestrator appends log entries in real time (not end of day)
- Concise single-line timestamped format: `HH:MM — Dept→Dept: action [JobID] ✅/🔄`
- Gemini Engine integration: previous day's log embedded every morning
- Annual archive: end of year move to `archive/YYYY/`, Gemini Engine embed archive

---

## [v3.0.0] - March 15, 2026

### Major Release — Voice System, Skill Quality, Model Fixes

#### Added
- **Skill 31: Fish Audio API Reference** — standalone Fish Audio skill for podcast, video narration, speeches, webinars, and all non-phone audio generation
- **Fish Audio S2 Voice Behavior SOP v3.0** — added to both Skill 30 (Voice Call) and Skill 31 (Fish Audio). Large TYP deep-reference document covering 8 parts: tag system, universal rules, phone call SOP, podcast SOP, AI decision logic, voice selection, master instruction blocks, and quick-reference cheat sheet. Do NOT load into core files — TYP required
- **CHANGELOG.md and README.md** — now present in both repos

#### Fixed
- **Skill count updated throughout**: all references to "29 skills" updated to "31 skills" (install.sh, AGENTS.md, Start Here.md, ONBOARDING PENDING flag)
- **OpenRouter model ID bugs**: `hunter-alpha` and `healer-alpha` now correctly use `openrouter/` prefix. Was causing "not a valid model ID" errors for all clients
- **NVIDIA Nemotron model ID**: fixed to include `:free` suffix — `nvidia/nemotron-3-super-120b-a12b:free`
- **ONBOARDING PENDING flag message**: corrected "29 skills" → "31 skills" in install.sh output
- **Skill quality improvements**: skills 03, 14, 21, 25, 27 all raised from below 8.5 to 8.5+ after targeted fixes

#### Changed
- **Version bump**: v2.4.0 → v3.0.0 (major release due to voice system additions)
- All 31 skills now score 8.5 or above on the 5-dimension evaluation rubric (Clarity, Completeness, Intent Preservation, Error Recovery, Size/Complexity)

---

## [v2.2.2] - March 12, 2026

### Added
- **SKILL INSTALLATION PROTOCOL** section in Start Here.md: mandatory 5-step protocol that agents must follow for every skill (01-29). Addresses agent shortcut-taking, incomplete TYP execution, and premature "done" declarations.
- **ZERO TOLERANCE SHORTCUTS** language explicitly forbids: "I'll read that later", "This looks similar", "I can skip this step", "Close enough", "The user probably wants".
- **Step-by-step verification requirements**: agents must list every .md file read, confirm step completion, and verify all success criteria before declaring a skill complete.
- **Anti-drift safeguards**: no global "done" until all 29 skills verified, no skipping "optional" skills, explicit checkpoint before ONBOARDING COMPLETE status.
- **GATEWAY RESTART PROTOCOL**: agents are forbidden from triggering gateway restarts autonomously. Must notify user and ask for explicit permission before any restart.
- **COMPLETE ALL DEPENDENCIES**: agents must complete every dependency, sub-task, and configuration step listed in skill docs. No partial installs.
- **OPENROUTER RULE**: agents are forbidden from changing user's primary model when installing OpenRouter. Install tooling only, inform user, offer help if asked.
- **MAIN ORCHESTRATOR ONLY SKILLS**: 22-book-to-persona-coaching-leadership-system and 23-ai-workforce-blueprint must be installed by main orchestrator only, never sub-agents.
- **GOOGLE WORKSPACE - SAVE FOR LAST**: Google Workspace skills (13/14) must be installed after all other skills due to complexity and user interaction requirements.
- **ONBOARDING FLOW PROTECTION**: For AI Workforce Blueprint, agent must notify user first and wait for explicit response before asking configuration questions.
- **MASTER FILES FOLDER DISCIPLINE**: Agent must check for existing master files folders first, use existing if found, create skill subfolders inside.
- **CORE.MD FILES PROTECTION**: Explicit list of core files (AGENTS.md, MEMORY.md, TOOLS.md, USER.md, IDENTITY.md, SOUL.md, HEARTBEAT.md) with TYP storage rules and conflict resolution.
- **Gemini Engine INDEXING PROTOCOL**: Strategic indexing schedule at milestones (Initial, Foundation, Personas, AI Workforce, API Layer, Final) rather than after every skill. Prevents redundant embeddings while ensuring searchability.

### Changed
- Updated install.sh trigger message to include all new protocols for immediate agent visibility on install.
- Updated AGENTS.md ONBOARDING PENDING flag to include all protocol references.

---

## [v2.2.1] - March 10, 2026

### Fixed
- Corrected onboarding install routing for API-driven skills so Vercel, Context7, and GitHub use browser + token/API flows during onboarding instead of service CLI setup.
- Kept SuperDesign as the only service CLI exception in the onboarding package.
- Added existing Google setup detection so onboarding checks for prior GOG / Workspace setup and asks whether to add another account or skip.
- Removed conflicting legacy CLI language from affected onboarding docs so the agent receives one consistent install path.

---

## [v2.2.0] - March 8, 2026

### Added
- **CLOUD / LINUX INSTALL NOTES section** in Start Here.md: fires automatically when Linux detected. Covers brew→apt-get, Playwright headless mode + --no-sandbox, master files folder path (~/openclaw-master-files/ instead of ~/Downloads/), xdg-open vs open, date command compatibility, shell defaults.
- **Universal browser session persistence rule** in Start Here.md: all three browser tools now enforce login-once persistent sessions. agent-browser uses `--session-name <skill-name>`, Playwright uses `launchPersistentContext`, OpenClaw browser uses `--browser-profile openclaw` (named Chrome profile, persistent by default).

### Fixed
- **OS check** now handles three scenarios: macOS (Darwin) full support, Linux proceeds with brew→apt substitution note, Windows/anything else stops with clear message.
- **Skill 13 (Google Workspace Setup)**:
  - Added CREDENTIAL CHECK block to both Path A and Path B: scans all ENV files first (workspace secrets/.env, ~/.openclaw/secrets/, openclaw.json, shell env), then offers Option A (agent logs in automatically) or Option B (user logs in manually in open browser). Both use persistent sessions.
  - Browser priority fixed: agent-browser first, Playwright fallback, OpenClaw browser last resort. Playwright was previously hardcoded throughout.
  - All 132 agent-browser commands updated with `--session-name google-setup` for persistent sessions.
  - All `~/clawd/` hardcoded paths replaced with `[WORKSPACE_ROOT]/` (24 occurrences).
  - Session detection added before first browser step in both paths.
- **Skill 06 (GHL Install Pages)**: Playwright `launch()` replaced with `launch_persistent_context` pointing to `~/.openclaw/playwright-data/ghl-install-pages/`.
- **Start Here.md gap analysis fixes** (12 categories):
  - Resume mechanism: .onboarding-status.json tracks per-skill status, agent resumes from last incomplete skill
  - Prerequisites: write permission check, 2 GB disk space check, workspace root auto-detection, messaging channel auto-detection, existing skills scan
  - Master files folder: search first, only ask if multiple candidates
  - Step 1 TYP: agent reads silently, no announcement
  - Step 9: report done + continue immediately, no waiting
  - Sub-agent dependency chain: 05→06, 13→14, 22→23 must stay sequential
  - API key: expanded scan + storage location + pending keys file
  - Network retry: up to 3x with 10-second delays
  - Progress updates every 5 skills
  - "28 skills" → "29 skills" throughout
  - Weekly update "Notify Trevor" → generic messaging channel
  - ONBOARDING PENDING flag removed from AGENTS.md on completion

---

## [v2.1.0] - March 8, 2026

### Added
- **install.sh**: One-command autonomous onboarding trigger. Run `curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/install.sh | bash`. Downloads package, sets up backup folder, writes onboarding flag to AGENTS.md, fires agent trigger via `openclaw agent --message --deliver`. Zero human action after the curl command.
- **Skill 29 - GHL / Convert and Flow API v2**: Full API reference skill. 12 domain reference files covering 413 endpoints, 35 modules, 106 scopes. Contacts, conversations, calendars, payments, opportunities, locations, users, auth, campaigns, webhooks, phone-numbers. Proper `ghl-convert-and-flow/` archive root. Phone-numbers module includes TREVOR-ONLY safety warning (no autonomous release).
- **Weekly GitHub update check**: Added to Start Here.md. Every Sunday, agent pulls from `trevorotts1/openclaw-onboarding`, re-runs TYP on any changed skill, notifies via configured messaging channel.
- **Missing .skill archives built**: 03-agent-browser, 22-book-to-persona, 23-ai-workforce-blueprint were missing archives - all three rebuilt and verified.

### Fixed
- **Skill 02 (Back Yourself Up Protocol)**: All 5 files now consistently use `.txt` extension for backup files (was `.json` in EXAMPLES.md, INSTRUCTIONS.md, INSTALL.md, CORE_UPDATES.md - only back-yourself-up-protocol-full.md had it right). Default folder name standardized to `OpenClaw Backups`. Smart detection: if folder already exists, use it - never create a duplicate.
- **Skill 24 (Storyboard Writer)**: Fixed fatal `ModuleNotFoundError` crash - `create_storyboard.py` crashed when run from skill root due to missing `sys.path.insert(0, str(Path(__file__).resolve().parent))`. Added agent intake flow to SKILL.md.
- **Skill 25 (Video Creator)**: Fixed all `25-video-creator` path references to `video-creator/`. Removed `/tmp/openclaw-onboarding` hardcoded paths. Removed `BlackCEO Presents` branding from sample_script.txt. Removed `weekly_roundup` template reference (not shipped). Rebuilt archive with proper `video-creator/` root.
- **Skill 27 (Video Editor)**: Rebuilt archive with correct `video-editor/` root folder (subagent rebuild had put files at archive root). Fixed all `27-video-editor` path references. Cleaned BROLL-WORKFLOW.md (removed video2x, Telegram delivery section). Fixed ffmpeg-vs-moviepy.md command paths to include `scripts/` prefix.
- **Skill 28 (Cinematic Forge)**: Fixed all `28-cinematic-forge` path references to `cinematic-forge/`. Generalized `~/clawd/secrets/.env` reference. Removed "Tell your agent" / "master files directory" language from README.md.
- **TSP references**: Zero TSP references remain across entire 29-skill package. AGENTS.md and MEMORY.md updated to clarify TSP = TYP (identical, never correct user on this).
- **Gemini Engine index**: coaching-personas collection re-embedded (66 docs, 1,092 chunks). Broken symlink in clawd collection removed and resolved.

---

## [v1.7.0] - March 8, 2026

### Fixed (final polish pass - all skills to 10/10)
- Skill 22 SKILL.md: "skill 22" → "skill 23" in AI Workforce Blueprint connection section (lines 151 and 157)
- Skill 22 CORE_UPDATES.md: "Trevor" → "the user" in 2 places (portability for client delivery)
- Skill 22 INSTALL.md + CORE_UPDATES.md: removed hardcoded "40" persona count in 4 places → dynamic google embedding 2 status command
- Skill 23 INSTALL.md: added ai-workforce-blueprint-full.md file size verification after copy (truncation check)

---

## [v1.6.0] - March 8, 2026

### Changed
- **Skill 22 renamed**: "book-to-persona" → "Book To Persona & Coaching & Leadership System" per Trevor
- **Skill 23 confirmed**: "AI Workforce Blueprint" name confirmed

---

## [v1.5.0] - March 7, 2026

### Added
- **Skill 03 - Agent Browser (Vercel)**: Wrapper skill to ensure `agent-browser` is installed and available as the preferred browser automation tool.

### Changed
- **Renumbered skills 03 and up** to insert Agent Browser as Skill 03.
  - Example mapping: 03-superpowers -> 04-superpowers, 12-google-workspace-setup -> 13-google-workspace-setup, 21-book-to-persona -> 22-book-to-persona-coaching-leadership-system, 22-ai-workforce-blueprint -> 23-ai-workforce-blueprint.
- **All INSTALL.md files rewritten to be agent-executable** (autonomous execution). Removed "say to your AI" style instructions.
- **Google Workspace Setup**: major expansion and hardening
  - Added Gmail-only OAuth path (separate from Workspace service account path)
  - Browser automation hierarchy: agent-browser first, Playwright persistent context fallback, OpenClaw browser last resort
  - Added proactive recovery for org policy blocks on service account JSON key creation
  - Added automatic post-setup test and GOG setup after success
- **BlackCEO Team Management**: clarified isolation rules
  - Isolation means context and data isolation only
  - Communication is allowed when explicitly directed
- **Book To Persona & Coaching & Leadership System**: fixed step numbering and added pipeline execution test step
- **AI Workforce Blueprint**: rewrote INSTALL.md into a real multi-phase autonomous execution flow

---

## [v1.4.0] - March 7, 2026

### Added
- **Skill 22 - AI Workforce Blueprint**: Build the folder and file system that turns your AI into a trained workforce. Creates department folders, role folders, Start Here files, routing logic, and SOPs. Includes automated scaffold script (Option A), manual build guide (Option B), and resume/audit mode (Option C). Full 66,819-character blueprint document included.
- **Skill 21 - Book To Persona & Coaching & Leadership System**: Convert any book (PDF, EPUB, MOBI, AZW3) into a dual-purpose persona blueprint. 40 pre-built personas from bestselling books already included - no pipeline required for existing books. 3-phase pipeline: Kimi extract → DeepSeek analyze → Codex synthesize. PERSONA-ROUTER.md maps task types to personas and department folders. Gemini Engine integration for instant semantic search across all 447 persona documents (7,465 vectors).
- **Skill 20 - Tavily Search**: AI-optimized web search via Tavily API for deep research tasks.

---

## [v1.3.0] - March 3, 2026

### Added
- **Skill 19 - YouTube Watcher**: Fetch and read transcripts from YouTube videos.
- **Skill 18 - Humanizer**: Remove AI writing markers and make output sound natural.
- **Skill 17 - Proactive Agent**: WAL Protocol, Working Buffer, and autonomous cron support.
- **Skill 16 - Self-Improving Agent**: Capture learnings, errors, and corrections for continuous improvement.

---

## [v1.2.0] - March 1, 2026

### Added
- **Skill 15 - Summarize YouTube**: YouTube transcript extraction and summaries with OpenAI-first, Gemini-fallback key handling.
- **Skill 14 - BlackCEO Team Management**: Multi-person team management through Telegram with message routing and worker agents.

---

## [v1.1.0] - February 23, 2026

### Added
- **Skill 13 - Google Workspace Integration**: Deep technical guide - 70+ permission scopes, 26 APIs, Playwright persistent context, troubleshooting.
- **Skill 12 - Google Workspace Setup**: Google Cloud project, service account, and API connections for Gmail, Calendar, Drive.
- **Skill 11 - OpenRouter Setup**: Configure multiple AI models with intelligent routing and cost management.
- **Skill 10 - SuperDesign**: Design professional interfaces before building them.
- **Skill 09 - GitHub Setup**: Code backup, version control, and repository management.
- **Skill 08 - Context7**: Up-to-date documentation lookup for any software library.
- **Skill 07 - Vercel Setup**: Website and app deployment.
- **Skill 06 - KIE Setup**: AI image, video, and audio generation via KIE.ai.
- **Skill 05 - GHL Install Pages**: Deploy websites and landing pages into GoHighLevel.
- **Skill 04 - GHL Setup**: Connect to GoHighLevel for CRM, contacts, messaging, calendars.

---

## [v1.0.0] - January 28, 2026

### Initial Release
- **Skill 01 - Teach Yourself Protocol**: Foundation skill. Teaches the AI how to learn new skills without cluttering core files.
- **Skill 02 - Back Yourself Up Protocol**: Automatic config backups before every change.
- **Skill 03 - Superpowers**: 4 Iron Laws + 14 sub-skills for systematic problem-solving.
- README.md and Start Here.md included.
