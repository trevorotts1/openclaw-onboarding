# CHANGELOG

## 1.3.12 - 2026-10-26 - oct-25 fix batch: l01-l08 install, preflight, handoff and intake hardening

- `scripts/install_local.py` (l01): the installer no longer truncates a registry that resolves back to the same file it is writing, refuses symlinked registry leaves, honours dry-run failures, and applies the terminal-evidence rule to the executor exit. Tests: `tests/test_scripts.py`.
- `scripts/preflight_installed.py` (l02): preflight requires positive proof - only demonstrated client-data refusals may pass, composed-prompt proof is required, the asset gate is layout-aware, and `scripts/check-skill71-parity.py` verifies the real installed runtime.
- `scripts/build_production_request.py`, `scripts/page_role.py`, `scripts/run_page_role_stages.py`, `scripts/run_page_type.py`, `scripts/stage_executor.py` (l03): one page role and one section-sequence rule across builder, executor and runner; completion is honest and utility CTA treatment is enforced.
- `scripts/validate_handoff.py` (l04): the page handoff is derived from the page kind; an undeclared handoff route fails closed and the form-route message no longer drifts. `references/page-kinds.json` and `references/stage-contract.json` extended.
- `scripts/write_intake.py`, `scripts/launch_context.py` (l05): both copy selectors are derived with a recovery owner for refusals; refusal registers are split and one copy selection is enforced.
- intake engine (l06, shared `shared-utils/client_intake/`): page-only profile, one colour policy, page-kind choices, the page ask list enforced at the engine boundary (findings 18, 19, 23, 46), and the payment flag derived from the bank's own billing text.
- `signature_launch/experience/render_question.py` (l07): style examples render before the A/B/C question with QC-hardened disclosure.
- docs and stamps (l08): honest entry path and accessibility criterion in INSTALL.md / START-HERE.md, real three-stamp lockstep (VERSION, skill-version.txt, SKILL.md) proven non-vacuously.

## 1.3.4 - 2026-10-20 - batch: a zero-image generation run is FAILED, never success (SPF002)

- `scripts/shared_page_service.py`: `--pipeline-command` is no longer optional for a generation run. `--validation-only` is the labelled admit-and-stage mode (prints `MODE=validation-only: no artifacts generated`); a generation run without `--pipeline-command` FAILS with exit 2. Before this change a run that generated nothing returned 0 and read exactly like a generated run.
- `scripts/stage_gate.py`: new `verify_generated_images()` wires generation success to image files on disk. Zero images is FAILED regardless of exit codes; a stage that ran (`stage-executor-record.json`) with no image, or a mockup part that is unreadable or not 1440 (desktop) / 390 (mobile) wide, also fails. It checks only the stages the run executed (wrappers run three stages; final-mockups follow client approval).
- `scripts/run_page_type.py`, Skill 49 `scripts/checkout_wrapper.py` and Skill 78 `scripts/run_image_stages.py` pass the new mode through. Tests: `tests/test_shared_page_service_generation.py`.

## 1.3.3 - 2026-10-20 - batch: LANE-49 repair: a folded-levels sales page gets its levels panel in a real run

- `scripts/build_production_request.py`: for a sales-kind request the builder reads `<run_dir>/launch.json` (staged by `write_intake.py --launch-context`) and, when its `journey_mode` is `folded_levels`, stamps `folded_levels` = the number of main offers into the production request. `wireframe_spec.py` already closes the last wireframe slice on an N-card levels panel when the request carries it; before this change nothing in a real run set it. The visual-mockup prompt now closes on the same levels panel: `stage_executor.py` passes `levels=request.get("folded_levels")` to `page_kinds.mockup_line` (a bad count is refused as an executor error), so the wireframes and the mockups of a folded-levels sales page end on the same N level cards. Tests: `tests/test_lane49_folded_levels.py`.

## 1.3.2 - 2026-10-20 - batch: signature funnel page types (sales page, landing, order form) and clear desktop/mobile labels

### order form (checkout) page type support

- `references/copy-specs/roles/checkout.json` and `scripts/role_spec.py`: a page role can have its own canonical section sequence; checkout has five. `stage_executor.check_section_count`, `build_production_request.py --page-role`, `composition.py` (composition roles), `wireframe_spec.py` (page type layout block) and `shared_page_service.py --design-style` read it. Landing behaviour is unchanged. Tests: `tests/test_role_section_spec.py`.

### clear desktop/mobile labeling on every wireframe and mockup

