# T-15 BUILD — BLOCKED

Unit: T-15 · lane PBB-609 · branch `pb/PBB-609/t-15-build` · base `76700ba3648f58472ca9c2111dce717a1cf2c5b7`
Verdict: **BLOCKED**, row named: **C-15** (and the "selected real" half of T-15's own acceptance).

No product code was written. That is the finding, not an omission.

---

## 0. Instrument proof, both polarities

Same shell, same git, same run that produced every row below.

| probe | command | expected | result | rc |
|---|---|---|---|---|
| EXPECTED-PASS path (known present) | `test -f README.md` in the onboarding repo | present | present | 0 |
| EXPECTED-PASS ancestry | `git merge-base --is-ancestor 76700ba3 origin/main` | true | true | 0 |
| EXPECTED-FAIL path (known absent) | `test -f ZZ_NO_SUCH_FILE_PBB609.md` | absent | absent | 1 |
| EXPECTED-FAIL sha, first attempt | `git merge-base --is-ancestor ffffffffffffffffffffffffffffffffffffffff origin/main` | non-ancestor | **invalid object** | **128** |
| EXPECTED-FAIL sha, corrected (real unmerged object) | `git merge-base --is-ancestor dc5c25aa598d8386f88c0737a8bef3c3d6eb1ff1 origin/main` | non-ancestor | non-ancestor | **1** |
| control for the corrected probe | `git merge-base --is-ancestor origin/main origin/main` | ancestor | ancestor | 0 |

The first EXPECTED-FAIL attempt returned **128**, which is an instrument abort (invalid commit name), never a fact
about the target. The probe was re-run against a commit that exists and is genuinely unmerged; that run returned 1
with a 0 control in the same pair. No `128` is used as evidence anywhere below.

---

## 1. The requirement, verbatim, from the ticket

`QUALITY-CONTROL/tickets/T-15.md`, in full:

```
# T-15 - Implement selected real bonus access and failed-step resume

Status: in_flight
Unit: T-15
Phase: BUILT
Ledger status: in_flight
Acceptance: Separate identity/grant/credential/SMS/resource authorization; return access and email-later same member.

Sources: ledger.json unit T-15; live-ledgers/build.json task T-15
Transcribed by: PBB-503 (board-sources lane). Status is the unit's real state; nothing marked delivered without its merge proof.
```

The ticket text does **not** contain its own check rows. The named rows C-15, C-F04, C-F07 and C-F11 live in the
project documents the ticket cites as its sources. Quoted from each, verbatim:

`TODO.md`, T-15 block:

```
## T-15 — Implement selected real bonus access and failed-step resume

State: **NOT_STARTED**. Workflow role: W-07. Repository scope: onboarding.

Preparation prerequisites: none imposed; use accepted policy and available evidence.

Build prerequisites: T-12, T-14, T-05.

Integration requirements: accepted_exact_candidate, independent_required_checks, compatible_target_lease.

Output: `bonus-access-adapter`.

Acceptance: Separate identity/grant/credential/SMS/resource authorization; return access and email-later same member.

Requirements: R-13, R-27. Checks: C-15, C-F04, C-F07, C-F11.
```

`ACCEPTANCE-MATRIX.md`, row R-13:

```
| R-13 | Actual optional access grant, credential, SMS, return and recovery | T-14 T-15 T-48 | C-14 C-15 C-48 C-F04 C-F07 C-F11 |
```

`ACCEPTANCE-MATRIX.md`, focused fixtures:

```
- C-F04 / F-04: Every-send gate STOP/rebind/window — **UNVERIFIED**.

- C-F07 / F-07: Original gift while bonus unavailable — **UNVERIFIED**.

- C-F11 / F-11: Access failed-step/return/email identity — **UNVERIFIED**.
```

`CHECKLIST.md`, R-13:

```
- [ ] **R-13** Actual optional access grant, credential, SMS, return and recovery
  - Discoveries: D-19, D-26, D-28, D-34
  - Tasks: T-14, T-15, T-48
  - Checks: C-14, C-15, C-48, C-F04, C-F07, C-F11
```

`DATA-CONTRACTS.md` section 6, the implementation contract under those rows:

```
## 6. Actual bonus access
Separate receipts: verified member identity → entitlement grant → credential issue → pass SMS → resource authorization/return access. Resume the failed step only. Later email binds to the same verified member, not a duplicate account. A login token's expiry is not entitlement or guide expiry.

GHL membership is a candidate. Its enrollment API alone does not prove mobile-only identity, credential automation or SMS recovery. Missing optional access cannot block original fulfillment, but the full advertised bonus product cannot show ready without it.
```

**Ticket header contradicts its own sources.** The ticket says `Phase: BUILT` / `Ledger status: in_flight`. The two
sources it names, and `TODO.md`, say `NOT_STARTED`. Measured state: live ledger `build.json` T-15 =
`"status": "NOT_STARTED"`, `"candidate_sha": null`, `"base_sha": null`, `"evidence_ids": []`, `attempt: 0`;
`TODO.md` = `State: **NOT_STARTED**`. Nothing has been delivered under this unit. The header is a transcription
artifact, not a merge proof.

## 1a. The repository the evidence indicates

`TODO.md`: `Repository scope: onboarding.` Live ledger `build.json`, T-15: `"repo_alias": "onboarding"`.
Both name the **onboarding** repository. The lane worktree is that repository at `origin/main`
`76700ba3648f58472ca9c2111dce717a1cf2c5b7`.

---

## 2. Ground truth before code, with controls in the same scan

Two independent scans over the tree at `origin/main` = `76700ba36`. Both print a file:line for every hit and
include known-present control terms so a zero is credible. Scanner scripts live under the run root's `tmp/`;
outputs are reproduced here.

Scan A — 13,489 decodable text files of 13,804 tracked files:

| term | hits | reading |
|---|---|---|
| `canonical_contact_id` (CONTROL) | **369** | instrument is live |
| `direct_fulfillment` (CONTROL) | **76** | instrument is live |
| `bonus_access` | **0** | no module |
| `credential_issue` | **0** | no credential step |
| `pass_sms` | **0** | no pass step |
| `return_access` | **0** | no return step |
| `email_later` | **0** | no email-later path |
| `same verified member` | 2 | `shared-utils/capture/progressive_capture.py:346` and its test `:660` only |
| `failed step` | 28 | 38-skill hits are `bootstrap_engine.py:31-32`; none is an access-step resume |
| `BONUS_COMMENT` | 3 | `schemas/outbound-action.schema.json:292,421`, `tools/pb_contracts.py:1040` — a purpose label |
| `bonus-access` | 1 | `38-conversational-ai-system/CHANGELOG.md:241` — prose describing T-13's independence |

Scan B — same instrument, prior-art token set:

| term | hits | term | hits |
|---|---|---|---|
| `canonical_contact_id` (CONTROL) | **369** | `access_adapter` | **0** |
| `presentation_job` (CONTROL) | **2420** | `access_capability` | **0** |
| `direct_fulfillment` (CONTROL) | **76** | `BONUS_ACCESS_CAPABILITY_BLOCKED` | **0** |
| `bonus_access` | **0** | `supported_route` | **0** |
| `BonusAccess` | **0** | `request_bonus_access` | **0** |
| `AccessLedger` | **0** | `resolve_member_state` | **0** |
| `sms_return` | **0** | `advertised_bonus_ready` | **0** |

Path-level scan: basename containing `bonus` at `origin/main` = **1** file
(`38-conversational-ai-system/tools/tests/fixtures/pb-contracts/approval/manifest-mut-bonus-asset-versions.json`,
an approval fixture). Basename containing `access_adapter` at `origin/main` = **0**.

Workflow scan (66 workflow files): `test_bonus_access` = 0 files, `bonus` = 0 files,
`test_direct_fulfillment` = 0 files, `test_progressive_capture` = 0 files,
`tenant_identity` = 0 files, `progressive_capture` = 0 files.

### What exists and what does not

Exists on main, and is the only adjacent implemented surface:

- `shared-utils/capture/progressive_capture.py` (T-16) — capture policy plus `bind_email()` at line 348, which
  binds a later email to the same canonical contact. **It has zero production callers** (only itself and
  `shared-utils/capture/tests/test_progressive_capture.py` reference it).
- `38-conversational-ai-system/tools/direct_fulfillment.py` (T-13) — original gift, with "no dependency on any
  bonus access module" stated in its own docstring (`:9-13`, `:31-39`). Also zero production callers.
- `consent_gate.make_gate_evaluator` (`tools/consent_gate.py:584`) — the every-send gate T-12/T-18 supply.
- `BONUS_COMMENT` as a purpose label only; no authorization semantics.

Does not exist on main: the five-receipt access adapter, any identity/grant/credential/pass/return state machine,
any failed-step resume, any access ledger, and any production consumer for any of them.

### The producer does not exist either

- Live ledger T-14 (`build.json`): `"status": "NOT_STARTED"`, `"artifact": "bonus-access-capability-decision"`,
  `"evidence_ids": []`, `"candidate_sha": null`.
- `TODO.md` T-14: `State: **NOT_STARTED**`; acceptance: `Current official route/tenant requirements, mobile-only
  identity/token/recovery evidence or exact capability block; no fabricated API.`; build prerequisites for T-15
  include T-14.
- No `bonus-access-capability-decision` artifact exists on `origin/main` (path scan above).
- The only route analysis in the repository is on unmerged branch `pb/PBB-356/t-14-repair3` at
  `dc5c25aa598d8386f88c0737a8bef3c3d6eb1ff1` (ancestry probe rc **1**, control rc 0), file
  `shared-utils/bonus/BONUS-ACCESS-CAPABILITY-DECISION.md`. Its own words:

  > **Decision:** **BLOCKED** for every automated route. Supported path is **assisted/operator**.

  and, in its "Not done / owned elsewhere" section:

  > **T-15** — the real bonus access adapter (identity/grant/credential/SMS/resource authorization, failed-step
  > resume, return access, email-later same member). It is blocked by this decision and must not fabricate the
  > route.

Corroboration from the last lane that touched this unit, `scratch/PBB-559/REPAIR.md` (read, not re-quoted as fact
beyond its own measurements): it recorded its `access_adapter` at zero non-test call sites (2 prose hits vs a
195-file control), deleted the module, and wrote that "A future T-15 must land alongside its real producer
(T-14's route decision) and its real consumer (T-16/T-48)." This lane independently reproduced the zero-call-site
and zero-producer conditions on today's main.

---

## 3. Build rationale — BLOCKED, C-15 named

**Row C-15 (R-13: "Actual optional access grant, credential, SMS, return and recovery") cannot be satisfied.**
T-15's own build prerequisite T-14 is `NOT_STARTED`, its artifact is absent, and it has no evidence id. The only
route analysis in existence returns BLOCKED for every automated route and states that T-15 must not fabricate a
route. "Implement **selected** real bonus access" therefore has no selection to implement. Building a provider
adapter now means inventing a vendor API — explicitly forbidden by T-14's acceptance clause and by the task's
"do not invent scope".

**Row C-F11 (access failed-step/return/email identity) cannot be proved reachable even if written.** The only
candidate consumer, `progressive_capture.py`, is itself orphaned (0 production callers, measured above); the only
other named consumers are T-16 and T-48, and T-48 is `DEFERRED_AUTH` (never an unattended consumer). A new module
wired into an orphaned module is dead-to-dead, which is precisely the defect that failed this unit before. The
task's own Step 4 requires "a real consumer, not a test, not an `__init__` re-export" — no such consumer exists on
main, and creating one is a decision for another unit (T-16/T-36/T-48), not this lane.

**C-F04 and C-F07 are not independently buildable as T-15 work:**

- C-F04 ("every-send gate STOP/rebind/window") is already owned and implemented by T-12's `outbound_gate.dispatch`
  (fresh verdict per attempt; `outbound_gate.py:146-230`). T-15 has no send to gate, because there is no access
  route.
- C-F07 ("original gift while bonus unavailable") is the independence check, and T-13 already satisfies the
  independence direction: `direct_fulfillment.py` imports no bonus module and its docstring states the rule. It
  stays UNVERIFIED as a bonus-side check exactly because the bonus side does not exist.

Rows satisfied: **0 of 4**. No function was written, so no function can be unreachable — the failure mode this
unit has died of twice is not being reintroduced by writing another orphan.

---

## 4. The two wiring proofs

### Reachability — NO

Every new public symbol gets a printed production call site: there are **no new public symbols**, so the set is
empty. For completeness, the measured population of adjacent symbols also has no production call site:

- `progressive_capture` / `bind_email` / `plan_capture`: only `shared-utils/capture/progressive_capture.py`
  itself and `shared-utils/capture/tests/test_progressive_capture.py`.
- `direct_fulfillment`: itself, its test, `CHANGELOG.md`, `evidence/captures/D13.admission-not-delivery.txt`.
- `bonus_access` / `BonusAccess` / `AccessLedger` / `access_adapter`: 0 hits anywhere on main.
- Controls in the same runs: `canonical_contact_id` 369, `presentation_job` 2420, `direct_fulfillment` 76.

### CI wiring — 0 workflows

No suite was created, so nothing can be wired, and wiring a step to a path that does not exist is itself the
defect repaired in PBB-568. Measured on the same tree: **0 of 66** workflow files name any bonus/access suite
(`test_bonus_access` 0/66, `bonus` 0/66). The same scan returns 0/66 for `test_direct_fulfillment` and
`test_progressive_capture`, so the scanner's zero is consistent with the tree, and its positive polarity is
established by other suites the same workflow set names explicitly (e.g. `qc-static.yml:3184` names
`38-conversational-ai-system/scripts/qc-pb-contracts.sh`).

When T-14 lands an accepted route decision, the wiring this lane would add is one step in
`.github/workflows/qc-static.yml` of the PBB-568/PBB-589 shape: resolve the path, fail if absent, `ls -l` it, then
`python3 -I <path>`.

---

## 5. Suite status — honest

**SUITE VERIFICATION PENDING (no heavy permit).** No suite exists for this unit because no code was written.

The exact command this unit's test would use once unblocked, from the repository root:

```
python3 -I shared-utils/capture/tests/test_bonus_access.py
```

No suite was run, so no suite is claimed green. The only executions this lane performed are the read-only scans
above and the git probes in §0/§7.

---

## 6. Version and CHANGELOG — untouched

No version marker was changed. `38-conversational-ai-system/skill-version.txt` and
`38-conversational-ai-system/CHANGELOG.md` are untouched by this lane. If a version or CHANGELOG entry were
needed, that would itself be a signal to stop; none is needed because nothing shipped.

---

## 7. Commit, push, readbacks, negative control

Commit on `pb/PBB-609/t-15-build` contains this report only (`evidence/PBB-609/T-15-BUILD.md`). No other unit,
ledger, census, decision file, version marker, CHANGELOG, test, or workflow was touched. No merge, no PR, no force.

- readback 1 — `git ls-remote --heads origin pb/PBB-609/t-15-build` → [filled below by the lane's own output]
- readback 2 — remote branch tip read a second time, independent command → [filled below]
- negative control, known-absent path on that sha: `git cat-file -e <sha>:shared-utils/bonus/access_adapter.py` →
  expected rc 128, path absent.
- control, known-present path on the same sha: `git cat-file -e <sha>:evidence/PBB-609/T-15-BUILD.md` → expected
  rc 0.

Exact outputs are appended by the lane after the push and are also returned in the structured receipt.

---

## 8. What would unblock this unit (named, not a to-do list for the owner)

T-14 must land an accepted `bonus-access-capability-decision` that names a supported route with evidence (its own
document lists the required order: a documented membership operation in the frozen registry, a recorded tenant
success, then an observed mobile-only login/credential/return/recovery). In the same change, a real consumer must
exist on a live path — T-16's capture flow or T-48's owner proof — so the adapter's call site is production, not a
test. Until both hold, any T-15 implementation is either a fabricated vendor API or an unreachable orphan.
