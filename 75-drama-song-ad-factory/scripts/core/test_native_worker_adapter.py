#!/usr/bin/env python3
"""Tests for native_worker_adapter (Skill 75 T11 / X01-X04). stdlib only, no network.

Run: python3 scripts/core/test_native_worker_adapter.py

Ported from the T11 behavioural battery and the 35-check install probe, keeping
every check that is self-contained: synthetic journals in a temp dir, the pure
worker frontier, persist, the refused control verbs and the import bound. Dropped:
checks bound to operator-box files (live settings, real host journals, lane
digests, scope manifest) -- they cannot run on a clean box and are not about
this module's behaviour.

Key regression: a READY unit overlapping an ACTIVE unit must be excluded
PATH_COLLISION_ACTIVE (the pre-fix frontier selected it).
"""
import ast
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import native_worker_adapter as NWA  # noqa: E402

MODULE = os.path.join(HERE, "native_worker_adapter.py")
VERBS = ("launch", "steer", "pause", "cancel", "reconcile", "resume")


def R(name, paths, **kw):
    return dict({"unit": name, "state": "ready", "owned_paths": paths}, **kw)


def A(name, paths, state="running"):
    return {"unit": name, "state": state, "owned_paths": paths}


def pick(units, cap=None):
    out = NWA.worker_frontier(units, cap)
    return ([s["unit"] for s in out["selected"]],
            [(e["unit"], e["reason"]) for e in out["excluded"]])


class Frontier(unittest.TestCase):
    def test_ready_vs_active_overlap_excluded(self):
        want = ([], [("act", "WAIT_STATE"), ("r", "PATH_COLLISION_ACTIVE")])
        self.assertEqual(pick([A("act", ["x"]), R("r", ["x"])]), want)
        self.assertEqual(pick([A("act", ["x/y"]), R("r", ["x"])]), want)
        self.assertEqual(pick([A("act", ["x"]), R("r", ["x/y"])]), want)

    def test_every_active_state_blocks(self):
        for st in ("running", "started", "in_progress", "claimed", "active"):
            self.assertEqual(pick([A("act", ["x"], st), R("r", ["x"])])[0], [], st)

    def test_active_disjoint_and_prefix_not_boundary(self):
        self.assertEqual(pick([A("act", ["y"]), R("r", ["x"])])[0], ["r"])
        self.assertEqual(pick([A("act", ["x"]), R("r", ["xy"])])[0], ["r"])

    def test_ready_vs_ready(self):
        self.assertEqual(pick([R("a", ["x"]), R("b", ["x"])]),
                         (["a"], [("b", "PATH_COLLISION_SELECTED")]))
        self.assertEqual(pick([R("a", ["x"]), R("b", ["x/z"])]),
                         (["a"], [("b", "PATH_COLLISION_SELECTED")]))
        self.assertEqual(pick([R("a", ["x/z"]), R("b", ["x"])]),
                         (["a"], [("b", "PATH_COLLISION_SELECTED")]))
        self.assertEqual(pick([R("a", ["x"]), R("b", ["y"])]), (["a", "b"], []))

    def test_capacity(self):
        self.assertEqual(pick([R("a", ["x"]), R("b", ["y"])], 1),
                         (["a"], [("b", "CAPACITY")]))
        self.assertEqual(pick([R("a", ["x"]), R("b", ["y"]), R("c", ["z"])], 2)[0],
                         ["a", "b"])

    def test_dependencies(self):
        self.assertEqual(pick([R("a", ["x"], depends_on=["q"])]), ([], [("a", "WAIT_DEP")]))
        self.assertEqual(pick([A("q", ["w"]), R("a", ["x"], depends_on=["q"])])[0], [])
        self.assertEqual(pick([A("q", ["w"], "done"), R("a", ["x"], depends_on=["q"])])[0],
                         ["a"])
        # a resolved unit holds no path
        self.assertEqual(pick([A("q", ["x"], "done"), R("a", ["x"])])[0], ["a"])

    def test_path_normalisation(self):
        self.assertEqual(pick([A("act", ["./x/"]), R("r", ["x/y"])])[0], [])
        self.assertEqual(pick([A("act", ["x\\y"]), R("r", ["x"])])[0], [])

    def test_active_active_collision_recorded(self):
        out = NWA.worker_frontier([A("a", ["x"]), A("b", ["x/y"])])
        self.assertEqual(out["selected"], [])
        self.assertEqual(out["collisions"],
                         [{"units": ["a", "b"], "reason": "PATH_COLLISION_ACTIVE"}])

    def test_empty_and_invalid(self):
        self.assertEqual(pick([]), ([], []))
        for bad in ([R("a", [""])], [{"unit": "a"}, {"unit": "a"}], "x"):
            with self.assertRaises(NWA.RecordError):
                NWA.worker_frontier(bad)
        with self.assertRaises(NWA.RecordError) as cm:
            NWA.worker_frontier([R("dup", ["a"]), R("dup", ["b"])])
        self.assertEqual((cm.exception.code, cm.exception.message),
                         ("INVALID_UNIT", "duplicate unit id: dup"))


