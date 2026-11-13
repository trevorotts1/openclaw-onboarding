"""PD-045 — decide "legitimately skipped" and "provider failure" from
structured facts, not words.

Rows proved here:
  A1  a passing verifier whose note text names a gate decline does NOT defer
      the phase when the manifest's structured gate (`defers_unless`) is not
      the reason; a real decline (gate unsatisfied by the recorded intake
      answers) DOES defer it.  The same words under the OLD word-matching rule
      defer it — the AFTER assertion therefore kills the old behaviour.
  A2  a check message that contains the word "provider" and carries
      `failure_kind="check_failed"` is not routed as a provider outage; the
      same message WITHOUT a kind still classifies as provider_error (the
      BEFORE control — the test can fail).
  A3  every word-based classification logs `heal.classified_by_text`; a
      fact-based classification does not.
"""
import json
import sys
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

import phase_verifiers  # noqa: E402
from presentation_job import heal  # noqa: E402
from presentation_job.heal import classify_failure  # noqa: E402
from presentation_job.manifest import Manifest  # noqa: E402
from presentation_job.phases import Engine  # noqa: E402
from presentation_job.state import StateStore  # noqa: E402


def _mkmanifest(tmp_path, phases):
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps({"manifest_version": 25, "phases": phases}))
    return Manifest(mp)


def _mkengine(tmp_path, manifest, intake=None):
    rd = tmp_path / "r"
    rd.mkdir(exist_ok=True)
    store = StateStore(rd)
    s = {"schema_version": 1, "job_id": "t", "run_dir": str(rd),
         "created_at": "", "manifest_path": str(manifest.path),
         "manifest_version": 25, "manifest_sha256": manifest.sha256,
         "presentation_type": "from_scratch", "requester": {"chat_id": "t"},
         "phases": [], "gates": {}, "waivers": [], "events": [], "sent": {},
         "undeliverable": [], "heartbeat": {}, "terminal": None,
         "intake": intake or {}}
    store.save(s)
    return Engine(rd, manifest, store, s, dry_run=False), s


GATE = 'intake.want_vsl_page == "yes"'
DECLINE_WORDS = ("NOTE: the gate was declined by nobody; deferred maintenance",)


def _phases():
    return [
        {"id": "P-U-GATED", "order": 1, "owning_role": "t",
         "produces_artifact": ["u.txt"], "defers_unless": GATE,
         "executor": {"kind": "script", "cmd": "echo ok"}},
        {"id": "P-PLAIN", "order": 2, "owning_role": "t",
         "produces_artifact": ["p.txt"],
         "executor": {"kind": "script", "cmd": "echo ok"}},
    ]


class TestGateDeclineStructuredFacts:
    def test_words_alone_do_not_defer(self, tmp_path, monkeypatch):
        """A1 negative: verifier PASS whose notes name a gate decline, but the
        phase has no structured gate — must NOT defer."""
        m = _mkmanifest(tmp_path, _phases())
        e, _s = _mkengine(tmp_path, m, {"want_vsl_page": "no"})
        monkeypatch.setattr(phase_verifiers, "verify",
                            lambda pid, rd: (True, list(DECLINE_WORDS)))
        assert e._phase_is_gate_declined(m.phase("P-PLAIN")) is False
        # BEFORE control: the old word rule answers True for the same notes.
        joined = "; ".join(DECLINE_WORDS).lower()
        old = ("defer" in joined or "waived" in joined) and (
            "gate" in joined or "declined" in joined)
        assert old is True, "the words-only rule the test kills must fire"

    def test_real_structured_decline_defers(self, tmp_path, monkeypatch):
        """A1 positive: the phase's own defers_unless gate is unsatisfied by
        the recorded intake answers — the phase is legitimately skipped."""
        m = _mkmanifest(tmp_path, _phases())
        e, _s = _mkengine(tmp_path, m, {"want_vsl_page": "no"})
        monkeypatch.setattr(phase_verifiers, "verify",
                            lambda pid, rd: (True, []))
        assert e._phase_is_gate_declined(m.phase("P-U-GATED")) is True

    def test_satisfied_gate_is_not_a_decline(self, tmp_path, monkeypatch):
        m = _mkmanifest(tmp_path, _phases())
        e, _s = _mkengine(tmp_path, m, {"want_vsl_page": "yes"})
        monkeypatch.setattr(phase_verifiers, "verify",
                            lambda pid, rd: (True, list(DECLINE_WORDS)))
        assert e._phase_is_gate_declined(m.phase("P-U-GATED")) is False

    def test_failing_verifier_is_not_a_decline(self, tmp_path, monkeypatch):
        m = _mkmanifest(tmp_path, _phases())
        e, _s = _mkengine(tmp_path, m, {"want_vsl_page": "no"})
        monkeypatch.setattr(phase_verifiers, "verify",
                            lambda pid, rd: (False, ["substance missing"]))
        assert e._phase_is_gate_declined(m.phase("P-U-GATED")) is False

    def test_intake_file_fallback(self, tmp_path, monkeypatch):
        """No state["intake"] — the run's own intake.json is the structured
        source (the same file the verifier reads)."""
        m = _mkmanifest(tmp_path, _phases())
        e, _s = _mkengine(tmp_path, m, {})
        copy = e.run_dir / "working" / "copy"
        copy.mkdir(parents=True, exist_ok=True)
        (copy / "intake.json").write_text(
            json.dumps({"want_vsl_page": "no"}), encoding="utf-8")
        monkeypatch.setattr(phase_verifiers, "verify",
                            lambda pid, rd: (True, []))
        assert e._phase_is_gate_declined(m.phase("P-U-GATED")) is True


