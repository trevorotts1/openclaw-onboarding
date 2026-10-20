#!/usr/bin/env python3
"""Validate a Skill 71 per-section production record (Update Plan Item 13).

Usage:
  python3 scripts/validate_production_record.py <production-record.json>

The production method for wireframe and mockup section images is pinned
(see references/artifact-contracts.md, "Production method and per-section
build record", and the SOP wireframe and mockup stages): every section is
generated per section via the KIE.ai GPT-image route, with the exact model
resolved from the model registry at build time (Skill 66 resolves it; the
record carries the resolved id and its source, never a name typed from
memory), the approved wireframe section as the mockup section's layout
reference, and the page visual bible as the style input; each section is
generated at its native aspect; a deterministic stitcher assembles the
full-page PNG and the PDF combiner the combined PDF; and text-fidelity QC
reads every section at native resolution BEFORE stitching, so any section
with a garbled word fails and is regenerated before stitching, never
accepted into the combined artifact.

This validator is the deterministic floor of that method. Per section it
checks:

  1. The generation inputs are recorded: the KIE GPT-image route, the
     build-time-resolved model id and its registry source, the layout
     reference, and the style input (the visual bible). On a mockup the
     layout reference must resolve to an existing file -- the approved
     wireframe section slice -- against the record's stage folder or the
     run folder above it.
  2. The native-aspect output: the recorded width/height and native_aspect
     match the slice file's actual pixel dimensions.
  3. The text-QC leg record exists, states the read happened at native
     resolution, and its verdict is honest: the garbled-word set is
     recomputed here from the recorded expected text (the section's real
     copy) and the recorded read-back text (the words read off the
     generated section at native resolution). A read-back token that does
     not appear in the expected text is a garble. Any garble FAILs the
     section by name, whatever the recorded verdict claims; a recorded
     garbled-word list that differs from the recomputed set also FAILs.

  4. Graphics hooks (SOP-GIP-02), both additive:
     * TEXT READ-BACK (AF-G1), only with --ocr: each section image is read by
       the Design Board's own machine reader (design_board.ocr_text), and the
       section FAILs when the recorded read-back is not supported by the pixels
       or when the image does not show its expected copy. A recorded read-back
       that the image does not contain is a self-typed read, not a QC read.
     * LOGO ACCURACY (AF-G2): a section that declares logo_expected true must
       carry a logo_check record naming the logo reference, the method and a
       verdict; a missing record or any verdict other than "pass" FAILs it.

Usage: validate_production_record.py <production-record.json> [--ocr]

Exit codes: 0 pass, 1 one named FAIL line per failure, 2 unreadable input.
"""
import json
import re
import sys
from pathlib import Path

ROUTE = "kie-gpt-image"
MODEL_SOURCES = {"latest-family", "explicit-request", "department-pin", "user-pin", "legacy-ratio-route"}
TOKEN_RE = re.compile(r"[a-z0-9]+(?:['-][a-z0-9]+)*")


def tokens(text):
    return TOKEN_RE.findall(str(text).lower())


def garbled_words(expected_text, readback_text):
    """Read-back tokens that do not appear in the expected text, sorted."""
    expected = set(tokens(expected_text))
    return sorted({tok for tok in tokens(readback_text) if tok not in expected})


LOGO_VERDICTS = ("pass", "fail")


def logo_failures(label, section):
    """AF-G2: a section that expects the client's logo must carry a passing logo_check."""
    if section.get("logo_expected") is not True:
        return []
    check = section.get("logo_check")
    if not isinstance(check, dict):
        return [f"section {label}: AF-G2 logo_expected is true but there is no logo_check record "
                f"(compare the section against the client's logo reference)"]
    out = []
    for key in ("logo_ref", "method"):
        if not isinstance(check.get(key), str) or not check[key].strip():
            out.append(f"section {label}: AF-G2 logo_check.{key} is required")
    verdict = check.get("verdict")
    if verdict not in LOGO_VERDICTS:
        out.append(f"section {label}: AF-G2 logo_check.verdict must be one of {list(LOGO_VERDICTS)}")
    elif verdict != "pass":
        out.append(f"section {label}: AF-G2 the logo is mutated, recolored or invented "
                   f"(logo_check.verdict is {verdict!r}); the section FAILS and is regenerated")
    return out


