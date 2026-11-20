#!/usr/bin/env python3
"""explain_stop.py - turn any Skill 49 stop into the four-part plain message the client reads.

Every stop the client sees is told in fifth-grade words:
  1. what happened (with the real numbers), 2. why this rule exists, 3. what will fix it,
  4. the client's choices (2 to 4 numbered things, one of them the agent doing the work).
The words live in references/stop-explanations.json, one entry per stop. Reason codes, file paths
and tracebacks never reach the message; they stay in logs, manifests and receipts.

explain_stop(reason_code=None, facts=None, envelope=None) -> {"what_happened", "why", "fix", "choices",
"message", "spent_nothing", "code"}. The stop is found from reason_code, else the envelope's
error.code / reason_code / code, else the first AF-FUN code inside its text (a longer code with no
entry of its own falls back to its nearest parent, AF-FUN-IMG-HOST-UNSIGNED -> AF-FUN-IMG-HOST),
else a known refusal phrase ("ABORT [HASH-PIN]", "plan is not ready: missing"). Real numbers are
read from the stop's own text (facts_from_detail) and from `facts`; anything not known falls back
to the entry's defaults, so no {placeholder} is ever shown. spent_nothing is true only for a check
that spends no money itself; the message then says so. An unknown stop still gets four parts,
built from the envelope's detail / message / next_action. "code" is for logs, never shown.

Usage:
  explain_stop.py --code AF-FUN-SEC12-WORDS [--facts '{"count": 160}']
  bash signature-funnel-entry.sh --run-dir <dir> 2>&1 | explain_stop.py --from-output -
  explain_stop.py --self-test
Exit: 0 message printed, 3 bad usage.
"""
import json
import re
import string
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
TABLE_PATH = SKILL_DIR / "references" / "stop-explanations.json"
PAGE_TYPES_PATH = SKILL_DIR / "structure" / "page_types.json"
CODE_RE = re.compile(r"\bAF-FUN-[A-Z0-9]+(?:-[A-Z0-9]+)*\b")
ANY_CODE_RE = re.compile(r"\b(?:AF(?:-FUN)?|FD|LAUNCH)-[A-Z0-9]+(?:-[A-Z0-9]+)*\b|\bABORT \[[A-Z-]+\]:?")
PATH_RE = re.compile(r"(?:[A-Za-z]:\\|~/|\.{0,2}/)?\b[\w.<>-]+(?:/[\w.<>-]+)+")
# A bare file name ("copy_ledger.json") reads as "a file" too.
FILE_RE = re.compile(r"\b[\w.-]+\.(?:py|json|sh|md|txt|ya?ml|log|html|csv)\b")
# Anything else that is for logs, not people: any CODE-LIKE or ENV_NAME token (RUN-UNKNOWN, SF_RUN_NONCE),
# exception class names (PermissionError), [Errno n], key=value pairs (rc=2), long hex digests,
# and a leading HTTP/network status ("HTTP 403 ...", "HTTPS ...") — a status line is never a sentence.
LEAD_STATUS_RE = re.compile(r"^(?:https?[\s:/\\._-]*)+(\d{3})\b[\s:/\\._-]*", re.IGNORECASE)
LOG_ONLY_RE = re.compile(r"\bHTTP\s+\d{3}\b|\b[A-Z][A-Z0-9]*(?:[-_][A-Z0-9]+)+\b|\b[A-Za-z_]*(?:Error|Exception|Warning)\b|"
                         r"\[Errno \d+\]|\b\w+=\S+|\b[0-9a-f]{12,}\b")
SPENT_NOTHING = " This check did not spend any money."


