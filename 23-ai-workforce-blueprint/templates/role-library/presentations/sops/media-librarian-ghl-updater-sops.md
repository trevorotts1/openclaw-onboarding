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
> 1. **GHL media destination resolved** (SOP 9.3, run-once) — `ghl_folder_id` set by
>    CREATING a per-deck folder via the verified `ghl_media.create_media_folder`
>    (POST `/medias/folder`, Version 2021-07-28, LOCATION PIT) — the system makes the
>    folder by software. Only if that call genuinely declines does it fall back to a
>    human-supplied folder id, then to `"root"` (the shareable media root; a PASSING
>    value). A null/empty `ghl_folder_id` is the unset Step-0 seed and does NOT satisfy
>    the gate. NEVER drive the GHL UI in a browser.
> 2. **Per-slide PNG upload** (SOP 9.3) — every passed slide carries a real
>    `ghl_media_id` and `ghl_upload_status: "complete"`.
> 3. **Final PPTX upload** (recorded by the Delivery Concierge, ROLE-13, at its SOP 9.2 —
>    see SOP 9.6 below for the migrated ownership) — the assembled deck is uploaded with
>    `pptx_ghl_media_id` recorded.
>
> **The closeout gate is MECHANICAL, not doctrine-only.** Run
> `python3 scripts/ghl_media_push.py --gate --run-dir <run_dir>` (exit 0 = pass, 1 =
> fail), or call `gate_ghl_media_complete(run_dir)`. It folds under **AF-DELIVERY-COMPLETE**
> and HARD-FAILS unless all three records above are present (no defer-to-pass).
>
> The ONLY way to skip GHL upload is an explicit, LOGGED owner/founder decision: a
> `owner_skip_approval` token in `working/checkpoints/process_manifest.json`
> (`owner_approved: true` + a non-empty `approved_by` + a non-empty `reason` + a `gate`
> naming this gate, e.g. `"AF-DELIVERY-COMPLETE"`). Only when that token is present may
> you also write `ghl_delivery_skipped: true` (role file §17 / Edge Case 17.1). An agent
> setting `has_ghl: false` on its own does NOT skip the gate. A deck that simply omits the
> upload records is INCOMPLETE.
>
> **THE SINGLE CANONICAL ENTRY-POINT — NO SHORTCUT PATH.**
> A deck build runs through ONE flow only: the Director-orchestrated pipeline
> documented in `universal-sops/CLIENT-WEBINAR-DECK-SOP.md`, in which THIS role's
> SOP 9.1 → 9.2 → 9.3 → 9.4 → 9.6 are mandatory phases. `scripts/build_deck.py` is
> ONLY the Phase-4 image renderer + Phase-8 bare-`.pptx` assembler — it is NOT an
> entry-point and produces NO research, NO QC records, and NO GHL upload. Running
> `build_deck.py` against a hand-fed `slides.json` is the bypass this gate exists to
> catch: such a deck has no GHL media-upload record and is therefore NOT done. The
> in-department `build_deck.py` postflight + delivery gates are the BINDING enforcement
> here (AF-BUNDLE-COMPLETE / AF-DELIVERY-COMPLETE). A Command Center QC-scorer mirror of
> **AF-PIPELINE-COMPLETE** is ROADMAP, not shipped in this repo, and must not be relied on
> as the enforcing gate.

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

**Status:** MANDATORY for every GHL-enabled client. This SOP is a hard gate: the GHL media
destination MUST be resolved and every passed slide PNG MUST be uploaded, with `ghl_folder_id`
(a real pre-made folder id OR `"root"`) and each `ghl_media_id` recorded in media_library.json.
Skipping this step is only permitted under the `has_ghl: false` carve-out (write
`ghl_delivery_skipped: true`). A deck that omits these records is NOT done.

