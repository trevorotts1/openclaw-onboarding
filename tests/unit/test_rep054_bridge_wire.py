#!/usr/bin/env python3
"""REP-054 / A54: the shipped CLI bridge (shared-utils/decision-engine.py).

The A54 acceptance criterion (spec 1.1 line 1421) requires the released
distribution to include the bridge the spec's own file plan names (line 196:
``shared-utils/decision-engine.py  # NEW CLI bridge``). This suite proves,
against the REAL shipped file and the REAL released policy packs:

  * WIRE (CC byte contract, mirrored from CC contract.ts/bridge.ts/
    capability.ts): --capability answers a non-empty schemaVersion with
    matching major; --evaluate echoes configRevision VERBATIM, returns
    recommendation{roleId,confidence,rationale} + evaluatedAt, and carries
    ZERO forbidden assignment keys anywhere (assignment-read-only).
  * FAIL-CLOSED: bad stdin / bad request major / bad department / no args all
    exit nonzero with a stderr line (never a fabricated response); a box
    missing the canonical core beside the bridge exits 3 on BOTH flags
    (never 'compatible' on a gutted box).
  * DISTRIBUTION: both the fresh-install D27 verify loop (install.sh) and the
    updater D27 guard loop (update-skills.sh) name decision-engine.py inside
    the loop body, so an assembly that drops it is flagged, not silently ok.

Run: pytest tests/unit/test_rep054_bridge_wire.py -q
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO = _HERE.parent.parent
_BRIDGE = _REPO / "shared-utils" / "decision-engine.py"

# Mirrors CC src/lib/decision-engine/contract.ts FORBIDDEN_ASSIGNMENT_KEYS.
FORBIDDEN_ASSIGNMENT_KEYS = (
    "assigned_agent_id",
    "assignedAgentId",
    "assignment",
    "board",
    "task_card",
    "taskCard",
    "dispatch",
    "column",
    "status_transition",
    "statusTransition",
    "persona_pin",
    "personaPin",
)


def _run(bridge: Path, args: list[str], stdin: str | None = None):
    return subprocess.run(
        [sys.executable, str(bridge), *args],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _request(**overrides) -> str:
    req = {
        "schemaVersion": "1.1.0",
        "configRevision": "cfgrev-unit-1",
        "taskId": "task-1",
        "taskDescription": "Can you explain it to me?",
    }
    req.update(overrides)
    return json.dumps(req)


def _assert_no_forbidden_keys(node) -> None:
    if isinstance(node, list):
        for item in node:
            _assert_no_forbidden_keys(item)
    elif isinstance(node, dict):
        for key, value in node.items():
            assert key not in FORBIDDEN_ASSIGNMENT_KEYS, f"forbidden key {key!r}"
            _assert_no_forbidden_keys(value)


class CapabilityProbe(unittest.TestCase):
    def test_capability_answers_compatible_major(self):
        result = _run(_BRIDGE, ["--capability"])
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        version = payload.get("schemaVersion")
        self.assertIsInstance(version, str)
        self.assertTrue(version)  # CC: absent schemaVersion -> handshake_failed
        # CC schemaMajor comparison (contract.ts).
        self.assertEqual(version.split(".")[0], "1")

    def test_capability_fails_closed_without_core(self):
        with tempfile.TemporaryDirectory(prefix="onb-rep054-gutted-") as tmp:
            lone = Path(tmp) / "decision-engine.py"
            shutil.copy2(_BRIDGE, lone)  # bridge alone: no decision_engine/
            result = _run(lone, ["--capability"])
            self.assertEqual(result.returncode, 3, result.stdout)
            self.assertNotIn("schemaVersion", result.stdout)
            self.assertTrue(result.stderr.strip())


class EvaluateWire(unittest.TestCase):
    def test_round_trip_matches_cc_contract(self):
        result = _run(_BRIDGE, ["--evaluate"], _request())
        self.assertEqual(result.returncode, 0, result.stderr)
        response = json.loads(result.stdout)
        self.assertIsInstance(response.get("schemaVersion"), str)
        self.assertTrue(response["schemaVersion"])
        self.assertEqual(response["schemaVersion"].split(".")[0], "1")
        # assertRevisionEcho: value non-empty and identical to the request.
        self.assertEqual(response.get("configRevision"), "cfgrev-unit-1")
        rec = response.get("recommendation")
        self.assertIsInstance(rec, dict)
        self.assertIsInstance(rec.get("roleId"), str)
        self.assertTrue(rec["roleId"])
        self.assertIsInstance(rec.get("confidence"), (int, float))
        self.assertIsInstance(rec.get("rationale"), str)
        self.assertTrue(rec["rationale"].strip())
        self.assertIsInstance(response.get("evaluatedAt"), str)
        # assertAssignmentReadOnly over the parsed payload.
        _assert_no_forbidden_keys(response)

    def test_revision_echo_verbatim_not_normalized(self):
        odd = "  cfgrev  with spaces  "
        result = _run(_BRIDGE, ["--evaluate"],
                      _request(configRevision=odd))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["configRevision"], odd)

    def test_department_present_and_absent_both_valid(self):
        with_dep = _run(_BRIDGE, ["--evaluate"],
                        _request(department="marketing"))
        self.assertEqual(with_dep.returncode, 0, with_dep.stderr)
        _assert_no_forbidden_keys(json.loads(with_dep.stdout))
        without_dep = _run(_BRIDGE, ["--evaluate"], _request())
        self.assertEqual(without_dep.returncode, 0, without_dep.stderr)

    def test_released_fixture_message_yields_truthful_reasons(self):
        result = _run(_BRIDGE, ["--evaluate"],
                      _request(taskDescription="Thanks."))
        self.assertEqual(result.returncode, 0, result.stderr)
        rationale = json.loads(result.stdout)["recommendation"]["rationale"]
        # 'Thanks.' is a released control/question fixture -> answer_only or
        # social_conversation, and either way a REAL pack match is reported.
        self.assertIn("intent match", rationale)

    def test_bad_stdin_exits_2(self):
        result = _run(_BRIDGE, ["--evaluate"], "not json at all")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout.strip(), "")

    def test_wrong_major_request_exits_2(self):
        result = _run(_BRIDGE, ["--evaluate"],
                      _request(schemaVersion="2.0"))
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout.strip(), "")

    def test_missing_task_description_exits_2(self):
        result = _run(_BRIDGE, ["--evaluate"],
                      json.dumps({"schemaVersion": "1.1.0",
                                  "configRevision": "c1"}))
        self.assertEqual(result.returncode, 2)

    def test_argless_usage_exits_2(self):
        result = _run(_BRIDGE, [])
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage", result.stderr)


class ShippedInBothD27Loops(unittest.TestCase):
    def _loop_body(self, path: Path) -> str:
        src = path.read_text(encoding="utf-8")
        start = src.index("for _D27_REL in")
        end = src.index("done", start)
        return src[start:end]

    def test_installer_verify_loop_names_bridge(self):
        body = self._loop_body(_REPO / "install.sh")
        self.assertIn('"decision-engine.py"', body)
        # The loop must still be the D27 recording loop, not a retext.
        self.assertIn('_D27_MISSING="${_D27_MISSING} ${_D27_REL}"',
                      (_REPO / "install.sh").read_text(encoding="utf-8"))

    def test_updater_guard_loop_names_bridge(self):
        body = self._loop_body(_REPO / "update-skills.sh")
        self.assertIn('"decision-engine.py"', body)
        self.assertIn('_D27_CORE_MISSING="${_D27_CORE_MISSING} ${_D27_REL}"',
                      (_REPO / "update-skills.sh").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
