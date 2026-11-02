"""The post-dispatch image stage driver: what takes a launch from layout proofs to finished pages.

Dispatch draws only the layout-proof stages (wireframes and a mockup with solid image blocks). The
rest of Skill 71's image chain never ran and nothing drove it, so a package read as complete with no
photography. This module is the driver. For every page run folder under a launch run it walks, in
order, the five stages the layout proof leaves open:

    image-inventory-prompts, image-generation-qc, image-map-upload, design-board, final-mockups

Each stage is started through Skill 71's own gate (``stage_gate.py check``), produced by Skill 71's
own commands (``stage_executor.py``), and closed only by ``stage_gate.py close``. The driver never
closes a stage itself, never writes a review, never records an approval and never fabricates a file:
where a stage needs an authored artifact, an independent review or the client, it STOPS and names
what is missing. Two stops are by design:

* the layout proofs are the first approval checkpoint: nothing is drawn or paid for until
  ``layout-proof-approval.json`` records the client's approval of them;
* the Design Board stops for the client's recorded approval (``design_board.py approve``);
  final-mockups never starts without it.

``python3 -m launcher_core.image_stages --run-dir <launch run folder>`` exits 0 only when every page
has all five stages closed, and always writes ``qc/image_stages_report.json``. The package check
(check_rules/image_qc.py) re-reads each page's own stage state, so the report is never trusted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .constants import REPO_ROOT, resolve_ref

STAGES = ("image-inventory-prompts", "image-generation-qc", "image-map-upload",
          "design-board", "final-mockups")
REPORT_REL = "qc/image_stages_report.json"
LAYOUT_APPROVAL_REL = "layout-proof-approval.json"
SCHEMA = "launcher.image-stages/1"
SKILL71_SCRIPTS = "71-blackceo-signature-page/scripts"
FINAL_REQUEST = "production-request-final-mockups.json"
_SKIP_DIRS = {"private", ".git", "node_modules", "__pycache__"}
_MAX_DEPTH = 5

Runner = Callable[[List[str]], Tuple[int, str]]


class Stop(Exception):
    """A page cannot go further without something this driver may not invent."""

    def __init__(self, status: str, reason: str) -> None:
        super().__init__(reason)
        self.status, self.reason = status, reason


def _read(path: Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def scripts_dir(root: Optional[Path] = None) -> Path:
    return resolve_ref(SKILL71_SCRIPTS, root or REPO_ROOT)


def stage_closed(run: Path, stage: str) -> bool:
    """True only when the run's own gate state says closed with a pass receipt and every artifact
    hash recorded at close still matches the file on disk."""
    run = Path(run)
    state, receipt = _read(run / "private" / "state.json"), _read(run / "private" / "receipts" / f"{stage}.json")
    entry = ((state or {}).get("stages") or {}).get(stage) if isinstance(state, dict) else None
    if not isinstance(entry, dict) or entry.get("status") != "closed":
        return False
    if not isinstance(receipt, dict) or receipt.get("status") != "pass":
        return False
    hashes = entry.get("artifact_hashes")
    if not isinstance(hashes, dict) or not hashes:
        return False
    for rel, recorded in hashes.items():
        path = run / str(rel)
        if not path.is_file() or _sha(path) != recorded:
            return False
    return True


def page_role(run: Path) -> str:
    """The page role the run's intake declares (page_role, else launch.page_role, else its folder)."""
    intake = _read(Path(run) / "intake.json")
    intake = intake if isinstance(intake, dict) else {}
    launch = intake.get("launch") if isinstance(intake.get("launch"), dict) else {}
    role = intake.get("page_role") or launch.get("page_role")
    if not role and intake.get("page_kind"):
        role = "landing"
    return str(role or Path(run).name)


def discover_page_runs(run_dir: Path) -> List[Path]:
    """Every Skill 71 page run folder under a launch run: a folder with intake.json beside the
    gate's private/ folder, a layout-proof folder or a production request. Never descends into one."""
    found: List[Path] = []

    def walk(folder: Path, depth: int) -> None:
        if (folder / "intake.json").is_file() and any(
                (folder / mark).exists() for mark in ("private", "desktop-wireframe", "production-request.json")):
            found.append(folder)
            return
        if depth >= _MAX_DEPTH:
            return
        for child in sorted(folder.iterdir()):
            if child.is_dir() and child.name not in _SKIP_DIRS:
                walk(child, depth + 1)

    walk(Path(run_dir), 0)
    return found


def inventory_ids(run: Path) -> List[str]:
    doc = _read(Path(run) / "desktop-wireframe" / "image-inventory.json")
    items = doc if isinstance(doc, list) else (
        (doc or {}).get("images") or (doc or {}).get("items") or (doc or {}).get("inventory") or []
        if isinstance(doc, dict) else [])
    return [str(i["id"]) for i in items if isinstance(i, dict) and i.get("id")]


