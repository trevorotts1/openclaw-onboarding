"""EVERY invocable intake driver must LOCK the client's PLAN TIER onto the profile.

WHAT WENT WRONG (MEASURED on v25.0.17 / eaedc0633, before this gate existed).
The production intake never recorded a plan tier anywhere. The order-9
``resource_plan`` turn recorded the client's model plan and their run mode and
nothing else -- no call to ``resource_profile.record_plan_answer`` or
``record_conservative_default`` existed anywhere in production, only in
docstrings, comments and the ``capacity.py --answer-plan`` operator CLI.

Driving that turn with ``"$100/month"`` against a profile that owed an
ollama-cloud answer returned::

    rc=0   {"value": "$100/month", "validated": true}      <- a SUCCESS
    profile: plan_tier=None plan_known=None ceiling=None locked=None
    pending_questions() -> ['ollama-cloud']                <- STILL PENDING

The client was told their answer was accepted; the store that answer exists to
fill was never written. Two consequences, both live on the fleet:

  * ASK-ONCE IS VIOLATED TODAY. The bank promises this is asked once and then
    locked forever, and the lock IS the profile entry. Nothing wrote it, so an
    Ollama client is re-asked their plan on every deck they ever order.
  * DISPATCH PARKS. With no locked ceiling the run PARKs on
    AF-CAPACITY-UNMEASURED until an operator hand-runs the capacity CLI --
    which writes capacity_override.json instead, the single-provider file that
    drags every OTHER provider's width down with it.

WHY THIS TEST IS BEHAVIOURAL, NOT A GREP. A string check for
"record_plan_answer" is satisfied by the comment that already mentioned it on
pristine main -- which is precisely how this defect hid in plain sight. So each
driver is EXECUTED against a real run directory and the profile it actually
wrote is read back.

WHY IT DISCOVERS RATHER THAN LISTS. Same reason as its sibling
test_intake_driver_run_mode_unification.py: the defect class here is a NEW copy
appearing beside an old one, so every ``deck-intake-*.py`` exposing the
answer-recording CLI is collected and must pass. Today that is the canonical
role-library driver plus the two skill-23 entry points that delegate to it.

ISOLATION. Every case points PRESENTATION_RESOURCE_PROFILE_DIR and
PRESENTATION_CAPACITY_CONFIG_DIR at tmp_path for BOTH this process and the
driver subprocess, and disables provider probes. The operator's live profile at
~/.openclaw/state/presentation/resource_profile.json is never read or written.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_PRES_SCRIPTS = _TESTS_DIR.parent                    # .../presentations/scripts
_SKILL23 = _PRES_SCRIPTS.parents[3]                  # .../23-ai-workforce-blueprint
_SKILL23_SCRIPTS = _SKILL23 / "scripts"
_QUESTIONS = _PRES_SCRIPTS.parent / "intake" / "deck-intake-questions.json"

_TURN = "resource_plan"
_PROVIDER = "ollama-cloud"

# The tier the operator ruling prices at 8 concurrent agents, and the decline.
_TIER = "$100/month"
_TIER_CEILING = 8
_DECLINE = "use conservative default"
# An answer that addresses ONLY the model half of this merged turn. The bank
# gives the plan-tier subfield a documented default equal to its own
# conservative_value, so a naive reader of derive_structured_answer() sees
# "use conservative default" here and would lock a DECLINE the client never
# made -- pinning a $100/month client to the conservative floor 3 forever.
_MODEL_ONLY = "workhorse: glm-5.3-flash@ollama-cloud"
_UNKNOWN_TIER = "banana plan"


def _is_intake_driver(path: Path) -> bool:
    """A driver is a deck-intake script exposing the answer-recording CLI.

    Anchored on the CLI surface rather than the filename, so a rename cannot
    slip a copy past this gate."""
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


def _seed(tmp_path: Path) -> Path:
    """A config dir whose profile owes exactly one plan answer, for ollama-cloud.

    Written as literal JSON rather than through the engine so the fixture
    cannot drift with the code under test."""
    cfg = tmp_path / "cfg"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "resource_profile.json").write_text(json.dumps({
        ".schema_version": 1,
        "profile_version": "20260101T000000Z0000",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "providers": {_PROVIDER: {"provider": _PROVIDER}},
        "creative_prefs": {},
        "consent": {},
        "interview": {},
    }, indent=2), encoding="utf-8")
    return cfg


def _answer(driver: Path, tmp_path: Path, text: str):
    """Run one driver's --answer for this turn; return (proc, provider entry).

    The config dir is passed through the environment to the subprocess, so the
    operator's live profile is never a participant."""
    cfg = _seed(tmp_path)
    run_dir = tmp_path / "run"
    run_dir.mkdir(exist_ok=True)
    env = dict(os.environ)
    env["PRESENTATION_RESOURCE_PROFILE_DIR"] = str(cfg)
    env["PRESENTATION_CAPACITY_CONFIG_DIR"] = str(cfg)
    env["PRESENTATION_PROVIDER_PROBES"] = "0"
    proc = subprocess.run(
        [sys.executable, str(driver), "--run-dir", str(run_dir),
         "--answer", _TURN, text],
        capture_output=True, text=True, timeout=180, env=env,
    )
    profile = json.loads((cfg / "resource_profile.json").read_text(encoding="utf-8"))
    entry = (profile.get("providers") or {}).get(_PROVIDER) or {}
    return proc, entry, profile


