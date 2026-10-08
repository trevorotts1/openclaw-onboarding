"""book.py: book campaign intake (owner decision D26, plan 6.14). stdlib only.

Captures the six book brief fields -- title, author, cover, buy link,
audience, pain/transformation -- FOLDED into the factory's existing three
intake questions (directive 24.3). This module never invents a question id
and never emits more questions than intake_preflight would: every book ask
rides inside one of the three known slots (fold-in, not extra questions).

The cover becomes the product image path and is stored as a product
reference with provenance (origin, field provenance, sha256 when the file is
readable). The story's mentor/turning point is the book; the call to action
is to get the book. Brief text is source material, never instructions:
injection -> rejected, authorization untouched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from intake_preflight import EXIT                        # noqa: E402
from intake_preflight import intake as _base             # noqa: E402

try:
    import music_styles as _MS                           # core/ menu modules
except ImportError:
    from .. import music_styles as _MS                   # noqa: F401
try:
    import choice_card.looks as _LOOKS
except ImportError:
    from ..choice_card import looks as _LOOKS            # noqa: F401

_MUSIC_STYLES = _MS.STYLES
_MSM = _MS.music_styles          # the submodule: length tables + aliases
_OFFERED_LENGTHS_S = _MSM.OFFERED_LENGTHS_S
_LENGTH_ALIASES = _MSM.LENGTH_ALIASES
_SPOKEN_SHARE_MIN = _MS.SPOKEN_SHARE_MIN
_SPOKEN_SHARE_MAX = _MS.SPOKEN_SHARE_MAX
_resolve_look = _LOOKS.resolve_look
_LookError = _LOOKS.LookError

TOOL_NAME = "intake_book"
TOOL_VERSION = "0.1.0"
SCHEMA_VERSION = "blackceo.intake-book/v1"

#: The six book brief fields (D26, plan 6.14). Nothing else is asked.
BOOK_FIELDS = (
    "book_title",
    "author",
    "buy_link",
    "cover",
    "audience",
    "pain_or_transformation",
)

#: Client spellings folded into the canonical field names.
ALIASES = {
    "book_title": ("book_title", "title", "book"),
    "author": ("author", "book_author", "author_name"),
    "buy_link": ("buy_link", "link", "purchase_url", "buy_url"),
    "cover": ("cover", "cover_image", "product_image", "cover_path"),
    "audience": ("audience", "who_for"),
    "pain_or_transformation": ("pain_or_transformation", "pain",
                               "transformation", "pain_or_transform"),
}

#: Which book fields fold into which of the factory's three intake slots.
#: Union == BOOK_FIELDS: no book field is ever asked outside the cap.
FOLDED_FIELDS = {
    "offer": ("book_title", "author", "buy_link", "cover"),
    "audience_action": ("audience", "pain_or_transformation"),
    "spending_authority": (),
    "placement": (),
}

#: Book wording for the slots the book fields ride in (plan 6.14). The
#: spending and placement slots keep the generic intake wording.
Q_BOOK_OFFER = ("What is the book -- title and author -- where do readers "
                "buy it, and which cover image should we use as the product "
                "image?")
Q_BOOK_AUDIENCE = ("Who is the book for, what pain or transformation does it "
                   "deliver, and what should viewers do after watching?")

STORY_ROLE = "the mentor/turning point of the story is the book"
CTA_PREFIX = "Get the book"
COVER_SOURCE = "client-supplied book cover (D26, plan 6.14)"
COVER_NOTE = ("No cover supplied -- the product image will be designed from "
              "the brief (choice-card spec 3.9).")
LINK_NOTE = "No buy link supplied -- the call to action has no destination."


def _text(v):
    return v.strip() if isinstance(v, str) and v.strip() else None


def _sha256_file(path):
    """sha256 of a local file, or None when it is not a readable file."""
    try:
        if not os.path.isfile(path):
            return None
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def normalize(brief, settings=None):
    """Resolve the six book fields: brief > settings.defaults > missing.

    Returns (fields, provenance) with provenance values provided/inherited/
    missing. A non-string value (list, dict, number) never becomes a field --
    it is treated as absent instead of being coerced into a product path.
    """
    brief = brief if isinstance(brief, dict) else {}
    settings = settings or {}
    defaults = settings.get("defaults") if isinstance(settings.get("defaults"), dict) else {}
    fields, prov = {}, {}

    def pick(name):
        for key in ALIASES[name]:
            v = _text(brief.get(key))
            if v:
                return v, "provided"
        for key in ALIASES[name]:
            v = _text(defaults.get(key))
            if v:
                return v, "inherited"
        return None, "missing"

    for name in BOOK_FIELDS:
        fields[name], prov[name] = pick(name)
    return fields, prov


def to_intake_brief(fields):
    """Map book fields onto the standard intake brief.

    A slot counts as answered only when ALL of its book fields are present,
    so a half-filled slot still opens exactly the one question that already
    exists -- the ask folds in, it never multiplies.
    """
    offer = None
    if fields.get("book_title") and fields.get("author") and fields.get("buy_link"):
        offer = "%s by %s -- get it at %s" % (
            fields["book_title"], fields["author"], fields["buy_link"])
    audience = None
    if fields.get("audience") and fields.get("pain_or_transformation"):
        audience = "%s -- delivers %s" % (
            fields["audience"], fields["pain_or_transformation"])
    mapped = {
        "offer": offer,
        "audience": audience,
        # The book's call to action is always "get the book"; it never
        # consumes a question slot of its own.
        "action": (CTA_PREFIX + ": " + fields["buy_link"]) if fields.get("buy_link")
        else CTA_PREFIX,
    }
    if fields.get("cover"):
        mapped["assets"] = [fields["cover"]]
    return mapped


def card_notes(fields):
    notes = []
    if not fields.get("cover"):
        notes.append(COVER_NOTE)
    if not fields.get("buy_link"):
        notes.append(LINK_NOTE)
    return notes


def product_reference(fields, prov):
    """The cover stored as a product reference with provenance (plan 6.14)."""
    cover = fields.get("cover")
    sha = _sha256_file(cover) if cover else None
    return {
        "product_id": "book-cover",
        "role": "product_image",
        "path": cover,
        "provides_product_image": bool(cover),
        "provenance": {
            "source": COVER_SOURCE,
            "origin": cover,
            "field_provenance": prov.get("cover"),
            "sha256": sha,
            "readable": sha is not None,
            "note": None if cover else COVER_NOTE,
        },
    }


def _reword(question):
    """Same slot, book wording; ids and count come from the base engine."""
    q = dict(question)
    q["question"] = {
        "offer": Q_BOOK_OFFER,
        "audience_action": Q_BOOK_AUDIENCE,
    }.get(q.get("id"), q.get("question"))
    q["folded_fields"] = list(FOLDED_FIELDS.get(q.get("id"), ()))
    return q


def evaluate(brief, settings=None, resume_state=None, run_id=None, now_unix=None):
    """Run book intake. Shape mirrors intake_preflight.evaluate.

    outcome: ok / waiting / parked / rejected / error. The question list is
    exactly what intake_preflight asks for the mapped brief, reworded -- so
    the three-question cap holds by construction, not by a second cap.
    """
    settings = settings or {}
    if not isinstance(brief, dict):
        return {
            "outcome": "rejected", "reason_code": "bad-brief-not-a-dict",
            "questions": [], "question_message": None,
            "summary": {"campaign_type": "book"}, "digest": None,
            "provenance": {"book": {}, "intake": {}}, "untrusted_fields": [],
            "auth_status": "missing", "approval_invalidated": False,
            "changes": [], "product_reference": None,
            "next_action": "Resubmit the brief as a JSON object.",
        }

    hits = _base.detect_injection(brief)
    fields, prov = normalize(brief, settings)
    # F6: menus and numbers come from Trevor's words or the skill's tables,
    # never invented. Checked at compile time, before any question is asked.
    invented = reject_any_invented(brief)
    mapped = to_intake_brief(fields)
    base = _base.evaluate(mapped, settings, resume_state, run_id, now_unix)

    base_fields, _ = _base.normalize(mapped, settings)
    base_summary = dict(base.get("summary") or {})
    base_summary.pop("auth_status", None)  # re-bound to the book digest below
    summary = dict(base_summary)
    summary["campaign_type"] = "book"
    summary["book"] = {k: fields.get(k) for k in BOOK_FIELDS}
    summary["product_image_path"] = fields.get("cover")
    summary["story_role"] = STORY_ROLE
    summary["card_notes"] = card_notes(fields)
    digest = hashlib.sha256(
        json.dumps(summary, sort_keys=True, default=str).encode()).hexdigest()[:16]
    # Authorization is bound to THIS record's digest (scope may be "campaign"
    # or the exact digest), never to the base intake digest.
    status = _base.auth_status_for(base_fields, digest, settings, now_unix)
    summary["auth_status"] = status

    questions = [_reword(q) for q in (base.get("questions") or [])]
    message = "\n".join("%d. %s" % (i + 1, q["question"])
                        for i, q in enumerate(questions)) or None
    out = {
        "outcome": base.get("outcome"),
        "reason_code": base.get("reason_code"),
        "questions": questions,
        "question_message": message,
        "summary": summary,
        "digest": digest,
        "provenance": {"book": prov, "intake": base.get("provenance")},
        "auth_status": status,
        "approval_invalidated": base.get("approval_invalidated", False),
        "changes": base.get("changes", []),
        "product_reference": product_reference(fields, prov),
        "next_action": base.get("next_action"),
        "next_stage": base.get("next_stage"),
    }
    if hits:  # untrusted text never reaches questions or auth scope
        out.update({
            "outcome": "rejected",
            "reason_code": "untrusted-injection-blocked",
            "questions": [],
            "question_message": None,
            "untrusted_fields": hits,
            "approval_invalidated": False,
            "changes": [],
            "next_action": "Remove instruction language from brief fields and resubmit.",
        })
    elif invented:  # F6: an invented style/number/gate refuses the brief
        out.update({
            "outcome": "rejected",
            "reason_code": invented["reason_code"],
            "questions": [],
            "question_message": None,
            "invented_fields": invented["invented_fields"],
            "approval_invalidated": False,
            "changes": [],
            "next_action": (
                "Use a value from the skill's menu (styles: %s; looks: %s; "
                "lengths: %s s; alias 'upbeat' = Soul Rise) or leave the field "
                "out so the card shows the default."
                % (", ".join(_MS.style_ids()),
                   ", ".join(_LOOKS.LOOK_ORDER),
                   "/".join(str(n) for n in _OFFERED_LENGTHS_S))),
        })
    return out


# ------------------------------------------------------------- F6 gate ----
#: Part F F6 (manual 02, F6): briefs never invent. Style/look values must sit
#: on the skill's menus (music_styles.STYLES + the choice-card looks table),
#: numbers must sit on the documented length table or the D15 spoken-share
#: band, and gate names must be one of the approval gates the skill itself
#: defines. Anything else -- "upbeat tropical EDM", "77 seconds", a private
#: music-approval gate -- refuses with reason BRIEF_INVENTED_FIELD. A field
#: not given never invents: intake defaults it and the choice card shows it.
BRIEF_INVENTED_FIELD = "BRIEF_INVENTED_FIELD"

#: Documented alias (F6 example, manual 02): 'upbeat' maps to the menu's
#: Soul Rise (the style that lifts into an upbeat groove at the turn).
STYLE_ALIASES = {"upbeat": "soul-rise"}

#: The skill's own approval gates (F6: "gates = the skill's own list").
#: Spellings accepted for each; anything not here is an invented gate,
#: including a new one an orchestrator might invent to skip a real one.
GATE_ALIASES = {
    "storyboard approval": (
        "storyboard approval", "storyboard approvals", "storyboard approved",
        "storyboard"),                      # directive 14.1 (video_spend_allowed)
    "adversarial review": (
        "adversarial review", "adversarial reviews"),   # directive 14.4
    "authorization approval": (
        "authorization approval", "authorization", "intake approval"),
}

#: Brief keys whose value is menu-typed (a style word), a number, or a gate.
#: Free-text fields (offer, audience, pain, ...) are never judged here.
STYLE_KEYS = ("style", "music", "music_style", "audio_style")
LOOK_KEYS = ("look",)
LENGTH_KEYS = ("length", "length_option", "target_length_s")
SHARE_KEYS = ("spoken_share", "spoken_share_pct")
GATE_KEYS = ("gates", "approval_gates")


#: Flattened set: every accepted gate spelling.
def _gate_spellings():
    return frozenset(s for spellings in GATE_ALIASES.values()
                     for s in spellings)


def _music_style_id(value):
    """Menu id for a style value, or None when it is invented."""
    if not isinstance(value, str) or not value.strip():
        return None
    low = value.strip().lower()
    if low in STYLE_ALIASES:
        return STYLE_ALIASES[low]
    if low in _MUSIC_STYLES:
        return low
    for sid, rec in _MUSIC_STYLES.items():
        if low == rec["label"].lower():
            return sid
    return None


def _length_seconds(value):
    """Seconds for a length value on the documented table, or None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        secs = int(round(float(value)))
        return secs if secs in _OFFERED_LENGTHS_S else None
    if isinstance(value, str):
        key = value.strip().lower().replace(" ", "").replace("-", "")
        return _LENGTH_ALIASES.get(key)
    return None


