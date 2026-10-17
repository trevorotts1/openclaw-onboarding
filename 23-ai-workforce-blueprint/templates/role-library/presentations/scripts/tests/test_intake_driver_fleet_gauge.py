"""EVERY invocable intake driver must TAKE THE SYSTEM GAUGE at the
resource_plan turn and ASK the one fleet-shape question when it is owed.

WHAT WAS MISSING (the B27 follow-up this gate pins). FIX-PLAN Item 17
(B27) built record_system_gauge() / fleet_shape_question() /
record_fleet_shape() at the profile layer and named their production hook
in its manifest, in so many words: the intake driver's resource_plan turn
-- "one call to record_system_gauge() at that moment, plus asking
fleet_shape_question() when it returns a question". The functions shipped
(tested at the profile layer by test_item17_fleet_profiles.py) but no
driver ever called them:

  * the remembered system gauge was never taken at intake, so a later run
    started from unmeasured assertion instead of measured truth;
  * the fleet-shape question was never asked, so on a Linux container
    (fleet-hostinger or fleet-contabo -- indistinguishable from inside)
    the shape stayed unrecorded forever and the gauge's per-shape budget
    derivation (container budget, host ceiling) never had its input.

Measured against the pre-wiring driver (this stream's control run, on
pristine main): driving the resource_plan turn left the profile with NO
"system_gauge" key at all and produced NO fleet_shape event -- every case
below fails there and passes here.

WHY THIS TEST IS BEHAVIOURAL, NOT A GREP. The string "record_system_gauge"
already appeared in the driver's neighbourhood (docstrings and the
profile module itself) while the call did not exist -- the same hiding
place the plan-tier defect used. So each driver is EXECUTED against a
real run directory and the profile + event stream it actually wrote are
read back.

WHY IT DISCOVERS RATHER THAN LISTS. Same reason as its sibling
test_intake_driver_plan_tier.py: every ``deck-intake-*.py`` exposing the
answer-recording CLI is collected and must pass. The skill-23 entry
points delegate standard mode to the canonical role-library driver, so
the wiring is exercised through each of them.

THE ASKING CHANNEL. The fleet question is NOT a bank turn: the bank is
the 23-turn ceiling (Trevor ruling) and the question is an install-level
fact owed once, not a per-deck conversational turn. The driver asks it
through its durable question-owed channel -- the configuration_pending
event stream (PRES-006) at working/events/configuration_events.jsonl --
as an event with field "fleet_shape", the question text, the candidate
shapes, park_class client_action and waiting_on client. These cases read
that stream back.

ISOLATION. Every case points PRESENTATION_RESOURCE_PROFILE_DIR and
PRESENTATION_CAPACITY_CONFIG_DIR at tmp_path for BOTH this process and
the driver subprocess, and disables provider probes. The operator's live
profile at ~/.openclaw/state/presentation/resource_profile.json is never
read or written.
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
_TIER = "$100/month"
# An answer that addresses ONLY the model half of this merged turn: the
# gauge moment is the TURN, not the plan half, so the hook must fire for
# this answer too.
_MODEL_ONLY = "workhorse: glm-5.3-flash@ollama-cloud"

_EVENTS_RELPATH = Path("working") / "events" / "configuration_events.jsonl"


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


def _seed(tmp_path: Path, fleet: dict = None) -> Path:
    """A config dir whose profile owes exactly one plan answer, for
    ollama-cloud (the plan-tier sibling's fixture, so the turn is driven
    the same way). Written as literal JSON rather than through the engine
    so the fixture cannot drift with the code under test."""
    cfg = tmp_path / "cfg"
    cfg.mkdir(parents=True, exist_ok=True)
    profile = {
        ".schema_version": 1,
        "profile_version": "20260101T000000Z0000",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "providers": {_PROVIDER: {"provider": _PROVIDER}},
        "creative_prefs": {},
        "consent": {},
        "interview": {},
    }
    if fleet:
        profile["fleet"] = fleet
    (cfg / "resource_profile.json").write_text(json.dumps(profile, indent=2),
                                              encoding="utf-8")
    return cfg


def _answer(driver: Path, tmp_path: Path, text: str, fleet: dict = None,
            extra_env: dict = None):
    """Run one driver's --answer for this turn; return (proc, profile, events).

    The config dir is passed through the environment to the subprocess, so
    the operator's live profile is never a participant."""
    cfg = _seed(tmp_path, fleet=fleet)
    run_dir = tmp_path / "run"
    run_dir.mkdir(exist_ok=True)
    env = dict(os.environ)
    env["PRESENTATION_RESOURCE_PROFILE_DIR"] = str(cfg)
    env["PRESENTATION_CAPACITY_CONFIG_DIR"] = str(cfg)
    env["PRESENTATION_PROVIDER_PROBES"] = "0"
    env.pop("PRESENTATION_FLEET_SHAPE", None)
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(
        [sys.executable, str(driver), "--run-dir", str(run_dir),
         "--answer", _TURN, text],
        capture_output=True, text=True, timeout=180, env=env,
    )
    profile = json.loads((cfg / "resource_profile.json").read_text(encoding="utf-8"))
    events = []
    events_path = run_dir / _EVENTS_RELPATH
    if events_path.is_file():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return proc, profile, events