# ---------------------------------------------------------------------------
# Non-vacuity controls -- a gate that inspects nothing must never report green.
# ---------------------------------------------------------------------------

def test_discovery_found_the_drivers():
    assert _DRIVERS, (
        f"no intake drivers discovered under {_PRES_SCRIPTS} or "
        f"{_SKILL23_SCRIPTS} -- the plan-tier gate inspected nothing."
    )
    canonical = _PRES_SCRIPTS / "deck-intake-driver.py"
    assert canonical in _DRIVERS, (
        f"the canonical driver {canonical} was not discovered; the gate is not "
        "looking where the shipping implementation lives."
    )


def test_the_plan_tier_half_is_still_on_this_turn():
    """Anchors the fixture. If the bank moves the plan-tier subfield off this
    turn, the cases below would stop exercising the axis while still passing."""
    bank = json.loads(_QUESTIONS.read_text(encoding="utf-8"))
    turn = next((q for q in bank["questions"] if q.get("id") == _TURN), None)
    assert turn is not None, f"{_TURN} turn is gone from the bank"
    sub = (turn.get("subfields") or {}).get(_TURN)
    assert sub, f"{_TURN} no longer carries its own plan-tier subfield"
    assert sub.get("conservative_value") == _DECLINE, (
        "the decline literal moved; _record_plan_tier reads it from the bank, "
        "so this fixture must follow it rather than hardcode a stale string."
    )


def test_this_turn_added_no_interview_turn():
    """The plan-tier wire rides the EXISTING order-9 turn. Trevor's ruling pins
    the interview at 23 turns; adding a 24th to record a plan tier is refused."""
    bank = json.loads(_QUESTIONS.read_text(encoding="utf-8"))
    assert bank["session_budget"]["max_turns"] == 23
    turn = next(q for q in bank["questions"] if q.get("id") == _TURN)
    assert turn.get("order") == 9 and turn.get("kind") == "merged"


# ---------------------------------------------------------------------------
# The gate itself -- executed, per driver.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("driver", _DRIVERS, ids=_IDS)
def test_a_declared_tier_locks_the_profile(driver, tmp_path):
    """THE DEFECT. A recognised tier must reach the profile as a locked entry
    with its cap-table ceiling. On pristine main nothing was written at all."""
    proc, entry, _ = _answer(driver, tmp_path, _TIER)

    assert proc.returncode == 0, (
        f"{driver} exited {proc.returncode} on a valid tier\n"
        f"stdout: {proc.stdout[:800]}\nstderr: {proc.stderr[:800]}"
    )
    assert entry.get("plan_tier") == _TIER, (
        f"{driver} accepted the client's plan tier {_TIER!r} but never recorded "
        f"it on the resource profile (entry: {entry!r}). The profile IS the "
        "store for this answer; without it the ask-once lock is never written, "
        "the client is re-asked every deck, and dispatch PARKs on "
        "AF-CAPACITY-UNMEASURED."
    )
    assert entry.get("plan_known") is True
    assert entry.get("concurrency_ceiling") == _TIER_CEILING, (
        f"{driver} recorded the tier without its cap-table ceiling "
        f"(got {entry.get('concurrency_ceiling')!r}, want {_TIER_CEILING}). "
        "The governor's reserve reads that number."
    )
    assert entry.get("locked") is True, (
        f"{driver} recorded the tier without locking the question. The lock is "
        "the ask-once contract the bank promises."
    )


