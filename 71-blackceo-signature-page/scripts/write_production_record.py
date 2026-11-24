#!/usr/bin/env python3
"""Author a run's final-mockups production record from tool evidence only.

Usage:
  python3 scripts/write_production_record.py <run_dir> --stage desktop-wireframe|mobile-tablet
         [--request production-request-<stage>.json] [--allow-text ...] [--no-ocr-validate] [--overwrite]
  python3 scripts/write_production_record.py <run_dir> [--stage final-mockups]
         [--request production-request-final-mockups.json] [--viewports desktop,mobile]
         [--allow-text WORDS ... --allow-reason TEXT --allow-authority TEXT]
         [--no-ocr-validate] [--ocr-mobile] [--overwrite]

Writes `<run>/final-mockups/production-record.json` (the desktop record the stage
gate validates) and `<run>/final-mockups/mobile/production-record.json`, in the
contract of references/artifact-contracts.md ("Production method and per-section
build record"). Nothing in a record is typed by hand. Every field comes from one
of these sources, and a source that is missing or disagrees stops the run:

  * the production request: the section ids, order, copy, button text and model;
  * `stage-executor-record.json`: provider, model, task id, requested ratio,
    attempt, prompt hash and the native pixels of each generated image;
  * `image-spend-ledger.json`: a settled, done row for that file and task id;
  * `image-jobs/`: the saved request of that attempt, for the reference URLs;
  * `export-receipt.json` (export_native_slices.py), re-verified file by file:
    the native kept in raw-native, the page-width export, both sha256 and sizes;
  * the real pixels of every slice (width, height, native_aspect);
  * a text read-back made here: design_board.ocr_text (tesseract) reads each
    NATIVE image, and the read is compared with the section's own copy.

Text QC is honest or it fails. The OCR text is recorded verbatim (and in
text-qc-readback-<viewport>.json). Each OCR word is an exact match of the copy,
a known brand word, noise (under three letters or no letters), a harmless OCR
variant (one misread character of a copy word that was also read correctly
elsewhere), or a garbled word. Garbled words are put in the read-back, so the
validator recomputes the same set and the section fails; a section whose image
shows less than the Design Board's floor of its copy also fails. A failing section
is never given a pass.

An allow-text override is never silent. `--allow-text` (extra brand or chrome words the
images may carry) requires `--allow-reason` and `--allow-authority`; each section's text_qc
then carries an `allowed_text` object: `words` (the exact allowed words that image shows and
its copy does not), `allow_list` (the whole list given), `reason`, `authority`. The validator
accepts and requires those fields whenever `allowed_text` is present; it loosens nothing.

Finally the tool runs validate_production_record.py itself (desktop with --ocr
and --model, as the stage gate does; mobile plain unless --ocr-mobile) on a
candidate file. A record that fails is deleted, never left in place, and the
failures are printed. Both records are replaced together or not at all.

Wireframe stages (SWB-290). `--stage desktop-wireframe` or `--stage mobile-tablet` writes the
ONE record of that stage, `<run>/<stage>/production-record.json` (artifact "wireframe"), from
the same kinds of evidence: the request, `<stage>/stage-executor-record.json`, the spend
ledger, the saved image-jobs request (reference URLs and the `resolution` actually sent), the
FLAT export receipt that `export_native_slices.py <stage dir>` wrote (natives kept in
`<stage>/raw-native/section-NN.png`, slices exported to the page width), the real pixels, and
an OCR read of each NATIVE. The read is compared with the section's copy plus the wireframe's own
annotations (the section name, its behavior note, the type-spec vocabulary); any other word is
garbled and the section fails, or is named with `--allow-text`, `--allow-reason`,
`--allow-authority`. Nothing in a wireframe record is typed by hand. The record then passes
`validate_production_record.py` before it is left in place, and `stitch_sections.py` and
`combine_review_pdf.py` read it.

Exit codes: 0 both records written and validated, 1 refused or failed (named
lines), 2 usage or a missing dependency.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import export_native_slices as exporter  # noqa: E402
import validate_production_record as vpr  # noqa: E402

VIEWPORT = {
    "desktop": {"wireframe_dir": "desktop-wireframe", "stitched": "mockup-full.png"},
    "mobile": {"wireframe_dir": "mobile-tablet", "stitched": "mockup-full-mobile.png"},
}
WIREFRAME_VIEWPORT = exporter.FLAT_VIEWPORT  # stage -> viewport (flat <stage>/section-NN.png layout)
WIREFRAME_LOGO_WAIVED = ("the wireframe is a private annotated build spec; the client logo is placed as a "
                         "supplied file at the responsive-html and install stages, not drawn by the image model")
# words a wireframe sheet legitimately prints besides the copy (references/wireframe-build-spec.json:
# section chip and name tab, inline type specs, plate labels, CTA microcopy line, behavior note)
WIREFRAME_ANNOTATION_VOCAB = (
    "section chip name tab type spec specs px h1 h2 h3 h4 subhead body eyebrow headline cta microcopy "
    "behavior note image plate slot label ratio treatment mask circle widths header strip desktop mobile "
    "tablet wireframe overlay light dark field backdrop")
PDF_OUTPUT = "review-pdfs (combine_review_pdf.py)"
DEFAULT_FM_REQUEST = "production-request-final-mockups.json"
QC_METHOD = ("design_board.ocr_text (tesseract) read of the native image kept in raw-native, compared with the "
             "section's own copy; the read-back lists the distinct words of that read that are in the copy, "
             "garbled words included")


class Refused(Exception):
    pass


def _board():
    import design_board
    return design_board


def read_json(path, what):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Refused(f"{what} is missing or unreadable: {path} ({type(exc).__name__})") from exc


def classify_ocr(expected_text, ocr_text, chrome_text, board):
    """Sort every distinct OCR word. Returns a dict of lists plus the coverage of the copy."""
    expected = vpr.tokens(expected_text)
    exp_set = set(expected)
    chrome = set(vpr.tokens(chrome_text))
    seen = []
    for tok in vpr.tokens(ocr_text):
        if tok not in seen:
            seen.append(tok)
    seen_set = set(seen)
    out = {"matched": [], "chrome": [], "noise": [], "variants": [], "garbled": []}
    for tok in seen:
        if tok in exp_set:
            out["matched"].append(tok)
        elif tok in chrome:
            out["chrome"].append(tok)
        elif len(tok) < 3 or not any(c.isalpha() for c in tok):
            out["noise"].append(tok)
        else:
            near = [w for w in exp_set if board.within_one(tok, w)]
            if near and all(w in seen_set for w in near):
                out["variants"].append(tok)  # a misread twin of a copy word that was read correctly too
            else:
                out["garbled"].append(tok)
    out["coverage"] = board.support(board.tokens(expected_text), board.tokens(ocr_text))
    out["floor"] = board.OCR_FLOOR
    return out


def text_qc(expected_text, native_path, attempts, ocr, chrome_text, board, allow=None):
    """allow, when given, is (words, reason, authority): the override the section's text_qc records."""
    ocr_text = ocr(Path(native_path))
    sort = classify_ocr(expected_text, ocr_text, chrome_text, board)
    readback = " ".join(sort["matched"] + sort["garbled"])
    garbled = vpr.garbled_words(expected_text, readback)
    shown = sort["coverage"] >= sort["floor"]
    verdict = "pass" if not garbled and shown else "fail"
    qc = {
        "checked_at_native_resolution": True,
        "expected_text": expected_text,
        "readback_text": readback,
        "garbled_words": garbled,
        "verdict": verdict,
        "attempts": attempts,
        "qc_method": QC_METHOD,
        "ocr_text": ocr_text,
        "ocr_coverage_of_copy": round(sort["coverage"], 3),
        "ocr_coverage_floor": sort["floor"],
        "ocr_brand_words_seen": sort["chrome"],
        "ocr_variants_of_copy_words": sort["variants"],
        "ocr_noise_ignored": sort["noise"],
    }
    if allow is not None:
        words, reason, authority = allow
        allow_tokens = []
        for w in words:
            for tok in vpr.tokens(w):
                if tok not in allow_tokens:
                    allow_tokens.append(tok)
        expected_set = set(vpr.tokens(expected_text))
        shown = set(vpr.tokens(ocr_text))
        qc["allowed_text"] = {
            "words": sorted(t for t in allow_tokens if t in shown and t not in expected_set),
            "allow_list": sorted(allow_tokens),
            "reason": reason,
            "authority": authority,
        }
    problems = []
    if garbled:
        problems.append(f"the native image shows word(s) the copy does not contain: {', '.join(garbled)}")
    if not shown:
        problems.append(f"the native image shows {sort['coverage']:.0%} of its copy (floor {sort['floor']:.0%})")
    return qc, problems


