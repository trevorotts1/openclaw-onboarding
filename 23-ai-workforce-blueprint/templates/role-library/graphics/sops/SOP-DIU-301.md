# SOP-DIU-301 — Style-Based Generation (Workflow B)

**ID:** SOP-DIU-301
**Band:** Vendor (3xx — Generation + Photo Shoot)
**Owner Role:** Generation Operator ("The Operator")
**Classification:** Vendor SOP — thin wrapper
**Version:** 1.0 | **Date:** 2026-06-12
**Status:** CANONICAL
**Library-version pin:** MASTER-SOP v1.1 (§§3.2, 7 verified 2026-06-12); MODEL-SPECS v1.2 (§§1, 2, 5 verified 2026-06-12); NEGATIVE-PROMPTING-SOP v1.0 (§§1–3 verified 2026-06-12); PHOTO-SHOOT-SOP v1.0 (§§1–5 verified 2026-06-12); TEST-PROTOCOL v1.0 (§§3, 5 verified 2026-06-12).

---

## Role Mission (scoped to this SOP)

The Generation Operator executes "use style {ID}" requests end-to-end. This SOP governs that execution. Starting from a validated assembly packet, the Operator assembles the positive prompt in the exact prescribed block order, runs the negative assembly and preflight gates, submits to the Kie.ai API, writes the receipt, and exits. The Operator does not improvise style changes — the style card and the library are law. If the requester asks for a deviation, the Operator applies it and notes it in the response but does NOT edit the card. Preflight failures are returned to the requester, not resolved in the field.

---

## Governing Library Files (source of truth — do NOT duplicate content here)

| File | Sections used | What it governs |
|---|---|---|
| `_system/MASTER-SOP.md` | §3.2 (variable system), §7 (Workflow B — 8 steps), §8 (versioning rules), §9 (brand defaults) | End-to-end Workflow B procedure; prompt assembly block order; variable token set; card-is-law rule |
| `_system/MODEL-SPECS.md` | §1 (model roster + aspect-ratio table + char limits), §2 (routing table), §3 (tier compatibility + LONG-to-MEDIUM rule), §4 (per-model prompting notes — expand_prompt, thinking_mode, watermark), §5 (JSON templates per endpoint), §6 (model-update protocol) | All routing decisions, endpoint constraints, `createTask` JSON templates, char budget caps |
| `_system/NEGATIVE-PROMPTING-SOP.md` | §§1–3 (three-layer stack), §4 (contradiction audit), §5 (avoid-list growth — pointer only) | Compiled negatives assembly; per-model delivery format; contradiction halt rule |
| `_system/PHOTO-SHOOT-SOP.md` | §§1–5 (consent, sourcing hierarchy, Identity Lock Block, shoot modes A–F, likeness rules) | Identity Lock Block assembly (Photo Shoot Director owns; Operator appends verbatim if present) |
| `_system/TEST-PROTOCOL.md` | §3 (hard-rule trigger set), §5 (diagnosis mode handoff) | Post-generation routing: hard-rule violations to quarantine; off-style results to Fidelity Tester |
| `{category}/_RULES.md` | Full file — platform constraints, aspect ratio restrictions, hard-rule avoid lists | Category compliance verification before model selection and at preflight |
| `INDEX.md` | Status column, card file path, version | Production-status gate (step 1); card file location for read at step 2 |
| `{CARD-ID}.md` (style card) | Full card at pinned version | Style DNA, Foundation Block, avoid-list entries, test log failure notes |

> The library is law. If this SOP disagrees with any library file, the library file wins. Report the conflict to the CDO — do not resolve silently.

---

## Procedure

**When to run:** On receipt of a validated assembly packet requesting generation using an existing style card.
**Frequency:** On-demand, per generation request.

### Step 1 — Verify production status

Open INDEX.md. Confirm the requested style card ID has `status: production`. If the card is `draft` or `tested`, halt immediately and return to the requesting role: production cards only ship to clients. Do not continue with a non-production card unless the CDO provides an explicit written override receipt flagging the run as a pre-production test.

### Step 2 — Read the card at the pinned version

Open the card file at the exact version specified in the assembly packet. Read the card fully, including:
- Foundation Block and Style DNA (these are copied verbatim in step 3 — do not paraphrase)
- Hard rules section (any card-specific hard blocks apply to this generation)
- Test log / failure notes (known failure modes inform negative assembly priority)

Do not use any other version without explicit requester instruction. Do not read the card once and cache it across jobs — always re-read at job start.

### Step 3 — Assemble the positive prompt (block order is mandatory)

