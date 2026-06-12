# Suggested Roles -- presentations-dept
**Version:** 1.3 | 2026-06-12
**Status:** v12 Deck Discovery Strategist addition (17 roles; ROLE-17 front-door discovery now live)

## Department Purpose
End-to-end branded webinar and slide deck production: copy writing, price ladder choreography, image prompt authoring, brand consistency, QC at every phase, image generation submission, media library management, PPTX assembly, adversarial review, hook development, live-presentation coaching, verified delivery, and department self-healing. Coordinates with Marketing (deck brief), CRM (GHL media library), Research (proof gaps), and the client's OpenClaw agent (discovery interview, approval gates, final delivery).

## v12.0.0 Role Roster (17 roles)
- Deck Discovery Strategist (ROLE-17, NEW -- v12)
- Director (ROLE-01)
- Brand Steward (ROLE-02)
- Capacity and Reliability Engineer (ROLE-03, NEW -- v11.19.0)
- Deep Research Specialist -- Presentations (ROLE-04)
- Devil's Advocate -- Presentations (ROLE-05)
- Media Librarian and GHL Updater (ROLE-06)
- Offer and Price Strategist (ROLE-07, NEW -- v11.19.0)
- PPTX Assembly Specialist (ROLE-08)
- QC Specialist -- Presentations (ROLE-09)
- Slide Copywriter (ROLE-10)
- Slide Image Creator (ROLE-11)
- Slide Submitter (ROLE-12)
- Delivery Concierge (ROLE-13, NEW -- v11.23.0)
- Presenter Coach (ROLE-14, NEW -- v11.23.0)
- Hook Strategist (ROLE-15, NEW -- v11.23.0)
- Healer -- Presentations (ROLE-16, NEW -- v11.23.0+healer)

---

## New Roles Added in v12.0.0

### 17. Deck Discovery Strategist (NEW -- v12)
**Slug:** deck-discovery-strategist
**What it does:** The department front door. When the owner says "how do I get started / make a deck?", this role brainstorms with them BEFORE the build: offers a SIMPLE interview (<=7 questions) or an EXTENSIVE interview (10 to 20 questions, back-and-forth), confirms what it learned with the owner (read-back + explicit sign-off), writes the binding working/copy/deck_brief.json, and kicks off the build by handing the locked brief to the Director. Replaces the Director's old discovery interview; the Director now ingests and validates the brief instead of re-interviewing.
**Core SOPs:** 9.0 Open + Depth Choice | 9.1 Simple Interview (<=7 Qs) | 9.2 Extensive Interview (10-20 Qs) | 9.3 Confirm-and-Lock | 9.4 Kickoff/Handoff
**Role type:** leadership

---

## New Roles Added in v11.23.0

### 12. Delivery Concierge (NEW -- v11.23.0)
**Slug:** delivery-concierge
**What it does:** Owns Phase 6+ multi-destination deck delivery. Resolves all delivery destinations from the Director's intake, uploads to each (GHL, Google Drive, local Mac Downloads), sends verified delivery notifications via openclaw message send, runs ground-truth verification (file hash + size), and writes a delivery_complete ledger entry.
**Core SOPs:** 9.1 Destination Resolution | 9.2 Multi-Destination Upload | 9.3 Notification | 9.4 Ground-Truth Verification
**Role type:** specialist
**Absorbed:** ROLE-06 SOP 9.6 (Final Deck Delivery)

### 13. Presenter Coach (NEW -- v11.23.0)
**Slug:** presenter-coach
**What it does:** Owns the live-presentation preparation layer. Writes a timed talk track (slide-by-slide narration against DURATION_MIN), preps Q and A objection answers for the 10 hardest questions, builds a one-page rehearsal run sheet, and runs a mandatory rehearsal gate (deck is not webinar-ready until owner completes at least one aloud run). Hands off to ROLE-13 Delivery Concierge.
**Core SOPs:** 9.1 Talk Track | 9.2 Q and A Objection Prep | 9.3 Rehearsal Pack | 9.4 Rehearsal Gate
**Role type:** specialist

