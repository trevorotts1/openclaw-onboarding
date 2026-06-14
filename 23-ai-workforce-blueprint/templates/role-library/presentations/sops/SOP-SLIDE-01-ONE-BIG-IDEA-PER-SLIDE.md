# SOP-SLIDE-01: ONE BIG IDEA PER SLIDE

**Cluster:** Slide-Craft Rules
**Master authority:** universal-sops/CLIENT-WEBINAR-DECK-SOP.md (Section 4.3 rule 9, Section 5.1, criterion 1)
**Owning roles at write time:** Director of Presentations (arc allocation and the hard splits), Slide Copywriter (per-slide enforcement)
**Owning role at render time:** Slide Image Creator (renders only the copy blocks)
**Enforced at the gate by:** QC Specialist - Presentations (auto-fail AF-OBI, below)
**Status:** Reference SOP, RECONCILED with the live gate. The one-big-idea protection is ALREADY WIRED in qc-specialist-presentations.md as auto-fail AF-C6 ("a slide that makes more than one point auto-fails") plus AF-C8 (the 30-word per-slide total-density ceiling) and copy QC criterion c5. The draft codes below (AF-OBI-1..6) are this SOP's own doctrine taxonomy; in the live repo read AF-OBI as AF-C6 + AF-C8. Do NOT add a parallel AF-OBI namespace to the QC role; that protection is done. This document is the authored doctrine behind the live check.

---

## 1. PURPOSE

A webinar slide carries ONE idea. The audience cannot read a slide and listen to the presenter at the same time; if the slide holds two ideas, they read instead of listen, and the presenter becomes furniture. This SOP exists because the Corey final deck shipped slides with three to five separate ideas stacked on one face (the footer hook silently added a second idea to roughly thirty of them), and the existing one-big-idea rule was a SCORED criterion that a two-idea slide could average its way past. Description failed. This SOP makes one-big-idea a hard, machine-checkable gate that a deck cannot pass.

This is the rule above all other slide-craft rules. When any other rule conflicts with it, this rule wins and the content is split across more slides.

---

## 2. THE HARD RULE

A slide presents exactly ONE core idea, expressed in a handful of words. Specifically and non-negotiably:

1. **One core idea per slide.** A core idea is one claim, one contrast, one number, one promise, one pain, or one beat. If a slide asserts a second claim, makes a second contrast, or teaches a second concept, it is two slides.
2. **The mandatory splits (these are not judgment calls):**
   - A **diagnosis + method + outcome** is THREE slides (one each). Never one slide that does all three.
   - A **value trio** (for example "confident, consistent, clear") is THREE slides plus a FOURTH formula slide (the trio summed into the equation). Four slides total. Never one slide listing all three Cs, and never a trio slide with a separate sub-grid bolted on.
   - A **gap + its reframe** is TWO slides (the gap on one, the "what if the problem is not X but Y" reframe on the next). Never one slide carrying both.
   - **Four distinct pains** are FOUR slides, one emotional image each (master rule 9). Never a bulleted list of pains.
3. **Text-block ceiling.** A slide carries at most THREE text blocks: headline, optional sub-copy, optional ONE supporting element (a stat chip, a label, or a CTA chip). A fourth text block is a defect. The hook footer is a text block; because the hook footer is banned outright (see SOP-SLIDE-03), it never counts as an allowed block and its presence is its own separate auto-fail.
4. **Word ceiling.** Headline 9 words maximum (target 4 to 7). Sub-copy 18 words maximum, one line. Counts are exact and mechanical (master Section 5.1). A slide that needs more words than this to make its point has more than one idea; split it.

---

## 3. THE ENFORCEMENT CHECK (what auto-fails the slide)

The QC Specialist runs these mechanical checks on slides_copy.md (Phase 1Q) and again on the rendered slide (Phase 5 and Phase 6). Each is a binary trigger, checked BEFORE any 1-to-10 scoring. Any trigger forces an immediate FAIL on that slide regardless of score.

**Auto-fail code AF-OBI (One Big Idea). Triggers, any one of which fails the slide:**

