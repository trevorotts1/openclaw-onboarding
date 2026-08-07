#!/usr/bin/env python3
"""
webinar_intro_outro.py — Webinar framing layer for presenter speech (Feature L2-H).

WHY THIS EXISTS
---------------
The department's presenter speeches read as flat narration: Slide 1 starts cold
("Have you ever felt..."), there is no welcome, no housekeeping, no attendee
greeting, no chat Q&A, and the ending is a soft fade instead of a crescendo. A
REAL webinar has a host. This module pre-generates the three framing sections a
host speaks, Fish S2/S2.1-Pro tagged so they reach the TTS engine:

  1. WELCOME / INTRO   (~5 min,  ~650 words) — greeting, housekeeping,
     made-up attendee first names, a light joke, chat prompts, and the frame:
     the problem (friction to buy), why it matters now, and the three outcomes.
  2. CHAT Q&A          (~2 min,  ~260 words) — the presenter answers plausible
     attendee questions confidently (proves expertise), then an email CTA.
  3. CRESCENDO CLOSE   (~3 min,  ~390 words) — an emotional pep-speech / call to
     action. Lifts the energy, rallies the audience, closes on a high note and
     names the "boulder" (the achievement) the listener is moving today.

Total: ~10 minutes of webinar framing added to the ~30-minute deck.

EXPRESSION TAGS (rotating per stage)
------------------------------------
Fish Audio S2/S2.1-Pro reads [bracket] natural-language reader tags. Tags are
ROTATED within a stage so consecutive lines never read flat (the same defect the
GAUNTLET LOOP 2 fix addressed for slide content):
  - WELCOME:  [warm and credible] / [warm and welcoming] / [smiling while speaking]
  - Q&A:      [confident] / [calm, grounded authority] / [warm, credible]
  - CLOSE:    [passionate] / [uplifting] / [determined] / [building to a crescendo]
Pauses ([pause]/[long pause]) are placed at dramatic beats; the audio executor
(synthesize_full_speech.py) splices EXACT measured silence for them. [emphasis]
stresses the word that follows.

INTEGRATION
-----------
synthesize_full_speech.py passes --webinar-intro-outro and the framing sections
are injected INTO THE FISH-TAGGED synthesis input (in memory) — the intro is
spoken before Slide 1, the Q&A + crescendo close after the last slide. The
on-disk UNTAGGED PRESENTERS-SPEECH.md (the word-count gate, the teleprompter and
the webinar timing track) is left untouched, so the deck-only timing contract
stays exact.

Section markers
---------------
Each framing section carries a `## Section <LABEL> -- <STAGE> (WEBINAR FRAMING)`
header. `extract_deck_body()` strips exactly those sections so the existing
verify_strip_equals_source deck gate keeps passing (framing words are NOT part of
the deck's word-for-word contract).

USAGE
-----
  # Print the three sections with word counts + build a reference rewritten speech
  python3 webinar_intro_outro.py --sample

  # Rewrite an existing FISH-TAGGED deck into a full webinar speech
  python3 webinar_intro_outro.py \
      --tagged-speech /path/PRESENTERS-SPEECH-FISH-TAGGED.md \
      --out-reference /path/PRESENTERS-SPEECH-FISH-TAGGED-WEBINAR.md
"""

import argparse
import os
import re
import sys
from typing import List, Optional, Tuple

# Directory that holds this module and its sibling pipeline modules.
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Word budgeting (SOP 9.1 math: words = minutes * wpm)
# ---------------------------------------------------------------------------
WELCOME_WPM = 130
INTRO_TARGET_MIN = 5.0
QA_TARGET_MIN = 2.0
CLOSE_TARGET_MIN = 3.0
INTRO_TARGET_WORDS = int(INTRO_TARGET_MIN * WELCOME_WPM)   # 650
QA_TARGET_WORDS = int(QA_TARGET_MIN * WELCOME_WPM)         # 260
CLOSE_TARGET_WORDS = int(CLOSE_TARGET_MIN * WELCOME_WPM)   # 390
TOLERANCE = 0.12  # +/-12% on the word targets

