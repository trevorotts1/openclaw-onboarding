#!/usr/bin/env python3
"""Client intake engine: one question bank, one answers file per run, the same in every harness.

  next_question(doc)        the ONE next question, hydrated (plain text, choices, why, help label)
  next_batch(doc)           the next few independent questions of one group (for the structured question tool)
  record(doc, id, value)    store an answer (or start the help path when the client says they do not know)
  resolve_unknown(doc, id)  help first (explain, examples, palettes, logo or website colors), then a safe
                            default flagged "to confirm". Never-default questions stay blocked, by name.
  finalize(doc)             apply the safe default to every remaining defaultable question, then check()
  check(doc)                {"ready", "blocking", "unanswered", "to_confirm", "warnings"}

The doc is plain JSON (answers.schema.json). Every function mutates the doc in memory; save() writes it
atomically, so any harness can stop and resume from the file. stdlib only; palette_help needs Pillow for
logo files only.

CLI:  engine.py FILE next | record ID VALUE [--ref MESSAGE_ID] | help ID [--logo F --site URL --palette N --mood "..."] |
      check | finalize | report | show      (FILE is created on first use;
      --mode launch|legacy|bf|page, --page-kind sales|opt_in for a page run)
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from decimal import Decimal
from datetime import date, datetime, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import palette_help as ph  # noqa: E402

BANK_PATH = Path(__file__).with_name("question-bank.json")
STATUSES = ("provided", "suggested", "default_to_confirm", "unknown")
HELP_WORDS = {"help", "help me", "not sure", "not sure yet", "im not sure", "i am not sure", "i dont know", "idk",
              "unsure", "i have no idea", "no idea", "dont know", "im not sure, help me", "im not sure help me", "no clue"}
# a short reply built from one of these phrases is a help request, never an answer
HELP_PHRASES = re.compile(r"\b(?:not sure|no idea|no clue|don'?t know|dont know|idk|unsure|help me|need help)\b")
_MAX_HELP_WORDS = 6  # longer replies are real answers that merely mention a phrase
SENTINEL = "CLIENT_MUST_SUPPLY"  # the Skill 71 brand-file marker for "not supplied yet"
ROLE_ORDER = ("primary", "secondary", "accent", "background", "text")
# The eight launch-operation areas, at the ids the shared intake contract fixes. A bank
# question may name its own "topic"; this map is the fallback so the ids always reach the
# client surface and the ledger. Every one of these questions is conditional (never legacy).
LAUNCH_TOPICS = {
    "timing": "launch_calendar",
    "channels": "channels",
    "conversation_ai": "conversation_ai",
    "access_delivery": "access_delivery",
    "payment_plans": "payment_plans",
    "sender_name": "sender_name",
    "reply_email": "reply_to_email",
    "texting_readiness": "a2p_ready",
}
_TOPIC_BY_QUESTION = {v: k for k, v in LAUNCH_TOPICS.items()}
# The three assistance preferences the client may pick and change at any time.
ASSISTANCE_MODES = {"choose_for_me": "A", "help": "B", "know": "C"}
# interview_mode answers resolve from the bank's long-form A/B/C wording, a bare
# A/B/C letter, or the older short phrases (kept as synonyms). None = the text names
# no recognizable preference — free text or a help phrase — never a silent default.
_MODE_LETTERS = {"a": "choose_for_me", "b": "help", "c": "know"}
_MODE_PHRASES = (("recommend a plan", "choose_for_me"),
                 ("guide me through", "help"),
                 ("already have a plan", "know"),
                 ("know what i want", "know"),
                 ("help me choose", "help"),
                 ("set it up for me", "choose_for_me"),
                 ("choose a setup for me", "choose_for_me"))
_BANK = None


def _mode_from_answer(raw):
    """interview_mode answer -> know/help/choose_for_me, or None when the text names
    no recognizable preference (a help request or free text, handled by the caller)."""
    n = _norm(raw)
    letter = re.match(r"^\(?([abc])\)?[.:\s]*$", n)
    if letter:
        return _MODE_LETTERS[letter.group(1)]
    for phrase, mode in _MODE_PHRASES:
        if phrase in n:
            return mode
    return None


def load_bank(path=None):
    global _BANK
    if path is not None:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    if _BANK is None:
        _BANK = json.loads(BANK_PATH.read_text(encoding="utf-8"))
    return _BANK


def question(qid, bank=None):
    for q in (bank or load_bank())["questions"]:
        if q["id"] == qid:
            return q
    raise KeyError(f"unknown question id {qid!r}")


# ---------------------------------------------------------------- the answers file
def new_doc(mode="launch", harness=None, run_id=None, page_kind=None):
    doc = {"schema": "client-intake-answers/v1", "meta": {"mode": mode, "phase": "pre_build"}, "answers": {}, "to_confirm": []}
    if mode == "page" and page_kind:
        doc["meta"]["page_kind"] = page_kind
    if harness:
        doc["harness"] = harness
    if run_id:
        doc["run_id"] = run_id
    return doc


def load(path, mode="launch"):
    p = Path(path)
    if not p.is_file():
        return new_doc(mode)
    doc = json.loads(p.read_text(encoding="utf-8"))
    derive_payment_plans(doc)  # a flag saved by an older run is still derived, never asked
    return doc


def save(doc, path):
    _sync_to_confirm(doc)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".answers-", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")
    os.replace(tmp, p)  # atomic: a stopped harness never leaves half a file


def get(doc, qid):
    return doc["answers"].get(qid)


def val(doc, qid, usable_only=True):
    e = get(doc, qid)
    if e is None or (usable_only and e["status"] == "unknown"):
        return None
    return e["value"]


def _set(doc, qid, value, status, source, note=None, keep_count=True):
    old = get(doc, qid) or {}
    e = {"value": value, "status": status, "source": source}
    if note:
        e["note"] = note
    if keep_count and old.get("unknown_count"):
        e["unknown_count"] = old["unknown_count"]
    doc["answers"][qid] = e
    return e


def _norm(t):
    return " ".join(re.sub(r"[^a-z0-9' ,.\-]", " ", str(t or "").lower()).split())


# ---------------------------------------------------------------- brand colour roles
def _colors(doc):
    c = val(doc, "brand_colors")
    return [h for h in c if isinstance(h, str)] if isinstance(c, list) else []


def _role_vals(doc):
    return {r: val(doc, f"brand_{r}") for r in ROLE_ORDER}


def _used(doc):
    out = set()
    for r, v in _role_vals(doc).items():
        out.update(v if isinstance(v, list) else ([v] if v else []))
    return out


def _remaining(doc):
    used = _used(doc)
    return [c for c in _colors(doc) if c not in used]


def autofill_roles(doc):
    """Assign the roles that need no question. The client is only asked when there is a real choice."""
    colors = _colors(doc)
    if not colors:
        return
    if get(doc, "brand_primary") is None or get(doc, "brand_primary")["status"] == "unknown":
        if len(colors) == 1:
            _set(doc, "brand_primary", colors[0], "provided", "only-color")
    rem = _remaining(doc)
    if val(doc, "brand_primary") and get(doc, "brand_secondary") is None and len(rem) == 1:
        _set(doc, "brand_secondary", rem[0], "provided", "only-color-left")
    rem = _remaining(doc)
    if val(doc, "brand_primary") and (get(doc, "brand_secondary") or len(colors) < 2) and get(doc, "brand_accent") is None and len(rem) == 1:
        _set(doc, "brand_accent", rem, "provided", "only-color-left")
    bg = val(doc, "brand_background")
    if bg and get(doc, "brand_text") is None:
        _set(doc, "brand_text", ph.readable_text_for(bg[0]), "suggested", "contrast rule", "Picked so the text is easy to read on the background.")


def needs_role(doc, role):
    colors = _colors(doc)
    if not colors or get(doc, f"brand_{role}") is not None and get(doc, f"brand_{role}")["status"] != "unknown":
        return False
    if role == "background":
        return True
    if role == "primary":
        return len(colors) >= 2
    if not val(doc, "brand_primary"):
        return False
    rem = _remaining(doc)
    if role == "secondary":
        return len(rem) >= 2
    if role == "accent":
        return len(rem) >= 2 and (get(doc, "brand_secondary") is not None or len(colors) < 3)
    return False


def roles(doc):
    """The client's palette as roles, with the status of the weakest piece."""
    autofill_roles(doc)
    r = _role_vals(doc)
    if not r["primary"]:
        return None
    acc = r["accent"] if isinstance(r["accent"], list) else ([r["accent"]] if r["accent"] else [])
    out = {"primary": r["primary"], "accent": acc, "background": r["background"] or ["#FFFFFF"],
           "text": r["text"] or ph.readable_text_for((r["background"] or ["#FFFFFF"])[0])}
    if r["secondary"]:
        out["secondary"] = r["secondary"]
    # a derived piece (the contrast-rule text colour) is documented like derived fonts,
    # never a proposal: it must not relabel the client's accepted palette
    sts = [ent["status"] for ent in (get(doc, f"brand_{k}") for k in ROLE_ORDER)
           if ent and ent.get("source") != "contrast rule"]
    status = ("default_to_confirm" if "default_to_confirm" in sts
              else "suggested" if "suggested" in sts else "provided")
    return {"roles": out, "status": status, "confirmed": status == "provided", "warnings": ph.check_palette(out)}


# ---------------------------------------------------------------- profiles and derived fields
def profile(doc, bank=None):
    """The ask list the doc's mode declares, or None. Mode page is Skill 71's page-only
    profile: its questions are the ask list, and nothing outside it is ever put to the client."""
    b = bank if isinstance(bank, dict) else load_bank()
    profiles = b.get("profiles") or {}
    if not profiles and b is not load_bank():  # a partial bank still obeys the canonical ask list
        profiles = load_bank().get("profiles") or {}
    return profiles.get((doc.get("meta") or {}).get("mode"))


_BILLING_PAYMENT_PLANS = {"one_time": False, "recurring": True, "installment": True}
# the bank's own answer text, which apply_default records verbatim
_BILLING_TEXT = {"all at once": "one_time", "monthly": "recurring", "in parts or trial first": "installment"}


def _billing_key(value):
    """one_time / recurring / installment from the stored key or the bank's answer text.
    Anything else - including a malformed hand-edited value - maps to None, never a crash."""
    if not isinstance(value, str):
        return None
    return value if value in _BILLING_PAYMENT_PLANS else _BILLING_TEXT.get(_norm(value))


def derive_payment_plans(doc):
    """The payment-plan flag comes from the billing answer. It is derived, never asked,
    and it inherits the billing answer's own state: a defaulted billing answer may not
    produce a confirmed payment-plan flag."""
    if (doc.get("meta") or {}).get("mode") == "legacy":
        return get(doc, "payment_plans")
    have = get(doc, "payment_plans")
    if have is not None and have["status"] != "unknown" and have.get("source") != "derived-billing":
        return have  # an answer recorded outside the derivation wins
    b = get(doc, "billing")
    key = _billing_key(b["value"]) if b is not None else None
    if b is None or b["status"] == "unknown" or key is None:
        return have
    return _set(doc, "payment_plans", _BILLING_PAYMENT_PLANS[key], b["status"], "derived-billing",
                f"Derived from your billing answer ({b['value']}); this is never asked.")


def page_kind(doc):
    return (doc.get("meta") or {}).get("page_kind")


def is_opt_in(doc):
    """The recorded page kind governs the length rule - including when --page-kind was
    stamped on a doc whose mode is not page. Enforcement never depends on two flags."""
    return page_kind(doc) == "opt_in"


# ---------------------------------------------------------------- conditions
def _token(doc, qid):
    if qid == "mode":
        return doc.get("meta", {}).get("mode")
    if qid == "phase":
        return doc.get("meta", {}).get("phase")
    e = get(doc, qid)
    if e is None or e["status"] == "unknown":
        return None
    v = e["value"]
    if v is None or (isinstance(v, str) and v.lower() in ("none", "no")):
        return "none"
    if isinstance(v, str):
        return "yes" if v.lower().startswith("yes") else v.lower()
    return "set"


def cond_met(doc, cond):
    if cond in (None, "always"):
        return True
    if " and " in cond:  # every part must hold; a question with two conditions is never half-asked
        return all(cond_met(doc, c.strip()) for c in cond.split(" and "))
    m = re.fullmatch(r"(\w+) (==|!=) (\w+)", cond)
    if m:
        t = _token(doc, m.group(1))
        return t is not None and ((t == m.group(3)) == (m.group(2) == "=="))
    m = re.fullmatch(r"(\w+) answered", cond)
    if m:
        return get(doc, m.group(1)) is not None and get(doc, m.group(1))["status"] != "unknown"
    m = re.fullmatch(r"(\w+) contains (\w+)", cond)
    if m:  # a follow-up question that only applies when the answer names a word, e.g. channels contains text
        e = get(doc, m.group(1))
        if e is None or e["status"] == "unknown":
            return False
        v = e["value"]
        words = " ".join(_norm(x) for x in (v if isinstance(v, list) else [v]))
        return (" " + m.group(2) + " ") in (" " + words + " ")
    m = re.fullmatch(r"needs_role (\w+)", cond)
    if m:
        return needs_role(doc, m.group(1))
    raise ValueError(f"unknown condition {cond!r}")


