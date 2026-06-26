#!/usr/bin/env python3
"""
presenters_speech_pdf.py -- Reusable Presenter's Speech TELEPROMPTER PDF generator.

OWNED BY: Presenter's Speech Writer (ROLE-20), Presentations department.
This is the PDF template referenced by presenters-speech-writer.md SOP 9.2.
It does NOT touch build_deck.py / sync_check.py / PIPELINE-MANIFEST.json (other owners).

VISUAL TARGET
-------------
This generator reproduces the layout of the department's reference file
`STANDARD-presenter-speech-layout.pdf` (the visual gold standard cited in SOP 9.2):

- LEAN COVER HEADER: big "PRESENTER'S SPEECH" title; one amber line
  "Owner -- Deck -- Word for Word"; ONE small grey pacing/legend line; a double
  amber rule; a "WORD-FOR-WORD SPEECH" section header. Slide 1 content begins on
  page 1 (no separate cover page that pushes the read back).
- BAR PER SLIDE: every slide leads with a "Slide N  [ LABEL ]" bar (slide number
  in dark ink, the LABEL in small grey caps) and a thin rule beneath it -- NOT one
  color band per webinar stage. At most a slim stage tint is carried on the bar.
- READABLE PARAGRAPHS: the spoken block is split into its natural paragraphs, set
  in black at a generous leading, the way a presenter actually reads it.
- CUES ON THEIR OWN LINE: [PAUSE] / [BREATHE] / [BREAK] AND the longer
  "(PAUSE 2 seconds)" / "(BREATHE)" forms are pulled onto their own amber line so
  the eye catches the beat. BOTH bracket and paren forms are supported.
- TELEPROMPTER FONT FLOOR: nothing below 14pt anywhere (hard floor, MIN_FONT_PT).
  The spoken body and the slide label are >=15pt; everything else >=14pt.
- PER-SLIDE PACING is KEPT (it is a KPI) but restyled to a SMALL GREY MARGIN NOTE
  so it never clutters the read.

INPUT
-----
A JSON "speech spec". See SAMPLE_SPEC at the bottom and `--emit-sample-spec`.
Shape (unchanged from the prior version -- backward compatible):
{
  "deck_title": str,
  "owner_name": str,
  "company_name": str,
  "duration_min": number,
  "tone": str,
  "hook": str,                       # the verbatim refrain
  "spoken_rate_wpm": 130,            # tunable; default 130
  "brand": {"primary": "#RRGGBB", "accent": "#RRGGBB", "ink": "#RRGGBB"},  # optional
  "design_system_path": "working/typography/design_system.json",  # optional; when
       # present, brand.accent_hex / brand.headline_font / brand.body_font from the
       # design system OVERRIDE the accent + typefaces so the PDF inherits the deck's
       # locked design system. (Also settable via the --design-system CLI flag.)
  "stages": [                        # ordered webinar stages
    {
      "stage": "WELCOME",            # one of the canonical stage keys (see STAGE_TINT)
      "label": "Welcome & Housekeeping",
      "slides": [
        {
          "slide_no": 1,
          "headline": "Welcome",
          "purpose": "...",          # optional (printed as a small grey note)
          "spoken": "Hello and welcome...",   # the word-for-word block
          "kind": "normal"           # normal | hook | drop | final | cta | owner_prompt
        }, ...
      ]
    }, ...
  ]
}

USAGE
-----
  python3 presenters_speech_pdf.py --spec speech_spec.json --out PRESENTER-SPEECH.pdf
  python3 presenters_speech_pdf.py --sample --out SAMPLE.pdf      # render built-in stub
  python3 presenters_speech_pdf.py --emit-sample-spec spec.json   # write the stub spec

OUTPUT FILENAME
---------------
The canonical shipped name is PRESENTER-SPEECH.pdf (singular; SOP 9.2, matching the
AF-DH1 client-package whitelist + PRESENTER-GUIDE/PRESENTER-AUDIO).

ENFORCEMENT (mirrors SOP 9.2 auto-fails)
- 14pt teleprompter floor enforced in code (MIN_FONT_PT). Any style below it raises.
- Word count per slide is computed (cues stripped) and shown as a small margin note;
  total vs budget is printed to stdout.
"""

