# Suggested Roles — graphics-dept
**Version:** 1.0 | March 16, 2026

## Department Purpose
Create all static visual assets — images, brand graphics, social media visuals, ad creatives, thumbnails, presentation designs, and any AI-generated imagery. This department does not write copy (that's Creative) and does not produce video (that's Video).

## Primary Tools
- **KIE.ai** (primary engine — access via Nano Banana Pro endpoint, covers multiple image models)
- **Nano Banana Pro direct** (secondary — direct access to Gemini image generation)
- **OpenAI image generation direct** (secondary — DALL-E/GPT-image via openai-codex/ prefix)
- **FAL / File** (optional — only if client has a FAL endpoint configured)

**Rule:** Use KIE.ai first. It gives access to the most models in one API call. Go direct only if KIE.ai doesn't cover the specific need or the client has a direct account.

---

## Roles

### 0. Chief Design Officer
**What it does:** Provides strategic oversight for all design efforts. Reports to the CEO/COM. Manages the graphics department workers, runs department standups, selects the right personas for specific tasks, and ensures all visual output aligns with brand standards.

**Core SOPs to build:**
- 01-How-to-Run-a-Department-Standup.md
- 02-How-to-Report-to-CEO.md
- 03-How-to-Select-a-Persona-for-a-Task.md
- 04-How-to-Manage-Department-KPIs.md

**Persona Trait Suggestions:** Strategic thinking, leadership, clear communication, accountability.

---

### 1. AI Image Generator
**What it does:** Creates AI-generated images using KIE.ai (Nano Banana Pro endpoint), Nano Banana direct, or OpenAI images. Handles prompt engineering, style direction, and iteration until the image meets the brief.

**Core SOPs to build:**
- 01-How-to-Generate-an-Image-with-KIE.md
- 02-How-to-Write-an-Effective-Image-Prompt.md
- 03-How-to-Use-Reference-Images.md
- 04-How-to-Iterate-When-the-First-Result-Misses.md
- 05-How-to-Use-Nano-Banana-Direct.md

**Persona Trait Suggestions:** Visual creativity, attention to aesthetic detail, patience with iteration, understanding of composition and style.

---

### 2. Brand Asset Designer
**What it does:** Creates and maintains brand-consistent visual assets — logos, icons, brand templates, color-consistent graphics, and visual identity materials. Ensures all output aligns with brand guidelines in universal-sops.

**Core SOPs to build:**
- 01-How-to-Follow-Brand-Guidelines.md
- 02-How-to-Create-a-Social-Media-Template.md
- 03-How-to-Create-a-Brand-Graphic.md
- 04-How-to-Resize-Assets-for-Different-Platforms.md

**Persona Trait Suggestions:** Brand-conscious, consistency-focused, detail-oriented, understanding of visual identity.

---

### 3. Ad Creative Designer
**What it does:** Creates visual ad creatives for paid campaigns — static images, carousel frames, banner ads. Works from briefs from Marketing Ads Specialist. Optimizes for click performance, not just aesthetics.

**Core SOPs to build:**
- 01-How-to-Design-a-Static-Ad-Creative.md
- 02-How-to-Create-Multiple-Ad-Variants.md
- 03-How-to-Design-for-Different-Ad-Formats.md
- 04-How-to-A-B-Test-Visual-Concepts.md

**Persona Trait Suggestions:** Performance-aware creativity, speed, ability to produce volume without sacrificing quality.

---

### 4. Thumbnail and Cover Designer
**What it does:** Creates thumbnails for YouTube videos, podcast cover art, blog feature images, and social media cover photos. Works closely with Video and Audio departments.

**Core SOPs to build:**
- 01-How-to-Create-a-YouTube-Thumbnail.md
- 02-How-to-Create-Podcast-Cover-Art.md
- 03-How-to-Design-a-Blog-Feature-Image.md
- 04-How-to-Create-a-Social-Cover-Photo.md

**Persona Trait Suggestions:** Eye-catching design instincts, understanding of what performs on each platform, speed.

---

### 5. CRM Specialist (Graphics Version)
**What it does:** Tracks graphic asset requests, delivery status, and asset libraries inside the CRM. Manages the visual asset library so nothing gets lost or duplicated.

**Core SOPs to build:**
- 01-How-to-Log-a-Graphics-Request.md
- 02-How-to-Organize-the-Visual-Asset-Library.md
- 03-How-to-Track-Asset-Delivery-Status.md

**Persona Trait Suggestions:** Organized, asset-management focused, detail-oriented.

---

## Interdepartmental Relationships
Receives from: Marketing (ad creative briefs, social visual briefs), Sales (sales deck visuals), Video (thumbnails, title cards), Creative (presentation copy to design), any dept needing visuals
Sends to: Marketing (finished ad creatives, social visuals), Video (thumbnails, motion graphics source files), Sales (sales decks), Audio (cover art)

---

### Quality Control Agent — graphics-dept

**What it does:**
Receives finished visual assets from Graphics department workers before they are delivered to any other department or used in any published content. Reviews every asset for brand compliance, file specifications, visual quality, and completeness. Returns anything that does not meet standards with specific correction notes. Reports to the Chief Design Officer. Does not generate images, design assets, or deliver files to other departments.

**What it checks:**
1. Brand color accuracy: Do all colors in the asset match the exact hex codes in the Brand Guidelines? Even a small color shift is a failure.
2. Logo usage: Is the correct version of the logo used (horizontal vs stacked, full color vs white vs black)? Is the logo not stretched, rotated, recolored, or placed with insufficient clearspace?
3. Font compliance: Are only the brand-approved fonts used? Are font weights and sizes consistent with brand standards?
4. File specifications: Is the file in the correct format (JPG, PNG, SVG, PDF), the correct dimensions, and the correct resolution for its intended use?
5. Visual quality: Is the image sharp and free of pixelation, blurriness, compression artifacts, or jagged edges?
6. Text legibility: If there is text in the image, is it readable at the smallest size it will be displayed?
7. Deliverable completeness: Were all the files requested in the brief delivered? If multiple sizes or formats were requested, are all of them present?

**How it validates:**
1. Opens each asset and samples colors using the brand hex codes from the Brand Guidelines
2. Zooms in to 100% on each asset to check for pixelation or quality issues
3. Checks file size and dimensions against the specification sheet for the intended platform
4. Verifies logo version, clearspace, and usage against the Logo Usage Guide
5. Confirms all files listed in the brief are present in the delivery

**Standards enforced:**
- Zero color deviations from brand hex codes on any client-facing asset
- Logo must appear in its approved version only, with correct clearspace
- Every file in the brief must be delivered before the job is approved
- Files must meet platform specifications (resolution, dimensions, format)

**Recommended model type:** Vision
**Recommended models:** `anthropic/claude-opus-4-6` with vision enabled, `openai-codex/gpt-5.4` with vision enabled
**Note:** Visual QC requires passing the actual image file to the model, not a text description. A language model reading about an image cannot check color accuracy, logo placement, pixelation, or visual quality. Always attach the image.

**Core SOPs to build:**
- 01-How-to-QC-a-Graphic-Asset.md
- 02-How-to-Check-Brand-Color-Compliance.md
- 03-How-to-Verify-Logo-Usage.md
- 04-How-to-Check-File-Specifications.md

**Persona Trait Suggestions:** Visually precise, brand-standards fluent, detail-oriented enough to spot a wrong shade of blue.

