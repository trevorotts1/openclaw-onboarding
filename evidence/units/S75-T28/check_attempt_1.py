#!/usr/bin/env python3
"""Self-check for the S75-T28 contract artefact `attempt-1.json` (RC-D1, RC-D2).

Checks, in order, and exits 1 on the first failure:
  1. the artefact exists at the exact path the acceptance row names and parses;
  2. its bytes and sha256 equal the identity the verdict of record certified;
  3. if the project package copy is mounted, the certified bytes are reproducible
     from it byte-exactly by removing the two post-verdict appended keys;
  4. instrument control: a one-byte change to the artefact must fail check 2.

Exit 0 = PASS, 1 = FAIL.
"""
import hashlib
import json
import sys
from pathlib import Path

CERT_BYTES = 33178
CERT_SHA256 = "296a2e227be782dbd8ce044fe19aaf670d8faf5f19a1e0686a52f64177dc69da"
HERE = Path(__file__).resolve().parent
ARTEFACT = HERE / "attempt-1.json"
PACKAGE = Path("/Volumes/mac mini m4/Downloads/git trees and automations/"
               "S75_Story_First_Full_Cast_Build_20261024/evidence/units/S75-T28/attempt-1.json")

failures = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (" — " + detail if detail else ""))
    if not ok:
        failures.append(name)


def identity(raw):
    return len(raw), hashlib.sha256(raw).hexdigest()


def main():
    check("artefact exists at the row's contract path", ARTEFACT.is_file(), str(ARTEFACT))
    if not ARTEFACT.is_file():
        return 1
    raw = ARTEFACT.read_bytes()
    try:
        json.loads(raw)
        parsed = True
    except ValueError:
        parsed = False
    check("artefact parses as JSON", parsed)

    n, sha = identity(raw)
    check("bytes equal the certified %d" % CERT_BYTES, n == CERT_BYTES, "measured %d" % n)
    check("sha256 equals the certified hash", sha == CERT_SHA256, "measured " + sha)

    if PACKAGE.is_file():
        pn, psha = identity(PACKAGE.read_bytes())
        drift = PACKAGE.read_bytes()
        i = drift.find(b'"head_sha"')
        recon = drift[:i - 4] + b"\n}\n" if i > 0 else b""
        check("certified bytes reproducible from the package copy",
              identity(recon) == (CERT_BYTES, CERT_SHA256),
              "package copy is %d B sha %s" % (pn, psha[:16]))
    else:
        print("SKIP package copy not mounted — certification checked against the row's hash only")

    # control: the comparator must reject a one-byte change to the same bytes
    mutated = raw[:-2] + (b" \n" if raw[-2:-1] != b" " else b"\n}\n")
    check("control: a mutated copy fails the hash test",
          identity(mutated)[1] != CERT_SHA256, "mutated %d B" % len(mutated))

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
