# SOPs Mirror -- Media Librarian and GHL Updater

**Source:** presentations/media-librarian-ghl-updater.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md

> **REQUIRED, GATED — THE GHL MEDIA UPLOAD IS NOT OPTIONAL.**
> For every deck whose client has GHL (`intake.json` does NOT set `has_ghl: false`),
> all three GHL actions below are MANDATORY and GATED — a deck is NOT done until each
> is recorded in `working/checkpoints/media_library.json`:
> 1. **GHL folder creation** (SOP 9.3, run-once) — `ghl_folder_id` set to a real id
>    (or `"root_fallback"` only after a logged API failure). A null/empty `ghl_folder_id`
>    is the unset Step-0 seed and does NOT satisfy the gate.
> 2. **Per-slide PNG upload** (SOP 9.3) — every passed slide carries a real
>    `ghl_media_id` and `ghl_upload_status: "complete"`.
> 3. **Final PPTX upload** (SOP 9.6) — the assembled deck is uploaded with
>    `pptx_ghl_media_id` recorded.
>
> The ONLY exception is the explicit carve-out in the role file §17: `intake.json`
> shows `has_ghl: false`, in which case you MUST write `ghl_delivery_skipped: true`
> (the gate then reads that field instead of the upload records). There is no other
> way to skip GHL upload — a deck that simply omits these records is INCOMPLETE.
>
> **THE SINGLE CANONICAL ENTRY-POINT — NO SHORTCUT PATH.**
> A deck build runs through ONE flow only: the Director-orchestrated pipeline
> documented in `universal-sops/CLIENT-WEBINAR-DECK-SOP.md`, in which THIS role's
> SOP 9.1 → 9.2 → 9.3 → 9.4 → 9.6 are mandatory phases. `scripts/build_deck.py` is
> ONLY the Phase-4 image renderer + Phase-8 bare-`.pptx` assembler — it is NOT an
> entry-point and produces NO research, NO QC records, and NO GHL upload. Running
> `build_deck.py` against a hand-fed `slides.json` is the bypass this gate exists to
> catch: such a deck has no GHL media-upload record and is therefore NOT done. The
> Command Center QC scorer enforces this independently as **AF-PIPELINE-COMPLETE**
> (blocks review→Done when the research brief, copy/image QC log, or GHL
> media-upload record are absent).

### SOP 9.0 -- Client-Asset Ingest + Scratch-Deck Parser (Decision 1C)

**When to run:** At intake, whenever `intake.json.assets_provided:true` (the client answered the Brainstorming Buddy ASSET BRANCH with materials). Runs BEFORE Phase 2 so the Brand Steward + Slide Image Creator can consume the provided assets as gpt-image-2 `input_urls`.

**Inputs:**
- intake.json (`assets_provided`, the captured asset list / uploads)
- The provided files (photos, logo, brand-color swatches, product shots, a rough/old deck, slides, concepts)

**Steps:**
1. **Classify each provided asset** into a `kind`: `photo` | `logo` | `brand_color` | `product` | `scratch_slide` | `concept`.
2. **Upload each asset to a STABLE public URL** (the same GHL/Drive upload path SOP 9.3 uses; the URL must be reachable so KIE can fetch it as `input_urls`). Record the resolved `public_url`.
3. **Write `working/copy/assets_manifest.json`** with this shape:
   ```json
   {
     "asset_question_asked": true,
     "assets_provided": true,
     "assets": [
       { "kind": "logo", "source_path": "uploads/logo.png",
         "public_url": "https://.../logo.png",
         "consumed_by": ["brand-steward", "slide-image-creator"] },
       { "kind": "photo", "source_path": "uploads/founder.jpg",
         "public_url": "https://.../founder.jpg",
         "consumed_by": ["slide-image-creator"] }
     ],
     "scratch_deck": { "provided": false, "parsed": false,
                       "path": null, "seed_prd_path": "working/copy/scratch_seed.json" }
   }
   ```
   Every provided asset MUST carry a non-empty `consumed_by` list AND a resolved `public_url`. The gate **AF-MANIFEST-UNREFERENCED** (`build_deck.py` `_chk_assets_manifest`) fails the deck if any provided asset is recorded but not provably consumed (no `consumed_by`) or has no `public_url` to feed as `input_urls`. Provided client material is NEVER collected and ignored.
