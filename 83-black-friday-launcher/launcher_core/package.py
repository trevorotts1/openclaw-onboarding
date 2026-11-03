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
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .constants import (
    COUNCIL_ENTRY_POINT,
    COUNCIL_NO_ADVICE_SUMMARY,
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
from . import image_plan as image_plan_module
from . import intake as intake_module
from . import launch_bridge
from . import launch_plan as launch_plan_module
from . import page_designs
from . import route as route_module
from .check_rules import delivery_units
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

# A package that carries open page blockers is never labelled a full launch (CHK-17): a page-result's
# own blockers (the order form is not built, the checkout pictures are placeholders) travel with it.
DELIVERY_LABEL_DESIGN_ONLY = ("design-only (open page blockers: the pages are drawn but not finished; "
                              "see each piece's blockers)")
# Open until the native checkout install (CHK-01) ships; recorded on every package.
SEAM_NATIVE_CHECKOUT_INSTALL = "native_checkout_install"

# ENF-03: the dispatch run this package is bound to. launch_bridge.run lays these down.
DISPATCH_MANIFEST_REL = "dispatch/dispatch-manifest.json"
LAUNCH_RECORD_REL = "launch.json"
# ENF-07: launch_bridge.run writes the run's own report; a bound package takes its to_confirm and
# landing_pages from it, never from the caller.
DISPATCH_REPORT_REL = "dispatch-report.json"
# ENF-09: landing_bridge.py writes bridge-receipt-<result stem>.json beside each landing result.
BRIDGE_RECEIPT_DIR = "bridge-receipts"
LANDING_REQUEST_ROLE = "landing"
# launch_bridge.run writes this (the writer half is carried to U-products-03); a strict binding requires it,
# so a changed entitlement basis or approval is caught. A non-strict run (found beside the pieces,
# test_only intake) verifies it when present and records 'absent' otherwise.
INTAKE_SNAPSHOT_REL = "intake-at-dispatch.json"
DISPATCH_STATE_BOUND = "bound"
DISPATCH_STATE_UNBOUND_FIXTURE = "unbound_fixture"
_REQUEST_RESULT_KEYS = ("request_id", "input_hash", "status", "proof_class", "independent_review",
                        "blockers", "author_session", "reviewer_session", "test_only")
_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")

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
    if piece["independent_review"] is True:
        reviewer = piece.get("reviewer_session")
        if not _nonempty_str(reviewer) or reviewer == piece["author_session"]:
            raise PackageError("AF-LAUNCH-PKG-REVIEW",
                               f"{role}: independent_review is true but no reviewer session is "
                               "recorded (or reviewer == author)")
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
        "reviewer_session": piece.get("reviewer_session"),
        # CHK-17: the page-result's own blockers travel with the piece, never dropped at packaging.
        "blockers": list(piece["blockers"]),
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
                        pieces: Dict[str, Any],
                        launch: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """The calendar + completeness record, or a named refusal when a planned unit is missing."""
    if plan is None:
        return None
    supplied = dict(deliveries or {})
    try:
        for unit_id, result in _page_deliveries(plan, pieces).items():
            supplied.setdefault(unit_id, result)
        record = launch_plan_module.record(plan, supplied, intake=launch)
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
        "blockers": list(piece.get("blockers") or []),
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
                   lane_deliveries: Optional[Dict[str, Any]] = None,
                   approved: Optional[str] = None) -> List[Dict[str, Any]]:
    """Every planned unit's typed receipt, or every delivered piece's when page-only."""
    approved = approved or intake["approval"]["hash"]
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
            if unit["type"] == "automation":
                # S44-21: a done.txt and three free-text strings never seal an automation.
                try:
                    builds = json.loads((run_dir / delivery_units.BUILDS_DOC).read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    builds = {}
                fails = delivery_units.automation_violations(
                    unit["id"], lane_deliveries.get(unit["id"]), plan.get("launch_id"),
                    delivery_units.reader_hashes(builds, plan.get("launch_id")), run_dir)
                if fails:
                    raise PackageError(delivery_units.CODE_AUTOMATION, "; ".join(fails))
            rows.append(_lane_receipt(unit, lane_deliveries.get(unit["id"]), intake,
                                      approved, plan_ref["sha256"], plan_ref["path"],
                                      run_dir))
    return rows


# --- ENF-03: assemble is bound to the dispatch run --------------------------------------------
# A package is the record of a dispatch that happened. The dispatch run's launch record, manifest,
# stored requests and stored results are the only authority: a piece file anyone could hand-write,
# a request id that is a free string and an approval hash that is a label are not.

def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _read_run_json(root: Path, rel: str, code: str, what: str) -> Any:
    path = root / rel
    if not path.is_file():
        raise PackageError(code, f"{what} {rel!r} is missing from the dispatch run")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PackageError(code, f"{what} {rel!r} is unreadable ({exc})") from exc


def _find_dispatch_root(dispatch_run: Optional[Path],
                        candidates: List[Path]) -> Tuple[Optional[Path], bool]:
    """(the dispatch run dir, named explicitly). None when no dispatch run is in evidence."""
    if dispatch_run is not None:
        root = Path(dispatch_run)
        if not (root / DISPATCH_MANIFEST_REL).is_file():
            raise PackageError("AF-LAUNCH-PKG-DISPATCH-MISSING",
                               f"the named dispatch run has no {DISPATCH_MANIFEST_REL}: a package "
                               "is assembled from a dispatch that happened")
        return root.resolve(), True
    for cand in candidates:
        if (Path(cand) / DISPATCH_MANIFEST_REL).is_file():
            return Path(cand).resolve(), False
    return None, False


def _dispatched_choices(launch: Dict[str, Any]) -> Dict[str, Any]:
    """The client's landing/extra page choices the dispatched record carries as plan-bound structure refs.

    They are not intake fields (the plan hash already binds them at dispatch), so the rebuilt record
    takes them from the dispatched one; everything the intake does own is still compared."""
    refs = {}
    for ref in launch.get("source_refs") or []:
        if isinstance(ref, str) and ref.startswith(launch_bridge.STRUCTURE_PREFIX) and "=" in ref:
            key, _, value = ref[len(launch_bridge.STRUCTURE_PREFIX):].partition("=")
            refs[key] = [v for v in value.split(",") if v]
    out: Dict[str, Any] = {}
    if refs.get("landing_pages"):
        out["landing_pages"] = refs["landing_pages"]
    if refs.get("extra_pages"):
        out["extra_pages"] = refs["extra_pages"]
    return out


def _expected_launch(intake: Dict[str, Any], dispatched: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The launch record this intake produces, exactly as launch_bridge.run derives it."""
    try:
        inputs, _ = image_plan_module.resolve(intake.get("image_plan"),
                                              test_only=bool(intake.get("test_only", True)))
        graph = route_module.compile_route(intake)
        return launch_bridge.to_launch_record(intake, graph, inputs, **_dispatched_choices(dispatched or {}))
    except (image_plan_module.ImagePlanError, route_module.RouteError) as exc:
        raise PackageError("AF-LAUNCH-PKG-PLAN-DRIFT",
                           f"the intake cannot be turned back into the dispatched launch record "
                           f"({exc})") from exc


def _drift_detail(launch: Dict[str, Any], expected: Dict[str, Any]) -> str:
    parts: List[str] = []
    for key in sorted(set(launch) | set(expected)):
        if key != "offers" and launch.get(key) != expected.get(key):
            parts.append(key)
    dispatched = {o.get("offer_id"): o for o in launch.get("offers") or []}
    now = {o.get("offer_id"): o for o in expected.get("offers") or []}
    for oid in sorted(set(dispatched) | set(now), key=str):
        a, b = dispatched.get(oid), now.get(oid)
        if a is None or b is None:
            parts.append(f"offer {oid!r} {'added' if a is None else 'removed'}")
            continue
        for key in sorted(set(a) | set(b)):
            if a.get(key) == b.get(key):
                continue
            if key == "prices":
                was = [x.get("amount_minor") for x in a.get(key) or []]
                is_now = [x.get("amount_minor") for x in b.get(key) or []]
                parts.append(f"offer {oid!r} price {was} was dispatched, {is_now} now")
            else:
                parts.append(f"offer {oid!r} {key}")
    return ", ".join(parts) or "the records differ"


def _bind_dispatch(root: Path, intake: Dict[str, Any], route: Dict[str, Any],
                   strict: bool) -> Dict[str, Any]:
    """Load the dispatch run and prove the intake, the route and the request ids are its own.

    strict (a named dispatch run, or any non-test run) also requires the intake's approval hash to
    BE the recomputed plan hash: the approved_plan_hash is computed, never accepted as a label.
    """
    dl = launch_bridge.substrate.dispatch()
    launch = _read_run_json(root, LAUNCH_RECORD_REL, "AF-LAUNCH-PKG-DISPATCH-MISSING", "launch record")
    manifest = _read_run_json(root, DISPATCH_MANIFEST_REL, "AF-LAUNCH-PKG-DISPATCH-MISSING",
                              "dispatch manifest")
    if not isinstance(launch, dict) or not isinstance(manifest, dict):
        raise PackageError("AF-LAUNCH-PKG-DISPATCH-PLAN",
                           "the launch record and the dispatch manifest must be objects")
    fails = launch_bridge.check_launch_record(launch)
    if fails:
        raise PackageError("AF-LAUNCH-PKG-DISPATCH-PLAN",
                           "Skill 49 does not accept the dispatched launch record: " + "; ".join(fails))
    plan_hash = dl.vlp.plan_document_hash(launch)
    if manifest.get("plan_document_hash") != plan_hash:
        raise PackageError("AF-LAUNCH-PKG-DISPATCH-PLAN",
                           "dispatch-manifest.json names a plan hash that is not the recomputed hash "
                           f"of launch.json ({plan_hash})")
    if (manifest.get("launch_id"), manifest.get("revision")) != (launch.get("launch_id"),
                                                                 launch.get("revision")):
        raise PackageError("AF-LAUNCH-PKG-DISPATCH-PLAN",
                           "dispatch-manifest.json is for another launch or revision than launch.json")
    report = _read_run_json(root, DISPATCH_REPORT_REL, "AF-LAUNCH-PKG-DISPATCH-REPORT", "dispatch report")
    if not (isinstance(report, dict) and isinstance(report.get("to_confirm"), list)
            and isinstance(report.get("landing_pages"), list)):
        raise PackageError("AF-LAUNCH-PKG-DISPATCH-REPORT",
                           "the dispatch report must carry to_confirm and landing_pages lists")
    expected = _expected_launch(intake, launch)
    if _canonical(expected) != _canonical(launch):
        raise PackageError("AF-LAUNCH-PKG-PLAN-DRIFT",
                           "the intake no longer produces the launch record that was dispatched and "
                           f"approved: {_drift_detail(launch, expected)}")
    plan_hash_matches = intake["approval"]["hash"] == plan_hash
    if strict and not plan_hash_matches:
        raise PackageError("AF-LAUNCH-PKG-APPROVAL-HASH",
                           "the intake's approval hash is not the recomputed plan hash "
                           f"({plan_hash}); approved_plan_hash is computed, never a free string")

    snapshot_state = "absent"
    snapshot_path = root / INTAKE_SNAPSHOT_REL
    if strict and not snapshot_path.is_file():
        raise PackageError("AF-LAUNCH-PKG-INTAKE-MISSING",
                           "the dispatch run carries no intake-at-dispatch.json, so the entitlement "
                           "basis and approval it was dispatched with cannot be proven; re-dispatch "
                           "the run")
    if snapshot_path.is_file():
        try:
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise PackageError("AF-LAUNCH-PKG-INTAKE-DRIFT",
                               f"{INTAKE_SNAPSHOT_REL} is unreadable or invalid ({exc})") from exc
        if not isinstance(snapshot, dict):
            raise PackageError("AF-LAUNCH-PKG-INTAKE-DRIFT", f"{INTAKE_SNAPSHOT_REL} is not an object")
        try:  # launch_bridge.run writes the validated intake; a raw payload is validated here
            snapshot = intake_module.validate(snapshot)
        except intake_module.IntakeError:
            pass  # already normalized: the comparison below catches any difference
        changed = sorted(k for k in set(snapshot) | set(intake) if snapshot.get(k) != intake.get(k))
        if changed:
            raise PackageError("AF-LAUNCH-PKG-INTAKE-DRIFT",
                               "the intake differs from the one the run was dispatched with in: "
                               + ", ".join(changed))
        snapshot_state = "verified"

    requests: Dict[str, Dict[str, Any]] = {}
    for entry in manifest.get("requests") or []:
        role, page_id = entry.get("page_role"), entry.get("page_id")
        input_hash = dl.request_input_hash(launch, page_id, role)
        if entry.get("input_hash") != input_hash \
                or entry.get("request_id") != dl.dispatch_key(launch, role, input_hash):
            raise PackageError("AF-LAUNCH-PKG-REQUEST",
                               f"dispatch-manifest.json request for {role!r} is not the one the "
                               "plan hash derives")
        stored = _read_run_json(root, f"dispatch/request-{role}.json", "AF-LAUNCH-PKG-REQUEST",
                                "stored page request")
        if any(stored.get(k) != entry.get(k) for k in ("request_id", "input_hash", "page_id")):
            raise PackageError("AF-LAUNCH-PKG-REQUEST",
                               f"the stored request for {role!r} disagrees with dispatch-manifest.json")
        requests[role] = {**entry, "stored": stored}
    route_roles = {n["role"]: n["page_id"] for n in route["nodes"]}
    if set(requests) != set(route_roles) \
            or any(requests[r]["page_id"] != pid for r, pid in route_roles.items()):
        raise PackageError("AF-LAUNCH-PKG-REQUEST",
                           "the dispatched requests are not this route's pages: dispatched "
                           f"{sorted(requests)}, route {sorted(route_roles)}")
    return {
        "state": DISPATCH_STATE_BOUND, "root": root, "plan_document_hash": plan_hash,
        "requests": requests, "plan_hash_matches": plan_hash_matches,
        "to_confirm": report["to_confirm"], "landing_pages": report["landing_pages"],
        "landing_results": {},
        "record": {
            "dispatch_report": {"path": DISPATCH_REPORT_REL,
                                "sha256": _sha256_file(root / DISPATCH_REPORT_REL)},
            "state": DISPATCH_STATE_BOUND,
            "dispatch_manifest": {"path": DISPATCH_MANIFEST_REL,
                                  "sha256": _sha256_file(root / DISPATCH_MANIFEST_REL)},
            "launch": {"path": LAUNCH_RECORD_REL, "sha256": _sha256_file(root / LAUNCH_RECORD_REL)},
            "plan_document_hash": plan_hash,
            "requests": [{"page_role": r, "request_id": requests[r]["request_id"],
                          "input_hash": requests[r]["input_hash"]} for r in sorted(requests)],
            "intake_approval_hash_is_plan_hash": plan_hash_matches,
            "intake_snapshot": snapshot_state,
        },
    }


def _receipts_module():
    return launch_bridge.substrate.load("49-signature-funnel/scripts/collect_launch_receipts.py",
                                        "launcher_collect_launch_receipts")


def _bind_piece(binding: Dict[str, Any], raw: Any, request_role: str, slot: str,
                extra: bool) -> None:
    """One piece is the dispatch's own answer to its own request, not a hand-written file."""
    if not isinstance(raw, dict):
        return  # _validate_piece names the shape fault
    request = binding["requests"].get(request_role)
    if request is None:
        raise PackageError("AF-LAUNCH-PKG-REQUEST",
                           f"{slot}: dispatch-manifest.json has no request for {request_role!r}")
    if raw.get("request_id") != request["request_id"]:
        known = raw.get("request_id") in {r["request_id"] for r in binding["requests"].values()}
        raise PackageError("AF-LAUNCH-PKG-REQUEST",
                           f"{slot}: request_id {raw.get('request_id')!r} "
                           + ("belongs to another page's request" if known
                              else "is not in dispatch-manifest.json")
                           + f"; the {request_role} request is {request['request_id']!r}")
    if raw.get("input_hash") != request["input_hash"]:
        raise PackageError("AF-LAUNCH-PKG-REQUEST",
                           f"{slot}: input_hash {raw.get('input_hash')!r} is not the dispatched "
                           f"request's {request['input_hash']!r}")
    stored_request = dict(request["stored"])
    if extra and raw.get("page_id") != stored_request.get("page_id"):
        stored_request.pop("page_id", None)  # a slot page rides on its parent's request
    fails = _receipts_module().validate_result(raw, stored_request)
    if fails:
        raise PackageError("AF-LAUNCH-PKG-ECHO",
                           f"{slot}: the result does not echo its dispatched request: "
                           + "; ".join(fails))
    dispatch_dir = binding["root"] / "dispatch"
    names = ([f"page-result-{slot}.json", f"result-{request_role}.json"] if extra
             else [f"result-{request_role}.json"])
    stored_path = next((dispatch_dir / n for n in names if (dispatch_dir / n).is_file()), None)
    if stored_path is None:
        raise PackageError("AF-LAUNCH-PKG-RESULT",
                           f"{slot}: the dispatch run stored no result for it ({names[0]})")
    try:
        stored = json.loads(stored_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PackageError("AF-LAUNCH-PKG-RESULT", f"{slot}: stored result unreadable ({exc})") from exc
    if request_role == LANDING_REQUEST_ROLE:
        binding["landing_results"][slot] = stored_path
    drifted = [k for k in _REQUEST_RESULT_KEYS if raw.get(k) != stored.get(k)]
    if drifted:
        raise PackageError("AF-LAUNCH-PKG-RESULT",
                           f"{slot}: the piece differs from the dispatch's stored result in "
                           + ", ".join(drifted))
    have = {(a.get("path"), a.get("sha256")) for a in stored.get("artifacts") or []
            if isinstance(a, dict)}
    for art in raw.get("artifacts") or []:
        if not isinstance(art, dict) or (art.get("path"), art.get("sha256")) not in have:
            raise PackageError("AF-LAUNCH-PKG-RESULT",
                               f"{slot}: artifact {art.get('path') if isinstance(art, dict) else art!r} "
                               "is not one the dispatch produced")


BRIDGE_RECEIPT_CODE = "AF-LAUNCH-PKG-BRIDGE-RECEIPT"


def bridge_receipt_violations(receipt: Any, delivery: bool) -> List[str]:
    """ENF-09: why a landing result's bridge-receipt sidecar (landing_bridge.py) is not a finished
    page. Plain sentences; the caller prefixes the code. Shared by assemble and check."""
    if not isinstance(receipt, dict):
        return ["the bridge receipt is not a JSON object"]
    fails: List[str] = []
    for prefix, label in (("", "the landing page"), ("opt_in_", "the opt-in landing page")):
        if prefix and not any(k.startswith(prefix) for k in receipt):
            continue
        if receipt.get(f"{prefix}receipt_validation") == "vendored_schema_fallback":
            fails.append(f"{label} was validated by the vendored schema fallback, not Skill 49's own "
                         "validator")
        # a run that declares itself a draft has its gate open by design; only a delivery refuses that (below)
        if (f"{prefix}pipeline_exit" in receipt or not prefix) and not (receipt.get("draft") is True and not delivery):
            if receipt.get(f"{prefix}pipeline_exit") != 0:
                fails.append(f"{label}'s production stage gate exited "
                             f"{receipt.get(f'{prefix}pipeline_exit')!r}, not 0 (production is not closed)")
    if delivery and receipt.get("draft") is not False:
        fails.append("the landing page is a draft (its production gate is open), and a delivery "
                     "package is never a draft")
    return fails


def _bind_bridge_receipts(binding: Dict[str, Any], delivery: bool) -> List[Tuple[Path, bytes]]:
    """Read the sidecar beside every landing result the dispatch stored and refuse a bad one.

    A sidecar that is present is always judged. One that is absent refuses a client delivery
    only: a hand-built test run has none (its consumer is a free fake, not landing_bridge.py).
    Returns the (package-relative path, bytes) pairs assemble copies into the package.
    """
    kept: List[Dict[str, Any]] = []
    files: List[Tuple[Path, bytes]] = []
    for slot, result_path in sorted(binding["landing_results"].items()):
        sidecar = result_path.with_name(f"bridge-receipt-{result_path.stem}.json")
        if not sidecar.is_file():
            if delivery:
                raise PackageError(BRIDGE_RECEIPT_CODE,
                                   f"{slot}: the landing result has no {sidecar.name}, so a draft or a "
                                   "vendored-schema fallback cannot be ruled out")
            continue
        raw = sidecar.read_bytes()
        try:
            doc = json.loads(raw.decode("utf-8"))
        except (OSError, ValueError) as exc:
            raise PackageError(BRIDGE_RECEIPT_CODE, f"{slot}: {sidecar.name} is unreadable ({exc})") from exc
        fails = bridge_receipt_violations(doc, delivery)
        if fails:
            raise PackageError(BRIDGE_RECEIPT_CODE, f"{slot}: " + "; ".join(fails))
        rel = Path(BRIDGE_RECEIPT_DIR) / sidecar.name
        kept.append({"slot": slot, "path": str(rel), "sha256": _sha256_bytes(raw)})
        files.append((rel, raw))
    binding["record"]["bridge_receipts"] = kept
    return files


def _verify_design_waiver(waiver: Any, approved_hash: str) -> Dict[str, Any]:
    """STR-01: designs may be waived only by a recorded owner approval bound to THIS plan hash."""
    if not isinstance(waiver, Mapping) or not _nonempty_str(waiver.get("approval_ref")):
        raise PackageError("AF-LAUNCH-PKG-DESIGN-WAIVER",
                           "assembling without the page designs needs a verified owner approval "
                           "(design_waiver with an approval_ref); none was supplied")
    if waiver.get("subject_type") != "design_waiver" or waiver.get("revoked") is True \
            or not _nonempty_str(waiver.get("owner_identity_ref")):
        raise PackageError("AF-LAUNCH-PKG-DESIGN-WAIVER",
                           "the design waiver must be an unrevoked design_waiver approval from a "
                           "named owner")
    if waiver.get("subject_hash") != approved_hash:
        raise PackageError("AF-LAUNCH-PKG-DESIGN-WAIVER",
                           "the design waiver approves another plan hash than this package's")
    return {"approval_ref": waiver["approval_ref"], "subject_hash": approved_hash,
            "owner_identity_ref": waiver["owner_identity_ref"]}


def _paid_image_renders(ordered: List[Dict[str, Any]]) -> int:
    """Picture files a paid provider rendered: the one live effect an offline build can have."""
    count = 0
    for piece in ordered:
        for art in piece["artifacts"]:
            kind = str(art.get("kind") or "")
            image = kind.endswith("_section") or kind == "board" \
                or str(art["path"]).lower().endswith(_IMAGE_SUFFIXES)
            provider = art.get("provider") or piece.get("image_provider")
            if image and provider and provider != "stub":
                count += 1
    return count



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


def _landing_run_roots(dispatch_root: Optional[Path]) -> List[Path]:
    """The landing bridge's run folder(s), from the config the dispatch wrote beside its run. The bridge lists
    its files relative to that folder (an opt-in run's carry its folder name, so they resolve from its parent)."""
    if dispatch_root is None:
        return []
    try:
        landing = json.loads((Path(dispatch_root) / "dispatch" / "landing-bridge.json")
                             .read_text(encoding="utf-8")).get("landing")
    except (OSError, ValueError, AttributeError):
        return []
    if not isinstance(landing, dict) or not landing.get("run_dir"):
        return []
    roots = [Path(landing["run_dir"])]
    opt_in = landing.get("opt_in")
    if isinstance(opt_in, dict) and opt_in.get("run_dir"):
        roots.append(Path(opt_in["run_dir"]).parent)
    return roots


def _artifact_source(path: str, source_root: Path, landing_roots: Sequence[Path]) -> Path:
    """Where a piece's artifact lives: absolute as given, else beside the run, else in the landing run folder."""
    src = Path(path)
    if src.is_absolute():
        return src
    if not (source_root / src).is_file():
        src = next((r / src for r in landing_roots if (r / src).is_file()), src)
        if src.is_absolute():
            return src
    return source_root / src


REPO_FIXTURE_DIR = "stand-in-inputs"  # where a test run's repo fixture is laid out inside its page folder


def _is_repo_fixture(src: Path, run_roots: Sequence[Path]) -> bool:
    """True for a repo fixture or test file: inside the skill repository under a fixtures/ or tests/ folder
    and not inside the run itself. A client package must never name one by its repo path (F7)."""
    src = src.resolve()
    if any(src.is_relative_to(Path(r).resolve()) for r in run_roots):
        return False
    try:
        parts = src.relative_to(REPO_ROOT.resolve()).parts[:-1]
    except ValueError:
        return False
    return "fixtures" in parts or "tests" in parts


def assemble(run_dir: Path, intake: Dict[str, Any], route: Dict[str, Any],
             pieces: Dict[str, Any], source_root: Optional[Path] = None,
             council: Optional[Dict[str, Any]] = None,
             council_runner=None, require_designs: Optional[bool] = None,
             image_plan: Optional[Dict[str, Any]] = None,
             to_confirm: Optional[List[Dict[str, Any]]] = None,
             design_approvals: Optional[Dict[str, Any]] = None,
             landing_pages: Optional[List[str]] = None,
             launch_plan: Optional[Dict[str, Any]] = None,
             deliveries: Optional[Dict[str, Any]] = None,
             delivery_scope: Optional[str] = None,
             dispatch_run: Optional[Path] = None,
             design_waiver: Optional[Dict[str, Any]] = None,
             checkout_readback: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Write package-manifest.json + receipt.json into run_dir. Returns both records.

    Artifacts are copied into run_dir/pieces/<page_id>/ so the delivered package
    is self-contained: a manifest entry whose bytes sit outside the package is not
    a delivered piece. The declared sha256 is verified before and after the copy.
    Each file keeps its folder path inside its page (desktop-wireframes/, review-pdfs/ ...)
    and its own labeled name, so the client opens "upsell-1_DESKTOP_WIREFRAMES.pdf", not a
    renamed hash. Two different files that would land on one path are refused.

    require_designs makes AF-LAUNCH-PAGE-DESIGNS part of the package's own checks: every page
    must carry its full labeled set of desktop and mobile wireframes and mockups. Explicit False
    (the CLI's --allow-no-designs) always needs a verified design_waiver bound to the approved hash.
    An unchosen value (None) is designs required for any dispatched or live package, and stays
    not-required only for a hand-built test fixture with no dispatch run (recorded
    dispatch_binding.state = "unbound_fixture"). checkout_readback, when given, is passed to
    checkout.order_form_mapping (CHK-10). image_plan,
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

    Bound to the dispatch (ENF-03). ``dispatch_run`` names the run dir that holds launch.json and
    dispatch/dispatch-manifest.json (when omitted, ``source_root`` or ``run_dir`` is used if it holds
    them). The plan hash is RECOMPUTED from launch.json; the intake must re-derive that launch record
    (a changed price or offer is AF-LAUNCH-PKG-PLAN-DRIFT); every piece must carry the manifest's
    request_id and input_hash for its role, echo its stored request (collect_launch_receipts.
    validate_result) and be the dispatch's own stored result (AF-LAUNCH-PKG-REQUEST / -ECHO /
    -RESULT). approved_plan_hash is that computed hash, never the intake's string. A named
    ``dispatch_run``, or any non-test intake, also requires the intake's approval hash to equal it.
    Hand-built fixtures with no dispatch run keep assembling only for a test_only intake and are
    recorded ``dispatch_binding.state = "unbound_fixture"``; a live intake without one refuses.

    A bound package takes ``to_confirm`` and ``landing_pages`` from the run's dispatch-report.json and
    refuses without it (AF-LAUNCH-PKG-DISPATCH-REPORT); a caller's list that differs is refused too.
    Each landing result's bridge-receipt sidecar is judged (AF-LAUNCH-PKG-BRIDGE-RECEIPT): a vendored-schema
    fallback or a non-zero pipeline exit refuses, a draft refuses a delivery, and a missing sidecar refuses a
    client delivery. A client delivery (test_only false) also needs Skill 49's live receipt store to verify.

    Open page blockers travel with each piece into the manifest and receipt units. A full launch
    refuses to assemble while any are open (AF-LAUNCH-PKG-BLOCKERS); a page-only package is labelled
    design-only. ``require_designs=False`` needs a verified ``design_waiver`` bound to the plan hash.
    A client delivery (a dispatched full launch, or any non-test intake) needs Skill 49's lane
    receipts in the store; live_effects names the paid picture renders instead of a constant.
    """
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    source_root = Path(source_root).resolve() if source_root else run_dir.resolve()
    # ENF-24: a graph handed straight to assemble must hold doc 02 section 4 before anything is written.
    law = route_module.route_law.graph_violations(route_module.launch_record(intake), route)
    if law:
        raise PackageError("AF-LAUNCH-ROUTE-LAW",
                           "the route graph breaks doc 02 section 4: " + "; ".join(law))
    scope = _resolve_delivery_scope(delivery_scope, launch_plan)
    open_raw = {slot: piece["blockers"] for slot, piece in pieces.items()
                if isinstance(piece, dict) and isinstance(piece.get("blockers"), list)
                and piece["blockers"]}
    if open_raw and scope == DELIVERY_SCOPE_FULL:
        raise PackageError(
            "AF-LAUNCH-PKG-BLOCKERS",
            "a full launch cannot carry open page blockers (assemble a page-only, design-only "
            "package instead): " + "; ".join(
                f"{slot}: {json.dumps(b, sort_keys=True, default=str)}" for slot, b in open_raw.items()))
    test_only = bool(intake.get("test_only", True))
    root, explicit = _find_dispatch_root(dispatch_run, [source_root, run_dir.resolve()])
    binding = None
    if root is not None:
        binding = _bind_dispatch(root, intake, route, strict=explicit or not test_only)
        approved = binding["plan_document_hash"]
        dispatch_record = binding["record"]
        # ENF-07: the run's own dispatch-report.json is authoritative for what was defaulted and which
        # landing pages were planned; a caller's list that differs is refused, never believed.
        for name, given, run_value in (("to_confirm", to_confirm, binding["to_confirm"]),
                                       ("landing_pages", landing_pages, binding["landing_pages"])):
            if given is not None and list(given) != run_value:
                raise PackageError("AF-LAUNCH-PKG-DISPATCH-REPORT",
                                   f"{name} differs from the dispatch run's {DISPATCH_REPORT_REL}")
        to_confirm, landing_pages = binding["to_confirm"], binding["landing_pages"]
    else:
        if not test_only:
            raise PackageError("AF-LAUNCH-PKG-DISPATCH-MISSING",
                               "a live (non-test) package is assembled from a dispatch run: no "
                               f"{DISPATCH_MANIFEST_REL} was found beside the pieces")
        approved = intake["approval"]["hash"]
        dispatch_record = {"state": DISPATCH_STATE_UNBOUND_FIXTURE,
                           "detail": "no dispatch run: hand-built test fixture, not a dispatched build"}
    evidence = receipt_evidence(run_dir)
    if evidence["state"] in ("malformed", "unavailable"):
        raise PackageError("AF-LAUNCH-PKG-RECEIPTS",
                           f"Skill 49 receipt store is {evidence['state']}: {evidence.get('detail', '')}")
    if not test_only:
        # ENF-17: the live store must verify (every line harness-signed), never the recorded word.
        module = _load_receipt_module()
        verify = getattr(module, "verify_delivery_store", None)
        if not callable(verify):
            raise PackageError("AF-LAUNCH-PKG-RECEIPTS",
                               "Skill 49's receipt module has no verify_delivery_store")
        store_ok, store_detail = verify(run_dir)
        if not store_ok:
            raise PackageError("AF-LAUNCH-PKG-RECEIPTS", store_detail)
    client_delivery = (binding is not None and scope == DELIVERY_SCOPE_FULL) or not test_only
    if client_delivery and (evidence["state"] != "verified" or not evidence.get("entries")):
        raise PackageError("AF-LAUNCH-PKG-RECEIPTS",
                           f"a client delivery needs Skill 49's lane receipts; the store is "
                           f"{evidence['state']!r} with {evidence.get('entries', 0)} entries")

    if council is None:
        council = council_module.planning_step(intake, runner=council_runner)
    checkout = checkout_module.order_form_mapping(
        intake, route, **({"readback": checkout_readback} if checkout_readback is not None else {}))
    if launch_plan is not None and launch_plan.get("launch_id") != intake["launch_id"]:
        raise PackageError("AF-LAUNCH-PLAN-LAUNCH",
                           f"the launch plan is for {launch_plan.get('launch_id')!r}, not "
                           f"{intake['launch_id']!r}")
    plan_record = _launch_plan_record(launch_plan, deliveries, pieces,
                                      {**intake, "approved_plan_hash": approved})

    ordered: List[Dict[str, Any]] = []
    for node in route["nodes"]:
        piece = pieces.get(node["role"])
        if piece is None:
            raise PackageError("AF-LAUNCH-PKG-MISSING",
                               f"route node {node['role']} has no delivered piece")
        ordered.append(_validate_piece(piece, node, intake))
        if binding is not None:
            _bind_piece(binding, piece, node["role"], node["role"], False)
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
        if binding is not None:
            _bind_piece(binding, pieces[slot], parent, slot, True)

    bridge_files: List[Tuple[Path, bytes]] = []
    if binding is not None:
        bridge_files = _bind_bridge_receipts(binding, delivery=client_delivery)

    designs_required = require_designs if require_designs is not None else (binding is not None or not test_only)
    waiver = None
    if require_designs is False:
        waiver = _verify_design_waiver(design_waiver, approved)
    if design_approvals is not None:
        # STR-25: an approved Design Board must resolve to a recorded Skill 71 approval, and a relative
        # reference is copied byte-for-byte into the package so `check` re-resolves the same record.
        bad = page_designs.approval_violations(design_approvals, source_root)
        if bad:
            raise PackageError(page_designs.CODE, "; ".join(bad))
        for entry in design_approvals.values():
            ref = entry.get("approval_ref") if isinstance(entry, dict) else None
            if not (isinstance(entry, dict) and entry.get("state") == "approved" and _nonempty_str(ref)):
                continue
            if Path(ref).is_absolute():
                continue  # recorded unchanged
            src = (source_root / ref).resolve()
            if not src.is_relative_to(source_root):
                raise PackageError(page_designs.CODE,
                                   f"approval record {ref!r} resolves outside the run it came from")
            dest = run_dir / ref
            if src != dest.resolve():
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(src.read_bytes())

    landing_roots = _landing_run_roots(root)
    for piece in ordered:
        copied: List[Dict[str, Any]] = []
        sources = [_artifact_source(art["path"], source_root, landing_roots) for art in piece["artifacts"]]
        # F7: a repo fixture (a test run's stand-in page copy) is never laid out by its repo path, and its
        # folders must not decide where the run's own files land. A client package refuses one outright.
        run_roots = [source_root, run_dir, *landing_roots]
        repo_fixture = [_is_repo_fixture(p, run_roots) for p in sources]
        if any(repo_fixture) and not test_only:
            raise PackageError("AF-LAUNCH-PKG-REPO-FIXTURE",
                               f"{piece['role']}: artifact "
                               f"{piece['artifacts'][repo_fixture.index(True)]['path']!r} is a repo fixture; "
                               "a client package carries only files the run produced")
        own = [p for p, fx in zip(sources, repo_fixture) if not fx]
        base = Path(os.path.commonpath([str(p.parent) for p in own])) if own else source_root
        for art, src, fx in zip(piece["artifacts"], sources, repo_fixture):
            if not src.is_file():
                raise PackageError("AF-LAUNCH-PKG-ARTIFACT-MISSING",
                                   f"{piece['role']}: artifact {art['path']!r} does not exist")
            data = src.read_bytes()
            actual = _sha256_bytes(data)
            if actual != art["sha256"]:
                raise PackageError("AF-LAUNCH-PKG-HASH",
                                   f"{piece['role']}: artifact {art['path']!r} is {actual}, "
                                   f"declared {art['sha256']}")
            prefix = Path("pieces") / piece["page_id"]
            if fx:
                inside = Path(REPO_FIXTURE_DIR) / src.name
            else:
                inside = src.resolve().relative_to(base.resolve())
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

    for rel, raw in bridge_files:
        (run_dir / rel).parent.mkdir(parents=True, exist_ok=True)
        (run_dir / rel).write_bytes(raw)
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

    open_blockers = [{"slot": p["slot"], "page_id": p["page_id"], "role": p["role"],
                      "blockers": p["blockers"]} for p in ordered if p["blockers"]]
    delivery_label = DELIVERY_LABELS[scope]
    if open_blockers:
        delivery_label = f"{DELIVERY_LABEL_DESIGN_ONLY}; {delivery_label}"
    if waiver is not None:
        delivery_label += f"; designs waived (owner approval {waiver['approval_ref']})"
    seams = [seam["id"] for seam in SEAMS]
    if SEAM_NATIVE_CHECKOUT_INSTALL not in seams:
        seams.append(SEAM_NATIVE_CHECKOUT_INSTALL)
    paid_renders = _paid_image_renders(ordered)
    live_effects = f"paid_image_renders:{paid_renders}" if paid_renders else "none"

    cross_sales = route.get("cross_sales") or {
        "relationships": [], "teaching": {"state": "pending"}, "route_node": False,
        "surface": "thank_you",
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "launcher": {"skill": SKILL_NAME, "version": SKILL_VERSION,
                     "skill_number_working": SKILL_NUMBER, "skill_number_final": True},
        "tenant_id": intake["tenant_id"],
        "location_id": intake["location_id"],
        "launch_id": intake["launch_id"],
        "revision": intake["revision"],
        "approved_plan_hash": approved,
        "dispatch_binding": dispatch_record,
        "journey_mode": intake["journey_mode"],
        "delivery_scope": scope,
        "delivery_label": delivery_label,
        "open_blockers": open_blockers,
        "design_waiver": waiver,
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
        "seams": seams,
        "decided": [d["id"] for d in DECIDED],
        "entitlement": intake["entitlement"],
        "offer_facts": offer_facts(intake),
        "council": {**council, "advice_path": "council-advice.json",
                    "advice_sha256": _sha256_file(council_path)},
        "checkout": {**checkout, "mapping_path": "checkout-mapping.json",
                     "mapping_sha256": _sha256_file(checkout_path)},
        "cross_sales": cross_sales,
        "live_effects": live_effects,
        "test_only": test_only,
        "designs_required": designs_required,
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
        "approved_plan_hash": approved,
        "dispatch_binding": dispatch_record,
        "assembled_at": manifest["assembled_at"],
        "delivery_scope": scope,
        "delivery_label": delivery_label,
        "open_blockers": open_blockers,
        "design_waiver": waiver,
        "manifest": {"path": "package-manifest.json", "sha256": _sha256_file(manifest_path)},
        "units": _unit_receipts(ordered, intake, launch_plan, pieces, plan_ref, run_dir,
                                lane_deliveries=deliveries, approved=approved),
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
            "council_session_held": council.get("council_session_held") is True,
            "client_summary": council.get("client_summary") or COUNCIL_NO_ADVICE_SUMMARY,
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
        "seams": seams,
        "decided": [d["id"] for d in DECIDED],
        "to_confirm": manifest["to_confirm"],
        "design_approvals": manifest["design_approvals"],
        "live_effects": live_effects,
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
