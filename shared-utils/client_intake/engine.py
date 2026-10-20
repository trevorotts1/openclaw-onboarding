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

CLI:  engine.py FILE next | record ID VALUE | help ID [--logo F --site URL --palette N --mood "..."] |
      check | finalize | report | show      (FILE is created on first use; --mode launch|legacy|bf)
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import palette_help as ph  # noqa: E402

BANK_PATH = Path(__file__).with_name("question-bank.json")
STATUSES = ("provided", "suggested", "default_to_confirm", "unknown")
HELP_WORDS = {"help", "help me", "not sure", "not sure yet", "im not sure", "i am not sure", "i dont know", "idk",
              "unsure", "i have no idea", "no idea", "dont know", "im not sure, help me", "im not sure help me", "no clue"}
SENTINEL = "CLIENT_MUST_SUPPLY"  # the Skill 71 brand-file marker for "not supplied yet"
ROLE_ORDER = ("primary", "secondary", "accent", "background", "text")
_BANK = None


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
def new_doc(mode="launch", harness=None, run_id=None):
    doc = {"schema": "client-intake-answers/v1", "meta": {"mode": mode, "phase": "pre_build"}, "answers": {}, "to_confirm": []}
    if harness:
        doc["harness"] = harness
    if run_id:
        doc["run_id"] = run_id
    return doc


def load(path, mode="launch"):
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else new_doc(mode)


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
    sts = [get(doc, f"brand_{k}")["status"] for k in ROLE_ORDER if get(doc, f"brand_{k}")]
    status = "default_to_confirm" if "default_to_confirm" in sts else "provided"
    return {"roles": out, "status": status, "warnings": ph.check_palette(out)}


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
    m = re.fullmatch(r"(\w+) (==|!=) (\w+)", cond)
    if m:
        t = _token(doc, m.group(1))
        return t is not None and ((t == m.group(3)) == (m.group(2) == "=="))
    m = re.fullmatch(r"(\w+) answered", cond)
    if m:
        return get(doc, m.group(1)) is not None and get(doc, m.group(1))["status"] != "unknown"
    m = re.fullmatch(r"needs_role (\w+)", cond)
    if m:
        return needs_role(doc, m.group(1))
    raise ValueError(f"unknown condition {cond!r}")


def applicable(doc, bank=None):
    autofill_roles(doc)
    return [q for q in (bank or load_bank())["questions"] if cond_met(doc, q["condition"])]


# ---------------------------------------------------------------- asking
def hydrate(doc, q):
    """The question exactly as a client should see it (text filled in, dynamic choices resolved)."""
    q = json.loads(json.dumps(q))
    if q.get("dynamic") == "colors":
        role = q["id"].split("_", 1)[1]
        pool = _colors(doc) if role == "primary" else _remaining(doc)
        q["text"] = q["text"].replace("{colors}", "(" + ", ".join(pool) + ")")
        q["choices"] = (pool + (["None"] if role == "accent" else []))[:3]
    if q["id"] == "design_style":
        q["help"]["examples"] = q["help"]["examples"] + _style_links()
    return q


def _style_links():
    for base in Path(__file__).resolve().parents:
        f = base / "71-blackceo-signature-page" / "references" / "design-styles.json"
        if f.is_file():
            try:
                return [f"{s['id']} {s['name']} example: {s['example']['url']}" for s in json.loads(f.read_text())["styles"] if s["example"].get("url")]
            except (OSError, ValueError, KeyError):
                return []
    return []


def _askable(doc, q):
    e = get(doc, q["id"])
    if e is None:
        return True
    if e["status"] != "unknown":
        return False
    return not (q["never_default"] and e.get("unknown_count", 0) >= 2)  # keep moving; check() names the blocker


def next_question(doc, bank=None):
    todo = [q for q in applicable(doc, bank) if _askable(doc, q)]
    if not todo:
        return None
    todo.sort(key=lambda q: not q["condition"].startswith("needs_role"))  # color-role follow-ups come right after the colors
    total = len(applicable(doc, bank))
    h = hydrate(doc, todo[0])
    h["help_label"] = (bank or load_bank())["help_label"]
    h["progress"] = {"answered": total - len(todo), "of": total}
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
    """True when the client says they do not know. 'Help me choose' is a real choice only for interview_mode."""
    if not isinstance(value, str):
        return False
    n = _norm(value).replace("'", "")
    if q["id"] == "interview_mode" and _pick(value, q["choices"]):
        return False
    return n in HELP_WORDS or n.startswith("help me") or any("not sure" in _norm(c) and _norm(c) == n for c in q["choices"])


