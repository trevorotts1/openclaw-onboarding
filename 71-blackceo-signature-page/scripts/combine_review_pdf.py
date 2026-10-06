#!/usr/bin/env python3
import argparse
import hashlib
import json
import sys
from pathlib import Path

ALLOWED = {
    "desktop-wireframes",
    "mobile-wireframes",
    "desktop-mockups",
    "mobile-mockups",
}


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def check_name(category, path):
    name = path.name.lower()
    errors = []
    if category.startswith("desktop") and "mobile" in name:
        errors.append(f"Desktop review set includes a file named as mobile: {path.name}")
    if category.startswith("mobile") and "desktop" in name:
        errors.append(f"Mobile review set includes a file named as desktop: {path.name}")
    if category.endswith("wireframes") and "mockup" in name:
        errors.append(f"Wireframe review set includes a file named as mockup: {path.name}")
    if category.endswith("mockups") and "wireframe" in name:
        errors.append(f"Mockup review set includes a file named as wireframe: {path.name}")
    return errors


def main():
    parser = argparse.ArgumentParser(description="Combine an explicit ordered BlackCEO wireframe/mockup image set into a review PDF.")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--resolution", type=float, default=144.0)
    args = parser.parse_args()

    try:
        from PIL import Image
    except ImportError:
        print("FAIL: Pillow is required. Install the Python package 'Pillow' in this runtime.")
        return 2

    try:
        data = json.loads(args.manifest.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"FAIL: could not read manifest: {exc}")
        return 2

    category = data.get("category")
    pages = data.get("pages")
    output_name = data.get("output")
    errors = []
    if category not in ALLOWED:
        errors.append(f"category must be one of: {', '.join(sorted(ALLOWED))}")
    if not isinstance(pages, list) or not pages:
        errors.append("pages must be a non-empty ordered array.")
    if not isinstance(output_name, str) or not output_name.lower().endswith(".pdf"):
        errors.append("output must be a PDF filename/path.")
    if errors:
        print("FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    base = args.manifest.parent
    resolved = []
    for i, item in enumerate(pages, start=1):
        if not isinstance(item, dict) or not item.get("path"):
            errors.append(f"pages[{i}] must contain path.")
            continue
        path = (base / item["path"]).resolve()
        if not path.exists():
            errors.append(f"Missing page {i}: {path}")
            continue
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            errors.append(f"Unsupported page image type: {path}")
        errors.extend(check_name(category, path))
        resolved.append((path, item.get("label", f"Page {i}")))

    if len({str(p) for p, _ in resolved}) != len(resolved):
        errors.append("The ordered page list contains duplicate image paths.")

    if errors:
        print("FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    output = (base / output_name).resolve() if not Path(output_name).is_absolute() else Path(output_name).resolve()
    if output.exists() and not args.overwrite:
        print(f"FAIL: output already exists: {output}. Use --overwrite to replace it.")
        return 1
    output.parent.mkdir(parents=True, exist_ok=True)

    pil_pages = []
    try:
        for path, _ in resolved:
            im = Image.open(path)
            if im.mode in {"RGBA", "LA"}:
                bg = Image.new("RGB", im.size, "white")
                alpha = im.getchannel("A") if im.mode == "RGBA" else im.getchannel("A")
                bg.paste(im.convert("RGB"), mask=alpha)
                im = bg
            else:
                im = im.convert("RGB")
            pil_pages.append(im.copy())
            im.close()
        first, rest = pil_pages[0], pil_pages[1:]
        first.save(output, "PDF", save_all=True, append_images=rest, resolution=args.resolution)
    finally:
        for im in pil_pages:
            try:
                im.close()
            except Exception:
                pass

    receipt = {
        "category": category,
        "pdf": str(output),
        "page_count": len(resolved),
        "pages": [
            {"order": i, "label": label, "path": str(path), "sha256": sha256(path)}
            for i, (path, label) in enumerate(resolved, start=1)
        ],
        "pdf_sha256": sha256(output),
    }
    receipt_path = output.with_suffix(output.suffix + ".manifest.json")
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    print(f"PASS: created {output} with {len(resolved)} pages.")
    print(f"Receipt: {receipt_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
