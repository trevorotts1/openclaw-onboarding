# SOPs Mirror -- Delivery Concierge

**Source:** presentations/delivery-concierge.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md

> Hybrid-delivery handoff (DOCTRINE -- HYBRID PRESENTATION, live -> record -> live; SOP-ENGINE-00 Section 4). This role owns the RECORDING handoff half of the hybrid model. A deck's recording is cut ONLY after the presenter has delivered it LIVE at least THREE times (the Presenter Coach logs these in working/presenter-coach/delivery_plan.json, `live_runs >= 3`; see presenter-coach-sops.md SOP 9.5). Do NOT accept a recording-cut handoff before the 3rd logged live run unless the owner has explicitly accepted the rust/pacing risk (logged as an exception). After the recording is deployed for scale, the plan schedules the presenter's RETURN to live for high-value rooms; the cadence is live -> record -> live, never live-once-then-recorded-forever.

> **BINDING -- how GHL is touched.** Any GHL upload goes EXCLUSIVELY through `POST https://services.leadconnectorhq.com/medias/upload-file` (Version `2021-07-28`, multipart, `parentId`) with the CLIENT's GHL **LOCATION** PIT (the agency token 401s for media). Token: `GOHIGHLEVEL_API_KEY` (preferred) / legacy `GHL_API_KEY`; location id: `GOHIGHLEVEL_LOCATION_ID` (preferred) / `GHL_LOCATION_ID`. The Delivery Concierge does NOT create the folder -- it uploads INTO the `ghl_folder_id` the Media Librarian already CREATED by software (`ghl_media.create_media_folder` -> `POST /medias/folder`, Version 2021-07-28; `"root"` only if create genuinely declined). Driving the GHL UI in a browser (agent-browser / Playwright / Puppeteer / ANY GHL UI automation) is FORBIDDEN. Reference: `29-ghl-convert-and-flow/references/medias.md`.

> **OPERATOR build bundle (9 files) vs CLIENT package (5 files).** `build_deck.py` writes a NINE-file OPERATOR build bundle to `~/Downloads/<client-slug>-<deck-slug>/` (`<deck-slug>-FINAL.pptx`, `<deck-slug>-FINAL.pdf`, `PRESENTER-GUIDE.pdf`, `PRESENTERS-SPEECH.md`, `PRESENTERS-SPEECH.pdf`, `PRESENTERS-SPEECH-FISH-TAGGED.md`, `PRESENTER-AUDIO.mp3`, `infographic.png`, `presenter-teleprompter.html`). SOP 9.0 CURATES the FIVE-file CLIENT package from those build artifacts. See `sops/SOP-PITCH-05-DELIVERABLE-BUNDLE.md`.

### SOP 9.0 -- Package Assembly and Hygiene Sweep (RUNS BEFORE SOP 9.1)

**When to run:** FIRST, immediately upon receiving a QC-passed deck, BEFORE SOP 9.1 (Destination Resolution) and BEFORE any file is moved or uploaded. This step is the AF-DH1 gate.

**Inputs:**
- working/qc/final_deck_qc.json (must pass AF-F5 before this step proceeds)
- output/[DECK_SLUG].pptx (assembled deck)
- output/[DECK_SLUG].pdf (portable-document export)
- working/deliverables/PRESENTER-GUIDE.pdf (rendered from PRESENTER-GUIDE.md by the Presenters Guide Specialist)
- working/presenter-speech/PRESENTERS-SPEECH.pdf (teleprompter PDF, Presenters Speech Writer)
- working/presenter-speech/audio/PRESENTER-AUDIO.mp3 (Fish Audio S2 render)
- sops/SOP-PITCH-05-DELIVERABLE-BUNDLE.md (the five-file whitelist and the blocklist)

**Steps:**
1. Create a clean, empty `delivery/[DECK_SLUG]-FINAL/` directory. This directory is NOT under `working/`. If it already exists from a prior run, empty it first.
2. Copy ONLY the five allowed CLIENT files into `delivery/[DECK_SLUG]-FINAL/`:
   - `output/[DECK_SLUG].pptx` -> `delivery/[DECK_SLUG]-FINAL/<deck-slug>-FINAL.pptx`
   - `output/[DECK_SLUG].pdf` -> `delivery/[DECK_SLUG]-FINAL/<deck-slug>-FINAL.pdf`
   - `working/deliverables/PRESENTER-GUIDE.pdf` -> `delivery/[DECK_SLUG]-FINAL/PRESENTER-GUIDE.pdf`
   - `working/presenter-speech/PRESENTERS-SPEECH.pdf` -> `delivery/[DECK_SLUG]-FINAL/PRESENTERS-SPEECH.pdf`
   - `working/presenter-speech/audio/PRESENTER-AUDIO.mp3` -> `delivery/[DECK_SLUG]-FINAL/PRESENTER-AUDIO.mp3`
   If any of the five source files does not exist or is empty: halt, notify the Director which artifact is missing, do NOT proceed to delivery.
