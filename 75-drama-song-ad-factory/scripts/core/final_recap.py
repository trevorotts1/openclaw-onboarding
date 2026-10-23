#!/usr/bin/env python3
"""final_recap.py: Gate 4 -- ONE final scene/music/cost recap + production Go.

v3.0 B7/B8. The video paid stage held on a model lock, the picture gate and the
onscreen gate, but nothing bound it to the approved soundtrack, the scene list,
the duration or the spend, so a run could be paid for with no final recap and no
operator Go. This is that ONE hold, and it cannot be opened by a flag:

  * the recap is ONE content-addressed file, ``control/final-recap.json``. Its
    ``measured`` block is READ from the run -- shot list, picked song and the
    digest of the picked file itself, the locked video model, the duration and
    the spend ledger's own projection -- never from caller-supplied strings;
  * ``recap_digest`` is the sha256 over the document minus that key, so an
    edited recap fails its own digest and refuses the stage;
  * the Go is ``control/production-go.json`` = {decision: "GO", operator,
    at_utc, recap_digest}. It records who, when and WHICH recap was approved;
    a Go naming any other digest unlocks nothing;
  * every missing measurement or malformed field is a typed REFUSAL that names
    what could not be measured. Nothing here writes a PASS for what it did not
    measure. stdlib only, read-only against the run.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import sys

SCHEMA = "blackceo.final-recap/v1"
GO_SCHEMA = "blackceo.production-go/v1"
RECAP_FILE = os.path.join("control", "final-recap.json")
GO_FILE = os.path.join("control", "production-go.json")

#: the typed refusals the video paid stage reads.
RECAP_MISSING = "FINAL_RECAP_MISSING"
RECAP_INCOMPLETE = "FINAL_RECAP_INCOMPLETE"
RECAP_UNMEASURABLE = "FINAL_RECAP_UNMEASURABLE"
RECAP_DIGEST_MISMATCH = "FINAL_RECAP_DIGEST_MISMATCH"
RECAP_STALE = "FINAL_RECAP_STALE"
GO_MISSING = "PRODUCTION_GO_MISSING"
GO_INVALID = "PRODUCTION_GO_INVALID"
GO_DIGEST_MISMATCH = "PRODUCTION_GO_DIGEST_MISMATCH"
BROKEN = "FINAL_RECAP_BROKEN"

_ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")

#: every measured field and the sub-keys the recap must carry for each.
_REQUIRED = {
    "scenes": ("count", "shot_ids", "duration_s"),
    "soundtrack": ("pick", "label", "sha256"),
    "model": ("video_model",),
    "spend": ("actual_cost", "committed_cost", "unknown_or_reserved_cost",
              "estimated_cost", "remaining_budget", "cost_projection", "currency"),
}


class RecapError(Exception):
    def __init__(self, code, detail):
        super().__init__("%s: %s" % (code, detail))
        self.code = code
        self.detail = detail


# -- reading the run ------------------------------------------------------

def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(path, doc):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _ro(db_path):
    return sqlite3.connect("file:%s?mode=ro" % db_path, uri=True, timeout=10)


def recap_path(run_dir):
    return os.path.join(run_dir, RECAP_FILE)


def go_path(run_dir):
    return os.path.join(run_dir, GO_FILE)


def recap_digest(doc):
    """sha256 over the document itself minus ``recap_digest``."""
    body = {k: v for k, v in (doc or {}).items() if k != "recap_digest"}
    return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


def _scene_rows(run_dir):
    """The storyboard's shot list, or None when it carries no usable scenes."""
    doc = _read(os.path.join(run_dir, "storyboard", "shot-list.json"))
    shots = doc.get("shots") if isinstance(doc, dict) else doc
    if not isinstance(shots, list) or not shots:
        return None
    rows = []
    for s in shots:
        if not isinstance(s, dict):
            return None
        if not isinstance(s.get("shot_id"), str) or not s["shot_id"].strip():
            return None
        if not (_num(s.get("song_start")) and _num(s.get("song_end"))
                and s["song_start"] < s["song_end"]):
            return None
        rows.append(s)
    rows.sort(key=lambda s: (float(s["song_start"]), float(s["song_end"])))
    return rows


def _selected_soundtrack(run_dir):
    """The client's pick, verified against the picked FILE's own digest."""
    pick = _read(os.path.join(run_dir, "song-choices", "pick.json"))
    if not isinstance(pick, dict):
        return None
    claimed = str(pick.get("sha256") or "").strip().lower()
    if not _HEX64.match(claimed):
        return None
    try:
        with open(os.path.join(run_dir, "music", "picked-song.mp3"), "rb") as f:
            got = hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None
    if got != claimed:          # the picked file changed under the recorded pick
        return None
    if not isinstance(pick.get("pick"), int) or isinstance(pick.get("pick"), bool):
        return None
    return {"pick": pick["pick"], "label": str(pick.get("label") or ""),
            "sha256": got}


