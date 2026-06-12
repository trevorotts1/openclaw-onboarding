# SOP-DIU-614 — Client Revision Loop & Taste Profile

**ID:** SOP-DIU-614
**Classification:** ZHC SOP — thin wrapper
**Owner Role:** Chief Design Officer (orchestrates); Generation Operator (executes re-runs)
**Section 9 slot:** 9.10
**Version:** 1.0 | **Date:** 2026-06-12
**Status:** CANONICAL
**Library-version pin:** TEST-PROTOCOL v1.0, MASTER-SOP v1.0, NEGATIVE-PROMPTING-SOP v1.0, PHOTO-SHOOT-SOP v1.0 (§-refs verified 2026-06-12)

---

## Role Mission

Every client feedback event on a DIU-generated deliverable enters this SOP. The CDO classifies the note — defect, preference within brief, or scope change — and routes accordingly. The style card is never edited to accommodate feedback; the library is law. Instead, client preferences are translated into 12-dimension/zone language as one-time deviation instructions, and every preference expressed is immediately appended to a disk-persisted taste profile that survives session limits and compounds over the life of the client relationship.

The taste profile (`_local/TASTE-PROFILE.md`) is the institutional memory for a client's aesthetics. Its absence means every future brief starts from zero. Writing to it is not optional and is not deferred.

---

## Governing Library Files (source-of-truth — do NOT duplicate content)

| File | Sections used | What it governs |
|---|---|---|
| `_system/TEST-PROTOCOL.md` | §5 (patch loop — defect diagnosis; when to escalate vs re-run) | Defect classification and Fidelity Tester routing; what constitutes a scorable failure vs a style preference |
| `_system/MASTER-SOP.md` | §7 step 6 (client feedback handling; named-style capture at approval moment) | Feedback handling discipline; when a preference becomes a named-style candidate |
| `_system/NEGATIVE-PROMPTING-SOP.md` | §5 (avoid-list growth from client feedback; aversions that should propagate to compiled negatives) | How persistent aversions feed the avoid list; aversion entries belong in compiled negatives, not card edits |
| `_system/PHOTO-SHOOT-SOP.md` | §3 (standing-preference pattern for identity work — the generalized model this SOP applies to all generation work) | Standing pre-approvals and how they are captured and enforced across future shoots |

All classification decisions reference these files at runtime. Do not duplicate rubric dimensions, avoid-list formats, or patch-loop logic here — the library files are the single source of truth.

---

## Procedure (ordered)

### Step 1 — Classify the client note

On receipt of any client feedback note on a DIU-generated deliverable, classify it into exactly one of three categories before taking any other action:

**(a) Defect:** the output has a factual, technical, or identity error — wrong text, wrong color per brand config, wrong aspect ratio, identity drift, text rendered on a face, lightened skin tone, missing brand element the brief required. Route immediately to the Fidelity Tester for diagnosis mode (TEST-PROTOCOL §5). Do not re-run the generation without a Fidelity Tester finding. Do not reclassify a defect as a preference to avoid the diagnosis step.

**(b) Preference within brief:** the output is technically correct and passes postflight verification, but the client prefers a different aesthetic direction within the style card's latitude — for example, warmer tones, a higher-energy composition, more negative space. Translate the preference into 12-dimension/zone language as a one-time deviation note and hand to the Generation Operator for a re-run. The style card is NEVER edited to record this deviation — the card and its library entry remain unchanged. The deviation is an instruction on this job only; if the preference is persistent, it belongs in TASTE-PROFILE.md (Step 3) and eventually in NAMED-STYLES.md (Step 5).

**(c) Scope change:** the client wants something the current card and brief cannot produce — a new subject, a different shoot mode, a style direction the card was not designed for. Treat as a new brief. Notify the CDO and open a new request cycle. Do not attempt to satisfy a scope change by stretching a preference re-run.

If the note is ambiguous between (b) and (c): the CDO makes the call. Document the classification and reason in the job directory.

### Step 2 — Count revision rounds

Track the number of type-(b) preference re-runs applied to this deliverable. Log the count in the job directory (`_local/jobs/{job-id}/revision-log.md`) with each round's date, deviation note, and receipt reference.

If the client requests more than 3 type-(b) re-runs on the same deliverable without approval: flag to the CDO with the revision log. The CDO must decide one of:
- Elevate to type-(c) scope change and open a new brief.
- Create a second style card variant (route back to Style Analyst as a new card request).
- Authorize a 4th round with a written reason recorded in the revision log.

Do not continue open-ended type-(b) re-runs beyond 3 without a CDO decision on record.

### Step 3 — Append every preference to TASTE-PROFILE.md

At the moment any client preference or aversion is expressed — on first delivery, on a revision round, on casual feedback between jobs — write it to `_local/TASTE-PROFILE.md` immediately. Do not defer this step to the end of a session. Preferences expressed to a session that is not written to disk are lost.

Required format for each entry:
```
[DATE] liked: {dimension or element} (context: {brief/asset identifier})
[DATE] disliked: {dimension or element} (context: {brief/asset identifier})
[DATE] pre-approved: {standing element, e.g., "always use deep navy base"} (confirmed by owner)
```

Examples of dimension language to use (reference TEST-PROTOCOL for the full 12-dimension rubric):
- "liked: deep, muted palette (Saturation: low; Value: dark) — context: social-header-2026-06-12"
- "disliked: high-contrast accent on subject (Contrast Weight: heavy) — context: calibration-card-1"
- "pre-approved: logo zone bottom-right — confirmed by owner 2026-06-12"

### Step 4 — Taste-profile discipline rules

These rules apply to TASTE-PROFILE.md at all times, not only during a revision event:

1. **Disk-persisted only.** Entries exist only when written to `_local/TASTE-PROFILE.md`. Session memory, chat messages, and agent working memory are not substitutes. If the file cannot be written (permissions error, file missing), create it immediately before the session ends.

2. **Append-only.** Entries are never edited or pruned. If the client reverses a prior preference, add a new entry with the date and context; do not delete the earlier one. The full preference history is the record.

3. **Standing pre-approvals are binding.** Once the owner confirms a standing pre-approval entry, it functions as a non-negotiable preflight item for this client's future jobs. The Generation Operator reads TASTE-PROFILE.md before assembling any new brief for this client and enforces every active pre-approval as if it were a required param.

4. **Persistent aversions feed the avoid list.** An aversion expressed across two or more separate briefs (same dimension or element, different context) is promoted to the client's compiled-negatives source per NEGATIVE-PROMPTING-SOP §5. The CDO authorizes the promotion; the Style Analyst executes it.

### Step 5 — Pre-fill from taste profile on new briefs

When the CDO assembles a new brief for this client: read `_local/TASTE-PROFILE.md` first. Pre-fill standing pre-approvals into the assembly packet as hard constraints. Surface preference patterns (5+ likes or dislikes in a single dimension) to the CDO as candidate additions to the client's `_local/NAMED-STYLES.md` brand overrides. This step closes the compounding loop: the taste profile should make each successive brief faster to specify, not re-expressed from scratch.

---

## Inputs

| Input | Required | Source |
|---|---|---|
| Client feedback note (verbatim) | Yes | Client, via CDO or owner channel |
| Delivered asset (the specific output being reviewed) | Yes | `_local/results/{job-id}/` — postflight-verified local file |
| Generation receipt for the asset (card ID@version, model, tier, exact filled prompt, seed, taskId) | Yes | `_local/receipts/{receipt-id}.json` — written at submit time per SOP-DIU-602 |
| Client's current `_local/TASTE-PROFILE.md` | Yes | Client box; created at calibration run (SOP-DIU-613) or on first feedback event if not yet initialized |
| Job revision log (`_local/jobs/{job-id}/revision-log.md`) | Yes | Created on first type-(b) re-run; used to count rounds |
| Fidelity Tester finding (type-a defects only) | Conditional | Fidelity Tester via TEST-PROTOCOL §5 |

---

## Outputs

| Output | Location | State at exit |
|---|---|---|
| Classification verdict | Logged in `_local/jobs/{job-id}/revision-log.md` | One of: defect / preference / scope-change, with reasoning |
| Re-run deviation instruction (type-b) | Handed to Generation Operator as a deviation note | One-time instruction; never written to the style card |
| New-brief trigger (type-c) | Notified to CDO | CDO opens new request cycle |
| `_local/TASTE-PROFILE.md` updated | `_local/TASTE-PROFILE.md` | Append-only; written at the moment of each preference |
| Revision log updated | `_local/jobs/{job-id}/revision-log.md` | Round count incremented; receipt reference recorded |

---

## Handoff Conditions

- **Type-(a) defect:** Hand to Fidelity Tester with the generation receipt and delivered asset. The Fidelity Tester diagnosis finding is required before any re-run. No re-run is authorized until the finding identifies the root cause.
- **Type-(b) preference, within round limit:** Hand deviation note to Generation Operator. Generation Operator re-runs with the deviation note as a one-time instruction and returns the new output to the CDO for delivery. Taste profile updated before the re-run is submitted.
- **Type-(b) preference, round limit exceeded:** Flag to CDO with full revision log. Await CDO decision (scope change, new card variant, or documented extension). Do not re-run without a CDO decision on record.
- **Type-(c) scope change:** Notify CDO. Open new brief cycle from intake. The current deliverable job is closed; the scope-change request is a new job.
- **Persistent aversion promotion:** CDO authorizes; Style Analyst adds to compiled-negatives source per NEGATIVE-PROMPTING-SOP §5. CDO notifies Generation Operator that the avoid list has been updated.

---

## Escalation Triggers

| Condition | Action |
|---|---|
| `_local/TASTE-PROFILE.md` cannot be written (permissions error, missing directory) | Create the file immediately. If creation fails, escalate to CDO with the error before the session ends. A preference recorded nowhere is lost. |
| TASTE-PROFILE.md does not exist at time of first feedback event (calibration run was skipped or incomplete) | Create the file now. Log a note that calibration run (SOP-DIU-613) was not completed. Escalate to CDO for a retroactive calibration run if the client has more than one brief in flight. |
| Type-(b) re-run count exceeds 3 without a CDO decision on record | Hard stop. Do not submit a 4th type-(b) re-run. Escalate to CDO with the full revision log immediately. |
| Feedback note contains a hard-rule violation as a request (e.g., client asks to lighten skin tone, add text on face) | Do not attempt. Classify as a type-(a) defect and route to Photo Shoot Director + CDO for consent/ethics review. This is not a "preference within brief." |
| Style card is edited in response to a preference note (any role) | Unauthorized change. Revert the card edit immediately. File a CDO incident note. Client preferences never mutate the library — they are deviation instructions or taste-profile entries only. |
| Generation receipt is missing for the asset under review | Hard stop. The receipt is required to issue a meaningful defect diagnosis or re-run instruction. Escalate to CDO and locate the receipt before classifying the feedback. A re-run without a receipt cannot be fingerprint-checked for idempotency (SOP-DIU-602). |

---

*Library-version pin: TEST-PROTOCOL v1.0, MASTER-SOP v1.0, NEGATIVE-PROMPTING-SOP v1.0, PHOTO-SHOOT-SOP v1.0 (§-refs verified 2026-06-12).*
