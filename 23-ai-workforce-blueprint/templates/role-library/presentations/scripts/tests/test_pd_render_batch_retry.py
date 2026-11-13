"""PD-070 -- RETRY A FAILED SLIDE INSIDE THE BATCH.

Acceptance (acc.txt PD-070, the unit's single A1 row):
  (a) a stubbed service that fails slide 3 once -> slide 3 submitted TWICE,
      every other slide submitted ONCE, result has NO failures;
  (b) fails 6 times -> ONE failure listed (the SLIDE_MAX_ATTEMPTS ladder);
  (c) an authentication error -> NO retry.

The proof is the ARTEFACT, not a returned value:

  * the WIRE -- every createTask the stub service actually receives, in order,
    is recorded per slide ordinal (the submitted prompt names the slide);
  * the DISK -- every rendered slide's PNG is asserted to exist in renders/,
    and working/checkpoints/pending_tasks.json is read back and must point at
    the task id of the SUCCESSFUL submit (the dead task's record cleared).

Before PD-070 the batch parked a failed slide in `failures` and never
re-submitted, so (a) read `slide 3 submitted once` + one failure -- both
assertions below go RED on the pre-fix file.
"""
import json
import sys
import time
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

import build_deck as bd  # noqa: E402


# ---------------------------------------------------------------------------
# Stub KIE service -- records the real createTask wire calls
# ---------------------------------------------------------------------------
class _StubService:
    """createTask records (wall_time, slide ordinal) from the submitted prompt;
    recordInfo fails a configured number of times for one slide, then succeeds.
    An ordinal in `auth_ordinals` raises AuthError at createTask (permanent)."""

    def __init__(self):
        self.wire = []                 # [(wall_time, ordinal, prompt)]
        self.task_seq = 0
        self.task_ordinal = {}         # task_id -> ordinal
        self.failures_left = {}        # ordinal -> terminal failures still owed
        self.auth_ordinals = set()     # submit-side 401
        self.poll_auth_ordinals = set()  # poll-side 403

    def createTask(self, api_key, prompt, logo_url):
        # submit_task APPENDS the mandatory English pin, so the slide marker is
        # parsed out of the body rather than off the end of the prompt.
        import re as _re
        ordinal = int(_re.search(r"prompt-(\d+)", prompt).group(1))
        self.wire.append((time.time(), ordinal, prompt))
        if ordinal in self.auth_ordinals:
            raise bd.AuthError("HTTP 401 from createTask (stub)")
        self.task_seq += 1
        tid = f"task-{self.task_seq}"
        self.task_ordinal[tid] = ordinal
        return {"code": 200, "data": {"taskId": tid}}

    def recordInfo(self, task_id):
        ordinal = self.task_ordinal[task_id]
        if ordinal in self.poll_auth_ordinals:
            raise bd.AuthError("HTTP 403 from recordInfo (stub)")
        if self.failures_left.get(ordinal, 0) > 0:
            self.failures_left[ordinal] -= 1
            return {"code": 200, "data": {"state": "failed", "failCode": 500,
                                          "failMsg": "stub terminal failure"}}
        return {
            "code": 200,
            "data": {
                "state": "success",
                "resultJson": json.dumps(
                    {"resultUrls": [f"http://cdn.example/{task_id}.png"]}),
            },
        }

    def submitted_count(self, ordinal):
        return sum(1 for _, o, _ in self.wire if o == ordinal)


def _install(monkeypatch):
    """Wire the stub into build_deck and collapse every sleep so the retry
    ladder runs instantly. Gates outside this unit's scope are stubbed exactly
    as tests/test_batch_render.py stubs them."""
    svc = _StubService()
    from urllib.parse import parse_qs, urlparse

    def _fake_http_json(method, url, api_key, body=None):
        if "recordInfo" in url:
            q = parse_qs(urlparse(url).query)
            return svc.recordInfo(q.get("taskId", [""])[0])
        if "createTask" in url:
            return svc.createTask(api_key,
                                  (body or {}).get("input", {}).get("prompt", ""),
                                  (body or {}).get("input", {}).get("input_urls"))
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr(bd, "_http_json", _fake_http_json)

    def _fake_download(url, dest, api_key=None):
        Path(dest).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)

    monkeypatch.setattr(bd, "download_image", _fake_download)
    monkeypatch.setattr(bd, "load_rich_prompt",
                        lambda slide, run_dir: f"prompt-{int(slide['slide'])}")
    monkeypatch.setattr(bd, "_verify_aspect_and_readback", lambda *a, **k: None)
    # The retry ladder's backoff must not spend real seconds in a test.
    monkeypatch.setattr(bd, "SLIDE_BACKOFF_BASE", 0.0)
    monkeypatch.setattr(bd, "RATE_LIMIT_SLEEP_S", 0.0)
    return svc


def _slides(n):
    return [{"slide": i, "scene": f"scene-{i}", "copy": ["H"]} for i in range(1, n + 1)]


def _run(tmp_path, svc, n=5):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    renders = tmp_path / "renders"
    result = bd.render_slides_batch(
        _slides(n), api_key="stub-key", renders_dir=renders, run_dir=run_dir,
        submit_interval=0.0, poll_interval=0.01, max_seconds=30.0)
    return result, renders, run_dir


