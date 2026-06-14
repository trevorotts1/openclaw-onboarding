# 00 -- START HERE -- Presentations Department
**Version:** 1.8 | 2026-06-14
**Role library path:** 23-ai-workforce-blueprint/templates/role-library/presentations/
**SOP mirror path:** 23-ai-workforce-blueprint/templates/role-library/presentations/sops/

---

## What This Department Does

End-to-end branded webinar and slide deck production: copy writing, price ladder choreography, image prompt authoring, brand consistency, QC at every phase, image generation submission, media library management, PPTX assembly, adversarial review, hook development, live-presentation coaching, and verified final delivery.

### The Ten Required Presentation Components (master SOP Section 4.4)

Every deck must carry, and the QC Specialist gates, the operator's ten named required components: (1) the Promise (pitch the promise, not the product), (2) the Hook (written like a song, sung ~10x, minimum 7), (3) Case Studies / "who says so other than you" (third-party proof woven between the drops; zero-proof deck FAILS), (4) the Wall of Wins / wall of results, (5) One Big Idea Per Slide (multi-idea slide AUTO-FAILS), (6) the Guarantee, (7) the Scarcity Factor (last-calls / doors-closing, real only), (8) the Story Arc (short-term fix vs long-term identity; self-recognition), (9) the Gradual Price Ladder (value-plant anchor -> spread earned-reason drops -> add value every drop -> final late), and (10) "a checklist for an AI is a list of promises" (the QC / checklist philosophy). Producing roles: Director (1, 10), Hook Strategist (2), Deep Research (3, 4), Copywriter (all copy beats), Offer Price Strategist (6, 7, 9). Gating role: QC Specialist (copy QC criteria c1, c11, c18-c22 + AF-C6 + final-deck structural-completeness).

---

## Role Roster (22 roles; all live)

**Doctrine count:** all 22 roles are live to spec (ROLE-01 through ROLE-22). ROLE-22 is the Content-to-Presentation Architect added v1.8: the source-ingest front door that turns any owner-supplied source (YouTube, Vimeo, any video file, audio training, website, blog post, PDF, report, white paper, Zoom recording, Google Meet recording) into a build-ready presentation BRIEF for the deck pipeline. It transcribes or extracts the source, finds the main theme by hook analysis, builds a step-by-step teaching arc, attaches teaching devices (analogy / metaphor / mnemonic) with a simplify-when trigger, decides micro-vs-full, and hands a source brief to the Director. It enforces a hard privacy rule on recordings of identifiable people (extract the lessons, never the identity) and does NOT duplicate the Deep Research Specialist (no open-web search) or the Brainstorming Buddy (source present, not idea only). ROLE-18 through ROLE-21 are the presentation-overhaul roles added v1.7: the Typography Architect (per-slide type-layout system, runs BEFORE the Slide Image Creator), the Presenters Guide Specialist (branded speaker outline PDF + Notion), the Presenters Speech Writer (word-for-word script paced to TARGET_WPM=140, PDF + Notion), and the Audio Demonstration + Fish Audio Expression Specialist (expression-tagged TTS demo with the Fish S2-Pro -> ElevenLabs -> Whisper-STT-verify fallback chain). All four route deliverables through the Delivery Concierge for verified last-mile. ROLE-16 The Healer is **COMPLETE** and built to full spec: the companion document THE_HEALER_AND_BUGS_DEPARTMENT.md (plus the T3-BUGBOARD-HEALER-SPEC.md build contract) has been supplied, and the ZHC Bugs Department it files into is commissioned and present in this repo at role-library/bugs/ (Bug Intake Clerk, Triage and Dedup Analyst, Bug Librarian, the universal bug-ticket-schema.json, and the B-9.1 to B-9.5 SOPs), with the Healer Department at role-library/healer/ (Chief Healer + the per-department Healer template). ROLE-16 carries the three authority tiers, all 12 Healer SOPs (9.1 to 9.12), and its triggers are wired to a live Bugs Department.


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
| ROLE-21 | audio-demonstration-specialist | specialist | audio-demonstration-specialist.md |
| ROLE-22 | content-to-presentation-architect | specialist | content-to-presentation-architect.md |

---

## Pipeline Sequence (phase order)

