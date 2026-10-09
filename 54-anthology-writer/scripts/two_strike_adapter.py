#!/usr/bin/env python3
"""DEL-17 two-strike wiring adapter - skill 54 anthology-writer.

Calls the shared two-strike module
(75-drama-song-ad-factory/scripts/two_strike/, PKG-08-U1) before answering a
suspicious extraction attempt. Legitimate turns pass through untouched; this
adapter never writes outside its own skill folder and never touches another
skill's files. Stdlib only.

Exit codes: 0 = allow (legitimate use), 1 = blocked (refusal printed on stdout).
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from pathlib import Path

SKILL_DIR_NAME = '54-anthology-writer'
_SHARED_OWNER = "75-drama-song-ad-factory"


def _shared_scripts() -> Path | None:
    """Locate the shared module's parent dir by walking up this skill tree."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / _SHARED_OWNER / "scripts"
        if (candidate / "two_strike" / "two_strike.py").is_file():
            return candidate
    return None


def gate(message: str, *, suspicious: bool | None = None,
         skill_dir: str | None = None) -> dict:
    """Run the shared two-strike entry check on one turn."""
    scripts = _shared_scripts()
    if scripts is None:
        # ponytail: fail-open when the pilot module is not installed yet, so a
        # partial install never bricks legitimate use; upgrade path is a
        # fail-closed install-time precondition once PKG-08-U1 ships everywhere.
        print("two_strike shared module not found; gate inert", file=sys.stderr)
        return {"blocked": False, "action": "allow", "wired": True, "module": None}
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from two_strike import evaluate  # noqa: E402

    client = (os.environ.get("BLACKCEO_CLIENT")
              or os.environ.get("CLIENT_NAME")
              or "unspecified-client")
    box = (os.environ.get("BOX_SLUG")
           or socket.gethostname()
           or "unspecified-box")
    default_dir = str(Path(__file__).resolve().parent.parent)
    return evaluate(
        client,
        box,
        SKILL_DIR_NAME,
        message,
        skill_dir=skill_dir or default_dir,
        suspicious=suspicious,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--message", required=True,
                        help="the user message to gate")
    parser.add_argument("--json", action="store_true",
                        help="print the full gate result as JSON")
    parser.add_argument("--suspicious", choices=("auto", "yes", "no"),
                        default="auto",
                        help="force the extraction verdict instead of auto-detect")
    args = parser.parse_args(argv)
    forced = None if args.suspicious == "auto" else args.suspicious == "yes"
    result = gate(args.message, suspicious=forced)
    if args.json:
        print(json.dumps(result, sort_keys=True))
    elif result.get("blocked"):
        print(result.get("refusal") or "")
    return 1 if result.get("blocked") else 0


if __name__ == "__main__":
    sys.exit(main())
