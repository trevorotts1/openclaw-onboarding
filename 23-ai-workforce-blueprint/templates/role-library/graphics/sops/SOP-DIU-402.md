# SOP-DIU-402 — Retouching & Surgical Editing

**ID:** SOP-DIU-402
**Classification:** Vendor SOP — thin wrapper
**Owner Role:** Photo Shoot Director
**Version:** 1.0 | **Date:** 2026-06-12
**Status:** CANONICAL
**Library-version pin:** PHOTO-SHOOT-SOP v1.0 (§6 verified 2026-06-12); MODEL-SPECS v1.2 (§2 Editing Hierarchy, §4 Seedream 4.5 Edit notes verified 2026-06-12)

---

## Role Mission

The Photo Shoot Director executes targeted, client-requested corrections on real photographs and completed generations using the surgical editing capabilities of the Seedream 4.5 Edit endpoint. The Director's mandate is to apply exactly the named change while preserving identity, skin tone, and every other unspecified element unchanged. Retouching is a craft of restraint: one change per pass, preserve-first phrasing, natural-result guardrails on every prompt. Over-editing, unsolicited alterations, and identity drift are failure modes — not style choices.

---

## Governing Library Files (source-of-truth — do NOT duplicate content)

| File | Sections used | What it governs |
|---|---|---|
| `_system/PHOTO-SHOOT-SOP.md` | §6 (Retouch Mode — detailed protocol, catalog, rules of the craft, prompt skeleton, endpoint assignment) | Authoritative retouch workflow: one-change-per-pass rule, subtlety scale, preserve-first phrasing, natural-result guardrails, full catalog of legitimate edits, quality settings |
| `_system/MODEL-SPECS.md` | §2 (routing table row: surgical edits → Seedream 4.5 Edit; THE EDITING HIERARCHY note), §4 (Seedream 4.5 Edit endpoint notes: 3,000-char ceiling, `image_urls` required, quality settings) | Endpoint selection authority; fallback to GPT-Image 2 I2I only when instruction exceeds 3,000 chars; no other endpoint performs true surgical editing |
| `_system/NEGATIVE-PROMPTING-SOP.md` | §§1–3 (layer merge) | Negative layer assembly for any retouch prompt that requires avoid-list terms |
| `personal-photo-shoot/{client-slug}/IDENTITY.md` | Identity description + Standing Retouch Preferences | Defines what must never change and which edits are pre-approved without additional producer loop |
| `personal-photo-shoot/{client-slug}/CONSENT.md` | `retouch_boundaries` scope field | Authorizes which retouch catalog entries are in scope for this client; out-of-scope requests halt before any prompt is assembled |

Do not copy catalog entries, prompt skeletons, or endpoint specs from these files into this SOP — PHOTO-SHOOT-SOP §6 and MODEL-SPECS §2/§4 are the single source of truth. If they change, this SOP does not.

---

## Procedure (ordered)

1. **Verify consent scope.** Open `personal-photo-shoot/{client-slug}/CONSENT.md`. Confirm `status: active` and that the `retouch_boundaries` field covers the requested edit. If the edit falls outside consented scope, halt immediately and notify the producer with the specific boundary mismatch. Do not proceed to prompt assembly.

2. **Classify the edit against the catalog.** Open PHOTO-SHOOT-SOP §6 retouching catalog. Match the inbound request to a named catalog entry (skin, teeth, body, hair, eyes, cleanup). Apply matter-of-factly. If the requested edit is not in the catalog, escalate to the producer before proceeding — do not improvise a category.