# ---------------------------------------------------------------------------
# Rotating Fish S2 reader-tag palettes (composed descriptors, valid on S2
# open-domain — see FISH-AUDIO-TAGS-MASTER.md section L).
# ---------------------------------------------------------------------------
WELCOME_TAGS = [
    "[warm and credible]",
    "[warm and welcoming]",
    "[smiling while speaking]",
    "[warm, credible]",
    "[deliberate and measured]",
    "[building excitement]",
]
QA_TAGS = [
    "[confident]",
    "[calm, grounded authority]",
    "[warm, credible]",
    "[confident]",
]
CLOSE_TAGS = [
    "[passionate]",
    "[uplifting]",
    "[determined]",
    "[building to a crescendo]",
    "[inspiring]",
    "[sincere, warm]",
]

# ---------------------------------------------------------------------------
# Prose — one entry per spoken paragraph (a blank-line separated block in the
# deck). Written for direct address, no em dashes, straight apostrophes.
# ---------------------------------------------------------------------------
WELCOME_PROSE = [
    "Hello everyone, and welcome. I am so glad you made the time to be here today. "
    "Whether you have been building your business for ten years or you are just "
    "getting serious about it, you are in exactly the right place.",

    "Quick bit of housekeeping before we start. This session is being recorded, and I "
    "see in the chat that a few of you asked if the recording can be shared. "
    "Absolutely, and yes. The replay goes out within twenty four hours, so if you "
    "step away or your connection blips, you will not miss a thing.",

    "I see Stephanie just arrived. Welcome, Stephanie, so good to have you. And "
    "Thomas from Washington, I can see you. Good to have you with us. Jill, Marcus, "
    "David, Sarah, if you are settling in, welcome. Some of you I know, some of you I "
    "am meeting for the first time, and that is exactly what today is for.",

    "Here is a quick confession to break the ice. I have been on more webinars than I "
    "can count where the presenter talks at you for an hour and then tries to sell "
    "you something you never asked for. I promise you, that is not what today is. "
    "Today is a working session. You are going to leave with something you can "
    "actually use.",

    "And one more thing before we dive in. My team told me I should tell you this "
    "webinar will change your life. I will settle for changing the way you look at "
    "your offer. If you laugh once and learn something real, we have done our job. "
    "[chuckling] Ha, ha.",

    "Before we get into the teaching, I want to hear from you. Put in the chat where "
    "you are joining from today. City, state, country, wherever you are. And more "
    "importantly, tell me the number one thing you want to get out of this session. "
    "What is the one thing that, if you took it home today, would make this hour "
    "worth it for you?",

    "While you are typing that, let me give you a second prompt, because I want this "
    "to be useful to you specifically. What is the one thing that has been holding "
    "your business back? Not the thing you say out loud. The honest thing. The one "
    "you think about at two in the morning. Put that in the chat too. I read every "
    "single one.",

    "Here is what we are going to talk about today, and I want to set the frame "
    "clearly. The problem is friction to buy. It is not your product, and it is not "
    "your pricing. It is the invisible resistance between a prospect who wants to "
    "say yes and the moment they actually do. That gap is quietly costing businesses "
    "like yours real money, every single day. And by the end of today, that gap is "
    "going to have a name, and you are going to know exactly how to close it.",

    "And here is why it matters right now. The market has changed. People are more "
    "distracted, more skeptical, and more impatient than ever. Your customers are "
    "not comparing you to your direct competitor. They are comparing you to how easy "
    "it was to buy from somewhere else. The business that makes it easy wins.",

    "By the end of today, you will have three things. You will understand exactly "
    "where the friction hides in your offer. You will have a proven framework for "
    "stripping it away, step by step. And you will know what to do first, this week, "
    "to start making buying from you feel effortless. You will walk away with a "
    "clear action plan you can start tonight, not someday.",

    "We have a lot to cover, and I am excited to walk through it with you. So grab a "
    "pen, open the chat, and let us get started. Here we go.",
]

QA_PROSE = [
    "Before we wrap the teaching, I want to take a few minutes for your questions, "
    "because the chat has been busy and I love it. Keep them coming.",

    "Jill from Florida asks, will this work for a service business, or is it just "
    "for products? Great question, Jill. This works even better for services. A "
    "product has one checkout. A service has a whole journey, the inquiry, the "
    "call, the proposal, the follow up. Every one of those steps is a chance for "
    "friction. When you smooth that path, service businesses see some of the "
    "fastest wins, because the friction is usually spread across so many touch "
    "points.",

    "Thomas from Washington asks, how long before we see real results? Honest "
    "answer. Most of our clients see a meaningful shift in two to four weeks, once "
    "they remove the first two or three biggest friction points. You do not need to "
    "fix everything at once. You need to find the one step where people are falling "
    "out and remove it. That is where the leverage is.",

    "Marcus asks, do I have to redo my whole website? No, and I would not want you "
    "to. Friction is rarely about a redesign. It is usually about one obvious "
    "thing. A confusing form, a buried price, a checkout that takes too long. Find "
    "that one thing, fix it, and you will feel it immediately.",

    "Any other questions? I want to make sure you do not leave with anything "
    "unanswered. Send them to the address on the screen, and I will personally get "
    "back to you within one business day. I mean that.",
]

