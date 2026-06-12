# SOP-DIU-612 — Cross-Department Style Request Block

**ID:** SOP-DIU-612
**Classification:** ZHC SOP — thin wrapper
**Owner Role:** Chief Design Officer
**Version:** 1.0 | **Date:** 2026-06-12
**Status:** CANONICAL
**Library-version pin:** MASTER-SOP v1.0, MODEL-SPECS v1.0, PHOTO-SHOOT-SOP v1.0 (§-refs verified 2026-06-12)

---

## Role Mission

The Chief Design Officer is the sole intake point for every cross-department request that asks graphics to produce a DIU-generated asset. No department reaches the Generation Operator directly. The CDO validates the required STYLE block, routes any likeness-flagged request through the Photo Shoot Director consent gate before any other processing begins, resolves every style ID against INDEX.md before any assembly packet is built, and returns a standard provenance bundle to the requesting department on delivery. Campaign version pins are recorded at intake and expiry notifications sent before any default-version change affects active campaigns.

This SOP closes the cross-department likeness bypass: a Social Media request carrying a client's face must hit the same consent gate as a formal photo shoot, regardless of which department submitted the request.

---

## Governing Library Files (source-of-truth — do NOT duplicate content)

| File | Sections used | What it governs |
|---|---|---|
| `_system/MASTER-SOP.md` | §3.2 (assembly packet requirements), §7 (step 6 — client-approval and version-pin mechanics) | Assembly packet fields; version pinning contract at campaign intake |
| `_system/MODEL-SPECS.md` | §5 (endpoint JSON templates, required params, taskId/resultUrls contract) | Model/endpoint routing; provenance fields (model, seed) required in the return bundle |
| `_system/PHOTO-SHOOT-SOP.md` | §§1–3 (Identity Lock principles, identity-sourcing hierarchy, self-likeness fast path) | Consent gate trigger conditions; shoot-brief format returned by Photo Shoot Director |
| `universal-sops/cross-dept-request-template.md` | Full file (standard request + delivery format) | The base cross-department request schema this SOP extends with the STYLE block |
| `_system/INDEX.md` | Registration rows (card ID, version, status column) | Authoritative style ID and version resolution; only production-status cards may be used |
| Category `_RULES.md` files | Per destination category (social-media, ad-creative, presentations, etc.) | Output format, size, and safe-zone requirements resolved from `destination_format` |

All ID resolution, consent-gate details, assembly packet field requirements, and endpoint routing rules are read from the library files above at runtime. Do not reproduce model IDs, char caps, or consent-gate logic in this SOP.

---

## Procedure (ordered)

### A. Receive and validate the STYLE block

1. **Accept the request only via the standard cross-department template** (per `universal-sops/cross-dept-request-template.md`). Requests that arrive outside this format are returned to the sender with the template attached — no exception.

2. **Verify all five required STYLE block fields are present and filled:**
   - `STYLE_ID@version` — a pinned card reference, OR a set of mood keywords for CDO-resolved pick. Absent = return immediately.
   - `tier` — SHORT / MEDIUM / LONG. Default to MEDIUM if omitted; note the defaulting in the job log.
   - All Workflow-B variables — every `{VARIABLE}` token that the target card requires must be filled. Any unfilled token = return to sender with an itemized list. Do not fill by guessing.
   - `destination_format` — the output category (e.g., social-media-square, ad-creative-story, webinar-deck-slide). Required to resolve the correct category `_RULES.md`.
   - `likeness_present`: true or false — a boolean declaration from the requesting department. Missing = treat as true and route to consent gate.

3. **Resolve STYLE_ID against INDEX.md.** If `STYLE_ID` is provided: verify the exact ID@version exists in INDEX.md at production status. If the ID is absent, draft, or retired: return the request with the message "Style ID [X] not found in INDEX.md at production status. Please confirm the correct ID or submit mood keywords for CDO-resolved pick." Never proceed on an unresolved ID. Never guess or improvise a style.

4. **Mood-keyword path (no STYLE_ID provided):** Resolve the keywords to a top-k candidate shortlist via SOP-DIU-606 (semantic retrieval). Present the shortlist to the requesting department for confirmation. A confirmed ID from the requester is required before proceeding — the CDO does not select unilaterally.

### B. Likeness gate (runs before any assembly packet is built)

5. **If `likeness_present: true` (or treated as true per step 2):** Route the entire request to the Photo Shoot Director via the cross-department template with the original request attached. No assembly packet is built, no generation is assembled, and the Generation Operator is not contacted until the Photo Shoot Director returns a consent-verified shoot brief. The Photo Shoot Director applies SOP-DIU-608 (Likeness Consent Lifecycle) and SOP-DIU-609 (Reference & Identity Media Hosting). The CDO waits for the shoot brief before advancing to step 6.

6. **If `likeness_present: false` and STYLE_ID is confirmed at production status:** proceed directly to step 7 (assembly packet construction). No Photo Shoot Director routing is required.

### C. Build the assembly packet and dispatch to Generation Operator

