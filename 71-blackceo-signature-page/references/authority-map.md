# BlackCEO Signature Page Authority Map

Use this map before loading detailed references.

## Authority order

1. Latest explicit user/client instruction for the current assignment.
2. `references/BlackCEO-Page-Brand-Law.md` plus the run's brand file (`intake.json` -> `brand_file`; `assets/brand/blackceo-brand.json` for BlackCEO pages) are the top authority for page colors, fonts, logo/masthead, and founder imagery. An agent never proposes page tokens.
3. `BlackCEO-Signature-Landing-Page-Production-and-QC-SOP-v1.md` for production sequence, gates, repair, implementation, and handoff.
4. The selected writing guide for copy architecture:
   - `BlackCEO-Signature-Landing-Page-Standard-v6.md`, or
   - `BlackCEO-Signature-Landing-Page-Long-Form-v6.md`.
5. `BlackCEO-Signature-Image-Intelligence-and-Prompt-Creation-Guide-v5.md` for current image planning, art direction, Secret Super Sauce, representation, prompt construction, and visual QC.
6. When an external page-level Creative Direction is active, the one selected family library and the one selected branded style block.
7. OpenClaw repository/runtime constraints and current client-tool capabilities.

If a lower authority conflicts with a higher authority, preserve the higher authority and record the conflict rather than silently blending them.

## Supersession note

The Production SOP and writing guides were written when the Image Prompt Creation Guide v1 was current. Inside this skill, `BlackCEO-Signature-Image-Intelligence-and-Prompt-Creation-Guide-v5.md` is the current successor for image planning and prompt work. Do not fall back to the old v1 image guide merely because an older document names it.

## Creative Direction rule

For one page, activate at most one external family/style:

- one Photographic Direction, or
- one Cinematic/Directorial Direction, or
- one Visual-Artist Direction, or
- no external style, using Secret-Sauce-only.

The BlackCEO Secret Super Sauce is not a second family. It is an adaptive house layer. Preserve compatible Sauce traits; when one dimension truly conflicts with the selected style, the selected style controls that dimension and the unaffected BlackCEO quality rules remain active.

## Visual reference status

`../assets/BlackCEO-Master-Visual-Reference-Guide.png` is an image-style menu only. It is not a page-layout or page-color reference. Written style IDs, names, and descriptive execution rules remain authoritative if a visual shorthand or label differs.

## Prompt and image QC thresholds

For prompts and images, `qc-contract.md` thresholds win over any style library: average >=8.5, each applicable criterion >=8, maximum 3 repair attempts.

## Prompt-length compatibility

Owner order 2026-10-05 (`07-kie-setup/references/kie-common-rules.md` rule 12) governs: a descriptive prompt uses 95 to 100 percent of the chosen model's character maximum and is never below 80 percent. The maximum comes from Skill 74 `prompt-budget` (live schema, registry fallback), never from memory. This supersedes the older 5,000-20,000 house band, the 8,000-14,000 working target and the 19,000 runtime-compatibility note wherever this skill still states them. Do not disable validation or silently truncate.

## Delegation seams (OpenClaw)

Route delegation through these seams; do not duplicate the receiving skill's provider client, browser manager, GHL builder, deployment client, or credential storage.

- **Images and video:** policy owner **Skill 66 `kie-image`** (images) or **Skill 67 `kie-video`** (video), then transport **Skill 74 `kie-live-adapter`**, per `references/kie-generation-route.md`; **Skill 63 `agnes-image`** when Agnes is explicitly selected/available. Do not hand-roll provider calls here.
- **GHL delivery:** delegate media/page build to **Skill 6 `ghl-install-pages`**, the existing GHL delivery rail.
- **Vercel:** use **Skill 8 `vercel-setup`** when that hosting target is selected and configured.
- **Browser automation:** use the repo's managed browser path / Skill 3 conventions when graphical browser work is required.
