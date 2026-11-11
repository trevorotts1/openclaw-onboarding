"""Skill 44's side of the launch delivery handoff to Skill 83 (issues 64, 1, 3).

``caf workflows build --from-automation-build ... --deliveries-out <file>`` calls
``export_build`` once the build and its read-back are done. For every launch unit that
built AND read back clean it writes a typed export object next to the build journal and
one row in the deliveries file Skill 83's ``assemble --deliveries`` reads:

* an automation unit  -> ``skill44.workflow-export.v1`` (``<journal dir>/exports/
  <launch_id>__<unit_id>.export.json``), the object Skill 83's
  ``check_rules/delivery_units.py`` re-checks (workflow id, ``draft``, unit key,
  ``produced_by``, the reader's ``expected_graph_hash`` and Skill 44's own graph validator);
* a text set          -> ``skill44.sms-set.v1`` (``<launch_id>__<set_id>.sms-set.json``).

Nothing here is a claim: a unit is exported only from the provider's own read-back
(the journal's verified hash, re-read just now and re-hashed), and only when
``tools/validate_graph.py`` passes the saved graph. A unit that cannot be proven is
refused by name and absent from the deliveries file, so Skill 83 reports it missing.

No network of its own: the caller hands in ``read_templates(workflow_id)``.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

EXPORT_CONTRACT = "skill44.workflow-export.v1"
SMS_SET_CONTRACT = "skill44.sms-set.v1"
BUILD_COMMAND = "caf workflows build --from-automation-build"
LANE = "skill44"
# utils -> gohighlevel -> cli_anything -> engine -> tools
VALIDATOR = Path(__file__).resolve().parents[4] / "validate_graph.py"
VALIDATOR_TIMEOUT_S = 60


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def graph_passes(templates: list) -> tuple:
    """(ok, detail): Skill 44's own graph validator on a saved graph, run as Skill 83 runs it."""
    if not VALIDATOR.is_file():
        return False, "tools/validate_graph.py is not installed"
    with tempfile.TemporaryDirectory(prefix="caf-export-") as td:
        probe = Path(td) / "graph.json"
        probe.write_text(json.dumps({"templates": templates}), encoding="utf-8")
        try:
            done = subprocess.run([sys.executable, "-I", str(VALIDATOR), "graph", "--export",
                                   str(probe)], capture_output=True, text=True,
                                  timeout=VALIDATOR_TIMEOUT_S)
        except (OSError, subprocess.SubprocessError) as exc:
            return False, "graph validator could not run (%s)" % type(exc).__name__
    return done.returncode == 0, "graph validator exit %d" % done.returncode


def _workflow_proof(key: str, wf_def: Mapping[str, Any], stats: Mapping[str, Any],
                    journal: Any, read_templates: Callable[[str], Optional[list]],
                    graph_hash: Callable[[list], str]) -> tuple:
    """(proof dict, None) for a workflow built and read back clean, else (None, reason)."""
    unit_key = wf_def.get("unit_key")
    wid = (stats.get("workflow_ids") or {}).get(key)
    if not wid:
        return None, "workflow %s was not built" % key
    if unit_key in (stats.get("needs_reconcile") or []):
        return None, "workflow %s needs reconcile before it can be trusted" % key
    if wf_def.get("status") != "draft":
        return None, "workflow %s is not a draft" % key
    rb = (stats.get("readback") or {}).get(key)
    if isinstance(rb, Mapping):
        if rb.get("ok") is not True:
            return None, "workflow %s read-back did not match the compiled graph" % key
        verified = rb.get("readback_hash")
    else:
        # An adopted workflow (re-run): the journal's own verified read-back is the proof.
        entry = journal.latest_phase(unit_key, "readback") if journal else None
        adopted = journal.latest_phase(unit_key, "reconcile") if journal else None
        entry = entry if (entry and entry.get("status") == "ok") else (
            adopted if (adopted and adopted.get("status") == "adopted") else None)
        if not entry or entry.get("remote_id") != wid:
            return None, "workflow %s has no verified read-back receipt in the journal" % key
        verified = entry.get("readback_hash")
    templates = read_templates(wid)
    if templates is None:
        return None, "workflow %s cannot be read back now" % key
    if not verified or graph_hash(templates) != verified:
        return None, "workflow %s changed since its verified read-back" % key
    ok, detail = graph_passes(templates)
    if not ok:
        return None, "workflow %s saved graph refused: %s" % (key, detail)
    return {"key": key, "workflow_id": str(wid), "name": wf_def.get("name"),
            "unit_key": unit_key, "readback_hash": verified, "templates": templates}, None


