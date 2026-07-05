# SOP-WEB-03: PER-SECTION IMAGE PROMPTS + IMAGES (DELEGATED)

**Cluster:** Website-Craft Rules (`universal-sops/website-craft/`)
**Owning role:** Conversion Copywriter (prompt authoring) → Skill 6 image stage (generation)
**Stage:** P2-PROMPTS-IMAGES
**Produces:** per-page `images/manifest.json` (via the Skill 6 image stage)

---

## 0. WHY THIS SOP EXISTS

A website's hero and section imagery is authored the same way the funnel's is — a strong, brand-graded
prompt per major page section, NOT one generic hero per page. This cluster does NOT re-implement the
image engine; it DELEGATES to the Skill 6 image stage (`06-ghl-install-pages` — `ghl_image_stage` /
`ghl_media.build_prompts_json`), which owns the prompt char floor, the 8-block prompt order, the
client-brand Grade Block, and the fail-loud Kie provenance.

## 1. ONE PROMPT PER MAJOR SECTION

For each page in the copy ledger, derive one image spec per major section (Home: hero + guide + success;
Services: one per service; About: founder portrait context; FAQ: optional). Feed the APPROVED
`website_copy_ledger.json` copy as the prompt's copy-context so imagery matches the words on the page.

## 2. FLOORS + PROVENANCE ARE THE SKILL 6 STAGE'S JOB

The prompt char floor, the negative/`Do not…` block, the em-dash ban, the typography lock, and the
brand-grade fingerprint are enforced by the Skill 6 image stage — this SOP does not restate the numbers
(single source of truth). A weak prompt can never reach a paid Kie call (the stage's `PROMPT_CHAR_FLOOR`
raises before spend).

## 3. VERIFY

Confirm each page's `images/manifest.json` lists a spec per major section with a resolved `cdn_url`
after generation. The rendered-`<img>` gate that binds each manifest image to the built DOM is the
Skill 6 verifier's job at build time (SOP-WEB-04).
