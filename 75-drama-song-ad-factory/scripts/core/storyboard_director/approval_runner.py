"""approval_runner.py: the live-run wiring for approval_package (Trevor, 2026-10-09).

Sits after ``image-keyframes`` and before ``video-generation``. ``factory.py
next`` will not hand out the video command until ``gate_open(run_dir)``;
``factory.py storyboard`` calls ``run()`` here:

* client chose STORYBOARD APPROVAL = Yes: ``build()`` the package, send the
  message and then every still (shot order) through ``openclaw message send``
  (the same sender the choice card uses), record the run as waiting, stop.
  A reply of GO calls ``approve()``; ``shot N: change ...`` calls
  ``revise_shot()`` and re-sends only that shot. A call with no reply never
  re-sends (resume-safe).
* client chose No: ``approve()`` straight away, nothing is sent.

Run-dir files (all under ``$RUN``): ``storyboard/shot-list.json``,
``storyboard/contracts.json``, ``storyboard/stills.json`` ({shot_id: path}),
``control/card-receipt.json`` (key ``storyboard_approval``: true/false, written
by ``record_card_answer`` when the intake card's recap is confirmed; no receipt
file at all means an old run, treated as Yes, the card's recommended pick). Writes ``storyboard/approval.json``
(state) and ``storyboard/gate.json`` ({shots, review}) for the video request's
``storyboard`` block. Stdlib only.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

import storyboard_director.approval_package as AP   # noqa: E402

LIMIT = 4000   # Telegram message cap, same margin the choice card uses
STAGE = "video-generation"
OWNER = "storyboard-approval"


class StillPending(Exception):
    """The redone still for one shot is not on disk yet."""


def _p(run_dir, *parts):
    return os.path.join(run_dir, *parts)


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except OSError:
        return default


def _write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def _state(run_dir):
    return _read(_p(run_dir, "storyboard", "approval.json"), {}) or {}


def gate_open(run_dir):
    """True once the client approved (or chose No and the stills passed)."""
    return _state(run_dir).get("state") == "approved"


def wants_approval(run_dir):
    r = _read(_p(run_dir, "control", "card-receipt.json"))
    if r is None:       # old run, no receipt: Yes (the card's recommended pick)
        return True
    a = r.get("answers") if isinstance(r.get("answers"), dict) else r
    v = a.get("storyboard_approval", False)   # receipt present, key absent: not asked Yes
    if isinstance(v, str):
        return not v.strip().lower().startswith("n")
    return bool(v)


def receipt_target(run_dir):
    return (_read(_p(run_dir, "control", "card-receipt.json"), {}) or {}).get("target", "")


def record_card_answer(run_dir, answers, questions, target=None):
    """Called when the intake card's recap is confirmed. ``answers`` and
    ``questions`` are the card's lists, same order. Writes
    ``storyboard_approval`` (true when option 1, Yes) and the client's send
    ``target`` into ``control/card-receipt.json``, keeping other keys."""
    path = _p(run_dir, "control", "card-receipt.json")
    r = _read(path, {}) or {}
    for q, a in zip(questions, answers):
        if q["id"] == "storyboard":
            r["storyboard_approval"] = a["n"] == 1
    if target:
        r["target"] = str(target)
    _write(path, r)


def _record(run_dir, to):
    """Mirror the wait in the state store (best effort; approval.json rules)."""
    try:
        import state_store as SS
        db = _p(run_dir, "control", "state.sqlite3")
        rid = os.path.basename(os.path.abspath(run_dir)) or "run"
        with SS.Store(db) as st:
            row = st.get(rid, STAGE)["state"]
            if to == "WAITING_APPROVAL" and row != "WAITING_APPROVAL":
                if row == "NOT_STARTED":
                    st.transition(rid, STAGE, "READY", OWNER)
                st.claim(rid, STAGE, OWNER, lease_s=86400)
                st.transition(rid, STAGE, "WAITING_APPROVAL", OWNER)
            elif to == "READY" and row == "WAITING_APPROVAL":
                st.transition(rid, STAGE, "RUNNING", OWNER)
                st.transition(rid, STAGE, "PARKED", OWNER, reason="storyboard approved")
                st.transition(rid, STAGE, "READY", OWNER)
    except Exception:   # noqa: BLE001 - no store / row: approval.json is the record
        pass


def _chunks(text, limit=LIMIT):
    out, cur = [], ""
    for part in text.split("\n\n"):
        cand = cur + "\n\n" + part if cur else part
        if len(cand) > limit and cur:
            out.append(cur)
            cur = part
        else:
            cur = cand
    return out + ([cur] if cur else [])


def openclaw_sender(target):
    """Default delivery: ``openclaw message send`` on Telegram, argv list, no
    shell; text via intake_card's argv builder, each still as ``--media``.
    ``images`` is [(shot number, file path)] in shot order."""
    from choice_card.intake_card import intake_card as IC

    def send(message, images):
        for m in _chunks(message):
            subprocess.run(IC.openclaw_send_argv(target, m), check=True)
        for n, img in images:
            subprocess.run(IC.openclaw_send_argv(target, "Shot %d" % n)
                           + ["--media", img], check=True)
    return send


def _load(run_dir):
    sb = _p(run_dir, "storyboard")
    env = _read(_p(sb, "shot-list.json"))
    shots = env.get("shots") if isinstance(env, dict) else env
    contracts = _read(_p(sb, "contracts.json"), {}) or {}
    stills = {k: (v if os.path.isabs(v) else _p(run_dir, v))
              for k, v in (_read(_p(sb, "stills.json"), {}) or {}).items()}
    return shots or [], contracts, stills


def _approve(run_dir, shots, contracts, stills, choice):
    approved = AP.approve(shots, contracts, stills)
    review = None
    try:
        import storyboard_director.storyboard_director as SD
        review = SD.adversarial_review(approved, contracts)
    except Exception:   # noqa: BLE001 - review is its own stage; gate.json just omits it
        pass
    _write(_p(run_dir, "storyboard", "gate.json"), {"shots": approved, "review": review})
    _write(_p(run_dir, "storyboard", "approval.json"),
           {"state": "approved", "choice": choice, "at": time.time()})
    _record(run_dir, "READY")
    return {"action": "approved", "message_sent": False}


def _redo_still(run_dir):
    def make(shot_id, card):
        d = _p(run_dir, "storyboard", "redo")
        png = _p(d, shot_id + ".png")
        if not os.path.isfile(png):
            _write(_p(d, shot_id + ".json"), card)
            raise StillPending(shot_id)
        done = _p(d, "%s-v%d.png" % (shot_id, time.time_ns()))
        os.replace(png, done)
        return done
    return make


def run(run_dir, send, reply=None, make_still=None):
    """One step of the approval gate. Returns {"action": ..., ...}:
    approved | waiting | revised | regenerate_still | unrecognized."""
    run_dir = os.path.abspath(run_dir)
    st = _state(run_dir)
    if st.get("state") == "approved":
        return {"action": "approved", "message_sent": False}
    shots, contracts, stills = _load(run_dir)
    if not wants_approval(run_dir):
        return _approve(run_dir, shots, contracts, stills, "no")
    sb_state = lambda **kw: _write(_p(run_dir, "storyboard", "approval.json"),   # noqa: E731
                                   dict(st, state="pending", choice="yes", **kw))
    if not st:   # first time: show everything once, then wait
        pkg = AP.build(shots, contracts, stills)
        send(pkg["message"], [(e["n"], e["still"]) for e in pkg["items"]])
        sb_state(sent_at=time.time())
        _record(run_dir, "WAITING_APPROVAL")
        return {"action": "waiting", "message_sent": True, "images": len(pkg["images"])}
    text = (reply or "").strip()
    redo = st.get("redo")
    if not text and not redo:
        return {"action": "waiting", "message_sent": False}   # resume: never re-send
    if re.fullmatch(r"go[.!]?", text, re.I):
        return _approve(run_dir, shots, contracts, stills, "yes")
    if redo:                       # finish a pending redo first
        sid, change = redo["shot_id"], redo["change"]
    else:
        m = re.match(r"shot\s+(\d+)\s*[:\-]\s*(?:change\s+)?(.+)", text, re.I | re.S)
        if not m:
            return {"action": "unrecognized", "message_sent": False}
        order = sorted(shots, key=lambda s: (s["song_start"], s["song_end"]))
        n = int(m.group(1))
        if not 1 <= n <= len(order):
            return {"action": "unrecognized", "message_sent": False}
        sid, change = order[n - 1]["shot_id"], m.group(2).strip()
    try:
        contracts, stills, msg = AP.revise_shot(
            shots, contracts, stills, sid, {"character_action": change},
            make_still or _redo_still(run_dir))
    except StillPending:
        sb_state(redo={"shot_id": sid, "change": change})
        return {"action": "regenerate_still", "shot_id": sid, "message_sent": False}
    _write(_p(run_dir, "storyboard", "contracts.json"), contracts)
    _write(_p(run_dir, "storyboard", "stills.json"), stills)
    send(msg, [(n, stills[sid]) for n, s in enumerate(sorted(
        shots, key=lambda s: (s["song_start"], s["song_end"])), 1) if s["shot_id"] == sid])
    sb_state(redo=None)
    return {"action": "revised", "shot_id": sid, "message_sent": True}
