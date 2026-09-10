"""F1 -- bounded auto-resume of parked runs.

WHAT IS BEING PINNED. Before F1, nothing in this system resumed a BLOCKED
run: the poller skipped it ("Already finished or parked -- skip"),
`supervisor.supervise()` skips DONE|BLOCKED|ABANDONED, `cc_board.
_dispatch_engine_if_idle` returns on a terminal, and the watchdog only
reports. One measured run took 22 h 14 min and 21 HUMAN `--resume` commands
to reach 37 of 38 phases; nine of those 21 passed on the very next try.

F1 adds a decider -- `presentation_job.auto_resume` -- and wires the poller's
BLOCKED branch to it. The danger of an auto-resume is not that it fails to
fire, it is that it fires FOREVER, so the majority of this file is about the
four bounds and about proving each one can actually stop a run, with a
control in the other direction for every single leg:

  CLASS     -- owner decisions never resume        (control: transient does)
  PHASE     -- close-time gates never resume       (control: a provider error
                                                    at the same phase does)
  CAP       -- 3 per rolling 24 h                  (control: 2 spent resumes;
                                                    control: rows older than
                                                    the window do not count)
  BACKOFF   -- attempt 2 waits 10 min              (control: an aged row
                                                    passes immediately)

Plus the F2 dependency, which is the reason F1 is dangerous on its own: a
run whose manifest pin moved dies EXIT_MANIFEST_MISMATCH about one second
into `__main__.main`, so an auto-resume without F2's auto-repin burns its
whole cap on three one-second deaths. Those legs prove the decider refuses
to spend an attempt it can predict will die -- and that it does NOT refuse
when F2 is present.

EVERY LEG IS OFFLINE. No engine, no renderer, no provider, no network. The
poller legs execute the SHIPPED walk-loop body against a scratch runs root
with `python3` stubbed; the unit legs import the real module and read real
files under tmp_path.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent  # .../presentations/scripts
POLL_SCRIPT = _SCRIPTS_DIR / "presentation-intake-poll.sh"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from presentation_job import auto_resume as ar  # noqa: E402
from presentation_job.heal import (  # noqa: E402
    FAILURE_OWNER_DECISION, FAILURE_PROVIDER_ERROR, FAILURE_TRANSIENT,
)


# ---------------------------------------------------------------------------
# Fixtures. Reason strings are REAL ones, copied from the code that writes
# them, because the whole class bound rides on `heal.classify_failure` seeing
# the vocabulary it was built for.
# ---------------------------------------------------------------------------

#: `phases._run_human_phase`'s style-pick timeout reason (the words "owner
#: decision" are what make it FAILURE_OWNER_DECISION).
OWNER_REASON = ("P-STYLE-PICK: the owner style pick timed out after 45 "
                "minutes with no verifiable owner choice. The full deck must "
                "NOT render until the owner picks A/B/C via their OWN gateway "
                "-- this is an owner decision")

#: The measured tail failure: nine of these passed on the very next resume.
TRANSIENT_REASON = "script executor failed after 3 attempts"

#: A provider refusal (`heal._PROVIDER_ERROR_MARKERS`).
PROVIDER_REASON = "HTTP 429 rate limit from deepseek-direct"

#: A verifier substance failure -- a judgement, not a blip.
SUBSTANCE_REASON = ("substance check failed: triggered autofails present: "
                    "['AF-C8 density ceiling exceeded on slide 20']")


def _stamp(when: datetime) -> str:
    """The same shape `state.utcnow()` writes (tz-aware ISO, seconds)."""
    return when.astimezone().isoformat(timespec="seconds")


def make_run(tmp_path: Path, *, terminal: str = "BLOCKED",
             phase: str = "P9.6-WEBINAR-VIDEO",
             reason: str = TRANSIENT_REASON,
             attempts: int = 0, attempt_age_minutes: float = 0.0,
             extra: dict | None = None, name: str = "pres-f1") -> Path:
    """A parked run dir. `attempts` pre-loads that many auto-resume rows, all
    `attempt_age_minutes` old, so a cap or backoff leg starts from a state the
    module itself would have written."""
    run_dir = tmp_path / name
    run_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    state = {
        "schema_version": 1,
        "job_id": "pj_f1",
        "run_dir": str(run_dir),
        "terminal": terminal,
        "phases": [],
    }
    if terminal == "BLOCKED":
        state["blocked"] = {"phase": phase, "reason": reason,
                            "at": _stamp(now - timedelta(minutes=90))}
    if attempts:
        state[ar.STATE_KEY] = [
            {"at": _stamp(now - timedelta(minutes=attempt_age_minutes)),
             "phase": phase, "class": FAILURE_TRANSIENT, "attempt": i + 1,
             "by": "presentation_job.auto_resume"}
            for i in range(attempts)
        ]
    if extra:
        state.update(extra)
    (run_dir / "state.json").write_text(json.dumps(state, indent=2),
                                        encoding="utf-8")
    return run_dir


def rows(run_dir: Path) -> list:
    doc = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    return doc.get(ar.STATE_KEY) or []


def cli(run_dir: Path, *extra: str) -> int:
    return ar.main(["--run-dir", str(run_dir), *extra])


@pytest.fixture(autouse=True)
def _no_rollback_no_transport(monkeypatch):
    """Every leg runs with the rollback OFF and no notify transport, unless
    the leg itself sets one. Inheriting an operator's env into a test is how a
    suite passes on one box and fails on another."""
    monkeypatch.delenv(ar.AUTO_RESUME_ENV, raising=False)
    monkeypatch.delenv("PRESENTATION_NOTIFY_CMD", raising=False)
    monkeypatch.delenv("PRESENTATION_MANIFEST", raising=False)


# ===========================================================================
# 1. CLASS -- an owner decision is never auto-resumed.
# ===========================================================================

def test_owner_decision_never_resumes(tmp_path):
    run_dir = make_run(tmp_path, phase="P-STYLE-PICK", reason=OWNER_REASON)
    d = ar.evaluate(run_dir)
    assert d.resume is False
    assert d.code == ar.DECISION_OWNER
    assert d.failure_class == FAILURE_OWNER_DECISION
    assert d.exit_code == ar.EXIT_SKIP
    assert cli(run_dir) == ar.EXIT_SKIP
    assert rows(run_dir) == [], (
        "an owner-decision park spent an auto-resume attempt -- the cap is "
        "then consumed by the one class of park that a resume can never fix"
    )


def test_transient_at_the_same_phase_does_resume(tmp_path):
    """CONTROL for the leg above: same phase, same fixture, retryable reason.
    Without this, "never resumes" could be passing because nothing ever
    resumes."""
    run_dir = make_run(tmp_path, phase="P-STYLE-PICK",
                       reason=TRANSIENT_REASON)
    d = ar.evaluate(run_dir)
    assert d.resume is True, d.why
    assert d.failure_class == FAILURE_TRANSIENT


def test_class_and_attempt_are_recorded_on_the_row(tmp_path):
    run_dir = make_run(tmp_path, reason=PROVIDER_REASON)
    assert cli(run_dir) == ar.EXIT_RESUME
    recorded = rows(run_dir)
    assert len(recorded) == 1, recorded
    row = recorded[0]
    assert row["class"] == FAILURE_PROVIDER_ERROR, row
    assert row["attempt"] == 1 and row["cap"] == ar.AUTO_RESUME_CAP, row
    assert row["phase"] == "P9.6-WEBINAR-VIDEO", row
    assert row["by"] == "presentation_job.auto_resume", row
    assert ar._parse_at(row["at"]) is not None, (
        f"the attempt stamp {row['at']!r} does not parse, so the rolling "
        "window can never count it and the cap is not a cap"
    )


# ===========================================================================
# 2. PHASE -- the close-time sentinels.
# ===========================================================================

@pytest.mark.parametrize("phase", list(ar.CLOSE_TIME_PHASES))
def test_close_time_gate_does_not_resume_on_a_judgement(tmp_path, phase):
    """CLOSE / CERT-INTEGRITY / CURATION / SELF-AUDIT are `Engine.close()`'s
    own sentinel strings. A gate that judged the artifacts and said no says no
    again when asked with the same artifacts."""
    run_dir = make_run(tmp_path, phase=phase, reason=SUBSTANCE_REASON)
    d = ar.evaluate(run_dir)
    assert d.resume is False and d.code == ar.DECISION_CLOSE_GATE, d.why
    assert cli(run_dir) == ar.EXIT_SKIP
    assert rows(run_dir) == []


@pytest.mark.parametrize("phase", list(ar.CLOSE_TIME_PHASES))
def test_close_time_gate_does_resume_when_nothing_was_judged(tmp_path, phase):
    """CONTROL: the same four phases with a PROVIDER failure. The gate never
    got to make a judgement -- something outside this system fell over -- so
    the carve-out applies and the run is retried."""
    run_dir = make_run(tmp_path, phase=phase, reason=PROVIDER_REASON)
    d = ar.evaluate(run_dir)
    assert d.resume is True, (
        f"a {phase} park caused by {PROVIDER_REASON!r} was refused; the "
        "close-time bound is then blocking retryable failures too: " + d.why
    )


def test_a_normal_phase_with_a_substance_failure_still_resumes(tmp_path):
    """CONTROL in the other direction: the substance reason itself is not what
    refuses above -- the PHASE is. The dispatcher re-authors with
    prior_reasons on a resume, so a substance park at an authoring phase is
    exactly the thing 21 human resumes were doing by hand."""
    run_dir = make_run(tmp_path, phase="P1Q-COPY-QC", reason=SUBSTANCE_REASON)
    assert ar.evaluate(run_dir).resume is True


# ===========================================================================
# 3. CAP -- three per rolling window, and it actually stops.
# ===========================================================================

def test_cap_is_honoured_at_three(tmp_path):
    run_dir = make_run(tmp_path, attempts=ar.AUTO_RESUME_CAP,
                       attempt_age_minutes=60)
    d = ar.evaluate(run_dir)
    assert d.resume is False and d.code == ar.DECISION_CAP, d.why
    assert cli(run_dir) == ar.EXIT_SKIP
    assert len(rows(run_dir)) == ar.AUTO_RESUME_CAP, (
        "a run at its cap recorded a FOURTH attempt row -- the ledger the cap "
        "is counted from is growing while the cap is supposedly holding"
    )


def test_one_under_the_cap_still_resumes(tmp_path):
    """CONTROL: the cap leg above must not be passing because nothing at all
    resumes once any row exists."""
    run_dir = make_run(tmp_path, attempts=ar.AUTO_RESUME_CAP - 1,
                       attempt_age_minutes=60)
    d = ar.evaluate(run_dir)
    assert d.resume is True, d.why
    assert d.attempt == ar.AUTO_RESUME_CAP


def test_attempts_older_than_the_window_do_not_count(tmp_path):
    """The cap is a ROLLING window, not a lifetime total: a run that spent
    three attempts two days ago is eligible again today."""
    stale = ar.AUTO_RESUME_WINDOW_HOURS * 60 + 30
    run_dir = make_run(tmp_path, attempts=ar.AUTO_RESUME_CAP,
                       attempt_age_minutes=stale)
    d = ar.evaluate(run_dir)
    assert d.resume is True, d.why
    assert d.attempt == 1, (
        "rows outside the window were still counted toward the attempt number"
    )


def test_four_consecutive_ticks_produce_at_most_three_attempts(tmp_path):
    """END TO END on the bound that matters: drive the CLI the way the poller
    does, once per tick, with the backoff satisfied each time, and prove the
    fourth tick spends nothing. This is the leg that would fail if any bound
    were merely advisory."""
    run_dir = make_run(tmp_path)
    codes = []
    for _ in range(4):
        codes.append(cli(run_dir))
        # Age every recorded attempt past the longest backoff, so this leg
        # tests the CAP and not the backoff (which has its own legs below).
        doc = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
        old = _stamp(datetime.now(timezone.utc) - timedelta(minutes=61))
        for row in doc.get(ar.STATE_KEY, []):
            row["at"] = old
        (run_dir / "state.json").write_text(json.dumps(doc, indent=2),
                                            encoding="utf-8")
    assert codes[:3] == [ar.EXIT_RESUME] * 3, codes
    assert codes[3] == ar.EXIT_SKIP, (
        f"the fourth tick was authorised ({codes}) -- the cap is not bounding "
        "anything and a broken run resumes forever at 12 attempts an hour"
    )
    assert len(rows(run_dir)) == 3


# ===========================================================================
# 4. BACKOFF -- the second and third attempts wait.
# ===========================================================================

def test_second_attempt_waits_for_the_backoff(tmp_path):
    run_dir = make_run(tmp_path, attempts=1, attempt_age_minutes=0.0)
    d = ar.evaluate(run_dir)
    assert d.resume is False and d.code == ar.DECISION_BACKOFF, d.why
    assert rows(run_dir) == rows(run_dir)  # nothing appended
    assert cli(run_dir) == ar.EXIT_SKIP
    assert len(rows(run_dir)) == 1


def test_second_attempt_proceeds_once_the_backoff_has_passed(tmp_path):
    """CONTROL: the same fixture with the row aged past the interval."""
    wait = ar.AUTO_RESUME_BACKOFF_MINUTES[1]
    run_dir = make_run(tmp_path, attempts=1, attempt_age_minutes=wait + 1)
    d = ar.evaluate(run_dir)
    assert d.resume is True, d.why
    assert d.attempt == 2


def test_the_first_attempt_is_immediate(tmp_path):
    """Deliberate: nine of the measured run's failures passed on the very next
    try, so making the FIRST retry wait is latency bought with nothing."""
    assert ar.AUTO_RESUME_BACKOFF_MINUTES[0] == 0
    run_dir = make_run(tmp_path)
    d = ar.evaluate(run_dir)
    assert d.resume is True and d.attempt == 1, d.why


# ===========================================================================
# 5. TERMINAL -- only a BLOCKED run is ever un-parked.
# ===========================================================================

@pytest.mark.parametrize("terminal", ["DONE", "ABANDONED", "", "REVIEW"])
def test_only_blocked_is_considered(tmp_path, terminal):
    run_dir = make_run(tmp_path, terminal=terminal)
    d = ar.evaluate(run_dir)
    assert d.resume is False and d.code == ar.DECISION_NOT_BLOCKED, d.why
    assert cli(run_dir) == ar.EXIT_SKIP
    assert rows(run_dir) == []


def test_blocked_is_considered(tmp_path):
    """CONTROL for the parametrised leg above."""
    assert ar.evaluate(make_run(tmp_path)).resume is True


# ===========================================================================
# 6. FAIL-CLOSED reads and the documented rollback.
# ===========================================================================

def test_missing_state_json_is_undetermined_not_a_resume(tmp_path):
    empty = tmp_path / "pres-empty"
    empty.mkdir()
    d = ar.evaluate(empty)
    assert d.resume is False and d.code == ar.DECISION_UNREADABLE
    assert d.exit_code == ar.EXIT_UNDETERMINED, (
        "an unreadable run must exit UNDETERMINED, not the same code as a "
        "decision -- 'I could not tell' and 'I decided no' are different facts"
    )
    assert cli(empty) == ar.EXIT_UNDETERMINED


def test_corrupt_state_json_is_undetermined_not_a_resume(tmp_path):
    bad = tmp_path / "pres-corrupt"
    bad.mkdir()
    (bad / "state.json").write_text("{not json at all", encoding="utf-8")
    d = ar.evaluate(bad)
    assert d.resume is False and d.exit_code == ar.EXIT_UNDETERMINED
    assert "unreadable" in d.why


def test_rollback_env_disables_every_decision(tmp_path, monkeypatch):
    monkeypatch.setenv(ar.AUTO_RESUME_ENV, "0")
    run_dir = make_run(tmp_path)
    d = ar.evaluate(run_dir)
    assert d.resume is False and d.code == ar.DECISION_DISABLED
    assert cli(run_dir) == ar.EXIT_SKIP
    assert rows(run_dir) == []


def test_check_mode_decides_without_spending(tmp_path):
    run_dir = make_run(tmp_path)
    assert cli(run_dir, "--check") == ar.EXIT_RESUME
    assert rows(run_dir) == [], (
        "--check recorded an attempt; an operator asking 'would this resume?' "
        "must not consume one of three daily attempts to find out"
    )


# ===========================================================================
# 7. THE F2 DEPENDENCY. An auto-resume without an auto-repin is worse than
#    none: it burns the whole cap dying EXIT_MANIFEST_MISMATCH after any roll.
# ===========================================================================

def _with_manifest(tmp_path: Path, *, pinned_matches: bool) -> Path:
    manifest = tmp_path / "PIPELINE-MANIFEST.json"
    manifest.write_text(json.dumps({"manifest_version": 67, "phases": []}),
                        encoding="utf-8")
    real = ar.sha256_file(manifest)
    pin = real if pinned_matches else ("0" * 64)
    return make_run(tmp_path, extra={"manifest_path": str(manifest),
                                     "manifest_sha256": pin})


def test_manifest_mismatch_without_f2_spends_no_attempt(tmp_path, monkeypatch):
    monkeypatch.setattr(ar, "_auto_repin_available",
                        lambda *a, **k: (False, "F2 auto-repin is NOT in this "
                                                "tree (test stand-in)"))
    run_dir = _with_manifest(tmp_path, pinned_matches=False)
    d = ar.evaluate(run_dir)
    assert d.resume is False and d.code == ar.DECISION_MANIFEST_PIN, d.why
    assert d.exit_code == ar.EXIT_UNDETERMINED
    assert "--repin" in d.why, (
        "the refusal does not name the command that cures it, so an operator "
        "reading the poll log learns nothing actionable"
    )
    assert cli(run_dir) == ar.EXIT_UNDETERMINED
    assert rows(run_dir) == [], (
        "an attempt was spent on a resume that dies EXIT_MANIFEST_MISMATCH in "
        "about one second -- three ticks later the cap is gone and the run is "
        "parked for a human WITH NO BUDGET LEFT once the pin is fixed"
    )


def test_manifest_mismatch_with_f2_present_proceeds(tmp_path, monkeypatch):
    """CONTROL: with F2's auto_repin_gate in the tree the launcher re-pins
    before it spawns, so the mismatch is not an obstacle and refusing here
    would block a resume that works."""
    monkeypatch.setattr(ar, "_auto_repin_available",
                        lambda *a, **k: (True, "auto_repin_gate present "
                                               "(test stand-in)"))
    run_dir = _with_manifest(tmp_path, pinned_matches=False)
    d = ar.evaluate(run_dir)
    assert d.resume is True, d.why


def test_matching_manifest_pin_resumes_either_way(tmp_path, monkeypatch):
    """CONTROL: when the pin MATCHES, F2's presence is irrelevant."""
    for available in (True, False):
        monkeypatch.setattr(ar, "_auto_repin_available",
                            lambda *a, **k: (available, "test stand-in"))
        run_dir = _with_manifest(tmp_path, pinned_matches=True)
        assert ar.evaluate(run_dir).resume is True


