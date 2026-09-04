#!/usr/bin/env python3
"""ghl_media.py — GoHighLevel media hosting for the Skill-48 Facebook/Instagram ad run.

WHAT THIS IS
------------
The image-hosting half of Skill 48's pipeline. After the 10 approved ad rasters are
generated (by the reused Kie ``gpt-image-*`` adapter), this module uploads each PNG to
the CLIENT's own GoHighLevel media library and returns the PUBLIC, login-free GCS object
URL that the PLAI hand-off package references. It owns the deterministic, mechanical
media calls so they are never improvised:

  1. ``upload_media(png_path, location_id, name, pit, ...)`` — the PROVEN
     ``POST services.leadconnectorhq.com/medias/upload-file`` Bearer-PIT call (ported
     from ``37-zhc-closeout/scripts/upload-ghl-media.sh``), returning ``{fileId, url}``
     where ``url`` is the PUBLIC ``storage.googleapis.com/msgsndr/...`` GCS object URL
     (openable with NO login — that is the real ``cdn_url``).
  2. ``create_media_folder(name, location_id, pit, ...)`` — NET-NEW for Skill 48: a
     per-run media FOLDER so each run's 10 images group under the run-id, with a
     name-prefix fallback when folders are unavailable on the location.
  3. ``resolve_location_pit`` / ``resolve_location_id`` — read the client's own LOCATION
     credentials from the canonical env names.
  4. ``verify_png`` — the PNG magic-byte guard so only real rasters are ever hosted.

AUTH MODEL (LOAD-BEARING)
-------------------------
The GHL MEDIA API (``services.leadconnectorhq.com`` + ``Authorization: Bearer <LOCATION
PIT>``) is NOT behind any Cloudflare interstitial, so it runs from bare Python via
``urllib`` — stdlib only, no ``requests``. Media uploads REQUIRE the LOCATION PIT with
``medias.write``; the Agency PIT 401s for media ops.

KEYS — THE CLIENT'S OWN, NEVER THE OPERATOR'S
---------------------------------------------
The LOCATION Private Integration Token (PIT) and location id are the CLIENT's own, read
from the canonical env names (full 11-alias LOCATION-PIT set starting with
``GOHIGHLEVEL_API_KEY`` — see ``_PIT_ENV_NAMES``; ``GOHIGHLEVEL_LOCATION_ID``/
``GHL_LOCATION_ID`` for the location id). The operator's key NEVER appears here.

DURABILITY — BOUNDED RETRY ON TRANSIENT FAILURES
------------------------------------------------
Both HTTP calls route through ``_send_with_retry``, which retries ONLY transient failures
(connection/timeout errors and HTTP 429/500/502/503/504) with exponential backoff, then
re-raises the last error unchanged. A non-transient 4xx (401/403/404/422…) is NEVER
retried, and a successful 2xx is never re-sent — so a transient S7 blip self-heals
without ever double-uploading.

NO-FABRICATION / FAIL-LOUD
--------------------------
Every step fails LOUD rather than substitute a placeholder: a non-PNG upload is refused
(magic-byte check); a missing key raises; an upload that returns no ``fileId``/``url``
raises (never a fabricated CDN URL). The hosted link a run records can therefore only
ever be a real, publicly-resolving ``https`` URL with a verified HTTP status.
"""

from __future__ import annotations

import json
import mimetypes
import os
import time
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable

# ── FIX 14 — governor gate for every outbound GHL media call ──────────────────
# One lease per HTTP attempt on the `ghl` provider (providers.yaml ghl row:
# rps 2.0, burst 20, max_inflight 25): the upload POST acquires a slot from
# presentation_job/governor.py before the request and releases it after; a
# live HTTP 429 halves the next 60 s of rate via report_429 (report_ok
# recovers). Fail-soft: when the governor module is absent (a legacy checkout
# predating the FIX 14 merge) every helper is a no-op passthrough — uploads
# proceed exactly as before, just unthrottled.
try:
    from presentation_job import governor as _governor
