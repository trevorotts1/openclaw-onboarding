#!/usr/bin/env python3
"""no_echo.py: the SMP weekly drama-song step's Suno request carries D22a.

Owner unit AF-SMP-U1 — Decision log 36-37 applied to Skill 35 (owner
2026-10-07), plan 6.15. stdlib only, zero paid calls.

What the weekly step's Suno request must always carry:

  * the dry close-microphone vocal rule (``dry_close_mic`` plus the phrase
    ``dry close-microphone vocal`` inside the prompt);
  * the seven negative tags — reverb, echo, delay, hall, ethereal, ambient,
    choir pad — set on the request, not merely implied by the prose;
  * the three style words never used in a spoken part's style text:
    spacious, cinematic, choir. A spoken part that names one is refused by
    name (``BANNED_STYLE_WORD:<word>``) instead of being shipped.

The module builds and verifies request dictionaries only. It carries no
transport of its own: Skill 74 is the only permitted KIE path, so nothing
here imports a network client or spends money. stdlib only. Ships only via
the onboarding batch train.

Deliberate scope (ponytail): spoken-part style text is checked as
``spoken_style`` (one string) and ``spoken_parts`` (list of strings or of
dicts carrying ``style``/``prompt``); the sung side of the prompt is free of
the three-word ban — D22a bans them in spoken parts.

Run: python3 core/smp/no_echo/test_no_echo.py
"""
from __future__ import annotations

import copy
import re
from typing import Any, Dict, Iterable, List, Optional

SCHEMA_VERSION = "blackceo.smp/no-echo/v1"
TOOL_VERSION = "0.1.0"
RULE_ID = "D22a"

#: The step this rule rides on.
STEP = "smp-weekly-drama-song"
#: The one producer. Nothing else generates this request's audio.
PROVIDER = "suno"
#: The only permitted KIE path (Skill 74); this module never becomes one.
KIE_PATH = "Skill 74"

#: D22a: what the weekly request asks for, in the owner's words.
DRY_RULE = "dry close-microphone vocal"

#: D22a / D37: exactly seven negative tags, set on every weekly request.
NEGATIVE_TAGS = (
    "reverb",
    "echo",
    "delay",
    "hall",
    "ethereal",
    "ambient",
    "choir pad",
)

#: D22a: three style words a spoken part never uses.
SPOKEN_BANNED_STYLE_WORDS = ("spacious", "cinematic", "choir")

RULE_TEXT = (
    "Dry close-microphone vocal; negative tags reverb, echo, delay, hall, "
    "ethereal, ambient, choir pad; a spoken part never uses spacious, "
    "cinematic or choir (D22a)."
)
CARD_LINE = (
    "  Audio:       dry close-mic vocals + 7 negative tags; spoken parts "
    "never use spacious / cinematic / choir (D22a)"
)

_BANNED_PATTERNS = tuple(
    (word, re.compile(r"\b%s\b" % re.escape(word), re.IGNORECASE))
    for word in SPOKEN_BANNED_STYLE_WORDS
)
_DRY_PHRASE = re.compile(
    r"\bdry\b[\s-]*(?:close[\s-]*mic(?:rophone)?|close[\s-]*microphone)\b",
    re.IGNORECASE,
)


class NoEchoError(Exception):
    """Structural problem with the caller's input (refusal, never a ship)."""

    def __init__(self, code: str, message: str):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def _envelope(outcome: str, reason_code: str, errors: Iterable[str],
              **extra: Any) -> Dict[str, Any]:
    env = {
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "outcome": outcome,
        "reason_code": reason_code,
        "errors": list(errors),
        "step": STEP,
        "provider": PROVIDER,
        "kie_path": KIE_PATH,
        "rule": RULE_TEXT,
        "card_line": CARD_LINE,
    }
    env.update(extra)
    return env


# --------------------------------------------------------------- surface ---

def rule_text() -> str:
    """The D22a rule exactly as it is stamped on every request."""
    return RULE_TEXT


