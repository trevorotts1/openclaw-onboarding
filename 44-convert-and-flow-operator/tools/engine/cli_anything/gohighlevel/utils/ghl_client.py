"""GoHighLevel REST API client with bearer token authentication.

Version selection is per operation, not per path family. The prefix map below is
legacy; ``_OPERATION_VERSION_OVERRIDES`` is consulted first and is **the only
place a per-operation version may be declared**.
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Any
from urllib.parse import urlencode

import requests

from cli_anything.gohighlevel.utils.safety_gate import check_write, SafetyRefused

BASE_URL = "https://services.leadconnectorhq.com"

# Path-based API version routing — different GHL endpoints require different versions
VERSION_MAP = {
    "/conversations/": "2021-04-15",
    "/calendars/": "2021-04-15",
    "/contacts/": "2021-07-28",
    "/opportunities/": "2021-07-28",
    "/workflows/": "2021-07-28",
    "/campaigns/": "2021-07-28",
    "/invoices/": "2021-07-28",
    "/payments/": "2021-07-28",
    "/products/": "2021-07-28",
    "/emails/": "2021-07-28",
    "/forms/": "2021-07-28",
    "/locations/": "2021-07-28",
    "/social-media-posting/": "2021-07-28",
    "/proposals/": "2021-07-28",
}
DEFAULT_VERSION = "2021-07-28"

# Per-operation Version overrides: (METHOD, compiled path regex) -> exact literal.
#
# THE ONLY PLACE A PER-OPERATION VERSION MAY BE DECLARED. An entry here wins over
# the legacy prefix map because a GHL version is a property of an operation, not
# of a path family. Add a row only when the operation page can be cited (doc URL
# + fetch date); every other operation keeps exactly the header it had.
#
# Family: opportunities + pipelines, all documented ``v3`` at
# https://marketplace.gohighlevel.com/docs/ghl/opportunities/* (fetched
# 2026-10-18; GHL modernization contract ledger decision record). The prefix map sent these
# 2021-07-28. ``GET /opportunities/search`` is deliberately absent: its query
# casing is version-coupled and unverified, so it keeps 2021-07-28 until a live
# probe settles it. ``GET /opportunities`` (bare list) is undocumented — no row.
_OPERATION_VERSION_OVERRIDES: tuple[tuple[str, "re.Pattern[str]", str], ...] = tuple(
    (method, re.compile(pattern), "v3")
    for method, pattern in (
        # get-pipelines / create-pipeline
        ("GET", r"^/opportunities/pipelines$"),
        ("POST", r"^/opportunities/pipelines$"),
        # get-pipeline / update-pipeline / delete-pipeline
        ("GET", r"^/opportunities/pipelines/[^/]+$"),
        ("PUT", r"^/opportunities/pipelines/[^/]+$"),
        ("DELETE", r"^/opportunities/pipelines/[^/]+$"),
        # upsert-opportunity
        ("POST", r"^/opportunities/upsert$"),
        # create-opportunity
        ("POST", r"^/opportunities/?$"),
        # update-opportunity-status
        ("PUT", r"^/opportunities/[^/]+/status$"),
        # get / update / delete opportunity by id — never a reserved sub-path
        ("GET", r"^/opportunities/(?!search$|pipelines$|upsert$)[^/]+$"),
        ("PUT", r"^/opportunities/(?!search$|pipelines$|upsert$)[^/]+$"),
        ("DELETE", r"^/opportunities/(?!search$|pipelines$|upsert$)[^/]+$"),
    )
)


def _version_for_path(path: str) -> str:
    """Resolve API version based on request path prefix."""
    for prefix, version in VERSION_MAP.items():
        if path.startswith(prefix):
            return version
    return DEFAULT_VERSION


def _resolve_version(method: str, path: str) -> str:
    """Resolve the ``Version`` header for one request.

    The per-operation override table is consulted before the legacy prefix map.
    An operation absent from the table keeps the header it had — there is no
    global default and no sweep.
    """
    verb = (method or "").upper()
    for op_method, pattern, version in _OPERATION_VERSION_OVERRIDES:
        if op_method == verb and pattern.match(path):
            return version
    return _version_for_path(path)


# Canonical LOCATION-PIT alias set — all mean the same credential (prefix pit-).
# First non-empty value wins. AGENCY PITs are intentionally excluded (they 401 on media).
# GHL PIT aliases: see TERMINOLOGY.md for the full canonical alias set.
_LOCATION_PIT_ENV_NAMES = (
    "GOHIGHLEVEL_API_KEY",             # preferred — matches openclaw.json + wire-ghl-env.sh
    "GHL_API_KEY",                     # legacy short alias
    "GHL_PIT",                         # canonical short alias
    "GHL_TOKEN",                       # alternate alias
    "GHL_PRIVATE_INTEGRATION_TOKEN",   # explicit full-name alias
    "PRIVATE_INTEGRATION_TOKEN",       # bare PIT alias
    "GHL_PRIVATE_TOKEN",               # shortened private-token alias
    "PIT_TOKEN",                       # short PIT alias
    "GHL_PIT_TOKEN",                   # combined PIT alias
    "GOHIGHLEVEL_LOCATION_PIT",        # explicit LOCATION-PIT name
    "GHL_LOCATION_PIT",                # explicit LOCATION-PIT short alias
)


def _is_placeholder(value: str) -> bool:
    """True when ``value`` is a documentation placeholder, not a real credential.

    Mirrors ``38-conversational-ai-system/scripts/check-ghl-pit-liveness.sh``'s
    ``_is_placeholder()`` — a naive first-non-empty-wins resolver over these same
    alias names produced a false "PIT is DEAD/EXPIRED" alarm on 2026-08-03 because
    the 10-char doc placeholder ``pit-abc123`` is non-empty and outranked the real
    credential. Same three shapes: shorter than 20 characters, a known dummy
    literal (``pit-abc...``, ``changeme...``, ``xxx...``, ``your-...``/``your_...``,
    a ``*_here``/``*-here`` suffix), or an angle-bracket placeholder (``<...>``).
    """
    if not value:
        return True
    if len(value) < 20:
        return True
    low = value.lower()
    if low.startswith("pit-abc") or low.startswith("changeme") or low.startswith("xxx") \
       or low.startswith("your-") or low.startswith("your_") \
       or low.endswith("_here") or low.endswith("-here") \
       or (value.startswith("<") and value.endswith(">")):
        return True
    return False


def _get_token() -> str:
    """Scan the full canonical LOCATION-PIT alias set and return the first non-empty,
    non-placeholder hit.

    The engine previously read ONLY GHL_API_KEY, which caused a 401 crash-loop when the
    client's token was stored under GOHIGHLEVEL_API_KEY or another canonical alias.
    This resolver closes that gap (root cause: a client-box GHL-MCP crash-loop, 2026-06).
    A placeholder-shaped value (see ``_is_placeholder``) is SKIPPED rather than accepted
    — the process env is seeded from openclaw.json ``env.vars`` at gateway launch, and
    those config copies are placeholders by design (see TERMINOLOGY.md); accepting the
    first non-empty value regardless of shape produced a false "PIT expired" alarm on
    2026-08-03.
    """
    saw_placeholder = False
    for name in _LOCATION_PIT_ENV_NAMES:
        token = os.environ.get(name, "").strip()
        if not token:
            continue
        if _is_placeholder(token):
            saw_placeholder = True
            continue
        return token
    placeholder_note = (
        "\nNote: at least one candidate was a documentation PLACEHOLDER (short / "
        "dummy-shaped) and was SKIPPED rather than used — put the real value in "
        "~/.openclaw/secrets/.env, not just openclaw.json."
        if saw_placeholder else ""
    )
    print(
        "Error: GHL location PIT not found in any canonical env-var name.\n"
        "Set one of these in ~/.openclaw/secrets/.env (or as an env var):\n"
        "  " + ", ".join(_LOCATION_PIT_ENV_NAMES) + "\n"
        "Example: GOHIGHLEVEL_API_KEY=pit-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" + placeholder_note,
        file=sys.stderr,
    )
    sys.exit(1)


def _get_location_id() -> str:
    """Get location ID from GHL_LOCATION_ID env var.

    Raises SystemExit if unset — no silent fallback to a foreign sub-account.
    """
    loc = os.environ.get("GHL_LOCATION_ID", "").strip()
    if not loc:
        print(
            "Error: GHL_LOCATION_ID environment variable is not set.\n"
            "Set it with: export GOHIGHLEVEL_LOCATION_ID='your-location-id'\n"
            "(No default is provided — defaulting to someone else's sub-account "
            "is a co-mingling violation.)",
            file=sys.stderr,
        )
        sys.exit(1)
    return loc


def _headers(version: str | None = None, path: str = "", method: str = "") -> dict[str, str]:
    """Build request headers.

    An explicit ``version`` always wins (caller override). Otherwise the header is
    resolved per operation: override table first, then the legacy prefix map.
    """
    return {
        "Authorization": f"Bearer {_get_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Version": version or _resolve_version(method, path),
    }


def get(path: str, params: dict[str, Any] | None = None, version: str | None = None) -> dict:
    """Make a GET request to the GHL API."""
    url = f"{BASE_URL}{path}"
    resp = requests.get(url, headers=_headers(version, path, "GET"), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def post(path: str, data: dict[str, Any] | None = None, version: str | None = None) -> dict:
    """Make a POST request to the GHL API."""
    url = f"{BASE_URL}{path}"
    loc = (data or {}).get("locationId") or os.environ.get("GHL_LOCATION_ID", "").strip() or None
    try:
        check_write("POST", url, data, location_id=loc)
    except SafetyRefused as exc:
        print(f"SAFETY GATE: {exc}", file=sys.stderr)
        sys.exit(1)
    resp = requests.post(url, headers=_headers(version, path, "POST"), json=data or {}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def put(path: str, data: dict[str, Any] | None = None, version: str | None = None) -> dict:
    """Make a PUT request to the GHL API."""
    url = f"{BASE_URL}{path}"
    loc = (data or {}).get("locationId") or os.environ.get("GHL_LOCATION_ID", "").strip() or None
    try:
        check_write("PUT", url, data, location_id=loc)
    except SafetyRefused as exc:
        print(f"SAFETY GATE: {exc}", file=sys.stderr)
        sys.exit(1)
    resp = requests.put(url, headers=_headers(version, path, "PUT"), json=data or {}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def delete(path: str, version: str | None = None, body: dict[str, Any] | None = None) -> dict:
    """Make a DELETE request to the GHL API.

    ``body`` — optional JSON request body. Some GHL DELETE endpoints require the
    payload in the body (e.g. DELETE /contacts/{id}/tags expects {"tags": [...]});
    without it the call 400s or silently no-ops. Omitted (None) sends no body,
    preserving the original behaviour for every other DELETE caller.
    """
    url = f"{BASE_URL}{path}"
    loc = (body or {}).get("locationId") or os.environ.get("GHL_LOCATION_ID", "").strip() or None
    try:
        check_write("DELETE", url, body, location_id=loc)
    except SafetyRefused as exc:
        print(f"SAFETY GATE: {exc}", file=sys.stderr)
        sys.exit(1)
    resp = requests.delete(url, headers=_headers(version, path, "DELETE"), json=body, timeout=30)
    resp.raise_for_status()
    try:
        return resp.json()
    except (json.JSONDecodeError, requests.exceptions.JSONDecodeError):
        return {"status": "deleted", "statusCode": resp.status_code}


# ---------------------------------------------------------------------------
# Products and prices: ONE implementation, shared-utils/ghl/products_prices.py.
#
# The CLI no longer builds a CreatePriceDto body. Money crosses one conversion
# (ISO-4217 exponent aware; the documented ``amount`` is a decimal in MAJOR
# units), every create is read-first / reconciled / read back, and every create
# needs a verified ``automation_write`` approval record bound to the exact
# object (key = "<location>:<kind>:<parent>:<logical id>", see _product_key /
# _price_key). With no verifier wired the create is refused (fail closed).
# ---------------------------------------------------------------------------

_SHARED_MODULE = None


def _products_prices():
    """Load shared-utils/ghl/products_prices.py by path (the engine has its own
    ``ghl`` package, so a plain ``import ghl`` would collide)."""
    global _SHARED_MODULE
    if _SHARED_MODULE is not None:
        return _SHARED_MODULE
    import importlib.util
    from pathlib import Path

    here = Path(__file__).resolve()
    for base in (here.parents[6], here.parents[5], Path.home() / ".openclaw" / "skills"):
        candidate = base / "shared-utils" / "ghl" / "products_prices.py"
        if candidate.is_file():
            spec = importlib.util.spec_from_file_location("_skill44_products_prices", candidate)
            mod = importlib.util.module_from_spec(spec)
            sys.modules["_skill44_products_prices"] = mod  # dataclasses resolve __module__
            spec.loader.exec_module(mod)
            _SHARED_MODULE = mod
            return mod
    print("Error: shared-utils/ghl/products_prices.py not found; product/price writes refused.",
          file=sys.stderr)
    sys.exit(1)


class _ClientTransport:
    """products_prices.Transport over this client: same auth/Version headers, and
    every write passes the safety gate. Returns (status, body); never raises on HTTP."""

    def __init__(self, pp) -> None:
        self._pp = pp

    def request(self, method: str, path: str, body=None):
        url = f"{BASE_URL}{path}"
        bare = path.split("?", 1)[0]
        if method != "GET":
            loc = (body or {}).get("locationId") or os.environ.get("GHL_LOCATION_ID", "").strip() or None
            check_write(method, url, body, location_id=loc)  # SafetyRefused propagates
        try:
            resp = requests.request(method, url, headers=_headers(None, bare, method),
                                    json=body if body is not None else None, timeout=30)
        except requests.exceptions.RequestException:
            raise self._pp.TransportTimeout(f"{method} {bare}: no authoritative outcome")
        try:
            parsed = resp.json() if resp.content else {}
        except ValueError:
            parsed = {"raw": resp.text[:500]}
        return self._pp.Response(resp.status_code, parsed if isinstance(parsed, dict) else {})


def _adapter(transport, verifier):
    pp = _products_prices()
    t = transport if transport is not None else _ClientTransport(pp)
    return pp, pp.ProductsPricesAdapter(t, pp.InMemoryStore(), approval_verifier=verifier)


def _product_key(pp, location_id: str, name: str, product_type: str):
    return pp.LogicalKey(location_id, "product", f"cli:{product_type}:{name}")


def _price_key(pp, location_id: str, product_id: str, name: str, billing_type: str,
               currency: str, amount_minor: int):
    return pp.LogicalKey(location_id, "price", f"cli:{name}:{billing_type}:{currency}:{amount_minor}",
                         parent_logical_id=product_id)


def create_product(name: str, product_type: str = "SERVICE", description: str | None = None,
                   image_url: str | None = None, *, approval: dict | None = None,
                   approval_verifier=None, location_id: str | None = None, transport=None) -> dict:
    """Create (or adopt, read-first) a product and read it back. ``approval`` is the
    per-action automation_write record; ``transport``/``approval_verifier`` are
    injectable for tests and for the approval authority."""
    pp, adapter = _adapter(transport, approval_verifier)
    loc = location_id or _get_location_id()
    spec = pp.ProductSpec(name, loc, product_type, description, image_url)
    rec, op = adapter.ensure_product(_product_key(pp, loc, name, product_type), spec, approval)
    return {"id": rec.native_product_id, "name": rec.name, "productType": rec.product_type,
            "locationId": rec.location_id, "readback": op.readback, "route": op.route}


def create_price(product_id: str, name: str, amount_minor: int, currency: str = "USD",
                 price_type: str = "one_time", *, recurring_interval: str | None = None,
                 recurring_interval_count: int = 1, trial_days: int | None = None,
                 approval: dict | None = None, approval_verifier=None,
                 location_id: str | None = None, transport=None) -> dict:
    """Create (or adopt, read-first) a price and read it back. ``amount_minor`` is in
    the currency's smallest unit (4900 = $49.00, JPY 5000 = 5000); the shared module
    converts to the documented major-unit ``amount``. ``price_type`` recurring with
    ``trial_days`` becomes trial_then_recurring."""
    pp, adapter = _adapter(transport, approval_verifier)
    loc = location_id or _get_location_id()
    billing = price_type
    if price_type == "recurring" and trial_days is not None:
        billing = "trial_then_recurring"
    spec = pp.PriceSpec(name, loc, billing, currency, amount_minor,
                        recurring_interval=recurring_interval, trial_days=trial_days,
                        recurring_interval_count=recurring_interval_count)
    product = pp.NativeProduct(product_id, loc, "", "")  # parent id only; price readback verifies it
    rec, op = adapter.ensure_price(_price_key(pp, loc, product_id, name, billing, currency, amount_minor),
                                   spec, product, approval)
    return {"id": rec.native_price_id, "product": rec.native_product_id, "name": rec.name,
            "currency": rec.currency, "amount_minor": rec.amount_minor, "type": price_type,
            "readback": op.readback, "route": op.route}


def format_output(data: Any, as_json: bool = False) -> str:
    """Format API response for display."""
    if as_json:
        return json.dumps(data, indent=2, default=str)
    if isinstance(data, dict):
        return _format_dict(data)
    if isinstance(data, list):
        return _format_list(data)
    return str(data)


def _format_dict(d: dict, indent: int = 0) -> str:
    """Format a dict for human-readable display."""
    lines = []
    prefix = "  " * indent
    for k, v in d.items():
        if isinstance(v, dict):
            lines.append(f"{prefix}{k}:")
            lines.append(_format_dict(v, indent + 1))
        elif isinstance(v, list):
            lines.append(f"{prefix}{k}: [{len(v)} items]")
            for i, item in enumerate(v[:5]):
                if isinstance(item, dict):
                    name = item.get("name") or item.get("title") or item.get("id", f"item {i}")
                    lines.append(f"{prefix}  - {name}")
                else:
                    lines.append(f"{prefix}  - {item}")
            if len(v) > 5:
                lines.append(f"{prefix}  ... and {len(v) - 5} more")
        else:
            lines.append(f"{prefix}{k}: {v}")
    return "\n".join(lines)


def _format_list(items: list, indent: int = 0) -> str:
    """Format a list for human-readable display."""
    lines = []
    prefix = "  " * indent
    for i, item in enumerate(items):
        if isinstance(item, dict):
            name = item.get("name") or item.get("title") or item.get("id", f"item {i}")
            lines.append(f"{prefix}{i + 1}. {name}")
            for k, v in item.items():
                if k not in ("name", "title") and not isinstance(v, (dict, list)):
                    lines.append(f"{prefix}   {k}: {v}")
        else:
            lines.append(f"{prefix}{i + 1}. {item}")
    return "\n".join(lines)
