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

The map stage is produced here, not left to the author: ``write_image_map`` builds
``image-map-upload/image-map.json`` from the files that exist, the client's logo (the file the brand
answer produced), the SOP-GIP-02 verdicts and the public URLs the Skill 45 upload really recorded in
``media_library.json``. The same map is the asset map every page renderer reads
(``shared-utils/signature_launch/design/image_slots.py``), and ``rewrite_page_assets`` replaces a
page's local file references with those hosted URLs while responsive-html is still open. An entry
with no passing review, or with no hosted URL on a production run, stops the stage by name.

The SOP-GIP-02 request and the report it names are the launch's, written once in
``<launch run>/qc/``. A page run is nested (``<launch run>/dispatch/<page>``), so both are read
through ``graphics_hooks.qc_report_root`` — the same resolution the package gate uses — and a
page run's own ``qc/`` folder is never mistaken for the launch's.

``python3 -m launcher_core.image_stages --run-dir <launch run folder>`` exits 0 only when every page
has all five stages closed, and always writes ``qc/image_stages_report.json``. The package check
(check_rules/image_qc.py) re-reads each page's own stage state, so the report is never trusted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
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
# The asset map every page renderer reads (shared-utils/signature_launch/design/image_slots.py):
# one entry per image slot, carrying the hosted URL the upload returned in `ghl_media_url`.
IMAGE_MAP_DIR = "image-map-upload"
IMAGE_MAP_REL = "image-map-upload/image-map.json"
IMAGE_MAP_MD_REL = "image-map-upload/image-map.md"
IMAGE_SLOTS_REF = "shared-utils/signature_launch/design/image_slots.py"
HOSTED_LEDGER_REL = "media_library.json"
PAGE_HTML_DIR = "responsive-html"
BRAND_LOGO_SLOT = "BRAND-LOGO"
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


def _number(name: str) -> Optional[int]:
    digits = "".join(c for c in name if c.isdigit())
    return int(digits) if digits else None


def default_runner(argv: List[str]) -> Tuple[int, str]:
    """Run one command; keep only the tail of its output (a run folder can hold client names)."""
    done = subprocess.run([str(a) for a in argv], capture_output=True, text=True, timeout=3600)
    text = (done.stdout or "") + (done.stderr or "")
    return done.returncode, "\n".join(text.strip().splitlines()[-12:])


# ---------------------------------------------------------------- the asset map (image-map-upload)
def _inventory_entries(run: Path) -> List[Dict[str, Any]]:
    doc = _read(Path(run) / "desktop-wireframe" / "image-inventory.json")
    if isinstance(doc, list):
        return [i for i in doc if isinstance(i, dict)]
    if isinstance(doc, dict):
        for key in ("images", "items", "inventory"):
            if isinstance(doc.get(key), list):
                return [i for i in doc[key] if isinstance(i, dict)]
    return []


