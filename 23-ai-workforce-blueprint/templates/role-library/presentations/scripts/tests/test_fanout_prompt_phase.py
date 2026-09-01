"""Tests for P4-PROMPT wired to the fan-out pool (Ticket 4, PARALLEL-PIPELINE-SPEC).

Stubs `deepseek_complete`, `compose_prompt`, and `_verify_single_prompt` so
the fan-out WIRING (ordering, partial-failure semantics, resume/re-dispatch
reuse) is under test in isolation from the real DeepSeek transport and the
real 9,000-18,000-char prompt-quality gate (both covered by their own
sibling test files elsewhere in this suite).

Required minimum per the spec's Ticket 4 test plan:
  (a) workers=1 produces the identical file set as before the change.
  (b) workers=N (N>1) produces the identical file set.
  (c) 3 stubbed failures leave N-3 verified files and a phase-level result
      naming exactly those 3 failed ordinals.
  (d) a re-run after those 3 failures re-calls the stub only for the 3
      previously-failed ordinals -- the already-good ones are never re-spent
      (dispatcher.py's own already-verified-and-on-disk short-circuit).

Flat file inside tests/, manages its own import path -- matching every
sibling in this directory.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Dict, List, Tuple

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import dispatcher  # noqa: E402
from presentation_job.manifest import Phase  # noqa: E402


def _phase(workers: int) -> Phase:
    return Phase(
        id="P4-PROMPT", order=4.7, owning_role="prompt-author-presentations",
        produces_artifact=["working/prompts/slide-*.txt"], executor_kind="agent",
        executor_cmd=None, verifier="phase_verifiers.verify", workers=workers,
    )


def _setup_run_dir(tmp_path: Path, n: int, name: str = "run") -> Path:
    run_dir = tmp_path / name
    (run_dir / "working" / "copy").mkdir(parents=True)
    (run_dir / "working" / "copy" / "slides.json").write_text(
        "[" + ",".join(f'{{"n":{i}}}' for i in range(1, n + 1)) + "]", encoding="utf-8")
    return run_dir


def _stub_compose_prompt(monkeypatch):
    monkeypatch.setattr(dispatcher, "compose_prompt",
                        lambda **kw: ("SYSTEM-PROMPT", "USER-PROMPT-BODY"))


def _stub_verify_by_content_marker(monkeypatch):
    """A slide is "verified" iff its file exists and its content ends with
    the literal marker "-OK". Decouples this test from the real
    9,000-18,000-char / build_deck.check_prompt_qc_deterministic gate, which
    is covered by its own sibling tests elsewhere in this suite."""
    def _verify(run_dir: Path, ordinal: int) -> Tuple[bool, List[str]]:
        target = run_dir / "working" / "prompts" / f"slide-{ordinal:02d}.txt"
        if not target.is_file():
            return False, [f"slide-{ordinal:02d}.txt missing"]
        content = target.read_text(encoding="utf-8")
        if content.endswith("-OK"):
            return True, []
        return False, [f"slide-{ordinal:02d}.txt failed the stub gate"]
    monkeypatch.setattr(dispatcher, "_verify_single_prompt", _verify)
    monkeypatch.setattr(dispatcher, "_verify", lambda phase_id, run_dir: (
        all(_verify(run_dir, i)[0] for i in
            range(1, dispatcher._prompt_slide_count(run_dir) + 1)),
        [],
    ))


def _extract_ordinal(user_prompt: str) -> int:
    import re
    m = re.search(r"SLIDE (\d+) OF", user_prompt)
    assert m, f"worker did not embed the slide-ordinal marker: {user_prompt!r}"
    return int(m.group(1))


def test_workers_1_and_workers_n_produce_identical_file_sets(tmp_path, monkeypatch):
    n = 10
    _stub_compose_prompt(monkeypatch)
    _stub_verify_by_content_marker(monkeypatch)

    calls_serial = []

    def stub_complete_serial(system_prompt, user_prompt, **kwargs):
        ordinal = _extract_ordinal(user_prompt)
        calls_serial.append(ordinal)
        return f"slide-{ordinal}-content-OK", {"prompt_tokens": 10, "completion_tokens": 10}

    monkeypatch.setattr(dispatcher, "deepseek_complete", stub_complete_serial)
    run_dir_serial = _setup_run_dir(tmp_path, n)
    result_serial = dispatcher._dispatch_prompt_phase(
        run_dir_serial, {"owning_role": "prompt-author-presentations"},
        dept_root=tmp_path, phase_obj=_phase(workers=1), worker_id="w1")
    assert result_serial.status == "ok"
    serial_files = sorted(p.name for p in (run_dir_serial / "working" / "prompts").glob("*.txt"))

    def stub_complete_parallel(system_prompt, user_prompt, **kwargs):
        ordinal = _extract_ordinal(user_prompt)
        return f"slide-{ordinal}-content-OK", {"prompt_tokens": 10, "completion_tokens": 10}

    monkeypatch.setattr(dispatcher, "deepseek_complete", stub_complete_parallel)
    run_dir_parallel = _setup_run_dir(tmp_path, n, name="run_parallel")
    result_parallel = dispatcher._dispatch_prompt_phase(
        run_dir_parallel, {"owning_role": "prompt-author-presentations"},
        dept_root=tmp_path, phase_obj=_phase(workers=8), worker_id="w1")
    assert result_parallel.status == "ok"
    parallel_files = sorted(p.name for p in (run_dir_parallel / "working" / "prompts").glob("*.txt"))

    assert serial_files == parallel_files == [f"slide-{i:02d}.txt" for i in range(1, n + 1)]
    for i in range(1, n + 1):
        content_s = (run_dir_serial / "working" / "prompts" / f"slide-{i:02d}.txt").read_text()
        content_p = (run_dir_parallel / "working" / "prompts" / f"slide-{i:02d}.txt").read_text()
        assert content_s == content_p == f"slide-{i}-content-OK"


def test_three_failures_leave_rest_verified_and_name_the_failures(tmp_path, monkeypatch):
    n = 25
    failing = {5, 13, 21}
    _stub_compose_prompt(monkeypatch)
    _stub_verify_by_content_marker(monkeypatch)
    call_count = {"n": 0}

    def stub_complete(system_prompt, user_prompt, **kwargs):
        ordinal = _extract_ordinal(user_prompt)
        call_count["n"] += 1
        if ordinal in failing:
            return f"slide-{ordinal}-content-BAD", {"prompt_tokens": 10, "completion_tokens": 10}
        return f"slide-{ordinal}-content-OK", {"prompt_tokens": 10, "completion_tokens": 10}

    monkeypatch.setattr(dispatcher, "deepseek_complete", stub_complete)
    run_dir = _setup_run_dir(tmp_path, n)
    result = dispatcher._dispatch_prompt_phase(
        run_dir, {"owning_role": "prompt-author-presentations"},
        dept_root=tmp_path, phase_obj=_phase(workers=25), worker_id="w1")

    assert result.status == "exhausted"
    for ordinal in failing:
        assert any(f"slide-{ordinal:02d}" in r for r in result.reasons)

    prompts_dir = run_dir / "working" / "prompts"
    all_files = sorted(p.name for p in prompts_dir.glob("*.txt"))
    assert all_files == [f"slide-{i:02d}.txt" for i in range(1, n + 1)], (
        "every ordinal's target file exists on disk (even the failing ones -- "
        "the worker writes-then-verifies and never deletes a failing attempt), "
        "but only the non-failing ones pass the stub gate")
    verified = [i for i in range(1, n + 1)
                if dispatcher._verify_single_prompt(run_dir, i)[0]]
    assert len(verified) == n - len(failing)
    assert set(range(1, n + 1)) - set(verified) == failing
    # DISPATCH_RETRY_CAP attempts (3) for each of the 3 failing slides, 1 each
    # for the 22 good ones.
    assert call_count["n"] == (n - len(failing)) + len(failing) * dispatcher.DISPATCH_RETRY_CAP


def test_resume_after_failure_only_recalls_stub_for_failed_ordinals(tmp_path, monkeypatch):
    n = 25
    failing = {5, 13, 21}
    _stub_compose_prompt(monkeypatch)
    _stub_verify_by_content_marker(monkeypatch)

    def stub_complete_first_run(system_prompt, user_prompt, **kwargs):
        ordinal = _extract_ordinal(user_prompt)
        if ordinal in failing:
            return f"slide-{ordinal}-content-BAD", {"prompt_tokens": 10, "completion_tokens": 10}
        return f"slide-{ordinal}-content-OK", {"prompt_tokens": 10, "completion_tokens": 10}

    monkeypatch.setattr(dispatcher, "deepseek_complete", stub_complete_first_run)
    run_dir = _setup_run_dir(tmp_path, n)
    first = dispatcher._dispatch_prompt_phase(
        run_dir, {"owning_role": "prompt-author-presentations"},
        dept_root=tmp_path, phase_obj=_phase(workers=25), worker_id="w1")
    assert first.status == "exhausted"

    # Resume: the transient issue is now resolved -- every ordinal (including
    # the 3 that failed) succeeds on its very first call this time.
    resume_calls = []

    def stub_complete_resume(system_prompt, user_prompt, **kwargs):
        ordinal = _extract_ordinal(user_prompt)
        resume_calls.append(ordinal)
        return f"slide-{ordinal}-content-OK", {"prompt_tokens": 10, "completion_tokens": 10}

    monkeypatch.setattr(dispatcher, "deepseek_complete", stub_complete_resume)
    second = dispatcher._dispatch_prompt_phase(
        run_dir, {"owning_role": "prompt-author-presentations"},
        dept_root=tmp_path, phase_obj=_phase(workers=25), worker_id="w1")

    assert second.status == "ok"
    # Only the 3 previously-failed ordinals were re-dispatched -- the 22
    # already-good slides were skipped instantly by the on-disk check.
    assert sorted(resume_calls) == sorted(failing)
    assert len(resume_calls) == len(failing)

    prompts_dir = run_dir / "working" / "prompts"
    all_files = sorted(p.name for p in prompts_dir.glob("*.txt"))
    assert all_files == [f"slide-{i:02d}.txt" for i in range(1, n + 1)]


def test_never_exceeds_manifest_workers_concurrent_calls(tmp_path, monkeypatch):
    _stub_compose_prompt(monkeypatch)
    _stub_verify_by_content_marker(monkeypatch)
    active = {"n": 0}
    max_seen = {"n": 0}
    lock = threading.Lock()

    def stub_complete(system_prompt, user_prompt, **kwargs):
        ordinal = _extract_ordinal(user_prompt)
        with lock:
            active["n"] += 1
            max_seen["n"] = max(max_seen["n"], active["n"])
        import time
        time.sleep(0.01)
        with lock:
            active["n"] -= 1
        return f"slide-{ordinal}-content-OK", {"prompt_tokens": 10, "completion_tokens": 10}

    monkeypatch.setattr(dispatcher, "deepseek_complete", stub_complete)
    run_dir = _setup_run_dir(tmp_path, 20)
    result = dispatcher._dispatch_prompt_phase(
        run_dir, {"owning_role": "prompt-author-presentations"},
        dept_root=tmp_path, phase_obj=_phase(workers=4), worker_id="w1")

    assert result.status == "ok"
    assert max_seen["n"] <= 4
