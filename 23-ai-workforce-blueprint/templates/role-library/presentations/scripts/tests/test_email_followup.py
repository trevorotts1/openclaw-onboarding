#!/usr/bin/env python3
"""test_email_followup.py -- pins the Item 33c Skill 50 email election
contract (scripts/email_followup.py): the delivery-phase draft-package
preparation and the verbatim declined-reason waiver.

The election: intake pre_presentation_capture.WANT_EMAIL_SEQUENCES
(default "no"; only an explicit "yes" elects) + its verbatim waiver
EMAIL_SEQUENCES_DECLINED_REASON. The delivery contract: elected runs get
the Skill 50 sequences PREPARED as a draft package (working/email/
email-brief.json + the Skill 44 operator handoff) awaiting HUMAN approval;
the module never sends and never arms, and these tests assert the absence
of a send path structurally (AST scan of the module source). Declined
prepares nothing and records the client's own words; unanswered defers;
Skill 50 unavailable records the fallback and prepares nothing.

Flat file inside scripts/tests/, manages its own import path -- matching
every sibling in this directory (test_upsell_intake_shape.py, test_gates.py).
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SCRIPTS))

import email_followup as ef  # noqa: E402
from presentation_job.defers import evaluate_defers_unless  # noqa: E402
from presentation_job.resolve_intake import (  # noqa: E402
    _UPSELL_FIELDS,
    _resolve_upsell_capture,
)

REASON = "We run our own email list already."


def _nested(want, reason=None, sales="yes", **extra):
    pre = {"WANT_EMAIL_SEQUENCES": want}
    if reason is not None:
        pre["EMAIL_SEQUENCES_DECLINED_REASON"] = reason
    if sales is not None:
        pre["WANT_SALES_CHECKOUT"] = sales
    intake = {"pre_presentation_capture": pre,
              "deck_brief": {"OFFER_NAME": "The Offer",
                             "TONE": "warm and direct",
                             "AUDIENCE": "coaches"},
              "client_name": "Alex Founder"}
    intake.update(extra)
    return intake


def _fake_skill50(tmp_path: Path) -> Path:
    d = tmp_path / "50-email-engine"
    d.mkdir()
    (d / "SKILL.md").write_text("# Email Engine (test double)\n",
                                encoding="utf-8")
    return d


def _brief(run: Path) -> dict:
    return json.loads((run / ef.BRIEF_REL).read_text(encoding="utf-8"))


def _brief_pkg(run: Path, sequence_id: str) -> dict:
    return {p["sequence_id"]: p for p in _brief(run)["packages"]}[sequence_id]


# ---------------------------------------------------------------------------
# The gate (mirrors the sales/VSL waiver discipline)
# ---------------------------------------------------------------------------

class TestGate:
    def test_yes_prepares(self):
        g = ef.resolve_email_gate(_nested("yes"))
        assert g["decision"] == "prepare"

    def test_flat_shape_yes_prepares(self):
        g = ef.resolve_email_gate({"WANT_EMAIL_SEQUENCES": "yes"})
        assert g["decision"] == "prepare"

    def test_absent_defers(self):
        g = ef.resolve_email_gate({})
        assert g["decision"] == "defer"

    def test_blank_defers(self):
        g = ef.resolve_email_gate(_nested("   "))
        assert g["decision"] == "defer"

    def test_no_with_reason_waives_with_verbatim_quote(self):
        g = ef.resolve_email_gate(_nested("no", REASON))
        assert g["decision"] == "waived"
        assert g["quote"] == REASON

    def test_no_without_reason_fails_closed(self):
        g = ef.resolve_email_gate(_nested("no"))
        assert g["decision"] == "fail_closed"
        assert ef.AF_WAIVER_MISSING in g["detail"]

    def test_no_with_blank_reason_fails_closed(self):
        g = ef.resolve_email_gate(_nested("no", "   "))
        assert g["decision"] == "fail_closed"
        assert ef.AF_WAIVER_MISSING in g["detail"]

    def test_unrecognized_value_fails_closed(self):
        g = ef.resolve_email_gate(_nested("maybe"))
        assert g["decision"] == "fail_closed"
        assert ef.AF_VALUE_UNRECOGNIZED in g["detail"]


# ---------------------------------------------------------------------------
# The delivery contract: prepare, never send, never arm
# ---------------------------------------------------------------------------

class TestPrepare:
    def test_elected_prepares_both_packages_awaiting_approval(self, tmp_path):
        run = tmp_path / "run"
        run.mkdir()
        ck = ef.prepare_draft_packages(run, _nested("yes"),
                                       skill50_dir=_fake_skill50(tmp_path))
        assert ck["outcome"] == "prepared_awaiting_human_approval"
        assert ck["approval"]["status"] == "AWAITING_HUMAN_APPROVAL"
        entries = {p["sequence_id"]: p for p in ck["packages"]}
        assert set(entries) == {"landing-page-10-promo",
                                "high-ticket-appointment"}
        assert entries["landing-page-10-promo"]["status"] == "prepared_draft"
        assert entries["high-ticket-appointment"]["status"] == "prepared_draft"
        # The three artifacts exist on disk.
        assert (run / ef.BRIEF_REL).is_file()
        assert (run / ef.HANDOFF_REL).is_file()
        assert (run / ef.CHECKPOINT_REL).is_file()
        # Sequence definitions carry Skill 50's sacred lengths.
        promo = _brief_pkg(run, "landing-page-10-promo")
        appt = _brief_pkg(run, "high-ticket-appointment")
        assert promo["sequence_definition"]["email_count"] == 10
        assert promo["sequence_definition"]["objective"] == "promotional"
        assert appt["sequence_definition"]["email_count"] == 12
        assert promo["status"] == "DRAFT_AWAITING_HUMAN_APPROVAL"
        assert appt["status"] == "DRAFT_AWAITING_HUMAN_APPROVAL"

    def test_brief_answers_come_from_the_run_record_only(self, tmp_path):
        run = tmp_path / "run"
        run.mkdir()
        ef.prepare_draft_packages(run, _nested("yes"),
                                  skill50_dir=_fake_skill50(tmp_path))
        brief = _brief(run)
        assert brief["status"] == "DRAFT_AWAITING_HUMAN_APPROVAL"
        appt = _brief_pkg(run, "high-ticket-appointment")
        assert appt["brief_answers"]["offer"] == "The Offer"
        assert appt["brief_answers"]["brand_voice"] == "warm and direct"
        assert appt["brief_answers"]["founder_name"] == "Alex Founder"
        assert appt["audience"]["value"] == "coaches"
        assert appt["audience"]["source_field"] == "deck_brief.AUDIENCE"
        assert appt["trigger"] == "delivery completion (post-delivery follow-up)"
        assert appt["approval"]["status"] == "AWAITING_HUMAN_APPROVAL"
        # The Skill 50 one-block attestation is NEVER fabricated here: the
        # field names appear only in the brief's explanatory note prose,
        # never as data keys anywhere in the document.
        def _keys(node):
            if isinstance(node, dict):
                for k, v in node.items():
                    yield k
                    yield from _keys(v)
            elif isinstance(node, list):
                for v in node:
                    yield from _keys(v)
        all_keys = set(_keys(brief))
        assert "asked_all_at_once" not in all_keys
        assert "question_block_msg_id" not in all_keys

    def test_missing_inputs_are_named_not_invented(self, tmp_path):
        run = tmp_path / "run"
        run.mkdir()
        intake = _nested("yes")
        del intake["client_name"]
        ef.prepare_draft_packages(run, intake,
                                  skill50_dir=_fake_skill50(tmp_path))
        appt = _brief_pkg(run, "high-ticket-appointment")
        assert appt["brief_answers"]["founder_name"] is None
        assert "founder_name" in appt["missing_inputs"]

    def test_promo_not_applicable_without_the_page_launch(self, tmp_path):
        run = tmp_path / "run"
        run.mkdir()
        ck = ef.prepare_draft_packages(run, _nested("yes", sales="no"),
                                       skill50_dir=_fake_skill50(tmp_path))
        entries = {p["sequence_id"]: p for p in ck["packages"]}
        assert entries["landing-page-10-promo"]["status"] == "not_applicable"
        assert "no page launch" in entries["landing-page-10-promo"]["detail"]
        assert entries["high-ticket-appointment"]["status"] == "prepared_draft"
        assert ck["outcome"] == "prepared_awaiting_human_approval"

    def test_skill50_unavailable_records_the_fallback(self, tmp_path):
        run = tmp_path / "run"
        run.mkdir()
        ck = ef.prepare_draft_packages(run, _nested("yes"),
                                       skill50_dir=None,
                                       _skill50_searched=True)
        assert ck["outcome"] == "elected_skill50_unavailable_nothing_prepared"
        assert ck["skill50"]["available"] is False
        entries = {p["sequence_id"]: p for p in ck["packages"]}
        assert entries["high-ticket-appointment"]["status"] == "not_prepared"
        assert not (run / "working" / "email").exists()
        assert (run / ef.CHECKPOINT_REL).is_file()

    def test_declined_prepares_nothing_and_records_the_waiver(self, tmp_path):
        run = tmp_path / "run"
        run.mkdir()
        ck = ef.prepare_draft_packages(run, _nested("no", REASON))
        assert ck["outcome"] == "waived_nothing_prepared"
        assert ck["waiver"]["rule"] == "email_sequences"
        assert ck["waiver"]["client_request_quote"] == REASON
        assert not (run / "working" / "email").exists()
        assert (run / ef.CHECKPOINT_REL).is_file()

    def test_unanswered_defers_and_records(self, tmp_path):
        run = tmp_path / "run"
        run.mkdir()
        ck = ef.prepare_draft_packages(run, {})
        assert ck["outcome"] == "deferred_nothing_prepared"
        assert not (run / "working" / "email").exists()
        assert (run / ef.CHECKPOINT_REL).is_file()

    def test_handoff_names_the_human_approval_step(self, tmp_path):
        run = tmp_path / "run"
        run.mkdir()
        ef.prepare_draft_packages(run, _nested("yes"),
                                  skill50_dir=_fake_skill50(tmp_path))
        handoff = json.loads((run / ef.HANDOFF_REL).read_text(encoding="utf-8"))
        assert handoff["kind"] == "skill44-operator-handoff"
        assert handoff["status"] == "AWAITING_HUMAN_APPROVAL"
        assert "human" in handoff["approval_step"].lower()
        assert "working/checkpoints/email.json" in handoff["approval_step"]
        assert "No live send exists" in handoff["wiring_gate"]


# ---------------------------------------------------------------------------
# No send path exists (structural assertion)
# ---------------------------------------------------------------------------

class TestNoSendPath:
    def test_module_imports_no_network_or_process_machinery(self):
        tree = ast.parse(Path(ef.__file__).read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        banned = {"smtplib", "socket", "subprocess", "requests", "urllib",
                  "http", "ftplib", "telnetlib"}
        assert imported.isdisjoint(banned), imported & banned

    def test_module_has_no_send_like_calls(self):
        tree = ast.parse(Path(ef.__file__).read_text(encoding="utf-8"))
        offenders = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = getattr(func, "attr", None) or getattr(func, "id", "")
                if name.startswith(("send", "publish", "arm", "deploy_live")):
                    offenders.append(name)
        assert offenders == []

    def test_prepared_artifacts_are_draft_only(self, tmp_path):
        run = tmp_path / "run"
        run.mkdir()
        ck = ef.prepare_draft_packages(run, _nested("yes"),
                                       skill50_dir=_fake_skill50(tmp_path))
        assert ck["approval"]["status"] == "AWAITING_HUMAN_APPROVAL"
        brief = _brief(run)
        assert brief["status"] == "DRAFT_AWAITING_HUMAN_APPROVAL"
        for p in brief["packages"]:
            assert p["status"] == "DRAFT_AWAITING_HUMAN_APPROVAL"
            assert p["approval"]["status"] == "AWAITING_HUMAN_APPROVAL"


# ---------------------------------------------------------------------------
# Engine-side carriage: defers gate + resolve carry
# ---------------------------------------------------------------------------

class TestEngineCarriage:
    def test_defers_expression_resolves_the_election(self):
        expr = 'intake.want_email_sequences == "yes"'
        assert evaluate_defers_unless(expr, _nested("yes")) is True
        assert evaluate_defers_unless(expr, _nested("no", REASON)) is False
        assert evaluate_defers_unless(expr, {}) is False

    def test_defers_waivers_record_counts_as_no(self):
        intake = {"waivers": [{"rule": "email_sequences",
                               "client_request_quote": REASON}]}
        expr = 'intake.want_email_sequences == "yes"'
        assert evaluate_defers_unless(expr, intake) is False

    def test_resolve_carry_list_includes_the_pair(self):
        assert ("WANT_EMAIL_SEQUENCES", "want_email_sequences") in _UPSELL_FIELDS
        assert ("EMAIL_SEQUENCES_DECLINED_REASON",
                "email_sequences_declined_reason") in _UPSELL_FIELDS

    def test_resolve_carries_the_pair_verbatim_from_the_ledger(self):
        entries = {
            "want_email_sequences": {"value": "no"},
            "email_sequences_declined_reason": {"value": REASON}}
        capture = _resolve_upsell_capture(entries, {})
        assert capture["WANT_EMAIL_SEQUENCES"] == "no"
        assert capture["EMAIL_SEQUENCES_DECLINED_REASON"] == REASON


# ---------------------------------------------------------------------------
# CLI exit codes (intake at the engine's resolved location,
# working/copy/intake.json)
# ---------------------------------------------------------------------------

class TestCli:
    def _run_dir(self, tmp_path: Path, intake: dict) -> Path:
        run = tmp_path / "run"
        copy_dir = run / "working" / "copy"
        copy_dir.mkdir(parents=True)
        (copy_dir / "intake.json").write_text(json.dumps(intake),
                                              encoding="utf-8")
        return run

    def test_cli_elected_prepares_and_exits_zero(self, tmp_path):
        # find_skill50() resolves the real 50-email-engine skill from this
        # repo checkout (it is a repo-root sibling of the department tree).
        run = self._run_dir(tmp_path, _nested("yes"))
        rc = ef.main(["--run-dir", str(run)])
        assert rc == 0
        ck = json.loads((run / ef.CHECKPOINT_REL).read_text(encoding="utf-8"))
        assert ck["outcome"] == "prepared_awaiting_human_approval"
        assert ck["skill50"]["available"] is True

    def test_cli_gate_block_exits_three(self, tmp_path):
        run = self._run_dir(tmp_path, _nested("no"))
        rc = ef.main(["--run-dir", str(run)])
        assert rc == 3
        ck = json.loads((run / ef.CHECKPOINT_REL).read_text(encoding="utf-8"))
        assert ck["outcome"] == "gate_blocked_nothing_prepared"
        assert ef.AF_WAIVER_MISSING in ck["gate"]["detail"]
