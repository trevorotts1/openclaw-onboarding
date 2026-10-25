#!/usr/bin/env python3
"""Tests for bootstrap_engine.py (T-36, idempotent setup and permitted provisioning).

The suite proves the doctrine, not just the plumbing: a plan writes nothing,
a second run is a byte-identical no-op, an unpermitted resource is refused with
a named reason and never appears in the provisioned set, an interrupted run
resumes from the failed step without duplicating a created resource, and a
partially failed run leaves a resumable receipt state on disk. A real child
interpreter is hard-killed at every write boundary to prove a created object is
never left without its receipt, and two real concurrent runs prove a resource is
never created twice and no receipt is lost.

Run from the skill root:
  python3 -m unittest discover -s tools/tests -p 'test_*.py'
or:
  python3 tools/tests/test_bootstrap_engine.py
"""

import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))

import bootstrap_engine as be  # noqa: E402

FIXED_NOW = datetime.datetime(
    2026, 10, 24, 12, 0, 0, 0, tzinfo=datetime.timezone.utc
)


def fixed_clock():
    return FIXED_NOW


def spec(resource_id, kind="knowledgebase", path=None, payload="payload", adopt=False):
    return be.ResourceSpec(
        resource_id=resource_id,
        kind=kind,
        path=path if path is not None else resource_id.replace(".", "/") + ".txt",
        payload=payload,
        adopt_existing=adopt,
    )


def tree_digest(root):
    digest = hashlib.sha256()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root)
            digest.update(rel.encode("utf-8"))
            digest.update(b"\0")
            with open(full, "rb") as handle:
                digest.update(handle.read())
            digest.update(b"\0")
    return digest.hexdigest()


def read(path):
    with open(path, "rb") as handle:
        return handle.read()


# Child driver for the crash and concurrency tests: a real second interpreter,
# so os._exit in it is a hard kill of a real run, not a simulated one. argv:
# tools dir, target root, kill-at write-call (0 = never), specs JSON, go file.
CHILD_RUN = r"""
import json, os, sys, time
tools, root, kill_at, rows, go = (sys.argv[1], sys.argv[2], int(sys.argv[3]),
                                 json.loads(sys.argv[4]), sys.argv[5])
sys.path.insert(0, tools)
import bootstrap_engine as be

specs = [be.ResourceSpec(r[0], "knowledgebase", r[1], r[2]) for r in rows]
if kill_at:
    real = be._atomic_write
    count = {"n": 0}
    def gated(path, data, mode=None):
        count["n"] += 1
        if count["n"] == kill_at:
            os._exit(9)  # hard kill: no flush, no cleanup, no last words
        return real(path, data, mode)
    be._atomic_write = gated
if go:
    deadline = time.time() + 30
    while not os.path.exists(go) and time.time() < deadline:
        time.sleep(0.002)
engine = be.BootstrapEngine(root, permissions=("kind:knowledgebase",))
report = engine.run(specs)
print(json.dumps({
    "created": [c["resource_id"] for c in report.created],
    "adopted": [a["resource_id"] for a in report.adopted],
    "blocked": [b["resource_id"] for b in report.blocked],
    "failed": [f["resource_id"] for f in report.failed],
}))
"""

# Three resources -> six write calls (write-ahead receipt, then artifact).
CRASH_ROWS = [
    ["kb.one", "kb/one.txt", "one"],
    ["kb.two", "kb/two.txt", "two"],
    ["kb.three", "kb/three.txt", "three"],
]


def child(root, kill_at=0, rows=CRASH_ROWS, go=""):
    return subprocess.run(
        [sys.executable, "-I", "-c", CHILD_RUN, str(TOOLS_DIR), root,
         str(kill_at), json.dumps(rows), go],
        capture_output=True, text=True, timeout=60,
    )


def specs_from(rows):
    return [be.ResourceSpec(r[0], "knowledgebase", r[1], r[2]) for r in rows]


def receipts_of(root):
    path = os.path.join(root, ".bootstrap-state.json")
    if not os.path.exists(path):
        return {}
    return json.loads(read(path).decode("utf-8"))["receipts"]


def tree_files(root):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            if name.startswith(".bootstrap-state"):
                continue
            out.append(os.path.relpath(os.path.join(dirpath, name), root))
    return sorted(out)


class EngineTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="pbb-bootstrap-test-")
        self.root = self.tmp.name
        self.addCleanup(self.tmp.cleanup)

    def engine(self, permissions, **kwargs):
        return be.BootstrapEngine(
            self.root, permissions=permissions, clock=fixed_clock, **kwargs
        )