def test_attempts_spent_under_a_still_stale_pin_are_refunded(tmp_path,
                                                             monkeypatch):
    """The race F2 does not close from here: the manifest can move AFTER a
    decision and BEFORE the engine loads it. Those attempts bought no running
    engine, so the next tick refunds them rather than counting them."""
    monkeypatch.setattr(ar, "_auto_repin_available",
                        lambda *a, **k: (False, "F2 absent (test stand-in)"))
    run_dir = _with_manifest(tmp_path, pinned_matches=False)
    doc = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    doc[ar.STATE_KEY] = [
        {"at": _stamp(now - timedelta(minutes=10 * (i + 1))),
         "phase": "P4-COPY", "class": FAILURE_TRANSIENT, "attempt": i + 1,
         "manifest_sha256": doc["manifest_sha256"]}
        for i in range(ar.AUTO_RESUME_CAP)
    ]
    (run_dir / "state.json").write_text(json.dumps(doc, indent=2),
                                        encoding="utf-8")

    assert cli(run_dir) == ar.EXIT_UNDETERMINED
    after = rows(run_dir)
    assert len(after) == ar.AUTO_RESUME_CAP, "rows were deleted, not refunded"
    assert all(r.get("refunded") == "manifest-pin" for r in after), after
    counted = ar._counted_rows(
        json.loads((run_dir / "state.json").read_text(encoding="utf-8")), now)
    assert counted == [], (
        "refunded rows still count toward the cap, so a run stranded by a "
        "manifest bump stays capped out even after the pin is cured"
    )


