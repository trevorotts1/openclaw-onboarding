# SOPs Mirror -- Deep Research Specialist -- Presentations

**Source:** presentations/deep-research-specialist-presentations.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md

### SOP 9.1 -- Niche Deck, Offer Benchmark, and External Corroboration Research

**When to run:** MANDATORY on every deck run as Phase -0.5, regardless of proof-asset availability, deck mode (personal or general), pipeline entry point (Brainstorming Buddy or Content-to-Presentation Architect), or deck size. Micro decks may produce a condensed brief with fewer queries, but the brief MUST exist and carry `research_complete: true` with all required category sections present. There are no opt-out triggers and no conditional skip paths; dispatching ROLE-04 as Phase -0.5 is a requirement of the Director SOP 9.x Step 5a. The prior "on-demand" dispatch triggers (a)-(d) are now sub-cases of the mandatory run, not its primary trigger.

**Inputs:**
- working/copy/intake.json (for research context; read PROOF_ASSETS, GROUNDED_CONTENT, and -- when present -- the `persuasion_intelligence` block propagated from a converter `source_brief.json` by the Director SOP 9.1 step 4a: `persuasion_intelligence.offer_intelligence`, `persuasion_intelligence.proof_assets`, `persuasion_intelligence.narrative_arc_type`, `persuasion_intelligence.transformation_promise`)
- working/copy/proof_audit.txt (for specific proof gaps, if applicable)
- Director's research brief request (specific research questions)

**Steps:**
1. Build the research plan. List 5-15 search queries for the Phase-1 categories below (A-D) PLUS the validation/persuasion categories (G-L) authored in SOP 9.4; the brief is not complete until SOP 9.1, 9.2, 9.3, AND 9.4 have all run. The brief does not merely DECORATE the deck -- it must materially IMPROVE and VALIDATE every Signature Presentation: every statistic, number, and price that will appear on a slide is verified upstream here (Category H), the offer price is anchored against real market comps (Category B), the arc is checked against proven structures (Category K), and the audience's objections are pre-loaded with proof (Category I). **When the run originated from the Content-to-Presentation Architect (ROLE-22) and `persuasion_intelligence` is present in intake.json:** seed the category queries from the source's own intelligence -- Category B queries use `offer_intelligence.price_anchor` and `offer_intelligence.price_mode` as starting-point benchmarks rather than generic market-range queries; Category D queries use `proof_assets` entries as corroboration targets ("who else says this same thing about [claim]?") and `primary_objection` to identify relevant third-party rebuttals; Category E scene descriptions use `narrative_arc_type` and `transformation_promise` to anchor grounded imagery to concrete moments in THIS source's method rather than generic industry stock scenes; Category I objections seed from `primary_objection`; Category K arc-validation seeds from `narrative_arc_type`; Category G quotes seed from the topic and `transformation_promise`.
   - Category A (Niche Deck Structures): "best webinar deck structure for [COMPANY_INDUSTRY] coaches", "[INDUSTRY] online course enrollment presentation format", "high-converting webinar slides [TARGET_AUDIENCE]".
   - Category B (Pricing & Value Benchmarking): "[INDUSTRY] group program price range", "[OFFER_NAME] competitor pricing [YEAR]", "high-ticket coaching offer price anchor [TARGET_AUDIENCE]", "[comparable offer] price vs value [YEAR]". When `offer_intelligence.price_anchor` is present, add a targeted query anchored to that stated figure. Build a comparable-market price band (low / median / high for the closest comparable offers) so the offer price AND the value-stack are credibly anchored, not asserted. **Out-of-market flag (mandatory):** compare the deck's intended FINAL_PRICE (and any per-component value figures) against the comparable band. If the price sits materially ABOVE the high end or BELOW the low end of the band, record an `out_of_market: true` flag with the band, the deviation, and a one-line "slide use note" so the Offer Price Strategist and the operator can decide before the price reaches a slide. You report the band; you never set the price.
   - Category C (Supporting Statistics / Studies / White Papers): "[COMPANY_INDUSTRY] ROI statistics [YEAR]", "[TARGET_AUDIENCE] transformation results study", "[problem statement] prevalence data", "[method/approach] white paper [YEAR]". Every Category C finding MUST carry a source URL AND a publication date so recency can be judged; prefer data from the last 18 months and flag anything older than 36 months as `stale: true`. A statistic with no date is not usable on a slide.
   - Category D (External Corroboration): This category serves the single GP-8 function "who says so other than you?" and covers all three sub-types together as ONE requirement. When `proof_assets` from the source's own `persuasion_intelligence` block are present, treat each as a corroboration target: find third-party sources that confirm or validate each claim the source makes.
     - Sub-type D1 (Case studies): Published or verifiable client transformation stories in the same niche; "[INDUSTRY] client case study [TRANSFORMATION_CLAIM]".
     - Sub-type D2 (White-paper and research studies): Peer-reviewed or institutional research validating the client's method or the problem it solves; "[method/approach] research study [YEAR]", "[problem statement] evidence-based intervention".
     - Sub-type D3 (Wall-of-wins): Documented testimonials, results screenshots, cohort outcome data, or award/recognition items the client has on record; combine with client-supplied PROOF_ASSETS from intake.json.
