#!/usr/bin/env python3
"""No-echo rule (D22a) on every Suno request the factory builds.

Owner unit AF-ECHO-U1 — Decision log 36 (D22a) 2026-10-07; plan 6.12 item 3;
``qualification/bsw-power-in-the-climb/AUDIO-FIX-BRIEF.md``. stdlib only,
zero paid calls.

Every Suno payload — the **song** payload and every **voice-pack** payload —
carries:

  * the dry close-microphone vocal rule (``dry_close_mic`` plus the phrase
    ``dry close-microphone vocal`` in every style/prompt text surface the
    payload actually has: ``input.style``, ``input.prompt``, ``prompt``, ...);
  * the short negative tags — reverb, echo, choir — set on the payload, not
    merely implied by the prose (Part F F13, owner order 2026-10-08: the
    research summary found the short list works where the long lists did
    not);
  * the three style words a spoken part never uses: spacious, cinematic,
    choir. A spoken part naming one is refused by name
    (``BANNED_STYLE_WORD:<word>``) instead of being shipped;
  * (Part F F13) the song style never uses the banned style words
    (``SONG_BANNED_STYLE_WORDS``: strings, gospel, harmonies, cinematic,
    choir and the wider dry-style list from 03-ECHO-ROOT-CAUSE.md section 7).
    A song style naming one is refused by name
    (``BANNED_SONG_STYLE_WORD:<word>``) instead of being shipped.

Two surfaces ship the rule as text: ``card_line()`` (the choice card) and
``docs_line()`` (the skill docs). Both state the dry vocal rule.

The module shapes and verifies payloads only. It carries no transport of its
own: Skill 74 is the only permitted KIE path, so nothing here imports a
network client or spends money. stdlib only.

Deliberate scope (ponytail): spoken-part style text is read from
``spoken_style`` (one string) and ``spoken_parts`` (list of strings or of
dicts carrying ``style``/``prompt``/``style_text``). Part F F13 (owner order
2026-10-08, root cause 03-ECHO-ROOT-CAUSE.md): the song style itself is
banned-word checked too — the echo batch was caused by builder-invented song
styles naming strings / choir / cinematic — so the style surfaces of a SONG
payload are scanned against ``SONG_BANNED_STYLE_WORDS`` and refused. The
lyrics surface is not scanned: the ban is a style rule, not a lyric rule.

Run: python3 core/audio_c3/no_echo/test_no_echo.py
"""
from __future__ import annotations

import copy
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

SCHEMA_VERSION = "blackceo.audio-c3/no-echo/v1"
TOOL_VERSION = "0.1.0"
RULE_ID = "D22a"

#: The one producer. Nothing else generates this audio.
PROVIDER = "suno"
#: The only permitted KIE path (Skill 74); this module never becomes one.
KIE_PATH = "Skill 74"

#: The two kinds of Suno payload this rule is stamped on.
KIND_SONG = "song"
KIND_VOICE_PACK = "voice-pack"
REQUEST_KINDS = (KIND_SONG, KIND_VOICE_PACK)

#: D22a: what every payload asks for, in the owner's words.
DRY_RULE = "dry close-microphone vocal"

#: D22a as narrowed by Part F F13 (owner order 2026-10-08): the short
#: negative tags, set on every payload. The 2026-10-07 rebuilds went from 14
#: tags to 7 to 3; the research summary behind F13 says only the short list
#: is reliable, so the long lists are retired from the stamp.
NEGATIVE_TAGS = (
    "reverb",
    "echo",
    "choir",
)

#: The owner brief's wider negative set (AUDIO-FIX-BRIEF item 1, 2026-10-07).
#: A superset of the short tags; stamped alongside them as
#: ``negative_tags_extended`` for the regenerate path. ``check`` only demands
#: it when it is present, so a payload carrying just the short tags still
#: passes.
BRIEF_NEGATIVE_TAGS = (
    "reverb",
    "echo",
    "delay",
    "hall",
    "room",
    "ethereal",
    "ambient",
    "choir",
    "choir pad",
    "atmospheric",
    "spacious",
    "cinematic",
    "wet",
    "shimmer",
)

