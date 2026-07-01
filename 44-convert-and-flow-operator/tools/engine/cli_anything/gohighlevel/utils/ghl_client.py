"""GoHighLevel REST API client with bearer token authentication."""
from __future__ import annotations

import json
import os
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


def _version_for_path(path: str) -> str:
    """Resolve API version based on request path prefix."""
    for prefix, version in VERSION_MAP.items():
        if path.startswith(prefix):
            return version
    return DEFAULT_VERSION


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


def _get_token() -> str:
    """Scan the full canonical LOCATION-PIT alias set and return the first non-empty hit.

    The engine previously read ONLY GHL_API_KEY, which caused a 401 crash-loop when the
    client's token was stored under GOHIGHLEVEL_API_KEY or another canonical alias.
    This resolver closes that gap (root cause: a client-box GHL-MCP crash-loop, 2026-06).
    """
    for name in _LOCATION_PIT_ENV_NAMES:
        token = os.environ.get(name, "").strip()
        if token:
            return token
    print(
        "Error: GHL location PIT not found in any canonical env-var name.\n"
        "Set one of these in ~/.openclaw/secrets/.env (or as an env var):\n"
        "  " + ", ".join(_LOCATION_PIT_ENV_NAMES) + "\n"
        "Example: GOHIGHLEVEL_API_KEY=pit-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
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


def _headers(version: str | None = None, path: str = "") -> dict[str, str]:
    """Build request headers with auth and auto-resolved version."""
    return {
        "Authorization": f"Bearer {_get_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Version": version or _version_for_path(path),
    }


def get(path: str, params: dict[str, Any] | None = None, version: str | None = None) -> dict:
    """Make a GET request to the GHL API."""
    url = f"{BASE_URL}{path}"
    resp = requests.get(url, headers=_headers(version, path), params=params, timeout=30)
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
    resp = requests.post(url, headers=_headers(version, path), json=data or {}, timeout=30)
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
    resp = requests.put(url, headers=_headers(version, path), json=data or {}, timeout=30)
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
    resp = requests.delete(url, headers=_headers(version, path), json=body, timeout=30)
    resp.raise_for_status()
    try:
        return resp.json()
    except (json.JSONDecodeError, requests.exceptions.JSONDecodeError):
        return {"status": "deleted", "statusCode": resp.status_code}


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
