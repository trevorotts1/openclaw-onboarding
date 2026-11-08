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
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    import fcntl  # ponytail: POSIX lock; without it the ledger is still atomic, just not serialised
except ImportError:  # pragma: no cover - Windows
    fcntl = None

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


def _asset_path(job_dir: Path, asset: dict) -> Path:
    rel = _asset_key(asset)
    return Path(rel) if Path(rel).is_absolute() else Path(job_dir) / rel


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def content_key(location_id: str, sha256: str) -> str:
    """The scoped content identity an upload is deduplicated and reconciled by.

    NEVER a path or a basename: the same bytes under two names are one upload, and
    different bytes under the SAME pathname are two uploads.
    """
    return f"{str(location_id or '').strip()}|{str(sha256 or '').strip()}"


def atomic_write_json(path: Path, data) -> None:
    """One JSON file, written so a crash can never leave it half-written."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(data, indent=2, sort_keys=True) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _ledger_update(job_dir: Path, edit) -> dict:
    """Read-modify-write the ledger under an exclusive lock and an atomic replace.

    Every accepted upload is persisted through here BEFORE the loop advances, so a
    crash leaves a receipt for each remote file that already exists.
    """
    job_dir = Path(job_dir)
    path = _ledger_path(job_dir)
    lock = path.with_suffix(path.suffix + ".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock, "a+", encoding="utf-8") as fh:
        if fcntl:
            fcntl.flock(fh, fcntl.LOCK_EX)
        data = _read_json(path) if path.exists() else {}
        if not isinstance(data, dict):
            data = {}
        edit(data)
        atomic_write_json(path, data)
        return data


def verified_passed_assets(job_dir) -> tuple[list, list]:
    """(assets, problems): the QC-PASSED assets whose LOCAL BYTES are verified now.

    A QC report's `pass:true` is a claim; the file must exist, be a regular readable file
    and, when the record carries a sha256, still hash to it. The verified digest is bound
    into the asset record so nothing downstream can host a different image.
    """
    job_dir = Path(job_dir)
    assets, problems = [], []
    for asset in collect_passed_assets(job_dir):
        rel = _asset_key(asset)
        path = _asset_path(job_dir, asset)
        if not path.is_file():
            problems.append(f"QC-passed asset {rel!r} is not on disk at {path}")
            continue
        try:
            digest = sha256_file(path)
        except OSError as exc:
            problems.append(f"QC-passed asset {rel!r} is unreadable ({exc})")
            continue
        declared = str(asset.get("sha256") or asset.get("sha_256") or "").strip().lower()
        if declared and declared != digest:
            problems.append(f"QC-passed asset {rel!r} hashes to {digest[:12]} but the QC record "
                            f"declares {declared[:12]}; the bytes changed after QC")
            continue
        assets.append(dict(asset, _path=str(path), _sha256=digest))
    return assets, problems


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
def _remote_entries(location_id, pit, *, media_type, parent_id, query, opener=None) -> list:
    try:
        return ghl_media.list_media(location_id, pit, media_type=media_type,
                                    parent_id=parent_id, query=query, opener=opener).get("data") or []
    except (RuntimeError, ValueError, OSError):
        return []


def _find_remote_folder(location_id, pit, name, opener=None):
    """An interrupted folder create: adopt the SAME folder instead of making a second one."""
    for entry in _remote_entries(location_id, pit, media_type="folder", parent_id=None,
                                 query=name, opener=opener):
        if isinstance(entry, dict) and str(entry.get("name") or "").strip() == name:
            return str(entry.get("id") or entry.get("_id") or entry.get("folderId") or "") or None
    return None


def _find_remote_file(location_id, pit, name, parent_id, opener=None):
    """An interrupted upload: adopt the remote file the API already holds, never re-post."""
    for entry in _remote_entries(location_id, pit, media_type="file", parent_id=parent_id,
                                 query=name, opener=opener):
        if not isinstance(entry, dict) or str(entry.get("name") or "").strip() != name:
            continue
        file_id = str(entry.get("fileId") or entry.get("_id") or entry.get("id") or "")
        url = str(entry.get("url") or entry.get("link") or "")
        if file_id and url:
            return {"fileId": file_id, "url": url}
    return None


def _upsert_row(ledger: dict, row: dict) -> None:
    rows = [r for r in (ledger.get("uploaded") or [])
            if isinstance(r, dict) and r.get("upload_key") != row.get("upload_key")]
    rows.append(row)
    rows.sort(key=lambda r: str(r.get("upload_key") or r.get("local_path") or ""))
    ledger["uploaded"] = rows
    ledger["upload_count"] = len([r for r in rows
                                  if str(r.get("ghl_upload_status") or "").lower() == "complete"])


def _row_for(job_dir: Path, key: str) -> dict:
    for row in (_read_json(_ledger_path(job_dir)).get("uploaded") or []):
        if isinstance(row, dict) and row.get("upload_key") == key:
            return row
    return {}


def _resolve_folder(job_dir, fname, slug, location_id, pit, opener) -> dict:
    """Create the per-job folder ONCE: a recorded id is reused, and an interrupted create is
    reconciled against the media library BEFORE another folder is made."""
    ledger = _read_json(_ledger_path(job_dir))
    recorded = str(ledger.get("ghl_folder_id") or "").strip()
    if recorded:
        return {"folderId": None if recorded == "root" else recorded,
                "name": ledger.get("ghl_folder_name") or fname, "reused": True}
    intent = ledger.get("folder_intent") if isinstance(ledger.get("folder_intent"), dict) else {}
    if intent.get("name") == fname and intent.get("location_id") == location_id:
        found = _find_remote_folder(location_id, pit, fname, opener)
        if found:
            _ledger_update(job_dir, lambda d: d.update({
                "ghl_folder_id": found, "ghl_folder_name": fname,
                "ghl_folder_created_via_api": True, "folder_reconciled": True}))
            return {"folderId": found, "name": fname, "reconciled": True}
    _ledger_update(job_dir, lambda d: d.update({
        "folder_intent": {"name": fname, "location_id": location_id, "at": _now_iso()}}))
    folder = ghl_media.create_media_folder(fname, location_id, pit, opener=opener)
    return folder


def _reconcile_pending_uploads(job_dir, location_id, pit, parent_id, opener, liveness_opener) -> list:
    """Before ANY new upload: resolve rows a crash left `pending`/`uncertain` against the remote
    library and persist the outcome, so a re-run never double-posts the same bytes."""
    rows = [r for r in (_read_json(_ledger_path(job_dir)).get("uploaded") or [])
            if isinstance(r, dict)
            and str(r.get("ghl_upload_status") or "").lower() in ("pending", "uncertain")]
    outcomes = []
    for row in rows:
        found = _find_remote_file(location_id, pit, row.get("name"), parent_id, opener)
        key = row.get("upload_key")

        def settle(d, key=key, found=found, row=row):
            rows_now = [r for r in (d.get("uploaded") or []) if isinstance(r, dict)]
            for r in rows_now:
                if r.get("upload_key") != key:
                    continue
                if found:
                    live = _url_live(found["url"], opener=liveness_opener)
                    r.update(ghl_media_id=found["fileId"], file_id=found["fileId"],
                             remote_media_id=found["fileId"], public_url=found["url"],
                             ghl_public_url=found["url"], final_url=found["url"],
                             ghl_upload_status="complete", liveness=live,
                             reconciled_at=_now_iso())
                else:
                    r.update(ghl_upload_status="not_accepted", reconciled_at=_now_iso())
            d["uploaded"] = rows_now
            d["upload_count"] = len([r for r in rows_now
                                     if str(r.get("ghl_upload_status") or "").lower() == "complete"])
        _ledger_update(job_dir, settle)
        outcomes.append({"upload_key": key, "name": row.get("name"),
                         "state": "complete" if found else "not_accepted"})
    return outcomes


def push_graphics_media(job_dir, *, folder_name: str | None = None, job_slug: str | None = None,
                        opener=None, liveness_opener=None, approval_ref=None,
                        approval_store: str | None = None) -> dict:
    """Create the per-job GHL folder and upload every QC-PASSED asset. Writes the gate-readable
    ledger to <job>/media_library.json and returns the same dict.

    Hash-aware and recoverable: every receipt binds the asset's SHA-256, the tenant location,
    the page/slot, the verified folder, the remote media id and the final URL; receipts are
    persisted one at a time, atomically, BEFORE the loop advances; uploads are deduplicated by
    scoped content identity (never by path or basename); and a partial or uncertain remote
    acceptance left by an interruption is reconciled before another upload or folder is made.

    REFUSES (PublishApprovalError, a RuntimeError) unless ``approval_ref`` resolves to a
    launcher approval record for the client's location (see _load_publish_approval)."""
    job_dir = Path(job_dir).resolve()
    # Approval first: nothing is read, created or uploaded without the record.
    _load_publish_approval().require_live_write(
        approval_ref, location_id=ghl_media.resolve_location_id(), store_dir=approval_store)
    slug = (job_slug or job_dir.name).strip()
    fname = (folder_name or f"GRAPHICS {slug}").strip()

    passed, problems = verified_passed_assets(job_dir)
    if problems:
        raise RuntimeError(f"{GHL_UPLOAD_GATE}: " + "; ".join(problems))
    if not passed:
        raise RuntimeError(
            f"{GHL_UPLOAD_GATE}: no QC-PASSED assets in {_qc_report_path(job_dir)} — nothing to "
            "host. Run SOP-GIP-02 image QC first (only pass:true + zero auto-fails are delivered).")

    pit = ghl_media.resolve_location_pit()         # client's LOCATION PIT (never operator's)
    location_id = ghl_media.resolve_location_id()   # client's location id

    folder = _resolve_folder(job_dir, fname, slug, location_id, pit, opener)
    parent_id = folder.get("folderId")
    name_prefix = "" if parent_id else f"{slug} — "
    ghl_folder_id = parent_id or "root"

    reconciled = _reconcile_pending_uploads(job_dir, location_id, pit, parent_id, opener,
                                            liveness_opener)

    for asset in passed:
        key = content_key(location_id, asset["_sha256"])
        row = _row_for(job_dir, key)
        if str(row.get("ghl_upload_status") or "").lower() == "complete":
            continue  # these exact bytes, in this tenant, are already hosted
        name = f"{name_prefix}{Path(asset['_path']).name}"
        intent = {
            "upload_key": key, "local_path": asset["_path"], "sha256": asset["_sha256"],
            "location_id": location_id, "ghl_folder_id": ghl_folder_id, "name": name,
            "ghl_remote_name": name, "page": asset.get("page"),
            "slot": asset.get("slot") or asset.get("asset_id"),
            "asset_id": asset.get("asset_id") or Path(asset["_path"]).stem,
            "ghl_upload_status": "pending", "attempted_at": _now_iso(),
        }
        # The INTENT is persisted before the POST: a crash mid-upload leaves a row to reconcile.
        _ledger_update(job_dir, lambda d, row=intent: _upsert_row(d, row))
        res = ghl_media.upload_media(
            asset["_path"], location_id, name, pit,
            parent_id=parent_id, opener=opener, require_png=_is_png(asset["_path"]))
        live = _url_live(res["url"], opener=liveness_opener)
        _update_sidecar(job_dir, asset, res["fileId"], res["url"])
        receipt = dict(intent, ghl_upload_status="complete",
                       file_id=res["fileId"], ghl_media_id=res["fileId"],
                       remote_media_id=res["fileId"], public_url=res["url"],
                       ghl_public_url=res["url"], final_url=res["url"],
                       http_status=res["http"],
                       # F17: the hosting binding reads content_type at the TOP level of the row,
                       # so the observed header is recorded beside the liveness evidence.
                       content_type=live.get("content_type"),
                       liveness=live, uploaded_at=_now_iso())
        # The RECEIPT is persisted, atomically, BEFORE the next upload is attempted.
        _ledger_update(job_dir, lambda d, row=receipt: _upsert_row(d, row))

    ledger = _read_json(_ledger_path(job_dir))
    out = {
        "job_slug": slug,
        "location_id": location_id,
        "ghl_folder_id": ghl_folder_id,
        "ghl_folder_name": folder.get("name") or ledger.get("ghl_folder_name") or fname,
        "ghl_folder_created_via_api": bool(folder.get("folderId")),
        "uploaded": list(ledger.get("uploaded") or []),
        "upload_count": len([r for r in (ledger.get("uploaded") or [])
                             if str(r.get("ghl_upload_status") or "").lower() == "complete"]),
        "passed_asset_count": len(passed),
        "reconciled": reconciled,
    }
    _ledger_update(job_dir, lambda d: d.update(out))
    return out


