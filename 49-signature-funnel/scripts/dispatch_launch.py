#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dispatch_launch.py — turn an APPROVED launch plan into specialist page
requests (spec 06 S49-07; contracts doc 02 §7, schemas page-request 1.0).

Q12 REVISION (schema 1.1, S49): when the launch record names a
prompt_policy_id (brand-group field, plan-approved content bound by the
plan document hash), build_requests stamps it into emitted requests
and marks those requests schema_version "1.1" (page-request.v1.1 schema,
1.0 preserved). When the record names none, the emitted requests are
byte-identical 1.0 requests. No policy values are minted here: the id is
copied from the record verbatim, never invented per run, and never
supplied by a CLI flag, a run-dir config key, or a function parameter
(copy_profile's parameter path is the anti-pattern: it is not plan-bound).
validate_request applies the same rule in reverse: a "1.1" request must
carry the field, and a "1.0" request must not.

PP-T2 REVISION (per-role adoption switch, S49; adoption map section 2.1):
the Q12 stamp above is no longer global. build_requests emits the 1.1
shape for a role ONLY when the record names a prompt_policy_id AND that
role's state in the adoption file (49-signature-funnel/
prompt-policy-adoption.json, repo state owned by S49) is "ready"; every
other role receives exactly the 1.0 request, with no prompt_policy_id
key. A role missing from the file, a state outside the vocabulary, or an
unreadable adoption file all mean NOT ready (fail toward 1.0, never
toward 1.1). The adoption file controls emission SHAPE only: it never
supplies, alters, or defaults the policy id, which still comes only
from the approved launch record exactly as the Q12 revision built it,
and readiness is never taken from a CLI flag, a run-dir config key, or
a function parameter; it changes only by editing the adoption file in
the repo, through the flip procedure. After the Question 1 ruling the
id is a citation of the one governing policy (the KIE rule-12 band),
not a selector; the switch exists as consumer-contract protection,
because a 1.1-shaped request breaks consumer schemas that are still
closed (additionalProperties: false), and for no other reason. The
dispatch manifest records a prompt_policy_adoption block (per role: the
state read, the emitted schema_version, the evidence_ref behind
"ready") so receipts prove after the fact which roles ran 1.1 and on
what evidence. validate_request is unchanged: it already dual-accepts.

MODES (explicit, never inferred):
  * ``page_only`` (default, byte-identical to the pre-mode behaviour): the
    approved plan's page requests are emitted and, when an executor is
    supplied, the page lanes run. A full launch plan supplied in this mode
    is NOT dispatched; the manifest records that fact so nothing is
    silently dropped.
  * ``turnkey_launch``: the FULL approved launch plan (pages, email
    sequences, text sets, automations and the requested Conversation AI)
    must be supplied. Every unit must have a registered lane adapter
    (page units use the existing page-role adapters; a non-page unit uses
    the adapter registered under its own plan unit id). Dispatch refuses
    by name when one is missing. It writes a durable progress file before
    and after every unit, resumes a re-dispatch without rebuilding units
    whose input hash has not changed, and accepts a lane result only after
    collect_launch_receipts.validate_result echoes the lane request. Page
    lanes still run through the existing page_swarm scheduler with its
    spend ledger, KIE limiter and worker profile; lane units run in
    waits_for order, independent ones side by side.

FAIL-CLOSED, in this order:
  1. The launch record must validate (validate_launch_plan) and its status
     must be approved/building.
  2. The plan-approval gate must pass for the CURRENT record
     (assert_plan_build_approved): hash binding, client identity, no worker
     self-approval, not revoked/expired.
  3. The route graph is RE-COMPILED from the record and must hash to the
     record's route_graph_hash — dispatch never trusts a stored graph.
  4. Write target discipline: local_only needs nothing more;
     approved_test_location needs a test_location_use approval;
     approved_live_publication needs test_location_use + page_publication
     approvals. Every scoped approval passes the SAME gate discipline as
     the plan approval (assert_scoped_approval): separate type, scope
     containing the type, plan-hash binding, client identity, no worker
     self-approval, provenance reference, revocation, expiry. Approvals
     are never inferred from the plan approval.

One idempotent page request per launch revision + page role. The dispatch
key is tenant + launch + revision + role + request hash: rebuilding the
same approved plan yields byte-identical requests, so a re-dispatch is a
no-op the consumer can dedupe, never a duplicate build.

EMISSION IS NOT EXECUTION. With no executor adapter configured this tool
writes the requests plus a dispatch manifest marked emitted_not_executed
and stops. A consumer adapter (S49-08, built with the owning skills' real
entrypoints) executes a request and returns a page-result (schema 1.0);
collect_launch_receipts.py aggregates those results into checkpoints.
The --simulate-executor flag exists for tests only and stamps every
result test_only with proof class L0.

Deterministic, stdlib only. Exit 0 ok, 2 violation, 3 usage/fail-closed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compile_launch_route as clr  # noqa: E402
import page_set as pset  # noqa: E402
import page_swarm as swarm  # noqa: E402
import validate_launch_plan as vlp  # noqa: E402

EXIT_OK = 0
EXIT_VIOLATION = 2
EXIT_FAILCLOSED = 3

WRITE_TARGETS = ("local_only", "approved_test_location", "approved_live_publication")

MODE_PAGE_ONLY = "page_only"
MODE_TURNKEY_LAUNCH = "turnkey_launch"
DISPATCH_MODES = (MODE_PAGE_ONLY, MODE_TURNKEY_LAUNCH)
# Non-page plan sections whose units a lane adapter must build. The page
# section is served by the existing page-role adapters, never by a lane id.
LANE_SECTIONS = ("email_sequences", "text_sets", "automations")
PLAN_SECTIONS = ("pages",) + LANE_SECTIONS
CONVERSATION_AI_UNIT = "conversation_ai"
PLAN_SCHEMA_VERSION = "1.0.0"
PROGRESS_SCHEMA = "signature-launch-dispatch-progress/v1"

ADOPTION_SCHEMA = "signature-launch-prompt-policy-adoption/v1"
ADOPTION_STATES = ("not_ready", "ready", "never_by_design",
                   "blocked_no_consumer")
# The adoption file lives at the skill root, one level above this scripts
# directory (49-signature-funnel/prompt-policy-adoption.json). It is repo
# state, changed only by the flip procedure's commit (adoption map
# section 2.3); dispatch never takes readiness from a CLI flag, a run-dir
# config key, or a function parameter, and the file can never supply the
# policy id. Tests rebind ADOPTION_FILE to a fixture copy.
ADOPTION_FILE = (Path(__file__).resolve().parent.parent
                 / "prompt-policy-adoption.json")
_NOT_READY = {"state": "not_ready", "evidence_ref": None}


class DispatchError(ValueError):
    pass


# Fix 15 — ONE page-type vocabulary, published once. The matrix/profiles use the
# funnel slugs (main, upsell, downsell, upsell-2, downsell-2, thank-you, checkout)
# while the dispatch contract speaks page_roles (landing, ... thank_you). The
# mapping lives in exactly one place, structure/funnel_structure.json's
# page_role_map block, and this module READS it instead of re-spelling either
# vocabulary. Fail closed: a missing or malformed table is a DispatchError (the
# role vocabulary cannot be guessed); a role set that disagrees with the fixed
# role -> skill assignment is refused at import so the two can never drift apart.
PAGE_ROLE_MAP_CONTRACT = "signature-funnel-page-role-map/v1"
PAGE_ROLE_MAP_FILE = (Path(__file__).resolve().parent.parent
                      / "structure" / "funnel_structure.json")


