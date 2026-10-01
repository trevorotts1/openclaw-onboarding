# BlackCEO Signature Landing Page Production and QC SOP

**Version:** 1.0 | **Date:** September 30, 2026  
**Owner:** Trevor Otts / BlackCEO  
**Scope:** A universal process for funnel-type pages: landing pages, opt-in/squeeze pages, event/registration pages, challenge pages, sales pages, booking pages and comparable focused visitor journeys.  
**Status:** Production instructions. Creating this document does not publish a page, update GitHub, authorize payment, or certify a live implementation.

## Start here: the four connected documents

| Document | Its job |
|---|---|
| [Standard writing guide v6](BlackCEO-Signature-Landing-Page-Standard-v6.md) | The original twelve-section writing system and its compact length/CTA rules. |
| [Long-form writing guide v6](BlackCEO-Signature-Landing-Page-Long-Form-v6.md) | Expanded writing with the three inserted solution sections and the long-form CTA map. |
| **This production and QC SOP** | The order of work, checks, repairs, current-version handoffs, implementation and delivery. |
| [Image Prompt Creation Guide v1](BlackCEO-Signature-Image-Prompt-Creation-Guide-v1.md) | Repository-led prompt anatomy plus section-based camera, face, hair, tone, composition and color-grade intelligence. |

Choose the writing guide for the requested page. Do not build both standard and long form by default. The image guide is required reading before image planning is finalized and before any image prompt is authored. The two writing guides point here so they do not carry competing copies of the entire production process.

Set for Life supplied lessons for this workflow. Its name, founder, free attendance, duration, palette, form, 22 images and assets are not universal defaults. Do not borrow one client's information or resources for another.

**The governing order:** confirm the page and action -> write and QC/repair the copy -> font intelligence and action plan -> full desktop wireframe -> full mobile wireframe and tablet rules -> visual-direction mockups -> individual image prompts and QC/repair -> generate and QC/repair images -> upload and complete Image Map -> finalize the same mockups with real assets -> responsive HTML and QC/repair -> install/test in GHL -> publish when authorized and verify the public result.

The default deliverables for one selected page version are **one full desktop wireframe and one full mobile wireframe**, plus their mockups. Four wireframes apply when explicitly creating the reusable standard/long-form template set: standard desktop, standard mobile, long-form desktop, long-form mobile. Exporting a long wireframe in Parts A-M does not create thirteen different pages.

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

The primary Graphics repository is stricter for prompts and generated images: retain its **8.5 minimum average**, with **every individual applicable criterion at least 8** under Trevor's newer requirement, and zero auto-fails. The new per-image 5,000-20,000-character range and the current repository's 19,000 ceiling are distinguished in the image guide. This document does not change live validators.

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

For sales pages: "Do you already have a checkout page or payment link for this offer? Send that link. If customers should pay directly on this page or in a popup, send the supported checkout embed code, if available."

A checkout URL is sufficient when the button goes to a checkout page. Do not demand a widget too. Do not assume every native GHL order form has portable embed code. If no checkout exists, collect the actual product, price/currency, one-time or recurring schedule and configured payment provider as a separate setup task. Do not put a homemade credit-card form into the landing-page HTML. [W5]

For booking: request the existing booking link or supported booking embed. For a download/lead magnet: request the actual form action and delivery destination. For a challenge: capture the actual dates/duration and access delivery only when missing. Do not assume all challenges are free or all events are ninety minutes.

### C. Record the outcome and only the needed image questions

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

**Output:** current QC-passed internal manuscript, clean public copy source and copy manifest. **QC/repair:** exact copy parity between the public view and all intended customer-facing source passages; no missing words or leaked instructions. Delivery follows the selected writing guide: Markdown in standalone chat, Google Docs first where configured, Notion next where configured, otherwise MD/TXT; Word when explicitly requested. Rendered document text is at least 12 points where controllable. These documentation choices do not affect the website's CSS-pixel typography.

## Stage 3 - Establish font intelligence and the visitor-action plan

### A. Map the fonts before full wireframes

Use Google Fonts by default, or a deliberately selected Google Fonts equivalent for an otherwise unavailable/proprietary face. Match the client's visual direction; do not claim the substitute is the original font detected in a raster mockup. Existing logos remain artwork.

