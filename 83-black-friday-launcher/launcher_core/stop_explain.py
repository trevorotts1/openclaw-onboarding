"""What the client is told when the launcher stops: four plain parts, never a dead end.

Owner order (2026-11-20): when a rule or a problem stops the work, the client is never left with no
answer. Every stop the client hears about says, in fifth-grade words:

  1. what happened, with the real numbers when there are any;
  2. why the rule exists: what it protects the client from;
  3. what will fix it;
  4. two to four numbered choices, at least one of them work the agent does.

The words live in ``references/stop-explanations.json`` (one row per stop code, grouped into families).
``explain_stop`` reads that table. An unknown code still gets four parts, built from the stop's own
plain detail with every code, path and stack trace removed. Codes stay in logs and receipts; they never
reach the client. ``tests/test_stop_explanations.py`` fails when a stop in this skill's code has no row.

Run ``python3 -m launcher_core.stop_explain <code> [detail]`` to see the message for one stop.
"""

from __future__ import annotations

import functools
import json
import re
import string
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

TABLE_PATH = Path(__file__).resolve().parent.parent / "references" / "stop-explanations.json"
PARTS = ("what_happened", "why", "fix", "choices")

_CODE = re.compile(r"\bAF-[A-Z0-9]+(?:-[A-Z0-9]+)*\b")
_PATH = re.compile(r"\S*(?:/|\\)\S*|\S+\.(?:py|json|md|sh|html|txt|pdf|png)\b")
_TRACE = re.compile(r"Traceback \(most recent call last\):.*", re.S)
_NOTHING_SPENT = re.compile(r"nothing (?:has been|was) spent", re.I)

_FALLBACK = {
    "what_happened": "I had to stop for a moment before going further.",
    "why": "I stop instead of guessing, so nothing wrong reaches your customers and nothing costs you money "
           "by mistake.",
    "fix": "I sort this out, then keep going.",
    "choices": ["I sort it out and come right back to you.",
                "I show you what's already done.",
                "We keep going with your other questions meanwhile."],
}

@functools.lru_cache(maxsize=1)
def table() -> Dict[str, Any]:
    return json.loads(TABLE_PATH.read_text(encoding="utf-8"))

def _row(code: str) -> Optional[Dict[str, Any]]:
    """The code's own row, or the nearest parent code's (AF-LAUNCH-X-Y falls back to AF-LAUNCH-X)."""
    codes = table()["codes"]
    parts = code.split("-")
    for n in range(len(parts), 2, -1):
        row = codes.get("-".join(parts[:n]))
        if row is not None:
            return row
    return codes.get(code)

def _plain(text: Any) -> str:
    """Stop text with every code, file path and stack trace taken out."""
    text = _TRACE.sub("", str(text or ""))
    text = _PATH.sub("", _CODE.sub("", text))
    text = re.sub(r"\s+([,.;:])", r"\1", re.sub(r"\s{2,}", " ", text)).strip(" :;,-")
    return text[:1].upper() + text[1:] if text else ""

def _money(minor: Any, currency: Optional[str]) -> str:
    cents = int(minor)
    if currency == "USD":
        return f"${cents // 100:,}" if cents % 100 == 0 else f"${cents / 100:,.2f}"
    amount = f"{cents / 100:,.2f}"
    return f"{amount} {currency}" if currency else amount

def _facts(found: Mapping[str, Any]) -> Dict[str, Any]:
    out = dict(found)
    currency = out.get("currency")
    for key in ("budget", "price", "amount"):
        if out.get(f"{key}_minor") is not None and key not in out:
            out[key] = _money(out[f"{key}_minor"], currency)
    return out

def _fill(text: str, facts: Mapping[str, Any]) -> Optional[str]:
    """The text with its {placeholders} filled, or None when a fact it needs is missing."""
    names = [name for _, name, _, _ in string.Formatter().parse(text) if name]
    if any(facts.get(name) in (None, "") for name in names):
        return None
    return text.format(**{name: facts[name] for name in names})

