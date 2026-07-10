#!/usr/bin/env python3
# =============================================================================
# SKILL 61 - LOOP PROTECTION SYSTEM :: loop_escalate.py
# Rescue Rangers integration (spec Section 7).
# -----------------------------------------------------------------------------
# Client-box escalations go via the n8n webhook $RESCUE_RANGERS_WEBHOOK_URL (the
# ONLY path the rescue agent reads; `openclaw message send` to the group is
# silently dropped - bots cannot read other bots). The structured format is
# adopted verbatim from sop-rescue-rangers-escalation.md:
#   Box / Role / Driver (LP class) / Finding / Evidence path / Proposed fix
#   (the prepared kill card) / Why escalating / Action needed
# plus a MACHINE block (finding id, class, box, prepared kill-card command, revert
# line) so the rescue flow can execute `loop-companion.sh fix <finding-id>` on the
# operator's word (spec Section 7). Webhook down -> write UNSENT-esc-*.json, retry
# next tick, NEVER fall back to the group send.
#
# TRANSPORT INJECTION: send() takes a `transport` callable so the self-test and
# verify battery run FULLY OFFLINE (they inject a stub that raises, proving the
# UNSENT fallback). The real webhook POST (urllib) is used only in production and
# only when a transport is not supplied. NO model call.
#
# DOCTRINE: a secret VALUE never enters an escalation (evidence is a PATH + a
# CLASS, never a credential). Operator-verbose, client-silent.
# =============================================================================
"""loop_escalate.py - Rescue Rangers escalation for the Loop Protection System."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from loop_ledger import openclaw_root  # noqa: E402

WEBHOOK_ENV = "RESCUE_RANGERS_WEBHOOK_URL"
DEFAULT_WEBHOOK = "https://main.blackceoautomations.com/webhook/rescue-rangers"


def escalations_dir() -> Path:
    env = os.environ.get("LOOP_STATE_DIR", "").strip()
    base = Path(env).expanduser() if env else (openclaw_root() / "loop-protection")
    d = base / "escalations"
    d.mkdir(parents=True, exist_ok=True)
    return d


def build_payload(box, loop_class, finding, evidence_path, proposed_fix,
                  why, action_needed, finding_id=None, killcard_cmd=None,
                  revert_cmd=None, role="openclaw-maintenance"):
    """The structured escalation object (SOP format + a machine block). No secret
    value is admitted: `evidence_path` is a PATH, `finding` and `why` are prose."""
    return {
        "action": "escalate",
        "source": "skill-61-loop-protection",
        "ts": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "box": box,
        "role": role,
        "driver": loop_class,
        "finding": finding,
        "evidence_path": evidence_path,
        "proposed_fix": proposed_fix,
        "why_escalating": why,
        "action_needed": action_needed,
        "machine": {
            "finding_id": finding_id,
            "loop_class": loop_class,
            "box": box,
            "killcard_command": killcard_cmd,
            "revert_line": revert_cmd,
        },
    }


def _urllib_transport(url, payload_bytes, timeout=10):
    """Production transport: POST JSON to the n8n webhook. Only used when the caller
    does not inject a transport (so it NEVER runs in the offline self-test/verify)."""
    import urllib.request
    req = urllib.request.Request(url, data=payload_bytes,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return 200 <= getattr(resp, "status", 200) < 300


def send(payload, transport=None, url=None):
    """Deliver an escalation. `transport(url, bytes)->bool` is injectable (the
    self-test passes a stub that raises, so no real network is touched). On ANY
    failure the payload is written to UNSENT-esc-<ts>.json for next-tick retry -
    NEVER a fall-back to the silently-dropped group send. Returns
    {sent: bool, unsent_path: str|None}."""
    url = url or os.environ.get(WEBHOOK_ENV, "").strip() or DEFAULT_WEBHOOK
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    tx = transport or _urllib_transport
    try:
        ok = bool(tx(url, body))
        if ok:
            return {"sent": True, "unsent_path": None}
    except Exception:  # noqa: BLE001 - any transport failure lands in the fallback
        ok = False
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    p = escalations_dir() / ("UNSENT-esc-%s-%s.json" % (payload.get("driver", "x"), ts))
    p.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return {"sent": False, "unsent_path": str(p)}


def self_test():
    import tempfile
    print("[loop_escalate] self-test: payload shape, OFFLINE UNSENT fallback, no-secret, live-transport OK")

    payload = build_payload(
        box="box-example", loop_class="LP-B1",
        finding="cc-app restart storm (12/tick)",
        evidence_path="~/.openclaw/loop-protection/boot-cc-app.log",
        proposed_fix="LF-6 park unit + capture boot log",
        why="restart velocity crossed P1 in one tick",
        action_needed="approve unpark after the boot cause is fixed",
        finding_id=42, killcard_cmd="loop-companion.sh fix 42",
        revert_cmd="loop-companion.sh unpark --finding 42")
    assert payload["driver"] == "LP-B1"
    assert payload["machine"]["killcard_command"] == "loop-companion.sh fix 42"
    assert set(payload) >= {"box", "role", "driver", "finding", "evidence_path",
                            "proposed_fix", "why_escalating", "action_needed", "machine"}
    print("  payload case: PASS (SOP format + machine block present)")

    with tempfile.TemporaryDirectory() as td:
        os.environ["LOOP_STATE_DIR"] = td

        # OFFLINE: a transport that RAISES (webhook down) -> UNSENT fallback written.
        def dead_transport(url, body):
            raise OSError("simulated webhook down (offline self-test; no real network)")
        res = send(payload, transport=dead_transport, url="http://webhook.invalid/x")
        assert res["sent"] is False and res["unsent_path"]
        unsent = Path(res["unsent_path"])
        assert unsent.is_file()
        text = unsent.read_text(encoding="utf-8")
        assert "LP-B1" in text and "sk-" not in text  # no secret shape ever in an escalation
        print("  offline-fallback case: PASS (UNSENT-esc file written, no group-send, no secret)")

        # a transport that SUCCEEDS -> sent True, no fallback file created
        def ok_transport(url, body):
            assert isinstance(body, (bytes, bytearray))  # real bytes, still no network
            return True
        before = set(Path(td, "loop-protection", "escalations").glob("UNSENT-*")) \
            if (Path(td) / "loop-protection" / "escalations").is_dir() else set()
        res2 = send(payload, transport=ok_transport)
        after = set((Path(td) / "loop-protection" / "escalations").glob("UNSENT-*"))
        assert res2["sent"] is True and res2["unsent_path"] is None
        assert after == before  # no new UNSENT file on success
        print("  live-transport case: PASS (sent, no fallback file)")

        os.environ.pop("LOOP_STATE_DIR", None)

    print("[loop_escalate] self-test: PASS")
    return 0


def _cli(argv=None):
    ap = argparse.ArgumentParser(description="Loop Protection Rescue Rangers escalation.")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="build + print the payload, do NOT POST (offline)")
    ap.add_argument("--box"); ap.add_argument("--loop-class")
    ap.add_argument("--finding"); ap.add_argument("--evidence-path")
    ap.add_argument("--proposed-fix"); ap.add_argument("--why")
    ap.add_argument("--action-needed"); ap.add_argument("--finding-id", type=int)
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    payload = build_payload(a.box, a.loop_class, a.finding, a.evidence_path,
                            a.proposed_fix, a.why, a.action_needed, a.finding_id)
    if a.dry_run:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    res = send(payload)
    print(json.dumps(res, sort_keys=True))
    return 0 if res["sent"] else 3


if __name__ == "__main__":
    sys.exit(_cli())
