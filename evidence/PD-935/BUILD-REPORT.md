# PD-935 — BUILD REPORT: ultra sidecar test fixture declared no `kie` route

**Unit:** PD-935 · lane FL02 · branch `pd/fl02-intake-driver`
**Repo:** `trevorotts1/openclaw-onboarding`
**Base commit:** `7d21a9641e98708959a07923df353ccc4bc2002a` (== `origin/pd/fl02-intake-driver` before this unit)
**Merge-base with `origin/main`:** `1a476d2cbbc57fedbfa9dbcf73c91074bfd1a1dc`
**Acceptance row used:** ledger row PD-935 `acceptance: ["A1"]`; the brief file for PD-935 does
not exist (`loop-control/pd-fix/briefs/` holds only PD-933), so A1 is read from the unit's own
`note` plus the four HARD REQUIREMENTS in the dispatch text. No spec text beyond those was used.

---

## 1. What changed (fixture only)

`23-ai-workforce-blueprint/templates/role-library/presentations/intake/interview-app/test/test_operator_contract_handoff.py`

```
@@ -236,0 +237,7 @@
+    # image_render (P-STYLE-PREVIEW / P4-RENDER) routes only via provider kie; ultra
+    # refuses any non-mechanical phase with no eligible route, so the profile the test
+    # asserts against must own kie or the launch it asserts is impossible by fixture.
+    profile['providers']['kie'] = {
+        'provider': 'kie', 'presence': True, 'detected': True,
+        'wired_models': [], 'consented': True,
+    }
@@ -239 +246 @@
-    monkeypatch.setattr(model_router, 'provider_key_resolves', lambda provider: provider == 'deepseek-direct')
+    monkeypatch.setattr(model_router, 'provider_key_resolves', lambda provider: provider in ('deepseek-direct', 'kie'))
```

`git diff --stat` for the code change: **1 file changed, 8 insertions(+), 1 deletion(-)**.
Launcher, `model_router.py`, and every other production file are **untouched**.

---

## 2. A1 — assertion lines byte-identical

Base lines 252–259 vs head lines 259–266 (the fixture added 7 lines):

| side | command | SHA-256 |
|---|---|---|
| base `7d21a9641` | `git show 7d21a9641:<file> \| sed -n '252,259p' \| shasum -a 256` | `0b755d7c456731b93a9f68ac0109d0e5eb0e14a62249e08b1aed842b7b14c179` |
| head (working tree) | `sed -n '259,266p' <file> \| shasum -a 256` | `0b755d7c456731b93a9f68ac0109d0e5eb0e14a62249e08b1aed842b7b14c179` |

Identical block:

```
    assert rc == 0
    mode_plan = json.loads((run / '.mode-plan.json').read_text())
    model_plan = json.loads((run / '.model-plan.json').read_text())
    assert mode_plan['mode'] == 'ultra' and mode_plan['declared'] is True
    assert mode_plan['ceiling']['operator_ceiling'] == 100
    assert json.loads((run / 'engine-env.json').read_text())['mode'] == 'ultra'
    authoring = next(row for row in model_plan['decisions'] if row['capability'] == 'authoring')
    assert authoring['provider'] == 'deepseek-direct' and authoring['model'] == 'deepseek-flash'
```

No assertion was weakened, deleted, renamed, skipped or xfailed.

---

## 3. A1 — the fixture change is LOAD-BEARING (same tree, mutation pair)

Single worktree `tmp/UNIT/wt-pd935`; fixture reverted with `git checkout -- <file>`, run,
restored, run again.

**OLD fixture (tip as-is):**

```
$ python3 -m pytest test_operator_contract_handoff.py::test_launcher_writes_ultra_mode_and_client_route_sidecars -q
>       assert rc == 0
E       assert 3 == 0
test_operator_contract_handoff.py:252: AssertionError
Captured stderr:
MODEL PLAN REFUSED: ultra: phase 'P-STYLE-PREVIEW' (capability 'image_render') has no eligible route -- ultra launch refused BEFORE any spend
```

**NEW fixture (kie declared + key resolves):**

```
$ python3 -m pytest test_operator_contract_handoff.py::test_launcher_writes_ultra_mode_and_client_route_sidecars -q
>       assert mode_plan['ceiling']['operator_ceiling'] == 100
E       assert 400 == 100
test_operator_contract_handoff.py:263: AssertionError
Captured stdout:
launcher: client model plan stamped -- authoring=deepseek-direct/deepseek-flash [client workhorse]; ...
launcher: run mode ULTRA (source: --mode) -- ... ; recorded in .mode-plan.json
```

The failure moved from `assert rc == 0` (launch refused, rc 3) to `assert
mode_plan['ceiling']['operator_ceiling'] == 100` (launch ran). Both sidecars the test
asserts — `.mode-plan.json` and `.model-plan.json` — were written and read successfully;
`assert mode_plan['mode'] == 'ultra' and mode_plan['declared'] is True` passed.

### PD-936, untouched

`assert mode_plan['ceiling']['operator_ceiling'] == 100` now sees **400**
(`ULTRA_OPERATOR_CEILING = 400`). Per the dispatch's hard requirement this is **PD-936's
separate defect**: stopped here, this unit did not touch that line or the ceiling.

---

## 4. A1 — router NOT widened: four-case gate probe

`tmp/UNIT/gate_probe.py` calls `launcher.model_plan_gate(run_dir, mode="ultra")` against four
profiles (key resolution patched exactly as the test does):

