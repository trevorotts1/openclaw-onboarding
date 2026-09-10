#!/usr/bin/env python3
# =============================================================================
# SKILL 60 - ZHC EARLY WARNING SYSTEM :: ews_fleet.py
# OPERATOR-BOX AGGREGATOR + DEAD-MAN SWITCH (spec 4.6)
# -----------------------------------------------------------------------------
# Runs ONLY on the operator box (install SKIPS it on client boxes; the no-
# commingling law means client boxes never see each other). Each cycle (hourly,
# D3) it ingests each box's tiny digest (last tick ts, red flags, event counts by
# class - NO config contents, NO secrets) collected over the fleet's existing
# sanctioned access paths (cloudflared-backed SSH to Macs, docker exec on VPS),
# writes a durable per-box ledger under <openclaw>/ews-fleet/<box>.json, and:
#   * fires the DEAD-MAN SWITCH: a box with no fresh sentinel tick for 2 consecutive
#     cycles (D4) = P1 "sentinel dark" - which catches frozen gateways, dead
#     containers, and killed crons: exactly the failures a per-box agent cannot
#     report. A dead-man P1 escalates to Rescue Rangers immediately (the box cannot
#     speak for itself).
#   * renders the fleet digest (red/yellow/green per box) for the operator.
# It NEVER pushes config, skills, or fixes to a box: it reads digests and alerts;
# fixes flow through the companion, one box at a time, operator-commanded.
#
# STDLIB ONLY. DOCTRINE: operator-only; never a secret value; reads digests, never
# config contents; never writes a client box.
#
# EXIT CODES: 0 OK, 1 error, 2 usage.
# =============================================================================
"""ews_fleet.py - operator-box aggregator + dead-man switch (Skill 60)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import ews_common as C  # noqa: E402
from ews_ledger import Ledger, openclaw_root, now_utc  # noqa: E402

EX_OK, EX_ERR, EX_USAGE = 0, 1, 2


def fleet_dir() -> Path:
    env = os.environ.get("EWS_FLEET_DIR", "").strip()
    d = Path(env).expanduser() if env else (openclaw_root() / "ews-fleet")
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    return d


def _state_file():
    return fleet_dir() / "_state.json"


def _read_state():
    p = _state_file()
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {"cycle": 0, "boxes": []}


def _write_json(path: Path, obj):
    fd, tmp = tempfile.mkstemp(prefix=".ews-fleet.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _box_file(box):
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(box))
    return fleet_dir() / ("%s.json" % safe)


def cmd_ingest(box, digest):
    """Record one box's digest and stamp it with the current cycle (fresh)."""
    st = _read_state()
    cycle = st.get("cycle", 0)
    rec = {}
    bf = _box_file(box)
    if bf.is_file():
        try:
            rec = json.loads(bf.read_text(encoding="utf-8"))
        except ValueError:
            rec = {}
    rec["box"] = box
    rec["last_tick_ts"] = digest.get("last_tick_ts")
    rec["red_flags"] = digest.get("red_flags", 0)
    rec["counts"] = digest.get("counts", {})
    rec["by_severity"] = digest.get("by_severity", {})
    rec["last_report_cycle"] = cycle
    rec["updated_at"] = now_utc()
    hist = rec.get("history", [])
    hist.append({"cycle": cycle, "ts": now_utc(), "red_flags": rec["red_flags"]})
    rec["history"] = hist[-50:]
    _write_json(bf, rec)
    if box not in st.get("boxes", []):
        st.setdefault("boxes", []).append(box)
        _write_json(_state_file(), st)
    return rec


def cmd_cycle(state_dir=None, sender=None, dry_run=False, admission=None):
    """Advance the aggregator cycle; fire the dead-man switch for silent boxes.
    `admission` is the injectable admission client (tests pass a stub so the
    cycle NEVER reaches the network); None resolves the shared client."""
    th = C.load_skill_config("thresholds.json").get("aggregator", {})
    dead_man = th.get("dead_man_cycles", 2)
    st = _read_state()
    st["cycle"] = st.get("cycle", 0) + 1
    cycle = st["cycle"]
    _write_json(_state_file(), st)

    dark = []
    for box in st.get("boxes", []):
        bf = _box_file(box)
        if not bf.is_file():
            continue
        rec = json.loads(bf.read_text(encoding="utf-8"))
        last = rec.get("last_report_cycle", 0)
        if (cycle - last) >= dead_man:
            dark.append(box)
            rec["sentinel_dark"] = True
            _write_json(bf, rec)
            _fire_dead_man(box, cycle - last, state_dir, sender, dry_run, admission)
        else:
            if rec.get("sentinel_dark"):
                rec["sentinel_dark"] = False
                _write_json(bf, rec)
    return {"ok": True, "cycle": cycle, "boxes": len(st.get("boxes", [])), "sentinel_dark": dark}


