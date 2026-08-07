"""Tests for the defers_unless gating evaluator (presentation_job/defers.py).

DESIGN-OPUS.md §4.2 — the 16 optional P-U-* phases carry a ``defers_unless``
gate on the intake answers (Q1 want_sales_checkout, Q2 want_vsl_page).  A gate
that evaluates false DEFERS the phase for that run.  Deck-only runs (Q1=no,
Q2=no) defer all 16 P-U phases — executing the identical manifest as today.

These tests pin the resolver (pre_presentation_capture.* storeTarget, waivers[]
decline records, top-level fallback, defaults) and the fail-closed security
behaviour of the evaluator (never eval()s manifest text).
"""

import json
import sys
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

from presentation_job.defers import (  # noqa: E402
    evaluate_defers_unless,
    phase_is_deferred,
    load_intake,
    resolve_intake_value,
)

# Manifest expressions (verbatim from universal-sops/.../PIPELINE-MANIFEST.json).
G_SALES = 'intake.want_sales_checkout == "yes"'
G_VSL = 'intake.want_vsl_page == "yes"'
G_EITHER = 'intake.want_sales_checkout == "yes" or intake.want_vsl_page == "yes"'


class TestResolver:
    def test_resolves_pre_presentation_capture_storeTarget(self):
        intake = {"pre_presentation_capture": {"WANT_SALES_CHECKOUT": "yes"}}
        assert resolve_intake_value(intake, "want_sales_checkout") == "yes"

    def test_resolves_vsl_storeTarget(self):
        intake = {"pre_presentation_capture": {"WANT_VSL_PAGE": "no"}}
        assert resolve_intake_value(intake, "want_vsl_page") == "no"

    def test_top_level_fallback(self):
        intake = {"want_sales_checkout": "yes"}
        assert resolve_intake_value(intake, "want_sales_checkout") == "yes"

    def test_waiver_record_is_a_decline(self):
        intake = {"waivers": [{"rule": "sales_checkout", "client_request_quote": "no thanks"}]}
        assert resolve_intake_value(intake, "want_sales_checkout") == "no"

    def test_bare_no_accepted_as_decline(self):
        """Regression for intake-no-length-hazard: a 2-char "no" stored under the
        pre_presentation_capture key for want_vsl_page is accepted and recorded as
        a decline. The intake driver's validate_answer() used to reject any text
        kind answer shorter than 3 characters, so a client typing "no" to a yes/no
        upsell question could not submit. The fix widens the floor for yes/no
        answers regardless of the question kind."""
        intake = {"pre_presentation_capture": {"WANT_VSL_PAGE": "no"}}
        assert resolve_intake_value(intake, "want_vsl_page") == "no"
        # Confirm the evaluator sees this as a decline.
        assert evaluate_defers_unless('intake.want_vsl_page == "yes"', intake) is False

    def test_bare_yes_accepted(self):
        """Bare "yes" (3 chars, so it skirted the old floor) also resolves correctly
        for want_sales_checkout."""
        intake = {"pre_presentation_capture": {"WANT_SALES_CHECKOUT": "yes"}}
        assert resolve_intake_value(intake, "want_sales_checkout") == "yes"
        assert evaluate_defers_unless('intake.want_sales_checkout == "yes"', intake) is True

    def test_defaults(self):
        # want_sales_checkout defaults to yes; want_vsl_page defaults to no.
        assert resolve_intake_value({}, "want_sales_checkout") == "yes"
        assert resolve_intake_value({}, "want_vsl_page") == "no"


class TestEvaluator:
    def test_deck_only_defers_all_gates(self):
        intake = {"pre_presentation_capture": {"WANT_SALES_CHECKOUT": "no", "WANT_VSL_PAGE": "no"}}
        assert evaluate_defers_unless(G_SALES, intake) is False
        assert evaluate_defers_unless(G_VSL, intake) is False
        assert evaluate_defers_unless(G_EITHER, intake) is False

    def test_full_upsell_runs_all_gates(self):
        intake = {"pre_presentation_capture": {"WANT_SALES_CHECKOUT": "yes", "WANT_VSL_PAGE": "yes"}}
        assert evaluate_defers_unless(G_SALES, intake) is True
        assert evaluate_defers_unless(G_VSL, intake) is True
        assert evaluate_defers_unless(G_EITHER, intake) is True

    def test_sales_only(self):
        intake = {"pre_presentation_capture": {"WANT_SALES_CHECKOUT": "yes", "WANT_VSL_PAGE": "no"}}
        assert evaluate_defers_unless(G_SALES, intake) is True
        assert evaluate_defers_unless(G_VSL, intake) is False
        assert evaluate_defers_unless(G_EITHER, intake) is True

    def test_no_gate_runs(self):
        assert evaluate_defers_unless(None, {}) is True
        assert evaluate_defers_unless("", {}) is True

    def test_waiver_declines(self):
        intake = {"waivers": [{"rule": "sales_checkout", "client_request_quote": "skip it"}]}
        assert evaluate_defers_unless(G_SALES, intake) is False

    def test_malformed_expression_fails_closed(self):
        assert evaluate_defers_unless("not a real expr", {}) is False
        assert evaluate_defers_unless(12345, {}) is False

    def test_injection_never_executes(self):
        assert evaluate_defers_unless('__import__("os").system("true")', {}) is False
        assert evaluate_defers_unless(
            'intake.want_sales_checkout == "yes" or __import__("os")', {}) is False


class TestPhaseIsDeferred:
    def test_phase_dict_deferred(self):
        phase = {"id": "P-U-SALES-COPY", "defers_unless": G_SALES}
        intake = {"pre_presentation_capture": {"WANT_SALES_CHECKOUT": "no"}}
        assert phase_is_deferred(phase, intake) is True

    def test_phase_dict_not_deferred(self):
        phase = {"id": "P-U-SALES-COPY", "defers_unless": G_SALES}
        intake = {"pre_presentation_capture": {"WANT_SALES_CHECKOUT": "yes"}}
        assert phase_is_deferred(phase, intake) is False

    def test_phase_without_gate_not_deferred(self):
        assert phase_is_deferred({"id": "P4-COPY"}, {}) is False


class TestLoadIntake:
    def test_loads_intake_json(self, tmp_path):
        run_dir = tmp_path / "run"
        (run_dir / "working" / "copy").mkdir(parents=True)
        (run_dir / "working" / "copy" / "intake.json").write_text(
            json.dumps({"pre_presentation_capture": {"WANT_SALES_CHECKOUT": "no"}}))
        assert load_intake(run_dir)["pre_presentation_capture"]["WANT_SALES_CHECKOUT"] == "no"

    def test_missing_intake_returns_empty(self, tmp_path):
        assert load_intake(tmp_path / "nope") == {}
