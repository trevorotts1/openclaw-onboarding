"""Durable, renderer-bound intake turns. Question text belongs to intake_card.

A call consumes at most one new client reply to a previously emitted question.
An exact cumulative history may be replayed, with at most one appended turn.
Every raw reply is journalled before advancing. A changed menu never reinterprets
an earlier numeric selection. Existing asset-approval machinery is untouched.
"""
import copy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile

from . import intake_card as card

SCHEMA = "blackceo.intake-session/v1"


def _dump(value):
    # Round-tripping also normalises integer JSON object keys in option values.
    value = json.loads(json.dumps(value, ensure_ascii=False))
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value):
    return hashlib.sha256(_dump(value).encode("utf-8")).hexdigest()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _write(path, state):
    fd, tmp = tempfile.mkstemp(prefix=".intake-session-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, sort_keys=True, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        dfd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _session_path(run_dir, run_state_file):
    if run_dir:
        return Path(run_dir) / "control" / "intake-session.json"
    if run_state_file:
        return Path(run_state_file).parent / "intake-session.json"
    return None


def _shape(base, answers, flow, client_dir):
    return (card._shaped(base, answers, client_dir) if flow
            else card._priced(base, answers))


def _active(state, base, client_dir):
    """Reattach surviving facts BY ID, verifying each original question.

    A changed conditional branch retains all records, including business facts
    occurring after the new branch's unanswered follow-up. Nothing is shifted
    into a newly inserted slot.
    """
    answers = []
    records = state["answer_records"]
    for _ in range(len(base) + 20):
        qs = _shape(base, answers, state["purpose_flow"], client_dir)
        if len(answers) >= len(qs):
            return answers, qs, None
        q = qs[len(answers)]
        rec = records.get(q["id"])
        if rec is None:
            return answers, qs, None
        if rec["definition_digest"] != _digest(q):
            return answers, qs, q["id"]
        parsed = copy.deepcopy(rec["parsed"])
        if parsed.get("id") != q["id"] or rec.get("question_id") != q["id"]:
            raise ValueError("stored answer has a mismatched question id")
        if rec.get("source") != "client" or not rec.get("accepted") or not rec.get("at_utc"):
            raise ValueError("stored answer has no client provenance")
        original_q = rec.get("question")
        if (_digest(original_q) != rec["definition_digest"] or
                _digest({"id": q["id"], "definition": original_q,
                         "message": rec.get("rendered_question")}) != rec.get("question_digest")):
            raise ValueError("stored answer is not bound to its rendered question")
        verified = _parse(rec["raw_answer"], q)
        if not verified or verified.get("error"):
            raise ValueError("saved raw answer is not an offered option")
        verified["id"] = q["id"]
        if _dump(verified) != _dump(parsed) or _dump(_option(q, verified)) != _dump(rec.get("option")):
            raise ValueError("stored answer differs from its raw client reply or option identity")
        answers.append(parsed)
    raise ValueError("question flow did not converge")


def _pending(answers, qs, editing=None):
    if editing:
        matches = [i for i, q in enumerate(qs) if q["id"] == editing]
        if not matches:
            raise ValueError("the question selected for editing is no longer present")
        at = matches[0]
    else:
        at = len(answers)
    if at < len(qs):
        q = qs[at]
        message = card.render_step(at + 1, qs)
        return {"id": q["id"], "definition": copy.deepcopy(q),
                "definition_digest": _digest(q), "position": at + 1,
                "message": message, "digest": _digest({"id": q["id"],
                    "definition": q, "message": message})}
    message = card.render_recap(answers, qs)
    return {"id": "recap", "definition_digest": _digest(answers),
            "message": message, "digest": _digest({"id": "recap", "message": message})}


def _parse(raw, q):
    text = raw.strip()
    low = text.casefold()
    if q.get("free_text"):
        return card._parse(raw, q)
    # "yes" never means a recommendation on an unrelated question. Recognise
    # it only when the menu actually names an affirmative option.
    if low in card._YES:
        affirmative = [i for i, o in enumerate(q["options"], 1)
                       if o[0].casefold() == low or
                       (low in ("yes", "y", "yep") and
                        (o[0].casefold() == "yes" or o[0].casefold().startswith("yes -")))]
        if len(affirmative) != 1:
            return None
        return card._parse(str(affirmative[0]), q)
    # Exact option labels are safe and useful when a previously invented menu
    # is being repaired. No fuzzy matching, durations/ages/budgets inferred
    # from sentences, or label aliases are introduced here.
    exact = [i for i, o in enumerate(q["options"], 1)
             if o[0].casefold() == low]
    if len(exact) == 1:
        return card._parse(str(exact[0]), q)
    return card._parse(raw, q)


def _option(q, parsed):
    if q.get("free_text") or q["id"] == "spend":
        return None
    n = parsed.get("n")
    if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= len(q["options"]):
        raise ValueError("parsed answer does not identify an offered option")
    label, description = q["options"][n - 1]
    # Option identity follows its text/value, never its changing menu number.
    identity = {"question_id": q["id"], "label": label,
                "description": description, "value": parsed.get("value")}
    return {"id": _digest(identity), "label": label,
            "description": description, "value": parsed.get("value"), "number_shown": n}


def _finish(state, answers, qs, run_dir, target, client_dir):
    if state["purpose_flow"]:
        blocked = card._wait_reason(answers, qs)
        if blocked:
            return blocked
    # These record PREFERENCES from intake. They do not approve a script,
    # storyboard or a selected song artifact; those existing gates still wait.
    if run_dir:
        from storyboard_director import approval_runner
        from song_choices import song_choices
        from script_approval import card_answers
        approval_runner.record_card_answer(run_dir, answers, qs, target)
        song_choices.record_card_answer(run_dir, answers, target)
        card_answers.write(run_dir, answers, qs)
        if state["purpose_flow"]:
            method = card._method_record(answers, qs)
            if method:
                card._write_json(os.path.join(run_dir, "control", "method.json"), method)
            card._record_agnes_receipt(run_dir, answers, qs)
    if state["purpose_flow"] and client_dir:
        card._remember_agnes(client_dir, answers, qs)
    return None


def _result(state, path, answers, qs, code="INTAKE_WAITING", outcome="ok", detail=None):
    pending = state.get("pending") or {}
    result = {"answers": answers, "done": bool(state.get("done")),
              "message": ("Locked in. I am starting now." if state.get("done")
                          else pending.get("message", "")),
              "outcome": outcome, "reason_code": code,
              "question_id": None if state.get("done") else pending.get("id"),
              "question_digest": None if state.get("done") else pending.get("digest"),
              "answered_count": len(answers), "total_count": len(qs),
              "saved_answer_count": len(state.get("answer_records", {})),
              "session_path": str(path), "pending": copy.deepcopy(pending),
              "video_model": next((a.get("n") for a in answers if a.get("id") == "model"), None)}
    if detail:
        result["detail"] = detail
    return result


def process(replies, questions=None, *, run_dir=None, run_state_file=None,
            target=None, client_dir=None, purpose_flow=None, question_id=None,
            question_digest=None, source="client"):
    """One persistent intake turn; a reply needs a previously emitted question.

    ``source`` must name the client. Identity arguments, when supplied, must
    match the exact pending renderer receipt. A caller must send ``message``
    verbatim and carry the receipt with replies whenever its transport permits.
    ``questions`` is the current renderer's base list, never agent-written text.
    """
    path = _session_path(run_dir, run_state_file)
    if path is None:
        return {"done": False, "answers": [], "message": "",
                "outcome": "error", "reason_code": "INTAKE_SESSION_PATH_REQUIRED",
                "question_id": None, "question_digest": None,
                "answered_count": 0, "total_count": 0}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path) + ".lock", "a", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            return _process_locked(path, replies, questions, run_dir, run_state_file,
                                   target, client_dir, purpose_flow, question_id,
                                   question_digest, source)
        except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
            return {"done": False, "answers": [], "message": "",
                    "outcome": "error", "reason_code": "INTAKE_SESSION_UNREADABLE",
                    "detail": str(exc), "session_path": str(path),
                    "question_id": None, "question_digest": None,
                    "answered_count": 0, "total_count": 0}
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _process_locked(path, replies, questions, run_dir, run_state_file, target,
                    client_dir, purpose_flow, question_id, question_digest, source):
    base = questions or card.QUESTIONS
    if not isinstance(replies, (list, tuple)) or any(not isinstance(r, str) for r in replies):
        raise ValueError("replies must be strings")
    existed = path.exists()
    if existed:
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("schema") != SCHEMA or not isinstance(state.get("answer_records"), dict):
            raise ValueError("unrecognised intake session schema")
        # Preserve the flow originally shown, even if an intro or receipt made
        # the legacy new-run heuristic change since the last CLI invocation.
        if purpose_flow is not None and bool(purpose_flow) != state["purpose_flow"]:
            answers, qs, _ = _active(state, base, client_dir)
            return _result(state, path, answers, qs, "INTAKE_FLOW_MISMATCH", "waiting")
    else:
        flow = (card.new_run_flow(run_dir, run_state_file) if purpose_flow is None
                else bool(purpose_flow))
        state = {"schema": SCHEMA, "created_at": _now(), "purpose_flow": flow,
                 "answer_records": {}, "events": [], "done": False,
                 "editing_question_id": None, "confirmation": None,
                 "base_definition_digest": _digest(base)}
    answers, qs, drift = _active(state, base, client_dir)
    current = _pending(answers, qs, state.get("editing_question_id"))
    old_pending = state.get("pending")
    changed = bool(old_pending and old_pending.get("digest") != current["digest"])
    if not old_pending or changed:
        if old_pending:
            state.setdefault("superseded_questions", []).append(old_pending)
        state["pending"] = current
        state["done"] = False
        state["confirmation"] = None
        _write(path, state)
    if not existed and replies:
        return _result(state, path, answers, qs, "QUESTION_NOT_PRESENTED", "waiting")
    if changed:
        return _result(state, path, answers, qs, "CARD_REVISION_CHANGED", "waiting",
                       "The saved answers remain intact. The changed question must be answered against this exact menu.")
    if not replies:
        return _result(state, path, answers, qs,
                       "INTAKE_CONFIRMED" if state["done"] else "INTAKE_WAITING")
    if source != "client":
        return _result(state, path, answers, qs, "ANSWER_SOURCE_REQUIRED", "waiting")
    if question_id is not None and question_id != current["id"]:
        return _result(state, path, answers, qs, "QUESTION_ID_MISMATCH", "waiting")
    if question_digest is not None and question_digest != current["digest"]:
        return _result(state, path, answers, qs, "QUESTION_DIGEST_MISMATCH", "waiting")
    history = [e["raw_answer"] for e in state["events"]]
    new = list(replies)
    if len(new) > 1:
        prefix = min(len(new), len(history))
        if new[:prefix] != history[:prefix]:
            return _result(state, path, answers, qs, "INTAKE_REPLAY_MISMATCH", "waiting")
        new = new[len(history):]
    if len(new) > 1:
        return _result(state, path, answers, qs, "ONE_REPLY_AT_A_TIME", "waiting")
    if not new:
        return _result(state, path, answers, qs, "INTAKE_REPLAYED")
    raw = new[0]
    if state["done"]:
        return _result(state, path, answers, qs, "INTAKE_ALREADY_CONFIRMED", "waiting")
    event = {"sequence": len(state["events"]) + 1, "raw_answer": raw,
             "source": source, "at_utc": _now(), "question_id": current["id"],
             "question_digest": current["digest"], "rendered_question": current["message"],
             "accepted": False}
    state["events"].append(event)
    code, outcome = "INTAKE_ANSWER_SAVED", "ok"
    if current["id"] == "recap":
        low = raw.strip().lower()
        if low in card._YES and len(answers) == len(qs):
            event["accepted"] = True
            state["confirmation"] = copy.deepcopy(event)
            # Durably record the explicit recap confirmation before the
            # existing preference writers execute. Recovery retries no paid job.
            _write(path, state)
            blocked = _finish(state, answers, qs, run_dir, target, client_dir)
            if blocked:
                code, outcome = blocked, "waiting"
            else:
                state["done"] = True
                code = "INTAKE_CONFIRMED"
        elif low.isdigit() and 1 <= int(low) <= len(qs):
            state["editing_question_id"] = qs[int(low) - 1]["id"]
            event["accepted"] = True
        else:
            code, outcome = "INVALID_RECAP_REPLY", "waiting"
    else:
        q = current["definition"]
        parsed = _parse(raw, q)
        if not parsed or parsed.get("error"):
            code, outcome = "INVALID_OPTION", "waiting"
        else:
            parsed["id"] = q["id"]
            option = _option(q, parsed)
            event.update(accepted=True, option=option, parsed=copy.deepcopy(parsed))
            record = dict(event, definition_digest=current["definition_digest"],
                          question=copy.deepcopy(q))
            state["answer_records"][q["id"]] = record
            state["editing_question_id"] = None
    # Persist the raw event/accepted answer before constructing the next turn.
    state["updated_at"] = _now()
    _write(path, state)
    answers, qs, drift = _active(state, base, client_dir)
    state["pending"] = _pending(answers, qs, state.get("editing_question_id"))
    _write(path, state)
    return _result(state, path, answers, qs, code, outcome)