def _fleet_events(events):
    return [e for e in events if e.get("field") == "fleet_shape"]


def _rp():
    sys.path.insert(0, str(_PRES_SCRIPTS))
    try:
        from presentation_job import resource_profile as rp  # noqa: PLC0415
        return rp
    finally:
        sys.path.remove(str(_PRES_SCRIPTS))


# ---------------------------------------------------------------------------
# Non-vacuity controls -- a gate that inspects nothing must never report green.
# ---------------------------------------------------------------------------

def test_discovery_found_the_drivers():
    assert _DRIVERS, (
        f"no intake drivers discovered under {_PRES_SCRIPTS} or "
        f"{_SKILL23_SCRIPTS} -- the fleet-gauge gate inspected nothing."
    )
    canonical = _PRES_SCRIPTS / "deck-intake-driver.py"
    assert canonical in _DRIVERS, (
        f"the canonical driver {canonical} was not discovered; the gate is not "
        "looking where the shipping implementation lives."
    )


def test_the_fleet_question_is_not_a_bank_turn():
    """Anchors the wiring channel. The fleet-shape question rides the
    configuration_pending event stream, NOT the interview: the bank stays
    at Trevor's 23-turn ceiling and gains no fleet_shape turn."""
    bank = json.loads(_QUESTIONS.read_text(encoding="utf-8"))
    assert bank["session_budget"]["max_turns"] == 23
    ids = [q.get("id") for q in bank["questions"]]
    assert "fleet_shape" not in ids, (
        "a fleet_shape bank turn appeared -- the question is install-level "
        "and asked once at the gauge moment, never a 24th conversational turn."
    )


# ---------------------------------------------------------------------------
# The gate itself -- executed, per driver.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("driver", _DRIVERS, ids=_IDS)
def test_the_resource_plan_turn_takes_the_system_gauge(driver, tmp_path):
    """THE GAUGE. Answering resource_plan must persist a measured system
    gauge on the profile: measured_at stamped, the 24h persisted window
    carried, a hardware block read, and gauge_status no longer "missing".
    On the pre-wiring driver the profile gains no "system_gauge" key at
    all -- that absence is the defect."""
    proc, profile, _events = _answer(driver, tmp_path, _TIER)

    assert proc.returncode == 0, (
        f"{driver} exited {proc.returncode} on a valid tier\n"
        f"stdout: {proc.stdout[:800]}\nstderr: {proc.stderr[:800]}"
    )
    gauge = profile.get("system_gauge")
    assert isinstance(gauge, dict) and gauge, (
        f"{driver} accepted the resource_plan answer but never took the "
        f"system gauge (profile keys: {sorted(profile.keys())!r}). B27 "
        "named this turn as record_system_gauge()'s production hook; "
        "without the call the gauge exists only in tests."
    )
    assert gauge.get("measured_at"), (
        f"{driver} wrote a gauge with no measurement date: {gauge!r}"
    )
    assert gauge.get("max_age_s") == 24 * 3600.0, (
        f"{driver} wrote a gauge without the 24h persisted-measurement "
        f"window (got {gauge.get('max_age_s')!r})."
    )
    assert "fleet_shape" in gauge, (
        f"{driver} wrote a gauge that does not even record whether the "
        f"fleet shape is known: {sorted(gauge.keys())!r}"
    )
    hardware = gauge.get("hardware")
    assert isinstance(hardware, dict) and "ram_total_bytes" in hardware, (
        f"{driver} wrote a gauge with no hardware block: {gauge!r}"
    )
    assert isinstance(gauge.get("providers"), list), (
        f"{driver} wrote a gauge with no per-provider capacity rows: "
        f"{gauge!r}"
    )
    rp = _rp()
    status = rp.gauge_status(profile=profile)
    assert status["state"] == "fresh", (
        f"{driver} left a gauge whose own freshness check reads "
        f"{status['state']!r} ({status.get('detail')!r}) immediately after "
        "the turn that was supposed to take it."
    )


