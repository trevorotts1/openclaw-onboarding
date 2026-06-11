#!/usr/bin/env python3
"""
Unit tests for shared-utils/a2_load_assert.py — confidence matrix.

Tests the four loaded_confidence outcomes (HIGH/MEDIUM/UNKNOWN/LOW) by
stubbing the subprocess calls that the A2LoadAssert state machine makes.

Run:
    python3 tests/unit/a2-load-assert.test.py
    or: pytest tests/unit/a2-load-assert.test.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Locate shared-utils (works from any cwd inside the repo)
# ---------------------------------------------------------------------------
_HERE = Path(__file__).parent  # tests/unit/
_REPO_ROOT = _HERE.parent.parent  # repo root
_SHARED_UTILS = _REPO_ROOT / "shared-utils"
assert _SHARED_UTILS.is_dir(), f"shared-utils not found at {_SHARED_UTILS}"

sys.path.insert(0, str(_SHARED_UTILS))

# Dynamic import so this test works even if a2_load_assert.py is NEW
_spec = importlib.util.spec_from_file_location(
    "a2_load_assert", _SHARED_UTILS / "a2_load_assert.py"
)
assert _spec is not None, "Could not load a2_load_assert.py"
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)  # type: ignore
A2LoadAssert = _mod.A2LoadAssert
_ts_strictly_after = _mod._ts_strictly_after
_CONFIDENCE_EXIT = _mod._CONFIDENCE_EXIT


# ---------------------------------------------------------------------------
# Helper: make a stub sessions.json in a temp directory
# ---------------------------------------------------------------------------
def make_sessions_json(
    tmp: Path,
    session_key: str = "agent:main:telegram:direct:12345",
    session_id: str = "sess-initial",
    started_at: str = "1000000",
) -> Path:
    sessions_dir = tmp / "agents" / "main" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    p = sessions_dir / "sessions.json"
    p.write_text(json.dumps({
        session_key: {
            "sessionId": session_id,
            "sessionStartedAt": started_at,
            "lastInteractionAt": started_at,
            "updatedAt": started_at,
        }
    }))
    return p


# ---------------------------------------------------------------------------
# Stub builders for subprocess.run
# ---------------------------------------------------------------------------
class StubResult:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def make_run_stub(
    sessions_json_path: Path,
    session_key: str,
    leg_a_pass: bool = True,
    has_model: bool = True,
    canary_echo: bool = True,
    chat_history_available: bool = True,
):
    """
    Returns a stub for subprocess.run that simulates the openclaw CLI
    calls made by A2LoadAssert according to the specified scenario flags.
    """
    reset_count = [0]

    def _stub(cmd, **kwargs):
        args = list(cmd)
        joined = " ".join(args)

        # ── sessions.reset ────────────────────────────────────────────────────
        if "sessions.reset" in joined:
            reset_count[0] += 1
            if leg_a_pass:
                # Simulate: write a new sessionId into the sessions.json
                new_id = f"sess-reset-{reset_count[0]}-{int(time.time())}"
                new_ts = str(int(time.time()) + reset_count[0] * 10)
                data = json.loads(sessions_json_path.read_text())
                data[session_key]["sessionId"] = new_id
                data[session_key]["sessionStartedAt"] = new_ts
                sessions_json_path.write_text(json.dumps(data))
            return StubResult(stdout='{"ok":true}')

        # ── Model detection (chat.history with limit:1) ───────────────────────
        if "chat.history" in joined:
            if not has_model:
                return StubResult(stdout='{"error":"no model configured"}')
            if not chat_history_available:
                return StubResult(
                    stdout='{"error":"unknown method"}',
                    returncode=1
                )
            if canary_echo:
                canary = ""
                workspace = sessions_json_path.parent.parent.parent.parent / "workspace"
                soul = workspace / "SOUL.md"
                if soul.exists():
                    import re as _re
                    m = _re.search(r"A2CANARY[A-Za-z0-9]+", soul.read_text())
                    if m:
                        canary = m.group()
                if canary:
                    msgs = [
                        {"id": "msg-2", "role": "assistant",
                         "content": f"The load-check token is {canary}"},
                        {"id": "msg-1", "role": "user",
                         "content": "load-check: reply with the load-check token"},
                    ]
                    return StubResult(stdout=json.dumps(msgs))
            return StubResult(stdout="[]")

        # ── message send (probe) ──────────────────────────────────────────────
        if "message" in args and "send" in args:
            return StubResult(stdout="")

        return StubResult(stdout="", returncode=0)

    return _stub


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------
class TestConfidenceMatrix(unittest.TestCase):

    def _run(self, tmp: Path, session_key: str = "agent:main:telegram:direct:12345",
             **kwargs) -> dict:
        """Build an A2LoadAssert, stub subprocess.run + shutil.which, run."""
        sessions_path = make_sessions_json(tmp, session_key=session_key)
        workspace = tmp / "workspace"
        workspace.mkdir(exist_ok=True)
        (workspace / "SOUL.md").write_text("# SOUL\n")

        stub_fn = make_run_stub(
            sessions_json_path=sessions_path,
            session_key=session_key,
            **kwargs,
        )

        asserter = A2LoadAssert(
            box="unit-test",
            session_key=session_key,
            ceo_chat_id="12345",
            sessions_json=str(sessions_path),
            workspace=str(workspace),
            probe_timeout=5,
            poll_interval=0,
        )

        with patch("subprocess.run", side_effect=stub_fn), \
             patch("shutil.which", return_value="/usr/bin/openclaw"):
            return asserter.run()

    def test_high_both_legs_pass(self):
        """HIGH: LEG A (new sessionId) AND LEG B (canary echoed)."""
        with tempfile.TemporaryDirectory() as td:
            result = self._run(
                Path(td),
                leg_a_pass=True,
                has_model=True,
                canary_echo=True,
                chat_history_available=True,
            )
        self.assertEqual(result["loaded_confidence"], "HIGH")
        self.assertTrue(result["present"])
        self.assertTrue(result["leg_a"]["passed"])
        self.assertTrue(result["leg_b"]["passed"])
        self.assertEqual(_CONFIDENCE_EXIT["HIGH"], 0)

    def test_low_leg_a_fails(self):
        """LOW/FAIL: sessionId does not change after reset."""
        with tempfile.TemporaryDirectory() as td:
            result = self._run(
                Path(td),
                leg_a_pass=False,
                has_model=True,
                canary_echo=False,
                chat_history_available=True,
            )
        self.assertEqual(result["loaded_confidence"], "LOW")
        self.assertFalse(result["present"])
        self.assertFalse(result["leg_a"]["passed"])
        self.assertEqual(_CONFIDENCE_EXIT["LOW"], 2)

    def test_unknown_no_model(self):
        """UNKNOWN: no live model; LEG B must not run; no key borrowing."""
        with tempfile.TemporaryDirectory() as td:
            result = self._run(
                Path(td),
                leg_a_pass=True,
                has_model=False,
                canary_echo=False,
                chat_history_available=True,
            )
        self.assertEqual(result["loaded_confidence"], "UNKNOWN")
        self.assertFalse(result["present"])
        self.assertTrue(result["leg_a"]["passed"])   # LEG A still ran
        self.assertFalse(result["leg_b"]["passed"])  # LEG B skipped
        # loaded_confidence=UNKNOWN must exit 0 (not an alert condition)
        self.assertEqual(_CONFIDENCE_EXIT["UNKNOWN"], 0)

    def test_medium_leg_b_unavailable(self):
        """MEDIUM: LEG A passes, chat.history RPC not available (non-model)."""
        with tempfile.TemporaryDirectory() as td:
            result = self._run(
                Path(td),
                leg_a_pass=True,
                has_model=True,
                canary_echo=False,
                chat_history_available=False,
            )
        self.assertEqual(result["loaded_confidence"], "MEDIUM")
        self.assertTrue(result["present"])
        self.assertTrue(result["leg_a"]["passed"])
        self.assertFalse(result["leg_b"]["passed"])
        self.assertEqual(_CONFIDENCE_EXIT["MEDIUM"], 0)

    def test_ts_strictly_after(self):
        """_ts_strictly_after helper handles int-as-string and ISO timestamps."""
        self.assertTrue(_ts_strictly_after("1000001", "1000000"))
        self.assertFalse(_ts_strictly_after("1000000", "1000000"))
        self.assertFalse(_ts_strictly_after("999999", "1000000"))
        self.assertFalse(_ts_strictly_after(None, "1000000"))
        self.assertFalse(_ts_strictly_after("1000001", None))
        self.assertTrue(_ts_strictly_after("2026-06-11T12:00:01Z", "2026-06-11T12:00:00Z"))

    def test_no_ceo_chat_id_is_medium(self):
        """MEDIUM when ceo_chat_id is absent (probe has no target)."""
        with tempfile.TemporaryDirectory() as td:
            sk = "agent:main:telegram:direct:12345"
            sessions_path = make_sessions_json(Path(td), session_key=sk)
            workspace = Path(td) / "workspace"
            workspace.mkdir()
            (workspace / "SOUL.md").write_text("# SOUL\n")

            stub_fn = make_run_stub(
                sessions_json_path=sessions_path,
                session_key=sk,
                leg_a_pass=True,
                has_model=True,
                canary_echo=False,
                chat_history_available=True,
            )
            asserter = A2LoadAssert(
                box="unit-test",
                session_key=sk,
                ceo_chat_id=None,  # <-- no target
                sessions_json=str(sessions_path),
                workspace=str(workspace),
                probe_timeout=5,
                poll_interval=0,
            )
            with patch("subprocess.run", side_effect=stub_fn), \
                 patch("shutil.which", return_value="/usr/bin/openclaw"):
                result = asserter.run()

        self.assertEqual(result["loaded_confidence"], "MEDIUM")
        self.assertTrue(result["present"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
