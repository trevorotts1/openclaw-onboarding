#!/usr/bin/env python3
"""F7 words-match guard: caption/lyric text equals the script packet words.

Manual Part F F7 (High): captions and sung/spoken words equal the packet
lines; the builder may not rewrite them ("gonna" where the packet says
"going to" fails) and may not invent lines. Done when: caption text vs
packet text differs by zero words.

Comparison is word by word. Normalization follows the repo's existing
text-compare convention (timing_guard._WORD_RE / music_qc.norm): case is
folded, and punctuation is word-boundary noise, not word content —
meaning-bearing tokens (contractions included) must still be identical, so
"gonna" where the packet says "going to" fails and an invented line fails.
No synonym tolerance, no contraction folding, no rewriting: a mismatch is
reported, never repaired. stdlib only, no network, zero paid calls.
"""
from __future__ import annotations

import difflib
import re

CODE = "CAPTION_WORD_MISMATCH"
SCHEMA_VERSION = "blackceo.words-match/f7/v1"
TOOL_VERSION = "0.1.0"

#: Same token rule as timing_guard: alnum runs plus inner apostrophes.
#: Punctuation is split off as word-boundary noise; meaning never is.
_WORD_RE = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?")


def _words(text):
    """Meaning-bearing words of one text: casefolded tokens."""
    return _WORD_RE.findall((text or "").casefold())


def validate_words_match(caption_text, packet_lines):
    """[] when caption words equal packet words in order; else errors.

    caption_text: the caption/lyric text written for the master (str).
    packet_lines: the script's packet lines (list of str).

    Fail-closed: a non-string caption or a non-list-of-strings packet is a
    mismatch itself, never a pass. Returns a list of ``CAPTION_WORD_MISMATCH
    ...`` strings; empty exactly when zero words differ.
    """
    if not isinstance(caption_text, str):
        return ["%s caption_text is not a string (%s)"
                % (CODE, type(caption_text).__name__)]
    if not isinstance(packet_lines, list) or \
            not all(isinstance(line, str) for line in packet_lines):
        return ["%s packet_lines is not a list of strings" % CODE]

    want = _words("\n".join(packet_lines))
    got = _words(caption_text)
    errors = []
    matcher = difflib.SequenceMatcher(a=want, b=got, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag in ("replace", "delete"):
            errors.append("%s word %d: caption %r != packet %r"
                          % (CODE, i1, got[j1:j2], want[i1:i2]))
        elif tag == "insert":
            errors.append("%s invented words after packet word %d "
                          "(caption-only): %r"
                          % (CODE, i1, got[j1:j2]))
    return errors