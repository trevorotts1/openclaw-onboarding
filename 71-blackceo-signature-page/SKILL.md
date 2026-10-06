---
name: blackceo-signature-page
description: Build, revise, QC, and hand off BlackCEO Signature funnel pages end to end, including Standard or Long-Form copy, font/action planning, desktop/mobile wireframes, visual-direction mockups, image intelligence and prompts, generated-image QC, image maps, responsive HTML, GHL installation/testing, and authorized publishing. Use when a user asks for a BlackCEO Signature landing, opt-in, registration, challenge, sales, booking, squeeze, webinar/event, or comparable focused-conversion page, or asks to apply the BlackCEO page, image, Secret Super Sauce, or visual-direction system.
version: 1.1.1
---

# BlackCEO Signature Page — Skill 71

This is the canonical BlackCEO **single-page** landing-page production skill for OpenClaw. It converts a client brief into a complete Standard or Long-Form BlackCEO Signature Page while preserving BlackCEO copy, design, visual intelligence, image-prompt, QC, and public/private separation rules.

## Route boundaries first

Use this skill for a focused single-page conversion experience: landing page, opt-in/squeeze page, event/registration page, challenge page, booking page, lead-generation page, or comparable page using the BlackCEO Standard or Long-Form system.

Route elsewhere when the assignment is specifically:

- **Skill 49 `signature-funnel`** — multi-step 3/5/7 Signature Funnel with checkout / upsell / downsell / OTO chain.
- **Skill 56 `sales-page-assets`** — Direct-Response / VSL / 8-section main / 9-section upsell / high-ticket / order-bump asset stack.
- **Skill 62 `cinematic-web-funnel-engine`** — animated, immersive, scroll-controlled cinematic website/funnel.
- **Website-craft** — ordinary multi-page marketing website whose governing copy contract is not this BlackCEO single-page system.

If the owner explicitly asks for this BlackCEO Signature Page skill, use it even when the page ultimately hands delivery to another rail.

## OpenClaw ownership and seams

- **Primary department:** Web Development.
- **Primary role:** Landing Page Specialist.
- **Copy collaboration:** Marketing / Conversion Copywriter when the current execution assigns copy work there; this skill's writing references remain the page-specific authority.
- **Images:** delegate execution to **Skill 66 `kie-image`** when Kie.ai is selected, or **Skill 63 `agnes-image`** when Agnes is explicitly selected/available. Do not hand-roll provider calls here.
- **GHL delivery:** delegate media/page build to **Skill 6 `ghl-install-pages`**, the existing GHL delivery rail.
- **Vercel:** use **Skill 8 `vercel-setup`** when that hosting target is selected and configured.
- **Browser automation:** use the repo's managed browser path / Skill 3 conventions when graphical browser work is required.

Do not duplicate another skill's provider client, browser manager, GHL builder, deployment client, or credential storage.

## Read only what the current stage needs

- **Brand (every stage):** `references/BlackCEO-Page-Brand-Law.md` and the run's brand file (`intake.json` -> `brand_file`; `assets/brand/blackceo-brand.json` for BlackCEO pages, `assets/brand/client-brand.template.json` filled by the client for client pages). Brand fonts are the one fail-open key: when they are still MUST_SUPPLY, `font_policy` says derive-document — derive the best display/body/accent for the job, document the rationale in the bible (`fonts_source: "derived"` + `font_rationale` + `font_reviewer`), reviewer approves. Never blocked on fonts; every other MUST_SUPPLY value still blocks.
- Production order / gates: `references/BlackCEO-Signature-Landing-Page-Production-and-QC-SOP-v1.md`
- Standard copy: `references/BlackCEO-Signature-Landing-Page-Standard-v6.md`
- Long-Form copy: `references/BlackCEO-Signature-Landing-Page-Long-Form-v6.md`
- Image planning / art direction / prompts / visual QC: `references/BlackCEO-Signature-Image-Intelligence-and-Prompt-Creation-Guide-v5.md`
- Photographic direction: `references/BlackCEO-Famous-Photographers-DNA-Style-Library-v1.1.md`
- Cinematic/directorial direction: `references/BlackCEO-Cinematic-Image-Style-Systems-v2.0.md`
- Visual-artist direction: `references/BlackCEO-Visual-Artists-AI-Style-Intelligence-Guide-v1.0.md`
- Visual companion: `assets/BlackCEO-Master-Visual-Reference-Guide.png` — an image-style menu only, never a page-layout or page-color reference
- Artifact and QC contracts: `references/artifact-contracts.md`, `references/qc-contract.md`, `references/stage-contract.json`, `references/html-qc-rubric.md`
- Swarm plan: `references/swarm-plan.md`