def card_line() -> str:
    """The weekly step's card line stating the rule."""
    return CARD_LINE


def negative_tags() -> List[str]:
    """The seven negative tags, as a list a request can carry."""
    return list(NEGATIVE_TAGS)


def refused_style_words(text: Any) -> List[str]:
    """Which of the three banned style words this spoken text names.

    Case-insensitive, whole-word: a spoken part asking for "Cinematic" or
    "choir pad" is refused under ``cinematic`` / ``choir``.
    """
    if not isinstance(text, str) or not text.strip():
        return []
    return [word for word, pattern in _BANNED_PATTERNS if pattern.search(text)]


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


def style_phrase(style: Any) -> str:
    """Render the stored weekly style the way the request prompt shows it."""
    if style is None:
        return ""
    if isinstance(style, str):
        return style.strip()
    if isinstance(style, dict):
        free_text = str(style.get("style_text") or "").strip()
        if free_text:
            return free_text
        parts = [str(style.get(k) or "").strip()
                 for k in ("look", "music", "voice")]
        parts = [p for p in parts if p]
        length = style.get("length_seconds")
        if length:
            parts.append("%s seconds" % length)
        return ", ".join(parts)
    raise NoEchoError("STYLE_INVALID",
                      "style must be a str, dict or None, got %r"
                      % type(style).__name__)


def _has_dry_rule(text: str) -> bool:
    return bool(_DRY_PHRASE.search(text or ""))


# ---------------------------------------------------------------- build ----

def stamp(request: Any = None, *, prompt: Optional[str] = None,
          spoken_style: Optional[str] = None,
          spoken_parts: Optional[list] = None) -> Dict[str, Any]:
    """Copy ``request`` with the D22a rule written on it.

    Refuses (``NoEchoError``) when any spoken part names a banned style
    word — the rule is never written over a contradicting request. The
    caller's dictionary is never mutated.
    """
    if request is None:
        request = {}
    if not isinstance(request, dict):
        raise NoEchoError("REQUEST_INVALID",
                          "request must be a dict, got %r"
                          % type(request).__name__)

    texts = _spoken_texts(spoken_style, spoken_parts)
    for text in texts:
        for word in refused_style_words(text):
            raise NoEchoError(
                "BANNED_STYLE_WORD",
                "%s: a spoken part never uses %r (D22a: spacious, cinematic, "
                "choir)" % (word, word))

    out = copy.deepcopy(request)
    out.setdefault("schema_version", SCHEMA_VERSION)
    out.setdefault("tool_version", TOOL_VERSION)
    out.setdefault("step", STEP)
    out.setdefault("provider", PROVIDER)
    out.setdefault("kie_path", KIE_PATH)

    base = prompt if prompt is not None else str(out.get("prompt") or "")
    base = base.strip().rstrip(",")
    if _has_dry_rule(base):
        base = base.strip()
    else:
        base = ("%s, %s" % (base, DRY_RULE)) if base else DRY_RULE
    out["prompt"] = base
    out["dry_close_mic"] = True
    out["negative_tags"] = list(NEGATIVE_TAGS)
    out["style_words_banned"] = list(SPOKEN_BANNED_STYLE_WORDS)
    out["rule"] = RULE_TEXT
    out["card_line"] = CARD_LINE
    if spoken_style is not None:
        out["spoken_style"] = spoken_style
    if spoken_parts is not None:
        out["spoken_parts"] = copy.deepcopy(spoken_parts)
    return out


