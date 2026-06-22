"""Goal-B defect tests — ghl_builder.subaccount_matches / MatchGuard.

Covers:
  - Exact-ID match: PASS and correct fields populated
  - Substring / short / generic rejection: ok=False
  - MatchGuard boolean protocol: bool(guard) tracks guard.ok
  - Empty current / empty target edge cases

No network, no filesystem side effects.
"""
from __future__ import annotations

import sys
import os

# Ensure ghl_builder is importable regardless of working directory.
_TOOLS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "tools")
)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import pytest
from ghl_builder import subaccount_matches, MatchGuard, _LOCATION_ID_MIN_LEN


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# A fabricated 20-char GHL-shaped location ID (alphanumeric, correct length — NOT a real client id).
REAL_ID = "Ab1Cd2Ef3Gh4Ij5Kl6Mn"
# A second distinct fabricated id for mismatch tests (NOT a real client id).
OTHER_ID = "Zy9Xw8Vu7Ts6Rq5Po4Nm"


# ---------------------------------------------------------------------------
# Exact-ID match — PASS cases
# ---------------------------------------------------------------------------

class TestExactIDMatch:
    """Exact normalised match must produce ok=True with both ID fields set."""

    def test_identical_ids_pass(self):
        guard = subaccount_matches(REAL_ID, REAL_ID)
        assert guard.ok is True

    def test_identical_ids_bool_true(self):
        guard = subaccount_matches(REAL_ID, REAL_ID)
        assert bool(guard) is True

    def test_match_populates_target_id(self):
        guard = subaccount_matches(REAL_ID, REAL_ID)
        assert guard.target_id == REAL_ID.lower()

    def test_match_populates_matched(self):
        guard = subaccount_matches(REAL_ID, REAL_ID)
        assert guard.matched == REAL_ID.lower()

    def test_match_reason_contains_pass(self):
        guard = subaccount_matches(REAL_ID, REAL_ID)
        assert "PASS" in guard.reason

    def test_case_normalisation_passes(self):
        """Mixed-case IDs normalise to the same value and match."""
        guard = subaccount_matches(REAL_ID.upper(), REAL_ID.lower())
        assert guard.ok is True

    def test_whitespace_around_id_normalised(self):
        guard = subaccount_matches(f"  {REAL_ID}  ", REAL_ID)
        assert guard.ok is True

    def test_getitem_interface_ok_field(self):
        """MatchGuard supports dict-like guard['ok'] access."""
        guard = subaccount_matches(REAL_ID, REAL_ID)
        assert guard["ok"] is True

    def test_as_dict_is_serialisable(self):
        guard = subaccount_matches(REAL_ID, REAL_ID)
        d = guard.as_dict()
        assert isinstance(d, dict)
        assert d["ok"] is True
        assert "reason" in d


# ---------------------------------------------------------------------------
# Mismatch — two valid-length IDs that differ
# ---------------------------------------------------------------------------

class TestMismatch:
    """When current != target (after normalisation) the guard must be FAIL."""

    def test_different_real_ids_reject(self):
        guard = subaccount_matches(OTHER_ID, REAL_ID)
        assert guard.ok is False

    def test_mismatch_bool_false(self):
        guard = subaccount_matches(OTHER_ID, REAL_ID)
        assert bool(guard) is False

    def test_mismatch_reason_contains_mismatch(self):
        guard = subaccount_matches(OTHER_ID, REAL_ID)
        assert "MISMATCH" in guard.reason

    def test_mismatch_target_id_is_target(self):
        guard = subaccount_matches(OTHER_ID, REAL_ID)
        assert guard.target_id == REAL_ID.lower()

    def test_mismatch_matched_is_current(self):
        guard = subaccount_matches(OTHER_ID, REAL_ID)
        assert guard.matched == OTHER_ID.lower()


# ---------------------------------------------------------------------------
# Short / fragment targets are rejected
# ---------------------------------------------------------------------------

class TestShortTargetRejection:
    """Targets shorter than _LOCATION_ID_MIN_LEN must be rejected."""

    def test_single_char_target_rejected(self):
        guard = subaccount_matches(REAL_ID, "x")
        assert guard.ok is False

    def test_too_short_target_bool_false(self):
        guard = subaccount_matches(REAL_ID, "abc")
        assert bool(guard) is False

    def test_too_short_reason_mentions_short(self):
        guard = subaccount_matches(REAL_ID, "abc")
        assert "short" in guard.reason.lower() or "minimum" in guard.reason.lower()

    def test_exactly_min_minus_one_rejected(self):
        short = "a" * (_LOCATION_ID_MIN_LEN - 1)
        guard = subaccount_matches(REAL_ID, short)
        assert guard.ok is False

    def test_exactly_min_len_accepted_when_matching(self):
        """A target exactly at the minimum length is accepted when IDs match."""
        at_min = "a" * _LOCATION_ID_MIN_LEN
        guard = subaccount_matches(at_min, at_min)
        # The IDs are equal but we do not know if they are in _GENERIC_TARGETS.
        # 'aaaaaaaa' is not in the generic list, so this should pass.
        assert guard.ok is True


