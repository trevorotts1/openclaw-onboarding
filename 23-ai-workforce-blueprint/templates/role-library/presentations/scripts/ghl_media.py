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
    Facebook-ad generator. Walks up from this file to the repo root (the dir that
    contains 48-facebook-ad-generator) so it resolves in the repo AND on a deployed
    client box where the sibling skill dirs are present. Raises if not found
    (fail loud rather than silently fork the proven REST calls)."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        cand = parent / "48-facebook-ad-generator" / "tools" / "ghl_media.py"
        if cand.is_file():
            return cand
    raise FileNotFoundError(
        "canonical ghl_media.py not found — expected "
        "<repo>/48-facebook-ad-generator/tools/ghl_media.py (the verified-working "
        "GHL media folder-create + upload module the Presentations dept SHARES). "
        "The dept must never fork these REST calls; ship the sibling skill dir."
    )


_CANON_PATH = _find_canonical_ghl_media()
_spec = importlib.util.spec_from_file_location("_ghl_media_canonical", str(_CANON_PATH))
_canon = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("_ghl_media_canonical", _canon)
_spec.loader.exec_module(_canon)  # type: ignore[union-attr]

# Re-export the proven symbols UNCHANGED (single source of truth).
create_media_folder = _canon.create_media_folder
upload_media = _canon.upload_media
resolve_location_pit = _canon.resolve_location_pit
resolve_location_id = _canon.resolve_location_id
verify_png = _canon.verify_png
GHL_SERVICES_ORIGIN = _canon.GHL_SERVICES_ORIGIN
GHL_MEDIA_UPLOAD_PATH = _canon.GHL_MEDIA_UPLOAD_PATH
GHL_MEDIA_FOLDER_PATH = _canon.GHL_MEDIA_FOLDER_PATH
GHL_MEDIA_VERSION = _canon.GHL_MEDIA_VERSION

CANONICAL_SOURCE = str(_CANON_PATH)

__all__ = [
    "create_media_folder",
    "upload_media",
    "resolve_location_pit",
    "resolve_location_id",
    "verify_png",
    "GHL_SERVICES_ORIGIN",
    "GHL_MEDIA_UPLOAD_PATH",
    "GHL_MEDIA_FOLDER_PATH",
    "GHL_MEDIA_VERSION",
    "CANONICAL_SOURCE",
]


if __name__ == "__main__":  # tiny self-describe (no network)
    print(f"ghl_media.py (Presentations) SHARES: {CANONICAL_SOURCE}")
    print(f"  folder-create: POST {GHL_SERVICES_ORIGIN}{GHL_MEDIA_FOLDER_PATH} "
          f"(Version: {GHL_MEDIA_VERSION}, Bearer LOCATION PIT)")
    print(f"  upload:        POST {GHL_SERVICES_ORIGIN}{GHL_MEDIA_UPLOAD_PATH} "
          f"(Version: {GHL_MEDIA_VERSION}, multipart, optional parentId)")
    _ = os.environ  # keys are read lazily by resolve_* at call time