def _number(name: str) -> Optional[int]:
    digits = "".join(c for c in name if c.isdigit())
    return int(digits) if digits else None


def default_runner(argv: List[str]) -> Tuple[int, str]:
    """Run one command; keep only the tail of its output (a run folder can hold client names)."""
    done = subprocess.run([str(a) for a in argv], capture_output=True, text=True, timeout=3600)
    text = (done.stdout or "") + (done.stderr or "")
    return done.returncode, "\n".join(text.strip().splitlines()[-12:])


class _Page:
    """One page run and the commands that move it."""

    def __init__(self, run: Path, scripts: Path, runner: Runner, provider: str, allow_paid: bool) -> None:
        self.run, self.scripts, self.runner = Path(run), Path(scripts), runner
        self.provider, self.allow_paid = provider, allow_paid
        self.log: List[str] = []

    def call(self, script: str, *args: Any) -> Tuple[int, str]:
        rc, out = self.runner([sys.executable, str(self.scripts / script), *map(str, args)])
        words = [str(a) for a in args if isinstance(a, str) and os.sep not in a]  # never a path in the log
        self.log.append(f"{script} {' '.join(words)} -> {rc}")
        return rc, out

    def executor(self, *args: Any) -> Tuple[int, str]:
        extra = ["--provider", self.provider] + (["--allow-paid"] if self.allow_paid else [])
        return self.call("stage_executor.py", self.run, *args, *extra)

    def need(self, rc: int, out: str, stage: str, what: str) -> None:
        if rc:
            raise Stop("blocked", f"{stage}: {what} failed: {out.splitlines()[-1] if out else 'no output'}")

    # -- one producer per stage; each returns when the stage is ready to be closed, or raises Stop

    def produce_prompts(self) -> None:
        ids = inventory_ids(self.run)
        missing = [i for i in ids if not (self.run / "image-inventory-prompts" / f"{i}.txt").is_file()]
        if not ids or missing:
            what = ", ".join(missing) if ids else "one per image slot (desktop-wireframe/image-inventory.json lists none)"
            raise Stop("needs_authoring", f"image-inventory-prompts: the prompts are authored, never generated here; "
                       f"write {what} (BlackCEO Signature Image Intelligence and Prompt Creation Guide v5), "
                       "then run this again")

    def produce_images(self) -> None:
        out_dir = self.run / "image-generation-qc"
        have = {_number(p.stem) for p in out_dir.glob("Image-*.png")} if out_dir.is_dir() else set()
        for item in inventory_ids(self.run):
            if _number(item) not in have:
                rc, out = self.executor("--stage", "image-generation-qc", "--item", item)
                self.need(rc, out, "image-generation-qc", f"drawing {item}")

    def produce_map(self) -> None:
        if not (self.run / "image-map-upload" / "image-map.json").is_file():
            raise Stop("needs_authoring",
                       "image-map-upload: image-map-upload/image-map.json (and image-map.md) is written from "
                       "the generated files and their hosted links; it does not exist yet")

    def produce_board(self) -> None:
        if not (self.run / "design-board" / "design-board.png").is_file():
            rc, out = self.executor("--stages", "design-board")
            self.need(rc, out, "design-board", "making the Design Board")
        rc, _ = self.call("design_board.py", "gate", self.run)
        if rc:  # no recorded, current client approval: stop here, final-mockups never starts
            raise Stop("awaiting_client_approval",
                       "design-board: the client has not approved this page's Design Board; show them "
                       "design-board/design-board.png, and record the approval with design_board.py approve. "
                       "final-mockups does not start without it")

    def produce_mockups(self) -> None:
        request = self.run / FINAL_REQUEST
        if not request.is_file():
            intake = _read(self.run / "intake.json") or {}
            manuscript = self.run / "copy" / "internal-manuscript.md"
            version = intake.get("copy_version")
            if version not in ("standard", "long-form") or not manuscript.is_file():
                raise Stop("needs_authoring", f"final-mockups: {FINAL_REQUEST} does not exist; build it with "
                           "build_production_request.py --stage final-mockups (the NEXT 2 line the layout-proof "
                           "run printed)")
            rc, out = self.call("build_production_request.py", "--copy-version", version, "--manuscript", manuscript,
                                "--stage", "final-mockups", "--out", request, "--run-dir", self.run)
            self.need(rc, out, "final-mockups", "building its request")
        if not (self.run / "final-mockups" / "stage-executor-record.json").is_file():
            rc, out = self.executor("--stages", "final-mockups", "--request", FINAL_REQUEST)
            self.need(rc, out, "final-mockups", "drawing the mockup")

    def advance(self) -> Dict[str, str]:
        """Close every stage the page can; returns {stage: closed|open}. Records why it stopped."""
        producers = {"image-inventory-prompts": self.produce_prompts, "image-generation-qc": self.produce_images,
                     "image-map-upload": self.produce_map, "design-board": self.produce_board,
                     "final-mockups": self.produce_mockups}
        self.stop: Optional[Stop] = None
        for stage in STAGES:
            if stage_closed(self.run, stage):
                continue
            try:
                rc, out = self.call("stage_gate.py", "check", self.run, stage)
                self.need(rc, out, stage, "the gate's start check")
                producers[stage]()
                rc, out = self.call("stage_gate.py", "close", self.run, stage)
                self.need(rc, out, stage, "the gate's close")
            except Stop as stop:
                self.stop = stop
                break
        return {s: "closed" if stage_closed(self.run, s) else "open" for s in STAGES}


