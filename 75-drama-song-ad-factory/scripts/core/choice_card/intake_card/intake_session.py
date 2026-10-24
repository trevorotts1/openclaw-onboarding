"""Durable, renderer-bound intake turns. Question text belongs to intake_card.

A call consumes at most one new client reply to a previously emitted question.
An exact cumulative history may be replayed, with at most one appended turn.
Every raw reply is journalled before advancing. A changed menu never reinterprets
an earlier numeric selection. Existing asset-approval machinery is untouched.
"""
import copy
from contextlib import contextmanager, closing
from datetime import datetime, timezone
try:
    import fcntl
except ImportError:  # native Windows
    fcntl = None
    import msvcrt
import hashlib
import json
import os
import sqlite3
from pathlib import Path
import tempfile

from . import intake_card as card

SCHEMA = "blackceo.intake-session/v1"


@contextmanager
def session_lock(lock_path):
    """One cross-process lock on POSIX and native Windows; no optional package."""
    with open(lock_path, "a+b") as lock:
        if fcntl is not None:
            fcntl.flock(lock, fcntl.LOCK_EX)
        else:
            lock.seek(0, os.SEEK_END)
            if lock.tell() == 0:
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(lock, fcntl.LOCK_UN)
            else:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


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
        if os.name != "nt":
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
        answers.append(_checked_parsed(rec, q))
    raise ValueError("question flow did not converge")


def _checked_parsed(rec, q):
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
    if q["id"] == "model":
        if rec.get("provider_identity") != _provider_identity(parsed):
            raise ValueError("saved video model route identity is missing or changed")
    return parsed


def _provider_identity(parsed):
    from choice_card.video_models import video_models as models
    row = models.model_for(parsed["n"])
    models.assert_resolvable(row)
    return {k: copy.deepcopy(row.get(k)) for k in
            ("name", "kie_model", "lock", "resolution", "shape", "shot_s", "kie_tier", "clip_s")}


def _persist_model_lock(state, answers, run_dir):
    import state_store
    try:
        return _persist_model_lock_impl(state, answers, run_dir)
    except (state_store.StoreError, sqlite3.Error):
        # A malformed or recovery-required existing store is preserved, never
        # recreated, rebound to another run, or treated as completed intake.
        return "VIDEO_MODEL_STATE_UNAVAILABLE"


def _persist_model_lock_impl(state, answers, run_dir):
    selected = next((a for a in answers if a.get("id") == "model"), None)
    if selected is None or not run_dir:
        return None
    from choice_card.video_models import video_models as models
    from kie_dispatch import model_lock
    import state_store
    rec = state["answer_records"]["model"]
    provider = _provider_identity(selected)
    if rec.get("provider_identity") != provider:
        return "VIDEO_MODEL_IDENTITY_CHANGED"
    db = Path(run_dir) / "control" / "state.sqlite3"
    ids, bindings = set(), []
    if state.get("run_id"):
        bindings.append((state["run_id"], "intake-session"))
    run_state = Path(run_dir) / "control" / "run-state.json"
    if run_state.exists():
        saved = json.loads(run_state.read_text(encoding="utf-8"))
        if saved.get("run_id"):
            bindings.append((saved["run_id"], "control/run-state.json"))
    if db.exists():
        # Read identity before opening a writer; a foreign/multi-run store is
        # never repaired or overwritten by intake.
        from urllib.parse import quote
        with closing(sqlite3.connect("file:" + quote(str(db.resolve())) + "?mode=ro", uri=True)) as con:
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in ("stages", "video_model_lock"):
                if table in tables:
                    ids.update(r[0] for r in con.execute("SELECT DISTINCT run_id FROM " + table) if r[0])
        if len(ids) > 1:
            return "VIDEO_MODEL_RUN_ID_AMBIGUOUS"
        if ids:
            bindings.append((next(iter(ids)), "existing-state-store"))
    if any(not isinstance(rid, str) or not rid for rid, _ in bindings):
        return "VIDEO_MODEL_RUN_ID_AMBIGUOUS"
    if len({rid for rid, _ in bindings}) > 1:
        return "VIDEO_MODEL_RUN_ID_CONFLICT"
    rid, identity_source = (bindings[0] if bindings else
                            (Path(run_dir).resolve().name, "run_folder_basename"))
    chosen = models.model_for(selected["n"])
    expected = chosen.get("lock", chosen["kie_model"])
    existing = model_lock.read_locked_model(db, rid) if db.exists() else None
    if existing is not None and existing != expected:
        return "VIDEO_MODEL_LOCK_CONFLICT"
    # This only creates the store's standard empty tables. It does not claim,
    # start or complete any stage, and it never submits a provider request.
    with state_store.Store(db):
        pass
    receipt = (models.lock_choice(db, rid, selected["n"]) if existing is None else
               {"run_id": rid, "model": existing, "reused": True})
    if model_lock.read_locked_model(db, rid) != expected:
        return "VIDEO_MODEL_LOCK_NOT_PERSISTED"
    state["run_id"] = rid
    state["model_lock"] = dict(receipt, provider_identity=provider,
        identity_source=identity_source, question_digest=rec["question_digest"],
        source=rec["source"], source_ref=rec.get("source_ref"))
    return None


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
        if at == 0 and q.get("preface"):
            message = q["preface"] + "\n\n" + message
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
        def starts_word(label, word):
            label = label.casefold()
            return label == word or (label.startswith(word) and
                                     len(label) > len(word) and not label[len(word)].isalnum())
        has_no = any(starts_word(o[0], "no") for o in q["options"])
        affirmative = [i for i, o in enumerate(q["options"], 1)
                       if o[0].casefold() == low or
                       (low in ("yes", "y", "yep") and has_no and starts_word(o[0], "yes"))]
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
    model_problem = _persist_model_lock(state, answers, run_dir)
    if model_problem:
        return model_problem
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
              "run_id": state.get("run_id"), "model_lock": copy.deepcopy(state.get("model_lock")),
              "video_model": next((a.get("n") for a in answers if a.get("id") == "model"), None)}
    if state.get("legacy_answers"):
        result["legacy_answers"] = copy.deepcopy(state["legacy_answers"])
    if detail:
        result["detail"] = detail
    return result