class IdempotencyTests(EngineTestCase):
    def test_first_run_creates_only_permitted_resources(self):
        engine = self.engine(("kb.one", "kind:journey_template"))
        report = engine.run(
            [
                spec("kb.one"),
                spec("jt.one", kind="journey_template"),
                spec("wf.one", kind="workflow"),
            ]
        )
        self.assertEqual(sorted(i["resource_id"] for i in report.created), ["jt.one", "kb.one"])
        self.assertTrue(os.path.isfile(os.path.join(self.root, "kb/one.txt")))
        self.assertTrue(os.path.isfile(os.path.join(self.root, "jt/one.txt")))
        self.assertFalse(os.path.exists(os.path.join(self.root, "wf/one.txt")))

    def test_plan_writes_nothing(self):
        engine = self.engine(("kb.one",))
        plan = engine.plan([spec("kb.one")])
        self.assertEqual([s.action for s in plan.steps], [be.ACTION_CREATE])
        self.assertFalse(os.path.exists(engine.state_path))
        self.assertFalse(os.path.exists(os.path.join(self.root, "kb")))

    def test_second_run_is_a_byte_identical_noop(self):
        engine = self.engine(("kb.one", "kind:journey_template"))
        specs = [spec("kb.one"), spec("jt.one", kind="journey_template")]
        engine.run(specs)

        state_before = read(engine.state_path)
        tree_before = tree_digest(self.root)
        mtimes_before = {
            rel: os.stat(os.path.join(self.root, rel)).st_mtime_ns
            for rel in ("kb/one.txt", "jt/one.txt")
        }

        second = engine.run(specs)

        self.assertEqual(second.created, [])
        self.assertEqual(second.adopted, [])
        self.assertEqual(
            sorted(i["resource_id"] for i in second.unchanged), ["jt.one", "kb.one"]
        )
        self.assertFalse(second.state_written)
        self.assertEqual(read(engine.state_path), state_before)
        self.assertEqual(tree_digest(self.root), tree_before)
        for rel, before in mtimes_before.items():
            self.assertEqual(os.stat(os.path.join(self.root, rel)).st_mtime_ns, before)

    def test_plan_and_run_agree_on_actions(self):
        engine = self.engine(("kb.one",))
        specs = [spec("kb.one"), spec("wf.one", kind="workflow")]
        planned = [s.action for s in engine.plan(specs).steps]
        engine.run(specs)
        # After the run the same inputs plan to unchanged/skip, exactly what
        # the run reported for the already-satisfied resources.
        self.assertEqual(planned, [be.ACTION_CREATE, be.ACTION_SKIP])
        self.assertEqual(
            [s.action for s in engine.plan(specs).steps],
            [be.ACTION_NOOP, be.ACTION_SKIP],
        )

    def test_missing_artifact_is_restored_without_a_second_receipt(self):
        engine = self.engine(("kb.one",))
        engine.run([spec("kb.one")])
        os.unlink(os.path.join(self.root, "kb/one.txt"))

        restored = engine.run([spec("kb.one")])
        self.assertEqual([i["resource_id"] for i in restored.created], ["kb.one"])
        self.assertEqual(read(os.path.join(self.root, "kb/one.txt")), b"payload")
        state = json.loads(read(engine.state_path).decode("utf-8"))
        self.assertEqual(list(state["receipts"]), ["kb.one"])

    def test_no_temp_files_are_left_behind(self):
        engine = self.engine(("kb.one",))
        engine.run([spec("kb.one")])
        leftovers = [
            name for name in os.listdir(os.path.join(self.root, "kb"))
            if name.startswith(".bootstrap-")
        ]
        self.assertEqual(leftovers, [])


