#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""aa_gate_integrity_check.py — anti-lie LIVE-gate guard (Skill 52).

Pins the sha256 of the manifests + provers into AA-GATE-HASHES.json. The
foreman (aa_director.py) and the delivery gate (aa_delivery_gate.py) both call
`check()` in-process before dispatch / before issuing a certificate and
REFUSE to proceed against modified gates — so nobody can weaken a prover to
fake a pass.

  --write   (re)record the pinned hashes (operator, at build time)
  --check   verify current files match the pins (default; fail-closed)

`--self-test` used to be `write()` then `check()` against the SAME real repo
files — a tautology that "PASS"es even when a pinned prover was JUST weakened
seconds earlier, because it re-pins whatever is currently on disk before
checking it (it "blesses" tampering rather than catching it). The self-test
below is side-effect-free: it never touches the real AA-GATE-HASHES.json, and
it proves `check()` on a TEMP MIRROR (a) matches the real, already-committed
pins right now, and (b) genuinely DETECTS drift when one pinned file's bytes
are mutated in the mirror.

Exit 0 = match, 2 = drift / missing pin, 3 = usage/IO error.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
HASHES = ROOT / "AA-GATE-HASHES.json"
PINNED = [
    "AA-PIPELINE-MANIFEST.json",
    "AVATAR-MANIFEST.json",
    "scripts/aa_intake_gate.py",
    "scripts/aa_build_check.py",
    "scripts/aa_delivery_gate.py",
    "scripts/aa_qc_cert.py",
    "scripts/aa_egress_gate.py",
    "scripts/aa_links_gate.py",
    "scripts/aa_director.py",
    "entry.sh",
]


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write(root: Path = ROOT, hashes_path: Path = HASHES, pinned: Optional[List[str]] = None) -> int:
    pinned = pinned if pinned is not None else PINNED
    pins = {rel: _sha256(root / rel) for rel in pinned}
    hashes_path.write_text(json.dumps({"pinned": pins}, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(pins)} pinned hashes -> {hashes_path.name}")
    return 0


def check(root: Path = ROOT, hashes_path: Path = HASHES, pinned: Optional[List[str]] = None) -> int:
    pinned = pinned if pinned is not None else PINNED
    if not hashes_path.is_file():
        print(f"FAIL: no pin file {hashes_path.name} — run --write first (fail-closed).")
        return 2
    pins = json.loads(hashes_path.read_text(encoding="utf-8")).get("pinned", {})
    drift = []
    for rel in pinned:
        f = root / rel
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
    print(f"PASS: all {len(pinned)} gates match their pinned hashes.")
    return 0


# ---------------------------------------------------------------------------
# self-test: side-effect-free (never writes the real AA-GATE-HASHES.json).
# ---------------------------------------------------------------------------
def run_self_test() -> int:
    import shutil
    import tempfile
    ok = True

    # (1) the REAL, already-committed pin file must match the REAL files right
    #     now (this is a genuine check against the checked-in artifact, not a
    #     re-derivation of it).
    rc = check()
    if rc == 0:
        print("SELF-TEST ok: the committed AA-GATE-HASHES.json matches the real pinned files right now.")
    else:
        ok = False
        print("SELF-TEST FAIL: the committed AA-GATE-HASHES.json does NOT match the real pinned files "
              "(run `python3 aa_gate_integrity_check.py --write` and re-commit if this is expected).")

    with tempfile.TemporaryDirectory() as td:
        mirror = Path(td)
        for rel in PINNED:
            src = ROOT / rel
            dst = mirror / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
        mirror_hashes = mirror / "AA-GATE-HASHES.json"

        # (2) write() on the MIRROR, then check() on the MIRROR -> clean pass
        #     (proves the round-trip is mechanically correct) — this never
        #     touches the real HASHES file.
        write(root=mirror, hashes_path=mirror_hashes)
        rc = check(root=mirror, hashes_path=mirror_hashes)
        if rc == 0:
            print("SELF-TEST ok: write()+check() round-trip is correct on an isolated mirror.")
        else:
            ok = False
            print("SELF-TEST FAIL: write()+check() round-trip failed on a freshly-written mirror.")

        # (3) THE REAL TEST: mutate one pinned file's bytes in the mirror
        #     AFTER the pins were written, then check() again — this must
        #     DETECT the drift, not silently re-bless it (the bug this
        #     replaces: --self-test used to call write() first every time,
        #     which would have re-pinned the tampered bytes and reported a
        #     false PASS).
        victim = mirror / "scripts" / "aa_build_check.py"
        original = victim.read_bytes()
        victim.write_bytes(original + b"\n# TAMPERED BY SELF-TEST\n")
        rc = check(root=mirror, hashes_path=mirror_hashes)
        if rc == 2:
            print("SELF-TEST ok: mutating a pinned file AFTER pins were written is DETECTED "
                  "(drift, fail-closed) — not silently re-blessed.")
        else:
            ok = False
            print(f"SELF-TEST FAIL: tampering a pinned file was NOT detected (rc={rc}).")

        # (4) a MISSING pinned file is also detected (delete, don't re-pin).
        (mirror / "scripts" / "aa_qc_cert.py").unlink()
        rc = check(root=mirror, hashes_path=mirror_hashes)
        if rc == 2:
            print("SELF-TEST ok: deleting a pinned file is DETECTED (MISSING, fail-closed).")
        else:
            ok = False
            print(f"SELF-TEST FAIL: a missing pinned file was NOT detected (rc={rc}).")

        # (5) a missing pin file itself fails closed (never silently permissive).
        mirror_hashes.unlink()
        rc = check(root=mirror, hashes_path=mirror_hashes)
        if rc == 2:
            print("SELF-TEST ok: an absent AA-GATE-HASHES.json fails closed (no pins = no trust).")
        else:
            ok = False
            print(f"SELF-TEST FAIL: an absent pin file did not fail closed (rc={rc}).")

    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv) -> int:
    ap = argparse.ArgumentParser(description="Avatar-Alchemist gate-integrity guard (hash pinning).")
    ap.add_argument("--write", action="store_true", help="record pinned hashes (operator, at build time)")
    ap.add_argument("--check", action="store_true", help="verify hashes (default)")
    ap.add_argument("--self-test", action="store_true",
                     help="side-effect-free: checks the real pins, then proves check() detects "
                          "drift/removal on an isolated mirror (never re-blesses tampering)")
    args = ap.parse_args(argv)
    try:
        if args.self_test:
            return run_self_test()
        if args.write:
            return write()
        return check()
    except Exception as exc:  # noqa: BLE001
        print(f"USAGE/IO ERROR: {exc}")
        return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
