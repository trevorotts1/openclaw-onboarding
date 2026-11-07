"""Graphics department hooks for the launch package (SOP-GIP-02 image QC, SOP-GIP-03 delivery).

The launch's wireframes and mockups are AI-generated images that go to a client, so the Graphics
department's two procedures apply to them:

* ``qc_request`` writes the SOP-GIP-02 request: every image in the package, the AF-G1..AF-G8
  automatic-fail battery (read from Skill 71's stage contract, never retyped here), the pass bar
  and the independence rule (the reviewer is never the model that wrote the prompt).
* ``report_violations`` is the check side of SOP-GIP-02: the package passes only when the expected
  report names every image with a real average at or above the bar and no automatic failure, and
  when each record is bound to a real review (``write_review.py``) of the same bytes by two named,
  different models. A hand-written average is not a review.
* ``delivery_record`` writes the SOP-GIP-03 record: for each image, whether it passed QC and
  whether a live hosted link exists. It NEVER publishes and never uploads. When no live link
  exists it records the missing capability by name, so the delivery report says "waiting for an
  approved hosting step" instead of implying the client can open a link.

The client's BRAND asset is part of this handoff, not a separate pipeline. When the client answers
"use my business name as text" (or sends nothing yet), Skill 71's ``brand_colors.record_from_answers``
sets that answer in type at ``brand/wordmark.png`` and the brand file names it as ``logo.files``;
``collect_images`` picks that file up, so the same request, the same review and the same upload that
carry the page photography also carry the logo. Its autofail battery is the subset that can apply to
a mark set in our own type (no generation receipt, no anatomy), named by code, never retyped.

Hosting itself belongs to ``45-design-intelligence-library/scripts/graphics_ghl_push.py`` (which uses
the shared GHL media module in Skill 06's tools) behind its own approval; ``host_assets`` is the one
door the launcher opens onto it (no approved record, no upload), and ``delivery_record`` only ever
reads the ledger that script writes (``media_library.json``).

No credential is read or printed. Capability is probed only when the caller passes an explicit
environment mapping.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .constants import REPO_ROOT, resolve_ref
from . import page_designs

PASS_AVERAGE = 8.5
QC_REPORT_REL = "qc/image_qc_report.json"
QC_REQUEST_REL = "qc/image_qc_request.json"
DELIVERY_REL = "delivery_record.json"
LEDGER_REL = "media_library.json"
GHL_MEDIA_REF = "06-ghl-install-pages/tools/ghl_media.py"
GRAPHICS_PUSH_REF = "45-design-intelligence-library/scripts/graphics_ghl_push.py"
STAGE_CONTRACT_REF = "71-blackceo-signature-page/references/stage-contract.json"
QC_CODE = "AF-LAUNCH-IMAGE-QC"
# The request and the report it names are written ONCE for the whole launch, in the launch run's
# qc/ folder (the request lists every page's images and its expected_report is the report beside
# it). A page run is nested inside that folder (<launch run>/dispatch/<page>), so every reader
# resolves the report through qc_report_root instead of assuming the folder it was handed is the
# one the request was written to.
QC_LAUNCH_MARKS = (QC_REPORT_REL, QC_REQUEST_REL)

# What an asset is, which decides which automatic fails can apply to it.
SCOPE_AI_IMAGE = "ai_image"        # drawn by the image service: the whole battery
SCOPE_BRAND_ASSET = "brand_asset"  # the client's mark, or their name set in our own type
BRAND_PAGE = "brand"
BRAND_LOGO_ID = "brand-logo"
# AF-G4 (anatomy), AF-G7 (skin tone) and AF-G8 (a KIE generation receipt) cannot apply to a
# mark that was not drawn by the image service; every other automatic fail can, and must.
AUTOFAILS_NOT_FOR_BRAND = ("AF-G4", "AF-G7", "AF-G8")


def autofail_battery(root: Optional[Path] = None) -> List[Dict[str, str]]:
    """AF-G1..AF-G8 as Skill 71's stage contract lists them. Empty when the contract has none."""
    try:
        doc = json.loads(resolve_ref(STAGE_CONTRACT_REF, root or REPO_ROOT).read_text(encoding="utf-8"))
    except (OSError, ValueError, LookupError):
        return []
    return [{"code": r["code"], "name": r.get("name", "")} for r in doc.get("graphics_autofails") or []
            if isinstance(r, dict) and r.get("code")]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def qc_report_root(run: Path) -> Path:
    """The folder that holds this run's SOP-GIP-02 request and report — the launch run folder.

    The review is written ONCE for the whole launch: ``qc_request`` lists every page's images
    under one ``expected_report``, and it is written into the launch run's folder. A page run is
    nested inside that folder (``<launch run>/dispatch/<page>``), so a page run's own ``qc/``
    folder is not where the report is. This resolves to the folder that really carries it, so the
    producer, the package gate and the image-map producer cannot disagree about which file they
    mean. The report itself is looked for first, then the request that names it; a page run driven
    on its own (no enclosing launch folder — the old flat layout) resolves to itself unchanged.
    """
    run = Path(run)
    for rel in QC_LAUNCH_MARKS:
        for folder in (run, *run.parents):
            if (folder / rel).is_file():
                return folder
    return run


