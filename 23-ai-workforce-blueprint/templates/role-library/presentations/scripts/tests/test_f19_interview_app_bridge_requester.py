#!/usr/bin/env python3
"""test_f19_interview_app_bridge_requester.py -- FIX F19 pin, interview-app
bridge half.

THE FAULT
----------
intake/interview-app/bridge/intake_bridge.py (the "SUBMIT-TRIGGER" bridge for
the hosted Presentation Interview app) stamped a requester from ONE env var,
PRESENTER_CHAT_ID -- a name found NOWHERE else in this department. Every
other intake path (cc_board.py's _REQUESTER_ENV_KEYS, deck-intake-driver.py's
own mirror of the same tuple) reads PRESENTATION_REQUESTER_CHAT_ID /
ROUTE_PRES_REQUESTER_CHAT_ID / MC_ROUTE_REQUESTER_CHAT_ID. A dispatcher that
exported the canonical names (as it does for the CLI driver) would silently
NOT reach this bridge -- an app-submitted session and a CLI/dispatcher-driven
session disagreed on where the requester lives. That is the exact
divergent-intake-path disease named in FAULT-02/05/11. And, like the CLI
driver, this bridge had no fallback at all for a genuinely operator-run app
session.

THIS FILE PROVES
------------------
  1. The canonical env vars (_REQUESTER_ENV_KEYS) are read FIRST and win --
     the two intake paths now agree.
  2. PRESENTER_CHAT_ID still works as a back-compat alias when none of the
     canonical names are set (an existing deployment's env export keeps
     working).
  3. The canonical names outrank PRESENTER_CHAT_ID when both are present
     (agreement, not just compatibility).
  4. The sanctioned OPERATOR fallback fires when NEITHER is set (via an
     injectable loader -- no real network/module-search dependency needed
     for this unit-level test).
  5. An intake that already carries requester_chat_id is never clobbered.
  6. Nothing resolves anywhere -> requester_chat_id stays absent (never
     fabricated) -- resolve_intake.py's own MissingRequester gate is what
     catches this downstream; this bridge must never paper over it.

Unit-level only: calls intake_bridge.stamp_requester() directly (extracted
by this same fix so it is testable without driving cmd_ingest()'s network
calls -- no HTTP, no cc_board network I/O, no live box, no real
~/.openclaw/openclaw.json touched). Flat file inside tests/, manages its own
import path -- matching every sibling in this directory.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
PRES_DEPT = SCRIPTS.parent
BRIDGE_PATH = PRES_DEPT / "intake" / "interview-app" / "bridge" / "intake_bridge.py"

pytestmark = pytest.mark.skipif(
    not BRIDGE_PATH.is_file(), reason=f"intake_bridge.py not found at {BRIDGE_PATH}")


def _load_bridge():
    spec = importlib.util.spec_from_file_location("f19_intake_bridge_under_test", BRIDGE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ib = _load_bridge()


def _fake_operator_loader(chat_id: str, channel: str = "telegram"):
    """Build a `load_operator_requester` stand-in returning a fake module
    whose resolve_operator_chat_id() returns exactly (chat_id, channel) --
    or (None loader) when chat_id is falsy, mirroring
    _load_operator_requester()'s own 'not found anywhere' contract."""
    if not chat_id:
        return lambda: None

    class _FakeMod:
        @staticmethod
        def resolve_operator_chat_id():
            return (chat_id, channel)

    return lambda: _FakeMod()


class TestCanonicalEnvKeysWin:
    def test_presentation_requester_chat_id_is_stamped(self):
        intake = {}
        ib.stamp_requester(
            intake, env={"PRESENTATION_REQUESTER_CHAT_ID": "REAL-CLIENT-0001"},
            load_operator_requester=_fake_operator_loader(""))
        assert intake["requester_chat_id"] == "REAL-CLIENT-0001"
        assert intake["requester_channel"] == "telegram"

    def test_route_pres_and_mc_route_aliases_also_work(self):
        for key in ("ROUTE_PRES_REQUESTER_CHAT_ID", "MC_ROUTE_REQUESTER_CHAT_ID"):
            intake = {}
            ib.stamp_requester(intake, env={key: "REAL-CLIENT-0002"},
                              load_operator_requester=_fake_operator_loader(""))
            assert intake["requester_chat_id"] == "REAL-CLIENT-0002", f"failed for {key}"


class TestPresenterChatIdBackCompat:
    def test_presenter_chat_id_alone_still_works(self):
        intake = {}
        ib.stamp_requester(intake, env={"PRESENTER_CHAT_ID": "LEGACY-CLIENT-0001"},
                          load_operator_requester=_fake_operator_loader(""))
        assert intake["requester_chat_id"] == "LEGACY-CLIENT-0001"
        assert intake["requester_channel"] == "telegram"

    def test_presenter_channel_alias_honored(self):
        intake = {}
        ib.stamp_requester(intake, env={
            "PRESENTER_CHAT_ID": "LEGACY-CLIENT-0002",
            "PRESENTER_CHANNEL": "sms",
        }, load_operator_requester=_fake_operator_loader(""))
        assert intake["requester_channel"] == "sms"


class TestAgreementCanonicalOutranksBackCompat:
    def test_canonical_wins_when_both_present(self):
        intake = {}
        ib.stamp_requester(intake, env={
            "PRESENTATION_REQUESTER_CHAT_ID": "CANONICAL-WINS",
            "PRESENTER_CHAT_ID": "LEGACY-SHOULD-LOSE",
        }, load_operator_requester=_fake_operator_loader(""))
        assert intake["requester_chat_id"] == "CANONICAL-WINS"


class TestOperatorFallback:
    def test_fires_when_neither_chat_surface_key_present(self):
        intake = {}
        ib.stamp_requester(intake, env={},
                          load_operator_requester=_fake_operator_loader("OPFALLBACK-0001"))
        assert intake["requester_chat_id"] == "OPFALLBACK-0001"
        assert intake["requester_channel"] == "telegram"

    def test_chat_surface_still_wins_over_operator_fallback(self):
        intake = {}
        ib.stamp_requester(intake, env={"PRESENTATION_REQUESTER_CHAT_ID": "REAL-CLIENT"},
                          load_operator_requester=_fake_operator_loader("OPFALLBACK-SHOULD-LOSE"))
        assert intake["requester_chat_id"] == "REAL-CLIENT"


class TestNoClobberAndNoFabrication:
    def test_existing_requester_chat_id_untouched(self):
        intake = {"requester_chat_id": "PRE-EXISTING", "requester_channel": "telegram"}
        ib.stamp_requester(intake, env={"PRESENTATION_REQUESTER_CHAT_ID": "SHOULD-NOT-APPEAR"},
                          load_operator_requester=_fake_operator_loader("SHOULD-NOT-APPEAR-EITHER"))
        assert intake["requester_chat_id"] == "PRE-EXISTING"

    def test_nothing_resolves_leaves_requester_absent(self):
        intake = {}
        ib.stamp_requester(intake, env={}, load_operator_requester=_fake_operator_loader(""))
        assert "requester_chat_id" not in intake, (
            "a genuinely requester-less app session must NOT have a chat_id "
            "invented -- resolve_intake.py's MissingRequester gate is the "
            "correct place for this to fail, loudly, downstream")

    def test_returns_the_same_intake_object(self):
        intake = {}
        out = ib.stamp_requester(intake, env={"PRESENTER_CHAT_ID": "X"},
                                load_operator_requester=_fake_operator_loader(""))
        assert out is intake


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
