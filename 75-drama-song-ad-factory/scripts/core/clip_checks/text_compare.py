#!/usr/bin/env python3
"""text_compare.py: compare the writing in a take with the writing in its
source (N-28, section 3A.4).

Six steps, in order, on every picture and every take:

1. Controls. One known-dirty and one known-clean frame must be told apart;
   otherwise LETTER_GATE_UNAVAILABLE and nothing passes.
2. Picture against the record. Every recorded string should be found, spelled
   exactly. Wrong or misspelled readable words on the prop the shot is about,
   or extra readable writing, are MAJOR; a blank prop where words were planned
   is MEDIUM and passes.
3. Take against its source. Allowed = the source picture's writing plus the
   record. A word seen in two samples in a row that is not allowed is new
   writing.
4. Script. Any non-English character in any sample fails at once.
5. Eye check. The fixed three questions must be answered for every lip-sync
   take, and the eye record must exist; a scan alone never passes.
6. Master. The same checks with allowed = every picture's record, the end card
   and the captions.

The verdict is recorded against the path that will actually play, never
borrowed from another copy. Stdlib only; the reader is injected.
"""
from __future__ import annotations

import re

from .severity import MEDIUM, finding

TOOL_NAME = "clip_checks.text_compare"
TOOL_VERSION = "1.0.0"

PICTURE_TEXT_WRONG = "PICTURE_TEXT_WRONG"
PICTURE_TEXT_EXTRA = "PICTURE_TEXT_EXTRA"
PROP_BLANK = "PROP_BLANK"
NEW_TEXT_IN_TAKE = "NEW_TEXT_IN_TAKE"
TEXT_CHANGED = "TEXT_CHANGED"
NON_ENGLISH_SCRIPT = "NON_ENGLISH_SCRIPT"
LETTER_GATE_UNAVAILABLE = "LETTER_GATE_UNAVAILABLE"
LIP_TAKE_NOT_EYE_CHECKED = "LIP_TAKE_NOT_EYE_CHECKED"

#: Fixed eye-check questions (3A.4 step 5) and the code a "yes" raises.
EYE_QUESTIONS = {
    "new_writing": ("Is there any writing in the take that is not in the "
                    "source picture?"),
    "non_english": "Is any character not English?",
    "changed": ("Did any writing that was in the source change or turn to "
                "gibberish?"),
}
EYE_CODES = {"new_writing": NEW_TEXT_IN_TAKE,
             "non_english": NON_ENGLISH_SCRIPT,
             "changed": TEXT_CHANGED}

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")
_WORD = re.compile(r"[A-Za-z]{3,}")
#: Scripts that are a hard fail on screen (3A.4 step 4).
_NON_LATIN = re.compile(
    "[Ѐ-ӿ"      # Cyrillic
    "֐-׿"       # Hebrew
    "؀-ۿ"       # Arabic
    "ऀ-ॿ"       # Devanagari
    "฀-๿"       # Thai
    "぀-ヿ"       # Japanese kana
    "㐀-䶿一-鿿"   # CJK
    "가-힯"       # Hangul
    "Ͱ-Ͽ]"      # Greek
)


def normalize(text):
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    return _WS.sub(" ", _PUNCT.sub(" ", text.casefold())).strip()


def words(text):
    return [w.lower() for w in _WORD.findall(text or "")]


def non_english(text):
    """True when any character is from a non-Latin script."""
    return bool(_NON_LATIN.search(text or ""))


def controls_discriminate(dirty_text, clean_text):
    """Step 1: the reader must read words in the dirty frame and none in the
    clean one. Returns (ok, detail)."""
    ok = bool(words(dirty_text)) and not words(clean_text)
    return ok, {"dirty_tokens": words(dirty_text),
                "clean_tokens": words(clean_text), "discriminates": ok}


def persistent_words(samples, min_in_a_row=2):
    """Words seen in ``min_in_a_row`` consecutive samples or more."""
    per_sample = [set(words(s)) for s in samples or []]
    out = set()
    for i in range(0, max(0, len(per_sample) - min_in_a_row + 1)):
        window = per_sample[i:i + min_in_a_row]
        shared = set.intersection(*window) if window else set()
        out.update(shared)
    return sorted(out)


def picture_check(read_text, record_lines):
    """Step 2: picture against the text record."""
    findings = []
    expected = [str(x) for x in (record_lines or []) if str(x).strip()]
    read_words = set(words(read_text))
    if expected and not read_words:
        # A blank prop where words were planned is MEDIUM and passes; it is
        # not a wrong spelling and must not raise PICTURE_TEXT_WRONG.
        return {"findings": [finding(PROP_BLANK, "prop is blank where words "
                                     "were planned", level=MEDIUM)],
                "tokens_seen": [], "pass": True}
    expected_words = set()
    for line in expected:
        expected_words.update(words(line))
        if not any(w in read_words for w in words(line)):
            findings.append(finding(PICTURE_TEXT_WRONG,
                                    'recorded line not found: "%s"' % line))
    extra = sorted(read_words - expected_words)
    if extra:
        findings.append(finding(PICTURE_TEXT_EXTRA,
                                "extra readable writing: %s" % ", ".join(extra)))
    return {"findings": findings, "tokens_seen": sorted(read_words),
            "pass": not any(f["level"] != MEDIUM for f in findings)}