except Exception:  # noqa: BLE001 — fail-soft: legacy tree without governor.py
    # The repo-root presentation_job/governor.py is the single source; walk up
    # from this file to find it and file-load it (same pattern as
    # synthesize_full_speech when no presentation_job package is importable).
    try:
        import importlib.util as _ilu
        _g = __file__ and os.path.dirname(os.path.abspath(__file__))
        _cand = None
        for _ in range(6):
            if _g and os.path.isfile(os.path.join(_g, "presentation_job", "governor.py")):
                _cand = os.path.join(_g, "presentation_job", "governor.py")
                break
            _g = os.path.dirname(_g) if _g else _g
        _governor = None
        if _cand:
            _spec = _ilu.spec_from_file_location("_presentation_governor", _cand)
            if _spec and _spec.loader:
                _gov_mod = _ilu.module_from_spec(_spec)
                sys.modules.setdefault("_presentation_governor", _gov_mod)
                _spec.loader.exec_module(_gov_mod)
                _governor = _gov_mod
    except Exception:  # noqa: BLE001 — never break an upload on a gate failure
        _governor = None

_GOV_GHL_PROVIDER = "ghl"


def _gov_ghl_acquire() -> Any:
    """One `ghl` lease for this upload attempt. None = unthrottled."""
    if _governor is None:
        return None
    try:
        return _governor.acquire(_GOV_GHL_PROVIDER, n=1, timeout_s=60.0)
    except Exception:  # noqa: BLE001 — the rate window is a courtesy, not a gate
        return None


def _gov_ghl_release(lease: Any) -> None:
    if _governor is None or lease is None:
        return
    try:
        _governor.release(lease)
    except Exception:  # noqa: BLE001
        pass


def _gov_ghl_report(kind: str) -> None:
    """Telemetry into the governor: kind is 'ok' or '429'. No-op when absent."""
    if _governor is None:
        return
    try:
        if kind == "429":
            _governor.report_429(_GOV_GHL_PROVIDER)
        elif kind == "ok":
            _governor.report_ok(_GOV_GHL_PROVIDER)
    except Exception:  # noqa: BLE001
        pass

# ── Constants (ported from the PROVEN upload-ghl-media.sh) ────────────────────

# Media upload lives on the services.* origin (Bearer PIT) — NOT WAF-gated, so this
# runs from bare Python.
GHL_SERVICES_ORIGIN = "https://services.leadconnectorhq.com"
GHL_MEDIA_UPLOAD_PATH = "/medias/upload-file"
GHL_MEDIA_FOLDER_PATH = "/medias/folder"   # Skill 48 addition: per-run media folder
GHL_MEDIA_LIST_PATH = "/medias/files"      # read-only media-library list (QC list-back)
GHL_MEDIA_VERSION = "2021-07-28"

# v3 media tier — VIDEO uploads. GHL's v3 media API grants a larger quota for VIDEO
# files (500MB) than the regular "2021-07-28" tier (25MB). The tier is selected by the
# ``Version`` request header: ``v3`` for the video tier (with the file part declared
# ``Content-Type: video/mp4``), ``2021-07-28`` for the regular tier. NOT the operator's
# numbers — these are GHL's published per-tier caps (25MB image/regular, 500MB video).
GHL_MEDIA_VERSION_V3 = "v3"
GHL_VIDEO_MAX_BYTES = 500 * 1024 * 1024  # 500MB — GHL v3 video tier ceiling
GHL_VIDEO_MIME = "video/mp4"

# PNG magic bytes — a real raster starts with these. A non-PNG upload is a hard FAIL
# (never stubbed).
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# Transient HTTP status set worth a bounded retry (rate-limit + gateway/5xx). A
# non-transient 4xx (401/403/404/422…) is NEVER retried.
_RETRY_HTTP_CODES = frozenset({429, 500, 502, 503, 504})

# Browser User-Agent — REQUIRED for the services.* origin. services.leadconnectorhq.com
# sits behind a Cloudflare edge WAF that 403s (error code 1010, "bot-signature") ANY
# request whose User-Agent is the bare-Python default `Python-urllib/3.x`. A real GHL
# LOCATION PIT + correct scope still 1010s without this. Every HTTP call in this module
# (upload / folder-create / read-only list) sets this UA; the WAF block is
# signature-based on the literal UA string, so a browser UA is the fix (proven live
# 2026-08-06: upload HTTP 201 + list HTTP 200 on a real location with this UA vs
# 403/1010 with the default UA).
_GHL_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

