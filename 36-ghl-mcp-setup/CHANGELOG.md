# Changelog - ghl-mcp-setup (Skill 36)

All notable changes to this skill are documented here.

---

## [v1.2.10] - 2026-07-05 — Command Center emit helper (fail-soft) + Tier-0 presence-check path fix

### Added (FIX-S36-01)
- `scripts/cc-task.sh` — a graceful-degrading Command Center Kanban helper (modeled byte-for-byte
  on Skill 38's `scripts/cc-task.sh`) that IMPLEMENTS the previously doc-only "emit" moments in
  INSTRUCTIONS.md. `start` creates-or-reuses the Skill-36 install card and moves it to
  `in_progress`; `review` moves it to `review` on QC pass. It never self-grades review→done (the
  independent CC auto-scorer is the only authority) and never fails the caller — with no
  `MC_API_TOKEN` / unreachable board it prints one operator-only stderr note and exits 0.
- Wired: `INSTALL.md` Autonomous Setup Execution (new Pre-Action 0.5) invokes
  `cc-task.sh start … || true`; the `qc-ghl-mcp-setup.sh` PASS branch invokes
  `cc-task.sh review || true`. INSTRUCTIONS.md's "Command Center hooks" section now names the
  helper as the implementing mechanism (config: `MC_API_TOKEN`, `MISSION_CONTROL_URL`, optional
  `MC_SKILL36_AGENT_ID` / `MC_SKILL36_SOP_ID`).

### Fixed (FIX-S36-02 — qc-ghl-mcp-setup.sh)
- Section H Tier-0 presence check no longer looks in a **sibling of** master-files
  (`$(dirname "$MASTER_FILES_DIR")/44-…`), which never matched → the Tier-0 `caf` asserts
  silently downgraded to warn-only on every real box. Now checks
  `$MASTER_FILES_DIR/44-convert-and-flow-operator` **OR** `$SKILLS_DIR_DEFAULT/44-convert-and-flow-operator`
  **OR** `~/.openclaw/tools/convert-and-flow-cli`, so an installed Skill 44 is actually detected and
  the `caf` PATH / `caf doctor` checks assert (not warn) as intended.

---

## [v1.2.9] - 2026-07-05 — fix: secret-printing greps → existence-only (FIX-XC-07); model prescription → cheapest non-metered on-box (FIX-XC-09g)

### Security (FIX-XC-07 — no secret VALUES in transcripts/logs)
- `INSTALL.md` Pre-Action 2 credential hunt: every credential check is now EXISTENCE-ONLY.
  The canonical/legacy secrets-file scans became per-key `grep -qE '^(export )?KEY=' && echo "KEY=SET"`
  loops; the live-env and home-dotfile scans strip the value with `cut -d= -f1` BEFORE grep (key NAMES
  only); the repo/master-files scans use `grep -rilE` (matching FILE names only); the config env.vars
  Python prints `{name}=SET` instead of a truncated value.
- `ghl-mcp-setup-full.md` Section 1 discovery block: same treatment — per-key existence loop, `cut`-first
  name-only live/dotfile scans, `grep -rilE` file-name-only repo/master-files scans, and a names-only
  config Python block. No check prints a secret value anymore.

### Changed (FIX-XC-09g — no hardcoded model prescription)
- `SKILL.md` "Critical Things to Know" item 10 and `INSTRUCTIONS.md` anti-pattern: replaced the hardcoded
  `deepseek-v4-flash (direct)` lookup-inference prescription with "the cheapest non-metered model
  configured on THIS box" + a provider preflight (inspect the client's configured model list and pick the
  lowest-cost free/local model they genuinely have — never hardcode a specific model id, since provisioned
  providers differ per box).

### Notes
- Repo-level: a new deterministic shipped gate `scripts/qc-assert-no-secret-printing-grep.sh`
  (wired into `qc-static.yml`) fails any secret-pattern grep in the 36/38 SOPs that lacks `-q`/`-l`/`-L`.

## [v1.2.8] - 2026-07-05 — docs: Command Center card moves to review, never done (board review-skip root fix)

