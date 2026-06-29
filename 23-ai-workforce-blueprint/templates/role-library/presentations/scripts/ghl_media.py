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

# Re-export the proven symbols UNCHANGED (single source of truth). NOTE: `upload_media`
# is the ONE exception — it is NOT re-exported raw; it is WRAPPED below by a fail-closed
# DECK-artifact gate (the lowest GHL upload chokepoint). Every other symbol, and the
# actual REST upload underneath the wrapper, is the canonical, verified-working code.
create_media_folder = _canon.create_media_folder
resolve_location_pit = _canon.resolve_location_pit
resolve_location_id = _canon.resolve_location_id
verify_png = _canon.verify_png
GHL_SERVICES_ORIGIN = _canon.GHL_SERVICES_ORIGIN
GHL_MEDIA_UPLOAD_PATH = _canon.GHL_MEDIA_UPLOAD_PATH
GHL_MEDIA_FOLDER_PATH = _canon.GHL_MEDIA_FOLDER_PATH
GHL_MEDIA_VERSION = _canon.GHL_MEDIA_VERSION

CANONICAL_SOURCE = str(_CANON_PATH)


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
