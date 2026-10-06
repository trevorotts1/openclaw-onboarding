"""F7 -- render width comes from the GOVERNOR, never from a hardcoded constant.

Broken (pristine main, ``build_deck.py`` ~line 420)::

    # Overridable via BUILD_DECK_RENDER_WORKERS (clamped to [1, 12]).
    def _render_workers() -> int:
        try:
            n = int(os.environ.get("BUILD_DECK_RENDER_WORKERS", "6"))
        except ValueError:
            n = 6
        return max(1, min(12, n))

Three defects in five lines:

1. The default is the literal ``6``. It never asks the governor what this
   account is actually entitled to, so a box provisioned for 100 concurrent
   KIE tasks still renders six wide.
2. The clamp ceiling is 12. Even an operator who KNOWS the entitlement
   cannot open the fan-out past 12 -- a 100-slide signature deck is 17
   rounds at 6 and still 9 rounds at 12.
3. ``BUILD_DECK_RENDER_WORKERS`` overrides in BOTH directions: it can widen
   the fan-out past what the governor allows, which is precisely the knob
   that gets a client's KIE account rate-limited.

Fixed: the width is ``min(governor kie max_inflight, slide_count)``, the
clamp ceiling is ``RENDER_WORKERS_CEILING`` (100), and the env var is a
SELF-THROTTLE ONLY -- ``min(env, governed)`` -- so an operator can narrow the
fan-out and can never widen it past the governor.

REALITY NOTE (verified while implementing F7; NOT something this file
proves): ``_render_workers`` has ZERO call sites in this repo. The
ThreadPoolExecutor fan-out its comment describes was replaced by the
batch-submit path, which already gates on ``_gov_max_inflight()``
(build_deck.py, the ``_kie_max_inflight`` gate in ``render_slides_batch``).
These tests pin the SYMBOL's contract so the hardcoded constant cannot come
back, and so the symbol is already correct on the day it is wired in.

Flat file inside ``tests/``, manages its own import path -- matching every
sibling in this directory (see test_poll_cap.py).
"""

import sys
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

import build_deck as bd  # noqa: E402


class _FakeGovernor:
    """Minimal stand-in for presentation_job.governor: the only surface
    ``_gov_max_inflight()`` touches is ``provider_config(provider)``."""

    def __init__(self, max_inflight):
        self.max_inflight = max_inflight
        self.asked_for = []

    def provider_config(self, provider):
        self.asked_for.append(provider)
        return {"max_inflight": self.max_inflight}


@pytest.fixture(autouse=True)
def _no_ambient_env(monkeypatch):
    """The ambient environment must never decide a test's answer."""
    monkeypatch.delenv("BUILD_DECK_RENDER_WORKERS", raising=False)


# ---------------------------------------------------------------------------
# CONTROL -- prove the instrument (the fake governor) is actually read.
# Without this, a governed-value assertion could pass for the wrong reason.
# ---------------------------------------------------------------------------
class TestControl:
    def test_fake_governor_is_the_source_of_max_inflight(self, monkeypatch):
        gov = _FakeGovernor(37)  # a value that is neither 6, 12, nor 100
        monkeypatch.setattr(bd, "_governor", gov)
        assert bd._gov_max_inflight() == 37
        assert gov.asked_for == ["kie"], (
            "control failed: _gov_max_inflight did not consult the governor for "
            "the kie provider -- every other assertion in this file is void"
        )

    def test_absent_governor_reports_the_documented_ceiling(self, monkeypatch):
        monkeypatch.setattr(bd, "_governor", None)
        assert bd._gov_max_inflight() == 100


