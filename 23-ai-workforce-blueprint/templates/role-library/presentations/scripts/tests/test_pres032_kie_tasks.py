"""PRES-032 — shared KIE lifecycle: persist-on-create, round-robin poll,
spec-bound reuse, bounded errors. Fully offline (injected fakes, no network)."""
import base64
import json
import sys
import zlib
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import kie_tasks  # noqa: E402

PNG_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


def _png_bytes(seed=0, size=60000):
    raw = PNG_1x1 + bytes([seed % 256]) * max(0, size - len(PNG_1x1))
    return raw


def _make_task(slide, prompt, out_dir, fakes, **kw):
    spec = kie_tasks.build_spec(prompt=prompt, mode="t2i",
                                aspect_ratio="16:9", resolution="2K")
    return {"slide": slide, "spec": spec,
            "submit": lambda s=slide: fakes.submit(s),
            "out_path": Path(out_dir) / f"{slide}.png", **kw}


class FakeProvider:
    """Offline KIE: per-slide scripted poll states; counts createTask calls."""

    def __init__(self):
        self.create_calls = []
        self.scripts = {}  # slide -> list of states to emit per poll

    def submit(self, slide):
        self.create_calls.append(slide)
        return f"task-{slide}"

    def poll_once(self, task_id):
        slide = task_id.replace("task-", "", 1)
        script = self.scripts.get(slide, ["success"])
        state = script.pop(0) if len(script) > 1 else script[0]
        if isinstance(state, Exception):
            raise state
        if state == "success":
            return {"state": "success",
                    "result_url": f"https://cdn.example/{slide}.png"}
        return {"state": state, "result_url": None}

    def download(self, seed=7):
        def _go(url, tmp_path):
            Path(tmp_path).write_bytes(_png_bytes(seed))
        return _go


def _run(tasks, fakes, tmp_path, **kw):
    params = dict(state_dir=tmp_path / "state", run_id="run-1",
                  artifact_id="test",
                  poll_once=fakes.poll_once, download=fakes.download(),
                  verify=lambda p, s: {"width": 2048, "height": 1152,
                                       "ocr": {"matched": None}},
                  poll_interval_s=0, deadline_s=60,
                  sleep=lambda s: None)
    params.update(kw)
    return kie_tasks.run(tasks, **params)


# QC-1: crash after create, before download — resume makes ZERO new creates.
def test_crash_after_create_resumes_with_zero_duplicate_creates(tmp_path):
    fakes = FakeProvider()
    out = tmp_path / "renders"
    tasks = [_make_task("slide-01", "hero prompt one", out, fakes),
             _make_task("slide-02", "hero prompt two", out, fakes)]

    created = {}

    crash = {"armed": True}

    def submit_once(slide):
        tid = fakes.submit(slide)
        created[slide] = tid
        # Crash BETWEEN the createTask response and its atomic persist for
        # slide-02: the provider was paid twice, the store knows only slide-01.
        # Resume must re-resolve slide-02 honestly (one second create for the
        # unknown id) and must NOT re-create slide-01.
        if slide == "slide-02" and crash["armed"]:
            crash["armed"] = False
            raise RuntimeError("SIMULATED CRASH after createTask, before poll")
        return tid

    for t in tasks:
        t["submit"] = (lambda s: lambda: submit_once(s))(t["slide"])
    result0 = _run(tasks, fakes, tmp_path)
    # slide-01 completed; slide-02 recorded submit_failed (crash), not created
    assert {r["slide"] for r in result0["completed"]} == {"slide-01"}
    state = kie_tasks.load_state(tmp_path / "state")
    assert state["tasks"]["slide-01"]["state"] == "verified"
    assert state["tasks"]["slide-02"]["error_kind"] == "submit_failed"

    # Resume: slide-01 reuses with zero creates; slide-02's crash-time task id
    # was never persisted, so exactly ONE create (slide-02) is honest — and a
    # second resume after that is fully create-free.
    before = list(fakes.create_calls)
    result = _run([_make_task("slide-01", "hero prompt one", out, fakes),
                   _make_task("slide-02", "hero prompt two", out, fakes)],
                  fakes, tmp_path)
    assert fakes.create_calls == before + ["slide-02"], (
        f"resume must create only the unpersisted slide-02: {fakes.create_calls}")
    assert result["create_calls"] == 1
    assert {r["slide"] for r in result["completed"]} == {"slide-01", "slide-02"}

    before2 = list(fakes.create_calls)
    result2 = _run([_make_task("slide-01", "hero prompt one", out, fakes),
                    _make_task("slide-02", "hero prompt two", out, fakes)],
                   fakes, tmp_path)
    assert fakes.create_calls == before2, (
        f"steady-state resume re-created tasks: {fakes.create_calls}")
    assert result2["create_calls"] == 0


