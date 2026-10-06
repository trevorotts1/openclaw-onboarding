# Changelog - kie-setup

All notable changes to this skill wrapper are documented here.

---

## [v7.0.5] - 2026-10-05 - Canonical KIE common rules

### Added
- Synchronous-model note, price and success-rate endpoints, N40 citation and full N43 restatement in the common rules.
- `references/kie-common-rules.md`: single source of truth for KIE authority order, endpoints, rate limits, polling, prompt caps, credit preflight, prices, retention, keys, model ids and the N43 image pin.
- Rule 13, GPT Image auto-latest default: the fleet image default follows the newest GPT Image generation (today 2.5 sunburst); rule 11 reworded to match.
- Rule 12, prompt length budget: write descriptive prompts at 95 to 100 percent of the model maxLength, never below 80 percent; supersedes the 9,000 to 19,000 house band.

---

## [v7.0.4] - 2026-10-05 - fix: dead KIE endpoints, key printing, version drift, retention prose

### Fixed
- Dead Veo status path: `GET /api/v1/veo/task` replaced by `GET /api/v1/veo/record-info` in `INSTRUCTIONS.md` (table, Veo section, status section; added a note that Veo status uses numeric flags 0 generating / 1 success / 2 or 3 failed), `EXAMPLES.md` (Example 4 and Common Mistake 2) and `kie-setup-full.md` (endpoint table). Live probe 2026-10-05 (known-good and fake-path controls): GET /api/v1/chat/credit, POST /api/v1/jobs/createTask, GET /api/v1/models and GET /api/v1/veo/record-info answered; /api/v1/account/balance, /api/v1/user/credits, /api/v1/jobs/create and /api/v1/veo/task returned HTTP 404.
- Dead credit endpoint: `PREREQS.json` (`kie-credits` manual note) named `GET /api/v1/account/balance`; it now names `GET https://api.kie.ai/api/v1/chat/credit` and tells the checker to read the response BODY (`{code,msg,data:<number>}`), not just the HTTP status. `INSTALL.md` Test 2, `INSTRUCTIONS.md` and `QC.md` now also say to check the body `code`. `qc-kie-setup.sh` previously treated any JSON containing `code` or `data` as "kie.ai API responds" (a 401 body qualified); it now requires `"code":200`.
- Secret printing: `QC.md` told the agent to mask-print the first 10 characters of `KIE_API_KEY`. It now uses the presence-only SET / NOT-SET check already used by `INSTALL.md` and `qc-kie-setup.sh`, and says never to print any character of the key.
- Version drift: `SKILL.md` carried only a nested `metadata.version` of 6.7.0 while `skill-version.txt` said v7.0.3, and the repo frontmatter gate skipped it. `SKILL.md` now has a top-level `version: v7.0.4` (nested value rolled to 7.0.4), so the gate checks it.
- Retention: Result retention prose now reads: KIE documents 14 days for generated media but its task-detail page says result URLs typically expire after 24 hours; download/persist immediately. Edited in `SKILL.md`, `INSTALL.md`, `INSTRUCTIONS.md`, `EXAMPLES.md`, `CORE_UPDATES.md`, `wire.sh` and `kie-setup-full.md`.

### Migration Notes
- `CORE_UPDATES.md` and the `wire.sh` TOOLS block changed (retention line). Existing boxes should re-run `bash wire.sh` (idempotent, replace-in-place).
- The prebuilt `kie-setup.skill` archive was not regenerated here.
- Risk level: LOW (documentation, one QC check, one prereq note).

---

## [7.0.0] - 2026-08-26 - Modernize KIE provider router, callback policy, and core wiring

### Changed
- Narrowed 07-kie-setup to canonical KIE provider/setup/router skill (credential management, generic Market API rules, dedicated API families, callback/polling policy, rate limits, retention).
- Removed stale 5-model table from INSTRUCTIONS.md; routing and model matrices now owned by dedicated modality skills 66-kie-image (image), 67-kie-video (video), 68-kie-audio (audio).
- Removed hardcoded model counts from CORE_UPDATES.md ("19 video, 19 image").
- Added idempotent `wire.sh` matching Skill 63/64 marker pattern (`<!-- BEGIN/END skill:07-kie-setup:<target> -->` and sentinel `<!-- skill:07-kie-setup:core-update-applied -->`). Existing boxes should re-run wiring (core-file block changed).
- Updated SKILL.md version metadata to 6.7.0 and skill-version.txt to v6.7.0.

---

## [v6.6.2] - July 10, 2026

### Changed
- Model-default guidance now scopes Nano Banana Pro to GENERAL/standalone image
  work and states explicitly that DEPARTMENT pipelines override it and pin their
  own model. Calls out the Presentations department as GPT-Image-2 ONLY
  (`gpt-image-2-text-to-image` / `gpt-image-2-image-to-image`), so the cross-skill
  model collision that caused deck renders to substitute Nano Banana Pro
  (AF-MODEL-SOVEREIGNTY) can no longer be read as sanctioned.

---

## [v1.5.0] - March 7, 2026

### Changed
- Converted INSTALL.md to agent-executable, autonomous execution format.
- Ensured TYP guardrails are present: MANDATORY TYP CHECK, CONFLICT RULE, and TYP file storage instructions.

## [v7.0.0] - 2026-09-03 - v23 major generation bump: no behavior change, version roll only

No functional changes. Version advanced to the next major generation alongside the v23.0.0 repo release.
