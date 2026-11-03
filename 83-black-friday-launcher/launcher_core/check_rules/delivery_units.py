"""Check rule: the plan is the approved launch, and an automation is a real Skill 44 build.

``check_package`` runs ``violations`` (the check_rules seam). Two laws live here:

* CON-04. The sealed launch plan must be the approved launch it was dispatched from
  (launch_id, tenant, location, revision and approved_plan_hash all equal the
  manifest), and a Black Friday plan that promises no email sequence or no
  automation fails unless the intake recorded the client's choice.
* S44-21. An automation unit counts as delivered only when its artifact is the
  workflow export Skill 44's build command (``caf workflows build
  --from-automation-build``) produced: a JSON object with a workflow id, status
  ``draft``, ``unit_key`` ``<launch_id>/<unit id>`` and an ``expected_graph_hash``
  equal to the one Skill 44's reader wrote for that unit in ``automation-builds.json``
  (staged in the package root). Skill 44's own graph validator (``validate_graph.py``)
  must pass the export. A non-empty file with three free-text strings proves nothing.

Validator of record per unit type: automations = Skill 44 (here); email = Skill 50 and
Conversation AI = Skill 38 each ship a validate-delivery script of their own (not here).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from .. import launch_plan as lp
from ..constants import SkillResolutionError, resolve_ref

CODE_PLAN = "AF-LAUNCH-UNIT-PLAN"
CODE_AUTOMATION = "AF-LAUNCH-UNIT-AUTOMATION"
EXPORT_CONTRACT = "skill44.workflow-export.v1"
BUILD_COMMAND = "caf workflows build --from-automation-build"
BUILDS_DOC = "automation-builds.json"
VALIDATOR_REF = "44-convert-and-flow-operator/tools/validate_graph.py"
VALIDATOR_TIMEOUT_S = 60


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def reader_hashes(doc: Any, launch_id: Any) -> Dict[str, str]:
    """automation id -> the reader's expected_graph_hash, for READY builds of this launch."""
    if not isinstance(doc, Mapping) or doc.get("launch_id") != launch_id:
        return {}
    out: Dict[str, str] = {}
    for build in doc.get("builds") or []:
        if (isinstance(build, Mapping) and build.get("state") == "ready"
                and isinstance(build.get("id"), str)
                and lp._nonempty_str(build.get("expected_graph_hash"))):
            out[build["id"]] = build["expected_graph_hash"]
    return out


