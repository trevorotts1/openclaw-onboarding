#!/usr/bin/env python3
"""
animated_captions.py - Create animated karaoke-style captions

This script uses FFmpeg's drawtext filter.
Important: drawtext treats ':' as an option separator, so caption text must be escaped.
"""

import argparse
import subprocess
import re
import sys

# T0-59: the animated path parsed the same subtitle file and proceeded on an
# empty cue list, producing a video with a no-op filter chain that was then
# announced as created. Exit code 3 == AF-CAPTION-EMPTY-TRANSCRIPTION, matching
# CAPTION_EMPTY_TRANSCRIPTION_EXIT in Scripts/lib-caption-guard.sh.
EMPTY_TRANSCRIPTION_EXIT = 3


def parse_srt(srt_file):
    """Parse SRT file and return list of (start, end, text) tuples"""
    with open(srt_file, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = r"(\d+)\s+([0-9:,]+) --> ([0-9:,]+)\s+(.+?)(?=\n\d+\s+\n|\Z)"
    matches = re.findall(pattern, content, re.DOTALL)

    captions = []
    for match in matches:
        _, start, end, text = match
        text = text.replace("\n", " ").strip()
        captions.append((start, end, text))

    return captions


def time_to_seconds(time_str):
    """Convert SRT time to seconds"""
    parts = time_str.split(":")
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = float(parts[2].replace(",", "."))
    return hours * 3600 + minutes * 60 + seconds


def escape_drawtext_text(text):
    """
    Escape caption text for FFmpeg drawtext.

    We wrap text in single quotes: text='...'
    - Escape backslashes first
    - Escape ':' because drawtext uses ':' as an option separator
    - Escape single quotes
    """
    text = text.replace("\\", r"\\")
    text = text.replace(":", r"\:")
    text = text.replace("'", r"\'")
    return text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--srt", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    captions = parse_srt(args.srt)

    # T0-59: reject an empty cue list here too. A cue whose text is blank draws
    # nothing, so it is not a caption and must not be counted as one.
    renderable = [(s, e, t) for (s, e, t) in captions if t.strip()]
    if not renderable:
        print(
            "Error: AF-CAPTION-EMPTY-TRANSCRIPTION — %s parsed to %d cue(s) and %d "
            "renderable caption(s)." % (args.srt, len(captions), len(renderable)),
            file=sys.stderr,
        )
        print(
            "  Burning in an empty cue list would produce a video announced as "
            "captioned with no captions in it. Nothing was rendered.",
            file=sys.stderr,
        )
        return EMPTY_TRANSCRIPTION_EXIT
    captions = renderable

    # Create FFmpeg filter complex for animated captions
    filter_parts = []

    for start, end, text in captions:
        start_sec = time_to_seconds(start)
        end_sec = time_to_seconds(end)

        safe_text = escape_drawtext_text(text)

        # Create animated subtitle effect
        filter_parts.append(
            f"drawtext=text='{safe_text}':fontcolor=white:fontsize=24:"
            f"x=(w-text_w)/2:y=h-text_h-50:"
            f"enable='between(t,{start_sec},{end_sec})':"
            f"borderw=2:bordercolor=black"
        )

    # Join filters
    filter_complex = ",".join(filter_parts)

    cmd = [
        "ffmpeg",
        "-i",
        args.input,
        "-vf",
        filter_complex,
        "-c:a",
        "copy",
        args.output,
    ]

    subprocess.run(cmd, check=True)
    print(f"Created: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
