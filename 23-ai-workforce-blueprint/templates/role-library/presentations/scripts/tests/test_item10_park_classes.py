"""FIX-PLAN Item 10 -- park classes, one attempt ledger, client-visible state.

WHAT IS BEING PINNED. Before Item 10, auto_resume's bounds were per-path
conventions, not a policy: an owner-decision park and a missing-credential
park and a transient park were all just "BLOCKED with a reason", the park
path and the Fix 35 crash path kept SEPARATE attempt ledgers with separate
caps (so one counter could believe a run was capped while the other kept
resuming it), and the only client-visible trace of a park was the raw
engineering reason the engine sent at park time.

Item 10 adds, in presentation_job.auto_resume:

  CLASSES   -- every park is classified at the resume system's first
               evaluation of the recorded park into transient_infra
               (auto-resume on the existing bounded cadence),
               client_action (never auto-resume; the client is notified
               once with exactly what is needed), or operator_action
               (never auto-resume; the operator is notified with the
               specific action). A park with no classifiable content
               defaults to operator_action, the safest class, stated in
               code as DEFAULT_PARK_CLASS.
  ONE LEDGER-- park attempts and crash attempts are rows on ONE persisted
               ledger (state["auto_resume"], crash rows carry
               kind="crash") under ONE rolling-window cap. Rows a field
               run still holds in the legacy state["auto_resume_crash"]
               key keep counting, so an upgrade cannot hand a capped run
               a fresh budget.
  PARK STATUS-- every refused evaluation stamps state["park_status"], a
               client-safe record (class in plain words, what is needed
               from whom, since when). The raw park reason never appears
               in it.

EVERY LEG IS OFFLINE, like test_auto_resume.py: scratch run dirs, a real
notify stub for the notification legs, no engine, no network.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent  # .../presentations/scripts
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from presentation_job import auto_resume as ar  # noqa: E402
from presentation_job.heal import FAILURE_TRANSIENT  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures. Reason strings are REAL ones, copied from the code that writes
# them (same discipline as test_auto_resume.py).
# ---------------------------------------------------------------------------

OWNER_REASON = ("P-STYLE-PICK: the owner style pick timed out after 45 "
                "minutes with no verifiable owner choice. The full deck must "
                "NOT render until the owner picks A/B/C via their OWN gateway "
                "-- this is an owner decision")

TRANSIENT_REASON = "script executor failed after 3 attempts"

PROVIDER_REASON = "HTTP 429 rate limit from deepseek-direct"

SUBSTANCE_REASON = ("substance check failed: triggered autofails present: "
                    "['AF-C8 density ceiling exceeded on slide 20']")

NO_RESOLVABLE_KEY_REASON = ("provider kie has no resolvable key "
                            "(FIX 114: no store carries a plausible "
                            "credential)")

RESOURCE_PLAN_REASON = ("resource plan pending for provider "
                        "ollama-cloud: the client has not chosen a plan "
                        "tier")

MISSING_INTAKE_REASON = ("missing intake: no intake ledger was recorded "
                         "for this run")

MISSING_ARTIFACT_REASON = ("missing working/P4-COPY/slide-copy.json "
                           "for phase P4-COPY")


def _stamp(when: datetime) -> str:
    return when.astimezone().isoformat(timespec="seconds")


def make_run(tmp_path: Path, *, terminal: str = "BLOCKED",
             phase: str = "P9.6-WEBINAR-VIDEO",
             reason: str = TRANSIENT_REASON,
             attempts: int = 0, attempt_age_minutes: float = 0.0,
             crash_attempts: int = 0,
             extra: dict | None = None, name: str = "pres-i10") -> Path:
    """A parked run dir. `attempts` pre-loads unified-ledger park rows and
    `crash_attempts` pre-loads LEGACY crash-ledger rows (the pre-Item-10
    state["auto_resume_crash"] shape), so cap legs start from states real
    field runs actually carry."""
    run_dir = tmp_path / name
    run_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    state = {
        "schema_version": 1,
        "job_id": "pj_i10",
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
             "kind": "park", "by": "presentation_job.auto_resume"}
            for i in range(attempts)
        ]
    if crash_attempts:
        state[ar.CRASH_STATE_KEY] = [
            {"at": _stamp(now - timedelta(minutes=attempt_age_minutes)),
             "phase": phase, "class": "crash", "attempt": i + 1,
             "kind": "crash", "by": "presentation_job.auto_resume"}
            for i in range(crash_attempts)
        ]
    if extra:
        state.update(extra)
    (run_dir / "state.json").write_text(json.dumps(state, indent=2),
                                        encoding="utf-8")
    return run_dir


def make_dead_run(tmp_path: Path, *, attempts: int = 0,
                  crash_attempts: int = 0,
                  attempt_age_minutes: float = 60.0,
                  name: str = "pres-i10-dead") -> Path:
    """The Fix 35 crash shape: nonterminal, no blocked record, no engine."""
    run_dir = make_run(tmp_path, terminal="", attempts=attempts,
                       crash_attempts=crash_attempts,
                       attempt_age_minutes=attempt_age_minutes, name=name)
    return run_dir


def read_state(run_dir: Path) -> dict:
    return json.loads((run_dir / "state.json").read_text(encoding="utf-8"))


def rows(run_dir: Path) -> list:
    return read_state(run_dir).get(ar.STATE_KEY) or []


def cli(run_dir: Path, *extra: str) -> int:
    return ar.main(["--run-dir", str(run_dir), *extra])


@pytest.fixture(autouse=True)
def _no_rollback_no_transport(monkeypatch, tmp_path):
    """Same isolation as test_auto_resume.py: rollback off, no inherited
    notify transport, and the resource-profile store pointed at an empty
    per-test directory so no leg reads the operator's live profile."""
    monkeypatch.delenv(ar.AUTO_RESUME_ENV, raising=False)
    monkeypatch.delenv("PRESENTATION_NOTIFY_CMD", raising=False)
    monkeypatch.delenv("PRESENTATION_MANIFEST", raising=False)
    cfg = tmp_path / "profile-store"
    cfg.mkdir(exist_ok=True)
    monkeypatch.setenv("PRESENTATION_RESOURCE_PROFILE_DIR", str(cfg))
    monkeypatch.setenv("PRESENTATION_CAPACITY_CONFIG_DIR", str(cfg))


