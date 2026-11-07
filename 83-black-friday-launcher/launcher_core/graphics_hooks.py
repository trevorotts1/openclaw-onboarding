"""Graphics department hooks for the launch package (SOP-GIP-02 image QC, SOP-GIP-03 delivery).

The launch's wireframes and mockups are AI-generated images that go to a client, so the Graphics
department's two procedures apply to them:

* ``qc_request`` writes the SOP-GIP-02 request: every image in the package, the AF-G1..AF-G8
  automatic-fail battery (read from Skill 71's stage contract, never retyped here), the pass bar,
  the independence rule (the reviewer is never the model that wrote the prompt) and the exact
  Review Receipt v2 item each image needs.
* ``qc_report`` is the one producer of ``qc/image_qc_report.json``. It never scores an image
  itself: it reads the Review Receipt v2 files Skill 71's ``write_review.py`` wrote, binds each
  one to the image's real SHA-256 and to the reviewer/author identities recorded in that receipt,
  and copies the receipt's own scores. An image with no receipt is left out of the report; a
  receipt made for different bytes is stale. A hand-typed score, a request file or a report
  without a receipt behind it is never a review.
* ``report_violations`` is the check side of SOP-GIP-02: every image needs a report record that
  resolves to a live Review Receipt v2 whose bytes still hash and whose artifact hash is the
  image's, with an independent reviewer and a different reviewer model. A record without that
  receipt fails by name.
* ``delivery_record`` writes the SOP-GIP-03 record: for each image, whether it passed QC and
  whether a live hosted link exists. It NEVER publishes and never uploads by itself. When no live
  link exists it records the missing capability by name, so the delivery report says "waiting for
  an approved hosting step" instead of implying the client can open a link.

Hosting itself belongs to ``45-design-intelligence-library/scripts/graphics_ghl_push.py`` (which
uses the shared GHL media module behind its own approval). ``host_assets`` is the only caller of
that script here: it runs only when the caller passes an explicit approval reference, records the
script's real result, and ``apply_hosted_urls`` then puts the real public URLs into the package's
artifact records and page HTML. With no approval nothing is uploaded and the record says so.

``handle_handoff`` is the orchestration seam ``cli.cmd_assemble`` calls after
``package.assemble``: request, report from real receipts, optional approved hosting, page URL
replacement, then the delivery record. It is also the producer of the F09 brand asset path
(``brand_asset``): the client's brand answer becomes a brief and, only with the paid approval and
a working image capability, a real logo file carried into the brand file every page reads.

No credential is read, printed or returned. Capability is probed only when the caller passes an
explicit environment mapping.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .constants import REPO_ROOT, resolve_ref
from . import page_designs

PASS_AVERAGE = 8.5
QC_REPORT_REL = "qc/image_qc_report.json"
QC_REQUEST_REL = "qc/image_qc_request.json"
DELIVERY_REL = "delivery_record.json"
LEDGER_REL = "media_library.json"
PIPELINE_REL = "qc/graphics_pipeline.json"
GHL_MEDIA_REF = "06-ghl-install-pages/tools/ghl_media.py"
PUSH_REF = "45-design-intelligence-library/scripts/graphics_ghl_push.py"
REVIEW_PRODUCER_REF = "71-blackceo-signature-page/scripts/write_review.py"
STAGE_CONTRACT_REF = "71-blackceo-signature-page/references/stage-contract.json"
ADAPTER_REF = "74-kie-live-adapter/scripts/kie_live_adapter.py"
STAGES_REPORT_REL = "qc/image_stages_report.json"
REVIEWS_REL = Path("private") / "reviews"
IMAGE_STAGE = "image-generation-qc"
QC_CODE = "AF-LAUNCH-IMAGE-QC"
UNKNOWN = "UNKNOWN"
_PAGE_SUFFIXES = (".html", ".htm", ".css", ".svg")
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _read(path: Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write(path: Path, doc: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _ref(rel: str, root: Optional[Path] = None) -> Optional[Path]:
    """A repository path, trying the numbered tree then the bare skill slug."""
    base = Path(root or REPO_ROOT)
    candidates: List[Path] = [base / rel]
    try:
        candidates.insert(0, resolve_ref(rel, base))
    except (LookupError, OSError):
        pass
    for candidate in candidates:
        try:
            if Path(candidate).is_file():
                return Path(candidate)
        except (OSError, ValueError):
            continue
    first, _, rest = rel.partition("/")
    slug = first.split("-", 1)[1] if "-" in first and first.split("-", 1)[0].isdigit() else first
    bare = base / slug / rest
    return bare if bare.is_file() else None


# --------------------------------------------------------------------------- SOP-GIP-02 request

def autofail_battery(root: Optional[Path] = None) -> List[Dict[str, str]]:
    """AF-G1..AF-G8 as Skill 71's stage contract lists them. Empty when the contract has none."""
    try:
        doc = json.loads(resolve_ref(STAGE_CONTRACT_REF, root or REPO_ROOT).read_text(encoding="utf-8"))
    except (OSError, ValueError, LookupError):
        return []
    return [{"code": r["code"], "name": r.get("name", "")} for r in doc.get("graphics_autofails") or []
            if isinstance(r, dict) and r.get("code")]


def collect_images(manifest: Dict[str, Any], package_root: Path) -> List[Dict[str, Any]]:
    """Every PNG design image in the package (section images and boards), with its page identity."""
    package_root = Path(package_root)
    out: List[Dict[str, Any]] = []
    for piece in manifest.get("pieces") or []:
        for art in piece.get("artifacts") or []:
            path = str(art.get("path") or "")
            kind = page_designs.classify(path, art.get("kind"))
            full = package_root / path
            if kind and path.lower().endswith(".png") and full.is_file():
                out.append({"asset_id": Path(path).stem, "local_path": str(full), "page": page_designs.page_key(piece),
                            "kind": kind, "sha256": _sha(full),
                            "provider": art.get("provider") or piece.get("image_provider")})
    return out