import argparse
import json
import re
import sys

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

MIN_FONT_PT = 14.0  # HARD FLOOR (teleprompter). SOP 9.2: no text below 14pt.

# A slim per-stage TINT carried on the slide bar only (NOT a full color band).
# The bar-per-slide layout is the navigation surface; the tint is a faint hint of
# where the presenter is in the webinar arc, never a heavy band.
STAGE_TINT = {
    "PRESTART":    "#94A3B8",
    "WELCOME":     "#38BDF8",
    "WHO_FOR":     "#22D3EE",
    "HOOK":        "#A78BFA",
    "CREDIBILITY": "#818CF8",
    "BIG_PROMISE": "#C084FC",
    "TEACH":       "#60A5FA",
    "PROOF":       "#34D399",
    "OFFER":       "#FBBF24",
    "PRICE_DROP":  "#F87171",
    "SCARCITY":    "#FB923C",
    "RECAP":       "#2DD4BF",
    "CLOSE":       "#FB7185",
    "QA":          "#A78BFA",
}
DEFAULT_STAGE_TINT = "#CBD5E1"

# kind -> small inline badge (kept, but rendered as a quiet grey-caps tag on the bar,
# not a loud colored pill) so special slides are still identifiable at a glance.
KIND_BADGE = {
    "hook":         "HOOK REFRAIN",
    "drop":         "PRICE DROP",
    "final":        "FINAL PRICE",
    "cta":          "CALL TO ACTION",
    "owner_prompt": "OWNER PROMPT",
}

# Cue forms. We support BOTH the short bracket form ([PAUSE], [BREATHE], [BREAK],
# [long-break]) AND the longer paren form ((PAUSE 2 seconds), (BREATHE), (BREAK)).
# A cue that sits alone on a line becomes its own amber cue line; a cue embedded
# mid-paragraph is colored inline.
BRACKET_CUE_RE = re.compile(
    r"\[\s*(?:PAUSE|BREATHE|BREAK|LONG[- ]?BREAK|SHORT\s+PAUSE)\s*\]",
    re.IGNORECASE,
)
PAREN_CUE_RE = re.compile(
    r"\(\s*(?:PAUSE|BREATHE|BREAK|LONG[- ]?BREAK|SHORT\s+PAUSE)\b[^)]*\)",
    re.IGNORECASE,
)
# Combined matcher used for word-count stripping and inline coloring.
ANY_CUE_RE = re.compile(
    BRACKET_CUE_RE.pattern + "|" + PAREN_CUE_RE.pattern, re.IGNORECASE
)
# Owner / client prompts -- a different amber-accent inline span (kept as a beat
# the presenter must personalize, never fabricated).
OWNER_RE = re.compile(r"\((?:OWNER|CLIENT)[^)]*\)", re.IGNORECASE)
# Fish-Audio expression-tag hints. These are NOT pacing cues (e.g. [warm and
# welcoming]) -- on the CLEAN teleprompter PDF they should not appear, but if a
# tagged spec is fed in we color them faintly rather than speak them.
# (Anything in [brackets] that is not a recognized pacing cue.)
EXPR_TAG_RE = re.compile(r"\[[^\]]+\]")


def _hex(c):
    return colors.HexColor(c) if isinstance(c, str) else c


def _wc(text):
    """Word count of the spoken text, ignoring pacing cues, owner prompts and tags."""
    stripped = ANY_CUE_RE.sub(" ", text)
    stripped = OWNER_RE.sub(" ", stripped)
    stripped = EXPR_TAG_RE.sub(" ", stripped)  # strip any leftover [expression tags]
    return len([w for w in re.split(r"\s+", stripped.strip()) if w])


def _esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _is_pure_cue_line(line):
    """True if a stripped line is ONLY a pacing cue (and nothing else)."""
    s = line.strip()
    if not s:
        return False
    rest = ANY_CUE_RE.sub("", s).strip()
    return rest == "" and ANY_CUE_RE.search(s) is not None


