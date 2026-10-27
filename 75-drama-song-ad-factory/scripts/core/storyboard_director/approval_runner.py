"""approval_runner.py: the live-run wiring for approval_package (Trevor, 2026-10-09).

Sits after ``image-keyframes`` and before ``video-generation``. ``factory.py
next`` will not hand out the video command until ``gate_open(run_dir)``;
``factory.py storyboard`` calls ``run()`` here:

* client chose STORYBOARD APPROVAL = Yes: ``build()`` the package, send the
  message and then every still (shot order) through ``openclaw message send``
  (the same sender the choice card uses), record the run as waiting, stop.
  A large plan is sent as NUMBERED card pages plus NUMBERED contact sheets;
  a small plan is one message plus one still per shot, in order.
  A reply of GO (or any unambiguous approve wording — 5.2 needs no magic
  word) calls ``approve()``; ``shot 2: change ...`` / ``shots 2 and 4: ...``
  (number or shot id) calls ``revise_shot()`` for those shots only and
  re-sends only those shots. A call with no reply never re-sends
  (resume-safe while the presented revisions are unchanged). Changed or
  unverifiable revisions are shown again and wait for a fresh reply.
* client chose No: ``approve()`` straight away, nothing is sent.

Selective revision (5.1 item 8): a named-shot revision invalidates the
approval of exactly those shots and their DESCENDANTS (approval_package.
affected_by_revision) — every unaffected shot keeps its approval, recorded
per shot in ``storyboard/approval.json`` with its revision binding. A
revision after an approval reopens just that scope.

Continuation (5.2): a valid approval persists the decision and enqueues the
continuation in the same write boundary (``control/continuation-queue.json``,
one idempotency key per event), so the pipeline resumes automatically with
no further "shall I continue?" prompt; a replayed GO acknowledges the
existing decision and does no duplicate work.

Run-dir files (all under ``$RUN``): ``storyboard/shot-list.json``,
``storyboard/contracts.json``, ``storyboard/stills.json`` ({shot_id: path}),
``control/card-receipt.json`` (key ``storyboard_approval``: true/false, written
by ``record_card_answer`` when the intake card's recap is confirmed; no receipt
file at all means an old run, treated as Yes, the card's recommended pick). Writes ``storyboard/approval.json``
(state, per-shot revisions, invalidation history, continuation) and
``storyboard/gate.json`` ({shots, review}) for the video request's
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

#: 5.2: no magic word. One pending approval + shots already presented means
#: ordinary approve wording is unambiguous. Anchored: a named-shot revision
#: or any other text never approves.
_APPROVE = re.compile(
    r"^(?:go|yes|y|yeah|yep|ok|okay|approve|approved|looks? good|looks? great"
    r"|lgtm|ship it|approve all|approve them|approve everything)[.!]*$", re.I)
#: Named-shot revision: "shot 2: change ...", "shot s2 - ...", "shots 2 and
#: 4: ...". Names are plan ordinals or shot ids; the text after the separator
#: is the change.
_REVISE = re.compile(
    r"^shots?\s+([A-Za-z0-9_,.&\s#-]+?)\s*[:\-]\s*(?:change\s+)?(.+)$",
    re.I | re.S)
_NAME = re.compile(r"\d+|s[A-Za-z0-9_.-]+")


class StillPending(Exception):
    """The redone still for one shot is not on disk yet."""


def _p(run_dir, *parts):
    return os.path.join(run_dir, *parts)


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def _state(run_dir):
    return _read(_p(run_dir, "storyboard", "approval.json"), {}) or {}


def _same_revisions(previous, current):
    """Exact scope; old revision hashes already include shot/contract/still bytes."""
    if not isinstance(previous, dict) or not previous or set(previous) != set(current):
        return False
    for sid, now in current.items():
        old = previous.get(sid)
        if not isinstance(old, dict) or not old.get("revision") or old["revision"] != now["revision"]:
            return False
        # Supported older per-shot maps may lack this redundant still hash.
        # Their matching revision is verified, never reconstructed or rewritten.
        if not now.get("still_sha256") or ("still_sha256" in old and old["still_sha256"] != now["still_sha256"]):
            return False
    return True


def _presentation_refusal(st, entries):
    previous = st.get("shots")
    if (st.get("state") not in ("pending", "approved") or
            not isinstance(previous, dict) or not previous or
            any(not isinstance(row, dict) or not row.get("revision") for row in previous.values()) or
            (st.get("state") == "pending" and not st.get("sent_at"))):
        return "STORYBOARD_PRESENTATION_UNVERIFIED"
    return None if _same_revisions(previous, entries) else "STORYBOARD_PRESENTATION_CHANGED"


def gate_open(run_dir):
    """Current per-shot revision proof is required; a bare boolean is unknown."""
    st = _state(run_dir)
    if st.get("state") != "approved":
        return False
    try:
        shots, contracts, stills = _load(run_dir)
        current = AP.approval_entries(shots, contracts, stills)
        return (_same_revisions(st.get("shots"), current) and
                all(row.get("status") == "approved" for row in st["shots"].values()))
    except Exception:                              # noqa: BLE001
        return False


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


def _method_contracts(run_dir, contracts, shots=None):
    """method_plan.storyboard_input feeds the storyboard review: the blueprint
    answers the 14.3 contract questions beside every shot card, and they are
    merged into the review's contract view.

    Each REAL shot takes the card whose story-beat window holds the shot's
    ``song_start`` (start <= t < end; the last beat also holds its end), or the
    card whose id equals the shot's own. Cards are keyed by blueprint
    story-beat id, which a shot list never has to reuse, so matching by id
    alone filled nothing. A card no real shot lands on is never added.

    Fill-only: a question the run's own contracts.json already answers keeps
    its answer, and nothing here touches shots, contracts.json or the
    approval record. No blueprint, no method_plan box: the review sees the
    run's contracts unchanged."""
    blueprint = _read(_p(run_dir, "creative", "blueprint.json"))
    if not blueprint:
        return contracts
    method = _read(_p(run_dir, "control", "method.json")) or {}
    try:
        import method_plan.method_plan as MP   # noqa: PLC0415  the owner module
        seeds = MP.shot_seeds(blueprint, method)
        cards = MP.storyboard_input(blueprint, method).get("cards") or []
    except Exception:                          # noqa: BLE001 - review stands alone
        return contracts
    by_id = {c.get("shot_id"): c for c in cards if isinstance(c, dict)}
    windows = [(s.get("song_start"), s.get("song_end"), by_id.get(s.get("shot_id")))
               for s in seeds
               if s.get("song_start") is not None and s.get("song_end") is not None]
    last_end = max((w[1] for w in windows), default=None)

    def card_for(shot):
        sid = shot.get("shot_id")
        if sid in by_id:
            return by_id[sid]
        try:
            t = float(shot.get("song_start"))
        except (TypeError, ValueError):
            return None
        for start, end, card in windows:
            if start <= t < end or (t == end == last_end):
                return card
        return None

    merged = {sid: dict(c or {}) for sid, c in (contracts or {}).items()}
    for shot in shots or []:
        sid = shot.get("shot_id") if isinstance(shot, dict) else None
        card = card_for(shot) if sid else None
        if not card:
            continue
        cur = merged.get(sid) or {}
        for key, val in (card.get("contract") or {}).items():
            if val and not cur.get(key):
                cur[key] = val
        if cur:
            merged[sid] = cur
    return merged


