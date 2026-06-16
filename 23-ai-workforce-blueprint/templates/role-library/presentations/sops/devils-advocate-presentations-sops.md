# SOPs Mirror -- Devil's Advocate -- Presentations

**Source:** presentations/devils-advocate-presentations.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md

### SOP 9.1 -- Adversarial Doctrine Review and Kill-List

**When to run:** By default, every DA review runs AFTER Phase 1Q (copy QC passes) and BEFORE Phase 1A (owner approval) -- so the adversarial review sits on QC-approved copy, doctrine violations are caught before the owner spends attention, and findings can be addressed in copy before the owner approves and before any prompt is written. A post-delivery review (after Phase 6, on the final deck) remains OPTIONAL and is dispatched only when the Director explicitly requests it.

**Inputs:**
- working/copy/slides_copy.md (approved copy)
- working/copy/price_ladder.json
- working/copy/hook_variants.json
- working/copy/proof_audit.txt

**Steps:**
1. Read the entire slides_copy.md from slide 1 to the last slide. Read as if you are the most skeptical person in the target audience, not as a supporter.
2. Score the deck against ALL 24 Pitch Doctrine points (the 18 verbatim master points plus the 6 department extensions, all listed below). For each point:
   a. State: PASS or FLAG.
   b. If FLAG: cite the specific slide number(s), the specific text that violates the doctrine, and the specific fix required.
   c. A FLAG is a recommendation, not a mandate -- the Director decides whether to act on it. But you never soften a FLAG to avoid discomfort.
   d. EXCEPTION -- BLOCKING FLAGS: a HIGH-severity flag for FABRICATED PROOF or FAKE/FALSE SCARCITY is NOT a recommendation. It BLOCKS the run. The deck does not advance to Phase 1A (or to delivery, on a post-delivery review) until the Director resolves the blocking flag. These two flag types are the only flags that carry blocking authority; every other flag remains a recommendation the Director may accept or dismiss.
      - FABRICATED PROOF is tested under master doctrine point 12 (WHO SAYS SO -- proof must be named, located, and sourced) reinforced by the master no-fabrication rule (master SOP Section 3.2: any proof not sourced to the client's records or published third-party data is fabricated and is never invented). Any statistic, testimonial, or case study with no source in proof_audit.txt or intake PROOF_ASSETS is fabricated.
      - FAKE/FALSE SCARCITY is tested under master doctrine point 14 (ALWAYS PITCH SOMETHING -- real revenue and real commitment) reinforced by the master scarcity-and-urgency rule (master SOP Section 5.4: scarcity is real quantity only, urgency is real timing only; fabricated scarcity is forbidden). "Only 3 spots left" when no real cap exists, or "doors close forever" when they do not, is fake scarcity.
2e. Apply the Supplemental Lens Checks (SP-EXPERT / SP-LING / GP-4 / GP-10) defined above. These run alongside the 24-point doctrine review. For each lens: state PASS or FLAG, with the same specificity requirement as a doctrine FLAG (slide number, exact text, exact fix). Supplemental lens FLAGs are severity-classified identically (HIGH/MEDIUM/LOW); they do not carry blocking authority independently, but a HIGH lens FLAG should trigger a HIGH doctrine FLAG on the overlapping doctrine point where applicable (e.g., an SP-EXPERT FLAG that also violates doctrine point 12 is flagged as HIGH on doctrine 12).

3. Write the Kill List to working/da/kill_list-[DECK_SLUG].md:
   ```markdown
   # Kill List -- [DECK_SLUG]
   DA Review Date: [YYYY-MM-DD]
   Reviewer: Devil's Advocate -- Presentations

   ## Doctrine Point 1: The Hook Doctrine (banded ceiling: hook on 3-4 dedicated slides, ~4-5 appearances max)
   STATUS: PASS/FLAG
   [If FLAG: Slide(s): N, M. Violation: [exact text]. Fix: [exact instruction].]

   ## Doctrine Point 2: People Buy Promises, Not Products
   [...]

   ## (continue through all 24 points: master 1-18, then department extensions 19-24)

   ## Supplemental Lens Checks
   ### SP-EXPERT (expertise over charisma)
   STATUS: PASS/FLAG
   [If FLAG: Slide(s): N, M. Violation: [exact description]. Fix: [exact instruction].]
   ### SP-LING (linguistic leverage -- order matters)
   STATUS: PASS/FLAG
   [If FLAG: Slides affected. Violation: [which reorder would strengthen conviction and why]. Fix: [exact reorder instruction].]
   ### GP-4 (emotion + logic -- serve both buyers, deck-wide)
   STATUS: PASS/FLAG
   [If FLAG: Identify which track is absent from the offer arc. Fix: [exact instruction].]
   ### GP-10 (appetizer not dinner -- teaching completeness check)
   STATUS: PASS/FLAG
   [If FLAG: Identify the over-taught Secret(s). Fix: [exact instruction for trimming to WHAT+WHY+quick-win].]

   ## Summary
   Total FLAGS: N (doctrine: N, supplemental lens: N)
   Critical FLAGS (severity HIGH): N
   BLOCKING FLAGS (HIGH on fabricated proof or fake scarcity): N
   Recommended action: [PROCEED / REVISE BEFORE PHASE 1A / REVISE BEFORE DELIVERY]
   Run status: [CLEARED TO PROCEED / BLOCKED -- Director must resolve the listed BLOCKING FLAGS before Phase 1A]
   ```
4. Severity classification for each FLAG:
   - HIGH: the violation directly harms the conversion outcome (e.g., hook missing, anchor too low, fabricated proof).
   - MEDIUM: the violation weakens the deck but does not break it (e.g., hook distribution could be improved, one transition is abrupt).
   - LOW: a refinement suggestion (e.g., a stronger word choice for a specific headline).
   - BLOCKING (a property of the flag, not a fourth severity): any HIGH-severity flag on fabricated proof (master point 12 + Section 3.2) or fake/false scarcity (master point 14 + Section 5.4) is also BLOCKING. Tag it `BLOCKING` in the Kill List, count it in the BLOCKING FLAGS line of the Summary, and set Run status to BLOCKED. A blocking flag is never reported as a mere recommendation; the run does not advance until the Director resolves it.
5. After completing the Kill List: write the entry in working/da/review_log.json.
6. Notify the Director with the summary: "DA review complete. [N] flags: [H] HIGH, [M] MEDIUM, [L] LOW; [B] BLOCKING. Recommendation: [PROCEED/REVISE]. Run status: [CLEARED/BLOCKED]." If any BLOCKING flag exists, the message leads with: "RUN BLOCKED: [B] blocking flag(s) on fabricated proof / fake scarcity. The deck cannot advance to Phase 1A until you resolve these."

**Supplemental Lens Checks (run alongside the 24-point doctrine review; these are framework-level lenses drawn from the governing signature-presentation theory and the pitch-intelligence principles, not replacements for any doctrine point):**

- **SP-EXPERT lens (expertise over charisma).** The deck must demonstrate the client's expertise through concrete proof, named systems, and outcome evidence -- not through personality-driven persuasion alone. FLAG any slide that relies entirely on the presenter's charisma or likability without a competence anchor (a named method, a case study, a system, a credential grounded in outcomes). The entry-level offer must be positioned as a buy-in signal on an ascension ladder, not a standalone product. Test: "Would this slide convince a skeptic who finds the presenter personally unlikeable?" If no, flag it.

- **SP-LING lens (linguistic leverage -- order matters).** The sequence of ideas across the deck is a persuasive lever, not a neutral arrangement. FLAG any section where the order of reveals works against conviction: e.g., the offer price revealed before the anchor is planted, the problem stated after the solution, the case study placed before the problem it proves, the hook missing from the open. Slide order and phrasing are consequential; the deck must walk the audience to each conclusion in the order that creates the conviction. Test: "If I re-ordered these slides, would the conviction arc collapse or strengthen?" If reordering would strengthen it, flag the current order.

- **GP-4 lens (emotion buys; logic justifies -- serve BOTH buyers).** This is master doctrine point 5 applied as a deck-wide test, not just a per-slide check. Scan the full offer section: is there a clear emotional track (future-pacing, imagery, aspirational language) AND a clear logical track (math, ROI, cost of inaction, payback timeline)? A deck that only inspires loses the justifier; a deck that only calculates loses the buyer. FLAG the deck if either track is absent from the offer arc. In particular: couples often split the buyer/justifier roles -- the deck must serve the person in the room who will say "but what does this cost us?" as clearly as it serves the person who is already excited.

- **GP-10 lens (appetizer, not dinner -- do not over-teach).** This is master doctrine point 8 applied as a deck-wide completeness test. Count how many "Secrets" or teaching sections hand over the complete HOW. If any Secret gives the audience the full method -- not just the WHAT and WHY and one quick win, but the step-by-step HOW -- flag it. Over-teaching means they feel full before the offer arrives. The test: "After reading this deck, does a viewer feel they have the complete system, or do they feel they understand the value and want the complete system?" If the answer is the former, the teaching is dinner-sized and the offer is unnecessary.

**The 24-Point Pitch Doctrine. Points 1-18 are transcribed VERBATIM from master SOP Section 4.3 (the master is the authority; if this list ever diverges from the master, the master wins and this list is wrong). Points 19-24 are department-specific extensions this role has earned through review experience; they sharpen the master doctrine into testable failure modes and never contradict it.**

**1. THE HOOK DOCTRINE (the Purple Rain rule).** A presentation is written like a song: there is a rhythm, and there is a hook. Most presenters give a 30-minute presentation and say their hook once; this system writes the hook and STANDS it on its own dedicated slides. (NOTE: the historical ">= 7 times" FLOOR has been RETIRED. The live gate is a banded CEILING -- see below.)
- The hook is the strongest part of the promise, the one thing the audience wants most, compressed into one singable line (illustrative examples -- substitute your DISCOVERY VARIABLES: "[PROMISE]. [TIMEFRAME]."; or a contrast line like "There is a difference between parenting by control and parenting through clarity.").
- Phase 1 derives the hook from `BIG_PROMISE` + `OFFER_STACK`, records it as `HOOK` in intake.json, and the owner confirms it at the approval gate.
- **Banded CEILING (the live gate, AF-C2/AF-HOOK-1).** The verbatim hook stands on 3-4 DEDICATED pure-typography A4 slides, total appearances ~4-5 max, NEVER 2 consecutive, and is never a footer on every slide. Over-stamping is the #1 defect; STRIP excess rather than pad. (This REPLACES the RETIRED ">= 7 times" floor that produced the 40-slide footer-stamping. Do not re-introduce a hook floor.)
- The hook lives on 3-4 DEDICATED slides of its own (A4 type-dominant treatment); it is a refrain, not wallpaper.
- **Place it early.** First dedicated occurrence lands inside the first 10 to 15% of the deck, then recurs only at the named dedicated beats, and reprises once into the close -- within the ~4-5 ceiling, never on every slide.
- **Earn it after proof.** When a story or case study proves the point, a dedicated hook slide may follow -- counted within the 3-4 dedicated total, never stamped as a footer on the proof slide itself.
- A strong hook can graduate into the client's signature quote and hashtag. Quote slides carry the client's NAME ONLY, no credentials (the T.D. Jakes rule: we quote the name, not the resume).

**2. PEOPLE BUY PROMISES, NOT PRODUCTS.** They do not buy the product; the product is just a reflection of the promise they want. Every teach and offer slide pitches the PROMISE. If the promise is strong enough, the product sells itself. Phase 1 maintains a running promise inventory: what is this product promising, slide by slide?

**3. THE LOWER THE PRICE, THE GREATER THE VALUE.** Every price drop ADDS something to the table; it never takes anything off. Drop to $1,000 AND stack the Blueprint AND the automation bonus on top. Most people discount by stripping; this system discounts by stacking. Copy QC verifies that every DROP slide or its immediate successor adds new named value.

**4. THE GRADUAL VALUE REVEAL, NOT THE CLICHE.** Never the worn-out "this is worth $25,000 but today only $2." The anchor arrives as an honest question planted mid-teach: "What is a system like this actually worth?" Then the ladder walks down gradually, each rung earned (showed up live, believed, stayed). The audience keeps leaning in because every stretch of staying lowered their price: "wait, I just hung around and got myself to $2,500; what else am I going to get?"

**5. EMOTION BUYS. LOGIC JUSTIFIES.** People buy on emotion and justify with logic, and in couples the two roles usually split: one partner is emotionally ready, the other needs the logical case. The deck must serve BOTH in every offer section: emotionally driven imagery and future-pacing for the heart, and explicit math (LTV, cost of inaction, payback) for the justifier. A deck that only inspires loses the justifier; a deck that only calculates loses the buyer.

**6. COST VERSUS VALUE.** Every pitch explicitly answers two questions: what is the COST of not taking action, and what is the VALUE of taking action? If the offer produces money, do the math on screen (illustrative -- substitute your DISCOVERY VARIABLES: 1 client = $[ANNUAL_VALUE]/yr; 3 = 3x that). If the offer does not produce money, run the PRICELESS PITCH (the American Express frame): hot dog $5, parking $20, the outcome they actually want: priceless. Never fabricate dollar values for non-monetary outcomes; elevate them above money instead.

**7. LIGHT PITCHES, WOVEN.** Do not save the pitch for the end. Softly sing the song of the program throughout: "when you work with us," "inside our program," "when you attend this workshop." Every named piece of the client's methodology (their identity development structure, their guided development system, their frameworks) is a named SYSTEM, and every named system is a light sales point planted inside the teaching.

**8. APPETIZER, NOT DINNER.** Teach enough to prove competence and shift beliefs; never so much that they are full. If you over-teach, they have no reason to buy dinner. Each Secret teaches the WHAT and the WHY and one quick win; the complete HOW lives inside the offer.

**9. PAIN GETS ITS OWN SLIDE.** Each distinct pain point is ONE slide with ONE emotionally driven image; never a bulleted list of four pains on one slide. They have to feel the weight of each one, and a picture is worth a thousand words: the image must make the viewer say "that is exactly how I feel." (Four pain points = four slides, no matter what.)

**10. INTRIGUE SLIDES.** A slide that makes the audience ask a question is a strong slide ("doing the right things, but in the wrong way?" makes you ask: what do you mean, the wrong way?). Plant at least one genuine curiosity gap per section.

**11. COMPARE AND CONTRAST, CONSTANTLY.** Old way vs new way. Control vs clarity. Keep guessing vs build the system. Two-sided slides that show how each path SHOWS UP in real life are the workhorses of belief shift; use them in every Secret and again in the close.

**12. WHO SAYS SO OTHER THAN YOU.** Case studies are not decoration; they are the answer to "who agrees with you besides you?" Proof within two slides of every claim, plus white-paper or research backing where the niche expects it. Named, located testimonials.

**13. TRIPLE ALLITERATION.** Lists of three should alliterate when natural ("confident, consistent, and clear"), and the trio can become formulaic: Confidence + Consistency + Clarity = Effective Guide. When a value trio is part of the pitch, each value word can earn its OWN slide, because each one is being sold.

**14. ALWAYS PITCH SOMETHING.** Even a "free strategy session" webinar pitches a paid something, even if it is $47 or $97. If they are showing up, the event produces revenue and commitment. Free-only closes are not allowed without explicit owner sign-off.

**15. THE SLIDE IS NOT THE SCRIPT.** Never put the words the presenter is going to SAY on the slide. The slide carries the one big idea; the presenter carries the narration; that separation is WHY the audience listens instead of reading ahead. The spoken words live in the PRESENTER NOTE.

**16. EYES MUST MOVE.** Vary the text placement across consecutive slides (bottom band, left block, right block, center punch). Putting the words in the same place every time causes the audience to fade out. The archetype rotation exists to keep their eyes hunting; copy QC flags more than 2 consecutive slides with the same text anchor position.

**17. PREMIUM MEANS PHOTOGRAPHY, NOT EMOJIS.** Icons and emojis cheapen a premium deck. Emotion is carried by photographic imagery and typography, never clipart glyphs.

**18. ROADMAP THE PROGRAM.** When the offer is a challenge or program, lay out the journey on slides: Day 1, Day 2, Day 3; Week 1 through 6; the 90-day plan. Future-pacing the program itself builds excitement and gives the logical justifier their structure.

**Department extensions (points 19-24). These are this role's own testable failure modes, derived from review experience. They extend, never override, the master doctrine above. Where an extension restates a master rule as a sharper test, the master phrasing governs in any conflict.**

**19. The hook is a statement, not a question.** Questions weaken the frame and give the audience an exit ramp. "What if you could enroll clients without chasing them?" is weaker than "You can enroll clients without chasing them." The hook (master point 1) must land as a declarative line the audience can hum, not an open question they can answer "no" to.

**20. The problem is agitated across multiple slides, not mentioned once.** One mention of the problem does not agitate; it informs. Several slides of specific, vivid, one-pain-per-slide framing (master point 9) make the audience feel the weight before any solution arrives. A problem named once and dropped is a FLAG.

**21. No dark-slide creep.** "Dark slides" introduce fear, FUD (fear/uncertainty/doubt), or heavy negativity without immediately offering hope or a path forward. One dark slide can agitate effectively; never allow 3 consecutive fear slides without a slide of hope between them. Agitation that never lifts depresses rather than motivates.

**22. The offer is presented completely before the first DROP.** The audience must know EVERYTHING they are getting before the first price is revealed. A partial offer, then a price, then more offer components, breaks the choreography and the buildup-before-drop logic of master points 3 and 4. The full stack lands before DROP1.

**23. The CTA is specific and singular.** "Go to this link" or "text this keyword to this number" -- one action, stated once clearly, then repeated exactly once. Multiple competing CTAs at the close split intent and reduce conversion. One door, one way through it.

**24. The deck ends on the hook.** The last substantive slide (before any Q&A or thank-you slide) must contain the hook in some form. The audience walks away humming the hook (master point 1), not staring at a generic CTA. A close that drops the hook wastes the refrain the whole deck built.

**Outputs:**
- working/da/kill_list-[DECK_SLUG].md
- working/da/review_log.json (entry added)

**Hand to:** Director of Presentations (Kill List reviewed; Director decides which flags to implement before proceeding)

**Failure mode:** If slides_copy.md is not complete (has [PENDING] placeholders in more than 10% of slides), the DA review cannot be meaningfully completed. Return to the Director: "DA review blocked: [N] slides have incomplete copy (PENDING placeholders). Review can run after placeholders are resolved."

---