# ---------------------------------------------------------------------------
# CLOSEOUT GATE — no delivery without the GHL upload.
# ---------------------------------------------------------------------------
def _valid_owner_skip(job_dir: Path):
    """Return the owner-skip record authorizing a gate skip, or None. The ONLY legitimate
    skip: a LOGGED token in <job>/checkpoints/process_manifest.json under owner_skip_approval
    (owner_approved:true + non-empty approved_by + non-empty reason + a matching gate name).
    An agent's own has_ghl:false is NOT a skip."""
    pm = _read_json(Path(job_dir) / "checkpoints" / "process_manifest.json")
    raw = pm.get("owner_skip_approval") if isinstance(pm, dict) else None
    if raw is None:
        return None
    records = raw if isinstance(raw, list) else [raw]
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
        if gate in _GATE_ALIASES:
            return rec
    return None


def _job_has_ghl(job_dir: Path):
    """Return the has_ghl flag from <job>/job.json or <job>/intake.json (None when unset)."""
    for fn in ("job.json", "intake.json"):
        data = _read_json(Path(job_dir) / fn)
        if isinstance(data, dict) and "has_ghl" in data:
            return data.get("has_ghl")
    return None


def _upload_complete(entry: dict) -> bool:
    """Complete means complete: an unknown or missing status is NOT a hosted file."""
    if str(entry.get("ghl_upload_status") or "").strip().lower() != "complete":
        return False
    if not str(entry.get("ghl_media_id") or entry.get("file_id") or entry.get("remote_media_id") or "").strip():
        return False
    return bool(str(entry.get("ghl_public_url") or entry.get("public_url") or entry.get("final_url") or "").strip())


