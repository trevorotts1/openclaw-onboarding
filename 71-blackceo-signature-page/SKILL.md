---
name: blackceo-signature-page
description: Builds BlackCEO Signature single-page conversion experiences using the Standard or Long-Form BlackCEO page system, full copy-to-wireframe-to-mockup-to-image-to-responsive-build workflow, Secret Super Sauce visual intelligence, and deterministic QC helpers. Use for landing pages, opt-in/squeeze pages, event or registration pages, challenge pages, booking pages, lead-generation pages, and other focused single-page conversion requests. Do not use for Skill 49 multi-step 3/5/7 funnels, Skill 56 direct-response/VSL sales-page stacks, or Skill 62 cinematic scroll experiences.
version: 1.0.2
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

Start with `references/authority-map.md`, then use:

- Production order / gates: `references/BlackCEO-Signature-Landing-Page-Production-and-QC-SOP-v1.md`
- Standard copy: `references/BlackCEO-Signature-Landing-Page-Standard-v6.md`
- Long-Form copy: `references/BlackCEO-Signature-Landing-Page-Long-Form-v6.md`
- Image planning / art direction / prompts / visual QC: `references/BlackCEO-Signature-Image-Intelligence-and-Prompt-Creation-Guide-v5.md`
- Photographic direction: `references/BlackCEO-Famous-Photographers-DNA-Style-Library-v1.1.md`
- Cinematic/directorial direction: `references/BlackCEO-Cinematic-Image-Style-Systems-v2.0.md`
- Visual-artist direction: `references/BlackCEO-Visual-Artists-AI-Style-Intelligence-Guide-v1.0.md`
- Visual companion: `assets/BlackCEO-Master-Visual-Reference-Guide.png`
- Artifact and QC contracts: `references/artifact-contracts.md`, `references/qc-contract.md`

Do not load all three style libraries at once. Load only the selected family/style when needed.

## Governing production order

Use the Production/QC SOP as authority. The normal state machine is:

`intake -> copy -> font/action plan -> desktop wireframe -> mobile/tablet -> visual mockup -> image inventory/prompts -> image generation/QC -> image map/upload -> final mockups -> responsive HTML -> target install/test -> publish/verify when authorized`

Use `scripts/validate_state.py` for deterministic state checks when a workflow-state JSON is maintained.

### Copy

- Select **Standard** or **Long-Form**; do not silently merge both.
- Copy leads layout; never shorten approved copy to fit a template.
- Keep internal framework labels/counts in the private review source only.
- Derive a clean publication source with no private production labels.
- Use `scripts/validate_public_copy.py` before public HTML/handoff.
- Repair only failed criteria. Maximum three focused repair attempts for failed work; passing work advances immediately.

### Design / wireframes / mockups

- Establish font intelligence and visitor-action plan before full wireframes.
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

Never mix external families on one page. The Secret Super Sauce is the adaptive BlackCEO house layer, not a second external style. Where a Sauce dimension conflicts with a defining trait of the selected style, the selected style wins for that dimension and compatible BlackCEO qualities remain active.

## Image planning and generation

Read the full v5 image-intelligence guide before production prompt authoring.

Non-negotiables:

- one image-map entry -> one complete prompt -> one independently generated asset -> one correctly named file;
- production prompts: **5,000–20,000 meaningful characters** under the BlackCEO house rule;
- default working target: **8,000–14,000 useful characters** because the current referenced runtime compatibility ceiling is 19,000;
- never silently truncate a prompt or disable validation;
- use camera, lens, aperture/depth, composition, subject placement, lighting, posture/expression, fashion, skin/hair, color-grade, typography-as-image, and negative-space intelligence where applicable;
- preserve real-person identity and recurring-character continuity;
- use the Black representation intelligence in the image guide when Black/African-descended subjects are present;
- keep one page-level Art Direction coherent while varying shot/view scale, ratio, environment, posture, scene type, and intensity;
- never pass human research-lineage names downstream when a style library requires branded, descriptive execution grammar.

Run `scripts/validate_prompt.py` on final prompts and `scripts/validate_image_manifest.py` on the image map.

### Image engine routing

Ask whether the owner/client has an explicit image-engine preference when generation is in scope.

- If **Kie.ai** is selected or no preference is given and Kie is available, hand the final prompt/payload requirements to **Skill 66 `kie-image`**, which owns current Kie model selection, payload validation, dispatch, and image QC. Do not hardcode a forever-model here. Skill 66 currently prefers the latest repo-approved GPT Image route when compatible.
- If **Agnes** is explicitly selected/available, use **Skill 63 `agnes-image`**.
- If another configured provider is explicitly selected, honor it if the current client environment supports it.

Paid-call approvals, client-owned credentials, provider limits, and retry rules remain owned by the executing provider skill and fleet policy.

## QC and repair

Read `references/qc-contract.md`.

- General page-stage criteria: each applicable criterion >=8/10 with no auto-fail.
- Prompt/generated-image work: retain the stricter average >=8.5, each applicable criterion >=8, zero auto-fails where the governing references require it.
- A failed artifact is repaired and rechecked before downstream use.
- Do not rework passing artifacts without a dependency reason.
- Do not invent completion: submitted generation is not completed imagery; local preview is not target-environment verification.

## Delivery

- Build only from current QC-passed copy, visual plan, approved assets, image map, and action plan.
- Preserve real forms, checkout, booking, URLs, embeds, and workflows; do not invent substitutes.
- For GHL, hand the delivery bundle to Skill 6 rather than bypassing its rail.
- Publish only when authorization is present under the current OpenClaw policy; otherwise deliver preview/staging artifacts and exact remaining action.

## Installation / maintenance boundary

`verify.sh` is an **install/update maintenance check**, not a normal page-build step. Do not run the complete skill verification every time this skill is invoked.

For onboarding-repo integration, read `REPO-INTEGRATION.md`. The repo's native-skill binding lives in `23-ai-workforce-blueprint/skill-department-map.json`; generated role blocks must be refreshed with the repo's stamper rather than hand-edited.
