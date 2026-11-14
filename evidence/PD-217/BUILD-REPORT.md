# PD-217 — the install receipt must match recorded ids

Unit PD-217 · lane FL16 · repo `trevorotts1/openclaw-onboarding` · branch `pd/fl16-page-installer`
Builder: deepseek-chain. This is a BUILD report; the verdict belongs to the opus-chain reviewer.

## Spec quoted (01-BUILD-SPEC.md, section "### PD-217")

> ### PD-217 — The install receipt must match recorded ids
>
> | Field | Value |
> |---|---|
> | Findings | PD-217 |
> | Severity | Moderate |
> | Builder | deepseek-chain — difficulty mechanical: two conditions in one file, fully specified |
> | Quality control (finds and fixes) | suggested opus-chain at thinking level low (mechanical wording, path or one-file change); re-check of any repair by a FRESH opus-chain agent at medium or above; the orchestrator decides |
> | Critical first | no |
> | Lane and repository | FL16 · trevorotts1/openclaw-onboarding |
> | Wave | 3 |
> | Depends on (must be ACCEPTED, that is QC-passed, first) | PD-069 |
> | Held by decision | none |
> | Existing tests it breaks and must update | none known in advance; the lane's reading units and the test census name the rest (rule 15) |
> | Live-action flag | none: files and stubbed tests only |
> | Acceptance rows the checker must run | A1 |
>
> **Carried-over unit text (from `PASS5-GATES.md`, section PD-217; ids, decisions and lanes already converted to final):**
>
> - **Change:** `ghl_external_installer.py` lines 797–800: for each of `funnel_id` and the page ids present in the receipt, fail when the ledger has no value for that key or the values differ. Lines 853–857: the same for `form_id` and `workflow_id`. Message: "receipt id not recorded in this run's operations ledger".
> - **Acceptance:** the existing self-test still passes; a new test deletes the ids from the ledger after a mock install → `validate_receipt` fails with the new message.

The carried-over line numbers are pre-PD-048a coordinates. At branch head, PD-048a's
`flat_receipt_fields` block moved those two closures down: the page block sits at
`validate_receipt` 879–885 and the gate block at `_validate_gate_receipts` 938–942
(both at 538253f). Those are the blocks changed.

## Files changed (owned paths only)

- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/ghl_external_installer.py`
- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_pd048_receipt_contract.py`

No other file touched. `update-skills.sh`, `universal-sops/_content-manifest.json` and
`install.sh` untouched.

## The change

Page branch — `validate_receipt`, `git show -U0 1d6cc92bd`:

```
  @@ -879,7 +879,13 @@ def validate_receipt(run_dir: Path, phase_id: str,
-    # Ledger agreement: the receipt's remote IDs must equal the ops ledger's
-    # recorded IDs. A receipt naming IDs the ledger never recorded is
-    # fabricated, even when the execution_id matches.
-    for key in ("funnel_id", *[f"{pg}_page_id" for pg in ("sales", "checkout", "vsl")]):
-        if remote.get(key) and ops_remote.get(key) and remote[key] != ops_remote[key]:
-            return False, (f"{phase_id}: receipt {key} {remote[key]!r} != ops "
-                           f"ledger {ops_remote[key]!r} -- fabricated"), data
+    # Ledger agreement (PD-217): every remote id the receipt NAMES must be
+    # recorded in this run's ops ledger AND equal it. A receipt naming an ID
+    # the ledger never recorded is fabricated even when the execution_id
+    # matches, so an ABSENT ledger value now fails exactly like a mismatch.
+    for key in sorted(k for k in remote
+                      if k == "funnel_id" or k.endswith("_page_id")):
+        val = remote.get(key)
+        if not isinstance(val, str) or not val:
+            continue
+        if ops_remote.get(key) != val:
+            return False, (f"{phase_id}: receipt id not recorded in this run's "
+                           f"operations ledger ({key} {val!r} vs ledger "
+                           f"{ops_remote.get(key)!r})"), data
```