def applicable_autofails(scope: str, root: Optional[Path] = None) -> List[Dict[str, str]]:
    """The automatic-fail battery that can apply to an asset of this scope.

    Read from the stage contract, then narrowed by code for a brand asset: a mark we set in
    type has no generation receipt and no anatomy, so those three codes cannot apply — the
    other five can, and still fail the asset outright."""
    battery = autofail_battery(root)
    if scope == SCOPE_BRAND_ASSET:
        return [r for r in battery if r["code"] not in AUTOFAILS_NOT_FOR_BRAND]
    return battery


def _brand_file_candidates(root: Path) -> List[Path]:
    """The brand files this run carries: the shared one, the intake's, then each page run's."""
    root = Path(root)
    out = [root / "brand" / "client-brand.json"]
    intake = _read(root / "intake.json")
    if isinstance(intake, dict) and intake.get("brand_file"):
        out.append(root / str(intake["brand_file"]))
    out.extend(sorted(root.glob("*/brand/client-brand.json")))
    return [p for p in dict.fromkeys(out) if p.is_file()]


def brand_logo_assets(root: Path) -> List[Dict[str, Any]]:
    """Every logo file the client's brand answer produced, as one SOP-GIP-02 asset.

    The answer is already a file by the time this runs: Skill 71's ``brand_colors`` keeps a
    logo the client handed over and sets a wordmark answer in our own type. A logo nobody
    produced therefore shows up as nothing here (never as a sentinel that passes review),
    and the same bytes seen in several page runs are listed once."""
    assets: List[Dict[str, Any]] = []
    seen = set()
    for brand_path in _brand_file_candidates(root):
        brand = _read(brand_path) or {}
        logo = brand.get("logo") if isinstance(brand, dict) else None
        if not isinstance(logo, dict):
            continue
        listed = logo.get("files") if isinstance(logo.get("files"), list) else [logo.get("files")]
        run_dir = Path(brand_path).parent.parent
        for raw in listed:
            text = str(raw or "").strip()
            if not text or "MUST_SUPPLY" in text:
                continue
            path = Path(text) if Path(text).is_absolute() else run_dir / text
            if not path.is_file() or path.stat().st_size == 0:
                continue
            digest = _sha(path)
            if digest in seen:
                continue
            seen.add(digest)
            assets.append({"asset_id": BRAND_LOGO_ID, "local_path": str(path.resolve()),
                           "page": BRAND_PAGE, "kind": "logo", "sha256": digest,
                           "provider": logo.get("origin") or "client",
                           "qc_scope": SCOPE_BRAND_ASSET, "brand_file": str(brand_path)})
    return assets


