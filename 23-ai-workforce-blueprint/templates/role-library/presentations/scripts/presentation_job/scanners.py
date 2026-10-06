#!/usr/bin/env python3
"""
scanners.py — FIX 110 (SMOKE-1 addenda, workflow W29b): deterministic scanners
understand negation.

THE PROBLEM THIS CLOSES: slide 1's own PROHIBITION — "no dark slide background
appears anywhere" — tripped AF-DARK-SLIDE, because build_deck's keyword gates
were substring scans. A substring scanner cannot tell a request for a dark
background from a prohibition of one, so the deck's own doctrine text failed
the deck. The same defect class hits every negative-detector keyword gate:
"the demographic split is not specified by a default ratio", "no 60/30/10
anywhere", "the prompt must never say default demographic"...

THE SHAPE OF THIS FIX (MASTER plan FIX 110, extends Fix 24/35; source R14
§2.3, §5.8): ONE helper, `scan_negation_aware(text, keywords)`, that ignores a
keyword hit sitting within six tokens AFTER a negator (no, never, not,
without, avoid, prohibit — plus their sentence-position variants) in the SAME
sentence. Every keyword gate in build_deck.py that detects FORBIDDEN
vocabulary uses it; a prompt lint warns an author whose prohibition is
written in scanner vocabulary (the lint is the escape from the honest limit
below — say the prohibition differently and no scanner has to parse it).

HONEST LIMIT (read before trusting the negation window more than it earns):
token-window negation detection is a heuristic, not a language model. It
correctly suppresses "no dark background anywhere", "not a dark background",
"avoid dark backgrounds", "never render a dark background", "without a dark
background", and prohibitions naming the keyword within the same sentence
("prohibit any dark background"). It does NOT parse long-range scope ("the
client rejected the proposal to use a dark background") — six tokens covers
the natural prohibition patterns, and a hit outside the window still fires.
A keyword hit that is NOT negated still fires with zero behavior change from
the old substring scan, so the gate cannot get weaker than it was.

PUBLIC SURFACE:
  NEGATORS                  — the negator token tuple (extension point)
  NEGATION_WINDOW_TOKENS=6  — how many tokens after a negator are suppressed
  find_negated_spans(text)  — character spans suppressed by negation
  scan_negation_aware(text, keywords, window=6)
                            — returns [(keyword, start)] of hits OUTSIDE
                              negated spans (substitute for `kw in text`)
  has_keyword_hit / first_keyword_hit
                            — convenience wrappers
  lint_prohibition(text)    — prompt lint: warnings for prohibitions written
                              in scanner vocabulary (author-facing)
"""

from __future__ import annotations

import re
from typing import Iterable, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Negator vocabulary (FIX 110: no, never, not, without, avoid, prohibit).
# Sentence-position variants and the common contractions are included so
# "don't"/"do not"/"must not"/"no more"/"none of" suppress the same way.
# Kept lowercase — callers lowercase their text first (mirrors every existing
# keyword gate, which scanned `.lower()` text).
# ---------------------------------------------------------------------------
NEGATORS: Tuple[str, ...] = (
    "no", "never", "not", "without", "avoid", "prohibit", "prohibits",
    "prohibited", "prohibiting", "prohibition", "nor", "don't", "do not",
    "does not", "doesn't", "must not", "mustn't", "cannot", "can't", "won't",
    "will not", "shall not", "shan't", "no more", "none of", "disallow",
    "disallows", "disallowed", "forbid", "forbids", "forbidden", "banned",
    "ban", "excluding", "except", "reject", "rejects", "rejected",
)

# How many tokens AFTER a negator remain suppressed (FIX 110: six).
NEGATION_WINDOW_TOKENS = 6

# FIX 35: how many tokens BEFORE a negator remain suppressed. English negation
# also runs backward through the copula: "the dark theme is not wanted",
# "a dark background is not allowed", "near-black is not requested" — the keyword
# sits UP TO three tokens BEFORE the negator ("dark theme is not" — 'dark' is 3
# before 'not'). The look-back arms ONLY when the negator is followed by a
# refusal-predicate ("wanted/allowed/..."), so a bare look-back cannot swallow a
# sentence whose own phrasing carries the scanner vocabulary ("this is not just a
# webinar" — the technique telegraph itself — still fires; AF-AUD-4's own test).
NEGATION_LOOKBACK_TOKENS = 3