@pytest.mark.parametrize("driver", _DRIVERS, ids=_IDS)
def test_the_fleet_shape_question_is_asked_exactly_when_owed(driver, tmp_path):
    """THE QUESTION. When the profile layer still owes the fleet-shape
    question after the turn (shape unrecorded and detection cannot settle
    it), the driver must have asked it through the wired path: a
    configuration_pending event with field "fleet_shape", the question
    text and the candidate shapes. When nothing is owed, no event.

    The expectation is computed from the profile layer itself
    (fleet_shape_question against the profile the driver left), so the
    case is honest on any box: on a Mac detection settles fleet-mac and
    nothing is owed; on this Linux VM nothing is settled and the question
    is owed with every candidate open. The pre-wiring driver emits no
    fleet_shape event in EITHER world, so the owed world fails there."""
    proc, profile, events = _answer(driver, tmp_path, _MODEL_ONLY)

    assert proc.returncode == 0, (
        f"{driver} exited {proc.returncode} on a model-only answer\n"
        f"stderr: {proc.stderr[:800]}"
    )
    rp = _rp()
    owed = rp.fleet_shape_question(profile=profile)
    asked = _fleet_events(events)
    if owed is None:
        assert not asked, (
            f"{driver} asked a fleet-shape question the profile layer "
            f"says is not owed (shape already settled): {asked!r}. "
            "Ask-once means a settled shape is never re-asked."
        )
        return
    assert asked, (
        f"{driver} never asked the fleet-shape question the profile "
        f"layer still owes (candidates: {owed.get('candidates')!r}). No "
        "fleet_shape event exists in the run's configuration_pending "
        "stream -- the question B27 built fleet_shape_question() to ask "
        "was never put to anyone."
    )
    event = asked[-1]
    assert event.get("event") == "configuration_pending"
    assert event.get("question") == owed.get("question"), (
        f"{driver} asked a fleet-shape question whose text is not the "
        f"profile layer's question.\nasked: {event.get('question')!r}\n"
        f"owed:  {owed.get('question')!r}"
    )
    assert event.get("candidates") == owed.get("candidates")
    assert event.get("park_class") == "client_action"
    assert event.get("waiting_on") == "client"
    assert event.get("next_action"), (
        f"{driver} emitted a fleet-shape event with no next action: "
        f"{event!r}"
    )


@pytest.mark.parametrize("driver", _DRIVERS, ids=_IDS)
def test_a_recorded_shape_is_never_reasked_and_the_gauge_uses_it(driver, tmp_path):
    """ASK-ONCE. A profile that already carries the client's fleet-shape
    answer is gauged UNDER that shape and asked nothing: no fleet_shape
    event, and the gauge's per-shape derivation fields are present."""
    fleet = {"shape": "fleet-contabo", "source": "interview",
             "locked": True, "recorded_at": "2026-01-01T00:00:00+00:00",
             "answered_at": "2026-01-01T00:00:00+00:00"}
    proc, profile, events = _answer(driver, tmp_path, _MODEL_ONLY, fleet=fleet)

    assert proc.returncode == 0, (
        f"{driver} exited {proc.returncode}\nstderr: {proc.stderr[:800]}"
    )
    assert not _fleet_events(events), (
        f"{driver} re-asked the fleet-shape question for a shape the "
        f"client already answered and locked (fleet-contabo): "
        f"{_fleet_events(events)!r}. Asked once, then locked -- forever."
    )
    gauge = profile.get("system_gauge") or {}
    assert gauge.get("fleet_shape") == "fleet-contabo", (
        f"{driver} gauged under {gauge.get('fleet_shape')!r} instead of "
        "the recorded fleet-contabo shape."
    )
    hardware = gauge.get("hardware") or {}
    assert "container_budget_bytes" in hardware \
        and "host_ceiling_bytes" in hardware, (
        f"{driver} gauged a fleet-contabo box without the both-numbers "
        f"record (container budget AND host ceiling): {hardware!r}"
    )


@pytest.mark.parametrize("driver", _DRIVERS, ids=_IDS)
def test_an_install_time_declaration_settles_the_shape_inside_the_gauge(driver, tmp_path):
    """ORDERING. A valid $PRESENTATION_FLEET_SHAPE declaration is recorded
    BY the gauge (source "declared", locked) -- which is exactly why the
    driver gauges before it asks: after this turn no question is owed and
    none is asked. If the driver asked first (or never gauged), the
    declaration would sit unread and the question would go out anyway."""
    proc, profile, events = _answer(
        driver, tmp_path, _MODEL_ONLY,
        extra_env={"PRESENTATION_FLEET_SHAPE": "fleet-hostinger"})

    assert proc.returncode == 0, (
        f"{driver} exited {proc.returncode}\nstderr: {proc.stderr[:800]}"
    )
    fleet = profile.get("fleet") or {}
    assert fleet.get("shape") == "fleet-hostinger", (
        f"{driver} left the fleet record at {fleet!r} with "
        "PRESENTATION_FLEET_SHAPE=fleet-hostinger declared: the gauge "
        "never ran, so the declaration was never recorded."
    )
    assert fleet.get("source") == "declared"
    assert fleet.get("locked") is True
    gauge = profile.get("system_gauge") or {}
    assert gauge.get("fleet_shape") == "fleet-hostinger"
    assert not _fleet_events(events), (
        f"{driver} asked the fleet-shape question after the gauge had "
        f"already settled it from the declaration: "
        f"{_fleet_events(events)!r}. Gauge first, then ask what is "
        "still owed -- never the reverse."
    )