def review_producer_command(item_id: str, artifact_rel: str, package_root: Path) -> List[str]:
    """The exact existing producer a reviewer runs. It is the ONLY way a Review Receipt v2 exists.
    The reviewer session is stamped from OPENCLAW_SESSION_ID / CLAUDE_CODE_SESSION_ID /
    CLAUDE_SESSION_ID by that producer; it is never passed in."""
    return [sys.executable, "scripts/write_review.py", str(Path(package_root).resolve()), IMAGE_STAGE, item_id,
            "--artifact", artifact_rel, "--scores", '<criterion -> {"score", "note"}>',
            "--verdict", "pass|fail", "--performed-check", "<what the reviewer actually did>",
            "--next-current-artifact", artifact_rel,
            "--author-session", "<prompt author session>", "--author-model", "<prompt author model>",
            "--reviewer-model", "<reviewer model>"]


def qc_request(manifest: Dict[str, Any], package_root: Path, job_dir: Path,
               author_models: Optional[Dict[str, str]] = None,
               repo_root: Optional[Path] = None,
               author_identities: Optional[Dict[str, Dict[str, str]]] = None) -> Dict[str, Any]:
    """Write <job>/qc/image_qc_request.json. A request, not a verdict: nothing here claims QC passed."""
    package_root = Path(package_root)
    images = collect_images(manifest, package_root)
    identities = author_identities or {}
    for img in images:
        identity = identities.get(img["asset_id"]) or identities.get(str(Path(img["local_path"]).name)) or {}
        img["prompt_author_model"] = (_text(identity.get("model")) or _text((author_models or {}).get(img["asset_id"]))
                                      or UNKNOWN)
        img["prompt_author_session"] = _text(identity.get("session")) or UNKNOWN
        rel = str(Path(img["local_path"]).resolve().relative_to(package_root.resolve())) \
            if Path(img["local_path"]).resolve().is_relative_to(package_root.resolve()) else img["local_path"]
        img["review_item_id"] = img["asset_id"]
        img["review_receipt_rel"] = f"private/reviews/{IMAGE_STAGE}/{img['asset_id']}.review.json"
        img["review_producer"] = review_producer_command(img["asset_id"], rel, package_root)
    requested = {
        "procedure": "SOP-GIP-02",
        "scope": "every AI-generated image in this launch package leaves the department to a client: 100 percent coverage",
        "pass_bar": {"average_at_least": PASS_AVERAGE, "automatic_failures": 0},
        "automatic_fail_battery": autofail_battery(repo_root),
        "reviewer_rule": ("the reviewing model must differ from the model that wrote the image's prompt; "
                          "an unknown prompt-author model counts as NOT independent (write_review.py "
                          "--author-model / --reviewer-model)"),
        "vision_read": "mandatory: a real multimodal read of every image, never graded from file names or prompts",
        "review_producer": REVIEW_PRODUCER_REF,
        "review_record": (f"{REVIEWS_REL.as_posix()}/{IMAGE_STAGE}/<item-id>.review.json (Review Receipt v2; "
                          "artifact_sha256 is computed by the producer from the file on disk)"),
        "expected_report": QC_REPORT_REL,
        "report_record_shape": ["local_path", "asset_id", "average", "pass", "triggered_autofails",
                                "review_ref", "review_sha256", "review_state"],
        "assets": images,
    }
    _write(Path(job_dir) / QC_REQUEST_REL, requested)
    return requested


# --------------------------------------------------------------------------- Review Receipt v2

def _number(value: Any) -> Optional[float]:
    """A real finite number (never a bool, never NaN), else None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
        return None
    return float(value)


def _mean(criteria: Any) -> Optional[float]:
    """The mean of the receipt's own per-criterion scores. No criterion, no average."""
    if not isinstance(criteria, dict):
        return None
    scores = [s for s in (_number((v or {}).get("score")) for v in criteria.values()
                          if isinstance(v, dict)) if s is not None]
    if not scores or len(scores) != len(criteria):
        return None
    return round(sum(scores) / len(scores), 2)


def review_roots(job_dir: Path, extra: Iterable[Path] = ()) -> List[Path]:
    """Where Review Receipt v2 files are looked for: the job, the dispatch run, the page runs and
    any caller-named root. Never a filesystem-wide search."""
    roots: List[Path] = []
    for cand in [Path(job_dir), *[Path(p) for p in extra if p]]:
        try:
            resolved = cand.resolve()
        except OSError:
            continue
        if resolved.is_dir() and resolved not in roots:
            roots.append(resolved)
    report = _read(Path(job_dir) / STAGES_REPORT_REL) or {}
    for page in (report.get("pages") or []) if isinstance(report, dict) else []:
        run = page.get("run_dir") if isinstance(page, dict) else None
        if isinstance(run, str) and run:
            try:
                resolved = Path(run).resolve()
            except OSError:
                continue
            if resolved.is_dir() and resolved not in roots:
                roots.append(resolved)
    return roots


def review_records(roots: Iterable[Path]) -> List[Dict[str, Any]]:
    """Every readable Review Receipt v2 under <root>/private/reviews/<stage>/, with its own hash."""
    out: List[Dict[str, Any]] = []
    seen = set()
    for root in roots:
        base = Path(root) / REVIEWS_REL
        if not base.is_dir():
            continue
        for path in sorted(base.glob("*/*.review.json")):
            try:
                resolved = path.resolve()
            except OSError:
                continue
            if resolved in seen:
                continue
            seen.add(resolved)
            doc = _read(path)
            if isinstance(doc, dict):
                out.append({"path": path, "sha256": _sha(path), "root": Path(root), "record": doc})
    return out


def _record_path(rec: Dict[str, Any], root: Path, image_path: str) -> bool:
    artifact = _text(rec.get("artifact"))
    if not artifact:
        return False
    target = Path(artifact)
    try:
        if target.is_absolute():
            return target.resolve() == Path(image_path).resolve()
        return (Path(root) / target).resolve() == Path(image_path).resolve()
    except OSError:
        return False


