#!/usr/bin/env python3
"""
fleet_notify.py — tell the OPERATOR when a fleet roll rolled a box back, failed
it, or left content gaps that were already there. Never a client: nothing here
can address a client chat.

  python3 fleet_notify.py --summary .fleet-refresh-summary.json [--dry-run]
  python3 fleet_notify.py --test            # one labelled test note, operator only

Channels:
  Telegram  the fleet-standing-operator-alert n8n webhook, a plain relay that
            posts to the operator's own chat through the operator agent's bot.
            Reached with the fleet-standing gate credentials every box already
            carries (FLEET_STANDING_GATE_URL / _HEADER / _SECRET, from the
            environment or openclaw.json env.vars), so it works from the
            operator's Mac AND from a client box running its own Sunday update.
            (Not the Rescue Rangers intake: that one routes to coaching the
            client's own agent or a remediation turn on the box -- AI tokens,
            and a path that can reach the client.)
  Email     only on the operator's Mac (his Google service account AND the
            private fleet boxes file present): Gmail send, as and to the operator.

Exit 0 always unless arguments are bad; what was sent is printed.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import operator_google  # noqa: E402

NOTIFY_OUTCOMES = ("ROLLED_BACK", "FAILED")


def _wants_alert(r: dict) -> bool:
    return r.get("outcome") in NOTIFY_OUTCOMES or bool((r.get("heal") or {}).get("needs_attention"))


_SECRETISH = [re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{25,}\b"),   # bot tokens
              re.compile(r"\b[A-Fa-f0-9]{32,}\b"),              # hex secrets / long SHAs
              re.compile(r"\b[A-Za-z0-9_-]{40,}\b")]            # other long opaque strings


def scrub(text: str) -> str:
    for rx in _SECRETISH:
        text = rx.sub("<redacted>", text)
    return text


def _openclaw_env() -> dict:
    roots = [os.environ.get("OPENCLAW_ROOT", ""), "/data/.openclaw", str(Path.home() / ".openclaw")]
    for r in filter(None, roots):
        try:
            cfg = json.loads((Path(r) / "openclaw.json").read_text())
            return (cfg.get("env") or {}).get("vars") or {}
        except (OSError, ValueError):
            continue
    return {}


def alert_target() -> tuple[str, str, str]:
    """(url, header name, secret) for the operator alert webhook, or empties."""
    envv = _openclaw_env()
    get = lambda k: os.environ.get(k) or str(envv.get(k) or "")
    url = get("FLEET_OPERATOR_ALERT_URL")
    gate = get("FLEET_STANDING_GATE_URL")
    if not url and gate.rstrip("/").endswith("/fleet-standing-check"):
        url = gate.rstrip("/")[: -len("fleet-standing-check")] + "fleet-standing-alert"
    return url, get("FLEET_STANDING_GATE_HEADER") or "X-Fleet-Standing-Secret", get("FLEET_STANDING_GATE_SECRET")


def send_telegram(text: str) -> tuple[bool, str]:
    url, header, secret = alert_target()
    if not url or not secret:
        return False, "operator alert webhook not configured on this machine"
    req = urllib.request.Request(url, data=json.dumps({"text": text[:3900]}).encode(), method="POST",
                                 headers={"Content-Type": "application/json", header: secret})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status == 200, f"alert webhook HTTP {r.status}"
    except urllib.error.HTTPError as e:
        return False, f"alert webhook HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return False, f"alert webhook unreachable ({e.__class__.__name__})"


def compose(rows: list[dict], origin: str) -> tuple[str, str]:
    stamp = time.strftime("%Y-%m-%d %H:%M %Z")
    bad = [r for r in rows if _wants_alert(r)]
    subject = (f"Fleet update: {sum(r.get('outcome') == 'ROLLED_BACK' for r in bad)} rolled back, "
               f"{sum(r.get('outcome') == 'FAILED' for r in bad)} failed, "
               f"{sum(r.get('outcome') == 'UPDATED' for r in bad)} need attention ({origin})")
    lines = [f"Fleet update report from {origin}, {stamp}.", ""]
    for r in bad:
        what = {"ROLLED_BACK": "was put back to how it was before the update (rolled back)",
                "FAILED": "FAILED and needs a person"}.get(
                    r["outcome"], "updated, but has content gaps that were already there before")
        tries = len((r.get("heal") or {}).get("attempts") or [])
        lines.append(f"- Box {r.get('box')}: {what}.")
        if tries:
            lines.append(f"  Fix attempts made before that: {tries}.")
        lines.append(f"  Why: {r.get('outcome_detail') or '; '.join(r.get('errors') or [])}")
        if r.get("rollback", {}).get("not_restored"):
            lines.append(f"  Not undone by the rollback: {r['rollback']['not_restored']}.")
    ok = sum(1 for r in rows if r.get("outcome") == "UPDATED")
    lines += ["", f"Updated fine: {ok}. Nothing was sent to any client."]
    return subject, scrub("\n".join(lines))


def notify(rows: list[dict], origin: str, dry_run: bool = False) -> dict:
    if not any(_wants_alert(r) for r in rows):
        return {"sent": False, "reason": "nothing rolled back, failed or needing attention"}
    subject, body = compose(rows, origin)
    out = {"subject": subject}
    if dry_run:
        out["body"] = body
        return out
    out["telegram"] = send_telegram(f"{subject}\n\n{body}")
    out["email"] = (operator_google.send_email(subject, body) if operator_google.available()
                    else (False, "no operator Google account on this machine (Telegram only)"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--summary", help="fleet-refresh summary JSON (a list of box results)")
    ap.add_argument("--origin", default=socket.gethostname().split(".")[0])
    ap.add_argument("--dry-run", action="store_true", help="print the note, send nothing")
    ap.add_argument("--test", action="store_true", help="send one labelled test note to the operator")
    a = ap.parse_args()
    if a.test:
        text = ("TEST ONLY - fleet roll notification check from "
                f"{a.origin}. No box was changed. If you see this, roll-back and failure alerts reach you.")
        res = {"telegram": send_telegram(text),
               "email": operator_google.send_email("TEST ONLY - fleet roll notification check", text)
               if operator_google.available() else (False, "no operator Google account here")}
        print(json.dumps(res))
        return 0
    if not a.summary:
        ap.error("--summary or --test is required")
    try:
        rows = json.loads(Path(a.summary).read_text())
    except (OSError, ValueError) as e:
        print(json.dumps({"sent": False, "reason": f"summary unreadable: {e}"}))
        return 0
    print(json.dumps(notify(rows, a.origin, a.dry_run), default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
