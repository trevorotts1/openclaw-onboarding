#!/usr/bin/env python3
"""
presenter_guide.py -- PRESENTER-GUIDE.pdf (speaker-facing outline).
Phase P8.2-GUIDE. Uses reportlab v4.4.10. Hard 12pt type floor.
[CLIENT TO SUPPLY] placeholders carried forward, never fabricated.
"""
import argparse, json, os, re, shutil, sys
from datetime import date
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate, Frame, HRFlowable, KeepTogether,
    PageTemplate, Paragraph, Spacer, PageBreak,
)

MIN_FONT_PT = 12.0
MIN_BYTES = 51200
MIN_BYTES_SAMPLE = 8192
SCRIPTS_DIR = Path(__file__).resolve().parent


# ----------------------------------------------------------------- helpers
def _hex(c):
    return colors.HexColor(c) if isinstance(c, str) else c

def _esc(text):
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def _load_json(path):
    try: return json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))
    except Exception: return None

def _sanitize_filename(name):
    return re.sub(r"[^a-zA-Z0-9 _\-]+", "_", name).strip() or "Webinar"

_BOUNDARY = r"(?=\n(?:PRESENTER\s+NOTE|PURPOSE|SECTION|LADDER|HOOK_REFRAIN|##\s+Slide|\Z))"
_HOOK_RE = re.compile(r"HOOK_REFRAIN:?\s*(.+?)" + _BOUNDARY, re.DOTALL | re.I)
_LADDER_RE = re.compile(r"LADDER:?\s*(.+?)" + _BOUNDARY, re.DOTALL | re.I)
_SECTION_RE = re.compile(r"SECTION:?\s*(.+?)" + _BOUNDARY, re.DOTALL | re.I)
_PURPOSE_RE = re.compile(r"PURPOSE:?\s*(.+?)" + _BOUNDARY, re.DOTALL | re.I)
_NOTE_RE = re.compile(r"PRESENTER\s+NOTE:?\s*(.+?)(?=\n(?:##\s+Slide|\Z))", re.DOTALL | re.I)
_SLIDE_SPLIT_RE = re.compile(r"(?m)^(?:#{1,3}\s+)?SLIDE\s+(\d+)\b", re.I)
_HEADLINE_RE = re.compile(r"(?m)^(?:\*\*(.+?)\*\*|Headline:?\s*(.+?)(?:\n|$))", re.I)
_SPEECH_SLIDE_RE = re.compile(r"##\s+Slide\s+(\d+)\s+--\s+(.+?)\s+\((\w+)\)")
_SPEECH_META_RE = re.compile(r">\s*STAGE:\s*(\w+)\s+KIND:\s*(\w+)")


# ----------------------------------------------------------- data loading
def _load_copy(run_dir):
    p = Path(run_dir) / "working" / "copy" / "slides_copy.md"
    try: return p.read_text(encoding="utf-8", errors="replace")
    except Exception: return ""

def _load_speech(run_dir):
    p = Path(run_dir) / "working" / "deliverables" / "PRESENTERS-SPEECH.md"
    try: return p.read_text(encoding="utf-8", errors="replace")
    except Exception: return ""

def _load_design(run_dir):
    data = _load_json(Path(run_dir) / "working" / "typography" / "design_system.json")
    return (data or {}).get("brand", {}) if isinstance(data, dict) else {}


# ------------------------------------------------------------- slide parse
def _parse_slides_copy(text):
    slides = []
    parts = _SLIDE_SPLIT_RE.split(text)
    i = 1
    while i + 1 < len(parts):
        try: no = int(parts[i])
        except (ValueError, TypeError): i += 2; continue
        block = parts[i + 1]
        note_m = _NOTE_RE.search(block)
        purpose_m = _PURPOSE_RE.search(block)
        section_m = _SECTION_RE.search(block)
        ladder_m = _LADDER_RE.search(block)
        hook_m = _HOOK_RE.search(block)
        hl_m = _HEADLINE_RE.search(block)
        headline = (hl_m.group(1) or hl_m.group(2) or "").strip() if hl_m else f"Slide {no}"
        slides.append({
            "no": no, "headline": headline,
            "presenter_note": note_m.group(1).strip() if note_m else "",
            "purpose": (purpose_m.group(1).strip()[:200] if purpose_m and purpose_m.group(1) else ""),
            "section": section_m.group(1).strip() if section_m else "",
            "ladder": ladder_m.group(1).strip() if ladder_m else "",
            "hook_refrain": bool(hook_m),
            "hook_text": hook_m.group(1).strip() if hook_m else "",
        })
        i += 2
    return sorted(slides, key=lambda s: s["no"])

