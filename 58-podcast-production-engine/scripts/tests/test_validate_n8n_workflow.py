#!/usr/bin/env python3
# =============================================================================
# SKILL 58 - PODCAST PRODUCTION ENGINE :: n8n workflow schema validation (U041)
# -----------------------------------------------------------------------------
# Stdlib unittest only. No network: the validator core is a pure function driven
# with hand-built workflow fixtures, plus a subprocess CLI check against the REAL
# committed workflow JSON. Proves F41: a corrupted or schema-violating workflow
# (missing nodes / connections / version marker, bad JSON, incompatible n8n
# schema version) is REJECTED before import, while a valid versioned workflow
# passes.
# Run:  python3 -m unittest 58-podcast-production-engine/scripts/tests/test_validate_n8n_workflow.py
# =============================================================================
"""Deterministic tests for the n8n workflow schema validator (U041 / F41)."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_SCRIPT = _HERE.parent.parent / "validate_n8n_workflow.py"
# config/ lives at the skill root (58-podcast-production-engine/config/), one
# level above scripts/ — not under scripts/.
_WORKFLOW = _SCRIPT.parent.parent / "config" / "n8n" / "podbean-publish.workflow.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("validate_n8n_workflow", str(_SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    # Register BEFORE exec: Python 3.14's dataclass machinery resolves the
    # defining module via sys.modules during class creation.
    sys.modules["validate_n8n_workflow"] = mod
    spec.loader.exec_module(mod)
    return mod


VW = _load_module()


def _workflow(**overrides) -> str:
    """A minimal valid versioned workflow, with optional field overrides/removals."""
    wf = {
        "meta": {"version": "1.0.0", "minN8nSchemaVersion": "1.0"},
        "name": "test workflow",
        "nodes": [{"id": "n1", "type": "n8n-nodes-base.start"}],
        "connections": {"n1": {"main": [[]]}},
    }
    for k, v in overrides.items():
        if v is _REMOVE:
            wf.pop(k, None)
        else:
            wf[k] = v
    return json.dumps(wf)


_REMOVE = object()  # sentinel: delete this field from the fixture


class ValidateWorkflowUnitTests(unittest.TestCase):
    # -- required test 3: a valid workflow passes ---------------------------
    def test_valid_workflow_passes(self):
        r = VW.validate_workflow(_workflow())
        self.assertTrue(r.ok, r.problems)
        self.assertEqual(r.version, "1.0.0")
        self.assertEqual(r.node_count, 1)

    # -- required test 2: removing a required field fails -------------------
    def test_missing_nodes_fails(self):
        r = VW.validate_workflow(_workflow(nodes=_REMOVE))
        self.assertFalse(r.ok)
        self.assertTrue(any("nodes" in p for p in r.problems))

    def test_missing_connections_fails(self):
        r = VW.validate_workflow(_workflow(connections=_REMOVE))
        self.assertFalse(r.ok)
        self.assertTrue(any("connections" in p for p in r.problems))

    def test_missing_version_marker_fails(self):
        r = VW.validate_workflow(_workflow(meta=_REMOVE))
        self.assertFalse(r.ok)
        self.assertTrue(any("meta" in p for p in r.problems))

    def test_empty_version_string_fails(self):
        r = VW.validate_workflow(_workflow(meta={"version": "  "}))
        self.assertFalse(r.ok)
        self.assertTrue(any("meta.version" in p for p in r.problems))

    def test_empty_nodes_list_fails(self):
        r = VW.validate_workflow(_workflow(nodes=[]))
        self.assertFalse(r.ok)
        self.assertTrue(any("empty" in p for p in r.problems))

    # -- required test 1: JSON parse validation -----------------------------
    def test_corrupted_json_fails(self):
        r = VW.validate_workflow("{ this is not valid json")
        self.assertFalse(r.ok)
        self.assertTrue(any("not valid JSON" in p for p in r.problems))

    def test_non_object_json_fails(self):
        r = VW.validate_workflow("[1, 2, 3]")
        self.assertFalse(r.ok)
        self.assertTrue(any("must be an object" in p for p in r.problems))

    # -- n8n schema-version compatibility -----------------------------------
    def test_incompatible_n8n_version_fails(self):
        # Workflow needs n8n >= 2.0, target is 1.0 → incompatible.
        r = VW.validate_workflow(
            _workflow(meta={"version": "1.0.0", "minN8nSchemaVersion": "2.0"}),
            min_n8n="1.0",
        )
        self.assertFalse(r.ok)
        self.assertTrue(any("incompatible" in p for p in r.problems))

    def test_compatible_n8n_version_passes(self):
        r = VW.validate_workflow(
            _workflow(meta={"version": "1.0.0", "minN8nSchemaVersion": "1.0"}),
            min_n8n="1.0",
        )
        self.assertTrue(r.ok, r.problems)

    def test_higher_target_n8n_passes(self):
        # Workflow needs >= 1.0, target is 1.48 → fine.
        r = VW.validate_workflow(
            _workflow(meta={"version": "1.0.0", "minN8nSchemaVersion": "1.0"}),
            min_n8n="1.48",
        )
        self.assertTrue(r.ok, r.problems)

    # -- multiple problems are all collected --------------------------------
    def test_collects_all_problems(self):
        r = VW.validate_workflow(json.dumps({"name": "bare"}))
        self.assertFalse(r.ok)
        # nodes, connections, AND meta all missing → at least 3 problems.
        self.assertGreaterEqual(len(r.problems), 3)


class ValidateWorkflowRealFileTests(unittest.TestCase):
    """The REAL committed workflow JSON must pass its own validator."""

    def test_real_workflow_is_valid(self):
        text = _WORKFLOW.read_text(encoding="utf-8")
        r = VW.validate_workflow(text)
        self.assertTrue(r.ok, f"committed workflow failed validation: {r.problems}")
        self.assertEqual(r.version, "1.0.0")
        self.assertGreater(r.node_count, 0)

    def test_real_workflow_cli_passes(self):
        r = subprocess.run(
            [sys.executable, str(_SCRIPT), str(_WORKFLOW)],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("VALID", r.stdout)


if __name__ == "__main__":
    unittest.main()