#: D22a: three style words a spoken part never uses.
SPOKEN_BANNED_STYLE_WORDS = ("spacious", "cinematic", "choir")

#: Part F F13 (owner order 2026-10-08; 03-ECHO-ROOT-CAUSE.md sections 5 and
#: 7): style words a SONG style never uses. The echo batch was caused by
#: builder-invented song styles asking for strings, gospel harmonies and a
#: cinematic mix; Suno returned sparse-ballad takes with long vocal tails.
#: "strings" covers swelling analog strings; "gospel" covers gospel organ
#: and gospel-tinged harmonies; "harmonies"/"backing"/"atmospheric"/
#: "ethereal"/"ambient"/"airy"/"spacious"/"cinematic"/"prayerful"/"wet"/
#: "shimmer"/"hall"/"room" are the wider dry-style list from the root-cause
#: report; "choir" was already banned in spoken parts and is banned in song
#: styles too. Matched whole-word, case-insensitive, so "strings" never
#: trips on a compound the root cause did not name unless it repeats the
#: word itself.
SONG_BANNED_STYLE_WORDS = (
    "strings",
    "gospel",
    "choir",
    "harmonies",
    "cinematic",
    "spacious",
    "prayerful",
    "atmospheric",
    "ethereal",
    "ambient",
    "airy",
    "wet",
    "shimmer",
    "hall",
    "room",
)

#: G1 amended (owner order 2026-10-08 11:50, part G, review G6): the
#: delivery map and the tags-vs-sheet contradiction gate, sourced from
#: core/music_styles (single point), never a second copy. The 11:35 ban
#: is REVERSED: the style text now CARRIES the delivery map ("SPEAKS the
#: lines tagged Spoken ... SINGS the lines tagged Sung") and negative
#: tags banning a delivery the sheet uses are refused.
try:
    import music_styles as _MS                  # core/ on sys.path
except ImportError:                             # loaded outside core/
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.abspath(
        _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                      "..", "..")))
    import music_styles as _MS

CONTRADICTING_NEGATIVE_TAGS = _MS.CONTRADICTING_NEGATIVE_TAGS
LYRICS_PATHS = (("input", "lyrics"), ("lyrics",))

#: Rendered once, derived, so no surface can drift from NEGATIVE_TAGS.
TAG_LIST_TEXT = ", ".join(NEGATIVE_TAGS)

RULE_TEXT = (
    "Rule %s: every Suno payload (song and voice pack) asks for %s and sets "
    "the negative tags %s; a spoken part never uses spacious, cinematic or "
    "choir, and a song style never uses the banned song-style words "
    "(D22a, Part F F13)." % (RULE_ID, DRY_RULE, TAG_LIST_TEXT)
)
#: Choice-card line; label plus padding matches the existing Audio lines.
CARD_LINE = (
    "  Audio:       dry close-mic vocals + negative tags (%s); spoken parts "
    "never use spacious / cinematic / choir; song styles stay dry (no "
    "strings / gospel / cinematic / choir) (D22a, F13)" % TAG_LIST_TEXT
)
DOCS_LINE = (
    "No-echo rule (D22a, Part F F13): every Suno payload (the song payload "
    "and every voice-pack payload) asks for %ss and sets the short negative "
    "tags %s; a spoken part never uses spacious, cinematic or choir, and a "
    "song style never uses the banned song-style words (strings, gospel, "
    "harmonies, cinematic, spacious, prayerful, atmospheric, ethereal, "
    "ambient, airy, wet, shimmer, hall, room, choir)."
    % (DRY_RULE, TAG_LIST_TEXT)
)

