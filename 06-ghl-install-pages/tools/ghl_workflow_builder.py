#!/usr/bin/env python3
"""ghl_workflow_builder.py — Skill 6 GATED, MANAGED Automations (Workflow) builder.

WHY (P3-08 Gap A): Skill 44 documented a "Tier 4 agent-browser" workflow-BUILD
backstop for when the Firebase token is unread/misconfigured, but no builder code
existed — a documented promise with NO implementation, routing readers to a
missing file. Skill 6's real browser infrastructure covered funnel/page/pipeline/
form/course/community/survey builders but had NO workflow builder and NO
Automations-UI gates. This module is that missing gated builder.

WHAT this is: the HARNESS that drives the GoHighLevel Automations builder UI to
create a workflow (name + trigger + action), reading its DOM gates from
``tools/gates.json`` (``automations_builder_gates``) and driving EVERY browser
action through Skill 6's ``browser_manager.sh`` SINGLETON gateway — one session,
lock=1, TTL, guaranteed teardown, reaper backstop. It NEVER spawns agent-browser
directly (the unmanaged-spawn law enforced by
``scripts/guard-agent-browser-managed.sh``) and NEVER freehand-navigates: if a
required gate is missing from the registry it raises ``MissingGateError`` rather
than inventing selectors ("NO invented CSS is shipped as fact" — Skill 6 law).

SELECTOR STATUS (honest): the Automations gates ship as ``status: runtime`` — the
harness resolves them against the LIVE DOM at runtime via accessibility role/name
find hints; they are NOT captured CSS asserted as fact. A live-capture hardening
pass on the operator's own GHL location will flip each to ``captured`` and record
the confirmed nodes in ``SELECTORS-LIVE-automations.md`` (the same discipline
every other Skill 6 runtime gate follows). The HARNESS itself is complete and
unit-tested here against a mocked gateway — only the live-captured SELECTORS are
the operator-box follow-on.

TOKEN CIRCULARITY (see 44-convert-and-flow-operator/SKILL.md): this Tier-4 path
helps ONLY when the Firebase token is unread/misconfigured — the managed browser
session it needs is seeded from the SAME token. A genuinely dead/revoked token
routes to ``ghl_auth.py``'s Tier-2 email-2FA self-heal, NOT here.

TESTABILITY: all browser I/O goes through a small ``Gateway`` protocol
(``ensure`` / ``step`` / ``read`` / ``teardown``). The default concrete gateway
(:class:`Skill6ManagedGateway`) shells ``browser_manager.sh``; tests (and
``--selftest``) inject a fake gateway, so the whole build path — gate loading,
step ordering, workflow-id readback, guaranteed teardown — is exercised
deterministically with NO live browser and NO network.

CLI:
  ghl_workflow_builder.py --selftest        # runnable proof via a fake gateway
  ghl_workflow_builder.py --location-id L --name N --trigger T --action A [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Protocol

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_GATES_PATH = os.path.join(_HERE, "gates.json")
DEFAULT_MANAGER_SH = os.path.join(_HERE, "browser_manager.sh")
AUTOMATIONS_GATES_KEY = "automations_builder_gates"

# The built workflow id read back from the builder URL after save. GHL routes the
# saved workflow to .../workflows/<id> (optionally .../workflows/builder/<id>).
_WORKFLOW_ID_RE = re.compile(r"/workflows/(?:builder/)?([A-Za-z0-9_-]{6,})")


class MissingGateError(RuntimeError):
    """A required Automations gate is absent from the registry. The builder
    REFUSES to run rather than freehand-navigate with invented selectors."""


class WorkflowBuildError(RuntimeError):
    """The build could not complete (e.g. the workflow id could not be read back
    after save). Raised loudly — never a silent partial success."""


# ── Gateway protocol — the ONLY door to the browser ───────────────────────────
class Gateway(Protocol):
    def ensure(self) -> None: ...
    def step(self, verb: str, *args: str) -> str: ...
    def read(self, verb: str, *args: str) -> str: ...
    def teardown(self) -> None: ...


@dataclass
class Skill6ManagedGateway:
    """Concrete gateway: drives Skill 6's ``browser_manager.sh`` SINGLETON gateway
    (one session, lock=1, TTL, guaranteed teardown, reaper backstop). Every verb
    is routed through the manager — this module never invokes the agent-browser
    binary itself, so the unmanaged-spawn guard passes. ``runner`` is injectable so
    the shell boundary is unit-testable without a live browser."""

    manager_sh: str = DEFAULT_MANAGER_SH
    env: Optional[dict] = None
    runner: Optional[Callable[[List[str]], "subprocess.CompletedProcess"]] = None
    _ensured: bool = field(default=False, init=False)

    def _run(self, verb: str, args: List[str]) -> str:
        argv = [self.manager_sh, verb]
        if args:
            argv += ["--", *args]
        run = self.runner or self._default_runner
        proc = run(argv)
        if getattr(proc, "returncode", 0) != 0:
            raise WorkflowBuildError(
                f"browser_manager.sh {verb} failed (rc={proc.returncode}): "
                f"{getattr(proc, 'stderr', '')!r}"
            )
        return getattr(proc, "stdout", "") or ""

    def _default_runner(self, argv: List[str]) -> "subprocess.CompletedProcess":
        return subprocess.run(
            argv, capture_output=True, text=True, env=self.env, check=False
        )

    def ensure(self) -> None:
        self._run("ensure", [])
        self._ensured = True

    def step(self, verb: str, *args: str) -> str:
        return self._run(verb, list(args))

    def read(self, verb: str, *args: str) -> str:
        return self._run(verb, list(args))

    def teardown(self) -> None:
        # Best-effort teardown of the canonical singleton session; the manager's
        # own trap + host reaper are the backstop if this process is killed first.
        self._run("teardown", [])
        self._ensured = False


# ── Gate registry ─────────────────────────────────────────────────────────────
@dataclass
class AutomationsGates:
    raw: dict
    steps: Dict[str, dict]
    required: List[str]
    nav_route_template: str
    capture_status: str

    def find_hint(self, name: str) -> str:
        step = self.steps.get(name)
        if step is None:
            raise MissingGateError(
                f"required Automations gate '{name}' is absent from "
                f"gates.json[{AUTOMATIONS_GATES_KEY}] — the builder refuses to "
                f"freehand-navigate (NO invented CSS is shipped as fact)."
            )
        hint = step.get("find")
        if not hint:
            raise MissingGateError(
                f"Automations gate '{name}' has no 'find' hint — refusing to guess."
            )
        return hint


def load_automations_gates(gates_path: str = DEFAULT_GATES_PATH) -> AutomationsGates:
    with open(gates_path, encoding="utf-8") as fh:
        data = json.load(fh)
    section = data.get(AUTOMATIONS_GATES_KEY)
    if not isinstance(section, dict):
        raise MissingGateError(
            f"gates.json is missing the '{AUTOMATIONS_GATES_KEY}' section — the "
            f"Tier-4 gated workflow builder has no gate registry to drive."
        )
    steps = {s["name"]: s for s in section.get("steps", []) if isinstance(s, dict) and s.get("name")}
    required = list(section.get("required_steps", []))
    return AutomationsGates(
        raw=section,
        steps=steps,
        required=required,
        nav_route_template=section.get("nav_route_template", ""),
        capture_status=section.get("_capture_status", "unknown"),
    )


# ── Workflow spec + result ────────────────────────────────────────────────────
@dataclass
class WorkflowSpec:
    name: str
    trigger_type: str
    action_type: str


@dataclass
class BuildResult:
    workflow_id: Optional[str]
    workflow_url: Optional[str]
    location_id: str
    name: str
    tier: str = "tier-4-gated-managed"
    capture_status: str = "pending_live_capture"
    steps_driven: List[str] = field(default_factory=list)
    torn_down: bool = False
    dry_run: bool = False

    def as_dict(self) -> dict:
        return {
            "workflow_id": self.workflow_id,
            "workflow_url": self.workflow_url,
            "location_id": self.location_id,
            "name": self.name,
            "tier": self.tier,
            "selector_capture_status": self.capture_status,
            "steps_driven": self.steps_driven,
            "torn_down": self.torn_down,
            "dry_run": self.dry_run,
        }


# ── The builder ───────────────────────────────────────────────────────────────
class WorkflowBuilder:
    """Drives the Automations UI to build one workflow through the managed gateway.

    Contract:
      * every browser action routes through ``gateway`` (never bare agent-browser);
      * a missing required gate → ``MissingGateError`` (no freehand navigation);
      * ``build`` ALWAYS tears the session down (``finally``) — zero orphan engines,
        reaper-clean — even on an exception mid-build;
      * the built workflow id is read back and returned (or ``WorkflowBuildError``
        if it cannot be read — never a silent partial success).
    """

    def __init__(self, gateway: Gateway, gates: AutomationsGates, location_id: str):
        if not location_id:
            raise ValueError("location_id is required (client sovereignty — build only on the whitelisted location)")
        self.gateway = gateway
        self.gates = gates
        self.location_id = location_id

    def _assert_gates_present(self) -> None:
        # Fail BEFORE opening a browser if any required gate is missing.
        for name in self.gates.required:
            self.gates.find_hint(name)

    def _nav_route(self) -> str:
        tmpl = self.gates.nav_route_template or "/v2/location/{location_id}/automation/workflows"
        return tmpl.replace("{location_id}", self.location_id)

    def build(self, spec: WorkflowSpec, dry_run: bool = False) -> BuildResult:
        self._assert_gates_present()
        result = BuildResult(
            workflow_id=None, workflow_url=None, location_id=self.location_id,
            name=spec.name, capture_status=self.gates.capture_status, dry_run=dry_run,
        )
        if dry_run:
            # Plan-only: prove gate ordering resolves without opening a browser.
            result.steps_driven = list(self.gates.required)
            result.torn_down = True
            return result

        try:
            self.gateway.ensure()
            result.steps_driven.append("open_automations")
            self.gateway.step("open", self._nav_route())

            for name in ("create_workflow", "start_from_scratch"):
                self.gateway.step("find", self.gates.find_hint(name))
                result.steps_driven.append(name)

            self.gateway.step("fill", self.gates.find_hint("name_workflow"), spec.name)
            result.steps_driven.append("name_workflow")

            self.gateway.step("find", self.gates.find_hint("add_trigger"))
            self.gateway.step(
                "find", self.gates.find_hint("choose_trigger_type").replace("{trigger_type}", spec.trigger_type)
            )
            self.gateway.step("find", self.gates.find_hint("save_trigger"))
            result.steps_driven += ["add_trigger", "choose_trigger_type", "save_trigger"]

            self.gateway.step("find", self.gates.find_hint("add_action"))
            self.gateway.step(
                "find", self.gates.find_hint("choose_action_type").replace("{action_type}", spec.action_type)
            )
            self.gateway.step("find", self.gates.find_hint("save_action"))
            result.steps_driven += ["add_action", "choose_action_type", "save_action"]

            self.gateway.step("find", self.gates.find_hint("save_workflow"))
            result.steps_driven.append("save_workflow")

            href = self.gateway.read("eval", "location.href")
            result.steps_driven.append("read_workflow_id")
            result.workflow_url = (href or "").strip() or None
            wf_id = self._parse_workflow_id(result.workflow_url or "")
            if not wf_id:
                raise WorkflowBuildError(
                    "workflow saved but its id could not be read back from the "
                    f"builder URL {result.workflow_url!r} — refusing to report a "
                    "build without proof of the created workflow id."
                )
            result.workflow_id = wf_id
            return result
        finally:
            # GUARANTEED teardown — zero orphan engines after the build, reaper-clean.
            self.gateway.teardown()
            result.torn_down = True

    @staticmethod
    def _parse_workflow_id(url: str) -> Optional[str]:
        m = _WORKFLOW_ID_RE.search(url or "")
        return m.group(1) if m else None


# ── Fake gateway for --selftest (and a template for unit tests) ───────────────
class _FakeGateway:
    """In-memory gateway that records the managed calls and returns a canned
    builder URL on the id read-back. Proves the harness end-to-end with NO live
    browser. Real builds use :class:`Skill6ManagedGateway`."""

    def __init__(self, workflow_id: str = "WF_selftest_1a2b3c"):
        self.calls: List[str] = []
        self._workflow_id = workflow_id
        self.ensured = 0
        self.torn_down = 0

    def ensure(self) -> None:
        self.ensured += 1
        self.calls.append("ensure")

    def step(self, verb: str, *args: str) -> str:
        self.calls.append(f"step:{verb}:{shlex.join(args) if args else ''}")
        return ""

    def read(self, verb: str, *args: str) -> str:
        self.calls.append(f"read:{verb}:{shlex.join(args) if args else ''}")
        return f"https://app.gohighlevel.com/v2/location/L1/automation/workflows/{self._workflow_id}"

    def teardown(self) -> None:
        self.torn_down += 1
        self.calls.append("teardown")


def _selftest() -> int:
    gates = load_automations_gates()
    gw = _FakeGateway()
    builder = WorkflowBuilder(gw, gates, location_id="L1")
    spec = WorkflowSpec(name="P3-08 selftest workflow", trigger_type="Contact Created", action_type="Send Email")
    result = builder.build(spec)
    ok = (
        result.workflow_id == "WF_selftest_1a2b3c"
        and result.torn_down
        and gw.ensured == 1
        and gw.torn_down == 1
    )
    print(json.dumps({"selftest": "pass" if ok else "FAIL", **result.as_dict(),
                      "gateway_calls": gw.calls}, indent=2))
    return 0 if ok else 1


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Skill 6 gated Automations workflow builder (P3-08)")
    ap.add_argument("--selftest", action="store_true",
                    help="run the whole build path through a fake gateway (no browser) and print proof")
    ap.add_argument("--gates-path", default=DEFAULT_GATES_PATH)
    ap.add_argument("--location-id", default=None)
    ap.add_argument("--name", default=None)
    ap.add_argument("--trigger", default=None, help="trigger type (e.g. 'Contact Created')")
    ap.add_argument("--action", default=None, help="action type (e.g. 'Send Email')")
    ap.add_argument("--dry-run", action="store_true", help="resolve+order gates, open no browser")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    if not (args.location_id and args.name and args.trigger and args.action):
        ap.error("--location-id, --name, --trigger and --action are required (or use --selftest)")

    gates = load_automations_gates(args.gates_path)
    gateway = Skill6ManagedGateway()
    builder = WorkflowBuilder(gateway, gates, location_id=args.location_id)
    spec = WorkflowSpec(name=args.name, trigger_type=args.trigger, action_type=args.action)
    result = builder.build(spec, dry_run=args.dry_run)
    print(json.dumps(result.as_dict(), indent=2))
    return 0 if (args.dry_run or result.workflow_id) else 1


if __name__ == "__main__":
    raise SystemExit(main())
