#!/usr/bin/env python3
"""ghl_media_push.py — host a deck's approved images + final deliverables in GHL.

The Media Librarian's mechanical upload half. Per the VERIFIED-WORKING Skill-48
pattern (ghl_media.create_media_folder, POST /medias/folder, Version 2021-07-28,
client LOCATION PIT), it:

  1. CREATES a named per-deck media folder ("DECK <deck-slug>") so the slide images
     are grouped under the deck, never scattered in the media root. Folder-create is
     the PRIMARY path (it returns 201 against a correctly-scoped client LOCATION PIT).
  2. If the API DECLINES folder-create (returns no folder id), falls back to (a) a
     human-supplied folder id from intake.json.ghl_media_folder_id, else (b) the
     media ROOT with a "<deck-slug> — " name PREFIX so the images stay grouped by
     name. Either way `ghl_folder_id` is recorded ("root" is a valid passing value).
  3. Uploads each approved PNG (+ the final PPTX/PDF when given) via
     ghl_media.upload_media (POST /medias/upload-file, multipart, parentId), recording
     the public storage.googleapis.com URL + fileId per file to media_library.json.

FORBIDDEN: driving the GoHighLevel UI in a browser (agent-browser / Playwright /
Puppeteer / any UI automation). The media library is touched ONLY via this REST path.

Idempotent per file (the basename is the ledger key) so a retry never re-uploads.
Fail-loud: a missing LOCATION PIT raises; a non-PNG is refused; an upload returning no
fileId/url raises. No fabricated CDN URLs, ever.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ghl_media  # noqa: E402  (the SHARED, verified-working module)


def _read_json(p: Path):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return {}


def push_deck_media(run_dir: Path, images: list, *, deck_slug: str | None = None,
                    extra_files: list | None = None, opener=None) -> dict:
    """Create the per-deck folder and upload the approved images (+ extra files).
    Returns a media_library.json-shaped dict (also written to disk)."""
    run_dir = Path(run_dir).resolve()
    intake = _read_json(run_dir / "working" / "copy" / "intake.json")
    slug = (deck_slug or intake.get("deck_slug") or run_dir.name).strip()

    pit = ghl_media.resolve_location_pit()        # client's LOCATION PIT (never operator's)
    location_id = ghl_media.resolve_location_id()  # client's location id

    # 1) PRIMARY: create the per-deck media folder via the verified POST /medias/folder.
    folder = ghl_media.create_media_folder(f"DECK {slug}", location_id, pit, opener=opener)
    parent_id = folder.get("folderId")
    # 2) FALLBACK chain when the API declined folder-create.
    if not parent_id:
        human_folder = str(intake.get("ghl_media_folder_id") or "").strip()
        if human_folder:
            parent_id = human_folder
    name_prefix = "" if parent_id else f"{slug} — "
    ghl_folder_id = parent_id or "root"

    uploaded = []
    ledger_path = run_dir / "working" / "delivery" / "media_library.json"
    ledger = _read_json(ledger_path) if ledger_path.exists() else {}
    done = {e.get("local_path"): e for e in ledger.get("uploaded", [])
            if isinstance(e, dict)}

    for f in list(images) + list(extra_files or []):
        f = str(f)
        if f in done:
            uploaded.append(done[f])           # idempotent: already hosted this file
            continue
        name = f"{name_prefix}{Path(f).name}"
        res = ghl_media.upload_media(f, location_id, name, pit,
                                     parent_id=parent_id, opener=opener)
        uploaded.append({"local_path": f, "name": name, "public_url": res["url"],
                         "file_id": res["fileId"], "http_status": res["http"],
                         "ghl_folder_id": ghl_folder_id})

    out = {
        "deck_slug": slug,
        "ghl_folder_id": ghl_folder_id,
        "ghl_folder_created_via_api": bool(folder.get("folderId")),
        "uploaded": uploaded,
        "upload_count": len(uploaded),
    }
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger.update(out)
    ledger_path.write_text(json.dumps(ledger, indent=2))
    return out


def main():
    ap = argparse.ArgumentParser(description="Host a deck's images + deliverables in GHL.")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--deck-slug", default=None)
    ap.add_argument("--images", nargs="*", default=None)
    ap.add_argument("--extra", nargs="*", default=None,
                    help="extra deliverables to upload (final PPTX/PDF).")
    args = ap.parse_args()
    rd = Path(args.run_dir).resolve()
    imgs = args.images
    if not imgs:
        imgs = sorted(str(p) for p in (rd / "renders").glob("slide-*.png"))
    if not imgs:
        print("FATAL: no images to host (pass --images or populate renders/).",
              file=sys.stderr)
        sys.exit(2)
    res = push_deck_media(rd, imgs, deck_slug=args.deck_slug, extra_files=args.extra)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
