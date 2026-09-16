"""PD-TEST-187 -- a DEAD per-attempt settle must be audible, not silent.

Found by the independent review of PR #1169, which introduced the per-attempt
settle. The block was wrapped in a BARE `except Exception: pass`, and the review
measured the consequence: deleting the whole block, or mutating it four ways,

  * a `str` instead of the outcome list  -> TypeError on every retry,
  * a typo'd phase id                    -> the settle targets no ledger,
  * `"ok"` instead of `"failed"`         -> the retry is refused as "already
                                            succeeded ... refusing to regenerate",

all leave the repo's own suites GREEN (46/46) while the end-to-end wave silently
degrades to **one** provider call -- i.e. back to the PD-TEST-177 defect, with
nothing anywhere saying so. The dispatcher's own settle failure records a
consequence row; the worker's recorded nothing.

These tests pin the property the review found missing: the settle stays
FAIL-SOFT (bookkeeping must never break a unit) but a failure is now REPORTED.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import dispatcher as dj  # noqa: E402
from presentation_job import parallel_prompt_worker as ppw  # noqa: E402


def _task(tmp_path: Path) -> dict:
    run_dir = tmp_path / "run"
    (run_dir / "working" / "checkpoints").mkdir(parents=True, exist_ok=True)
    return {
        "slide": {"ordinal": 1, "slide_id": 1, "copy": ["Headline", "Subhead"]},
        "routing": {"provider": "stub", "model": "stub"},
        "run_dir": str(run_dir),
        "prompt_constraints": {},
        "n_slides": 8,
        "owning_role": "prompt-author-presentations",
        "attempts_log": str(run_dir / "working" / "checkpoints" / "res.jsonl"),
    }


def _drive(monkeypatch, tmp_path, *, settle_raises: bool):
    monkeypatch.setattr(dj, "compose_prompt", lambda **kw: ("SYS", "USER"))
    monkeypatch.setattr(dj, "dispatch_complete",
                        lambda *a, **k: ("PROMPT BODY", {}, {}))
    monkeypatch.setattr(ppw, "provider_call", None)
    calls = {"n": 0, "settle": 0}

    def _settle(*a, **k):
        calls["settle"] += 1
        if settle_raises:
            raise TypeError("simulated dead settle (wrong outcome shape)")
        return None

    monkeypatch.setattr(dj, "_settle_unit_paid_attempts", _settle)
    seq = []

    def _verify(slide, text, run_dir, constraints):
        seq.append(1)
        # Fail the first attempt so a SECOND one runs -- the settle only fires
        # when attempt > 0, i.e. exactly on the retry path.
        return (False, ["AF-FACE-PROMPT-MISSING"]) if len(seq) == 1 else (True, [])

    monkeypatch.setattr(ppw, "_verify_prompt", _verify)
    result = ppw._execute_slide(_task(tmp_path))
    return calls, result


def test_a_settle_failure_is_reported_and_does_not_break_the_unit(
        tmp_path, monkeypatch, capsys):
    calls, result = _drive(monkeypatch, tmp_path, settle_raises=True)
    err = capsys.readouterr().err
    assert calls["settle"] >= 1, (
        "the per-attempt settle was never attempted -- this test would pass "
        "vacuously and the retry path is not being exercised")
    assert "settle failed" in err, (
        "a FAILED per-attempt settle produced no diagnostic. Before this change "
        "it was a bare `except Exception: pass`, which the review measured as "
        "indistinguishable from a working settle: every suite stayed green while "
        "the wave silently degraded to one provider call. stderr was: " + repr(err))
    # FAIL-SOFT means the failure does not ABORT the unit's attempt sequence --
    # it still ran a second attempt instead of dying on the bookkeeping. (The
    # unit's own status is the stub harness's business, not this property's.)
    assert int(result.get("attempts") or 0) >= 2, (
        "a settle failure ABORTED the retry -- bookkeeping must never break a "
        f"unit. Got attempts={result.get('attempts')!r}, "
        f"error={result.get('error_message')!r}")


def test_a_healthy_settle_stays_quiet(tmp_path, monkeypatch, capsys):
    calls, result = _drive(monkeypatch, tmp_path, settle_raises=False)
    err = capsys.readouterr().err
    assert calls["settle"] >= 1, "the settle was never attempted"
    assert "settle failed" not in err, (
        f"a WORKING settle emitted a failure warning: {err!r}")
    assert int(result.get("attempts") or 0) >= 2, (
        f"the retry did not run: attempts={result.get('attempts')!r}")
