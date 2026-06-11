# Changelog - ghl-mcp-setup (Skill 36)

All notable changes to this skill are documented here.

---

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
