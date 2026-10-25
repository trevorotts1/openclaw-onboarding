"""Reuse of answers already given, without re-asking or overwriting.

S75-T23's resume rule: an answered choice is reused by identity, never asked
again. A changed question definition is NOT reused -- it is reported as stale
so the client answers the exact menu they were shown. Every function here is
read-only; ``apply_reuse`` returns a decision, it never writes a session or an
approval.

'' ``ponytail:`` shared-library (Notion) reuse is S75-T14's. This module only
offers what the run itself already holds, and says so rather than pretending a
library was consulted.
"""
from __future__ import annotations

HELP_WORDS = ("help", "help me choose", "explain", "explain the styles")
REUSE_WORDS = ("reuse", "reuse my answers", "show my answers",
               "what have i answered")
HELP_QUESTION_IDS = ("music",)


def _digest(value):
    from . import intake_session as session
    return session._digest(value)


def _label(question):
    return (question or {}).get("label") or (question or {}).get("id") or ""


def kept_rows(state):
    """Answers this run already holds, in the order the client gave them."""
    rows, records = [], (state or {}).get("answer_records") or {}
    for qid in (state or {}).get("active_question_ids") or list(records):
        rec = records.get(qid)
        if not isinstance(rec, dict):
            continue
        parsed = rec.get("parsed") or {}
        rows.append({"question_id": qid, "label": _label(rec.get("question")),
                     "text": parsed.get("text"), "value": parsed.get("value"),
                     "raw_answer": rec.get("raw_answer"),
                     "at_utc": rec.get("at_utc"),
                     "definition_digest": rec.get("definition_digest")})
    return rows


def reusable_rows(state, questions):
    """Per answered question: still matches today's definition, or is stale.

    ``matches`` False means the menu or a dependent value changed; the saved
    answer is preserved but cannot be silently replayed (CARD_REVISION_CHANGED).
    """
    current = {q["id"]: q for q in questions or []}
    rows = []
    for row in kept_rows(state):
        q = current.get(row["question_id"])
        row = dict(row, matches=bool(q) and
                   row["definition_digest"] == _digest(q))
        if not row["matches"]:
            row["reason"] = ("the question changed, so this answer is kept as "
                             "history and is not reused")
        rows.append(row)
    return rows


def apply_reuse(state, question_ids, questions):
    """Decide which saved answers may be reused. Pure: no state is mutated.

    Refused when the question changed or is no longer asked. A new client
    answer is never replaced by a reused one, because nothing here writes.
    """
    reusable = {r["question_id"]: r for r in reusable_rows(state, questions)}
    applied, refused = [], []
    for qid in question_ids or []:
        row = reusable.get(qid)
        if row is None:
            refused.append({"question_id": qid, "reason": "no saved answer"})
        elif not row["matches"]:
            refused.append({"question_id": qid, "reason": row["reason"]})
        else:
            applied.append(qid)
    return {"applied": applied, "refused": refused, "wrote": False}


def _is_option_label(raw, question):
    text = (raw or "").strip().casefold()
    return any(text == str(option).casefold()
               for option, _sentence in question.get("options") or [])


def progress_message(state, questions):
    """Real counts plus the one next action; never 'approved' or a fake percent."""
    from . import style_help
    answered = len((state or {}).get("active_question_ids") or [])
    total = len(questions or [])
    next_label = ""
    pending = ((state or {}).get("pending") or {})
    for q in questions or []:
        if q["id"] == pending.get("id"):
            next_label = q.get("label")
            break
    return style_help.progress(answered, total, next_label)


def reuse_message(state, questions=None):
    """The single reuse screen: what is kept, and that nothing is re-asked."""
    rows = kept_rows(state)
    if not rows:
        body = ["You have not answered anything yet.",
                "Nothing is reused, and nothing is skipped."]
    else:
        body = ["Here is what you already answered:"]
        for n, row in enumerate(rows, 1):
            detail = row["text"] if row["text"] not in (None, "") \
                else (row["raw_answer"] or "")
            body.append("%d. %s: %s" % (n, row["label"].title(), detail))
        body += ["", "I keep all of these; none is asked again.",
                 "Reusing answers is not an approval of anything new."]
    line = progress_message(state, questions)
    if line:
        body += ["", line]
    body += ["", "Reply with a number for the current question when ready."]
    return "\n".join(body)


def guided_reply(raw, question, state, questions=None):
    """A help/reuse word answered with guidance; ``None`` for a real reply.

    Only the music question offers style help, and only menu questions accept
    guidance, so a typed brief question still stores the client's own words
    (a typed answer literally saying "help" keeps its existing meaning).
    """
    if (question or {}).get("free_text") or _is_option_label(raw, question):
        return None
    text = (raw or "").strip().casefold()
    if not text:
        return None
    qid = question.get("id")
    if qid in HELP_QUESTION_IDS and text in HELP_WORDS:
        from . import style_help
        rows = style_help.help_rows()
        if not rows:
            return None
        selected = None
        rec = ((state or {}).get("answer_records") or {}).get(qid) or {}
        parsed = rec.get("parsed") or {}
        value = parsed.get("value")
        if isinstance(value, str):
            selected = value
        answers = (state or {}).get("active_question_ids") or []
        line = progress_message(state, questions or
                                (state or {}).get("required_questions") or
                                [{"id": p, "label": p} for p in answers])
        return {"kind": "style_help", "reason_code": "CARD_HELP_SHOWN",
                "message": style_help.help_text(selected=selected)}
    if text in REUSE_WORDS:
        return {"kind": "answer_reuse", "reason_code": "REUSE_OFFER_SHOWN",
                "message": reuse_message(state, questions)}
    return None
