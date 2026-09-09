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
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional


class LiveSmokeRefused(RuntimeError):
    """Raised when live smoke is not authorized — evidence stays NOT VERIFIED."""


SANDBOX_ENV_VARS = ("GHL_SANDBOX_LOCATION_ID", "GHL_SANDBOX_PIT")


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


def ghl_list_back(media_path: Any, env: Optional[dict] = None) -> Dict[str, Any]:
    """REAL list-back against the GHL sandbox. No mocks on this path."""
    creds = check_authorized(env)
    e = _env(env)
    base = (e.get("GHL_SANDBOX_BASE_URL") or "").strip()
    if not base:
        raise LiveSmokeRefused(
            "NOT VERIFIED: live GHL smoke missing GHL_SANDBOX_BASE_URL")
    import sys  # noqa: PLC0415
    from pathlib import Path as _Path  # noqa: PLC0415

    sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
    import ghl_media  # noqa: PLC0415

    listed = ghl_media.list_media(creds["GHL_SANDBOX_LOCATION_ID"],
                                  creds["GHL_SANDBOX_PIT"], media_type="file")
    if listed.get("http") != 200:
        raise LiveSmokeRefused(
            f"NOT VERIFIED: sandbox list-back http={listed.get('http')}")
    return {"http": listed.get("http"), "count": listed.get("count"),
            "remote_ids": [d.get("_id") for d in listed.get("data", [])],
            "note": "LIVE sandbox IDs — mocked CI never produces these"}


if __name__ == "__main__":
    try:
        out = ghl_list_back({}, env=None)
    except LiveSmokeRefused as exc:
        print(str(exc))
        raise SystemExit(3)
    print(out)