4. **Scratch-deck parser sub-step (when the client uploaded a rough/old deck):** set `scratch_deck.provided:true`, extract the uploaded deck's content + structure (slide titles, copy, section order, any stated offer/claims) into `working/copy/scratch_seed.json`, then set `scratch_deck.parsed:true` and `scratch_deck.path` to the uploaded file. The Director's PRD improvement pass (director SOP 9.2) folds `scratch_seed.json` into the Mission PRD and sets `seeded_from_scratch_deck:true`. **The interview still runs in FULL — the scratch deck only SEEDS the PRD; the client still answers every question.** The gate **AF-SCRATCH-PARSE-SKIPPED** (`_chk_scratch_parse`) fails the deck if an uploaded scratch deck is recorded but not parsed, or parsed but never seeds the PRD.
5. Notify the Director: "Asset ingest complete: N assets in assets_manifest.json (consumed_by recorded); scratch deck parsed=[yes/no]."

**Outputs:**
- `working/copy/assets_manifest.json` (per-asset `public_url` + `consumed_by`)
- `working/copy/scratch_seed.json` (only when a scratch deck was uploaded)

**Hand to:** Brand Steward (consumes logo/brand-color/photo assets as `input_urls`) + Slide Image Creator (consumes photo/product assets as `input_urls`); Director (PRD seed from `scratch_seed.json`).

---

### SOP 9.1 -- Step-0 Landing Zone Creation

**When to run:** At the very start of every new deck run -- before discovery interview, before any other action.

**Inputs:**
- intake.json (may be partially complete at this point -- only client_slug and deck_slug are needed)
- Current date (ISO format, YYYY-MM-DD)

**Steps:**
1. Determine the local workdir path:
   - Mac clients: `~/webinar-decks/<client-slug>/<deck-slug>/<YYYY-MM-DD>/`
   - VPS clients: `/data/.openclaw/workspace/webinar-decks/<client-slug>/<deck-slug>/<YYYY-MM-DD>/`
   Use today's date for YYYY-MM-DD.
2. Create the directory tree with all required subdirectories:
   ```
   <workdir>/
     media-library/               (passed images -- the deliverable folder; files named slide-NN.png)
       assets/
         logo/                    (client logo files: logo-full.png, logo-chip.png)
         founder-portrait/        (founder / host portrait photos passed in as A5 reference images)
         proof-assets/            (before/after photos, testimonial screenshots, product images)
     working/
       prompts/                   (per-slide prompt files: slide-NN-prompt.txt)
       renders/                   (raw downloads from Phase 4 -- pre-QC: slide-NN-raw.png)
       checkpoints/               (all checkpoint JSON files)
         media_library.json       (run ledger: paths, GHL folder id, version number)
         run_ledger.json          (per-phase completion log)
         (no pptx_text_overlays.json — native-text overlays are eliminated, Decision 5C; its presence is AF-OVERLAY-DELIVERED)
       qc/                        (QC reports from all phases)
         copy_qc_report.json
         prompt_qc_report.json
         image_qc_report.json
         final_deck_qc.json
         finalrender/             (QC-passed final render copies, before upload to GHL)
       copy/                      (slide copy, intake, PRD, approval records)
       brand/                     (STYLE BLOCK, brand registry, representation audit)
     output/                      (final assembled deck: <deck-slug>_v<N>.pptx)
   ```
   **Naming conventions:**
   - Local slide files: `slide-NN.png` (zero-padded two digits, lowercase, kebab-case)
   - GHL folder name: `<Client First Name> <Deck Short Name> v<N>` (title-case, per run)
   - GHL slide title: `Slide NN v<N>` (title-case, space-separated)
   - Founder portrait: `founder-portrait-[slug].png` (client-supplied, not generated)
   - Logo: `logo-full.png` (full color) and `logo-chip.png` (small lockup for slide placement)
