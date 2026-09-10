#!/usr/bin/env python3
"""WF23 prep: standalone-no-gateway readiness probe TEMPLATE (NOT acceptance).

Standalone mode must work WITHOUT a gateway (HOST-ACCEPTANCE.md step 1:
"standalone does not require that gateway"). This probe asserts the offline
half hermetically and NEVER opens a socket:

  --package-dir DIR   the installed package root under test

READY (exit 0) only when the package marker exists:
  <package-dir>/presentation_job/__init__.py is a file.

Missing marker is NOT-READY (exit 2). Gateway env vars, if set, are
reported but never consulted — a standalone verdict must not flip because
a gateway happens to be reachable. The live half (hide both source repos
plus ~/.openclaw fixtures, install the exact artifact, invoke the skill)
runs in W6, not here.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def probe(package_dir: Path) -> dict:
    marker = package_dir / "presentation_job" / "__init__.py"
    gateway_hint = bool(os.environ.get("OPENCLAW_GATEWAY_URL")
                        or os.environ.get("GATEWAY_URL"))
    if not marker.is_file():
        return {"status": "NOT-READY",
                "reason": f"missing package marker {marker}",
                "gateway_env_present": gateway_hint}
    return {"status": "READY",
            "reason": f"package marker present; no gateway required",
            "gateway_env_present": gateway_hint}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--package-dir", required=True, type=Path)
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 1)
    result = probe(args.package_dir)
    print(json.dumps(result))
    return 0 if result["status"] == "READY" else 2


if __name__ == "__main__":
    sys.exit(main())
