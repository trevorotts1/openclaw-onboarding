"""Image-slot contract: slot id -> GHL media URL, shared by every page renderer.

Owner: S71. One contract for Skills 71 and 78 to 82. The image-map written by
the media upload hand-off (``image-map-upload/image-map.json``) is a list of
entries (or ``{"images": [...]}``). Each entry names one slot:

    id             slot id, unique in the map (for example ``IMG-001``, ``PKG-1``)
    ghl_media_url  the https URL the page embeds (the GHL media library URL
                   returned by the upload). Absent until the image is uploaded.
    sha256         SHA-256 of the QC'd image file. When absent, it is the hash
                   of ``asset_file`` if that file can be read.
    asset_file     the QC'd file, relative to the image-map (or the run); the
                   map stage spells it asset_path, and both are accepted
    alt_text       the image's alt text

A renderer calls ``render_img`` (never hand-writes an ``<img>``): the slot id
must be in the map and must carry its uploaded URL. ``validate_page.py --mode
page`` calls ``check_page_images`` on the rendered page: every content image
must map to an entry (by ``data-image-slot``, else by its src) with a matching
src, and its bytes must hash to the QC'd file. Nothing is invented: an unknown
slot, a missing URL, a missing hash or a changed byte is an error, never a
fallback.

``apply_hosted_urls`` is the same contract applied to a page that was authored
with local asset paths: once the upload has returned a URL, that URL replaces
the local reference, so the delivered page never asks the client's browser to
read a file on our disk.

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
    """The slot entries from a path, a parsed list, or an ``{"images": [...]}`` document.

    A document may also carry ``brand_assets`` (the client's logo, which Skill 71's map
    validator does not count as a generated master). Both lists are slots to a renderer, so
    they are returned together: the page resolves its logo by the same contract as its photos."""
    data = source
    if isinstance(source, (str, Path)):
        try:
            data = json.loads(Path(source).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ImageSlotError("image-map unreadable at %s: %s" % (source, exc))
    if isinstance(data, dict):
        images = data.get("images")
        brand = data.get("brand_assets") or []
        if isinstance(images, list) and isinstance(brand, list):
            return images + brand
        data = images
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
        # the map stage names the file asset_path, the prompt plan names it asset_file
        asset_file = entry.get("asset_file") or entry.get("asset_path")
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


_IMG_TAG = re.compile(r"<img\b[^>]*>", re.I)
_SRC_ATTR = re.compile(r"(\bsrc\s*=\s*)([\"'])([^\"']*)\2", re.I)
_SLOT_ATTR = re.compile(r"\bdata-image-slot\s*=\s*([\"'])([^\"']*)\1", re.I)


def _strip(src):
    return src.split("#")[0].split("?")[0]


def hosted_slot_for(src, slots):
    """The slot a rendered ``src`` belongs to AND that already carries its hosted URL, or None.

    A local path that matches an entry whose image has not been uploaded resolves to None:
    the caller keeps the local reference and the missing link stays visible."""
    for slot in slots.values():
        if slot["url"] and src_matches(slot, src):
            return slot
    return None


def apply_hosted_urls(html_text, slots):
    """Point every slot image on an authored page at its hosted URL.

    A renderer or an author that could only name the local asset file is rewritten to the
    ``ghl_media_url`` the upload returned, so the page the client opens carries the hosted
    asset, never a path on our disk. Only an ``<img>`` whose src matches a slot's asset file
    (or already carries its URL) is touched, and only when that slot is hosted; a src that
    matches nothing, or a slot with no URL yet, is left exactly as it was — nothing is guessed.

    Returns ``(html, changes)``, changes being ``[{slot, was, now}]`` for the caller to record.
    """
    changes = []

    def _rewrite(tag):
        slot_attr = _SLOT_ATTR.search(tag)
        src_attr = _SRC_ATTR.search(tag)
        if src_attr is None:
            return tag
        src = src_attr.group(3)
        slot = slots.get(slot_attr.group(2)) if slot_attr else None
        if slot is not None:
            if not src_matches(slot, src) or not slot["url"] or _strip(src) == _strip(slot["url"]):
                return tag
        else:
            slot = hosted_slot_for(src, slots)
            if slot is None:
                return tag
        changes.append({"slot": slot["id"], "was": src, "now": slot["url"]})
        new = _SRC_ATTR.sub(lambda m: m.group(1) + m.group(2) + slot["url"] + m.group(2), tag, count=1)
        if slot_attr is None:  # name the slot too, so check_page_images can bind it by id
            new = new[:-1] + ' data-image-slot="%s">' % html.escape(slot["id"], quote=True)
        return new

    return _IMG_TAG.sub(lambda m: _rewrite(m.group(0)), html_text), changes


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


def planned_slot_ids(document):
    """The slot ids a page request or copy spec PLANS, in page order.

    Reads both shapes the pipeline uses: a page request's
    ``sections[].slots[]`` and a copy spec's ``sections[].default_slots[]``.
    An entry's id is ``slot_id``, else ``id``. A duplicate id is an error: one
    planned slot is one picture, and two slots that share an id can never be
    told apart in the rendered page or the image map.
    """
    sections = document.get("sections") if isinstance(document, dict) else document
    if not isinstance(sections, list):
        raise ImageSlotError("planned slots: expected a page request / copy spec with a sections list")
    planned = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        for key in ("slots", "default_slots"):
            for entry in section.get(key) or []:
                if not isinstance(entry, dict):
                    continue
                slot_id = str(entry.get("slot_id") or entry.get("id") or "").strip()
                if not slot_id:
                    continue
                if slot_id in planned:
                    raise ImageSlotError("planned slots: %s is planned twice; one slot, one picture" % slot_id)
                planned.append(slot_id)
    return planned

def check_planned_coverage(planned, rendered):
    """The reverse pass: every PLANNED slot must appear in the rendered page.

    ``check_page_images`` walks the images a page happened to render, so a page
    that leaves most of its plan out still passes it. This walks the plan and
    reports each planned slot no rendered image carries. A miss is an error,
    never a warning: a twelve-slot page rendered with two pictures is the
    defect this floor exists for, and the client must not be shown it.

    ``rendered`` items are slot ids or dicts carrying ``slot`` / ``slot_id`` /
    ``id`` (the generation record's entry shape).
    """
    seen = set()
    for item in rendered:
        if isinstance(item, dict):
            value = item.get("slot") or item.get("slot_id") or item.get("id")
        else:
            value = item
        if value:
            seen.add(str(value).strip())
    planned = [str(s).strip() for s in planned]
    missing = [s for s in planned if s not in seen]
    total = len(planned)
    return ["planned image slot %s is missing from the rendered page "
            "(%d of %d planned slot(s) rendered; every planned slot must carry "
            "real photography)" % (slot_id, total - len(missing), total)
            for slot_id in missing]

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
