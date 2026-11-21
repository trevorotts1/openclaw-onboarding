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
# An authorization header is a credential, not a sentence. A bearer value of plain letters
# ("Authorization: Bearer abcdefghijklmnop") carries no digit, so the token patterns below
# never see it; it is removed whole here, header word and value together.
_CREDENTIAL = re.compile(
    r"(?i)\b(?:proxy-)?authorization\b\s*[:=]\s*(?:(?:bearer|basic)\s+)?[A-Za-z0-9._~+/=-]{4,}"
    r"|\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"
    r"|\b(?:api[-_ ]?key|apikey|access[-_ ]?key)\b\s*[:=]\s*[A-Za-z0-9._~+/=-]{4,}")
# The operator's own disk never appears in a line a person could read: an absolute operator
# path is dropped whole. Relative repository paths (shared-utils/x.py) stay, because the agent
# reading the operator line needs them to find the file.
_ABS_PATH = re.compile(r"(?<![\w.~-])/(?:Users|Volumes|private|home|var|opt|tmp|mnt|data)/\S*")
_HTTP_WORD = re.compile(r"(?i)\bhttps?\b")
# A 4xx/5xx number is a transport code only when a transport word sits right beside it
# ("HTTP 429", "status 500", "error 503"). A bare number is a real count ("a 450-picture
# limit", "500 required pictures") and is kept.
_HTTP_STATUS_CODE = re.compile(
    r"(?i)\b(?:https?|status|code|error|response)\b\s*[:=]?\s*[45]\d\d\b")
# A bare identifier that looks like a secret value, never a plain word: mixed letters and
# digits (abc123, tok_9f2), the shape real tokens and digests take. Pure words ("widget",
# "broke", "retry") are kept; these are not.
# It must also START with a letter: a real count ("450-picture limit", "500 pictures") begins
# with a digit and is a number the client needs, never a token.
_SECRET_TOKEN = re.compile(r"\b(?=[A-Za-z][A-Za-z0-9_-]*\d)[A-Za-z0-9_-]{4,}\b")
# A whole identifier built around a secret word (secret_setting, customer_token): the value
# beside it is dropped with it, so neither half reaches the client.
_SECRET_WORD = re.compile(
    r"(?i)[A-Za-z0-9_]*(?:secret|token|password|passwd|credential|private|internal|customer)"
    r"[A-Za-z0-9_]*")
# Python exception class names: the client never needs to know the error's class.
_ERROR_CLASS = re.compile(r"(?i)\b(?:KeyError|ValueError|TypeError|AttributeError|IndexError|"
                          r"RuntimeError|OSError|IOError|FileNotFoundError|PermissionError)\b"
                          r"\s*:?\s*['\"]?")
# Leftover filler an exception leak leaves behind once its identifiers are gone.
_FILLER = re.compile(r"(?i)\b(?:keys?|settings?|values?|errors?)\b")
_NOTHING_SPENT = re.compile(r"nothing (?:has been|was) spent", re.I)