#: Text surfaces a Suno payload can carry the dry rule on, in stamp order.
STYLE_TEXT_PATHS = (
    ("input", "style"),
    ("input", "prompt"),
    ("prompt",),
    ("style",),
    ("style_text",),
)

_BANNED_PATTERNS = tuple(
    (word, re.compile(r"\b%s\b" % re.escape(word), re.IGNORECASE))
    for word in SPOKEN_BANNED_STYLE_WORDS
)
_SONG_BANNED_PATTERNS = tuple(
    (word, re.compile(r"\b%s\b" % re.escape(word), re.IGNORECASE))
    for word in SONG_BANNED_STYLE_WORDS
)
_DRY_PHRASE = re.compile(
    r"\bdry\b[\s-]*(?:close[\s-]*mic(?:rophone)?)",
    re.IGNORECASE,
)


class NoEchoError(Exception):
    """Structural problem with the caller's payload (refusal, never a ship)."""

    def __init__(self, code: str, message: str):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def _music_refusal(exc: Exception) -> NoEchoError:
    """A ``MusicStyleError`` as the refusal this module raises.

    Keeps the code and strips the duplicated ``CODE: `` prefix, so the
    envelope reports ``NEGATIVE_TAG_CONTRADICTION: ...`` once, not twice.
    """
    text = str(exc)
    code = str(getattr(exc, "code", "STYLE_REFUSAL"))
    message = text.split(": ", 1)[1] if text.startswith(code + ": ") else text
    return NoEchoError(code, message)


def _envelope(outcome: str, reason_code: str, errors: Iterable[str],
              **extra: Any) -> Dict[str, Any]:
    env = {
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "outcome": outcome,
        "reason_code": reason_code,
        "errors": list(errors),
        "rule_id": RULE_ID,
        "provider": PROVIDER,
        "kie_path": KIE_PATH,
        "rule": RULE_TEXT,
        "card_line": CARD_LINE,
        "docs_line": DOCS_LINE,
    }
    env.update(extra)
    return env


# --------------------------------------------------------------- surface ---

def rule_text() -> str:
    """The D22a rule exactly as it is stamped on every payload."""
    return RULE_TEXT


def card_line() -> str:
    """The choice-card line stating the dry vocal rule."""
    return CARD_LINE


def docs_line() -> str:
    """The docs line stating the dry vocal rule."""
    return DOCS_LINE


def negative_tags() -> List[str]:
    """The short negative tags, as a list a payload can carry."""
    return list(NEGATIVE_TAGS)


def refused_style_words(text: Any) -> List[str]:
    """Which of the three banned style words this spoken text names.

    Case-insensitive, whole word: a spoken part asking for "Cinematic" or
    "choir pad" is refused under ``cinematic`` / ``choir``.
    """
    if not isinstance(text, str) or not text.strip():
        return []
    return [word for word, pattern in _BANNED_PATTERNS if pattern.search(text)]


def refused_song_style_words(text: Any) -> List[str]:
    """Which banned song-style words this song style text names (Part F F13).

    Case-insensitive, whole word, same matcher as the spoken ban: a song
    style asking for "swelling analog strings", "gospel-tinged backing
    harmonies" or a "cinematic mix" is refused under ``strings`` /
    ``gospel`` / ``harmonies`` / ``cinematic``.
    """
    if not isinstance(text, str) or not text.strip():
        return []
    return [word for word, pattern in _SONG_BANNED_PATTERNS
            if pattern.search(text)]


def _spoken_texts(spoken_style: Any, spoken_parts: Any) -> List[str]:
    out: List[str] = []
    if isinstance(spoken_style, str):
        out.append(spoken_style)
    elif spoken_style is not None:
        raise NoEchoError(
            "SPOKEN_STYLE_INVALID",
            "spoken_style must be a string or None, got %r"
            % type(spoken_style).__name__)
    for part in spoken_parts or ():
        if isinstance(part, str):
            out.append(part)
        elif isinstance(part, dict):
            for key in ("style", "prompt", "style_text"):
                value = part.get(key)
                if isinstance(value, str):
                    out.append(value)
        elif part is not None:
            raise NoEchoError(
                "SPOKEN_PART_INVALID",
                "a spoken part must be a string or a dict, got %r"
                % type(part).__name__)
    return out