class TestFailureKind:
    def test_check_message_with_provider_word_is_not_a_provider_outage(self):
        """A2: the acceptance row, both sides."""
        msg = ("artifact matching deck.pptx exists but failed substance "
               "verification: the provider returned an empty body")
        assert classify_failure(msg, failure_kind="check_failed") \
            == heal.FAILURE_VERIFIER_SUBSTANCE
        assert classify_failure(msg) == heal.FAILURE_PROVIDER_ERROR

    def test_timeout_fact_is_not_a_provider_outage(self):
        assert classify_failure("exceeded its 30-minute budget: 402 seen in tail",
                                failure_kind="timeout") \
            == heal.FAILURE_TRANSIENT

    def test_exec_os_error_fact_is_transient(self):
        assert classify_failure("could not start: provider shell missing",
                                failure_kind="exec_os_error") \
            == heal.FAILURE_TRANSIENT

    def test_masked_402_exit_code_is_a_provider_fact(self):
        assert classify_failure("exit 146", failure_kind="exit_code:146") \
            == heal.FAILURE_PROVIDER_ERROR
        assert classify_failure("exit 1", failure_kind="exit_code:1") \
            == heal.FAILURE_TRANSIENT

    def test_classified_by_text_is_logged_only_on_the_words_path(
            self, capsys):
        """A3: the weaker evidence is named every time it is used."""
        assert classify_failure("HTTP 429 rate limit") \
            == heal.FAILURE_PROVIDER_ERROR
        err = capsys.readouterr().err
        assert "heal.classified_by_text" in err
        assert classify_failure("HTTP 429 rate limit",
                                failure_kind="check_failed") \
            == heal.FAILURE_VERIFIER_SUBSTANCE
        assert "heal.classified_by_text" not in capsys.readouterr().err


class TestAgentPhaseRouting:
    def _engine(self, tmp_path):
        m = _mkmanifest(tmp_path, _phases())
        e, _s = _mkengine(tmp_path, m, {"want_vsl_page": "no"})
        calls = []
        monkeypatch_targets = {}
        e._fail_unit = lambda phase, reason: (calls.append(("fail", phase.id)), 7)[1]
        monkeypatch_targets["regenerate"] = lambda eng, ph, rsn, **kw: (
            calls.append(("regenerate", rsn)), 1)[1]
        monkeypatch_targets["failover"] = lambda eng, ph, rsn, **kw: (
            calls.append(("failover", rsn)), 1)[1]
        return e, m, calls, monkeypatch_targets

    def test_check_failed_takes_regenerate_not_failover(self, tmp_path,
                                                       monkeypatch):
        e, m, calls, t = self._engine(tmp_path)
        monkeypatch.setattr(heal, "rung2_regenerate", t["regenerate"])
        monkeypatch.setattr(heal, "rung2_provider_failover", t["failover"])
        monkeypatch.setattr(heal, "_ledger", lambda *a, **kw: None)
        reason = ("artifact matching deck.pptx exists but failed substance "
                  "verification for 30 minutes: the provider returned nothing")
        e._heal_or_fail_agent_phase(m.phase("P-PLAIN"), reason,
                                    failure_kind="check_failed")
        assert [c[0] for c in calls] == ["regenerate", "fail"]

    def test_without_the_kind_the_old_words_path_fails_over(self, tmp_path,
                                                           monkeypatch):
        """BEFORE control: same message, no kind — provider failover fires, so
        the row above is a real discriminator."""
        e, m, calls, t = self._engine(tmp_path)
        monkeypatch.setattr(heal, "rung2_regenerate", t["regenerate"])
        monkeypatch.setattr(heal, "rung2_provider_failover", t["failover"])
        monkeypatch.setattr(heal, "_ledger", lambda *a, **kw: None)
        reason = ("artifact matching deck.pptx exists but failed substance "
                  "verification for 30 minutes: the provider returned nothing")
        e._heal_or_fail_agent_phase(m.phase("P-PLAIN"), reason)
        assert [c[0] for c in calls] == ["failover", "fail"]