def applicable(doc, bank=None):
    autofill_roles(doc)
    derive_payment_plans(doc)
    prof = profile(doc, bank)
    allowed = set(prof["questions"]) if prof else None
    return [q for q in (bank or load_bank())["questions"]
            if cond_met(doc, q["condition"]) and (allowed is None or q["id"] in allowed)]


def topics(doc, bank=None):
    """The eight launch-operation areas keyed by their contract ids (timing, channels,
    conversation_ai, access_delivery, payment_plans, sender_name, reply_email,
    texting_readiness). Conditional: an area that does not apply to this run is marked so,
    never asked."""
    out = {}
    for topic, qid in LAUNCH_TOPICS.items():
        entry = get(doc, qid)
        out[topic] = {"question_id": qid,
                      "applicable": any(q["id"] == qid for q in applicable(doc, bank)),
                      "state": ("answered" if entry and entry["status"] != "unknown"
                                else "help_open" if entry else "unasked")}
    return out


def assistance_mode(doc):
    """A (recommend a plan for me), B (guide me through each decision) or C (I already
    have a plan). Read fresh on every call, so the client may change it mid-flow."""
    e = get(doc, "interview_mode")
    v = e["value"] if e is not None and e["status"] != "unknown" else None
    if v is not None and v not in ASSISTANCE_MODES:
        v = _mode_from_answer(v)   # long-form A/B/C wording or an older synonym
    return ASSISTANCE_MODES.get(v, "B")


# ---------------------------------------------------------------- asking
def hydrate(doc, q):
    """The question exactly as a client should see it (text filled in, dynamic choices resolved).
    Nested help.examples, default.value and every per-option explanation survive untouched."""
    q = json.loads(json.dumps(q))
    q.setdefault("topic", _TOPIC_BY_QUESTION.get(q["id"]))
    if q.get("dynamic") == "colors":
        role = q["id"].split("_", 1)[1]
        pool = _colors(doc) if role == "primary" else _remaining(doc)
        q["text"] = q["text"].replace("{colors}", "(" + ", ".join(pool) + ")")
        q["choices"] = (pool + (["None"] if role == "accent" else []))[:3]
    if q["id"] == "design_style" and isinstance(q.get("help"), dict) and isinstance(q["help"].get("examples"), list):
        q["help"]["examples"] = q["help"]["examples"] + _style_links()
    if q["id"] == "copy_profile" and is_opt_in(doc):
        q["choices"] = [c for c in q["choices"] if _norm(c) != "standard"]  # opt-in is long-form only
    return q


def _style_links():
    """The design-style visual examples, wherever this distribution installs Skill 71.
    One line per style, never silently dropped: a style with no example image says so, so
    the client is not told a picture exists when it does not."""
    names = ("71-blackceo-signature-page", "blackceo-signature-page")  # repo tree vs skills tree
    bases = [p / n for p in Path(__file__).resolve().parents for n in names]
    home = Path.home()
    for root in (home / ".openclaw" / "skills", home / ".claude" / "skills",
                 home / ".claude-nine" / "skills", Path("/data/.openclaw/skills")):
        bases += [root / n for n in names]
    for base in bases:
        f = base / "references" / "design-styles.json"
        if f.is_file():
            try:
                styles = json.loads(f.read_text())["styles"]
            except (OSError, ValueError, KeyError, TypeError):
                return []
            return _style_lines(styles)
    return []


def _style_lines(styles):
    """One honest line per style. A malformed entry is skipped, never crashes the ask
    (a nameless entry has nothing to disclose); a missing or non-string URL is "none"."""
    out = []
    for s in styles if isinstance(styles, list) else []:
        if not isinstance(s, dict):
            continue
        ex = s.get("example")
        url = ex.get("url") if isinstance(ex, dict) else None
        name = f"{s.get('id', '?')} {s.get('name', '')}".strip()
        out.append(f"{name} example: {url}" if isinstance(url, str) and url
                   else f"{name} example: none available yet - this style has no example image")
    return out


def _askable(doc, q):
    e = get(doc, q["id"])
    if e is None:
        return True
    if e["status"] != "unknown":
        return False
    return not (q["never_default"] and e.get("unknown_count", 0) >= 2)  # keep moving; check() names the blocker


def next_question(doc, bank=None):
    """The ONE next applicable question. Mode A (choose_for_me) and C (know) propose the
    safe defaults and ask only what is missing; mode B (help) walks every applicable
    question. One question at a time — never the raw bank."""
    mode = assistance_mode(doc)
    if mode in ("A", "C"):
        _default_the_rest(doc, bank)  # a proposal, every one flagged "to confirm"
    todo = [q for q in applicable(doc, bank) if _askable(doc, q)]
    if not todo:
        return None
    todo.sort(key=lambda q: not q["condition"].startswith("needs_role"))  # color-role follow-ups come right after the colors
    total = len(applicable(doc, bank))
    b = bank or load_bank()
    h = hydrate(doc, todo[0])
    h["help_label"] = b["help_label"]
    done = total - len(todo)
    h["progress"] = {"answered": done, "of": total,
                     "percent": (round(100 * done / total) if total else 100)}
    meta = doc.setdefault("meta", {})
    was = meta.get("estimate_of")
    note = (f"about {total} short questions now, depending on what we already know "
            f"(was {was}; your answers opened or closed follow-up questions)"
            if was is not None and was != total else None)
    template = b.get("question_estimate_template")
    meta["estimate_of"] = total
    h["estimate"] = {"questions": total, "note": note,
                     "text": (template.replace("{n}", str(total)) if template
                              else f"about {total} short questions, depending on what we already know")}
    h["assistance_mode"] = mode
    h["coaching"] = b.get("coaching")
    if was is None:
        h["introduction"] = b.get("introduction")  # flow opening, once
    return h


def next_batch(doc, limit=4, bank=None):
    """Up to `limit` unconditional questions of the same group, for a harness that can show several at once."""
    todo = [q for q in applicable(doc, bank) if _askable(doc, q)]
    if not todo:
        return []
    first = todo[0]
    batch = [first]
    if first["condition"] == "always":
        batch += [q for q in todo[1:] if q["group"] == first["group"] and q["condition"] == "always" and not q.get("dynamic")][:limit - 1]
    return [hydrate(doc, q) for q in batch]


# ---------------------------------------------------------------- recording
def wants_help(q, value):
    """True when the client says they do not know. A help request opens coaching and is
    never recorded as a substantive answer. 'Help me choose' is a real choice only for interview_mode."""
    if not isinstance(value, str):
        return False
    if value.strip() in ("?", "??", "???"):
        return True
    n = _norm(value).replace("'", "")
    if q["id"] == "interview_mode" and (_pick(value, q["choices"])
                                        or _mode_from_answer(value)):
        return False   # a real preference (bank wording, A/B/C letter or older synonym)
    return (n in HELP_WORDS or n.startswith("help me")
            or (len(n.split()) <= _MAX_HELP_WORDS and HELP_PHRASES.search(n) is not None)
            or any("not sure" in _norm(c) and _norm(c) == n for c in q["choices"]))


# Currencies the interview can price in. A symbol or code outside this set is never
# guessed: the client is asked which currency they mean.
ISO_CURRENCIES = ("USD", "EUR", "GBP")
_SYMBOL_CURRENCY = {"$": "USD", "\u20ac": "EUR", "\u00a3": "GBP"}
_AMOUNT = r"(\d{1,3}(?:,\d{3})+|\d+)(\.\d{1,2})?"
_MONEY_RE = re.compile(r"^(?:([A-Za-z]{3})\s*)?([$\u20ac\u00a3])?\s*" + _AMOUNT + r"(?:\s*([A-Za-z]{3}))?$")
_PRICE_QUESTION = "What price should I use? One number like 497, or $497, or USD 497."


def _parse_money(text):
    """(money, None) or (None, the question to ask). Strict: one amount, comma thousands only,
    at most two decimals, at most one currency marker (a $/euro/pound symbol or an ISO code from
    ISO_CURRENCIES). k/m suffixes, a second number, other separators and unknown currency
    markers are refused, never guessed. A bare number reads as USD; the caller echoes it."""
    t = str(text).strip()
    m = _MONEY_RE.match(t)
    if m:
        pre, sym, whole, frac, post = m.groups()
        marks = [x for x in (pre, sym, post) if x]
        if len(marks) <= 1:
            code = ((pre or post or "").upper() or _SYMBOL_CURRENCY.get(sym or "", "USD"))
            if code in ISO_CURRENCIES:
                minor = int((Decimal(whole.replace(",", "") + (frac or "")) * 100).to_integral_value())
                return {"amount_minor": minor, "currency": code}, None
            return None, "Which currency is that price in? I can use " + ", ".join(ISO_CURRENCIES) + "."
        return None, "I see two currency markers. Which one currency is the price in?"
    if len(re.findall(r"\d+(?:[.,]\d+)*", t)) > 1:
        return None, "I see more than one number. Which single price should I use? Please send just that one number."
    if re.search(r"\d[.,]\d{3,}", t):
        return None, "A price can have at most two decimal places, with commas only for thousands, like 1,497.00."
    if re.search(r"\d\s*[kKmM]\b|thousand|million", t):
        return None, "Please write the full number, for example 1500 instead of 1.5k."
    if re.search(r"[^\d\s,.$\u20ac\u00a3A-Za-z]|[A-Za-z]{2,}", t) and re.search(r"\d", t):
        return None, "Which currency is that price in? I can use " + ", ".join(ISO_CURRENCIES) + ", written like USD 497."
    return None, _PRICE_QUESTION


def _money(text):
    return _parse_money(text)[0]


def _pick(text, choices):
    n = _norm(text)
    for c in choices:
        if _norm(c) == n:
            return c
    for c in choices:
        if n and (n.startswith(_norm(c)) or _norm(c).startswith(n)):
            return c
    return None


def _bad_price(p):
    """The question to ask when a price dict is not a positive integer amount in an ISO currency."""
    amt, cur = p.get("amount_minor"), p.get("currency")
    if not cur:
        return "Which currency is the price in?"
    if cur not in ISO_CURRENCIES:
        return "Which currency is that? I can use " + ", ".join(ISO_CURRENCIES) + "."
    if not isinstance(amt, int) or isinstance(amt, bool) or amt <= 0:
        return "A price must be a positive whole number of cents."
    return None


PRICE_STATUSES = ("provided", "recommended_unapproved")


def _bad_package(p):
    """The refusal for a package dict: it needs a name, a valid price, and a price_status limited to
    provided or recommended_unapproved (never 'approved': approval is the client's, at the plan)."""
    if not (isinstance(p.get("display_name"), str) and p["display_name"].strip()):
        return "Every package needs a name."
    if not isinstance(p.get("price"), dict):
        return f"Package {p['display_name']!r} needs a price with a currency."
    bad = _bad_price(p["price"])
    if bad:
        return f"Package {p['display_name']!r}: {bad}"
    if p.get("price_status", "provided") not in PRICE_STATUSES:
        return f"Package {p['display_name']!r}: price_status can only be provided or recommended_unapproved, never {p['price_status']!r}."
    return None


_FUNNEL_SHAPES = (
    ("single_simple", r"\b(?:single|one)(?: simple)? offer\b|^(?:one|single|just one)$"),
    ("multiple_options", r"\b(?:few|several|multiple|couple of)\s+(?:\w+\s+)?(?:packages|options|tiers)\b|\bpackages\b"),
    ("folded_levels", r"\blevels? (?:that )?build\b|\bbuild(?:s|ing)? on each other\b|\bfolded levels\b"),
)


def _need(msg):
    return {"ok": False, "message": msg}


def _package_key(p):
    """One package's identity while accumulating: its name and its own price. A resent package is the
    same package, never a second copy."""
    price = p.get("price") if isinstance(p.get("price"), dict) else {}
    return (_norm(p.get("display_name")), price.get("amount_minor"), price.get("currency"))