def _normalize_cue(raw):
    """Return the display label for a cue token, e.g. '[PAUSE]', '[BREATHE]'.
    The longer paren forms collapse to a clean uppercase bracket label so the
    teleprompter cue line is consistent regardless of which form was authored."""
    inner = raw.strip().strip("[]()").strip()
    up = inner.upper()
    if up.startswith("PAUSE"):
        # keep any trailing duration hint (e.g. "PAUSE 3 SECONDS") but tidy it
        return "[PAUSE]" if up == "PAUSE" else "[" + " ".join(up.split()) + "]"
    if up.startswith("BREATHE"):
        return "[BREATHE]"
    if up.startswith("SHORT"):
        return "[SHORT PAUSE]"
    if "LONG" in up and "BREAK" in up:
        return "[LONG BREAK]"
    if up.startswith("BREAK"):
        return "[BREAK]"
    return "[" + up + "]"


class SpeechPDF:
    def __init__(self, spec):
        self.spec = spec
        self.rate = float(spec.get("spoken_rate_wpm", 130))
        brand = spec.get("brand", {})
        # Ink is the body color; accent is the amber cue/subtitle color in the
        # reference. Defaults match the STANDARD reference look.
        self.primary = brand.get("primary", "#1A1A1A")   # near-black title ink
        self.accent = brand.get("accent", "#C8860D")      # amber (cues, subtitle, rules)
        self.ink = brand.get("ink", "#1A1A1A")            # body ink (black-ish)
        self.muted = "#7A7A7A"                            # grey for labels / margin notes
        self.faint = "#B8B8B8"                            # faint grey for thin rules
        self.tag_col = "#9333EA"                          # purple for stray expression tags
        # Default typeface families (reportlab built-ins). May be overridden by the
        # design-system below.
        self.headline_font = "Helvetica-Bold"
        self.body_font = "Helvetica"
        # design-system accent that MUST appear in the rendered color table; set by
        # _apply_design_system when a design_system.json is wired into the spec.
        self.design_system_accent = None
        self._apply_design_system()
        self._build_styles()

    def _apply_design_system(self):
        """When the speech spec carries a `design_system_path`, pull the LOCKED
        brand accent and typeface families from design_system.json so the speech
        PDF inherits the deck's design system instead of the house defaults.

        Reads brand.accent_hex (accent color), brand.headline_font and
        brand.body_font (typeface family names). Font names are mapped to a
        reportlab built-in family; if an explicit *_font_file TTF path is given
        and exists, it is registered and used verbatim. Absent/unreadable
        design system leaves the reference defaults untouched (backward compatible).
        """
        ds_path = self.spec.get("design_system_path")
        if not ds_path:
            return
        try:
            with open(ds_path) as f:
                ds = json.load(f)
        except Exception:
            return
        brand = ds.get("brand") if isinstance(ds, dict) else None
        if not isinstance(brand, dict):
            return
        accent = brand.get("accent_hex") or brand.get("accent")
        if isinstance(accent, str) and re.fullmatch(
            r"#[0-9A-Fa-f]{3}([0-9A-Fa-f]{3})?", accent.strip()
        ):
            self.accent = accent.strip()
            self.design_system_accent = accent.strip()
        self.headline_font = self._resolve_font(
            brand.get("headline_font"), brand.get("headline_font_file"),
            default="Helvetica-Bold", bold=True,
        )
        self.body_font = self._resolve_font(
            brand.get("body_font"), brand.get("body_font_file"),
            default="Helvetica", bold=False,
        )

    @staticmethod
    def _resolve_font(font_name, font_file, default, bold):
        """Resolve a design-system font name to a usable reportlab font.

        If a TTF path is provided and readable, register and return it. Otherwise
        map the family name to the nearest reportlab built-in (Times/Courier),
        defaulting to the Helvetica family. Never raises -- falls back to default.
        """
        if font_file:
            try:
                from reportlab.pdfbase import pdfmetrics
                from reportlab.pdfbase.ttfonts import TTFont
                import os
                if os.path.exists(font_file):
                    reg_name = os.path.splitext(os.path.basename(font_file))[0]
                    pdfmetrics.registerFont(TTFont(reg_name, font_file))
                    return reg_name
            except Exception:
                pass
        if not isinstance(font_name, str) or not font_name.strip():
            return default
        low = font_name.lower()
        if "times" in low or ("serif" in low and "sans" not in low):
            return "Times-Bold" if bold else "Times-Roman"
        if "courier" in low or "mono" in low:
            return "Courier-Bold" if bold else "Courier"
        # Sans-serif families (Helvetica, Arial, Montserrat, Inter, etc.) map to
        # the Helvetica built-in family, the closest universally available sans.
        return "Helvetica-Bold" if bold else "Helvetica"

    def _S(self, name, **kw):
        size = kw.get("fontSize", MIN_FONT_PT)
        if size < MIN_FONT_PT:
            raise ValueError(
                f"Style {name!r} fontSize {size} below {MIN_FONT_PT}pt teleprompter "
                f"floor (SOP 9.2 auto-fail)."
            )
        leading = kw.pop("leading", size * 1.4)
        return ParagraphStyle(name, parent=self.base, leading=leading, **kw)

    def _build_styles(self):
        ss = getSampleStyleSheet()
        self.base = ss["Normal"]
        self.base.fontName = self.body_font
        self.st = {
            # --- lean cover header (no separate cover page) ---
            "cover_title": self._S("cover_title", fontSize=30, leading=34,
                                    textColor=_hex(self.primary),
                                    fontName=self.headline_font),
            "cover_sub": self._S("cover_sub", fontSize=15, leading=20,
                                  textColor=_hex(self.accent)),
            "cover_pacing": self._S("cover_pacing", fontSize=14, leading=18,
                                    textColor=_hex(self.muted)),
            "section_hdr": self._S("section_hdr", fontSize=15, leading=19,
                                    textColor=_hex(self.primary),
                                    fontName=self.headline_font),
            # --- per-slide bar ---
            "slide_no": self._S("slide_no", fontSize=16, leading=20,
                                 textColor=_hex(self.primary),
                                 fontName=self.headline_font),
            "slide_label": self._S("slide_label", fontSize=15, leading=20,
                                    textColor=_hex(self.muted),
                                    fontName=self.body_font),
            "badge": self._S("badge", fontSize=14, leading=18,
                             textColor=_hex(self.muted),
                             fontName="Helvetica-Bold"),
            # --- body ---
            "spoken": self._S("spoken", fontSize=16, leading=23,
                              textColor=_hex(self.ink), spaceBefore=2,
                              spaceAfter=2, alignment=TA_LEFT,
                              fontName=self.body_font),
            "cue": self._S("cue", fontSize=14, leading=20,
                           textColor=_hex(self.accent),
                           fontName="Helvetica-Bold", leftIndent=18,
                           spaceBefore=4, spaceAfter=4),
            "purpose": self._S("purpose", fontSize=14, leading=18,
                               textColor=_hex(self.muted),
                               fontName="Helvetica-Oblique"),
            # per-slide pacing, restyled as a SMALL GREY MARGIN NOTE (KPI kept)
            "pacing": self._S("pacing", fontSize=14, leading=17,
                              textColor=_hex(self.muted),
                              fontName="Helvetica-Oblique"),
            "foot": self._S("foot", fontSize=14, leading=17,
                            textColor=_hex(self.muted)),
        }

    # ---- page furniture -------------------------------------------------
    def _footer(self, canvas, doc):
        canvas.saveState()
        canvas.setFillColor(_hex(self.muted))
        canvas.setFont("Helvetica", MIN_FONT_PT)
        title = self.spec.get("deck_title", "Presenter's Speech")
        foot = f"Presenter's Speech (speaker-facing) -- {title}"
        # Keep the footer text clear of the right-aligned page number.
        max_w = 5.4 * inch
        full = foot
        while foot and canvas.stringWidth(foot, "Helvetica", MIN_FONT_PT) > max_w:
            foot = foot[:-2]
        if foot != full:
            foot = foot.rstrip() + "…"
        canvas.drawString(0.9 * inch, 0.55 * inch, foot)
        canvas.drawRightString(7.6 * inch, 0.55 * inch, f"Page {doc.page}")
        canvas.setStrokeColor(_hex(self.faint))
        canvas.setLineWidth(0.75)
        canvas.line(0.9 * inch, 0.75 * inch, 7.6 * inch, 0.75 * inch)
        canvas.restoreState()

    # ---- per-slide bar + body ------------------------------------------
    def _slide_bar(self, stage_key, slide):
        """The 'Slide N  [ LABEL ]' bar with a slim stage tint and a thin rule."""
        tint = _hex(STAGE_TINT.get(stage_key, DEFAULT_STAGE_TINT))
        no = slide.get("slide_no", "?")
        headline = slide.get("headline", "")
        label = headline.upper().strip()
        kind = slide.get("kind", "normal")
        badge = KIND_BADGE.get(kind)
        # "Slide N" in dark ink + " [ LABEL ]" in grey caps, on one line.
        # The label font stays at the 14pt floor (size="14") so nothing dips below it.
        bar_markup = (
            f'<font color="{self.primary}"><b>Slide {no}</b></font>'
            f'&nbsp;&nbsp;<font size="14" color="{self.muted}">[ {_esc(label)} ]</font>'
        )
        cells = [[Paragraph(bar_markup, self.st["slide_no"])]]
        widths = [6.7 * inch]
        if badge:
            badge_p = Paragraph(_esc(badge), self.st["badge"])
            cells = [[Paragraph(bar_markup, self.st["slide_no"]), badge_p]]
            widths = [4.55 * inch, 2.15 * inch]
        head = Table(cells, colWidths=widths)
        head.setStyle(TableStyle([
            # thin grey rule under the bar (the reference look)
            ("LINEBELOW", (0, 0), (-1, -1), 0.75, _hex(self.faint)),
            # slim stage tint as a short colored rule segment on the left edge
            ("LINEABOVE", (0, 0), (0, 0), 2.5, tint),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
        ]))
        return head

    def _render_spoken_flow(self, spoken):
        """Split the spoken block into readable paragraphs and amber cue lines.

        A line (split on blank lines OR on a standalone cue token) that is purely a
        pacing cue becomes its own amber cue line; everything else is a body
        paragraph. Cues embedded mid-sentence are colored inline (not pulled out).
        """
        flow = []
        # First, normalize: ensure each standalone cue token sits on its own line so
        # an author who wrote "...land. (PAUSE 2 seconds) Now..." still gets a clean
        # break. We split on blank lines into blocks, then within a block we walk
        # tokens and break out pure-cue runs.
        # Normalize Windows newlines.
        text = spoken.replace("\r\n", "\n").replace("\r", "\n")
        # Split into paragraph blocks on blank lines.
        blocks = re.split(r"\n\s*\n", text)
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            # Within a block, isolate cues that the author placed inline so they can
            # become their own line. We split the block on cue tokens but KEEP the
            # tokens.
            parts = re.split(f"({ANY_CUE_RE.pattern})", block, flags=re.IGNORECASE)
            buf = ""
            for part in parts:
                if part is None:
                    continue
                if ANY_CUE_RE.fullmatch(part.strip()):
                    # flush any buffered body text first
                    if buf.strip():
                        self._emit_body(flow, buf)
                        buf = ""
                    flow.append(Paragraph(_esc(_normalize_cue(part)), self.st["cue"]))
                else:
                    buf += part
            if buf.strip():
                self._emit_body(flow, buf)
        if not flow:
            self._emit_body(flow, spoken)
        return flow

    def _emit_body(self, flow, text):
        """Emit a body paragraph. Any leftover inline owner-prompt or stray
        expression tag is colored; pacing cues at this point are already split out,
        but if one is embedded mid-sentence we color it amber inline."""
        safe = _esc(text.strip())
        # color inline pacing cues amber (these were embedded mid-sentence)
        safe = ANY_CUE_RE.sub(
            lambda m: f'<font color="{self.accent}"><b>{_normalize_cue(m.group(0))}</b></font>',
            safe,
        )
        # color owner prompts in amber-accent (a beat to personalize)
        safe = OWNER_RE.sub(
            lambda m: f'<font color="{self.accent}"><b>{m.group(0)}</b></font>', safe
        )
        # color any stray Fish expression tag faintly (should not be on clean PDF)
        safe = EXPR_TAG_RE.sub(
            lambda m: (m.group(0)
                       if ANY_CUE_RE.fullmatch(m.group(0))
                       else f'<font color="{self.tag_col}">{m.group(0)}</font>'),
            safe,
        )
        # collapse internal whitespace/newlines into single spaces for one paragraph
        safe = re.sub(r"\s+", " ", safe).strip()
        if safe:
            flow.append(Paragraph(safe, self.st["spoken"]))

    def _slide_block(self, stage_key, slide):
        flow = [self._slide_bar(stage_key, slide), Spacer(1, 4)]
        purpose = slide.get("purpose")
        if purpose:
            flow.append(Paragraph(_esc(purpose), self.st["purpose"]))
            flow.append(Spacer(1, 2))
        spoken = slide.get("spoken", "")
        flow += self._render_spoken_flow(spoken)
        words = _wc(spoken)
        secs = round(words / self.rate * 60.0, 1)
        # per-slide pacing KEPT as a small grey margin note (KPI, restyled)
        pacing = (f"{words} words &middot; ~{secs:.0f}s at {self.rate:.0f} wpm")
        flow.append(Spacer(1, 2))
        flow.append(Paragraph(pacing, self.st["pacing"]))
        flow.append(Spacer(1, 16))
        return flow, words, secs

    # ---- lean cover header (NO separate cover page) ---------------------
    def _cover_header(self):
        s = self.spec
        flow = []
        flow.append(Paragraph("PRESENTER&#39;S SPEECH", self.st["cover_title"]))
        flow.append(Spacer(1, 4))
        # "Owner -- Deck -- Word for Word"
        owner = _esc(s.get("owner_name", "the presenter"))
        deck = _esc(s.get("deck_title", "Webinar"))
        sub = f"{owner} &mdash; {deck} &mdash; Word for Word"
        flow.append(Paragraph(sub, self.st["cover_sub"]))
        flow.append(Spacer(1, 10))
        # ONE pacing / legend line (two physical lines of small grey text).
        pacing_line = (
            f"Pacing: ~{self.rate:.0f} words per minute. Read at a comfortable, "
            f"conversational pace. "
            f'<font color="{self.accent}"><b>[PAUSE]</b></font> marks a beat, one to '
            f'two seconds. <font color="{self.accent}"><b>[BREATHE]</b></font> marks a '
            f"longer pause. Read this text aloud, not quickly; let each idea land "
            f"before moving."
        )
        flow.append(Paragraph(pacing_line, self.st["cover_pacing"]))
        flow.append(Spacer(1, 8))
        # double amber rule (the reference uses a thicker amber line)
        flow.append(HRFlowable(width="100%", thickness=2.2,
                               color=_hex(self.accent), spaceBefore=0, spaceAfter=12))
        # "WORD-FOR-WORD SPEECH" section header + thin amber rule under it
        flow.append(Paragraph("WORD-FOR-WORD SPEECH", self.st["section_hdr"]))
        flow.append(HRFlowable(width="100%", thickness=1.0,
                               color=_hex(self.accent), spaceBefore=4, spaceAfter=16))
        return flow

    # ---- build ----------------------------------------------------------
    def build(self, out_path):
        doc = BaseDocTemplate(
            out_path, pagesize=letter,
            leftMargin=0.9 * inch, rightMargin=0.9 * inch,
            topMargin=0.8 * inch, bottomMargin=0.95 * inch,
            title=self.spec.get("deck_title", "Presenter's Speech"),
            author="Presenter's Speech Writer (ROLE-20)",
        )
        frame = Frame(doc.leftMargin, doc.bottomMargin,
                      doc.width, doc.height, id="main")
        doc.addPageTemplates([PageTemplate(id="all", frames=[frame],
                                           onPage=self._footer)])
        story = []
        story += self._cover_header()

        total_words = 0
        total_secs = 0.0
        for stage in self.spec.get("stages", []):
            stage_key = stage.get("stage", "")
            for slide in stage.get("slides", []):
                flow, w, s = self._slide_block(stage_key, slide)
                # keep the bar with at least its first body paragraph
                if len(flow) >= 2:
                    story.append(KeepTogether(flow[:2]))
                    story += flow[2:]
                else:
                    story += flow
                total_words += w
                total_secs += s

        doc.build(story)
        return total_words, total_secs


