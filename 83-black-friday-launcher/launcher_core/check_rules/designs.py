"""IMG-02: every design file in a package is a real PNG or PDF, whatever designs_required says.

check_package runs this rule through the check_rules seam. It does not repeat the stub, waiver or
completeness logic (checks.py and page_designs own those); it closes the hole where a manifest that
sets designs_required false, or a caller that never asks for designs, ships one-byte placeholder files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from launcher_core import page_designs


def violations(manifest: Dict[str, Any], root: Path, skill_root: Path) -> List[str]:
    strict = manifest.get("test_only") is not True
    fails: List[str] = []
    for piece in manifest.get("pieces") or []:
        for art in piece.get("artifacts") or []:
            path = str(art.get("path") or "")
            kind = page_designs.classify(path)
            target = Path(root) / path
            if kind is None or not target.is_file():
                continue
            why = page_designs.real_file_problem(target, kind, strict=strict)
            if why:
                fails.append(f"{page_designs.CODE}: {page_designs.page_key(piece)} {kind} "
                             f"{Path(path).name!r} {why}")
    return fails
