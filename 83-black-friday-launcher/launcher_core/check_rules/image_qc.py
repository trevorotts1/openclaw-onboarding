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

F17 item 7, TWO SEPARATE PAGES ARE TWO INSTANCES. A page is bound by its OWN identity (role + page
kind + role instance, ``page_designs.page_key``), never by its role:

* a planned page with no run is NAMED as missing, with its page identity and its role — a count of
  folders is never proof that every planned page was designed;
* one role-level report row cannot stand for two planned page instances of that role (the signature
  sales page and the signature opt-in page share the role ``landing`` and are two pages);
* one page run's stage receipt is one page instance's receipt: two page identities citing the same
  run folder, and a row whose own intake says a different page, are both refused.

ponytail: the closure read trusts the run's state.json plus its recorded artifact hashes; a forged
state file with forged hashes passes. U-images-04 binds the design gate to the gate's own files.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_SKILL_ROOT = Path(__file__).resolve().parents[2]
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

from launcher_core import graphics_hooks, image_stages, page_designs  # noqa: E402

CODE = "AF-LAUNCH-IMAGE-STAGES"
CODE_BINDING = "AF-LAUNCH-HOSTING-BINDING"
# What a launch leaves in the package root: the stage report, the layout-proof approval, the dispatch report.
LAUNCH_MARKS = (image_stages.REPORT_REL, image_stages.LAYOUT_APPROVAL_REL, "dispatch-report.json")


def _name(entry: Dict[str, Any]) -> str:
    """A report row's display name: its own page label, else its run folder."""
    return str(entry.get("page") or Path(str(entry.get("run_dir") or "")).name or "?")


