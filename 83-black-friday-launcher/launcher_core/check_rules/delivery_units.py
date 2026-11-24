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
* SWB-081. A workflow that already existed (built in the browser, or an SMS-only unit the compiler has no
  workflow for) is delivered by Skill 44's ``caf workflows adopt``, whose export says ``produced_by``
  ``adopt`` and has NO reader hash. That producer is believed only when, for every workflow it lists:
  the saved graph passes Skill 44's validator, the graph hash recomputed here (``validate_graph.py hash``)
  equals the recorded one (and the export's ``expected_graph_hash`` for the primary), and a
  ``qc-<workflow_id>.json`` passes exactly as above AND carries a ``graph_hash`` equal to that hash (the
  QC graded this graph, not an earlier one). Any other ``produced_by`` is still refused.
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
* SWB-052. An installer receipt that nests the page under ``page`` and names no location is never
  edited: another unit writes a NEW ``skill83.page-install-restatement/v1`` receipt naming every
  fact top level plus the installer's own receipt by sha256. It counts only when that original is
  sealed in the same row, was written by the installer, records no publish and itself names this
  page and this exact draft, and when the GET read-back's own ``locationId`` is the location named.

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
# SWB-094: a page the owner ordered published. Same contract and same ids; a row says published true only
# with the owner's live-publication approval record sealed in the row (this role) and a read-back that shows
# the live top version, served on its public URL.
PAGE_LIVE_APPROVAL_ROLE = "live_publication_approval"
PAGE_LIVE_APPROVAL_TARGET = "approved_live_publication"
PAGE_ID_KEYS = ("page_id", "funnel_id", "step_id", "location_id", "draft_version_id",
                "installed_by", "read_by")
# SWB-052: an installer whose own receipt nests the page under "page" and names no location is restated
# (never edited) by another unit. The restatement is believed only through the installer's own receipt,
# sealed in the same row and matched by sha256, and the location only through the GET read-back.
PAGE_RESTATEMENT_SCHEMA = "skill83.page-install-restatement/v1"
_RESTATED_KEYS = ("page_id", "funnel_id", "step_id", "location_id", "draft_version_id",
                  "content_sha256", "installed_by")
BUILD_COMMAND = "caf workflows build --from-automation-build"
# SWB-081: the producer of a workflow that already existed and was adopted by `caf workflows adopt`.
# It is a different, honest producer: it is believed only through the graph validator, the real graph
# hash recomputed here and a signed passing QC result that names that exact hash.
ADOPT_PRODUCER = "adopt"
# An adopted workflow is recorded with the status it really has: it may already be published on the
# owner's order. The build command's own exports must still say draft.
ADOPT_STATUSES = ("draft", "published")
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


def qc_violations(label: str, workflow_id: str, artifacts: List[Any], root: Path,
                  graph_hash: Optional[str] = None) -> List[str]:
    """Why the unit carries no passing per-build QC result for ``workflow_id`` (empty = it does).

    ``graph_hash`` (an adopted workflow) also requires the QC to have graded that exact saved graph."""
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
    if graph_hash is not None and qc.get("graph_hash") != graph_hash:
        wrong.append(f"graph_hash is {qc.get('graph_hash')!r}, not the saved graph's {graph_hash!r} "
                     "(the graph was edited after this QC, or this QC graded another graph)")
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
    if facts.get("published") is True:
        # SWB-094: published is accepted ONLY through the owner's live-publication approval (its own law).
        return _page_live_violations(unit_id, row, root, label, facts, sha)
    if facts.get("published") is not False:
        wrong.append(f"page_install.published is {facts.get('published')!r}, not false: only an unpublished "
                     "DRAFT page is delivered by this contract (a published page needs the owner's "
                     "live-publication approval record in its row)")
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
    docs = []
    for art in installs:
        doc, why = _sealed_json(label, art, root)
        if why:
            return [why]
        if not isinstance(doc, Mapping):
            return [f"{label} install receipt {art.get('path')!r} is not a JSON object"]
        docs.append((art, doc))
    named = False
    restated = False
    for art, doc in docs:
        if doc.get("schema") == PAGE_RESTATEMENT_SCHEMA:
            why = _restatement_violation(label, art, doc, facts, sha, docs)
            if why:
                return [why]
            restated = True
            continue
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
    named = named or restated
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
    ) + ((("locationId (the location a restatement names is the one the GET returned)",
           page.get("locationId"), facts["location_id"]),) if restated else ())
    bad = [f"{name} is {got!r}, not {want!r}" for name, got, want in checks
           if got != want or type(got) is not type(want)]
    if bad:
        return [f"{label} the independent read-back does not show this draft: " + "; ".join(bad)]
    return []


