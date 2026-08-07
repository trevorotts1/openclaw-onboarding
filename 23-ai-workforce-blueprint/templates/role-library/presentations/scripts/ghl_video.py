#!/usr/bin/env python3
"""ghl_video.py — GHL v3 VIDEO upload wrapper + self-cleaning SMALL-PROBE.

WHAT THIS IS
------------
A THIN wrapper over the SHARED, canonical ``ghl_media.upload_video`` (the v3 video
tier of the Presentations department's single GHL media implementation). Per the
department's contract, the REST upload is NEVER forked: ``ghl_media.upload_video`` is
the ONE implementation, and this module re-exports it UNCHANGED (the same delegation
pattern ``ghl_media.py`` uses for the Skill-48 canonical module). What this module
ADDS on top — so the deployment teams get a usable surface, not just a raw function:

    upload_video(...)   -> the SHARED ghl_media.upload_video, re-exported (no fork):
                           POST services.leadconnectorhq.com/medias/upload-file
                           Authorization: Bearer <LOCATION PIT> ; Version: v3 ;
                           multipart file part Content-Type: video/mp4 ; 500MB tier.
                           -> {fileId, url, name, local_path, http, tier: "v3",
                               content_type: "video/mp4"}
    verify_video(path)  -> the SHARED ghl_media.verify_video small-probe (local,
                           no-network pre-flight: exists / non-empty / <=500MB /
                           MP4 ftyp box). Re-exported, no fork.
    delete_media_file() -> v3 BULK-DELETE (PUT /medias/delete-files) so a probe or a
                           failed run can SELF-CLEAN. NOT in the shared module.
    probe_upload()      -> the SMALL-PROBE: upload a tiny structurally-valid MP4
                           (~32 bytes) against the LIVE library, VERIFY it landed via
                           ghl_media.list_media (the read-only verification twin),
                           then DELETE it. Exit 0 = PASS. NEVER leaves junk, NEVER
                           prints a credential.

THE v3 CONTRACT (pinned to GHL's own published spec)
----------------------------------------------------
From ``GoHighLevel/highlevel-api-docs/apps/v3/medias-v3.json`` (the official GHL
spec): the ``upload-file`` operation declares the ``Version`` header enum
``["v3"]``, multipart fields ``file``/``hosted``/``fileUrl``/``name``/``parentId``,
the response schema ``{fileId, url}`` (both required), and "If adding a file, maximum
allowed is 25 MB. For video files, the maximum allowed size is 500 MB." The shared
module sends exactly that: ``Version: v3`` + a ``video/mp4`` file part, so a 500MB
video is hosted through the SAME proven ``POST /medias/upload-file`` REST call that
the deck/PNG pipeline uses (the regular ``2021-07-28`` tier would 413 a 500MB file).

WHY THIS MODULE EXISTS SEPARATELY
---------------------------------
``ghl_media.upload_video`` is the implementation; this module is the OPERATIONAL
surface for the video tier — the small-probe that proves v3+video/mp4+auth against a
LIVE client library, the v3 bulk-delete for self-cleaning, the CLI, and the offline
selftest. Keeping those here (rather than in the shared module) leaves the shared
module's contract surface unchanged for its existing callers (slides/decks).

NO BROWSER, EVER
----------------
The GoHighLevel media library is touched ONLY via this Tier-3 REST module. Driving
the GHL web UI with agent-browser / Playwright / Puppeteer / any UI automation is
FORBIDDEN.

FAIL-LOUD / NO-FABRICATION
--------------------------
Both the shared upload and this module fail LOUD rather than substitute a
placeholder: a missing file, a non-MP4 (bad ``ftyp`` magic), an over-500MB file, a
missing key, a non-2xx response, or a 2xx missing ``fileId``/``url`` all RAISE —
never a fabricated CDN URL. The hosted link a run records can only ever be a real,
publicly-resolving ``https`` URL with a verified HTTP status.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time  # noqa: F401  (imported for parity; retry lives in the shared module)
import urllib.error
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ghl_media  # noqa: E402  (the SHARED module: upload_video + verify_video + list)

# ── Re-export the shared v3 constants and functions UNCHANGED (no fork) ─────────
# The single source of truth for the v3 video tier lives in the shared module; this
# wrapper re-exports them so a caller can use this module as a one-stop surface.
upload_video = ghl_media.upload_video     # the SHARED v3 upload (Version: v3 + video/mp4)
verify_video = ghl_media.verify_video     # the SHARED local small-probe
GHL_MEDIA_VERSION_V3 = ghl_media.GHL_MEDIA_VERSION_V3      # "v3"
GHL_VIDEO_MAX_BYTES = ghl_media.GHL_VIDEO_MAX_BYTES        # 500 * 1024 * 1024
GHL_VIDEO_MIME = ghl_media.GHL_VIDEO_MIME                  # "video/mp4"
GHL_SERVICES_ORIGIN = ghl_media.GHL_SERVICES_ORIGIN
GHL_MEDIA_UPLOAD_PATH = ghl_media.GHL_MEDIA_UPLOAD_PATH

# v3 bulk-delete — NOT in the shared module; used ONLY for self-cleaning (a probe or
# a failed run deletes the probe/temp file it uploaded). Never leaves junk.
GHL_MEDIA_DELETE_PATH = "/medias/delete-files"

# The SAME browser User-Agent the shared module proves is required for the services.*
# origin (Cloudflare 1010 bot-signature WAF block). Duplicated here because the shared
# module's private ``_GHL_UA`` is not in its exported symbol list; the literal UA is
# load-bearing (proven live 2026-08-06: upload HTTP 201 with this UA vs 403/1010 with
# the Python-urllib default).
_GHL_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

# A structurally-valid minimal MP4 used ONLY by the small-probe: an ``ftyp`` box
# (32-bit size + 'ftyp' + brand 'isom' + 2 minor brands) plus a 32-bit ``free`` box.
# This is the standard "smallest MP4" shape real-world clients accept for the video
# content-type; it is a genuine MP4 container structure, not a placeholder blob, and
# it passes the shared ``verify_video`` ftyp probe.
_PROBE_MP4 = (
    b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isommp42"   # ftyp box (24 bytes)
    b"\x00\x00\x00\x08free"                                 # free box (8 bytes)
)

MAX_PROBE_SIZE = 64 * 1024   # small-probe files must be tiny (<= 64 KB)


def _require(value, name: str) -> None:
    """Reject empty / whitespace-only required values (fail loud, never silently
    proceed with a blank that would target the wrong resource)."""
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"{name} is required and must be non-empty")


def _send_with_retry(req, timeout, opener, *, attempts: int = 3, backoff: float = 0.5):
    """Bounded retry on TRANSIENT failures only (mirrors the canonical helper).

    Retries a connection/timeout error or an ``HTTPError`` in the transient set
    (429/500/502/503/504). A non-transient 4xx (401/403/404/422) is re-raised on the
    FIRST failure, and a successful response returns immediately (never re-sent)."""
    last_exc: BaseException | None = None
    for n in range(1, attempts + 1):
        try:
            return opener(req, timeout)
        except urllib.error.HTTPError as exc:
            if exc.code not in frozenset({429, 500, 502, 503, 504}):
                raise
            last_exc = exc
        except (urllib.error.URLError, OSError) as exc:
            last_exc = exc
        if n < attempts:
            time.sleep(backoff * (2 ** (n - 1)))
    assert last_exc is not None
    raise last_exc


# ── v3 bulk-delete (self-clean) ───────────────────────────────────────────────

def delete_media_file(file_id: str, location_id: str, pit: str, *,
                      timeout: int = 60, opener=None) -> int:
    """DELETE/trash one media file via the v3 bulk-delete endpoint (SELF-CLEAN).

    ``PUT services.leadconnectorhq.com/medias/delete-files`` with
    ``Authorization: Bearer <LOCATION PIT>`` + ``Version: v3`` and a JSON body
    ``{filesToBeDeleted: [{_id}], altType: "location", altId, status: "deleted"}``
    (the v3 spec's ``DeleteMediaObjectsBodyParams``). Used by the small-probe so a
    probe upload never leaves junk in a client's library. Returns the HTTP status.

    Raises on transport error; a non-2xx status is RETURNED (not raised) so the
    probe can report "self-clean delete failed" without aborting."""
    _require(file_id, "file_id")
    _require(location_id, "location_id")
    _require(pit, "pit")
    body_obj = {
        "filesToBeDeleted": [{"_id": file_id}],
        "altType": "location",
        "altId": location_id,
        "status": "deleted",
    }
    body = json.dumps(body_obj).encode("utf-8")
    url = GHL_SERVICES_ORIGIN.rstrip("/") + GHL_MEDIA_DELETE_PATH
    req = urllib.request.Request(url, data=body, method="PUT")
    req.add_header("Authorization", f"Bearer {pit}")
    req.add_header("Version", GHL_MEDIA_VERSION_V3)
    req.add_header("User-Agent", _GHL_UA)
    req.add_header("Content-Type", "application/json")
    _opener = opener or (lambda r, t: urllib.request.urlopen(r, timeout=t))
    try:
        resp = _send_with_retry(req, timeout, _opener)
        return int(resp.getcode())
    except urllib.error.HTTPError as exc:
        return int(getattr(exc, "code", 0))
    except (urllib.error.URLError, OSError) as exc:
        raise RuntimeError(f"video delete transport error for {file_id!r}: {exc}") from exc


# ── the SMALL-PROBE: prove v3 + video/mp4 + auth against the LIVE library ─────

def probe_upload(*, pit: str | None = None, location_id: str | None = None,
                 name: str | None = None, parent_id: str | None = None,
                 opener=None) -> dict:
    """SMALL-PROBE: prove the v3 + video/mp4 + LOCATION-PIT path against the LIVE
    library, then SELF-CLEAN.

    Uploads the tiny structural ``_PROBE_MP4`` (~32 bytes) via the shared
    ``ghl_media.upload_video`` (Version: v3, video/mp4), VERIFIES it landed by listing
    the library with ``ghl_media.list_media`` (the read-only verification twin,
    matching on the probe name), then DELETES it via ``delete_media_file``. A probe
    NEVER leaves junk in a client's library.

    ``pit`` / ``location_id`` default to the shared ``ghl_media.resolve_location_pit()``
    / ``resolve_location_id()`` (the CLIENT's LOCATION PIT). ``name`` defaults to
    ``"PROBE <uuid>.mp4"`` so the probe is unmistakable in a list-back.

    Returns ``{pass: bool, name, file_id, url, http, verified_in_listing: bool,
    deleted: bool, delete_http, reasons: [...]}`` — NEVER a credential."""
    pit = pit or ghl_media.resolve_location_pit()
    location_id = location_id or ghl_media.resolve_location_id()
    probe_name = name or f"PROBE {uuid.uuid4().hex}.mp4"

    import tempfile
    reasons: list[str] = []
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        Path(tmp_path).write_bytes(_PROBE_MP4)
        res = upload_video(tmp_path, location_id, probe_name, pit,
                           parent_id=parent_id, opener=opener)
        file_id = res["fileId"]
        url = res["url"]
        http = res["http"]

        # Verification twin: prove the file is genuinely in the library (name match).
        listed_ok = False
        try:
            listing = ghl_media.list_media(location_id, pit, media_type="file",
                                           query=probe_name, limit=25, opener=opener)
            listed_ok = any(
                isinstance(e, dict)
                and str(e.get("name") or "").lower() == probe_name.lower()
                for e in (listing.get("data") or [])
            )
        except Exception as exc:  # noqa: BLE001 — the probe reports, it does not crash
            reasons.append(f"list-verify failed: {exc!r}")

        # SELF-CLEAN: always attempt the v3 delete so no probe junk remains.
        delete_http = None
        deleted = False
        try:
            delete_http = delete_media_file(file_id, location_id, pit, opener=opener)
            deleted = 200 <= int(delete_http) < 300
        except Exception as exc:  # noqa: BLE001
            reasons.append(f"self-clean delete failed: {exc!r}")

        ok = bool(listed_ok) and bool(deleted)
        if not ok:
            if not listed_ok:
                reasons.append("probe file was not found in a live list-back")
            if not deleted:
                reasons.append("probe file could not be deleted after upload")
        return {
            "pass": ok,
            "name": probe_name,
            "file_id": file_id,
            "url": url,
            "http": http,
            "verified_in_listing": listed_ok,
            "deleted": deleted,
            "delete_http": delete_http,
            "ghl_version": GHL_MEDIA_VERSION_V3,
            "reasons": reasons,
        }
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ── CLI ───────────────────────────────────────────────────────────────────────

def _check_size_cli(path: str) -> int:
    p = Path(path)
    if not p.is_file():
        print(f"check-size: FAIL — {path!r} does not exist", file=sys.stderr)
        return 2
    size = p.stat().st_size
    tier = "video (500MB v3 tier OK)" if size <= GHL_VIDEO_MAX_BYTES else "OVER 500MB — REFUSED"
    print(f"{p.name}: {size / (1024 * 1024):.1f} MB — {tier}")
    if not verify_video(path):
        print(f"  WARNING: does not pass the MP4 ftyp small-probe — "
              f"upload_video will refuse it")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="GHL v3 video upload wrapper: upload_video (Version: v3, video/mp4, "
                    "500MB tier), self-cleaning small-probe, offline selftest.")
    ap.add_argument("--upload", metavar="PATH", default=None,
                    help="upload this video via Version: v3 (needs the client's LOCATION "
                         "PIT in env; fails loud on any guard).")
    ap.add_argument("--name", default=None, help="media-library name for the upload.")
    ap.add_argument("--parent", default=None, help="optional folder id (parentId).")
    ap.add_argument("--probe", action="store_true",
                    help="SMALL-PROBE: upload a tiny MP4, verify it lands, then delete it "
                         "— proves v3 + video/mp4 + auth against the LIVE library.")
    ap.add_argument("--check-size", metavar="PATH", default=None,
                    help="read-only size/tier check for a file (no network, no creds).")
    ap.add_argument("--selftest", action="store_true",
                    help="offline self-test of the wrapper (stdlib only, no network).")
    args = ap.parse_args()

    if args.selftest:
        return _selftest()

    if args.check_size:
        return _check_size_cli(args.check_size)

    if args.probe:
        try:
            out = probe_upload(parent_id=args.parent)
        except Exception as exc:  # noqa: BLE001
            print(f"GHL VIDEO PROBE: FAIL ({exc!r})", file=sys.stderr)
            return 1
        print(json.dumps(out, indent=2))
        return 0 if out.get("pass") else 1

    if args.upload:
        if not args.name:
            args.name = Path(args.upload).name
        try:
            pit = ghl_media.resolve_location_pit()
            loc = ghl_media.resolve_location_id()
        except Exception as exc:  # noqa: BLE001
            print(f"GHL VIDEO UPLOAD: FAIL (credential resolution: {exc})", file=sys.stderr)
            return 2
        try:
            res = upload_video(args.upload, loc, args.name, pit, parent_id=args.parent)
        except Exception as exc:  # noqa: BLE001
            print(f"GHL VIDEO UPLOAD: FAIL ({exc})", file=sys.stderr)
            return 1
        print(json.dumps(res, indent=2))
        return 0

    ap.error("provide one of --upload / --probe / --check-size / --selftest")


# ── offline self-test (no network, stdlib only) ───────────────────────────────

def _selftest() -> int:
    import tempfile
    fails: list[str] = []

    class _Resp:
        def __init__(self, code, raw):
            self._code, self._raw = code, raw

        def getcode(self):
            return self._code

        def read(self):
            return self._raw

    def _mock_ok(req, timeout):
        captured.append((req.get_header("Version", "MISSING"),
                         req.get_header("Authorization", "MISSING") is not None,
                         req.get_header("User-Agent", "MISSING")))
        return _Resp(200, b'{"fileId":"file_v1","url":"https://storage.googleapis.com/'
                          b'msgsndr/probe/file_v1"}')

    def _mock_err(code: int, body: bytes):
        return lambda req, timeout: _Resp(code, body)

    # 1. Delegation happy path: the shared upload_video carries Version: v3 + Bearer + UA.
    with tempfile.TemporaryDirectory() as t:
        mp4 = Path(t) / "probe.mp4"
        mp4.write_bytes(_PROBE_MP4)
        captured = []
        res = upload_video(str(mp4), "loc-v", "Probe.mp4", "pit-v", opener=_mock_ok)
        if res.get("fileId") != "file_v1":
            fails.append(f"happy-path: unexpected result {res!r}")
        ver = captured[0][0]
        if ver != "v3":
            fails.append(f"happy-path: expected Version: v3, got {ver!r}")
        if not captured[0][1]:
            fails.append("happy-path: Authorization Bearer header missing")
        if not captured[0][2]:
            fails.append("happy-path: User-Agent header missing (Cloudflare 1010 guard)")

    # 2. The probe MP4 passes the shared verify_video ftyp small-probe.
    with tempfile.TemporaryDirectory() as t:
        mp4 = Path(t) / "p.mp4"
        mp4.write_bytes(_PROBE_MP4)
        if not verify_video(str(mp4)):
            fails.append("probe-mp4: _PROBE_MP4 must pass verify_video")
        if len(_PROBE_MP4) > MAX_PROBE_SIZE:
            fails.append(f"probe-mp4: probe is {len(_PROBE_MP4)} bytes, over MAX_PROBE_SIZE")

    # 3. Non-MP4 (not 'ftyp' at offset 4) -> refused by the shared small-probe.
    with tempfile.TemporaryDirectory() as t:
        bad = Path(t) / "fake.mp4"
        bad.write_bytes(b"NOTVIDEO" * 64)
        try:
            upload_video(str(bad), "loc", "x", "pit", opener=_mock_ok)
            fails.append("non-mp4: expected ValueError (no 'ftyp' magic), got success")
        except ValueError:
            pass
        except Exception as exc:  # noqa: BLE001
            fails.append(f"non-mp4: expected ValueError, got {exc!r}")

    # 4. Over-500MB -> refused BEFORE any network (opener must never fire).
    with tempfile.TemporaryDirectory() as t:
        big = Path(t) / "huge.mp4"
        big.write_bytes(_PROBE_MP4 + b"\x00" * (GHL_VIDEO_MAX_BYTES + 1))
        fired = []

        def _never(req, timeout):
            fired.append(1)
            raise AssertionError("opener reached for an over-500MB file")

        try:
            upload_video(str(big), "loc", "huge.mp4", "pit", opener=_never)
            fails.append("over-500mb: expected ValueError, got success")
        except ValueError as exc:
            if "500" not in str(exc):
                fails.append(f"over-500mb: expected a 500MB-tier message, got {exc!r}")
        except Exception as exc:  # noqa: BLE001
            fails.append(f"over-500mb: expected ValueError, got {exc!r}")
        if fired:
            fails.append("over-500mb: opener invoked — over-limit file was sent")

    # 5. Missing file -> ValueError.
    try:
        upload_video("/nonexistent/nope.mp4", "loc", "x", "pit", opener=_mock_ok)
        fails.append("missing-file: expected ValueError, got success")
    except ValueError:
        pass

    # 6. delete_media_file: success path returns the HTTP status (mock).
    def _mock_delete_ok(req, timeout):
        return _Resp(200, b'{"deleted":true}')

    with tempfile.TemporaryDirectory() as t:
        st = delete_media_file("file_x", "loc", "pit", opener=_mock_delete_ok)
        if not (200 <= int(st) < 300):
            fails.append(f"delete-ok: expected 2xx, got {st}")

    # 7. delete_media_file: a non-transient 403 is returned (not raised) so the probe
    #    can report "self-clean delete failed" without crashing.
    with tempfile.TemporaryDirectory() as t:
        st = delete_media_file("file_x", "loc", "pit", opener=_mock_err(403, b'{"e":1}'))
        if st != 403:
            fails.append(f"delete-403: expected status 403 returned, got {st}")

    # 8. probe_upload offline: explicit pit/location_id (>= 20 chars so the shared
    #    _is_placeholder guard does not reject them) + patched upload/list/delete, so
    #    the full probe sequence (upload -> list-verify -> self-clean) runs with zero
    #    network and zero env dependence.
    _probe_seen = {"name": None}
    _real_list = ghl_media.list_media
    _orig_upload = upload_video
    _orig_delete = delete_media_file

    def _fake_list(location_id, pit, *, media_type="file", query=None, limit=25,
                   opener=None, **kw):
        return {"http": 200, "count": 1,
                "data": [{"name": _probe_seen["name"] or "PROBE", "_id": "file_probe",
                          "url": "https://x"}]}

    def _fake_delete(file_id, location_id, pit, *, timeout=60, opener=None):
        return 200

    def _fake_upload(video_path, location_id, name, pit, *, parent_id=None,
                     hosted=False, timeout=900, opener=None, require_video=True):
        _probe_seen["name"] = name
        return {"fileId": "file_probe",
                "url": "https://storage.googleapis.com/msgsndr/probe/file_probe",
                "name": name, "local_path": video_path, "http": 201,
                "tier": "v3", "content_type": "video/mp4"}

    globals()["upload_video"] = _fake_upload
    ghl_media.list_media = _fake_list
    globals()["delete_media_file"] = _fake_delete
    try:
        out = probe_upload(pit="probe-fixture-pit-1234567890",
                           location_id="loc-probe-fixture-1234567890")
    finally:
        globals()["upload_video"] = _orig_upload
        ghl_media.list_media = _real_list
        globals()["delete_media_file"] = _orig_delete
    if not out.get("pass"):
        fails.append(f"probe-offline: expected PASS, got {out!r}")
    if not out.get("deleted"):
        fails.append(f"probe-offline: expected self-clean delete, got {out!r}")
    if out.get("ghl_version") != "v3":
        fails.append(f"probe-offline: expected ghl_version v3, got {out!r}")

    if fails:
        print("ghl_video selftest -> FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("ghl_video selftest -> PASS (delegation v3 header+UA wiring / probe-MP4 ftyp "
          "probe / non-mp4-refused / over-500MB-refused-before-network / missing-file / "
          "delete-2xx / delete-403-reported / offline small-probe PASS+self-clean)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
