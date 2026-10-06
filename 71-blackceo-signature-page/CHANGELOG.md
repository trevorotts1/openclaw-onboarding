# CHANGELOG

## 1.2.5 - 2026-10-06

- `verify.sh`: the prompt validator sanity fixture failed under the 1.2.4 KIE rule-12 gate — `tests/fixtures/prompt_good.txt` is 6,795 characters, below the 16,000 hard floor of the GPT Image 2.5 Sunburst band. verify.sh now grows the fixture into the band with `tests/fit_prompt.py` (the same helper `tests/run_tests.py` uses, matching the 999-setup copy of this skill) before running the sanity check; a fit failure is reported as its own line. `--runtime-max 19000` dropped — accepted and ignored since 1.2.4.
- Version bumped to 1.2.5 (SKILL.md frontmatter, skill-version.txt, VERSION).

## 1.2.4 - 2026-10-06

- `scripts/validate_prompt.py`: the 5,000 to 20,000 house band and the 19,000 runtime warning are retired. KIE prompt rule 12 (owner order 2026-10-05): prompt length is 95 to 100 percent of the model maxLength, hard floor 80 percent, hard ceiling 100 percent, measured by the one shared enforcer `shared-utils/kie_prompt_enforcer.py` (wraps Skill 74 `prompt-budget --check`); the gate keeps no band of its own and its rejection names the exact characters to add or cut. New `--model` (default GPT Image 2.5 Sunburst); `--runtime-max` is accepted and ignored.
- `tests/fit_prompt.py` grows the fixture prompts into the band for the tests that need a passing prompt.
- Version bumped to 1.2.4 (SKILL.md frontmatter, skill-version.txt, VERSION).

## 1.2.3 - 2026-10-06

- The image-engine question now has an agent-facing step: SKILL.md "Image and video engine routing" and the SOP intake step tell the agent to run `scripts/write_intake.py ... --image-engine kie|agnes`. The intake stage reads `references/artifact-contracts.md` and closes only when `intake.json` carries `image_engine` (new `gate:intake_engine`; test i16).
- Model-source `evidence` also needs at least 3 words and may not be one repeated character.
- Version bumped to 1.2.3 (SKILL.md frontmatter, skill-version.txt, VERSION).

## 1.2.2 - 2026-10-06

- `scripts/write_intake.py` writes `intake.json` including `image_engine` (`kie` default, `agnes`), so a real Agnes run satisfies the stage gate; documented in `references/kie-generation-route.md` and `artifact-contracts.md`. Test i15.
- `stage_gate.py`: `evidence` for an explicit-request or department-pin model source must be at least 12 characters, not a placeholder and not the model id; test i14 extended.
- Version bumped to 1.2.2 (SKILL.md frontmatter, skill-version.txt, VERSION).

## 1.2.1 - 2026-10-06

QC fixes on the KIE integration (PR 1527).

- **M2** `stage_gate.py` transport check no longer trusts the receipt alone: each Skill 74 `task_id` must be unique and have its own successful, active result file in `receipts/kie74/`; two result files may not share a task id; the Agnes route requires `intake.json` `image_engine: "agnes"`; an `explicit-request` or `department-pin` model source needs `evidence`. Tests i10 to i14 added.
- Version bumped to 1.2.1 (SKILL.md frontmatter, skill-version.txt, VERSION).

## 1.2.0 - 2026-10-06

KIE integration (owner order: the landing page skill must work flawlessly with the KIE rules, and Skill 74 is the one approved KIE path).

