# Changelog — sales-page-assets (Skill 56)

All notable changes to this skill are documented here.

---

## [1.0.2] - 2026-07-05 — fix(Copy routing): baked-prompt hygiene + manifest

### FIX-COPY-04(iii) — junk baked prompts archived; runtime iterates a manifest
- Archived the two legacy non-runtime stubs `prompts/baked/13-test-prompt-airtable-mcp-demo.md` and
  `prompts/baked/14-empty-record.md` to `prompts/baked/_archive/` (an Airtable MCP test stub and an
  empty Airtable record — never real generation prompts).
- Added `prompts/baked/_index.json` — the canonical ordered manifest of the **12 active** runtime
  prompts. The runtime iterates this manifest instead of globbing the directory, so a stray/junk `.md`
  is never silently picked up.
- `prompts/PROMPT-SEAMS.md` updated to reflect the 12-active / 2-archived split.

No generation behavior changed; the 12 active prompts and their provers are unchanged.

---

## [1.0.1] — prior

Initial hardened release (canonical fail-closed entry, deterministic provers, signed
PROCESS-CERTIFICATE, golden reproduce). See `SKILL.md` and `verify.sh`.
