# 00 -- START HERE -- Presentations Department

> **SOP-LOCKED DEPARTMENT:** if you add/modify any SOP, role, or gate, you MUST update
> `PIPELINE-MANIFEST.json` + `build_deck.py` + a test. Run `scripts/sync_check.py` — it fails
> the gate if the Python and the SOP stack drift. Single source of truth:
> `universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json`. Procedure:
> `universal-sops/presentation-slide-craft/SOP-SLIDE-06-EXTENSION-AND-SYNC.md`.

**Version:** 1.4 | 2026-06-14 (density-floor overhaul: +5 roles, Phase 1.5, the slide-craft / design-system / image-library SOP clusters, and the enforcement-gate auto-fail batteries)
**Role library path:** 23-ai-workforce-blueprint/templates/role-library/presentations/
**SOP mirror path:** 23-ai-workforce-blueprint/templates/role-library/presentations/sops/

---

## ⛔ The ONE Sanctioned Build Command (entrypoint gate — read before you build)

> **There is exactly one way to build a deck**, and it is the canonical entry command:
>
> ```
> bash 23-ai-workforce-blueprint/scripts/presentation-canonical-entry.sh \
>     --run-dir <RUN_DIR> --slides slides.json --out <OUT>.pptx
> ```
>
> The entry script runs three **fail-closed** gates and only then dispatches the canonical
> orchestrator `run_signature_deck.py` → `build_deck.py` (kie.ai gpt-image-2 only, words baked
> into each image, zero native on-slide text, full phase-attestation chain):
> 1. **deps check** — the four runtime deps (`soffice`, `pdftoppm`, `reportlab`, `python-pptx`)
>    or the build refuses to start.
> 2. **bypass-scan** — refuses to start if any hand-rolled renderer/assembler is present in the
>    run directory: a non-canonical `*.py` defining a 2048×1152 `Image.new` slide canvas
>    (`AF-LOCAL-CANVAS`), a native `add_textbox`/`add_text_box` overlay, or a direct kie
>    `createTask` outside `build_deck.py` (`AF-CANONICAL-RENDER-BYPASS`).
> 3. **version/hash pin** — the deployed renderer must be in lockstep with the SOP/manifest
>    stack (`sync_check.py`) and match the pinned governed head.
>
> **`python3 working/*.py` — writing and running your own per-deck driver/submit/assemble
> scripts — is the ungoverned path and is FORBIDDEN.** It re-creates the retired "skip kie.ai
> for hook slides + paste words on top in PowerPoint" failure; every guardrail lives inside the
> canonical path, so the only way they fire is to go through this command. **Skipping any gate
> requires an explicit, logged owner/founder approval token** in
> `working/checkpoints/process_manifest.json` (`owner_skip_approval`: `approved:true` +
> `approved_by` + `reason`, naming the exact gate code) — never silently, never by an agent's
> own choice. Agent doctrine: see `BUILDER-PROMPT.md` STEP 2.

---

## What This Department Does

> **The true goal first (the crown over every activity below).** The #1 job of every deck this
> department produces is to **HOLD THE AUDIENCE'S ATTENTION for the whole duration** — so that the
> owner's offer or idea **re-ranks to the top of the audience's priority stack** (the PRIORITY
> SHIFT). The creativity of the imagery is the engine that holds attention; the DESIGNER and the
> CONTENT author are the two most important roles, and every other role exists to protect the
> attention they earn. A deck ships only if it engineers a deliberate **peak + ending** and the
> owner's thing is the **single most vivid element by the end.** Doctrine root:
> `universal-sops/CLIENT-WEBINAR-DECK-SOP.md` §0 (THE TRUE GOAL). Everything in the activity list
> below is *how* the department serves that goal — never a substitute for it.

End-to-end branded webinar and slide deck production: copy writing, price ladder choreography, image prompt authoring, brand consistency, QC at every phase, image generation submission, media library management, PPTX assembly, adversarial review, hook development, live-presentation coaching, and verified final delivery.

### Deck Types This Department Builds

- **Standard webinar / slide deck** (default) -- the proven Mode-A / Mode-B webinar arc (hook, story, teach, proof, offer ladder, close); Mode-A capped at 90 slides. This is the deck type every role below assumes unless `deck_type` says otherwise.
- **Trevor Otts Signature Presentation** (`deck_type: signature_presentation`, Skill 51) -- the SACRED 4-phase methodology (Avatar >= 11 -> Signature Story >= 13 -> Transformational Teaching >= 36 -> Purpose Pitch >= 40, >= 100 slides total), authored by the **Signature Presentation Architect** (`signature-presentation-architect.md`) and independently graded by the **QC Specialist (Signature Presentations)** (`qc-specialist-signature-presentations.md`), in one of four client-facing frames -- **The Rulebook / The Vault / The Quest / The Original**. The 8 Questions are asked one at a time (choice-first) and recorded as ONE atomic block; the 90-slide Mode-A cap is explicitly N/A for this type; a client-exact slide count still wins when logged. Activated by `deck_type: signature_presentation` in `working/copy/intake.json` -- the single switch that turns on the `_chk_sp_*` gates (which DEFER for every other deck type). See `51-signature-presentation/SKILL.md`, `51-signature-presentation/MASTERDOC.md`, and the department how-to ("Requesting a Signature Presentation").

### The Ten Required Presentation Components (director-of-presentations SOP (`checklist_of_promises`) + qc-specialist-presentations SOP 9.5 (PRESENTATION-MASTER-DOCTRINE.md §4))

Every deck must carry, and the QC Specialist gates, the operator's ten named required components: (1) the Promise (pitch the promise, not the product), (2) the Hook (written like a song, 3-4 dedicated pure-typography slides, ceiling not floor), (3) Case Studies / "who says so other than you" (third-party proof woven between the drops; zero-proof deck FAILS), (4) the Wall of Wins / wall of results, (5) One Big Idea Per Slide (multi-idea slide AUTO-FAILS), (6) the Guarantee, (7) the Scarcity Factor (last-calls / doors-closing, real only), (8) the Story Arc (short-term fix vs long-term identity; self-recognition), (9) the Gradual Price Ladder (value-plant anchor -> spread earned-reason drops -> add value every drop -> final late), and (10) "a checklist for an AI is a list of promises" (the QC / checklist philosophy). Producing roles: Director (1, 10), Hook Strategist (2), Deep Research (3, 4), Copywriter (all copy beats), Offer Price Strategist (6, 7, 9). Gating role: QC Specialist (copy QC criteria c1, c11, c18-c22 + AF-C6 + final-deck structural-completeness).