# ---------------------------------------------------------------------------
# F7.1 -- the width is the governor's entitlement, not a constant
# ---------------------------------------------------------------------------
class TestWidthComesFromTheGovernor:
    def test_full_entitlement_is_used_when_the_deck_is_big_enough(self, monkeypatch):
        """100 concurrent tasks entitled, 100 slides -> 100 workers.

        Pristine main returns 6: one round of a signature deck becomes 17."""
        monkeypatch.setattr(bd, "_governor", _FakeGovernor(100))
        assert bd._render_workers(100) == 100

    def test_width_tracks_a_narrower_entitlement(self, monkeypatch):
        """A throttled account (max_inflight 8) renders 8 wide -- not 6, not 12.
        The number has to MOVE with the governor."""
        monkeypatch.setattr(bd, "_governor", _FakeGovernor(8))
        assert bd._render_workers(40) == 8

    def test_no_slide_count_still_uses_the_governor_not_six(self, monkeypatch):
        """Called without a slide count the width is the raw entitlement.
        Pristine main returns 6 here regardless of what the box is allowed."""
        monkeypatch.setattr(bd, "_governor", _FakeGovernor(100))
        assert bd._render_workers() == 100

    def test_ceiling_is_100_not_12(self):
        assert bd.RENDER_WORKERS_CEILING == 100

    def test_absent_governor_falls_back_to_12_not_6(self, monkeypatch):
        """A legacy checkout without governor.py self-throttles at 12 (the
        documented fail-soft default) -- never at the old hardcoded 6."""
        monkeypatch.setattr(bd, "_governor", None)
        assert bd.RENDER_WORKERS_NO_GOVERNOR_DEFAULT == 12
        assert bd._render_workers(40) == 12

    def test_governor_config_of_zero_still_floors_at_one(self, monkeypatch):
        """_gov_max_inflight already floors at 1; the width must inherit that
        floor rather than hand back a pool that can run nothing."""
        monkeypatch.setattr(bd, "_governor", _FakeGovernor(0))
        assert bd._render_workers(40) == 1


# ---------------------------------------------------------------------------
# F7.2 -- the deck never gets more workers than it has slides
# ---------------------------------------------------------------------------
class TestSlideCountClamp:
    def test_small_deck_does_not_overallocate(self, monkeypatch):
        monkeypatch.setattr(bd, "_governor", _FakeGovernor(100))
        assert bd._render_workers(5) == 5

    def test_zero_and_negative_slide_counts_floor_at_one(self, monkeypatch):
        monkeypatch.setattr(bd, "_governor", _FakeGovernor(100))
        assert bd._render_workers(0) == 1
        assert bd._render_workers(-3) == 1

    def test_unparseable_slide_count_is_ignored_not_fatal(self, monkeypatch):
        monkeypatch.setattr(bd, "_governor", _FakeGovernor(100))
        assert bd._render_workers("not-a-number") == 100


# ---------------------------------------------------------------------------
# F7.3 -- BUILD_DECK_RENDER_WORKERS is a self-throttle, never a widener
# ---------------------------------------------------------------------------
class TestEnvIsSelfThrottleOnly:
    def test_env_can_narrow_the_fan_out(self, monkeypatch):
        monkeypatch.setattr(bd, "_governor", _FakeGovernor(100))
        monkeypatch.setenv("BUILD_DECK_RENDER_WORKERS", "3")
        assert bd._render_workers(40) == 3

    def test_env_cannot_widen_past_the_governor(self, monkeypatch):
        """The account allows 8. An operator asking for 50 still gets 8 -- on
        pristine main the same request is granted 12, i.e. the env var widens
        the fan-out 4 past the entitlement the governor published."""
        monkeypatch.setattr(bd, "_governor", _FakeGovernor(8))
        monkeypatch.setenv("BUILD_DECK_RENDER_WORKERS", "50")
        assert bd._render_workers(40) == 8

    def test_env_cannot_widen_past_the_slide_count(self, monkeypatch):
        monkeypatch.setattr(bd, "_governor", _FakeGovernor(100))
        monkeypatch.setenv("BUILD_DECK_RENDER_WORKERS", "64")
        assert bd._render_workers(9) == 9

    def test_garbage_env_is_ignored_not_fatal(self, monkeypatch):
        monkeypatch.setattr(bd, "_governor", _FakeGovernor(100))
        monkeypatch.setenv("BUILD_DECK_RENDER_WORKERS", "wide-open")
        assert bd._render_workers(40) == 40

    def test_env_zero_still_floors_at_one(self, monkeypatch):
        monkeypatch.setattr(bd, "_governor", _FakeGovernor(100))
        monkeypatch.setenv("BUILD_DECK_RENDER_WORKERS", "0")
        assert bd._render_workers(40) == 1


# ---------------------------------------------------------------------------
# F7.4 -- the constant cannot come back
# ---------------------------------------------------------------------------
class TestNoHardcodedDefault:
    def test_source_has_no_literal_six_default_and_no_twelve_clamp(self):
        """Read the shipped source: the two literals that ARE the defect -- the
        "6" env default and the min(12, n) clamp -- must both be gone."""
        src = (_scripts_dir / "build_deck.py").read_text(encoding="utf-8")
        assert 'os.environ.get("BUILD_DECK_RENDER_WORKERS", "6")' not in src
        assert "return max(1, min(12, n))" not in src
        # Control: the symbol under test really is in the file just read, so the
        # two assertions above cannot be passing off an empty read as a result.
        assert "def _render_workers(" in src
