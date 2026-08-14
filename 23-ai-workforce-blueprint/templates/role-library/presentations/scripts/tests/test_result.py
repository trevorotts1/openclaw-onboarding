"""Tests for the shared CheckResult type (presentation_job/result.py).

This is the type introduced to close Root Cause 2 (every gate/transport
returning exactly two values, so "I could not determine this" has nowhere to
live and silently becomes a pass). These tests cover the type in isolation;
the call-site acceptance tests live beside each converted check
(tests/test_gates.py::TestCanonicalPromptDirProblemsThreeValued,
tests/test_report.py::TestBlockedDedupeNeverSuppressesAnUnconfirmedSend,
tests/test_watchdog.py test 13/13b/13c/13d).
"""
import sys
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

from presentation_job.result import CheckResult


class TestNoTruthiness:
    """The core anti-regression guard: `if result:` must never silently
    resolve UNDETERMINED to a side."""

    @pytest.mark.parametrize("member", list(CheckResult))
    def test_bool_raises_for_every_member(self, member):
        with pytest.raises(TypeError):
            bool(member)

    @pytest.mark.parametrize("member", list(CheckResult))
    def test_if_statement_raises_for_every_member(self, member):
        with pytest.raises(TypeError):
            if member:  # pragma: no cover - the raise happens before the branch
                pass


class TestOkProperty:
    def test_pass_is_ok(self):
        assert CheckResult.PASS.ok is True

    def test_fail_is_not_ok(self):
        assert CheckResult.FAIL.ok is False

    def test_undetermined_is_not_ok(self):
        """UNDETERMINED must never read as ok -- this is the narrow escape
        hatch for gate-shaped callers, and a gate's whole point is refusing
        on UNDETERMINED, not accepting it."""
        assert CheckResult.UNDETERMINED.ok is False


class TestWorstOf:
    def test_empty_is_undetermined_not_pass(self):
        """Zero evidence is not evidence of a pass -- generalizes the
        EXIT_SWEEP_NO_RUNS / EXIT_WATCHDOG_NO_RUNS precedent."""
        assert CheckResult.worst_of([]) is CheckResult.UNDETERMINED

    def test_all_pass_is_pass(self):
        assert CheckResult.worst_of(
            [CheckResult.PASS, CheckResult.PASS, CheckResult.PASS]
        ) is CheckResult.PASS

    def test_any_fail_wins_over_pass_and_undetermined(self):
        assert CheckResult.worst_of(
            [CheckResult.PASS, CheckResult.UNDETERMINED, CheckResult.FAIL]
        ) is CheckResult.FAIL

    def test_undetermined_wins_over_pass_when_no_fail_present(self):
        assert CheckResult.worst_of(
            [CheckResult.PASS, CheckResult.UNDETERMINED, CheckResult.PASS]
        ) is CheckResult.UNDETERMINED

    def test_single_fail(self):
        assert CheckResult.worst_of([CheckResult.FAIL]) is CheckResult.FAIL

    def test_single_undetermined(self):
        assert CheckResult.worst_of([CheckResult.UNDETERMINED]) is CheckResult.UNDETERMINED

    def test_generator_input_consumed_once_still_correct(self):
        """worst_of takes an Iterable, not just a list -- prove a one-shot
        generator still aggregates correctly (no double-iteration bug)."""
        def gen():
            yield CheckResult.PASS
            yield CheckResult.FAIL
        assert CheckResult.worst_of(gen()) is CheckResult.FAIL


class TestIdentityNotEquality:
    """Members compare by identity (`is`), the pattern every converted call
    site uses. Confirms there's no accidental value-equality surprise (e.g.
    CheckResult.PASS == True) that would reopen the collapse this type
    exists to prevent."""

    def test_pass_is_not_equal_to_true(self):
        assert CheckResult.PASS != True  # noqa: E712
        assert CheckResult.FAIL != False  # noqa: E712

    def test_undetermined_is_not_equal_to_none(self):
        assert CheckResult.UNDETERMINED is not None
        assert CheckResult.UNDETERMINED != None  # noqa: E711