def _ordered(shots):
    return sorted(shots or [], key=lambda s: (s["song_start"], s["song_end"]))


def _next_command(run_dir, stage):
    """The registry's own next action for ``stage`` — reused from
    factory._runbook_rows, never re-derived here. None when the box does not
    carry factory (guarded import: degrades one data line, never the step)."""
    try:
        fp = os.path.join(_CORE, "intake_preflight")
        if fp not in sys.path:
            sys.path.insert(0, fp)
        import factory as F                            # noqa: PLC0415
        rows, _path = F._runbook_rows()
        return (rows.get(stage) or {}).get("command") or None
    except Exception:                                  # noqa: BLE001
        return None


def _enqueue_continuation(run_dir):
    """5.2: the approval decision and its continuation enqueue land in the
    same write boundary. One idempotency key per (run, event): a replayed
    approval acknowledges the existing entry and does no duplicate work.
    Returns the continuation entry (queued or the existing one)."""
    key = "%s/storyboard-approved" % (os.path.basename(os.path.abspath(run_dir)) or "run")
    path = _p(run_dir, "control", "continuation-queue.json")
    q = _read(path, []) or []
    if not isinstance(q, list):
        q = []
    for e in q:
        if isinstance(e, dict) and e.get("idempotency_key") == key:
            return e
    entry = {"idempotency_key": key, "event": "storyboard-approved",
             "stage": STAGE, "at": time.time(), "status": "queued",
             "next_action": _next_command(run_dir, STAGE)}
    q.append(entry)
    _write(path, q)
    return entry