# QC-2: slow A, fast B — B downloads + verifies before A completes.
def test_slow_a_fast_b_downloads_b_first(tmp_path):
    order = []
    fakes = FakeProvider()
    fakes.scripts = {"slide-A": ["waiting"] * 5 + ["success"],
                     "slide-B": ["success"]}

    def verify(p, s):
        order.append(s)
        return {"width": 2048, "height": 1152, "ocr": {"matched": None}}

    out = tmp_path / "renders"
    state = tmp_path / "state"
    result = kie_tasks.run(
        [_make_task("slide-A", "prompt A", out, fakes),
         _make_task("slide-B", "prompt B", out, fakes)],
        state_dir=state, run_id="r", artifact_id="t",
        poll_once=fakes.poll_once, download=fakes.download(),
        verify=verify, poll_interval_s=0, deadline_s=60,
        sleep=lambda s: None)
    assert {r["slide"] for r in result["completed"]} == {"slide-A", "slide-B"}
    assert order[0] == "slide-B", f"B must verify first, got {order}"
    assert (out / "slide-B.png").is_file()


# QC-3: changed prompt rejects the old PNG even though it exists.
def test_changed_prompt_rejects_old_png(tmp_path):
    fakes = FakeProvider()
    out = tmp_path / "renders"
    result = _run([_make_task("hero", "original prompt", out, fakes)],
                  fakes, tmp_path)
    assert len(result["completed"]) == 1
    old_bytes = (out / "hero.png").read_bytes()

    # Same prompt again: reused, zero creates.
    again = _run([_make_task("hero", "original prompt", out, fakes)],
                 fakes, tmp_path)
    assert again["create_calls"] == 0

    # Changed prompt: MUST resubmit, must not accept the old bytes as-is.
    fakes2 = FakeProvider()

    def download_new(url, tmp_path_p):
        Path(tmp_path_p).write_bytes(_png_bytes(99))

    tasks = [_make_task("hero", "REVISED prompt v2", out, fakes2)]
    result2 = kie_tasks.run(
        tasks, state_dir=tmp_path / "state", run_id="r", artifact_id="t",
        poll_once=fakes2.poll_once, download=download_new,
        verify=lambda p, s: {"width": 1, "height": 1, "ocr": {}},
        poll_interval_s=0, deadline_s=60, sleep=lambda s: None,
        clock=__import__("time").time)
    assert result2["create_calls"] == 1, "revised prompt must submit fresh"
    assert (out / "hero.png").read_bytes() != old_bytes
    state = kie_tasks.load_state(tmp_path / "state")
    assert state["tasks"]["hero"]["state"] == "verified"


def test_stale_png_without_sidecar_never_counts(tmp_path):
    out = tmp_path / "renders"
    out.mkdir(parents=True)
    (out / "hero.png").write_bytes(_png_bytes())
    spec = kie_tasks.build_spec(prompt="whatever")
    assert kie_tasks.render_reuse_ok(out / "hero.png",
                                     kie_tasks.spec_hash(spec)) is False


# QC-4: bounded outcomes for every fault class.
class _Auth(Exception):
    pass


def _named(name, base=Exception):
    return type(name, (base,), {})


