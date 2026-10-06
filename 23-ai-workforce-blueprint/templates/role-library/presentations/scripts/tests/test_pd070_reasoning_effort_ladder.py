"""PD-070 -- an empty completion must say WHY it was empty, and a re-attempt of
a unit that has ALREADY come back empty must walk DOWN a ladder instead of
re-sending the rung that just failed.

Both defects were established on the LIVE run
pres-operator-1d269693-ff54-4b1f-b45a-61dc7d8ca4d4, whose P4-COPY section-01
(authoring call: deepseek-flash, max_tokens=64000, thinking enabled,
reasoning_effort="max") returned empty content on 3/3 paid attempts:

  1. WHY WAS IT EMPTY -- UNKNOWABLE FROM THE RECORD. PD-TEST-065 made the
     fan-out record the provider's `usage`, which is what proves reasoning
     starved the deliverable (a same-run sibling call spent reasoning_tokens
     =47,940 of a 57,178 completion). But `finish_reason` was read NOWHERE in
     this module (grep -c finish_reason dispatcher.py == 0). "length" is the
     provider's documented marker that the request's token maximum was reached
     -- and with thinking enabled that maximum is SHARED with reasoning. So
     "length" + empty content (reasoning exhausted the budget) and "stop" +
     empty content (the model chose to emit nothing) were recorded identically,
     and nothing but a sibling phase's luck could tell them apart afterwards.

  2. THE STEP-DOWN HAD ONE RUNG AND DEAD-ENDED. PD-TEST-065 re-issues an
     empty-completion re-attempt at DEEPSEEK_REASONING_EFFORT_AFTER_EMPTY
     ("medium"). On this endpoint `medium` is a documented ALIAS FOR `high`
     (api-docs.deepseek.com/guides/thinking_mode: "`medium`/`xhigh` are
     accepted and mapped to `high`") and `high` is the model's own DEFAULT
     effort. So a SECOND empty completion re-sent the same default effort as
     the first, a third re-sent it again, and the phase could only ever reach
     the paid-retry ceiling. An unchanged-input empty completion is
     deterministic; repeating it cannot succeed.

The fix: keep `finish_reason` with the usage it belongs to, and drive the
re-attempt from DEEPSEEK_REASONING_EFFORT_LADDER indexed by how many attempts
the unit has already spent, so the retry is never the request that just failed.

PD-TEST-124 (2026-09-16) -- THIS FILE'S PREMISE MOVED. The ladder above was a
RECOVERY-ONLY mechanism: attempt 1 always went out at the default `max`, `max`
saturated the 64,000-token budget on a ~155k-char section prompt, and the
phase's 3-attempt paid cap was often spent before any rung could help. A
bounded experiment on the byte-identical production prompt showed `max`
spending reasoning_tokens=64,000 of 64,000 for ZERO-length content
(finish_reason="length") while `medium` finished at 9,788 tokens with valid
content (finish_reason="stop"). So the worker's DEFAULT is now `medium` and the
ladder's rung 0 moved `medium` -> `low` (a rung equal to the new default would
be the dead rung PD-070 removed). The tests below were restated to assert the
invariant that still holds -- a re-attempt after an empty completion is never
re-sent the worker's DEFAULT -- rather than PD-070's `LADDER[1]`, which no
longer exists. See DEEPSEEK_REASONING_EFFORT in dispatcher.py.

`urlopen` is stubbed throughout: there is NO network and NO real key.
"""
from __future__ import annotations

import json
import sys
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

#: The usage shape the provider actually returned on the live failure: the
#: whole budget spent, nearly all of it on reasoning. `finish_reason="length"`
#: is what the fix now preserves.
EMPTY_USAGE_LENGTH = {
    "completion_tokens": 64_000,
    "completion_tokens_details": {"reasoning_tokens": 63_998},
    "finish_reason": "length",
    "request_id": "req-empty",
}
#: A model that answered nothing and stopped of its own accord -- the OTHER
#: empty completion, which the record must not confuse with the one above.
EMPTY_USAGE_STOP = {
    "completion_tokens": 12,
    "completion_tokens_details": {"reasoning_tokens": 0},
    "finish_reason": "stop",
    "request_id": "req-empty-stop",
}


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


def _unit_record(rd: Path, unit: str = "section-02",
                 phase_id: str = "P4-COPY") -> dict:
    p = rd / "working" / "fanout" / "_units" / phase_id / "state.json"
    return (json.loads(p.read_text()).get("units") or {}).get(unit) or {}


@pytest.fixture()
def p4_env(tmp_path, monkeypatch):
    rd = _p4_run(tmp_path)
    dept = _dept(tmp_path, "slide-copywriter")
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