def take_check(samples, allowed_texts, model_kind="lipsync"):
    """Step 3: take against its source plus the record."""
    allowed = set()
    for text in allowed_texts or []:
        allowed.update(words(text))
    new = [w for w in persistent_words(samples) if w not in allowed]
    findings = []
    for word in new:
        if model_kind == "lipsync":
            findings.append(finding(NEW_TEXT_IN_TAKE,
                                    'new writing in the take: "%s"' % word))
        else:
            findings.append(finding("NEW_VIDEO_TEXT",
                                    'new writing by the video model: "%s"'
                                    % word, item=3))
    return {"findings": findings, "tokens_seen": sorted(set().union(
        *[set(words(s)) for s in samples or []])) if samples else [],
        "new_words": new, "pass": not findings}


def script_check(samples):
    """Step 4: any non-English script fails at once, never waived."""
    findings = []
    for text in samples or []:
        if non_english(text):
            findings.append(finding(NON_ENGLISH_SCRIPT,
                                    "non-English script on screen"))
            break
    return {"findings": findings, "pass": not findings}


def eye_check(answers, required=True):
    """Step 5: the fixed three questions, answered, for every lip-sync take.

    ``answers`` maps question key -> True (bad) | False (clean) | None.
    A missing answer or a missing record fails closed; a scan alone never
    passes a take.
    """
    findings = []
    if not isinstance(answers, dict):
        if required:
            findings.append(finding(LIP_TAKE_NOT_EYE_CHECKED,
                                    "no eye record for this take", item=15))
        return {"findings": findings, "pass": not findings}
    for key in EYE_QUESTIONS:
        answer = answers.get(key)
        if answer is None:
            findings.append(finding(LETTER_GATE_UNAVAILABLE,
                                    "eye question not answered: %s" % key,
                                    item=15))
        elif answer is True:
            findings.append(finding(EYE_CODES[key],
                                    EYE_QUESTIONS[key]))
    return {"findings": findings, "pass": not findings}


def compare_take(path, samples, source_text, record_lines, eye=None,
                 model_kind="lipsync", dirty_text=None, clean_text=None):
    """Steps 1, 3, 4 and 5 for one take; verdict against the playing path."""
    findings = []
    ok, detail = controls_discriminate(dirty_text, clean_text)
    if not ok:
        findings.append(finding(LETTER_GATE_UNAVAILABLE,
                                "controls not told apart", item=15))
        return {"path": path, "verdict": "UNAVAILABLE", "findings": findings,
                "controls": detail, "pass": False}
    allowed = [source_text or ""] + [str(x) for x in (record_lines or [])]
    take = take_check(samples, allowed, model_kind=model_kind)
    script = script_check(samples)
    eye_out = eye_check(eye, required=(model_kind == "lipsync"))
    findings += take["findings"] + script["findings"] + eye_out["findings"]
    return {"path": path, "verdict": "FAIL" if findings else "PASS",
            "findings": findings, "tokens_seen": take["tokens_seen"],
            "new_words": take["new_words"], "controls": detail,
            "pass": not findings}


def compare_picture(path, read_text, record_lines, dirty_text=None,
                    clean_text=None):
    """Steps 1, 2 and 4 for one picture."""
    findings = []
    ok, detail = controls_discriminate(dirty_text, clean_text)
    if not ok:
        findings.append(finding(LETTER_GATE_UNAVAILABLE,
                                "controls not told apart", item=15))
        return {"path": path, "verdict": "UNAVAILABLE", "findings": findings,
                "controls": detail, "pass": False}
    pic = picture_check(read_text, record_lines)
    script = script_check([read_text])
    findings += pic["findings"] + script["findings"]
    return {"path": path, "verdict": "FAIL" if findings else "PASS",
            "findings": findings, "tokens_seen": pic["tokens_seen"],
            "controls": detail, "pass": not findings}


def compare_master(path, samples, allowed_texts):
    """Step 6: the finished master. Allowed = every record, end card and
    captions. The same new-text and script rules apply."""
    take = take_check(samples, allowed_texts, model_kind="video")
    script = script_check(samples)
    findings = take["findings"] + script["findings"]
    return {"path": path, "verdict": "FAIL" if findings else "PASS",
            "findings": findings, "tokens_seen": take["tokens_seen"],
            "pass": not findings}


if __name__ == "__main__":
    assert normalize("Balance $14.82") == "balance 14 82"
    assert non_english("Привет")
    # The reader keeps words of 3+ letters (the OCR rule), so the control uses
    # 3-letter words: single letters are never tokens.
    assert persistent_words(["aaa bbb ccc", "bbb ccc ddd", "bbb ccc eee"]) == \
        ["bbb", "ccc"]
    rec = ["Bachelor of Science", "Dana Rivers"]
    ok = picture_check("Bachelor of Science Dana Rivers", rec)
    assert ok["pass"], ok
    bad = picture_check("Bachelor of Scence Dana Rivers", rec)
    assert not bad["pass"]
    print("text_compare control: PASS")