class PermissionTests(EngineTestCase):
    def test_unpermitted_resource_is_skipped_with_a_named_reason(self):
        engine = self.engine(())
        report = engine.run([spec("kb.one")])
        self.assertEqual(report.created, [])
        self.assertEqual(report.provisioned, [])
        self.assertEqual(report.skipped[0]["reason"], be.REASON_NOT_PERMITTED)
        self.assertIn("kb.one", report.skipped[0]["detail"])
        self.assertFalse(os.path.exists(os.path.join(self.root, "kb/one.txt")))

    def test_permission_may_be_granted_by_kind(self):
        engine = self.engine(("kind:journey_template",))
        report = engine.run([spec("jt.one", kind="journey_template")])
        self.assertEqual([i["resource_id"] for i in report.created], ["jt.one"])

    def test_never_permitted_kinds_are_refused_even_when_named(self):
        for kind in sorted(be.NEVER_PERMITTED_KINDS):
            with self.subTest(kind=kind):
                engine = self.engine((kind, "kind:" + kind, "x." + kind))
                report = engine.run([spec("x." + kind, kind=kind)])
                self.assertEqual(report.created, [])
                self.assertEqual(report.refused[0]["reason"], be.REASON_NEVER_PERMITTED)
                self.assertNotIn("x." + kind, report.provisioned)
                self.assertFalse(
                    os.path.exists(os.path.join(self.root, ("x." + kind).replace(".", "/") + ".txt"))
                )

    def test_blank_permission_entries_are_rejected(self):
        with self.assertRaises(be.BootstrapPermissionError):
            be.BootstrapEngine(self.root, permissions=("",))

    def test_skipped_resources_never_appear_as_provisioned(self):
        engine = self.engine(("kb.one",))
        report = engine.run([spec("kb.one"), spec("wf.one", kind="workflow")])
        self.assertNotIn("wf.one", report.provisioned)
        self.assertIn("wf.one", [i["resource_id"] for i in report.skipped])


class OwnerHandoffTests(EngineTestCase):
    def _preexisting(self, relpath, data):
        path = os.path.join(self.root, relpath)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(data)
        return path

    def test_matching_unowned_object_requires_handoff_and_is_untouched(self):
        path = self._preexisting("kb/one.txt", b"payload")
        before = os.stat(path).st_mtime_ns
        engine = self.engine(("kb.one",))
        report = engine.run([spec("kb.one")])
        self.assertEqual(report.created, [])
        self.assertEqual(report.blocked[0]["reason"], be.REASON_OWNER_HANDOFF)
        self.assertEqual(path and read(path), b"payload")
        self.assertEqual(os.stat(path).st_mtime_ns, before)
        self.assertFalse(os.path.exists(engine.state_path))

    def test_adoption_reuses_matching_bytes_without_rewriting(self):
        path = self._preexisting("kb/one.txt", b"payload")
        inode_before = os.stat(path).st_ino
        mtime_before = os.stat(path).st_mtime_ns
        engine = self.engine(("kb.one",))
        report = engine.run([spec("kb.one", adopt=True)])
        self.assertEqual([i["resource_id"] for i in report.adopted], ["kb.one"])
        self.assertEqual(os.stat(path).st_ino, inode_before)
        self.assertEqual(os.stat(path).st_mtime_ns, mtime_before)
        self.assertEqual(read(path), b"payload")
        # A second run is still a no-op after adoption.
        self.assertFalse(engine.run([spec("kb.one", adopt=True)]).state_written)

    def test_differing_unowned_object_is_never_overwritten(self):
        path = self._preexisting("kb/one.txt", b"client hand edit")
        engine = self.engine(("kb.one",))
        report = engine.run([spec("kb.one", adopt=True)])
        self.assertEqual(report.blocked[0]["reason"], be.REASON_TARGET_UNOWNED)
        self.assertEqual(read(path), b"client hand edit")

    def test_owned_content_drift_blocks_instead_of_overwriting(self):
        engine = self.engine(("kb.one",))
        engine.run([spec("kb.one")])
        path = os.path.join(self.root, "kb/one.txt")
        with open(path, "wb") as handle:
            handle.write(b"hand edit")
        state_before = read(engine.state_path)

        report = engine.run([spec("kb.one")])
        self.assertEqual(report.blocked[0]["reason"], be.REASON_CONTENT_DRIFT)
        self.assertEqual(read(path), b"hand edit")
        self.assertEqual(read(engine.state_path), state_before)

    def test_changed_spec_payload_blocks_instead_of_rewriting(self):
        engine = self.engine(("kb.one",))
        engine.run([spec("kb.one", payload="v1")])
        report = engine.run([spec("kb.one", payload="v2")])
        self.assertEqual(report.blocked[0]["reason"], be.REASON_CONTENT_DRIFT)
        self.assertEqual(read(os.path.join(self.root, "kb/one.txt")), b"v1")