def _fire_dead_man(box, silent_cycles, state_dir, sender, dry_run, admission=None):
    """Record a P1 'sentinel dark' on the OPERATOR box ledger, alert the
    operator, and route the dead-man through RESCUE ADMISSION immediately (D4:
    dead-man escalates immediately -- the box cannot speak for itself).

    RR-015: admission is the REAL deliverable -- a durable rescue ticket with a
    validated receipt. The event is marked escalated ONLY when the admission
    receipt says admitted/replay; a failed/refused/unavailable admission leaves
    the event OPEN so the 30-minute escalate() path (or the next cycle) can
    retry it. dry_run mutates NOTHING (no event, no admission, no send)."""
    try:
        import ews_alert
        from ews_sentinel import F
        import ews_common
    except ImportError:
        return
    detail = ("SENTINEL DARK: box '%s' has not reported a fresh tick for %d aggregator "
              "cycle(s) - frozen gateway, dead container, or killed cron. The box cannot "
              "self-report; investigate now." % (box, silent_cycles))
    finding = F("S7", "P1", "fleet:%s" % box, "deadman", detail,
                dedup_key="deadman|%s" % box)
    reason = "admission status unknown (dry run)"
    admitted = False
    ticket_id = None
    with Ledger(state_dir) as led:
        eid = led.record_event("S7", "P1", key_path="fleet:%s" % box, klass="deadman",
                               detail=detail, dedup_key="deadman|%s" % box)
        if dry_run:
            reason = "dry run: no admission attempted"
        else:
            client = admission if admission is not None else ews_common.load_rescue_admission()
            admit_fn = getattr(client, "admit", None)
            if admit_fn is None and callable(client):
                admit_fn = client
            if client is None or admit_fn is None:
                # missing shared client: owned setup fault; event stays OPEN so
                # the escalate() sweep retries it after the next unacked window.
                reason = "admission client unavailable (shared client missing)"
                led.record_digest("rescue_admission_client_unavailable",
                                  "deadman|%s" % box,
                                  payload="box=%s" % box)
            else:
                receipt = admit_fn(
                    state_dir, box=box,
                    problem_text=("[EWS ESCALATION] " + detail),
                    source="skill-60-ews-fleet", signal="S7",
                    key_path="fleet:%s" % box, dedup_key="deadman|%s" % box,
                    event_id=eid, tick_ts=now_utc())
                reason = receipt.get("status", "failed")
                ticket_id = receipt.get("ticket_id")
                admitted = ews_common.admission_is_ack_eligible(reason)
                if admitted:
                    led.ack_event(eid, "escalated")
                    if ticket_id:
                        led.record_digest("rescue_admission_ticket", "deadman|%s" % box,
                                          payload="ticket_id=%s box=%s" % (ticket_id, box))
                elif ews_common.admission_is_pending_repair(reason):
                    # RR-015: missing enrollment is a PENDING REPAIR with an
                    # owner -- visible and retryable, never an admission and
                    # never a generic refusal. The dead-man event stays OPEN so
                    # the escalate sweep owns the retry.
                    led.record_digest(
                        "rescue_admission_pending_repair", "deadman|%s" % box,
                        payload=("box=%s reason=%s owner=%s action=%s" % (
                            box, reason,
                            receipt.get("repair_owner") or "operator-seeder-D08",
                            receipt.get("repair_action") or "enroll this box")))
                else:
                    led.record_digest("rescue_admission_%s" % reason,
                                      "deadman|%s" % box,
                                      payload="box=%s" % box)
    # operator alert (deduped; unchanged)
    try:
        ews_alert.route_finding(finding, state_dir, sender=sender, dry_run=dry_run)
    except Exception:  # noqa: BLE001
        pass
    # Telegram group visibility: SUPPLEMENTAL ONLY (a message is NOT admission).
    if not dry_run:
        rescue = None
        for n in ("EWS_RESCUE_CHAT", "RESCUE_RANGERS_CHAT_ID"):
            rescue = rescue or os.environ.get(n)
        if rescue:
            snd = sender or ews_alert._gateway_sender
            try:
                ok, _detail = snd("rescue-rangers", rescue, "[EWS ESCALATION] " + detail)
                with Ledger(state_dir) as led:
                    led.record_digest(
                        "rescue_group_visibility" if ok else "rescue_group_visibility_failed",
                        "deadman|%s" % box, payload="box=%s" % box)
            except Exception:  # noqa: BLE001
                pass
    return {"status": reason, "ticket_id": ticket_id, "admitted": admitted}