> **BINDING -- GHL is touched ONE WAY ONLY: the Tier-3 REST API via the SHARED
> `scripts/ghl_media.py` tool.** Two calls, both with the CLIENT's GHL **LOCATION** PIT
> (the Agency token 401s for media; token `GOHIGHLEVEL_API_KEY` (preferred) / legacy
> `GHL_API_KEY`; location id `GOHIGHLEVEL_LOCATION_ID` (preferred) / `GHL_LOCATION_ID`):
> (1) **CREATE the per-deck folder** `ghl_media.create_media_folder(name, location_id, pit)`
> -> `POST https://services.leadconnectorhq.com/medias/folder` (Version: 2021-07-28,
> JSON `{name, locationId[, parentId]}`) — **FAIL-CLOSED as of FIX 36(2)**: the folder-create
> POST is NEVER issued. A folder MUST be pre-created by a human in the GHL UI (its id passed
> as `approved_folder_id`) or the tool returns the documented decline (`{"folderId": None,
> "http": 404, "fallback": "name-prefix"}`) and the upload proceeds to the media **root** with
> a name prefix. (2) **UPLOAD** `ghl_media.upload_media(...)` ->
> `POST .../medias/upload-file` (Version: 2021-07-28, multipart; `file` + `locationId` +
> `name` + `hosted=false` + `parentId=<folderId>`). FALLBACK only when create genuinely
> declines: human-supplied folder id, else media **root**. Driving the GHL UI in a browser
> (agent-browser / Playwright / Puppeteer / any UI automation) is **STRICTLY FORBIDDEN**.

**When to run:** Immediately after each image is intaked (SOP 9.2), and after SOP 9.1 records the media destination.

**Inputs:**
- media_library.json (`ghl_folder_id` -- a pre-made folder id, or `"root"`; resolved in the first step below)
- intake.json (optional `ghl_media_folder_id` -- a folder a human created in the GHL UI for this deck)
- working/media-library/slide-NN.png (the image to upload)
- GHL **LOCATION** PIT from the client's env stores (`GOHIGHLEVEL_API_KEY` / legacy `GHL_API_KEY`) + location id (`GOHIGHLEVEL_LOCATION_ID` / legacy `GHL_LOCATION_ID`)

**Steps (Resolve the GHL media destination -- run once per deck run; CREATE the folder BY SOFTWARE):**
1. If media_library.json still has `ghl_folder_id: null`, resolve the destination (or just run `scripts/ghl_media_push.py`, which does this + the uploads):
   a. **CREATE the per-deck folder (FAIL-CLOSED, FIX 36(2)):** `ghl_media.create_media_folder("DECK <deck-slug>", location_id, pit)` — NO network call. With an `approved_folder_id` (a folder a human pre-created in the GHL UI) it returns that id with `approved: true`; set `ghl_folder_id` to it and pass it as `parentId` on every upload. Without one it returns the documented decline (`{"folderId": None, "http": 404, "fallback": "name-prefix"}`) — proceed to step c (media root + name prefix). The folder-create POST is never issued by this pipeline.
   b. **If create DECLINES** AND a human supplied `ghl_media_folder_id` in intake.json: use that id as `parentId`.
   c. **Else:** omit `parentId` and upload to the shareable GHL media **root**; set `ghl_folder_id: "root"` (a PASSING value), prefixing each upload `name` with `"<deck-slug> — "`.
   d. **Never drive the GHL web UI in a browser** -- folder-create is the REST API (step a), not UI automation.

**Steps (Upload Each Image):**
1. For the image at working/media-library/slide-NN.png:
   a. GHL remote name (`name`) MUST be: `Slide NN v<version_number>` (zero-padded). Example: `Slide 01 v1`, `Slide 23 v2`.
   b. Call `POST /medias/upload-file` (Version: 2021-07-28, multipart) with the LOCATION PIT as Bearer, `file=@slide-NN.png`, `locationId=<location id>`, `name=Slide NN v<N>`, `hosted=false`, and `parentId=<ghl_folder_id>` ONLY when `ghl_folder_id` is a real folder id (omit `parentId` when it is `"root"`).
   c. Read the `fileId` (the GHL media id) and the `url` from the response and record them.
