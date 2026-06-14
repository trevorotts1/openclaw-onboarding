# 00 -- START HERE -- Presentations Department
**Version:** 1.6 | 2026-06-14
**Role library path:** 23-ai-workforce-blueprint/templates/role-library/presentations/
**SOP mirror path:** 23-ai-workforce-blueprint/templates/role-library/presentations/sops/

---

## What This Department Does

End-to-end branded webinar and slide deck production: copy writing, price ladder choreography, image prompt authoring, brand consistency, QC at every phase, image generation submission, media library management, PPTX assembly, adversarial review, hook development, live-presentation coaching, and verified final delivery.

### The Ten Required Presentation Components (master SOP Section 4.4)

Every deck must carry, and the QC Specialist gates, the operator's ten named required components: (1) the Promise (pitch the promise, not the product), (2) the Hook (written like a song, sung ~10x, minimum 7), (3) Case Studies / "who says so other than you" (third-party proof woven between the drops; zero-proof deck FAILS), (4) the Wall of Wins / wall of results, (5) One Big Idea Per Slide (multi-idea slide AUTO-FAILS), (6) the Guarantee, (7) the Scarcity Factor (last-calls / doors-closing, real only), (8) the Story Arc (short-term fix vs long-term identity; self-recognition), (9) the Gradual Price Ladder (value-plant anchor -> spread earned-reason drops -> add value every drop -> final late), and (10) "a checklist for an AI is a list of promises" (the QC / checklist philosophy). Producing roles: Director (1, 10), Hook Strategist (2), Deep Research (3, 4), Copywriter (all copy beats), Offer Price Strategist (6, 7, 9). Gating role: QC Specialist (copy QC criteria c1, c11, c18-c22 + AF-C6 + final-deck structural-completeness).

---

## Role Roster (17 roles; all live)

**Doctrine count:** all 17 roles are live to spec (ROLE-01 through ROLE-17). ROLE-16 The Healer is **COMPLETE** and built to full spec: the companion document THE_HEALER_AND_BUGS_DEPARTMENT.md (plus the T3-BUGBOARD-HEALER-SPEC.md build contract) has been supplied, and the ZHC Bugs Department it files into is commissioned and present in this repo at role-library/bugs/ (Bug Intake Clerk, Triage and Dedup Analyst, Bug Librarian, the universal bug-ticket-schema.json, and the B-9.1 to B-9.5 SOPs), with the Healer Department at role-library/healer/ (Chief Healer + the per-department Healer template). ROLE-16 carries the three authority tiers, all 12 Healer SOPs (9.1 to 9.12), and its triggers are wired to a live Bugs Department.


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

**Mirror rule:** role file is authoritative. If a sops/ file diverges from the role file's Section 9, the role file wins and the mirror must be regenerated immediately. Never edit the sops/ file directly.

---

## Design Intelligence Unit (DIU) Boundary

The Graphics department's Design Intelligence Unit (DIU) -- Style Analyst, Deck Systems Specialist, Generation Operator, Photo Shoot Director, Fidelity Tester -- operates entirely within the Graphics department and does NOT touch the presentations pipeline. This department's webinar and deck production workflow (ROLE-01 through ROLE-17, the full phase sequence above, and the Kie.ai submission path via ROLE-12 Slide Submitter) is the authoritative source for webinar deck delivery. The DIU's Deck Systems Specialist analyzes and generates deck IMAGERY STYLE SYSTEMS only; deck narrative writing, price ladder choreography, PPTX assembly, and final submission to Kie.ai for webinar decks remain exclusively with this department. Any cross-department request that would route deck narrative or assembly work to the Graphics DIU is a misroute -- return it here.

**Permitted cross-department request (presentations → Graphics DIU):** This department MAY request a style card analysis from the Graphics DIU when a client wants a NEW webinar deck built to match an existing deck's visual aesthetic. In that case, ROLE-02 Brand Steward submits the reference deck to the Graphics DIU Style Analyst (via Chief Design Officer) for a PPT-tier style card; the resulting style ID is then passed back to ROLE-11 Slide Image Creator as the style reference for Phase 2 prompt authoring. The narrative, copy, and assembly pipeline remain entirely with this department; only the imagery style analysis crosses the boundary. This is the ONLY permitted cross-department call; all other DIU capabilities (photo shoot, generation operator, fidelity testing) are out of scope for this department.

---

## Master SOP Authority

All roles defer to: `universal-sops/CLIENT-WEBINAR-DECK-SOP.md`

---

## Bug Filing

Every error, stall, or failCode in this department is a filing event. File using the Bug Ticket schema (see ZHC Bugs Department) before continuing stabilization. ROLE-16 Healer receives the routed ticket.

**Mandatory:** An unfiled bug is a future repeat. File first, then stabilize.