def _page_live_violations(unit_id: str, row: Mapping[str, Any], root: Path, label: str,
                          facts: Mapping[str, Any], sha: str) -> List[str]:
    """SWB-094: why ``row`` is not a verified PUBLISHED page (empty = it is).

    A page that is live is recorded as live, never relabelled a draft. Nothing here weakens the draft law: a row
    with published false still goes through it. A row with published true needs ALL of:

    * the owner's live-publication approval record, sealed in the row (role ``live_publication_approval``), that
      is unrevoked, not a test record, writes ``approved_live_publication`` in this location, and names this page
      (and its funnel), and the row cites it by ``page_install.live_publication_approval_ref``;
    * the installer's receipt, sealed in the row, naming this page (the page may have been edited after install,
      so the installer's receipt is believed only for who built it, never for the live bytes);
    * one independent read-back, by a different unit, read by GET, showing the page's top version is the LIVE
      version with this version id and content sha256, not deleted, and the public URL answering 200.
    """
    wrong: List[str] = []
    ref = facts.get("live_publication_approval_ref")
    if not lp._nonempty_str(ref):
        wrong.append("page_install.live_publication_approval_ref is missing")
    url = facts.get("public_url")
    if not (lp._nonempty_str(url) and str(url).startswith("https://")):
        wrong.append("page_install.public_url is not an https URL")
    status = facts.get("public_http_status")
    if status != 200 or type(status) is not int:
        wrong.append(f"page_install.public_http_status is {status!r}, not 200")
    if lp._nonempty_str(facts.get("installed_by")) and facts.get("installed_by") == facts.get("read_by"):
        wrong.append("read_by is the installer itself: the read-back must be independent")
    if lp._nonempty_str(row.get("location_id")) and facts.get("location_id") != row.get("location_id"):
        wrong.append(f"page_install.location_id {facts.get('location_id')!r} is not the launch's "
                     f"{row.get('location_id')!r}")
    if wrong:
        return [f"{label} page_install is not a verifiable published page: " + "; ".join(wrong)]

    artifacts = [a for a in (row.get("artifacts") or []) if isinstance(a, Mapping)]
    approvals = [a for a in artifacts if a.get("role") == PAGE_LIVE_APPROVAL_ROLE]
    installs = [a for a in artifacts if a.get("role") == PAGE_INSTALL_ROLE]
    readbacks = [a for a in artifacts if a.get("role") == PAGE_READBACK_ROLE]
    if len(approvals) != 1:
        return [f"{label} a published page carries {len(approvals)} {PAGE_LIVE_APPROVAL_ROLE!r} artifacts, "
                "not exactly one (the owner's live-publication approval record)"]
    if not installs:
        return [f"{label} carries no {PAGE_INSTALL_ROLE!r} artifact"]
    if len(readbacks) != 1:
        return [f"{label} carries {len(readbacks)} {PAGE_READBACK_ROLE!r} artifacts, not exactly one"]

    approval, why = _sealed_json(label, approvals[0], root)
    if why:
        return [why]
    if not isinstance(approval, Mapping):
        return [f"{label} the live-publication approval is not a JSON object"]
    pages = approval.get("page_ids")
    bad = [f"{name} is {got!r}, not {want!r}" for name, got, want in (
        ("approval_ref", approval.get("approval_ref"), ref),
        ("allowed_write_target", approval.get("allowed_write_target"), PAGE_LIVE_APPROVAL_TARGET),
        ("test_only", approval.get("test_only"), False),
        ("revoked", approval.get("revoked"), False),
        ("location_id", approval.get("location_id"), facts["location_id"])) if got != want
        or type(got) is not type(want)]
    if not (isinstance(pages, list) and facts["page_id"] in pages):
        bad.append(f"page_ids does not name page {facts['page_id']!r}")
    if approval.get("funnel_id") not in (None, facts["funnel_id"]):
        bad.append(f"funnel_id is {approval.get('funnel_id')!r}, not {facts['funnel_id']!r}")
    words = approval.get("owner_words")
    if not (isinstance(words, list) and any(lp._nonempty_str(w) for w in words)):
        bad.append("owner_words carries none of the owner's own words")
    if bad:
        return [f"{label} the live-publication approval does not cover this page: " + "; ".join(bad)]

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
        if facts["page_id"] in _strings(doc) and doc.get("unit") == facts["installed_by"]:
            named = True
    if not named:
        return [f"{label} no install receipt written by {facts['installed_by']!r} names page "
                f"{facts['page_id']!r}"]

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
    served = page.get("public") if isinstance(page.get("public"), Mapping) else {}
    checks = (
        ("read-back unit", doc.get("unit"), facts["read_by"]),
        ("read-back location_id", doc.get("location_id"), facts["location_id"]),
        ("read_at present", lp._nonempty_str(doc.get("read_at")), True),
        ("read by GET", isinstance(method, str) and "GET" in method, True),
        ("http_status", page.get("http_status"), 200),
        ("page_id", page.get("page_id"), facts["page_id"]),
        ("funnelId", page.get("funnelId"), facts["funnel_id"]),
        ("stepId", page.get("stepId"), facts["step_id"]),
        ("locationId", page.get("locationId"), facts["location_id"]),
        ("deleted", page.get("deleted"), False),
        ("top_version.pageType", top.get("pageType"), "live"),
        ("top_version.versionId", top.get("versionId"), facts["draft_version_id"]),
        ("top_version.blob_sha256", top.get("blob_sha256"), sha),
        ("public.url", served.get("url"), url),
        ("public.http_status", served.get("http_status"), 200),
    )
    bad = [f"{name} is {got!r}, not {want!r}" for name, got, want in checks
           if got != want or type(got) is not type(want)]
    if bad:
        return [f"{label} the independent read-back does not show this page live: " + "; ".join(bad)]
    return []