- **KIE-1** New `references/kie-generation-route.md`: every image or video request routes policy owner (Skill 66 images, Skill 67 video, Skill 63 only when Agnes is selected) then Skill 74 transport (validate, preflight at price x 1.30, prompt-budget check, `submit --mode active`, wait, save immediately). GPT Image default via `latest-family`; N43 ratio rules; account limit 20 createTask per 10 seconds; no hard-coded prices, model ids or endpoints.
- **KIE-2** `scripts/stage_gate.py` + `references/stage-contract.json`: `image-generation-qc` now has `transport_required`. The stage closes only when the receipt carries a `transport` block (Skill 74, mode active, per-file task id, model id and source, preflight ok, budget exit 0, N43 ratios) and `cost.provider` matches the route. A hand-rolled createTask has no such receipt and cannot close the stage. Tests: `tests/test_stage_gate.py` i1 to i9.
- **KIE-3** Prompt length text now points to `07-kie-setup/references/kie-common-rules.md` rule 12 (95 to 100 percent of the model maximum, never below 80 percent) instead of the older 5,000-20,000 house band, the 8,000-14,000 working target and the 19,000 ceiling: SKILL.md, `references/authority-map.md`, the Production and QC SOP (Stage 7 and 8), the image guide v5 (start, section 1, section 12), EVALUATION-CHECKLIST. The length validator code in `scripts/validate_prompt.py` is not changed here; if its check disagrees with `prompt-budget`, the budget wins.
- **KIE-4** Submission limit corrected from 20 per 15 seconds to 20 per 10 seconds (rule 3) in `references/swarm-plan.md`, the SOP and the image guide. Retention (save immediately, links can expire within 24 hours) and the single-attempt 401/403 rule are stated in the route file.
- **KIE-5** `references/BlackCEO-Page-Brand-Law.md` notes that model names inside the quoted brand-law rule 5 are never typed by Skill 71; the policy owners resolve them. `references/artifact-contracts.md` documents the generation receipt. `verify.sh` requires the new reference.
- Version bumped to 1.2.0 (SKILL.md frontmatter, skill-version.txt, VERSION).

## 1.1.1 - 2026-10-05

Font fallback: "if a person doesn't provide a font, the system figures out the best for
the job" (Trevor, 2026-10-05). Brand fonts move from BLOCKED to DERIVE-AND-DOCUMENT;
every other MUST_SUPPLY value stays BLOCKED.

- **FONTS-1** `assets/brand/blackceo-brand.json` + `assets/brand/client-brand.template.json` carry a `font_policy` object (`when_brand_fonts_missing: "derive-document"`, `requires_rationale`, `requires_reviewer`, context note); the TREVOR_MUST_SUPPLY font values are unchanged — the policy, not invented names, is what ships. `assets/brand/brand.schema.json` allows `font_policy` (optional, same shape).
- **FONTS-2** `scripts/validate_visual_direction.py`: brand `fonts.*` placeholders no longer FAIL when `font_policy` authorizes derive-document. Instead the bible must be derived-and-documented: `fonts_source == "derived"`, non-empty `font_rationale`, `font_reviewer` named (FAIL, one reason per line, when any is missing); a MUST_SUPPLY or banned font inside `bible.fonts` still FAILs; every non-font MUST_SUPPLY key (logo, masthead, founder_photos, page references) still FAILs naming each key. Exits stay 0/1/2.
- **FONTS-3** `scripts/validate_page.py`: `brand_fonts()` returns a derived flag; under derive-document the "not a brand font"/"not loadable" font checks become WARN lines (`WARN font (derived): ...`) instead of FAIL, while a banned font still FAILs. Exit codes stay 0/1/2.
- **FONTS-4** `scripts/stage_gate.py`: `gate:must_supply` no longer blocks intake when the only missing keys are `fonts.*` under derive-document (logo/photos still block); `gate:brand_fonts` accepts a derived font map (real families not in the placeholder brand list pass; a placeholder in the font map fails; banned fonts fail). Also fixes a latent `"fonts" and "utf-8"` encoding-arg quirk in `find_must_supply_keys`.
- **FONTS-5** Docs: `references/BlackCEO-Page-Brand-Law.md` "Fail closed" gains the font carve-out (derived-and-documented, never blocked; banned fonts still bound; everything else still blocks). SKILL.md brand bullet and the "pending means BLOCKED" line get the same carve-out. SOP Stage 3 font map states the derive-rationale-review flow.
- **FONTS-6** Tests: `tests/test_validate_visual_direction.py` (12 tests — derived pass, missing fonts_source/rationale/reviewer fail, placeholder font in bible fails, banned font fails, non-font key still fails) and `tests/test_validate_page.py` (9 tests — derived policy WARNs not FAILs). All 32 existing tests stayed green before the new ones were added.
- Version bumped to 1.1.1 everywhere (SKILL.md frontmatter, skill-version.txt, VERSION).