- New `scripts/deliverable_labels.py`: one helper (page_role + stage + device -> human label and file slug) used by `combine_review_pdf.py` and `build_overview_board.py`. Every review PDF carries ONE title band at the very top of page 1 only (`DOWNSELL 1 · DESKTOP WIREFRAME · 8 SECTIONS`: page type, DESKTOP or MOBILE, WIREFRAME or MOCKUP, section count) added at compose time, never inside the AI image; pages 2 and on are the bare section image, so there are no notes between sections and the PDF reads as one continuous page (Trevor order 2026-10-20). The rule is a permanent guard: `validate_review_pdf.py` measures page geometry and FAILS any PDF with a label band anywhere but the page-1 title (it runs in the stage contract for all four image stages and inside `--deliver`, so a failing PDF is deleted and never delivered). PDFs, section images and boards are named by those labels (`upsell-1_DESKTOP_WIREFRAMES.pdf`, `upsell-1_desktop_wireframe_s03-of-08_offer.png`, `upsell-1_DESKTOP-and-MOBILE_WIREFRAME-BOARD.png`); client deliveries use the `desktop-wireframes`, `mobile-wireframes`, `desktop-mockups`, `mobile-mockups` folders. Board titles, column headers and tile captions carry the same words. `stage-contract.json` mockup PDF globs follow the new names. Approval and gate behavior unchanged.
- Sales page labels (SPF035 repair): a run with `page_role` landing and `page_kind` sales is named by its kind, not as a landing page. `deliverable_labels.declared_page_role` returns `sales_page` for it, so the review PDF title band, PDF and image file names and overview boards read `SIGNATURE SALES PAGE` and `sales-page_*`, matching the Design Board. Test: `tests/test_review_pdf_stage.py`.

### signature sales page and signature landing (opt-in) page are two page kinds (SPF030)

- `references/page-kinds.json` and `scripts/page_kinds.py`: the landing role has two kinds, `sales` (Standard 12 or Long-Form 15 sections, buttons go to checkout) and `opt_in` (Long-Form 15 only, buttons open the form). The canonical section sequence is the copy spec's own; a kind that does not allow the declared copy form is refused.
- `write_intake.py --page-kind sales|opt_in`, enforced for production runs by the new intake validator `gate:intake_page_kind` (test runs exempt). `build_production_request.py --page-kind`, `stage_executor.py` (kind check, `PREFLIGHT_PAGE`, kind line in the mockup prompts), `wireframe_spec.py` (kind head on every slice, closing checkout panel or registration strip on the last), `design_board.py` (label, emphasis and record by kind) and the run report all carry the kind. The wireframe, mockup, PDF and overview-board pipeline is unchanged and shared.
- Routing: "signature sales page" is a Skill 71 trigger and a Skill 56 anti-signal; the Skill 49 bridge now requires `landing.page_kind`. The department map no longer claims Skill 56's sales page uses the shared image service.
- `tests/test_page_kinds.py` (new, 24 tests, no provider call).
- Closing band button (SPF030 repair 1): the closing band sits on the last slice, the founder letter, which both copy specs forbid a CTA of its own, so it used to ask for a button "reading the section's CTA label" that never exists while the same prompt said "no CTA". It now reads the page's last given CTA label (`page_kinds.closing_label`), prints that label as its own `CLOSING BUTTON LABEL` verbatim line, replaces the "no CTA" item and behaviour note on that slice only (wireframes) and ends the mockup slice on the panel or strip with the same label; the builder's `BUTTON` line says the same. A page that gives no CTA label at all is refused. The new tests run on the real example copy, where the founder letter has no CTA.

## 1.3.1 - 2026-10-19 - sync allowlist test passes in the 999 edition

- `tests/test_sync_allowlist.py`: the file that exists only in this repo must be absent in the 999 edition, so the same test passes in both. Version bumped so the G3 gate sees the skill content change. No production behavior changed.

## Unreleased - 2026-10-19 - test honesty: fixture-dependent modules report SKIPPED, not PASS; mobile anchor floor 18px

- `tests/`: two fixture-dependent modules (browser hygiene, swarm runner) now report SKIPPED with a named reason instead of a false PASS when their fixtures are not shipped; `test_validate_page.py` pins the 18px mobile anchor floor. Suite: 40 passed, 2 skipped. No production behavior changed.

## 1.3.0 - 2026-10-19 - signature page fidelity batch: design board, brand colors, reference use, review PDFs

One batch of the signature page fixes from the SPF020, SPF025 and SPF026 test runs, plain-English summary:

- Reference images are structure only. Pictures a client likes are used to copy layout and composition, never their content, and a bleed check fails the run when reference content shows up in a delivered image. A typed reference catalog with media-library links backs this.
- Brand colors are resolved first. The client's palette is looked up (exact owner match) and read from one place before any wireframe, mockup or image stage starts, and every later check reads that same palette.
- Go Full Page framework. A page color system, an image grade and a page pixel check are required; the hypersaturation step is never optional, a missing palette is refused, and colors outside the palette are refused in prose.
- Section count. One request section per canonical copy section; a mismatch fails closed, and prompts no longer carry "Pain N" framework names or slot canon text for slots that are not planned.
- Design Board. One client-approved board per page is made from the page's real images, after the image chain and before any wireframe; it sends only its own pictures and checks each declared text on the image.
- Design style choice. The client picks A Block, B Circle or C Hybrid, and the chosen style is checked against the image inventory (a circle check needs a real PNG).
- Composition library. Words over images, shaped crops and light fields, with flags, a light-field check and catalog URLs.
- Wireframe standard. Wireframe stages send the owner's liked sheets and an annotated build-spec prompt in the client's colors; a prompt that names no color is refused only when the plates are its subject; a half-delivered wireframe sibling skips the combined board instead of failing the stage.
- Combined overview boards. Every image stage also produces one all-in-one board (desktop page, guide and mobile parts), with the mobile head sized from the subtitle.
- Client PDF. Each image stage combines into validator-gated desktop and mobile review PDFs automatically; `validate_review_pdf.py --delivered` proves the client's section images and the delivered PDF are the exact validated build, and `--deliver` copies and re-validates it.
- Prompt budget. Composed prompts reach the 16,000 character floor, truncated copy is always refused, and with every new block added the composed prompts still fit the 20,000 maximum by dropping superseded palette and style prose.
- Tests: new modules for each unit are registered in `tests/run_tests.py`, and older tests follow the merged gates.
- Version bumped to 1.3.0 (`SKILL.md` frontmatter, `skill-version.txt`, `VERSION`).

## 1.2.24 - 2026-10-19 - fidelity wire: copy-source CTA, tier strip, prompt budget

- `scripts/stage_executor.py` carries the generation-wire repairs from 757ce86c0 and 770086e57, plus this repair round:
  - Request templates render the double-brace form first (`{{section_number}}`, `{{section_name}}`), so the values substitute instead of becoming literal `{token}` text; any leftover token-shaped placeholder fails closed before a provider call.
  - CTA recovery accepts the section payload (a label string or `{label, microcopy}`) and resolves the copy source through every real layout in authority order: the request's top-level `copy_source`, then `metadata.copy_source`, then `<run_dir>/inputs/copy.json`, then `<run_dir>/copy.json`; the first existing file wins. Labels are keyed by the canonical copy-source section id, never the request's band label. When an inline CTA and the copy source both carry a label and disagree, the copy source wins and a `WARN cta_conflict` names both; an inline label with no copy-source counterpart is used as before. A section marked `cta_required` with no resolvable label fails closed by section name.
  - `sanitize_prompt` strips cross-client project names derived generically from the visual-standards manifest basenames (no hardcoded client), every sentence carrying a tier verdict regardless of preceding tokens (named-sheet forms such as `Ref Tier H` and `AA Tier H`, and standalone forms such as `Tier H (flat, sparse)`, `Tier R (layered, photo-dense)` and the template heading `Tier R rich mockup, M4`), and every full-page WxH dimension pair; current-client content is untouched.
  - `prompt_budget()` reads `references/prompt-budget-policy.json`: below the 80 percent floor warns and names the deficit, above the maximum fails hard, and a per-section prose budget reserves the verbatim copy and contract blocks first so design-rules prose cannot crowd them out. Records carry `prompt_sizes`.
- `references/generation-execution.md`: states the accurate geometry story. Canvas geometry is per-image via `target_ratio()` with the `geometry_mismatch` warning; `stitch_sections.py` and `build_hybrid_board.py` are unchanged (already content-height), and no assembly-canvas fix is claimed.
- `tests/test_stage_executor_prompt_contract.py`: contract tests pin the double-brace render, the leftover refusal, CTA from the payload/copy source/required refusal, the two cross-client leak shapes plus dimension pairs, the below-floor warning, the per-section prose budget, the three real copy-source layouts (top-level, `metadata`, `<run_dir>/inputs/`) with the conflict warning and the `cta_required` refusal, and the standalone tier shapes. Registered in `tests/run_tests.py` `MODULES`, so the suite actually runs the repair's own tests.
- Version bumped to 1.2.24 (`SKILL.md` frontmatter, `skill-version.txt`, `VERSION`).

## Unreleased - 2026-10-17 - S71-06-Q1: the band governs in all contexts; two stale doctrine surfaces reconciled (Signature Launch room S71, B-19)

