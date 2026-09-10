"""PRES-043 — LIVE provider/GHL smoke, kept SEPARATE from mocked CI.

This module performs REAL network calls and is NEVER imported by the mocked
battery except for the refusal leg (which proves it refuses). Execution
requires ALL of:
  PRES043_LIVE_SMOKE=1            explicit opt-in, and
  GHL_SANDBOX_LOCATION_ID + GHL_SANDBOX_PIT   sandbox credentials, and
  a reachable sandbox base URL (GHL_SANDBOX_BASE_URL, default sandbox host).

Anything else raises LiveSmokeRefused with a NOT VERIFIED marker — the exact
string the evidence log greps for. On success it returns REAL remote IDs plus
a list-back readback; the caller records those IDs in the receipt.

SANDBOX BASE URL (the seam the previous version was missing). The canonical
``ghl_media.list_media`` hard-codes ``https://services.leadconnectorhq.com``.
An authorized sandbox run must never touch production, so this module builds
an OPENER that rewrites only the request URL's scheme+host+port to
``GHL_SANDBOX_BASE_URL`` (same path/query, same headers) and hands it to the
canonical call. With no sandbox base the module refuses (NOT VERIFIED) — it
never falls through to production. The gated-upload and create-folder public
surfaces are NOT harnessed here: this smoke lists and reads back; uploads
stay in the ``ghl_media_push`` governed paths.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlsplit, urlunsplit


class LiveSmokeRefused(RuntimeError):
    """Raised when live smoke is not authorized — evidence stays NOT VERIFIED."""


SANDBOX_ENV_VARS = ("GHL_SANDBOX_LOCATION_ID", "GHL_SANDBOX_PIT")
REAL_GHL_ORIGIN = "https://services.leadconnectorhq.com"


def _env(env: Optional[dict] = None) -> dict:
    import os as _os

    return dict(_os.environ) if env is None else dict(env)


def check_authorized(env: Optional[dict] = None) -> Dict[str, str]:
    """Return sandbox credentials or raise LiveSmokeRefused (NOT VERIFIED)."""
    e = _env(env)
    if e.get("PRES043_LIVE_SMOKE") != "1":
        raise LiveSmokeRefused(
            "NOT VERIFIED: live GHL smoke requires PRES043_LIVE_SMOKE=1 "
            "(sandbox execution not authorized in CI)")
    missing = [k for k in SANDBOX_ENV_VARS if not (e.get(k) or "").strip()]
    if missing:
        raise LiveSmokeRefused(
            "NOT VERIFIED: live GHL smoke missing sandbox credentials: "
            + ", ".join(missing))
    return {k: e[k].strip() for k in SANDBOX_ENV_VARS}


class _SandboxOpener:
    """Rewrites ONLY the origin of a GHL request to the sandbox base URL.

    Path, query, method, headers and body pass through untouched, so the
    canonical ``list_media`` (and its retry wrapper) exercise the real code
    path against the sandbox. The rewrite is byte-strict: any request whose
    origin is not the canonical GHL services origin is passed through
    unchanged (a defensive belt; this smoke only ever builds GHL requests).
    """

    def __init__(self, base_url: str, real_urlopen: Any):
        self._base = urlsplit(str(base_url).rstrip("/"))
        self._real = real_urlopen

    def __call__(self, req: Any, timeout: int) -> Any:
        parts = urlsplit(req.full_url)
        if (parts.scheme, parts.netloc) == urlsplit(REAL_GHL_ORIGIN)[:2]:
            netloc = self._base.netloc
            scheme = self._base.scheme or parts.scheme
            req.full_url = urlunsplit(
                (scheme, netloc, parts.path, parts.query, parts.fragment))
        return self._real(req, timeout=timeout)


def ghl_list_back(media_path: Any, env: Optional[dict] = None) -> Dict[str, Any]:
    """REAL list-back against the GHL sandbox. No mocks on this path."""
    creds = check_authorized(env)
    e = _env(env)
    base = (e.get("GHL_SANDBOX_BASE_URL") or "").strip()
    if not base:
        raise LiveSmokeRefused(
            "NOT VERIFIED: live GHL smoke missing GHL_SANDBOX_BASE_URL")
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import ghl_media  # noqa: PLC0415

    # Never the production origin: the sandbox rewrite is mandatory.
    opener = _SandboxOpener(base, urllib_urlopen())
    listed = ghl_media.list_media(creds["GHL_SANDBOX_LOCATION_ID"],
                                  creds["GHL_SANDBOX_PIT"], media_type="file",
                                  opener=opener)
    if listed.get("http") != 200:
        raise LiveSmokeRefused(
            f"NOT VERIFIED: sandbox list-back http={listed.get('http')}")
    return {"http": listed.get("http"), "count": listed.get("count"),
            "remote_ids": [d.get("_id") if isinstance(d, dict) else None
                           for d in listed.get("data", [])],
            "sandbox_base": base,
            "note": "LIVE sandbox IDs — mocked CI never produces these"}


def urllib_urlopen():
    """Import-boundary seam: live urllib urlopen (no mocks)."""
    import urllib.request

    return urllib.request.urlopen


if __name__ == "__main__":
    try:
        out = ghl_list_back({}, env=None)
    except LiveSmokeRefused as exc:
        print(str(exc))
        raise SystemExit(3)
    print(out)
