#!/usr/bin/env python3
"""Skill 71 reference-image use: the prompt contract and the bleed QC check.

A reference image (the Design Board example, the wireframe and mockup
standards) teaches STRUCTURE. It is never a source of style or identity.
This module owns both halves of that rule so no stage re-words it:

  reference_block(references, roles)   the labelled prompt section every
                                       stage that attaches reference images
                                       must carry (stage_executor wires it)
  check(output, references, ...)       the QC check: did the output reproduce
                                       the reference's palette or brand text

Contract text and the field list: references/reference-image-use.md.
Known references and their fingerprints: references/reference-library.json.

CLI (exit 0 PASS, 1 FAIL, 3 UNDETERMINED - never a silent pass):
  python3 scripts/reference_use.py check OUTPUT.png --reference URL_OR_NAME
      [--reference ...] [--client-palette '#112233,#aabbcc'] [--text-file F]
      [--no-ocr]
  python3 scripts/reference_use.py block [--reference URL ...] [--role design-board ...]
"""
from __future__ import annotations

import argparse
import colorsys
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
LIBRARY = SKILL_ROOT / "references" / "reference-library.json"

# Tunables, measured on the bundled standards (see the reference doc).
# ponytail: share thresholds are heuristics; low-coverage bleed (under about
# 5% of pixels) is left to the reviewer's side-by-side leg, upgrade path is a
# perceptual (Lab) distance plus a region-level test.
TOL = 36            # RGB distance counted as "the same color"
MAX_ONE = 0.08      # one reference color covering this share of the output
MAX_SUM = 0.10      # all reference colors together
SET_MIN = 0.01      # a color "is present" at this share ...
SET_COUNT = 4       # ... and this many present = the palette is recombined
ROLE = re.compile(r"[a-z0-9-]{1,32}")
HEX = re.compile(r"#?([0-9a-fA-F]{6})\b")

TAKE = ("layout grid and block arrangement; section order and rhythm; "
        "information hierarchy; density and whitespace balance; composition "
        "and framing; how blocks are annotated or grouped; overall level of polish")
NEVER = ("its color palette or gradients; font styling; logo; brand names, "
         "taglines or any copy; people, photography subjects or icons; any "
         "client identity")


def _urls(references):
    return [str(r) for r in dict.fromkeys(str(r) for r in (references or []) if r)]


def reference_block(references, roles=None) -> str:
    """The labelled 'REFERENCE IMAGE - structure only' section, or '' when no
    reference image is attached. The caller's attach order must put the
    request-level references FIRST (stage_executor.build_input does)."""
    refs = _urls(references)
    if not refs:
        return ""
    n = len(refs)
    kinds = [r for r in (roles or []) if ROLE.fullmatch(str(r))][:n]
    label = f" ({', '.join(kinds)})" if kinds else ""
    what = ("The first attached image is a REFERENCE IMAGE" if n == 1
            else f"The first {n} attached images are REFERENCE IMAGES") + label
    return (
        "REFERENCE IMAGE - structure only. "
        f"{what}: an example of the KIND of artifact wanted, never of this client. "
        f"TAKE from it: {TAKE}. "
        f"NEVER take from it: {NEVER}. "
        "Colors come only from this client's resolved brand palette, the logo "
        "only from this client, imagery only from this client's selected images, "
        "and every word only from this client's copy. Where the reference and "
        "the client differ, the client wins. If any part of your output could be "
        "mistaken for the reference's brand, redo it. Any other attached images "
        "are this page's own earlier-stage slices: follow those as the layout source.")


def load_library() -> dict:
    return json.loads(LIBRARY.read_text(encoding="utf-8"))


def lookup(ref: str, library: dict | None = None):
    """The library entry for a reference given as its URL, name or sha256."""
    for entry in (library or load_library()).get("references") or []:
        if str(ref) in (entry.get("url"), entry.get("name"), entry.get("sha256")):
            return entry
    return None


def library_urls(*kinds: str) -> list:
    """Media-library links for the named kinds (design-board, wireframe,
    mockup), library order; every kind when none is named. Request builders
    use this so a reference is always the operator's own public link."""
    return [e["url"] for e in load_library().get("references") or []
            if not kinds or e.get("kind") in kinds]


def _rgb(hexcode: str):
    h = HEX.search(hexcode).group(1)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _chromatic(rgb) -> bool:
    _h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    return s >= 0.2 and 0.2 <= v <= 0.95   # ivory and near-black cannot be "bled"