CLOSE_PROSE = [
    "I want you to take a breath, because we are at the end, and I need you to hear "
    "this part with a clear head and an open heart.",

    "Think about why you showed up today. You did not sign up for a webinar. You "
    "showed up because something in your business, in your life, is not quite "
    "right, and you know it. You have been carrying that weight for a long time. "
    "You have been working hard, doing the right things, and still watching too "
    "many of the right people walk away.",

    "Here is what you know now that you did not know when you joined. It was never "
    "about working harder. It was never about a better product or a slicker ad. It "
    "is about friction. The invisible wall between a person who wants to say yes "
    "and the moment they do. And you now know exactly how to tear that wall down.",

    "That boulder you have been pushing uphill, the one that has exhausted you, the "
    "one that has kept you from the growth you deserve, that boulder has a name "
    "now. It is friction. And boulders move. One push at a time, one removed step "
    "at a time, one effortless checkout at a time, that boulder starts to roll, "
    "and once it is rolling, it does not stop.",

    "Picture it. A customer lands on your page, and instead of hesitating, they "
    "feel relief. They feel understood. They feel safe. And they say yes, not "
    "because you pressured them, but because you made it easy. That is not a "
    "fantasy. That is a decision away.",

    "The only thing standing between you and that business is the decision to "
    "start. Not to be perfect. Not to fix everything. To start. To remove one piece "
    "of friction this week. To look at your offer with new eyes. To stop waiting "
    "for the right moment, because the right moment is right now.",

    "So here is my ask, and I do not make it lightly. Take what you learned today "
    "and use it. Today. Open your offer tonight and find the one thing that is "
    "making people hesitate. Remove it. Watch what happens. Because the business "
    "you want is not on the other side of harder. It is on the other side of "
    "easier.",

    "Thank you for being here. Thank you for trusting me with your hour. You have "
    "the map. You have the moment. Now go build the business that makes saying yes "
    "effortless. I will be right here cheering you on.",
]

# ---------------------------------------------------------------------------
# Tag assembly — rotate the palette per paragraph, add pauses at dramatic beats,
# add [emphasis] before high-value words.
# ---------------------------------------------------------------------------

def strip_tags(text: str) -> str:
    """Remove all Fish reader tags (bracket + paren) from *text*, preserving
    every real spoken word. This mirrors speech_fish_tag.verify_strip_equals_source
    so the same words are compared on both the tagged and untagged sides."""
    stripped = re.sub(r"\[[^\]]*\]", "", text)
    stripped = re.sub(r"\([^)]*\)", "", stripped)
    return stripped


def word_count(text: str) -> int:
    """Count real spoken words (bracket tags stripped)."""
    stripped = strip_tags(text)
    return len([w for w in stripped.split() if w])


def _assemble(lines: List[str], palette: List[str],
              pause_after: Optional[Tuple[int, ...]] = None,
              pause_before: Optional[Tuple[int, ...]] = None,
              emphasis: Optional[dict] = None) -> List[str]:
    """Tag + pace a list of prose paragraphs.

    - each paragraph gets palette[i % len(palette)] so consecutive lines differ;
    - pause_before/pause_after are paragraph indices that get a standalone
      [pause]/[long pause] line (the executor converts these to measured silence);
    - emphasis maps paragraph-index -> list of words to wrap in [emphasis].
    Returns the assembled list of markdown lines (paragraphs + pause cues).
    """
    pause_before = pause_before or ()
    pause_after = pause_after or ()
    emphasis = emphasis or {}
    out: List[str] = []
    for i, para in enumerate(lines):
        if i in pause_before:
            out.append("[pause]")
        tag = palette[i % len(palette)]
        line = para
        for w in emphasis.get(i, []):
            m = re.search(r"(?<![A-Za-z])" + re.escape(w) + r"(?![A-Za-z])", line, re.IGNORECASE)
            if m:
                # find the real word span in the ORIGINAL line, insert [emphasis] before it
                span = re.search(r"\S*" + re.escape(w) + r"\S*", line, re.IGNORECASE)
                if span:
                    line = line[:span.start()] + "[emphasis] " + line[span.start():]
        out.append(f"{tag} {line}")
        if i in pause_after:
            out.append("[pause]")
    return out


