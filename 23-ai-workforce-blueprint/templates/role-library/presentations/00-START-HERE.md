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

## What This Department Does

End-to-end branded webinar and slide deck production: copy writing, price ladder choreography, image prompt authoring, brand consistency, QC at every phase, image generation submission, media library management, PPTX assembly, adversarial review, hook development, live-presentation coaching, and verified final delivery.

### The Ten Required Presentation Components (master SOP Section 4.4)

Every deck must carry, and the QC Specialist gates, the operator's ten named required components: (1) the Promise (pitch the promise, not the product), (2) the Hook (written like a song, sung ~10x, minimum 7), (3) Case Studies / "who says so other than you" (third-party proof woven between the drops; zero-proof deck FAILS), (4) the Wall of Wins / wall of results, (5) One Big Idea Per Slide (multi-idea slide AUTO-FAILS), (6) the Guarantee, (7) the Scarcity Factor (last-calls / doors-closing, real only), (8) the Story Arc (short-term fix vs long-term identity; self-recognition), (9) the Gradual Price Ladder (value-plant anchor -> spread earned-reason drops -> add value every drop -> final late), and (10) "a checklist for an AI is a list of promises" (the QC / checklist philosophy). Producing roles: Director (1, 10), Hook Strategist (2), Deep Research (3, 4), Copywriter (all copy beats), Offer Price Strategist (6, 7, 9). Gating role: QC Specialist (copy QC criteria c1, c11, c18-c22 + AF-C6 + final-deck structural-completeness).

---

## Role Roster (22 roles)

| ROLE | Slug | Role type | File |
|------|------|-----------|------|
| ROLE-17 | brainstorming-buddy-presentations | specialist | brainstorming-buddy-presentations.md |
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
| ROLE-18 | typography-architect | specialist | typography-architect.md |
| ROLE-19 | presenters-guide-specialist | specialist | presenters-guide-specialist.md |
| ROLE-20 | presenters-speech-writer | specialist | presenters-speech-writer.md |
| ROLE-21 | fish-audio-expression-specialist | specialist | fish-audio-expression-specialist.md |
| ROLE-22 | first-time-onboarding-presentations | specialist | first-time-onboarding-presentations.md |

**New in the density-floor overhaul (2026-06-14):** ROLE-18 Typography Architect (locks the type/layout/treatment system in Phase 1.5, before any prompt), ROLE-19 Presenter's Guide Specialist (speaker-facing outline PDF + Notion), ROLE-20 Presenter's Speech Writer (word-for-word script at 130 wpm + audio demo via Fish > ElevenLabs > local + ffmpeg chunk/stitch), ROLE-21 Fish Audio / Expression Specialist (expression-tags the speech), ROLE-22 First-Time-User Onboarding (orients a newcomer once, then hands to the Brainstorming Buddy).

---

## Pipeline Sequence (phase order)