def review_binding(asset: Dict[str, Any], records: List[Dict[str, Any]], job_dir: Path) -> Dict[str, Any]:
    """Bind one image to its own Review Receipt v2, or say precisely why it is not reviewed.

    Identity is the receipt's artifact SHA-256 (computed by the producer from the file) and the
    image's file name; a receipt for another file is never applied. ``stale`` means a receipt
    exists for this item but for different bytes: the asset changed after it was reviewed.
    """
    image = Path(asset["local_path"]).resolve()
    digest = asset["sha256"]
    matches = [r for r in records if str(r["record"].get("artifact_sha256") or "") == digest]
    if matches:
        def rank(entry: Dict[str, Any]) -> Tuple[int, str]:
            return (1 if _record_path(entry["record"], entry["root"], str(image)) else 0,
                    str(entry["record"].get("reviewed_at") or ""))
        matches.sort(key=rank)
        entry = matches[-1]
        rec = entry["record"]
        binding = {
            "review_path": str(entry["path"].resolve()),
            "review_sha256": entry["sha256"],
            "artifact_sha256": str(rec.get("artifact_sha256") or ""),
            "verdict": rec.get("verdict"),
            "automatic_failures": list(rec.get("automatic_failures") or []),
            "specific_defects": list(rec.get("specific_defects") or []),
            "author_session": _text(rec.get("author_session")) or UNKNOWN,
            "reviewer_session": _text(rec.get("reviewer_session")) or UNKNOWN,
            "author_model": _text(rec.get("author_model")) or UNKNOWN,
            "reviewer_model": _text(rec.get("reviewer_model")) or UNKNOWN,
            "model_independence": _text(rec.get("model_independence")) or "unknown",
            "independent_review": rec.get("independent_review") is True,
            "average": _mean(rec.get("criteria")),
            "performed_check": _text(rec.get("performed_check")),
        }
        if binding["average"] is None:
            binding["state"] = "no_scores"
            binding["reason"] = "the review receipt carries no numeric score for every criterion"
        elif not binding["independent_review"] or binding["reviewer_session"] in ("", UNKNOWN) \
                or binding["reviewer_session"] == binding["author_session"]:
            binding["state"] = "not_independent"
            binding["reason"] = ("the reviewer is not a named session different from the prompt author "
                                 "(independent_review is false)")
        elif binding["model_independence"] != "independent" or binding["author_model"] == UNKNOWN \
                or binding["reviewer_model"] == UNKNOWN:
            binding["state"] = "model_not_independent"
            binding["reason"] = ("the reviewer model and the prompt-author model are not both named and "
                                 "different, so model independence is not proved")
        elif binding["verdict"] != "pass" or binding["automatic_failures"]:
            binding["state"] = "failed"
            binding["reason"] = "the review did not pass" + (
                f" (automatic failures {binding['automatic_failures']})" if binding["automatic_failures"] else "")
        else:
            binding["state"] = "verified"
            binding["reason"] = ""
        return binding
    name = image.name
    for entry in records:
        rec = entry["record"]
        artifact = _text(rec.get("artifact"))
        same = (_text(rec.get("item")) == asset["asset_id"]
                or (artifact and Path(artifact).name == name)
                or _record_path(rec, entry["root"], str(image)))
        if same:
            return {"state": "stale", "review_path": str(entry["path"].resolve()), "review_sha256": entry["sha256"],
                    "artifact_sha256": str(rec.get("artifact_sha256") or ""),
                    "reason": "the image changed after it was reviewed; the receipt is for different bytes"}
    return {"state": "missing", "reason": "no Review Receipt v2 names this image's SHA-256"}


