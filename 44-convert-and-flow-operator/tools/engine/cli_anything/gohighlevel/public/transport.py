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

import json
import socket
import ssl
import time
from dataclasses import dataclass
from typing import Any, Literal, Mapping, Protocol
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

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
