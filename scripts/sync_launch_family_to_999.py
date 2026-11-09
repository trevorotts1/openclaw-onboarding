#!/usr/bin/env python3
"""Sync engine for the launch family, onboarding to 999 (CON-06).

Direction is onboarding to 999, always. Which files cross is decided by the
allowlist declared in check-launch-family-parity.py (FAMILIES, NINE_ONLY,
DIVERGENT), the same module the parity gate judges by, so the sync and the
gate cannot disagree. The sync:

  - copies neutral files byte for byte (created or overwritten);
  - seeds per-repo adapter and divergent files only when 999 has none, and
    never overwrites one (their drift is reported by the parity check);
  - never writes, deletes or compares a declared 999-only file, and never
    deletes anything at all;
  - refuses (writing nothing) when an excluded file is present in 999, when a
    999 tree resolves into the onboarding tree, or an onboarding tree is
    missing; removing is a human act;
  - runs Skill 71 through its own sync (sync_skill71_to_999.py) and carries the
    two parity gate scripts into 999 so its own workflow can run them;
  - runs the parity check over the synced families at the end.

Exit codes: 0 synced and parity holds (dry run: 0), 1 refused or parity
failures remain, 2 usage or config error.
"""
import argparse
import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "check_launch_family_parity", HERE / "check-launch-family-parity.py")
_parity = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_parity)
FAMILY_CHOICES = _parity.FAMILY_CHOICES


def copy_file(src: Path, dst: Path, dry: bool, log: list, verb: str):
    log.append(f"{verb} {src} -> {dst}")
    if not dry:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        shutil.copymode(src, dst)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Sync the launch family from onboarding to 999 (CON-06).")
    ap.add_argument("--onboarding", "--onb-root", dest="onb", type=Path, required=True)
    ap.add_argument("--nine", "--nine-root", dest="nine", type=Path, required=True)
    ap.add_argument("--family", action="append", choices=FAMILY_CHOICES,
                    help="family to sync (repeatable); default all")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    onb, nine, dry = args.onb, args.nine, args.dry_run
    families = args.family or list(FAMILY_CHOICES)
    if not onb.is_dir() or not nine.is_dir():
        print(f"REFUSED: root missing (onboarding: {onb}, 999: {nine})")
        return 2

    plans = {n: _parity.family_plan(onb, nine, n) for n in families}
    for name, rows in plans.items():
        for status, dest, detail in rows:
            if status in _parity.REFUSE_STATUSES:
                print(f"REFUSED: {status}: {dest} ({detail}); fix it by hand "
                      f"(it must never be synced over), then re-run the sync")
                return 1

    log = []
    for rows in plans.values():
        for status, dest, detail in rows:
            if status in _parity.COPY_STATUSES:
                copy_file(onb / detail, nine / dest, dry, log, "copy")
            elif status in _parity.SEED_STATUSES:
                copy_file(onb / detail, nine / dest, dry, log, "seed")
    for line in log:
        print(("DRY " if dry else "") + line)
    print(f"{'would write' if dry else 'wrote'}: {len(log)} file(s)")

    if "signature-page" in families:
        cmd = [sys.executable, str(HERE / "sync_skill71_to_999.py"),
               "--onb-root", str(onb), "--nine-root", str(nine)] + (["--dry-run"] if dry else [])
        proc = subprocess.run(cmd, text=True, capture_output=True)
        for line in proc.stdout.splitlines():  # prefixed so its own PASS line is never read as the verdict
            print(f"[skill71] {line}")
        if proc.returncode != 0:
            print(proc.stderr, file=sys.stderr, end="")
            print(f"REFUSED OR FAILED: skill 71 sync exit {proc.returncode}")
            return 1
    if dry:
        return 0

    report = _parity.check(onb, nine, families)
    for f in report["failures"]:
        print(f"FAIL {f}")
        m = re.search(r"divergent_token_missing: (\S+) \((.*)\)$", f)
        if m:
            print(f"HAND-MERGE NEEDED: {m.group(1)} lacks '{m.group(2)}'; "
                  f"the sync never overwrites a declared divergence")
    if report["failures"]:
        print(f"SYNC DONE, PARITY FAILURES REMAIN: {len(report['failures'])} "
              f"(declared divergences are reported, not synced)")
        return 1
    print("SYNC DONE, PARITY PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