3. **Run AF-DH1 (deliverable hygiene gate).** Enumerate every file in `delivery/[DECK_SLUG]-FINAL/`. For each file, check:
   a. **Whitelist check (primary):** Every file must match one of these exact name patterns: `*-FINAL.pptx`, `*-FINAL.pdf`, `PRESENTER-GUIDE.pdf`, `PRESENTERS-SPEECH.pdf`, `PRESENTER-AUDIO.mp3`. Any file not matching = AF-DH1 FAIL.
   b. **Blocklist check (belt-and-suspenders):** Fail immediately if any file matches: `*.py`, `*.log`, `*.txt` (prompt files), `*_manifest.json`, `*_qc_log.json`, `*_run.log`, `fix_*.py`, `run_*.py`, `write_*.py`, `validate_*.py`, `assemble_*.py`, `post_render*.py`, `*QC-FINAL.md`, `vision_qc_log.json`, `render_manifest.json`. Fail immediately if any of these directories exist inside the package: `working/`, `prompts/`, `images/`, `renders/`, `qc/`, `scripts/`, `checkpoints/`.
   c. **Format check:** Any PRESENTER-GUIDE or PRESENTERS-SPEECH file present as `.md` (not `.pdf`) = AF-DH1 FAIL.
   d. **Audio check:** PRESENTER-AUDIO.mp3 missing = AF-DH1 FAIL (also caught by AF-DELIVER; both gates are required).
4. **If AF-DH1 triggers:** halt all delivery. Record the failure in `working/checkpoints/delivery_plan.json` as `"af_dh1_triggered": true, "af_dh1_details": "<specific file or dir that failed>"`. Notify the Director: "AF-DH1: DELIVERY BLOCKED. Package hygiene fail: {details}. The client package must contain exactly the five allowed files. Remove all dev artifacts before re-running SOP 9.0." Do NOT proceed to SOP 9.1 until SOP 9.0 passes cleanly.
5. **If AF-DH1 passes:** record `"af_dh1_pass": true` in the delivery plan. Proceed to SOP 9.1.
6. **Mechanical confirmation (R9-F9):** the AF-DH1 whitelist + the GHL-upload record + the SOP 9.4 destination ground-truth are ALSO enforced mechanically by `python3 scripts/delivery_gate.py <run_dir>` (exit 0 = pass, 1 = fail). Run it before the SOP 9.3 notification; a non-zero exit BLOCKS `delivery_complete: true`. This coded enforcer backstops these otherwise doctrine-only autofails (AF-DH1 / AF-DELIVER / AF-DELIVERY-COMPLETE) — never rely on the SOP prose alone.

**Outputs:**
- `delivery/[DECK_SLUG]-FINAL/` (clean five-file package, AF-DH1 verified)
- `working/checkpoints/delivery_plan.json` (af_dh1_pass or af_dh1_triggered recorded)

**Hand to:** SOP 9.1 (Destination Resolution) -- only if AF-DH1 passed.

**Failure mode:** If any of the five required source files does not exist: halt immediately, notify the Director which artifact is missing. Check: (1) Was the PPTX Assembly Specialist's SOP 9.2 portable-document export run and recorded in render_log.json? (2) Did the Presenters Guide Specialist render PRESENTER-GUIDE.pdf? (3) Did the Presenters Speech Writer render PRESENTERS-SPEECH.pdf? (4) Did the Audio Demonstration Specialist produce PRESENTER-AUDIO.mp3? Each missing artifact routes back to its owning role.

---

### SOP 9.1 -- Destination Resolution

**When to run:** Immediately upon receiving a QC-passed PPTX from ROLE-08 (PPTX Assembly Specialist) via the Director of Presentations. This is the first step before any file is moved or uploaded.

**Inputs:**
- intake.json (client box type: `box_type: "mac"` or other; `use_drive: true/false`)
- working/checkpoints/media_library.json (ghl_folder_id, ghl_folder_name, version_number)
- working/qc/final_deck_qc.json (final QC score -- must confirm >= 8.5 before proceeding)

