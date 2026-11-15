#!/usr/bin/env python3
"""stage.py: the continuity-bible STAGE runner (S75-W06-U2). Stdlib only.

The continuity-bible stage gate rides over the agent-authored Character DNA,
product DNA and style-bible records (``character_continuity/`` and
``product_style_bible/`` stay import-only libraries). Before this module the
stage had no executable of its own: the runbook handed out
``qc_gate.py evaluate ... --required <required-checks>`` — an instruction
string with a placeholder a human had to invent — and the row only moved by
separate manual actions (finding D08). This file is the stage's real
execution entrypoint and its advancement contract (findings D08, D33):

* ``load_records`` / ``load_makers`` — TYPED readers. ``continuity/
  qc-records.json`` is a LIST of qc-schema records; a legacy dict wrapper
  ({"records": [...]}) migrates with a note; any other shape is an explicit
  bad state and can never pass. The dict-only-reader bug class (a reader
  that returns nothing for a list) cannot live here.
* ``REQUIRED_CHECKS`` — the required evidence DECLARED independently of
  whatever records arrive. Missing evidence fails the gate (MISSING_QC); it
  never shrinks the required set and the set is never empty.
* ``evaluate`` — the qc_gate stage gate over those readers, always against
  the declared set.
* ``proven`` — the registry reconciler predicate, same contract as
  factory's ``_RECONCILIERS`` entries; ``register(registry)`` wires it in.
* ``seal`` — the signed step gate over the FINISHED bible (finding S75-016):
  the records ``character_approval`` writes (``character/bible.json`` and the
  approved ``character/approval.json``) plus this stage's own QC records. Two
  small hand-written files in ``continuity/`` no longer seal anything.
* ``advance`` — the executable advancement: gate PASS **and** the step gate's
  seal move the continuity-bible row through state_store's guarded transitions
  to COMPLETE in one call (no separate manual registration), and report the
  seven downstream stages' rows (storyboard, image-keyframes,
  video-generation, qc-retakes, assembly, final-qc, delivery) so their
  advancement is real, not just storyboard eligibility. A refused seal is
  ``{"outcome": "not-proven"}`` with the gate's own reason — never a
  transition and never an invented pass.
* ``main`` — the CLI the stage-runbook registry row points at:
  ``python3 scripts/core/character_continuity/stage.py advance --run-dir
  "$RUN" --run-id "$RUN_ID"``.

Continuity-bible therefore advances through the registry's executable path
— the runbook row ``factory.py next`` hands out and the reconciler the
registry runs — never through a separate manual action.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_CORE = os.path.dirname(_HERE)                  # .../core
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

STAGE = "continuity-bible"
OWNER = "continuity-bible"
SCHEMA_VERSION = "1.0.0"

#: Independently declared required evidence for this stage's gate (D33:
#: "reconcile from independently declared required evidence, not whatever
#: records are present"). qc-schema check names; NEVER derived from the
#: records that happen to arrive, never empty when evidence is missing.
REQUIRED_CHECKS = ("continuity",)

#: The seven downstream stages whose real advancement continuity-bible must
#: unlock (Skill 75 section 8.6: "a continuity fix that merely exposes
#: storyboard eligibility cannot close the acceptance row").
DOWNSTREAM_STAGES = ("storyboard", "image-keyframes", "video-generation",
                     "qc-retakes", "assembly", "final-qc", "delivery")

#: The files a FINISHED continuity bible consists of, as its own writers write
#: them: ``character_approval.save_bible`` -> ``character/bible.json``,
#: ``character_approval.approve`` -> ``character/approval.json`` (the versioned
#: approval event, status "approved"), and this stage's QC records under
#: ``continuity/``. ``step_gate/stage_contracts.json`` declares exactly this
#: set; the test holds the two lists together so they cannot drift.
CONTRACT_ARTIFACTS = ("character/bible.json", "character/approval.json",
                      "continuity/qc-records.json", "continuity/makers.json")


class StageError(Exception):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def _p(run_dir, *parts):
    return os.path.join(run_dir, *parts)


def _read_json(path):
    """(doc, note): raw JSON read with an explicit note. The TYPE of the
    document is decided by the typed readers below, never here."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f), "ok"
    except FileNotFoundError:
        return None, "missing"
    except (OSError, ValueError):
        return None, "corrupt"