# Refusal predicates: a negator followed by one of these negates the clause's
# SUBJECT — the tokens before the copula — arming the look-back window.
_REFUSAL_PREDICATES = (
    "wanted", "allowed", "permitted", "requested", "authorized", "authorised",
    "approved", "needed", "desired", "welcome", "acceptable", "supported",
    "used", "rendered", "invoked",
)

# FIX 35: conjunction-scope extension. A prohibition's scope runs across its
# coordination: "do not use a dark background or a near-black vignette" — the
# second object is inside the SAME prohibition. When the forward window's last
# token is followed by a coordinating conjunction (and/or/nor, a comma, or a
# slash), the window extends past it (up to +3 tokens total) so both coordinated
# objects are suppressed, not just the first.
_CONJUNCTION_EXTENSIONS = ("and", "or", "nor", ",", "/")

# Sentence boundary — the window never crosses a sentence end.
_SENTENCE_SPLIT_RE = re.compile(r"[.!?;]\s+|\n+")

# A "token" for window purposes: letters/digits/hyphen/slash run (so
# "near-black" and "60/30/10" are one token), or any other non-space run.
_TOKEN_RE = re.compile(r"[a-z0-9_\-/#\.']+|[^\s]")

# Word characters for boundary checks: a keyword hit must not be glued to a
# longer word on either side (substring scanners had the same aliasing).
_WORD_BOUNDARY_RE = re.compile(r"[a-z0-9_\-/#]")


def _tokenize(sentence_lc: str) -> List[Tuple[str, int, int]]:
    """Tokenize a lower-cased sentence into (token, start, end) triples."""
    return [(m.group(0), m.start(), m.end())
            for m in _TOKEN_RE.finditer(sentence_lc)]


def _is_negator(token: str) -> bool:
    """True iff the token is a negator (exact token match — 'not' yes,
    'nothing' no: 'nothing' does not negate the FOLLOWING window)."""
    return token in NEGATORS


def find_negated_spans(text: str) -> List[Tuple[int, int]]:
    """Character spans of `text` suppressed by negation.

    A sentence is split at [.!?;] + whitespace and at newlines. Within a
    sentence, every keyword-sized region starting within
    NEGATION_WINDOW_TOKENS tokens after a negator token is suppressed:
    the negator token itself, the next NEGATION_WINDOW_TOKENS tokens, and the
    inter-token whitespace between them.

    The text is lower-cased internally for matching, but the returned spans
    are indices into the ORIGINAL string (callers slice the original text).
    """
    text_lc = text.lower()
    spans: List[Tuple[int, int]] = []
    for sentence_match in _SENTENCE_SPLIT_RE.finditer(text_lc):
        pass  # boundaries only; the loop below walks sentences directly.
    # Walk sentences: split text_lc into (start, end) sentence slices.
    sentence_bounds: List[Tuple[int, int]] = []
    prev = 0
    for m in _SENTENCE_SPLIT_RE.finditer(text_lc):
        # m.start() is the boundary (the separator start); the sentence is
        # [prev, m.end()) — keep the separator with the sentence so offsets
        # never overlap.
        sentence_bounds.append((prev, m.end()))
        prev = m.end()
    sentence_bounds.append((prev, len(text_lc)))

    for s_start, s_end in sentence_bounds:
        if s_start >= s_end:
            continue
        sentence = text_lc[s_start:s_end]
        tokens = _tokenize(sentence)
        for idx, (tok, t_start, t_end) in enumerate(tokens):
            if not _is_negator(tok):
                continue
            # Suppress the negator token itself plus the next
            # NEGATION_WINDOW_TOKENS tokens — i.e. a keyword hit starting at
            # token idx+1 .. idx+1+WINDOW-1 after the negator is negated
            # ("no dark background" — 1 token after; "no a b c d e dark
            # background" — 'dark' is the 7th token after the negator and
            # fires again). The spec reads "within six tokens after a
            # negator": the keyword's FIRST token lands inside the six.
            window_end_tok = min(idx + NEGATION_WINDOW_TOKENS, len(tokens) - 1)
            if window_end_tok < idx:
                continue
            # FIX 35: conjunction-scope extension — the prohibition's scope runs
            # across its coordination ("do not use a dark background or a
            # near-black vignette"). When the token after the current window end
            # is a coordinating conjunction/separator, the window jumps PAST it
            # plus up to three more tokens (the coordinated object), bounded by
            # +NEGATION_WINDOW_TOKENS so a run of commas cannot eat the rest of
            # the sentence.
            extend = 0
            while (window_end_tok + 1 < len(tokens)
                   and extend < NEGATION_WINDOW_TOKENS
                   and tokens[window_end_tok + 1][0] in _CONJUNCTION_EXTENSIONS):
                window_end_tok += 2  # skip the conjunction, take the next object
                extend += 2
            window_end_tok = min(window_end_tok + 1, len(tokens) - 1)
            extend += 1
            span_start = s_start + t_start
            span_end = s_start + tokens[window_end_tok][2]
            spans.append((span_start, span_end))
            # FIX 35: look-back window — copula negation puts the negator AFTER
            # the keyword ("the dark theme is not wanted"). It arms ONLY when the
            # negator is followed by a refusal predicate ("not wanted/allowed/…"):
            # then the clause's subject — the tokens before the negator — is what
            # is being refused, so up to NEGATION_LOOKBACK_TOKENS tokens BEFORE
            # the negator are suppressed (bounded at sentence start). A negator
            # followed by anything else ("not just a webinar") keeps its forward
            # window only, so scanner vocabulary that PRECEDES the negator still
            # fires.
            next_tok = tokens[idx + 1][0] if idx + 1 < len(tokens) else ""
            if next_tok in _REFUSAL_PREDICATES:
                lb_end_tok = max(0, idx - 1 - NEGATION_LOOKBACK_TOKENS)
                lb_start = s_start + (tokens[lb_end_tok][1]
                                      if lb_end_tok < idx else t_start)
                if lb_start < span_end:
                    spans.append((lb_start, span_end))
    return spans


