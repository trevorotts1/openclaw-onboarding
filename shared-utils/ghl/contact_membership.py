#!/usr/bin/env python3
"""Read-only GHL (Convert and Flow) contact membership and order lookup.

The Black Friday entitlement gate must not trust a string the builder wrote. This
module reads the client's own GHL contact record (its tags) and, for a purchase,
the order record, through ONE read-only path:

  * every request goes through ``read(transport, path, query)``, which sends the
    verb GET and nothing else; a transport asked for anything else is refused
    before any network call;
  * the live transport (``LiveReadTransport``) can only build GET requests;
  * the PIT comes from the environment and never reaches a log or an exception.

Routes: ``GET /contacts/{contactId}`` is the verified W2A contract route
(capability_inventory ``contacts.get``). ``GET /payments/orders/{orderId}`` is NOT
in the W2A inventory; its response shape below is the documented public API and is
UNVERIFIED live until a capture on an approved test location exists.

Runnable check:
    python3 shared-utils/ghl/contact_membership.py
"""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

REST_BASE = "https://services.leadconnectorhq.com"
REST_VERSION = "2021-07-28"
TOKEN_ENV = "GOHIGHLEVEL_API_KEY"
LOCATION_ENV = "GOHIGHLEVEL_LOCATION_ID"
CREDENTIAL_FIX = (
    f"set {TOKEN_ENV} (location PIT) and {LOCATION_ENV} so the contact record can "
    "be read; entitlement is never accepted on a string alone"
)


class LookupFailed(Exception):
    """A lookup that did not return a usable record. ``kind`` is stable."""

    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(f"{kind}: {detail}")
        self.kind = kind  # "unresolved" (404) | "unavailable" (anything else)
        self.detail = detail


Response = Tuple[int, Optional[Dict[str, Any]]]


def read(transport: Any, path: str, query: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """The only request this module makes: GET. Raises LookupFailed otherwise."""
    status, body = transport.request("GET", path, dict(query or {}))
    if status == 404:
        raise LookupFailed("unresolved", f"{path} does not exist (http 404)")
    if status != 200 or not isinstance(body, dict):
        raise LookupFailed("unavailable", f"{path} could not be read (http {status})")
    return body


class LiveReadTransport:
    """GET-only HTTPS transport over the public REST API + location PIT."""

    def __init__(self, token: str, location_id: str, timeout: float = 30.0) -> None:
        if not token or not location_id:
            raise LookupFailed("unavailable", CREDENTIAL_FIX)
        self._token = token
        self.location_id = location_id
        self._timeout = timeout

    @classmethod
    def from_env(cls) -> "LiveReadTransport":
        return cls(os.environ.get(TOKEN_ENV, ""), os.environ.get(LOCATION_ENV, ""))

    def request(self, method: str, path: str, query: Dict[str, str]) -> Response:
        if method != "GET":
            raise ValueError(f"read-only transport refuses {method}")
        url = REST_BASE + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        req = urllib.request.Request(url, method="GET", headers={
            "Authorization": "Bearer " + self._token, "Version": REST_VERSION})
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
                status = getattr(resp, "status", None) or resp.getcode()
        except urllib.error.HTTPError as exc:
            return exc.code, None
        except (socket.timeout, urllib.error.URLError, OSError):
            return 0, None
        try:
            data = json.loads(raw)
        except ValueError:
            return status, None
        return status, data if isinstance(data, dict) else None


class StaticReadTransport:
    """Offline stand-in: serves fixed GET responses, records every request.

    ``routes`` maps a path to a response body. Any non-GET verb is refused, so a
    test can prove the lookup never writes (``requests`` lists what was sent).
    """

    def __init__(self, routes: Dict[str, Dict[str, Any]], location_id: str = "loc-a") -> None:
        self.routes = dict(routes)
        self.location_id = location_id
        self.requests: List[Tuple[str, str, Dict[str, str]]] = []

    def request(self, method: str, path: str, query: Dict[str, str]) -> Response:
        self.requests.append((method, path, dict(query)))
        if method != "GET":
            raise ValueError(f"read-only transport refuses {method}")
        body = self.routes.get(path)
        return (200, body) if body is not None else (404, None)


def contact_tags(transport: Any, contact_id: str) -> List[str]:
    """Tags on the client's own contact record (GET /contacts/{id})."""
    body = read(transport, "/contacts/" + urllib.parse.quote(contact_id, safe=""))
    contact = body.get("contact", body)
    tags = contact.get("tags") if isinstance(contact, dict) else None
    if not isinstance(tags, list):
        raise LookupFailed("unavailable", "contact record carries no tags list")
    return [t.strip().lower() for t in tags if isinstance(t, str)]


def order_record(transport: Any, order_id: str) -> Dict[str, Any]:
    """One order, normalized: contact id, paid flag source, minor-unit amount."""
    body = read(transport, "/payments/orders/" + urllib.parse.quote(order_id, safe=""),
                {"altId": str(getattr(transport, "location_id", "")), "altType": "location"})
    order = body.get("data", body)
    if not isinstance(order, dict):
        raise LookupFailed("unavailable", "order record is not an object")
    try:
        minor = int((Decimal(str(order["amount"])) * 100).to_integral_value())
    except (KeyError, InvalidOperation, ValueError):
        raise LookupFailed("unavailable", "order record carries no readable amount") from None
    return {
        "order_id": str(order.get("_id") or order.get("id") or order_id),
        "contact_id": str(order.get("contactId") or ""),
        "status": str(order.get("status") or order.get("paymentStatus") or "").lower(),
        "amount_minor": minor,
        "currency": str(order.get("currency") or "").upper(),
    }


def self_check() -> None:
    t = StaticReadTransport({
        "/contacts/c1": {"contact": {"tags": ["Brand-Management-Member", 3]}},
        "/payments/orders/o1": {"_id": "o1", "contactId": "c1", "status": "completed",
                                "amount": 497, "currency": "usd"},
    })
    assert contact_tags(t, "c1") == ["brand-management-member"]
    assert order_record(t, "o1") == {"order_id": "o1", "contact_id": "c1",
                                     "status": "completed", "amount_minor": 49700,
                                     "currency": "USD"}
    try:
        contact_tags(t, "nope")
    except LookupFailed as exc:
        assert exc.kind == "unresolved"
    else:
        raise AssertionError("a missing contact must not resolve")
    assert {m for m, _, _ in t.requests} == {"GET"}
    try:
        t.request("POST", "/contacts/c1", {})
    except ValueError:
        pass
    else:
        raise AssertionError("a write verb must be refused")


if __name__ == "__main__":
    self_check()
    print("contact_membership self-check: PASS")