def _payload_spoken_texts(request: Dict[str, Any]) -> List[str]:
    """Spoken style text already sitting on the payload itself."""
    return _spoken_texts(request.get("spoken_style"),
                          request.get("spoken_parts"))


def _style_surfaces(request: Any) -> List[Tuple[Tuple[str, ...], str]]:
    """``(path, text)`` for every style/prompt surface the payload carries."""
    out: List[Tuple[Tuple[str, ...], str]] = []
    if not isinstance(request, dict):
        return out
    for path in STYLE_TEXT_PATHS:
        node: Any = request
        for key in path:
            if not isinstance(node, dict) or key not in node:
                node = None
                break
            node = node[key]
        if isinstance(node, str) and node.strip():
            out.append((path, node))
    return out


def _set_surface(request: Dict[str, Any], path: Tuple[str, ...],
                 value: str) -> None:
    node: Any = request
    for key in path[:-1]:
        nxt = node.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            node[key] = nxt
        node = nxt
    node[path[-1]] = value


def _with_dry(text: str) -> str:
    """``text`` asking for the dry rule, never asked for twice."""
    base = text.strip().rstrip(",")
    if not base:
        return DRY_RULE
    if _DRY_PHRASE.search(base):
        return base
    return "%s, %s" % (base, DRY_RULE)


def _has_dry(text: str) -> bool:
    return bool(_DRY_PHRASE.search(text or ""))


def _sheet_text(request: Any) -> str:
    """The lyric sheet the payload carries, from the known lyrics paths."""
    if not isinstance(request, dict):
        return ""
    for path in LYRICS_PATHS:
        node: Any = request
        for key in path:
            if not isinstance(node, dict) or key not in node:
                node = None
                break
            node = node[key]
        if isinstance(node, str) and node.strip():
            return node
    return ""

def _check_declared_transport(request: Dict[str, Any]) -> None:
    """Refuse a payload that already names a second producer or KIE path."""
    provider = request.get("provider")
    if isinstance(provider, str) and provider.strip() and \
            provider.strip().lower() != PROVIDER:
        raise NoEchoError(
            "WRONG_PROVIDER",
            "%s: only %s builds this payload (D22a)" % (provider, PROVIDER))
    kie_path = request.get("kie_path")
    if isinstance(kie_path, str) and kie_path.strip() and \
            kie_path.strip() != KIE_PATH:
        raise NoEchoError(
            "WRONG_KIE_PATH",
            "%s: only %s is the permitted KIE path" % (kie_path, KIE_PATH))


# ---------------------------------------------------------------- build ----

