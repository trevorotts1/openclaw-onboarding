# Changelog - kie-setup

All notable changes to this skill wrapper are documented here.

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

