#!/usr/bin/env python3
"""WF23 prep: render hook stub TEMPLATE (NOT acceptance).

Validates the fixture deck shape (slides.schema.json floor: every slide
carries slide/scene/nonempty copy; ordinals unique and contiguous from 1)
and emits a receipt. PASS only on a valid deck; anything else is PENDING —
and PENDING is never a pass at the W6 gate.

Usage: render_hook.py --deck DECK.json --out RECEIPT.json
Exit: 0 on PASS, 2 on PENDING, 1 on usage error.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REQUIRED_KEYS = {"slide", "scene", "copy"}


def check_deck(deck) -> tuple[bool, str]:
    if not isinstance(deck, list) or not deck:
        return False, "deck must be a nonempty array"
    seen = []
    for entry in deck:
        if not isinstance(entry, dict):
            return False, f"slide entry not an object: {entry!r}"
        if not REQUIRED_KEYS <= set(entry):
            return False, f"slide missing keys: {entry!r}"
        if not isinstance(entry["slide"], int):
            return False, f"ordinal not int: {entry!r}"
        if not entry["scene"]:
            return False, f"empty scene on slide {entry['slide']}"
        if not entry["copy"]:
            return False, f"empty copy on slide {entry['slide']}"
        seen.append(entry["slide"])
    if sorted(seen) != list(range(1, len(deck) + 1)):
        return False, f"ordinals not contiguous 1..{len(deck)}"
    return True, f"{len(deck)} slides, ordinals 1..{len(deck)} contiguous"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--deck", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 1)
    try:
        deck = json.loads(args.deck.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        ok, why = False, f"deck unreadable: {exc}"
    else:
        ok, why = check_deck(deck)
    receipt = {"hook": "render", "status": "PASS" if ok else "PENDING",
               "detail": why,
               "emitted_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat()}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps(receipt))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
