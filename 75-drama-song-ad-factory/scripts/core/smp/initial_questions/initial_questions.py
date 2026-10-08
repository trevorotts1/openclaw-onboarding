#!/usr/bin/env python3
"""Planner setup: the drama-song block (Owner D27 / D35, plan section 6.15).

Skill 35's initial (setup) questions gain ONE block. Everything here is
prompt-building and answer-resolution -- pure data, stdlib only. It never
opens a network connection, never spawns a process, never spends money and
never talks to a provider: Skill 74 stays the only KIE path in this build,
and the caller passes its mode in as ``kie_active``.

The block (plan 6.15, transcribed):

  * "Do you want a drama song video every week?" -- default YES when the
    client's KIE connection is switched on, otherwise NO (the default flips
    with the adapter mode; an explicit client answer always wins, and the
    weekly step re-checks the mode at run time anyway).
  * Look, music, voice and length are asked ONCE, with the defaults already
    selected so the client can just say yes: Lifelike 3D / Soul Ballad /
    All Suno / 60 seconds (90 seconds optional, nothing longer is offered
    here -- the long menu belongs to the factory intake, not the planner).
  * The weekly call to action and link default to the planner's own weekly
    action link (``SOCIAL_MEDIA_ACTION_LINK``).
  * One combined ask (manual C4 step 4) fills the weekly brief: "What should
    viewers do, and what is your weekly video budget?" Offer, audience,
    action and a weekly ``budget_minor`` / ``budget_currency`` land in the
    record, so Skill 75's three-question intake is never reached from setup.

Resolved answers become the style record the weekly step reads::

    {enabled, look, music, voice, length, cta_text, cta_link,
     offer, audience, action, budget_minor, budget_currency, updated_at}

``enabled`` defaults to ``kie_active``; an explicit weekly yes/no overrides
it. With KIE switched off and no answer the record comes out disabled, and
if the client did say yes the weekly step skips at run time with a
client-facing reason (never a fallback to a private KIE client).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

#: D25 (decision log 38, 2026-10-07): Sketch to Life is always All Suno.
#: The intake gate lives with the choice card; core/ goes on the path so this
#: module still runs standalone from a plain ``python3 ...`` invocation.
_CORE_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _CORE_DIR not in sys.path:
    sys.path.insert(0, _CORE_DIR)
from choice_card.stl_voice_guard import (             # noqa: E402
    CLIENT_REASON as STL_CLIENT_REASON,
    REASON_CODE as STL_REASON_CODE,
    guard_intake,
)

SCHEMA_VERSION = "blackceo.smp.initial-questions/v1"
TOOL_VERSION = "0.1.0"

#: Where the resolved record is stored on the client box (brief; overridable).
#: The literal stays ``~``-relative so no host path lands in the source.
STYLE_PATH_TEMPLATE = "~/.openclaw/workspace/social-media-planner/drama-song-style.json"
#: M8: Docker boxes keep OpenClaw at /data/.openclaw (wire.sh's two-line rule),
#: so the same file has to be found there too. The sub-path is taken from the
#: template above, so the two cannot drift apart.
_OC_ROOT = ("/data/.openclaw" if os.path.isdir("/data/.openclaw")
            else os.path.expanduser("~/.openclaw"))
DEFAULT_STYLE_PATH = os.path.join(_OC_ROOT,
                                  STYLE_PATH_TEMPLATE.split(".openclaw/", 1)[1])

#: The brief fields. The first eight are the plan 6.15 style record; the last
#: five are the essentials Skill 75's intake needs (manual C4 step 4), asked
#: once at setup so the weekly brief never lands in the factory's
#: ``missing-essentials`` loop. Offer / audience / action / budget never get
#: a default value here -- a blank field means the factory asks for it.
STYLE_FIELDS = ("enabled", "look", "music", "voice", "length",
                "cta_text", "cta_link", "offer", "audience", "action",
                "budget_minor", "budget_currency", "updated_at")

#: The five fields the weekly brief must carry (manual C4 step 4).
BRIEF_ESSENTIALS = ("offer", "audience", "action", "budget_minor",
                    "budget_currency")

#: Fill-ins for the five essentials when a pre-existing style record predates
#: them: blank / zero only, never an invented offer, audience or budget.
ESSENTIAL_DEFAULTS = {
    "offer": "",
    "audience": "",
    "action": "",
    "budget_minor": 0,
    "budget_currency": "",
}

#: Menu order carries the default first, exactly as plan 4.1 prints it.
LOOKS = (
    ("lifelike-3d", "Lifelike 3D"),
    ("2d-hand-painted", "2D Hand-Painted"),
    ("sketch-to-life", "Sketch to Life"),
    ("canvas-to-life", "Canvas to Life"),
    ("canvas-to-3d", "Canvas to 3D"),
)
MUSICS = (
    ("soul-ballad", "Soul Ballad"),
    ("rnb-flow", "R&B Flow"),
    ("soul-rise", "Soul Rise"),
)
VOICES = (
    ("all_suno", "All Suno"),
    ("velvet_voiceover", "Velvet Voiceover"),
)

#: Plan 6.15: the planner offers 60 (default) and 90 (optional), nothing else.
LENGTHS = (60, 90)
DEFAULT_LENGTH = 60

#: Manual C4 step 4: the one setup ask that fills the weekly brief with offer,
#: audience, action and a weekly budget. It is ONE question in ONE message, so
#: Skill 75's three-question intake cap is never exceeded: asking it here
#: REMOVES up to three questions from intake instead of adding to them.
Q_WEEKLY_BRIEF = (
    "What should viewers do, and what is your weekly video budget?")

SOURCE = "Owner D27/D35 2026-10-07, plan 6.15"


class InitialQuestionsError(Exception):
    """A refusal this block owns: an off-menu answer or a missing link."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def _norm(text) -> str:
    """Case/separator-insensitive normal form for menu matching."""
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def _menu_lookup(table):
    """normal form of id AND label -> label, so either spelling matches.

    The normal forms of id and label can differ (``rnb-flow`` vs ``R&B
    Flow``), so both keys are indexed.
    """
    out = {}
    for key, label in table:
        out[_norm(key)] = label
        out[_norm(label)] = label
    return out