@pytest.mark.parametrize("driver", _DRIVERS, ids=_IDS)
def test_the_declared_tier_ends_the_pending_question(driver, tmp_path):
    """Ask-once, proved on the surface the bank names as the ask-gate."""
    _answer(driver, tmp_path, _TIER)
    cfg = tmp_path / "cfg"
    sys.path.insert(0, str(_PRES_SCRIPTS))
    try:
        from presentation_job import resource_profile as rp  # noqa: PLC0415
        profile = json.loads((cfg / "resource_profile.json").read_text(encoding="utf-8"))
        pending = [q.get("provider") for q in rp.pending_questions(profile=profile)]
    finally:
        sys.path.remove(str(_PRES_SCRIPTS))
    assert _PROVIDER not in pending, (
        f"{driver} left {_PROVIDER} owing a plan answer after the client "
        f"answered it (pending: {pending!r}). That is the ask-once violation: "
        "the same question is put to the client on every subsequent deck."
    )


@pytest.mark.parametrize("driver", _DRIVERS, ids=_IDS)
def test_the_explicit_decline_locks_without_inventing_a_tier(driver, tmp_path):
    """The turn's OTHER documented choice. It locks ask-once exactly like a
    tier but must never invent a ceiling the client did not confirm."""
    proc, entry, _ = _answer(driver, tmp_path, _DECLINE)

    assert proc.returncode == 0, (
        f"{driver} exited {proc.returncode} on the documented decline\n"
        f"stderr: {proc.stderr[:800]}"
    )
    assert entry.get("locked") is True, (
        f"{driver} did not lock the question on an explicit decline "
        f"(entry: {entry!r}) -- the client was asked, and answered, exactly once."
    )
    assert entry.get("locked_choice") == _DECLINE
    assert entry.get("concurrency_ceiling") is None, (
        f"{driver} invented a ceiling {entry.get('concurrency_ceiling')!r} from "
        "a decline. A decline confirms nothing about the account."
    )


@pytest.mark.parametrize("driver", _DRIVERS, ids=_IDS)
def test_an_answer_about_models_only_records_no_plan_tier(driver, tmp_path):
    """THE FALSE-DECLINE GUARD, and the reason this wire cannot read
    derive_structured_answer()'s output.

    This merged turn asks its model/mode subfields of EVERY client, but its
    plan half only of a client the probe left a pending question for. The
    bank gives that subfield a documented default equal to its own
    conservative_value, so the derived answer to "workhorse: X" reads
    "use conservative default" -- a decline the client never uttered.

    Without this case, a driver that recorded the derived value would pass
    every other test in this file while silently locking a $100/month client
    at the conservative floor 3, forever, on the turn where they only picked a
    model. Absence must stay absence."""
    proc, entry, _ = _answer(driver, tmp_path, _MODEL_ONLY)

    assert proc.returncode == 0, (
        f"{driver} exited {proc.returncode} on a model-only answer\n"
        f"stderr: {proc.stderr[:800]}"
    )
    assert entry.get("locked") is not True, (
        f"{driver} locked the plan question from an answer that said nothing "
        f"about a plan (entry: {entry!r}). The client picked a model; they did "
        "not decline their tier, and they must still be asked for it."
    )
    assert entry.get("locked_choice") is None, (
        f"{driver} recorded the decline {entry.get('locked_choice')!r} that the "
        "client never made -- the plan-tier subfield's documented default was "
        "read as if it were an answer."
    )
    assert entry.get("plan_tier") is None


@pytest.mark.parametrize("driver", _DRIVERS, ids=_IDS)
def test_an_unrecordable_tier_is_refused_not_dropped(driver, tmp_path):
    """FAIL-CLOSED. A tier no pending provider can be on is refused while the
    client is still in the conversation, with the accepted tiers named -- never
    accepted-and-dropped, which is exactly the silent success that hid the
    original defect."""
    proc, entry, profile = _answer(driver, tmp_path, _UNKNOWN_TIER)

    assert proc.returncode != 0, (
        f"{driver} ACCEPTED the unrecordable tier {_UNKNOWN_TIER!r} (rc=0). The "
        "answer cannot be recorded, so accepting it tells the client they are "
        "measured when nothing was stored -- the defect this gate exists for.\n"
        f"stdout: {proc.stdout[:800]}"
    )
    assert "banana plan" in proc.stdout or "banana plan" in proc.stderr, (
        f"{driver} refused without echoing the offending value; the client "
        "cannot tell what was rejected."
    )
    combined = proc.stdout + proc.stderr
    assert _TIER in combined and _DECLINE in combined, (
        f"{driver} refused without naming the accepted tiers or the decline, so "
        f"the client has no way to answer correctly. Output: {combined[:600]}"
    )
    assert entry.get("locked") is not True and entry.get("plan_tier") is None, (
        f"{driver} half-landed a refused answer (entry: {entry!r})."
    )
    assert not (profile.get("interview") or {}).get("resource_plan"), (
        f"{driver} wrote an audit row for an answer it refused."
    )