def _empty_for(env, name: str, usage: dict):
    """A dispatch stub returning ZERO-LENGTH content for one section."""
    def stub(system_prompt, user_prompt, *, phase_id, run_dir, **kw):
        env["calls"].append((user_prompt, kw))
        if repr(name) in user_prompt and "AUTHORS EXACTLY ONE SECTION" in user_prompt:
            return ("", dict(usage), {"provider": "stub", "model": "stub-1"})
        for n, lo, hi in SECTIONS:
            if repr(n) in user_prompt and "AUTHORS EXACTLY ONE SECTION" in user_prompt:
                return (_section_body(n, lo, hi), {"request_id": "req-stub"},
                        {"provider": "stub", "model": "stub-1"})
        raise AssertionError("unit prompt lost its one-scope instruction")
    return stub


def _effort_for(env, name: str):
    return [kw.get("reasoning_effort") for prompt, kw in env["calls"]
            if repr(name) in prompt]


# ---------------------------------------------------------------------------
# 1. WHY WAS IT EMPTY -- the record must carry the provider's own verdict.
# ---------------------------------------------------------------------------

def test_finish_reason_reaches_the_reason_and_the_durable_record(p4_env):
    p4_env["monkeypatch"].setattr(
        D, "dispatch_complete", _empty_for(p4_env, "Teach", EMPTY_USAGE_LENGTH))
    res = _dispatch(p4_env)

    joined = "; ".join(res.reasons)
    assert "reasoning_tokens=63998" in joined, res.reasons
    assert "finish_reason='length'" in joined, \
        "a budget-exhausted empty completion must name finish_reason=length"
    # ...and it survives into the durable per-unit record, not just the result.
    rec = _unit_record(p4_env["rd"], "section-02")
    assert "finish_reason='length'" in rec["last_error"], rec


def test_a_model_that_emitted_nothing_is_distinguishable_from_starvation(p4_env):
    """The two empty completions must NOT be recorded identically."""
    p4_env["monkeypatch"].setattr(
        D, "dispatch_complete", _empty_for(p4_env, "Teach", EMPTY_USAGE_STOP))
    res = _dispatch(p4_env)

    joined = "; ".join(res.reasons)
    assert "finish_reason='stop'" in joined, res.reasons
    assert "finish_reason='length'" not in joined, res.reasons
    # Both are still the SAME failure class for the retry decision -- the
    # marker is unchanged, so PD-TEST-065's step-down still engages.
    assert all(D.EMPTY_COMPLETION_MARKER in r for r in res.reasons), res.reasons


def test_absent_finish_reason_leaves_the_pd065_wording_byte_identical():
    """Backward compatibility: PD-TEST-065's exact strings must not move."""
    assert D._empty_completion_detail(
        {"completion_tokens": 100, "completion_tokens_details":
         {"reasoning_tokens": 90}}) == (
        " (completion_tokens=100, reasoning_tokens=90 of max_tokens=64000 -- "
        "reasoning is billed INSIDE that budget)")
    assert D._empty_completion_detail(
        {"completion_tokens": 100}) == (
        " (completion_tokens=100, reasoning_tokens not reported)")
    assert D._empty_completion_detail({}) == (
        " (usage recorded without token counts)")
    assert D._empty_completion_detail(None) == " (no usage recorded)"


# ---------------------------------------------------------------------------
# 2. THE LADDER -- a second empty completion must not repeat the first rung.
# ---------------------------------------------------------------------------

def test_second_empty_completion_never_re_sends_the_workers_default(p4_env):
    """PD-TEST-124 restated this test's invariant.

    PD-070's version asserted that a SECOND empty completion reaches
    `LADDER[1]`, i.e. it required the ladder to have at least two rungs. That
    requirement is no longer satisfiable: PD-TEST-124 moved the worker's default
    from `max` down to `medium`, and the only documented, thinking-ENABLED value
    below it is `low`. There is no second rung to reach that is not either the
    default itself (a dead rung) or a return to the runaway value.

    The invariant that actually protects the unit is therefore: **a re-attempt
    after an empty completion is never re-sent the worker's default.** That is
    what this asserts, at every round, and it is the property PD-070 existed to
    guarantee. KNOWN AND ACCEPTED LIMIT: with one rung, round 3 re-sends `low`
    -- a bounded repeat, not PD-070's unbounded one, because the phase's
    paid-attempt cap (DISPATCH_RETRY_CAP=3) parks the unit after it.
    """
    # ROUND 1: first attempt, no evidence yet -> effort stays None, so the
    # MODULE's own default (DEEPSEEK_REASONING_EFFORT, "medium") governs.
    p4_env["monkeypatch"].setattr(
        D, "dispatch_complete", _empty_for(p4_env, "Teach", EMPTY_USAGE_LENGTH))
    _dispatch(p4_env)
    assert _effort_for(p4_env, "Teach") == [None], \
        "the FIRST attempt must not be downgraded"

    # ROUND 2: the unit now carries the marker once -> rung 0.
    p4_env["calls"].clear()
    _dispatch(p4_env)
    assert _effort_for(p4_env, "Teach") == [D.DEEPSEEK_REASONING_EFFORT_LADDER[0]]
    assert _effort_for(p4_env, "Teach") != [D.DEEPSEEK_REASONING_EFFORT], \
        "a retry after an empty completion re-sent the worker's own default"

    # ROUND 3: it carries the marker TWICE. The rung clamps to the last
    # documented value -- never back to the default.
    p4_env["calls"].clear()
    _dispatch(p4_env)
    spent = _unit_record(p4_env["rd"], "section-02")["attempts_total"]
    assert spent >= 2, spent
    assert _effort_for(p4_env, "Teach") == [D.DEEPSEEK_REASONING_EFFORT_LADDER[-1]], \
        "a second empty completion did not stay on the documented rung"
    assert _effort_for(p4_env, "Teach") != [D.DEEPSEEK_REASONING_EFFORT], \
        "a second empty completion re-sent the worker's own default"