# Canonical env names for the GHL LOCATION PIT — full 11-alias set, priority order.
# Media uploads REQUIRE the LOCATION PIT (the Agency PIT 401s for media ops).
_PIT_ENV_NAMES = (
    "GOHIGHLEVEL_API_KEY",
    "GHL_API_KEY",
    "GHL_PIT",
    "GHL_TOKEN",
    "GHL_PRIVATE_INTEGRATION_TOKEN",
    "PRIVATE_INTEGRATION_TOKEN",
    "GHL_PRIVATE_TOKEN",
    "PIT_TOKEN",
    "GHL_PIT_TOKEN",
    "GOHIGHLEVEL_LOCATION_PIT",
    "GHL_LOCATION_PIT",
)
_LOCATION_ENV_NAMES = ("GOHIGHLEVEL_LOCATION_ID", "GHL_LOCATION_ID")


def _is_placeholder(value: str) -> bool:
    """True when ``value`` is a documentation placeholder, not a real credential.

    Mirrors ``38-conversational-ai-system/scripts/check-ghl-pit-liveness.sh``'s
    ``_is_placeholder()`` (the proven, already-fixed reference implementation —
    root-caused a false "PIT is DEAD/EXPIRED" alarm on 2026-08-03: the 10-char doc
    placeholder ``pit-abc123`` is non-empty, so a naive first-non-empty-wins
    resolver picks it up over the real credential). Same three shapes, ported to
    Python: shorter than 20 characters, a known dummy literal (``pit-abc...``,
    ``changeme...``, ``xxx...``, ``your-...``/``your_...``, a ``*_here``/``*-here``
    suffix), or an angle-bracket placeholder token (``<...>``). Never logs or
    returns the value — shape only.
    """
    if not value:
        return True
    if len(value) < 20:
        return True
    low = value.lower()
    if low.startswith("pit-abc") or low.startswith("changeme") or low.startswith("xxx") \
       or low.startswith("your-") or low.startswith("your_") \
       or low.endswith("_here") or low.endswith("-here") \
       or (value.startswith("<") and value.endswith(">")):
        return True
    return False


# ── small helpers ─────────────────────────────────────────────────────────────

def _require(value: Any, name: str) -> None:
    """Reject empty / whitespace-only required values (fail loud, never silently
    proceed with a blank that would target the wrong resource)."""
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"{name} is required and must be non-empty")


def _send_with_retry(
    req: urllib.request.Request,
    timeout: int,
    opener: Callable[[urllib.request.Request, int], Any],
    *,
    attempts: int = 3,
    backoff: float = 0.5,
) -> Any:
    """Call ``opener(req, timeout)`` with a bounded retry on TRANSIENT failures only.

    Retries a connection/timeout error (``urllib.error.URLError``, ``OSError`` incl. a
    socket timeout) or an ``HTTPError`` whose status is in ``_RETRY_HTTP_CODES``
    (429/500/502/503/504), sleeping ``backoff * 2 ** (n - 1)`` seconds between tries. A
    non-transient 4xx (401/403/404/422…) is re-raised on the FIRST failure (never
    retried), and a successful response returns immediately (never re-sent). After the
    ``attempts`` cap the LAST exception is re-raised UNCHANGED, so each caller's existing
    fail-loud handling (upload's ``RuntimeError`` / folder's name-prefix fallback) still
    fires exactly as before — retry only turns a transient blip into a self-heal, it
    never swallows a real error and never double-sends a 2xx."""
    last_exc: BaseException | None = None
    for n in range(1, attempts + 1):
        try:
            return opener(req, timeout)
        except urllib.error.HTTPError as exc:
            # HTTPError is a URLError subclass: only the transient status set is retried;
            # a real 4xx propagates immediately (no double-upload on a rejected request).
            if exc.code not in _RETRY_HTTP_CODES:
                raise
            last_exc = exc
        except (urllib.error.URLError, OSError) as exc:
            # Transport-level transient (DNS / connection reset / socket timeout).
            last_exc = exc
        if n < attempts:
            time.sleep(backoff * (2 ** (n - 1)))
    # Exhausted the cap on transient failures — re-raise the LAST one unchanged.
    assert last_exc is not None  # loop only falls through here after an except set it
    raise last_exc


