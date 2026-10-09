#!/usr/bin/env python3
"""script_pdf: DEL-03 -- the approved script delivered as a client-facing PDF.

The script already exists twice before this module runs: as the message
`script_approval.render_script` sent for approval, and as the run's
`creative/script.json`. This turns that SAME approved content into the printed
page that lands in the delivery folder. It never rewrites a word and never
invents a section; if the approval record does not cover the lyrics on disk,
the page is refused instead of printed from the wrong revision.

Layout house style matches `references/CLIENT-GUIDE.md` (bright page, warm
accent, ink body); the drawing is `delivery_docs/pdf_writer.py` -- standard
library only, base-14 fonts, no third-party package, no font file.

Content rules that fail closed before a byte is written, because these are the
ones that make a client-facing PDF unshippable:

  * no money figure (currency symbol or currency code next to digits);
  * no income or earnings promise;
  * no model, tool or platform name;
  * a section label (THE STORY, THE SONG LYRICS, TITLE, APPROVED FOR
    PRODUCTION, and a bracketed song tag like [Verse]) is never treated as
    song copy when those rules look for offenders;
  * the printed copy must carry the approval's own lyrics hash, so a stale
    revision can never be shipped as the approved one;
  * nothing renders below `pdf_writer.MIN_PT` -- `Layout.para` raises.

Files written into the delivery folder, merged (never clobbered) alongside the
other deliverables:
  * `03 - SCRIPT.pdf`
  * `delivery-receipt.json` gains a `script_pdf` entry with the sha256
  * `README.md` gains the script block between its own markers

Run: python3 script_pdf/test_script_pdf.py
"""
from __future__ import annotations

import json
import os
import re
import sys

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

import script_approval as SA                      # noqa: E402
import delivery_docs.pdf_writer as PW              # noqa: E402
from delivery_variants.manifests import sha256_file  # noqa: E402

TOOL_NAME = "script_pdf"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0.0"

PDF_PREFIX = "03"
PDF_LABEL = "SCRIPT"
PDF_NAME = "%s - %s.pdf" % (PDF_PREFIX, PDF_LABEL)

RECEIPT_NAME = "delivery-receipt.json"
README_NAME = "README.md"
README_BEGIN = "<!-- script-pdf:begin -->"
README_END = "<!-- script-pdf:end -->"

APPROVAL_PATH = os.path.join("creative", "script-approval.json")
SCRIPT_PATH = os.path.join("creative", "script.json")

PASS, FAIL = "PASS", "FAIL"
CHECK_NAME = "script_pdf"

REASON_NOT_APPROVED = "SCRIPT_PDF_NOT_APPROVED"
REASON_STALE = "SCRIPT_PDF_STALE_REVISION"
REASON_NO_SOURCE = "SCRIPT_PDF_MISSING_SOURCE"
REASON_PRICE = "SCRIPT_PDF_PRICE_IN_COPY"
REASON_INCOME = "SCRIPT_PDF_INCOME_PROMISE"
REASON_TOOL = "SCRIPT_PDF_TOOL_NAME_IN_COPY"
REASON_LAYOUT = "SCRIPT_PDF_BAD_LAYOUT"

DETAILS = {
    REASON_NOT_APPROVED: "the run's script approval record is missing or is "
                         "not approved, so there is no approved script to print",
    REASON_STALE: "the approved record covers different lyrics than "
                  "creative/script.json holds; this is not the approved revision",
    REASON_NO_SOURCE: "creative/script.json is missing, unreadable, or has "
                      "no song sections",
    REASON_PRICE: "the copy carries a money figure, which never goes on a "
                  "client-facing page",
    REASON_INCOME: "the copy carries an income or earnings promise, which "
                   "never goes on a client-facing page",
    REASON_TOOL: "the copy names a model, tool or platform, which never goes "
                 "on a client-facing page",
    REASON_LAYOUT: "the page could not be laid out inside the type floor",
}

# --- content rules -------------------------------------------------------