def load_records(run_dir):
    """(records, note) for ``continuity/qc-records.json``.

    The file is a LIST of qc-schema records. Legacy migration: a dict that
    wraps the list under "records" is unwrapped (``migrated:dict-wrapper``).
    A dict without that key, any other type, or corrupt JSON is an explicit
    bad state returning (None, note) — a bad read never becomes an empty
    pass and never coerces a dict to a list.
    """
    doc, note = _read_json(_p(run_dir, "continuity", "qc-records.json"))
    if note != "ok":
        return None, "records-%s" % note
    if isinstance(doc, list):
        return doc, "ok"
    if isinstance(doc, dict) and isinstance(doc.get("records"), list):
        return doc["records"], "migrated:dict-wrapper"
    return None, "records-bad-shape:%s" % type(doc).__name__


def load_makers(run_dir):
    """(makers, note) for ``continuity/makers.json`` (check_id -> maker).
    Missing = {} (the gate then fails MAKER_UNKNOWN — fail closed, never
    invented); corrupt or non-dict = explicit bad state."""
    doc, note = _read_json(_p(run_dir, "continuity", "makers.json"))
    if note == "missing":
        return {}, "makers-missing"
    if note != "ok":
        return None, "makers-%s" % note
    if not isinstance(doc, dict):
        return None, "makers-bad-shape:%s" % type(doc).__name__
    return doc, "ok"


def _run_id(run_dir, run_id):
    return str(run_id or os.path.basename(os.path.abspath(run_dir)) or "run")


def evaluate(run_dir, run_id=""):
    """The continuity-bible stage gate: typed readers + qc_gate.evaluate
    against REQUIRED_CHECKS. Returns the gate verdict plus reader notes.
    Nothing here invents a gate: an unreadable record set is BLOCKED with
    the reader's own reason, never PASS."""
    records, rec_note = load_records(run_dir)
    makers, mk_note = load_makers(run_dir)
    rid = _run_id(run_dir, run_id)
    if records is None:
        return {"gate": "BLOCKED", "reason_code": rec_note.split(":")[0].upper(),
                "failures": [], "readers": {"records": rec_note, "makers": mk_note},
                "required": list(REQUIRED_CHECKS), "run_id": rid, "stage": STAGE}
    if makers is None:
        return {"gate": "BLOCKED", "reason_code": mk_note.split(":")[0].upper(),
                "failures": [], "readers": {"records": rec_note, "makers": mk_note},
                "required": list(REQUIRED_CHECKS), "run_id": rid, "stage": STAGE}
    import qc_gate                                   # noqa: PLC0415
    res = qc_gate.evaluate(rid, STAGE, records, makers, list(REQUIRED_CHECKS))
    return dict(res, readers={"records": rec_note, "makers": mk_note},
                required=list(REQUIRED_CHECKS), run_id=rid, stage=STAGE)


def proven(run_dir, run_id=""):
    """(proven, evidence): the registry reconciler predicate — the same
    contract as factory's ``_RECONCILIERS`` entries. Proven only when the
    stage's OWN gate evaluates PASS on the declared required evidence; a
    missing check fails rather than disappearing from the requirement."""
    res = evaluate(run_dir, run_id)
    ev = {"artifacts": list(CONTRACT_ARTIFACTS),
          "gate": res.get("gate"), "reason_code": res.get("reason_code"),
          "required": list(REQUIRED_CHECKS), "readers": res.get("readers")}
    return res.get("gate") == "PASS", ev


def register(registry):
    """Wire this stage's reconciler into a stage registry dict — factory's
    ``_RECONCILIERS`` on current main, the published 12-stage registry when
    it lands. Returns the registry (one call, idempotent)."""
    registry["continuity-bible"] = proven
    return registry


_STEP_GATE = None


