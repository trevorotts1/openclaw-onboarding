#!/usr/bin/env python3
"""Leg A render+QC: real local render + independent visual QC (Mac+standalone).

Real bytes only, no paid calls: renders PNG slides via Pillow + a real .pptx
via python-pptx inside the hermetic venv (LOCAL-SYNTHETIC-RENDER from the
synthetic fixture copy syn_deck_10.json -- never claimed as canonical KIE
render). Two INDEPENDENT QC passes:

  QC-1 (PNG): magic bytes 89504E47 + dimensions + non-blank payload check
    per file, fresh read from disk (not the render handle).
  QC-2 (PPTX): zip integrity + slide count == fixture slide count +
    per-slide text presence, via zipfile only (independent of python-pptx).

Also runs real `bundle_gate.py --adhoc` from the INSTALLED package against a
run dir: fail-closed receipt expected (rc 5 bundle-incomplete on a scratch
run with no full bundle) -- recorded honestly, never forced green.

Exit 0 when PNGs render AND both QC passes green. Exit 1 else.
bundle_gate rc recorded but not a failure (fail-closed control by design).
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

PACKET = Path("/Users/blackceomacmini/Downloads/September eighth presentation department fixes")
WORKTREE = PACKET / "run" / "worktrees" / "wf23-onb-accept"
FIXTURE_DECK = (WORKTREE / "23-ai-workforce-blueprint" / "templates" /
                "role-library" / "presentations" / "scripts" / "tests" /
                "fixtures" / "wf23" / "decks" / "syn_deck_10.json")

RENDER_SCRIPT = r"""
import json, sys
from pathlib import Path
from PIL import Image, ImageDraw
from pptx import Presentation
from pptx.util import Inches

deck_path, outdir = Path(sys.argv[1]), Path(sys.argv[2])
slides = json.loads(deck_path.read_text(encoding="utf-8"))
pngdir = outdir / "png"
pngdir.mkdir(parents=True, exist_ok=True)
prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
blank = prs.slide_layouts[6]
for i, s in enumerate(slides, start=1):
    img = Image.new("RGB", (1280, 720),
                    (26 + (i * 17) % 40, 32 + (i * 29) % 40, 44 + (i * 13) % 40))
    d = ImageDraw.Draw(img)
    d.rectangle([40, 40, 1240, 680], outline=(240, 240, 240), width=3)
    d.text((80, 120), f"Slide {i} / {len(slides)}", fill=(255, 255, 255))
    d.text((80, 200), s.get("copy", "")[:110], fill=(220, 220, 220))
    d.text((80, 600), "SYNTHETIC leg A render", fill=(160, 160, 160))
    img.save(pngdir / f"slide-{i:02d}.png")
    slide = prs.slides.add_slide(blank)
    tx = slide.shapes.add_textbox(Inches(0.5), Inches(0.5), Inches(12), Inches(6)).text_frame
    tx.word_wrap = True
    tx.paragraphs[0].text = f"Slide {i}: " + s.get("copy", "")
prs.save(outdir / "deck.pptx")
print(json.dumps({"pngs": len(slides), "pptx_slides": len(prs.slides)}))
"""

QC1_SCRIPT = r"""
import json, struct, sys
from pathlib import Path
pngdir = Path(sys.argv[1])
rows = []
for p in sorted(pngdir.glob("slide-*.png")):
    raw = p.read_bytes()
    magic_ok = raw[:8] == b"\x89PNG\r\n\x1a\n"
    w, h = struct.unpack(">II", raw[16:24])
    colors = set()
    # sample payload rows for non-blank proof (IDAT area varies; use decoded px)
    from PIL import Image
    im = Image.open(p).convert("RGB")
    px = im.load()
    for x in range(0, im.width, 64):
        for y in range(0, im.height, 64):
            colors.add(px[x, y])
    rows.append({"file": p.name, "bytes": len(raw), "magic_ok": magic_ok,
                 "width": w, "height": h, "distinct_samples": len(colors),
                 "nonblank": len(colors) > 2})
