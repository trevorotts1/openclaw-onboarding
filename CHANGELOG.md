# Changelog

All notable changes to the OpenClaw Onboarding package are documented here.

---

## [v1.7.0] - March 8, 2026

### Fixed (final polish pass - all skills to 10/10)
- Skill 22 SKILL.md: "skill 22" → "skill 23" in AI Workforce Blueprint connection section (lines 151 and 157)
- Skill 22 CORE_UPDATES.md: "Trevor" → "the user" in 2 places (portability for client delivery)
- Skill 22 INSTALL.md + CORE_UPDATES.md: removed hardcoded "40" persona count in 4 places → dynamic qmd status command
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
- **Skill 21 - Book To Persona & Coaching & Leadership System**: Convert any book (PDF, EPUB, MOBI, AZW3) into a dual-purpose persona blueprint. 40 pre-built personas from bestselling books already included - no pipeline required for existing books. 3-phase pipeline: Kimi extract → DeepSeek analyze → Codex synthesize. PERSONA-ROUTER.md maps task types to personas and department folders. QMD integration for instant semantic search across all 447 persona documents (7,465 vectors).
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
