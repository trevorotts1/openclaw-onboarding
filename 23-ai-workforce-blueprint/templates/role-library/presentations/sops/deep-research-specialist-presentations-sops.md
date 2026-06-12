# SOPs Mirror -- Deep Research Specialist -- Presentations

**Source:** presentations/deep-research-specialist-presentations.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md

### SOP 9.1 -- Niche Deck and Offer Benchmark Research

**When to run:** On-demand, when dispatched by the Director. Common dispatch triggers: (a) proof_audit.txt has >= 3 PROOF PENDING items, (b) the Offer Price Strategist cannot find a market-rate anchor for an offer component, (c) the Director wants competitor deck structure benchmarks before writing the arc.

**Inputs:**
- working/copy/intake.json (for research context)
- working/copy/proof_audit.txt (for specific proof gaps, if applicable)
- Director's research brief request (specific research questions)

**Steps:**
1. Build the research plan. List exactly 5-10 search queries. Each query must target one of three research categories:
   - Category A (Niche Deck Structures): "best webinar deck structure for [COMPANY_INDUSTRY] coaches", "[INDUSTRY] online course enrollment presentation format", "high-converting webinar slides [TARGET_AUDIENCE]".
   - Category B (Price Anchors): "[INDUSTRY] group program price range", "[OFFER_NAME] competitor pricing [YEAR]", "high-ticket coaching offer price anchor [TARGET_AUDIENCE]".
   - Category C (Proof Statistics): "[COMPANY_INDUSTRY] ROI statistics [YEAR]", "[TARGET_AUDIENCE] transformation results study", "[problem statement] prevalence data".
2. Execute each query. For each result:
   a. Record the finding: the specific fact or statistic.
   b. Record the source: URL + publication name + publication date.
   c. Record the confidence level:
      - HIGH: primary source (government data, peer-reviewed study, company's own published results)
      - MEDIUM: secondary source (news article citing a study, industry report citing primary data)
      - LOW: tertiary source (blog post, forum, no clear citation chain)
   d. Flag LOW-confidence findings as not usable for slide copy without further verification.
3. Synthesize the findings. Group by category (A, B, C). Within each category, rank by confidence (HIGH first).
4. Write the Research Brief to working/research/brief-[DECK_SLUG].md. Structure:
   ```markdown
   # Research Brief -- [DECK_SLUG]
   Research Date: [YYYY-MM-DD]
   Researcher: Deep Research Specialist -- Presentations

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

   ## Summary: Top 5 Most Usable Findings
   [Numbered list of the 5 findings with highest confidence and relevance]

   ## Gaps Still Open
   [Any research questions that returned no HIGH or MEDIUM confidence findings]
   ```
5. Add the brief to working/research/archive.json: `{ "deck_slug": "...", "brief_path": "...", "researched_at": "...", "query_count": N, "findings_count": N }`.
6. Notify the Director that the brief is ready. Include the "Top 5 Most Usable Findings" summary in the notification message.

**Outputs:**
- working/research/brief-[DECK_SLUG].md
- working/research/archive.json (entry added)

**Hand to:** Director (who routes to Copywriter for proof gaps and to Offer Price Strategist for price anchor data)

**Failure mode:** If all search queries return only LOW-confidence results for a specific category: report this to the Director: "No HIGH or MEDIUM confidence data found for [Category C -- proof statistics for [AUDIENCE]]. The client must provide their own proof for these slides." Do not present LOW-confidence findings as reliable data.

---