def load_table(path=TABLE_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def clean(text):
    """Plain words only: no reason codes, file paths, bracket tags or traceback lines.
    A leading HTTP/network status line is not a sentence for the client, so it is
    dropped before cleaning (the fallback message says the work stopped instead)."""
    lines = [l for l in str(text or "").splitlines()
             if not l.lstrip().startswith(("Traceback", 'File "')) and not re.match(r"\s+\^", l)]
    lines = [l for l in lines if not LEAD_STATUS_RE.match(l.strip())]
    out = PATH_RE.sub("a file", ANY_CODE_RE.sub("", " ".join(lines)))
    out = LOG_ONLY_RE.sub("", FILE_RE.sub("a file", out))
    out = re.sub(r"\s+([:;,.])", r"\1", out)
    out = re.sub(r"^(?:\s*[:;,.]\s*)+|(?:\s*[:;,.])+(?=\s*[:;,.])", "", out)
    out = re.sub(r"\[\s*\]|\(\s*\)", "", out)
    out = re.sub(r"^\s*(?:VIOLATION|FAIL-CLOSED|REFUSED|FAIL|ABORT|USAGE ERROR)\s*:?\s*", "", out)
    return re.sub(r"\s{2,}", " ", out).strip(" :;")


def _page_labels():
    try:
        pages = json.loads(PAGE_TYPES_PATH.read_text(encoding="utf-8"))["pages"]
        return {p["matrix_slug"]: p["label"] for p in pages.values() if p.get("matrix_slug")}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}


def _page(slug, labels):
    slug = str(slug).strip().lower()
    return labels.get(slug) or slug.replace("-", " ").title()


_TRUTH = {"community_url": "the community link", "bonus": "the bonus name",
          "founder_text": "the personal text from you"}
_VISUAL = {"skill71_root": "where the page design tool lives", "brand_file": "your brand file",
           "brand_owner": "who owns the brand"}


def facts_from_detail(text):
    """The real names and numbers inside a stop's own text (prover and orchestrator wording)."""
    t, labels, f = str(text or ""), _page_labels(), {}
    page = re.search(r"page '([^']+)'", t) or re.search(r"pages/([a-z][a-z0-9-]*)\.fragment", t)
    if page:
        f["page"] = _page(page.group(1), labels)
    frag = re.search(r"fragment\.html for \[([^\]]*)\]", t)
    if frag:
        f["page"] = " and ".join(_page(x.strip(" '\""), labels) for x in frag.group(1).split(",") if x.strip())
    named = re.search(r"(brief|copy_ledger|prompt_ledger|media_ledger|build_receipt|funnel_graph|derived_pages|"
                      r"fab-artifact|emails|route-graph|launch|approval)\.json", t)
    if named:
        f["file"] = {"brief": "your locked setup answers", "copy_ledger": "your page copy",
                     "prompt_ledger": "your picture instructions", "media_ledger": "your picture list",
                     "build_receipt": "the build record", "funnel_graph": "the funnel map",
                     "derived_pages": "the follow-up page list", "fab-artifact": "the copy scorecard",
                     "emails": "the promo emails", "route-graph": "the funnel route",
                     "launch": "your launch plan", "approval": "your approval record"}[named.group(1)]
    sec = re.search(r"Section (\d+) \(([^)?]+)\)", t)
    if sec:
        f["section"] = sec.group(1)
        f["section_label"] = f"Section {sec.group(1)} ({sec.group(2)})" + (f" on the {f['page']}" if "page" in f else "")
    elif re.search(r"Section (\d+)", t):
        f["section"] = re.search(r"Section (\d+)", t).group(1)
    if "TY-1" in t:
        f["section_label"] = "The welcome message at the top of the thank-you page"
    m = re.search(r"\b(\d+) (?:chars|characters|words)\b", t)
    if m:
        f["count"] = m.group(1)
    m = re.search(r"\b(\d+) (?:personas|bullets|steps|labeled parts|items|distinct words)\b", t)
    if m:
        f["count"] = m.group(1)
    m = re.search(r"only (\d+) distinct words", t)
    if m:
        f["count"] = m.group(1)
    m = re.search(r"\[(\d+), (\d+)\]", t)
    if m:
        f["min"], f["max"] = m.group(1), m.group(2)
    m = re.search(r"maximum (?:of )?(\d+)", t)
    if m:
        f["max"] = m.group(1)
    m = re.search(r"minimum (?:of )?(\d+)", t)
    if m:
        f["min"] = m.group(1)
    m = re.search(r"step (\d+) is (\d+) chars", t)
    if m:
        f["step"], f["count"] = m.group(1), m.group(2)
    m = re.search(r"qc_score (?:is )?([\d.]+)", t)
    if m:
        f["score"] = m.group(1)
    m = re.search(r"funnel_size resolves to (\S+?),", t)
    if m:
        f["size"] = m.group(1)
    m = re.search(r"\b([357])-step\b", t)
    if m and "size" not in f:
        f["size"] = m.group(0)
    slot = re.search(r"\('([a-z0-9-]+)', '?([\w-]+)'?\)", t)
    if slot and "where" not in f:
        f["where"] = f"the Section {slot.group(2)} picture on the {_page(slot.group(1), labels)}"
    if "where" not in f and re.search(r"page '[^']+' section (\w+)", t):
        s = re.search(r"page '([^']+)' section (\w+)", t)
        f["where"] = f"the Section {s.group(2)} picture on the {_page(s.group(1), labels)}"
    m = re.search(r"required answers: ([^\n]+)", t)
    if m:
        f["missing"] = ", ".join(f"question {n}" for n in re.findall(r"\bq(\d+)_", m.group(1))) or m.group(1)
    if "delivery_rail" in t:
        f["missing"] = (f.get("missing", "") + ", " if f.get("missing") else "") + "the name of the tool that builds your pages"
    m = re.search(r"plan is not ready: missing (.+)", t) or re.search(r"missing facts: (.+)", t)
    if m:
        f["missing"] = m.group(1).strip(" .")
    found = [w for k, w in _TRUTH.items() if k in t]
    if found:
        f["detail"] = " and ".join(found)
    found = [w for k, w in _VISUAL.items() if k in t]
    if found:
        f["detail"] = ", ".join(found)
    m = re.search(r"mandatory step kind\(s\): ([^\n]+)", t)
    if m:
        f["detail"] = m.group(1).replace("_", " ")
    m = re.search(r"ledger has no '([^']+)' page", t)
    if m:
        f["detail"] = f"the {_page(m.group(1), labels)} copy"
    elif "section" in f and "page" in f and "is absent" in t:
        f["detail"] = f"Section {f['section']} on the {f['page']}"
    return f


