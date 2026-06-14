# SOPs Mirror -- Style Analyst ("The Eye") -- DIU

**Source:** graphics/style-analyst.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.
**Library-version pin:** MASTER-SOP v1.0, STYLE-CARD-TEMPLATE v1.0, PPT-ANALYSIS-SOP v1.0, MODEL-SPECS v1.0, INDEX.md v1.0, NEGATIVE-PROMPTING-SOP v1.0 (§-refs verified 2026-06-12).

---

## 9. Standard Operating Procedures (Numbered)

### SOP 9.1 -- [SOP-DIU-101] Style Analysis & Card Creation (Vendor Workflow A)

**Vendor SOP.** Wraps MASTER-SOP §§3-4; STYLE-CARD-TEMPLATE.md (full); PPT-ANALYSIS-SOP §2 (for deck-sourced references).
**Library-version pin:** MASTER-SOP v1.0, STYLE-CARD-TEMPLATE v1.0 (§-refs verified 2026-06-12).
**When to run:** A new style reference (image, mood board, reference deck excerpt, brand collateral) arrives from the CDO or Brainstorming Buddy for analysis and card creation.
**Frequency:** On-demand; primary daily work function.

**Steps:**
1. Receive the reference material and the brief: what category, what client, what intended use. If any field is missing, return to the CDO with a specific question list before beginning.
2. **Dedupe pre-check.** Embed a 2-3 sentence description of the reference's dominant mood, palette, and style and query the semantic index (SOP-DIU-606). Record the top-3 similarity scores. If any score >= 0.92, HALT and surface to the CDO: "This reference closely resembles [CARD-ID]. Should I version the existing card or proceed with a new card?" Do not proceed without a written decision.
3. **Provenance classification.** Classify the source: client-owned, licensed (record license scope), or third-party-style-only (style analysis permitted; near-verbatim reproduction prohibited). If the reference depicts a real person's face or likeness, HALT and notify the CDO + Photo Shoot Director -- the PHOTO-SHOOT-SOP §1 consent gate must run BEFORE the card enters draft.
4. **Execute Workflow A analysis per MASTER-SOP §§3-4.** Fill every section of STYLE-CARD-TEMPLATE.md. No section may be left blank or marked "TBD" in a submitted draft.

   **REPRESENTATION-MIX SCHEMA FIELD (required for any card involving people):** When the client's brief or intake record includes a REPRESENTATION_MIX value (the captured audience composition with percentages), record it in the card's Model Notes section under the key `representation_mix`. Format: `representation_mix: {gender: "...", ethnicity: "...", notes: "..."}`. If no REPRESENTATION_MIX has been captured and the card is for an audience/webinar context, add a flag: `representation_mix: UNCAPTURED - NO PEOPLE default until intake is completed`. For webinar and audience decks: casting and representation is owned by the Presentations pipeline QC. The DIU style card governs the visual aesthetic only.
5. **Count actual prompt characters.** For each prompt tier block in the card, count the actual character length and write it explicitly in the card's character-count annotation line. Do not estimate. Seedream hard cap is 3,000 characters; flag any tier that exceeds 2,800 characters with a warning.
6. **Set card status = "draft."** Emit a per-card receipt file: `{CARD-ID}.json` containing id, name, category, status, version, authored-by, authored-date, similarity-scores-at-creation, provenance-class.
7. **Hand to Fidelity Tester** with: the draft card file path, the receipt file path, the reference images path, and a one-line handoff note specifying the intended test category and any flags from steps 2-3.

**Outputs:** Completed draft style card in STYLE-CARD-TEMPLATE format; per-card receipt file; handoff note to Fidelity Tester.
**Hand to:** Fidelity Tester (test run + promotion to "tested" status).
**Failure mode:** If after 2 analysis attempts the reference material is too low-resolution, too stylistically ambiguous, or too legally ambiguous to produce a complete card, escalate to the CDO with a written diagnosis rather than submitting an incomplete card.

---

### SOP 9.2 -- [SOP-DIU-102] Batch & Multi-Style Clustering from Deck Sources