_FALLBACK = {
    "what_happened": "I had to stop for a moment before going further.",
    "why": "I stop and sort it out instead of guessing, so nothing half-done goes any further.",
    "fix": "I sort it out, then keep going.",
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
    """Stop text with every code, file path and stack trace taken out, scrubbed for the client.

    Unknown exception detail passes through here on its way to the client message. Secret-shaped
    tokens, secret-word identifiers and their KEY=value pairs are removed before the plain words
    are used, so a leak like ``KeyError: 'secret_setting'`` can never reach the client. Bare
    transport words (HTTP/HTTPS) and their 4xx/5xx status numbers are removed too, so a note like
    "HTTP 429 billing problem" reaches the client as "Billing problem": the status is a transport
    code, not a fact the client can act on. Real counts always have a counted word beside them
    ("135 pictures") and are never stripped. A scrubbed line is kept only when real words remain;
    a line that was all identifiers becomes "" and the caller falls back to the generic parts.
    """
    text = str(text or "")
    # An authorization header dies whole, letters-only bearer values included.
    text = _ABS_PATH.sub(" ", _CREDENTIAL.sub(" ", text))
    # A transport status number dies with the transport word beside it, before the filler scrub
    # removes that word ("error 500" -> "500" would leave a bare number behind).
    text = _HTTP_STATUS_CODE.sub(" ", text)
    # A KEY=value pair dies whole: dropping only the value would leave "customer_token is" behind.
    text = re.sub(r"(?i)\b[A-Za-z0-9_]*(?:secret|token|password|passwd|credential|private|internal|customer)[A-Za-z0-9_]*\s*[=:]\s*[^\s,;]+", " ", text)
    text = _SECRET_WORD.sub(" ", text)
    # The header word left behind once its value died says nothing to the client.
    text = re.sub(r"(?i)\b(?:proxy-)?authorization\b", " ", text)
    text = _TRACE.sub("", text)
    text = _PATH.sub("", _CODE.sub("", text))
    text = _SECRET_TOKEN.sub(" ", text)
    text = _ERROR_CLASS.sub(" ", text)
    text = re.sub(r"['\"]", " ", text)
    text = _FILLER.sub(" ", text)
    # Bare HTTP transport words: "HTTP billing problem" loses only its transport word.
    text = _HTTP_WORD.sub(" ", text)
    # A bare tool path or operator loop word is not client words: "tools/fix.py" dies
    # with the _PATH pattern above, and "run"/"retry" beside it die here, so
    # "run tools/fix.py then retry" becomes "" instead of "Run then retry". Bare verbs
    # ("then", "name", "record") are kept, so client next_steps survive untouched.
    # "run" dies only as the first word ("run tools/..." / "run, then ..."), never as a
    # noun later in the line: "the paid logo run" keeps its run, "Name the page run"
    # keeps its run. A client next_step never opens with "run".
    text = re.sub(r"(?i)\b(?:fix|tools?|retrys?|retry)\b", " ", text)
    text = re.sub(r"(?i)^\s*run\b(?=\s|\$)", " ", text)
    # A lone "then" left by a scrubbed tool path ("run ... then ...") is an operator
    # loop connector, not client words. "Name ..., then retry" keeps its then: the
    # retry-word scrub above already removed a real retry, so a surviving "then" with
    # real words on both sides stays.
    collapsed = re.sub(r"\s{2,}", " ", text).strip(" :;,-")
    if re.fullmatch(r"(?i)(?:then|and|to|please)[\s,.;:]*", collapsed):
        return ""
    text = re.sub(r"\s+([,.;:])", r"\1", collapsed).strip(" :;,-")
    text = re.sub(r"\s+([,.;:])", r"\1", re.sub(r"\s{2,}", " ", text)).strip(" :;,-")
    # Residue of a scrubbed code/path: "the widget at broke ()" -> "The widget broke".
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"(?i)\b(at|in|on|from)\s+(broke|failed|missing|stopped)\b", r"\2", text)
    text = re.sub(r"\s{2,}", " ", text).strip(" :;,-")
    if not re.search(r"[a-zA-Z]{3,}", text):
        return ""
    return text[:1].upper() + text[1:] if text else ""

def operator_text(text: Any) -> str:
    """One operator line with credentials and absolute operator paths taken out, words kept.

    The operator line in front of the client message names the reason code on purpose: the agent
    and the log need it. What it may never carry is a live credential or the operator's own disk.
    """
    text = _ABS_PATH.sub(" ", _CREDENTIAL.sub(" ", str(text or "")))
    return re.sub(r"\s{2,}", " ", text).strip()

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
    An unknown code's ``next_step`` is trusted only when the same scrub that cleans the detail
    leaves real client words in it; a technician's note (an operator path or command) scrubs to
    "" and the fix falls back to the generic "I sort it out", which is all the evidence supports.
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
    """One explanation per distinct failure in a list of "CODE: detail" violation strings.

    Two pages blocked by the same code are two failures and get two messages; only a literally
    repeated line is shown once, because it is the same failure said twice.
    """
    seen: Dict[tuple, Dict[str, Any]] = {}
    for line in violations:
        text = str(line)
        code = next(iter(_CODE.findall(text)), "")
        key = (code, text)
        if key not in seen:
            seen[key] = explain_stop(code, envelope={"code": code, "detail": text.split(code, 1)[-1]})
    return list(seen.values())

if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: python3 -m launcher_core.stop_explain <code> [detail]")
    print(explain_stop(sys.argv[1], envelope={"detail": " ".join(sys.argv[2:])})["message"])
