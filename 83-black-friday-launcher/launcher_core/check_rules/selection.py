"""AF-LAUNCH-SELECTION: the product selection page must have something to compare.

A check_rules module (see check_rules/__init__.py). The selection page's manuscript
(copy/internal-manuscript.md, listed among the page's artifacts by emit_page_result.py
--image-run-dir) must have at least one row in its Compare section (Section 4): a page of bare
prices is not a selection page. A package whose selection piece lists no manuscript cannot be
judged here, so a test_only (practice) package is not failed by this rule (the other design-set checks
still apply to it). On any other package a selection piece that lists no manuscript, or lists one that is
not on disk, is a finding: emit_page_result.py lists the manuscript for every real run, so its absence
means the Compare check never ran and the pass would be a pass by absence.

The manuscript is read with Skill 78's own parser (validate_selection_content.compare_rows).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Dict, List

CODE = "AF-LAUNCH-SELECTION"
ROLE = "product_selection"
MANUSCRIPT = "internal-manuscript.md"


def _compare_rows(skill_root: Path):
    from launcher_core.constants import skill_path
    path = skill_path("signature-product-selection", "scripts", "validate_selection_content.py",
                      root=Path(skill_root).parent)
    spec = importlib.util.spec_from_file_location("s78_validate_selection_content_for_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.compare_rows


def violations(manifest: Dict[str, Any], root: Path, skill_root: Path) -> List[str]:
    fails: List[str] = []
    practice = manifest.get("test_only") is True
    for piece in manifest.get("pieces") or []:
        if piece.get("role") != ROLE:
            continue
        listed = False
        for art in piece.get("artifacts") or []:
            path = str(art.get("path") or "")
            if Path(path).name != MANUSCRIPT:
                continue
            listed = True
            target = (Path(root) / path).resolve()
            if not target.is_file():
                if not practice:
                    fails.append(f"{CODE}: the selection page's manuscript ({path}) is not in the package; "
                                 "its Compare section cannot be checked")
                continue
            if not _compare_rows(skill_root)(target.read_text(encoding="utf-8", errors="replace")):
                fails.append(f"{CODE}: the selection page's Compare section ({path}) has no rows; buyers "
                             "would choose between prices alone")
        if not listed and not practice:
            fails.append(f"{CODE}: the selection piece lists no {MANUSCRIPT}; its Compare section cannot be "
                         "checked, and a package that is not test_only does not pass by absence")
    return fails
