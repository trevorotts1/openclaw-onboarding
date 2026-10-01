# Signature-Page-Craft SOP Cluster (`universal-sops/signature-page-craft/`)

The SHARED, cross-department procedure for how any department discovers and drives the **BlackCEO
Signature Page engine (Skill 71)** end to end: intake -> Standard/Long-Form copy -> font/action plan ->
desktop wireframe -> mobile/tablet -> visual mockup -> image inventory/prompts -> image generation/QC ->
image map/upload -> final mockups -> responsive HTML -> target install/test -> publish/verify when
authorized.

This cluster is the `universal-sops` face of the capability. It does NOT re-implement the skill. The
authoritative machine spine lives in the skill:

- `71-blackceo-signature-page/SKILL.md` -- route boundaries, seams, production order, copy/design/QC/delivery contracts, install-boundary rule.
- `71-blackceo-signature-page/references/authority-map.md` -- the authority order (client instruction > Production/QC SOP > selected writing guide > image-intelligence guide v5 > one external Creative Direction family > repo/runtime constraints).
- `71-blackceo-signature-page/references/BlackCEO-Signature-Landing-Page-Production-and-QC-SOP-v1.md` -- the 14-stage production/QC stage state machine.
- `71-blackceo-signature-page/references/qc-contract.md` -- page-stage >=8/10 no-auto-fail; prompt/image >=8.5 average, >=8 each, zero auto-fails where required; failed-only repair.
- `71-blackceo-signature-page/references/BlackCEO-Signature-Landing-Page-Standard-v6.md` OR `...-Long-Form-v6.md` -- the selected writing guide (never both silently merged).
- `71-blackceo-signature-page/references/BlackCEO-Signature-Image-Intelligence-and-Prompt-Creation-Guide-v5.md` -- image planning, Secret Super Sauce, representation, prompt construction, visual QC.
- `71-blackceo-signature-page/references/artifact-contracts.md` -- the private/public output tree + workflow-state/image-map/review-PDF JSON contracts.
- `71-blackceo-signature-page/scripts/validate_state.py`, `validate_public_copy.py`, `validate_prompt.py`, `validate_image_manifest.py`, `combine_review_pdf.py`, `validate_review_pdf.py` -- the deterministic model-free validators.

Read only what the current stage needs. Do not load all three style libraries at once. Load only the
selected family/style when needed.

<!-- CRAFT_INTENT_TRIGGERS_V1 -->
## Intent triggers

This craft cluster (`universal-sops/signature-page-craft/`) is the execution playbook for the skill(s) below. A specialist reaches for it when the client's plain-language request matches any of these intents — the client never has to name the skill or type its slash command. Source of truth: `23-ai-workforce-blueprint/skill-department-map.json` (Layer D).

| Skill | Reach for this craft when the client says… |
|---|---|
| **71** blackceo-signature-page | "build me a landing page" · "build my landing page" · "create a BlackCEO landing page" · "create a signature landing page" · "build an opt-in page" |

Dept-scoped: only the task department's craft is offered. Operate the owning skill per the SOPs in this cluster **before** authoring by hand. Rule-Zero paid-call approval (USD announce + budget cap) still applies. Doctrine: `universal-sops/native-skill-invocation.md`.
<!-- END CRAFT_INTENT_TRIGGERS_V1 -->

## Files

| File | What it governs |
|---|---|
| `README.md` (this file) | The cross-department pointer + the routing/delegation boundary for Skill 71. The stage SOPs live in `71-blackceo-signature-page/references/`; this cluster does NOT restate them. |

The detailed methodology is intentionally NOT duplicated here -- the 14-stage Production/QC SOP, the
Standard/Long-Form writing guides, the image-intelligence guide, and the artifact contracts live
authoritatively in the skill folder. Adding SOP files to this cluster would create a second source of
truth for a 20,000+ line reference set.

## The ONE way in

Skill 71 ships no entry shell, no run-dir orchestrator, and no gate-code family. The deterministic
rail for a page build is the skill's own model-free validators, run per stage as the workflow-state
dictates:

```
python3 71-blackceo-signature-page/scripts/validate_state.py <workflow-state.json>
python3 71-blackceo-signature-page/scripts/validate_public_copy.py <public-copy.md>
python3 71-blackceo-signature-page/scripts/validate_prompt.py <prompt.md>
python3 71-blackceo-signature-page/scripts/validate_image_manifest.py <image-map.json>
python3 71-blackceo-signature-page/scripts/combine_review_pdf.py <review-manifest.json>
python3 71-blackceo-signature-page/scripts/validate_review_pdf.py <pdf> <receipt.json>
```

Requests must route to the page family FIRST (see the routing boundary below). Routing into the
neighbouring engines (49 multi-step funnel, 56 direct-response stack, 62 cinematic) is the boundary,
not a bypass -- do not force a single-page request through another engine's entry shell, and do not
author a BlackCEO page by hand when this skill is available. Do not hand-roll provider calls, GHL REST
calls, or browser automation; those rails are delegated (see Delegation seams).

## Routing boundary (single-page vs the four neighbours)

This table is the disambiguation contract. A plain "landing page" request must be claimed exactly once.

| Skill | The request it owns |
|---|---|
| **71** blackceo-signature-page | focused single-page BlackCEO conversion experience: landing, opt-in/squeeze, event/registration, challenge, booking, lead-generation (Standard or Long-Form) |
| **49** signature-funnel | multi-step 3/5/7 Signature Funnel with checkout / upsell / downsell / OTO chain |
| **56** sales-page-assets | Direct-Response / VSL / 8-section main / 9-section upsell / high-ticket / order-bump asset stack |
| **62** cinematic-web-funnel-engine | animated / immersive / scroll-controlled cinematic website or funnel |
| website-craft | ordinary multi-page marketing website whose governing copy contract is not the BlackCEO single-page system |