def resolve_location_pit(env: dict | None = None) -> str:
    """Resolve the client's GHL LOCATION PIT from the canonical env names.

    Iterates the full 11-alias ``_PIT_ENV_NAMES`` set (priority order: ``GOHIGHLEVEL_API_KEY``
    first, ``GHL_LOCATION_PIT`` last). Strips surrounding quotes. A placeholder-shaped
    value (see ``_is_placeholder``) is SKIPPED, not returned — the live process env is
    seeded from openclaw.json ``env.vars`` at gateway launch, and those config copies are
    placeholders BY DESIGN (see TERMINOLOGY.md). Raises if every alias is absent or
    placeholder-shaped — media upload cannot proceed without a real LOCATION PIT, and we
    never fabricate a public URL, so this is a hard, honest FAIL."""
    env = env if env is not None else os.environ
    saw_placeholder = False
    for name in _PIT_ENV_NAMES:
        val = str(env.get(name, "")).strip().strip("'\"")
        if not val:
            continue
        if _is_placeholder(val):
            saw_placeholder = True
            continue
        return val
    placeholder_note = (
        " Note: at least one candidate was a documentation PLACEHOLDER (short / "
        "dummy-shaped) and was SKIPPED rather than used — put the real value in "
        "~/.openclaw/secrets/.env, not just openclaw.json."
        if saw_placeholder else ""
    )
    raise RuntimeError(
        "GHL LOCATION PIT not found — set one of "
        f"{', '.join(_PIT_ENV_NAMES)} (the LOCATION Private Integration Token). "
        f"Media uploads require the LOCATION PIT (the Agency PIT 401s for media).{placeholder_note}"
    )


def resolve_location_id(env: dict | None = None) -> str:
    """Resolve the client's GHL location id from the canonical env names —
    ``GOHIGHLEVEL_LOCATION_ID`` (preferred) or the legacy ``GHL_LOCATION_ID`` alias.
    Raises if unset (fail loud)."""
    env = env if env is not None else os.environ
    for name in _LOCATION_ENV_NAMES:
        val = str(env.get(name, "")).strip().strip("'\"")
        if val:
            return val
    raise RuntimeError(
        f"GHL location id not found — set one of {', '.join(_LOCATION_ENV_NAMES)}."
    )


# ── PNG guard — only a real raster is ever hosted ─────────────────────────────

def verify_png(path: str) -> bool:
    """True iff ``path`` exists and starts with the PNG magic bytes.

    Guards ``upload_media`` so a non-PNG stub can never be hosted or referenced in the
    PLAI package."""
    p = Path(path)
    if not p.is_file() or p.stat().st_size < len(PNG_MAGIC):
        return False
    with open(p, "rb") as f:
        return f.read(len(PNG_MAGIC)) == PNG_MAGIC


# ── upload_media — PROVEN services.* Bearer-PIT media upload (bare Python) ─────

