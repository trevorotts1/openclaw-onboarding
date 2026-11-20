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
error.code / reason_code / code, else its session state (expired, reconfirm_required). Only a stop
with no code at all is looked up by an S78 code or a known refusal phrase inside its text; a code the
table does not know stays unknown, so a stray phrase in its text never explains a different problem.
The facts are the caller's, over the envelope's error.facts.
An unknown stop still gets four parts, in fixed plain words: its raw text (an exception, a path, a
secret) is for the logs and never reaches the message.

report_stop(log, code=None, facts=None, stream=None, exit_code=2) is how every script in this skill
prints a stop, on one stream: the log line (code and raw text, for logs and receipts), one JSON
envelope line {"ok": false, "error": {"code", "message", "facts", "client_explanation"}}, and last,
after the line "Tell the client:", the plain message. The client is shown only that last part. It
comes last so a caller that keeps the tail of the output (dispatch does) still carries it.

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

CLIENT_HEADER = "Tell the client:"
TABLE_PATH = Path(__file__).resolve().parent.parent / "references" / "stop-explanations.json"
CODE_RE = re.compile(r"\b(?:S\d{2}|AF)-[A-Z0-9]+(?:-[A-Z0-9]+)*\b")
PATH_RE = re.compile(r"(?:[A-Za-z]:\\|~/|\.{0,2}/)?\b[\w.-]+(?:/[\w.-]+)+")
STATE_CODES = {"expired": "S78-SESSION-EXPIRED", "reconfirm_required": "S78-SESSION-RECONFIRM"}
FALLBACK = {
    "what_happened": "The work stopped before it finished, on a check that does not have plain words yet.",
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
    """(code, text, facts) from any envelope shape this skill emits, or from raw output text.
    text only finds the code or a known refusal phrase; it is never shown to the client."""
    if envelope is None:
        return None, "", {}
    if isinstance(envelope, str):
        return None, envelope, {}
    err = envelope.get("error") if isinstance(envelope.get("error"), dict) else {}
    code = err.get("code") or envelope.get("reason_code") or envelope.get("code")
    if not code and envelope.get("state") in STATE_CODES:
        code = STATE_CODES[envelope["state"]]
    text = err.get("message") or envelope.get("detail") or envelope.get("message") or ""
    facts = err.get("facts") if isinstance(err.get("facts"), dict) else {}
    return code, str(text), facts

def from_output(text):
    """The stop in a script's printed output: the whole text as JSON, else its last line that is a
    JSON envelope with an error (the picture step's stop line), else the text itself."""
    try:
        return json.loads(text)
    except ValueError:
        pass
    for line in reversed(text.splitlines()):
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("error"), dict):
            return obj
    return text

def _resolve(code, text, entries):
    if code:  # an explicit code is the stop: known, or unknown (the fallback), never another code found in text
        return code if code in entries else None
    found = [c for c in CODE_RE.findall(text or "") if c in entries]
    if found:
        return found[0]
    low = (text or "").lower()
    hits = [c for c, e in entries.items() if any(m.lower() in low for m in e.get("match") or ())]
    if not hits:
        return None
    if len(hits) == 1:
        return hits[0]
    # "--inputs none" also refuses on missing inputs; the longer refusal phrase wins.
    return max(hits, key=lambda c: max(len(m) for m in entries[c].get("match") or ("",)))

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
    env_code, text, env_facts = _envelope_parts(envelope)
    code = _resolve(reason_code or env_code, text, entries)
    if code is None:
        parts = {**FALLBACK, "choices": list(FALLBACK["choices"]), "spent_nothing": False, "audience": "client",
                 "code": None}
    else:
        entry = entries[code]
        values = {**table.get("defaults", {}), **entry.get("defaults", {}),
                  **{k: clean(v) for k, v in {**env_facts, **(facts or {})}.items() if v is not None and clean(v)}}
        parts = {"what_happened": _fill(entry["what_happened"], values), "why": _fill(entry["why"], values),
                 "fix": _fill(entry["fix"], values), "choices": [_fill(c, values) for c in entry["choices"]],
                 "spent_nothing": bool(entry.get("spends_nothing")), "audience": entry.get("audience", "client"),
                 "code": code}
    parts["message"] = render(parts["what_happened"], parts["why"], parts["fix"], parts["choices"],
                              parts["spent_nothing"], parts["audience"])
    return parts

