# SOP-DIU-609 — Reference & Identity Media Hosting

**ID:** SOP-DIU-609
**Classification:** ZHC SOP — thin wrapper
**Owner Role:** Photo Shoot Director (primary); Generation Operator (co-owner — executes the hosting steps before each `createTask` call)
**Section 9 slot:** 9.7
**Version:** 1.0 | **Date:** 2026-06-12
**Status:** CANONICAL
**Library-version pin:** MODEL-SPECS v1.2, PHOTO-SHOOT-SOP v1.0 (§-refs verified 2026-06-12)

---

## Role Mission

Every Kie.ai reference-image parameter (`input_urls`, `image_input`, `image_urls`) requires a publicly reachable HTTPS URL at submit time. Client reference images live on Mac minis behind Cloudflare tunnels — they are never publicly reachable at rest. This SOP closes the hosting gap with a tiered ladder that keeps identity and likeness data off public CDNs permanently.

**Hard rule:** ANY image containing a real person's likeness must use client-owned hosting only. Identity references are never uploaded to public third-party image hosts, never given permanent URLs, and never committed to git in any form. Non-person assets may use the existing ImgBB ephemeral-upload flow. Both paths require size and format validation before upload and verified deletion after job completion.

The Photo Shoot Director owns the hosting policy and consent gate; the Generation Operator executes the upload steps as part of its SOP-DIU-601 preflight sequence.

---

## Governing Library Files (source-of-truth — do NOT duplicate content)

| File | Sections used | What it governs |
|---|---|---|
| `_system/MODEL-SPECS.md` | §1 (reference-image size limits per endpoint — 30MB for GPT-I2I/NB2; 10MB for Seedream/Wan), §5.2 (`input_urls` — GPT-Image 2 I2I), §5.3 (`image_input` — Nano Banana 2), §5.5 (`image_urls` — Seedream 4.5 Edit) | Authoritative file-size caps and per-endpoint reference param names; do not duplicate size limits here |
| `_system/PHOTO-SHOOT-SOP.md` | §2 (identity-sourcing hierarchy — the four source tiers and verification requirement), §3 (IDENTITY.md schema — reference image paths and quality notes) | How refs are located; where verified hosted URLs are written back |
| `45-design-intelligence-library/` → `07-kie-setup/` | Media-librarian pattern (GHL media library as client-owned hosting) | GHL media library as the approved identity-ref hosting target |
| `templates/role-library/presentations/` → `media-librarian` pattern | ImgBB ephemeral-upload flow reference | Non-person asset upload procedure |

All size limits and endpoint param names are read from MODEL-SPECS at runtime. Do not encode megabyte values directly in this SOP.

---

## Procedure (ordered)

### A. Classify the reference images (Photo Shoot Director — before any upload)

1. **Determine whether any image contains a real person's likeness.** A real person includes the client, any named individual, and any face that is recognizably a specific person even if unnamed.
   - Likeness present → follow **Path L (Identity Hosting)** below.
   - No likeness (style swatches, logo assets, product photos without people, abstract textures) → follow **Path N (Non-Person Hosting)** below.

2. **Verify consent is active** for every likeness before any upload step. Read the consent record at `_local/consent/{client-id}.json` (schema per SOP-DIU-608). Status must be `active`. If status is `none`, `pending`, `expired`, or `revoked`: halt this shoot, notify the Photo Shoot Director and CDO, do not upload. Consent check is not delegated to the Generation Operator.

3. **Record the classification decision** in the current shoot record at `_local/shoots/{shoot-id}/shoot-record.json` as `hosting_path: "identity"` or `hosting_path: "non-person"`. Write this before any upload.

### B. Size and format pre-validation (both paths — Generation Operator)

Run these checks against every candidate image file before any upload call. Any failure = hard stop, return itemized list to Photo Shoot Director.

1. **File size.** Look up the resolved endpoint in MODEL-SPECS §1 to get the applicable size cap. Verify each file is strictly under the cap. Return `HOSTING FAIL: {filename} is {actual_size} — exceeds {cap} cap for {endpoint}` if over. Do not compress and silently retry — return the failure to the Photo Shoot Director for decision.