def _notify_stub(tmp_path: Path) -> tuple[Path, Path]:
    stub = tmp_path / "notify.py"
    outbox = tmp_path / "outbox.jsonl"
    stub.write_text(
        "import json, sys\n"
        "doc = json.load(sys.stdin)\n"
        f"open({str(outbox)!r}, 'a').write(json.dumps(doc) + '\\n')\n",
        encoding="utf-8")
    return stub, outbox


def _outbox(outbox: Path) -> list:
    if not outbox.exists():
        return []
    return [json.loads(l) for l in outbox.read_text().splitlines()
            if l.strip()]


# ===========================================================================
# 1. CLASSIFICATION -- one class per park shape, derived from the record.
# ===========================================================================

def test_provider_park_classifies_transient_infra(tmp_path):
    run_dir = make_run(tmp_path, reason=PROVIDER_REASON)
    park = ar.classify_park(read_state(run_dir))
    assert park["park_class"] == ar.PARK_CLASS_TRANSIENT_INFRA, park
    assert park["waiting_on"] == "system"
    assert park["auto_resume"] is True
    # And the policy is real: the park resumes under the existing bounds.
    assert ar.evaluate(run_dir).resume is True


def test_transient_park_classifies_transient_infra(tmp_path):
    run_dir = make_run(tmp_path, reason=TRANSIENT_REASON)
    park = ar.classify_park(read_state(run_dir))
    assert park["park_class"] == ar.PARK_CLASS_TRANSIENT_INFRA, park


def test_owner_decision_park_classifies_client_action(tmp_path):
    """The deciding party for an owner-decision park is the run's owner
    (the client): a style pick, a waiver, a gate decline. The run waits
    on the client, so the class is client_action, never operator."""
    run_dir = make_run(tmp_path, phase="P-STYLE-PICK", reason=OWNER_REASON)
    park = ar.classify_park(read_state(run_dir))
    assert park["park_class"] == ar.PARK_CLASS_CLIENT_ACTION, park
    assert park["waiting_on"] == "client"
    assert park["auto_resume"] is False
    d = ar.evaluate(run_dir)
    assert d.resume is False and d.code == ar.DECISION_OWNER, d.why
    assert d.park_class == ar.PARK_CLASS_CLIENT_ACTION