-2. **Step -2 (first use only)** -- ROLE-22 First-Time-User Onboarding orients a brand-new user once (what the dept does, the roles, the AUDIENCE-vs-SPEAKER surface distinction, how to start), sets the first-time flag, then hands to the Brainstorming Buddy. Skipped for returning users.
-1. **Step -1** -- ROLE-17 Brainstorming Buddy brainstorms with the owner (SIMPLE or EXTENSIVE interview, incl. the SOP-IMG-03 style branch that sets STYLE_SOURCE), confirms, and locks working/brainstorm/presentations/<slug>/brief.json; then hands the locked brief to the Director.
1. **Step 0** -- ROLE-06 Media Librarian creates the landing zone and acquires client assets (the single locked LOGO_URL, FOUNDER_PORTRAIT_URL).
2. **Step 0.5** -- ROLE-03 Capacity and Reliability Engineer probes the box and writes capacity_plan.json.
2a. **Phase -0.5 (MANDATORY on EVERY deck run -- personal brand AND general; dispatched by Director; runs BEFORE Phase B+)** -- ROLE-04 Deep Research Specialist runs six research categories (A: market/audience, B: competitor offer, C: social proof/evidence mining, D: industry statistics and external proof, E: grounded image content, F: design style and typography research). Blocks Phase B+ until `working/research/brief-[DECK_SLUG].md` is on disk with `research_complete: true` and all required categories present. The AF-RESEARCH-GATE at Phase 1Q enforces this mechanically. Category F routes its design-brief output to ROLE-18 Typography Architect (who loads it before authoring any layout template) and to ROLE-11 Slide Image Creator (who loads it before writing any image prompt). STYLE BRANCH for Category F: if the owner says "match existing deck" or "analyze reference," set `design_research_mode: delegated_to_DIU` and skip F1-F4; otherwise complete F1-F4. If a niche has no established design language, flag `design_research_mode: original_territory` and document what IS available.
3. **Phase B+** -- ROLE-15 Hook Strategist runs the Hook Lab; outputs hook_package.json.
4. **Phase 1** -- ROLE-10 Slide Copywriter (concurrent: ROLE-07 Offer and Price Strategist). Output: slides_copy.md + price_ladder.json.
5. **Phase 1Q** -- ROLE-09 QC Specialist runs copy QC gate (score >= 8.5).
6. **Phase 1A** -- Owner approval gate (Director-managed). No prompts until YES.
6.5. **Phase 1.5 (density-floor overhaul)** -- ROLE-18 Typography Architect locks type_system + layout_map + treatment_table and runs the self-audit; ROLE-02 Brand Steward locks the single LOGO_URL in parallel. Phase 2 is BLOCKED until these exist. Typography and layout are DECIDED before any prompt is written.
7. **Phase 2** -- ROLE-11 Slide Image Creator writes prompts TO the treatment table (requires the STYLE BLOCK from ROLE-02 and the three ROLE-18 artifacts). Logo via image-to-image (Mode B); hook slides pure-type; no footer hook; render only the approved copy blocks.
8. **Phase 3** -- ROLE-09 QC Specialist runs prompt QC gate (dual-scored).
9. **Phase 4** -- ROLE-12 Slide Submitter submits to Kie.ai (2 RPS cap, smoke test first).
10. **Phase 4 concurrent** -- ROLE-03 watchdog cron runs.
11. **Phase 5** -- ROLE-09 QC Specialist runs image QC gate.
12. **Phase 5 passed** -- ROLE-06 Media Librarian intakes passed images to GHL.
13. **Phase 6** -- ROLE-08 PPTX Assembly Specialist assembles the deck.
14. **Phase 6 QC** -- ROLE-09 QC Specialist runs final deck QC (score >= 8.5).
15. **Post-Phase 6** -- ROLE-19 Presenter's Guide Specialist builds the speaker-facing outline (PDF + Notion, font >= 12); ROLE-20 Presenter's Speech Writer writes the word-for-word script (130 wpm) and renders the audio demo (Fish > ElevenLabs > local + ffmpeg), with ROLE-21 Fish Audio / Expression Specialist tagging the script; ROLE-14 Presenter Coach writes the timed talk track and runs the rehearsal gate. The deck is the AUDIENCE surface; the Guide, Speech, and audio are the SPEAKER surface (the cardinal separation the reference failure case broke).
16. **Delivery** -- ROLE-13 Delivery Concierge delivers to all destinations and verifies (deliverables Trevor opens go to Downloads, clearly labeled).

On-call throughout: ROLE-05 Devil's Advocate (high-stakes reviews).

