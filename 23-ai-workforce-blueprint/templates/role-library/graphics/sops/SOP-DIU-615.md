# SOP-DIU-615 — DIU Integrity Sweep (Healer playbook)

**ID:** SOP-DIU-615
**Classification:** ZHC SOP — thin wrapper
**Owner Role:** Healer-Graphics (existing role; zero additional headcount)
**Section 9 slot:** 9.13
**Version:** 1.0 | **Date:** 2026-06-12
**Status:** CANONICAL
**Library-version pin:** INDEX.md v1.0, STYLE-CARD-TEMPLATE v1.0, MODEL-SPECS v1.0, DEPARTMENT-BUILD-BRIEF v1.0 (§-refs verified 2026-06-12)

---

## Role Mission

The Healer-Graphics runs this SOP on a scheduled cron basis (weekly minimum) and on-demand when the CDO or an operator requests a health check. The sweep is the mechanical ground-truth layer that keeps the DIU library self-consistent without human audit overhead: it detects INDEX drift, schema gaps, stale SOP pins, stuck jobs, and unreachable infrastructure before they cause silent failures or bad deliveries.

**HEARTBEAT POLICY: notify-on-change-only, heartbeat stays OFF.** This SOP MUST NOT be wired into a heartbeat or session-keepalive loop. It fires, checks, reports only if something changed, and exits. Wiring it to a heartbeat or session loop is a violation of fleet doctrine and creates owner-session spam — the 48,780-message fleet incident of 2026-06-12 is the recorded precedent. A clean sweep with nothing to report produces zero output. This is the intended behavior.

The Healer never touches the image API during a sweep. All checks are read-only against disk artifacts (INDEX.md, card files, receipts, quarantine, SOP files, MODEL-SPECS header, env stores). Ground truth comes from the files, not from API round-trips.

---

## Governing Library Files (source-of-truth — do NOT duplicate content)

| File | Sections used | What it governs |
|---|---|---|
| `_system/library/INDEX.md` | Header rules (registration, ID uniqueness, status column definitions, reserved namespace prefixes) | Authoritative card registry; bijection check reference; duplicate-ID check source |
| `_system/STYLE-CARD-TEMPLATE.md` | Filling instruction 3 (required sections, declared char-count annotation format, no empty sections, no TBD markers) | Card schema completeness requirements; char-count annotation format |
| `_system/MODEL-SPECS.md` | Header date, §1 (Seedream 3,000-char cap), §6 (model-bump change-control procedure) | MODEL-SPECS staleness threshold; Seedream silent-fail char ceiling; endpoint reachability baseline |
| `_system/DEPARTMENT-BUILD-BRIEF.md` | §4 (drift warning — what breaks when library files diverge from SOP pins) | Authoritative statement of the version-pin requirement and its enforcement rationale |

All checks reference these files at runtime. Do not encode model-specific char caps, status-column definitions, or threshold values directly in this SOP — the governing library files are the single source of truth and update independently.

---

## Procedure (ordered)

**Run all checks in sequence. Collect all findings before reporting. Report ONLY findings that are new or changed since the last sweep.**

### 1. INDEX bijection

Read every row in `_system/library/INDEX.md`. For each row, verify that the referenced card file exists at the declared path on disk. Then enumerate every file under `_system/library/` matching the card filename pattern. For each file, verify it has a corresponding INDEX.md row.

- **Orphaned INDEX row** (row exists, file absent): FAIL — `INDEX-BIJECTION FAIL: INDEX row {card-id} has no corresponding file at {path}`.
- **Unregistered card file** (file exists, no INDEX row): FAIL — `INDEX-BIJECTION FAIL: card file {filename} has no INDEX.md row`.

Both conditions are actionable failures, not warnings. A card that does not exist in both places simultaneously is not a production card.

### 2. No duplicate IDs

Grep `_system/library/INDEX.md` and all card files under `_system/library/` for any card ID that appears more than once. Also grep all SOP files in `sops/` for any `[SOP-DIU-` tag that appears more than once repo-wide.