def test_missing_intake_classifies_client_action_and_never_resumes(tmp_path):
    """A missing INTAKE is owed by the client. Before Item 10 this park
    fell through every bound and burned auto-resume attempts on a resume
    that could not fix it."""
    run_dir = make_run(tmp_path, reason=MISSING_INTAKE_REASON)
    park = ar.classify_park(read_state(run_dir))
    assert park["park_class"] == ar.PARK_CLASS_CLIENT_ACTION, park
    d = ar.evaluate(run_dir)
    assert d.resume is False, d.why
    assert d.code == ar.DECISION_CLIENT_ACTION, d.why
    assert cli(run_dir) == ar.EXIT_SKIP
    assert rows(run_dir) == [], "a client-action park spent an attempt"


def test_missing_engine_artifact_stays_transient_infra(tmp_path):
    """CONTROL: heal's other missing-input markers name artifacts the
    ENGINE produces; a resume re-runs the producing phase, so those parks
    stay auto-resumable. The client split rides on the marker, not on
    the heal class alone."""
    run_dir = make_run(tmp_path, reason=MISSING_ARTIFACT_REASON)
    park = ar.classify_park(read_state(run_dir))
    assert park["park_class"] == ar.PARK_CLASS_TRANSIENT_INFRA, park
    assert ar.evaluate(run_dir).resume is True


def test_resource_plan_park_classifies_client_action(tmp_path):
    run_dir = make_run(tmp_path, phase="P0A-INTAKE",
                       reason=RESOURCE_PLAN_REASON)
    park = ar.classify_park(read_state(run_dir))
    assert park["park_class"] == ar.PARK_CLASS_CLIENT_ACTION, park
    d = ar.evaluate(run_dir)
    assert d.resume is False
    assert d.code == ar.DECISION_CONFIGURATION_PENDING


def test_credential_park_classifies_operator_action(tmp_path):
    run_dir = make_run(tmp_path, phase="P6-SLIDES",
                       reason=NO_RESOLVABLE_KEY_REASON)
    park = ar.classify_park(read_state(run_dir))
    assert park["park_class"] == ar.PARK_CLASS_OPERATOR_ACTION, park
    assert park["waiting_on"] == "operator"
    assert park["auto_resume"] is False
    d = ar.evaluate(run_dir)
    assert d.resume is False
    assert d.code == ar.DECISION_CONFIGURATION_PENDING


@pytest.mark.parametrize("phase", list(ar.CLOSE_TIME_PHASES))
def test_close_gate_verdict_classifies_operator_action(tmp_path, phase):
    run_dir = make_run(tmp_path, phase=phase, reason=SUBSTANCE_REASON)
    park = ar.classify_park(read_state(run_dir))
    assert park["park_class"] == ar.PARK_CLASS_OPERATOR_ACTION, park
    d = ar.evaluate(run_dir)
    assert d.resume is False and d.code == ar.DECISION_CLOSE_GATE, d.why


def test_unclassifiable_park_defaults_to_operator_action(tmp_path):
    """THE DOCUMENTED DEFAULT. A park record with no reason text carries
    nothing any classifier can read. heal.classify_failure calls an
    empty reason transient, but Item 10 does not let an unclassifiable
    park inherit the retry class by that accident: the default is
    operator_action, the class that never auto-resumes and puts a human
    on it."""
    assert ar.DEFAULT_PARK_CLASS == ar.PARK_CLASS_OPERATOR_ACTION
    run_dir = make_run(tmp_path, reason="")
    park = ar.classify_park(read_state(run_dir))
    assert park["park_class"] == ar.PARK_CLASS_OPERATOR_ACTION, park
    assert "default" in park["basis"], park
    d = ar.evaluate(run_dir)
    assert d.resume is False, d.why
    assert d.code == ar.DECISION_OPERATOR_ACTION, d.why
    assert cli(run_dir) == ar.EXIT_SKIP
    assert rows(run_dir) == [], "an unclassifiable park spent an attempt"


def test_park_record_without_a_reason_key_defaults_too(tmp_path):
    run_dir = make_run(tmp_path, reason=TRANSIENT_REASON)
    doc = read_state(run_dir)
    del doc["blocked"]["reason"]
    (run_dir / "state.json").write_text(json.dumps(doc, indent=2),
                                        encoding="utf-8")
    park = ar.classify_park(read_state(run_dir))
    assert park["park_class"] == ar.PARK_CLASS_OPERATOR_ACTION, park
    assert ar.evaluate(run_dir).resume is False


