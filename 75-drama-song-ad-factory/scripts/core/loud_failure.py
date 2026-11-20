"""loud_failure -- no silent failure, ever (Trevor's rule, skill 75).

Anything that goes wrong or is skipped records a NAMED entry here and prints it
at once to stderr. The final receipt carries every entry (attach), a FAILURE
flips the receipt to outcome "error", and a WARNING stays visible. Stdlib only.

  fail(code, detail)  -- a gate or step broke; the run must not look clean
  warn(code, detail)  -- a deliberate, documented fail-soft path (for example a
                         Command Center board that cannot be reached); still
                         printed as a WARNING line and listed in the receipt
"""
import json
import os
import sys

_ENTRIES = []


def _add(kind, code, detail):
    entry = {"kind": kind, "code": str(code), "detail": str(detail)}
    _ENTRIES.append(entry)
    line = "%s %s: %s" % (kind, entry["code"], entry["detail"])
    print(line, file=sys.stderr)
    path = os.environ.get("DSAF_FAILURE_LOG")
    if path:
        try:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
        except OSError as exc:      # the log itself failing is also loud
            print("WARNING FAILURE_LOG_UNWRITABLE: %s: %s" % (path, exc),
                  file=sys.stderr)
    return entry


def fail(code, detail=""):
    return _add("FAILURE", code, detail)


def warn(code, detail=""):
    return _add("WARNING", code, detail)


def entries():
    return list(_ENTRIES)


def reset():
    del _ENTRIES[:]


def lines():
    return ["%s %s: %s" % (e["kind"], e["code"], e["detail"]) for e in _ENTRIES]


def attach(receipt):
    """Put every entry on the receipt. A FAILURE turns an ok receipt into an
    error receipt, so a broken gate can never ship a clean-looking result."""
    fails = [e for e in _ENTRIES if e["kind"] == "FAILURE"]
    warns = [e for e in _ENTRIES if e["kind"] == "WARNING"]
    receipt["failures"] = fails
    receipt["warnings"] = warns
    if fails and receipt.get("outcome") == "ok":
        receipt["outcome"] = "error"
        receipt["reason_code"] = "LOUD_FAILURE"
        receipt["next_action"] = "; ".join(
            "%s: %s" % (e["code"], e["detail"]) for e in fails)
    return receipt

# ---- every stop explains itself (owner order 2026-11-20) --------------------
#
# A client is never left at a dead stop. ``explain_stop`` turns any refusal,
# hold or wait into four plain parts -- what happened, why the rule exists,
# what will fix it, and 2-4 numbered choices -- read from the ONE table in
# references/client-messages.md ("Every stop explained"). Reason codes stay in
# logs and receipts; they never reach the client. An unknown code still gets
# all four parts, built from the envelope's own detail and next action with
# codes, paths and stack traces scrubbed out. Stdlib only, never raises.
import re

TABLE_PATH = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "references",
    "client-messages.md"))
TABLE_HEAD = "## Every stop explained"
PARTS = ("what_happened", "why", "fix", "choices")
_TABLE = {}
_PH = re.compile(r"\{(\w+)(?::([^{}]*))?\}")
# Conditional blocks {+name}...{/name}: kept only when facts[name] is truthy.
# {name:fallback} keeps the old meaning (value or fallback). Blocks let one
# row say two different things, e.g. a longer-song fix vs. shorten-the-opener.
_BLOCK_OPEN = re.compile(r"\{\+(\w+)\}")
_BLOCK_CLOSE = re.compile(r"\{/\w+\}")
_CODE_TOKEN = re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+\b")
_PATHISH = re.compile(r"(?:~|\.{1,2})?/[\w.\-/]+|\b[\w\-]+\.(?:py|json|sqlite3|md|sh|txt|log|mp3)\b"
                      r"|--[\w-]+|`[^`]*`")
# A run path in client text is not a secret, so a detail that only carries
# the run's own files stays usable: only the risky pieces get cut.
_RUN_PATH = re.compile(r"(?:~|\.{1,2})?/[\w.\-/]*runs?/[\w.\-/]*"
                       r"|/tmp/[\w.\-/]*")
_QUOTED_PATH = re.compile(r"'[^']*(?:/|\.py|\.json|\.sqlite3|\.log)[^']*'|"
                          r'"[^"]*(?:/|\.py|\.json|\.sqlite3|\.log)[^"]*"')