2. **Format.** Confirm each file is jpeg, jpg, png, or webp (the formats listed in MODEL-SPECS §1 for reference inputs). Return `HOSTING FAIL: {filename} is unsupported format {ext}` for any other extension.

3. **Readable.** Open and decode each file to confirm it is not corrupted. Return `HOSTING FAIL: {filename} unreadable or corrupted` if decoding fails.

4. Log all checks in the shoot record as `preflight_hosting_validated: true` with timestamp.

### C. Path L — Identity Hosting (any real-person likeness)

1. **Upload to the client's GHL media library** via the GHL MCP media-library upload endpoint. The GHL media library is client-owned, access-gated, and serves URLs over the client's own domain — it satisfies the client-owned hosting requirement.

2. **One upload per image.** Write the returned URL to `_local/shoots/{shoot-id}/hosted-refs.json` as a per-image entry:
   ```
   {
     "source_filename": "{original filename}",
     "hosted_url": "{GHL media library URL}",
     "hosting_path": "identity",
     "uploaded_at": "{iso8601}",
     "ghl_media_id": "{GHL asset ID for deletion}"
   }
   ```

3. **URL-liveness check.** Immediately after each upload, perform a HEAD request against the returned URL. A non-200 response is a hard stop — do not submit the Kie.ai task with an unreachable reference URL. Escalate to CDO if the GHL media library is unreachable.

4. **Pass hosted URLs to the Generation Operator.** The Operator populates the correct Kie.ai endpoint param (`input_urls`, `image_input`, or `image_urls` per MODEL-SPECS §5.2/5.3/5.5) using only the verified hosted URLs from `hosted-refs.json`. The Operator never uses a local file path or CF-tunnel URL as a Kie.ai reference param.

5. **Deletion is mandatory.** After the Kie.ai task reaches `state: success` and postflight verification is complete (SOP-DIU-601), the Generation Operator calls the GHL MCP deletion endpoint using the `ghl_media_id` recorded in step 2. Record the deletion result in `hosted-refs.json` as `deleted_at: "{iso8601}"`. A hosted identity reference that has not been deleted within 24 hours of job completion is an escalation trigger (see below).

6. **Log deletion in shoot record.** Update `_local/shoots/{shoot-id}/shoot-record.json` with `identity_refs_deleted: true` and `deleted_at`. This is the audit trail for consent revocation, licensing audits, and SOP-DIU-610 rights manifest entries.

### D. Path N — Non-Person Hosting (no real-person likeness confirmed)

1. **Use the existing ImgBB ephemeral-upload flow** per the ai-image-generator-specialist precedent (presentations media-librarian pattern). ImgBB is acceptable for non-person assets because no identity or consent record is implicated.

2. **Set the shortest available expiry.** Use ImgBB's ephemeral URL option — permanent ImgBB URLs are not used even for non-person assets.

3. **Write the returned URL** to `_local/shoots/{shoot-id}/hosted-refs.json` with `hosting_path: "non-person"` and the ImgBB delete hash.

4. **URL-liveness check.** Same as Path L step 3: HEAD request before submit.

5. **Deletion after job completion.** Call the ImgBB delete endpoint using the stored delete hash after postflight verification passes. Record `deleted_at` in `hosted-refs.json`.

### E. Job completion and audit close-out

1. After every task that used hosted references: confirm all Path L entries have `deleted_at` populated. Confirm all Path N entries have `deleted_at` populated.

2. Write a `hosting_closed: true` entry to the shoot record with the closing timestamp.

3. Pass the `hosted-refs.json` path to the Photo Shoot Director for inclusion in the SOP-DIU-610 Rights Manifest entry for this shoot.

---

## Inputs

| Input | Required | Source |
|---|---|---|
| Reference image files (local paths on the client box) | Yes | PHOTO-SHOOT-SOP §2 sourcing hierarchy — already verified by Photo Shoot Director |
| Consent record for every likeness image | Yes | `_local/consent/{client-id}.json` via SOP-DIU-608 |
| Resolved Kie.ai endpoint (determines size cap) | Yes | MODEL-SPECS §2 routing decision (SOP-DIU-302) |
| Shoot record (`shoot-record.json`) | Yes | Created at shoot open; written by Photo Shoot Director |
| GHL MCP credentials (client box) | Yes (Path L) | Client box env stores — GHL_API_KEY / location ID |
| ImgBB API key (client box) | Yes (Path N) | Client box env stores |