def test_refund_never_touches_attempts_made_under_a_different_pin(tmp_path,
                                                                  monkeypatch):
    """CONTROL for the refund: it must only ever forgive attempts made under
    the pin that is STILL stale. An attempt from before the last repin is a
    real engine start and stays counted."""
    monkeypatch.setattr(ar, "_auto_repin_available",
                        lambda *a, **k: (False, "F2 absent (test stand-in)"))
    run_dir = _with_manifest(tmp_path, pinned_matches=False)
    doc = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    doc[ar.STATE_KEY] = [
        {"at": _stamp(datetime.now(timezone.utc) - timedelta(minutes=20)),
         "phase": "P4-COPY", "class": FAILURE_TRANSIENT, "attempt": 1,
         "manifest_sha256": "f" * 64},
    ]
    (run_dir / "state.json").write_text(json.dumps(doc, indent=2),
                                        encoding="utf-8")
    cli(run_dir)
    assert not rows(run_dir)[0].get("refunded"), rows(run_dir)


# --- the detector itself, with its own control ------------------------------

def _fake_scripts_dir(tmp_path: Path, launcher_src: str) -> Path:
    scripts = tmp_path / "scripts"
    (scripts / "presentation_job").mkdir(parents=True)
    (scripts / "presentation_job" / "launcher.py").write_text(
        launcher_src, encoding="utf-8")
    return scripts