def _png_size(path: Path) -> Tuple[int, int]:
    """The file's own pixel size from its PNG header, or (0, 0) when it cannot be read."""
    try:
        head = Path(path).read_bytes()[:24]
    except OSError:
        return (0, 0)
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        return (0, 0)
    return (int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big"))


def _png_ratio(path: Path) -> str:
    """The file's own width:height, reduced; 1:1 when the header cannot be read."""
    width, height = _png_size(Path(path))
    if not width or not height:
        return "1:1"
    divisor = math.gcd(width, height)
    return f"{width // divisor}:{height // divisor}"


def _qc_folder(run: Path) -> Path:
    """The launch folder that holds this run's SOP-GIP-02 request and report.

    A page run is nested inside its launch run (``<launch run>/dispatch/<page>``) and the review is
    written once for the whole launch, in the launch run's ``qc/`` folder — the folder the
    launcher's own ``_write_qc_request`` writes the request into and the one the package gate
    reads (``graphics_hooks.qc_report_root``). Asking the page run for its own ``qc/`` found
    nothing, which is why the same report could pass the package gate and leave this map
    unverified."""
    from . import graphics_hooks
    return graphics_hooks.qc_report_root(run)


def _qc_records(root: Path) -> Dict[str, Dict[str, Any]]:
    """SOP-GIP-02 report records by resolved asset path, from the launch folder that holds them."""
    from . import graphics_hooks
    doc = _read(_qc_folder(root) / graphics_hooks.QC_REPORT_REL) or {}
    out: Dict[str, Dict[str, Any]] = {}
    for rec in (doc.get("assets") or []) if isinstance(doc, dict) else []:
        if isinstance(rec, dict) and rec.get("local_path"):
            out[str(Path(str(rec["local_path"])).resolve())] = rec
    return out


_HTML_TYPES = ("text/html", "application/xhtml+xml")
# Content type -> the format its BYTES must decode as. A recorded type alone is not evidence.
# The accepted types are exactly the ones admission accepted before; nothing new is admitted.
_IMAGE_TYPE_FORMATS = {"image/png": "png", "image/jpeg": "jpeg", "image/webp": "webp"}
# Generic binary is a transport detail, not an image claim: admitted only with decoded image bytes.
_GENERIC_BINARY_TYPES = ("application/octet-stream", "binary/octet-stream")


def _image_evidence(entry: Dict[str, Any]) -> Dict[str, Any]:
    """What the fetched bytes ARE, as the hosting route recorded them: format, dimensions, decode.

    ``45-design-intelligence-library/scripts/graphics_ghl_push.py`` reads the magic header and the
    pixel dimensions of the body it fetched and records them under ``liveness.image``. An entry
    that carries no such record is not evidence of a picture, so an empty dict here is refused."""
    live = entry.get("liveness") if isinstance(entry.get("liveness"), dict) else {}
    image = live.get("image") if isinstance(live.get("image"), dict) else {}
    return image


def remote_image_problems(entry: Dict[str, Any]) -> List[str]:
    """Why the hosted URL's recorded remote evidence is not a picture (F17), or [].

    A nonempty HTML response is insufficient proof of an image, so the route records the real
    Content-Type header and what the fetched bytes decode to (magic header + dimensions). Admission
    refuses by name: no content type at all (an unrecorded header is not evidence and is never
    filled in from the filename), an HTML/XML/JSON or any other non-image type, bytes that do not
    decode as an image, and a type that contradicts the bytes. A generic ``octet-stream`` is
    admitted only when the bytes themselves decode as an image.
    """
    problems: List[str] = []
    ctype = str(entry.get("content_type") or entry.get("mime_type") or "").split(";")[0].strip().lower()
    evidence = _image_evidence(entry)
    fmt = str(evidence.get("format") or "").strip().lower()
    width, height = evidence.get("width"), evidence.get("height")
    decodes = (evidence.get("decodes") is True and isinstance(width, int) and isinstance(height, int)
               and width > 0 and height > 0)
    if not ctype:
        problems.append("records no remote content type, so a login page cannot be told from a picture")
    elif ctype in _HTML_TYPES:
        problems.append(f"the URL returned {ctype}, which is a page, not a picture")
    elif ctype in _GENERIC_BINARY_TYPES:
        pass  # a transport detail: the decoded bytes below are the evidence
    elif ctype not in _IMAGE_TYPE_FORMATS:
        problems.append(f"the URL returned {ctype}, not an image")
    if not decodes:
        problems.append("the fetched bytes do not decode as an image (no readable image header/dimensions)")
    elif ctype in _IMAGE_TYPE_FORMATS and _IMAGE_TYPE_FORMATS[ctype] != fmt:
        problems.append(f"the URL returned {ctype} but its bytes decode as {fmt}")
    return problems


def _hosted_urls(root: Path) -> Dict[str, str]:
    """The public URL each asset really got: complete upload AND a live link, https only, and —
    F17 — remote evidence that the URL really served a picture, never a 200 that is a login page."""
    doc = _read(Path(root) / HOSTED_LEDGER_REL) or {}
    out: Dict[str, str] = {}
    for rec in (doc.get("uploaded") or []) if isinstance(doc, dict) else []:
        url = str(rec.get("public_url") or "")
        if rec.get("ghl_upload_status") == "complete" and (rec.get("liveness") or {}).get("live") is True \
                and url.startswith("https://") and rec.get("local_path") \
                and not remote_image_problems(rec):
            out[str(Path(str(rec["local_path"])).resolve())] = url
    return out


def hosted_admission(run_dir: Path, run: Path) -> Dict[str, Any]:
    """Admit each hosted link for this run's current artifacts. Returns a report, never raises.

    The same rules the asset map applies — a complete upload, a live link, a usable http(s) URL
    and a local file that still hashes to what the ledger recorded — plus the F17 remote evidence: the
    URL must have served a real content type and bytes that decode as an image with readable
    dimensions. Every refusal is named, so an HTTP 200 whose body is an HTML login page is refused
    as a page rather than admitted as a picture.
    """
    run, run_dir = Path(run), Path(run_dir)
    doc, source = None, ""
    for path in (run / HOSTED_LEDGER_REL, run_dir / HOSTED_LEDGER_REL):
        loaded = _read(path)
        if isinstance(loaded, dict):
            doc, source = loaded, str(path)
            break
    out: Dict[str, Any] = {"ledger": source or None, "admitted": [], "refused": []}
    if doc is None:
        out["state"] = "not_recorded"
        out["reason"] = f"no {HOSTED_LEDGER_REL}: hosting has not recorded an upload for this run"
        return out
    rows = doc.get("uploaded") if isinstance(doc.get("uploaded"), list) else []
    for entry in rows:
        if not isinstance(entry, dict):
            continue
        local = str(entry.get("local_path") or "")
        name = Path(local).name or str(entry.get("asset_id") or "?")
        url = str(entry.get("public_url") or "")
        problems: List[str] = []
        target = Path(local) if Path(local).is_absolute() else run / local
        if not local or not target.is_file():
            problems.append("the local artifact does not exist")
        elif entry.get("sha256") and _sha(target) != entry["sha256"]:
            problems.append("is not the current artifact (the ledger's hash is stale)")
        if entry.get("ghl_upload_status") != "complete":
            problems.append(f"completion status is {entry.get('ghl_upload_status')!r}, not 'complete'")
        if not url.lower().startswith(("http://", "https://")):
            problems.append("records no usable hosted URL")
        live = entry.get("liveness") if isinstance(entry.get("liveness"), dict) else {}
        if live.get("live") is not True:
            problems.append("the URL is not recorded as live")
        problems.extend(remote_image_problems(entry))
        if problems:
            out["refused"].append({"file": name, "problems": problems})
        else:
            out["admitted"].append({"file": name, "local_path": local, "public_url": url,
                                    "ghl_media_id": entry.get("ghl_media_id") or entry.get("file_id"),
                                    "sha256": entry.get("sha256")})
    out["state"] = "pass" if out["admitted"] and not out["refused"] else (
        "partial" if out["admitted"] else "refused")
    return out


def _map_entry(run: Path, slot_id: str, path: Path, digest: str, slot: Dict[str, Any],
               qc: Dict[str, Dict[str, Any]], hosted: Dict[str, str], alt: str) -> Dict[str, Any]:
    from . import graphics_hooks
    rec = qc.get(str(path.resolve())) or {}
    # the same binding the package gate applies: only a review of these bytes by two named,
    # different models earns the word "passed" in the map. It is judged against the launch folder
    # the report lives in, so a relative review_ref resolves exactly as it does for the gate.
    passed = bool(rec) and not graphics_hooks.asset_review_problems(
        rec, {"local_path": str(path), "page": slot_id, "sha256": digest, "asset_id": slot_id},
        _qc_folder(run))
    url = hosted.get(str(path.resolve()))
    width, height = _png_size(path)
    # the validator resolves asset paths against the image-map's own folder
    rel = os.path.relpath(str(path), str(Path(run) / IMAGE_MAP_DIR)).replace(os.sep, "/")
    return {"id": slot_id, "job": page_role(run), "filename": path.name, "status": "ready",
            "asset_path": rel, "sha256": digest, "width": width or None, "height": height or None,
            "alt_text": str(slot.get("alt_text") or slot.get("alt") or slot.get("description") or alt),
            "intended_ratio": str(slot.get("intended_ratio") or slot.get("ratio")
                                  or slot.get("aspect_ratio") or _png_ratio(path)),
            "crop_focal": slot.get("crop_focal") or "center",
            "qc_status": "passed" if passed else "unverified",
            "ghl_media_url": url, "hosting_state": "hosted" if url else "not_hosted"}


def image_map_entries(run: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """(page entries, brand entries, state) for the run's asset map.

    Every generated file in image-generation-qc gets its inventory id under ``images``; the
    client's logo (the file the brand answer produced) gets BRAND_LOGO_SLOT under
    ``brand_assets`` — Skill 71's validator counts every ``images`` entry as a generated
    master, and the logo is not one, so it rides in the same file under its own key where
    every renderer still resolves it. ``state`` names what is missing: no URL is ever written
    that the upload did not return."""
    run = Path(run)
    qc, hosted = _qc_records(run), _hosted_urls(run)
    inventory = {str(i.get("id")): i for i in _inventory_entries(run) if i.get("id")}
    id_by_number = {_number(k): k for k in inventory if _number(k) is not None}
    entries: List[Dict[str, Any]] = []
    for path in sorted((run / "image-generation-qc").glob("Image-*.png")):
        number = _number(path.stem)
        slot_id = id_by_number.get(number) if number is not None else None
        slot_id = str(slot_id) if slot_id else (f"IMG-{number:03d}" if number is not None else path.stem)
        entry = _map_entry(run, slot_id, path, _sha(path), inventory.get(slot_id) or {},
                           qc, hosted, f"{page_role(run)} image {number}")
        # Skill 71's map contract names the prompt that made each generated image. It is
        # recorded when it exists; an image with no prompt on file says so by status.
        prompt = run / "image-inventory-prompts" / f"{slot_id}.txt"
        entry["prompt_file"] = (os.path.relpath(str(prompt), str(run / IMAGE_MAP_DIR))
                                .replace(os.sep, "/") if prompt.is_file() else None)
        entry["status"] = "ready" if prompt.is_file() else "missing"
        entries.append(entry)
    from . import graphics_hooks
    brand_entries: List[Dict[str, Any]] = []
    for asset in graphics_hooks.brand_logo_assets(run):
        path = Path(asset["local_path"])
        brand_entries.append(_map_entry(run, BRAND_LOGO_SLOT, path, asset["sha256"], {},
                                        qc, hosted, "the client's logo"))
    every = entries + brand_entries
    unverified = [e["id"] for e in every if e["qc_status"] != "passed"]
    unhosted = [e["id"] for e in every if not e["ghl_media_url"]]
    missing: List[str] = []
    if unverified:
        missing.append("no passing SOP-GIP-02 review for " + ", ".join(unverified))
    if unhosted:
        missing.append("no hosted URL recorded for " + ", ".join(unhosted))
    return entries, brand_entries, {
        "qc_state": "covered" if every and not unverified else "unverified",
        "hosting_state": "hosted" if every and not unhosted else "not_hosted",
        "missing": missing}


def write_image_map(run: Path) -> Dict[str, Any]:
    """Write image-map-upload/image-map.json and .md (Skill 71's stage artifacts)."""
    run = Path(run)
    entries, brand_entries, state = image_map_entries(run)
    out_dir = run / IMAGE_MAP_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = {"images": entries, "brand_assets": brand_entries,
           "generated_by": "launcher_core.image_stages",
           "qc_state": state["qc_state"], "hosting_state": state["hosting_state"],
           "missing": state["missing"]}
    (run / IMAGE_MAP_REL).write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [f"# Image map — {page_role(run)}", "",
             "| slot | file | sha256 | QC | hosted URL |", "|---|---|---|---|---|"]
    for e in entries + brand_entries:
        lines.append(f"| {e['id']} | {e['filename']} | {e['sha256'][:12]}… | {e['qc_status']} | "
                     f"{e['ghl_media_url'] or 'not hosted'} |")
    if state["missing"]:
        lines += ["", "## Missing", *[f"- {m}" for m in state["missing"]]]
    (run / IMAGE_MAP_MD_REL).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return doc


def _image_slots_module():
    """The shared image-slot contract every page renderer uses; None when it is not installed."""
    path = resolve_ref(IMAGE_SLOTS_REF, REPO_ROOT)
    if not path.is_file():
        return None
    import importlib.util
    spec = importlib.util.spec_from_file_location("signature_launch_image_slots", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def rewrite_page_assets(run: Path) -> Dict[str, int]:
    """Point the run's authored pages at the hosted asset URLs.

    Runs only while responsive-html is open: rewriting a closed stage would change bytes the
    gate already hashed. A page is left untouched when no entry carries a URL yet, so a page
    is never rewritten to a link that does not exist."""
    run = Path(run)
    if stage_closed(run, PAGE_HTML_DIR):
        return {}
    doc = _read(run / IMAGE_MAP_REL)
    if not isinstance(doc, dict):
        return {}
    listed = [e for group in (doc.get("images"), doc.get("brand_assets"))
              for e in (group or []) if isinstance(e, dict)]
    if not any(e.get("ghl_media_url") for e in listed):
        return {}
    module = _image_slots_module()
    if module is None:
        return {}
    slots = module.build_slots(doc, [run, run / IMAGE_MAP_DIR])
    changed: Dict[str, int] = {}
    for html_path in sorted((run / PAGE_HTML_DIR).glob("*.html")):
        try:
            text = html_path.read_text(encoding="utf-8")
        except OSError:
            continue
        new_text, changes = module.apply_hosted_urls(text, slots)
        if changes and new_text != text:
            html_path.write_text(new_text, encoding="utf-8")
            changed[str(html_path.relative_to(run))] = len(changes)
    return changed


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
        """Write the asset map from what exists: the generated files, the client's logo, the
        SOP-GIP-02 verdicts and the URLs the upload really returned.

        The map is written even when it is incomplete, so the pages can be pointed at whatever
        is hosted; the stage then stops by name on what is genuinely missing rather than
        closing on an empty or invented link."""
        doc = write_image_map(self.run)
        if doc["qc_state"] != "covered":
            from . import graphics_hooks
            launch = _qc_folder(self.run)  # the one folder the request and the report live in
            raise Stop("needs_qc",
                       "image-map-upload: " + "; ".join(doc["missing"]) + ". Run SOP-GIP-02 "
                       f"({launch / graphics_hooks.QC_REQUEST_REL} lists every asset), write each "
                       "review with scripts/write_review.py --author-model/--reviewer-model and "
                       f"record it in {launch / graphics_hooks.QC_REPORT_REL}, then run this again")
        if doc["hosting_state"] != "hosted":
            intake = _read(self.run / "intake.json") or {}
            if not (isinstance(intake, dict) and intake.get("test_run")):
                raise Stop("needs_hosting",
                           "image-map-upload: " + "; ".join(doc["missing"]) + ". Host the QC-passed "
                           "assets with 45-design-intelligence-library/scripts/graphics_ghl_push.py "
                           "(it needs an approval_ref for the client's location), then run this again: "
                           "a page may not ship a file on our disk as the client's image")

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


def _page_set():
    """Skill 49's page_set (the one list of a page's design files), loaded through the substrate."""
    if str(_ROUTES_DIR) not in sys.path:
        sys.path.insert(0, str(_ROUTES_DIR))
    import substrate
    return substrate.load("49-signature-funnel/scripts/page_set.py", "launcher_page_set",
                          "49-signature-funnel/scripts")


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
    """SOP-GIP-02 request for every image the launch's pieces list (graphics_hooks.qc_request).

    Written into the launch run's own folder — the one canonical place ``qc_report_root`` finds
    from every nested page run — and with absolute asset paths, so a record names the same bytes
    whichever folder reads it back. The reviewer's report is ``expected_report`` beside it."""
    run_dir = Path(run_dir).resolve()
    pieces = [_read(p) for p in sorted((run_dir / "pieces").glob("*.json"))]
    pieces = [p for p in pieces if isinstance(p, dict)]
    if not pieces:
        return None
    from . import graphics_hooks
    graphics_hooks.qc_request({"pieces": pieces}, run_dir, run_dir)
    return graphics_hooks.QC_REQUEST_REL


def drive(run_dir: Path, *, runner: Runner = default_runner, provider: str = "stub",
          allow_paid: bool = False, layout_approval_file: Optional[Path] = None,
          repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """Drive every page run under ``run_dir``. Writes and returns the report."""
    run_dir = Path(run_dir)
    scripts = scripts_dir(repo_root)
    runs = discover_page_runs(run_dir)
    # Written before the pages move, so the SOP-GIP-02 reviewer has the request in hand when
    # the map stage stops for a missing review (it lists the logo too, once the brand file exists).
    qc_request = _write_qc_request(run_dir) if runs else None
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
            if stages.get("final-mockups") == "closed":  # the labeled final files exist now: list them in the piece
                entry["pieces_refreshed"] = refresh_pieces(run_dir, run)
            # The asset map carries the hosted URLs; an authored page still pointing at a local
            # file is rewritten to them here, before responsive-html closes.
            entry["pages_rewritten"] = rewrite_page_assets(run)
            asset_map = _read(run / IMAGE_MAP_REL)
            if isinstance(asset_map, dict):
                entry["image_map"] = {"qc_state": asset_map.get("qc_state"),
                                      "hosting_state": asset_map.get("hosting_state"),
                                      "missing": list(asset_map.get("missing") or []),
                                      "entries": len(asset_map.get("images") or [])}
            done = all(v == "closed" for v in stages.values())
            entry.update(status="complete" if done else (page.stop.status if page.stop else "blocked"),
                         stages=stages, reason=None if done else (page.stop.reason if page.stop else "a stage is still open"),
                         commands=page.log)
        pages.append(entry)
    complete = bool(pages) and all(p["status"] == "complete" for p in pages)
    report = {"schema": SCHEMA, "run_dir": str(run_dir.resolve()), "stages": list(STAGES),
              "first_checkpoint": "layout proofs", "layout_proof_approval": (approval or {}).get("approval_ref"),
              "provider": provider, "pages": pages, "complete": complete,
              "qc_request": qc_request}
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
