# SOP-GIP-03 — Finished-Asset GHL Media Delivery (BINDING)

**ID:** SOP-GIP-03
**Classification:** ZHC SOP — Graphics Image Protocol (GIP)
**Owner Role:** Asset & Provenance Librarian ("The Vault")
**Version:** 1.0 | **Date:** 2026-07-10
**Status:** CANONICAL
**Library-version pin:** MODEL-SPECS v1.4; canonical GHL media module
`48-facebook-ad-generator/tools/ghl_media.py` (§-refs verified 2026-07-10)

---

## Why this exists

The Graphics department's `connection-manifest.json` REQUIRES `GOHIGHLEVEL_API_KEY` +
`GOHIGHLEVEL_LOCATION_ID` "for uploading finished graphics assets to the GHL media library", but no
graphics role, SOP, or script implemented finished-asset upload — the manifest promised a pipeline that
did not exist (diagnosis G3). This SOP + `graphics_ghl_push.py` are that pipeline, ported thin from the
Presentations department so both share the ONE canonical, verified-working REST module (never fork the
folder-create / upload-file calls).

---

## The three MANDATORY actions

For every client job with GHL enabled, the THREE actions are MANDATORY and recorded in
`<job>/media_library.json` (the canonical ledger the closeout gate reads):

1. **Per-job folder resolved** — `ghl_folder_id` from `create_media_folder`
   (POST `/medias/folder`, LOCATION PIT, `Version: 2021-07-28`), or `"root"` (a PASSING fallback).
   Null/empty = unset seed, does NOT satisfy the gate.
2. **Per-asset upload** — every QC-passed asset (from `<job>/qc/image_qc_report.json`, only `pass:true`
   with zero auto-fails) carries `ghl_media_id` + `ghl_upload_status:"complete"` + the public `url`
   returned by `/medias/upload-file`.
3. **Link-back** — the public URLs are written into the provenance sidecar (`ghl_media_id` +
   `ghl_public_url`, additive-only per SOP 9.5) and returned to the requesting department/client in the
   delivery message.

Post-upload liveness: `graphics_ghl_push.py` GETs each returned public URL and records
`liveness.live` (expect HTTP 200 with a non-empty body — the Vault's url-liveness law, SOP 9.2 step 3).

---

## The gate

```
python3 45-design-intelligence-library/scripts/graphics_ghl_push.py --gate --job-dir <dir>
```

Exit 0 pass / 1 fail. The gate HARD-FAILS unless `media_library.json` records a resolved `ghl_folder_id`
AND every QC-passed asset uploaded with a real `ghl_media_id` + `ghl_upload_status:"complete"` (the
graphics AF-DELIVERY-COMPLETE). **No defer-to-pass.** The ONLY bypass is a logged `owner_skip_approval`
token in `<job>/checkpoints/process_manifest.json` (`owner_approved:true` + `approved_by` + `reason` + a
matching gate name); an agent setting `has_ghl:false` on its own does NOT skip the gate.

**NEVER drive the GHL web UI in a browser.** Client jobs use the CLIENT's LOCATION PIT from the client's
env stores (`GOHIGHLEVEL_API_KEY` / `GHL_API_KEY`), never the operator's key, never an agency PIT (the
agency PIT 401s for media).

---

## Management cadence (owned by the Asset & Provenance Librarian)

- **Weekly:** confirm job folders still exist / are accessible (clients can delete them; flag to CDO).
- **Monthly:** folder-naming audit `<Client> Graphics <Job> v<N>`.
- **Never delete, archive only.**

**Hand to:** the requesting department / client (delivery message with the public URLs) after the gate
passes; CDO on any liveness or deletion anomaly.