def test_auto_repin_detector_says_present_absent_and_undetermined(tmp_path):
    present, why = ar._auto_repin_available(_fake_scripts_dir(
        tmp_path / "a", "def dispatch(x):\n    pass\n\n"
                        "def auto_repin_gate(a, b, c):\n    return None\n"))
    assert present is True, why

    absent, why = ar._auto_repin_available(_fake_scripts_dir(
        tmp_path / "b", "def dispatch(x):\n    pass\n"))
    assert absent is False, why
    assert "control OK" in why

    # THE CONTROL LEG, and the reason this function exists rather than a bare
    # `in` check: a launcher.py that does not even contain `def dispatch(` is
    # not a launcher this check can read, so the answer is UNDETERMINED. A
    # negative whose own control also comes back empty is a broken instrument.
    undetermined, why = ar._auto_repin_available(_fake_scripts_dir(
        tmp_path / "c", "# truncated file, nothing here\n"))
    assert undetermined is None, why
    assert "UNDETERMINED" in why

    missing, why = ar._auto_repin_available(tmp_path / "does-not-exist")
    assert missing is None, why


def test_auto_repin_env_rollback_counts_as_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("PRESENTATION_AUTO_REPIN", "0")
    present, why = ar._auto_repin_available(_fake_scripts_dir(
        tmp_path, "def dispatch(x):\n    pass\n\n"
                  "def auto_repin_gate(a, b, c):\n    return None\n"))
    assert present is False, (
        "F2's own documented rollback was ignored -- with auto-repin disabled "
        "the resume dies on the pin exactly as if F2 were absent: " + why
    )


def test_auto_repin_detector_finds_the_real_launcher(tmp_path):
    """CONTROL on the SHIPPED tree: whatever the answer is here, it must not
    be UNDETERMINED -- the real launcher.py is readable and contains the
    control symbol. This is the leg that fails if the detector is looking in
    the wrong place."""
    answer, why = ar._auto_repin_available()
    assert answer is not None, (
        "the detector cannot read this repository's own launcher.py, so every "
        f"manifest-mismatch decision it makes is UNDETERMINED: {why}"
    )


def test_an_unrecordable_attempt_refuses_instead_of_resuming(tmp_path,
                                                              monkeypatch):
    """FAIL-CLOSED on the ledger itself. A cap counted from a ledger that
    cannot be written is not a cap: every tick would read zero attempts and
    resume again, forever. So a failed record refuses the resume."""
    run_dir = make_run(tmp_path)
    monkeypatch.setattr(ar, "_merge", lambda *a, **k: False)
    d = ar.evaluate(run_dir)
    assert d.resume is True, "fixture is not eligible; the leg proves nothing"
    assert cli(run_dir) == ar.EXIT_UNDETERMINED, (
        "the CLI authorised a resume whose attempt could not be recorded -- "
        "an uncounted attempt repeats every five minutes forever"
    )
    assert rows(run_dir) == []


def test_a_recordable_attempt_still_resumes(tmp_path):
    """CONTROL: without the broken merge, the same fixture resumes and the row
    lands -- so the leg above is not passing because nothing ever resumes."""
    run_dir = make_run(tmp_path)
    assert cli(run_dir) == ar.EXIT_RESUME
    assert len(rows(run_dir)) == 1


# ===========================================================================
# 7b. THE REFUND -- the cap counts ENGINE STARTS, not dispatch attempts.
# ===========================================================================

def test_refund_gives_back_the_last_attempt_and_the_cap_notices(tmp_path):
    run_dir = make_run(tmp_path)
    assert cli(run_dir) == ar.EXIT_RESUME
    assert len(rows(run_dir)) == 1

    assert ar.refund_last_attempt(run_dir, "the launcher refused (exit 8)")
    row = rows(run_dir)[0]
    assert row["refunded"] == "no-engine-started", row
    assert "exit 8" in row["refunded_why"], row

    doc = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert ar._counted_rows(doc, datetime.now(timezone.utc)) == [], (
        "a refunded attempt still counts against the cap, so a run stranded "
        "by an unset PRESENTATION_NOTIFY_CMD stays capped out after the "
        "transport is fixed"
    )
    assert ar.evaluate(run_dir).resume is True, (
        "the run is not eligible again after its only attempt was refunded"
    )


