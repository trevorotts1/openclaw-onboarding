# SOP-DIU-601 — Preflight & Postflight Mechanical Gates

**ID:** SOP-DIU-601
**Classification:** ZHC SOP — thin wrapper
**Owner Role:** Generation Operator
**Version:** 1.0 | **Date:** 2026-06-12
**Status:** CANONICAL
**Library-version pin:** MODEL-SPECS v1.0, MASTER-SOP v1.0, NEGATIVE-PROMPTING-SOP v1.0, PHOTO-SHOOT-SOP v1.0 (§-refs verified 2026-06-12)

---

## Role Mission

The Generation Operator runs this SOP as a mandatory gate before every API submission (preflight) and immediately after every completed result download (postflight). Preflight is deterministic lint — zero tokens spent, zero API calls made — that prevents foreseeable failures before they cost money. Postflight verifies that what was paid for was actually received and is usable. Nothing reports success until postflight passes. The Operator never submits with a known preflight failure and never marks a job complete before local files are verified.

---

## Governing Library Files (source-of-truth — do NOT duplicate content)

| File | Sections used | What it governs |
|---|---|---|
| `_system/MODEL-SPECS.md` | §1 (endpoint roster, aspect-ratio table, char caps per endpoint), §3 (tier compatibility + LONG-to-MEDIUM rule), §4 (endpoint prompting notes, style_reference_only), §5 (JSON templates + required params per endpoint) | Char-count caps, aspect-ratio support, required params, Seedream 3,000-char silent-fail ceiling, GPT-Image-2/NB2 filter note |
| `_system/MASTER-SOP.md` | §3.2 (assembly packet requirements), §5 (submit-and-exit discipline) | What a valid assembly packet must contain; exit-after-submit rule |
| `_system/NEGATIVE-PROMPTING-SOP.md` | §4 (contradiction audit) | Compiled-negatives artifact must exist and pass contradiction audit before preflight clears |
| `_system/PHOTO-SHOOT-SOP.md` | §4 (Identity Lock Block verbatim requirement on likeness jobs) | Identity Lock Block presence check on `likeness: true` jobs |

All checks reference these files at runtime. Do not encode char caps, ratio tables, or required-param lists directly in this SOP — MODEL-SPECS is the single source of truth and changes independently.

---

## Procedure (ordered)

### Preflight (run before every `createTask` call — any failure = halt, return itemized list to sender, do not submit)

1. **Verify API key across all env stores.** Check every env store (secrets/.env, openclaw.json, ~/.openclaw/workspace/.env, ~/clawd/secrets/.env, and the running gateway process env) for `KIE_API_KEY` before any other check. A key absent from all stores is a hard stop — do not proceed and do not guess at key location.

2. **Char count.** Count actual characters in the fully assembled positive prompt (after variable fill, after Identity Lock Block append if present). Look up the resolved endpoint's character cap in MODEL-SPECS §1. Seedream hard ceiling is 3,000 characters — silent fail above this with no API error. Return `PREFLIGHT FAIL: char count {actual} exceeds endpoint cap {cap} for {endpoint}` if over.

3. **Unfilled variable tokens.** Grep the assembled prompt for any remaining `{[A-Z_]+}` pattern. A match means a variable was not filled. Return `PREFLIGHT FAIL: unfilled variables: {list}` if any found.

4. **Aspect ratio supported.** Verify the requested aspect ratio appears in the supported-ratio table for the resolved endpoint (MODEL-SPECS §1). Return `PREFLIGHT FAIL: aspect ratio {ratio} not supported by {endpoint}` if absent.

5. **Required params present.** Verify all endpoint-required params are set in the JSON template per MODEL-SPECS §5:
   - Seedream: `aspect_ratio` present.
   - Ideogram production run: `expand_prompt: false` and `aspect_ratio` resolving to a valid preset.
   - Wan: `watermark: false` set.
   - Return `PREFLIGHT FAIL: missing required param {param} for {endpoint}` for each absent param.

6. **`style_reference_only` directive.** If `image_input`, `input_urls`, or `image_urls` are populated in the template, verify the per-endpoint style-reference-only field is also set per MODEL-SPECS §4. Return `PREFLIGHT FAIL: reference images present but style_reference_only not set` if absent.

7. **Identity Lock Block (likeness jobs only).** If the job is flagged `likeness: true`, verify the Identity Lock Block is present verbatim at the end of the positive prompt, assembled by the Photo Shoot Director per PHOTO-SHOOT-SOP §4. Return `PREFLIGHT FAIL: likeness job missing Identity Lock Block` if absent.

8. **Compiled negatives and contradiction audit.** Confirm the compiled negatives artifact exists for this job (written by SOP-DIU-303) and that the contradiction audit (NEGATIVE-PROMPTING-SOP §4) completed with a clean pass. Return `PREFLIGHT FAIL: compiled negatives artifact missing or contradiction audit not completed` if absent.

9. **Budget headroom.** Estimate job cost from `_local/PRICING.md` for the selected model and tier. Verify `current_period_spend + estimated_cost` does not exceed the client's monthly cap. If the estimated cost exceeds the per-job approval threshold, require a producer approval receipt before proceeding. If no `budget_config` block exists for the client, halt all generation and ask CDO to provide it.

