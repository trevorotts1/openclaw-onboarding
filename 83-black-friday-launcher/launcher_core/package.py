"""Package and receipt assembly.

Pieces come from the compiled route, never from a caller's wish list: every
route node must arrive with a valid shared page-result. Receipt evidence is
Skill 49's own receipt store (49-signature-funnel/scripts/delegation_receipt.py);
this module loads it and never writes a parallel store.
"""

from __future__ import annotations

import datetime
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from .constants import (
    COUNCIL_ENTRY_POINT,
    COUNCIL_SKILL_SLUG,
    DECIDED,
    FUNNEL_SKILL_SLUG,
    PAGE_STATUSES,
    PROOF_CLASSES,
    RECEIPT_MODULE_REF,
    REPO_ROOT,
    SCHEMA_VERSION,
    SEAMS,
    SKILL_NAME,
    SKILL_NUMBER,
    SKILL_VERSION,
    skill_path,
)
from . import checkout as checkout_module
from . import council as council_module
from . import launch_plan as launch_plan_module
from . import page_designs
from . import route as route_module
from .intake import offer_facts

# A second page of a role that the route graph does not repeat. The piece is keyed by its slot
# (downsell_2), carries the parent role (downsell_1) and the instance, and is one more page of the
# launch: its designs are required exactly like every other page's.
EXTRA_SLOTS = {"downsell_2": "downsell_1", "sales": "landing"}
# "sales" is the signature sales page when the client also has the landing (opt-in) page: two pages of
# the one landing route node.

_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_RECEIPTS_REL = "delegation_receipts.jsonl"

# The typed receipt this lane owns. ``receipt.schema.json`` beside this tree is
# the published contract; the producer here and the validator in checks.py are
# the two halves that must agree with it.
RECEIPT_SCHEMA_REF = "receipt.schema.json"
RECEIPT_SCHEMA_VERSION = "1.1"
RECEIPT_TYPE = "launcher.package.v1"

# What a package claims to deliver. A full Black Friday launch must carry the shared
# U-CONTRACT plan: the seasonal calendar and every planned email, text and automation.
# Without a plan the package is pages only and says so, in the manifest and the receipt.
DELIVERY_SCOPE_FULL = "full_launch"
DELIVERY_SCOPE_PAGE_ONLY = "page_only"
DELIVERY_LABELS = {
    DELIVERY_SCOPE_FULL: "full Black Friday launch (calendar, emails, texts and automations "
                         "delivered)",
    DELIVERY_SCOPE_PAGE_ONLY: "page-only (no shared launch plan: the Black Friday calendar, "
                              "emails, texts and automations are not part of this package)",
}

# Proof classes are separate facts, never one ladder collapsed into a status:
# authored bytes, a draft installation, a test record, a live observation.
PROOF_BY_STATUS = {
    "authored": (True, False, False, False),
    "draft_delivered": (True, False, False, False),
    "locally_verified": (True, False, True, False),
    "installed_test_verified": (True, True, True, False),
    "ready_for_activation": (True, True, True, False),
    "live_verified": (True, True, True, True),
}
PROOF_KEYS = ("authored", "draft_installed", "tested", "live_verified")
LANE_VALIDATION = {"lane": "L04", "contract": RECEIPT_TYPE, "state": "passed",
                   "detail": "artifact bytes hashed and sized at assembly"}

# A plan page kind -> the delivered piece slot that satisfies it. Ambiguous kinds
# consume their candidate slots in plan order, so two upsell pages never claim
# one piece twice.
_PAGE_KIND_SLOTS = {
    "landing": ("landing",),
    "sales": ("sales",),
    "order": ("checkout",),
    "checkout": ("checkout",),
    "upsell": ("upsell_1", "upsell_2"),
    "downsell": ("downsell_1", "downsell_2"),
    "thank_you": ("thank_you",),
}