def _runs_for(piece: Dict[str, Any], rows: List[Dict[str, Any]],
              per_role: Dict[str, int]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """The report row(s) this package piece is proved by, or the reason it is not proved at all.

    The piece's own page identity wins. A row that carries no identity is a role-level row, and a
    role-level row proves only a role the launch planned once: it can never stand in for two page
    instances of one role, which is how one landing run used to answer for both landing pages.
    """
    key = page_designs.page_key(piece)
    role = str(piece.get("role") or "")
    mine = [row for row in rows if str(row.get("page_key") or "") == key]
    if mine:
        return mine, None
    if per_role.get(role, 0) > 1:
        return [], (f"page {key} (role {role}) is covered only by a role-level row in "
                    f"{image_stages.REPORT_REL}; one role-level row cannot stand for two planned page "
                    f"instances of {role}")
    mine = [row for row in rows if not row.get("page_key") and str(row.get("role") or "") == role]
    if mine:
        return mine, None
    return [], f"page {key} (role {role or '?'}) has no page run in {image_stages.REPORT_REL}"


def _page_rows(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [row for row in report.get("pages") or [] if isinstance(row, dict)]


def _set_violations(report: Dict[str, Any], rows: List[Dict[str, Any]]) -> List[str]:
    """The planned page set: named missing pages, one run per identity, and a run that stays its own."""
    fails: List[str] = []
    state = report.get("expected_pages_state")
    if state is not None and state != "known":
        fails.append(f"{CODE}: {image_stages.REPORT_REL} says the planned page set is {state!r} "
                     f"({report.get('reason') or 'no reason recorded'}); a directory listing of run folders "
                     "cannot prove every planned page was designed, so completeness is unverified")
    for row in rows:
        if row.get("status") == "missing_page":
            key = row.get("page_key") or row.get("role")
            fails.append(f"{CODE}: page {key} (role {row.get('role') or '?'}) is missing: "
                         f"{row.get('reason') or 'the launch plans this page and no run folder was found'}")
    claims: Dict[str, List[str]] = {}
    for row in rows:
        declared = str(row.get("run_dir") or "").strip()
        if not declared:  # a row that names no run proves nothing about which page it is
            continue
        claims.setdefault(str(Path(declared).resolve()), []).append(
            str(row.get("page_key") or row.get("role") or _name(row)))
    for run_dir, identities in sorted(claims.items()):
        holders = sorted(set(identities))
        if len(holders) > 1:
            fails.append(f"{CODE}: pages {holders[0]} and {holders[1]} cite the same page run "
                         f"({Path(run_dir).name!r}); one run's stage receipt is one page instance's "
                         "receipt and is never transferable to another page")
    for row in rows:
        key, declared = row.get("page_key"), str(row.get("run_dir") or "").strip()
        if not key or not declared:
            continue
        run = Path(declared)
        if not run.is_dir():
            continue
        actual = image_stages.page_key_for_run(run)
        if actual != str(key):
            fails.append(f"{CODE}: page {key} (role {row.get('role') or '?'}) is bound to run "
                         f"{run.name!r}, whose own intake declares {actual}; a run's receipt belongs to "
                         "the page it was drawn for")
    return fails


def _stage_violations(manifest: Dict[str, Any], root: Path) -> List[str]:
    path = Path(root) / image_stages.REPORT_REL
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        rows = _page_rows(report)
        if not rows:
            raise ValueError("no pages")
    except (OSError, ValueError, AttributeError, TypeError):
        return [f"{CODE}: {image_stages.REPORT_REL} is missing or lists no page; the post-dispatch image "
                "stages never ran, so this package holds layout proofs only "
                "(python3 -m launcher_core.image_stages --run-dir <launch run folder>)"]
    fails: List[str] = _set_violations(report, rows)
    pieces = [piece for piece in manifest.get("pieces") or [] if isinstance(piece, dict)]
    per_role: Dict[str, int] = {}
    for piece in pieces:
        role = str(piece.get("role") or "")
        per_role[role] = per_role.get(role, 0) + 1
    seen: List[Path] = []
    for piece in pieces:
        mine, why = _runs_for(piece, rows, per_role)
        if why:
            fails.append(f"{CODE}: {why}")
            continue
        for row in mine:
            run = Path(str(row.get("run_dir") or ""))
            if not run.is_dir():
                fails.append(f"{CODE}: page {_name(row)} (role {row.get('role') or '?'}) run folder "
                             f"{str(run)!r} does not exist")
                continue
            if run.resolve() not in seen:
                seen.append(run.resolve())
                for stage in image_stages.STAGES:
                    if not image_stages.stage_closed(run, stage):
                        fails.append(f"{CODE}: page {_name(row)} stage {stage} is not closed by "
                                     "stage_gate.py")
    return fails


def _hosting_binding_violations(manifest: Dict[str, Any], root: Path) -> List[str]:
    """A client delivery ships hosted images: every page's own binding must admit them.

    ``image_stages.hosted_admission`` is the launcher's decision; it is re-run from each
    page's run folder (against the binding the launcher wrote), so a report row alone cannot
    pass. The local SHA-256 is the identity: a changed artifact or a row with no folder/media
    id/recognised status/usable URL is named. A test package keeps the existing "images only,
    render pending" state and is not required to host.
    """
    if manifest.get("test_only") is True:
        return []
    runs = image_stages.discover_page_runs(root)
    pieces = [piece for piece in manifest.get("pieces") or [] if isinstance(piece, dict)]
    per_role: Dict[str, int] = {}
    for piece in pieces:
        role = str(piece.get("role") or "")
        per_role[role] = per_role.get(role, 0) + 1
    fails: List[str] = []
    for piece in pieces:
        key, role = page_designs.page_key(piece), str(piece.get("role") or "")
        mine = [run for run in runs if image_stages.page_key_for_run(run) == key]
        if not mine and per_role.get(role, 0) == 1:  # a role-level run, one instance of that role
            mine = [run for run in runs if image_stages.page_role(run) == role]
        if not mine and per_role.get(role, 0) > 1:
            fails.append(f"{CODE_BINDING}: page {key} (role {role}) has no page run of its own, so its "
                         "hosted binding cannot be admitted; another page of this role is not it")
            continue
        for run in mine:
            decision = image_stages.hosted_admission(root, run)
            if decision.get("state") == "pass":
                continue
            refused = decision.get("refused") or []
            detail = (refused[0].get("problems") if isinstance(refused[0], dict) else str(refused[0])) \
                if refused else decision.get("reason") or decision.get("state")
            fails.append(f"{CODE_BINDING}: page {key} has no admitted hosting binding "
                         f"({decision.get('state')}): {detail}")
    return fails


def applies(manifest: Dict[str, Any], root: Path) -> bool:
    """A paid run (test_only not true) always: it delivers finished pages (DECISIONS 2026-11-02 09:25).
    A test package once a launch dispatch or the stage driver left its mark in the package root; a
    bare stub package stays 'images only, render pending' (checks.py, U-launcher-core-02)."""
    if manifest.get("test_only") is not True:
        return True
    return any((root / rel).exists() for rel in LAUNCH_MARKS) or bool(image_stages.discover_page_runs(root))


def violations(manifest: Dict[str, Any], root: Path, skill_root: Path) -> List[str]:
    root = Path(root)
    if not applies(manifest, root):
        return []
    return (graphics_hooks.report_violations(manifest, root)
            + _stage_violations(manifest, root)
            + _hosting_binding_violations(manifest, root))