### 14. Hook Strategist (NEW -- v11.23.0)
**Slug:** hook-strategist
**What it does:** Owns the Hook Lab end-to-end. Generates 10 hook candidates (>=1 per formula across 7 formulas: F1 Purple Rain / F2 Contrarian / F3 Specificity Bomb / F4 Identity Claim / F5 Before-After / F6 Two-Truths / F7 Direct Prediction), scores each on 5 dimensions (Memorable/Provocative/Punchy/Specific/Singable), field-tests top 3 (say-it-aloud / 3-second recall / T-shirt / cookout tests), presents to owner for selection. Builds variant ladder (7-10 variants), placement map, and runs post-deck hook audit. Outputs hook_package.json consumed by Copywriter.
**Core SOPs:** 9.1 Hook Generation and Scoring | 9.2 Variant Ladder, Placement Map, Post-Deck Hook Audit
**Role type:** specialist

---

## Roles

### 0. Director of Presentations
**Slug:** director-of-presentations
**What it does:** Orchestrates the entire webinar deck pipeline from end to end. Runs the adaptive discovery interview, owns the PRD gate, dispatches all specialists, enforces every QC gate, manages the owner approval gate (Phase 1A), and delivers the final deck. Nothing ships without the Director's checkpoint.
**Core SOPs:** 9.1 Adaptive Discovery Interview | 9.2 Echo Protocol and Mission PRD Gate | 9.3 Mode Selection and Enhancement Gap Analysis | 9.4 Slide-Count Math and Arc Allocation | 9.5 Owner Approval Gate and Presenter-Notes Export | 9.6 Parallelization and Sequencing Strategy
**Role type:** leadership

### 1. Slide Copywriter
**Slug:** slide-copywriter
**What it does:** Writes every word on every slide (Phase 1): headlines (max 9 words), subheads (max 18 words), body bullets (max 3), and presenter notes. Embeds the hook >= 7 times. Enforces no-em-dash and no-fabrication rules. Produces slides_copy.md for the Phase 1Q QC gate and the owner approval gate.
**Core SOPs:** 9.1 Write the Slides (Words First, One Big Idea) | 9.2 Hook Authoring and Refrain Placement | 9.3 Proof Integrity and No-Fabrication | 9.4 Mode B Word-Preserving Augmentation
**Role type:** specialist

### 2. Offer and Price Strategist (NEW)
**Slug:** offer-price-strategist
**What it does:** Owns the price drop ladder choreography and offer stack construction. Sets the SPREAD LADDER at ~32/47/68/87/97% marks. Ensures ANCHOR_PRICE >= 3x FINAL_PRICE. Builds offer_stack.json and price_ladder.json. Runs the cross-slide numeric consistency gate (blocking QC gate) after copy is written.
**Core SOPs:** 9.1 Price-Drop Ladder Choreography | 9.2 Offer Stack and Value-Anchor Construction | 9.3 Cross-Slide Numeric Consistency and Price Validation Gate
**Role type:** specialist

### 3. Slide Image Creator
**Slug:** slide-image-creator
**What it does:** Writes one 15-element image prompt per slide (Phase 2). Targets 5,000-7,500 characters per prompt (range: 1,500-15,000). Applies the STYLE BLOCK from the Brand Steward. Front-loads critical content. Handles price-drop strikethroughs and hook text overlays. Produces working/prompts/slide-NN-prompt.txt files.
**Core SOPs:** 9.1 Per-Slide Prompt Authoring (15-Element Spec) | 9.2 Thirds-Grid and Composition | 9.3 White-Base and Brand-Palette | 9.4 Three-People-Engines and Overlays and Logo | 9.5 Drawn-Strikethrough and Struck-Text Handling
**Role type:** specialist

### 4. Brand Steward
**Slug:** brand-steward
**What it does:** Creates and owns the STYLE BLOCK (800-1,500 characters): 3 hex codes with roles, typography system, logo placement rule, and representation ratio. Dispatched early in every run -- before Phase 2. Runs the deck-level representation distribution audit after prompts are written.
**Core SOPs:** 9.1 Shared STYLE BLOCK Authorship | 9.2 Cross-Slide Consistency and Representation-Ratio Audit
**Role type:** specialist