def automation_violations(unit_id: str, row: Any, launch_id: Any, expected: Mapping[str, str],
                          root: Path) -> List[str]:
    """Why ``row`` (a receipt row or a lane delivery) is not a Skill 44 build of ``unit_id``."""
    label = f"{CODE_AUTOMATION}: unit {unit_id!r}"
    root = Path(root)
    if not isinstance(row, Mapping):
        return [f"{label} has no delivery receipt row"]
    reader = expected.get(unit_id)
    if not reader:
        return [f"{label} has no ready build in the Skill 44 reader output ({BUILDS_DOC}); "
                "its expected_graph_hash cannot be compared"]
    lane = row.get("lane_validation")
    if not (isinstance(lane, Mapping) and lane.get("contract") == EXPORT_CONTRACT
            and lane.get("state") == "passed"):
        return [f"{label} lane_validation is not a passed {EXPORT_CONTRACT!r} (free text is not proof)"]
    artifacts = row.get("artifacts")
    art = artifacts[0] if isinstance(artifacts, list) and artifacts else None
    if not (isinstance(art, Mapping) and lp._nonempty_str(art.get("path"))):
        return [f"{label} carries no workflow export artifact"]
    target = (root / art["path"]).resolve()
    if Path(art["path"]).is_absolute() or not target.is_relative_to(root.resolve()) \
            or not target.is_file():
        return [f"{label} export {art['path']!r} does not resolve inside the package"]
    if hashlib.sha256(target.read_bytes()).hexdigest() != art.get("sha256"):
        return [f"{label} export {art['path']!r} does not match its recorded sha256"]
    try:
        export = _load(target)
    except (OSError, ValueError):
        return [f"{label} export {art['path']!r} is not JSON"]
    if not isinstance(export, Mapping):
        return [f"{label} export is not a workflow export object"]

    wrong = []
    if not lp._nonempty_str(export.get("workflow_id")):
        wrong.append("no workflow_id")
    if export.get("status") != "draft":
        wrong.append(f"status is {export.get('status')!r}, not 'draft'")
    if export.get("unit_key") != f"{launch_id}/{unit_id}":
        wrong.append(f"unit_key is {export.get('unit_key')!r}, not '{launch_id}/{unit_id}'")
    if export.get("produced_by") != BUILD_COMMAND:
        wrong.append(f"not produced by `{BUILD_COMMAND}`")
    if export.get("expected_graph_hash") != reader:
        wrong.append("expected_graph_hash is not the reader's")
    if wrong:
        return [f"{label} export is not the Skill 44 build: " + "; ".join(wrong)]

    try:
        validator = resolve_ref(VALIDATOR_REF)
    except SkillResolutionError:
        return [f"{label} cannot be validated: {VALIDATOR_REF} is not installed"]
    if not validator.is_file():
        return [f"{label} cannot be validated: {VALIDATOR_REF} is not installed"]
    try:
        done = subprocess.run([sys.executable, "-I", str(validator), "graph", "--export", str(target)],
                              capture_output=True, text=True, timeout=VALIDATOR_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError) as exc:
        return [f"{label} Skill 44 graph validator could not run ({type(exc).__name__})"]
    if done.returncode != 0:
        return [f"{label} Skill 44 graph validator refused the export (exit {done.returncode})"]
    return []


def _plan_of(manifest: Mapping[str, Any], root: Path) -> Optional[Any]:
    path = ((manifest.get("launch_plan") or {}).get("plan") or {}).get("path")
    if not path:
        return None
    try:
        return _load(root / path)
    except (OSError, ValueError):
        return None


def violations(manifest: Dict[str, Any], root: Path, skill_root: Path) -> List[str]:
    """The check_rules seam entry point. Empty list means the plan and its automations hold."""
    if manifest.get("launch_plan") is None:
        return []  # a page-only package carries no plan; checks.py names that scope
    root = Path(root)
    plan = _plan_of(manifest, root)
    if not isinstance(plan, Mapping):
        return [f"{CODE_PLAN}: the sealed launch plan cannot be read, so it cannot be bound"]

    intake: Mapping[str, Any] = {}
    intake_path = (manifest.get("intake") or {}).get("path")
    if intake_path:
        try:
            loaded = _load(root / intake_path)
            intake = loaded if isinstance(loaded, Mapping) else {}
        except (OSError, ValueError):
            intake = {}

    fails = [f"AF-LAUNCH-PLAN-BIND: {v}" for v in lp.bind_violations(plan, manifest)]
    fails += [f"AF-LAUNCH-PLAN-SCOPE: {v}"
              for v in lp.scope_violations(plan, intake.get("client_choices"))]

    try:
        automations = [u for u in lp.planned_units(plan) if u["type"] == "automation"]
    except lp.LaunchPlanError as exc:
        return fails + [f"{exc.code}: {exc.detail}"]
    if not automations:
        return fails

    try:
        expected = reader_hashes(_load(root / BUILDS_DOC), plan.get("launch_id"))
    except (OSError, ValueError):
        expected = {}
    try:
        receipt = _load(root / "receipt.json")
    except (OSError, ValueError):
        receipt = {}
    rows = ({r.get("unit_id"): r for r in (receipt.get("units") or []) if isinstance(r, Mapping)}
            if isinstance(receipt, Mapping) else {})
    for unit in automations:
        fails += automation_violations(unit["id"], rows.get(unit["id"]), plan.get("launch_id"),
                                       expected, root)
    return fails
