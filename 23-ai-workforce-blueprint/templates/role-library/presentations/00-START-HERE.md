# 00 -- START HERE -- Presentations Department
**Version:** 1.3 | 2026-06-12
**Role library path:** 23-ai-workforce-blueprint/templates/role-library/presentations/
**SOP mirror path:** 23-ai-workforce-blueprint/templates/role-library/presentations/sops/

---

## What This Department Does

End-to-end branded webinar and slide deck production: copy writing, price ladder choreography, image prompt authoring, brand consistency, QC at every phase, image generation submission, media library management, PPTX assembly, adversarial review, hook development, live-presentation coaching, and verified final delivery.

---

## Role Roster (17 roles)

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

---

## Pipeline Sequence (phase order)

-1. **Step -1** -- ROLE-17 Brainstorming Buddy brainstorms with the owner (SIMPLE or EXTENSIVE interview), confirms, and locks working/brainstorm/presentations/<slug>/brief.json; then hands the locked brief to the Director.
1. **Step 0** -- ROLE-06 Media Librarian creates the landing zone and acquires client assets (LOGO_URL, FOUNDER_PORTRAIT_URL).
2. **Step 0.5** -- ROLE-03 Capacity and Reliability Engineer probes the box and writes capacity_plan.json.
3. **Phase B+** -- ROLE-15 Hook Strategist runs the Hook Lab; outputs hook_package.json.
4. **Phase 1** -- ROLE-10 Slide Copywriter (concurrent: ROLE-07 Offer and Price Strategist). Output: slides_copy.md + price_ladder.json.
5. **Phase 1Q** -- ROLE-09 QC Specialist runs copy QC gate (score >= 8.5).
6. **Phase 1A** -- Owner approval gate (Director-managed). No prompts until YES.
7. **Phase 2** -- ROLE-11 Slide Image Creator writes prompts (requires STYLE BLOCK from ROLE-02).
8. **Phase 3** -- ROLE-09 QC Specialist runs prompt QC gate (dual-scored).
9. **Phase 4** -- ROLE-12 Slide Submitter submits to Kie.ai (2 RPS cap, smoke test first).
10. **Phase 4 concurrent** -- ROLE-03 watchdog cron runs.
11. **Phase 5** -- ROLE-09 QC Specialist runs image QC gate.
12. **Phase 5 passed** -- ROLE-06 Media Librarian intakes passed images to GHL.
13. **Phase 6** -- ROLE-08 PPTX Assembly Specialist assembles the deck.
14. **Phase 6 QC** -- ROLE-09 QC Specialist runs final deck QC (score >= 8.5).
15. **Post-Phase 6** -- ROLE-14 Presenter Coach writes talk track and runs rehearsal gate.
16. **Delivery** -- ROLE-13 Delivery Concierge delivers to all destinations and verifies.

On-call throughout: ROLE-05 Devil's Advocate (high-stakes reviews), ROLE-04 Deep Research Specialist.

**ROLE-16 Healer** receives: second consecutive stall handoffs from ROLE-03, loop-4 escalations from ROLE-09, API failCode events from ROLE-12, and any department error flag.

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
| sops/offer-price-strategist-sops.md | offer-price-strategist.md | 9.1 Ladder, 9.2 Offer Stack, 9.3 Price Gate, 9.4 Straight Mode, 9.5 VIP, 9.6 Priceless Pitch |
| sops/pptx-assembly-specialist-sops.md | pptx-assembly-specialist.md | 9.1 PPTX Build, 9.2 PDF Render, 9.3 Text Overlay |
| sops/presenter-coach-sops.md | presenter-coach.md | 9.1 Talk Track, 9.2 Q&A Prep, 9.3 Rehearsal Pack, 9.4 Rehearsal Gate |
| sops/qc-specialist-presentations-sops.md | qc-specialist-presentations.md | 9.1 Copy QC, 9.2 Prompt QC, 9.3 Image QC, 9.4 Loop Control, 9.5 Final Deck QC |
| sops/slide-copywriter-sops.md | slide-copywriter.md | 9.1 Write Slides, 9.2 Hook Placement, 9.3 Proof Integrity, 9.4 Mode B, 9.7 Doctrine |
| sops/slide-image-creator-sops.md | slide-image-creator.md | 9.1 15-Element Prompt, 9.2 Archetypes+Composition, 9.3 White-Base+Palette, 9.4 Engines+Overlays, 9.5 Strikethrough |
| sops/slide-submitter-sops.md | slide-submitter.md | 9.1 Model Manifest, 9.2 KIE Submit, 9.3 Poll+Download, 9.3a API Contract, 9.4 Budget Discipline, 9.5 Smoke Test |
| sops/healer-presentations-sops.md | healer-presentations.md | 9.1 Intake+Triage, 9.2 Diagnosis, 9.3 Fix Forward, 9.4 SOP Surgery, 9.5 Gap Detection, 9.6 Model Census, 9.7 Healing Report, 9.8 Regression Watch, 9.9 Core-File Surgery, 9.10 Settings Repair, 9.11 Teacher-Self, 9.12 Embedding Refresh |

**Mirror rule:** role file is authoritative. If a sops/ file diverges from the role file's Section 9, the role file wins and the mirror must be regenerated immediately. Never edit the sops/ file directly.

---

## Master SOP Authority

All roles defer to: `universal-sops/CLIENT-WEBINAR-DECK-SOP.md`

---

## Bug Filing

Every error, stall, or failCode in this department is a filing event. File using the Bug Ticket schema (see ZHC Bugs Department) before continuing stabilization. ROLE-16 Healer receives the routed ticket.

**Mandatory:** An unfiled bug is a future repeat. File first, then stabilize.