# --------------------------------------------------------------------------
# Built-in stub speech. Uses BOTH cue forms ([PAUSE] bracket and the longer
# "(PAUSE 2 seconds)" paren form) so the renderer's dual-form support is exercised
# in the sample render. Paragraphs are separated by blank lines so the reader
# splits them cleanly.
SAMPLE_SPEC = {
    "deck_title": "From Overlooked to Overbooked: The 90-Day Authority Webinar",
    "owner_name": "Jordan Avery",
    "company_name": "Avery Growth Lab",
    "duration_min": 60,
    "tone": "Prolific, passionate, warm, direct",
    "hook": "You are not behind. You are one decision away.",
    "spoken_rate_wpm": 130,
    "brand": {"primary": "#1A1A1A", "accent": "#C8860D", "ink": "#1A1A1A"},
    "stages": [
        {
            "stage": "WELCOME", "label": "Welcome & Housekeeping",
            "slides": [{
                "slide_no": 1, "headline": "Welcome",
                "kind": "normal",
                "spoken": (
                    "Hello and welcome, everybody.\n\n"
                    "[PAUSE]\n\n"
                    "Congratulations on taking the first step just by being here. I mean "
                    "that. You could be doing a hundred other things right now, and instead "
                    "you showed up for your future.\n\n"
                    "So before we go one inch further, do me a favor. Drop in the chat where "
                    "you are watching from today. Go ahead, I will wait.\n\n"
                    "[BREATHE]\n\n"
                    "Quick housekeeping. Stay to the very end, because what I save for the "
                    "last ten minutes is the part nobody else will give you for free."
                ),
            }],
        },
        {
            "stage": "WHO_FOR", "label": "Who This Is For",
            "slides": [{
                "slide_no": 2, "headline": "Is this you?",
                "kind": "normal",
                "spoken": (
                    "Let me tell you exactly who this is for.\n\n"
                    "This is for the person who is genuinely good at what they do, and is "
                    "quietly furious that the world has not noticed yet. If you are nodding "
                    "right now, you are in the right room. (PAUSE 2 seconds) And if you are "
                    "just curious, that is fine too. Stay. Steal everything."
                ),
            }],
        },
        {
            "stage": "CREDIBILITY", "label": "Who I Am",
            "slides": [{
                "slide_no": 3, "headline": "I was exactly where you are",
                "kind": "owner_prompt",
                "spoken": (
                    "Five years ago I was the best-kept secret in my whole industry. "
                    "Talented, broke, and invisible.\n\n"
                    "(OWNER: say the one true detail about your lowest moment here, in your "
                    "own words.)\n\n"
                    "[PAUSE]\n\n"
                    "And then one Tuesday something broke open for me, and I want to give "
                    "you that exact moment today."
                ),
            }],
        },
        {
            "stage": "BIG_PROMISE", "label": "The One Thing",
            "slides": [{
                "slide_no": 4, "headline": "The big promise",
                "kind": "hook",
                "spoken": (
                    "Here is the one thing I need you to believe before you leave today.\n\n"
                    "It is not that you need more talent. It is not that you need more time. "
                    "(PAUSE 2 seconds) It is that you are one decision away from being "
                    "seen.\n\n"
                    "Say it with me. You are not behind. You are one decision away."
                ),
            }],
        },
        {
            "stage": "TEACH", "label": "Teach the Framework",
            "slides": [{
                "slide_no": 5, "headline": "Secret one: the vehicle",
                "kind": "normal",
                "spoken": (
                    "So let me hand you the framework. I call it the Authority Loop, and it "
                    "has three moves.\n\n"
                    "Move one. Pick one painfully specific person to serve. Not everyone. "
                    "One. Because the riches really are in the niches, and the fastest way "
                    "to be ignored is to talk to everybody at once."
                ),
            }],
        },
        {
            "stage": "PROOF", "label": "Proof & Case Studies",
            "slides": [{
                "slide_no": 6, "headline": "It works for people like you",
                "kind": "owner_prompt",
                "spoken": (
                    "Let me show you it is not just me.\n\n"
                    "(OWNER: share one real client win with the actual number and the actual "
                    "timeframe.)\n\n"
                    "Same framework. Ordinary person. Extraordinary result. That could be "
                    "your story ninety days from now."
                ),
            }],
        },
        {
            "stage": "OFFER", "label": "The Offer & Value Stack",
            "slides": [{
                "slide_no": 7, "headline": "Everything you get",
                "kind": "normal",
                "spoken": (
                    "So here is everything you get when you join the 90-Day Authority "
                    "program.\n\n"
                    "You get the full Authority Loop course. And you get the live coaching "
                    "calls. And you get the swipe library. (OWNER: confirm the real stack "
                    "and the real value of each.)\n\n"
                    "Add it all up and the honest value is well into five figures."
                ),
            }],
        },
        {
            "stage": "PRICE_DROP", "label": "Price Drop & Anchoring",
            "slides": [{
                "slide_no": 8, "headline": "Your investment today",
                "kind": "drop",
                "spoken": (
                    "Now here is what I want you to notice. You showed up. You stayed live "
                    "with me. That matters, and I am going to honor it.\n\n"
                    "You will not pay the full value today. (PAUSE 3 seconds) Because you "
                    "are here live, it is a fraction of that.\n\n"
                    "(OWNER: state the real anchor price, then the real live price.)"
                ),
            }],
        },
        {
            "stage": "SCARCITY", "label": "Scarcity & Urgency",
            "slides": [{
                "slide_no": 9, "headline": "Why now",
                "kind": "cta",
                "spoken": (
                    "This price closes when this webinar ends. (OWNER: state the real "
                    "deadline and any real spot limit.)\n\n"
                    "Go to the link on your screen right now and claim your seat while the "
                    "door is still open."
                ),
            }],
        },
        {
            "stage": "RECAP", "label": "Recap",
            "slides": [{
                "slide_no": 10, "headline": "What we covered",
                "kind": "normal",
                "spoken": (
                    "Let me bring it home.\n\n"
                    "We named who you are, we broke the beliefs holding you back, I handed "
                    "you the Authority Loop, and I showed you the door. The only thing left "
                    "is your decision."
                ),
            }],
        },
        {
            "stage": "CLOSE", "label": "The Close",
            "slides": [{
                "slide_no": 11, "headline": "One decision away",
                "kind": "hook",
                "spoken": (
                    "So I will leave you the way we started.\n\n"
                    "(PAUSE 2 seconds)\n\n"
                    "You are not behind. You are one decision away. Make it today. I will "
                    "see you on the inside."
                ),
            }],
        },
    ],
}