def stamp(request: Any = None, *, kind: Optional[str] = None,
          style_text: Optional[str] = None,
          spoken_style: Optional[str] = None,
          spoken_parts: Optional[list] = None,
          sung: Optional[bool] = None) -> Dict[str, Any]:
    """Copy ``request`` with the D22a rule written on it.

    Refuses (``NoEchoError``) when any spoken part names a banned style
    word, when ``kind`` is not one of the two Suno payload kinds, or when the
    payload already names a second producer or a non-Skill-74 KIE path — the
    rule is never written over a contradicting payload. The caller's
    dictionary is never mutated.

    G1 amended (owner order 2026-10-08 11:50, part G, review G6): the
    payload is refused when its negative tags ban "spoken word" or "rap"
    while the lyric sheet carries spoken or rap blocks (the tags would
    contradict the sheet), and every style surface whose sheet names a
    delivery ends with the delivery map built from that sheet ("The lead
    SPEAKS the lines tagged Spoken ... SINGS the lines tagged Sung").
    The earlier 11:35 rule -- ban spoken-word wording from the style text
    and add "spoken word, rap" as negative tags -- is REVERSED: no
    negative tag is ever added here.
    """
    if request is None:
        request = {}
    if not isinstance(request, dict):
        raise NoEchoError("REQUEST_INVALID",
                          "a Suno payload is a dict, got %r"
                          % type(request).__name__)
    if kind is not None and kind not in REQUEST_KINDS:
        raise NoEchoError(
            "BAD_REQUEST_KIND",
            "%r: a Suno payload is a %s" % (kind, " or ".join(REQUEST_KINDS)))
    if style_text is not None and not isinstance(style_text, str):
        raise NoEchoError("STYLE_TEXT_INVALID",
                          "style_text must be a string or None, got %r"
                          % type(style_text).__name__)

    texts = _spoken_texts(spoken_style, spoken_parts)
    for text in texts:
        for word in refused_style_words(text):
            raise NoEchoError(
                "BANNED_STYLE_WORD",
                "%s: a spoken part never uses %r (D22a: spacious, cinematic, "
                "choir)" % (word, word))

    out = copy.deepcopy(request)
    _check_declared_transport(out)

    sheet = _sheet_text(out) or (style_text if isinstance(style_text, str)
                                 else "")
    # G1 amended: the contradiction gate runs on EVERY payload, sung or
    # not -- negative tags banning a delivery the sheet uses are refused
    # (the 11:35 style-text ban is reversed). MusicStyleError surfaces as
    # NoEchoError, so the envelope contract holds.
    try:
        _MS.assert_no_contradiction(out.get("negative_tags") or (), sheet)
    except _MS.MusicStyleError as exc:
        raise _music_refusal(exc) from None

    out.setdefault("schema_version", SCHEMA_VERSION)
    out.setdefault("tool_version", TOOL_VERSION)
    out.setdefault("rule_id", RULE_ID)
    out.setdefault("provider", PROVIDER)
    out.setdefault("kie_path", KIE_PATH)
    if kind is not None:
        out["request_kind"] = kind

    surfaces = _style_surfaces(out)
    if style_text is not None:
        if surfaces:
            _set_surface(out, surfaces[0][0], style_text)
        else:
            out["prompt"] = style_text
        surfaces = _style_surfaces(out)
    if not surfaces:
        out["prompt"] = DRY_RULE
        surfaces = _style_surfaces(out)
    for path, text in surfaces:
        if not _has_dry(text):
            _set_surface(out, path, _with_dry(text))
        if (kind is None or kind == KIND_SONG):
            for word in refused_song_style_words(text):
                raise NoEchoError(
                    "BANNED_SONG_STYLE_WORD",
                    "%s: a song style never uses %r (D22a, Part F F13)"
                    % (word, word))

    out["dry_close_mic"] = True
    out["negative_tags"] = list(NEGATIVE_TAGS)
    out["style_words_banned"] = list(SPOKEN_BANNED_STYLE_WORDS)
    # G1 amended: every style surface whose sheet names a delivery ends
    # with the delivery map built from that sheet. A sheet that names no
    # delivery owes no map (the G2 tag grammar owns that refusal), so a
    # "la la" payload stamps exactly as before. No negative tag is ever
    # added here -- the 11:35 ban is reversed.
    try:
        deliveries = _MS.sheet_deliveries(sheet)
        if deliveries:
            map_sentence = _MS.delivery_map(sheet)
            for path, text in _style_surfaces(out):
                if _MS.has_delivery_map(text, deliveries):
                    continue
                name = ".".join(str(p) for p in path) or "style_text"
                new_text = "%s %s" % (text.rstrip(".,"), map_sentence)
                _MS.assert_delivery_map(name, new_text, deliveries)
                _set_surface(out, path, new_text)
        if sung:
            out["sung"] = True
    except _MS.MusicStyleError as exc:
        raise _music_refusal(exc) from None
    if kind is None or kind == KIND_SONG:
        out["song_style_words_banned"] = list(SONG_BANNED_STYLE_WORDS)
    out["rule"] = RULE_TEXT
    out["card_line"] = CARD_LINE
    out["docs_line"] = DOCS_LINE
    if spoken_style is not None:
        out["spoken_style"] = spoken_style
    if spoken_parts is not None:
        out["spoken_parts"] = copy.deepcopy(spoken_parts)
    return out


