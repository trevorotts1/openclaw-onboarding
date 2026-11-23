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
  (``LANE_CONTRACTS``: email = Skill 50, text and automation = Skill 44, a page another skill
  installed = ``skill06.page-draft-install.v1``), never a string the caller typed. The
  Conversation AI has NO producer yet, so its set is empty and any lane delivery for it is
  refused by name. An email is also re-verified by Skill 50's own ``validate_delivery.py
  --check``, run by path exactly as ``validate_graph.py`` is run for an automation; an absent
  validator or a non-zero exit is a refusal, never a pass.
* SWB-033. A page another skill installed (a GoHighLevel DRAFT page installed through Skill 06's
  rail by a page skill) counts only when ``page_draft_violations`` holds: its ``page_install``
  facts (page, funnel, step, location, draft version id, content sha256, preview status 200,
  ``published`` false, installed_by, read_by) are re-read from its own sealed files, never
  believed: one ``install_receipt`` artifact written by ``installed_by`` must name this page, its
  location and this exact draft (version id or content sha256), and exactly one
  ``independent_readback`` artifact written by ``read_by`` (a different unit than the installer)
  must show the live record read by GET: the same ids, a draft top version with that version id
  and content sha256, no published version, not deleted, preview HTTP 200. Anything unverifiable
  is refused.

Validator of record per unit type: automations = Skill 44 (here); email = Skill 50 (here, by
path); text = the contract allow-list only until Skill 44 ships a text-set validator; a page
another skill installed = ``page_draft_violations`` (here); Conversation AI (Skill 38) = none
yet, so it cannot be sealed from a lane delivery.
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
PAGE_CONTRACT = "skill06.page-draft-install.v1"
# unit_type -> the contract ids the producing lane may write into lane_validation.contract.
# An empty tuple means "no producer yet": nothing a caller types can seal that unit type.
LANE_CONTRACTS = {"email": (EMAIL_CONTRACT,), "text": (TEXT_CONTRACT,), "automation": (EXPORT_CONTRACT,),
                  "page": (PAGE_CONTRACT,), "conversation_ai": ()}
# SWB-033: the facts a page another skill installed carries, and the artifact roles that prove them.
PAGE_INSTALL_ROLE = "install_receipt"
PAGE_READBACK_ROLE = "independent_readback"
PAGE_READBACK_KIND = "rest_readback"
PAGE_ID_KEYS = ("page_id", "funnel_id", "step_id", "location_id", "draft_version_id",
                "installed_by", "read_by")
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


def _strings(value: Any) -> List[str]:
    """Every string value inside a JSON document (keys excluded)."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def _sealed_json(label: str, art: Mapping[str, Any], root: Path):
    """(document, refusal): one artifact's JSON, read from its hash-checked bytes inside ``root``."""
    target = _inside(root, art.get("path"))
    if target is None:
        return None, f"{label} artifact {art.get('path')!r} does not resolve inside the package"
    if hashlib.sha256(target.read_bytes()).hexdigest() != art.get("sha256"):
        return None, f"{label} artifact {art.get('path')!r} does not match its recorded sha256"
    try:
        return _load(target), None
    except (OSError, ValueError):
        return None, f"{label} artifact {art.get('path')!r} is not JSON"