GENERIC_WHAT = "The work paused before the next step."
GENERIC_WHY = ("Each step waits until it is safe and ready, so nothing goes "
               "wrong.")
GENERIC_FIX = "I check what this step needs and take care of it before going on."
GENERIC_CHOICES = ("I take care of what this step needs and tell you when it is done.",
                   "I explain more about this stop first.",
                   "We pause here until you say go.")
# LYRICS_REJECTED carries several causes in one detail; each has its own row.
# A charge happened only when the envelope says the provider billed us: any
# recorded credits consumed, an accepted submit stamp, or generated media.
_CHARGED_KEYS = ("credits_consumed", "actual_cost", "accepted_submit_at",
                 "kicks_cost_cents", "spent_cents", "charge_cents", "cost_cents")
_LYRIC_CAUSES = (
    ("LYRICS_REJECTED/words_over_budget",
     re.compile(r"(?P<total>\d+) words, the (?P<delivered_s>\d+) s budget is (?P<budget>\d+)")),
    ("LYRICS_REJECTED/opener_over_cap",
     re.compile(r"spoken intro is (?P<opener_words>\d+) words, max (?P<opener_max>\d+)")),
    ("LYRICS_REJECTED/line_under_no_voice_cue",
     re.compile(r"lyric line under a no-voice tag \(it would be sung\): (?P<line>.+)"
                r"|section (?P<section>.+?) has no voice but carries lyric lines")),
)
_DETAIL_FACTS = {
    "REPAIR_CAP": re.compile(r"repair cap (?P<cap>\d+); this attempt would be repair (?P<attempt>\d+)"),
    "REPAIR_CAP_EXHAUSTED": re.compile(r"\((?P<attempt>\d+) attempts, cap (?P<cap>\d+)\)"),
    "SONG_LENGTH_NOT_SUPPORTED": re.compile(
        r"asks for a (?P<asked>[\d.]+)-second song .*? at most (?P<max_s>[\d.]+) seconds"),
}
_FIELD_WORDS = {"video_style": "video style", "audio_style": "music style",
                "length": "length", "video_model": "video model"}


def _split_choices(cell):
    """Split a table choices cell on top-level <br>, keeping conditional
    blocks whole: a {+name}...{/name} span may itself contain <br>."""
    parts, depth, cur = [], 0, ""
    for tok in re.split(r"(<br>|\{\+\w+\}|\{/\w+\})", cell):
        if not tok:
            continue
        if _BLOCK_OPEN.fullmatch(tok):
            if depth == 0 and cur.strip():
                parts.append(cur.strip())
                cur = ""
            depth += 1
            cur += tok
        elif _BLOCK_CLOSE.fullmatch(tok):
            depth = max(0, depth - 1)
            cur += tok
            if depth == 0:
                parts.append(cur.strip())
                cur = ""
        elif tok == "<br>" and depth == 0:
            if cur.strip():
                parts.append(cur.strip())
            cur = ""
        else:
            cur += tok
    if cur.strip():
        parts.append(cur.strip())
    return parts


