# Changelog - kie-setup

All notable changes to this skill wrapper are documented here.

---

## [v7.1.0] - 2026-10-06 - feat: Skill 74 dependency, adapter health in QC, common rules pointers

- `PREREQS.json` (Rule 16 shape): new `skill-74-kie-live-adapter` entry, severity optional (Skill 74 itself requires Skill 07, so a required entry here would be circular; 66, 67 and 68 fall back to static tables when it is absent).
- `qc-kie-setup.sh`: checks the adapter is present and that `health --json` runs and names `74-kie-live-adapter`, hermetically (placeholder key, dead localhost port, nothing leaves the machine); checks `references/kie-common-rules.md` exists; `KIE_QC_OFFLINE=1` skips the live credit probe.
- `SKILL.md`, `INSTRUCTIONS.md`, `QC.md` point to `references/kie-common-rules.md` as the single source of truth and describe the 66/67/68 flow (validate, preflight, submit via Skill 74, then QC).
- `references/kie-common-rules.md`: removed the "lands in a follow-up change" notes (Skill 74 v1.1 is in this branch's base).
- Merged PR #1497 (common rules); its v7.0.5 entry is kept below under a distinct heading. Version roll to v7.1.0.

---

## [v7.0.6] - 2026-10-05 - fix: price figures marked as historical snapshots; kie-setup-full.md sweep

### Fixed
- Swept `kie-setup-full.md` (all 6,447 lines read in chunks) for: a dashed Seedream model id used as a model id (none; the file uses `seedream/4.5-edit` and `seedream/4.5-text-to-image`), the dead endpoints `/api/v1/account/balance`, `/api/v1/user/credits`, `/api/v1/jobs/create`, `/api/v1/veo/task`, `/api/v1/video/generate` (none remain; the one `veo/task` was fixed in v7.0.4), and hard-coded prices presented as authoritative (many). The file carries dozens of per-model dollar figures from the 2026-08 research pass. Rather than rewrite each vendor quote, a notice was added under "FULL API REFERENCE BELOW" saying every dollar figure is a historical snapshot and giving the live sources: `GET /api/v1/models` (`pricingDesc` per model) and, when the KIE live adapter (Skill 74) is installed, `kie_live_adapter.py price <model>`. The Veo pricing note and the closing "model pricing" section carry the same caveat. Skill 74 is not in this repository yet, so the adapter reference is conditional; the `/api/v1/models` source is live today.
- `INSTRUCTIONS.md`, `EXAMPLES.md` and `CORE_UPDATES.md` per-clip and per-credit figures are labelled historical and point to the same live sources.

### Migration Notes
- `CORE_UPDATES.md` changed (the pricing line); `wire.sh` bodies did not, so no re-wire is needed for the core-file blocks.
- Risk level: LOW (documentation only).

---

## [v7.0.5] - 2026-10-05 - fix: credit check in qc-kie-setup.sh no longer depends on shell quote stripping

### Fixed
- `qc-kie-setup.sh` passed its credit check only by accident: the inner `'"code" *: *200'` lost its quotes inside the outer double-quoted eval string, so the grep that ran was `code *: *200`. The response is now tested with a plain `case "$RESP" in *'"code":200'*|*'"code": 200'*)` outside the eval, and the check reads that flag. Proven offline with a stub `curl`: body `{"code":200,...}` and `{"code": 200,...}` pass; body `{"code":401,...}` fails (warning).
- The prebuilt `kie-setup.skill` archive is not rebuilt: no packaging script exists in `scripts/` (checked by listing), the archive was already out of date with its source before this change, and the updater copies skill folders wholesale.

---

## [v7.0.5, PR 1497] - 2026-10-05 - Canonical KIE common rules

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