```
CASE 1-old-fixture-direct-only: rc=3
CASE 2-new-fixture-direct+kie: rc=None
CASE 3-kie-declared-key-unresolved: rc=3
CASE 4-kie-nonsense-wired-model: rc=3
SUMMARY {"old_refuses": true, "new_proceeds": true, "keyless_refuses": true, "nonsense_refuses": true}
```

- Case 1 = old fixture → refuses with the exact `MODEL PLAN REFUSED` line.
- Case 2 = new fixture → proceeds (rc None) with the model-plan banner.
- Case 3 = `kie` declared but no resolvable key → **still refuses** (FIX 114 key gate intact).
- Case 4 = `kie` declared, key resolves, `wired_models: ["made-up/not-a-real-model"]` →
  **still refuses**; a nonsense model cannot mint an `image_render` route.

---

## 5. Test file — pass/fail by test id, base vs head

Every id run individually (`timeout 40` per id) because one live-shape test must be bounded;
`TMPDIR` was overridden to `/Volumes/mac mini m4/swarm-contract/pd-fix/tmp/UNIT` so pytest's
`tmp_path` default never lands in `/tmp` — stated here per the storage rule.

**17 ids · 14 PASS · 3 FAIL on BOTH trees.** Verdicts identical base→head:

| verdict base | verdict head | test id |
|---|---|---|
| PASS | PASS | `test_contract_runs_real_driver_then_resolver_without_provider` |
| PASS | PASS | `test_live_contract_shape_projects_ultra_and_direct_flash_to_real_consumers` |
| **FAIL** | **FAIL** | `test_launcher_writes_ultra_mode_and_client_route_sidecars` — **reason changed**: base `assert 3 == 0` + `MODEL PLAN REFUSED`; head `assert 400 == 100` (PD-936) |
| PASS | PASS | `test_rejects_client_shaped_or_incomplete_contract` |
| PASS | PASS | `test_contract_delegates_to_bridge_launcher_with_transport_stub` |
| FAIL | FAIL | `test_signed_receipt_binds_existing_cc_task_and_replays_once` — pre-existing env: `AssertionError: PD025 fresh CC checkout/runtime missing` (`/private/tmp/pd025-cc-current/node_modules/.bin/tsx`) |
| PASS | PASS | `test_cli_propagates_deferred_bridge_status` |
| FAIL | FAIL | `test_same_signed_contract_resumes_retry_then_acknowledges_once` — same missing-CC-tsx precondition |
| PASS | PASS | `test_changed_contract_cannot_resume_authenticated_run` |
| PASS | PASS | `test_optional_boolean_and_yes_no_types_allow_unselected_extras_without_coercion` |
| PASS | PASS | `test_general_mode_contract_recovers_receipt_only_run` |
| PASS | PASS | `test_live_contract_shape_maps_brief_to_canonical_client_notes_and_seals_all_options` |
| PASS | PASS | `test_unknown_answer_is_rejected_before_receipt_or_partial_intake` |
| PASS | PASS | `test_live_contract_shape_resumes_after_mid_intake_failure_without_duplicate_turns` |
| PASS | PASS | `test_same_contract_reopens_only_obsolete_webinar_block` |
| PASS | PASS | `test_operator_launch_uses_selected_env_store_without_logging_values` |
| PASS | PASS | `test_operator_launch_rejects_unresolved_selected_transport` |

The two CC-tsx failures are environment preconditions of the unit's harness (PD-931 added the
`PD_CC_ROOT` escape; this unit did not set it), identical on base and head, and unrelated to
the fixture change.

---

## 6. Hunk attribution — merge-base `1a476d2cb` → HEAD `7d21a9641`

| marker | commit | sibling unit | files |
|---|---|---|---|
| base→PD-001 | `37fc849c2` | PD-001 | `deck-intake-driver.py`, `test_f21_f22_intake_transcript_envelope.py`, `test_pd_intake_signature.py` |
| PD-001 qc | `5ff8a5f22` | PD-001 | two of the same test files |
| PD-011 | `bb1ae8042` | PD-011 | `deck-intake-driver.py`, `test_pd_intake_complete_signing.py` |
| PD-016 | `44c9a0ea1` | PD-016 | `deck-intake-driver.py`, `test_pd_intake_frame_wording.py` |
| PD-015 | `f427a31b6` | PD-015 | `deck-intake-driver.py`, `test_pd_intake_owner_msg.py` |
| PD-004b | `27c667070` | PD-004b | `deck-intake-driver.py`, `intake_provenance.py`, `test_one_question_intake.py`, `test_pd004b_intake_provenance.py` |
| PD-913 | `869d0637e` | PD-913 | `deck-intake-driver.py` + 9 script tests + `evidence/PD-913/BUILD-REPORT.md` |
| PD-927 | `108b092bf` | PD-927 | `bridge/intake_bridge.py`, `test_pd927_operator_replay_atomic_turns.py` |
| PD-930 | `87e2458d4` | PD-930 | `test_operator_contract_handoff.py` (atomic-shape fixtures) |
| PD-932 | `2c3d74b92` | PD-932 | `test_operator_contract_handoff.py` (workhorse_model retarget) |
| PD-931 | `7d21a9641` | PD-931 | `test_operator_contract_handoff.py` (`PD_CC_ROOT`) |
| **this unit** | new commit | **PD-935** | `test_operator_contract_handoff.py` — fixture hunk only, lines 233–246; no other hunk |

---

## 7. Result

Fixture retargeted; launcher and router untouched; the test's own assertions byte-identical.
The target test still fails, but now **only** at PD-936's `operator_ceiling == 100` (actual
400) — the separate defect this unit was ordered not to touch.