3. Verify: `ls -la <workdir>` confirms all subdirectories exist. If any creation failed, halt and notify the Director.
4. Determine version number N for this run. Check the GHL media library for existing folders with the naming pattern `<Client> <Deck> v<N>`. If none exist, N=1. If v1 exists, N=2. Etc.
5. Record all paths in working/checkpoints/media_library.json:
   ```json
   {
     "client_slug": "...",
     "deck_slug": "...",
     "run_date": "YYYY-MM-DD",
     "version_number": N,
     "local_workdir": "<full path>",
     "local_media_library": "<full path>/media-library/",
     "ghl_folder_name": "<Client> <Deck> v<N>",
     "ghl_folder_id": null,
     "drive_folder_id": null,
     "created_at": "ISO timestamp"
   }
   ```
   (ghl_folder_id is null until GHL folder is created in SOP 9.3)
6. Notify the Director: "Step 0 complete. Local workdir: [path]. GHL folder will be created next."

**Outputs:**
- Local directory tree (verified to exist)
- working/checkpoints/media_library.json (with null ghl_folder_id pending GHL creation)

**Hand to:** Director (who can now begin the discovery interview and all other run phases)

**Failure mode:** If directory creation fails (permission error, disk full), halt immediately. Notify the Director: "Step 0 blocked: [specific error]. Cannot proceed." Never start a run without the local directory tree.

---

### SOP 9.2 -- Passed-Image Intake

**When to run:** During Phase 5 -- as each image passes the QC gate (score >= 8.5). Run continuously as QC reports come in; do not wait for all images.

**Inputs:**
- working/qc/image_qc_report.json (watch for new passes)
- working/renders/slide-NN.png (source of passed images)

**Steps:**
1. Watch image_qc_report.json for entries with `pass: true` and `local_path` set.
2. For each newly passed image:
   a. Verify the file exists at the path in local_path and is a valid non-empty PNG.
   b. Copy (do not move) the image from working/renders/slide-NN.png to working/media-library/slide-NN.png.
   c. Naming convention MUST be: `slide-NN.png` (zero-padded slide number, kebab-case). This naming is mandatory for python-pptx assembly order.
3. Update media_library.json: add an entry for this image: `{ "slide_number": N, "local_media_library_path": "...", "ghl_upload_status": "pending" }`.
4. After copying: trigger SOP 9.3 (GHL upload) for this image immediately. Do not batch -- upload as images pass.

**Outputs:**
- working/media-library/slide-NN.png (copied from renders)
- media_library.json (updated with intake entries)

**Hand to:** SOP 9.3 (GHL upload, triggered per image)

**Failure mode:** If the source file does not exist at working/renders/slide-NN.png (despite image_qc_report.json showing a pass): flag to the QC Specialist. Do not fabricate a file path. Record the anomaly in media_library.json.

---

### SOP 9.3 -- GHL-Drive Upload (REQUIRED, GATED)

**Status:** MANDATORY for every GHL-enabled client. This SOP is a hard gate: the GHL
folder MUST be created and every passed slide PNG MUST be uploaded, with `ghl_folder_id`
and each `ghl_media_id` recorded in media_library.json. Skipping this step is only
permitted under the `has_ghl: false` carve-out (write `ghl_delivery_skipped: true`).
A deck that omits these records is NOT done — enforced as AF-PIPELINE-COMPLETE.

**When to run:** Immediately after each image is intaked (SOP 9.2), and after SOP 9.1 creates the GHL folder.

**Inputs:**
- media_library.json (ghl_folder_id -- if still null, create the folder first)
- working/media-library/slide-NN.png (the image to upload)
- GHL credentials from client's env stores

**Steps (Create GHL Folder -- run once per deck run):**
1. If media_library.json has `ghl_folder_id: null`: create the GHL media library folder.
   a. Folder name: `<Client> <Deck> v<N>` (use the values from media_library.json).
   b. Call the GHL media library folder-create API. The CORRECT endpoint is:
      POST https://services.leadconnectorhq.com/medias/folder
      Headers: Authorization: Bearer <LOCATION_PIT>, Version: 2021-07-28, Content-Type: application/json
      Body: {"altId": "<locationId>", "altType": "location", "name": "<folder name>"}
      IMPORTANT: do NOT use POST /medias/ — that path does not exist and returns 404.
      The successful response is a folder object; capture the _id field as the folder_id.
   c. If the API call fails: log the failure, upload to Media Library root, and note in media_library.json: `ghl_folder_creation_failed: true, fallback: "media_library_root"`.
   d. Update media_library.json: `ghl_folder_id: "[returned_id or 'root_fallback']"`.