## 1.1.0 - 2026-10-05

Enforcement fixes after the failed 2026-10-01 page test (order:
BLACKCEO-SKILL-71-ENFORCEMENT-FIX-ORDER.md). Every item ID from that order is
listed in the entry.

- **A1.4-6** Brand is now a machine-readable file every stage loads: `assets/brand/blackceo-brand.json`, `assets/brand/brand.schema.json`, `assets/brand/client-brand.template.json`, `references/BlackCEO-Page-Brand-Law.md`; SKILL.md "Read only what the current stage needs" opens with the brand bullet; SOP Stage 3 and Stage 6 read fonts/palette from the brand file exactly; `authority-map.md` names the brand file and Page Brand Law the top authority for page colors, fonts, logo, and founder imagery.
- **A2.1-2** No direction at intake means `SECRET_SAUCE_ONLY` — never agent-delegated style choice; SKILL.md states it and the v5 image guide's selection step 4 requires explicit owner delegation (`creative_direction: "delegated"`); `scripts/validate_visual_direction.py` enforces it with color/font/placeholder checks.
- **A3** Signature Grade Block restored as a constant: `assets/brand/signature-grade-block.txt` (byte-for-byte from the archived IMPROVED-FRAMEWORK-v2 section 2.4); required verbatim in every `SECRET_SAUCE_ONLY` prompt via `validate_prompt.py --sauce-only`; image guide section 8 states it.
- **A4** `assets/page-references/README.md` lists the three REQUIRED page-layout reference files; `authority-map.md` marks `BlackCEO-Master-Visual-Reference-Guide.png` an image-style menu only, never a page-layout/page-color reference.
- **B1** A mockup is a real rendered image: SOP Stage 6 and Stage 11 outputs are `mockup.html` plus `part-*.png` renders by `scripts/render_page.py`; Stage 12 adds "the final mockups are the visual target"; `validate_page.py --mode mockup` brand-checks the mock before any image work.
- **B2** `scripts/stage_gate.py` is mandatory: check/close/report; `references/stage-contract.json` owns stage IDs, artifacts, validators, review and score requirements; SKILL.md states the gate cannot be bypassed and `validate_state.py` remains for back-compat.
- **B3** Stage order owned by the gate; SKILL.md: "If a run order lists fewer stages than `references/stage-contract.json`, follow the contract and record the order's omission in the report."
- **C1-C6** (scripts, other lane) `render_page.py`, `compare_sheet.py`, `html-qc-rubric.md`, `validate_page.py`, extended `validate_public_copy.py`, extended `validate_prompt.py`, extended `validate_image_manifest.py`, `validate_image_grade.py`.
- **D1** `references/swarm-plan.md` — one agent per item, per-image fan-out, reviewers start when their item lands; stage contract fan-out deps.
- **D2** Stage-contract `reads` field is the only reading list per stage; SOP:154 narrowed to the image guide's crop/face/hair requirements section.
- **D3** SKILL.md + swarm-plan: agents write receipts; the orchestrator learns results only from `stage_gate.py check/close` output, never chat replies; no recovery lanes.
- **E1** `stage_gate.py report` writes `REPORT.md`; SKILL.md: report to the owner by pasting REPORT.md's overall line, stage table, and cost line — no self-written stage-status summary.
- **E2** "Nothing marked 'pending confirmation' may ship; pending means BLOCKED." in SKILL.md; invented tokens fail `validate_visual_direction.py`.
- **F1** Installed-only 1.0.2 fixes and files ported into this repo copy (CHANGELOG, EVALUATION-CHECKLIST, START-HERE, VERSION, adapters/, agents/openai.yaml, references/runtime-adapters.md, scripts/install_local.py, tests/); SKILL.md merged to one text (installed 1.0.2 fix wording wins, repo OpenClaw seam sections kept); verify.sh now runs `python3 tests/run_tests.py`.
- **F2** Five dead links to the removed `BlackCEO-Signature-Image-Prompt-Creation-Guide-v1.md` re-pointed to `BlackCEO-Signature-Image-Intelligence-and-Prompt-Creation-Guide-v5.md` (SOP x3, Standard v6, Long-Form v6).
- **F3.1** `authority-map.md`: qc-contract thresholds win over style libraries (average >=8.5, each >=8, 3 repair attempts).
- **F3.2** Photographers library section 6 heading: "Not used by Skill 71 — one style per page."
- **F3.3** Image guide: "this v4 master" -> "this v5 master".
- **F3.5** `artifact-contracts.md` stage names now point to `references/stage-contract.json`; stage IDs live in SKILL.md.
- **F3.6** SOP scope note: OpenClaw direct-response/VSL sales-page stacks route to Skill 56; SOP sales-page notes apply only to an explicitly assigned single BlackCEO Signature page.
- **F3.7** SOP:302 links `references/html-qc-rubric.md` for the "every required criterion >=8" rule.
- Version bumped to 1.1.0 everywhere (SKILL.md frontmatter, skill-version.txt, VERSION).


