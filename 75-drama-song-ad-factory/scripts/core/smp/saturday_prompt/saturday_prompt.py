#!/usr/bin/env python3
"""saturday_prompt.py: the Saturday theme prompt gains the drama-song style
line, and "no answer" means keep the style (Owner D27 / plan 6.15, 2026-10-07).

One added line on the planner's Saturday theme question:

    Drama song of the week: keep <current style> or change it?

Rules that come straight from plan 6.15:
  * no answer (empty reply)  -> keep; the style persists across weeks
  * "keep"-style answer      -> keep
  * a reply naming a style    -> change to that style (it becomes the style
    that the NEXT Saturday prompt shows)
  * a bare "change" with no replacement named cannot be applied, so it keeps
    the current style rather than inventing one (fail-safe, caller may re-ask)

This module only builds and parses a text prompt and persists one small JSON
style record. It never calls Skill 74, Skill 75 or any network client — the
weekly step owns that, and Skill 74 is the only permitted KIE path. stdlib
only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, Optional, Union

SCHEMA_VERSION = "blackceo.smp-saturday-prompt/v1"
TOOL_VERSION = "0.1.0"

# D24 / D22 / D25 defaults — only used when no style has been stored yet.
DEFAULT_STYLE: Dict[str, Any] = {
    "look": "Lifelike 3D",
    "music": "Soul Ballad",
    "voice": "All Suno",
    "length_seconds": 60,
}

DEFAULT_STATE_PATH = os.path.expanduser(
    "~/.openclaw/data/skill35/drama-song-style.json"
)

PROMPT_PREFIX = "Theme for this week (reply any time before Sunday; a blank reply keeps last week's theme):"
DRAMA_LINE_HEAD = "Drama song of the week: keep "
DRAMA_LINE_TAIL = " or change it?"

_KEEPS = re.compile(
    r"^(keep|keep\s+it|keep\s+this|same|unchanged|no|no\s+change|stay|as\s+is)[.!,]?$",
    re.IGNORECASE,
)
_CHANGE_WITH_VALUE = re.compile(
    r"^(?:change\s+to|switch\s+to|use|make\s+it)\s+(?P<style>.+)$",
    re.IGNORECASE,
)
_CHANGE_BARE = re.compile(r"^(?:change|change\s+it|change\s+it\s+up)[.!,]?$", re.IGNORECASE)

StyleLike = Union[str, Dict[str, Any], None]


def render_style(style: StyleLike) -> str:
    """Turn a stored style into the bracketed phrase shown to the client."""
    if style is None:
        style = DEFAULT_STYLE
    if isinstance(style, str):
        text = style.strip()
        return text or render_style(DEFAULT_STYLE)
    if isinstance(style, dict):
        free_text = str(style.get("style_text") or "").strip()
        if free_text:
            return free_text
        look = str(style.get("look") or "").strip()
        music = str(style.get("music") or "").strip()
        voice = str(style.get("voice") or "").strip()
        length = style.get("length_seconds")
        parts = [p for p in (look, music, voice) if p]
        if length:
            parts.append("%s seconds" % length)
        if parts:
            return ", ".join(parts)
    return render_style(DEFAULT_STYLE)


def normalize_style(style: StyleLike) -> Dict[str, Any]:
    """Canonical stored form: the DEFAULT_STYLE shape, never None/empty."""
    if isinstance(style, dict) and str(style.get("style_text") or "").strip():
        out = dict(DEFAULT_STYLE)
        out["style_text"] = str(style["style_text"]).strip()
        return out
    if isinstance(style, dict) and any(
        str(style.get(k) or "").strip() for k in ("look", "music", "voice")
    ):
        out = dict(DEFAULT_STYLE)
        for key in ("look", "music", "voice"):
            value = str(style.get(key) or "").strip()
            if value:
                out[key] = value
        try:
            length = int(style.get("length_seconds") or DEFAULT_STYLE["length_seconds"])
        except (TypeError, ValueError):
            length = DEFAULT_STYLE["length_seconds"]
        out["length_seconds"] = length
        return out
    if isinstance(style, str) and style.strip():
        return {"style_text": style.strip(), "length_seconds": DEFAULT_STYLE["length_seconds"]}
    return dict(DEFAULT_STYLE)


def build_saturday_prompt(current_style: StyleLike = None, theme: Optional[str] = None) -> str:
    """The full Saturday message: theme question plus the drama-song line."""
    line = DRAMA_LINE_HEAD + render_style(current_style) + DRAMA_LINE_TAIL
    header = PROMPT_PREFIX
    if theme and str(theme).strip():
        header = "%s %s" % (header, str(theme).strip())
    return "%s\n%s" % (header, line)


def parse_reply(reply: Optional[str], current_style: StyleLike = None) -> Dict[str, Any]:
    """Apply the owner's rule: no answer means keep.

    Returns {"answered", "action", "style", "style_text", "reason"}.
    """
    current = normalize_style(current_style)
    raw = "" if reply is None else str(reply)
    text = raw.strip()

    if not text:
        return {
            "answered": False,
            "action": "keep",
            "style": dict(current),
            "style_text": render_style(current),
            "reason": "no_answer_keeps_style",
        }

    if _KEEPS.match(text):
        return {
            "answered": True,
            "action": "keep",
            "style": dict(current),
            "style_text": render_style(current),
            "reason": "explicit_keep",
        }

    if _CHANGE_BARE.match(text):
        # "change" with no replacement cannot be applied — keep, do not invent.
        return {
            "answered": True,
            "action": "keep",
            "style": dict(current),
            "style_text": render_style(current),
            "reason": "change_without_a_named_style_keeps_current",
        }

    match = _CHANGE_WITH_VALUE.match(text)
    new_text = match.group("style").strip() if match else text
    if not new_text:
        return {
            "answered": True,
            "action": "keep",
            "style": dict(current),
            "style_text": render_style(current),
            "reason": "change_without_a_named_style_keeps_current",
        }
    new_style = normalize_style(
        {
            "style_text": new_text,
            "length_seconds": current.get(
                "length_seconds", DEFAULT_STYLE["length_seconds"]
            ),
        }
    )
    return {
        "answered": True,
        "action": "change",
        "style": new_style,
        "style_text": render_style(new_style),
        "reason": "style_changed_from_reply",
    }


def resolve_week(reply: Optional[str], current_style: StyleLike = None) -> Dict[str, Any]:
    """Parse this Saturday's reply and hand back the style that now persists."""
    decision = parse_reply(reply, current_style)
    decision["schema_version"] = SCHEMA_VERSION
    return decision


