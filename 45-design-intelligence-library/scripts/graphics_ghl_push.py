#!/usr/bin/env python3
"""graphics_ghl_push.py — host a graphics job's QC-PASSED assets in the client's GHL media
library, AND enforce the HARD closeout gate that no finished graphics asset is delivered
without that upload.

WHY THIS EXISTS
---------------
The Graphics department's connection-manifest.json REQUIRES GOHIGHLEVEL_API_KEY +
GOHIGHLEVEL_LOCATION_ID "for uploading finished graphics assets to the GHL media library",
but NO graphics role, SOP, or script implemented finished-asset upload — the manifest
promised a pipeline that did not exist (diagnosis G3). This is that pipeline, ported thin
from the Presentations department's ghl_media_push.py so both departments share the ONE
canonical, verified-working REST module (48-facebook-ad-generator/tools/ghl_media.py) and
never fork the folder-create / upload-file calls.

WHAT IT DOES (SOP-GIP-03)
-------------------------
  1. CREATES a named per-job media folder ("<Client> Graphics <Job> v<N>") so the finished
     assets group under the job, never scattered in the media root. Folder-create is the
     PRIMARY path (POST /medias/folder, Version 2021-07-28, client LOCATION PIT); on decline
     it falls back to the media ROOT with a "<job> — " name PREFIX. Either way ghl_folder_id
     is recorded ("root" is a valid PASSING fallback).
  2. Uploads every QC-PASSED asset (reads the job's SOP-GIP-02 report — only assets with
     pass:true and ZERO auto-fails; the report is the launch's, see _qc_report_path) via
     ghl_media.upload_media (POST /medias/upload-file,
     multipart, parentId), recording {fileId, url} per asset to <job>/media_library.json AND,
     best-effort, into the Vault provenance sidecar (ghl_media_id + ghl_public_url).
  3. Post-upload LIVENESS check: GET the returned public URL and record what it returned — the
     HTTP status, the real Content-Type header, and what the bytes decode to (image magic header
     and pixel dimensions). HTTP 200 with a non-empty body is NOT proof of a picture: a
     Cloudflare/GHL login page is exactly that, so the ledger carries the evidence admission
     needs (F17 item 12).

CANONICAL LEDGER (the file the gate reads): <job>/media_library.json.

CLOSEOUT GATE — no delivery without the GHL upload (folds under AF-DELIVERY-COMPLETE):
    gate_graphics_media_complete(job_dir) -> (ok, reasons)
    python3 graphics_ghl_push.py --gate --job-dir <job_dir>   (exit 0 pass / 1 fail)
For every GHL-enabled job it HARD-FAILS unless media_library.json records: (1) a resolved
ghl_folder_id (real id OR "root"); and (2) every QC-PASSED asset uploaded with a real
ghl_media_id + ghl_upload_status:"complete". The ONLY skip is a LOGGED owner/founder token in
<job>/checkpoints/process_manifest.json under owner_skip_approval (owner_approved:true +
approved_by + reason + a matching gate name). An agent setting has_ghl:false on its own does
NOT skip the gate.

FORBIDDEN: driving the GoHighLevel UI in a browser. The media library is touched ONLY via
this REST path. Client jobs use the CLIENT's LOCATION PIT (GOHIGHLEVEL_API_KEY / GHL_API_KEY),
never the operator's key, never an agency PIT (the agency PIT 401s for media).

Idempotent per file (the absolute local path is the ledger key) so a retry never re-uploads.
Fail-loud: a missing LOCATION PIT raises; an upload returning no fileId/url raises. No
fabricated CDN URLs, ever. Stdlib only.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# The closeout code this GHL-upload gate folds under (mirrors presentations AF-DELIVERY-COMPLETE).
GHL_UPLOAD_GATE = "AF-DELIVERY-COMPLETE"

# Owner-skip token gate names this carve-out will honor (any one matches).
_GATE_ALIASES = frozenset({
    "AF-DELIVERY-COMPLETE", "AF-GIP-DELIVERY-COMPLETE", "AF-BUNDLE-COMPLETE",
    "graphics_ghl_upload", "ghl_media", "media_library", "ghl_upload",
})


# ---------------------------------------------------------------------------
# Load the ONE canonical, verified-working GHL media module (never fork the REST calls).
# Walk up from this file to the repo root (the dir that contains 48-facebook-ad-generator),
# exactly like presentations/scripts/ghl_media.py resolves it.
# ---------------------------------------------------------------------------
def _load_canonical_ghl_media():
    here = Path(__file__).resolve()
    for parent in here.parents:
        cand = parent / "48-facebook-ad-generator" / "tools" / "ghl_media.py"
        if cand.is_file():
            spec = importlib.util.spec_from_file_location("_ghl_media_canonical_graphics", str(cand))
            mod = importlib.util.module_from_spec(spec)
            sys.modules.setdefault("_ghl_media_canonical_graphics", mod)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            return mod
    raise FileNotFoundError(
        "canonical ghl_media.py not found — expected "
        "<repo>/48-facebook-ad-generator/tools/ghl_media.py (the verified-working GHL media "
        "folder-create + upload module the Graphics dept SHARES; never fork these REST calls).")


ghl_media = _load_canonical_ghl_media()


# ---------------------------------------------------------------------------
# S06-06 / ENF-19: a push writes into the client's LIVE GHL sub-account, so it needs the
# SAME launcher approval record Skill 6 needs to publish (allowed_write_target
# approved_live_publication, test_only false, this location, not revoked/expired), read
# from the launch approval store. Loaded from Skill 6 (one check, never a fork); if it
# cannot be found the push is refused (fail closed).
# ---------------------------------------------------------------------------
def _load_publish_approval():
    here = Path(__file__).resolve()
    for parent in here.parents:
        cand = parent / "06-ghl-install-pages" / "tools" / "ghl_publish_approval.py"
        if cand.is_file():
            spec = importlib.util.spec_from_file_location("_ghl_publish_approval_graphics", str(cand))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            return mod
    raise RuntimeError(
        "REFUSE push: Skill 6 ghl_publish_approval.py not found "
        "(<repo>/06-ghl-install-pages/tools/) - cannot verify the launcher approval record")


# ---------------------------------------------------------------------------
# F19: the ONE current-file review authority. A local pass:true flag, an empty
# auto-fail list, or a same-named file is not a review. The uploader and the
# delivery gate below consume the shared validator (shared-utils/
# signature_launch_contract/review_record.py) over the asset's CURRENT bytes.
# ---------------------------------------------------------------------------
def _load_review_record():
    here = Path(__file__).resolve()
    for parent in here.parents:
        cand = parent / "shared-utils" / "signature_launch_contract" / "review_record.py"
        if cand.is_file():
            spec = importlib.util.spec_from_file_location(
                "_review_record_graphics", str(cand))
            mod = importlib.util.module_from_spec(spec)
            sys.modules.setdefault("_review_record_graphics", mod)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            return mod
    raise RuntimeError(
        "REFUSE delivery: shared review_record.py not found "
        "(<repo>/shared-utils/signature_launch_contract/) - cannot verify "
        "independent current-file review")


_REVIEW_MODULE = None


def review_module():
    global _REVIEW_MODULE
    if _REVIEW_MODULE is None:
        _REVIEW_MODULE = _load_review_record()
    return _REVIEW_MODULE


def _load_approval_record():
    here = Path(__file__).resolve()
    for parent in here.parents:
        cand = parent / "shared-utils" / "signature_launch_contract" / "approval_record.py"
        if cand.is_file():
            spec = importlib.util.spec_from_file_location(
                "_approval_record_graphics", str(cand))
            mod = importlib.util.module_from_spec(spec)
            sys.modules.setdefault("_approval_record_graphics", mod)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            return mod
    return None


def _default_approval_verifier(approval_id, kind, plan_hash, scope):
    """The real F20 authority: a live Command Center verification."""
    mod = _load_approval_record()
    if mod is None:
        raise RuntimeError("REFUSE waiver: shared approval_record.py not found")
    return mod.verify(approval_id, kind, plan_hash, list(scope))


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(p: Path):
    try:
        return json.loads(Path(p).read_text())
    except Exception:  # noqa: BLE001
        return {}


def _ledger_path(job_dir: Path) -> Path:
    return Path(job_dir) / "media_library.json"


# The SOP-GIP-02 request and the report it names are written ONCE for the whole launch, into the
# launch run's qc/ folder (the request carries the report beside it as its expected_report). A page
# run is nested inside it (<launch run>/dispatch/<page>), so the report is resolved up the tree.
_QC_REPORT_REL = "image_qc_report.json"
_QC_REQUEST_REL = "image_qc_request.json"


def _qc_report_path(job_dir: Path) -> Path:
    """The SOP-GIP-02 report this job's assets were reviewed in.

    The launcher writes the request — and expects the report beside it — in the LAUNCH run folder,
    while a job folder for one page is nested inside that launch run. Asking the job folder for its
    own qc/ report therefore found nothing on a real launch and refused an upload every asset had
    passed. The report is read from the nearest enclosing folder that carries it (the report first,
    then the request that names it), and from the job folder itself only when no enclosing folder
    does — a job driven on its own, which is the flat layout this chain used before pages nested.
    Same rule as launcher_core/graphics_hooks.qc_report_root, so the upload and the package gate
    can never disagree about which file is the review.
    """
    job_dir = Path(job_dir)
    for name in (_QC_REPORT_REL, _QC_REQUEST_REL):
        for folder in (job_dir, *job_dir.parents):
            if (folder / "qc" / name).is_file():
                return folder / "qc" / _QC_REPORT_REL
    return job_dir / "qc" / _QC_REPORT_REL


def _is_png(path_str: str) -> bool:
    return Path(path_str).name.lower().endswith(".png")


def _autofails_of(entry: dict) -> list:
    if not isinstance(entry, dict):
        return []
    af = entry.get("triggered_autofails") or entry.get("autofails_triggered") or []
    return list(af) if isinstance(af, (list, tuple)) else []


def collect_passed_assets(job_dir) -> list:
    """Read <job>/qc/image_qc_report.json and return the list of QC-PASSED asset records —
    each an image with pass:true AND zero triggered auto-fails. These are the ONLY assets
    that are hosted (a QC-failed asset is not delivered). Tolerant of the presentations QC
    shape (average|average_score, triggered_autofails|autofails_triggered) so the two depts
    can share code. Returns [] when the report is missing/empty. Never raises."""
    report = _read_json(_qc_report_path(job_dir))
    if not isinstance(report, dict):
        return []
    assets = report.get("assets") or report.get("images") or []
    if not isinstance(assets, list):
        return []
    out = []
    for a in assets:
        if not isinstance(a, dict):
            continue
        if a.get("pass") is not True:
            continue
        if _autofails_of(a):
            continue
        lp = a.get("local_path") or a.get("path") or a.get("file")
        if not lp:
            continue
        out.append(a)
    return out


def _asset_key(entry: dict) -> str:
    return str(entry.get("local_path") or entry.get("path") or entry.get("file") or "")


def _sha256_file(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _asset_abspath(job_dir: Path, asset: dict) -> Path:
    rel = _asset_key(asset)
    return Path(rel) if Path(rel).is_absolute() else (Path(job_dir) / rel)


def _job_json(job_dir: Path) -> dict:
    for name in ("job.json", "intake.json"):
        data = _read_json(Path(job_dir) / name)
        if isinstance(data, dict) and data:
            return data
    return {}


def review_policy(job_dir) -> dict:
    """The governing review policy for this job (fail closed).

    Independent review is REQUIRED for production delivery. A policy may only
    set it false when it also declares ``draft_only: true``; a draft job still
    cannot pass the delivery gate (the gate requires production admission).
    """
    job_dir = Path(job_dir)
    policy = _read_json(job_dir / "review_policy.json")
    if not isinstance(policy, dict):
        policy = {}
    job = _job_json(job_dir)
    for key in ("require_independent_review", "require_model_independence",
                "author_session", "author_model", "attempt_id", "revision",
                "plan_hash"):
        if key not in policy and key in job:
            policy[key] = job.get(key)
    policy.setdefault("require_independent_review", True)
    policy.setdefault("require_model_independence", False)
    policy.setdefault("draft_only", False)
    if policy.get("require_independent_review") is False and not policy.get("draft_only"):
        policy["require_independent_review"] = True
    policy.setdefault("revision", "r1")
    return policy


def _dispatch_ledger(job_dir: Path) -> dict:
    data = _read_json(Path(job_dir) / "qc" / "dispatch_ledger.json")
    return data if isinstance(data, (dict, list)) else {}


def _review_records(job_dir: Path) -> list:
    """Review records for this job: a bundle and/or one file per record."""
    out = []
    bundle = _read_json(Path(job_dir) / "qc" / "review_records.json")
    if isinstance(bundle, dict):
        out.extend(r for r in (bundle.get("records") or []) if isinstance(r, dict))
    elif isinstance(bundle, list):
        out.extend(r for r in bundle if isinstance(r, dict))
    reviews = Path(job_dir) / "reviews"
    if reviews.is_dir():
        for path in sorted(reviews.glob("*.json")):
            data = _read_json(path)
            if isinstance(data, dict):
                out.append(data)
            elif isinstance(data, list):
                out.extend(r for r in data if isinstance(r, dict))
    return out


def review_admission(job_dir, asset: dict, *, policy: dict | None = None):
    """Return (ok, reasons, record) for ONE asset's CURRENT bytes.

    The file's sha256 is computed now. A record that reviewed other bytes is
    stale and cannot authorize this upload. A local pass:true flag is not a
    review and never reaches this function as evidence.
    """
    job_dir = Path(job_dir)
    policy = policy if isinstance(policy, dict) else review_policy(job_dir)
    rel = _asset_key(asset)
    path = _asset_abspath(job_dir, asset)
    sha = _sha256_file(path)
    if not sha:
        return False, [f"{GHL_UPLOAD_GATE}: asset {rel!r} is missing or unreadable; "
                       "there is no current-file review to consume"], None
    try:
        rr = review_module()
    except RuntimeError as exc:
        return False, [str(exc)], None
    ledger = _dispatch_ledger(job_dir)
    records = _review_records(job_dir)
    if not records:
        return False, [
            f"{GHL_UPLOAD_GATE}: asset {rel!r} has no review record; a local "
            "pass:true flag, an empty auto-fail list, or a same-named file is "
            "not independent review"], None
    closest = []
    for record in records:
        scope = str(record.get("scope") or "item").strip().lower()
        fails = rr.validate_review_record(
            record, ledger=ledger,
            author_session=(record.get("author_session")
                            or policy.get("author_session")),
            artifacts=[{"path": rel, "sha256": sha}],
            request_id=record.get("request_id"),
            author_model=policy.get("author_model"),
            require_independence=bool(policy.get("require_independent_review")),
            require_model_independence=bool(policy.get("require_model_independence")),
            exact_artifact_set=(scope in ("asset", "item")),
            expected_scope=scope,
            require_attempt_identity=True,
            attempt_id=record.get("attempt_id"),
            revision=policy.get("revision"))
        if not fails:
            return True, [], record
        closest = fails
    return False, [
        f"{GHL_UPLOAD_GATE}: asset {rel!r} has no accepted current-file review "
        f"record for sha256 {sha[:12]}...: " + "; ".join(closest[:4])], None


_CLIENT_RULES_MODULE = None


def client_rules_module():
    """The shared client-rule sweep, loaded once (F19 items 7-10)."""
    global _CLIENT_RULES_MODULE
    if _CLIENT_RULES_MODULE is None:
        here = Path(__file__).resolve()
        for parent in here.parents:
            cand = parent / "shared-utils" / "signature_launch_contract" / "client_rules.py"
            if cand.is_file():
                spec = importlib.util.spec_from_file_location(
                    "_client_rules_graphics", str(cand))
                mod = importlib.util.module_from_spec(spec)
                sys.modules.setdefault("_client_rules_graphics", mod)
                spec.loader.exec_module(mod)  # type: ignore[union-attr]
                _CLIENT_RULES_MODULE = mod
                break
    return _CLIENT_RULES_MODULE


def client_rule_admission(job_dir) -> tuple[bool, list, str]:
    """Run the client's declared measurable rules over its output tree.

    Absence of a rule document is not an error (no client rules declared).
    A declared document is swept recursively BEFORE admission, including newly
    added nested files and generated reports, and any finding or sweep error
    refuses delivery. This never rewrites files (F19 item 8).
    """
    job_dir = Path(job_dir)
    policy = review_policy(job_dir)
    rel = (policy.get("client_rules_path")
           or _job_json(job_dir).get("client_rules_path") or "client_rules.json")
    rules_path = Path(rel) if Path(rel).is_absolute() else job_dir / rel
    if not rules_path.is_file():
        return True, [], "no client rules declared"
    module = client_rules_module()
    if module is None:
        return False, [f"{GHL_UPLOAD_GATE}: client rules are declared but the "
                       "shared client_rules.py sweep is unavailable (fail closed)"], \
            "sweep unavailable"
    try:
        rules = module.load_client_rules(rules_path)
    except Exception as exc:  # noqa: BLE001 - unusable rules fail closed
        return False, [f"{GHL_UPLOAD_GATE}: client rules refused: {exc}"], "invalid rules"
    reasons = []
    for root_name in (rules.get("output_roots") or ["."]):
        base = Path(root_name) if Path(root_name).is_absolute() else job_dir / root_name
        report = module.sweep_tree(base, rules, exclude=[rules_path])
        for reason in report.get("reasons") or []:
            reasons.append(f"{GHL_UPLOAD_GATE}: client-rule sweep: {reason}")
        for finding in report.get("findings") or []:
            reasons.append(
                f"{GHL_UPLOAD_GATE}: client rule {finding.get('rule_id')!r} "
                f"({finding.get('kind')}) failed in {finding.get('file')}: "
                f"{finding.get('detail')}")
    return (not reasons), reasons, "swept" if not reasons else "violations"


def _checkpoint_laundering(job_dir: Path) -> list:
    """F19 item 5: a locally_verified copy checkpoint is not a designed page."""
    reasons = []
    for name in ("result.json", "page_result.json", "process_result.json"):
        data = _read_json(Path(job_dir) / name)
        if not isinstance(data, dict):
            continue
        claimed = str(data.get("completion") or data.get("stage") or "").lower()
        if data.get("locally_verified") is True and claimed in (
                "page", "design", "complete", "completed", "final", "published"):
            reasons.append(
                f"{GHL_UPLOAD_GATE}: {name} claims {claimed!r} from a "
                "locally_verified copy checkpoint; a checkpoint is not a "
                "completed designed page")
    return reasons


def _write_json_atomic(path: Path, data) -> None:
    """Persist a receipt atomically: an interrupted write cannot leave a
    half-ledger that a later attempt mistakes for accepted evidence."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)