def find_job_urls(run_dir, image):
    """The reference URLs of the attempt that made `image`, from its saved request in image-jobs."""
    key = (image.get("identity") or {}).get("key")
    attempt = image.get("attempt")
    jobs = Path(run_dir) / "image-jobs"
    if not key or not isinstance(attempt, int) or not jobs.is_dir():
        raise Refused(f"{image.get('file')}: no identity key or attempt to find its saved request in image-jobs")
    for job in sorted(jobs.iterdir()):
        att = job / f"attempt-{attempt:03d}.json"
        if not att.is_file():
            continue
        try:
            data = json.loads(att.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (data.get("identity") or {}).get("key") != key:
            continue
        if data.get("task_id") not in (None, image.get("task_id")):
            raise Refused(f"{image.get('file')}: image-jobs attempt names task {data.get('task_id')} "
                          f"but the executor record names {image.get('task_id')}")
        req = read_json(job / "requests" / f"request-a{attempt:03d}.json", "the saved request of the attempt")
        urls = (req.get("input") or {}).get("input_urls") or []
        return [u for u in urls if isinstance(u, str)]
    raise Refused(f"{image.get('file')}: no image-jobs attempt carries identity key {key[:12]} "
                  f"attempt {attempt}; the reference URLs cannot be recorded from evidence")


def ratio_ok(requested, width, height):
    try:
        a, b = (int(x) for x in str(requested).split(":"))
    except ValueError:
        return False
    return abs(width / height - a / b) <= 0.01 * (a / b)


def build_record(run_dir, stage, viewport, request, executor, ledger, receipt, receipt_name, ocr,
                 board, allow_text, design_style, allow=None):
    run_dir = Path(run_dir)
    stage_dir = run_dir / stage
    vp_dir = stage_dir / viewport
    cfg = VIEWPORT[viewport]
    sections = request.get("sections")
    if not isinstance(sections, list) or not sections:
        raise Refused(f"the request has no sections: cannot name the {viewport} slices")
    rows = {(r["viewport"], r["section_part"]): r for r in receipt["entries"]}
    on_disk = sorted(p.name for p in vp_dir.glob("part-*.png")) if vp_dir.is_dir() else []
    wanted = [f"part-{i:02d}.png" for i in range(1, len(sections) + 1)]
    if on_disk != wanted:
        raise Refused(f"{viewport}: the request names {len(sections)} section(s) ({', '.join(wanted)}) but "
                      f"{stage}/{viewport} holds {on_disk or 'no slices'}; every request section needs exactly one slice")
    receipt_names = sorted(n for (v, n) in rows if v == viewport)
    if receipt_names != wanted:
        raise Refused(f"{viewport}: the export receipt covers {receipt_names}, not the request's {wanted}")
    by_file = {i.get("file"): i for i in executor.get("images", []) if isinstance(i, dict)}
    ledger_rows = ledger.get("calls") if isinstance(ledger, dict) else None
    if not isinstance(ledger_rows, list):
        raise Refused("image-spend-ledger.json has no calls list")
    base_dir = vp_dir if viewport == "mobile" else stage_dir
    out_sections, evidence, problems = [], [], []
    for number, (section, name) in enumerate(zip(sections, wanted), start=1):
        sid = str(section.get("section_id"))
        label = f"{viewport}/{name} (section {sid})"
        row = rows[(viewport, name)]
        native_rel = row["native"]["path"]
        image = by_file.get(f"{stage}/{viewport}/{name}")
        if image is None:
            raise Refused(f"{label}: the executor record has no generated image for {stage}/{viewport}/{name}")
        if str(image.get("section_id")) != sid:
            raise Refused(f"{label}: the executor record says this slice is section {image.get('section_id')}")
        if image.get("provider") != "kie" or not str(image.get("model", "")).startswith("gpt-image"):
            raise Refused(f"{label}: provider {image.get('provider')!r} model {image.get('model')!r} is not "
                          f"the KIE.ai GPT-image route; a record never claims it")
        if request.get("model") != image.get("model"):
            raise Refused(f"{label}: the request names model {request.get('model')!r} but the image was made by "
                          f"{image.get('model')!r}")
        if image.get("sha256") != row["native"]["sha256"]:
            raise Refused(f"{label}: the executor record's sha256 is not the kept native's ({native_rel}); "
                          f"the native is not the image the executor delivered")
        nw, nh = row["native"]["width"], row["native"]["height"]
        if list(image.get("actual_pixels") or []) != [nw, nh]:
            raise Refused(f"{label}: the executor record says {image.get('actual_pixels')} pixels, the native is {nw}x{nh}")
        if not ratio_ok(image.get("requested_ratio"), nw, nh):
            raise Refused(f"{label}: generated {nw}x{nh} does not equal the requested ratio {image.get('requested_ratio')}")
        match = [r for r in ledger_rows if r.get("file") == image["file"] and r.get("task_id") == image.get("task_id")
                 and r.get("status") == "done"]
        if not match:
            raise Refused(f"{label}: no done row in image-spend-ledger.json for task {image.get('task_id')}")
        urls = find_job_urls(run_dir, image)
        if str(image["model"]).endswith("image-to-image") and not urls:
            raise Refused(f"{label}: an image-to-image call with no reference URL in its saved request")
        want = f"{VIEWPORT[viewport]['wireframe_dir']}/section-{number:02d}.png"
        layout = next((i for i in image.get("inputs") or [] if "/".join(Path(i).parts[-2:]) == want), None)
        if layout is None or not (run_dir / want).is_file():
            raise Refused(f"{label}: the layout reference {want} is not among the executor's inputs or not on disk")
        layout_ref = os.path.relpath(run_dir / want, base_dir.parent)
        if not (run_dir / "visual-mockup" / "page-visual-bible.json").is_file():
            raise Refused("visual-mockup/page-visual-bible.json (the style input) is not on disk")
        ow, oh = row["output"]["width"], row["output"]["height"]
        expected = str(section.get("copy") or "").strip()
        if section.get("cta"):
            expected = f"{expected}\n{section['cta']}".strip()
        if not expected:
            raise Refused(f"{label}: the request carries no copy for this section")
        qc, why = text_qc(expected, run_dir / stage / native_rel, image.get("attempt") or 1, ocr, allow_text, board,
                          allow)
        problems.extend(f"{label}: {w}" for w in why)
        evidence.append({"section_id": sid, "slice": f"{viewport}/{name}", "native": native_rel,
                         "ocr_text": qc["ocr_text"], "verdict": qc["verdict"], "problems": why})
        generation = {
            "route": vpr.ROUTE, "model_id": image["model"], "model_source": "explicit-request",
            "layout_reference": layout_ref, "reference_urls": urls,
            "style_input": "visual-mockup/page-visual-bible.json", "native_aspect": f"{ow}x{oh}",
            "native_pixels": f"{nw}x{nh}", "provider": image["provider"], "task_id": image["task_id"],
            "requested_ratio": image["requested_ratio"], "prompt_sha256": image.get("prompt_sha256"),
            "request_sha256": image.get("request_sha256"), "attempt": image.get("attempt"),
            "ledger_id": match[-1].get("id"), "source_image": f"{stage}/{native_rel}",
            "source_sha256": row["native"]["sha256"],
        }
        res = (request.get("input_extra") or {}).get("resolution")
        if res:
            generation["resolution"] = res
        out_sections.append({
            "section_id": sid,
            "slice": name if viewport == "mobile" else f"{viewport}/{name}",
            "width": ow, "height": oh, "generation": generation,
            "export": {"source_px": f"{nw}x{nh}", "scale_factor": row["scale_factor"], "upscaled": row["upscaled"],
                       "method": receipt["method"], "receipt": receipt_name, "receipt_sha256": receipt["receipt_sha256"],
                       "native_path": f"{stage}/{native_rel}", "native_sha256": row["native"]["sha256"],
                       "output_sha256": row["output"]["sha256"]},
            "text_qc": qc,
        })
    record = {"artifact": "mockup", "stage": stage, "page_width": receipt["page_widths"][viewport]}
    if design_style in ("A", "B", "C"):
        record["design_style"] = design_style
    record.update(stitched_output=cfg["stitched"], pdf_output=PDF_OUTPUT, sections=out_sections)
    return record, evidence, problems


def validate_candidate(candidate, ocr_flag, model):
    cmd = [sys.executable, str(HERE / "validate_production_record.py"), str(candidate)]
    if ocr_flag:
        cmd.append("--ocr")
    if model:
        cmd += ["--model", model]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def find_job_input(run_dir, image):
    """The saved request `input` of the attempt that made `image` (reference URLs, resolution sent)."""
    key = (image.get("identity") or {}).get("key")
    attempt = image.get("attempt")
    jobs = Path(run_dir) / "image-jobs"
    if not key or not isinstance(attempt, int) or not jobs.is_dir():
        raise Refused(f"{image.get('file')}: no identity key or attempt to find its saved request in image-jobs")
    for job in sorted(jobs.iterdir()):
        att = job / f"attempt-{attempt:03d}.json"
        if not att.is_file():
            continue
        try:
            data = json.loads(att.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (data.get("identity") or {}).get("key") != key:
            continue
        if data.get("task_id") not in (None, image.get("task_id")):
            raise Refused(f"{image.get('file')}: image-jobs attempt names task {data.get('task_id')} "
                          f"but the executor record names {image.get('task_id')}")
        req = read_json(job / "requests" / f"request-a{attempt:03d}.json", "the saved request of the attempt")
        return req.get("input") or {}
    raise Refused(f"{image.get('file')}: no image-jobs attempt carries identity key {key[:12]} "
                  f"attempt {attempt}; the reference URLs cannot be recorded from evidence")


def wireframe_annotation_text(section, request):
    """The words this section's own wireframe annotations print: its name, its behavior note, its
    type specs, plus the fixed sheet vocabulary. Read from the request and the page type's spec."""
    parts = [WIREFRAME_ANNOTATION_VOCAB, str(section.get("section_name") or ""), str(section.get("name") or "")]
    notes = section.get("behavior_notes")
    parts += [notes] if isinstance(notes, str) else [str(n) for n in notes or []]
    specs = section.get("type_specs")
    if isinstance(specs, dict):
        parts += [f"{k} {v}" for k, v in specs.items()]
    try:
        import page_role
        spec = page_role.request_spec(request)
        entry = page_role.section_spec(spec, section.get("section_id")) if spec else None
    except Exception:
        entry = None
    if entry:
        parts += [str(entry.get("name") or ""), str(entry.get("framework_name") or ""), str(entry.get("note") or "")]
    return " ".join(p for p in parts if p)


def build_wireframe_record(run_dir, stage, request, executor, ledger, receipt, receipt_name, ocr, board,
                           chrome_text, design_style, allow=None):
    run_dir = Path(run_dir)
    stage_dir = run_dir / stage
    viewport = WIREFRAME_VIEWPORT[stage]
    sections = request.get("sections")
    if not isinstance(sections, list) or not sections:
        raise Refused("the request has no sections: cannot name the wireframe slices")
    if receipt.get("layout") != "flat" or receipt.get("stage") != stage:
        raise Refused(f"the export receipt is not the flat export of {stage} (export_native_slices.py "
                      f"{stage_dir} writes it); a wireframe record cites that receipt only")
    rows = {(r["viewport"], r["section_part"]): r for r in receipt["entries"]}
    on_disk = sorted(p.name for p in stage_dir.glob("section-*.png"))
    wanted = [f"section-{i:02d}.png" for i in range(1, len(sections) + 1)]
    if on_disk != wanted:
        raise Refused(f"the request names {len(sections)} section(s) ({', '.join(wanted)}) but {stage} holds "
                      f"{on_disk or 'no slices'}; every request section needs exactly one slice")
    receipt_names = sorted(n for (v, n) in rows if v == viewport)
    if receipt_names != wanted:
        raise Refused(f"the export receipt covers {receipt_names}, not the request's {wanted}")
    plan_ref = f"{stage}/section-plan.json"
    if not (run_dir / plan_ref).is_file():
        raise Refused(f"{plan_ref} (the section plan, a wireframe section's layout reference) is not on disk")
    if not (run_dir / "private" / "brand.json").is_file():
        raise Refused("private/brand.json (the wireframe's style input) is not on disk")
    by_file = {i.get("file"): i for i in executor.get("images", []) if isinstance(i, dict)}
    ledger_rows = ledger.get("calls") if isinstance(ledger, dict) else None
    if not isinstance(ledger_rows, list):
        raise Refused("image-spend-ledger.json has no calls list")
    out_sections, evidence, problems = [], [], []
    for section, name in zip(sections, wanted):
        sid = str(section.get("section_id"))
        label = f"{stage}/{name} (section {sid})"
        row = rows[(viewport, name)]
        native_rel = row["native"]["path"]
        image = by_file.get(f"{stage}/{name}")
        if image is None:
            raise Refused(f"{label}: the executor record has no generated image for {stage}/{name}")
        if str(image.get("section_id")) != sid:
            raise Refused(f"{label}: the executor record says this slice is section {image.get('section_id')}")
        if image.get("provider") != "kie" or not str(image.get("model", "")).startswith("gpt-image"):
            raise Refused(f"{label}: provider {image.get('provider')!r} model {image.get('model')!r} is not "
                          f"the KIE.ai GPT-image route; a record never claims it")
        if request.get("model") != image.get("model"):
            raise Refused(f"{label}: the request names model {request.get('model')!r} but the image was made by "
                          f"{image.get('model')!r}")
        if image.get("sha256") != row["native"]["sha256"]:
            raise Refused(f"{label}: the executor record's sha256 is not the kept native's ({native_rel}); "
                          f"the native is not the image the executor delivered")
        nw, nh = row["native"]["width"], row["native"]["height"]
        if list(image.get("actual_pixels") or []) != [nw, nh]:
            raise Refused(f"{label}: the executor record says {image.get('actual_pixels')} pixels, the native is {nw}x{nh}")
        if not str(image.get("requested_ratio") or "").strip():
            raise Refused(f"{label}: the executor record names no requested ratio; every section's ratio must be explicit")
        if not ratio_ok(image.get("requested_ratio"), nw, nh):
            raise Refused(f"{label}: generated {nw}x{nh} does not equal the requested ratio {image.get('requested_ratio')}")
        match = [r for r in ledger_rows if r.get("file") == image["file"] and r.get("task_id") == image.get("task_id")
                 and r.get("status") == "done"]
        if not match:
            raise Refused(f"{label}: no done row in image-spend-ledger.json for task {image.get('task_id')}")
        job_input = find_job_input(run_dir, image)
        urls = [u for u in job_input.get("input_urls") or [] if isinstance(u, str)]
        if str(image["model"]).endswith("image-to-image") and not urls:
            raise Refused(f"{label}: an image-to-image call with no reference URL in its saved request")
        ow, oh = row["output"]["width"], row["output"]["height"]
        expected = str(section.get("copy") or "").strip()
        if section.get("cta"):
            expected = f"{expected}\n{section['cta']}".strip()
        if not expected:
            raise Refused(f"{label}: the request carries no copy for this section")
        chrome = f"{chrome_text} {wireframe_annotation_text(section, request)}"
        qc, why = text_qc(expected, run_dir / stage / native_rel, image.get("attempt") or 1, ocr, chrome, board, allow)
        problems.extend(f"{label}: {w}" for w in why)
        evidence.append({"section_id": sid, "slice": name, "native": native_rel,
                         "ocr_text": qc["ocr_text"], "verdict": qc["verdict"], "problems": why})
        generation = {
            "route": vpr.ROUTE, "model_id": image["model"], "model_source": "explicit-request",
            "layout_reference": plan_ref, "reference_urls": urls,
            "style_input": "private/brand.json", "native_aspect": f"{ow}x{oh}",
            "native_pixels": f"{nw}x{nh}", "provider": image["provider"], "task_id": image["task_id"],
            "requested_ratio": image["requested_ratio"], "prompt_sha256": image.get("prompt_sha256"),
            "request_sha256": image.get("request_sha256"), "attempt": image.get("attempt"),
            "ledger_id": match[-1].get("id"), "source_image": f"{stage}/{native_rel}",
            "source_sha256": row["native"]["sha256"],
        }
        if job_input.get("resolution"):
            generation["resolution"] = job_input["resolution"]
        out_sections.append({
            "section_id": sid, "slice": name, "width": ow, "height": oh, "logo_expected": False,
            "generation": generation,
            "export": {"source_px": f"{nw}x{nh}", "scale_factor": row["scale_factor"], "upscaled": row["upscaled"],
                       "method": receipt["method"], "receipt": receipt_name, "receipt_sha256": receipt["receipt_sha256"],
                       "native_path": f"{stage}/{native_rel}", "native_sha256": row["native"]["sha256"],
                       "output_sha256": row["output"]["sha256"]},
            "text_qc": qc,
        })
    record = {"artifact": "wireframe", "stage": stage, "page_width": receipt["page_widths"][viewport]}
    if design_style in ("A", "B", "C"):
        record["design_style"] = design_style
    record.update(stitched_output="wireframe-full.png", pdf_output=PDF_OUTPUT, logo_waived=WIREFRAME_LOGO_WAIVED,
                  sections=out_sections)
    return record, evidence, problems


def run_wireframe(run_dir, stage, request_name="production-request.json", allow_text=(), ocr=None,
                  ocr_validate=True, overwrite=False, receipt_name="export-receipt.json",
                  allow_reason=None, allow_authority=None):
    """The wireframe stage's one record. Returns (ok, lines); on ok the record is in place, else none is."""
    run_dir = Path(run_dir)
    stage_dir = run_dir / stage
    lines = []
    allow_words = [w for w in allow_text if str(w).strip()]
    allow = None
    if allow_words:
        if not str(allow_reason or "").strip() or not str(allow_authority or "").strip():
            raise Refused("--allow-text needs both --allow-reason and --allow-authority: an override of the "
                          "text read-back is never recorded without the reason and who authorised it")
        allow = (allow_words, str(allow_reason).strip(), str(allow_authority).strip())
    elif str(allow_reason or "").strip() or str(allow_authority or "").strip():
        raise Refused("--allow-reason and --allow-authority belong to --allow-text, and no --allow-text was given")
    board = _board()
    ocr = ocr or board.ocr_text
    request = read_json(run_dir / request_name, "the production request")
    executor = read_json(stage_dir / "stage-executor-record.json", "the stage executor record")
    ledger = read_json(run_dir / "image-spend-ledger.json", "the image spend ledger")
    bad = exporter.verify_receipt(stage_dir / receipt_name, stage_dir)
    if bad:
        raise Refused("the export receipt does not verify: " + "; ".join(bad))
    receipt = read_json(stage_dir / receipt_name, "the export receipt")
    target = stage_dir / "production-record.json"
    if target.exists() and not overwrite:
        raise Refused(f"{target} already exists; --overwrite replaces it")
    design_style = None
    try:
        design_style = read_json(run_dir / "intake.json", "intake.json").get("design_style")
    except Refused:
        pass
    brand = request.get("design_board") or {}
    chrome = " ".join([str(brand.get("brand_name") or "")] + [str(t) for t in brand.get("footer_taglines") or []]
                      + list(allow_words))
    record, evidence, problems = build_wireframe_record(run_dir, stage, request, executor, ledger, receipt,
                                                        receipt_name, ocr, board, chrome, design_style, allow)
    ev_path = stage_dir / "text-qc-readback.json"
    ev_path.write_text(json.dumps({"stage": stage, "method": QC_METHOD, "sections": evidence}, indent=2) + "\n",
                       encoding="utf-8")
    lines.append(f"read-back evidence: {ev_path}")
    cand = target.with_name(".production-record.candidate.json")
    cand.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    failed = bool(problems)
    lines.extend(f"FAIL text QC: {p}" for p in problems)
    rc, out = validate_candidate(cand, ocr_validate, request.get("model"))
    lines.append(f"validate_production_record.py {stage}: rc {rc}")
    if rc != 0:
        failed = True
        lines.extend("  " + ln for ln in out.splitlines())
    if failed:
        cand.unlink(missing_ok=True)
        lines.append("FAIL: no production record was left in place; fix the sections named above and run again")
        return False, lines
    os.replace(cand, target)
    lines.append(f"PASS: wrote {target} ({len(record['sections'])} sections)")
    return True, lines


def run(run_dir, stage="final-mockups", request_name="production-request-final-mockups.json",
        viewports=("desktop", "mobile"), allow_text=(), ocr=None, ocr_validate=True, ocr_mobile=False,
        overwrite=False, receipt_name="export-receipt.json", allow_reason=None, allow_authority=None):
    """Returns (ok, lines). On ok both records are in place; otherwise none is."""
    if stage in WIREFRAME_VIEWPORT:  # SWB-290: the flat wireframe stages have their own single record
        return run_wireframe(run_dir, stage, f"production-request-{stage}.json" if request_name == DEFAULT_FM_REQUEST
                             else request_name, allow_text, ocr, ocr_validate, overwrite, receipt_name,
                             allow_reason, allow_authority)
    run_dir = Path(run_dir)
    stage_dir = run_dir / stage
    lines = []
    allow_words = [w for w in allow_text if str(w).strip()]
    allow = None
    if allow_words:
        if not str(allow_reason or "").strip() or not str(allow_authority or "").strip():
            raise Refused("--allow-text needs both --allow-reason and --allow-authority: an override of the "
                          "text read-back is never recorded without the reason and who authorised it")
        allow = (allow_words, str(allow_reason).strip(), str(allow_authority).strip())
    elif str(allow_reason or "").strip() or str(allow_authority or "").strip():
        raise Refused("--allow-reason and --allow-authority belong to --allow-text, and no --allow-text was given")
    board = _board()
    ocr = ocr or board.ocr_text
    request = read_json(run_dir / request_name, "the production request")
    executor = read_json(stage_dir / "stage-executor-record.json", "the stage executor record")
    ledger = read_json(run_dir / "image-spend-ledger.json", "the image spend ledger")
    bad = exporter.verify_receipt(stage_dir / receipt_name, stage_dir)
    if bad:
        raise Refused("the export receipt does not verify: " + "; ".join(bad))
    receipt = read_json(stage_dir / receipt_name, "the export receipt")
    for vp in viewports:
        if vp not in VIEWPORT or vp not in receipt.get("page_widths", {}):
            raise Refused(f"the export receipt does not cover viewport {vp!r}")
    targets = {vp: (stage_dir / "production-record.json" if vp == "desktop"
                    else stage_dir / vp / "production-record.json") for vp in viewports}
    if not overwrite:
        for vp, path in targets.items():
            if path.exists():
                raise Refused(f"{path} already exists; --overwrite replaces it")
    design_style = None
    try:
        design_style = read_json(run_dir / "intake.json", "intake.json").get("design_style")
    except Refused:
        pass
    brand = request.get("design_board") or {}
    chrome = " ".join([str(brand.get("brand_name") or "")] + [str(t) for t in brand.get("footer_taglines") or []]
                      + list(allow_text))
    candidates, all_problems = {}, []
    for vp in viewports:
        record, evidence, problems = build_record(run_dir, stage, vp, request, executor, ledger, receipt,
                                                  receipt_name, ocr, board, chrome, design_style,
                                                  allow)
        ev_path = stage_dir / f"text-qc-readback-{vp}.json"
        ev_path.write_text(json.dumps({"viewport": vp, "method": QC_METHOD, "sections": evidence}, indent=2) + "\n",
                           encoding="utf-8")
        lines.append(f"read-back evidence: {ev_path}")
        all_problems.extend(problems)
        cand = targets[vp].with_name(".production-record.candidate.json")
        cand.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        candidates[vp] = (cand, record)
    failed = bool(all_problems)
    lines.extend(f"FAIL text QC: {p}" for p in all_problems)
    model = request.get("model")
    for vp, (cand, record) in candidates.items():
        rc, out = validate_candidate(cand, ocr_validate and (vp == "desktop" or ocr_mobile), model)
        lines.append(f"validate_production_record.py {vp}: rc {rc}")
        if rc != 0:
            failed = True
            lines.extend("  " + ln for ln in out.splitlines())
    if failed:
        for cand, _ in candidates.values():
            cand.unlink(missing_ok=True)
        lines.append("FAIL: no production record was left in place; fix the sections named above and run again")
        return False, lines
    for vp, (cand, record) in candidates.items():
        os.replace(cand, targets[vp])
        lines.append(f"PASS: wrote {targets[vp]} ({len(record['sections'])} sections)")
    return True, lines


def main(argv=None, ocr=None):
    ap = argparse.ArgumentParser(description="Author final-mockups production records from tool evidence only.")
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--stage", default="final-mockups")
    ap.add_argument("--request", default=DEFAULT_FM_REQUEST,
                    help="the production request (a wireframe stage reads production-request-<stage>.json unless this names another)")
    ap.add_argument("--viewports", default="desktop,mobile")
    ap.add_argument("--allow-text", action="append", default=[],
                    help="extra brand or chrome words the images may carry besides the section copy")
    ap.add_argument("--allow-reason", default=None,
                    help="why the --allow-text words are allowed (required with --allow-text); recorded in text_qc")
    ap.add_argument("--allow-authority", default=None,
                    help="who authorised the --allow-text words (required with --allow-text); recorded in text_qc")
    ap.add_argument("--no-ocr-validate", action="store_true",
                    help="skip --ocr in the validator run (the stage gate still runs it)")
    ap.add_argument("--ocr-mobile", action="store_true", help="also run the validator's --ocr on the mobile record")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args(argv)
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("FAIL: Pillow is required. Install the Python package 'Pillow' in this runtime.")
        return 2
    viewports = tuple(v.strip() for v in args.viewports.split(",") if v.strip())
    try:
        ok, lines = run(args.run_dir, args.stage, args.request, viewports, args.allow_text, ocr,
                        not args.no_ocr_validate, args.ocr_mobile, args.overwrite,
                        allow_reason=args.allow_reason, allow_authority=args.allow_authority)
    except Refused as exc:
        print(f"FAIL: refused: {exc}")
        return 1
    except Exception as exc:  # the OCR reader missing or crashed is an unreadable check, not a pass
        print(f"FAIL: the text read-back could not run: {type(exc).__name__}: {exc}")
        return 2
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