def unit_workflows(campaign: Mapping[str, Any], unit_id: str) -> list:
    return [(k, v) for k, v in campaign.items()
            if isinstance(v, Mapping) and v.get("source_unit") == unit_id]


def write_json(path: Path, doc: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def export_unit(unit_id: str, launch_id: str, campaign: Mapping[str, Any],
                stats: Mapping[str, Any], journal: Any, read_templates, out_dir: Path) -> tuple:
    """(export path, proofs, []) for a proven automation unit, else (None, [], reasons)."""
    from cli_anything.gohighlevel.utils.workflow_builder import graph_hash

    members = unit_workflows(campaign, unit_id)
    if not members:
        return None, [], ["no workflow compiled for the unit"]
    proofs, reasons = [], []
    for key, wf_def in members:
        proof, why = _workflow_proof(key, wf_def, stats, journal, read_templates, graph_hash)
        if why:
            reasons.append(why)
        else:
            proofs.append(proof)
    expected = {wf_def.get("expected_source_hash") for _k, wf_def in members}
    if len(expected) != 1 or not next(iter(expected)):
        reasons.append("the unit's workflows carry no single expected_graph_hash")
    if reasons:
        return None, [], reasons
    primary = proofs[0]
    export = {
        "contract": EXPORT_CONTRACT,
        "workflow_id": primary["workflow_id"],
        "name": primary["name"],
        "status": "draft",
        "unit_key": "%s/%s" % (launch_id, unit_id),
        "produced_by": BUILD_COMMAND,
        "expected_graph_hash": next(iter(expected)),
        "readback_hash": primary["readback_hash"],
        "journal": getattr(journal, "path", Path("journal")).name,
        # The saved graph itself, so the validator Skill 83 re-runs has a graph to judge.
        "templates": primary["templates"],
        "workflows": [{k: p[k] for k in ("key", "workflow_id", "name", "unit_key",
                                         "readback_hash")} for p in proofs],
    }
    return write_json(out_dir / ("%s__%s.export.json" % (launch_id, unit_id)), export), proofs, []


def export_text_set(text: Mapping[str, Any], launch_id: str, proven: Mapping[str, list],
                    out_dir: Path) -> tuple:
    """(export path, []) when every approved message sits in a saved SMS step, else (None, reasons).

    Proof is the provider's read-back of the workflow(s) of the automation(s) that elected the
    set: each approved body must be the body of a saved ``sms`` step that is not copy_pending."""
    set_id = text["id"]
    if text.get("state") != "ready":
        return None, list(text.get("blocked_by") or ["text set is blocked"])
    electing = [u for u in text.get("automations") or []]
    missing = [u for u in electing if u not in proven]
    if not electing or missing:
        return None, ["no delivered automation carries the set (elected by: %s; not delivered: %s)"
                      % (", ".join(electing) or "none", ", ".join(missing) or "none")]
    saved = [(u, p["workflow_id"], step) for u in electing for p in proven[u]
             for step in p["templates"]
             if isinstance(step, Mapping) and step.get("type") == "sms"
             and not (step.get("attributes") or {}).get("copy_pending")]
    categories = text.get("categories") or {}
    messages, reasons = [], []
    for step_id, body in sorted((text.get("bindings") or {}).get("sms_copy", {}).items()):
        hit = next((row for row in saved if (row[2].get("attributes") or {}).get("body") == body), None)
        if hit is None:
            reasons.append("message %s is not the body of any saved SMS step" % step_id)
            continue
        messages.append({"step_id": step_id, "category": categories.get(step_id),
                         "body_sha256": _sha256_bytes(body.encode("utf-8")),
                         "bound_in": {"unit": hit[0], "workflow_id": hit[1],
                                      "saved_step_id": hit[2].get("id")}})
    if reasons or not messages or (isinstance(text.get("messages"), int)
                                   and len(messages) != text["messages"]):
        return None, reasons or ["the set carries %r message(s), %d are saved"
                                 % (text.get("messages"), len(messages))]
    export = {
        "contract": SMS_SET_CONTRACT, "set_id": set_id, "status": "draft",
        "unit_key": "%s/%s" % (launch_id, set_id), "produced_by": BUILD_COMMAND,
        "profile_sha256": text.get("profile_sha256"), "messages": messages,
        "electing_units": sorted(electing),
    }
    return write_json(out_dir / ("%s__%s.sms-set.json" % (launch_id, set_id)), export), []


def delivery_row(path: Path, base_dir: Path, *, contract: str, launch_id: str, unit_id: str,
                 plan_sha256: str) -> dict:
    """One deliveries-file row. The artifact path is relative to ``base_dir`` (Skill 83's run dir)."""
    rel = os.path.relpath(path, base_dir)
    if rel.startswith("..") or os.path.isabs(rel):
        raise ValueError("%s is outside %s; put --journal and --deliveries-out in the same "
                         "directory tree (the Skill 83 run directory)" % (path.name, base_dir))
    data = Path(path).read_bytes()
    return {
        "state": "complete",
        "artifacts": [{"path": rel.replace(os.sep, "/"), "sha256": _sha256_bytes(data),
                       "size": len(data)}],
        "lane_validation": {"lane": LANE, "contract": contract, "state": "passed"},
        "request": {"launch_id": launch_id, "unit_id": unit_id, "plan_sha256": plan_sha256},
    }


def export_build(doc: Mapping[str, Any], campaign: Mapping[str, Any], stats: Mapping[str, Any], *,
                 journal: Any, read_templates, deliveries_path: str, launch_plan: str) -> dict:
    """Write exports + the deliveries file for every provable unit; name the refused ones."""
    launch_id = doc.get("launch_id")
    plan_sha = _sha256_bytes(Path(launch_plan).read_bytes())
    base = Path(deliveries_path).resolve().parent
    out_dir = Path(journal.path).resolve().parent / "exports"
    rows: dict = {}
    refused: dict = {}
    proven: dict = {}
    for build in doc.get("builds") or []:
        if not isinstance(build, Mapping) or not build.get("id"):
            continue
        unit_id = build["id"]
        path, proofs, reasons = export_unit(unit_id, launch_id, campaign, stats, journal,
                                            read_templates, out_dir)
        if reasons:
            refused[unit_id] = reasons
            continue
        try:
            rows[unit_id] = delivery_row(path, base, contract=EXPORT_CONTRACT,
                                         launch_id=launch_id, unit_id=unit_id, plan_sha256=plan_sha)
            proven[unit_id] = proofs
        except ValueError as exc:
            refused[unit_id] = [str(exc)]
    for text in doc.get("text_builds") or []:
        if not isinstance(text, Mapping) or not text.get("id"):
            continue
        set_id = text["id"]
        path, reasons = export_text_set(text, launch_id, proven, out_dir)
        if reasons:
            refused[set_id] = reasons
            continue
        try:
            rows[set_id] = delivery_row(path, base, contract=SMS_SET_CONTRACT, launch_id=launch_id,
                                        unit_id=set_id, plan_sha256=plan_sha)
        except ValueError as exc:
            refused[set_id] = [str(exc)]
    write_json(Path(deliveries_path), rows)
    return {"deliveries": str(deliveries_path), "units": sorted(rows), "refused": refused}