def _in_spans(pos: int, spans: Sequence[Tuple[int, int]]) -> bool:
    return any(s <= pos < e for s, e in spans)


def _whole_word_hit(text_lc: str, start: int, end: int) -> bool:
    """A hit is whole-word unless glued to a word character on either side."""
    if start > 0 and _WORD_BOUNDARY_RE.match(text_lc[start - 1]):
        return False
    if end < len(text_lc) and _WORD_BOUNDARY_RE.match(text_lc[end]):
        return False
    return True


def scan_negation_aware(
    text: str,
    keywords: Iterable[str],
    window: int = NEGATION_WINDOW_TOKENS,
) -> List[Tuple[str, int]]:
    """FIX 110 core: every keyword hit NOT suppressed by negation.

    Replaces the bare `keyword in text_lower` scans: returns [(keyword, char
    offset)] for each hit of any keyword in `text` that does NOT sit within
    `window` tokens after a negator in the same sentence. A keyword found
    only inside negated spans returns []. Offsets index the ORIGINAL text
    (find on `text[offset:offset+len(keyword)]`).

    `window` defaults to the module constant (6 per FIX 110); callers may
    pass a different width, 0 disables negation suppression entirely
    (degenerates to the old substring scan + whole-word boundary).
    """
    keywords = [str(k).lower() for k in keywords if str(k)]
    if not keywords or not text:
        return []
    text_lc = text.lower()

    spans = find_negated_spans(text) if window and window > 0 else []

    hits: List[Tuple[str, int]] = []
    for kw in keywords:
        search_from = 0
        while True:
            idx = text_lc.find(kw, search_from)
            if idx < 0:
                break
            search_from = idx + 1
            if not _whole_word_hit(text_lc, idx, idx + len(kw)):
                continue
            if _in_spans(idx, spans):
                continue  # negated — FIX 110 suppresses this hit
            hits.append((kw, idx))
    hits.sort(key=lambda h: (h[1], h[0]))
    return hits


def has_keyword_hit(text: str, keywords: Iterable[str]) -> bool:
    """True iff any keyword hit survives negation suppression."""
    return bool(scan_negation_aware(text, keywords))


def first_keyword_hit(
    text: str,
    keywords: Iterable[str],
) -> Optional[Tuple[str, int]]:
    """The earliest surviving (keyword, offset) or None."""
    hits = scan_negation_aware(text, keywords)
    return hits[0] if hits else None


def hit_outside_negation(
    text: str,
    keywords: Iterable[str],
) -> bool:
    """Backwards-compatible boolean for the gates: any surviving hit?"""
    return has_keyword_hit(text, keywords)


