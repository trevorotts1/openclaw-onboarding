"""PD-TEST-183 -- a retry must be told WHAT failed, not just THAT something did.

THE DEFECT, and it is now MEASURED rather than argued. On retry the worker
composed the next attempt's prompt with a content-free instruction:

    "attempt {n} failed verification; re-author slide {ordinal}"

It named neither the failing check nor the requirement. The engine HAD the real
findings -- the verify path records them as
`attempt {n}: verify failed ({'; '.join(reasons)})` -- but they went only to the
attempt log, the settle outcome and the final report.

On `pres-operator-1d269693` the engine was then given a funded re-dispatch (the
PD-TEST-182 repair receipt was issued and consumed, `should_dispatch` returned
True for the first time, `slide-01` was re-authored at 17:47). The re-authored
prompt **failed the same checks** -- `AF-FACE-PROMPT-MISSING`,
`AF-LIGHT-PROMPT-MISSING`, `AF-HAIR-INAUTHENTIC` -- and **added**
`AF-WORLD-SCALE`, spending the entire allowance plus the retry pool for the same
non-result. A model told only that it failed has no signal about WHICH token is
missing, so it omits the same ones.

Same masking family as PD-TEST-162 and PD-TEST-177: the durable record knows the
real reason and the actor that could act on it is not told it.

HARNESS NOTE (learned by tracing, recorded so it is not re-derived): composition
happens in `_default_provider_call`, NOT in `_execute_slide`. Replacing
`ppw.provider_call` therefore SKIPS the code under test and the capture comes
back empty. This file leaves `provider_call` as the default and stubs one level
LOWER, at `dispatcher.dispatch_complete`.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import dispatcher as dj  # noqa: E402
from presentation_job import parallel_prompt_worker as ppw  # noqa: E402

CODE = "AF-FACE-PROMPT-MISSING"


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


def _drive(tmp_path, monkeypatch, *, fail_first: bool):
    seen = []

    def _compose(**kw):
        seen.append(list(kw.get("prior_reasons") or []))
        return "SYS", "USER"

    monkeypatch.setattr(dj, "compose_prompt", _compose)
    monkeypatch.setattr(dj, "dispatch_complete",
                        lambda *a, **k: ("PROMPT BODY", {}, {}))
    monkeypatch.setattr(ppw, "provider_call", None)
    seq = []

    def _verify(slide, text, run_dir, constraints):
        seq.append(1)
        if fail_first and len(seq) == 1:
            return False, [CODE]
        return True, []

    monkeypatch.setattr(ppw, "_verify_prompt", _verify)
    ppw._execute_slide(_task(tmp_path))
    return seen


def test_the_named_check_reaches_the_next_attempts_prompt(tmp_path, monkeypatch):
    seen = _drive(tmp_path, monkeypatch, fail_first=True)
    assert len(seen) >= 2, (
        "expected at least two composed attempts, saw "
        f"{len(seen)} -- if 0, the harness replaced provider_call and skipped "
        "_default_provider_call, which is where composition happens")
    second = " ".join(seen[1])
    assert CODE in second, (
        "the second attempt was NOT told which check failed -- it received only "
        f"a content-free instruction: {seen[1]!r}. Measured on the live run, that "
        "reproduces the same findings and burns the whole allowance.")
    assert any("failed verification" in r for r in seen[1]), (
        f"the original generic instruction was lost: {seen[1]!r}")


def test_a_first_attempt_is_told_nothing_about_failures(tmp_path, monkeypatch):
    seen = _drive(tmp_path, monkeypatch, fail_first=False)
    assert seen, "compose_prompt was never called"
    assert seen[0] == [], (
        f"the first attempt carried a prior-failure instruction: {seen[0]!r}")