def _run_ids(db_path, table):
    """Every run id a store holds (state store: ``stages``; ledger: ``runs``);
    [] when it cannot be read."""
    if not os.path.isfile(db_path):
        return []
    try:
        con = _ro(db_path)
        try:
            return [r[0] for r in con.execute(
                "SELECT DISTINCT run_id FROM %s" % table)]
        finally:
            con.close()
    except sqlite3.Error:
        return []


def _resolve_run_id(ids, run_dir):
    """The same resolution `factory.next` uses: exactly one id answers for the
    store, else the run dir's own name. None = the store cannot say."""
    if len(ids) == 1:
        return ids[0]
    base = os.path.basename(os.path.abspath(run_dir)) or "run"
    return base if base in ids else None


def _locked_model(run_dir, run_id):
    db = os.path.join(run_dir, "control", "state.sqlite3")
    if not run_id or not os.path.isfile(db):
        return None
    core = os.path.dirname(os.path.abspath(__file__))
    if core not in sys.path:
        sys.path.insert(0, core)
    try:
        from kie_dispatch import model_lock as ML  # noqa: PLC0415
    except Exception:                                # noqa: BLE001
        return None
    return ML.read_locked_model(db, run_id)


def _spend(run_dir, run_id):
    """The ledger's own projection: what is spent, reserved, estimated and
    left. Read-only; None when the ledger cannot answer for this run."""
    db = os.path.join(run_dir, "spend.sqlite3")
    if not os.path.isfile(db):
        return None
    try:
        import spend_ledger as sl  # noqa: PLC0415
    except Exception:                                # noqa: BLE001
        return None
    ids = _run_ids(db, "runs")
    rid = run_id if run_id in ids else _resolve_run_id(ids, run_dir)
    if rid is None:
        return None
    got = sl.summary(db, rid)
    if got.get("outcome") != "ok":
        return None
    ev = got.get("evidence") or {}
    out = {k: ev.get(k) for k in
           ("actual_cost", "committed_cost", "unknown_or_reserved_cost",
            "estimated_cost", "remaining_budget", "currency")}
    if not all(out[k] is not None for k in
               ("actual_cost", "committed_cost", "unknown_or_reserved_cost",
                "estimated_cost", "remaining_budget")):
        return None
    out["cost_projection"] = (int(out["actual_cost"]) + int(out["committed_cost"])
                              + int(out["unknown_or_reserved_cost"])
                              + int(out["estimated_cost"]))
    out["generation_calls"] = (ev.get("counts") or {}).get("number_of_generation_calls")
    out["retry_cost"] = ev.get("retry_cost")
    return out


def measure(run_dir):
    """(measured, missing). ``missing`` names every field that could not be
    measured from the run itself; nothing is defaulted or invented."""
    run_dir = str(run_dir)
    run_id = _resolve_run_id(
        _run_ids(os.path.join(run_dir, "control", "state.sqlite3"), "stages"),
        run_dir)
    measured, missing = {}, []

    rows = _scene_rows(run_dir)
    if rows is None:
        missing.append("scenes (storyboard/shot-list.json holds no usable shots)")
    else:
        measured["scenes"] = {
            "count": len(rows),
            "shot_ids": [s["shot_id"] for s in rows],
            "duration_s": round(max(float(s["song_end"]) for s in rows), 3)}
        measured["duration_s"] = measured["scenes"]["duration_s"]

    track = _selected_soundtrack(run_dir)
    if track is None:
        missing.append("soundtrack (song-choices/pick.json or music/picked-song.mp3 "
                       "is absent or no longer matches its recorded digest)")
    else:
        measured["soundtrack"] = track

    model = _locked_model(run_dir, run_id)
    if not model:
        missing.append("model (no locked video model in the run's state store)")
    else:
        measured["model"] = {"video_model": str(model)}

    spend = _spend(run_dir, run_id)
    if spend is None:
        missing.append("spend (spend.sqlite3 cannot answer for this run)")
    else:
        measured["spend"] = spend

    method = _read(os.path.join(run_dir, "control", "method.json"))
    chosen = method.get("chosen_length_s") if isinstance(method, dict) else None
    if isinstance(chosen, int) and not isinstance(chosen, bool):
        measured["chosen_length_s"] = chosen
    return measured, missing