**Vendor SOP.** Wraps PPT-ANALYSIS-SOP §§2, 4; MASTER-SOP §§3-4; STYLE-CARD-TEMPLATE.md.
**Library-version pin:** PPT-ANALYSIS-SOP v1.0, MASTER-SOP v1.0 (§-refs verified 2026-06-12).
**When to run:** A multi-slide PowerPoint or deck-format reference source arrives requiring style system extraction rather than single-card analysis.
**Frequency:** On-demand; typically 1-3 times per month per client.

**Steps:**
1. Receive the deck and the brief. Confirm: How many distinct style families are expected? Is this deck from the client (client-owned provenance) or a competitor/reference source (third-party-style-only provenance)?
2. **Run PPT-ANALYSIS-SOP §2 clustering pass.** Group slides by visual family. Identify 1-N distinct style clusters. Do not proceed to individual card authoring until the cluster map has been reviewed with the CDO.
3. **Dedupe pre-check per cluster.** Run SOP 9.1 step 2 for each identified cluster before assigning IDs. Record similarity scores per cluster.
4. **Author individual cards per cluster** following SOP 9.1 steps 4-7 for each non-duplicate cluster.
5. **Per PPT-ANALYSIS-SOP §4:** when sibling styles emerge from the same deck, add cross-reference links in each card's Model Notes.
6. **Batch receipt files.** Emit one receipt file per card as in SOP 9.1 step 6. Also emit a batch-level summary receipt: `{BATCH-ID}-batch.json` listing all card IDs produced, the source deck path, and the cluster similarity scores.

**Outputs:** 1-N completed draft style cards; N individual receipt files; one batch-level receipt; CDO cluster-map confirmation record.
**Hand to:** Fidelity Tester (each card individually via SOP 9.1 step 7); batch receipt to CDO.
**Failure mode:** If deck source contains fewer than 5 slides per cluster, flag the affected cluster to the CDO as "insufficient signal -- recommend collecting additional reference slides before authoring."

---

### SOP 9.3 -- [SOP-DIU-502] Library Governance & Versioning (Registrar Duty -- Dormant Until > 50 Cards)

**Vendor SOP (Registrar Duty).** Wraps MASTER-SOP §8 (library versioning and card lifecycle); MODEL-SPECS §6 (new-model and deprecation protocol); INDEX.md (registration rules, retire-never-delete rule); NEGATIVE-PROMPTING-SOP §5 (quarterly avoid-list pruning schedule).
**Library-version pin:** MASTER-SOP v1.0, MODEL-SPECS v1.0, NEGATIVE-PROMPTING-SOP v1.0 (§-refs verified 2026-06-12).
**When to run:** (a) Any card progresses from "tested" to "production" status; (b) any card requires a version bump following a Fidelity Tester-approved prompt patch; (c) the Healer-Graphics SOP-DIU-615 sweep flags an INDEX integrity issue; (d) a vendor library file update requires re-pinning thin-wrapper SOPs.
**Frequency:** On-demand; triggered by card lifecycle events and Healer sweep results.
**Note:** This SOP captures the vendor's Library Registrar duty (Role 6, vendor DEPARTMENT-BUILD-BRIEF §3). It is executed by the Style Analyst until INDEX.md production card count reaches >= 50, at which point the CDO activates the Library Registrar as a standalone role.

**Steps -- Card Registration at "tested" promotion:**
1. Receive the Fidelity Tester's promotion notification: card ID, new status = "tested," updated card file path, test log file path.
2. Verify the per-card receipt file exists and is current. If not present, emit it now from the card data before proceeding.
3. Write the INDEX.md row: ID, name, category, status = "tested," version, source summary, file path, test-log path, embedding-last-run date (set to today after step 4).
4. Embed the card per SOP 9.4 (SOP-DIU-606): compute the embedding from the card's one-line summary + mood keywords + palette descriptors. Record the embedding checksum in the receipt file.
5. **Increment the Registrar counter.** Record the new count in the INDEX.md summary row.
6. **If counter >= 50:** Immediately raise a CDO activation ticket: "Library Registrar activation threshold reached (N tested+production cards). Per SOP-DIU-606 step 9, the Library Registrar role is eligible for activation. Please schedule the `add-role.sh --dept graphics --role 'Library Registrar'` run and confirm INDEX write ownership transfer."

