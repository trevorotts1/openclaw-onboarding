"""HTTP seam for the public adapter.

Frozen by the GHL modernization contract ledger, 2026-10-18 (GU-004 section 1.5). The
only Version it can carry comes from the operation's official page
https://marketplace.gohighlevel.com/docs/ghl/<module>/<operation-slug>/.

Rules enforced here:

* the transport owns no version default and no version constant: the only
  ``Version`` value that can travel is the one passed per call, taken from the
  operation row;
* the transport adds no header of its own except content negotiation
  (``Accept`` / ``Content-Type``);
* the ``Authorization`` header (and cookies) is never returned in
  ``TransportResponse.headers`` and is never logged;
* the full response is captured: status, allowlisted headers, raw body bytes
  and elapsed wall time.
"""

from __future__ import annotations

import hashlib
import json
import socket
import ssl
import time
import uuid
from dataclasses import dataclass
from typing import Any, Literal, Mapping, Protocol
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from .errors import ContractViolation
from .result import ECHOED_RESPONSE_HEADERS

ErrorKind = Literal["none", "timeout", "connection", "tls", "dns", "unknown"]

DEFAULT_BASE_URL = "https://services.leadconnectorhq.com"

_STRIP_REQUEST_HEADERS = ("authorization", "proxy-authorization", "cookie", "version")


@dataclass(frozen=True)
class TransportResponse:
    status: int | None
    headers: Mapping[str, str]
    body: bytes
    error_kind: ErrorKind = "none"
    elapsed_s: float | None = None


class Transport(Protocol):
    def request(
        self,
        *,
        method: str,
        url: str,
        version: str | None,
        headers: Mapping[str, str],
        query: Mapping[str, object] | None,
        body: Mapping[str, object] | None,
        timeout_s: float,
    ) -> TransportResponse: ...


