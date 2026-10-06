#!/usr/bin/env python3
"""
test_consent_check_cli.py -- proves the coded consent gate (diu_validator.py
`consent-check`) reads the SOP-DIU-608 CONSENT.md record, not IDENTITY.md, and fails
closed (exit 4, AF-DIU-CONSENT) on every missing / negative / ambiguous field, THROUGH THE
REAL CLI (subprocess).

Cases:
  1. A fully valid CONSENT.md (active, dated, unexpired, adult attested, storage protected)
     -> exit 0.
  2. Missing CONSENT.md -> exit 4 and the message says IDENTITY.md is not read.
  3. One broken field at a time (status, created, expiry in the past, adult_attested,
     minors override, storage_protection, no front-matter) -> exit 4 each, naming the field.
  4. The old IDENTITY.md shape (`Consent: granted` ...) is NOT accepted -> exit 4.
  5. The old `--identity-file` spelling still reaches the same gate (pointing at CONSENT.md).

Run:  python3 test_consent_check_cli.py
Exit: 0 = every assertion passed; 1 = a case failed (prints which one).
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
VALIDATOR = HERE / "diu_validator.py"
FAILURES: list[str] = []

GOOD = """---
client_slug: "sample-client"
subject_name: "Sample Client"
created: "2026-01-15"
updated: "2026-01-15"
status: "active"          # active
modes_approved: [A, B, C]
use_class: "both"
channels: ["social_media"]
term_months: null
expiry_date: null
standing_release: true
minors: "hard_block"
adult_attested: true
storage_protection: "encrypted-at-rest"
retouch_boundaries: []
revision_log: []
revocation_log: []
---
# CONSENT log
"""

OLD_IDENTITY = """# IDENTITY - Sample Client
- Slug: sample-client
- Consent: granted
- Consent date: 2026-01-15
- Minor: no
- Storage protection: encrypted-at-rest
"""


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  PASS: {label}")
    else:
        print(f"  FAIL: {label}" + (f" -- {detail}" if detail else ""))
        FAILURES.append(label)


def run(text: str | None, flag: str = "--consent-file") -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "CONSENT.md"
        if text is not None:
            p.write_text(text, encoding="utf-8")
        return subprocess.run([sys.executable, str(VALIDATOR), "consent-check", flag, str(p)],
                              capture_output=True, text=True, timeout=30)


def main() -> int:
    print("=== 1. valid CONSENT.md -> exit 0 ===")
    r = run(GOOD)
    check("exit 0", r.returncode == 0, f"{r.returncode} {r.stderr!r}")
    check("stdout confirms OK", r.stdout.strip().startswith("OK:"), r.stdout)

    print("\n=== 2. missing CONSENT.md -> exit 4 ===")
    r = run(None)
    check("exit 4", r.returncode == 4, f"{r.returncode}")
    check("stderr says IDENTITY.md is not read", "IDENTITY.md is not read" in r.stderr, r.stderr)

    print("\n=== 3. one broken field at a time -> exit 4, field named ===")
    past = "2020-01-01"
    future = f"{int(time.strftime('%Y')) + 5}-01-01"
    cases = [
        ("status pending", GOOD.replace('status: "active"          # active', 'status: "pending"'), "status"),
        ("status revoked", GOOD.replace('status: "active"          # active', 'status: "revoked"'), "status"),
        ("no created date", GOOD.replace('created: "2026-01-15"\n', ""), "consent date"),
        ("expiry in the past", GOOD.replace("expiry_date: null", f'expiry_date: "{past}"'), "expired"),
        ("adult not attested", GOOD.replace("adult_attested: true", "adult_attested: false"), "adult"),
        ("adult field absent", GOOD.replace("adult_attested: true\n", ""), "adult"),
        ("minors overridden", GOOD.replace('minors: "hard_block"', 'minors: "allowed"'), "minors"),
        ("storage unprotected", GOOD.replace('storage_protection: "encrypted-at-rest"', 'storage_protection: "plaintext"'), "storage"),
        ("no front-matter", "# CONSENT\nstatus: active\n", "status"),
    ]
    for label, text, needle in cases:
        r = run(text)
        check(f"{label}: exit 4", r.returncode == 4, f"{r.returncode} {r.stderr!r}")
        check(f"{label}: names {needle!r}", needle in r.stderr.lower(), r.stderr)
    r = run(GOOD.replace("expiry_date: null", f'expiry_date: "{future}"'))
    check("expiry in the future still passes", r.returncode == 0, r.stderr)

    print("\n=== 4. the old IDENTITY.md shape is not accepted ===")
    r = run(OLD_IDENTITY)
    check("IDENTITY-style lines -> exit 4", r.returncode == 4, f"{r.returncode}")

    print("\n=== 5. the old --identity-file spelling still reaches the gate ===")
    r = run(GOOD, flag="--identity-file")
    check("valid CONSENT.md via --identity-file -> exit 0", r.returncode == 0, r.stderr)
    r = run(None, flag="--identity-file")
    check("missing file via --identity-file -> exit 4", r.returncode == 4, r.stderr)

    print()
    if FAILURES:
        print(f"test_consent_check_cli: {len(FAILURES)} FAILURE(S): {FAILURES}")
        return 1
    print("test_consent_check_cli: ALL CASES PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