def page_run_images(root: Path) -> List[Dict[str, Any]]:
    """The generated slot images each page run drew (``<run>/image-generation-qc/Image-NN.png``).

    These are the pictures that end up on the live pages, so they are in SOP-GIP-02's scope
    whether or not a package piece happens to list them; a piece lists design deliverables, and
    leaving the generated images to it left every delivered photograph unreviewed."""
    root = Path(root)
    out: List[Dict[str, Any]] = []
    found: List[Path] = []
    for pattern in ("image-generation-qc/Image-*.png", "*/image-generation-qc/Image-*.png",
                    "*/*/image-generation-qc/Image-*.png"):
        found.extend(sorted(root.glob(pattern)))
    for path in found:
        if not path.is_file():
            continue
        page = path.parent.parent.name
        out.append({"asset_id": path.stem, "local_path": str(path.resolve()), "page": page,
                    "kind": "generated_image", "sha256": _sha(path), "provider": "kie",
                    "qc_scope": SCOPE_AI_IMAGE})
    return out


def collect_images(manifest: Dict[str, Any], package_root: Path) -> List[Dict[str, Any]]:
    """Every image the launch ships: PNG design images and boards, the generated slot images each
    page run drew, and the client's brand logo — each with its page identity and the scope that
    decides which automatic fails apply."""
    package_root = Path(package_root)
    out: List[Dict[str, Any]] = []
    seen = set()
    for piece in manifest.get("pieces") or []:
        for art in piece.get("artifacts") or []:
            path = str(art.get("path") or "")
            kind = page_designs.classify(path, art.get("kind"))
            full = package_root / path
            if kind and path.lower().endswith(".png") and full.is_file():
                seen.add(str(full.resolve()))
                out.append({"asset_id": Path(path).stem, "local_path": str(full), "page": page_designs.page_key(piece),
                            "kind": kind, "sha256": _sha(full),
                            "provider": art.get("provider") or piece.get("image_provider"),
                            "qc_scope": SCOPE_AI_IMAGE})
    for image in page_run_images(package_root):
        if image["local_path"] not in seen:
            seen.add(image["local_path"])
            out.append(image)
    out.extend(brand_logo_assets(package_root))
    return out