10. **Exploratory mode tag.** If the requestor has flagged `mode: exploratory` (non-production `expand_prompt: true` or thinking-mode run), verify the assembly packet carries the exploratory tag so the receipt records this output as non-production and never writes it to the style library.

### Postflight (run immediately when the cron poller detects `state: completed`)

1. **Download immediately.** Call `getResultInfo` and download all `resultUrls` to `_local/results/{job-id}/`. Do not log anything as complete before local files exist on disk. Result URLs are perishable.

2. **Nonzero file size.** Verify each downloaded file has size > 0 bytes. A zero-byte file means a failed or truncated transfer.

3. **Decodable image.** Open and decode each file to confirm it is a valid image, not a corrupted or placeholder response.

4. **Dimensions match request.** Verify actual pixel dimensions match the requested resolution and aspect ratio.

5. **Record sha256.** Hash each verified file and record the digest in the receipt.

6. **Flip receipt state.** Only after all five checks above pass: update the receipt `state` to `complete`, record the verified local delivery path, and notify the requesting role and CDO.

---

## Inputs

| Input | Required | Source |
|---|---|---|
| Fully assembled positive prompt (all variables filled, Identity Lock Block appended if applicable) | Yes | Generation Operator (SOP-DIU-301 assembly step) |
| Resolved endpoint + model + tier + aspect ratio | Yes | MODEL-SPECS §2 routing decision (SOP-DIU-302) |
| Completed JSON template for the resolved endpoint | Yes | MODEL-SPECS §5 |
| `likeness: true` or `false` flag | Yes | Assembly packet from CDO or Photo Shoot Director |
| Identity Lock Block (if `likeness: true`) | Conditional | Photo Shoot Director via SOP-DIU-608 |
| Compiled negatives artifact + contradiction-audit pass | Yes | SOP-DIU-303 |
| `_local/PRICING.md` | Yes | Box-owned pricing file |
| Client `budget_config` block | Yes | Client box config |
| `KIE_API_KEY` verified across all env stores | Yes | Client box env stores |
| Completed task `resultUrls` (postflight) | Yes | Kie.ai `getResultInfo` response |

---

## Outputs

| Output | Location | State at exit |
|---|---|---|
| Preflight verdict (pass or itemized failure list) | Returned to caller | Pass or FAIL with itemized list |
| Receipt `state` flipped to `complete` | `_local/receipts/{receipt-id}.json` | `complete` |
| Downloaded result files | `_local/results/{job-id}/` | Verified, sha256 recorded |
| CDO + requestor notification | Via `openclaw message send` | Sent on postflight completion |
| Postflight-failed receipt (on failure) | `_local/receipts/{receipt-id}.json` | `postflight-failed` |

---

## Handoff Conditions

- **Preflight pass:** Operator proceeds to `createTask` submission (SOP-DIU-302). Receipt is written at submit time.
- **Preflight fail:** Itemized failure list returned to the requestor. No submission. No spend. Operator does not improvise fixes — prompt authoring and variable-fill corrections belong to the requestor.
- **Postflight complete (all checks pass):** Receipt flipped to `complete`. CDO and requesting role notified. Asset ready for delivery or Fidelity Tester (SOP-DIU-501a) if off-style.
- **Hard-rule violation detected in postflight visual inspection:** Hand to SOP-DIU-604 (Hard-Rule Quarantine & Incident Response) immediately.
- **Postflight verification failure (bad download, zero bytes, wrong dimensions):** Receipt flipped to `postflight-failed`. CDO notified. Do not re-submit without CDO direction.

---

## Escalation Triggers

| Condition | Action |
|---|---|
| `KIE_API_KEY` absent from all env stores | Hard stop. Escalate to CDO with list of all stores checked. Never proceed without a verified key. |
| Preflight char count exceeds endpoint cap | Hard stop. Return `PREFLIGHT FAIL: char count {actual} exceeds cap {cap}`. Do not truncate prompt — return to author. |
| Unfilled `{VARIABLE}` tokens in assembled prompt | Hard stop. Return itemized list of unfilled tokens. Do not fill by guessing. |
| `likeness: true` but Identity Lock Block absent | Hard stop. Return to Photo Shoot Director for block assembly before resubmission. |
| Compiled negatives artifact missing | Hard stop. Return to SOP-DIU-303 owner before resubmission. |
| Budget cap missing (`budget_config` absent) | Hard stop. Escalate to CDO. Never generate without a defined budget cap. |
| Estimated cost exceeds per-job approval threshold | Require producer approval receipt before proceeding. Do not generate without it. |
| Monthly cap would be exceeded | Hard stop. Notify CDO. Do not proceed without a producer override receipt. |
| Downloaded result file is zero bytes or undecodable | Flip receipt to `postflight-failed`. Escalate to CDO. Do not retry without direction. |
| Actual dimensions do not match requested resolution/ratio | Flip receipt to `postflight-failed`. Escalate to CDO. Do not report success. |
| Hard-rule violation detected during postflight visual inspection | Immediately route to SOP-DIU-604 quarantine. Do not deliver. Do not leave asset in any sourcing-accessible folder. |

---

*Library-version pin: MODEL-SPECS v1.0, MASTER-SOP v1.0, NEGATIVE-PROMPTING-SOP v1.0, PHOTO-SHOOT-SOP v1.0 (§-refs verified 2026-06-12).*