### Changed (FIX-XC-01b — Command Center card moves to review, never done)
- `INSTRUCTIONS.md` "Command Center hooks" — the **Install complete** hook now moves the card to
  **review** (never straight to `done`), with the QC result as the note ("certified — awaiting QC
  promotion; …"). A producer never self-promotes to `done`: the independent auto-scorer is the ONLY
  authority that moves a card `review -> done`. Prose carrier for the shared `mc_board` review-skip
  root fix (FIX-XC-01b); aligns Skill 36 with Skill 6's `cc_board`, Skill 41's `cc_move_task`, and the
  Skill 32 move-task Done-Gate.

## [v1.2.7] - 2026-07-01 — docs: GHL PIT alias cross-ref + canonicalize-once guidance

### Changed
- `SKILL.md` gains the GHL PIT-aliases banner (cross-ref to `TERMINOLOGY.md`'s 11-alias canonical
  set) and an expanded "Aliases" section lead-in stating the GHL = Convert & Flow = Go High Level
  platform identity.
- Item 5 under "Critical Things to Know" rewritten: Tier 1 now explicitly sends `Authorization:
  Bearer $GOHIGHLEVEL_API_KEY`; Tier 2's `GHL_API_KEY` env var is documented as one of the 10
  aliases the unified resolver normalizes to `$GOHIGHLEVEL_API_KEY` — with a "canonicalize once at
  session start, never re-resolve mid-session" rule that points at skill 29's 11-alias resolver.

---

## [v1.2.6] - 2026-06-30 — Tier 2 fork pinned to a verified commit SHA; QC script bug-fixes; stale full-doc/QC.md reconciled; runtime missing-cred grace; disclosure scoped operator-only; Command Center hooks

### Fixed (qc-ghl-mcp-setup.sh)
- **BUG-1:** `$URL` was used by the Tier 2 `/tools` assert one line BEFORE its own assignment → `URL: unbound variable` under `set -u` → spurious Section D FAIL every run. URL is now resolved at the top of Section D, before any use.
- **BUG-2:** the URL capture was `URL=$(command -v openclaw && openclaw config get ...)`, which prepended the `openclaw` binary path onto the URL → all Tier 2 probes hit a broken URL → spurious FAIL. `openclaw` presence is now guarded by a separate `command -v` test.
- **BUG-3 / D5-ii:** the VPS service check was `systemctl is-active ghl-mcp` only, which FAILS on a Hostinger Docker VPS (no systemd) even when pm2 correctly runs the server. Now checks `pm2 jlist | grep ghl-community-mcp` first, systemd as fallback.
- Tool-count asserts are now range-based: Tier 1 `>= 36` (was exact `= 36`), Tier 2 `>= 500` — so a single GHL tool add/remove no longer trips QC.

### Changed (pin the Tier 2 community fork — reproducibility / drift protection)
- `INSTALL.md` §5.2 and `ghl-mcp-setup-full.md` §6.2 now clone the BusyBee3333 fork and `git checkout` a **pinned commit** (`GHL_MCP_PIN_SHA=3dd9006ac5242762612e6d22b9a51a0a17aeca79`, 2026-05-15) instead of tracking `main`. That commit is the state this skill was verified against (`package.json main=dist/main.js`, `src/main.ts:55` PORT-before-MCP_SERVER_PORT precedence, `GET /health`+`GET /tools`+`POST /execute`). `main` HEAD (2026-06-11+) adds `mcp-apps` / an "easy setup" flow / a curated tool-profile that changes the default `/tools` surface; a re-run now re-pins instead of drifting. Bumping the pin requires re-running the QC script.
- Verified `ghl_create_workflow` / `ghl_update_workflow_actions` DO exist in the fork (`src/tools/workflow-builder-tools.ts` + `workflow-builder-client.ts`) but wrap an undocumented internal endpoint and remain unverified/likely non-functional — hardened the Tier 2 Workflows row (INSTRUCTIONS.md) and GHL-LOOKUP-SOP.md RULE 6 so they are never mistaken for a build path (build stays Tier 0 / Skill 44 Build API).

### Fixed (reconcile the stale long-form reference to the post-v1.1.0 canonical model)
- `ghl-mcp-setup-full.md`: §6.7 no longer instructs `openclaw mcp set ghl-community-mcp` — Tier 2 is documented as ON-DEMAND curl (not registered in `mcp.servers`), matching INSTALL.md §5.7, wire.sh M2, and qc.sh. §8.1 flipped to "SOUL.md — NO UPDATE NEEDED" (the Tier Escalation Protocol lives in AGENTS.md); §8.2 tier order gains Tier 0, marks Tier 2 on-demand, and Tier 4 = agent-browser-first; §8.4 MEMORY.md, the master checklist, and §11.A QC items flipped off the "Tier 2 registered" / "add to SOUL.md" / exact-count claims.
- `QC.md`: file manifest corrected to the real 14 package files (was "10"); "ghl-community-mcp registered" → "NOT registered (on-demand)"; "SOUL.md contains the protocol" → "AGENTS.md contains it; SOUL.md unchanged"; platform detection and VPS supervisor descriptions corrected (uname; pm2-first).
- `ghl-mcp-setup-full.md` §6.5 launchd plist + §6.6 systemd unit now pin BOTH `PORT` and `MCP_SERVER_PORT` (the supervision fix already in INSTALL.md); §6.6 notes pm2 is the canonical VPS supervisor.

### Fixed (D5-i — quoted-tilde platform detection in the full doc)
- Replaced `if [ -d "~/.openclaw" ]` (tilde does not expand inside quotes → always "desktop") with `uname -s` detection at all four sites, and switched the broken quoted-`"~/..."` path assignments to `$HOME/...`. Removed two dead quoted-tilde entries from the master-files locator ROOTS array.

### Added (runtime grace + silence + Command Center)
- **Runtime missing-credential grace** (GHL-LOOKUP-SOP.md RULE 5 + CORE_UPDATES.md token-routing): an empty `GOHIGHLEVEL_API_KEY` / `GOHIGHLEVEL_LOCATION_ID` at runtime now BLOCKS with a named, client-facing remediation (how to create the PIT + find the Location ID), mirroring the Firebase-token nudge — never a silent no-op. (A 429 still STOPs and surfaces the reset time; it does not ask for credentials.)
- **Disclosure header scoped OPERATOR-CHANNEL ONLY** (INSTRUCTIONS.md + CORE_UPDATES.md): the `[GHL tier used: N — tool]` header is the operator's audit trail and MUST be stripped from client-facing replies (WE MOVE IN SILENCE).
- **Command Center hooks** (INSTRUCTIONS.md): skill 36 emits status to Skill 32's existing board ingestion at install start/complete and on tier incidents (429 lockout, missing credential) — best-effort, operator-only, no parallel board (uses Skill 32's documented ingestion; skipped if Skill 32 absent).