@unittest.skipIf(os.geteuid() == 0, "permission failure needs a non-root user")
class ResumeTests(EngineTestCase):
    def _interrupted_engine(self):
        engine = self.engine(("kind:knowledgebase",))
        engine.run([spec("kb.first")])
        blocked_dir = os.path.join(self.root, "kb")
        os.chmod(blocked_dir, 0o500)
        self.addCleanup(os.chmod, blocked_dir, 0o700)
        specs = [
            spec("kb.second", payload="two"),
            spec("kb.third", payload="three"),
            spec("kb.fourth", payload="four"),
        ]
        return engine, specs, blocked_dir

    def test_failed_step_is_reported_and_state_stays_resumable(self):
        engine, specs, blocked_dir = self._interrupted_engine()
        report = engine.run(specs)
        self.assertEqual(len(report.failed), 1)
        self.assertEqual(report.failed[0]["reason"], be.REASON_WRITE_FAILED)
        self.assertEqual(
            [i["resource_id"] for i in report.not_attempted], ["kb.third", "kb.fourth"]
        )
        os.chmod(blocked_dir, 0o700)
        state = json.loads(read(engine.state_path).decode("utf-8"))
        # Only the resource created before the failure has a receipt.
        self.assertEqual(sorted(state["receipts"]), ["kb.first"])

    def test_resume_continues_without_duplicating_a_created_resource(self):
        engine, specs, blocked_dir = self._interrupted_engine()
        engine.run(specs)
        first_path = os.path.join(self.root, "kb/first.txt")
        first_bytes = read(first_path)
        first_mtime = os.stat(first_path).st_mtime_ns
        os.chmod(blocked_dir, 0o700)

        resumed = engine.run(specs)
        self.assertEqual(
            [i["resource_id"] for i in resumed.created], ["kb.second", "kb.third", "kb.fourth"]
        )
        self.assertEqual(read(first_path), first_bytes)
        self.assertEqual(os.stat(first_path).st_mtime_ns, first_mtime)
        state = json.loads(read(engine.state_path).decode("utf-8"))
        self.assertEqual(
            sorted(state["receipts"]),
            ["kb.first", "kb.fourth", "kb.second", "kb.third"],
        )
        # Every resource is created exactly once, at its exact path.
        for resource_id in ("kb.first", "kb.second", "kb.third", "kb.fourth"):
            relpath = resource_id.replace(".", "/") + ".txt"
            self.assertTrue(os.path.isfile(os.path.join(self.root, relpath)))

    def test_resume_is_a_noop_once_complete(self):
        engine, specs, blocked_dir = self._interrupted_engine()
        engine.run(specs)
        os.chmod(blocked_dir, 0o700)
        engine.run(specs)
        tree_before = tree_digest(self.root)
        state_before = read(engine.state_path)
        final = engine.run(specs)
        self.assertEqual(final.created, [])
        self.assertFalse(final.state_written)
        self.assertEqual(tree_digest(self.root), tree_before)
        self.assertEqual(read(engine.state_path), state_before)

    def test_stop_on_failure_false_attempts_every_step(self):
        engine, specs, blocked_dir = self._interrupted_engine()
        report = engine.run(specs, stop_on_failure=False)
        # Every step is attempted; all three land in the unwritable directory
        # and each failure is reported by name.
        self.assertEqual(
            [i["resource_id"] for i in report.failed],
            ["kb.second", "kb.third", "kb.fourth"],
        )
        self.assertEqual(report.not_attempted, [])
        os.chmod(blocked_dir, 0o700)