def qc_report(manifest: Dict[str, Any], package_root: Path, job_dir: Path,
              roots: Optional[Iterable[Path]] = None,
              repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """Write <job>/qc/image_qc_report.json from real Review Receipt v2 files only.

    Only an image with a receipt has a record, and the record copies that receipt's own scores,
    verdict and identities. Everything else is listed under ``unreviewed`` with its reason, so a
    missing review is never silently turned into a number.
    """
    package_root, job_dir = Path(package_root), Path(job_dir)
    records = review_records(review_roots(job_dir, [package_root, *(roots or [])]))
    assets: List[Dict[str, Any]] = []
    unreviewed: List[Dict[str, Any]] = []
    for img in collect_images(manifest, package_root):
        binding = review_binding(img, records, job_dir)
        if binding["state"] == "missing":
            unreviewed.append({"asset_id": img["asset_id"], "page": img["page"], "sha256": img["sha256"],
                               "state": "missing", "reason": binding["reason"]})
            continue
        record = {
            "local_path": img["local_path"], "asset_id": img["asset_id"], "page": img["page"],
            "kind": img["kind"], "sha256": img["sha256"], "review_state": binding["state"],
            "average": binding.get("average"), "pass": binding["state"] == "verified",
            "triggered_autofails": list(binding.get("automatic_failures") or []),
            "verdict": binding.get("verdict"), "review_ref": binding.get("review_path"),
            "review_sha256": binding.get("review_sha256"),
            "author_session": binding.get("author_session"), "reviewer_session": binding.get("reviewer_session"),
            "author_model": binding.get("author_model"), "reviewer_model": binding.get("reviewer_model"),
            "model_independence": binding.get("model_independence"),
            "independent_review": binding.get("independent_review"),
            "reason": binding.get("reason", ""),
        }
        assets.append(record)
        if binding["state"] != "verified":
            unreviewed.append({"asset_id": img["asset_id"], "page": img["page"], "sha256": img["sha256"],
                               "state": binding["state"], "reason": binding.get("reason", "")})
    report = {
        "procedure": "SOP-GIP-02",
        "produced_by": "launcher_core.graphics_hooks.qc_report",
        "review_producer": REVIEW_PRODUCER_REF,
        "pass_bar": {"average_at_least": PASS_AVERAGE, "automatic_failures": 0},
        "automatic_fail_battery": autofail_battery(repo_root),
        "assets": assets,
        "unreviewed": unreviewed,
        "reviewed": sum(1 for a in assets if a["pass"]),
        "failed": sum(1 for a in assets if not a["pass"]),
    }
    _write(job_dir / QC_REPORT_REL, report)
    return report


def _same_file(recorded: Any, job_dir: Path, image_path: str) -> bool:
    try:
        path = Path(str(recorded))
        return (path if path.is_absolute() else job_dir / path).resolve() == Path(image_path).resolve()
    except (OSError, ValueError):
        return False


def _strict_review_problems(rec: Dict[str, Any], image_path: str, digest: str, job_dir: Path) -> List[str]:
    """Why a report record is not backed by a live Review Receipt v2, or nothing when it is."""
    ref = _text(rec.get("review_ref"))
    if not ref:
        return ["names no Review Receipt v2; a score typed into the report is not a review"]
    path = Path(ref) if Path(ref).is_absolute() else job_dir / ref
    if not path.is_file():
        return [f"names review receipt {ref!r} that does not exist"]
    recorded_hash = _text(rec.get("review_sha256"))
    if not recorded_hash or _sha(path) != recorded_hash:
        return [f"review receipt {path.name!r} does not match the hash the report recorded"]
    receipt = _read(path)
    if not isinstance(receipt, dict):
        return [f"review receipt {path.name!r} is not readable JSON"]
    problems: List[str] = []
    if str(receipt.get("artifact_sha256") or "") != digest:
        problems.append("its review receipt was written for different image bytes")
    if receipt.get("independent_review") is not True:
        problems.append("its reviewer is not recorded as independent")
    if _text(receipt.get("reviewer_session")) in ("", UNKNOWN) \
            or _text(receipt.get("author_session")) in ("", UNKNOWN) \
            or receipt.get("reviewer_session") == receipt.get("author_session"):
        problems.append("its reviewer and prompt author are not two named, different sessions")
    if _text(receipt.get("model_independence")) != "independent" \
            or _text(receipt.get("author_model")) in ("", UNKNOWN) \
            or _text(receipt.get("reviewer_model")) in ("", UNKNOWN):
        problems.append("its reviewer model and prompt-author model are not both named and different")
    if receipt.get("verdict") != "pass" or receipt.get("automatic_failures"):
        problems.append("its review receipt did not pass with zero automatic failures")
    average = _mean(receipt.get("criteria"))
    if average is None:
        problems.append("its review receipt carries no numeric score for every criterion")
    elif _number(rec.get("average")) != average:
        problems.append(f"the recorded average {rec.get('average')!r} is not the review's {average}")
    if list(receipt.get("automatic_failures") or []) != list(rec.get("triggered_autofails") or []):
        problems.append("the recorded automatic failures are not the review's")
    return problems


def report_violations(manifest: Dict[str, Any], package_root: Path,
                      job_dir: Optional[Path] = None) -> List[str]:
    """SOP-GIP-02 at check time: ``qc/image_qc_report.json`` must exist and cover 100 percent of the
    package's images, each with a real average of at least PASS_AVERAGE, ``pass`` true, no automatic
    failure, and a live Review Receipt v2 bound to the image's own bytes and to a reviewer who is a
    different named session and model from the prompt author. A missing report, a missing image, a
    low or non-numeric average, a changed file and a record with no receipt each fail by name. An
    empty list passes."""
    package_root = Path(package_root)
    job_dir = Path(job_dir) if job_dir else package_root
    report = _read(job_dir / QC_REPORT_REL)
    if not isinstance(report, dict) or not isinstance(report.get("assets"), list):
        return [f"{QC_CODE}: {QC_REPORT_REL} is missing or unreadable; every image in the package needs "
                "an independent review before it is delivered (SOP-GIP-02)"]
    images = collect_images(manifest, package_root)
    if not images:
        return [f"{QC_CODE}: the package holds no design image to review"]
    records = [r for r in report["assets"] if isinstance(r, dict)]
    fails: List[str] = []
    for img in images:
        name = Path(img["local_path"]).name
        found = [r for r in records if _same_file(r.get("local_path"), job_dir, img["local_path"])]
        if not found:
            fails.append(f"{QC_CODE}: {img['page']} {name} has no record in {QC_REPORT_REL} (100 percent coverage)")
            continue
        for rec in found:
            average = _number(rec.get("average"))
            autofails = rec.get("triggered_autofails")
            if average is None:
                fails.append(f"{QC_CODE}: {img['page']} {name} has no numeric average")
            elif average < PASS_AVERAGE:
                fails.append(f"{QC_CODE}: {img['page']} {name} averages {average}, under the {PASS_AVERAGE} bar")
            if not isinstance(autofails, list):
                fails.append(f"{QC_CODE}: {img['page']} {name} does not list its triggered_autofails")
            elif autofails:
                fails.append(f"{QC_CODE}: {img['page']} {name} has automatic failure(s) "
                             f"{', '.join(str(a) for a in autofails)}")
            if rec.get("pass") is not True:
                fails.append(f"{QC_CODE}: {img['page']} {name} is not recorded as passed")
            if rec.get("sha256") not in (None, img["sha256"]):
                fails.append(f"{QC_CODE}: {img['page']} {name} changed after it was reviewed")
            for problem in _strict_review_problems(rec, img["local_path"], img["sha256"], job_dir):
                fails.append(f"{QC_CODE}: {img['page']} {name} {problem}")
    return fails


# --------------------------------------------------------------------------- SOP-GIP-03 hosting

def ghl_media_present(repo_root: Optional[Path] = None) -> bool:
    return _ref(GHL_MEDIA_REF, repo_root) is not None


def _load_module(name: str, path: Path):
    parent = str(Path(path).parent)
    added = parent not in sys.path
    if added:
        sys.path.insert(0, parent)
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"{path} cannot be imported")
        module = importlib.util.module_from_spec(spec)
        sys.modules.setdefault(name, module)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        return module
    finally:
        if added and parent in sys.path:
            sys.path.remove(parent)


def host_assets(package_root: Path, job_dir: Optional[Path] = None, approval_ref: Optional[str] = None,
                folder_name: Optional[str] = None, repo_root: Optional[Path] = None,
                push=None) -> Dict[str, Any]:
    """Run the existing authorised uploader, or record honestly why nothing was hosted.

    Nothing is read, created or uploaded without an explicit ``approval_ref``; the uploader itself
    refuses a record that is not a live-publication approval for the client's location. Its real
    result is returned unchanged; no URL is ever composed here.
    """
    job_dir = Path(job_dir or package_root)
    if not _text(approval_ref):
        return {"state": "not_authorized",
                "reason": "no approved hosting approval_ref was supplied; hosting is its own approved step",
                "uploaded": []}
    if not (job_dir / QC_REPORT_REL).is_file():
        return {"state": "needs_qc", "reason": f"{QC_REPORT_REL} does not exist; only QC-passed assets are hosted",
                "uploaded": []}
    path = _ref(PUSH_REF, repo_root)
    if path is None:
        return {"state": "unavailable", "reason": f"{PUSH_REF} is not installed", "uploaded": []}
    try:
        module = _load_module("_launch_graphics_ghl_push", path)
        push = push or module.push_graphics_media
        result = push(job_dir, folder_name=folder_name, job_slug=job_dir.name, approval_ref=approval_ref)
    except Exception as exc:  # noqa: BLE001  (a refusal is a recorded capability gap, never printed secrets)
        state = "refused" if isinstance(exc, RuntimeError) else "failed"
        return {"state": state, "reason": f"{type(exc).__name__}: {str(exc)[:400]}", "uploaded": []}
    return {"state": "hosted", "reason": "", "folder_id": result.get("ghl_folder_id"),
            "folder_name": result.get("ghl_folder_name"),
            "upload_count": result.get("upload_count"), "uploaded": result.get("uploaded") or []}