def cmd_digest():
    """Render the fleet red/yellow/green digest for the operator."""
    st = _read_state()
    lines = []
    reds = yellows = greens = 0
    for box in sorted(st.get("boxes", [])):
        bf = _box_file(box)
        if not bf.is_file():
            continue
        rec = json.loads(bf.read_text(encoding="utf-8"))
        sev = rec.get("by_severity", {})
        if rec.get("sentinel_dark") or sev.get("P1"):
            color = "RED"
            reds += 1
        elif sev.get("P2"):
            color = "YELLOW"
            yellows += 1
        else:
            color = "GREEN"
            greens += 1
        lines.append({"box": box, "color": color, "last_tick_ts": rec.get("last_tick_ts"),
                      "sentinel_dark": bool(rec.get("sentinel_dark")), "by_severity": sev})
    return {"cycle": st.get("cycle", 0), "red": reds, "yellow": yellows, "green": greens,
            "boxes": lines}


def _emit(obj):
    sys.stdout.write(json.dumps(obj, sort_keys=True) + "\n")


def _cli(argv=None):
    ap = argparse.ArgumentParser(prog="ews_fleet.py",
                                 description="Operator-box aggregator + dead-man switch (Skill 60).")
    ap.add_argument("--state-dir")
    ap.add_argument("--self-test", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=False)
    sp = sub.add_parser("ingest")
    sp.add_argument("--box", required=True)
    sp.add_argument("--digest", help="digest JSON (or - for stdin)")
    sub.add_parser("cycle").add_argument("--dry-run", action="store_true")
    sub.add_parser("digest")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.cmd == "ingest":
        raw = sys.stdin.read() if args.digest in (None, "-") else args.digest
        _emit(cmd_ingest(args.box, json.loads(raw)))
        return EX_OK
    if args.cmd == "cycle":
        _emit(cmd_cycle(Path(args.state_dir) if args.state_dir else None,
                        dry_run=getattr(args, "dry_run", False)))
        return EX_OK
    if args.cmd == "digest":
        _emit(cmd_digest())
        return EX_OK
    ap.error("a subcommand is required (or use --self-test)")


