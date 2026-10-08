#!/usr/bin/env python3
"""H7 protected names + approved-words captions (Part H, Kiesett Stop Stale).

Failure this prevents: Suno was handed "the house went still" where the
packet said "Stale" (136 request files), Suno sang it, and the caption copied
the sheet. Four rules, one module, stdlib only, no network, $0:

1. BUILD gate  - ``check_sheet`` : the lyric sheet may not change a protected
   name (character/brand, e.g. Stale, Stop Stale) or rewrite a packet line.
2. TAKE gate   - ``check_sung_names`` : a take where the singer's words show a
   protected name sung wrong is rejected (words check).
3. CAPTIONS    - ``build_captions`` : text is the approved sheet; only the
   times come from the Suno timestamps. Speech-to-text is never a text source.
4. QC          - ``check_captions`` : any caption mismatch fails, protected
   names named in the failure.
5. SPELLING    - ``check_spelling`` (I1) : every caption word must be a real
   word (bundled dictionary) or a protected word (names, brands, the client's
   website); an unknown word fails with the word shown. ``check_website``
   requires the client's exact web address, verbatim, in lyrics, captions and
   the end card.

Comparison is word by word, case folded, punctuation ignored, section tags
such as ``[Verse]`` ignored. No synonym tolerance: a mismatch is reported,
never repaired. Self-contained (no import of words_match) so the packaged
999 copy, which predates words_match, can ship it unchanged.
"""
from __future__ import annotations

import difflib
import gzip
import os
import re

TOOL_VERSION = "1.0.0"
CODE_SHEET = "PROTECTED_NAME_CHANGED"
CODE_PACKET = "PACKET_LINE_REWRITTEN"
CODE_SUNG = "PROTECTED_NAME_SUNG_WRONG"
CODE_CAPTION = "CAPTION_MISMATCH"
CODE_SOURCE = "CAPTION_SOURCE_NOT_SHEET"
CODE_SPELL = "CAPTION_MISSPELLED"
CODE_WEBSITE = "WEBSITE_NOT_VERBATIM"
CODE_NO_DICT = "SPELLCHECK_DICTIONARY_MISSING"

#: The only text source a caption may come from.
CAPTION_TEXT_SOURCE = "approved-lyric-sheet"

_WORD_RE = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?")
_TAG_RE = re.compile(r"\[[^\]\n]*\]")


def _tokens(text):
    return _WORD_RE.findall(_TAG_RE.sub(" ", text or "").casefold())


def _lines(value):
    """str -> its lines; list -> itself; line dicts -> their text."""
    if isinstance(value, str):
        value = value.splitlines()
    return [x.get("text", "") if isinstance(x, dict) else str(x)
            for x in (value or [])]


def protected_list(brief):
    """Protected names of a brief: protected_names + characters + brands
    + product_name (strings or {name: ...} dicts). Order kept, no dupes."""
    brief = brief or {}
    out, seen = [], set()
    for key in ("protected_names", "characters", "brands", "website"):
        for item in ([brief.get(key)] if key == "website" else brief.get(key) or []):
            name = item.get("name") if isinstance(item, dict) else item
            if isinstance(name, str) and _tokens(name) and \
                    tuple(_tokens(name)) not in seen:
                seen.add(tuple(_tokens(name)))
                out.append(name.strip())
    name = brief.get("product_name")
    if isinstance(name, str) and _tokens(name) and \
            tuple(_tokens(name)) not in seen:
        out.append(name.strip())
    return out


def _spans(tokens, name_tokens):
    """Start index of every occurrence of name_tokens inside tokens."""
    n = len(name_tokens)
    return [i for i in range(len(tokens) - n + 1)
            if tokens[i:i + n] == name_tokens]


def _find(tokens, want, start):
    """Index of contiguous ``want`` in tokens at/after start, else -1."""
    for i in _spans(tokens[start:], want):
        return start + i
    return -1


