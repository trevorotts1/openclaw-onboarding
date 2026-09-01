#!/usr/bin/env python3
"""ghl_media.py — the Presentations department's GHL media tool (SHARED, not forked).

WHAT THIS IS
------------
The Media Librarian and Delivery Concierge upload approved slide PNGs + the final
deliverables to the client's GoHighLevel media library, AND — per the Skill-48
ad-pipeline's VERIFIED-WORKING pattern — CREATE a named media FOLDER per deck so the
images are grouped, never scattered in the media root. Rather than re-implement (and
risk drifting from) the proven REST calls, this module RE-EXPORTS the exact functions
the Skill-48 Facebook-ad generator already proved against a live GoHighLevel location:

    create_media_folder(name, location_id, pit, *, parent_id=None, opener=None)
        -> POST services.leadconnectorhq.com/medias/folder
           Authorization: Bearer <LOCATION PIT> ; Version: 2021-07-28 ;
           Content-Type: application/json ; body {name, locationId[, parentId]}
        -> {folderId, name, http} on success (201) ; {folderId: None, fallback:
           "name-prefix"} when the API declines (caller falls back to a name-prefix
           root upload). NEVER fabricates a folder id; raises only on transport error.

    upload_media(png_path, location_id, name, pit, *, parent_id=None, opener=None)
        -> POST services.leadconnectorhq.com/medias/upload-file (multipart)
           Authorization: Bearer <LOCATION PIT> ; Version: 2021-07-28 ;
           fields file / locationId / name / hosted=false / optional parentId
        -> {fileId, url, http} ; url is the PUBLIC storage.googleapis.com/msgsndr/...
           GCS object URL (login-free). FAIL-LOUD on non-2xx / missing fileId/url.

    list_media(location_id, pit, *, media_type="file", ...)
        -> READ-ONLY GET services.leadconnectorhq.com/medias/files?locationId=...
           Authorization: Bearer <LOCATION PIT> ; Version: 2021-07-28.
           The verification twin of upload_media: proves a just-uploaded deck is
           genuinely in the GHL media library by listing and matching on name/fileId.
           Plain GET, never mutates — safe for operator-account QC list-backs.

    resolve_location_pit() / resolve_location_id()  — read the canonical env names
        (GOHIGHLEVEL_API_KEY then GHL_API_KEY ; GOHIGHLEVEL_LOCATION_ID then
        GHL_LOCATION_ID). For a CLIENT deck these resolve the CLIENT's LOCATION PIT —
        never the operator's key, never an agency PIT (the agency PIT 401s for media).

CONTRACT PARITY (why this is safe)
----------------------------------
This module imports the canonical `tools/ghl_media.py` from `48-facebook-ad-generator`
by repo-relative path and re-exports its symbols UNCHANGED. There is exactly ONE
implementation of the folder-create / upload calls in the repo; the Presentations
pipeline calls the identical, verified-working code (same origin, same
`POST /medias/folder`, same `Version: 2021-07-28` header, same LOCATION-PIT auth,
same response-id parsing). If the Skill-48 call is correct (it returns 201 against the
client's location), the Presentations call is correct by construction.

NO BROWSER, EVER
----------------
The GoHighLevel media library is touched ONLY via this Tier-3 REST module. Driving the
GHL web UI with agent-browser / Playwright / Puppeteer / any UI automation is FORBIDDEN
(see the Media Librarian + Delivery Concierge SOPs and the master delivery note).
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


def _find_canonical_ghl_media() -> Path:
    """Locate the verified-working tools/ghl_media.py shipped by the Skill-48
    Facebook-ad generator. Resolves in every layout the Presentations dept can
    run from. PRIORITY (FIX-23(d) — the GHL co-location fix):

      1. Co-located _skill48_ghl_media.py next to THIS module — the materializer
         (create_role_workspaces.py) copies the CANONICAL repo module here on
         every floor-fill, so this is the AUTHORITATIVE, always-current copy for
         a deployed department. A deployed box must never silently fall back to
         a stale installed Skill-48 sibling (measured: the installed
         ~/.openclaw/skills/48-facebook-ad-generator/tools/ghl_media.py was a
         22KB pre-list_media version while the repo's verified-working module is
         25KB — a stale sibling would silently fork the media contract).
      2. Repo tree:       walking up from this file to the repo root (the dir
                           that contains 48-facebook-ad-generator).
      3. Skills tree:     the OpenClaw skills dir where Skill-48 actually lands
                           on a box (~/.openclaw/skills or /data/.openclaw/skills
                           on a VPS, i.e. OC_SKILLS_DIR) — used only when no
                           co-located copy and no repo sibling exist.

    Raises if not found (fail loud rather than silently fork the proven REST
    calls). GATE 1b asserts this import under the render interpreter BEFORE any
    render spend."""
    here = Path(__file__).resolve()
    # 1. Self-contained co-located copy (materializer-installed sibling) — FIRST,
    #    so a deployed department always loads the canonical, always-current module.
    local = here.parent / "_skill48_ghl_media.py"
    if local.is_file():
        return local
    # 2. Repo tree: walk up for a sibling 48-facebook-ad-generator dir.
    for parent in here.parents:
        cand = parent / "48-facebook-ad-generator" / "tools" / "ghl_media.py"
        if cand.is_file():
            return cand
    # 3. Deployed box: the OpenClaw skills tree (Skill-48 installs here) — last
    #    resort, because the installed copy can lag the repo's canonical module.
    for skills_root in (
        Path(os.environ.get("OPENCLAW_SKILLS_DIR", "")),
        Path.home() / ".openclaw" / "skills",
        Path("/data/.openclaw/skills"),
    ):
        if not skills_root or not skills_root.is_dir():
            continue
        cand = skills_root / "48-facebook-ad-generator" / "tools" / "ghl_media.py"
        if cand.is_file():
            return cand
    raise FileNotFoundError(
        "canonical ghl_media.py not found — expected a co-located "
        "_skill48_ghl_media.py next to this module, "
        "<repo>/48-facebook-ad-generator/tools/ghl_media.py, or "
        "<skills>/48-facebook-ad-generator/tools/ghl_media.py (the verified-working "
        "GHL media folder-create + upload module the Presentations dept SHARES). The "
        "dept must never fork these REST calls; install the Skill-48 sibling "
        "(48-facebook-ad-generator) or run the materializer to co-locate it."
    )


_CANON_PATH = _find_canonical_ghl_media()
_spec = importlib.util.spec_from_file_location("_ghl_media_canonical", str(_CANON_PATH))
_canon = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("_ghl_media_canonical", _canon)
_spec.loader.exec_module(_canon)  # type: ignore[union-attr]

# Re-export the proven symbols UNCHANGED (single source of truth). NOTE: `upload_media`
# is NOT re-exported raw; it is WRAPPED below by a fail-closed DECK-artifact gate (the
# lowest GHL upload chokepoint). `create_media_folder` is the OTHER exception — it is
# NOT re-exported raw either; it is DISABLED (FIX 36) below.
list_media = _canon.list_media
list_media = _canon.list_media
resolve_location_pit = _canon.resolve_location_pit
resolve_location_id = _canon.resolve_location_id
verify_png = _canon.verify_png
GHL_SERVICES_ORIGIN = _canon.GHL_SERVICES_ORIGIN
GHL_MEDIA_UPLOAD_PATH = _canon.GHL_MEDIA_UPLOAD_PATH
GHL_MEDIA_FOLDER_PATH = _canon.GHL_MEDIA_FOLDER_PATH
GHL_MEDIA_LIST_PATH = _canon.GHL_MEDIA_LIST_PATH
GHL_MEDIA_VERSION = _canon.GHL_MEDIA_VERSION
GHL_MEDIA_VERSION_V3 = _canon.GHL_MEDIA_VERSION_V3
GHL_VIDEO_MAX_BYTES = _canon.GHL_VIDEO_MAX_BYTES
GHL_VIDEO_MIME = _canon.GHL_VIDEO_MIME

CANONICAL_SOURCE = str(_CANON_PATH)


# ===========================================================================
# FIX 36 — FOLDER-CREATE IS DISABLED (doc-vs-code reconciliation).
# ===========================================================================
# CLIENT-WEBINAR-DECK-SOP (BINDING "how GHL is touched") says: "The agent NEVER
# creates a GHL folder (the folder-create endpoint returns 404; folders are made
# by a human in the GHL UI and the id is passed as parentId, else upload to the
# shareable media root)." Until FIX 36 this module re-exported the Skill-48
# folder-create call RAW, and ghl_media_push treated a 201 as the PRIMARY path —
# directly contradicting the documented 404. Resolved fail-closed:
#   * create_media_folder stays a PRESENT attribute (import compatibility +
#     the import-surface contract) but NEVER issues the POST. Every call returns
#     the documented-declined shape {folderId: None, fallback: "name-prefix"}
#     WITHOUT any network traffic, so a caller that ignores the decline falls
#     through to the pre-existing, human-approved intake folder id or the media
#     root — exactly the SOP's two legal outcomes.
#   * To keep the Skill-48 canonical call reachable for the AD pipeline (the one
#     place the endpoint is genuinely used), the raw symbol remains importable as
#     CANON_CREATE_MEDIA_FOLDER. The PRESENTATIONS department never calls it.
# The canonical Skill-48 module itself is NOT forked or modified (shared source
# of truth preserved); the disable lives entirely in this dept-side layer.

def create_media_folder(name, location_id, pit, *, parent_id=None, opener=None):
    """DISABLED per CLIENT-WEBINAR-DECK-SOP (the folder-create endpoint returns
    404 for this department's use). NEVER POSTs. Returns the documented
    declined shape so callers fall back to the human-approved folder id
    (intake.json.ghl_media_folder_id) or the shareable media root."""
    return {"folderId": None, "name": str(name), "fallback": "name-prefix",
            "http": None, "disabled": "fix36-folder-create-endpoint-returns-404"}

CANON_CREATE_MEDIA_FOLDER = _canon.create_media_folder

# ===========================================================================
# THE LOWEST GHL UPLOAD CHOKEPOINT — fail-closed DECK-artifact tripwire (v16.1.2).
# ===========================================================================
# Until v16.1.2 this module re-exported the canonical `upload_media` RAW, so a direct
# `ghl_media.upload_media(deck.pptx, ...)` — the function `ghl_media_push.push_deck_media`
# wraps — could host a deck to the client's GHL media library WITHOUT the out-of-band
# delivery boundary gate (the gate only ran INSIDE push_deck_media / runner P9). That was
# the residual code bypass. `upload_media` is now a GATED WRAPPER: every DECK artifact
# (.pptx / the canonical *-FINAL.pdf) MUST pass delivery_gate.gate_delivered_artifact
# (PRE-TRANSPORT, fail-closed) BEFORE the actual GHL POST, so a deck that did not go
# through the governed kie.ai pipeline CANNOT be uploaded no matter who calls this. The
# governed path (push_deck_media / runner P9) produces exactly the provenance the gate
# requires, so it passes and does NOT self-block. NON-DECK media (slide PNGs, hero/logo
# images, presenter guide/speech PDFs, audio) is NOT a deck and flows straight through to
# the canonical REST upload UNCHANGED — ordinary media is never false-blocked.
# ---------------------------------------------------------------------------
_DECK_PPTX_SUFFIXES = (".pptx",)


def _is_deck_artifact(path) -> bool:
    """Conservative DECK-artifact predicate. True ONLY for a final assembled deck: a
    ``.pptx``, or the canonical deck PDF (named ``*-FINAL.pdf``). Deliberately NARROW so
    ordinary media is NEVER gated — slide / hero / logo images (.png/.jpg/.jpeg/.webp),
    the presenter guide / speech PDFs (``PRESENTER-GUIDE.pdf`` / ``PRESENTERS-SPEECH.pdf``,
    which are NOT ``-FINAL.pdf``), audio (.mp3) and everything else return False and
    upload untouched. This matches the deck-PDF naming the delivery gate's own
    `_categorize` treats as the deck (``name.endswith('-FINAL.pdf')``)."""
    name = Path(str(path)).name.lower()
    return name.endswith(_DECK_PPTX_SUFFIXES) or name.endswith("-final.pdf")


def upload_media(png_path, location_id, name, pit, *, hosted=False, parent_id=None,
                 timeout=300, opener=None, require_png=True, run_dir=None):
    """GATED upload chokepoint — wraps the canonical, verified-working ``upload_media``.

    NON-DECK media (images / slide PNGs / guide & speech PDFs / audio) is delegated to the
    canonical REST upload UNCHANGED (the PNG magic-byte check still applies via
    ``require_png``; behavior is byte-for-byte identical to the pre-v16.1.2 re-export).

    DECK artifact (``.pptx`` / ``*-FINAL.pdf``) -> the out-of-band delivery boundary gate
    (``delivery_gate.gate_delivered_artifact``, PRE-TRANSPORT mode) runs INLINE,
    fail-closed, BEFORE any network call. A hand-built / overlay (AF-OVERLAY-DELIVERED),
    not-kie (AF-NOT-KIE-RENDERED), no-governed-run-dir (AF-NO-RUN-DIR) or
    incomplete-bundle (AF-BUNDLE-COMPLETE) deck is REJECTED — this raises
    ``delivery_gate.DeliveryGateRejected`` and NOTHING is uploaded. On PASS the deck is
    hosted through the SAME canonical upload with ``require_png=False`` (a deck is
    legitimately not a PNG; the REST call is never forked). The ONLY bypass is a logged
    owner_skip_approval token, honored inside ``gate_delivered_artifact``.

    ``run_dir`` is an OPTIONAL hint used ONLY to resolve the governed run dir for a deck
    (the governed caller ``push_deck_media`` passes it); it is NEVER forwarded to the
    canonical REST call. When omitted the gate resolves the run dir by walking up from the
    artifact, and a deck with no governed run dir is REJECTED (AF-NO-RUN-DIR)."""
    if _is_deck_artifact(png_path):
        # Lazy import: keeps this module's load surface stdlib + canonical only, with no
        # import-order coupling (delivery_gate is stdlib-only at module load).
        import delivery_gate  # noqa: WPS433
        ok, reasons = delivery_gate.gate_delivered_artifact(
            png_path, run_dir, verify_destinations=False)
        if not ok:
            hard = [r for r in reasons if not str(r).startswith("NOTE")]
            raise delivery_gate.DeliveryGateRejected(hard or reasons)
        # Gate PASSED — host the deck through the single proven REST call (no fork).
        return _canon.upload_media(png_path, location_id, name, pit, hosted=hosted,
                                   parent_id=parent_id, timeout=timeout, opener=opener,
                                   require_png=False)
    # Non-deck media: the canonical path, entirely unchanged.
    return _canon.upload_media(png_path, location_id, name, pit, hosted=hosted,
                               parent_id=parent_id, timeout=timeout, opener=opener,
                               require_png=require_png)


# ===========================================================================
# v3 VIDEO upload — the 500MB tier, SMALL-PROBE-GATED (v17). NOT a fork.
# ===========================================================================
# GHL media offers TWO tiers: the regular "2021-07-28" tier caps files at 25MB, and
# the v3 tier grants 500MB for VIDEO. The tier is selected per-request by the
# ``Version`` header — ``v3`` (with the multipart file part declared
# ``Content-Type: video/mp4``) for the video tier, ``2021-07-28`` for regular media.
# The REST call underneath is the SAME verified-working canonical
# ``POST /medias/upload-file`` (same multipart encoder, same bounded retry, same
# Cloudflare-1010 Browser-UA) — only the ``Version`` header and the file part's
# declared content type differ. So a 500MB video can be hosted WITHOUT forking the
# proven upload path, and a video that slips past the 25MB regular-tier cap is not
# silently 413'd: it uses the tier that allows it.
#
# SMALL-PROBE GATE: before the real (potentially huge) upload, ``verify_video`` runs
# a cheap local probe of the artifact — it must (1) exist, (2) be non-empty, (3) be
# within the 500MB v3 ceiling, and (4) start with an MP4 ftyp box (the ISO-BMFF
# container signature). A non-MP4 or oversized file is refused BEFORE any network
# spend — the same fail-closed posture as ``verify_png`` for the image tier. The
# probe is deliberately local (no network): it cannot leak a credential and it fails
# instantly on a stub, not after a multi-hundred-MB transfer.
_MP4_FTYP_MAGIC = b"ftyp"


def verify_video(path) -> bool:
    """SMALL-PROBE: True iff ``path`` is a plausible v3-uploadable MP4 video.

    Cheap, LOCAL, no-network pre-flight used before the real v3 video upload. Returns
    False for a missing / empty / over-500MB file, or a file whose first box is not the
    ISO-BMFF ``ftyp`` container signature (bytes 4:8 of the MP4 header) — i.e. not an
    MP4 at all. Mirrors ``verify_png`` (the image-tier guard) so a stub or a
    wrong-tier artifact is refused before any network spend."""
    p = Path(str(path))
    if not p.is_file():
        return False
    size = p.stat().st_size
    if size <= 0:
        return False
    if size > GHL_VIDEO_MAX_BYTES:
        return False
    with open(p, "rb") as f:
        head = f.read(8)
    return len(head) == 8 and head[4:8] == _MP4_FTYP_MAGIC


def upload_video(video_path, location_id, name, pit, *, parent_id=None, timeout=900,
                 opener=None, require_video=True):
    """Host a VIDEO (up to 500MB) to the GHL media library via the v3 tier.

    The v3 video tier is selected by sending ``Version: v3`` (instead of the regular
    tier's ``Version: 2021-07-28``) and declaring the multipart file part as
    ``Content-Type: video/mp4``. The REST call is otherwise the IDENTICAL
    verified-working canonical ``upload_media`` — same ``POST /medias/upload-file``
    endpoint, same multipart encoder, same bounded retry, same Browser-UA — so this
    wrapper never forks the proven upload path, it only chooses the tier that allows
    the file size.

    SMALL-PROBE: ``verify_video`` runs BEFORE any network call (fail-closed): the file
    must exist, be non-empty, be <= 500MB, and carry an MP4 ``ftyp`` box. A missing /
    oversized / non-MP4 file raises ``ValueError`` with zero bytes sent. Set
    ``require_video=False`` to lift the MP4-magic check for a proven non-MP4 video
    container (the file must still exist and be within the 500MB ceiling).

    Args:
        video_path: Local MP4 video to upload (validated by the small probe).
        location_id: The GHL sub-account location id (client's own).
        name: Human-friendly media-library name.
        pit: The LOCATION Private Integration Token (Bearer).
        parent_id: Optional FOLDER id (``parentId``) — videos land in the media root
            when omitted.
        timeout: HTTP timeout seconds (default 900 — video uploads are large).
        opener: Optional callable ``(Request, timeout) -> response-like`` for tests
            (mock the HTTP). Default = ``urllib.request.urlopen`` (real call).
        require_video: When True (DEFAULT), the file MUST pass the MP4 small probe
            before the real upload. When False, only existence + the 500MB ceiling are
            checked (for a caller that has already proven a non-MP4 video container).

    Returns:
        ``{fileId, url, name, local_path, http, tier, content_type}`` — ``url`` is the
        public GCS URL; ``tier`` is ``"v3"`` and ``content_type`` is ``video/mp4``.

    Raises:
        ValueError: missing args, a non-MP4 file when ``require_video``, a file over
            the 500MB ceiling, or a non-existent file when ``require_video=False``.
        RuntimeError: non-2xx HTTP, or a 2xx response missing ``fileId``/``url``
            (never fabricates a CDN URL).
    """
    if not video_path or not str(video_path).strip():
        raise ValueError("video_path is required and must be non-empty")
    _canon._require(location_id, "location_id")
    _canon._require(name, "name")
    _canon._require(pit, "pit")
    if require_video:
        if not verify_video(video_path):
            raise ValueError(
                f"refusing to upload {video_path!r}: small probe failed — file must "
                f"exist, be non-empty, be <= {GHL_VIDEO_MAX_BYTES} bytes (500MB v3 "
                "video ceiling), and start with an MP4 ftyp box. Nothing was sent."
            )
    elif not os.path.isfile(video_path):
        raise ValueError(
            f"refusing to upload {video_path!r}: file does not exist (require_video=False "
            "lifts the MP4-magic check, not the existence or size-ceiling checks)"
        )
    size = os.path.getsize(video_path)
    if size > GHL_VIDEO_MAX_BYTES:
        raise ValueError(
            f"refusing to upload {video_path!r}: {size} bytes exceeds the {GHL_VIDEO_MAX_BYTES}"
            "-byte (500MB) v3 video ceiling — the regular 25MB tier would 413, and the "
            "v3 tier still cannot take a file this large."
        )

    # Same canonical REST call, video tier: Version: v3 + video/mp4 file part.
    res = _canon.upload_media(video_path, location_id, name, pit, hosted=False,
                              parent_id=parent_id, timeout=timeout, opener=opener,
                              require_png=False, file_content_type=GHL_VIDEO_MIME,
                              version=GHL_MEDIA_VERSION_V3)
    # Tag the v3 tier + declared content type so a caller (or a QC list-back) can prove
    # WHICH tier hosted the file without re-inspecting the wire.
    res["tier"] = GHL_MEDIA_VERSION_V3
    res["content_type"] = GHL_VIDEO_MIME
    return res


__all__ = [
    "create_media_folder",
    "upload_media",
    "upload_video",
    "list_media",
    "resolve_location_pit",
    "resolve_location_id",
    "verify_png",
    "verify_video",
    "GHL_SERVICES_ORIGIN",
    "GHL_MEDIA_UPLOAD_PATH",
    "GHL_MEDIA_FOLDER_PATH",
    "GHL_MEDIA_LIST_PATH",
    "GHL_MEDIA_VERSION",
    "GHL_MEDIA_VERSION_V3",
    "GHL_VIDEO_MAX_BYTES",
    "GHL_VIDEO_MIME",
    "CANONICAL_SOURCE",
]


if __name__ == "__main__":  # tiny self-describe (no network)
    print(f"ghl_media.py (Presentations) SHARES: {CANONICAL_SOURCE}")
    print(f"  folder-create: POST {GHL_SERVICES_ORIGIN}{GHL_MEDIA_FOLDER_PATH} "
          f"(Version: {GHL_MEDIA_VERSION}, Bearer LOCATION PIT)")
    print(f"  upload:        POST {GHL_SERVICES_ORIGIN}{GHL_MEDIA_UPLOAD_PATH} "
          f"(Version: {GHL_MEDIA_VERSION}, multipart, optional parentId)")
    print(f"  upload_video:  POST {GHL_SERVICES_ORIGIN}{GHL_MEDIA_UPLOAD_PATH} "
          f"(Version: {GHL_MEDIA_VERSION_V3}, Content-Type: {GHL_VIDEO_MIME}, "
          f"small-probe gated, up to {GHL_VIDEO_MAX_BYTES} bytes)")
    _ = os.environ  # keys are read lazily by resolve_* at call time
