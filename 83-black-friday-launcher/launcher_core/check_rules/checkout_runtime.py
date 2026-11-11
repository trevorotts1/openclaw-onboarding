"""AF-LAUNCH-CHECKOUT-RUNTIME: a checkout is not ready or live without its runtime binding.

Check-rule contract (see ``check_rules/__init__.py``): ``violations(manifest, root,
skill_root)`` returns one string per violation; an empty list passes.

Skill 79's purchase-safety rules (reconfirm on a changed price, the recovery choice,
grant once, paid edges only) exist as fixture models that refuse to run outside tests.
The only production host for them is Skill 44's purchase-event normalizer. So a checkout
page may claim ``ready_for_activation`` or ``live_verified`` only when the package holds
``runtime-binding.json``, the record that normalizer writes once it is installed::

    {"normalizer": "44/tools/siglaunch/normalizer", "schema_version": "...",
     "grant_policy": "once", "paid_edges_only": true,
     "verified_at": "<ISO-8601 with a zone>", "evidence_ref": "<where the proof lives>"}

Three facts are judged, each by name:

  1. THE CLAIM. A checkout piece in the manifest, or the receipt row of the checkout
     page, carries ``ready_for_activation`` or ``live_verified``.
  2. THE RECORD. ``runtime-binding.json`` is at the package root (a symlink out of the
     package does not count), is an object, and carries every key above with the values
     above. A key that names the launch (``tenant_id`` / ``location_id`` / ``launch_id``)
     must be this launch's, so one client's binding never covers another's checkout.
  3. THE SEAL. ``package.assemble`` records the file's digest in ``manifest["runtime_binding"]``
     whenever a claim is made (copying the file into the package when it was staged in the run
     the package is assembled from), so a binding written or swapped after assembly fails.

This rule proves the record is present, well formed, sealed and this launch's. The
producer (Skill 44, ``normalizer.py --emit-binding``) owns what the record attests.
``package.assemble`` calls the same functions, so a claim without a binding is refused
before anything is sealed, not only reported by ``check``.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

CODE = "AF-LAUNCH-CHECKOUT-RUNTIME"
BINDING_REL = "runtime-binding.json"
CLAIM_STATUSES = ("ready_for_activation", "live_verified")
CHECKOUT_PAGE_KINDS = ("checkout", "order")
# The spec spelling and the repository-relative spelling of the same directory.
NORMALIZERS = ("44/tools/siglaunch/normalizer",
               "44-convert-and-flow-operator/tools/siglaunch/normalizer")
GRANT_POLICY = "once"
IDENTITY_KEYS = ("tenant_id", "location_id", "launch_id")


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _aware_timestamp(value: Any) -> bool:
    if not _text(value):
        return False
    try:  # a trailing Z is spelled +00:00 so older interpreters read it too
        stamp = datetime.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return False
    return stamp.tzinfo is not None


def _is_checkout(piece: Any) -> bool:
    return isinstance(piece, dict) and (piece.get("role") == "checkout"
                                        or piece.get("page_kind") in CHECKOUT_PAGE_KINDS)


def piece_claims(pieces: Sequence[Any]) -> List[str]:
    """One sentence per checkout piece that claims a status only the runtime can back."""
    return [f"checkout piece {p.get('slot') or p.get('role')!r} claims {p['status']}"
            for p in pieces or [] if _is_checkout(p) and p.get("status") in CLAIM_STATUSES]


def receipt_claims(pieces: Sequence[Any], root: Path) -> List[str]:
    """The same claim made on the receipt: a checkout page's unit row cannot out-claim the manifest."""
    prefixes = tuple(f"pieces/{p['page_id']}/" for p in pieces or []
                     if _is_checkout(p) and _text(p.get("page_id")))
    try:
        rows = json.loads((Path(root) / "receipt.json").read_text(encoding="utf-8")).get("units")
    except (OSError, ValueError, AttributeError):
        return []  # a missing or unreadable receipt is already named by AF-LAUNCH-PKG-RECEIPT
    out: List[str] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or row.get("status") not in CLAIM_STATUSES:
            continue
        paths = [str(a.get("path") or "").replace("\\", "/")
                 for a in row.get("artifacts") or [] if isinstance(a, dict)]
        if prefixes and any(path.startswith(prefixes) for path in paths):
            out.append(f"receipt unit {row.get('unit_id')!r} claims {row['status']} for the checkout page")
    return out


