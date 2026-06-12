# SOP-DIU-608 — Likeness Consent Lifecycle & Restricted-Content Gate

**ID:** SOP-DIU-608
**Classification:** ZHC SOP — thin wrapper
**Owner Role:** Photo Shoot Director (extends base-plan 9.1 / [SOP-DIU-401a])
**Version:** 1.0 | **Date:** 2026-06-12
**Status:** CANONICAL
**Library-version pin:** PHOTO-SHOOT-SOP v1.0, personal-photo-shoot/_RULES.md v1.0, IDENTITY.md schema v1.0 (§-refs verified 2026-06-12)

---

## Role Mission

The Photo Shoot Director maintains the consent record for every person whose likeness enters the DIU pipeline, runs it through a documented status machine before each shoot, and applies the Restricted-Content Matrix to determine whether a requested output is BLOCK, ESCALATE, or ALLOW-with-conditions. The consent gate is a file read, not a human loop, for clients with a standing self-likeness release obtained at onboarding. Every reference image set receives a who-appears inventory before generation begins. Minors are a hard block — no consent document, opt-in, or producer override changes this.

This SOP is the upstream gate for SOP-DIU-609 (reference hosting) and SOP-DIU-610 (Rights Manifest). No generation involving a real person's likeness begins until this SOP clears it.

---

## Governing Library Files (source-of-truth — do NOT duplicate content)

| File | Sections used | What it governs |
|---|---|---|
| `_system/PHOTO-SHOOT-SOP.md` | §1 (consent & identity rules, non-negotiable list), §2 (reference sourcing hierarchy), §3 (IDENTITY.md schema — consent-status line is a pointer to the CONSENT.md record, not a field copy) | Foundational consent rules, identity-sourcing order, IDENTITY.md schema |
| `personal-photo-shoot/_RULES.md` | Hard rules block (consent verified before first generation; one change per pass; all outputs route through producer) | Category-level hard rules that run in parallel with this SOP |
| `personal-photo-shoot/{client-slug}/IDENTITY.md` | §3 consent-status pointer (the line in IDENTITY.md that reads `Consent status & date` is a pointer to the CONSENT.md record governed here — do not duplicate consent fields in IDENTITY.md) | Per-client identity profile; this SOP governs the record it points at |

All consent-scope definitions, identity verification steps, and hard-rule triggers are read from these files at runtime. Do not reproduce or paraphrase those definitions here.

---

## Consent Record Schema

File: `personal-photo-shoot/{client-slug}/CONSENT.md`

The file carries YAML front-matter (machine-readable gate fields) followed by a human-readable log section.

```yaml
---
client_slug: "{client-slug}"
subject_name: "{Full Name}"
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"

# STATUS MACHINE
# Valid states: none | pending | active | expired | revoked
status: "none"

# SCOPE
modes_approved: []          # subset of [A, B, C, D, E, F] — Mode F requires explicit opt-in
use_class: ""               # "commercial" | "internal" | "both"
channels: []                # e.g. ["social_media", "presentations", "print", "webinar"]
term_months: null           # integer; null = indefinite standing release
expiry_date: null           # ISO date or null; computed from created + term_months if set

# SELF-LIKENESS FAST PATH
# true = this consent was collected at onboarding as a standing release;
# gate check is a file-read (no human loop required unless scope changes)
standing_release: false

# REVOCATION LOG (append-only; newest entry last)
revocation_log: []
  # each entry: { date, revoked_by, reason, assets_purged: true|false, manifest_updated: true|false }
---
```

### Status Machine

| From | To | Trigger |
|---|---|---|
| `none` | `pending` | Shoot request received; consent collection initiated; producer notified |
| `pending` | `active` | Producer confirms consent collected; CONSENT.md scope fields populated |
| `active` | `expired` | Current date >= `expiry_date` (or `status` manually set on standing-release termination) |
| `active` | `revoked` | Subject or producer requests revocation |
| `expired` | `active` | Renewal collected; new `expiry_date` set; `updated` bumped |
| `revoked` | *(terminal)* | Revoked records are never reactivated; a new record is required after any re-consent |

---

## Procedure (ordered)

### A. Self-Likeness Fast Path (client onboarding — run once per client)

