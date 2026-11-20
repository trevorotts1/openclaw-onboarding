#!/usr/bin/env python3
"""explain_stop.py - turn any Skill 78 stop into the four-part plain message the client reads.

Every stop the client (or, for a buyer-facing stop, the buyer) sees is told in fifth-grade words:
  1. what happened (with the real numbers), 2. why this rule exists, 3. what will fix it,
  4. the client's choices (2 to 4 numbered things, one of them the agent doing the work).
The words live in references/stop-explanations.json, one entry per S78 stop code. Reason codes,
file paths and tracebacks never reach the message; they stay in logs, envelopes and receipts.

explain_stop(reason_code, facts=None, envelope=None) -> {"what_happened", "why", "fix", "choices",
"message", "spent_nothing", "audience"}. spent_nothing is true only for a stop whose check spends no money
itself; the message then says so, and an unknown stop never claims it. The code is taken from reason_code, else the envelope's
error.code / reason_code / code, else its session state (expired, reconfirm_required), else an
S78 code or a known refusal phrase inside its text (the image step prints text, not envelopes).
An unknown stop still gets four parts, built from the envelope's detail / message / next_action.

Usage:
  explain_stop.py --code S78-UNKNOWN-PRICE [--facts '{"offer": "Pro"}']
  some_skill78_script ... 2>&1 | explain_stop.py --from-output -
  explain_stop.py --self-test
Exit: 0 message printed, 3 bad usage.
"""
import json
import re
import string
import sys
from pathlib import Path

TABLE_PATH = Path(__file__).resolve().parent.parent / "references" / "stop-explanations.json"
CODE_RE = re.compile(r"\b(?:S\d{2}|AF)-[A-Z0-9]+(?:-[A-Z0-9]+)*\b")
PATH_RE = re.compile(r"(?:[A-Za-z]:\\|~/|\.{0,2}/)?\b[\w.-]+(?:/[\w.-]+)+")
STATE_CODES = {"expired": "S78-SESSION-EXPIRED", "reconfirm_required": "S78-SESSION-RECONFIRM"}
FALLBACK = {
    "what_happened": "The work stopped before it finished.",
    "why": "This skill stops instead of guessing when something does not look right, "
           "so nothing wrong reaches your page or your buyers.",
    "fix": "Find out what stopped it, fix that one thing, and try again.",
    "choices": ["I look into what stopped it, fix it, and try again.",
                "I explain the problem to you in more detail before I change anything.",
                "I stop here and wait for your decision."],
}