def _build(kind: str, request: Any, style_text: Optional[str],
           spoken_style: Optional[str], spoken_parts: Optional[list],
           request_id: Optional[str],
           sung: Optional[bool] = None) -> Dict[str, Any]:
    """Shared builder for both payload kinds. Envelope, never an exception."""
    if request is None:
        request = {}
    if not isinstance(request, dict):
        return _envelope(
            "rejected", "request-invalid",
            ["REQUEST_INVALID:%r (a Suno payload is a dict)"
             % type(request).__name__],
            request_kind=kind, request=None, request_id=request_id)
    try:
        texts = _spoken_texts(spoken_style, spoken_parts)
    except NoEchoError as exc:
        return _envelope("rejected", "spoken-part-invalid", [str(exc)],
                         request_kind=kind, request=None,
                         request_id=request_id)
    banned: List[str] = []
    for text in texts:
        for word in refused_style_words(text):
            if word not in banned:
                banned.append(word)
    if banned:
        return _envelope(
            "rejected", "banned-spoken-style-word",
            ["BANNED_STYLE_WORD:%s (a spoken part never uses %r: D22a)"
             % (word, word) for word in banned],
            request_kind=kind, request=None, request_id=request_id,
            refused_words=banned)
    # Part F F13: the song style itself is banned-word checked. A song
    # payload whose style names a banned song-style word is refused, never
    # shipped. A payload with no kind is treated as a song.
    if kind is None or kind == KIND_SONG:
        song_banned: List[str] = []
        try:
            probe = copy.deepcopy(request) if isinstance(request, dict) else {}
            probe_surfaces = _style_surfaces(probe)
            if style_text is not None:
                if probe_surfaces:
                    _set_surface(probe, probe_surfaces[0][0], style_text)
                else:
                    probe["prompt"] = style_text
                probe_surfaces = _style_surfaces(probe)
            for _path, text in probe_surfaces:
                for word in refused_song_style_words(text):
                    if word not in song_banned:
                        song_banned.append(word)
        except NoEchoError as exc:
            return _envelope("rejected", exc.code.lower(), [str(exc)],
                             request_kind=kind, request=None,
                             request_id=request_id)
        if song_banned:
            return _envelope(
                "rejected", "banned-song-style-word",
                ["BANNED_SONG_STYLE_WORD:%s (a song style never uses %r: "
                 "D22a, Part F F13)" % (word, word)
                 for word in song_banned],
                request_kind=kind, request=None, request_id=request_id,
                refused_words=song_banned)
    try:
        stamped = stamp(request, kind=kind, style_text=style_text,
                        spoken_style=spoken_style, spoken_parts=spoken_parts,
                        sung=sung)
    except NoEchoError as exc:
        return _envelope("rejected", exc.code.lower(), [str(exc)],
                         request_kind=kind, request=None,
                         request_id=request_id)
    if request_id is not None:
        stamped["request_id"] = request_id
    return _envelope("ok", "", [], request_kind=kind, request=stamped,
                     request_id=request_id, refused_words=[])


