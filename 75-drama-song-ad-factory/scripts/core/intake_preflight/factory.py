#!/usr/bin/env python3
"""factory.py: one CLI entrypoint, subcommands intake/preflight/next.

Envelope (directive 24.4/line 2215): schema_version, tool_version, command,
run_id, outcome, reason_code, next_action, evidence, data, state_version.
Exit codes: ok 0, waiting 2, parked 3, rejected 4, error 1. stdlib only.

`next` (manual 02 B1) reads the run's control/state.sqlite3 through
state_store.py and answers one question: which stage is next and what exact
command runs it. It prints the same envelope as intake/preflight (outcome
ok/error; waiting/parked/rejected never come out of `next`) and exits 0/1.

Stage IDs come from batch_mode.batch.STAGES verbatim (never a second list).
Command lines come from references/stage-runbook.md, parsed from its stage |
command | produces table. Lane counts come from scripts/core/lane_size.py
when that module is importable; otherwise the Part D fallback defaults below
are used (agents >= 1, kie_inflight <= 8, one machine-sized ffmpeg pool).

No automatic runner: the agent loops next -> run the command -> register ->
next (manual B1 step 5).

SCRIPT APPROVAL (the card question labelled SCRIPT APPROVAL -- never a position
number, which drifts when the card grows): when `next` would hand out the `music`
stage
and the client answered Yes, it first runs script_approval.stage.run_stage: sends
the script through the client-delivery path (`openclaw message send` to --target,
or, with no --target, the messages come back in data.messages for the chat),
records the run as waiting and answers outcome "waiting" (exit 2) with no music
command. `script-reply --run-dir D --reply TEXT` carries the client's answer:
approve -> `next` hands out music; anything else -> the edit is re-checked and re-sent.
"""
import argparse
import json
import os
import re
import shlex
import sqlite3
import sys
import time
import uuid
from pathlib import Path

try:
    from . import EXIT, SCHEMA_VERSION, TOOL_VERSION
    from . import intake as _intake
    from . import preflight as _preflight
except ImportError:  # direct script run: python3 factory.py ...
    import intake as _intake  # type: ignore
    import preflight as _preflight  # type: ignore
    _eval = _intake.evaluate
    _check = _preflight.check
    SCHEMA_VERSION = "blackceo.intake-preflight/envelope/v1"
    TOOL_VERSION = "0.2.0"
    EXIT = {"ok": 0, "waiting": 2, "parked": 3, "rejected": 4, "error": 1}
else:
    _eval = _intake.evaluate
    _check = _preflight.check

try:  # W2-A-U1's module, when the box has it; else Part D fallback below.
    from .. import lane_size as _lane_size
except Exception:  # noqa: BLE001 - package-or-module missing: try sibling
    try:
        _core = Path(__file__).resolve().parent.parent
        if str(_core) not in sys.path:
            sys.path.insert(0, str(_core))
        import lane_size as _lane_size_mod  # type: ignore
        _lane_size = _lane_size_mod
    except Exception:  # noqa: BLE001 - module missing: fallback stays
        _lane_size = None

#: Part D fallback when lane_size.py is not importable (W2-A-U1 not landed).
#: Same constants a live lane_size exposes; agents floor 1, never 0.
PART_D_DEFAULTS = {"agents": 1, "kie_inflight": 8, "ffmpeg_jobs": 1,
                   "ffmpeg_threads": 1, "source": "part_d_defaults"}


def _loud(kind, code, detail):
    """Named, visible failure/warning that reaches the receipt (loud_failure.py)."""
    import os as _os, sys as _sys
    d = _os.path.dirname(_os.path.abspath(__file__))
    while d != _os.path.dirname(d) and not _os.path.exists(_os.path.join(d, "loud_failure.py")):
        d = _os.path.dirname(d)
    if d not in _sys.path:
        _sys.path.insert(0, d)
    import loud_failure
    getattr(loud_failure, kind)(code, detail)


def envelope(command, run_id, outcome, reason_code, next_action,
             data=None, evidence=None, state_version=None):
    return {"schema_version": SCHEMA_VERSION.replace(
                "intake-preflight", "intake-preflight", 1),
            "tool_version": TOOL_VERSION, "command": command,
            "run_id": run_id, "outcome": outcome, "reason_code": reason_code,
            "next_action": next_action, "evidence": evidence or [],
            "data": data or {},
            "state_version": state_version
            or {"expected": None, "current": run_id}}


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def limit_from(doc):
    """Dollars (str) from a brief or intake summary/envelope, or None. Minor units,
    USD only (or no currency named); anything else is left for the client to type."""
    if not isinstance(doc, dict):
        return None
    doc = ((doc.get("data") or {}).get("summary") or doc.get("summary") or doc)
    ceil = doc.get("generation_ceiling") or {}
    minor = doc.get("budget_minor", doc.get("budget_amount_minor", ceil.get("amount_minor")))
    cur = str(doc.get("budget_currency") or doc.get("currency") or ceil.get("currency") or "usd").lower()
    if not isinstance(minor, int) or isinstance(minor, bool) or minor <= 0 or cur != "usd":
        return None
    return "%d.%02d" % divmod(minor, 100)


def cmd_intake(a):
    brief = _load(a.brief_file) if a.brief_file else json.loads(a.brief or "{}")
    settings = _load(a.settings_file) if a.settings_file else {}
    resume = _load(a.resume_file) if a.resume_file else None
    run_id = a.run_id or uuid.uuid4().hex[:12]
    try:
        r = _eval(brief, settings, resume, run_id)
    except Exception as e:
        return envelope("intake", run_id, "error", "intake-failed", str(e)[:200])
    return envelope("intake", run_id, r["outcome"], r["reason_code"], r["next_action"],
                    data={k: r.get(k) for k in ("questions", "question_message", "summary",
                                                "digest", "provenance", "auth_status",
                                                "approval_invalidated", "changes",
                                                "untrusted_fields", "next_stage", "mode", "notices")},
                    state_version={"expected": (resume or {}).get("digest") if resume else None,
                                   "current": r.get("digest")})


def cmd_preflight(a):
    run_id = a.run_id or uuid.uuid4().hex[:12]
    payload = {"tools": a.require_tool or [], "modules": a.require_module or [],
               "storage_dir": a.storage_dir, "min_free_bytes": a.min_free_bytes,
               "approved_root": a.root, "references": a.ref or [],
               "profile": a.profile, "allowed_profiles": json.loads(a.allowed_profiles or "[]") or None,
               "schema_version": a.schema_version,
               "allowed_schemas": json.loads(a.allowed_schemas or "[]") or None,
               "credentials": a.credential or [], "auth": _load(a.auth_file) if a.auth_file else None,
               "summary_digest": a.summary_digest,
               "run_state": _load(a.run_state_file) if a.run_state_file else None,
               "card_receipt": _load(a.card_receipt_file) if a.card_receipt_file else None}
    try:
        r = _check(payload)
    except Exception as e:
        return envelope("preflight", run_id, "error", "preflight-failed", str(e)[:200])
    return envelope("preflight", run_id, r["outcome"], r["reason_code"], r["next_action"],
                    data={k: r.get(k) for k in ("checks", "missing", "outside")},
                    state_version={"expected": a.summary_digest, "current": run_id})


# ── B1: the "what next" command ──────────────────────────────────────────────

#: Stage order, read from batch_mode/batch.py (never a second copy).
def _stages():
    try:
        from .batch_mode import batch as batch_mod   # package import
    except ImportError:
        core = None
        try:
            core = Path2 = __import__("pathlib").Path(__file__).resolve().parent.parent
            if str(core) not in sys.path:
                sys.path.insert(0, str(core))
            from batch_mode import batch as batch_mod  # type: ignore  # noqa: PLC0415
        except Exception:                              # noqa: BLE001
            return None
    return tuple(sid for sid, _title in batch_mod.STAGES)


def _runbook_rows():
    """{stage_id: {"command":…, "produces":…}} from references/stage-runbook.md.

    Table format (W2-A-U3): lines starting with '|' whose first cell matches a
    stage id win; the header/separator rows do not.
    """
    ref = Path(__file__).resolve()
    skill_root = ref.parent.parent.parent.parent   # core/intake_preflight -> skill root
    md = skill_root / "references" / "stage-runbook.md"
    rows = {}
    text = None
    try:
        text = md.read_text(encoding="utf-8")
    except OSError:
        return rows, str(md)
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        sid = cells[0]
        # U3's table: the command cell is wrapped in backticks; produces is
        # free prose. Header ("stage id") and separator ("---") never match.
        if re.fullmatch(r"[a-z0-9-]+", sid) and (
                cells[1].startswith("`") and cells[1].endswith("`")
                and cells[2]):
            rows[sid] = {"command": cells[1][1:-1],
                         "produces": cells[2]}
    return rows, str(md)


def lane_size_payload():
    """One sizing payload. Live module when importable; else Part D defaults."""
    if _lane_size is not None:
        try:
            line = _lane_size.size("claude-code", "openrouter")
            return {"agents": line["agents"],
                    "kie_inflight": line["kie_inflight"],
                    "ffmpeg_jobs": line["ffmpeg_jobs"],
                    "ffmpeg_threads": line["ffmpeg_threads"],
                    "source": "lane_size.module"}
        except Exception as exc:  # noqa: BLE001 - broken module: fall through
            _loud("warn", "LANE_SIZE_BROKEN",
                  "using Part D default lane sizes: %r" % (exc,))
    out = dict(PART_D_DEFAULTS)
    out["source"] = "part_d_defaults"
    return out


def _approval_runner():
    core = str(Path(__file__).resolve().parent.parent)
    if core not in sys.path:
        sys.path.insert(0, core)
    try:
        from storyboard_director import approval_runner  # noqa: PLC0415
        return approval_runner
    except ImportError:
        return None


# ── STUDIO (SPEC §6): the studio page as an approval channel ─────────────────
#
# A run that came from the studio page carries `control/studio-order.json`
# ({order_id, client_id, title, base_url} — no key; the key comes from the
# bridge's own lookup). Two seams only, both through shared-bridge/
# approvals_bridge.py (W1-box-bridge-U2): PUBLISH an approval item to the page,
# READ the client's answer back. The approval rules themselves (first answer
# wins, same version = same item) live in the service; nothing here re-derives
# them.

def _bridge_dir():
    return Path(__file__).resolve().parents[3] / "shared-bridge"


def _studio_order(run_dir):
    """The studio order this run came from, or None (a chat/manual run)."""
    try:
        d = json.loads((Path(run_dir) / "control" / "studio-order.json")
                       .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) and d.get("order_id") else None