def test_refund_marks_at_most_one_row(tmp_path):
    """BOUNDED: a refund is a correction of ONE charge, not an amnesty. Two
    refund calls after one attempt must not forgive an older, real one."""
    run_dir = make_run(tmp_path, attempts=1, attempt_age_minutes=600)
    doc = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    doc[ar.STATE_KEY][0]["by"] = "presentation_job.auto_resume"
    (run_dir / "state.json").write_text(json.dumps(doc, indent=2),
                                        encoding="utf-8")
    assert cli(run_dir) == ar.EXIT_RESUME          # a second, fresh attempt
    assert len(rows(run_dir)) == 2

    assert ar.refund_last_attempt(run_dir, "no engine started") is True
    refunded = [r for r in rows(run_dir) if r.get("refunded")]
    assert len(refunded) == 1, refunded
    assert refunded[0]["attempt"] == 2, (
        "the refund forgave the WRONG attempt -- it must be the newest "
        f"un-refunded one: {refunded}"
    )


def test_refund_never_touches_a_row_this_module_did_not_write(tmp_path):
    """CONTROL: an attempt row from any other writer is not this module's to
    forgive."""
    run_dir = make_run(tmp_path)
    doc = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    doc[ar.STATE_KEY] = [{"at": _stamp(datetime.now(timezone.utc)),
                          "attempt": 1, "by": "some-other-tool"}]
    (run_dir / "state.json").write_text(json.dumps(doc, indent=2),
                                        encoding="utf-8")
    assert ar.refund_last_attempt(run_dir, "not mine") is False
    assert not rows(run_dir)[0].get("refunded"), rows(run_dir)


def test_refund_cli_always_exits_zero(tmp_path):
    """The caller is already inside its dispatch-failure path. A refund that
    could fail the poller would add a second, unrelated failure to a log that
    is already reporting the first."""
    run_dir = make_run(tmp_path)
    assert cli(run_dir, "--refund", "nothing was charged yet") == ar.EXIT_RESUME
    empty = tmp_path / "pres-none"
    empty.mkdir()
    assert cli(empty, "--refund", "no state.json at all") == ar.EXIT_RESUME


# ===========================================================================
# 8. THE HARD STOP -- one operator alert per exhaustion, not one per tick.
# ===========================================================================

def _notify_stub(tmp_path: Path) -> tuple[Path, Path]:
    """A real PRESENTATION_NOTIFY_CMD transport, so `report.dispatch3` runs
    end to end (tokenise, subprocess, exit code) instead of being mocked."""
    stub = tmp_path / "notify.py"
    outbox = tmp_path / "outbox.jsonl"
    stub.write_text(
        "import json, sys\n"
        "doc = json.load(sys.stdin)\n"
        f"open({str(outbox)!r}, 'a').write(json.dumps(doc) + '\\n')\n",
        encoding="utf-8")
    return stub, outbox


def test_cap_exhaustion_alerts_once_not_every_tick(tmp_path, monkeypatch):
    stub, outbox = _notify_stub(tmp_path)
    monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", f"{sys.executable} {stub}")
    monkeypatch.setenv("OWNER_CHAT_ID", "8505558285")
    run_dir = make_run(tmp_path, attempts=ar.AUTO_RESUME_CAP,
                       attempt_age_minutes=60)

    for _ in range(4):
        assert cli(run_dir) == ar.EXIT_SKIP

    sent = [json.loads(l) for l in outbox.read_text().splitlines() if l.strip()]
    assert len(sent) == 1, (
        f"the cap-exhausted alert was sent {len(sent)} times; a parked run is "
        "polled every 5 minutes forever, so 'notify on exhaustion' without a "
        "stamp is an operator's chat filled with the same line all night"
    )
    assert sent[0]["chat_id"] == "8505558285", (
        "the alert did not resolve to the operator chat -- report."
        "KNOWN_SUBSYSTEM_IDS must contain the label this module dispatches "
        f"under ({ar.ALERT_CHAT_LABEL!r}), or it lands nowhere"
    )
    assert "EXHAUSTED" in sent[0]["message"] and run_dir.name in sent[0]["message"]


def test_the_exhaustion_alert_only_names_real_commands(tmp_path):
    """An alert that tells an operator to run a flag the parser does not have
    is worse than no alert: it costs them the time to find out. Every `--flag`
    in the message must exist in `presentation_job.__main__`'s own parser.
    (There is no `--diagnose`; the flag is `--diagnose-only`, and it only
    means anything alongside `--resume`.)"""
    main_src = (_SCRIPTS_DIR / "presentation_job" / "__main__.py").read_text(
        encoding="utf-8")
    declared = set(re.findall(r'add_argument\("(--[a-z0-9-]+)"', main_src))
    assert "--status" in declared and "--run-dir" in declared, (
        "the control failed: this test cannot read __main__'s parser, so it "
        f"cannot judge any flag. Found: {sorted(declared)}"
    )
    run_dir = make_run(tmp_path, attempts=ar.AUTO_RESUME_CAP,
                       attempt_age_minutes=60)
    message = ar._alert_message(run_dir, ar.evaluate(run_dir))
    used = set(re.findall(r'(--[a-z0-9-]+)', message))
    unknown = sorted(used - declared)
    assert not unknown, (
        f"the cap-exhausted alert tells the operator to run {unknown}, which "
        f"presentation_job.py does not accept. Message: {message}"
    )


def test_a_new_attempt_makes_the_next_exhaustion_news_again(tmp_path,
                                                            monkeypatch):
    """CONTROL for the leg above: the stamp must suppress a REPEAT, never the
    next real event. Age the rows out of the window, take a fresh attempt, put
    the run back at its cap, and the alert must fire a second time."""
    stub, outbox = _notify_stub(tmp_path)
    monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", f"{sys.executable} {stub}")
    monkeypatch.setenv("OWNER_CHAT_ID", "8505558285")
    run_dir = make_run(tmp_path, attempts=ar.AUTO_RESUME_CAP,
                       attempt_age_minutes=60)
    assert cli(run_dir) == ar.EXIT_SKIP
    assert cli(run_dir) == ar.EXIT_SKIP  # suppressed

    doc = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    stale = _stamp(datetime.now(timezone.utc)
                   - timedelta(hours=ar.AUTO_RESUME_WINDOW_HOURS + 1))
    for row in doc[ar.STATE_KEY]:
        row["at"] = stale
    (run_dir / "state.json").write_text(json.dumps(doc, indent=2),
                                        encoding="utf-8")
    assert cli(run_dir) == ar.EXIT_RESUME          # window rolled: one attempt
    doc = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    fresh = _stamp(datetime.now(timezone.utc) - timedelta(minutes=60))
    for row in doc[ar.STATE_KEY]:
        row["at"] = fresh
    doc[ar.STATE_KEY] = doc[ar.STATE_KEY][-1:] * ar.AUTO_RESUME_CAP
    (run_dir / "state.json").write_text(json.dumps(doc, indent=2),
                                        encoding="utf-8")
    assert cli(run_dir) == ar.EXIT_SKIP

    sent = [l for l in outbox.read_text().splitlines() if l.strip()]
    assert len(sent) == 2, (
        f"expected a second alert for the second exhaustion, got {len(sent)} "
        "-- the once-only stamp is suppressing real events, not repeats"
    )


