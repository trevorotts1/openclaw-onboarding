# OpenClaw Onboarding — Unified (Mac + VPS)
<!-- PRD 2.1 unified repo — branch prd-2.1-unified-repo -->

> **Version:** see `/version` - this repo at v12.4.8.
>
> **NOTE (v12.4.8) -- feat: professional design-craft, color-theory, and QC standard for Presentations (Skill 23).** Encodes the PROFESSIONAL DESIGN-CRAFT + COLOR-THEORY standard across four presentation role files and their SOP mirrors. All 8 design-craft dimensions verified MISSING (grep=0) before this change. Art-Director Persona; THE THIRDS SYSTEM; IMAGE LAYERING AND DEPTH; OBJECTS / CARDS / PANELS / INSETS; SOP 9.7 Color Theory and Color Grading; Design-Craft Auto-Fail Battery (AF-DC1 through AF-DC7); Design-Craft Scoring Dimensions (p-DC1/i-DC1 through p-DC7/i-DC7 with double-weight for color-harmony and color-grading); design_craft block in final_deck_qc.json; expanded media-library folder structure with naming conventions. Brand Steward adds step 5a, COLOR THEORY + COLOR GRADING sections to STYLE BLOCK, Gate 7, and 3 new common mistakes. See [CHANGELOG.md](CHANGELOG.md).
> Every release MUST agree across the version-tracked files; run `./scripts/bump-version.sh vX.Y.Z` to update them atomically. Drift is caught in CI (`.github/workflows/version-consistency.yml`).
>
> **NOTE (v12.4.7) — feat: DIU full role set — 13 graphics specialists registered.** Eight remaining Design Intelligence Unit specialist roles (design-producer, style-librarian, likeness-rights-officer, render-dispatcher, asset-provenance-librarian, style-steward, brand-systems-specialist, motion-systems-specialist) added to `_index.json` + ROLE-- files shipped. Graphics dept count 23 → 31, total_roles 323 → 331. All 26 SOP-DIU files present; SOP-DIU id uniqueness verified. See [CHANGELOG.md](CHANGELOG.md).
>
> **NOTE (v12.4.7) — feat: Presentation Department change order v2 + ROLE-16 Healer-Presentations.** Comprehensive P0-P5 presentation pipeline fixes (API contract, doctrine restorations, Hook Lab, Delivery Concierge, Presenter Coach, Capacity/Reliability watchdog), plus ROLE-16 Healer-Presentations added to presentations department. Presentations dept count 15->16, total_roles 281->282. See [CHANGELOG.md](CHANGELOG.md).
>
> **NOTE (v12.4.7) — feat: shared core-file unification (Zero-Human-Workforce file model).** On every box, ALL of an account's agents + sub-agents now SHARE the box's ONE canonical `AGENTS.md` / `TOOLS.md` / `USER.md` via symlink (not duplicated); per-agent `IDENTITY.md` / `SOUL.md` / `MEMORY.md` / `HEARTBEAT.md` stay each agent's own. `link_shared_core_files()` runs at install (`install.sh` Step 10a) and on every update (`update-skills.sh`). Co-mingling guard: the symlink target is always the LOCAL box's own canonical, resolved from that box's own `openclaw.json` — never a cross-box/cross-account path. Nested workflow agents (`*/workflows/*/agents/*`) are exempt. Non-destructive (backups + additive `IDENTITY.md` preservation) and idempotent. QC check 9.9 enforces it. Full rule: [docs/SHARED-CORE-FILES.md](docs/SHARED-CORE-FILES.md). See [CHANGELOG.md](CHANGELOG.md).
>
> **NOTE (v12.4.7) — fix: safe_json_edit validate/rollback guard added (parity with VPS v10.16.49 skills.path fix).** The VPS updater was writing `skills.path` into `openclaw.json` — rejected by OpenClaw 2026.5.x — which aborted the entire VPS updater before writing `.onboarding-version`. Mac updater had no such write but equally lacked a validate/rollback harness. `safe_json_edit()` added as a forward-defense guard for any future direct json edits. See [CHANGELOG.md](CHANGELOG.md).
>
> **NOTE (v12.4.7) — TYP hardening: explicit storage path, pointer format, mandatory no-paste rule.** `01-teach-yourself-protocol` INSTRUCTIONS.md and the full doc (Section 13 + Section 17) now specify the canonical Mac storage path (`~/Downloads/openclaw-master-files/<subfolder>/`), mandatory pointer format (full path + "when to go deeper"), and a non-negotiable no-paste rule: long docs are NEVER pasted into bootstrap files. Shared bootstrap templates (AGENTS.md, TOOLS.md, USER.md, SOUL.md, IDENTITY.md) all carry a short mandatory TYP rule so every agent reads it on session start. TYP skill-version.txt → v6.5.7. Per-release version history lives in [CHANGELOG.md](CHANGELOG.md). VPS (10.16.x) and Mac (10.15.x) sequences remain intentionally independent.
>
> **After every release:** `git tag vX.Y.Z && git push --tags && gh release create vX.Y.Z --notes-from-tag` so the GitHub Releases page mirrors the CHANGELOG.