def main():
    ap = argparse.ArgumentParser(description="Presenter's Speech teleprompter PDF generator")
    ap.add_argument("--spec", help="path to speech-spec JSON")
    ap.add_argument("--out", default="PRESENTER-SPEECH.pdf", help="output PDF path")
    ap.add_argument("--sample", action="store_true", help="render the built-in stub speech")
    ap.add_argument("--design-system",
                    help="path to design_system.json; injects the locked brand "
                         "accent_hex/headline_font/body_font into the PDF "
                         "(overrides spec.design_system_path if both are given)")
    ap.add_argument("--emit-sample-spec", metavar="PATH",
                    help="write the built-in stub spec to PATH and exit")
    args = ap.parse_args()

    if args.emit_sample_spec:
        with open(args.emit_sample_spec, "w") as f:
            json.dump(SAMPLE_SPEC, f, indent=2)
        print(f"Wrote sample spec to {args.emit_sample_spec}")
        return

    if args.sample:
        spec = dict(SAMPLE_SPEC)
    elif args.spec:
        with open(args.spec) as f:
            spec = json.load(f)
    else:
        ap.error("provide --spec PATH or --sample")

    if args.design_system:
        spec["design_system_path"] = args.design_system

    pdf = SpeechPDF(spec)
    words, secs = pdf.build(args.out)
    rate = pdf.rate
    budget = spec.get("duration_min", 0) * rate
    print(f"Rendered {args.out}  (teleprompter floor {MIN_FONT_PT:.0f}pt)")
    print(f"Total spoken words: {words}  (~{words/rate:.1f} min at {rate:.0f} wpm)")
    if budget:
        delta = (words - budget) / budget * 100 if budget else 0
        print(f"Budget at {spec.get('duration_min')} min: {budget:.0f} words "
              f"(this stub is a short sample, not a full-length script; delta {delta:+.0f}%)")


if __name__ == "__main__":
    main()
