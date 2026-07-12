#!/usr/bin/env python3
"""test_ghl_workflow_builder.py — fail-first proof for the Skill 6 GATED Automations
workflow builder (P3-08 Gap A, step 2 + QC break-it probe #4).

These tests FAIL against the pre-fix tree (ghl_workflow_builder.py did not exist —
the Tier-4 workflow-build path was a documented promise routing to a missing file)
and PASS with the harness in place. They satisfy the P3-08 (e) break-it probe #4:

  "Tier-4 dry-run: with the Firebase token deliberately unset, drive one
   workflow-build through the new gated path ... and quote the built workflow's ID
   (and prove teardown — zero orphan engines after, reaper-clean)."

The harness drives its browser I/O through an injectable gateway, so this probe is
runnable with NO live browser and NO network — the gateway is mocked. The
live-captured selectors remain the operator-box follow-on; the HARNESS (gate
loading, step ordering, id read-back, guaranteed teardown) is proven here.

Run: pytest 06-ghl-install-pages/tests/test_ghl_workflow_builder.py -q
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_TOOLS_DIR = _TESTS_DIR.parent / "tools"
for p in (str(_TOOLS_DIR),):
    if p not in sys.path:
        sys.path.insert(0, p)

import ghl_workflow_builder as wb  # noqa: E402

_MODULE_PATH = _TOOLS_DIR / "ghl_workflow_builder.py"
_GATES_PATH = _TOOLS_DIR / "gates.json"


class MockGateway:
    """Records every managed call; returns a canned builder URL carrying a
    workflow id on the read-back. Stands in for browser_manager.sh's singleton
    session so the whole build path runs with no browser."""

    def __init__(self, workflow_id="WF_probe_9z8y7x", raise_on=None):
        self.calls = []
        self.ensured = 0
        self.torn_down = 0
        self._id = workflow_id
        self._raise_on = raise_on  # verb name to explode on (teardown test)

    def ensure(self):
        self.ensured += 1
        self.calls.append(("ensure",))

    def step(self, verb, *args):
        self.calls.append(("step", verb, args))
        if self._raise_on == verb:
            raise RuntimeError(f"simulated browser failure on {verb}")
        return ""

    def read(self, verb, *args):
        self.calls.append(("read", verb, args))
        return (
            "https://app.gohighlevel.com/v2/location/L9/automation/"
            f"workflows/{self._id}"
        )

    def teardown(self):
        self.torn_down += 1
        self.calls.append(("teardown",))


def _gates():
    return wb.load_automations_gates(str(_GATES_PATH))


def test_module_and_gates_exist():
    # Fail-first anchor: before P3-08 step 2 neither existed and the docs routed
    # Tier-4 workflow-build to a missing ghl_workflow_builder.py.
    assert _MODULE_PATH.exists(), "ghl_workflow_builder.py must exist (P3-08 Gap A)"
    gates = _gates()
    assert gates.required, "gates.json must carry automations_builder_gates.required_steps"


def test_tier4_token_unset_build_through_gated_path_quotes_id_and_tears_down(monkeypatch):
    """QC break-it probe #4: Firebase token UNSET → build through the gated path,
    quote the built workflow id, prove zero-orphan teardown."""
    # Deliberately unset the Firebase token in the environment.
    for var in (
        "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN",
        "GHL_FIREBASE_REFRESH_TOKEN",
    ):
        monkeypatch.delenv(var, raising=False)
    assert os.environ.get("GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN") is None

    gw = MockGateway(workflow_id="WF_probe_9z8y7x")
    builder = wb.WorkflowBuilder(gw, _gates(), location_id="L9")
    spec = wb.WorkflowSpec(name="Tier-4 probe workflow", trigger_type="Contact Created", action_type="Send Email")
    result = builder.build(spec)

    # The built workflow id is read back and QUOTED (probe requirement).
    assert result.workflow_id == "WF_probe_9z8y7x", result.as_dict()
    assert result.tier == "tier-4-gated-managed"

    # Zero orphan engines: teardown ran EXACTLY once (reaper-clean), and the
    # session was ensured exactly once (singleton, not per-step).
    assert gw.ensured == 1
    assert gw.torn_down == 1
    assert result.torn_down is True
    # The very last managed call is teardown — nothing leaked after it.
    assert gw.calls[-1] == ("teardown",)

    # EVERY browser action went through the managed gateway (never bare
    # agent-browser): the recorded verbs are only manager verbs.
    verbs = {c[1] for c in gw.calls if c[0] in ("step", "read")}
    assert verbs <= {"open", "find", "fill", "eval"}, verbs


def test_teardown_runs_even_when_build_raises_midway():
    """Zero-orphan guarantee holds on failure too: a mid-build browser error must
    still tear the singleton session down (finally)."""
    gw = MockGateway(raise_on="fill")  # explode while naming the workflow
    builder = wb.WorkflowBuilder(gw, _gates(), location_id="L9")
    spec = wb.WorkflowSpec(name="x", trigger_type="Contact Created", action_type="Send Email")
    with pytest.raises(RuntimeError):
        builder.build(spec)
    assert gw.torn_down == 1, "teardown MUST run even when the build raises (no orphan engine)"
    assert gw.calls[-1] == ("teardown",)


def test_missing_required_gate_refuses_no_freehand(monkeypatch):
    """No invented CSS / no freehand: if a required gate is absent, the builder
    raises MissingGateError BEFORE opening a browser."""
    gates = _gates()
    # Drop a required gate to simulate an un-captured/removed selector.
    gates.steps.pop("save_workflow", None)
    gw = MockGateway()
    builder = wb.WorkflowBuilder(gw, gates, location_id="L9")
    spec = wb.WorkflowSpec(name="x", trigger_type="t", action_type="a")
    with pytest.raises(wb.MissingGateError):
        builder.build(spec)
    # It refused BEFORE touching the browser.
    assert gw.ensured == 0
    assert gw.calls == []


def test_no_workflow_id_readback_is_loud_not_silent():
    """A save with no readable id is a WorkflowBuildError — never a silent partial
    success reported as a build."""
    class NoIdGateway(MockGateway):
        def read(self, verb, *args):
            self.calls.append(("read", verb, args))
            return "https://app.gohighlevel.com/v2/location/L9/automation/workflows"  # no id
    gw = NoIdGateway()
    builder = wb.WorkflowBuilder(gw, _gates(), location_id="L9")
    spec = wb.WorkflowSpec(name="x", trigger_type="Contact Created", action_type="Send Email")
    with pytest.raises(wb.WorkflowBuildError):
        builder.build(spec)
    assert gw.torn_down == 1  # still tears down


def test_dry_run_opens_no_browser():
    gw = MockGateway()
    builder = wb.WorkflowBuilder(gw, _gates(), location_id="L9")
    spec = wb.WorkflowSpec(name="x", trigger_type="t", action_type="a")
    result = builder.build(spec, dry_run=True)
    assert result.dry_run is True
    assert result.torn_down is True
    assert gw.ensured == 0 and gw.torn_down == 0 and gw.calls == []
    assert result.steps_driven == gates_required()


def gates_required():
    return list(_gates().required)


def test_location_id_required():
    with pytest.raises(ValueError):
        wb.WorkflowBuilder(MockGateway(), _gates(), location_id="")


def test_managed_gateway_shells_browser_manager_never_agent_browser():
    """The concrete gateway drives browser_manager.sh — never the agent-browser
    binary directly (the unmanaged-spawn law)."""
    seen = []

    class FakeProc:
        returncode = 0
        stdout = "https://app.gohighlevel.com/v2/location/L/automation/workflows/WF_x123456"
        stderr = ""

    def fake_runner(argv):
        seen.append(argv)
        return FakeProc()

    gw = wb.Skill6ManagedGateway(manager_sh="/path/to/browser_manager.sh", runner=fake_runner)
    gw.ensure()
    gw.step("open", "/route")
    gw.read("eval", "location.href")
    gw.teardown()

    assert seen, "gateway must have shelled the manager"
    for argv in seen:
        assert argv[0].endswith("browser_manager.sh"), argv
        assert "agent-browser" not in argv[0], "must not invoke agent-browser directly"


def test_selftest_cli_passes():
    rc = wb.main(["--selftest"])
    assert rc == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
