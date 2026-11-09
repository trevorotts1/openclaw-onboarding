# SOPs Mirror -- Photo Shoot Director ("The Director") -- DIU

**Source:** graphics/photo-shoot-director.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.
**Library-version pin:** PHOTO-SHOOT-SOP v1.0, MODEL-SPECS v1.0, NEGATIVE-PROMPTING-SOP v1.0, IDENTITY.md v1.0 (§-refs verified 2026-06-12).

---

## 9. Standard Operating Procedures (Numbered)

### SOP 9.1 -- [SOP-DIU-401a] Consent & Identity Verification (Vendor Wrapper)

**Vendor SOP.** Wraps PHOTO-SHOOT-SOP §§1-3.
**Library-version pin:** PHOTO-SHOOT-SOP v1.0 (§-refs verified 2026-06-12).
**When to run:** Any inbound request that involves a real person's likeness -- including requests routed from Social Media, Ad Creative, Presentations, or any other department via the CDO's cross-department intake gate (SOP-DIU-612).
**Frequency:** Every shoot brief, no exceptions.
**Inputs:** Shoot request (client name / subject name, shoot mode(s) requested, reference images or reference-image path, intended use channel and commercial/internal flag).

**Steps:**
1. Look up the subject's CONSENT.md at `personal-photo-shoot/{client-slug}/CONSENT.md`. If the file does not exist, the shoot cannot proceed -- create a new `pending` record and route to producer for consent collection. Do NOT proceed to generation. Then run the coded gate `python3 45-design-intelligence-library/scripts/diu_validator.py consent-check --consent-file personal-photo-shoot/{client-slug}/CONSENT.md`; exit 4 (`AF-DIU-CONSENT`) means STOP, fail closed. It reads only CONSENT.md, never IDENTITY.md.
2. Check consent status machine: must be `active`. If `expired` or `revoked`, halt immediately; notify producer and subject (via producer). If `pending`, halt; notify producer that consent collection is outstanding.
3. Verify scope coverage: does the active consent record cover (a) the requested shoot modes (A-F), (b) the intended commercial/internal use, and (c) the distribution channels listed in the brief? Mode F (Stylized / Cartoon) requires explicit opt-in -- confirm `F` is in `modes_approved`.
4. MINORS HARD BLOCK: if any subject in the brief is under 18, STOP. This is an unconditional hard block. Route to producer with a clear statement: "Minor likeness -- hard block, cannot proceed." No exceptions, no workarounds.
5. Run the who-appears inventory on every reference image provided: identify every recognizable person in each image. For any other recognizable person visible in a reference image, halt and resolve: either crop/exclude the face from the reference or obtain an independent release. Log the inventory result in the shoot record.
6. Confirm the sourcing hierarchy (PHOTO-SHOOT-SOP §2) is satisfied: references come from approved paths (the client's design library identity folder, client-provided uploads via GHL media library) -- never from public web searches or unvetted media library folders.
7. Record the gate outcome in the shoot brief header: `consent_verified: true`, `modes_approved: [list]`, `inventory_complete: true`, `gate_date: {date}`, `gate_by: {role-slug}`.

**Outputs:** Consent-verified shoot brief (gate header filled) or a documented halt with reason code and producer notification.
**Hand to:** If gate passes -> SOP 9.2 (Identity Lock Block assembly). If halt -> Chief Design Officer with the halt reason and required resolution.
**Failure mode:** If consent status cannot be read (file missing, YAML parse error, ambiguous scope field), treat as `not-active` and halt. Never infer consent from memory or chat history. Fix the record before proceeding.

---

### SOP 9.2 -- [SOP-DIU-401b] Identity Lock Block & Shoot Modes A-F (Vendor Wrapper)

**Vendor SOP.** Wraps PHOTO-SHOOT-SOP §§4-5.
**Library-version pin:** PHOTO-SHOOT-SOP v1.0 (§-refs verified 2026-06-12).
**When to run:** Immediately after SOP 9.1 consent gate passes.
**Frequency:** Every shoot brief that clears the consent gate.
**Inputs:** Consent-verified shoot brief, the client's IDENTITY.md profile, the relevant category `_RULES.md`, the shoot mode(s) approved in consent scope.

**Steps:**
1. Open `personal-photo-shoot/{client-slug}/IDENTITY.md`. Confirm the reference-image set listed is current and hosted correctly (see SOP 9.5 / SOP-DIU-609 for hosting mechanics).
2. Assemble the Identity Lock Block per PHOTO-SHOOT-SOP §4: exact physical descriptors drawn from the IDENTITY.md profile, framed as hard constraints. The block must be present verbatim in every generation prompt for this shoot. Do NOT summarize or paraphrase.
3. Add the universal Identity Lock Block clause: `"Do not render any other recognizable real person in the scene."` This clause is mandatory on every block, regardless of mode.
4. Select the Mode-appropriate workflow per PHOTO-SHOOT-SOP §5:
   - Mode A (Location): Identity Lock Block + setting/background descriptors (a studio headshot is a Mode A setting), NB2 or GPT-Image-2.5 I2I per the PHOTO-SHOOT-SOP §5 table and the MODEL-SPECS routing table.
   - Mode B (Wardrobe): Identity Lock Block + clothing descriptors; Seedream 4.5 Edit on an existing photo, NB2 for a new scene.
   - Mode C (Action & Pose): Identity Lock Block + body-position/activity descriptors, NB2 or GPT-Image-2.5 I2I.
   - Mode D (Editorial / Lifestyle): Identity Lock Block + the style card prompt with {SUBJECT} = the identity-locked client, brand foundation block (from box brand config), GPT-Image-2.5 I2I (refs + LONG style spec). Contact sheets are a workflow step, not a mode: generate 3-4 draft variants per concept at 1K first (PHOTO-SHOOT-SOP §8 step 3), then the producer selects winners.
   - Mode E (Slide Integration): Identity Lock Block, text-clear-zone framing and the deck's foundation style block, coordinate with Deck Systems Specialist for slide composition specs.
   - Mode F (Stylized / Cartoon): Identity Lock Block + stylized descriptors (NO named-artist or named-studio references); requires explicit consent opt-in confirmed in SOP 9.1.
   - Mode G (Retouch) is SOP 9.3.
5. Compile the full shoot prompt: Identity Lock Block + mode-appropriate context + category `_RULES.md` applicable constraints + negative prompt (assembled per NEGATIVE-PROMPTING-SOP layer merge, plus the universal Identity Lock negative: no other recognizable real persons).
6. Fill all Workflow-B variables ({SUBJECT_NAME}, {SETTING}, {MOOD}, {BRAND_COLOR_1}/{BRAND_COLOR_2} if applicable, {LOGO_NOTE} if applicable). Zero unfilled `{VARIABLE}` tokens may remain in the compiled prompt -- SOP-DIU-601 preflight will hard-fail any unfilled tokens.
7. Confirm endpoint assignment, aspect ratio, resolution tier, and all required params per MODEL-SPECS §5 JSON template for the selected mode's endpoint.

**Outputs:** Complete, Identity-Lock-annotated shoot brief ready to pass to the Generation Operator -- prompt, endpoint, params, reference image URLs (hosting verified per SOP 9.5), mode record, all fields filled.
**Hand to:** Generation Operator for execution via standard handoff.
**Failure mode:** If IDENTITY.md is missing or stale, halt and update the profile before proceeding. If a Mode-appropriate routing assignment is ambiguous due to a MODEL-SPECS change, escalate to the Chief Design Officer -- never guess the endpoint.

---

### SOP 9.3 -- [SOP-DIU-402] Retouching & Surgical Editing (Vendor Wrapper)

**Vendor SOP.** Wraps PHOTO-SHOOT-SOP §6; MODEL-SPECS editing hierarchy.
**Library-version pin:** PHOTO-SHOOT-SOP v1.0, MODEL-SPECS v1.0 (§-refs verified 2026-06-12).
**When to run:** When a completed generation requires retouching, or when a standalone retouching brief arrives.
**Frequency:** Multiple times per week for active photo-shoot clients; on-demand for surgical editing requests.
**Inputs:** Source image (generation output or client-provided photo), retouching brief (specifying requested edits from PHOTO-SHOOT-SOP §6 catalog), consent record confirming retouching scope.

**Steps:**
1. Check that retouching scope is covered in the client's active consent record (the `retouch_boundaries` field of the SOP-DIU-608 consent record). If the requested edit falls outside the consented retouch scope, halt and notify producer.
2. Classify the edit type per PHOTO-SHOOT-SOP §6 retouching catalog. Apply matter-of-factly and without judgment. The catalog governs; if an edit type is not in the catalog, escalate to producer before proceeding.
3. Apply the MODEL-SPECS editing hierarchy for AI-assisted retouching: select the appropriate editing endpoint and tier for the classified edit type. The Generation Operator executes the Kie.ai call.
4. Review the retouched output: verify the edit was applied correctly, no new artifacts introduced, Identity Lock integrity maintained.
5. If retouch outputs for commercial delivery, apply channel x jurisdiction synthetic-media disclosure per SOP-DIU-610.
6. Log the retouching session in the shoot record with: edit type, endpoint used, prompt hash, output asset path, disclosure applied y/n.

**Outputs:** Retouched image with disclosure flag applied if required; shoot record updated.
**Hand to:** Chief Design Officer for delivery; Rights Manifest entry appended per SOP 9.6.
**Failure mode:** If retouched output fails Identity Lock integrity check, quarantine the output and re-route. Never deliver an output where the identity has drifted.

---

### SOP 9.4 -- [SOP-DIU-608] Likeness Consent Lifecycle & Restricted-Content Gate

**ZHC SOP.** Wraps PHOTO-SHOOT-SOP §§1-3, §6; personal-photo-shoot/_RULES.md; IDENTITY.md §3.
**Library-version pin:** PHOTO-SHOOT-SOP v1.0, IDENTITY.md v1.0 (§-refs verified 2026-06-12).
**When to run:** (1) At new client onboarding when identity-locked work is anticipated -- create the standing self-likeness release. (2) When SOP 9.1 finds a non-`active` consent record. (3) When an out-of-scope mode is requested on an existing active record. (4) Quarterly, as part of the consent registry audit.
**Frequency:** Onboarding once; then as triggered by the status machine events above.
**Inputs:** Client identity information, intended shoot modes, commercial/internal use, distribution channels, term/expiry preference.

**Steps:**
1. Create or update `personal-photo-shoot/{client-slug}/CONSENT.md` using the machine-readable YAML front-matter schema defined in SOP-DIU-608 (the schema lives in that SOP; there is no separate template file). Fields required: `client_slug`, `subject_name`, `created`, `updated`, `status` (one of: none / pending / active / expired / revoked), `modes_approved` (subset of A-F; `F` only by explicit opt-in), `use_class`, `channels`, `term_months`, `expiry_date`, `standing_release`, `minors`, `adult_attested`, `storage_protection`, `retouch_boundaries`, and the append-only `revision_log` and `revocation_log`.
2. MINORS: The `minors` field in the schema is fixed at `hard_block` and is never overridden; `adult_attested: true` is set only after the subject is attested an adult. If a brief involves a minor, the record cannot be created with any non-block status. Full stop.
3. Self-likeness fast path (standing release at onboarding): for a client consenting to their own image, create with `status: active`, full standard scope (Modes A-D as default, Mode F only if client opts in explicitly), standard commercial/internal use, channels as specified. This record is a file-read gate on all subsequent requests -- no human loop required for in-scope modes.
4. Restricted-Content Gate (three-verdict matrix): before any generation proceeds, evaluate the brief against the current Restricted-Content Matrix (the three-verdict table in SOP-DIU-608):
   - **BLOCK:** sexualized real-person likeness not consented, any minor likeness, non-consented real people generated recognizably in scene, deceptive news/political framing, fabricated endorsements. HARD STOP -- no escalation path.
   - **ESCALATE-to-producer:** consented adult client's boudoir/swimwear brand shoot; before/after body-transformation creative; regulated verticals (health claims, finance, alcohol/CBD/supplements).
   - **ALLOW-with-conditions:** body-retouch deliverables for commercial print (flag for retouching-disclosure jurisdictions); standard identity-locked generations within active consent scope.
5. Log the gate outcome in the shoot brief and in the consent record's `revision_log` (append only -- never edit prior log entries).
6. Revocation procedure: if `status` is set to `revoked` (by producer or subject request), immediately halt all in-progress generations for this subject, write a purge task to the shoot record (remove hosted reference URLs, flag manifest entries as `revoked`), and notify the producer for client communication. Revoked records are never deleted -- status machine is append-only.

**Outputs:** `active` CONSENT.md record (fast path) or escalation/halt with reason documented.
**Hand to:** If active: proceed to SOP 9.1 gate read on the next request. If escalated: Chief Design Officer for producer sign-off. If blocked: Chief Design Officer immediately.
**Failure mode:** If a consent record is ambiguous (scope field missing a mode, expiry date in the past, status field not one of the defined machine states), treat as NOT active and halt. Ambiguity is not consent. Resolve the record before proceeding.

---

### SOP 9.5 -- [SOP-DIU-609] Reference & Identity Media Hosting

**ZHC SOP.** Wraps MODEL-SPECS §1, §5.2/5.3/5.5; PHOTO-SHOOT-SOP §2.
**Library-version pin:** MODEL-SPECS v1.0, PHOTO-SHOOT-SOP v1.0 (§-refs verified 2026-06-12).
**When to run:** Every time a shoot brief requires reference images to be fetchable by the Kie.ai API. Mandatory for all identity-locked work.
**Frequency:** Every shoot brief that references client identity images.
**Inputs:** The reference image set listed in IDENTITY.md (or new images provided by the client for this specific shoot), MODEL-SPECS endpoint size/format limits for the target endpoint.

**Steps:**
1. Validate each reference image against the target endpoint's format and size limits: the live schema (`kie_live_adapter.py validate`) is the limits authority (rule 5 of `07-kie-setup/references/kie-common-rules.md`) and MODEL-SPECS §1/§5 is its dated snapshot; do not write megabyte values into the brief. Reject and request a replacement for any reference that exceeds the limit or is in an unsupported format.
2. For any real-person likeness reference (identity photos, client headshots): the ONLY permitted hosting path is the client's GHL media library for that client's GHL location. Public ImgBB or any other public-permanent hosting is PROHIBITED for identity reference images.
3. Upload the validated reference images to the client's GHL media library. Record the upload receipts (URLs + upload timestamp) in the shoot record.
4. Verify each URL fetches correctly: perform a URL-liveness check (HTTP HEAD or GET returning 200 with the expected content-type) before including it in the shoot brief.
5. Include the verified hosting URLs in the shoot brief handed to the Generation Operator.
6. After the Generation Operator confirms job completion and the Render Dispatcher's SOP-DIU-601 postflight has verified the asset is downloaded to local storage: you (not the Generation Operator) delete the remote reference images from GHL media using the recorded `ghl_media_id`. Record deletion confirmation in the shoot record and `hosted-refs.json`.
7. Log the full hosting lifecycle (upload -> URL verification -> use -> deletion) in the shoot record.

**Outputs:** Shoot brief with verified reference image URLs; shoot record updated with hosting lifecycle log.
**Hand to:** Generation Operator (shoot brief with live URLs).
**Failure mode:** If deletion cannot be confirmed after job completion (GHL API error, URL still live 24h post-delivery), escalate to the Chief Design Officer. Do NOT mark the shoot as fully closed until deletion is confirmed or the reason for retention is explicitly documented by the producer.

---

### SOP 9.6 -- [SOP-DIU-610] Rights Manifest & Synthetic-Media Disclosure

**ZHC SOP.** Wraps PHOTO-SHOOT-SOP §8 step 7 + IDENTITY.md Shoot History; MODEL-SPECS §5 (taskId/resultUrls as keys); TEST-PROTOCOL §7.
**Library-version pin:** PHOTO-SHOOT-SOP v1.0, IDENTITY.md v1.0, MODEL-SPECS v1.0, TEST-PROTOCOL v1.0 (§-refs verified 2026-06-12).
**When to run:** After every verified delivery of a likeness-bearing or client-facing generative output. This SOP runs LAST in every shoot lifecycle, immediately before handing the deliverable to the producer.
**Frequency:** Every shoot delivery, without exception.
**Inputs:** Verified deliverable asset (local file, sha256 confirmed), Generation Operator's receipt (containing model ID, endpoint, prompt hash, seed if available, taskId, card ID + version), consent record version, reference image provenance records.

**Steps:**
1. Open `_local/rights-manifest/{client-id}/RIGHTS-MANIFEST.md` (initialize the manifest and its `disclosure-table.json` per SOP-DIU-610 section A on the client's first shoot). Append ONE new entry block per delivered output, as one write; never batch entries, never edit or delete a prior entry (a correction is a new entry with `correction_of`). You are the only writer; the Generation Operator's receipt is your input, not a second writer.
2. Write the entry with ALL fields of the SOP-DIU-610 entry block: output asset path + sha256, shoot id, taskId, card ID + version, model + tier + prompt hash + seed (if available), reference provenance + hosting method, consent record ID + version + scope modes at delivery, `likeness_present`, `minors_present` (always `false`), `watermark_false_permitted`, disclosure applied + disclosure-table version, delivery channel + jurisdiction, delivered_at, delivered_by.
3. Determine the required disclosure per the client's `_local/rights-manifest/{client-id}/disclosure-table.json` (keyed `{channel}_{jurisdiction}`, versioned independently -- not hard-coded in this file): photoreal synthetic imagery of a real person published externally on covered platforms requires the platform's AI-content label per their synthetic-media policies and the EU AI Act deepfake-transparency obligations. Internal drafts and obviously-stylized Mode F outputs are exempt.
4. If disclosure is required: apply the appropriate platform label to the asset before delivery. Record `disclosure_applied` and the disclosure text copied verbatim from the table in the manifest entry.
5. Wan 2.7 `watermark:false` parameter is permitted ONLY when a manifest entry exists for this asset. Never use `watermark:false` on a Wan output that has not been fully manifested.
6. If C2PA/Content-Credentials tooling is available in the pipeline: populate the corresponding assertion fields from the manifest entry (asset, model, prompt hash, seed, date, consent version) -- the manifest fields map 1:1 to C2PA assertions by design.
7. Append the entry ID and delivery date to the Shoot History row in IDENTITY.md (a pointer only). The appended entry closes the shoot.

**Outputs:** One appended manifest entry; disclosure applied to deliverable where required; shoot marked closed in shoot record.
**Hand to:** Chief Design Officer (final deliverable with manifest entry confirmed).
**Failure mode:** If any required manifest field cannot be populated (e.g., the Generation Operator's receipt is missing the prompt hash or taskId), do NOT close the shoot as complete. Return to the Operator for the missing receipt data. A delivery is not complete without a complete manifest entry.

---

*SOPs owned: [SOP-DIU-401a], [SOP-DIU-401b], [SOP-DIU-402], [SOP-DIU-608], [SOP-DIU-609], [SOP-DIU-610]. sop_count: 6.*