# ---------------------------------------------------------------------------
# Prompt lint (FIX 110): warn an author whose PROHIBITION is written in
# scanner vocabulary. A prohibition sentence that names a scanner keyword
# within the negation window parses clean today — but it is one rewrite away
# from tripping a scanner (any editor who drops the negator re-fails the
# deck). The lint surfaces those sentences so the prohibition gets written in
# non-scanner vocabulary ("render light backgrounds only") instead of the
# negative of scanner vocabulary ("no dark background anywhere").
# ---------------------------------------------------------------------------
def lint_prohibition(text: str) -> List[str]:
    """Human-readable warnings for prohibitions phrased in scanner vocabulary.

    Returns [] when nothing to warn about. A warning fires per SENTENCE that
    (a) opens with or contains a negator in its first half AND (b) carries a
    scanner-vocabulary keyword within the negation window — i.e. exactly the
    sentence a scanner will only skip because of the negator. Deliberately a
    WARNING (author guidance), never a gate: the scanner-vocabulary sentence
    still passes FIX 110's negation-aware scan.
    """
    warnings: List[str] = []
    if not text or not text.strip():
        return warnings

    text_lc = text.lower()
    sentence_bounds: List[Tuple[int, int]] = []
    prev = 0
    for m in _SENTENCE_SPLIT_RE.finditer(text_lc):
        sentence_bounds.append((prev, m.end()))
        prev = m.end()
    sentence_bounds.append((prev, len(text_lc)))

    for s_start, s_end in sentence_bounds:
        sentence = text_lc[s_start:s_end]
        if not sentence.strip():
            continue
        tokens = _tokenize(sentence)
        if not tokens:
            continue
        # Negator in the first half of the sentence = the sentence's job is
        # prohibition, not contrast ("light here, not there" reads different).
        neg_idx = next((i for i, (tok, _, _) in enumerate(tokens)
                        if _is_negator(tok)), None)
        if neg_idx is None or neg_idx > len(tokens) // 2:
            continue
        # Scanner vocabulary within the negation window?
        window_tokens = {t for t, _, _ in
                         tokens[neg_idx:neg_idx + NEGATION_WINDOW_TOKENS + 1]}
        vocab_hit = next((v for v in SCANNER_VOCAB if v in window_tokens),
                         None)
        if vocab_hit is None:
            # multi-word vocabulary: fall back to a substring pass over the
            # suppressed span of this sentence.
            spans = _negated_span_in_sentence(tokens, s_start)
            vocab_hit = next((v for v in SCANNER_VOCAB_MULTIWORD
                              if any(v in text_lc[s:e] for s, e in spans)),
                             None)
        if vocab_hit is not None:
            warnings.append(
                f"prohibition phrased in scanner vocabulary ({vocab_hit!r}) — "
                "prefer positive art direction (e.g. 'render light backgrounds "
                "only') so the deterministic scanners never depend on parsing "
                "this negation (FIX 110 prompt lint)")
    return warnings


def _negated_span_in_sentence(
    tokens: List[Tuple[str, int, int]],
    sentence_start: int,
) -> List[Tuple[int, int]]:
    """The negation-suppressed character spans within ONE sentence's tokens."""
    spans: List[Tuple[int, int]] = []
    for idx, (tok, t_start, t_end) in enumerate(tokens):
        if not _is_negator(tok):
            continue
        window_end_tok = min(idx + NEGATION_WINDOW_TOKENS, len(tokens) - 1)
        if window_end_tok < idx:
            continue
        spans.append((sentence_start + t_start,
                      sentence_start + tokens[window_end_tok][2]))
    return spans


# Scanner-vocabulary tokens the lint watches (the dark-gate vocabulary plus
# the demographic landmine vocabulary — the gates that actually parse prose).
SCANNER_VOCAB: Tuple[str, ...] = (
    "dark", "black", "near-black", "theme", "mode", "slide",
    "background", "default", "demographic", "ethnicity", "race",
    "ratio", "60/30/10",
)
SCANNER_VOCAB_MULTIWORD: Tuple[str, ...] = (
    "dark background", "black background", "dark theme", "dark mode",
    "dark slide", "near-black", "default demographic", "default ethnicity",
    "default race", "default skin", "standard demographic",
    "standard representation", "system default",
)