def process(replies, questions=None, *, run_dir=None, run_state_file=None,
            target=None, client_dir=None, purpose_flow=None, question_id=None,
            question_digest=None, source="client", source_ref=None):
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
    with session_lock(str(path) + ".lock"):
        try:
            return _process_locked(path, replies, questions, run_dir, run_state_file,
                                   target, client_dir, purpose_flow, question_id,
                                   question_digest, source, source_ref)
        except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
            return {"done": False, "answers": [], "message": "",
                    "outcome": "error", "reason_code": "INTAKE_SESSION_UNREADABLE",
                    "detail": str(exc), "session_path": str(path),
                    "question_id": None, "question_digest": None,
                    "answered_count": 0, "total_count": 0}


def _process_locked(path, replies, questions, run_dir, run_state_file, target,
                    client_dir, purpose_flow, question_id, question_digest, source, source_ref):
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
        if run_dir:
            legacy = Path(run_dir) / "card-answers.json"
            if legacy.exists():
                try:
                    old = json.loads(legacy.read_text(encoding="utf-8"))
                    state["legacy_answers"] = {"status": "unverified_preserved",
                        "path": str(legacy), "data": old,
                        "reason": "Prior answers need explicit raw client provenance; no numeric menu mapping was imported."}
                except (OSError, ValueError):
                    state["legacy_answers"] = {"status": "unreadable_preserved", "path": str(legacy)}
    answers, qs, drift = _active(state, base, client_dir)
    current = _pending(answers, qs, state.get("editing_question_id"))
    _progress(state, answers, qs)
    old_pending = state.get("pending")
    changed = bool(old_pending and old_pending.get("digest") != current["digest"])
    if not old_pending or changed:
        if old_pending:
            state.setdefault("superseded_questions", []).append(old_pending)
        state["pending"] = current
        if changed:
            state["pending"]["requires_identity"] = True
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
    if (raw.strip().isdigit() and state["pending"].get("requires_identity") and
            (question_id != current["id"] or question_digest != current["digest"])):
        return _result(state, path, answers, qs, "QUESTION_IDENTITY_REQUIRED", "waiting")
    if state["done"]:
        return _result(state, path, answers, qs, "INTAKE_ALREADY_CONFIRMED", "waiting")
    event = {"sequence": len(state["events"]) + 1, "raw_answer": raw,
             "source": source, "source_ref": source_ref, "at_utc": _now(), "question_id": current["id"],
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
            if q["id"] == "model":
                record["provider_identity"] = _provider_identity(parsed)
            state["answer_records"][q["id"]] = record
            state["editing_question_id"] = None
    # Persist the raw event/accepted answer before constructing the next turn.
    state["updated_at"] = _now()
    _write(path, state)
    answers, qs, drift = _active(state, base, client_dir)
    _progress(state, answers, qs)
    next_pending = _pending(answers, qs, state.get("editing_question_id"))
    if state["pending"].get("requires_identity") and next_pending["digest"] == state["pending"]["digest"]:
        next_pending["requires_identity"] = True
    state["pending"] = next_pending
    _write(path, state)
    return _result(state, path, answers, qs, code, outcome)


def _progress(state, answers, qs):
    state["required_question_ids"] = [q["id"] for q in qs]
    state["active_question_ids"] = [a["id"] for a in answers]
    state["answered_count"] = len(answers)
    state["total_count"] = len(qs)


def _inspect_model_lock(db, run_id):
    """Strictly read-only projection: never creates a DB, journal or sidecar.

    A not-yet-checkpointed concurrent WAL writer can make this projection
    unavailable; completion remains fail-closed until the writer publishes it.
    """
    if not db.is_file():
        return None
    from urllib.parse import quote
    try:
        uri = "file:" + quote(str(db.resolve())) + "?mode=ro&immutable=1"
        with closing(sqlite3.connect(uri, uri=True)) as con:
            row = con.execute("SELECT model FROM video_model_lock WHERE run_id=?", (run_id,)).fetchone()
            return row[0] if row else None
    except sqlite3.Error:
        return None


def completion_status(run_dir):
    """Inspect persisted intake completion without changing any run artifact.

    Only this session's complete question IDs and its explicit client recap
    confirmation permit ``done``. A summary string or asset preference cannot.
    """
    path = _session_path(run_dir, None)
    out = {"exists": bool(path and path.exists()), "valid": True, "done": False,
           "reason_code": "INTAKE_SESSION_MISSING", "question_id": None,
           "question_digest": None, "message": "", "answered_count": 0,
           "total_count": 0, "pending": {}}
    if not out["exists"]:
        return out
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("schema") != SCHEMA:
            raise ValueError("unrecognised intake session schema")
        required = state["required_question_ids"]
        active = state["active_question_ids"]
        if (not isinstance(required, list) or not required or
                any(not isinstance(q, str) or not q for q in required) or
                len(set(required)) != len(required) or not isinstance(active, list) or
                active != required[:len(active)] or len(active) > len(required) or
                type(state["answered_count"]) is not int or
                type(state["total_count"]) is not int or
                state["answered_count"] != len(active) or state["total_count"] != len(required)):
            raise ValueError("stored completion counts or question identities do not agree")
        for qid in active:
            rec = state["answer_records"][qid]
            question = copy.deepcopy(rec["question"])
            if isinstance(question.get("values"), dict):
                question["values"] = {int(k) if str(k).isdigit() else k: v
                                      for k, v in question["values"].items()}
            _checked_parsed(rec, question)
        pending = state["pending"]
        if not isinstance(pending.get("id"), str) or not pending.get("message") or not pending.get("digest"):
            raise ValueError("no exact pending renderer receipt")
        if pending["id"] == "recap":
            expected = _digest({"id": "recap", "message": pending["message"]})
        else:
            if pending["id"] not in required:
                raise ValueError("pending question is not in the required question list")
            expected = _digest({"id": pending["id"], "definition": pending["definition"],
                                "message": pending["message"]})
        if pending["digest"] != expected:
            raise ValueError("pending renderer receipt does not match its exact text")
        if type(state.get("done")) is not bool:
            raise ValueError("completion state is not boolean")
        if state["done"]:
            conf = state["confirmation"]
            if (len(active) != len(required) or pending["id"] != "recap" or
                    conf.get("source") != "client" or conf.get("accepted") is not True or
                    conf.get("question_id") != "recap" or
                    conf.get("raw_answer", "").strip().lower() not in card._YES or
                    conf.get("question_digest") != pending["digest"] or
                    conf.get("rendered_question") != pending["message"] or not conf.get("at_utc") or
                    not any(e == conf for e in state["events"])):
                raise ValueError("completion has no matching explicit client recap confirmation")
            if "model" in required:
                selected = state["answer_records"]["model"]
                binding = state.get("model_lock") or {}
                provider = selected.get("provider_identity")
                expected_model = provider.get("lock") or provider["kie_model"]
                if (not state.get("run_id") or binding.get("run_id") != state["run_id"] or
                        binding.get("provider_identity") != provider or
                        binding.get("question_digest") != selected["question_digest"] or
                        binding.get("source") != "client" or binding.get("model") != expected_model or
                        _inspect_model_lock(Path(run_dir) / "control" / "state.sqlite3",
                                            state["run_id"]) != expected_model):
                    raise ValueError("completion has no matching persisted video-model choice")
        out.update(valid=True, done=state["done"],
                   reason_code="INTAKE_CONFIRMED" if state["done"] else "INTAKE_WAITING",
                   question_id=None if state["done"] else pending["id"],
                   question_digest=None if state["done"] else pending["digest"],
                   message=pending["message"], answered_count=len(active),
                   total_count=len(required), pending=copy.deepcopy(pending))
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError) as exc:
        out.update(valid=False, done=False, reason_code="INTAKE_SESSION_UNREADABLE", detail=str(exc))
    return out