LOOK_BY_NORM = _menu_lookup(LOOKS)
MUSIC_BY_NORM = _menu_lookup(MUSICS)
VOICE_BY_NORM = _menu_lookup(VOICES)

#: The plain refusal spellings for a yes/no question.
_YES = frozenset(("yes", "y", "true", "t", "on", "sure", "yeah", "yep"))
_NO = frozenset(("no", "n", "false", "f", "off", "nope"))


def default_weekly(kie_active: bool) -> str:
    """Plan 6.15: the weekly question defaults to yes only when KIE is on."""
    return "yes" if kie_active else "no"


def resolve_weekly(answer, kie_active: bool) -> bool:
    """Explicit yes/no wins; no answer falls back to the KIE-dependent default."""
    if answer is None:
        return bool(kie_active)
    if isinstance(answer, bool):
        return answer
    key = _norm(answer)
    if key in _YES:
        return True
    if key in _NO:
        return False
    raise InitialQuestionsError(
        "WEEKLY_ANSWER_INVALID",
        "weekly answer %r is not yes or no" % (answer,),
    )


def resolve_menu(answer, table, code: str, field: str) -> str:
    """Accept an id or a label, return the label; refuse anything off-menu."""
    if answer is None or (isinstance(answer, str) and not answer.strip()):
        return table[0][1]                       # pre-selected default
    if not isinstance(answer, str):
        raise InitialQuestionsError(
            code, "%s must be a string, got %r" % (field, answer))
    label = _menu_lookup(table).get(_norm(answer))
    if label is None:
        raise InitialQuestionsError(
            code, "%s %r is not one of %s"
            % (field, answer, [lbl for _, lbl in table]))
    return label


def resolve_length(answer) -> int:
    """60 or 90 only (plan 6.15); the long menu is not offered here."""
    if answer is None or (isinstance(answer, str) and not answer.strip()):
        return DEFAULT_LENGTH
    if isinstance(answer, bool):
        raise InitialQuestionsError(
            "LENGTH_NOT_OFFERED", "length must be 60 or 90, got %r" % (answer,))
    if isinstance(answer, (int, float)) and not isinstance(answer, bool):
        value = int(answer)
    else:
        match = re.match(r"^\s*(\d+)", str(answer))
        if not match:
            raise InitialQuestionsError(
                "LENGTH_NOT_OFFERED", "length %r is not 60 or 90" % (answer,))
        value = int(match.group(1))
    if value not in LENGTHS:
        raise InitialQuestionsError(
            "LENGTH_NOT_OFFERED",
            "length %d is not offered to the planner (60 or 90 only)" % value)
    return value