def load_table(path=TABLE_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def clean(text):
    """Plain words only: no reason codes, file paths, bracket tags or traceback lines."""
    lines = [l for l in str(text or "").splitlines()
             if not l.lstrip().startswith(("Traceback", 'File "')) and not re.match(r"\s+\^", l)]
    out = PATH_RE.sub("a file", CODE_RE.sub("", " ".join(lines)))
    out = re.sub(r"\[\s*\]|\(\s*\)", "", out)
    out = re.sub(r"^\s*(?:VIOLATION|FAIL-CLOSED|REFUSED|FAIL)\s*:?\s*", "", out)
    return re.sub(r"\s{2,}", " ", out).strip(" :;")

def _envelope_parts(envelope):
    """(code, text, next_action) from any envelope shape this skill emits, or from raw output text."""
    if envelope is None:
        return None, "", ""
    if isinstance(envelope, str):
        return None, envelope, ""
    err = envelope.get("error") if isinstance(envelope.get("error"), dict) else {}
    code = err.get("code") or envelope.get("reason_code") or envelope.get("code")
    if not code and envelope.get("state") in STATE_CODES:
        code = STATE_CODES[envelope["state"]]
    text = err.get("message") or envelope.get("detail") or envelope.get("message") or ""
    return code, str(text), str(envelope.get("next_action") or "")

def _resolve(code, text, entries):
    if code in entries:
        return code
    found = [c for c in CODE_RE.findall(text or "") if c in entries]
    if found:
        return found[0]
    low = (text or "").lower()
    return next((c for c, e in entries.items() if any(m.lower() in low for m in e.get("match") or ())), None)

class _Facts(dict):
    def __missing__(self, key):
        return "{" + key + "}"

def _fill(template, values):
    """Fill {placeholders}; a value with no fact and no default is dropped with its braces."""
    out = string.Formatter().vformat(template, (), _Facts(values))
    return re.sub(r"\s*\{[a-z_]+\}", "", out).replace("( ", "(").strip()

SPENT_NOTHING = {"client": " This check spent no money.", "buyer": " You have not been charged."}

def render(what, why, fix, choices, spent_nothing=False, audience="client"):
    head = what + (SPENT_NOTHING.get(audience, SPENT_NOTHING["client"]) if spent_nothing else "")
    lines = [f"What happened: {head}", f"Why this rule exists: {why}", f"What will fix it: {fix}", "Your choices:"]
    lines += [f"{n}. {c}" for n, c in enumerate(choices, 1)]
    lines.append("Reply with the number you want.")
    return "\n".join(lines)

def explain_stop(reason_code=None, facts=None, envelope=None, *, table=None):
    table = table or load_table()
    entries = table["entries"]
    env_code, text, next_action = _envelope_parts(envelope)
    code = _resolve(reason_code or env_code, text, entries)
    if code is None:
        what = clean(text) or FALLBACK["what_happened"]
        fix = clean(next_action) or FALLBACK["fix"]
        parts = {"what_happened": what, "why": FALLBACK["why"], "fix": fix, "choices": list(FALLBACK["choices"]),
                 "spent_nothing": False, "audience": "client"}
    else:
        entry = entries[code]
        values = {**table.get("defaults", {}), **entry.get("defaults", {}),
                  **{k: clean(v) for k, v in (facts or {}).items() if v is not None and clean(v)}}
        parts = {"what_happened": _fill(entry["what_happened"], values), "why": _fill(entry["why"], values),
                 "fix": _fill(entry["fix"], values), "choices": [_fill(c, values) for c in entry["choices"]],
                 "spent_nothing": bool(entry.get("spends_nothing")), "audience": entry.get("audience", "client")}
    parts["message"] = render(parts["what_happened"], parts["why"], parts["fix"], parts["choices"],
                              parts["spent_nothing"], parts["audience"])
    return parts

def self_test():
    out = explain_stop("S78-INSTALLMENT-TOTAL-MISMATCH",
                       {"offer": "Pro", "count": 3, "schedule_total": "$290.00", "total": "$297.00"})
    assert "3 payments that add up to $290.00" in out["what_happened"] and "$297.00" in out["what_happened"], out
    assert "S78-" not in out["message"] and out["message"].endswith("Reply with the number you want."), out
    env = {"ok": False, "error": {"code": "S78-QUERY-PRICE-AUTHORITY", "message": "Query keys ['price'] rejected."}}
    assert "price=" in explain_stop(envelope=env)["what_happened"]
    assert "waiting for you to approve" in explain_stop(
        envelope="FAIL: design board: no client approval recorded for this page's board")["what_happened"]
    unknown = explain_stop("S99-NOT-A-CODE", envelope={"detail": "S78-X broke in /tmp/x/y.py", "next_action": "retry"})
    assert unknown["what_happened"] == "broke in a file" and unknown["fix"] == "retry", unknown
    assert explain_stop()["what_happened"] == FALLBACK["what_happened"]
    print("explain_stop --self-test: PASS (table entry with real numbers, envelope code, refusal text match, unknown-code fallback)")
    return 0

def main(argv):
    if "--self-test" in argv:
        return self_test()

    def opt(name):
        return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else None

    if "--from-output" in argv:
        src = opt("--from-output")
        text = sys.stdin.read() if src in (None, "-") else Path(src).read_text(encoding="utf-8")
        try:
            envelope = json.loads(text)
        except ValueError:
            envelope = text
        print(explain_stop(envelope=envelope)["message"])
        return 0
    if "--code" in argv:
        print(explain_stop(opt("--code"), json.loads(opt("--facts") or "{}"))["message"])
        return 0
    print("usage: explain_stop.py --code <S78-...> [--facts <json>] | --from-output <file|-> | --self-test",
          file=sys.stderr)
    return 3

if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