def _normalize(doc, q, raw, *, accumulate=True):
    """(value, status, note) or a _need() dict. Free text always wins over the listed choices.
    accumulate=False reads an answer without touching the saved partial packages (citation checks)."""
    qid, t, ch = q["id"], q["answer_type"], q["choices"]
    text = str(raw).strip() if not isinstance(raw, (dict, list)) else raw
    low = _norm(text) if isinstance(text, str) else ""
    pick = _pick(text, ch) if isinstance(text, str) else None
    if qid == "interview_mode":
        raw_choice = pick or text
        mode = ({"i know what i want": "know", "help me choose": "help",
                 "set it up for me to review": "choose_for_me"}.get(_norm(raw_choice))
                or _mode_from_answer(raw_choice) or "help")
        return (mode, "provided", None)
    if qid == "design_style":
        m = re.match(r"^\(?([abc])\b", low) or re.search(r"\b(block|circle|hybrid)\b", low)
        if not m:
            return _need("Please answer A, B or C, or say 'help' and tell me three words for how you want your brand to feel.")
        k = m.group(1)
        return ({"block": "A", "circle": "B", "hybrid": "C"}.get(k, k.upper()), "provided", None)
    if qid == "funnel_shape":
        exact = next((c for c in ch if _norm(c) == low), None)  # an exact choice first
        if exact:
            return ("folded_levels" if exact.startswith("Levels") else "multiple_options" if exact == "A few packages"
                    else "single_simple"), "provided", None
        if text in ("single_simple", "multiple_options", "folded_levels"):
            return text, "provided", None
        # free text: anchored phrases only, a negated mention ("no levels") never counts, and
        # anything that is not exactly one shape is asked back, never guessed
        pos = re.sub(r"\b(?:no|not|without|never|don'?t (?:want|have|need))\s+(?:\w+\s+){0,2}?(?:levels?|packages?|tiers?|options)\b", " ", low)
        hits = [k for k, rx in _FUNNEL_SHAPES if re.search(rx, pos)]
        if len(hits) == 1:
            return hits[0], "provided", None
        return _need("Is it one offer, a few packages to choose from, or levels that build on each other?")
    if qid == "page_set":
        if low in ("all", "core"):
            return low, "provided", None
        if pick and pick.startswith("Every"):
            return "all", "provided", None
        if pick and pick.startswith("Only"):
            return "core", "provided", None
        return _need("Choose every page my funnel needs, or only the main page and checkout. Or say 'help'.")
    if t == "colors":
        parsed = ph.parse_colors(text if isinstance(text, str) else " ".join(text))
        if not parsed["colors"]:
            return _need("I could not read a color from that. Send color codes like #1A2B3C, common color names like navy or orange, or say 'help' and I will find them for you.")
        for r in (*ROLE_ORDER,):  # a new color answer replaces every earlier role, including a default palette
            doc["answers"].pop(f"brand_{r}", None)
        for r, v in parsed["roles"].items():  # roles the client labelled are recorded as given
            _set(doc, f"brand_{r}", v, "provided", "client")
        return parsed["colors"], "provided", ("I did not recognize: " + ", ".join(parsed["unknown"][:4])) if parsed["unknown"] else None
    if t == "choice" and qid.startswith("brand_") and q.get("dynamic"):
        if low in ("none", "no"):
            return [], "provided", None
        hexes = ph.to_hex(text)
        pool = ([*_colors(doc)] if qid == "brand_primary" else _remaining(doc))
        if low.isdigit() and 1 <= int(low) <= len(pool):
            hexes = pool[int(low) - 1]
        if not hexes:
            return _need("Please pick one of the listed colors, or send a color code like #1A2B3C.")
        return ([hexes] if qid == "brand_accent" else hexes), "provided", None
    if qid == "brand_background":
        if "dark" in low:
            dark = [c for c in _colors(doc) if ph.luminance(c) < 0.15]
            return [dark[0] if dark else "#111111"], "provided", None
        if low.startswith("light") or "white" in low or "cream" in low:
            return ["#FFFFFF"], "provided", None
        h = ph.to_hex(text)
        return ([h], "provided", None) if h else _need("Light, dark, or a color code for the background?")
    if qid == "logo":
        # Three ways, all the client's own choice: an existing logo, a clean name wordmark, or a new
        # logo made by the existing graphics capability. None is assumed and nothing is redrawn.
        if pick == "Create a new logo for me" or (("create" in low or "make" in low or "design" in low) and "logo" in low):
            brief = logo_brief(doc)
            propose(doc, qid, artifact={"kind": "logo", "brief": brief, "capability": GRAPHICS_CAPABILITY},
                    why="A new logo made from the name, colours, voice and style you already gave.")
            return ({"mode": "create", "brief": brief,
                     "capability": GRAPHICS_CAPABILITY["name"]}, "provided",
                    "I will have a new logo made and put it in the same asset map every page uses. "
                    "We keep going on the offers and the copy while it is made.")
        if pick == "Use my business name as text" or ("text" in low and "name" in low):
            return {"mode": "wordmark", "text": val(doc, "business_name")}, "provided", None
        if pick == "I will send it" or low in ("yes", "i will send it"):
            return _need("Please send the logo file (PNG or SVG), say 'use my business name as text', "
                         "or say 'create a new logo for me'.")
        return {"mode": "file", "path": str(text)}, "provided", None
    if qid == "billing_detail":
        # The rest of the plan the client actually asked for. Anything they did not say stays missing.
        n = re.search(r"\b(\d+)\s*(?:payments?|installments?)\b", low) or re.search(r"\d+", low)
        detail = {}
        for word, unit in _INTERVAL_WORDS:
            if word in low:
                detail["interval"] = unit
                break
        # the count of payments is only read when the client said how many payments there are
        if re.search(r"\b\d+\s*(?:payments?|installments?)\b", low):
            detail["installment_count"] = int(n.group(1))
        if "trial" in low or "free" in low:
            detail["trial"] = True
        if not detail:
            return _need("How many payments, how often, and is there a trial or an amount due today?")
        return detail, "provided", None
    if qid == "lead_magnet":
        # The free lead product is its own record: price zero is valid here and only here. A genuinely
        # paid offer keeps the positive-price rule.
        if isinstance(text, dict):
            return text, "provided", None
        if low in ("none", "no", "no thanks", "skip"):
            return "none", "provided", None
        structured = normalize_offer_prose(text, qid=qid)
        if pick == "Recommend one" or "recommend" in low:
            return _need("I only recommend from what you can actually give away. Tell me what you could "
                         "hand over for free and I will shape it for you to review.")
        if not structured["display_name"]:
            return _need("What is the free item called, and what do people get?")
        structured["price"] = {"amount_minor": 0, "currency": structured["price"]["currency"]
                               if structured["price"] else "USD"}
        return structured, "provided", None
    if qid == "fonts":
        if pick == "Pick good ones for me":
            return {"mode": "derive", "suggested": ph.fonts_suggestions()[0]}, "suggested", "Chosen by us; confirm or give your own."
        if pick == "I know my fonts" or low in ("yes", "i know my fonts"):
            return _need("Which fonts? A headline font and a text font are enough, like 'Playfair Display and Source Sans 3'.")
        parts = [p.strip() for p in re.split(r"/|,|\+|&| and |;", str(text)) if p.strip()]
        return {"mode": "given", "display": parts[0], "body": parts[1] if len(parts) > 1 else parts[0]}, "provided", None
    if qid in ("photos_founder", "photos_permission"):
        if low.startswith("yes") or low in ("y", "sure", "ok", "okay"):
            return "yes", "provided", None
        if low.startswith("no"):
            return "no", "provided", None
        return _need("A simple yes or no please.")
    if qid == "price":
        if isinstance(text, dict):  # a dict skips the parser: only a reasoned suggestion is kept, as a proposal
            bad = _bad_price(text)
            if bad or not text.get("rationale"):
                return _need(bad or "Send the price as the client's own words, like $497; a pre-built price is not accepted.")
            return text, "suggested", "Suggested price; it needs your approval."
        free = pick == "It is free" or low in ("free", "it is free")
        m, why = ({"amount_minor": 0, "currency": "USD"}, None) if free else _parse_money(text)
        if m and pick != "Suggest one for me to review":
            if m["amount_minor"] <= 0 and doc.get("meta", {}).get("mode") == "bf":
                # The free item is a lead product with its own record and its own opt-in journey. It is
                # never pushed through the paid checkout, and the paid offer keeps its positive price.
                propose(doc, "price", artifact={"kind": "free_entry", "name": val(doc, "offer_name"),
                                                "price": m},
                        why="The free item becomes a lead product with its own opt-in and thank-you, "
                            "not a paid checkout line.",
                        capability=None)
                return _need("That is a free lead magnet - a lead product, so I will carry it as its own "
                             "free entry, with its own opt-in page and thank-you page, and it never goes "
                             "through the paid checkout. The paid offer still needs a price above zero. "
                             "What should the paid offer cost?")
            return m, "provided", None
        if pick == "Suggest one for me to review" or "suggest" in low:
            return _need("Tell me what it includes and roughly who buys it. I will suggest a range with my reasoning for you to approve.")
        return _need(why)
    if t == "money":  # paid_render_approval
        if pick in ("No paid pieces", "Decide later") or low.startswith("no") or low.startswith("decide"):
            return {"approved": False, "decide_later": pick == "Decide later"}, "provided", None
        m = _money(text)
        if m:
            return {"approved": True, "cap_minor": m["amount_minor"], "currency": m["currency"]}, "provided", None
        return _need("Say 'no paid pieces', or the most you want to spend, like $200.")
    if qid == "billing":
        n = {"all at once": "one_time", "monthly": "recurring", "in parts or trial first": "installment"}.get(_norm(pick or ""))
        n = n or ("recurring" if "month" in low else "installment" if "part" in low or "trial" in low else "one_time" if "once" in low or "one" in low else None)
        return (n, "provided", None) if n else _need("All at once, monthly, or in parts?")
    if t == "offer":
        if (pick or "").startswith("No") or low in ("none", "no", "no thanks", "skip"):
            return "none", "provided", None
        if isinstance(text, dict):
            return text, "provided", None
        if pick in ("Yes, I have one", "Yes, a smaller version", "Yes, easier payments") or pick == "Easier payments" or low in ("yes", "yes i have one"):
            return _need("What is it called, what does the buyer get, and what does it cost?")
        if pick == "Recommend one" or "recommend" in low:
            return _need("I only recommend from products you have told me about. Tell me what you could offer and I will shape it for you to review.")
        if doc.get("meta", {}).get("mode") == "legacy":
            # the older step-by-step funnel's brief is plain text: a deliberate legacy request keeps
            # exactly the answers it always had, never a restructured record it does not read
            return str(text), "provided", None
        # Ordinary prose becomes the existing structured offer record, and the client's own words are
        # kept under source_text. A part they did not give stays missing, never invented.
        structured = normalize_offer_prose(text, qid=qid)
        if structured["missing"]:
            propose(doc, qid, artifact={"kind": "offer", **structured},
                    why="Read from what you wrote: " + ", ".join(structured["missing"]) + " still to confirm.",
                    action=structured)
            return dict(_need(f"I saved what you wrote. I still need the "
                              f"{', '.join(structured['missing'])}. One line with the name, what they "
                              "get and the price is enough."), action="proposal", id=qid,
                        proposal=structured)
        return structured, "provided", None
    if qid == "image_provider":
        n = {"My connected service": "connected", "Recommend one": "kie"}.get(pick or "")
        n = n or (low if low in ("kie", "agnes", "connected") else None)
        if not n:  # every page needs its canonical renders; "none" is not an answer
            return _need("Which image service should make your pictures: your connected one, or one I recommend? Every page needs its generated pictures, so there is no none.")
        return n, ("suggested" if pick == "Recommend one" else "provided"), None
    if qid == "image_cap":
        m = re.search(r"\d+", low)
        if not m or int(m.group(0)) <= 0:  # "no pictures" and 0 are the removed no-images path
            return _need("Every page needs its canonical set of generated pictures, so the number must be at least 1. A number like 12 is fine.")
        return int(m.group(0)), "provided", None
    if qid == "copy_profile":
        if not (pick or "standard" in low or "long" in low):
            return _need("Standard or long-form?")
        value = "long_form" if "long" in low else "standard"
        if value == "standard" and is_opt_in(doc):
            return _need("An opt-in landing page is long-form only. Say long-form, or change the page kind to a sales page.")
        return value, "provided", None
    if qid == "location":
        return ("existing" if "existing" in low or low.startswith("yes") else "new" if "new" in low else None, "provided", None) if (low.startswith("yes") or "new" in low or "existing" in low) else _need("Your existing account or a new one?")
    if qid == "entitlement":
        if pick == "Yes, it is included" or low.startswith("yes"):
            return "attested", "provided", None
        return "check" if pick == "Please check for me" else "no", "unknown", "Needs verification against the account record."
    if qid == "plan_approval":
        return ({"approve this plan": "approve", "i want a change": "change", "stop here": "stop"}.get(_norm(pick or text), None) or "change"), "provided", None
    if qid == "community_truth":
        if isinstance(text, dict):
            return text, "provided", None
        url = re.search(r"https?://\S+", text)
        if not url or not re.search(r"\b(yes|confirm)", low):
            return _need("I need the real community link, what the bonus is, and a yes that you will send the personal text.")
        bonus = re.sub(r"https?://\S+|[;,]?\s*\b(yes|confirmed?)\b.*$", "", re.split(r"bonus:?", text, flags=re.I)[-1], flags=re.I).strip(" ;,.")
        return {"community_url": url.group(0).rstrip(".,;"), "bonus": bonus, "founder_text_confirmed": True}, "provided", None
    if t == "packages":
        rows = text if isinstance(text, list) else [ln for ln in str(text).splitlines() if ln.strip()]
        pk, bad = [], []
        for row in rows:
            if isinstance(row, dict):
                err = _bad_package(row)
                if err:
                    return _need(err)
                pk.append(row)
                continue
            sym = re.findall(r"[$\u20ac\u00a3]\s*\d[\d,]*(?:\.\d+)?", row)
            cell = row.split("|")[-1].strip() if "|" in row else sym[0] if len(sym) == 1 else None
            m = _money(cell) if cell else None
            name = re.split(r"\s*(?:\||:|\s-\s|\(|\$|\u20ac|\u00a3)\s*", row.strip(" -*\u2022"), maxsplit=1)[0].strip()
            rest = [x.strip() for x in re.split(r"\|", row)[1:] if x.strip() and not re.fullmatch(r"[\$\u20ac\u00a3]?\s*[\d,.]+(\s*[A-Za-z]{3})?", x.strip(), re.I)]
            inc = [i.strip() for r in rest for i in re.split(r";", r) if i.strip()]
            if name and m and m["amount_minor"] > 0:
                pk.append({"display_name": name, "deliverables": inc, "price": m,
                           "source_text": row.strip()})
            else:
                bad.append(row.strip()[:60])
        if bad:
            return _need("I could not read one clear price in: " + "; ".join(bad) + ". Each package needs a name and one price, like: Premium | 12 lessons; 4 live calls | $497")
        if not pk:
            return _need("I need one package to start: a name and one price, like: Premium | 12 lessons; 4 live calls | $497")
        # Successive single-package turns ACCUMULATE. The first package is a valid PARTIAL record the
        # next turn adds to, so a client answering one package per turn still finishes; a resend of a
        # package already saved is the same package, never a second copy. The answer stays incomplete
        # until the client has actually described two, so nothing is invented to reach the minimum.
        part = doc.get("packages_partial") if accumulate else None
        if isinstance(part, dict):
            merged = list(part.get("packages") or [])
        else:  # a package added after the set was already recorded extends the recorded set
            have = val(doc, "packages") if accumulate else None
            merged = list(have) if isinstance(have, list) else []
        seen = {_package_key(p) for p in merged}
        for p in pk:
            k = _package_key(p)
            if k not in seen:
                seen.add(k)
                merged.append(p)
        if len(merged) < 2:
            if accumulate:
                doc["packages_partial"] = {"packages": merged,
                                           "note": f"{len(merged)} package saved; more collected next"}
            return _need("I need at least two, each with a name and a price, one per line. "
                         "I have saved the first one; send the next the same way. For example: "
                         "Premium | 12 lessons; 4 live calls | $497")
        # the completion path consumes the whole accumulated set, and with it each package's own words,
        # price and price_status, so a saved partial can never be dropped or silently re-statused. The
        # partial is cleared by record() only once the answer is actually saved, so a refused citation
        # never throws the packages the client already described away.
        st = "suggested" if any(p.get("price_status") == "recommended_unapproved" for p in merged) else "provided"
        return merged, st, None
    if t == "list":
        items = text if isinstance(text, list) else [s.strip(" -*•") for s in re.split(r"\n|;|,(?=\s)", text) if s.strip(" -*•")]
        return (items, "provided", None) if items else _need("Please give me at least one.")
    if q["required"] == "optional" and isinstance(text, str) and not text.strip():
        return None, "provided", "left blank on purpose"
    if not text or (isinstance(text, str) and not text.strip()):
        return _need("Please give me an answer, or say 'help'.")
    return text, "provided", None