def build(run_dir):
    """Measure the run and write the ONE recap. Raises RecapError when any
    measurement is missing -- a partial recap is never written."""
    run_dir = str(run_dir)
    measured, missing = measure(run_dir)
    if missing:
        raise RecapError(RECAP_UNMEASURABLE,
                         "the final recap cannot be built; nothing was written. "
                         "Missing measurements: " + "; ".join(missing))
    import datetime as _dt
    doc = {"schema": SCHEMA,
           "run_id": os.path.basename(os.path.abspath(run_dir)) or "run",
           "generated_at_utc": _dt.datetime.now(_dt.timezone.utc).strftime(
               "%Y-%m-%dT%H:%M:%SZ"),
           "measured": measured}
    doc["recap_digest"] = recap_digest(doc)
    _write(recap_path(run_dir), doc)
    return doc


# -- validating, Go, and the hold -----------------------------------------

def _recap_problems(doc):
    if not isinstance(doc, dict):
        return ["the recap is not a JSON object"]
    out = []
    if doc.get("schema") != SCHEMA:
        out.append("schema is %r, not %r" % (doc.get("schema"), SCHEMA))
    m = doc.get("measured")
    if not isinstance(m, dict):
        return out + ["measured is %s, not a mapping" % type(m).__name__]
    for field, keys in _REQUIRED.items():
        block = m.get(field)
        if not isinstance(block, dict):
            out.append("measured.%s is missing" % field)
            continue
        for k in keys:
            v = block.get(k)
            if v is None or (isinstance(v, str) and not v.strip()) \
                    or (isinstance(v, (list, dict)) and not v):
                out.append("measured.%s.%s is missing" % (field, k))
    sc = m.get("scenes")
    if isinstance(sc, dict) and isinstance(sc.get("count"), int) and sc["count"] < 1:
        out.append("measured.scenes.count is %r; a recap with no scenes is not a recap"
                   % sc.get("count"))
    dig = doc.get("recap_digest")
    if not isinstance(dig, str) or not _HEX64.match(dig):
        out.append("digest recap_digest is not a lowercase sha256")
    elif dig != recap_digest(doc):
        out.append("digest recap_digest does not match the recap's own contents "
                   "(it was changed after it was built)")
    return out


def go_problems(go):
    """[] = admissible. Never returns an operator or digest it did not verify."""
    if not isinstance(go, dict):
        return ["the Go is not a JSON object"]
    out = []
    if go.get("schema") != GO_SCHEMA:
        out.append("schema is %r, not %r" % (go.get("schema"), GO_SCHEMA))
    if str(go.get("decision") or "").strip().upper() != "GO":
        out.append("decision is %r, not GO" % (go.get("decision"),))
    who = go.get("operator")
    if not isinstance(who, str) or len(who.strip()) < 2:
        out.append("operator must name WHO is going; %r is not a person" % (who,))
    when = go.get("at_utc")
    if not isinstance(when, str) or not _ISO_Z.match(when.strip()):
        out.append("at_utc must be an ISO 8601 UTC stamp like 2026-10-22T12:00:00Z")
    dig = go.get("recap_digest")
    if not isinstance(dig, str) or not _HEX64.match(dig.strip().lower()):
        out.append("recap_digest must be the lowercase sha256 of the recap approved")
    return out


def read_recap(run_dir):
    return _read(recap_path(run_dir))


def read_go(run_dir):
    return _read(go_path(run_dir))


def record_go(run_dir, go):
    """Validate and record the operator Go against the CURRENT recap digest.
    Raises RecapError on anything it cannot verify; writes nothing then."""
    run_dir = str(run_dir)
    doc = read_recap(run_dir)
    if doc is None:
        raise RecapError(RECAP_MISSING, "no %s to approve; build it first"
                         % RECAP_FILE)
    probs = _recap_problems(doc)
    if probs:
        raise RecapError(RECAP_INCOMPLETE, "; ".join(probs))
    gprobs = go_problems(go)
    if gprobs:
        raise RecapError(GO_INVALID, "; ".join(gprobs))
    claimed = go["recap_digest"].strip().lower()
    if claimed != doc["recap_digest"]:
        raise RecapError(GO_DIGEST_MISMATCH,
                         "the Go approves %s but the recap on disk is %s; re-read "
                         "the recap and approve the digest you were actually shown"
                         % (claimed[:12], doc["recap_digest"][:12]))
    import datetime as _dt
    out = dict(go, decision="GO", operator=go["operator"].strip(),
               at_utc=go["at_utc"].strip(), recap_digest=claimed,
               recorded_at_utc=_dt.datetime.now(_dt.timezone.utc).strftime(
                   "%Y-%m-%dT%H:%M:%SZ"))
    _write(go_path(run_dir), out)
    return out