1. At DIU onboarding (SOP-DIU-613 calibration run), create `personal-photo-shoot/{client-slug}/CONSENT.md` with `standing_release: true`, scope covering the client's anticipated modes and channels, `use_class: "both"`, and `status: "active"`. Set `term_months` per client preference (null = indefinite; 12 months is the recommended default for annual review).
2. Add the IDENTITY.md pointer line: `Consent status & date: active YYYY-MM-DD → personal-photo-shoot/{client-slug}/CONSENT.md`. The IDENTITY.md field is a pointer only; the record lives in CONSENT.md.
3. Record the Mode F (stylized) opt-in status explicitly in `modes_approved`. If Mode F is not in scope, it cannot be used — even on an otherwise-active record — until re-consented.
4. The standing release converts every subsequent shoot gate into a file read: read CONSENT.md, confirm `status: active` and scope coverage, and proceed. No producer loop required unless scope changes.

### B. Gate Check (run before every shoot — no exceptions)

1. Read `personal-photo-shoot/{client-slug}/CONSENT.md`. If the file does not exist: create a `status: pending` record, halt all generation, and notify the producer. Do not proceed.
2. Confirm `status: active`. Any other status is a halt: `pending` = notify producer that consent collection is outstanding; `expired` = notify producer to initiate renewal (14-day lead-time target per KPI); `revoked` = hard stop, no generation, escalate to CDO.
3. Verify scope coverage for this specific request: (a) all requested shoot modes are in `modes_approved`; (b) `use_class` covers the intended use; (c) all intended distribution channels are in `channels`. Scope gap = halt and notify producer for scope extension.
4. Mode F explicit opt-in check: if any requested mode includes stylized/cartoon/illustration rendering, confirm `F` is in `modes_approved`. Absence = halt regardless of overall record status.
5. Check expiry: if `expiry_date` is within 14 days, flag for renewal even if still `active`. Continue the current shoot, but add a renewal-needed note to the shoot brief header.
6. Record gate outcome in the shoot brief header: `consent_verified: true`, `modes_approved: [list]`, `gate_date: {date}`, `gate_by: photo-shoot-director`.

### C. Who-Appears Inventory (run on every reference image set)

1. For every reference image supplied to the shoot brief, identify every recognizable person visible in the image.
2. Self-likeness only (consented client, no other recognizable person): single-line inventory entry — `{client-slug}: consented (CONSENT.md active)`. Proceed.
3. Any other recognizable person appears in a reference image: halt. Resolve by either (a) crop/blur/exclude that person's face from the reference before using it, or (b) obtain an independent release for them and create a separate CONSENT.md record. Log the resolution.
4. Record the inventory result in the shoot record: `who_appears_inventory: complete`, noting each person and resolution method.
5. Non-person reference images (environments, objects, textures, clothing without a face): log as `non-person-ref` and proceed.

### D. Revocation Procedure

1. On receipt of a revocation request (from the subject directly or via producer): set `status: revoked` immediately, append an entry to `revocation_log`.
2. Halt all in-flight generations for this subject. Notify CDO and Generation Operator.
3. Walk the Rights Manifest (SOP-DIU-610): identify every delivered asset that used this consent record. CDO leads client communication on handling of already-delivered assets.
4. Purge all hosted identity references per SOP-DIU-609 deletion protocol. Log `assets_purged: true` in the revocation entry when complete.
5. Update the Rights Manifest to flag affected entries. Log `manifest_updated: true` in the revocation entry.
6. Mark `revocation_log` entry as fully resolved only when both `assets_purged` and `manifest_updated` are true.

---

## Restricted-Content Matrix

Three verdicts. Read definitions from PHOTO-SHOOT-SOP §1 and §10 at runtime — do not reproduce them here. Apply the verdict to every generation request before the brief is handed to the Generation Operator.

| Verdict | Condition |
|---|---|
| **BLOCK** (hard stop, no override path) | Sexualized real-person likeness of any kind; any image involving a minor in any generation context (MINORS HARD-NO — no consent document, opt-in, or CDO override changes this); generation of a non-consented person's likeness; deceptive news/political framing with a real person's face; fabricated endorsements the client has not approved; any output the client's `Do-Not List` (IDENTITY.md) prohibits |
| **ESCALATE-to-CDO** | Consented adult client's own glamour or brand shoot that falls in a regulated vertical (health, financial, legal claims); any Mode F output that pushes the stylization into territory the producer has not seen a sample of; any request where the Photo Shoot Director cannot independently determine the correct verdict |
| **ALLOW-with-conditions** | Output requires a synthetic-media disclosure per SOP-DIU-610's channel+jurisdiction table (retouch-disclosure jurisdictions); output uses Mode F with valid explicit opt-in; output is a retouch at degree 4–5 (dramatic) and the producer has pre-approved the degree |

