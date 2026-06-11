# Skill 44 — Convert and Flow Operator: QC Checklist

The authoritative automated validator is `qc-convert-and-flow.sh`. This file is the
human-readable companion checklist. All items below are machine-asserted by the script.

---

## Section A: Installation

- [ ] `caf doctor` exits 0 (all checks green; Firebase WARN is acceptable)
- [ ] `caf` resolves on PATH inside the openclaw gateway
- [ ] `convertandflow` and `ghl` aliases resolve (symlinks present)
- [ ] venv exists at `~/.openclaw/tools/convert-and-flow-cli/.venv` (Mac) or `/data/.openclaw/tools/convert-and-flow-cli/.venv` (VPS)

## Section B: Credentials

- [ ] `GOHIGHLEVEL_API_KEY` is set and starts with `pit-`
- [ ] `GOHIGHLEVEL_LOCATION_ID` is set
- [ ] Canonical env mapping: wrapper passes `GHL_API_KEY` to engine (verify `caf contacts list --limit 1` returns data)
- [ ] Firebase token: present = PASS; absent = WARN (not FAIL)
- [ ] `GOHIGHLEVEL_DRAFT_ONLY=true` is set (write safety default)

## Section C: Standard ops

- [ ] `caf contacts list --limit 3` returns real contacts
- [ ] `caf workflows list` returns the workflow list
- [ ] `caf locations get` returns location info

## Section D: Write safety

- [ ] `--dry-run` flag recognized (does not fire live API call)
- [ ] Location whitelist enforced (cross-location write rejected)
- [ ] Snapshot dir exists at `~/.openclaw/tools/convert-and-flow-cli/data/snapshots/`
- [ ] Internal-write lock file mechanism present

## Section E: TRINITY and self-test

- [ ] `qc-trinity-registry.sh` called for any conversational build (hard gate)
- [ ] `24-self-test-hook.sh` invoked post-build for brain-containing workflows
- [ ] Self-test credential read alias-aware: accepts `GOHIGHLEVEL_API_KEY` OR `GHL_PRIVATE_INTEGRATION_TOKEN`

## Section F: Core files

- [ ] CORE_UPDATES.md sentinel `<!-- skill:44-convert-and-flow-operator:core-update-applied -->` present in AGENTS.md
- [ ] AGENTS.md has Tier 0 mention and disclosure format reference
- [ ] TOOLS.md has caf/convertandflow wrapper entry
- [ ] MEMORY.md has install record

## Section G: Platform overlay

- [ ] Platform overlay frontmatter `name: convert-and-flow-operator` matches SKILL.md
- [ ] Mac overlay: auto-re-grab recipe present in platform/mac/recipes/

## Section H: QC scope flags (document for Opus QC)

- Criterion 8 grep for old Rule 16 wording EXCLUDES historical CHANGELOG.md entries.
- Criterion 13/17 skill-35 grep EXCLUDES intentional deprecated-name guardrails in INSTALL.md/QC.md/qc-*.sh.
- Criterion 18 media test asserts `url` field non-empty/openable — does NOT hardcode CDN host.
- Criterion 11 Tier-2 de-registration was gated on context-overhead measurement: SHIP decision (see skill 36 CHANGELOG v1.1.0).