**Steps:**
1. Read intake.json. Check the `box_type` field.
2. **If `box_type` is `mac` (Mac mini or MacBook):**
   a. Primary destination: the folder `~/Downloads/<client-slug>-<deck-slug>/` on the client's Mac (the SAME folder-aware location `build_deck.py` writes to). The whole clean five-file CLIENT package lands here; verify anchor `~/Downloads/<client-slug>-<deck-slug>/<deck-slug>-FINAL.pptx`.
   b. Secondary destination: GHL media library (same `ghl_folder_id`/`"root"` resolved by the Media Librarian).
   c. Tertiary destination: Google Drive mirror folder (if `use_drive: true`).
   d. Record all destinations in a local `delivery_plan.json` before proceeding.
3. **If `box_type` is NOT mac, or is missing or unclear:**
   a. DO NOT assume a delivery location.
   b. Ask the client explicitly via `openclaw message send`: "Where would you like the PowerPoint delivered: email, Google Drive, GHL, or somewhere else?" Wait for their reply before proceeding.
   c. Record their stated destination in `delivery_plan.json`.
   d. Deliver only to the destination(s) they confirm.
   e. **Fallback file channel:** if the client has neither GHL (`has_ghl: false`) nor Drive (`use_drive: false`) and no other reachable file destination, add a `telegram_documents` destination so the five client files still reach them as document attachments (SOP 9.2). If even that is unreachable, hard-escalate "no reachable file channel" to the Director (never silently mark done).
4. Write `delivery_plan.json` to working/checkpoints/:
   ```json
   {
     "deck_slug": "...",
     "qc_score": 9.2,
     "destinations": [
       {"type": "mac_downloads", "dir": "~/Downloads/<client-slug>-<deck-slug>/", "verify_anchor": "~/Downloads/<client-slug>-<deck-slug>/<deck-slug>-FINAL.pptx", "status": "pending"},
       {"type": "ghl", "ghl_folder_id": "... or root", "remote_name": "[Deck Title] FINAL v<N>.pptx", "status": "pending"},
       {"type": "drive", "drive_folder_id": "...", "status": "pending"},
       {"type": "telegram_documents", "status": "pending"}
     ],
     "created_at": "ISO timestamp"
   }
   ```
5. Confirm the final QC score from working/qc/final_deck_qc.json. If score < 8.5: halt, return to Director. Record in delivery_plan.json: `"delivery_blocked": true, "reason": "QC score below threshold"`.

**Outputs:**
- working/checkpoints/delivery_plan.json (all destinations listed with pending status)

**Hand to:** SOP 9.2 (Multi-Destination Upload)

**Failure mode:** If intake.json is missing or malformed and box_type cannot be determined: ask the client directly before touching any destination. Never guess the delivery path. Record the blocker in delivery_plan.json and notify the Director.

---

### SOP 9.2 -- Multi-Destination Upload

**When to run:** Immediately after delivery_plan.json is written (SOP 9.1 complete). Run all deliveries; do not skip any destination in the plan.

**Inputs:**
- working/checkpoints/delivery_plan.json (all destinations; `af_dh1_pass` must be true before this SOP runs)
- delivery/[DECK_SLUG]-FINAL/ (the AF-DH1-verified clean FIVE-file CLIENT package -- copy/upload FROM here, NEVER from `output/`, `working/`, or the build root)
- media_library.json (ghl_folder_id `or "root"`, version_number)
- GHL **LOCATION** PIT from client's env stores; Google Drive credentials (if applicable)

> Every destination receives the ENTIRE five-file client package, not just the pptx: `<deck-slug>-FINAL.pptx`, `<deck-slug>-FINAL.pdf`, `PRESENTER-GUIDE.pdf`, `PRESENTERS-SPEECH.pdf`, `PRESENTER-AUDIO.mp3`.

**Steps (Mac Downloads destination):**
1. If `type: "mac_downloads"` is in delivery_plan.json:
   a. Copy the entire clean package into the folder-aware Downloads dir (the same dir the builder uses):
      ```bash
      mkdir -p ~/Downloads/<client-slug>-<deck-slug>/
      cp delivery/[DECK_SLUG]-FINAL/* ~/Downloads/<client-slug>-<deck-slug>/
      ```
   b. Verify: `ls -lh ~/Downloads/<client-slug>-<deck-slug>/<deck-slug>-FINAL.pptx` must return the file with a non-zero size; confirm all five files are present.
   c. Update delivery_plan.json for this destination: `"status": "uploaded", "files_copied": 5, "uploaded_at": "ISO timestamp"`.
   d. If the copy fails (permission error, disk full): record the error, notify the Director immediately. Continue with other destinations.

