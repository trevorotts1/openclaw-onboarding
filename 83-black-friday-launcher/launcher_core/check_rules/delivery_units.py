"""Check rule: the plan is the approved launch, and an automation is a real Skill 44 build.

``check_package`` runs ``violations`` (the check_rules seam). These laws live here:

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
  The unit also carries the per-build QC result Skill 44's ``qc-built-workflow.sh --json``
  printed (``qc-<workflow_id>.json``): the same workflow, ``exit_code`` 0, PLAN MODE gate
  PASS and an exit gate PASS. An automation that was never QC'd, or whose QC did not
  return 0, cannot be sealed.
* AF-LAUNCH-PKG-RECEIPT-LANE. A unit another lane delivered counts only when its
  ``lane_validation.contract`` is the contract id that unit type's producer writes
  (``LANE_CONTRACTS``: email = Skill 50, text and automation = Skill 44), never a string the
  caller typed. A page another lane delivered and the Conversation AI have NO producer yet, so
  their set is empty and any lane delivery for them is refused by name. An email is also
  re-verified by Skill 50's own ``validate_delivery.py --check``, run by path exactly as
  ``validate_graph.py`` is run for an automation; an absent validator or a non-zero exit is a
  refusal, never a pass.

Validator of record per unit type: automations = Skill 44 (here); email = Skill 50 (here, by
path); text = the contract allow-list only until Skill 44 ships a text-set validator; a page
another lane delivers and Conversation AI (Skill 38) = none yet, so they cannot be sealed from
a lane delivery.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from .. import constants as _constants
from .. import launch_plan as lp
from ..constants import SkillResolutionError

CODE_PLAN = "AF-LAUNCH-UNIT-PLAN"
CODE_AUTOMATION = "AF-LAUNCH-UNIT-AUTOMATION"
CODE_LANE = "AF-LAUNCH-PKG-RECEIPT-LANE"
EXPORT_CONTRACT = "skill44.workflow-export.v1"
EMAIL_CONTRACT = "skill50.email-delivery.v1"
TEXT_CONTRACT = "skill44.sms-set.v1"
# unit_type -> the contract ids the producing lane may write into lane_validation.contract.
# An empty tuple means "no producer yet": nothing a caller types can seal that unit type.
LANE_CONTRACTS = {"email": (EMAIL_CONTRACT,), "text": (TEXT_CONTRACT,), "automation": (EXPORT_CONTRACT,),
                  "page": (), "conversation_ai": ()}
BUILD_COMMAND = "caf workflows build --from-automation-build"
BUILDS_DOC = "automation-builds.json"
VALIDATOR_REF = "44-convert-and-flow-operator/tools/validate_graph.py"
EMAIL_VALIDATOR_REF = "50-email-engine/tools/validate_delivery.py"
VALIDATOR_TIMEOUT_S = 60
# The per-build QC result file is qc-<workflow_id>.json: the JSON `qc-built-workflow.sh --json`
# prints, plus the script's own process exit status as "exit_code" (see SKILL.md, Launch mode).
QC_ARTIFACT = "qc-{workflow_id}.json"
QC_REQUIRED = (("exit_code", 0), ("exit_gate", "PASS"), ("overall_mechanical", "PASS"))


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _inside(root: Path, rel: Any) -> Optional[Path]:
    """The file ``rel`` names inside ``root``, or None when it escapes the package or is absent."""
    if not isinstance(rel, str) or not rel.strip() or Path(rel).is_absolute():
        return None
    target = (Path(root) / rel).resolve()
    return target if target.is_relative_to(Path(root).resolve()) and target.is_file() else None


def qc_violations(label: str, workflow_id: str, artifacts: List[Any], root: Path) -> List[str]:
    """Why the unit carries no passing per-build QC result for ``workflow_id`` (empty = it does)."""
    name = QC_ARTIFACT.format(workflow_id=workflow_id)
    art = next((a for a in artifacts if isinstance(a, Mapping) and isinstance(a.get("path"), str)
                and Path(a["path"]).name == name), None)
    if art is None:
        return [f"{label} carries no {name} artifact: the per-build QC result "
                "(qc-built-workflow.sh --json, exit 0) is part of the delivery"]
    target = _inside(root, art["path"])
    if target is None:
        return [f"{label} QC result {art['path']!r} does not resolve inside the package"]
    if hashlib.sha256(target.read_bytes()).hexdigest() != art.get("sha256"):
        return [f"{label} QC result {art['path']!r} does not match its recorded sha256"]
    try:
        qc = _load(target)
    except (OSError, ValueError):
        return [f"{label} QC result {art['path']!r} is not JSON"]
    if not isinstance(qc, Mapping):
        return [f"{label} QC result is not the QC script's JSON object"]
    wrong = []
    if qc.get("workflow_id") != workflow_id:
        wrong.append(f"workflow_id is {qc.get('workflow_id')!r}, not {workflow_id!r}")
    for key, want in QC_REQUIRED:
        got = qc.get(key)
        if got != want or type(got) is not type(want):
            wrong.append(f"{key} is {got!r}, not {want!r}")
    gate = qc.get("plan_mode_gate")
    if not (isinstance(gate, Mapping) and gate.get("status") == "PASS"):
        wrong.append(f"plan_mode_gate.status is {gate.get('status') if isinstance(gate, Mapping) else gate!r}, "
                     "not 'PASS'")
    if wrong:
        return [f"{label} QC did not pass: " + "; ".join(wrong)]
    return []


def lane_contract_violations(unit_id: str, unit_type: str, lane: Any) -> List[str]:
    """Why ``lane`` (a lane_validation object) is not a contract ``unit_type``'s producer writes."""
    allowed = LANE_CONTRACTS.get(unit_type, ())
    if not allowed:
        return [f"{CODE_LANE}: unit {unit_id!r} ({unit_type}) has no producer yet: no lane contract is "
                f"defined for a {unit_type} unit another lane delivers, so no lane delivery can seal it"]
    got = lane.get("contract") if isinstance(lane, Mapping) else None
    if got not in allowed:
        return [f"{CODE_LANE}: unit {unit_id!r} ({unit_type}) lane_validation contract {got!r} is not "
                f"{' or '.join(map(repr, allowed))}, the contract its producing lane writes "
                "(a self-declared string is not proof)"]
    return []


