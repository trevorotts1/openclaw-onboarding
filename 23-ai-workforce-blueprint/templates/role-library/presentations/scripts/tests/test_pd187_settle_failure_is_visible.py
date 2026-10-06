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

THE FIRST FIX WAS TOO NARROW, and adversarial review of it proved that: it
caught only a settle that RAISES, while TWO OF THE FOUR MUTANTS ABOVE NEVER
RAISE. `_settle_unit_paid_attempts` returns quietly when the phase id reads an
empty ledger (`dispatcher.py`, `if not led: return`), and a settle that records
`"ok"` for a unit we reported `"failed"` returns quietly too. Both left the
reservation in flight -- exactly the state that makes the unit's own retry
resolve as `budget_deferred` -- and both were still completely invisible, with
this file passing 2/2 under that mutant.

So these tests pin the wider property: the settle stays FAIL-SOFT (bookkeeping
must never break a unit) but a settle that FAILS, in EITHER of its two death
modes -- raising, or returning without settling -- is now REPORTED.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import dispatcher as dj  # noqa: E402
from presentation_job import parallel_prompt_worker as ppw  # noqa: E402

# The stable substring every dead-settle report carries, whichever way it died.
DEAD = "did not take effect"


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


def _record_outcome(run_dir: Path, status: str) -> None:
    """Write the durable outcome row a WORKING settle would have written.

    This is what makes the healthy case a real control rather than a stub: the
    post-condition check reads the ledger back, so a stub that settles nothing
    is indistinguishable from a settle that settled nothing -- which is the
    whole point of the second half of this file.
    """
    led = dj._read_ledger(run_dir, ppw.PHASE_ID)
    if not isinstance(led, dict):
        led = {}
    led[dj.LEDGER_UNIT_OUTCOMES] = {
        "1": {"status": status, "unit_status": "failed",
              "worker": "p4prompt-unit"},
    }
    dj._write_ledger(run_dir, ppw.PHASE_ID, led)


def _drive(monkeypatch, tmp_path, *, mode: str):
    """mode: 'raises' | 'silent' | 'wrong_status' | 'lands'."""
    monkeypatch.setattr(dj, "compose_prompt", lambda **kw: ("SYS", "USER"))
    monkeypatch.setattr(dj, "dispatch_complete",
                        lambda *a, **k: ("PROMPT BODY", {}, {}))
    monkeypatch.setattr(ppw, "provider_call", None)
    calls = {"n": 0, "settle": 0}
    run_dir = tmp_path / "run"

    def _settle(*a, **k):
        calls["settle"] += 1
        if mode == "raises":
            raise TypeError("simulated dead settle (wrong outcome shape)")
        if mode == "silent":
            # The typo'd-phase-id mutant: returns NORMALLY, settles NOTHING.
            # `dispatcher.py` `if not led: return`. Never raises.
            return None
        if mode == "wrong_status":
            # The "ok"-instead-of-"failed" mutant: returns NORMALLY and writes a
            # durable row claiming the unit succeeded. Never raises.
            _record_outcome(run_dir, "ok")
            return None
        _record_outcome(run_dir, "failed")
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


def _sidecar_rows(tmp_path: Path):
    path = dj._sidecar_log_path(tmp_path / "run", ppw.PHASE_ID)
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def _assert_fail_soft(result):
    """FAIL-SOFT means a dead settle never ABORTS the unit's attempt sequence."""
    assert int(result.get("attempts") or 0) >= 2, (
        "a settle failure ABORTED the retry -- bookkeeping must never break a "
        f"unit. Got attempts={result.get('attempts')!r}, "
        f"error={result.get('error_message')!r}")


def test_a_raising_settle_is_reported_and_does_not_break_the_unit(
        tmp_path, monkeypatch, capsys):
    calls, result = _drive(monkeypatch, tmp_path, mode="raises")
    err = capsys.readouterr().err
    assert calls["settle"] >= 1, (
        "the per-attempt settle was never attempted -- this test would pass "
        "vacuously and the retry path is not being exercised")
    assert DEAD in err, (
        "a RAISING per-attempt settle produced no diagnostic. Before this change "
        "it was a bare `except Exception: pass`. stderr was: " + repr(err))
    _assert_fail_soft(result)


def test_a_silent_settle_is_reported(tmp_path, monkeypatch, capsys):
    """THE MUTANT THE FIRST FIX MISSED (adversarial review of PR #1174).

    A settle that returns normally but settles nothing -- a typo'd phase id
    reading an empty ledger -- raises no exception, so an `except`-only fix
    cannot see it. It is now caught by asserting the POST-CONDITION.
    """
    calls, result = _drive(monkeypatch, tmp_path, mode="silent")
    err = capsys.readouterr().err
    assert calls["settle"] >= 1, "the settle was never attempted"
    assert DEAD in err, (
        "a settle that returned NORMALLY having settled NOTHING produced no "
        "diagnostic. This is the exact mutant that left the reservation in "
        "flight (so the unit's own retry resolves as budget_deferred) while "
        "every suite stayed green. stderr was: " + repr(err))
    _assert_fail_soft(result)


def test_a_settle_that_records_the_wrong_outcome_is_reported(
        tmp_path, monkeypatch, capsys):
    """The 'ok'-instead-of-'failed' mutant: writes a durable row, wrongly.

    It raises nothing and writes something, so only a post-condition check that
    compares the RECORDED status against the one we asked for can see it.
    """
    calls, result = _drive(monkeypatch, tmp_path, mode="wrong_status")
    err = capsys.readouterr().err
    assert calls["settle"] >= 1, "the settle was never attempted"
    assert DEAD in err, (
        "a settle that recorded status 'ok' for a unit we reported 'failed' "
        "produced no diagnostic. stderr was: " + repr(err))
    assert "'ok'" in err or '"ok"' in err, (
        "the diagnostic does not name the wrong status it found, so an operator "
        f"cannot tell what happened. stderr was: {err!r}")
    _assert_fail_soft(result)


def test_a_dead_settle_also_lands_a_machine_readable_sidecar_row(
        tmp_path, monkeypatch, capsys):
    """stderr is read live; the sidecar is read after the fact.

    The module's own `_announce_unleased_route` uses both, "because the log is
    only read after the fact and stderr is only read live", and the dispatcher's
    serial settle records a consequence in the sidecar for the same reason.
    """
    _drive(monkeypatch, tmp_path, mode="silent")
    capsys.readouterr()
    rows = [r for r in _sidecar_rows(tmp_path)
            if r.get("status") == "fanout_paid_settle_dead"]
    assert rows, "a dead settle recorded no machine-readable sidecar row"
    row = rows[0]
    assert row.get("unit") == "1" and isinstance(row.get("attempt"), int), row
    assert row.get("consequence"), (
        "the sidecar row states no CONSEQUENCE, so a reader cannot tell why it "
        f"matters: {row!r}")
    assert len(str(row.get("reason") or "")) <= 400, (
        "the diagnostic text is unbounded -- every other exception this module "
        f"surfaces goes through _sanitize(), which bounds it: {row!r}")


def test_a_healthy_settle_stays_quiet(tmp_path, monkeypatch, capsys):
    calls, result = _drive(monkeypatch, tmp_path, mode="lands")
    err = capsys.readouterr().err
    assert calls["settle"] >= 1, "the settle was never attempted"
    assert DEAD not in err, (
        f"a WORKING settle emitted a dead-settle warning: {err!r}")
    assert not [r for r in _sidecar_rows(tmp_path)
                if r.get("status") == "fanout_paid_settle_dead"], (
        "a WORKING settle recorded a dead-settle sidecar row")
    _assert_fail_soft(result)
