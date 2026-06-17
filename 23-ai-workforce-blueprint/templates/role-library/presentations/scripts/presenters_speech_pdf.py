#!/usr/bin/env python3
"""
presenters_speech_pdf.py — Reusable Presenter's Speech PDF generator.

OWNED BY: Presenter's Speech Writer (ROLE-20), Presentations department.
This is the PDF template referenced by presenters-speech-writer.md SOP 9.2.
It does NOT touch build_deck.py / sync_check.py / PIPELINE-MANIFEST.json (other owners).

WHAT IT PRODUCES
----------------
A visually-appealing, speaker-facing PDF of a WEBINAR speech:
- Colored section headers, one per webinar stage (welcome, credibility, big promise,
  teach, proof, offer, price drops, scarcity, recap, close).
- Every slide is LABELED with its number, headline, and the webinar stage it belongs to.
- Per-slide pacing band: target words, target seconds, running cumulative time.
- Pause cues, hook refrains, OWNER prompts and inline Fish-Audio expression-tag hints
  are visually distinct.
- NO font below 12pt anywhere (hard floor; the presenter reads this live).
- Clean, readable, generous leading and spacing.

INPUT
-----
A JSON "speech spec". See SAMPLE_SPEC at the bottom and `--emit-sample-spec`.
Shape:
{
  "deck_title": str,
  "owner_name": str,
  "company_name": str,
  "duration_min": number,
  "tone": str,
  "hook": str,                       # the verbatim refrain
  "spoken_rate_wpm": 130,            # tunable; default 130
  "brand": {"primary": "#RRGGBB", "accent": "#RRGGBB", "ink": "#RRGGBB"},  # optional
  "stages": [                        # ordered webinar stages
    {
      "stage": "WELCOME",            # one of the canonical stage keys (see STAGE_COLORS)
      "label": "Welcome & Housekeeping",
      "slides": [
        {
          "slide_no": 1,
          "headline": "Welcome",
          "purpose": "Genuine live welcome; qualify the room.",   # optional
          "spoken": "Hello and welcome, everybody...",            # the word-for-word block
          "kind": "normal"           # normal | hook | drop | final | cta | owner_prompt
        }, ...
      ]
    }, ...
  ]
}

USAGE
-----
  python3 presenters_speech_pdf.py --spec speech_spec.json --out Presenters_Speech.pdf
  python3 presenters_speech_pdf.py --sample --out SAMPLE.pdf      # render built-in stub
  python3 presenters_speech_pdf.py --emit-sample-spec spec.json   # write the stub spec

ENFORCEMENT (mirrors SOP 9.2 auto-fails)
- 12pt floor enforced in code (MIN_FONT_PT). Any style below it raises ValueError.
- Word count per slide is computed and shown; total vs budget is printed to stdout.
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
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

MIN_FONT_PT = 12.0  # HARD FLOOR. SOP 9.2: no text below 12pt.

# Canonical webinar-stage palette. Each proven stage gets its own header color so a
# presenter can navigate the live arc at a glance. Keys are the stage identifiers.
STAGE_COLORS = {
    "PRESTART":    "#6B7280",  # slate  — pre-start holding loop
    "WELCOME":     "#0EA5E9",  # sky    — live welcome + housekeeping
    "WHO_FOR":     "#06B6D4",  # cyan   — who this is for / qualify the room
    "HOOK":        "#8B5CF6",  # violet — engagement hook + big promise tee-up
    "CREDIBILITY": "#6366F1",  # indigo — presenter origin story / credibility
    "BIG_PROMISE": "#A855F7",  # purple — the one thing / big promise
    "TEACH":       "#2563EB",  # blue   — teach the framework (the secrets)
    "PROOF":       "#059669",  # emerald— proof / case studies
    "OFFER":       "#D97706",  # amber  — offer + value stack
    "PRICE_DROP":  "#DC2626",  # red    — price drops / anchoring
    "SCARCITY":    "#EA580C",  # orange — scarcity / urgency
    "RECAP":       "#0D9488",  # teal   — recap
    "CLOSE":       "#BE123C",  # rose   — final close / CTA
    "QA":          "#7C3AED",  # violet — live Q&A
}
DEFAULT_STAGE_COLOR = "#334155"

# kind -> small inline badge color for special spoken blocks
KIND_BADGE = {
    "hook":         ("#8B5CF6", "HOOK REFRAIN"),
    "drop":         ("#DC2626", "PRICE DROP"),
    "final":        ("#BE123C", "FINAL PRICE"),
    "cta":          ("#D97706", "CALL TO ACTION"),
    "owner_prompt": ("#0D9488", "OWNER PROMPT"),
}

PAUSE_RE = re.compile(r"\((?:PAUSE|pause)[^)]*\)")
OWNER_RE = re.compile(r"\((?:OWNER|CLIENT)[^)]*\)")
TAG_RE = re.compile(r"\[[^\]]+\]")  # Fish-Audio S2 [bracket] expression-tag hints


def _hex(c):
    return colors.HexColor(c) if isinstance(c, str) else c


def _wc(text):
    """Word count of the spoken text, ignoring cue/tag annotations."""
    stripped = PAUSE_RE.sub(" ", text)
    stripped = OWNER_RE.sub(" ", stripped)
    stripped = TAG_RE.sub(" ", stripped)
    return len([w for w in re.split(r"\s+", stripped.strip()) if w])


def _esc(text):
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def _highlight_spoken(text, accent, pause_col, tag_col):
    """Return reportlab markup: keep words plain, color pause cues / owner prompts / tags."""
    safe = _esc(text)

    def color_span(m, col, bold=True):
        inner = m.group(0)
        b0, b1 = ("<b>", "</b>") if bold else ("", "")
        return f'<font color="{col}">{b0}{inner}{b1}</font>'

    safe = PAUSE_RE.sub(lambda m: color_span(m, pause_col), safe)
    safe = OWNER_RE.sub(lambda m: color_span(m, accent), safe)
    safe = TAG_RE.sub(lambda m: color_span(m, tag_col, bold=False), safe)
    return safe


class SpeechPDF:
    def __init__(self, spec):
        self.spec = spec
        self.rate = float(spec.get("spoken_rate_wpm", 130))
        brand = spec.get("brand", {})
        self.primary = brand.get("primary", "#1E3A8A")
        self.accent = brand.get("accent", "#0D9488")
        self.ink = brand.get("ink", "#1F2933")
        self.muted = "#64748B"
        self.pause_col = "#B45309"   # warm brown for pause cues
        self.tag_col = "#9333EA"     # purple for expression tags
        self._build_styles()

    def _S(self, name, **kw):
        size = kw.get("fontSize", 12)
        if size < MIN_FONT_PT:
            raise ValueError(
                f"Style {name!r} fontSize {size} below 12pt floor (SOP 9.2 auto-fail)."
            )
        leading = kw.pop("leading", size * 1.32)
        return ParagraphStyle(name, parent=self.base, leading=leading, **kw)

    def _build_styles(self):
        ss = getSampleStyleSheet()
        self.base = ss["Normal"]
        self.base.fontName = "Helvetica"
        self.st = {
            "cover_title": self._S("cover_title", fontSize=30, leading=35,
                                   textColor=_hex(self.primary),
                                   fontName="Helvetica-Bold"),
            "cover_sub": self._S("cover_sub", fontSize=15, leading=20,
                                  textColor=_hex(self.muted)),
            "cover_meta": self._S("cover_meta", fontSize=12.5, leading=18,
                                   textColor=_hex(self.ink)),
            "cover_banner": self._S("cover_banner", fontSize=13, leading=18,
                                     textColor=colors.white,
                                     fontName="Helvetica-Bold"),
            "stage_hdr": self._S("stage_hdr", fontSize=18, leading=22,
                                  textColor=colors.white,
                                  fontName="Helvetica-Bold", spaceBefore=4,
                                  spaceAfter=2, leftIndent=8),
            "slide_label": self._S("slide_label", fontSize=13.5, leading=17,
                                    textColor=_hex(self.primary),
                                    fontName="Helvetica-Bold"),
            "purpose": self._S("purpose", fontSize=12, leading=16,
                                textColor=_hex(self.muted),
                                fontName="Helvetica-Oblique"),
            "spoken": self._S("spoken", fontSize=13.5, leading=20,
                               textColor=_hex(self.ink), spaceBefore=4,
                               spaceAfter=4, alignment=TA_LEFT),
            "pacing": self._S("pacing", fontSize=12, leading=15,
                              textColor=_hex(self.muted)),
            "badge": self._S("badge", fontSize=12, leading=14,
                             textColor=colors.white, fontName="Helvetica-Bold"),
            "legend": self._S("legend", fontSize=12, leading=16,
                              textColor=_hex(self.ink)),
            "foot": self._S("foot", fontSize=12, leading=14,
                            textColor=_hex(self.muted)),
        }

    # ---- page furniture -------------------------------------------------
    def _footer(self, canvas, doc):
        canvas.saveState()
        canvas.setFillColor(_hex(self.muted))
        canvas.setFont("Helvetica", 12)
        title = self.spec.get("deck_title", "Presenter's Speech")
        foot = f"Presenter's Speech (speaker-facing) — {title}"
        # Keep the footer text clear of the right-aligned page number.
        max_w = 5.6 * inch
        while foot and canvas.stringWidth(foot, "Helvetica", 12) > max_w:
            foot = foot[:-2]
        if foot != f"Presenter's Speech (speaker-facing) — {title}":
            foot = foot.rstrip() + "…"
        canvas.drawString(0.9 * inch, 0.55 * inch, foot)
        canvas.drawRightString(7.6 * inch, 0.55 * inch, f"Page {doc.page}")
        canvas.setStrokeColor(_hex(self.primary))
        canvas.setLineWidth(2)
        canvas.line(0.9 * inch, 0.75 * inch, 7.6 * inch, 0.75 * inch)
        canvas.restoreState()

    def _stage_band(self, stage_key, label):
        col = _hex(STAGE_COLORS.get(stage_key, DEFAULT_STAGE_COLOR))
        para = Paragraph(_esc(label.upper()), self.st["stage_hdr"])
        t = Table([[para]], colWidths=[6.7 * inch])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), col),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("ROUNDEDCORNERS", [4, 4, 4, 4]),
        ]))
        return t

    def _slide_block(self, stage_key, slide):
        col = _hex(STAGE_COLORS.get(stage_key, DEFAULT_STAGE_COLOR))
        flow = []
        no = slide.get("slide_no", "?")
        headline = slide.get("headline", "")
        label = f"SLIDE {no} &nbsp;|&nbsp; {_esc(headline)}"
        # badge for special kinds
        kind = slide.get("kind", "normal")
        badge_cells = [[Paragraph(label, self.st["slide_label"])]]
        widths = [6.7 * inch]
        if kind in KIND_BADGE:
            bcol, btxt = KIND_BADGE[kind]
            badge = Paragraph(btxt, self.st["badge"])
            bt = Table([[badge]], colWidths=[1.6 * inch])
            bt.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), _hex(bcol)),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]))
            badge_cells = [[Paragraph(label, self.st["slide_label"]), bt]]
            widths = [5.05 * inch, 1.65 * inch]
        head = Table(badge_cells, colWidths=widths)
        head.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (0, 0), 1.5, col),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        flow.append(head)

        purpose = slide.get("purpose")
        if purpose:
            flow.append(Paragraph("Purpose: " + _esc(purpose), self.st["purpose"]))

        spoken = slide.get("spoken", "")
        words = _wc(spoken)
        secs = round(words / self.rate * 60.0, 1)
        markup = _highlight_spoken(spoken, self.accent, self.pause_col, self.tag_col)
        flow.append(Paragraph(markup, self.st["spoken"]))

        pacing = (f'<font color="{col}">▎</font> '
                  f"<b>{words} words</b> &nbsp;~{secs:.0f}s spoken "
                  f"@ {self.rate:.0f} wpm")
        flow.append(Paragraph(pacing, self.st["pacing"]))
        flow.append(Spacer(1, 9))
        return flow, words, secs

    # ---- cover ----------------------------------------------------------
    def _cover(self):
        s = self.spec
        flow = []
        banner = Paragraph("PRESENTER&#39;S SPEECH &nbsp;•&nbsp; WORD-FOR-WORD "
                           "&nbsp;•&nbsp; SPEAKER-FACING", self.st["cover_banner"])
        bt = Table([[banner]], colWidths=[6.7 * inch])
        bt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), _hex(self.primary)),
            ("TOPPADDING", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ]))
        flow.append(bt)
        flow.append(Spacer(1, 26))
        flow.append(Paragraph(_esc(s.get("deck_title", "Webinar Speech")),
                              self.st["cover_title"]))
        flow.append(Spacer(1, 8))
        sub = f"A live webinar presenter script for {_esc(s.get('owner_name','the presenter'))}"
        if s.get("company_name"):
            sub += f" &nbsp;•&nbsp; {_esc(s['company_name'])}"
        flow.append(Paragraph(sub, self.st["cover_sub"]))
        flow.append(Spacer(1, 22))
        flow.append(HRFlowable(width="100%", thickness=1.2,
                               color=_hex(self.muted), spaceAfter=14))

        # metadata table
        total_words = sum(_wc(sl.get("spoken", ""))
                          for st in s.get("stages", []) for sl in st.get("slides", []))
        slide_count = sum(len(st.get("slides", [])) for st in s.get("stages", []))
        est_min = total_words / self.rate
        rows = [
            ["Duration target", f"{s.get('duration_min','?')} min"],
            ["Spoken rate", f"{self.rate:.0f} wpm (tunable)"],
            ["Slides", str(slide_count)],
            ["Tone", s.get("tone", "—")],
            ["Hook refrain", s.get("hook", "—")],
            ["Script length", f"{total_words} words (~{est_min:.1f} min spoken)"],
        ]
        data = [[Paragraph(f"<b>{_esc(k)}</b>", self.st["cover_meta"]),
                 Paragraph(_esc(str(v)), self.st["cover_meta"])] for k, v in rows]
        mt = Table(data, colWidths=[1.9 * inch, 4.8 * inch])
        mt.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, -2), 0.5, _hex("#E2E8F0")),
        ]))
        flow.append(mt)
        flow.append(Spacer(1, 22))

        # legend
        flow.append(Paragraph("<b>How to read this script</b>", self.st["legend"]))
        legend = (
            f'<font color="{self.pause_col}"><b>(PAUSE …)</b></font> = stop and let it land. &nbsp; '
            f'<font color="{self.accent}"><b>(OWNER: …)</b></font> = say your real detail here, never fabricate. &nbsp; '
            f'<font color="{self.tag_col}">[expression tag]</font> = Fish-Audio delivery hint for the audio demo. &nbsp; '
            "Colored band = the webinar stage you are in. &nbsp; "
            "Each slide shows its word count and spoken seconds so you can pace the room."
        )
        flow.append(Paragraph(legend, self.st["legend"]))
        flow.append(Spacer(1, 10))
        flow.append(Paragraph(
            "This is for YOU, the speaker. The slide deck is what the audience sees. "
            "These words are only in your mouth.", self.st["foot"]))
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
        story += self._cover()
        from reportlab.platypus import PageBreak
        story.append(PageBreak())

        total_words = 0
        total_secs = 0.0
        for stage in self.spec.get("stages", []):
            story.append(self._stage_band(stage.get("stage", ""),
                                          stage.get("label", stage.get("stage", ""))))
            story.append(Spacer(1, 8))
            for slide in stage.get("slides", []):
                flow, w, s = self._slide_block(stage.get("stage", ""), slide)
                story += flow
                total_words += w
                total_secs += s
            story.append(Spacer(1, 6))

        doc.build(story)
        return total_words, total_secs


# --------------------------------------------------------------------------
SAMPLE_SPEC = {
    "deck_title": "From Overlooked to Overbooked: The 90-Day Authority Webinar",
    "owner_name": "Jordan Avery",
    "company_name": "Avery Growth Lab",
    "duration_min": 60,
    "tone": "Prolific, passionate, warm, direct",
    "hook": "You are not behind. You are one decision away.",
    "spoken_rate_wpm": 130,
    "brand": {"primary": "#1E3A8A", "accent": "#0D9488", "ink": "#1F2933"},
    "stages": [
        {
            "stage": "WELCOME", "label": "Welcome & Housekeeping",
            "slides": [{
                "slide_no": 1, "headline": "Welcome",
                "purpose": "Genuine live host welcome. Reward people for being here. Get the chat moving.",
                "kind": "normal",
                "spoken": (
                    "[warm and welcoming] Hello and welcome, everybody. Congratulations on taking "
                    "the first step just by being here. (PAUSE 2 seconds) I mean that. You could be "
                    "doing a hundred other things right now, and instead you showed up for your future. "
                    "So before we go one inch further, do me a favor. Drop in the chat where you are "
                    "watching from today. Go ahead, I will wait. [smiling while speaking] I love seeing "
                    "the room fill up. Quick housekeeping: stay to the very end, because what I save for "
                    "the last ten minutes is the part nobody else will give you for free."
                ),
            }],
        },
        {
            "stage": "WHO_FOR", "label": "Who This Is For",
            "slides": [{
                "slide_no": 2, "headline": "Is this you?",
                "purpose": "Qualify the room so the right people lean in and the wrong ones self-select out.",
                "kind": "normal",
                "spoken": (
                    "[calm, grounded authority] Let me tell you exactly who this is for. This is for the "
                    "person who is genuinely good at what they do, and is quietly furious that the world "
                    "has not noticed yet. If you are nodding right now, you are in the right room. "
                    "(PAUSE 2 seconds) And if you are just curious, that is fine too. Stay. Steal everything."
                ),
            }],
        },
        {
            "stage": "CREDIBILITY", "label": "Who I Am (Origin Story)",
            "slides": [{
                "slide_no": 3, "headline": "I was exactly where you are",
                "purpose": "Earn trust through an epiphany-bridge story, not a resume dump.",
                "kind": "owner_prompt",
                "spoken": (
                    "[reflective, looking back] Five years ago I was the best-kept secret in my whole "
                    "industry. Talented, broke, and invisible. (OWNER: say the one true detail about your "
                    "lowest moment here, in your own words.) [vulnerable, almost confessional] And then "
                    "one Tuesday something broke open for me, and I want to give you that exact moment today."
                ),
            }],
        },
        {
            "stage": "BIG_PROMISE", "label": "The One Thing",
            "slides": [{
                "slide_no": 4, "headline": "The big promise",
                "purpose": "State the single belief that, once accepted, makes the rest inevitable.",
                "kind": "hook",
                "spoken": (
                    "[unshakeable confidence] Here is the one thing I need you to believe before you "
                    "leave today. It is not that you need more talent. It is not that you need more time. "
                    "(PAUSE 2 seconds) It is that you are one decision away from being seen. Say it with me. "
                    "You are not behind. You are one decision away."
                ),
            }],
        },
        {
            "stage": "TEACH", "label": "Teach the Framework",
            "slides": [{
                "slide_no": 5, "headline": "Secret #1: The Vehicle",
                "purpose": "Break the false belief about the method. Teach generously.",
                "kind": "normal",
                "spoken": (
                    "[building excitement] So let me hand you the framework. I call it the Authority Loop, "
                    "and it has three moves. Move one: pick one painfully specific person to serve. Not "
                    "everyone. One. Because the riches really are in the niches, and the fastest way to be "
                    "ignored is to talk to everybody at once."
                ),
            }],
        },
        {
            "stage": "PROOF", "label": "Proof & Case Studies",
            "slides": [{
                "slide_no": 6, "headline": "It works for people like you",
                "purpose": "Mini-transformation before the offer. Specific, vivid, true.",
                "kind": "owner_prompt",
                "spoken": (
                    "[confident and factual] Let me show you it is not just me. (OWNER: share one real client "
                    "win with the actual number and the actual timeframe.) [proud but humble] Same framework. "
                    "Ordinary person. Extraordinary result. That could be your story ninety days from now."
                ),
            }],
        },
        {
            "stage": "OFFER", "label": "The Offer & Value Stack",
            "slides": [{
                "slide_no": 7, "headline": "Everything you get",
                "purpose": "Stack the offer one component at a time; anchor the full value.",
                "kind": "normal",
                "spoken": (
                    "[warm and welcoming] So here is everything you get when you join the 90-Day Authority "
                    "program. You get the full Authority Loop course. And you get the live coaching calls. "
                    "And you get the swipe library. (OWNER: confirm the real stack and the real value of each.) "
                    "Add it all up and the honest value is well into five figures."
                ),
            }],
        },
        {
            "stage": "PRICE_DROP", "label": "Price Drop & Anchoring",
            "slides": [{
                "slide_no": 8, "headline": "Your investment today",
                "purpose": "Anchor high, then drop. Honor the live attendees.",
                "kind": "drop",
                "spoken": (
                    "[measured and deliberate] Now here is what I want you to notice. You showed up. You "
                    "stayed live with me. That matters, and I am going to honor it. You will not pay the "
                    "full value today. (PAUSE 3 seconds) Because you are here live, it is a fraction of that. "
                    "(OWNER: state the real anchor price, then the real live price.)"
                ),
            }],
        },
        {
            "stage": "SCARCITY", "label": "Scarcity & Urgency",
            "slides": [{
                "slide_no": 9, "headline": "Why now",
                "purpose": "Honest, specific urgency. Never fake a countdown.",
                "kind": "cta",
                "spoken": (
                    "[urgent but controlled] This price closes when this webinar ends. (OWNER: state the real "
                    "deadline and any real spot limit.) [direct eye-contact energy] Go to the link on your "
                    "screen right now and claim your seat while the door is still open."
                ),
            }],
        },
        {
            "stage": "RECAP", "label": "Recap",
            "slides": [{
                "slide_no": 10, "headline": "What we covered",
                "purpose": "Tie the bow. Remind them of the promise and the path.",
                "kind": "normal",
                "spoken": (
                    "[calm, grounded authority] Let me bring it home. We named who you are, we broke the "
                    "beliefs holding you back, I handed you the Authority Loop, and I showed you the door. "
                    "The only thing left is your decision."
                ),
            }],
        },
        {
            "stage": "CLOSE", "label": "The Close",
            "slides": [{
                "slide_no": 11, "headline": "One decision away",
                "purpose": "Circle back to the hook. End on the verbatim refrain.",
                "kind": "hook",
                "spoken": (
                    "[smiling while speaking] So I will leave you the way we started. (PAUSE 2 seconds) "
                    "You are not behind. You are one decision away. Make it today. I will see you on the inside."
                ),
            }],
        },
    ],
}


def main():
    ap = argparse.ArgumentParser(description="Presenter's Speech PDF generator")
    ap.add_argument("--spec", help="path to speech-spec JSON")
    ap.add_argument("--out", default="Presenters_Speech.pdf", help="output PDF path")
    ap.add_argument("--sample", action="store_true", help="render the built-in stub speech")
    ap.add_argument("--emit-sample-spec", metavar="PATH",
                    help="write the built-in stub spec to PATH and exit")
    args = ap.parse_args()

    if args.emit_sample_spec:
        with open(args.emit_sample_spec, "w") as f:
            json.dump(SAMPLE_SPEC, f, indent=2)
        print(f"Wrote sample spec to {args.emit_sample_spec}")
        return

    if args.sample:
        spec = SAMPLE_SPEC
    elif args.spec:
        with open(args.spec) as f:
            spec = json.load(f)
    else:
        ap.error("provide --spec PATH or --sample")

    pdf = SpeechPDF(spec)
    words, secs = pdf.build(args.out)
    rate = pdf.rate
    budget = spec.get("duration_min", 0) * rate
    print(f"Rendered {args.out}")
    print(f"Total spoken words: {words}  (~{words/rate:.1f} min @ {rate:.0f} wpm)")
    if budget:
        delta = (words - budget) / budget * 100 if budget else 0
        print(f"Budget @ {spec.get('duration_min')} min: {budget:.0f} words "
              f"(this stub is a short sample, not a full-length script; delta {delta:+.0f}%)")


if __name__ == "__main__":
    main()