---

## Role Roster (34 roles, one unique ROLE number per file)

> **Fix-77 uniqueness rule:** every role file in this directory carries exactly one ROLE number
> (the `**Role number:**` header line inside the file), and no two files share one. The numbers
> below are copied FROM each file's header, not the other way around; `scripts/tests/test_fix77_roster_uniqueness.py`
> fails CI if the roster and the file headers ever disagree or if a number is claimed twice.

| ROLE | Slug | Role type | File |
|------|------|-----------|------|
| ROLE-01 | director-of-presentations | leadership | director-of-presentations.md |
| ROLE-02 | brand-steward | specialist | brand-steward.md |
| ROLE-03 | capacity-reliability-engineer | specialist | capacity-reliability-engineer.md |
| ROLE-04 | deep-research-specialist-presentations | deep-research | deep-research-specialist-presentations.md |
| ROLE-05 | devils-advocate-presentations | on-call | devils-advocate-presentations.md |
| ROLE-06 | media-librarian-ghl-updater | specialist | media-librarian-ghl-updater.md |
| ROLE-07 | offer-price-strategist | specialist | offer-price-strategist.md |
| ROLE-08 | pptx-assembly-specialist | specialist | pptx-assembly-specialist.md |
| ROLE-09 | qc-specialist-presentations | qc | qc-specialist-presentations.md |
| ROLE-10 | slide-copywriter | specialist | slide-copywriter.md |
| ROLE-11 | slide-image-creator | specialist | slide-image-creator.md |
| ROLE-12 | slide-submitter | specialist | slide-submitter.md |
| ROLE-13 | delivery-concierge | specialist | delivery-concierge.md |
| ROLE-14 | presenter-coach | specialist | presenter-coach.md |
| ROLE-15 | hook-strategist | specialist | hook-strategist.md |
| ROLE-16 | healer-presentations | healer | healer-presentations.md |
| ROLE-17 | brainstorming-buddy-presentations | specialist | brainstorming-buddy-presentations.md |
| ROLE-18 | typography-architect | specialist | typography-architect.md |
| ROLE-19 | presenters-guide-specialist | specialist | presenters-guide-specialist.md |
| ROLE-20 | presenters-speech-writer | specialist | presenters-speech-writer.md |
| ROLE-21 | audio-demonstration-specialist | specialist | audio-demonstration-specialist.md |
| ROLE-22 | first-time-onboarding-presentations | specialist | first-time-onboarding-presentations.md |
| ROLE-23 | content-to-presentation-architect | specialist | content-to-presentation-architect.md |
| ROLE-23B | attention-content-strategist | strategist | attention-content-strategist.md |
| ROLE-24 | prompt-author-presentations | specialist | prompt-author-presentations.md |
| ROLE-25 | qc-specialist-prompt-presentations | qc | qc-specialist-prompt-presentations.md |
| ROLE-26 | qc-specialist-image-presentations | qc | qc-specialist-image-presentations.md |
| ROLE-27 | qc-specialist-typography-presentations | qc | qc-specialist-typography-presentations.md |
| ROLE-28 | qc-specialist-speech-presentations | qc | qc-specialist-speech-presentations.md |
| ROLE-29 | fish-audio-expression-specialist | specialist | fish-audio-expression-specialist.md |
| ROLE-30 | qc-specialist-signature-presentations | qc | qc-specialist-signature-presentations.md |
| ROLE-31 | signature-presentation-architect | specialist | signature-presentation-architect.md |
| ROLE-32 | representation-casting-director | specialist | representation-casting-director.md |
| ROLE-33 | image-grounding-steward | specialist | image-grounding-steward.md |

**New in the density-floor overhaul (2026-06-14):** ROLE-18 Typography Architect (locks the type/layout/treatment system in Phase 1.5, before any prompt), ROLE-19 Presenter's Guide Specialist (speaker-facing outline PDF + Notion), ROLE-20 Presenter's Speech Writer (word-for-word script at 130 wpm + audio demo via Fish > ElevenLabs > local + ffmpeg chunk/stitch), ROLE-29 Fish Audio / Expression Specialist (expression-tags the speech), ROLE-22 First-Time-User Onboarding (orients a newcomer once, then hands to the Brainstorming Buddy).

---

## Pipeline Sequence (phase order)

> **This list is generated from `phases[]` in `universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json` (manifest_version 55, 55 phases) and MUST be kept in lockstep with it — GATE 4 of `scripts/ci/presentations-drift-gates.sh` fails CI if any manifest phase id below goes missing from this file.** The **order** shown is the manifest's own `order` field, the exact number `run_signature_deck.py` sorts phases on — it is a dispatch key, not a step count, which is why it runs negative, fractional, and out of round numbers. Every id is the literal `phases[].id` string; look it up in the manifest for its full preflight/gate-code contract.
>
> **Before phase order -1:** the Brainstorming Buddy (`brainstorming-buddy-presentations`, and, for a first-time owner, First-Time Onboarding `first-time-onboarding-presentations` first) hold the pre-manifest brainstorm that locks `working/brainstorm/presentations/<slug>/brief.json` and hands it to the Director. Neither step is a `phases[]` entry — the machine-checked, manifest-governed pipeline begins at intake.
>

### Upsell (P-U) phases — Wave D (manifest v54, added by the presentation rev2 batch)

The 15 P-U upsell phases below complete the 55-phase manifest. Each is CONDITIONAL (defer per its own preflight; a decline is a logged client waiver, never silence):

