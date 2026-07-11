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
  2. Uploads every QC-PASSED asset (reads <job>/qc/image_qc_report.json — only assets with
     pass:true and ZERO auto-fails) via ghl_media.upload_media (POST /medias/upload-file,
     multipart, parentId), recording {fileId, url} per asset to <job>/media_library.json AND,
     best-effort, into the Vault provenance sidecar (ghl_media_id + ghl_public_url).
  3. Post-upload LIVENESS check: GET the returned public URL, expect HTTP 200 with a non-empty
     body (the Vault's existing url-liveness law, asset-provenance-librarian.md SOP 9.2 step 3).

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
import importlib.util
import json
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


def _qc_report_path(job_dir: Path) -> Path:
    return Path(job_dir) / "qc" / "image_qc_report.json"


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
    """GET the returned public URL; expect HTTP 200 with a non-empty body (the Vault's
    url-liveness law). Returns {live: bool, http: int|None, bytes: int}. Never raises — a
    liveness failure is RECORDED (not fatal to the upload record), and surfaces in the ledger
    so the Vault/QC can flag it."""
    _opener = opener or (lambda u, t: urllib.request.urlopen(u, timeout=t))
    try:
        resp = _opener(url, timeout)
        code = int(resp.getcode())
        body = resp.read() or b""
        return {"live": (200 <= code < 300) and len(body) > 0, "http": code, "bytes": len(body)}
    except urllib.error.HTTPError as exc:  # noqa: PERF203
        return {"live": False, "http": int(getattr(exc, "code", 0)), "bytes": 0}
    except (urllib.error.URLError, OSError):
        return {"live": False, "http": None, "bytes": 0}


# ---------------------------------------------------------------------------
# push_graphics_media — create the per-job folder + upload every QC-passed asset.
# ---------------------------------------------------------------------------
def push_graphics_media(job_dir, *, folder_name: str | None = None, job_slug: str | None = None,
                        opener=None, liveness_opener=None) -> dict:
    """Create the per-job GHL folder and upload every QC-PASSED asset. Writes the gate-readable
    ledger to <job>/media_library.json (MERGED with any prior seed) and returns the same dict.
    Idempotent per file (a re-run never re-uploads an already-hosted asset)."""
    job_dir = Path(job_dir).resolve()
    slug = (job_slug or job_dir.name).strip()
    fname = (folder_name or f"GRAPHICS {slug}").strip()

    passed = collect_passed_assets(job_dir)
    if not passed:
        raise RuntimeError(
            f"{GHL_UPLOAD_GATE}: no QC-PASSED assets in {_qc_report_path(job_dir)} — nothing to "
            "host. Run SOP-GIP-02 image QC first (only pass:true + zero auto-fails are delivered).")

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
    done = {e.get("local_path"): e for e in ledger.get("uploaded", [])
            if isinstance(e, dict) and e.get("local_path")}
    uploaded = list(ledger.get("uploaded", []))

    for asset in passed:
        rel = _asset_key(asset)
        abspath = rel if Path(rel).is_absolute() else str(job_dir / rel)
        if abspath in done:
            continue  # idempotent: already hosted this file
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
            "ghl_upload_status": "complete",
            "ghl_folder_id": ghl_folder_id,
            "liveness": live,
            "uploaded_at": _now_iso(),
        }
        uploaded.append(rec)
        done[abspath] = rec

    out = {
        "job_slug": slug,
        "ghl_folder_id": ghl_folder_id,
        "ghl_folder_name": folder.get("name") or ledger.get("ghl_folder_name") or fname,
        "ghl_folder_created_via_api": bool(folder.get("folderId")),
        "uploaded": uploaded,
        "upload_count": len(uploaded),
        "passed_asset_count": len(passed),
    }
    ledger.update(out)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger, indent=2))
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
    mid = entry.get("ghl_media_id") or entry.get("file_id")
    if str(entry.get("ghl_upload_status", "")).lower() in ("failed", "pending"):
        return False
    return bool(str(mid or "").strip())


