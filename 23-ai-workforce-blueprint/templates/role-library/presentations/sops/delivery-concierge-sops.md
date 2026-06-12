# SOPs Mirror -- Delivery Concierge

**Source:** presentations/delivery-concierge.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md

### SOP 9.1 -- Destination Resolution

**When to run:** Immediately upon receiving a QC-passed PPTX from ROLE-08 (PPTX Assembly Specialist) via the Director of Presentations. This is the first step before any file is moved or uploaded.

**Inputs:**
- intake.json (client box type: `box_type: "mac"` or other; `use_drive: true/false`)
- working/checkpoints/media_library.json (ghl_folder_id, ghl_folder_name, version_number)
- working/qc/final_deck_qc.md (final QC score -- must confirm >= 8.5 before proceeding)

**Steps:**
1. Read intake.json. Check the `box_type` field.
2. **If `box_type` is `mac` (Mac mini or MacBook):**
   a. Primary destination: `~/Downloads/[DECK_SLUG]_final.pptx` on the client's Mac.
   b. Secondary destination: GHL media library (same folder used for slide images, per ghl_folder_id in media_library.json).
   c. Tertiary destination: Google Drive mirror folder (if `use_drive: true`).
   d. Record all three destinations in a local `delivery_plan.json` before proceeding.
3. **If `box_type` is NOT mac, or is missing or unclear:**
   a. DO NOT assume a delivery location.
   b. Ask the client explicitly via `openclaw message send`: "Where would you like the PowerPoint delivered: email, Google Drive, GHL, or somewhere else?" Wait for their reply before proceeding.
   c. Record their stated destination in `delivery_plan.json`.
   d. Deliver only to the destination(s) they confirm.
4. Write `delivery_plan.json` to working/checkpoints/:
   ```json
   {
     "deck_slug": "...",
     "qc_score": 9.2,
     "destinations": [
       {"type": "mac_downloads", "path": "~/Downloads/[DECK_SLUG]_final.pptx", "status": "pending"},
       {"type": "ghl", "ghl_folder_id": "...", "remote_name": "[Deck Title] FINAL v<N>.pptx", "status": "pending"},
       {"type": "drive", "drive_folder_id": "...", "status": "pending"}
     ],
     "created_at": "ISO timestamp"
   }
   ```
5. Confirm the final QC score from working/qc/final_deck_qc.md. If score < 8.5: halt, return to Director. Record in delivery_plan.json: `"delivery_blocked": true, "reason": "QC score below threshold"`.

**Outputs:**
- working/checkpoints/delivery_plan.json (all destinations listed with pending status)

**Hand to:** SOP 9.2 (Multi-Destination Upload)

**Failure mode:** If intake.json is missing or malformed and box_type cannot be determined: ask the client directly before touching any destination. Never guess the delivery path. Record the blocker in delivery_plan.json and notify the Director.

---

### SOP 9.2 -- Multi-Destination Upload

**When to run:** Immediately after delivery_plan.json is written (SOP 9.1 complete). Run all deliveries; do not skip any destination in the plan.

**Inputs:**
- working/checkpoints/delivery_plan.json (all destinations)
- output/[DECK_SLUG].pptx (the QC-passed assembled deck)
- media_library.json (ghl_folder_id, version_number)
- GHL credentials from client's env stores
- Google Drive credentials (if applicable)

**Steps (Mac Downloads destination):**
1. If `type: "mac_downloads"` is in delivery_plan.json:
   a. Copy the PPTX to the client's Downloads folder:
      ```bash
      cp output/[DECK_SLUG].pptx ~/Downloads/[DECK_SLUG]_final.pptx
      ```
   b. Verify: `ls -lh ~/Downloads/[DECK_SLUG]_final.pptx` must return the file with a non-zero size.
   c. Update delivery_plan.json for this destination: `"status": "uploaded", "verified_size_bytes": N, "uploaded_at": "ISO timestamp"`.
   d. If the copy fails (permission error, disk full): record the error, notify the Director immediately. Continue with other destinations.

