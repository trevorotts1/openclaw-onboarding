# Suggested Roles -- presentations-dept
**Version:** 2.0 | 2026-07-03
**Status:** The v12.20.0 canonical 24-role roster is extended with the **2 Skill-51 Signature-Presentation methodology roles** (`signature-presentation-architect`, `qc-specialist-signature-presentations`) and the **6 attention-strategy + prompt-authoring + specialist-QC roles** (`attention-content-strategist`, `prompt-author-presentations`, `qc-specialist-prompt-presentations`, `qc-specialist-image-presentations`, `qc-specialist-typography-presentations`, `qc-specialist-speech-presentations`) -> **32 roster roles**. Every roster role resolves to a role-library `_index.json` entry (verified green by `qc-assert-repo-consistency.py --only consistency` and `register-library-additions.py --check`). Every role header is CLEAN (no `(NEW)`, no `-- vX.Y`, no `renamed from ...`, no `&`/`+`/`'` decorations) and carries an explicit `**Slug:**` that matches its role-library `.md` file exactly. The slug is the canonical key for folder naming (`NN-<slug>/`) and role-library lookup.

## Canonical Role Count: 32
The canonical set is one role per role-library `.md` file under
`templates/role-library/presentations/` (excluding the `00-START-HERE.md` meta
doc, `BUILDER-PROMPT.md`, `how-to-use-this-department.md`, `IDENTITY.md`,
`SOUL.md`, `TOOLS.md`). The earlier "22 roles" figure undercounted: it omitted
the Content-to-Presentation Architect and folded the Audio Demonstration
Specialist and the Fish Audio Expression Specialist into a single line, while
both ship as distinct role-library docs. The number→slug map below is STABLE:
adding a role appends the next integer; existing numbers never renumber.

## Department Purpose
End-to-end branded webinar and slide deck production: copy writing, price ladder choreography, image prompt authoring, brand consistency, QC at every phase, image generation submission, media library management, PPTX assembly, adversarial review, hook development, live-presentation coaching, verified delivery, and department self-healing. Coordinates with Marketing (deck brief), CRM (GHL media library), Research (proof gaps), and the client's OpenClaw agent (discovery interview, approval gates, final delivery).

**Canonical Render Module (mandatory for all producing roles):** All image generation in this department MUST use the shared module at `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/build_deck.py`. Per-deck renderers are FORBIDDEN (AF-RENDERER auto-fail). The canonical module validates model sovereignty, prompt character floor, and structural block requirements before any API call, and writes the render record to `working/checkpoints/process_manifest.json` (via `write_process_manifest`) for QC verification. The older `templates/presentation-render/render_deck.py` + `render_manifest.json` path is RETIRED — its checks were folded into `build_deck.py` and nothing imports it; see `docs/LEGACY-RETIREMENT.md`.