## [v1.2.5] - 2026-06-21 — Tier 4 realigned to agent-browser-first; page/funnel building delegated to Skill 06 (no parallel path)

### Changed
- `ghl-mcp-setup-full.md` Tier 4 section: PRIMARY browser engine is now **agent-browser** (Vercel Labs, Skill 03), headless + isolated `--session`; Playwright is the scripted fallback only (still `launchPersistentContext`, never `launch()`).
- Removed the stale **"Browser MUST be Playwright + Kimi K2.5 model"** line (no longer the primary path).
- Auth now prefers the seeded Firebase refresh token (logged-in session, no typing); `GHL_AGENCY_EMAIL` / `GHL_AGENCY_PASSWORD` documented as fallback only.
- Login URL corrected to the white-label **root** (the login form mounts at `/`, not `/login`).
- **Funnel / Website / Page building is explicitly owned by Skill 06 (`ghl-install-pages`)** — points at Skill 06's `ghl-browser-builder-full.md` (v3.0) + `tools/`; no parallel page-builder path is maintained in Skill 36.

## [v1.2.1] - 2026-06-11 — 5-tier → 6-tier label sweep (Tier 0 = Skill 44) across QC/INSTRUCTIONS/full doc

### Fixed
- Four stale "5-tier" labels survived from before Tier 0 (Convert and Flow CLI, skill 44) became the PRIMARY first stop; SKILL.md/INSTALL.md/CORE_UPDATES.md already said 6-tier, but these lagged. Corrected — no behavior change, the routing logic was already 6-tier:
  - `QC.md` §1 Purpose — "5-tier" → "6-tier" with Tier 0 named.
  - `INSTRUCTIONS.md` intro — "5-tier" → "6-tier"; the preference-order sentence now leads with Tier 0 (Convert and Flow CLI, skill 44).
  - `ghl-mcp-setup-full.md` §"access chain you are setting up" — added the missing **Tier 0 row** to the chain table (it only listed Tiers 1-5); header + "try in numerical order" rule updated to start at Tier 0; Tier 4 corrected to agent-browser-first per the canonical SKILL.md.
  - `ghl-mcp-setup-full.md` §8 Phase 7 heading — "5-TIER CHAIN" → "6-TIER CHAIN".

## [v1.2.0] - 2026-06-11 — GHL_AI_LAYERS cross-reference added; MCP scope clarified vs Build API