**Steps (GHL destination):**
1. If a GHL destination is in delivery_plan.json:
   a. Upload ALL FIVE files from `delivery/[DECK_SLUG]-FINAL/` via `POST /medias/upload-file` (LOCATION PIT Bearer, `Version: 2021-07-28`, multipart `file=@<each>`, `locationId`, `name`, `hosted=false`, and `parentId=<ghl_folder_id>` ONLY when it is a real folder id -- omit when `"root"`). Use the CLIENT's credentials, not the operator's. The pptx `name` is `[Deck Title] FINAL v<N>.pptx`.
   b. Record each returned `fileId` and `url`.
   c. Update delivery_plan.json: `"status": "uploaded", "ghl_media_ids": {"pptx":"...","pdf":"...","guide":"...","speech":"...","audio":"..."}, "uploaded_at": "ISO timestamp"`.
   d. Update media_library.json: `"pptx_ghl_media_id": "...", "pptx_ghl_remote_name": "[Deck Title] FINAL v<N>.pptx"`.
   e. If any GHL upload fails: retry once after 30 seconds. If the second attempt fails: mark status `"failed"`, log the error, notify the Director. Do not send a notification until resolved or overridden.

**Steps (Google Drive destination):**
1. If `use_drive: true` and a Drive destination is in delivery_plan.json:
   a. Upload ALL FIVE files from `delivery/[DECK_SLUG]-FINAL/` to the client's Drive folder (drive_folder_id from media_library.json).
   b. Record each Drive file_id.
   c. Update delivery_plan.json: `"status": "uploaded", "drive_file_ids": {...}, "uploaded_at": "ISO timestamp"`.
   d. If a Drive upload fails: retry once after 30 seconds. If the second attempt fails: mark status `"failed"` and notify the Director.

**Steps (Telegram-documents fallback -- no GHL, no Drive, no other file channel):**
1. If `type: "telegram_documents"` is in delivery_plan.json:
   a. Send each of the five files in `delivery/[DECK_SLUG]-FINAL/` to the client as a DOCUMENT attachment via `openclaw message send` (NEVER the raw Telegram API).
   b. Update delivery_plan.json: `"status": "uploaded", "telegram_files_sent": 5, "uploaded_at": "ISO timestamp"`.
   c. If `openclaw message send` cannot attach files on this box, hard-escalate "no reachable file channel" to the Director and hold delivery.

**Outputs:**
- The five-file client package at every successfully delivered destination
- delivery_plan.json (updated with uploaded status and IDs for each destination)
- media_library.json (updated with pptx_ghl_media_id)

**Hand to:** SOP 9.3 (Notification) and SOP 9.4 (Ground-Truth Verification) -- run SOP 9.4 first, then SOP 9.3.

**Failure mode:** If the clean package `delivery/[DECK_SLUG]-FINAL/` is missing, incomplete, or any file is zero size: halt all delivery. Notify the Director: "Delivery blocked: the clean client package is missing or incomplete. Re-run SOP 9.0." Never deliver from `output/` or `working/` directly.

---

### SOP 9.3 -- Notification

**When to run:** After SOP 9.4 (Ground-Truth Verification) passes. Never send the delivery notification before SOP 9.4 confirms every destination.

**Inputs:**
- working/checkpoints/delivery_plan.json (all destinations with verified status)
- working/qc/final_deck_qc.json (final QC score)
- working/checkpoints/media_library.json (ghl_folder_name for human-readable reference)

**Steps:**
1. Confirm SOP 9.4 has completed and all destinations in delivery_plan.json show `"status": "verified"`. If any destination is not verified: do not send the notification. Halt until resolution.
2. Compose the delivery notification. Include:
   a. Every verified destination path or URL (human-readable).
   b. The final QC score.
   c. Example notification text (adapt per actual destinations):
      "Your webinar deck is ready. Final QC score: [SCORE]/10. File locations: (1) the folder ~/Downloads/<client-slug>-<deck-slug>/ on your Mac (deck, PDF, presenter guide, speech, and audio), (2) GHL media library as '[REMOTE_NAME]'. Both locations confirmed."
3. Send the notification using `openclaw message send` to the client's normal channel.
   - NEVER use the raw Telegram API (curl to api.telegram.org or equivalent).
   - NEVER use a hardcoded channel ID or token outside of OpenClaw's message routing.
