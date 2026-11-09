"""F22 check rule: a delivered launch accounts for every linked destination.

Check-rule contract (see ``check_rules/__init__.py``): ``violations(manifest, root,
skill_root)`` returns one string per violation; an empty list passes.

What this rule refuses:

* a package whose recorded resource inventory no longer matches the intake it was
  assembled from (``AF-LAUNCH-LINKED-DRIFT``) — changed delivery facts are a new
  revision, never a silent edit under the old approval;
* a delivery/readiness CLAIM (``delivery_scope == full_launch`` or a live package)
  while a linked destination cannot be resolved — an ungoverned new page, an external
  destination with no ownership/access/link/product/entitlement/fulfillment evidence,
  a bump claimed as a page, or a design-only downsell claimed as a purchase route
  (``AF-LAUNCH-LINKED-BLOCKED``).

A page-only design package records the blockers and stays labelled design-only; the
independent work is not stopped, the readiness claim is. A package assembled before
this record existed is recomputed from its own intake file, so omitting the block
never hides a blocker.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .. import linked_delivery as ld

CODE_DRIFT = "AF-LAUNCH-LINKED-DRIFT"
CODE_BLOCKED = "AF-LAUNCH-LINKED-BLOCKED"


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _intake(manifest: Dict[str, Any], root: Path) -> Dict[str, Any]:
    path = (manifest.get("intake") or {}).get("path")
    if not path:
        return {}
    doc = _load(Path(root) / str(path))
    return doc if isinstance(doc, dict) else {}


def violations(manifest: Dict[str, Any], root: Path, skill_root: Path) -> List[str]:
    """The check_rules seam entry point. Empty list means every destination is accounted for."""
    root = Path(root)
    intake = _intake(manifest, root)
    if not intake:
        # Without the intake the inventory cannot be recomputed; a claim over an
        # unprovable inventory is a violation, a design-only package is not.
        if manifest.get("delivery_scope") == "full_launch" or manifest.get("test_only") is False:
            return [f"{CODE_DRIFT}: the package names no readable intake, so its linked "
                    "delivery destinations cannot be accounted for"]
        return []
    record = ld.resolve(intake)
    fails: List[str] = []

    recorded = manifest.get("linked_delivery") or {}
    recorded_path = recorded.get("path") if isinstance(recorded, dict) else None
    if recorded_path:
        written = _load(root / str(recorded_path))
        if not isinstance(written, dict):
            fails.append(f"{CODE_DRIFT}: the recorded resource inventory {recorded_path!r} "
                         "cannot be read")
        elif written.get("fingerprint") != record["fingerprint"]:
            fails.append(
                f"{CODE_DRIFT}: the linked delivery inventory changed after assembly "
                f"(recorded {written.get('fingerprint')}, now {record['fingerprint']}); "
                "a changed destination is a new revision, not an edit")

    claiming = manifest.get("delivery_scope") == "full_launch" or manifest.get("test_only") is False
    if record["blockers"] and claiming:
        fails.append(
            f"{CODE_BLOCKED}: this package claims delivery while "
            f"{len(record['blockers'])} linked destination(s) cannot be accounted for: "
            + "; ".join(b["operator_detail"] for b in record["blockers"]))
    return fails
