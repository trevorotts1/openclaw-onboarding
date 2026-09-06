"""EVERY invocable intake driver must record the client's RUN-MODE declaration.

WHAT WENT WRONG. Two intake implementations existed against the SAME question
bank (intake/deck-intake-questions.json): the role-library driver, which mirrors
the order-9 ``resource_plan`` turn's ``run_mode`` subfield onto the ``RUN_MODE``
ledger key via ``_record_run_mode()``, and the two skill-23 copies
(``23-ai-workforce-blueprint/scripts/deck-intake-driver.py`` and
``deck-intake-turngate.py``), which did not. Both banks, one behaviour missing.

A client answering that turn with "mode: ultra" through either copy got
``{"status": "accepted", ... "validated": true}`` back -- a success -- while
RUN_MODE was silently dropped. ``presentation-intake-poll.sh::read_run_mode()``
reads exactly that ledger key to set the run-mode door (``launcher --mode`` on
the resume path, ``PRESENTATION_MODE`` on the new-intake path), so it found
nothing and the run executed STANDARD. Ultra was declared and never delivered,
and nothing anywhere failed.

WHY THIS TEST IS BEHAVIOURAL, NOT A GREP. A string check for "_record_run_mode"
or "RUN_MODE" is satisfied by a comment mentioning it -- which is exactly how a
gate whose clause was a literal-string grep got broken by accident in this repo.
So each driver is EXECUTED against a real run directory and the ledger it
actually wrote is read back.

WHY IT DISCOVERS RATHER THAN LISTS. The defect was a NEW copy appearing beside
an old one. Hard-coding today's three paths would let tomorrow's fourth copy
reintroduce it untested, so every ``deck-intake-*.py`` in either scripts
directory that exposes the answer-recording CLI is collected and must pass.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_PRES_SCRIPTS = _TESTS_DIR.parent                    # .../presentations/scripts
_SKILL23 = _PRES_SCRIPTS.parents[3]                  # .../23-ai-workforce-blueprint
_SKILL23_SCRIPTS = _SKILL23 / "scripts"
_QUESTIONS = _PRES_SCRIPTS.parent / "intake" / "deck-intake-questions.json"

# The turn that carries the run-mode axis, and the ledger key it lands on.
_RUN_MODE_TURN = "resource_plan"
_RUN_MODE_KEY = "RUN_MODE"
# A full answer for that turn: a model slot plus the mode declaration, phrased
# the way the bank's own labels accept it.
_ANSWER_ULTRA = "workhorse: deepseek-v4-flash@deepseek-direct; mode: ultra"
_ANSWER_NO_MODE = "workhorse: deepseek-v4-flash@deepseek-direct"


def _is_intake_driver(path: Path) -> bool:
    """A driver is a deck-intake script exposing the answer-recording CLI.

    Anchored on the CLI surface rather than the filename so a rename (which is
    how deck-intake-turngate.py came to exist) cannot slip a copy past this
    gate, and so non-driver helpers that merely sit in the same directory are
    not dragged in.
    """
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return '"--answer"' in src or "'--answer'" in src


def _discover_drivers() -> list:
    found = []
    for d in (_PRES_SCRIPTS, _SKILL23_SCRIPTS):
        if not d.is_dir():
            continue
        for p in sorted(d.glob("deck-intake-*.py")):
            if _is_intake_driver(p):
                found.append(p)
    return found


_DRIVERS = _discover_drivers()
_IDS = [str(p.relative_to(_SKILL23.parent)) for p in _DRIVERS]


def _record(driver: Path, run_dir: Path, answer: str):
    """Run one driver's --answer for the run-mode turn; return (rc, ledger)."""
    proc = subprocess.run(
        [sys.executable, str(driver), "--run-dir", str(run_dir),
         "--answer", _RUN_MODE_TURN, answer],
        capture_output=True, text=True, timeout=120,
    )
    ledger_path = run_dir / "working" / "interview" / "intake_ledger.json"
    ledger = {}
    if ledger_path.is_file():
        try:
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            ledger = {}
    return proc, ledger


def _run_mode_value(ledger: dict):
    entry = (ledger.get("entries") or {}).get(_RUN_MODE_KEY)
    if isinstance(entry, dict):
        return entry.get("value")
    return entry