4. Record the notification timestamp in media_library.json: `"delivery_notification_sent_at": "ISO timestamp"`.

**Outputs:**
- Delivery notification sent to the client via `openclaw message send`
- media_library.json updated with delivery_notification_sent_at

**Hand to:** Director of Presentations (run complete signal)

**Failure mode:** If `openclaw message send` fails: retry once. If the second attempt fails: notify the Director via the Director's channel (not the client's). Log the failure in media_library.json: `"delivery_notification_failed": true, "notification_error": "..."`. The delivery is complete (files are at their destinations) but the client has not been notified -- this is a partial success. The Director must resolve the notification path.

---

### SOP 9.4 -- Ground-Truth Verification

**When to run:** After all destinations have been uploaded (SOP 9.2 complete for all destinations). Run before SOP 9.3. Verification must pass before the notification is sent.

**Inputs:**
- working/checkpoints/delivery_plan.json (all destinations with uploaded status and IDs)
- GHL API (live call -- not a self-report)
- File system (live check -- not a cached result)

**Steps:**
1. **Mac Downloads verification (if applicable):**
   a. Run: `ls -lh ~/Downloads/<client-slug>-<deck-slug>/`.
   b. All FIVE client files must exist and be non-zero, specifically `~/Downloads/<client-slug>-<deck-slug>/<deck-slug>-FINAL.pptx`. A missing or zero-byte file is a verification failure.
   c. Update delivery_plan.json: `"status": "verified", "verified_at": "ISO timestamp", "files_verified": 5` for this destination.

2. **GHL verification (if applicable):**
   a. Call the GHL API: fetch the file record for EACH of the five uploaded media ids in delivery_plan.json.
   b. Each must return a file record with a non-null `url`. Any 404 or empty response for any of the five is a verification failure.
   c. A self-report ("I uploaded it") is NOT sufficient. An API confirmation per file is required.
   d. Update delivery_plan.json: `"status": "verified", "verified_at": "ISO timestamp", "files_verified": 5` for this destination.

3. **Google Drive verification (if applicable):**
   a. Call the Drive API: fetch the file metadata for EACH of the five uploaded file ids in delivery_plan.json.
   b. Each must return metadata with a non-null name and size. Any 404 or empty response is a verification failure.
   c. Update delivery_plan.json: `"status": "verified", "verified_at": "ISO timestamp", "files_verified": 5` for this destination.

4. **Telegram-documents verification (if applicable):**
   a. Confirm the send result reported success for all five document attachments (the `openclaw message send` result, not a self-report). Any failed attachment is a verification failure -- re-send once, then escalate.
   b. Update delivery_plan.json: `"status": "verified", "verified_at": "ISO timestamp", "files_verified": 5` for this destination.

5. **Final check:**
   a. Every destination in delivery_plan.json must show `"status": "verified"`.
   b. If all destinations are verified: write to media_library.json:
      ```json
      {
        "delivery_complete": true,
        "delivery_verified_at": "ISO timestamp",
        "delivery_destinations": [
          {"type": "mac_downloads", "dir": "~/Downloads/<client-slug>-<deck-slug>/", "files_verified": 5, "verified": true},
          {"type": "ghl", "pptx_ghl_media_id": "...", "files_verified": 5, "verified": true},
          {"type": "drive", "files_verified": 5, "verified": true}
        ]
      }
      ```
   c. If any destination fails verification: see Failure mode below.

**Outputs:**
- delivery_plan.json (all destinations at "verified" status)
- media_library.json (delivery_complete: true, all destination records with verified: true)

**Hand to:** SOP 9.3 (Notification -- now cleared to send)

**Failure mode:** If any destination fails verification after the upload step:
1. Attempt a one-time re-upload for the failed destination.
2. Re-verify after the re-upload attempt.
3. If verification still fails: mark that destination `"status": "verification_failed"` in delivery_plan.json. Do NOT set `delivery_complete: true`. Notify the Director: "Delivery incomplete: [destination type] could not be verified. Error: [specific error]. Files at other destinations are confirmed. Awaiting resolution." Never send the client a "done" notification when a destination is unverified.

---

### SOP 9.5 -- Teleprompter Publish + Link Delivery

**When to run:** During SOP 9.2 (Multi-Destination Upload), as a dedicated destination. The teleprompter is a hosted web app, not a downloaded file -- it is delivered as a LINK, not a copy. The deck is not "done" until the teleprompter link is published, verified live, delivered to the client, and filed in GHL.