def check_sheet(sheet, packet_lines, protected=()):
    """Lyric-sheet BUILD gate. [] when clean, else error strings.

    sheet: str / list of str / list of {text}. packet_lines: the script
    packet's lines (list of str). Every packet line must appear in the sheet
    word for word and in packet order (the lyric writer may add lines, never
    rewrite one); every protected name must occur in the sheet at least as
    often as in the packet.
    """
    sheet_lines = _lines(sheet)
    stream = _tokens("\n".join(sheet_lines))
    errors, pos = [], 0
    for n, line in enumerate(_lines(packet_lines)):
        want = _tokens(line)
        if not want:
            continue
        hit = _find(stream, want, pos)
        if hit < 0:
            near = difflib.get_close_matches(
                " ".join(want), [" ".join(_tokens(s)) for s in sheet_lines],
                n=1, cutoff=0.5)
            errors.append("%s packet line %d %r not in sheet verbatim%s"
                          % (CODE_PACKET, n, line.strip(),
                             "; sheet has %r" % near[0] if near else ""))
        else:
            pos = hit + len(want)
    packet_stream = _tokens("\n".join(_lines(packet_lines)))
    for name in protected or ():
        nt = _tokens(name)
        if nt and len(_spans(stream, nt)) < len(_spans(packet_stream, nt)):
            errors.append("%s protected name %r appears %d time(s) in the "
                          "sheet, packet has %d"
                          % (CODE_SHEET, name, len(_spans(stream, nt)),
                             len(_spans(packet_stream, nt))))
    return errors


def _align(want, got):
    """difflib opcodes of want (sheet) vs got (sung/timed) token lists."""
    return difflib.SequenceMatcher(a=want, b=got, autojunk=False).get_opcodes()


def check_sung_names(sheet, sung_words, protected=()):
    """Words check for a take. sung_words: what was heard/aligned, as a
    string or list of words/{word}. [] when every protected name in the
    sheet was sung as written, else one error per wrong name."""
    want = _tokens("\n".join(_lines(sheet)))
    got = _tokens(" ".join(
        w.get("word", "") if isinstance(w, dict) else str(w)
        for w in ([sung_words] if isinstance(sung_words, str)
                  else (sung_words or []))))
    bad = {}
    for tag, i1, i2, j1, j2 in _align(want, got):
        if tag == "equal":
            continue
        for name in protected or ():
            nt = _tokens(name)
            for s in _spans(want, nt):
                if s < i2 and s + len(nt) > i1:
                    bad[(name, s)] = got[j1:j2]
    return ["%s %r sung as %r" % (CODE_SUNG, name, " ".join(heard) or "nothing")
            for (name, _), heard in sorted(bad.items(), key=lambda kv: kv[0][1])]


def build_captions(sheet, aligned_words):
    """One cue per sheet line: {text, start, end}. Text is ALWAYS the sheet's
    own text; aligned_words ([{word,start,end}] from Suno timestamps) supply
    times only. A sheet word with no matching timed word borrows its
    neighbour's time. Lines with no words at all (tags) are skipped."""
    sheet_lines = [s for s in _lines(sheet) if _tokens(s)]
    want, owner = [], []
    for i, line in enumerate(sheet_lines):
        for tok in _tokens(line):
            want.append(tok)
            owner.append(i)
    timed = [(_tokens(w.get("word", "")), float(w.get("start", 0)),
              float(w.get("end", 0))) for w in aligned_words or []]
    flat = [(t, s, e) for toks, s, e in timed for t in toks]
    at = [None] * len(want)
    for tag, i1, i2, j1, j2 in _align(want, [t for t, _, _ in flat]):
        if tag == "equal":
            for k in range(i2 - i1):
                at[i1 + k] = (flat[j1 + k][1], flat[j1 + k][2])
        elif j2 > j1:  # replaced word: spread over the sung span, text stays sheet
            for k in range(i1, i2):
                at[k] = (flat[j1][1], flat[j2 - 1][2])
    known = [a for a in at if a]
    cues = []
    for i, line in enumerate(sheet_lines):
        t = [at[k] for k in range(len(want)) if owner[k] == i and at[k]]
        if not t and known:  # whole line untimed: sit after the previous cue
            prev = cues[-1]["end"] if cues else known[0][0]
            t = [(prev, prev)]
        cues.append({"text": line.strip(),
                     "start": min(a for a, _ in t) if t else 0.0,
                     "end": max(b for _, b in t) if t else 0.0})
    return cues


