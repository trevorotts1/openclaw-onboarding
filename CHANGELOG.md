## [v5.5.1] - March 20, 2026

### Skill 23: QC Agent Roles for All 17 Departments

#### Added
- QC-ROLES-MASTER.md: 34KB master reference covering what QC agents do, how they work, reporting structure, and model selection guidance
- QC agent role added to all 17 department suggested-roles files
- Department-specific QC checklists and validation procedures
- QC agents report to department heads. Do not produce deliverables.

#### Notes for Existing Clients
- No config changes required
- QC agent roles are optional additions. Existing department setups are not affected.
- To add a QC agent to any department, read QC-ROLES-MASTER.md first.
- Risk level: LOW (additive only, no breaking changes)

# Changelog

All notable changes to the OpenClaw Onboarding package are documented here.

---

## [v5.5.0] - March 20, 2026

### Mem0 Gemini Migration + Skill 32 Cloudflare Manual Setup

#### Changed
- **Skill 31**: All Mem0 config examples switched from OpenAI to Gemini
  - LLM: `gemini` provider, model `gemini-3-flash-preview`
  - Embedder: `gemini` provider, model `models/gemini-embedding-001`
  - Both use `${GEMINI_API_KEY}`, zero OpenAI dependency
  - Migration warning added for vector store dimension mismatch
- **Skill 32**: Added Phase 8 (Manual Cloudflare Tunnel Setup)
  - 9 subsections: install, auth, create tunnel, config, DNS, start, test, persistence, Tailscale alt
  - macOS (launchctl) and Linux (systemd) persistence
  - Phase 6b clarified as agent-automated path with cross-reference to Phase 8
  - Phase numbering fixed (was broken: 6b, 7, 9 with missing 8)

#### Fixed
- Skill 32 phase numbering corrected
- Skill 32 sub-numbering in Phase 9 fixed (was using 8.x instead of 9.x)

---

## [v5.4.2] - March 19, 2026

### Command Center Hardening

#### Added
- Approved Option C hostname rule for Skill 32: `[company-slug]-[shortid]`
- Unique-hostname check requirement before DNS registration completes
- Free self-hosted Mem0 / GitHub verification requirement during Command Center setup
- 5-layer memory verification requirement for each department workspace

#### Changed
- Skill 32 INSTALL.md now explains the collision-safe hostname pattern
- Verification phase now checks free OSS memory mode and 5-layer memory readiness
- Completion checklist now includes hostname uniqueness and memory verification

---

## [v5.4.1] - March 19, 2026

### Cloudflare Tunnel Auto-Setup for Client Onboarding

#### Added
- Phase 6b to Skill 32: Cloudflare Tunnel and Domain Registration
- Automated tunnel creation on client machines
- Webhook registration system for subdomain DNS routes
- Client registry tracking at ~/clawd/projects/blackceo-command-center/client-registry.json
- command-center-webhook.sh script for automated DNS route creation
- Support for both macOS and Linux/VPS cloudflared installation
- Automated DNS propagation waiting and URL verification
- Live URL reporting to clients after tunnel setup

#### Changed
- Skill 32 INSTALL.md now includes Phase 6b between Phase 6 and Phase 7
- Phase 8 renamed to Phase 9 (manual tunnel setup as fallback)
- Completion checklist updated with Cloudflare tunnel verification steps

---

## [v5.4.0] - March 19, 2026

### Skill 32: Command Center Setup

#### Added
- **Skill 32: Command Center Setup** - Activates AI workforce as a live Command Center
- Persistent department agents with dedicated Telegram topics
- Visual Kanban dashboard at localhost:3000
- Integration between Skill 23 (AI Workforce Blueprint) and live operation
- 8-phase installation process with guided Telegram setup
- Automated workspace creation for each department
- Automated agent configuration with memory search setup
- Topic binding system for department-specific communication
- Cloudflare tunnel support for remote dashboard access
- 3-check standup cadence (morning, midday, end of day)
- Worker spin-up system with persona assignment

#### Files Added
- `32-command-center-setup/SKILL.md` - Overview and context
- `32-command-center-setup/INSTALL.md` - Step-by-step installation guide
- `32-command-center-setup/INSTRUCTIONS.md` - Post-install usage guide
- `32-command-center-setup/CORE_UPDATES.md` - Core file updates
- `32-command-center-setup/command-center-setup.skill` - Skill metadata

