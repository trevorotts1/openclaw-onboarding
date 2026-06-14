# Cluster Index - Image-Gen Mechanics + Design-Library (skill 45) Integration

**Cluster scope:** (1) Kie.ai call mechanics per mode; (2) Design-Intelligence-Library integration + the 5 gaps; (3) signature-style recall.
**Repo grounded against:** `openclaw-onboarding` @ HEAD 89676f2, repo v12.2.0 (both copies identical; CLAWD copy matches).
**Principle:** EXTEND the existing Presentations dept + skill 45. None of these SOPs re-authors the analysis engine, the boundary contract, the alias system, or the model manifest. They make existing capability enforceable and wire it in.

---

## Files in this cluster

| File | Covers | Concerns / gaps closed |
|---|---|---|
| `SOP-IMG-01-KIE-CALL-MECHANICS.md` | The three call modes (T2I / I2I / image-to-text-analysis), exact curl+JSON+lifecycle per mode, logo-on-every-slide = I2I, and that there is NO Kie image-to-text endpoint. | Concern 20. The logo-mutation defect (Dimension F). |
| `SOP-IMG-02-DIU-INTEGRATION-AND-SEEDING.md` | How Presentations uses skill 45 (PPTX analysis -> 3-8 named families -> per-family scaffolding prompts -> STYLE BLOCK); the seeding step (run the gold-standard v2 reference deck + client decks); the auto-handoff trigger/contract. | Concern 21. GAP a (empty library), GAP d (no auto-handoff). |
| `SOP-IMG-03-STYLE-OR-CREATIVE-DEVELOP-CONVERSATION.md` | The verbatim "do you have a style, or should I creatively develop one?" three-way branch + the creative-develop probe flow; the canonical NAMED-STYLES.md seed. | Concern 22. GAP b ("creatively develop one" path), GAP e (NAMED-STYLES seed). |
| `SOP-IMG-04-SIGNATURE-STYLE-RECALL-AND-DIU-LOGO-I2I.md` | "Use Style 1" recall resolution (alias -> card@version -> STYLE BLOCK, no guessing); DIU logo-as-image-to-image mechanic. | Concern 22 (recall). GAP c (DIU logo-I2I unspecified). |

All five investigation gaps (a-e) are covered: a -> IMG-02; b -> IMG-03; c -> IMG-04; d -> IMG-02; e -> IMG-03.

---

## Where these wire into EXISTING files (edits the build agents make - extend, do not duplicate)

These SOPs are the source; the build step folds short pointers into the existing role/SOP files so nothing is orphaned.

1. **`presentations/slide-image-creator.md` + its `sops/` mirror** - add a short reference under SOP 9.1 step 1 and SOP 9.4: "Mode selection per SOP-IMG-01: if a logo/portrait/style-frame is in play, the submission MUST be I2I with named references; never T2I a logo slide." Add the §7 enforcement checks (esp. check 9, rendered-logo-matches-locked-asset) to the role's Quality Gates. Do NOT restate the call lifecycle (it already lives in master SOP §9 and MODEL-SPECS §5).
2. **`presentations/slide-submitter.md` + mirror** - add SOP-IMG-01 §7 checks 1-8 as a submit-time preflight (mode matches assets; refs named; refs reachable; resultUrls parse). The submitter is where the mode is physically chosen.
3. **`presentations/brand-steward.md` + mirror (SOP 9.1)** - add the SOP-IMG-02 §3 trigger: when intake has a style reference / STYLE_ID / ANALYZE_REQUEST, fire Crossing A via SOP-DIU-612 and fold the Foundation Prompt Block into the STYLE BLOCK before delivery; record `style_card_id@version` in brand_registry.json. Add the SOP-IMG-04 §2 recall path for `STYLE_SOURCE = saved_style`.
4. **`presentations/brainstorming-buddy-presentations.md` + mirror** - add the SOP-IMG-03 §2 verbatim three-way style branch as the first style question, setting `STYLE_SOURCE`; add the §3 creative-develop micro-interview (reuse the existing mood/imagery/avoid stems - sequence them, don't re-bank them).
5. **`graphics/sops/SOP-DIU-607.md`** - no content change; ship `templates/NAMED-STYLES.md` (SOP-IMG-03 §4 seed) so step A.5's referenced template actually exists. (Closes GAP e at the source.)
6. **`graphics/style-analyst.md` + `deck-systems-specialist.md`** - add the SOP-IMG-02 §4 bootstrap-seed task (run the gold-standard v2 reference deck through PPT-ANALYSIS-SOP at onboarding, register PPT-001 as production) and the SOP-IMG-04 §3 DIU logo-as-I2I mechanic (logo passed as a reference, "place, do not redraw," opposite directive from a style frame).
7. **`45-design-intelligence-library/library/INDEX.md`** - after the bootstrap seed runs, the PowerPoint section gains the `PPT-001_gold-standard` rows (production). The empty-INDEX auto-fail (IMG-02 check 1/6) verifies this on every box.
8. **`qc-specialist-presentations.md` + mirror** - promote the SOP-IMG-01 §7 checks (esp. logo mode + logo identity) into the image-QC auto-fail table, so a T2I-logo slide or a mutated logo is caught at the gate, not after delivery.

---

## Cross-cluster dependencies (not owned here - flagged for the other clusters)

- **Logo identity / "one locked logo asset"** is enforced at WRITE time here (IMG-01 §7 checks 1-3, IMG-04 §3); the deck-wide "lock one canonical logo, forbid monogram/mountain/tagline variants" rule belongs to the **brand-steward / design-system cluster**. Both are needed; IMG checks are the I2I-mechanics half.
- **Audience-facing battery** (no build doctrine on slides) is owned by the **slide-craft cluster**; these SOPs only reiterate that all call-mechanics and library content are DATA, never slide copy.
- **The model manifest** (which model is pinned) stays owned by master SOP §9.0; SOP-IMG-01 chooses the MODE within the pinned family, never the model.

---

## What was verified before writing (ground truth)

- Skill 45 is real and complete: PPT-ANALYSIS-SOP v1.1 (rasterize -> 3-8 families -> Deck Style System + SHORT/MEDIUM/LONG templates); INDEX.md v2.0 is empty on every section; SOP-DIU-607 fully specifies the alias/lookbook system; SOP-DIU-611 is the boundary contract; SOP-DIU-612 is the cross-dept request block (CDO sole intake).
- MODEL-SPECS v1.2: 7 endpoints, none of them image-to-text; GPT-Image-2 I2I takes `input_urls` (<=16, 30MB); the style-reference-only directive is mandatory for style refs.
- CLIENT-WEBINAR-DECK-SOP §9: GPT-Image-2-only manifest; I2I default with logo URL in `input_urls`; the full createTask/recordInfo lifecycle + the `resultUrls` (not `.url`) parse.
- The forensic reference deck confirmed logo mutation came from per-slide T2I instead of I2I, and that none of the named defects was an auto-fail at the gate. These SOPs make them auto-fails.
