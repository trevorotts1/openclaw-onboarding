#!/usr/bin/env python3
"""Export a run's final-mockups native slices to the page widths, keeping every native.

Usage:
  python3 scripts/export_native_slices.py <final-mockups dir> [--raw-dir raw-native]
         [--viewports desktop,mobile] [--desktop-width 1440] [--mobile-width 390]
         [--receipt export-receipt.json] [--dry-run]

The image route delivers each section at its native size (for example 2880x2880
or 3840x2160 for desktop, 2160x3840 for mobile). The page-width export is what
the stitcher, the review PDF combiner and the production record use: desktop
1440 pixels wide, mobile 390 pixels wide. Doing that resize by hand, or with an
ad hoc script, leaves no proof of which native a slice came from. This tool is
the one deterministic step:

  1. Every input is read first. An unreadable image, a zero-size file, a
     viewport with no `part-NN.png`, a gap in the numbering or a native narrower
     than its page width stops the run before any file is touched.
  2. Each native is copied to `<raw-dir>/<viewport>/part-NN.png` and re-read by
     sha256. A native that is already there is never overwritten: if it differs
     from the slice being exported, the run stops (use a fresh `--raw-dir`).
  3. The export is written back over `<viewport>/part-NN.png`: Lanczos resize to
     the page width, aspect preserved (height = round(native height * width /
     native width)), never upscaled, via a temporary file and an atomic replace.
  4. `export-receipt.json` records every input and output (path, bytes, pixels,
     sha256), the method and the scale factor, and carries `receipt_sha256`, the
     hash of its own body. `write_production_record.py` cites and re-verifies it.

Re-running is idempotent: a slice whose native is kept and whose export matches
the receipt is reported UNCHANGED and nothing is rewritten.

Exit codes: 0 pass (or unchanged), 1 refused (one named line per reason), 2 usage
or a missing dependency.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

TOOL = "export_native_slices.py"
RECEIPT_KIND = "native-slice-export"
METHOD = ("Lanczos (Pillow Image.LANCZOS) resize to the page width, aspect preserved, "
          "height = round(native height * page width / native width); never upscaled; "
          "the native is kept unchanged in the raw folder")
DEFAULT_WIDTHS = {"desktop": 1440, "mobile": 390}
PART_RE = re.compile(r"^part-(\d{2,3})\.png$")


class Refused(Exception):
    pass


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def body_hash(receipt):
    body = {k: v for k, v in receipt.items() if k != "receipt_sha256"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def read_dims(path):
    """(width, height) of a readable, non-empty image, or Refused naming why not."""
    from PIL import Image
    p = Path(path)
    if not p.is_file():
        raise Refused(f"{p}: file is missing")
    if p.stat().st_size == 0:
        raise Refused(f"{p}: zero-size file")
    try:
        with Image.open(p) as im:
            im.load()
            w, h = im.size
    except Exception as exc:
        raise Refused(f"{p}: not a readable image ({type(exc).__name__})") from exc
    if w < 1 or h < 1:
        raise Refused(f"{p}: image has no pixels")
    return w, h


def export_height(native_w, native_h, width):
    return max(1, round(native_h * width / native_w))


def render_export(native_path, width, out_path):
    """Write the Lanczos export of native_path to out_path (a temp file), return its size."""
    from PIL import Image
    with Image.open(native_path) as im:
        im.load()
        mode = "RGBA" if "A" in im.getbands() else "RGB"
        src = im.convert(mode)
    h = export_height(src.width, src.height, width)
    out = src.resize((width, h), Image.LANCZOS)
    out.save(out_path, "PNG")
    return out.size


def same_pixels(a, b):
    from PIL import Image, ImageChops
    with Image.open(a) as ia, Image.open(b) as ib:
        if ia.size != ib.size:
            return False
        ca, cb = ia.convert("RGBA"), ib.convert("RGBA")
        return ImageChops.difference(ca, cb).getbbox(alpha_only=False) is None


def list_parts(vp_dir, viewport):
    if not vp_dir.is_dir():
        raise Refused(f"{viewport}: folder is missing: {vp_dir}")
    names = sorted(p.name for p in vp_dir.iterdir() if PART_RE.match(p.name))
    if not names:
        raise Refused(f"{viewport}: no part-NN.png slices in {vp_dir}")
    nums = [int(PART_RE.match(n).group(1)) for n in names]
    if nums != list(range(1, len(nums) + 1)):
        raise Refused(f"{viewport}: slice numbering has a gap or does not start at 01: {names}")
    return names


def plan_viewport(root, viewport, width, raw_dir, prior):
    """Decide, without touching anything, what each slice of one viewport needs."""
    entries = []
    for name in list_parts(root / viewport, viewport):
        slice_path = root / viewport / name
        raw_path = root / raw_dir / viewport / name
        sw, sh = read_dims(slice_path)
        s_sha = sha256_file(slice_path)
        entry = {"viewport": viewport, "name": name, "slice_path": slice_path, "raw_path": raw_path,
                 "raw_rel": f"{raw_dir}/{viewport}/{name}", "out_rel": f"{viewport}/{name}", "width": width}
        raw_exists = raw_path.is_file()
        if raw_exists:
            rw, rh = read_dims(raw_path)
            r_sha = sha256_file(raw_path)
        if sw == width and not raw_exists:
            raise Refused(f"{viewport}/{name}: already {width} px wide and no native is kept at {entry['raw_rel']}; "
                          f"the native cannot be recovered, so nothing is exported (regenerate it, or restore the native)")
        if sw < width:
            raise Refused(f"{viewport}/{name}: native is {sw} px wide, narrower than the {width} px page width; "
                          f"the tool never upscales")
        if sw > width:  # the slice is a native not yet exported
            if raw_exists and r_sha != s_sha:
                raise Refused(f"{viewport}/{name}: a different native is already kept at {entry['raw_rel']} "
                              f"(sha256 {r_sha[:12]} against this slice {s_sha[:12]}); natives are never overwritten, "
                              f"export into a fresh --raw-dir")
            entry.update(action="export", native_sha=s_sha, native_size=(sw, sh), copy_native=not raw_exists)
        else:  # sw == width and the native is kept: is the slice this native's export?
            expect_h = export_height(rw, rh, width)
            prior_row = prior.get((viewport, name))
            if (prior_row and prior_row["output"]["sha256"] == s_sha and prior_row["native"]["sha256"] == r_sha):
                entry.update(action="unchanged", native_sha=r_sha, native_size=(rw, rh))
            elif sh == expect_h and _export_matches(raw_path, width, slice_path):
                entry.update(action="adopt", native_sha=r_sha, native_size=(rw, rh))
            else:
                raise Refused(f"{viewport}/{name}: the slice is {sw}x{sh} but is not the {width} px export of the kept "
                              f"native {entry['raw_rel']} ({rw}x{rh}); a stale or hand-made slice is never trusted. "
                              f"Restore the native over the slice or use a fresh --raw-dir")
        entries.append(entry)
    return entries


def _export_matches(raw_path, width, slice_path):
    import tempfile
    with tempfile.TemporaryDirectory(prefix="export-check-") as td:
        probe = Path(td) / "probe.png"
        render_export(raw_path, width, probe)
        return same_pixels(probe, slice_path)


def load_prior(receipt_path):
    if not receipt_path.is_file():
        return {}
    try:
        data = json.loads(receipt_path.read_text(encoding="utf-8"))
        if data.get("receipt_sha256") != body_hash(data):
            return {}
        return {(r["viewport"], Path(r["output"]["path"]).name): r for r in data["entries"]}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def execute(entry):
    """Apply one planned export. The native is copied and re-read before the slice is replaced."""
    slice_path, raw_path = entry["slice_path"], entry["raw_path"]
    if entry["action"] == "export":
        if entry["copy_native"]:
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = raw_path.with_name(raw_path.name + ".part")
            shutil.copy2(slice_path, tmp)
            if sha256_file(tmp) != entry["native_sha"]:
                tmp.unlink()
                raise Refused(f"{entry['out_rel']}: the native copy did not re-read to the same sha256")
            os.replace(tmp, raw_path)
        tmp_out = slice_path.with_name(slice_path.name + ".export")
        try:
            render_export(raw_path, entry["width"], tmp_out)
            os.replace(tmp_out, slice_path)
        finally:
            if tmp_out.exists():
                tmp_out.unlink()


def build_receipt(root, entries, raw_dir, widths):
    rows = []
    for e in entries:
        ow, oh = read_dims(e["slice_path"])
        nw, nh = e["native_size"]
        rows.append({
            "viewport": e["viewport"], "section_part": e["name"],
            "native": {"path": e["raw_rel"], "sha256": e["native_sha"], "width": nw, "height": nh,
                       "bytes": e["raw_path"].stat().st_size},
            "output": {"path": e["out_rel"], "sha256": sha256_file(e["slice_path"]), "width": ow, "height": oh,
                       "bytes": e["slice_path"].stat().st_size},
            "scale_factor": round(ow / nw, 4), "upscaled": False,
        })
    import PIL
    receipt = {
        "kind": RECEIPT_KIND, "tool": TOOL, "method": METHOD, "pillow_version": PIL.__version__,
        "raw_dir": raw_dir, "page_widths": widths,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "entries": rows,
    }
    receipt["receipt_sha256"] = body_hash(receipt)
    return receipt


def verify_receipt(receipt_path, root):
    """The receipt as a list of failure strings: body hash, then every file against its row."""
    root = Path(root)
    try:
        data = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"export receipt is unreadable: {type(exc).__name__}"]
    if not isinstance(data, dict) or data.get("kind") != RECEIPT_KIND:
        return ["export receipt is not a native-slice-export receipt"]
    if data.get("receipt_sha256") != body_hash(data):
        return ["export receipt was edited: receipt_sha256 does not match its body"]
    out = []
    for r in data.get("entries") or []:
        label = f"{r.get('viewport')}/{r.get('section_part')}"
        for side in ("native", "output"):
            row = r.get(side) or {}
            path = root / str(row.get("path", ""))
            if not path.is_file():
                out.append(f"{label}: {side} file is missing: {row.get('path')}")
            elif sha256_file(path) != row.get("sha256"):
                out.append(f"{label}: {side} file {row.get('path')} no longer matches the receipt sha256")
            else:
                try:
                    if read_dims(path) != (row.get("width"), row.get("height")):
                        out.append(f"{label}: {side} file {row.get('path')} pixels differ from the receipt")
                except Refused as exc:
                    out.append(str(exc))
    if not data.get("entries"):
        out.append("export receipt has no entries")
    return out


def run(root, raw_dir="raw-native", viewports=("desktop", "mobile"), widths=None,
        receipt_name="export-receipt.json", dry_run=False):
    root = Path(root)
    widths = dict(DEFAULT_WIDTHS, **(widths or {}))
    if not root.is_dir():
        raise Refused(f"final-mockups folder is missing: {root}")
    if "/" in raw_dir or raw_dir in ("", ".", "..") or raw_dir in viewports:
        raise Refused(f"--raw-dir must be a plain folder name inside {root}, not {raw_dir!r}")
    receipt_path = root / receipt_name
    prior = load_prior(receipt_path)
    plan = []
    for vp in viewports:
        if vp not in widths:
            raise Refused(f"unknown viewport {vp!r}")
        plan.extend(plan_viewport(root, vp, widths[vp], raw_dir, prior))
    summary = {"export": [], "unchanged": [], "adopt": []}
    for e in plan:
        summary["export" if e["action"] == "export" else e["action"]].append(e["out_rel"])
    if dry_run:
        return summary, None
    for e in plan:
        execute(e)
    if not summary["export"] and not summary["adopt"] and receipt_path.is_file() and not verify_receipt(receipt_path, root):
        return summary, json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt = build_receipt(root, plan, raw_dir, {v: widths[v] for v in viewports})
    tmp = receipt_path.with_name(receipt_path.name + ".tmp")
    tmp.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, receipt_path)
    return summary, receipt


def main(argv=None):
    ap = argparse.ArgumentParser(description="Export final-mockups native slices to page width, keeping the natives.")
    ap.add_argument("final_mockups", type=Path)
    ap.add_argument("--raw-dir", default="raw-native")
    ap.add_argument("--viewports", default="desktop,mobile")
    ap.add_argument("--desktop-width", type=int, default=DEFAULT_WIDTHS["desktop"])
    ap.add_argument("--mobile-width", type=int, default=DEFAULT_WIDTHS["mobile"])
    ap.add_argument("--receipt", default="export-receipt.json")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("FAIL: Pillow is required. Install the Python package 'Pillow' in this runtime.")
        return 2
    viewports = tuple(v.strip() for v in args.viewports.split(",") if v.strip())
    try:
        summary, receipt = run(args.final_mockups, args.raw_dir, viewports,
                               {"desktop": args.desktop_width, "mobile": args.mobile_width},
                               args.receipt, args.dry_run)
    except Refused as exc:
        print(f"FAIL: refused: {exc}")
        return 1
    tag = "DRY-RUN" if args.dry_run else "PASS"
    print(f"{tag}: export {len(summary['export'])}, adopt {len(summary['adopt'])}, "
          f"unchanged {len(summary['unchanged'])} slice(s)")
    for key in ("export", "adopt", "unchanged"):
        for rel in summary[key]:
            print(f"  {key.upper()} {rel}")
    if receipt:
        print(f"Receipt: {Path(args.final_mockups) / args.receipt} ({receipt['receipt_sha256'][:12]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