def _update_sidecar(job_dir: Path, asset: dict, ghl_media_id: str, ghl_public_url: str) -> None:
    """Best-effort: merge ghl_media_id + ghl_public_url into the asset's Vault provenance
    sidecar (asset-provenance-librarian SOP 9.5 schema, additive-only). The sidecar path may
    be named in the QC record (`sidecar`) or be `<asset>.json` beside the asset. Never fatal —
    a missing sidecar on a test/box without the Vault is not an error here."""
    cand = []
    sc = asset.get("sidecar")
    if sc:
        cand.append(Path(sc) if Path(sc).is_absolute() else (Path(job_dir) / sc))
    lp = _asset_key(asset)
    if lp:
        p = Path(lp) if Path(lp).is_absolute() else (Path(job_dir) / lp)
        cand.append(p.with_suffix(p.suffix + ".json"))
    for path in cand:
        try:
            if not path.is_file():
                continue
            data = _read_json(path)
            if not isinstance(data, dict):
                continue
            data["ghl_media_id"] = ghl_media_id
            data["ghl_public_url"] = ghl_public_url
            path.write_text(json.dumps(data, indent=2))
            return
        except OSError:
            continue


def _url_live(url: str, opener=None, timeout: int = 30) -> dict:
    """GET the returned public URL and record WHAT it returned: status, byte count, the real
    Content-Type header the transport exposed, and decoded-image evidence read from the bytes
    themselves (magic header + dimensions).

    A nonempty body is not proof of a picture: a Cloudflare/GHL login page answers HTTP 200 with
    ``<!doctype html>…Sign in to continue`` (F17 item 12). ``content_type`` is null ONLY when the
    transport exposed no header — the consumer refuses that; it is never filled in from the
    filename or guessed. Never raises: a liveness failure is RECORDED (not fatal to the upload
    record) and surfaces in the ledger so the Vault/QC can flag it."""
    _opener = opener or (lambda u, t: urllib.request.urlopen(u, timeout=t))
    try:
        resp = _opener(url, timeout)
        code = int(resp.getcode())
        ctype = _content_type_of(resp)
        body = resp.read() or b""
    except urllib.error.HTTPError as exc:  # noqa: PERF203
        return {"live": False, "http": int(getattr(exc, "code", 0)), "bytes": 0,
                "content_type": _content_type_of(exc), "image": image_evidence(b"")}
    except (urllib.error.URLError, OSError):
        return {"live": False, "http": None, "bytes": 0, "content_type": None,
                "image": image_evidence(b"")}
    return {"live": (200 <= code < 300) and len(body) > 0, "http": code, "bytes": len(body),
            "content_type": ctype, "image": image_evidence(body)}