def page_draft_violations(unit_id: str, row: Mapping[str, Any], root: Path) -> List[str]:
    """SWB-033: why ``row`` is not a verified DRAFT page another skill installed (empty = it is).

    Every fact in ``row['page_install']`` must be re-read from the row's own sealed files: an
    ``install_receipt`` written by the installer that names this page and this exact draft, and one
    ``independent_readback`` written by a different unit that read the live record by GET."""
    label = f"{CODE_LANE}: unit {unit_id!r} (page)"
    lane = row.get("lane_validation")
    if not (isinstance(lane, Mapping) and lane.get("contract") == PAGE_CONTRACT and lane.get("state") == "passed"):
        return [f"{label} lane_validation is not a passed {PAGE_CONTRACT!r}"]
    facts = row.get("page_install")
    if not isinstance(facts, Mapping):
        return [f"{label} carries no page_install record (page, funnel, step, location, draft version, "
                "content sha256, preview status, published, installed_by, read_by)"]
    wrong = [f"page_install.{key} is missing" for key in PAGE_ID_KEYS if not lp._nonempty_str(facts.get(key))]
    sha = facts.get("content_sha256")
    if not (isinstance(sha, str) and len(sha) == 64 and all(c in "0123456789abcdef" for c in sha)):
        wrong.append("page_install.content_sha256 is not 64 lowercase hex")
    if facts.get("published") is not False:
        wrong.append(f"page_install.published is {facts.get('published')!r}, not false: only an unpublished "
                     "DRAFT page is delivered by this contract")
    status = facts.get("preview_http_status")
    if status != 200 or type(status) is not int:
        wrong.append(f"page_install.preview_http_status is {status!r}, not 200")
    if lp._nonempty_str(facts.get("installed_by")) and facts.get("installed_by") == facts.get("read_by"):
        wrong.append("read_by is the installer itself: the read-back must be independent")
    if lp._nonempty_str(row.get("location_id")) and facts.get("location_id") != row.get("location_id"):
        wrong.append(f"page_install.location_id {facts.get('location_id')!r} is not the launch's "
                     f"{row.get('location_id')!r}")
    if wrong:
        return [f"{label} page_install is not a verifiable draft install: " + "; ".join(wrong)]

    artifacts = [a for a in (row.get("artifacts") or []) if isinstance(a, Mapping)]
    installs = [a for a in artifacts if a.get("role") == PAGE_INSTALL_ROLE]
    readbacks = [a for a in artifacts if a.get("role") == PAGE_READBACK_ROLE]
    if not installs:
        return [f"{label} carries no {PAGE_INSTALL_ROLE!r} artifact"]
    if len(readbacks) != 1:
        return [f"{label} carries {len(readbacks)} {PAGE_READBACK_ROLE!r} artifacts, not exactly one"]

    # The installer's own receipt must name this page, its location and this exact draft.
    named = False
    for art in installs:
        doc, why = _sealed_json(label, art, root)
        if why:
            return [why]
        if not isinstance(doc, Mapping):
            return [f"{label} install receipt {art.get('path')!r} is not a JSON object"]
        if doc.get("unit") == facts["read_by"]:
            return [f"{label} install receipt {art.get('path')!r} was written by the reader "
                    f"{facts['read_by']!r}: the read-back must be independent of the install"]
        if doc.get("published") is True:
            return [f"{label} install receipt {art.get('path')!r} records a publish"]
        text = _strings(doc)
        if (doc.get("unit") == facts["installed_by"] and doc.get("page_id") == facts["page_id"]
                and doc.get("location_id") == facts["location_id"]
                and (facts["draft_version_id"] in text or sha in text)):
            named = True
    if not named:
        return [f"{label} no install receipt written by {facts['installed_by']!r} names page "
                f"{facts['page_id']!r} in location {facts['location_id']!r} and its draft "
                f"(version {facts['draft_version_id']!r} or content {sha})"]

    doc, why = _sealed_json(label, readbacks[0], root)
    if why:
        return [why]
    if not isinstance(doc, Mapping) or doc.get("kind") != PAGE_READBACK_KIND:
        return [f"{label} read-back is not a {PAGE_READBACK_KIND!r} record"]
    method = doc.get("method")
    page = (doc.get("pages") or {}).get(unit_id) if isinstance(doc.get("pages"), Mapping) else None
    top = page.get("top_version") if isinstance(page, Mapping) else None
    if not isinstance(top, Mapping):
        return [f"{label} read-back carries no live record for {unit_id!r}"]
    checks = (
        ("read-back unit", doc.get("unit"), facts["read_by"]),
        ("read-back location_id", doc.get("location_id"), facts["location_id"]),
        ("read_at present", lp._nonempty_str(doc.get("read_at")), True),
        ("read by GET", isinstance(method, str) and "GET" in method, True),
        ("http_status", page.get("http_status"), 200),
        ("page_id", page.get("page_id"), facts["page_id"]),
        ("funnelId", page.get("funnelId"), facts["funnel_id"]),
        ("stepId", page.get("stepId"), facts["step_id"]),
        ("deleted", page.get("deleted"), False),
        ("published_version_present", page.get("published_version_present"), False),
        ("top_version.pageType", top.get("pageType"), "draft"),
        ("top_version.versionId", top.get("versionId"), facts["draft_version_id"]),
        ("top_version.blob_sha256", top.get("blob_sha256"), sha),
        ("preview_http_status", page.get("preview_http_status"), 200),
    )
    bad = [f"{name} is {got!r}, not {want!r}" for name, got, want in checks
           if got != want or type(got) is not type(want)]
    if bad:
        return [f"{label} the independent read-back does not show this draft: " + "; ".join(bad)]
    return []


def row_lane_violations(unit_id: str, unit_type: str, row: Mapping[str, Any], root: Path) -> List[str]:
    """The lane law for one sealed receipt row: the contract allow-list, then (email) the re-check
    and (a page another skill installed) the draft read-back law."""
    fails = lane_contract_violations(unit_id, unit_type, row.get("lane_validation"))
    if fails:
        return fails
    if unit_type == "page":
        return page_draft_violations(unit_id, row, root)
    if unit_type != "email":
        return fails
    return email_delivery_violations(unit_id, lane_document(unit_id, row), root)


def external_page_slots(receipt: Any) -> Dict[str, str]:
    """route slot -> unit id for every sealed page row another skill delivered (SWB-033).

    Only a row under the page contract that names its slot counts; whether the row is TRUE is judged by
    ``violations`` (row_lane_violations), so a forged row still fails the package."""
    out: Dict[str, str] = {}
    rows = receipt.get("units") if isinstance(receipt, Mapping) else None
    for row in rows or []:
        if (isinstance(row, Mapping) and row.get("unit_type") == "page" and row.get("delivery") == "declared"
                and isinstance(row.get("lane_validation"), Mapping)
                and row["lane_validation"].get("contract") == PAGE_CONTRACT
                and lp._nonempty_str(row.get("page_slot")) and lp._nonempty_str(row.get("unit_id"))):
            out[row["page_slot"]] = row["unit_id"]
    return out


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