class ValidationTests(EngineTestCase):
    def test_duplicate_resource_ids_are_rejected(self):
        engine = self.engine(("kb.one",))
        with self.assertRaises(be.BootstrapError):
            engine.plan([spec("kb.one"), spec("kb.one", path="other.txt")])

    def test_duplicate_paths_are_rejected(self):
        engine = self.engine(("kb.one", "kb.two"))
        with self.assertRaises(be.BootstrapError):
            engine.plan([spec("kb.one", path="same.txt"), spec("kb.two", path="same.txt")])

    def test_absolute_and_parent_paths_are_rejected(self):
        engine = self.engine(("kb.one",))
        for bad in ("/etc/passwd", "~/file", "../escape.txt", "a/../../escape.txt"):
            with self.subTest(path=bad):
                with self.assertRaises(be.BootstrapError):
                    engine.plan([spec("kb.one", path=bad)])

    def test_symlink_escape_is_refused_and_writes_outside_root(self):
        outside = tempfile.mkdtemp(prefix="pbb-bootstrap-outside-")
        self.addCleanup(lambda: __import__("shutil").rmtree(outside, ignore_errors=True))
        os.symlink(outside, os.path.join(self.root, "escape"))
        engine = self.engine(("kb.one",))
        report = engine.run([spec("kb.one", path="escape/one.txt")])
        self.assertEqual(report.refused[0]["reason"], be.REASON_PATH_ESCAPE)
        self.assertFalse(os.path.exists(os.path.join(outside, "one.txt")))

    def test_corrupt_state_fails_closed(self):
        engine = self.engine(("kb.one",))
        with open(engine.state_path, "wb") as handle:
            handle.write(b"{not json")
        with self.assertRaises(be.BootstrapError):
            engine.run([spec("kb.one")])
        self.assertFalse(os.path.exists(os.path.join(self.root, "kb/one.txt")))

    def test_unknown_state_schema_fails_closed(self):
        engine = self.engine(("kb.one",))
        with open(engine.state_path, "wb") as handle:
            handle.write(json.dumps({"schema": "other", "receipts": {}}).encode("utf-8"))
        with self.assertRaises(be.BootstrapError):
            engine.run([spec("kb.one")])

    def test_missing_target_root_is_created_on_first_write(self):
        nested = os.path.join(self.root, "deep", "root")
        engine = be.BootstrapEngine(
            nested, permissions=("kb.one",), clock=fixed_clock
        )
        report = engine.run([spec("kb.one")])
        self.assertEqual([i["resource_id"] for i in report.created], ["kb.one"])


class DiscoveryTests(EngineTestCase):
    def test_discover_reports_owned_state_and_digest(self):
        engine = self.engine(("kb.one", "kb.two"))
        engine.run([spec("kb.one")])
        found = engine.discover([spec("kb.one"), spec("kb.two")])
        one = found["resources"]["kb.one"]
        two = found["resources"]["kb.two"]
        self.assertTrue(one["exists"])
        self.assertTrue(one["owned"])
        self.assertTrue(one["matches_spec"])
        self.assertFalse(two["exists"])
        self.assertFalse(two["owned"])

    def test_discover_sees_an_unowned_object_without_claiming_it(self):
        path = os.path.join(self.root, "kb", "one.txt")
        os.makedirs(os.path.dirname(path))
        with open(path, "wb") as handle:
            handle.write(b"payload")
        engine = self.engine(("kb.one",))
        found = engine.discover([spec("kb.one")])["resources"]["kb.one"]
        self.assertTrue(found["exists"])
        self.assertFalse(found["owned"])
        self.assertTrue(found["matches_spec"])