# A section label or song tag is structure, never song copy: it is exempt from
# the content rules below (and still printed exactly as the approval showed it).
SECTION_LABELS = frozenset({
    "THE STORY", "THE SONG LYRICS", "THE SONG TITLE", "TITLE", "SCRIPT",
    "APPROVED FOR PRODUCTION",
})

_MONEY = re.compile(
    r"(?:[$£€¥]\s?\d)"
    r"|(?:\b\d[\d,.]*\s?(?:USD|EUR|GBP|CAD|AUD|JPY|dollars?|euros?|pounds?)\b)",
    re.IGNORECASE)
_INCOME = re.compile(
    r"\b(?:"
    r"guaranteed\s+income|income\s+guarantee|passive\s+income|"
    r"earn\s+up\s+to|make\s+up\s+to|earn\s+money|make\s+money\s+fast|"
    r"get\s+rich|six[-\s]figures?|seven[-\s]figures?|\d[-\s]figures?|"
    r"guaranteed\s+returns?|earnings?\s+guarantee|residual\s+income|"
    r"monthly\s+income|weekly\s+income|financial\s+freedom"
    r")\b"
    r"|[$£€¥]\s?\d[\d,.]*\s*(?:a|per)\s+(?:day|week|month|year)\b",
    re.IGNORECASE)
_TOOLS = re.compile(
    r"\b(?:"
    r"python|ffmpeg|ffprobe|sqlite|sqlite3|pytest|git|github|docker|node|"
    r"npm|telegram|n8n|reportlab|pypdf|weasyprint|openai|anthropic|"
    r"deepseek|qwen|llama|gpt|claude|gemini|ollama|openrouter|suno|kie|"
    r"kling|seedance|minimax|veo|runway|luma|flux|whisper|mediapipe|"
    r"opencv|numpy|supabase|vercel|openclaw"
    r")\b",
    re.IGNORECASE)


def _is_label(text):
    t = str(text).strip().strip("[]").strip()
    return t.upper() in SECTION_LABELS or (
        str(text).strip().startswith("[") and str(text).strip().endswith("]"))


def copy_violation(text):
    """None when `text` may be printed; else (reason_code, detail)."""
    for probe in str(text).split("\n"):
        if _is_label(probe):
            continue
        if _MONEY.search(probe):
            return (REASON_PRICE, "money figure in the copy: %s" % probe.strip()[:80])
        if _INCOME.search(probe):
            return (REASON_INCOME, "income promise in the copy: %s" % probe.strip()[:80])
        if _TOOLS.search(probe):
            return (REASON_TOOL, "tool or model name in the copy: %s" % probe.strip()[:80])
    return None


def _fail(code, detail=None):
    return {"ok": False, "reason_code": code,
            "detail": detail or DETAILS.get(code, code), "file": None,
            "name": None}


# --- source --------------------------------------------------------------