def _present(run_dir, shots, contracts, stills, send, st=None, reason=None):
    # Snapshot BEFORE the sender can read or change mutable asset paths.
    # A later GO must match this snapshot, never a digest computed after send.
    entries = AP.approval_entries(shots, contracts, stills)
    pkg = AP.build(shots, contracts, stills)
    if pkg["large"]:
        for page in pkg["pages"]:
            send(page["text"], [])
        for sheet in pkg["sheets"]:
            send(sheet["caption"], sheet["images"])
    else:
        send(pkg["message"], [(e["n"], e["still"]) for e in pkg["items"]])
    pending = dict(st or {})
    if pending.get("state") == "approved":
        pending["previous_approval"] = {k: pending[k] for k in
            ("state", "choice", "at", "shots", "decision", "continuation") if k in pending}
    pending.update(state="pending", choice="yes", sent_at=time.time(), redo=None,
                   shots=entries, invalidations=pending.get("invalidations") or [])
    _write(_p(run_dir, "storyboard", "approval.json"), pending)
    _record(run_dir, "WAITING_APPROVAL")
    result = {"action": "waiting", "message_sent": True, "images": len(pkg["images"]),
              "sheets": len(pkg["sheets"]), "pages": len(pkg["pages"])}
    if reason:
        result.update(reason_code=reason,
                      detail="The current package has been shown. Its presented revisions need a fresh approval reply.")
    return result


def _approve(run_dir, shots, contracts, stills, choice, st=None, reply=None):
    # Re-read authority even for a direct internal call; supplied JSON is not
    # proof that the client saw these current revisions.
    st = _state(run_dir)
    entries = AP.approval_entries(shots, contracts, stills)
    if choice == "yes":
        if _parse_reply(reply)[0] != "approve":
            return {"action": "waiting", "message_sent": False,
                    "reason_code": "STORYBOARD_APPROVAL_REPLY_REQUIRED"}
        reason = _presentation_refusal(st, entries)
        if reason:
            return {"action": "waiting", "message_sent": False, "reason_code": reason}
    approved = AP.approve(shots, contracts, stills)
    review = None
    try:
        import storyboard_director.storyboard_director as SD
        review = SD.adversarial_review(approved,
                                       _method_contracts(run_dir, contracts, approved))
    except Exception:   # noqa: BLE001 - review is its own stage; gate.json just omits it
        pass
    _write(_p(run_dir, "storyboard", "gate.json"), {"shots": approved, "review": review})
    now = time.time()
    for rec in entries.values():
        rec["status"], rec["at"] = "approved", now
    cont = _enqueue_continuation(run_dir)
    st = dict(st or _state(run_dir))
    approved_state = dict(st, state="approved", choice=choice, at=now,
                          shots=entries, invalidations=st.get("invalidations") or [], continuation=cont)
    if choice == "yes":
        approved_state["decision"] = {"scope": "whole-package", "reply_text": reply, "at": now}
    else:
        approved_state.pop("decision", None)  # No is a preference, not a client artifact approval.
    _write(_p(run_dir, "storyboard", "approval.json"), approved_state)
    _record(run_dir, "READY")
    return {"action": "approved", "message_sent": False, "continuation": cont}


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


def _parse_reply(text):
    """("approve", None) | ("revise", (names, change)) | ("other", None)."""
    t = (text or "").strip()
    if _APPROVE.fullmatch(t):
        return "approve", None
    m = _REVISE.match(t)
    if m:
        names = _NAME.findall(m.group(1))
        change = m.group(2).strip()
        if names and change:
            return "revise", (names, change)
    return "other", None


def _resolve_names(names, shots):
    """Plan ordinals ("2") or shot ids ("s2") -> shot_ids in plan order."""
    ordered = _ordered(shots)
    by_id = {s["shot_id"]: s["shot_id"] for s in ordered}
    out = []
    for name in names:
        if name.isdigit():
            n = int(name)
            if not 1 <= n <= len(ordered):
                return None
            out.append(ordered[n - 1]["shot_id"])
        else:
            hit = by_id.get(name) or next(
                (sid for sid in by_id if sid.lower() == name.lower()), None)
            if not hit:
                return None
            out.append(hit)
    seen, uniq = set(), []
    for sid in out:
        if sid not in seen:
            seen.add(sid)
            uniq.append(sid)
    return uniq


def _invalidate(st, shots, contracts, stills, targets, change):
    """Scoped invalidation: revised shots + descendants drop their approval
    records; every unaffected shot keeps its record untouched."""
    affected, kept = AP.affected_by_revision(shots, contracts, targets)
    desc = [sid for sid in affected if sid not in targets]
    entries = AP.approval_entries(shots, contracts, stills)
    prev = (st or {}).get("shots") if isinstance(st, dict) else None
    prev = prev if isinstance(prev, dict) else {}
    now = time.time()
    for sid, rec in entries.items():
        old = prev.get(sid) or {}
        if sid in affected:
            rec["status"] = "invalidated"
            rec["at"] = now
            rec["reason"] = "revised" if sid in targets \
                else "descendant of %s" % ", ".join(targets)
        elif old.get("status") == "approved" and old.get("revision") == rec["revision"]:
            rec["status"], rec["at"] = "approved", old.get("at", now)
    inv = {"shots": list(targets), "descendants": desc, "kept": kept,
           "change": change, "at": now}
    history = list((st or {}).get("invalidations") or []) \
        if isinstance(st, dict) else []
    history.append(inv)
    return entries, history, inv


