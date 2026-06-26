#!/usr/bin/env python3
"""
ad_selection.py — PICK-10 capture (the first human pause).

Captures the owner's `PICK: n,n,...` reply, checks it is exactly the locked count of
real, in-range, NON-duplicate choices, echoes the ten chosen overlay lines back to
confirm, and writes `working/s1-selection.json` ONCE. A second reply REPLACES the first
(never adds). The offline checkers `_chk_selection_count` / `_chk_selection_subset`
validate the written file; PICK-10 is a NON-skippable human gate.

CLI:
    python3 ad_selection.py --run-dir DIR --reply "PICK: 3,7,12,18,22,31,40,55,61,68"
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ad_build_check as abc  # for the locked counts


def parse_reply(reply: str) -> list:
    """Pull the integers out of a 'PICK: 3,7,12,...' reply (tolerant of spacing and a
    missing 'PICK:' prefix). De-duplicates while preserving order."""
    body = re.sub(r"(?i)^\s*pick\s*:?", "", reply).strip()
    nums = [int(n) for n in re.findall(r"\d+", body)]
    seen, out = set(), []
    for n in nums:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def overlay_count(run_dir: Path) -> int:
    r = abc._s1_receipt(run_dir)
    if isinstance(r, dict) and isinstance(r.get("overlay_count"), int):
        return r["overlay_count"]
    return abc.OVERLAY_COUNT_LOCKED


def overlay_lines(run_dir: Path) -> list:
    """Best-effort: read the numbered overlay lines from s1-overlays.md for the echo."""
    p = run_dir / "working" / "s1-overlays.md"
    lines = {}
    if p.exists():
        for ln in p.read_text().splitlines():
            m = re.match(r"\s*(\d+)[.)]\s*(.+)", ln)
            if m:
                lines[int(m.group(1))] = m.group(2).strip()
    return lines


def capture(run_dir: Path, reply: str):
    """Returns (ok, message, picks). Writes s1-selection.json only when ok."""
    picks = parse_reply(reply)
    n = overlay_count(run_dir)
    want = abc.SELECTION_COUNT_LOCKED
    out_of_range = [p for p in picks if p < 1 or p > n]
    if out_of_range:
        return False, (f"Out of range: {out_of_range}. Pick numbers 1..{n}. "
                       "Reply again with exactly "
                       f"{want} numbers."), picks
    if len(picks) != want:
        return False, (f"You picked {len(picks)} distinct number(s); I need exactly "
                       f"{want}. Reply again, e.g. PICK: 3,7,12,18,22,31,40,55,61,68."), picks
    # Write ONCE — a second reply replaces (atomic).
    p = run_dir / "working" / "s1-selection.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"selection": picks, "overlay_count": n}, indent=2))
    os.replace(tmp, p)
    lines = overlay_lines(run_dir)
    echo = "\n".join(f"  {i}. {lines.get(i, '(overlay ' + str(i) + ')')}" for i in picks)
    return True, ("Saved your top 10. Confirm these are the ten:\n" + echo), picks


def main():
    ap = argparse.ArgumentParser(description="PICK-10 capture (first human pause).")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--reply", required=True, help="the owner's 'PICK: n,n,...' reply")
    args = ap.parse_args()
    ok, msg, picks = capture(Path(args.run_dir).resolve(), args.reply)
    print(msg)
    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