| Trigger | How it is detected | Failure message |
|---|---|---|
| OBI-1: More than 3 text blocks on the slide | Count distinct text blocks in the slide entry (HEADLINE, SUB-COPY, SUPPORTING) plus any block rendered on the image that is not one of those three. Count > 3 = fail. | "AF-OBI (OBI-1): slide N has [count] text blocks (max 3). Blocks found: [list]. Split into [count-2] slides or move the extra block to the Presenter's Guide." |
| OBI-2: Headline over 9 words | Mechanical word count of the HEADLINE field, exact. | "AF-OBI (OBI-2): slide N headline is [N] words (max 9). It is carrying two ideas. Split." |
| OBI-3: Two or more core ideas in one entry | The QC agent identifies the count of distinct claims/contrasts/concepts. A diagnosis-and-method, a gap-and-reframe, a value-trio-on-one-slide, or two unrelated assertions = fail. | "AF-OBI (OBI-3): slide N contains [N] core ideas: [idea A]; [idea B]. Per SOP-SLIDE-01 this is [N] separate slides. Split as: [proposed split]." |
| OBI-4: A value trio on a single slide | Detect three parallel named values (alliterated trio) co-present in HEADLINE/SUB-COPY/SUPPORTING. | "AF-OBI (OBI-4): slide N lists a full value trio ([the three values]) on one slide. Per SOP-SLIDE-01 each value is its own slide plus a formula slide. Build 4 slides." |
| OBI-5: A bulleted list of pains | Detect 2 or more distinct pain statements as list items on one slide. | "AF-OBI (OBI-5): slide N lists [N] pains as bullets. Per master rule 9 each pain is its own slide with its own emotional image. Build [N] slides." |
| OBI-6: A comparison table with more than 2 rows of contrast | Count contrast rows rendered on the slide (the Corey deck shipped an 8-row control-vs-clarity table). More than 2 rows = the slide is teaching a whole framework, not one contrast. | "AF-OBI (OBI-6): slide N renders a [N]-row comparison table. Reduce to the single sharpest contrast (one row, two sides) or move the full table to the Presenter's Guide." |

**Render-time addition (Phase 5/6):** the rendered image is inspected for any text block beyond the three approved copy blocks. A step list, a credential paragraph, a "Step 1 / Step 2 / Step 3" cue, or any body text not present in slides_copy.md that appears on the rendered face fails AF-OBI at the image gate (this is where the Corey slide-5 stacked image cards leaked in: the copy was clean-ish but the image creator invented extra text blocks). Cross-reference: SOP-SLIDE-02 OBI overlaps with the audience-facing ban on invented captions.

---

## 4. PASS vs FAIL EXAMPLES (drawn from the actual Corey defects)

**FAIL (Corey slide 8, the canonical two-idea slide Trevor named by name):**
> "Doing The Right Things, The Wrong Way" (the gap) AND "What if the problem is not effort, but approach?" (the reframe), on one slide, plus a hook footer, plus an "An intrigue gap, on purpose" meta line.
Why it fails: OBI-3 (two core ideas: a gap and its reframe), OBI-1 (four-plus text blocks). This is two slides.

**PASS (the split):**
> Slide A, HEADLINE: "Doing the right things. The wrong way." (the gap, 6 words). Slide B, HEADLINE: "What if it is not effort, but approach?" (the reframe, 8 words). Each is one idea, one text block, under 9 words, no footer.

**FAIL (Corey slide 5):**
> Three headline ideas stacked ("Why It Happens. The Framework. Confident Guide."), three full step descriptions baked into image cards, a hook footer, and a redundant "Step 1 / Step 2 / Step 3" cue. At least five text blocks, three big ideas.
Why it fails: OBI-3 (three core ideas), OBI-1 (five-plus text blocks).

**PASS (the split):** a why-it-happens slide, a framework slide, and an outcome beat; the step descriptions move to the Presenter's Guide; no footer.

**FAIL (Corey slide 26):**
> All three Cs (Confident, Consistent, Clear) on one slide PLUS a separate CLARIFY/COMMUNICATE/COACH card grid PLUS a hook footer.
Why it fails: OBI-4 (full value trio on one slide), OBI-1, OBI-3.

**PASS (the split):** a Confident slide, a Consistent slide, a Clear slide, then a formula slide ("Confident + Consistent + Clear = an Effective Guide"). Four slides.

**FAIL (Corey slide 28):**
> An 8-row comparison table (4 CONTROL traits vs 4 CLARITY traits) plus a headline plus a body paragraph plus the hook footer printed twice.
Why it fails: OBI-6 (8-row table), OBI-1.

**PASS:** reduce to the single sharpest one-row contrast (Control on the left, Clarity on the right), or move the full table to the Presenter's Guide and keep the slide to the one-line contrast.

---

## 5. ESCALATION / REPAIR PATH

1. On any AF-OBI trigger, the QC Specialist writes the failure message with the exact split proposed and routes it to the responsible role: a copy-level split goes to the **Slide Copywriter**; an arc-level split that requires net-new slide slots (a value trio needing four slots) goes to the **Director of Presentations** to update arc_allocation.json, then to the Copywriter.
2. The Director reserves slots for the mandatory splits AT ARC TIME so the splits do not later collide with the deck-density minimums (see SOP-SLIDE-04). A diagnosis+method+outcome reserves three slots; a value trio reserves four; a gap+reframe reserves two.
3. Re-run AF-OBI on the revised slides only. The split is verified mechanically (block count, word count, idea count).
4. Loop up to 3 times (shared loop budget with the other Phase 1Q gates). On the 4th failure, escalate to the Director and the ROLE-16 Healer with the persistent OBI trigger codes and the slide range, per the existing QC SOP 9.4.
5. A slide that cannot be reduced to one idea without losing meaning is almost always two slides that were never separated; the repair is always "split," never "shrink the font."