# ---------------------------------------------------------------------------
# Generic / placeholder targets are rejected
# ---------------------------------------------------------------------------

class TestGenericTargetRejection:
    """Known placeholder strings must never be accepted as a real location ID."""

    @pytest.mark.parametrize("placeholder", [
        "test", "demo", "example", "placeholder",
        "unknown", "none", "null", "undefined",
        "default", "account", "client", "location",
    ])
    def test_generic_placeholder_rejected(self, placeholder):
        guard = subaccount_matches(REAL_ID, placeholder)
        assert guard.ok is False, (
            f"Placeholder {placeholder!r} must be REJECTED — it is not a real location_id"
        )

    @pytest.mark.parametrize("placeholder", [
        "test", "demo", "example",
    ])
    def test_generic_placeholder_bool_false(self, placeholder):
        guard = subaccount_matches(REAL_ID, placeholder)
        assert bool(guard) is False

    @pytest.mark.parametrize("placeholder", [
        "TEST", "DEMO", "EXAMPLE",
    ])
    def test_generic_placeholder_case_insensitive(self, placeholder):
        """Generic detection is case-insensitive."""
        guard = subaccount_matches(REAL_ID, placeholder)
        assert guard.ok is False


# ---------------------------------------------------------------------------
# Empty inputs
# ---------------------------------------------------------------------------

class TestEmptyInputs:
    """Empty current or target must produce ok=False immediately."""

    def test_empty_current_rejected(self):
        guard = subaccount_matches("", REAL_ID)
        assert guard.ok is False

    def test_empty_target_rejected(self):
        guard = subaccount_matches(REAL_ID, "")
        assert guard.ok is False

    def test_both_empty_rejected(self):
        guard = subaccount_matches("", "")
        assert guard.ok is False

    def test_empty_current_reason_mentions_empty(self):
        guard = subaccount_matches("", REAL_ID)
        assert "empty" in guard.reason.lower()

    def test_empty_target_reason_mentions_empty(self):
        guard = subaccount_matches(REAL_ID, "")
        assert "empty" in guard.reason.lower()


# ---------------------------------------------------------------------------
# MatchGuard object protocol
# ---------------------------------------------------------------------------

class TestMatchGuardProtocol:
    """MatchGuard must behave as a bool while also exposing structured fields."""

    def test_ok_true_guard_is_truthy(self):
        g = MatchGuard(ok=True, reason="PASS", target_id="abc", matched="abc")
        assert bool(g) is True

    def test_ok_false_guard_is_falsy(self):
        g = MatchGuard(ok=False, reason="REJECT", target_id="abc")
        assert bool(g) is False

    def test_slots_prevent_extra_attrs(self):
        g = MatchGuard(ok=True, reason="PASS")
        with pytest.raises(AttributeError):
            g.nonexistent_field = "bad"  # type: ignore[attr-defined]

    def test_repr_contains_ok_and_reason(self):
        g = MatchGuard(ok=False, reason="MISMATCH something")
        r = repr(g)
        assert "ok=False" in r
        assert "MISMATCH" in r

    def test_as_dict_contains_all_four_fields(self):
        g = MatchGuard(ok=True, reason="PASS: exact", target_id="aaa", matched="aaa")
        d = g.as_dict()
        assert set(d.keys()) >= {"ok", "reason", "target_id", "matched"}

    def test_getitem_reason(self):
        g = MatchGuard(ok=False, reason="REJECT: short")
        assert g["reason"] == "REJECT: short"

    def test_getitem_target_id(self):
        g = MatchGuard(ok=True, reason="PASS", target_id="xyz123ab", matched="xyz123ab")
        assert g["target_id"] == "xyz123ab"

    def test_if_guard_pattern_works(self):
        """Existing callers using `if subaccount_matches(...):` remain correct."""
        real_guard = subaccount_matches(REAL_ID, REAL_ID)
        called = False
        if real_guard:
            called = True
        assert called is True

    def test_not_guard_pattern_works(self):
        fake_guard = subaccount_matches(OTHER_ID, REAL_ID)
        blocked = False
        if not fake_guard:
            blocked = True
        assert blocked is True
