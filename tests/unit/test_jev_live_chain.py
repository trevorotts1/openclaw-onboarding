#!/usr/bin/env python3
"""JEV live chain: the bridge asks the Jev model (own key, else OpenRouter, else local).

Offline only: every transport is a fake that records calls, no network, no real key.
The REAL bridge (_evaluate), jev_live, ladder, providers and resolver run around them.

Run: pytest tests/unit/test_jev_live_chain.py -q
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import time
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
_SU = _REPO / "shared-utils"
sys.path.insert(0, str(_SU))

_spec = importlib.util.spec_from_file_location("jev_chain_bridge", _SU / "decision-engine.py")
bridge = importlib.util.module_from_spec(_spec)
sys.modules["jev_chain_bridge"] = bridge
_spec.loader.exec_module(bridge)
import jev_live  # noqa: E402

_REAL_DECIDE = jev_live.decide

FAKE_DIRECT = "directKeyAA1b2c3d4e5f6g7h8i9j0"
FAKE_OR = "routerKeyDD7q8w9e0r1t2y3u4i5o6"
TASK = "Zorblax the quintessential frobnicator for the quarterly thing"
CATALOG = [{"slug": "alpha-dept", "name": "Alpha Department", "description": "zorblax"},
           {"slug": "beta-dept", "name": "Beta Department", "description": "unrelated"}]
FORBIDDEN = ("assigned_agent_id", "assignedAgentId", "assignment", "board", "task_card",
             "taskCard", "dispatch", "column", "status_transition", "statusTransition",
             "persona_pin", "personaPin")
KEY_ENVS = ("TYPESAFE_API_KEY", "JEV_API_KEY", "JEV_TYPESAFE_API_KEY",
            "OPENROUTER_API_KEY", "OPENROUTER_KEY", "OPEN_ROUTER_API_KEY")


class Fakes:
    """Recording transports. `answer` = (intent, department, top_probability)."""

    def __init__(self, answer=("task_request", "beta-dept", 0.95), direct_status=200,
                 or_status=200, delay=0.0):
        self.answer, self.direct_status, self.or_status, self.delay = (
            answer, direct_status, or_status, delay)
        self.direct_calls, self.or_calls = [], []

    def _payload(self, record, model):
        intent, dept, p = self.answer
        judgments = []
        for qid, q in record.items():
            cands = q["candidates"]
            pick = intent if qid == jev_live.Q_INTENT else dept
            rest = (1.0 - p) / (len(cands) - 1)
            probs = {c: (p if c == pick else rest) for c in cands}
            judgments.append({"question_id": qid, "type": "select", "answer": pick,
                              "probabilities": probs})
        return {"model": model, "judgments": judgments}

    def direct(self, url, body, headers, timeout_s):
        self.direct_calls.append(url)
        time.sleep(self.delay)
        if self.direct_status != 200:
            return self.direct_status, None
        return 200, self._payload(json.loads(body)["questions"], "jev-1.13.0")

    def openrouter(self, endpoint, headers, payload):
        self.or_calls.append(endpoint)
        if self.or_status != 200:
            return self.or_status, None
        return 200, self._payload(json.loads(payload)["questions"], "typesafe/jev-1.13")


@pytest.fixture
def box(tmp_path, monkeypatch):
    root = tmp_path / "oc"
    (root / "secrets").mkdir(parents=True)
    for name in KEY_ENVS + ("OPENCLAW_DECISION_ENGINE_MODE",):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OC_CONFIG", str(root))
    monkeypatch.delenv("OPENCLAW_ROUTING_NO_RECORD", raising=False)
    return root


def _keys(root, **kv):
    (root / "secrets" / ".env").write_text(
        "".join("%s=%s\n" % (k, v) for k, v in kv.items()), encoding="utf-8")


def _evaluate(monkeypatch, fakes, task=TASK, **extra):
    monkeypatch.setattr(jev_live, "decide", lambda *a, **k: _REAL_DECIDE(
        *a, direct_http=fakes.direct, openrouter_transport=fakes.openrouter, **k))
    request = {"schemaVersion": "1.1.0", "configRevision": "rev-77", "taskId": "t",
               "taskDescription": task, "departments": CATALOG, **extra}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(request)))
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = bridge._evaluate()
    assert rc == 0, err.getvalue()
    return json.loads(out.getvalue()), out.getvalue() + err.getvalue()


def _local(monkeypatch):
    return _evaluate(monkeypatch, Fakes())[0]


def test_own_key_first_openrouter_untouched(box, monkeypatch):
    _keys(box, TYPESAFE_API_KEY=FAKE_DIRECT, OPENROUTER_API_KEY=FAKE_OR)
    f = Fakes(("task_request", "beta-dept", 0.95))
    resp, _ = _evaluate(monkeypatch, f)
    assert len(f.direct_calls) == 1 and f.or_calls == []
    assert resp["intent"] == "task_request"
    assert resp["route"]["department"] == "beta-dept"
    assert resp["route"]["method"] == "jev_own_key"
    assert resp["route"]["fallback"] is False


def test_openrouter_only(box, monkeypatch):
    _keys(box, OPENROUTER_API_KEY=FAKE_OR)
    f = Fakes(("task_request", "beta-dept", 0.9))
    resp, _ = _evaluate(monkeypatch, f)
    assert f.direct_calls == [] and len(f.or_calls) == 1
    assert resp["route"]["department"] == "beta-dept"
    assert resp["route"]["method"] == "jev_openrouter"


def test_direct_error_falls_to_openrouter(box, monkeypatch):
    _keys(box, JEV_TYPESAFE_API_KEY=FAKE_DIRECT, OPENROUTER_API_KEY=FAKE_OR)
    f = Fakes(direct_status=500)
    resp, _ = _evaluate(monkeypatch, f)
    assert len(f.direct_calls) == 1 and len(f.or_calls) == 1
    assert resp["route"]["method"] == "jev_openrouter"


def test_neither_key_is_exactly_the_local_engine(box, monkeypatch):
    f = Fakes()
    resp, _ = _evaluate(monkeypatch, f)
    assert f.direct_calls == [] and f.or_calls == []
    assert "method" not in resp["route"]
    assert resp["intentSource"] == "heuristic"


@pytest.mark.parametrize("keys", [{"TYPESAFE_API_KEY": FAKE_DIRECT},
                                  {"OPENROUTER_API_KEY": FAKE_OR},
                                  {"TYPESAFE_API_KEY": FAKE_DIRECT, "OPENROUTER_API_KEY": FAKE_OR}])
def test_provider_errors_fall_back_to_local(box, monkeypatch, keys):
    baseline = _local(monkeypatch)
    _keys(box, **keys)
    f = Fakes(direct_status=500, or_status=429)
    resp, _ = _evaluate(monkeypatch, f)
    resp.pop("evaluatedAt"), baseline.pop("evaluatedAt")
    assert resp == baseline


def test_low_confidence_falls_back_to_local(box, monkeypatch):
    baseline = _local(monkeypatch)
    _keys(box, TYPESAFE_API_KEY=FAKE_DIRECT, OPENROUTER_API_KEY=FAKE_OR)
    f = Fakes(("task_request", "beta-dept", 0.55))
    resp, _ = _evaluate(monkeypatch, f)
    assert "method" not in resp["route"]
    assert resp["route"] == baseline["route"]


def test_openrouter_low_confidence_falls_back_to_local(box, monkeypatch):
    _keys(box, OPENROUTER_API_KEY=FAKE_OR)
    resp, _ = _evaluate(monkeypatch, Fakes(("task_request", "beta-dept", 0.5)))
    assert "method" not in resp["route"]


@pytest.mark.parametrize("mode", ["legacy", "off", "shadow"])
def test_non_jev_modes_send_nothing(box, monkeypatch, mode):
    _keys(box, TYPESAFE_API_KEY=FAKE_DIRECT, OPENROUTER_API_KEY=FAKE_OR)
    (box / "decision-engine-mode.conf").write_text(mode + "\n", encoding="utf-8")
    f = Fakes()
    resp, _ = _evaluate(monkeypatch, f)
    assert f.direct_calls == [] and f.or_calls == []
    assert "method" not in resp["route"]


def test_model_mode_uses_jev(box, monkeypatch):
    _keys(box, TYPESAFE_API_KEY=FAKE_DIRECT)
    (box / "decision-engine-mode.conf").write_text("model\n", encoding="utf-8")
    f = Fakes()
    resp, _ = _evaluate(monkeypatch, f)
    assert len(f.direct_calls) == 1 and resp["route"]["department"] == "beta-dept"


def test_exact_fixture_match_sends_nothing(box, monkeypatch):
    _keys(box, TYPESAFE_API_KEY=FAKE_DIRECT, OPENROUTER_API_KEY=FAKE_OR)
    f = Fakes()
    resp, _ = _evaluate(monkeypatch, f, task="Thanks.")
    assert f.direct_calls == [] and f.or_calls == []
    assert resp["intentSource"] == "fixture"


def test_jev_answer_only_intent(box, monkeypatch):
    _keys(box, TYPESAFE_API_KEY=FAKE_DIRECT)
    resp, _ = _evaluate(monkeypatch, Fakes(("answer_only", "general-task", 0.9)))
    assert resp["intent"] == "answer_only" and resp["route"]["action"] == "answer"


def test_named_department_still_wins(box, monkeypatch):
    _keys(box, TYPESAFE_API_KEY=FAKE_DIRECT)
    resp, _ = _evaluate(monkeypatch, Fakes(("task_request", "beta-dept", 0.95)),
                        department="alpha-dept")
    assert resp["route"]["department"] == "alpha-dept"


def test_wire_contract_unchanged(box, monkeypatch):
    _keys(box, TYPESAFE_API_KEY=FAKE_DIRECT)
    resp, _ = _evaluate(monkeypatch, Fakes())
    assert resp["schemaVersion"] == "1.1.0"
    assert resp["configRevision"] == "rev-77"
    assert set(resp) == {"schemaVersion", "configRevision", "recommendation", "evaluatedAt",
                         "intent", "intentSource", "route"}
    assert resp["recommendation"]["roleId"] == "none_suitable"
    assert resp["intentSource"] in ("fixture", "heuristic")
    assert not [k for k in FORBIDDEN if k in resp or k in resp["route"]
                or k in resp["recommendation"]]


def test_hung_provider_is_cut_at_the_deadline(box, monkeypatch):
    _keys(box, TYPESAFE_API_KEY=FAKE_DIRECT)
    f = Fakes(delay=1.5)
    t0 = time.monotonic()
    res = jev_live.decide(TASK, [{"slug": "a", "text": "A"}], "auto", box,
                          direct_http=f.direct, deadline_ms=200)
    assert res == {"ok": False, "reason": "deadline"}
    assert time.monotonic() - t0 < 1.0


def test_default_deadline_fits_under_command_center(box):
    assert jev_live.DEADLINE_MS <= 2500 < 3000  # CC live.ts stampRootDeadline(3000)


def test_no_key_material_anywhere(box, monkeypatch):
    _keys(box, TYPESAFE_API_KEY=FAKE_DIRECT, OPENROUTER_API_KEY=FAKE_OR)
    _, text = _evaluate(monkeypatch, Fakes())
    events = (box / "routing-events.jsonl").read_text(encoding="utf-8")
    assert FAKE_DIRECT not in text + events and FAKE_OR not in text + events


def test_path_event_recorded_only_on_change(box, monkeypatch):
    _keys(box, TYPESAFE_API_KEY=FAKE_DIRECT)
    for _ in range(3):
        _evaluate(monkeypatch, Fakes())
    lines = [json.loads(x) for x in (box / "routing-events.jsonl").read_text().splitlines()]
    assert [e["reason"] for e in lines if e["event"] == "jev_path"] == ["own-key"]
    (box / "secrets" / ".env").write_text("OPENROUTER_API_KEY=%s\n" % FAKE_OR)
    _evaluate(monkeypatch, Fakes())
    _evaluate(monkeypatch, Fakes())
    lines = [json.loads(x) for x in (box / "routing-events.jsonl").read_text().splitlines()]
    assert [e["reason"] for e in lines if e["event"] == "jev_path"] == ["own-key", "openrouter"]


def test_health_path_from_key_names_only(box):
    assert jev_live.would_use_path(box) == "local-only"
    _keys(box, OPENROUTER_API_KEY=FAKE_OR)
    assert jev_live.would_use_path(box) == "openrouter"
    _keys(box, OPENROUTER_API_KEY=FAKE_OR, JEV_API_KEY=FAKE_DIRECT)
    assert jev_live.would_use_path(box) == "own-key"
    _keys(box, TYPESAFE_API_KEY="PASTE_YOUR_KEY_HERE")  # placeholder never counts
    assert jev_live.would_use_path(box) == "local-only"
