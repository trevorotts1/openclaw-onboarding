#!/usr/bin/env python3
"""no_pitch_scan.py - the thank-you page's no-pitch scan and its copy-close receipt (AF-71-THANK-YOU-PITCH).

A thank-you page sells nothing (references/copy-specs/thank-you-v1.json, no_pitch). Skill 82 owns the
pre-screen (82-signature-thank-you/scripts/semantic_scan.py); this module runs it, and the one thing it
adds is the receipt that makes the rule enforceable:

  private/receipts/no-pitch-scan.json   {findings: 0, manuscript_sha256, ...}

run_page_role_stages.py writes it (through scan_and_receipt) before its first stage and refuses on any
FLAG line. stage_gate.py's `gate:no_pitch_receipt` row on the copy stage demands it for a thank_you run,
and requires the sha to still match copy/internal-manuscript.md, so the copy stage cannot close, and no
later stage can start, on a manuscript that was not scanned clean (or was edited after the scan). A
refusal deletes any earlier receipt. A scanner that is missing or errors is a refusal, never a pass.

Usage: no_pitch_scan.py <run_dir> [--manuscript FILE] [--scanner FILE]
Exit codes: 0 clean, receipt written; 1 refused (AF-71-THANK-YOU-PITCH); 2 usage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import page_role  # noqa: E402
import sibling_skill  # noqa: E402

CODE = "AF-71-THANK-YOU-PITCH"
ROLE = "thank_you"
RECEIPT_REL = "private/receipts/no-pitch-scan.json"
SKILL_ROOT = HERE.parent


def default_scanner():
    """Skill 82's semantic_scan.py, found beside this skill under either layout; None when absent."""
    return sibling_skill.skill_file("signature-thank-you", "scripts", "semantic_scan.py",
                                    skill_root=SKILL_ROOT)


def sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def scan(manuscript, scanner):
    """(flags, problem): FLAG lines from the scanner, or the reason it could not give a verdict."""
    if scanner is None or not Path(scanner).is_file():
        return [], f"the Skill 82 scanner is missing ({scanner}); nothing was scanned"
    if not Path(manuscript).is_file():
        return [], f"the manuscript is missing ({manuscript}); nothing was scanned"
    proc = subprocess.run([sys.executable, str(scanner), str(manuscript)],
                          capture_output=True, text=True, timeout=120)
    flags = [ln for ln in proc.stdout.splitlines() if ln.startswith("FLAG ")]
    if proc.returncode == 0 and not flags:
        return [], None
    if proc.returncode in (0, 1):
        return flags, None
    return [], f"the scanner exited {proc.returncode}: {(proc.stderr or proc.stdout).strip()[:300]}"


def scan_and_receipt(run_dir, manuscript, scanner=None):
    """Scan, then write the receipt on a clean verdict. Returns (ok, lines). A refusal removes any
    receipt an earlier clean scan left, so a stale pass can never outlive an edit."""
    run_dir, manuscript = Path(run_dir), Path(manuscript)
    scanner = Path(scanner) if scanner else default_scanner()
    receipt = run_dir / RECEIPT_REL
    flags, problem = scan(manuscript, scanner)
    if problem or flags:
        receipt.unlink(missing_ok=True)
        if problem:
            return False, [f"REFUSED {CODE}: {problem}"]
        return False, [f"REFUSED {CODE}: the thank-you manuscript pitches; a thank-you page sells nothing. "
                       f"{len(flags)} flag(s), nothing was drawn:"] + [f"  {ln}" for ln in flags]
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps({
        "schema": 1, "check": CODE, "scanner": Path(scanner).name, "findings": 0,
        "manuscript": manuscript.name, "manuscript_sha256": sha256(manuscript),
        "scanned_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}, indent=2) + "\n",
        encoding="utf-8")
    return True, [f"PASS {CODE}: no pitch flags; receipt written to {RECEIPT_REL}"]


def receipt_failure(run_dir):
    """The copy-close row: None when the run needs no receipt or holds a good one, else the failure."""
    run_dir = Path(run_dir)
    if page_role.declared_role(run_dir) != ROLE:
        return None
    path = run_dir / RECEIPT_REL
    where = f"gate:no_pitch_receipt: {CODE}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return (f"{where}: no readable {RECEIPT_REL}; run scripts/no_pitch_scan.py {run_dir} "
                "(a thank-you page sells nothing and its manuscript must be scanned clean before copy closes)")
    if not isinstance(data, dict) or data.get("findings") != 0:
        return f"{where}: {RECEIPT_REL} does not record a zero-finding scan"
    manuscript = run_dir / "copy" / "internal-manuscript.md"
    if not manuscript.is_file() or data.get("manuscript_sha256") != sha256(manuscript):
        return (f"{where}: copy/internal-manuscript.md changed since it was scanned (or is missing); "
                "scan it again")
    return None


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("run_dir", type=Path)
    p.add_argument("--manuscript", type=Path, default=None, help="default <run_dir>/copy/internal-manuscript.md")
    p.add_argument("--scanner", type=Path, default=None, help="default: Skill 82's semantic_scan.py")
    a = p.parse_args(argv)
    ok, lines = scan_and_receipt(a.run_dir, a.manuscript or a.run_dir / "copy" / "internal-manuscript.md",
                                 a.scanner)
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