# The commercial answers a client must have said in their own words. Each one recorded as
# 'provided' cites a source_message_ref that resolves to a CLIENT message in the transcript
# store, so an agent-chosen price or shape can never pass as the client's answer.
CITED_QUESTIONS = ("price", "packages", "deliverables", "funnel_shape", "entitlement")
_CLIENT_ROLES = ("client", "user", "customer", "inbound")
TRANSCRIPT_LOOKUP = None  # tests / a harness may set a callable(ref) -> {"role", "text"} or None


def client_message(ref):
    """The text of the client message `ref` names in the transcript store, or None.
    The store is the JSON or JSONL file named by CLIENT_INTAKE_TRANSCRIPT_STORE (an operator
    setting the agent does not write): messages {id, role, text}. A missing store, an unknown
    id or a non-client role all resolve to None."""
    if not isinstance(ref, str) or not ref.strip():
        return None
    if TRANSCRIPT_LOOKUP is not None:
        msg = TRANSCRIPT_LOOKUP(ref.strip())
    else:
        path = os.environ.get("CLIENT_INTAKE_TRANSCRIPT_STORE")
        msg = None
        try:
            raw = Path(path).read_text(encoding="utf-8") if path else ""
            try:
                rows = json.loads(raw)
                rows = rows.get("messages", []) if isinstance(rows, dict) else rows
            except ValueError:
                rows = [json.loads(ln) for ln in raw.splitlines() if ln.strip()]
            msg = next((r for r in rows if isinstance(r, dict) and str(r.get("id", r.get("message_id"))) == ref.strip()), None)
        except (OSError, ValueError, TypeError):
            msg = None
    if not isinstance(msg, dict) or str(msg.get("role", "")).lower() not in _CLIENT_ROLES:
        return None
    text = msg.get("text", msg.get("content"))
    return text if isinstance(text, str) and text.strip() else None