def _envelope_parts(envelope):
    """(code, text, next_action) from a dict envelope, or from raw output text."""
    if envelope is None:
        return None, "", ""
    if isinstance(envelope, str):
        return None, envelope, ""
    err = envelope.get("error") if isinstance(envelope.get("error"), dict) else {}
    code = err.get("code") or envelope.get("reason_code") or envelope.get("code")
    text = err.get("message") or envelope.get("detail") or envelope.get("message") or ""
    return code, str(text), str(envelope.get("next_action") or "")


def _known(code, entries):
    """The code's own entry, else its nearest parent (AF-FUN-IMG-HOST-UNSIGNED -> AF-FUN-IMG-HOST)."""
    while code and code.count("-") >= 2:
        if code in entries:
            return code
        code = code.rsplit("-", 1)[0]
    return None


def resolve(code, text, entries):
    """The table key for a stop, or None when the table does not know it."""
    hit = _known(code, entries) if code else None
    if hit:
        return hit
    for found in CODE_RE.findall(text or ""):
        hit = _known(found, entries)
        if hit:
            return hit
    low = (text or "").lower()
    for key, entry in entries.items():
        if any(m.lower() in low for m in entry.get("match") or ()):
            return key
    return None


def _plain(text, default):
    """An unknown stop's own words, cleaned; the table's plain default when too little plain text is left
    (a bare code, an exception name or a path is never a sentence for the client)."""
    out = clean(text)
    return out if len(re.findall(r"[A-Za-z]{2,}", out)) >= 3 else default