def _content_type_of(resp) -> str | None:
    """The response's own Content-Type header, or None when the transport did not expose one."""
    headers = getattr(resp, "headers", None)
    getter = getattr(headers, "get", None)
    if not callable(getter):
        return None
    value = getter("Content-Type")
    if not value:
        return None
    return str(value).strip() or None


def image_evidence(data: bytes) -> dict:
    """What these bytes ARE: the format their magic header names and its decoded dimensions.

    ``decodes`` is True only when a recognised raster header AND real pixel dimensions were read,
    so an HTML page, a JSON body or a truncated stub is never image evidence. Dimensions are
    decoded from the container header (PNG IHDR, JPEG SOF, WebP VP8/VP8L/VP8X); a format whose
    header cannot be read counts as not decoded."""
    data = data or b""
    out = {"format": None, "decodes": False, "width": None, "height": None,
           "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest() if data else None}
    size = None
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        out["format"], size = "png", _png_dimensions(data)
    elif data.startswith(b"\xff\xd8\xff"):
        out["format"], size = "jpeg", _jpeg_dimensions(data)
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        out["format"], size = "webp", _webp_dimensions(data)
    if size and size[0] > 0 and size[1] > 0:
        out.update(decodes=True, width=size[0], height=size[1])
    return out


def _png_dimensions(data: bytes):
    if len(data) < 24 or data[12:16] != b"IHDR":
        return None
    return (int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big"))


_SOF_MARKERS = frozenset({0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF})


def _jpeg_dimensions(data: bytes):
    """Walk the JPEG marker segments to the first Start-Of-Frame (height at +5, width at +7)."""
    pos, end = 2, len(data)
    while pos + 4 <= end:
        if data[pos] != 0xFF:
            pos += 1
            continue
        marker = data[pos + 1]
        if marker in (0xFF, 0x01, 0xD8) or 0xD0 <= marker <= 0xD7:  # fill / standalone / RSTn
            pos += 1 if marker == 0xFF else 2
            continue
        length = int.from_bytes(data[pos + 2:pos + 4], "big")
        if marker in _SOF_MARKERS:
            if pos + 9 > end:
                return None
            return (int.from_bytes(data[pos + 7:pos + 9], "big"),
                    int.from_bytes(data[pos + 5:pos + 7], "big"))
        pos += 2 + length
    return None


def _webp_dimensions(data: bytes):
    if len(data) < 30:
        return None
    chunk = data[12:16]
    if chunk == b"VP8X":
        return (1 + int.from_bytes(data[24:27], "little"), 1 + int.from_bytes(data[27:30], "little"))
    if chunk == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
        return (int.from_bytes(data[26:28], "little") & 0x3FFF,
                int.from_bytes(data[28:30], "little") & 0x3FFF)
    if chunk == b"VP8L" and data[20] == 0x2F:
        bits = int.from_bytes(data[21:25], "little")
        return ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
    return None


# ---------------------------------------------------------------------------
# push_graphics_media — create the per-job folder + upload every QC-passed asset.
# ---------------------------------------------------------------------------
def push_graphics_media(job_dir, *, folder_name: str | None = None, job_slug: str | None = None,
                        opener=None, liveness_opener=None, approval_ref=None,
                        approval_store: str | None = None,
                        attempt_id: str | None = None, revision: str | None = None) -> dict:
    """Create the per-job GHL folder and upload every QC-PASSED, CURRENTLY REVIEWED asset.

    Writes the gate-readable ledger to <job>/media_library.json (MERGED with any prior seed)
    atomically after every accepted upload. Idempotent per file AND per current bytes: the
    absolute path plus the local sha256 is the ledger key, so a changed image is re-uploaded
    and a prior attempt's record cannot stand in for the current attempt (F19 item 6).

    REFUSES (RuntimeError) unless (1) ``approval_ref`` resolves to a launcher approval record
    for the client's location, and (2) every QC-passed asset has an accepted current-file
    review record under the shared review validator (F19 item 14)."""
    job_dir = Path(job_dir).resolve()
    # Approval first: nothing is read, created or uploaded without the record.
    _load_publish_approval().require_live_write(
        approval_ref, location_id=ghl_media.resolve_location_id(), store_dir=approval_store)
    slug = (job_slug or job_dir.name).strip()
    fname = (folder_name or f"GRAPHICS {slug}").strip()

    passed = collect_passed_assets(job_dir)
    if not passed:
        raise RuntimeError(
            f"{GHL_UPLOAD_GATE}: no QC-PASSED assets in {_qc_report_path(job_dir)} — nothing to "
            "host. Run SOP-GIP-02 image QC first (only pass:true + zero auto-fails are delivered).")

    policy = review_policy(job_dir)
    refusal = []
    for asset in passed:
        ok, reasons, _record = review_admission(job_dir, asset, policy=policy)
        if not ok:
            refusal.extend(reasons)
    if refusal:
        raise RuntimeError(
            f"{GHL_UPLOAD_GATE}: upload REFUSED — no accepted current-file independent "
            "review for every QC-passed asset. " + " ".join(refusal[:6]))
    c_ok, c_reasons, _c_state = client_rule_admission(job_dir)
    if not c_ok:
        raise RuntimeError(
            f"{GHL_UPLOAD_GATE}: upload REFUSED — the client-rule sweep failed before "
            "admission. " + " ".join(c_reasons[:6]))

    pit = ghl_media.resolve_location_pit()         # client's LOCATION PIT (never operator's)
    location_id = ghl_media.resolve_location_id()   # client's location id

    # 1) PRIMARY: create the per-job media folder via the verified POST /medias/folder.
    folder = ghl_media.create_media_folder(fname, location_id, pit, opener=opener)
    parent_id = folder.get("folderId")
    name_prefix = "" if parent_id else f"{slug} — "
    ghl_folder_id = parent_id or "root"

    ledger_path = _ledger_path(job_dir)
    ledger = _read_json(ledger_path) if ledger_path.exists() else {}
    if not isinstance(ledger, dict):
        ledger = {}
    current_attempt = (attempt_id or policy.get("attempt_id")
                       or f"attempt-{_now_iso()}-{os.getpid()}")
    current_revision = revision or policy.get("revision") or "r1"
    uploaded = [e for e in ledger.get("uploaded", []) if isinstance(e, dict)]
    # A prior attempt's result may be kept as history but must not be mistaken
    # for the current attempt (F19 item 6).
    for entry in uploaded:
        if entry.get("attempt_id") not in (None, current_attempt) \
                or entry.get("revision") not in (None, current_revision):
            entry["stale"] = True
    done = {
        (e.get("local_path"), e.get("local_sha256")): e for e in uploaded
        if e.get("local_path") and e.get("local_sha256")
        and e.get("attempt_id") == current_attempt
        and e.get("revision") == current_revision
        and e.get("stale") is not True
    }

    for asset in passed:
        rel = _asset_key(asset)
        abspath = str(_asset_abspath(job_dir, asset))
        local_sha = _sha256_file(Path(abspath))
        if (abspath, local_sha) in done:
            continue  # idempotent: this exact file content is already hosted
        _ok, _reasons, review = review_admission(job_dir, asset, policy=policy)
        name = f"{name_prefix}{Path(abspath).name}"
        res = ghl_media.upload_media(
            abspath, location_id, name, pit,
            parent_id=parent_id, opener=opener, require_png=_is_png(abspath))
        live = _url_live(res["url"], opener=liveness_opener)
        _update_sidecar(job_dir, asset, res["fileId"], res["url"])
        rec = {
            "local_path": abspath,
            "asset_id": asset.get("asset_id") or Path(abspath).stem,
            "name": name,
            "ghl_remote_name": name,
            "public_url": res["url"],
            "ghl_public_url": res["url"],
            "file_id": res["fileId"],
            "ghl_media_id": res["fileId"],
            "http_status": res["http"],
            "content_type": live.get("content_type"),
            "ghl_upload_status": "complete",
            "ghl_folder_id": ghl_folder_id,
            "liveness": live,
            "local_sha256": local_sha,
            "review_sha256": local_sha,
            "review_record_id": (review or {}).get("record_id")
                                or (review or {}).get("request_id"),
            "reviewer_session": (review or {}).get("reviewer_session"),
            "attempt_id": current_attempt,
            "revision": current_revision,
            "stale": False,
            "uploaded_at": _now_iso(),
        }
        uploaded.append(rec)
        done[(abspath, local_sha)] = rec
        # Persist each accepted upload receipt BEFORE advancing (F21 item 9 /
        # F19 item 6): an interruption cannot repeat or lose an accepted upload.
        ledger.update({
            "job_slug": slug,
            "ghl_folder_id": ghl_folder_id,
            "ghl_folder_name": folder.get("name") or ledger.get("ghl_folder_name") or fname,
            "ghl_folder_created_via_api": bool(folder.get("folderId")),
            "attempt_id": current_attempt,
            "revision": current_revision,
            "uploaded": uploaded,
            "upload_count": len(uploaded),
            "passed_asset_count": len(passed),
        })
        _write_json_atomic(ledger_path, ledger)

    out = {
        "job_slug": slug,
        "ghl_folder_id": ghl_folder_id,
        "ghl_folder_name": folder.get("name") or ledger.get("ghl_folder_name") or fname,
        "ghl_folder_created_via_api": bool(folder.get("folderId")),
        "attempt_id": current_attempt,
        "revision": current_revision,
        "uploaded": uploaded,
        "upload_count": len(uploaded),
        "passed_asset_count": len(passed),
    }
    ledger.update(out)
    _write_json_atomic(ledger_path, ledger)
    return out


# ---------------------------------------------------------------------------
# CLOSEOUT GATE — no delivery without the GHL upload.
# ---------------------------------------------------------------------------
def _waiver_admission(job_dir: Path, *, approval_verifier=None):
    """Return (ok, verified_waiver, reasons) for the ONLY legitimate skip.

    F19 items 5/14: a local owner token is not authority. The token must name
    an ``approval_ref`` and that ref must verify through F20's scoped authority
    (approval_record.verify) for the ``graphics_upload_waiver`` scope. A local
    ``waiver: true``, a has_ghl:false agent choice, or a test-only record is
    refused for production delivery.
    """
    pm = _read_json(Path(job_dir) / "checkpoints" / "process_manifest.json")
    raw = pm.get("owner_skip_approval") if isinstance(pm, dict) else None
    if raw is None:
        return False, None, []
    reasons = []
    records = raw if isinstance(raw, list) else [raw]
    verify = approval_verifier or _default_approval_verifier
    policy = review_policy(job_dir)
    plan_hash = str(policy.get("plan_hash") or _job_json(job_dir).get("plan_hash") or "")
    for rec in records:
        if not isinstance(rec, dict):
            continue
        if rec.get("owner_approved") is not True:
            continue
        if not str(rec.get("approved_by", "")).strip():
            continue
        if not str(rec.get("reason", "")).strip():
            continue
        gate = str(rec.get("gate") or rec.get("gate_id") or rec.get("phase_id") or "").strip()
        if gate not in _GATE_ALIASES:
            continue
        ref = str(rec.get("approval_ref") or "").strip()
        if not ref:
            reasons.append(
                f"{GHL_UPLOAD_GATE}: owner_skip_approval is a local token with no "
                "approval_ref; an upload waiver must be F20-scoped authority, not "
                "a file the worker wrote")
            continue
        try:
            verified = verify(ref, "page_publication", plan_hash,
                              ["graphics_upload_waiver"])
        except Exception as exc:  # noqa: BLE001 - unavailable authority fails closed
            reasons.append(
                f"{GHL_UPLOAD_GATE}: upload waiver {ref!r} could not be verified "
                f"through F20 authority ({type(exc).__name__}); refusal, not a skip")
            continue
        try:
            fails = review_module().validate_upload_waiver(
                verified, required_scope="graphics_upload_waiver",
                test_only=bool(rec.get("test_only")))
        except RuntimeError as exc:
            reasons.append(str(exc))
            continue
        if fails:
            reasons.extend(f"{GHL_UPLOAD_GATE}: upload waiver {ref!r} refused: {f}"
                           for f in fails)
            continue
        return True, verified, []
    return False, None, reasons


def _job_has_ghl(job_dir: Path):
    """Return the has_ghl flag from <job>/job.json or <job>/intake.json (None when unset)."""
    for fn in ("job.json", "intake.json"):
        data = _read_json(Path(job_dir) / fn)
        if isinstance(data, dict) and "has_ghl" in data:
            return data.get("has_ghl")
    return None


def _upload_complete(entry: dict) -> bool:
    mid = entry.get("ghl_media_id") or entry.get("file_id")
    if str(entry.get("ghl_upload_status", "")).lower() in ("failed", "pending"):
        return False
    return bool(str(mid or "").strip())


def gate_graphics_media_complete(job_dir, *, approval_verifier=None, policy=None):
    """HARD closeout gate. Returns (ok: bool, reasons: list[str]).

    PASS only when the SAME current-file review authority the uploader consumes
    has accepted every QC-PASSED asset's CURRENT bytes, and <job>/media_library.json
    records the current attempt/revision, a resolved ghl_folder_id, a real
    ghl_media_id + ghl_upload_status:"complete", the same local sha256, and
    decoded image evidence for the hosted URL. A local pass:true flag, an empty
    auto-fail list, a same-named file, a stale attempt or a nonempty HTML reply
    is insufficient. The only skip is an F20-scoped verified upload waiver
    (_waiver_admission). There is NO defer-to-pass."""
    job_dir = Path(job_dir)
    policy = policy if isinstance(policy, dict) else review_policy(job_dir)

    # The ONLY skip path: an F20-scoped, verified upload waiver.
    waiver_ok, _waiver, waiver_reasons = _waiver_admission(
        job_dir, approval_verifier=approval_verifier)
    if waiver_ok:
        return True, []

    # has_ghl:false WITHOUT a verified waiver is an agent choice, not authority.
    if _job_has_ghl(job_dir) is False:
        return False, waiver_reasons + [
            f"{GHL_UPLOAD_GATE}: job.json/intake.json has_ghl:false but no verified "
            "approval_ref for a graphics_upload_waiver. The GHL media-upload gate "
            "may be skipped ONLY through F20's scoped authority (authenticated "
            "record, approved scope, unexpired, unrevoked). An agent cannot opt "
            "out of the upload on its own."]

    passed = collect_passed_assets(job_dir)
    media = _read_json(_ledger_path(job_dir))

    if not passed:
        return False, [
            f"{GHL_UPLOAD_GATE}: no QC-PASSED assets found in {_qc_report_path(job_dir)} — run "
            "SOP-GIP-02 image QC first; a job with nothing that passed QC has nothing to deliver."]

    if not media:
        return False, [
            f"{GHL_UPLOAD_GATE}: <job>/media_library.json is missing/empty — no GHL upload record "
            "at all (folder + per-asset uploads). No finished graphics asset ships without the GHL "
            "media upload."]

    reasons = list(waiver_reasons)
    reasons.extend(_checkpoint_laundering(job_dir))
    c_ok, c_reasons, _c_state = client_rule_admission(job_dir)
    if not c_ok:
        reasons.extend(c_reasons)

    # (1) per-job folder resolved (a real id OR the 'root' fallback; null seed fails).
    folder = str(media.get("ghl_folder_id") or "").strip()
    if not folder:
        reasons.append(
            f"{GHL_UPLOAD_GATE}: ghl_folder_id is null/empty — the per-job GHL media folder was "
            "never resolved (create_media_folder, or the 'root' fallback).")

    # (2) the ledger must name the CURRENT attempt/revision. A prior attempt's
    # result file surviving a failure cannot be mistaken for this attempt.
    attempt = str(media.get("attempt_id") or "").strip()
    revision = str(media.get("revision") or "").strip()
    if not attempt or not revision:
        reasons.append(
            f"{GHL_UPLOAD_GATE}: media_library.json carries no attempt_id/revision; "
            "a prior attempt's result cannot certify the current attempt")
    if revision and policy.get("revision") and revision != policy.get("revision"):
        reasons.append(
            f"{GHL_UPLOAD_GATE}: ledger revision {revision!r} is not the governing "
            f"revision {policy.get('revision')!r}")
    policy_attempt = str(policy.get("attempt_id") or "").strip()
    if attempt and policy_attempt and attempt != policy_attempt:
        reasons.append(
            f"{GHL_UPLOAD_GATE}: ledger attempt {attempt!r} is not the current "
            f"attempt {policy_attempt!r}; a prior attempt's result cannot certify "
            "the current attempt")

    uploaded = [e for e in media.get("uploaded", []) if isinstance(e, dict)]
    by_path = {str(e.get("local_path") or ""): e for e in uploaded}
    by_id = {str(e.get("asset_id")): e for e in uploaded if e.get("asset_id")}

    for a in passed:
        rel = _asset_key(a)
        apath = _asset_abspath(job_dir, a)
        abspath = str(apath.resolve()) if not Path(rel).is_absolute() else rel
        current_sha = _sha256_file(apath)

        # (3) F19 item 14: the SAME current-file review authority the uploader uses.
        r_ok, r_reasons, _record = review_admission(job_dir, a, policy=policy)
        if not r_ok:
            reasons.extend(r_reasons)

        rec = None
        for candidate in (uploaded and by_path.get(abspath),
                          uploaded and by_path.get(rel),
                          by_id.get(str(a.get("asset_id"))) if a.get("asset_id") else None):
            if candidate is not None:
                rec = candidate
                break
        if rec is None:
            reasons.append(
                f"{GHL_UPLOAD_GATE}: QC-passed asset {rel!r} has NO upload record in "
                "media_library.json — every passed asset must be hosted with a real ghl_media_id.")
            continue
        if rec.get("stale") is True:
            reasons.append(
                f"{GHL_UPLOAD_GATE}: upload record for {rel!r} is stale (a prior "
                "attempt); it cannot certify the current attempt")
            continue
        if attempt and str(rec.get("attempt_id") or "") != attempt:
            reasons.append(
                f"{GHL_UPLOAD_GATE}: upload record for {rel!r} belongs to attempt "
                f"{rec.get('attempt_id')!r}, not the current {attempt!r}")
        if revision and str(rec.get("revision") or "") != revision:
            reasons.append(
                f"{GHL_UPLOAD_GATE}: upload record for {rel!r} is not bound to the "
                f"current revision {revision!r}")
        if not _upload_complete(rec):
            reasons.append(
                f"{GHL_UPLOAD_GATE}: upload for {rel!r} is not complete (no ghl_media_id or status "
                "failed/pending).")
        if not str(rec.get("public_url") or rec.get("ghl_public_url") or "").strip():
            reasons.append(
                f"{GHL_UPLOAD_GATE}: upload record for {rel!r} carries no usable hosted URL")
        if current_sha and rec.get("local_sha256") != current_sha:
            reasons.append(
                f"{GHL_UPLOAD_GATE}: upload record for {rel!r} hosted different bytes "
                f"({str(rec.get('local_sha256'))[:12]}... != {current_sha[:12]}...); "
                "a changed image cannot retain old hosting")
        live = rec.get("liveness") if isinstance(rec.get("liveness"), dict) else {}
        image = live.get("image") if isinstance(live.get("image"), dict) else {}
        if image.get("decodes") is not True:
            reasons.append(
                f"{GHL_UPLOAD_GATE}: upload record for {rel!r} has no decoded image "
                "evidence for the hosted URL (a nonempty HTML reply is not proof "
                "of a picture)")

    return (len(reasons) == 0), reasons


def main():
    ap = argparse.ArgumentParser(description="Host a graphics job's QC-passed assets in GHL, or "
                                             "run the GHL-upload closeout gate.")
    ap.add_argument("--job-dir", required=True)
    ap.add_argument("--folder-name", default=None,
                    help='per-job folder name, e.g. "<Client> Graphics <Job> v<N>".')
    ap.add_argument("--job-slug", default=None)
    ap.add_argument("--approval-ref", default=None,
                    help="launcher approval_ref (record in the launch approval store) "
                         "authorizing this live write; the push is refused without it.")
    ap.add_argument("--gate", action="store_true",
                    help="run the HARD closeout gate (no upload, exit 1 on fail).")
    args = ap.parse_args()
    job_dir = Path(args.job_dir).resolve()

    if args.gate:
        ok, reasons = gate_graphics_media_complete(job_dir)
        if ok:
            print("GRAPHICS GHL MEDIA GATE: PASS (folder + every QC-passed asset recorded, or "
                  "logged owner skip)")
            return 0
        print(f"GRAPHICS GHL MEDIA GATE: FAIL ({GHL_UPLOAD_GATE})")
        for r in reasons:
            print("  -", r)
        return 1

    try:
        res = push_graphics_media(job_dir, folder_name=args.folder_name, job_slug=args.job_slug,
                                  approval_ref=args.approval_ref)
    except RuntimeError as exc:
        print(f"GRAPHICS GHL PUSH: ABORTED — {exc}", file=sys.stderr)
        return 2
    print(json.dumps(res, indent=2))
    return 0


# ---------------------------------------------------------------------------
# SELF-TEST — no network, stdlib only.
# ---------------------------------------------------------------------------
def _selftest() -> int:
    import tempfile
    fails = []

    # A real 1x1 PNG: the bytes that must decode as image evidence, never a magic-byte stub.
    PNG_BYTES = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f"
                 b"\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x9a\xa0\xa0\x00\x00"
                 b"\x00\x00IEND\xaeB`\x82")
    SHA = hashlib.sha256(PNG_BYTES).hexdigest()
    ATTEMPT, REVISION = "attempt-1", "r1"
    PLAN_HASH = "a" * 64

    def _setup(base, *, qc=None, media=None, pm=None, job=None, review=True,
               review_author="author-1", review_reviewer="rev-1",
               review_model="m-review", review_independent=True):
        (base / "qc").mkdir(parents=True, exist_ok=True)
        (base / "checkpoints").mkdir(parents=True, exist_ok=True)
        (base / "renders").mkdir(parents=True, exist_ok=True)
        assets = (qc or {}).get("assets") or []
        for asset in assets:
            rel = asset.get("local_path") or ""
            if rel and asset.get("pass") is True:
                (base / rel).write_bytes(PNG_BYTES)
        if qc is not None:
            (base / "qc" / "image_qc_report.json").write_text(json.dumps(qc))
        if media is not None:
            (base / "media_library.json").write_text(json.dumps(media))
        if pm is not None:
            (base / "checkpoints" / "process_manifest.json").write_text(json.dumps(pm))
        if job is not None:
            (base / "job.json").write_text(json.dumps(job))
        (base / "review_policy.json").write_text(json.dumps({
            "require_independent_review": True,
            "require_model_independence": False,
            "author_session": review_author,
            "author_model": "m-author",
            "attempt_id": ATTEMPT,
            "revision": REVISION,
            "plan_hash": PLAN_HASH,
        }))
        if review:
            records = []
            for asset in assets:
                if asset.get("pass") is not True:
                    continue
                rel = asset.get("local_path")
                records.append({
                    "schema": "signature-launch-review-record/v1",
                    "reviewer_session": review_reviewer,
                    "reviewer_model": review_model,
                    "verdict": "pass",
                    "independent_review": review_independent,
                    "scope": "item",
                    "attempt_id": ATTEMPT,
                    "revision": REVISION,
                    "reviewed_artifacts": [{"path": rel, "sha256": SHA}],
                })
            (base / "qc" / "review_records.json").write_text(json.dumps({"records": records}))
            (base / "qc" / "dispatch_ledger.json").write_text(json.dumps({"sessions": [
                {"session_id": review_reviewer, "model": review_model},
                {"session_id": review_author, "model": "m-author"}]}))

    GOOD_QC = {"gate": "AF-G-IMAGE-QC", "pass": True, "assets": [
        {"local_path": "renders/ad-01.png", "asset_id": "ad-01", "pass": True, "triggered_autofails": []},
        {"local_path": "renders/ad-02.png", "asset_id": "ad-02", "pass": True, "triggered_autofails": []},
        {"local_path": "renders/ad-03.png", "asset_id": "ad-03", "pass": False, "triggered_autofails": ["AF-G1"]},
    ]}

    def _media(base, *, attempt=ATTEMPT, revision=REVISION, folder="fld_1",
               skip=(), status="complete", sha=SHA, decode=True, stale=False):
        uploaded = []
        for asset in GOOD_QC["assets"]:
            if asset.get("pass") is not True or asset.get("local_path") in skip:
                continue
            uploaded.append({
                "local_path": str((base / asset["local_path"]).resolve()),
                "asset_id": asset.get("asset_id"),
                "ghl_media_id": f"m-{asset.get('asset_id')}",
                "ghl_upload_status": status,
                "ghl_folder_id": folder or "root",
                "public_url": "https://storage.googleapis.com/msgsndr/x.png",
                "local_sha256": sha,
                "attempt_id": attempt,
                "revision": revision,
                "stale": stale,
                "liveness": {"live": True, "content_type": "image/png",
                             "image": {"decodes": decode, "format": "png" if decode else None}},
            })
        return {"ghl_folder_id": folder, "attempt_id": attempt,
                "revision": revision, "uploaded": uploaded}

    def _verified_waiver(ref, kind, plan_hash, scope):
        return {"ok": True, "approval_id": ref, "kind": "publish",
                "plan_hash": plan_hash or PLAN_HASH, "scope": list(scope),
                "verification_class": "authenticated_platform_record",
                "revoked": False, "expires_at": "2999-01-01T00:00:00Z"}

    def _gate(base, **kw):
        return gate_graphics_media_complete(base, **kw)

    # A — complete current-file review + uploads -> PASS.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t); _setup(base, qc=GOOD_QC, media=_media(Path(t)), job={"has_ghl": True})
        ok, r = _gate(base)
        if not ok:
            fails.append(f"A complete: expected PASS, got {r}")

    # B — empty ledger -> FAIL.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t); _setup(base, qc=GOOD_QC, media={}, job={"has_ghl": True})
        ok, r = _gate(base)
        if ok or not any("missing/empty" in x for x in r):
            fails.append(f"B empty: expected FAIL, got ok={ok} {r}")

    # C — one passed asset NOT uploaded -> FAIL.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        _setup(base, qc=GOOD_QC, media=_media(Path(t), skip=("renders/ad-02.png",)),
               job={"has_ghl": True})
        ok, r = _gate(base)
        if ok or not any("NO upload record" in x for x in r):
            fails.append(f"C missing-upload: expected FAIL, got ok={ok} {r}")

    # D — null folder id -> FAIL.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        _setup(base, qc=GOOD_QC, media=_media(Path(t), folder=None), job={"has_ghl": True})
        ok, r = _gate(base)
        if ok or not any("ghl_folder_id" in x for x in r):
            fails.append(f"D null-folder: expected FAIL, got ok={ok} {r}")

    # E — an upload marked pending -> FAIL (incomplete).
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        _setup(base, qc=GOOD_QC, media=_media(Path(t), status="pending"), job={"has_ghl": True})
        ok, r = _gate(base)
        if ok or not any("not complete" in x for x in r):
            fails.append(f"E incomplete: expected FAIL, got ok={ok} {r}")

    # F — has_ghl:false with NO waiver -> FAIL (agent cannot opt out).
    with tempfile.TemporaryDirectory() as t:
        base = Path(t); _setup(base, qc=GOOD_QC, media={}, job={"has_ghl": False})
        ok, r = _gate(base)
        if ok or not any("owner_skip_approval" in x or "verified approval_ref" in x for x in r):
            fails.append(f"F agent-skip: expected waiver FAIL, got ok={ok} {r}")

    # G — has_ghl:false WITH a verified F20-scoped waiver -> PASS.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        _setup(base, qc=GOOD_QC, media={}, job={"has_ghl": False},
               pm={"owner_skip_approval": {"owner_approved": True, "approved_by": "owner",
                                           "reason": "client has no GHL account",
                                           "approval_ref": "APPR-WAIVE",
                                           "gate": "AF-DELIVERY-COMPLETE"}})
        ok, r = _gate(base, approval_verifier=_verified_waiver)
        if not ok:
            fails.append(f"G verified-waiver: expected PASS, got {r}")

    # G2 — the same local token WITHOUT a verified approval_ref -> FAIL.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        _setup(base, qc=GOOD_QC, media={}, job={"has_ghl": False},
               pm={"owner_skip_approval": {"owner_approved": True, "approved_by": "owner",
                                           "reason": "client has no GHL account",
                                           "gate": "AF-DELIVERY-COMPLETE"}})
        ok, r = _gate(base, approval_verifier=_verified_waiver)
        if ok or not any("local token" in x or "approval_ref" in x for x in r):
            fails.append(f"G2 local-token: expected FAIL (no approval_ref), got ok={ok} {r}")

    # H — owner skip with owner_approved:false -> NOT a skip -> FAIL.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        _setup(base, qc=GOOD_QC, media={}, job={"has_ghl": True},
               pm={"owner_skip_approval": {"owner_approved": False, "approved_by": "x",
                                           "reason": "y", "approval_ref": "APPR-WAIVE",
                                           "gate": "AF-DELIVERY-COMPLETE"}})
        ok, r = _gate(base, approval_verifier=_verified_waiver)
        if ok:
            fails.append(f"H false-token: expected FAIL, got ok={ok} {r}")

    # I — no QC-passed assets at all -> FAIL.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        _setup(base, qc={"pass": False, "assets": [
            {"local_path": "renders/x.png", "pass": False, "triggered_autofails": ["AF-G1"]}]},
               media={}, job={"has_ghl": True})
        ok, r = _gate(base)
        if ok or not any("nothing that passed QC" in x or "no QC-PASSED" in x.lower() for x in r):
            fails.append(f"I no-passed: expected FAIL, got ok={ok} {r}")

    # M — NEGATIVE CONTROL: a same-session review is REFUSED. A local pass:true
    #     flag with no review record cannot authorize the upload or the gate.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        _setup(base, qc=GOOD_QC, media=_media(Path(t)), job={"has_ghl": True},
               review_reviewer="author-1")
        ok, r = _gate(base)
        if ok or not any("reviewer session == author session" in x for x in r):
            fails.append(f"M same-session: expected refusal, got ok={ok} {r}")
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        _setup(base, qc=GOOD_QC, media=_media(Path(t)), job={"has_ghl": True}, review=False)
        ok, r = _gate(base)
        if ok or not any("no review record" in x for x in r):
            fails.append(f"M no-review: expected refusal, got ok={ok} {r}")

    # N — stale prior attempt / changed bytes -> FAIL.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        _setup(base, qc=GOOD_QC, media=_media(Path(t), attempt="attempt-old"),
               job={"has_ghl": True})
        ok, r = _gate(base)
        if ok or not any("attempt" in x for x in r):
            fails.append(f"N prior-attempt: expected FAIL, got ok={ok} {r}")
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        _setup(base, qc=GOOD_QC, media=_media(Path(t), sha="b" * 64), job={"has_ghl": True})
        ok, r = _gate(base)
        if ok or not any("hosted different bytes" in x for x in r):
            fails.append(f"N changed-bytes: expected FAIL, got ok={ok} {r}")

    # L — liveness evidence, not merely a 200.
    class _Resp:
        def __init__(self, body, ctype):
            self._body, self.headers = body, {"Content-Type": ctype}

        def getcode(self):
            return 200

        def read(self):
            return self._body

    html = _url_live("https://host.test/a.png",
                     opener=lambda u, t: _Resp(b"<!doctype html><body>Sign in to continue",
                                               "text/html; charset=utf-8"))
    if (not html["live"] or html.get("content_type") != "text/html; charset=utf-8"
            or html["image"]["decodes"]):
        fails.append(f"L html200: expected text/html and no image decode, got {html}")
    png = _url_live("https://host.test/b.png", opener=lambda u, t: _Resp(PNG_BYTES, "image/png"))
    if (png.get("content_type") != "image/png" or png["image"]["decodes"] is not True
            or (png["image"]["width"], png["image"]["height"]) != (1, 1)):
        fails.append(f"L png: expected image/png with decoded 1x1 evidence, got {png}")
    missing = _url_live("https://host.test/c.png", opener=lambda u, t: _Resp(PNG_BYTES, ""))
    if missing.get("content_type") is not None:
        fails.append(f"L no-header: expected content_type None (never invented), got {missing}")

    # J/K — end-to-end push over a mock transport + approval refusals.
    def _mock_opener(req, timeout):
        class _R:
            def getcode(self):
                return 200

            def read(self):
                return (b'{"id":"fld_x","folderId":"fld_x","fileId":"file_x",'
                        b'"url":"https://storage.googleapis.com/msgsndr/file_x"}')
        return _R()

    def _mock_live(url, timeout):
        class _R:
            headers = {"Content-Type": "image/png"}

            def getcode(self):
                return 200

            def read(self):
                return PNG_BYTES
        return _R()

    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        _setup(base, qc=GOOD_QC, job={"has_ghl": True})
        saved = {k: os.environ.get(k) for k in ("GHL_API_KEY", "GHL_LOCATION_ID")}
        os.environ["GHL_API_KEY"] = "pit-0f3a9c1e-7b2d-4e65-9a18-c4d2b6e8f0a1"
        os.environ["GHL_LOCATION_ID"] = "loc-fixture"
        try:
            store = base / "approval-store"
            store.mkdir()

            def _put(ref, **over):
                rec = {"approval_ref": ref, "allowed_write_target": "approved_live_publication",
                       "test_only": False, "location_id": "loc-fixture", "page_ids": []}
                rec.update(over)
                (store / f"{ref}.json").write_text(json.dumps(rec))

            _put("APPR-TEST", test_only=True, allowed_write_target="approved_test_location")
            for label, ref in (("none", None), ("free string", "yes"), ("bare bool", True),
                               ("test_only record", "APPR-TEST")):
                try:
                    push_graphics_media(base, opener=_mock_opener, liveness_opener=_mock_live,
                                        approval_ref=ref, approval_store=str(store))
                    fails.append(f"K {label}: push was NOT refused")
                except RuntimeError:
                    pass
            if (base / "media_library.json").exists():
                fails.append("K refused push still wrote media_library.json")

            _put("APPR-LIVE")
            kw = dict(opener=_mock_opener, liveness_opener=_mock_live,
                      approval_ref="APPR-LIVE", approval_store=str(store))
            out = push_graphics_media(base, **kw)
            if out.get("upload_count") != 2:
                fails.append(f"J push: expected 2 uploads (passed only), got {out.get('upload_count')}")
            ok, r = _gate(base)
            if not ok:
                fails.append(f"J push->gate: expected PASS after hosting, got {r}")
            out2 = push_graphics_media(base, **kw)
            if out2.get("upload_count") != 2:
                fails.append(f"J idempotent: re-run changed upload_count to {out2.get('upload_count')}")
            # A changed image has no current-file review: the push must refuse.
            changed = PNG_BYTES + b"changed"
            (base / "renders" / "ad-01.png").write_bytes(changed)
            try:
                push_graphics_media(base, **kw)
                fails.append("J changed-bytes: push accepted bytes with no current review")
            except RuntimeError as exc:
                if "no accepted current-file review" not in str(exc):
                    fails.append(f"J changed-bytes: wrong refusal {exc}")
            # After a fresh review of the new bytes, the upload proceeds.
            new_sha = hashlib.sha256(changed).hexdigest()
            bundle = json.loads((base / "qc" / "review_records.json").read_text())
            for record in bundle.get("records", []):
                paths = [a.get("path") for a in record.get("reviewed_artifacts", [])]
                if "renders/ad-01.png" in paths:
                    record["reviewed_artifacts"] = [
                        {"path": "renders/ad-01.png", "sha256": new_sha}]
                    record["reviewer_session"] = "rev-2"
            (base / "qc" / "review_records.json").write_text(json.dumps(bundle))
            ledger = json.loads((base / "qc" / "dispatch_ledger.json").read_text())
            ledger.setdefault("sessions", []).append(
                {"session_id": "rev-2", "model": "m-review"})
            (base / "qc" / "dispatch_ledger.json").write_text(json.dumps(ledger))
            out3 = push_graphics_media(base, **kw)
            if out3.get("upload_count") != 3:
                fails.append(f"J changed-bytes: expected a re-upload after review, got {out3.get('upload_count')}")
        except Exception as exc:  # noqa: BLE001
            fails.append(f"J push raised {exc!r}")
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    # O — a declared client rule document is swept recursively before admission.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        _setup(base, qc=GOOD_QC, media=_media(Path(t)), job={"has_ghl": True})
        (base / "deliverables" / "nested").mkdir(parents=True)
        (base / "deliverables" / "nested" / "page.html").write_text(
            "<p>a world-class world-class result</p>", encoding="utf-8")
        (base / "client_rules.json").write_text(json.dumps({
            "schema": "signature-launch-client-rules/v1", "client_id": "client-1",
            "rules": [{"id": "phrase", "kind": "banned_phrase",
                       "values": ["world-class"]}]}))
        ok, r = _gate(base)
        if ok or not any("client rule 'phrase'" in x for x in r):
            fails.append(f"O client-rules: expected FAIL, got ok={ok} {r}")

    after = []
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        _setup(base, qc=GOOD_QC, media=_media(Path(t)), job={"has_ghl": True})
        ok, r = _gate(base)
        if not ok:
            after.append(f"post-change gate: {r}")
    if after:
        fails.extend(after)

    if fails:
        print("graphics_ghl_push gate selftest -> FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("graphics_ghl_push gate selftest -> PASS (complete/empty/missing-upload/"
          "null-folder/incomplete/agent-skip/verified-waiver/local-token/false-token/"
          "no-passed + negative controls same-session/no-review + prior-attempt/"
          "changed-bytes + end-to-end push-hosts-passed-only/idempotent/gate-passes + "
          "approval-record refusals + liveness-evidence html200/png/no-header)")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    sys.exit(main())