2. Update media_library.json for this image: `{ "ghl_upload_status": "complete", "ghl_media_id": "...", "ghl_url": "...", "ghl_remote_name": "Slide NN v<N>", "uploaded_at": "ISO timestamp" }`.
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

### SOP 9.6 -- Final Deck Delivery (MIGRATED to ROLE-13 Delivery Concierge)

**Status:** MIGRATED. Final deck delivery is owned by the Delivery Concierge (ROLE-13, `presentations/delivery-concierge.md`, whose SOPs absorb this procedure). ROLE-13 exists in the department roster (00-START-HERE.md, Role Roster) and `PIPELINE-MANIFEST.json` assigns `P9-DELIVER` to `delivery-concierge`. This role does NOT deliver the final deck. The full upload/verify/notify procedure (package assembly, destination resolution, the final PPTX GHL upload recording `pptx_ghl_media_id`, destination ground-truth verification, the `openclaw message send` notification) lives in the Delivery Concierge's SOPs 9.0-9.4, including the `AF-DH1` hygiene whitelist and the `working/qc/final_deck_qc.json` delivery interlock.

**What this role still owns:** the media-library and GHL upload records delivery consumes (SOPs 9.1-9.5 above), plus the GHL upload closeout gate (SOP 9.8 below): `python3 scripts/ghl_media_push.py --gate --run-dir <run_dir>` / `AF-DELIVERY-COMPLETE`.

**When it triggers:** After final Phase 6 QC passes (`working/qc/final_deck_qc.json` present with `pass: true` and `qc_score >= 8.5`).

