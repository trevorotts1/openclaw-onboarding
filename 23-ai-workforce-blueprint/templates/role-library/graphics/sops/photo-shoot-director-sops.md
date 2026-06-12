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
1. Look up the subject's CONSENT.md at `personal-photo-shoot/{client-slug}/CONSENT.md`. If the file does not exist, the shoot cannot proceed -- create a new `pending` record and route to producer for consent collection. Do NOT proceed to generation.
2. Check consent status machine: must be `active`. If `expired` or `revoked`, halt immediately; notify producer and subject (via producer). If `pending`, halt; notify producer that consent collection is outstanding.
3. Verify scope coverage: does the active consent record cover (a) the requested shoot modes (A-F), (b) the intended commercial/internal use, and (c) the distribution channels listed in the brief? Mode F (stylized creative) requires explicit opt-in.
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
   - Mode A (Headshot): tight Identity Lock Block, NB2 or GPT-Image-2 I2I per MODEL-SPECS routing table, studio/natural light settings.
   - Mode B (Lifestyle): Identity Lock Block + environment/activity descriptors, extended context prompt.
   - Mode C (Branded editorial): Identity Lock Block + brand foundation block (from box brand config), editorial-style context.
   - Mode D (Contact sheet): Identity Lock Block, multiple-variation contact sheet workflow (PHOTO-SHOOT-SOP §8 step 1), Kie.ai n=4 contact-sheet tier.
   - Mode E (Client-in-Slide composite): Identity Lock Block, text-clear-zone framing, coordinate with Deck Systems Specialist for slide composition specs.
   - Mode F (Stylized creative): Identity Lock Block + stylized descriptors (NO named-artist or named-studio references); requires explicit consent opt-in confirmed in SOP 9.1.
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
1. Check that retouching scope is covered in the client's active consent record (SOP-DIU-608 scope field includes retouch boundaries). If the requested edit falls outside the consented retouch scope, halt and notify producer.
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
1. Create or update `personal-photo-shoot/{client-slug}/CONSENT.md` using the machine-readable YAML front-matter schema (from `_system/CONSENT-RECORD-TEMPLATE.md`). Fields required: `who`, `scope` (modes A-F covered, stylized_opt_in y/n, commercial_use y/n, channels list), `term` (start date, expiry date), `retouch_boundaries`, `status` (one of: none / pending / active / expired / revoked), `revision_log` (append-only).
2. MINORS: The `minors` field in the schema defaults to `hard_block`. This default is never overridden. If a brief involves a minor, the record cannot be created with any non-block status. Full stop.
3. Self-likeness fast path (standing release at onboarding): for a client consenting to their own image, create with `status: active`, full standard scope (Modes A-D as default, Mode F only if client opts in explicitly), standard commercial/internal use, channels as specified. This record is a file-read gate on all subsequent requests -- no human loop required for in-scope modes.
4. Restricted-Content Gate (three-verdict matrix): before any generation proceeds, evaluate the brief against the current Restricted-Content Matrix (`_system/RIGHTS-SAFETY-SOP.md` versioned matrix section):
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
1. Validate each reference image against the target endpoint's format and size limits per MODEL-SPECS §1/§5: GPT-Image-2 I2I and NB2 accept up to 30MB (jpeg/png/webp/jpg); Seedream Edit and Wan accept up to 10MB. Reject and request a replacement for any reference that exceeds the limit or is in an unsupported format.
2. For any real-person likeness reference (identity photos, client headshots): the ONLY permitted hosting path is the client's GHL media library for that client's GHL location. Public ImgBB or any other public-permanent hosting is PROHIBITED for identity reference images.
3. Upload the validated reference images to the client's GHL media library. Record the upload receipts (URLs + upload timestamp) in the shoot record.
4. Verify each URL fetches correctly: perform a URL-liveness check (HTTP HEAD or GET returning 200 with the expected content-type) before including it in the shoot brief.
5. Include the verified hosting URLs in the shoot brief handed to the Generation Operator.
6. After the Generation Operator confirms job completion and the asset has been downloaded to local storage (per SOP-DIU-601 postflight): trigger deletion of the remote reference images from GHL media. Record deletion confirmation in the shoot record.
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
1. Open the per-client Rights Manifest directory at `personal-photo-shoot/{client-slug}/rights-manifests/`. Create a NEW per-item receipt file (one file per delivered output, never a shared concurrent-append manifest) named `{YYYYMMDD}_{shoot-mode}_{taskId}.json`.
2. Write the manifest entry with ALL required fields: output asset path + sha256, consent record ID + version at time of delivery, reference images used + their provenance class, model ID + endpoint + prompt hash + seed (if available) + taskId, date, disclosure applied (true/false + disclosure type).
3. Determine the required disclosure per the channel x jurisdiction table in `_system/RIGHTS-SAFETY-SOP.md` (the versioned disclosure table -- not hard-coded in this file): photoreal synthetic imagery of a real person published externally on covered platforms requires the platform's AI-content label per their synthetic-media policies and the EU AI Act deepfake-transparency obligations. Internal drafts and obviously-stylized Mode F outputs are exempt.
4. If disclosure is required: apply the appropriate platform label to the asset before delivery. Record `disclosure_applied: true` and `disclosure_type: {platform_label_type}` in the manifest entry.
5. Wan 2.7 `watermark:false` parameter is permitted ONLY when a manifest entry exists for this asset. Never use `watermark:false` on a Wan output that has not been fully manifested.
6. If C2PA/Content-Credentials tooling is available in the pipeline: populate the corresponding assertion fields from the manifest entry (asset, model, prompt hash, seed, date, consent version) -- the manifest fields map 1:1 to C2PA assertions by design.
7. File the completed manifest receipt. This receipt file closes the shoot.

**Outputs:** Per-item manifest receipt file; disclosure applied to deliverable where required; shoot marked closed in shoot record.
**Hand to:** Chief Design Officer (final deliverable with manifest entry confirmed).
**Failure mode:** If any required manifest field cannot be populated (e.g., the Generation Operator's receipt is missing the prompt hash or taskId), do NOT close the shoot as complete. Return to the Operator for the missing receipt data. A delivery is not complete without a complete manifest entry.

---

*SOPs owned: [SOP-DIU-401a], [SOP-DIU-401b], [SOP-DIU-402], [SOP-DIU-608], [SOP-DIU-609], [SOP-DIU-610]. sop_count: 6.*