class IsolationTests(EngineTestCase):
    def test_module_has_no_network_or_shell_path(self):
        # The strings below are scan needles, never executed: this test asserts
        # the provisioning module contains no network or shell sink at all.
        source = (TOOLS_DIR / "bootstrap_engine.py").read_text(encoding="utf-8")
        for forbidden in (
            "import socket", "import ssl", "import subprocess", "import urllib",
            "import http", "import requests", "os.system(", "os.popen(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)
        self.assertFalse(be.TRAFFIC_AUTHORIZED)

    def test_module_self_check_runs(self):
        result = subprocess.run(
            [sys.executable, "-I", str(TOOLS_DIR / "bootstrap_engine.py")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("self-check: OK", result.stdout)


class CrashDurabilityTests(EngineTestCase):
    """A hard kill can never leave a created object unrecorded (PBB-081)."""

    @staticmethod
    def engine_at(root):
        return be.BootstrapEngine(
            root, permissions=("kind:knowledgebase",), clock=fixed_clock
        )

    def test_hard_kill_at_every_write_boundary_leaves_no_unrecorded_artifact(self):
        # Six write calls: a write-ahead receipt and its artifact per step. A
        # real child is killed before call 1..6; every surviving artifact must
        # already have a receipt, and a resume must continue without blocking,
        # without adoption and without recreating anything on disk.
        for kill_at in range(1, 2 * len(CRASH_ROWS) + 1):
            with self.subTest(kill_at=kill_at):
                root = tempfile.mkdtemp(prefix="pbb-bootstrap-crash-")
                self.addCleanup(shutil.rmtree, root, True)
                proc = child(root, kill_at=kill_at)
                self.assertEqual(proc.returncode, 9, proc.stderr)

                on_disk = tree_files(root)
                recorded_paths = {v["path"] for v in receipts_of(root).values()}
                self.assertEqual(
                    [r for r in on_disk if r not in recorded_paths], [],
                    "a created object was left without its receipt",
                )
                survived = {
                    rel: (read(os.path.join(root, rel)),
                          os.stat(os.path.join(root, rel)).st_mtime_ns)
                    for rel in on_disk
                }
                missing = [r[0] for r in CRASH_ROWS if r[1] not in on_disk]

                engine = self.engine_at(root)
                resumed = engine.run(specs_from(CRASH_ROWS))
                self.assertEqual(resumed.blocked, [])
                self.assertEqual(resumed.failed, [])
                self.assertEqual(resumed.adopted, [])
                self.assertEqual(
                    sorted(i["resource_id"] for i in resumed.created), sorted(missing)
                )
                for rel, (body, mtime) in survived.items():
                    self.assertEqual(read(os.path.join(root, rel)), body)
                    self.assertEqual(
                        os.stat(os.path.join(root, rel)).st_mtime_ns, mtime
                    )
                self.assertEqual(
                    sorted(receipts_of(root)), ["kb.one", "kb.three", "kb.two"]
                )
                for row in CRASH_ROWS:
                    self.assertEqual(read(os.path.join(root, row[1])), row[2].encode())

                # It settles: the next run is a byte-identical no-op.
                tree_before = tree_digest(root)
                state_before = read(engine.state_path)
                again = engine.run(specs_from(CRASH_ROWS))
                self.assertEqual(again.created, [])
                self.assertFalse(again.state_written)
                self.assertEqual(tree_digest(root), tree_before)
                self.assertEqual(read(engine.state_path), state_before)


class ConcurrencyTests(EngineTestCase):
    """Two runs at once never duplicate a resource and never lose a receipt."""

    def _run_two(self, rows_a, rows_b):
        go_fd, go = tempfile.mkstemp(prefix="pbb-bootstrap-go-")
        os.close(go_fd)
        os.unlink(go)
        self.addCleanup(lambda: os.path.exists(go) and os.unlink(go))
        args = lambda rows: [  # noqa: E731 - one-shot arg builder
            sys.executable, "-I", "-c", CHILD_RUN, str(TOOLS_DIR), self.root,
            "0", json.dumps(rows), go,
        ]
        first = subprocess.Popen(
            args(rows_a), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        second = subprocess.Popen(
            args(rows_b), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        with open(go, "wb") as handle:
            handle.write(b"go")
        out_a, err_a = first.communicate(timeout=60)
        out_b, err_b = second.communicate(timeout=60)
        self.assertEqual(first.returncode, 0, err_a)
        self.assertEqual(second.returncode, 0, err_b)
        return json.loads(out_a), json.loads(out_b)

    def test_two_concurrent_runs_never_create_a_resource_twice(self):
        run_a, run_b = self._run_two(CRASH_ROWS, CRASH_ROWS)
        created_total = len(run_a["created"]) + len(run_b["created"])
        self.assertEqual(created_total, len(CRASH_ROWS))
        self.assertEqual(run_a["blocked"], [])
        self.assertEqual(run_b["blocked"], [])
        self.assertEqual(tree_files(self.root), sorted(r[1] for r in CRASH_ROWS))
        self.assertEqual(
            sorted(receipts_of(self.root)), ["kb.one", "kb.three", "kb.two"]
        )

    def test_concurrent_runs_with_different_specs_lose_no_receipts(self):
        rows_x = [["x.one", "x/one.txt", "one"], ["x.two", "x/two.txt", "two"]]
        rows_y = [["y.one", "y/one.txt", "uno"], ["y.two", "y/two.txt", "dos"]]
        run_a, run_b = self._run_two(rows_x, rows_y)
        self.assertEqual(len(run_a["created"]) + len(run_b["created"]), 4)
        self.assertEqual(
            sorted(receipts_of(self.root)),
            ["x.one", "x.two", "y.one", "y.two"],
        )
        self.assertEqual(
            tree_files(self.root),
            ["x/one.txt", "x/two.txt", "y/one.txt", "y/two.txt"],
        )

    def test_run_refuses_when_another_run_holds_the_state_lock(self):
        engine = self.engine(("kb.one",), lock_timeout=0.2)
        with be._StateLock(engine.lock_path, 1.0):
            with self.assertRaises(be.BootstrapError) as caught:
                engine.run([spec("kb.one")])
        self.assertIn("lock", str(caught.exception))
        self.assertFalse(os.path.exists(os.path.join(self.root, "kb/one.txt")))
        self.assertFalse(os.path.exists(engine.state_path))
        # Once the other run is done, the same call goes through.
        report = engine.run([spec("kb.one")])
        self.assertEqual([i["resource_id"] for i in report.created], ["kb.one"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
