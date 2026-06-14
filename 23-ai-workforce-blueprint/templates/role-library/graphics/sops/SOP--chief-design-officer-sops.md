# SOPs Mirror -- Chief Design Officer (CDO) -- DIU Addendum

**Source:** graphics/chief-design-officer.md
**Extract:** DIU-addendum Section 9 SOPs only (SOP-DIU-612, SOP-DIU-613, SOP-DIU-614). The CDO role file's base SOPs 9.1-9.7 (creative brief intake, production, review, distribution, revision loop, brand emergency, AI-assisted production) are the generic department SOPs and appear in the role file directly. This mirror file carries only the ZHC DIU-specific additions.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.
**Library-version pin:** MASTER-SOP v1.0, MODEL-SPECS v1.0, INDEX.md v1.0, PHOTO-SHOOT-SOP v1.0, PPT-ANALYSIS-SOP v1.0, TEST-PROTOCOL v1.0 (§-refs verified 2026-06-12).

---

## 9. DIU-Specific Standard Operating Procedures (CDO Addendum)

### SOP 9.8 -- [SOP-DIU-612] Cross-Department Style Request Block

**ZHC SOP.** Wraps MASTER-SOP §3.2, §7; category `_RULES.md`; MODEL-SPECS §5; `universal-sops/cross-dept-request-template.md`.
**Library-version pin:** MASTER-SOP v1.0, MODEL-SPECS v1.0 (§-refs verified 2026-06-12).
**When to run:** Any time a department outside graphics (Social Media, Ad Creative, Marketing, Presentations, etc.) submits a request for a DIU-generated asset. This SOP governs every cross-department request that enters the DIU pipeline.
**Frequency:** On-demand, per inbound cross-department request.
**Inputs:** Cross-department request via the standard `universal-sops/cross-dept-request-template.md` with the STYLE block filled.

**Required STYLE block fields (any request missing these fields is returned to the sender before processing begins):**
- `STYLE_ID@version` (or a set of mood keywords for CDO-resolved pick -- if keywords only, the CDO resolves to a confirmed INDEX.md card ID before any generation proceeds)
- `tier` (default MEDIUM if not specified)
- All Workflow-B variable values filled ({SUBJECT}, {HEADLINE_TEXT}, {BRAND_COLOR_1}, etc.)
- `destination_format` (resolves the target category `_RULES.md` for the output asset)
- `likeness_present`: true or false

**Steps:**
1. Receive and validate the cross-department request STYLE block. If `STYLE_ID` is provided but does not resolve in INDEX.md, return the request immediately: "Style ID [X] not found in INDEX.md. Please confirm the correct ID or submit mood keywords for CDO-resolved pick." Never proceed on an unresolved ID.
2. **If `likeness_present: true`:** route the ENTIRE request to the Photo Shoot Director consent gate FIRST before any other processing. No generation assembly packet is built until the Photo Shoot Director returns a consent-verified shoot brief. This closes the cross-department likeness bypass -- a Social Media request with the client's face hits the same gate as a formal photo shoot.
3. If `likeness_present: false` and STYLE_ID is confirmed in INDEX.md at production status: proceed to assembly packet construction.
4. Build the generation assembly packet for the Generation Operator: card ID@version (resolved), all filled Workflow-B variables, tier, destination format, model selection per MODEL-SPECS routing table for the destination category, budget cap.
5. Hand the assembly packet to the Generation Operator. The CDO is the ONLY intake source for cross-department requests -- the Generation Operator does not accept raw cross-department briefs directly.
6. Upon delivery of the verified output: return to the requesting department with: the asset, the generation log (card ID@version, model, tier used), and provenance (ID@version / model / seed) so the department can request exact regenerations later.
7. **Campaign version pinning:** if the requesting department is running a multi-asset campaign, resolve the ID@version at intake and record it in the campaign record. When the card version bumps or is retired, notify all departments with active version pins before the new version becomes default.

**Outputs:** Generation assembly packet to Generation Operator (or shoot brief routing to Photo Shoot Director). Delivered asset + generation log + provenance to requesting department.
**Hand to:** Photo Shoot Director (if `likeness_present: true`); Generation Operator (if `likeness_present: false` and ID resolved).
**Failure mode:** If the requesting department cannot supply a valid STYLE_ID or mood keywords sufficient to resolve to an INDEX entry, return the request and offer to schedule a calibration run (SOP 9.9 / SOP-DIU-613). Never generate from an unresolved style -- guessing a style is the primary library failure mode.

---

### SOP 9.9 -- [SOP-DIU-613] New-Client Calibration Run

**ZHC SOP.** Wraps MASTER-SOP §6; PPT-ANALYSIS-SOP §4; PHOTO-SHOOT-SOP §§1-3; TEST-PROTOCOL (cards reach tested before client sees output).
**Library-version pin:** MASTER-SOP v1.0, PPT-ANALYSIS-SOP v1.0, PHOTO-SHOOT-SOP v1.0, TEST-PROTOCOL v1.0 (§-refs verified 2026-06-12).
**When to run:** When the DIU activates for a new client -- the first structured DIU engagement for any client must go through this SOP. This is the DIU's equivalent of Skill 38's "appointment-booking playbook is always first": identical designed first deliverable on every box.
**Frequency:** Once per client at DIU activation; never skipped.
**Inputs:** Client brand materials (logo, brand colors, existing visual assets), interview notes or brief from the CDO/client onboarding session, client name and box identifier.