def _restatement_violation(label: str, art: Mapping[str, Any], doc: Mapping[str, Any],
                           facts: Mapping[str, Any], sha: str, docs: List[Any]) -> Optional[str]:
    """SWB-052: why a restated install receipt does not prove this draft (None = it does).

    The restatement names every page fact top level and the installer's own receipt by sha256. That
    receipt must be sealed in the same row, be written by the installer, record no publish, and itself
    name this page id and this exact draft (version id or content sha256). The restating unit is never
    the installer. The location it names is held to the GET read-back's own locationId by the caller."""
    where = f"{label} restated install receipt {art.get('path')!r}"
    author = doc.get("unit")
    if not lp._nonempty_str(author) or author == facts["installed_by"]:
        return f"{where} must be written by a unit other than the installer it restates"
    if doc.get("published") is not False:
        return f"{where} does not record published false"
    wrong = [key for key in _RESTATED_KEYS if doc.get(key) != facts.get(key)]
    if wrong:
        return f"{where} does not name this draft: " + ", ".join(wrong)
    source = doc.get("source_receipt")
    digest = source.get("sha256") if isinstance(source, Mapping) else None
    match = [d for a, d in docs if a is not art and a.get("sha256") == digest
             and d.get("schema") != PAGE_RESTATEMENT_SCHEMA]
    if not (isinstance(digest, str) and match):
        return (f"{where} names no source_receipt sealed in this row (the installer's own receipt, "
                "matched by sha256)")
    original = match[0]
    if original.get("unit") != facts["installed_by"]:
        return f"{where} restates a receipt written by {original.get('unit')!r}, not {facts['installed_by']!r}"
    if original.get("published") is True:
        return f"{where} restates a receipt that records a publish"
    text = _strings(original)
    if facts["page_id"] not in text or not (facts["draft_version_id"] in text or sha in text):
        return (f"{where} restates a receipt that does not name page {facts['page_id']!r} and its draft "
                f"(version {facts['draft_version_id']!r} or content {sha})")
    return None


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


def _run_graph_tool(validator: Path, subcommand: str, templates: Any):
    """(exit code, stdout) of Skill 44's validate_graph.py ``subcommand`` on a transient graph file."""
    with tempfile.TemporaryDirectory(prefix="adopt-graph-") as td:
        probe = Path(td) / "graph.json"
        probe.write_text(json.dumps({"templates": templates}), encoding="utf-8")
        done = subprocess.run([sys.executable, "-I", str(validator), subcommand, "--export", str(probe)],
                              capture_output=True, text=True, timeout=VALIDATOR_TIMEOUT_S)
    return done.returncode, done.stdout.strip()


