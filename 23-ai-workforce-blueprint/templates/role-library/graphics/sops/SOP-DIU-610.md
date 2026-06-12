# SOP-DIU-610 — Rights Manifest & Synthetic-Media Disclosure

**ID:** SOP-DIU-610
**Classification:** ZHC SOP — thin wrapper
**Owner Role:** Photo Shoot Director (primary); Generation Operator (executed at delivery)
**Version:** 1.0 | **Date:** 2026-06-12
**Status:** CANONICAL
**Library-version pin:** PHOTO-SHOOT-SOP v1.0, IDENTITY.md v1.0, MODEL-SPECS v1.0, TEST-PROTOCOL v1.0 (§-refs verified 2026-06-12)

---

## Role Mission

The Photo Shoot Director maintains an append-only Rights Manifest for every client and every shoot. The manifest maps each delivered synthetic-media output to the consent record version, reference provenance, model/prompt fingerprint, seed, delivery date, and disclosure applied. The Generation Operator writes manifest entries at delivery time per this SOP.

The manifest makes consent revocation, licensing audits, and takedowns executable. Without it, there is no path from a delivered asset back to the consent that authorized it. A Wan `watermark: false` generation is permitted only when this manifest entry exists before delivery. Fields are authored to map 1:1 onto C2PA/Content-Credentials assertions so that when providers expose signed provenance, the manifest is ready to feed it without re-instrumentation.

MINORS POLICY: This SOP applies the absolute hard-no to minors. Minors never appear in any generated output governed by this manifest. No consent record, waiver, or parental authorization changes this rule. If a reference image contains a minor, the job halts at SOP-DIU-608 before reaching this SOP.

---

## Governing Library Files (source-of-truth — do NOT duplicate content)

| File | Sections used | What it governs |
|---|---|---|
| `_system/PHOTO-SHOOT-SOP.md` | §8 step 7 (delivery checklist — manifest entry required before handoff) | Delivery gate: manifest entry is a required step, not optional documentation |
| `_local/IDENTITY.md` (per-client) | Shoot History section | The per-client shoot history pointer; manifest entries cross-reference and extend it |
| `_system/MODEL-SPECS.md` | §5 (taskId, resultUrls fields), §6 (versioning and update protocol) | taskId and resultUrls are the receipt-side keys; the §6 protocol governs disclosure-table versioning |
| `_system/TEST-PROTOCOL.md` | §7 (asset traceability requirements at production promotion) | Traceability fields the Fidelity Tester requires; manifest satisfies §7 at delivery |

All field definitions, disclosure logic, and consent schema are authoritative in the files above. Do not duplicate or paraphrase consent record schemas or disclosure rules in this SOP — point to the governing file.

---

## Procedure (ordered)

### A. Manifest Initialization (once per client, at first shoot or DIU activation)

1. **Create the manifest file.** Write `_local/rights-manifest/{client-id}/RIGHTS-MANIFEST.md` using the header block below. This file is append-only — entries are never edited or deleted once written. Corrections are new entries with a `correction_of` field referencing the original entry ID.

2. **Create the disclosure table.** Write `_local/rights-manifest/{client-id}/disclosure-table.json` keyed by `{channel}_{jurisdiction}`. Populate with the applicable disclosure variants per the client's active channels and known jurisdictions. This file is versioned independently; bumping its version does not alter the manifest entries that already reference the prior version.

3. **Record the disclosure-table version.** The manifest header carries the initial `disclosure_table_version`. Every manifest entry records the version in force at delivery time — law changes bump the table version and create a new table file; SOPs do not change.

4. **Seed the cross-reference pointer.** In `_local/IDENTITY.md` Shoot History, add a line pointing to `_local/rights-manifest/{client-id}/RIGHTS-MANIFEST.md`. IDENTITY.md remains thin; the manifest is the detail record.

### B. Manifest Entry (one entry per delivered output, written at delivery time before asset handoff)

The Generation Operator writes a new entry block to the manifest immediately before handing off any delivered asset. The entry is written before the delivery is marked complete — no exceptions.

Entry block format:

```
### Entry {entry-id}
- **entry_id**: {uuid}
- **asset_path**: {verified local delivery path — from SOP-DIU-601 postflight receipt}
- **asset_sha256**: {sha256 digest — from SOP-DIU-601 postflight receipt}
- **shoot_id**: {shoot identifier from Photo Shoot Director}
- **task_id**: {Kie.ai taskId — from SOP-DIU-602 generation receipt}
- **card_id**: {style card ID} @ **card_version**: {version}
- **model**: {model slug — MODEL-SPECS §1}
- **tier**: SHORT | MEDIUM | LONG
- **filled_prompt_hash**: sha256({exact positive prompt submitted})
- **seed**: {value} | `"no-seed-endpoint"`
- **reference_provenance**: {source path(s) of all reference images used; "none" if no references}
- **hosting_method**: {`ghl-media-library` | `imgbb` | `none`} — per SOP-DIU-609
- **consent_record_id**: {UUID from _local/consent/{client-id}.json}
- **consent_record_version**: {version at time of generation}
- **consent_scope_modes**: [{list of modes A–F active at generation time}]
- **likeness_present**: true | false
- **minors_present**: HARD-NO — this field is always `false`; if `true` would be required, the job must not have reached delivery (see SOP-DIU-608)
- **watermark_false_permitted**: true | false — `true` only if `watermark: false` was set in the Wan API call; requires this manifest entry to exist BEFORE delivery
- **disclosure_applied**: {disclosure text applied to this asset's delivery channel, copied verbatim from disclosure-table.json}
- **disclosure_table_version**: {version of disclosure-table.json in force at delivery}
- **delivery_channel**: {channel slug — e.g., `social_media`, `internal`, `client_direct`}
- **jurisdiction**: {jurisdiction slug — e.g., `us`, `eu`, `ca`}
- **delivered_at**: {ISO 8601 timestamp}
- **delivered_by**: {role slug}
- **correction_of**: {entry_id} | `null`
```

5. **Verify watermark gate.** If the Wan `watermark: false` param was used in the generation, confirm this manifest entry is written before the delivery receipt is marked complete. Writing the entry IS the gate — deliver only after the entry exists.

6. **Update IDENTITY.md Shoot History.** Append the entry ID and delivery date to the Shoot History row for this shoot. IDENTITY.md carries the pointer; the manifest carries the detail.

7. **Notify Photo Shoot Director.** Send the manifest entry ID and asset path on delivery. The Director confirms the consent record version matches the active consent record before the CDO marks the deliverable closed.

### C. Disclosure Table Maintenance (triggered by law/channel change, not by SOP revision)

1. **Trigger.** The disclosure table is updated when: (a) a new delivery channel is added for a client, (b) a new jurisdiction is added, or (c) legal requirements change for an existing channel/jurisdiction combination.

2. **Version bump protocol.** Follow MODEL-SPECS §6 update discipline: create a new versioned disclosure table file, log the change, and update the manifest header's `disclosure_table_version`. Existing manifest entries reference the version in force at their delivery time — they are never retroactively updated.

3. **Revocation walk.** When a consent record is revoked (SOP-DIU-608 revocation procedure), query the manifest for all entries with the matching `consent_record_id`. The Photo Shoot Director receives the full list. Revocation action (takedown, archive, notification) is CDO-directed per SOP-DIU-608 scope.

### D. Licensing Audit (on-demand or as part of SOP-DIU-615 integrity sweep)

1. Read the manifest for the client. Verify every entry has a non-null `consent_record_id` and `consent_record_version`.
2. Cross-check: for every entry where `likeness_present: true`, confirm the referenced consent record exists in `_local/consent/{client-id}.json` and its status was `active` at `delivered_at`.
3. For entries where `watermark_false_permitted: true`, confirm a valid manifest entry exists with `delivered_at` populated.
4. Report any gap to CDO as a blocking finding. Gaps are not self-closed.

---

## Inputs

| Input | Required | Source |
|---|---|---|
| Verified local asset path + sha256 | Yes | SOP-DIU-601 postflight receipt |
| Kie.ai taskId | Yes | SOP-DIU-602 generation receipt |
| Card ID + version, model, tier, filled prompt | Yes | SOP-DIU-602 generation receipt |
| Seed value (or `no-seed-endpoint` flag) | Yes | SOP-DIU-602 generation receipt |
| Reference image source paths | Conditional | SOP-DIU-609 hosting record; `"none"` if no references used |
| Consent record ID + version at generation time | Yes | `_local/consent/{client-id}.json` — managed by SOP-DIU-608 |
| Active consent scope modes | Yes | `_local/consent/{client-id}.json` |
| Disclosure table | Yes | `_local/rights-manifest/{client-id}/disclosure-table.json` |
| Delivery channel + jurisdiction | Yes | CDO delivery brief |
| Shoot ID | Yes | Photo Shoot Director |
| `watermark: false` flag (if applicable) | Conditional | SOP-DIU-601 preflight record for the Wan job |