**Steps -- Card Version Bump:**
1. Receive the Fidelity Tester's patch approval: card ID, old version, new version, change description.
2. Update the card file version number and Changelog section per MASTER-SOP §8.
3. Re-embed the updated card per SOP 9.4 (dedupe check is NOT required on version bumps -- same card lineage).
4. Update the INDEX.md row: version field, embedding-last-run date.
5. Check NAMED-STYLES.md for any alias pinned to this card ID. If an alias pins at a version older than the bump, apply SOP-DIU-607 version-advance logic: v1.x patches auto-advance; v2.0 re-analyses require a CDO confirmation + Fidelity Tester side-by-side regression render before the alias pointer moves.

**Outputs:** Updated INDEX.md row; updated receipt file; updated embedding entry; version bump applied to card Changelog; alias advance notifications where applicable; Registrar activation ticket if threshold reached.
**Hand to:** CDO (for activation ticket if threshold reached); Fidelity Tester (for regression render if alias v2.0 advance pending).
**Failure mode:** If INDEX.md write conflicts with a concurrent write attempt, abort the second write, emit both per-card receipt files, and execute a single compiled INDEX write from both receipts. Never proceed with a merged append that could lose one receipt's data. Notify CDO of the collision.

---

### SOP 9.4 -- [SOP-DIU-606] Semantic Style Retrieval & Dedupe Index

**ZHC SOP.** Wraps INDEX.md (registration protocol and authority rule); STYLE-CARD-TEMPLATE.md (summary, mood keywords, and palette fields); MASTER-SOP §6 steps 6-7 (card registration in Workflow A context).
**Library-version pin:** MASTER-SOP v1.0, STYLE-CARD-TEMPLATE v1.0, INDEX.md v1.0 (§-refs verified 2026-06-12).
**When to run:** (a) A new card is registered (embed on registration); (b) a card version bumps (re-embed); (c) a style lookup request arrives; (d) the embedding index coverage check fails (coverage != card count).
**Frequency:** On registration/version-bump events; on-demand for queries; weekly coverage check.

**Steps -- Embedding a Card:**
1. Extract the embed payload from the card: one-line summary (STYLE-CARD-TEMPLATE §1 Summary field) + mood keyword list (§11 Mood/Energy Keywords field) + palette descriptors (§4 Color Palette table, "Palette Notes" column text). Concatenate into a single text block (target: 200-600 characters).
2. If a stored source thumbnail or winning test image is available on disk, include it as the multimodal input to gemini-embedding-2. If not, text-only embedding is acceptable.
3. Call gemini-embedding-2 @3072 with the text (and optional image). Record: embedding vector, checksum (sha256 of the vector bytes), model ID, dimensions, run date. NEVER use gemini-embedding-001 (hard shutdown 2026-07-14).
4. Store the embedding entry: key = card ID, value = {vector, checksum, model-id, dims, run-date, card-version}. Update the index manifest's coverage count.

**Steps -- Dedupe Gate (new card pre-registration):**
1. Compute the candidate card's embed payload as in step 1 above.
2. Query the index for top-5 nearest neighbors.
3. **Score thresholds:**
   - >= 0.92 cosine similarity: HALT registration. Flag to CDO: "Candidate card resembles [CARD-ID] (similarity: X.XX). Please decide: merge into existing card (version bump), register as sibling with cross-links, or proceed as independent card with documented rationale."
   - 0.80-0.91: Register with mandatory sibling cross-links added to both cards' Model Notes. Record the similarity score and the sibling card IDs in the new card's receipt file.
   - < 0.80: Proceed to registration without flags.

**Steps -- Style Lookup (query):**
1. Receive the lookup request: a text description or an attached image.
2. Compute the embed payload from the request text or image.
3. Query the index for top-3 nearest neighbors. Production cards only by default (exclude draft and retired vectors unless the query explicitly requests history).
4. Return the shortlist to the CDO (or requesting role) as: [{card-id, card-name, similarity-score, status}]. Label clearly: "These are retrieval suggestions -- INDEX.md is the authority. No generation should fire from this list without an INDEX-verified card ID confirmed by the CDO."