# ===========================================================================
# 2. PARK STATUS -- the client-safe record, for each class.
# ===========================================================================

def _park_status(run_dir: Path) -> dict:
    return read_state(run_dir).get(ar.PARK_STATUS_KEY) or {}


def test_park_status_for_a_client_action_park(tmp_path):
    run_dir = make_run(tmp_path, phase="P-STYLE-PICK", reason=OWNER_REASON)
    blocked_at = read_state(run_dir)["blocked"]["at"]
    assert cli(run_dir) == ar.EXIT_SKIP
    rec = _park_status(run_dir)
    assert rec["park_class"] == ar.PARK_CLASS_CLIENT_ACTION, rec
    assert rec["label"] == "Waiting for you", rec
    assert rec["waiting_on"] == "client", rec
    assert "A, B or C" in rec["needed"], rec
    assert rec["since"] == blocked_at, rec
    assert rec["auto_resume"] is False, rec
    dumped = json.dumps(rec)
    assert "timed out after 45" not in dumped, (
        "the raw engineering reason leaked into the client record")
    assert "owner_msg_id" not in dumped and "gateway" not in dumped


def test_park_status_for_an_operator_action_park(tmp_path):
    run_dir = make_run(tmp_path, phase="P6-SLIDES",
                       reason=NO_RESOLVABLE_KEY_REASON)
    blocked_at = read_state(run_dir)["blocked"]["at"]
    assert cli(run_dir) == ar.EXIT_SKIP
    rec = _park_status(run_dir)
    assert rec["park_class"] == ar.PARK_CLASS_OPERATOR_ACTION, rec
    assert rec["label"] == "Waiting for our team", rec
    assert rec["waiting_on"] == "operator", rec
    assert "credential" in rec["needed"], rec
    assert rec["since"] == blocked_at, rec
    dumped = json.dumps(rec)
    assert "resolvable" not in dumped and "FIX 114" not in dumped, (
        "the raw engineering reason leaked into the client record")


def test_park_status_for_a_transient_park_at_its_cap(tmp_path):
    run_dir = make_run(tmp_path, reason=PROVIDER_REASON,
                       attempts=ar.AUTO_RESUME_CAP, attempt_age_minutes=60)
    blocked_at = read_state(run_dir)["blocked"]["at"]
    assert cli(run_dir) == ar.EXIT_SKIP  # cap refusal
    rec = _park_status(run_dir)
    assert rec["park_class"] == ar.PARK_CLASS_TRANSIENT_INFRA, rec
    assert rec["waiting_on"] == "system", rec
    assert rec["auto_resume"] is True, rec
    assert rec["attempts_used"] == ar.AUTO_RESUME_CAP, rec
    assert rec["attempts_cap"] == ar.AUTO_RESUME_CAP, rec
    assert rec["since"] == blocked_at, rec
    dumped = json.dumps(rec)
    assert "deepseek" not in dumped and "429" not in dumped, (
        "the raw provider error leaked into the client record")


# ===========================================================================
# 3. NOTIFICATION RECORDS -- once per park, naming what is needed.
# ===========================================================================

def test_client_is_notified_once_with_what_is_needed(tmp_path, monkeypatch):
    stub, outbox = _notify_stub(tmp_path)
    monkeypatch.setenv("PRESENTATION_NOTIFY_CMD",
                       f"{sys.executable} {stub}")
    run_dir = make_run(tmp_path, phase="P-STYLE-PICK", reason=OWNER_REASON)
    # The requester address the way a real run carries it: the intake
    # ledger the poller and the bridge read.
    ledger_dir = run_dir / "working" / "interview"
    ledger_dir.mkdir(parents=True)
    (ledger_dir / "intake_ledger.json").write_text(json.dumps(
        {"status": "complete", "requester_chat_id": "123456789"}),
        encoding="utf-8")

    assert cli(run_dir) == ar.EXIT_SKIP
    assert cli(run_dir) == ar.EXIT_SKIP  # second tick: no second notice

    sent = _outbox(outbox)
    assert len(sent) == 1, (
        f"the client was notified {len(sent)} times for one park; the "
        "poller ticks every five minutes, so an unstamped notice is spam")
    assert sent[0]["chat_id"] == "123456789", sent
    assert "A, B or C" in sent[0]["message"], sent

    rec = read_state(run_dir).get(ar.PARK_NOTIFY_KEY) or {}
    assert rec["to"] == "client", rec
    assert rec["park_class"] == ar.PARK_CLASS_CLIENT_ACTION, rec
    assert rec["delivered"] is True, rec


