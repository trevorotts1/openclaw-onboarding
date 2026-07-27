#!/usr/bin/env python3
"""
speech_fish_tag.py -- Fish Audio expression tag applicator for presenter speech.

Phase P8.4-FISH-TAG, Step 7 of U012.
Adds S2 bracket-style Fish Audio expression tags to the presenter's speech
markdown so the text-to-speech engine can deliver a nuanced, emotive read.

OWNED BY: Presenter's Speech Writer (ROLE-20), Presentations department.
Consumes PRESENTERS-SPEECH.md, intake.json, slides_copy.md, and the
Fish Audio tags master catalog.  Produces PRESENTERS-SPEECH-FISH-TAGGED.md.

USAGE
-----
  python3 speech_fish_tag.py --run-dir <run_dir>
  python3 speech_fish_tag.py --run-dir <run_dir> --verify-only
  python3 speech_fish_tag.py --run-dir <run_dir> --sample

TAG GRAMMAR (from the role doc)
-------------------------------
  - Pair a physical / vocal tag with at most ONE emotion tag.
  - NEVER stack two emotion tags on the same line.
  - Maximum 2 tags per line unless a specific performance reason demands a
    third (e.g., [laughing][happy][whispering] for a layered moment).
  - Every tag MUST be followed by text to speak on the same line.
  - S2 syntax: [square brackets] with natural-language descriptors.
"""

import argparse
import json
import os
import re
import sys
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


def _tokenize_speech(speech_text: str) -> list:
    """Tokenise the speech markdown into a list of typed tokens.

    Each token is a dict:
        {'type': 'meta'|'header'|'meta_line'|'separator'|'blank'|'cue'|'spoken', 'text': str}

    This preserves every byte of the original so reconstruction is exact.
    """
    tokens = []
    lines_raw = speech_text.splitlines(True)
    current_slide_no = None
    after_meta = False

    for line in lines_raw:
        stripped = line.strip()

        # Slide header
        hdr = re.match(r"^##\s+Slide\s+(\d+)\s+--", stripped)
        if hdr:
            current_slide_no = int(hdr.group(1))
            after_meta = False
            tokens.append({"type": "header", "text": stripped})
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
    """
    classifications = {}
    current_slide = None
    current_stage = "NORMAL"
    current_kind = "normal"

    for tok in tokens:
        if tok["type"] == "header":
            m = re.search(r"Slide\s+(\d+)", tok["text"])
            if m:
                current_slide = int(m.group(1))
                stage_match = re.search(r"\((\w+)\)", tok["text"])
                current_stage = stage_match.group(1).upper() if stage_match else "NORMAL"
                current_kind = "normal"
        elif tok["type"] == "meta_line" and current_slide is not None:
            kind_match = re.search(r"KIND:\s*(\w+)", tok["text"])
            if kind_match:
                current_kind = kind_match.group(1).lower()
            stage = current_stage.upper()
            kind = current_kind.lower()

            if "DROP" in stage or "LADDER" in stage or kind in ("drop", "final", "ladder"):
                classifications[current_slide] = "LADDER_DROP"
            elif "PAIN" in stage or kind == "pain":
                classifications[current_slide] = "PAIN"
            elif "STORY" in stage or kind == "story":
                classifications[current_slide] = "STORY"
            elif stage in ("CLOSE", "CTA") or kind in ("close", "cta"):
                classifications[current_slide] = "CTA_CLOSE"
            elif stage in ("HOOK", "BIG_PROMISE") or kind == "hook":
                classifications[current_slide] = "HOOK_REFRAIN"
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
# Core: rebuild speech with tags
# ---------------------------------------------------------------------------


def _build_tagged_speech(speech_text, intake, slides_copy_text, catalog_text):
    """Produce the full tagged speech markdown.

    Tokenises the entire speech, applies tags to 'spoken' tokens, and
    reconstructs the output line-for-line.  All non-spoken tokens
    (headers, meta, blanks, separators, cues) pass through unchanged.
    """
    tone = intake.get("TONE", "warm and passionate")
    slides_copy_markers = _parse_slides_copy_markers(slides_copy_text)
    hook_refrain_text = _extract_hook_refrain_text(slides_copy_markers)

    tokens = _tokenize_speech(speech_text)
    classifications = _classify_slide_from_tokens(tokens)

    current_slide = None
    output_lines = []

    for tok in tokens:
        if tok["type"] == "header":
            current_slide = None
            m = re.search(r"Slide\s+(\d+)", tok["text"])
            if m:
                current_slide = int(m.group(1))
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

            # Build tag
            if classification == "HOOK_REFRAIN" and is_refrain:
                tag = "[deliberate and measured]"
            elif classification == "PAIN":
                tag = "[empathetic, unhurried]"
            elif classification == "STORY":
                tag = "[storytelling tone]"
            elif classification == "CTA_CLOSE":
                tag = "[confident]"
            else:
                tag = _default_tag(tone)

            tagged_line = f"{tag} {line_text}"
            output_lines.append(tagged_line)

            # For LADDER_DROP slides: inject [long pause] after a price line
            if classification == "LADDER_DROP" and _is_price_line(line_text):
                output_lines.append("[long pause]")

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