# ---------------------------------------------------------------------------
# Discovery control -- a gate that inspects nothing must never report green.
# ---------------------------------------------------------------------------

def test_discovery_found_the_drivers():
    """Without this, an empty _DRIVERS list would make every parametrised case
    below vanish and the suite would pass having proved nothing. The canonical
    role-library driver must be among them."""
    assert _DRIVERS, (
        "no intake drivers discovered under "
        f"{_PRES_SCRIPTS} or {_SKILL23_SCRIPTS} -- the run-mode gate inspected "
        "nothing. Either the layout moved or _is_intake_driver() no longer "
        "recognises the answer-recording CLI."
    )
    canonical = _PRES_SCRIPTS / "deck-intake-driver.py"
    assert canonical in _DRIVERS, (
        f"the canonical driver {canonical} was not discovered; the gate is "
        "not looking where the shipping implementation lives."
    )


def test_the_run_mode_axis_is_still_on_the_resource_plan_turn():
    """Anchors the fixture: if the bank ever moves the run_mode subfield off
    this turn, the parametrised cases would silently stop exercising the axis
    while still passing. Fail here instead, loudly."""
    bank = json.loads(_QUESTIONS.read_text(encoding="utf-8"))
    turn = next((q for q in bank["questions"] if q.get("id") == _RUN_MODE_TURN), None)
    assert turn is not None, f"{_RUN_MODE_TURN} turn is gone from the bank"
    sub = (turn.get("subfields") or {}).get("run_mode")
    assert sub, f"{_RUN_MODE_TURN} no longer carries a run_mode subfield"
    assert sub.get("storeOn") == _RUN_MODE_KEY
    assert "ultra" in [str(v).lower() for v in (sub.get("enum") or [])]


# ---------------------------------------------------------------------------
# The gate itself -- executed, per driver.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("driver", _DRIVERS, ids=_IDS)
def test_declared_ultra_reaches_the_ledger(driver, tmp_path):
    """Declare ultra through this driver; RUN_MODE=ultra must land in the
    ledger presentation-intake-poll.sh reads. This is the whole defect."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    proc, ledger = _record(driver, run_dir, _ANSWER_ULTRA)

    assert proc.returncode == 0, (
        f"{driver} exited {proc.returncode} recording the run-mode turn\n"
        f"stdout: {proc.stdout[:800]}\nstderr: {proc.stderr[:800]}"
    )
    assert ledger, (
        f"{driver} wrote no readable intake ledger under {run_dir}\n"
        f"stdout: {proc.stdout[:800]}\nstderr: {proc.stderr[:800]}"
    )
    assert _run_mode_value(ledger) == "ultra", (
        f"{driver} accepted a client's ULTRA declaration but did not record "
        f"{_RUN_MODE_KEY} in the intake ledger. presentation-intake-poll.sh "
        "reads that key to open the run-mode door; without it the run "
        "silently executes STANDARD while every report says success. Every "
        "driver a caller can invoke must record the run mode -- delegate the "
        "ledger-writing commands to the canonical role-library driver rather "
        "than reimplementing them. Ledger entries seen: "
        f"{sorted((ledger.get('entries') or {}).keys())}"
    )


@pytest.mark.parametrize("driver", _DRIVERS, ids=_IDS)
def test_no_declaration_records_no_run_mode(driver, tmp_path):
    """The negative half of the gate. Without it, a driver that hardcoded
    RUN_MODE="ultra" unconditionally would pass the test above -- and would
    launch every client at the operator ceiling. Absence must stay absence:
    nothing silently escalates to ultra."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    proc, ledger = _record(driver, run_dir, _ANSWER_NO_MODE)

    assert proc.returncode == 0, (
        f"{driver} exited {proc.returncode} on a mode-less answer\n"
        f"stderr: {proc.stderr[:800]}"
    )
    assert _run_mode_value(ledger) is None, (
        f"{driver} invented a run mode from an answer that declared none "
        f"(recorded {_run_mode_value(ledger)!r}). An omitted declaration must "
        "record NOTHING so the launcher's own default applies -- never ultra "
        "by default."
    )