def test_every_rung_is_a_different_request_from_the_workers_default(p4_env):
    """The invariant PD-070 was really protecting, restated for PD-TEST-124.

    PD-070 asserted `len(ladder) >= 2`; with the default now `medium` and only
    `low` available below it, a length check would demand an invented rung.
    What must hold is that NO rung is the request the unit was just sent, i.e.
    no rung equals the worker's default, and rung 0 is the documented
    after-empty step-down.
    """
    ladder = D.DEEPSEEK_REASONING_EFFORT_LADDER
    assert ladder, "an empty ladder would make every retry the default again"
    assert len(set(ladder)) == len(ladder), f"a rung repeats: {ladder}"
    assert D.DEEPSEEK_REASONING_EFFORT not in ladder, \
        f"rung re-sends the worker's own default ({D.DEEPSEEK_REASONING_EFFORT}): {ladder}"
    assert ladder[0] == D.DEEPSEEK_REASONING_EFFORT_AFTER_EMPTY, \
        "rung 0 must be the documented after-empty step-down"


def test_the_ladder_never_disables_thinking_implicitly():
    """`thinking` is sent as enabled on every call, so a rung that DISABLES
    thinking would contradict it, and the precedence of that contradiction is
    undocumented -- so no rung may be `none` (or the profile's `off`) until it
    has been probed. Every rung must be a member of this box's own documented
    thinking-level vocabulary (resource_profile.THINKING_LEVELS)."""
    documented = ("max", "high", "medium", "low")   # THINKING_LEVELS minus "off"
    ladder = D.DEEPSEEK_REASONING_EFFORT_LADDER
    assert "none" not in ladder and "off" not in ladder
    for rung in ladder:
        assert rung in documented, f"undocumented rung {rung!r} in {ladder}"
    # PD-TEST-124: rung 0 stepped DOWN with the default (max -> medium moved the
    # step-down medium -> low). It is no longer `medium`, because `medium` is
    # now the default and a rung equal to the default is a dead rung.
    assert ladder[0] == "low"
    assert ladder[0] != D.DEEPSEEK_REASONING_EFFORT


def test_the_rung_is_clamped_so_a_long_failure_history_still_retries(p4_env):
    """A unit with far more attempts than rungs must still get a valid rung,
    never an IndexError and never a silent repeat of the top rung."""
    p4_env["monkeypatch"].setattr(
        D, "dispatch_complete", _empty_for(p4_env, "Teach", EMPTY_USAGE_LENGTH))
    for _ in range(len(D.DEEPSEEK_REASONING_EFFORT_LADDER) + 2):
        p4_env["calls"].clear()
        _dispatch(p4_env)
    assert _effort_for(p4_env, "Teach") == [D.DEEPSEEK_REASONING_EFFORT_LADDER[-1]]


# ---------------------------------------------------------------------------
# 3. THE WIRE -- finish_reason must come off the response, not be invented.
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
    import types
    sent: list = []
    reply = json.dumps({
        "choices": [{"message": {"content": ""}, "finish_reason": "length"}],
        "usage": {"completion_tokens": 64_000,
                  "completion_tokens_details": {"reasoning_tokens": 63_998}},
    }).encode()

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


def test_wire_captures_finish_reason_off_the_response(wire):
    content, usage = D.deepseek_complete("sys", "user", retries=1)
    assert content == ""
    assert usage["finish_reason"] == "length", usage
    # The provider's own numbers are untouched.
    assert usage["completion_tokens"] == 64_000
    assert usage["completion_tokens_details"]["reasoning_tokens"] == 63_998


def test_the_captured_usage_reproduces_the_live_failure_reason(wire):
    """End-to-end: the phrase the NEXT incident will be read from."""
    _content, usage = D.deepseek_complete("sys", "user", retries=1)
    detail = D._empty_completion_detail(usage)
    assert "reasoning_tokens=63998 of max_tokens=64000" in detail, detail
    assert "finish_reason='length'" in detail, detail