- Any duplicate card ID: FAIL — `DUPLICATE-ID FAIL: card ID {id} appears in {file-list}`.
- Any duplicate SOP tag: FAIL — `DUPLICATE-SOP-TAG FAIL: [SOP-DIU-{NNN}] appears in {file-list}`.

This check satisfies the T12 QC requirement that `grep -rE 'SOP-DIU-[0-9]{3}' --include='*.md'` returns no duplicate IDs across the repo.

### 3. Card schema completeness lint

For every card file under `_system/library/`:

1. Verify no section required by STYLE-CARD-TEMPLATE filling instruction 3 is empty.
2. Verify no section contains a `TBD` marker or a line consisting solely of a placeholder.
3. Verify no prompt tier block contains an unfilled `{[A-Z_]+}` variable token.

- Draft-status card with any empty section: WARN — `SCHEMA-WARN: card {card-id} has empty section [{section-name}] (status: draft)`.
- Production or tested card with any empty section or unfilled token: FAIL — `SCHEMA-FAIL: card {card-id} has empty section [{section-name}] or unfilled token (status: {status}). Production cards must be complete.`

### 4. ACTUAL char count vs declared (Seedream silent-fail protection)

For every card that has a declared character-count annotation line (format per STYLE-CARD-TEMPLATE filling instruction 3):

1. Recount the actual characters in the relevant prompt tier block.
2. Compare the actual count to the declared count. A discrepancy of more than 5 characters is a FAIL.
3. Regardless of declaration, for every card's Seedream prompt tier:
   - Actual count 2,801–3,000 characters: WARN — `CHAR-WARN: card {card-id} Seedream tier is {count} chars (approaching 3,000-char silent-fail ceiling)`.
   - Actual count > 3,000 characters: FAIL — `CHAR-FAIL: card {card-id} Seedream tier is {count} chars — EXCEEDS 3,000-char ceiling. This prompt will fail silently on Seedream with no API error.`

The 3,000-char ceiling is the Seedream silent-fail boundary documented in MODEL-SPECS §1. This check must never be omitted even if the card has no declared annotation line.

### 5. 6xx SOP version pins

For every SOP file in `sops/` that contains a `Library-version pin:` line (required on all 6xx SOPs per ZHC SOP authoring rules):

1. Parse the pinned version for each referenced library file.
2. Read the current version from the referenced library file's header.
3. Compare.

- Pin matches current version: silent pass.
- Any mismatch: FAIL — `PIN-FAIL: SOP-DIU-{NNN} version pin STALE: pinned [{pinned-version}], current [{actual-version}] for {library-file}. Re-pin required before this SOP can be trusted.`

Flag these LOUDLY. A stale pin means the SOP's procedure steps may reference sections that no longer exist or have moved. This is the most dangerous silent failure in the thin-wrapper architecture — the SOP executes with confidence against a different document than it was verified against.

### 6. Quarantine folder empty or escalated

List all asset files in `_local/quarantine/`. For each:

1. Verify an incident file exists at `_local/quarantine/{asset-id}-incident.json` (or equivalent, per the quarantine naming convention).
2. Verify the incident file contains a non-null `cdo_notified_at` timestamp.
3. Verify the incident file contains a non-null `resolution` field (accepted values: `pending-CDO-review`, `regenerated`, `discarded`, `client-comms-sent`; any non-null value is sufficient for this check).

- Quarantined asset without a corresponding incident file: FAIL — `QUARANTINE-FAIL: asset {filename} in quarantine has no incident file`.
- Incident file without `cdo_notified_at`: FAIL — `QUARANTINE-FAIL: incident {incident-id} has no CDO notification timestamp. CDO must be notified of every quarantined asset`.
- Incident file without a `resolution` field: FAIL — `QUARANTINE-FAIL: incident {incident-id} has no resolution. This asset is unresolved in quarantine`.

An empty quarantine folder with zero files: silent pass.

### 7. Embedding coverage