class RequestsTransport:
    """Stdlib HTTP implementation of the frozen seam.

    ``url`` is a path (``/contacts/{id}`` resolved by the adapter); the base
    URL is joined here so the adapter never owns an origin.
    """

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        opener: Any | None = None,
    ) -> None:
        self._base_url = str(base_url).rstrip("/")
        self._opener = opener

    def request(
        self,
        *,
        method: str,
        url: str,
        version: str | None,
        headers: Mapping[str, str],
        query: Mapping[str, object] | None,
        body: Mapping[str, object] | None,
        timeout_s: float,
    ) -> TransportResponse:
        target = self._absolute(url)
        encoded_query = encode_query(query)
        if encoded_query:
            target += ("&" if "?" in target else "?") + encoded_query

        request_headers = {str(k): str(v) for k, v in dict(headers or {}).items()}
        # A caller header can never smuggle a version: the row literal is the
        # only source, and "no version" means no header at all.
        for name in list(request_headers):
            if name.lower() in _STRIP_REQUEST_HEADERS:
                del request_headers[name]
        if version is not None:
            request_headers["Version"] = str(version)
        if body is not None:
            if not _has_header(request_headers, "content-type"):
                request_headers["Content-Type"] = "application/json"
        if not _has_header(request_headers, "accept"):
            request_headers["Accept"] = "application/json"

        data = None
        if body is not None:
            data = json.dumps(
                body, sort_keys=True, separators=(",", ":"), default=str
            ).encode("utf-8")

        request = urlrequest.Request(
            target,
            data=data,
            headers=request_headers,
            method=str(method).upper(),
        )

        started = time.monotonic()
        try:
            opener = self._opener or urlrequest.urlopen
            with opener(request, timeout=float(timeout_s)) as response:
                payload = response.read()
                status = response.getcode()
                response_headers = _echo_headers(response.headers.items())
        except urlerror.HTTPError as exc:
            payload = exc.read()
            status = exc.code
            response_headers = _echo_headers(exc.headers.items() if exc.headers else ())
        except (socket.timeout, TimeoutError):
            return TransportResponse(None, {}, b"", "timeout", time.monotonic() - started)
        except urlerror.URLError as exc:
            elapsed = time.monotonic() - started
            return TransportResponse(None, {}, b"", _classify(exc.reason), elapsed)
        except ssl.SSLError:
            return TransportResponse(None, {}, b"", "tls", time.monotonic() - started)
        except socket.gaierror:
            return TransportResponse(None, {}, b"", "dns", time.monotonic() - started)
        except ConnectionError:
            return TransportResponse(None, {}, b"", "connection", time.monotonic() - started)
        except OSError:
            return TransportResponse(None, {}, b"", "unknown", time.monotonic() - started)

        return TransportResponse(
            status=status,
            headers=response_headers,
            body=payload,
            error_kind="none",
            elapsed_s=time.monotonic() - started,
        )

    def request_multipart(
        self,
        *,
        method: str,
        url: str,
        version: str | None,
        headers: Mapping[str, str],
        query: Mapping[str, object] | None,
        payload: MultipartRequest,
        timeout_s: float,
        max_bytes: int | None = None,
    ) -> MultipartOutcome:
        """Send a typed multipart request built by this implementation.

        The boundary and the body are constructed here; a caller can never
        hand-set a mismatched boundary or disguise bytes as guessed JSON.  The
        target must be the operation host: a Bearer token is never attached to
        an arbitrary asset host, and a redirect is never followed.
        """

        if not isinstance(payload, MultipartRequest):
            raise ContractViolation("multipart_payload_invalid")
        cap = DEFAULT_MAX_UPLOAD_BYTES if max_bytes is None else int(max_bytes)
        if cap < 1:
            raise ContractViolation("multipart_limit_invalid")
        if payload.total_bytes > cap:
            # Refused before transport: no partial upload leaves the process.
            raise ContractViolation(
                "multipart_oversize",
                detail={"total_bytes": payload.total_bytes, "max_bytes": cap},
            )
        target = self._upload_target(url)
        encoded_query = encode_query(query)
        if encoded_query:
            target += ("&" if "?" in target else "?") + encoded_query

        boundary = "----ghlboundary" + uuid.uuid4().hex
        body = _encode_multipart(boundary, payload)
        # Hash the ACTUAL bytes that travel.
        body_hash = hashlib.sha256(body).hexdigest()

        request_headers = {str(k): str(v) for k, v in dict(headers or {}).items()}
        for name in list(request_headers):
            if name.lower() in _STRIP_REQUEST_HEADERS:
                del request_headers[name]
        if version is not None:
            request_headers["Version"] = str(version)
        request_headers["Content-Type"] = MULTIPART_MEDIA_TYPE + "; boundary=" + boundary
        request_headers["Accept"] = "application/json"

        request = urlrequest.Request(
            target, data=body, headers=request_headers, method=str(method).upper()
        )
        started = time.monotonic()
        opener = self._opener or urlrequest.build_opener(_RefuseRedirects())
        response = _perform(opener, request, float(timeout_s), started)
        evidence = dict(payload.evidence())
        evidence.update(
            {
                "body_sha256": body_hash,
                "body_bytes": len(body),
                "boundary_library_built": True,
                "redirects_followed": False,
            }
        )
        return MultipartOutcome(response=response, evidence=evidence)

    def _upload_target(self, url: str) -> str:
        text = str(url)
        if text.startswith("http://") or text.startswith("https://"):
            parsed = urlparse.urlsplit(text)
            base = urlparse.urlsplit(self._base_url)
            if parsed.scheme != "https" or parsed.netloc != base.netloc:
                # Never attach this credential to another host or plain HTTP.
                raise ContractViolation(
                    "asset_host_refused",
                    detail={"host": parsed.netloc or "", "scheme": parsed.scheme},
                )
            return text
        return self._absolute(text)

    def _absolute(self, url: str) -> str:
        text = str(url)
        if text.startswith("http://") or text.startswith("https://"):
            return text
        if not text.startswith("/"):
            text = "/" + text
        return self._base_url + text


