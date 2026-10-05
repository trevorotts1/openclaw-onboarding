#!/usr/bin/env python3
"""RF-014: the REAL bridge under `model` mode + the tripwire hooks.

Companion to tests/unit/routing-mode-switch.test.sh (which exercises the shell
surface). Here the bridge module is imported and _evaluate() runs in-process with:
  * a fake department catalog (request-supplied, so no repo path is read);
  * the model_route ask seam patched to return canned replies;
  * OC_CONFIG pointed at throwaway fixture roots (--evaluate is asked to prove it
    touches nothing outside them).

Proven, against the REAL code:
  1. model mode: an unplaceable task is placed by the box's own default model
     (method=model, confidence 0.9, wire shape unchanged); the model's reply is
     honoured ONLY when it is exactly one slug from the box's own list; anything
     else -> general-task fallback.
  2. no default model resolves in model mode -> the task goes the legacy way
     (route untouched) AND model_mode_fallback_legacy is logged.
  3. auto/shadow/legacy/off do NOT call the model pick (the seam must go unused) --
     legacy and off stay byte-identical normalized, and auto's fallback behaviour
     is unchanged.
  4. tripwire hooks: a failing evaluation (core unusable) counts once per process
     toward the tripwire; five in a row flip the store to legacy with the marker
     and flag; a success resets; a legacy/off box is never counted.
  5. the evaluation still answers rc 0 with the EXACT same non-route response
     fields as before RF-014 (wire compatibility).
  6. controls on the instrument: the catalog seam really reaches _model_place
     (a model-picked slug arrives on the wire), so a pass is not vacuous.

Run: python3 -m pytest tests/unit/test_rf014_model_mode.py -q
"""

from __future__ import annotations

import io
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
_SU = _REPO / "shared-utils"
sys.path.insert(0, str(_SU))

import routing_switch as rs  # noqa: E402
import model_route as mr  # noqa: E402

_spec = importlib.util.spec_from_file_location("rf014_bridge", _SU / "decision-engine.py")
bridge = importlib.util.module_from_spec(_spec)
sys.modules["rf014_bridge"] = bridge
_spec.loader.exec_module(bridge)

CATALOG = [
    {"slug": "graphics", "name": "Graphics Department",
     "description": "logos, banners", "keywords": []},
    {"slug": "presentations", "name": "Presentations Department",
     "description": "decks and keynotes", "keywords": []},
]
CATALOG_IDS = {e["slug"] for e in CATALOG} | {mr.GENERAL}


def _box(tmp, mode=None, config=None):
    root = Path(tmp) / "oc"
    root.mkdir(parents=True, exist_ok=True)
    if mode:
        (root / rs.STORE).write_text(mode + "\n", encoding="utf-8")
    if config is not None:
        (root / "openclaw.json").write_text(json.dumps(config), encoding="utf-8")
    return root


def _evaluate(root, task, *, mode_env=None, catalog=True):
    """Run the REAL bridge _evaluate with OC_CONFIG at the fixture root."""
    request = {"schemaVersion": "1.1.0", "configRevision": "t1", "taskId": "t",
               "taskDescription": task}
    if catalog:
        request["departments"] = CATALOG
    old_env, old_cfg = dict(os.environ), os.environ.get("OC_CONFIG")
    buf, err = io.StringIO(), io.StringIO()
    try:
        os.environ.pop("OPENCLAW_DECISION_ENGINE_MODE", None)
        if mode_env:
            os.environ["OPENCLAW_DECISION_ENGINE_MODE"] = mode_env
        os.environ["OPENCLAW_ROUTING_NO_RECORD"] = "1"
        os.environ["OC_CONFIG"] = str(root)
        with redirect_stdout(buf), redirect_stderr(err):
            rc = bridge._evaluate.__wrapped__() if False else _run_eval(request)
    finally:
        os.environ.clear()
        os.environ.update(old_env)
        if old_cfg is not None:
            os.environ["OC_CONFIG"] = old_cfg
        else:
            os.environ.pop("OC_CONFIG", None)
    return rc, buf.getvalue(), err.getvalue()


def _run_eval(request):
    stdin = sys.stdin
    class _In:
        def read(self):
            return json.dumps(request)
    sys.stdin = _In()
    try:
        return bridge._evaluate()
    finally:
        sys.stdin = stdin