**Steps (this role's part of the hand-off):**
1. Confirm the delivery pass-artifact `working/qc/final_deck_qc.json` exists on disk with `pass: true` and `qc_score >= 8.5`. If absent or failing, halt and notify the QC Specialist.
2. Confirm media_library.json is complete: `ghl_folder_id` (a real folder id or `"root"`), `ghl_folder_name`, `version_number`, and per-slide `ghl_media_id` records from SOP 9.3.
3. Hand off to the Delivery Concierge (ROLE-13): the QC-passed deck plus media_library.json. The Delivery Concierge assembles the clean package (its SOP 9.0), resolves destinations (its SOP 9.1), uploads to every destination including the final PPTX GHL upload recording `pptx_ghl_media_id` (its SOP 9.2), verifies every destination (its SOP 9.4), and sends the delivery notification via `openclaw message send` (its SOP 9.3).
4. Support re-uploads on request: if the Delivery Concierge reports a missing or unverified file in GHL, retry the affected upload via SOP 9.3 and report back.

**Outputs:**
- Complete media_library.json (upload records ready for delivery consumption)
- Hand-off to the Delivery Concierge (ROLE-13) recorded to the Director

**Hand to:** Delivery Concierge (ROLE-13) -- final deck delivery; Director of Presentations (run closeout happens after the Delivery Concierge verifies every destination)

**Failure mode:** If any GHL record this role owns is missing or failed (SOP 9.3 `ghl_upload_status: "failed"`): resolve it BEFORE the hand-off, or notify the Director with the specific gap list. Never hand off an incomplete media_library.json as if it were complete -- a "ready for delivery" claim without verified upload records is a lie.

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

### SOP 9.8 -- GHL Upload Closeout Gate (AF-DELIVERY-COMPLETE)

**When to run:** At closeout, before the run is marked "Done" — invoked by the governed
orchestrator/postflight. Not optional; not skippable by re-ordering phases.

**What it enforces:** `working/checkpoints/media_library.json` records ALL THREE GHL
uploads — `ghl_folder_id` (real id or `"root"`), a complete per-slide `ghl_media_id`
for every passed slide, and a `pptx_ghl_media_id` for the final deck. Reads the canonical
ledger ONLY (the same file SOP 9.1 seeds and `scripts/delivery_gate.py` reads); no GHL UI,
no self-report.

**Steps:**
1. Run `python3 scripts/ghl_media_push.py --gate --run-dir <run_dir>` (exit 0 = pass,
   1 = fail), or call `gate_ghl_media_complete(run_dir)` -> `(ok, reasons)`. Optionally
   pass `--expected-slides N` (or record `expected_slide_count` in the ledger) for a
   per-slide coverage cross-check.
2. On FAIL: complete the missing upload via SOP 9.3 / 9.6, then re-run. Never mark the
   run delivered on a FAIL.
3. **Owner-skip carve-out (the ONLY skip):** a logged token in
   `working/checkpoints/process_manifest.json` under `owner_skip_approval`
   (`owner_approved: true` + `approved_by` + `reason` + `gate: "AF-DELIVERY-COMPLETE"`).
   With the token the gate passes and `ghl_delivery_skipped: true` may be recorded
   (Edge Case 17.1). Without it, `has_ghl: false` set by the agent alone still fails.

**Outputs:** a PASS verdict (exit 0) that authorizes closeout, or a FAIL with the exact
missing records.

**Hand to:** Delivery Concierge / Director (closeout proceeds only on PASS).

**Failure mode:** A FAIL hard-blocks "Done." Do not fabricate `ghl_media_id` /
`pptx_ghl_media_id` values — every id must come from a real `upload_media` response.

---

### SOP 9.9 -- Upsell Pages: Sales / Checkout / VSL (pointer)

**When to run:** `P-U-SALES-BUILD` (order 8.75), `P-U-CHECKOUT-BUILD` (order 8.76),
`P-U-FORM-CHECKOUT` (order 8.77), and `P-U-VSL-BUILD` (order 8.93) all declare
`owning_role: media-librarian-ghl-updater` and `sop_refs: ["media-librarian-ghl-updater-sops.md"]`
in `PIPELINE-MANIFEST.json` (manifest_version 51) -- this entry is that reference resolving to real
content, not a dead pointer.

**Full procedure lives in two standalone builder SOPs, same directory:**
- `SALES-CHECKOUT-BUILDER-SOP.md` -- `P-U-SALES-BUILD`, `P-U-CHECKOUT-BUILD`, `P-U-FORM-CHECKOUT`
  (the waiver mechanic, the copy -> Kie.ai design -> HTML -> GHL funnel push pipeline, the checkout
  form's cross-department form-craft option).
- `VSL-BUILDER-SOP.md` -- `P-U-VSL-BUILD` (the same pipeline shape, the hard video dependency on
  `P9.6-WEBINAR-VIDEO`, the ~3-8-minute viewer gate).

**Why these four don't get their own full numbered SOP block here:** they are a genuinely separate
build (a different deliverable class -- funnel pages, not deck/workbook/webinar assets) with their
own waiver mechanic, their own executor scripts (`sales_checkout_builder.py`, `vsl_builder.py`), and
their own push mechanism (`06-ghl-install-pages/tools/ghl_rest_canvas.py`, not this role's usual
`ghl_media.py`/`ghl_media_push.py` bare-REST media path -- see `SALES-CHECKOUT-BUILDER-SOP.md` §3.4
for why that distinction matters operationally). Folding that into this file's SOP-9.x numbering would
bury a distinct capability inside the media-library/upload procedure it isn't part of. The manifest's
`owning_role` assignment to this role stands because this role is the department's only other
GHL-push-terminating deliverable owner (`P9.6-WEBINAR-VIDEO`, SOP 9.6 above) -- the same precedent the
two builder SOPs cite for that choice.

**Status as of this entry (2026-08-19):** the four phases above ARE in `PIPELINE-MANIFEST.json`
(manifest_version 51) and `scripts/sales_checkout_builder.py` exists on disk. `scripts/vsl_builder.py`
does not yet exist; no `phase_verifiers.py` entries or `AF-U-*` autofail-registry rows exist yet for
any of the four. See each builder SOP's own STATUS section for the full, itemized LIVE/PENDING
breakdown -- do not treat this pointer entry as confirming more than that.

---