**Steps (Upload Each Image):**
1. For the image at working/media-library/slide-NN.png:
   a. GHL remote name MUST be: `Slide NN v<version_number>` (zero-padded, human-readable). Example: `Slide 01 v1`, `Slide 23 v2`.
   b. Call the GHL upload API with the file content, the GHL folder ID (or root if fallback), and the remote name.
   c. Record the GHL media_id returned by the API.
2. Update media_library.json for this image: `{ "ghl_upload_status": "complete", "ghl_media_id": "...", "ghl_remote_name": "Slide NN v<N>", "uploaded_at": "ISO timestamp" }`.
3. If the client uses Google Drive (has `use_drive: true` in intake.json): also upload to the Drive folder at the path recorded in media_library.json. Record Drive file_id.
4. If the GHL upload fails: retry once after 30 seconds. If second attempt fails: mark `ghl_upload_status: "failed"` and flag to the Director. Do not skip the delivery verification until the failure is resolved.

**Outputs:**
- media_library.json (updated with ghl_upload_status and ghl_media_id for each image)
- Images in GHL media library (or root fallback)

**Hand to:** SOP 9.4 (delivery verification, run after all images are uploaded)

**Failure mode:** If GHL API is completely unavailable (authentication failure, service outage): log all failed uploads in media_library.json. Notify the Director: "[N] images could not be uploaded to GHL. Local copies are in [path]. GHL upload is pending resolution." The PPTX Assembly Specialist can still work from the local media-library/ folder; GHL upload can be retried separately.

---

### SOP 9.4 -- Delivery and Ground-Truth Verification

**When to run:** After all images have been uploaded (all entries in media_library.json show `ghl_upload_status: "complete"` or `"failed"`).

**Inputs:**
- media_library.json (complete with all entries)
- GHL media library (live API check)

**Steps:**
1. Count local images in working/media-library/: `ls working/media-library/*.png | wc -l`. Record as `local_count`.
2. Call the GHL API to list files in the deck's GHL folder. Count files with names matching `Slide NN v<N>` pattern. Record as `ghl_count`.
3. Compare local_count to slide_count_final from mission_prd.json.
4. Compare ghl_count to slide_count_final.
5. Compare local_count to ghl_count.
6. All three counts must match. Any mismatch = delivery verification FAILED.
7. For any GHL file that is missing (present locally but not in GHL): attempt a one-time re-upload.
8. If all counts match after any necessary re-uploads: write `delivery_verified: true, verified_at: "ISO timestamp", local_count: N, ghl_count: N` to media_library.json.
9. Notify the Director and the PPTX Assembly Specialist: "Delivery verification PASSED. [N] images confirmed in local media-library/ and GHL. PPTX assembly can begin."

**Outputs:**
- media_library.json (delivery_verified: true)
- Notification to Director and PPTX Assembly Specialist

**Hand to:** PPTX Assembly Specialist (who reads local media-library/ for assembly)

**Failure mode:** If after one re-upload attempt the GHL count still does not match: notify the Director with the specific gap: "[N] images are missing from GHL. See media_library.json for the list. PPTX assembly can proceed from local copies; GHL delivery is incomplete and requires manual resolution." Mark `delivery_verified: "partial"` in media_library.json.

---

### SOP 9.5 -- Client Asset Acquisition

**When to run:** During Phase A (discovery), before Phase 2 ends. LOGO_URL (and FOUNDER_PORTRAIT_URL when A5 slides exist) must be recorded in media_library.json before Phase 2 is complete. The [PROOF PENDING] resolution loop with the client must be completed before Phase 1A.

**Inputs:**
- intake.json (LOGO_ON_SLIDES, LOGO_FILE, LOGO_URL, A5 slide presence flag)
- Client's GHL media library credentials
- Client's Google Drive credentials (if applicable)
- PROOF_ASSETS list from discovery

**Steps:**