def _money(text):
    t = str(text).replace(",", "")
    m = re.search(r"(\d+(?:\.\d{1,2})?)", t)
    if not m:
        return None
    cur = "USD"
    for sym, c in (("€", "EUR"), ("£", "GBP"), ("eur", "EUR"), ("gbp", "GBP")):
        if sym in t.lower():
            cur = c
    return {"amount_minor": round(float(m.group(1)) * 100), "currency": cur}


def _pick(text, choices):
    n = _norm(text)
    for c in choices:
        if _norm(c) == n:
            return c
    for c in choices:
        if n and (n.startswith(_norm(c)) or _norm(c).startswith(n)):
            return c
    return None


def _need(msg):
    return {"ok": False, "message": msg}


def _normalize(doc, q, raw):
    """(value, status, note) or a _need() dict. Free text always wins over the listed choices."""
    qid, t, ch = q["id"], q["answer_type"], q["choices"]
    text = str(raw).strip() if not isinstance(raw, (dict, list)) else raw
    low = _norm(text) if isinstance(text, str) else ""
    pick = _pick(text, ch) if isinstance(text, str) else None
    if qid == "interview_mode":
        return ({"i know what i want": "know", "help me choose": "help", "set it up for me to review": "choose_for_me"}.get(_norm(pick or text), "help"), "provided", None)
    if qid == "design_style":
        m = re.match(r"^\(?([abc])\b", low) or re.search(r"\b(block|circle|hybrid)\b", low)
        if not m:
            return _need("Please answer A, B or C, or say 'help' and tell me three words for how you want your brand to feel.")
        k = m.group(1)
        return ({"block": "A", "circle": "B", "hybrid": "C"}.get(k, k.upper()), "provided", None)
    if qid == "funnel_shape":
        if pick and pick.startswith("Levels") or "level" in low:
            return "folded_levels", "provided", None
        if pick == "A few packages" or "package" in low or "multiple" in low:
            return "multiple_options", "provided", None
        if pick == "One offer" or "single" in low or low in ("one", "one offer"):
            return "single_simple", "provided", None
        if text in ("single_simple", "multiple_options", "folded_levels"):
            return text, "provided", None
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
        if pick == "Use my business name as text" or "text" in low and "name" in low:
            return {"mode": "wordmark", "text": val(doc, "business_name")}, "provided", None
        if pick == "I will send it" or low in ("yes", "i will send it"):
            return _need("Please send the logo file (PNG or SVG), or say 'use my business name as text'.")
        return {"mode": "file", "path": str(text)}, "provided", None
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
        if pick == "It is free" or low in ("free", "it is free", "0"):
            return {"amount_minor": 0, "currency": "USD"}, "provided", None
        if isinstance(text, dict):
            if text.get("rationale"):  # a suggestion with its reasoning stays a proposal
                return text, "suggested", "Suggested price; it needs your approval."
            return text, "provided", None
        m = _money(text)
        if m and pick != "Suggest one for me to review":
            return m, "provided", None
        if pick == "Suggest one for me to review" or "suggest" in low:
            return _need("Tell me what it includes and roughly who buys it. I will suggest a range with my reasoning for you to approve.")
        return _need("What price should I use? A number like 497 is fine.")
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
        return str(text), "provided", None
    if qid == "image_provider":
        n = {"My connected service": "connected", "Recommend one": "kie", "No images needed": "none"}.get(pick or "")
        n = n or (low if low in ("kie", "agnes", "none", "connected") else None)
        return ((n, "suggested" if pick == "Recommend one" else "provided", None) if n else _need("Which image service: your connected one, one I recommend, or none?"))
    if qid == "image_cap":
        if low in ("no pictures", "none", "0"):
            return 0, "provided", None
        m = re.search(r"\d+", low)
        return (int(m.group(0)), "provided", None) if m else _need("A number please, like 12.")
    if qid == "copy_profile":
        return (("long_form" if "long" in low else "standard"), "provided", None) if (pick or "standard" in low or "long" in low) else _need("Standard or long-form?")
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
        pk = []
        for row in rows:
            if isinstance(row, dict):
                pk.append(row)
                continue
            sym = re.findall(r"[\$€£]\s*\d[\d,]*(?:\.\d+)?", row)
            m = _money(sym[-1]) if sym else _money(row.split("|")[-1]) if "|" in row else None
            name = re.split(r"\s*(?:\||:|\s-\s|\(|\$|€|£)\s*", row.strip(" -*\u2022"), maxsplit=1)[0].strip()
            rest = [x.strip() for x in re.split(r"\|", row)[1:] if x.strip() and not re.fullmatch(r"[\$€£]?\s*[\d,.]+(\s*(usd|eur|gbp))?", x.strip(), re.I)]
            inc = [i.strip() for r in rest for i in re.split(r";", r) if i.strip()]
            if name and m:
                pk.append({"display_name": name, "deliverables": inc, "price": m})
        if len(pk) < 2 or any(not (p.get("display_name") and isinstance(p.get("price"), dict)) for p in pk):
            return _need("I need at least two, each with a name and a price, one per line. For example: Premium | 12 lessons; 4 live calls | $497")
        return pk, "provided", None
    if t == "list":
        items = text if isinstance(text, list) else [s.strip(" -*•") for s in re.split(r"\n|;|,(?=\s)", text) if s.strip(" -*•")]
        return (items, "provided", None) if items else _need("Please give me at least one.")
    if q["required"] == "optional" and isinstance(text, str) and not text.strip():
        return None, "provided", "left blank on purpose"
    if not text or (isinstance(text, str) and not text.strip()):
        return _need("Please give me an answer, or say 'help'.")
    return text, "provided", None