def gate_graphics_media_complete(job_dir):
    """HARD closeout gate. Returns (ok: bool, reasons: list[str]).

    PASS only when <job>/media_library.json records a resolved ghl_folder_id AND every
    QC-PASSED asset (from the SOP-GIP-02 report _qc_report_path resolves) is uploaded with a real ghl_media_id
    + ghl_upload_status:"complete" — OR a logged owner_skip_approval authorizes the skip. There
    is NO defer-to-pass."""
    job_dir = Path(job_dir)

    # The ONLY skip path: an explicit, logged owner/founder approval token.
    if _valid_owner_skip(job_dir) is not None:
        return True, []

    # has_ghl:false WITHOUT an owner token is an agent choice, not an authorization.
    if _job_has_ghl(job_dir) is False:
        return False, [
            f"{GHL_UPLOAD_GATE}: job.json/intake.json has_ghl:false but no logged "
            "owner_skip_approval in checkpoints/process_manifest.json. The GHL media-upload gate "
            "may be skipped ONLY by an explicit owner/founder token (owner_approved:true + "
            "approved_by + reason + gate). An agent cannot opt out of the upload on its own."]

    passed, problems = verified_passed_assets(job_dir)
    media = _read_json(_ledger_path(job_dir))

    if problems:
        return False, [f"{GHL_UPLOAD_GATE}: {p}" for p in problems]

    if not passed:
        return False, [
            f"{GHL_UPLOAD_GATE}: no QC-PASSED assets found in {_qc_report_path(job_dir)} — run "
            "SOP-GIP-02 image QC first; a job with nothing that passed QC has nothing to deliver."]

    if not media:
        return False, [
            f"{GHL_UPLOAD_GATE}: <job>/media_library.json is missing/empty — no GHL upload record "
            "at all (folder + per-asset uploads). No finished graphics asset ships without the GHL "
            "media upload."]

    reasons = []

    # (1) per-job folder resolved (a real id OR the 'root' fallback; null seed fails).
    folder = str(media.get("ghl_folder_id") or "").strip()
    if not folder:
        reasons.append(
            f"{GHL_UPLOAD_GATE}: ghl_folder_id is null/empty — the per-job GHL media folder was "
            "never resolved (create_media_folder, or the 'root' fallback).")

    # (2) every QC-passed asset uploaded with a real ghl_media_id + status complete, matched by
    #     scoped CONTENT identity (tenant + sha256). No basename fallback: a record for a
    #     different image that happens to share a filename never satisfies this asset.
    location_id = str(media.get("location_id") or "").strip()
    rows = [e for e in media.get("uploaded", []) if isinstance(e, dict)]
    by_key, by_sha, by_path = {}, {}, {}
    for entry in rows:
        sha = str(entry.get("sha256") or "").strip()
        key = entry.get("upload_key") or (content_key(entry.get("location_id") or location_id, sha)
                                          if sha else "")
        if key:
            by_key[key] = entry
        if sha:
            by_sha.setdefault(sha, []).append(entry)
        lp = str(entry.get("local_path") or "")
        if lp:
            by_path[lp] = entry
            by_path[str(Path(lp))] = entry

    for a in passed:
        sha = a["_sha256"]
        rec = by_key.get(content_key(location_id, sha)) if location_id else None
        if rec is None:
            for candidate in by_sha.get(sha, []):
                row_loc = str(candidate.get("location_id") or "").strip()
                if location_id and row_loc and row_loc != location_id:
                    continue  # another tenant's copy of these bytes is not this location's upload
                rec = candidate
                break
        if rec is None:
            rec = by_path.get(a["_path"]) or by_path.get(_asset_key(a))
            if rec is not None and str(rec.get("sha256") or "").strip() not in ("", sha):
                rec = None  # same pathname, different bytes: NOT this asset
        rel = _asset_key(a)
        if rec is None:
            reasons.append(
                f"{GHL_UPLOAD_GATE}: QC-passed asset {rel!r} (sha256 {sha[:12]}) has NO upload "
                "record in media_library.json for this tenant — every passed asset must be hosted "
                "with a real ghl_media_id.")
        elif not _upload_complete(rec):
            reasons.append(
                f"{GHL_UPLOAD_GATE}: upload for {rel!r} is not complete (status "
                f"{rec.get('ghl_upload_status')!r}; a complete upload carries a media id and a "
                "public URL).")

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
    import os
    import tempfile
    fails = []

    # A real 1x1 PNG: the bytes that must decode as image evidence, never a magic-byte stub.
    PNG_BYTES = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f"
                 b"\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x9a\xa0\xa0\x00\x00"
                 b"\x00\x00IEND\xaeB`\x82")

    def _setup(base, *, qc=None, media=None, pm=None, job=None, files=True):
        (base / "qc").mkdir(parents=True, exist_ok=True)
        (base / "checkpoints").mkdir(parents=True, exist_ok=True)
        if files:
            (base / "renders").mkdir(parents=True, exist_ok=True)
            for name in ("ad-01.png", "ad-02.png", "ad-03.png"):
                (base / "renders" / name).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64 + name.encode())
        if qc is not None:
            (base / "qc" / "image_qc_report.json").write_text(json.dumps(qc))
        if media is not None:
            (base / "media_library.json").write_text(json.dumps(media))
        if pm is not None:
            (base / "checkpoints" / "process_manifest.json").write_text(json.dumps(pm))
        if job is not None:
            (base / "job.json").write_text(json.dumps(job))

    def _mock_http(listing=None, uploads=None):
        """A request-level fake for the canonical GHL media module: one folder, one file per POST."""
        state = {"uploads": 0, "folders": 0, "posted": []}

        class _R:
            def __init__(self, payload):
                self._p = payload

            def getcode(self):
                return 200

            def read(self):
                return self._p

        def opener(req, timeout):
            url, method = req.full_url, req.get_method()
            if method == "GET":
                return _R(json.dumps({"data": list(listing or [])}).encode())
            if "/medias/folder" in url:
                state["folders"] += 1
                return _R(json.dumps({"id": "fld_1"}).encode())
            state["uploads"] += 1
            state["posted"].append(url)
            if uploads and state["uploads"] > uploads:
                raise RuntimeError("simulated transport failure after the first upload")
            return _R(json.dumps({"fileId": f"m{state['uploads']}",
                                  "url": f"https://cdn.test/m{state['uploads']}"}).encode())

        return opener, state

    def _live(url, timeout):
        class _R:
            def getcode(self):
                return 200

            def read(self):
                return b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
        return _R()

    def _sha(base, rel):
        return sha256_file(Path(base) / rel)

    GOOD_QC = {"gate": "AF-G-IMAGE-QC", "pass": True, "assets": [
        {"local_path": "renders/ad-01.png", "asset_id": "ad-01", "pass": True, "triggered_autofails": []},
        {"local_path": "renders/ad-02.png", "asset_id": "ad-02", "pass": True, "triggered_autofails": []},
        {"local_path": "renders/ad-03.png", "asset_id": "ad-03", "pass": False, "triggered_autofails": ["AF-G1"]},
    ]}
    GOOD_MEDIA = {"ghl_folder_id": "fld_1", "location_id": "loc-fixture", "uploaded": [
        {"local_path": "renders/ad-01.png", "asset_id": "ad-01", "ghl_media_id": "m1",
         "ghl_public_url": "https://cdn.test/m1", "ghl_upload_status": "complete",
         "location_id": "loc-fixture"},
        {"local_path": "renders/ad-02.png", "asset_id": "ad-02", "ghl_media_id": "m2",
         "ghl_public_url": "https://cdn.test/m2", "ghl_upload_status": "complete",
         "location_id": "loc-fixture"},
    ]}

    # A — both passed assets uploaded (the failed one is NOT required) -> PASS.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t); _setup(base, qc=GOOD_QC, media=GOOD_MEDIA, job={"has_ghl": True})
        ok, r = gate_graphics_media_complete(base)
        if not ok:
            fails.append(f"A complete: expected PASS, got {r}")

    # B — empty ledger -> FAIL.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t); _setup(base, qc=GOOD_QC, media={}, job={"has_ghl": True})
        ok, r = gate_graphics_media_complete(base)
        if ok or not any("missing/empty" in x for x in r):
            fails.append(f"B empty: expected FAIL, got ok={ok} {r}")

    # C — one passed asset NOT uploaded -> FAIL.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        m = {"ghl_folder_id": "root", "uploaded": [GOOD_MEDIA["uploaded"][0]]}
        _setup(base, qc=GOOD_QC, media=m, job={"has_ghl": True})
        ok, r = gate_graphics_media_complete(base)
        if ok or not any("NO upload record" in x for x in r):
            fails.append(f"C missing-upload: expected FAIL, got ok={ok} {r}")

    # D — null folder id -> FAIL.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        m = dict(GOOD_MEDIA); m["ghl_folder_id"] = None
        _setup(base, qc=GOOD_QC, media=m, job={"has_ghl": True})
        ok, r = gate_graphics_media_complete(base)
        if ok or not any("ghl_folder_id" in x for x in r):
            fails.append(f"D null-folder: expected FAIL, got ok={ok} {r}")

    # E — an upload marked pending -> FAIL (incomplete).
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        m = {"ghl_folder_id": "root", "uploaded": [
            GOOD_MEDIA["uploaded"][0],
            {"local_path": "renders/ad-02.png", "asset_id": "ad-02", "ghl_upload_status": "pending"}]}
        _setup(base, qc=GOOD_QC, media=m, job={"has_ghl": True})
        ok, r = gate_graphics_media_complete(base)
        if ok or not any("not complete" in x for x in r):
            fails.append(f"E incomplete: expected FAIL, got ok={ok} {r}")

    # F — has_ghl:false with NO owner token -> FAIL (agent cannot opt out).
    with tempfile.TemporaryDirectory() as t:
        base = Path(t); _setup(base, qc=GOOD_QC, media={}, job={"has_ghl": False})
        ok, r = gate_graphics_media_complete(base)
        if ok or not any("owner_skip_approval" in x for x in r):
            fails.append(f"F agent-skip: expected owner-token FAIL, got ok={ok} {r}")

    # G — has_ghl:false WITH a valid logged owner skip -> PASS (carve-out).
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        _setup(base, qc=GOOD_QC, media={}, job={"has_ghl": False},
               pm={"owner_skip_approval": {"owner_approved": True, "approved_by": "owner",
                                           "reason": "client has no GHL account",
                                           "gate": "AF-DELIVERY-COMPLETE"}})
        ok, r = gate_graphics_media_complete(base)
        if not ok:
            fails.append(f"G owner-skip: expected PASS, got {r}")

    # H — owner skip with owner_approved:false -> NOT a skip -> FAIL.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        _setup(base, qc=GOOD_QC, media={}, job={"has_ghl": True},
               pm={"owner_skip_approval": {"owner_approved": False, "approved_by": "x",
                                           "reason": "y", "gate": "AF-DELIVERY-COMPLETE"}})
        ok, r = gate_graphics_media_complete(base)
        if ok:
            fails.append(f"H false-token: expected FAIL, got ok={ok} {r}")

    # I — no QC-passed assets at all -> FAIL.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        _setup(base, qc={"pass": False, "assets": [
            {"local_path": "renders/x.png", "pass": False, "triggered_autofails": ["AF-G1"]}]},
               media={}, job={"has_ghl": True})
        ok, r = gate_graphics_media_complete(base)
        if ok or not any("nothing that passed QC" in x or "no QC-PASSED" in x.lower() for x in r):
            fails.append(f"I no-passed: expected FAIL, got ok={ok} {r}")

    # J — END-TO-END push_graphics_media over a mock HTTP opener HOSTS both passed assets and
    #     the resulting ledger PASSES the gate; the QC-failed asset is NOT hosted.
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

    # L — the liveness record is EVIDENCE, not merely a 200. An HTML login page answers 200 with
    #     text/html and its bytes decode as no image; a real PNG records image/png and its size.
    class _Resp:
        def __init__(self, body, ctype):
            self._body, self.headers = body, {"Content-Type": ctype}

        def getcode(self):
            return 200

        def read(self):
            return self._body

    html = _url_live("https://host.test/a.png",
                     opener=lambda u, t: _Resp(b"<!doctype html><body>Sign in to continue", "text/html; charset=utf-8"))
    if (not html["live"] or html.get("content_type") != "text/html; charset=utf-8"
            or html["image"]["decodes"] or html["image"]["format"]):
        fails.append(f"L html200: expected a live 200 recording text/html and no image decode, got {html}")
    png = _url_live("https://host.test/b.png", opener=lambda u, t: _Resp(PNG_BYTES, "image/png"))
    if (png.get("content_type") != "image/png" or png["image"]["decodes"] is not True
            or (png["image"]["width"], png["image"]["height"]) != (1, 1)):
        fails.append(f"L png: expected image/png with decoded 1x1 evidence, got {png}")
    missing = _url_live("https://host.test/c.png", opener=lambda u, t: _Resp(PNG_BYTES, ""))
    if missing.get("content_type") is not None:
        fails.append(f"L no-header: expected content_type None (never invented), got {missing}")

    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        (base / "renders").mkdir(parents=True, exist_ok=True)
        for n in ("ad-01.png", "ad-02.png", "ad-03.png"):
            (base / "renders" / n).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
        _setup(base, qc=GOOD_QC, job={"has_ghl": True})
        saved = {k: os.environ.get(k) for k in ("GHL_API_KEY", "GHL_LOCATION_ID")}
        os.environ["GHL_API_KEY"] = "pit-0f3a9c1e-7b2d-4e65-9a18-c4d2b6e8f0a1"  # real-shaped (the resolver skips placeholder-shaped values)
        os.environ["GHL_LOCATION_ID"] = "loc-fixture"
        try:
            store = base / "approval-store"
            store.mkdir()

            def _put(ref, **over):
                rec = {"approval_ref": ref, "allowed_write_target": "approved_live_publication",
                       "test_only": False, "location_id": "loc-fixture", "page_ids": []}
                rec.update(over)
                (store / f"{ref}.json").write_text(json.dumps(rec))

            # K — no record / free string / test_only record -> the push is REFUSED and nothing
            #     is uploaded (S06-06: the same record Skill 6 needs to publish).
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
            ok, r = gate_graphics_media_complete(base)
            if not ok:
                fails.append(f"J push->gate: expected PASS after hosting, got {r}")
            # idempotent re-run does not double-upload.
            out2 = push_graphics_media(base, **kw)
            if out2.get("upload_count") != 2:
                fails.append(f"J idempotent: re-run changed upload_count to {out2.get('upload_count')}")
        except Exception as exc:  # noqa: BLE001
            fails.append(f"J push raised {exc!r}")
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    # E2 — an UNKNOWN completion status is not complete either.
    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        m = {"ghl_folder_id": "root", "uploaded": [
            {"local_path": "renders/ad-01.png", "ghl_media_id": "m1", "ghl_upload_status": "complete"},
            {"local_path": "renders/ad-02.png", "ghl_media_id": "m2", "ghl_upload_status": "weird"}]}
        _setup(base, qc=GOOD_QC, media=m, job={"has_ghl": True})
        ok, r = gate_graphics_media_complete(base)
        if ok or not any("not complete" in x for x in r):
            fails.append(f"E2 unknown-status: expected FAIL, got ok={ok} {r}")

    # ---- hash-aware / recoverable hosting (F21 step 8) ----
    saved_env = {k: os.environ.get(k) for k in ("GHL_API_KEY", "GHL_LOCATION_ID")}
    os.environ["GHL_API_KEY"] = "pit-0f3a9c1e-7b2d-4e65-9a18-c4d2b6e8f0a1"
    os.environ["GHL_LOCATION_ID"] = "loc-fixture"

    def _approve(base):
        store = base / "approval-store"
        store.mkdir(exist_ok=True)
        (store / "APPR-LIVE.json").write_text(json.dumps({
            "approval_ref": "APPR-LIVE", "allowed_write_target": "approved_live_publication",
            "test_only": False, "location_id": "loc-fixture", "page_ids": []}))
        return str(store)

    try:
        # K — the SAME pathname with DIFFERENT bytes is a different asset: hosted again.
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            _setup(base, qc=GOOD_QC, job={"has_ghl": True})
            opener, state = _mock_http()
            kw = dict(opener=opener, liveness_opener=_live, approval_ref="APPR-LIVE",
                      approval_store=_approve(base))
            push_graphics_media(base, **kw)
            first = state["uploads"]
            (base / "renders" / "ad-01.png").write_bytes(
                b"\x89PNG\r\n\x1a\n" + b"\x01" * 64 + b"replaced-bytes")
            push_graphics_media(base, **kw)
            if state["uploads"] <= first:
                fails.append("K pathname: different bytes at the same pathname were NOT hosted "
                             "(deduplicated by path, not content)")

        # L — the SAME bytes under a different pathname are one asset: never hosted twice.
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            (base / "renders").mkdir(parents=True)
            (base / "renders" / "ad-01.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64 + b"one")
            (base / "renders" / "ad-02.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64 + b"two")
            (base / "renders" / "copy-of-two.png").write_bytes(
                (base / "renders" / "ad-02.png").read_bytes())
            qc = {"gate": "AF-G-IMAGE-QC", "pass": True, "assets": [
                {"local_path": "renders/ad-01.png", "asset_id": "ad-01", "pass": True,
                 "triggered_autofails": []},
                {"local_path": "renders/ad-02.png", "asset_id": "ad-02", "pass": True,
                 "triggered_autofails": []},
                {"local_path": "renders/copy-of-two.png", "asset_id": "dup", "pass": True,
                 "triggered_autofails": []}]}
            _setup(base, qc=qc, job={"has_ghl": True}, files=False)
            opener, state = _mock_http()
            push_graphics_media(base, opener=opener, liveness_opener=_live,
                                approval_ref="APPR-LIVE", approval_store=_approve(base))
            if state["uploads"] != 2:
                fails.append(f"L content-dedup: expected 2 uploads for 2 distinct byte streams, "
                             f"got {state['uploads']}")

        # M — each receipt is persisted BEFORE the loop advances (a crash keeps it).
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            _setup(base, qc=GOOD_QC, job={"has_ghl": True})
            opener, state = _mock_http(uploads=1)
            try:
                push_graphics_media(base, opener=opener, liveness_opener=_live,
                                    approval_ref="APPR-LIVE", approval_store=_approve(base))
                fails.append("M receipt: the simulated transport failure was swallowed")
            except RuntimeError:
                pass
            rows = _read_json(base / "media_library.json").get("uploaded") or []
            complete = [r for r in rows if r.get("ghl_upload_status") == "complete"]
            pending = [r for r in rows if r.get("ghl_upload_status") == "pending"]
            if len(complete) != 1:
                fails.append(f"M receipt: {len(complete)} receipts persisted before the crash, "
                             "expected the first upload's receipt")
            if len(pending) != 1:
                fails.append("M intent: the interrupted upload left no pending row to reconcile")

        # N — a pending row is reconciled against the library, never re-posted.
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            _setup(base, qc=GOOD_QC, job={"has_ghl": True})
            key = content_key("loc-fixture", "a" * 64)
            atomic_write_json(base / "media_library.json", {
                "ghl_folder_id": "fld_1", "location_id": "loc-fixture",
                "uploaded": [{"upload_key": key, "name": "ad-01.png", "sha256": "a" * 64,
                              "local_path": "renders/ad-01.png", "ghl_upload_status": "pending"}]})
            opener, state = _mock_http(listing=[{"name": "ad-01.png", "fileId": "m-existing",
                                                 "url": "https://cdn.test/m-existing"}])
            _reconcile_pending_uploads(base, "loc-fixture", "pit-x", "fld_1", opener, _live)
            row = (_read_json(base / "media_library.json").get("uploaded") or [{}])[0]
            if state["uploads"] != 0:
                fails.append("N reconcile: a NEW upload was posted instead of adopting the remote file")
            if row.get("ghl_media_id") != "m-existing" or row.get("ghl_upload_status") != "complete":
                fails.append(f"N reconcile: the pending row resolved to {row!r}")

        # O — a record for the same BASENAME elsewhere does not satisfy the asset.
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            _setup(base, qc=GOOD_QC, job={"has_ghl": True})
            real = _sha(base, "renders/ad-02.png")
            m = {"ghl_folder_id": "fld_1", "location_id": "loc-fixture", "uploaded": [
                {"local_path": "other/ad-01.png", "name": "ad-01.png", "ghl_media_id": "mX",
                 "ghl_public_url": "https://cdn.test/mX", "ghl_upload_status": "complete",
                 "location_id": "loc-fixture", "sha256": "d" * 64},
                {"local_path": "renders/ad-02.png", "name": "ad-02.png", "ghl_media_id": "m2",
                 "ghl_public_url": "https://cdn.test/m2", "ghl_upload_status": "complete",
                 "location_id": "loc-fixture", "sha256": real}]}
            _setup(base, qc=GOOD_QC, media=m, job={"has_ghl": True})
            ok, r = gate_graphics_media_complete(base)
            if ok or not any("NO upload record" in x for x in r):
                fails.append(f"O basename: a same-basename record in another folder satisfied the "
                             f"gate, got ok={ok} {r}")

        # P — a QC record whose declared sha does not match the bytes refuses the asset.
        with tempfile.TemporaryDirectory() as t:
            base = Path(t)
            qc = {"gate": "AF-G-IMAGE-QC", "pass": True, "assets": [
                {"local_path": "renders/ad-01.png", "asset_id": "ad-01", "pass": True,
                 "triggered_autofails": [], "sha256": "0" * 64}]}
            _setup(base, qc=qc, job={"has_ghl": True})
            ok, r = gate_graphics_media_complete(base)
            if ok or not any("hashes to" in x for x in r):
                fails.append(f"P sha: a QC record with a stale sha256 passed, got ok={ok} {r}")
            try:
                push_graphics_media(base, opener=_mock_http()[0], liveness_opener=_live,
                                    approval_ref="APPR-LIVE", approval_store=_approve(base))
                fails.append("P sha: the push hosted an asset whose bytes changed after QC")
            except RuntimeError:
                pass
    finally:
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    if fails:
        print("graphics_ghl_push gate selftest -> FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("graphics_ghl_push gate selftest -> PASS (cases: complete/empty/missing-upload/"
          "null-folder/incomplete/unknown-status/agent-skip/owner-skip/false-token/no-passed + "
          "end-to-end push-hosts-passed-only/idempotent/gate-passes + approval-record refusals + "
          "liveness-evidence html200/png/no-header + "
          "hash-aware hosting: different bytes at one pathname re-host, identical bytes under a "
          "different name do not, each receipt persisted before the loop advances, a pending row "
          "reconciled instead of re-posted, no basename fallback, stale QC sha refused)")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    sys.exit(main())