class Records(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="nwa-test-")
        self.tmp = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def mkrun(self, name, events, meta=None):
        d = os.path.join(self.tmp, name)
        os.makedirs(d)
        with open(os.path.join(d, "journal.jsonl"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(json.dumps(e) for e in events) + "\n")
        for agent, body in (meta or {}).items():
            with open(os.path.join(d, "agent-%s.meta.json" % agent), "w",
                      encoding="utf-8") as fh:
                json.dump(body, fh)
        return d

    def err(self, d):
        with self.assertRaises(NWA.RecordError) as cm:
            NWA.read_run(d, None)
        return cm.exception.code, cm.exception.message

    def test_complete_run_shape(self):
        d = self.mkrun("wf-a", [
            {"type": "launched"},
            {"type": "started", "key": "k1", "agentId": "a1", "label": "L", "phase": "P"},
            {"type": "started", "key": "k2", "agentId": "a2"},
            {"type": "result", "key": "k1", "agentId": "a1", "result": "done"},
            {"type": "result", "key": "k2", "agentId": "a2", "result": "done"}],
            {"a1": {"model": "model-one"}, "a2": {"model": "model-two"}})
        run = NWA.read_run(d, None)
        self.assertEqual(run["state"], "COMPLETE")
        self.assertEqual((run["started_count"], run["result_count"], run["launched_events"]),
                         (2, 2, 1))
        self.assertEqual(run["journal_sha256"],
                         NWA.sha256_file(os.path.join(d, "journal.jsonl")))
        self.assertEqual(sorted(w["route"]["requested_model"] for w in run["workers"]),
                         ["model-one", "model-two"])
        # served route is never inferred from the requested model
        self.assertEqual([w["route"]["served_status"] for w in run["workers"]],
                         ["UNAVAILABLE_SERVED_ROUTE"] * 2)
        self.assertEqual([w["result"]["nonempty"] for w in run["workers"]], [True, True])

    def test_served_route_maps(self):
        d = self.mkrun("r-flat", [
            {"type": "started", "key": "k1", "agentId": "a1"},
            {"type": "result", "key": "k1", "agentId": "a1", "result": "done"}],
            {"a1": {"model": "model-one"}})
        route = NWA.read_run(d, {"r-flat/a1": "served-z"})["workers"][0]["route"]
        self.assertEqual((route["served_model"], route["served_status"], route["served_source"]),
                         ("served-z", "RECORDED", "route-map-flat"))
        route = NWA.read_run(d, {"runs": {"r-flat": {"agents": {"a1": "served-n"}}}}
                             )["workers"][0]["route"]
        self.assertEqual((route["served_model"], route["served_source"]),
                         ("served-n", "route-map-runs"))

    def test_invalid_records(self):
        s1 = {"type": "started", "key": "k1", "agentId": "a1"}
        cases = [
            ([s1, {"type": "result", "key": "k1", "agentId": "a1", "result": ""}],
             ("INVALID_RECORD", "empty/non-string result for k1")),
            ([s1, {"type": "result", "key": "k1", "agentId": "a1", "result": "a"},
              {"type": "result", "key": "k1", "agentId": "a1", "result": "b"}],
             ("INVALID_RECORD", "duplicate result key: k1")),
            ([{"type": "result", "key": "k9", "agentId": "a1", "result": "x"}],
             ("INVALID_RECORD", "result without started key: 'k9'")),
            ([s1, {"type": "result", "key": "k1", "agentId": "a2", "result": "x"}],
             ("INVALID_RECORD", "result agent mismatch for key: k1")),
            ([s1, {"type": "started", "key": "k2", "agentId": "a1"}],
             ("INVALID_RECORD", "duplicate started agentId: a1")),
            ([s1, {"type": "started", "key": "k1", "agentId": "a2"}],
             ("INVALID_RECORD", "duplicate started key: k1")),
        ]
        for i, (events, want) in enumerate(cases):
            self.assertEqual(self.err(self.mkrun("bad-%d" % i, events)), want)

    def test_missing_journal_and_states(self):
        nj = os.path.join(self.tmp, "r-nojournal")
        os.makedirs(nj)
        self.assertEqual(self.err(nj)[0], "UNAVAILABLE_RECORD")
        partial = self.mkrun("r-partial", [
            {"type": "started", "key": "k1", "agentId": "a1"},
            {"type": "started", "key": "k2", "agentId": "a2"},
            {"type": "result", "key": "k1", "agentId": "a1", "result": "a"}],
            {"a1": {}, "a2": {}})
        self.assertEqual(NWA.read_run(partial)["state"], "PARTIAL")
        unknown = self.mkrun("r-unknown", [
            {"type": "started", "key": "k1", "agentId": "a1"},
            {"type": "result", "key": "k1", "agentId": "a1", "result": "a"},
            {"type": "frobnicate"}])
        self.assertEqual(NWA.read_run(unknown)["unknown_event_types"], ["frobnicate"])
        self.assertEqual(NWA.read_run(self.mkrun("r-launched", [{"type": "launched"}]))["state"],
                         "UNAVAILABLE_RECORD")

    def test_persist_atomic(self):
        out = os.path.join(self.tmp, "persist", "sub", "out.json")
        NWA.persist({"x": 1}, out)
        with open(out, encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), {"x": 1})
        self.assertFalse(os.path.exists(out + ".tmp"))