- Q1 ruled (MAIN, 2026-10-17, under owner Decision 1): the KIE rule 12 band governs in ALL contexts, including Signature Launch runs; packet doc 07 section 6 is reconciled as an erratum wherever it conflicts; there is no prompt_policy_id selector and no context split.
- `references/qc-contract.md`: erratum paragraph appended to the Style fidelity enforcement section. The section's former closing sentence (prompt length never passes or fails a prompt; element completeness governs; length is telemetry; a VERIFIED cap is the only hard ceiling) is recorded as superseded by the band: below the 80 percent floor fails (budget exit 3), above the maximum fails (budget exit 4), cap_status is provenance only. No gate, validator, threshold, or schema changed; the sentence itself is retained above its erratum for the record.
- `references/external-authorities.json`: erratum appended to the gpt-image-2-cap-divergence resolution. Its warn-only overflow clause for the NOT_PUBLISHED GPT Image 2.5 figure is recorded as superseded (band applies to the recorded maximum in full; overflow fails, budget exit 4). No cap value, pin, or checked_on changed; the divergence itself still routes to the owning rooms (matrix Q4).
- No version bump: the version pair is bumped once at candidate assembly (Lane B convention).

## 1.2.10 - 2026-10-15 - Decision 1: the rule 12 band is the native authoring target (update plan Items 4 and 23)

- `scripts/validate_prompt.py`: the KIE rule 12 band governs prompt length again, adopted as this skill's native authoring target by owner Decision 1 (2026-10-15), superseding Amendment 6 Part C wherever the two conflict. `band_numbers()` calls the shared enforcer's `budget()` for the verdict math (fallback arithmetic identical). Below the 80 percent floor fails (budget exit 3, naming the characters to ADD and the count to the 95 percent target); above the maximum fails (budget exit 4, naming the characters to CUT); floor-to-target passes with a warning; in band passes. Telemetry carries characters, percent_of_max, the budget block, and `ratio_confirmation`: the requested ratio is confirmed at validate time against the model's aspect-ratio enum in Skill 74's registry snapshot (confirmed / not_in_enum, which fails by name / unverified / not_recorded). The 2,000-character tripwire is retained for models with no recorded maximum; token-limited models render no character verdict. Part C's supersession is recorded in the module docstring's RETIRED section.
- `references/prompt-budget-policy.json`: carries the band block (floor 80 percent, target 95 to 100 percent; GPT Image 2.5 maximum 20,000, floor 16,000, target 19,000); cap_status survives as provenance only.
- `scripts/stage_gate.py`: `_prompt_budget_record()` records the validator's budget block on prompt-stage item close entries (best-effort; never blocks a passed close).
- `tests/fit_prompt.py`: restored to real fitting (grows fixtures to 97 percent of the policy maximum; synthetic test filler only, never a production authoring method).
- SOP Stage 7A/7B: the band is named as the native authoring target, reached by genuine specification across all nine categories, with padding a named failure; Stage 7B names the in-validator budget check and the ratio confirmation alongside the Skill 74 adapter check.
- Guide and SKILL.md (P2 surfaces, Decision 7): the guide's rule 12 paragraph presents the band as this skill's own authoring target with the Part C supersession recorded in the paragraph; the appendix prompt-length row and its note record the reconciliation; the lesson instruction authors all ten elements to the band by genuine specification; SKILL.md's Non-negotiables carry the same doctrine.
- Version bumped to 1.2.10 (SKILL.md frontmatter and skill-version.txt; the skill-local VERSION file is untouched).

## Unreleased - 2026-10-14 - Ruling 6: Signature Grade Block conformed to selective saturation

- `assets/brand/signature-grade-block.txt`: saturation prose conformed to the Secret Super Sauce doctrine (Image Guide v5 Sauce sections 2, 3, 23.2, 23.10; Guide section 8) under owner Ruling 6 (2026-10-14): the hero color and its one supporting accent are pushed to roughly 140 percent of natural while neutrals, skin, whites, blacks, and shadow detail stay protected; the former instruction to push global saturation is removed. The block's opening, structure, single-paragraph form, and closing lines are unchanged, and the verbatim mechanism (the block must START Element F in `SECRET_SAUCE_ONLY`) is unchanged.
- `tests/fixtures/prompt_good.txt`: the embedded copy of the block conformed identically (byte-identical to the canonical file, verified).
- `references/BlackCEO-Page-Brand-Law.md`: Signature Grade Block section annotated with the Ruling 6 conformance and the supersession of the archived global-push wording.
- No gate, validator, threshold, or schema changed; grade thresholds stay `null`.

## 1.2.7 - 2026-10-09 - operator wording scrub

- Wording scrub, behavior identical: the two-strike gate block in SKILL.md says the unlock is operator-only (no personal name).

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