def test_no_transport_does_not_break_the_decision(tmp_path):
    """PRESENTATION_NOTIFY_CMD unset (report.dispatch3 -> CheckResult.FAIL).
    The decision must still be a clean EXIT_SKIP: an alert that cannot be
    delivered is a fact to record, never a reason to stop deciding."""
    run_dir = make_run(tmp_path, attempts=ar.AUTO_RESUME_CAP,
                       attempt_age_minutes=60)
    assert cli(run_dir) == ar.EXIT_SKIP
    doc = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert doc[ar.ALERT_KEY]["delivered"] is False, doc.get(ar.ALERT_KEY)


# ===========================================================================
# 9. THE POLLER. Extract the SHIPPED walk-loop body and execute it.
#    A decider nothing calls is a decider that changes nothing.
# ===========================================================================

_WALK_RE = re.compile(
    r"while IFS= read -r run_dir;\s*do(?P<body>.*?)done\s*<\s*<\(find", re.S)
_HELPERS_RE = re.compile(
    r"# >>> POLLER-LAUNCH-VERIFY-BEGIN\n(?P<block>.*?)"
    r"# <<< POLLER-LAUNCH-VERIFY-END", re.S)

_STUB = """#!/usr/bin/env bash
REAL_PY={real_py}
_run_dir_from_argv() {
  _dir=""
  _prev=""
  for _a in "$@"; do
    if [ "$_prev" = "--run-dir" ]; then _dir="$_a"; fi
    _prev="$_a"
  done
}
if [ "$1" = "-c" ]; then
  case "$2" in
    *subprocess*) exit 0 ;;
    *) exec "$REAL_PY" "$@" ;;
  esac
fi
case " $* " in
  *" -m presentation_job.auto_resume "*)
    _run_dir_from_argv "$@"
    echo "auto-resume [STUB] rc {AUTO_RESUME_RC} for $_dir"
    exit {AUTO_RESUME_RC}
    ;;
  *" -m presentation_job.launcher "*)
    _run_dir_from_argv "$@"
    echo "launcher: dispatched (stub)"
    if [ -n "$_dir" ]; then
      mkdir -p "$_dir/working/logs"
      sleep 20 >/dev/null 2>&1 </dev/null &
      _epid=$!
      printf '%s\\n' "$_epid" > "$_dir/.engine.pid"
      printf '%s stub-engine\\n' "$_epid" > "$_dir/.job.lock"
    fi
    exit 0
    ;;
  *" -m "*) exit 0 ;;
  *) exec "$REAL_PY" "$@" ;;
esac
exit 0
"""


def _src() -> str:
    return POLL_SCRIPT.read_text(encoding="utf-8")


def _walk_body() -> str:
    m = _WALK_RE.search(_src())
    assert m, "could not find the poller's walk loop -- has its shape changed?"
    return m.group("body").rstrip("\n")


def _helpers() -> str:
    m = _HELPERS_RE.search(_src())
    assert m, "could not find the POLLER-LAUNCH-VERIFY block"
    return m.group("block").rstrip("\n")


def _make_blocked_run(runs_root: Path, name: str = "parked") -> Path:
    run_dir = runs_root / f"pres-{name}"
    (run_dir / "working" / "interview").mkdir(parents=True)
    (run_dir / "working" / "interview" / "intake_ledger.json").write_text(
        json.dumps({"status": "complete", "complete": True,
                    "requester_chat_id": "123456789",
                    "entries": {"presentation_type":
                                {"value": "from_scratch",
                                 "normalized": "from_scratch"}}}),
        encoding="utf-8")
    (run_dir / "state.json").write_text(json.dumps({
        "schema_version": 1, "job_id": "pj_parked", "terminal": "BLOCKED",
        "blocked": {"phase": "P9.6-WEBINAR-VIDEO",
                    "reason": TRANSIENT_REASON,
                    "at": _stamp(datetime.now(timezone.utc))},
    }), encoding="utf-8")
    return run_dir


def _run_walk(tmp_path: Path, runs_root: Path, *, auto_resume_rc: int,
              body: str | None = None, log_name: str = "poll.log",
              stub: bool = True) -> str:
    bindir = tmp_path / f"bin-{log_name}"
    bindir.mkdir()
    if stub:
        py = bindir / "python3"
        py.write_text(_STUB.replace("{real_py}", f'"{sys.executable}"')
                           .replace("{AUTO_RESUME_RC}", str(auto_resume_rc)),
                      encoding="utf-8")
        py.chmod(0o755)
    log_file = tmp_path / log_name
    harness = "\n".join([
        "set -uo pipefail",
        f'export PATH="{bindir}:$PATH"',
        "PROG=presentation-intake-poll.sh",
        f'LOG_FILE="{log_file}"',
        "log() {",
        '    echo "$(date \'+%Y-%m-%dT%H:%M:%S%z\') [$PROG] $*" >> "$LOG_FILE"',
        "}",
        "export PRESENTATION_LAUNCH_VERIFY_S=1",
        _helpers(),
        "read_run_mode() { :; }",
        f'RUNS_ROOT="{runs_root}"',
        f'SCRIPTS_DIR="{_SCRIPTS_DIR}"',
        f'ENGINE_ENTRY="{_SCRIPTS_DIR / "presentation_job.py"}"',
        f'LAUNCHER="{_SCRIPTS_DIR / "presentation_job" / "launcher.py"}"',
        'LEASE_ENABLED="0"',
        "NEW_LAUNCHES=0", "REFUSED_DISPATCH=0", "SKIPPED_RUNNING=0",
        "SKIPPED_NO_INTAKE=0", "SKIPPED_TERMINAL=0", "SKIPPED_LEASE_HELD=0",
        "SKIPPED_REFUSED_STICKY=0", "LEASE_TAKEOVERS=0", "RUN_DIRS_SEEN=0",
        'RUN_MODE=""',
        "while IFS= read -r run_dir; do",
        _walk_body() if body is None else body,
        'done < <(find "$RUNS_ROOT" -maxdepth 2 -type d -name "pres-*" '
        '-not -path "$RUNS_ROOT/_*" 2>/dev/null)',
        'log "scan complete: $NEW_LAUNCHES launched, $REFUSED_DISPATCH '
        'refused, $SKIPPED_TERMINAL terminal, $RUN_DIRS_SEEN seen"',
        "",
    ])
    result = subprocess.run(["bash", "-c", harness], capture_output=True,
                            text=True, timeout=120)
    assert result.returncode == 0, (
        "the harness itself failed -- a harness that aborts proves nothing.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}")
    return log_file.read_text(encoding="utf-8")