def load_approved_source(run_dir, approval=None, doc=None):
    """The approved script, or a refusal.

    Returns {"ok": True, "title", "story", "sheet", "lyrics", "sha"} or
    {"ok": False, "reason_code", "detail"}.
    """
    record = approval
    if record is None:
        try:
            with open(os.path.join(run_dir, APPROVAL_PATH), encoding="utf-8") as f:
                record = json.load(f)
        except (OSError, ValueError):
            record = None
    if not isinstance(record, dict) or not record.get("required") \
            or record.get("status") != "approved":
        return _fail(REASON_NOT_APPROVED)

    payload = doc
    if payload is None:
        try:
            with open(os.path.join(run_dir, SCRIPT_PATH), encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, ValueError):
            payload = None
    if not isinstance(payload, dict) or not payload.get("sheet"):
        return _fail(REASON_NO_SOURCE)

    sheet = payload["sheet"]
    story = payload.get("story") or []
    # A run directory is untrusted input. A section that is not an object, a
    # line list that is a bare string, or an act that is not a pair must
    # refuse as "no source" -- never raise out of this function and never be
    # walked character by character.
    if not isinstance(sheet, list) or not isinstance(story, list):
        return _fail(REASON_NO_SOURCE)
    if payload.get("title") is not None and not isinstance(payload.get("title"), str):
        return _fail(REASON_NO_SOURCE)
    for sec in sheet:
        if not isinstance(sec, dict) or not isinstance(sec.get("lines") or [], list):
            return _fail(REASON_NO_SOURCE)
    for act in story:
        if not (isinstance(act, (list, tuple)) and len(act) == 2
                and isinstance(act[1] or [], list)):
            return _fail(REASON_NO_SOURCE)
    title = str(payload.get("title") or "Your song")
    try:
        lyrics = payload.get("lyrics") or "\n".join(
            line for sec in sheet for line in (sec.get("lines") or []))
        sha = SA.lyrics_sha(lyrics)
        approved_sha = record.get("lyrics_sha")
        lines = [title]
        for act, act_lines in story:
            lines.append(str(act))
            lines.extend(str(x) for x in (act_lines or []))
        for sec in sheet:
            lines.append(str(sec.get("tag") or ""))
            lines.extend(str(x) for x in (sec.get("lines") or []))
        hit = copy_violation("\n".join(lines))
    except (AttributeError, TypeError, ValueError):
        return _fail(REASON_NO_SOURCE)

    if approved_sha is not None and approved_sha != sha:
        # Any mismatch -- including a hash the record cannot even render as
        # one -- means this is not the revision that was approved.
        return _fail(REASON_STALE,
                     "approval covers a different revision of the lyrics "
                     "(approved %s, on disk %s)"
                     % (str(approved_sha)[:12], sha[:12]))
    if hit:
        return _fail(hit[0], hit[1])

    return {"ok": True, "title": title,
            "story": [tuple(a) for a in story], "sheet": sheet,
            "lyrics": lyrics, "sha": sha}


# --- layout --------------------------------------------------------------

def _footer(layout):
    def stamp(page, total):
        y = PW.MARGIN_B - 34.0
        if y < 0:
            return []
        ops = [PW.text_op(PW.MARGIN_L, y, PW.fit(
            layout.title or PDF_LABEL, "F1", PW.MIN_PT, PW.PAGE_W - 240),
            "F1", PW.MIN_PT, PW.GREY)]
        label = "Page %d of %d" % (page, total)
        x = PW.PAGE_W - PW.MARGIN_R - PW.text_width(label, "F1", PW.MIN_PT)
        ops.append(PW.text_op(x, y, label, "F1", PW.MIN_PT, PW.GREY))
        ops.append(PW.rect_op(PW.MARGIN_L, y + 16,
                               PW.PAGE_W - PW.MARGIN_L - PW.MARGIN_R,
                               1.0, PW.HAIR))
        return ops
    return stamp


def _keep_with_first(layout, heading, lines):
    """Reserve the heading and the first thing under it, so a section head
    never lands alone at the foot of a page."""
    lines = list(lines or [])
    heading_lead = round(13.0 * 1.45)          # Layout.para's default leading
    if not lines:
        layout.need(8 + heading_lead)
        return
    layout.need(8 + heading_lead + 19.0)


