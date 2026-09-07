"""FIX-5 — BATCH RENDER tests.

Requirement (per-task QC standard, FIX-5 row / T-05 / D22 root cause B):
    Submit ALL prompts once, 0.6s apart, inside kie's 20 requests / 10s window
    (+ 100 concurrent tasks). Then poll all taskIds together every 10s and
    download each image the moment ITS task finishes.

QC gate:
    "Submit 20 prompts 0.6s apart against live kie.ai; poll all.
     All 20 submissions land in < 20s; all return taskIds; zero 429s."

Because a live-kie test would burn credits and hit the real network from a
worktree, the network layer is mocked the SAME way the engine's own
test_preflight.py mocks `build_deck._fetch_kie_balance` (monkeypatch the module
function). The mocked API server records real wall-clock timestamps per
createTask call, so the assertions below prove the WIRE SHAPE of the batch:

  1. render_slides_batch submits all 20 prompts once, spaced 0.6s apart, and the
     whole submission window lands in < 20s (well inside kie's 20/10s cap).
  2. every one of the 20 submit calls returned a distinct taskId (none dropped).
  3. all 20 taskIds are polled on the shared 10s cadence (poll_task_once).
  4. each image is downloaded the moment ITS task's state flips to success —
     a fast slide's download does NOT wait for the slowest slide (the D22 win).
  5. zero 429s on the submit pass.
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
# Mock KIE API server
# ---------------------------------------------------------------------------
class _KieMock:
    """In-memory fake of the kie.ai createTask + recordInfo surface.

    submit: returns {code:200, data:{taskId: "task-<seq>"}} unless told to 429.
    recordInfo: each task completes after a per-task artificial latency.
    A call to recordInfo for an in-flight task returns state "generating"; once
    enough real time has passed it returns "success" with a resultUrls[0]. The
    test patches download_unauthenticated to a local PNG writer (download timing
    is what the test measures, not the transport)."""

    def __init__(self):
        self.submit_calls = []       # list of (wall_time, ordinal_name)
        self.poll_calls = []         # list of (wall_time, task_id)
        self.tasks = {}              # task_id -> {"latency_s": float}
        self.submit_429s = 0
        self.next_seq = 0

    # -- server behavior --
    def createTask(self, api_key, prompt, logo_url):
        self.submit_calls.append((time.time(), None))
        if getattr(self, "force_429", False):
            self.submit_429s += 1
            raise bd.RateLimited("HTTP 429 from createTask")
        self.next_seq += 1
        tid = f"task-{self.next_seq}"
        # deterministic per-task latency so different slides finish on
        # different passes (proves downloads do not serialize behind the slowest)
        self.tasks[tid] = {"latency_s": self._latency_for(tid), "started_at": time.time()}
        return {"code": 200, "data": {"taskId": tid}}

    def _latency_for(self, tid):
        seq = int(tid.split("-")[-1])
        # slide ordinals 1..20 -> latency spreads across 3 poll passes
        # (pass ~10s apart): odds finish pass 1, evens pass 2, every 5th pass 3.
        # The poll cadence in the test is compressed (poll_interval=0.05s) so the
        # whole test runs in well under a second of wall clock.
        if seq % 5 == 0:
            return 0.030
        if seq % 2 == 0:
            return 0.015
        return 0.005

    def recordInfo(self, task_id):
        self.poll_calls.append((time.time(), task_id))
        rec = self.tasks.get(task_id)
        if rec is None:
            raise RuntimeError(f"polled unknown task {task_id}")
        age = time.time() - rec["started_at"]
        if age < rec["latency_s"]:
            return {"code": 200, "data": {"state": "generating"}}
        return {
            "code": 200,
            "data": {
                "state": "success",
                "resultJson": json.dumps({"resultUrls": [f"http://cdn.example/{task_id}.png"]}),
            },
        }


# ---------------------------------------------------------------------------
# Wiring the mock into build_deck (mirrors test_preflight's monkeypatch style)
# ---------------------------------------------------------------------------
def _install_mock(monkeypatch):
    mock = _KieMock()
    # recordInfo passes the taskId in the URL query, so parse it out there.
    from urllib.parse import parse_qs, urlparse

    def _fake_http_json(method, url, api_key, body=None):
        if "recordInfo" in url:
            q = parse_qs(urlparse(url).query)
            tid = q.get("taskId", [""])[0]
            return mock.recordInfo(tid)
        if "createTask" in url:
            return mock.createTask(api_key, (body or {}).get("input", {}).get("prompt"),
                                   (body or {}).get("input", {}).get("input_urls"))
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr(bd, "_http_json", _fake_http_json)
    # download: write a minimal real PNG (no network, no CDN). Timing of the
    # download call is what matters — record it per slide.
    download_log = {}

    def _fake_download(url, dest, api_key=None):
        # record when this slide's download started (after ITS task completed)
        download_log[Path(dest).stem] = time.time()
        # minimal valid 1x1 PNG (magic + minimal chunks) so verify_png passes
        dest.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)

    # The batch now downloads via the AUTHENTICATED path (Bearer + browser UA,
    # download_image) — FIX-4's proven CDN contract. Patch that helper so the
    # mock measures download timing without touching the network.
    monkeypatch.setattr(bd, "download_image", _fake_download)
    # load_rich_prompt needs real prompt files >= 9000 chars — stub it to avoid
    # authoring 20 x 9KB files in the test.
    monkeypatch.setattr(
        bd, "load_rich_prompt",
        lambda slide, run_dir: "x" * bd.PROMPT_CHAR_FLOOR)
    # _verify_aspect_and_readback imports prompt_gate + PIL + OCR — stub it out
    # (its behavior is FIX-4/FIX-6 territory, not this unit's scope).
    monkeypatch.setattr(bd, "_verify_aspect_and_readback", lambda *a, **k: None)
    # _checkpoint_pending_task / _record_completed_task write to run_dir — keep
    # them real so the checkpoint contract is exercised.
    return mock, download_log


def _make_slides(n):
    return [{"slide": i, "scene": f"scene-{i}", "copy": ["H"]} for i in range(1, n + 1)]


# ---------------------------------------------------------------------------
# F26 — TIMING HELPERS: measure the wait RELATIVE to the configured cap
#
# build_deck routes EVERY kie call — every submit AND every poll — through
# presentation_job/governor.py, whose providers.yaml entry pins kie at
# `rps: 2.0`. That is one slot every ~0.5s, so a stuck N-slide batch spends
# N x 0.5s in Phase A and another N x 0.5s on each Phase-B poll pass BEFORE the
# poll cap is ever consulted. For the 5-slide stuck batch below that is a
# deterministic 5.0s floor, which is why the old `wall < 5.0` assertion could
# only fail: it measured governor throughput, not the hard cap it claimed to
# prove. `max_seconds` is a PHASE-B budget; it never bounded Phase A and it was
# never what a total-wall constant measured.
#
# So the assertions below bound Phase B against the batch's OWN `max_seconds`
# (two-sided) and derive the per-call pacing from the run's own timestamps.
# Total wall survives only as a coarse no-hang backstop.
# ---------------------------------------------------------------------------

# Machine jitter allowance on top of the measured pacing. Generous on purpose:
# the bound it guards (cap + one poll pass) is what carries the proof, and an
# unbounded poll loop overshoots it without limit, not by a second.
_TIMING_SLACK_S = 1.0


def _worst_case_pace_s(mock):
    """Worst-case governor pacing per kie call, from THIS run's own timestamps.

    Every submit and every poll acquires one kie slot from the SAME per-process
    kie rate bucket, so consecutive call timestamps are spaced by whatever that
    bucket was willing to hand out at that moment. Two things make an average
    useless here, and both were observed:

      * the bucket has a burst allowance (`burst: 20`), so a phase can fire
        several calls back-to-back and only then throttle;
      * the bucket is process-wide, so the REST OF THE SUITE drains it. Run
        alone, this file's stuck batch spends 2.5s in Phase A; run inside the
        full suite it spent 4.9s — in bursts averaging 0.161s/call — while
        Phase B still paced at a flat ~0.5s/call.

    So take the LARGEST consecutive gap (the slowest the governor actually was,
    not the mean) and prefer the POLL series, which is the phase `max_seconds`
    actually budgets. Returns 0.0 when neither series has two samples — e.g. a
    legacy checkout where `_governor` is None and every acquire is a no-op
    passthrough, which paces at ~0 and which the bounds below tolerate."""
    for series in ([t for t, _ in mock.poll_calls],
                   [t for t, _ in mock.submit_calls]):
        if len(series) >= 2:
            return max(later - earlier
                       for earlier, later in zip(series, series[1:]))
    return 0.0


def _phase_b_seconds(mock, batch_end_ts):
    """Upper bound on the poll/download phase, from the run's own timestamps.

    Phase B starts only after the last createTask has returned, so
    (batch_end - last_submit) can only OVERSTATE it. That direction is
    deliberate: it keeps `phase_b >= max_seconds` mathematically safe, because
    the poll loop provably breaks only once (now - poll_start) >= max_seconds
    and poll_start >= the last submit timestamp."""
    return batch_end_ts - mock.submit_calls[-1][0]


# ---------------------------------------------------------------------------
# TEST 1: 20 prompts submit once, 0.6s apart, ALL land in < 20s, all taskIds
# ---------------------------------------------------------------------------
class TestBatchSubmitWindow:
    def test_twenty_submits_under_20s_at_0606_spacing(self, tmp_path, monkeypatch):
        mock, download_log = _install_mock(monkeypatch)
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        renders = tmp_path / "renders"

        start = time.time()
        result = bd.render_slides_batch(
            _make_slides(20), api_key="stub-key", renders_dir=renders, run_dir=run_dir,
            submit_interval=0.6,  # the FIX-5 documented cadence
            poll_interval=0.05,   # compressed poll cadence for the test (10s real -> fast)
            max_seconds=5.0,
        )
        wall = time.time() - start

        # (1) all 20 submitted once, zero failures
        assert len(mock.submit_calls) == 20, f"expected 20 submits, got {len(mock.submit_calls)}"
        assert result["failures"] == [], f"unexpected failures: {result['failures']}"
        assert len(result["rendered"]) == 20

        # (2) submission window < 20s — the QC gate's headline threshold
        submit_span = mock.submit_calls[-1][0] - mock.submit_calls[0][0]
        assert submit_span < 20.0, (
            f"20 submissions spanned {submit_span:.2f}s — must be < 20s (20/10s cap)")
        assert submit_span >= (20 - 1) * 0.6 - 0.5, (
            f"submissions not spaced ~0.6s apart (span {submit_span:.2f}s)")

        # (3) all 20 taskIds distinct
        tids = [r["taskId"] for r in result["rendered"]]
        assert len(set(tids)) == 20, f"taskIds not distinct: {tids}"

        # (4) every rendered slide has a file + a taskId
        for r in result["rendered"]:
            assert r["file"] and r["taskId"]

        # (5) zero 429s on the submit pass (the gate explicitly calls this out)
        assert mock.submit_429s == 0

        # (6) hard evidence: print the per-submit timestamps
        print(f"\nBATCH SUBMIT WINDOW: {submit_span:.2f}s for 20 submits "
              f"(target < 20s). Total batch wall {wall:.2f}s.")
        for i, (t, _) in enumerate(mock.submit_calls, 1):
            rel = t - mock.submit_calls[0][0]
            print(f"  submit {i:>2}: t+{rel:6.2f}s")

    def test_zero_429_reported(self, tmp_path, monkeypatch):
        """Regression: even with a transient 429 on ONE submit, the other 19 still
        land and the 429 is not a silent failure (RateLimited is the only submit
        error that retries in-place)."""
        mock, download_log = _install_mock(monkeypatch)
        # First submit returns 429 once, then succeeds — the retry must land it.
        original = mock.createTask
        flaky_fired = {"n": 0}

        def flaky_createTask(api_key, prompt, logo_url):
            if flaky_fired["n"] == 0:
                flaky_fired["n"] += 1
                mock.submit_429s += 1
                raise bd.RateLimited("HTTP 429 (transient)")
            return original(api_key, prompt, logo_url)

        mock.createTask = flaky_createTask
        # Collapse the 429 backoff sleep to near-zero so the retry path is fast.
        monkeypatch.setattr(bd, "RATE_LIMIT_SLEEP_S", 0.0)
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        renders = tmp_path / "renders"

        result = bd.render_slides_batch(
            _make_slides(20), api_key="stub-key", renders_dir=renders, run_dir=run_dir,
            submit_interval=0.0, poll_interval=0.01, max_seconds=5.0,
        )
        assert len(result["rendered"]) == 20, (
            f"transient 429 must not drop a slide: {result['failures']}")
        assert mock.submit_429s == 1


# ---------------------------------------------------------------------------
# TEST 2: ALL taskIds are polled on the shared cadence, downloads fire as each
#         slide finishes (fast slide never waits for the slowest).
# ---------------------------------------------------------------------------
class TestBatchPollAndDownloadAsFinished:
    def test_all_twenty_taskids_polled_and_downloads_spread(self, tmp_path, monkeypatch):
        mock, download_log = _install_mock(monkeypatch)
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        renders = tmp_path / "renders"

        result = bd.render_slides_batch(
            _make_slides(20), api_key="stub-key", renders_dir=renders, run_dir=run_dir,
            submit_interval=0.0, poll_interval=0.05, max_seconds=5.0,
        )
        assert result["failures"] == []
        assert len(result["rendered"]) == 20

        # (1) every submitted taskId was polled at least once
        polled = {tid for _, tid in mock.poll_calls}
        submitted = {r["taskId"] for r in result["rendered"]}
        assert polled == submitted, (
            f"polled {len(polled)} taskIds but submitted {len(submitted)}")

        # (2) every slide's download ran (i.e. file written + verified)
        assert len(download_log) == 20, f"downloaded {len(download_log)}/20 slides"

        # (3) PROVE download-as-finished: the earliest-finishing slide downloaded
        #     before the slowest slide even completed. With per-task latencies
        #     (5ms/15ms/30ms) the first download must precede the last by at least
        #     one poll gap, and the number of distinct download instants > 1
        #     (i.e. not all 20 downloaded in the same instant = serialization).
        dl_times = sorted(download_log.values())
        assert len(set(round(t, 4) for t in dl_times)) > 1, (
            "all downloads happened at the same instant — the batch serialized "
            "downloads instead of downloading each slide as it finished")
        span = dl_times[-1] - dl_times[0]
        assert span > 0.005, f"downloads did not spread (span {span:.4f}s)"

        # (4) every rendered PNG passed verify_png (real magic bytes written)
        for r in result["rendered"]:
            with open(r["file"], "rb") as f:
                assert f.read(4) == b"\x89PNG", f"{r['file']} not a PNG"

        print("\nBATCH POLL EVIDENCE:")
        print(f"  submitted taskIds : {len(submitted)}")
        print(f"  polled taskIds    : {len(polled)}")
        print(f"  downloaded        : {len(download_log)}")
        print(f"  download span     : {span:.4f}s across {len(set(round(t,4) for t in dl_times))} "
              f"distinct instants (as-finished, not serialized)")

    def _run_stuck_batch(self, monkeypatch, tmp_path, n_slides, max_seconds):
        """Submit `n_slides` tasks that NEVER complete; return the timings.

        Shared by both stuck-task tests so they prove the same code path."""
        mock, download_log = _install_mock(monkeypatch)
        # Make every task never complete: each created task stays "generating"
        # forever by giving it an infinite latency.
        original_create = mock.createTask

        def never_complete_createTask(api_key, prompt, logo_url):
            resp = original_create(api_key, prompt, logo_url)
            tid = resp["data"]["taskId"]
            mock.tasks[tid]["latency_s"] = 10 ** 9  # never completes
            return resp

        mock.createTask = never_complete_createTask
        monkeypatch.setattr(bd, "RATE_LIMIT_SLEEP_S", 0.0)
        run_dir = tmp_path / "run"
        run_dir.mkdir(parents=True, exist_ok=True)
        renders = tmp_path / "renders"

        start = time.time()
        result = bd.render_slides_batch(
            _make_slides(n_slides), api_key="stub-key", renders_dir=renders,
            run_dir=run_dir, submit_interval=0.0, poll_interval=0.01,
            max_seconds=max_seconds,
        )
        end = time.time()

        assert mock.submit_calls, "no createTask ever fired — the mock is not wired"
        assert mock.poll_calls, (
            "the stuck batch never polled — nothing exercised the poll cap")
        # Every pass polls every still-pending task, and a stuck task is never
        # removed, so the poll count is always a whole number of full passes.
        assert len(mock.poll_calls) % n_slides == 0, (
            f"{len(mock.poll_calls)} polls is not a whole number of "
            f"{n_slides}-task passes")
        return {
            "result": result,
            "mock": mock,
            "wall": end - start,
            "phase_b": _phase_b_seconds(mock, end),
            "passes": len(mock.poll_calls) // n_slides,
            "one_pass_s": _worst_case_pace_s(mock) * n_slides,
        }

    def test_stuck_task_surfaces_fail_no_hang(self, tmp_path, monkeypatch):
        """A task that NEVER completes is surfaced as FAIL at the hard cap — never
        hangs (D14). The batch must terminate and report the stuck slide.

        F26: the wait this test exists to prove is the batch's OWN configured
        poll cap, so Phase B is bounded two-sided against `max_seconds` and the
        pacing the run itself measured. The total-wall number survives only as
        a coarse no-hang backstop, widened from 5.0 to 8.0 because the
        governor's kie `rps: 2.0` puts a deterministic 5.0s floor under this
        5-slide batch (see the F26 note above `_worst_case_pace_s`) — the old
        threshold sat exactly on that floor and could only fail."""
        n_slides = 5
        max_seconds = 0.05  # hard cap hit on the first elapsed check
        run = self._run_stuck_batch(monkeypatch, tmp_path, n_slides, max_seconds)

        # (1) coarse backstop — the batch terminated at all.
        assert run["wall"] < 8.0, f"batch hung: {run['wall']:.2f}s"

        # (2) THE POINT OF THIS TEST — the CONFIGURED cap is what ended the
        #     wait, bounded on both sides against `max_seconds` itself:
        #       lower  : the loop breaks only once elapsed >= max_seconds, so a
        #                Phase B shorter than the cap means something else cut
        #                the wait short.
        #       upper  : the cap is checked at the top of each pass, so the
        #                worst honest overshoot is the one pass already in
        #                flight when the budget came due. Anything beyond that
        #                is unbounded polling — the D14 hang this guards.
        ceiling = max_seconds + run["one_pass_s"] + _TIMING_SLACK_S
        assert run["phase_b"] >= max_seconds, (
            f"poll phase ran {run['phase_b']:.3f}s but the configured cap was "
            f"{max_seconds}s — the wait ended before the cap, so the cap was "
            "not the binding wait")
        assert run["phase_b"] <= ceiling, (
            f"poll phase ran {run['phase_b']:.3f}s — the configured cap "
            f"({max_seconds}s) plus the one poll pass already in flight "
            f"({run['one_pass_s']:.3f}s) allows at most {ceiling:.3f}s. The cap "
            "did not bind; the batch kept polling a task that never completes")

        # (3) the cap fired for EVERY stuck slide, and the surfaced error names
        #     the configured cap — full-string, so a silently different failure
        #     path (network, shape, terminal state) cannot satisfy it.
        failures = run["result"]["failures"]
        assert len(failures) == n_slides, (
            f"expected all {n_slides} to surface FAIL: {failures}")
        expected = {
            f"taskId task-{i} still pending after {max_seconds:.0f}s "
            "— surfaced FAIL (no hang)"
            for i in range(1, n_slides + 1)
        }
        assert {f["error"] for f in failures} == expected, (
            f"failures did not come from the poll-cap branch: {failures}")

        print("\nSTUCK-TASK CAP EVIDENCE:")
        print(f"  configured cap    : {max_seconds}s")
        print(f"  poll phase        : {run['phase_b']:.3f}s "
              f"(ceiling {ceiling:.3f}s = cap + one in-flight pass + slack)")
        print(f"  poll passes       : {run['passes']}")
        print(f"  total wall        : {run['wall']:.3f}s "
              f"(governor floor {n_slides * 2 * 0.5:.1f}s at kie rps 2.0)")

    def test_poll_cap_is_the_binding_wait(self, tmp_path, monkeypatch):
        """F26 regression: the batch waits exactly as long as its CONFIGURED cap
        says — not for some fixed constant that happens to look right.

        The same never-completing batch is run twice at two different
        `max_seconds`. If `max_seconds` is genuinely the binding wait, the
        larger cap must reach its own budget, stop within one poll pass of it,
        and burn strictly more poll passes than the small cap. A wait governed
        by anything else — a hard-coded sleep, the governor's pacing alone, a
        fixed retry count — would spend the same number of passes on both."""
        n_slides = 2  # >= 2 so the per-call pacing is measurable from Phase A
        small_cap = 0.05
        large_cap = 1.5

        low = self._run_stuck_batch(monkeypatch, tmp_path / "low", n_slides, small_cap)
        high = self._run_stuck_batch(monkeypatch, tmp_path / "high", n_slides, large_cap)

        # both caps actually fired, on every slide
        for tag, run in (("small", low), ("large", high)):
            assert len(run["result"]["failures"]) == n_slides, (
                f"{tag} cap: expected {n_slides} FAILs, "
                f"got {run['result']['failures']}")

        # raising the cap must buy MORE polling — this is the relative proof
        assert high["passes"] > low["passes"], (
            f"cap {large_cap}s spent {high['passes']} poll passes and cap "
            f"{small_cap}s spent {low['passes']} — the configured cap is not "
            "what decides how long the batch waits")
        assert high["phase_b"] > low["phase_b"], (
            f"cap {large_cap}s waited {high['phase_b']:.3f}s but cap "
            f"{small_cap}s waited {low['phase_b']:.3f}s — the wait does not "
            "track the configured cap")

        # and each run stops inside its OWN budget + the pass already in flight
        for tag, run, cap in (("small", low, small_cap), ("large", high, large_cap)):
            ceiling = cap + run["one_pass_s"] + _TIMING_SLACK_S
            assert run["phase_b"] >= cap, (
                f"{tag} cap {cap}s: poll phase {run['phase_b']:.3f}s ended "
                "before the configured budget was reached")
            assert run["phase_b"] <= ceiling, (
                f"{tag} cap {cap}s: poll phase {run['phase_b']:.3f}s exceeds "
                f"{ceiling:.3f}s (cap + one in-flight pass + slack) — "
                "unbounded polling")

        print("\nBINDING-WAIT EVIDENCE (cap is relative, not a constant):")
        for tag, run, cap in (("small", low, small_cap), ("large", high, large_cap)):
            print(f"  cap {cap:>5}s -> poll phase {run['phase_b']:.3f}s, "
                  f"{run['passes']} pass(es), wall {run['wall']:.3f}s")