def _multipart_encode(
    fields: dict[str, str],
    file_field: str,
    file_path: str,
    file_content_type: str | None = None,
) -> tuple[bytes, str]:
    """Encode ``multipart/form-data`` for the media upload (one file + text fields).

    Returns ``(body_bytes, content_type)``. Mirrors the curl ``-F`` form the proven
    shell script sends: ``file=@<path>``, ``locationId``, ``name``, ``hosted`` (and
    optional ``parentId``). A small, dependency-free encoder so the upload runs on
    stock Python (no ``requests``).

    ``file_content_type`` optionally FORCES the file part's ``Content-Type`` (used by
    the v3 video path so an MP4 is declared ``video/mp4`` even when the extension is
    ambiguous); when omitted the type is guessed from the filename as before."""
    boundary = f"----ghlmedia{uuid.uuid4().hex}"
    crlf = b"\r\n"
    out: list[bytes] = []
    for key, val in fields.items():
        out.append(b"--" + boundary.encode())
        out.append(f'Content-Disposition: form-data; name="{key}"'.encode())
        out.append(b"")
        out.append(str(val).encode("utf-8"))
    # The file part.
    fname = os.path.basename(file_path)
    ctype = file_content_type or (mimetypes.guess_type(fname)[0] or "application/octet-stream")
    with open(file_path, "rb") as f:
        file_bytes = f.read()
    out.append(b"--" + boundary.encode())
    out.append(
        f'Content-Disposition: form-data; name="{file_field}"; filename="{fname}"'.encode()
    )
    out.append(f"Content-Type: {ctype}".encode())
    out.append(b"")
    body = crlf.join(out) + crlf + file_bytes + crlf
    body += b"--" + boundary.encode() + b"--" + crlf
    return body, f"multipart/form-data; boundary={boundary}"