#: Currency symbols and codes the plain-language budget accepts. Only these
#: are recognised; anything else is refused by name rather than guessed.
CURRENCY_SYMBOLS = {
    "$": "USD", "usd": "USD", "us$": "USD",
    "£": "GBP", "gbp": "GBP",
    "€": "EUR", "eur": "EUR",
    "c$": "CAD", "cad": "CAD",
    "a$": "AUD", "aud": "AUD",
}
#: Every bare unit word the budget accepts, next to the symbols above.
BUDGET_UNITS = frozenset(("usd", "gbp", "eur", "cad", "aud",
                          "credit", "credits"))

BUDGET_RE = re.compile(
    r"^\s*(?P<sym>[$£€]|US\$|C\$|A\$|USD|GBP|EUR|CAD|AUD)?\s*"
    r"(?P<amount>\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>[a-zA-Z]+)?\s*$",
    re.IGNORECASE,
)


def resolve_budget(answer) -> "tuple[int, str]":
    """Plain-language weekly budget -> ``(budget_minor, budget_currency)``.

    Accepts the shapes a client actually types: ``25``, ``$25``, ``$25.00``,
    ``25 USD``, ``25 credits``. Credits are kept as-is because Skill 74 prices
    in credits too; the parser never converts and never invents a currency.
    A blank answer stays blank (``0`` / ``""``) so the factory asks for it.
    """
    if answer is None or (isinstance(answer, str) and not answer.strip()):
        return 0, ""
    if isinstance(answer, bool):
        raise InitialQuestionsError(
            "BUDGET_UNREADABLE",
            "weekly budget must be an amount, got %r" % (answer,))
    if isinstance(answer, (int, float)) and not isinstance(answer, bool):
        amount = float(answer)
        currency = ""
    else:
        text = str(answer).strip()
        m = BUDGET_RE.match(text)
        if not m or not m.group("amount"):
            raise InitialQuestionsError(
                "BUDGET_UNREADABLE",
                "weekly budget %r is not an amount (for example: $25, "
                "25 USD, 25 credits)" % (answer,))
        amount = float(m.group("amount").replace(",", ""))
        sym = (m.group("sym") or "").strip()
        unit = (m.group("unit") or "").strip()
        if sym:
            currency = CURRENCY_SYMBOLS.get(sym.lower(), "")
            if not currency:
                raise InitialQuestionsError(
                    "BUDGET_CURRENCY_UNKNOWN",
                    "weekly budget currency %r is not one of %s"
                    % (sym, sorted(set(CURRENCY_SYMBOLS.values()))))
        elif unit:
            # A bare unit word is accepted only when it names a currency or
            # the credit unit Skill 74 prices in -- never invented from
            # whatever word happens to sit next to the number.
            if unit.lower() not in BUDGET_UNITS:
                raise InitialQuestionsError(
                    "BUDGET_CURRENCY_UNKNOWN",
                    "weekly budget unit %r is not one of %s"
                    % (unit, sorted(BUDGET_UNITS)))
            currency = unit.upper()
        else:
            currency = ""
    if amount < 0:
        raise InitialQuestionsError(
            "BUDGET_UNREADABLE",
            "weekly budget must not be negative; got %r" % (answer,))
    return int(round(amount * 100)), currency