**Steps:**
1. **Collect brand materials.** Gather: logo files (vector preferred), brand color codes (hex or RGB), existing visual assets (prior decks, social posts, ad creative -- whatever the client has). If the client has no existing visual assets, proceed to step 2 with a blank-slate brief.
2. **Style Analyst produces 2-3 draft cards.** Brief the Style Analyst to analyze the collected brand materials using Workflow A (MASTER-SOP §§3-4) and produce 2-3 draft style cards. If the client has no existing visual references, request a PPT batch analysis (SOP-DIU-102) using 2-3 competitor or aspirational reference decks the client approves.
3. **Brand variable verification.** Verify all Workflow-B variables ({BRAND_COLOR_1}, {BRAND_COLOR_2}, {LOGO_NOTE}) resolve correctly from the box's brand config file. If the box has no brand config populated, create `_local/BRAND.md` with the verified values before proceeding.
4. **Identity profile + standing consent (if likeness work anticipated).** If the client is likely to request photo-shoot or likeness work: (a) create `personal-photo-shoot/{client-slug}/IDENTITY.md` with the client's physical descriptors and an approved reference image set; (b) initiate the standing self-likeness consent record per SOP-DIU-608 self-likeness fast path (CONSENT.md, status: active, standard scope). This prepares the consent gate for file-read speed on all future likeness requests.
5. **Fidelity Tester review.** All 2-3 draft cards must reach `tested` status (passing the 12-dimension rubric per TEST-PROTOCOL) before the client sees any output. Do not present draft or untested cards to the client.
6. **1K calibration contact sheet.** For each card that reaches tested status: generate a 1K SHORT contact sheet (4 variations, cheapest capable endpoint) using the card and the client's brand variables. This validates key wiring, hosting path, and receipt plumbing per SOP-DIU-602 smoke-test rule.
7. **Client picks favorites.** Present the contact sheets to the client via the CDO. The client selects their favorite(s). Record the selections.
8. **Taste profile seeded.** Write initial entries to `_local/TASTE-PROFILE.md` based on what the client selected (liked dimensions, palette preferences, standing pre-approvals) per SOP-DIU-614 taste-profile mechanics.
9. **Lookbook v1 published.** Trigger SOP-DIU-607 (via Style Analyst) to generate the client's first Lookbook from the winning card(s). Deliver Lookbook v1 to the client as the calibration run deliverable.

**Outputs:** 2-3 tested style cards registered in INDEX.md; brand config verified; identity profile + standing consent (if applicable); 1K contact sheet; initial TASTE-PROFILE.md; Lookbook v1.
**Hand to:** Generation Operator (cards are now available for Workflow B requests); Style Analyst (Lookbook generation trigger); client (Lookbook v1 via CDO).
**Failure mode:** If the client's brand materials are insufficient for card creation (no visual references, no brand colors, no existing assets), do not produce a blank calibration run. Escalate to the client (via the human owner if needed) for a brief intake session before proceeding. Never skip the calibration run -- a client without a calibration run has no library, no taste profile, and no Lookbook, which means every subsequent generation request requires re-intake.

---

### SOP 9.10 -- [SOP-DIU-614] Client Revision Loop & Taste Profile

**ZHC SOP.** Wraps TEST-PROTOCOL §5; MASTER-SOP §7 step 6; NEGATIVE-PROMPTING-SOP §5; PHOTO-SHOOT-SOP §3 (standing-preference pattern generalized).
**Library-version pin:** TEST-PROTOCOL v1.0, MASTER-SOP v1.0, NEGATIVE-PROMPTING-SOP v1.0, PHOTO-SHOOT-SOP v1.0 (§-refs verified 2026-06-12).
**When to run:** On receipt of any client feedback on a DIU-generated deliverable.
**Frequency:** On-demand, per client feedback event.
**Inputs:** Client feedback note (verbatim), the delivered asset, the generation receipt for the asset (card ID@version, model, tier, exact filled prompt, seed, taskId), the client's current `_local/TASTE-PROFILE.md`.

**Steps:**
1. **Classify the client note** into one of three categories:
   - **(a) Defect:** the output has a factual error (wrong name in text, wrong color, wrong aspect ratio, identity drift, text-on-face). Route to Fidelity Tester for diagnosis mode. Do not re-run without a Fidelity Tester finding.
   - **(b) Preference within brief:** the output is technically correct but the client prefers a different aesthetic direction within the style card's latitude (e.g., "I like the composition but want warmer tones"). Re-run with the preference translated into 12-dimension/zone language as a noted deviation. NEVER edit the style card -- the library is law. The re-run note goes to the Generation Operator as a one-time deviation instruction, not a card edit.
   - **(c) Scope change:** the client wants something the card and brief cannot produce (new subject, new mode, new style direction entirely). Treat this as a new brief. Brief the CDO and begin a new request cycle; do not mutate the current deliverable job.