#### Updated
- README.md: Added Skill 32 to skill inventory, updated version to v5.4.0
- Start Here.md: Added Skill 32 to the skill list table
- install.sh: Updated skill count from 31 to 32
- scripts/update-skills.sh: Updated skill number range to include 32

---

## [v5.3.1] - March 19, 2026

### Updater: Silent Failure Fix

#### Fixed
- Update script no longer silently exits when onboarding folder is not found
- Error message is now loud, clear, and tells the user exactly what to do next
- Includes both "run the install first" and "find your files" instructions

---

## [v5.3.0] - March 19, 2026

### Skill 23: AI Workforce Blueprint

#### Added
- Department heads (Role #0) added to all 15 existing departments
- Two new departments: Research and Communications
- All 17 departments now presented equally (removed "optional" tier)

#### Changed
- INSTALL.md: Updated department list to show all 17 as recommended choices
- ai-workforce-blueprint-full.md: Replaced tiered department list with flat list of all 17
- SKILL.md: Updated "Pre-Built Departments Available" to list all 17 departments
- suggested-roles/README.md: Added Research and Communications to department file list

---

## [v5.2.3] - March 19, 2026

### Skill 31: Source-Verified Corrections

#### Fixed
- **extraPaths must use absolute paths** (e.g., `/Users/USERNAME/Downloads/...`), not tilde paths. OpenClaw `path.isAbsolute()` treats `~` as relative and prepends workspace dir, creating invalid paths. Verified in `src/memory/internal.ts:normalizeExtraMemoryPaths`.
- **Corrected supported file types** from source code (`src/memory/multimodal.ts`): only `.md` + images (jpg/jpeg/png/webp/gif/heic/heif) + audio (mp3/wav/ogg/opus/m4a/aac/flac) are indexed. Removed false claims about PDF, TXT, MP4, and WebM support.
- **Added helper command** `echo "$(cd ~/Downloads/openclaw-master-files && pwd)"` so agents can resolve the absolute path correctly.

---

## [v5.2.2] - March 19, 2026

### Skill 31: Full Indexing + Embedding of Master Files

#### Added
- **extraPaths config step** in INSTALL.md: agent must find and add the master files folder to memorySearch.extraPaths so ALL subfolders, personas, AI workforce docs, and knowledge files get indexed
- **Multimodal indexing config step**: enables Gemini Embedding 2 to embed images, audio, video, and PDFs, not just markdown
- **Complete Layer 4 config example** showing the full memorySearch block with extraPaths + multimodal + sync + query
- **Updated checklist** with extraPaths and multimodal verification items
- **Updated CORE_UPDATES.md** TOOLS.md section to document extraPaths and multimodal settings

#### Fixed
- The root cause of her agent not indexing master files: sources only covered memory + sessions, extraPaths was never configured

---

## [v5.2.1] - March 19, 2026

### Skill 31: 10/10 Release

#### Added
- **FULL-DOC.md** combined reference document (all skill docs in one file, 1036 lines)
- **Automated rollback procedure** for Layer 4, Layer 5, and config validation failures
- **Update result JSON writer** (.update-result.json) for Telegram agent handoff after terminal updates
- **AGENTS.md flag writer** so agent auto-detects updates and communicates to user in Telegram

#### Changed
- Rollback rules: restore first, debug second. Never leave user on invalid config.
- Update script now writes structured status for agent consumption instead of just terminal output

---

## [v5.2.0] - March 19, 2026

### Skill 31: Core Updates Rewrite + Client Education

#### Changed
- **CORE_UPDATES.md rewritten** with concise, TYP-compliant additions for MEMORY.md, AGENTS.md, TOOLS.md, and HEARTBEAT.md
- **Explicitly lists which core files to NOT modify** (USER.md, SOUL.md, IDENTITY.md)
- **HEARTBEAT.md addition** for periodic memory health monitoring

#### Added
- **HOW-YOUR-MEMORY-WORKS.md** - plain-English explanation of all 5 memory layers for clients who ask how their system works. No jargon. Written for non-technical users.
- **Client education checklist item** added to completion checklist
- **SKILL.md updated** with new file listing and reading order

---

## [v5.1.1] - March 19, 2026

### Skill 31: Embedding + Real Layer Testing

#### Fixed
- **Indexing and embedding are now separate documented steps** with distinct verification for each
- **Embedding verification** checks for Vector dims: 3072 to confirm Gemini Embedding 2 is generating vectors
- **Real layer testing** replaces config-only checks: each layer is tested with actual queries/operations
- **Per-layer test results** reported individually to user in Telegram with pass/fail and diagnostics
- **Expanded checklist** now has 4 sections: Configuration, Restart, Indexing/Embedding, Live Testing, Reporting
- **All Gemini-supported file types** explicitly listed for indexing (md, txt, pdf, images, audio, video)

---

## [v5.1.0] - March 19, 2026

### Skill 31 Major Upgrade: Testing, Indexing, Telegram Flow

#### Added
- **Post-install memory layer testing** with per-layer verification reported to user in Telegram
- **Config validation gate** before restart (openclaw config validate must pass)
- **Knowledge base indexing trigger** after restart: indexes all master files, subfolders, personas, AI workforce docs, and multimodal files (images, audio, PDFs)
- **Telegram-first update flow** design: update progress and approval happen in Telegram, not terminal
- **Update status file** (.update-result.json) for agent handoff after terminal updates
- **Expanded completion checklist** with config validation, indexing, live search test, and Telegram reporting steps

#### Fixed
- Post-install verification now tests each layer individually instead of a single generic search
- Restart safety: config must validate before user is asked to restart

---

## [v5.0.5] - March 19, 2026

### Update Script Safety + Skill Refresh Fix

#### Fixed
- **Updater now runs `openclaw config validate`** after applying changes. If config is invalid, it warns the user and blocks restart.
- **Skill folders with content changes are now properly detected** for refresh during updates

#### Changed
- Changelog is now maintained as an ongoing record of every version with specific changes documented per standard release practice

---

## [v5.0.4] - March 19, 2026

### Cache-Busting Fix

#### Fixed
- **Updater now cache-busts all GitHub requests** so clients always get the latest changelog and files, not stale CDN copies

---

## [v5.0.3] - March 19, 2026

### Critical Migration Fix

#### Fixed
- **memory.backend must be "builtin" not "gemini"** in MIGRATION.md, Skill 31 INSTALL.md, and CORE_UPDATES.md
- Setting memory.backend to "gemini" crashes the gateway on restart (only "builtin" and "google embedding 2" are valid)
- All migration instructions now use the correct value

---

## [v5.0.2] - March 19, 2026

### Client Approval UX Fix

#### Fixed
- **Non-interactive update runs now stop with a human explanation** instead of looking like a mysterious cancel
- **Exact rerun commands shown** when approval is required but the script was launched with `curl ... | bash`
- **Clearer approval and cancel wording** so clients understand whether anything changed

---

## [v5.0.1] - March 19, 2026

### Update System Hardening

#### Changed
- **update-skills.sh rewritten to v3.0** — works on any machine with dynamic onboarding folder detection
- **Backup protocol added** — backs up core .md files and openclaw.json before applying updates
- **Approval workflow added** — shows change plan, risk levels, and waits for explicit user approval
- **Verification step added** — confirms version marker, skill count, and warns if restart may be needed
- **No autonomous restarts** — script never triggers a gateway restart; user must do it manually if needed

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

## v5.5.2 - March 21, 2026
- Fix: gemini-indexer.py now does case-insensitive search for master files folder (handles "Open Claw Master Files", "openclaw-master-files", etc.)
- Fix: install.sh now copies gemini-indexer.py and gemini-search.py to ~/clawd/scripts/ on install so Skill 22 dependency checks pass
- Fix: install.sh now writes GOOGLE_API_KEY to ~/clawd/secrets/.env if set in environment during install
- Fix: Skill 22 docs (GEMINI-RETRIEVAL-GUIDE.md, PIPELINE.md, PERSONA-ROUTER.md) updated to use correct script paths

- Fix: Skill 22 orchestrator.py now auto-installs Calibre via Homebrew when missing instead of stopping and asking the user

- Fix: Parallel sub-agent install architecture - Wave 0 pre-flight config, Wave 1 via sub-agent (main stays free), Wave 2 with 6 parallel agents, correct sessions_spawn commands replacing invalid openclaw agent spawn, maxConcurrent 20/maxChildren 10/maxDepth 4 config block