def test_poller_resumes_a_parked_run_when_the_decider_says_yes(tmp_path):
    runs_root = tmp_path / "runs"
    _make_blocked_run(runs_root)
    log_text = _run_walk(tmp_path, runs_root, auto_resume_rc=0)
    assert "resuming parked job" in log_text, (
        "a BLOCKED run the decider AUTHORISED was still not dispatched -- "
        "this is the entire F1 defect, unchanged. Log:\n" + log_text
    )
    assert "1 launched, 0 refused, 0 terminal, 1 seen" in log_text, log_text


def test_poller_leaves_it_parked_when_the_decider_says_no(tmp_path):
    """CONTROL: the leg above must not be passing because the poller now
    dispatches every BLOCKED run unconditionally, which is the unbounded
    auto-resume this whole design exists to avoid."""
    runs_root = tmp_path / "runs"
    _make_blocked_run(runs_root)
    log_text = _run_walk(tmp_path, runs_root, auto_resume_rc=3,
                         log_name="skip.log")
    assert "resuming parked job" not in log_text, log_text
    assert "0 launched, 0 refused, 1 terminal, 1 seen" in log_text, (
        "a declined auto-resume was not counted as terminal, so the run dir "
        "left the walk unaccounted for. Log:\n" + log_text
    )


def test_poller_leaves_it_parked_on_undetermined(tmp_path):
    runs_root = tmp_path / "runs"
    _make_blocked_run(runs_root)
    log_text = _run_walk(tmp_path, runs_root, auto_resume_rc=4,
                         log_name="undet.log")
    assert "resuming parked job" not in log_text, log_text
    assert "0 launched, 0 refused, 1 terminal, 1 seen" in log_text, log_text


#: What `python3 -m presentation_job.auto_resume` does on a box that has not
#: taken the scripts refresh: the interpreter aborts with exit 1 before any of
#: this module's code runs. Byte-for-byte the message CPython prints.
_NO_MODULE_STUB = """#!/usr/bin/env bash
REAL_PY={real_py}
if [ "$1" = "-c" ]; then
  case "$2" in
    *subprocess*) exit 0 ;;
    *) exec "$REAL_PY" "$@" ;;
  esac
fi
case " $* " in
  *" -m presentation_job.auto_resume "*)
    echo "/usr/bin/python3: No module named presentation_job.auto_resume" >&2
    exit 1
    ;;
  *" -m presentation_job.launcher "*)
    echo "launcher: dispatched (stub) -- THIS MUST NOT HAPPEN"
    exit 0
    ;;
  *" -m "*) exit 0 ;;
  *) exec "$REAL_PY" "$@" ;;
esac
exit 0
"""


def test_poller_fails_closed_when_the_decider_is_missing(tmp_path):
    """A box that has not taken the scripts refresh has no auto_resume module.
    `python3 -m` then exits 1 before any decision is made, and the poller must
    behave exactly as it did before F1 -- leave the run parked. FAIL-CLOSED is
    the requirement: an unavailable decider must never mean "resume anyway"."""
    runs_root = tmp_path / "runs"
    _make_blocked_run(runs_root)
    bindir = tmp_path / "bin-nomodule"
    bindir.mkdir()
    py = bindir / "python3"
    py.write_text(_NO_MODULE_STUB.replace("{real_py}", f'"{sys.executable}"'),
                  encoding="utf-8")
    py.chmod(0o755)

    log_file = tmp_path / "nomodule.log"
    harness = "\n".join([
        "set -uo pipefail",
        f'export PATH="{bindir}:$PATH"',
        "PROG=presentation-intake-poll.sh",
        f'LOG_FILE="{log_file}"',
        "log() {",
        '    echo "$(date \'+%Y-%m-%dT%H:%M:%S%z\') [$PROG] $*" >> "$LOG_FILE"',
        "}",
        "export PRESENTATION_LAUNCH_VERIFY_S=1",
        _helpers(),
        "read_run_mode() { :; }",
        f'RUNS_ROOT="{runs_root}"',
        f'SCRIPTS_DIR="{_SCRIPTS_DIR}"',
        f'ENGINE_ENTRY="{_SCRIPTS_DIR / "presentation_job.py"}"',
        f'LAUNCHER="{_SCRIPTS_DIR / "presentation_job" / "launcher.py"}"',
        'LEASE_ENABLED="0"',
        "NEW_LAUNCHES=0", "REFUSED_DISPATCH=0", "SKIPPED_RUNNING=0",
        "SKIPPED_NO_INTAKE=0", "SKIPPED_TERMINAL=0", "SKIPPED_LEASE_HELD=0",
        "SKIPPED_REFUSED_STICKY=0", "LEASE_TAKEOVERS=0", "RUN_DIRS_SEEN=0",
        'RUN_MODE=""',
        "while IFS= read -r run_dir; do",
        _walk_body(),
        'done < <(find "$RUNS_ROOT" -maxdepth 2 -type d -name "pres-*" '
        '-not -path "$RUNS_ROOT/_*" 2>/dev/null)',
        'log "scan complete: $NEW_LAUNCHES launched, $REFUSED_DISPATCH '
        'refused, $SKIPPED_TERMINAL terminal, $RUN_DIRS_SEEN seen"',
        "",
    ])
    result = subprocess.run(["bash", "-c", harness], capture_output=True,
                            text=True, timeout=120)
    assert result.returncode == 0, (
        f"harness aborted.\nstdout: {result.stdout}\nstderr: {result.stderr}")
    log_text = log_file.read_text(encoding="utf-8")

    assert "No module named presentation_job.auto_resume" in log_text, (
        "the poller never called the decider (or swallowed its error), so "
        "this leg proves nothing about the missing-module case. Log:\n"
        + log_text
    )
    assert "THIS MUST NOT HAPPEN" not in log_text, (
        "the poller resumed a parked run even though the decider could not "
        "run -- an unavailable bound is being read as permission. Log:\n"
        + log_text
    )
    assert "0 launched, 0 refused, 1 terminal, 1 seen" in log_text, log_text


