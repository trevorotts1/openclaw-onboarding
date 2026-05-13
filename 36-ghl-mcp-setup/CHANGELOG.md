# Changelog - ghl-mcp-setup (Skill 36)

All notable changes to this skill are documented here.

---

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
