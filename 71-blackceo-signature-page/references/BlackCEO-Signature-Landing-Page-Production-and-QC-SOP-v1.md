# BlackCEO Signature Landing Page Production and QC SOP

**Version:** 1.0 | **Date:** September 30, 2026  
**Owner:** Trevor Otts / BlackCEO  
**Scope:** A universal process for funnel-type pages: landing pages, opt-in/squeeze pages, event/registration pages, challenge pages, sales pages, booking pages and comparable focused visitor journeys. Direct-response sales pages (VSL, 8-section main, high-ticket, order-bump asset stacks) belong to Skill 56 `sales-page-assets`. This SOP's sales-page notes apply only to a single BlackCEO Signature page the owner explicitly assigns here. A multi-page marketing website whose governing copy contract is not this BlackCEO single-page system is website-craft work, not a signature page, however similar the pages look.  

**Product-creation scope (Update Plan Item 24 / proposal P3):** Creating a missing GHL product is inside this job's scope exactly once per missing product: only after an existence check proves it absent, only the product the funnel's order form binds, and always recorded in the funnel-completion receipt (Item 32). Everything else about products (pricing changes, catalog management) stays outside this job.
**Status:** Production instructions. Creating this document does not publish a page, update GitHub, authorize payment, or certify a live implementation.

## Start here: the four connected documents

| Document | Its job |
|---|---|
| [Standard writing guide v6](BlackCEO-Signature-Landing-Page-Standard-v6.md) | The original twelve-section writing system and its compact length/CTA rules. |
| [Long-form writing guide v6](BlackCEO-Signature-Landing-Page-Long-Form-v6.md) | Expanded writing with the three inserted solution sections and the long-form CTA map. |
| **This production and QC SOP** | The order of work, checks, repairs, current-version handoffs, implementation and delivery. |
| [Image Prompt Creation Guide v1](BlackCEO-Signature-Image-Intelligence-and-Prompt-Creation-Guide-v5.md) | Repository-led prompt anatomy plus section-based camera, face, hair, tone, composition and color-grade intelligence. |

Choose the writing guide for the requested page. Do not build both standard and long form by default. The image guide is required reading before image planning is finalized and before any image prompt is authored. The two writing guides point here so they do not carry competing copies of the entire production process.

Set for Life supplied lessons for this workflow. Its name, founder, free attendance, duration, palette, form, 22 images and assets are not universal defaults. Do not borrow one client's information or resources for another.

**The governing order:** confirm the page and action -> write and QC/repair the copy -> font intelligence and action plan -> full desktop wireframe -> full mobile wireframe and tablet rules -> visual bible and internal layout proof -> individual image prompts and QC/repair -> generate and QC/repair images -> upload and complete Image Map -> the mockup: finalize the layout proof per section with the real assets (the single client-judged mockup) -> responsive HTML and QC/repair -> install/test in GHL -> publish when authorized and verify the public result -> wire the follow-up automations when the intake's automation scope includes them (conditional Stage 15).

Every selected page version gets **four images: desktop wireframe, mobile wireframe, desktop mockup, and mobile mockup**. The mobile wireframe and the mobile mockup are each produced at the mobile width, never a desktop image resized to mobile. Creating the reusable standard/long-form template set means producing that set's four images for each page version: standard desktop, standard mobile, long-form desktop, long-form mobile. Exporting a long wireframe in Parts A-M does not create thirteen different pages.

## Non-negotiable rules

**A. Copy leads layout.** Use every required paragraph, headline, inclusion, benefit, onboarding step and founder-letter passage. Layout can grow. It cannot silently summarize or rewrite the copy.

**B. Private production structure never reaches visitors.** Section names, framework numbering, founder-letter part labels, asset IDs, QC scores, prompts and developer notes belong in private working files. Remove them from public copy, image pixels, mockups, final HTML, accessible names, tooltips, comments and shipped data. CSS hiding is not removal. Use neutral implementation IDs instead of names exposing the private framework. Real customer-facing step numbers, dates and approved image text are not private labels.

**C. Latest explicit client direction wins over defaults.** A supplied opening is not replaced with a generic claim. A free event is not changed into a purchase. A request for mobile is not answered with desktop. Never import factual details or language from fictional teaching examples into a client page.

**D. Failed work cannot advance.** A repaired artifact is not ready until it is rechecked. Pass only the current QC-passed version downstream. Do not put rejected predecessors beside the new files in the delivery package.

**E. No invented completion claims.** A text file must exist before linking it. A ZIP must contain the promised assets. A local browser test is not a GHL test. A submitted image task is not a completed image. A writer cannot invent independent QC credentials.

**F. No added claim-auditing assignment.** Client-claim verification and substantiation remain with the human reviewer. AI checks adherence to the supplied materials and marks missing inputs internally; it does not fabricate them or independently downgrade the client's positioning.

## QC and repair rule used at every stage

### A. What passes

For page-stage work, every applicable required quality criterion must score at least **8/10**, with no automatic failure. A section at 6 cannot be hidden by an overall average of 9. The goal is strong work, not artificially inflating a score.