def song_request(request: Any = None, *, style_text: Optional[str] = None,
                 spoken_style: Optional[str] = None,
                 spoken_parts: Optional[list] = None,
                 request_id: Optional[str] = None,
                 sung: Optional[bool] = None) -> Dict[str, Any]:
    """The song payload, D22a stamped. Envelope, never an exception.

    Hand it the payload the song builder produced (for example the
    current-envelope generate payload) and it comes back carrying the dry
    rule, the short negative tags, the spoken-part ban and the song-style
    ban (Part F F13).

    G1 amended: ``sung=True`` marks the payload as a sung style. The
    payload is refused when its negative tags ban "spoken word" or "rap"
    while the sheet carries spoken or rap blocks, and every style surface
    whose sheet names a delivery ends with the delivery map. No negative
    tag is added (the 11:35 rule that added "spoken word, rap" is
    REVERSED).
    """
    return _build(KIND_SONG, request, style_text, spoken_style,
                  spoken_parts, request_id, sung=sung)


def voice_pack_request(request: Any = None, *, prompt: Optional[str] = None,
                       spoken_style: Optional[str] = None,
                       spoken_parts: Optional[list] = None,
                       request_id: Optional[str] = None) -> Dict[str, Any]:
    """The voice-pack payload, D22a stamped. Envelope, never an exception.

    ``prompt`` is the pack's own style text; a pack already carrying the dry
    rule comes back unchanged (the stamp is idempotent).
    """
    return _build(KIND_VOICE_PACK, request, prompt, spoken_style,
                  spoken_parts, request_id)


# ---------------------------------------------------------------- check ----