If the owner explicitly asks for the BlackCEO Signature Page skill, use it even when the page
ultimately hands delivery to another rail. The reciprocal rows live in `universal-sops/funnel-craft/`
and `universal-sops/sales-page-craft/`; this table changes only when the skill-department map changes,
and the generated blocks in those sibling clusters re-stamp from the map rather than being hand-edited.

## SACRED law / non-negotiables (from the skill's own references)

- Copy leads layout -- never shorten approved copy to fit a template (`SKILL.md` Copy).
- Select Standard OR Long-Form; never silently merge both; never auto-switch.
- Internal framework labels and counts stay in the private review source; the publication source carries no private production labels.
- One page = at most ONE external Creative Direction family (Photographic OR Cinematic/Directorial OR Visual-Artist) or Secret-Sauce-only; never mix families on one page; Secret Super Sauce is the adaptive house layer, not a second style.
- Image prompts: house rule 5,000-20,000 meaningful characters; default working target 8,000-14,000; the referenced runtime validator currently rejects above 19,000 -- never disable validation, never silently truncate.
- One image-map entry -> one complete prompt -> one independently generated asset -> one correctly named file.
- Never pass human research-lineage names downstream when a style library requires branded, descriptive execution grammar.
- QC: page-stage criteria each >=8/10 with no auto-fail; prompt/generated-image work retains average >=8.5, each criterion >=8, zero auto-fails where the governing references require it.
- Repair only failed criteria, max three focused attempts; passing work advances immediately and is not reworked without a dependency reason.
- Do not invent completion: submitted generation is not completed imagery; local preview is not target-environment verification.

## Delegation seams (what this skill does NOT fork)

- Images: delegate execution to **66 kie-image** when Kie.ai is selected, or **63 agnes-image** when Agnes is explicitly selected/available. Do not hand-roll provider calls. Paid-call approvals, client-owned credentials, provider limits and retry rules stay owned by the executing provider skill and fleet policy.
- GHL media + page build: delegate to **06 ghl-install-pages**, the existing GHL delivery rail.
- Vercel hosting: **08 vercel-setup** when selected and configured.
- Browser automation: the repo's managed browser path / Skill 03 conventions when graphical browser work is required.
- Primary department web-development / primary role landing-page-specialist; copy collaboration with marketing conversion-copywriter when the current execution assigns it -- this skill's writing references remain the page-specific authority.

Do not duplicate another skill's provider client, browser manager, GHL builder, deployment client, or
credential storage.

## Deliverable naming + private/public separation

`references/artifact-contracts.md` defines a PROJECT TREE, not a label grammar:

```text
project/
  private/   workflow-state.json, internal-copy.md, copy-manifest.json, page-visual-bible.md, image-map.json, qc/
  public/    public-copy.md, html/
  wireframes/desktop/, wireframes/mobile/
  mockups/desktop/, mockups/mobile/
  images/prompts/, images/generated/
  review/    desktop-wireframes.pdf, mobile-wireframes.pdf, desktop-mockups.pdf, mobile-mockups.pdf
```

Four JSON contracts govern handoff: the workflow-state JSON (exact ordered stage names, attempts 0-3),
the image-map JSON (one entry per intended generated master asset; crops point to a `master_id`), the
copy manifest, and the review-PDF manifest (the manifest is the authority for page order -- never
lexicographic filename sorting; `combine_review_pdf.py` writes the PDF plus a SHA-256 receipt).

Separation rule: the private review source carries the internal production labels; the public handoff
carries none. A page delivered to a client never ships the private tree. This cluster does NOT publish
the `<client>__<funnel>__<stage>__<type>__vNN` label grammar -- that grammar belongs to Skills 49/56/62
and their clusters; asserting it here would invent a contract the skill does not have.

## Flexibility = guide-not-rule

The skill is a GUIDE and a RESOURCE for how a department fulfils a page request; honour an explicit
owner choice (page length class, creative-direction family, image count) and record it. But the copy
contract, the QC floors, the one-external-family rule and the image-prompt band are enforced by the
skill's own validators and references and are not opinions. Client-exact overrides win over default
bands and are logged; they never override the public/private separation or a QC floor.

## Client-runtime rule (binding)

The shipped skill on a client box NEVER uses Anthropic / `claude-*` models or operator keys.
Authoring/QC run on the CLIENT's own configured provider chain; image execution delegates to the
client's selected image provider skill; the deterministic validators (`scripts/validate_*.py`,
`combine_review_pdf.py`) are provider-neutral Python and run identically everywhere. Publishing is
human-approved (preview URLs + a labeled `~/Downloads/` bundle).

Source caveat: this is the repo's binding fleet rule and every sibling cluster carries it, but the
skill package itself does not currently ship a provider-purity scan in `verify.sh` (unlike
`sales-page-assets`). Treat the rule as binding anyway; adding a purity check to the skill's
`verify.sh` is a separate, explicitly-recorded decision.

## Installation / maintenance boundary

`71-blackceo-signature-page/verify.sh` is an install/update MAINTENANCE check, not a page-build step --
do not run the full skill verification on every invocation. For repo integration read the skill's
`REPO-INTEGRATION.md`; the native binding lives in `23-ai-workforce-blueprint/skill-department-map.json`
and the generated role/guide/craft blocks are refreshed with the repo's stampers, never hand-edited.