For prompts and generated images, this skill carries its own scoring bar, vendored into the Image Guide's QC section and `references/qc-contract.md` (Update Plan Item 21, Decision 5: the skill carries its own standard and defers to no external repository for this bar): retain the **8.5 minimum average**, with **every individual applicable criterion at least 8** under Trevor's newer requirement, and zero auto-fails. The per-image prompt length is the KIE prompt budget (owner order 2026-10-05, `07-kie-setup/references/kie-common-rules.md` rule 12: 95 to 100 percent of the chosen model's character maximum, never below 80 percent), which supersedes the older 5,000-20,000 range and the 19,000 ceiling. This document does not change live validators.

A missing requirement, wrong image, exposed private label, unsupported route, truncated text, broken main action, or unresolved public placeholder is an automatic failure, regardless of aesthetic score.

### B. Three repair attempts, only for failed work

Perform the initial QC. If the item passes, move it forward immediately. Do not perform three additional reviews or revisions.

If it fails, repair the named defect and recheck it. Allow up to three focused repair-and-recheck attempts. Stop immediately when it passes. If it still fails, escalate with the exact blocker rather than looping indefinitely or changing the brief. A stricter existing repository trigger, such as three consecutive failed assessments on the same defect, is honored earlier. Do not bypass it to consume three more attempts.

Escalation first goes to the relevant lead/Chief Design Officer or other configured expert, not a routine client sign-off request. Ask the human only for missing facts, required access, budget/permission or an instruction conflict that the system cannot legitimately resolve. Do not mark the failed item passed merely because the retry allowance is exhausted.

Recheck repaired content and its directly affected neighbors/dependencies. Leave unrelated passing work alone. A changed image crop, altered headline, new URL or modified code creates a relevant recheck; an unchanged passing file does not.

### C. Who reviews and what is recorded

The creator performs mechanical checks before handoff. The configured independent reviewer grades the artifact, not the creator's description of it. For Graphics, retain the repo's separate Prompt Author, Prompt QC, Generation Operator and image-QC responsibilities. Routine human approval is not required for prompts or images.

A short internal record is sufficient: artifact ID, version/hash, score by criterion, auto-fail codes, specific repair, check result and next destination. Do not create a separate report-writing phase or require the client to approve that record. If the environment cannot perform a required independent review or live check, report the limitation; do not simulate it.

### D. Current-version handoff

Maintain one `current` manifest or equivalent list. Failed work lives in a private working location; only passed artifacts are listed as ready. When a repaired asset passes, update the current pointer and its references. Copy writers, designers, image generators and coders all read that same current manifest.

This is what "source of truth" means here: use the right current file. This is what "change control" means here: do not quietly change it, and do not send an old version forward. No extra committee or mandatory human approval loop is implied.

## Stage 1 - Confirm what we are building and what visitors should do

### A. Read first, ask only what is missing

Read the supplied transcript, copy, brand guide, references and existing page. Skip answered questions. Ask in plain language, not a long technical questionnaire.

| Needed decision | Client-facing wording |
|---|---|
| Page type, name and subject | "What kind of page are we building, what is it called, and what is it about?" |
| Intended action | "What should people do: sign up, get something free, buy, book, or something else?" |
| Hosting | "Will we build it directly in GoHighLevel, or build it on Vercel and embed it into GoHighLevel?" |
| Existing materials | "Send any copy, recording/transcript, brand guide, logo or page example you already have." |

The AI can state its understanding of the selected standard/long-form version from the assignment. Ask the client to choose only when that is unresolved. A squeeze page does not authorize silently removing required sections from the chosen signature system; clarify an explicitly shorter alternative once when necessary.

### B. Ask the correct action question

For opt-in, event and registration pages: "Have you already created the form in GoHighLevel? If so, send the embed code." Then, only if unknown: "Should people see the form on the page, or should it pop open when they click a button?" Use the client's existing separate form-page link if that is their chosen flow.

For a single BlackCEO Signature sales page the owner has explicitly assigned here: "Do you already have a checkout page or payment link for this offer? Send that link. If customers should pay directly on this page or in a popup, send the supported checkout embed code, if available."

A checkout URL is sufficient when the button goes to a checkout page. Do not demand a widget too. Do not assume every native GHL order form has portable embed code. If no checkout exists, collect the actual product, price/currency, one-time or recurring schedule and configured payment provider as a separate setup task. Do not put a homemade credit-card form into the landing-page HTML. [W5]

For booking: request the existing booking link or supported booking embed. For a download/lead magnet: request the actual form action and delivery destination. For a challenge: capture the actual dates/duration and access delivery only when missing. Do not assume all challenges are free or all events are ninety minutes.

### C. Record the outcome and only the needed image questions

Record the image-engine answer in the intake stage with `scripts/write_intake.py <run_dir> ... --image-engine kie|agnes` (default kie); `stage_gate.py` reads it, and the intake stage will not close without `image_engine` in `intake.json`.

Record the funnel handoff in the same intake record: the Convert and Flow form's name and object id (`--handoff-form-name` / `--handoff-form-id`), the pop behavior, and the step order (signature page, then product selection page, then order form page). When no form identity exists yet, record the handoff as the explicit missing input with its reason (`--handoff-missing-reason`) instead. A placeholder destination (a `#join`-style link) is never a handoff: it is either the recorded missing input or a defect the page build must repair.

Record what successful action produces: confirmation, download, event access, booking or checkout success. Reuse existing workflows; do not fabricate bonuses, SMS flows or communities. Collect exact founder/brand names and usable logo/identity assets where required.

Use the image guide's short conditional questions for missing visual decisions: who to show, references, real-person identity, tone/hair preferences, grade and image text. Do not make the client select cameras or write prompts.

**Output:** a compact private page/job record with available source files and unresolved essentials. **QC/repair:** correct page type, action, hosting and audience; no invented facts. Proceed only when the next stage has its required inputs. Independent tasks can continue while a genuinely separate input is being obtained.

## Stage 2 - Write or rewrite the complete copy

### A. Use the selected writing guide

Write the actual opening first. Follow the version-specific sequence, CTA locations, length rules and source material. The standard guide has twelve original sections; long form inserts the three matching solutions. Neither version becomes generic sales-page copy because it is easier to lay out.

Preserve a client's explicit opening and positioning. The generic teaching rule about leading with a bold possibility does not authorize overriding a specific opening the client has supplied. Keep benefits distinct and every solution connected to its preceding pain. The founder letter uses supplied personal material; a production conversation is not automatically a meaningful founder struggle.

### B. Grade the words, not only the structure

Check the actual opening, emotional recognition, solution specificity, conviction in the Why, audience fit, clear inclusions, distinct benefits, practical action steps, founder connection, voice and continuity. Use the detailed tests in the writing guide. Check the selected version's exact CTA map and applicable counts separately.

Repair each criterion or section below 8. A single unclear solution cannot advance because the pain writing scored highly. Repair the passage, not the user's framework. Recount changed text and review its immediate transition.

### C. Produce two separated views of the same copy

Keep an internal review manuscript with exact framework labels, counts and private notes. Derive a clean publication source with only audience-facing text and semantic elements. Keep button labels as data with their actual wording, not the visible text "CTA BUTTON". Do not send internal labels through a website renderer and rely on CSS to conceal them.

**Output:** current QC-passed internal manuscript, clean public copy source and copy manifest. The copy manifest's CTA entries carry each button's handoff type (`form_pop`, `in_page_anchor`, or `external_link`); the primary CTA's type is `form_pop`, the pop of the form intake names. **QC/repair:** exact copy parity between the public view and all intended customer-facing source passages; no missing words or leaked instructions. Delivery follows the selected writing guide: Markdown in standalone chat, Google Docs first where configured, Notion next where configured, otherwise MD/TXT; Word when explicitly requested. Rendered document text is at least 12 points where controllable. These documentation choices do not affect the website's CSS-pixel typography.

## Stage 3 - Establish font intelligence and the visitor-action plan

### A. Map the fonts before full wireframes

Use the fonts in the run's brand file (`intake.json` -> `brand_file`) exactly — display, body, and accent roles come from `references/BlackCEO-Page-Brand-Law.md` and that file, never from an agent's proposal. If the brand fonts are missing, derive the best display/body/accent for the job, and document the derivation in the font map (`fonts_source: "derived"`, `font_rationale`, `font_reviewer` naming the visual-mockup stage's independent bible reviewer as the designate, a forward reference only); the three fields are lifted verbatim into the visual bible, and the approval is recorded there, exactly once, at the bible review: fonts are never blocked (`font_policy.when_brand_fonts_missing: "derive-document"`), and derived faces stay bound by the brand file's `banned_fonts`, and no approval is recorded at this stage. Google Fonts by default supplies those faces, or a deliberately selected Google Fonts equivalent for an otherwise unavailable/proprietary face; do not claim the substitute is the original font detected in a raster mockup. Existing logos remain artwork.

Map actual family names, real weights/italics, role, desktop/tablet/mobile size and line height, emphasis, readable colors, wrapping, margins and fallback behavior. Use the actual longest copy and CTA wording. Avoid forcing one client's four font choices onto every future client. Google Fonts supports requesting named families and selected variants. [W1]

### B. Check fonts at the appropriate time

Confirm family/variant availability while preparing the map. As the wireframe is rendered, check that its renderer loaded the intended fonts. This is part of rendering the wireframe, not a separate website build or GHL setup. Do not label a fallback-font output an exact-font proof.

When HTML exists, check loaded FontFace entries and rendered typography in the actual browser. `document.fonts.load()` returns loaded font faces; a stylesheet declaration alone is not loading evidence. Inspect the actual glyphs used in headings/body; do not treat font loading as proof of every glyph or visual fit. [W2]

### C. Define how the action and motion work

Record on-page form versus button-triggered popup versus separate page. Specify close behavior, keyboard focus, return to scroll position, mobile scrolling, loading/error handling and actual success destination. Plan restrained reveals/hover/popup effects where desired, with reduced-motion behavior and readable content when scripts fail. A mockup's attractiveness does not establish these interactions.

**Output:** font map and compact action/motion specification. **QC/repair:** correct family/role choices, clear action, readable type and no contradictory behavior. No new temporary website or human sign-off round solely for fonts.

## Stage 4 - Create the entire desktop wireframe

**Layout references resolve in order; only an unresolved reference stops the stage.** Before drawing, resolve each required layout reference: first the supplied or bundled original file; where the original is absent, the approved house default recorded for that reference in the standing registry, `assets/page-references/substitutions.json`; and only where neither exists, a recorded owner waiver with its reason. A reference with none of the three fails the gate by name. Every run records which source each reference used, and REPORT.md prints it: a fallback is visible, never silent. The same resolution governs the mobile wireframe and visual-mockup stages.

### A. Build the annotated spec sheet around the exact public copy

The desktop wireframe is a designed, annotated build spec rendered as images, in the client's brand colors from the brand file. It is not an HTML render and is never a screenshot of a web page. Build it section by section around the full copy at its mapped type scale: show real headlines, paragraphs, titles, descriptions, benefits, complete steps and the letter. Preserve live-copy priority above the fold.

Every section is one spec image (a section slice), and each slice carries, printed on the sheet:

- the section's number and name, against the selected guide's section standard;
- the printed type specs for the section's elements (heading, body and CTA sizes);
- every image slot as a deliberate placeholder, labeled with its aspect ratio and its art direction (what the image must show), never a generated photo masquerading as a wireframe and never a bare empty box;
- the run's real copy, and CTA chips showing the real button text with their microcopy specs;
- the section's behavior notes (for example "No CTA"; "Typography-only response").

A header strip on the sheet states the page width and the content width. The annotations are production markings on a private build spec: they are not page copy, they never carry into the mockups or the HTML, and the layout they annotate shows only real copy and real CTA text.

Create a creative composition through meaningful hierarchy, mixed image proportions, offset frames, varied scale, typography-only panels and spacing. Do not substitute a monotonous stack of identical editor blocks. Creativity does not justify random order or missing content.

### B. Start the image inventory

Assign every requested generated image its stable ID, intended role, dimensions/aspect, desktop slot and expected mobile role. Identify existing logo/product/identity assets separately. Zero-image panels remain valid. Read only the image guide's crop/face/hair requirements section during this planning so crop, face, hair and scene requirements are not discovered after the layout is locked. The art direction printed on each slot's label is that slot's inventory role, stated on the sheet so the layout and the inventory cannot drift apart.

### C. Deliver the spec image set

Deliver the wireframe as one spec image set: the section slices (`desktop-wireframe/section-*.png`, one per section, in section order, each at the full 1440px page width and its section's native height), one stitched full-page PNG (`desktop-wireframe/wireframe-full.png`) assembled from the slices in section order, and one combined PDF (`desktop-wireframe/wireframe.pdf`) of the same slices in the same order. The stitched PNG and the combined PDF match the slices section for section: every section appears exactly once, in order, in each form. A private assembly map records the slice order and each slice's file. Never shrink or cut a section to fit an export length; a tall section is simply a taller slice.

**Part naming:** each section slice is one part of the wireframe export, and every part carries two names for the same file. The human-facing name is lettered: the first slice in section order is Part-A, the second is Part-B, and later slices continue with consecutive letters in section order. The lettered names are the names people use: they appear on human-facing exports and listings (for example the review PDF's page labels), and they never become page headings. The machine name is numeric: the slice's file name in its stage folder (`section-01.png` for the first slice, `section-02.png` for the second, and so on), and every machine record uses the machine name only (the stage contract's artifact globs, validator output, and any review item id derived from the file). The private assembly map is where the two names meet: for each slice, in order, it records the machine name (the file), the human-facing name (its Part letter), and the number and name of the section the slice carries. The stitched `wireframe-full.png` and the combined `wireframe.pdf` are single files and carry no part name. When a part name is ambiguous, the assembly map is the authority for which file a Part letter means.

**Output:** the desktop wireframe spec image set (section slices, stitched full-page PNG, combined PDF) and the private layout/image inventory. **QC/repair:** every section numbered and named with its type specs printed; every slot labeled with aspect ratio and art direction; full copy, correct sequence, typography, image proportions and CTA placements; the annotations present on the sheet as production markings and absent from the depicted page copy. Asset references go in filenames or the private assembly map.

### D. Production method (pinned; Update Plan Item 13)

The spec image set is produced by one fixed method, for the wireframe stages and the mockup stage alike; no run invents its own. (1) Generate per section: each section slice is generated on its own via the KIE.ai GPT-image route (the route in `references/kie-generation-route.md`: Skill 66 policy, Skill 74 transport), with the exact model resolved from the model registry at build time; the skill pins the method, never a model name. (2) Inputs per section: for a wireframe section, the section plan and the run's copy are the layout input; for a mockup section, the approved wireframe section slice is the layout reference; in both cases the page visual bible (palette, fonts, grade) is the style input. (3) Generate each section at its native aspect: the stage's full page width and the section's own height, never a cropped or stretched fit. (4) Assemble by code, not by hand: `scripts/stitch_sections.py` stitches the slices into the full-page PNG in section order and `scripts/combine_review_pdf.py` combines the same slices into the combined PDF from a manifest in the same order. (5) Text-fidelity QC before stitching: every section is read at native resolution and its words are checked against the section's real copy; any section with a garbled word fails that section and is regenerated before stitching, and a garbled section is never accepted into the combined artifact. The stage folder's `production-record.json` records, per section, the generation inputs (route, resolved model id and its registry source, layout reference, style input), the native-aspect output, and the per-section text-QC record with its attempts; `scripts/validate_production_record.py` checks the record, and the stitcher refuses to run on a record that does not pass. Small printed text is the known weak point of model-rendered sheets; the QC leg exists because of it, not as a formality.

**Gate (Update Plan Item 15):** the wireframe stage's validator (`scripts/validate_wireframe.py`, re-run by the stage gate at close) fails the close on the named traits: a section whose plan entry lacks its number and name annotation (W1), its printed type specs (W2), or its behavior notes (W6); the first section lacking the header strip record stating page width and content width (W5); any slot lacking its ratio-plus-art-direction label (W3); and any slice whose measured colors fall outside the brand palette (W4). Each failure prints one named line per section or slot. The section plan carries the annotation record (`section_number`, `section_name`, `type_specs`, `behavior_notes`, `header_strip`, and the per-slot labels; see `references/artifact-contracts.md`); the reviewer verifies the record against the printed sheet by eye.

## Stage 5 - Create the entire mobile wireframe and tablet rules

### A. Reflow; do not shrink desktop

The mobile wireframe is the same artifact in its mobile form: a designed, annotated build spec rendered as images in the client's brand colors, one section slice per section at the 390px phone width, carrying the same printed annotations as the desktop sheet (section number and name, type specs, image slots labeled with aspect ratio and art direction, the run's real copy, CTA chips with microcopy specs, behavior notes) under a header strip stating page width and content width. Mobile-specific direction is printed as a behavior note on the section it governs (for example "CTA before portrait on mobile").

Build a readable phone layout using the same copy and assigned assets. Main content is one readable column. Image-led details may be offset where the map calls for them, but never leave long copy in a narrow strip beside an image. Keep the first CTA and opening purpose usable before a long image procession.

At the baseline 390 CSS-pixel canvas, use roughly 24-pixel gutters, at least 18-pixel body copy and at least 16-pixel public microcopy unless an explicit approved typography map specifies a different accessible treatment. Buttons are at least 56 pixels high and may grow for two lines. These are house defaults, not a claim about a universal accessibility law. Check 320, 360, 390 and 430 CSS-pixel widths and phone landscape in the actual implementation.

### B. Treat dense sections explicitly

Long pains can use consecutive visual panels before their matching solutions. Expanded Why movements remain one family with its final CTA. Each inclusion's full title and description remains visible; no hidden carousel or accordion merely to save height. All onboarding steps appear in order. The letter stays a continuous reading experience, not six summary cards. Tablet receives a defined intermediate arrangement instead of accidental narrow desktop columns.

### C. Verify the whole deliverable set

Deliver the mobile spec image set: the section slices (`mobile-tablet/section-*.png`, one per section, in section order, each at the full 390px width and its section's native height), one stitched full-page PNG (`mobile-tablet/wireframe-full.png`) and one combined PDF (`mobile-tablet/wireframe.pdf`), the stitched PNG and the PDF matching the slices section for section. Confirm the stitched PNG shows the complete page exactly once. An annotation or section label never becomes public copy. The mobile output is not a collage of miniature phone screenshots and is not another desktop deliverable. The mobile set is produced by the same pinned production method as the desktop set (Stage 4D): per-section generation at native aspect, per-section text-fidelity QC at native resolution with regeneration of any garbled section before stitching, the deterministic stitcher and PDF combiner, and a `production-record.json` in the stage folder.

Part naming follows the Stage 4 mapping exactly, applied per wireframe: the mobile slices are lettered from Part-A at the mobile page's first section, their machine names are the `section-*.png` files in the `mobile-tablet` folder, and the mobile assembly map records both names per slice in the same form. The folder name is what disambiguates a desktop part and a mobile part that share a letter or a number.

**Output:** the mobile wireframe spec image set (section slices, stitched full-page PNG, combined PDF), tablet reflow rules and updated private image placements. **QC/repair:** independent device-layout assessment, intact copy, no horizontal clipping, correct image proportions, no lost CTA/letter content, every section annotated and every slot labeled. Static wireframes do not constitute live-device tests.

## Stage 6 - Create the visual bible and the internal layout proof

### A. Apply the visual system to the passed layouts

Use the fonts and palette in the run's brand file (`intake.json` -> `brand_file`) exactly — never tokens an agent proposes. Apply actual typography, frames/backgrounds and the full copy. Keep the wireframes' structural decisions and image slots. Use deliberate temporary references or placeholders where final imagery does not yet exist. Record their temporary status privately; do not put "image goes here" inside customer-facing copy. The page visual bible this stage produces is the style input for every mockup section generated under the pinned production method (Stage 4D, applied at Stage 11C): palette, fonts and grade travel into section generation through the bible, never through ad-hoc per-section choices.

This stage's render is an internal layout proof, not a mockup: it is never presented to the client as the mockup and is never client-judged. Its image slots are solid blocks by design, because the proof exists to lock layout, typography and visual direction before image generation; a client shown this artifact would be shown a page that structurally cannot carry real photography. The client judges exactly one mockup: the Stage 11 mockup, produced after generation with real photography in every slot. This stage's lasting product is the page visual bible, the style input the Stage 7 prompt work requires.

### B. Avoid double image production

Do not generate throwaway campaign photography just to fill this layout proof. Establish each image's visual direction through the layout and image plan. The same layout proof will later be finalized with the final passed images at Stage 11; this is not two independent design projects.

**Output:** `visual-mockup/page-visual-bible.json` and its human-readable `.md`; `visual-mockup/mockup.html` (static, full public copy, brand fonts and palette only, image slots as solid blocks marked `data-image-slot="IMG-###"` at the wireframe's exact sizes); `visual-mockup/desktop/part-*.png` (1440px) and `visual-mockup/mobile/part-*.png` (390px) rendered from `mockup.html` by `scripts/render_page.py`. The renders are an internal layout proof only: never a client deliverable and never presented as the mockup. **QC/repair:** brand file, typography, composition, continuity, readable full copy and no unapproved additions. No new testimonials, offers, FAQs, badges or extra CTAs invented to make the layout proof look complete.

## Stage 7 - Write and QC the image prompts

### A. Use the image guide, not remembered shortcuts

Read the current Graphics rules and [Image Prompt Creation Guide](BlackCEO-Signature-Image-Intelligence-and-Prompt-Creation-Guide-v5.md). For every actual generated-asset entry, author one complete ten-element prompt to the model's rule 12 band, which is Skill 71's native authoring target under owner Decision 1 (2026-10-15): 95 to 100 percent of the model's live prompt field maximum, never below the 80 percent floor. Resolve the model and its maximum through Skill 66 (policy) and Skill 74 (live field limits) at run start; never type a maximum from memory. Reach the band by genuine specification only: scene geography, cast micro-detail, wardrobe construction, lighting recipe, optics, grade application, composition geometry, distinctness, and scene-specific negatives. Padding a prompt to length is a named failure. The Signature Grade Block is pasted byte-verbatim, exactly once. Use camera, expression, hair, skin-tone and color-grade intelligence where relevant. People-free assets explicitly remain people-free.

**Supplied assets.** An inventory entry whose `source` begins with `supplied` (for example `supplied-logo`, `supplied-founder-photo`) names an existing asset requiring no generation. Do not author a prompt for it. Its per-image TXT file is a supplied-asset record in the format fixed in `references/artifact-contracts.md`: it names the image id, carries the asset sha256 recorded on the inventory entry, carries the inventory aspect ratio, declares the asset supplied, and states explicitly that no generation was performed for it and none is permitted. `scripts/validate_prompt.py` validates the file as that record and names the exception on its PASS line; the entry is exempt from style-selection governance, and no style selection record has to govern it.

Keep numeric technical ratio/dimension fields in the request/manifest, matched to the prompt's composition. Put all actual rendering instructions, reference directives and negatives inside the counted prompt. Resolve alternatives before submission. No Midjourney flags, spintax, obsolete reference links, shortened generator summaries or blanket ratios.

### B. Run mechanical checks and independent prompt review

Check each final normalized string against the in-validator prompt-stage budget check first: `python3 scripts/validate_prompt.py <file> <sauce>` renders the band verdict for the prompt's model (budget exit 3 below the floor, naming the characters to ADD and the count to the 95 percent target; budget exit 4 above the maximum, naming the characters to CUT) and confirms the requested ratio against the model's aspect-ratio enum in Skill 74's registry, failing by name when the ratio is not in the enum; the prompt stage gate records the budget block on the item's close entry. Then run the Skill 74 adapter check, `python3 74-kie-live-adapter/scripts/kie_live_adapter.py prompt-budget --model <id> --check --prompt-file <file>` (exit 3 means add the reported characters, exit 4 means cut them), plus declared band, exact text locks, references, negative block and hash. Do not use a bypass or silently truncate. An automatically generated mechanical report is not independent creative QC.

Repair only failed prompts. No routine human approval is required. A prompt that passes advances immediately. Apply the three-attempt failed-only rule and existing stricter repo triggers.

**Output:** one prompt document, separate per-image TXT files when needed, current request manifest and real prompt-QC results. **QC/repair:** each applicable dimension >=8, overall Graphics average >=8.5, zero hard failures. The image count exactly matches the inventory, except explicitly existing assets requiring no generation.

## Stage 8 - Generate the images through the selected KIE route

In OpenClaw, run image generation through the route in `references/kie-generation-route.md`: Skill 66 (policy) then Skill 74 (transport) for Kie, or Skill 63 (Agnes) when the client selected it, using the client's own keys and the job's image cap; do not call image providers directly and never hand-write a createTask call.

### A. Resolve and pin the GPT image model

The default is the newest GPT Image generation in KIE's live catalog, resolved by `kie_live_adapter.py latest-family --family gpt-image` (rule 13; GPT Image 2.5 Sunburst today). An explicit client request or a department pin overrides it. Record the resolved model id, its source and its schema limits at the start of the job. A model name in an older document is not guaranteed to remain latest, and no model id is typed from memory. Apply the N43 ratio rules (3:1, 1:3 and 9:21 use the legacy route; on the default route 5:4 becomes 4:3, 4:5 becomes 3:4, 2:1 becomes 16:9, 1:2 becomes 9:16). Do not silently substitute another generator, including a native chat image tool, when the task requires KIE.

Use client-owned credentials, permitted resources and the authorized spend cap. No keys appear in prompts, public HTML or handoff files. Preserve repository isolation and permission rules. The authoring of this SOP does not authorize a paid generation job.

### B. Submit the exact passed prompts

One asset per task. Keep the hash/count unchanged after review. For each image run, in order: `validate`, `preflight` (balance must cover price x 1.30), `prompt-budget --check`, then `submit --mode active`, `wait`, and `save` immediately (all Skill 74 commands). The KIE limit is 20 createTask requests per 10 seconds per account (rule 3), including repairs and concurrent jobs. The limit is shared, not twenty for each agent. Obey 429 backoff. Delivery batches of four/eight/six are packaging choices, not independent rate limits. [W3]

Track task IDs and state. A 200 response or queued task is not finished. Check an uncertain request's existing state before repeating it; Skill 74 never retries createTask after a network error. Use the configured callback architecture (Skill 46) when available; otherwise Skill 74 `wait` polls with backoff. Download completed masters immediately (links can expire within 24 hours) rather than using temporary generation links as permanent website hosting. Save each completed master under its delivered name, the two-digit `Image-NN.png` derived from its three-digit internal ID (Item 26: `IMG-001` saves as `Image-01.png`), so the saved file, the transport receipt's `file`, and the delivered file are one name. Record the transport receipt that `stage_gate.py` requires. [W3]

For a supplied asset there is no task: the file placed in the stage folder is the supplied asset itself, and its transport receipt entry carries `supplied_asset: true` and the sha256 of the filed bytes in place of a task entry. The gate verifies that hash against the bytes on disk and against the sha256 recorded on the inventory entry.

**Output:** original masters tied to asset IDs, actual tasks/receipts, measured dimensions and the submitted prompt version. **QC/repair:** completion and provenance must be real. Missing returned output is a failure, not an invitation to reuse an unrelated older picture.

## Stage 9 - QC, repair and package every image

### A. Inspect the pixels against the assigned prompt

The independent image reviewer opens every external deliverable. Check scene, cast, expression, hair/skin fidelity, grade, composition, text, logo, anatomy, actual dimensions and desktop/mobile crop fitness. Review the set for cloned faces or repetitive shots while keeping intentional same-person continuity. Repository Graphics image-QC rules remain primary.

### B. Repair the failed asset

A wrong scene, missing person, burned-in image number, incorrect text, under-size image, unapproved crop or collage is a failure. Repair it with a complete compliant prompt or an explicitly authorized crop/grade operation that preserves required content. Keep the master. After any edit/export, inspect the actual final file. Do not report requested dimensions as actual or secretly upscale a smaller return to hide a miss.

### C. Package passed files only

Use `Image-01.png`, `Image-02.png` and so on, with numbers corresponding to the image inventory. This is the one delivered-file convention (Update Plan Item 26, proposal P6, ruled 2026-10-15): delivered files carry the two-digit `Image-NN.png` name, while the run's manifest and inventory carry the three-digit internal ID (`IMG-001`, `IMG-002`) alongside, so `IMG-001` is delivered as `Image-01.png`, `IMG-012` as `Image-12.png`, and `IMG-123` as `Image-123.png`. Every delivered file maps to exactly one internal ID and one receipt; no other delivered form (never `IMG-001.png`, never `Image-001.png`) ships. The generation route saves under this same delivered name (see `references/kie-generation-route.md`), and delivery validation (`scripts/validate_image_manifest.py`) checks the delivered filename against the manifest ID and fails by name on any mismatch. Labels belong in filenames, never across the artwork. Each requested batch gets its own ZIP and a private manifest. All requested entries must be present or the batch is explicitly incomplete; do not advertise a missing-image package as finished.

**Output:** QC-passed, correctly named individual exports plus batch ZIPs. **QC/repair:** individual dimensions >=8, Graphics average >=8.5, zero auto-fails, exact inventory count and correct filenames. No routine human prompt/image approval gate.

## Stage 10 - Upload the images and complete the Image Map

### A. Use the correct client and folder

Create or reuse a GHL Media Storage folder named for the page/campaign. Upload the passed assets with their correct filenames. Do not create duplicates blindly when a folder already exists. Use the configured authorized route; if upload access is absent, deliver the ready-to-upload package and identify that exact missing capability rather than pretending the upload occurred.

### B. Record the hosted URLs

Create `PageName-Image-Map.md` and, where automation benefits, the equivalent JSON. The map is a document; it does not need its own web hosting. It contains links to where each image is hosted.

| Required column | Meaning |
|---|---|
| Image ID and filename | Stable asset identification. |
| Private page placement | Which current desktop/mobile slot uses it. |
| Width, height and aspect ratio | Actual final delivery geometry. |
| Hosted URL | Exact GHL media link for that file. |
| Crop/focal instructions | Per-device presentation, if required. |
| Alt text/decorative status | User-facing description where useful, never internal numbering. |
| Current version/QC status | Confirms the hosted image is the passed version. |

### C. Verify the mapping

Open every URL and verify the actual subject/file, not merely an HTTP success. Confirm the dimensions and image count against the inventory. A revised upload must update the current map; do not let code point to a rejected predecessor.

**Output:** complete Image Map with working URLs. **QC/repair:** every passed asset has the correct hosted link, no mismatched or stale entries, and no private production data is embedded in the image itself.

## Stage 11 - The mockup: finalize the layout proof with the actual assets

### A. Replace temporary imagery

This stage produces the mockup: the single client-judged mockup. It is produced per section, with real photography composited into every slot. Supplied assets (the logo, the founder photo, and any other supplied file) are placed as files and never generated; the supplied-asset record is the placement proof. No slot may remain a solid block or placeholder in the judged mockup.

Install the actual passed images in their assigned positions. Keep the approved typography, layout and full copy. Preserve the surrounding live text and avoid new slogans to fill gaps. Include the popup/open-action state where that behavior is part of the design.

### B. Check the resulting composition

Review desktop and mobile separately and the tablet reflow specification. Actual faces, hair, words on props and focal points must survive the intended crops. Do not redesign a page solely because the generator delivered a different composition; repair the image or obtain an authorized layout decision.

**Output:** `final-mockups/mockup.html` = the Stage 6 layout proof finalized with real images in every slot; this is the client-judged mockup. `final-mockups/desktop/part-*.png` and `final-mockups/mobile/part-*.png` rendered by `scripts/render_page.py`. **QC/repair:** full copy and image parity, intended visual hierarchy, correct fonts, usable action state, no private labels. This is the finalization of the layout proof, not another unrelated creative round.

### C. Production method for the mockup sections (pinned; Update Plan Item 13)

Where the mockup is delivered as section images, the sections are produced by the same pinned method as the wireframe set (Stage 4D), with the mockup's own inputs: each mockup section is generated per section via the KIE.ai GPT-image route (model resolved from the registry at build time; the method is pinned, not a model name), with the approved wireframe section slice as that section's layout reference and the page visual bible as the style input, at the section's native aspect. Supplied assets are placed as files into their slots, never generated. Before any stitching, every section passes the text-fidelity QC leg at native resolution: a section with a garbled word fails and is regenerated, and no garbled section enters the combined artifact. `scripts/stitch_sections.py` assembles the full-page mockup PNG and `scripts/combine_review_pdf.py` the combined PDF, both in section order, and the stage folder's `production-record.json` carries the per-section build record (generation inputs, native-aspect output, text-QC record and attempts) that `scripts/validate_production_record.py` checks.

### D. Compose the hybrid board (standard deliverable at mockup approval; Update Plan Item 12)

At mockup close the stage produces one hybrid board, `final-mockups/hybrid-board.png`: a single sheet carrying three panels (the hybrid traits H1/H2 of the Item 14 trait checklist): the mockup-fidelity desktop page, the mockup-fidelity mobile page, and a section guide column (numbered sections, a mini wireframe thumbnail per section, and the section's typography specs), so structure and finished look are approved from one sheet. The board is composed deterministically by `scripts/build_hybrid_board.py` from the already-approved section artifacts named in the board record `final-mockups/hybrid-board.json` (the approved desktop and mobile mockup artifacts, byte-pinned by sha256; the guide's thumbnails are the approved desktop wireframe section slices, byte-pinned likewise; the typography specs are drawn from the font map, the typography spec record), never by a new generation pass and never by hand. `scripts/validate_hybrid_board.py` checks the record (and, with `--check-board`, that the composed board and its receipt match the record exactly); a panel or thumbnail whose bytes no longer match the approved artifact fails that validation by name, as does a guide whose sections do not match the mockups section for section. The mockup approval is recorded against the board: the stage contract names `final-mockups/hybrid-board.png` as the stage's approval artifact, the board is in the stage's review cover, and the stage receipt records `approval_artifact: "final-mockups/hybrid-board.png"`.

**Output:** the hybrid board and its composition receipt beside the finalized mockups. **QC/repair:** the board's three panels match the approved desktop mockup, the approved mobile mockup, and the section guide exactly; approval evidence references the board, not the separate artifacts.

**Gate (Update Plan Item 15):** this stage is the client-judged mockup, and it cannot close with a placeholder slot. The stage carries a section generation record (`final-mockups/generation-record.json`; see `references/artifact-contracts.md`) in which every inventory slot traces, per section, to a generated image file or to a placed supplied asset under Item 3's supplied-asset record (supplied assets are placed as files, never generated). `scripts/validate_mockup_slots.py`, a stage validator the gate re-runs at close, fails the close by name for any slot tracing to neither (trait M1: real photography in every slot, zero placeholder slots). Mockup traits bind at this stage only; Stage 6's layout-proof slots are solid blocks by design and are never scored by this gate.

## Stage 12 - Build the responsive HTML and repair it before installation

### A. Read the current inputs

Use the clean public copy, font map, wireframes, final mockups, Image Map, form/checkout information and action plan. The approved final mockup is the design source of truth for this stage (Update Plan Item 16; the standing rule of 2026-10-11: the image is the design source of truth and the live HTML page is built to match the approved mockup, never the reverse). The final mockups are the visual target; the HTML must match them section by section. Use only current QC-passed versions. Keep the exact button labels and their version-specific placement. No live page receives private framework names in body text, image alt/title, data content, CSS class names describing secret steps, or comments.

### B. Implement the selected route

For direct GHL: provide one code-only TXT file containing complete page markup, scoped CSS and required JavaScript for one Custom HTML/JavaScript element. Avoid unrelated global resets. Handle initialization both when the element is ready and through the actual documented GHL lifecycle; initialize once safely. HighLevel documents `hydrationDone` for preview custom code. [W6]

For Vercel embedded into GHL: build/deploy the page on Vercel, then supply embed code for the GHL page. Ensure the intended GHL origin may embed it without indiscriminately weakening security headers. Handle frame sizing and resize/orientation with an agreed, validated-origin mechanism when required; a tall page must not be cut by a fixed short iframe. Test popup visibility and scroll behavior in the embedded context, not only standalone Vercel. Do not change the selected hosting route to escape implementation work. [W7]

### C. Implement real responsive behavior and animation

One content source reflows by available screen width; it does not require browser-brand guessing or separate truncated mobile copy. Load the actual Google Fonts and requested variants. Keep images proportional, body readable, controls touch-friendly and all content present. Let long sections grow.

Use progressive animation so unsupported or delayed scripts do not hide copy. Respect reduced-motion preference. For popups, provide a usable close control, Escape behavior where possible, focus/scroll return, mobile-safe height and usable error/loading states. Do not invent a form success event or replace the client's form fields. Parent CSS styles the popup/iframe container; the form's internal styling belongs in the form builder's Custom CSS area. [W8]

### D. QC source and rendered output

Compare customer-facing text with the approved copy, compare all image URLs/placements, scan for private labels/placeholders, and render desktop/tablet/mobile widths. Check actual font faces loaded, overflow, image crops, full steps/letter, action behavior and reduced motion. A regex scan alone is not proof of visual correctness. Test the passed code after repairs without changing unrelated passing content.

The primary CTA implements the form pop against the named Convert and Flow form object recorded at intake (`funnel_handoff`), per the copy manifest's primary CTA entry; it is never a hand-rolled modal and never a placeholder link. `scripts/validate_handoff.py` verifies this on the built page: a placeholder destination fails the stage unless intake recorded the form identity as an explicit missing input, in which case the placeholder is carried under that recorded flag.

**Parity evidence (required to close, Update Plan Item 16):** run `scripts/compare_sheet.py` so the stage's closing evidence includes the side-by-side parity sheet at 1440 and at 390 (approved mockup render against built page render, in `responsive-html/compare/`) and the structural drift table in `responsive-html/compare/compare-report.json` (section count, section order, per-section image-placement class, heading-to-body size ratios within tolerance). The stage cannot close without that evidence on record, and named drift failures block close: a drift status other than `pass` (including a skipped or unavailable drift pass) refuses the close at the gate. The reviewer scores fidelity against the approved mockup under `references/html-qc-rubric.md` criterion 4, not against the page's own internal consistency.

**Output:** current responsive code-only TXT, appropriate HTML preview/deployment files, separate form CSS where required, minimal install notes, the parity sheets at 1440 and 390 and the drift table, and real check results. **QC/repair:** every required criterion >=8 under `references/html-qc-rubric.md`, no hard failures. Local tests are explicitly local; never mark them as completed GHL tests.

## Stage 13 - Install in GHL and test the actual visitor journey

### A. Install once in the right place

Use the correct sub-account. Go to Sites -> Funnels -> correct named folder -> existing or new funnel -> existing or new funnel page/step -> editor. Add/configure a full-width section, suitable one-column row and Custom HTML/JavaScript element. Set unwanted surrounding padding to zero. Paste the entire approved direct code or Vercel embed once, according to the selected route. Replace old code rather than placing another full copy underneath it. Keep the element visible for desktop and mobile. The GHL builder uses sections, rows, columns and elements; saving and publishing are separate operations. [W4]

### B. Check in GHL Preview

Confirm the correct current design, real hosted images and actual fonts. Click every CTA to confirm routing, but submit a shared form only once with a designated test contact. Check popup opening/closing, scroll return, mobile keyboard/scroll usability and orientation. If GHL delays critical custom initialization, apply its documented guidance rather than claiming the code works from a local screenshot. [W6]

For sales, verify the intended product/price and supported checkout path using test mode where available. Do not make an unauthorized live charge. For signups, confirm a real submission/contact and the specified confirmation/access path. For booking/downloads, confirm the actual outcome. A button opening is not completion of the visitor journey.

### C. Repair the relevant failure, not the whole project

A failed popup gets a popup repair plus checks of the affected buttons/scrolling. A font issue gets a font-loading/fit repair. Do not regenerate every image because one URL is wrong. If live GHL access is unavailable, report which test is outstanding and supply the minimum exact action required; do not fabricate a PASS.

**Output:** installed current page/embed and actual preview/action result, recorded as evidence, not prose: the install receipt carries the structured `install` block (target, per-CTA click results, the once-only form submission with its designated test contact, popup and mobile keyboard/scroll checks, test-mode sales check) verified by `scripts/validate_install.py`; desktop and mobile evidence screenshots under `ghl-install-test/evidence/`; and, on the GHL route, the funnel-completion sub-stage's per-object receipt `ghl-install-test/funnel-completion.json` with its live click-through record (see `references/funnel-completion-checklist.md`: funnel and steps in order, every step bound, forms attached, pop-ups wired, click actions clicked, order form bound, missing products created only after an existence check, payment presence as a boolean, the primary CTA opens the form intake names, and its test submission routes to the product selection step). At this stage's close the automation hand-off `handoff/automation-handoff.json` is recorded (IDs only, never credentials) for Stage 15. **QC/repair:** complete usable experience on the selected route, not merely attractive code.

## Stage 14 - Publish when authorized and check the public URL

### A. Apply the already established publication authority

If the job authorizes publication, do not invent another routine human sign-off gate. If authorization only covers drafting, do not publish. Confirm intended domain/path and existing page metadata, favicon/share asset and required supplied privacy links. Do not invent legal copy or extra tracking. Preserve the last known working code privately before replacement.

### B. Check delivery, not redesign

Open the public GHL URL after publication and verify that it displays the intended current version, loads its assets and performs the main action. For Vercel, inspect the actual GHL-embedded experience. Check at least the relevant desktop and phone presentation and any tablet-specific arrangement affected by the implementation. Repair real delivery defects; do not reopen passed copy for subjective polishing.

### C. Deliver the final files and concise result

Give the current code, maps, required assets/batches and install notes in a clear package. Keep prompts, source material, private framework notes and QC records out of the public site, but available in the authorized private handoff. State exactly what was tested, what was published and any genuine unresolved limitation. No completed declaration for an unfinished page.

**Output:** working public page when authorized, current deliverable package and short internal release record. The public result is verified against the LIVE bytes, not the preview: `scripts/validate_install.py` fetches the receipt's `public_url` and writes `publish-verify/fetch-record.json` (status, final URL, byte count, checks run); a non-200, a final URL that differs from the recorded one, a private framework label, or a placeholder in the fetched HTML fails the stage, and a network that cannot be reached records the stage BLOCKED, never passed. On the Vercel-embed route the standalone fetch is only the first layer: the Stage 12-13 embedded-context checks (iframe sizing, popup visibility, scroll behavior inside the actual GHL embed) must also be on record, and the fetched page's build marker must agree with the deliverables provenance (Item 34). A test run never closes this stage as a production pass, derived fonts require an independent font-review record, and a production close is refused while the brand file's grade thresholds are uncalibrated (owner-ordered; waivers are recorded in the receipt and printed in REPORT.md). **QC/repair:** correct version live, main action usable, no truncation or private-label leakage. This check reuses the established design; it is not another creative stage.

## Stage 15 - Wire the follow-up automations (conditional)

### A. When this stage exists

This stage runs only when the intake records a GHL publish target and `automation_scope: "workflows"`. In every other case the gate records it `not_applicable`, citing the intake values, in the run state and in REPORT.md. It is never silently skipped, and intake refuses a workflows scope on a non-GHL target.

### B. Execute from the hand-off, with the operator skill

Skill 44 (Convert and Flow Operator) builds the workflows from `handoff/automation-handoff.json`, which publish-verify carried forward unchanged (the gate verifies its hash). The Tier 0 `caf` CLI is the primary build path; the Tier 4 browser backstop is declared, never silent, and prints in REPORT.md whenever used. Every hand-off form ends trigger-covered by a recorded workflow or with an explicit `no_workflow_reason`. Each workflow carries Skill 44's own QC evidence (its `qc-built-workflow.sh` exit code and a filled WF checklist instance) and a read-back confirming it exists.

The conversational layer rides the same stage: each trigger derived from the funnel (opt-in per form, purchase per bound order form, booking per booking step) maps to a workflow carrying a named Skill 38 playbook with SMS and email tracks, or a recorded owner override that prints in REPORT.md. Workflow writes use the Firebase refresh token; a run without it proceeds only under the intake's recorded choice (token supplied, backstop declared, or scope dropped).

**Output:** the automation-wiring receipt with per-workflow build method, QC evidence and read-backs, the conversational coverage map, and the filled checklist instances under `automation-wiring/`. **QC/repair:** independent review of the wiring against the opt-in intent, through the standard review machinery. The full contract is `references/automation-handoff.md`.

## Do not repeat the failures from the Set for Life project

| Failure to prevent | Mandatory check/repair |
|---|---|
| Overriding the supplied opening or offer | Compare the opening and core offer against the client's actual latest direction. |
| Free event turned into paid selling language | Confirm the page action and actual price/free status from the current record. |
| Wrong duration, founder, topic or borrowed example | Check those facts against supplied material, not an older draft or teaching example. |
| Internal Section/Part labels displayed | Remove them from public source, not just CSS; inspect rendered full copy too. |
| Image numbers burned into artwork | Reject the pixels; name the individual files instead. |
| Wrong prompt used or prompt shortened | Compare submitted prompt hash/count with its passed per-asset file. |
| Collage delivered instead of separate images | Count files and inspect each; one task/asset is not a six-panel composite. |
| Missing Image 20 or a misnumbered batch | Compare promised inventory to actual ZIP entries and opened file subjects. |
| Undersized file secretly upscaled | Measure original and export; repair through approved method, disclose any limitation. |
| Cloned faces and identical poses | Review the full cast/shot register, preserving only intended continuity. |
| Standing versus seated ignored | Compare the actual latest pose request to the delivered image. |
| Fake founder identity | Use the supplied identity or expressly authorized non-identity image, never silent substitution. |
| Full copy squeezed or summarized | Text parity check and complete visual review; let the layout grow. |
| Desktop delivered when mobile requested | Confirm device scope before export; use readable mobile geometry. |
| Phone miniatures masquerading as complete wireframes | Export consecutive full-width parts; no overview-only substitute. |
| Fonts silently replaced by fallbacks | Check renderer/browser use; distinguish temporary fallback from font-map compliance. |
| Popup became always-visible form | Test initial state and all trigger actions in the real hosting context. |
| Parent CSS promised to style iframe fields | Separate form-builder CSS from the surrounding page/popup CSS. |
| Old broken code left in the replacement package | Build from the current manifest, inspect ZIP contents, replace old GHL code once. |
| "Fixed" claimed without an actual check | Record the performed check and inspect its output; no simulated PASS. |
| Invented tool limits or claimed KIE use after another tool ran | Verify the actual tool/route and receipts; do not improvise service restrictions. |
| Arbitrary additions to improve the appearance | No unrequested FAQs, testimonials, bonus products, public labels or extra buttons. |

## Lightweight QC record template

This is private working data, not a form for clients to fill out and not a public-page object.

```json
{
  "artifact_id": "actual internal ID",
  "version_or_hash": "actual current version",
  "stage": "actual production stage",
  "reviewer": "actual reviewer identity or tool",
  "independent_review": false,
  "criteria_scores": {},
  "automatic_failures": [],
  "result": "NOT_YET_REVIEWED",
  "repair_attempt": 0,
  "specific_defects": [],
  "performed_check": "",
  "next_current_artifact": null
}
```

Populate only actual results. `independent_review` becomes true only when an independent reviewer actually performed the review. The operator's quick payload integrity check is not a new subjective QC cycle.

## Documentation and scope boundaries

This SOP governs shared production. The two writing guides retain their distinct frameworks and full examples, with explicit links here. The image guide governs per-asset prompt construction and links back here for staging. Do not copy the entire process into all four documents.

A later repair updates the current artifact and only affected references. It does not authorize deleting the previous private backup, changing another client's resources, rewriting unaffected passing material, or bypassing an existing independent Graphics gate. Keep evidence small and useful: the purpose is to prevent stale-file mistakes and false completion claims, not to create bureaucracy.

## Sources and authority notes

The production order, universal scope, below-8 repair rule, failed-only three-attempt allowance, Google Fonts preference, image naming and no-private-label rule are Trevor's current instructions. The per-image prompt length and the submission limit are governed by `07-kie-setup/references/kie-common-rules.md` (rules 12 and 3), which replaced the earlier 5,000-20,000 range and the earlier 20-per-15-second house ceiling. The specific action templates and stage deliverables implement those instructions.

The source Graphics rules and retrieved hashes are recorded in [the image guide](BlackCEO-Signature-Image-Intelligence-and-Prompt-Creation-Guide-v5.md#15-source-record-and-translation-boundaries). Those sources retain their separate independent roles and stricter 8.5 averages; their older 19,000-character cap is superseded for KIE by the prompt budget (rule 12). The supplied legacy Midjourney document informs aesthetic guidance only; it does not control provider syntax or the current page sequence.

Public technical references checked September 30, 2026:

- W1: Google Fonts CSS2 API, https://developers.google.com/fonts/docs/css2 . Named font family/weight/style requests.
- W2: FontFaceSet.load, https://developer.mozilla.org/en-US/docs/Web/API/FontFaceSet/load . Loaded FontFace objects; not proof of every glyph or final visual fit.
- W3: KIE Getting Started, https://kie.ai/getting-started . Task lifecycle, current per-account submission limit and temporary media retention; see `kie-common-rules.md` rules 3 and 8 for the verified figures.
- W4: HighLevel Sites Overview, https://help.gohighlevel.com/support/solutions/articles/155000001633-sites-overview . Shared funnel/website builder structure and save/publish distinction.
- W5: HighLevel Payment Links, https://help.gohighlevel.com/support/solutions/articles/155000002177-payment-links . Hosted checkout tied to actual products/prices; not proof every order form has portable embed code.
- W6: HighLevel hydration event, https://help.gohighlevel.com/support/solutions/articles/155000002421-hydration-event-in-custom-code-in-funnels . Actual custom-code preview lifecycle guidance.
- W7: Vercel security headers, https://vercel.com/docs/cdn-security/security-headers . Embedding/security configuration; actual allowed origins must match the deployed job.
- W8: HighLevel form Custom CSS, https://help.gohighlevel.com/support/solutions/articles/155000006727-how-to-add-custom-css-to-forms-surveys-and-quizzes- . Form-internal versus parent-container styling.

No new client page, image, GHL folder, payment object or Vercel deployment is created by preparing this documentation package.