def weekly_request(style: Any = None, *, prompt: Optional[str] = None,
                   spoken_style: Optional[str] = None,
                   spoken_parts: Optional[list] = None,
                   request_id: Optional[str] = None) -> Dict[str, Any]:
    """The SMP weekly drama-song step's Suno request, D22a stamped.

    Envelope, not an exception: a banned spoken style word comes back as
    ``outcome=rejected`` naming the word, and no request is built.
    """
    try:
        texts = _spoken_texts(spoken_style, spoken_parts)
    except NoEchoError as exc:
        return _envelope("rejected", "spoken-part-invalid", [str(exc)],
                         request=None, request_id=request_id)
    banned = []
    for text in texts:
        for word in refused_style_words(text):
            if word not in banned:
                banned.append(word)
    if banned:
        return _envelope(
            "rejected", "banned-spoken-style-word",
            ["BANNED_STYLE_WORD:%s (a spoken part never uses %r: D22a)"
             % (word, word) for word in banned],
            request=None, request_id=request_id,
            refused_words=banned)
    base = prompt if prompt is not None else style_phrase(style)
    request = stamp({}, prompt=base, spoken_style=spoken_style,
                    spoken_parts=spoken_parts)
    if request_id is not None:
        request["request_id"] = request_id
    return _envelope("ok", "", [], request=request, request_id=request_id,
                     refused_words=[])


# ---------------------------------------------------------------- check ----

def check(request: Any) -> Dict[str, Any]:
    """Verify a request already carries D22a. Fail closed on every gap."""
    if not isinstance(request, dict):
        return _envelope("rejected", "request-invalid",
                         ["REQUEST_INVALID:%r (a request is a dict)"
                          % type(request).__name__],
                         request=None)
    errors: List[str] = []

    prompt = request.get("prompt")
    prompt = prompt if isinstance(prompt, str) else ""
    if request.get("dry_close_mic") is not True:
        errors.append("MISSING_DRY_RULE:dry_close_mic is not True")
    if not _has_dry_rule(prompt):
        errors.append(
            "MISSING_DRY_RULE:prompt does not ask for %r" % DRY_RULE)

    tags = request.get("negative_tags")
    tags = [t for t in tags if isinstance(t, str)] if isinstance(
        tags, (list, tuple)) else []
    for tag in NEGATIVE_TAGS:
        if tag not in tags:
            errors.append("MISSING_NEGATIVE_TAG:%s" % tag)

    guards = request.get("style_words_banned")
    guards = [str(g).lower() for g in guards] if isinstance(
        guards, (list, tuple)) else []
    for word in SPOKEN_BANNED_STYLE_WORDS:
        if word not in guards:
            errors.append("MISSING_BANNED_STYLE_WORD_GUARD:%s" % word)

    banned: List[str] = []
    try:
        texts = _spoken_texts(request.get("spoken_style"),
                              request.get("spoken_parts"))
    except NoEchoError as exc:
        return _envelope("rejected", "spoken-part-invalid", [str(exc)],
                         request=None)
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
        errors.append("WRONG_PROVIDER:%s (only %s makes this audio)"
                      % (provider, PROVIDER))
    kie_path = request.get("kie_path")
    if isinstance(kie_path, str) and kie_path.strip() and \
            kie_path.strip() != KIE_PATH:
        errors.append("WRONG_KIE_PATH:%s (only %s is the permitted KIE path)"
                      % (kie_path, KIE_PATH))

    if errors:
        reason = ("banned-spoken-style-word" if banned
                  else "no-echo-rule-incomplete")
        return _envelope("rejected", reason, errors, request=request)
    return _envelope("ok", "", [], request=request)


def main(argv: Optional[list] = None) -> int:  # pragma: no cover - thin CLI
    """``--check`` a JSON request on stdin/file; exit 0 only when D22a holds."""
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(
        description="Check an SMP weekly Suno request against D22a.")
    parser.add_argument("--file", default=None,
                        help="request JSON (default: stdin)")
    args = parser.parse_args(argv)
    raw = open(args.file, "r", encoding="utf-8").read() if args.file \
        else sys.stdin.read()
    try:
        request = json.loads(raw)
    except ValueError as exc:
        sys.stderr.write("REQUEST_INVALID: %s\n" % exc)
        return 1
    result = check(request)
    sys.stdout.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0 if result["outcome"] == "ok" else 4


if __name__ == "__main__":
    raise SystemExit(main())