def _parse_slides_speech(md_text):
    slides = []
    for m in _SPEECH_SLIDE_RE.finditer(md_text):
        no = int(m.group(1))
        headline = m.group(2).strip()
        stage = m.group(3)
        rest = md_text[m.end():]
        meta_m = _SPEECH_META_RE.search(rest[:300])
        kind = meta_m.group(2) if meta_m else "normal"
        ladder = kind if kind in {"drop", "final"} else ""
        hook = kind == "hook"
        slides.append({
            "no": no, "headline": headline, "presenter_note": "",
            "purpose": "", "section": stage, "ladder": ladder,
            "hook_refrain": hook, "hook_text": "",
        })
    return sorted(slides, key=lambda s: s["no"])


# ---------------------------------------------------------------- arc map
def _build_sections(arc_dict, slides):
    comps = (arc_dict or {}).get("components") or (arc_dict or {}).get("sections") or []
    if isinstance(comps, list) and comps:
        out = []
        for c in comps:
            if not isinstance(c, dict): continue
            name = c.get("name") or c.get("section_name") or c.get("label", "")
            first = c.get("first_slide") or c.get("slide_start")
            last = c.get("last_slide") or c.get("slide_end") or first
            job = c.get("job") or c.get("description") or c.get("purpose", "")
            if name and first is not None:
                out.append({"name": str(name), "first": int(first),
                             "last": int(last) if last is not None else int(first),
                             "job": str(job)})
        if out:
            return sorted(out, key=lambda s: s["first"])
    # fallback: per-slide SECTION tags
    order, rng = [], {}
    for s in slides:
        sec = s.get("section", "").strip()
        if not sec: continue
        if sec not in rng:
            rng[sec] = {"name": sec, "first": s["no"], "last": s["no"], "job": ""}
            order.append(sec)
        else:
            rng[sec]["last"] = max(rng[sec]["last"], s["no"])
            rng[sec]["first"] = min(rng[sec]["first"], s["no"])
    if rng: return [rng[k] for k in order]
    # last-chance: one flat section
    if slides:
        return [{"name": "PRESENTATION", "first": slides[0]["no"],
                  "last": slides[-1]["no"], "job": "Deliver the complete presentation"}]
    return []