Map actual family names, real weights/italics, role, desktop/tablet/mobile size and line height, emphasis, readable colors, wrapping, margins and fallback behavior. Use the actual longest copy and CTA wording. Avoid forcing one client's four font choices onto every future client. Google Fonts supports requesting named families and selected variants. [W1]

### B. Check fonts at the appropriate time

Confirm family/variant availability while preparing the map. As the wireframe is rendered, check that its renderer loaded the intended fonts. This is part of rendering the wireframe, not a separate website build or GHL setup. Do not label a fallback-font output an exact-font proof.

When HTML exists, check loaded FontFace entries and rendered typography in the actual browser. `document.fonts.load()` returns loaded font faces; a stylesheet declaration alone is not loading evidence. Inspect the actual glyphs used in headings/body; do not treat font loading as proof of every glyph or visual fit. [W2]

### C. Define how the action and motion work

Record on-page form versus button-triggered popup versus separate page. Specify close behavior, keyboard focus, return to scroll position, mobile scrolling, loading/error handling and actual success destination. Plan restrained reveals/hover/popup effects where desired, with reduced-motion behavior and readable content when scripts fail. A mockup's attractiveness does not establish these interactions.

**Output:** font map and compact action/motion specification. **QC/repair:** correct family/role choices, clear action, readable type and no contradictory behavior. No new temporary website or human sign-off round solely for fonts.

## Stage 4 - Create the entire desktop wireframe

### A. Build around the exact public copy

Use the full copy at its mapped type scale. Show real headlines, paragraphs, titles, descriptions, benefits, complete steps and the letter. Use schematic/grayscale image placeholders with actual proportions and defined positions, not generated photos masquerading as wireframes. Preserve live-copy priority above the fold.

Create a creative composition through meaningful hierarchy, mixed image proportions, offset frames, varied scale, typography-only panels and spacing. Do not substitute a monotonous stack of identical editor blocks. Creativity does not justify random order or missing content.

### B. Start the image inventory

Assign every requested generated image its stable ID, intended role, dimensions/aspect, desktop slot and expected mobile role. Identify existing logo/product/identity assets separately. Zero-image panels remain valid. Read the Image Prompt Creation Guide during this planning so crop, face, hair and scene requirements are not discovered after the layout is locked.

### C. Export without shrinking or cutting

One continuous page may need several PNG files. Use consecutive Part-A, Part-B filenames and a private assembly map. Split at meaningful boundaries; never through a paragraph, button/reason group, image or step. If an individual block is taller than the preferred export length, allow a taller file or split its visual treatment at a real paragraph boundary while keeping the argument intact.

**Output:** full desktop wireframe, all needed consecutive parts, and private layout/image inventory. **QC/repair:** full copy, correct sequence, typography, image proportions and CTA placements; no private framework labels inside the depicted customer page. Part names and asset references go in filenames or a separate production map.

## Stage 5 - Create the entire mobile wireframe and tablet rules

### A. Reflow; do not shrink desktop

Build a readable phone layout using the same copy and assigned assets. Main content is one readable column. Image-led details may be offset where the map calls for them, but never leave long copy in a narrow strip beside an image. Keep the first CTA and opening purpose usable before a long image procession.

At the baseline 390 CSS-pixel canvas, use roughly 24-pixel gutters, at least 18-pixel body copy and at least 16-pixel public microcopy unless an explicit approved typography map specifies a different accessible treatment. Buttons are at least 56 pixels high and may grow for two lines. These are house defaults, not a claim about a universal accessibility law. Check 320, 360, 390 and 430 CSS-pixel widths and phone landscape in the actual implementation.

### B. Treat dense sections explicitly

Long pains can use consecutive visual panels before their matching solutions. Expanded Why movements remain one family with its final CTA. Each inclusion's full title and description remains visible; no hidden carousel or accordion merely to save height. All onboarding steps appear in order. The letter stays a continuous reading experience, not six summary cards. Tablet receives a defined intermediate arrangement instead of accidental narrow desktop columns.

### C. Verify the whole export

Use as many consecutive PNG parts as needed. Confirm that stitching them in order would show the complete page exactly once. A part label never becomes public copy. The mobile output is not a collage of miniature phone screenshots and is not another desktop deliverable.

**Output:** complete mobile wireframe, consecutive parts as needed, tablet reflow rules and updated private image placements. **QC/repair:** independent device-layout assessment, intact copy, no horizontal clipping, correct image proportions, and no lost CTA/letter content. Static wireframes do not constitute live-device tests.