def adopt_violations(label: str, unit_id: str, export: Mapping[str, Any], validator: Path,
                     artifacts: List[Any], root: Path) -> List[str]:
    """SWB-081: why an ``adopt`` export is not an honest adoption of passing, QC'd draft workflows.

    No reader hash exists for a workflow nobody compiled, so nothing is taken on the export's word:
    every member's graph is re-validated by Skill 44's validator, its hash is recomputed here and must
    equal the one recorded, and every member needs a passing signed QC naming that same hash."""
    members = export.get("workflows")
    if not (isinstance(members, list) and members and all(isinstance(m, Mapping) for m in members)):
        return [f"{label} adopt export lists no workflows"]
    ids = [m.get("workflow_id") for m in members]
    if not all(lp._nonempty_str(i) for i in ids) or len(set(ids)) != len(ids):
        return [f"{label} adopt export names a workflow twice or without an id"]
    if ids[0] != export.get("workflow_id"):
        return [f"{label} adopt export's workflow_id is not its first workflow"]
    if members[0].get("templates") != export.get("templates"):
        return [f"{label} adopt export's graph is not its first workflow's saved graph"]
    out: List[str] = []
    for member in members:
        wid = member["workflow_id"]
        if member.get("status") not in ADOPT_STATUSES:
            out.append(f"{label} adopted workflow {wid!r} status is {member.get('status')!r}, "
                       f"not one of {', '.join(ADOPT_STATUSES)}")
            continue
        nodes = member.get("templates")
        if not (isinstance(nodes, list) and nodes):
            out.append(f"{label} adopted workflow {wid!r} carries no saved graph")
            continue
        try:
            code, _ = _run_graph_tool(validator, "graph", nodes)
            hcode, recomputed = _run_graph_tool(validator, "hash", nodes)
        except (OSError, subprocess.SubprocessError) as exc:
            out.append(f"{label} Skill 44 graph validator could not run ({type(exc).__name__})")
            continue
        if code != 0:
            out.append(f"{label} Skill 44 graph validator refused adopted workflow {wid!r} (exit {code})")
            continue
        if hcode != 0 or not recomputed or member.get("graph_hash") != recomputed:
            out.append(f"{label} adopted workflow {wid!r} graph_hash is not the hash of its saved graph")
            continue
        if wid == export.get("workflow_id") and export.get("expected_graph_hash") != recomputed:
            out.append(f"{label} adopt export's expected_graph_hash is not the hash of its saved graph")
            continue
        out += qc_violations(f"{label} workflow {wid!r}", wid, artifacts, root, graph_hash=recomputed)
    return out


def automation_violations(unit_id: str, row: Any, launch_id: Any, expected: Mapping[str, str],
                          root: Path) -> List[str]:
    """Why ``row`` (a receipt row or a lane delivery) is not a Skill 44 build of ``unit_id``."""
    label = f"{CODE_AUTOMATION}: unit {unit_id!r}"
    root = Path(root)
    if not isinstance(row, Mapping):
        return [f"{label} has no delivery receipt row"]
    reader = expected.get(unit_id)
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

    adopted = export.get("produced_by") == ADOPT_PRODUCER
    if not adopted and not reader:
        return [f"{label} has no ready build in the Skill 44 reader output ({BUILDS_DOC}); "
                "its expected_graph_hash cannot be compared"]
    wrong = []
    if not lp._nonempty_str(export.get("workflow_id")):
        wrong.append("no workflow_id")
    if adopted:
        if export.get("status") not in ADOPT_STATUSES:
            wrong.append(f"status is {export.get('status')!r}, not one of {', '.join(ADOPT_STATUSES)}")
    elif export.get("status") != "draft":
        wrong.append(f"status is {export.get('status')!r}, not 'draft'")
    if export.get("unit_key") != f"{launch_id}/{unit_id}":
        wrong.append(f"unit_key is {export.get('unit_key')!r}, not '{launch_id}/{unit_id}'")
    if not adopted:
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
    if adopted:
        return adopt_violations(label, unit_id, export, validator, artifacts, root)
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