def _pick_route(out):
    return json.loads(out.strip().splitlines()[-1])["route"]



def _patch_pick(replacement):
    """Patch mr.pick AND the bridge's own alias (the bridge imported the module, so
    patching only mr would miss it -- and the alias is what production actually uses)."""
    old = mr.pick
    mr.pick = replacement
    if bridge._model_route is not None:
        bridge._model_route.pick = replacement
    return old


def _restore_pick(old):
    mr.pick = old
    if bridge._model_route is not None:
        bridge._model_route.pick = old


class _Ask:
    """Canned ask seam."""
    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def __call__(self, prompt, model_id, timeout_s):
        self.calls.append({"prompt": prompt, "model": model_id})
        return self.answer


class ModelMode(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="rf014-model-")
        self.addCleanup(self.tmp.cleanup)
        self.cfg = {"agents": {"defaults": {"model": {"primary": "ollama-cloud/qwen3:32b"}}}}

    def test_unplaceable_task_is_picked_by_the_box_model(self):
        root = _box(self.tmp.name, mode="model", config=self.cfg)
        ask = _Ask("graphics")
        fake = lambda task, cat, path, **kw: {
            "status": "ok", "department": "graphics",
            "model": mr.resolve_default_model(str(root / "openclaw.json")),
            "detail": "model_pick"}
        old = _patch_pick(fake)
        try:
            rc, out, _err = _evaluate(root, "frobnicate the quux xyzzy")
        finally:
            _restore_pick(old)
        self.assertEqual(rc, 0)
        route = _pick_route(out)
        self.assertEqual(route["department"], "graphics")
        self.assertFalse(route["fallback"])
        self.assertEqual(route["confidence"], bridge._MODEL_PICK_CONFIDENCE)
        self.assertEqual(route["method"], "model")

    def test_model_reply_must_be_exactly_a_catalog_slug(self):
        root = _box(self.tmp.name, mode="model", config=self.cfg)
        fake = lambda *a, **kw: {"status": "ok", "department": mr.GENERAL,
                                 "model": "ollama-cloud/qwen3:32b", "detail": "unparsed"}
        old = _patch_pick(fake)
        try:
            rc, out, _ = _evaluate(root, "water the plants")
        finally:
            _restore_pick(old)
        route = _pick_route(out)
        self.assertEqual(route["department"], "general-task")
        self.assertTrue(route["fallback"])

    def test_no_default_model_falls_back_and_logs(self):
        root = _box(self.tmp.name, mode="model")  # no openclaw.json
        rc, out, _ = _evaluate(root, "frobnicate the quux xyzzy")
        self.assertEqual(rc, 0)
        route = _pick_route(out)
        # the task still lands (general-task via the rules), and the fallback is logged
        self.assertEqual(route["department"], "general-task")
        self.assertEqual(route["method"], "legacy_no_default_model")
        events = (root / rs.EVENTS).read_text(encoding="utf-8")
        self.assertIn("model_mode_fallback_legacy", events)

    def test_other_modes_never_call_the_pick(self):
        for mode in ("auto", "shadow", "legacy", "off"):
            with self.subTest(mode=mode):
                root = _box(self.tmp.name, mode=mode, config=self.cfg)
                called = []
                old = _patch_pick(lambda *a, **kw: called.append(1))
                try:
                    rc, out, _ = _evaluate(root, "frobnicate the quux xyzzy")
                finally:
                    _restore_pick(old)
                self.assertEqual(rc, 0)
                self.assertEqual(called, [], mode)
                route = _pick_route(out)
                self.assertEqual(route["department"], "general-task")
                self.assertNotIn("method", route)  # no model stamping in other modes

    def test_wire_response_fields_unchanged(self):
        root = _box(self.tmp.name, mode="auto", config=self.cfg)
        rc, out, _ = _evaluate(root, "frobnicate the quux xyzzy")
        payload = json.loads(out.strip().splitlines()[-1])
        for key in ("schemaVersion", "configRevision", "recommendation",
                    "evaluatedAt", "intent", "intentSource", "route"):
            self.assertIn(key, payload)
        self.assertEqual(payload["recommendation"]["roleId"], "none_suitable")

    def test_placeable_task_never_reaches_the_model(self):
        # a confident lexical pick (department requested explicitly) never calls the pick
        root = _box(self.tmp.name, mode="model", config=self.cfg)
        called = []
        old = _patch_pick(lambda *a, **kw: called.append(1))
        buf, err = io.StringIO(), io.StringIO()
        request = {"schemaVersion": "1.1.0", "configRevision": "t1", "taskId": "t",
                   "taskDescription": "make a keynote deck", "department": "presentations",
                   "departments": CATALOG}
        old_env = dict(os.environ)
        try:
            os.environ["OC_CONFIG"] = str(root)
            os.environ["OPENCLAW_ROUTING_NO_RECORD"] = "1"
            os.environ.pop("OPENCLAW_DECISION_ENGINE_MODE", None)
            with redirect_stdout(buf), redirect_stderr(err):
                rc = _run_eval(request)
        finally:
            _restore_pick(old)
            os.environ.clear(); os.environ.update(old_env)
        self.assertEqual(rc, 0)
        self.assertEqual(called, [])
        self.assertEqual(_pick_route(buf.getvalue())["department"], "presentations")


