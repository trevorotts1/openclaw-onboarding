"""Skill 44 ADOPT path (SWB-081): an honest workflow-export row for a workflow that already exists.

``caf workflows build --from-automation-build`` can only export what it built itself. Some launch
automations were built another way (a browser build of an if/else, an SMS-only unit the compiler has
no workflow for) and live in GoHighLevel as DRAFT workflows. ``caf workflows adopt`` gives those a
``skill44.workflow-export.v1`` object WITHOUT pretending the build command produced them:

* ``produced_by`` is ``adopt`` (never the build command's name);
* the saved graph is read back from GoHighLevel now, must be a draft, and must pass Skill 44's own
  graph validator (``tools/validate_graph.py``, the same one Skill 83 re-runs);
* ``expected_graph_hash`` is the real hash of that saved graph, computed here, not copied from a reader;
* a delivery row is written ONLY when every adopted workflow also has a signed per-build QC result
  (``qc-<workflow_id>.json``: exit 0, both gates PASS, the PLAN MODE and QC-session approval verified
  by ``qc-built-workflow.sh``) whose ``graph_hash`` is the hash of the graph read just now. A graph
  edited after its QC, a failed validation, a missing QC and a wrong unit key each refuse by name.

Nothing here writes to GoHighLevel. No network of its own: the caller hands in ``read_workflow``.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from cli_anything.gohighlevel.utils.delivery_export import (
    EXPORT_CONTRACT, LANE, graph_passes, write_json,
)

ADOPT_PRODUCER = "adopt"
QC_NAME = "qc-%s.json"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def split_unit_key(unit_key: str) -> tuple:
    """(launch_id, unit_id) of ``<launch_id>/<unit_id>``; ValueError otherwise."""
    parts = unit_key.split("/") if isinstance(unit_key, str) else []
    if len(parts) != 2 or not all(p.strip() for p in parts):
        raise ValueError("unit key must be <launch_id>/<unit_id>, got %r" % (unit_key,))
    return parts[0], parts[1]


def read_member(workflow_id: str, read_workflow: Callable[[str], Optional[Mapping[str, Any]]],
                graph_hash: Callable[[list], str]) -> tuple:
    """(member dict, None) for a readable DRAFT workflow whose saved graph passes, else (None, reason)."""
    doc = read_workflow(workflow_id)
    if not isinstance(doc, Mapping):
        return None, "workflow %s cannot be read back now" % workflow_id
    if (doc.get("id") or doc.get("_id")) != workflow_id:
        return None, "workflow %s: the read-back is a different workflow" % workflow_id
    if doc.get("status") != "draft":
        return None, "workflow %s is %r, not a draft" % (workflow_id, doc.get("status"))
    data = doc.get("workflowData")
    templates = data.get("templates") if isinstance(data, Mapping) else doc.get("templates")
    if not isinstance(templates, list) or not templates:
        return None, "workflow %s has no saved graph to adopt" % workflow_id
    ok, detail = graph_passes(templates)
    if not ok:
        return None, "workflow %s saved graph refused: %s" % (workflow_id, detail)
    return {"workflow_id": workflow_id, "name": doc.get("name"),
            "graph_hash": graph_hash(templates), "templates": templates}, None


def qc_refusals(member: Mapping[str, Any], qc: Any) -> list:
    """Why ``qc`` is not a passing signed QC of exactly this member's saved graph (empty = it is)."""
    if not isinstance(qc, Mapping):
        return ["its QC result is not the QC script's JSON object"]
    wrong = []
    if qc.get("workflow_id") != member["workflow_id"]:
        wrong.append("workflow_id is %r" % (qc.get("workflow_id"),))
    for key, want in (("exit_code", 0), ("exit_gate", "PASS"), ("overall_mechanical", "PASS")):
        got = qc.get(key)
        if got != want or type(got) is not type(want):
            wrong.append("%s is %r, not %r" % (key, got, want))
    gate = qc.get("plan_mode_gate")
    if not (isinstance(gate, Mapping) and gate.get("status") == "PASS"):
        wrong.append("plan_mode_gate is not PASS")
    if qc.get("graph_hash") != member["graph_hash"]:
        wrong.append("it graded graph %s, the saved graph is %s (edited since QC, or QC predates "
                     "graph hashing)" % (qc.get("graph_hash") or "unrecorded", member["graph_hash"]))
    return wrong


def adopt_unit(unit_key: str, workflow_ids: list, read_workflow, graph_hash, out_dir: Path) -> tuple:
    """(export path, members, []) for a unit whose workflows all read back as passing drafts."""
    try:
        launch_id, unit_id = split_unit_key(unit_key)
    except ValueError as exc:
        return None, [], [str(exc)]
    if not workflow_ids or len(set(workflow_ids)) != len(workflow_ids):
        return None, [], ["name each workflow of the unit once"]
    members, reasons = [], []
    for wid in workflow_ids:
        member, why = read_member(wid, read_workflow, graph_hash)
        if why:
            reasons.append(why)
        else:
            members.append(member)
    if reasons:
        return None, [], reasons
    primary = members[0]
    export = {
        "contract": EXPORT_CONTRACT,
        "workflow_id": primary["workflow_id"],
        "name": primary["name"],
        "status": "draft",
        "unit_key": unit_key,
        "produced_by": ADOPT_PRODUCER,
        "expected_graph_hash": primary["graph_hash"],
        "readback_hash": primary["graph_hash"],
        "templates": primary["templates"],
        "workflows": [{k: m[k] for k in ("workflow_id", "name", "graph_hash", "templates")}
                      for m in members],
    }
    return write_json(out_dir / ("%s__%s.adopt.json" % (launch_id, unit_id)), export), members, []


def adopt_row(export_path: Path, members: list, qc_dir: Path, base_dir: Path, *,
              launch_id: str, unit_id: str, plan_sha256: str) -> tuple:
    """(row, []) when every member has a passing signed QC of its current graph, else (None, reasons)."""
    reasons, qc_paths = [], []
    for member in members:
        path = Path(qc_dir) / (QC_NAME % member["workflow_id"])
        if not path.is_file():
            reasons.append("workflow %s has no %s" % (member["workflow_id"], path.name))
            continue
        try:
            qc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            reasons.append("workflow %s: %s is not JSON" % (member["workflow_id"], path.name))
            continue
        why = qc_refusals(member, qc)
        if why:
            reasons.append("workflow %s QC did not pass for this graph: %s"
                           % (member["workflow_id"], "; ".join(why)))
        else:
            qc_paths.append(path)
    if reasons:
        return None, reasons
    artifacts = []
    for path, role in [(export_path, "workflow_export")] + [(p, "qc") for p in qc_paths]:
        rel = os.path.relpath(path, base_dir)
        if rel.startswith("..") or os.path.isabs(rel):
            return None, ["%s is outside %s; keep the export, the QC files and the deliveries file "
                          "in the Skill 83 run directory tree" % (Path(path).name, base_dir)]
        data = Path(path).read_bytes()
        artifacts.append({"path": rel.replace(os.sep, "/"), "role": role,
                          "sha256": _sha256_bytes(data), "size": len(data)})
    return {
        "state": "complete",
        "artifacts": artifacts,
        "lane_validation": {"lane": LANE, "contract": EXPORT_CONTRACT, "state": "passed"},
        "request": {"launch_id": launch_id, "unit_id": unit_id, "plan_sha256": plan_sha256},
    }, []