def _numbers(text):
    return {Decimal(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}


def _client_said(doc, q, raw, v, msg):
    """True when the cited client message really carries this answer: the raw text sits inside
    it, or the message on its own normalizes to the same answer. Listed items and package
    prices must each appear in it."""
    nm = _norm(msg)
    if isinstance(raw, str):
        if _norm(raw) and _norm(raw) in nm:
            return True
        out = _normalize(doc, q, msg, accumulate=False)  # a citation check never edits the partial
        return isinstance(out, tuple) and out[0] == v
    nums = _numbers(msg)
    for it in raw if isinstance(raw, list) else []:
        if isinstance(it, dict):
            if Decimal(it["price"]["amount_minor"]) / 100 not in nums:
                return False
        elif _norm(it) not in nm:
            return False
    return isinstance(raw, list) and bool(raw)


def _refused(code, message):
    return {"ok": False, "error": code, "message": message}


def _cite_error(doc, q, raw, v, source, ref):
    """None when a 'provided' commercial answer is properly cited, else the refusal."""
    if source != "client":
        return _refused("source_not_client", f"{q['id']} is a commercial answer: its source must be the client, not {source!r}.")
    msg = client_message(ref)
    if msg is None:
        return _refused("source_message_ref_required",
                        f"{q['id']} is a never-default commercial answer. Cite a source_message_ref that resolves to the client's own message in the transcript store.")
    if not _client_said(doc, q, raw, v, msg):
        return _refused("source_message_mismatch", f"The cited client message does not say this {q['id']}. Cite the message where the client said it.")
    return None


def record(doc, qid, value, *, source="client", status=None, note=None, source_message_ref=None):
    """Store an answer. Returns {"ok": True, ...}; {"ok": False, "message"} when the answer is incomplete;
    or the help payload when the client said they do not know. Price, packages, deliverables, funnel
    shape and entitlement recorded as provided need source_message_ref (see CITED_QUESTIONS). A price is
    echoed back first ("I heard USD 497.00, correct?") and recorded only after the client says yes."""
    q = question(qid)
    if wants_help(q, value):
        return resolve_unknown(doc, qid)
    if qid in ("brand_colors", "design_style") and isinstance(value, str):
        reply = _help_reply(doc, q, value)  # a reply to the help message: logo, website, 1-3, "yes", feel words
        if reply is not None:
            return reply
    ref = source_message_ref
    pend = ((get(doc, qid) or {}).get("pending") or {}) if qid == "price" else {}
    reply = _norm(value) if isinstance(value, str) else ""
    confirmed = bool(pend.get("money")) and reply in _YES
    if pend.get("money") and reply in ("no", "n", "nope"):
        _set(doc, qid, None, "unknown", "client", keep_count=False)
        return _need(_PRICE_QUESTION)
    if confirmed:  # the client said yes to the echo: the price came from the earlier message
        out, raw = (pend["money"], "provided", None), pend["raw"]
        err = _cite_error(doc, q, raw, pend["money"], source, pend.get("ref")) or (
            _refused("source_message_ref_required", "Cite the message where the client said yes.") if client_message(ref) is None else None)
        if err:
            return err
        ref_for_entry = pend["ref"]
    else:
        out = _normalize(doc, q, value)
        ref_for_entry = ref
    if isinstance(out, dict):
        return out
    v, st, nt = out
    if qid in CITED_QUESTIONS and status == "provided" and st != "provided":
        return _refused("status_not_provided", f"{qid} was not given as a final answer, so it cannot be recorded as provided.")
    st = status or st
    if q["never_default"] and st == "default_to_confirm":
        raise ValueError(f"{qid} is never defaulted")
    if qid in CITED_QUESTIONS and st == "provided" and not confirmed:
        err = _cite_error(doc, q, value, v, source, ref)
        if err:
            return err
        if qid == "price":  # echo first; nothing is recorded until the client says yes
            _pend(doc, qid, money=v, ref=ref, raw=value)
            shown = "free (USD 0.00)" if v["amount_minor"] == 0 else f"{v['currency']} {v['amount_minor'] / 100:,.2f}"
            assumed = "" if re.search(r"[A-Za-z$\u20ac\u00a3]", str(value)) else " (no currency given, so I took USD)"
            return {"ok": False, "action": "confirm_price", "heard": v, "message": f"I heard {shown}{assumed}, correct? Say yes to record it, or give me the right price."}
    e = _set(doc, qid, v, st, source, note or nt)
    if qid == "packages":
        doc.pop("packages_partial", None)  # the accumulated set is the recorded answer now
    if qid in CITED_QUESTIONS and st == "provided":
        e["source_message_ref"] = ref_for_entry
        if confirmed:
            e["confirmation_ref"] = ref
    if st == "unknown":
        e["unknown_count"] = e.get("unknown_count", 0) + 1
    autofill_roles(doc)
    derive_payment_plans(doc)  # billing answered: the payment-plan flag follows, never asked
    _sync_to_confirm(doc)
    return {"ok": True, "id": qid, "entry": e, "warnings": (roles(doc) or {}).get("warnings", []) if qid.startswith("brand_") else []}


# ---------------------------------------------------------------- not knowing the answer
_YES = ("yes", "y", "yep", "yeah", "ok", "okay", "sure", "use it", "use them")
_IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")


def _pend(doc, qid, **kw):
    """Remember what the help message offered, on the question's own entry, so the client's next reply can finish it."""
    e = get(doc, qid) or _set(doc, qid, None, "unknown", "client")
    e["pending"] = kw
    return e


def _help_reply(doc, q, text):
    """The replies the help messages ask for. None means: not one of those, use the normal path."""
    qid, low = q["id"], _norm(text)
    e = get(doc, qid) or {}
    pend = e.get("pending") or {}
    helped = e.get("status") == "unknown" and e.get("unknown_count", 0) >= 1
    if qid == "design_style":
        if pend.get("recommendation") and low in _YES:
            return record(doc, qid, pend["recommendation"])
        if pend.get("recommendation") and low in ("no", "n", "nope"):
            return _need("No problem. Pick A, B or C, or tell me three other words for how you want your brand to feel.")
        if helped and not re.match(r"^\(?[abc]\b", low) and not re.search(r"\b(block|circle|hybrid)\b", low) and low not in _YES and low:
            rec = _recommend_style(q, text)  # the three words the help message asked for
            _pend(doc, qid, mood=text, recommendation=rec["recommendation"])
            return dict(ok=False, action="recommend", **rec)
        return None
    if pend.get("colors") and low in _YES:  # "I read these colors ... Should I use them?"
        return record(doc, qid, " ".join(pend["colors"]), source=pend["source"])
    if text.strip().lower().startswith(("http://", "https://", "www.")):
        kw = {"website": text.strip() if "://" in text else "https://" + text.strip()}
    elif text.strip().lower().endswith(_IMAGE_EXT) or Path(text.strip()).expanduser().is_file():
        kw = {"logo": str(Path(text.strip()).expanduser())}
    elif helped and low.isdigit():
        kw = {"palette": low}
    elif helped and not ph.parse_colors(text)["colors"] and re.search(r"[a-z]", low):
        pals = ph.suggest_palettes((_colors(doc) or [None])[0], text)  # feel words: reorder the three palettes
        _pend(doc, qid, mood=text)
        return {"ok": False, "action": "palettes", "palettes": pals, "message": "From those words, here are 3 palettes. Say 1, 2 or 3, or send color codes."}
    else:
        return None
    try:
        return resolve_unknown(doc, qid, mood=pend.get("mood"), **kw)
    except (OSError, ValueError, ImportError) as err:
        return _need(str(err) if isinstance(err, ValueError) else "I could not read that. Send color codes, or say 1, 2 or 3 for a palette.")


def _how_to_change(q):
    return f"Tell me your new answer to \"{q['text'].split('?')[0].strip()}\" (question {q['id']}) and I will update it."


def _sync_to_confirm(doc):
    bc = get(doc, "brand_colors")
    covered = bc["source"] if bc and bc["status"] in ("default_to_confirm", "suggested") else None
    doc["to_confirm"] = [{"id": k, "value": e["value"], "reason": e.get("note") or ("Chosen for you; not confirmed yet." if e["status"] == "default_to_confirm" else "Suggested; not confirmed yet."),
                          "how_to_change": _how_to_change(question(k)) if _is_q(k) else f"Tell me the new {k.replace('_', ' ')} and I will update it."}
                         for k, e in doc["answers"].items() if e["status"] in ("default_to_confirm", "suggested")
                         and not (k.startswith("brand_") and k != "brand_colors" and (e["source"] == covered or e["source"] == "contrast rule"))]


def _is_q(qid):
    return any(q["id"] == qid for q in load_bank()["questions"])


def _apply_palette(doc, pal, status, source, note):
    r = pal["roles"]
    _set(doc, "brand_colors", [r["primary"]] + ([r["secondary"]] if r.get("secondary") else []) + r.get("accent", []), status, source, note)
    for k in ROLE_ORDER:
        if r.get(k):
            _set(doc, f"brand_{k}", r[k] if k in ("primary", "secondary", "text") else list(r[k]), status, source, note)


def apply_default(doc, qid):
    q = question(qid)
    if q["never_default"]:
        raise ValueError(f"{qid} is never defaulted")
    d = q["default"]
    if d is None:
        return None
    v, reason = d["value"], d["reason"]
    if qid == "brand_colors":
        _apply_palette(doc, ph.safe_default(), "default_to_confirm", "safe-default", reason)
        _sync_to_confirm(doc)
        return get(doc, qid)
    if qid == "logo":
        v = {"mode": "wordmark", "text": val(doc, "business_name")}
    elif qid == "fonts":
        v = {"mode": "derive", "suggested": ph.fonts_suggestions()[0]}
    elif qid == "copy_profile" and is_opt_in(doc):
        v = "long_form"  # an opt-in landing page has one valid length; the default cannot weaken it
    elif qid == "brand_primary" or v in ("first_color", "next_color"):
        pool = _colors(doc) if qid == "brand_primary" else _remaining(doc)
        v = (pool or [None])[0]
        if qid == "brand_accent":
            v = [v] if v else []
    elif qid == "brand_background":
        v = ["#FFFFFF"]
    e = _set(doc, qid, v, "default_to_confirm", "safe-default", reason)
    autofill_roles(doc)
    _sync_to_confirm(doc)
    return e


def resolve_unknown(doc, qid, *, logo=None, website=None, palette=None, mood=None, fetch=None):
    """The client does not know. First time: help. Second time: a safe default flagged 'to confirm'
    (never for a never-default question, which stays blocked and is named)."""
    q = question(qid)
    e = get(doc, qid) or {"value": None, "status": "unknown", "source": "client"}
    n = e.get("unknown_count", 0)
    if logo or website or palette:
        return _palette_action(doc, q, logo, website, palette, mood, fetch)
    mood = mood or (e.get("pending") or {}).get("mood")
    e = _set(doc, qid, None, "unknown", "client", keep_count=False)
    e["unknown_count"] = n + 1
    h = q["help"]
    payload = {"id": qid, "explain": h["explain"], "examples": h["examples"], "why": q["why"], "attempt": n + 1}
    if q["never_default"]:
        payload.update(action="blocked", message=f"I cannot guess this one, because {q['why'][0].lower() + q['why'][1:]} {h['explain']} Take your time; the build waits for this answer and I will list it as the thing I need.")
        return payload
    if n == 0:
        payload.update(action="help", message=h["explain"])
        if h["kind"] == "palette":
            seed = (_colors(doc) or [None])[0]
            payload.update(options=[{"id": "logo", "label": "Read the colors from my logo (send the file)"},
                                    {"id": "website", "label": "Read them from my website (send the link)"},
                                    {"id": "palette", "label": "Pick one of these 3 palettes (say 1, 2 or 3)"}],
                           palettes=ph.suggest_palettes(seed, mood or ""))
            if mood:
                _pend(doc, qid, mood=mood)
        elif h["kind"] == "fonts":
            payload["pairs"] = ph.fonts_suggestions()
        elif h["kind"] == "style" and mood:
            payload.update(_recommend_style(q, mood))
            _pend(doc, qid, mood=mood, recommendation=payload["recommendation"])
        return payload
    if h["kind"] == "style" and mood:  # the client gave feel words: the safe default is what they point to
        best = _recommend_style(q, mood)["recommendation"]
        _set(doc, qid, best, "default_to_confirm", "feel-words", "Picked from the words you used for how your brand should feel.")
        _sync_to_confirm(doc)
        return dict(payload, action="default_applied", value=best, flag="to confirm",
                    message=f"No problem. I will use {best} for now, picked from your words, marked TO CONFIRM. It will be listed in your delivery report with a one-line way to change it.")
    if q["default"] is None:
        return dict(payload, action="skipped", message="No problem, we will leave this one out.")
    d = apply_default(doc, qid)
    return dict(payload, action="default_applied", value=d["value"], flag="to confirm",
                message=f"No problem. I will use {_say(qid, d['value'])} for now, marked TO CONFIRM. It will be listed in your delivery report with a one-line way to change it.")


def _say(qid, v):
    if qid == "brand_colors":
        return "a neutral palette (" + ph.DEFAULTS["safe_default"]["name"] + ") that belongs to no client"
    if isinstance(v, dict):
        return v.get("text") or v.get("mode") or "a standard choice"
    return str(v)


def _recommend_style(q, mood):
    words = set(re.findall(r"[a-z]+", str(mood).lower()))
    score = {k: len(words & set(ws)) for k, ws in q["feel_keywords"].items()}
    best = max(score, key=lambda k: (score[k], k == "C"))
    name = {"A": "Block", "B": "Circle", "C": "Hybrid"}[best]
    return {"recommendation": best, "message": f"From those words I would pick {best} {name}. Say yes to use it, or pick another."}


def _palette_action(doc, q, logo, website, palette, mood, fetch):
    if palette:
        pals = ph.suggest_palettes((_colors(doc) or [None])[0], mood or "")
        idx = int(palette) - 1
        if not 0 <= idx < len(pals):
            return _need("Choose 1, 2 or 3.")
        _apply_palette(doc, pals[idx], "provided", f"palette-help:option-{idx + 1}", None)
        _sync_to_confirm(doc)
        return {"ok": True, "action": "palette_chosen", "palette": pals[idx]}
    got = ph.extract_from_logo(logo) if logo else ph.extract_from_website(website, fetch=fetch)
    if not got["colors"]:
        return {"ok": False, "action": "nothing_found", "message": "I could not read any colors from that. Send color codes, or pick one of the 3 palettes."}
    _pend(doc, q["id"], colors=got["colors"], source=got["source"])
    return {"ok": True, "action": "confirm_colors", "colors": got["colors"], "source": got["source"],
            "message": f"I read these colors from your {got['source']}: {', '.join(got['colors'])}. Should I use them? If yes, I will ask which one is your main color."}


# ---------------------------------------------------------------- checking and finishing
def check(doc, bank=None):
    autofill_roles(doc)
    blocking, unanswered = [], []
    for q in applicable(doc, bank):
        e = get(doc, q["id"])
        usable = e is not None and e["status"] != "unknown"
        if q["required"] == "optional" and not usable:
            continue
        if not usable:
            row = {"id": q["id"], "question": q["text"], "why": q["why"]}
            (blocking if q["never_default"] else unanswered).append(row)
        elif q["never_default"] and e["status"] in ("suggested", "default_to_confirm"):
            blocking.append({"id": q["id"], "question": q["text"], "why": "This is a suggestion until you approve it."})
    if is_opt_in(doc):
        e = get(doc, "copy_profile")
        if e is not None and e["status"] != "unknown" and e["value"] == "standard":
            blocking.append({"id": "copy_profile", "question": question("copy_profile")["text"],
                             "why": "An opt-in landing page is long-form only; record long-form, or change the page kind to a sales page."})
    _sync_to_confirm(doc)
    r = roles(doc)
    return {"ready": not blocking and not unanswered, "blocking": blocking, "unanswered": unanswered,
            "to_confirm": doc["to_confirm"], "warnings": r["warnings"] if r else []}


def _default_the_rest(doc, bank=None):
    """Apply every safe default still open, never the never-default ones. Each one is a
    proposal flagged 'to confirm', listed with a one-line way to change it."""
    for _ in range(4):  # defaults can unlock follow-up questions (roles); settle them
        for q in applicable(doc, bank):
            e = get(doc, q["id"])
            if (e is None or e["status"] == "unknown") and not q["never_default"] and q["required"] != "optional" and q["default"] is not None:
                apply_default(doc, q["id"])


def finalize(doc, bank=None):
    """'Use sensible defaults for the rest': defaults every defaultable question still open, never the
    never-default ones. Everything defaulted is listed in to_confirm."""
    _default_the_rest(doc, bank)
    return check(doc, bank)


# ---------------------------------------------------------------- views for the consumers
def view(doc):
    """Plain values keyed by question id, plus roles. What every consumer reads."""
    out = {k: e["value"] for k, e in doc["answers"].items() if e["status"] != "unknown"}
    r = roles(doc)
    if r:
        out["palette_roles"], out["palette_status"] = r["roles"], r["status"]
    return out


def to_sf_brief_answers(doc):
    """The legacy sf-intake q1..q18 answer keys, built from the one answers file."""
    v = view(doc)
    join = lambda *a: " - ".join(str(x) for x in a if x)  # noqa: E731
    pr = v.get("price")
    if pr is None and v.get("packages"):
        pr = min((p["price"] for p in v["packages"]), key=lambda x: x["amount_minor"])
    price = "free" if isinstance(pr, dict) and pr.get("amount_minor") == 0 else (f"{pr['currency']} {pr['amount_minor'] / 100:,.2f}" if isinstance(pr, dict) and "amount_minor" in pr else "")
    pal = v.get("palette_roles")
    colors = "; ".join(f"{k} {', '.join(x) if isinstance(x, list) else x}" for k, x in pal.items()) if pal else ""
    ph_ = v.get("photos_founder")
    out = {"q1_offer": join(v.get("offer_name"), v.get("offer_description")),
           "q2_price_promise": join(price, v.get("offer_transformation")),
           "q3_pains": "; ".join(v.get("pains") or []), "q4_people": v.get("audience"), "q5_goods": "; ".join(v.get("deliverables") or []),
           "q6_founder_story": v.get("founder_story"), "q7_brand_colors": colors, "q8_representation": v.get("representation"),
           "q9_voice": v.get("voice"), "q10_funnel_length": v.get("funnel_length"),
           "q11_oto1": _offer_text(v.get("upsell_1")), "q12_downsell1": _offer_text(v.get("downsell_1")),
           "q13_oto2": _offer_text(v.get("upsell_2")), "q14_downsell2": _offer_text(v.get("downsell_2")),
           "q15_reference_images": "client uploads" if ph_ == "yes" else "signature only", "q16_truth_gate": v.get("community_truth"),
           "q17_confirmation": "approved" if v.get("plan_approval") == "approve" else None, "q18_style_card_id": v.get("style_card_id")}
    return {k: x for k, x in out.items() if x not in (None, "", [])}


def _offer_text(x):
    return None if x in (None, "none") else (json.dumps(x) if isinstance(x, dict) else str(x))


_STATE = {"provided": "provided", "suggested": "recommended_unapproved", "default_to_confirm": "recommended_unapproved", "unknown": "unknown"}

# ---------------------------------------------------------------- launch answers, typed
# The eight launch answers a Signature Launch (Skill 49) must carry end to end. Raw
# client text is NEVER forwarded as-is: a string is not a boolean, and "No, not yet"
# must never read as a truthy A2P approval. Each adapter below returns a typed value
# or None (kept unknown), plus the provenance of the answer it came from.
LAUNCH_LEDGER_KEYS = (
    ("launch_calendar", ("launch.launch_at", "launch.doors_open_at", "launch.doors_close_at", "launch.timezone")),
    ("channels", ("launch.channels",)),
    ("conversation_ai", ("launch.conversation_ai",)),
    ("access_delivery", ("launch.access_delivery",)),
    ("payment_plans", ("launch.payment_plans",)),
    ("sender_name", ("launch.sender_name",)),
    ("reply_to_email", ("launch.reply_to_email",)),
    ("a2p_ready", ("launch.a2p_ready",)),
)

_TRUE_WORDS = {"conversation_ai": ("yes, add the bot",),
               "access_delivery": ("yes, send access after purchase",),
               "payment_plans": ("payment plans offered",),
               "a2p_ready": ("yes, it is approved",)}
_FALSE_WORDS = {"conversation_ai": ("no, not this launch",),
                "access_delivery": ("no, nothing to deliver",),
                "payment_plans": ("paid in full",),
                "a2p_ready": ("no, not yet",)}

_TZ_ALIASES = (
    ("new york", "America/New_York"), ("eastern", "America/New_York"),
    ("los angeles", "America/Los_Angeles"), ("pacific", "America/Los_Angeles"),
    ("chicago", "America/Chicago"), ("central", "America/Chicago"),
    ("denver", "America/Denver"), ("mountain", "America/Denver"),
    ("phoenix", "America/Phoenix"), ("toronto", "America/Toronto"),
    ("london", "Europe/London"), ("berlin", "Europe/Berlin"), ("paris", "Europe/Paris"),
    ("dubai", "Asia/Dubai"), ("singapore", "Asia/Singapore"),
    ("mumbai", "Asia/Kolkata"), ("kolkata", "Asia/Kolkata"),
    ("sydney", "Australia/Sydney"), ("utc", "UTC"), ("gmt", "UTC"),
)
_MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}