3. **Confirm identity-drift risk.** Check IDENTITY.md Standing Retouch Preferences. If the requested change is so extreme the person would no longer be recognizable, flag to the producer as a deliverability risk (identity drift breaks the output's purpose), not as a judgment call. Halt pending producer guidance if flagged.

4. **Apply the MODEL-SPECS Editing Hierarchy.** Open MODEL-SPECS §2 Editing Hierarchy. Route to Seedream 4.5 Edit unless the instruction cannot fit within the 3,000-character ceiling — in that case, route to GPT-Image 2 I2I (expect more drift in untouched areas; note this in the shoot record). No other endpoint performs true surgical editing and must not be substituted.

5. **Assemble the prompt using PHOTO-SHOOT-SOP §6 rules of the craft.** Follow all five rules without exception:
   - One change per pass — chain passes for multiple edits; each pass prompt: "Keep everything unchanged except: {single edit}."
   - Specify degree on the 1–5 subtlety scale; translate to language per §6.
   - Lead with preserve-first phrasing (what to keep, then the change).
   - Include natural-result guardrails verbatim in every prompt: "retain natural skin texture and pores, no plastic smoothing, result must look like an unedited photograph."
   - Use the retouch prompt skeleton from PHOTO-SHOOT-SOP §6 as the structural template.

6. **Set endpoint params.** Per MODEL-SPECS §4 (Seedream 4.5 Edit notes): `image_urls` is REQUIRED — verify the source image URL is live (HTTP 200) before submitting. Set `aspect_ratio` explicitly (no auto). Set `quality: basic` for intermediate chain steps; `quality: high` (4K) for final deliverable passes.

7. **Run SOP-DIU-601 preflight.** Do not submit until SOP-DIU-601 returns a clean pass (char count within 3,000-char ceiling for Seedream Edit; no unfilled `{VARIABLE}` tokens; all required params present). Any preflight failure halts submission.

8. **Submit to Generation Operator.** Hand the completed retouch brief (prompt, endpoint, params, source image URL, tier) to the Generation Operator for Kie.ai API execution per SOP-DIU-301/302. The Director does not execute API calls directly.

9. **Review the retouched output.** Verify: (a) the named edit was applied correctly; (b) no new artifacts introduced; (c) Identity Lock integrity maintained — skin tone, facial structure, and all unlisted elements are unchanged. If Identity Lock is broken, quarantine the output and re-route; never deliver.

10. **Apply synthetic-media disclosure if required.** If the retouched output is destined for commercial delivery on a covered channel, apply the appropriate disclosure per SOP-DIU-610 (Rights Manifest & Synthetic-Media Disclosure) before handoff.

11. **Log the session.** Record in the shoot record: edit type, endpoint used, prompt hash, source image path, output asset path, number of chain passes, disclosure applied (y/n), and SOP-DIU-610 manifest receipt reference.

---

## Inputs

| Input | Required | Source |
|---|---|---|
| Source image (generation output or client-provided photo) | Yes | Operator delivery or client via producer |
| Retouching brief (named edits from §6 catalog, degree specification) | Yes | Producer / CDO |
| Active CONSENT.md with `retouch_boundaries` covering the requested edits | Yes | `personal-photo-shoot/{client-slug}/CONSENT.md` |
| Client IDENTITY.md (Standing Retouch Preferences + identity description) | Yes | `personal-photo-shoot/{client-slug}/IDENTITY.md` |
| Source image hosted at a live, accessible URL | Yes | SOP-DIU-609 hosting flow (or local path verified accessible) |
| SOP-DIU-601 preflight pass verdict | Yes | SOP-DIU-601 execution immediately prior to submit |

---

## Outputs

| Output | Location | State at exit |
|---|---|---|
| Retouched image | `_local/deliverables/{client-slug}/{date}/` | Verified, identity-lock intact |
| Shoot record update | `personal-photo-shoot/{client-slug}/IDENTITY.md` Shoot History | Updated with session log |
| Rights Manifest receipt (if commercial delivery) | `personal-photo-shoot/{client-slug}/rights-manifests/` | Appended per SOP-DIU-610 |
| Generation Operator receipt | `_local/receipts/{receipt-id}.json` | `state: complete` (written by Operator) |

---

## Handoff Conditions

- **Normal completion:** Retouched output passes identity-lock review; disclosure applied if required; shoot record logged; Rights Manifest receipt written. Hand deliverable to Chief Design Officer.
- **Multiple edits requested:** Execute as a chain (one change per pass) before handing to CDO. Each intermediate pass remains in `_local/jobs/{job-id}/chain/` until the final pass is verified.
- **Identity drift in retouched output:** Quarantine the output (`_local/quarantine/`). Do not deliver. Notify CDO with the specific drift description. Re-run with strengthened preserve-first phrasing or escalate to CDO if repeated.
- **Hard-rule violation detected (e.g., skin tone lightened):** HARD FAIL. Quarantine immediately per SOP-DIU-604. Log as incident. CDO notification mandatory. Quarantined assets are never delivered or reused.
- **Out-of-scope edit request:** Halt before prompt assembly. Route to CDO with the consent boundary mismatch documented.

---

## Escalation Triggers

| Condition | Action |
|---|---|
| Consent status not `active`, or `retouch_boundaries` does not cover the requested edit | Hard stop before any prompt assembly. Notify producer with boundary mismatch detail. |
| Requested edit not in PHOTO-SHOOT-SOP §6 catalog | Halt. Escalate to producer for scope determination before proceeding. |
| Requested change would make the person unrecognizable (identity drift risk) | Flag to producer as a deliverability risk. Halt pending guidance. Do not apply as-is. |
| Seedream 4.5 Edit rejects `image_urls` (URL not reachable or format unsupported) | Hard stop. Resolve hosting per SOP-DIU-609 before resubmitting. |
| Retouched output has lightened skin tone | HARD FAIL. Quarantine + SOP-DIU-604 + CDO incident notification. Never deliver. |
| Retouched output has identity drift beyond the named edit | Quarantine. Notify CDO. Do not deliver until a passing output is produced. |
| Instruction exceeds 3,000-char ceiling on Seedream Edit | Route to GPT-Image 2 I2I per MODEL-SPECS §2 Editing Hierarchy. Document in shoot record that drift risk is higher; note for CDO review. |
| SOP-DIU-601 preflight fails | Do not submit. Return itemized failure list to requestor. |
| API key missing from all env stores | Hard stop. Escalate to CDO. Do not attempt generation. |

---

*Library-version pin: PHOTO-SHOOT-SOP v1.0 (§6 verified 2026-06-12); MODEL-SPECS v1.2 (§2 Editing Hierarchy, §4 Seedream 4.5 Edit notes verified 2026-06-12).*