1. Read the embedding index manifest at `_system/library/embedding-manifest.json` (or the equivalent path recorded in the SOP-DIU-606 setup). Count entries.
2. Count all card rows in INDEX.md with status `production` or `tested`.
3. If the counts differ (coverage does not equal card count): WARN — `EMBEDDING-WARN: embedding coverage {actual} != production+tested card count {expected}. SOP-DIU-606 rebuild required. Notifying Style Analyst.` Trigger the rebuild notification to the Style Analyst via `openclaw message send`.

Note: the embedding index is a derived artifact — it is rebuildable from card files at any time and is explicitly not authoritative (INDEX.md is authoritative). This check ensures retrieval serves current cards. A coverage mismatch is a WARN, not a FAIL, because the production pipeline continues on INDEX.md; retrieval is a hint layer.

### 8. Receipt age — stuck job detection

List all receipt files in `_local/receipts/` with `state` equal to `submitted` or `polling`. For each:

1. Read the `last_polled` timestamp.
2. If `last_polled` is more than 24 hours before the current sweep timestamp: FAIL — `STUCK-JOB FAIL: receipt {receipt-id} is in state {state} with last_polled {last_polled} ({hours} hours ago). CDO attention required.`

The Healer reports the stuck job but does NOT call the Kie.ai API directly. Ground truth comes from the receipt file on disk. A CDO-directed re-poll is the correct next step; the Healer escalates, the Generation Operator executes.

### 9. MODEL-SPECS staleness

Read the header date in `_system/MODEL-SPECS.md`. If the date is more than 90 days before the current sweep date:

FAIL — `MODEL-SPECS FAIL: MODEL-SPECS.md header date is {date} -- over 90 days old. CDO should trigger a Healer model-currency census (SOP 9.6) to review endpoint and model changes.`

MODEL-SPECS is the load-bearing document for all generation routing. A document more than 90 days old without a review has a material probability of containing retired endpoints, changed char caps, or deprecated models.

### 10. Kie.ai key and endpoint reachability

1. Search every env store for `KIE_API_KEY` in the following order: `secrets/.env`, `openclaw.json`, `~/.openclaw/workspace/.env`, `~/clawd/secrets/.env`, and the running gateway process env. Applying the client-box-env-stores policy: check all stores before reporting missing.
   - Key absent from all stores: FAIL — `KIE-KEY FAIL: KIE_API_KEY not found in any env store (searched: {list-of-stores-checked})`.
2. Perform a lightweight reachability probe against the Kie.ai primary endpoint (a HEAD request or a model-list GET that requires no credits and produces no billable activity).
   - Non-2xx response: FAIL — `KIE-ENDPOINT FAIL: primary Kie.ai endpoint returned HTTP {status}. Verify account status and endpoint URL in MODEL-SPECS §1`.

### 11. Registrar activation counter

Count all rows in INDEX.md with status `production` or `tested`.

- Count >= 50: flag — `REGISTRAR-THRESHOLD: {N} production+tested cards in INDEX.md. CDO should activate the Library Registrar role per SOP-DIU-606 step 9 (Registrar duty currently folded into Style Analyst; promotion to standalone role is warranted above 50 cards).`

This is an informational flag, not a FAIL. Generation and testing continue. The flag is the Healer's mechanical trigger for the Registrar promotion procedure documented in SOP-DIU-606 and the FORESIGHT addendum §1.2.

---

## Inputs

| Input | Required | Source |
|---|---|---|
| `_system/library/INDEX.md` | Yes | DIU library system; read-only during sweep |
| All card files under `_system/library/` | Yes | DIU card library; read-only |
| `_system/STYLE-CARD-TEMPLATE.md` | Yes | DIU library system; read-only |
| `_system/MODEL-SPECS.md` | Yes | DIU library system; read-only |
| `_system/DEPARTMENT-BUILD-BRIEF.md` | Yes | DIU library system; read-only |
| All SOP files under `sops/` | Yes | DIU SOP library; read-only |
| `_local/receipts/` (all receipt files) | Yes | Generation Operator outputs; read-only |
| `_local/quarantine/` (all quarantine files) | Yes | SOP-DIU-604 outputs; read-only |
| `_system/library/embedding-manifest.json` (or equivalent) | Yes | SOP-DIU-606 output; read-only |
| All env stores on the client box | Yes | Standard client-box env stores per fleet policy |
| Previous sweep findings log (`_local/healer/last-sweep.json`) | Yes (creates if absent) | Healer own output; used to suppress findings unchanged since last sweep |