def _typed_bool(qid, value):
    """A real boolean from a chosen answer, or None. A non-empty string is never truthy."""
    if isinstance(value, bool):
        return value
    if not isinstance(value, str):
        return None
    n = _norm(value)
    if any(n == w or n.startswith(w) for w in _TRUE_WORDS.get(qid, ())):
        return True
    if any(n == w or n.startswith(w) for w in _FALSE_WORDS.get(qid, ())):
        return False
    if n == "yes" or n.startswith("yes "):
        return True
    if n == "no" or n.startswith("no "):
        return False
    return None


def _typed_channels(value):
    """["email"] or ["email", "text"], or None when the answer says nothing usable."""
    if isinstance(value, str):
        low = value.lower()
        has_text = "text" in low or "sms" in low
        if "email" in low or has_text:
            return ["email", "text"] if has_text else ["email"]
        return None
    if isinstance(value, list):
        out = []
        for item in value:
            low = str(item).strip().lower()
            if low in ("email", "e-mail") and "email" not in out:
                out.append("email")
            elif ("text" in low or "sms" in low) and "text" not in out:
                out.append("text")
        return out or None
    return None


def _find_date(text):
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))), m.span()
        except ValueError:
            return None, None
    for pattern, order in (
            (r"\b(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?\s+(\d{4})", "dmy"),
            (r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})", "mdy")):
        m = re.search(pattern, text, re.I)
        if m:
            g = [x for x in m.groups()]
            month = _MONTHS[g[0][:3].lower()] if order == "mdy" else _MONTHS[g[1][:3].lower()]
            day = int(g[1]) if order == "mdy" else int(g[0])
            try:
                return date(int(g[2]), month, day), m.span()
            except ValueError:
                return None, None
    return None, None


def _find_time(text):
    low = text.lower()
    if re.search(r"\bnoon\b", low):
        return time(12, 0)
    if re.search(r"\bmidnight\b", low):
        return time(0, 0)
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)\b", text, re.I)
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2) or 0)
    pm = m.group(3).lower().startswith("p")
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return None
    if pm and hour != 12:
        hour += 12
    elif not pm and hour == 12:
        hour = 0
    return time(hour, minute)


def _find_timezone(text):
    low = str(text).lower()
    for alias, zone in _TZ_ALIASES:
        if re.search(r"\b" + re.escape(alias) + r"\b", low):
            return zone
    return None


def _iso(day, clock, zone):
    """ISO 8601 for the client's own words. With no zone the wall time is kept and the
    plan names the missing timezone; nothing is guessed."""
    dt = datetime.combine(day, clock)
    if zone:
        try:
            from zoneinfo import ZoneInfo
            dt = dt.replace(tzinfo=ZoneInfo(zone))
        except Exception:  # no tz database: keep the wall time rather than invent an offset
            pass
    return dt.isoformat()


def parse_launch_calendar(text):
    """The client's launch sentence as four typed timestamps. Anything not stated stays
    None; a partial calendar is never filled in from another sentence unless the client
    said only the time (e.g. 'launch at noon' after naming the doors-open day)."""
    out = {"launch_at": None, "doors_open_at": None, "doors_close_at": None, "timezone": None}
    if not isinstance(text, str) or not text.strip():
        return out
    zone = _find_timezone(text)
    out["timezone"] = zone
    parsed = {}
    for clause in re.split(r"[;]", text):
        for piece in re.split(r",", clause):
            low = piece.lower()
            key = None
            if re.search(r"doors?\s+open", low):
                key = "doors_open_at"
            elif re.search(r"doors?\s+close", low):
                key = "doors_close_at"
            elif re.search(r"\blaunch(?:es|ing)?\b", low) and not re.search(r"launch\s+(?:e-?mail)", low):
                key = "launch_at"
            if key is None or key in parsed:
                continue
            day, span = _find_date(piece)
            rest = (piece[:span[0]] + " " + piece[span[1]:]) if span else piece
            clock = _find_time(rest)
            if day and clock:
                parsed[key] = (day, clock)
            elif clock and key == "launch_at":
                parsed[key] = (None, clock)  # resolved from the doors day below
    for key, (day, clock) in parsed.items():
        if day is None:
            day = (parsed.get("doors_open_at") or (None, None))[0] or \
                  (parsed.get("doors_close_at") or (None, None))[0]
        if day:
            out[key] = _iso(day, clock, zone)
    return out


def launch_answers(doc):
    """The eight launch answers as typed ledger entries, keyed by the launch ledger names.

    Each entry is {value, state, source_ref, provenance}; state is the launch intake
    field state (provided / recommended_unapproved / unknown) so a default or a
    suggestion can never be read as an approval."""
    if doc.get("meta", {}).get("mode") == "legacy":
        return {}
    derive_payment_plans(doc)  # the flag is read from billing, never from a question
    out = {}

    def put(qid, key, value):
        e = get(doc, qid)
        if e is None:
            return
        state = _STATE[e["status"]]
        v = value
        if state == "unknown" or v is None:
            state, v = "unknown", None
        out[key] = {"value": v, "state": state, "source_ref": f"answers-file:{qid}",
                    "provenance": {"question_id": qid, "raw": e.get("value"),
                                   "answer_status": e["status"], "answer_source": e.get("source", "")}}

    cal = get(doc, "launch_calendar")
    if cal is not None:
        typed = parse_launch_calendar(cal.get("value"))
        cal_state = _STATE[cal["status"]]
        for key in ("launch.launch_at", "launch.doors_open_at", "launch.doors_close_at", "launch.timezone"):
            put("launch_calendar", key, typed[key.split(".", 1)[1]])
            if cal_state != "provided" and key in out:  # a defaulted calendar is a proposal, not a fact
                out[key]["state"] = cal_state
    put("channels", "launch.channels", _typed_channels((get(doc, "channels") or {}).get("value")))
    for qid, key in (("conversation_ai", "launch.conversation_ai"),
                     ("access_delivery", "launch.access_delivery"),
                     ("payment_plans", "launch.payment_plans"),
                     ("a2p_ready", "launch.a2p_ready")):
        put(qid, key, _typed_bool(qid, (get(doc, qid) or {}).get("value")))
    for qid, key in (("sender_name", "launch.sender_name"), ("reply_to_email", "launch.reply_to_email")):
        e = get(doc, qid)
        if e is not None:
            raw = e.get("value")
            put(qid, key, str(raw).strip() if isinstance(raw, str) and raw.strip() else None)
    # The full launch plan refuses without a usable access destination, so the
    # intake has to be able to produce one. Anything that is not an http(s)
    # address is recorded as unknown rather than passed through.
    e = get(doc, "access_url")
    if e is not None:
        raw = e.get("value")
        url = raw.strip() if isinstance(raw, str) else ""
        put("access_url", "launch.access_url",
            url if url.startswith(("http://", "https://")) else None)
    return out


def to_launch_known(doc):
    """Skill 49 launch_intake `known` entries ({field: {value, state, source_ref}}) from the one answers file.
    A default or suggestion becomes recommended_unapproved, so it can never pass as approved."""
    v = view(doc)
    ent = lambda value, qid: {"value": value, "state": _STATE[doc["answers"][qid]["status"]], "source_ref": f"answers-file:{qid}"}  # noqa: E731
    out = {}
    if "offer_description" in v or "offer_name" in v:
        out["offers.main.description"] = ent({"display_name": v.get("offer_name") or v.get("offer_description"), "description": v.get("offer_description"),
                                              "deliverables": v.get("deliverables", [])}, "offer_name" if "offer_name" in v else "offer_description")
    for field, qid in (("audience", "audience"), ("offers.main.transformation", "offer_transformation"), ("offers.main.pains", "pains"),
                       ("offers.main.deliverables", "deliverables"), ("journey_mode", "funnel_shape"), ("offers.main.price", "price"),
                       ("offers.main.packages", "packages"),
                       ("offers.main.billing_type", "billing"), ("copy_profile", "copy_profile"), ("image_provider", "image_provider")):
        if qid in v:
            out[field] = ent(v[qid], qid)
    if "image_provider" in out:  # the launch record knows kie, agnes and other_explicit only
        out["image_provider"]["value"] = {"connected": "kie", "none": "other_explicit"}.get(v["image_provider"], v["image_provider"])
    out["offers.main.exclusions"] = {"value": [], "state": "not_applicable", "source_ref": "answers-file:exclusions"}
    out["offers.main.schedule"] = {"value": [], "state": "provided", "source_ref": "answers-file:billing"}
    if v.get("interview_mode"):
        out["interview.mode"] = {"value": v["interview_mode"], "state": "provided", "source_ref": "answers-file:interview_mode"}
    if v.get("location") == "existing":
        out["location_binding"] = {"value": {"choice": "existing account", "note": "IDs come from verified access (S06), not recitation"},
                                   "state": "provided", "source_ref": "answers-file:location"}
    if "proof" in v:
        out["proof"] = ent(None if v["proof"] == "none yet" else v["proof"], "proof")
        if v["proof"] == "none yet":
            out["proof"]["state"] = "not_applicable"  # a proof-free narrative; nothing is invented
    ex = {s: v.get(s, "none") not in ("none", None) for s in ("upsell_1", "downsell_1", "upsell_2")}
    if any(s in v for s in ex):
        out["extras"] = {"value": ex, "state": "provided", "source_ref": "answers-file:extras"}
    for slot in ("bump", "upsell_1", "downsell_1", "upsell_2"):
        if slot in v:
            out[f"offers.{slot}"] = ent(None if v[slot] == "none" else (v[slot] if isinstance(v[slot], dict) else {"description": v[slot]}), slot)
            if out[f"offers.{slot}"]["value"] is None:
                out[f"offers.{slot}"]["state"] = "not_applicable"
    if "bump" in v:
        out["bump_enabled"] = {"value": v["bump"] != "none", "state": "provided", "source_ref": "answers-file:bump"}
    if "packages" in v:  # each package carries its own price; there is no single main price to ask for
        for field in ("offers.main.price", "offers.main.billing_type"):
            out[field] = {"value": None, "state": "not_applicable", "source_ref": "answers-file:packages"}
    pra = v.get("paid_render_approval")
    if pra and pra.get("approved"):
        out["paid_asset_budget"] = ent({"cap_minor": pra["cap_minor"], "currency": pra["currency"],
                                        "approval": "separate paid_asset_budget approval required"}, "paid_render_approval")
    elif pra:  # no paid pieces, or decide later: nothing paid is approved
        out["paid_asset_budget"] = {"value": None, "state": "not_applicable", "source_ref": "answers-file:paid_render_approval"}
    out.update(launch_answers(doc))  # typed, with provenance; unknown and unapproved survive
    return out


def image_inputs(doc):
    """The C3 image inputs these answers decide (the lanes add brand_file and refs)."""
    v = view(doc)
    pra = v.get("paid_render_approval") or {}
    approved = bool(pra.get("approved"))
    # the money and the Command Center approval id go to image_plan.resolve as paid_render_approval_ref (+ cap and
    # currency); 83 verifies the record itself. "No paid pieces" / "Decide later" carry no ref and allow nothing paid,
    # and a free-text yes is never an approval ref.
    ref = pra.get("approval_id") if approved and isinstance(pra.get("approval_id"), str) and pra["approval_id"].strip() else None
    return {"design_style": v.get("design_style"), "image_cap": v.get("image_cap"), "image_provider": v.get("image_provider"),
            "paid_render_approved": approved, "page_set": v.get("page_set"),
            "paid_render_approval_ref": ref,
            "image_cap_minor": pra.get("cap_minor") if ref else None,
            "image_currency": pra.get("currency") if ref else None,
            "allow_paid": ref is not None}