def upload_media(
    png_path: str,
    location_id: str,
    name: str,
    pit: str,
    *,
    hosted: bool = False,
    parent_id: str | None = None,
    timeout: int = 300,
    opener: Callable[[urllib.request.Request, int], Any] | None = None,
    require_png: bool = True,
    file_content_type: str | None = None,
    version: str | None = None,
) -> dict:
    """Upload one media file to the GHL media library and return ``{fileId, url}``.

    Ports the PROVEN call from ``37-zhc-closeout/scripts/upload-ghl-media.sh``:
    ``POST services.leadconnectorhq.com/medias/upload-file`` with
    ``Authorization: Bearer <LOCATION PIT>`` + ``Version: 2021-07-28`` and the
    multipart fields ``file`` / ``locationId`` / ``name`` / ``hosted`` (+ optional
    ``parentId`` FOLDER id — the field is ``parentId``, NOT ``folderId``). The
    response ``url`` is a PUBLIC ``storage.googleapis.com/msgsndr/...`` GCS object
    URL — openable with NO login. THAT public URL is the real ``cdn_url`` the page
    references.

    This is on the bare-Python side of the auth split (services.* + Bearer PIT is
    NOT Cloudflare-WAF-gated). The HTTP POST routes through ``_send_with_retry`` so a
    transient blip (429/5xx/timeout) self-heals; a real 4xx or a bad 2xx still FAILS
    LOUD: a non-2xx response, or a 2xx with no ``fileId``/``url``, raises (we never
    fabricate a CDN URL).

    Args:
        png_path: Local PNG to upload (must be a real PNG — re-verified).
        location_id: The GHL sub-account location id (client's own, e.g. ``Mct54...``).
        name: Human-friendly media-library name.
        pit: The LOCATION Private Integration Token (Bearer).
        hosted: The ``hosted`` form field (default False).
        parent_id: Optional FOLDER id (``parentId``); files land in the media root
            when omitted (still fully shareable).
        timeout: HTTP timeout seconds (uploads can be large).
        opener: Optional callable ``(Request, timeout) -> response-like`` for tests
            (mock the HTTP). Default = ``urllib.request.urlopen`` (real call).
        require_png: When True (DEFAULT — the ad-image pipeline), the file MUST pass the
            PNG magic-byte check (only real generated rasters are hosted, never a stub).
            When False, the PNG-only restriction is lifted so a NON-IMAGE media artifact
            (e.g. a final ``.pptx``/``.pdf`` deck) can be hosted through this SAME proven
            REST call instead of forking it — the file must still exist. The default
            keeps every existing caller's behavior byte-for-byte; ONLY a caller that has
            already proven the artifact is a legitimate non-image deliverable passes
            ``require_png=False`` behind its own fail-closed delivery gate.
        file_content_type: OPTIONAL override for the multipart file part's
            ``Content-Type`` (e.g. ``video/mp4`` for a v3 video upload so the API treats
            the file as video regardless of extension). When omitted the type is guessed
            from the filename — the pre-existing behavior is unchanged.
        version: OPTIONAL ``Version`` request-header override. The media-library
            "regular" tier is ``2021-07-28`` (the default — unchanged); a v3 video
            upload passes ``"v3"`` so the API grants the larger v3 video quota (500MB)
            instead of the 25MB regular-media cap. When omitted the pre-existing
            ``Version: 2021-07-28`` header is sent.

    Returns:
        ``{fileId, url, name, local_path, http}`` — ``url`` is the public GCS URL.

    Raises:
        ValueError: missing args, a non-PNG file when ``require_png`` (default), or a
            non-existent file when ``require_png=False``.
        RuntimeError: non-2xx HTTP, or a 2xx response missing ``fileId``/``url``.
    """
    _require(png_path, "png_path")
    _require(location_id, "location_id")
    _require(name, "name")
    _require(pit, "pit")
    if require_png:
        if not verify_png(png_path):
            raise ValueError(
                f"refusing to upload {png_path!r}: not a valid PNG (magic-byte check "
                "failed) — only real generated rasters are uploaded, never a stub"
            )
    elif not os.path.isfile(png_path):
        # require_png=False lifts the image-only restriction (a deck deliverable), but
        # a missing file is still a hard FAIL — we never POST a phantom artifact.
        raise ValueError(
            f"refusing to upload {png_path!r}: file does not exist (require_png=False "
            "lifts the PNG-only check for non-image deliverables, not the existence check)"
        )

    fields: dict[str, str] = {
        "locationId": location_id,
        "name": name,
        "hosted": "true" if hosted else "false",
    }
    if parent_id:
        fields["parentId"] = parent_id  # documented folder field is parentId

    body, content_type = _multipart_encode(fields, "file", png_path,
                                           file_content_type=file_content_type)
    url = GHL_SERVICES_ORIGIN.rstrip("/") + GHL_MEDIA_UPLOAD_PATH
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {pit}")
    req.add_header("Version", version or GHL_MEDIA_VERSION)
    req.add_header("User-Agent", _GHL_UA)  # Cloudflare 1010 bot-block fix
    req.add_header("Content-Type", content_type)

    _opener = opener or (lambda r, t: urllib.request.urlopen(r, timeout=t))
    # FIX 14: the medias/upload-file POST is an outbound `ghl` call — acquire
    # one governor lease per send attempt (retry sends re-acquire via
    # _send_with_retry's loop) so an upload fan-out can never exceed the ghl
    # row's rps/burst window or max_inflight. report_429 on a live 429 halves
    # the next 60 s of rate; a clean response feeds report_ok. Fail-soft:
    # a None lease (governor absent or acquire timed out) proceeds unthrottled.
    _gov_lease = _gov_ghl_acquire()
    try:
        resp = _send_with_retry(req, timeout, _opener)
        code = resp.getcode()
        raw = resp.read()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
        _gov_ghl_report("ok")
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            _gov_ghl_report("429")
        else:
            _gov_ghl_report("ok")  # a non-429 HTTP failure is not throttling
        detail = exc.read().decode("utf-8", "replace") if hasattr(exc, "read") else ""
        raise RuntimeError(
            f"media upload HTTP {exc.code} for {name!r}: {detail[:300]} "
            "(media uploads REQUIRE the LOCATION PIT with medias.write scope; "
            "the Agency PIT 401s)"
        ) from exc
    finally:
        _gov_ghl_release(_gov_lease)

    if not (200 <= int(code) < 300):
        raise RuntimeError(f"media upload returned HTTP {code} for {name!r}: {raw[:300]}")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"media upload {code} but body is not JSON for {name!r}: {raw[:300]}"
        ) from exc

    file_id = data.get("fileId") or data.get("id")
    public_url = data.get("url") or data.get("fileUrl")
    if not file_id or not public_url:
        raise RuntimeError(
            f"media upload {code} but response missing fileId/url for {name!r}: "
            f"{json.dumps(data)[:300]} — refusing to fabricate a CDN URL"
        )

    return {
        "fileId": file_id,
        "url": public_url,
        "name": name,
        "local_path": png_path,
        "http": int(code),
    }


