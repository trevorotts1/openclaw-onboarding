"""Write $RUN/card-answers.json when the client confirms the intake card recap.
stage.run_stage reads it. Kept separate from the song-approval and storyboard
recorders so the branches merge cleanly.

D17 (saved-answer identity): a saved answer is identified by its STABLE
QUESTION ID together with a schema version -- never by its position in a
question list that may have been reordered since the answer was saved.
Reordering the questions must not turn a saved Yes into a No.

Shapes:
    v2 (this writer): {"schema_version": 2, "answers": [{"id","n","text",...}, ...]}
    v1 (legacy writer): [{"id","n","text",...}, ...]

Legacy lists are migrated by their stored IDs (see ``migrate``). Rows without
a stored ID, an unreadable file and a wrong-shaped file are all one explicit
UNKNOWN state -- never "approval not asked", never permission.

External readers (ready_post_kit.answer_map, delivery_package.run_inputs)
already accept both shapes and map rows by id.

Stdlib only.
"""
import json
import os

ANSWERS = "card-answers.json"
SCHEMA_VERSION = 2

OK = "ok"
MISSING = "missing"
CORRUPT = "corrupt"

YES = "yes"
NO = "no"
UNKNOWN = "unknown"


def _state(state, rows=None, by_id=None, schema_version=None, detail=""):
    return {"state": state, "rows": rows or [], "by_id": by_id or {},
            "schema_version": schema_version, "detail": detail}


def pair_rows(answers, questions):
    """Attach the producing question's id to rows that carry none. This is the
    ORIGINAL conversation pairing (the list and the question list it was built
    from) -- never a re-read of saved rows through a newer question order: saved
    files always carry stored ids and are read strictly by them. None when a row
    cannot be paired: that is an explicit unknown, never a guess."""
    rows = []
    for i, a in enumerate(answers):
        row = dict(a)
        if not row.get("id"):
            q = questions[i] if questions and i < len(questions) else None
            if not (isinstance(q, dict) and q.get("id")):
                return None
            row["id"] = q["id"]
        rows.append(row)
    return rows


def write(run_dir, answers, questions):
    """answers: the `answers` list of intake_card.conversation; each entry gets
    its question id (its own stored id, else the id of the question that produced
    it in THIS conversation)."""
    rows = pair_rows(answers, questions)
    if rows is None:
        raise ValueError("an answer carries no question id")
    os.makedirs(run_dir, exist_ok=True)
    path = os.path.join(run_dir, ANSWERS)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"schema_version": SCHEMA_VERSION, "answers": rows}, f, indent=2)
    os.replace(tmp, path)
    return path


def normalize(raw):
    """Raw JSON -> the typed state. Rows are matched by stored id only. A row
    without a stored id is kept but never decides anything (its question reads
    as UNKNOWN) -- position is never a substitute for identity."""
    if isinstance(raw, dict):
        rows, ver = raw.get("answers"), raw.get("schema_version")
    elif isinstance(raw, list):
        rows, ver = raw, 1                      # legacy list of id-carrying rows
    else:
        return _state(CORRUPT, detail="card answers are not a list or object")
    if not isinstance(rows, list):
        return _state(CORRUPT, detail="card answers carry no answer list")
    by_id, unmapped = {}, 0
    for r in rows:
        if not isinstance(r, dict):
            return _state(CORRUPT, rows=rows, schema_version=ver,
                          detail="a saved answer row is not an object")
        if not r.get("id") or "n" not in r:
            unmapped += 1
            continue
        if r["id"] in by_id:
            return _state(CORRUPT, rows=rows, schema_version=ver,
                          detail="duplicate stored question id %r" % r["id"])
        by_id[r["id"]] = r
    st = _state(OK, rows=rows, by_id=by_id,
                schema_version=ver if isinstance(ver, int) else 1)
    st["unmapped"] = unmapped
    return st


def load(run_dir):
    """The run's saved answers: MISSING / CORRUPT / OK, never a guess."""
    path = os.path.join(run_dir, ANSWERS)
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        return _state(MISSING, detail="card-answers.json is missing")
    except (OSError, ValueError) as e:
        return _state(CORRUPT, detail="card-answers.json is unreadable: %s" % e)
    return normalize(raw)


def decision(st, question_id):
    """The saved decision for one question, read BY STORED ID.

    {"state": YES|NO|UNKNOWN, ...} -- YES/NO from the stored row, UNKNOWN when
    the answers are missing, corrupt, or simply do not record this question's
    decision (no row, or a row with no stored id). UNKNOWN is never permission.
    """
    if not isinstance(st, dict) or st.get("state") != OK:
        detail = st.get("detail") if isinstance(st, dict) else "card answers unreadable"
        return {"state": UNKNOWN,
                "detail": detail or "the saved card answers are missing or corrupt"}
    row = st["by_id"].get(question_id)
    if row is None:
        return {"state": UNKNOWN,
                "detail": "the saved card answers record no decision for question %r; "
                          "that is an explicit unknown, not permission" % question_id}
    return {"state": YES if row.get("n") == 1 else NO, "row": row}


def repair_decision(run_dir, question_id, n, text=""):
    """Recovery for an explicit unknown: record the question's answer by STABLE
    ID on top of whatever rows survive (legacy rows are migrated by their stored
    ids; rows without ids are dropped, never re-read positionally)."""
    st = load(run_dir)
    rows = [dict(r) for r in st["rows"]] if st["state"] == OK else []
    rows = [r for r in rows if r.get("id")]
    rows = [r for r in rows if r["id"] != question_id]
    rows.append({"id": question_id, "n": int(n), "text": text, "value": None})
    os.makedirs(run_dir, exist_ok=True)
    path = os.path.join(run_dir, ANSWERS)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"schema_version": SCHEMA_VERSION, "answers": rows}, f, indent=2)
    os.replace(tmp, path)
    return load(run_dir)


def migrate(run_dir):
    """Rewrite a legacy v1 list in place as the versioned v2 envelope, keyed by
    the rows' own stored ids. Idempotent; refuses (and rewrites nothing) when the
    file cannot be read by stored id."""
    st = load(run_dir)
    if st["state"] != OK or st["schema_version"] == SCHEMA_VERSION:
        return st
    path = os.path.join(run_dir, ANSWERS)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"schema_version": SCHEMA_VERSION, "answers": st["rows"]}, f, indent=2)
    os.replace(tmp, path)
    return load(run_dir)