#: A plain-language amount inside the one combined setup sentence
#: ("... and what is your weekly video budget?  Answer: $25").
SENTENCE_BUDGET_RE = re.compile(
    r"(?:budget\s*(?:is|of|:)?\s*)?"
    r"([$\u00a3\u20ac]|US\$|C\$|A\$)\s*"
    r"(\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)


def _budget_from_sentence(answer: Any) -> Optional[str]:
    """The amount in the one combined setup answer, or None when absent.

    Never guesses: a sentence with no amount yields None and the budget
    stays blank, so Skill 75's intake asks for it instead of inventing one.
    """
    if not isinstance(answer, str) or not answer.strip():
        return None
    m = SENTENCE_BUDGET_RE.search(answer)
    if not m:
        return None
    return "%s%s" % (m.group(1), m.group(2))


def resolve_weekly_budget(answers: Dict[str, Any]) -> "tuple[int, str]":
    """The weekly budget out of one setup answer bag.

    Priority: explicit ``budget_minor`` / ``budget_currency`` (already minor
    units), then ``budget`` / ``weekly_budget`` (parsed), then the amount
    carried inside the one combined ``weekly_brief`` sentence. Nothing is
    ever invented -- an absent budget stays ``0`` / ``""`` so the factory
    asks for it.
    """
    if not isinstance(answers, dict):
        return 0, ""
    if "budget_minor" in answers or "budget_currency" in answers:
        try:
            minor = int(answers.get("budget_minor") or 0)
        except (TypeError, ValueError):
            raise InitialQuestionsError(
                "BUDGET_UNREADABLE",
                "budget_minor must be a whole number of minor units")
        if minor < 0:
            raise InitialQuestionsError(
                "BUDGET_UNREADABLE", "budget_minor must not be negative")
        return minor, str(answers.get("budget_currency") or "").strip()
    raw = answers.get("budget")
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raw = answers.get("weekly_budget")
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raw = _budget_from_sentence(answers.get("weekly_brief"))
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return 0, ""
    return resolve_budget(raw)


def build_block(kie_active: bool, weekly_action_link: str = "") -> Dict[str, Any]:
    """The one drama-song setup block, defaults pre-selected (plan 6.15)."""
    link = str(weekly_action_link or "").strip()
    return {
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "block": "drama-song",
        "source": SOURCE,
        "kie_active": bool(kie_active),
        "questions": [
            {
                "id": "weekly",
                "prompt": "Do you want a drama song video every week?",
                "type": "yes_no",
                "default": default_weekly(kie_active),
                "cadence": "weekly",
            },
            {
                "id": "look",
                "prompt": "Which look?",
                "type": "choice",
                "options": [label for _, label in LOOKS],
                "default": LOOKS[0][1],
                "cadence": "once",
            },
            {
                "id": "music",
                "prompt": "Which music style?",
                "type": "choice",
                "options": [label for _, label in MUSICS],
                "default": MUSICS[0][1],
                "cadence": "once",
            },
            {
                "id": "voice",
                "prompt": "Which voice?",
                "type": "choice",
                "options": [label for _, label in VOICES],
                "default": VOICES[0][1],
                "cadence": "once",
            },
            {
                "id": "length",
                "prompt": "How long should each weekly video be?",
                "type": "choice",
                "options": [str(n) for n in LENGTHS],
                "default": str(DEFAULT_LENGTH),
                "optional": ["90"],
                "cadence": "once",
            },
            {
                "id": "cta",
                "prompt": "What should the weekly call to action and link be?",
                "type": "text",
                "default": link or None,
                "required": True,
                "cadence": "once",
            },
            {
                "id": "weekly_brief",
                "prompt": Q_WEEKLY_BRIEF,
                "type": "text",
                "default": None,
                "cadence": "once",
                "fills": list(BRIEF_ESSENTIALS),
            },
        ],
    }


def resolve_style(answers: Optional[Dict[str, Any]] = None,
                  kie_active: bool = True,
                  weekly_action_link: str = "",
                  now: Optional[datetime] = None) -> Dict[str, Any]:
    """Answers -> the style record the weekly step reads.

    Missing answers fall back to the pre-selected defaults. An off-menu
    look/music/voice, a length outside 60/90, a non yes/no weekly answer or
    an empty call-to-action link refuses by name instead of guessing.

    D25 (decision log 38): Sketch to Life + Velvet Voiceover is refused here
    too, by name, with the client-facing reason -- the exception's ``reask``
    carries the question whose ``preselected`` is All Suno on the same look,
    so the planner re-asks once instead of silently swapping the choice.
    """
    answers = dict(answers or {})
    link = str(weekly_action_link or "").strip()

    cta_link = str(answers.get("cta_link") or "").strip() or link
    if not cta_link:
        raise InitialQuestionsError(
            "CTA_LINK_MISSING",
            "no call-to-action link: give cta_link or the planner's weekly "
            "action link")
    cta_text = str(answers.get("cta_text") or "").strip() or cta_link

    # Manual C4 step 4: the essentials the weekly brief must carry. Offer,
    # audience and action are taken only from their own keys -- a combined
    # answer is never split into an invented offer or action. The budget is
    # the one value read out of the combined sentence.
    offer = str(answers.get("offer") or "").strip()
    audience = str(answers.get("audience") or "").strip()
    action = str(answers.get("action") or "").strip()
    budget_minor, budget_currency = resolve_weekly_budget(answers)

    stamp = now or datetime.now(timezone.utc)
    updated = stamp.astimezone(timezone.utc).replace(microsecond=0)
    updated = updated.isoformat().replace("+00:00", "Z")

    style = {
        "enabled": resolve_weekly(answers.get("weekly"), kie_active),
        "look": resolve_menu(answers.get("look"), LOOKS,
                             "LOOK_UNKNOWN", "look"),
        "music": resolve_menu(answers.get("music"), MUSICS,
                              "MUSIC_UNKNOWN", "music"),
        "voice": resolve_menu(answers.get("voice"), VOICES,
                              "VOICE_UNKNOWN", "voice"),
        "length": resolve_length(answers.get("length")),
        "cta_text": cta_text,
        "cta_link": cta_link,
        "offer": offer,
        "audience": audience,
        "action": action,
        "budget_minor": budget_minor,
        "budget_currency": budget_currency,
        "updated_at": updated,
    }

    # D25: the one forbidden pair never leaves intake.
    verdict = guard_intake(style["look"], style["voice"])
    if verdict["outcome"] == "refused":
        error = InitialQuestionsError(STL_REASON_CODE, STL_CLIENT_REASON)
        error.reask = verdict
        raise error
    return style


def save_style(style: Dict[str, Any], path: str = DEFAULT_STYLE_PATH) -> str:
    """Persist the record atomically; refuses an incomplete record."""
    missing = [field for field in STYLE_FIELDS if field not in style]
    if missing:
        raise InitialQuestionsError(
            "STYLE_INCOMPLETE", "style record is missing %s" % missing)
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp_path = "%s.tmp.%d" % (path, os.getpid())
    with open(tmp_path, "w", encoding="utf-8") as handle:
        # brief field order, not alphabetical
        json.dump({k: style[k] for k in STYLE_FIELDS}, handle, indent=2)
        handle.write("\n")
    os.replace(tmp_path, path)
    return path


def load_style(path: str = DEFAULT_STYLE_PATH) -> Optional[Dict[str, Any]]:
    """The stored record, or None when there is none yet / it is unreadable.

    A record written before the weekly essentials existed loads with those
    five fields blank (``0`` / ``""``) rather than being rejected: the
    factory then asks for them instead of the planner inventing any.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    required = ("enabled", "look", "music", "voice", "length",
                "cta_text", "cta_link", "updated_at")
    if any(field not in data for field in required):
        return None
    out = {}
    for field in STYLE_FIELDS:
        if field in data:
            out[field] = data[field]
        else:
            out[field] = ESSENTIAL_DEFAULTS.get(field)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Skill 35 drama-song setup block (plan 6.15).")
    parser.add_argument("--kie-active", action="store_true",
                        help="Skill 74 adapter is in active mode")
    parser.add_argument("--action-link", default="",
                        help="the planner's weekly action link")
    parser.add_argument("--weekly", default=None, help="yes / no")
    parser.add_argument("--look", default=None)
    parser.add_argument("--music", default=None)
    parser.add_argument("--voice", default=None)
    parser.add_argument("--length", default=None)
    parser.add_argument("--cta-text", default=None)
    parser.add_argument("--cta-link", default=None)
    parser.add_argument("--offer", default=None,
                        help="what the weekly video promotes (offer)")
    parser.add_argument("--audience", default=None,
                        help="who the weekly video is for")
    parser.add_argument("--action", default=None,
                        help="what viewers should do")
    parser.add_argument("--weekly-brief", default=None,
                        help="the one combined setup answer: what viewers do "
                             "and the weekly video budget")
    parser.add_argument("--budget", default=None,
                        help="weekly video budget, for example: $25")
    parser.add_argument("--path", default=DEFAULT_STYLE_PATH,
                        help="style record path")
    parser.add_argument("--block", action="store_true",
                        help="print the setup block instead of resolving")
    parser.add_argument("--save", action="store_true",
                        help="write the resolved record to --path")
    args = parser.parse_args(argv)

    if args.block:
        sys.stdout.write(json.dumps(
            build_block(args.kie_active, args.action_link),
            indent=2, sort_keys=True) + "\n")
        return 0

    answers = {key: getattr(args, key) for key in
               ("weekly", "look", "music", "voice", "length")
               if getattr(args, key) is not None}
    if args.cta_text is not None:
        answers["cta_text"] = args.cta_text
    if args.cta_link is not None:
        answers["cta_link"] = args.cta_link
    for key in ("offer", "audience", "action", "weekly_brief", "budget"):
        value = getattr(args, key)
        if value is not None:
            answers[key] = value
    try:
        style = resolve_style(answers, kie_active=args.kie_active,
                              weekly_action_link=args.action_link)
        if args.save:
            save_style(style, args.path)
    except InitialQuestionsError as exc:
        sys.stderr.write("%s\n" % exc)
        return 1
    sys.stdout.write(json.dumps(style, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