def _live_ledger_entries(job_dir: Path) -> Dict[str, Dict[str, Any]]:
    """{sha256 of the local file: ledger entry} for uploads recorded complete and live. A URL is
    only used when the uploader recorded both a complete upload and a live GET of that URL."""
    ledger = _read(Path(job_dir) / LEDGER_REL) or {}
    out: Dict[str, Dict[str, Any]] = {}
    for entry in ledger.get("uploaded") or [] if isinstance(ledger, dict) else []:
        if not isinstance(entry, dict):
            continue
        url = _text(entry.get("public_url") or entry.get("ghl_public_url"))
        if entry.get("ghl_upload_status") != "complete" or not url.startswith("https://"):
            continue
        if (entry.get("liveness") or {}).get("live") is not True:
            continue
        local = _text(entry.get("local_path"))
        if local and Path(local).is_file():
            out[_sha(Path(local))] = entry
    return out


def _replace_page_references(path: Path, hosted: Dict[str, Dict[str, Any]],
                             artifacts: Dict[str, str]) -> List[Dict[str, str]]:
    """Replace local image references in one text page with the real hosted URL, and nothing else.
    Only an attribute/url shape is touched (``src="file"``, ``href='file'``, ``url(file)``, or the
    recorded local path itself); prose that happens to mention a file name is left alone. Returns
    the replacements made; the file is left untouched when none matched."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    original = text
    made: List[Dict[str, str]] = []
    for sha, entry in sorted(hosted.items()):
        url = _text(entry.get("public_url") or entry.get("ghl_public_url"))
        local = Path(_text(entry.get("local_path")))
        names = {local.name}
        if sha in artifacts:
            names.add(Path(artifacts[sha]).name)
        for name in sorted(n for n in names if n):
            for pattern, replacement in ((f'"{name}"', f'"{url}"'), (f"'{name}'", f"'{url}'"),
                                         (f"url({name})", f"url({url})"),
                                         (f"url('{name}')", f"url('{url}')"),
                                         (f'url("{name}")', f'url("{url}")')):
                if pattern in text:
                    text = text.replace(pattern, replacement)
                    made.append({"from": pattern, "to": url})
        for form in {str(local), str(local.resolve())}:
            if form and form in text:
                text = text.replace(form, url)
                made.append({"from": form, "to": url})
    if text != original:
        path.write_text(text, encoding="utf-8")
    return made


def apply_hosted_urls(manifest: Dict[str, Any], package_root: Path, job_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Put the real public URLs into the package: an artifact record gains ``hosted_url``; page HTML
    references to that image are replaced. A changed page's artifact hash (manifest and receipt) is
    updated for that file only, and the receipt is re-sealed over the manifest. With no live ledger
    entry nothing changes and the state says so."""
    package_root, job_dir = Path(package_root), Path(job_dir or package_root)
    hosted = _live_ledger_entries(job_dir)
    if not hosted:
        return {"state": "local_only", "replaced": [], "artifacts": 0,
                "reason": f"no complete, live upload is recorded in {LEDGER_REF_NAME}"}
    artifacts = {str(art.get("sha256")): str(art.get("path"))
                 for piece in manifest.get("pieces") or [] for art in piece.get("artifacts") or []}
    changed: Dict[str, Dict[str, Any]] = {}
    hosted_count = 0
    replaced: List[Dict[str, str]] = []
    for piece in manifest.get("pieces") or []:
        for art in piece.get("artifacts") or []:
            digest = str(art.get("sha256") or "")
            entry = hosted.get(digest)
            if entry:
                art["hosted_url"] = _text(entry.get("public_url") or entry.get("ghl_public_url"))
                art["hosted_file_id"] = _text(entry.get("ghl_media_id") or entry.get("file_id"))
                hosted_count += 1
            path = package_root / str(art.get("path") or "")
            if path.suffix.lower() in _PAGE_SUFFIXES and path.is_file():
                made = _replace_page_references(path, hosted, artifacts)
                if made:
                    replaced += [{"path": str(art["path"]), **item} for item in made]
                    changed[str(art["path"])] = {"sha256": _sha(path), "size": path.stat().st_size}
    if changed:
        for piece in manifest.get("pieces") or []:
            for art in piece.get("artifacts") or []:
                if str(art.get("path")) in changed:
                    art.update(changed[str(art["path"])])
    if changed or hosted_count:
        _write(package_root / "package-manifest.json", manifest)
        receipt_path = package_root / "receipt.json"
        receipt = _read(receipt_path)
        if isinstance(receipt, dict):
            for row in receipt.get("units") or []:
                for art in (row.get("artifacts") or []) if isinstance(row, dict) else []:
                    path = str(art.get("path") or "") if isinstance(art, dict) else ""
                    if path in changed:
                        art.update(changed[path])
            receipt.setdefault("manifest", {})["sha256"] = _sha(package_root / "package-manifest.json")
            _write(receipt_path, receipt)
    return {"state": "hosted_urls_applied" if hosted_count else "local_only",
            "artifacts": hosted_count, "replaced": replaced,
            "pages_updated": sorted(changed), "reason": ""}


LEDGER_REF_NAME = LEDGER_REL


# --------------------------------------------------------------------------- delivery record