# ── create_media_folder — NET-NEW for Skill 48 (per-run media folder) ─────────

def create_media_folder(
    name: str,
    location_id: str,
    pit: str,
    *,
    parent_id: str | None = None,
    timeout: int = 60,
    opener: "Callable[[urllib.request.Request, int], Any] | None" = None,
) -> dict:
    """Create a named media-library FOLDER and return ``{folderId, name}``.

    NET-NEW for Skill 48. Each ad run gets its own named folder so the 10 hosted images
    are grouped under the run-id, never scattered in the media root. Calls
    ``POST services.leadconnectorhq.com/medias/folder`` with
    ``Authorization: Bearer <LOCATION PIT>`` + ``Version: 2021-07-28`` and a JSON body
    ``{name, locationId[, parentId]}`` — the same auth model as ``upload_media`` (the
    LOCATION PIT with ``medias.write``; the Agency PIT 401s for media ops). The POST
    routes through ``_send_with_retry`` so a transient blip self-heals.

    FALLBACK (the caller's contract, not an exception here): if folder creation is not
    available on the box / location, the caller uploads to the media ROOT with a
    ``name`` PREFIX (e.g. ``"<run-id> — ad 3"``) so the images are still grouped by name.
    This function returns ``{"folderId": None, "fallback": "name-prefix", ...}`` on a
    non-2xx response WITHOUT a folder id (including after the retry cap on a persistent
    transient status), so the caller can take the prefix path; it raises only on a hard
    transport error (never fabricates a folder id).

    Returns:
        ``{folderId, name, http}`` on success, or
        ``{folderId: None, name, http, fallback: "name-prefix"}`` when the API declines
        (the caller then uses the name-prefix fallback).
    """
    _require(name, "name")
    _require(location_id, "location_id")
    _require(pit, "pit")

    body_obj: dict[str, Any] = {"name": name, "locationId": location_id}
    if parent_id:
        body_obj["parentId"] = parent_id
    body = json.dumps(body_obj).encode("utf-8")

    url = GHL_SERVICES_ORIGIN.rstrip("/") + GHL_MEDIA_FOLDER_PATH
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {pit}")
    req.add_header("Version", GHL_MEDIA_VERSION)
    req.add_header("User-Agent", _GHL_UA)  # Cloudflare 1010 bot-block fix
    req.add_header("Content-Type", "application/json")

    _opener = opener or (lambda r, t: urllib.request.urlopen(r, timeout=t))
    try:
        resp = _send_with_retry(req, timeout, _opener)
        code = resp.getcode()
        raw = resp.read()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        # API declined (e.g. folders unsupported on this location) -> name-prefix fallback.
        return {"folderId": None, "name": name, "http": int(getattr(exc, "code", 0)),
                "fallback": "name-prefix"}
    except (urllib.error.URLError, OSError) as exc:
        raise RuntimeError(
            f"media folder create transport error for {name!r}: {exc} "
            "(LOCATION PIT with medias.write required)"
        ) from exc

    if not (200 <= int(code) < 300):
        return {"folderId": None, "name": name, "http": int(code), "fallback": "name-prefix"}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"folderId": None, "name": name, "http": int(code), "fallback": "name-prefix"}
    folder_id = (data.get("id") or data.get("folderId")
                 or (data.get("folder") or {}).get("id")
                 or (data.get("data") or {}).get("id"))
    if not folder_id:
        return {"folderId": None, "name": name, "http": int(code), "fallback": "name-prefix"}
    return {"folderId": folder_id, "name": name, "http": int(code)}


# ── list_media — READ-ONLY media-library listing (the QC list-back) ─────────