## 1.0.2 - 2026-10-01

Compatibility, safety and documentation fixes found by the Opus review of the landing-page
skill window plus the full page test. No methodology, writing, visual, QC, threshold or
production-order change.

1. `SKILL.md` intake: paid providers (Kie, Agnes, GHL, Vercel) use ONLY the client's own keys from that client's own `secrets.env` — never an operator's or another client's key; if a key is absent, the stage is marked BLOCKED. The same intake list now asks for a per-job image cap (count) — a cap, never an approval gate.
2. Large references note in `SKILL.md`: the style libraries are large — run the copy and image stages in separate sessions or subagents, and grep a style library by Style-ID (`VDL-nnn` photographic, `CIS-nn` cinematic, `ART-nn` visual artist) instead of reading it whole.
3. Adapter READMEs (`adapters/claude-code/README.md`, `adapters/claude-nine/README.md`, `adapters/codex/README.md`): Windows command line using `py scripts/...`, and the Pillow prerequisite noted where the PDF review test is documented.
4. `references/`: five dead links to the removed "Image Prompt Creation Guide v1" (`SOP-v1.md` x3, `Standard-v6.md`, `Long-Form-v6.md`) re-pointed to the v5 image guide; the image guide now states that when the onboarding repository is absent, the rules in that guide apply and nothing is fetched; `SOP-v1.md` GHL test-form step now requires a named test contact the owner approved for testing and never fires a live client automation.
5. Script fixes: `scripts/install_local.py` continues past a Codex-root conflict and creates absent roots instead of returning early on the first one; `scripts/validate_state.py` no longer crashes on a non-object stage; `scripts/validate_image_manifest.py` no longer crashes on an unhashable id and no longer false-fails authoring dialects against map-dialect schema; `scripts/validate_prompt.py` no longer false-fails on the ordinary English word "placeholder" (the bracketed marker and the bare `PLACEHOLDER` token still fail).
6. 999-setup installers: `setup-macos.sh` and `setup-windows.ps1` install Pillow the safe way (`python3 -m pip install --user Pillow` on macOS CLT python, `py -m pip install Pillow` on Windows) and link the bundled skills into `~/.codex/skills` and `~/.agents/skills` when `~/.codex` exists. `--break-system-packages` is never used.

The page-test artifact also carries the wireframe Section 3 overlap fix (the image frame no longer covers the text and CTA in `desktop-part-B.png`).

## 1.0.1 - 2026-10-01

Two compatibility fixes. No methodology, writing, visual, QC, threshold or production-order change.

1. `python` -> `python3` in `adapters/claude-code/README.md`, `adapters/claude-nine/README.md`, `adapters/codex/README.md`, and `references/runtime-adapters.md`. On macOS only `python3` exists; the documented `python` commands fail with exit 127.
2. `scripts/install_local.py` now knows both Codex skills roots. `DEFAULT_ROOTS["codex"]` was `~/.agents/skills` only; it is now `~/.agents/skills` and `~/.codex/skills`, and the installer links into every root listed.

## 1.0.0 - initial

First packaged release of the BlackCEO Signature Page skill.