class PackageError(Exception):
    """A package that cannot be assembled. Carries a stable autofail code."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _sha256_path(path: Path) -> Optional[str]:
    path = Path(path)
    return _sha256_file(path) if path.is_file() else None


def _repo_ref(path: Path) -> str:
    """A path's repository-relative spelling, whichever convention resolved it."""
    try:
        return str(Path(path).relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _load_receipt_module():
    """Import the funnel skill's receipt collector. None when it is not present."""
    path = skill_path(FUNNEL_SKILL_SLUG, RECEIPT_MODULE_REF)
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("s49_delegation_receipt", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def receipt_evidence(run_dir: Path) -> Dict[str, Any]:
    """What Skill 49's receipt store actually says about this run dir."""
    module = _load_receipt_module()
    if module is None:
        return {"store": str(_RECEIPTS_REL), "state": "unavailable", "entries": 0,
                "detail": f"{FUNNEL_SKILL_SLUG}/{RECEIPT_MODULE_REF} not found"}
    try:
        entries = module.load(Path(run_dir))
        raw_state = module.store_state(Path(run_dir))
    except Exception as exc:  # ReceiptError and any unreadable store
        return {"store": str(_RECEIPTS_REL), "state": "malformed", "entries": 0,
                "detail": str(exc)}
    # Skill 49 reports 'present' / 'absent' / 'malformed'; keep the raw value too.
    state = {"present": "verified"}.get(raw_state, raw_state)
    return {
        "store": str(_RECEIPTS_REL),
        "state": state,
        "store_state_raw": raw_state,
        "entries": len(entries),
    }


def _validate_piece(piece: Any, node: Dict[str, str], intake: Dict[str, Any]) -> Dict[str, Any]:
    role = node["role"]
    if not isinstance(piece, dict):
        raise PackageError("AF-LAUNCH-PKG-PIECE", f"{role}: page result must be an object")
    if piece.get("schema_version") != SCHEMA_VERSION:
        raise PackageError("AF-LAUNCH-PKG-PIECE", f"{role}: schema_version must be {SCHEMA_VERSION!r}")
    for key in ("tenant_id", "location_id", "launch_id", "revision"):
        if piece.get(key) != intake[key]:
            raise PackageError("AF-LAUNCH-PKG-PIECE",
                               f"{role}: {key} {piece.get(key)!r} does not match launch {intake[key]!r}")
    # A slot page (downsell_2) rides on its parent's Skill 49 request, so a real result echoes the parent's id.
    if piece.get("page_id") not in (node["page_id"], node.get("echoed_page_id")):
        raise PackageError("AF-LAUNCH-PKG-PIECE",
                           f"{role}: page_id {piece.get('page_id')!r} != route node {node['page_id']!r}")
    for key in ("request_id", "input_hash", "author_session"):
        if not isinstance(piece.get(key), str) or not piece[key].strip():
            raise PackageError("AF-LAUNCH-PKG-PIECE", f"{role}: {key} must be a non-empty string")
    status = piece.get("status")
    if status not in PAGE_STATUSES:
        raise PackageError("AF-LAUNCH-PKG-PIECE", f"{role}: unknown status {status!r}")
    if status == "blocked":
        raise PackageError("AF-LAUNCH-PKG-BLOCKED",
                           f"{role}: page is blocked {piece.get('blockers')!r}; a blocked page "
                           "is not a delivered package")
    proof = piece.get("proof_class")
    if proof not in PROOF_CLASSES:
        raise PackageError("AF-LAUNCH-PKG-PIECE", f"{role}: unknown proof_class {proof!r}")
    if not isinstance(piece.get("independent_review"), bool):
        raise PackageError("AF-LAUNCH-PKG-PIECE", f"{role}: independent_review must be a boolean")
    if not isinstance(piece.get("test_only"), bool):
        raise PackageError("AF-LAUNCH-PKG-PIECE", f"{role}: test_only must be a boolean")
    if piece.get("native_bindings_ref") is not None and not isinstance(piece["native_bindings_ref"], str):
        raise PackageError("AF-LAUNCH-PKG-PIECE", f"{role}: native_bindings_ref must be string or null")
    if not isinstance(piece.get("blockers"), list):
        raise PackageError("AF-LAUNCH-PKG-PIECE", f"{role}: blockers must be a list")
    artifacts = piece.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise PackageError("AF-LAUNCH-PKG-PIECE", f"{role}: at least one artifact is required")
    clean_artifacts: List[Dict[str, Any]] = []
    for i, art in enumerate(artifacts):
        if not isinstance(art, dict):
            raise PackageError("AF-LAUNCH-PKG-PIECE", f"{role}: artifacts[{i}] must be an object")
        path, digest = art.get("path"), art.get("sha256")
        if not isinstance(path, str) or not path.strip():
            raise PackageError("AF-LAUNCH-PKG-PIECE", f"{role}: artifacts[{i}].path missing")
        if not isinstance(digest, str) or not _SHA256_RE.match(digest):
            raise PackageError("AF-LAUNCH-PKG-PIECE",
                               f"{role}: artifacts[{i}].sha256 must be 64 lowercase hex")
        clean = {"path": path, "sha256": digest}
        kind = page_designs.classify(path, art.get("kind"))
        if kind:
            clean["kind"] = kind
        if isinstance(art.get("provider"), str) and art["provider"].strip():
            clean["provider"] = art["provider"].strip()
        clean_artifacts.append(clean)
    instance = node.get("role_instance") or piece.get("role_instance")
    page_kind = piece.get("page_kind") or role
    out_piece = {
        "page_id": node["page_id"],
        "role": role,
        "page_kind": page_kind,
        "role_instance": instance,
        "slot": instance or role,
        "request_id": piece["request_id"],
        "input_hash": piece["input_hash"],
        "status": status,
        "proof_class": proof,
        "independent_review": piece["independent_review"],
        "artifacts": clean_artifacts,
    }
    if isinstance(piece.get("image_provider"), str) and piece["image_provider"].strip():
        out_piece["image_provider"] = piece["image_provider"].strip()
    return out_piece


def _page_deliveries(plan: Dict[str, Any], pieces: Dict[str, Any]) -> Dict[str, Any]:
    """Plan page units satisfied by a delivered piece, without reusing one piece twice."""
    taken = set()
    out: Dict[str, Any] = {}
    for unit in launch_plan_module.planned_units(plan):
        if unit["type"] != "page":
            continue
        candidates = _PAGE_KIND_SLOTS.get(unit["kind"], (unit["kind"],))
        slot = next((c for c in candidates if c in pieces and c not in taken), None)
        if slot:
            taken.add(slot)
            out[unit["id"]] = {"state": "complete", "piece": slot}
    return out


def _launch_plan_record(plan: Optional[Dict[str, Any]], deliveries: Optional[Dict[str, Any]],
                        pieces: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The calendar + completeness record, or a named refusal when a planned unit is missing."""
    if plan is None:
        return None
    supplied = dict(deliveries or {})
    try:
        for unit_id, result in _page_deliveries(plan, pieces).items():
            supplied.setdefault(unit_id, result)
        record = launch_plan_module.record(plan, supplied)
        launch_plan_module.assert_complete(record["completeness"])
    except launch_plan_module.LaunchPlanError as exc:
        raise PackageError(exc.code, exc.detail) from exc
    return record


def _identity(intake: Dict[str, Any], approved_plan_hash: str) -> Dict[str, Any]:
    """The launch identity every typed receipt row is bound to."""
    return {
        "tenant_id": intake["tenant_id"],
        "location_id": intake["location_id"],
        "launch_id": intake["launch_id"],
        "revision": intake["revision"],
        "approved_plan_hash": approved_plan_hash,
    }


def _proof(status: Any) -> Dict[str, bool]:
    expected = PROOF_BY_STATUS.get(status)
    if expected is None:
        raise PackageError("AF-LAUNCH-PKG-RECEIPT-PROOF",
                           f"unknown delivered status {status!r}; no proof class fits it")
    return dict(zip(PROOF_KEYS, expected))


def _piece_receipt(piece: Dict[str, Any], unit_id: str, unit_type: str,
                   intake: Dict[str, Any], approved: str, plan_sha: Optional[str],
                   run_dir: Path) -> Dict[str, Any]:
    """One page's typed receipt: its request echo and its own copied artifact bytes."""
    artifacts = []
    for art in piece["artifacts"]:
        target = run_dir / art["path"]
        artifacts.append({"path": art["path"], "sha256": art["sha256"],
                          "size": target.stat().st_size})
    return {
        **_identity(intake, approved),
        "unit_id": unit_id,
        "unit_type": unit_type,
        "request": {"plan_sha256": plan_sha,
                    "request_id": piece["request_id"],
                    "input_hash": piece["input_hash"]},
        "artifacts": artifacts,
        "lane_validation": dict(LANE_VALIDATION),
        "proof": _proof(piece["status"]),
        "status": piece["status"],
    }


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _lane_receipt(unit: Dict[str, Any], delivery: Any, intake: Dict[str, Any],
                  approved: str, plan_sha: Optional[str], plan_path: Optional[str],
                  run_dir: Path, unit_type: Optional[str] = None,
                  delivery_marker: Optional[str] = None) -> Dict[str, Any]:
    """One non-launcher unit's typed receipt, from the producing lane's own output.

    The launcher owns no bytes for an email, text, automation or for a page
    another lane delivers, so the proof is the lane's delivery receipt: its own
    artifact bytes (hashed and sized here, never trusted on sight), the request
    it answers and the lane that validated it. The sealed launch plan is planning
    evidence and stays PLANNED: a unit with no lane delivery is never sealed as
    delivered, and plan bytes are never delivery proof. No draft is ever labelled
    installed, tested or live.
    """
    label = f"unit {unit['id']!r}"
    if not isinstance(delivery, Mapping) \
            or launch_plan_module._delivery_state(delivery) != "complete":
        raise PackageError(
            "AF-LAUNCH-PLAN-MISSING",
            f"{label} carries no complete lane delivery; planning evidence stays PLANNED")
    artifacts_in = delivery.get("artifacts")
    if not isinstance(artifacts_in, list) or not artifacts_in:
        raise PackageError(
            "AF-LAUNCH-PKG-RECEIPT-ARTIFACT",
            f"{label} carries no lane delivery artifacts; planning evidence stays PLANNED")
    artifacts: List[Dict[str, Any]] = []
    for index, art in enumerate(artifacts_in):
        if not isinstance(art, dict):
            raise PackageError("AF-LAUNCH-PKG-RECEIPT-ARTIFACT",
                               f"{label} artifacts[{index}] is not an object")
        path, digest, size = art.get("path"), art.get("sha256"), art.get("size")
        if not isinstance(path, str) or not path.strip():
            raise PackageError("AF-LAUNCH-PKG-RECEIPT-ARTIFACT",
                               f"{label} artifacts[{index}].path is missing")
        if not isinstance(digest, str) or not _SHA256_RE.match(digest):
            raise PackageError("AF-LAUNCH-PKG-RECEIPT-ARTIFACT",
                               f"{label} artifacts[{index}].sha256 is not 64 lowercase hex")
        if Path(path).is_absolute():
            raise PackageError("AF-LAUNCH-PKG-RECEIPT-ARTIFACT",
                               f"{label} artifact {path!r} escapes the run")
        target = (run_dir / path).resolve()
        if not target.is_relative_to(run_dir.resolve()):
            raise PackageError("AF-LAUNCH-PKG-RECEIPT-ARTIFACT",
                               f"{label} artifact {path!r} escapes the run")
        if plan_path is not None and target == (run_dir / plan_path).resolve():
            raise PackageError(
                "AF-LAUNCH-PKG-RECEIPT-ARTIFACT",
                f"{label} points at the sealed launch plan; planning evidence stays "
                f"PLANNED and is never delivery proof")
        if not target.is_file():
            raise PackageError("AF-LAUNCH-PKG-ARTIFACT-MISSING",
                               f"{label} artifact {path!r} does not resolve")
        actual_size = target.stat().st_size
        if actual_size == 0:
            raise PackageError("AF-LAUNCH-PKG-ARTIFACT-EMPTY",
                               f"{label} artifact {path!r} is zero bytes")
        if _sha256_file(target) != digest:
            raise PackageError("AF-LAUNCH-PKG-HASH",
                               f"{label} artifact {path!r} does not match its hash")
        if not isinstance(size, int) or isinstance(size, bool) or size != actual_size:
            raise PackageError("AF-LAUNCH-PKG-ARTIFACT-SIZE",
                               f"{label} artifact {path!r} is {actual_size} bytes, "
                               f"the lane receipt says {size!r}")
        artifacts.append({"path": path, "sha256": digest, "size": actual_size})

    lane = delivery.get("lane_validation")
    if not isinstance(lane, dict) or not _nonempty_str(lane.get("lane")) \
            or not _nonempty_str(lane.get("contract")) or lane.get("state") != "passed":
        raise PackageError("AF-LAUNCH-PKG-RECEIPT-LANE",
                           f"{label} carries no passed producing-lane validation")

    request = delivery.get("request")
    if not isinstance(request, dict):
        raise PackageError("AF-LAUNCH-PKG-RECEIPT-REQUEST",
                           f"{label} carries no lane request echo")
    if plan_sha is not None:
        echo = request.get("plan_sha256")
        if not _nonempty_str(echo):
            raise PackageError("AF-LAUNCH-PKG-RECEIPT-REQUEST",
                               f"{label} carries no plan echo for the sealed plan")
        if echo != plan_sha:
            raise PackageError("AF-LAUNCH-PKG-RECEIPT-REQUEST",
                               f"{label} echoes plan {echo!r}, not the sealed plan")
    elif not _nonempty_str(request.get("request_id")) \
            or not _nonempty_str(request.get("input_hash")):
        raise PackageError("AF-LAUNCH-PKG-RECEIPT-REQUEST",
                           f"{label} carries no request echo")

    row = {
        **_identity(intake, approved),
        "unit_id": unit["id"],
        "unit_type": unit_type or unit["type"],
        "request": {"plan_sha256": request.get("plan_sha256"),
                    "request_id": request.get("request_id"),
                    "input_hash": request.get("input_hash")},
        "artifacts": artifacts,
        "lane_validation": {"lane": lane["lane"], "contract": lane["contract"],
                            "state": "passed",
                            **({"detail": lane["detail"]} if "detail" in lane else {})},
        "proof": _proof("draft_delivered"),
        "status": "draft_delivered",
    }
    if row["unit_type"] in ("email", "text", "automation"):
        row["draft_only"] = True
    if delivery_marker:
        row["delivery"] = delivery_marker
    return row


def _unit_receipts(ordered: List[Dict[str, Any]], intake: Dict[str, Any],
                   plan: Optional[Dict[str, Any]], pieces: Dict[str, Any],
                   plan_ref: Optional[Dict[str, Any]], run_dir: Path,
                   lane_deliveries: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Every planned unit's typed receipt, or every delivered piece's when page-only."""
    approved = intake["approval"]["hash"]
    if plan is None or plan_ref is None:
        return [_piece_receipt(piece, piece["slot"], "page", intake, approved, None, run_dir)
                for piece in ordered]
    by_slot = {piece["slot"]: piece for piece in ordered}
    lane_deliveries = lane_deliveries or {}
    deliveries = _page_deliveries(plan, pieces)
    rows: List[Dict[str, Any]] = []
    for unit in launch_plan_module.planned_units(plan):
        if unit["type"] == "page":
            delivery = deliveries.get(unit["id"]) or {}
            piece = by_slot.get(delivery.get("piece"))
            if piece is not None:
                rows.append(_piece_receipt(piece, unit["id"], "page", intake, approved,
                                           plan_ref["sha256"], run_dir))
            else:
                # A page another lane delivered: its lane receipt proves it, never the plan.
                rows.append(_lane_receipt(unit, lane_deliveries.get(unit["id"]), intake,
                                          approved, plan_ref["sha256"], plan_ref["path"],
                                          run_dir, unit_type="page",
                                          delivery_marker="declared"))
        else:
            rows.append(_lane_receipt(unit, lane_deliveries.get(unit["id"]), intake,
                                      approved, plan_ref["sha256"], plan_ref["path"],
                                      run_dir))
    return rows


def _resolve_delivery_scope(requested: Optional[str],
                            plan: Optional[Dict[str, Any]]) -> str:
    """Full-launch delivery always requires the shared plan. Unrequested scope follows the
    plan, so a plan-free package is never silently called a full launch."""
    if requested is None:
        return DELIVERY_SCOPE_FULL if plan is not None else DELIVERY_SCOPE_PAGE_ONLY
    if requested not in DELIVERY_LABELS:
        raise PackageError("AF-LAUNCH-SCOPE-UNKNOWN",
                           f"unknown delivery scope {requested!r}; use "
                           f"{DELIVERY_SCOPE_FULL!r} or {DELIVERY_SCOPE_PAGE_ONLY!r}")
    if requested == DELIVERY_SCOPE_FULL and plan is None:
        raise PackageError(
            "AF-LAUNCH-PLAN-REQUIRED",
            "full-launch delivery requires the shared launch plan (calendar and every planned "
            "unit); pass delivery_scope='page_only' (cli: --page-only) for a page-only package")
    if requested == DELIVERY_SCOPE_PAGE_ONLY and plan is not None:
        raise PackageError(
            "AF-LAUNCH-SCOPE-CONFLICT",
            "a page-only package cannot carry a launch plan; assemble a full launch instead")
    return requested


def assemble(run_dir: Path, intake: Dict[str, Any], route: Dict[str, Any],
             pieces: Dict[str, Any], source_root: Optional[Path] = None,
             council: Optional[Dict[str, Any]] = None,
             council_runner=None, require_designs: bool = False,
             image_plan: Optional[Dict[str, Any]] = None,
             to_confirm: Optional[List[Dict[str, Any]]] = None,
             design_approvals: Optional[Dict[str, Any]] = None,
             landing_pages: Optional[List[str]] = None,
             launch_plan: Optional[Dict[str, Any]] = None,
             deliveries: Optional[Dict[str, Any]] = None,
             delivery_scope: Optional[str] = None) -> Dict[str, Any]:
    """Write package-manifest.json + receipt.json into run_dir. Returns both records.

    Artifacts are copied into run_dir/pieces/<page_id>/ so the delivered package
    is self-contained: a manifest entry whose bytes sit outside the package is not
    a delivered piece. The declared sha256 is verified before and after the copy.
    Each file keeps its folder path inside its page (desktop-wireframes/, review-pdfs/ ...)
    and its own labeled name, so the client opens "upsell-1_DESKTOP_WIREFRAMES.pdf", not a
    renamed hash. Two different files that would land on one path are refused.

    require_designs makes AF-LAUNCH-PAGE-DESIGNS part of the package's own checks: every page
    must carry its full labeled set of desktop and mobile wireframes and mockups. image_plan,
    to_confirm and design_approvals are recorded so the delivery report can say which choices
    were defaults awaiting the client's confirmation.

    The Council planning step runs here (unless a record is supplied) and its
    result travels into the manifest and the receipt. It is advice: a not-ready
    result never blocks assembly.

    A shared launch plan (U-CONTRACT) makes the package fail closed: the Black
    Friday calendar is validated, every planned email, text, automation and the
    requested Conversation AI must arrive as a lane delivery receipt, and the
    calendar and completeness percentages travel into the manifest and the
    receipt. A delivery is the producing lane's own output record for one unit:
    {"state": "complete", "artifacts": [{"path", "sha256", "size"}],
    "lane_validation": {"lane", "contract", "state": "passed"},
    "request": {...}} with artifact bytes already staged inside run_dir. A bare
    state claim with no lane receipt is planning evidence, never delivery proof:
    the unit stays PLANNED and assembly refuses.

    delivery_scope names what is delivered. ``full_launch`` requires the shared
    plan: without it the seasonal calendar and the planned-unit checks would be
    skipped and a page-only package would pass as a Black Friday launch. With no
    plan the only honest scope is ``page_only``, which is recorded in the manifest
    and the receipt. When the caller names no scope it follows the plan, so a
    plan-free package is labelled page-only rather than silently accepted.
    """
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    source_root = Path(source_root).resolve() if source_root else run_dir.resolve()
    scope = _resolve_delivery_scope(delivery_scope, launch_plan)
    evidence = receipt_evidence(run_dir)
    if evidence["state"] in ("malformed", "unavailable"):
        raise PackageError("AF-LAUNCH-PKG-RECEIPTS",
                           f"Skill 49 receipt store is {evidence['state']}: {evidence.get('detail', '')}")

    if council is None:
        council = council_module.planning_step(intake, runner=council_runner)
    checkout = checkout_module.order_form_mapping(intake, route)
    if launch_plan is not None and launch_plan.get("launch_id") != intake["launch_id"]:
        raise PackageError("AF-LAUNCH-PLAN-LAUNCH",
                           f"the launch plan is for {launch_plan.get('launch_id')!r}, not "
                           f"{intake['launch_id']!r}")
    plan_record = _launch_plan_record(launch_plan, deliveries, pieces)

    ordered: List[Dict[str, Any]] = []
    for node in route["nodes"]:
        piece = pieces.get(node["role"])
        if piece is None:
            raise PackageError("AF-LAUNCH-PKG-MISSING",
                               f"route node {node['role']} has no delivered piece")
        ordered.append(_validate_piece(piece, node, intake))
    if landing_pages and set(landing_pages) == {"landing", "sales"} and "sales" not in pieces:
        raise PackageError("AF-LAUNCH-PKG-MISSING",
                           "the client's plan has both landing pages but no signature sales page piece "
                           "was delivered; a package one page short is not delivered")
    for slot, parent in EXTRA_SLOTS.items():
        if slot not in pieces:
            continue
        parent_node = next((n for n in route["nodes"] if n["role"] == parent), None)
        if parent_node is None:
            raise PackageError("AF-LAUNCH-PKG-SLOT",
                               f"a {slot} piece was delivered but the route has no {parent} page")
        node = {"role": parent, "role_instance": slot, "echoed_page_id": parent_node["page_id"],
                "page_id": route_module.route_law._page_id(intake["launch_id"], slot)}
        ordered.append(_validate_piece(pieces[slot], node, intake))

    for piece in ordered:
        copied: List[Dict[str, Any]] = []
        sources = []
        for art in piece["artifacts"]:
            src = Path(art["path"])
            sources.append(src if src.is_absolute() else source_root / src)
        base = Path(os.path.commonpath([str(p.parent) for p in sources])) if sources else source_root
        for art in piece["artifacts"]:
            src = Path(art["path"])
            if not src.is_absolute():
                src = source_root / src
            if not src.is_file():
                raise PackageError("AF-LAUNCH-PKG-ARTIFACT-MISSING",
                                   f"{piece['role']}: artifact {art['path']!r} does not exist")
            data = src.read_bytes()
            actual = _sha256_bytes(data)
            if actual != art["sha256"]:
                raise PackageError("AF-LAUNCH-PKG-HASH",
                                   f"{piece['role']}: artifact {art['path']!r} is {actual}, "
                                   f"declared {art['sha256']}")
            inside = src.resolve().relative_to(base.resolve())
            prefix = Path("pieces") / piece["page_id"]
            if inside.parts[:2] == prefix.parts:  # already laid out as pieces/<page_id>/...
                inside = Path(*inside.parts[2:])
            rel = str(prefix / inside)
            dest = run_dir / rel
            if dest.exists() and _sha256_file(dest) != actual:
                raise PackageError("AF-LAUNCH-PKG-COLLISION",
                                   f"{piece['role']}: two different files would both be delivered as {rel!r}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            if _sha256_file(dest) != art["sha256"]:
                raise PackageError("AF-LAUNCH-PKG-HASH",
                                   f"{piece['role']}: copied artifact {rel!r} did not verify")
            entry = {k: v for k, v in art.items() if k not in ("path", "sha256")}
            copied.append({"path": rel, "sha256": actual, **entry})
        piece["artifacts"] = copied

    intake_path = run_dir / "intake.json"
    route_path = run_dir / "route-graph.json"
    council_path = run_dir / "council-advice.json"
    checkout_path = run_dir / "checkout-mapping.json"
    intake_path.write_text(json.dumps(intake, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    route_path.write_text(json.dumps(route, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    council_path.write_text(json.dumps(council, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    checkout_path.write_text(json.dumps(checkout, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    plan_ref = calendar_ref = None
    if plan_record is not None:
        plan_path = run_dir / "launch-plan.json"
        calendar_path = run_dir / "launch-calendar.json"
        plan_path.write_text(json.dumps(launch_plan, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
        calendar_path.write_text(json.dumps(plan_record["calendar"], indent=2, sort_keys=True) + "\n",
                                 encoding="utf-8")
        plan_ref = {"path": "launch-plan.json", "sha256": _sha256_file(plan_path),
                    "contract": launch_plan_module.PLAN_CONTRACT_REF,
                    "contract_sha256": _sha256_path(REPO_ROOT / launch_plan_module.PLAN_CONTRACT_REF)}
        calendar_ref = {"path": "launch-calendar.json", "sha256": _sha256_file(calendar_path)}

    cross_sales = route.get("cross_sales") or {
        "relationships": [], "teaching": {"state": "pending"}, "route_node": False,
        "surface": "thank_you",
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "launcher": {"skill": SKILL_NAME, "version": SKILL_VERSION,
                     "skill_number_working": SKILL_NUMBER, "skill_number_final": False},
        "tenant_id": intake["tenant_id"],
        "location_id": intake["location_id"],
        "launch_id": intake["launch_id"],
        "revision": intake["revision"],
        "approved_plan_hash": intake["approval"]["hash"],
        "journey_mode": intake["journey_mode"],
        "delivery_scope": scope,
        "delivery_label": DELIVERY_LABELS[scope],
        "intake": {"path": "intake.json", "sha256": _sha256_file(intake_path)},
        "route_graph": {"path": "route-graph.json", "sha256": _sha256_file(route_path)},
        "pieces": ordered,
        "bindings": {
            "skill_entry": "SKILL.md",
            "cli": "launcher_core/cli.py",
            "decisions": "DECISIONS-PENDING.md",
            "entitlement_declaration": "entitlement-declaration.json",
        },
        "dependencies": {
            "checkout_contract": {"path": checkout_module.contract_ref(),
                                  "sha256": checkout.get("contract_sha256")},
            "council_entry": {"path": _repo_ref(council_module.entry_point()),
                              "sha256": _sha256_path(council_module.entry_point())},
        },
        "seams": [s["id"] for s in SEAMS],
        "decided": [d["id"] for d in DECIDED],
        "entitlement": intake["entitlement"],
        "offer_facts": offer_facts(intake),
        "council": {**council, "advice_path": "council-advice.json",
                    "advice_sha256": _sha256_file(council_path)},
        "checkout": {**checkout, "mapping_path": "checkout-mapping.json",
                     "mapping_sha256": _sha256_file(checkout_path)},
        "cross_sales": cross_sales,
        "live_effects": "none",
        "test_only": bool(intake.get("test_only", True)),
        "designs_required": bool(require_designs),
        "design_approvals": design_approvals or page_designs.default_approvals(),
        "image_plan": image_plan,
        "to_confirm": list(to_confirm or []),
        "assembled_at": _now(),
    }
    if plan_record is not None:
        manifest["launch_plan"] = {
            "plan": plan_ref,
            "calendar": calendar_ref,
            "completeness": plan_record["completeness"],
            "conversation_ai": plan_record["conversation_ai"],
        }
        manifest["launch_calendar"] = plan_record["calendar"]
    manifest_path = run_dir / "package-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    receipt = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "receipt_type": RECEIPT_TYPE,
        "receipt_schema": RECEIPT_SCHEMA_REF,
        "receipt_id": f"launcher-{intake['launch_id']}-r{intake['revision']}",
        "launch_id": intake["launch_id"],
        "tenant_id": intake["tenant_id"],
        "location_id": intake["location_id"],
        "revision": intake["revision"],
        "approved_plan_hash": intake["approval"]["hash"],
        "assembled_at": manifest["assembled_at"],
        "delivery_scope": scope,
        "delivery_label": DELIVERY_LABELS[scope],
        "manifest": {"path": "package-manifest.json", "sha256": _sha256_file(manifest_path)},
        "units": _unit_receipts(ordered, intake, launch_plan, pieces, plan_ref, run_dir,
                                lane_deliveries=deliveries),
        "lane_validations": [
            dict(LANE_VALIDATION),
            {"lane": "L05", "contract": checkout["contract"], "state": "recorded",
             "detail": f"Skill 79 validator {checkout['validator']['state']}"},
            {"lane": "L07", "contract": launch_plan_module.PLAN_CONTRACT_REF,
             "state": "passed" if plan_record is not None else "not_applicable",
             "detail": "calendar validated for the automation compiler"},
        ],
        "pieces": [
            {"page_id": p["page_id"], "role": p["role"], "slot": p["slot"], "status": p["status"],
             "proof_class": p["proof_class"], "artifact_count": len(p["artifacts"])}
            for p in ordered
        ],
        "receipt_evidence": evidence,
        "approvals": {"launch_plan_build": intake["approval"]["ref"]},
        "entitlement": {
            "basis": intake["entitlement"]["basis"],
            "requires_purchase": intake["entitlement"]["requires_purchase"],
            "billing": "none",
            "declaration_sha256": intake["entitlement"]["declaration"]["sha256"],
        },
        "council": {
            "step": council["step"],
            "skill": council["skill"],
            "entry_point": council["entry_point"],
            "status": council["status"],
            "advice_state": council["advice_state"],
            "blocks_build": False,
            "is_permission": False,
            "advice_path": "council-advice.json",
            "advice_sha256": _sha256_file(council_path),
        },
        "checkout": {
            "surface": checkout["surface"],
            "contract": checkout["contract"],
            "contract_sha256": checkout["contract_sha256"],
            "checkout_mode": checkout["checkout_mode"],
            "checkout_mode_state": checkout["checkout_mode_state"],
            "dispatch_adapter": False,
            "mapping_path": "checkout-mapping.json",
            "mapping_sha256": _sha256_file(checkout_path),
        },
        "offer_facts": offer_facts(intake),
        "cross_sales": cross_sales,
        "seams": [s["id"] for s in SEAMS],
        "decided": [d["id"] for d in DECIDED],
        "to_confirm": manifest["to_confirm"],
        "design_approvals": manifest["design_approvals"],
        "live_effects": "none",
        "test_only": manifest["test_only"],
    }
    if plan_record is not None:
        receipt["launch_plan"] = {
            "plan": plan_ref,
            "calendar": calendar_ref,
            "completeness": plan_record["completeness"],
            "conversation_ai": plan_record["conversation_ai"],
        }
        receipt["launch_calendar"] = plan_record["calendar"]
    (run_dir / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                                          encoding="utf-8")
    return {"manifest": manifest, "receipt": receipt, "launch_plan": plan_record,
            "manifest_path": str(manifest_path), "receipt_path": str(run_dir / "receipt.json")}