- **`P-U-SALES-COPY`** (order 3.6) — . Full contract: look it up in the manifest.
- **`P-U-CHECKOUT-COPY`** (order 3.7) — . Full contract: look it up in the manifest.
- **`P-U-VSL-RESEARCH`** (order 3.8) — . Full contract: look it up in the manifest.
- **`P-U-VSL-COPY`** (order 3.9) — . Full contract: look it up in the manifest.
- **`P-U-DESIGN-SALES`** (order 4.2) — . Full contract: look it up in the manifest.
- **`P-U-DESIGN-CHECKOUT`** (order 4.3) — . Full contract: look it up in the manifest.
- **`P-U-DESIGN-VSL`** (order 4.4) — . Full contract: look it up in the manifest.
- **`P-U-HTML-SALES`** (order 5.2) — . Full contract: look it up in the manifest.
- **`P-U-HTML-CHECKOUT`** (order 5.3) — . Full contract: look it up in the manifest.
- **`P-U-HTML-VSL`** (order 5.4) — . Full contract: look it up in the manifest.
- **`P-U-FORM-GATE`** (order 5.6) — . Full contract: look it up in the manifest.
- **`P-U-GHL-SALES`** (order 6.2) — . Full contract: look it up in the manifest.
- **`P-U-GHL-VSL`** (order 6.4) — . Full contract: look it up in the manifest.
- **`P-U-COLLATERAL`** (order 8.8) — . Full contract: look it up in the manifest.
- **`P-U-QC`** (order 9.05) — . Full contract: look it up in the manifest.