### Why
The 6-tier chain (Skill 36) installs GHL MCP access. Multiple operators conflated the
MCP tier (read/write contacts, conversations, calendar via public API) with Skill 44's
internal Build API (workflow create/edit). GHL_AI_LAYERS.md now documents the full
picture; Skill 36 cross-references it so operators reading the tier chain know MCP and
the Build API are orthogonal surfaces.

### Changes
- Cross-reference to `38-conversational-ai-system/references/GHL_AI_LAYERS.md` added to
  SKILL.md and INSTRUCTIONS.md with a one-line clarification: "MCP tools (Tiers 1-2)
  cover contacts/conversations/calendar/tags reads and writes. They do NOT build GHL
  workflows. Workflow builds use Skill 44's internal Build API (Tier 0) or the
  Build-with-AI manual paste. These are orthogonal surfaces. See GHL_AI_LAYERS.md."
- skill-version.txt bumped to v1.2.0.

## [v1.1.1] - 2026-06-11 — SOUL.md tier-protocol removal regex fix (D-1)

### Changes
- wire.sh SOUL.md tier-protocol removal regex now matches header suffix variants (D-1).

## [v1.1.0] - 2026-06-10

### Skill 44 era — 6-tier overhaul (edits a-m)

- Added Tier 0 (Convert and Flow CLI, skill 44) as the new first stop in the access chain across all files. 6-tier chain replaces 5-tier throughout SKILL.md, INSTALL.md, CORE_UPDATES.md, INSTRUCTIONS.md, qc-ghl-mcp-setup.sh.
- SOUL.md section flipped to NO UPDATE NEEDED; GHL Tier Escalation Protocol relocated to AGENTS.md (operating law, not identity). QC assertions updated accordingly (Section E + new Section H).
- Appendix-B tier table with Owning skill column written into CORE_UPDATES.md AGENTS.md block.
- Token-aware routing rule and 429/rate-limit carve-out added to AGENTS.md block.
- Disclosure header format gains Tier 0 examples; AGENTS.md disclosure line updated.
- Anti-patterns block gains two Tier-0-skip entries (CORE_UPDATES.md + INSTRUCTIONS.md).
- Tier 2 (Community MCP) changed to ON-DEMAND via curl — no native mcp.servers registration. Context overhead measurement: 588 tool schemas in standing context added ~18k tokens per session on representative workloads; decision = SHIP the de-registration. QC Section D assertion flipped to assert NOT registered + service responds on /tools.
- Tier 4 updated to agent-browser-first (skill 03) in INSTRUCTIONS.md + CORE_UPDATES.md.
- Skill 35 cross-reference corrected: skill 35's 15+6 pipeline is exempt from tier routing; only AD-HOC interactive requests follow the chain (SKILL.md + INSTRUCTIONS.md).
- wire.sh added with migration units M1 (SOUL relocation), M2 (Tier 2 de-register): marker-bounded, backed up, idempotent.

## [v1.0.0] - May 13, 2026

### Initial Release

- **New skill 36** that installs the 5-tier GHL access chain
- **Tier 1:** Official GHL MCP registration via `openclaw mcp set ghl-mcp` — 36 tools, stateless protocol
- **Tier 2:** Community GHL MCP (BusyBee3333 2026 fork) — 588 tools across 44 categories including Voice AI, Phone System, Agent Studio, Proposals
- **`$GHL_COMMUNITY_MCP_URL` env var** added to prevent port-hardcoding failures
- **launchd plist (macOS)** OR **systemd unit (Linux/VPS)** lifecycle — no Docker dependency
- **Platform auto-detection** — single skill, same files in both Mac and VPS repos, conditional logic inside for `/data/...` vs `~/...` paths
- **🔴 Tier Escalation Protocol** added to SOUL.md as cardinal behavioral rule
- **Canonical state block** added to AGENTS.md to override stale session memory
- **Tier-skip enforcement** with named anti-patterns from documented past failures (2026-05-12: skipping Tier 2 for products; hardcoded port 8000)
- **Disclosure header protocol** — every GHL response must prefix with `[GHL tier used: N — tool_name]`
- **20-assertion QC script** (`qc-ghl-setup.sh`) covering platform detection, credentials, both MCPs, core file wiring, and security
- **Cross-references** to skills 05 (foundation), 29 (Tier 3 reference), and 35 (which now routes through MCPs first)
- **Credential canonical path migration:** moved from `~/clawd/secrets/.env` (legacy skill 05 location) to `~/.openclaw/secrets/.env` (current AGENTS.md canonical)