**A complete onboarding package for setting up a fully operational OpenClaw agent on Mac mini or Hostinger Docker VPS.**

**Current Version: v12.4.8** - See [CHANGELOG.md](CHANGELOG.md) for the full per-release history.

This is the **unified repo** for both platforms (PRD 2.1). Platform-specific files live in `platform/mac/` and `platform/vps/`. The `install.sh` auto-detects Mac vs VPS, or accepts `OPENCLAW_PLATFORM=mac|vps`.

> Previously the VPS installer was a separate repo (`trevorotts1/openclaw-onboarding-vps`). That repo will become an archived pointer to this unified one. Do not add new features to the VPS repo.

This repo contains **44 numbered skill folders (01 through 44)** — 41 active plus 3 archived (13, 33, 34) — plus an install script and update script. See the [Skill Inventory](#skill-inventory-folder-names) below for the full live list.

> **First time installing or updating?** Read **[ONBOARDING-TRIGGERS.md](ONBOARDING-TRIGGERS.md)** — it shows exactly how to start a fresh install or run an update via Terminal or Telegram.

> **Release history:** Per-release "What's New" notes for v6.x through the current v10.15.x line live in **[CHANGELOG.md](CHANGELOG.md)**. This README shows live state only.

---

## Quick Install (Recommended)

**Mac mini (macOS):**
```bash
curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/install.sh | bash
```

**Hostinger Docker VPS** (run on VPS host SSH session or directly inside container):
```bash
curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/install.sh | bash
```
The installer auto-detects the platform. If running on the Hostinger Docker host (not inside the container), it re-executes inside the container automatically. See `platform/vps/INSTALL-GOTCHAS.md` for edge cases.

What it does:
1. Downloads the latest onboarding package
2. Detects platform (Mac or VPS) and sources the appropriate bootstrap
3. Copies skills into the canonical skills directory (`~/.openclaw/skills/` Mac / `/data/.openclaw/skills/` VPS)
4. Installs Gemini Engine early (required by skill 22 and skill 23)
5. Asks for missing API keys with a skip option (does not block optional skills)
6. Prints the next step

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
| 38-conversational-ai-system | **Conversational AI System (v12.4.7)** — the conversational AI BRAIN on top of skill 29 (GHL Convert and Flow). 45 protocols (sales brain, intelligent follow-up, dual-mode customer service + support, typed knowledge bases, intelligent routing, weekly + monthly self-tuning, model version freshness, ZHC tag-prefix, F45 geo-qualification, F46 CRM field write, F47 inline smart-FAQ, F49 ZHC Pixel, plus the Round-2 6: F21 multi-tenant isolation, F17 segmentation, F15 proactive outreach, F16 A/B testing, F14 voice/phone, F18 webhook chaining — all default-OFF, etc.). 8 customer journey templates. 68 idempotent OS-aware scripts. 19 references. Sunday 2am + Saturday 11pm + 1st-of-month crons. Skills 05/10/19/29 required as prerequisites. Its `skill-version.txt` versions independently of the repo line. |
| 39-real-estate-playbook | **Real Estate Playbook & Property Intelligence (v12.4.7)** — the real-estate VERTICAL on top of skill 38. Provider-abstraction property intelligence (keyless US Census geocoding + optional Google/Mapbox/RentCast/MLS — honest gap, NEVER fabricated), buyer/seller/investor qualification, showing scheduler (lockbox/MLS rules), 50-state + DC disclosure pointer matrix, lead routing by agent specialty, open-house + pre-foreclosure outreach (pairs with skill 40), and an ADDITIVE Sales-Brain RE extension (RE objections + CMA pricing-reveal timing + SPICED-RE) that drops into skill 38 without editing its own protocol. Emits `real-estate-events.jsonl`. ZHC tags: buyer/seller/investor-lead, pre-foreclosure-prospect. Skill 38 required as prerequisite. |
| 40-zhc-public-records-scraper | **ZHC Public Records Scraper (v12.4.7)** — tiered, compliance-first public-records intelligence and the data sibling of skill 39. address/ZIP → county+state → Tier 1 (curated configs for 21 major counties: Cook, LA, Maricopa, Harris, San Diego, Orange, Miami-Dade, Kings, Dallas, King, Clark, Santa Clara, Tarrant, Riverside, Wayne, Broward, Bexar, Sacramento, San Bernardino, Hillsborough, Pierce) → Tier 2 (platform-adapter framework + Tyler/GovOS example adapters) → Tier 3 (operator-buildable, validated config) → else Tier 4 (HONEST GAP, never fabricated). robots.txt respected, ToS per target, source+timestamp attribution; cost cap + per-day + per-target rate limits with bulk cost confirm; 30-day cache. Emits `public-records-queries.jsonl` (F52 PII-free contract: opaque query_ref/target_ref, record TYPES + counts only). RE use cases (pre-foreclosure/NOD, tax delinquency, comps, permits, tax, ownership). Never runs outreach (that's skill 39). |
| 41-build-with-ai-playbook | **Build With AI Playbook Generator (v12.4.7)** — generates GoHighLevel "Build With AI" conversation playbooks: dependency-ordered build steps, webhook/trigger configuration, prompt-completeness + no-fabrication + no-personal-data + zhc-tag-prefix QC gates (each with a passing negative self-test), and OS-aware (uname -s) install scripts. Templates + protocols for repeatable, verified GHL workflow generation. Installer scripts 00-04 run at client-install time only. |
| 42-personal-assistant-library | **Personal Assistant Library (v12.4.7)** — 29 ready-to-deploy personal-life specialists (inbox, calendar, daily briefing, tasks, meetings, research, brainstorming, coaching, emotional support, travel, finance, relationships, errands, life-admin, spiritual life, motivation, challenger, family, study partner, passion/purpose, clarity, YouTube teacher, goals, superwoman, imposter, therapeutic support, focus, celebration, greatness). Each ships 6 role files (IDENTITY/SOUL/governing-personas/how-to/ROSTER/00-START-HERE) + a DMAIC `SOP/` folder (`PA-NN-NN-slug.md`, consistently named) — 180 role files (Specialist 19 adds 6 sub-specialist role files), 162 SOPs + 29 indexes total. The agent materializes a specialist into `workspace/departments/personal-assistant/<slug>/` on demand and fills `{{TOKEN}}` placeholders from USER.md. Additive to Skill 23 (does NOT modify it); the optional `department-naming-map.json` auto-build patch is deferred to a product decision. Coaching-scope specialists (09/24/26) carry STOP-and-refer crisis protocols. Skill 23 required as prerequisite; Skill 22 recommended (graceful degradation). |
| 43-graphify-knowledge-graph | **Graphify Knowledge Graph (v12.4.7)** — turns the client's OWN workforce/codebase/docs into a persistent, queryable knowledge graph (`graphify-out/`: clickable `graph.html`, god-node `GRAPH_REPORT.md`, `graph.json`). Installs graphify (`uv tool install "graphifyy[all]"`), registers the OpenClaw skill (`graphify install --platform claw`), maps the workforce ONCE using the CLIENT'S OWN model (`deepseek-v4-pro:cloud` via their Ollama — NEVER the operator's keys), installs the FREE AST auto-rebuild hook (`graphify hook install`), and wires `/graphify` (query/path/explain) so the agent reaches for the graph FIRST on "how is this wired / what depends on what" questions. **Two tiers:** the heavy semantic pass is on-demand (owner-triggered); the AST rebuild is free + automatic on every commit. Carries the binding NO-COMINGLING rule. Additive — modifies no other skill; versions independently via its own `skill-version.txt`. |
| 45-design-intelligence-library | **Design Intelligence Library (v12.4.7)** — Design Intelligence Unit (DIU): self-contained image-style analysis and generation system. 13 specialist roles (style-analyst, deck-systems-specialist, generation-operator, photo-shoot-director, fidelity-tester, design-producer, style-librarian, likeness-rights-officer, render-dispatcher, asset-provenance-librarian, style-steward, brand-systems-specialist, motion-systems-specialist) + extended Brainstorming Buddy — Graphics + Chief Design Officer gatekeeper integration. Ships 26 SOP-DIU files, 12-dimension style analysis protocol, style-card library (3 prompt tiers SHORT/MEDIUM/LONG), Style Rotation Engine for deck generation, personal photo shoot mode with identity-lock guarantees, fidelity-test protocol (≥4.0 avg, 3-strike escalation), and routes across 7 image-generation endpoints. Skill 07 (Kie.ai) prerequisite. |

**Total: 45 numbered skill folders** (01 through 45) — **42 active + 3 archived** (13, 33, 34). This matches the live tree on `main`.

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

## Speech-to-Text (Audio Transcription) — tiered, Mac-local

This repo is the **Mac (Apple Silicon)** installer, so audio transcription runs **LOCALLY** by default:

- **Primary: local `faster-whisper`, model `medium`** — balanced (fast on the Apple Neural Engine), **free** (no token cost), and **private** (audio never leaves the client's machine).
- **Final fallback: OpenAI cloud** (`gpt-4o-mini-transcribe`) — so transcription never hard-fails if the local model is missing or errors.

`install.sh` Step 8b does this automatically on a fresh install:
1. Installs a faster-whisper CLI locally (`uv tool install whisper-ctranslate2`, with `pipx`/`pip3 --user` fallbacks).
2. Writes a deterministic wrapper at `~/.openclaw/bin/oc-faster-whisper` (forces model `medium`, prints plain text to stdout).
3. Bakes `tools.media.audio` into `~/.openclaw/openclaw.json` with the local CLI as the **first** model entry (primary) and OpenAI cloud as the **last** entry (fallback).

See **[docs/STT-TRANSCRIPTION.md](docs/STT-TRANSCRIPTION.md)** for the full note (config shape, how to change the model, and how this differs from the VPS platform overlay, which uses cloud Groq — no local model).

---

## Shared Core Files (Zero-Human-Workforce file model)

On **every box**, all of that account's agents and sub-agents **share the box's
ONE canonical `AGENTS.md`, `TOOLS.md`, and `USER.md`** via **symlink** (not
duplicated). Each agent keeps its **own** `IDENTITY.md`, `SOUL.md`, `MEMORY.md`,
and `HEARTBEAT.md`.

- **CANON_DIR** = the box's default agent workspace (`agents.defaults.workspace`,
  same resolver as `install.sh` Step 10).
- **Co-mingling guard:** the symlink target is always the LOCAL box's own
  canonical, resolved from that box's own `openclaw.json` — never a hardcoded or
  cross-box/cross-account path. A client box links to the client's own files.
- **Nested workflow agent exemption:** internal workflow micro-agents (`*/workflows/*/agents/*`)
  are never touched.
- **Non-destructive + idempotent:** real files are backed up
  (`*.bak-unify-<ts>`, never deleted) and any unique content is preserved into
  the agent's own `IDENTITY.md` before linking; correct symlinks are no-ops on
  re-run.

Runs automatically at install (`install.sh` Step 10a) and on every update
(`update-skills.sh`), and is QC-enforced (check 9.9 in
`scripts/qc-system-integrity.sh`). Full rule: **[docs/SHARED-CORE-FILES.md](docs/SHARED-CORE-FILES.md)** (N29).

---

## Notes

- Gemini Engine is installed by `install.sh` before platform skills. There is no separate Gemini Engine skill folder.
- If you fork this repo for client delivery, update `install.sh` to point at your fork.