def encode_query(query: Mapping[str, object] | None) -> str:
    if not query:
        return ""
    pairs: list[tuple[str, str]] = []
    for key in sorted(query, key=str):
        value = query[key]
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            for item in value:
                if item is not None:
                    pairs.append((str(key), _stringify(item)))
        else:
            pairs.append((str(key), _stringify(value)))
    return urlparse.urlencode(pairs)


def _stringify(value: object) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def _has_header(headers: Mapping[str, str], name: str) -> bool:
    lowered = name.lower()
    return any(str(key).lower() == lowered for key in headers)


def _echo_headers(items: Any) -> dict[str, str]:
    echoed: dict[str, str] = {}
    for key, value in items:
        if str(key).lower() in ECHOED_RESPONSE_HEADERS:
            echoed[str(key)] = str(value)
    return echoed


def _classify(reason: object) -> ErrorKind:
    if isinstance(reason, (socket.timeout, TimeoutError)):
        return "timeout"
    if isinstance(reason, ssl.SSLError):
        return "tls"
    if isinstance(reason, socket.gaierror):
        return "dns"
    if isinstance(reason, (ConnectionError, ConnectionRefusedError)):
        return "connection"
    return "unknown"


def _encode_multipart(boundary: str, payload: MultipartRequest) -> bytes:
    """Library-built body: fields first, then validated file bytes."""

    chunks: list[bytes] = []
    for name, value in sorted(dict(payload.fields or {}).items(), key=str):
        chunks.append(b"--" + boundary.encode("ascii") + b"\r\n")
        chunks.append(
            b'Content-Disposition: form-data; name="'
            + str(name).encode("utf-8")
            + b'"\r\n\r\n'
        )
        chunks.append(str(value).encode("utf-8") + b"\r\n")
    for item in payload.files:
        chunks.append(b"--" + boundary.encode("ascii") + b"\r\n")
        chunks.append(
            b'Content-Disposition: form-data; name="'
            + item.field_name.encode("utf-8")
            + b'"; filename="'
            + item.filename.encode("utf-8")
            + b'"\r\n'
        )
        chunks.append(
            b"Content-Type: " + item.content_type.encode("ascii") + b"\r\n\r\n"
        )
        chunks.append(bytes(item.content) + b"\r\n")
    chunks.append(b"--" + boundary.encode("ascii") + b"--\r\n")
    return b"".join(chunks)


def _perform(opener: Any, request: Any, timeout_s: float, started: float) -> TransportResponse:
    """One HTTP attempt with the frozen error classification."""

    try:
        with opener(request, timeout=timeout_s) as response:
            payload = response.read()
            status = response.getcode()
            response_headers = _echo_headers(response.headers.items())
    except urlerror.HTTPError as exc:
        payload = exc.read()
        status = exc.code
        response_headers = _echo_headers(exc.headers.items() if exc.headers else ())
    except (socket.timeout, TimeoutError):
        return TransportResponse(None, {}, b"", "timeout", time.monotonic() - started)
    except urlerror.URLError as exc:
        return TransportResponse(None, {}, b"", _classify(exc.reason), time.monotonic() - started)
    except ssl.SSLError:
        return TransportResponse(None, {}, b"", "tls", time.monotonic() - started)
    except socket.gaierror:
        return TransportResponse(None, {}, b"", "dns", time.monotonic() - started)
    except ConnectionError:
        return TransportResponse(None, {}, b"", "connection", time.monotonic() - started)
    except OSError:
        return TransportResponse(None, {}, b"", "unknown", time.monotonic() - started)
    return TransportResponse(
        status=status,
        headers=response_headers,
        body=payload,
        error_kind="none",
        elapsed_s=time.monotonic() - started,
    )