# ---------------------------------------------------------------- which run mode is this
# An explicit COMPLETE Black Friday / launch request routes into the signature launch. An
# explicit request for the older step-by-step funnel keeps legacy. Nothing here guesses: an
# ambiguous opening is asked about with one plain question, never routed by default.
MODE_ROUTING = {
    "launch": {
        "phrases": ("black friday", "black friday launch", "signature launch", "signature funnel",
                    "launch my", "launch this", "launch the", "run a launch", "bfcm", "cyber monday",
                    "holiday promotion", "seasonal promotion"),
        "reason": "You asked for a launch, so this runs the signature launch interview.",
    },
    "legacy": {
        "phrases": ("legacy", "legacy mode", "old step-by-step", "old step by step", "step-by-step funnel",
                    "step by step funnel", "3-step funnel", "5-step funnel", "7-step funnel",
                    "the older funnel", "classic funnel"),
        "reason": "You asked for the older step-by-step funnel, so this keeps legacy mode.",
    },
}
ROUTE_QUESTION = ("Is this a Black Friday or launch promotion, or do you want the older step-by-step "
                  "funnel? Reply launch or legacy.")


def _routing_table():
    """The bank's own routing table when it carries one, else the default above."""
    table = load_bank().get("mode_routing")
    return table if isinstance(table, dict) and table else MODE_ROUTING


def route_mode(text, bank=None):
    """('launch'|'legacy'|None, reason) for what the client actually asked for.

    A deliberate legacy request is preserved; an explicit launch request becomes the signature
    launch. Both markers present is ambiguous and is asked, never silently resolved."""
    t = " " + _norm(text) + " "
    if not t.strip():
        return None, ROUTE_QUESTION
    table = (bank or {}).get("mode_routing") if isinstance(bank, dict) else None
    table = table if isinstance(table, dict) and table else _routing_table()
    hits = []
    for mode in ("launch", "legacy"):
        block = table.get(mode) or {}
        for phrase in block.get("phrases") or MODE_ROUTING[mode]["phrases"]:
            if " " + _norm(phrase) + " " in t:
                hits.append((mode, block.get("reason") or MODE_ROUTING[mode]["reason"]))
                break
    if len(hits) == 1:
        return hits[0]
    if not hits:
        return None, ROUTE_QUESTION
    return None, ("I heard both a launch and the older step-by-step funnel. Which one should I set up? "
                  "Reply launch or legacy.")


def apply_mode(doc, text, *, asked=False):
    """Stamp the routed mode on the doc. `asked=True` means the client named the mode, so the
    reason is kept. A doc already carrying a client-set mode is never overwritten by a guess."""
    mode, reason = route_mode(text)
    if mode is None:
        return {"ok": False, "action": "ask_mode", "question": reason}
    doc.setdefault("meta", {})["mode"] = mode
    doc["meta"]["mode_source"] = "explicit_request" if asked or mode else "routing"
    doc["meta"]["mode_reason"] = reason
    return {"ok": True, "mode": mode, "reason": reason}


# ---------------------------------------------------------------- answer provenance
# Every saved answer says what it IS, so a proposal can never read as a promise and a generated
# file can never read as a confirmed fact.
PROVENANCE_CLASSES = ("confirmed_fact", "ai_proposal", "user_selected_recommendation",
                      "generated_asset", "unresolved_capability")


def provenance_of(entry):
    """The class of one saved answer, or None when nothing is saved."""
    if not isinstance(entry, dict):
        return None
    if entry.get("generated"):
        return "generated_asset"
    if entry.get("unresolved_capability") or entry.get("status") == "unknown":
        return "unresolved_capability"
    if entry.get("status") in ("suggested", "default_to_confirm"):
        return "ai_proposal"
    source = str(entry.get("source") or "")
    if entry.get("accepted_proposal") or source.startswith(("recommendation", "feel-words", "palette-help")):
        return "user_selected_recommendation"
    return "confirmed_fact"


def proposed_action(qid, answer=None, *, artifact=None, why="", capability=None):
    """One proposed artifact or action for an answer the client has not given yet.

    Stored on the launch record (`proposals`) beside the answers, so a missing answer becomes a
    reviewable proposal instead of a dead end. `capability` names the limit when the proposal
    needs something the run cannot do, and stays unresolved rather than pretending."""
    return {"question_id": qid, "artifact": artifact, "action": answer, "why": why,
            "state": "proposed", "provenance": "ai_proposal",
            "capability": capability,
            "unresolved": bool(capability)}


def propose(doc, qid, *, artifact=None, action=None, why="", capability=None):
    """Record a proposal on the launch record. Never an answer: the client still accepts it."""
    doc.setdefault("proposals", {})[qid] = proposed_action(
        qid, action, artifact=artifact, why=why, capability=capability)
    return {"ok": True, "action": "proposal", "id": qid, **doc["proposals"][qid]}


def proposals(doc):
    """Every open proposal, keyed by question id, each carrying its provenance class."""
    return {k: dict(v, provenance="ai_proposal") for k, v in (doc.get("proposals") or {}).items()
            if isinstance(v, dict) and v.get("state") == "proposed"}


def accept_proposal(doc, qid, *, accepted_by="client", note=None):
    """THE one proposal-acceptance transition, used by Skill 49 and Skill 83 alike.

    Accepting turns the stored proposal into the answer, marked user_selected_recommendation and
    leaving the artifact provenance intact. A proposal that needs a capability the run does not
    have cannot be accepted into a confirmed fact: it stays unresolved, by name."""
    p = (doc.get("proposals") or {}).get(qid)
    if not isinstance(p, dict) or p.get("state") != "proposed":
        return _refused("no_open_proposal", f"No open proposal is recorded for {qid}.")
    if p.get("unresolved"):
        entry = _set(doc, qid, p.get("action"), "unknown", f"proposal-accepted:{accepted_by}", note)
        entry["accepted_proposal"] = True
        entry["unresolved_capability"] = p.get("capability")
        p["state"] = "accepted_unresolved"
        _sync_to_confirm(doc)
        return {"ok": True, "id": qid, "provenance": "unresolved_capability",
                "capability": p.get("capability"), "entry": entry,
                "message": f"Recorded, but {p.get('capability')} is not available in this run, so it stays open."}
    entry = _set(doc, qid, p.get("action"), "provided", f"proposal-accepted:{accepted_by}", note)
    entry["accepted_proposal"] = True
    entry["proposal_artifact"] = p.get("artifact")
    p["state"] = "accepted"
    autofill_roles(doc)
    derive_payment_plans(doc)
    _sync_to_confirm(doc)
    return {"ok": True, "id": qid, "provenance": "user_selected_recommendation", "entry": entry}


# ---------------------------------------------------------------- revision
# A change is reconciled, never re-interviewed: only the answers, approvals and artifacts the
# change actually touches are reopened. Brand and context answers are never collateral.
REVISION_DEPENDENTS = {
    "upsell_1": ("downsell_1", "upsell_2"),   # no U1 means no D1 and no U2 route
    "funnel_shape": ("price", "packages"),
    "brand_colors": ("brand_primary", "brand_secondary", "brand_accent", "brand_background", "brand_text"),
    "price": ("billing",),
    "logo": ("logo_create",),
}
APPROVAL_ANSWERS = ("plan_approval",)


def reconcile_revision(doc, changed):
    """Reconcile a revision. `changed` is {question_id: new_value} for what the client changed.

    Reopens only the dependent answers, drops the approvals tied to the changed plan, and leaves
    every unrelated answer untouched. Returns what moved so the caller can re-plan exactly that."""
    reopened, invalidated, kept = [], [], []
    for qid in changed:
        for dep in REVISION_DEPENDENTS.get(qid, ()):
            if get(doc, dep) is not None:
                _set(doc, dep, None, "unknown", f"reopened-by:{qid}", keep_count=False)
                reopened.append(dep)
        for approval in APPROVAL_ANSWERS:
            e = get(doc, approval)
            if e is not None and e["status"] != "unknown":
                _set(doc, approval, None, "unknown", f"reopened-by:{qid}", keep_count=False)
                invalidated.append(approval)
            doc.get("meta", {}).pop("route_graph_ref", None)
            doc.get("meta", {}).pop("route_graph_hash", None)
    touched = set(changed) | set(reopened) | set(invalidated)
    for qid, e in doc["answers"].items():
        if qid not in touched and e.get("status") != "unknown":
            kept.append(qid)
    for qid in changed:
        doc.get("proposals", {}).pop(qid, None)
    _sync_to_confirm(doc)
    return {"ok": True, "changed": sorted(changed), "reopened": sorted(set(reopened)),
            "invalidated": sorted(set(invalidated)), "kept": sorted(kept),
            "next_question": (next_question(doc) or {}).get("id")}


# ---------------------------------------------------------------- billing terms, never flattened
BILLING_TERMS_FIELDS = ("amount_minor", "currency", "interval", "interval_count", "installment_count",
                        "trial", "upfront_minor", "total_commitment_minor")
_INTERVAL_WORDS = (("month", "month"), ("week", "week"), ("year", "year"), ("quarter", "quarter"))
_UNSUPPORTED_BILLING = ("recurring", "installment")
BILLING_ALTERNATIVE = "one paid amount at checkout"
BILLING_LIMIT = ("this release's checkout takes one paid amount per purchase, so it cannot charge a "
                 "repeating or split payment")


def billing_terms(doc):
    """The complete billing terms for the offer, or None when billing is unanswered.

    amount/currency come from the price or the cheapest package; interval, count, trial, upfront and
    total commitment come from the client's own detail answer. A term the client did not give stays
    None: a plan is never flattened into one-time and never invented."""
    b = get(doc, "billing")
    key = _billing_key(b["value"]) if b is not None and b["status"] != "unknown" else None
    if key is None:
        return None
    price = val(doc, "price")
    if not isinstance(price, dict) and val(doc, "packages"):
        price = min((p.get("price") for p in val(doc, "packages") if isinstance(p.get("price"), dict)),
                    key=lambda x: x["amount_minor"], default=None)
    detail = val(doc, "billing_detail") or {}
    terms = {f: None for f in BILLING_TERMS_FIELDS}
    if isinstance(price, dict):
        terms["amount_minor"], terms["currency"] = price.get("amount_minor"), price.get("currency")
    if key == "recurring":
        terms["interval"] = detail.get("interval") or "month"
        terms["interval_count"] = detail.get("interval_count") or 1
    elif key == "installment":
        terms["installment_count"] = detail.get("installment_count")
        terms["upfront_minor"] = detail.get("upfront_minor")
        terms["trial"] = detail.get("trial")
    if terms["amount_minor"] is not None:
        n = terms["installment_count"] or terms["interval_count"] or 1
        terms["total_commitment_minor"] = terms["amount_minor"] * (n if key != "one_time" else 1)
    e = get(doc, "billing")
    return dict(terms, billing_type=key, source_ref="answers-file:billing",
                state=_STATE.get(e["status"], "unknown") if e else "unknown")


def billing_supported(doc):
    """Whether the selected execution path can bill this plan, and when it cannot, the specific limit
    plus ONE supported alternative. The request itself stays unresolved until the alternative is
    accepted, so nothing is silently flattened into a one-time payment."""
    terms = billing_terms(doc)
    if terms is None:
        return {"supported": True, "billing_type": None, "limit": None, "alternative": None,
                "unresolved": False}
    key = terms["billing_type"]
    if key in _UNSUPPORTED_BILLING:
        return {"supported": False, "billing_type": key, "requested": terms,
                "limit": BILLING_LIMIT, "alternative": BILLING_ALTERNATIVE,
                "unresolved": True,
                "message": (f"Your {key.replace('installment', 'split-payment')} plan needs billing this "
                            f"release does not have: {BILLING_LIMIT}. The one plan I can build is "
                            f"{BILLING_ALTERNATIVE}. I have kept your request as it is until you choose.")}
    return {"supported": True, "billing_type": key, "terms": terms, "limit": None,
            "alternative": None, "unresolved": False}


# ---------------------------------------------------------------- extra-offer prose
_OFFER_PRICE_RE = re.compile(r"[$€£]\s*\d[\d,]*(?:\.\d{1,2})?|\b(?:USD|EUR|GBP)\s*\d[\d,]*(?:\.\d{1,2})?|\b\d[\d,]*\s*(?:USD|EUR|GBP)\b", re.I)


# How a buyer receives the offer, and whether it exists yet: read only from the client's own words.
# No hint means the fact is missing, and missing stays missing.
_DELIVERY_HINTS = (
    ("generated", ("pdf", "template", "download", "video", "recordings", "checklist", "guide", "workbook", "file")),
    ("human_service", ("call", "session", "coaching", "done-for-you", "done for you", "1:1", "live", "consultation", "review", "service")),
    ("physical", ("ship", "shipped", "printed", "book", "kit")),
)
_PRODUCTION_HINTS = (
    ("ready_now", ("ready", "already", "have it", "exists")),
    ("being_made", ("being made", "in progress", "building", "half done")),
    ("needs_creation", ("create", "make it", "record it", "write it", "new", "not yet")),
)


def _first_hint(low, hints):
    for value, words in hints:
        if any(w in low for w in words):
            return value
    return None


