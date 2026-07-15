#!/usr/bin/env python3
"""
test_state_engine.py — unit + interruption test suite for state_engine.py
(Skill 62, build unit U6).

Stdlib only (unittest / json / os / subprocess). Zero network. Zero secrets.

Run:  python3 test_state_engine.py            (verbose unittest)
      python3 -m pytest test_state_engine.py   (also works; pytest is present
                                                 in this environment, but the
                                                 suite does not require it)

Coverage map (spec Section 19.1 "Unit tests" + Section 19.4 "Break-it tests",
the parts this unit — U6 — owns):

  - schemas and validation                         -> SchemaValidationTests
  - idempotency hashing                             -> IdempotencyTests
  - state transitions                               -> TaskStateMachineTests
  - budget enforcement                              -> BudgetEnforcementTests
  - manifest atomic updates                         -> AtomicWriteTests
  - simultaneous manifest writer attempt             -> ProjectLockTests
  - session restart with in_progress provider jobs   -> InterruptionRecoveryTests
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "lib"))

import state_engine as se  # noqa: E402
import json_schema_lite as jsl  # noqa: E402


def _mk_run_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="cwfe-u6-test-"))


def _mk_project(run_dir: Path, *, cap: float = 100.0) -> dict:
    state = se.ProjectState(run_dir)
    return state.create_project(
        project_id="proj-test",
        client_slug="acme-co",
        project_slug="cinematic-launch",
        deliverable_type="cinematic-website",
        budget_cap_usd=cap,
    )


class SchemaValidationTests(unittest.TestCase):
    """The five schema files exist, are valid JSON Schema, and the lite
    validator actually enforces required fields / types / enums / patterns —
    not just returning [] unconditionally."""

    def test_all_five_schema_files_exist_and_parse(self):
        for kind, fname in se.SCHEMA_FILES.items():
            path = se._STRUCTURE_DIR / fname
            self.assertTrue(path.exists(), f"missing schema file for {kind}: {path}")
            schema = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(schema.get("$schema"), "http://json-schema.org/draft-07/schema#")
            self.assertIn("type", schema)

    def test_valid_project_manifest_passes(self):
        run_dir = _mk_run_dir()
        try:
            manifest = _mk_project(run_dir)
            errors = jsl.validate(manifest, se._load_schema("project-manifest"))
            self.assertEqual(errors, [])
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    def test_missing_required_field_is_rejected(self):
        schema = se._load_schema("project-manifest")
        bad = {"schema_version": "1.0.0"}  # missing everything else
        errors = jsl.validate(bad, schema)
        self.assertTrue(any("missing required property" in e for e in errors))

    def test_wrong_type_is_rejected(self):
        schema = se._load_schema("cost-ledger")
        bad = {
            "schema_version": "1.0.0",
            "project_id": "p1",
            "budget_cap_usd": "not-a-number",  # wrong type
            "cumulative_spend_usd": 0,
            "remaining_budget_usd": 0,
            "entries": [],
            "created_at": "t",
            "updated_at": "t",
        }
        errors = jsl.validate(bad, schema)
        self.assertTrue(any("expected type" in e for e in errors))

    def test_enum_violation_is_rejected(self):
        schema = se._load_schema("deployment-receipt")
        bad = {
            "schema_version": "1.0.0",
            "project_id": "p1",
            "environment": "staging",  # not in enum [preview, production]
            "host": "vercel",
            "commit_sha": "abc123",
            "status": "ready",
            "created_at": "t",
            "updated_at": "t",
        }
        errors = jsl.validate(bad, schema)
        self.assertTrue(any("is not one of" in e for e in errors))

    def test_pattern_violation_on_content_hash_is_rejected(self):
        schema = se._load_schema("content-manifest")
        instance = {
            "schema_version": "1.0.0",
            "project_id": "p1",
            "methodology_source": "signature-funnel",
            "source_skill": "49-signature-funnel",
            "source_skill_version": "1.0.0",
            "page_profiles": [{"profile_id": "home", "sections": ["hero"]}],
            "section_order": ["hero"],
            "approved_copy_paths": [],
            "cta_map": {},
            "offer_ledger": [],
            "conversion_requirements": {},
            "claims": [],
            "copy_qc_receipt": {},
            "content_hash": "not-a-sha256",
            "locked": True,
            "created_at": "t",
            "updated_at": "t",
        }
        errors = jsl.validate(instance, schema)
        self.assertTrue(any("does not match pattern" in e for e in errors))

    def test_additional_properties_false_rejects_unknown_key(self):
        schema = se._load_schema("scene-plan")
        instance = {
            "schema_version": "1.0.0",
            "project_id": "p1",
            "architecture": "hybrid",
            "scenes": [],
            "created_at": "t",
            "updated_at": "t",
            "totally_unexpected_key": True,
        }
        errors = jsl.validate(instance, schema)
        self.assertTrue(any("additional properties not allowed" in e for e in errors))

    def test_load_raises_on_schema_violation(self):
        run_dir = _mk_run_dir()
        try:
            path = run_dir / "content-manifest.json"
            path.write_text(json.dumps({"schema_version": "1.0.0"}), encoding="utf-8")
            state = se.ProjectState(run_dir)
            with self.assertRaises(se.SchemaValidationFailed):
                state.load("content-manifest")
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)


class IdempotencyTests(unittest.TestCase):
    def test_request_hash_is_deterministic_regardless_of_key_order(self):
        h1 = se.ProjectState.compute_request_hash(
            provider="kie", model="m", operation="generate_image", params={"a": 1, "b": 2}
        )
        h2 = se.ProjectState.compute_request_hash(
            provider="kie", model="m", operation="generate_image", params={"b": 2, "a": 1}
        )
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)

    def test_different_params_produce_different_hashes(self):
        h1 = se.ProjectState.compute_request_hash(
            provider="kie", model="m", operation="generate_image", params={"prompt": "a"}
        )
        h2 = se.ProjectState.compute_request_hash(
            provider="kie", model="m", operation="generate_image", params={"prompt": "b"}
        )
        self.assertNotEqual(h1, h2)

    def test_begin_task_refuses_duplicate_active_request(self):
        run_dir = _mk_run_dir()
        try:
            state = se.ProjectState(run_dir)
            _mk_project(run_dir)
            state.begin_task(
                provider="kie", model="gpt-image-2-text-to-image", operation="generate_image",
                params={"prompt": "hero"}, estimated_cost_usd=0.03,
            )
            with self.assertRaises(se.IdempotencyViolation):
                state.begin_task(
                    provider="kie", model="gpt-image-2-text-to-image", operation="generate_image",
                    params={"prompt": "hero"}, estimated_cost_usd=0.03,
                )
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    def test_begin_task_refuses_resubmit_of_a_completed_request(self):
        """The core AF-CWFE-RESTART-DUPLICATE guarantee: once a task with a given
        request_hash reaches 'complete', re-issuing the SAME logical request
        (e.g. after a restart replays the same plan) must never spend again."""
        run_dir = _mk_run_dir()
        try:
            state = se.ProjectState(run_dir)
            _mk_project(run_dir)
            entry = state.begin_task(
                provider="kie", model="bytedance/seedance-1.5-pro", operation="generate_video",
                params={"scene": "s1"}, estimated_cost_usd=0.5,
            )
            state.transition_task(entry["task_id"], "submitted", provider_task_id="pt-1")
            state.transition_task(entry["task_id"], "in_progress")
            state.transition_task(entry["task_id"], "complete", actual_cost_usd=0.51)

            with self.assertRaises(se.IdempotencyViolation):
                state.begin_task(
                    provider="kie", model="bytedance/seedance-1.5-pro", operation="generate_video",
                    params={"scene": "s1"}, estimated_cost_usd=0.5,
                )
            ledger = state.load("cost-ledger")
            self.assertEqual(len(ledger["entries"]), 1)
            self.assertAlmostEqual(ledger["cumulative_spend_usd"], 0.51, places=6)
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    def test_find_active_or_complete_entry(self):
        run_dir = _mk_run_dir()
        try:
            state = se.ProjectState(run_dir)
            _mk_project(run_dir)
            req_hash = se.ProjectState.compute_request_hash(
                provider="kie", model="m", operation="generate_image", params={"x": 1}
            )
            self.assertIsNone(state.find_active_or_complete_entry(req_hash))
            state.begin_task(
                provider="kie", model="m", operation="generate_image", params={"x": 1},
                estimated_cost_usd=0.01,
            )
            self.assertIsNotNone(state.find_active_or_complete_entry(req_hash))
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)


class BudgetEnforcementTests(unittest.TestCase):
    def test_hard_stop_before_exceeding_cap(self):
        run_dir = _mk_run_dir()
        try:
            state = se.ProjectState(run_dir)
            _mk_project(run_dir, cap=1.0)
            state.begin_task(
                provider="kie", model="m", operation="generate_image", params={"i": 1},
                estimated_cost_usd=0.9,
            )
            with self.assertRaises(se.BudgetExceeded):
                state.begin_task(
                    provider="kie", model="m", operation="generate_image", params={"i": 2},
                    estimated_cost_usd=0.2,
                )
            # the rejected call must not have been recorded
            ledger = state.load("cost-ledger")
            self.assertEqual(len(ledger["entries"]), 1)
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    def test_call_exactly_at_cap_is_allowed(self):
        run_dir = _mk_run_dir()
        try:
            state = se.ProjectState(run_dir)
            _mk_project(run_dir, cap=1.0)
            entry = state.begin_task(
                provider="kie", model="m", operation="generate_image", params={"i": 1},
                estimated_cost_usd=1.0,
            )
            self.assertEqual(entry["status"], "queued")
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)


class TaskStateMachineTests(unittest.TestCase):
    def test_full_happy_path(self):
        run_dir = _mk_run_dir()
        try:
            state = se.ProjectState(run_dir)
            _mk_project(run_dir)
            entry = state.begin_task(
                provider="kie", model="m", operation="generate_video", params={"s": 1},
                estimated_cost_usd=0.1,
            )
            self.assertEqual(entry["status"], "queued")
            entry = state.transition_task(entry["task_id"], "submitted", provider_task_id="pt-9")
            self.assertEqual(entry["status"], "submitted")
            self.assertEqual(entry["provider_task_id"], "pt-9")
            entry = state.transition_task(entry["task_id"], "in_progress")
            entry = state.transition_task(entry["task_id"], "in_progress")  # repeated poll allowed
            entry = state.transition_task(entry["task_id"], "complete", actual_cost_usd=0.11)
            self.assertEqual(entry["status"], "complete")
            self.assertEqual(len(entry["status_history"]), 5)  # None->queued,queued->submitted,submitted->in_progress,in_progress->in_progress,in_progress->complete
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    def test_failed_then_retry_increments_retry_count(self):
        run_dir = _mk_run_dir()
        try:
            state = se.ProjectState(run_dir)
            _mk_project(run_dir)
            entry = state.begin_task(
                provider="kie", model="m", operation="generate_video", params={"s": 1},
                estimated_cost_usd=0.1,
            )
            state.transition_task(entry["task_id"], "submitted")
            state.transition_task(entry["task_id"], "failed", retry_reason="provider timeout")
            entry = state.transition_task(entry["task_id"], "queued")
            self.assertEqual(entry["retry_count"], 1)
            self.assertEqual(entry["retry_reason"], "provider timeout")
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    def test_illegal_transitions_are_rejected(self):
        run_dir = _mk_run_dir()
        try:
            state = se.ProjectState(run_dir)
            _mk_project(run_dir)
            entry = state.begin_task(
                provider="kie", model="m", operation="generate_video", params={"s": 1},
                estimated_cost_usd=0.1,
            )
            with self.assertRaises(se.InvalidStateTransition):
                state.transition_task(entry["task_id"], "complete")  # queued -> complete is not allowed
            state.transition_task(entry["task_id"], "submitted")
            state.transition_task(entry["task_id"], "in_progress")
            state.transition_task(entry["task_id"], "complete", actual_cost_usd=0.1)
            with self.assertRaises(se.InvalidStateTransition):
                state.transition_task(entry["task_id"], "queued")  # complete is terminal
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    def test_unknown_status_rejected(self):
        run_dir = _mk_run_dir()
        try:
            state = se.ProjectState(run_dir)
            _mk_project(run_dir)
            entry = state.begin_task(
                provider="kie", model="m", operation="generate_video", params={"s": 1},
                estimated_cost_usd=0.1,
            )
            with self.assertRaises(se.InvalidStateTransition):
                state.transition_task(entry["task_id"], "bogus-status")
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    def test_completion_cost_never_double_counted_on_repeated_call(self):
        """A defensive regression test: calling transition_task(..., 'complete', ...)
        is a terminal transition, so a caller cannot invoke it twice on the
        same task — this proves the state machine itself (not just the cost
        rollup guard) prevents double-spend accounting."""
        run_dir = _mk_run_dir()
        try:
            state = se.ProjectState(run_dir)
            _mk_project(run_dir)
            entry = state.begin_task(
                provider="kie", model="m", operation="generate_video", params={"s": 1},
                estimated_cost_usd=0.1,
            )
            state.transition_task(entry["task_id"], "submitted")
            state.transition_task(entry["task_id"], "in_progress")
            state.transition_task(entry["task_id"], "complete", actual_cost_usd=0.1)
            with self.assertRaises(se.InvalidStateTransition):
                state.transition_task(entry["task_id"], "complete", actual_cost_usd=0.1)
            ledger = state.load("cost-ledger")
            self.assertAlmostEqual(ledger["cumulative_spend_usd"], 0.1, places=6)
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)


class AtomicWriteTests(unittest.TestCase):
    def test_write_then_read_roundtrip(self):
        run_dir = _mk_run_dir()
        try:
            path = run_dir / "x.json"
            se.atomic_write_json(path, {"a": 1, "b": [1, 2, 3]})
            self.assertEqual(se.read_json(path), {"a": 1, "b": [1, 2, 3]})
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    def test_no_tmp_file_left_behind_on_success(self):
        run_dir = _mk_run_dir()
        try:
            path = run_dir / "y.json"
            se.atomic_write_json(path, {"ok": True})
            leftovers = [p for p in run_dir.iterdir() if p.name != "y.json"]
            self.assertEqual(leftovers, [])
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    def test_failed_write_never_corrupts_existing_file(self):
        """Simulate a writer that dies mid-serialization (json.dump hits a
        non-serializable value partway through the object, after the
        destination path already had a good version on disk). The
        pre-existing good file must be untouched and no partial tmp file
        left behind."""
        run_dir = _mk_run_dir()
        try:
            path = run_dir / "z.json"
            se.atomic_write_json(path, {"version": 1})

            class Poison:
                """Not JSON-serializable — json.dump raises TypeError on it,
                simulating a writer that dies partway through serialization."""

            with self.assertRaises(TypeError):
                se.atomic_write_json(path, {"version": 2, "boom": Poison()})

            self.assertEqual(se.read_json(path), {"version": 1})
            leftovers = [p for p in run_dir.iterdir() if p.name != "z.json"]
            self.assertEqual(leftovers, [], f"a crashed write left a stray file behind: {leftovers}")
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    def test_stray_leftover_tmp_file_is_never_read_as_the_manifest(self):
        run_dir = _mk_run_dir()
        try:
            state = se.ProjectState(run_dir)
            manifest = _mk_project(run_dir)
            stray = run_dir / ".project-manifest.json.deadwriter123.tmp"
            stray.write_text('{"schema_version": "1.0.0", "corrupt', encoding="utf-8")
            reloaded = state.load("project-manifest")
            self.assertEqual(reloaded["project_id"], manifest["project_id"])
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)


class ProjectLockTests(unittest.TestCase):
    def test_simultaneous_writer_is_rejected(self):
        run_dir = _mk_run_dir()
        try:
            lock_a = se.ProjectLock(run_dir)
            lock_a.acquire()
            lock_b = se.ProjectLock(run_dir)
            with self.assertRaises(se.ProjectLockError):
                lock_b.acquire()
            lock_a.release()
            # after release, a fresh acquire must succeed
            lock_b.acquire()
            lock_b.release()
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    def test_stale_lock_from_dead_process_is_recovered(self):
        run_dir = _mk_run_dir()
        try:
            run_dir.mkdir(exist_ok=True)
            # Fabricate a lock held by a pid guaranteed not to be alive.
            dead_pid = 32000
            while se._pid_alive(dead_pid) and dead_pid > 2:
                dead_pid -= 1
            lock_path = run_dir / se.ProjectLock.LOCK_FILENAME
            lock_path.write_text(
                json.dumps(
                    {"pid": dead_pid, "host": "ghost", "acquired_at": "1970-01-01T00:00:00Z", "acquired_at_epoch": 0}
                ),
                encoding="utf-8",
            )
            lock = se.ProjectLock(run_dir, stale_after_seconds=900)
            lock.acquire()  # must not raise — dead-pid lock is broken automatically
            lock.release()
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    def test_live_lock_within_stale_window_is_never_broken(self):
        run_dir = _mk_run_dir()
        try:
            lock_a = se.ProjectLock(run_dir, stale_after_seconds=900)
            lock_a.acquire()
            lock_b = se.ProjectLock(run_dir, stale_after_seconds=900)
            with self.assertRaises(se.ProjectLockError):
                lock_b.acquire()  # this process's own pid IS alive; must not be broken
            lock_a.release()
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    def test_locked_mutations_actually_serialize_via_state_engine(self):
        """begin_task/transition_task acquire the lock internally; prove two
        sequential calls both land (no lost update) as a proxy for correct
        locking discipline inside ProjectState."""
        run_dir = _mk_run_dir()
        try:
            state = se.ProjectState(run_dir)
            _mk_project(run_dir)
            for i in range(5):
                state.begin_task(
                    provider="kie", model="m", operation="generate_image", params={"i": i},
                    estimated_cost_usd=0.01,
                )
            ledger = state.load("cost-ledger")
            self.assertEqual(len(ledger["entries"]), 5)
            self.assertEqual(len({e["task_id"] for e in ledger["entries"]}), 5)
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)


class InterruptionRecoveryTests(unittest.TestCase):
    """'session restart with in_progress provider jobs' (spec 19.4 break-it list)."""

    def test_recover_partitions_must_query_vs_safe_to_requeue(self):
        run_dir = _mk_run_dir()
        try:
            state = se.ProjectState(run_dir)
            _mk_project(run_dir)

            # Task A: actually reached the provider before the crash.
            a = state.begin_task(
                provider="kie", model="m", operation="generate_video", params={"s": "A"},
                estimated_cost_usd=0.2,
            )
            state.transition_task(a["task_id"], "submitted", provider_task_id="pt-A")
            state.transition_task(a["task_id"], "in_progress")

            # Task B: process died before the provider call was ever sent.
            b = state.begin_task(
                provider="kie", model="m", operation="generate_video", params={"s": "B"},
                estimated_cost_usd=0.2,
            )
            state.transition_task(b["task_id"], "submitted")  # no provider_task_id recorded
            state.transition_task(b["task_id"], "in_progress")

            # Task C: already finished before the crash — must be invisible to recovery.
            c = state.begin_task(
                provider="kie", model="m", operation="generate_video", params={"s": "C"},
                estimated_cost_usd=0.2,
            )
            state.transition_task(c["task_id"], "submitted", provider_task_id="pt-C")
            state.transition_task(c["task_id"], "in_progress")
            state.transition_task(c["task_id"], "complete", actual_cost_usd=0.2)

            report = state.recover()
            self.assertEqual(report["in_progress_count"], 2)
            must_query_ids = {e["task_id"] for e in report["must_query_provider"]}
            safe_ids = {e["task_id"] for e in report["safe_to_requeue"]}
            self.assertEqual(must_query_ids, {a["task_id"]})
            self.assertEqual(safe_ids, {b["task_id"]})
            self.assertNotIn(c["task_id"], must_query_ids | safe_ids)
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    def test_restart_never_repeats_a_completed_paid_call(self):
        """End-to-end restart simulation: build a ProjectState against a run_dir,
        complete a task, throw the in-memory object away (simulating process
        exit), build a BRAND NEW ProjectState against the same run_dir
        (simulating restart), and prove replaying the identical plan refuses
        to spend again."""
        run_dir = _mk_run_dir()
        try:
            state1 = se.ProjectState(run_dir)
            _mk_project(run_dir)
            entry = state1.begin_task(
                provider="kie", model="gpt-image-2-image-to-image", operation="generate_image",
                params={"scene_id": "scene-01", "ref": "anchor.png"}, estimated_cost_usd=0.03,
            )
            state1.transition_task(entry["task_id"], "submitted", provider_task_id="pt-Z")
            state1.transition_task(entry["task_id"], "in_progress")
            state1.transition_task(entry["task_id"], "complete", actual_cost_usd=0.03)
            del state1  # simulate process exit

            state2 = se.ProjectState(run_dir)  # simulate restart: fresh object, same run_dir
            with self.assertRaises(se.IdempotencyViolation):
                state2.begin_task(
                    provider="kie", model="gpt-image-2-image-to-image", operation="generate_image",
                    params={"scene_id": "scene-01", "ref": "anchor.png"}, estimated_cost_usd=0.03,
                )
            ledger = state2.load("cost-ledger")
            self.assertEqual(len(ledger["entries"]), 1)
            self.assertAlmostEqual(ledger["cumulative_spend_usd"], 0.03, places=6)
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    def test_recover_after_kill_9_style_interruption_via_subprocess(self):
        """A REAL interruption: spawn a subprocess that begins a task, marks it
        in_progress, and then hard-exits via os._exit() (no cleanup, no atexit,
        the closest a same-machine test can get to kill -9). The lock file
        must not still be held by a live process afterward, and the parent
        must be able to acquire the lock and read a consistent, schema-valid
        in_progress task back out — proving restart-after-crash recovery
        against a real OS-level process death, not just an in-process
        `del`/simulated crash."""
        run_dir = _mk_run_dir()
        try:
            _mk_project(run_dir)
            child_script = f"""
