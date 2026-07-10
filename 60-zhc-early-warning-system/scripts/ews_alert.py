#!/usr/bin/env python3
# =============================================================================
# SKILL 60 - ZHC EARLY WARNING SYSTEM :: ews_alert.py
# ALERT ROUTING - operator-only, silent to clients, structurally (spec 4.5)
# -----------------------------------------------------------------------------
# The ONE and ONLY path to the operator's alert channel for this skill. The
# sentinel NEVER sends Telegram directly; it calls route_finding(), which decides
# whether to send and, when it does, routes THROUGH the box's OWN OpenClaw gateway
# (openclaw message send) to the OPERATOR account only. A client bot / chat /
# account is structurally never a recipient. MOVE IN SILENCE toward clients.
#
# Reuses the Skill 58 alert-dedup pattern:
#   * dedup: one alert per (signal, dedup_key) per dedup_window_hours (default 6);
#   * storm cap: max_operator_alerts_per_box_per_day (default 4); beyond it, non-P1
#     alerts collapse into the daily digest. P1 BYPASSES the batch (but not dedup).
#   * D5 routing: a 'box_agent' finding (the context running-low warning) is written
#     to the box's OWN agent notices - it NEVER reaches the operator.
#   * escalation (D4): an unacknowledged P1 older than 30 minutes, or a dead-man P1,
#     escalates to the Rescue Rangers channel.
#
# STDLIB ONLY. No network except the gateway CLI subprocess. DOCTRINE: operator
# target only (a client chat is never a fallback); never print a secret value; the
# alert body is plain operator language with the exact box + key path + class +
# measured-vs-threshold + revert line.
#
# EXIT CODES: 0 OK, 1 error, 2 usage.
# =============================================================================
"""ews_alert.py - operator-only alert routing + Rescue Rangers escalation (Skill 60)."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import ews_common as C  # noqa: E402
from ews_ledger import Ledger, default_state_dir, now_utc  # noqa: E402
from datetime import datetime  # noqa: E402

EX_OK, EX_ERR, EX_USAGE = 0, 1, 2

# operator / rescue targets are resolved from env; a client chat is NEVER consulted.
_OPERATOR_TARGET_ENV = ("EWS_OPERATOR_CHAT", "OPERATOR_TELEGRAM_CHAT_ID", "FOUNDER_TELEGRAM_CHAT_ID")
_RESCUE_TARGET_ENV = ("EWS_RESCUE_CHAT", "RESCUE_RANGERS_CHAT_ID")
_OPERATOR_ACCOUNT = os.environ.get("EWS_OPERATOR_ACCOUNT", "operator")
_RESCUE_ACCOUNT = os.environ.get("EWS_RESCUE_ACCOUNT", "rescue-rangers")


def _first_env(names):
    for n in names:
        v = os.environ.get(n, "")
        if v and v.strip():
            return v.strip()
    return None


def _box_name(led):
    return led.get_meta("box", None) or os.environ.get("EWS_BOX_NAME") or socket.gethostname()


def _mask(target):
    if not target:
        return "UNSET"
    s = str(target)
    return "***" + s[-4:] if len(s) > 4 else "***"


# --------------------------------------------------------------------------- #
# the gateway send (the ONLY egress). Injectable for tests.
# --------------------------------------------------------------------------- #
def _gateway_sender(account, target, text):
    """Send THROUGH the OpenClaw gateway CLI. Returns (ok, detail). Never contacts
    the Telegram bot HTTP API directly, never targets a client chat."""
    openclaw = os.environ.get("OPENCLAW_BIN") or _which("openclaw")
    if not openclaw:
        return False, "openclaw binary not found (set OPENCLAW_BIN)"
    cmd = [openclaw, "message", "send", "--channel", "telegram",
           "--account", str(account), "--target", str(target), "--message", text]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=45, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, "gateway send failed: %s" % type(exc).__name__
    if proc.returncode == 0:
        return True, "sent via gateway"
    detail = (proc.stderr or proc.stdout or "").strip().splitlines()
    return False, "gateway rc=%d %s" % (proc.returncode, detail[-1] if detail else "")


def _which(name):
    from shutil import which
    return which(name)


# --------------------------------------------------------------------------- #
# alert text
# --------------------------------------------------------------------------- #
def _alert_text(box, finding):
    lines = ["[EWS %s] box=%s signal=%s class=%s"
             % (finding["severity"], box, finding["signal"], finding.get("class") or "-")]
    if finding.get("key_path"):
        lines.append("key: %s" % finding["key_path"])
    lines.append(finding.get("detail") or "")
    if finding.get("revert_cmd"):
        lines.append("revert: %s" % finding["revert_cmd"])
    return "\n".join(x for x in lines if x)


def _box_agent_text(box, finding):
    return ("[EWS self-notice] box=%s signal=%s: %s"
            % (box, finding["signal"], finding.get("detail") or ""))


# --------------------------------------------------------------------------- #
# route one finding (the function the sentinel calls)
# --------------------------------------------------------------------------- #
def route_finding(finding, state_dir=None, sender=None, dry_run=False):
    """Decide + (maybe) send one finding. Returns True iff a send actually happened.
    box_agent findings NEVER reach the operator. Operator findings dedup by
    (signal, dedup_key) within the window and honor the daily storm cap (P1 bypasses
    the batch, not the dedup)."""
    sender = sender or _gateway_sender
    th = C.load_skill_config("thresholds.json").get("alert", {})
    window = th.get("dedup_window_hours", 6)
    cap = th.get("max_operator_alerts_per_box_per_day", 4)

    with Ledger(state_dir) as led:
        box = _box_name(led)
        route = finding.get("route", "operator")
        dedup_key = "%s|%s|%s" % (route, finding["signal"], finding.get("dedup_key") or "")

        # dedup window (both routes)
        if led.recent_digest(dedup_key, window) is not None:
            return False

        # D5: box-agent route - write to the box's OWN agent notices, never operator
        if route == "box_agent":
            notices = (led.state_dir / "box-agent-notices.jsonl")
            with open(notices, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"ts": now_utc(), "box": box, "deliver": False,
                                     "finding": {k: finding.get(k) for k in
                                                 ("signal", "severity", "key_path", "detail")}}) + "\n")
            try:
                os.chmod(notices, 0o600)
            except OSError:
                pass
            led.record_digest("box_agent", dedup_key, payload="routed to box's own agent (deliver:false)")
            return False  # not an operator SEND; the box's agent self-handles

        # operator route
        target = _first_env(_OPERATOR_TARGET_ENV)
        if not target:
            # a send was warranted but no operator target is configured: send to NOBODY
            # (a client chat is never a fallback). Flag it so the canary catches it.
            led.record_event("S7", "P2", key_path="alert.operator_target", klass="alert",
                             detail="an alert was warranted but no operator target is configured")
            return False

        # storm cap: count today's operator alert digests
        today = datetime.now().strftime("%Y-%m-%d")
        since = today + "T00:00:00+00:00"
        sent_today = led.count_digests_since(since, kind="alert")
        severity = finding["severity"]
        if sent_today >= cap and severity != "P1":
            led.record_digest("deferred", dedup_key, payload="storm cap reached; deferred to digest")
            return False

        if dry_run:
            led.record_digest("alert", dedup_key, payload="DRY-RUN (no gateway call)")
            return False

        text = _alert_text(box, finding)
        ok, detail = sender(_OPERATOR_ACCOUNT, target, text)
        led.record_digest("alert" if ok else "send_failed", dedup_key,
                          payload="%s target=%s" % (detail, _mask(target)))
        return bool(ok)


# --------------------------------------------------------------------------- #
# escalation (D4): unacked P1 older than 30 min -> Rescue Rangers
# --------------------------------------------------------------------------- #
def escalate(state_dir=None, sender=None, dry_run=False):
    sender = sender or _gateway_sender
    th = C.load_skill_config("thresholds.json").get("alert", {}).get("escalation", {})
    minutes = th.get("p1_unacked_minutes", 30)
    escalated = []
    with Ledger(state_dir) as led:
        box = _box_name(led)
        rescue = _first_env(_RESCUE_TARGET_ENV)
        stale = led.unacked_p1_older_than(minutes)
        for ev in stale:
            text = ("[EWS ESCALATION] box=%s: unacknowledged P1 for >%d min\nsignal=%s key=%s\n%s"
                    % (box, minutes, ev["signal"], ev.get("key_path") or "-", ev.get("detail") or ""))
            ok = False
            if rescue and not dry_run:
                ok, _ = sender(_RESCUE_ACCOUNT, rescue, text)
            led.ack_event(ev["event_id"], "escalated")
            escalated.append({"event_id": ev["event_id"], "signal": ev["signal"], "sent": ok})
    return escalated


def _emit(obj):
    sys.stdout.write(json.dumps(obj, sort_keys=True) + "\n")


def _cli(argv=None):
    ap = argparse.ArgumentParser(prog="ews_alert.py",
                                 description="Operator-only alert routing + escalation (Skill 60).")
    ap.add_argument("--state-dir")
    ap.add_argument("--self-test", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=False)
    sp = sub.add_parser("route", help="route a single finding from a JSON string/stdin")
    sp.add_argument("--finding", help="finding JSON (or - for stdin)")
    sp.add_argument("--dry-run", action="store_true")
    sp = sub.add_parser("escalate", help="escalate unacked P1s to Rescue Rangers")
    sp.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    sd = Path(args.state_dir) if args.state_dir else None
    if args.cmd == "route":
        raw = sys.stdin.read() if args.finding in (None, "-") else args.finding
        finding = json.loads(raw)
        sent = route_finding(finding, sd, dry_run=args.dry_run)
        _emit({"ok": True, "sent": sent})
        return EX_OK
    if args.cmd == "escalate":
        out = escalate(sd, dry_run=args.dry_run)
        _emit({"ok": True, "escalated": out})
        return EX_OK
    ap.error("a subcommand is required (or use --self-test)")


# --------------------------------------------------------------------------- #
def self_test():
    import tempfile
    print("[ews_alert] self-test: operator-only, dedup, storm cap, D5 box-agent, escalation")
    sent_log = []

    def fake_sender(account, target, text):
        sent_log.append({"account": account, "target": target, "text": text})
        return True, "fake-sent"

    with tempfile.TemporaryDirectory() as td:
        os.environ["EWS_STATE_DIR"] = str(Path(td) / "ews")
        os.environ["EWS_OPERATOR_CHAT"] = "9999operator"
        os.environ["EWS_RESCUE_CHAT"] = "8888rescue"
        os.environ["EWS_BOX_NAME"] = "operator-box-example"
        from ews_sentinel import F

        # operator P1 send, with revert line, value-free
        f = F("S4", "P1", "agents.defaults.maxConcurrent", "cap",
              "safety limit raise with NO approval stamp", revert_cmd="bash ews-entry.sh revert --to X")
        assert route_finding(f, sender=fake_sender) is True
        assert len(sent_log) == 1
        assert sent_log[0]["account"] == "operator" and sent_log[0]["target"] == "9999operator"
        assert "revert:" in sent_log[0]["text"] and "box=operator-box-example" in sent_log[0]["text"]
        print("  operator-send case: PASS (operator account+target, box+revert in text)")

        # dedup: same finding within the window is suppressed (no second send)
        assert route_finding(f, sender=fake_sender) is False
        assert len(sent_log) == 1
        print("  dedup case: PASS (identical finding suppressed inside the window)")

        # D5 box_agent route: never reaches the operator; writes a self-notice
        fb = F("S3", "P2", "context.usage", "compaction", "context at 90%%", route="box_agent")
        assert route_finding(fb, sender=fake_sender) is False  # not an operator send
        assert len(sent_log) == 1  # operator sender NOT called
        notices = Path(os.environ["EWS_STATE_DIR"]) / "box-agent-notices.jsonl"
        assert notices.is_file() and "context at 90%" in notices.read_text()
        print("  D5 box-agent case: PASS (self-notice written; operator NOT contacted)")

        # storm cap: after `cap` operator alerts, a NON-P1 defers but a P1 bypasses
        # (use distinct dedup keys so dedup doesn't hide the cap behavior)
        for i in range(6):
            fi = F("S1", "P2", "agents.defaults.model.primary", "model",
                   "model change %d" % i, dedup_key="cap-test-%d" % i)
            route_finding(fi, sender=fake_sender)
        # cap=4: the first alert above counted as 1, so ~3 more P2 sends then defer
        p2_sends = [s for s in sent_log if "signal=S1" in s["text"]]
        assert len(p2_sends) <= 4, len(p2_sends)
        # a P1 still goes through despite the cap
        fp1 = F("S6", "P1", "config.owner", "config", "root-owned", dedup_key="p1-bypass")
        before = len(sent_log)
        assert route_finding(fp1, sender=fake_sender) is True
        assert len(sent_log) == before + 1
        print("  storm-cap case: PASS (non-P1 defers past the cap; P1 bypasses the batch)")

        # no operator target -> send to NOBODY (never a client fallback)
        os.environ.pop("EWS_OPERATOR_CHAT", None)
        f2 = F("S4", "P1", "x", "cap", "y", dedup_key="no-target")
        assert route_finding(f2, sender=fake_sender) is False
        os.environ["EWS_OPERATOR_CHAT"] = "9999operator"
        print("  no-target case: PASS (no operator target = send to nobody, never a client)")

        # escalation: an unacked P1 older than the window escalates to Rescue Rangers
        with Ledger() as led:
            eid = led.record_event("S6", "P1", "config.owner", "config", "root-owned",
                                   tick_ts="2000-01-01T00:00:00+00:00")  # ancient -> stale
        esc = escalate(sender=fake_sender)
        assert any(e["event_id"] == eid and e["sent"] for e in esc)
        assert sent_log[-1]["account"] == "rescue-rangers" and sent_log[-1]["target"] == "8888rescue"
        with Ledger() as led:
            assert not any(e["event_id"] == eid for e in led.open_events())  # now escalated
        print("  escalation case: PASS (stale P1 -> Rescue Rangers; event marked escalated)")

        for k in ("EWS_STATE_DIR", "EWS_OPERATOR_CHAT", "EWS_RESCUE_CHAT", "EWS_BOX_NAME"):
            os.environ.pop(k, None)
    print("[ews_alert] self-test: PASS")
    return EX_OK


if __name__ == "__main__":
    sys.exit(_cli())