-2. **Step -2 (source-ingest front door; only when a SOURCE is supplied)** -- ROLE-22 Content-to-Presentation Architect runs when the owner says "turn this <video|Vimeo|blog|PDF|report|white paper|audio|Zoom|Google Meet|link> into a presentation." It ingests the source per modality (video/audio = transcribe; web/blog = fetch + extract; PDF/report/white-paper = parse), enforces the hard privacy rule on recordings of identifiable people, finds the main theme by hook analysis, builds the step-by-step teaching arc with teaching devices, decides micro-vs-full, and writes working/content-to-presentation/<source-slug>/source_brief.json. It hands that source brief to the Director and flags that the audience/representation/style fields are NOT captured (route via ROLE-17's SOP 9.0, theme/arc/hook pre-seeded). If the owner has only an IDEA and no source, work starts at Step -1 instead.
-1. **Step -1** -- ROLE-17 Brainstorming Buddy brainstorms with the owner (SIMPLE or EXTENSIVE interview), confirms, and locks working/brainstorm/presentations/<slug>/brief.json; then hands the locked brief to the Director. When ROLE-22 produced a source brief, the Buddy captures only the audience/representation/style fields (REPRESENTATION_MIX, AUDIENCE_COMPOSITION_NOTE, VISUAL_MIX, DARK_OK, GROUNDED_CONTENT, DELIVERABLE_SET) and never re-asks the theme, arc, or hook the source brief already answers.
1. **Step 0** -- ROLE-06 Media Librarian creates the landing zone and acquires client assets (LOGO_URL, FOUNDER_PORTRAIT_URL).
2. **Step 0.5** -- ROLE-03 Capacity and Reliability Engineer probes the box and writes capacity_plan.json.
3. **Phase B+** -- ROLE-15 Hook Strategist runs the Hook Lab; outputs hook_package.json.
4. **Phase 1** -- ROLE-10 Slide Copywriter (concurrent: ROLE-07 Offer and Price Strategist). Output: slides_copy.md + price_ladder.json.
5. **Phase 1Q** -- ROLE-09 QC Specialist runs copy QC gate (score >= 8.5).
6. **Phase 1A** -- Owner approval gate (Director-managed). No prompts until YES.
7. **Phase 1.5 (type-layout gate)** -- ROLE-18 Typography Architect authors working/typography/type_layout_system.md (one distinct layout template per archetype) AFTER the STYLE BLOCK and arc_allocation.json exist and BEFORE the Slide Image Creator writes any prompt. This is a hard gate: it replaces the single hard-coded canonical hierarchy stack in slide-image-creator.md element 5, so the deck rotates layouts instead of stamping one frame. Hook slides are type-driven (no image OR <=15% opacity bg).
8. **Phase 2** -- ROLE-11 Slide Image Creator writes prompts (requires STYLE BLOCK from ROLE-02 AND type_layout_system.md from ROLE-18; element 5 of every prompt is sourced from the matching archetype layout template).
9. **Phase 3** -- ROLE-09 QC Specialist runs prompt QC gate (dual-scored).
10. **Phase 4** -- ROLE-12 Slide Submitter submits to Kie.ai (2 RPS cap, smoke test first).
11. **Phase 4 concurrent** -- ROLE-03 watchdog cron runs.
12. **Phase 5** -- ROLE-09 QC Specialist runs image QC gate (including the ROLE-18 layout-variety / image-position asserts).
13. **Phase 5 passed** -- ROLE-06 Media Librarian intakes passed images to GHL.
14. **Phase 6** -- ROLE-08 PPTX Assembly Specialist assembles the deck.
15. **Phase 6 QC** -- ROLE-09 QC Specialist runs final deck QC (score >= 8.5).
16. **Post-Phase 6** -- ROLE-14 Presenter Coach writes talk track and runs rehearsal gate.
17. **Post-Coach deliverables (per DELIVERABLE_SET, AFTER ROLE-14, BEFORE ROLE-13):** ROLE-19 Presenters Guide Specialist (if "+guide") writes the branded speaker-outline PDF + Notion page; ROLE-20 Presenters Speech Writer (if "+guide+speech") writes the word-for-word script paced to TARGET_WPM=140 as a PDF + Notion page; ROLE-21 Audio Demonstration + Fish Audio Expression Specialist (if WANT_AUDIO_DEMO=true / DELIVERABLE_SET "+audio") turns the QC-passed Speech into an expression-tagged TTS demo mp3. Each routes its deliverable through ROLE-13 for verified last-mile (no self-report).
18. **Delivery** -- ROLE-13 Delivery Concierge delivers the deck and every post-coach deliverable to all destinations and verifies (ground-truth: file hash + size).

On-call throughout: ROLE-05 Devil's Advocate (high-stakes reviews), ROLE-04 Deep Research Specialist.

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
| sops/deep-research-specialist-presentations-sops.md | deep-research-specialist-presentations.md | 9.1 Benchmark Research |
| sops/delivery-concierge-sops.md | delivery-concierge.md | 9.1 Destination Resolution, 9.2 Upload, 9.3 Notification, 9.4 Verification |
| sops/devils-advocate-presentations-sops.md | devils-advocate-presentations.md | 9.1 Doctrine Review |
| sops/director-of-presentations-sops.md | director-of-presentations.md | 9.1 Interview, 9.2 PRD Gate, 9.3 Mode, 9.4 Slide Math, 9.5 Approval Gate, 9.6 Parallelization |
| sops/hook-strategist-sops.md | hook-strategist.md | 9.1 Hook Lab Gen+Score, 9.2 Variant Ladder+Audit |
| sops/media-librarian-ghl-updater-sops.md | media-librarian-ghl-updater.md | 9.1 Landing Zone, 9.2 Image Intake, 9.3 GHL Upload, 9.4 Verification, 9.5 Asset Acquisition |
| sops/offer-price-strategist-sops.md | offer-price-strategist.md | 9.1 Ladder, 9.2 Offer Stack, 9.3 Price Gate, 9.4 Straight Mode, 9.5 VIP, 9.6 Priceless Pitch, 9.7 SP-EXPERT, 9.8 Guarantee + Scarcity |
| sops/pptx-assembly-specialist-sops.md | pptx-assembly-specialist.md | 9.1 PPTX Build, 9.2 PDF Render, 9.3 Text Overlay |
| sops/presenter-coach-sops.md | presenter-coach.md | 9.1 Talk Track, 9.2 Q&A Prep, 9.3 Rehearsal Pack, 9.4 Rehearsal Gate |
| sops/qc-specialist-presentations-sops.md | qc-specialist-presentations.md | 9.1 Copy QC, 9.2 Prompt QC, 9.3 Image QC, 9.4 Loop Control, 9.5 Final Deck QC |
| sops/slide-copywriter-sops.md | slide-copywriter.md | 9.1 Write Slides, 9.2 Hook Placement, 9.3 Proof Integrity, 9.4 Mode B, 9.7 Doctrine |
| sops/slide-image-creator-sops.md | slide-image-creator.md | 9.1 15-Element Prompt, 9.2 Archetypes+Composition, 9.3 White-Base+Palette, 9.4 Engines+Overlays, 9.5 Strikethrough |
| sops/slide-submitter-sops.md | slide-submitter.md | 9.1 Model Manifest, 9.2 KIE Submit, 9.3 Poll+Download, 9.3a API Contract, 9.4 Budget Discipline, 9.5 Smoke Test |
| sops/healer-presentations-sops.md | healer-presentations.md | 9.1 Intake+Triage, 9.2 Diagnosis, 9.3 Fix Forward, 9.4 SOP Surgery, 9.5 Gap Detection, 9.6 Model Census, 9.7 Healing Report, 9.8 Regression Watch, 9.9 Core-File Surgery, 9.10 Settings Repair, 9.11 Teacher-Self, 9.12 Embedding Refresh |
| sops/typography-architect-sops.md | typography-architect.md | 9.1 Type-Layout System Authoring, 9.2 Hook-Slide Typography Spec, 9.3 Layout-Variety Audit |
| sops/presenters-guide-specialist-sops.md | presenters-guide-specialist.md | 9.1 Guide Assembly, 9.2 PDF Render (fonts >=12), 9.3 Notion Publish, 9.4 Verified Delivery |
| sops/presenters-speech-writer-sops.md | presenters-speech-writer.md | 9.1 Word-for-Word Draft, 9.2 WPM Pacing Pass (TARGET_WPM=140), 9.3 Designed PDF Render (fonts >=12), 9.4 Notion Publish + Verified Delivery |
| sops/audio-demonstration-specialist-sops.md | audio-demonstration-specialist.md | 9.1 Expression Tagging, 9.2 Chunk + Synthesize (Fish S2 -> ElevenLabs -> fallthrough), 9.3 ffmpeg Stitch + Normalize, 9.4 STT Verify (Whisper), 9.5 Deliver Demo |
| sops/content-to-presentation-architect-sops.md | content-to-presentation-architect.md | 9.1 Source Ingestion per Modality (+ Privacy Rule), 9.2 Analysis + Hook Main-Theme + Teaching Arc, 9.3 Teaching Devices + Simplify-When, 9.4 Micro-vs-Full Decision, 9.5 Handoff, 9.6 Trigger Standard |

**Mirror rule:** role file is authoritative. If a sops/ file diverges from the role file's Section 9, the role file wins and the mirror must be regenerated immediately. Never edit the sops/ file directly.

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

---

## Bug Filing

Every error, stall, or failCode in this department is a filing event. File using the Bug Ticket schema (see ZHC Bugs Department) before continuing stabilization. ROLE-16 Healer receives the routed ticket.

**Mandatory:** An unfiled bug is a future repeat. File first, then stabilize.