### 5. QC Specialist -- Presentations
**Slug:** qc-specialist-presentations
**What it does:** Runs all four QC gates: Phase 1Q (copy, 14 criteria, double-weight on 1/2/7/11/12), Phase 3 (prompts, 15 criteria dual-scored, double-weight on 2/3/4/13), Phase 5 (images, 11 criteria, double-weight on 3/5/6/7), and Phase 6 (final deck). Threshold: >= 8.5. Loops back automatically for up to 3 attempts; escalates on attempt 4. Classifies image failures as render-noise, prompt-defect, or text-fail-x1/x2.
**Core SOPs:** 9.1 Copy QC Gate (Phase 1Q) | 9.2 Prompt QC Gate (Phase 3, Dual-Scored) | 9.3 Image QC Gate (Phase 5) and Fail Classification | 9.4 Revision-Loop Control and Escalation | 9.5 Final Deck QC (Rendered Pages)
**Role type:** qc

### 6. Slide Submitter
**Slug:** slide-submitter
**What it does:** Submits all prompts to Kie.ai GPT Image 2 (Phase 4). Uses model gpt-image-2-image-to-image (with refs) or gpt-image-2-text-to-image (without refs) per the MODEL MANIFEST. Enforces 2 RPS rate cap (20 slides/wave + 15s sleep). Polls for completions (5-min initial wait, 60s intervals, 100-poll hard cap). Downloads to working/renders/. Runs the generation budget discipline gate (warn at 1.5x, stop at 2x SLIDE_COUNT x $0.03).
**Core SOPs:** 9.1 Model Manifest and Variant Selection | 9.2 KIE Submit and 2-RPS Rate Cap | 9.3 Loop-Guarded Poll and Parallel Download | 9.4 Truncation and Generation-Budget Discipline
**Role type:** specialist

### 7. Media Librarian and GHL Updater
**Slug:** media-librarian-ghl-updater
**What it does:** Creates the local + GHL media library folders at Step 0 (first action, always). Intakes passed images from Phase 5 into working/media-library/ (local naming: slide-NN.png). Uploads each passed image to GHL immediately (GHL naming: Slide NN v<N>). Runs the final delivery verification: local count == GHL count == slide_count_final before PPTX assembly begins.
**Core SOPs:** 9.1 Step-0 Landing Zone Creation | 9.2 Passed-Image Intake | 9.3 GHL-Drive Upload | 9.4 Delivery and Ground-Truth Verification
**Role type:** specialist

### 8. PPTX Assembly Specialist
**Slug:** pptx-assembly-specialist
**What it does:** Assembles the final PowerPoint from QC-passed images using python-pptx (13.333 x 7.5 inch slides, full-bleed). Embeds speaker notes from presenter_notes.json. Applies native text overlays from pptx_text_overlays.json if present. Renders to PDF via soffice --headless --convert-to pdf, then to PNG pages via pdftoppm -png -r 100 for Phase 6 QC.
**Core SOPs:** 9.1 PPTX Build with Embedded Speaker Notes | 9.2 Render-to-PDF for Final QC | 9.3 Native-Text Overlay Fallback
**Role type:** specialist

### 9. Capacity and Reliability Engineer (NEW)
**Slug:** capacity-reliability-engineer
**What it does:** Owns Step 0.5 (system capacity probe) and Phase 7 (resilience watchdog cron). Probes the client's box (free -h, nproc, uptime, df -h), verifies Ollama Cloud reachability, checks Kie.ai credit balance vs. budget ceiling, checks all 4 env stores for required keys, and writes capacity_plan.json with fleet sizing recommendations and a go/no-go decision. Installs a 15-minute watchdog cron after Phase 4 begins; removes it after Phase 6 completes.
**Core SOPs:** 9.1 System Capacity Probe and Fleet Sizing | 9.2 Resilience Watchdog Cron and Checkpoint Recovery | 9.3 Model Routing and Env-Store Verification
**Role type:** specialist

### 10. Deep Research Specialist -- Presentations
**Slug:** deep-research-specialist-presentations
**What it does:** On-demand research specialist. Researches niche deck structures (Category A), proven price anchors (Category B), and proof statistics (Category C) for the client's industry. Produces a Research Brief with all findings cited (source URL + publication date + confidence level HIGH/MEDIUM/LOW). Never fabricates. Feeds the Slide Copywriter (proof gaps) and Offer Price Strategist (price anchor benchmarks).
**Core SOPs:** 9.1 Niche Deck and Offer Benchmark Research
**Role type:** deep-research