def test_the_rollback_leaves_every_parked_run_parked(tmp_path, monkeypatch):
    """PRESENTATION_AUTO_RESUME=0 end to end through the REAL decider (no
    stub): the poller must fall back to exactly the pre-F1 behaviour."""
    runs_root = tmp_path / "runs"
    _make_blocked_run(runs_root)
    monkeypatch.setenv(ar.AUTO_RESUME_ENV, "0")
    log_text = _run_walk(tmp_path, runs_root, auto_resume_rc=0,
                         log_name="rollback.log", stub=False)
    assert "resuming parked job" not in log_text, (
        "PRESENTATION_AUTO_RESUME=0 did not stop the resume -- the documented "
        "rollback does not roll anything back. Log:\n" + log_text
    )
    assert "0 launched, 0 refused, 1 terminal, 1 seen" in log_text, log_text


def test_prefix_terminal_branch_would_never_have_resumed(tmp_path):
    """NEGATIVE CONTROL, permanently in the suite. Revert a SCRATCH COPY of
    the walk body to the pre-F1 three-value terminal test and confirm the same
    authorised run is NOT resumed -- proving the passing leg above is F1's
    change and not an artifact of the harness."""
    runs_root = tmp_path / "runs"
    _make_blocked_run(runs_root)
    body = _walk_body()
    reverted = body.replace(
        'if [ "$TERMINAL" = "DONE" ] || [ "$TERMINAL" = "ABANDONED" ]; then',
        'if [ "$TERMINAL" = "DONE" ] || [ "$TERMINAL" = "BLOCKED" ] '
        '|| [ "$TERMINAL" = "ABANDONED" ]; then')
    assert reverted != body, (
        "could not synthesize the pre-F1 terminal test -- this control would "
        "pass vacuously"
    )
    log_text = _run_walk(tmp_path, runs_root, auto_resume_rc=0,
                         body=reverted, log_name="prefix.log")
    assert "resuming parked job" not in log_text, log_text
    assert "0 launched" in log_text and "1 terminal" in log_text, log_text


def test_the_dispatch_line_is_unchanged_and_still_the_only_one(tmp_path):
    """F1 must not become a SECOND engine dispatcher. The authorised resume
    goes through the same launcher line every other resume uses, with the same
    client run-mode passthrough."""
    src = _src()
    resume_lines = [l for l in src.splitlines()
                    if "-m presentation_job.launcher --resume" in l
                    and not l.lstrip().startswith("#")]
    assert len(resume_lines) == 1, (
        f"expected exactly one --resume dispatch line, found {len(resume_lines)}"
        f": {resume_lines}"
    )
    assert '${RUN_MODE:+--mode "$RUN_MODE"}' in resume_lines[0], resume_lines[0]


def test_a_refused_dispatch_gives_the_attempt_back_end_to_end(tmp_path,
                                                              monkeypatch):
    """END TO END with NO stubs on either side: the REAL decider authorises a
    real parked run, the REAL launcher refuses the dispatch
    (AF-NOTIFY-UNCONFIGURED -- PRESENTATION_NOTIFY_CMD is unset, FIX 22
    fail-closed), and the attempt must come back.

    This is the leg that matters most for the bound being honest rather than
    merely small: without the refund, ONE unset environment variable spends
    all three of a run's daily attempts inside forty minutes and then parks it
    for a human -- and the "it needs you" alert goes out over the same
    transport that is unset."""
    monkeypatch.delenv("PRESENTATION_NOTIFY_CMD", raising=False)
    monkeypatch.setenv("PRESENTATION_PROVIDER_PROBES", "0")
    runs_root = tmp_path / "runs"
    run_dir = _make_blocked_run(runs_root)

    log_text = _run_walk(tmp_path, runs_root, auto_resume_rc=0,
                         log_name="e2e-refund.log", stub=False)

    assert "resuming parked job" in log_text, (
        "the real decider did not authorise a plainly retryable park. Log:\n"
        + log_text
    )
    assert "NOT LAUNCHED" in log_text, (
        "the real launcher did NOT refuse, so this leg proves nothing about "
        "the refund path. Log:\n" + log_text
    )
    doc = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    recorded = doc.get(ar.STATE_KEY) or []
    assert len(recorded) == 1, (
        f"expected exactly one attempt row, got {recorded}. Log:\n" + log_text
    )
    assert recorded[0].get("refunded") == "no-engine-started", (
        "an attempt was charged for a dispatch that started no engine, and "
        f"never given back: {recorded[0]}. Log:\n" + log_text
    )
    assert ar._counted_rows(doc, datetime.now(timezone.utc)) == [], recorded


def test_a_successful_auto_resume_is_not_refunded(tmp_path):
    """CONTROL for the leg above: when the dispatch DOES leave a running
    engine, the attempt stays charged. A refund that fired on success would
    make the cap unreachable and the bound imaginary."""
    runs_root = tmp_path / "runs"
    run_dir = _make_blocked_run(runs_root)
    log_text = _run_walk(tmp_path, runs_root, auto_resume_rc=0,
                         log_name="no-refund.log")
    assert "1 launched" in log_text, log_text
    assert "refunded" not in log_text, (
        "a SUCCESSFUL auto-resume was refunded. Log:\n" + log_text
    )


def test_a_human_resume_has_no_attempt_to_refund(tmp_path):
    """A run that was never BLOCKED never charged an attempt, so the refund
    hook must be a no-op on it -- it must not reach into an unrelated ledger."""
    runs_root = tmp_path / "runs"
    run_dir = _make_blocked_run(runs_root, "human")
    doc = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    doc["terminal"] = ""
    doc.pop("blocked", None)
    doc[ar.STATE_KEY] = [{"at": _stamp(datetime.now(timezone.utc)),
                          "attempt": 1,
                          "by": "presentation_job.auto_resume"}]
    (run_dir / "state.json").write_text(json.dumps(doc, indent=2),
                                        encoding="utf-8")
    log_text = _run_walk(tmp_path, runs_root, auto_resume_rc=0,
                         log_name="human.log")
    assert "auto-resume" not in log_text, (
        "the decider was consulted for a run that is not BLOCKED. Log:\n"
        + log_text
    )
    after = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert not after[ar.STATE_KEY][0].get("refunded"), after[ar.STATE_KEY]


def test_poll_script_is_valid_bash():
    result = subprocess.run(["bash", "-n", str(POLL_SCRIPT)],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