def gate_graphics_media_complete(job_dir):
    """HARD closeout gate. Returns (ok: bool, reasons: list[str]).

    PASS only when <job>/media_library.json records a resolved ghl_folder_id AND every
    QC-PASSED asset (from <job>/qc/image_qc_report.json) is uploaded with a real ghl_media_id
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

    reasons = []

    # (1) per-job folder resolved (a real id OR the 'root' fallback; null seed fails).
    folder = str(media.get("ghl_folder_id") or "").strip()
    if not folder:
        reasons.append(
            f"{GHL_UPLOAD_GATE}: ghl_folder_id is null/empty — the per-job GHL media folder was "
            "never resolved (create_media_folder, or the 'root' fallback).")

    # (2) every QC-passed asset uploaded with a real ghl_media_id + status complete.
    uploaded = {str(e.get("local_path") or ""): e for e in media.get("uploaded", [])
                if isinstance(e, dict)}
    # Also index by basename + asset_id so a job_dir-relative vs absolute path still matches.
    by_base = {}
    for e in media.get("uploaded", []):
        if isinstance(e, dict):
            lp = str(e.get("local_path") or "")
            if lp:
                by_base[Path(lp).name] = e
            if e.get("asset_id"):
                by_base[f"id:{e['asset_id']}"] = e

    for a in passed:
        rel = _asset_key(a)
        abspath = rel if Path(rel).is_absolute() else str(Path(job_dir).resolve() / rel)
        rec = (uploaded.get(abspath) or uploaded.get(rel)
               or by_base.get(Path(rel).name)
               or (by_base.get(f"id:{a.get('asset_id')}") if a.get("asset_id") else None))
        if rec is None:
            reasons.append(
                f"{GHL_UPLOAD_GATE}: QC-passed asset {rel!r} has NO upload record in "
                "media_library.json — every passed asset must be hosted with a real ghl_media_id.")
        elif not _upload_complete(rec):
            reasons.append(
                f"{GHL_UPLOAD_GATE}: upload for {rel!r} is not complete (no ghl_media_id or status "
                "failed/pending).")

    return (len(reasons) == 0), reasons


def main():
    ap = argparse.ArgumentParser(description="Host a graphics job's QC-passed assets in GHL, or "
                                             "run the GHL-upload closeout gate.")
    ap.add_argument("--job-dir", required=True)
    ap.add_argument("--folder-name", default=None,
                    help='per-job folder name, e.g. "<Client> Graphics <Job> v<N>".')
    ap.add_argument("--job-slug", default=None)
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
        res = push_graphics_media(job_dir, folder_name=args.folder_name, job_slug=args.job_slug)
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

    def _setup(base, *, qc=None, media=None, pm=None, job=None):
        (base / "qc").mkdir(parents=True, exist_ok=True)
        (base / "checkpoints").mkdir(parents=True, exist_ok=True)
        if qc is not None:
            (base / "qc" / "image_qc_report.json").write_text(json.dumps(qc))
        if media is not None:
            (base / "media_library.json").write_text(json.dumps(media))
        if pm is not None:
            (base / "checkpoints" / "process_manifest.json").write_text(json.dumps(pm))
        if job is not None:
            (base / "job.json").write_text(json.dumps(job))

    GOOD_QC = {"gate": "AF-G-IMAGE-QC", "pass": True, "assets": [
        {"local_path": "renders/ad-01.png", "asset_id": "ad-01", "pass": True, "triggered_autofails": []},
        {"local_path": "renders/ad-02.png", "asset_id": "ad-02", "pass": True, "triggered_autofails": []},
        {"local_path": "renders/ad-03.png", "asset_id": "ad-03", "pass": False, "triggered_autofails": ["AF-G1"]},
    ]}
    GOOD_MEDIA = {"ghl_folder_id": "fld_1", "uploaded": [
        {"local_path": "renders/ad-01.png", "asset_id": "ad-01", "ghl_media_id": "m1", "ghl_upload_status": "complete"},
        {"local_path": "renders/ad-02.png", "asset_id": "ad-02", "ghl_media_id": "m2", "ghl_upload_status": "complete"},
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
            def getcode(self):
                return 200

            def read(self):
                return b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
        return _R()

    with tempfile.TemporaryDirectory() as t:
        base = Path(t)
        (base / "renders").mkdir(parents=True, exist_ok=True)
        for n in ("ad-01.png", "ad-02.png", "ad-03.png"):
            (base / "renders" / n).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
        _setup(base, qc=GOOD_QC, job={"has_ghl": True})
        saved = {k: os.environ.get(k) for k in ("GHL_API_KEY", "GHL_LOCATION_ID")}
        os.environ["GHL_API_KEY"] = "pit-fixture"
        os.environ["GHL_LOCATION_ID"] = "loc-fixture"
        try:
            out = push_graphics_media(base, opener=_mock_opener, liveness_opener=_mock_live)
            if out.get("upload_count") != 2:
                fails.append(f"J push: expected 2 uploads (passed only), got {out.get('upload_count')}")
            ok, r = gate_graphics_media_complete(base)
            if not ok:
                fails.append(f"J push->gate: expected PASS after hosting, got {r}")
            # idempotent re-run does not double-upload.
            out2 = push_graphics_media(base, opener=_mock_opener, liveness_opener=_mock_live)
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

    if fails:
        print("graphics_ghl_push gate selftest -> FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("graphics_ghl_push gate selftest -> PASS (10 cases: complete/empty/missing-upload/"
          "null-folder/incomplete/agent-skip/owner-skip/false-token/no-passed + end-to-end "
          "push-hosts-passed-only/idempotent/gate-passes)")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    sys.exit(main())