**Logo acquisition:**
1. Check intake.json for LOGO_URL. If a stable public https URL is already present and the file downloads successfully (HTTP 200, non-empty), record it directly -- no upload needed.
2. If the client provided only a local file (LOGO_FILE set, LOGO_URL missing or not stable):
   a. Upload the file to the client's GHL media library (use the same GHL credentials as SOP 9.3). Record the returned media URL.
   b. If the client uses Drive, also upload to the client's Drive folder and record the direct-download link.
   c. Prefer the GHL URL. Fall back to Drive direct-download link if GHL is unavailable.
3. Verify: attempt an HTTP GET on the final URL. It must return 200 with a non-empty body. A URL that returns 403 or 404 cannot be used as a Kie.ai reference image.
4. Record LOGO_URL in media_library.json: `"logo_url": "<verified public https URL>"`.

**Founder portrait acquisition (A5 slides only):**
1. If slides_copy.md (or the draft slide plan) contains any A5 archetype slides: collect the founder portrait image from the client.
2. Upload to GHL media library (and Drive if applicable) using the same upload process as above.
3. Verify the URL returns HTTP 200 with a non-empty body.
4. Record FOUNDER_PORTRAIT_URL in media_library.json: `"founder_portrait_url": "<verified public https URL>"`.

**[PROOF PENDING] resolution loop:**
1. During Phase A, collect all PROOF_ASSETS items: testimonials, revenue screenshots, press logos, before/after numbers.
2. For any proof item that the client has not yet supplied: mark it `[PROOF PENDING]` in intake.json and in the corresponding slide entry in slides_copy.md.
3. Before Phase 1A (owner approval gate): present the full list of [PROOF PENDING] items to the client and collect each one or confirm it will be replaced with a restructured slide (per the master SOP asset collection rule -- no fabricated proof, ever).
4. After the client responds: update intake.json and slides_copy.md. Replace [PROOF PENDING] with the actual asset reference, or mark [CLIENT TO SUPPLY] and restructure the slide to remove the fabricated element.
5. Run this loop until no [PROOF PENDING] entries remain before Phase 1A closes.

**Outputs:**
- media_library.json updated with `logo_url` (and `founder_portrait_url` if applicable)
- intake.json updated with resolved PROOF_ASSETS
- slides_copy.md updated with all proof references resolved or marked [CLIENT TO SUPPLY]

**Hand to:** Slide Image Creator / Prompt Writer (who reads LOGO_URL and FOUNDER_PORTRAIT_URL from media_library.json for image-to-image submissions); Director (confirmation that assets are ready before Phase 2)

**Failure mode:** If the client cannot supply a logo or founder portrait and the intake calls for one: escalate to the Director immediately. Do not proceed to Phase 2 with a missing reference URL. If the client confirms LOGO_ON_SLIDES = false, update intake.json and remove all logo references; text-to-image mode applies.

---

### SOP 9.6 -- Final Deck Delivery

**When to run:** After final Phase 6 QC passes (working/qc/final_deck_qc.md score >= 8.5).

Note: if a ROLE-13 Delivery Concierge role is added to this department in a future revision, this SOP migrates there and this role hands off to ROLE-13 after QC passes. Until that role exists, this role owns delivery.

**Inputs:**
- output/[DECK_SLUG].pptx (the QC-passed assembled deck)
- working/qc/final_deck_qc.md (final QC score, must be >= 8.5)
- intake.json (client box type: Mac vs. other)
- media_library.json (GHL folder name and ghl_folder_id)
- GHL credentials from client's env stores

**Steps:**

1. Confirm the final QC score is >= 8.5. Do not deliver a deck that has not passed final QC.

2. Determine delivery path:
   a. **Mac client (Mac mini or MacBook):** copy the PPTX to the client's ~/Downloads/ folder.
      - Command: `cp output/[DECK_SLUG].pptx ~/Downloads/[DECK_SLUG]_final.pptx`
      - Verify: `ls -lh ~/Downloads/[DECK_SLUG]_final.pptx` must show the file with a non-zero size.
      - Record the exact path.
   b. **Non-Mac or environment unclear:** do NOT assume a delivery location. Ask the client explicitly: "Where would you like the PowerPoint delivered: email, Google Drive, GHL, or somewhere else?" Then deliver to their stated destination. Record the destination.