# ---------------------------------------------------------------------------
# Request media types (Document 1 section 21.2)
#
# A row declares its REAL request media type.  A typed JSON request and a typed
# multipart request can never be confused, and an unimplemented type is refused
# BEFORE transport - never a fake success.
# ---------------------------------------------------------------------------

JSON_MEDIA_TYPE = "application/json"
MULTIPART_MEDIA_TYPE = "multipart/form-data"
SUPPORTED_REQUEST_MEDIA_TYPES: frozenset[str] = frozenset(
    {JSON_MEDIA_TYPE, MULTIPART_MEDIA_TYPE}
)

#: Documented upload media types for the KB/course-asset families.  A type
#: outside this set is refused before a byte leaves the process.
ALLOWED_UPLOAD_TYPES: frozenset[str] = frozenset(
    {
        "text/plain",
        "text/csv",
        "text/markdown",
        "application/json",
        "application/pdf",
        "application/zip",
        "image/png",
        "image/jpeg",
        "image/webp",
        "audio/mpeg",
        "audio/wav",
        "video/mp4",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
)
DEFAULT_MAX_UPLOAD_BYTES = 25 * 1024 * 1024

_MULTIPART_FORBIDDEN_FIELDS = frozenset(
    {"authorization", "cookie", "token", "access_token", "api_key", "apikey", "pit"}
)


def resolve_request_media_type(row: object) -> str:
    """The row's declared media type, normalised.  No default is invented.

    ``None``/absent means the frozen JSON behaviour (every existing caller).
    An unknown declared type is refused rather than sent as JSON.
    """

    declared = None
    if isinstance(row, Mapping):
        declared = row.get("request_media_type")
    else:
        declared = getattr(row, "request_media_type", None)
    if declared is None or (isinstance(declared, str) and not declared.strip()):
        return JSON_MEDIA_TYPE
    text = str(declared).strip().lower()
    if text.startswith(MULTIPART_MEDIA_TYPE):
        return MULTIPART_MEDIA_TYPE
    if text == JSON_MEDIA_TYPE or text.startswith("application/json"):
        return JSON_MEDIA_TYPE
    raise ContractViolation(
        "request_media_type_unsupported", detail={"media_type": str(declared)}
    )


@dataclass(frozen=True)
class MultipartFile:
    """One validated local file reference.  Bytes, never a path guess."""

    field_name: str
    filename: str
    content_type: str
    content: bytes

    def __post_init__(self) -> None:
        for field in ("field_name", "filename", "content_type"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ContractViolation(
                    "multipart_file_incomplete", detail={"field": field}
                )
            if any(ch in value for ch in "\r\n"):
                raise ContractViolation(
                    "multipart_header_injection", detail={"field": field}
                )
        if not isinstance(self.content, (bytes, bytearray)) or not self.content:
            raise ContractViolation("multipart_file_empty")
        media = str(self.content_type).split(";")[0].strip().lower()
        if media not in ALLOWED_UPLOAD_TYPES:
            raise ContractViolation(
                "multipart_type_refused", detail={"content_type": media}
            )

    @property
    def byte_hash(self) -> str:
        return hashlib.sha256(bytes(self.content)).hexdigest()

    @property
    def size(self) -> int:
        return len(self.content)


@dataclass(frozen=True)
class MultipartRequest:
    """A typed multipart request: files plus plain text fields."""

    files: tuple[MultipartFile, ...]
    fields: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.files, tuple) or not self.files:
            raise ContractViolation("multipart_files_required")
        for item in self.files:
            if not isinstance(item, MultipartFile):
                raise ContractViolation("multipart_file_invalid")
        for name in dict(self.fields or {}):
            if str(name).strip().lower() in _MULTIPART_FORBIDDEN_FIELDS:
                # A credential never travels as a multipart field.
                raise ContractViolation(
                    "multipart_credential_field", detail={"field": str(name)}
                )
        if len({item.field_name for item in self.files}) != len(self.files):
            raise ContractViolation("multipart_field_duplicate")

    @property
    def total_bytes(self) -> int:
        return sum(item.size for item in self.files)

    def evidence(self) -> dict[str, Any]:
        """Redacted request evidence: hashes and names, never content."""

        return {
            "request_media_type": MULTIPART_MEDIA_TYPE,
            "file_count": len(self.files),
            "total_bytes": self.total_bytes,
            "files": [
                {
                    "field": item.field_name,
                    "filename": item.filename,
                    "content_type": item.content_type,
                    "size": item.size,
                    "sha256": item.byte_hash,
                }
                for item in self.files
            ],
            "fields": sorted(str(name) for name in dict(self.fields or {})),
        }


@dataclass(frozen=True)
class MultipartOutcome:
    """The HTTP response plus the request-side evidence for the receipt."""

    response: TransportResponse
    evidence: Mapping[str, Any]


class MultipartTransport(Protocol):
    def request_multipart(
        self,
        *,
        method: str,
        url: str,
        version: str | None,
        headers: Mapping[str, str],
        query: Mapping[str, object] | None,
        payload: MultipartRequest,
        timeout_s: float,
        max_bytes: int,
    ) -> MultipartOutcome: ...


class _RefuseRedirects(urlrequest.HTTPRedirectHandler):
    """A multipart body is never re-sent to a redirect target."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None


class _QuotaExceeded(Exception):
    pass


class LocationQuota:
    """Shared per-location request budget plus provider-driven backoff.

    One object per location; every route in the process consults the SAME
    object, so a throttled location cannot be escaped by switching transports
    (IG-ROUTE-05).  Time is injected so tests are deterministic.
    """

    def __init__(
        self,
        *,
        location_id: str,
        limit: int = 100,
        window_s: float = 60.0,
        max_backoff_s: float = 300.0,
    ) -> None:
        if not isinstance(location_id, str) or not location_id.strip():
            raise ContractViolation("quota_location_required")
        if int(limit) < 1:
            raise ContractViolation("quota_limit_invalid")
        if float(window_s) <= 0:
            raise ContractViolation("quota_window_invalid")
        self._location_id = str(location_id)
        self._limit = int(limit)
        self._window_s = float(window_s)
        self._max_backoff_s = float(max_backoff_s)
        self._events: list[float] = []
        self._blocked_until: float = 0.0
        self._last_backoff_s: float = 0.0
        self._attempts: int = 0

    @property
    def location_id(self) -> str:
        return self._location_id

    @property
    def attempted(self) -> int:
        return self._attempts

    def _prune(self, now: float) -> None:
        cutoff = now - self._window_s
        self._events = [ts for ts in self._events if ts > cutoff]

    def blocked_for(self, now: float) -> float:
        """Seconds the location must still wait.  ``0`` means go."""

        return max(0.0, self._blocked_until - float(now))

    def reserve(self, now: float) -> tuple[bool, float]:
        """Reserve one request slot.  (allowed, retry_after_s)."""

        wait = self.blocked_for(now)
        if wait > 0:
            return False, wait
        self._prune(now)
        if len(self._events) >= self._limit:
            oldest = self._events[0]
            return False, max(0.0, (oldest + self._window_s) - float(now))
        self._events.append(float(now))
        self._attempts += 1
        return True, 0.0

    def record_retry_after(self, seconds: float | None, *, now: float) -> float:
        """Honor the provider's reset/backoff.  Bounded, shared, no rotation."""

        try:
            value = float(seconds) if seconds is not None else 0.0
        except (TypeError, ValueError):
            value = 0.0
        if value <= 0:
            value = min(self._max_backoff_s, max(1.0, self._last_backoff_s * 2 or 1.0))
        value = min(self._max_backoff_s, value)
        self._last_backoff_s = value
        self._blocked_until = max(self._blocked_until, float(now) + value)
        return value
