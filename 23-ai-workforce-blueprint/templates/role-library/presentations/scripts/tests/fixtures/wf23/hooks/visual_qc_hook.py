#!/usr/bin/env python3
"""WF23 prep: visual-QC hook stub TEMPLATE (NOT acceptance).

W6 acceptance requires independent VISUAL review of rendered slides, not
metadata alone. This stub checks the hermetic half: every *.png under
--artifacts-dir must carry PNG magic plus a minimum payload (placeholder
floor, mirroring checkpoint.PLACEHOLDER_MIN_BYTES doctrine at a small
fixture scale). PASS only when >=1 PNG checked and all pass; zero PNGs or
any bad file is PENDING — never a pass.

Usage: visual_qc_hook.py --artifacts-dir DIR --out RECEIPT.json
Exit: 0 on PASS, 2 on PENDING, 1 on usage error.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
MIN_BYTES = 64


def check_artifacts(artifacts_dir: Path) -> tuple[bool, str]:
    try:
        pngs = sorted(p for p in artifacts_dir.iterdir()
                      if p.is_file() and p.suffix.lower() == ".png")
    except OSError as exc:
        return False, f"artifacts dir unreadable: {exc}"
    if not pngs:
        return False, "no PNG artifacts to review (UNDETERMINED, never a pass)"
    bad = []
    for png in pngs:
        try:
            data = png.read_bytes()
        except OSError as exc:
            bad.append(f"{png.name}: unreadable ({exc})")
            continue
        if len(data) < MIN_BYTES or not data.startswith(PNG_MAGIC):
            bad.append(f"{png.name}: missing PNG magic or under {MIN_BYTES}B")
    if bad:
        return False, f"{len(bad)}/{len(pngs)} artifacts failed visual floor: {bad[0]}"
    return True, f"{len(pngs)} PNG artifacts carry magic + payload"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--artifacts-dir", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 1)
    ok, why = check_artifacts(args.artifacts_dir)
    receipt = {"hook": "visual-qc", "status": "PASS" if ok else "PENDING",
               "detail": why,
               "emitted_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat()}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps(receipt))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