2. Execute each query. For each result:
   a. Record the finding: the specific fact, statistic, or outcome claim.
   b. Record the source: URL + publication name + publication date.
   c. Record the confidence level:
      - HIGH: primary source (government data, peer-reviewed study, company's own published results, client-verified testimonial with name + outcome)
      - MEDIUM: secondary source (news article citing a study, industry report citing primary data, third-party platform review)
      - LOW: tertiary source (blog post, forum, no clear citation chain)
   d. Flag LOW-confidence findings as not usable for slide copy without further verification.
   e. For Category D findings: also record the sub-type (D1 / D2 / D3) and a one-sentence "slide use note" explaining which proof slide this corroborates.
3. Synthesize the findings. Group by category (A, B, C, D). Within each category, rank by confidence (HIGH first). Within Category D, group by sub-type (D1 / D2 / D3).
4. Count total HIGH + MEDIUM Category D items. Record this as `external_proof_count`. If `external_proof_count` = 0: set a GP-8 ALERT flag in the brief header.
5. Write the Research Brief to working/research/brief-[DECK_SLUG].md. Structure:
   ```markdown
   # Research Brief -- [DECK_SLUG]
   Research Date: [YYYY-MM-DD]
   Researcher: Deep Research Specialist -- Presentations
   research_complete: true
   external_proof_count: [N]
   GP-8 ALERT: [YES if external_proof_count = 0, else NO]

   ## Category A: Niche Deck Structures
   [Finding 1]
   - Source: [URL] ([Publication Name], [Date])
   - Confidence: HIGH/MEDIUM/LOW
   - Usable for: arc structure, section ordering, hook placement

   [Finding 2]...

   ## Category B: Pricing & Value Benchmarking
   [Comparable-market price band: low / median / high, each with source + date]
   [out_of_market flag if the intended FINAL_PRICE or any value figure is outside the band]
   [Finding]...

   ## Category C: Supporting Statistics / Studies / White Papers
   [Finding -- each with source URL + publication date; stale:true if older than 36 months]...

   ## Category D: External Corroboration ("Who Says So Other Than You?" -- GP-8)
   ### D1 -- Case Studies
   [Finding]
   - Source: [URL] ([Publication or Client Name], [Date])
   - Confidence: HIGH/MEDIUM/LOW
   - Slide use note: [which proof slide this corroborates]

   ### D2 -- White-Paper and Research Studies
   [Finding]...

   ### D3 -- Wall-of-Wins
   [Finding]...
   (Include client-supplied PROOF_ASSETS from intake.json here, annotated with confidence level.)
   (Category D feeds TWO of the operator's required presentation components: D1/D2 feed component 3 "who says so other than you" -- woven between the drops; D3 feeds component 4 the WALL OF WINS slide near the close. Surface enough named, located D3 wins for the Copywriter to build a multi-win wall; if none exist, mark them `[CLIENT TO SUPPLY]` and note it, never fabricate.)

   ## Category E: Grounded Image Context (see SOP 9.2 for detail)
   [Output of SOP 9.2 pasted here verbatim]

   ## Category F: Design + Hook + Pacing Best-Practices Research (see SOP 9.3 for detail)
   [Output of SOP 9.3 pasted here verbatim; also written separately to working/research/design-brief-[DECK_SLUG].md]

   ## Category G: Credible Attributable Quotes (see SOP 9.4 for detail)
   [Output of SOP 9.4 Step G pasted here verbatim]

   ## Category H: Fact-Validation -- Slide-Claim Verification Ledger (see SOP 9.4 for detail)
   [Output of SOP 9.4 Step H pasted here verbatim; also written separately to working/research/fact-validation-[DECK_SLUG].json]

   ## Category I: Objection Research (see SOP 9.4 for detail)
   [Output of SOP 9.4 Step I pasted here verbatim]

   ## Category J: Social-Proof Patterns (see SOP 9.4 for detail)
   [Output of SOP 9.4 Step J pasted here verbatim]

   ## Category K: Persuasion-Framework Validation (see SOP 9.4 for detail)
   [Output of SOP 9.4 Step K pasted here verbatim]

   ## Category L: Compliance Flags (see SOP 9.4 for detail)
   [Output of SOP 9.4 Step L pasted here verbatim]

   ## Summary: Top 5 Most Usable Findings
   [Numbered list of the 5 findings with highest confidence and relevance; at least 1 must be from Category D if any exist]

   ## Gaps Still Open
   [Any research questions that returned no HIGH or MEDIUM confidence findings, including GP-8 ALERT if applicable]
   ```
6. Add the brief to working/research/archive.json: `{ "deck_slug": "...", "brief_path": "...", "researched_at": "...", "query_count": N, "findings_count": N, "external_proof_count": N, "gp8_alert": true/false }`.
7. Notify the Director that the brief is ready. Include the "Top 5 Most Usable Findings" summary in the notification message. If `gp8_alert` is true, open the notification with: "GP-8 ALERT: zero third-party proof found -- the QC Specialist must flag this deck before delivery. Operator must supply or approve substitute corroboration."

**Outputs:**
- working/research/brief-[DECK_SLUG].md
- working/research/archive.json (entry added)

**Hand to:** Director (who routes to Copywriter for proof gaps; to Offer Price Strategist for price anchor data; to Slide Image Creator for Category E grounded image context via SOP 9.2)

**Failure mode:** If all search queries return only LOW-confidence results for a specific category: report this to the Director: "No HIGH or MEDIUM confidence data found for [Category D -- external corroboration for [AUDIENCE/NICHE]]. Set GP-8 ALERT. The client must supply their own verified proof assets for these slides." Do not present LOW-confidence findings as reliable data.

---

### SOP 9.2 -- Grounded Image Context Extract (IMAGE PROMPT INPUT)

**When to run:** On every research brief run, immediately after SOP 9.1. This SOP extracts concrete imagery anchors from the client's actual method, offer, and transformation so the Slide Image Creator can depict real moments from THIS client's work, not generic stock scenes.

**Inputs:**
- working/copy/intake.json (read GROUNDED_CONTENT, OFFER_NAME, TARGET_AUDIENCE, COMPANY_INDUSTRY)
- working/research/brief-[DECK_SLUG].md (Category C + D findings for visual proof moments)
- Director's research brief request

**Steps:**
1. Read GROUNDED_CONTENT from intake.json. This is the client's book / message / offer / methodology (e.g., "a 12-week group coaching program teaching women entrepreneurs to raise capital via pitch decks"). If GROUNDED_CONTENT is empty: flag it to the Director and derive a best-effort description from OFFER_NAME + COMPANY_INDUSTRY -- label it "DERIVED -- confirm with operator."
2. For each of the following image-prompt slot types, write one concrete grounded scene description (2-4 sentences, imagery-facing language):
   a. PAIN SLIDE scene: What does a member of TARGET_AUDIENCE look like at their lowest point relative to the problem this offer solves? Describe a real, recognizable, emotionally specific setting (not a generic "stressed person at desk"). Reference any D1 case study detail if available.
   b. METHOD SLIDE scene: What does the client's specific method or process look like in action? Name the room, the tool, the moment -- something only THIS client's approach produces (e.g., "a small-group workshop on a whiteboard mapping a startup's funding stack," not "people in a meeting").
   c. TRANSFORMATION SLIDE scene: What does a client who completed the offer look like 90 days later? Reference a specific outcome from Category C or D3 (wall-of-wins) if available. Describe what they are doing, not just how they feel.
   d. PROOF SLIDE scene: What does the external corroboration look like as an image? (e.g., "a close-up of a printed research citation or a framed award certificate on a real desk," or "a testimonial quote set in a clean pull-quote design against a lifestyle photography background" -- choose based on Category D sub-type).
   e. OFFER SLIDE scene: What does the client's offer look like as a physical or visual object? (e.g., "a printed binder labeled with the program name on a glass desk next to a laptop open to a cohort portal").
3. Write a GROUNDED_CONTENT_VARIABLE block for working/research/grounded-content-[DECK_SLUG].json:
   ```json
   {
     "deck_slug": "[DECK_SLUG]",
     "grounded_content_source": "[verbatim GROUNDED_CONTENT from intake, or DERIVED note]",
     "image_anchors": {
       "pain_slide": "[2-4 sentence concrete scene description]",
       "method_slide": "[2-4 sentence concrete scene description]",
       "transformation_slide": "[2-4 sentence concrete scene description]",
       "proof_slide": "[2-4 sentence concrete scene description]",
       "offer_slide": "[2-4 sentence concrete scene description]"
     },
     "gp8_proof_scenes_available": true/false,
     "derived_not_confirmed": true/false
   }
   ```
4. Paste the full contents of working/research/grounded-content-[DECK_SLUG].json into the Research Brief under "Category E: Grounded Image Context."
5. Notify the Director: "Category E grounded image context is ready. Route to Slide Image Creator before prompt authoring begins. Image Creator must load working/research/grounded-content-[DECK_SLUG].json and reference the relevant `image_anchors` entry for each slide archetype."

**Outputs:**
- working/research/grounded-content-[DECK_SLUG].json
- Category E section inserted into working/research/brief-[DECK_SLUG].md

**Hand to:** Director (routes grounded-content JSON to Slide Image Creator; Slide Image Creator loads it as the `grounded_content` variable in every prompt brief)

**Failure mode:** If GROUNDED_CONTENT is absent from intake.json AND no offer/method description can be derived: set `derived_not_confirmed: true`, write placeholder scene descriptions marked "[PLACEHOLDER -- operator must confirm before prompt authoring]", and alert the Director. Do NOT block the brief -- deliver the placeholders. The Image Creator will treat unconfirmed placeholders as generic until the operator confirms them.

---

### SOP 9.3 -- Design Style and Typography Research (Category F)

**When to run:** On every research brief run, alongside SOP 9.1. Mandatory except when `STYLE_BRANCH = "match existing"` or `"analyze reference"` (delegated to the Graphics Differentiated Imaging Unit per 00-START-HERE), in which case a delegation note replaces the F1-F4 findings.

**Inputs:**
- working/copy/intake.json (read COMPANY_INDUSTRY, OFFER_NAME, TARGET_AUDIENCE, STYLE_REFERENCES)
- Director's research brief request (deck_slug, any declared STYLE BRANCH)

**STYLE BRANCH handling:**
- `STYLE_BRANCH: "match existing"` or `"analyze reference"` -> set `design_research_mode: delegated_to_DIU`, record delegation note only, skip F1-F4.
- `STYLE_BRANCH: "create new"` or absent -> run F1-F4 fully.

**Steps:**
1. Build Category F research queries: F1 (competitor/aspirational deck visual styles), F2 (typography in the niche -- defaults to avoid, alternatives to use), F3 (color/grading trends), F4 (layout/composition archetypes -- overused vs underused), F5 (HOOK STRUCTURE for this audience -- proven opening-hook patterns, intrigue-gap and cold-open formats that perform in this niche), F6 (WEBINAR PACING for this audience -- segment timing, drop placement cadence, attention-retention rhythm for a ~30-min presentation to THIS audience). F5 and F6 feed the design brief AND the Hook Strategist's opening beat.
2. Execute queries. For each result: record finding + source URL + publication date + at least one observed published example + confidence (HIGH/MEDIUM/LOW) + `feeds:` note ("Typography Architect" and/or "Slide Image Creator" and/or "Hook Strategist").
3. Write Design Style Brief to `working/research/design-brief-[DECK_SLUG].md` with sections F1-F4 plus a 3-5 bullet summary.
4. Paste the full Design Style Brief into the main Research Brief under "Category F."
5. Notify the Director: "Category F Design Style Brief ready. Route design-brief-[DECK_SLUG].md to Typography Architect (Phase 1.5) and Slide Image Creator (Phase 2)."

**Niche gap:** If no niche data exists, use adjacent-market research labeled "FROM ADJACENT MARKET [market name]" and set `design_research_niche_gap: true`. Not a blocking condition.

**Outputs:**
- working/research/design-brief-[DECK_SLUG].md
- Category F section inserted into working/research/brief-[DECK_SLUG].md

**Hand to:** Director (routes design-brief to Typography Architect and Slide Image Creator)

**Failure mode:** No HIGH/MEDIUM data for a sub-type -- report the gap, use adjacent-market data labeled as such, do not block the brief.

---

### SOP 9.4 -- Deep Validation and Persuasion Research (Categories G-L)

**When to run:** MANDATORY on every deck run, alongside SOP 9.1/9.2/9.3, as part of Phase -0.5. This SOP is the reason the brief MATERIALLY IMPROVES AND VALIDATES the Signature Presentation rather than merely decorating it. The brief is not `research_complete: true` until Categories G, H, I, K, and L are present (J is conditional -- see Step J). The whole-brief NO-FABRICATION rule governs every finding here: each item is sourced + cited + confidence-tagged; an unverifiable claim is OMITTED and FLAGGED, never invented.

**Inputs:**
- working/copy/intake.json (read GROUNDED_CONTENT, OFFER_NAME, TARGET_AUDIENCE, COMPANY_INDUSTRY, PROOF_ASSETS, FINAL_PRICE if present, and -- when present -- `persuasion_intelligence`: `primary_objection`, `narrative_arc_type`, `transformation_promise`, `offer_intelligence`)
- working/copy/slides_copy.md or the brief's claim list, IF a draft exists at research time (for the Category H verification ledger; if no draft exists yet, Category H validates the offer/transformation claims and any numbers carried in intake.json + the source material, and the QC Specialist re-checks the rendered deck against this ledger at Phase 1Q)
- working/research/brief-[DECK_SLUG].md (Categories C and D, for cross-feeding)

**Steps (run all; each produces its own labeled section pasted into the main Research Brief):**

**Step G -- Credible Attributable Quotes.** Find quotes from named experts, authorities, recognized practitioners, or institutions relevant to the deck's topic and transformation promise. Each quote MUST be: (a) verbatim (or marked `[paraphrase]` with the source), (b) attributed to a named person/organization with their credential/title, (c) sourced to a URL + publication date, (d) confidence-tagged. A quote with no attributable, locatable source is OMITTED and listed under "Gaps Still Open" -- never paraphrase an unsourced quote into a slide. Record a one-line "slide use note" for each (which beat it strengthens: authority open, mid-deck credibility, objection rebuttal, or close). Misattributed or unverifiable quotes are a fabrication risk and are killed, not softened.

**Step H -- Fact-Validation (the upstream partner to the money/number gates AF-C3, AF-C4, and AF-PRICE-FACE).** Verify EVERY statistic, percentage, dollar figure, named study, dated claim, and quantified outcome that will appear -- or is proposed to appear -- on a slide, against an authoritative source. This is the gate that guarantees NO INVENTED FIGURE REACHES A SLIDE. Build a machine-readable verification ledger at `working/research/fact-validation-[DECK_SLUG].json`:
```json
{
  "deck_slug": "[DECK_SLUG]",
  "validated_at": "[ISO_DATE]",
  "claims": [
    {
      "claim": "[the exact stat/number/claim as it would appear on a slide]",
      "slide_ref": "[slide id or 'intake' or 'source']",
      "status": "VERIFIED | FLAGGED | KILL",
      "source_url": "[URL or null]",
      "source_name": "[publication/author or null]",
      "source_date": "[YYYY-MM-DD or null]",
      "confidence": "HIGH | MEDIUM | LOW",
      "note": "[why VERIFIED, or what could not be confirmed, or why KILL]"
    }
  ],
  "verified_count": N,
  "flagged_count": N,
  "kill_count": N
}
```
- `VERIFIED` = the figure is confirmed against a named, dated, attributable source (sourced + recorded).
- `FLAGGED` = the figure is plausible but could not be confirmed to HIGH/MEDIUM confidence; it must NOT be rendered until the operator confirms or a source is found. Mark the slide claim `[FLAGGED -- unverified, operator must confirm or pull]`.
- `KILL` = the figure is contradicted by authoritative sources, or is an invented/un-sourceable number; it is removed and must never reach a slide.
This ledger is the upstream partner to the QC money gates: AF-C3 (no fabricated proof/statistic not traceable to intake or research brief), AF-C4 (cross-slide numeric mismatch), and AF-PRICE-FACE (unauthorized prices on the face). A number that is not `VERIFIED` in this ledger has no business on a slide. Paste a human-readable summary of the ledger (one line per claim with its status) into the brief under Category H.

**Step I -- Objection Research.** Identify the TARGET_AUDIENCE's top 3-6 objections to an offer like this one (price, time, trust, "will it work for me", prior failures, skepticism). For each objection, supply a proof point or rebuttal anchored to a sourced finding (cross-feed from Category C/D/G where possible). When `persuasion_intelligence.primary_objection` is present, lead with it. Each objection records: the objection (in the audience's own framing), the rebuttal angle, and the supporting proof (with source + confidence). Objections with NO available proof point are still listed -- flagged "NO PROOF FOUND -- client must supply or the deck must reframe" -- so the Copywriter and Devil's Advocate can act. Feeds the Slide Copywriter (objection-handling beats) and the Devil's Advocate.