## Stage 6 - Create visual-direction mockups

### A. Apply the visual system to the passed layouts

Use brand colors, actual typography, frames/backgrounds and the full copy. Keep the wireframes' structural decisions and image slots. Use deliberate temporary references or placeholders where final imagery does not yet exist. Record their temporary status privately; do not put "image goes here" inside customer-facing copy.

### B. Avoid double image production

Do not generate throwaway campaign photography just to fill this first mockup. Establish each image's visual direction through the layout and image plan. The same mockup will later receive the final passed images; this is not two independent design projects.

**Output:** full desktop/mobile visual-direction mockups and current image inventory. **QC/repair:** brand, typography, composition, continuity, readable full copy and no unapproved additions. No new testimonials, offers, FAQs, badges or extra CTAs invented to make the mockup look complete.

## Stage 7 - Write and QC the image prompts

### A. Use the image guide, not remembered shortcuts

Read the current Graphics rules and [Image Prompt Creation Guide](BlackCEO-Signature-Image-Prompt-Creation-Guide-v1.md). For every actual generated-asset entry, author one complete ten-element prompt, 5,000-20,000 characters each. Use camera, expression, hair, skin-tone and color-grade intelligence where relevant. People-free assets explicitly remain people-free.

Keep numeric technical ratio/dimension fields in the request/manifest, matched to the prompt's composition. Put all actual rendering instructions, reference directives and negatives inside the counted prompt. Resolve alternatives before submission. No Midjourney flags, spintax, obsolete reference links, shortened generator summaries or blanket ratios.

### B. Run mechanical checks and independent prompt review

Check each final normalized string's length, declared band, exact text locks, references, negative block, runtime compatibility and hash. Current live repository gates cap at 19,000; use the documented compatible range or separately authorized policy implementation, not a bypass. An automatically generated mechanical report is not independent creative QC.

Repair only failed prompts. No routine human approval is required. A prompt that passes advances immediately. Apply the three-attempt failed-only rule and existing stricter repo triggers.

**Output:** one prompt document, separate per-image TXT files when needed, current request manifest and real prompt-QC results. **QC/repair:** each applicable dimension >=8, overall Graphics average >=8.5, zero hard failures. The image count exactly matches the inventory, except explicitly existing assets requiring no generation.

## Stage 8 - Generate the images through the selected KIE route

### A. Verify and pin the available GPT image model

Use the latest suitable supported GPT image model through KIE as requested. Verify its actual endpoint, reference fields, ratios, resolution options and prompt capacity at the start of the job, then record the pin. A model name in an older document is not guaranteed to remain latest. Do not silently substitute another generator, including a native chat image tool, when the task requires KIE.

Use client-owned credentials, permitted resources and the authorized spend cap. No keys appear in prompts, public HTML or handoff files. Preserve repository isolation and permission rules. The authoring of this SOP does not authorize a paid generation job.

### B. Submit the exact passed prompts

One asset per task. Keep the hash/count unchanged after review. Use the account-wide rolling limiter: **no more than 20 new image-generation submissions per 15 seconds**, including repairs and concurrent jobs. The limit is shared, not twenty for each agent. Obey any stricter vendor restriction and 429 backoff. Delivery batches of four/eight/six are packaging choices, not independent rate limits. [W3]

Track task IDs and state. A 200 response or queued task is not finished. Check an uncertain request's existing state before repeating it. Use the configured callback architecture when available; otherwise poll with the permitted backoff. Download completed masters promptly rather than using temporary generation links as permanent website hosting. [W3]

**Output:** original masters tied to asset IDs, actual tasks/receipts, measured dimensions and the submitted prompt version. **QC/repair:** completion and provenance must be real. Missing returned output is a failure, not an invitation to reuse an unrelated older picture.

## Stage 9 - QC, repair and package every image

### A. Inspect the pixels against the assigned prompt

The independent image reviewer opens every external deliverable. Check scene, cast, expression, hair/skin fidelity, grade, composition, text, logo, anatomy, actual dimensions and desktop/mobile crop fitness. Review the set for cloned faces or repetitive shots while keeping intentional same-person continuity. Repository Graphics image-QC rules remain primary.

### B. Repair the failed asset

A wrong scene, missing person, burned-in image number, incorrect text, under-size image, unapproved crop or collage is a failure. Repair it with a complete compliant prompt or an explicitly authorized crop/grade operation that preserves required content. Keep the master. After any edit/export, inspect the actual final file. Do not report requested dimensions as actual or secretly upscale a smaller return to hide a miss.