Do not load all three style libraries at once. Load only the selected family/style when needed. The exact per-stage reading list is the `reads` field of `references/stage-contract.json` — agents carry only what their stage names, never the full 100-400 KB guides.

### Design / wireframes / mockups

Fonts, colors, logo, and page look come only from the brand file. An agent never proposes page tokens.

## Governing production order

Use the Production/QC SOP as authority. `scripts/stage_gate.py` is mandatory. Before starting any stage run `stage_gate.py check <run_dir> <stage>`; a stage ends only when `stage_gate.py close <run_dir> <stage>` exits 0. A run order or prompt cannot remove or rename stages. If a run order lists fewer stages than `references/stage-contract.json`, follow the contract and record the order's omission in the report.

Stage IDs (canonical, from `references/stage-contract.json`):

`intake, copy, font-action-plan, desktop-wireframe, mobile-tablet, visual-mockup, image-inventory-prompts, image-generation-qc, image-map-upload, final-mockups, responsive-html, ghl-install-test, publish-verify`

Track stage status as `blocked`, `working`, `qc_failed`, or `ready` in the private workflow-state JSON; `scripts/validate_state.py` remains available for that file (back-compat). The gate's receipts under `private/receipts/` are what actually close stages.

### Copy

- Select **Standard** or **Long-Form**; do not silently merge both.
- Copy leads layout; never shorten approved copy to fit a template.
- Keep internal framework labels/counts in the private review source only.
- Derive a clean publication source with no private production labels.
- Use `scripts/validate_public_copy.py` before public HTML/handoff.
- Repair only failed criteria. Maximum three focused repair attempts for failed work; passing work advances immediately.

### Design / wireframes / mockups

- Establish font intelligence and visitor-action plan before full wireframes. Fonts, colors, logo, and page look come only from the brand file; an agent never proposes page tokens.
- Build complete desktop first, then intentionally reflow mobile/tablet; do not merely shrink desktop.
- Resist generic AI-page patterns: repetitive cards, identical section geometry, generic SaaS gradients, sterile stock-office scenes, repeated center alignment, and same-ratio imagery everywhere.
- Use varied visual rhythm, negative space, typography, asymmetry, scale, image shape, and intentional interruptions.
- Keep exact approved copy unless the owner explicitly authorizes copy changes.

For multi-part review exports, keep individual PNGs and use ordered manifests with `scripts/combine_review_pdf.py` and `scripts/validate_review_pdf.py` for separate desktop/mobile wireframe/mockup PDFs.

## Page-level Creative Direction

A page may use exactly one external Creative Direction family/style, or Secret-Sauce-only:

- one Photographic Direction; or
- one Cinematic/Directorial Direction; or
- one Visual-Artist Direction; or
- no external direction, with the BlackCEO Secret Super Sauce primary.

If the intake does not name an external Creative Direction, the page is `SECRET_SAUCE_ONLY`. "No direction supplied" never means "choice delegated to the agent". An external style is used only when the owner names it at intake. `scripts/validate_visual_direction.py` enforces this at the visual-mockup gate.

Never mix external families on one page. The Secret Super Sauce is the adaptive BlackCEO house layer, not a second external style. Where a Sauce dimension conflicts with a defining trait of the selected style, the selected style wins for that dimension and compatible BlackCEO qualities remain active.

## Image planning and generation

Read only what the stage contract's `reads` field names for image stages (the v5 image guide sections needed, brand law, the grade block), never the whole library bundle.

Non-negotiables:

- one image-map entry -> one complete prompt -> one independently generated asset -> one correctly named file;
- production prompts: **5,000–20,000 meaningful characters** under the BlackCEO house rule;
- default working target: **8,000–14,000 useful characters** because the current referenced runtime compatibility ceiling is 19,000;
- never silently truncate a prompt or disable validation;
- in `SECRET_SAUCE_ONLY`, the prompt's color-grade element starts with the Signature Grade Block from `assets/brand/signature-grade-block.txt`, verbatim (`scripts/validate_prompt.py --sauce-only` enforces it);
- use camera, lens, aperture/depth, composition, subject placement, lighting, posture/expression, fashion, skin/hair, color-grade, typography-as-image, and negative-space intelligence where applicable;
- preserve real-person identity and recurring-character continuity;
- use the Black representation intelligence in the image guide when Black/African-descended subjects are present;
- keep one page-level Art Direction coherent while varying shot/view scale, ratio, environment, posture, scene type, and intensity;
- never pass human research-lineage names downstream when a style library requires branded, descriptive execution grammar.

Run `scripts/validate_prompt.py` on final prompts (with `--sauce-only` on `SECRET_SAUCE_ONLY` pages) and `scripts/validate_image_manifest.py` (with `--inventory` and `--measure`) on the image map.

### Image engine routing

Ask whether the owner/client has an explicit image-engine preference when generation is in scope.

- If **Kie.ai** is selected or no preference is given and Kie is available, hand the final prompt/payload requirements to **Skill 66 `kie-image`**, which owns current Kie model selection, payload validation, dispatch, and image QC. Do not hardcode a forever-model here. Skill 66 currently prefers the latest repo-approved GPT Image route when compatible.
- If **Agnes** is explicitly selected/available, use **Skill 63 `agnes-image`**.
- If another configured provider is explicitly selected, honor it if the current client environment supports it.

Paid-call approvals, client-owned credentials, provider limits, and retry rules remain owned by the executing provider skill and fleet policy.

## Swarm execution

Run stages as `references/swarm-plan.md` defines: one agent per item, reviewers start when their item lands, never fixed-size chunks. Every agent writes its receipt to `private/receipts/` and its files to the run folder. The orchestrator learns results only from `stage_gate.py check/close` output, never from an agent's chat reply. No re-read or recovery lanes.

## QC and repair

Read `references/qc-contract.md`.

- General page-stage criteria: each applicable criterion >=8/10 with no auto-fail (responsive-html is scored on `references/html-qc-rubric.md`).
- Prompt/generated-image work: retain the stricter average >=8.5, each applicable criterion >=8, zero auto-fails where the governing references require it.
- A failed artifact is repaired and rechecked before downstream use.
- Do not rework passing artifacts without a dependency reason.
- Do not invent completion: submitted generation is not completed imagery; local preview is not target-environment verification.

## Delivery

- Build only from current QC-passed copy, visual plan, approved assets, image map, and action plan. The final mockups are the visual target; the HTML must match them section by section.
- Preserve real forms, checkout, booking, URLs, embeds, and workflows; do not invent substitutes.
- For GHL, hand the delivery bundle to Skill 6 rather than bypassing its rail.
- Publish only when authorization is present under the current OpenClaw policy; otherwise deliver preview/staging artifacts and exact remaining action.

## Reporting

Report to the owner by pasting `REPORT.md`'s overall line, stage table, and cost line — `REPORT.md` is written only by `scripts/stage_gate.py report`. Do not write your own summary of stage status. Nothing marked "pending confirmation" may ship; pending means BLOCKED — except derived fonts: brand fonts missing are derived-and-documented per `font_policy` and reviewed, never blocked (the reviewer's approval of `fonts_source`/`font_rationale`/`font_reviewer` in the bible is the confirmation, and an unapproved derived-font bible still ships nothing).

## Installation / maintenance boundary

`verify.sh` is an **install/update maintenance check**, not a normal page-build step. Do not run the complete skill verification every time this skill is invoked.

For onboarding-repo integration, read `REPO-INTEGRATION.md`. The repo's native-skill binding lives in `23-ai-workforce-blueprint/skill-department-map.json`; generated role blocks must be refreshed with the repo's stamper rather than hand-edited.