class _Facts(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def _fill(template, values):
    out = string.Formatter().vformat(template, (), _Facts(values))
    return re.sub(r"\s*\{[a-z_]+\}", "", out).strip()


def render(what, why, fix, choices, spent_nothing=False):
    lines = [f"What happened: {what}{SPENT_NOTHING if spent_nothing else ''}",
             f"Why this rule exists: {why}", f"What will fix it: {fix}", "Your choices:"]
    lines += [f"{n}. {c}" for n, c in enumerate(choices, 1)]
    lines.append("Reply with the number you want.")
    return "\n".join(lines)


def explain_stop(reason_code=None, facts=None, envelope=None, *, table=None):
    table = table or load_table()
    entries, fallback = table["entries"], table["fallback"]
    env_code, text, next_action = _envelope_parts(envelope)
    code = resolve(reason_code or env_code, text, entries)
    if code is None:
        parts = {"what_happened": _plain(text, fallback["what_happened"]), "why": fallback["why"],
                 "fix": _plain(next_action, fallback["fix"]), "choices": list(fallback["choices"]),
                 "spent_nothing": False}
    else:
        entry = entries[code]
        found = {k: v for k, v in facts_from_detail(text).items() if clean(v)}
        given = {k: clean(v) for k, v in (facts or {}).items() if v is not None and clean(v)}
        values = {**entry.get("defaults", {}), **found, **given}
        parts = {"what_happened": _fill(entry["what_happened"], values), "why": _fill(entry["why"], values),
                 "fix": _fill(entry["fix"], values), "choices": [_fill(c, values) for c in entry["choices"]],
                 "spent_nothing": bool(entry.get("spends_nothing"))}
    parts["message"] = render(parts["what_happened"], parts["why"], parts["fix"], parts["choices"],
                              parts["spent_nothing"])
    parts["code"] = code  # for logs and receipts only; never part of the message
    return parts


def client_message(text, reason_code=None, facts=None):
    """The message only, for a CLI that just printed a refusal line (never raises)."""
    try:
        return explain_stop(reason_code, facts, envelope=str(text or ""))["message"]
    except Exception:  # noqa: BLE001 - the explanation must never turn a clean stop into a crash
        return render("The funnel work stopped before it finished.",
                      "This skill stops instead of guessing when something does not look right.",
                      "Find out what stopped it, fix that one thing, and run it again.",
                      ["I look into what stopped it, fix it, and run it again.",
                       "I stop here and wait for your decision."])


def self_test():
    out = explain_stop(envelope="prove_sf_copy.py rc=2 :: VIOLATION [AF-FUN-SEC12-WORDS] page 'main' Section 12 "
                                "(The Big Bold Heartfelt Message): 160 words, over the sacred maximum of 150")
    assert "160 words" in out["what_happened"] and "between 100 and 150" in out["what_happened"], out
    assert "AF-FUN" not in out["message"] and out["message"].endswith("Reply with the number you want."), out
    assert explain_stop(envelope="ABORT [HASH-PIN]: pin mismatch")["code"] == "AF-FUN-HASH-PIN"
    assert explain_stop("AF-FUN-IMG-HOST-UNSIGNED")["code"] == "AF-FUN-IMG-HOST"
    unknown = explain_stop("AF-FUN-NOT-A-CODE", envelope={"detail": "it broke in /tmp/x/y.py", "next_action": "retry"})
    assert unknown["what_happened"] == "it broke in a file" and unknown["fix"] == "Find out what stopped it, fix that one "\
        "thing, and run it again.", unknown
    leak = explain_stop(envelope={"detail": "RUN-UNKNOWN: PermissionError: /tmp/private.txt"})
    assert leak["what_happened"] == "The funnel work stopped before it finished.", leak
    http_leak = explain_stop(envelope="HTTP 403 from a file with API access forbidden")
    assert http_leak["code"] is None, http_leak
    for word in ("403", "HTTP", "API"):
        assert word not in http_leak["message"], http_leak
    print("explain_stop --self-test: PASS (real numbers, shell abort tag, parent code, unknown-code fallback, no leak)")
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
        print(explain_stop(envelope=envelope if isinstance(envelope, (dict, str)) else text)["message"])
        return 0
    if "--code" in argv:
        print(explain_stop(opt("--code"), json.loads(opt("--facts") or "{}"))["message"])
        return 0
    print("usage: explain_stop.py --code <AF-FUN-...> [--facts <json>] | --from-output <file|-> | --self-test",
          file=sys.stderr)
    return 3


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
