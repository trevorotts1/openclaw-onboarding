# SOP-SLIDE-03: HOOK DOCTRINE (THE SACRED REFRAIN)

**Cluster:** Slide-Craft Rules
**Master authority:** universal-sops/CLIENT-WEBINAR-DECK-SOP.md (Section 4.3 rule 1, Section 5.1 the HOOK, criterion 11)
**Owning role at write time:** Hook Strategist (anchors + hook-absent list), Slide Copywriter (places only the approved anchors)
**Owning role at render time:** Slide Image Creator (renders the hook ONLY on its dedicated typography slides, never as a footer band)
**Enforced at the gate by:** QC Specialist - Presentations (auto-fail AF-HOOK, below)
**Status:** Reference SOP, RECONCILED with the live gate. The floor-based hook rule this SOP corrects has ALREADY BEEN CORRECTED in the live repo (the FIX-1 banded-cadence overhaul). The hook ceiling and anti-footer protection is wired as auto-fail AF-C2 (the banded hook cadence: fails BOTH ways -- over-stamping on more than ~5 slides, on 2+ consecutive slides, or as a footer on every slide; AND under the 3-4 dedicated beats) plus AF-P12 (prompt-side hook-overlay over-stamping; the literal phrase "present on every slide" is itself an AF-P12 auto-fail). Hook mutation/misspelling on render is caught by AF-P3 (headline not verbatim), AF-I1 (garbled glyph), and AF-F9 (OCR diff). The draft codes AF-HOOK-1..7 map onto AF-C2 / AF-P12 / AF-P3 / AF-I1 / AF-F9. Section 6 below describes the original floor-to-ceiling reconciliation; in the live repo that reconciliation is ALREADY APPLIED, so treat Section 6 as the historical record of why AF-C2 is banded, not as pending wiring. Do NOT add a parallel AF-HOOK namespace.

---

## 1. PURPOSE

The hook is a song's chorus, not its wallpaper. It is sung at a few natural beats so the audience leaves humming it. The forensic reference deck did the exact opposite: the example signature hook was stamped as a footer on roughly 40 of 45 slides, printed twice on at least eight, extended/mutated on one ("...and the results are significantly different."), and rendered a misspelled hook ("hclarity") on slide 23. There was no clean dedicated hook slide at all.

**This is the HOOK INTELLIGENCE engine (SOP-ENGINE-00 Engine 7). "Hook Doctrine / The Sacred Refrain" and "Hook Intelligence" are the same doctrine** -- the engine framework's name for this already-built mechanic: ONE canonical hook, built once, reused verbatim at 3 to 4 natural beats, never reworded, never a footer band. No new behavior or gate is added by the alias; the enforcement remains the AF-HOOK / AF-C2 / AF-P12 battery.

The root cause is in the system's own rules: the master SOP mandates the hook "AT LEAST 7 TIMES... roughly one per 8 to 10 slides", the copy criterion 11 auto-fails when the count is BELOW 7, and the image creator's render spec prescribed a bottom-band footer as the hook rendering. The system did exactly what it was told: it floored the count and stamped footers. This SOP inverts the rule: the hook lives on a small, fixed CEILING of dedicated slides, footer-stamping is banned, and the refrain is sacred and exact.

---

## 2. THE HARD RULE

1. **Dedicated slides only, with a hard CEILING.** The verbatim hook appears on **3 to 4 DEDICATED, pure-typography slides** at natural beats, and **NOWHERE ELSE**. A hook-carrying slide is a slide whose one big idea IS the hook (large hook line over a low-opacity image or clean type), with no other competing copy. Anything beyond 4 hook-carrying slides is a defect. Zero hook-carrying slides is also a defect (the hook must exist and be sung).
2. **The hook is NEVER a footer.** No footer band, no bottom-strip overlay, no recurring stamp at the base of content slides. The hook does not appear as body copy on a teaching slide, a proof slide, an offer slide, or any non-dedicated slide.
3. **The natural beats** (the 3 to 4 anchors, from the transcript): (a) when the hook is born, right after the core contrast that produces it; (b) after the story that proves it; (c) at the result/payoff beat; (d) late, as the through-line into the close. The Hook Strategist names these anchors and produces an explicit HOOK-ABSENT list (every other slide).
4. **The hook is a sacred, exact refrain.** It is rendered VERBATIM every time. It is never reworded, never extended, never abbreviated mid-deck, never duplicated on the same slide, never misspelled. One canonical string, locked at copy stage, rendered identically on each dedicated slide.
5. **The signature quote is a SEPARATE beat.** The client's second quotable line (the example signature quote, attributed to the client's name only) lives on its OWN dedicated quote slide. The example signature hook is NOT stamped on top of the signature-quote slide; conflating the two hooks is a defect (forensic-deck slide 18 did this).
6. **Print once per slide.** On a dedicated hook slide the line appears exactly once. Not as a bold copy plus a ghosted italic repeat. Not as headline plus body plus footer. Once.