def check_captions(cues, sheet, protected=(), text_source=CAPTION_TEXT_SOURCE):
    """QC gate. cues: list of {text} / str lines. [] when the caption words
    equal the approved sheet word for word, else error strings. Any
    mismatch fails; a changed protected name is named. A caption whose
    ``text_source`` is not the approved sheet (speech-to-text) fails."""
    errors = []
    if text_source != CAPTION_TEXT_SOURCE:
        errors.append("%s text_source %r, captions must come from %s, "
                      "never speech-to-text"
                      % (CODE_SOURCE, text_source, CAPTION_TEXT_SOURCE))
    want = _tokens("\n".join(_lines(sheet)))
    got = _tokens("\n".join(_lines(cues)))
    for tag, i1, i2, j1, j2 in _align(want, got):
        if tag == "equal":
            continue
        hit = [n for n in protected or ()
               if any(s < i2 and s + len(_tokens(n)) > i1
                      for s in _spans(want, _tokens(n)))]
        errors.append("%s word %d: caption %r != sheet %r%s"
                      % (CODE_CAPTION, i1, " ".join(got[j1:j2]),
                         " ".join(want[i1:i2]),
                         " (protected name %s)" % ", ".join(hit) if hit else ""))
    return errors


# --- I1: spell check + website ------------------------------------------------
_DICT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "english_words.txt.gz")
#: Sung filler and slang the dictionary lacks. Add here, never loosen the check.
_EXTRA = frozenset("""ok okay yeah yep nope hey hi oh ah aw uh um mm hmm woah whoa
gonna wanna gotta kinda cuz ya y'all na la da doo wow ain't tv dvd app apps
online email website url wifi""".split())
_VOCAL_RE = re.compile(r"^[aeiouhm]+$")  # ooh, ahh, mmm: held vowels
_SHORT_CVC = re.compile(r"^[^aeiou]{1,2}[aeiou][^aeiouwxy]$")
_dict_cache = []


def _dictionary():
    if not _dict_cache:
        try:
            with gzip.open(_DICT_PATH, "rt") as fh:
                _dict_cache.append(frozenset(fh.read().split()))
        except OSError:
            _dict_cache.append(None)
    return _dict_cache[0]


def _is_word(w, d, depth=2):
    """w or a simple inflection of it (web2 has no plurals/-ed/-ing)."""
    if w in d or w in _EXTRA or _VOCAL_RE.match(w):
        return True
    if depth == 0:
        return False
    for suf, add in (("ies", "y"), ("es", ""), ("s", ""), ("ed", ""), ("ed", "e"),
                     ("d", ""), ("ing", ""), ("ing", "e"), ("ly", ""), ("er", ""),
                     ("er", "e"), ("est", ""), ("est", "e"), ("ness", ""), ("en", "e"), ("en", ""), ("in", "g")):
        if w.endswith(suf) and len(w) - len(suf) >= 2:
            stem = w[:-len(suf)] + add
            if (suf in ("ed", "ing", "er", "est") and not add and len(stem) <= 4
                    and _SHORT_CVC.match(stem)):
                pass  # run + ing must double: runing is a typo, running is not
            elif _is_word(stem, d, depth - 1):
                return True
            if (
                    len(stem) > 2 and stem[-1] == stem[-2]
                    and _is_word(stem[:-1], d, depth - 1)):  # running -> run
                return True
    return False


def check_spelling(cues, protected=(), extra_words=()):
    """I1 QC gate. [] when every caption word is a real word, a number, or a
    protected word (character, brand, client website, ``extra_words``); else
    one error per unknown word, the word shown. Fails closed when the bundled
    dictionary cannot be read."""
    d = _dictionary()
    if d is None:
        return ["%s %s" % (CODE_NO_DICT, os.path.basename(_DICT_PATH))]
    ok = {t for n in list(protected or ()) + list(extra_words or ())
          for t in _tokens(n)}
    errors, seen = [], set()
    for w in _tokens("\n".join(_lines(cues))):
        base = w.split("'")[0]
        if w in seen or w in ok or base in ok or any(c.isdigit() for c in w):
            continue
        seen.add(w)
        if not (_is_word(w, d) or (base != w and _is_word(base, d)
                                   and w.split("'")[1] in ("s", "t", "re", "ve", "ll", "d", "m"))):
            errors.append("%s word %r is not a real word and not a protected name"
                          % (CODE_SPELL, w))
    return errors


def check_website(website, **texts):
    """I1: the client's exact web address, verbatim (case and punctuation
    ignored), in each given text (lyrics=, captions=, end_card=). A text that
    is None is skipped. [] when every given text carries it."""
    want = _tokens(website)
    if not want:
        return []
    return ["%s %r missing from %s (found %r)"
            % (CODE_WEBSITE, website, label,
               " ".join(_tokens("\n".join(_lines(t)))[:12]))
            for label, t in sorted(texts.items())
            if t is not None and not _spans(_tokens("\n".join(_lines(t))), want)]
