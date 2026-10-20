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
from typing import Any, Dict, List, Optional

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


def assemble(run_dir: Path, intake: Dict[str, Any], route: Dict[str, Any],
             pieces: Dict[str, Any], source_root: Optional[Path] = None,
             council: Optional[Dict[str, Any]] = None,
             council_runner=None, require_designs: bool = False,
             image_plan: Optional[Dict[str, Any]] = None,
             to_confirm: Optional[List[Dict[str, Any]]] = None,
             design_approvals: Optional[Dict[str, Any]] = None,
             landing_pages: Optional[List[str]] = None) -> Dict[str, Any]:
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
    """
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    source_root = Path(source_root).resolve() if source_root else run_dir.resolve()
    evidence = receipt_evidence(run_dir)
    if evidence["state"] in ("malformed", "unavailable"):
        raise PackageError("AF-LAUNCH-PKG-RECEIPTS",
                           f"Skill 49 receipt store is {evidence['state']}: {evidence.get('detail', '')}")

    if council is None:
        council = council_module.planning_step(intake, runner=council_runner)
    checkout = checkout_module.order_form_mapping(intake, route)

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
        "journey_mode": intake["journey_mode"],
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
    manifest_path = run_dir / "package-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    receipt = {
        "schema_version": SCHEMA_VERSION,
        "receipt_id": f"launcher-{intake['launch_id']}-r{intake['revision']}",
        "launch_id": intake["launch_id"],
        "tenant_id": intake["tenant_id"],
        "location_id": intake["location_id"],
        "revision": intake["revision"],
        "assembled_at": manifest["assembled_at"],
        "manifest": {"path": "package-manifest.json", "sha256": _sha256_file(manifest_path)},
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
    (run_dir / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                                          encoding="utf-8")
    return {"manifest": manifest, "receipt": receipt,
            "manifest_path": str(manifest_path), "receipt_path": str(run_dir / "receipt.json")}