def self_test():
    import tempfile as _tf
    print("[ews_fleet] self-test: ingest, dead-man switch (2 cycles), fleet digest")
    sent = []
    admission_calls = []

    def fake_sender(account, target, text):
        sent.append({"account": account, "target": target, "text": text})
        return True, "fake"

    # RR-015: the dead-man path goes through the SHARED admission client. The
    # self-test injects a stub so the cycle NEVER reaches the network; the real
    # client is exercised offline in its own self-test.
    def fake_admission(state_dir=None, box="", problem_text="", **kw):
        admission_calls.append({"box": box, "problem": problem_text})
        return {"status": "admitted", "operation_id": "op-deadman-fixture",
                "ticket_id": "T-DM-1", "admission_schema": "v1",
                "detail": "admitted ticket_id=T-DM-1", "reply_digest": "d1"}

    with _tf.TemporaryDirectory() as td:
        os.environ["EWS_FLEET_DIR"] = str(Path(td) / "ews-fleet")
        os.environ["EWS_STATE_DIR"] = str(Path(td) / "ews")
        os.environ["EWS_RESCUE_CHAT"] = "8888rescue"
        os.environ["EWS_OPERATOR_CHAT"] = "9999op"

        # two boxes report clean
        cmd_ingest("box-alpha-example", {"last_tick_ts": now_utc(), "red_flags": 0,
                                         "by_severity": {}, "counts": {}})
        cmd_ingest("box-bravo-example", {"last_tick_ts": now_utc(), "red_flags": 0,
                                         "by_severity": {}, "counts": {}})
        d0 = cmd_digest()
        assert d0["green"] == 2 and d0["red"] == 0
        print("  ingest case: PASS (2 boxes green)")

        # cycle 1: alpha re-reports, bravo goes silent
        cmd_cycle(sender=fake_sender, admission=fake_admission)  # cycle -> 1
        cmd_ingest("box-alpha-example", {"last_tick_ts": now_utc(), "red_flags": 0, "by_severity": {}})
        # cycle 2: bravo still silent (last_report_cycle=0, now cycle 2 => 2 cycles => dark)
        res = cmd_cycle(sender=fake_sender, admission=fake_admission)
        assert "box-bravo-example" in res["sentinel_dark"], res
        assert "box-alpha-example" not in res["sentinel_dark"]
        print("  dead-man case: PASS (silent box dark after 2 cycles; reporting box healthy)")

        # dead-man fired an operator alert, a RESCUE ADMISSION (RR-015) and the
        # supplemental group visibility message
        assert len(admission_calls) == 1 and admission_calls[0]["box"] == "box-bravo-example"
        assert any(s["account"] == "operator" for s in sent)
        assert any(s["account"] == "rescue-rangers" and "8888rescue" == s["target"] for s in sent)
        assert any("SENTINEL DARK" in s["text"] for s in sent)
        with Ledger() as led:
            # the dead-man event was acked ONLY because the receipt admitted
            evs = [dict(r) for r in led.conn.execute(
                "SELECT * FROM events WHERE dedup_key=?",
                ("deadman|box-bravo-example",)).fetchall()]
            assert evs and evs[0]["ack_state"] == "escalated", evs
        print("  escalation case: PASS (dead-man admission given once; event escalated on receipt)")

        # a FAILED dead-man admission leaves the event OPEN (RR-005 contract)
        def failing_admission(state_dir=None, box="", problem_text="", **kw):
            return {"status": "failed", "operation_id": "op-deadman-fail",
                    "ticket_id": None, "admission_schema": "v1",
                    "detail": "intake unreachable", "reply_digest": None}
        cmd_cycle(sender=fake_sender, admission=failing_admission)  # cycle -> 3
        with Ledger() as led:
            evs2 = [dict(r) for r in led.conn.execute(
                "SELECT * FROM events WHERE dedup_key=? ORDER BY event_id",
                ("deadman|box-bravo-example",)).fetchall()]
            # the first event is escalated; the new cycle event stays OPEN
            assert evs2[0]["ack_state"] == "escalated", evs2
            assert any(e["ack_state"] == "open" for e in evs2), evs2
        print("  dead-man-failure case: PASS (failed admission leaves event OPEN, retryable)")

        # RR-015: a MISSING ENROLLMENT on the dead-man path is a PENDING REPAIR
        # with an owner -- recorded as such, never an admission, never a
        # generic refusal, and the dead-man event stays OPEN so the escalate
        # sweep owns the retry (the box still cannot speak for itself).
        def unenrolled_admission(state_dir=None, box="", problem_text="", **kw):
            return {"status": "no_enrollment", "operation_id": "op-deadman-noenroll",
                    "ticket_id": None, "admission_schema": "none",
                    "detail": "no enrollment accepted by the intake (schema=none)",
                    "reply_digest": None, "pending_repair": True,
                    "repair_owner": "operator-seeder-D08",
                    "repair_action": "enroll this box in rr_box_auth with an "
                                     "accepted admission credential"}
        cmd_cycle(sender=fake_sender, admission=unenrolled_admission)  # cycle -> 4
        with Ledger() as led:
            evs3 = [dict(r) for r in led.conn.execute(
                "SELECT * FROM events WHERE dedup_key=? ORDER BY event_id",
                ("deadman|box-bravo-example",)).fetchall()]
            rows = [dict(r) for r in led.conn.execute(
                "SELECT kind,payload FROM digests WHERE kind=?",
                ("rescue_admission_pending_repair",)).fetchall()]
        assert any(e["ack_state"] == "open" for e in evs3), evs3
        assert not any(e["ack_state"] == "escalated" for e in evs3[1:]), evs3
        assert rows, "missing enrollment must record a pending-repair digest"
        assert "owner=operator-seeder-D08" in (rows[0]["payload"] or ""), rows
        assert "action=" in (rows[0]["payload"] or ""), rows
        print("  dead-man-no-enrollment case: PASS (pending repair with owner; "
              "event stays OPEN, never admitted)")

        # digest now shows bravo RED (sentinel dark)
        d1 = cmd_digest()
        bravo = [b for b in d1["boxes"] if b["box"] == "box-bravo-example"][0]
        assert bravo["color"] == "RED" and bravo["sentinel_dark"]
        print("  digest case: PASS (dark box renders RED)")

        # a box reporting a P1 renders RED too
        cmd_ingest("box-charlie-example", {"last_tick_ts": now_utc(), "by_severity": {"P1": 1}})
        d2 = cmd_digest()
        charlie = [b for b in d2["boxes"] if b["box"] == "box-charlie-example"][0]
        assert charlie["color"] == "RED"
        print("  severity case: PASS (a reported P1 renders RED)")

        for k in ("EWS_FLEET_DIR", "EWS_STATE_DIR", "EWS_RESCUE_CHAT", "EWS_OPERATOR_CHAT"):
            os.environ.pop(k, None)
    print("[ews_fleet] self-test: PASS")
    return EX_OK


if __name__ == "__main__":
    sys.exit(_cli())
