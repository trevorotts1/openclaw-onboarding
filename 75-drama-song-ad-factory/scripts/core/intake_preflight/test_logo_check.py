#!/usr/bin/env python3
"""F-EOC-2 proof: the logo rule refuses what it must and passes what it must.

Plain asserts, no framework: `python3 -B scripts/core/intake_preflight/test_logo_check.py`
prints one line per proof and exits 0 only when every proof holds.
"""
import os
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import logo_check as L  # noqa: E402


def _png(width, height, color_type, with_trns=False):
    """Header-only PNG: enough for header-only validation, not a renderable file."""
    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    body = L.PNG_SIG + struct.pack(">I4s", 13, b"IHDR") + ihdr + b"\x00\x00\x00\x00"
    if with_trns:
        body += struct.pack(">I4s", 2, b"tRNS") + b"\x00\x00" + b"\x00\x00\x00\x00"
    body += struct.pack(">I4s", 0, b"IEND") + b"\x00\x00\x00\x00"
    return body


def main():
    checks = 0
    with tempfile.TemporaryDirectory() as td:
        def write(name, data):
            p = os.path.join(td, name)
            with open(p, "wb") as fh:
                fh.write(data)
            return p

        # 1. the known bad case: a 350 px opaque PNG is refused
        tiny = write("350-opaque.png", _png(350, 350, 2))
        got = L.validate_logo(tiny)
        assert not got["ok"] and got["code"] == "LOGO_UNUSABLE", got
        assert any("opaque" in r for r in got["reasons"]), got
        assert any("too small" in r for r in got["reasons"]), got
        print("ok 1 - 350 px opaque PNG refused as LOGO_UNUSABLE")
        checks += 1

        # 2. a good logo passes: transparent, big enough
        good = write("good.png", _png(1024, 1024, 6))
        assert L.validate_logo(good)["ok"], L.validate_logo(good)
        print("ok 2 - 1024x1024 RGBA PNG accepted")
        checks += 1

        # 3. palette PNG with a tRNS chunk counts as transparent
        pal = write("pal.png", _png(600, 600, 3, with_trns=True))
        assert L.validate_logo(pal)["ok"], L.validate_logo(pal)
        print("ok 3 - palette PNG with tRNS accepted")
        checks += 1

        # 4. missing file refuses, never raises
        assert L.validate_logo(os.path.join(td, "nope.png"))["code"] == "LOGO_UNUSABLE"
        print("ok 4 - missing logo refused")
        checks += 1
    print("%d proofs held" % checks)


def test_logo_check():
    """Collected by pytest so the proofs run under the per-file gate (U-GEN438)."""
    main()


if __name__ == "__main__":
    main()