def record(doc, qid, value, *, source="client", status=None, note=None):
    """Store an answer. Returns {"ok": True, ...}; {"ok": False, "message"} when the answer is incomplete;
    or the help payload when the client said they do not know."""
    q = question(qid)
    if wants_help(q, value):
        return resolve_unknown(doc, qid)
    if qid in ("brand_colors", "design_style") and isinstance(value, str):
        reply = _help_reply(doc, q, value)  # a reply to the help message: logo, website, 1-3, "yes", feel words
        if reply is not None:
            return reply
    out = _normalize(doc, q, value)
    if isinstance(out, dict):
        return out
    v, st, nt = out
    st = status or st
    if q["never_default"] and st == "default_to_confirm":
        raise ValueError(f"{qid} is never defaulted")
    e = _set(doc, qid, v, st, source, note or nt)
    if st == "unknown":
        e["unknown_count"] = e.get("unknown_count", 0) + 1
    autofill_roles(doc)
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
    _sync_to_confirm(doc)
    r = roles(doc)
    return {"ready": not blocking and not unanswered, "blocking": blocking, "unanswered": unanswered,
            "to_confirm": doc["to_confirm"], "warnings": r["warnings"] if r else []}


def finalize(doc, bank=None):
    """'Use sensible defaults for the rest': defaults every defaultable question still open, never the
    never-default ones. Everything defaulted is listed in to_confirm."""
    for _ in range(4):  # defaults can unlock follow-up questions (roles); settle them
        for q in applicable(doc, bank):
            e = get(doc, q["id"])
            if (e is None or e["status"] == "unknown") and not q["never_default"] and q["required"] != "optional" and q["default"] is not None:
                apply_default(doc, q["id"])
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
    return out


def image_inputs(doc):
    """The C3 image inputs these answers decide (the lanes add brand_file and refs)."""
    v = view(doc)
    return {"design_style": v.get("design_style"), "image_cap": v.get("image_cap"), "image_provider": v.get("image_provider"),
            "paid_render_approved": bool((v.get("paid_render_approval") or {}).get("approved")), "page_set": v.get("page_set")}


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
    if _flag(a, "--harness"):
        doc["harness"] = _flag(a, "--harness")
    if cmd == "next":
        q = next_question(doc)
        print(json.dumps(q, indent=2) if q else json.dumps({"done": True, "check": check(doc)}, indent=2))
    elif cmd == "record" and len(a) >= 4:
        print(json.dumps(record(doc, a[2], a[3]), indent=2))
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
    else:
        print(__doc__)
        return 2
    save(doc, path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