> **Conditional phases (do not assume every phase ran on every deck):** `P-CONVERTER` runs ONLY on the content-first path (Zoom/video/doc source) and DEFERS otherwise. `P-SP-INTAKE`, `P-SP-INTAKE-TRACE`, `P-SP-STRUCTURE`, and `P-SP-P3-HYGIENE` DEFER (return empty, no-op) unless `intake.json` declares `deck_type: signature_presentation` — they exist only for the Trevor Otts Signature Presentation type. `P-SP-CLAIM` is the exception among the signature-named gates: it runs on EVERY deck (never defers) as the router that fails closed if signature signals appear without the declaration. `P-SPEECH-QC` defers when no speech QC report exists (i.e., when the run's `DELIVERABLE_SET` did not put a speech in scope). **`P-U-SALES-BUILD`, `P-U-CHECKOUT-BUILD`, and `P-U-FORM-CHECKOUT`** (Wave C, manifest v51) DEFER unless the client elects the sales+checkout upsell (`intake/upsell-questions.json` `want_sales_checkout`, default YES; a decline is a logged client waiver, never silence). **`P-U-VSL-BUILD`** DEFERS unless the client elects the VSL upsell (`want_vsl_page`, default NO, opt-in only) and only ever runs after `P9.6-WEBINAR-VIDEO`. Every other phase below runs on every standard deck.
>
> **Executed counts (out of 40 enforced):** the count now depends on BOTH deck type AND the two upsell elections — see `DEPARTMENT-COUNTS-CANONICAL.md` for the full mechanically-derived table (deck type x sales/checkout x VSL). With both upsells unelected/unknown and no signature/content-conversion signals: **31 on a standard from-scratch deck, 35 on a signature deck, 32 on a content-conversion deck** (the pre-Wave-C baseline, unchanged when the upsells are declined). Do not restate the full matrix here — `DEPARTMENT-COUNTS-CANONICAL.md` is the single source; link to it.

1. **`P-CONVERTER`** (order -1) -- CONDITIONAL, content-first path only -- content-to-presentation-architect converts a Zoom/video/doc source into `intake.json` (`source_brief_origin: content-to-presentation-architect`); DEFERS unless a raw source is present. Mandates Phase -0.5 Deep Research immediately after (SOP 9.8 step 3).
2. **`P-0.5-RESEARCH`** (order -0.5) -- MANDATORY on every run -- deep-research-specialist-presentations runs the six research categories (A: niche deck structures, B: pricing/value benchmarking, C: supporting statistics, D: external corroboration/GP-8, E: grounded image context, F: design+hook+pacing best practices). Blocks everything downstream until `working/research/brief-*.md` carries `research_complete: true`. Category F routes to the Typography Architect and Slide Image Creator; the STYLE BRANCH (match/analyze -> `design_research_mode: delegated_to_DIU`, else complete F1-F4) is decided here.
3. **`P0A-INTAKE`** (order 0.1) -- director-of-presentations confirms the interview/intake and writes `intake.json`.
4. **`P-SP-CLAIM`** (order 0.14) -- ALWAYS RUNS (never defers) -- signature-presentation-architect: the SP router/claim gate. Fails closed if the run shows signature-presentation signals (an `sp_intake.json`, a set frame, a frame-selection question) but `deck_type` was never declared `signature_presentation` -- the gate that stops a signature deck from sneaking through the generic path by omitting the magic word.
5. **`P-SP-INTAKE`** (order 0.15) -- SIGNATURE-ONLY (defers otherwise) -- signature-presentation-architect runs the 8 Questions in ONE block + sets the client-facing frame (Rulebook/Vault/Quest/Original) + declares the offer(s).
6. **`P-SP-INTAKE-TRACE`** (order 0.16) -- SIGNATURE-ONLY -- signature-presentation-architect proves the intake was CONDUCTED choice-first, one bank question per turn (not a batched dump), against `working/interview/intake_transcript.json`.
7. **`P0B-PRIORITY`** (order 0.2) -- attention-content-strategist writes the Priority-Shift Spec (`priority_shift_spec.json`: `true_goal` + `priority_stack[]`, the Seven-P / Eight-Move build sequence) BEFORE any copy is written. All P0B gates DEFER until this spec exists.
8. **`P3-ARC`** (order 3) -- offer-price-strategist allocates the converting arc.
9. **`P-3.5-RESEARCH-MAP`** (order 3.5) -- deep-research-specialist-presentations maps the already-gathered facts/quotes/stats (Categories C/D/G/H) onto SPECIFIC slides, writing `working/research/research_map.json`. Phase 4 copy is BLOCKED until this map exists.
10. **`P4-COPY`** (order 4) -- slide-copywriter (concurrent: offer-price-strategist) writes `slides_copy.md` + `price_ladder.json`, loading `research_map.json` and weaving each assigned anchor into the copy.
11. **`P-SP-STRUCTURE`** (order 4.1) -- SIGNATURE-ONLY -- signature-presentation-architect locks the SACRED 4-phase arc (Avatar >=11 -> Story >=13 -> Teaching >=36 -> Pitch >=40, >=100 slides floor) with contiguous phase labels, image suggestions on every slide, and the N.E.E.I.T. / 4-Quadrant markers.
12. **`P-SP-P3-HYGIENE`** (order 4.15) -- SIGNATURE-ONLY -- qc-specialist-signature-presentations enforces no-pitch hygiene on the Teaching band: no offer name, price, or enroll/buy/scarcity CTA before the Phase-3-to-Phase-4 bridge.
13. **`P1Q-COPY-QC`** (order 4.2) -- qc-specialist-presentations runs the copy QC gate (score >= 8.5). This is the current "Phase 1Q" -- it is sequenced AFTER Slide Copy (order 4.2, not before it); a QC now follows the artifact it grades, which is the defect the O1 re-sequence fixed.
14. **`P-U-DESIGN-RENDER-SALES`** (order 4.21, kind: script) -- See manifest for the full contract.. Full contract: look it up in the manifest.
14. **`P-U-DESIGN-RENDER-CHECKOUT`** (order 4.31, kind: script) -- See manifest for the full contract.. Full contract: look it up in the manifest.
14. **`P-U-DESIGN-RENDER-VSL`** (order 4.41, kind: script) -- See manifest for the full contract.. Full contract: look it up in the manifest.
14. **`PF-DESIGN`** (order 4.5) -- typography-architect locks `type_system` + `layout_map` + `treatment_table` and runs the self-audit before any prompt is written.
15. **`P-TYPO-QC`** (order 4.6) -- qc-specialist-typography-presentations independently reviews the design brief.
16. **`P4-PROMPT`** (order 4.7) -- prompt-author-presentations writes each slide's image prompt to the treatment table, to the 9,000-character standard.
17. **`P-PROMPT-QC`** (order 4.8) -- qc-specialist-prompt-presentations independently (dual-scored) reviews the prompts.
18. **`P-STYLE-SPEC`** (order 4.84, kind: script) -- See manifest for the full contract.. Full contract: look it up in the manifest.
18. **`P-STYLE-PREVIEW`** (order 4.85) -- slide-image-creator renders 9 samples across 3 style variants; the owner picks 1 via their OWN gateway before the full render, and the winner's 3 representative renders are LOCKED + reused so Kie never double-charges.
19. **`P-STYLE-PICK`** (order 4.86, kind: script) -- See manifest for the full contract.. Full contract: look it up in the manifest.
19. **`P4-RENDER`** (order 4.9) -- slide-image-creator's deterministic render via `build_deck.py` (this script; the ONLY renderer -- Logo via image-to-image on Mode B; hook slides pure-type; no footer hook).
20. **`P-IMAGE-QC`** (order 4.95) -- qc-specialist-image-presentations runs the independent multimodal vision QC gate on every rendered slide.
21. **`P-SHIFT-QC`** (order 7.5) -- qc-specialist-presentations runs the Priority-Shift Ship Gate -- the ONLY phase where copy, design, and rendered images all coexist; the framework's 14-item pre-output checklist (item 0 = the North Star: attention is the #1 job).
22. **`P8-ASSEMBLE`** (order 8) -- pptx-assembly-specialist assembles the final deck PPTX.
23. **`P8.1-PDF-EXPORT`** (order 8.1, mechanical: `scripts/pdf_export.py`) -- exports the deck PDF (portable-document export, required delivery output + QC render).
24. **`P8.2-GUIDE`** (order 8.2, mechanical: `scripts/presenter_guide.py`) -- presenters-guide-specialist builds the speaker-facing outline PDF (font >= 12) + Notion.
25. **`P8.25-WORKBOOK`** (order 8.25, mechanical, resumes the canonical entry script) -- pptx-assembly-specialist builds the branded content-rich Workbook (regular PDF + fillable AcroForm PDF).
26. **`P8.3-INFOGRAPHIC`** (order 8.3, kind: script) -- See manifest for the full contract.. Full contract: look it up in the manifest.
26. **`P9-SPEECH`** (order 8.5, mechanical: `scripts/speech_build_harness.py`) -- presenters-speech-writer writes the word-for-word Presenter's Speech at 130 wpm (length-gated).
27. **`P8.4-FISH-TAG`** (order 8.52, mechanical: `scripts/speech_fish_tag.py`) -- fish-audio-expression-specialist expression-tags the speech for Fish Audio synthesis.
28. **`P9-SPEECH-WEBINAR-INTRO`** (order 8.54, mechanical: `scripts/synthesize_full_speech.py`) -- audio-demonstration-specialist renders the webinarized speech audio (welcome + Q&A + crescendo close framing).
29. **`P9.1-SPEECH-PDF`** (order 8.55, mechanical: `scripts/speech_spec_build.py` + `scripts/presenters_speech_pdf.py`) -- presenters-speech-writer renders the teleprompter-print Presenter's Speech PDF.
30. **`P-SPEECH-QC`** (order 8.6) -- CONDITIONAL, defers when no speech QC report exists -- qc-specialist-speech-presentations independently reviews the speech (average >= 8.5).
31. **`P-QC-AGGREGATE`** (order 8.65, mechanical: `scripts/qc_aggregate.py`) -- qc-specialist-presentations combines the six domain QC reports (Copy/Typography/Prompt/Image/Priority-Shift/Speech) into `working/qc/final_qc_report.json`, verifying independent-reviewer + anti-bypass provenance first.
32. **`P9.5-NOTES-SYNC`** (order 8.7) -- pptx-assembly-specialist syncs the notes pane AFTER the speech is finalized.
33. **`P-U-SALES-BUILD`** (order 8.75, mechanical: `scripts/sales_checkout_builder.py`) -- CONDITIONAL, upsell branch -- DEFERS unless the client elects it (`intake/upsell-questions.json` `want_sales_checkout`, default YES; a decline is a logged client waiver in the client's own words, never inferred from silence) -- media-librarian-ghl-updater builds the sales page AND the checkout page in one invocation (copy -> kie gpt-image-2 design -> HTML -> `06-ghl-install-pages/tools/ghl_rest_canvas.py` GHL funnel push-plan). Template: LOOP2C-VSL-SALES-CHECKOUT-WEBSITE.md.
34. **`P-U-CHECKOUT-BUILD`** (order 8.76, mechanical: `scripts/sales_checkout_builder.py --skip-design`) -- CONDITIONAL, upsell branch, same flag/waiver as `P-U-SALES-BUILD` -- re-invokes the same script with `--skip-design` (no fresh kie.ai spend) purely to give the checkout page its own tracked gate/AF code and step-count entry; `P-U-SALES-BUILD`'s single invocation already wrote `checkout.html`.
35. **`P-U-FORM-CHECKOUT`** (order 8.77, mechanical: `scripts/sales_checkout_builder.py --skip-design`) -- CONDITIONAL, upsell branch, same flag/waiver as `P-U-CHECKOUT-BUILD` -- INTERIM PLACEHOLDER: re-verifies the same `build_receipt.json` P-U-SALES-BUILD produced; no dedicated payment/lead-capture form-wiring implementation exists yet (see `SALES-CHECKOUT-BUILDER-SOP.md` SS4 "THE CHECKOUT FORM" for the proposed follow-up).
36. **`P9.2-GHL-UPLOAD`** (order 8.9, mechanical: `scripts/ghl_media_push.py`) -- media-librarian-ghl-updater uploads passed assets to the client's GHL media library.
37. **`P9.6-WEBINAR-VIDEO`** (order 8.92, mechanical, resumes the canonical entry script) -- media-librarian-ghl-updater builds the Ken Burns + xfade webinar video slideshow and pushes it to GHL's v3 500MB video tier.
38. **`P-U-VSL-BUILD`** (order 8.93, mechanical: `scripts/vsl_builder.py`) -- CONDITIONAL, upsell branch -- DEFERS unless the client elects it (`want_vsl_page`, default NO, opt-in only; a decline is a logged client waiver) -- media-librarian-ghl-updater builds the video-sales-letter page (kie design -> HTML -> GHL funnel push). MUST run after `P9.6-WEBINAR-VIDEO` (order 8.92) -- `verify_video_dependency()` fails closed (`AF-VSL-NO-VIDEO`) if `{deck_slug}-WEBINAR.mp4` does not exist yet. Template: LOOP2C-VSL-SALES-CHECKOUT-WEBSITE.md.
39. **`P7-TELEPROMPTER`** (order 8.95, mechanical: `scripts/build_teleprompter.py`) -- presenters-speech-writer builds the standalone scrolling teleprompter HTML app.
40. **`P9-DELIVER`** (order 9, mechanical: `scripts/synthesize_full_speech.py` + delivery interlock) -- delivery-concierge runs the postflight completeness gate and delivers to every destination (deliverables Trevor opens go to Downloads, clearly labeled).
41. **`P-BUNDLE-GATE`** (order 9.95, kind: script) -- See manifest for the full contract.. Full contract: look it up in the manifest.

On-call throughout: devils-advocate-presentations (high-stakes reviews).

**ROLE-04 Deep Research Specialist:** MANDATORY Phase -0.5 on EVERY deck run (personal brand and general). NOT on-call -- it is a blocking phase gate dispatched by the Director after Step 0.5. See Phase -0.5 above. Output: `working/research/brief-[DECK_SLUG].md` (`research_complete: true`, categories A-L). Categories B/C/D feed Copywriter; E feeds Image Creator; F feeds Typography Architect AND Image Creator. Category G (attributable quotes) -> Copywriter; H (fact-validation ledger) -> QC Specialist + Copywriter; I (objection research) -> Copywriter + Devil's Advocate; J (social proof) -> Copywriter; K (persuasion-framework validation) -> Director + Copywriter; L (compliance) -> Director + Devil's Advocate.

**Dogfooding doctrine (Workstream 1E):** Every role in this department that produces a deliverable (copy, prompts, images, layouts, assembly) MUST itself serve as a demonstration of the department's own doctrine. A slide written by the Copywriter is itself a proof-of-concept of AF-C1 through AF-C11. A prompt written by the Image Creator is itself a proof-of-concept of AF-P1 through AF-P16. An assembled PPTX produced by the Assembly Specialist is itself a proof-of-concept of AF-F1 through AF-F14. A layout template produced by the Typography Architect is itself a proof-of-concept of the min_body_pt and type_scale_steps requirements. The department's own internal documents -- SOPs, briefs, templates, schemas -- are held to the same bar as a client deliverable. A rule not enforced on the department's own artifacts does not exist.

**ROLE-16 Healer (LIVE)** receives: second consecutive stall handoffs from ROLE-03, loop-4 escalations from ROLE-09, API failCode events from ROLE-12, and any department error flag. Every such event is filed as a Bug Ticket to the ZHC Bugs Department first; the Triage and Dedup Analyst routes department-local Presentations defects to this Healer with the ticket bug_id.

> **STATUS NOTE - ROLE-16 The Healer (COMPLETE, full spec):** ROLE-16 is built to full spec per THE_HEALER_AND_BUGS_DEPARTMENT.md and the T3-BUGBOARD-HEALER-SPEC.md build contract. It is instantiated with department=Presentations and carries the three authority tiers (Tier 1 mechanical autonomous: apply immediately, log, report after; Tier 2 SOP-patch and core-file edits with notify plus version-bump and changelog; Tier 3 model-manifest changes, new roles or departments, doctrine, master SOP, pricing, brand, SOUL.md and USER.md, and command-center architecture held for the operator's written approval), the full Bug Ticket schema (bugs/bug-ticket-schema.json), all 12 Healer SOPs (9.1 to 9.12), and its failCode/stall/loop-4 triggers wired through the live ZHC Bugs Department (role-library/bugs/) which routes tickets to the assigned Healer. The Healer hands closed-out root causes, patches, regression entries, and teaching links to the Bug Librarian for the company-wide knowledge base. The role is on-demand by construction (no heartbeat, dormant until a trigger fires), so it adds zero token burn until dispatched.

---

## SOP Mirror Index

Each role's Section 9 (Standard Operating Procedures) is mirrored verbatim in sops/:

| SOP Mirror File | Source Role | SOPs Covered |
|----------------|-------------|--------------|
| sops/brainstorming-buddy-presentations-sops.md | brainstorming-buddy-presentations.md | 9.1 Simple Interview, 9.2 Extensive Interview, 9.3 Confirm-and-Lock, 9.4 Kickoff/Handoff |
| sops/brand-steward-sops.md | brand-steward.md | 9.1 Style Block, 9.2 Consistency Audit, 9.3 Exemplar Handoff |
| sops/capacity-reliability-engineer-sops.md | capacity-reliability-engineer.md | 9.1 Capacity Probe, 9.2 Watchdog Cron, 9.3 Model Routing |
| sops/deep-research-specialist-presentations-sops.md | deep-research-specialist-presentations.md | 9.1 Mandatory Phase -0.5 Research (all runs; categories A-F incl. Category F design/typography), 9.2 GP-8 Alert, 9.3 Design Style and Typography Research (Category F) |
| sops/delivery-concierge-sops.md | delivery-concierge.md | 9.0 Package Assembly and Hygiene Sweep (AF-DH1 gate; RUNS BEFORE 9.1), 9.1 Destination Resolution, 9.2 Upload, 9.3 Notification, 9.4 Verification |
| sops/devils-advocate-presentations-sops.md | devils-advocate-presentations.md | 9.1 Doctrine Review |
| sops/director-of-presentations-sops.md | director-of-presentations.md | 9.1 Interview, 9.2 PRD Gate, 9.3 Mode, 9.4 Slide Math, 9.5 Approval Gate, 9.6 Parallelization |
| sops/hook-strategist-sops.md | hook-strategist.md | 9.1 Hook Lab Gen+Score, 9.2 Variant Ladder+Audit |
| sops/media-librarian-ghl-updater-sops.md | media-librarian-ghl-updater.md | 9.1 Landing Zone, 9.2 Image Intake, 9.3 GHL Upload, 9.4 Verification, 9.5 Asset Acquisition |
| sops/offer-price-strategist-sops.md | offer-price-strategist.md | 9.1 Ladder, 9.2 Offer Stack, 9.3 Price Gate, 9.4 Straight Mode, 9.5 VIP, 9.6 Priceless Pitch, 9.7 SP-EXPERT, 9.8 Guarantee + Scarcity |
| sops/pptx-assembly-specialist-sops.md | pptx-assembly-specialist.md | 9.1 PPTX Build, 9.2 Portable-Document Export (system-wide deck PDF; required delivery output + QC render, Gate 6), 9.3 Text Overlay, 9.4 Typography-Safe Assembler |
| sops/presenter-coach-sops.md | presenter-coach.md | 9.1 Talk Track, 9.2 Q&A Prep, 9.3 Rehearsal Pack, 9.4 Rehearsal Gate |
| sops/qc-specialist-presentations-sops.md | qc-specialist-presentations.md | 9.1 Copy QC, 9.2 Prompt QC, 9.3 Image QC, 9.4 Loop Control, 9.5 Final Deck QC |
| sops/slide-copywriter-sops.md | slide-copywriter.md | 9.1 Write Slides, 9.2 Hook Placement, 9.3 Proof Integrity, 9.4 Mode B, 9.7 Doctrine |
| sops/slide-image-creator-sops.md | slide-image-creator.md | 9.1 15-Element Prompt, 9.2 Archetypes+Composition, 9.3 White-Base+Palette, 9.4 Engines+Overlays, 9.5 Strikethrough |
| sops/slide-submitter-sops.md | slide-submitter.md | 9.1 Model Manifest, 9.2 KIE Submit, 9.3 Poll+Download, 9.3a API Contract, 9.4 Budget Discipline, 9.5 Smoke Test |
| sops/healer-presentations-sops.md | healer-presentations.md | 9.1 Intake+Triage, 9.2 Diagnosis, 9.3 Fix Forward, 9.4 SOP Surgery, 9.5 Gap Detection, 9.6 Model Census, 9.7 Healing Report, 9.8 Regression Watch, 9.9 Core-File Surgery, 9.10 Settings Repair, 9.11 Teacher-Self, 9.12 Embedding Refresh |
| sops/typography-architect-sops.md | typography-architect.md | 9.1 Weight Ladder + Type Tokens, 9.2 Five-Archetype Layout Rotation, 9.3 Price-Typography System, 9.4 Per-Slide Type Plan + Anti-Cookie-Cutter Audit |
| sops/presenters-guide-specialist-sops.md | presenters-guide-specialist.md | 9.1 Build the Speaker Outline, 9.2 Beautiful PDF (font >= 12), 9.3 Notion, 9.4 Surface-Boundary Audit + Delivery |
| sops/presenters-speech-writer-sops.md | presenters-speech-writer.md | 9.1 Word-for-Word Speech at 130 wpm, 9.2 PDF + Notion, 9.3 Expression-Tag Handoff, 9.4 Audio Demo (TTS fallback chain + ffmpeg), 9.5 Surface-Boundary Audit + Delivery |
| sops/fish-audio-expression-specialist-sops.md | fish-audio-expression-specialist.md | 9.1 Tag for the Tier, 9.2 Word-Fidelity + Tag-Discipline Audit, 9.3 Cross-Tier Translation Guidance |
| sops/first-time-onboarding-presentations-sops.md | first-time-onboarding-presentations.md | 9.1 First-Time Orientation, 9.2 Roles Tour + Surface Explainer, 9.3 Hand to Buddy + Set Flag, 9.4 On-Demand Refresher |

**Mirror rule:** role file is authoritative. If a sops/ file diverges from the role file's Section 9, the role file wins and the mirror must be regenerated immediately. Never edit the sops/ file directly.

---

## Cluster SOP Library (standalone cross-role doctrine, added v12.7.0)

These standalone SOP documents live in `sops/` alongside the per-role mirrors. They are NOT role mirrors; they are cross-role doctrine the design-system overhaul authored, each carrying purpose, the hard rule, the enforcement check (mapped to the LIVE qc-specialist auto-fail codes), pass/fail examples drawn from the forensic reference deck and the gold-standard reference deck, and an escalation path. Where a cluster SOP names a draft auto-fail code (AF-HOOK, AF-AUD, AF-OBI, AF-DEN, AF-I8..I12, AF-D1..D3), that protection is ALREADY WIRED in qc-specialist-presentations.md under the repo's existing codes (AF-C2 / AF-C6 / AF-C7 / AF-C8 / AF-C9 / AF-P3 / AF-P12 / AF-I1 / AF-F6 / AF-F7 / AF-F9 / AF-F10 / AF-DC1..7 and copy QC c5 / c17 / c19 / c23 / c24); each SOP carries the reconciliation. Do not re-add a parallel auto-fail namespace.

| Cluster | SOP file | Covers | Live enforcement it documents |
|---------|----------|--------|-------------------------------|
| Intelligence-Engines | sops/SOP-ENGINE-00-INTELLIGENCE-ENGINES-FRAMEWORK.md | The nine named engines (Facial, Lighting, Typography, Story, World, Pricing, Hook, Recap, Product) each with definition + verify + failure modes; the single artifact proving the department runs this taxonomy | AF-FACE-MOOD + AF-LIGHT-SKINTONE + AF-TYPE-8THROW + AF-TYPE-SALESY-FONT + AF-STORY-CHARACTER-DRIFT + AF-PRODUCT-MISSING/INVENTED + AF-WORD-IMAGE-MISMATCH (+ naming-only: AF-C7/AF-DEN, AF-HOOK/AF-C2, c23/c24) |
| Slide-Craft | sops/SOP-SLIDE-00-MASTER-QC-AUTOFAIL-RULESET.md | The master slide-craft auto-fail doctrine + the reconciliation map to the live codes (incl. the 2026-06-17 Intelligence-Engines codes, Section 8) | AF-C2/C6/C7/C9/C10/C11/P3/P12/I1/I11/I12/I13/F6/F7/F9/F10/F12/F13/F14/DH1/RESEARCH-GATE + AF-LIGHT-SKINTONE/TYPE-8THROW/TYPE-SALESY-FONT/STORY-CHARACTER-DRIFT/PRODUCT-*/NO-FORMULA/NO-MEASURABLE-RESULTS/NO-FORK/NO-BEFORE-AFTER/NO-EXPERT-PROOF/EMPTY-NOTES-PANE/WORD-IMAGE-MISMATCH |
| Slide-Craft | sops/SOP-SLIDE-01-ONE-BIG-IDEA-PER-SLIDE.md | One core idea per slide; mandatory splits; text-block + word ceilings | AF-C6 + AF-C8 + copy c5 |
| Slide-Craft | sops/SOP-SLIDE-02-AUDIENCE-FACING-ONLY.md | Six banned audience-facing categories (speaker lines, build doctrine, image narration, telegraphing/"webinar", credentials, build tokens) | AF-C9 + AF-F9 + AF-F10 |
| Slide-Craft | sops/SOP-SLIDE-03-HOOK-DOCTRINE.md | The sacred refrain: 3-4 dedicated pure-type hook slides, ceiling not floor, no footer | AF-C2 + AF-P12 + AF-P3 + AF-I1 + AF-F9 |
| Slide-Craft | sops/SOP-SLIDE-04-DECK-DENSITY-AND-PACING.md | Beat spacing, build-up before drops, value-stack/promises/re-pitch presence, section floors | AF-C7 + copy c17/c19/c23/c24 |
| Pitch-Craft | sops/SOP-PITCH-01-SLOW-DROP-PROCESS.md | The slow-drop choreography: anchor early, spread beats, earned reason + added value per drop, late final | AF-C7 + copy c17 |
| Pitch-Craft | sops/SOP-PITCH-02-VALUE-STACK-AND-PROMISES.md | Itemized stack summed to a total exceeding the anchor; promises before the first number | Offer Price Strategist SOP 9.2 + director-of-presentations SOP checklist_of_promises + qc-specialist-presentations SOP 9.5 (PRESENTATION-MASTER-DOCTRINE.md §4) component gates |
| Pitch-Craft | sops/SOP-PITCH-03-RE-PITCH.md | Mandatory 4-7 slide post-price recap before the close | copy c23 + c24 + Offer Price Strategist SOP 9.9 |
| Pitch-Craft | sops/SOP-PITCH-04-WALL-OF-WINS.md | Real-client homage ~5 slides before the offer; never a child future-pace | copy c19 + c24 |
| Design-System | sops/SOP-DESIGN-00-INTEGRATION-MAP.md | Where each design rule lands + the reconciliation map to the live codes | AF-C2/P12/P3/I1/F6/F7/F9/F10/DC1..7 |
| Design-System | sops/SOP-DESIGN-01-CREATIVE-TYPOGRAPHY-GUIDE.md | Locked weight ladder, expressive display, per-word emphasis | AF-DC1..7 |
| Design-System | sops/SOP-DESIGN-02-PURE-TYPOGRAPHY-HOOK-SLIDES.md | Hook line large over a low-opacity image, no competing imagery, no footer | AF-F6 + AF-C2 |
| Design-System | sops/SOP-DESIGN-03-VARIABLE-LAYOUT-ANTI-TEMPLATE.md | Rotate archetype + word-block position; no single chassis | AF-F6 + AF-DC |
| Design-System | sops/SOP-DESIGN-04-LOGO-CONSISTENCY.md | One locked mark, image-to-image, drift is a defect (full gold-standard design proof) | AF-F7 + AF-I4 |
| Image-Design | sops/SOP-IMG-00-CLUSTER-INDEX-AND-WIRING.md | The image-gen + design-library cluster index | (reference) |
| Image-Design | sops/SOP-IMG-01-KIE-CALL-MECHANICS.md | The three Kie.ai modes (T2I / I2I / analysis) made exact; logo = I2I | slide-image-creator I2I path + AF-F7 |
| Image-Design | sops/SOP-IMG-02-DIU-INTEGRATION-AND-SEEDING.md | Wiring skill 45 into Presentations; seeding the empty library; the auto-handoff trigger | forward work (Brand Steward + DIU) |
| Image-Design | sops/SOP-IMG-03-STYLE-OR-CREATIVE-DEVELOP-CONVERSATION.md | The three-way style branch + the creative-develop probe flow + the NAMED-STYLES seed | forward work (Brainstorming Buddy + Brand Steward) |
| Image-Design | sops/SOP-IMG-04-SIGNATURE-STYLE-RECALL-AND-DIU-LOGO-I2I.md | "Use Style 1" recall; the DIU logo-as-image-to-image mechanic | forward work + slide-image-creator I2I path |

---

## Design Intelligence Unit (DIU) Boundary

The Graphics department's Design Intelligence Unit (DIU) -- Style Analyst, Deck Systems Specialist, Generation Operator, Photo Shoot Director, Fidelity Tester -- operates entirely within the Graphics department and does NOT touch the presentations pipeline. This department's webinar and deck production workflow (ROLE-01 through ROLE-33, the full phase sequence above, and the Kie.ai submission path via ROLE-12 Slide Submitter) is the authoritative source for webinar deck delivery. The DIU's Deck Systems Specialist analyzes and generates deck IMAGERY STYLE SYSTEMS only; deck narrative writing, price ladder choreography, PPTX assembly, and final submission to Kie.ai for webinar decks remain exclusively with this department. Any cross-department request that would route deck narrative or assembly work to the Graphics DIU is a misroute -- return it here.

**Permitted cross-department request (presentations → Graphics DIU):** This department MAY request a style card analysis from the Graphics DIU when a client wants a NEW webinar deck built to match an existing deck's visual aesthetic. In that case, ROLE-02 Brand Steward submits the reference deck to the Graphics DIU Style Analyst (via Chief Design Officer) for a PPT-tier style card; the resulting style ID is then passed back to ROLE-11 Slide Image Creator as the style reference for `P4-PROMPT` prompt authoring. The narrative, copy, and assembly pipeline remain entirely with this department; only the imagery style analysis crosses the boundary. This is the ONLY permitted cross-department call; all other DIU capabilities (photo shoot, generation operator, fidelity testing) are out of scope for this department.

---

## First-Time Onboarding (the owner's first-run experience)

When an owner first says something conversational like "I need a deck," "make me a webinar,"
or "I want a pitch," this is the front door to the whole department. The experience is:

1. **Conversational trigger, friendly answer.** The owner does not fill a form. The
   Brainstorming Buddy (ROLE-17) answers "Let's brainstorm it together first." It is FRIENDLY
   proactive Q&A: roughly 3 to 10 adaptive questions, NOT a 50-question dump.
2. **Use what we already know.** The Buddy reads workspace SOUL.md / USER.md / any prior brief
   and NEVER re-asks what the agent already knows (governing rule from the master SOP
   "never re-ask what the agent already knows"). It only asks the unknowns.
3. **Capture the scope + style up front (SOP 9.0).** Before the mode offer, the Buddy runs the
   pre-presentation capture: the six hard-required audience/content/hook fields PLUS the three
   scope fields and the style branch:
   - **DELIVERABLE_SET** (deck only / +guide / +guide+speech / +audio) -- offered as an explicit
     add-on menu so the owner knows the Guide, Speech, and Audio demo exist.
   - **WANT_AUDIO_DEMO** (+ voice/persona) -- only when "+audio" is chosen; the voice is never
     defaulted silently.
   - **TARGET_WPM** (default 140; 130 teach-heavy / 150-160 high-energy) -- only when a speech is
     in scope.
   - **STYLE BRANCH** -- "do you have a style to match, a reference deck to analyze, or should we
     CREATE a signature style?" On match/analyze, the Brand Steward submits the reference to the
     Graphics DIU Style Analyst for a PPT-tier style card (the only permitted DIU crossing);
     on create, the Brand Steward builds the STYLE BLOCK fresh.
4. **ECHO -> PRD -> checklist gate.** The Buddy reads the brief back for explicit sign-off
   (the ECHO protocol), then hands the locked brief to the Director, who runs the Echo / Mission
   PRD gate and the checklist before any build begins.
5. **Then the build.** The Director dispatches the pipeline (`P-CONVERTER`/`P-0.5-RESEARCH` -> `P0A-INTAKE`
   -> ... -> `PF-DESIGN` Typography Architect -> ... -> `P4-PROMPT` prompt authoring -> ... -> Presenter Coach
   -> Guide/Speech/Audio per DELIVERABLE_SET -> `P9-DELIVER` Delivery Concierge), surfacing the owner-approval
   gate (Phase 1A -- a legacy, pre-manifest label for this gate with no corresponding `phases[]` id; see
   `director-of-presentations.md`) before any prompts.

A first-time owner who says "I need a webinar" is therefore met with a brainstorm, asked only
the unknowns (3 to 10 questions, known context not re-asked), offered the guide/speech/audio
add-ons and the style branch, and shown an ECHO + PRD + checklist before a single slide is built.

---

## Master SOP Authority

All roles defer to: `universal-sops/CLIENT-WEBINAR-DECK-SOP.md`

### density-floor-overhaul SOP clusters (2026-06-14) -- these EXTEND the master SOP and are enforced as auto-fails by ROLE-09 QC

- **Slide-craft** (`universal-sops/presentation-slide-craft/`): SOP-SLIDE-01 One Big Idea, SOP-SLIDE-02 Audience-Facing Only, SOP-SLIDE-03 Hook Doctrine (ceiling + anti-footer), SOP-SLIDE-04 Deck Density and Pacing, MASTER-QC-AUTOFAIL-RULESET (the machine-checkable spec the QC gate is wired from).
- **Design-system** (`universal-sops/presentation-design-system/`): Creative Typography Guide, Pure-Typography Hook Slides, Variable Layout / Anti-Template, Logo Consistency. Owned at write time by ROLE-18 Typography Architect + ROLE-02 Brand Steward.
- **Image-library** (`universal-sops/presentation-image-library/`): SOP-IMG-01 Kie call mechanics per mode, SOP-IMG-02 DIU integration + library seeding, SOP-IMG-03 style branch + NAMED-STYLES seed, SOP-IMG-04 signature-style recall + DIU logo-as-I2I.

### The enforcement gate (why this overhaul exists)

The 77 prior auto-fails did NOT catch the reference failure case (hook on 40 slides, speaker/doctrine/meta/"webinar"/placeholder text on the face, a misspelled/mutated hook, multi-idea slides, a crammed offer, a drifting logo). ROLE-09 QC now blocks a deck that trips ANY of: AF-HOOK (hook on >4 slides, footer-stamped, zero dedicated, doubled, mutated, misspelled, or conflated with the signature quote), AF-AUD (speaker line, internal pitch doctrine, image narration, "webinar"/meta, credential dump, or a bracket/placeholder token on a rendered slide), AF-OBI (multi-idea slide, value trio on one slide, pain list, oversized table), AF-DEN (price beats <8 slides apart, anchor not near one-third, missing BUILDUP/value-stack/promises/re-pitch, Wall of Wins mis-spaced, section below floor), AF-D1/D2/D3 + AF-I11 (single-device typography, layout never varies, no dedicated hook slide, logo drift). A description-only rule does not stop a defect; every rule is a binary trigger checked before scoring with a deck/slide-level veto, and is promoted into the PRODUCING role's write/render-time constraint as well as the gate.

---

## Bug Filing

Every error, stall, or failCode in this department is a filing event. File using the Bug Ticket schema (see ZHC Bugs Department) before continuing stabilization. ROLE-16 Healer receives the routed ticket.

**Mandatory:** An unfiled bug is a future repeat. File first, then stabilize.