def test_operator_is_notified_once_with_the_action_needed(tmp_path,
                                                          monkeypatch):
    stub, outbox = _notify_stub(tmp_path)
    monkeypatch.setenv("PRESENTATION_NOTIFY_CMD",
                       f"{sys.executable} {stub}")
    monkeypatch.setenv("OWNER_CHAT_ID", "8505558285")
    run_dir = make_run(tmp_path, phase="P6-SLIDES",
                       reason=NO_RESOLVABLE_KEY_REASON)

    assert cli(run_dir) == ar.EXIT_SKIP
    assert cli(run_dir) == ar.EXIT_SKIP

    sent = _outbox(outbox)
    assert len(sent) == 1, sent
    assert sent[0]["chat_id"] == "8505558285", sent
    assert "credential" in sent[0]["message"], sent

    rec = read_state(run_dir).get(ar.PARK_NOTIFY_KEY) or {}
    assert rec["to"] == "operator", rec
    assert rec["park_class"] == ar.PARK_CLASS_OPERATOR_ACTION, rec
    assert rec["delivered"] is True, rec


def test_notification_record_survives_a_missing_transport(tmp_path):
    """No PRESENTATION_NOTIFY_CMD: the record still lands, marked
    undelivered, and the decision is unchanged. A notice that cannot be
    sent is a fact to record, never a reason to resume or to crash."""
    run_dir = make_run(tmp_path, phase="P-STYLE-PICK", reason=OWNER_REASON)
    assert cli(run_dir) == ar.EXIT_SKIP
    rec = read_state(run_dir).get(ar.PARK_NOTIFY_KEY) or {}
    assert rec.get("to") == "client", rec
    assert rec.get("delivered") is False, rec


def test_check_mode_notifies_nobody_and_stamps_no_notice(tmp_path,
                                                         monkeypatch):
    stub, outbox = _notify_stub(tmp_path)
    monkeypatch.setenv("PRESENTATION_NOTIFY_CMD",
                       f"{sys.executable} {stub}")
    run_dir = make_run(tmp_path, phase="P-STYLE-PICK", reason=OWNER_REASON)
    assert cli(run_dir, "--check") == ar.EXIT_SKIP
    assert _outbox(outbox) == []
    assert not read_state(run_dir).get(ar.PARK_NOTIFY_KEY), (
        "--check sent or stamped a notification; the documented contract "
        "is that it notifies nobody")


# ===========================================================================
# 4. ONE LEDGER -- the two-cap race is closed.
# ===========================================================================

def test_attempt_rows_carry_kind_and_park_class(tmp_path):
    run_dir = make_run(tmp_path, reason=PROVIDER_REASON)
    assert cli(run_dir) == ar.EXIT_RESUME
    recorded = rows(run_dir)
    assert len(recorded) == 1, recorded
    assert recorded[0]["kind"] == "park", recorded
    assert recorded[0]["park_class"] == ar.PARK_CLASS_TRANSIENT_INFRA, recorded


def test_mixed_ledger_rows_cap_the_park_path(tmp_path):
    """Two park attempts plus one legacy crash attempt inside the window
    is a run AT its cap, whichever path asks."""
    run_dir = make_run(tmp_path, attempts=2, crash_attempts=1,
                       attempt_age_minutes=60)
    d = ar.evaluate(run_dir)
    assert d.resume is False and d.code == ar.DECISION_CAP, d.why
    assert cli(run_dir) == ar.EXIT_SKIP
    assert len(rows(run_dir)) == 2, "a capped run recorded another attempt"


def test_crash_rows_alone_cap_the_park_path(tmp_path):
    """THE RACE, one direction: three crash-path resumes must leave the
    park path with nothing to spend. Under the pre-Item-10 split ledger
    this run still had its full park budget."""
    run_dir = make_run(tmp_path, crash_attempts=ar.AUTO_RESUME_CAP,
                       attempt_age_minutes=60)
    d = ar.evaluate(run_dir)
    assert d.resume is False and d.code == ar.DECISION_CAP, d.why