---

## Outputs

| Output | Location | State at exit |
|---|---|---|
| Sweep findings report (on WARN or FAIL only) | Sent via `openclaw message send` to CDO | Emitted only if findings changed since last sweep |
| Embedding rebuild notification (on coverage mismatch) | Sent via `openclaw message send` to Style Analyst | Emitted only on Check 7 WARN |
| Stuck-job alert (on Check 8 FAIL) | Sent via `openclaw message send` to CDO and Generation Operator | Emitted only on new stuck receipts |
| Last-sweep state file (updated every run) | `_local/healer/last-sweep.json` | Written at end of every sweep (pass or fail) with timestamp and findings fingerprint |
| No output (on clean sweep with no changes) | — | Deliberately silent |

---

## Handoff Conditions

- **Clean sweep (all checks pass, nothing changed):** No message sent. `last-sweep.json` updated with timestamp and `status: clean`. Exit. This is the expected steady-state result.
- **One or more WARN findings:** Send report to CDO listing each WARN with severity, check name, exact file or path implicated, and recommended action. CDO decides whether immediate action is required.
- **One or more FAIL findings:** Send report to CDO. FAIL conditions represent active integrity violations. CDO directs the appropriate role (Style Analyst for INDEX/schema/embedding; Generation Operator for stuck receipts or key issues; Photo Shoot Director for quarantine gaps; Healer for SOP pin staleness).
- **Check 7 coverage mismatch:** Additionally notify Style Analyst directly with the rebuild trigger message.
- **Check 8 stuck job:** Additionally notify Generation Operator directly with the receipt ID and stuck duration.
- **Check 11 Registrar threshold reached:** Notify CDO with the counter value and the promotion procedure reference.

---

## Escalation Triggers

| Condition | Action |
|---|---|
| Healer cannot read any required input file (permissions error, disk error, file missing) | Emit a single FAIL report: "SOP-DIU-615 sweep aborted — cannot read {path}. No sweep completed. CDO action required." Never claim a clean sweep if the sweep could not complete. |
| Any FAIL finding involving a quarantined hard-rule-violation asset | Send report immediately; do not wait for next scheduled sweep. Notify CDO and Photo Shoot Director. |
| KIE_API_KEY absent from all env stores | Hard FAIL with full list of stores checked. Notify CDO immediately. Generation pipeline is unrunnable. |
| SOP version pin staleness found on any 6xx SOP | FAIL report to CDO. Generation using that SOP should be paused until the pin is re-verified and updated by the owning role. |
| Seedream prompt tier over 3,000 characters on a production card | FAIL report to CDO and Style Analyst. Active Seedream generations using this card will silently fail with no API error. Card must be corrected before any further Seedream generation against it. |
| MODEL-SPECS.md header date over 90 days old | FAIL report to CDO. Flag as requiring model-currency census (SOP 9.6). |
| Sweep was last completed more than 14 days ago (detected from `last-sweep.json`) | WARN in the report header: "Last sweep was {N} days ago — over the 14-day maximum interval. Verify scheduled cron is running." |

---

## What the Healer Must Never Do During a Sweep

- Call any Kie.ai image generation endpoint or task endpoint
- Write to or modify INDEX.md, card files, SOP files, or any library file
- Delete quarantine assets or close quarantine incidents
- Send "all clear" heartbeat messages (notify-on-change-only is a hard rule)
- Re-poll stuck receipts directly (escalate to CDO; Generation Operator executes the re-poll)
- Report findings as resolved without verifying the fix from disk

---

*Library-version pin: INDEX.md v1.0, STYLE-CARD-TEMPLATE v1.0, MODEL-SPECS v1.0, DEPARTMENT-BUILD-BRIEF v1.0 (§-refs verified 2026-06-12).*
