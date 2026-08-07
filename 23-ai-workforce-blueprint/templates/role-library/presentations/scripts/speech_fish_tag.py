#!/usr/bin/env python3
"""
speech_fish_tag.py -- Fish Audio expression tag applicator for presenter speech.

Phase P8.4-FISH-TAG, Step 7 of U012.
Adds S2 bracket-style Fish Audio expression tags to the presenter's speech
markdown so the text-to-speech engine can deliver a nuanced, emotive read.

OWNED BY: Presenter's Speech Writer (ROLE-20), Presentations department.
Consumes PRESENTERS-SPEECH.md, intake.json, slides_copy.md, and the
Fish Audio tags master catalog.  Produces PRESENTERS-SPEECH-FISH-TAGGED.md.

EXPRESSIVE TAGGING (GAUNTLET LOOP 2 + RICH READ-DIRECTOR PALETTES)
-------------------------------------------------------------------
The tagger emits RICH, stage-appropriate reader tags — large per-stage palettes
(10-14 tags each) that blend VERIFIED emotion cues, COMPOSED instructional
descriptors (feeling + direction, FISH-READER-TAG-LIBRARY.md §2.5/2.8/2.9),
INTENSITY MODIFIERS (very/super/increasingly, §2.4), and DYNAMIC PROSODY levers
(slow down / low voice / speed up, §2.11). Rotation is DETERMINISTIC — seeded by
stage + slide index (zlib.crc32, stable across runs/hosts) — and an anti-repeat
guard guarantees consecutive blocks never reuse the same tag, even across slide
boundaries. [emphasis] lands on price/promise/CTA words in OFFER, SCARCITY, CTA
and LADDER_DROP beats; [pause]/[long pause]/[short pause] are placed
strategically per stage (before refrains, before the crescendo turn, around the
price, at story turns). Webinar-framing sections (`## Section ... (WEBINAR
FRAMING)`) are classified into WELCOME / QNA / CRESCENDO palettes so the framing
read is as alive as the deck.

Reference palettes: FISH-READER-TAG-LIBRARY.md in the presentations fish-audio/
dir (a SOURCE, not a limit — S2 is open-domain).
Output ALWAYS satisfies verify_strip_equals_source: tags are added, never words
changed. The audio executor consumes this FISH-TAGGED file (--tagged-speech) so
the tags reach the Fish API — the root-cause fix for flat audio.

USAGE
-----
  python3 speech_fish_tag.py --run-dir <run_dir>
  python3 speech_fish_tag.py --run-dir <run_dir> --verify-only
  python3 speech_fish_tag.py --run-dir <run_dir> --sample

TAG GRAMMAR (from the role doc + FISH-READER-TAG-LIBRARY.md)
-----------------------------------------------------------
  - Emotion cue at the START of the sentence it governs; tone/sound cues anywhere.
  - Stack max 3 cues per sentence (e.g. [sad][whispering] ...).
  - Every tag MUST be followed by text to speak on the same line.
  - S2 syntax: [square brackets] with natural-language descriptors (open-domain).
  - Pauses ([pause]/[long pause]) are qualitative; the audio executor splices
    EXACT silence (1-5 s) at the ffmpeg stage. (OWNER: ...) notes are dropped.
"""

import argparse
import json
import os
import re
import sys
import zlib
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# PUBLIC module-level function  (must be importable by tests)
# ---------------------------------------------------------------------------


def verify_strip_equals_source(tagged_text: str, source_text: str) -> bool:
    """Return True iff stripping all [bracket] and (paren) tags from
    *tagged_text* yields word-for-word identical output to *source_text*,
    after normalising whitespace in both strings.

    This is the LOAD-BEARING gate.  If it ever returns False the tagged
    file is corrupt and must NOT be shipped.
    """
    # Strip all [bracket] tags from BOTH sides so cues like [PAUSE] and
    # [BREATHE] in the original speech are not counted as source words
    # that the stripped tagged text would miss.
    tagged_stripped = re.sub(r"\[[^]]*\]", "", tagged_text)
    source_stripped = re.sub(r"\[[^]]*\]", "", source_text)
    # Strip all (parenthetical) tags from BOTH sides -- covers legacy S1
    # tags and director's cues like (PAUSE 2 seconds), (OWNER: ...).
    tagged_stripped = re.sub(r"\([^)]*\)", "", tagged_stripped)
    source_stripped = re.sub(r"\([^)]*\)", "", source_stripped)
    # Collapse any sequence of whitespace (including newlines) to a single
    # space, then strip leading / trailing whitespace.
    tagged_norm = re.sub(r"\s+", " ", tagged_stripped).strip()
    source_norm = re.sub(r"\s+", " ", source_stripped).strip()
    return tagged_norm == source_norm


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fish_tags_catalog_path() -> Path:
    return Path(__file__).resolve().parent.parent / "fish-audio" / "FISH-AUDIO-TAGS-MASTER.md"


