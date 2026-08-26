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
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from loop_ledger import openclaw_root  # noqa: E402

WEBHOOK_ENV = "RESCUE_RANGERS_WEBHOOK_URL"
SECRET_ENV = "RESCUE_RANGERS_WEBHOOK_SECRET"
DEFAULT_WEBHOOK = "https://main.blackceoautomations.com/webhook/rr-v2-intake"


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
    value is admitted: `evidence_path` is a PATH, `finding` and `why` are prose.

    RR-SENDER-FIX-20260826: the prose also rides as `message`. The RR intake
    requires one of message|problem|problem_text|problemText and this payload
    only ever carried `finding`, so a correctly-detected loop was refused at the
    door. `finding` is KEPT so nothing downstream that reads it breaks."""
    return {
        "action": "escalate",
        "source": "skill-61-loop-protection",
        "ts": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "box": box,
        "role": role,
        "driver": loop_class,
        "finding": finding,
        "message": finding,
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


class EscalationRefused(Exception):
    """The intake was REACHED but did not admit the escalation. Distinct from a
    transport failure: a refusal is a CONTRACT fault (wrong field spelling, bad
    secret, schema drift), not a network fault. Both spill to UNSENT; only this
    one can say why. RR-SENDER-FIX-20260826"""


_BODY_READ_LIMIT = 65536
TIMEOUT_ENV = "RESCUE_RANGERS_TIMEOUT"
DEFAULT_TIMEOUT = 120.0
DRAIN_LIMIT_ENV = "RESCUE_RANGERS_DRAIN_PER_TICK"
DRAIN_SPACING_ENV = "RESCUE_RANGERS_DRAIN_SPACING"
DRAIN_JITTER_ENV = "RESCUE_RANGERS_DRAIN_JITTER"
DEFAULT_DRAIN_LIMIT = 2
DEFAULT_DRAIN_SPACING = 5.0
DEFAULT_DRAIN_JITTER = 45.0
_SECRET_SHAPES = ("sk-", "Bearer ", "eyJ", "AIza", "xoxb-")


def _trim(text, limit=400):
    """Collapse an intake response to one loggable line. A body carrying a
    credential SHAPE is dropped whole, never truncated into a spill file:
    doctrine is that no secret value may enter an escalation artifact."""
    t = " ".join((text or "").split())
    for shape in _SECRET_SHAPES:
        if shape in t:
            return "<redacted: intake response carried a credential shape>"
    return t[:limit]


def _intake_verdict(body_text):
    """Read the intake's answer. True = admitted, False = explicitly refused,
    None = UNDETERMINED. An unparseable body is NOT evidence of refusal.

    A 2xx is not admission on its own. The n8n RR intake answers HTTP 200 with
    an admission verdict in the BODY, so `{"accepted":false,"rejectReason":
    "missing message"}` arrived as a 200 and every box logged it as sent."""
    try:
        doc = json.loads(body_text)
    except Exception:  # noqa: BLE001 - a non-JSON answer is undetermined
        return None
    if not isinstance(doc, dict):
        return None
    adm = doc.get("admission")
    if isinstance(adm, dict):
        decision = str(adm.get("decision", "")).lower()
        if decision.startswith("reject"):
            return False
        if decision.startswith(("accept", "admit")):
            return True
    for key in ("accepted", "ok", "success"):
        if isinstance(doc.get(key), bool):
            return doc[key]
    for key in ("rejectReason", "reject_reason", "rejected", "error"):
        if doc.get(key):
            return False
    return None


def _unquote_env(value):
    """A shell env value that kept its quotes ('https://...') is a config-drift
    artifact, not an address: urllib reads the scheme as "'https" and the
    escalation dies with `unknown url type`. Strip only a MATCHED surrounding
    pair, so a value that legitimately contains a quote is left alone."""
    v = (value or "").strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        return v[1:-1].strip()
    return v


def _env_num(name, default, cast=float):
    try:
        v = cast(_unquote_env(os.environ.get(name, "")) or 0)
    except (TypeError, ValueError):
        v = 0
    return v if v > 0 else default


def _rr_timeout():
    """The intake's real admission path measured 29.8s (n8n execution 596246) and
    longer under fleet load, but the transport waited 10s. Every escalation was
    abandoned MID-FLIGHT and spilled to UNSENT while the intake was about to
    accept it - a self-inflicted timeout no field-name fix could cure."""
    return _env_num(TIMEOUT_ENV, DEFAULT_TIMEOUT, float)


def _drain_limit():
    return int(_env_num(DRAIN_LIMIT_ENV, DEFAULT_DRAIN_LIMIT, int))


def _drain_spacing():
    return _env_num(DRAIN_SPACING_ENV, DEFAULT_DRAIN_SPACING, float)


def _drain_jitter():
    """Deterministic per-box offset (never random, so a run is reproducible) so
    that boxes sharing a */15 cron do not all hit a GLOBALLY rate-limited intake
    in the same instant."""
    span = _env_num(DRAIN_JITTER_ENV, DEFAULT_DRAIN_JITTER, float)
    h = hashlib.sha256(os.uname().nodename.encode("utf-8")).digest()[0]
    return (h / 255.0) * span


def _spill_signature(payload):
    """Identity of the PROBLEM, not of the spill event.

    A census of the live fleet found 17,058 spilled files carrying only a small
    number of distinct problems - an unresolved finding re-escalates every tick,
    so a handful of real issues produce thousands of identical files. Draining
    one-for-one would post the whole backlog to an intake that is rate-limited
    GLOBALLY across the fleet, shedding other clients' live escalations and
    burying the rescue team. Dedup here is a SAFETY CONTROL, not an
    optimisation. RR-SENDER-DRAIN-20260826"""
    key = "|".join(str(payload.get(k))
                   for k in ("box", "driver", "finding", "evidence_path"))
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def _mtime_iso(path):
    return (datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            .replace(microsecond=0).isoformat())


def _urllib_transport(url, payload_bytes, timeout=None):
    """Production transport: POST JSON to the n8n webhook. Only used when the caller
    does not inject a transport (so it NEVER runs in the offline self-test/verify).
    Sends X-Rescue-Secret when the env carries it - the rr-v2-intake webhook 403s
    without it, so an escalation without the header was silently dead.

    RR-SENDER-FIX-20260826: the STATUS and the BODY are both inspected. A non-2xx,
    and a 2xx whose body carries an admission refusal, now raise EscalationRefused
    so send() spills to UNSENT instead of reporting a delivery that never happened.
    Returning True here means the intake ADMITTED the escalation - nothing less.
    The timeout is no longer a hard-coded 10s (see _rr_timeout), and both the URL
    and the secret are unquoted before use."""
    import urllib.error
    import urllib.request
    timeout = timeout or _rr_timeout()
    headers = {"Content-Type": "application/json"}
    secret = _unquote_env(os.environ.get(SECRET_ENV, ""))
    if secret:
        headers["X-Rescue-Secret"] = secret
    req = urllib.request.Request(url, data=payload_bytes,
                                 headers=headers,
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            status = int(getattr(resp, "status", 0) or 0)
            body = resp.read(_BODY_READ_LIMIT).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        code = int(getattr(exc, "code", 0) or 0)
        try:
            detail = exc.read(_BODY_READ_LIMIT).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            detail = ""
        raise EscalationRefused(
            "intake HTTP %d: %s" % (code, _trim(detail))) from exc
    if not 200 <= status < 300:
        raise EscalationRefused("intake HTTP %d: %s" % (status, _trim(body)))
    if _intake_verdict(body) is False:
        raise EscalationRefused(
            "intake refused a %d payload: %s" % (status, _trim(body)))
    return True


def send(payload, transport=None, url=None):
    """Deliver an escalation. `transport(url, bytes)->bool` is injectable (the
    self-test passes a stub that raises, so no real network is touched). On ANY
    failure - transport down OR intake refusal - the payload is written to
    UNSENT-esc-<ts>.json for next-tick retry (see drain()), NEVER a fall-back to
    the silently-dropped group send.

    RR-SENDER-FIX-20260826: the reason rides back in `error` instead of being
    swallowed, and is recorded in the spill file as `_unsent_reason` so a dead
    relay is readable on the box afterwards. Returns
    {sent: bool, unsent_path: str|None, error: str|None}."""
    url = url or _unquote_env(os.environ.get(WEBHOOK_ENV, "")) or DEFAULT_WEBHOOK
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    tx = transport or _urllib_transport
    err = None
    try:
        ok = bool(tx(url, body))
        if ok:
            return {"sent": True, "unsent_path": None, "error": None}
        err = "transport returned a falsy result; no delivery was confirmed"
    except Exception as exc:  # noqa: BLE001 - transport failure OR intake refusal
        err = _trim("%s: %s" % (type(exc).__name__, exc), 600)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    p = escalations_dir() / ("UNSENT-esc-%s-%s.json" % (payload.get("driver", "x"), ts))
    spill = dict(payload)
    spill["_unsent_reason"] = err
    p.write_text(json.dumps(spill, indent=2, sort_keys=True), encoding="utf-8")
    return {"sent": False, "unsent_path": str(p), "error": err}


def drain(limit=None, transport=None, url=None, dry_run=False, spacing=None):
    """Re-post escalations that were spilled to UNSENT and then ABANDONED.

    RR-SENDER-DRAIN-20260826. This module's own header and REPAIRS.md have always
    told the operator a spilled payload is "retried next tick". Nothing ever read
    the directory back: the only glob("UNSENT-*") calls in the whole skill lived
    inside self_test(). Escalations were detected correctly, spilled faithfully,
    and lost forever - 17,058 files across the fleet, none ever delivered.

    Deliberately SLOW. The Rescue Rangers intake is rate-limited GLOBALLY across
    the fleet, not per box, so a fast drain would shed OTHER clients' live
    escalations - a self-inflicted outage worse than the backlog. Therefore:
      * spills are DEDUPED by problem identity (see _spill_signature),
      * at most `limit` distinct problems per tick (default 2),
      * spaced `spacing` seconds apart after a deterministic per-box offset,
      * and the drain STOPS for this tick the moment one post fails.

    A file is cleared only on CONFIRMED admission, and is MOVED to
    escalations/drained/ - never deleted. The backlog is evidence.

    Returns a summary dict; never raises."""
    d = escalations_dir()
    archive = d / "drained"
    files = sorted(d.glob("UNSENT-esc-*.json"),
                   key=lambda p: (p.stat().st_mtime, p.name))
    summary = {"pending_files": len(files), "unique_problems": 0, "posted": 0,
               "archived_files": 0, "unparseable": 0, "dry_run": bool(dry_run),
               "stopped": None}
    if not files:
        return summary
    groups = {}
    for f in files:
        try:
            payload = json.loads(f.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("spill is not an object")
        except Exception:  # noqa: BLE001 - never re-post what we cannot read
            summary["unparseable"] += 1
            continue
        groups.setdefault(_spill_signature(payload), []).append((f, payload))
    summary["unique_problems"] = len(groups)
    if not groups:
        summary["stopped"] = "every pending spill was unparseable"
        return summary
    order = sorted(groups.items(), key=lambda kv: kv[1][0][0].stat().st_mtime)
    cap = _drain_limit() if limit is None else int(limit)
    gap = _drain_spacing() if spacing is None else float(spacing)
    known = {str(p) for p in files}
    first = True
    for sig, members in order:
        if summary["posted"] >= cap:
            summary["stopped"] = "per-tick cap reached (%d)" % cap
            break
        oldest_file, payload = members[0]
        replay = dict(payload)
        replay.pop("_unsent_reason", None)
        replay["_replay"] = {
            "signature": sig,
            "occurrences": len(members),
            "first_spilled": _mtime_iso(oldest_file),
            "last_spilled": _mtime_iso(members[-1][0]),
            "replayed_at": datetime.now(timezone.utc)
                           .replace(microsecond=0).isoformat(),
        }
        if dry_run:
            summary["posted"] += 1
            continue
        if first and gap > 0:
            time.sleep(_drain_jitter())
        elif gap > 0:
            time.sleep(gap)
        first = False
        res = send(replay, transport=transport, url=url)
        if not res.get("sent"):
            # The intake is refusing or unreachable. STOP - never hammer a
            # struggling, globally rate-limited intake with a backlog.
            summary["stopped"] = "post failed, backing off: %s" % res.get("error")
            # send() just spilled a NEW file for this replay attempt. Drop it, or
            # every failed drain would GROW the backlog it is trying to clear.
            up = res.get("unsent_path")
            if up and str(up) not in known:
                try:
                    Path(up).unlink()
                except OSError:
                    pass
            break
        summary["posted"] += 1
        try:
            archive.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            summary["stopped"] = "cannot create archive dir: %s" % exc
            break
        for f, _p in members:
            try:
                f.rename(archive / f.name)   # MOVED, never deleted: evidence
                summary["archived_files"] += 1
            except OSError:
                pass
    return summary


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
    # RR-SENDER-FIX-20260826: the intake keys on `message`; `finding` is kept.
    assert payload["message"] == payload["finding"]
    print("  payload case: PASS (SOP format + machine block + intake `message` present)")

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

        # RR-SENDER-FIX-20260826: a 2xx carrying an admission REFUSAL is a failure,
        # not a delivery. Before this fix it returned sent=True and the escalation
        # vanished with no trace on the box. Proven offline - no network.
        assert _intake_verdict('{"accepted":false,"rejectReason":"missing message"}') is False
        assert _intake_verdict('{"accepted":true,"ticketId":null,"status":"test_suppressed"}') is True
        assert _intake_verdict('{"admission":{"decision":"reject_invalid"}}') is False
        assert _intake_verdict('{"admission":{"decision":"accept"}}') is True
        assert _intake_verdict("<html>502 Bad Gateway</html>") is None  # UNDETERMINED, not refused

        def refusing_transport(url, body):
            raise EscalationRefused("intake refused a 200 payload: missing message")
        res3 = send(payload, transport=refusing_transport)
        assert res3["sent"] is False and res3["unsent_path"]
        assert "refused" in (res3["error"] or "")
        assert "_unsent_reason" in Path(res3["unsent_path"]).read_text(encoding="utf-8")
        print("  intake-refusal case: PASS (a 200 that refuses no longer reports sent)")

        # The production transport must resolve every global it touches. A missing
        # constant here is invisible to every other drill, because they all inject
        # a stub and NEVER execute _urllib_transport. Checked statically - offline.
        import builtins as _builtins
        import dis as _dis
        _missing = sorted({i.argval for i in _dis.get_instructions(_urllib_transport)
                           if i.opname == "LOAD_GLOBAL"}
                          - set(_urllib_transport.__globals__)
                          - set(dir(_builtins)))
        assert not _missing, ("_urllib_transport references undefined global(s): %s"
                              % ", ".join(_missing))
        print("  transport-globals case: PASS (no undefined name on the real send path)")

        # A quote-wrapped env URL and a 10s timeout each killed real escalations
        # on their own. Both proven here, offline, with no network.
        assert _unquote_env("'https://x/y'") == "https://x/y"
        assert _unquote_env('"https://x/y"') == "https://x/y"
        assert _unquote_env("https://x/y") == "https://x/y"
        assert _unquote_env("it's fine") == "it's fine"  # unmatched quote left alone
        assert _rr_timeout() >= 90  # MEASURED: real admission path 29.8s (n8n exec
        # 596246) and longer under fleet load. The old 10s never stood a chance.
        os.environ[TIMEOUT_ENV] = "7"
        assert _rr_timeout() == 7
        os.environ.pop(TIMEOUT_ENV, None)
        print("  unquote/timeout case: PASS (quoted URL survives; 120s timeout, overridable)")

        os.environ.pop("LOOP_STATE_DIR", None)

    # ---- the DRAIN: dedup, cap, archive-not-delete, back off on refusal -------
    # Fully offline. Proves the queue REPAIRS.md always claimed was retried.
    with tempfile.TemporaryDirectory() as td2:
        os.environ["LOOP_STATE_DIR"] = td2
        esc_dir = escalations_dir()
        base = build_payload(box="box-example", loop_class="LP-A9",
                             finding="semantic retry loop against a fail-closed dep",
                             evidence_path="~/.openclaw/x.log", proposed_fix="LF-11",
                             why="drill", action_needed="operator decision")
        other = dict(base, finding="a DIFFERENT problem")
        for i in range(4):                       # 4 copies of ONE problem
            (esc_dir / ("UNSENT-esc-LP-A9-2026082%dT000000.json" % i)).write_text(
                json.dumps(base, sort_keys=True), encoding="utf-8")
        (esc_dir / "UNSENT-esc-LP-A9-20260825T000000.json").write_text(
            json.dumps(other, sort_keys=True), encoding="utf-8")
        (esc_dir / "UNSENT-esc-LP-A9-20260826T000000.json").write_text(
            "{ not json", encoding="utf-8")

        seen = []

        def counting_ok(url, body):
            seen.append(json.loads(body.decode("utf-8")))
            return True

        r = drain(limit=9, transport=counting_ok, spacing=0)
        assert r["pending_files"] == 6, r
        assert r["unparseable"] == 1, r          # the junk file is never re-posted
        assert r["unique_problems"] == 2, r      # 5 readable files, 2 real problems
        assert r["posted"] == 2, r               # ONE post per distinct problem
        assert r["archived_files"] == 5, r
        assert len(seen) == 2
        assert seen[0]["_replay"]["occurrences"] == 4  # the 4 copies collapsed
        assert seen[0]["message"] == seen[0]["finding"]
        assert len(list(esc_dir.glob("UNSENT-esc-*.json"))) == 1   # only the junk left
        assert len(list((esc_dir / "drained").glob("*.json"))) == 5
        print("  drain dedup case: PASS (4 copies of one problem -> ONE post; "
              "unreadable spill skipped; files ARCHIVED, never deleted)")

        # A refusal must archive NOTHING and must not grow the backlog.
        (esc_dir / "UNSENT-esc-LP-B1-20260826T010000.json").write_text(
            json.dumps(dict(base, driver="LP-B1"), sort_keys=True), encoding="utf-8")
        before = len(list(esc_dir.glob("UNSENT-esc-*.json")))

        def refusing(url, body):
            raise EscalationRefused("intake refused a 200 payload")

        r2 = drain(limit=9, transport=refusing, spacing=0)
        assert r2["posted"] == 0 and r2["archived_files"] == 0, r2
        assert "backing off" in (r2["stopped"] or ""), r2
        assert len(list(esc_dir.glob("UNSENT-esc-*.json"))) == before, "drain grew the backlog"
        print("  drain refusal case: PASS (nothing archived, backlog did not grow, backed off)")

        # The per-tick cap is what protects a GLOBALLY rate-limited intake.
        assert drain(limit=1, transport=counting_ok, spacing=0, dry_run=True)["posted"] == 1
        print("  drain cap case: PASS (per-tick cap honoured; dry-run posts nothing)")

        os.environ.pop("LOOP_STATE_DIR", None)

    print("[loop_escalate] self-test: PASS")
    return 0


def _cli(argv=None):
    ap = argparse.ArgumentParser(description="Loop Protection Rescue Rangers escalation.")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--drain", action="store_true",
                    help="re-post spilled UNSENT escalations (deduped, rate-limited)")
    ap.add_argument("--limit", type=int, default=None,
                    help="max DISTINCT problems to re-post this run")
    ap.add_argument("--dry-run", action="store_true",
                    help="build + print the payload, do NOT POST (offline)")
    ap.add_argument("--box"); ap.add_argument("--loop-class")
    ap.add_argument("--finding"); ap.add_argument("--evidence-path")
    ap.add_argument("--proposed-fix"); ap.add_argument("--why")
    ap.add_argument("--action-needed"); ap.add_argument("--finding-id", type=int)
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    if a.drain:
        res = drain(limit=a.limit, dry_run=a.dry_run)
        print(json.dumps(res, sort_keys=True))
        return 0
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
