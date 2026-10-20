"""Graphics department hooks for the launch package (SOP-GIP-02 image QC, SOP-GIP-03 delivery).

The launch's wireframes and mockups are AI-generated images that go to a client, so the Graphics
department's two procedures apply to them:

* ``qc_request`` writes the SOP-GIP-02 request: every image in the package, the AF-G1..AF-G8
  automatic-fail battery (read from Skill 71's stage contract, never retyped here), the pass bar
  and the independence rule (the reviewer is never the model that wrote the prompt).
* ``delivery_record`` writes the SOP-GIP-03 record: for each image, whether it passed QC and
  whether a live hosted link exists. It NEVER publishes and never uploads. When no live link
  exists it records the missing capability by name, so the delivery report says "waiting for an
  approved hosting step" instead of implying the client can open a link.

Hosting itself belongs to ``45-design-intelligence-library/scripts/graphics_ghl_push.py`` (which uses
the shared GHL media module in Skill 06's tools) behind its own approval; this module only reads the
ledger that script writes (``media_library.json``) when one exists.

No credential is read or printed. Capability is probed only when the caller passes an explicit
environment mapping.
"""

from __future__ import annotations

import hashlib
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
STAGE_CONTRACT_REF = "71-blackceo-signature-page/references/stage-contract.json"


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


def qc_request(manifest: Dict[str, Any], package_root: Path, job_dir: Path,
               author_models: Optional[Dict[str, str]] = None,
               repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """Write <job>/qc/image_qc_request.json. A request, not a verdict: nothing here claims QC passed."""
    images = collect_images(manifest, package_root)
    for img in images:
        img["prompt_author_model"] = (author_models or {}).get(img["asset_id"]) or "UNKNOWN"
    request = {
        "procedure": "SOP-GIP-02",
        "scope": "every AI-generated image in this launch package leaves the department to a client: 100 percent coverage",
        "pass_bar": {"average_at_least": PASS_AVERAGE, "automatic_failures": 0},
        "automatic_fail_battery": autofail_battery(repo_root),
        "reviewer_rule": ("the reviewing model must differ from the model that wrote the image's prompt; "
                          "an unknown prompt-author model counts as NOT independent (write_review.py "
                          "--author-model / --reviewer-model)"),
        "vision_read": "mandatory: a real multimodal read of every image, never graded from file names or prompts",
        "expected_report": QC_REPORT_REL,
        "report_record_shape": ["local_path", "asset_id", "average", "pass", "triggered_autofails"],
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


def ghl_media_present(repo_root: Optional[Path] = None) -> bool:
    try:
        return resolve_ref(GHL_MEDIA_REF, repo_root or REPO_ROOT).is_file()
    except LookupError:
        return False


def delivery_record(manifest: Dict[str, Any], package_root: Path, job_dir: Path,
                    probe_env: Optional[Dict[str, str]] = None,
                    repo_root: Optional[Path] = None) -> Dict[str, Any]:
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
        "assets": assets,
    }
    path = job_dir / DELIVERY_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record
