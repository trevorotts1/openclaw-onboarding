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
- working/copy/intake.json (for research context; read PROOF_ASSETS and GROUNDED_CONTENT fields)
- working/copy/proof_audit.txt (for specific proof gaps, if applicable)
- Director's research brief request (specific research questions)

**Steps:**
1. Build the research plan. List 5-15 search queries. Each query must target one of four research categories:
   - Category A (Niche Deck Structures): "best webinar deck structure for [COMPANY_INDUSTRY] coaches", "[INDUSTRY] online course enrollment presentation format", "high-converting webinar slides [TARGET_AUDIENCE]".
   - Category B (Price Anchors): "[INDUSTRY] group program price range", "[OFFER_NAME] competitor pricing [YEAR]", "high-ticket coaching offer price anchor [TARGET_AUDIENCE]".
   - Category C (Proof Statistics): "[COMPANY_INDUSTRY] ROI statistics [YEAR]", "[TARGET_AUDIENCE] transformation results study", "[problem statement] prevalence data".
   - Category D (External Corroboration): This category serves the single GP-8 function "who says so other than you?" and covers all three sub-types together as ONE requirement:
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

   ## Category B: Price Anchors
   [Finding]...

   ## Category C: Proof Statistics
   [Finding]...

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

   ## Category F: Design Styles and Typography Research (see SOP 9.3 for detail)
   [Output of SOP 9.3 pasted here verbatim; also written separately to working/research/design-brief-[DECK_SLUG].md]

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
1. Build Category F research queries: F1 (competitor/aspirational deck visual styles), F2 (typography in the niche -- defaults to avoid, alternatives to use), F3 (color/grading trends), F4 (layout/composition archetypes -- overused vs underused).
2. Execute queries. For each result: record finding + source URL + publication date + at least one observed published example + confidence (HIGH/MEDIUM/LOW) + `feeds:` note ("Typography Architect" and/or "Slide Image Creator").
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

