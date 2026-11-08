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

When a page's final-mockups stage closes, its labeled final mockups, review PDF and boards exist for the
first time. Dispatch listed the page's files before that, so ``refresh_pieces`` lists them again in the
page's piece and in the dispatch's stored result the package binds the piece to; without it the package
check would never see the final mockups of a real run.

``python3 -m launcher_core.image_stages --run-dir <launch run folder>`` exits 0 only when every page
has all five stages closed, and always writes ``qc/image_stages_report.json``. The package check
(check_rules/image_qc.py) re-reads each page's own stage state, so the report is never trusted.

WHAT IS OWNED, NOT LEFT AS A DEAD END (F17). The prompt files and the image map are authored work,
and this driver owns the deterministic half of it:

* the prompt manifest (``prompt-manifest.json``, the stage contract's second artifact) is written
  here from the prompt files on disk, exactly as the swarm runner maintains it, so a page whose
  prompts exist is closable;
* a registered author command (``image_authoring.prompts`` in the run's ``launch.json`` or
  ``intake.json``, or ``SKILL83_PROMPT_AUTHOR``) is invoked when prompts are missing, then the
  driver re-reads them; an author that produces nothing leaves a named task in the report
  (``owned_tasks``) with its owner, its stage and its acceptance gate — never a bare string;
* the image map (``image-map.json``/``image-map.md``) is written from the inventory, the generated
  files and the hosting ledger, and is only accepted when the stage contract's own validator
  passes it;
* the hosting ledger is admitted per asset: the current file's hash, the page/slot, the folder,
  the media id, a recognised completion status and a usable URL — a non-empty HTML response is
  never proof of a correct picture, and CDN transformation is expected (the LOCAL hash is the
  identity; the remote bytes are never compared to it).

The page SET comes from Skill 49's inventory (``page_types.json``) read against the run's launch
record, never from a directory count: a planned page with no run folder is named missing.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .constants import REPO_ROOT, resolve_ref

STAGES = ("image-inventory-prompts", "image-generation-qc", "image-map-upload",
          "design-board", "final-mockups")
# The two stages whose work is one file per image slot; their quantity comes from the page profile.
ITEMIZED = ("image-inventory-prompts", "image-generation-qc")
# The chain that must be closed BEFORE the image chain, and the stage that follows the mockups.
LAYOUT_STAGES = ("desktop-wireframe", "mobile-tablet", "visual-mockup")
IMPLEMENTATION_STAGE = "responsive-html"
REPORT_REL = "qc/image_stages_report.json"
LAYOUT_APPROVAL_REL = "layout-proof-approval.json"
SCHEMA = "launcher.image-stages/1"
SKILL71_SCRIPTS = "71-blackceo-signature-page/scripts"
FINAL_REQUEST = "production-request-final-mockups.json"
PROMPT_AUTHOR_ENV = "SKILL83_PROMPT_AUTHOR"     # a registered prompt-author command, optional
MAP_VALIDATOR = "validate_image_manifest.py"     # the stage contract's own map validator
HOSTING_ROUTE = "45-design-intelligence-library/scripts/graphics_ghl_push.py"
MEDIA_LIBRARY = "media_library.json"             # the ledger that hosting route writes
DESIGN_ONLY_ROLES = ("checkout", "downsell_2")   # mockups are the deliverable; no live page is built
_SKIP_DIRS = {"private", ".git", "node_modules", "__pycache__"}
_MAX_DEPTH = 5

Runner = Callable[[List[str]], Tuple[int, str]]
_ROUTES_DIR = Path(__file__).resolve().parent.parent / "routes"


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


def _skill71_module(filename: str):
    """One Skill 71 script by path (the module that already owns the rule being reused)."""
    path = scripts_dir() / filename
    if not path.is_file():
        raise Stop("blocked", f"{SKILL71_SCRIPTS}/{filename} is not installed; the driver reuses that "
                              "module's own rule instead of re-typing it")
    spec = importlib.util.spec_from_file_location(f"launcher_skill71_{Path(filename).stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def inventory_doc(run: Path):
    return _read(Path(run) / "desktop-wireframe" / "image-inventory.json")


def _slot_is_supplied(module: Any, item: Dict[str, Any]) -> bool:
    """Skill 71's OWN test for a slot the client supplies (so nothing is generated for it).

    `requires_generation: false`, a supplied-* or stock source (the validator's
    `is_supplied_or_stock`), or a source/asset_kind in its NON_GENERATED_SOURCES set — the same
    three tests `inventory_generation_count` applies. Loaded from that module, never retyped, so
    the driver and the map validator can never disagree about how many images a page buys.
    """
    if item.get("requires_generation") is False:
        return True
    is_supplied = getattr(module, "is_supplied_or_stock", None)
    if callable(is_supplied) and is_supplied(item):
        return True
    source = str(item.get("source") or item.get("asset_kind") or "").strip().lower()
    return source in (getattr(module, "NON_GENERATED_SOURCES", None) or frozenset())


def generation_items(run: Path) -> List[str]:
    """The inventory slots this page must GENERATE, from the inventory's own declarations.

    A slot the client already supplies is not generated (``_slot_is_supplied``). Retyping that
    rule here would let the driver demand a picture for a slot the map already accepts as supplied.
    """
    doc = inventory_doc(run)
    if doc is None:
        return []
    module = _skill71_module(MAP_VALIDATOR)
    try:
        items = module.inventory_items(doc)
    except (ValueError, AttributeError) as exc:
        raise Stop("blocked", f"desktop-wireframe/image-inventory.json: {exc}")
    return [str(item["id"]) for item in items
            if isinstance(item, dict) and item.get("id") and not _slot_is_supplied(module, item)]


def supplied_items(run: Path) -> List[Dict[str, str]]:
    """The slots the client already supplied: named in the report, never generated, never waived."""
    doc = inventory_doc(run)
    if doc is None:
        return []
    module = _skill71_module(MAP_VALIDATOR)
    try:
        items = module.inventory_items(doc)
    except (ValueError, AttributeError):
        return []
    out = []
    for item in items:
        if not isinstance(item, dict) or not item.get("id") or not _slot_is_supplied(module, item):
            continue
        source = str(item.get("source") or item.get("asset_kind") or "").strip().lower()
        out.append({"id": str(item["id"]), "source": source or "supplied",
                    "file": str(item.get("file") or item.get("asset_file") or "")})
    return out


_PAGE_SET_MODULE: Any = None


def _page_set():
    """Skill 49's page_set (the one list of a page's design files), loaded through the substrate.

    Loaded once per process: every ``substrate.load`` runs Skill 49's front-door gates, whose
    hash-pin walks the whole launcher tree, and this driver asks for the page inventory once per
    page. Caching the module changes no gate — the load itself still ran the gates.
    """
    global _PAGE_SET_MODULE
    if _PAGE_SET_MODULE is not None:
        return _PAGE_SET_MODULE
    if str(_ROUTES_DIR) not in sys.path:
        sys.path.insert(0, str(_ROUTES_DIR))
    import substrate
    _PAGE_SET_MODULE = substrate.load("49-signature-funnel/scripts/page_set.py", "launcher_page_set",
                                      "49-signature-funnel/scripts")
    return _PAGE_SET_MODULE


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

    def __init__(self, run: Path, scripts: Path, runner: Runner, provider: str, allow_paid: bool,
                 run_dir: Optional[Path] = None) -> None:
        self.run, self.scripts, self.runner = Path(run), Path(scripts), runner
        self.provider, self.allow_paid = provider, allow_paid
        self.run_dir = Path(run_dir) if run_dir else Path(run).parent
        self.log: List[str] = []
        self.tasks: List[Dict[str, Any]] = []   # authored work this page still needs, with its owner
        self.notes: Dict[str, Any] = {}

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

    def task(self, stage: str, owner: str, missing: List[str], how: str, gate: str) -> None:
        """Record authored work as an OWNED task: who owes it, what is missing and what closes it."""
        self.tasks.append({"stage": stage, "owner": owner, "missing": missing, "how": how, "gate": gate,
                           "page": page_key_for_run(self.run)})

    # -- one producer per stage; each returns when the stage is ready to be closed, or raises Stop

    def produce_prompts(self) -> None:
        items = generation_items(self.run)
        if not items:
            return  # every slot is supplied: nothing to author (the stage is not applicable)
        folder = self.run / "image-inventory-prompts"
        missing = [i for i in items if not (folder / f"{i}.txt").is_file()]
        if missing:
            command = author_command(self.run_dir, self.run, "prompts")
            if command:
                done = subprocess.run(command, cwd=str(self.run), capture_output=True, text=True, timeout=3600)
                self.log.append(f"prompt-author {' '.join(Path(c).name for c in command)} -> {done.returncode}")
                missing = [i for i in items if not (folder / f"{i}.txt").is_file()]
            if missing:
                self.task("image-inventory-prompts", "graphics", missing,
                          "write each prompt from the slot's inventory entry, the composition treatment and "
                          "the BlackCEO Signature Image Intelligence and Prompt Creation Guide v5",
                          "python3 scripts/validate_prompt.py <file> <sauce> --model <model> --max-chars <max>")
                raise Stop("needs_authoring",
                           f"image-inventory-prompts: {len(missing)} of {len(items)} prompt(s) are not authored: "
                           f"{', '.join(missing)}. The work is owned (see owned_tasks) and a registered author "
                           f"command ({PROMPT_AUTHOR_ENV} or image_authoring.prompts) runs here when one is set")
        write_prompt_manifest(self.run)  # the stage's second artifact, from the prompts on disk

    def produce_images(self) -> None:
        out_dir = self.run / "image-generation-qc"
        have = {_number(p.stem) for p in out_dir.glob("Image-*.png")} if out_dir.is_dir() else set()
        for item in generation_items(self.run):
            if _number(item) not in have:
                rc, out = self.executor("--stage", "image-generation-qc", "--item", item)
                self.need(rc, out, "image-generation-qc", f"drawing {item}")

    def produce_map(self) -> None:
        if not (self.run / "image-map-upload" / "image-map.json").is_file():
            hosted = hosted_admission(self.run_dir, self.run)
            self.notes["hosting"] = hosted
            if write_image_map(self.run_dir, self.run) is None:
                self.task("image-map-upload", "graphics",
                          [str(i["id"]) for i in supplied_items(self.run)] or ["inventory"],
                          "the map is authored from the page's inventory and its generated files; the inventory "
                          "is missing or unreadable",
                          "python3 scripts/validate_image_manifest.py <map> --inventory <inventory> --measure")
                raise Stop("needs_authoring",
                           "image-map-upload: desktop-wireframe/image-inventory.json is missing or unreadable, so "
                           "image-map.json cannot be authored from the page's own slots")
            # every image slot must also carry its QC verdict before the map's stage can close
            pending = [e["id"] for e in (_read(self.run / "image-map-upload" / "image-map.json") or {}).get("images", [])
                       if isinstance(e, dict) and e.get("qc_status") not in (None, "passed")]
            if pending:
                self.task("image-generation-qc", "graphics", pending,
                          "review each generated image (SOP-GIP-02) and record its verdict; the map refuses an "
                          "image used on the page without a passing QC status",
                          "qc/image_qc_report.json (pass:true, zero auto-fails) or image-generation-qc/image-qc.json")
                raise Stop("needs_authoring",
                           f"image-map-upload: {len(pending)} image(s) have no passing QC verdict yet "
                           f"({', '.join(pending)})")

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
        """Close every stage the page can; returns {stage: closed|open|not_applicable}.

        A page whose inventory declares every slot as supplied has nothing to author or draw: the
        two itemized stages are recorded not applicable (with the reason and the supplied slots),
        never forced through an empty generation and never silently skipped.
        """
        producers = {"image-inventory-prompts": self.produce_prompts, "image-generation-qc": self.produce_images,
                     "image-map-upload": self.produce_map, "design-board": self.produce_board,
                     "final-mockups": self.produce_mockups}
        self.stop: Optional[Stop] = None
        try:  # the inventory is read through Skill 71's own rule; an unreadable one stops the page, never the report
            inventory = inventory_doc(self.run)
            supplied = supplied_items(self.run)
            nothing_to_generate = inventory is not None and bool(supplied) and not generation_items(self.run)
        except Stop:
            supplied, nothing_to_generate = [], False
        for stage in STAGES:
            if stage_closed(self.run, stage):
                continue
            if nothing_to_generate and stage in ITEMIZED:
                self.notes.setdefault("not_applicable", []).append(
                    {"stage": stage, "reason": "every image slot on this page is supplied by the client, so "
                                               "nothing is generated for it",
                     "slots": [s["id"] for s in supplied]})
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
        na = {entry["stage"] for entry in self.notes.get("not_applicable") or []}
        return {s: ("closed" if stage_closed(self.run, s) else
                    "not_applicable" if s in na else "open") for s in STAGES}


def layout_chain(run: Path) -> Dict[str, Any]:
    """The stages BEFORE the image chain, read from the run's own gate state, plus what comes after.

    The defect this closes: dispatch draws the layout proof (desktop and mobile wireframes plus a
    mockup with solid image blocks) and a package read that as the finished design chain. The
    driver now names the earlier chain explicitly — the three layout stages closed by the gate and
    their review PDFs on disk — and names the implementation stage that follows the mockups
    instead of letting a page look finished at the image chain's end.
    """
    stages = {s: ("closed" if stage_closed(run, s) else "open") for s in LAYOUT_STAGES}
    review_dir = Path(run) / "review-pdfs"
    pdfs = sorted(p.name for p in review_dir.glob("*.pdf")) if review_dir.is_dir() else []
    implementation = IMPLEMENTATION_STAGE
    state = _read(Path(run) / "private" / "state.json") or {}
    recorded = ((state.get("stages") or {}).get(implementation) or {}) if isinstance(state, dict) else {}
    return {
        "stages": stages,
        "review_pdfs": pdfs,
        "layout_proof": (Path(run) / "visual-mockup").is_dir(),
        "complete": all(v == "closed" for v in stages.values()) and bool(pdfs),
        "implementation": {"stage": implementation,
                           "state": "closed" if stage_closed(run, implementation) else
                                    (str(recorded.get("status")) if recorded else "not_run"),
                           "owned_by": "the implementation unit (F01-F03); a design chain never claims it"},
    }


def page_key_for_run(run: Path) -> str:
    """The page identity a run folder IS: role + page kind + role instance, never its folder name.

    Two runs of one role are two different pages (downsell_1 and its role-instance downsell_2), and
    a landing run's page kind (opt_in or sales) is what tells the two landing pages apart. The key
    is built from the run's own intake so a renamed folder can never stand in for another page.
    """
    intake = _read(Path(run) / "intake.json")
    intake = intake if isinstance(intake, dict) else {}
    launch = intake.get("launch") if isinstance(intake.get("launch"), dict) else {}
    role = str(intake.get("page_role") or launch.get("page_role") or Path(run).name)
    kind = intake.get("page_kind") or launch.get("page_kind")
    instance = intake.get("role_instance") or launch.get("role_instance")
    parts = [role] + ([str(kind)] if kind and str(kind) != role else []) + \
            ([str(instance)] if instance else [])
    return ":".join(parts)


def expected_pages(run_dir: Path) -> Tuple[Optional[List[Dict[str, Any]]], str]:
    """(the pages this launch planned, why-not) from Skill 49's inventory and the run's launch record.

    A directory walk answers "how many folders are there"; a launch answers "which pages exist".
    The launch record the dispatch writes (``launch.json``, with its chosen ``landing_pages`` from
    ``dispatch-report.json``) is read through Skill 49's own page_set, so page identity, order and
    the design-only pages are the inventory's, never a hard-coded list here.
    """
    launch = _read(Path(run_dir) / "launch.json")
    if not isinstance(launch, dict) or not launch.get("journey_mode"):
        return None, "the run has no launch.json with a journey_mode, so the planned page set is unknown"
    report = _read(Path(run_dir) / "dispatch" / "dispatch-report.json") or _read(Path(run_dir) / "dispatch-report.json")
    landing = None
    if isinstance(report, dict) and isinstance(report.get("landing_pages"), list):
        landing = [str(x) for x in report["landing_pages"]]
    try:
        page_set = _page_set()
    except Exception as exc:  # noqa: BLE001 — Skill 49 absent is a named refusal, never a guess
        return None, f"Skill 49's page_set could not be loaded ({exc.__class__.__name__})"
    try:
        planned = page_set.build_page_set(launch, landing_pages=landing)
    except Exception as exc:  # noqa: BLE001
        return None, f"Skill 49 refused the launch record: {exc}"
    pages = []
    for entry in planned["pages"]:
        key = entry["role"]
        if entry.get("page_kind") and entry["page_kind"] != entry["role"]:
            key += f":{entry['page_kind']}"
        if entry.get("role_instance"):
            key += f":{entry['role_instance']}"
        pages.append({"page_key": key, "label": entry.get("label"), "role": entry["role"],
                      "page_kind": entry.get("page_kind"), "role_instance": entry.get("role_instance"),
                      "design_only": bool(entry.get("design_only")),
                      "image_estimate": entry.get("image_estimate")})
    return pages, f"49-signature-funnel/structure/page_types.json ({len(pages)} planned page(s))"


def image_profile(run: Path) -> Optional[Dict[str, Any]]:
    """The governing page profile's image allowance for this page, from Skill 49's inventory."""
    try:
        page_set = _page_set()
        key = page_key_for_run(run)
    except Exception:  # noqa: BLE001
        return None
    try:
        pages = page_set.page_types()["pages"]
    except Exception:  # noqa: BLE001
        return None
    bare = key.split(":")[0]
    match = next((k for k, v in pages.items()
                  if k == key or (v.get("role") == bare and not v.get("role_instance"))), None)
    if match is None:
        return None
    profile = pages[match]
    return {"page_key": match, "sections": profile.get("sections"),
            "long_form_sections": profile.get("long_form_sections"),
            "image_estimate": page_set.image_estimate(match),
            "design_only": bool(profile.get("design_only"))}


def write_prompt_manifest(run: Path) -> Optional[Path]:
    """Rewrite ``image-inventory-prompts/prompt-manifest.json`` from the prompt files on disk.

    The stage contract requires this file beside the per-image prompts, and the swarm runner
    maintains it exactly this way (`{"prompts": [{id, file, sha256}]}`, deterministic order). The
    driver writes the same shape, so a run driven here and a run driven by the runner agree.
    """
    folder = Path(run) / "image-inventory-prompts"
    if not folder.is_dir():
        return None
    entries = [{"id": f.stem, "file": f"image-inventory-prompts/{f.name}", "sha256": _sha(f)}
               for f in sorted(folder.glob("IMG-*.txt")) if f.is_file()]
    if not entries:
        return None
    path = folder / "prompt-manifest.json"
    _write_json(path, {"prompts": entries})
    return path


def author_command(run_dir: Path, page_run: Path, kind: str) -> Optional[List[str]]:
    """A registered author command for this page, or None.

    `image_authoring.prompts` in the launch's ``launch.json`` or the page run's ``intake.json``,
    else the ``SKILL83_PROMPT_AUTHOR`` environment variable. A command is a list of words;
    ``{run_dir}`` is replaced with the page's run folder. Nothing is executed that the run did not
    declare, and an absent command is reported, never invented.
    """
    if kind != "prompts":
        return None
    env = os.environ.get(PROMPT_AUTHOR_ENV)
    if env:
        return [part.replace("{run_dir}", str(page_run)) for part in env.split()]
    for doc in (_read(Path(run_dir) / "launch.json"), _read(Path(page_run) / "intake.json")):
        authoring = (doc or {}).get("image_authoring") if isinstance(doc, dict) else None
        command = (authoring or {}).get(kind) if isinstance(authoring, dict) else None
        if isinstance(command, list) and command:
            return [str(part).replace("{run_dir}", str(page_run)) for part in command]
    return None


def _hosting_ledger(run_dir: Path, run: Path) -> Tuple[Optional[Dict[str, Any]], str]:
    """The media ledger the graphics hosting route writes (page run first, then the launch root)."""
    for path in (Path(run) / MEDIA_LIBRARY, Path(run_dir) / MEDIA_LIBRARY):
        doc = _read(path)
        if isinstance(doc, dict):
            return doc, str(path)
    return None, f"no {MEDIA_LIBRARY}: hosting has not recorded an upload for this launch"


_HTML_TYPES = ("text/html", "application/xhtml+xml")
_IMAGE_TYPES = ("image/png", "image/jpeg", "image/webp", "application/octet-stream", "binary/octet-stream")


def _inside_run(local: str, run: Path) -> bool:
    """True when a ledger path sits inside this page's run folder (the ledger records absolute paths)."""
    try:
        target = Path(local)
        target = target.resolve() if target.is_absolute() else (Path(run) / target).resolve()
        return target.is_relative_to(Path(run).resolve())
    except (OSError, ValueError):
        return False


def hosted_admission(run_dir: Path, run: Path) -> Dict[str, Any]:
    """Admit each hosted link for THIS launch's current artifacts. Returns a report, never raises.

    A hosted link is admitted only when all of these hold, and each refusal is named:

    * the local file is the CURRENT artifact — it exists and its bytes hash to the hash the ledger
      recorded (the local hash is the identity; a CDN may legitimately re-encode, so the remote
      bytes are never compared to it);
    * the ledger entry names the page/slot it serves (``asset_id`` or a ``local_path`` inside this
      page's run folder), so one upload cannot stand in for another page's slot;
    * a folder (``ghl_folder_id`` — a real id, or the route's documented "root" fallback) and a
      media id (``ghl_media_id`` or ``file_id``) are recorded;
    * the completion status is the route's recognised one (``ghl_upload_status == "complete"``);
    * the URL is a usable HTTP(S) URL that the route recorded as live, and the content type it
      recorded (when it recorded one) is an image or unspecified — never ``text/html``, which is
      what a failed or login-intercepted fetch returns and is not proof of a picture.
    """
    ledger, source = _hosting_ledger(run_dir, run)
    out: Dict[str, Any] = {"route": HOSTING_ROUTE, "ledger": source, "admitted": [], "refused": []}
    if ledger is None:
        out["state"] = "not_recorded"
        out["reason"] = source
        return out
    location = (str(ledger.get("location_id") or ledger.get("tenant_id") or "")).strip()
    run_intake = _read(Path(run) / "intake.json") or {}
    run_location = str((run_intake or {}).get("location_id") or "").strip() if isinstance(run_intake, dict) else ""
    out["location_id"] = location or None
    if location and run_location and location != run_location:
        out["state"] = "refused"
        out["refused"].append(f"the ledger belongs to location {location}, not this page's {run_location}")
        return out
    for entry in ledger.get("uploaded") or []:
        if not isinstance(entry, dict):
            continue
        local = str(entry.get("local_path") or "")
        name = Path(local).name or str(entry.get("asset_id") or "?")
        problems: List[str] = []
        target = Path(local) if Path(local).is_absolute() else Path(run) / local
        if not str(entry.get("asset_id") or "").strip() and not _inside_run(local, run):
            problems.append("names no page/slot (no asset_id, and its file is outside this page's run)")
        if not target.is_file():
            problems.append("the local artifact does not exist")
        elif entry.get("sha256") and _sha(target) != entry["sha256"]:
            problems.append("is not the current artifact (the ledger's hash is stale)")
        elif not entry.get("sha256"):
            problems.append("records no local content hash, so it cannot be bound to the current file")
        if not str(entry.get("ghl_folder_id") or "").strip():
            problems.append("records no folder")
        if not str(entry.get("ghl_media_id") or entry.get("file_id") or "").strip():
            problems.append("records no media id")
        if entry.get("ghl_upload_status") != "complete":
            problems.append(f"completion status is {entry.get('ghl_upload_status')!r}, not 'complete'")
        url = str(entry.get("public_url") or entry.get("ghl_public_url") or "")
        if not url.lower().startswith(("http://", "https://")):
            problems.append("records no usable hosted URL")
        live = entry.get("liveness") if isinstance(entry.get("liveness"), dict) else {}
        if live.get("live") is not True:
            problems.append("the URL is not recorded as live")
        ctype = str(entry.get("content_type") or entry.get("mime_type") or "").split(";")[0].strip().lower()
        if ctype in _HTML_TYPES:
            problems.append(f"the URL returned {ctype}, which is a page, not a picture")
        elif ctype and ctype not in _IMAGE_TYPES:
            problems.append(f"the URL returned {ctype}, not an image")
        if problems:
            out["refused"].append({"file": name, "problems": problems})
        else:
            out["admitted"].append({"file": name, "public_url": url,
                                    "ghl_media_id": entry.get("ghl_media_id") or entry.get("file_id"),
                                    "sha256": entry.get("sha256")})
    out["state"] = "pass" if out["admitted"] and not out["refused"] else (
        "partial" if out["admitted"] else "refused")
    return out


def qc_passed(run: Path, item_id: str, delivered: str) -> bool:
    """True only when the gate's OWN record says this image passed its review.

    Two authorities, in order: the item's close in ``private/state.json`` (status closed, the
    Review Receipt v2 file it names has verdict ``pass``, and the file still hashes to the
    ``review_hash`` recorded at close — the gate's item gate, references/item-gate-spec.md); then
    a run-level QC record (``image-generation-qc/image-qc.json`` or ``qc/image_qc_report.json``)
    whose entry passes with no automatic failure. Anything else is not a pass.
    """
    state = _read(Path(run) / "private" / "state.json") or {}
    items = state.get("items") if isinstance(state, dict) else None
    entry = ((items or {}).get("image-generation-qc") or {}).get(item_id) if isinstance(items, dict) else None
    if isinstance(entry, dict) and entry.get("status") == "closed" and entry.get("review"):
        review_path = Path(run) / str(entry["review"])
        review = _read(review_path)
        if (isinstance(review, dict) and review.get("verdict") == "pass"
                and (not entry.get("review_hash") or _sha(review_path) == entry["review_hash"])):
            return True
    for doc in (_read(Path(run) / "image-generation-qc" / "image-qc.json"),
                _read(Path(run).parent / "qc" / "image_qc_report.json")):
        records = ((doc or {}).get("images") or (doc or {}).get("assets") or []) if isinstance(doc, dict) else []
        for record in records:
            if not isinstance(record, dict) or record.get("pass") is not True or record.get("triggered_autofails"):
                continue
            named = {str(record.get("id") or ""), str(record.get("asset_id") or ""),
                     Path(str(record.get("local_path") or "")).stem}
            if item_id in named or Path(delivered).stem in named:
                return True
    return False


def write_image_map(run_dir: Path, run: Path) -> Optional[Path]:
    """Author ``image-map-upload/image-map.json`` (+ ``.md``) from the page's own artifacts.

    Deterministic work, never a model call: one entry per inventory slot, in inventory order, with
    the delivered file, its measured size, its QC status from the gate's own item record when one
    exists, and the admitted hosted URL when hosting recorded one. A slot with no generated file
    yet is `missing`; a supplied slot names its supplied file and is never generated. The map is
    written only when the stage's own validator accepts it (validate_image_manifest.py), so a map
    that cannot pass never appears to be one.

    Returns the map path, or None when the map cannot be authored yet (the caller reports why).
    """
    inventory = inventory_doc(run)
    if inventory is None:
        return None
    module = _skill71_module(MAP_VALIDATOR)
    try:
        items = module.inventory_items(inventory)
    except (ValueError, AttributeError):
        return None
    hosted = hosted_admission(run_dir, run)
    urls = {entry["file"]: entry["public_url"] for entry in hosted.get("admitted") or []}
    entries: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        item_id = str(item["id"])
        digits = "".join(ch for ch in item_id if ch.isdigit())
        delivered = f"image-generation-qc/Image-{int(digits):02d}.png" if digits else ""
        target = Path(run) / delivered if delivered else None
        source = str(item.get("source") or item.get("asset_kind") or "").strip().lower()
        supplied = _slot_is_supplied(module, item)
        entry: Dict[str, Any] = {
            "id": item_id,
            "job": str(item.get("job") or item.get("slot_id") or ""),
            "filename": delivered or str(item.get("file") or ""),
            "status": "missing",
            "alt_text": str(item.get("alt_text") or item.get("description") or item_id),
            "intended_ratio": str(item.get("aspect_ratio") or "4:3"),
            "crop_focal": str(item.get("crop_focal") or "center"),
            "prompt_file": f"image-inventory-prompts/{item_id}.txt",
        }
        if supplied:
            supplied_file = str(item.get("file") or item.get("asset_file") or "")
            entry.update(status="ready", asset_path=supplied_file, qc_status="passed",
                         supplied_asset=item.get("supplied_asset") or {})
        elif target is not None and target.is_file():
            size = _png_size(target)
            entry.update(status="ready", asset_path=delivered,
                         **({"width": size[0], "height": size[1]} if size else {}),
                         qc_status="passed" if qc_passed(run, item_id, delivered) else "pending")
            if delivered in urls:
                entry["hosted_url"] = urls[delivered]
        entries.append(entry)
    doc = {"images": entries}
    errors = module.validate(doc, run, check_files=False, inventory_data=inventory, measure=False)
    if errors:
        raise Stop("blocked", "image-map-upload: the map the page's own artifacts produce does not pass "
                              "validate_image_manifest.py: " + "; ".join(errors[:3]))
    folder = Path(run) / "image-map-upload"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "image-map.json"
    _write_json(path, doc)
    lines = [f"# Image map — {page_key_for_run(run)}", "",
             "| id | status | file | hosted |", "|---|---|---|---|"]
    lines += [f"| {e['id']} | {e['status']} | {e.get('asset_path') or e['filename'] or '-'} | "
              f"{e.get('hosted_url') or 'not hosted'} |" for e in entries]
    (folder / "image-map.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _png_size(path: Path) -> Optional[Tuple[int, int]]:
    """(width, height) from a PNG's IHDR, or None: the map's measured size, no Pillow needed."""
    try:
        with Path(path).open("rb") as fh:
            head = fh.read(24)
    except OSError:
        return None
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        return None
    return (int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big"))


def _upsert(result: Dict[str, Any], fresh: List[Dict[str, Any]], old: set) -> bool:
    """Put ``fresh`` artifacts into ``result`` (replace the same path, else append) when it lists any of ``old``."""
    arts = result.get("artifacts")
    if not isinstance(arts, list) or not any(isinstance(a, dict) and (a.get("path"), a.get("sha256")) in old
                                             for a in arts):
        return False
    by_path = {a["path"]: a for a in fresh}
    result["artifacts"] = [by_path.pop(a["path"], a) if isinstance(a, dict) else a for a in arts] + list(by_path.values())
    return True


def _own_form(page_run: Path, artifacts: Sequence[Any]) -> Optional[str]:
    """How a piece names this run's files, or None when it lists none of them: "prefix" (``<run folder>/path``,
    the form landing_bridge gives an opt-in run's files, resolved from the run's parent exactly as
    package._artifact_source does), "absolute", or "relative" (from the run). A file counts only when it sits
    inside the run AND carries the hash listed for it. The prefix form is tried first: it names the run, while
    a bare name can match another run's identical file (two runs share generic names and some bytes)."""
    def mine(digest: Any, target: Path) -> bool:
        return target.is_file() and target.resolve().is_relative_to(page_run) and (not digest or _sha(target) == digest)

    listed = [(a.get("path"), a.get("sha256")) for a in artifacts if isinstance(a, dict) and isinstance(a.get("path"), str)]
    if any(p.startswith(page_run.name + "/") and mine(d, page_run.parent / p) for p, d in listed):
        return "prefix"
    for p, d in listed:
        if Path(p).is_absolute() and mine(d, Path(p)):
            return "absolute"
        if not Path(p).is_absolute() and mine(d, page_run / p):
            return "relative"
    return None


def _write_json(path: Path, doc: Any) -> None:
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def refresh_pieces(run_dir: Path, page_run: Path) -> List[str]:
    """Re-list one page's design files in its piece after its final-mockups stage closed. Returns the slots refreshed.

    A piece (``pieces/<slot>.json``) belongs to the page run when one of its artifacts is that file inside it
    (same bytes; see ``_own_form``). The run's files are listed again with Skill 49's own
    ``page_set.design_artifacts``, for the page key the PIECE names (a landing-lane piece's page_kind: the
    sales-only slot "landing" is the "sales" page), in the form the piece already uses (absolute, relative to
    the run, or prefixed with the run folder name as the opt-in run's files are; with the provider when the
    piece names one) and merged by path. The piece must stay one of the
    dispatch's own artifacts (``package._bind_piece``), so every stored dispatch result that lists the
    piece's files, and the dispatch manifest's copy of it, takes the same files.
    """
    run_dir, page_run = Path(run_dir), Path(page_run).resolve()
    page_set = _page_set()
    pages = page_set.page_types()["pages"]
    by_kind = {v["page_kind"]: k for k, v in pages.items() if v.get("page_kind")}  # opt_in -> landing, sales -> sales
    intake = _read(page_run / "intake.json")
    run_kind = intake.get("page_kind") if isinstance(intake, dict) else None
    stored = [p for p in sorted((run_dir / "dispatch").glob("*result-*.json"))]
    manifest_path = run_dir / "dispatch" / "dispatch-manifest.json"
    manifest = _read(manifest_path)
    refreshed: List[str] = []
    for piece_path in sorted((run_dir / "pieces").glob("*.json")):
        piece = _read(piece_path)
        if piece_path.stem not in pages or not isinstance(piece, dict):
            continue
        # the page key comes from the piece, not its slot: the sales-only lane's slot is "landing" but it is the sales page
        kind = piece.get("page_kind")
        key = by_kind.get(kind, piece_path.stem)
        if kind in by_kind and run_kind != kind:  # a landing-lane piece is refreshed only from the run of its own kind
            continue
        form = _own_form(page_run, piece.get("artifacts") or [])
        if form is None:
            continue
        fresh = page_set.design_artifacts(key, page_run, relative=form != "absolute",
                                          with_provider=any(isinstance(a, dict) and "provider" in a
                                                          for a in piece["artifacts"]))
        if form == "prefix":
            fresh = [{**a, "path": f"{page_run.name}/{a['path']}"} for a in fresh]
        old = {(a.get("path"), a.get("sha256")) for a in piece["artifacts"] if isinstance(a, dict)}
        _upsert(piece, fresh, old)
        _write_json(piece_path, piece)
        for path in stored:
            doc = _read(path)
            if isinstance(doc, dict) and _upsert(doc, fresh, old):
                _write_json(path, doc)
        if isinstance(manifest, dict):
            for doc in list(manifest.get("results") or []) + list((manifest.get("page_results") or {}).values()):
                if isinstance(doc, dict):
                    _upsert(doc, fresh, old)
        refreshed.append(piece_path.stem)
    if refreshed and isinstance(manifest, dict):
        _write_json(manifest_path, manifest)
    return refreshed


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


def _page_entry(run: Path, run_dir: Path, approval: Optional[Dict[str, Any]], scripts: Path,
                runner: Runner, provider: str, allow_paid: bool) -> Dict[str, Any]:
    """One page's report entry: its identity, its own chain, its authored work and its hosting."""
    entry: Dict[str, Any] = {"page": run.name, "page_key": page_key_for_run(run), "role": page_role(run),
                             "run_dir": str(run.resolve())}
    profile = image_profile(run)
    if profile:
        entry["image_profile"] = profile
    try:
        supplied = supplied_items(run)
        generated = generation_items(run)
    except Stop as stop:  # Skill 71's own inventory rule is unavailable: say so, never guess a count
        entry["asset_quantity"] = {"state": "unknown", "reason": stop.reason}
        supplied, generated = [], []
    else:
        if supplied:
            entry["supplied_slots"] = supplied
        entry["asset_quantity"] = {
            "inventory_generation_items": len(generated),
            "inventory_supplied_items": len(supplied),
            "profile_image_estimate": (profile or {}).get("image_estimate"),
            "counted_from": "desktop-wireframe/image-inventory.json through Skill 71's own "
                            "validate_image_manifest rule; the profile's allowance is Skill 49's page_types.json",
        }
    if approval is None:
        entry.update(status="awaiting_layout_proof_approval",
                     stages={s: "open" if not stage_closed(run, s) else "closed" for s in STAGES},
                     reason="the layout proofs are the first approval checkpoint; nothing is drawn until the "
                            f"client's approval is recorded in {LAYOUT_APPROVAL_REL}")
        return entry
    page = _Page(run, scripts, runner, provider, allow_paid, run_dir=run_dir)
    stages = page.advance()
    if stages.get("final-mockups") == "closed":  # the labeled final files exist now: list them in the piece
        entry["pieces_refreshed"] = refresh_pieces(run_dir, run)
    done = all(v in ("closed", "not_applicable") for v in stages.values())
    chain = layout_chain(run)
    entry["layout_chain"] = chain
    entry["design_chain_complete"] = bool(done and chain["complete"])
    entry.update(status="complete" if done else (page.stop.status if page.stop else "blocked"),
                 stages=stages,
                 reason=None if done else (page.stop.reason if page.stop else "a stage is still open"),
                 commands=page.log)
    if not chain["complete"]:
        # The image chain's stages depend on the layout stages, so a real run cannot reach here
        # without them; a run that does is named rather than reported as the finished design chain.
        entry["layout_chain_gap"] = [s for s, v in chain["stages"].items() if v != "closed"] or \
                                    ["no review PDFs on disk"]
    if page.tasks:
        entry["owned_tasks"] = page.tasks
    if page.notes.get("not_applicable"):
        entry["not_applicable"] = page.notes["not_applicable"]
    entry["hosting"] = page.notes.get("hosting") or hosted_admission(run_dir, run)
    return entry


def drive(run_dir: Path, *, runner: Runner = default_runner, provider: str = "stub",
          allow_paid: bool = False, layout_approval_file: Optional[Path] = None,
          repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """Drive every planned page of the launch. Writes and returns the report.

    The page set is the launch's, not the folder walk's: Skill 49's inventory read against this
    run's launch record. A planned page with no run folder is named missing (and carries the path
    it should have been found at), so a missing page can never be read as a count that adds up.
    A discovered run the launch did not plan is named `unexpected_run`, never counted as a page.
    """
    run_dir = Path(run_dir)
    scripts = scripts_dir(repo_root)
    runs = discover_page_runs(run_dir)
    planned, planned_source = expected_pages(run_dir)
    by_key = {page_key_for_run(run): run for run in runs}
    approval = layout_approval(run_dir, layout_approval_file)
    pages: List[Dict[str, Any]] = []
    if planned:
        for want in planned:
            run = by_key.pop(want["page_key"], None)
            if run is None:
                pages.append({"page": want["page_key"].replace(":", "-"), "page_key": want["page_key"],
                              "role": want["role"], "label": want.get("label"),
                              "status": "missing_page",
                              "run_dir": str((run_dir / "dispatch" / want["page_key"].replace(":", "-")).resolve()),
                              "stages": {s: "open" for s in STAGES},
                              "reason": "the launch plans this page and no Skill 71 run folder for it was found"})
                continue
            pages.append(_page_entry(run, run_dir, approval, scripts, runner, provider, allow_paid))
    else:
        pages = [_page_entry(run, run_dir, approval, scripts, runner, provider, allow_paid) for run in runs]
        by_key = {}
    for extra_key, run in sorted(by_key.items()):
        entry = _page_entry(run, run_dir, approval, scripts, runner, provider, allow_paid)
        entry.update(status="unexpected_run",
                     reason=f"this run is not a page {planned_source or 'the launch'} plans")
        pages.append(entry)
    missing = [p["page_key"] for p in pages if p.get("status") == "missing_page"]
    complete = bool(pages) and all(p["status"] == "complete" for p in pages) and not missing
    report = {"schema": SCHEMA, "run_dir": str(run_dir.resolve()), "stages": list(STAGES),
              "first_checkpoint": "layout proofs", "layout_proof_approval": (approval or {}).get("approval_ref"),
              "provider": provider, "pages": pages, "complete": complete,
              "expected_pages_source": planned_source if planned else None,
              "expected_pages_state": "known" if planned else "unknown",
              "missing_pages": missing,
              "qc_request": _write_qc_request(run_dir) if runs else None}
    if not planned:
        report["reason"] = (planned_source or "the planned page set is unknown") + \
            "; the pages listed are the run folders that were discovered, never a proven complete set"
    elif not runs:
        report["reason"] = "no Skill 71 page run folder (intake.json beside private/) was found under this run"
    path = run_dir / REPORT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def summary_lines(report: Dict[str, Any]) -> List[str]:
    lines = []
    for p in report["pages"]:
        closed = sum(1 for v in p["stages"].values() if v == "closed")
        na = sum(1 for v in p["stages"].values() if v == "not_applicable")
        note = (f", {na} not applicable" if na else "")
        lines.append(f"{p['page']} ({p['role']}): {p['status']}, {closed} of {len(STAGES)} image stages closed{note}"
                     + (f". {p['reason']}" if p.get("reason") else ""))
        for task in p.get("owned_tasks") or []:
            lines.append(f"  owned task: {task['stage']} -> {task['owner']} owes {', '.join(task['missing'][:6])}")
        if p.get("layout_chain_gap"):
            lines.append(f"  layout chain gap: {', '.join(p['layout_chain_gap'])}; "
                         "the image chain is not the whole design chain")
    if report.get("missing_pages"):
        lines.append("MISSING PAGES (planned, no run): " + ", ".join(report["missing_pages"]))
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