def qc_request(manifest: Dict[str, Any], package_root: Path, job_dir: Path,
               author_models: Optional[Dict[str, str]] = None,
               repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """Write <job>/qc/image_qc_request.json. A request, not a verdict: nothing here claims QC passed."""
    images = collect_images(manifest, package_root)
    for img in images:
        img["prompt_author_model"] = (author_models or {}).get(img["asset_id"]) or "UNKNOWN"
        img["applicable_autofails"] = applicable_autofails(img["qc_scope"], repo_root)
    request = {
        "procedure": "SOP-GIP-02",
        "scope": ("every image in this launch package leaves the department to a client, and the "
                  "client's own logo goes with them: 100 percent coverage"),
        "pass_bar": {"average_at_least": PASS_AVERAGE, "automatic_failures": 0},
        "automatic_fail_battery": autofail_battery(repo_root),
        "reviewer_rule": ("the reviewing model and reviewer session must differ from the model and "
                          "session that authored the prompt; an unknown prompt-author model counts as "
                          "NOT independent (write_review.py --author-model / --reviewer-model)"),
        "review_rule": ("every record must cite review_ref, the write_review.py file for that asset: "
                        "its artifact_sha256 must equal the asset's sha256, its verdict must be pass "
                        "with no automatic failure, and its average must be the mean of its own "
                        "criterion scores. A hand-written average or a request file is not a review"),
        "vision_read": "mandatory: a real multimodal read of every image, never graded from file names or prompts",
        "expected_report": QC_REPORT_REL,
        "report_record_shape": ["local_path", "asset_id", "sha256", "average", "pass",
                                "triggered_autofails", "review_ref", "prompt_author_model",
                                "reviewer_model"],
        "assets": images,
    }
    path = Path(job_dir) / QC_REQUEST_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return request


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _number(value: Any) -> Optional[float]:
    """A real finite number (never a bool, never NaN), else None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
        return None
    return float(value)


def _same_file(recorded: Any, job_dir: Path, image_path: str) -> bool:
    try:
        path = Path(str(recorded))
        return (path if path.is_absolute() else job_dir / path).resolve() == Path(image_path).resolve()
    except (OSError, ValueError):
        return False


def _mean_score(review: Dict[str, Any]) -> Optional[float]:
    """The mean of a review's own criterion scores, or None when it scored nothing."""
    scores = [_number(v.get("score")) for v in (review.get("criteria") or {}).values()
              if isinstance(v, dict)]
    real = [s for s in scores if s is not None]
    return round(sum(real) / len(real), 2) if real else None


def _review_problems(rec: Dict[str, Any], img: Dict[str, Any], job_dir: Path,
                     cache: Dict[Path, Any]) -> List[str]:
    """Why one report record is not a review of THESE bytes by two named, different models.

    A request file is not a review, and neither is a number typed into the report: the record
    must cite the ``write_review.py`` file for this asset, and that file must hash to the same
    bytes, pass, carry no automatic failure, be independent, and score what the report claims."""
    where = f"{img['page']} {Path(img['local_path']).name}"
    problems: List[str] = []
    recorded = rec.get("sha256")
    if not _nonempty_str(recorded):
        problems.append(f"{QC_CODE}: {where} carries no sha256; a record that never names the bytes it "
                        "reviewed vouches for nothing")
    elif str(recorded).strip().lower() != img["sha256"]:
        problems.append(f"{QC_CODE}: {where} changed after it was reviewed (the record names sha256 "
                        f"{str(recorded).strip()[:12]}…, the asset is {img['sha256'][:12]}…)")
    ref = str(rec.get("review_ref") or "").strip()
    if not ref:
        problems.append(f"{QC_CODE}: {where} cites no review_ref; a request file or a written-in average "
                        "is not a review (write_review.py writes private/reviews/<stage>/<item>.review.json)")
        return problems
    path = Path(ref) if Path(ref).is_absolute() else job_dir / ref
    if path not in cache:
        cache[path] = _read(path)
    review = cache[path]
    if not isinstance(review, dict):
        problems.append(f"{QC_CODE}: {where} review_ref {ref!r} is not a readable review record")
        return problems
    reviewed = str(review.get("artifact_sha256") or "").strip().lower()
    if reviewed != img["sha256"]:
        problems.append(f"{QC_CODE}: {where} review {ref!r} reviewed different bytes "
                        f"(artifact_sha256 {reviewed[:12] or 'missing'}…, asset {img['sha256'][:12]}…)")
    if review.get("verdict") != "pass":
        problems.append(f"{QC_CODE}: {where} review {ref!r} verdict is {review.get('verdict')!r}, not pass")
    if review.get("automatic_failures"):
        problems.append(f"{QC_CODE}: {where} review {ref!r} records automatic failure(s) "
                        f"{', '.join(str(a) for a in review['automatic_failures'])}")
    if review.get("independent_review") is not True:
        problems.append(f"{QC_CODE}: {where} review {ref!r} is not an independent review "
                        "(reviewer session is unknown or the author's own)")
    if not _nonempty_str(review.get("performed_check")):
        problems.append(f"{QC_CODE}: {where} review {ref!r} does not say what the reviewer actually did")
    author = str(review.get("author_model") or "").strip()
    reviewer = str(review.get("reviewer_model") or "").strip()
    if not author or not reviewer:
        problems.append(f"{QC_CODE}: {where} review {ref!r} names no prompt-author AND reviewer model; "
                        "an unnamed model counts as NOT independent")
    elif author.lower() == reviewer.lower():
        problems.append(f"{QC_CODE}: {where} was reviewed by its own prompt author's model {author!r}")
    elif _nonempty_str(rec.get("prompt_author_model")) and \
            str(rec["prompt_author_model"]).strip().lower() != author.lower():
        problems.append(f"{QC_CODE}: {where} report says the prompt author was "
                        f"{rec['prompt_author_model']!r} but the review names {author!r}")
    claimed = _number(rec.get("average"))
    actual = _mean_score(review)
    if claimed is not None and actual is not None and abs(claimed - actual) > 0.005:
        problems.append(f"{QC_CODE}: {where} report claims average {claimed}, but its review's own "
                        f"criterion scores average {actual}; the number is not the review's")
    return problems


def asset_review_problems(rec: Dict[str, Any], img: Dict[str, Any], job_dir: Path,
                          cache: Optional[Dict[Path, Any]] = None) -> List[str]:
    """Every way ONE report record fails to be a passing review of ONE asset (empty when it is).

    Shared by the package gate and by the image-map producer, so the map's ``qc_status`` and
    the SOP-GIP-02 verdict cannot disagree about whether an asset was reviewed."""
    problems: List[str] = []
    where = f"{img['page']} {Path(img['local_path']).name}"
    average = _number(rec.get("average"))
    if average is None:
        problems.append(f"{QC_CODE}: {where} has no numeric average")
    elif average < PASS_AVERAGE:
        problems.append(f"{QC_CODE}: {where} averages {average}, under the {PASS_AVERAGE} bar")
    autofails = rec.get("triggered_autofails")
    if not isinstance(autofails, list):
        problems.append(f"{QC_CODE}: {where} does not list its triggered_autofails")
    elif autofails:
        problems.append(f"{QC_CODE}: {where} has automatic failure(s) "
                        f"{', '.join(str(a) for a in autofails)}")
    if rec.get("pass") is not True:
        problems.append(f"{QC_CODE}: {where} is not recorded as passed")
    problems.extend(_review_problems(rec, img, Path(job_dir), cache if cache is not None else {}))
    return problems


def report_violations(manifest: Dict[str, Any], package_root: Path,
                      job_dir: Optional[Path] = None) -> List[str]:
    """SOP-GIP-02 at check time: ``qc/image_qc_report.json`` must exist and cover 100 percent of the
    package's images and its brand logo, each record bound to a real review of the same bytes by a
    named reviewer model that differs from the prompt author's, with a real average of at least
    PASS_AVERAGE, ``pass`` true and no automatic failure. A missing report, a missing image, a low or
    non-numeric average, a changed file, a missing hash and an unbound record each fail by name.
    An empty list passes. The report is read from the launch folder that carries it
    (``qc_report_root``), which is the folder its records' relative paths and review_refs resolve
    against — the same one ``qc_request`` wrote the request into."""
    package_root = Path(package_root)
    job_dir = qc_report_root(job_dir if job_dir else package_root)
    report = _read(job_dir / QC_REPORT_REL)
    if not isinstance(report, dict) or not isinstance(report.get("assets"), list):
        return [f"{QC_CODE}: {QC_REPORT_REL} is missing or unreadable; every image in the package needs "
                "an independent review before it is delivered (SOP-GIP-02)"]
    images = collect_images(manifest, package_root)
    if not images:
        return [f"{QC_CODE}: the package holds no design image to review"]
    records = [r for r in report["assets"] if isinstance(r, dict)]
    cache: Dict[Path, Any] = {}
    fails: List[str] = []
    for img in images:
        name = Path(img["local_path"]).name
        found = [r for r in records if _same_file(r.get("local_path"), job_dir, img["local_path"])]
        if not found:  # a record may name the asset by id instead of by a resolved path
            found = [r for r in records if str(r.get("asset_id") or "") == img["asset_id"]]
        if not found:
            fails.append(f"{QC_CODE}: {img['page']} {name} has no record in {QC_REPORT_REL} (100 percent coverage)")
            continue
        clean, complaints = False, []
        for rec in found:
            problems = asset_review_problems(rec, img, job_dir, cache)
            if problems:
                complaints.extend(problems)
            else:
                clean = True
        if not clean:
            fails.extend(complaints or [f"{QC_CODE}: {img['page']} {name} has no passing record"])
    return fails


def ghl_media_present(repo_root: Optional[Path] = None) -> bool:
    try:
        return resolve_ref(GHL_MEDIA_REF, repo_root or REPO_ROOT).is_file()
    except LookupError:
        return False


def graphics_push_module(repo_root: Optional[Path] = None):
    """Skill 45's graphics push, loaded from the repo; None when it is not installed."""
    try:
        path = resolve_ref(GRAPHICS_PUSH_REF, repo_root or REPO_ROOT)
    except LookupError:
        return None
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("_launch_graphics_ghl_push", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def host_assets(job_dir: Path, approval_ref: Any = None, approval_store: Optional[str] = None,
                repo_root: Optional[Path] = None, opener=None,
                liveness_opener=None) -> Dict[str, Any]:
    """SOP-GIP-03 upload through the ONE existing graphics push (Skill 45), behind its own approval.

    Every QC-passed asset — the page photography and the client's logo alike — is uploaded by
    ``graphics_ghl_push.push_graphics_media``, which writes ``media_library.json`` with the real
    public URL per file. Nothing is uploaded without an ``approval_ref`` that resolves to a live
    write for the client's location; that refusal is Skill 45's own and is recorded here by name,
    never bypassed. When the push cannot run, the run is never made to look hosted."""
    job_dir = Path(job_dir)
    module = graphics_push_module(repo_root)
    if module is None:
        return {"uploaded": False,
                "missing_capability": [f"the graphics hosting script ({GRAPHICS_PUSH_REF}) is not "
                                       "installed here, so nothing can be hosted"]}
    try:
        result = module.push_graphics_media(job_dir.resolve(), job_slug=job_dir.name,
                                            approval_ref=approval_ref, approval_store=approval_store,
                                            opener=opener, liveness_opener=liveness_opener)
    except Exception as exc:  # noqa: BLE001  (a refusal is a recorded capability gap, never a crash)
        return {"uploaded": False, "missing_capability": [f"the upload did not run: {exc}"]}
    return {"uploaded": True, "ledger": str(job_dir / LEDGER_REL),
            "upload_count": result.get("upload_count"), "folder_id": result.get("ghl_folder_id")}


def delivery_record(manifest: Dict[str, Any], package_root: Path, job_dir: Path,
                    probe_env: Optional[Dict[str, str]] = None,
                    repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """Write <job>/delivery_record.json (SOP-GIP-03). Records; never uploads, never publishes.

    Only the SOP-GIP-02 report is launch-scoped (``qc_report_root``); the ledger and the record
    this writes are the job's own, beside the files it delivered."""
    job_dir = Path(job_dir)
    report = _read(qc_report_root(job_dir) / QC_REPORT_REL) or {}
    qc = {str(a.get("local_path")): a for a in (report.get("assets") or []) if isinstance(a, dict)}
    ledger = _read(job_dir / LEDGER_REL) or {}
    hosted = {str(e.get("local_path")): e for e in (ledger.get("uploaded") or []) if isinstance(e, dict)}

    assets: List[Dict[str, Any]] = []
    for img in collect_images(manifest, package_root):
        verdict = qc.get(img["local_path"])
        if verdict is None:
            qc_state = "not_reviewed"
        else:
            clean = verdict.get("pass") is True and not (verdict.get("triggered_autofails") or [])
            qc_state = "qc_passed" if clean else "qc_failed"
        entry = hosted.get(img["local_path"])
        live = bool(entry and entry.get("ghl_upload_status") == "complete"
                    and (entry.get("liveness") or {}).get("live") is True)
        assets.append({"asset_id": img["asset_id"], "page": img["page"], "kind": img["kind"],
                       "local_path": img["local_path"], "qc": qc_state,
                       "hosted": live, "public_url": entry.get("public_url") if live else None})

    missing: List[str] = []
    module_ok = ghl_media_present(repo_root)
    if not module_ok:
        missing.append(f"the shared hosting module ({GHL_MEDIA_REF}) is not installed")
    elif probe_env is not None:
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "_launch_ghl_media", resolve_ref(GHL_MEDIA_REF, repo_root or REPO_ROOT))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            mod.resolve_location_pit(probe_env, search_stores=False)
        except Exception:  # noqa: BLE001  (a missing credential is a recorded capability gap, never printed)
            missing.append("the client's hosting credentials are not available to this run")
    if not assets or not all(a["hosted"] for a in assets):
        missing.append("no live hosted link is recorded for every image; hosting is a separate approved "
                       f"step ({GRAPHICS_PUSH_REF} with an approval_ref, then host_assets)")

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
        "assets": assets,
    }
    path = job_dir / DELIVERY_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record