**The Intelligence Engines (the department's named capability set):** Every deck is run against NINE named INTELLIGENCE ENGINES -- Facial, Lighting, Typography, Story, World, Pricing, Hook, Recap, and Product (roadmap) -- each defined with a verification check and auto-failed failure modes in `sops/SOP-ENGINE-00-INTELLIGENCE-ENGINES-FRAMEWORK.md`. The framework promotes the three engines the image pipeline already ran by name (Facial, Audience, World) and the two pitch mechanics (Hook, Recap) into the full set, and wires each engine to its enforcement (SOP-SLIDE-00 Section 8).

---

## Roles

### 0. Director of Presentations
**Slug:** director-of-presentations
**What it does:** Orchestrates the entire webinar deck pipeline from end to end. Runs the adaptive discovery interview, owns the PRD gate, dispatches all specialists, enforces every QC gate, manages the owner approval gate (Phase 1A), and delivers the final deck. Nothing ships without the Director's checkpoint.
**Core SOPs to build:**
- 01-Adaptive-Discovery-Interview.md
- 02-Echo-Protocol-and-Mission-PRD-Gate.md
- 03-Mode-Selection-and-Enhancement-Gap-Analysis.md
- 04-Slide-Count-Math-and-Arc-Allocation.md
- 05-Owner-Approval-Gate-and-Presenter-Notes-Export.md
- 06-Parallelization-and-Sequencing-Strategy.md
**Role type:** leadership

### 1. Slide Copywriter
**Slug:** slide-copywriter
**What it does:** Writes every word on every slide (Phase 1): headlines (max 9 words), subheads (max 18 words), body bullets (max 3), and presenter notes. Places the canonical hook on the 3 to 4 DEDICATED pure-typography hook slides named by the Hook Strategist and nowhere else. Enforces no-em-dash and no-fabrication rules. Produces slides_copy.md for the Phase 1Q QC gate and the owner approval gate.
**Core SOPs to build:**
- 01-Write-the-Slides-Words-First-One-Big-Idea.md
- 02-Hook-Authoring-and-Refrain-Placement.md
- 03-Proof-Integrity-and-No-Fabrication.md
- 04-Mode-B-Word-Preserving-Augmentation.md
**Role type:** specialist

### 2. Brand Steward
**Slug:** brand-steward
**What it does:** Creates and owns the STYLE BLOCK (800-1,500 characters): 3 hex codes with roles, typography system, logo placement rule, and representation ratio. Dispatched early in every run, before Phase 2. Runs the deck-level representation distribution audit after prompts are written.
**Core SOPs to build:**
- 01-Shared-STYLE-BLOCK-Authorship.md
- 02-Cross-Slide-Consistency-and-Representation-Ratio-Audit.md
**Role type:** specialist

### 3. Capacity and Reliability Engineer
**Slug:** capacity-reliability-engineer
**What it does:** Owns Step 0.5 (system capacity probe) and Phase 7 (resilience watchdog cron). Probes the client's box (free -h, nproc, uptime, df -h), verifies Ollama Cloud reachability, checks Kie.ai credit balance vs. budget ceiling, checks all 4 env stores for required keys, and writes capacity_plan.json with fleet sizing recommendations and a go/no-go decision. Installs a 15-minute watchdog cron after Phase 4 begins; removes it after Phase 6 completes.
**Core SOPs to build:**
- 01-System-Capacity-Probe-and-Fleet-Sizing.md
- 02-Resilience-Watchdog-Cron-and-Checkpoint-Recovery.md
- 03-Model-Routing-and-Env-Store-Verification.md
**Role type:** specialist

### 4. Deep Research Specialist - Presentations
**Slug:** deep-research-specialist-presentations
**What it does:** On-demand research specialist. Researches niche deck structures (Category A), proven price anchors (Category B), and proof statistics (Category C) for the client's industry. Produces a Research Brief with all findings cited (source URL + publication date + confidence level HIGH/MEDIUM/LOW). Never fabricates. Feeds the Slide Copywriter (proof gaps) and Offer and Price Strategist (price anchor benchmarks).
**Core SOPs to build:**
- 01-Niche-Deck-and-Offer-Benchmark-Research.md
**Role type:** deep-research

### 5. QC Specialist - Presentations
**Slug:** qc-specialist-presentations
**What it does:** Runs all four QC gates: Phase 1Q (copy, 14 criteria, double-weight on 1/2/7/11/12), Phase 3 (prompts, 15 criteria dual-scored, double-weight on 2/3/4/13), Phase 5 (images, 11 criteria, double-weight on 3/5/6/7), and Phase 6 (final deck). Threshold: at least 8.5. Loops back automatically for up to 3 attempts; escalates on attempt 4. Classifies image failures as render-noise, prompt-defect, or text-fail-x1/x2.
**Core SOPs to build:**
- 01-Copy-QC-Gate-Phase-1Q.md
- 02-Prompt-QC-Gate-Phase-3-Dual-Scored.md
- 03-Image-QC-Gate-Phase-5-and-Fail-Classification.md
- 04-Revision-Loop-Control-and-Escalation.md
- 05-Final-Deck-QC-Rendered-Pages.md
**Role type:** qc

### 6. Slide Submitter
**Slug:** slide-submitter
**What it does:** Submits all prompts to Kie.ai GPT Image 2 (Phase 4). Uses model gpt-image-2-image-to-image (with refs) or gpt-image-2-text-to-image (without refs) per the MODEL MANIFEST. Enforces the documented rate cap of 20 requests / 10 seconds (20 slides/wave + 10s sleep; source docs.kie.ai Section 8, verified 2026-06-14). Polls for completions (5-min initial wait, 60s intervals, 100-poll hard cap). Downloads to working/renders/. MUST call the canonical render module, not a per-deck renderer. Runs the generation budget discipline gate (warn at 1.5x, stop at 2x SLIDE_COUNT x $0.03).
**Core SOPs to build:**
- 01-Model-Manifest-and-Variant-Selection.md
- 02-KIE-Submit-and-Rate-Cap-20-requests-10-seconds.md
- 03-Loop-Guarded-Poll-and-Parallel-Download.md
- 04-Truncation-and-Generation-Budget-Discipline.md
**Role type:** specialist

### 7. Offer and Price Strategist
**Slug:** offer-price-strategist
**What it does:** Owns the price drop ladder choreography and offer stack construction. Sets the SPREAD LADDER at ~32/47/68/87/97% marks. Ensures ANCHOR_PRICE at least 3x FINAL_PRICE. Builds offer_stack.json and price_ladder.json. Runs the cross-slide numeric consistency gate (blocking QC gate) after copy is written.
**Core SOPs to build:**
- 01-Price-Drop-Ladder-Choreography.md
- 02-Offer-Stack-and-Value-Anchor-Construction.md
- 03-Cross-Slide-Numeric-Consistency-and-Price-Validation-Gate.md
**Role type:** specialist

### 8. PPTX Assembly Specialist
**Slug:** pptx-assembly-specialist
**What it does:** Assembles the final PowerPoint from QC-passed images using python-pptx (13.333 x 7.5 inch slides, full-bleed). Each slide is a SINGLE composed gpt-image-2 image (text baked in by the model); the only PPTX text part is the off-slide speaker-notes pane (from presenter_notes.json). Native text overlays are ELIMINATED (Decision 5C) — no pptx_text_overlays.json, no native on-slide text runs (AF-OVERLAY-DELIVERED). Renders to PDF via soffice --headless --convert-to pdf, then to PNG pages via pdftoppm -png -r 100 for Phase 6 QC.
**Core SOPs to build:**
- 01-PPTX-Build-with-Embedded-Speaker-Notes.md
- 02-Render-to-PDF-for-Final-QC.md
- 03-Native-Text-Overlay-Fallback.md
**Role type:** specialist

### 9. Slide Image Creator
**Slug:** slide-image-creator
**What it does:** Writes one 15-element image prompt per slide (Phase 2). Targets 5,000-7,500 characters per prompt (range: 1,500-15,000). Applies the STYLE BLOCK from the Brand Steward. Front-loads critical content. Handles price-drop strikethroughs and hook text overlays. Consumes type_layout_system.md from the Typography Architect so the deck rotates layouts instead of stamping one frame. Produces working/prompts/slide-NN-prompt.txt files.
**Core SOPs to build:**
- 01-Per-Slide-Prompt-Authoring-15-Element-Spec.md
- 02-Thirds-Grid-and-Composition.md
- 03-White-Base-and-Brand-Palette.md
- 04-Three-People-Engines-and-Overlays-and-Logo.md
- 05-Drawn-Strikethrough-and-Struck-Text-Handling.md
**Role type:** specialist

### 10. Media Librarian and GHL Updater
**Slug:** media-librarian-ghl-updater
**What it does:** Creates the local + GHL media library folders at Step 0 (first action, always). Intakes passed images from Phase 5 into working/media-library/ (local naming: slide-NN.png). Uploads each passed image to GHL immediately (GHL naming: Slide NN v<N>). Runs the final delivery verification: local count == GHL count == slide_count_final before PPTX assembly begins. Hands off to the Delivery Concierge after PPTX assembly.
**Core SOPs to build:**
- 01-Step-0-Landing-Zone-Creation.md
- 02-Passed-Image-Intake.md
- 03-GHL-Drive-Upload.md
- 04-Delivery-and-Ground-Truth-Verification.md
**Role type:** specialist

### 11. Devils Advocate - Presentations
**Slug:** devils-advocate-presentations
**What it does:** Adversarial on-call reviewer. Reviews any deck marked "high-stakes" against the 18-point Pitch Doctrine from master SOP Section 4.3. Produces a Kill List: every doctrine violation with the specific slide number, the specific violation text, the severity (HIGH/MEDIUM/LOW), and the specific fix required. Focuses on: hook count, anchor ratio, dark-slide creep, overclaimed promises, fabricated proof, price choreography, and CTA clarity.
**Core SOPs to build:**
- 01-Adversarial-Doctrine-Review-and-Kill-List.md
**Role type:** on-call

### 12. Delivery Concierge
**Slug:** delivery-concierge
**What it does:** Owns Phase 6+ multi-destination deck delivery. Resolves all delivery destinations from the Director's intake, uploads to each (GHL, Google Drive, local Mac Downloads), sends verified delivery notifications via openclaw message send, runs ground-truth verification (file hash + size), and writes a delivery_complete ledger entry. Every other producing role routes its deliverables through this role for verified last-mile (never self-report).
**Core SOPs to build:**
- 01-Destination-Resolution.md
- 02-Multi-Destination-Upload.md
- 03-Notification.md
- 04-Ground-Truth-Verification.md
**Role type:** specialist

### 13. Presenter Coach
**Slug:** presenter-coach
**What it does:** Owns the live-presentation preparation layer. Writes a timed talk track (slide-by-slide narration against DURATION_MIN), preps Q and A objection answers for the 10 hardest questions, builds a one-page rehearsal run sheet, and runs a mandatory rehearsal gate (deck is not webinar-ready until owner completes at least one aloud run). Hands off to the Delivery Concierge.
**Core SOPs to build:**
- 01-Talk-Track.md
- 02-QandA-Objection-Prep.md
- 03-Rehearsal-Pack.md
- 04-Rehearsal-Gate.md
**Role type:** specialist

### 14. Hook Strategist
**Slug:** hook-strategist
**What it does:** Owns the Hook Lab end-to-end. Generates 10 hook candidates (at least 1 per formula across 7 formulas: F1 Purple Rain / F2 Contrarian / F3 Specificity Bomb / F4 Identity Claim / F5 Before-After / F6 Two-Truths / F7 Direct Prediction), scores each on 5 dimensions (Memorable/Provocative/Punchy/Specific/Singable), field-tests top 3 (say-it-aloud / 3-second recall / T-shirt / cookout tests), presents to owner for selection. Builds variant ladder (7-10 variants), placement map, and runs post-deck hook audit. Outputs hook_package.json consumed by the Slide Copywriter.
**Core SOPs to build:**
- 01-Hook-Generation-and-Scoring.md
- 02-Variant-Ladder-Placement-Map-Post-Deck-Hook-Audit.md
**Role type:** specialist

### 15. Healer - Presentations
**Slug:** healer-presentations
**What it does:** Department immune system. Receives second-consecutive-stall handoffs from the Capacity and Reliability Engineer, loop-4 escalations from the QC Specialist, and Phase-4 API failCode events from the Slide Submitter. Diagnoses root cause using five-whys on evidence (dispatches the Deep Research Specialist for provider docs). Fixes the run (Tier 1: mechanical hot-patch, resume from last good checkpoint). Patches the SOP that allowed the failure so it never recurs (Tier 2: SOP surgery, mirror regeneration, regression entry). Proposes model manifest changes and new specialists to the operator and holds until approved (Tier 3). Reports every heal to the Director, CEO orchestrator, and operator before closing the incident. Runs monthly model currency census on GPT Image 2 / Minimax m3 / DeepSeek models in this department.
**Core SOPs to build:**
- 01-Intake-and-Triage.md
- 02-Root-Cause-Diagnosis.md
- 03-Fix-Forward.md
- 04-SOP-Surgery.md
- 05-Gap-Detection.md
- 06-Model-Census.md
- 07-Healing-Report.md
- 08-Regression-Watch.md
- 09-Core-File-Surgery.md
- 10-Settings-Repair.md
- 11-Teacher-Self.md
- 12-Embedding-Refresh.md
**Role type:** healer

### 16. Brainstorming Buddy - Presentations
**Slug:** brainstorming-buddy-presentations
**What it does:** The department Step -1 (runs BEFORE the Director). When the owner says "how do I get started / make a presentation?", this role brainstorms with them BEFORE the build: asks 1-2 opening framing questions, offers a SIMPLE interview (7 questions or fewer) or an EXTENSIVE interview (10 to 20 questions, back-and-forth), confirms what it learned with the owner (read-back + explicit sign-off), writes the binding brief.json at working/brainstorm/presentations/<slug>/brief.json, and kicks off the build by handing the locked brief to the Director of Presentations. The Director's SOP 9.1 ingests and validates the brief and never re-interviews the owner.
**Core SOPs to build:**
- 01-Simple-Interview-7-Questions-or-Fewer.md
- 02-Extensive-Interview-10-to-20-Questions.md
- 03-Confirm-and-Lock.md
- 04-Kickoff-and-Handoff.md
**Role type:** specialist

### 17. Typography Architect
**Slug:** typography-architect
**What it does:** Runs as a Phase-0.7/1.5 gate AFTER the Brand Steward emits the STYLE BLOCK and the Director emits arc_allocation.json, and BEFORE the Slide Image Creator writes any prompt. Designs one distinct TYPE-LAYOUT SYSTEM CARD per slide archetype (hook / divider / teach-one-big-idea / jaw-drop standalone / data / wall-of-wins / offer-component-card / CTA): image position, word-placement zone, type treatment, and a do/never list. Replaces the single hard-coded canonical hierarchy stack so the deck rotates layouts instead of stamping one frame. Hook slides are type-driven (no image OR at most 15% opacity background). Enforces image-position rotation (no more than 2 consecutive slides same position) and type-family rotation (no more than 3 consecutive). Outputs working/typography/type_layout_system.md, the required input to the Slide Image Creator.
**Core SOPs to build:**
- 01-Type-Layout-System-Authoring.md
- 02-Hook-Slide-Typography-Spec.md
- 03-Layout-Variety-Audit.md
**Role type:** specialist

### 18. Presenters Guide Specialist
**Slug:** presenters-guide-specialist
**What it does:** Converts the QC-passed deck + the Presenter Coach talk track into a beautiful speaker-facing OUTLINE (one block per section and per slide: slide thumbnail ref, the one point to drive home, the beat/transition, the time budget, ladder/hook cues). Speaker-facing run-of-show, NOT the word-for-word script. Renders a designed, branded PDF (no font below 12pt) AND a Notion page (Notion to Google Docs to text fallback chain). Delivers via the Delivery Concierge (verified last-mile, never self-report). Runs only if DELIVERABLE_SET includes the guide.
**Core SOPs to build:**
- 01-Guide-Assembly.md
- 02-PDF-Render-Fonts-12-or-Larger.md
- 03-Notion-Publish-Fallback-Chain.md
- 04-Verified-Delivery-via-Delivery-Concierge.md
**Role type:** specialist

### 19. Presenters Speech Writer
**Slug:** presenters-speech-writer
**What it does:** Writes the FULL word-for-word "here is what you say" script keyed to each slide, paced to TARGET_WPM (default 140; 130 teach-heavy, 150-160 high-energy), hook sung on its scheduled beats, drops with earned reasons + timed pauses, no em dashes. Asserts total_words / TARGET_WPM lands within plus or minus 10% of DURATION_MIN, and records TARGET_WPM=140 as the SOP constant so it is never silently 150. Renders a designed PDF (no font below 12pt) + a Notion page, per-slide pace markers. Sibling to the Guide (Guide = at-a-glance outline, Speech = full read). Delivers via the Delivery Concierge. Runs only if DELIVERABLE_SET includes the speech.
**Core SOPs to build:**
- 01-Word-for-Word-Draft.md
- 02-WPM-Pacing-Pass-TARGET-WPM-140.md
- 03-Designed-PDF-Render-Fonts-12-or-Larger.md
- 04-Notion-Publish-and-Verified-Delivery.md
**Role type:** specialist

### 20. Audio Demonstration Specialist
**Slug:** audio-demonstration-specialist
**What it does:** Turns the QC-passed Presenters Speech into a marketable AUDIO DEMO. Owns the expression engine (Fish Audio expression tags / emphasis / pauses / energy mapped to hook, jaw-drops, drops) and authoritatively documents the ElevenLabs v2-vs-v3 difference for correct fallback mode-switching. Runs the TTS FALLBACK CHAIN: PRIMARY Fish Audio S2-Pro -> FALLBACK ElevenLabs v3 / v2 -> FINAL leg local Whisper/STT (faster-whisper) as the round-trip word-match VERIFICATION leg. Chunks long talks, synthesizes per chunk, ffmpeg-concats + loudness-normalizes, STT-verifies at least 95% word-match. Runs only when WANT_AUDIO_DEMO=true. Delivers via the Delivery Concierge.
**Core SOPs to build:**
- 01-Expression-Tagging.md
- 02-Chunk-and-Synthesize-Fallback-Chain.md
- 03-ffmpeg-Stitch-and-Loudness-Normalize.md
- 04-STT-Verify-Whisper-Word-Match.md
- 05-Deliver-Demo.md
**Role type:** specialist

### 21. Fish Audio Expression Specialist
**Slug:** fish-audio-expression-specialist
**What it does:** Makes the audio demonstration of the Presenter's Speech sound like a real, emotionally alive human delivering a high-stakes pitch, not a flat robot. Takes the clean word-for-word script from the Presenters Speech Writer and marks it up with Fish Audio expression tags so the right words land with emphasis, the drops breathe, the hook hits, and the emotional beats actually feel emotional. The expression-markup companion to the Audio Demonstration Specialist; the Audio Demonstration Specialist owns the full synthesis + verify chain while this role owns the deep expression-tag craft.
**Core SOPs to build:**
- 01-Expression-Tag-Markup.md
- 02-Emphasis-and-Pause-Mapping.md
**Role type:** specialist

### 22. First-Time-User Onboarding - Presentations
**Slug:** first-time-onboarding-presentations
**What it does:** The owner's first-run welcome and the department's front door. On a first-time Presentations request it detects first-time use (working/presentations/onboarding_state.json), orients the owner in under 3 minutes (what the department does, the roles available, the Brainstorming Buddy, how to get started, and the AUDIENCE-versus-SPEAKER surface distinction), then hands straight to the Brainstorming Buddy and sets first_time_complete so it never repeats. Re-runnable on request ("remind me how this works") without resetting the flag. Builds nothing; it orients and triggers. Runs as Step -2, before the Brainstorming Buddy.
**Core SOPs to build:**
- 01-First-Time-Orientation.md
- 02-Roles-Tour-and-Surface-Explainer.md
- 03-Hand-to-the-Brainstorming-Buddy-and-Set-the-Flag.md
- 04-On-Demand-Refresher.md
**Role type:** specialist

### 23. Content-to-Presentation Architect
**Slug:** content-to-presentation-architect
**What it does:** The front door for one specific request: "turn THIS into a presentation." The owner hands over a source (a video, an audio training, a webpage, a blog post, a report, a white paper, a recorded meeting) and this role turns it into a build-ready presentation BRIEF the existing deck pipeline can build from directly. An INGEST-AND-STRUCTURE role: it acquires the source, decides up front whether the deck is for ONE named person or a GENERAL audience, transcribes/extracts the text, strips conversational fluff, finds what it is really teaching, builds a step-by-step teaching arc, chooses the teaching devices that make it stick, decides micro vs full presentation, and writes all of that into one structured brief, then hands the brief to the Director of Presentations.
**Core SOPs to build:**
- 01-Source-Acquisition-and-Audience-Decision.md
- 02-Transcribe-Extract-and-De-Fluff.md
- 03-Teaching-Arc-and-Device-Selection.md
- 04-Micro-vs-Full-Decision-and-Brief-Handoff.md
**Role type:** specialist

### 24. Signature Presentation Architect
**Slug:** signature-presentation-architect
**What it does:** Owns the Signature Presentation deck type end to end (Skill 51): the 4-phase methodology (Avatar 1-11 -> Signature Story 12-24 -> Transformational Teaching 25-60 -> Purpose Pitch 61-100, expanding to >=100 slides), the 8-Questions-in-ONE-block intake, frame selection (rulebook | vault | quest | original), and the structure ledger. Sets `deck_type: signature_presentation` in `working/copy/intake.json` (the single switch that activates every SP gate), builds `sp_intake.json` + `sp_structure.json`, then dispatches the four phase-authors and hands off to the existing pipeline. Never renders, assembles, or delivers; never floors/caps/reinterprets the SACRED law. The methodology is machine-enforced by three fail-closed provers (`prove_sp_intake.py`, `prove_sp_structure.py`, `prove_sp_no_pitch.py`) wired as manifest phases P-SP-INTAKE / P-SP-STRUCTURE / P-SP-P3-HYGIENE.
**Core SOPs to build:**
- 01-The-8-Questions-Asked-All-at-Once.md
- 02-Frame-Selection-and-Template-Load.md
- 03-Four-Phase-Arc-and-Labels.md
- 04-Expansion-to-100-Math.md
- 05-Handoff-to-Copywriter-Hook-Lab-Phase-Authors.md
**Role type:** specialist

### 25. QC Specialist - Signature Presentations
**Slug:** qc-specialist-signature-presentations
**What it does:** The INDEPENDENT grader for the Signature Presentation deck type (Skill 51). Clones the department QC pattern: AUTO-FAIL battery first (the AF-SP-* codes, re-verified semantically on top of the deterministic provers), then scored average >= 8.5 on a 10.0 scale with a 7.0 per-item floor. Carries the mandatory `qc_independence` provenance block (a self-graded / builder-graded report is refused), loops back automatically for up to 3 attempts, escalates on the 4th. Adds the semantic layer on top of the provers: does the copy actually teach (not pitch) in Phase 3, does the frame tone ladder hold, is Movement+Message+Methodology present, does the close land manifesto-grade. Never authors, never waives an auto-fail, never grades its own work.
**Core SOPs to build:**
- 01-Intake-QC-P-SP-INTAKE.md
- 02-Structure-QC-P-SP-STRUCTURE.md
- 03-Phase-3-No-Pitch-QC-P-SP-P3-HYGIENE.md
- 04-Rework-Loop-and-Escalation.md
**Role type:** qc

### 26. Attention Content Strategist
**Slug:** attention-content-strategist
**What it does:** Owns the strategic CONTENT SPINE of every deck at Phase P0B-PRIORITY (order 0.2), between intake and the arc. Names the PRIORITY SHIFT (re-ranking the owner's offer to the top of the audience's priority stack), runs the seven-P diagnosis, decides the creation mode, and authors the eight-move build sequence plus the norm-challenging Proclamations. Guards the CROWN law: holding attention for the full duration is the #1 job, above clarity and completeness. Its single canonical output is `working/copy/priority_shift_spec.json`, which the arc allocator, copywriter, price strategist, hook strategist, and QC composite gate all read from. Never fabricates a client claim; flags gaps to the owner.
**Core SOPs to build:**
- 01-Attention-Is-the-Product-Northstar.md
- 02-Seven-P-Model-and-Diagnostic.md
- 03-Three-Creation-Modes.md
- 04-Eight-Move-Build-Sequence.md
- 05-Dare-to-Challenge-the-Norm-Proclamations.md
**Role type:** strategist

### 27. Prompt Author - Presentations
**Slug:** prompt-author-presentations
**What it does:** Writes each slide's rich image prompt to the 9,000-to-18,000-character density band (hard floor 9,000, ceiling 18,000) that the renderer (`build_deck.py`) sends to the image model verbatim. Sits after the Typography Architect and before the deterministic render. Encodes the 15-element structural specification per prompt: archetype declaration, scene, every line of verbatim copy with per-line weight and point size, the three-engine facial intelligence with explicit REPRESENTATION_MIX, composition grid, lighting, color/brand palette, the eight-class NEGATIVE BLOCK, per-string spelling-locks, and the image-to-image logo directive. Spends the expanded budget only on defect-preventing specificity, never padding. Output is graded by the independent Prompt QC Specialist; never grades its own prompts.
**Core SOPs to build:**
- 01-Fifteen-Element-Prompt-Structure.md
- 02-Creative-Typography-Guide.md
- 03-Pure-Typography-Hook-Slides.md
- 04-Variable-Layout-Anti-Template.md
- 05-Logo-Consistency.md
**Role type:** specialist

### 28. Prompt QC Specialist - Presentations
**Slug:** qc-specialist-prompt-presentations
**What it does:** The INDEPENDENT reviewer of every per-slide image prompt the Prompt Author wrote, sequencing after Prompt-Authoring (Phase P-PROMPT-QC). Grades each prompt file (`working/prompts/slide-NN.txt`) against the written prompt-standard rubric and writes `working/qc/prompt_qc_report.json`. Gate AF-PROMPT-QC blocks the renderer unless the report gates "Phase Prompt-QC", averages >= 8.5, has zero triggered auto-fails, marks `pass: true`, and carries an independent-reviewer provenance block. Auto-fail first: a prompt below the char floor, missing the NEGATIVE BLOCK, or encoding a demographic default cannot average out to a pass. Grades prompt specifications only, not rendered images or copy; never grades prompts it authored.
**Core SOPs to build:**
- 01-Prompt-QC-Gate-Phase-Prompt-QC.md
- 02-Char-Floor-and-Structure-Battery.md
- 03-Independence-and-Provenance-Block.md
- 04-Rework-Loop-and-Escalation.md
**Role type:** qc

### 29. Image QC Specialist - Presentations
**Slug:** qc-specialist-image-presentations
**What it does:** The INDEPENDENT multimodal reviewer of every rendered slide image produced by the Slide Image Creator, sequencing after Render (Phase P-IMAGE-QC). Performs a real vision pass on the pixel content of each render, grades against the image-QC rubric, and writes `working/qc/image_qc_report.json` with a per-slide `vision_api_response` provenance record. Gate AF-IMAGE-QC blocks assembly. Enforces the mandatory vision read (AF-IMAGE-QC-VISION), every-slide scope with no exclusions, and pixel auto-fails: AF-LOCAL-CANVAS (flat cream card), AF-OVERLAY-DELIVERED (double-printed words), under-byte renders below the 51,200-byte kie-bake floor, and AF-CANONICAL-RENDER-BYPASS. Auto-fail first; never grades renders it produced.
**Core SOPs to build:**
- 01-Image-QC-Gate-Phase-Image-QC-Vision-Read.md
- 02-Pixel-Auto-Fail-Battery.md
- 03-Every-Slide-Scope-No-Exclusions.md
- 04-Independence-and-Provenance-Block.md
**Role type:** qc

### 30. Typography QC Specialist - Presentations
**Slug:** qc-specialist-typography-presentations
**What it does:** The INDEPENDENT reviewer of the design system the Typography Architect produced, sequencing after Design (Phase P-TYPO-QC). Grades the design system against the typography rubric and writes `working/qc/typography_qc_report.json`. Gate AF-TYPOGRAPHY-QC blocks prompt authoring unless the report gates "Phase Typography-QC", averages >= 8.5, has zero triggered auto-fails, marks `pass: true`, and carries an independent-reviewer provenance block. Co-owns AF-CREATIVITY (the anti-template auto-fail): rejects any design system where a single layout archetype dominates more than 60% of slides (ARCHETYPE_DOMINANCE_CEILING). Auto-fail first; never grades a design system it built.
**Core SOPs to build:**
- 01-Typography-QC-Gate-Phase-Typo-QC.md
- 02-Anti-Template-Archetype-Dominance-Ceiling.md
- 03-Creative-Typography-Rubric.md
- 04-Independence-and-Provenance-Block.md
**Role type:** qc

### 31. Speech QC Specialist - Presentations
**Slug:** qc-specialist-speech-presentations
**What it does:** The INDEPENDENT reviewer of the presenter speech the Presenters Speech Writer authored, sequencing after Speech (Phase P-SPEECH-QC). Grades the speech manuscript (`working/presenter-speech/presenters_speech.md`) against the speech rubric and writes `working/qc/speech_qc_report.json`. Gate AF-SPEECH-QC is conditional: it defers until the report exists, then enforces that it gates "Phase Speech-QC", averages >= 8.5, has zero triggered auto-fails, marks `pass: true`, and carries an independent-reviewer provenance block. Grades the speech's craft, coverage, pacing, and audience-facing voice; the mechanical word-count floor (AF-SPEECH-SHORT) is a separate pipeline gate. Auto-fail first; never grades a speech it wrote.
**Core SOPs to build:**
- 01-Speech-QC-Gate-Phase-Speech-QC.md
- 02-Craft-Coverage-and-Pacing-Rubric.md
- 03-Independence-and-Provenance-Block.md
- 04-Rework-Loop-and-Escalation.md
**Role type:** qc

---

## Department Coordination Notes

- **Step -2 / Step -1 Come First:** ROLE-22 First-Time-User Onboarding (Step -2) runs on a first-time request, then ROLE-16 Brainstorming Buddy (Step -1) runs before the Director. The Brainstorming Buddy produces the owner-signed brief.json; the Director's SOP 9.1 ingests and validates it and never re-interviews the owner.
- **Content-to-Presentation Architect is an alternate front door:** ROLE-23 handles the "turn THIS source into a presentation" request, producing a build-ready brief for the Director, parallel to the Brainstorming Buddy's discovery brief.
- **Media Library Comes First:** the Media Librarian and GHL Updater runs Step 0 (folder creation) before ANY other phase begins.
- **Capacity Before Dispatch:** the Capacity and Reliability Engineer runs Step 0.5 and produces capacity_plan.json before the Director dispatches Phase 1 agents.
- **Copy Before Prompts Before Generation:** the Slide Copywriter finishes slides_copy.md (Phase 1) before the Slide Image Creator writes a single prompt (Phase 2) before the Slide Submitter submits to Kie.ai (Phase 4). The pipeline is sequential at the phase level.
- **Price Ladder Concurrent with Copy:** the Offer and Price Strategist runs concurrently with the Slide Copywriter during Phase 1. The Copywriter waits for price_ladder.json before writing price-bearing slides.
- **Brand Steward Before Phase 2:** the STYLE BLOCK must exist before the Slide Image Creator writes any prompt.
- **Owner Approval Gate is Hard:** no prompts are written until the owner says YES to the slide copy. This gate cannot be waived without explicit operator authorization on record.
- **Hook Lab Before Copy:** the Hook Strategist runs during Phase B+ (after slide math, before Phase 1 copy). The Copywriter waits for hook_package.json before writing any slides.
- **Typography Architect Before the Slide Image Creator:** ROLE-17 runs as a Phase-0.7/1.5 gate after the STYLE BLOCK (ROLE-02) and arc_allocation.json (ROLE-00) exist and BEFORE the Slide Image Creator writes any prompt. type_layout_system.md is a hard input; without it the deck reverts to one stamped frame.
- **Presenter Coach After Copy, Before Delivery:** ROLE-13 runs after Phase 1A owner approval and before the deck ships. The rehearsal gate must be cleared before the Delivery Concierge delivers.
- **Guide / Speech / Audio After the Presenter Coach, Before Delivery:** ROLE-18 (guide), ROLE-19 (speech), ROLE-20 (audio), and ROLE-21 (Fish Audio expression markup) run AFTER the Presenter Coach and BEFORE the Delivery Concierge, gated on DELIVERABLE_SET and WANT_AUDIO_DEMO. ROLE-19 consumes ROLE-13's talk track; ROLE-20/ROLE-21 consume ROLE-19's QC-passed speech. All route every deliverable through the Delivery Concierge for verified last-mile (never self-report). TARGET_WPM=140 is the recorded speech constant.
- **Delivery Concierge Replaces Direct Delivery:** the Media Librarian hands off to the Delivery Concierge after PPTX assembly (Phase 6). The Delivery Concierge owns all destinations, verification, and notification.
- **Healer is Live:** the Healer receives second-consecutive-stall handoffs from ROLE-03, loop-4 escalations from ROLE-05, and Phase-4 API failCode events from ROLE-06. File a Bug Ticket to the Bugs Department before handing off to the Healer.
