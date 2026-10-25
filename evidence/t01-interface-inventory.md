# T-01 — Current onboarding interfaces at pinned main

Unit: **PBB-206** (rebuild of the refused PBB-182 revision); re-stamped at the current pin by **PBB-237**
on 2026-10-24. Ledger task: **T-01**, interface inventory.
Repository: `trevorotts1/openclaw-onboarding`.
Mode: read-only reconnaissance plus execution of the repository's own stdlib self-checks.
No product code was changed. Nothing was pushed. No pull request was opened. No merge was performed.

Every absence claim in this document is scoped to **one commit**, named below, and to the tracked
content of that commit. It is not a claim about any other branch, any other commit, or any client box.

Status vocabulary (unchanged from the earlier revisions):

| Status | Meaning |
|---|---|
| **PRESENT** | An executable interface with an entry point and a caller-visible input/output exists at the pin. |
| **PARTIAL** | Part of the interface exists in code and part exists only as documentation or a contract schema. |
| **ABSENT** | No executable interface exists at the pin. Named only, or absent entirely. |

---

## 0. The pin, and why the previous revision was refused (D1)

| Item | Value |
|---|---|
| Pin SHA | `9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865` |
| Commit subject | `Merge pull request #2548 from trevorotts1/batch/s75-b2` |
| Commit date | 2026-10-24 17:56:32 -0400 |
| Fetched (UTC) | 2026-10-24T22:12:40Z (re-stamp session PBB-237; the earlier PBB-206 revision was pinned at `144ec54507695371b0eaea1e06a561d7cd76273b` with fetch time 2026-10-24T21:01:33Z) |
| How verified | `git fetch --prune origin main`, then `git rev-parse origin/main`; cross-checked with `gh api repos/trevorotts1/openclaw-onboarding/commits/main` at 2026-10-24T22:12:40Z, same SHA |
| Remote truth at fetch | `9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 refs/heads/main` (`PIN.remote-main`, rc=0) |
| Worktree HEAD at run | `9ed73df16ec55dacf503ab0d01603544ea58469f`, two evidence-only commits above the pin, so the harness preflight records `worktree_at_pin: false` and `pin_is_ancestor_of_head: true`. Every search command names the pin SHA itself, so the checkout cannot move the answers; only the pin's tracked content is read. |
| Tracked files | 13,672 (`PIN.tracked-files`, rc=0) |
| Repo `version` | `v27.1.65` (unchanged) |
| Skill 38 `skill-version.txt` | `v2.0.33` (was `v2.0.32`) |

The refused revision called `bccc4050f8ed98b2d9b55cfc087c27c924d62b03` "origin/main" and derived its
absences there. It was not main even then, and main has moved twice since. Measured now:

| Baseline | Commits ahead of it | Merges ahead of it | Search |
|---|---|---|---|
| `bccc4050f` (the refused revision's base) | **183** | **77** | `PIN.commits-ahead-of-bccc4050f` / `PIN.merges-ahead-of-bccc4050f`, rc=0 |
| `f0a9c80e` (the SHA the FAIL verdict called current main) | **41** | **21** | `PIN.commits-ahead-of-f0a9c80e` / `PIN.merges-ahead-of-f0a9c80e`, rc=0 |

Main moved 41 commits (21 merges) between the FAIL verdict's `f0a9c80e` and this fetch. That is the
argument for recording a fetch time alongside the SHA, and it is why this document cites
`9488ccbc8`, not the verdict's `f0a9c80e`.

### Changed since `144ec545` (dated 2026-10-24, re-stamp PBB-237)

The previous revision of this document was pinned at `144ec54507695371b0eaea1e06a561d7cd76273b`.
Every probe was re-run at `9488ccbc8`. Seven results moved. Six are properties of the pin's tracked
content; the `PIN.*` live rows are observations of GitHub and the local host at run time, not
properties of any commit.

| What | At `144ec545` | At `9488ccbc8` | Command (abridged) | rc |
|---|---|---|---|---|
| `O3.absent-handoff-lifecycle` | ABSENT (rc=1, n=0) | **PRESENT (rc=0, n=23)** | `git grep -niE handoff_accept\|handoff_due\|handoff-lifecycle\|backup_owner\|backup-owner <pin> -- .` | 0 |
| `PIN.tracked-files` | 13,636 | 13,672 | `git ls-tree -r --name-only <pin>` | 0 |
| `R4.adapter-file-census` | 147 | 150 | `git ls-tree -r --name-only <pin>`, case-insensitive `adapter` filter | 0 |
| `C4.sms-email-ask` | 14 | 15 | `git grep -nF max_sms_email_asks <pin> -- .` | 0 |
| Skill 38 `skill-version.txt` | `v2.0.32` | `v2.0.33` | `git show <pin>:38-conversational-ai-system/skill-version.txt` | 0 |
| `PIN.remote-branches` (live) | 1,884 | 1,901 | `git ls-remote --heads origin` | 0 |
| `PIN.worktree-count` (live) | 89 | 93 | `git worktree list` | 0 |

Unchanged and re-derived: `PIN.open-pr-count` = **8** (`gh pr list … --json number --jq length`, rc=0;
the set moved — PR 2546 closed and PR 2549 opened — but the count did not), and repo `version` =
**v27.1.65** (`git show <pin>:version`, rc=0).

O3 became PRESENT because `21f9be77a258debb382c093e39b420b54a199693` — `feat(handoff): owned human
handoff with acceptance, due, backup and fence (T-29)` — added `shared-utils/handoff/handoff.py`
(658 lines) and `shared-utils/handoff/tests/test_handoff.py` (522 lines). It is an ancestor of the pin
(`git merge-base --is-ancestor 21f9be77a 9488ccbc8`, rc=0). The search id is kept unchanged so the
absent → present history is legible; it is the same probe, answered at two pins.

`PIN.remote-branches`, `PIN.worktrees` and `PIN.worktree-count` read live state at run time, so a later
run will legitimately differ. They are recorded as observations, never as claims about the pin.

### Claims of absence that flipped, re-derived at the pin

Each row below was an ABSENT claim in the refused revision. Each is now re-run at `9488ccbc8` with the
actual exit code and match count from this session.

| # | What flipped | Search id | Command (abridged) | rc | count | Verdict now |
|---|---|---|---|---|---|---|
| J4 | `approval-manifest.schema.json` exists | `J4.approval-schema` | `git ls-tree -r --name-only <pin> -- 38-conversational-ai-system/schemas/approval-manifest.schema.json` | 0 | 1 | PRESENT |
| J4 | the schema's own title says it is the joined 30-day manifest | `J4.approval-title` | `git grep -nF "Revisioned monthly approval manifest" <pin> -- …/approval-manifest.schema.json` | 0 | 1 | PRESENT |
| J5 | `tools/direct_fulfillment.py` and `pb_contracts.py:68-69` (`"keyword"`, `"promised_item_version"` in `PLACEMENT_BOUND_FIELDS`) exist | `J5.name-probe` | `git grep -niE "<the five J5 phrases, ERE alternation>" <pin> -- *.py *.sh` (exact command in the register) | 0 | 6 | PRESENT |
| C5 | `pb_contracts.py:342-358` validates reminder slots | `C5.reminder-slots` | `git grep -nF "reminder_slots" <pin> -- .` | 0 | 20 | PRESENT |
| F2 | `38-conversational-ai-system/tools/direct_fulfillment.py` exists (authored in `d117da5ce`, merged to `main` in `ad06494f6`) | `F2.fulfillment-file` | `git ls-tree -r --name-only <pin> -- …/tools/direct_fulfillment.py` | 0 | 1 | PRESENT |
| R3 | `pb_contracts.py:980` implements `COMMENT_PRIVATE_OPENER` | `R3.private-opener` | `git grep -nF "COMMENT_PRIVATE_OPENER" <pin> -- .` | 0 | 4 | PRESENT |

Two further absences flipped that the verdict did not name, found by re-deriving every row rather than
only the five it listed:

| # | What flipped | Search id | rc | count |
|---|---|---|---|---|
| G5 | `tools/bootstrap_engine.py` is the T-36 `client-bootstrap-engine` | `G5.bootstrap-file`, `G5.bootstrap-name` | 0 | 1, 2 |
| C4 | the SMS/email ask and reminder budget exist as a validated collection contract | `C4.capture-budget`, `C4.sms-email-ask` | 0 | 2, 15 |

Nothing in the earlier revision's **substance** was invented. The defect was the pin: the contracts
layer (commit `053c4fee9`, "feat(contracts): bind shared collection, outbound, approval, readiness and
action-lifecycle contracts (T-08)") landed after `bccc4050f`, and every one of those rows describes code
that now exists.

---

## Verdict summary

| Status | Count |
|---|---|
| PRESENT | 19 |
| PARTIAL | 5 |
| ABSENT | 1 |
| **Total interfaces inspected** | **25** |

The single remaining ABSENT row is R4, the per-surface route **adapter** interface. Its policy layer
now exists (R3, PRESENT); the adapter interface itself does not.

---

## 1. Guided setup entry points and inputs

| # | Interface | Status | Evidence (file:line + quoted line) | Search result |
|---|---|---|---|---|
| G1 | Installer entry point (8 documented kickoff paths: Mac/VPS, full/update, terminal/Telegram) | PRESENT | `ONBOARDING-TRIGGERS.md:3` — `… There are **8 different ways to do it**, depending on …`; `install.sh:8` — `#  Run via: curl -fSL --progress-bar https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/install.sh \| bash` | `G1.trigger-count` rc=0 n=1; `G1.install-entry` rc=0 n=1 |
| G2 | Owner / company / optional owner-email identity collection before resources | PRESENT | `install.sh:3077` — `collect_onboarding_identity() {`; `install.sh:3106` — `collect_onboarding_identity \|\| exit 8`; `scripts/onboarding-identity.py:16` — `QUESTIONS = {'ownerName': …`; `:143` — `return 8 if result['status'] == 'needs-input' else 0` | `G2.identity-def` rc=0 n=1; `G2.identity-exit8` rc=0 n=1; `G2.identity-questions` rc=0 n=1 |
| G3 | Client intake question engine with resume (`next`/`record`/`help`/`check`/`finalize`) | PRESENT | `shared-utils/client_intake/engine.py:2` — `"""Client intake engine: one question bank, one answers file per run …`; `:333` — `def next_question(doc, bank=None):`; `:594` — `def record(doc, qid, value, *, source="client", …)`; `:829` — `def finalize(doc, bank=None):` | `G3.intake-engine` rc=0 n=1 |
| G4 | Guided business/audience/offer discovery brief (T-06) | PRESENT | `38-conversational-ai-system/tools/acquisition_brief.py:2` — `"""Guided business, audience and offer discovery for Skill 38 (T-06).`; `:310` — `class AcquisitionBrief:`; `:456` `record_fact`, `:615` `next_questions`, `:769` `answer`, `:966` `is_campaign_ready` | `G4.acquisition-brief` rc=0 n=1 |
| G5 | Idempotent client-bootstrap engine with provision diff and step receipts (T-36, output `client-bootstrap-engine`) | **PRESENT** (was ABSENT) | `38-conversational-ai-system/tools/bootstrap_engine.py:4` — `Contract basis: Purple-Billboard TODO T-36 ("client-bootstrap-engine") and`; `:460` — `def plan(self, specs: Sequence[ResourceSpec]) -> Plan:`; `:562` — `def run(`. The module's own doctrine separates the pure diff from the writer, and `CHANGELOG.md:66` binds the T-36 output name to this file. | `G5.bootstrap-file` rc=0 n=1; `G5.bootstrap-name` rc=0 n=2; `G5.bootstrap-plan` rc=0 n=1; `G5.bootstrap-run` rc=0 n=1 |

There is still **no single guided-setup object** carrying these into a provisioning plan. `bootstrap_engine.py`
consumes `ResourceSpec` values; G2/G3/G4 remain three separate stores. The engine is the writer, the
three stores are the sources, and no module yet projects one into the other.

---

## 2. Join / campaign entry

| # | Interface | Status | Evidence (file:line + quoted line) | Search result |
|---|---|---|---|---|
| J1 | Campaign publishing entry (single-topic orchestrator) | PRESENT | `35-social-media-planner/scripts/run-publishing-cycle.sh:14` — `#  Usage:` (the `--topic` / `--platforms` block follows) | `J1.publishing-cycle` rc=0 n=4 |
| J2 | Scheduled weekly campaign entry (cron) | PRESENT | `35-social-media-planner/scripts/weekly-batch.sh:6` — `#  Cron-driven weekly batch (\`0 9 * * 1\`) that reads` | `J2.weekly-batch` rc=0 n=1 |
| J3 | Skill 57 client-driven `campaign` creative mode | PRESENT | `57-social-media-in-a-box/social-media-entry.sh:53` — `  --mode MODE     engine : week \| day \| carousel \| video \| podcast-cover \| plan \| clean`; `57-social-media-in-a-box/modes.md` names the `campaign` mode | `J3.campaign-mode` rc=0 n=2 |
| J4 | Joined 30-day monthly approval manifest with version enforcement (T-23, output `monthly-approval-contract`) | **PRESENT** (was ABSENT) | `38-conversational-ai-system/schemas/approval-manifest.schema.json:3` — `"title": "Revisioned monthly approval manifest, one joined 30-day campaign",`; `:4` binds it to `DATA-CONTRACTS section 10 and DEC-02`; `pb_contracts.py:393` — `def semantic_approval(doc):`; `:1036` — `def approval_errors(action, manifest_path):`, which refuses a stale `approval_revision`, a non-`APPROVED` placement, and divergence on each of the ten `PLACEMENT_BOUND_FIELDS`. | `J4.approval-schema` rc=0 n=1; `J4.approval-title` rc=0 n=1; `J4.approval-semantic` rc=0 n=1; `J4.approval-binding` rc=0 n=1 |
| J5 | Stable promised-item keyword / join mapping | **PRESENT** (was ABSENT) | `direct_fulfillment.py:118` — `"""The immutable original promise. Hosting location is not identity."""`; `:136` — `"not_approved: the original promised item is not approved"`; `pb_contracts.py:68` — `"keyword",` inside `PLACEMENT_BOUND_FIELDS`, so an action's keyword must equal the approved placement's keyword or dispatch is refused. | `J5.promised-item` rc=0 n=1; `J5.keyword-bound` rc=0 n=2; `J5.immutable-item` rc=0 n=1; `J5.name-probe` rc=0 n=6 |

The **literal output names** `monthly-approval-contract` and `direct-original-fulfillment` are still
absent: `J4.absent-artifact-name` rc=1 n=0 (control 66) and `F2.absent-artifact-name` rc=1 n=0
(control 66). That is a naming gap, not a capability gap, and the status column reflects the capability.

---

## 3. Posting / comment / DM route selection

| # | Interface | Status | Evidence (file:line + quoted line) | Search result |
|---|---|---|---|---|
| R1 | Per-channel / account-type capability declaration and assisted-placement route (T-22) | PRESENT | `35-social-media-planner/config/profile-capabilities.json:2` — `"$schema_note": "T-22 honest personal-profile capability declaration and assisted contract. …`; `shared-utils/personal_profile_capability.py:154` — `def get_capability(`; `:226` — `def request_placement(`. Executed: the CLI returns `"mode": "assisted"` with `"forbidden_assisted_statuses": ["published-by-system","published"]` (see §10). | `R1.capability-declaration` rc=0 n=1 |
| R2 | Comment-read route selection with per-channel honesty | PRESENT (FB/IG only; others explicitly unavailable) | `35-social-media-planner/scripts/comment_reader.py:75` — `CHANNEL_COMMENT_SURFACE = {`; `:221` — `if channel not in CHANNEL_COMMENT_SURFACE:`; `:225` — `surface = CHANNEL_COMMENT_SURFACE[channel]` | `R2.comment-surface` rc=0 n=4 |
| R3 | DM entry route (GHL Conversations inbound hook) and DM call-to-action, including the private-opener purpose | **PRESENT** (was PARTIAL) | `38-conversational-ai-system/tools/pb_contracts.py:980` — `if action["purpose"] == "COMMENT_PRIVATE_OPENER" and gate["inbound_dm_window"]:`; the outbound schema enumerates the purpose (`schemas/outbound-action.schema.json:788` — `"COMMENT_PRIVATE_OPENER",`) and a fixture exercises it (`tools/tests/fixtures/pb-contracts/outbound/person-comment-opener.json:4`). Hook writer: `15-configure-hooks-mappings.sh` still builds `s38_canonical_mapping`. DM CTA documented: `35-social-media-planner/references/playbook.md:1042` — `The post itself contains BOTH a DM call-to-action (primary …`. | `R3.private-opener` rc=0 n=4; `R3.hook-writer` rc=0 n=2 |
| R4 | Per-surface route adapters (T-20 Page comment/Messenger, T-21 Instagram, output `instagram-route-adapter`) | **ABSENT** | No adapter interface, module or file. All four output names return nothing: `instagram-route-adapter`, `page-comment-adapter`, `messenger-route-adapter`, `private-opener-adapter`. The filename census on `adapter` returns 150 paths; none is a Page-comment, Messenger, IG-DM or private-opener route adapter. The policy that a route *would* call now exists in `pb_contracts.py` (R3); the per-surface adapter layer does not. | `R4.absent-adapter-names` rc=1 n=0, control `book_appointment` n=66; `R4.adapter-file-census` rc=0 n=150 |

Scope note so the R4 negative is not read as broader than it is: `identity` mapping exists
(`tenant_identity.py:48` maps `facebook`/`messenger` to `fb_psid`, `instagram` to `ig_psid`, `sms` to
`sms_number`). That resolves *who* a message is from; it does not route *where* a reply goes.

---

## 4. Gift fulfillment hooks

| # | Interface | Status | Evidence (file:line + quoted line) | Search result |
|---|---|---|---|---|
| F1 | Gift / asset inventory and preparation worklist (precondition, not delivery) | PARTIAL | `38-conversational-ai-system/tools/asset_registry.py:372` — `class AssetRegistry:`; `:584` — `def record_present(`. It plans and records preparation; it does not deliver. Delivery now lives in F2. | `F1.asset-registry` rc=0 n=1 |
| F2 | Direct original / promised-item fulfillment hook (T-13, output `direct-original-fulfillment`) | **PRESENT** (was ABSENT) | `38-conversational-ai-system/tools/direct_fulfillment.py:462` — `def fulfill(store: DurableStore, ledger: FulfillmentLedger,`; `:632` — `def record_delivery_proof(store: DurableStore, item: PromisedItem,`. The module states its own guarantees: `IMMUTABLE.` (item identity is `(item_id, version, content_sha256)`), `AT-MOST-ONCE.` (one outbox action, fenced lease), `EVIDENCE.` (`Provider admission is labelled accepted/sent, never "delivered".`), `RESUME.` | `F2.fulfillment-file` rc=0 n=1; `F2.fulfill-entry` rc=0 n=1; `F2.receipt` rc=0 n=1 |

The separate **commerce** fulfillment path (`shared-utils/signature_launch/events/events.py`,
`44-convert-and-flow-operator/tools/siglaunch/fulfillment_map/`) is still not the PBB gift interface; it
is keyed to purchase events and entitlements. F2 is the conversation-side promise.

---

## 5. Contact capture and follow-up

| # | Interface | Status | Evidence (file:line + quoted line) | Search result |
|---|---|---|---|---|
| C1 | Canonical contact identity across FB / IG / SMS / email | PRESENT | `38-conversational-ai-system/tools/tenant_identity.py:48` — `CHANNEL_IDENTIFIER_TYPES = {`; `:109` — `reminder_total       INTEGER NOT NULL DEFAULT 0,` | `C1.channel-identifier-types` rc=0 n=2; `C1.reminder-column` rc=0 n=6 |
| C2 | Collection lock and durable capture cursor | PRESENT | `collection_lock.py:501` — `class CaptureStore:`; `:530` — `def begin(`; `:573` `def advance(`; `:633` `def complete(`; `:654` `def reject(` | `C2.capture-store` rc=0 n=1 |
| C3 | Consent gate: refusal, channel opt-out, global stop, human precedence, partial capture | PRESENT | `consent_gate.py:85` — `SCOPE_OFFER = "offer"`; `:299` — `def human_takeover(self, tenant_id: str, canonical_contact_id: str, *,`; `:325` — `def human_release(self, tenant_id: str, canonical_contact_id: str, *,`; `:584` `make_gate_evaluator` | `C3.consent-offer-scope` rc=0 n=4; `C3.human-fence` rc=0 n=1 |
| C4 | Mobile-first progressive capture with one logical SMS email ask (T-16, output `progressive-capture-candidate`) | PARTIAL | The contract exists and is validated: `schemas/collection-state.schema.json:72` — `"capture_budget": {`; `:79` — `"max_sms_email_asks": {`; `pb_contracts.py:333-339` refuses `reminders_used > max_reminders`, `sms_email_asks_used > max_sms_email_asks`, and `reminders_used < reminders_accepted`. Missing: the ask-state engine that would produce `progressive-capture-candidate` — the output name is absent. | `C4.capture-budget` rc=0 n=2; `C4.sms-email-ask` rc=0 n=15; `C4.absent-artifact-name` rc=1 n=0 (control 66) |
| C5 | Reminder slots, final reserved action and terminal stop (T-17, output `reminder-state-machine`) | **PRESENT** (was ABSENT) | `pb_contracts.py:341` — `# Section 8: three distinct slots, in order.`; `:342` — `slots = doc["reminder_slots"]`; `:345`/`:347` refuse duplicate and out-of-order slot numbers; `:358` — `errs.append("$.reminder_slots: due_at must increase across slots")`. `reminder_slots` appears 20 times across the schema, validator, tests and fixtures. The `reminder_total` counter in `tenant_identity.py` is no longer the only reminder artefact. | `C5.reminder-slots` rc=0 n=20; `C5.slot-order-rule` rc=0 n=1; `C5.absent-artifact-name` rc=1 n=0 (control 66) |
| C6 | Follow-up cadence after a stalled conversation | PARTIAL | The protocol exists: `38-conversational-ai-system/protocols/intelligent-followup-protocol.md:1` — `# Intelligent Follow-up Protocol`. The only code that reads it is a static QC linter: `scripts/qc-zhc-tag-prefix.sh:157,163,167,169,219`. No cron or schedule asset binds it to a run. | `C6.followup-protocol` rc=0 n=1; `C6.protocol-readers` rc=0 n=5 (control 34); `C6.runtime-scheduler` rc=1 n=0 (control 2625) |

C6's scheduler negative is deliberately narrow: the pattern is the protocol filename, the scope is
paths whose name contains `cron`, `schedule` or `04-register`, and the control on that same scope
returns 2,625 matches. The protocol being read is not the protocol being run.

---

## 6. Offer / booking / handoff

| # | Interface | Status | Evidence (file:line + quoted line) | Search result |
|---|---|---|---|---|
| O1 | Offer interface (offer selection or routing) | PARTIAL | Offer is a first-class scoped value: `consent_gate.py:85` — `SCOPE_OFFER = "offer"` (6 matches under `tools/`); discovery questions in `acquisition_brief.py`. Missing: selection/routing inside the PBB conversation surface — `select_offer`, `offer_route`, `pick_offer`, `choose_offer`, `offer_select` return nothing across `38-`, `35-` and `57-`. | `O1.offer-scope` rc=0 n=6; `O1.offer-route-absent` rc=1 n=0 (control 55) |
| O2 | Booking execution / follow-through adapter (T-28, output `booking-followthrough-adapter`) | PARTIAL | Documented protocol: `protocols/smart-booking-protocol.md:37` — `` `caf calendars book` first, Tier 3 `POST /calendars/events/appointments` as the ``. The adapter output name is absent. | `O2.booking-protocol` rc=0 n=1; `O2.absent-artifact-name` rc=1 n=0 (control 66) |
| O3 | Owned human handoff: context, acceptance, due time, backup owner and fence (T-29) | **PRESENT** (was PARTIAL) | Executable module `shared-utils/handoff/handoff.py` with a runnable entry point (`:681` — `if __name__ == "__main__":`, `:682` — `_self_check()`). `HandoffStore.create` (`:266`), `.accept` (`:348`), `.escalate` (`:376`), `.backup_accept` (`:413`), `.release` (`:456`), `.get` (`:507`) expose the caller-visible lifecycle; `:434` — `if actor != row["backup_owner_id"]:`; `:529` — `"backup_owner_id": data["backup_owner_id"],`. Tests: `shared-utils/handoff/tests/test_handoff.py:113` — `def test_create_requires_a_distinct_backup_owner(self):`. Fence also present at `consent_gate.py:299` `human_takeover` and `:325` `human_release`; loop lifecycle at `pb_contracts.py:74` — `LIFECYCLE_LADDER = [...]`. Introduced by `21f9be77a` (T-29). | `O3.human-fence` rc=0 n=1; `O3.lifecycle-ladder` rc=0 n=1; `O3.absent-handoff-lifecycle` rc=0 n=23 (control 66) |

At the previous pin (`144ec545`) this row was PARTIAL and the handoff lifecycle was genuinely
missing: `O3.absent-handoff-lifecycle` returned rc=1 n=0. It became PRESENT at `9488ccbc8` with
`21f9be77a` (T-29), which added `shared-utils/handoff/handoff.py` and its test module. The
`pb_contracts.py:74` `LIFECYCLE_LADDER` is a separate thing — the engineering-loop lifecycle — and is
no longer the only lifecycle evidence for O3.

---

## 7. Ledger-gap closure: D-11, D-12, D-13, D-15

The ledger rows behind R-24 and R-25 named four gaps. Each is addressed here explicitly. Two are now
closed by code that landed after the refused base; one is partly closed; one is still open. The
reproducers are in `evidence/search/prove_defects.sh` and their raw output in
`evidence/captures/proofs.txt`.

### D-11 — hook mapping skipped migration (CLOSED at the pin)

`38-conversational-ai-system/scripts/15-configure-hooks-mappings.sh:192` — `if [[ "$HAS_MAPPING" == "true" ]]; then`,
and the comment at `:197` records the old behaviour verbatim: `every re-run — an upgraded box kept the broken body forever.`
The branch now builds `MERGED_MAPPING` with `s38_merge_mapping_body` (`:199`) and reports one line per
changed key. The repair stage calls the same canonical migration:
`repair/repair-inbound-hooks.py:130` — `res = migrate_mapping_body(cfg_path, m)`.

Reproducer (real library, no stubs): a legacy mapping with a nested `{{contact.id}}` session key and a
template carrying neither the send directive nor the conversation-log read. Before the rebuild this
body survived untouched. Now:

```
hooks mapping ghl-inbound-sms: rewrite body
hooks mapping ghl-inbound-sms: changed key: messageTemplate
hooks mapping ghl-inbound-sms: changed key: sessionKey
...
repair_rc=0
{"id":"ghl-inbound-sms","sessionKey":"{{session_key}}","has_model":false,
 "nested_session_token":false,"template_has_send_directive":true,
 "template_has_conversation_log":true}
```

Searches: `D11.mapping-migrate` rc=0 n=1; `D11.repair-migrate` rc=0 n=2.

### D-12 — model property in the self-test versus the installer (CLOSED at the pin)

The two gates no longer hold private opinions. `24-self-test-hook.sh:157` — `… This used to be a private python snippet`
and `:160` — `… One predicate now, per mapping id (G-03/G-04/G-05).` Both source
`scripts/lib-hook-mapping-contract.sh`, which records the ground truth at `:12` —
`# PBB-017 GROUND TRUTH — \`model\` is NOT required (evidence, not preference):` and at `:32` —
`` (`model` is an OPTIONAL override — see PBB-017 above) ``.

Reproducer, three configs evaluated by the shared predicate itself:

| Config | `MAPCONTRACT` | Verdict |
|---|---|---|
| mapping with no `model` key | `OK` | `GATEVERDICT\|OK` |
| mapping with `"model": ""` | `ERR\|blank-model-override` | `GATEVERDICT\|ERR\|mapping-not-ready` |
| mapping with `"model": "client-chosen-model"` | `OK` | `GATEVERDICT\|OK` |

Searches: `D12.shared-contract-lib` rc=0 n=11; `D12.model-optional` rc=0 n=1.

### D-13 — HTTP 200 admission treated as a completed reply (OPEN in the hook self-test; correct in the contracts layer)

This one is **not** closed, and the two halves must not be conflated.

The contracts layer states the right rule: `direct_fulfillment.py:20` —
`EVIDENCE.  Provider admission is labelled accepted/sent, never "delivered".` A completion receipt
requires a caller-supplied delivery proof matching the pinned content hash
(`record_delivery_proof`, `:632`).

The hook self-test still accepts admission as completion on its default path:

- `24-self-test-hook.sh:334` — `if [ "$CODE" = "200" ] && printf '%s' "$RESP_BODY" | grep -q '"ok"[[:space:]]*:[[:space:]]*true'; then`
  marks the step `ok "hook returned HTTP 200 + {ok:true}"`.
- The only check that can prove a reply actually reached the customer is the GHL `messageId` check at
  `:388`, and that whole block is gated at `:371` — `if [ "${CREATE_TEMP_CONTACT:-0}" = "1" ] && [ -n "$SECRETS_ENV" ]; then`.
  `CREATE_TEMP_CONTACT` defaults to `0`.

So on a default run, `selfTestPassed=true` requires HTTP 200 `{ok:true}`, no 401/429 in the transcript,
and no failed check — but never a delivered message. `qc-self-test.sh` still PASSes, because it asserts
that the messageId check **exists in the text**, not that it ran. That is exactly the
"passing gate is not a passing install" shape, and it is recorded here rather than smoothed over.

Searches: `D13.admission-not-delivery` rc=0 n=1; `D13.selftest-200-only` rc=0 n=1;
`D13.selftest-temp-contact-default` rc=0 n=1.

### D-15 — Skill 44 ownership of the reply-owner contract (OPEN)

The gate exists: `38-conversational-ai-system/launch/qc-launch-conversation-ai.sh:2` —
`# qc-launch-conversation-ai.sh — launch Conversation-AI completion gate.` It is documented in
`launch/README.md:87` and `launch/conversation-runtime-contract.md:4`.

Nothing runs it on a client box. Searching `install.sh`, `update-skills.sh` and `.github/workflows/`
for `qc-launch-conversation-ai` returns nothing (rc=1, n=0), while the control on
`38-conversational-ai-system/launch/` returns 18 matches. Skill 44 names the contract in its
automation template (`D15.skill44-consumer` rc=0 n=4) but does not invoke the gate either.

Ownership is therefore split and unassigned: Skill 38 owns the contract text and the gate; Skill 44
owns the delivery template that references it; no installer, updater or workflow owns *running* it.

Searches: `D15.launch-gate-exists` rc=0 n=1; `D15.launch-gate-uninvoked` rc=1 n=0 (control 18);
`D15.skill44-consumer` rc=0 n=4.

---

## 8. Work in progress at the pin (D3)

The refused revision only said its own worktree was clean and skipped in-flight branches. This section
inventories the dirty work instead. Source: `evidence/captures/d3-work-in-progress.txt`, produced by
`evidence/search/inventory_work_in_progress.sh` at the same session as the pin.

| Dimension | Value |
|---|---|
| Open pull requests | **8** (`PIN.open-pr-count` rc=0, value `8`) |
| Remote heads on `origin` | **1,901** (`PIN.remote-branches` rc=0) |
| Remote heads under `refs/heads/pb/` | **0** (control: 1,901 heads total, so the pattern is live) |
| Local worktrees | **93** at the D3 run recorded in `d3-work-in-progress.txt` (run time in that file). Worktree count is a live local property, not a property of the pinned commit, so this is a timed observation. |
| — attached to a branch | 53 |
| — detached HEAD | 40 |
| Local `pb/*` branches | **60** |

The open pull requests, newest first:

| PR | Head branch | Draft | Updated | Title |
|---|---|---|---|---|
| 2549 | `batch/s75-b3` | no | 2026-10-24T22:10:43Z | S75 batch 3: land accepted-but-unmerged T10 and T24 |
| 2167 | `fix/update-skills-cp-r-preserve-symlinks` | no | 2026-10-16T18:56:17Z | fix(update-skills): cp -R so macOS stops dereferencing a skill symlink and the version stamp can be written |
| 1889 | `fix/qc-falsefail-20261012` | no | 2026-10-13T02:29:41Z | QC false-FAIL fix: personal-workspace skip + pointer-regex + Sunday owner-hold |
| 1702 | `fix/lipsync-process-LSP001` | no | 2026-10-09T00:15:39Z | skill 75: approved lip-sync process (LSP001) |
| 1594 | `fix/kie-guard-bible-import` | yes | 2026-10-07T20:49:02Z | fix(kie): skill 75 style bible uses the shared prompt enforcer |
| 1345 | `fix/rr-escalation-v4` | yes | 2026-09-28T23:37:49Z | fix(rescue): one escalation sender, section stamped into client AGENTS.md |
| 1165 | `fix/pd169-copy-is-the-slides-text` | no | 2026-09-28T15:16:02Z | fix(pd-test-169): copy[] is the slide's TEXT, not a labelled form |
| 1083 | `codex/social-planner-private-links-20260909` | yes | 2026-09-10T00:17:37Z | Add verified private planner sheets and mini-app delivery instructions |

Read this way, the 93 worktrees and 60 local `pb/*` branches are the real in-flight surface; the 8
open PRs are only what has been proposed. None of the 60 `pb/*` branches exists on `origin`, so a
claim derived from `origin/main` alone would miss all of them — which is the D3 defect this section
closes.

---

## 9. What the repository can prove (executed at the pin)

Each line is pasted from a capture written in this session
(`evidence/captures/executed-checks.txt`). Durations are run-dependent; the load-bearing facts are the
counts, verdicts and exit codes.

```
cwd = repo root
$ python3 -B 38-conversational-ai-system/tools/consent_gate.py
OK 15 PASS
rc=0
```

```
cwd = 38-conversational-ai-system/tools
$ python3 -B -m unittest tests.test_pb_contracts tests.test_direct_fulfillment \
      tests.test_bootstrap_engine tests.test_compat_guard -q
----------------------------------------------------------------------
Ran 118 tests in 9.089s

OK
rc=0
```

```
cwd = repo root
$ bash 38-conversational-ai-system/scripts/qc-self-test.sh
  [PASS] 24-self-test-hook.sh exists, parses, POSTs a synthetic flat-23-key inbound with the real Bearer
  [PASS] verifies 200/{ok:true} + no 401/429 + conversation-log read + GHL send messageId + temp-contact cleanup
  [PASS] writes selfTestPassed, fails on error, wired as a blocking readiness gate + documented
RESULT: PASS — the agent self-tests the backend by ground truth before the client ever does.
rc=0
```

```
cwd = repo root
$ python3 -B 35-social-media-planner/scripts/profile_capability.py capabilities \
      --channel facebook --account-type personal
{ "assisted_statuses": ["awaiting-operator","operator-confirmed"], …
  "forbidden_assisted_statuses": ["published-by-system","published"], … }
rc=0
```

```
cwd = repo root
$ python3 -B 38-conversational-ai-system/tools/pb_contracts.py validate --kind approval \
      --file 38-conversational-ai-system/tools/tests/fixtures/pb-contracts/approval/manifest.json
{ "command": "validate", "errors": [], "kind": "approval", "ok": true }
rc=0
```

What these prove: the consent gate's module self-check passes; the contracts layer's own suites pass;
the hook self-test's static standard is satisfied; a personal profile is declared `assisted` and can
never be reported `published-by-system`; and the pinned approval manifest validates through the public
CLI entry point.

What they do **not** prove: any live provider call. No network request, no GHL API call and no client
box was touched. A passing unit test is not a passing install, and a passing static gate is not a
passing run.

---

## 10. Instrument, controls and coverage

### The instrument defect that already bit this task

`\b` and `\|` are inert inside this machine's `git grep -E`. A pattern using them returns exit 1
regardless of content, which manufactures false zeros. Every absence row in this document is derived
with fixed strings (`-F`) or with extended regex using plain `|` and no `\b`.

### Controls

Every claim of absence carries a control with the **same** instrument shape, same flags and same
pathspec, and a pattern proven present (`book_appointment`). If a control returns nothing the harness
marks the row `instrument-failed` and the claim is not recorded as proven. This run: **0
instrument-failed, 0 instrument-error**.

| Absence row | rc | count | Control | Control matches |
|---|---|---|---|---|
| `J4.absent-artifact-name` | 1 | 0 | `-niF book_appointment -- .` | 66 |
| `R4.absent-adapter-names` | 1 | 0 | `-niE book_appointment -- .` | 66 |
| `F2.absent-artifact-name` | 1 | 0 | `-niF book_appointment -- .` | 66 |
| `C4.absent-artifact-name` | 1 | 0 | `-niF book_appointment -- .` | 66 |
| `C5.absent-artifact-name` | 1 | 0 | `-niF book_appointment -- .` | 66 |
| `O1.offer-route-absent` | 1 | 0 | `-niE book_appointment -- 38- 35- 57-` | 55 |
| `O2.absent-artifact-name` | 1 | 0 | `-niF book_appointment -- .` | 66 |
| `C6.runtime-scheduler` | 1 | 0 | `-niF cron -- *cron* *schedule* *04-register*` | 2,625 |
| `D15.launch-gate-uninvoked` | 1 | 0 | `-niF qc-launch-conversation-ai -- …/launch/` | 18 |

`O3.absent-handoff-lifecycle` is deliberately not in this table: at `9488ccbc8` it returns rc=0 with 23
matches, so it is a presence row in the register, not a claim of absence. At the previous pin it was an
absence row (rc=1 n=0) with the same control (66); the identical probe is kept so the flip stays legible.

### Coverage statement

Checked at the pin: repository identity and commit graph; tracked file census; installer and updater
entry points and version stamps; guided-setup identity, intake and discovery stores; the bootstrap
engine; campaign and publishing entries; the full contracts layer (approval manifest, outbound action,
collection state, readiness, action lifecycle, compatibility, reconciliation); hook writer, hook
repair and the shared hook-mapping predicate; self-test and readiness gates; asset registry; direct
fulfillment; tenant identity, collection lock and consent gate; reminder slots; the launch
reply-owner gate; Skill 44's reference to it; open branches, worktrees and pull requests.

Not checked, and named so no negative above is read as broader than it is: any client box; any GitHub
Actions run result (a workflow file existing is not a passing run); live GHL or provider behaviour;
the `999-setup` and `blackceo-command-center` repositories (separate tasks T-02/T-03); branches other
than the pin. Absence claims are claims about **tracked content at `9488ccbc8`**, not about the fleet.

---

## 11. Citations

`evidence/search/check_citations.py` re-checked every citation listed in
`evidence/search/citations.json` against the pinned blob, reading `git show <pin>:<path>` and never
the working tree.

```
pin=9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 citations=80 mismatches=0
```

Full report: `evidence/citations-report.txt`.

**Scope of that 80 — what is checked and what is not.** The previous wording here said "every
`file:line` quoted in this document was re-checked". That was an overstatement of process strength,
raised as H1 by the independent verifier PBB-280 and repaired by PBB-351: it is narrowed here to
what the manifest actually certifies, and the gap is named instead of implied.

This document carries **102 line references**, counted as tokens of the form `path:NN` plus bare
`:NN` tokens: 51 written with a path token, 51 bare. The manifest is not 102 entries, and the
difference is not hidden:

- **51 bare `:NN` references** carry no path of their own. No script can resolve them; a reader has
  to take the file from the surrounding prose. **They are not machine-checked.**
- **No handoff citation is in the manifest.** `citations.json` has **0 of 80** entries under
  `shared-utils/handoff/`. That leaves uncovered the ten bare `handoff.py` references in section 6 —
  `HandoffStore.create`, `.accept`, `.escalate`, `.backup_accept`, `.release` and `.get`, the
  backup-owner guard, the stored `backup_owner_id`, and the module's `__main__` entry point and
  `_self_check()` call — and the one path-anchored reference in that section, the O3 test in
  `shared-utils/handoff/tests/test_handoff.py` (`test_create_requires_a_distinct_backup_owner`).
- **Those 11 O3 citations were checked by hand**, line by line, against the pinned blob, and every
  one is true. That check is a human reading of `git show`, not a reproducible script run, so the
  manifest does not certify it.

What the manifest certifies, exactly: the 80 citations it lists resolve at the pin with 0
mismatches, reproducible by the command above. What it does not certify: the remaining line
references in this document. Any finding that rests on a bare reference or a handoff reference rests
on the hand check recorded here, not on the manifest.

---

## 12. Deliverables and how to reproduce

All on branch `pb/PBB-236/t01-inventory-rebase`, created from the pin (the PBB-206 revision lived on
`pb/PBB-206/t01-inventory`; this re-stamp carries the same evidence files forward).

| Path | What it is |
|---|---|
| `evidence/t01-interface-inventory.md` | This document. |
| `evidence/current-onboarding-evidence.json` | Machine-readable artifact: pin, fetch time, every search command, scope, exit code, count, verdict and control. |
| `evidence/citations-report.txt` | Per-citation verification result. |
| `evidence/search/searches.json` | The search manifest the artifact is generated from. |
| `evidence/search/citations.json` | The citation manifest. |
| `evidence/search/run_searches.py` | Runs every search at the pin; writes the artifact and one capture per search. |
| `evidence/search/check_citations.py` | Verifies every citation against the pinned blob. |
| `evidence/search/prove_defects.sh` | D-11 / D-12 / D-13 / D-15 reproducers against the pinned code. |
| `evidence/search/inventory_work_in_progress.sh` | D3: open PRs, remote heads, worktrees. |
| `evidence/search/render_inventory_tables.py` | Renders the search register below from the artifact. |
| `evidence/captures/*.txt` | One raw capture per search, plus `proofs.txt`, `executed-checks.txt`, `d3-work-in-progress.txt`. |

Reproduce from the repository root:

```
python3 -I evidence/search/run_searches.py --root .
python3 -I evidence/search/check_citations.py --root .
bash evidence/search/prove_defects.sh "$PWD" /path/to/scratch
bash evidence/search/inventory_work_in_progress.sh "$PWD"
python3 -I evidence/search/render_inventory_tables.py --root .
```

`run_searches.py` exits non-zero unless `HEAD` is the pin or descends from it, or if any control fails.

---

## 13. CHANGELOG and skill-version

No skill behaviour changes in this unit, so no `CHANGELOG.md` entry and no `skill-version.txt` bump are
included. This unit adds evidence documents and read-only search scripts only; it does not touch
installer, updater, skill, protocol or script behaviour anywhere in the repository.

The pin's own versions for reference: repo `version` = `v27.1.65`, Skill 38 `skill-version.txt` =
`v2.0.33`. Neither is changed by this branch.

---

## Search register

Generated from `evidence/current-onboarding-evidence.json`. Every row is a command that ran in this
session against the pin. `rc` is git grep's own exit status (0 = match, 1 = no match, 2 = error);
`count` is matching output lines; `control` is the same-instrument same-scope known-present run.

<!-- SEARCH-REGISTER:START -->

| # | Search id | Interface | Command | Scope | rc | count | verdict | control |
|---|---|---|---|---|---|---|---|---|
| 1 | `PIN.pin-resolves` | PIN | `git rev-parse --verify 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865^{commit}` | object store | 0 | 1 | present | - |
| 2 | `PIN.pin-is-commit` | PIN | `git cat-file -t 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865` | object store | 0 | 1 | present | - |
| 3 | `PIN.remote-main` | PIN | `git ls-remote origin refs/heads/main` | remote origin | 0 | 1 | present | - |
| 4 | `PIN.commits-ahead-of-bccc4050f` | PIN | `git rev-list --count bccc4050f8ed98b2d9b55cfc087c27c924d62b03..9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865` | commit graph | 0 | 1 | present | - |
| 5 | `PIN.merges-ahead-of-bccc4050f` | PIN | `git rev-list --count --merges bccc4050f8ed98b2d9b55cfc087c27c924d62b03..9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865` | commit graph | 0 | 1 | present | - |
| 6 | `PIN.commits-ahead-of-f0a9c80e` | PIN | `git rev-list --count f0a9c80e076e5a6cf8e293acdcaad9f2f72ea82b..9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865` | commit graph | 0 | 1 | present | - |
| 7 | `PIN.merges-ahead-of-f0a9c80e` | PIN | `git rev-list --count --merges f0a9c80e076e5a6cf8e293acdcaad9f2f72ea82b..9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865` | commit graph | 0 | 1 | present | - |
| 8 | `PIN.tracked-files` | PIN | `git ls-tree -r --name-only 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865` | all tracked paths | 0 | 13672 | present | - |
| 9 | `PIN.remote-branches` | PIN | `git ls-remote --heads origin` | remote origin heads | 0 | 1901 | present | - |
| 10 | `PIN.open-prs` | PIN | `gh pr list --repo trevorotts1/openclaw-onboarding --state open --limit 200 --json number,headRefName,isDraft,title,updatedAt` | GitHub pull requests | 0 | 1 | present | - |
| 11 | `PIN.worktrees` | PIN | `git worktree list --porcelain` | local clone | 0 | 279 | present | - |
| 12 | `PIN.worktree-count` | PIN | `git worktree list` | local clone | 0 | 93 | present | - |
| 13 | `PIN.open-pr-count` | PIN | `gh pr list --repo trevorotts1/openclaw-onboarding --state open --limit 200 --json number --jq length` | GitHub pull requests | 0 | 1 | present | - |
| 14 | `G1.trigger-count` | G1 | `git grep -nF 8 different ways to do it 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- ONBOARDING-TRIGGERS.md` | ONBOARDING-TRIGGERS.md | 0 | 1 | present | 78 matches |
| 15 | `G1.install-entry` | G1 | `git grep -nF Run via: curl -fSL 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- install.sh` | install.sh | 0 | 1 | present | 13 matches |
| 16 | `G2.identity-def` | G2 | `git grep -nF collect_onboarding_identity() { 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- install.sh` | install.sh | 0 | 1 | present | - |
| 17 | `G2.identity-exit8` | G2 | `git grep -nF collect_onboarding_identity \|\| exit 8 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- install.sh` | install.sh | 0 | 1 | present | - |
| 18 | `G2.identity-questions` | G2 | `git grep -nF QUESTIONS = { 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- scripts/onboarding-identity.py` | scripts/onboarding-identity.py | 0 | 1 | present | - |
| 19 | `G3.intake-engine` | G3 | `git grep -nF def next_question 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- shared-utils/client_intake/engine.py` | shared-utils/client_intake/engine.py | 0 | 1 | present | - |
| 20 | `G4.acquisition-brief` | G4 | `git grep -nF class AcquisitionBrief 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 38-conversational-ai-system/tools/acquisition_brief.py` | 38-conversational-ai-system/tools/acquisition_brief.py | 0 | 1 | present | - |
| 21 | `G5.bootstrap-file` | G5 | `git ls-tree -r --name-only 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 38-conversational-ai-system/tools/bootstrap_engine.py` | 38-conversational-ai-system/tools | 0 | 1 | present | - |
| 22 | `G5.bootstrap-name` | G5 | `git grep -niF client-bootstrap-engine 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- .` | all tracked paths | 0 | 2 | present | - |
| 23 | `G5.bootstrap-plan` | G5 | `git grep -nF def plan 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 38-conversational-ai-system/tools/bootstrap_engine.py` | bootstrap_engine.py | 0 | 1 | present | - |
| 24 | `G5.bootstrap-run` | G5 | `git grep -nF def run 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 38-conversational-ai-system/tools/bootstrap_engine.py` | bootstrap_engine.py | 0 | 1 | present | - |
| 25 | `J1.publishing-cycle` | J1 | `git grep -nF run-publishing-cycle.sh 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 35-social-media-planner/scripts/run-publishing-cycle.sh` | run-publishing-cycle.sh | 0 | 4 | present | - |
| 26 | `J2.weekly-batch` | J2 | `git grep -nF Cron-driven weekly batch 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 35-social-media-planner/scripts/weekly-batch.sh` | weekly-batch.sh | 0 | 1 | present | - |
| 27 | `J3.campaign-mode` | J3 | `git grep -nF campaign 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 57-social-media-in-a-box/modes.md` | 57-social-media-in-a-box/modes.md | 0 | 2 | present | - |
| 28 | `J4.approval-schema` | J4 | `git ls-tree -r --name-only 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 38-conversational-ai-system/schemas/approval-manifest.schema.json` | 38-conversational-ai-system/schemas | 0 | 1 | present | - |
| 29 | `J4.approval-title` | J4 | `git grep -nF Revisioned monthly approval manifest 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 38-conversational-ai-system/schemas/approval-manifest.schema.json` | approval-manifest.schema.json | 0 | 1 | present | - |
| 30 | `J4.approval-semantic` | J4 | `git grep -nF def semantic_approval 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 38-conversational-ai-system/tools/pb_contracts.py` | pb_contracts.py | 0 | 1 | present | - |
| 31 | `J4.approval-binding` | J4 | `git grep -nF def approval_errors 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 38-conversational-ai-system/tools/pb_contracts.py` | pb_contracts.py | 0 | 1 | present | - |
| 32 | `J4.absent-artifact-name` | J4 | `git grep -niF monthly-approval-contract 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- .` | all tracked paths | 1 | 0 | absent | 66 matches |
| 33 | `J5.promised-item` | J5 | `git grep -nF class PromisedItem 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 38-conversational-ai-system/tools/direct_fulfillment.py` | direct_fulfillment.py | 0 | 1 | present | - |
| 34 | `J5.keyword-bound` | J5 | `git grep -nF keyword 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 38-conversational-ai-system/tools/pb_contracts.py` | pb_contracts.py | 0 | 2 | present | - |
| 35 | `J5.immutable-item` | J5 | `git grep -nF IMMUTABLE. 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 38-conversational-ai-system/tools/direct_fulfillment.py` | direct_fulfillment.py | 0 | 1 | present | - |
| 36 | `J5.name-probe` | J5 | `git grep -niE stable keyword\|promised-item\|promised_item\|keyword mapping\|original promise 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- *.py *.sh` | *.py and *.sh | 0 | 6 | present | - |
| 37 | `R1.capability-declaration` | R1 | `git grep -nF personal_profile_rule 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 35-social-media-planner/config/profile-capabilities.json` | profile-capabilities.json | 0 | 1 | present | - |
| 38 | `R2.comment-surface` | R2 | `git grep -nF CHANNEL_COMMENT_SURFACE 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 35-social-media-planner/scripts/comment_reader.py` | comment_reader.py | 0 | 4 | present | - |
| 39 | `R3.private-opener` | R3 | `git grep -nF COMMENT_PRIVATE_OPENER 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- .` | all tracked paths | 0 | 4 | present | - |
| 40 | `R3.hook-writer` | R3 | `git grep -nF s38_canonical_mapping 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 38-conversational-ai-system/scripts/15-configure-hooks-mappings.sh` | 15-configure-hooks-mappings.sh | 0 | 2 | present | - |
| 41 | `R4.absent-adapter-names` | R4 | `git grep -niE instagram-route-adapter\|page-comment-adapter\|messenger-route-adapter\|private-opener-adapter 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- .` | all tracked paths | 1 | 0 | absent | 66 matches |
| 42 | `R4.adapter-file-census` | R4 | `git ls-tree -r --name-only 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865` | all tracked paths, case-insensitive substring on the path | 0 | 150 | present | - |
| 43 | `F1.asset-registry` | F1 | `git grep -nF def record_present 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 38-conversational-ai-system/tools/asset_registry.py` | asset_registry.py | 0 | 1 | present | - |
| 44 | `F2.fulfillment-file` | F2 | `git ls-tree -r --name-only 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 38-conversational-ai-system/tools/direct_fulfillment.py` | 38-conversational-ai-system/tools | 0 | 1 | present | - |
| 45 | `F2.fulfill-entry` | F2 | `git grep -nF def fulfill( 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 38-conversational-ai-system/tools/direct_fulfillment.py` | direct_fulfillment.py | 0 | 1 | present | - |
| 46 | `F2.receipt` | F2 | `git grep -nF def record_delivery_proof 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 38-conversational-ai-system/tools/direct_fulfillment.py` | direct_fulfillment.py | 0 | 1 | present | - |
| 47 | `F2.absent-artifact-name` | F2 | `git grep -niF direct-original-fulfillment 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- .` | all tracked paths | 1 | 0 | absent | 66 matches |
| 48 | `C1.channel-identifier-types` | C1 | `git grep -nF CHANNEL_IDENTIFIER_TYPES 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 38-conversational-ai-system/tools/tenant_identity.py` | tenant_identity.py | 0 | 2 | present | - |
| 49 | `C1.reminder-column` | C1 | `git grep -nF reminder_total 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 38-conversational-ai-system/tools/tenant_identity.py` | tenant_identity.py | 0 | 6 | present | - |
| 50 | `C2.capture-store` | C2 | `git grep -nF class CaptureStore 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 38-conversational-ai-system/tools/collection_lock.py` | collection_lock.py | 0 | 1 | present | - |
| 51 | `C3.consent-offer-scope` | C3 | `git grep -nF SCOPE_OFFER 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 38-conversational-ai-system/tools/consent_gate.py` | consent_gate.py | 0 | 4 | present | - |
| 52 | `C3.human-fence` | C3 | `git grep -nF def human_takeover 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 38-conversational-ai-system/tools/consent_gate.py` | consent_gate.py | 0 | 1 | present | - |
| 53 | `C4.capture-budget` | C4 | `git grep -nF capture_budget 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 38-conversational-ai-system/schemas/collection-state.schema.json` | collection-state.schema.json | 0 | 2 | present | - |
| 54 | `C4.sms-email-ask` | C4 | `git grep -nF max_sms_email_asks 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- .` | all tracked paths | 0 | 15 | present | - |
| 55 | `C4.absent-artifact-name` | C4 | `git grep -niF progressive-capture-candidate 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- .` | all tracked paths | 1 | 0 | absent | 66 matches |
| 56 | `C5.reminder-slots` | C5 | `git grep -nF reminder_slots 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- .` | all tracked paths | 0 | 20 | present | - |
| 57 | `C5.slot-order-rule` | C5 | `git grep -nF due_at must increase across slots 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 38-conversational-ai-system/tools/pb_contracts.py` | pb_contracts.py | 0 | 1 | present | - |
| 58 | `C5.absent-artifact-name` | C5 | `git grep -niF reminder-state-machine 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- .` | all tracked paths | 1 | 0 | absent | 66 matches |
| 59 | `C6.followup-protocol` | C6 | `git ls-tree -r --name-only 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 38-conversational-ai-system/protocols/intelligent-followup-protocol.md` | 38-conversational-ai-system/protocols | 0 | 1 | present | - |
| 60 | `C6.protocol-readers` | C6 | `git grep -niE intelligent-followup-protocol\|intelligent_followup 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- *.py *.sh` | *.py and *.sh | 0 | 5 | present | 34 matches |
| 61 | `C6.runtime-scheduler` | C6 | `git grep -niF intelligent-followup-protocol 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- *cron* *schedule* *04-register*` | paths whose name contains cron, schedule or 04-register | 1 | 0 | absent | 2625 matches |
| 62 | `O1.offer-scope` | O1 | `git grep -nF SCOPE_OFFER 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 38-conversational-ai-system/tools` | 38-conversational-ai-system/tools | 0 | 6 | present | - |
| 63 | `O1.offer-route-absent` | O1 | `git grep -niE select_offer\|offer_route\|pick_offer\|choose_offer\|offer_select 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 38-conversational-ai-system 35-social-media-planner 57-social-media-in-a-box` | 38- / 35- / 57- skill directories | 1 | 0 | absent | 55 matches |
| 64 | `O2.booking-protocol` | O2 | `git ls-tree -r --name-only 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 38-conversational-ai-system/protocols/smart-booking-protocol.md` | 38-conversational-ai-system/protocols | 0 | 1 | present | - |
| 65 | `O2.absent-artifact-name` | O2 | `git grep -niF booking-followthrough-adapter 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- .` | all tracked paths | 1 | 0 | absent | 66 matches |
| 66 | `O3.human-fence` | O3 | `git grep -nF def human_release 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 38-conversational-ai-system/tools/consent_gate.py` | consent_gate.py | 0 | 1 | present | - |
| 67 | `O3.lifecycle-ladder` | O3 | `git grep -nF LIFECYCLE_LADDER 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 38-conversational-ai-system/tools/pb_contracts.py` | pb_contracts.py | 0 | 1 | present | - |
| 68 | `O3.absent-handoff-lifecycle` | O3 | `git grep -niE handoff_accept\|handoff_due\|handoff-lifecycle\|backup_owner\|backup-owner 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- .` | all tracked paths | 0 | 23 | present | 66 matches |
| 69 | `D11.mapping-migrate` | D-11 | `git grep -nF s38_merge_mapping_body 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 38-conversational-ai-system/scripts/15-configure-hooks-mappings.sh` | 15-configure-hooks-mappings.sh | 0 | 1 | present | - |
| 70 | `D11.repair-migrate` | D-11 | `git grep -nF migrate_mapping_body( 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 38-conversational-ai-system/scripts/repair/repair-inbound-hooks.py` | repair-inbound-hooks.py | 0 | 2 | present | - |
| 71 | `D12.shared-contract-lib` | D-12 | `git grep -nF lib-hook-mapping-contract.sh 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 38-conversational-ai-system/scripts` | 38-conversational-ai-system/scripts | 0 | 11 | present | - |
| 72 | `D12.model-optional` | D-12 | `git grep -nF model` is an OPTIONAL override 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 38-conversational-ai-system/scripts/lib-hook-mapping-contract.sh` | lib-hook-mapping-contract.sh | 0 | 1 | present | - |
| 73 | `D13.admission-not-delivery` | D-13 | `git grep -nF never "delivered" 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 38-conversational-ai-system/tools/direct_fulfillment.py` | direct_fulfillment.py | 0 | 1 | present | - |
| 74 | `D13.selftest-200-only` | D-13 | `git grep -nF hook returned HTTP 200 + {ok:true} 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 38-conversational-ai-system/scripts/24-self-test-hook.sh` | 24-self-test-hook.sh | 0 | 1 | present | - |
| 75 | `D13.selftest-temp-contact-default` | D-13 | `git grep -nF CREATE_TEMP_CONTACT:-0 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 38-conversational-ai-system/scripts/24-self-test-hook.sh` | 24-self-test-hook.sh | 0 | 1 | present | - |
| 76 | `D15.launch-gate-uninvoked` | D-15 | `git grep -nF qc-launch-conversation-ai 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- install.sh update-skills.sh .github/workflows/` | install.sh, update-skills.sh, .github/workflows/ | 1 | 0 | absent | 18 matches |
| 77 | `D15.launch-gate-exists` | D-15 | `git ls-tree -r --name-only 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 38-conversational-ai-system/launch/qc-launch-conversation-ai.sh` | 38-conversational-ai-system/launch | 0 | 1 | present | - |
| 78 | `D15.skill44-consumer` | D-15 | `git grep -nF customer-replied-conversation-ai 9488ccbc8cd57a90dec6bd30a15ba4eba2cc4865 -- 44-convert-and-flow-operator` | 44-convert-and-flow-operator | 0 | 4 | present | - |

<!-- SEARCH-REGISTER:END -->