---

## 3. THE ENFORCEMENT CHECK (what auto-fails the deck / slide)

**Auto-fail code AF-HOOK. Checked on slides_copy.md (Phase 1Q), on hook_package.json (the Strategist's audit), and on every rendered image (Phase 5/6). Triggers, any one of which fails:**

| Trigger | How it is detected | Failure message |
|---|---|---|
| HOOK-1: Hook on MORE than its dedicated slides | Count the slides on which the verbatim hook (or any near-variant of it) appears as copy or rendered text. Count > 4 = fail the DECK. | "AF-HOOK (HOOK-1): the hook appears on [N] slides (max 4 dedicated). It is being used as wallpaper. Remove it from all but the 3 to 4 named anchor slides per the Hook Strategist's placement map." |
| HOOK-2: Hook footer-stamped on ANY slide | Detect the hook line in a footer / bottom-band / recurring-strip position on any slide (copy field TEXT_ANCHOR = bottom band carrying the hook on a non-dedicated slide, or a rendered bottom strip carrying the hook). Any occurrence = fail that slide. | "AF-HOOK (HOOK-2): slide N footer-stamps the hook. The hook is never a footer. Remove the footer band entirely from this slide." |
| HOOK-3: No dedicated typography hook slide exists | Count of dedicated hook slides = 0 = fail the DECK. | "AF-HOOK (HOOK-3): the deck has zero dedicated hook slides. Build 3 to 4 pure-typography hook slides at the named anchors." |
| HOOK-4: Hook printed TWICE on one slide | On any single slide, the hook line appears 2 or more times (for example a bold copy plus a ghosted italic repeat, or headline plus footer). | "AF-HOOK (HOOK-4): slide N prints the hook [N] times. Print it exactly once. Remove the duplicate(s)." |
| HOOK-5: Hook mutated, extended, reworded, or abbreviated | Compare every rendered/copy occurrence character-by-character against the canonical HOOK string in mission_prd.json. Any difference (added clause, dropped word, reordering) = fail. | "AF-HOOK (HOOK-5): slide N renders a mutated hook: '[rendered]' vs canonical '[canonical]'. The hook is a verbatim refrain. Restore the exact string." |
| HOOK-6: Hook misspelled or garbled in a rendered image | On the rendered slide, the hook contains a misspelling or garbled glyph ("hclarity"). This is also AF-I1 at image QC; it is double-flagged here because the hook is sacred. | "AF-HOOK (HOOK-6): slide N renders the hook misspelled: '[rendered]'. Re-render via RE-PROMPT + RE-SEED; on persistent garble ESCALATE TO A HUMAN — never a native text overlay (Decision 5C, AF-OVERLAY-DELIVERED)." |
| HOOK-7: Signature quote conflated with the hook | The dedicated signature-quote slide also carries the control-vs-clarity hook. | "AF-HOOK (HOOK-7): slide N is the signature-quote beat but also carries the main hook. Keep them as two separate beats. Remove the main hook from the quote slide." |

**Render-time guarantee against HOOK-6:** because the hook is sacred, a hook that garbles twice is fixed by the Slide Image Creator's RE-PROMPT + RE-SEED loop (tighten the per-line spelling-lock + negative block, new seed, re-render the SINGLE composed gpt-image-2 image), and on PERSISTENT garble is ESCALATED TO A HUMAN. The hook text is ALWAYS baked into the image and is NEVER composited as a native PPTX text run/layer — the legacy native-text overlay path is eliminated (Decision 5C; a `pptx_text_overlays.json` or any native on-slide text run is AF-OVERLAY-DELIVERED). See slide-image-creator SOP 9.5 step 7.

---

## 4. PASS vs FAIL EXAMPLES (drawn from the actual forensic reference deck defects)

**FAIL (the forensic reference deck, deck-wide):** the hook footer-stamped on slides 1, 2, 4, 5, 6, 8, 10, 12, 13, 14, 15, 18, 20, 22, 23, 25, 26, 28, 29, 32, 34, 37, 38, 40, 42, 44, 45 (40 of 45) -> AF-HOOK-1 (count 40 > 4) and AF-HOOK-2 (footer on every one).
**PASS:** delete the footer from all 40 slides; build 4 dedicated pure-typography hook slides at the named anchors; the hook appears on exactly those 4 and nowhere else.

**FAIL (forensic-deck slides 10, 12, 14, 22, 28, 44):** hook printed twice (bold copy plus ghosted italic repeat) -> AF-HOOK-4. Slide 4 printed it three times -> AF-HOOK-4.
**PASS:** the hook appears once on each dedicated slide; these content slides carry no hook at all.

**FAIL (forensic-deck slide 28):** "...and the results are significantly different." appended to the hook -> AF-HOOK-5 (extended/mutated).
**PASS:** the canonical line is rendered verbatim, with nothing added.

**FAIL (forensic-deck slide 23):** footer rendered a misspelled hook ("hclarity") -> AF-HOOK-6 (misspelled) and AF-HOOK-2 (footer).
**PASS:** the hook is on a dedicated slide, baked into the image and spelled exactly (verified letter-for-letter by the OCR readback).

**FAIL (forensic-deck slide 18):** the example signature quote ("We Walk Them Through How To Think About It") on its own slide BUT with the example signature hook footer stamped on top -> AF-HOOK-7 and AF-HOOK-2.
**PASS:** the signature quote stands alone on its own beat (name-only attribution); the main hook is on its separate dedicated slides.

---

## 5. ESCALATION / REPAIR PATH

1. The Hook Strategist is the owner of the placement map and the hook-absent list. The Strategist's audit (in hook_package.json) must report: `hook_carrying_slides` (the 3 to 4 anchors with slide numbers), `footer_occurrences` (must be 0), `dedicated_slide_count` (3 to 4), `canonical_hook` (the exact string), and `verdict`. If the audit is missing or reports more than 4 carrying slides or any footer, Phase 1Q fails before scoring.
2. On AF-HOOK-1/2/4 (overuse, footer, duplicate), the repair routes to the **Slide Copywriter** to strip the hook from all non-anchor slides, and to the **Slide Image Creator** to delete any footer-band render element.
3. On AF-HOOK-3 (no dedicated slide), the **Director** reserves 3 to 4 dedicated hook slots in arc_allocation.json at the named beats, then the Copywriter writes them.
4. On AF-HOOK-5/6 (mutation, misspelling), the canonical string in mission_prd.json is the single source of truth; the slide is re-rendered via RE-PROMPT + RE-SEED, and on persistent garble is ESCALATED TO A HUMAN — the hook is always baked into the image, never composited as native text (Decision 5C, AF-OVERLAY-DELIVERED).
5. On AF-HOOK-7 (conflation), the main hook is removed from the signature-quote slide.
6. Loop up to 3 times (shared Phase 1Q / Phase 5 budget). On the 4th failure escalate to the Director and ROLE-16 Healer per QC SOP 9.4.

---

## 6. RECONCILIATION WITH THE EXISTING (FLOOR-BASED) RULE -- REQUIRED INTEGRATION EDITS

This SOP contradicts, on purpose, the current floor-based hook rule that PRODUCED the forensic reference deck failure. The integrator MUST make these exact changes so the system stops flooring-and-stamping:

- **Master SOP Section 4.3 rule 1:** replace "The hook appears AT LEAST 7 TIMES across the deck (scale up on longer decks: roughly one occurrence per 8 to 10 slides, never fewer than 7)" with "The hook appears on EXACTLY 3 to 4 DEDICATED pure-typography slides at named beats and NOWHERE ELSE. Footer-stamping is banned. The hook is a verbatim, sacred refrain." Keep "Sing it early", "Refrain after proof" only as a NOTE that the refrain after proof is one of the 3 to 4 dedicated beats, not a new footer.
- **Master SOP Section 5.1, THE HOOK bullet:** replace "Sing it at least 7 times" with "Place it on 3 to 4 dedicated slides only." Delete "refrains at the bottom of proof slides" (that line authorized the footer) and "light occurrences through every section."
- **Master SOP Section 6.1 criterion 11 (HOOK COUNT):** replace "Fewer than 7 = auto-fail" with "More than 4 hook-carrying slides = auto-fail; zero dedicated hook slides = auto-fail; the hook footer-stamped on any slide = auto-fail."
- **QC role AF-C2:** replace the BELOW-7 floor auto-fail with the AF-HOOK ceiling battery above.
- **Hook Strategist role:** change the KPI "Hook occurrences >= 7" to "Hook-carrying slides: 3 to 4; footer occurrences: 0; dedicated typography hook slides: 3 to 4." Replace the "7 to 10 variants + refrains after proof" placement logic with the 3-to-4-anchor + hook-absent-list logic. The dedicated A4 hook slide and the closing reprise remain hard requirements (they ARE two of the 3 to 4 anchors).
- **Slide Image Creator SOP 9.4 (Overlays element 8):** DELETE the "semi-transparent band at the bottom 15% ... HOOK VARIANT TEXT" footer rendering. The hook renders ONLY as the type-dominant content of a dedicated A4 hook slide. Non-hook slides have no hook overlay.
- **Slide Copywriter SOP 9.1 step 7 and SOP 9.2:** remove the "insert hook refrains until the count reaches 7" instruction; replace with "place the hook only on the 3 to 4 dedicated anchor slides from the Hook Strategist's map; never as a footer; never on a content slide."