Gate branch — `_validate_gate_receipts`, same commit:

```
  @@ -938,0 +945,2 @@ def _validate_gate_receipts(run_dir: Path, data: dict, scope: dict,
+    # PD-217: the same rule as the page branch -- an id the ledger never
+    # recorded is not proof of an install, whether it differs or is missing.
  @@ -940,3 +948,4 @@ def _validate_gate_receipts(run_dir: Path, data: dict, scope: dict,
-        if ops_remote.get(key) and val != ops_remote[key]:
-            return False, (f"{PHASE_FORM_GATE}: receipt {key} {val!r} != ops "
-                           f"ledger {ops_remote[key]!r} -- fabricated"), data
+        if ops_remote.get(key) != val:
+            return False, (f"{PHASE_FORM_GATE}: receipt id not recorded in this "
+                           f"run's operations ledger ({key} {val!r} vs ledger "
+                           f"{ops_remote.get(key)!r})"), data
```

Both old conditions were `if X and Y and X != Y` — an absent ledger value short-circuited
to false and the receipt validated. Both are now `if ledger != receipt: fail`, which covers
absent and different. The required message phrase `receipt id not recorded in this run's
operations ledger` appears verbatim in both, followed by the key and both values.

## Acceptance row A1 — proven

Spec: "the existing self-test still passes; a new test deletes the ids from the ledger after
a mock install → `validate_receipt` fails with the new message."

Nine new rows in `test_pd048_receipt_contract.py` (hunk `@@ -346,0 +347,89 @@`), each its own
BEFORE/AFTER pair on one run dir: the completed in-memory install validates with the ops
ledger intact, then the ledger loses the id (or records a different one) and the SAME receipt
stops validating with the named message.

- `test_pd217_a1_page_receipt_id_absent_from_the_ledger_fails` × 5 params:
  SALES/`funnel_id`, SALES/`sales_page_id`, SALES/`checkout_page_id`,
  VSL/`funnel_id`, VSL/`vsl_page_id`
- `test_pd217_a1_gate_receipt_id_absent_from_the_ledger_fails` × 2 params:
  `form_id`, `workflow_id`
- `test_pd217_a1_a_different_ledger_id_fails_with_the_same_message` × 2 params:
  SALES/`sales_page_id`, gate/`workflow_id` — the old mismatch branch keeps its teeth under
  the one new message

Row set run on the pushed commit (`1d6cc92bd`, fresh worktree, `--tb=no`):

```
......................                                                   [100%]
22 passed in 0.25s
```

Existing self-test on the same commit:

```
ghl_external_installer selftest -> PASS (preflight, scope, fake-receipt refusal, mock adapters + readback + location, kill-resume no-dup, gate pair)
```

## Failure proof — the mutation turns the row RED, then is reverted

The regression this row is aimed at: pre-PD-217, an id deleted from the ledger still
validated. Mutation = restore the installer from the parent commit (`git show 1d6cc92bd^:<path>`),
keep the new tests, run. Exit code 1:

```
.............FFFFFFFFF                                                   [100%]
=========================== short test summary info ============================
FAILED tests/test_pd048_receipt_contract.py::test_pd217_a1_page_receipt_id_absent_from_the_ledger_fails[P-U-GHL-SALES-funnel_id-pre0]
FAILED tests/test_pd048_receipt_contract.py::test_pd217_a1_page_receipt_id_absent_from_the_ledger_fails[P-U-GHL-SALES-sales_page_id-pre1]
FAILED tests/test_pd048_receipt_contract.py::test_pd217_a1_page_receipt_id_absent_from_the_ledger_fails[P-U-GHL-SALES-checkout_page_id-pre2]
FAILED tests/test_pd048_receipt_contract.py::test_pd217_a1_page_receipt_id_absent_from_the_ledger_fails[P-U-GHL-VSL-funnel_id-pre3]
FAILED tests/test_pd048_receipt_contract.py::test_pd217_a1_page_receipt_id_absent_from_the_ledger_fails[P-U-GHL-VSL-vsl_page_id-pre4]
FAILED tests/test_pd048_receipt_contract.py::test_pd217_a1_gate_receipt_id_absent_from_the_ledger_fails[form_id]
FAILED tests/test_pd048_receipt_contract.py::test_pd217_a1_gate_receipt_id_absent_from_the_ledger_fails[workflow_id]
FAILED tests/test_pd048_receipt_contract.py::test_pd217_a1_a_different_ledger_id_fails_with_the_same_message[P-U-GHL-SALES-sales_page_id-pre0]
FAILED tests/test_pd048_receipt_contract.py::test_pd217_a1_a_different_ledger_id_fails_with_the_same_message[P-U-FORM-GATE-workflow_id-pre1]
9 failed, 13 passed in 0.40s
```