**Why this exists:** A self-contained `presenter-teleprompter.html` on disk is NOT a delivered teleprompter. The client needs a hosted URL they can open in any browser to read their speech live. `build_deck.py`'s postflight gate (AF-BUNDLE-COMPLETE, which folds in the TELEPROMPTER-PUBLISH sub-check) hard-fails (exit 5) until the teleprompter is published with a verified live public URL, so this step can never be silently skipped.

**Inputs:**
- `<bundle_dir>/presenter-teleprompter.html` (self-contained app; produced by `build_teleprompter.py`, owned by the Presenter's Speech Writer)
- `<bundle_dir>/teleprompter_publish.json` (written by `build_deck.py`'s `publish_teleprompter()` if it already ran; this SOP re-runs/repairs the publish if absent or unverified)
- The FLEET Cloudflare token `CLOUDFLARE_ZHW_APPS_API_TOKEN` (operator/fleet infra -- NOT a client key, never printed) for the upload to the central host
- `CLOUDFLARE_ZHW_ACCOUNT_ID` (operator/fleet infra -- the Zero Human Workforce Cloudflare account ID, set ONCE in `~/clawd/secrets/.env` by the operator; NEVER written by per-client onboarding scripts such as `13-create-cloudflare-tunnel.sh` or `23-save-secrets.sh`). This is DISTINCT from the per-client `CLOUDFLARE_ACCOUNT_ID` (the client's own Cloudflare tunnel account). The R2 PutObject for the `zhw-teleprompter` bucket MUST use `CLOUDFLARE_ZHW_ACCOUNT_ID`; using the generic `CLOUDFLARE_ACCOUNT_ID` here will target the wrong account and cause a hard publish failure if a per-client token was active during onboarding.

**Host (UNIFORM -- every client, Mac and VPS):** the central Cloudflare host at
`https://teleprompter.zerohumanworkforce.com/<client-slug>/<deck-slug>/teleprompter.html`
(an R2 bucket fronted by the `zhw-teleprompter` Worker, gated by Cloudflare Access). There is ONE host so the link works identically everywhere. `intake.json` `box_type` (mac vs vps) is recorded for the audit trail only; it does NOT change the host.

**Steps:**
1. If `build_deck.py` already ran and `teleprompter_publish.json` shows `status: "published"` with a verified `public_url`, this step is already satisfied -- proceed to step 5. Otherwise continue.
2. Publish the HTML to the central Cloudflare host (R2 PutObject of the self-contained file). Capture the resulting public URL.
3. **Ground-truth verify (no self-report):** live HTTP GET on the public URL. It MUST return HTTP 200 with a non-empty body. A 403/404/timeout is a publish failure -- retry once, then escalate to the Director.
4. Write/refresh `<bundle_dir>/teleprompter_publish.json` with `public_url`, `platform`, `host_target: "cloudflare-central"`, `verified_http_status: 200`, `verified_at`, `status: "published"`.
5. **File the link in GHL:** hand the verified teleprompter public URL to the Media Librarian (ROLE-06 SOP 9.7) to record in `media_library.json.teleprompter_public_url` and file in the deck's GHL media library record.
6. **Deliver the link to the client (Telegram):** include the teleprompter public URL in the SOP 9.3 notification, sent via `openclaw message send` (NEVER raw Telegram API), labeled as the live scrolling teleprompter -- "(N) Teleprompter (live): <public_url> -- open this link in any browser to read your speech live." The link is one of the verified destinations checked in SOP 9.4.

**Outputs:** `teleprompter_publish.json` (status `published`, verified URL); `media_library.json.teleprompter_public_url`; the URL included in the SOP 9.3 client notification.

**Hand to:** SOP 9.4 (Ground-Truth Verification -- the teleprompter URL is one of the verified destinations) and SOP 9.3 (Notification -- the link is delivered to the client via `openclaw message send`).

**Failure mode:** If the publish or the live-200 verify fails after one retry: mark `teleprompter_publish.json` `status: "verify_failed"`, do NOT send the notification with a dead link, and notify the Director: "Teleprompter publish unverified: [platform] [error]." The postflight gate (AF-BUNDLE-COMPLETE / TELEPROMPTER-PUBLISH sub-check) and AF-DELIVERY-COMPLETE keep the run from "Done" until the link is live. Never deliver a teleprompter as a local file copy and never deliver a dead/unverified link.

---