def lane_document(unit_id: str, row: Mapping[str, Any]) -> Dict[str, Any]:
    """The producing lane's delivery document for one unit, from a sealed receipt row."""
    return {"state": "complete", "unit": unit_id, "artifacts": row.get("artifacts"),
            "lane_validation": row.get("lane_validation"), "request": row.get("request")}


def email_delivery_violations(unit_id: str, document: Mapping[str, Any], root: Path) -> List[str]:
    """Re-run Skill 50's ``validate_delivery.py --check`` on an email unit's delivery document.

    The document is written to a transient file in the package root and checked with the working
    directory set there, so its artifact paths resolve against the package. Exit 0 is the only pass.
    """
    label = f"{CODE_LANE}: unit {unit_id!r}"
    try:
        validator = _constants.resolve_ref(EMAIL_VALIDATOR_REF)
    except SkillResolutionError:
        return [f"{label} cannot be validated: {EMAIL_VALIDATOR_REF} is not installed"]
    if not validator.is_file():
        return [f"{label} cannot be validated: {EMAIL_VALIDATOR_REF} is not installed"]
    root = Path(root)
    try:
        handle, name = tempfile.mkstemp(prefix=".lane-check-", suffix=".json", dir=str(root))
    except OSError:
        return [f"{label} cannot be validated: the package folder is not writable, so the lane "
                "receipt cannot be re-verified"]
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            json.dump(document, out, sort_keys=True)
        done = subprocess.run([sys.executable, "-I", str(validator), "--check", name],
                              capture_output=True, text=True, timeout=VALIDATOR_TIMEOUT_S,
                              cwd=str(root))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return [f"{label} Skill 50 delivery validator could not run ({type(exc).__name__})"]
    finally:
        try:
            os.unlink(name)
        except OSError:
            pass
    if done.returncode != 0:
        return [f"{label} Skill 50 delivery validator refused the receipt (exit {done.returncode})"]
    return []


def row_lane_violations(unit_id: str, unit_type: str, row: Mapping[str, Any], root: Path) -> List[str]:
    """The lane law for one sealed receipt row: the contract allow-list, then (email) the re-check."""
    fails = lane_contract_violations(unit_id, unit_type, row.get("lane_validation"))
    if fails or unit_type != "email":
        return fails
    return email_delivery_violations(unit_id, lane_document(unit_id, row), root)


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
        validator = _constants.resolve_ref(VALIDATOR_REF)
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
    return qc_violations(label, export["workflow_id"], artifacts, root)


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
        units = lp.planned_units(plan)
    except lp.LaunchPlanError as exc:
        return fails + [f"{exc.code}: {exc.detail}"]
    automations = [u for u in units if u["type"] == "automation"]
    lane_units = [u for u in units if u["type"] in ("email", "text", "conversation_ai", "page")]
    if not automations and not lane_units:
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
    for unit in lane_units:
        # A planned unit with no receipt row is named by checks.py (AF-LAUNCH-PKG-RECEIPT-UNITS). A page
        # the launcher itself built is proved by its own L04 row; only a page ANOTHER lane declared is judged.
        row = rows.get(unit["id"])
        if isinstance(row, Mapping) and (unit["type"] != "page" or row.get("delivery") == "declared"):
            fails += row_lane_violations(unit["id"], unit["type"], row, root)
    return fails