# ---------------------------------------------------------------------------
# A1(a) -- slide 3 fails ONCE: re-submitted, all siblings exactly once, no failures
# ---------------------------------------------------------------------------
def test_failed_slide_is_resubmitted_once_and_batch_has_no_failures(tmp_path, monkeypatch):
    svc = _install(monkeypatch)
    svc.failures_left[3] = 1

    result, renders, run_dir = _run(tmp_path, svc)

    # WIRE: slide 3 hit createTask twice; every other slide exactly once.
    by_slide = {o: svc.submitted_count(o) for o in range(1, 6)}
    assert by_slide == {1: 1, 2: 1, 3: 2, 4: 1, 5: 1}, (
        f"wire submissions per slide: {by_slide}; full wire: "
        f"{[o for _, o, _ in svc.wire]}")
    assert len(svc.wire) == 6

    # RESULT: the retried slide counts as rendered, nothing is listed as failed.
    assert result["failures"] == [], f"unexpected failures: {result['failures']}"
    assert sorted(r["slide"] for r in result["rendered"]) == [1, 2, 3, 4, 5]

    # DISK: all five renders exist and every rendered file is a PNG on disk.
    for ordinal in range(1, 6):
        p = renders / f"{bd.slide_name(ordinal)}.png"
        assert p.is_file(), f"missing render {p}"
        assert p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    # DISK: the checkpoint points at the WINNING task of slide 3 (the failed one
    # was cleared -- no future resume can re-poll the dead id).
    ckpt = json.loads((run_dir / "working" / "checkpoints" / "pending_tasks.json").read_text())
    live_tid = result["rendered"][2]["taskId"]
    assert ckpt["3"]["completed"] is True
    assert ckpt["3"]["task_id"] == live_tid, (
        f"checkpoint kept dead task: {ckpt['3']} (live={live_tid})")


# ---------------------------------------------------------------------------
# A1(b) -- fails on EVERY attempt: one failure row, not six
# ---------------------------------------------------------------------------
def test_six_failures_yield_exactly_one_failure(tmp_path, monkeypatch):
    svc = _install(monkeypatch)
    monkeypatch.setattr(bd, "SLIDE_MAX_ATTEMPTS", 6)  # the documented default
    svc.failures_left[3] = 6

    result, renders, run_dir = _run(tmp_path, svc)

    # WIRE: the ladder ran all six rungs for slide 3, once for everyone else.
    assert svc.submitted_count(3) == 6, (
        f"expected 6 submissions for slide 3, got {svc.submitted_count(3)}")
    for ordinal in (1, 2, 4, 5):
        assert svc.submitted_count(ordinal) == 1

    # RESULT: exactly ONE failure row, naming slide 3.
    assert len(result["failures"]) == 1, f"failures: {result['failures']}"
    assert result["failures"][0]["slide"] == 3

    # DISK: slide 3 has no render; the other four do.
    assert not (renders / f"{bd.slide_name(3)}.png").exists()
    for ordinal in (1, 2, 4, 5):
        assert (renders / f"{bd.slide_name(ordinal)}.png").is_file()


# ---------------------------------------------------------------------------
# A1(c) -- authentication error is permanent: one submit, zero retries
# ---------------------------------------------------------------------------
def test_auth_error_is_never_retried(tmp_path, monkeypatch):
    svc = _install(monkeypatch)
    svc.auth_ordinals.add(3)

    result, renders, run_dir = _run(tmp_path, svc)

    # WIRE: exactly one createTask for slide 3 -- the 401 was never re-sent.
    assert svc.submitted_count(3) == 1, (
        f"auth error was retried: {svc.submitted_count(3)} submissions")
    for ordinal in (1, 2, 4, 5):
        assert svc.submitted_count(ordinal) == 1

    # RESULT: one failure row; the rest of the deck still rendered.
    assert len(result["failures"]) == 1
    assert result["failures"][0]["slide"] == 3
    assert "401" in result["failures"][0]["error"]
    assert sorted(r["slide"] for r in result["rendered"]) == [1, 2, 4, 5]
    assert not (renders / f"{bd.slide_name(3)}.png").exists()

# ---------------------------------------------------------------------------
# A1(c) second half -- a POLL-side auth error is also permanent: the poll
# failure must never trigger the retry path's re-submit.
# ---------------------------------------------------------------------------
def test_poll_auth_error_is_never_retried(tmp_path, monkeypatch):
    svc = _install(monkeypatch)
    svc.poll_auth_ordinals.add(3)

    result, renders, run_dir = _run(tmp_path, svc)

    # WIRE: one createTask for slide 3 -- the 403 did not buy a re-submit.
    assert svc.submitted_count(3) == 1, (
        f"poll auth error was retried: {svc.submitted_count(3)} submissions")
    for ordinal in (1, 2, 4, 5):
        assert svc.submitted_count(ordinal) == 1

    assert len(result["failures"]) == 1
    assert result["failures"][0]["slide"] == 3
    assert "403" in result["failures"][0]["error"]
    assert not (renders / f"{bd.slide_name(3)}.png").exists()