Assemble the positive prompt in this exact order per MASTER-SOP §7 Workflow B:

1. **Foundation Block** — the scene-setting descriptor from the card's Foundation Block field.
2. **Subject Block** — the filled `{SUBJECT}` value from the assembly packet (one-line description supplied at generation time).
3. **Style DNA** — copy verbatim from the card's Style DNA field. Do not paraphrase, summarize, or reorder. Any deviation breaks the style contract.
4. **Filled variables** — substitute all standard variable tokens (`{HEADLINE_TEXT}`, `{SUBHEAD_TEXT}`, `{CTA_TEXT}`, `{BRAND_COLOR_1}`, `{BRAND_COLOR_2}`, `{ASPECT_RATIO}`, `{LOGO_NOTE}`) with the values from the assembly packet per MASTER-SOP §3.2. Anything not supplied in the packet takes the card's default.
5. **Identity Lock Block** — if the job is flagged `likeness: true`, append the Identity Lock Block verbatim as the final element of the prompt. This block is assembled by the Photo Shoot Director (SOP-DIU-608) and must be included exactly as delivered — never paraphrased or abbreviated.

If a deviation from the card is explicitly requested by the requester, apply it to the filled prompt and note it in the response. Do NOT edit the card file.

### Step 4 — Lock production generation settings

Confirm per MODEL-SPECS §4 that the appropriate inference guard is set for the resolved endpoint:
- **Ideogram V3:** `expand_prompt: false` must be set. MagicPrompt re-writes corrupt the card's style contract.
- **Wan 2.7:** `thinking_mode` must be off. Enabled thinking re-writes the prompt semantics.
- **All other endpoints:** verify no analogous prompt-expansion flag is enabled in the JSON template.

Exception: if the requestor has explicitly flagged `mode: exploratory` in the assembly packet (a non-production draft run), these guards may be relaxed. Document the override in the receipt.

### Step 5 — Assemble compiled negatives (SOP-DIU-303)

Run SOP-DIU-303 (Negative Prompt Assembly) to produce the compiled negatives artifact. Pass:
- The style card's AVOID-LIST block (Layer 3)
- The category identifier (to pull the category `_RULES.md` avoid-list, Layer 2)
- The fully assembled positive prompt from step 3 (required for the contradiction audit)
- The model + endpoint selection from step 6 (determines delivery format)
- The `likeness: true` / `false` flag

Do not proceed until SOP-DIU-303 returns a compiled artifact with `contradiction_audit: "passed"`. If a contradiction is found, halt and return the conflict to the prompt author — do not resolve it.

### Step 6 — Select model, tier, and endpoint (SOP-DIU-302)

Run SOP-DIU-302 (Model Routing & API Execution) steps 1–6:
- Read the PRIMARY column of MODEL-SPECS §2 routing table for the requested category and tier.
- Verify aspect ratio compatibility per MODEL-SPECS §1.
- Apply the LONG-to-MEDIUM fallback rule (MODEL-SPECS §3) with CDO notification if triggered.
- Select the exact JSON template from MODEL-SPECS §5 for the resolved endpoint.

Do not proceed without a confirmed endpoint and verified API key.

### Step 7 — Run SOP-DIU-601 preflight gate

Execute SOP-DIU-601 (Preflight & Postflight Mechanical Gates) — all 8 preflight checks — on the fully assembled prompt and configured JSON template. Do not submit to the API until SOP-DIU-601 returns a clean pass.

If preflight fails on any check, halt submission immediately. Return the itemized failure list (with check name, expected value, and actual value) to the requestor. Do not improvise a fix — preflight failures are authoring problems, not operator problems.

### Step 8 — Submit and exit (SOP-DIU-302 steps 7–10)

Submit via `createTask` per MODEL-SPECS §5 JSON template. Extract `data.taskId` from the response immediately. Write the receipt file to `_local/receipts/{receipt-id}.json` with `state: submitted` before exiting. Exit. The cron poller handles completion detection via `getTaskInfo` — do not hold the session open polling for results.

---

## Inputs

| Input | Required | Source |
|---|---|---|
| Style card ID + version | Required | Assembly packet (CDO or requesting role) |
| All filled `{VARIABLE}` tokens (SUBJECT, HEADLINE_TEXT, etc.) | Required | Assembly packet |
| Model preference or `auto-route` flag | Required | Assembly packet |
| Tier (SHORT / MEDIUM / LONG) | Required | Assembly packet |
| Aspect ratio + resolution | Required | Assembly packet |
| Budget cap | Required | Assembly packet or client `budget_config` block |
| `likeness: true` / `false` flag | Required | Assembly packet |
| Identity Lock Block (if `likeness: true`) | Conditional | Photo Shoot Director via SOP-DIU-608 — included verbatim in assembly packet |
| `mode: exploratory` flag | Optional | Assembly packet — required only for non-production runs |

