#!/usr/bin/env python3
"""WF23 prep: OpenClaw gateway readiness probe TEMPLATE (NOT acceptance).

Proves the SELECTED adapter is a listening, authenticated service — not a
live PID. Stdlib only, hermetic: the W6 acceptance leg points this at the
real gateway; the prep self-test points it at a local fixture HTTP server
(positive) and a closed port (negative control).

Checks, in order:
  1. TCP connect to host:port succeeds (listening, not just alive).
  2. HTTP GET <base><path> returns 200.
  3. When --token is given, the request carries
     `Authorization: Bearer <token>` and a 401/403 counts as NOT-READY
     (auth failure), not as READY.

Exit codes: 0 READY; 2 NOT-READY (refused/timeout/bad status/auth);
1 usage/internal error. Prints one JSON line to stdout either way.
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import urllib.request
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit


def probe(base_url: str, path: str = "/wf23-prep-probe",
          token: str | None = None, timeout: float = 5.0) -> dict:
    parts = urlsplit(base_url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return {"status": "NOT-READY", "reason": f"bad base_url {base_url!r}"}
    host, port = parts.hostname, parts.port or (443 if parts.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
    except OSError as exc:
        return {"status": "NOT-READY", "reason": f"tcp-connect failed: {exc}"}
    url = base_url.rstrip("/") + path
    req = urllib.request.Request(url, method="GET")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.getcode()
            if code == 200:
                return {"status": "READY", "reason": f"GET {path} -> 200, listening service"}
            return {"status": "NOT-READY", "reason": f"GET {path} -> {code}"}
    except HTTPError as exc:
        if exc.code in (401, 403):
            return {"status": "NOT-READY",
                    "reason": f"GET {path} -> {exc.code} (auth refused)"}
        return {"status": "NOT-READY", "reason": f"GET {path} -> HTTP {exc.code}"}
    except (URLError, OSError, TimeoutError) as exc:
        return {"status": "NOT-READY", "reason": f"http failed: {exc}"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", required=True, help="Gateway base URL, e.g. http://127.0.0.1:PORT")
    ap.add_argument("--path", default="/wf23-prep-probe")
    ap.add_argument("--token", default=None)
    ap.add_argument("--timeout", type=float, default=5.0)
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 1)
    result = probe(args.url, path=args.path, token=args.token, timeout=args.timeout)
    print(json.dumps(result))
    return 0 if result["status"] == "READY" else 2


if __name__ == "__main__":
    sys.exit(main())