def test_park_rows_alone_cap_the_crash_path(tmp_path):
    """THE RACE, the other direction."""
    run_dir = make_dead_run(tmp_path, attempts=ar.AUTO_RESUME_CAP)
    d = ar.evaluate_crash(run_dir)
    assert d.resume is False and d.code == ar.DECISION_CRASH_CAP, d.why


def test_mixed_ledger_rows_cap_the_crash_path(tmp_path):
    run_dir = make_dead_run(tmp_path, attempts=1, crash_attempts=2)
    d = ar.evaluate_crash(run_dir)
    assert d.resume is False and d.code == ar.DECISION_CRASH_CAP, d.why


def test_one_under_the_unified_cap_still_resumes_either_path(tmp_path):
    """CONTROL: unification must not become a stricter cap by accident.
    Two rows in the window, of either kind, leave one attempt."""
    parked = make_run(tmp_path, attempts=1, crash_attempts=1,
                      attempt_age_minutes=60, name="pres-i10-under-park")
    assert ar.evaluate(parked).resume is True
    dead = make_dead_run(tmp_path, attempts=1, crash_attempts=1,
                         name="pres-i10-under-dead")
    assert ar.evaluate_crash(dead).resume is True


def test_crash_attempt_lands_on_the_unified_ledger(tmp_path):
    run_dir = make_dead_run(tmp_path)
    assert cli(run_dir, "--crash") == ar.EXIT_RESUME
    recorded = rows(run_dir)
    assert len(recorded) == 1, recorded
    assert recorded[0]["kind"] == "crash", recorded
    assert not (read_state(run_dir).get(ar.CRASH_STATE_KEY) or []), (
        "a post-Item-10 crash attempt was written to the legacy ledger; "
        "the two streams are split again")


def test_crash_refund_reads_the_unified_ledger(tmp_path):
    run_dir = make_dead_run(tmp_path)
    assert cli(run_dir, "--crash") == ar.EXIT_RESUME
    assert ar.refund_last_crash_attempt(run_dir, "no engine started")
    recorded = rows(run_dir)
    assert recorded[0].get("refunded") == "no-engine-started", recorded
    state = read_state(run_dir)
    assert ar._counted_rows(state, datetime.now(timezone.utc)) == []


def test_park_refund_never_forgives_a_crash_row(tmp_path):
    """Kind-scoped refunds: the park path's refund hook (the poller's
    BLOCKED-branch failure path) must not reach a crash charge, and the
    crash refund must still find legacy-ledger rows."""
    run_dir = make_dead_run(tmp_path)
    assert cli(run_dir, "--crash") == ar.EXIT_RESUME
    assert ar.refund_last_attempt(run_dir, "wrong path") is False
    assert not rows(run_dir)[0].get("refunded"), rows(run_dir)

    legacy = make_run(tmp_path, crash_attempts=1, attempt_age_minutes=60,
                      name="pres-i10-legacy")
    assert ar.refund_last_crash_attempt(legacy, "no engine started")
    legacy_rows = read_state(legacy)[ar.CRASH_STATE_KEY]
    assert legacy_rows[0].get("refunded") == "no-engine-started", legacy_rows


# ===========================================================================
# 5. THE INTAKE DRIVER -- its own classification surface carries the class.
# ===========================================================================

def _load_driver():
    path = _SCRIPTS_DIR / "deck-intake-driver.py"
    spec = importlib.util.spec_from_file_location("deck_intake_driver", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_driver_configuration_pending_event_carries_the_park_class(tmp_path):
    """PRES-006's configuration_pending event is the intake driver's
    park-writing surface: the wait it records is owed by the CLIENT (the
    resource-plan answer), so the event now carries the Item 10 class at
    write time, alongside every field existing readers use."""
    driver = _load_driver()
    run_dir = tmp_path / "pres-i10-driver"
    events = driver._emit_configuration_pending(
        run_dir, ["ollama-cloud"], "plan tier", "sess-i10")
    assert len(events) == 1, events
    ev = events[0]
    assert ev["park_class"] == ar.PARK_CLASS_CLIENT_ACTION, ev
    assert ev["waiting_on"] == "client", ev
    assert ev["event"] == "configuration_pending", ev
    assert ev["owner"] == "presentation-intake", ev
    on_disk = [json.loads(l) for l in
               (run_dir / "working" / "events" /
                "configuration_events.jsonl").read_text().splitlines()]
    assert on_disk[0]["park_class"] == "client_action", on_disk