---

## Outputs

| Output | Location | State at exit |
|---|---|---|
| Manifest entry (appended) | `_local/rights-manifest/{client-id}/RIGHTS-MANIFEST.md` | Appended; file is never overwritten |
| IDENTITY.md Shoot History pointer | `_local/IDENTITY.md` — Shoot History section | Updated with entry ID + delivery date |
| Photo Shoot Director notification | Via OpenClaw `message send` | Sent before delivery receipt is closed |
| Licensing audit report (on-demand) | Returned to CDO | Gap list or clean pass |
| Revocation asset list (on consent revocation) | Returned to Photo Shoot Director + CDO | All matching entries enumerated |

---

## Handoff Conditions

- **Normal delivery:** Manifest entry written and Photo Shoot Director notified before delivery receipt is marked complete. CDO closes the deliverable only after Director confirmation.
- **Wan `watermark: false` delivery:** Manifest entry written before delivery receipt is marked complete. The entry IS the permission gate — no entry, no delivery.
- **Consent revocation:** Photo Shoot Director receives the full asset list from the manifest query. CDO directs takedown/archive/notification. Generation Operator takes no action on revoked assets without CDO written direction.
- **Disclosure table version bump:** New version file written; manifest header updated; all future entries reference the new version; past entries are untouched.
- **Licensing audit clean pass:** Returned to CDO. No action required.
- **Licensing audit gap found:** Escalated to CDO as a blocking finding. No further delivery from the affected shoot until CDO resolves.

---

## Escalation Triggers

| Condition | Action |
|---|---|
| Manifest entry cannot be written before delivery (filesystem error) | Halt delivery immediately. Escalate to CDO. Do not deliver without a manifest entry. |
| Consent record absent or `status != active` at delivery time | Halt delivery. Escalate to Photo Shoot Director + CDO. Do not deliver without an active consent record. |
| `watermark: false` Wan job attempted without manifest entry | Hard stop. Write the manifest entry, then deliver. Never deliver `watermark: false` output without a manifest entry existing first. |
| `minors_present` would be `true` | This state must never exist at delivery. If reached, the job did not complete SOP-DIU-608 correctly. Halt delivery. Quarantine asset per SOP-DIU-604. Escalate to CDO immediately. |
| Consent record revoked after delivery — asset already in client's hands | Notify CDO immediately. Do not contact the client independently. CDO leads all communication and takedown decisions. |
| Manifest entry references a consent record that no longer exists in `_local/consent/` | Escalate to CDO and Photo Shoot Director. Do not assume the consent was valid — treat as a gap until resolved. |
| Disclosure table has not been reviewed in over 90 days for a jurisdiction with active deliveries | Flag to CDO in the SOP-DIU-615 Healer sweep output. CDO decides whether a re-review is required. |
| Licensing audit finds entries with `likeness_present: true` and no matching consent record | Blocking escalation to CDO + Photo Shoot Director. Do not use the affected card or any assets from the affected shoot until resolved. |

---

## Manifest Header Block (template — written once at initialization)

```
# Rights Manifest — {client-id}
**Created:** {ISO 8601 date}
**Maintained by:** Photo Shoot Director (entries written by Generation Operator at delivery)
**Disclosure table version:** {version}
**Disclosure table file:** _local/rights-manifest/{client-id}/disclosure-table.json
**Append-only:** true — entries are never edited or deleted. Corrections use `correction_of` field.
**C2PA mapping:** fields map 1:1 to Content-Credentials assertions; ready for signed provenance when providers expose it.
**Minors policy:** HARD-NO. No entry in this manifest may record a minor in any output. See SOP-DIU-608.
```

---

*Library-version pin: PHOTO-SHOOT-SOP v1.0, IDENTITY.md v1.0, MODEL-SPECS v1.0, TEST-PROTOCOL v1.0 (§-refs verified 2026-06-12).*
