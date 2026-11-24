#!/usr/bin/env python3
"""G-FACE-02 proofs: a lip-source still under 720x1280 is refused at intake.

Plain asserts, no framework:
`python3 -B scripts/core/intake_preflight/test_still_provenance_s75.py`
exits 0 only when every proof holds.
"""
import os
import struct
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import still_provenance as S   # noqa: E402


def _png(path, width, height):
    raw = bytearray()
    row = bytes((10, 20, 30)) * width
    for _ in range(height):
        raw.append(0)
        raw.extend(row)
    def chunk(typ, body):
        return (struct.pack(">I", len(body)) + typ + body
                + struct.pack(">I", zlib.crc32(typ + body) & 0xFFFFFFFF))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")
        fh.write(chunk(b"IHDR", ihdr))
        fh.write(chunk(b"IDAT", zlib.compress(bytes(raw), 9)))
        fh.write(chunk(b"IEND", b""))


def _check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ((" :: " + detail) if not ok and detail else ""))
    return ok


def main():
    fails = []
    with tempfile.TemporaryDirectory() as tmp:
        def p(name):
            return os.path.join(tmp, name)

        _png(p("small-still.png"), 212, 377)
        r = S.validate_source_still(p("small-still.png"))
        fails.append(_check("a 212x377 lip-source still is refused",
                            not r["ok"] and r["problems"][0]["code"] == "SOURCE_STILL_TOO_SMALL",
                            repr(r)))

        _png(p("big-still.png"), 720, 1280)
        r = S.validate_source_still(p("big-still.png"))
        fails.append(_check("a 720x1280 lip-source still passes", r["ok"], repr(r["problems"])))

        r = S.validate_source_still(p("small-still.png"), is_lip_source=False)
        fails.append(_check("a small story still is not refused by the lip-source rule", r["ok"]))

        r = S.validate_stills([{"path": p("small-still.png"), "purpose": "lip_source"}])
        fails.append(_check("a small lip-source still refuses the brief at intake",
                            not r["ok"] and r["problems"][0]["code"] == "SOURCE_STILL_TOO_SMALL",
                            repr(r)))

    print("\n%d checks failed" % sum(1 for f in fails if not f))
    return 0 if all(fails) else 1


def test_still_provenance_s75():
    """Collected by pytest so the proofs run under the per-file gate (U-GEN438)."""
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