### 11. Devil's Advocate -- Presentations
**Slug:** devils-advocate-presentations
**What it does:** Adversarial on-call reviewer. Reviews any deck marked "high-stakes" against the 18-point Pitch Doctrine from master SOP Section 4.3. Produces a Kill List: every doctrine violation with the specific slide number, the specific violation text, the severity (HIGH/MEDIUM/LOW), and the specific fix required. Focuses on: hook count, anchor ratio, dark-slide creep, overclaimed promises, fabricated proof, price choreography, and CTA clarity.
**Core SOPs:** 9.1 Adversarial Doctrine Review and Kill-List
**Role type:** on-call

### 15. Healer -- Presentations (NEW -- v11.23.0+healer)
**Slug:** healer-presentations
**What it does:** Department immune system. Receives second-consecutive-stall handoffs from ROLE-03 Capacity and Reliability Engineer, loop-4 escalations from ROLE-09 QC Specialist, and Phase-4 API failCode events from ROLE-12 Slide Submitter. Diagnoses root cause using five-whys on evidence (dispatches ROLE-04 Deep Research Specialist for provider docs). Fixes the run (Tier 1: mechanical hot-patch, resume from last good checkpoint). Patches the SOP that allowed the failure so it never recurs (Tier 2: SOP surgery, mirror regeneration, regression entry). Proposes model manifest changes and new specialists to the operator and holds until approved (Tier 3). Reports every heal to the Director, CEO orchestrator, and operator before closing the incident. Runs monthly model currency census on GPT Image 2 / Minimax m3 / DeepSeek models in this department.
**Core SOPs:** 9.1 Intake+Triage | 9.2 Root-Cause Diagnosis | 9.3 Fix Forward | 9.4 SOP Surgery | 9.5 Gap Detection | 9.6 Model Census | 9.7 Healing Report | 9.8 Regression Watch | 9.9 Core-File Surgery | 9.10 Settings Repair | 9.11 Teacher-Self | 9.12 Embedding Refresh
**Role type:** healer
**Receives from:** ROLE-03 (second consecutive stall or failed self-heal), ROLE-09 (loop-4 escalation), ROLE-12 (Phase-4 failCode events), Director (gap flags), Chief Healer (global patch directives)

---

## Department Coordination Notes

- **Discovery Comes First:** ROLE-17 Deck Discovery Strategist runs before the Director. It produces the owner-signed deck_brief.json; the Director's SOP 9.1 ingests and validates it and never re-interviews the owner.
- **Media Library Comes First:** The Media Librarian / GHL Updater runs Step 0 (folder creation) before ANY other phase begins.
- **Capacity Before Dispatch:** The Capacity & Reliability Engineer runs Step 0.5 and produces capacity_plan.json before the Director dispatches Phase 1 agents.
- **Copy Before Prompts Before Generation:** The Slide Copywriter finishes slides_copy.md (Phase 1) before the Slide Image Creator writes a single prompt (Phase 2) before the Slide Submitter submits to Kie.ai (Phase 4). The pipeline is sequential at the phase level.
- **Price Ladder Concurrent with Copy:** The Offer Price Strategist runs concurrently with the Slide Copywriter during Phase 1. The Copywriter waits for price_ladder.json before writing price-bearing slides.
- **Brand Steward Before Phase 2:** The STYLE BLOCK must exist before the Slide Image Creator writes any prompt.
- **Owner Approval Gate is Hard:** No prompts are written until the owner says YES to the slide copy. This gate cannot be waived without explicit operator authorization on record.
- **Hook Lab Before Copy:** The Hook Strategist (ROLE-15) runs during Phase B+ (after slide math, before Phase 1 copy). The Copywriter waits for hook_package.json before writing any slides.
- **Presenter Coach After Copy, Before Delivery:** ROLE-14 runs after Phase 1A owner approval and before the deck ships. The rehearsal gate must be cleared before ROLE-13 delivers.
- **Delivery Concierge Replaces Direct Delivery:** ROLE-06 Media Librarian hands off to ROLE-13 Delivery Concierge after PPTX assembly (Phase 6). ROLE-13 owns all destinations, verification, and notification.
- **ROLE-16 Healer is Live:** healer-presentations.md authored and merged (change order v1 + healer addition). The Healer receives: second consecutive stall handoffs from ROLE-03, loop-4 escalations from ROLE-09, Phase-4 API failCode events from ROLE-12. File a Bug Ticket to the Bugs Department before handing off to the Healer (Bugs Department pending commission).
