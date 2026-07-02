#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""aa_gate_integrity_check.py — anti-lie LIVE-gate guard (Skill 52).

Pins the sha256 of the manifests + provers into AA-GATE-HASHES.json. The foreman
(aa_director.py) calls this in --check mode before every run and REFUSES to run
against modified gates — so nobody can weaken a prover to fake a pass.

  --write   (re)record the pinned hashes (operator, at build time)
  --check   verify current files match the pins (default; fail-closed)

Exit 0 = match, 2 = drift / missing pin, 3 = usage/IO error.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HASHES = ROOT / "AA-GATE-HASHES.json"
PINNED = [
    "AA-PIPELINE-MANIFEST.json",
    "AVATAR-MANIFEST.json",
    "scripts/aa_intake_gate.py",
    "scripts/aa_build_check.py",
    "scripts/aa_delivery_gate.py",
]


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write() -> int:
    pins = {rel: _sha256(ROOT / rel) for rel in PINNED}
    HASHES.write_text(json.dumps({"pinned": pins}, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(pins)} pinned hashes -> {HASHES.name}")
    return 0


def check() -> int:
    if not HASHES.is_file():
        print(f"FAIL: no pin file {HASHES.name} — run --write first (fail-closed).")
        return 2
    pins = json.loads(HASHES.read_text(encoding="utf-8")).get("pinned", {})
    drift = []
    for rel in PINNED:
        f = ROOT / rel
        if not f.is_file():
            drift.append((rel, "MISSING")); continue
        actual = _sha256(f)
        if pins.get(rel) != actual:
            drift.append((rel, f"changed ({str(pins.get(rel))[:10]}.. -> {actual[:10]}..)"))
    if drift:
        print(f"FAIL: {len(drift)} gate integrity drift — the foreman refuses to run.")
        for rel, why in drift:
            print(f"  DRIFT {rel}: {why}")
        return 2
    print(f"PASS: all {len(PINNED)} gates match their pinned hashes.")
    return 0


def main(argv) -> int:
    ap = argparse.ArgumentParser(description="Avatar-Alchemist gate-integrity guard (hash pinning).")
    ap.add_argument("--write", action="store_true", help="record pinned hashes")
    ap.add_argument("--check", action="store_true", help="verify hashes (default)")
    ap.add_argument("--self-test", action="store_true", help="write then check (round-trip)")
    args = ap.parse_args(argv)
    try:
        if args.self_test:
            write()
            return check()
        if args.write:
            return write()
        return check()
    except Exception as exc:  # noqa: BLE001
        print(f"USAGE/IO ERROR: {exc}")
        return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