---

## Outputs

| Output | Location | State at exit |
|---|---|---|
| Receipt file | `_local/receipts/{receipt-id}.json` | `state: submitted` |
| Submitted task | Kie.ai API | Processing |
| Compiled negatives artifact | `_local/jobs/{job-id}/compiled-negatives.json` | Written by SOP-DIU-303 before submission |
| Preflight failure report (if triggered) | Returned to requesting role; no API call made | Itemized failure list |

---

## Handoff Conditions

- **Normal completion:** Receipt written with `taskId`; Operator exits. Cron poller takes over via `getTaskInfo`. When the poller detects `state: success`, SOP-DIU-601 postflight runs and flips the receipt to `complete`; CDO and requestor are notified.
- **Off-style result (after postflight visual inspection):** Hand to Fidelity Tester (SOP-DIU-501a / SOP-DIU-501b) with the receipt, card ID + version, and filled prompt. Do not re-submit without Fidelity Tester diagnosis.
- **Hard-rule violation detected (postflight inspection):** Hand immediately to SOP-DIU-604 (Hard-Rule Quarantine & Incident Response). Do not deliver the asset. Do not re-use it as a reference.
- **Fallback or degradation event during submission:** Hand to SOP-DIU-603 (Fallback Ladder & Graceful Degradation) for ladder execution and CDO notification.
- **Preflight failure:** Return itemized failure list to the requesting role. No API call is made. Handoff back to the requester for authoring resolution.

---

## Escalation Triggers

| Condition | Action | Route to |
|---|---|---|
| Style card ID not found in INDEX.md | Hard stop. Return error to requesting role. | Requesting role / CDO |
| Card status is `draft` or `tested` (not `production`) | Halt. Return to requesting role — production gate not met. | Requesting role |
| Unfilled `{VARIABLE}` tokens remain in assembled prompt | Preflight catch (SOP-DIU-601 check 2). Return itemized list to requester. | Requesting role |
| Identity Lock Block missing on `likeness: true` job | Preflight catch (SOP-DIU-601 check 6). Halt. Route to Photo Shoot Director. | Photo Shoot Director |
| Contradiction found in negative assembly (SOP-DIU-303 step 5) | Halt assembly. Return conflict report (term + source) to prompt author. | Prompt author (CDO or requesting role) |
| `expand_prompt: false` / `thinking_mode off` not set in production run | Hard stop. Do not submit. Flag to CDO for config correction. | CDO |
| API key missing from all env stores | Hard stop. Escalate to CDO with list of all stores checked. | CDO |
| `createTask` returns non-2xx error | Apply SOP-DIU-603 fallback ladder. Escalate if ladder exhausted. | SOP-DIU-603 then CDO |
| Budget cap missing or `budget_config` block absent | Halt all generation. Ask CDO to provide config. Never generate without a defined cap. | CDO |
| Model-swap mid-deck attempted for any reason | Hard stop. A Slide Manifest is a cohesion contract. Escalate immediately. | CDO |
| Hard-rule violation found in generated output | Immediate quarantine. Do not deliver. Notify CDO and Photo Shoot Director (identity incidents). | SOP-DIU-604 |
| Requestor asks operator to edit the style card | Refuse. Apply the requested deviation to the filled prompt and note it. Card edits require CDO + Registrar function (SOP-DIU-502). | CDO |

---

## Library-Version Pin

```
MASTER-SOP v1.1              §§3.2, 7, 8, 9     verified 2026-06-12
MODEL-SPECS v1.2             §§1, 2, 3, 4, 5     verified 2026-06-12
NEGATIVE-PROMPTING-SOP v1.0  §§1–4               verified 2026-06-12
PHOTO-SHOOT-SOP v1.0         §§1–5               verified 2026-06-12
TEST-PROTOCOL v1.0           §§3, 5              verified 2026-06-12
```

If any pinned file advances to a new version, the Healer-Graphics SOP-DIU-615 integrity sweep will flag this pin as stale. The CDO must re-verify all §-references and update this pin line before this SOP is executed under the new version.

---

*Thin-wrapper SOP. All procedure authority lives in the library files listed above. Do not copy library content into this file — copies drift. This file points; the library governs.*
