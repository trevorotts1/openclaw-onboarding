"""Shared durable card adapter for the factory and direct intake-card CLI.

All question text and option data come from intake_card. The adapter changes
transport and persistence only; intake_session owns answer validation.
"""
import importlib
import json
import os
import sys
import tempfile
from pathlib import Path

EXIT = {"ok": 0, "waiting": 2, "parked": 3, "rejected": 4, "error": 1}
SCHEMA = "blackceo.intake-session/cli/v1"


def _error(code, detail):
    return {"done": False, "answers": [], "outcome": "error",
            "reason_code": code, "message": code + ": " + detail,
            "question_id": None, "question_digest": None,
            "answered_count": 0, "total_count": None}


def _session_path(a):
    if getattr(a, "run_dir", ""):
        return Path(a.run_dir) / "control" / "intake-session.json"
    return Path(a.run_state_file).resolve().with_name("intake-session.json")


def _intro(a, purpose_flow, session):
    """Return (intro message or None, frozen flow).

    No pending question is recorded behind the intro: the first question is
    presented by the following no-reply invocation. The existing run-state
    document is preserved, including unrelated owner fields.
    """
    path_text = getattr(a, "run_state_file", "")
    if not path_text:
        return None, purpose_flow
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    with session.session_lock(path.with_name(path.name + ".intake-launch.lock")):
        state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if not isinstance(state, dict):
            raise ValueError("run state must be a JSON object")
        saved_flow = state.get("intake_purpose_flow")
        if saved_flow is not None:
            if not isinstance(saved_flow, bool):
                raise ValueError("saved intake flow must be boolean")
            if getattr(a, "purpose_flow", None) is None:
                purpose_flow = saved_flow
        if (getattr(a, "reply", []) or getattr(a, "seed_answers_file", None)
                or state.get("intro_shown") or _session_path(a).exists()):
            return None, purpose_flow
        from choice_card.intake_card.intro import INTRO
        state["intro_shown"] = True
        state["intake_purpose_flow"] = bool(purpose_flow)
        fd, tmp = tempfile.mkstemp(prefix=".intake-intro-", suffix=".json", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                json.dump(state, out, indent=2, sort_keys=True)
                out.write("\n")
                out.flush()
                os.fsync(out.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return INTRO, purpose_flow


def _emit(a, state, stdout):
    fmt = getattr(a, "format", "text")
    if fmt == "session-json":
        payload = dict(state, format="session-json", version=1, schema=SCHEMA)
        json.dump(payload, stdout, indent=2, sort_keys=True)
        stdout.write("\n")
    elif fmt == "text":
        message = state["message"]
        if state.get("outcome") == "error" and not message:
            message = state.get("reason_code", "INTAKE_SESSION_FAILED") + ": " + state.get("detail", "the intake state could not be read")
        stdout.write(message + "\n")
    elif fmt in ("openclaw-json", "telegram-json"):
        from choice_card.intake_card import intake_card as card
        send = card.openclaw_send_argv if fmt == "openclaw-json" else card.telegram_payload
        metadata = {key: state.get(key) for key in (
            "schema", "outcome", "reason_code", "question_id", "question_digest",
            "answered_count", "total_count", "session_path", "pending")}
        metadata["schema"] = SCHEMA
        json.dump({"done": state["done"],
                   "send": send(getattr(a, "target", ""), state["message"]),
                   "session": metadata}, stdout, indent=2, sort_keys=True)
        stdout.write("\n")
    else:
        raise ValueError("durable intake requires text or a session/send JSON format")
    return EXIT.get(state.get("outcome", "ok"), 1)


def run(a, questions=None, purpose_flow=None, stdout=None):
    """Render/process one durable CLI turn; never fall back to stateless replay."""
    stdout = sys.stdout if stdout is None else stdout
    if not (getattr(a, "run_dir", "") or getattr(a, "run_state_file", "")):
        return _emit(a, _error("INTAKE_RUN_REQUIRED", "provide --run-dir or --run-state-file"), stdout)
    try:
        session = importlib.import_module("choice_card.intake_card.intake_session")
    except (ImportError, AttributeError) as exc:
        return _emit(a, _error("INTAKE_SESSION_UNAVAILABLE", str(exc)), stdout)
    try:
        from choice_card.intake_card import intake_card as card
        if questions is None:
            questions = [card.spend_question(
                getattr(a, "price", None), getattr(a, "limit", None),
                getattr(a, "limit_from_brief", False)) if q["id"] == "spend" else q
                for q in card._with_saved_character(getattr(a, "client_dir", ""))]
        intro, purpose_flow = _intro(a, purpose_flow, session)
        if intro is not None:
            state = {"done": False, "answers": [], "outcome": "ok",
                     "reason_code": "INTAKE_INTRO", "message": intro,
                     "question_id": None, "question_digest": None,
                     "answered_count": 0, "total_count": None,
                     "session_path": str(_session_path(a)), "pending": None}
        else:
            # A default recomputed from the intro marker or other progress is
            # not an instruction to switch a session that already chose its flow.
            if _session_path(a).exists() and getattr(a, "purpose_flow", None) is None:
                purpose_flow = None
            common = dict(run_dir=getattr(a, "run_dir", "") or None,
                run_state_file=getattr(a, "run_state_file", "") or None,
                target=getattr(a, "target", "") or None,
                client_dir=getattr(a, "client_dir", "") or None,
                purpose_flow=purpose_flow)
            seed_file = getattr(a, "seed_answers_file", None)
            if seed_file:
                if getattr(a, "reply", []) or getattr(a, "reply_source", "client") != "client":
                    raise ValueError("seeded owner facts require their own explicit provenance and no simultaneous reply")
                records = json.loads(Path(seed_file).read_text(encoding="utf-8"))
                state = session.seed_answers(records, questions, **common)
            else:
                state = session.process(
                    getattr(a, "reply", []), questions, **common,
                    question_id=getattr(a, "question_id", None),
                    question_digest=getattr(a, "question_digest", None),
                    source=getattr(a, "reply_source", "client"),
                    source_ref=getattr(a, "answer_source_ref", None))
            if not isinstance(state, dict) or not isinstance(state.get("message"), str):
                raise ValueError("session returned no usable message")
            if not isinstance(state.get("done"), bool):
                raise ValueError("session returned no completion state")
            if state["done"] and (not isinstance(state.get("total_count"), int)
                    or state.get("answered_count") != state["total_count"]):
                raise ValueError("session completion count does not match the rendered card")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        state = _error("INTAKE_SESSION_FAILED", str(exc))
    return _emit(a, state, stdout)