# ---------------------------------------------------------------------------
# Public generators — return the body text (paragraphs + tags, one per line).
# ---------------------------------------------------------------------------

def generate_intro() -> str:
    """~5 min welcome / housekeeping / greet / chat prompts / frame. Returns the
    Fish-tagged body (no section header)."""
    lines = _assemble(
        WELCOME_PROSE,
        WELCOME_TAGS,
        pause_after=(1,),           # after housekeeping
        pause_before=(7,),          # before "here is what we are going to talk about"
        emphasis={7: ["friction to buy"], 8: ["wins"], 10: ["excited"]},
    )
    return "\n".join(lines)


def generate_qa() -> str:
    """~2 min chat Q&A — the presenter answers three plausible attendee questions
    confidently, then an email CTA."""
    lines = _assemble(
        QA_PROSE,
        QA_TAGS,
        pause_after=(1, 3),
        emphasis={2: ["two", "four"], 4: ["personally"]},
    )
    return "\n".join(lines)


def generate_crescendo_close() -> str:
    """~3 min emotional pep-speech / call to action. Lifts energy, rallies the
    audience, names the boulder, closes on a high note."""
    lines = _assemble(
        CLOSE_PROSE,
        CLOSE_TAGS,
        pause_before=(4,),          # a beat before "Picture it"
        pause_after=(2, 6),         # let the reveals land
        emphasis={4: ["decision"], 6: ["Today"], 7: ["effortless"]},
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section markdown builders
# ---------------------------------------------------------------------------

def _section_markdown(label: str, stage: str, body: str) -> str:
    """Wrap a tagged body in a `## Section ... (WEBINAR FRAMING)` header + meta so
    consumers can identify (and extract_deck_body can strip) the framing sections."""
    words = word_count(body)
    secs = round(words / (WELCOME_WPM / 60.0))
    header = f"## Section {label} -- {stage}  (WEBINAR FRAMING)"
    meta = f"> STAGE: {stage}  KIND: framing  BUDGET: {words}w  ACTUAL: {words}w  SECONDS: {secs}s"
    return f"{header}\n{meta}\n\n{body}\n"


def build_framing_markdown() -> str:
    """Return all three framing sections as markdown (welcome / qa / close),
    already Fish-tagged and word-budgeted."""
    parts = [
        _section_markdown("WELCOME", "WELCOME", generate_intro()),
        _section_markdown("QNA", "QNA", generate_qa()),
        _section_markdown("CLOSE", "CLOSE", generate_crescendo_close()),
    ]
    return "\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# Inject / strip framing
# ---------------------------------------------------------------------------

_FRAMING_HEADER_RE = re.compile(r"^##\s+Section\b.*\(WEBINAR\s+FRAMING\).*$", re.MULTILINE | re.IGNORECASE)
_SLIDE_HEADER_RE = re.compile(r"^##\s+Slide\s+\d+\b", re.MULTILINE)


def extract_deck_body(speech_md: str) -> str:
    """Remove every `## Section ... (WEBINAR FRAMING)` block from *speech_md*,
    returning only the deck body (headers + meta + slide spoken text). Slide
    content is preserved byte-for-byte; framing is separated from the deck by
    blank lines (inject_framing never uses a `---` rule for that boundary), so
    the round-trip is exact."""
    lines = speech_md.splitlines(True)
    out: List[str] = []
    skip = False
    for line in lines:
        if _FRAMING_HEADER_RE.match(line):
            skip = True
            continue
        if skip:
            # a framing block ends at the next heading
            if re.match(r"^#{1,6}\s", line):
                skip = False
                out.append(line)
            continue
        out.append(line)
    return "".join(out)


def inject_framing(speech_md: str, framing_md: Optional[str] = None) -> str:
    """Insert the webinar framing into *speech_md*.

    - the WELCOME section is placed BEFORE the first `## Slide N` header;
    - the Q&A and CLOSE sections are placed AFTER the last slide.
    The deck's slide content and metadata are preserved byte-for-byte. Framing is
    separated from the deck by BLANK LINES (never a `---` rule) so
    extract_deck_body can round-trip the deck exactly.
    Returns *speech_md* unchanged if no slide headers exist.
    """
    framing_md = framing_md or build_framing_markdown()
    m = _SLIDE_HEADER_RE.search(speech_md)
    if not m:
        return speech_md
    head = speech_md[: m.start()].rstrip()
    body = speech_md[m.start():].rstrip()

    # split framing into welcome (first block) vs qa+close (remainder)
    blocks = [b for b in framing_md.split("\n---\n\n")]
    welcome = blocks[0] if blocks else ""
    tail_blocks = "\n\n".join(blocks[1:])

    out = head + "\n\n" + welcome + "\n\n" + body
    if tail_blocks:
        out += "\n\n" + tail_blocks
    return out.rstrip() + "\n"


def rewrite_webinar_speech(tagged_speech_md: str, framing_md: Optional[str] = None) -> str:
    """Build the full webinar speech: framing + existing tagged deck content.

    *tagged_speech_md* is the FISH-TAGGED deck (tags already on slide content).
    Returns the complete Fish-tagged webinar speech markdown."""
    return inject_framing(tagged_speech_md, framing_md)


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify_sections() -> dict:
    """Verify the three framing sections hit their word budgets and rotate tags.
    Returns a dict of {section: {"words": int, "target": int, "tags": list}}."""
    report = {}
    cases = [
        ("welcome", generate_intro(), INTRO_TARGET_WORDS, WELCOME_TAGS),
        ("qa", generate_qa(), QA_TARGET_WORDS, QA_TAGS),
        ("close", generate_crescendo_close(), CLOSE_TARGET_WORDS, CLOSE_TAGS),
    ]
    for name, body, target, palette in cases:
        w = word_count(body)
        used = sorted({re.match(r"\[([^\]]*)\]", line).group(0) for line in body.splitlines()
                       if re.match(r"^\s*\[", line)})
        report[name] = {
            "words": w,
            "target": target,
            "within_band": target * (1 - TOLERANCE) <= w <= target * (1 + TOLERANCE),
            "tags_used": used,
            "n_distinct_tags": len(used),
        }
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Webinar framing layer (Feature L2-H): welcome / Q&A / crescendo close.",
    )
    ap.add_argument("--sample", action="store_true",
                    help="Print the three generated framing sections + verification.")
    ap.add_argument("--tagged-speech", default=None,
                    help="Path to a FISH-TAGGED deck speech (## Slide N format).")
    ap.add_argument("--out-reference", default=None,
                    help="Where to write the full rewritten webinar speech "
                         "(framing + existing tagged deck).")
    ap.add_argument("--verify-only", action="store_true",
                    help="Only print the word-count / tag-rotation verification.")
    args = ap.parse_args()

    if args.sample:
        print(build_framing_markdown())
        print("\n" + "=" * 64)
        print("VERIFICATION")
        for name, r in verify_sections().items():
            print(f"  {name:8s} words={r['words']} target={r['target']} "
                  f"in-band={r['within_band']} distinct-tags={r['n_distinct_tags']} "
                  f"tags={','.join(r['tags_used'])}")
        return 0

    if args.verify_only:
        ok = True
        for name, r in verify_sections().items():
            print(f"  {name:8s} words={r['words']} target={r['target']} "
                  f"in-band={r['within_band']} distinct-tags={r['n_distinct_tags']}")
            ok = ok and r["within_band"] and r["n_distinct_tags"] >= 2
        print("OVERALL:", "PASS" if ok else "FAIL")
        return 0 if ok else 1

    if args.tagged_speech and args.out_reference:
        md = open(args.tagged_speech, "r", encoding="utf-8").read()
        rewritten = rewrite_webinar_speech(md)
        with open(args.out_reference, "w", encoding="utf-8") as f:
            f.write(rewritten)
        # Import extract_spoken from the synthesis executor (same scripts dir) so
        # the report counts ONLY spoken words — never headers, meta, or separators.
        sys.path.insert(0, _SCRIPTS_DIR)
        from synthesize_full_speech import extract_spoken
        deck_body = extract_deck_body(rewritten)
        deck_spoken_words = word_count(extract_spoken(deck_body))
        total_spoken_words = word_count(extract_spoken(rewritten))
        framing_spoken_words = total_spoken_words - deck_spoken_words
        print(f"[webinar_intro_outro] Wrote rewritten webinar speech -> {args.out_reference}")
        print(f"[webinar_intro_outro] {len(rewritten)} chars | "
              f"{deck_spoken_words} deck spoken words + "
              f"{framing_spoken_words} framing spoken words = "
              f"{total_spoken_words} total spoken words")
        return 0

    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
