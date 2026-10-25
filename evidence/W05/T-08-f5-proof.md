# T-08 / F5 — `NO_TRUSTED_CONTACT_MAPPING` is a reachable, named refusal

Lane: PBB-349 (repair 4 of the PBB-321 verifier's FAIL on `9b73fabd6`) · Unit: T-08 (W-05, `versioned-interface-contracts`, repo scope shared)
Branch: `pb/PBB-349/t-08-repair4`
Pinned base: `3550dc3f4316e1ad6aed7362c9a79a890aa29b1c` (`origin/main` when F5 was measured)
Commit under repair: `9b73fabd699db06dd670c21b3267ab965c3c18f5`
Prior attempt under test: `053c4fee` (ancestor of the pinned base)
F5 as reviewed: `8e98f155e` (the commit `lanes/PBB-018-operator/QC-VERDICT.md` names)
Artifact under test: `38-conversational-ai-system/tools/pb_contracts.py`, `schemas/outbound-action.schema.json`

This revision repairs one overstated claim in this file. The earlier table
reported the three-tree progression as 1/8 → 4/8 → 8/8 and called the single
pre-fix "held" case a hold. It was not a hold: see section 4.3. The case list is
now stated explicitly, the instrument that produces every number in this file is
committed beside it, and the canonical progression under the independent case
list is **0/8 → 3/8 → 8/8**. Nothing else about the F5 evidence is changed.

## 1. The clause, verbatim

`TODO.md` lines 121–135:

> ## T-08 — Bind shared collection, outbound, approval and readiness contracts
> State: **NOT_STARTED**. Workflow role: W-05. Repository scope: shared.
> Output: `versioned-interface-contracts`.
> Acceptance: Strict public-placement/person-directed envelopes, canonical contact sequence, one CLOSED/ACK contract and approval/readiness schemas bind consumers without fake contacts or terminal aliases.
> Requirements: R-04, R-21, R-22, R-23, R-27, R-28. Checks: C-08, C-F17.

`ACCEPTANCE-MATRIX.md` line 15 (R-04 row) and `live-ledgers/checks.json` item `C-08` carry the same sentence; `C-08` states `"status": "UNVERIFIED"`, `"required": true`, `"required_qc_alias": "opus-chain"`, `"candidate_sha": null` — no receipt has ever existed.

`DATA-CONTRACTS.md` line 22, section 3, person branch:

> Person branch: trusted contact mapping; scoped consent/requested-delivery basis; field refusal, channel/global suppression and human ownership; purpose-specific platform eligibility; current sequence and precondition.

Line 24 of the same section closes the gate's vocabulary:

> Return ALLOW, WAIT_UNTIL, SUPPRESSED, QUARANTINED or RECONCILE_UNKNOWN with checked time, binding/policy/fence and supporting evidence.

## 2. What F5 required

`lanes/PBB-018-operator/QC-VERDICT.md`, FAIL — F5:

> **`NO_TRUSTED_CONTACT_MAPPING` can never fire.** `$gate.trusted_contact_mapping_evidence_id` is `{"type":"string","minLength":1}` *and* required, so any gate that reaches the check already carries a non-empty string and `if not gate[...]` is dead code. […] This is a claimed-but-unreachable enforcement reason […] The fix is a design decision to be made from the contract: either the field is genuinely optional and dispatch must refuse with that reason, or it is mandatory and both the dead code and the claim must go.

The verdict also records a competing reading it did not adopt: "probe expects `reason`, implementation returns `errs`". Both readings are answered below — the refusal now populates `reason` **and** leaves `errors == []`.

## 3. Decision recorded

The field is **mandatory but nullable**:

- key present with `null`, `""`, whitespace or format-mark-only → refused check, `SUPPRESSED` / `NO_TRUSTED_CONTACT_MAPPING`, `errors == []`;
- key absent → `INVALID_GATE` naming the field (a gate never written against this contract);
- key with a real id, padded or not → dispatches (known-good control);
- key with a non-string → `INVALID_GATE` naming the field (schema owns "malformed").

That decision is asserted in the suite (`test_a_missing_mapping_key_is_malformed_not_a_named_refusal`, added in the base commit) so it cannot drift back to either failure mode.

## 4. Proof — one instrument, three trees

### 4.1 The instrument

`evidence/W05/f5_proof.py`, committed in this same commit. Stdlib only, no
network, no checkout: it takes a tree's own
`38-conversational-ai-system` directory, imports that tree's `tools/pb_contracts.py`,
drives the same `contracts.main(["dispatch", …])` call the suite uses, and prints
one line per case. Exit 0 only when all eight cases hold; exit 1 otherwise.

```
python3 -I evidence/W05/f5_proof.py "<tree>/38-conversational-ai-system" A
python3 -I evidence/W05/f5_proof.py "<tree>/38-conversational-ai-system" B
```

Trees are extracted with `git archive`, never checked out over a worktree.

### 4.2 The case list, stated explicitly

Case set **A** (independent, canonical — the numbers of record):

| # | gate field value | expected |
|---|---|---|
| C1 | key absent | `INVALID_GATE`, errors name `trusted_contact_mapping_evidence_id` |
| C2 | `null` | `SUPPRESSED` / `NO_TRUSTED_CONTACT_MAPPING`, `errors == []` |
| C3 | `""` | `SUPPRESSED` / `NO_TRUSTED_CONTACT_MAPPING`, `errors == []` |
| C4 | `"   "` (spaces) | `SUPPRESSED` / `NO_TRUSTED_CONTACT_MAPPING`, `errors == []` |
| C5 | `" \t\n"` (tab/newline) | `SUPPRESSED` / `NO_TRUSTED_CONTACT_MAPPING`, `errors == []` |
| C6 | U+200B (format mark only) | `SUPPRESSED` / `NO_TRUSTED_CONTACT_MAPPING`, `errors == []` |
| C7 | `"ev-tcm-1"` | exit 0, `DISPATCHED` / `GATE_ALLOWED` |
| C8 | `"  ev-tcm-1  "` | exit 0, `DISPATCHED` / `GATE_ALLOWED` |

Case set **B** (the historical list this file used before this repair): identical
except that C6/U+200B is replaced by B6 = integer `123`, expected `INVALID_GATE`
naming the field. It is kept only so the old table can be reproduced exactly; it
is not the canonical measurement.

Both sets are eight cases. The difference between them is exactly one case —
the one that explains the old number, below.

### 4.3 The old 1/8 was an artefact, not a hold

Under set B, `053c4fee` reports 1/8, and the case that "held" is `B6-non-string`:

```
B6-non-string  HELD  code=1 decision=INVALID_GATE reason='<missing>'
  errors=["$gate: unexpected property 'trusted_contact_mapping_evidence_id'"]
```

It held because the pre-fix tree rejects **every** gate carrying the key with
`$gate: unexpected property 'trusted_contact_mapping_evidence_id'`, and that
rejection message contains the key name. B6 only asks that some error string
contain the key, so the pre-fix rejection satisfies it by accident. The same
tree shows the other side of the same defect — a gate with the key **absent**
dispatches (`B1` `code=0` `DISPATCHED`), which is the dead-code defect F5 named.
A case list in which the only surviving case is one an error message can satisfy
does not measure the decision, so it is not used for the numbers of record.

### 4.4 The numbers of record (set A)

| tree | cases held | exit | the failure |
|---|---|---|---|
| `053c4fee` (prior attempt) | **0/8** | 1 | every gate carrying the key is `INVALID_GATE` "unexpected property"; a gate with the key absent **dispatches** |
| `8e98f155e` (F5 as reviewed) | **3/8** | 1 | holds only the absent-key refusal and the two real-id controls; `null` and `""` → `INVALID_GATE` type errors; `"   "`, `" \t\n"` and U+200B **dispatch** |
| this commit | **8/8** | 0 | — |

Set B on the same three trees, for the record (not the measurement):
`053c4fee` **1/8** exit 1 → `8e98f155e` **4/8** exit 1 → this commit **8/8** exit 0.
The end state is 8/8 under both lists; only the middle number moves.

Known-good control inside the same run: C7 and C8 reach exit 0 with
`DISPATCHED` / `GATE_ALLOWED` on this tree, so the six refusals are the checked
case and not a gate that refuses everything.

Measured with the committed instrument (outputs quoted above are from these
exact commands):

```
python3 -I evidence/W05/f5_proof.py "<pre-fix>/38-conversational-ai-system" A        # 0/8, rc 1
python3 -I evidence/W05/f5_proof.py "<qc-reviewed>/38-conversational-ai-system" A   # 3/8, rc 1
python3 -I evidence/W05/f5_proof.py "<this tree>/38-conversational-ai-system" A     # 8/8, rc 0
```

### 4.5 The suite tests that carry the decision

Same test file copied into each tree; the two tests that pin the decision and
its control:

```
python3 -I tools/tests/test_pb_contracts.py \
  -k test_a_missing_mapping_key_is_malformed_not_a_named_refusal \
  -k test_a_real_trusted_contact_mapping_still_dispatches

# 053c4fee tree, this test file copied in -> FAILED (failures=2, errors=1), rc 1
# this tree                               -> OK, rc 0
```

## 5. Suites run

Repaired tree (this commit):

| command | result |
|---|---|
| `bash scripts/qc-pb-contracts.sh` (cwd `38-conversational-ai-system`) | exit 0, **43 tests OK** |
| `python3 -I -m unittest discover -s 38-conversational-ai-system/tools/tests -p 'test_*.py'` | exit 0, **324 tests OK, 1 skip** |

Same commands on a `git archive` of `origin/main` (`9c69a5d7d`) at the time of
this repair:

| command | result |
|---|---|
| `bash scripts/qc-pb-contracts.sh` | exit 0, **42 tests OK** |
| `python3 -I -m unittest discover -s 38-conversational-ai-system/tools/tests -p 'test_*.py'` | exit 0, **323 tests OK, 1 skip** |

Difference is exactly the one added test in each runner (42 → 43, 323 → 324).

## 6. No assertion was weakened

The diff of the test file against `origin/main` is **+19 lines, no deletions**:
one new test method (`test_a_missing_mapping_key_is_malformed_not_a_named_refusal`)
and nothing else. No existing assertion was edited, loosened or removed, and no
schema, gate code or fixture is changed in this lane.

## 7. Deferred

- **Independent QC PASS receipt (C-08).** Cannot be produced by the author; `checks.json` requires `required_qc_alias: "opus-chain"` and `different_native_agent_after_repair: true`. This lane supplies the proof a verifier needs, not the verdict.
- **`live-ledgers/` status for T-08.** `build.json` / `checks.json` / `blockers.json` live in the package directory, outside the git tree, and are updated by the merge/QC lanes. T-08 remains `NOT_STARTED` / `UNVERIFIED` until a verifier writes its own receipt; editing them from a builder lane would be self-approval.
- **`blockers.json` entry F5-11 adjudication.** The two conflicting readings (unreachable reason vs `reason`/`errs` field) are both satisfied by this lane's evidence; the adjudication record itself belongs to the verifier.