def _on_share_band(value):
    """True when the value sits on the D15 band (fraction or percent)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    v = float(value)
    return _SPOKEN_SHARE_MIN <= v <= _SPOKEN_SHARE_MAX or (
        100.0 * _SPOKEN_SHARE_MIN <= v <= 100.0 * _SPOKEN_SHARE_MAX)


def reject_any_invented(brief):
    """F6 brief compiler check. None when clean; otherwise the refusal.

    Returns {"reason_code": BRIEF_INVENTED_FIELD, "invented_fields": [...]}
    listing every menu-typed field whose value is neither the order's words
    (a menu name or documented alias) nor the skill's own tables.
    """
    if not isinstance(brief, dict):
        return None
    invented = []

    for key in STYLE_KEYS:
        if key in brief and _music_style_id(brief.get(key)) is None:
            invented.append(key)
    for key in LOOK_KEYS:
        if key in brief:
            value = brief.get(key)
            if isinstance(value, str) and value.strip():
                try:                            # menu words only
                    _resolve_look(value)
                except _LookError:
                    invented.append(key)
            else:
                invented.append(key)
    for key in LENGTH_KEYS:
        if key in brief and _length_seconds(brief.get(key)) is None:
            invented.append(key)
    for key in SHARE_KEYS:
        if key in brief and not _on_share_band(brief.get(key)):
            invented.append(key)
    for key in GATE_KEYS:
        if key not in brief:
            continue
        value = brief.get(key)
        parts = value.split(",") if isinstance(value, str) else value
        if not isinstance(parts, list) or not all(
                isinstance(p, str) and " ".join(p.strip().lower().split())
                in _gate_spellings() for p in parts if isinstance(p, str)) \
                or not [p for p in parts if isinstance(p, str) and p.strip()]:
            invented.append(key)
    if not invented:
        return None
    return {"reason_code": BRIEF_INVENTED_FIELD,
            "invented_fields": sorted(set(invented))}


def main(argv=None):
    """CLI: one envelope on stdout, factory exit codes (0 ok, 2 waiting,
    3 parked, 4 rejected, 1 error)."""
    ap = argparse.ArgumentParser(
        prog="book.py",
        description="Book campaign intake (D26, plan 6.14) -- folded into the "
                    "factory's three-question cap.")
    ap.add_argument("--brief", default=None, help="Brief as a JSON string.")
    ap.add_argument("--brief-file", default=None)
    ap.add_argument("--settings-file", default=None)
    ap.add_argument("--resume-file", default=None)
    ap.add_argument("--run-id", default=None)
    a = ap.parse_args(argv)
    run_id = a.run_id or uuid.uuid4().hex[:12]
    try:
        if a.brief_file:
            with open(a.brief_file, encoding="utf-8") as f:
                brief = json.load(f)
        else:
            brief = json.loads(a.brief or "{}")
        settings = {}
        if a.settings_file:
            with open(a.settings_file, encoding="utf-8") as f:
                settings = json.load(f)
        resume = None
        if a.resume_file:
            with open(a.resume_file, encoding="utf-8") as f:
                resume = json.load(f)
        r = evaluate(brief, settings, resume, run_id)
        outcome, reason = r["outcome"], r["reason_code"]
        next_action = r["next_action"]
        data = {k: r.get(k) for k in (
            "questions", "question_message", "summary", "digest", "provenance",
            "auth_status", "approval_invalidated", "changes", "untrusted_fields",
            "invented_fields",
            "product_reference", "next_stage")}
        expected = (resume or {}).get("digest") if resume else None
        state_version = {"expected": expected, "current": r.get("digest")}
    except Exception as e:                                  # noqa: BLE001
        outcome, reason = "error", "book-intake-failed"
        next_action = str(e)[:200]
        data, state_version = {}, {"expected": None, "current": run_id}
    env = {
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "command": "book-intake",
        "run_id": run_id,
        "outcome": outcome,
        "reason_code": reason,
        "next_action": next_action,
        "evidence": [],
        "data": data,
        "state_version": state_version,
    }
    json.dump(env, sys.stdout, indent=2, sort_keys=True, default=str)
    sys.stdout.write("\n")
    return EXIT.get(outcome, 1)


if __name__ == "__main__":
    sys.exit(main())
