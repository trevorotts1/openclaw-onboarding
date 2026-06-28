# OpenClaw Onboarding — Unified (Mac + VPS)
<!-- PRD 2.1 unified repo — branch prd-2.1-unified-repo -->

> **Version:** see `/version` - this repo at v14.27.1.
>
> **NOTE (v14.26.0) — fix: tools.agentToAgent added to complete routing set at all four write-sites.** PR #398 (v14.26.0) added `tools.sessions.visibility=all` at all four config write-sites but omitted `tools.agentToAgent`. Without it the routing agent can see all sessions but cannot send peer-agent messages directly, so cross-agent handoffs silently fail on newly provisioned boxes. Fixed: `tools.agentToAgent = {"enabled": true, "allow": ["*"]}` now emitted by build-workforce.py (build-time), apply-routing-fix.sh Layer 5 (self-heal), apply-fleet-standards.sh CEO re-assert (fleet roll), and hooks/lib-ceo-tool-gate.sh (revoke/restore path). All four write-sites emit the complete routing tool set. Idempotent: patch scripts use `setdefault` so any already-customized `allow` list is preserved. See [CHANGELOG.md](CHANGELOG.md).
>
> **NOTE (v14.26.0) - fix(persona-system): complete gemini dead-path sweep + reproducible section tagging + canonical persona categories + department-agnostic specialist routing.** Closes the persona-system repo-comprehensive review. (1) The v14.21.0 hygiene pass fixed only the `~/clawd/scripts/gemini-*` refs in 8 docs and missed 715 live `~/.openclaw/workspace/scripts/gemini-*` run-commands across 643 files (skill-22 retrieval/router/QC/install/pipeline docs + every role-library specialist template); ALL now point at the canonical `~/.openclaw/scripts/gemini-*.py` and zero live-command dead paths remain repo-wide (CHANGELOG/legacy-comment provenance preserved). (2) Added the live fleet tagger `section-tag-migration.py` and made `embedding_engine.py` the single source of truth for the section→mode map (`LEADERSHIP_SECTION_NUMBER=4`, new `COACHING_SECTION_NUMBER=3`); `gemini-section-indexer.py` imported the constants, fixing its hardcoded `COACHING_SECTIONS={6}` (Section 6 was wrongly tagged coaching; canonical is Section 3=coaching, 4=leadership — matching live). (3) Reconciled the skill-22 `persona-categories.json` bundle copy (diverged md5 79df2afd) to the canonical 54-persona runtime set (md5 c544561). (4) `persona-selector-v2.py` now reads the distinctive `custom[]` specialty tags so a clearly-named canonical specialist (network-marketing→`brunson-network-marketing-secrets`, sketchnote→`rohde-the-sketchnote-workbook`) is reachable AND wins regardless of department — additive-only, never-to-zero, provably inert on generic tasks. New agreement + specialist-routing tests wired into CI; existing selector A6/A7 and the 45-test funnel pytest stay green. No client names or secret values. See [CHANGELOG.md](CHANGELOG.md).
>
> **NOTE (v14.26.0) - fix(skill6): GoHighLevel credential resolution searches every alias + every env store (kills the six-month image-step false-fail) + folds the B7 SOP docs (closes PR #356).** The Skill-6 image/media step once false-failed `"GHL LOCATION PIT not found"` on a LOCATION Private Integration Token the operator had used for SIX MONTHS — the token was in `~/.openclaw/secrets/.env` under `GOHIGHLEVEL_API_KEY` the whole time, but the resolver checked only two env-var names in the live process environment and never opened the canonical store, so a clean agent shell (where the gateway had not exported `secrets/.env`) read empty and fail-loud. `ghl_media.resolve_location_pit()` / `resolve_location_id()` now resolve from EVERY known LOCATION-class alias AND, when the live env is empty, parse the canonical env stores directly (`~/.openclaw/secrets/.env` → `~/clawd/secrets/.env` → `~/.openclaw/workspace/.env`) — the same multi-alias/multi-store pattern as the Google 3-alias key and the `KIE_API_KEY` store-fallback. It NEVER falls back to an agency-class PIT (agency tokens 401 for media), and a genuine miss now names exactly which vars and stores it checked and tells the agent to `source ~/.openclaw/secrets/.env` and retry. SOP `v2-autonomous-build-sop.md` gains §2.0.1 (credential preflight + the HARD RULE: real research across all env stores before any `honest_fail`) and a §7.1 forbidden-shortcut row; SKILL.md documents where the LOCATION PIT / location id / KIE key live and the no-false-fail rule. PR #356's B7 SOP sections (§2.05 method-decision, §2.06 theme/colors, §4.1 embed-widget, §7 sealed-mode, §7.1 forbidden shortcuts) are folded in and the PR closed. No secret values committed (env var NAMES only). See [CHANGELOG.md](CHANGELOG.md).
>
> **NOTE (v14.26.0) - fix(presentations): department hardened end-to-end so a deck runs to a finished, complete bundle.** Closes the full presentation-department review. (1) DELIVERY NO LONGER BREAKS: the presenter speech filename is now the plural `PRESENTERS-SPEECH` everywhere (renderer, manifest, master ruleset, tests) — the old singular spelling made a real run die at the final bundle-completeness check; a new mechanical last-mile gate (`delivery_gate.py`) requires the full five-file client package (every destination, not just the PowerPoint) and wires the Director -> Delivery Concierge handoff. (2) REAL TINY-FONT GATE: `build_deck.py` now has a deterministic numeric font-floor rejector (18pt body floor, modular type-scale, 4.5 contrast) with a negative test, and the Typography Architect emits the size tokens the gate reads — not just a vision opinion. (3) RESEARCH WOVEN ACROSS THE WHOLE DECK: research facts/quotes/stats are now mapped to specific slides before copy is written, the copy template carries a "research used here" tag, and a breadth gate REJECTS a deck that leans on one fact on one slide. (4) RENDERER IDENTITY CORRECTED: every guide names the live builder `build_deck.py`/`process_manifest.json`; the retired `render_deck.py` is documented in `docs/LEGACY-RETIREMENT.md`. (5) GOHIGHLEVEL FOLDER CREATED BY SOFTWARE, NEVER A BROWSER: the media folder is created via the verified-working API call (shared `ghl_media.py` `create_media_folder()`), images upload over the API, and driving the GoHighLevel user interface in a browser is explicitly forbidden. (6) PROMPT FLOOR 1,500 -> 5,000 everywhere to match the enforced code floor. (7) Garbled image text is re-generated then escalated to a human — never pasted as a native text box (text is always baked into the image). (8) Presentations added to the owner-task routing table and granted the same protective permission set graphics/video/audio get, so the "no permission" headless stall stops. Lockstep CI (renderer<->ruleset<->manifest<->roles), Guard A (declared==enforced==tested), Guard B (no retired doctrine), the process-gate tests, and the content-manifest all stay green. See [CHANGELOG.md](CHANGELOG.md).
>
> **NOTE (v14.26.0) - feat(full-funnel): one owner sentence -> full live funnel + website + automations (Skill 6 + Skill 44 as one system).** Wires the request -> strategy -> copy -> assets -> built pages/forms/product/tags -> email + CRM automations -> QC -> publish value-stream into the existing AI Workforce (NO new department, NO new role — a wiring + one-orphan-artifact fix). NEW: `SOP-07 — Full-Funnel Build Orchestration` (single owner of the P0->P5 value-stream; full-funnel intent detection in SOP-00 Step 2 hands here; creates a parent `funnel_epic` + 6 staged child cards with `depends_on` edges; `waiting_on_dependency` non-human sub-state that is NOT counted against the 3-bounce cap; routes via `POST /api/tasks/ingest` to the persistent `agent:<dept>`, never inline; `funnel_rollback` on any child FAILED; parent/child idempotency keys). NEW: Funnel Strategist `SOP 9.5` produces the previously-orphaned `funnel-spec.json` (persona-grounded on `hormozi-100m-offers`, writes `persona-selection-log.md`); Chief Sales Officer `SOP 9.9` emits `offer-spec.json`. UPDATE: `persona-selector-v2.py` web-development domain tags widened to include marketing/sales/copywriting/strategy-innovation (so funnel/landing tasks surface the conversion masters), with a matching `A7` row in `test-persona-selector.sh`; Conversion Copywriter `SOP 9.2 Step 0` persona grounding + Gate-1 checkbox; Email Campaign Strategist CRM/Skill-44 handoff + persona grounding; Funnel Builder + Landing Page Specialist Skill-44 downstream handoff line; `v2-autonomous-build-sop.md` P0/P1/P2 pre-flight gates grafted onto the front end; SOP-01 Kanban schema extension (parent_task_id/stage/depends_on/task_type + first-class board handoff events + parent rollup); Skill 6 <-> Skill 44 SKILL.md cross-references both ways. The deployed Command Center owns the actual `mission-control.db` schema/migration; this repo carries the contract. See [CHANGELOG.md](CHANGELOG.md).
>
> **NOTE (v14.26.0) - feat: Presentations department made UNIVERSAL (zero client names) + anti-compression hard gate + deterministic build pipeline shipped.** The entire Presentations role library and the master CLIENT-WEBINAR-DECK-SOP were genericized: every concrete name, niche, price, hook line, logo wordmark, deck title, and number is now an ILLUSTRATIVE EXAMPLE / DISCOVERY VARIABLE the agent substitutes from the live client interview — nothing client-specific is hardcoded (zero client names, enforced by a repo-wide name scan). Anti-compression HARD GATE: the density-floor overhaul replaces the RETIRED "sung at least 7 times" hook FLOOR (which produced 40-slide footer-stamping) with a CEILING of exactly 3 to 4 dedicated pure-typography hook slides at named beats, footer-stamping banned, refrain verbatim; the new AF-COVERAGE-1 / `_chk_coverage` gate plus the AF-DEN density triggers (8-slide gaps, anchor at one-third, BUILDUP before every DROP, value-stack before Drop 1, Wall of Wins before offer, re-pitch after FINAL) enforce real coverage instead of compression. Deterministic render path shipped: `build_deck.py` (single-command, zero-AI-judgement-at-runtime renderer; the agent writes only `slides.json` per `slides.schema.json`), `kie_generate.py`, `test_preflight.py`, plus the English/Latin-only spelling-lock pin appended to every prompt. Process manifest (SOP-SLIDE-05) documents the one mandated flow; the SOP↔Python lockstep detector (`PIPELINE-MANIFEST.json` + `sync_check.py` + SOP-SLIDE-06) fails the build if the SOPs and the scripts drift out of sync. Hook CEILING (not floor), renderer reconciliation, and the Deep Research Specialist twelve-category framework (A-L: fact-validation ledger, quotes, objections, compliance flags, persuasion-framework validation) with `persuasion_intelligence` seeding are all carried in. `_index.json`: presentations dept now 25 roles, total_roles 425. See [CHANGELOG.md](CHANGELOG.md).
>
> **NOTE (v14.26.0) - feat: Content-to-Presentation one-person/general modes + fluff-strip + cover/close + infographic checklist + system-wide deck portable-document export (AF-F11).** The Content-to-Presentation Architect (ROLE-22) now ALWAYS asks, before building, whether a deck is a ONE-PERSON presentation (a personalized deck for a single named recipient) or a GENERAL presentation (designed to be seen by many), and records the answer as the deciding fork for the whole build. Mode-aware privacy reconciles the old blanket hard-zero-names rule: GENERAL strips ALL personal references (full de-identification); ONE-PERSON keeps ONLY the named recipient's identity and strips every other person's personally identifiable information. A signal-vs-fluff extraction step strips chitchat, scheduling talk, and tangents while keeping the main theme, points, decisions, lessons, key concepts, and action items, and captures action items plus key soundbites. One-person decks gain a personalized cover and closing addressed to the recipient. Every content-to-presentation source now names a deliverable bundle (the deck, a Presenter guide in portable-document format, and a one-page infographic checklist of the main points and action items). System-wide (fleet-wide, ALL decks): the PPTX Assembly Specialist now emits a portable-document-format (.pdf) export ALONGSIDE the .pptx via headless LibreOffice (`soffice --headless --convert-to pdf`, with a documented fallback chain), so a recipient without PowerPoint can open the deck; both files are required and verified at the assembly gate (Gate 6) and at the Phase 6 QC gate (new AF-F11). The Director propagates the mode and the bundle into the build. SOPs renumbered/extended cleanly; both SOP mirrors regenerated. See [CHANGELOG.md](CHANGELOG.md).
>
> **NOTE (v14.26.0) - feat: ravenous rising-value-curve - visible climbing value total + escalation rule at every price drop.** Strengthens the EXISTING slow-drop doctrine (the red rule: with every price drop the value must INCREASE) with two refinements that build on AF-C7(c) and the Offer Price Strategist Gate 6, without weakening or duplicating them. (1) VISIBLE RISING-VALUE CURVE: every drop slide (or its successor) now renders a cumulative RUNNING VALUE TOTAL climbing against the struck/falling price, so the audience watches the two lines move in opposite directions (price down, value up) and the widening gap is SEEN, not implied. The Offer Price Strategist records `running_value_total` per rung in offer_stack.json (strictly increasing, reconciled to the dollar so AF-C4 stays clean); the design-system price-typography SOP (Creative Typography Guide 2.5) renders it. (2) ESCALATION RULE: the value added at each drop must be BIGGER and BETTER than the prior rung (a substantive, distinct, named deliverable/bonus/guarantee that lifts the running total by a non-trivial amount); a trivial, restated, or unnamed add now fails. Added as new checkable clauses inside AF-C7 sub-condition (c) and the Offer Strategist Gate 6 (with PASS/FAIL examples), consistent with the AF-SRC discipline (the running total is internal pitch doctrine, not an external-API constant). The RAVENOUS objective is now stated where the doctrine is summarized. Files: SOP-PITCH-01, SOP-PITCH-02, SOP-DESIGN-01, offer-price-strategist (+ mirror), qc-specialist-presentations (+ mirror). See [CHANGELOG.md](CHANGELOG.md).
>
> **NOTE (v14.26.0) - feat: Kie callback Worker (centralized, operator CF) + submitter webhook-primary/poll-fallback.** Skill 46 (kie-callback-relay): one centralized Cloudflare Worker at kie-callback.zerohumanworkforce.com receives all Kie.ai image callbacks, verifies HMAC once, writes to Worker KV. Box-side KV poller + slide submitter updated to submit the full batch first, then wait via KV poll with single-poll Kie fallback. Crash-safe on-disk task registry. Callbacks enabled for decks above 5 slides; smaller decks use efficient batch polling. Skill 07 updated with corrected rate limit citation (20/10s, verified docs.kie.ai 2026-06-14) and callback architecture reference. See [CHANGELOG.md](CHANGELOG.md).
>
> **NOTE (v14.26.0) - feat: Presentation SOP overhaul - 4 new specialist roles, QC expansion, hook cadence, re-pitch choreography, and Design Intelligence Library scope boundary (Skills 23 + 45).** Comprehensive presentation standard upgrade across 14 role/SOP files, the master CLIENT-WEBINAR-DECK-SOP, and Skill 45 DIU. Key changes: ROLE-18 Typography Architect (per-slide type-layout system, hard gate before Slide Image Creator); ROLE-19 Presenters Guide Specialist; ROLE-20 Presenters Speech Writer (TARGET_WPM=140 constant, duration assert); ROLE-21 Audio Demonstration + Fish Audio Expression Specialist (S2-Pro -> ElevenLabs -> Whisper-STT-verify chain). Hook cadence recut from floor-only to a BANDED model (3-4 dedicated A4 hook slides, ceiling ~1 per 6 slides, never 2 consecutive). RE-PITCH block added (4-7 slides after FINAL price). On-slide FORBIDDEN list (narrator copy, AI meta-commentary, scene descriptions, telegraphing kickers, the word "webinar"). New QC criteria c23 (re-pitch required), c24 (close density >= 8 slides on 45+ deck). AF-C7 through AF-C9 and AF-F6 through AF-F9 added. Skill 45 DIU: signature-style friendly aliases (Sig #), style-branch Step 0, image-to-JSON Kie.ai mode documented, SCOPE boundary (webinar decks belong to Presentations dept). _index.json: presentations dept 17 -> 21 roles, total_roles updated to 355. See [CHANGELOG.md](CHANGELOG.md).
> Every release MUST agree across the version-tracked files; run `./scripts/bump-version.sh vX.Y.Z` to update them atomically. Drift is caught in CI (`.github/workflows/version-consistency.yml`).
>
> **NOTE (v14.26.0) — feat: DIU full role set — 13 graphics specialists registered.** Eight remaining Design Intelligence Unit specialist roles (design-producer, style-librarian, likeness-rights-officer, render-dispatcher, asset-provenance-librarian, style-steward, brand-systems-specialist, motion-systems-specialist) added to `_index.json` + ROLE-- files shipped. Graphics dept count 23 → 31, total_roles 323 → 331. All 26 SOP-DIU files present; SOP-DIU id uniqueness verified. See [CHANGELOG.md](CHANGELOG.md).
>
> **NOTE (v14.26.0) — feat: Presentation Department change order v2 + ROLE-16 Healer-Presentations.** Comprehensive P0-P5 presentation pipeline fixes (API contract, doctrine restorations, Hook Lab, Delivery Concierge, Presenter Coach, Capacity/Reliability watchdog), plus ROLE-16 Healer-Presentations added to presentations department. Presentations dept count 15->16, total_roles 281->282. See [CHANGELOG.md](CHANGELOG.md).
>
> **NOTE (v14.26.0) — feat: shared core-file unification (Zero-Human-Workforce file model).** On every box, ALL of an account's agents + sub-agents now SHARE the box's ONE canonical `AGENTS.md` / `TOOLS.md` / `USER.md` via symlink (not duplicated); per-agent `IDENTITY.md` / `SOUL.md` / `MEMORY.md` / `HEARTBEAT.md` stay each agent's own. `link_shared_core_files()` runs at install (`install.sh` Step 10a) and on every update (`update-skills.sh`). Co-mingling guard: the symlink target is always the LOCAL box's own canonical, resolved from that box's own `openclaw.json` — never a cross-box/cross-account path. Nested workflow agents (`*/workflows/*/agents/*`) are exempt. Non-destructive (backups + additive `IDENTITY.md` preservation) and idempotent. QC check 9.9 enforces it. Full rule: [docs/SHARED-CORE-FILES.md](docs/SHARED-CORE-FILES.md). See [CHANGELOG.md](CHANGELOG.md).
>
> **NOTE (v14.26.0) — fix: safe_json_edit validate/rollback guard added (parity with VPS v10.16.49 skills.path fix).** The VPS updater was writing `skills.path` into `openclaw.json` — rejected by OpenClaw 2026.5.x — which aborted the entire VPS updater before writing `.onboarding-version`. Mac updater had no such write but equally lacked a validate/rollback harness. `safe_json_edit()` added as a forward-defense guard for any future direct json edits. See [CHANGELOG.md](CHANGELOG.md).
>
> **NOTE (v14.26.0) — TYP hardening: explicit storage path, pointer format, mandatory no-paste rule.** `01-teach-yourself-protocol` INSTRUCTIONS.md and the full doc (Section 13 + Section 17) now specify the canonical Mac storage path (`~/Downloads/openclaw-master-files/<subfolder>/`), mandatory pointer format (full path + "when to go deeper"), and a non-negotiable no-paste rule: long docs are NEVER pasted into bootstrap files. Shared bootstrap templates (AGENTS.md, TOOLS.md, USER.md, SOUL.md, IDENTITY.md) all carry a short mandatory TYP rule so every agent reads it on session start. TYP skill-version.txt → v6.5.7. Per-release version history lives in [CHANGELOG.md](CHANGELOG.md). VPS (10.16.x) and Mac (10.15.x) sequences remain intentionally independent.>
> **After every release:** `git tag vX.Y.Z && git push --tags && gh release create vX.Y.Z --notes-from-tag` so the GitHub Releases page mirrors the CHANGELOG.

**A complete onboarding package for setting up a fully operational OpenClaw agent on Mac mini or Hostinger Docker VPS.**

**Current Version: v14.27.1** - See [CHANGELOG.md](CHANGELOG.md) for the full per-release history.
The Presentations department ships a deterministic deck-build pipeline: `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/` (`build_deck.py`, `kie_generate.py`, `slides.schema.json`, `test_preflight.py`, `sync_check.py`) plus the slide-craft SOP set in `universal-sops/presentation-slide-craft/` (`PIPELINE-MANIFEST.json`, `SOP-SLIDE-05-PROCESS-MANIFEST.md`, `SOP-SLIDE-06-EXTENSION-AND-SYNC.md`).

This is the **unified repo** for both platforms (PRD 2.1). Platform-specific files live in `platform/mac/` and `platform/vps/`. The `install.sh` auto-detects Mac vs VPS, or accepts `OPENCLAW_PLATFORM=mac|vps`.

> Previously the VPS installer was a separate repo (`trevorotts1/openclaw-onboarding-vps`). That repo will become an archived pointer to this unified one. Do not add new features to the VPS repo.

This repo contains **48 numbered skill folders (01 through 48)** — 43 active plus 5 archived (11, 13, 21, 33, 34) — plus an install script and update script. See the [Skill Inventory](#skill-inventory-folder-names) below for the full live list.

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
| 06-ghl-install-pages | **GHL Install Pages** — browser/REST funnel + page builder. Ships a **38-template funnel library** (`funnel-templates/`, by category) + `funnel_matcher` (STEP 0 in `tools/v2_dispatcher.py`, template-first / guide-not-rule) + the FAB-QC ≥ 8.5 build gate (`qc-built-funnel.sh`). |
| 07-kie-setup | KIE Setup |
| 08-vercel-setup | Vercel Setup |
| 09-context7 | Context7 Setup |
| 10-github-setup | GitHub Setup |
| 11-superdesign-ARCHIVED | SuperDesign (ARCHIVED — replaced by Skill 45 Design Intelligence Library) |
| 12-openrouter-setup | OpenRouter Setup |
| 13-google-workspace-setup-ARCHIVED | Google Workspace Setup (ARCHIVED — replaced by skill 14) |
| 14-google-workspace-integration | Google Workspace Integration |
| 15-blackceo-team-management | BlackCEO Team Management |
| 16-summarize-youtube | Summarize YouTube |
| 17-self-improving-agent | Self-Improving Agent |
| 18-proactive-agent | Proactive Agent |
| 19-humanizer | Humanizer |
| 20-youtube-watcher | YouTube Watcher |
| 21-tavily-search-ARCHIVED | Tavily Search (ARCHIVED — Tavily no longer used; replaced by Skill 03 Agent Browser) |
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
| 38-conversational-ai-system | **Conversational AI System (v14.26.0)** — the conversational AI BRAIN on top of skill 29 (GHL Convert and Flow). 45 protocols (sales brain, intelligent follow-up, dual-mode customer service + support, typed knowledge bases, intelligent routing, weekly + monthly self-tuning, model version freshness, ZHC tag-prefix, F45 geo-qualification, F46 CRM field write, F47 inline smart-FAQ, F49 ZHC Pixel, plus the Round-2 6: F21 multi-tenant isolation, F17 segmentation, F15 proactive outreach, F16 A/B testing, F14 voice/phone, F18 webhook chaining — all default-OFF, etc.). 8 customer journey templates. 68 idempotent OS-aware scripts. 19 references. Sunday 2am + Saturday 11pm + 1st-of-month crons. Skills 05/10/19/29 required as prerequisites. Its `skill-version.txt` versions independently of the repo line. |
| 39-real-estate-playbook | **Real Estate Playbook & Property Intelligence (v14.26.0)** — the real-estate VERTICAL on top of skill 38. Provider-abstraction property intelligence (keyless US Census geocoding + optional Google/Mapbox/RentCast/MLS — honest gap, NEVER fabricated), buyer/seller/investor qualification, showing scheduler (lockbox/MLS rules), 50-state + DC disclosure pointer matrix, lead routing by agent specialty, open-house + pre-foreclosure outreach (pairs with skill 40), and an ADDITIVE Sales-Brain RE extension (RE objections + CMA pricing-reveal timing + SPICED-RE) that drops into skill 38 without editing its own protocol. Emits `real-estate-events.jsonl`. ZHC tags: buyer/seller/investor-lead, pre-foreclosure-prospect. Skill 38 required as prerequisite. |
| 40-zhc-public-records-scraper | **ZHC Public Records Scraper (v14.26.0)** — tiered, compliance-first public-records intelligence and the data sibling of skill 39. address/ZIP → county+state → Tier 1 (curated configs for 21 major counties: Cook, LA, Maricopa, Harris, San Diego, Orange, Miami-Dade, Kings, Dallas, King, Clark, Santa Clara, Tarrant, Riverside, Wayne, Broward, Bexar, Sacramento, San Bernardino, Hillsborough, Pierce) → Tier 2 (platform-adapter framework + Tyler/GovOS example adapters) → Tier 3 (operator-buildable, validated config) → else Tier 4 (HONEST GAP, never fabricated). robots.txt respected, ToS per target, source+timestamp attribution; cost cap + per-day + per-target rate limits with bulk cost confirm; 30-day cache. Emits `public-records-queries.jsonl` (F52 PII-free contract: opaque query_ref/target_ref, record TYPES + counts only). RE use cases (pre-foreclosure/NOD, tax delinquency, comps, permits, tax, ownership). Never runs outreach (that's skill 39). |
| 41-build-with-ai-playbook | **Build With AI Playbook Generator (v14.26.0)** — generates GoHighLevel "Build With AI" conversation playbooks: dependency-ordered build steps, webhook/trigger configuration, prompt-completeness + no-fabrication + no-personal-data + zhc-tag-prefix QC gates (each with a passing negative self-test), and OS-aware (uname -s) install scripts. Templates + protocols for repeatable, verified GHL workflow generation. Installer scripts 00-04 run at client-install time only. |
| 42-personal-assistant-library | **Personal Assistant Library (v14.26.0)** — 29 ready-to-deploy personal-life specialists (inbox, calendar, daily briefing, tasks, meetings, research, brainstorming, coaching, emotional support, travel, finance, relationships, errands, life-admin, spiritual life, motivation, challenger, family, study partner, passion/purpose, clarity, YouTube teacher, goals, superwoman, imposter, therapeutic support, focus, celebration, greatness). Each ships 6 role files (IDENTITY/SOUL/governing-personas/how-to/ROSTER/00-START-HERE) + a DMAIC `SOP/` folder (`PA-NN-NN-slug.md`, consistently named) — 180 role files (Specialist 19 adds 6 sub-specialist role files), 162 SOPs + 29 indexes total. The agent materializes a specialist into `workspace/departments/personal-assistant/<slug>/` on demand and fills `{{TOKEN}}` placeholders from USER.md. Additive to Skill 23 (does NOT modify it); the optional `department-naming-map.json` auto-build patch is deferred to a product decision. Coaching-scope specialists (09/24/26) carry STOP-and-refer crisis protocols. Skill 23 required as prerequisite; Skill 22 recommended (graceful degradation). |
| 43-graphify-knowledge-graph | **Graphify Knowledge Graph (v14.26.0)** — turns the client's OWN workforce/codebase/docs into a persistent, queryable knowledge graph (`graphify-out/`: clickable `graph.html`, god-node `GRAPH_REPORT.md`, `graph.json`). Installs graphify (`uv tool install "graphifyy[all]"`), registers the OpenClaw skill (`graphify install --platform claw`), maps the workforce ONCE using the CLIENT'S OWN model (`deepseek-v4-pro:cloud` via their Ollama — NEVER the operator's keys), installs the FREE AST auto-rebuild hook (`graphify hook install`), and wires `/graphify` (query/path/explain) so the agent reaches for the graph FIRST on "how is this wired / what depends on what" questions. **Two tiers:** the heavy semantic pass is on-demand (owner-triggered); the AST rebuild is free + automatic on every commit. Carries the binding NO-COMINGLING rule. Additive — modifies no other skill; versions independently via its own `skill-version.txt`. |
| 44-convert-and-flow-operator | **Convert and Flow Operator (v14.26.0)** — Tier 0 GoHighLevel operator: the Convert and Flow CLI (`caf`/`convertandflow`/`ghl`) gives the agent direct CRM access for contacts, opportunities, calendars, conversations, documents, payments, forms, social, locations, and workflow builds via internal API (no MCP overhead). Standard ops run on the Private Integration Token alone; workflow writes additionally require the Firebase refresh token, falling through to Tier 4 agent-browser when absent. Write-safe by default (dry-run, draft-only, location whitelist, approval gate). Ships a **28-template automation/email library** (`automation-templates/`, by category) + `automation_matcher` (Step 0.4, shared `flex.py` core) + the **funnel↔automation link map** (`_links/funnel-to-automation.json`) + the FAB-QC ≥ 8.5 overlay (`qc-built-workflow.sh --fab`). |
| 45-design-intelligence-library | **Design Intelligence Library (v14.26.0)** — Design Intelligence Unit (DIU): self-contained image-style analysis and generation system. 13 specialist roles (style-analyst, deck-systems-specialist, generation-operator, photo-shoot-director, fidelity-tester, design-producer, style-librarian, likeness-rights-officer, render-dispatcher, asset-provenance-librarian, style-steward, brand-systems-specialist, motion-systems-specialist) + extended Brainstorming Buddy — Graphics + Chief Design Officer gatekeeper integration. Ships 26 SOP-DIU files, 12-dimension style analysis protocol, style-card library (3 prompt tiers SHORT/MEDIUM/LONG), Style Rotation Engine for deck generation, personal photo shoot mode with identity-lock guarantees, fidelity-test protocol (≥4.0 avg, 3-strike escalation), and routes across 7 image-generation endpoints. Skill 07 (Kie.ai) prerequisite. |
| 46-kie-callback-relay | **Kie.ai Callback Relay (v14.26.0)** — centralized Cloudflare Worker that receives Kie.ai image-generation callbacks for the entire operator fleet, verifies the HMAC signature once, and writes verified results to Worker KV. Client boxes poll the Worker KV endpoint instead of Kie's status API. Implements webhook-primary with a single-poll fallback and a crash-safe on-disk task registry. Applies to large decks above the configurable threshold. |
| 47-movie-producer | **Movie Producer — Automated Video Production (v14.26.0)** — autonomous multi-pipeline video production for the `video` department. Clones the open-source OpenMontage agentic video engine on the client box at install (AGPLv3 operated as an installed client skill; source never vendored into this template), runs `make setup`, and fail-loud pre-flights the runtime dependencies (FFmpeg, Node ≥18, `npx hyperframes`, Piper). Ships free documentary-montage from a public-domain real-footage corpus (Archive.org / NASA / Wikimedia / Library of Congress / NOAA / ESA / JAXA / Pond5, zero-key, ~$1 budget cap) plus a Kie.AI generative path: two adapter tools route ALL image generation through `gpt-image-2-image-to-image` and ALL video generation through `gemini-omni-video` / `veo3_fast`, gated on the client's own `KIE_API_KEY` so native paid providers stay unavailable. Free render engines (FFmpeg / Remotion / HyperFrames) and Piper free TTS are preserved. Multi-SOP set: a Rule-Zero/budget SOP, per-pipeline-type SOPs (documentary-montage / short-form / VSL), and a cross-role-handoff SOP — announce provider + model + estimated cost before any paid call, `budget.mode: cap`, `ffprobe` validates every MP4. Powers the Movie Producer (Automated Video Production) role (registered slug `automated-video-production-specialist-openmontage`); hands off captions to Skill 26 and premium TTS to Skill 30. Skill 07 (Kie.ai) prerequisite for the generative path. |
| 48-facebook-ad-generator | **Facebook & Instagram Ad Generator (v14.26.0)** — autonomous creative assembly line for the `paid-advertisement` department. Turns two client documents (a show/product bio + an audience profile) into a finished batch of **10 Facebook + Instagram ads**: ~70 overlay lines → a human **pick-10** → 10 ad bodies + 10 headlines + 10 image prompts → 10 square 1500×1500 images via Kie.AI `gpt-image-*` with text **baked into the image** (version-accepting regex `^gpt-image-[0-9]+` auto-adopts future gpt-image versions, gated on the client's own `KIE_API_KEY`) → a verified PLAI-shape audience-targeting brief (fabrication auto-fails; degrades to `flagged-unverified` so the package still ships) → GoHighLevel-hosted public image links (`ghl_media.py` + new `create_media_folder()`) → a copy-paste ad-text doc (Notion → Google Doc → plain text; headline + body as separate paste blocks) → a **PLAI-ready** handoff package (PLAI is the only ad path; no direct Meta API). Mirrors Skill 47's bulletproof spine: a single source-of-truth manifest (`universal-sops/fb-ad-craft/AD-PIPELINE-MANIFEST.json`), a dependency-**MAP** foreman (`ad_director.py` — S2/S3/S4 parallel after pick-10, S6 after S2+S3, S7 after S5+S6), a Python gate-and-attest enforcer (`ad_build_check.py`), a 37-autofail QC ruleset, lockstep CI (`ad-pipeline-lockstep.yml`), and GOOD/BAD fixtures. Money safety = up-front estimate ≤ ceiling + cheap LOCAL running tally that stops before crossing + one balance preflight; unique run-id no-double-charge ledger (`ad_run_ledger.py`); two **non-skippable** human gates (pick-10, approve); independent QC (grader ≠ maker, avg ≥ 8.5, no category < 7). 2 new role seats (Facebook & Instagram Ad-Run Producer + Direct-Response Ad Copywriter) plus 6 reused seats. Skill 07 (Kie.ai) prerequisite for image generation. |
**Total: 48 numbered skill folders** (01 through 48) — **43 active + 5 archived** (11, 13, 21, 33, 34). This matches the live tree on `main`.

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