def _approvals_bridge():
    """shared-bridge/approvals_bridge.py when the box has it; else None (fail closed)."""
    br = str(_bridge_dir())
    if br not in sys.path:
        sys.path.insert(0, br)
    try:
        import approvals_bridge   # noqa: PLC0415
        return approvals_bridge
    except ImportError:
        return None


def _studio_key():
    """The presented key, via the bridge's own lookup. Never printed."""
    br = str(_bridge_dir())
    if br not in sys.path:
        sys.path.insert(0, br)
    try:
        import studio_bridge      # noqa: PLC0415
        return studio_bridge.load_key()
    except ImportError:
        import os
        return os.environ.get("DS_KEY") or ""


def _studio_versions(run_dir):
    """{stage: current approval version} — the version key the service scopes
    items by (same version = same item, first answer wins)."""
    try:
        return json.loads((Path(run_dir) / "control" / "studio-versions.json")
                          .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _studio_bump_version(run_dir, stage):
    """One more approval round for this stage; returns the new version."""
    v = _studio_versions(run_dir)
    v[stage] = int(v.get(stage) or 0) + 1
    p = Path(run_dir) / "control" / "studio-versions.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(v, indent=2, sort_keys=True), encoding="utf-8")
    return v[stage]


def _studio_publish(run_dir, order, stage, text, files, choices=()):
    """One approval item on the studio page (approvals_bridge.publish). Returns
    the item dict, or None when the bridge module is not on this box."""
    ab = _approvals_bridge()
    if ab is None:
        return None
    version = _studio_bump_version(run_dir, stage)
    return ab.publish(order.get("base_url") or "", _studio_key(),
                      order.get("order_id"), stage, version,
                      text, list(choices), list(files))


def _studio_answer(run_dir, stage):
    """The client's studio answer for one approval stage, or None — never opens
    a gate on a studio error, a missing bridge, or a never-published stage."""
    order = _studio_order(run_dir)
    ab = _approvals_bridge() if order else None
    if not order or ab is None:
        return None
    version = int(_studio_versions(run_dir).get(stage) or 1)
    try:
        return ab.answer(order.get("base_url") or "", _studio_key(),
                         order.get("order_id"), stage, version)
    except Exception:   # noqa: BLE001 - a studio outage keeps the gate waiting
        return None


def _studio_apply(cmd, sid, run_dir, stage, approval, value):
    """A studio ANSWER becomes the EXISTING apply command (script-reply /
    song pick / storyboard --reply). No new approval logic here."""
    q = shlex.quote
    run = q(str(run_dir))
    if approval == "script":
        command = ("python3 scripts/core/intake_preflight/factory.py script-reply "
                   "--run-dir %s --reply %s" % (run, q(str(value))))
    elif approval == "song":
        command = ("python3 scripts/core/song_choices/song_choices.py pick "
                   "--run-dir %s --reply %s" % (run, q(str(value))))
    else:
        command = ("python3 scripts/core/intake_preflight/factory.py storyboard "
                   "--run-dir %s --reply %s" % (run, q(str(value))))
    return envelope(cmd, sid, "ok", "next-stage",
                    "The client answered the %s approval on the studio page; "
                    "run this command, then `next` again." % approval,
                    data={"stage": stage, "command": command,
                          "approval": approval, "answer": value})


def cmd_storyboard(a):
    """storyboard --run-dir D [--target CHAT] [--reply TEXT]: one approval step.

    Delivery, in order (SPEC §6): the studio page when the run came from one
    (approvals_bridge.publish), the client chat when a target exists (both when
    the run has both — first answer wins), and with neither the cards and stills
    come back in data for whoever called."""
    ar = _approval_runner()
    run_dir = str(Path(a.run_dir).expanduser().resolve())
    sid = Path(run_dir).name or "run"
    if ar is None:
        return envelope("storyboard", sid, "error", "approval-runner-missing",
                        "storyboard_director/approval_runner.py not importable.")
    studio = _studio_order(run_dir)
    target = a.target or ar.receipt_target(run_dir)
    sent, stills = [], []

    def send(message, images):
        delivered = False
        if studio:
            delivered = _studio_publish(run_dir, studio, "storyboard", message,
                                        [p for _n, p in images],
                                        choices=["GO"]) is not None or delivered
        if target:
            ar.openclaw_sender(target)(message, images)
            delivered = True
        if not delivered:       # nowhere to send: hand the cards back to the caller
            sent.append(message)
            stills.extend(p for _n, p in images)

    try:
        r = ar.run(run_dir, send, reply=a.reply)
    except Exception as e:   # ApprovalError, missing files, send failure: loud, no video
        return envelope("storyboard", sid, "error", getattr(e, "code", "storyboard-failed"),
                        str(e)[:300])
    out = "ok" if r["action"] in ("approved", "revised") else "waiting"
    data = dict(r)
    if sent:
        data["messages"], data["stills"] = sent, stills
    return envelope("storyboard", sid, out, r["action"],
                    "Run `next` for the video stage." if r["action"] == "approved"
                    else "Waiting for the client's reply (GO, or 'shot N: change ...').",
                    data=data)


def _deliverer(a, out):
    """The client-delivery sink: `openclaw message send` (intake_card.openclaw_send_argv)
    to --target; with no --target the message is handed back for the chat."""
    target = getattr(a, "target", "") or ""

    def deliver(text):
        out.append(text)
        if target:
            import subprocess
            core = Path(__file__).resolve().parent.parent
            if str(core) not in sys.path:
                sys.path.insert(0, str(core))
            from choice_card.intake_card import intake_card as _card  # noqa: PLC0415
            r = subprocess.run(_card.openclaw_send_argv(target, text), capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError("client delivery failed: %s" % (r.stderr or r.stdout)[:200])
    return deliver


def _script_gate(run_dir, a, reply):
    core = Path(__file__).resolve().parent.parent
    if str(core) not in sys.path:
        sys.path.insert(0, str(core))
    from script_approval import stage as _stage  # noqa: PLC0415
    out = []
    try:
        r = _stage.run_stage(str(run_dir), _deliverer(a, out), reply=reply)
    except Exception as e:  # noqa: BLE001 - delivery failed: stay paused, resume re-sends
        return {"outcome": "error", "problems": [str(e)[:200]], "messages": out}
    r["delivered"] = out
    return r


def _sa_envelope(cmd, sid, r):
    oc = r["outcome"]
    if oc == "error":
        return envelope(cmd, sid, "error", "script-delivery-failed",
                        "The script was not delivered; nothing was lost. Run it again.",
                        data=r)
    if oc == "blocked":
        return envelope(cmd, sid, "rejected", "script-checks-failed",
                        "Fix: %s" % "; ".join(r["problems"]), data=r)
    if oc == "waiting":
        return envelope(cmd, sid, "waiting", "SCRIPT_AWAITING_APPROVAL",
                        "The client has the script. No song until they reply. When they do, "
                        "run script-reply --run-dir <dir> --reply <their words>.", data=r)
    return envelope(cmd, sid, "ok", "script-approved",
                    "Script approved (or not asked for). Run `next` for the music stage.", data=r)


def cmd_script_reply(a):
    run_dir = Path(a.run_dir).expanduser().resolve()
    return _sa_envelope("script-reply", run_dir.name or "run",
                        _script_gate(run_dir, a, reply=a.reply))


def _song_choices_next(run_dir, orchestrated=False):
    """SONG APPROVAL = Yes -> the three-version music runner descriptors.

    Exposes the canonical umbrella command AND the three owned unit
    descriptors, with an EXPLICIT orchestrated-mode selection: exactly ONE of
    them is ``selected`` and goes in ``command``; the other is listed only, so
    the two are never emitted or executed together (an unqualified umbrella in
    every unit prompt would fan out three each and pay for NINE generations).
    ``None`` when this run did not answer Yes."""
    try:
        _c = str(Path(__file__).resolve().parent.parent)
        if _c not in sys.path:
            sys.path.insert(0, _c)
        from song_choices import song_choices as _sc   # noqa: PLC0415
        st = _sc._state(str(run_dir))
    except Exception:  # noqa: BLE001 - a broken gate never silently opens the single row
        return None
    if not st or not st.get("required"):
        return None
    rd = str(run_dir)
    units = _sc.plan_units(rd)["units"]
    base = ("python3 scripts/core/song_choices/song_choices.py generate "
            "--run-dir \"$RUN\" --request \"$RUN/music/req.json\" "
            "--ledger \"$RUN/spend.sqlite3\" --run-id \"$RUN_ID\"")
    umbrella = base
    for u in units:
        u["command"] = base + " --unit-id %s" % u["unit_id"]
        u["selected"] = bool(orchestrated)
    mode = "orchestrated" if orchestrated else "umbrella"
    return {
        "mode": mode,
        "orchestrated": bool(orchestrated),
        "umbrella_command": umbrella,
        "command": "" if orchestrated else umbrella,
        "units": units,
        "selected_command": ((units[0]["command"] if units else umbrella)
                             if orchestrated else umbrella),
        "provider_slots": _sc.PROVIDER_SLOTS, "reserve": _sc.RESERVE,
        "builder_agent_units": len(units), "media_concurrency": len(units),
        "note": "Choose ONE: umbrella (3 provider jobs in 3 threads, ONE agent "
                "unit) OR orchestrated (3 units, ONE variant each, 1 job per "
                "unit). Never both: that pays for nine generations.",
        "overlap_min_s": _sc.OVERLAP_MIN_S,
    }


# ── Music stage lifecycle: the ONE owner of the music row ───────────────────
#
# `next` only reads the store, and nothing ever claimed or completed the music
# row, so a run that had bought and reconciled every song still read music =
# NOT_STARTED and continuity-bible was never eligible. `music` is the parent
# owner of that row (INSTRUCTIONS step 8: claim, work, register, independent
# QC, guarded transition): start = claim or resume, the two waiting states,
# and complete = song gate + audio on disk + independent qc_gate PASS, then
# QC -> COMPLETE. Variant workers own their take folders, never a second claim
# on music. This command never buys, never regenerates, never invents a pick.

MUSIC = "music"
_MUSIC_TO = {"wait-provider": "WAITING_PROVIDER", "wait-approval": "WAITING_APPROVAL",
             "resume": "RUNNING", "park": "PARKED", "reopen": "READY"}
_MUSIC_ACTIONS = ("start", "complete", "fail") + tuple(_MUSIC_TO)
_AUDIO_EXT = (".mp3", ".wav", ".flac", ".m4a", ".aac")
# ponytail: a client's song pick can take a day; same lease the storyboard
# approval wait uses. Make it a flag when a client needs longer.
_APPROVAL_LEASE_S = 86400


def _mres(outcome, code, detail, row=None):
    return {"outcome": outcome, "reason_code": code, "detail": detail, "row": row}


def _music_audio(run_dir):
    """Non-empty audio files in $RUN/music (single-song master or picked-song.mp3)."""
    try:
        return sorted(p.name for p in (Path(run_dir) / "music").iterdir()
                      if p.suffix.lower() in _AUDIO_EXT and p.stat().st_size > 0)
    except OSError:
        return []


def _song_hold(run_dir):
    """The existing song-pick / acceptance / constituent gate; fail closed.
    L2 (WW-21): a recorded, well-formed OPERATOR DECISION does not open the
    WW-21 acceptance hold by ITSELF — the decision is recorded at complete
    time (before the hold), and the hold is still evaluated on the take
    records; only a relabel-shaped MANUAL_RELABEL refusal stays absolute."""
    try:
        sc = _core_mod("song_choices")
        ref = sc.refusal(str(run_dir))
        if ref is not None and ref.get("reason_code") == "ACCEPTANCE_NOT_PROVEN":
            sd = _core_mod("song_dispatch")
            dec = sd.read_operator_decision(str(run_dir))
            if dec is not None:
                dec, rs = sd.decision_applies(str(run_dir), dec=dec)
                if dec is not None and not rs:
                    return None            # recorded decision + honest record; the hold opens
        return ref or sc.constituent_hold(str(run_dir))
    except Exception as exc:  # noqa: BLE001 - a broken gate never opens
        return {"reason_code": "SONG_GATE_BROKEN", "detail": repr(exc)[:200]}


def music_stage(run_dir, owner, action, run_id=None, reason=None,
                retryable=False, qc=None, lease_s=3600, operator_decision=None):
    """One guarded lifecycle step on the music row. Returns _mres(...).

    Idempotent: COMPLETE answers with the existing row; the live owner calling
    start again heartbeats and resumes (no second claim); another live owner is
    refused; an expired RUNNING lease is reclaimed by state_store.claim. Every
    write is a version-predicated state_store call, so TRANSITIONS is the law.
    qc = {"records": [...], "makers": {...}, "required": [...]} for complete.
    operator_decision = the L2 (WW-21) recorded operator-decision doc for
    complete: NEVER a PASS for a measured gate -- the WW-21 boundary still
    applies and the stage holds at ACCEPTANCE_NOT_PROVEN until every gate is
    proven OR the operator has explicitly accepted the named gates as NOT
    proven (a decision is not a relabel; `_MANUAL_SOURCES` refusals stand).
    """
    core = str(Path(__file__).resolve().parent.parent)
    if core not in sys.path:
        sys.path.insert(0, core)
    import state_store as ss  # noqa: PLC0415
    db = Path(run_dir) / "control" / "state.sqlite3"
    if not db.exists():
        return _mres("error", "state-file-missing", str(db))
    try:
        st = ss.Store(db)
    except ss.StoreError as e:
        return _mres("error", e.code, str(e))
    row = None
    try:
        rid = run_id
        if not rid:
            ids = [r[0] for r in st.con.execute(
                "SELECT DISTINCT run_id FROM stages WHERE stage=?", (MUSIC,))]
            if len(ids) != 1:
                return _mres("error", "music-run-id-ambiguous",
                             "store holds %d music rows %r; pass --run-id" % (len(ids), ids))
            rid = ids[0]
        row = st.get(rid, MUSIC)
        state = row["state"]
        live = bool(row["owner"]) and (row["lease_expires"] or 0) > time.time()
        if state == "COMPLETE" and action in ("start", "complete"):
            return _mres("ok", "music-complete", "music is already COMPLETE; no new work", row)

        if action == "start":
            waiting = ("WAITING_PROVIDER", "WAITING_APPROVAL")
            if state in ("RUNNING", "QC") + waiting and live and row["owner"] == owner:
                row = st.heartbeat(rid, MUSIC, owner, lease_s=lease_s)
                return _mres("ok", "music-resumed",
                             "%s already holds music (%s); lease extended, resume the "
                             "existing work, never resubmit a ledger-known job" % (owner, state), row)
            if state in waiting:
                if live:
                    return _mres("rejected", "NOT_OWNER", "lease held by %s" % row["owner"], row)
                return _mres("rejected", "LEASE_EXPIRED_WAITING",
                             "the %s lease expired: reconcile the spend ledger's acknowledged "
                             "jobs first, then `music --action resume` under the recovering "
                             "worker id; never resubmit a paid job to recover" % state, row)
            if state == "NOT_STARTED":
                row = st.transition(rid, MUSIC, "READY", owner, expected_version=row["version"])
            row = st.claim(rid, MUSIC, owner, lease_s=lease_s, expected_version=row["version"])
            return _mres("ok", "music-claimed", "%s owns music (RUNNING)" % owner, row)

        if action != "complete":
            to = _MUSIC_TO.get(action) or ("FAILED_RETRYABLE" if retryable else "FAILED_BLOCKED")
            row = st.transition(rid, MUSIC, to, owner, expected_version=row["version"],
                                reason=reason)
            if row["owner"] == owner and to in ("RUNNING", "WAITING_PROVIDER", "WAITING_APPROVAL"):
                row = st.heartbeat(rid, MUSIC, owner, lease_s=max(
                    lease_s, _APPROVAL_LEASE_S if to == "WAITING_APPROVAL" else 0))
            elif to == "RUNNING":       # recovering worker after an expired lease
                row = st.claim(rid, MUSIC, owner, lease_s=lease_s,
                               expected_version=row["version"])
            out = {"PARKED": "parked", "FAILED_BLOCKED": "rejected"}.get(to, "ok")
            return _mres(out, "music-" + to.lower().replace("_", "-"),
                         "music %s -> %s" % (state, to), row)

        # complete
        if row["owner"] != owner or not live:
            return _mres("rejected", "NOT_OWNER",
                         "complete needs the live music lease (run `music --action start` "
                         "first); row owner %r state %s" % (row["owner"], state), row)
        if state not in ("RUNNING", "WAITING_APPROVAL", "QC"):
            return _mres("rejected", "ILLEGAL_TRANSITION",
                         "complete from %s: reconcile and `--action resume` first" % state, row)

        def block(code, why):
            r = st.transition(rid, MUSIC, "FAILED_BLOCKED", owner,
                              expected_version=row["version"], reason="%s: %s" % (code, why)[:500])
            return _mres("rejected", code, why, r)

        # L2 (WW-21): the operator decision, when supplied, is validated and
        # recorded BEFORE the hold, so `_song_hold` can honour it. It never
        # opens the WW-21 boundary by itself (a measured gate is never
        # re-labelled PASS) and never rewrites a take record; it says the run
        # may advance with the named gates NOT PROVEN -- and a relabel-shaped
        # MANUAL_RELABEL refusal is never decided around.
        if operator_decision is not None:
            sd = _core_mod("song_dispatch")
            try:
                sd.record_operator_decision(str(run_dir), operator_decision,
                                            required=None)
            except Exception as e:  # noqa: BLE001 - a bad decision writes nothing
                why = str(e)
                return block("OPERATOR_DECISION_REJECTED",
                             why[why.find("OPERATOR_DECISION_REJECTED:"):]
                             if "OPERATOR_DECISION_REJECTED:" in why else why[:500])
        hold = _song_hold(run_dir)
        if hold:
            code, why = hold["reason_code"], hold.get("detail") or hold.get("next_action", "")
            if code == "SONG_GATE_BROKEN":
                return _mres("error", code, why, row)
            # SONG-FAILURE VERDICT BELONGS TO THE CLIENT (order 2026-10-21).
            # When the song judge failed a take this command NEVER regenerates
            # and never loops: the stage waits on the client's ONE answer,
            # recorded in song-choices/fork-decision.json. That answer is
            # authoritative -- redo_all / new_three send the run back to READY
            # for a fresh round the CLIENT asked for; keep_one is recorded but
            # the measured gates below still decide (a decision never writes a
            # PASS for a measured gate).
            if code in ("SONG_CONSTITUENT_EVIDENCE_MISSING",
                        "ACCEPTANCE_NOT_PROVEN") and operator_decision is None:
                sc = _core_mod("song_choices")
                try:
                    dec = sc.fork_decision(str(run_dir))
                except Exception as e:  # noqa: BLE001 - unreadable fork is no answer
                    return _mres("error", "SONG_FORK_UNREADABLE", repr(e)[:200], row)
                if dec is None:
                    if state != "WAITING_APPROVAL":
                        row = st.transition(rid, MUSIC, "WAITING_APPROVAL", owner,
                                            expected_version=row["version"],
                                            reason="song judge failed: client fork")
                    row = st.heartbeat(rid, MUSIC, owner,
                                       lease_s=max(lease_s, _APPROVAL_LEASE_S))
                    return _mres("waiting", "SONG_FAILURE_AWAITING_CLIENT",
                                 "%s. My notes: %s" % (sc.FAILURE_FORK, why), row)
                if dec.get("answer") in ("redo_all", "new_three"):
                    # The client ASKED for a fresh round. The row goes back to
                    # RUNNING under the live owner (the one transition
                    # state_store allows from a waiting state) and the worker
                    # may buy the next round -- a client-authorized retry,
                    # never an automatic one.
                    row = st.transition(rid, MUSIC, "RUNNING", owner,
                                        expected_version=row["version"],
                                        reason="client chose %s" % dec.get("answer"))
                    row = st.heartbeat(rid, MUSIC, owner, lease_s=lease_s)
                    return _mres("ok", "music-client-redo",
                                 "client chose %r; run the next round with "
                                 "`music --action start` (same owner)" % dec.get("answer"), row)
                why = "client kept a take (%r), but the measured gates still " \
                      "hold: %s" % (dec.get("answer"), why)
            if code != "SONG_PICK_MISSING":
                return block(code, why)
            if state == "QC":
                row = st.transition(rid, MUSIC, "RUNNING", owner, expected_version=row["version"])
            if row["state"] == "RUNNING":
                row = st.transition(rid, MUSIC, "WAITING_APPROVAL", owner,
                                    expected_version=row["version"])
            row = st.heartbeat(rid, MUSIC, owner, lease_s=max(lease_s, _APPROVAL_LEASE_S))
            return _mres("waiting", code, why, row)
        audio = _music_audio(run_dir)
        if not audio:
            return block("MUSIC_AUDIO_MISSING",
                         "no non-empty audio in %s" % (Path(run_dir) / "music"))
        qc = qc or {}
        qg = _core_mod("qc_gate")
        try:
            res = qg.evaluate(rid, MUSIC, qc.get("records"), qc.get("makers"),
                              qc.get("required"))
        except Exception as e:  # noqa: BLE001 - bad QC input: nothing written
            return _mres("error", getattr(e, "code", "qc-input-invalid"), str(e)[:300], row)
        if state != "QC":
            row = st.transition(rid, MUSIC, "QC", owner, expected_version=row["version"])
        if res["gate"] != "PASS":
            # Operator order 2026-10-21: a recorded operator decision overcomes
            # a QC block. NOTHING is relabelled -- the failed checks stay FAIL
            # in the evidence, and the acceptance is its own audited artifact.
            if operator_decision is not None:
                import json as _json
                import time as _time
                failed = [f.get("check_id") or f.get("code") or ""
                          for f in (res.get("failures") or [])]
                acc_dir = Path(run_dir) / "music" / "acceptance"
                acc_dir.mkdir(parents=True, exist_ok=True)
                rec = {
                    "schema_version": "blackceo.qc-risk-acceptance/v1",
                    "decision": "QC_ACCEPTED_RISK",
                    "operator": owner,
                    "at_utc": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
                    "qc_gate": res.get("gate"),
                    "reason_code": res.get("reason_code"),
                    "failed_checks": failed,
                    "failures": res.get("failures") or [],
                    "operator_decision": operator_decision,
                }
                (acc_dir / "qc-risk-acceptance.json").write_text(
                    _json.dumps(rec, indent=1, default=str))
                row = st.transition(rid, MUSIC, "COMPLETE", owner,
                                    expected_version=row["version"],
                                    reason="QC_ACCEPTED_RISK by %s: %s; failed %s"
                                    % (owner, res.get("reason_code"),
                                       ",".join(failed)[:200]))
                return _mres("ok", "music-complete-accepted-risk",
                             "music COMPLETE under recorded operator risk "
                             "acceptance (%s); failed checks kept FAIL: %s"
                             % (res.get("reason_code"), ",".join(failed)[:160]), row)
            return block("QC_" + res["gate"], res["reason_code"])
        row = st.transition(rid, MUSIC, "COMPLETE", owner, expected_version=row["version"],
                            reason="qc %s; audio %s" % (res["reason_code"], ",".join(audio)))
        return _mres("ok", "music-complete", "music COMPLETE: %s" % ",".join(audio), row)
    except ss.StoreError as e:
        return _mres("rejected", e.code, str(e), row)
    finally:
        st.close()


def cmd_music(a):
    run_dir = Path(a.run_dir).expanduser().resolve()
    qc = None
    od = None
    if a.action == "complete":
        try:
            qc = {"records": _load(a.records) if a.records else [],
                  "makers": _load(a.makers) if a.makers else {},
                  "required": [c.strip() for c in (a.required or "").split(",") if c.strip()]}
        except (OSError, ValueError) as e:
            return envelope("music", run_dir.name or "run", "error", "qc-input-unreadable", str(e)[:200])
        # L2 (WW-21): the documented operator decision rides `complete`. Missing
        # file = None; unreadable file = a loud refusal (never a silent pass).
        if a.operator_decision:
            try:
                od = _load(a.operator_decision)
            except (OSError, ValueError) as e:
                return envelope("music", run_dir.name or "run", "error",
                                "OPERATOR_DECISION_UNREADABLE",
                                "%s: %s" % (a.operator_decision, str(e)[:200]))
    r = music_stage(run_dir, a.owner, a.action, run_id=a.run_id, reason=a.reason,
                    retryable=a.retryable, qc=qc, lease_s=a.lease_s,
                    operator_decision=od)
    return envelope("music", run_dir.name or "run", r["outcome"], r["reason_code"],
                    r["detail"], data={"stage": MUSIC, "row": r["row"]})


def _music_lifecycle():
    """The commands `next` hands out with the music stage (descriptor only)."""
    base = ("python3 scripts/core/intake_preflight/factory.py music "
            "--run-dir \"$RUN\" --owner <worker id> --action ")
    return {"start": base + "start",
            "wait_provider": base + "wait-provider",
            "resume": base + "resume",
            "complete": base + "complete --records \"$RUN/music/qc-records.json\" "
                        "--makers \"$RUN/music/makers.json\" --required <required-checks>",
            "note": "Claim music BEFORE any generation, complete it after the pick and "
                    "independent QC; continuity-bible is never eligible until then. "
                    "When the WW-21 gates fail on MEASURED evidence and the run owner "
                    "accepts them unproven, complete with --operator-decision <path> "
                    "(music/acceptance/operator-decision.json: decision ACCEPTED_RISK, "
                    "operator, at_utc, gates_not_proven, measured_evidence_digest, "
                    "reason) -- it never writes a PASS for a measured gate."}


# ── W2-wiring-U1: purpose routing, method gates, Agnes routing ──────────────
#
# Inert until the run carries control/method.json (purpose routing) or the
# receipt's agnes.answer == "yes" (the Agnes path): a run with neither answers
# exactly what it answered before this unit landed (SPEC "inert-until-wired").
# The modules these routes read (length_formula, method_plan, agnes_plan,
# agnes_quota, onscreen_text) belong to other units of this program, so every
# import below is guarded the way factory.py already guards lane_size and the
# approval runner: a module this box does not carry yet degrades that one line
# of data, never the command.

_PAID_STAGES = ("music", "image-keyframes", "video-generation")
#: Method gate -> the stop whose completion records it (METHOD-INTEGRATION 5).
_GATE_STAGE = (("A", "creative-strategy"), ("B", "script-lyrics"),
               ("C", "music"), ("D", "storyboard"),
               ("E", "final-qc"), ("F", "delivery"))
#: Method 11.3's four levels, verbatim. This unit writes only the first three:
#: an approval is a recorded human answer, which the factory never has (C6).
_GATE_LEVELS = ("planned", "generated", "inspected", "approved")
#: The social/paid purposes that run platform_fit.check before delivery (F13).
_PLATFORM_PURPOSES = ("paid_ad", "short_post")

def _core_mod(name):
    """`<core>/<name>/<name>.py`, then a plain module of that name; None when
    the box carries neither (the W1 units land on their own branches)."""
    core = str(Path(__file__).resolve().parent.parent)
    if core not in sys.path:
        sys.path.insert(0, core)
    try:
        return __import__("%s.%s" % (name, name), fromlist=[name])
    except Exception:                               # noqa: BLE001
        try:
            return __import__(name)
        except Exception:                           # noqa: BLE001
            return None

def _read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        return default
    return doc if isinstance(doc, dict) else default

# ── L4-RL4 (v2.9.73 reliability): reconcile / stale-session / forks ─────────
#
# Live proof (Voyage To Virtue, 2026-10-20/21): storyboard gate.json was
# approved with shots and stills on disk while the stages row read
# NOT_STARTED, so `next` kept handing back the music command; a money
# question sat for hours with no safe default; long-lived sessions ran code
# older than the installed skill, so three merged fixes could not reach
# them; and 65 identical lip-sync failures had no early abort.

#: L4.2: the skill version this PROCESS started on, read once at import.
#: `next` (and every other subcommand's run) compares it with the version
#: installed on disk and refuses to continue a run when the installed one is
#: newer — the process would otherwise silently keep running stale code.
def _skill_version_at_boot():
    # an explicit launcher override wins (documented: the process records
    # what it booted on when the file layout makes a plain read ambiguous)
    env = os.environ.get("DSAF_BOOT_SKILL_VERSION")
    if env:
        return env.strip()
    try:
        return (Path(__file__).resolve().parents[3] / "skill-version.txt") \
            .read_text(encoding="utf-8").strip()
    except OSError:
        return ""

_BOOT_SKILL_VERSION = _skill_version_at_boot()

def _skill_version_on_disk():
    try:
        return (Path(__file__).resolve().parents[3] / "skill-version.txt") \
            .read_text(encoding="utf-8").strip()
    except OSError:
        return ""

def _stale_session():
    """(stale, boot_version, disk_version): L4.2 — the installed skill is
    NEWER than the version this process recorded at start. An equal or older
    disk version, or a version this process could not read at boot (a run
    inside a bare install where skill-version.txt sits elsewhere), is never
    stale. Restart is the remedy; no stage command is ever handed out by a
    process on obsolete code."""
    boot, disk = _BOOT_SKILL_VERSION, _skill_version_on_disk()
    if not boot or not disk or disk == boot:
        return False, boot, disk

    def parts(v):
        try:
            return tuple(int(x) for x in v.lstrip("v").split(".")[:4])
        except ValueError:
            return ()
    try:
        pb, pd = parts(boot), parts(disk)
    except Exception:                                # noqa: BLE001
        return False, boot, disk
    if not pb or not pd:
        return False, boot, disk
    return pd > pb, boot, disk

_MUSIC = "music"
_RECON_OWNER = "reconcile"

def _proven_storyboard(run_dir, run_id=""):
    """(proven, evidence): the storyboard's OWN approval artifacts, all on
    disk — gate.json's approved shots, approval.json state "approved", and
    every stills.json path a non-empty file. No shot is approved that is not
    in the approved set."""
    sb = Path(run_dir) / "storyboard"
    gate = _read_json(sb / "gate.json")
    appr = _read_json(sb / "approval.json")
    shots = gate.get("shots") if isinstance(gate, dict) else None
    if not (isinstance(shots, list) and shots
            and isinstance(appr, dict) and appr.get("state") == "approved"):
        return False, {"missing": "gate.json shots or approval.json approved"}
    stills = _read_json(sb / "stills.json")
    paths = [v for v in (stills or {}).values() if isinstance(v, (str, Path))]
    missing = []
    for p in paths:
        try:
            q = Path(p) if Path(p).is_absolute() else Path(run_dir, p)
            if not (q.is_file() and q.stat().st_size > 0):
                missing.append(str(p))
        except OSError:
            missing.append(str(p))
    ev = {"artifacts": ["storyboard/gate.json", "storyboard/approval.json",
                        "storyboard/stills.json"],
          "approved_shots": len(shots), "stills": len(paths),
          "stills_missing": missing}
    return (not missing), ev

def _proven_music(run_dir, run_id=""):
    """(proven, evidence): the music stage's OWN documented complete
    condition, all on disk — the picked file matches pick.json's sha256, the
    pick is the recorded pick (the gate's own refusal is None), and the
    independent QC records written beside it evaluate to PASS via qc_gate.
    Without the QC records the row is never reconciled: no gate is invented."""
    pick = _read_json(Path(run_dir) / "song-choices" / "pick.json")
    picked = Path(run_dir) / "music" / "picked-song.mp3"
    if not (isinstance(pick, dict) and pick.get("sha256")
            and picked.is_file() and picked.stat().st_size > 0):
        return False, {"missing": ["song-choices/pick.json",
                                   "music/picked-song.mp3"]}
    try:
        import hashlib
        h = hashlib.sha256(picked.read_bytes()).hexdigest()
    except OSError:
        return False, {"pick": "unreadable"}
    if h != pick["sha256"]:
        return False, {"sha_mismatch": True}
    ev = {"artifacts": ["song-choices/pick.json", "music/picked-song.mp3"],
          "picked_sha256": h[:12], "qc": None}
    rec_path = Path(run_dir) / "music" / "qc-records.json"
    if not rec_path.is_file():
        ev["qc"] = "records-missing"
        return False, ev
    qg = _core_mod("qc_gate")
    if qg is None:
        ev["qc"] = "qc_gate-unavailable"
        return False, ev
    try:
        with open(rec_path, encoding="utf-8") as f:
            recs = json.load(f)
    except (OSError, ValueError):
        recs = None
    if not isinstance(recs, list) or not recs:
        ev["qc"] = "records-empty"
        return False, ev
    makers = _read_json(Path(run_dir) / "music" / "makers.json", {}) or {}
    # the required checks the record set itself names (same read the CLI's
    # complete step takes); an empty required list is a refusal here too.
    required = sorted({str(r.get("check_id")) for r in recs
                       if isinstance(r, dict) and r.get("check_id")})
    try:
        res = qg.evaluate(run_id or "reconcile", _MUSIC, recs, makers,
                          required)
    except Exception:                                # noqa: BLE001
        ev["qc"] = "records-unreadable"
        return False, ev
    ev["qc"] = {"gate": res.get("gate"), "reason_code": res.get("reason_code")}
    return res.get("gate") == "PASS", ev

#: stage -> proven-artifact predicate. The ONLY reconciled stages: each
#: predicate reads exactly the artifacts its OWN stage gate writes.
_RECONCILIERS = {"storyboard": _proven_storyboard, "music": _proven_music}

def _reconcile_stages(run_dir, got):
    """L4.1: reconcile stage rows from proven artifacts through state_store.

    Returns (reconciled_rows, fresh_states). Proven: the runbook's own
    artifact set for a stage exists and its own gate evaluates PASS. Only
    non-terminal rows move, every write is a guarded state_store transition /
    claim under owner "reconcile" (version CAS + event trail) — never a
    hand-written sqlite UPDATE — and a live foreign lease is never seized.
    A stage whose artifacts do not prove completion is untouched.
    """
    out = []
    db = Path(run_dir) / "control" / "state.sqlite3"
    if not db.exists():
        return out, got
    try:
        import state_store as ss  # noqa: PLC0415
        st = ss.Store(db)
    except Exception:                                # noqa: BLE001
        return out, got
    try:
        ids = [r[0] for r in st.con.execute("SELECT DISTINCT run_id FROM stages")]
        if len(ids) == 1:
            rid = ids[0]
        else:
            rid = run_dir.name or "run"
            if rid not in ids:
                return out, got
        for stage, probe in _RECONCILIERS.items():
            try:
                row = st.get(rid, stage)
            except ss.StoreError:
                continue
            if row["state"] not in ("NOT_STARTED", "WAITING_APPROVAL",
                                    "WAITING_PROVIDER", "READY", "RUNNING",
                                    "PARKED"):
                continue
            proven, ev = probe(run_dir, run_id=rid)
            if not proven:
                continue
            from_state = row["state"]
            now = time.time()
            if row["owner"] and now < (row["lease_expires"] or 0) \
                    and row["owner"] != _RECON_OWNER:
                out.append({"stage": stage, "from_state": from_state,
                            "to_state": from_state,
                            "skipped": "live lease held by %s" % row["owner"]})
                continue
            try:
                if from_state == "NOT_STARTED":
                    row = st.transition(rid, stage, "READY", _RECON_OWNER,
                                        expected_version=row["version"])
                if row["state"] in ("READY", "PARKED", "FAILED_RETRYABLE",
                                    "WAITING_APPROVAL", "WAITING_PROVIDER"):
                    row = st.claim(rid, stage, _RECON_OWNER, lease_s=60,
                                   expected_version=row["version"])
                targets = ("QC", "COMPLETE") if stage == _MUSIC else ("COMPLETE",)
                for to in targets:
                    if row["state"] == to:
                        break
                    row = st.transition(rid, stage, to, _RECON_OWNER,
                                        expected_version=row["version"],
                                        reason="reconciled from proven "
                                               "artifacts on disk")
            except ss.StoreError as e:
                out.append({"stage": stage, "from_state": from_state,
                            "to_state": from_state, "error": e.code,
                            "detail": str(e)[:160]})
                continue
            out.append({"stage": stage, "from_state": from_state,
                        "to_state": row["state"], "evidence": ev})
        fresh = {r[0]: r[1] for r in st.con.execute(
            "SELECT stage, state FROM stages WHERE run_id=?", (rid,))}
        got.update(fresh)
        return out, got
    finally:
        st.close()

# ── L4.5: the cost/approval fork and its safe default ──────────────────────
#
# A run must not sit for hours on a small money question. When `next` meets a
# fork whose paid branch is bigger than the remaining ledger balance, the
# recorded decision is the FREE branch — never a spend above the balance or
# above the run's declared budget. A fork whose paid branch fits is recorded
# as "proceed" and the paid command stays in the envelope; the decision, the
# remaining balance and the fork's two costs are written to
# control/fork-decisions.json (append, never clobber) and returned on the
# envelope. No balance readable -> WAIT (the only safe default), never spend.

_FORK_DECISIONS = "fork-decisions.json"

def _remaining_ledger_balance(run_dir):
    """Minor units left on this run's own spend ledger, or None (never a
    guess: a ledger that is unreachable or holds no such run is None — and
    None means WAIT below, the safe default)."""
    db = Path(run_dir) / "spend.sqlite3"
    if not db.exists():
        return None
    rid = (run_dir.name or "run")
    try:
        import spend_ledger as sl  # noqa: PLC0415
    except Exception:                                # noqa: BLE001
        return None
    # the run's id: exactly one on the ledger answers for it; anything else
    # must be the run dir's own name (a run folder named for its run id).
    try:
        import sqlite3
        con = sqlite3.connect("file:%s?mode=ro" % db, uri=True, timeout=5)
        try:
            ids = [r[0] for r in con.execute("SELECT run_id FROM runs")]
        finally:
            con.close()
    except Exception:                                # noqa: BLE001
        return None
    if len(ids) == 1:
        rid = ids[0]
    elif rid not in ids:
        return None
    s = sl.summary(str(db), rid)
    if s.get("outcome") != "ok" \
            or (s.get("evidence") or {}).get("run_status") != "active":
        return None
    try:
        rem = int(s["evidence"]["remaining_budget"])
    except (KeyError, TypeError, ValueError):
        return None
    return rem

def cost_fork(run_dir, fork_id, paid_cost_minor, label="",
              budget_minor=None, now=None):
    """One cost fork, decided. Returns the decision dict.

    paid_cost_minor: what the paid branch costs (None = unknown — unknown
    is never auto-spent; the decision is WAIT). budget_minor: the run's
    declared ceiling (optional; a fork is never auto-passed above it even
    when the ledger could). The recorded decision is "proceed" ONLY when the
    cost is a number > 0 and it fits BOTH the remaining ledger balance and
    the declared budget; every other case records the safe default "wait",
    which spends nothing and leaves the client question standing.
    Writes/merges $RUN/control/fork-decisions.json (one line appended inside
    the JSON doc) and never answers above budget.
    """
    now = now or time.time()
    at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
    rem = _remaining_ledger_balance(run_dir)
    cost = paid_cost_minor
    fits_balance = (isinstance(cost, int) and not isinstance(cost, bool)
                    and cost > 0 and rem is not None and cost <= rem)
    fits_budget = (not isinstance(budget_minor, int) or isinstance(budget_minor, bool)
                   or budget_minor < 0 or
                   (isinstance(cost, int) and not isinstance(cost, bool)
                    and cost <= budget_minor))
    cost_known = (isinstance(cost, int) and not isinstance(cost, bool)
                  and cost > 0)
    if cost_known and fits_balance and fits_budget:
        decision, why = "proceed", "cost fits the remaining ledger balance"
    else:
        decision = "wait"
        if not cost_known:
            why = "unknown cost: never auto-spent"
        elif rem is None:
            why = "no readable ledger balance: the safe default is wait"
        elif not fits_balance:
            why = ("cost %d over the remaining ledger balance %s"
                   % (cost, rem))
        else:
            why = ("cost %d over the run's declared budget %s"
                   % (cost, budget_minor))
    rec = {"fork_id": str(fork_id), "decision": decision, "label": str(label),
           "cost_minor": cost, "remaining_balance_minor": rem,
           "budget_minor": budget_minor, "at_utc": at, "reason": why}
    p = Path(run_dir) / "control" / _FORK_DECISIONS
    doc = _read_json(p, {}) or {}
    log = doc.get("forks")
    log = log if isinstance(log, list) else []
    log.append(rec)
    out = dict(doc, forks=log)
    try:
        _write_json(p, out)
        rec["recorded"] = True
        rec["path"] = str(p)
    except OSError:
        rec["recorded"] = False          # the decision still rides the envelope
    return rec

def _write_json(path, doc):
    """Atomic write beside the target (never a copy anywhere else)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("%s.%d.tmp" % (path.name, os.getpid()))
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)

def _method_record(run_dir):
    """control/method.json (SPEC B1); None until the card's recap confirmed."""
    return _read_json(Path(run_dir) / "control" / "method.json")

def _agnes_answer(run_dir):
    """The receipt's agnes.answer, or None when this run never answered."""
    rec = _read_json(Path(run_dir) / "control" / "card-receipt.json", {}) or {}
    block = rec.get("agnes")
    if isinstance(block, dict) and block.get("answer") in ("yes", "no"):
        return block["answer"]
    return None

def _agnes_progress(run_dir):
    """control/agnes-progress.json (SPEC A11); None before the job starts."""
    return _read_json(Path(run_dir) / "control" / "agnes-progress.json")

def _sync_gates(run_dir, method, got):
    """Record gates A-F in control/method.json (F17).

    Every gate is present and ``planned`` (the card writes that), and is raised
    to ``inspected`` once its own stop is COMPLETE in this run's own state
    store: a stage that finished has been through its gate record, which is
    inspection. ``approved`` is never written here -- it needs a recorded client
    or Trevor answer (SPEC C6). Only a change is written, atomically, and no
    level ever moves back.
    """
    if not isinstance(method, dict):
        return method
    gates = method.get("gates")
    gates = dict(gates) if isinstance(gates, dict) else {}
    changed = False
    for key in "ABCDEF":
        if gates.get(key) not in _GATE_LEVELS:
            gates[key] = "planned"
            changed = True
    for key, stage in _GATE_STAGE:
        if got.get(stage) == "COMPLETE" and gates.get(key) == "planned":
            gates[key] = "inspected"
            changed = True
    if not changed:
        return method
    out = dict(method)
    out["gates"] = gates
    try:
        _write_json(Path(run_dir) / "control" / "method.json", out)
    except OSError:        # the envelope still reports the levels it would set
        pass
    return out

def _method_block(method):
    """What `next` says about this run's purpose routing (F17, F13, METHOD 4)."""
    if not isinstance(method, dict) or not method.get("purpose"):
        return None
    purpose = method["purpose"]
    out = {"purpose": purpose,
           "platform": method.get("platform"),
           "output_types": method.get("output_types"),
           "gates": method.get("gates") or {},
           #: METHOD-INTEGRATION 4: a lesson's product checks read as lesson
           #: checks -- the connection target measures the point, no offer.
           "product_checks": "lesson" if purpose == "lesson" else "product"}
    if purpose == "testimonial":
        out["testimonial_permission"] = method.get("testimonial_permission")
    if purpose == "campaign":
        out["derivatives"] = ["trailer-60", "trailer-90", "ad-60", "ad-90"]
    if purpose in _PLATFORM_PURPOSES:
        out["platform_fit"] = "required-before-delivery"
    return out

def _method_plan_block(run_dir, method):
    """The method length plan and the blueprint check, built before script-lyrics.

    `length_formula.plan` is the ONE length function; one that predates the
    method row takes no flag and falls back to the same plan without it. The
    blueprint is this run's own creative/blueprint.json: absent means not
    written yet (nothing to refuse), rejected refuses before any script-lyrics
    spend, and method_plan not being on this box reports UNDETERMINED -- never
    a pass.
    """
    out = {"length_plan": None, "blueprint_check": None}
    chosen = method.get("chosen_length_s") if isinstance(method, dict) else None
    lf = _core_mod("length_formula")
    if lf is not None and isinstance(chosen, int):
        try:
            try:
                out["length_plan"] = lf.plan(chosen, method=True)
            except TypeError:      # before the method row landed in that function
                out["length_plan"] = lf.plan(chosen)
        except Exception:                         # noqa: BLE001 - never blocks the stage
            out["length_plan"] = None
    blueprint = _read_json(Path(run_dir) / "creative" / "blueprint.json")
    mp = _core_mod("method_plan")
    if mp is None:
        out["blueprint_check"] = {
            "status": "UNDETERMINED",
            "detail": "method_plan is not on this box; the blueprint was not checked"}
    elif blueprint is None:
        out["blueprint_check"] = {
            "status": "pending",
            "detail": "creative/blueprint.json is written at this stage"}
    else:
        try:
            out["blueprint_check"] = mp.validate(blueprint, method)
        except Exception as exc:                  # noqa: BLE001
            out["blueprint_check"] = {"status": "UNDETERMINED",
                                      "detail": str(exc)[:200]}
    return out

def _pace_into_music(run_dir, method):
    """method_plan.pace_order + true_at_beat into the music request (F17).

    The request builder reads both keys, so they are written into
    $RUN/music/req.json when that file already exists and are always returned
    for whoever builds it. No blueprint means no seam is ever invented (the
    rule pace_order itself keeps), so the request is left alone.
    """
    blueprint = _read_json(Path(run_dir) / "creative" / "blueprint.json")
    mp = _core_mod("method_plan")
    if mp is None or not isinstance(method, dict) or not blueprint:
        return {"available": False}
    try:
        order = mp.pace_order(blueprint) or {}
    except Exception as exc:                      # noqa: BLE001
        return {"available": False, "detail": str(exc)[:200]}
    if not order:
        return {"available": False}
    out = {"available": True, "pace_order": order,
           "true_at_beat": order.get("true_at_beat")}
    req = Path(run_dir) / "music" / "req.json"
    doc = _read_json(req)
    if isinstance(doc, dict):
        merged = dict(doc)
        merged["pace_order"] = order
        if out["true_at_beat"]:
            merged["true_at_beat"] = out["true_at_beat"]
        try:
            _write_json(req, merged)
            out["written_into_request"] = True
        except OSError:
            out["written_into_request"] = False
    return out

def _agnes_segment_total(run_dir, method, prog):
    """How many fixed 10-second segments the delivered timeline is cut into."""
    if isinstance(prog, dict):
        try:
            total = int(prog.get("clips_total"))
        except (TypeError, ValueError):
            total = 0
        if total > 0:
            return total
    chosen = method.get("chosen_length_s") if isinstance(method, dict) else None
    if not isinstance(chosen, int) or chosen <= 0:
        return None
    delivered = max(1, chosen - 2)   # delivered length = chosen - 2 (SKILL 613)
    ap = _core_mod("agnes_plan")
    if ap is not None:
        try:
            return int(len(ap.segments(delivered)))
        except Exception:                         # noqa: BLE001
            pass
    return -(-delivered // 10)                    # ceil(delivered / 10), A5.1

def _agnes_wait_reason(prog):
    """Why `next` answers waiting instead of a segment job (SPEC A11)."""
    if not isinstance(prog, dict):
        return None
    reason = str(prog.get("waiting_reason") or "").strip()
    if reason:
        return reason
    try:
        inflight = int(prog.get("in_flight") or 0)
        done = int(prog.get("clips_done") or 0)
        total = int(prog.get("clips_total") or 0)
    except (TypeError, ValueError):
        return None
    if inflight > 0 and total > done:
        return "agnes-video-running"
    return None

def _clips_cut(run_dir):
    """True once $RUN/edit/clips holds a cut file.

    That directory is where the `clips` runbook row writes, so it is what says
    the campaign's trailer/ad step has run and `next` may move on to `delivery`.
    """
    d = Path(run_dir) / "edit" / "clips"
    try:
        return any(p.suffix == ".mp4" and p.stat().st_size > 0
                   for p in d.iterdir())
    except OSError:
        return False

def _agnes_admission(remaining):
    """Whole-run quota admission: run now, or wait for the 00:00 UTC reset.

    Never a partial start, never a run split across days (SPEC A5.3).
    agnes_quota is another unit's module; without it there is no admission
    number to read, so this reports None rather than guessing a pass.
    """
    aq = _core_mod("agnes_quota")
    if aq is None or remaining is None:
        return None
    try:
        # fits_today(clips, now): `now` is a required positional, and the
        # ledger reads os.environ by default. Calling it with one argument
        # raised TypeError, which this bare except swallowed -- so whole-run
        # admission silently reported None on every box and SPEC A5.3 never
        # fired.
        return dict(aq.fits_today(int(remaining), None)) or None
    except Exception:                             # noqa: BLE001
        return None

def cmd_next(a):
    """next --run-dir <dir>: which stage, which command, how many lanes."""
    # L4.2: a process whose skill was updated since it started refuses to
    # continue ANY run — silently running stale code is how merged fixes
    # missed 17-20 h sessions. Both versions are named; restart is the remedy.
    stale, boot_v, disk_v = _stale_session()
    if stale:
        env = envelope("next", "",
                       "error", "SKILL_UPDATED",
                       "The installed skill (%s) is newer than the version "
                       "this process started on (%s). Restart the run "
                       "process so the fixes apply; this process answers no "
                       "stage command." % (disk_v, boot_v),
                       data={"installed_version": disk_v,
                             "boot_version": boot_v})
        env["run_id"] = ""
        return env
    run_dir = Path(a.run_dir or ".").expanduser().resolve()
    db = run_dir / "control" / "state.sqlite3"
    sid = run_dir.name or "run"
    if not db.exists():
        env = envelope("next", str(sid), "error", "state-file-missing",
                       "Create the run first (factory.py intake, then "
                       "preflight); missing state file: %s" % db)
        env["data"] = {"missing_path": str(db)}
        evidence = None
        return env
    stages = _stages()
    if not stages:
        return envelope("next", str(sid), "error", "stage-list-unavailable",
                        "Could not read stage IDs from batch_mode/batch.py.")
    stages_source = "batch_mode STAGES (batch_mode/batch.py:112-125)"
    rows, runbook_path = _runbook_rows()
    # Read-only projection of the store: states already say what is eligible.
    try:
        import sqlite3
        con = sqlite3.connect("file:%s?mode=ro" % db, uri=True, timeout=10)
        try:
            got = dict(con.execute(
                "SELECT stage, state FROM stages ORDER BY rowid").fetchall())
        finally:
            con.close()
    except sqlite3.DatabaseError as e:
        return envelope("next", str(sid), "error", "state-unreadable",
                        "state file unreadable (%s): %s" % (db, str(e)[:120]))
    # L4.1: reconcile the rows from proven artifacts on disk BEFORE the
    # answer — through state_store's guarded transitions only; rows the
    # artifacts do not prove are never touched, and every move it made is
    # carried on the envelope under data.reconciled.
    reconciled, got = _reconcile_stages(run_dir, got)
    blocked = ("COMPLETE", "FAILED_BLOCKED", "PARKED")
    next_stage = None
    for s in stages:
        st = got.get(s)
        if st is None:                    # stage not initialized: still ahead
            next_stage = s
            break
        if st not in blocked:
            next_stage = s
            break
    if next_stage is None:
        return envelope("next", str(sid), "ok", "run-complete",
                        "Every stage is COMPLETE; the run is delivered. "
                        "Nothing left to run.",
                        data={"reconciled": reconciled} if reconciled else {})
    # W2-wiring-U1: what this run is for, and whether Agnes makes its media.
    method = _method_record(run_dir)
    if isinstance(method, dict):
        method = _sync_gates(run_dir, method, got)
    else:
        method = None
    method_block = _method_block(method)
    agnes_answer = _agnes_answer(run_dir)
    if (method_block is not None
            and method.get("purpose") == "testimonial"
            and method.get("testimonial_permission") != "yes"
            and next_stage in _PAID_STAGES):
        # F17 / SPEC B2: PERMISSION = Yes comes before ANY paid job, so the
        # refusal lands before the music stop even opens, not at generation.
        return envelope(
            "next", str(sid), "rejected", "TESTIMONIAL_PERMISSION_MISSING",
            "This is a client success story and the card holds no recorded "
            "PERMISSION = Yes, so stage %r never runs: get the permission and "
            "confirm the card's recap again." % next_stage,
            data={"stage": next_stage, "method": method_block})
    if next_stage == "video-generation":      # storyboard approval point
        ar = _approval_runner()
        if ar is not None and not ar.gate_open(str(run_dir)):
            ans = _studio_answer(run_dir, "storyboard")
            if ans:
                return _studio_apply("next", str(sid), run_dir, next_stage,
                                     "storyboard", ans)
            return envelope("next", str(sid), "waiting", "storyboard-approval-required",
                            "Video is blocked until the storyboard is approved. Run "
                            "`factory.py storyboard --run-dir %s --target <chat id>` "
                            "(sends the shot cards + stills once; reply GO or "
                            "'shot N: change ...' via --reply)." % run_dir,
                            data={"stage": next_stage})
    if (stages.index(next_stage) > stages.index(MUSIC)
            and got.get(MUSIC) in ("FAILED_BLOCKED", "PARKED")):
        # A blocked or parked music row is skipped by the loop above; it must
        # never read as permission for a later stage (fail closed).
        return envelope("next", str(sid), "rejected", "MUSIC_NOT_COMPLETE",
                        "music is %s, so %r never runs: fix the cause, then "
                        "`factory.py music --action reopen` and `--action start`."
                        % (got[MUSIC], next_stage),
                        data={"stage": MUSIC, "blocked_stage": next_stage,
                              "lifecycle": _music_lifecycle()})
    if stages.index(next_stage) > stages.index("music"):    # SONG APPROVAL gate (fail closed)
        try:
            _c = str(Path(__file__).resolve().parent.parent)
            if _c not in sys.path:
                sys.path.insert(0, _c)
            from song_choices import song_choices as _sc  # noqa: PLC0415
            # WW-08 item 3: the pick must be in AND every offered song's
            # constituent-evidence receipt current before a later stage runs.
            # One hold implementation: the same _song_hold the music stage
            # uses, so a recorded operator decision that opens the hold
            # for `music --action complete` also opens it for `next`.
            hold = _song_hold(run_dir)
        except Exception as exc:  # noqa: BLE001 - a broken gate never opens
            hold = {"reason_code": "SONG_GATE_BROKEN", "next_action": "song gate failed: %r" % (exc,)}
        if hold:
            if hold["reason_code"] == "SONG_PICK_MISSING":   # the client's pick, via the studio
                ans = _studio_answer(run_dir, "song")
                if ans:
                    return _studio_apply("next", str(sid), run_dir, next_stage, "song", ans)
            return envelope("next", str(sid), "error", hold["reason_code"], hold["next_action"],
                            data={"stage": next_stage, "detail": hold.get("detail", "")})
    plan_block = None
    if method is not None and next_stage == "script-lyrics":
        # F17: the length plan and the blueprint check happen BEFORE the model
        # call this stage makes, not after it has been paid for.
        plan_block = _method_plan_block(run_dir, method)
        bc = plan_block.get("blueprint_check") or {}
        if bc.get("outcome") == "rejected":
            codes = ", ".join(str(e.get("error"))
                              for e in (bc.get("errors") or [])[:3])
            return envelope(
                "next", str(sid), "rejected",
                str(bc.get("reason_code") or "BLUEPRINT_INVALID"),
                "The Story Beat Blueprint does not pass method_plan.validate "
                "(%s). Fix creative/blueprint.json before any script-lyrics "
                "spend." % codes,
                data={"stage": next_stage, "method_plan": plan_block,
                      "method": method_block})
    if agnes_answer == "yes" and next_stage == "image-keyframes":
        arow = rows.get("agnes-keyframes") or {"command": "", "produces": ""}
        if arow["command"]:
            agnes = {"answer": "yes", "keyframes": arow["command"], "in_flight": 2}
            ot = _core_mod("onscreen_text")
            if ot is not None:
                try:
                    agnes["no_text_block"] = ot.no_text_block()
                except Exception:                          # noqa: BLE001
                    pass
            return envelope(
                "next", str(sid), "ok", "next-stage",
                "Agnes path: these keyframes come from Agnes Image with no words "
                "in the picture; onscreen_text decides bake or overlay per shot.",
                data={"stage": next_stage, "command": arow["command"],
                      "produces": arow["produces"], "lane_size": lane_size_payload(),
                      "stages_source": stages_source, "agnes": agnes,
                      "method": method_block},
                evidence=["%s" % db, runbook_path])
    if agnes_answer == "yes" and next_stage == "video-generation":
        prog = _agnes_progress(run_dir)
        total = _agnes_segment_total(run_dir, method, prog)
        done = 0
        if isinstance(prog, dict):
            try:
                done = max(0, int(prog.get("clips_done") or 0))
            except (TypeError, ValueError):
                done = 0
        if total is None or total < done:
            total = done
        wait = _agnes_wait_reason(prog)
        agnes = {"answer": "yes", "background": True, "in_flight_max": 2,
                 "clips_total": total, "clips_done": done, "waiting_reason": wait}
        if isinstance(prog, dict) and prog.get("next_continue_utc"):
            agnes["next_continue_utc"] = prog["next_continue_utc"]
        admission = _agnes_admission(max(0, total - done))
        if admission is not None:         # whole-run admission, never partial
            agnes["quota"] = admission
            agnes["quota_source"] = "agnes_quota.fits_today"
            if admission.get("fits") is False:
                wait = admission.get("waiting_reason") or "agnes-quota-next-day"
                agnes["next_continue_utc"] = admission.get("next_continue_utc")
        if wait:
            return envelope(
                "next", str(sid), "waiting", str(wait),
                ("Agnes video is running: %d of %d segments made, at most 2 in "
                 "flight. `next` never resubmits a job the ledger already knows."
                 % (done, total)) if wait == "agnes-video-running"
                else ("The whole run will not fit today's Agnes quota, so it "
                      "waits for the next 00:00 UTC reset (%s) and is never "
                      "split across days."
                      % (agnes.get("next_continue_utc") or "next UTC day")),
                data={"stage": next_stage, "agnes": agnes, "method": method_block})
        kie = (rows.get("video-generation") or {}).get("command", "")
        vrow = rows.get("agnes-video-segment") or {"command": "", "produces": ""}
        jobs = [{"segment": n,
                 "command": vrow["command"].replace("<segment>", str(n))}
                for n in range(done + 1, total + 1)] if vrow["command"] else []
        agnes["segment_jobs"] = jobs
        agnes["segment_produces"] = vrow.get("produces", "")
        #: The lip-sync windows keep the KIE Kling row, verbatim and unchanged.
        agnes["kie_lipsync_command"] = kie
        if not jobs:
            if total:
                why = ("Agnes made all %d segments. The lip-sync windows keep "
                       "the KIE Kling row exactly as it is." % total)
            else:
                why = ("No Agnes segment count is known yet (no method length "
                       "and no progress record), so the lip-sync windows keep "
                       "the KIE Kling row exactly as it is.")
            return envelope(
                "next", str(sid), "ok", "next-stage", why,
                data={"stage": next_stage, "command": kie,
                      "produces": (rows.get("video-generation") or {}).get("produces", ""),
                      "lane_size": lane_size_payload(),
                      "stages_source": stages_source, "agnes": agnes,
                      "method": method_block},
                evidence=["%s" % db, runbook_path])
        return envelope(
            "next", str(sid), "ok", "next-stage",
            "Agnes path: run the segment jobs as a background job, 2 in flight, "
            "polling no faster than every 15 seconds; `next` answers waiting "
            "while they run.",
            data={"stage": next_stage, "command": jobs[0]["command"],
                  "produces": agnes["segment_produces"],
                  "lane_size": lane_size_payload(),
                  "stages_source": stages_source, "agnes": agnes,
                  "method": method_block},
            evidence=["%s" % db, runbook_path])
    # W2-wiring-U1 (F17 / SPEC C5): a campaign run gets the trailer stage, and
    # the two rows are one clip_cutdown command read two ways (F10 / F19).
    # `clips` is a runbook stage, not a batch state row, so it is presented in
    # front of `delivery` and lasts until it has cut its files.
    row_id = next_stage
    if (method is not None and method.get("purpose") == "campaign"
            and next_stage == "delivery" and not _clips_cut(run_dir)
            and (rows.get("trailers") or {}).get("command")):
        row_id = "trailers"
    present_id = "clips" if row_id == "trailers" else next_stage
    row = rows.get(row_id) or rows.get(next_stage) or {"command": "", "produces": ""}
    if not row["command"]:
        return envelope("next", str(sid), "error", "runbook-row-missing",
                        "No runbook row for stage %r in %s"
                        % (next_stage, runbook_path))
    platform_fit = None
    if (method is not None and next_stage == "delivery"
            and method.get("purpose") in _PLATFORM_PURPOSES
            and (rows.get("platform-fit") or {}).get("command")):
        pfrow = rows["platform-fit"]
        platform_fit = {
            "required": True,
            "command": pfrow["command"],
            "placement": method.get("platform") or (
                "organic" if method.get("purpose") == "short_post" else "meta"),
            "produces": pfrow["produces"]}
    music_request = (_pace_into_music(run_dir, method)
                     if method is not None and next_stage == "music" else None)
    sa = None
    if next_stage == "music":
        sa = _script_gate(run_dir, a, reply=None)
        if sa["outcome"] != "go":
            if sa["outcome"] == "waiting":      # the client's answer, via the studio
                ans = _studio_answer(run_dir, "script")
                if ans:
                    return _studio_apply("next", str(sid), run_dir, next_stage,
                                         "script", ans)
            return _sa_envelope("next", str(sid), sa)
        # D2 item 1: SONG APPROVAL = Yes routes HERE, to the three-version
        # music runner, not the single dispatch runbook row.
        sc = _song_choices_next(run_dir, orchestrated=bool(getattr(a, "orchestrated", False)))
        if sc is not None:
            lane = lane_size_payload()
            data = {"stage": next_stage, "command": sc["command"],
                    "produces": row.get("produces", ""), "lane_size": lane,
                    "stages_source": stages_source, "song_choices": sc,
                    "lifecycle": _music_lifecycle()}
            if method_block is not None:
                data["method"] = method_block
            if music_request is not None:
                data["music_request"] = music_request
            return envelope(
                "next", str(sid), "ok", "next-stage",
                "SONG APPROVAL = Yes: run the three-version music runner (%s mode); "
                "one submission pass, overlap receipt, no paid redo for a missing overlap."
                % sc["mode"],
                data=data, evidence=["%s" % db, runbook_path])
    lane = lane_size_payload()
    nxt = {"stage": present_id, "command": row["command"],
           "produces": row.get("produces", ""), "lane_size": lane,
           "stages_source": stages_source}
    if row_id != present_id:
        nxt["method_stage"] = row_id
    if method_block is not None:
        nxt["method"] = method_block
    if plan_block is not None:
        nxt["method_plan"] = plan_block
    if platform_fit is not None:
        nxt["platform_fit"] = platform_fit
    if music_request is not None:
        nxt["music_request"] = music_request
    if next_stage == "music":
        nxt["lifecycle"] = _music_lifecycle()
        # L4.5: the SONG PICK / next paid step is a cost fork. Record the
        # decision with the safe default BEFORE the run can sit on it: a
        # three-version pick whose paid redo exceeds the remaining ledger
        # balance records "wait", never a spend above the balance. The
        # umbrella's cost is read off the run's own request when one exists.
        try:
            reqdoc = _read_json(Path(run_dir) / "music" / "req.json", {}) or {}
            est = reqdoc.get("estimated_cost")
            est_int = int(est) if isinstance(est, int) and not isinstance(est, bool) else None
            method_doc = _read_json(Path(run_dir) / "control" / "method.json",
                                    {}) or {}
            ceiling = method_doc.get("budget_minor")
            ceiling_int = (int(ceiling) if isinstance(ceiling, int)
                           and not isinstance(ceiling, bool) else None)
            nxt["cost_fork"] = cost_fork(
                run_dir, "music-umbrella-%s" % sid, est_int,
                label="music stage next paid step",
                budget_minor=ceiling_int)
        except Exception:                                # noqa: BLE001
            pass
    if reconciled:
        nxt["reconciled"] = reconciled
    return envelope("next", str(sid), "ok", "next-stage",
                    "Run this command for stage %r; after it passes its QC "
                    "gate, run `next` again." % present_id,
                    data=nxt, evidence=["%s" % db, runbook_path])


def _card_help():
    """`card` subcommand help carrying the card's LIVE total.

    SWI-002: the total is read off QUESTIONS at parser-build time, so this file
    holds no literal question count for the card and cannot repeat the stale
    literal one it used to carry. When the card module is not importable here
    the help claims no total at all rather than guessing one.
    """
    total = ""
    try:
        core = str(Path(__file__).resolve().parent.parent)
        if core not in sys.path:
            sys.path.insert(0, core)
        from choice_card.intake_card import intake_card as _card  # noqa: PLC0415
        total = " (%d questions, the same total with a saved character)" % len(_card.QUESTIONS)
    except Exception:  # noqa: BLE001 - card module absent: claim no total
        total = ""
    return "Print the intake card%s as raw text (not JSON), or as send payloads (H9)." % total


def main(argv=None):
    ap = argparse.ArgumentParser(prog="factory.py",
                                 description="Drama-song factory control CLI (intake/preflight/next).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("intake", help="Normalize brief, ask ONE missing essential per turn.")
    i.add_argument("--brief", default=None, help="Brief as JSON string.")
    i.add_argument("--brief-file", default=None)
    i.add_argument("--settings-file", default=None)
    i.add_argument("--resume-file", default=None)
    i.add_argument("--run-id", default=None)
    p = sub.add_parser("preflight", help="NAMES-only dependency/auth checks; never generates.")
    p.add_argument("--run-id", default=None)
    p.add_argument("--root", default=None, help="Approved storage root.")
    p.add_argument("--storage-dir", default=None)
    p.add_argument("--ref", action="append", default=None)
    p.add_argument("--require-tool", action="append", default=None)
    p.add_argument("--require-module", action="append", default=None)
    p.add_argument("--profile", default=_preflight.DEFAULT_PROFILES[0],
                   help="Delivery profile; default is the version-2 "
                        "drama-9x16-60s (see preflight.DEFAULT_PROFILES).")
    p.add_argument("--allowed-profiles", default=None)
    p.add_argument("--schema-version", default="blackceo.campaign/v1")
    p.add_argument("--allowed-schemas", default=None)
    p.add_argument("--credential", action="append", default=None)
    p.add_argument("--auth-file", default=None)
    p.add_argument("--summary-digest", default=None)
    p.add_argument("--min-free-bytes", type=int, default=0)
    p.add_argument("--run-state-file", default=None,
                   help="Run-state JSON; must carry the recorded F15 choice-"
                        "card receipt before any paid job.")
    p.add_argument("--card-receipt-file", default=None,
                   help="The recorded choice-card receipt (answers, who, at); "
                        "overrides the run-state record.")
    n = sub.add_parser("next", help="Which stage is next, its exact command, and "
                                    "how many lanes may run (manual 02 B1).")
    n.add_argument("--run-dir", required=True,
                   help="Run dir that holds control/state.sqlite3.")
    n.add_argument("--orchestrated", action="store_true",
                   help="With SONG APPROVAL = Yes, select the ORCHESTRATED mode "
                        "(three units, one variant each) instead of the umbrella "
                        "three-up runner. Exactly one mode is ever emitted.")
    sb = sub.add_parser("storyboard", help="Storyboard approval step: send cards + "
                        "stills, or apply the client's reply.")
    sb.add_argument("--run-dir", required=True)
    sb.add_argument("--target", default="", help="Telegram chat id")
    sb.add_argument("--reply", default=None, help="The client's reply, if any.")
    n.add_argument("--target", default="",
                   help="Client Telegram chat id for the SCRIPT APPROVAL message; "
                        "empty = hand the message back for the chat.")
    m = sub.add_parser("music", help="Own the music stage row: start (claim/resume), "
                       "wait-provider, wait-approval, resume, complete (song gate + audio "
                       "+ independent qc_gate PASS), fail, park, reopen.")
    m.add_argument("--run-dir", required=True)
    m.add_argument("--owner", required=True, help="Worker id that holds the music lease.")
    m.add_argument("--action", required=True, choices=_MUSIC_ACTIONS)
    m.add_argument("--run-id", default=None, help="Store run id; default: the only one.")
    m.add_argument("--reason", default=None, help="Required for fail and park.")
    m.add_argument("--retryable", action="store_true", help="fail -> FAILED_RETRYABLE.")
    m.add_argument("--lease-s", type=int, default=3600)
    m.add_argument("--records", default=None, help="complete: qc-schema records JSON.")
    m.add_argument("--makers", default=None, help="complete: check_id -> maker JSON.")
    m.add_argument("--required", default=None, help="complete: required checks, comma list.")
    m.add_argument("--operator-decision", default=None,
                   help="complete (L2/WW-21): operator-decision JSON -- {decision, operator, "
                        "at_utc, gates_not_proven, measured_evidence_digest, reason}; never a "
                        "PASS for a measured gate, never a relabel.")
    sr = sub.add_parser("script-reply", help="The client's reply to the script message "
                                             "(SCRIPT APPROVAL): approve, or an edit.")
    sr.add_argument("--run-dir", required=True)
    sr.add_argument("--reply", required=True)
    sr.add_argument("--target", default="")
    c = sub.add_parser("card", help=_card_help())
    c.add_argument("--format", default="text",
                   choices=("text", "openclaw-json", "telegram-json", "studio-json"),
                   help="text: raw card for the chat. openclaw-json / telegram-json: "
                        "send payloads. studio-json: the studio question/price/example "
                        "export (SPEC §5).")
    c.add_argument("--target", default="", help="Telegram chat id")
    c.add_argument("--client-dir", default="",
                   help="Client data folder; swaps in the saved-character question when it has saved characters (I6).")
    c.add_argument("--run-state-file", default="",
                   help="with --step and no replies: first call sends the one-time intro, next call question 1")
    c.add_argument("--price", default=None, help="card total in dollars, shown in the spend question")
    c.add_argument("--limit", default=None, help="spend limit in dollars; overrides the one found in the brief or summary")
    c.add_argument("--brief", default=None, help="Brief as JSON string; its budget_minor becomes spend option 1.")
    c.add_argument("--brief-file", default=None, help="Brief JSON file (or the planner's); same.")
    c.add_argument("--summary-file", default=None,
                   help="intake output (envelope or summary) JSON; its generation_ceiling becomes spend option 1.")
    c.add_argument("--run-dir", default="",
                   help="Run dir; the confirmed card writes control/card-receipt.json (storyboard), the SONG APPROVAL answer and card-answers.json (SCRIPT APPROVAL) there.")
    c.add_argument("--step", action="store_true",
                   help="one question per message (I7): print only the next message")
    c.add_argument("--reply", action="append", default=[],
                   help="a client reply so far, in order (repeat the flag)")
    c.add_argument("--fit", action="store_true",
                   help="FU-U4: the fit STOP card for the client's own lines "
                        "(--brief-file, --packet-file); exit 2 when they do not fit")
    c.add_argument("--packet-file", default=None,
                   help="JSON list of client lines {id, speaker, text, scene}")
    ch = sub.add_parser("character", help="Per-client character library: ask / save / "
                                          "list / use / card (Part I, I6). Extra args pass through.")
    args = sys.argv[1:] if argv is None else list(argv)
    if args[:1] == ["character"]:      # own parser; passes --client-dir etc. through
        a = argparse.Namespace(cmd="character", rest=args[1:])
    else:
        a = ap.parse_args(argv)
    if a.cmd == "character":
        import os
        core = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if core not in sys.path:
            sys.path.insert(0, core)
        from character_library import character_library as _cl  # noqa: PLC0415
        return _cl.main(a.rest)
    if a.cmd == "card":
        import os
        core = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if core not in sys.path:
            sys.path.insert(0, core)
        from choice_card.intake_card import intake_card as _card  # noqa: PLC0415
        if a.fit:
            brief = _load(a.brief_file) if a.brief_file else {}
            packet = _load(a.packet_file) if a.packet_file else brief.get("packet_lines")
            card = _card.fit_card(brief, packet)
            sys.stdout.write(card["text"] + "\n")
            return EXIT[card["outcome"]]
        limit, from_brief = a.limit, False
        for doc in ((_load(a.summary_file) if a.summary_file else None),
                    (_load(a.brief_file) if a.brief_file else json.loads(a.brief) if a.brief else None)):
            if not limit:
                limit = limit_from(doc)
                from_brief = bool(limit)
        return _card.main(["--format", a.format, "--target", a.target]
                          + (["--client-dir", a.client_dir] if a.client_dir else [])
                          + (["--price", a.price] if a.price else [])
                          + (["--limit", limit] if limit else [])
                          + (["--limit-from-brief"] if limit and from_brief else [])
                          + (["--run-dir", a.run_dir] if a.run_dir else [])
                          + (["--step"] if a.step else [])
                          + (["--run-state-file", a.run_state_file] if a.run_state_file else [])
                          + [x for r in a.reply for x in ("--reply", r)])
    if a.cmd == "intake":
        env = cmd_intake(a)
    elif a.cmd == "preflight":
        env = cmd_preflight(a)
    elif a.cmd == "storyboard":
        env = cmd_storyboard(a)
    elif a.cmd == "script-reply":
        env = cmd_script_reply(a)
    elif a.cmd == "music":
        env = cmd_music(a)
    else:
        env = cmd_next(a)
    json.dump(env, sys.stdout, indent=2, sort_keys=True, default=str)
    sys.stdout.write("\n")
    return EXIT[env["outcome"]]


if __name__ == "__main__":
    sys.exit(main())