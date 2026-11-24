"""A synthetic thank-you style run folder for the export and production-record tools.

make_run(tmp) writes a run with two sections, desktop and mobile natives in
final-mockups, the production request, the stage executor record, the spend
ledger, the saved image-jobs requests, the layout references, the style input
and intake.json: the evidence write_production_record.py reads. Page widths in
the tests are small (desktop 144, mobile 39) so images stay tiny.
"""
import hashlib
import json
from pathlib import Path

from PIL import Image

WIDTHS = {"desktop": 144, "mobile": 39}
MODEL = "gpt-image-2-6/sunburst-image-to-image"
SECTIONS = [
    {"section_id": "1", "copy": "CONFIRMED\nYou are all set. Your seat is confirmed.", "cta": "Go to my access page"},
    {"section_id": "2", "copy": "Your payment has been received and your receipt is in your email.", "cta": None},
]
# viewport -> per-part native pixel size and requested ratio
NATIVES = {
    "desktop": [((288, 288), "1:1"), ((384, 216), "16:9")],
    "mobile": [((288, 288), "1:1"), ((216, 384), "9:16")],
}
# what the fake OCR reads off each native, by file name
OCR_TEXT = {
    "1": "CONFIRMED You are all set. Your seat is confirmed. Go to my access page",
    "2": "Your payment has been received and your receipt is in your email.",
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def make_run(tmp, widths=WIDTHS):
    run = Path(tmp) / "thank_you-run"
    fm = run / "final-mockups"
    (run / "visual-mockup").mkdir(parents=True)
    (run / "visual-mockup" / "page-visual-bible.json").write_text("{}", encoding="utf-8")
    (run / "intake.json").write_text(json.dumps({"design_style": "A"}), encoding="utf-8")
    images, calls = [], []
    for vp, specs in NATIVES.items():
        (fm / vp).mkdir(parents=True)
        wf = run / ("desktop-wireframe" if vp == "desktop" else "mobile-tablet")
        wf.mkdir(exist_ok=True)
        for n, ((w, h), ratio) in enumerate(specs, start=1):
            name = f"part-{n:02d}.png"
            Image.new("RGB", (w, h), (200 + n, 30 * n, 40)).save(fm / vp / name)
            Image.new("RGB", (20, 20), (9, 9, 9)).save(wf / f"section-{n:02d}.png")
            task = f"task{vp}{n}"
            key = f"key-{vp}-{n}"
            rel = f"final-mockups/{vp}/{name}"
            images.append({
                "file": rel, "section_id": str(n), "provider": "kie", "model": MODEL, "state": "settled",
                "actual_pixels": [w, h], "requested_ratio": ratio, "attempt": 1, "task_id": task,
                "sha256": sha(fm / vp / name), "prompt_sha256": "p" * 64, "request_sha256": "r" * 64,
                "identity": {"key": key, "attempt": 1},
                "inputs": [str(Path("/elsewhere/run") / wf.name / f"section-{n:02d}.png")],
            })
            calls.append({"file": rel, "task_id": task, "status": "done", "state": "settled", "id": f"id{vp}{n}"})
            job = run / "image-jobs" / f"final-mockups-{vp}-{name}-1440x760-aaaa{n}"
            (job / "requests").mkdir(parents=True)
            (job / "attempt-001.json").write_text(json.dumps(
                {"identity": {"key": key, "attempt": 1}, "task_id": task, "attempt": 1}), encoding="utf-8")
            (job / "requests" / "request-a001.json").write_text(json.dumps(
                {"input": {"input_urls": [f"https://example.invalid/{vp}/{n}.png"]}}), encoding="utf-8")
    (fm / "stage-executor-record.json").write_text(json.dumps({"stage": "final-mockups", "images": images}), encoding="utf-8")
    (run / "image-spend-ledger.json").write_text(json.dumps({"calls": calls}), encoding="utf-8")
    (run / "production-request-final-mockups.json").write_text(json.dumps({
        "model": MODEL, "input_extra": {"resolution": "4K"}, "sections": SECTIONS,
        "design_board": {"brand_name": "Dr Wall", "footer_taglines": ["Worthiness Gap"]},
    }), encoding="utf-8")
    return run


def fake_ocr(path):
    """What the reader returns for a native: the section's text, by part number."""
    n = str(int(Path(path).stem.split("-")[1]))
    return OCR_TEXT[n]