**ROLE-04 Deep Research Specialist:** MANDATORY Phase -0.5 on EVERY deck run (personal brand and general). NOT on-call -- it is a blocking phase gate dispatched by the Director after Step 0.5. See Phase -0.5 above. Output: `working/research/brief-[DECK_SLUG].md` (`research_complete: true`, categories A-F). Categories B/C/D feed Copywriter; E feeds Image Creator; F feeds Typography Architect AND Image Creator.

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
| Slide-Craft | sops/SOP-SLIDE-00-MASTER-QC-AUTOFAIL-RULESET.md | The master slide-craft auto-fail doctrine + the reconciliation map to the live codes | AF-C2/C6/C7/C9/C10/C11/P3/P12/I1/I11/I12/I13/F6/F7/F9/F10/F12/F13/F14/DH1/RESEARCH-GATE |
| Slide-Craft | sops/SOP-SLIDE-01-ONE-BIG-IDEA-PER-SLIDE.md | One core idea per slide; mandatory splits; text-block + word ceilings | AF-C6 + AF-C8 + copy c5 |
| Slide-Craft | sops/SOP-SLIDE-02-AUDIENCE-FACING-ONLY.md | Six banned audience-facing categories (speaker lines, build doctrine, image narration, telegraphing/"webinar", credentials, build tokens) | AF-C9 + AF-F9 + AF-F10 |
| Slide-Craft | sops/SOP-SLIDE-03-HOOK-DOCTRINE.md | The sacred refrain: 3-4 dedicated pure-type hook slides, ceiling not floor, no footer | AF-C2 + AF-P12 + AF-P3 + AF-I1 + AF-F9 |
| Slide-Craft | sops/SOP-SLIDE-04-DECK-DENSITY-AND-PACING.md | Beat spacing, build-up before drops, value-stack/promises/re-pitch presence, section floors | AF-C7 + copy c17/c19/c23/c24 |
| Pitch-Craft | sops/SOP-PITCH-01-SLOW-DROP-PROCESS.md | The slow-drop choreography: anchor early, spread beats, earned reason + added value per drop, late final | AF-C7 + copy c17 |
| Pitch-Craft | sops/SOP-PITCH-02-VALUE-STACK-AND-PROMISES.md | Itemized stack summed to a total exceeding the anchor; promises before the first number | Offer Price Strategist SOP 9.2 + Section 4.4 component gates |
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

The Graphics department's Design Intelligence Unit (DIU) -- Style Analyst, Deck Systems Specialist, Generation Operator, Photo Shoot Director, Fidelity Tester -- operates entirely within the Graphics department and does NOT touch the presentations pipeline. This department's webinar and deck production workflow (ROLE-01 through ROLE-17, the full phase sequence above, and the Kie.ai submission path via ROLE-12 Slide Submitter) is the authoritative source for webinar deck delivery. The DIU's Deck Systems Specialist analyzes and generates deck IMAGERY STYLE SYSTEMS only; deck narrative writing, price ladder choreography, PPTX assembly, and final submission to Kie.ai for webinar decks remain exclusively with this department. Any cross-department request that would route deck narrative or assembly work to the Graphics DIU is a misroute -- return it here.

**Permitted cross-department request (presentations → Graphics DIU):** This department MAY request a style card analysis from the Graphics DIU when a client wants a NEW webinar deck built to match an existing deck's visual aesthetic. In that case, ROLE-02 Brand Steward submits the reference deck to the Graphics DIU Style Analyst (via Chief Design Officer) for a PPT-tier style card; the resulting style ID is then passed back to ROLE-11 Slide Image Creator as the style reference for Phase 2 prompt authoring. The narrative, copy, and assembly pipeline remain entirely with this department; only the imagery style analysis crosses the boundary. This is the ONLY permitted cross-department call; all other DIU capabilities (photo shoot, generation operator, fidelity testing) are out of scope for this department.

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
5. **Then the build.** The Director dispatches the pipeline (Phase -1 -> Step 0 -> ... -> Phase 1.5
   Typography Architect -> Phase 2 ... -> Presenter Coach -> Guide/Speech/Audio per DELIVERABLE_SET
   -> Delivery Concierge), surfacing the owner-approval gate (Phase 1A) before any prompts.

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