**Minors policy (absolute):** No generation of any image depicting, referencing, or likening a person under 18 years of age in any mode (including cartoon/stylized Mode F). This is a BLOCK with no consent-document path, no guardian override, and no CDO override. If a reference image contains a minor, that image may not be used as a reference for any generation.

---

## Inputs

| Input | Required | Source |
|---|---|---|
| Shoot request with requested modes, use class, and distribution channels | Yes | Chief Design Officer (producer gate) |
| `personal-photo-shoot/{client-slug}/CONSENT.md` | Yes | Written at onboarding (Procedure A); must exist before first shoot |
| Reference image set (all images supplied to the brief) | Yes | Requestor; sourced per PHOTO-SHOOT-SOP §2 hierarchy |
| `personal-photo-shoot/{client-slug}/IDENTITY.md` | Yes | For consent-pointer verification and Do-Not List |

---

## Outputs

| Output | Location | State at exit |
|---|---|---|
| Gate outcome recorded in shoot brief header | Shoot brief (in-flight doc) | `consent_verified: true`, `modes_approved: [list]`, `gate_date`, `gate_by` |
| Who-appears inventory | Shoot record | `who_appears_inventory: complete` with per-person resolution notes |
| Restricted-Content verdict | Returned to CDO / shoot brief | BLOCK / ESCALATE / ALLOW-with-conditions |
| Updated CONSENT.md (expiry flag, revocation) | `personal-photo-shoot/{client-slug}/CONSENT.md` | Current state reflected |
| Revocation receipt (on revocation) | `revocation_log` entry in CONSENT.md | Appended; `assets_purged` + `manifest_updated` flags set when complete |

---

## Handoff Conditions

- **Gate cleared (ALLOW or ALLOW-with-conditions):** Photo Shoot Director assembles the Identity Lock Block and routes the complete shoot brief to the Generation Operator (SOP-DIU-601 preflight, then SOP-DIU-302 submission). Disclosure conditions accompany the brief.
- **ESCALATE verdict:** CDO receives the shoot brief, the ESCALATE reason, and the relevant consent record. Generation is paused until CDO returns a written direction.
- **BLOCK verdict:** Generation halted. CDO notified with reason. No regeneration attempt without a CDO written direction that removes the blocking condition (e.g., client removes themselves from a reference that contained another person). The blocking condition is never resolved by reframing the request.
- **Scope gap (modes or channels not in consent):** Producer notified for consent extension. Generation of out-of-scope modes halts; in-scope modes on the same brief may proceed.
- **Revocation complete:** CDO receives the completed revocation receipt (both `assets_purged` and `manifest_updated` true) before any client communication about downstream assets begins.

---

## Escalation Triggers

| Condition | Action |
|---|---|
| CONSENT.md file missing for any shoot subject | Halt. Create `status: pending` record. Notify producer. Do not generate. |
| `status` is anything other than `active` | Halt. Notify producer with the current status and the correction required. |
| Mode F requested but not in `modes_approved` | Halt regardless of overall record status. Notify producer for scope extension. Do not proceed. |
| Minor appears in any reference image | Hard block. Remove the image from the reference set entirely before any further work. Notify CDO. |
| Any generation request depicts a minor | Hard block. No path forward regardless of requester, brief, or consent framing. Escalate to CDO. |
| Reference image set contains a non-consented recognizable person | Halt. Resolve (crop/exclude or independent release) before submitting the brief. |
| CONSENT.md cannot be parsed (YAML error, missing fields) | Treat as `not-active`. Halt. Do not infer consent from memory or chat history. Fix the record first. |
| Expiry within 14 days | Flag renewal-needed in brief. Continue current shoot. Initiate renewal outreach via producer. |
| Revocation assets-purged step cannot be completed (hosting error, missing receipt) | Halt asset-purge acknowledgment. Escalate to CDO with list of un-purged hosted references. Do not mark `assets_purged: true` until verified. |
| Restricted-Content verdict is uncertain | ESCALATE to CDO. Never guess a verdict. |

---

*Library-version pin: PHOTO-SHOOT-SOP v1.0, personal-photo-shoot/_RULES.md v1.0, IDENTITY.md schema v1.0 (§-refs verified 2026-06-12).*
