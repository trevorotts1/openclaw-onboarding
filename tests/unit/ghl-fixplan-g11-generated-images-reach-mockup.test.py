#!/usr/bin/env python3
"""G-11 (fix plan B8, unowned): the generated images reach the final-mockups draw.

Both halves are proven here:
  * `--references`: the final-mockups production request is now built with the page's real
    pictures (image-map first, then image-generation-qc) instead of none;
  * `prior_slices`: the final-mockups job for a section carries that section's generated
    images, not only the wireframe and visual-mockup slices.

FAILS before the change: `prior_slices` returned only stage slices even with
image-generation-qc/Image-001.png present, and the request was built with no --references,
so the model invented the imagery.
"""
import importlib.machinery
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SE = ROOT / "71-blackceo-signature-page" / "scripts" / "stage_executor.py"
IS = ROOT / "83-black-friday-launcher" / "launcher_core" / "image_stages.py"


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def load_launcher_module():
    """image_stages uses relative imports; import it as part of its package."""
    root = ROOT / "83-black-friday-launcher"
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    import launcher_core.image_stages as mod  # noqa: PLC0415
    return mod


def png(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)


def main() -> int:
    fails = []
    se = load("se_g11", SE)
    is_mod = load_launcher_module()

    with tempfile.TemporaryDirectory(prefix="bld002-g11-") as d:
        rd = Path(d) / "run"
        (rd / "desktop-wireframe").mkdir(parents=True)
        (rd / "desktop-wireframe" / "image-inventory.json").write_text(json.dumps(
            {"images": [{"id": "IMG-001"}, {"id": "IMG-002"}]}), encoding="utf-8")
        (rd / "desktop-wireframe" / "section-plan.json").write_text(json.dumps(
            [{"section_id": "1", "image_slot_ids": ["IMG-001"]},
             {"section_id": "2", "image_slot_ids": ["IMG-002"]}]), encoding="utf-8")
        png(rd / "image-generation-qc" / "Image-001.png")
        png(rd / "image-generation-qc" / "Image-002.png")
        (rd / "image-map-upload").mkdir(parents=True)
        (rd / "image-map-upload" / "image-map.json").write_text(json.dumps(
            {"images": [{"id": "IMG-001", "asset_file": "Image-001.png"}]}), encoding="utf-8")
        section = {"section_id": "1", "slots": [{"slot_id": "IMG-001"}]}

        if not hasattr(se, "generated_images_for_section"):
            fails.append("G-11: stage_executor has no generated_images_for_section")
        try:
            picks = [str(p) for p in se.prior_slices("final-mockups", rd, 1,
                                                    "desktop/part-{n:02d}.png", section)]
        except TypeError as exc:
            picks = []
            fails.append("G-11: prior_slices cannot take the section (no generated images "
                         "can reach the draw): %s" % exc)
        if not any("Image-001.png" in p for p in picks):
            fails.append("G-11: prior_slices did not carry the section's generated image: %r" % (picks,))
        if any("Image-002.png" in p for p in picks):
            fails.append("G-11: prior_slices leaked ANOTHER section's image: %r" % (picks,))

        # --references half
        page_cls = getattr(is_mod, "_Page", None)
        if page_cls is None:
            fails.append("G-11: image_stages has no _Page")
        else:
            if not hasattr(page_cls, "generated_references"):
                fails.append("G-11: _Page has no generated_references")
            else:
                page = page_cls(run=rd, scripts=ROOT / "71-blackceo-signature-page" / "scripts",
                                runner=lambda cmd: (0, ""), provider="kie", allow_paid=True)
                refs = page.generated_references()
                if not any("Image-001.png" in r for r in refs):
                    fails.append("G-11: generated_references dropped the page images: %r" % (refs,))

                # produce_mockups must pass them as --references.
                seen = []

                def fake_call(script, *args):
                    seen.append((script, [str(a) for a in args]))
                    if script == "build_production_request.py":
                        (rd / "production-request-final-mockups.json").write_text("{}", encoding="utf-8")
                    return 0, ""

                page.call = fake_call  # type: ignore[assignment]
                (rd / "copy").mkdir(parents=True, exist_ok=True)
                (rd / "copy" / "internal-manuscript.md").write_text("# s\nbody\n", encoding="utf-8")
                (rd / "intake.json").write_text(json.dumps({"copy_version": "standard"}), encoding="utf-8")
                try:
                    page.produce_mockups()
                except Exception:  # noqa: BLE001  (the draw step may stop; we only inspect the build call)
                    pass
                build_calls = [a for s, a in seen if s == "build_production_request.py"]
                if not build_calls:
                    fails.append("G-11: produce_mockups never called build_production_request.py")
                elif "--references" not in build_calls[0]:
                    fails.append("G-11: the final-mockups request was built with NO --references: %r"
                                 % (build_calls[0],))

    for f in fails:
        print("FAIL: " + f)
    if fails:
        return 1
    print("PASS G-11: generated images reach the final-mockups draw via --references AND prior_slices")
    return 0


if __name__ == "__main__":
    sys.exit(main())
