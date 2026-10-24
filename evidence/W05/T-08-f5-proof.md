# T-08 / F5 — `NO_TRUSTED_CONTACT_MAPPING` is a reachable, named refusal

Lane: PBB-229 · Unit: T-08 (W-05, `versioned-interface-contracts`, repo scope shared)
Branch: `pb/PBB-229/t-08`
Pinned base: `3550dc3f4316e1ad6aed7362c9a79a890aa29b1c` (`origin/main` after `git fetch origin`)
Prior attempt under test: `053c4fee` (ancestor of the pinned base)
F5 as reviewed: `8e98f155e` (the commit `lanes/PBB-018-operator/QC-VERDICT.md` names)
Artifact under test: `38-conversational-ai-system/tools/pb_contracts.py`, `schemas/outbound-action.schema.json`

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

That decision is now asserted in the suite (`test_a_missing_mapping_key_is_malformed_not_a_named_refusal`, added in this lane) so it cannot drift back to either failure mode.

## 4. Proof — one instrument, three trees

Instrument: `f5_proof.py` (lane root), which drives the same `contracts.main(["dispatch", …])` call the suite uses, and asserts all eight cases. Trees extracted with `git archive`, never checked out over a worktree.

```
python3 -I f5_proof.py "pre-fix/38-conversational-ai-system"        # 053c4fee
python3 -I f5_proof.py "qc-reviewed/38-conversational-ai-system"   # 8e98f155e
python3 -I f5_proof.py "repo/38-conversational-ai-system"          # this lane
```

| tree | cases held | exit | the failure |
|---|---|---|---|
| `053c4fee` (prior attempt) | 1/8 | 1 | no mapping **dispatched**: `DISPATCHED` / `GATE_ALLOWED`; a gate that carried the field was `INVALID_GATE` "unexpected property" |
| `8e98f155e` (F5 as reviewed) | 4/8 | 1 | `null` → `INVALID_GATE` type error; `""` → `INVALID_GATE`; `"   "` and `" \t\n"` **dispatched** |
| this lane | 8/8 | 0 | — |

Known-good control on the same instrument: `ev-tcm-1` and `"  ev-tcm-1  "` → `code 0`, `DISPATCHED`, `GATE_ALLOWED` on this lane, so the refusals above are the checked case and not a gate that refuses everything.

Suite tests that carry the decision and its control, run against both trees with the same file:

```
# pre-fix tree, current test file copied in
python3 -I tools/tests/test_pb_contracts.py -k test_a_missing_mapping_key_is_malformed_not_a_named_refusal -k test_a_real_trusted_contact_mapping_still_dispatches
# -> FAILED (failures=2, errors=1)   exit 1

# this lane
python3 -I tools/tests/test_pb_contracts.py -k test_a_missing_mapping_key_is_malformed_not_a_named_refusal -k test_a_real_trusted_contact_mapping_still_dispatches
# -> OK                              exit 0
```

## 5. Suites run on this lane

| command | result |
|---|---|
| `bash 38-conversational-ai-system/scripts/qc-pb-contracts.sh` | exit 0, 43 tests OK (42 before + the new one) |
| `python3 -I -m unittest discover -s tools/tests -p 'test_*.py'` | exit 0, 324 tests OK, 1 named dependency skip |

## 6. No assertion was weakened

The blank/null and real-id assertions in `test_pb_contracts.py` are byte-identical to the pinned base; the only edit to that file is the added test. No schema, no gate code and no fixture changed in this lane — the behaviour F5 names was already correct on the pinned base and this lane proves it instead of rewriting it.

## 7. Deferred

- **Independent QC PASS receipt (C-08).** Cannot be produced by the author; `checks.json` requires `required_qc_alias: "opus-chain"` and `different_native_agent_after_repair: true`. This lane supplies the proof a verifier needs, not the verdict.
- **`live-ledgers/` status for T-08.** `build.json` / `checks.json` / `blockers.json` live in the package directory, outside the git tree, and are updated by the merge/QC lanes. T-08 remains `NOT_STARTED` / `UNVERIFIED` until a verifier writes its own receipt; editing them from a builder lane would be self-approval.
- **`blockers.json` entry F5-11 adjudication.** The two conflicting readings (unreachable reason vs `reason`/`errs` field) are both satisfied by this lane's evidence; the adjudication record itself belongs to the verifier.