def layout_approval(run_dir: Path, path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """The client's recorded approval of the layout proofs, or None. A record names an approval_ref;
    this is recorded consent, not an authenticated signature (the approval units own that)."""
    doc = _read(path or Path(run_dir) / LAYOUT_APPROVAL_REL)
    if isinstance(doc, dict) and str(doc.get("approval_ref") or "").strip() and doc.get("revoked") is not True:
        return doc
    return None


def _write_qc_request(run_dir: Path) -> Optional[str]:
    """SOP-GIP-02 request for every image the launch's pieces list (graphics_hooks.qc_request)."""
    pieces = [_read(p) for p in sorted((Path(run_dir) / "pieces").glob("*.json"))]
    pieces = [p for p in pieces if isinstance(p, dict)]
    if not pieces:
        return None
    from . import graphics_hooks
    graphics_hooks.qc_request({"pieces": pieces}, Path(run_dir), Path(run_dir))
    return graphics_hooks.QC_REQUEST_REL


def drive(run_dir: Path, *, runner: Runner = default_runner, provider: str = "stub",
          allow_paid: bool = False, layout_approval_file: Optional[Path] = None,
          repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """Drive every page run under ``run_dir``. Writes and returns the report."""
    run_dir = Path(run_dir)
    scripts = scripts_dir(repo_root)
    runs = discover_page_runs(run_dir)
    approval = layout_approval(run_dir, layout_approval_file)
    pages: List[Dict[str, Any]] = []
    for run in runs:
        entry: Dict[str, Any] = {"page": run.name, "role": page_role(run), "run_dir": str(run.resolve())}
        if approval is None:
            entry.update(status="awaiting_layout_proof_approval", stages={s: "open" if not stage_closed(run, s) else "closed" for s in STAGES},
                         reason="the layout proofs are the first approval checkpoint; nothing is drawn until the "
                                f"client's approval is recorded in {LAYOUT_APPROVAL_REL}")
        else:
            page = _Page(run, scripts, runner, provider, allow_paid)
            stages = page.advance()
            done = all(v == "closed" for v in stages.values())
            entry.update(status="complete" if done else (page.stop.status if page.stop else "blocked"),
                         stages=stages, reason=None if done else (page.stop.reason if page.stop else "a stage is still open"),
                         commands=page.log)
        pages.append(entry)
    complete = bool(pages) and all(p["status"] == "complete" for p in pages)
    report = {"schema": SCHEMA, "run_dir": str(run_dir.resolve()), "stages": list(STAGES),
              "first_checkpoint": "layout proofs", "layout_proof_approval": (approval or {}).get("approval_ref"),
              "provider": provider, "pages": pages, "complete": complete,
              "qc_request": _write_qc_request(run_dir) if runs else None}
    if not runs:
        report["reason"] = "no Skill 71 page run folder (intake.json beside private/) was found under this run"
    path = run_dir / REPORT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def summary_lines(report: Dict[str, Any]) -> List[str]:
    lines = []
    for p in report["pages"]:
        closed = sum(1 for v in p["stages"].values() if v == "closed")
        lines.append(f"{p['page']} ({p['role']}): {p['status']}, {closed} of {len(STAGES)} image stages closed"
                     + (f". {p['reason']}" if p.get("reason") else ""))
    lines.append("Every page has finished images." if report["complete"] else
                 "Not finished: the package check refuses this launch until every page closes all five image stages.")
    return lines


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="launcher_core.image_stages", description=__doc__.split("\n\n")[0])
    ap.add_argument("--run-dir", required=True, type=Path, help="the launch run folder (the dispatch --out)")
    ap.add_argument("--provider", choices=["stub", "kie"], default="stub")
    ap.add_argument("--allow-paid", action="store_true", help="required with --provider kie")
    ap.add_argument("--layout-approval", type=Path, default=None,
                    help=f"the client's layout-proof approval record (default <run-dir>/{LAYOUT_APPROVAL_REL})")
    args = ap.parse_args(argv)
    if args.provider == "kie" and not args.allow_paid:
        print("FAIL: --provider kie spends money and needs --allow-paid", file=sys.stderr)
        return 2
    report = drive(args.run_dir, provider=args.provider, allow_paid=args.allow_paid,
                   layout_approval_file=args.layout_approval)
    for line in summary_lines(report):
        print(line)
    print(f"report: {args.run_dir / REPORT_REL}")
    return 0 if report["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
