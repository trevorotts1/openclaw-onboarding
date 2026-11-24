#!/usr/bin/env python3
"""F-EOC-2 proofs: a logo must be a transparent PNG of minimum size.

Builds real PNG bytes in a temp folder (no third-party library, no network,
no writes outside the temp dir) and asserts the refusals. Plain asserts, no
framework: `python3 -B scripts/core/intake_preflight/test_asset_inputs_s75.py`
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

import asset_inputs as A   # noqa: E402


def _png(path, width, height, color_type, pixel):
    """Write an 8-bit non-interlaced PNG whose every pixel is `pixel`."""
    channels = {2: 3, 6: 4}[color_type]
    raw = bytearray()
    row = bytes(pixel) * width
    for _ in range(height):
        raw.append(0)                  # filter: none
        raw.extend(row)
    def chunk(typ, body):
        return (struct.pack(">I", len(body)) + typ + body
                + struct.pack(">I", zlib.crc32(typ + body) & 0xFFFFFFFF))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
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

        # A clean transparent logo: RGBA, border alpha 0.
        _png(p("good-logo.png"), 600, 400, 6, (255, 0, 0, 0))
        r = A.validate_logo(p("good-logo.png"))
        fails.append(_check("a transparent 600x400 PNG logo passes", r["ok"], repr(r["problems"])))

        # The known bad file: 350 px, opaque RGB.
        _png(p("opaque-350.png"), 350, 350, 2, (240, 240, 240))
        r = A.validate_logo(p("opaque-350.png"))
        fails.append(_check("the known 350px opaque logo is refused LOGO_UNUSABLE",
                            not r["ok"] and r["problems"][0]["code"] == "LOGO_UNUSABLE",
                            repr(r)))

        # A PNG with an alpha channel but a full-white opaque border.
        _png(p("white-bg.png"), 600, 600, 6, (255, 255, 255, 255))
        r = A.validate_logo(p("white-bg.png"))
        fails.append(_check("a full-white-background PNG logo is refused",
                            not r["ok"] and any("full-white" in x["detail"]
                                                for x in r["problems"]), repr(r)))

        # The intake hook refuses a brief carrying an unusable logo.
        r = A.validate_intake_assets({"logo_path": p("opaque-350.png")})
        fails.append(_check("an unusable logo refuses the brief at intake",
                            not r["ok"] and r["problems"][0]["code"] == "LOGO_UNUSABLE",
                            repr(r)))

    print("\n%d checks failed" % sum(1 for f in fails if not f))
    return 0 if all(fails) else 1


def test_asset_inputs_s75():
    """Collected by pytest so the proofs run under the per-file gate (U-GEN438)."""
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