def _load_page_role_map() -> Dict[str, Any]:
    """Read the one page_type -> page_role table (funnel_structure.json)."""
    try:
        doc = json.loads(PAGE_ROLE_MAP_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DispatchError(
            f"cannot read the page-role map {PAGE_ROLE_MAP_FILE}: {exc}"
        ) from exc
    table = doc.get("page_role_map") if isinstance(doc, dict) else None
    if not isinstance(table, dict):
        raise DispatchError(
            f"{PAGE_ROLE_MAP_FILE} carries no page_role_map block")
    if table.get("contract") != PAGE_ROLE_MAP_CONTRACT:
        raise DispatchError(
            f"page_role_map contract is {table.get('contract')!r}, expected "
            f"{PAGE_ROLE_MAP_CONTRACT!r}")
    roles = table.get("page_roles")
    types = table.get("page_types")
    if (not isinstance(roles, list) or not roles
            or len(set(roles)) != len(roles)
            or not all(isinstance(r, str) and r for r in roles)):
        raise DispatchError(
            "page_role_map.page_roles must be a non-empty list of unique "
            "page_role strings")
    if not isinstance(types, dict) or not types:
        raise DispatchError("page_role_map.page_types must be a non-empty map")
    for page_type, row in types.items():
        if not isinstance(row, dict) or row.get("page_role") not in roles:
            raise DispatchError(
                f"page_type {page_type!r} does not map onto a declared "
                "page_role")
    return table

PAGE_ROLE_MAP = _load_page_role_map()
PAGE_ROLES = tuple(PAGE_ROLE_MAP["page_roles"])
PAGE_TYPE_TO_ROLE = {page_type: row["page_role"]
                     for page_type, row in PAGE_ROLE_MAP["page_types"].items()}
# A page type with its own canonical sections names its copy profile here; every other role takes
# the launch's copy_profile (standard or long_form) exactly as before. The value is the copy_version
# of that page type's spec in Skill 71 (71-blackceo-signature-page/references/copy-specs/
# thank-you-v1.json), which Skill 71's launch import maps to the run's copy_version. Kept out of
# structure/funnel_structure.json on purpose: that file is hash-pinned enforcement core.
ROLE_COPY_PROFILE = {"thank_you": "thank-you"}

ROLE_SKILL = {"landing": 71, "product_selection": 78, "checkout": 79,
              "upsell_1": 80, "downsell_1": 81, "upsell_2": 80, "thank_you": 82}
ROLE_OFFERS = {"landing": ("main",), "product_selection": ("main",),
               "checkout": ("main", "bump"), "upsell_1": ("upsell_1",),
               "downsell_1": ("downsell_1",), "upsell_2": ("upsell_2",),
               "thank_you": ("main", "bump", "upsell_1", "downsell_1", "upsell_2")}

if set(ROLE_SKILL) != set(PAGE_ROLES):
    raise DispatchError(
        "dispatch role -> skill map and page_role_map.page_roles disagree: "
        f"{sorted(set(ROLE_SKILL) ^ set(PAGE_ROLES))}")


def _read_adoption() -> Tuple[Dict[str, Dict[str, Any]], str]:
    """Read the per-role adoption file (adoption map section 2.1 rule 1).

    Returns (decisions, file_status): decisions maps every dispatch role
    to {"state", "evidence_ref"} holding the EFFECTIVE state for this
    run, and file_status is "loaded" or "unreadable". Fail toward 1.0 at
    every layer: a missing, unparseable, or wrongly shaped file makes
    every role not ready; a role missing from the file, an entry that is
    not an object, or a state value outside the vocabulary makes that
    role not ready. Nothing here raises, because 1.0 is always
    emittable and an adoption-file failure must never widen emission."""
    try:
        doc = json.loads(ADOPTION_FILE.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) \
                or doc.get("schema") != ADOPTION_SCHEMA \
                or not isinstance(doc.get("roles"), dict):
            raise ValueError("adoption file does not have the v1 shape")
        entries = doc["roles"]
    except (OSError, ValueError):
        return ({role: dict(_NOT_READY) for role in ROLE_SKILL},
                "unreadable")
    decisions: Dict[str, Dict[str, Any]] = {}
    for role in ROLE_SKILL:
        entry = entries.get(role)
        if isinstance(entry, dict) \
                and entry.get("state") in ADOPTION_STATES:
            ref = entry.get("evidence_ref")
            decisions[role] = {
                "state": entry["state"],
                "evidence_ref": ref if isinstance(ref, str) else None}
        else:
            decisions[role] = dict(_NOT_READY)
    return decisions, "loaded"


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def request_input_hash(launch: Dict[str, Any], page_id: str, role: str) -> str:
    return hashlib.sha256(_canonical({
        "plan_document_hash": vlp.plan_document_hash(launch),
        "route_graph_hash": launch["route_graph_hash"],
        "page_id": page_id, "page_role": role,
        "revision": launch["revision"]})).hexdigest()


def dispatch_key(launch: Dict[str, Any], role: str, input_hash: str) -> str:
    return (f"{launch['tenant_id']}:{launch['launch_id']}:"
            f"rev{launch['revision']}:{role}:{input_hash[:16]}")


def build_requests(launch: Dict[str, Any], graph: Dict[str, Any], *,
                   copy_profile: str,
                   allowed_write_target: str) -> List[Dict[str, Any]]:
    if allowed_write_target not in WRITE_TARGETS:
        raise DispatchError(f"allowed_write_target {allowed_write_target!r} "
                            "is not a write target")
    if "prompt_policy_id" in launch:
        policy_id = launch["prompt_policy_id"]
        if not isinstance(policy_id, str) or not policy_id.strip():
            raise DispatchError(
                "launch record prompt_policy_id, when the key is present, "
                "must be a non-empty string — null or blank is refused; "
                "omit the key entirely when no policy governs (absence is "
                "the only encoding of 'no policy': absent, null, and a "
                "value are three different plan hashes)")
    else:
        policy_id = None
    decisions, _adoption_status = _read_adoption()
    offer_ids = {}
    for o in launch["offers"]:
        offer_ids.setdefault(o["slot"], []).append(o["offer_id"])
    requests: List[Dict[str, Any]] = []
    for node in graph["nodes"]:
        role = node["role"]
        ih = request_input_hash(launch, node["page_id"], role)
        refs: List[str] = []
        for slot in ROLE_OFFERS[role]:
            refs.extend(offer_ids.get(slot, []))
        # PP-T2 emission rule (adoption map section 2.1 rule 2): the 1.1
        # shape is emitted for this role only when the record names a
        # policy id AND the role's adoption state is "ready". The switch
        # gates shape only; the id stamped is the record's, verbatim.
        decision = decisions.get(role) or _NOT_READY
        stamp = bool(policy_id) and decision["state"] == "ready"
        requests.append({
            "schema_version": "1.1" if stamp else "1.0",
            "tenant_id": launch["tenant_id"],
            "location_id": launch["location_id"],
            "launch_id": launch["launch_id"],
            "revision": launch["revision"],
            "request_id": dispatch_key(launch, role, ih),
            "page_id": node["page_id"],
            "page_role": role,
            "assigned_skill": ROLE_SKILL[role],
            "approval_ref": launch["plan_approval_ref"],
            "input_hash": ih,
            "brand_ref": launch["brand_ref"],
            "brand_hash": launch["brand_hash"],
            "route_graph_ref": launch["route_graph_ref"],
            "route_graph_hash": launch["route_graph_hash"],
            "offer_refs": refs,
            "copy_profile": ROLE_COPY_PROFILE.get(role, copy_profile),
            **({"prompt_policy_id": policy_id} if stamp else {}),
            "allowed_write_target": allowed_write_target,
            "test_only": bool(launch["test_only"]),
        })
    return requests


_REQUEST_FIELDS = ("schema_version", "tenant_id", "location_id", "launch_id",
                   "revision", "request_id", "page_id", "page_role",
                   "assigned_skill", "approval_ref", "input_hash", "brand_ref",
                   "brand_hash", "route_graph_ref", "route_graph_hash",
                   "offer_refs", "copy_profile", "allowed_write_target",
                   "test_only")


def validate_request(req: Dict[str, Any]) -> List[str]:
    fails = [f"request missing field {f!r}" for f in _REQUEST_FIELDS
             if f not in req]
    if fails:
        return fails
    if req["schema_version"] not in ("1.0", "1.1"):
        fails.append("request schema_version is not 1.0 or 1.1")
    elif req["schema_version"] == "1.1":
        pid = req.get("prompt_policy_id")
        if not isinstance(pid, str) or not pid.strip():
            fails.append("a 1.1 request must carry a non-empty "
                         "prompt_policy_id (the 1.1 label exists to carry "
                         "the field)")
    elif "prompt_policy_id" in req:
        fails.append("prompt_policy_id requires request schema_version "
                     "1.1 (the 1.0 schema forbids the field)")
    if req["page_role"] not in ROLE_SKILL:
        fails.append(f"unknown page_role {req['page_role']!r}")
    elif req["assigned_skill"] != ROLE_SKILL[req["page_role"]]:
        fails.append(f"page_role {req['page_role']} must be assigned to skill "
                     f"{ROLE_SKILL[req['page_role']]}, not {req['assigned_skill']}")
    if req["allowed_write_target"] not in WRITE_TARGETS:
        fails.append("allowed_write_target is not valid")
    return fails


# ---------------------------------------------------------------------------
# turnkey_launch — the full plan, its lane adapters, durable progress, receipts
# ---------------------------------------------------------------------------
def plan_units(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every unit of a full launch plan in contract order, with its section.

    The Conversation AI is one unit when the client requested it; a plan that
    does not request it has no such unit (a lane is never invented)."""
    units: List[Dict[str, Any]] = []
    for section in PLAN_SECTIONS:
        for unit in plan.get(section) or []:
            units.append({"section": section, "id": unit["id"], "unit": unit})
    ai = plan.get(CONVERSATION_AI_UNIT) or {}
    if ai.get("requested"):
        units.append({"section": CONVERSATION_AI_UNIT, "id": CONVERSATION_AI_UNIT,
                      "unit": {"id": CONVERSATION_AI_UNIT, "waits_for": [],
                               "conversation_ai": ai}})
    return units


def validate_turnkey_plan(plan: Any, launch: Dict[str, Any],
                          page_keys: Sequence[str]) -> List[str]:
    """Fail-closed checks for a FULL plan before a turnkey run starts.

    A missing section, a duplicate unit id, a dangling wait, a non-draft unit,
    a page the plan does not account for, or a Conversation AI that requests
    without a mode all block by name. Nothing here builds or defaults a unit."""
    if not isinstance(plan, dict):
        return ["the launch plan is not an object"]
    fails: List[str] = []
    if plan.get("state") not in (None, "ready"):
        fails.append(f"the launch plan state is {plan.get('state')!r}, not ready")
    if plan.get("schema_version") != PLAN_SCHEMA_VERSION:
        fails.append(f"the launch plan schema_version is {plan.get('schema_version')!r}, "
                     f"expected {PLAN_SCHEMA_VERSION!r}")
    if plan.get("launch_id") != launch["launch_id"]:
        fails.append("the launch plan launch_id does not match the launch record")
    for section in PLAN_SECTIONS:
        value = plan.get(section)
        if not isinstance(value, list):
            fails.append(f"the launch plan carries no {section} list")
    ai = plan.get(CONVERSATION_AI_UNIT)
    if not isinstance(ai, dict):
        fails.append("the launch plan carries no conversation_ai block")
    elif bool(ai.get("requested")) != (ai.get("mode") not in (None, "none")):
        fails.append("conversation_ai requested and mode disagree")
    if fails:
        return fails
    ids: List[str] = []
    for item in plan_units(plan):
        ids.append(item["id"])
        if item["section"] != CONVERSATION_AI_UNIT:
            unit = item["unit"]
            if not isinstance(unit.get("id"), str) or not unit["id"].strip():
                fails.append(f"a {item['section']} unit has no id")
            waits = unit.get("waits_for", [])
            if not isinstance(waits, list):
                fails.append(f"{item['id']}: waits_for is not a list")
            elif item["section"] in LANE_SECTIONS and unit.get("draft_only") is not True:
                fails.append(f"{item['id']}: is not draft_only")
    if len(set(ids)) != len(ids):
        fails.append("the launch plan has duplicate unit ids")
    known = set(ids)
    for item in plan_units(plan):
        for wait in (item["unit"].get("waits_for") or []):
            if wait not in known:
                fails.append(f"{item['id']}: waits_for unknown unit {wait!r}")
            elif wait == item["id"]:
                fails.append(f"{item['id']}: waits_for itself")
    planned_pages = {u["id"] for u in plan.get("pages") or []}
    expected_pages = {f"page_{key}" for key in page_keys}
    for missing in sorted(expected_pages - planned_pages):
        fails.append(f"the launch plan does not account for page unit {missing!r}")
    for extra in sorted(planned_pages - expected_pages):
        fails.append(f"the launch plan names page unit {extra!r} that this page set "
                     "does not build")
    return fails


def _unit_input_hash(launch: Dict[str, Any], unit_id: str, unit: Any) -> str:
    return hashlib.sha256(_canonical({
        "plan_document_hash": vlp.plan_document_hash(launch),
        "launch_id": launch["launch_id"], "revision": launch["revision"],
        "unit_id": unit_id, "unit": unit})).hexdigest()


def _lane_request(launch: Dict[str, Any], item: Dict[str, Any],
                  input_hash: str) -> Dict[str, Any]:
    """The request a lane adapter answers. It echoes page-result identity so
    collect_launch_receipts can bind the result to this exact unit and plan."""
    return {
        "schema_version": "1.0",
        "tenant_id": launch["tenant_id"], "location_id": launch["location_id"],
        "launch_id": launch["launch_id"], "revision": launch["revision"],
        "request_id": (f"{launch['tenant_id']}:{launch['launch_id']}:"
                       f"rev{launch['revision']}:{item['id']}:{input_hash[:16]}"),
        "input_hash": input_hash, "page_id": item["id"],
        "section": item["section"], "unit": item["unit"],
        "test_only": bool(launch["test_only"]),
        "allowed_write_target": "local_only",
    }


class Progress:
    """Durable per-unit progress: written after every state change, atomically.

    A unit is skipped only when it is ``done`` AND its recorded input hash
    still matches the plan, so a changed plan rebuilds the changed units and
    nothing else. A corrupt or absent file starts empty; it never blocks."""
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self.doc: Dict[str, Any] = {"schema": PROGRESS_SCHEMA, "units": {}}
        if self.path.is_file():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict) and loaded.get("schema") == PROGRESS_SCHEMA \
                        and isinstance(loaded.get("units"), dict):
                    self.doc = loaded
            except (OSError, ValueError):
                pass

    def state(self, unit_id: str) -> Dict[str, Any]:
        entry = self.doc["units"].get(unit_id)
        return entry if isinstance(entry, dict) else {}

    def should_skip(self, unit_id: str, input_hash: str) -> bool:
        entry = self.state(unit_id)
        result_path = entry.get("result_path")
        if entry.get("status") != "done" or entry.get("input_hash") != input_hash:
            return False
        if not result_path:
            return False
        path = Path(result_path)
        if not path.is_file():
            return False
        try:
            return hashlib.sha256(path.read_bytes()).hexdigest() == \
                entry.get("result_sha256")
        except OSError:
            return False

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.doc, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
        os.replace(tmp, self.path)

    def mark(self, unit_id: str, *, status: str, input_hash: str,
             section: str, result_path: Optional[Path] = None,
             error: Optional[str] = None) -> None:
        with self._lock:
            entry = {"status": status, "input_hash": input_hash,
                     "section": section}
            if result_path is not None and Path(result_path).is_file():
                entry["result_path"] = str(result_path)
                entry["result_sha256"] = hashlib.sha256(
                    Path(result_path).read_bytes()).hexdigest()
            if error:
                entry["error"] = error
            self.doc["units"][unit_id] = entry
            self._write()


def _adapter_command(command: Sequence[Any], *, request_path: Path,
                     result_path: Path, work_dir: Path, unit_id: str) -> List[str]:
    return [str(part).replace("{request}", str(request_path))
                    .replace("{result}", str(result_path))
                    .replace("{work_dir}", str(work_dir))
                    .replace("{unit}", unit_id)
            for part in command]


def _run_lane(item: Dict[str, Any], *, launch: Dict[str, Any],
              adapter: Dict[str, Any], work_dir: Path, progress: Progress,
              receipts) -> Dict[str, Any]:
    """Run one lane adapter, accept only a receipt-valid echo, record progress."""
    import subprocess
    unit_id = item["id"]
    ih = _unit_input_hash(launch, unit_id, item["unit"])
    request = _lane_request(launch, item, ih)
    request_path = work_dir / f"lane-request-{unit_id}.json"
    result_path = work_dir / f"lane-result-{unit_id}.json"
    if result_path.is_file():  # never answer a unit over an older answer's bytes
        result_path.unlink()
    request_path.write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")
    progress.mark(unit_id, status="running", input_hash=ih, section=item["section"])
    cmd = _adapter_command(adapter["command"], request_path=request_path,
                           result_path=result_path, work_dir=work_dir,
                           unit_id=unit_id)
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          timeout=float(adapter.get("timeout_s", 600)))
    if proc.returncode != 0:
        error = f"lane adapter exited {proc.returncode}: {proc.stderr.strip()[:400]}"
        progress.mark(unit_id, status="failed", input_hash=ih,
                      section=item["section"], error=error)
        raise DispatchError(f"{unit_id}: {error}")
    if not result_path.is_file():
        error = f"lane adapter produced no result file at {result_path}"
        progress.mark(unit_id, status="failed", input_hash=ih,
                      section=item["section"], error=error)
        raise DispatchError(f"{unit_id}: {error}")
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        error = f"lane result is not JSON: {exc}"
        progress.mark(unit_id, status="failed", input_hash=ih,
                      section=item["section"], error=error)
        raise DispatchError(f"{unit_id}: {error}")
    fails = receipts.validate_result(result, request)
    if fails:
        error = "lane result failed receipt validation: " + "; ".join(fails)
        progress.mark(unit_id, status="failed", input_hash=ih,
                      section=item["section"], error=error)
        raise DispatchError(f"{unit_id}: {error}")
    progress.mark(unit_id, status="done", input_hash=ih,
                  section=item["section"], result_path=result_path)
    return {"unit_id": unit_id, "section": item["section"],
            "request_id": request["request_id"], "input_hash": ih,
            "status": result["status"], "proof_class": result["proof_class"],
            "result_path": str(result_path), "result": result}


def _run_lane_waves(items: List[Dict[str, Any]], *, launch: Dict[str, Any],
                    adapters: Dict[str, Dict[str, Any]], work_dir: Path,
                    progress: Progress, receipts, workers: int) -> List[Dict[str, Any]]:
    """Execute lane units in waits_for order; independent units side by side.

    Every unit in one wave has all its prerequisites done, so a native binding
    never starts before the unit it waits for. A cycle blocks by name."""
    done: set = set()
    by_id = {item["id"]: item for item in items}
    waits = {item["id"]: set(item["unit"].get("waits_for") or []) & set(by_id)
             for item in items}
    outcomes: List[Dict[str, Any]] = []
    remaining = set(by_id)
    while remaining:
        ready = sorted(uid for uid in remaining if not (waits[uid] - done))
        if not ready:
            raise DispatchError("the launch plan's waits_for edges form a cycle: "
                                + ", ".join(sorted(remaining)))
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = [pool.submit(_run_lane, by_id[uid], launch=launch,
                                   adapter=adapters[uid], work_dir=work_dir,
                                   progress=progress, receipts=receipts)
                       for uid in ready]
            for future in futures:
                outcomes.append(future.result())
        done.update(ready)
        remaining.difference_update(ready)
    return outcomes


def _check_scoped_approvals(launch: Dict[str, Any],
                              approvals: List[Dict[str, Any]],
                              target: str, *,
                              client_identity_ref: str,
                              worker_identity_ref: str) -> None:
    """Scoped side-effect approvals get the FULL gate discipline (doc 02 §9,
    doc 03 §9): separate type, scope containing the type, plan-hash binding,
    client identity, no worker self-approval, provenance reference,
    revocation, expiry — via validate_launch_plan.assert_scoped_approval,
    the same helper core the plan gate uses. A record the worker minted
    alone authorizes nothing."""
    needed = {"local_only": [],
              "approved_test_location": ["test_location_use"],
              "approved_live_publication": ["test_location_use",
                                            "page_publication"]}[target]
    for need in needed:
        candidates = [a for a in approvals
                      if isinstance(a, dict)
                      and a.get("subject_type") == need]
        if not candidates:
            raise DispatchError(
                f"write target {target} requires a {need} approval bound to "
                "this plan hash; none supplied (approvals are separate types "
                "and never inferred from the plan approval)")
        first_error: Optional[str] = None
        for cand in candidates:
            try:
                vlp.assert_scoped_approval(
                    launch, cand, need,
                    client_identity_ref=client_identity_ref,
                    worker_identity_ref=worker_identity_ref)
                break
            except vlp.ApprovalError as exc:
                if first_error is None:
                    first_error = str(exc)
        else:
            raise DispatchError(
                f"write target {target}: no {need} approval passed the gate "
                f"discipline — {first_error}")


def dispatch(launch: Dict[str, Any], approval: Dict[str, Any], *,
             client_identity_ref: str, worker_identity_ref: str,
             copy_profile: str = "standard",
             allowed_write_target: str = "local_only",
             scoped_approvals: Optional[List[Dict[str, Any]]] = None,
             out_dir: Optional[Path] = None,
             executor: Optional[Callable[..., Dict[str, Any]]] = None,
             parallel: int = 1,
             image_inputs: Optional[Dict[str, Any]] = None,
             landing_pages: Optional[List[str]] = None,
             extra_pages: Tuple[str, ...] = (),
             limiter: Any = None,
             mode: str = MODE_PAGE_ONLY,
             launch_plan: Optional[Dict[str, Any]] = None,
             lane_adapters: Optional[Dict[str, Any]] = None,
             progress_path: Optional[Path] = None,
             ) -> Dict[str, Any]:
    """Full dispatch. Returns the manifest dict; writes requests (+ results
    when an executor ran) under out_dir when given.

    mode: explicit ``page_only`` (default) or ``turnkey_launch``. turnkey
    additionally requires the full approved launch plan (``launch_plan``),
    a registered lane adapter for every non-page unit (``lane_adapters``),
    a durable progress file (``progress_path`` or ``out_dir/progress.json``)
    and a page executor, because a turnkey run promises every unit.

    parallel: pages built side by side (1 = the sequential fallback, same
    results). Every page, the landing page too, runs side by side. image_inputs: the shared
    image inputs (page_set.load_image_inputs); with the paid provider the
    spend cap and the KIE limiter apply (page_swarm). extra_pages: opted-in
    design pages that ride on a route request (today downsell_2)."""
    if mode not in DISPATCH_MODES:
        raise DispatchError(f"mode {mode!r} is not one of {DISPATCH_MODES!r}; "
                            "the mode is explicit and never inferred")
    fails = vlp.validate_launch(launch)
    if fails:
        raise DispatchError("launch record fails validation: " + "; ".join(fails))
    if launch["status"] not in ("approved", "building"):
        raise DispatchError(f"launch status is {launch['status']!r} — dispatch "
                            "requires an approved plan")
    vlp.assert_plan_build_approved(launch, approval,
                                   client_identity_ref=client_identity_ref,
                                   worker_identity_ref=worker_identity_ref)
    graph = clr.compile_route(launch)
    if clr.graph_hash(graph) != launch["route_graph_hash"]:
        raise DispatchError("re-compiled route graph hash does not match the "
                            "record's route_graph_hash — the approved plan and "
                            "its route disagree; re-plan, never dispatch")
    _check_scoped_approvals(launch, scoped_approvals or [], allowed_write_target,
                            client_identity_ref=client_identity_ref,
                            worker_identity_ref=worker_identity_ref)
    page_set = pset.build_page_set(launch, landing_pages=landing_pages,
                                   extra_pages=extra_pages)
    requests = build_requests(launch, graph, copy_profile=copy_profile,
                              allowed_write_target=allowed_write_target)
    for r in requests:
        rf = validate_request(r)
        if rf:
            raise DispatchError("built request failed schema discipline: " +
                                "; ".join(rf))
    # ---- turnkey gate: every promise checked BEFORE anything runs ----------
    turnkey_block: Dict[str, Any] = {"mode": mode}
    lane_items: List[Dict[str, Any]] = []
    lane_adapters_by_id: Dict[str, Dict[str, Any]] = {}
    progress: Optional[Progress] = None
    if mode == MODE_TURNKEY_LAUNCH:
        if launch_plan is None:
            raise DispatchError(
                "turnkey_launch requires the FULL approved launch plan "
                "(--launch-plan); page_only is the explicit mode for pages alone")
        plan_fails = validate_turnkey_plan(
            launch_plan, launch, [p["page_key"] for p in page_set["pages"]])
        if plan_fails:
            raise DispatchError("launch plan cannot be dispatched turnkey: "
                                + "; ".join(plan_fails))
        if executor is None:
            raise DispatchError(
                "turnkey_launch requires a page executor; without one the page "
                "units would only be emitted, and turnkey promises every unit")
        if out_dir is None:
            raise DispatchError(
                "turnkey_launch requires --out: durable progress is written there")
        progress = Progress(progress_path or (Path(out_dir) / "progress.json"))
        units = plan_units(launch_plan)
        lane_items = [u for u in units if u["section"] != "pages"]
        registered = (lane_adapters or {}).get("adapters")
        if not isinstance(registered, dict):
            raise DispatchError(
                "turnkey_launch requires a lane adapter registry "
                "({adapters: {<unit id>: {command: [...]}}}); none supplied")
        lane_ids = [u["id"] for u in lane_items]
        unknown = sorted(str(k) for k in registered if k not in set(lane_ids))
        if unknown:
            raise DispatchError(
                "lane adapter registry names unit(s) outside the approved plan: "
                + ", ".join(unknown))
        missing = [uid for uid in lane_ids
                   if not (registered.get(uid) or {}).get("command")]
        if missing:
            raise DispatchError(
                "no registered lane adapter for plan unit(s): " + ", ".join(missing)
                + " — turnkey never skips a promised unit")
        lane_adapters_by_id = {uid: registered[uid] for uid in lane_ids}
        turnkey_block.update({
            "plan_schema_version": launch_plan.get("schema_version"),
            "plan_units": len(units),
            "lane_units": len(lane_items),
            "progress_path": str(progress.path),
        })
    elif launch_plan is not None:
        # Explicit, never silent: page_only does not dispatch non-page units.
        turnkey_block = {"mode": mode, "plan_state": "not_dispatched",
                         "reason": ("page_only dispatches page units only; the "
                                    "supplied launch plan's email, text, automation "
                                    "and Conversation AI units were NOT run")}
    # PP-T2 manifest block (adoption map section 2.1 rule 5): per role,
    # the state read, the schema_version actually emitted (taken from the
    # request itself, never inferred from the decision), and the
    # evidence_ref behind the state.
    adoption, adoption_status = _read_adoption()
    adoption_block: Dict[str, Any] = {"file_status": adoption_status,
                                      "roles": {}}
    for r in requests:
        d = adoption[r["page_role"]]
        adoption_block["roles"][r["page_role"]] = {
            "state": d["state"],
            "emitted_schema_version": r["schema_version"],
            "evidence_ref": d["evidence_ref"]}
    manifest: Dict[str, Any] = {
        "schema": "signature-launch-dispatch/v1",
        "mode": mode,
        "launch_id": launch["launch_id"], "revision": launch["revision"],
        "plan_document_hash": vlp.plan_document_hash(launch),
        "route_graph_hash": launch["route_graph_hash"],
        "allowed_write_target": allowed_write_target,
        "prompt_policy_adoption": adoption_block,
        "execution": "executed" if executor else "emitted_not_executed",
        "launch_plan": turnkey_block,
        "requests": [{"request_id": r["request_id"], "page_id": r["page_id"],
                      "page_role": r["page_role"],
                      "assigned_skill": r["assigned_skill"],
                      "input_hash": r["input_hash"]} for r in requests],
        "page_set": {"shape": page_set["shape"], "to_confirm": page_set["to_confirm"],
                     "pages": [{k: p[k] for k in ("page_key", "role", "page_kind", "role_instance",
                                                  "label", "skill", "design_only")}
                               for p in page_set["pages"]],
                     "lane_plan": pset.lane_plan(page_set)},
        "results": [],
    }
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "route-graph.json").write_bytes(clr.serialize_graph(graph))
        for r in requests:
            (out_dir / f"request-{r['page_role']}.json").write_text(
                json.dumps(r, indent=2) + "\n", encoding="utf-8")
    # turnkey page-unit bookkeeping: a page request is skipped only when every
    # page unit it answers is already done at the same input hash.
    page_units_by_id: Dict[str, Dict[str, Any]] = {}
    role_page_units: Dict[str, List[str]] = {}
    if progress is not None and launch_plan is not None:
        page_key_role = {p["page_key"]: p["role"] for p in page_set["pages"]}
        for u in plan_units(launch_plan):
            if u["section"] != "pages":
                continue
            page_units_by_id[u["id"]] = u
            page_key = u["id"].removeprefix("page_")
            role = page_key_role.get(page_key, page_key)
            role_page_units.setdefault(role, []).append(u["id"])
    requests_to_run = requests
    if progress is not None:
        done_units = {uid for uid, u in page_units_by_id.items()
                      if progress.should_skip(uid, _unit_input_hash(
                          launch, uid, u["unit"]))}
        requests_to_run = [r for r in requests
                           if not all(uid in done_units
                                      for uid in role_page_units.get(r["page_role"], []))]
        if not requests_to_run:
            manifest["page_resume"] = {"skipped_roles": [r["page_role"]
                                                         for r in requests]}
    if executor:
        run = swarm.execute(requests_to_run, executor, page_set=page_set,
                            out_dir=out_dir, launch_id=launch["launch_id"],
                            workers=parallel, image_inputs=image_inputs,
                            limiter=limiter)
        manifest["swarm"] = run["swarm"]
        failed = [o for o in run["outcomes"] if o["status"] != "ok"]
        for o in run["outcomes"]:
            if o["status"] != "ok":
                continue
            extra = o["lane"] not in PAGE_ROLES
            if extra:
                manifest.setdefault("page_results", {})[o["lane"]] = o["result"]
            else:
                manifest["results"].append(o["result"])
            if out_dir:
                name = (f"page-result-{o['lane']}.json" if extra
                        else f"result-{o['lane']}.json")
                (out_dir / name).write_text(
                    json.dumps(o["result"], indent=2) + "\n", encoding="utf-8")
            if progress is not None:
                for uid in role_page_units.get(o["lane"], []):
                    progress.mark(uid, status="done",
                                  input_hash=_unit_input_hash(
                                      launch, uid, page_units_by_id[uid]["unit"]),
                                  section="pages",
                                  result_path=(out_dir / name) if out_dir else None)
        if failed:
            if progress is not None:
                for o in failed:
                    for uid in role_page_units.get(o["lane"], []):
                        progress.mark(uid, status="failed",
                                      input_hash=_unit_input_hash(
                                          launch, uid, page_units_by_id[uid]["unit"]),
                                      section="pages", error=str(o.get("error")))
            if out_dir:  # the pages that did finish are kept and named
                (out_dir / "dispatch-manifest.json").write_text(
                    json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            raise DispatchError(
                "page(s) did not complete (every other page was still built): "
                + "; ".join(f"{o['lane']} {o['status']}: {o['error']}" for o in failed))
    if mode == MODE_TURNKEY_LAUNCH:
        import collect_launch_receipts as receipts
        lane_results: List[Dict[str, Any]] = []
        pending: List[Dict[str, Any]] = []
        for item in lane_items:
            ih = _unit_input_hash(launch, item["id"], item["unit"])
            if progress.should_skip(item["id"], ih):
                lane_results.append({"unit_id": item["id"],
                                     "section": item["section"],
                                     "input_hash": ih,
                                     "status": "skipped_done",
                                     "result_path": progress.state(item["id"]).get("result_path")})
            else:
                pending.append(item)
        try:
            lane_results += _run_lane_waves(
                pending, launch=launch, adapters=lane_adapters_by_id,
                work_dir=Path(out_dir), progress=progress, receipts=receipts,
                workers=max(1, parallel))
        except DispatchError:
            manifest["lane_results"] = lane_results
            manifest["progress_path"] = str(progress.path)
            if out_dir:
                (out_dir / "dispatch-manifest.json").write_text(
                    json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            raise
        manifest["lane_results"] = lane_results
        manifest["progress_path"] = str(progress.path)
    if out_dir:
        (out_dir / "dispatch-manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def executor_from_config(config: Dict[str, Any], work_dir: Path,
                         landing_pages: Optional[List[str]] = None):
    """Build an executor from a consumer-adapter config (S49-08 seam).

    Config shape: {"adapters": {"<page_role>": {"command": ["prog", "{request}",
    "{result}"], "timeout_s": 600}}}. For each request the adapter command
    runs with the request JSON path and the expected result JSON path; the
    result is accepted ONLY when it parses and passes the receipt
    validation (schema shape + exact request echo) from
    collect_launch_receipts. A role with no configured adapter, a failing
    command, or an invalid result is a DispatchError — dispatch never
    papers over a consumer that did not really answer.

    landing_pages: the client's landing page set (page_set.py), filled into
    the {landing_pages} placeholder. A landing adapter that runs
    landing_bridge.py MUST pass it (--landing-pages {landing_pages}), so the
    bridge refuses a config that builds fewer or other pages than planned;
    a command that leaves it out is refused here, before anything runs."""
    import subprocess
    import collect_launch_receipts as receipts

    adapters = config.get("adapters") or {}
    # An adapter key is a page_role, or an extra design page that rides on a
    # role's request (page_types.json role_instance, today downsell_2).
    allowed = set(PAGE_ROLES) | {k for k, p in pset.page_types()["pages"].items()
                                 if p["role_instance"]}
    unknown = sorted(str(k) for k in adapters if k not in allowed)
    if unknown:
        raise DispatchError(
            "adapter config names page_role(s) outside the page-role map "
            f"({PAGE_ROLE_MAP_FILE.name} page_role_map.page_roles): {unknown}")

    landing = (adapters.get("landing") or {}).get("command") or []
    if any(Path(str(part)).name == "landing_bridge.py" for part in landing) \
            and not any("{landing_pages}" in str(part) for part in landing):
        raise DispatchError(
            "landing adapter runs landing_bridge.py without --landing-pages {landing_pages}: "
            "the bridge could not check that it builds the pages the client planned")

    def run(req: Dict[str, Any], lane: Optional[str] = None) -> Dict[str, Any]:
        role = req["page_role"]
        key = lane or role
        spec = adapters.get(key) or (adapters.get(role) if lane else None)
        if not spec or not spec.get("command"):
            raise DispatchError(f"no consumer adapter configured for role "
                                f"{key} — dispatch cannot execute it")
        # An extra page rides on its parent's request bytes; its files are
        # named page-request-/page-result- so the route's request-*/result-*
        # collections never see a second answer for one request.
        req_path = work_dir / (f"page-request-{key}.json" if lane
                               else f"request-{role}.json")
        res_path = work_dir / (f"page-result-{key}.json" if lane
                               else f"result-{role}.json")
        if lane:
            req_path.write_text(json.dumps(req, indent=2) + "\n", encoding="utf-8")
        cmd = [part.replace("{request}", str(req_path))
                    .replace("{result}", str(res_path))
                    .replace("{work_dir}", str(work_dir))
                    .replace("{image_inputs}", str(work_dir / swarm.INPUTS_NAME))
                    .replace("{landing_pages}", ",".join(landing_pages or ()))
                    .replace("{page_key}", key)
                    .replace("{role_instance}", lane or "")
               for part in spec["command"]]
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=float(spec.get("timeout_s", 600)))
        if proc.returncode != 0:
            raise DispatchError(f"consumer adapter for {role} exited "
                                f"{proc.returncode}: {proc.stderr.strip()[:400]}")
        if not res_path.is_file():
            raise DispatchError(f"consumer adapter for {role} produced no "
                                f"result file at {res_path}")
        result = json.loads(res_path.read_text(encoding="utf-8"))
        fails = receipts.validate_result(result, req)
        if fails:
            raise DispatchError(f"consumer result for {role} failed receipt "
                                "validation: " + "; ".join(fails))
        return result

    return run


def _simulated_executor(author: str):
    def run(req: Dict[str, Any], lane: Optional[str] = None) -> Dict[str, Any]:
        return {"schema_version": "1.0", "tenant_id": req["tenant_id"],
                "location_id": req["location_id"], "launch_id": req["launch_id"],
                "revision": req["revision"], "request_id": req["request_id"],
                "input_hash": req["input_hash"], "page_id": req["page_id"],
                "status": "authored", "artifacts": [],
                "author_session": author, "reviewer_session": None,
                "independent_review": False, "proof_class": "L0",
                "blockers": [], "native_bindings_ref": None,
                "test_only": True}
    return run


def _load(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _self_test() -> int:
    ok = True

    def say(good, msg):
        nonlocal ok
        ok = ok and good
        print(f"SELF-TEST {'ok' if good else 'FAIL'}: {msg}")

    # Fix 15 — ONE page-type vocabulary. The table is the only authority; these
    # probes prove a consumer can loop over it and that no copy of the role
    # vocabulary has drifted from it.
    say(set(PAGE_ROLE_MAP["page_roles"]) == set(ROLE_SKILL),
        "page_role_map.page_roles is exactly the dispatch role set")
    say(set(PAGE_TYPE_TO_ROLE) == {
            "main", "product_selection", "checkout", "upsell", "downsell",
            "upsell-2", "downsell-2", "thank-you"},
        "the map covers the seven page_role values plus matrix-only downsell-2")
    say(set(PAGE_TYPE_TO_ROLE.values()) == set(PAGE_ROLES),
        "a loop over the page_role_map reaches every page_role the skill "
        "understands")
    say(PAGE_TYPE_TO_ROLE["downsell-2"] == "downsell_1"
        and PAGE_ROLE_MAP["page_types"]["downsell-2"].get("role_instance")
        == "downsell_2",
        "downsell-2 is decided: downsell_1 + role_instance downsell_2")
    say(PAGE_ROLE_MAP["page_types"]["checkout"].get("adapter")
        == "design_only",
        "checkout's adapter is design-only by ruling: the native form is "
        "never a dispatch adapter, its wireframes and mockups are")
    try:
        executor_from_config({"adapters": {"not_a_page_role": {
            "command": ["true"]}}}, Path("."))
        say(False, "an adapter key outside the page-role map must be refused")
    except DispatchError:
        say(True, "an adapter key outside the page-role map is refused")
    _repo_root = Path(__file__).resolve().parent.parent.parent
    _schema_copies = [
        _repo_root / "71-blackceo-signature-page" / "references"
        / "page-request.schema.json",
        _repo_root / "49-signature-funnel" / "scripts" / "vendor"
        / "page-request.schema.json",
        _repo_root / "shared-utils" / "signature_launch" / "domain"
        / "page-request.schema.json",
        _repo_root / "shared-utils" / "signature_launch" / "domain"
        / "page-request.v1.0.schema.json",
    ]
    for _schema in _schema_copies:
        if not _schema.is_file():
            print(f"SELF-TEST skip: {_schema.name} absent "
                  f"({_schema.parent} not in this layout)")
            continue
        _enum = json.loads(_schema.read_text(encoding="utf-8"))[
            "properties"]["page_role"]["enum"]
        say(_enum == list(PAGE_ROLES),
            f"{_schema.relative_to(_repo_root)} page_role enum equals "
            "page_role_map.page_roles")

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def offer(oid, slot, amt, excludes=()):
        return {"offer_id": oid, "slot": slot, "display_name": oid,
                "deliverables": ["x"], "exclusions": [],
                "entitlement_ids": [oid.lower()], "requires": [],
                "excludes": list(excludes), "native_product_id": None,
                "prices": [{"price_choice_id": f"{oid}-USD", "currency": "USD",
                            "amount_minor": amt, "billing_type": "one_time",
                            "native_price_id": None, "schedule": [],
                            "terms_source": None, "approval_status": "approved"}],
                "source_kind": "test_fixture", "source_ref": "self-test",
                "test_only": True}

    launch = {"schema_version": "1.0", "tenant_id": "T", "location_id": "L",
              "launch_id": "X", "revision": 1, "journey_mode": "multiple_options",
              "status": "awaiting_plan_approval", "brand_ref": "B",
              "brand_hash": "H", "route_graph_ref": "", "route_graph_hash": "",
              "plan_approval_ref": None,
              "offers": [offer("M1", "main", 1000), offer("M2", "main", 2000),
                         offer("BP", "bump", 500),
                         offer("U1", "upsell_1", 3000, ["D1"]),
                         offer("D1", "downsell_1", 1500, ["U1"]),
                         offer("U2", "upsell_2", 4000)],
              "extras": {"upsell_1": True, "downsell_1": True, "upsell_2": True},
              "bump_enabled": True, "image_provider": "agnes",
              "source_refs": [], "test_only": True}
    graph = clr.compile_route(launch)
    launch["route_graph_ref"] = "route-graph:X:rev1"
    launch["route_graph_hash"] = clr.graph_hash(graph)
    approval = {"schema_version": "1.0", "approval_id": "APPR-1",
                "subject_type": "launch_plan_build",
                "subject_hash": vlp.plan_document_hash(launch),
                "owner_identity_ref": "client-1", "source_message_ref": "m-1",
                "recorded_at": now, "scope": ["launch_plan_build"],
                "revoked": False,
                "verification_class": "recorded_consent_not_cryptographically_sealed"}
    launch["status"] = "approved"
    launch["plan_approval_ref"] = "APPR-1"

    m = dispatch(launch, approval, client_identity_ref="client-1",
                 worker_identity_ref="worker-9")
    say(len(m["requests"]) == 7 and m["execution"] == "emitted_not_executed",
        "approved full plan emits 7 role requests and honestly marks them "
        "not executed")
    roles = {r["page_role"]: r for r in m["requests"]}
    _built = {r["page_role"]: r for r in build_requests(
        launch, graph, copy_profile="standard", allowed_write_target="local_only")}
    say(_built["thank_you"]["copy_profile"] == "thank-you"
        and all(r["copy_profile"] == "standard"
                for role, r in _built.items() if role != "thank_you"),
        "the thank-you page request names its own copy profile (its own five "
        "sections in Skill 71), every other role keeps the launch's profile")
    say(roles["upsell_1"]["assigned_skill"] == 80 and
        roles["upsell_2"]["assigned_skill"] == 80 and
        roles["upsell_1"]["request_id"] != roles["upsell_2"]["request_id"],
        "U1 and U2 are separate S80 invocations with distinct dispatch keys")
    say(roles["checkout"]["page_role"] == "checkout" and
        len([r for r in m["requests"] if r["page_role"] == "bump"]) == 0,
        "the bump is never dispatched as a page")
    m2 = dispatch(launch, approval, client_identity_ref="client-1",
                  worker_identity_ref="worker-9")
    say([r["request_id"] for r in m["requests"]] ==
        [r["request_id"] for r in m2["requests"]],
        "dispatch is idempotent: same approved plan, same dispatch keys")
    try:
        dispatch(launch, dict(approval, subject_hash="0" * 64),
                 client_identity_ref="client-1", worker_identity_ref="worker-9")
        say(False, "dispatch under a stale approval must fail")
    except vlp.ApprovalError:
        say(True, "dispatch refuses when the plan approval does not bind")
    try:
        dispatch(launch, approval, client_identity_ref="client-1",
                 worker_identity_ref="worker-9",
                 allowed_write_target="approved_test_location")
        say(False, "test-location dispatch without its approval must fail")
    except DispatchError:
        say(True, "test-location write target requires its own scoped approval")
    scoped = [dict(approval, approval_id="APPR-T",
                   subject_type="test_location_use",
                   scope=["test_location_use"])]
    m3 = dispatch(launch, approval, client_identity_ref="client-1",
                  worker_identity_ref="worker-9",
                  allowed_write_target="approved_test_location",
                  scoped_approvals=scoped, executor=_simulated_executor("test"))
    say(len(m3["results"]) == 7 and m3["execution"] == "executed",
        "with the scoped approval + executor, dispatch executes and returns results")
    # Review probe D (D6): fabricated scoped approvals — worker as owner,
    # no provenance reference, recorded in 2020, class "none" — must NOT
    # authorize a live publication target.
    fabricated = [
        dict(approval, approval_id="F-T", subject_type="test_location_use",
             scope=["test_location_use"], owner_identity_ref="worker-9",
             source_message_ref="", recorded_at="2020-01-01T00:00:00Z",
             verification_class="none"),
        dict(approval, approval_id="F-P", subject_type="page_publication",
             scope=["page_publication"], owner_identity_ref="worker-9",
             source_message_ref="", recorded_at="2020-01-01T00:00:00Z",
             verification_class="none")]
    try:
        dispatch(launch, approval, client_identity_ref="client-1",
                 worker_identity_ref="worker-9",
                 allowed_write_target="approved_live_publication",
                 scoped_approvals=fabricated)
        say(False, "fabricated scoped approvals must not authorize live "
                   "publication (D6)")
    except DispatchError:
        say(True, "fabricated scoped approvals are refused for live "
                  "publication (D6: identity, provenance, expiry, class all "
                  "checked)")

    # Consumer-adapter seam (S49-08): a real subprocess consumer whose
    # result echoes the request is accepted; one that echoes wrongly is not.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        consumer = tdp / "consumer.py"
        consumer.write_text(
            "import json,sys\n"
            "req=json.load(open(sys.argv[1]))\n"
            "res={'schema_version':'1.0','tenant_id':req['tenant_id'],"
            "'location_id':req['location_id'],'launch_id':req['launch_id'],"
            "'revision':req['revision'],'request_id':req['request_id'],"
            "'input_hash':req['input_hash'],'page_id':req['page_id'],"
            "'status':'authored','artifacts':[],"
            "'author_session':'consumer-test','reviewer_session':None,"
            "'independent_review':False,'proof_class':'L0','blockers':[],"
            "'native_bindings_ref':None,'test_only':req['test_only']}\n"
            "json.dump(res,open(sys.argv[2],'w'))\n", encoding="utf-8")
        cfg = {"adapters": {role: {"command": [sys.executable, str(consumer),
                                              "{request}", "{result}"]}
                            for role in ROLE_SKILL}}
        out = tdp / "dispatch"
        m4 = dispatch(launch, approval, client_identity_ref="client-1",
                      worker_identity_ref="worker-9", out_dir=out,
                      executor=executor_from_config(cfg, out))
        say(len(m4["results"]) == 7,
            "adapter-config executor runs real consumers and validates echoes")
        bad = tdp / "bad_consumer.py"
        bad.write_text("import json,sys\n"
                       "json.dump({'bogus': True}, open(sys.argv[2],'w'))\n",
                       encoding="utf-8")
        cfg_bad = {"adapters": {role: {"command": [sys.executable, str(bad),
                                                   "{request}", "{result}"]}
                                for role in ROLE_SKILL}}
        try:
            dispatch(launch, approval, client_identity_ref="client-1",
                     worker_identity_ref="worker-9", out_dir=out,
                     executor=executor_from_config(cfg_bad, out))
            say(False, "an invalid consumer result must be refused")
        except DispatchError:
            say(True, "a consumer result that fails receipt validation is refused")

    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Dispatch an approved launch plan.")
    ap.add_argument("--launch"); ap.add_argument("--approval")
    ap.add_argument("--run-dir",
                    help="launch run dir holding launch.json, approval.json and "
                         "launch-request.json (mode signature_launch); outputs "
                         "go to <run-dir>/dispatch")
    ap.add_argument("--client"); ap.add_argument("--worker")
    ap.add_argument("--copy-profile", default="standard")
    ap.add_argument("--write-target", default="local_only")
    ap.add_argument("--scoped-approvals", help="JSON array of extra approvals")
    ap.add_argument("--out", help="directory for requests + manifest")
    ap.add_argument("--adapters",
                    help="consumer adapter config JSON (executes requests "
                         "through the owning skills' entrypoints)")
    ap.add_argument("--simulate-executor", action="store_true",
                    help="TEST ONLY: fabricate L0 authored results")
    ap.add_argument("--parallel", default="auto",
                    help="pages built side by side: a number, or auto (the runner "
                         "profile's worker count: Mac 6, Hostinger 8, Contabo 4). "
                         "1 builds one page at a time")
    ap.add_argument("--image-inputs",
                    help="shared image inputs JSON (design style, brand file, owner, "
                         "image cap, provider); adapters read it as {image_inputs}")
    ap.add_argument("--landing-pages",
                    help="which landing pages the client chose: landing, sales or "
                         "landing,sales (default: the recommended set, flagged to confirm)")
    ap.add_argument("--extra-page", action="append", default=[],
                    help="an extra design page to add (downsell_2)")
    ap.add_argument("--mode", choices=DISPATCH_MODES, default=MODE_PAGE_ONLY,
                    help="explicit dispatch mode: page_only (default: page units "
                         "only) or turnkey_launch (the full approved plan: every "
                         "email, text, automation and requested AI unit too)")
    ap.add_argument("--launch-plan",
                    help="the FULL launch plan JSON (required for turnkey_launch)")
    ap.add_argument("--lane-adapters",
                    help="lane adapter registry JSON for turnkey_launch: "
                         "{adapters: {<plan unit id>: {command: [...], timeout_s: N}}}")
    ap.add_argument("--progress",
                    help="durable progress file (default: <out>/progress.json)")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return _self_test()
    cfg: Dict[str, Any] = {}
    if args.run_dir:
        rd = Path(args.run_dir)
        args.launch = args.launch or str(rd / "launch.json")
        args.approval = args.approval or str(rd / "approval.json")
        cfg_path = rd / "launch-request.json"
        if cfg_path.is_file():
            cfg = _load(str(cfg_path))
        if cfg.get("mode") not in (None, "signature_launch"):
            print("FAIL: launch-request.json mode is not signature_launch")
            return EXIT_VIOLATION
        args.image_inputs = args.image_inputs or cfg.get("image_inputs")
        args.landing_pages = args.landing_pages or (
            ",".join(cfg["landing_pages"]) if cfg.get("landing_pages") else None)
        args.extra_page = args.extra_page or list(cfg.get("extra_pages") or [])
        if args.parallel == "auto" and cfg.get("parallel") is not None:
            args.parallel = str(cfg["parallel"])
        args.client = args.client or cfg.get("client_identity_ref")
        args.worker = args.worker or cfg.get("worker_identity_ref")
        args.copy_profile = cfg.get("copy_profile", args.copy_profile)
        args.write_target = cfg.get("allowed_write_target", args.write_target)
        args.mode = cfg.get("dispatch_mode", args.mode)
        args.launch_plan = args.launch_plan or cfg.get("launch_plan")
        args.lane_adapters = args.lane_adapters or cfg.get("lane_adapters")
        args.out = args.out or str(rd / "dispatch")
    if not (args.launch and args.approval and args.client and args.worker):
        print("USAGE ERROR: --launch --approval --client --worker are required.")
        return EXIT_FAILCLOSED
    try:
        launch = _load(args.launch)
        approval = _load(args.approval)
        scoped = _load(args.scoped_approvals) if args.scoped_approvals \
            else cfg.get("scoped_approvals", [])
        executor = None
        if args.adapters:
            if not args.out:
                print("FAIL: --adapters requires --out (or --run-dir) as the "
                      "work dir for request/result files")
                return EXIT_FAILCLOSED
            executor = executor_from_config(
                _load(args.adapters), Path(args.out),
                args.landing_pages.split(",") if args.landing_pages
                else pset.recommended_landing_pages(launch))
        elif args.simulate_executor:
            executor = _simulated_executor("dispatch-cli-simulated")
        inputs = pset.load_image_inputs(args.image_inputs) \
            if args.image_inputs else None
        workers = swarm.default_workers() if args.parallel == "auto" \
            else int(args.parallel)
        if workers < 1:
            raise DispatchError("--parallel must be auto or a number >= 1")
        limiter = swarm.kie_limiter() if inputs and \
            inputs["image_provider"] == "kie" else None
        m = dispatch(launch, approval, client_identity_ref=args.client,
                     worker_identity_ref=args.worker,
                     copy_profile=args.copy_profile,
                     allowed_write_target=args.write_target,
                     scoped_approvals=scoped,
                     out_dir=Path(args.out) if args.out else None,
                     executor=executor, parallel=workers,
                     image_inputs=inputs,
                     landing_pages=args.landing_pages.split(",")
                     if args.landing_pages else None,
                     extra_pages=tuple(args.extra_page), limiter=limiter,
                     mode=args.mode,
                     launch_plan=_load(args.launch_plan) if args.launch_plan else None,
                     lane_adapters=_load(args.lane_adapters) if args.lane_adapters else None,
                     progress_path=Path(args.progress) if args.progress else None)
    except (DispatchError, pset.PageSetError, swarm.SwarmError,
            vlp.ApprovalError, clr.RouteError, OSError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return EXIT_VIOLATION
    print(json.dumps({"mode": m["mode"],
                      "execution": m["execution"],
                      "requests": len(m["requests"]),
                      "results": len(m["results"]),
                      "lane_units": len(m.get("lane_results") or []),
                      "pages": [p["page_key"] for p in m["page_set"]["pages"]],
                      "to_confirm": m["page_set"]["to_confirm"]}, indent=2))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