def palette_bleed(output: Path, signature, client_palette=()) -> dict:
    """Share of the output's pixels that sit on a reference signature color
    the client does not own."""
    from PIL import Image
    client = [_rgb(c) for c in client_palette]
    sig = []
    for code in signature:
        rgb = _rgb(code)
        if _chromatic(rgb) and not any(sum((a - b) ** 2 for a, b in zip(rgb, c)) <= TOL ** 2
                                       for c in client):
            sig.append((code.upper() if code.startswith("#") else "#" + code.upper(), rgb))
    if not sig:
        return {"status": "PASS", "note": "reference has no chromatic color the client lacks",
                "shares": {}}
    img = Image.open(output).convert("RGB")
    img.thumbnail((256, 2048))
    pixels = list(img.getdata())
    hits = {code: 0 for code, _ in sig}
    lim = TOL ** 2
    for p in pixels:
        for code, rgb in sig:
            if (p[0] - rgb[0]) ** 2 + (p[1] - rgb[1]) ** 2 + (p[2] - rgb[2]) ** 2 <= lim:
                hits[code] += 1
    shares = {c: round(n / len(pixels), 4) for c, n in hits.items()}
    total, top = sum(shares.values()), max(shares.values())
    present = sum(1 for s in shares.values() if s >= SET_MIN)
    why = []
    if top >= MAX_ONE:
        why.append(f"one reference color covers {top:.1%} (limit {MAX_ONE:.0%})")
    if total >= MAX_SUM:
        why.append(f"reference colors cover {total:.1%} together (limit {MAX_SUM:.0%})")
    if len(sig) >= SET_COUNT and present >= SET_COUNT:
        why.append(f"{present} reference colors each at {SET_MIN:.0%} or more: the palette is recombined")
    return {"status": "FAIL" if why else "PASS", "shares": shares, "reasons": why}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def text_bleed(text: str, forbidden) -> list:
    """Reference brand strings found in the text (normalized, word-bounded)."""
    hay = f" {_norm(text)} "
    return sorted({t for t in forbidden if t and f" {_norm(t)} " in hay})


def ocr_text(path: Path):
    """Text read from the image, or None when OCR cannot run (never '')."""
    exe = shutil.which("tesseract")
    if not exe:
        return None
    proc = subprocess.run([exe, str(path), "stdout"], capture_output=True, text=True)
    return proc.stdout if proc.returncode == 0 else None


def check(output, references, client_palette=(), text=None, ocr=True) -> dict:
    """The QC check. status: PASS, FAIL, or UNDETERMINED (a reference with no
    fingerprint, or a text leg that could not run, is never reported as PASS)."""
    output = Path(output)
    library = load_library()
    palette, brand, unknown = [], [], []
    for ref in _urls(references):
        entry = lookup(ref, library)
        if not entry:
            unknown.append(ref)
            continue
        palette += entry.get("signature_palette") or []
        brand += entry.get("brand_text") or []
    result = {"output": output.name, "references": len(_urls(references)),
              "palette": None, "text": None, "problems": []}
    if unknown:
        result["problems"].append("UNDETERMINED: no fingerprint for " + ", ".join(unknown)
                                  + " (add it to references/reference-library.json)")
    if output.is_file():
        try:
            result["palette"] = palette_bleed(output, list(dict.fromkeys(palette)), client_palette)
        except Exception as exc:  # unreadable image, Pillow missing: say so, never crash, never PASS
            result["palette"] = {"status": "UNDETERMINED", "reason": f"{type(exc).__name__}: {exc}"}
            result["problems"].append(
                f"UNDETERMINED: {output.name} could not be read as an image ({type(exc).__name__}); "
                "palette leg not run")
        if ocr and text is None:
            text = ocr_text(output)
            if text is None:
                result["problems"].append(
                    "UNDETERMINED: OCR unavailable (tesseract missing or failed); "
                    "brand-text leg not run on the image")
    else:
        result["problems"].append(f"UNDETERMINED: output {output} is not a file")
    if text is not None:
        found = text_bleed(text, brand)
        result["text"] = {"status": "FAIL" if found else "PASS", "found": found}
    elif not any("OCR unavailable" in x for x in result["problems"]):
        result["problems"].append(
            "UNDETERMINED: brand-text leg not run (no OCR and no text supplied)")
    fails = [k for k in ("palette", "text") if (result[k] or {}).get("status") == "FAIL"]
    result["status"] = ("FAIL" if fails else
                        "UNDETERMINED" if result["problems"] else "PASS")
    return result


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("output", type=Path)
    c.add_argument("--reference", action="append", default=[])
    c.add_argument("--client-palette", default="")
    c.add_argument("--text-file", type=Path)
    c.add_argument("--no-ocr", action="store_true")
    b = sub.add_parser("block")
    b.add_argument("--reference", action="append", default=[])
    b.add_argument("--role", action="append", default=[])
    a = p.parse_args(argv)
    if a.cmd == "block":
        print(reference_block(a.reference, a.role))
        return 0
    text = a.text_file.read_text(encoding="utf-8") if a.text_file else None
    palette = [x for x in a.client_palette.split(",") if x.strip()]
    result = check(a.output, a.reference, palette, text, ocr=not a.no_ocr)
    print(json.dumps(result, indent=2, sort_keys=True))
    return {"PASS": 0, "FAIL": 1}.get(result["status"], 3)


if __name__ == "__main__":
    sys.exit(main())
