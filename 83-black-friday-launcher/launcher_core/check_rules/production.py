"""AF-LAUNCH-PRODUCTION: an approved page is a PRODUCTION page, with its hash on record (issue 4).

A package that stops at designs is honest about it; one that says a page was produced must be able to
prove it. This rule reads ``production/manifest.json`` (written by the `produce` stage) and fails when:

  * a page the manifest calls built has no ``production/<role>.html``, or the file's sha256 is not the one
    recorded (the page changed after it was produced);
  * the manifest is for a different test_only value than the package (a practice production cannot stand
    in for a client package, or the reverse);
  * on a package that is NOT test_only and `required`: any approved upsell_1 / downsell_1 / upsell_2 /
    thank_you piece has no built production page with a recorded sha256.

Before `produce` has run (no ``production/manifest.json`` and no record that the produce stage closed) the
seam call (`violations`) does not demand pages, so `check` still passes and reaches `produce`; once the
manifest exists or the state records produce closed, the seam demands them (required=True), so deleting
one page afterwards fails `check`. ``production_violations(..., required=True)`` is also what the produce
and install stages call, so neither can close or proceed without the pages (question WP-10a-2).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
from typing import Any, Dict, List

CODE = "AF-LAUNCH-PRODUCTION"
MANIFEST_REL = "production/manifest.json"
PRODUCED_ROLES = ("upsell_1", "downsell_1", "upsell_2", "thank_you")


def _approved_roles(manifest: Dict[str, Any]) -> List[str]:
    return [r for r in PRODUCED_ROLES
            if any(p.get("role") == r and not p.get("role_instance") for p in manifest.get("pieces") or [])]


def production_violations(manifest: Dict[str, Any], root: Path, *, required: bool) -> List[str]:
    root = Path(root)
    path = root / MANIFEST_REL
    test_only = manifest.get("test_only") is True
    approved = _approved_roles(manifest)
    if not path.is_file():
        if required and not test_only:
            return [f"{CODE}: the package has no {MANIFEST_REL}; {', '.join(approved) or 'its pages'} "
                    "were never produced"]
        return []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        pages = doc["pages"]
        if not isinstance(pages, dict):
            raise TypeError("pages is not an object")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [f"{CODE}: {MANIFEST_REL} cannot be read ({type(exc).__name__})"]
    fails: List[str] = []
    if bool(doc.get("test_only")) != test_only:
        fails.append(f"{CODE}: the production manifest says test_only {bool(doc.get('test_only'))} but the "
                     f"package says {test_only}; a practice production never stands in for a client package")
    for role, row in sorted(pages.items()):
        if not isinstance(row, dict) or row.get("state") != "built":
            continue
        target = root / "production" / str(row.get("file") or "")
        if not target.is_file():
            fails.append(f"{CODE}: {role} is recorded as built but production/{row.get('file')} is missing")
        elif hashlib.sha256(target.read_bytes()).hexdigest() != row.get("sha256"):
            fails.append(f"{CODE}: production/{row.get('file')} does not match the sha256 recorded when {role} "
                         "was produced (the page changed after it was built)")
    if required and not test_only:
        for role in approved:
            row = pages.get(role)
            if not isinstance(row, dict) or row.get("state") != "built" or not row.get("sha256"):
                why = row.get("reason") if isinstance(row, dict) and row.get("reason") else "no production page"
                fails.append(f"{CODE}: {role} is an approved piece but has no production/{role}.html with a "
                             f"recorded sha256 ({why})")
    return fails


def _state_records_produce_closed(manifest: Dict[str, Any]) -> bool:
    """True when the launch-event spool holds a stage_closed event for produce on this package's launch."""
    launch_id = str(manifest.get("launch_id") or "")
    if not launch_id:
        return False
    try:
        from ..constants import resolve_ref
        spec = importlib.util.spec_from_file_location(
            "launcher_production_rule_events", resolve_ref("shared-utils/signature_launch/launch_events.py"))
        events = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(events)
        spool = events._spool_dir(os.environ) / events.SPOOL_FILE
        for line in spool.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if (isinstance(row, dict) and row.get("launch_id") == launch_id
                    and row.get("event_type") == "stage_closed" and row.get("stage") == "produce"):
                return True
    except Exception:  # no spool, no loader: no record, so the manifest file alone decides
        return False
    return False


def violations(manifest: Dict[str, Any], root: Path, skill_root: Path) -> List[str]:
    """The check_rules seam: integrity always; completeness once produce has run (manifest or state)."""
    produced = (Path(root) / MANIFEST_REL).is_file() or _state_records_produce_closed(manifest)
    return production_violations(manifest, root, required=produced)
