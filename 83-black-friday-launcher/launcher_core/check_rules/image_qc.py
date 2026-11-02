"""check rule: the images a launch ships were reviewed, and every page closed its image stages.

check_package runs ``violations(manifest, root, skill_root)`` from every module in this folder
(see check_rules/__init__.py). This rule holds two things a package cannot pass without:

* IMG-12 (SOP-GIP-02): ``qc/image_qc_report.json`` exists, covers every image in the package and
  gives each a real average of at least 8.5 and no automatic failure (graphics_hooks.report_violations).
* IMG-01: each page's Skill 71 run has closed image-inventory-prompts, image-generation-qc,
  image-map-upload, design-board and final-mockups. The page runs are listed in
  ``qc/image_stages_report.json`` (written by ``python3 -m launcher_core.image_stages``), but that
  report is only a list of where to look: every stage is re-read from the run's own gate state, with
  the artifact hashes it recorded at close, so a hand-edited report proves nothing.

ponytail: the closure read trusts the run's state.json plus its recorded artifact hashes; a forged
state file with forged hashes passes. U-images-04 binds the design gate to the gate's own files.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

_SKILL_ROOT = Path(__file__).resolve().parents[2]
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

from launcher_core import graphics_hooks, image_stages  # noqa: E402

CODE = "AF-LAUNCH-IMAGE-STAGES"


def _stage_violations(manifest: Dict[str, Any], root: Path) -> List[str]:
    path = Path(root) / image_stages.REPORT_REL
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        pages = report["pages"]
        if not isinstance(pages, list) or not pages:
            raise ValueError("no pages")
    except (OSError, ValueError, KeyError, TypeError):
        return [f"{CODE}: {image_stages.REPORT_REL} is missing or lists no page; the post-dispatch image "
                "stages never ran, so this package holds layout proofs only "
                "(python3 -m launcher_core.image_stages --run-dir <launch run folder>)"]
    fails: List[str] = []
    roles = {str(p.get("role")) for p in pages if isinstance(p, dict)}
    for piece in manifest.get("pieces") or []:
        if str(piece.get("role")) not in roles:
            fails.append(f"{CODE}: {piece.get('role')} has no page run in {image_stages.REPORT_REL}")
    if len(pages) < len(manifest.get("pieces") or []):
        fails.append(f"{CODE}: {image_stages.REPORT_REL} lists {len(pages)} page run(s) for "
                     f"{len(manifest.get('pieces') or [])} package pieces")
    for page in pages:
        run = Path(str((page or {}).get("run_dir") or ""))
        name = (page or {}).get("page") or run.name
        if not run.is_dir():
            fails.append(f"{CODE}: page {name} run folder {str(run)!r} does not exist")
            continue
        for stage in image_stages.STAGES:
            if not image_stages.stage_closed(run, stage):
                fails.append(f"{CODE}: page {name} stage {stage} is not closed by stage_gate.py")
    return fails


def violations(manifest: Dict[str, Any], root: Path, skill_root: Path) -> List[str]:
    root = Path(root)
    return graphics_hooks.report_violations(manifest, root) + _stage_violations(manifest, root)