7. **Construct the generation assembly packet** per MASTER-SOP §3.2, including:
   - Resolved card ID@version (from INDEX.md, not from the requester's text alone)
   - All filled Workflow-B variable values
   - Tier (SHORT / MEDIUM / LONG)
   - Destination format and the resolved category `_RULES.md` output specifications (size, aspect ratio, safe zones)
   - Model and endpoint routing per MODEL-SPECS (resolved from the destination category)
   - Client budget cap reference (pointer to `budget_config` — not a dollar value in this packet)
   - `likeness: false` OR the Photo Shoot Director's consent-verified shoot brief (if likeness involved)

8. **Dispatch the assembly packet to the Generation Operator.** The Generation Operator does not accept raw cross-department briefs directly — the CDO is the only intake source. Include the requesting department's Job ID so the Generation Operator's receipt links back to the originating request.

9. **Record the campaign version pin** if the requesting department is running a multi-asset campaign. Write the resolved ID@version and the requesting department's Job ID to `_local/campaign-pins/{job-id}.json`. The pinned version governs all assets in this campaign until the campaign closes.

### D. Deliver and close

10. **On receipt of the verified output from the Generation Operator** (after SOP-DIU-601 postflight passes and the receipt is `state: complete`): compile the return bundle.

11. **Return the delivery bundle to the requesting department** via the cross-department template delivery format, including:
    - The delivered asset (local path or hosted URL if the department requires one)
    - Generation log: card ID@version, model, endpoint, tier used
    - Provenance: ID@version / model / seed (or "no-seed-endpoint") — so the department can request an exact regeneration later
    - Rights manifest reference (per SOP-DIU-610) if the asset includes a likeness

12. **Campaign version bump notification.** When a card version increments or a card is retired: check `_local/campaign-pins/` for active pins on that card. Notify all departments with active pins before the new version becomes the default. No default-version change is applied to a running campaign without the requesting department's acknowledgment.

---

## Inputs

| Input | Required | Source |
|---|---|---|
| Cross-department request in standard template format | Yes | Requesting department via `universal-sops/cross-dept-request-template.md` |
| `STYLE_ID@version` or mood keywords | Yes | STYLE block in the request |
| Tier (SHORT / MEDIUM / LONG) | Yes (default MEDIUM) | STYLE block |
| All filled Workflow-B variables | Yes | STYLE block |
| `destination_format` | Yes | STYLE block — used to resolve category `_RULES.md` |
| `likeness_present` flag | Yes | STYLE block (missing = treated as true) |
| INDEX.md (current, production-status rows) | Yes | `_system/INDEX.md` |
| Photo Shoot Director consent-verified shoot brief | Conditional | SOP-DIU-608 + SOP-DIU-609 output (required when `likeness_present: true`) |
| Client `budget_config` block | Yes | Client box config — referenced in the assembly packet |
| Verified output + receipt (`state: complete`) | Yes | Generation Operator via SOP-DIU-601 postflight |

---

## Outputs

| Output | Location | State at exit |
|---|---|---|
| STYLE block validation verdict (pass or itemized failure list) | Returned to requesting department | Pass or FAIL with itemized list |
| Shoot-brief routing packet to Photo Shoot Director | Cross-department template | Sent (if `likeness_present: true`) |
| Generation assembly packet to Generation Operator | Direct CDO→Operator handoff | Written |
| Campaign version pin record | `_local/campaign-pins/{job-id}.json` | Written (for campaign requests) |
| Delivery bundle to requesting department | Cross-department template delivery format | Delivered on postflight `state: complete` |
| Campaign version bump notification | Requesting department (via `openclaw message send`) | Sent on card version increment or retirement |

---

## Handoff Conditions

- **STYLE block incomplete or STYLE_ID unresolved:** Request returned to sender with itemized failure list. No generation proceeds. CDO offers to schedule a calibration run (SOP-DIU-613) if the department has no library-registered styles.
- **`likeness_present: true`:** Entire request handed to Photo Shoot Director. CDO holds; no assembly packet built until consent-verified shoot brief returns.
- **`likeness_present: false`, ID confirmed, assembly packet complete:** Assembly packet handed to Generation Operator. CDO waits for postflight-verified receipt.
- **Output delivered:** Return bundle (asset + generation log + provenance) sent to requesting department. Campaign pin recorded (if applicable).
- **Card version bump or retirement:** Departments with active campaign pins notified before new version default is applied.

---

## Escalation Triggers

| Condition | Action |
|---|---|
| STYLE_ID not found in INDEX.md at production status | Return request to sender with exact message (see step 3). Never proceed. Never guess a substitute style. |
| `likeness_present` field absent from STYLE block | Treat as `true`. Route to Photo Shoot Director consent gate. Notify sending department that the flag was missing and defaulted to true. |
| Photo Shoot Director consent gate returns a block (BLOCK verdict per SOP-DIU-608) | Hard stop. Return to requesting department: "This request cannot be fulfilled — consent gate returned a BLOCK verdict. Contact the CDO for options." Do not route to the Generation Operator. |
| Photo Shoot Director consent gate returns ESCALATE verdict | Hold. Escalate to CDO + Director-of-Legal per SOP-DIU-608. Do not generate pending resolution. |
| Requesting department cannot supply a valid STYLE_ID or mood keywords sufficient to resolve to an INDEX entry | Return request. Offer to schedule a New-Client Calibration Run (SOP-DIU-613) to build the library. |
| Generation Operator returns a preflight failure | Return itemized preflight failure list to the requesting department (if the failure involves their Workflow-B variable fill). Return to the Photo Shoot Director (if the failure involves the likeness packet). Never improvise a fix. |
| Campaign pin record cannot be written (filesystem error) | Hard stop delivery until the pin is written. An active campaign without a version pin is untracked — a card version bump could silently change mid-campaign output. Escalate to CDO. |
| Card used in an active campaign is flagged for version bump or retirement | Notify all departments with active pins immediately. Do not apply the bump as campaign default without acknowledgment from each pinned department. |

---

## Minors Policy

Any request — from any department, via any template — that involves generating an image depicting a minor is a hard block with no override path. The CDO does not route, escalate, or re-evaluate such a request. It is returned to the sender immediately with the label "BLOCKED: minors." No consent document, CDO approval, or client authorization changes this outcome.

---

*Library-version pin: MASTER-SOP v1.0, MODEL-SPECS v1.0, PHOTO-SHOOT-SOP v1.0 (§-refs verified 2026-06-12).*