### C. Package passed files only

Use `Image-01.png`, `Image-02.png` and so on, with numbers corresponding to the image inventory. Labels belong in filenames, never across the artwork. Each requested batch gets its own ZIP and a private manifest. All requested entries must be present or the batch is explicitly incomplete; do not advertise a missing-image package as finished.

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

## Stage 11 - Finalize the same mockups with the actual assets

### A. Replace temporary imagery

Install the actual passed images in their assigned positions. Keep the approved typography, layout and full copy. Preserve the surrounding live text and avoid new slogans to fill gaps. Include the popup/open-action state where that behavior is part of the design.

### B. Check the resulting composition

Review desktop and mobile separately and the tablet reflow specification. Actual faces, hair, words on props and focal points must survive the intended crops. Do not redesign a page solely because the generator delivered a different composition; repair the image or obtain an authorized layout decision.

**Output:** final desktop/mobile mockups using the current assets and maps. **QC/repair:** full copy and image parity, intended visual hierarchy, correct fonts, usable action state, no private labels. This is an update of the original mockup, not another unrelated creative round.

## Stage 12 - Build the responsive HTML and repair it before installation

### A. Read the current inputs

Use the clean public copy, font map, wireframes, final mockups, Image Map, form/checkout information and action plan. Use only current QC-passed versions. Keep the exact button labels and their version-specific placement. No live page receives private framework names in body text, image alt/title, data content, CSS class names describing secret steps, or comments.

### B. Implement the selected route

For direct GHL: provide one code-only TXT file containing complete page markup, scoped CSS and required JavaScript for one Custom HTML/JavaScript element. Avoid unrelated global resets. Handle initialization both when the element is ready and through the actual documented GHL lifecycle; initialize once safely. HighLevel documents `hydrationDone` for preview custom code. [W6]

For Vercel embedded into GHL: build/deploy the page on Vercel, then supply embed code for the GHL page. Ensure the intended GHL origin may embed it without indiscriminately weakening security headers. Handle frame sizing and resize/orientation with an agreed, validated-origin mechanism when required; a tall page must not be cut by a fixed short iframe. Test popup visibility and scroll behavior in the embedded context, not only standalone Vercel. Do not change the selected hosting route to escape implementation work. [W7]

### C. Implement real responsive behavior and animation

One content source reflows by available screen width; it does not require browser-brand guessing or separate truncated mobile copy. Load the actual Google Fonts and requested variants. Keep images proportional, body readable, controls touch-friendly and all content present. Let long sections grow.

Use progressive animation so unsupported or delayed scripts do not hide copy. Respect reduced-motion preference. For popups, provide a usable close control, Escape behavior where possible, focus/scroll return, mobile-safe height and usable error/loading states. Do not invent a form success event or replace the client's form fields. Parent CSS styles the popup/iframe container; the form's internal styling belongs in the form builder's Custom CSS area. [W8]

### D. QC source and rendered output

Compare customer-facing text with the approved copy, compare all image URLs/placements, scan for private labels/placeholders, and render desktop/tablet/mobile widths. Check actual font faces loaded, overflow, image crops, full steps/letter, action behavior and reduced motion. A regex scan alone is not proof of visual correctness. Test the passed code after repairs without changing unrelated passing content.

**Output:** current responsive code-only TXT, appropriate HTML preview/deployment files, separate form CSS where required, minimal install notes and real check results. **QC/repair:** every required criterion >=8, no hard failures. Local tests are explicitly local; never mark them as completed GHL tests.

## Stage 13 - Install in GHL and test the actual visitor journey

### A. Install once in the right place

Use the correct sub-account. Go to Sites -> Funnels -> correct named folder -> existing or new funnel -> existing or new funnel page/step -> editor. Add/configure a full-width section, suitable one-column row and Custom HTML/JavaScript element. Set unwanted surrounding padding to zero. Paste the entire approved direct code or Vercel embed once, according to the selected route. Replace old code rather than placing another full copy underneath it. Keep the element visible for desktop and mobile. The GHL builder uses sections, rows, columns and elements; saving and publishing are separate operations. [W4]

### B. Check in GHL Preview