def step_gate_module():
    """The step gate MODULE (``scripts/core/step_gate/step_gate.py``).

    Loaded from its own file: ``scripts/core/step_gate/`` is a directory whose
    ``__init__.py`` is empty, so a plain ``import step_gate`` binds the package
    and finds none of the gate's functions. The contract file sits beside the
    module, so the gate's own default contract path resolves correctly.
    """
    global _STEP_GATE
    if _STEP_GATE is None:
        import importlib.util                          # noqa: PLC0415
        path = os.path.join(_CORE, "step_gate", "step_gate.py")
        spec = importlib.util.spec_from_file_location("step_gate_module", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _STEP_GATE = mod
    return _STEP_GATE


def _seal_pair(records, makers):
    """(maker, checker) for the declared check, or (None, None).

    The maker is the identity the records' sidecar names; the checker is the
    reviewer the record itself names. The step gate refuses a pair that is the
    same identity, so a second-hand note can never be its own check.
    """
    for rec in records or []:
        if not isinstance(rec, dict) or rec.get("check") not in REQUIRED_CHECKS:
            continue
        reviewer = rec.get("reviewer")
        maker = (makers or {}).get(rec.get("check_id"))
        checker = reviewer.get("identity") if isinstance(reviewer, dict) else None
        if maker and checker:
            return str(maker), str(checker)
    return None, None


def seal(run_dir, records, makers, contract=None):
    """(seal_doc, refusal): the signed step gate over the FINISHED bible.

    The gate's own ``init`` and ``open`` run first when they are absent —
    ``open`` still refuses without the previous stage's seal, so this call can
    never shorten the chain. The seal re-reads every artifact the contract
    declares for this stage (``CONTRACT_ARTIFACTS``) and refuses when one is
    missing, empty, a placeholder or unapproved. A refusal comes back as
    ``{"reason_code", "detail"}`` in the gate's own words.
    """
    SG = step_gate_module()
    try:
        doc = SG.load_contract(contract)
        maker, checker = _seal_pair(records, makers)
        if not maker or not checker:
            raise SG.Refused(
                "MAKER_UNKNOWN",
                "the %s records name no maker/reviewer pair to seal with" % STAGE)
        if not os.path.exists(SG.key_path(run_dir)):
            SG.cmd_init(run_dir)
        SG.cmd_open(run_dir, STAGE, doc)
        return SG.cmd_seal(run_dir, STAGE, maker, checker, doc), None
    except SG.Refused as exc:
        return None, {"reason_code": exc.code, "detail": exc.detail}


def _store(run_dir):
    import state_store                              # noqa: PLC0415
    db = _p(run_dir, "control", "state.sqlite3")
    if not os.path.exists(db):
        return None, None
    st = state_store.Store(db)
    ids = [r[0] for r in st.con.execute("SELECT DISTINCT run_id FROM stages")]
    if len(ids) == 1:
        return st, ids[0]
    rid = os.path.basename(os.path.abspath(run_dir)) or "run"
    if rid in ids:
        return st, rid
    st.close()
    return None, None


def _entrypoints():
    """{stage: runbook command} for the seven, reused from the registry's
    runbook rows (factory._runbook_rows) — never re-derived. Guarded: a box
    without factory loses this one data line, never the step."""
    out = {}
    try:
        fp = os.path.join(_CORE, "intake_preflight")
        if fp not in sys.path:
            sys.path.insert(0, fp)
        import factory as F                         # noqa: PLC0415
        runbook, _path = F._runbook_rows()
        for stage in DOWNSTREAM_STAGES:
            out[stage] = (runbook.get(stage) or {}).get("command")
    except Exception:                               # noqa: BLE001
        pass
    return out


def _downstream_rows(st, rid):
    eps = _entrypoints()
    out = {}
    for stage in DOWNSTREAM_STAGES:
        try:
            row = st.get(rid, stage)
            out[stage] = {"state": row["state"], "owner": row["owner"],
                          "entrypoint": eps.get(stage)}
        except Exception as exc:                    # noqa: BLE001
            out[stage] = {"state": "UNKNOWN", "error": str(exc)[:120],
                          "entrypoint": eps.get(stage)}
    return out


def downstream_status(run_dir, run_id=None):
    """The seven downstream stages: row state plus the registry entrypoint
    each one advances through. Proof surface for real downstream
    advancement."""
    st, rid = _store(run_dir)
    rows = _downstream_rows(st, rid) if st else {}
    if st:
        st.close()
    if not rows:
        eps = _entrypoints()
        rows = {stage: {"state": "UNKNOWN", "entrypoint": eps.get(stage)}
                for stage in DOWNSTREAM_STAGES}
    return rows


def advance(run_dir, run_id=None, owner=OWNER, contract=None):
    """The executable advancement (the registry's entrypoint action): run the
    gate, SEAL the finished bible through the step gate, and only then move the
    continuity-bible row to COMPLETE through state_store's guarded transitions
    in ONE call. A run holding only its QC records is refused as
    ``{"outcome": "not-proven"}`` carrying the gate's own reason, so the two
    small files the finding named can never complete the stage. Returns the
    outcome, the gate evidence and the seven downstream stages' rows."""
    st, srid = _store(run_dir)
    rid = srid or _run_id(run_dir, run_id)
    ok, ev = proven(run_dir, rid)
    if not ok:
        if st is not None:
            st.close()
        return {"outcome": "not-proven", "stage": STAGE, "run_id": rid,
                "evidence": ev, "downstream": downstream_status(run_dir, rid)}
    records, _rec_note = load_records(run_dir)
    makers, _mk_note = load_makers(run_dir)
    seal_doc, refusal = seal(run_dir, records, makers, contract)
    if seal_doc is None:
        if st is not None:
            st.close()
        return {"outcome": "not-proven", "stage": STAGE, "run_id": rid,
                "reason_code": refusal["reason_code"], "detail": refusal["detail"],
                "evidence": ev, "downstream": downstream_status(run_dir, rid)}
    ev = dict(ev, sealed=[row["path"] for row in seal_doc.get("artifacts") or []])
    if st is None:
        return {"outcome": "no-store", "stage": STAGE, "run_id": rid,
                "evidence": ev, "downstream": downstream_status(run_dir, rid)}
    import state_store                              # noqa: PLC0415
    try:
        try:
            row = st.get(rid, STAGE)
        except state_store.StoreError:
            st.init_run(rid, [STAGE])
            row = st.get(rid, STAGE)
        if row["state"] == "COMPLETE":
            return {"outcome": "already-complete", "stage": STAGE, "run_id": rid,
                    "row": row, "evidence": ev,
                    "downstream": _downstream_rows(st, rid)}
        now = time.time()
        if row["owner"] and now < (row["lease_expires"] or 0) \
                and row["owner"] != owner:
            return {"outcome": "lease-held", "stage": STAGE, "run_id": rid,
                    "row": row, "evidence": ev,
                    "downstream": _downstream_rows(st, rid)}
        if row["state"] == "NOT_STARTED":
            row = st.transition(rid, STAGE, "READY", owner,
                                expected_version=row["version"])
        if row["state"] != "COMPLETE":
            row = st.claim(rid, STAGE, owner, lease_s=60,
                           expected_version=row["version"])
            row = st.transition(rid, STAGE, "COMPLETE", owner,
                                expected_version=row["version"],
                                reason="continuity-bible gate PASS and step-gate "
                                       "seal over the declared artifacts")
        return {"outcome": "advanced", "stage": STAGE, "run_id": rid,
                "row": row, "evidence": ev,
                "downstream": _downstream_rows(st, rid)}
    except state_store.StoreError as e:
        return {"outcome": "store-error", "stage": STAGE, "run_id": rid,
                "error": e.code, "detail": str(e)[:160], "evidence": ev,
                "downstream": _downstream_rows(st, rid)}
    finally:
        st.close()


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="continuity-bible stage",
        description="Continuity-bible stage runner: typed record load, the "
                    "qc_gate stage gate on the declared required evidence, "
                    "and the guarded row advancement.")
    p.add_argument("action_pos", nargs="?", default=None,
                   choices=("check", "advance", "proven", "downstream"),
                   help="action as a positional (the registry row's form)")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--run-id", default=None,
                   help="Store run id / record run_id; default: run folder name.")
    p.add_argument("--action", default=None,
                   choices=("check", "advance", "proven", "downstream"))
    a = p.parse_args(argv)
    action = a.action_pos or a.action or "check"
    run_dir = os.path.abspath(os.path.expanduser(a.run_dir))
    try:
        if action == "check":
            res = evaluate(run_dir, a.run_id)
            out, code = res, (0 if res.get("gate") == "PASS" else 3)
        elif action == "proven":
            ok, ev = proven(run_dir, a.run_id)
            out, code = {"proven": ok, "evidence": ev}, (0 if ok else 3)
        elif action == "downstream":
            out, code = {"downstream": downstream_status(run_dir, a.run_id)}, 0
        else:
            res = advance(run_dir, a.run_id)
            out, code = res, (0 if res.get("outcome") in
                              ("advanced", "already-complete") else 3)
    except Exception as exc:                        # noqa: BLE001
        out, code = {"outcome": "error", "detail": str(exc)[:200]}, 1
    json.dump(out, sys.stdout, indent=2, sort_keys=True, default=str)
    sys.stdout.write("\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
