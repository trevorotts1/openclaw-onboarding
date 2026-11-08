"""F06 activation rule: a stage receipt is not a completion receipt.

Check-rule contract (see ``check_rules/__init__.py``): ``violations(manifest, root,
skill_root)`` returns one string per violation; an empty list passes.

``package.assemble`` writes the package's stage into ``activation.json``, apart from
the construction receipts, and carries that record plus its digest in
``package-manifest.json`` and ``receipt.json``. This rule is the other half of that
contract at VERIFICATION time (``check``, and recovery via
``verify_package_receipt``): without it the record is written but never re-proved, so
an edited ``activation.json`` — or a receipt that claims ``published`` with no
observed read-back and no recorded authority — would pass ``check`` and read as a
finished launch.

Four facts are separated here, exactly as the contract separates them:

  1. AUTHORIZATION PRECEDES THE STAGE. ``installed`` and ``published`` each need a
     recorded authority whose ``scope`` matches the stage and whose ``location_id`` is
     this launch's own; a ``test_only`` package never reaches either. A local/draft
     package carries no installation or publication authority at all.
  2. A STAGE IS NEVER PAST WHAT WAS AUTHORIZED. The achieved stage may not rank above
     ``desired_state``, and a pending stage must be the one still owed.
  3. EVIDENCE PROVES THE STAGE. An ``installed``/``published`` stage is re-proved from
     the recorded read-back through the SAME function ``package.assemble`` uses —
     observed canonical route, https page URL, ``observed_at``, the live
     ``page_type``/``page_version`` for a publication and the observed native record
     for an installation — bound to this package's pages and location.
  4. STAGE != COMPLETION. The activation record is its own file: it names the
     construction receipts it belongs to and never carries unit receipts of its own,
     so it can never be counted as the package being complete.

Nothing here re-implements a receipt system or a publisher. Every stage rule is read
from ``launcher_core.package`` and ``launcher_core.intake``, the modules that own it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

CODE = "AF-LAUNCH-ACTIVATION"

# What the manifest's activation block must carry. ``record`` is the sealed
# activation.json; the rest is the stage record itself.
REQUIRED_KEYS = ("desired_state", "achieved_state", "authority", "pending_stage",
                 "activation_pending", "readback", "source", "record")
# The keys activation.json and the manifest must agree on.
SHARED_KEYS = ("desired_state", "achieved_state", "authority", "pending_stage",
               "activation_pending", "readback", "source")
# A stage receipt is never a construction receipt: these belong to receipt.json.
CONSTRUCTION_ONLY_KEYS = ("units", "receipt_type", "receipt_id", "lane_validations")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _stage_rules():
    """(ACTIVATION_STATES, ACTIVATION_AUTHORITY_SCOPES, the read-back prover)."""
    from launcher_core import intake as intake_module
    from launcher_core import package as package_module
    return (package_module.ACTIVATION_STATES,
            intake_module.ACTIVATION_AUTHORITY_SCOPES,
            package_module._activation_readback_violations)


def violations(manifest: Dict[str, Any], root: Path, skill_root: Path) -> List[str]:
    stages, scopes, prove_readback = _stage_rules()
    root = Path(root).resolve()  # a symlinked /var vs /private/var root is the same package
    fails: List[str] = []
    activation = manifest.get("activation")
    if not isinstance(activation, dict):
        return [f"{CODE}-MISSING: the package carries no activation record; installation "
                "and publication are separate stages and must be recorded, not implied"]
    missing = [key for key in REQUIRED_KEYS if key not in activation]
    if missing:
        return [f"{CODE}-SHAPE: the activation record lacks {', '.join(missing)}"]

    desired = activation.get("desired_state")
    achieved = activation.get("achieved_state")
    if desired not in stages:
        fails.append(f"{CODE}-STATE: desired_state {desired!r} is not one of {list(stages)}")
    if achieved not in stages:
        fails.append(f"{CODE}-STATE: achieved_state {achieved!r} is not one of {list(stages)}")
    if fails:
        return fails  # every rule below needs two known stages

    # 1. the sealed record resolves, is inside the package, and has not been edited
    record = activation.get("record")
    record_doc: Dict[str, Any] | None = None
    if not isinstance(record, dict) or not _nonempty(record.get("path")):
        fails.append(f"{CODE}-RECORD: the activation record names no path")
    elif not _nonempty(record.get("sha256")):
        fails.append(f"{CODE}-RECORD: the activation record carries no sha256")
    else:
        target = (root / str(record["path"])).resolve()
        if not target.is_relative_to(root):
            fails.append(f"{CODE}-RECORD: {record['path']!r} escapes the package")
        elif not target.is_file():
            fails.append(f"{CODE}-RECORD: {record['path']!r} does not resolve; the stage "
                         "record the manifest and receipt name is missing")
        elif _sha256(target) != record["sha256"]:
            fails.append(f"{CODE}-RECORD: {record['path']!r} does not match the digest the "
                         "manifest and receipt recorded; the stage record was changed")
        else:
            try:
                loaded = json.loads(target.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                fails.append(f"{CODE}-RECORD: {record['path']!r} is unreadable ({exc})")
            else:
                if not isinstance(loaded, dict):
                    fails.append(f"{CODE}-RECORD: {record['path']!r} must be an object")
                else:
                    record_doc = loaded
    if record_doc is not None:
        fails.extend(_record_violations(activation, record_doc))
    fails.extend(_receipt_violations(manifest, root, activation))

    # 2. authorization precedes the stage, and the stage never passes it
    authority = activation.get("authority")
    waiting = activation.get("activation_pending") is True
    if achieved in scopes:
        if manifest.get("test_only") is not False:
            fails.append(f"{CODE}-TEST-ONLY: the package is test_only but claims "
                         f"{achieved!r}; a local/test package is never installed or live")
        if not isinstance(authority, dict):
            fails.append(f"{CODE}-AUTHORITY: {achieved!r} needs the recorded authorization "
                         "that covers this page and location; none is carried")
        else:
            want = scopes[achieved]
            if not _nonempty(authority.get("ref")):
                fails.append(f"{CODE}-AUTHORITY: the record names no approval ref")
            if authority.get("scope") != want:
                fails.append(f"{CODE}-AUTHORITY: {achieved!r} needs scope {want!r}, the "
                             f"record carries {authority.get('scope')!r}")
            if str(authority.get("location_id") or "").strip() \
                    != str(manifest.get("location_id") or "").strip():
                fails.append(f"{CODE}-AUTHORITY: the recorded authority covers location "
                             f"{authority.get('location_id')!r}, and this launch is "
                             f"{manifest.get('location_id')!r}")
    elif authority is not None and not (waiting and desired in scopes):
        # Recorded authority rides with the package while the authorized stage is still
        # owed: a pending publication legitimately carries it at a lower achieved stage.
        fails.append(f"{CODE}-AUTHORITY: {achieved!r} is construction only and carries no "
                     "installation or publication authority")

    # Only install and publication are gated by the authorization. Local preparation and
    # draft construction are what dispatch itself produces and are always allowed — a bound
    # dispatch IS ``draft_constructed`` even when the client never asked for more.
    if achieved in scopes and stages.index(achieved) > stages.index(desired):
        fails.append(f"{CODE}-SCOPE: the package claims {achieved!r} but the recorded "
                     f"authority covers only {desired!r}; never claim more than was authorized")

    pending = activation.get("activation_pending")
    if not isinstance(pending, bool):
        fails.append(f"{CODE}-PENDING: activation_pending must be a boolean")
    elif pending:
        if activation.get("pending_stage") != desired:
            fails.append(f"{CODE}-PENDING: the pending stage is "
                         f"{activation.get('pending_stage')!r}, not the authorized "
                         f"{desired!r}")
        if desired == achieved:
            fails.append(f"{CODE}-PENDING: {achieved!r} is recorded as both achieved and "
                         "still pending")
    elif activation.get("pending_stage") is not None:
        fails.append(f"{CODE}-PENDING: a pending stage is recorded but activation_pending "
                     "is false")

    # 3. observed evidence proves the achieved stage, bound to this package
    readback = activation.get("readback")
    if achieved in scopes:
        page_ids = [p.get("page_id") for p in manifest.get("pieces") or []
                    if isinstance(p, dict) and _nonempty(p.get("page_id"))]
        for why in prove_readback(readback, achieved, page_ids=page_ids,
                                 location_id=str(manifest.get("location_id") or "")):
            fails.append(f"{CODE}-READBACK: {achieved!r} is claimed but {why}")
    elif readback is not None:
        fails.append(f"{CODE}-READBACK: {achieved!r} is decided by the run itself and "
                     "carries no read-back; an observed read-back proves an installed or "
                     "published stage only")
    return fails


def _record_violations(activation: Dict[str, Any], record_doc: Dict[str, Any]) -> List[str]:
    """The sealed record is the same record the manifest carries, and is not a receipt."""
    fails: List[str] = []
    if record_doc.get("schema") != "launcher.activation/v1":
        fails.append(f"{CODE}-RECORD: the activation record schema is "
                     f"{record_doc.get('schema')!r}, not 'launcher.activation/v1'")
    for key in SHARED_KEYS:
        if record_doc.get(key) != activation.get(key):
            fails.append(f"{CODE}-RECORD: activation.json and the manifest disagree on "
                         f"{key!r}; the sealed record is not the one being claimed")
    carried = record_doc.get("construction_receipts")
    if not isinstance(carried, dict) or not carried:
        fails.append(f"{CODE}-RECORD: activation.json names no construction receipts; a "
                     "stage record belongs to the construction it was reached from")
    for key in CONSTRUCTION_ONLY_KEYS:
        if key in record_doc:
            fails.append(f"{CODE}-RECORD: activation.json carries {key!r}; a stage receipt "
                         "is not a completion receipt")
    return fails


def _receipt_violations(manifest: Dict[str, Any], root: Path,
                        activation: Dict[str, Any]) -> List[str]:
    """receipt.json carries the same stage block; a package cannot claim two stages."""
    path = Path(root) / "receipt.json"
    if not path.is_file():
        return []  # a missing receipt is already named by AF-LAUNCH-PKG-RECEIPT
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []  # an unreadable receipt is already named by AF-LAUNCH-PKG-RECEIPT
    if not isinstance(receipt, dict):
        return []
    if "activation" not in receipt:
        return [f"{CODE}-RECEIPT: receipt.json carries no activation record, so the stage "
                "it was delivered at cannot be read from the receipt"]
    if receipt.get("activation") != activation:
        return [f"{CODE}-RECEIPT: the receipt's activation record is not the manifest's; "
                "one package cannot claim two stages"]
    return []