def seed_answers(records, questions=None, *, run_dir=None, run_state_file=None,
                 target=None, client_dir=None, purpose_flow=None):
    """Import explicit prior client raw answers, never an assistant recap.

    Each row requires question_id, raw_answer and source_ref. Typed business
    facts (and an explicit dollar amount) can be preserved before PURPOSE is
    known. Menu choices require the exact pending renderer digest and cannot
    be old numeric selections. Unprovenanced legacy files are never imported.
    """
    first = process([], questions, run_dir=run_dir, run_state_file=run_state_file,
                    target=target, client_dir=client_dir, purpose_flow=purpose_flow)
    if first.get("outcome") == "error":
        return first
    path = _session_path(run_dir, run_state_file)
    with session_lock(str(path) + ".lock"):
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            base = questions or card.QUESTIONS
            answers, qs, _ = _active(state, base, client_dir)
            if not isinstance(records, list) or not records:
                return _result(state, path, answers, qs, "SEED_ANSWERS_REQUIRED", "waiting")
            if state.get("done"):
                return _result(state, path, answers, qs, "INTAKE_ALREADY_CONFIRMED", "waiting")
            candidates, seen = [], set()
            for row in records:
                if (not isinstance(row, dict) or row.get("source", "client") != "client" or
                        not isinstance(row.get("raw_answer"), str) or
                        not isinstance(row.get("source_ref"), str) or not row["source_ref"].strip()):
                    return _result(state, path, answers, qs, "SEED_PROVENANCE_REQUIRED", "waiting")
                qid, raw = row.get("question_id"), row["raw_answer"]
                if not isinstance(qid, str) or qid in seen:
                    return _result(state, path, answers, qs, "SEED_DUPLICATE_OR_UNKNOWN_QUESTION", "waiting")
                seen.add(qid)
                possible = [q for q in qs if q["id"] == qid]
                if len(possible) != 1:
                    return _result(state, path, answers, qs, "SEED_QUESTION_UNKNOWN", "waiting")
                q = possible[0]
                is_fact = q.get("free_text") or (qid == "spend" and raw.strip().startswith("$"))
                current = state["pending"]
                if not is_fact and (raw.strip().isdigit() or qid != current["id"] or
                                    row.get("question_digest") != current["digest"]):
                    return _result(state, path, answers, qs, "SEED_MENU_IDENTITY_REQUIRED", "waiting")
                parsed = _parse(raw, q)
                if not parsed or parsed.get("error"):
                    return _result(state, path, answers, qs, "INVALID_OPTION", "waiting")
                parsed["id"] = qid
                at = next(i for i, entry in enumerate(qs) if entry["id"] == qid)
                rendered = card.render_step(at + 1, qs)
                receipt = {"id": qid, "definition": q, "message": rendered}
                event = {"sequence": len(state["events"]) + len(candidates) + 1,
                         "raw_answer": raw, "source": "client", "source_ref": row["source_ref"],
                         "provenance_kind": "explicit_prior_client_answer", "at_utc": _now(),
                         "question_id": qid, "question_digest": _digest(receipt),
                         "rendered_question": rendered, "accepted": True,
                         "option": _option(q, parsed), "parsed": parsed}
                record = dict(event, definition_digest=_digest(q), question=copy.deepcopy(q))
                if qid == "model":
                    record["provider_identity"] = _provider_identity(parsed)
                prior = state["answer_records"].get(qid)
                if prior is not None and prior.get("raw_answer") != raw:
                    return _result(state, path, answers, qs, "SEED_CONFLICTS_WITH_SAVED_ANSWER", "waiting")
                if prior is None:
                    candidates.append(record)
            for record in candidates:
                state["events"].append({k: v for k, v in record.items()
                                        if k not in ("question", "definition_digest")})
                state["answer_records"][record["question_id"]] = record
            # Save imported facts before deriving a new pending question.
            _write(path, state)
            answers, qs, _ = _active(state, base, client_dir)
            _progress(state, answers, qs)
            state["pending"] = _pending(answers, qs, state.get("editing_question_id"))
            state["updated_at"] = _now()
            _write(path, state)
            return _result(state, path, answers, qs, "INTAKE_ANSWERS_SEEDED")
        except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
            return {"done": False, "answers": [], "message": "", "outcome": "error",
                    "reason_code": "INTAKE_SESSION_UNREADABLE", "detail": str(exc),
                    "session_path": str(path), "question_id": None, "question_digest": None,
                    "answered_count": 0, "total_count": 0}