def run(run_dir, send, reply=None, make_still=None):
    """One step of the approval gate. Returns {"action": ..., ...}:
    approved | waiting | revised | regenerate_still | unrecognized."""
    run_dir = os.path.abspath(run_dir)
    st = _state(run_dir)
    text = (reply or "").strip()
    kind, parsed = _parse_reply(text) if text else ("other", None)
    shots, contracts, stills = _load(run_dir)
    if not wants_approval(run_dir):
        if st.get("state") == "approved" and gate_open(run_dir):
            return {"action": "approved", "message_sent": False, "continuation": st.get("continuation")}
        return _approve(run_dir, shots, contracts, stills, "no", st)
    if st.get("state") == "approved" and kind != "revise" and gate_open(run_dir):
        # Replay only acknowledges the same current approved package.
        return {"action": "approved", "message_sent": False, "continuation": st.get("continuation")}
    if not st:
        return _present(run_dir, shots, contracts, stills, send)

    def sb_state(**kw):
        st.update(state="pending", choice="yes", **kw)
        _write(_p(run_dir, "storyboard", "approval.json"), st)

    redo = st.get("redo") or []
    if isinstance(redo, dict):          # legacy single redo record
        redo = [redo]
    if not redo:
        reason = _presentation_refusal(st, AP.approval_entries(shots, contracts, stills))
        if reason:
            return _present(run_dir, shots, contracts, stills, send, st, reason)
    if not text and not redo:
        return {"action": "waiting", "message_sent": False}   # resume: never re-send
    if redo:                       # finish pending redos first
        targets = [r["shot_id"] for r in redo]
        change = redo[0].get("change", "")
    elif kind == "approve":
        result = _approve(run_dir, shots, contracts, stills, "yes", st, reply=text)
        if result["action"] == "waiting":
            return _present(run_dir, shots, contracts, stills, send, st, result["reason_code"])
        return result
    elif kind == "revise":
        targets = _resolve_names(parsed[0], shots)
        if not targets:
            return {"action": "unrecognized", "message_sent": False}
        change = parsed[1]
    else:
        return {"action": "unrecognized", "message_sent": False}
    order = _ordered(shots)
    ordinal = {s["shot_id"]: i for i, s in enumerate(order, 1)}
    new_contracts, new_stills, done, pending = dict(contracts), dict(stills), [], []
    for sid in targets:
        try:
            new_contracts, new_stills, _msg = AP.revise_shot(
                shots, new_contracts, new_stills, sid,
                {"character_action": change},
                make_still or _redo_still(run_dir))
            done.append(sid)
        except StillPending:
            pending.append(sid)
    if pending:
        sb_state(redo=[{"shot_id": sid, "change": change} for sid in pending])
        return {"action": "regenerate_still", "shot_id": pending[0],
                "shot_ids": pending, "message_sent": False}
    _write(_p(run_dir, "storyboard", "contracts.json"), new_contracts)
    _write(_p(run_dir, "storyboard", "stills.json"), new_stills)
    entries, history, inv = _invalidate(st, shots, new_contracts, new_stills,
                                        done, change)
    pkg = AP.build(shots, new_contracts, new_stills)
    e_by_id = {e["shot_id"]: e for e in pkg["items"]}
    body = "\n\n".join("Updated shot %d.\n\n%s"
                       % (ordinal[sid], AP.card_text(e_by_id[sid]))
                       for sid in done)
    kept_nums = [ordinal[sid] for sid in inv["kept"]]
    note = ("Approval re-open for %s and its dependents (%s). "
            "Shots %s keep their approval."
            % (", ".join("shot %d" % ordinal[sid] for sid in done),
               ", ".join(inv["descendants"]) or "none",
               ", ".join(str(n) for n in kept_nums) or "none"))
    msg = "%s\n\n%s\n\n%s" % (body, note, AP.FOOTER)
    send(msg, [(ordinal[sid], new_stills[sid]) for sid in done])
    sb_state(redo=None, shots=entries, invalidations=history)
    return {"action": "revised", "shot_id": done[0], "shot_ids": done,
            "invalidated": inv["shots"] + inv["descendants"],
            "kept": inv["kept"], "message_sent": True}