**Step J -- Social-Proof Patterns.** Research the case-study and testimonial STRUCTURES that perform in this niche (e.g. before/after transformation arc, named-metric proof, peer-mirroring testimonial, authority endorsement, cohort-outcome wall). This is PATTERN research (how proof is framed in this niche), distinct from Category D which collects the actual corroboration items. Output 3-5 named patterns, each with a sourced/observed example + a one-line note on which proof slide or Wall-of-Wins structure it informs. **Conditional:** if Category D already surfaced enough named, located proof items to build the Wall of Wins and the "who says so" beats, Category J may be a condensed 2-3 pattern note; it is still required (it shapes HOW the Copywriter frames the proof), but it is the only G-L category permitted to be condensed. Feeds the Slide Copywriter and the Wall-of-Wins build (SOP-PITCH-04).

**Step K -- Persuasion-Framework Validation.** Check the deck's intended arc against PROVEN webinar/pitch structures (e.g. PASTOR, Problem-Agitate-Solve, the Perfect Webinar stack-slide arc, hook -> stakes -> promise -> proof -> offer -> CTA). When `persuasion_intelligence.narrative_arc_type` is present, validate THAT named arc against published structures. Output: (a) the named reference framework(s) with source, (b) a beat-by-beat check of the deck's planned arc against the reference -- which beats are present, which are missing or out of order, (c) a one-line recommendation per gap (routed as a recommendation to the Director, never a copy decision). This is the upstream partner to AF-C11 (missing persuasion arc / no CTA): if a required beat is absent, surface it here so it is fixed before copy, not caught at the gate. Feeds the Director and the Slide Copywriter.