def delivery_record(manifest: Dict[str, Any], package_root: Path, job_dir: Path,
                    probe_env: Optional[Dict[str, str]] = None,
                    repo_root: Optional[Path] = None,
                    hosting: Optional[Dict[str, Any]] = None,
                    rewrite: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Write <job>/delivery_record.json (SOP-GIP-03). Records; never uploads, never publishes."""
    job_dir = Path(job_dir)
    report = _read(job_dir / QC_REPORT_REL) or {}
    qc = {str(a.get("local_path")): a for a in (report.get("assets") or []) if isinstance(a, dict)}
    ledger = _read(job_dir / LEDGER_REL) or {}
    hosted = {str(e.get("local_path")): e for e in (ledger.get("uploaded") or []) if isinstance(e, dict)}

    assets: List[Dict[str, Any]] = []
    for img in collect_images(manifest, package_root):
        verdict = qc.get(img["local_path"])
        if verdict is None:
            qc_state = "not_reviewed"
        else:
            clean = verdict.get("pass") is True and verdict.get("review_state") == "verified" \
                and not (verdict.get("triggered_autofails") or [])
            qc_state = "qc_passed" if clean else "qc_failed"
        entry = hosted.get(img["local_path"])
        live = bool(entry and entry.get("ghl_upload_status") == "complete"
                    and (entry.get("liveness") or {}).get("live") is True)
        assets.append({"asset_id": img["asset_id"], "page": img["page"], "kind": img["kind"],
                       "local_path": img["local_path"], "sha256": img["sha256"], "qc": qc_state,
                       "review_state": (verdict or {}).get("review_state"),
                       "review_ref": (verdict or {}).get("review_ref"),
                       "reviewer_session": (verdict or {}).get("reviewer_session"),
                       "hosted": live, "public_url": entry.get("public_url") if live else None})

    missing: List[str] = []
    module_ok = ghl_media_present(repo_root)
    if not module_ok:
        missing.append(f"the shared hosting module ({GHL_MEDIA_REF}) is not installed")
    elif probe_env is not None:
        try:
            module = _load_module("_launch_ghl_media", _ref(GHL_MEDIA_REF, repo_root))
            module.resolve_location_pit(probe_env, search_stores=False)
        except Exception:  # noqa: BLE001  (a missing credential is a recorded capability gap, never printed)
            missing.append("the client's hosting credentials are not available to this run")
    if not assets or not all(a["hosted"] for a in assets):
        missing.append("no live hosted link is recorded for every image; hosting is a separate approved step")

    state = ("hosted_links_recorded" if assets and all(a["hosted"] for a in assets)
             else "local_only_missing_capability")
    record = {
        "procedure": "SOP-GIP-03",
        "published": False,
        "publishing_performed_by_this_record": "never",
        "delivery_state": state,
        "missing_capability": missing if state != "hosted_links_recorded" else [],
        "qc_summary": {s: sum(1 for a in assets if a["qc"] == s)
                       for s in ("qc_passed", "qc_failed", "not_reviewed")},
        "hosting": hosting or {"state": "not_attempted",
                               "reason": "no hosting step was run for this package"},
        "page_references": rewrite or {"state": "not_run"},
        "assets": assets,
    }
    _write(job_dir / DELIVERY_REL, record)
    return record


# --------------------------------------------------------------------------- orchestration seam

def prompt_authors(manifest: Dict[str, Any], package_root: Path,
                   roots: Iterable[Path]) -> Dict[str, Dict[str, str]]:
    """{image asset_id: {"session", "model"}} from each page run's own prompt-stage receipt. A
    receipt that names no model leaves the model unknown; nothing is inferred from a file name."""
    images = collect_images(manifest, package_root)
    out: Dict[str, Dict[str, str]] = {}
    for root in roots:
        root = Path(root)
        receipts = root / "private" / "receipts"
        if not receipts.is_dir():
            continue
        identity = {"session": "", "model": ""}
        for name in ("image-inventory-prompts", IMAGE_STAGE):
            doc = _read(receipts / f"{name}.json")
            if isinstance(doc, dict):
                identity["session"] = identity["session"] or _text(doc.get("author_session")) \
                    or _text(doc.get("author_agent"))
                identity["model"] = identity["model"] or _text(doc.get("author_model")) \
                    or _text(doc.get("model"))
        for img in images:
            try:
                inside = Path(img["local_path"]).resolve().is_relative_to(root.resolve())
            except OSError:
                inside = False
            if inside and (identity["session"] or identity["model"]):
                out.setdefault(img["asset_id"], dict(identity))
    return out


def handle_handoff(manifest: Dict[str, Any], package_root: Path, job_dir: Optional[Path] = None,
                   dispatch_root: Optional[Path] = None, review_roots_extra: Iterable[Path] = (),
                   host_approval_ref: Optional[str] = None, folder_name: Optional[str] = None,
                   probe_env: Optional[Dict[str, str]] = None,
                   repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """The real assemble-time handoff: SOP-GIP-02 request + report, approved hosting, page URL
    replacement, SOP-GIP-03 record, and one machine-readable summary at qc/graphics_pipeline.json."""
    package_root = Path(package_root)
    job_dir = Path(job_dir or package_root)
    roots = [job_dir, package_root, *([Path(dispatch_root)] if dispatch_root else []),
             *[Path(p) for p in review_roots_extra if p]]
    identities = prompt_authors(manifest, package_root, roots)
    request = qc_request(manifest, package_root, job_dir, author_identities=identities, repo_root=repo_root)
    report = qc_report(manifest, package_root, job_dir, roots=roots, repo_root=repo_root)
    hosting = host_assets(package_root, job_dir, approval_ref=host_approval_ref,
                          folder_name=folder_name, repo_root=repo_root)
    # Idempotent: a live ledger from an earlier approved upload is applied too; with no live entry
    # nothing changes and local references stay.
    rewrite = apply_hosted_urls(manifest, package_root, job_dir)
    delivery = delivery_record(manifest, package_root, job_dir, probe_env=probe_env, repo_root=repo_root,
                               hosting=hosting, rewrite=rewrite)
    pipeline = {
        "qc_request": {"path": QC_REQUEST_REL, "assets": len(request.get("assets") or [])},
        "qc_report": {"path": QC_REPORT_REL, "reviewed": report.get("reviewed"),
                      "failed": report.get("failed"), "unreviewed": len(report.get("unreviewed") or [])},
        "review_violations": report_violations(manifest, package_root, job_dir),
        "hosting": hosting,
        "page_references": rewrite,
        "delivery": {"path": DELIVERY_REL, "state": delivery.get("delivery_state"),
                     "qc_summary": delivery.get("qc_summary")},
    }
    _write(job_dir / PIPELINE_REL, pipeline)
    return pipeline


# --------------------------------------------------------------------------- F09 brand asset

BRAND_MODES = {
    "file": "existing_logo", "logo": "existing_logo", "send": "existing_logo", "existing": "existing_logo",
    "i will send it": "existing_logo", "send a file": "existing_logo",
    "wordmark": "wordmark", "text": "wordmark", "name": "wordmark", "business name": "wordmark",
    "use my business name as text": "wordmark",
    "create": "create", "new": "create", "new_logo": "create", "create a new logo": "create",
    "not sure": "wordmark",
}
BRAND_FALLBACK_ORDER = ("existing_logo", "wordmark", "create")


def _answer_value(answers: Any, key: str) -> Any:
    """The raw value of one shared answer, whatever form the answers file records it in."""
    if not isinstance(answers, dict):
        return None
    entry = answers.get(key)
    if isinstance(entry, dict):
        return entry.get("value")
    return entry


def brand_answer(doc: Any) -> Dict[str, Any]:
    """The client's brand answer from the shared answers file, in a shape this producer reads.

    W05 owns the question. This reader accepts the answer's value as an object
    ({mode|choice, path|file, text|wordmark, brief}) or the plain choice text, and keeps the
    answer's own status. A missing answer is a missing answer, never a guessed one.
    """
    answers = (doc or {}).get("answers") if isinstance(doc, dict) else {}
    entry = None
    for key in ("logo", "brand_logo", "logo_choice", "brand_mark"):
        candidate = (answers or {}).get(key) if isinstance(answers, dict) else None
        if candidate:
            entry = candidate
            break
    entry = entry if isinstance(entry, dict) else {}
    value = entry.get("value")
    mode = path = text = ""
    if isinstance(value, dict):
        mode = _text(value.get("mode") or value.get("choice") or value.get("kind"))
        path = _text(value.get("path") or value.get("file"))
        text = _text(value.get("text") or value.get("wordmark") or value.get("brief"))
    elif isinstance(value, str):
        mode = value
    key = " ".join(mode.lower().replace("_", " ").replace("-", " ").split())
    resolved = BRAND_MODES.get(key, "")
    if not resolved and isinstance(value, str):
        for needle, name in BRAND_MODES.items():
            if needle in key:
                resolved = name
                break
    business = _answer_value(answers, "business_name")
    return {"mode": resolved, "path": path, "text": text,
            "business_name": _text(business), "status": _text(entry.get("status")) or "unknown",
            "found": bool(entry)}


def brand_brief(answer: Dict[str, Any], palette_roles: Optional[Dict[str, Any]] = None,
                design_style: Optional[str] = None, audience: Optional[str] = None,
                voice: Optional[str] = None) -> Dict[str, Any]:
    """The logo brief. Every line is drawn from a recorded client answer; a missing value is
    omitted, never invented."""
    name = answer.get("business_name")
    lines = [f"Logo for {name}." if name else "Logo for the client's business.",
             "A clean, timeless mark that reads at small sizes and in one colour."]
    if palette_roles:
        listed = "; ".join(f"{k} {', '.join(v) if isinstance(v, list) else v}"
                           for k, v in palette_roles.items())
        lines.append(f"Use only the client's own brand colours: {listed}.")
    if design_style:
        lines.append(f"Design style {design_style} (the look used on every page of this launch).")
    if audience:
        lines.append(f"The audience: {audience}.")
    if voice:
        lines.append(f"Brand voice: {voice}.")
    lines.append("No text other than the business name. No other client's marks or likeness.")
    return {"business_name": name or None, "palette_roles": palette_roles or {},
            "design_style": design_style or None, "audience": audience or None, "voice": voice or None,
            "prompt": " ".join(lines)}


def _brand_file(path: Optional[Path], job_dir: Path) -> Optional[Path]:
    for cand in ([Path(path)] if path else []) + [job_dir / "private" / "brand.json",
                                                  job_dir / "brand" / "client-brand.json"]:
        if cand and Path(cand).is_file():
            return Path(cand)
    return None


def _record_logo(brand_path: Optional[Path], mode: str, value: str, extra: Optional[Dict[str, Any]] = None) -> bool:
    """Put the finished logo into the brand file every page prompt reads. A client's brand file is
    only ever updated in place; one that does not exist is not created by guesswork."""
    if brand_path is None:
        return False
    brand = _read(brand_path)
    if not isinstance(brand, dict):
        return False
    logo = brand.get("logo") if isinstance(brand.get("logo"), dict) else {}
    if mode == "existing_logo":
        logo.update({"files": value, "masthead_files": value, "status": "provided"})
    elif mode == "wordmark":
        logo.update({"files": "CLIENT_MUST_SUPPLY", "masthead_files": "CLIENT_MUST_SUPPLY",
                     "wordmark_text": value, "status": "provided" if value else "default_to_confirm"})
    else:
        logo.update({"files": value, "masthead_files": value, "status": "provided"})
    logo.update(extra or {})
    brand["logo"] = logo
    _write(brand_path, brand)
    return True


def brand_asset(answers_path: Path, job_dir: Path, brand_file: Optional[Path] = None,
                allow_paid: bool = False, approval_ref: Optional[str] = None,
                model_id: Optional[str] = None, repo_root: Optional[Path] = None,
                provider: str = "kie") -> Dict[str, Any]:
    """Carry the client's brand answer to the asset producer.

    * existing logo: the supplied file is recorded; a missing file is a named missing input.
    * wordmark: the business name is recorded as the text logo.
    * create: a brief is always written; the real image capability runs only with ``allow_paid``,
      an approved reference and a model id. Otherwise the record says exactly what is missing and
      nothing is spent or invented.
    """
    job_dir = Path(job_dir)
    doc = _read(answers_path)
    if not isinstance(doc, dict) or doc.get("schema") != "client-intake-answers/v1":
        return {"state": "refused", "reason": f"{answers_path} is not a client-intake-answers/v1 file"}
    answer = brand_answer(doc)
    if not answer["found"] or not answer["mode"]:
        return {"state": "needs_answer",
                "reason": "the answers file carries no usable logo answer; ask the client (existing logo, "
                          "name wordmark, or create a new logo)"}
    brand_path = _brand_file(brand_file, job_dir)
    intent = {"mode": answer["mode"], "business_name": answer["business_name"],
              "status": answer["status"], "brand_file": str(brand_path) if brand_path else None}
    if answer["mode"] == "existing_logo":
        logo_path = Path(answer["path"]) if answer["path"] else None
        if logo_path is None or not logo_path.is_file():
            return {"state": "missing_logo_file", "intent": intent,
                    "reason": "the client chose their existing logo but no readable logo file is recorded"}
        recorded = _record_logo(brand_path, "existing_logo", str(logo_path.resolve()))
        return {"state": "recorded", "intent": intent, "file": str(logo_path.resolve()),
                "brand_file_updated": recorded}
    if answer["mode"] == "wordmark":
        name = answer["business_name"] or answer["text"]
        if not name:
            return {"state": "needs_business_name", "intent": intent,
                    "reason": "the wordmark needs the business name; the answers file names none"}
        recorded = _record_logo(brand_path, "wordmark", name)
        return {"state": "recorded", "intent": intent, "wordmark_text": name,
                "brand_file_updated": recorded}
    # create: the brief is deterministic and always written first
    brand = _read(brand_path) if brand_path else None
    palette = (brand or {}).get("palette_roles") if isinstance(brand, dict) else None
    answers = doc.get("answers") or {}
    brief = brand_brief(answer, palette,
                        design_style=_text(_answer_value(answers, "design_style")),
                        audience=_text(_answer_value(answers, "audience")),
                        voice=_text(_answer_value(answers, "voice")))
    brief_path = job_dir / "brand" / "logo-brief.json"
    prompt_path = job_dir / "brand" / "logo-prompt.txt"
    _write(brief_path, brief)
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(brief["prompt"] + "\n", encoding="utf-8")
    result: Dict[str, Any] = {"state": "brief_ready", "intent": intent,
                              "brief": str(brief_path), "prompt": str(prompt_path),
                              "brand_file_updated": False, "missing_capability": []}
    adapter = _ref(ADAPTER_REF, repo_root)
    if not allow_paid:
        result["missing_capability"].append("creating the logo spends money; it needs the client's approved "
                                            "spend record (nothing was sent and nothing was spent)")
        return result
    if not _text(approval_ref):
        result["missing_capability"].append("creating the logo needs an approved paid-render reference")
        return result
    if not _text(model_id):
        result["missing_capability"].append("no image model id was supplied from the existing registry")
        return result
    if adapter is None:
        result["missing_capability"].append(f"the image adapter ({ADAPTER_REF}) is not installed")
        return result
    if not os.environ.get("KIE_API_KEY"):
        result["missing_capability"].append("KIE_API_KEY is not set in this environment")
        return result
    request = {"model": model_id, "input": {"prompt": brief["prompt"], "input_urls": [],
                                            "aspect_ratio": "1:1"}}
    request_path = job_dir / "brand" / "logo-request.json"
    _write(request_path, request)
    save_dir = job_dir / "brand" / "logo"
    save_dir.mkdir(parents=True, exist_ok=True)
    try:
        done = subprocess.run([sys.executable, str(adapter), "run", "--request", str(request_path),
                               "--save-dir", str(save_dir), "--mode", "active"],
                              capture_output=True, text=True, timeout=600)
        payload = {}
        for candidate in (done.stdout.strip(), (done.stdout.strip().splitlines() or [""])[-1]):
            try:
                value = json.loads(candidate)
            except ValueError:
                continue
            if isinstance(value, dict):
                payload = value
                break
    except (OSError, subprocess.SubprocessError) as exc:
        result.update(state="failed", reason=f"{type(exc).__name__}: {exc}")
        return result
    if payload.get("state") != "success" or not payload.get("saved_paths"):
        error = (payload.get("error") or {}).get("msg") if isinstance(payload.get("error"), dict) else None
        result.update(state="failed", reason=str(error or done.stderr or "the adapter returned no saved file")[:400])
        return result
    source = Path(payload["saved_paths"][0])
    if not source.is_file() or source.read_bytes()[:8] != _PNG_MAGIC:
        result.update(state="failed", reason="the adapter reported a file that is absent or not a PNG")
        return result
    final = save_dir / "logo.png"
    final.write_bytes(source.read_bytes())
    asset = {"file": str(final.resolve()), "sha256": _sha(final), "task_id": payload.get("task_id"),
             "model_id": model_id, "provider": provider, "mode": "active",
             "prompt": str(prompt_path), "brief": str(brief_path), "approval_ref": approval_ref,
             "created_at": payload.get("created_at")}
    _write(job_dir / "brand" / "logo-asset.json", asset)
    result.update(state="created", file=asset["file"], sha256=asset["sha256"],
                  brand_file_updated=_record_logo(brand_path, "create", asset["file"], {"sha256": asset["sha256"]}),
                  asset=str(job_dir / "brand" / "logo-asset.json"))
    return result


def revise_asset(page_run: Path, item_id: str, defects: Iterable[str], provider: str = "kie",
                 allow_paid: bool = False, repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """Correct ONE generated image in ONE page run, reusing Skill 71's own producer.

    The reviewer's concrete defects are appended to that item's prompt file (the focused repair),
    and only that item is redrawn with ``stage_executor.py --item``. No other item, page or launch
    stage is reopened. The caller re-reviews that asset; its old receipt is stale by hash.
    """
    page_run = Path(page_run)
    item = _text(item_id)
    names = [d.strip() for d in defects if isinstance(d, str) and d.strip()]
    if not item or not names:
        return {"state": "refused", "reason": "a page run, an image item id and at least one named defect are needed"}
    prompt = page_run / "image-inventory-prompts" / f"{item}.txt"
    if not prompt.is_file():
        return {"state": "needs_authoring", "reason": f"{prompt} does not exist; there is no prompt to repair"}
    scripts = _ref("71-blackceo-signature-page/scripts/stage_executor.py", repo_root)
    if scripts is None:
        return {"state": "unavailable", "reason": "stage_executor.py is not installed"}
    prompt.write_text(prompt.read_text(encoding="utf-8").rstrip()
                      + "\n\nFOCUSED REPAIR — correct these named defects, change nothing else:\n"
                      + "".join(f"- {d}\n" for d in names), encoding="utf-8")
    argv = [sys.executable, str(scripts), str(page_run), "--stage", IMAGE_STAGE, "--item", item,
            "--provider", provider] + (["--allow-paid"] if allow_paid else [])
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=3600)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"state": "failed", "reason": f"{type(exc).__name__}: {exc}", "prompt": str(prompt)}
    record = {"state": "regenerated" if done.returncode == 0 else "failed", "item": item,
              "page_run": str(page_run.resolve()), "prompt": str(prompt),
              "defects": names, "provider": provider, "allow_paid": bool(allow_paid),
              "exit_code": done.returncode,
              "output_tail": "\n".join(((done.stdout or "") + (done.stderr or "")).strip().splitlines()[-8:])}
    _write(page_run / "private" / "reviews" / IMAGE_STAGE / f"{item}.repair.json", record)
    return record