2. **Count revision rounds.** Track how many rounds of type-(b) preference re-runs have been applied to this deliverable (logged in the job directory). If the client has requested more than 3 type-(b) re-runs on the same brief: flag to the CDO with a recommendation to either elevate to type-(c) scope change or create a second style card variant. Do not continue open-ended type-(b) re-runs.
3. **Append every preference to TASTE-PROFILE.md.** At the moment any client preference is expressed (on delivery, on revision, on casual feedback): append it immediately to `_local/TASTE-PROFILE.md` with the date, the asset context, and the expressed preference or aversion. Format:
   ```
   [DATE] liked: {dimension or element} (context: {brief/asset identifier})
   [DATE] disliked: {dimension or element} (context: {brief/asset identifier})
   [DATE] pre-approved: {standing element, e.g., "always use deep navy base"} (confirmed by owner)
   ```
4. **Taste-profile discipline rules:**
   - Taste-profile entries are disk-persisted ONLY -- never chat-only, never in the session memory alone. They must survive session limits.
   - Entries are append-only and never edited or pruned without CDO authorization.
   - Standing pre-approvals (e.g., "always include the logo in the bottom-right zone") function as non-negotiable preflight checks for this client's future jobs once confirmed by the owner.
   - The taste profile compounds over time: after 5+ entries, patterns should be surfaced to the client as candidate additions to their NAMED-STYLES.md brand overrides.
5. **Pre-fill from taste profile on new briefs.** When the CDO assembles a new brief for this client, read `_local/TASTE-PROFILE.md` first and pre-fill any standing pre-approvals into the assembly packet variables. This prevents re-expressing preferences the client has already declared.

**Outputs:** Classification verdict (defect / preference / scope change); re-run instruction to Generation Operator (for type-b); new brief trigger (for type-c); TASTE-PROFILE.md updated.
**Hand to:** Fidelity Tester (type-a defect); Generation Operator (type-b re-run with deviation note); CDO new-brief intake (type-c scope change).
**Failure mode:** If TASTE-PROFILE.md cannot be written to disk (permissions error, file missing), create it immediately before the session ends. A preference lost because the file didn't exist is the same failure as a preference expressed to an agent that forgets everything on session close. The taste profile is the institutional memory for this client's aesthetics -- its absence means every future brief starts from zero.

---

---

### SOP 9.11 -- DIU Webinar-vs-DIU Routing Arbiter (Coded Decision Gate)

**ZHC SOP.** Routing arbiter for ambiguous webinar/audience deck vs. DIU pipeline decisions.
**Library-version pin:** CLIENT-WEBINAR-DECK-SOP v2.3, SOP-DIU-611 v1.1, powerpoint-designs/_RULES.md v1.0 (§-refs verified 2026-06-13).
**When to run:** Any time a deck brief is ambiguous between the DIU pipeline and the Presentations pipeline.
**Frequency:** On-demand; every ambiguous deck escalation must route through this SOP before any generation begins.
**Inputs:** Deck brief from the Deck Systems Specialist (or escalation notice), the brief's stated purpose/audience/context.

**ROUTING ARBITER DECISION TABLE:**

| Condition in the brief | Routing verdict |
|---|---|
| Brief names "webinar," "funnel," "virtual event," or "audience presentation" | Presentations dept - CLIENT-WEBINAR-DECK-SOP |
| Brief shows a REPRESENTATION_MIX or specific audience composition | Presentations dept |
| Brief specifies one of the five CLIENT-WEBINAR-DECK-SOP archetypes | Presentations dept |
| Brief is a brand/strategy/campaign deck with a specific DIU style card ID in INDEX.md | DIU pipeline |
| Brief is for internal use only, no live audience delivery | DIU pipeline |
| Brief does not fit any row above | Escalate to Director of Presentations; halt all generation |

**Steps:**
1. Apply the decision table. Document the matching row and deliver the routing decision in writing.
2. For Presentations-routed decks: forward the brief to the Director of Presentations.
3. For DIU-routed decks: confirm to Deck Systems Specialist and authorize manifest assembly; record verdict + date.
4. For escalations: forward full brief + decision-table analysis to Director of Presentations; no generation until written verdict received.
5. If DIU routing is disputed after generation begins: halt immediately. CDO is final arbiter.

**Outputs:** Routing verdict with documented decision-table row; Director of Presentations' written arbiter decision on record (for escalations).
**Hand to:** Deck Systems Specialist (DIU route) or Director of Presentations (Presentations route).
**Failure mode:** If deck incorrectly routed to DIU and generation has begun, halt immediately. Log root cause and implement corrective measure.

---

*DIU SOPs owned: [SOP-DIU-612], [SOP-DIU-613], [SOP-DIU-614], [routing-arbiter-9.11]. These are addendum SOPs (9.8, 9.9, 9.10, 9.11) appended to the CDO's existing 9.1-9.7 base SOPs. Total CDO sop_count: 11.*