def _refuse(code, detail):
    return {"reason_code": code, "detail": detail,
            "next_action": _NEXT.get(code, ""),
            "causal_chain": [{"stage": "final_recap", "reason_code": code,
                              "detail": detail}]}


_NEXT = {
    RECAP_MISSING: "Build the ONE final recap (`factory.py final-recap --run-dir <dir>`); "
                   "it reads the scenes, soundtrack, model, duration and spend off the run.",
    RECAP_INCOMPLETE: "The recap is partial or was edited after it was built. Rebuild it "
                      "from the run, then have the operator approve THAT digest.",
    RECAP_UNMEASURABLE: "A measurement is missing (named in the detail). Produce it, then "
                        "rebuild the recap -- nothing was invented to fill the gap.",
    RECAP_DIGEST_MISMATCH: "The recap's contents changed after it was built. Rebuild it and "
                           "take a fresh Go; an edited recap is never approved.",
    RECAP_STALE: "The run changed after the recap was built, so that Go approves numbers that "
                 "no longer describe it. Rebuild the recap and take a fresh Go.",
    GO_MISSING: "Show the operator the recap, then record their Go: "
                "`factory.py production-go --run-dir <dir> --go <path>` with "
                "{decision: GO, operator, at_utc, recap_digest}.",
    GO_INVALID: "The Go names no operator, no timestamp or no recap digest. A Go is a "
                "person, a time and the exact digest they approved.",
    GO_DIGEST_MISMATCH: "That Go approves a different recap. Re-show the current recap and "
                        "record a Go for its digest.",
    BROKEN: "The final-recap gate failed unexpectedly; it stays CLOSED. Inspect the run's "
            "control/final-recap.json and production-go.json.",
}


def hold(run_dir):
    """None when the video paid stage may run; else the typed refusal.

    ONE implementation, read by `factory.py next` where the video paid stage
    is handed out -- not re-derived at a second site."""
    run_dir = str(run_dir)
    try:
        if not os.path.exists(recap_path(run_dir)):
            return _refuse(RECAP_MISSING,
                           "no %s: the video stage is a paid boundary and needs ONE "
                           "final scene/music/cost recap before any video spend"
                           % RECAP_FILE)
        doc = read_recap(run_dir)
        probs = _recap_problems(doc)
        if probs:
            code = (RECAP_DIGEST_MISMATCH
                    if any(p.startswith("digest ") for p in probs)
                    else RECAP_INCOMPLETE)
            return _refuse(code, "; ".join(probs))
        # The Go approves what the operator was SHOWN. Re-measure the run now:
        # a recap whose measured values no longer describe it is stale, and a
        # Go bound to a stale digest approves numbers that are already wrong.
        now, missing = measure(run_dir)
        if missing:
            return _refuse(RECAP_UNMEASURABLE,
                           "the recap can no longer be re-measured: "
                           + "; ".join(missing))
        was = doc["measured"]
        moved = [k for k in sorted(set(now) | set(was))
                 if _canonical(now.get(k)) != _canonical(was.get(k))]
        if moved:
            return _refuse(RECAP_STALE,
                           "the run changed after the recap was built (%s); the "
                           "recap's digest %s no longer describes it"
                           % (", ".join(moved), doc["recap_digest"][:12]))
        gpath = go_path(run_dir)
        if not os.path.exists(gpath):
            return _refuse(GO_MISSING,
                           "the recap is complete (digest %s) but no %s records the "
                           "operator's Go" % (doc["recap_digest"][:12], GO_FILE))
        go = read_go(run_dir)
        gprobs = go_problems(go)
        if gprobs:
            return _refuse(GO_INVALID, "; ".join(gprobs))
        claimed = go["recap_digest"].strip().lower()
        if claimed != doc["recap_digest"]:
            return _refuse(GO_DIGEST_MISMATCH,
                           "the Go approves recap %s; the recap on disk is %s"
                           % (claimed[:12], doc["recap_digest"][:12]))
        return None
    except Exception as exc:            # noqa: BLE001 - a broken gate never opens
        return _refuse(BROKEN, repr(exc)[:200])


def cli_build(run_dir):
    """`factory.py final-recap`: build and print the measured recap."""
    doc = build(run_dir)
    return {"outcome": "ok", "path": recap_path(str(run_dir)), "recap": doc}


def cli_go(run_dir, go_doc):
    """`factory.py production-go`: record the operator's Go."""
    out = record_go(run_dir, go_doc)
    return {"outcome": "ok", "path": go_path(str(run_dir)), "go": out}
