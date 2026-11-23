"""Check rule (B3): open page blockers in a sealed package, re-proved at `check`.

``package.assemble`` refuses a full launch that carries an open page blocker, with one exception: a
``draft_constructed`` package may carry the named "not installed by Skill 06 yet" standing blockers
(``package.OPEN_BY_DESIGN_BLOCKERS``), recorded as ``open_by_design_blockers`` in the manifest and the
receipt. This rule holds a sealed package to the same law, so a hand-edited manifest cannot slip an
unlisted blocker, a blocker on another page, or a not-installed blocker on an installed or published
package past `check`, and the recorded names must be the ones the pieces actually carry.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

CODE = "AF-LAUNCH-PKG-BLOCKERS"
RECORD = "open_by_design_blockers"


def violations(manifest: Dict[str, Any], root: Path, skill_root: Path) -> List[str]:
    from launcher_core import package as package_module

    rows = [(p.get("slot"), p.get("role"), p.get("blockers")) for p in manifest.get("pieces") or []
            if isinstance(p, dict) and isinstance(p.get("blockers"), list) and p["blockers"]]
    achieved = (manifest.get("activation") or {}).get("achieved_state")
    draft = achieved == package_module.OPEN_BY_DESIGN_STAGE
    by_design, other = package_module.open_blocker_split(rows)
    fails: List[str] = []
    full = manifest.get("delivery_scope") == package_module.DELIVERY_SCOPE_FULL
    if full:
        refused = other if draft else [(slot, b) for slot, _, bs in rows for b in bs]
        fails += [f"{CODE}: {slot}: a full launch carries open page blocker "
                  f"{json.dumps(b, sort_keys=True, default=str)}"
                  + ("" if draft else f" on a {achieved!r} package (only {package_module.OPEN_BY_DESIGN_STAGE!r} "
                                      "may carry the named not-installed blockers)")
                  for slot, b in refused]
    # A full launch must NAME what it carries open by design; any package that records names must be true.
    if RECORD in manifest or (full and draft and by_design):
        expected = by_design if draft else []
        if manifest.get(RECORD) != expected:
            fails.append(f"{CODE}: the manifest's {RECORD} {manifest.get(RECORD)!r} is not what the pieces "
                         f"carry at stage {achieved!r} ({expected!r})")
        try:
            receipt = json.loads((Path(root) / "receipt.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            receipt = None  # a missing or unreadable receipt is named by AF-LAUNCH-PKG-RECEIPT
        if isinstance(receipt, dict) and receipt.get(RECORD) != manifest.get(RECORD):
            fails.append(f"{CODE}: the receipt's {RECORD} is not the manifest's")
    return fails
