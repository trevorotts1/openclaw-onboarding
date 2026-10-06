"""PD-TEST-065 -- an empty completion in the GENERIC fan-out must be RECORDED
and must never be retried byte-identically.

The defect this pins (proven live on run
pres-operator-1d269693-ff54-4b1f-b45a-61dc7d8ca4d4):

  * `_dispatch_phase_fanout_units._unit_worker` -- the runner for EVERY
    manifest-declared fan-out phase, including P4-COPY (the deck's spine) --
    turned a zero-length completion into a BARE failure:
    `UnitResult(status="failed", reasons=["unit returned empty output"])`.
    The provider's `usage` dict was discarded, so `reasoning_tokens` -- the one
    number that explains the failure -- never reached any durable record. The
    serial path has always written a sidecar `empty_completion` row WITH usage
    (dispatcher.py, `_dispatch_prompt_phase_serial`); the P4-PROMPT fan-out has
    its own copy of that guard. The generic path did not.
  * The phase-level sweep then re-issued the IDENTICAL request. P4-COPY's
    section-01 returned empty 3/3 times and the phase quarantined, withholding
    14 dependents. An unchanged-input empty completion is deterministic, so the
    retry could only burn another paid call.

Two directions, because a repair that only records is half a repair and a
repair that only changes the request is unverifiable:

  A. RECORD: the empty completion writes a sidecar row carrying the usage, and
     the durable per-unit `last_error` names the budget arithmetic.
  B. STEP DOWN, NARROWLY: a re-attempt for a unit whose OWN record already
     carries that marker is issued at
     DEEPSEEK_REASONING_EFFORT_AFTER_EMPTY -- the 2026-08-26/27 mitigation this
     box used and later lost -- while a first attempt and an unrelated failure
     both keep the operator-declared "max".

The wire is asserted too: `deepseek_complete` must actually put the effort on
the request body, or the step-down would be cosmetic. `urlopen` is stubbed, so
there is NO network and NO real key.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import dispatcher as D  # noqa: E402
from presentation_job import fanout  # noqa: E402


class FakePhase:
    """Phase-shaped stub: this test never loads a manifest."""

    def __init__(self, pid: str, role: str):
        self.id = pid
        self.owning_role = role
        self.workers = 1
        self.budget_minutes = 5
        self.executor_kind = "agent"


SECTIONS = (("Hook", 1, 5), ("Teach", 6, 15), ("Offer", 16, 20))
N_SLIDES = 20
EMPTY_USAGE = {"completion_tokens": 64_000,
               "completion_tokens_details": {"reasoning_tokens": 63_998},
               "request_id": "req-empty"}


def _p4_run(tmp_path: Path) -> Path:
    rd = tmp_path / "run"
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "working" / "research").mkdir(parents=True)
    (rd / "working" / "work-orders").mkdir(parents=True)
    slots = [{"ordinal": n, "arc": name}
             for name, lo, hi in SECTIONS
             for n in range(lo, hi + 1)]
    (rd / "working" / "copy" / "arc_allocation.json").write_text(json.dumps({"slots": slots}))
    (rd / "working" / "copy" / "intake.json").write_text(json.dumps({"client": "t"}))
    (rd / "working" / "copy" / "priority_shift_spec.json").write_text(json.dumps({"p": 1}))
    (rd / "working" / "copy" / "sp_intake.json").write_text(json.dumps({"s": 1}))
    (rd / "working" / "research" / "research_map.json").write_text(json.dumps({"m": 1}))
    (rd / "working" / "copy" / "slides.json").write_text(
        json.dumps({"slides": [{"ordinal": n} for n in range(1, N_SLIDES + 1)]}))
    return rd


def _dept(tmp_path: Path, role: str) -> Path:
    dept = tmp_path / "dept"
    r = dept / role
    r.mkdir(parents=True)
    (r / "how-to.md").write_text("SOP")
    return dept


def _section_body(name: str, lo: int, hi: int) -> str:
    return "\n".join(f"SLIDE {n}\nHEADLINE for {n}\nNOTE {n}" for n in range(lo, hi + 1))


def _sidecar_rows(rd: Path, phase_id: str = "P4-COPY") -> list:
    p = rd / "working" / "work-orders" / f"{phase_id}.dispatcher-log.jsonl"
    if not p.is_file():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def _unit_record(rd: Path, unit: str = "section-01",
                 phase_id: str = "P4-COPY") -> dict:
    p = rd / "working" / "fanout" / "_units" / phase_id / "state.json"
    return (json.loads(p.read_text()).get("units") or {}).get(unit) or {}


@pytest.fixture()
def p4_env(tmp_path, monkeypatch):
    rd = _p4_run(tmp_path)
    dept = _dept(tmp_path, "slide-copywriter")
    # (user_prompt, kwargs) for every paid call this dispatch makes.
    calls: list = []

    def fake_dispatch(system_prompt, user_prompt, *, phase_id, run_dir, **kw):
        calls.append((user_prompt, kw))
        for name, lo, hi in SECTIONS:
            if repr(name) in user_prompt and "AUTHORS EXACTLY ONE SECTION" in user_prompt:
                return (_section_body(name, lo, hi), {"request_id": "req-stub"},
                        {"provider": "stub", "model": "stub-1"})
        raise AssertionError("unit prompt lost its one-scope instruction")

    monkeypatch.setattr(D, "dispatch_complete", fake_dispatch)
    monkeypatch.setattr(D, "_verify", lambda pid, rdir: (True, []))
    return {"rd": rd, "dept": dept, "calls": calls, "monkeypatch": monkeypatch,
            "fake_dispatch": fake_dispatch,
            "order": {"owning_role": "slide-copywriter",
                      "produces_artifact": "working/copy/slides_copy.md"},
            "spec": fanout.parse_fanout_field({"by": "section", "max_units": 5}),
            "phase": FakePhase("P4-COPY", "slide-copywriter"),
            "target": rd / "working" / "copy" / "slides_copy.md"}


def _dispatch(env):
    return D._dispatch_phase_fanout_units(
        env["rd"], env["order"], dept_root=env["dept"], phase_obj=env["phase"],
        worker_id="test", spec=env["spec"],
        patterns=["working/copy/slides_copy.md"], target=env["target"],
        prior_reasons=[])


def _empty_for(env, name: str):
    """A dispatch stub that returns ZERO-LENGTH content for one section.

    Records into `env["calls"]` exactly like the fixture's own stub, so a test
    can assert BOTH what was requested and in which order."""
    def stub(system_prompt, user_prompt, *, phase_id, run_dir, **kw):
        env["calls"].append((user_prompt, kw))
        if repr(name) in user_prompt and "AUTHORS EXACTLY ONE SECTION" in user_prompt:
            return ("", dict(EMPTY_USAGE), {"provider": "stub", "model": "stub-1"})
        for n, lo, hi in SECTIONS:
            if repr(n) in user_prompt and "AUTHORS EXACTLY ONE SECTION" in user_prompt:
                return (_section_body(n, lo, hi), {"request_id": "req-stub"},
                        {"provider": "stub", "model": "stub-1"})
        raise AssertionError("unit prompt lost its one-scope instruction")
    return stub


# ---------------------------------------------------------------------------
# A. RECORD -- the usage and the budget arithmetic must reach durable state.
# ---------------------------------------------------------------------------

def test_empty_completion_is_recorded_with_usage_and_budget_arithmetic(p4_env):
    p4_env["monkeypatch"].setattr(D, "dispatch_complete", _empty_for(p4_env, "Teach"))
    res = _dispatch(p4_env)

    # Only the Teach unit failed; the other two are real authored units.
    assert res.status == "partial_failure", res.reasons
    assert any("section-02" in r for r in res.reasons)
    # The failure reason names the ONE number that explains it.
    assert "reasoning_tokens=63998" in "; ".join(res.reasons), res.reasons
    assert "max_tokens=64000" in "; ".join(res.reasons), res.reasons

    # The explicit sidecar row exists, exactly like the serial path's, and it
    # carries the provider's usage -- the fact the old code threw away.
    rows = [r for r in _sidecar_rows(p4_env["rd"])
            if r.get("status") == "empty_completion"]
    assert len(rows) == 1, rows
    row = rows[0]
    assert row["unit"] == "section-02", row
    assert row["usage"]["completion_tokens_details"]["reasoning_tokens"] == 63_998
    assert row["reasoning_effort"] == D.DEEPSEEK_REASONING_EFFORT, row
    assert row["max_tokens"] == D.DEEPSEEK_MAX_OUTPUT_TOKENS, row

    # ...and the DURABLE per-unit record carries it, so the next reader (or the
    # next process, after a resume) can see WHY without the transcript.
    rec = _unit_record(p4_env["rd"], "section-02")
    assert rec["status"] == "failed", rec
    assert D.EMPTY_COMPLETION_MARKER in rec["last_error"], rec
    assert "reasoning_tokens=63998" in rec["last_error"], rec
    # The successful sibling is untouched by any of this.
    assert _unit_record(p4_env["rd"], "section-01")["status"] == "ok"


def test_empty_completion_reason_survives_a_missing_usage_dict(p4_env):
    """A provider that reports no usage must not crash the diagnostic path."""
    p4_env["monkeypatch"].setattr(
        D, "dispatch_complete",
        lambda sp, up, *, phase_id, run_dir, **kw: (
            "", None, {"provider": "stub", "model": "stub-1"}))
    res = _dispatch(p4_env)
    assert res.status == "exhausted", res.reasons
    assert all(D.EMPTY_COMPLETION_MARKER in r for r in res.reasons), res.reasons
    assert "no usage recorded" in "; ".join(res.reasons), res.reasons


# ---------------------------------------------------------------------------
# B. STEP DOWN -- and ONLY on the evidence that justifies it.
# ---------------------------------------------------------------------------

def test_re_attempt_after_empty_steps_down_and_is_not_the_identical_request(p4_env):
    # ROUND 1: the first attempt runs at the operator-declared effort (the
    # caller passes None; the transport maps that to "max").
    p4_env["monkeypatch"].setattr(D, "dispatch_complete", _empty_for(p4_env, "Teach"))
    _dispatch(p4_env)
    assert p4_env["calls"][1][1].get("reasoning_effort") is None, \
        "the FIRST attempt must not be downgraded"

    # ROUND 2 (the sweep's re-attempt): the same unit, now carrying the marker,
    # must be issued at the reduced effort -- a DIFFERENT request.
    p4_env["calls"].clear()
    p4_env["monkeypatch"].setattr(D, "dispatch_complete", p4_env["fake_dispatch"])
    res = _dispatch(p4_env)

    assert res.status == "ok", res.reasons
    teach = [kw for prompt, kw in p4_env["calls"] if repr("Teach") in prompt]
    assert len(teach) == 1, p4_env["calls"]
    assert teach[0].get("reasoning_effort") == D.DEEPSEEK_REASONING_EFFORT_AFTER_EMPTY
    # Hook and Offer were banked, so they were not re-paid at all.
    assert len(p4_env["calls"]) == 1, "a re-attempt must re-pay only the failed unit"
    assert _unit_record(p4_env["rd"], "section-02")["status"] == "ok"
    # The marker is cleared by the successful re-attempt.
    assert not _unit_record(p4_env["rd"], "section-02").get("last_error")


def test_first_attempt_and_unrelated_failures_keep_the_declared_effort(p4_env):
    """The step-down is keyed to the empty-completion marker, not to failure."""
    # ROUND 1: an unrelated failure (transport raised) -- NOT an empty answer.
    def boom(system_prompt, user_prompt, *, phase_id, run_dir, **kw):
        p4_env["calls"].append((user_prompt, kw))
        if repr("Teach") in user_prompt and "AUTHORS EXACTLY ONE SECTION" in user_prompt:
            raise RuntimeError("stub transport failure mid-deck")
        for n, lo, hi in SECTIONS:
            if repr(n) in user_prompt and "AUTHORS EXACTLY ONE SECTION" in user_prompt:
                return (_section_body(n, lo, hi), {"request_id": "req-stub"},
                        {"provider": "stub", "model": "stub-1"})
        raise AssertionError("unit prompt lost its one-scope instruction")

    p4_env["monkeypatch"].setattr(D, "dispatch_complete", boom)
    first = _dispatch(p4_env)
    assert first.status == "partial_failure", first.reasons
    rec = _unit_record(p4_env["rd"], "section-02")
    assert D.EMPTY_COMPLETION_MARKER not in (rec.get("last_error") or ""), rec

    # ROUND 2: the re-attempt of a NON-empty failure keeps the declared effort.
    p4_env["calls"].clear()
    p4_env["monkeypatch"].setattr(D, "dispatch_complete", p4_env["fake_dispatch"])
    second = _dispatch(p4_env)
    assert second.status == "ok", second.reasons
    teach = [kw for prompt, kw in p4_env["calls"] if repr("Teach") in prompt]
    assert len(teach) == 1, p4_env["calls"]
    assert teach[0].get("reasoning_effort") is None, \
        "an unrelated failure must NOT trigger the reasoning step-down"


def test_a_clean_unit_is_never_downgraded(p4_env):
    res = _dispatch(p4_env)
    assert res.status == "ok", res.reasons
    assert len(p4_env["calls"]) == 3
    assert all(kw.get("reasoning_effort") is None for _p, kw in p4_env["calls"]), \
        "no unit carries empty-completion evidence, so none may be downgraded"
    assert not [r for r in _sidecar_rows(p4_env["rd"])
                if r.get("status") == "empty_completion"]


# ---------------------------------------------------------------------------
# C. THE WIRE -- the step-down must actually reach the request body.
# ---------------------------------------------------------------------------

class _FakeResp:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture()
def wire(monkeypatch):
    """Capture the exact bytes deepseek_complete would POST. No network."""
    sent: list = []
    reply = json.dumps({"choices": [{"message": {"content": "hello"}}],
                        "usage": {"completion_tokens": 3}}).encode()

    def fake_urlopen(req, timeout=None):
        sent.append(json.loads(req.data.decode("utf-8")))
        return _FakeResp(reply)

    monkeypatch.setattr(D, "_load_deepseek_key", lambda: "test-key-not-a-secret")
    monkeypatch.setattr(D, "_govern_admit", lambda provider: types.SimpleNamespace(
        admitted=True, lease=None))
    monkeypatch.setattr(D, "_govern_release", lambda provider, lease: None)
    monkeypatch.setattr(D, "_govern_ok", lambda provider: None)
    monkeypatch.setattr(D.urllib.request, "urlopen", fake_urlopen)
    return sent


def test_wire_body_carries_the_product_workers_effort_by_default(wire):
    """PD-TEST-124: the DEFAULT is the PRODUCT WORKER's effort, not the harness
    agent's declared one. On a ~155k-char authoring prompt `max` consumes 100%
    of max_tokens on reasoning and returns ZERO-length content; `medium`
    terminates at ~15% of the same budget with a schema-valid payload. This test
    previously asserted "max" and so pinned the defect."""
    content, usage = D.deepseek_complete("sys", "user", retries=1)
    assert content == "hello" and usage["completion_tokens"] == 3
    assert len(wire) == 1
    assert wire[0]["reasoning_effort"] == "medium", wire[0]
    assert wire[0]["thinking"] == {"type": "enabled"}, wire[0]
    assert wire[0]["max_tokens"] == D.DEEPSEEK_MAX_OUTPUT_TOKENS, wire[0]
    # The harness-vs-worker distinction must be PINNED, not merely commented:
    # the operator's declared value is retained for audit, and the worker's
    # default deliberately differs from it.
    assert D.DEEPSEEK_REASONING_EFFORT_DECLARED_BY_OPERATOR == "max"
    assert D.DEEPSEEK_REASONING_EFFORT != D.DEEPSEEK_REASONING_EFFORT_DECLARED_BY_OPERATOR


def test_wire_body_carries_the_stepped_down_effort_when_asked(wire):
    D.deepseek_complete("sys", "user", retries=1,
                        reasoning_effort=D.DEEPSEEK_REASONING_EFFORT_AFTER_EMPTY)
    assert len(wire) == 1
    assert wire[0]["reasoning_effort"] == D.DEEPSEEK_REASONING_EFFORT_AFTER_EMPTY
    # NO DEAD-END: the step-down must differ from the default, or a retry after
    # an empty completion would re-send the request that just failed (the exact
    # defect in the old ("medium","low") ladder once medium became a documented
    # ALIAS of high, the model's own default).
    assert wire[0]["reasoning_effort"] != D.DEEPSEEK_REASONING_EFFORT, wire[0]
    # ...and the shared budget is UNCHANGED -- this is a reasoning step-down,
    # not a silent budget cut.
    assert wire[0]["max_tokens"] == D.DEEPSEEK_MAX_OUTPUT_TOKENS, wire[0]


def test_the_step_down_never_repeats_the_effort_that_just_failed():
    """PD-TEST-124 property, driven through the REAL ladder walk rather than
    asserted against the constants.

    The previous version of this test only inspected
    `DEEPSEEK_REASONING_EFFORT_LADDER` (`default not in ladder`, no duplicate
    rungs). Both of those hold for ANY one-rung ladder, so it passed unchanged
    even when the walk was broken -- and its claim ("never repeats the rung that
    just failed") was FALSE for the shipped ladder: the rung index is clamped,
    so attempt 3 re-sent attempt 2's `low`. An independent review caught that
    (PD-TEST-148). This version calls the production function over the real
    attempt sequence, so it fails if the walk regresses, and it asserts the
    guarantee that actually holds.

    The genuine guarantee: attempt 2 DIFFERS from attempt 1 (the step-down that
    PD-TEST-124 exists to create). Attempts beyond the ladder's length are
    documented resamples of the final rung, and are asserted as such here rather
    than denied.
    """
    ladder = D.DEEPSEEK_REASONING_EFFORT_LADDER
    assert ladder, "the ladder must have at least one rung"
    assert len(set(ladder)) == len(ladder), f"ladder repeats a rung: {ladder!r}"
    assert D.DEEPSEEK_REASONING_EFFORT not in ladder, (
        "the first rung must differ from the default, or a retry after an empty "
        f"completion re-sends it: default={D.DEEPSEEK_REASONING_EFFORT!r} ladder={ladder!r}")

    # Attempt 1: nothing has failed yet -> no override, the product default.
    assert D.effort_for_paid_attempt("", 1) is None
    assert D.effort_for_paid_attempt("some other provider error", 1) is None
    assert D.effort_for_paid_attempt("", 0) is None

    # Attempt 2 after an EMPTY COMPLETION: a real step DOWN from attempt 1.
    attempt1 = D.DEEPSEEK_REASONING_EFFORT
    attempt2 = D.effort_for_paid_attempt(D.EMPTY_COMPLETION_MARKER + " detail", 2)
    assert attempt2 is not None, "attempt 2 must be re-issued at a reduced effort"
    assert attempt2 != attempt1, (
        "attempt 2 must differ from attempt 1, or the retry re-sends the request "
        f"that just returned empty: attempt1={attempt1!r} attempt2={attempt2!r}")
    assert attempt2 in ladder, attempt2

    # Attempts past the ladder's length RESAMPLE the final rung. Asserted
    # explicitly so the shipped behaviour is pinned honestly; if a measured rung
    # below `low` is ever added, this case is where the new step-down gets
    # pinned. (It is a clamp, not a crash and not a silent fall back to the
    # default -- which would be the PD-070 dead-end.)
    last_rung = ladder[-1]
    for spent in range(len(ladder) + 1, len(ladder) + 4):
        assert D.effort_for_paid_attempt(D.EMPTY_COMPLETION_MARKER, spent) == last_rung, (
            f"a unit past the ladder must resample the final rung {last_rung!r}, "
            f"never fall back to the default {attempt1!r}")


def test_dispatch_complete_forwards_the_effort_to_the_transport(monkeypatch):
    """The routed entrypoint must not swallow the parameter it advertises."""
    seen: dict = {}

    def fake_deepseek(system_prompt, user_prompt, *, model=None, run_dir=None,
                      max_tokens=None, retries=None, reasoning_effort=None):
        seen["reasoning_effort"] = reasoning_effort
        return "body", {"completion_tokens": 1}

    monkeypatch.setattr(D, "deepseek_complete", fake_deepseek)
    monkeypatch.setattr(D, "_model_router", None)   # router unavailable -> the
    monkeypatch.setattr(D, "_reserve_paid_attempt", lambda *a, **k: None)
    monkeypatch.setattr(D, "_govern_admit", lambda provider: types.SimpleNamespace(
        admitted=True, lease=None))
    monkeypatch.setattr(D, "_govern_release", lambda provider, lease: None)
    # ...documented DeepSeek-direct fallback path, which is a real call site.
    D.dispatch_complete("sys", "user", phase_id="P4-COPY",
                        reasoning_effort="medium")
    assert seen["reasoning_effort"] == "medium", seen