import sys
sys.path.insert(0, {str(HERE)!r})
sys.path.insert(0, {str(HERE / "lib")!r})
import state_engine as se
state = se.ProjectState({str(run_dir)!r})
entry = state.begin_task(
    provider="kie", model="m", operation="generate_video", params={{"s": "crash-me"}},
    estimated_cost_usd=0.15,
)
state.transition_task(entry["task_id"], "submitted", provider_task_id="pt-crash")
state.transition_task(entry["task_id"], "in_progress")
sys.stdout.flush()
import os
os._exit(9)
"""
            proc = subprocess.run([sys.executable, "-c", child_script], capture_output=True, text=True, timeout=30)
            self.assertEqual(proc.returncode, 9, f"child did not exit as expected: {proc.stdout} {proc.stderr}")

            # The child released its lock cleanly during transition_task's own
            # __exit__ calls (each locked call acquires+releases per-operation),
            # so no stale lock should even be present. Prove the parent can
            # still acquire the lock either way (covers both cases).
            lock = se.ProjectLock(run_dir, stale_after_seconds=5)
            lock.acquire()
            lock.release()

            state = se.ProjectState(run_dir)
            report = state.recover()
            self.assertEqual(report["in_progress_count"], 1)
            self.assertEqual(len(report["must_query_provider"]), 1)
            self.assertEqual(report["must_query_provider"][0]["provider_task_id"], "pt-crash")

            # And the manifest/ledger on disk are still schema-valid (atomic
            # writes mean the last COMPLETED write always wins, never a
            # partial one, even though the child was hard-killed).
            ledger = state.load("cost-ledger")
            manifest = state.load("project-manifest")
            self.assertEqual(len(ledger["entries"]), 1)
            self.assertEqual(len(manifest["tasks"]), 1)
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)


class SelfTestEntryPointTest(unittest.TestCase):
    """Prove the module's own --self-test CLI entry point (used by the entry
    shell's self-test convention elsewhere in this skill) actually runs and
    exits 0."""

    def test_state_engine_self_test_cli_exits_zero(self):
        proc = subprocess.run(
            [sys.executable, str(HERE / "state_engine.py"), "--self-test"],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(proc.returncode, 0, f"stdout={proc.stdout}\nstderr={proc.stderr}")
        self.assertIn("RESULT: PASS", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