**Outputs:** Embedding entries (on registration/re-embed); dedupe verdict with similarity scores (on new card gate); lookup shortlist (on query).
**Hand to:** CDO (for dedupe decisions and lookup confirmations); INDEX registration (SOP 9.3) after dedupe clears.
**Failure mode:** If the gemini-embedding-2 API is unavailable, queue the embed for retry at next scheduled run. Do not block card registration -- register the card in INDEX.md and mark "embedding: PENDING" in the receipt file. The Healer-Graphics SOP-DIU-615 sweep will detect and surface pending embeddings.

---

### SOP 9.5 -- [SOP-DIU-607] Named Styles, Client Aliases & Lookbook

**ZHC SOP.** Wraps MASTER-SOP §3.2 (variable system and brand overrides); MASTER-SOP §7 step 6 (Workflow B generation contract); STYLE-CARD-TEMPLATE Changelog section (version events for alias-advance rules); INDEX.md (status authority for Lookbook filtering).
**Library-version pin:** MASTER-SOP v1.0, STYLE-CARD-TEMPLATE v1.0, INDEX.md v1.0 (§-refs verified 2026-06-12).
**When to run:** (a) A client approves a delivered asset and assigns a name to the style; (b) a named-style alias must advance because the underlying card was version-bumped; (c) the monthly Lookbook update is due; (d) a client requests a "what styles do we have?" summary.
**Frequency:** On-demand for alias creation/advance; monthly for Lookbook.

**Steps -- Alias Creation:**
1. Receive the alias-creation trigger from the CDO: client name, style name, the card ID being named, the client-approved winning image file path, any brand overrides.
2. Write the alias entry in the client's NAMED-STYLES.md: {alias-name -> card-id @ current-version, frozen-reference-image-path, brand-overrides object, created-date, approved-by}.
3. Record in the card's STYLE-CARD-TEMPLATE Changelog section: "Named alias '[ALIAS-NAME]' created for client [CLIENT] at v[VERSION], [DATE]."
4. Update the per-card receipt file: add `aliases: [{client, alias-name, created-date}]` entry.

**Steps -- Alias Version Advance (triggered by SOP 9.3 step 5):**
1. Check the version bump type:
   - **v1.x prompt patch:** Auto-advance the alias pointer to the new card version. Update NAMED-STYLES.md entry version field. No CDO confirmation required. Log: "Alias auto-advanced to v[NEW] (prompt patch -- within v1.x lineage)."
   - **v2.0 re-analysis:** HALT auto-advance. Notify CDO: "Card [ID] reached v2.0. Alias '[ALIAS]' for client [CLIENT] is pinned at v[OLD]. A side-by-side regression render is required before the alias pointer moves. Please confirm with the Fidelity Tester." Do not advance the alias until CDO provides written confirmation + Fidelity Tester regression pass.

**Steps -- Monthly Lookbook Update:**
1. Filter INDEX.md for the client's cards with status = "production" only (exclude draft, tested, retired from the client-facing Lookbook).
2. For each production card with an active alias in NAMED-STYLES.md: include the alias name, the card's one-line summary, and the winning test image thumbnail.
3. For production cards without an alias: include the card ID, category, and one-line summary as an "unnamed style."
4. Compile into the client's `_local/LOOKBOOK.md`. Send to CDO for delivery to the client.

**Outputs:** NAMED-STYLES.md entries (on alias creation/advance); updated card Changelog entries; monthly Lookbook document.
**Hand to:** CDO (Lookbook delivery; v2.0 alias advance confirmation gate); Fidelity Tester (for v2.0 regression render request).
**Failure mode:** If a client's NAMED-STYLES.md references a card ID that does not appear in INDEX.md (orphaned alias), flag to the CDO immediately with: which alias is orphaned, which card ID it pointed to, and whether the card was retired or never registered. Never silently serve a generation from an orphaned alias.

---

*SOPs owned: [SOP-DIU-101], [SOP-DIU-102], [SOP-DIU-502], [SOP-DIU-606], [SOP-DIU-607]. sop_count: 5.*
