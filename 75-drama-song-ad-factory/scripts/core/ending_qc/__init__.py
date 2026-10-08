"""ending_qc (Part I I5): a clean ending, never "drops off a cliff". stdlib only.

Two halves:
  * with_clean_ending / check_sheet_ending: the song is ASKED for a real
    ending (an [Outro] section plus a final resolved-chord tag in the lyric
    sheet, and ending words in the style text).
  * check_ending: the finished master is MEASURED over its last 2 s: the
    audio level decays, the last sung word is not cut, the picture fades to
    the end card, and the end card (4-5 s) finishes inside the delivery
    limit (target length minus 2 s).
Reason codes: ENDING_ABRUPT_AUDIO, ENDING_CUT_MID_WORD, ENDING_NO_PICTURE_FADE,
ENDING_CARD_LENGTH, ENDING_CARD_PAST_LIMIT, ENDING_TAG_MISSING.
"""
from __future__ import annotations

import array
import re
import wave

TAIL_S = 2.0            # window measured at the end of the master
WINDOW_S = 0.1
DECAY_MAX = 0.35        # last window RMS must be <= 35% of the tail's start
WORD_GAP_S = 0.3        # last sung word ends at least this long before audio end
CARD_MIN_S, CARD_MAX_S = 4.0, 5.0
MIN_FADE_S = 0.3
EARLY_END_S = 2.0       # deliveries finish this early (60 s ad ends at 58 s)
OUTRO_TAG = "[Outro]"
END_TAG = "[Resolve on final chord]"
STYLE_ENDING = "natural resolved ending, final chord rings out and fades"


def with_clean_ending(lyrics, style):
    """Return (lyrics, style) with the ending asked for; no-op if present."""
    if not re.search(r"\[\s*outro", lyrics or "", re.I):
        lyrics = (lyrics or "").rstrip() + "\n\n" + OUTRO_TAG + "\n"
    if not re.search(r"\[\s*(resolve|end)", lyrics, re.I):
        lyrics = lyrics.rstrip() + "\n" + END_TAG + "\n"
    if "resolved ending" not in (style or "").lower():
        style = ((style or "").rstrip(", ") + ", " + STYLE_ENDING).lstrip(", ")
    return lyrics, style


def check_sheet_ending(lyrics, style):
    """[] when the sheet and style ask for an ending, else reason codes."""
    ok = (re.search(r"\[\s*outro", lyrics or "", re.I)
          and re.search(r"\[\s*(resolve|end)", lyrics or "", re.I)
          and "resolved ending" in (style or "").lower())
    return [] if ok else ["ENDING_TAG_MISSING"]


def tail_levels(wav_path, tail_s=TAIL_S, window_s=WINDOW_S):
    """(RMS per window over the last tail_s, audio length s). 16-bit PCM WAV."""
    with wave.open(str(wav_path), "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError("ENDING_INPUT_BAD: 16-bit PCM WAV required")
        n, ch, rate = w.getnframes(), w.getnchannels(), w.getframerate()
        w.setpos(max(0, n - int(tail_s * rate)))
        data = array.array("h", w.readframes(int(tail_s * rate)))
    step = max(1, int(window_s * rate)) * ch
    out = []
    for i in range(0, len(data) - step + 1, step):
        seg = data[i:i + step]
        out.append((sum(s * s for s in seg) / len(seg)) ** 0.5)
    return out, n / float(rate)


def check_ending(wav_path, last_word_end_s, endcard_start_s, endcard_end_s,
                 target_s, picture_fade_s):
    """Measure the ending. Returns {"verdict": PASS|FAIL, "reasons": [...]}.

    last_word_end_s: end of the final sung/spoken word on the timeline.
    endcard_start_s / endcard_end_s: end card window on the video timeline.
    target_s: the ad length asked for (60); limit = target_s - 2.
    picture_fade_s: length of the picture fade into the end card.
    """
    reasons = []
    levels, length = tail_levels(wav_path)
    if not levels or levels[0] <= 0 or levels[-1] > DECAY_MAX * levels[0]:
        reasons.append("ENDING_ABRUPT_AUDIO")
    if last_word_end_s > length - WORD_GAP_S or last_word_end_s > endcard_start_s:
        reasons.append("ENDING_CUT_MID_WORD")
    if picture_fade_s < MIN_FADE_S:
        reasons.append("ENDING_NO_PICTURE_FADE")
    card = endcard_end_s - endcard_start_s
    if not CARD_MIN_S <= card <= CARD_MAX_S:
        reasons.append("ENDING_CARD_LENGTH")
    if endcard_end_s > target_s - EARLY_END_S:
        reasons.append("ENDING_CARD_PAST_LIMIT")
    return {"verdict": "FAIL" if reasons else "PASS", "reasons": reasons,
            "tail_levels": [round(x, 1) for x in levels]}