The 13 pre-existing rows still pass under the mutation — the split is caused by the changed
blocks, not by the harness. The failure MESSAGE under the mutation shows the defect itself,
i.e. the old code certifying a receipt whose id the ledger no longer records:

```
E       AssertionError: P-U-GHL-SALES: verified install (funnel funnel_mem_0001, 2 page(s), readback ok)
E       AssertionError: P-U-FORM-GATE: verified gate form form_mem_0001 + workflow wf_mem_0002 (readback ok)
```

Reverted (installer copied back, 2 occurrences of the new message restored), re-run:

```
......................                                                   [100%]
22 passed in 0.25s
```

## Test runs by id — base and head

base = `538253f015346939a59f58471293a02bd543cc39` (PD-069 accepted head, PD-217 parent)
head = `1d6cc92bd66472e9c8cef23fff4f6a4672215b6d` (this unit)

| id | command | base | head |
|---|---|---|---|
| `test_pd048_receipt_contract.py` | `python3 -m pytest tests/test_pd048_receipt_contract.py -q` | 13 passed | 22 passed |
| `test_pres011_ghl_external.py` + `test_item21_brief_consumer.py` + above | same command, 3 files | 47 passed | 56 passed |
| module self-test | `python3 ghl_external_installer.py --selftest` | PASS, rc=0 | PASS, rc=0 |

Both suites exit 0 on base and head. 56 − 47 = 9 = the new rows; 22 − 13 = 9. No test was
weakened, renamed, skipped or removed; the 13 pre-existing rows are byte-identical.

## Hunk attribution — merge-base `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc` to head

Commits on the branch between merge-base and head:

| commit | unit | files |
|---|---|---|
| `164b893b3` | PD-048a | `ghl_external_installer.py` (+127/−12), `tests/test_pd048_receipt_contract.py` (new, 348 lines) |
| `97f99ab84` | PD-918 (sibling, not this lane's file) | `phase_verifiers.py` (+16/−4) |
| `ffe5625b5` | PD-918 | `evidence/PD-918/BUILD-REPORT.md` (new) |
| `4198c0648` | PD-069 | `tests/test_pd048_receipt_contract.py` (+111), `evidence/PD-069/BUILD-REPORT.md` (new) |
| `48a589eee`, `a432e045d`, `538253f01` | PD-069 | `evidence/PD-069/BUILD-REPORT.md` only |

Hunks in the two owned files, by owner:

**`ghl_external_installer.py` (merge-base..538253f) — every hunk is PD-048a's**, hunks
`@@ -713,0 +714,85 @@` (the new `_canonical_json_sha256` / `_gate_plan_blocks` / `flat_receipt_fields`
block), `@@ -947 +1032 @@`, `@@ -964,0 +1050,2 @@`, `@@ -965,0 +1053,13 @@`,
`@@ -967 +1066,0 @@`, `@@ -971,2 +1069,0 @@`, `@@ -974,2 +1071,6 @@`, `@@ -977 +1078,2 @@`,
`@@ -1058,0 +1161 @@`, `@@ -1171,0 +1275 @@`, `@@ -1202,2 +1306 @@`, `@@ -1210 +1313 @@`,
`@@ -1300,2 +1403,2 @@`. `git blame` on the flat-field block (lines 726–800) returns
`164b893b3` for 73 of 75 lines (the other 2 are pre-existing `e8deb7158`). PD-069's own
installer hunks did not land separately — PD-048a's commit already carried `name`/`fields`/`steps`
into `flat_receipt_fields`, which is why PD-069's commit is test-and-report only.

**`tests/test_pd048_receipt_contract.py`** — one whole-file hunk `@@ -0,0 +1,348 @@` from
merge-base (PD-048a created the file). Relative to that file's own base, PD-069's block is
`@@ -235,0 +236,111 @@` (its five rows, `SHAPE_MARKERS`, `_shape_reasons`).

**This unit's hunks (commit `1d6cc92bd`):**

- `ghl_external_installer.py` `@@ -879,7 +879,13 @@` — page ledger agreement
- `ghl_external_installer.py` `@@ -938,0 +945,2 @@` and `@@ -940,3 +948,4 @@` — gate ledger agreement
- `tests/test_pd048_receipt_contract.py` `@@ -346,0 +347,89 @@` — the PD-217 rows, appended
  after PD-069's block (which ends at line 346)

No hunk of PD-048a's or PD-069's was modified, reverted or re-formatted.

## Remote-head proof

Pre-push, before anything was written to the branch:

```
538253f015346939a59f58471293a02bd543cc39	refs/heads/pd/fl16-page-installer
```

`git push origin HEAD:refs/heads/pd/fl16-page-installer`:

```
   538253f01..1d6cc92bd  HEAD -> pd/fl16-page-installer
```

`git ls-remote --heads origin refs/heads/pd/fl16-page-installer`, after that push:

```
1d6cc92bd66472e9c8cef23fff4f6a4672215b6d	refs/heads/pd/fl16-page-installer
```

All 40 characters compared literally: `1d6cc92bd66472e9c8cef23fff4f6a4672215b6d` is the
commit this unit built.

Second push, carrying this report file:

```
   1d6cc92bd..5652fcb32  HEAD -> pd/fl16-page-installer
5652fcb32d11af7a8a51ee611cbbfeb3479c7f4a	refs/heads/pd/fl16-page-installer
```

(the `ls-remote` line above was taken immediately after that push). The head that carries
this addendum is proven with `git ls-remote` after its own push and quoted in the delivery
message, so every push this unit made has a 40-character remote proof somewhere it can be
checked against.

The tests and the self-test above were run in a FRESH worktree checked out at
`1d6cc92bd66472e9c8cef23fff4f6a4672215b6d` — the pushed artefact, not the editing tree.

## Storage discipline

Every scratch path lives under `TMPDIR=/Volumes/mac mini m4/swarm-contract/pd-fix/tmp/PD-217`
(created by this unit): build worktree, base worktree, proof worktree, `*.log`, and the two
throwaway installer copies. No `/tmp`, `/private/tmp` or `/var/folders` path was used. The
lane clone `/Volumes/mac mini m4/swarm-contract/pd-fix/worktrees/onboarding/FL16` was left
untouched and clean (it still sits at `ffe5625b5`, 4 commits behind, as found).

## Anything unproved

- No live GoHighLevel call was made; the spec's live-action flag is `none` and every row uses
  `MemoryPageAdapter` / `MemoryGateAdapter`.
- The `phase_verifiers.verify(...)` wrapper was not re-run for the stale-ledger case: this
  unit's contract is `validate_receipt`, which is the installer's own proof. PD-048a's rows
  already prove the wrapper accepts a completed install; PD-217 changes only the refusal path.
- `test_pres011_ghl_external.py` still exercises the hand-made "perfect fake" (no ops ledger
  entry at all) and still refuses it — that path is rejected earlier, at the recorded-execution
  check, so PD-217 did not change its outcome. Verified by the 47→56 suite run, not by a
  dedicated new row.