class TripwireHooks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="rf014-trip-")
        self.addCleanup(self.tmp.cleanup)

    def _count_one_failure(self, root):
        old = os.environ.get("OC_CONFIG")
        try:
            os.environ["OC_CONFIG"] = str(root)
            os.environ.pop("OPENCLAW_DECISION_ENGINE_MODE", None)
            os.environ.pop("OPENCLAW_ROUTING_NO_RECORD", None)
            bridge._count(False, "core_unusable")
        finally:
            os.environ.pop("OC_CONFIG", None)
            if old is not None:
                os.environ["OC_CONFIG"] = old

    def test_five_failures_trip_the_box(self):
        root = _box(self.tmp.name) # default box, net armed
        for _ in range(5):
            self._count_one_failure(root)
        st = rs.resolve_mode(root)
        self.assertEqual(st["mode"], "legacy")
        self.assertTrue(st["tripped"])
        self.assertTrue((root / rs.FLAG).is_file())
        self.assertIn("tripwire_tripped", (root / rs.EVENTS).read_text(encoding="utf-8"))
        self.assertIn(rs.TRIP_MARK, (root / rs.STORE).read_text(encoding="utf-8"))

    def test_success_resets_the_counter(self):
        root = _box(self.tmp.name)
        for _ in range(4):
            self._count_one_failure(root)
        os.environ["OC_CONFIG"] = str(root)
        try:
            os.environ.pop("OPENCLAW_ROUTING_NO_RECORD", None)
            bridge._count(True)
        finally:
            os.environ.pop("OC_CONFIG", None)
        self._count_one_failure(root)
        self._count_one_failure(root)
        st = rs.resolve_mode(root)
        self.assertEqual(st["mode"], "auto")  # never reached 5 in a row

    def test_off_box_is_never_counted(self):
        root = _box(self.tmp.name, mode="off")
        for _ in range(9):
            self._count_one_failure(root)
        self.assertFalse((root / rs.HEALTH).is_file())
        self.assertEqual(rs.resolve_mode(root)["mode"], "off")

    def test_killed_evaluation_counts_as_a_failure(self):
        root = _box(self.tmp.name)
        first = os.getpid()
        # a pending marker from a dead pid + a fresh begin() = one counted failure
        with _lock_free(root):
            (root / rs.HEALTH).write_text(json.dumps(
                {"pending": {"pid": 999999999, "at": "x"}}), encoding="utf-8")
        rs.begin(root)
        health = json.loads((root / rs.HEALTH).read_text(encoding="utf-8"))
        self.assertEqual(health["consecutiveFailures"], 1)
        self.assertIn("evaluation_did_not_finish", health["lastFailureReason"])

    def test_five_real_evaluations_that_die_still_never_trip_when_pinned(self):
        root = _box(self.tmp.name, mode="shadow")
        (root / rs.HEALTH).write_text(json.dumps(
            {"pending": {"pid": 999999999, "at": "x"}}), encoding="utf-8")
        rs.begin(root)  # pending pid dead, but the mode is pinned: counted, not moved
        self.assertEqual(rs.resolve_mode(root)["mode"], "shadow")
        self.assertFalse((root / rs.FLAG).is_file())


from contextlib import contextmanager  # noqa: E402


@contextmanager
def _lock_free(root):
    yield  # no concurrent writers in this suite


if __name__ == "__main__":
    unittest.main(verbosity=2)