def report_stop(log, code=None, facts=None, stream=None, exit_code=2):
    """Print one stop for the logs and for the client (see the module docstring); return exit_code."""
    stream = stream or sys.stdout
    exp = explain_stop(code, facts, {"message": log})
    shown = exp["code"]  # the entry this message really explains; None for the unknown fallback
    envelope = {"ok": False, "error": {"code": shown, "message": log, "facts": dict(facts or {}),
                                       "client_explanation": exp}}
    print(log, file=stream)
    print(json.dumps(envelope, default=str), file=stream)
    print(f"{CLIENT_HEADER}\n{exp['message']}", file=stream, flush=True)
    return exit_code

def self_test():
    out = explain_stop("S78-INSTALLMENT-TOTAL-MISMATCH",
                       {"offer": "Pro", "count": 3, "schedule_total": "$290.00", "total": "$297.00"})
    assert "3 payments that add up to $290.00" in out["what_happened"] and "$297.00" in out["what_happened"], out
    assert "S78-" not in out["message"] and out["message"].endswith("Reply with the number you want."), out
    env = {"ok": False, "error": {"code": "S78-QUERY-PRICE-AUTHORITY", "message": "Query keys ['price'] rejected."}}
    assert "price=" in explain_stop(envelope=env)["what_happened"]
    assert "waiting for you to approve" in explain_stop(
        envelope="FAIL: design board: no client approval recorded for this page's board")["what_happened"]
    unknown = explain_stop("S99-NOT-A-CODE", envelope={"detail": "KeyError: 'secret' in /tmp/x/y.py"})
    assert unknown["what_happened"] == FALLBACK["what_happened"] and "secret" not in unknown["message"], unknown
    assert explain_stop()["what_happened"] == FALLBACK["what_happened"]
    # a code the table does not know stays unknown, even when the text names a known stop
    stray = explain_stop(envelope={"error": {"code": "S99-NOT-A-CODE", "message": "REFUSED: --inputs none"}})
    assert stray["what_happened"] == FALLBACK["what_happened"], stray  # never the inputs-none explanation
    line = json.dumps({"ok": False, "error": {"code": "S78-INSTALLMENT-TOTAL-MISMATCH", "message": "log text",
                       "facts": {"offer": "Pro", "count": 2, "schedule_total": "$180.00", "total": "$197.00"}}})
    piped = explain_stop(envelope=from_output("RUN a b\n" + line + "\nREFUSED: [S78-INSTALLMENT-TOTAL-MISMATCH] log text"))
    assert "2 payments that add up to $180.00" in piped["what_happened"], piped
    print("explain_stop --self-test: PASS (table entry with real numbers, envelope code, refusal text match, "
          "fixed-words unknown fallback, unknown code never re-matched by its text, piped stop line keeps its facts)")
    return 0

def main(argv):
    if "--self-test" in argv:
        return self_test()

    def opt(name):
        return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else None

    if "--from-output" in argv:
        src = opt("--from-output")
        text = sys.stdin.read() if src in (None, "-") else Path(src).read_text(encoding="utf-8")
        print(explain_stop(envelope=from_output(text))["message"])
        return 0
    if "--code" in argv:
        print(explain_stop(opt("--code"), json.loads(opt("--facts") or "{}"))["message"])
        return 0
    print("usage: explain_stop.py --code <S78-...> [--facts <json>] | --from-output <file|-> | --self-test",
          file=sys.stderr)
    return 3

if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