def _render(parts: Mapping[str, Any], nothing_spent: bool) -> str:
    lines = [parts["what_happened"]]
    if nothing_spent:
        lines.append("Nothing was charged.")
    lines += ["", f"Why this rule is here: {parts['why']}", "", f"What will fix it: {parts['fix']}", "",
              "Here's what I can do right now:"]
    lines += [f"{i}. {choice}" for i, choice in enumerate(parts["choices"], 1)]
    lines += ["", "Just tell me the number you'd like."]
    return "\n".join(lines)

def explain_stop(reason_code: Optional[str], facts: Optional[Mapping[str, Any]] = None,
                 envelope: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """The four-part client explanation of one stop, plus the rendered message.

    ``facts`` fills the {placeholders} with real numbers. ``envelope`` is the stop itself: its ``code``,
    ``detail`` (the refusal text) and any ``client_message`` / ``next_step`` / ``next_action`` it carries.
    A variant in the table that matches the detail fills its placeholders from the detail too.
    """
    envelope = dict(envelope or {})
    code = str(reason_code or envelope.get("code") or "")
    detail = str(envelope.get("detail") or "")
    row = _row(code) if code else None
    if row is not None and row.get("inner"):
        inner = next((c for c in _CODE.findall(detail) if c != code and _row(c) is not None), None)
        if inner is not None:
            return explain_stop(inner, facts, {**envelope, "code": inner,
                                               "detail": detail.split(inner, 1)[1]})
    found: Dict[str, Any] = dict(facts or {})
    if row is None:
        parts: Dict[str, Any] = dict(_FALLBACK)
        said = _plain(envelope.get("client_message") or detail)
        step = _plain(envelope.get("next_step") or envelope.get("next_action"))
        if said:
            parts["what_happened"] = said
        if step:
            parts["fix"] = step
    else:
        family = table()["families"][row["family"]]
        parts = {**family, **{k: v for k, v in row.items() if k != "family"}}
        for variant in row.get("variants") or family.get("variants") or []:
            match = re.search(variant["match"], detail)
            if match:
                found = {**match.groupdict(), **found}
                parts.update({k: v for k, v in variant.items() if k != "match"})
                break
    found = _facts(found)
    what = _fill(parts["what_happened"], found) or _fill(parts.get("what_happened_general") or "", found) \
        or _FALLBACK["what_happened"]
    out = {"what_happened": what, "why": parts["why"], "fix": _fill(parts["fix"], found) or _FALLBACK["fix"],
           "choices": list(parts["choices"])}
    nothing_spent = bool(found.get("nothing_spent")) or bool(_NOTHING_SPENT.search(detail))
    out["message"] = _render(out, nothing_spent)
    return out

def explain_exception(exc: BaseException) -> Dict[str, Any]:
    """The explanation of a raised refusal: its code attribute, or the first code in its text."""
    text = str(exc)
    code = getattr(exc, "code", None) or next(iter(_CODE.findall(text)), None)
    detail = getattr(exc, "detail", None) or (text.split(code, 1)[1] if code and code in text else text)
    return explain_stop(code, envelope={"code": code, "detail": detail})

def explain_violations(violations: List[str]) -> List[Dict[str, Any]]:
    """One explanation per distinct stop code in a list of "CODE: detail" violation strings."""
    seen: Dict[str, Dict[str, Any]] = {}
    for line in violations:
        code = next(iter(_CODE.findall(str(line))), "")
        if code not in seen:
            seen[code] = explain_stop(code, envelope={"code": code, "detail": str(line).split(code, 1)[-1]})
    return list(seen.values())

if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: python3 -m launcher_core.stop_explain <code> [detail]")
    print(explain_stop(sys.argv[1], envelope={"detail": " ".join(sys.argv[2:])})["message"])