Confirm the correct current design, real hosted images and actual fonts. Click every CTA to confirm routing, but submit a shared form only once with a designated test contact. Check popup opening/closing, scroll return, mobile keyboard/scroll usability and orientation. If GHL delays critical custom initialization, apply its documented guidance rather than claiming the code works from a local screenshot. [W6]

For sales, verify the intended product/price and supported checkout path using test mode where available. Do not make an unauthorized live charge. For signups, confirm a real submission/contact and the specified confirmation/access path. For booking/downloads, confirm the actual outcome. A button opening is not completion of the visitor journey.

### C. Repair the relevant failure, not the whole project

A failed popup gets a popup repair plus checks of the affected buttons/scrolling. A font issue gets a font-loading/fit repair. Do not regenerate every image because one URL is wrong. If live GHL access is unavailable, report which test is outstanding and supply the minimum exact action required; do not fabricate a PASS.

**Output:** installed current page/embed and actual preview/action result. **QC/repair:** complete usable experience on the selected route, not merely attractive code.

## Stage 14 - Publish when authorized and check the public URL

### A. Apply the already established publication authority

If the job authorizes publication, do not invent another routine human sign-off gate. If authorization only covers drafting, do not publish. Confirm intended domain/path and existing page metadata, favicon/share asset and required supplied privacy links. Do not invent legal copy or extra tracking. Preserve the last known working code privately before replacement.

### B. Check delivery, not redesign

Open the public GHL URL after publication and verify that it displays the intended current version, loads its assets and performs the main action. For Vercel, inspect the actual GHL-embedded experience. Check at least the relevant desktop and phone presentation and any tablet-specific arrangement affected by the implementation. Repair real delivery defects; do not reopen passed copy for subjective polishing.

### C. Deliver the final files and concise result

Give the current code, maps, required assets/batches and install notes in a clear package. Keep prompts, source material, private framework notes and QC records out of the public site, but available in the authorized private handoff. State exactly what was tested, what was published and any genuine unresolved limitation. No completed declaration for an unfinished page.

**Output:** working public page when authorized, current deliverable package and short internal release record. **QC/repair:** correct version live, main action usable, no truncation or private-label leakage. This check reuses the established design; it is not another creative stage.

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

The production order, universal scope, below-8 repair rule, failed-only three-attempt allowance, 5,000-20,000 per-image prompt requirement, Google Fonts preference, image naming, shared 20-per-15-second submission ceiling, and no-private-label rule are Trevor's current instructions. The specific action templates and stage deliverables implement those instructions.

The source Graphics rules and retrieved hashes are recorded in [the image guide](BlackCEO-Signature-Image-Prompt-Creation-Guide-v1.md#15-source-record-and-translation-boundaries). Those sources retain their separate independent roles, stricter 8.5 averages and current 19,000-character runtime cap. The supplied legacy Midjourney document informs aesthetic guidance only; it does not control provider syntax or the current page sequence.

Public technical references checked September 30, 2026:

- W1: Google Fonts CSS2 API, https://developers.google.com/fonts/docs/css2 . Named font family/weight/style requests.
- W2: FontFaceSet.load, https://developer.mozilla.org/en-US/docs/Web/API/FontFaceSet/load . Loaded FontFace objects; not proof of every glyph or final visual fit.
- W3: KIE Getting Started, https://kie.ai/getting-started . Task lifecycle, current per-account submission limit and temporary media retention. The 15-second house window is deliberately stricter.
- W4: HighLevel Sites Overview, https://help.gohighlevel.com/support/solutions/articles/155000001633-sites-overview . Shared funnel/website builder structure and save/publish distinction.
- W5: HighLevel Payment Links, https://help.gohighlevel.com/support/solutions/articles/155000002177-payment-links . Hosted checkout tied to actual products/prices; not proof every order form has portable embed code.
- W6: HighLevel hydration event, https://help.gohighlevel.com/support/solutions/articles/155000002421-hydration-event-in-custom-code-in-funnels . Actual custom-code preview lifecycle guidance.
- W7: Vercel security headers, https://vercel.com/docs/cdn-security/security-headers . Embedding/security configuration; actual allowed origins must match the deployed job.
- W8: HighLevel form Custom CSS, https://help.gohighlevel.com/support/solutions/articles/155000006727-how-to-add-custom-css-to-forms-surveys-and-quizzes- . Form-internal versus parent-container styling.

No new client page, image, GHL folder, payment object or Vercel deployment is created by preparing this documentation package.