def load_style(path: str = DEFAULT_STATE_PATH) -> Dict[str, Any]:
    """Stored style, or the defaults when nothing valid is stored yet."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError, TypeError):
        return dict(DEFAULT_STYLE)
    if isinstance(data, dict):
        style = data.get("style", data)
        return normalize_style(style)
    return dict(DEFAULT_STYLE)


def save_style(style: StyleLike, path: str = DEFAULT_STATE_PATH) -> Dict[str, Any]:
    """Persist the style so it carries into next week's prompt."""
    stored = normalize_style(style)
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "style": stored,
    }
    tmp_path = "%s.tmp.%d" % (path, os.getpid())
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(tmp_path, path)
    return stored


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Saturday theme prompt line for the weekly drama song (Skill 35)."
    )
    parser.add_argument("--state", default=DEFAULT_STATE_PATH, help="style JSON path")
    parser.add_argument("--theme", default=None, help="theme already chosen for this week")
    parser.add_argument("--reply", default=None, help="owner reply to the style question")
    parser.add_argument(
        "--apply", action="store_true", help="persist the reply before printing"
    )
    args = parser.parse_args(argv)

    current = load_style(args.state)
    if args.reply is None and not args.apply:
        sys.stdout.write(build_saturday_prompt(current, args.theme) + "\n")
        return 0

    decision = resolve_week(args.reply, current)
    if args.apply:
        decision["style"] = save_style(decision["style"], args.state)
        decision["style_text"] = render_style(decision["style"])
    sys.stdout.write(json.dumps(decision, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