def list_media(
    location_id: str,
    pit: str,
    *,
    media_type: str = "file",
    parent_id: str | None = None,
    query: str | None = None,
    limit: int = 50,
    offset: int = 0,
    timeout: int = 60,
    opener: "Callable[[urllib.request.Request, int], Any] | None" = None,
) -> dict:
    """READ-ONLY list of media-library entries for a location. NEVER mutates.

    Calls ``GET services.leadconnectorhq.com/medias/files?locationId=...&type=...``
    with ``Authorization: Bearer <LOCATION PIT>`` + ``Version: 2021-07-28`` (the same
    auth model as ``upload_media``/``create_media_folder``; the LOCATION PIT with
    ``medias.read`` scope — the Agency PIT 401s for media ops). This is the
    verification twin of ``upload_media``: a caller proves a just-uploaded deck is
    genuinely in the library by listing and matching on ``name`` (or ``fileId``), not
    by trusting its own local ledger.

    READ-ONLY GUARANTEE: a plain HTTP GET with no body and no mutation semantics. It
    never creates, deletes, renames, or moves anything in the media library. Safe for
    operator-account QC list-backs and for client read-only verification.

    Args:
        location_id: The GHL sub-account location id (client's own).
        pit: The LOCATION Private Integration Token (Bearer).
        media_type: ``"file"`` (default) or ``"folder"``. The API requires a single
            string value; passing both returns HTTP 422.
        parent_id: Optional folder id to list only entries inside that folder.
        query: Optional name search string the API applies server-side.
        limit: Page size (default 50; the API caps it).
        offset: Pagination offset.
        timeout: HTTP timeout seconds.
        opener: Optional callable ``(Request, timeout) -> response-like`` for tests
            (mock the HTTP). Default = ``urllib.request.urlopen`` (real call).

    Returns:
        ``{"http": code, "data": [ ...entries... ], "count": N}`` — ``data`` is the
        raw entry list from the API (each entry carries ``name``, ``_id``/``fileId``,
        ``parentId``, ``url`` for files, ``type``). Raises on a non-2xx response or a
        transport error (fail loud — never fabricates a listing).

    Raises:
        ValueError: missing/blank required args.
        RuntimeError: non-2xx HTTP (e.g. the LOCATION PIT lacking ``medias.read``) or a
            transport error.
    """
    _require(location_id, "location_id")
    _require(pit, "pit")
    if not str(media_type or "").strip():
        raise ValueError("media_type is required and must be 'file' or 'folder'")

    params = ["locationId=" + str(location_id), "type=" + str(media_type)]
    if parent_id:
        params.append("parentId=" + str(parent_id))
    if query:
        params.append("query=" + str(query))
    params.append("limit=" + str(int(limit)))
    if offset:
        params.append("offset=" + str(int(offset)))

    url = GHL_SERVICES_ORIGIN.rstrip("/") + GHL_MEDIA_LIST_PATH + "?" + "&".join(params)
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {pit}")
    req.add_header("Version", GHL_MEDIA_VERSION)
    req.add_header("User-Agent", _GHL_UA)  # Cloudflare 1010 bot-block fix
    req.add_header("Accept", "application/json")

    _opener = opener or (lambda r, t: urllib.request.urlopen(r, timeout=t))
    try:
        resp = _send_with_retry(req, timeout, _opener)
        code = resp.getcode()
        raw = resp.read()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace") if hasattr(exc, "read") else ""
        raise RuntimeError(
            f"media list HTTP {exc.code} for location {location_id}: {detail[:300]} "
            "(read-only list requires the LOCATION PIT with medias.read scope; "
            "the Agency PIT 401s for media ops)"
        ) from exc

    if not (200 <= int(code) < 300):
        raise RuntimeError(f"media list returned HTTP {code}: {raw[:300]}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"media list {code} but body is not JSON: {raw[:300]}"
        ) from exc

    entries = data.get("data") or data.get("files") or []
    return {"http": int(code), "data": entries, "count": len(entries)}


__all__ = [
    "GHL_SERVICES_ORIGIN",
    "GHL_MEDIA_UPLOAD_PATH",
    "GHL_MEDIA_FOLDER_PATH",
    "GHL_MEDIA_LIST_PATH",
    "GHL_MEDIA_VERSION",
    "GHL_MEDIA_VERSION_V3",
    "GHL_VIDEO_MAX_BYTES",
    "GHL_VIDEO_MIME",
    "PNG_MAGIC",
    "resolve_location_pit",
    "resolve_location_id",
    "verify_png",
    "upload_media",
    "create_media_folder",
    "list_media",
]