def _read_text(path: Path) -> str:
    """Return file contents as a string, or '' if missing."""
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError):
        return ""


def _read_json(path: Path) -> dict:
    """Return parsed JSON, or {} if missing / unparseable."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Slide marker parsing from slides_copy.md
# ---------------------------------------------------------------------------


_SLIDE_BLOCK_RE = re.compile(r"^\s*SLIDE\s+(\d+)", re.MULTILINE | re.IGNORECASE)
_SLIDE_H2_RE = re.compile(r"^##\s+Slide\s+(\d+)", re.MULTILINE)


def _parse_slides_copy_markers(slides_copy_text: str) -> dict:
    """Parse slides_copy.md and return a dict mapping slide-number (int) ->
    dict of marker -> value.

    Looks for:
      LADDER: <value>
      PURPOSE: <value>
      HOOK_REFRAIN: <text>
    inside each slide's content block.
    """
    markers: dict = {}
    blocks = _SLIDE_BLOCK_RE.split(slides_copy_text)
    if len(blocks) <= 1:
        blocks = _SLIDE_H2_RE.split(slides_copy_text)

    i = 1
    while i + 1 < len(blocks):
        try:
            slide_no = int(blocks[i].strip())
        except ValueError:
            i += 2
            continue
        content = blocks[i + 1]
        slide_markers: dict = {}
        for key in ("LADDER", "PURPOSE", "HOOK_REFRAIN"):
            m = re.search(rf"{key}:\s*(.+?)(?:\n|$)", content, re.IGNORECASE)
            if m:
                slide_markers[key.upper()] = m.group(1).strip()
        if slide_markers:
            markers[slide_no] = slide_markers
        i += 2
    return markers


# ---------------------------------------------------------------------------
# Speech tokeniser
# ---------------------------------------------------------------------------


def _header_slide_stage(text: str, section_counter: list):
    """Return (slide_no, stage) for a header line, or (None, None).

    Handles BOTH deck slide headers (`## Slide N -- Title (STAGE)`) and
    webinar-framing section headers (`## Section LABEL -- STAGE (WEBINAR
    FRAMING)`). Framing sections have no Slide N number, so they receive a
    synthetic slide number from *section_counter* (a single-element list,
    mutable so the tokenizer, classifier and builder all see the SAME numbering).
    """
    m = re.match(r"^##\s+Slide\s+(\d+)\s+--", text)
    if m:
        slide_no = int(m.group(1))
        stage_match = re.search(r"\((\w+)\)", text)
        stage = stage_match.group(1).upper() if stage_match else "NORMAL"
        return slide_no, stage
    sec = re.match(
        r"^##\s+Section\s+\S+\s+--\s+(\S+)", text, re.IGNORECASE)
    if sec:
        slide_no = section_counter[0]
        section_counter[0] += 1
        return slide_no, sec.group(1).upper()
    return None, None


def _tokenize_speech(speech_text: str) -> list:
    """Tokenise the speech markdown into a list of typed tokens.

    Each token is a dict:
        {'type': 'meta'|'header'|'meta_line'|'separator'|'blank'|'cue'|'spoken',
         'text': str}
    Header tokens also carry 'slide' (int) and 'stage' (str) so downstream
    classification/rebuild never has to re-parse header text — framing sections
    (which have no Slide N number) get the same synthetic numbering everywhere.

    This preserves every byte of the original so reconstruction is exact.
    """
    tokens = []
    lines_raw = speech_text.splitlines(True)
    current_slide_no = None
    after_meta = False
    # Webinar-framing sections (`## Section <LABEL> -- <STAGE> (WEBINAR FRAMING)`)
    # have no Slide N number, so the tagger assigns synthetic slide numbers from
    # a high base that can never collide with real deck slides. This lets the
    # QNA / CRESCENDO palettes engage with the same deterministic rotation.
    section_counter = [1000]

    for line in lines_raw:
        stripped = line.strip()

        # Slide header OR webinar-framing section header (shared parser).
        slide_no, stage = _header_slide_stage(stripped, section_counter)
        if slide_no is not None:
            current_slide_no = slide_no
            after_meta = False
            tokens.append({"type": "header", "text": stripped,
                           "slide": slide_no, "stage": stage})
            continue

        # Metadata line within a slide body
        if current_slide_no is not None and not after_meta:
            if re.match(r"^>\s*STAGE:", stripped):
                after_meta = True
                tokens.append({"type": "meta_line", "text": stripped})
                continue

        # Separator
        if stripped == "---":
            tokens.append({"type": "separator", "text": "---"})
            continue

        # Blank line
        if stripped == "":
            tokens.append({"type": "blank", "text": ""})
            continue

        # Cue line (director's note, not spoken)
        if re.match(r"^\[(?:PAUSE|BREATHE|BREAK)\]", stripped, re.IGNORECASE):
            tokens.append({"type": "cue", "text": stripped})
            continue
        if re.fullmatch(r"\([^)]+\)", stripped):
            tokens.append({"type": "cue", "text": stripped})
            continue

        # If we're past the meta line, this is a spoken line
        if after_meta and current_slide_no is not None:
            tokens.append({"type": "spoken", "text": stripped})
        else:
            # Preamble -- title block lines before the first slide
            tokens.append({"type": "meta", "text": stripped})

    return tokens


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def _classify_slide_from_tokens(tokens: list) -> dict:
    """Walk tokens and derive slide classification from stage/kind info.

    Returns dict {slide_no: classification}.

    Handles the deck stages (WELCOME / PAIN / STORY / HOOK_REFRAIN / TEACH /
    PROOF / OFFER / SCARCITY / CTA_CLOSE / LADDER_DROP) AND the webinar-framing
    stage names emitted by webinar_intro_outro.py — "QNA" (and "Q&A", "QA")
    map to the QNA palette, "CRESCENDO" (and "CLOSE" with KIND framing) map to
    the CRESCENDO palette, and the "WELCOME" framing section reuses the
    WELCOME palette. This keeps the tagger's own output aligned with the
    framing sections the synthesizer injects.
    """
    classifications = {}
    current_slide = None
    current_stage = "NORMAL"
    current_kind = "normal"

    for tok in tokens:
        if tok["type"] == "header":
            # slide/stage are stamped by the tokenizer (shared numbering for
            # deck slides AND webinar-framing sections).
            if tok.get("slide") is not None:
                current_slide = tok["slide"]
                current_stage = tok.get("stage") or "NORMAL"
                current_kind = "normal"
        elif tok["type"] == "meta_line" and current_slide is not None:
            kind_match = re.search(r"KIND:\s*(\w+)", tok["text"])
            if kind_match:
                current_kind = kind_match.group(1).lower()
            stage_match_meta = re.search(r"STAGE:\s*(\S+)", tok["text"])
            stage = stage_match_meta.group(1).upper() if stage_match_meta else current_stage.upper()
            kind = current_kind.lower()

            if "DROP" in stage or "LADDER" in stage or kind in ("drop", "final", "ladder"):
                classifications[current_slide] = "LADDER_DROP"
            elif stage in ("QNA", "QA", "Q&A", "CHAT_QNA") or kind in ("qna", "qa"):
                classifications[current_slide] = "QNA"
            elif stage in ("CRESCENDO", "CRESCENDO_CLOSE", "PEP") \
                    or (kind == "framing" and stage in ("CLOSE", "CTA", "OUTRO")):
                classifications[current_slide] = "CRESCENDO"
            elif "PAIN" in stage or kind == "pain":
                classifications[current_slide] = "PAIN"
            elif "STORY" in stage or kind == "story":
                classifications[current_slide] = "STORY"
            elif stage in ("CLOSE", "CTA") or kind in ("close", "cta"):
                classifications[current_slide] = "CTA_CLOSE"
            elif stage in ("HOOK", "BIG_PROMISE") or kind == "hook":
                classifications[current_slide] = "HOOK_REFRAIN"
            elif stage in ("WELCOME", "OPEN", "INTRO") or kind == "welcome":
                classifications[current_slide] = "WELCOME"
            elif stage in ("TEACH", "VALUE", "HOW", "MECHANISM", "EDUCATE") \
                    or kind in ("teach", "value", "how"):
                classifications[current_slide] = "TEACH"
            elif stage in ("PROOF", "RESULTS", "SOCIAL_PROOF", "WALL_OF_WINS") \
                    or kind in ("proof", "results"):
                classifications[current_slide] = "PROOF"
            elif stage in ("OFFER", "PITCH", "PRICE", "VALUE_STACK") \
                    or kind in ("offer", "pitch"):
                classifications[current_slide] = "OFFER"
            elif stage in ("SCARCITY", "URGENCY", "DEADLINE") \
                    or kind in ("scarcity", "urgency"):
                classifications[current_slide] = "SCARCITY"
            else:
                classifications[current_slide] = "DEFAULT"

    return classifications


# ---------------------------------------------------------------------------
# Tag helpers
# ---------------------------------------------------------------------------


def _is_hook_refrain_line(line, hook_refrain_text=""):
    """Return True if *line* reads like a hook refrain."""
    stripped = line.strip()
    if not stripped:
        return False
    if hook_refrain_text:
        norm = re.sub(r"[^\w\s]", "", stripped.lower())
        norm_refrain = re.sub(r"[^\w\s]", "", hook_refrain_text.lower())
        if len(norm) >= 10 and len(norm_refrain) >= 10:
            if norm_refrain in norm:
                return True
            words_line = set(norm.split())
            words_ref = set(norm_refrain.split())
            if words_line and words_ref:
                overlap = len(words_line & words_ref) / len(words_line | words_ref)
                if overlap > 0.55:
                    return True
    return False


def _is_price_line(line):
    """Return True if *line* likely mentions a price / monetary amount."""
    return bool(re.search(r"\$\d[\d,.]*|price|cost|invest|payment|fee",
                          line, re.IGNORECASE))


def _default_tag(tone):
    """Build the default tag from intake TONE, falling back to [warm, credible]."""
    if not tone or tone == "warm and passionate":
        return "[warm, credible]"
    clean = tone.strip().lower()
    if len(clean) <= 40 and not clean.startswith("["):
        return f"[{clean}]"
    return "[warm, credible]"


def _extract_hook_refrain_text(slides_copy_markers):
    """Extract HOOK_REFRAIN from slides_copy.md markers."""
    for markers in slides_copy_markers.values():
        if "HOOK_REFRAIN" in markers:
            return markers["HOOK_REFRAIN"]
    return ""


# ---------------------------------------------------------------------------
# Expressive tag palettes (GAUNTLET LOOP 2 + richer read-director palettes)
#
# Each classification carries a LARGE ROTATING palette of S2/S2.1-Pro reader
# cues so consecutive lines inside a slide NEVER share a tag (the "minimal"
# flat-tagging defect — one tag on every line produces a monotone read). Tags
# come from FISH-AUDIO-TAGS-MASTER.md, the composed descriptor library in
# section L, and FISH-READER-TAG-LIBRARY.md §2 (all open-domain, valid on S2).
#
# Each palette blends, per stage:
#   - strong COMPOSED instructional descriptors (feeling + direction, §2.5/2.8/2.9)
#   - INTENSITY MODIFIERS (very / super / increasingly / slightly, §2.4)
#   - DYNAMIC PROSODY levers (slow down / speed up / low voice / volume up, §2.11)
# Stacked entries (two bracketed cues) stay within the max-3-cues-per-sentence
# rule and are stripped cleanly by verify_strip_equals_source.
#
# Rotation is DETERMINISTIC: the start offset is seeded from the stage key +
# slide index (_stage_slide_seed), so the same stage on the same slide always
# produces the same tag sequence, while different slides of a stage diverge.
# An anti-repeat guard in the caller keeps consecutive blocks from sharing a tag
# even across slide boundaries.
#
# Verified source tags: [confident] [calm] [excited] [happy] [sad] [empathetic]
#   [proud] [grateful] [curious] [hopeful] [determined] [nostalgic]
#   [whispering] [emphasis] [pause] [long pause] [short pause]
#   [slow down] [speed up] [low voice] [soft voice] [volume up]
# Composed (open-domain S2 descriptors): [warm and welcoming] [reflective, looking back]
#   [vulnerable, almost confessional] [calm, grounded authority] [deliberate and measured]
#   [understated, letting the numbers speak] [building excitement] [urgent but controlled]
#   [sincere, warm] [smiling while speaking] [a knowing smile]
#   [barely contained enthusiasm] [rising energy] [quietly triumphant]
#   [speaking slowly, almost hesitant] [slowing down for weight] [quickening pace]
# ---------------------------------------------------------------------------
_EXPRESSIVE_PALETTES = {
    "WELCOME": [
        "[warm and welcoming]",
        "[smiling while speaking]",
        "[genuinely caring]",
        "[warm, credible]",
        "[grateful and sincere]",
        "[upbeat and bright]",
        "[like talking to an old friend]",
        "[deliberate and measured]",
        "[soft, intimate]",
        "[genuinely enthusiastic]",
    ],
    "PAIN": [
        "[empathetic, unhurried]",
        "[quiet, sincere]",
        "[like talking to an old friend]",
        "[genuinely caring]",
        "[soft and intimate]",
        "[serious, compassionate]",
        "[quietly concerned]",
        "[gentle encouragement]",
        "[slightly anxious]",
        "[understanding, patient]",
    ],
    "STORY": [
        "[reflective, looking back]",
        "[vulnerable, almost confessional]",
        "[nostalgic]",
        "[wistful]",
        "[bittersweet]",
        "[hopeful rising]",
        "[a knowing smile]",
        "[quiet before a turn]",
        "[soft, intimate]",
        "[slightly wistful]",
        "[emotionally moved]",
        "[determined]",
    ],
    "HOOK_REFRAIN": [
        "[deliberate and measured]",
        "[calm, grounded authority]",
        "[confident, building]",
        "[unshakeable confidence]",
        "[steady, certain]",
        "[matter-of-fact]",
        "[leaning in, conspiratorial]",
        "[lowering voice for emphasis]",
        "[slow down, deliberate]",
        "[measured and deliberate]",
        "[direct, assured]",
    ],
    "TEACH": [
        "[calm, clear]",
        "[helpful, generous]",
        "[measured and deliberate]",
        "[matter-of-fact]",
        "[steady, certain]",
        "[calm, grounded authority]",
        "[gently encouraging]",
        "[clinical precision]",
        "[clear and patient]",
        "[slow down, clear]",
        "[warm, knowledgeable]",
    ],
    "PROOF": [
        "[confident and factual]",
        "[understated, letting the numbers speak]",
        "[proud but humble]",
        "[quietly proud]",
        "[matter-of-fact]",
        "[clinical precision]",
        "[steady, certain]",
        "[satisfied]",
        "[proud]",
        "[modest and grounded]",
    ],
    "OFFER": [
        "[building excitement]",
        "[excited]",
        "[delighted]",
        "[barely contained enthusiasm]",
        "[rising energy]",
        "[upbeat and bright]",
        "[celebratory]",
        "[contagious energy]",
        "[very excited]",
        "[excited tone]",
        "[fast and punchy]",
        "[confident]",
        "[super happy]",
        "[joyful]",
    ],
    "SCARCITY": [
        "[urgent but controlled]",
        "[serious, direct]",
        "[quickening pace]",
        "[in a hurry tone]",
        "[time-pressure tone]",
        "[clipped and direct]",
        "[speed up]",
        "[serious warning]",
        "[no-nonsense]",
        "[determined]",
        "[increasingly urgent]",
    ],
    "CTA_CLOSE": [
        "[sincere, warm]",
        "[confident, reassuring]",
        "[grateful]",
        "[warm and welcoming]",
        "[calm, grounded authority]",
        "[speaking slowly, almost hesitant]",
        "[slowing down for weight]",
        "[grateful and sincere]",
        "[warm and reassuring]",
        "[soft voice]",
        "[low voice]",
        "[quietly triumphant]",
        "[reassuring]",
    ],
    "QNA": [
        "[confident]",
        "[calm, grounded authority]",
        "[warm, credible]",
        "[helpful, generous]",
        "[steady, certain]",
        "[matter-of-fact]",
        "[genuinely caring]",
        "[direct, assured]",
        "[clear and patient]",
        "[warm and helpful]",
    ],
    "CRESCENDO": [
        "[passionate]",
        "[uplifting]",
        "[determined]",
        "[building to a crescendo]",
        "[inspiring]",
        "[rising energy]",
        "[hopeful rising]",
        "[celebratory]",
        "[sincere, warm]",
        "[joyful]",
        "[powerful and certain]",
        "[quietly triumphant]",
    ],
    "LADDER_DROP": [
        "[calm, grounded authority]",
        "[slowing down for weight]",
        "[understated, letting the numbers speak]",
        "[quietly triumphant]",
        "[measured and deliberate]",
        "[low voice]",
        "[steady, certain]",
        "[a knowing smile]",
        "[confident and quiet]",
    ],
    "DEFAULT": [
        "[warm and credible]",
        "[confident]",
        "[warm, credible]",
        "[calm, grounded authority]",
        "[measured and deliberate]",
        "[genuinely caring]",
    ],
}

# Words that carry emphasis in a price / promise / CTA line. When present, the
# tagger inserts [emphasis] before the word so the number or the action lands.
_EMPHASIS_WORDS = (
    "today", "now", "nineteen", "ninety", "one", "first", "exact", "only",
    "never", "free", "thousand", "payment", "inside", "decision", "right",
    "tonight", "immediately", "start", "join", "worth", "best", "choose",
    "difference", "exactly", "guarantee",
)

# Stage + line-hash seed: deterministic rotation so the SAME stage on the SAME
# slide always produces the same tag sequence (stable output), while different
# slides of a stage diverge. Uses zlib.crc32 (stable across runs / hosts —
# builtin hash() is randomized per process and must NOT be used here).


def _stage_seed(classification: str, slide_no: int) -> int:
    """Return a deterministic integer seed for (stage, slide index)."""
    return zlib.crc32(f"{classification}|{slide_no}".encode("utf-8"))


def _rotate_seeded(palette, slide_seed, line_idx):
    """Deterministic rotation within a stage/slide: the palette walk starts at a
    stage+slide-derived offset (so two different slides of the same stage diverge)
    and advances by line_idx with a coprime stride for non-adjacent variety."""
    if not palette:
        return ""
    n = len(palette)
    # stride coprime to n (always 1 for prime-ish lengths; else pick one)
    stride = 1
    for s in (2, 3, 5, 7, 11, 13):
        if n % s != 0:
            stride = s
            break
    start = slide_seed % n
    return palette[(start + line_idx * stride) % n]


def _emphasize_line(line_text):
    """Return line_text with [emphasis] injected before the first high-value word
    (price / promise / CTA trigger). If none matches, return line_text unchanged.
    Safe: [emphasis] is a reader tag, stripped by verify_strip_equals_source."""
    lowered = line_text.lower()
    for w in _EMPHASIS_WORDS:
        # word-boundary, not inside another word (e.g. 'someone' vs 'one')
        m = re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", lowered)
        if m:
            pos = m.start()
            # find the real start of that word in the ORIGINAL case text
            word_match = re.search(
                r"\S*" + re.escape(w) + r"\S*", line_text, re.IGNORECASE)
            if word_match:
                return line_text[:word_match.start()] + "[emphasis] " + line_text[word_match.start():]
    return line_text


# Dynamic-prosody and pacing levers applied strategically per stage (not on
# every line — seasoning, not the meal). Each is a bracket reader tag the
# executor strips/splices exactly like the other pauses.
_LEAD_IN_PAUSE = "[long pause]"       # the single biggest line of the section
_PAUSE = "[pause]"
_SHORT_PAUSE = "[short pause]"



# ---------------------------------------------------------------------------
# Core: rebuild speech with tags
# ---------------------------------------------------------------------------


def _build_tagged_speech(speech_text, intake, slides_copy_text, catalog_text):
    """Produce the full tagged speech markdown.

    Tokenises the entire speech, applies expressive (rotating, stage-appropriate)
    tags to 'spoken' tokens, injects [pause]/[long pause] at dramatic points and
    [emphasis] on high-value words, then reconstructs the output line-for-line.
    All non-spoken tokens (headers, meta, blanks, separators, cues) pass through
    unchanged. The output ALWAYS satisfies verify_strip_equals_source — tags are
    added, never words changed.
    """
    tone = intake.get("TONE", "warm and passionate")
    slides_copy_markers = _parse_slides_copy_markers(slides_copy_text)
    hook_refrain_text = _extract_hook_refrain_text(slides_copy_markers)

    tokens = _tokenize_speech(speech_text)
    classifications = _classify_slide_from_tokens(tokens)

    current_slide = None
    output_lines = []
    # per-slide tag rotation counters so consecutive lines differ
    line_index = {"n": 0}
    last_slide_no = None
    last_tag_emitted = None

    for tok in tokens:
        if tok["type"] == "header":
            current_slide = None
            if tok.get("slide") is not None:
                current_slide = tok["slide"]
                if current_slide != last_slide_no:
                    line_index["n"] = 0
                    last_slide_no = current_slide
            output_lines.append(tok["text"])

        elif tok["type"] == "meta_line":
            output_lines.append(tok["text"])

        elif tok["type"] == "separator":
            output_lines.append(tok["text"])

        elif tok["type"] == "blank":
            output_lines.append("")

        elif tok["type"] == "cue":
            output_lines.append(tok["text"])

        elif tok["type"] == "spoken":
            if current_slide is None:
                output_lines.append(tok["text"])
                continue

            classification = classifications.get(current_slide, "DEFAULT")
            line_text = tok["text"]
            is_refrain = (
                classification == "HOOK_REFRAIN"
                and _is_hook_refrain_line(line_text, hook_refrain_text)
            )

            # Build a stage-appropriate tag via DETERMINISTIC seeded rotation:
            # same stage + same slide => same sequence; different slides diverge.
            palette = _EXPRESSIVE_PALETTES.get(classification,
                                               _EXPRESSIVE_PALETTES["DEFAULT"])
            slide_seed = _stage_seed(classification, current_slide)
            tag = _rotate_seeded(palette, slide_seed, line_index["n"])
            line_index["n"] += 1

            # Anti-repeat: a consecutive block NEVER reuses the previous block's
            # tag (across slide boundaries too) when the palette allows.
            if tag == last_tag_emitted and len(palette) > 1:
                tag = _rotate_seeded(palette, slide_seed + 1, line_index["n"])
            last_tag_emitted = tag

            tagged_line = f"{tag} {line_text}"

            # Strategic [emphasis] on price/promise/CTA words across the offer,
            # scarcity, close and ladder-drop beats (not just price lines).
            emphasize_now = (
                _is_price_line(line_text)
                or classification in ("CTA_CLOSE", "LADDER_DROP")
                or (classification == "SCARCITY" and line_index["n"] % 2 == 0)
                or (classification == "OFFER" and line_index["n"] % 3 == 0)
            )
            if emphasize_now:
                tagged_line = _emphasize_line(tagged_line)

            # ---- Strategic [pause]/[long pause] placement per stage ----
            # Price lines: the number must land. Long pause after the reveal.
            if _is_price_line(line_text):
                output_lines.append(tagged_line)
                output_lines.append(
                    "[long pause]" if classification == "LADDER_DROP" else "[pause]")
                continue

            # Hook / promise lines: a beat BEFORE the refrain so it lands.
            if classification == "HOOK_REFRAIN" and is_refrain:
                output_lines.append("[pause]")
                output_lines.append(tagged_line)
                continue

            # CTA / close: a short pause after the final directive.
            if classification == "CTA_CLOSE":
                output_lines.append(tagged_line)
                output_lines.append("[short pause]")
                continue

            # Crescendo (webinar framing): the biggest line gets a long pause
            # BEFORE it so the turn lands, then a beat after.
            if classification == "CRESCENDO" and line_index["n"] == 1:
                output_lines.append("[long pause]")
                output_lines.append(tagged_line)
                continue

            # Welcome / Q&A framing: an opening beat to settle the listener.
            if classification in ("WELCOME", "QNA") and line_index["n"] == 1:
                output_lines.append("[pause]")
                output_lines.append(tagged_line)
                continue

            # Story: a beat at the emotional turn (a pause before a hopeful line).
            if classification == "STORY" and line_index["n"] % 3 == 0:
                output_lines.append("[pause]")
                output_lines.append(tagged_line)
                continue

            output_lines.append(tagged_line)

        elif tok["type"] == "meta":
            output_lines.append(tok["text"])

    return "\n".join(output_lines)


# ---------------------------------------------------------------------------
# --verify-only mode
# ---------------------------------------------------------------------------


def _verify_mode(run_dir, use_sample=False):
    """Re-read the tagged file and source file, run verify_strip_equals_source,
    and exit with the appropriate code.

    Returns 0 on equality, 4 on any difference.
    """
    tagged_path = run_dir / "working" / "deliverables" / "PRESENTERS-SPEECH-FISH-TAGGED.md"
    source_path = run_dir / "working" / "deliverables" / "PRESENTERS-SPEECH.md"

    tagged_text = _read_text(tagged_path)
    if use_sample:
        source_text = _use_sample_speech()
    else:
        source_text = _read_text(source_path)

    if not tagged_text:
        print(f"ERROR: Tagged file missing or empty: {tagged_path}", file=sys.stderr)
        return 4
    if not source_text:
        print(f"ERROR: Source file missing or empty: {source_path}", file=sys.stderr)
        return 4

    result = verify_strip_equals_source(tagged_text, source_text)
    if result:
        print("VERIFY PASS: Tagged speech matches source word-for-word "
              "after stripping tags.")
        return 0
    else:
        tagged_stripped = re.sub(r"\[[^]]*\]", "", tagged_text)
        tagged_stripped = re.sub(r"\([^)]*\)", "", tagged_stripped)
        tagged_norm = re.sub(r"\s+", " ", tagged_stripped).strip()
        source_stripped = re.sub(r"\[[^]]*\]", "", source_text)
        source_stripped = re.sub(r"\([^)]*\)", "", source_stripped)
        source_norm = re.sub(r"\s+", " ", source_stripped).strip()
        tagged_words = tagged_norm.split()
        source_words = source_norm.split()
        max_len = max(len(tagged_words), len(source_words))
        first_diff = None
        for idx in range(max_len):
            tw = tagged_words[idx] if idx < len(tagged_words) else "<MISSING>"
            sw = source_words[idx] if idx < len(source_words) else "<MISSING>"
            if tw != sw:
                first_diff = (idx, tw, sw)
                break
        if first_diff:
            idx, tw, sw = first_diff
            print(f"VERIFY FAIL: First difference at word index {idx}: "
                  f"tagged='{tw}' vs source='{sw}'")
        else:
            print(f"VERIFY FAIL: Word count differs. "
                  f"Tagged has {len(tagged_words)} words, "
                  f"source has {len(source_words)} words.")
        return 4


# ---------------------------------------------------------------------------
# --sample mode helper
# ---------------------------------------------------------------------------


def _use_sample_speech():
    """Import and return the built-in SAMPLE_SPEECH_MD from build_teleprompter."""
    _scripts = str(Path(__file__).resolve().parent)
    if _scripts not in sys.path:
        sys.path.insert(0, _scripts)
    from build_teleprompter import SAMPLE_SPEECH_MD
    return SAMPLE_SPEECH_MD


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser(
        description="Speech Fish Audio Tag applicator "
                    "-- Phase P8.4-FISH-TAG (Step 7, U012)",
    )
    ap.add_argument(
        "--run-dir", required=True,
        help="Path to the run directory "
             "(contains working/copy/ and working/deliverables/)",
    )
    ap.add_argument(
        "--verify-only", action="store_true",
        help="Only verify existing tagged output against source; "
             "write nothing.",
    )
    ap.add_argument(
        "--sample", action="store_true",
        help="Use the built-in sample speech (SAMPLE_SPEECH_MD) as the "
             "source speech.",
    )
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        print(f"ERROR: --run-dir must be an existing directory: {run_dir}",
              file=sys.stderr)
        sys.exit(2)

    # --verify-only path
    if args.verify_only:
        sys.exit(_verify_mode(run_dir, use_sample=args.sample))

    # Determine paths
    speech_path = run_dir / "working" / "deliverables" / "PRESENTERS-SPEECH.md"
    intake_path = run_dir / "working" / "copy" / "intake.json"
    slides_copy_path = run_dir / "working" / "copy" / "slides_copy.md"
    catalog_path = _fish_tags_catalog_path()
    output_path = run_dir / "working" / "deliverables" / "PRESENTERS-SPEECH-FISH-TAGGED.md"

    # Load inputs
    if args.sample:
        speech_text = _use_sample_speech()
        print(f"[speech_fish_tag] Using built-in SAMPLE_SPEECH_MD "
              f"({len(speech_text)} chars)")
    else:
        speech_text = _read_text(speech_path)
        if not speech_text:
            print(f"ERROR: Speech file missing or empty: {speech_path}",
                  file=sys.stderr)
            sys.exit(2)

    intake = _read_json(intake_path)
    slides_copy_text = _read_text(slides_copy_path)
    catalog_text = _read_text(catalog_path)

    # Log what we found
    tone = intake.get("TONE", "warm and passionate")
    print(f"[speech_fish_tag] TONE from intake.json: {tone}")
    slides_copy_markers = _parse_slides_copy_markers(slides_copy_text)
    print(f"[speech_fish_tag] Slides with extra markers from slides_copy.md: "
          f"{len(slides_copy_markers)}")
    hook_refrain_text_local = _extract_hook_refrain_text(slides_copy_markers)
    if hook_refrain_text_local:
        print(f"[speech_fish_tag] HOOK_REFRAIN text: "
              f"{hook_refrain_text_local[:80]}...")

    print(f"[speech_fish_tag] Speech has {len(speech_text)} chars; "
          f"catalog has {len(catalog_text)} chars")

    # Build tagged output
    tagged = _build_tagged_speech(speech_text, intake,
                                  slides_copy_text, catalog_text)

    # Floor check: 2,048 bytes minimum
    tagged_bytes = len(tagged.encode("utf-8"))
    print(f"[speech_fish_tag] Tagged output: {tagged_bytes} bytes "
          f"(floor: 2048)")
    if tagged_bytes < 2048:
        print(f"ERROR: Tagged output is {tagged_bytes} bytes, "
              f"below the 2,048-byte floor.",
              file=sys.stderr)
        sys.exit(3)

    # Verification gate
    if not verify_strip_equals_source(tagged, speech_text):
        # Debug: find the first difference
        tagged_stripped = re.sub(r"\[[^]]*\]", "", tagged)
        tagged_stripped = re.sub(r"\([^)]*\)", "", tagged_stripped)
        tagged_norm_dbg = re.sub(r"\s+", " ", tagged_stripped).strip()
        source_norm_dbg = re.sub(r"\s+", " ", speech_text).strip()
        twords = tagged_norm_dbg.split()
        swords = source_norm_dbg.split()
        for idx in range(max(len(twords), len(swords))):
            tw = twords[idx] if idx < len(twords) else "<MISSING>"
            sw = swords[idx] if idx < len(swords) else "<MISSING>"
            if tw != sw:
                ctx_s = max(0, idx - 3)
                ctx_e = min(max(len(twords), len(swords)), idx + 4)
                print(f"  First diff at word index {idx}: tagged='{tw}' vs source='{sw}'",
                      file=sys.stderr)
                print(f"  context: {' '.join(twords[ctx_s:ctx_e])}",
                      file=sys.stderr)
                break
        print("ERROR: verify_strip_equals_source FAILED -- tagged text "
              "does not match source word-for-word after stripping tags.",
              file=sys.stderr)
        sys.exit(4)

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(tagged, encoding="utf-8")
    print(f"[speech_fish_tag] Wrote {output_path} ({tagged_bytes} bytes)")

    print("[speech_fish_tag] PASS -- tagged speech written and verified.")


if __name__ == "__main__":
    main()