def explanation_table(path=None):
    """{code: {what_happened, why, fix, choices[]}} from the reference table."""
    key = path or TABLE_PATH
    if key in _TABLE:
        return _TABLE[key]
    rows = {}
    try:
        with open(key, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        text = ""
    body = text.split(TABLE_HEAD, 1)[1] if TABLE_HEAD in text else ""
    body = body.split("\n## ", 1)[0]
    for line in body.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 5:
            continue
        rows[cells[0].strip("`")] = {
            "what_happened": cells[1], "why": cells[2], "fix": cells[3],
            "choices": [c.strip() for c in _split_choices(cells[4]) if c.strip()]}
    _TABLE[key] = rows
    return rows


def length_words(seconds):
    """60 -> '60-second', 120 -> '2-minute' (the card's own spellings)."""
    s = int(round(float(seconds)))
    return "%d-minute" % (s // 60) if s >= 120 and s % 60 == 0 else "%d-second" % s


def _num(v):
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _derive(facts):
    f = {k: v for k, v in facts.items() if v is not None and v != ""}
    if "delivered_s" in f and "length" not in f:
        try:   # the gate measures DELIVERED seconds; the client chose 2 s more
            f["length"] = length_words(float(f["delivered_s"]) + 2)
        except (TypeError, ValueError):
            pass
    if "fit_length_s" in f:
        try:
            f["fit_length"] = length_words(f["fit_length_s"])
        except (TypeError, ValueError):
            pass
    if isinstance(f.get("missing"), (list, tuple)) and f["missing"]:
        f["missing"] = ", ".join(_FIELD_WORDS.get(str(m), str(m).replace("_", " "))
                                 for m in f["missing"])
    if isinstance(f.get("line"), str):
        f["line"] = f["line"].strip().strip("'\"")
        # A lyric line naming a run path is a leak vector: keep words, cut path.
        cut = _RUN_PATH.sub(" ", _QUOTED_PATH.sub(" ", f["line"]))
        if _PATHISH.search(cut):
            f["line"] = "that line"
        else:
            f["line"] = re.sub(r"\s{2,}", " ", cut).strip(" ;:,-")
            if len(f["line"].split()) < 2:
                f["line"] = "that line"
    return {k: _num(v) for k, v in f.items()}


def _fill(text, facts):
    def _blocks(s):
        # innermost-first: drop or keep each {+name}...{/name} span
        while True:
            m = _BLOCK_OPEN.search(s)
            if not m:
                return s
            name, start = m.group(1), m.start()
            depth, i = 1, m.end()
            while depth:
                o = _BLOCK_OPEN.search(s, i)
                c = _BLOCK_CLOSE.search(s, i)
                if c is None:
                    return s  # unbalanced: leave the rest alone
                if o is not None and o.start() < c.start():
                    depth += 1
                    i = o.end()
                else:
                    depth -= 1
                    i = c.end()
                    if depth == 0:
                        inner = s[m.end():c.start()]
                        s = s[:start] + (inner if facts.get(name) else "") + s[c.end():]
        return s
    out = _blocks(text)
    # Split choices on <br> BEFORE filling, so a dropped span never leaves a
    # dangling separator and a kept span never leaks block tags.
    seps = [m.start() for m in re.finditer(r"<br>", out)]
    out = _PH.sub(lambda m: str(facts.get(m.group(1)) or (m.group(2) or "")), out)
    out = re.sub(r"\s{2,}", " ", out).strip(" ,")
    out = re.sub(r"(?:^|<br>)\s*<br>", "<br>", out)
    out = re.sub(r"<br>\s*<br>", "<br>", out).strip(" ,")
    return out.replace(" ,", ",").replace(" .", ".").strip()


def _scrub(text, code=""):
    """Plain words from an envelope's own text, or "" when it is not fit for a
    client (a command, a stack trace, or too little left). A run-folder or
    /tmp path is cut but the words around it stay, so the stop still explains
    itself; anything outside the run (a home dir, .py/.json source file, an
    --option or `backticked` command) rejects the whole text."""
    t = str(text or "")
    if "Traceback" in t:
        return ""
    cut = _RUN_PATH.sub(" ", _QUOTED_PATH.sub(" ", t))
    if _PATHISH.search(cut):
        return ""
    t = cut
    if code:
        t = t.replace(code, " ")
    t = _CODE_TOKEN.sub(" ", t)
    t = re.sub(r"\s{2,}", " ", t).strip(" ;:,-")
    t = re.sub(r"\s+([.,])", r"\1", t).strip(" ;:,-")
    return t if len(t.split()) >= 3 else ""


def _sentence(t):
    t = t.strip()
    return t[:1].upper() + t[1:] + ("" if t.endswith((".", "!", "?")) else ".")


def _message(p):
    lines = ["What happened: " + p["what_happened"], "",
             "Why this rule is here: " + p["why"], "",
             "What will fix it: " + p["fix"], "",
             "What would you like me to do?"]
    lines += ["%d. %s" % (i, c) for i, c in enumerate(p["choices"], 1)]
    lines += ["", "Reply with the number you want."]
    return "\n".join(lines)


def _row_parts(row, facts):
    parts = {"what_happened": _fill(row["what_happened"], facts),
             "why": _fill(row["why"], facts), "fix": _fill(row["fix"], facts),
             "choices": [_fill(c, facts) for c in row["choices"]]}
    # A conditional span that did not apply leaves an empty choice: drop it
    # (the table still guarantees 2-4 choices; the test holds the floor).
    parts["choices"] = [c for c in parts["choices"] if c.strip()]
    return parts


def _charged(env):
    """True only when the stop's own envelope records a provider charge:
    recorded credits consumed or cost, an accepted submit stamp, or generated
    media. Anything else -- a refused dispatch, a held gate, a garbled check --
    was stopped before spend."""
    ev = env.get("evidence") if isinstance(env, dict) else None
    if isinstance(ev, dict):
        for k in _CHARGED_KEYS:
            v = ev.get(k)
            if isinstance(v, bool):
                if v and k != "generated":
                    return True
            elif isinstance(v, (int, float)) and v > 0:
                return True
            elif isinstance(v, str) and v.strip() and k in (
                    "accepted_submit_at",):
                return True
        gen = ev.get("generated")
        if gen is True:
            return True
    return False


def _lyric_parts(table, detail, facts, charged=False):
    """One LYRICS_REJECTED detail can carry several causes; explain each."""
    found = []
    for cause in [c.strip() for c in detail.split("; ") if c.strip()]:
        for key, rx in _LYRIC_CAUSES:
            m = rx.search(cause)
            if m and key in table:
                found.append((key, {k: v for k, v in m.groupdict().items() if v}))
                break
        else:
            found.append(("LYRICS_REJECTED", {}))
    order = [k for k, _ in _LYRIC_CAUSES] + ["LYRICS_REJECTED"]
    seen, parts = set(), []
    for key, local in sorted(found, key=lambda kv: order.index(kv[0])):
        if key in seen or key not in table:
            continue
        seen.add(key)
        parts.append(_row_parts(table[key], _derive(dict(local, **facts))))
    if not parts:
        return None
    choices = []
    for p in parts:
        choices += [c for c in p["choices"] if c not in choices]
    # LYRICS_REJECTED is raised while the request is built, before any spend.
    what = " ".join(p["what_happened"] for p in parts)
    if not charged and "nothing new was charged" not in what.lower():
        what += " I stopped before making the song, so nothing new was charged."
    return {"what_happened": what,
            "why": " ".join(dict.fromkeys(p["why"] for p in parts)),
            "fix": " ".join(p["fix"] for p in parts),
            "choices": choices[:4]}


def explain_stop(reason_code, facts=None, envelope=None):
    """Four plain parts plus the ready message for ONE stop. Never empty,
    never a raw reason code, a file path or a stack trace."""
    try:
        env = envelope if isinstance(envelope, dict) else {}
        code = str(reason_code or env.get("reason_code") or env.get("code") or "")
        detail = str(env.get("detail") or env.get("reason") or "")
        nxt = str(env.get("next_action") or env.get("recovery") or "")
        merged = {}
        ev = env.get("evidence")
        if isinstance(ev, dict):
            merged.update({k: v for k, v in ev.items() if isinstance(v, (int, float, str))})
            if isinstance(ev.get("missing_card_fields"), list):
                merged["missing"] = ev["missing_card_fields"]
        if isinstance(env.get("missing"), list):
            merged["missing"] = env["missing"]
        rx = _DETAIL_FACTS.get(code)
        m = rx.search(detail + " " + nxt) if rx else None
        if m:
            merged.update({k: v for k, v in m.groupdict().items() if v})
        merged.update(facts or {})
        table = explanation_table()
        parts = _lyric_parts(table, detail, merged, _charged(env)) \
            if code == "LYRICS_REJECTED" else None
        if parts is None and code in table:
            parts = _row_parts(table[code], _derive(merged))
        if parts is None:
            what = _scrub(detail, code)
            fix = _scrub(nxt, code)
            parts = {"what_happened": _sentence(what) if what else GENERIC_WHAT,
                     "why": GENERIC_WHY,
                     "fix": _sentence(fix) if fix else GENERIC_FIX,
                     "choices": list(GENERIC_CHOICES)}
    except Exception:  # noqa: BLE001 - an explanation must never break a stop
        parts = {"what_happened": GENERIC_WHAT, "why": GENERIC_WHY, "fix": GENERIC_FIX, "choices": list(GENERIC_CHOICES)}
    parts["message"] = _message(parts)
    return parts