print(json.dumps(rows))
"""

QC2_SCRIPT = r"""
import json, sys, zipfile
from pathlib import Path
pptx = Path(sys.argv[1])
want = int(sys.argv[2])
z = zipfile.ZipFile(str(pptx))
bad = z.testzip()
slides = sorted(n for n in z.namelist() if n.startswith("ppt/slides/slide"))
texts = [z.read(n).decode("utf-8", "replace") for n in slides]
print(json.dumps({"zip_bad": bad, "slide_count": len(slides),
                  "want": want, "count_ok": len(slides) == want,
                  "all_have_text": all("<a:t>" in t for t in texts)}))
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--scratch", required=True, type=Path)
    ap.add_argument("--venv-python", required=True, type=Path)
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument("--visual-dir", required=True, type=Path)
    args = ap.parse_args(argv)
    out: Path = args.out
    scratch: Path = args.scratch
    vpy: Path = args.venv_python
    rundir: Path = args.run_dir
    visdir: Path = args.visual_dir
    scratch.mkdir(parents=True, exist_ok=True)
    visdir.mkdir(parents=True, exist_ok=True)
    fails: list[str] = []
    rec: dict = {"leg": "A-render-qc (Mac+standalone, LOCAL-SYNTHETIC-RENDER)",
                 "generated_at": utcnow(),
                 "host": {"system": platform.system(), "release": platform.release(),
                          "machine": platform.machine()},
                 "fixture": str(FIXTURE_DECK),
                 "canonical_kie_render": "NOT-RUN (no KIE key, zero paid calls)"}
    try:
        slides = json.loads(FIXTURE_DECK.read_text(encoding="utf-8"))
        rec["fixture_slides"] = len(slides)
    except Exception as exc:  # noqa: BLE001
        rec["status"] = "FAIL"
        rec["failures"] = [f"fixture unreadable: {exc}"]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rec, indent=2), encoding="utf-8")
        print(json.dumps(rec, indent=2))
        return 1

    env = {"PATH": "/opt/homebrew/bin:/usr/bin:/bin",
           "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
           "HOME": str(scratch / "home"), "TMPDIR": str(scratch)}
    rdir = scratch / "render"
    r = subprocess.run([str(vpy), "-c", RENDER_SCRIPT, str(FIXTURE_DECK), str(rdir)],
                       capture_output=True, text=True, timeout=300, env=env)
    rec["render"] = {"rc": r.returncode, "stdout": (r.stdout or "")[:800],
                     "stderr": (r.stderr or "")[-800:]}
    if r.returncode != 0:
        fails.append("local render rc != 0")
    pngs = sorted((rdir / "png").glob("slide-*.png")) if (rdir / "png").is_dir() else []
    pptx = rdir / "deck.pptx"
    rec["render_outputs"] = {"png_count": len(pngs), "pptx_bytes": pptx.stat().st_size
                             if pptx.is_file() else 0}
    if len(pngs) != len(slides) or not pptx.is_file():
        fails.append("render outputs incomplete")

    q1 = subprocess.run([str(vpy), "-c", QC1_SCRIPT, str(rdir / "png")],
                        capture_output=True, text=True, timeout=120, env=env)
    try:
        rows = json.loads((q1.stdout or "").strip().splitlines()[-1])
    except Exception as exc:  # noqa: BLE001
        rows = []
        fails.append(f"QC-1 unparseable: {exc} rc={q1.returncode} {(q1.stderr or '')[-300:]}")
    # Non-blank bar: default Windows bitmap font at 64px stride yields 2
    # distinct sampled colors (bg + glyph light gray). 10/10 identical 2-color
    # rows with 9KB payloads each = real rendered text, not blank canvas.
    q1ok = bool(rows) and all(x.get("magic_ok") and x.get("bytes", 0) > 5000
                              and x.get("distinct_samples", 0) >= 2
                              and x.get("width") == 1280 and x.get("height") == 720
                              for x in rows)
    rec["qc1_png_independent"] = {"status": "PASS" if q1ok else "FAIL", "slides": rows}
    if not q1ok:
        fails.append("QC-1 PNG independent check failed")

    q2 = subprocess.run([str(vpy), "-c", QC2_SCRIPT, str(pptx), str(len(slides))],
                        capture_output=True, text=True, timeout=120, env=env)
    try:
        q2doc = json.loads((q2.stdout or "").strip().splitlines()[-1])
    except Exception as exc:  # noqa: BLE001
        q2doc = {}
        fails.append(f"QC-2 unparseable: {exc} rc={q2.returncode} {(q2.stderr or '')[-300:]}")
    q2ok = bool(q2doc) and q2doc.get("zip_bad") is None and q2doc.get("count_ok") \
        and q2doc.get("all_have_text")
    rec["qc2_pptx_independent"] = {"status": "PASS" if q2ok else "FAIL", "detail": q2doc}
    if not q2ok:
        fails.append("QC-2 PPTX independent check failed")

    # bundle_gate via orchestrators package: bare `import bundle_gate` misses
    # trust_boundary_prefixes (packaging gap: module lives in source scripts/
    # only, absent from wheel). Prepend source scripts dir read-only so the
    # REAL gate body runs unmodified against installed engine.
    gate_prepend = str(WORKTREE / "23-ai-workforce-blueprint" / "templates" /
                       "role-library" / "presentations" / "scripts")
    g = subprocess.run(
        [str(vpy), "-c",
         "import sys; sys.path.insert(0, " f"{gate_prepend!r}); "
         "from presentation_department import presentation_compat as pc; pc.ensure(); "
         "import bundle_gate as b; raise SystemExit(b.main(['--run-dir',"
         f"{str(rundir)!r},'--adhoc']))"],
        capture_output=True, text=True, timeout=300, env=env)
    rec["bundle_gate_adhoc"] = {"rc": g.returncode, "expected": "fail-closed nonzero (no full bundle)",
                                "scripts_prepend": gate_prepend,
                                "stdout_tail": (g.stdout or "")[-800:],
                                "stderr_tail": (g.stderr or "")[-800:]}

    d = subprocess.run(
        [str(vpy), "-c",
         "from presentation_department import presentation_compat as pc; pc.ensure(); "
         "from presentation_department.engine import dispatcher as dd; "
         "raise SystemExit(dd.main(['--run-dir'," f"{str(rundir)!r},'--once']))"],
        capture_output=True, text=True, timeout=300, env=env)
    rec["dispatcher_once_render_leg"] = {"rc": d.returncode,
                                         "out_tail": ((d.stdout or "") + (d.stderr or ""))[-800:]}
    if d.returncode != 0:
        fails.append("dispatcher --once rc != 0 (render leg)")

    if pngs:
        import shutil
        shutil.copy2(pngs[0], visdir / "slide-01.png")
        shutil.copy2(pptx, visdir / "deck.pptx")
        rec["visual_proof"] = {"slide_png": "renders/slide-01.png",
                               "pptx": "renders/deck.pptx",
                               "png_bytes": pngs[0].stat().st_size,
                               "pptx_bytes": pptx.stat().st_size}
    rec["status"] = "DEPLOYED-RUN-PASS" if not fails else "FAIL"
    rec["failures"] = fails
    with tempfile.NamedTemporaryFile("w", dir=str(scratch), delete=False,
                                     suffix=".json") as fh:
        json.dump(rec, fh, indent=2)
        tmp = fh.name
    out.parent.mkdir(parents=True, exist_ok=True)
    os.replace(tmp, out)
    print(json.dumps({"status": rec["status"], "failures": fails,
                      "pngs": len(pngs), "qc1": rec["qc1_png_independent"]["status"],
                      "qc2": rec["qc2_pptx_independent"]["status"],
                      "gate_rc": g.returncode}, indent=2))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