class Boundary(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="nwa-cli-")
        self.home = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def cli(self, *args):
        p = subprocess.run([sys.executable, "-I", MODULE] + list(args),
                           capture_output=True, text=True, cwd=self.home,
                           env={"HOME": self.home, "PATH": "/usr/bin:/bin"},
                           stdin=subprocess.DEVNULL, timeout=60)
        return p.returncode, p.stdout

    def test_control_verbs_refused_without_writes(self):
        for verb in VERBS:
            out = os.path.join(self.home, "control-%s.json" % verb)
            rc, stdout = self.cli("--" + verb, "--out", out)
            body = json.loads(stdout)
            self.assertEqual((rc, body["status"], body["writes"]),
                             (4, "UNAVAILABLE_EXTERNAL", []), verb)
            self.assertFalse(os.path.exists(out), verb)

    def test_capabilities_refuse_control(self):
        caps = NWA.capabilities()
        for verb in VERBS:
            self.assertEqual(caps[verb], "UNAVAILABLE_EXTERNAL: no supported external harness "
                             "control endpoint; owner stop and host records remain read-only")

    def test_cli_units(self):
        units = os.path.join(self.home, "units.json")
        with open(units, "w", encoding="utf-8") as fh:
            json.dump([A("act", ["x/y"]), R("r", ["x"]), R("d", ["d"])], fh)
        cap = os.path.join(self.home, "cap.json")
        with open(cap, "w", encoding="utf-8") as fh:
            fh.write("3")
        before = set(os.listdir(self.home))
        rc, stdout = self.cli("--units", units, "--capacity", cap)
        self.assertEqual(rc, 0)
        self.assertEqual(set(os.listdir(self.home)), before)  # no --out, no writes
        self.assertEqual([s["unit"] for s in json.loads(stdout)["frontier"]["selected"]], ["d"])
        out = os.path.join(self.home, "o", "out.json")
        rc, stdout = self.cli("--units", units, "--out", out)
        self.assertEqual((rc, os.path.exists(out), json.loads(stdout)["writes"]),
                         (0, True, [out]))

    def test_import_set_has_no_network_or_process_control(self):
        with open(MODULE, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module.split(".")[0])
        self.assertEqual(sorted(names), ["__future__", "argparse", "collections", "hashlib",
                                         "json", "os", "pathlib", "posixpath", "sys"])


if __name__ == "__main__":
    unittest.main()