def check(request: Any) -> Dict[str, Any]:
    """Verify a payload already carries D22a. Fail closed on every gap."""
    if not isinstance(request, dict):
        return _envelope("rejected", "request-invalid",
                         ["REQUEST_INVALID:%r (a Suno payload is a dict)"
                          % type(request).__name__],
                         request=None)
    errors: List[str] = []

    kind = request.get("request_kind")
    if kind is not None and kind not in REQUEST_KINDS:
        errors.append("WRONG_REQUEST_KIND:%r (a Suno payload is a %s)"
                      % (kind, " or ".join(REQUEST_KINDS)))

    surfaces = _style_surfaces(request)
    if not surfaces:
        errors.append(
            "MISSING_STYLE_TEXT:no style or prompt surface to carry %r"
            % DRY_RULE)
    if request.get("dry_close_mic") is not True:
        errors.append("MISSING_DRY_RULE:dry_close_mic is not True")
    for path, text in surfaces:
        if not _has_dry(text):
            errors.append("MISSING_DRY_RULE:%s does not ask for %r"
                          % (".".join(path), DRY_RULE))

    tags = request.get("negative_tags")
    tags = [t for t in tags if isinstance(t, str)] if isinstance(
        tags, (list, tuple)) else []
    for tag in NEGATIVE_TAGS:
        if tag not in tags:
            errors.append("MISSING_NEGATIVE_TAG:%s" % tag)

    extended = request.get("negative_tags_extended")
    if extended is not None:
        ext = [t for t in extended if isinstance(t, str)] if isinstance(
            extended, (list, tuple)) else []
        # An extended list is a caller's choice; completeness is measured
        # against the full brief set, not the short stamp.
        for tag in BRIEF_NEGATIVE_TAGS:
            if tag not in ext:
                errors.append("INCOMPLETE_EXTENDED_NEGATIVE_TAGS:%s" % tag)

    guards = request.get("style_words_banned")
    guards = [str(g).lower() for g in guards] if isinstance(
        guards, (list, tuple)) else []
    for word in SPOKEN_BANNED_STYLE_WORDS:
        if word not in guards:
            errors.append("MISSING_BANNED_STYLE_WORD_GUARD:%s" % word)

    # Part F F13: the song style itself is banned-word checked. Only the
    # style/prompt surfaces are scanned (the lyrics surface is a lyric, not
    # a style), and only on song payloads -- a voice-pack prompt is spoken
    # text and is covered by the spoken ban below.
    if request.get("request_kind") == KIND_SONG:
        song_guards = request.get("song_style_words_banned")
        song_guards = [str(g).lower() for g in song_guards] if isinstance(
            song_guards, (list, tuple)) else []
        for word in SONG_BANNED_STYLE_WORDS:
            if word not in song_guards:
                errors.append("MISSING_SONG_BANNED_STYLE_WORD_GUARD:%s"
                              % word)
        song_banned: List[str] = []
        for path, text in surfaces:
            for word in refused_song_style_words(text):
                if word not in song_banned:
                    song_banned.append(word)
        for word in song_banned:
            errors.append(
                "BANNED_SONG_STYLE_WORD_IN_STYLE:%s (a song style never uses "
                "%r)" % (word, word))

    # G1 amended: every payload whose sheet names a delivery must carry the
    # delivery map on its style text, and no payload may set negative tags
    # that ban a delivery its sheet uses (the 11:35 style-text ban and the
    # sung negative tags are REVERSED).
    sheet = _sheet_text(request)
    deliveries = _MS.sheet_deliveries(sheet)
    map_missing = False
    contradicted = False
    if deliveries:
        for path, text in surfaces:
            missing = _MS.missing_delivery_verbs(text, deliveries)
            if missing:
                map_missing = True
                errors.append(
                    "MISSING_DELIVERY_MAP:%s (a %s sheet needs %s)"
                    % (".".join(path), "/".join(sorted(deliveries)),
                       " and ".join(missing)))
    try:
        _MS.assert_no_contradiction(tags, sheet)
    except Exception as exc:  # MusicStyleError -> rejection
        contradicted = True
        errors.append("NEGATIVE_TAG_CONTRADICTION:%s" % exc)

    banned: List[str] = []
    try:
        texts = _payload_spoken_texts(request)
    except NoEchoError as exc:
        return _envelope("rejected", "spoken-part-invalid", [str(exc)],
                         request=request)
    for text in texts:
        for word in refused_style_words(text):
            if word not in banned:
                banned.append(word)
    for word in banned:
        errors.append(
            "BANNED_STYLE_WORD_IN_SPOKEN:%s (a spoken part never uses %r)"
            % (word, word))

    provider = request.get("provider")
    if isinstance(provider, str) and provider.strip() and \
            provider.strip().lower() != PROVIDER:
        errors.append("WRONG_PROVIDER:%s (only %s builds this payload)"
                      % (provider, PROVIDER))
    kie_path = request.get("kie_path")
    if isinstance(kie_path, str) and kie_path.strip() and \
            kie_path.strip() != KIE_PATH:
        errors.append("WRONG_KIE_PATH:%s (only %s is the permitted KIE path)"
                      % (kie_path, KIE_PATH))

    if errors:
        if banned:
            reason = "banned-spoken-style-word"
        elif any(e.startswith("BANNED_SONG_STYLE_WORD_IN_STYLE:")
                 for e in errors):
            reason = "banned-song-style-word"
        elif contradicted:
            reason = "negative-tag-contradiction"
        elif map_missing:
            reason = "delivery-map-missing"
        else:
            reason = "no-echo-rule-incomplete"
        return _envelope("rejected", reason, errors, request=request)
    return _envelope("ok", "", [], request=request)


def main(argv: Optional[list] = None) -> int:  # pragma: no cover - thin CLI
    """``--check`` a JSON Suno payload on stdin/file; exit 0 only if D22a holds."""
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(
        description="Check a Suno payload against the D22a no-echo rule.")
    parser.add_argument("--file", default=None,
                        help="payload JSON (default: stdin)")
    args = parser.parse_args(argv)
    raw = open(args.file, "r", encoding="utf-8").read() if args.file \
        else sys.stdin.read()
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        sys.stderr.write("REQUEST_INVALID: %s\n" % exc)
        return 1
    result = check(payload)
    sys.stdout.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0 if result["outcome"] == "ok" else 4


if __name__ == "__main__":
    raise SystemExit(main())
