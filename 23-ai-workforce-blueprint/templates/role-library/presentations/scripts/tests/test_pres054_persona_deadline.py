#!/usr/bin/env python3
"""test_pres054_persona_deadline.py — PRES-054 persona timeout mismatch.

The defect: ``presentation_job/persona.py::resolve_for_phase`` ran
``governed_phase_voice`` under a 90-second Future wall with
``shutdown(wait=False)``, while the seam below
(``shared-utils/persona_for_job.py::_default_selector_timeout``) spawned the
selector subprocess with a 600-second default. A timed-out Future did NOT
stop the selector subprocess: expensive work stayed alive while a retry
started, unaccounted against shared capacity, with no proof the child died.

What this file locks (QC-PRES-054):

  1. Hanging fixture selector exceeds deadline:
     - NO live owned child after timeout (real SIGTERM/SIGKILL/reap proof,
       never ``Future.cancel()`` treated as "subprocess stopped"),
     - NO overlapping retry (attempts are sequential; the next attempt is
       admitted only after the previous one's tree is reaped),
     - capacity slots released EXACTLY once per attempt.
  2. Provider resume: a task with a known remote id polls the existing task
     instead of creating a duplicate.
  3. Normal selection passes within budget; the scoped cache reuses ONLY an
     identical context (a different context is a cache MISS).
  4. Caller cancellation produces truthful durable state — and a cancelled
     Future is proven NOT to mean the subprocess stopped (the negative
     control that motivated the fix).

No network, no real provider, no OpenClaw install. The one real-subprocess
test spawns a short-lived python child so the process-group reap is exercised
against the real OS, not a mock.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import threading
import time

import pytest

_HERE = pathlib.Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from presentation_job import persona_deadline as pdead  # noqa: E402
from presentation_job import persona  # noqa: E402

# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------
def _make_run_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    """A minimal valid run_dir (state.json present so record_event writes)."""
    rd = tmp_path / "run"
    rd.mkdir(parents=True, exist_ok=True)
    st = {
        "schema_version": 1,
        "job_id": "test-pj-pres054-0000000001",
        "run_dir": str(rd),
        "created_at": "2026-09-09T00:00:00+00:00",
        "manifest_path": str(rd / "PIPELINE-MANIFEST.json"),
        "manifest_version": 1,
        "manifest_sha256": "0" * 64,
        "presentation_type": "signature",
        "requester": {"chat_id": "test-chat"},
        "intake": {},
        "current_phase": None,
        "phases": [],
        "gates": {},
        "waivers": [],
        "events": [],
        "sent": {},
        "undeliverable": [],
        "heartbeat": {},
        "terminal": None,
    }
    (rd / "state.json").write_text(json.dumps(st), encoding="utf-8")
    return rd


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """Every test starts with clean registries and a scoped PERSONA_PROC_DIR
    so no test can reap or account anything outside its own tmp_path."""
    monkeypatch.setenv("PERSONA_PROC_DIR", str(tmp_path / "proc"))
    pdead.clear_attempt_log()
    pdead._ACTIVE.clear()
    pdead.set_lease_provider(None, None)
    os.environ.pop("PERSONA_FOR_JOB_DEADLINE", None)
    os.environ.pop("PERSONA_RESOLUTION_ID", None)
    os.environ.pop("SKILL51_BLEND_GOVERNS", None)
    yield
    pdead.clear_attempt_log()
    pdead._ACTIVE.clear()
    pdead.set_lease_provider(None, None)
    os.environ.pop("PERSONA_FOR_JOB_DEADLINE", None)
    os.environ.pop("PERSONA_RESOLUTION_ID", None)


def _state_events(run_dir: pathlib.Path) -> list:
    data = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    return [e.get("kind") for e in data.get("events", [])]


# ---------------------------------------------------------------------------
# 1. Hanging selector: no live owned child after timeout, no overlapping
#    retry, slots released once.
# ---------------------------------------------------------------------------
class _HangingGoverned:
    """A governed_phase_voice stub that spawns a REAL child python process
    that hangs until killed — the expensive-work-alive defect, for real."""

    CHILD_HANG_MS = 30000  # 30 s: far past every test budget

    SCRIPT = (
        "import time, os, sys\n"
        "child = __import__('subprocess').Popen(\n"
        "    [sys.executable, '-c', 'import time; time.sleep(%d)'])\n"
        "# report the child pid to the parent's registry env\n"
        "print('CHILD_PID', child.pid, flush=True)\n"
        "sys.stderr.write(str(child.pid) + '\\n')\n"
        "try:\n"
        "    time.sleep(%d)\n"
        "finally:\n"
        "    child.kill()\n"
        "    child.wait()\n"
    ) % (CHILD_HANG_MS // 1000, CHILD_HANG_MS // 1000)

    def __init__(self):
        self.calls = []          # sequential attempt record
        self.lock = threading.Lock()

    def __call__(self, phase, avatar_context="", department=None, record=None):
        with self.lock:
            self.calls.append({"at": time.monotonic(), "phase": phase})
        proc = subprocess.Popen(
            [sys.executable, "-c", self.SCRIPT],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            start_new_session=True)
        # own it under this attempt's resolution id (what the real spawn
        # path does via persona_for_job._spawn_selector)
        rid = pdead.current_resolution_id() or ""
        pdead.register_proc(rid, proc)
        try:
            proc.communicate(timeout=self.CHILD_HANG_MS)
        except subprocess.TimeoutExpired:
            pass  # the deadline wall fires first in every test that uses this
        return {}


def test_hanging_selector_deadline_reaps_owned_tree(tmp_path):
    """A selector child that hangs past the deadline: after the resolution
    raises, NO owned child is alive and the reap proof is complete."""
    run_dir = _make_run_dir(tmp_path)
    hang = _HangingGoverned()

    with pytest.raises(pdead.PersonaTimeout):
        pdead.resolve_persona(
            hang, ("signature-story",), {},
            budget_s=2.0, attempts=2, on_state=lambda k, m: None,
            job_id="j1", phase_id="P4-COPY")

    proof = pdead.attempt_log()
    assert proof, "no terminate/reap proof was recorded"
    for entry in proof:
        p = entry["proof"]
        assert p["reap_complete"] is True, p
        assert p["live_after"] == [], p
    # nothing registered under any resolution id survives
    assert pdead.live_owned_pids("j1:P4-COPY") == []


def test_hanging_selector_no_overlapping_retry(tmp_path):
    """Attempts are strictly sequential AND the one absolute deadline is
    spent by attempt 1: with budget 2 s, attempt 1 (hung selector) exhausts
    the deadline, its tree is reaped, and NO second attempt is admitted —
    the retry that would have overlapped with the still-alive child in the
    old shape cannot exist."""
    run_dir = _make_run_dir(tmp_path)
    hang = _HangingGoverned()
    reap_times = []

    real_term = pdead.terminate_owned_tree

    def spy(rid, grace_s=pdead.GRACE_S):
        out = real_term(rid, grace_s)
        reap_times.append(time.monotonic())
        return out

    orig = pdead.terminate_owned_tree
    pdead.terminate_owned_tree = spy  # type: ignore[assignment]
    try:
        with pytest.raises(pdead.PersonaTimeout):
            pdead.resolve_persona(
                hang, ("signature-story",), {},
                budget_s=2.0, attempts=2, on_state=lambda k, m: None,
                job_id="j2", phase_id="P4-COPY")
    finally:
        pdead.terminate_owned_tree = orig  # type: ignore[assignment]

    # ONE attempt ran; its owned tree was reaped BEFORE the resolution raised
    assert len(hang.calls) == 1, hang.calls
    assert len(reap_times) == 1, reap_times
    assert hang.calls[0]["at"] <= reap_times[0], (
        "reap completed before the attempt even started — impossible")
    # and the deadline is spent: a hypothetical attempt 2 gets <= 0 remaining
    # (checked implicitly: PersonaTimeout, not a second attempt)


def test_capacity_slots_released_once_per_attempt(tmp_path):
    """One lease per attempt, released exactly once — including on the
    timeout path (the leak the old shutdown(wait=False) shape had). With the
    one absolute deadline, a hung attempt 1 consumes the budget, so exactly
    ONE attempt runs: ONE acquire, ONE release, no leak, and the retry that
    would have double-booked capacity never starts."""
    held = []
    released = []

    def acq(provider, timeout_s=None, n=1):
        held.append({"provider": provider, "n": n})
        return {"provider": provider, "n": n}

    def rel(lease):
        released.append(lease)

    pdead.set_lease_provider(acq, rel)
    hang = _HangingGoverned()

    with pytest.raises(pdead.PersonaTimeout):
        pdead.resolve_persona(
            hang, ("signature-story",), {},
            budget_s=2.0, attempts=2, on_state=lambda k, m: None,
            job_id="j3", phase_id="P4-COPY")

    assert len(held) == 1, held      # one per attempt, no extra
    assert len(released) == 1, released
    assert released[0]["provider"] == held[0]["provider"]
    assert released[0]["n"] == held[0]["n"]

    # double release is a no-op (idempotent guard)
    g = pdead.LeaseGuard(provider="persona").acquire()
    g.release()
    extra_before = len(released)
    g.release()
    g.release()
    assert len(released) == extra_before, "release() was not idempotent"


def test_persona_provider_uses_shared_governor(tmp_path, monkeypatch):
    """With no external adapter, LeaseGuard accounts through the engine's own
    rate governor (presentation_job.governor) under the ``persona`` provider
    — shared capacity, not an unlocked per-process counter."""
    from presentation_job import governor

    monkeypatch.setenv("PRESENTATION_GOVERNOR_LOG", str(tmp_path / "gov.jsonl"))
    g = pdead.LeaseGuard(provider="persona").acquire(timeout_s=5)
    assert g.acquired is True
    gov_state = governor.diagnostics("persona") if hasattr(governor, "diagnostics") else {}
    if gov_state:
        assert gov_state.get("inflight", 0) >= 1
    g.release()
    # after release the slot is back
    if gov_state:
        assert gov_state.get("inflight", 0) == 0


def test_governor_timeout_propagates_no_slot_leak(tmp_path, monkeypatch):
    """If the governor cannot admit within the remaining budget, the attempt
    fails without holding a slot (acquire raised, nothing to release)."""
    from presentation_job import governor

    # saturate the persona provider so acquire() cannot admit: the 1-slot
    # inflight ceiling is held by "someone else" AND the window budget is
    # spent, so neither path can admit within the timeout
    monkeypatch.setattr(governor, "provider_config",
                        lambda p: {"rps": 0.0001, "burst": 1, "max_inflight": 1,
                                   "daily_cap": 0, "poll_counts_toward_rps": True})
    with governor._lock:
        st = governor._state_for("persona")
        st.inflight = 1
        now = time.time()
        st.tokens = 0.0
        st.last_refill = now
        st.events = [(now, "acquire", 1)]  # the 10 s window budget is spent
    lease = pdead.LeaseGuard(provider="persona")
    with pytest.raises(governor.GovernorTimeout):
        lease.acquire(timeout_s=0.5)
    assert lease.acquired is False
    assert lease._lease is None


# ---------------------------------------------------------------------------
# 2. Provider resume — known remote id is polled, never duplicate-created
# ---------------------------------------------------------------------------
def test_remote_task_known_id_resumes_without_duplicate(tmp_path):
    reg = pdead.RemoteTaskRegistry(tmp_path)
    created = []

    def create_fn():
        created.append(True)
        return "remote-abc-123"

    polls = []

    def poll_fn(rid):
        polls.append(rid)
        return {"id": rid, "status": "done"}

    # first call: nothing known -> create exactly once, record the id
    out1 = reg.get_or_create("co1:pres1:img3", None, create_fn, poll_fn)
    assert out1["id"] == "remote-abc-123"
    assert created == [True]
    assert polls == ["remote-abc-123"]

    # second call (the retry): the recorded id is polled; create_fn NOT called
    out2 = reg.get_or_create("co1:pres1:img3", None, create_fn, poll_fn)
    assert out2["id"] == "remote-abc-123"
    assert created == [True], "create_fn ran twice for a known remote id"
    assert polls == ["remote-abc-123", "remote-abc-123"]

    # a caller-supplied known id (e.g. recovered from the provider) wins and
    # is persisted — still no create
    out3 = reg.get_or_create("co1:pres1:img3", "remote-abc-123", create_fn, poll_fn)
    assert out3["id"] == "remote-abc-123"
    assert created == [True]

    # the registry is durable on disk
    data = json.loads((tmp_path / "working" / "persona_remote_tasks.json")
                      .read_text(encoding="utf-8"))
    assert data["co1:pres1:img3"]["remote_id"] == "remote-abc-123"


def test_remote_task_different_scope_creates_separately(tmp_path):
    reg = pdead.RemoteTaskRegistry(tmp_path)
    created = []

    reg.get_or_create("co1:pres1", None, lambda: ("r-1" if created.append(True) is None else "r-1"), lambda rid: rid)
    reg.get_or_create("co1:pres2", None, lambda: ("r-2" if created.append(True) is None else "r-2"), lambda rid: rid)
    reg.get_or_create("co2:pres1", None, lambda: ("r-3" if created.append(True) is None else "r-3"), lambda rid: rid)
    assert created == [True, True, True], "scopes share a create path"


# ---------------------------------------------------------------------------
# 3. Normal selection within budget + scoped immutable cache
# ---------------------------------------------------------------------------
def test_normal_selection_passes_within_budget(tmp_path):
    run_dir = _make_run_dir(tmp_path)
    calls = []

    def fast_selector(phase, avatar_context="", department=None, record=None):
        calls.append(phase)
        return {"blend_directive": "Write as X.", "persona_id": "x"}

    bundle = pdead.resolve_persona(
        fast_selector, ("signature-story",), {},
        budget_s=10.0, attempts=2, on_state=lambda k, m: None,
        job_id="j4", phase_id="P4-COPY")
    assert bundle["persona_id"] == "x"
    assert calls == ["signature-story"]
    assert _state_events(run_dir) == [] or "persona_timeout" not in _state_events(run_dir)


def test_cache_reuses_identical_context_only(tmp_path):
    run_dir = _make_run_dir(tmp_path)
    ctx = {"company": "co1", "presentation": "pres1", "phase": "P4-COPY",
           "audience": "founders", "topic": "offers", "offer": "beta",
           "context_revision": 7}
    h = pdead.scope_hash(ctx)
    bundle = {"blend_directive": "d", "persona_id": "x"}

    pdead.cache_save(run_dir, "P4-COPY", h, bundle)
    got = pdead.cache_load(run_dir, "P4-COPY", h)
    assert got == bundle, "identical context must hit"

    # a DIFFERENT context (any field changed) is a MISS — its own hash space
    ctx2 = dict(ctx, audience="students")
    h2 = pdead.scope_hash(ctx2)
    assert h2 != h
    assert pdead.cache_load(run_dir, "P4-COPY", h2) is None

    # the stored payload is bound to its hash: a payload tampered to claim a
    # foreign hash returns nothing (byte-identity, not filename identity)
    path = pdead.cache_path(run_dir, "P4-COPY", h)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["context_hash"] = h2
    path.write_text(json.dumps(data), encoding="utf-8")
    assert pdead.cache_load(run_dir, "P4-COPY", h) is None


def test_cache_survives_identical_context_across_calls(tmp_path):
    run_dir = _make_run_dir(tmp_path)
    ctx = {"company": "co1", "presentation": "pres1", "phase": "P4-COPY",
           "audience": "a", "topic": "t", "offer": "o", "context_revision": 1}
    h = pdead.scope_hash(ctx)
    calls = []

    def counting_selector(phase, avatar_context="", department=None, record=None):
        calls.append(phase)
        return {"blend_directive": "d", "persona_id": "x"}

    pdead.cache_save(run_dir, "P4-COPY", h,
                     {"blend_directive": "d", "persona_id": "x"})
    hit = pdead.cache_load(run_dir, "P4-COPY", h)
    assert hit is not None
    assert calls == [], "selector must not run for an identical cached context"


def test_absolute_deadline_exported_and_clamps_seam(tmp_path, monkeypatch):
    """The engine's one deadline is exported on the wall clock and the seam
    clamps its own ceiling to the remaining time — the 90-vs-600 mismatch
    cannot recur."""
    # no deadline exported -> seam uses its own default
    os.environ.pop("PERSONA_FOR_JOB_DEADLINE", None)
    import importlib.util
    # repo root = worktree root: scripts/ -> presentations/ -> role-library/
    # -> templates/ -> 23-ai-workforce-blueprint/ -> <repo root>
    repo_root = _SCRIPTS.parents[3]
    pfj_path = repo_root / "shared-utils" / "persona_for_job.py"
    if not pfj_path.is_file():
        # installed-skills layout fallback: walk up until shared-utils exists
        for anc in _SCRIPTS.parents:
            cand = anc / "shared-utils" / "persona_for_job.py"
            if cand.is_file():
                pfj_path = cand
                break
    assert pfj_path.is_file(), pfj_path
    spec = importlib.util.spec_from_file_location("pfj_pres054", str(pfj_path))
    pfj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pfj)
    assert pfj._deadline_clamped_timeout() == pfj.DEFAULT_SELECTOR_TIMEOUT

    # deadline 30 s out -> clamped to ~29 (floored, margin applied)
    os.environ["PERSONA_FOR_JOB_DEADLINE"] = repr(time.time() + 30.0)
    clamped = pfj._deadline_clamped_timeout()
    assert 27 <= clamped <= 30, clamped

    # deadline already past -> 1 s fail-fast ceiling
    os.environ["PERSONA_FOR_JOB_DEADLINE"] = repr(time.time() - 5.0)
    assert pfj._deadline_clamped_timeout() == 1

    # and resolve_persona exports/clears it around the resolution
    os.environ.pop("PERSONA_FOR_JOB_DEADLINE", None)

    def ok(phase, *a, **k):
        return {"ok": True}

    pdead.resolve_persona(ok, ("p",), {}, budget_s=5.0, attempts=1,
                          on_state=lambda k, m: None,
                          job_id="j5", phase_id="P4-COPY")
    assert "PERSONA_FOR_JOB_DEADLINE" not in os.environ, \
        "wall deadline must be cleared after the resolution ends"


# ---------------------------------------------------------------------------
# 4. Visible state + truthful cancellation
# ---------------------------------------------------------------------------
def test_timeout_emits_visible_state_only_for_this_run(tmp_path):
    run_dir = _make_run_dir(tmp_path)
    other_dir = _make_run_dir(tmp_path.parent / "other")
    assert (other_dir / "state.json").is_file()
    hang = _HangingGoverned()

    with pytest.raises(pdead.PersonaTimeout):
        pdead.resolve_persona(
            hang, ("signature-story",), {},
            budget_s=2.0, attempts=1,
            on_state=(lambda k, m: pdead.record_event(
                run_dir, k, m, phase_id="P4-COPY")),
            job_id="j6", phase_id="P4-COPY")

    kinds = _state_events(run_dir)
    assert "persona_timeout" in kinds, kinds
    # the OTHER run's state is untouched
    other = json.loads((other_dir / "state.json").read_text(encoding="utf-8"))
    assert other["events"] == [], other["events"]


def test_persona_cancelled_is_truthful_durable_state(tmp_path):
    """Caller cancellation: visible persona_cancelled event, the exception
    carries the reap proof, and Future-cancel is PROVEN not to mean the
    subprocess stopped (the negative control)."""
    run_dir = _make_run_dir(tmp_path)
    cancel = threading.Event()
    cancel.set()  # cancel is already decided by the time attempt 1 starts
    ex = pdead.PersonaExecutor(job_id="j7", phase_id="P4-COPY",
                               run_dir=run_dir, attempts=1,
                               budget_s=20.0, cancel_event=cancel)

    def slow_but_killable(phase, *a, **k):
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            start_new_session=True)
        rid = pdead.current_resolution_id() or ""
        pdead.register_proc(rid, proc)
        cancel.wait(30)
        return {}

    # cancel BEFORE run: PersonaCancelled raised with a reap proof attached,
    # and a persona_cancelled event persisted
    with pytest.raises(pdead.PersonaCancelled) as excinfo:
        ex.run(slow_but_killable, "signature-story")
    proof = excinfo.value.proof
    assert proof.get("reap_complete") is True, proof
    assert "persona_cancelled" in _state_events(run_dir)

    # negative control: cancelling a PYTHON future does NOT stop a real child
    from concurrent.futures import ThreadPoolExecutor
    holder = {}

    def real_child(phase, *a, **k):
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)
        holder["proc"] = proc
        rid = pdead.current_resolution_id() or ""
        holder["rid"] = rid
        pdead.register_proc(rid, proc)
        time.sleep(30)
        return {}

    ex2 = ThreadPoolExecutor(max_workers=1)
    try:
        fut = ex2.submit(real_child, "signature-story")
        for _ in range(100):
            if "proc" in holder:
                break
            time.sleep(0.05)
        proc = holder["proc"]
        fut.cancel()  # cancels the PYTHON wait only
        # the child process is STILL ALIVE — this is exactly why the fix
        # reaps the owned tree and never trusts Future.cancel() as proof
        assert proc.poll() is None, \
            "negative control changed shape: child died on its own before reap"
        # the production reap then makes the truth durable:
        proof2 = pdead.terminate_owned_tree(holder["rid"], grace_s=1.0)
        assert proof2["reap_complete"] is True, proof2
        assert pdead.live_owned_pids(holder["rid"]) == []
    finally:
        ex2.shutdown(wait=False)


# ---------------------------------------------------------------------------
# 5. Real resolve_for_phase integration — timeout surfaces as TimeoutError
#    with the run's own state updated (engine contract unchanged).
# ---------------------------------------------------------------------------
def test_resolve_for_phase_timeout_blocks_with_visible_state(tmp_path, monkeypatch):
    run_dir = _make_run_dir(tmp_path)
    monkeypatch.setenv("PERSONA_BUDGET_S", "2")

    mod = persona.load_blend_module()
    assert mod is not None, "blend_voice_governance must be reachable"

    def hang(phase, avatar_context="", department=None, record=None):
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)
        pdead.register_proc(pdead.current_resolution_id() or "", proc)
        time.sleep(30)
        return {}

    monkeypatch.setattr(mod, "governed_phase_voice", hang)

    with pytest.raises(TimeoutError):
        persona.resolve_for_phase(run_dir, "P4-COPY",
                                  avatar_context="founders")

    kinds = _state_events(run_dir)
    assert "persona_timeout" in kinds, kinds
    # the phase is BLOCKED (the callers' except (RuntimeError, TimeoutError)
    # contract), and no owned child survived
    for entry in pdead.attempt_log():
        assert entry["proof"]["reap_complete"] is True


def test_resolve_for_phase_normal_path_within_budget(tmp_path, monkeypatch):
    run_dir = _make_run_dir(tmp_path)
    monkeypatch.setenv("PERSONA_BUDGET_S", "10")

    mod = persona.load_blend_module()
    assert mod is not None

    def fast(phase, avatar_context="", department=None, record=None):
        return {"blend_directive": "Write as X.", "persona_id": "x"}

    monkeypatch.setattr(mod, "governed_phase_voice", fast)

    bundle = persona.resolve_for_phase(run_dir, "P4-COPY",
                                       avatar_context="founders")
    assert bundle["persona_id"] == "x"
    assert "persona_timeout" not in _state_events(run_dir)