def ocr_failures(label, slice_path, qc, ocr, board):
    """AF-G1: the image itself must support the recorded read-back and show the expected copy."""
    seen = board.tokens(ocr(slice_path))
    out = []
    readback = qc.get("readback_text")
    if isinstance(readback, str) and readback.strip():
        share = board.support(board.tokens(readback), seen)
        if share < board.OCR_FLOOR:
            out.append(f"section {label}: AF-G1 the recorded read-back is not supported by the image "
                       f"({share:.0%} of its words are on the pixels, floor {board.OCR_FLOOR:.0%}); "
                       f"a read-back must come from the image, not be typed")
    expected = qc.get("expected_text")
    if isinstance(expected, str) and expected.strip():
        share = board.support(board.tokens(expected), seen)
        if share < board.OCR_FLOOR:
            out.append(f"section {label}: AF-G1 the section image does not show its copy "
                       f"({share:.0%} of the expected words are on the pixels, floor "
                       f"{board.OCR_FLOOR:.0%}); regenerate before stitching")
    return out


def _design_board():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import design_board
    finally:
        sys.path.pop(0)
    return design_board


def check_record(data, base_dir=None, ocr=None):
    """Return a list of named failure strings; empty means the record passes.

    base_dir, when given, is the folder slice paths resolve against; slice
    existence and pixel dimensions are checked only then. ocr, when given, is a
    callable(path) -> text (design_board.ocr_text in production); with a base_dir
    it adds the AF-G1 text read-back leg for every slice on disk.
    """
    failures = []
    if not isinstance(data, dict):
        return ["production record is not a JSON object"]
    if data.get("artifact") not in ("wireframe", "mockup"):
        failures.append("artifact must be 'wireframe' or 'mockup'")
    # The client's design style (A Block, B Circle, C Hybrid) is recorded at the top of
    # the record, and must match intake.json's choice when the run folder carries one.
    style = data.get("design_style")
    if style is not None and style not in ("A", "B", "C"):
        failures.append(f"design_style must be A, B or C, got {style!r}")
    elif style is not None and base_dir is not None:
        for folder in (Path(base_dir), Path(base_dir).parent):
            try:
                chosen = json.loads((folder / "intake.json").read_text(encoding="utf-8")).get("design_style")
            except (OSError, ValueError, AttributeError):
                continue
            if chosen and chosen != style:
                failures.append(f"design_style {style!r} differs from intake.json's {chosen!r}")
            break
    sections = data.get("sections")
    if not isinstance(sections, list) or not sections:
        failures.append("sections must be a non-empty ordered array")
        return failures
    seen = set()
    for i, section in enumerate(sections, start=1):
        if not isinstance(section, dict):
            failures.append(f"sections[{i}] is not an object")
            continue
        sid = section.get("section_id")
        label = sid if isinstance(sid, str) and sid else f"sections[{i}]"
        if not isinstance(sid, str) or not sid:
            failures.append(f"sections[{i}]: section_id is required")
        elif sid in seen:
            failures.append(f"section {sid}: duplicated section_id")
        else:
            seen.add(sid)

        slice_name = section.get("slice")
        if not isinstance(slice_name, str) or not slice_name:
            failures.append(f"section {label}: slice file is required")
            slice_name = None
        width, height = section.get("width"), section.get("height")
        dims_ok = isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0
        if not dims_ok:
            failures.append(f"section {label}: width and height must be positive integers (the native-aspect output)")

        gen = section.get("generation")
        if not isinstance(gen, dict):
            failures.append(f"section {label}: generation inputs record is required")
            gen = {}
        if gen.get("route") != ROUTE:
            failures.append(f"section {label}: generation.route must be '{ROUTE}' (the KIE.ai GPT-image route)")
        if not isinstance(gen.get("model_id"), str) or not gen.get("model_id"):
            failures.append(f"section {label}: generation.model_id is required (the model resolved from the registry at build time)")
        if gen.get("model_source") not in MODEL_SOURCES:
            failures.append(f"section {label}: generation.model_source must be one of {sorted(MODEL_SOURCES)}")
        if not isinstance(gen.get("layout_reference"), str) or not gen.get("layout_reference"):
            failures.append(f"section {label}: generation.layout_reference is required (the approved wireframe section for a mockup section; the section plan for a wireframe section)")
        layout_reference = gen.get("layout_reference")
        if (base_dir is not None and data.get("artifact") == "mockup"
                and isinstance(layout_reference, str) and layout_reference.strip()):
            ref = Path(layout_reference)
            candidates = ([ref] if ref.is_absolute()
                          else [Path(base_dir) / ref, Path(base_dir).parent / ref])
            if not any(candidate.is_file() for candidate in candidates):
                failures.append(
                    f"section {label}: generation.layout_reference does not resolve to an existing file: "
                    f"{layout_reference} (a mockup section's approved wireframe slice must be on disk, "
                    f"relative to the stage folder or the run folder above it)")
        if not isinstance(gen.get("style_input"), str) or not gen.get("style_input"):
            failures.append(f"section {label}: generation.style_input is required (the page visual bible)")
        if dims_ok and gen.get("native_aspect") != f"{width}x{height}":
            failures.append(f"section {label}: generation.native_aspect must equal the recorded output size {width}x{height}")

        if base_dir is not None and slice_name:
            slice_path = Path(base_dir) / slice_name
            if not slice_path.exists():
                failures.append(f"section {label}: slice file is not on disk: {slice_name}")
            elif dims_ok:
                try:
                    from PIL import Image
                    with Image.open(slice_path) as im:
                        actual = im.size
                except Exception as exc:
                    failures.append(f"section {label}: slice is not a readable image: {slice_name} ({exc})")
                    actual = None
                if actual is not None and actual != (width, height):
                    failures.append(
                        f"section {label}: slice is {actual[0]}x{actual[1]} on disk but the record claims "
                        f"{width}x{height} (native-aspect output must match the filed bytes)")

        failures.extend(logo_failures(label, section))

        qc = section.get("text_qc")
        if (ocr is not None and base_dir is not None and slice_name
                and isinstance(qc, dict) and (Path(base_dir) / slice_name).is_file()):
            failures.extend(ocr_failures(label, Path(base_dir) / slice_name, qc, ocr, _design_board()))
        if not isinstance(qc, dict):
            failures.append(f"section {label}: text_qc record is required (the per-section text-QC leg runs before stitching)")
            continue
        if qc.get("checked_at_native_resolution") is not True:
            failures.append(f"section {label}: text_qc.checked_at_native_resolution must be true (the read happens at native resolution)")
        expected, readback = qc.get("expected_text"), qc.get("readback_text")
        if not isinstance(expected, str) or not expected.strip():
            failures.append(f"section {label}: text_qc.expected_text is required (the section's real copy)")
        if not isinstance(readback, str) or not readback.strip():
            failures.append(f"section {label}: text_qc.readback_text is required (the words read off the generated section)")
        attempts = qc.get("attempts")
        if not isinstance(attempts, int) or attempts < 1:
            failures.append(f"section {label}: text_qc.attempts must be an integer >= 1 (a regenerated section records its attempts)")
        if isinstance(expected, str) and isinstance(readback, str) and expected.strip() and readback.strip():
            recomputed = garbled_words(expected, readback)
            recorded = qc.get("garbled_words")
            if recorded != recomputed:
                failures.append(
                    f"section {label}: text_qc.garbled_words {recorded!r} does not match the recomputed "
                    f"garble set {recomputed!r}")
            if recomputed:
                failures.append(
                    f"section {label}: garbled word(s) in the generated section: {', '.join(recomputed)} "
                    f"(the section FAILS the text-QC leg and must be regenerated before stitching)")
            elif qc.get("verdict") != "pass":
                failures.append(f"section {label}: text_qc.verdict must be 'pass' when no garbled word is present")
            if recomputed and qc.get("verdict") == "pass":
                failures.append(f"section {label}: text_qc.verdict claims 'pass' but the section is garbled")
    return failures


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    use_ocr = "--ocr" in argv
    argv = [a for a in argv if a != "--ocr"]
    if len(argv) != 1:
        print("FAIL: usage: validate_production_record.py <production-record.json> [--ocr]")
        return 2
    path = Path(argv[0])
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"FAIL: could not read production record: {exc}")
        return 2
    ocr = None
    if use_ocr:
        try:
            ocr = _design_board().ocr_text
        except Exception as exc:
            print(f"FAIL: could not load the Design Board text reader: {exc}")
            return 2
    try:
        failures = check_record(data, base_dir=path.parent, ocr=ocr)
    except Exception as exc:  # the reader (tesseract) is missing or crashed: unreadable, not a pass
        print(f"FAIL: the text read-back could not run: {exc}")
        return 2
    if failures:
        print("FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1
    count = len(data.get("sections", []))
    print(f"PASS: production record for {data.get('artifact')} '{data.get('stage')}' "
          f"carries {count} section(s), each with its generation inputs, native-aspect "
          f"output, and a passing per-section text-QC record.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