def normalize_offer_prose(text, *, qid=None):
    """Ordinary extra-offer prose -> the existing structured offer record, keeping the source text.

    Name, deliverables and price are read from what the client wrote; a part they did not give stays
    missing, never invented. The prose is preserved verbatim under source_text so nothing is lost."""
    raw = str(text or "").strip()
    out = {"display_name": None, "deliverables": [], "price": None,
           "source_text": raw, "source_ref": (f"answers-file:{qid}" if qid else None),
           "missing": []}
    if not raw:
        out["missing"] = ["whole offer"]
        return out
    money = _OFFER_PRICE_RE.search(raw)
    if money:
        parsed = _money(money.group(0))
        if parsed:
            out["price"] = parsed
    head = _OFFER_PRICE_RE.sub(" ", raw).strip(" ,;.-")
    name = re.split(r"\s*(?:\||:|\s-\s|\(|,)\s*", head, maxsplit=1)[0].strip()
    out["display_name"] = name or None
    tail = head[len(name):].strip(" ,;.-|:") if name else head
    items = [x.strip() for x in re.split(r";|\n|,", tail) if x.strip()]
    out["deliverables"] = items
    if not out["display_name"]:
        out["missing"].append("name")
    if not out["price"]:
        out["missing"].append("price")
    if not out["deliverables"]:
        out["missing"].append("what the buyer gets")
    low = " " + _norm(raw) + " "
    # delivery method and production status are read from the same words; no hint leaves them absent
    out["delivery_kind"] = _first_hint(low, _DELIVERY_HINTS)
    out["production_status"] = _first_hint(low, _PRODUCTION_HINTS)
    return out


OFFER_RECORD_FIELDS = ("offer_id", "product_id", "product_role", "display_name", "audience_problem",
                       "promised_result", "deliverables", "price", "billing_type", "delivery_kind",
                       "production_status", "native_product_id", "native_price_id", "pages", "source_text")


def offer_record(doc, qid, *, role=None, product_role=None):
    """One real offer, as the launch model records it: a role SEPARATE from the product identity,
    the audience problem it solves, the result it promises, what the buyer gets, its price and
    payment choice, how it is delivered, whether it exists yet, its native ids when known, and the
    pages that use it. A fact the client did not give stays None; nothing is invented."""
    e = get(doc, qid)
    if e is None or e["status"] == "unknown" or e["value"] in (None, "none"):
        return None
    v = e["value"]
    v = v if isinstance(v, dict) else normalize_offer_prose(v, qid=qid)
    name = v.get("display_name")
    price = v.get("price")
    if qid == "price":  # the price question answers the price; the offer's identity is its own answer
        name, price = val(doc, "offer_name") or name, v if "amount_minor" in v else price
    billing = _billing_key((get(doc, "billing") or {}).get("value"))
    main = qid in ("price", "packages", "offer_name")
    return {
        "offer_id": (qid if qid != "price" else "MAIN").upper().replace("_", "-"),
        "product_id": _slug_name(name) if name else None,
        "product_role": product_role or _ROLE_OF_QUESTION.get(qid) or (
            _TIER_IN_SHAPE.get(val(doc, "funnel_shape") or "", None) if qid == "price" else None),
        "role": role or OFFER_ROLE_OF.get(qid, "main"),
        "display_name": name,
        # the main offer's problem and result are already answered; an extra offer keeps its own when
        # the client stated them on the offer, and stays None when they did not
        "audience_problem": (val(doc, "pains") or None) if main else v.get("audience_problem"),
        "promised_result": (val(doc, "offer_transformation") if main else v.get("promised_result")),
        "deliverables": v.get("deliverables") or [],
        "price": price,
        "billing_type": billing,
        "delivery_kind": v.get("delivery_kind"),
        "production_status": v.get("production_status"),
        "native_product_id": (v.get("checkout") or {}).get("native_product_id"),
        "native_price_id": (v.get("checkout") or {}).get("native_price_id"),
        "pages": _pages_for(doc, OFFER_ROLE_OF.get(qid, "main")),
        "source_text": v.get("source_text"),
    }


# a question id -> the page-level role it plays, and the product identity it names
OFFER_ROLE_OF = {"price": "main", "packages": "main", "bump": "bump", "upsell_1": "upsell_1",
                 "downsell_1": "downsell_1", "upsell_2": "upsell_2", "lead_magnet": "free_entry"}
_ROLE_OF_QUESTION = {"lead_magnet": "free_lead", "bump": "bump", "upsell_1": "upsell_1",
                     "downsell_1": "downsell_1", "upsell_2": "upsell_2"}
_TIER_IN_SHAPE = {"single_simple": "mid"}


def _slug_name(name):
    return re.sub(r"[^A-Za-z0-9]+", "-", str(name or "")).strip("-").upper() or None


def _pages_for(doc, role):
    """The pages that actually use this offer, from the existing page set. Never every page."""
    pages = ["sales", "checkout"]
    if role == "free_entry":
        return ["opt_in", "thank_you"]
    if role == "main" and (val(doc, "funnel_shape") == "multiple_options"):
        pages.insert(1, "product_selection")
    if role in ("upsell_1", "downsell_1", "upsell_2"):
        pages = ["sales", "checkout"]
    pages.append("thank_you")
    return pages


# ---------------------------------------------------------------- one approved brand record
LOGO_VARIANTS = ("existing_file", "wordmark", "created")
# The existing graphics capability the launch already uses for its pictures: Skill 66 (kie-image)
# draws, and Skill 83's graphics hooks carry the QC and delivery record. Nothing new is invented.
GRAPHICS_CAPABILITY = {"name": "kie-image", "skill": 66, "produces": "logo",
                       "qc": "83:launcher_core.graphics_hooks", "blocking": False}


def _logo_variant(doc):
    e = get(doc, "logo")
    v = e["value"] if e and e["status"] != "unknown" else None
    if e is None or e["status"] == "unknown":
        return {"kind": None, "state": "unknown"}
    if isinstance(v, dict):
        mode = v.get("mode")
        if mode == "create" or v.get("create"):
            return {"kind": "created", "state": "pending_assets", "brief": v.get("brief"),
                    "provenance": provenance_of(e)}
        if mode == "wordmark":
            return {"kind": "wordmark", "text": v.get("text") or val(doc, "business_name"),
                    "state": "provided", "provenance": provenance_of(e)}
        return {"kind": "existing_file", "path": v.get("path"), "state": "provided",
                "provenance": provenance_of(e)}
    return {"kind": "existing_file", "path": str(v), "state": "provided", "provenance": provenance_of(e)}


def logo_brief(doc):
    """The brief handed to the existing graphics capability when the client asks for a new logo.

    Built only from facts the client gave; the run continues with offer and copy work while the
    asset is made, so this is never a blocking gate."""
    name = val(doc, "business_name")
    r = roles(doc)
    # no colours yet: the brief carries the small coherent palette we recommend, as a proposal
    palette = (r or {}).get("roles")
    if not palette:
        rec = recommended_palette(doc, val(doc, "voice") or "")
        palette = (rec or {}).get("proposal", {}).get("roles")
    return {"schema": "logo-brief/v1",
            "business_name": name,
            "wordmark_text": name,
            "palette": palette,
            "voice": val(doc, "voice"),
            "design_style": val(doc, "design_style"),
            "image_direction": val(doc, "visual_direction"),
            "usage": ["site_header", "checkout", "email_header", "social_avatar"],
            "must_not": ["redraw a logo the client already has", "invent a trademark or registration"],
            "capability": GRAPHICS_CAPABILITY}


def brand_record(doc):
    """ONE approved brand record every page reads: logo variants, colour roles, typography, image
    direction and voice, each carrying its provenance class.

    Assets that are still being made are `pending_assets` and never block the offer or copy work."""
    r = roles(doc)
    logo = _logo_variant(doc)
    jobs = []
    if logo["kind"] == "created":
        brief = logo.get("brief") or logo_brief(doc)
        jobs.append({"asset": "logo", "capability": GRAPHICS_CAPABILITY,
                     "brief": brief, "blocking": False, "state": "queued"})
    typo = val(doc, "fonts") or {}
    voice = val(doc, "voice")
    direction = {"design_style": val(doc, "design_style"),
                 "creative_direction": val(doc, "visual_direction")}
    statuses = [provenance_of(get(doc, q)) for q in ("logo", "brand_colors", "fonts", "design_style", "voice")]
    if logo["kind"] == "created" or "pending_assets" in (logo.get("state"),):
        # the logo is being made: one record, not yet final, and it never blocks offer or copy work
        status = "pending_assets"
    elif logo["kind"] is None or not r:
        status = "pending"
    elif "unresolved_capability" in statuses:
        status = "pending_assets"
    elif "ai_proposal" in statuses:
        status = "proposed"
    else:
        status = "approved"
    return {"schema": "brand-record/v1", "status": status,
            "logo_variants": [logo],
            "colors": {"roles": (r or {}).get("roles"), "status": (r or {}).get("status"),
                       "warnings": (r or {}).get("warnings", [])},
            "typography": {"value": typo, "provenance": provenance_of(get(doc, "fonts"))},
            "image_direction": direction,
            "voice": {"value": voice, "provenance": provenance_of(get(doc, "voice"))},
            "asset_jobs": jobs,
            "work_independent": {"offers": True, "copy": True, "assets": status != "approved"},
            "blocks_offer_work": False}


def asset_map(doc):
    """Every page reads this one map for its files. A slot that is still being made says so."""
    out = {}
    logo = _logo_variant(doc)
    out["logo"] = {"state": "pending_assets" if logo["kind"] == "created" else logo.get("state"),
                   "variant": logo["kind"], "path": logo.get("path"),
                   "brief": logo.get("brief") if logo["kind"] == "created" else None}
    photos = val(doc, "photos_founder")
    out["founder_photo"] = {"state": "provided" if isinstance(photos, str) and photos.startswith("yes") else "empty_frame",
                            "path": None}
    return {"schema": "asset-map/v1", "slots": out, "source": "brand_record"}


def recommended_palette(doc, mood=""):
    """A small coherent palette when the client has no colours yet, as a proposal, never a fact."""
    seed = (_colors(doc) or [None])[0]
    pals = ph.suggest_palettes(seed, mood or "")
    if not pals:
        return None
    best = pals[0]
    return {"proposal": best, "provenance": "ai_proposal", "alternatives": pals[1:],
            "message": "I suggest this small palette; say yes to use it, or send your own colours."}


# ---------------------------------------------------------------- CLI
def _flag(a, name):
    return a[a.index(name) + 1] if name in a else None


def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    if len(a) < 2:
        print(__doc__)
        return 2
    path, cmd = a[0], a[1]
    doc = load(path, _flag(a, "--mode") or "launch")
    if _flag(a, "--mode"):
        doc["meta"]["mode"] = _flag(a, "--mode")
    pk = _flag(a, "--page-kind")
    if pk:
        if pk not in ("sales", "opt_in"):
            print("--page-kind must be sales or opt_in", file=sys.stderr)
            return 2
        doc["meta"]["page_kind"] = pk
    if _flag(a, "--harness"):
        doc["harness"] = _flag(a, "--harness")
    if cmd == "next":
        q = next_question(doc)
        print(json.dumps(q, indent=2) if q else json.dumps({"done": True, "check": check(doc)}, indent=2))
    elif cmd == "record" and len(a) >= 4:
        print(json.dumps(record(doc, a[2], a[3], source_message_ref=_flag(a, "--ref")), indent=2))
    elif cmd == "help" and len(a) >= 3:
        print(json.dumps(resolve_unknown(doc, a[2], logo=_flag(a, "--logo"), website=_flag(a, "--site"), palette=_flag(a, "--palette"), mood=_flag(a, "--mood")), indent=2))
    elif cmd == "check":
        print(json.dumps(check(doc), indent=2))
    elif cmd == "finalize":
        print(json.dumps(finalize(doc), indent=2))
    elif cmd == "report":
        for t in check(doc)["to_confirm"]:
            print(f"TO CONFIRM  {t['id']}: {t['value']}\n    {t['reason']}\n    {t['how_to_change']}")
    elif cmd == "show":
        print(json.dumps(view(doc), indent=2))
    elif cmd == "route" and len(a) >= 3:
        print(json.dumps(apply_mode(doc, " ".join(a[2:]), asked=True), indent=2))
    elif cmd == "propose" and len(a) >= 3:
        print(json.dumps(propose(doc, a[2], action=(a[3] if len(a) > 3 else None)), indent=2))
    elif cmd == "accept" and len(a) >= 3:
        print(json.dumps(accept_proposal(doc, a[2]), indent=2))
    elif cmd == "reconcile" and len(a) >= 3:
        print(json.dumps(reconcile_revision(doc, {a[2]: (a[3] if len(a) > 3 else None)}), indent=2))
    elif cmd == "brand-record":
        print(json.dumps({"brand": brand_record(doc), "assets": asset_map(doc)}, indent=2))
    elif cmd == "billing":
        print(json.dumps({"terms": billing_terms(doc), "supported": billing_supported(doc)}, indent=2))
    elif cmd == "proposals":
        print(json.dumps(proposals(doc), indent=2))
    else:
        print(__doc__)
        return 2
    save(doc, path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
