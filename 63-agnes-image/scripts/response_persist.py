"""S63-04 - Agnes synchronous response validation and persistence.

Spec 15 sections 4 and 5:
- The image endpoint is synchronous: a 200 response carries the finished
  image at data[0].url or data[0].b64_json. No polling loop, no task ID.
- If both fields appear and one is empty, use the non-empty one (observed
  contract: the unused field is null, not a competing payload).
- Verify the payload is actually an image: nonempty bytes, media type
  sniffed from magic bytes, dimensions parsed from the real headers.
  An HTML error page must never be saved as .png.
- Persist atomically (temp file + rename) BEFORE any expiring URL is the
  sole remaining copy.
- HTTP classification: 401/403 stops (credentials, not retries); 429 is a
  bounded-backoff signal; a timeout after submission is ambiguous - do not
  blindly resubmit a paid generation.

Network access is injected (`fetcher`) so this module is fully testable
offline; the production adapter supplies the real fetcher with bounded
connection/read timeouts.
"""
from __future__ import annotations

import base64
import binascii
import os
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path


class ResponseError(ValueError):
    pass


@dataclass
class PersistedImage:
    path: str
    media_type: str          # "png" | "jpeg" | "webp" | "gif"
    width: int
    height: int
    byte_count: int

    @property
    def dimensions(self) -> str:
        return f"{self.width}x{self.height}"


def classify_http_status(status: int) -> str:
    """Return the recovery class for an HTTP status (spec sections 5, 8)."""
    if status in (401, 403):
        return "stop_credentials"      # resolve credentials or stop; never loop
    if status == 429:
        return "bounded_backoff"       # capacity signal, per-account limits
    if 500 <= status <= 599:
        return "bounded_retry"         # transient upstream, bounded
    if 400 <= status <= 499:
        return "stop_request"          # malformed/unsupported request
    return "unknown"


def classify_timeout_after_submit() -> str:
    """A timeout after submission has an ambiguous remote outcome."""
    return "ambiguous_check_before_resubmit"


# ---------------------------------------------------------------------------
# Media sniffing (magic bytes + real header dimensions; no external deps)
# ---------------------------------------------------------------------------

def sniff_media(data: bytes) -> tuple[str, int, int]:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        if len(data) < 24 or data[12:16] != b"IHDR":
            raise ResponseError("PNG signature present but IHDR missing/truncated")
        width, height = struct.unpack(">II", data[16:24])
        return "png", width, height
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg", *_jpeg_dimensions(data)
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp", *_webp_dimensions(data)
    if data.startswith((b"GIF87a", b"GIF89a")):
        if len(data) < 10:
            raise ResponseError("GIF header truncated")
        width, height = struct.unpack("<HH", data[6:10])
        return "gif", width, height
    if data.lstrip().lower().startswith((b"<!doctype", b"<html", b"{", b"[")):
        raise ResponseError("payload is text/HTML/JSON, not image bytes (refusing to save as an image)")
    raise ResponseError("unrecognized image bytes (no PNG/JPEG/WebP/GIF signature)")


def _jpeg_dimensions(data: bytes) -> tuple[int, int]:
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2):
            height, width = struct.unpack(">HH", data[i + 5:i + 9])
            return width, height
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        length = struct.unpack(">H", data[i + 2:i + 4])[0]
        if length < 2:
            break
        i += 2 + length
    raise ResponseError("JPEG SOF marker not found; cannot verify dimensions")


def _webp_dimensions(data: bytes) -> tuple[int, int]:
    chunk = data[12:16]
    if chunk == b"VP8X" and len(data) >= 30:
        width = int.from_bytes(data[24:27], "little") + 1
        height = int.from_bytes(data[27:30], "little") + 1
        return width, height
    if chunk == b"VP8 " and len(data) >= 30:
        width = struct.unpack("<H", data[26:28])[0] & 0x3FFF
        height = struct.unpack("<H", data[28:30])[0] & 0x3FFF
        return width, height
    if chunk == b"VP8L" and len(data) >= 25:
        bits = int.from_bytes(data[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    raise ResponseError("WebP dimension chunk not recognized")


# ---------------------------------------------------------------------------
# Response extraction + persistence
# ---------------------------------------------------------------------------

def extract_image_bytes(response: dict, fetcher) -> bytes:
    """Resolve the synchronous response to actual image bytes.

    `fetcher(url) -> bytes` is injected. Exactly one of url / b64_json is
    expected to be non-empty. If both are non-empty, the b64_json copy is
    used when it decodes AND carries a valid image signature; if it
    decodes to non-image bytes, the URL copy is used instead. A b64 copy
    that fails to decode likewise falls back to the URL. With no URL to
    fall back to, the decoded bytes are returned and the persistence step
    refuses them with a clear error. Both fields empty/missing is an
    error, never a placeholder.
    """
    if not isinstance(response, dict):
        raise ResponseError("provider response is not an object")
    items = response.get("data")
    if not isinstance(items, list) or not items:
        raise ResponseError("provider response has no data[0] result")
    first = items[0] or {}
    url = first.get("url") or None
    b64 = first.get("b64_json") or None
    if b64:
        try:
            raw = base64.b64decode(b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            if url:
                raw = fetcher(url)
            else:
                raise ResponseError(f"b64_json did not decode: {exc}") from exc
        if raw:
            try:
                sniff_media(raw)
                return raw
            except ResponseError:
                if url:
                    fetched = fetcher(url)
                    if fetched:
                        return fetched
                return raw
    if url:
        raw = fetcher(url)
        if raw:
            return raw
    raise ResponseError("provider response contains no usable image (url and b64_json both empty)")


def persist_image(data: bytes, dest: Path) -> PersistedImage:
    """Validate bytes as a real image and save atomically."""
    if not data:
        raise ResponseError("empty image payload")
    media_type, width, height = sniff_media(data)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(dest.parent), prefix=dest.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return PersistedImage(
        path=str(dest), media_type=media_type, width=width, height=height,
        byte_count=len(data),
    )


def handle_response(response: dict, fetcher, dest: Path) -> PersistedImage:
    """Full S63-04 path: extract -> verify -> persist atomically."""
    return persist_image(extract_image_bytes(response, fetcher), dest)