def render_document(source):
    """Approved script -> a `Layout` laid out to the house style."""
    layout = PW.Layout()
    layout.title = source["title"]
    layout.on_footer(_footer(layout))

    layout.para(PDF_LABEL, font="F2", size=PW.MIN_PT, color=PW.ACCENT)
    layout.space(6)
    layout.para(source["title"], font="F2", size=26.0, color=PW.INK,
                leading=32.0, space_before=0)
    layout.space(10)
    layout.rule(3.0, PW.BAR)
    layout.space(12)
    layout.para("Approved for production", font="F2", size=13.0, color=PW.INK)
    layout.space(4)
    layout.para("This is the exact script the client approved: the story and "
                "every lyric below. Nothing was added, changed or left out "
                "after approval.", size=13.0, color=PW.GREY, leading=19.0)
    layout.space(20)

    layout.need(23 + 10 + 8 + 19 + 19)        # head + gap + first section
    layout.para("THE STORY", font="F2", size=16.0, color=PW.ACCENT,
                space_before=0)
    layout.space(10)
    if source["story"]:
        for act, lines in source["story"]:
            _keep_with_first(layout, act, lines)
            layout.para(str(act), font="F2", size=13.0, color=PW.INK,
                        space_before=8)
            layout.space(4)
            for line in lines or []:
                layout.para(str(line), size=13.0, leading=19.0, space_before=2)
            layout.space(10)
    else:
        layout.para("(no story sections)", size=13.0, color=PW.GREY)
    layout.space(16)

    layout.need(23 + 10 + 8 + 19 + 19)        # head + gap + first tag + line
    layout.para("THE SONG LYRICS", font="F2", size=16.0, color=PW.ACCENT)
    layout.space(10)
    for sec in source["sheet"]:
        tag = str(sec.get("tag") or "").strip()
        if tag and tag.lower() != "end":
            _keep_with_first(layout, tag, sec.get("lines") or [])
            layout.para("[%s]" % tag.strip("[] "), font="F2", size=13.0,
                        color=PW.ACCENT, space_before=8)
            layout.space(3)
        for line in sec.get("lines") or []:
            layout.para(str(line), size=13.0, leading=19.0, space_before=2)
        layout.space(8)
    return layout


# --- delivery folder -----------------------------------------------------