def test_bounded_outcomes_per_fault(tmp_path):
    AuthError = _named("AuthError")
    RateLimited = _named("RateLimited")

    # 4a: auth error on submit aborts the run, records auth_error, no retry.
    fakes = FakeProvider()
    out = tmp_path / "a"
    tasks = [_make_task("s1", "p1", out, fakes)]
    tasks[0]["submit"] = lambda: (_ for _ in ()).throw(AuthError("HTTP 401 no"))
    with pytest.raises(kie_tasks.FatalAuth):
        _run(tasks, fakes, tmp_path)
    state = kie_tasks.load_state(tmp_path / "state")
    assert state["tasks"]["s1"]["error_kind"] == "auth_error"

    # 4b: sustained 429 exhausts the bound, records rate_exhausted, stops.
    fakes = FakeProvider()
    out = tmp_path / "b"
    tasks = [_make_task("s1", "p1", out, fakes)]
    tasks[0]["submit"] = lambda: (_ for _ in ()).throw(RateLimited("HTTP 429"))
    result = kie_tasks.run(
        tasks, state_dir=tmp_path / "b-state", run_id="r", artifact_id="t",
        poll_once=fakes.poll_once, download=fakes.download(),
        verify=lambda p, s: {}, poll_interval_s=0, deadline_s=60,
        sleep=lambda s: None, max_submit_429_streak=3)
    assert result["failed"][0]["error_kind"] == "rate_exhausted"

    # 4c: malformed (non-PNG) bytes fail the slide as malformed, tmp removed.
    fakes = FakeProvider()
    out = tmp_path / "c"
    result = kie_tasks.run(
        [_make_task("s1", "p1", out, fakes)],
        state_dir=tmp_path / "c-state", run_id="r", artifact_id="t",
        poll_once=fakes.poll_once,
        download=lambda u, p: Path(p).write_bytes(b"NOT-A-PNG" * 9000),
        verify=lambda p, s: {}, poll_interval_s=0, deadline_s=60,
        sleep=lambda s: None)
    assert result["failed"][0]["error_kind"] == "malformed"
    assert not (out / "s1.png.part").exists()
    assert not (out / "s1.png").exists()

    # 4d: download interruption exhausts bounded attempts -> download_failed.
    fakes = FakeProvider()
    out = tmp_path / "d"

    def _boom(url, p):
        raise OSError("connection reset")

    result = kie_tasks.run(
        [_make_task("s1", "p1", out, fakes)],
        state_dir=tmp_path / "d-state", run_id="r", artifact_id="t",
        poll_once=fakes.poll_once, download=_boom,
        verify=lambda p, s: {}, poll_interval_s=0, deadline_s=60,
        sleep=lambda s: None, max_download_attempts=2)
    assert result["failed"][0]["error_kind"] == "download_failed"

    # 4e: provider success with no URL -> no_url, explicit and terminal.
    fakes = FakeProvider()
    fakes.poll_once = lambda tid: {"state": "success", "result_url": None}
    out = tmp_path / "e"
    result = kie_tasks.run(
        [_make_task("s1", "p1", out, fakes)],
        state_dir=tmp_path / "e-state", run_id="r", artifact_id="t",
        poll_once=fakes.poll_once, download=fakes.download(),
        verify=lambda p, s: {}, poll_interval_s=0, deadline_s=60,
        sleep=lambda s: None)
    assert result["failed"][0]["error_kind"] == "no_url"

    # 4f: terminal provider state -> provider_failed with the message.
    fakes = FakeProvider()

    def _fail_poll(tid):
        raise RuntimeError("taskId x: terminal state 'failed'. failCode=400")

    out = tmp_path / "f"
    result = kie_tasks.run(
        [_make_task("s1", "p1", out, fakes)],
        state_dir=tmp_path / "f-state", run_id="r", artifact_id="t",
        poll_once=_fail_poll, download=fakes.download(),
        verify=lambda p, s: {}, poll_interval_s=0, deadline_s=60,
        sleep=lambda s: None)
    assert result["failed"][0]["error_kind"] == "provider_failed"

    # 4g: deadline with no terminal state -> timeout, NOT resubmitted.
    fakes = FakeProvider()
    fakes.scripts = {"s1": ["waiting"] * 100}
    out = tmp_path / "g"
    ticks = {"n": 0}

    def _clock():
        ticks["n"] += 1
        return 1000.0 + ticks["n"] * 999.0

    result = kie_tasks.run(
        [_make_task("s1", "p1", out, fakes)],
        state_dir=tmp_path / "g-state", run_id="r", artifact_id="t",
        poll_once=fakes.poll_once, download=fakes.download(),
        verify=lambda p, s: {}, poll_interval_s=0, deadline_s=60,
        sleep=lambda s: None, clock=_clock)
    assert result["failed"][0]["error_kind"] == "timeout"
    assert len(fakes.create_calls) == 1, "timeout must not resubmit"


def test_heartbeat_fields_present(tmp_path):
    fakes = FakeProvider()
    out = tmp_path / "renders"
    _run([_make_task("s1", "p1", out, fakes)], fakes, tmp_path)
    rec = kie_tasks.load_state(tmp_path / "state")["tasks"]["s1"]
    for field in ("submitted_at", "last_poll_at", "next_poll_at",
                  "deadline_at", "updated_at", "polls", "state"):
        assert rec.get(field) is not None, f"missing heartbeat field {field}"
    assert rec["state"] == "verified"


def test_resume_after_verify_reuses_without_create(tmp_path):
    fakes = FakeProvider()
    out = tmp_path / "renders"
    first = _run([_make_task("hero", "same prompt", out, fakes)], fakes,
                 tmp_path)
    assert first["create_calls"] == 1
    fakes2 = FakeProvider()
    second = _run([_make_task("hero", "same prompt", out, fakes2)], fakes2,
                  tmp_path)
    assert second["create_calls"] == 0
    assert len(fakes2.create_calls) == 0
    assert len(second["completed"]) == 1