**Steps (GHL destination):**
1. If a GHL destination is in delivery_plan.json:
   a. GHL remote name: `[Deck Title] FINAL v<N>.pptx` (use version_number from media_library.json).
   b. Call the GHL upload API: upload output/[DECK_SLUG].pptx to the GHL folder (ghl_folder_id). Use the CLIENT's GHL credentials, not the operator's.
   c. Record the GHL media_id returned by the API.
   d. Update delivery_plan.json: `"status": "uploaded", "ghl_media_id": "...", "uploaded_at": "ISO timestamp"`.
   e. Update media_library.json: `"pptx_ghl_media_id": "...", "pptx_ghl_remote_name": "[Deck Title] FINAL v<N>.pptx"`.
   f. If the GHL upload fails: retry once after 30 seconds. If the second attempt fails: mark status `"failed"`, log the error, and notify the Director. Do not send a delivery notification until the failure is resolved or explicitly overridden by the Director.

**Steps (Google Drive destination):**
1. If `use_drive: true` and a Drive destination is in delivery_plan.json:
   a. Upload output/[DECK_SLUG].pptx to the client's Drive folder (drive_folder_id from media_library.json).
   b. Record the Drive file_id returned by the API.
   c. Update delivery_plan.json: `"status": "uploaded", "drive_file_id": "...", "uploaded_at": "ISO timestamp"`.
   d. If the Drive upload fails: retry once after 30 seconds. If the second attempt fails: mark status `"failed"` and notify the Director.

**Outputs:**
- PPTX file at every successfully uploaded destination
- delivery_plan.json (updated with uploaded status and IDs for each destination)
- media_library.json (updated with pptx_ghl_media_id)

**Hand to:** SOP 9.3 (Notification) and SOP 9.4 (Ground-Truth Verification) -- run SOP 9.4 first, then SOP 9.3.

**Failure mode:** If the output PPTX file is missing or has zero size at output/[DECK_SLUG].pptx: halt all delivery immediately. Notify the Director: "Delivery blocked: output/[DECK_SLUG].pptx is missing or empty. PPTX Assembly Specialist must re-verify assembly." Do not attempt delivery of a missing or empty file.

---

### SOP 9.3 -- Notification

**When to run:** After SOP 9.4 (Ground-Truth Verification) passes. Never send the delivery notification before SOP 9.4 confirms every destination.

**Inputs:**
- working/checkpoints/delivery_plan.json (all destinations with verified status)
- working/qc/final_deck_qc.md (final QC score)
- working/checkpoints/media_library.json (ghl_folder_name for human-readable reference)

**Steps:**
1. Confirm SOP 9.4 has completed and all destinations in delivery_plan.json show `"status": "verified"`. If any destination is not verified: do not send the notification. Halt until resolution.
2. Compose the delivery notification. Include:
   a. Every verified destination path or URL (human-readable).
   b. The final QC score.
   c. Example notification text (adapt per actual destinations):
      "Your webinar deck is ready. Final QC score: [SCORE]/10. File locations: (1) ~/Downloads/[DECK_SLUG]_final.pptx on your Mac, (2) GHL media library folder '[FOLDER_NAME]' as '[REMOTE_NAME]'. Both locations confirmed."
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
   a. Run: `ls -lh ~/Downloads/[DECK_SLUG]_final.pptx`.
   b. The file must exist and show a non-zero size. A missing file or a zero-byte file is a verification failure.
   c. Update delivery_plan.json: `"status": "verified", "verified_at": "ISO timestamp"` for this destination.

2. **GHL verification (if applicable):**
   a. Call the GHL API: fetch the file record by ghl_media_id from delivery_plan.json.
   b. The API must return the file record with a non-null URL. A 404 or empty response is a verification failure.
   c. A self-report ("I uploaded it") is NOT sufficient. An API confirmation is required.
   d. Update delivery_plan.json: `"status": "verified", "verified_at": "ISO timestamp"` for this destination.

3. **Google Drive verification (if applicable):**
   a. Call the Drive API: fetch the file metadata by drive_file_id from delivery_plan.json.
   b. The API must return the file metadata with a non-null name and size. A 404 or empty response is a verification failure.
   c. Update delivery_plan.json: `"status": "verified", "verified_at": "ISO timestamp"` for this destination.

4. **Final check:**
   a. Every destination in delivery_plan.json must show `"status": "verified"`.
   b. If all destinations are verified: write to media_library.json:
      ```json
      {
        "delivery_complete": true,
        "delivery_verified_at": "ISO timestamp",
        "delivery_destinations": [
          {"type": "mac_downloads", "path": "~/Downloads/[DECK_SLUG]_final.pptx", "verified": true},
          {"type": "ghl", "ghl_media_id": "...", "remote_name": "...", "verified": true},
          {"type": "drive", "drive_file_id": "...", "verified": true}
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
