#!/usr/bin/env python3
"""test_fix29_style_pick_human_stage.py — FIX 29 (workflow R-B02, unit [opus] R-B02-B3).

PROOF (verbatim, from the fix brief / QC.md): a fresh deck-12 run stops at
P-STYLE-PICK with a delivered message (stub transport log) and continues only
after style_preview_choice.json with a verified owner_msg_id is written. A
choice without an id is rejected.

What FIX 29 declares and this file proves, without any network or model spend:

  1. The manifest declares the two new stages: P-STYLE-SPEC (order 4.84, agent,
     brand-steward, fanout by slide) authors working/copy/style_preview_spec.json
     — the spec P-STYLE-PREVIEW consumes — and P-STYLE-PICK (order 4.86, kind
     "human") is the owner gateway whose produces_artifact is
     working/copy/style_preview_choice.json.
  2. The engine dispatches kind "human" to a REAL executor (_run_human_phase),
     never the agent work-order loop that would forge the owner decision.
  3. THE LIVE PROOF RUN: a fresh run entering P-STYLE-PICK DELIVERS one pick
     request through the same reporter transport every client message uses
     (monkeypatched dispatch3 = the stub transport log), then STOPS — the run
     parks BLOCKED on the phase when the wait times out without a signed choice
     and without a recorded intake opt-in. Nothing is picked, nothing advances.
  4. The run CONTINUES only after style_preview_choice.json carries
     owner_approved:true + a chosen_variant from the offered set + an
     owner_msg_id the Fix 32 approvals oracle resolves to a REAL owner-authored
     message (stubbed oracle). The phase then attests done through the same
     substance verifier every phase runs.
  5. A choice WITHOUT an id is REJECTED: the file is denied loudly, the phase
     never completes, and the run still parks at the pick.
  6. The only auto-pick is the recorded opt-in: intake.style_pick_auto:true lets
     the timeout auto-pick variant 1 with auto_pick:true provenance — never a
     forged owner_msg_id. A falsy/missing field is never an opt-in.

Flat file inside tests/, manages its own import path — matching every sibling.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import approvals as approvals_mod  # noqa: E402
from presentation_job import phases as phases_mod  # noqa: E402
from presentation_job import report as report_mod  # noqa: E402
from presentation_job.manifest import Manifest  # noqa: E402
from presentation_job.phases import Engine  # noqa: E402
from presentation_job.state import EXIT_GATE_BLOCKED, StateStore  # noqa: E402

PICK = "P-STYLE-PICK"
SPEC = "P-STYLE-SPEC"
CHOICE_REL = "working/copy/style_preview_choice.json"
SAMPLES_REL = "working/style-preview/style_samples_manifest.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _canonical_manifest_path() -> Path:
    deployed = SCRIPTS.parent / "sops" / "PIPELINE-MANIFEST.json"
    if deployed.is_file():
        return deployed
    cur = SCRIPTS
    for _ in range(12):
        cand = cur / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
        if cand.is_file():
            return cand
        if cur.parent == cur:
            break
        cur = cur.parent
    raise FileNotFoundError("PIPELINE-MANIFEST.json not found from " + str(SCRIPTS))


def _manifest() -> Manifest:
    return Manifest(_canonical_manifest_path())


def _seed_run(tmp_path: Path, style_pick_auto=None) -> Path:
    """A fresh run dir: sealed intake, the samples manifest P-STYLE-PREVIEW
    produces (3 variant ids), and the minimal schema-complete state dict."""
    rd = tmp_path / "run"
    (rd / "working" / "copy").mkdir(parents=True)
    (rd / "working" / "style-preview").mkdir(parents=True)
    intake = {"business_name": "TestCo", "hook": "Grow without guesswork"}
    if style_pick_auto is not None:
        intake["style_pick_auto"] = style_pick_auto
    (rd / "working" / "copy" / "intake.json").write_text(json.dumps(intake))
    (rd / SAMPLES_REL).write_text(json.dumps({
        "schema": "style_samples_manifest/v1",
        "phase": "P-STYLE-PREVIEW (order 4.85)",
        "variants": ["A", "B", "C"],
        "representative_slides": [1, 2, 3],
        "owner_pick_required": True,
        "owner_pick_artifact": CHOICE_REL,
    }))
    return rd


def _engine(rd: Path) -> Engine:
    manifest = _manifest()
    store = StateStore(rd)
    state = {
        "schema_version": 1, "job_id": "t", "run_dir": str(rd),
        "created_at": "2026-01-01T00:00:00+00:00", "manifest_path": str(manifest.path),
        "manifest_version": manifest.version, "manifest_sha256": manifest.sha256,
        "presentation_type": "from_scratch", "requester": {"chat_id": "tc"},
        "phases": [], "gates": {}, "waivers": [], "events": [], "sent": {},
        "undeliverable": [], "heartbeat": {}, "terminal": None,
    }
    return Engine(rd, manifest, store, state, dry_run=False)


def _phase(rd: Path):
    return _manifest().phase_or_none(PICK)


def _stub_transport(monkeypatch):
    """The stub transport log: every delivered requester message lands here."""
    sent = []

    def _fake_dispatch3(chat_id, kind, message):
        sent.append({"chat_id": chat_id, "kind": kind, "message": message})
        return report_mod.CheckResult.PASS

    monkeypatch.setattr(report_mod, "dispatch3", _fake_dispatch3)
    return sent


def _stub_oracle(monkeypatch, ids):
    monkeypatch.setattr(
        approvals_mod, "_cc_board_oracle",
        lambda run_dir=None: frozenset(ids) if ids is not None else None)


def _write_choice(rd: Path, choice: dict) -> Path:
    p = rd / CHOICE_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(choice))
    return p


def _signed_choice(variant: str, msg_id: str = "owner-msg-42") -> dict:
    return {
        "owner_approved": True,
        "chosen_variant": variant,
        "owner_msg_id": msg_id,
        "approved_by": "owner",
        "reason": "variant B reads strongest on the data slide",
        "granted_at": datetime.now(timezone.utc).isoformat(),
        "picked_at": datetime.now(timezone.utc).isoformat(),
    }


def _phase_record(eng: Engine) -> dict:
    return next(ps for ps in eng.state["phases"] if ps["id"] == PICK)


# ---------------------------------------------------------------------------
# 1. Manifest wiring — the two new stages exactly as FIX 29 declares them.
# ---------------------------------------------------------------------------
class TestManifestWiring:
    def test_style_spec_agent_phase_4_84_authors_the_spec(self):
        m = _manifest()
        ph = m.phase_or_none(SPEC)
        assert ph is not None
        assert ph.order == pytest.approx(4.84)
        assert ph.executor_kind == "agent"
        assert ph.owning_role == "brand-steward"
        assert ph.produces_artifact == ["working/copy/style_preview_spec.json"]
        assert ph.fanout == {"by": "slide", "max_units": 3}
        assert "working/copy/slides.json" in ph.consumes
        assert "working/copy/intake.json" in ph.consumes

    def test_style_pick_human_stage_4_86(self):
        m = _manifest()
        ph = m.phase_or_none(PICK)
        assert ph is not None
        assert ph.order == pytest.approx(4.86)
        assert ph.executor_kind == "human", (
            "P-STYLE-PICK must declare executor kind 'human' — an agent executor "
            "on this phase is the forged-decision vector FIX 29 closes")
        assert ph.produces_artifact == [CHOICE_REL]
        assert "working/style-preview/style_samples_manifest.json" in ph.consumes

    def test_spec_feeds_preview_dag_edge(self):
        m = _manifest()
        preview = m.phase_or_none("P-STYLE-PREVIEW")
        spec = m.phase_or_none(SPEC)
        assert "working/copy/style_preview_spec.json" in preview.consumes
        assert spec.order < preview.order < m.phase_or_none(PICK).order

    def test_budgets_declared(self):
        from presentation_job.manifest import PHASE_BUDGET_MINUTES
        assert PHASE_BUDGET_MINUTES.get(SPEC) == 20
        assert PHASE_BUDGET_MINUTES.get(PICK) == 45

    def test_verifiers_registered(self):
        import phase_verifiers as pv
        assert pv.PHASE_VERIFIERS.get(SPEC) is not None
        assert pv.PHASE_VERIFIERS.get(PICK) is not None

    def test_engine_dispatches_human_kind_to_a_real_executor(self):
        src = Path(phases_mod.__file__).read_text(encoding="utf-8")
        assert 'elif phase.executor_kind == "human":' in src
        assert "rc = self._run_human_phase(phase)" in src


# ---------------------------------------------------------------------------
# 2. The pick-proof gate (_style_choice_authentic) — unit level.
# ---------------------------------------------------------------------------
class TestChoiceProofGate:
    def test_signed_choice_with_verified_id_passes(self, tmp_path, monkeypatch):
        eng = _engine(_seed_run(tmp_path))
        _stub_oracle(monkeypatch, ["owner-msg-42"])
        ok, denial = eng._style_choice_authentic(
            _signed_choice("B"), offered_variants=["A", "B", "C"])
        assert ok, denial

    def test_choice_without_id_is_rejected(self, tmp_path, monkeypatch):
        eng = _engine(_seed_run(tmp_path))
        _stub_oracle(monkeypatch, ["owner-msg-42"])
        choice = _signed_choice("A")
        choice.pop("owner_msg_id")
        ok, denial = eng._style_choice_authentic(choice, ["A", "B", "C"])
        assert not ok
        assert "owner_msg_id" in denial and "AF-FORGED-APPROVAL" in denial

    def test_unresolvable_id_is_denied_fail_closed(self, tmp_path, monkeypatch):
        eng = _engine(_seed_run(tmp_path))
        _stub_oracle(monkeypatch, ["a-different-id"])
        ok, denial = eng._style_choice_authentic(
            _signed_choice("A", msg_id="forged-1"), ["A", "B", "C"])
        assert not ok
        assert "forged-1" in denial

    def test_undetermined_oracle_denies(self, tmp_path, monkeypatch):
        eng = _engine(_seed_run(tmp_path))
        _stub_oracle(monkeypatch, None)  # board unreachable / no cc_task_id
        ok, denial = eng._style_choice_authentic(
            _signed_choice("A"), ["A", "B", "C"])
        assert not ok
        assert "UNDETERMINED" in denial or "authenticity" in denial

    def test_variant_not_offered_is_rejected(self, tmp_path, monkeypatch):
        eng = _engine(_seed_run(tmp_path))
        _stub_oracle(monkeypatch, ["owner-msg-42"])
        ok, denial = eng._style_choice_authentic(
            _signed_choice("D"), ["A", "B", "C"])
        assert not ok
        assert "not one of the offered variants" in denial

    def test_owner_approved_not_true_is_rejected(self, tmp_path, monkeypatch):
        eng = _engine(_seed_run(tmp_path))
        _stub_oracle(monkeypatch, ["owner-msg-42"])
        choice = _signed_choice("A")
        choice["owner_approved"] = "yes"
        ok, _ = eng._style_choice_authentic(choice, ["A", "B", "C"])
        assert not ok


# ---------------------------------------------------------------------------
# 3. The auto-pick opt-in — a recorded consent, never inferred.
# ---------------------------------------------------------------------------
class TestAutoPickOptIn:
    def test_true_intake_is_an_opt_in(self, tmp_path):
        eng = _engine(_seed_run(tmp_path, style_pick_auto=True))
        assert eng._style_pick_intake_auto() is True

    def test_nested_capture_opt_in_is_honored(self, tmp_path):
        rd = _seed_run(tmp_path)
        (rd / "working" / "copy" / "intake.json").write_text(json.dumps(
            {"business_name": "TestCo",
             "pre_presentation_capture": {"STYLE_PICK_AUTO": True}}))
        assert _engine(rd)._style_pick_intake_auto() is True

    def test_missing_or_falsy_is_never_an_opt_in(self, tmp_path):
        for i, val in enumerate((False, None, "true", 1)):
            rd = _seed_run(tmp_path / f"case{i}",
                           style_pick_auto=None if val is None else val)
            assert _engine(rd)._style_pick_intake_auto() is False, val

    def test_timeout_env_precedence(self, tmp_path, monkeypatch):
        eng = _engine(_seed_run(tmp_path))
        monkeypatch.setenv("PRESENTATION_STYLE_PICK_TIMEOUT_MINUTES", "0.25")
        assert eng._style_pick_timeout_minutes() == pytest.approx(0.25)
        monkeypatch.setenv("PRESENTATION_STYLE_PICK_TIMEOUT_MINUTES", "garbage")
        assert eng._style_pick_timeout_minutes() == pytest.approx(45.0)
        monkeypatch.delenv("PRESENTATION_STYLE_PICK_TIMEOUT_MINUTES")
        assert eng._style_pick_timeout_minutes() == pytest.approx(45.0)


# ---------------------------------------------------------------------------
# 4. THE LIVE PROOF RUN (the QC.md proof, end to end).
# ---------------------------------------------------------------------------
class TestLiveProofRun:
    def test_run_stops_at_the_pick_then_continues_on_a_signed_choice(
            self, tmp_path, monkeypatch):
        sent = _stub_transport(monkeypatch)
        _stub_oracle(monkeypatch, ["owner-msg-42"])
        monkeypatch.setenv("PRESENTATION_STYLE_PICK_TIMEOUT_MINUTES", "0.05")
        rd = _seed_run(tmp_path)  # NO intake.style_pick_auto opt-in
        eng = _engine(rd)
        phase = eng.manifest.phase_or_none(PICK)

        # --- 1. Fresh run: deliver the pick request, wait, stop. ------------
        rc = eng.run_phase(phase)
        assert rc == EXIT_GATE_BLOCKED
        rec = _phase_record(eng)
        assert rec["status"] == "blocked"
        assert eng.state["terminal"] == "BLOCKED"
        assert eng.state["blocked"]["phase"] == PICK
        # The delivered message: exactly ONE pick request on the stub transport
        # log, listing the three variants, stamped so a resume never re-spams.
        picks = [s for s in sent if s["kind"] == "ack"
                 and "style directions" in s["message"]]
        assert len(picks) == 1, sent
        assert "Variant A" in picks[0]["message"]
        assert "Variant B" in picks[0]["message"]
        assert "Variant C" in picks[0]["message"]
        assert rec.get("pick_request_sent_at")
        assert not (rd / CHOICE_REL).exists(), (
            "a run that stops at the pick must not pick anything by itself")

        # --- 2. A choice without an id is REJECTED (never advances). --------
        _write_choice(rd, {"owner_approved": True, "chosen_variant": "B"})
        rc = eng.run_phase(phase)
        assert rc == EXIT_GATE_BLOCKED
        assert _phase_record(eng)["status"] == "blocked"
        rejections = [e for e in eng.state["events"]
                      if e["kind"] == "phase.style_pick.choice_rejected"]
        assert rejections, "the id-less choice must be denied loudly"
        assert "owner_msg_id" in rejections[-1]["message"]
        assert eng.state["terminal"] == "BLOCKED"

        # --- 3. The signed choice: the run continues and attests done. ------
        _write_choice(rd, _signed_choice("B"))
        rc = eng.run_phase(phase)
        assert rc == 0, "the run must continue once the signed choice lands"
        rec = _phase_record(eng)
        assert rec["status"] == "done"
        assert rec.get("attested_at")
        assert rec.get("owner_pick", {}).get("chosen_variant") == "B"
        assert rec.get("owner_pick", {}).get("owner_msg_id") == "owner-msg-42"
        received = [e for e in eng.state["events"]
                    if e["kind"] == "phase.style_pick.choice_received"]
        assert received and "owner_msg_id verified" in received[-1]["message"]
        # No re-delivery on resume: still exactly one pick request total.
        picks = [s for s in sent if s["kind"] == "ack"
                 and "style directions" in s["message"]]
        assert len(picks) == 1

    def test_timeout_without_optin_parks_and_never_auto_picks(
            self, tmp_path, monkeypatch):
        sent = _stub_transport(monkeypatch)
        monkeypatch.setenv("PRESENTATION_STYLE_PICK_TIMEOUT_MINUTES", "0.05")
        rd = _seed_run(tmp_path)  # no opt-in
        eng = _engine(rd)
        phase = eng.manifest.phase_or_none(PICK)

        rc = eng.run_phase(phase)
        assert rc == EXIT_GATE_BLOCKED
        assert eng.state["blocked"]["phase"] == PICK
        assert not (rd / CHOICE_REL).exists()
        assert not any(e["kind"] == "phase.style_pick.auto_pick"
                       for e in eng.state["events"])
        timeouts = [e for e in eng.state["events"]
                    if e["kind"] == "phase.style_pick.timeout"]
        assert timeouts and "owner decision" in timeouts[-1]["message"]

    def test_timeout_with_recorded_optin_auto_picks_variant_1(
            self, tmp_path, monkeypatch):
        _stub_transport(monkeypatch)
        monkeypatch.setenv("PRESENTATION_STYLE_PICK_TIMEOUT_MINUTES", "0.05")
        rd = _seed_run(tmp_path, style_pick_auto=True)
        eng = _engine(rd)
        phase = eng.manifest.phase_or_none(PICK)

        rc = eng.run_phase(phase)
        assert rc == 0, "the recorded opt-in lets the timeout auto-pick"
        rec = _phase_record(eng)
        assert rec["status"] == "done"
        choice = json.loads((rd / CHOICE_REL).read_text())
        assert choice["owner_approved"] is True
        assert choice["chosen_variant"] == "A"
        assert choice["auto_pick"] is True
        assert "intake.style_pick_auto" in choice["auto_pick_basis"]
        assert not choice.get("owner_msg_id"), (
            "the auto-pick must never forge an owner_msg_id")
        # The substance verifier accepts the auto-pick shape (no id needed).
        import phase_verifiers as pv
        ok, reasons = pv.verify(PICK, rd)
        assert ok, reasons