3. Upload the final PPTX to the client's GHL media library (REQUIRED, not optional for GHL-enabled clients):
   - Upload to the same GHL folder used for the slide images (ghl_folder_id from media_library.json).
   - Remote name: `[Deck Title] FINAL v<N>.pptx`.
   - Record the returned GHL media_id and URL in media_library.json: `"pptx_ghl_media_id": "...", "pptx_ghl_url": "..."`.
   - The deck is NOT delivered until `pptx_ghl_media_id` is recorded (or the `has_ghl: false`
     carve-out applies and `ghl_delivery_skipped: true` is set). A self-report without the
     recorded media_id is not ground truth.

4. Verify every destination before reporting done:
   - Mac download: `ls -lh ~/Downloads/[DECK_SLUG]_final.pptx` (non-empty file must exist).
   - GHL: call the GHL API to confirm the PPTX file exists in the folder by its media_id. A self-report without an API confirmation is not ground truth.
   - Additional destinations (Drive, email, etc.): confirm via the relevant API or service before reporting.

5. Send a delivery notification via `openclaw message send` (never raw Telegram API):
   - Include every verified destination path or URL.
   - Include the final QC score.
   - Example message: "Your webinar deck is ready. Final QC score: [SCORE]/10. File locations: (1) ~/Downloads/[DECK_SLUG]_final.pptx on your Mac, (2) GHL media library folder '[FOLDER_NAME]' as '[REMOTE_NAME]'. Both locations confirmed."

6. Update media_library.json: add `"delivery_complete": true, "delivery_verified_at": "ISO timestamp", "delivery_destinations": [{"type": "...", "path_or_url": "...", "verified": true}]`.

**Outputs:**
- PPTX at every confirmed delivery destination
- media_library.json updated with delivery_complete and all destination records
- Delivery notification sent via openclaw message send

**Hand to:** Director of Presentations (run complete); client (via the delivery notification)

**Failure mode:** If any delivery destination fails verification: do not mark delivery_complete = true. Notify the Director: "Delivery incomplete: [destination] could not be verified. [Specific error]. Local PPTX is at output/[DECK_SLUG].pptx. Awaiting resolution." Never send a "done" message when a destination is unverified.

---

### SOP 9.7 -- Teleprompter Link Filing (GHL)

**When to run:** When the Delivery Concierge (ROLE-13 SOP 9.5) publishes the teleprompter and reports its verified public URL. The teleprompter is delivered to the client as a hosted LINK; that link is a deliverable artifact and must be filed in GHL alongside the deck.

**Inputs:**
- `<bundle_dir>/teleprompter_publish.json` (written by `build_deck.py`'s `publish_teleprompter()` or by the Delivery Concierge SOP 9.5; `status` must be `published`)
- `media_library.json` (the run ledger)
- The CLIENT's GHL credentials (from the client's env stores -- NEVER the operator's)

**Steps:**
1. Read the verified `public_url` from `<bundle_dir>/teleprompter_publish.json`. Its `status` must be `published` and `verified_http_status` must be 200. If not published/verified, do NOT file a link -- hand back to the Delivery Concierge to publish first.
2. Record the URL in `media_library.json` as `"teleprompter_public_url": "<url>", "teleprompter_published_at": "<ISO>"`, alongside `pptx_ghl_media_id`.
3. If the client uses GHL: attach the link to the deck's GHL media library folder record (custom field / note) using the CLIENT's GHL credentials -- never the operator's. A URL is filed as a reference, not a file upload (the teleprompter is hosted on the central Cloudflare host, not uploaded into GHL).
4. **Verify (ground-truth):** the URL recorded in `media_library.json` must match the published URL in `teleprompter_publish.json` EXACTLY. A self-report is not ground truth.

**Outputs:** `media_library.json.teleprompter_public_url` (matches the published URL exactly); the GHL deck folder record carries the teleprompter link.

**Hand to:** Delivery Concierge (ROLE-13 SOP 9.3 / 9.4) -- the link is now filed and can be delivered + verified.

**Failure mode:** If `teleprompter_publish.json` is absent or not `published`: do not invent a link. Notify the Delivery Concierge that the teleprompter is not yet published, and do not record a `teleprompter_public_url`. The postflight gate (AF-BUNDLE-COMPLETE / TELEPROMPTER-PUBLISH sub-check) keeps the run from "Done" until the link is live.

---