# -------------------------------------------------------------- PDF engine
class PresenterGuide:
    def __init__(self, slides, sections, intake, design):
        self.slides = slides
        self.sections = sections
        self.intake = intake or {}
        self.design = design or {}
        self.acc = self.design.get("accent_hex") or self.design.get("accent") or "#f2b134"
        self.pri = self.design.get("primary_hex") or self.design.get("primary") or "#1A1A1A"
        if not re.fullmatch(r"#[0-9A-Fa-f]{3}([0-9A-Fa-f]{3})?", str(self.acc).strip()): self.acc = "#f2b134"
        if not re.fullmatch(r"#[0-9A-Fa-f]{3}([0-9A-Fa-f]{3})?", str(self.pri).strip()): self.pri = "#1A1A1A"
        self.mut = "#6B7280"
        self.fnt = "#C0C0C0"
        self.deck_title = self.intake.get("DECK_SLUG") or self.intake.get("deck_title") or "Webinar"
        self.owner = self.intake.get("owner_name") or "the presenter"
        self.company = self.intake.get("company_name") or ""
        self.hook = self.intake.get("HOOK") or ""
        self.goal = self.intake.get("GOAL") or ""
        self._font_recs = []
        self._build_styles()

    def _build_styles(self):
        ss = getSampleStyleSheet()
        base = ss["Normal"]
        def S(name, fs, leading=None, bold=False, color=None, accent=False, **kw):
            fs = float(fs)
            if fs < MIN_FONT_PT:
                raise ValueError(f"{name}: {fs}pt < {MIN_FONT_PT}pt floor")
            ld = leading or (fs * 1.4)
            c = color or (self.acc if accent else self.pri)
            fn = "Helvetica-Bold" if bold else "Helvetica"
            st = ParagraphStyle(name, parent=base, fontSize=fs, leading=ld,
                                textColor=_hex(c), fontName=fn, **kw)
            self._font_recs.append((name, fs))
            return st
        self.st = {
            "cover_title": S("cover_title", 28, 34, bold=True),
            "cover_sub":   S("cover_sub", 16, 22, accent=True, alignment=TA_CENTER),
            "cover_meta":  S("cover_meta", 12, 17, color="#6B7280", alignment=TA_CENTER),
            "toc_title":   S("toc_title", 20, 26, bold=True),
            "toc_item":    S("toc_item", 14, 22),
            "toc_sub":     S("toc_sub", 12, 18, color="#6B7280"),
            "section_hdr": S("section_hdr", 18, 24, bold=True, accent=True, spaceBefore=14, spaceAfter=4),
            "section_meta":S("section_meta", 12, 17, accent=True, bold=True),
            "section_job": S("section_job", 13, 19, color="#6B7280"),
            "slide_hdr":   S("slide_hdr", 15, 21, bold=True, spaceBefore=8, spaceAfter=2),
            "on_screen":   S("on_screen", 12, 17, color="#6B7280", leftIndent=12),
            "bullet":      S("bullet", 13, 19, leftIndent=12),
            "point_drive": S("point_drive", 14, 20, bold=True, accent=True, leftIndent=6, spaceBefore=4, spaceAfter=4),
            "hook_cue":    S("hook_cue", 13, 19, bold=True, accent=True, leftIndent=12, spaceBefore=2, spaceAfter=2),
            "ladder_cue":  S("ladder_cue", 13, 19, bold=True, color="#DC2626", leftIndent=12, spaceBefore=2, spaceAfter=2),
            "foot":        S("foot", 12, 16, color="#9CA3AF"),
        }

    def verify_floor(self):
        bad = [(n, s) for n, s in self._font_recs if s < MIN_FONT_PT]
        if bad:
            print(f"[FONT-FLOOR-FAIL] {len(bad)} styles < {MIN_FONT_PT:.0f}pt:", file=sys.stderr)
            for n, s in bad: print(f"  - {n}: {s}pt", file=sys.stderr)
            sys.exit(4)
        sizes = sorted(set(s for _, s in self._font_recs))
        print(f"[font-floor-ok] All {len(self._font_recs)} styles >= {MIN_FONT_PT:.0f}pt (range {min(sizes):.0f}-{max(sizes):.0f}pt)")

    def _footer(self, canvas, doc):
        canvas.saveState()
        canvas.setFillColor(_hex("#9CA3AF"))
        canvas.setFont("Helvetica", MIN_FONT_PT)
        title = self.deck_title if len(self.deck_title) < 60 else self.deck_title[:57] + "..."
        foot = f"Presenter's Guide (speaker-facing) -- {title}"
        max_w = 5.4 * inch
        while foot and canvas.stringWidth(foot, "Helvetica", MIN_FONT_PT) > max_w:
            foot = foot[:-2]
        canvas.drawString(0.9 * inch, 0.55 * inch, foot or "...")
        canvas.drawRightString(7.6 * inch, 0.55 * inch, f"Page {doc.page}")
        canvas.restoreState()

    def _cover(self):
        f = []
        f.append(Spacer(1, 1.5 * inch))
        f.append(Paragraph("PRESENTER'S GUIDE", self.st["cover_title"]))
        f.append(Spacer(1, 0.3 * inch))
        f.append(Paragraph("Speaker-Facing Outline", self.st["cover_sub"]))
        f.append(Spacer(1, 0.5 * inch))
        f.append(HRFlowable(width="60%", thickness=2.0, color=_hex(self.acc), spaceBefore=0, spaceAfter=16))
        f.append(Paragraph(_esc(self.deck_title), self.st["cover_sub"]))
        f.append(Spacer(1, 0.2 * inch))
        f.append(Paragraph(f"Prepared for {_esc(self.owner)}", self.st["cover_meta"]))
        f.append(Spacer(1, 0.1 * inch))
        if self.company:
            f.append(Paragraph(_esc(self.company), self.st["cover_meta"]))
            f.append(Spacer(1, 0.1 * inch))
        f.append(Paragraph(date.today().strftime("%B %d, %Y"), self.st["cover_meta"]))
        f.append(Spacer(1, 0.5 * inch))
        dur = self.intake.get("DURATION_MIN", "?")
        meta = [f"Duration: {dur} minutes  |  {len(self.slides)} slides  |  {len(self.sections)} sections"]
        if self.intake.get("TONE"): meta.append(f"Tone: {_esc(self.intake['TONE'])}")
        if self.hook: meta.append(f'Hook: "{_esc(self.hook)}"')
        if self.goal: meta.append(f"Goal: {_esc(self.goal)}")
        for line in meta: f.append(Paragraph(line, self.st["cover_meta"])); f.append(Spacer(1, 0.06 * inch))
        f.append(Spacer(1, 0.3 * inch))
        f.append(HRFlowable(width="60%", thickness=1.5, color=_hex(self.acc), spaceBefore=0, spaceAfter=8))
        f.append(Paragraph(
            "This Guide is your MAP: what to cover and the point to land on each slide. "
            "The Presenter's Speech provides the exact words. "
            "The deck is what the AUDIENCE sees. The Guide and Speech are only for YOU.",
            self.st["cover_meta"]))
        f.append(PageBreak())
        return f

    def _toc(self):
        f = []
        f.append(Spacer(1, 0.3 * inch))
        f.append(Paragraph("Contents &amp; Section Map", self.st["toc_title"]))
        f.append(Spacer(1, 0.15 * inch))
        f.append(HRFlowable(width="100%", thickness=1.0, color=_hex(self.acc), spaceBefore=0, spaceAfter=12))
        for i, sec in enumerate(self.sections, 1):
            name = _esc(sec.get("name", ""))
            first, last = sec.get("first", "?"), sec.get("last", "?")
            sr = f"{first}-{last}" if first != last else str(first)
            job = _esc(sec.get("job", ""))
            f.append(Paragraph(
                f"<b>Section {i}: {name}</b>  "
                f'<font color="{self.mut}">Slides {sr}</font>', self.st["toc_item"]))
            if job: f.append(Paragraph(f'<font color="{self.mut}">{job}</font>', self.st["toc_sub"]))
            f.append(Spacer(1, 0.06 * inch))
        f.append(Spacer(1, 0.12 * inch))
        f.append(Paragraph(f"Total: {len(self.slides)} slides in {len(self.sections)} section(s)", self.st["toc_sub"]))
        f.append(PageBreak())
        return f

    @staticmethod
    def _highlight_placeholders(text):
        """Amber-accent [CLIENT TO SUPPLY] / [OWNER: ...] placeholders."""
        text = re.sub(r'\[CLIENT\s+TO\s+SUPPLY\]',
                       '<font color="#f2b134"><b>[OWNER: fill in your real detail before going live]</b></font>',
                       text, flags=re.I)
        text = re.sub(r'\[OWNER:?\s*[^\]]*\]',
                       lambda m: f'<font color="#f2b134"><b>{m.group(0)}</b></font>',
                       text, flags=re.I)
        return text

    @staticmethod
    def _extract_bullets(note):
        note = note.strip()
        if not note: return []
        blines = re.findall(r"(?:^|\n)\s*[-*]\s+(.+?)(?:\n|$)", note)
        if blines: return [b.strip().rstrip(".").strip() for b in blines[:4]]
        sents = re.split(r"(?<=[.!?])\s+", note)
        return [s.strip().rstrip(".").strip() for s in sents if len(s.strip()) > 5][:4]

    def _derive_point(self, slide):
        note = slide.get("presenter_note", "").strip()
        if note:
            pm = re.search(r"(?:the point|key takeaway|remember|core message|drive home)[:\s-]*(.+?)(?:\.|$)", note, re.I)
            if pm: return pm.group(1).strip() + "."
            sents = re.split(r"(?<=[.!?])\s+", note)
            if sents: return sents[-1].strip().rstrip(".").strip() + "."
        purpose = slide.get("purpose", "").strip()
        if purpose: return purpose.rstrip(".").strip() + "."
        return "[OWNER: fill in your real point to drive home here]"

    def _slide_block(self, slide, sec_name):
        no = slide["no"]; hl = slide["headline"]; purpose = slide.get("purpose", "")
        note = slide.get("presenter_note", ""); ladder = slide.get("ladder", "")
        hook_ref = slide.get("hook_refrain", False); hook_txt = slide.get("hook_text", "") or self.hook
        ss = sec_name or slide.get("section", "")
        ladder_s = f", {ladder}" if ladder else ""
        f = []
        f.append(Paragraph(
            f'SLIDE {no}  [{_esc(hl)}]  '
            f'<font color="{self.mut}">({_esc(ss)}{ladder_s})</font>', self.st["slide_hdr"]))
        os_text = _esc(purpose) if purpose else _esc(hl)
        f.append(Paragraph(f'<b>On screen:</b> <font color="{self.mut}">{os_text}</font>', self.st["on_screen"]))
        if note:
            bullets = self._extract_bullets(note)
            if bullets:
                f.append(Spacer(1, 2))
                for b in bullets:
                    be = self._highlight_placeholders(_esc(b))
                    f.append(Paragraph(f'<font color="{self.mut}">&#8226;</font> '
                        f'<font color="{self.pri}">{be}</font>', self.st["bullet"]))
        else:
            f.append(Paragraph(f'<font color="{self.mut}">&#8226; [INCOMPLETE PRESENTER NOTE]</font>', self.st["bullet"]))
        f.append(Spacer(1, 4))
        point = self._derive_point(slide)
        pd = self._highlight_placeholders(_esc(point))
        f.append(Paragraph(
            f'<font color="{self.acc}"><b>POINT TO DRIVE HOME:</b></font> {pd}',
            self.st["point_drive"]))
        if hook_ref:
            f.append(Spacer(1, 2))
            f.append(Paragraph(
                f'<font color="{self.acc}"><b>SING THE HOOK here:</b></font> '
                f'"{_esc(hook_txt)}"', self.st["hook_cue"]))
        if ladder:
            f.append(Spacer(1, 2))
            f.append(Paragraph(
                f'{_esc(ladder)}: land the number, state the earned reason, '
                f'then <font color="{self.acc}"><b>GO QUIET for 3 seconds</b></font> '
                f'before advancing.', self.st["ladder_cue"]))
        return f

    def build(self, out_path, alias_path=None, sample_mode=False):
        doc = BaseDocTemplate(str(out_path), pagesize=letter,
            leftMargin=0.85*inch, rightMargin=0.85*inch,
            topMargin=0.7*inch, bottomMargin=0.9*inch,
            title=f"Presenter's Guide - {self.deck_title}",
            author="Presenter's Guide Specialist (ROLE-19)")
        frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
        doc.addPageTemplates([PageTemplate(id="all", frames=[frame], onPage=self._footer)])
        story = self._cover() + self._toc()
        for si, sec in enumerate(self.sections):
            first = sec.get("first", 1); last = sec.get("last", first)
            sec_slides = [s for s in self.slides if first <= s["no"] <= last]
            if not sec_slides: continue
            name = _esc(sec.get("name", "Untitled"))
            job = sec.get("job", "")
            sr = f"Slides {first} -- {last}" if first != last else f"Slide {first}"
            story.append(Paragraph(name.upper(), self.st["section_hdr"]))
            story.append(Paragraph(sr, self.st["section_meta"]))
            if job: story.append(Paragraph(job, self.st["section_job"]))
            story.append(HRFlowable(width="100%", thickness=1.0, color=_hex(self.acc), spaceBefore=6, spaceAfter=10))
            for slide in sec_slides:
                bf = self._slide_block(slide, sec.get("name", ""))
                story.append(KeepTogether(bf))
                story.append(Spacer(1, 8))
            if si < len(self.sections) - 1: story.append(PageBreak())
        doc.build(story)
        size = os.path.getsize(out_path) if os.path.exists(out_path) else 0
        if sample_mode:
            floor = MIN_BYTES_SAMPLE
        else:
            # Scale the byte floor with the deck size. MIN_BYTES (51,200) was tuned
            # for a ~34-slide reference deck (~1,500 bytes/slide); a smaller, fully
            # populated deck legitimately renders smaller. Scaling proportionally
            # keeps the floor catching an empty/garbled guide while not rejecting
            # a real 20-slide guide that passes the font floor. (E2E finding.)
            _n_slides = len(getattr(self, "slides", []) or []) or 1
            floor = max(int(MIN_BYTES * _n_slides // 34), MIN_BYTES_SAMPLE)
        if size < floor:
            print(f"[FATAL] {Path(out_path).name} is {size} bytes, below {floor:,}-byte floor", file=sys.stderr)
            sys.exit(3)
        if alias_path:
            Path(alias_path).parent.mkdir(parents=True, exist_ok=True)
            try: shutil.copy2(str(out_path), str(alias_path))
            except Exception as e: print(f"[warn] alias copy failed: {e}")
        return doc.page, size


# ------------------------------------------ sample builders for --sample
_SAMPLE_INTAKE = {
    "DURATION_MIN": 60, "GOAL": "Get the viewer to book a call or purchase.",
    "HOOK": "You are not behind. You are one decision away.",
    "TONE": "Prolific, passionate, warm, direct",
    "owner_name": "Jordan Avery", "company_name": "Avery Growth Lab",
    "DECK_SLUG": "From Overlooked to Overbooked",
}
_SAMPLE_ARC = {"components": [
    {"name": "Welcome & Housekeeping", "first_slide": 1, "last_slide": 1,
     "job": "Greet the audience, set expectations."},
    {"name": "Who This Is For", "first_slide": 2, "last_slide": 2,
     "job": "Name the target avatar; make them feel seen."},
    {"name": "Credibility", "first_slide": 3, "last_slide": 3,
     "job": "Earn the right to teach."},
    {"name": "The Big Promise", "first_slide": 4, "last_slide": 4,
     "job": "Deliver the hook and core belief shift."},
    {"name": "The Close", "first_slide": 5, "last_slide": 5,
     "job": "Re-anchor the hook; call to action."},
]}
_SAMPLE_SLIDES = [
    {"no": 1, "headline": "Welcome", "presenter_note":
     "Warmly welcome everyone. Congratulate them for showing up. "
     "Ask them to drop where they are watching from. Cover housekeeping. "
     "Build anticipation for what is coming at the end.",
     "purpose": "Welcome the audience and set expectations",
     "section": "Welcome & Housekeeping"},
    {"no": 2, "headline": "Is this you?", "presenter_note":
     "Describe exactly who this is for: the talented person who feels invisible. "
     "Name the pain: doing good work but not being noticed. Make them feel seen.",
     "purpose": "Identify the target avatar and pain point",
     "section": "Who This Is For"},
    {"no": 3, "headline": "I was exactly where you are", "presenter_note":
     "Share your personal low moment. [OWNER: say the one true detail about your lowest moment here]. "
     "Then share the exact moment things turned around.",
     "purpose": "Build credibility and personal connection",
     "section": "Credibility"},
    {"no": 4, "headline": "The big promise", "presenter_note":
     "State the core belief shift. It is not more talent or time. "
     "The key insight: you are one decision away. "
     "Deliver the hook and ask them to say it with you.",
     "purpose": "Deliver the hook and core belief shift",
     "section": "The Big Promise",
     "hook_refrain": True, "hook_text": "You are not behind. You are one decision away."},
    {"no": 5, "headline": "One decision away",
     "presenter_note": "Recap the journey. Re-anchor the hook one final time. "
     "The only thing left is the decision. Close warm and direct.",
     "purpose": "Close the presentation and spur action",
     "section": "The Close",
     "hook_refrain": True, "hook_text": "You are not behind. You are one decision away."},
]


# ------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Build PRESENTER-GUIDE.pdf (speaker-facing outline)")
    ap.add_argument("--run-dir", required=True, help="run directory (contains working/)")
    ap.add_argument("--sample", action="store_true", help="build from built-in sample speech")
    args = ap.parse_args()
    run_dir = Path(args.run_dir).resolve()
    if not run_dir.exists():
        print(f"[FATAL] Run directory does not exist: {run_dir}", file=sys.stderr); sys.exit(2)

    print(f"[presenter-guide] Reading inputs from {run_dir}")

    if args.sample:
        print("[presenter-guide] --sample: using built-in sample data")
        intake = dict(_SAMPLE_INTAKE)
        arc = dict(_SAMPLE_ARC)
        copy_text = ""
        design = {}
    else:
        intake = _load_json(run_dir / "working" / "copy" / "intake.json") or {}
        arc = _load_json(run_dir / "working" / "copy" / "arc_allocation.json") or {}
        copy_text = _load_copy(run_dir)
        design = _load_design(run_dir)

    hook = intake.get("HOOK", "")
    deck_title = intake.get("DECK_SLUG") or intake.get("deck_title") or "Webinar"

    print(f"  Deck: {deck_title}")
    print(f"  Owner: {intake.get('owner_name', '?')}")
    print(f"  Duration: {intake.get('DURATION_MIN', '?')} min")

    if copy_text.strip():
        slides = _parse_slides_copy(copy_text)
        print(f"  Parsed {len(slides)} slides from slides_copy.md")
    elif args.sample:
        slides = [dict(s) for s in _SAMPLE_SLIDES]
        print(f"  Using {len(slides)} sample slides")
    else:
        print("[warn] slides_copy.md unreadable; degrading to speech file")
        speech = _load_speech(run_dir)
        if speech.strip():
            slides = _parse_slides_speech(speech)
            print(f"  Parsed {len(slides)} slides from PRESENTERS-SPEECH.md")
        else:
            print("[FATAL] No slide source available", file=sys.stderr); sys.exit(1)

    if not slides:
        print("[FATAL] No slides found", file=sys.stderr); sys.exit(1)

    sections = _build_sections(arc, slides)
    print(f"  Built {len(sections)} section(s) from arc" if sections else
          "[warn] No sections; treating as one flat section")
    if not sections:
        sections = [{"name": "PRESENTATION", "first": slides[0]["no"],
                      "last": slides[-1]["no"], "job": "Deliver the complete presentation"}]

    guide = PresenterGuide(slides, sections, intake, design)
    guide.verify_floor()

    deliverables = run_dir / "working" / "deliverables"
    deliverables.mkdir(parents=True, exist_ok=True)
    out_path = deliverables / "PRESENTER-GUIDE.pdf"

    safe = _sanitize_filename(deck_title)
    alias_dir = run_dir / "working" / "presenter-guide"
    alias = alias_dir / f"Presenters_Guide_{safe}.pdf"

    is_sample = args.sample
    print(f"\n[presenter-guide] Rendering {out_path} ...")
    pages, size = guide.build(str(out_path), str(alias), sample_mode=is_sample)

    _n = len(getattr(guide, "slides", []) or []) or 1
    floor = MIN_BYTES_SAMPLE if is_sample else max(int(MIN_BYTES * _n // 34), MIN_BYTES_SAMPLE)
    print(f"[presenter-guide] Rendered {out_path} ({pages} page(s), {size:,} bytes)")
    print(f"[presenter-guide] Alias: {alias}")
    if size >= floor:
        print(f"[presenter-guide] Above {floor:,}-byte {'sample' if is_sample else ''} floor: PASS")
    print("[presenter-guide] Done. Exit code 0.")


if __name__ == "__main__":
    main()