def _load(root: Path) -> tuple[Optional[Dict[str, Any]], Optional[Path], str]:
    """(record, file, why not). The file must sit inside the package, not behind a link out of it."""
    target = Path(root) / BINDING_REL
    if not target.is_file():
        return None, None, f"the package holds no {BINDING_REL}"
    if not target.resolve().is_relative_to(Path(root).resolve()):
        return None, None, f"{BINDING_REL} resolves outside the package"
    try:
        doc = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, None, f"{BINDING_REL} is unreadable ({exc})"
    if not isinstance(doc, dict):
        return None, None, f"{BINDING_REL} must be an object"
    return doc, target, ""


def binding_problems(doc: Dict[str, Any], identity: Dict[str, Any]) -> List[str]:
    """Why this record is not the normalizer's binding; empty when it is."""
    out: List[str] = []
    if doc.get("normalizer") not in NORMALIZERS:
        out.append(f"normalizer is {doc.get('normalizer')!r}, not Skill 44's purchase-event "
                   f"normalizer ({NORMALIZERS[0]!r})")
    if not _text(doc.get("schema_version")):
        out.append("schema_version is missing")
    if doc.get("grant_policy") != GRANT_POLICY:
        out.append(f"grant_policy is {doc.get('grant_policy')!r}, not {GRANT_POLICY!r}; access is "
                   "granted once per purchase")
    if doc.get("paid_edges_only") is not True:
        out.append(f"paid_edges_only is {doc.get('paid_edges_only')!r}, not true; access is "
                   "granted on a paid edge only")
    if not _aware_timestamp(doc.get("verified_at")):
        out.append("verified_at is not an ISO-8601 timestamp with a zone")
    if not _text(doc.get("evidence_ref")):
        out.append("evidence_ref names no evidence")
    out.extend(f"{key} {doc[key]!r} is not this launch's {identity.get(key)!r}"
               for key in IDENTITY_KEYS if key in doc and doc[key] != identity.get(key))
    return out


def home(root: Path, source_root: Path) -> Path:
    """The folder that holds the binding: the package itself, else the run it is assembled from."""
    return Path(root) if (Path(root) / BINDING_REL).exists() else Path(source_root)


def seal(held_in: Path, root: Path) -> Dict[str, str]:
    """Bring the binding into the package (a byte copy when it was staged in the run) and return the
    record ``package.assemble`` carries in the manifest."""
    src, dest = Path(held_in) / BINDING_REL, Path(root) / BINDING_REL
    if src.resolve() != dest.resolve():
        dest.write_bytes(src.read_bytes())
    return {"path": BINDING_REL, "sha256": _sha256(dest)}


def problems(claims: Sequence[str], root: Path, identity: Dict[str, Any],
             sealed: Any = None, check_seal: bool = False) -> List[str]:
    """Why *claims* are not backed by a runtime binding; empty when none is made or the binding holds."""
    if not claims:
        return []
    lead = "; ".join(claims)
    doc, target, why = _load(root)
    if doc is None or target is None:
        return [f"{lead}, but {why}; the purchase-safety rules (reconfirm on a changed price, the "
                "recovery choice, grant once, paid edges only) run only in Skill 44's purchase-event "
                "normalizer, so a checkout is not ready or live until that runtime is bound"]
    found = [f"{lead}, but {BINDING_REL} {reason}" for reason in binding_problems(doc, identity)]
    if check_seal:
        if not isinstance(sealed, dict) or sealed.get("path") != BINDING_REL or not _text(sealed.get("sha256")):
            found.append(f"{lead}, but the manifest does not seal {BINDING_REL}; "
                         "assemble the package again with the binding in place")
        elif sealed["sha256"] != _sha256(target):
            found.append(f"{lead}, but {BINDING_REL} does not match the digest the manifest sealed; "
                         "the binding was changed after assembly")
    return found


def violations(manifest: Dict[str, Any], root: Path, skill_root: Path) -> List[str]:
    pieces = manifest.get("pieces") or []
    claims = piece_claims(pieces) + receipt_claims(pieces, root)
    return [f"{CODE}: {why}" for why in problems(
        claims, root, manifest, sealed=manifest.get("runtime_binding"), check_seal=True)]