---

## Outputs

| Output | Location | State at exit |
|---|---|---|
| `hosted-refs.json` (per-image upload records with hosted URLs) | `_local/shoots/{shoot-id}/hosted-refs.json` | Written before Kie.ai submission; `deleted_at` populated after job completion |
| Shoot record (`shoot-record.json`) updated with hosting classification, preflight result, and deletion close-out | `_local/shoots/{shoot-id}/shoot-record.json` | Updated at each gate |
| Verified hosted URLs | Passed to Generation Operator's Kie.ai JSON template | Populated in `input_urls` / `image_input` / `image_urls` per MODEL-SPECS §5.2/5.3/5.5 |
| Deletion receipts (GHL media ID or ImgBB delete hash, `deleted_at`) | `hosted-refs.json` | Written at deletion confirmation |

---

## Handoff Conditions

- **Hosting validated and URLs live:** Generation Operator receives `hosted-refs.json` with verified URLs and populates the Kie.ai template. Preflight continues per SOP-DIU-601.
- **Job completed and postflight passed (SOP-DIU-601):** Generation Operator immediately triggers deletion for all hosted refs. Photo Shoot Director receives the closed `hosted-refs.json` for inclusion in the SOP-DIU-610 Rights Manifest.
- **Hosting pre-validation failure:** Itemized failure list returned to Photo Shoot Director. No upload. No Kie.ai submission. Operator does not resize or reformat — returns to Photo Shoot Director for decision.
- **Consent not active:** Photo Shoot Director and CDO notified. Shoot halted. No upload under any circumstances until consent record is updated.

---

## Escalation Triggers

| Condition | Action |
|---|---|
| Consent status is not `active` for a likeness image | Hard stop. Halt the entire shoot. Notify Photo Shoot Director and CDO. No upload, no generation. |
| File exceeds MODEL-SPECS §1 size cap for the resolved endpoint | Hard stop. Return `HOSTING FAIL` with filename, actual size, and cap. Do not compress silently. Return to Photo Shoot Director. |
| URL-liveness check fails after upload (non-200 HEAD response) | Hard stop. Do not submit Kie.ai task with an unreachable URL. Escalate to CDO if hosting service is unreachable. |
| GHL media library unreachable (Path L) | Hard stop. Identity refs cannot be hosted on public third-party services. Escalate to CDO. Do not fall back to ImgBB for identity refs under any circumstance. |
| Identity reference uploaded to a non-client-owned host (detected post-hoc) | Immediate CDO escalation. Attempt to delete from the non-owned host immediately using any available deletion token. Log as a hosting incident in the shoot record. Notify Photo Shoot Director. |
| `deleted_at` not populated within 24 hours of job completion (Path L) | SOP-DIU-615 Healer-Graphics integrity sweep flags this. Escalate to Photo Shoot Director and CDO. Retry deletion immediately. |
| `hosted-refs.json` missing or `hosting_closed: true` absent when shoot record is inspected by SOP-DIU-615 | Flag as an open hosting audit gap. Escalate to Photo Shoot Director for close-out. |
| GHL or ImgBB API credentials absent from all env stores | Hard stop. Search every env store before reporting missing (secrets/.env, openclaw.json, ~/.openclaw/workspace/.env, ~/clawd/secrets/.env, running gateway process env). Escalate to CDO only after all stores checked. |

---

## What Identity References May Never Do

- Be uploaded to ImgBB, Cloudinary, or any public third-party image host
- Be given permanent URLs (even on client-owned hosting, URLs are temporary and deleted after job completion)
- Be committed to git in any form, including as base64 strings in JSON
- Be passed as local file paths or CF-tunnel URLs to any external API
- Be reused across shoots without re-verifying consent status at the time of each new upload
- Remain hosted beyond 24 hours after job completion without CDO written direction

---

*Library-version pin: MODEL-SPECS v1.2, PHOTO-SHOOT-SOP v1.0 (§-refs verified 2026-06-12).*