**Step L -- Compliance Flags.** Scan the offer, transformation promise, and every proposed claim for regulated-claim risk: INCOME / earnings claims, MEDICAL / health-outcome claims, RESULTS / "guaranteed outcome" claims -- with heightened scrutiny for coaching, family, financial, and health offers. For each flagged claim, record: the claim, the risk category (income / medical / results / other), the nature of the risk (e.g. "implies guaranteed earnings -- needs an earnings disclaimer or must be reframed as a possibility, not a promise"), and a recommended safe reframe or required disclaimer. You do NOT give legal advice and you do NOT block the deck; you SURFACE the risk so the Director, the operator, and the Devil's Advocate can resolve it before delivery. A compliance flag with a recommended reframe is the deliverable. Feeds the Director, the Devil's Advocate, and the Slide Copywriter.

**Synthesis + write:** Paste each step's output into the main Research Brief under its named category (G-L), write the Category H ledger to `working/research/fact-validation-[DECK_SLUG].json`, and update the brief header counts:
```
validated_claim_count: [VERIFIED count from Category H]
flagged_claim_count: [FLAGGED count]
killed_claim_count: [KILL count]
out_of_market: [true/false from Category B]
objection_proof_gaps: [count of objections with NO proof from Category I]
compliance_flags: [count from Category L]
arc_beats_missing: [count from Category K]
```

**Outputs:**
- working/research/fact-validation-[DECK_SLUG].json
- Categories G, H, I, J, K, L inserted into working/research/brief-[DECK_SLUG].md
- Header counts above added to the brief

**Hand to:** Director, who routes: Category G quotes + Category C/D to the Slide Copywriter; Category H ledger to the QC Specialist (for AF-C3 / AF-C4 / AF-PRICE-FACE cross-check at Phase 1Q) and to the Slide Copywriter (no number rendered unless VERIFIED); Category B out-of-market flag to the Offer Price Strategist; Category I + J to the Slide Copywriter and Devil's Advocate; Category K to the Director and Copywriter; Category L compliance flags to the Director and Devil's Advocate.

**Failure mode:** If a category returns no HIGH/MEDIUM findings: deliver the category section with its gaps explicitly listed ("NO VERIFIED [quotes / proof points / etc.] FOUND -- client must supply or the deck must reframe"), set the relevant header count, and notify the Director. Never fabricate to fill a category. Category H is the hard one: a deck whose slide-bound numbers cannot be VERIFIED ships with those numbers FLAGGED, and the QC Specialist blocks any FLAGGED/KILL number that reaches a rendered slide via AF-C3.

---