def _update_receipt(delivery_dir, entry):
    path = os.path.join(delivery_dir, RECEIPT_NAME)
    receipt = {}
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                receipt = json.load(f)
        except (OSError, ValueError):
            receipt = {}
    if not isinstance(receipt, dict):
        receipt = {}
    receipt["script_pdf"] = entry
    with open(path, "w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2, sort_keys=True)
        f.write("\n")
    return path


def _update_readme(delivery_dir, name, pages):
    path = os.path.join(delivery_dir, README_NAME)
    block = "\n".join([
        README_BEGIN,
        "## The script (printed)", "",
        "- `%s` - the approved script as a printed page: the story and every "
        "lyric, %d page%s, set at %g point and above."
        % (name, pages, "" if pages == 1 else "s", PW.MIN_PT),
        "", README_END, ""])
    text = "# Delivery\n\n"
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            text = f.read()
    if README_BEGIN in text and README_END in text:
        start = text.index(README_BEGIN)
        end = text.index(README_END) + len(README_END)
        text = text[:start] + block.rstrip("\n") + text[end:]
    else:
        text = text.rstrip("\n") + "\n\n" + block
    with open(path, "w", encoding="utf-8") as f:
        f.write(text if text.endswith("\n") else text + "\n")
    return path


def render(run_dir, delivery_dir, *, approval=None, doc=None,
           number=PDF_PREFIX, label=PDF_LABEL):
    """Write the approved script PDF into `delivery_dir`. Fail-closed dict."""
    source = load_approved_source(run_dir, approval=approval, doc=doc)
    if not source.get("ok"):
        return source
    try:
        layout = render_document(source)
        data = layout.to_bytes()
    except (ValueError, OSError) as exc:
        return _fail(REASON_LAYOUT, "%s: %s" % (type(exc).__name__, exc))
    if not data.startswith(b"%PDF-") or len(data) < 512:
        return _fail(REASON_LAYOUT, "the writer did not produce a PDF")

    name = "%s - %s.pdf" % (number, label)
    os.makedirs(delivery_dir, exist_ok=True)
    path = os.path.join(delivery_dir, name)
    with open(path, "wb") as f:
        f.write(data)
    digest = sha256_file(path)
    pages = len(layout.pages)
    _update_receipt(delivery_dir, {
        "file": name, "sha256": digest, "pages": pages,
        "title": source["title"], "lyrics_sha": source["sha"],
        "schema_version": SCHEMA_VERSION})
    _update_readme(delivery_dir, name, pages)
    return {"ok": True, "reason_code": None,
            "detail": "wrote %s (%d page%s)" % (name, pages,
                                                "" if pages == 1 else "s"),
            "file": path, "name": name, "pages": pages,
            "sha256": digest, "title": source["title"]}


# --- QC ------------------------------------------------------------------

def check_pdf(path):
    """(PASS|FAIL, detail) for one script PDF: exists, is a PDF, type floor."""
    try:
        if not os.path.isfile(path):
            return (FAIL, "%s missing" % os.path.basename(path))
        with open(path, "rb") as f:
            body = f.read()
    except OSError as exc:
        return (FAIL, "%s unreadable: %s" % (os.path.basename(path), exc))
    if len(body) < 512:
        return (FAIL, "%s is %d bytes, too small to be a document"
                % (os.path.basename(path), len(body)))
    if not body.startswith(b"%PDF-"):
        return (FAIL, "%s is not a PDF" % os.path.basename(path))
    if b"%%EOF" not in body[-4096:]:
        return (FAIL, "%s has no PDF end marker" % os.path.basename(path))
    # Type floor: every Tf operator in the document carries its own size.
    sizes = [float(s) for s in re.findall(rb"/F\d\s+([0-9.]+)\s+Tf", body)]
    if not sizes:
        return (FAIL, "%s carries no text" % os.path.basename(path))
    small = sorted({round(s, 2) for s in sizes if s < PW.MIN_PT})
    if small:
        return (FAIL, "%s sets type below %g pt: %s"
                % (os.path.basename(path), PW.MIN_PT, small))
    pages = body.count(b"/Type /Page ")   # not /Type /Pages (the tree node)
    return (PASS, "%s is a valid PDF, %d page%s, smallest type %g pt"
            % (os.path.basename(path), pages, "" if pages == 1 else "s",
               min(sizes)))


def check_delivery(delivery_dir):
    """(PASS|FAIL, detail): the numbered script PDF is present and clean."""
    path = os.path.join(delivery_dir, PDF_NAME)
    verdict, detail = check_pdf(path)
    if verdict != PASS:
        return (FAIL, detail)
    receipt_path = os.path.join(delivery_dir, RECEIPT_NAME)
    try:
        with open(receipt_path, encoding="utf-8") as f:
            receipt = json.load(f)
    except (OSError, ValueError):
        return (FAIL, "%s missing or unreadable; cannot bind the script PDF"
                % RECEIPT_NAME)
    entry = receipt.get("script_pdf") or {}
    if entry.get("file") != PDF_NAME:
        return (FAIL, "%s does not list %s" % (RECEIPT_NAME, PDF_NAME))
    if entry.get("sha256") != sha256_file(path):
        return (FAIL, "the receipt hash for %s does not match the file"
                % PDF_NAME)
    readme = ""
    readme_path = os.path.join(delivery_dir, README_NAME)
    if os.path.isfile(readme_path):
        with open(readme_path, encoding="utf-8") as f:
            readme = f.read()
    if PDF_NAME not in readme:
        return (FAIL, "%s not listed in %s" % (PDF_NAME, README_NAME))
    return (PASS, "script PDF present, bound in the receipt and listed in "
                  "the README; " + detail)


def _cli(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "run" and len(args) >= 5 \
            and args[1] in ("--run-dir", "-r") and args[3] in ("--delivery-dir", "-d"):
        result = render(args[2], args[4])
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 5
    if args and args[0] == "check" and len(args) >= 2:
        verdict, detail = check_delivery(args[1])
        print(json.dumps({"check": CHECK_NAME, "verdict": verdict,
                          "detail": detail}, sort_keys=True))
        return 0 if verdict == PASS else 5
    print("usage: script_pdf.py run --run-dir <run> --delivery-dir <folder>")
    print("       script_pdf.py check <delivery_dir>")
    return 2


if __name__ == "__main__":
    sys.exit(_cli())