"""Image-slot contract: slot id -> GHL media URL, shared by every page renderer.

Owner: S71. One contract for Skills 71 and 78 to 82. The image-map written by
the media upload hand-off (``image-map-upload/image-map.json``) is a list of
entries (or ``{"images": [...]}``). Each entry names one slot:

    id             slot id, unique in the map (for example ``IMG-001``, ``PKG-1``)
    ghl_media_url  the https URL the page embeds (the GHL media library URL
                   returned by the upload). Absent until the image is uploaded.
    sha256         SHA-256 of the QC'd image file. When absent, it is the hash
                   of ``asset_file`` if that file can be read.
    asset_file     the QC'd file, relative to the image-map (or the run)
    alt_text       the image's alt text

A renderer calls ``render_img`` (never hand-writes an ``<img>``): the slot id
must be in the map and must carry its uploaded URL. ``validate_page.py --mode
page`` calls ``check_page_images`` on the rendered page: every content image
must map to an entry (by ``data-image-slot``, else by its src) with a matching
src, and its bytes must hash to the QC'd file. Nothing is invented: an unknown
slot, a missing URL, a missing hash or a changed byte is an error, never a
fallback.

Deterministic, standard library only.
"""

import hashlib
import html
import json
import posixpath
import re
import urllib.parse
from pathlib import Path

SLOT_CONTRACT_VERSION = "1.0.0"
URL_KEY = "ghl_media_url"
HASH_KEY = "sha256"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class ImageSlotError(ValueError):
    """The image-map or a slot request breaks the contract."""


def load_entries(source):
    """The entry list from a path, a parsed list, or ``{"images": [...]}``."""
    data = source
    if isinstance(source, (str, Path)):
        try:
            data = json.loads(Path(source).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ImageSlotError("image-map unreadable at %s: %s" % (source, exc))
    if isinstance(data, dict):
        data = data.get("images")
    if not isinstance(data, list):
        raise ImageSlotError("image-map must be a list of entries or {\"images\": [...]}")
    return data


def _hash_of(value):
    text = str(value).strip().lower()
    if text.startswith("sha256:"):
        text = text.split(":", 1)[1].strip()
    if not _HEX64.match(text):
        raise ImageSlotError("sha256 %r is not a 64-character hex digest" % (value,))
    return text


def _file_hash(asset_file, base_dirs):
    for base in base_dirs:
        path = Path(base) / asset_file
        if path.is_file():
            return hashlib.sha256(path.read_bytes()).hexdigest()
    return None


def build_slots(source, base_dirs=()):
    """Validate the image-map and return ``{slot_id: slot}``.

    ``base_dirs`` are searched, in order, for an entry's ``asset_file`` when the
    entry carries no ``sha256``. A slot is ``{id, url, sha256, alt_text,
    asset_file, entry}``; ``url`` and ``sha256`` are None when unknown.
    """
    slots = {}
    for i, entry in enumerate(load_entries(source)):
        if not isinstance(entry, dict) or not str(entry.get("id") or "").strip():
            raise ImageSlotError("image-map entry %d has no id" % i)
        slot_id = str(entry["id"]).strip()
        if slot_id in slots:
            raise ImageSlotError("image-map slot %s appears twice" % slot_id)
        url = entry.get(URL_KEY)
        if url is not None:
            if not isinstance(url, str) or urllib.parse.urlparse(url).scheme != "https" \
                    or not urllib.parse.urlparse(url).netloc:
                raise ImageSlotError("slot %s: %s %r is not an https URL" % (slot_id, URL_KEY, url))
        asset_file = entry.get("asset_file")
        digest = entry.get(HASH_KEY)
        if digest is not None:
            digest = _hash_of(digest)
        elif asset_file:
            digest = _file_hash(str(asset_file), base_dirs)
        slots[slot_id] = {"id": slot_id, "url": url, "sha256": digest,
                          "alt_text": entry.get("alt_text") or "",
                          "asset_file": asset_file, "entry": entry}
    return slots


def slot_url(slots, slot_id):
    """The GHL media URL of a slot; refuses an unknown or not-yet-uploaded slot."""
    slot = slots.get(slot_id)
    if slot is None:
        raise ImageSlotError("slot %s is not in the image-map" % slot_id)
    if not slot["url"]:
        raise ImageSlotError("slot %s has no %s: upload the image before rendering it" % (slot_id, URL_KEY))
    return slot["url"]


def render_img(slots, slot_id, alt=None, css_class="sl-image"):
    """The one ``<img>`` every renderer emits for a slot (eager, never lazy)."""
    url = slot_url(slots, slot_id)
    text = alt if alt is not None else slots[slot_id]["alt_text"]
    if not str(text).strip():
        raise ImageSlotError("slot %s has no alt text" % slot_id)
    return '<img class="%s" data-image-slot="%s" src="%s" alt="%s" loading="eager">' % (
        html.escape(css_class, quote=True), html.escape(slot_id, quote=True),
        html.escape(url, quote=True), html.escape(str(text), quote=True))


def _strip(src):
    return src.split("#")[0].split("?")[0]


def src_matches(slot, src):
    """True when ``src`` is the slot's uploaded URL or its QC'd file."""
    bare = _strip(src)
    if slot["url"] and bare == _strip(slot["url"]):
        return True
    asset = slot["asset_file"]
    if asset:
        wanted = posixpath.normpath(str(asset).replace("\\", "/")).lstrip("./")
        path = posixpath.normpath(urllib.parse.unquote(urllib.parse.urlparse(bare).path
                                                       if "://" in bare else bare))
        return path == wanted or path.endswith("/" + wanted)
    return False


def check_page_images(slots, images, fetch):
    """Errors for rendered content images that break the slot contract.

    ``images`` are dicts with ``src`` and (optionally) ``slot``; ``fetch(src)``
    returns the bytes behind a src. Founder and logo images are checked by their
    own gates and are not passed here.
    """
    errors = []
    hashed = {}
    for img in images:
        src, slot_id = img.get("src") or "", img.get("slot")
        if slot_id:
            slot = slots.get(slot_id)
            if slot is None:
                errors.append("image src does not map to an image-map entry: %s (slot %s is not in the image-map)" % (src, slot_id))
                continue
        else:
            slot = next((s for s in slots.values() if src_matches(s, src)), None)
            if slot is None:
                errors.append("image src does not map to an image-map entry: %s (no data-image-slot and no entry's URL or file matches)" % src)
                continue
        if not src_matches(slot, src):
            errors.append("image %s src %s is neither the entry's %s nor its asset_file" % (slot["id"], src, URL_KEY))
            continue
        if slot["sha256"] is None:
            errors.append("image %s has no sha256 and no readable asset_file in the image-map: its bytes cannot be checked against the QC'd file" % slot["id"])
            continue
        if src not in hashed:
            try:
                hashed[src] = hashlib.sha256(fetch(src)).hexdigest()
            except Exception as exc:  # fetch failures are findings, not crashes
                hashed[src] = None
                errors.append("image %s could not be hashed: %s" % (slot["id"], exc))
        digest = hashed[src]
        if digest is not None and digest != slot["sha256"]:
            errors.append("image %s src bytes sha256 %s differ from the QC'd file sha256 %s" % (
                slot["id"], digest, slot["sha256"]))
    return errors
