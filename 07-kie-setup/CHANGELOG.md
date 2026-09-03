# Changelog - kie-setup

All notable changes to this skill wrapper are documented here.

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
