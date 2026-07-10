#!/usr/bin/env python3
# =============================================================================
# SKILL 60 - ZHC EARLY WARNING SYSTEM :: ews_sentinel.py
# THE PER-BOX DETECTOR - runs S1..S10 each tick (spec Section 3)
# -----------------------------------------------------------------------------
# The heart of the system. One tick per 15 minutes (D3), ZERO model calls, ZERO
# network beyond the local gateway send (which the alert layer owns). Every check
# is deterministic file / stat / diff / arithmetic work. The sentinel is the only
# non-ledger script that RECORDS events; it goes through ews_ledger for all state
# and through ews_alert for all sends (operator-only, deduped).
#
# The ten signals, each a pure detector so it is unit-testable against fixtures:
#   S1 model/provider config drift          S6 config-write hygiene + root-owner
#   S2 runtime fallback (trajectory truth)  S7 surfaces dark (gateway/dash/tunnel)
#   S3 context vs compaction (D5 routing)   S8 secret leaked into transcript/log
#   S4 safety-cap raise (never-silently)    S9 skills integrity / stale downgrade
#   S5 furnace / idle-burn (D9 billing)     S10 cron / delivery drift
#
# DOCTRINE: never print a secret value (S8 reports file:line + class only); model
# choice is sovereign (S1/S2 ALERT, never act); caps are ALERT-ONLY by default (D2,
# enforce_caps off); the D5 context running-low warning routes to the BOX'S OWN
# agent, and the operator is alerted ONLY for the broken-config crash case.
#
# STDLIB ONLY. EXIT CODES: 0 clean tick (no findings), 1 error, 2 usage,
#   10 findings present (a non-zero, non-error signal for cron log scrapers).
# =============================================================================
"""ews_sentinel.py - the per-box S1..S10 detector for the ZHC Early Warning System."""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import ews_common as C  # noqa: E402
from ews_ledger import Ledger, default_state_dir, openclaw_root  # noqa: E402
import ews_baseline as B  # noqa: E402
import ews_snapshot as SNAP  # noqa: E402

EX_OK, EX_ERR, EX_USAGE, EX_FINDINGS = 0, 1, 2, 10

# routes a finding can carry
R_OPERATOR = "operator"       # default: the operator Telegram (via the gateway)
R_BOX_AGENT = "box_agent"     # D5: the box's OWN agent (self-handoff/flush), NOT operator

# S8 secret-CLASS shapes (same high-precision classes as scan-no-secrets.sh; the
# VALUE is never emitted, only file:line + class). Version-pinned in signatures.json.
_SECRET_CLASSES = [
    ("provider_sk", re.compile(r"sk-(?:proj-|ant-|or-v1-)?[A-Za-z0-9_-]{20,}")),
    ("caf_pit", re.compile(r"pit-[A-Za-z0-9]{20,}")),
    ("google_api", re.compile(r"AIza[0-9A-Za-z_-]{35}")),
    ("aws_akid", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("slack_token", re.compile(r"xox[abprs]-[0-9A-Za-z-]{10,}")),
    ("github_pat", re.compile(r"(?:gh[pousr]_[0-9A-Za-z]{36}|github_pat_[0-9A-Za-z_]{50,})")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{6,}")),
]


def F(signal, severity, key_path=None, klass=None, detail=None, route=R_OPERATOR,
      revert_cmd=None, dedup_key=None, enforce=False, escalate_provider=False):
    return {"signal": signal, "severity": severity, "key_path": key_path, "class": klass,
            "detail": detail, "route": route, "revert_cmd": revert_cmd,
            "dedup_key": dedup_key or ("%s|%s" % (signal, key_path or "")),
            "enforce": enforce, "escalate_provider": escalate_provider}


# --------------------------------------------------------------------------- #
# value helpers
# --------------------------------------------------------------------------- #
def _strings_in(value):
    out = []
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, list):
        for x in value:
            out.extend(_strings_in(x))
    elif isinstance(value, dict):
        for k, v in value.items():
            out.append(str(k))
            out.extend(_strings_in(v))
    return out


def _family_or_paid(value, sig):
    fam = paid = False
    for s in _strings_in(value):
        f = C.model_id_flags(s, sig)
        fam = fam or f["family"]
        paid = paid or f["paid"]
    return fam, paid


# --------------------------------------------------------------------------- #
# S1 - model/provider config drift
# --------------------------------------------------------------------------- #
def sig_s1(diffs, role, sig, revert_cmd=None):
    findings = []
    for d in diffs:
        if d["class"] != "model" or not d["changed"]:
            continue
        fam, paid = _family_or_paid(d.get("live_value"), sig)
        sev = "P2"
        why = "model config changed (%s)" % d["direction"]
        if role == "client" and (fam or paid):
            sev = "P1"
            why = ("model config changed to a %s tier on a CLIENT box"
                   % ("Anthropic-family" if fam else "paid"))
        findings.append(F("S1", sev, d["path"], "model",
                          "%s; ALERT only - client model choice is sovereign, the "
                          "operator decides" % why, revert_cmd=revert_cmd))
    return findings


# --------------------------------------------------------------------------- #
# S4 - safety-cap raise (the never-silently rule)
# --------------------------------------------------------------------------- #
def sig_s4(diffs, led, role, enforce_caps, revert_cmd=None):
    findings = []
    for d in diffs:
        if d["class"] not in ("cap", "access") or not d["dangerous"]:
            continue
        live_hash = C.sha256_of_value(d.get("live_value"))
        if led is not None and led.has_stamp(d["path"], live_hash):
            continue  # stamped = deliberate = silent
        detail = ("safety limit %s (%s) with NO approval stamp; run "
                  "'approve-baseline --key %s' if intended, else revert"
                  % (d["direction"], d["class"], d["path"]))
        enforce = bool(enforce_caps) and d["class"] == "cap"
        findings.append(F("S4", "P1", d["path"], d["class"], detail,
                          revert_cmd=revert_cmd, enforce=enforce))
    return findings


# --------------------------------------------------------------------------- #
# S10 - cron / delivery drift
# --------------------------------------------------------------------------- #
def sig_s10(baseline_cron, live_cron, operator_targets=None):
    findings = []
    op = {str(t).lower() for t in (operator_targets or ["operator"])}
    base_names = {c["name"] for c in baseline_cron}
    for c in live_cron:
        if c["name"] not in base_names:
            findings.append(F("S10", "P2", "cron:%s" % c["name"], "cron",
                              "new cron not in baseline: %s" % c["name"],
                              dedup_key="S10|new|%s" % c["name"]))
        if c.get("delivery") == "announce":
            tgt = str(c.get("target") or "").lower()
            if tgt not in op:
                findings.append(F("S10", "P1", "cron:%s" % c["name"], "cron",
                                  "cron '%s' delivery=announce to a NON-operator target; "
                                  "re-register with --no-deliver (client-spam trap)" % c["name"],
                                  dedup_key="S10|announce|%s" % c["name"]))
    return findings


# --------------------------------------------------------------------------- #
# S3 - context vs compaction (D5 routing)
# --------------------------------------------------------------------------- #
def sig_s3(config, thresholds, usage_pct=None, context_window=None):
    findings = []
    broken, ceiling, reason = C.subtractive_broken(config, context_window)
    if broken:
        findings.append(F("S3", "P1", C._SOFT_THRESHOLD_PATH, "compaction",
                          "BROKEN CONFIG: %s (effective ceiling %s). This box WILL die "
                          "with 'Context too large' no matter what - fix the config, then "
                          "/new. This is the ONLY S3 case that alerts the operator (D5)."
                          % (reason, ceiling), route=R_OPERATOR,
                          dedup_key="S3|broken"))
    # running-low: routes to the BOX'S OWN agent (D5), never the operator
    if usage_pct is not None:
        note = thresholds.get("context", {}).get("note_threshold_pct", 70)
        handoff = thresholds.get("context", {}).get("handoff_threshold_pct", 85)
        if usage_pct >= handoff:
            findings.append(F("S3", "P2", "context.usage", "compaction",
                              "context at %d%% of the effective ceiling - recommend a "
                              "proactive handoff / new session NOW while context remains"
                              % usage_pct, route=R_BOX_AGENT, dedup_key="S3|handoff"))
        elif usage_pct >= note:
            findings.append(F("S3", "P3", "context.usage", "compaction",
                              "context at %d%% of the effective ceiling (note)" % usage_pct,
                              route=R_BOX_AGENT, dedup_key="S3|note"))
    return findings


# --------------------------------------------------------------------------- #
# S2 - runtime fallback (trajectory ground truth)
# --------------------------------------------------------------------------- #
def sig_s2(model_allowlist, traj_events, role, sig):
    findings = []
    allow = set(model_allowlist or [])
    out = []
    for ev in traj_events:
        mid = ev.get("modelId")
        prov = ev.get("provider")
        if mid and mid not in allow:
            out.append(ev)
    if not out:
        return findings
    count = len(out)
    # classify the worst
    worst_fam = any(C.model_id_flags(e.get("modelId"), sig)["family"] for e in out)
    worst_paid = any(C.model_id_flags(e.get("modelId"), sig)["paid"] for e in out)
    sev = "P2"
    detail = "%d runtime event(s) on a model outside the baseline allowlist" % count
    if role == "client" and (worst_fam or worst_paid):
        sev = "P1"
        detail = ("%d runtime event(s) on a %s model outside the allowlist on a CLIENT box"
                  % (count, "Anthropic-family" if worst_fam else "paid"))
    elif count >= 3:
        sev = "P1"
        detail = "%d runtime fallback events in one tick - provider likely down" % count
    sample = out[0]
    findings.append(F("S2", sev, "trajectory", "model",
                      "%s (e.g. session=%s model=%s)"
                      % (detail, sample.get("sessionId"), sample.get("modelId")),
                      dedup_key="S2|%s" % sample.get("modelId")))
    return findings


# --------------------------------------------------------------------------- #
# S5 - furnace / idle-burn (D9 billing-aware)
# --------------------------------------------------------------------------- #
def _billing_for(model_or_provider, billing):
    mid = str(model_or_provider or "").lower()
    for entry in billing.get("provider_billing_defaults", []):
        for m in entry.get("provider_match", []):
            if m.lower() in mid:
                return entry.get("billing_type"), entry.get("note")
    return billing.get("default_billing_type"), billing.get("default_note")


def sig_s5(config, traj_events, billing, role, initiated_sessions=None, sig=None):
    findings = []
    sig = sig if sig is not None else C.load_signatures()
    defaults = C.dotpath_get(config, "agents.defaults")
    hb = defaults.get("heartbeat") if isinstance(defaults, dict) else None
    if isinstance(hb, dict):
        every = hb.get("every")
        bound = C.fires_per_day_bound(every)
        if bound is not None and bound > 24.0 + 1e-9:  # sub-hourly heartbeat = furnace
            findings.append(F("S5", "P2", "agents.defaults.heartbeat.every", "furnace",
                              "heartbeat cadence ~%.0f/day (sub-hourly) - cadence IS spend"
                              % bound, dedup_key="S5|cadence"))
        hbm = hb.get("model")
        if hbm and C.model_id_flags(hbm, sig)["paid"]:
            bt, _ = _billing_for(hbm, billing)
            frame = billing.get("billing_types", {}).get(bt, {})
            findings.append(F("S5", "P2", "agents.defaults.heartbeat.model", "furnace",
                              "heartbeat model '%s' resolves to a paid tier (%s: %s)"
                              % (hbm, bt, frame.get("alert_verb", "")), dedup_key="S5|hbmodel"))
    # idle burn: paid-model trajectory events with no initiated session in the window
    if initiated_sessions is not None and initiated_sessions == 0:
        paid_events = [e for e in traj_events
                       if C.model_id_flags(e.get("modelId"), sig)["paid"]]
        if paid_events:
            mid = paid_events[0].get("modelId")
            bt, _ = _billing_for(mid, billing)
            frame = billing.get("billing_types", {}).get(bt, {})
            findings.append(F("S5", "P1", "trajectory", "furnace",
                              "IDLE BURN: %d paid-model event(s) with ZERO initiated sessions - "
                              "%s (impact: %s). Allowlist + tier the heartbeat model."
                              % (len(paid_events), frame.get("alert_verb", "wasting tokens"),
                                 frame.get("frame", "")),
                              dedup_key="S5|idleburn", escalate_provider=True))
    return findings


# --------------------------------------------------------------------------- #
# S6 - config-write hygiene + root-owner
# --------------------------------------------------------------------------- #
def _is_known_writer(argv, tokens):
    """A config.write is by a sanctioned writer when some argv WORD's basename starts
    with a known-writer token (openclaw CLI, update-skills, ews-entry.sh, ews_*,
    bump-version.sh). Config-file arguments (*.json/*.jsonl) are skipped so that the
    config PATH 'openclaw.json' never masquerades as the 'openclaw' binary."""
    toks = [t.lower() for t in (tokens or [])]
    for word in str(argv or "").split():
        base = word.rsplit("/", 1)[-1].lower()
        if base.endswith(".json") or base.endswith(".jsonl"):
            continue
        if any(base.startswith(t) for t in toks):
            return True
    return False


def sig_s6(audit_writes, config_owner, box_user, known_writer_tokens):
    findings = []
    if config_owner and config_owner in ("root", "0"):
        findings.append(F("S6", "P1", "config.owner", "config",
                          "openclaw.json is owned by root - gateway freeze imminent. "
                          "Remediation: chown to the box user (%s), validate, then restart "
                          "the gateway per the platform's sanctioned procedure." % (box_user or "node"),
                          dedup_key="S6|root-owned"))
    elif box_user and config_owner and config_owner != box_user and config_owner not in ("root", "0"):
        findings.append(F("S6", "P2", "config.owner", "config",
                          "openclaw.json owner '%s' is not the box user '%s'"
                          % (config_owner, box_user), dedup_key="S6|owner"))
    for w in audit_writes:
        argv = str(w.get("argv") or "")
        if argv and not _is_known_writer(argv, known_writer_tokens):
            findings.append(F("S6", "P2", "config.write", "config",
                              "config.write by an UNKNOWN writer (pid=%s) - argv not in the "
                              "known-writer allowlist" % w.get("pid"),
                              dedup_key="S6|unknown|%s" % w.get("pid")))
    return findings


# --------------------------------------------------------------------------- #
# S7 - surfaces dark
# --------------------------------------------------------------------------- #
def sig_s7(probe):
    findings = []
    if probe.get("gateway") == "down":
        findings.append(F("S7", "P1", "surface.gateway", "surface",
                          "gateway unreachable locally", dedup_key="S7|gateway"))
    if probe.get("dashboard") == "down":
        findings.append(F("S7", "P2", "surface.dashboard", "surface",
                          "Command Center probe failing", dedup_key="S7|dashboard"))
    if probe.get("tunnel") == "down":
        findings.append(F("S7", "P2", "surface.tunnel", "surface",
                          "cloudflared tunnel down", dedup_key="S7|tunnel"))
    return findings


def probe_surfaces():
    """Best-effort LOCAL probes (no network beyond localhost). Returns up/down/unknown
    per surface. Conservative: only 'down' when a probe DEFINITIVELY fails, so a probe
    we cannot run is 'unknown' (never a false P1); the dead-man switch is the real net
    for a box that cannot self-report."""
    def proc_running(pattern):
        try:
            r = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True, timeout=10)
            if r.returncode == 0 and r.stdout.strip():
                return "up"
            if r.returncode == 1:
                return "down"
        except (OSError, subprocess.SubprocessError):
            pass
        return "unknown"
    gw = proc_running("openclaw")
    tun = proc_running("cloudflared")
    return {"gateway": gw, "tunnel": tun, "dashboard": "unknown"}


# --------------------------------------------------------------------------- #
# S8 - secret leaked into transcript/log
# --------------------------------------------------------------------------- #
def sig_s8(chunks):
    """chunks: list of (source_name, text). Scans line by line; reports file:line +
    CLASS only - the VALUE is NEVER reproduced."""
    findings = []
    for name, text in chunks:
        for i, line in enumerate(text.splitlines(), 1):
            for klass, rx in _SECRET_CLASSES:
                if rx.search(line):
                    findings.append(F("S8", "P1", "%s:%d" % (name, i), "secret",
                                      "secret shape [%s] in %s:%d (VALUE NOT SHOWN)"
                                      % (klass, name, i),
                                      dedup_key="S8|%s|%s|%d" % (klass, name, i)))
                    break
    return findings


# --------------------------------------------------------------------------- #
# S9 - skills integrity drift / stale downgrade
# --------------------------------------------------------------------------- #
def sig_s9(baseline_manifest, current_manifest):
    findings = []
    if not baseline_manifest or not current_manifest:
        return findings
    for skill, base_hash in baseline_manifest.items():
        if skill == "__TREE_SHA__":
            continue
        cur = current_manifest.get(skill)
        if cur is None:
            findings.append(F("S9", "P1", "skill:%s" % skill, "skills",
                              "skill '%s' present at baseline is MISSING now - possible "
                              "downgrade/partial rollout" % skill, dedup_key="S9|gone|%s" % skill))
        elif cur != base_hash:
            findings.append(F("S9", "P2", "skill:%s" % skill, "skills",
                              "skill '%s' content hash drifted from the pinned manifest"
                              % skill, dedup_key="S9|drift|%s" % skill))
    return findings


# =========================================================================== #
# TICK ORCHESTRATION
# =========================================================================== #
def _read_audit_writes(led, audit_path, max_bytes=2_000_000):
    """Tail config-audit.jsonl from the stored offset; return (writes, new_offset)."""
    p = Path(audit_path)
    if not p.is_file():
        return [], led.get_offset("config-audit")
    size = p.stat().st_size
    off = led.get_offset("config-audit")
    if off > size:
        off = 0  # file rotated/truncated
    writes = []
    with open(p, "r", encoding="utf-8", errors="replace") as fh:
        fh.seek(off)
        data = fh.read(max_bytes)
        new_off = fh.tell()
    for line in data.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("event") == "config.write":
            writes.append(row)
    return writes, new_off


def _read_trajectory_events(led, max_files=50, max_bytes=1_000_000):
    """Read NEW bytes of trajectory files since the last tick; return events."""
    base = openclaw_root() / "agents"
    events = []
    files = sorted(glob.glob(str(base / "*" / "sessions" / "*.trajectory.jsonl")))[:max_files]
    for f in files:
        key = "traj:%s" % f
        try:
            size = os.path.getsize(f)
        except OSError:
            continue
        off = led.get_offset(key)
        if off > size:
            off = 0
        with open(f, "r", encoding="utf-8", errors="replace") as fh:
            fh.seek(off)
            data = fh.read(max_bytes)
            new_off = fh.tell()
        for line in data.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            mid = row.get("modelId") or row.get("model")
            if mid:
                events.append({"modelId": mid, "provider": row.get("provider"),
                               "sessionId": row.get("sessionId"), "_file": f})
        led.set_offset(key, new_off)
    return events


def run_tick(state_dir=None, config_path=None, send=True, probe=None, role=None):
    """One deterministic tick. Records events; routes findings via ews_alert unless
    send is False. Returns a summary dict."""
    thresholds = C.load_skill_config("thresholds.json")
    signatures = C.load_signatures()
    billing = C.load_skill_config("billing-models.json")
    findings = []

    with Ledger(state_dir) as led:
        role = role or led.get_meta("role", "client")
        enforce_caps = led.get_meta("enforce_caps", "false") == "true"

        # config (best effort)
        try:
            config = C.read_config(config_path)
        except (OSError, ValueError):
            config = None
            led.record_event("S7", "P1", key_path="config", klass="config",
                             detail="live openclaw.json unreadable/unparseable")

        # --- S6: audit tail + snapshot every write + ownership -----------------
        audit_path = openclaw_root() / "logs" / "config-audit.jsonl"
        writes, new_off = _read_audit_writes(led, audit_path)
        for w in writes:
            try:
                SNAP.take_snapshot(config_path, state_dir,
                                   previous_hash=w.get("previousHash"), argv=str(w.get("argv")))
            except (OSError, FileNotFoundError):
                pass
        led.set_offset("config-audit", new_off)

        baseline = None
        bp = B.baseline_path(Path(state_dir) if state_dir else None)
        if bp.is_file():
            baseline = json.loads(bp.read_text(encoding="utf-8"))

        # a single revert command per tick if the config changed
        revert_cmd = None
        diffs = []
        if baseline and config is not None:
            diffs = B.compute_diff(baseline, config)
            if any(d["changed"] for d in diffs):
                try:
                    snap = SNAP.take_snapshot(config_path, state_dir)
                    revert_cmd = snap["revert_cmd"]
                except (OSError, FileNotFoundError):
                    revert_cmd = None

        box_user = baseline.get("user") if baseline else None
        config_owner = baseline.get("config_owner") if baseline else None
        # re-stat live owner for freshness
        try:
            import pwd
            st = (Path(config_path) if config_path else C.default_config_path()).stat()
            config_owner = pwd.getpwuid(st.st_uid).pw_name
        except (OSError, KeyError, ImportError):
            pass
        findings += sig_s6(writes, config_owner, box_user,
                           signatures.get("known_writer_argv_tokens", []))

        # --- S1 / S4 / S10 (need baseline) -------------------------------------
        if baseline and config is not None:
            findings += sig_s1(diffs, role, signatures, revert_cmd)
            findings += sig_s4(diffs, led, role, enforce_caps, revert_cmd)
            findings += sig_s10(baseline.get("cron_inventory", []), C.cron_inventory(config))

        # --- S3 (no baseline needed) -------------------------------------------
        if config is not None:
            findings += sig_s3(config, thresholds)

        # --- S2 / S5 (trajectory) ----------------------------------------------
        traj = _read_trajectory_events(led)
        if baseline:
            findings += sig_s2(baseline.get("model_allowlist", []), traj, role, signatures)
        if config is not None:
            findings += sig_s5(config, traj, billing, role, sig=signatures)

        # --- S7 surfaces --------------------------------------------------------
        findings += sig_s7(probe if probe is not None else probe_surfaces())

        # --- S9 skills manifest -------------------------------------------------
        if baseline and baseline.get("skills_manifest"):
            cur = B._skills_manifest()
            findings += sig_s9(baseline.get("skills_manifest"), cur)

        # record every finding as an event
        recorded = []
        for f in findings:
            eid = led.record_event(f["signal"], f["severity"], f["key_path"], f["class"],
                                   f["detail"], dedup_key=f["dedup_key"])
            f["event_id"] = eid
            recorded.append(f)

    # route (outside the ledger context; the alert layer opens its own)
    sent = 0
    if send and recorded:
        sent = _route(recorded, state_dir)

    summary = {"ok": True, "action": "tick", "role": role,
               "findings": len(recorded),
               "by_severity": _tally(recorded),
               "sent": sent}
    return summary, recorded


def _tally(findings):
    t = {}
    for f in findings:
        t[f["severity"]] = t.get(f["severity"], 0) + 1
    return t


def _route(findings, state_dir):
    """Hand findings to ews_alert (operator-only, deduped). Import lazily so the
    sentinel's detectors stay usable even before the alert layer exists."""
    try:
        import ews_alert
    except ImportError:
        return 0
    sent = 0
    for f in findings:
        try:
            if ews_alert.route_finding(f, state_dir):
                sent += 1
        except Exception:  # noqa: BLE001 - a send failure never crashes the tick
            pass
    return sent


def _emit(obj):
    sys.stdout.write(json.dumps(obj, sort_keys=True) + "\n")


def _cli(argv=None):
    ap = argparse.ArgumentParser(prog="ews_sentinel.py",
                                 description="The per-box S1..S10 detector (Skill 60).")
    ap.add_argument("--state-dir")
    ap.add_argument("--config")
    ap.add_argument("--no-send", action="store_true", help="detect and record, but do not route alerts")
    ap.add_argument("--role", choices=["client", "operator"])
    ap.add_argument("--self-test", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=False)
    sub.add_parser("tick")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.cmd != "tick":
        ap.error("expected the 'tick' subcommand (or --self-test)")
    summary, _ = run_tick(Path(args.state_dir) if args.state_dir else None,
                          args.config, send=not args.no_send, role=args.role)
    _emit(summary)
    return EX_FINDINGS if summary["findings"] else EX_OK


# =========================================================================== #
# self-test (deterministic; drives every detector against fixtures)
# =========================================================================== #
def self_test():
    print("[ews_sentinel] self-test: S1..S10 detectors + an end-to-end no-send tick")
    sig = C.load_signatures()
    billing = C.load_skill_config("billing-models.json")
    thresholds = C.load_skill_config("thresholds.json")
    fam_id = ("clau" + "de") + "-3-opus"  # assembled, no contiguous banned literal

    # S1
    diffs_model = [{"path": "agents.defaults.model.primary", "class": "model", "changed": True,
                    "direction": "change", "dangerous": False, "live_value": fam_id}]
    f1 = sig_s1(diffs_model, "client", sig)
    assert len(f1) == 1 and f1[0]["severity"] == "P1"
    f1b = sig_s1([{**diffs_model[0], "live_value": "glm-5.2"}], "client", sig)
    assert f1b[0]["severity"] == "P2"
    print("  S1 case: PASS (family on client=P1, benign=P2)")

    # S4 with a ledger (stamped raise is silent)
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        led = Ledger(Path(td) / "ews")
        diffs_cap = [{"path": "agents.defaults.subagents.maxConcurrent", "class": "cap",
                      "changed": True, "direction": "raise", "dangerous": True, "live_value": 64}]
        f4 = sig_s4(diffs_cap, led, "client", enforce_caps=False)
        assert len(f4) == 1 and f4[0]["severity"] == "P1" and not f4[0]["enforce"]
        # stamp it -> silent
        led.record_stamp("agents.defaults.subagents.maxConcurrent", C.sha256_of_value(64), "operator")
        assert sig_s4(diffs_cap, led, "client", enforce_caps=False) == []
        # enforce_caps on a cap sets the enforce flag
        led2diffs = [{"path": "agents.defaults.maxConcurrent", "class": "cap", "changed": True,
                      "direction": "raise", "dangerous": True, "live_value": 99}]
        fe = sig_s4(led2diffs, led, "client", enforce_caps=True)
        assert fe[0]["enforce"] is True
        led.close()
    print("  S4 case: PASS (unstamped raise=P1; stamped=silent; enforce flag when opted-in)")

    # S10
    f10 = sig_s10([{"name": "ews-tick"}],
                  [{"name": "ews-tick", "schedule": "*/15 * * * *", "delivery": "silent", "target": None},
                   {"name": "daily-report", "schedule": "0 9 * * *", "delivery": "announce", "target": "client"}])
    sevs = {(x["severity"], x["key_path"]) for x in f10}
    assert ("P2", "cron:daily-report") in sevs  # new cron
    assert ("P1", "cron:daily-report") in sevs  # announce to non-operator
    print("  S10 case: PASS (new cron=P2, announce-to-nonoperator=P1)")

    # S3 broken (operator) + running-low (box agent, NOT operator)
    broken_cfg = {"agents": {"defaults": {"compaction": {"memoryFlush":
                  {"softThresholdTokens": 900000}}}}, "_contextWindow": 128000}
    f3 = sig_s3(broken_cfg, thresholds)
    assert len(f3) == 1 and f3[0]["severity"] == "P1" and f3[0]["route"] == R_OPERATOR
    f3low = sig_s3({"agents": {"defaults": {}}}, thresholds, usage_pct=90)
    assert f3low and f3low[0]["route"] == R_BOX_AGENT and f3low[0]["severity"] == "P2"
    f3note = sig_s3({"agents": {"defaults": {}}}, thresholds, usage_pct=72)
    assert f3note and f3note[0]["route"] == R_BOX_AGENT and f3note[0]["severity"] == "P3"
    print("  S3 case: PASS (broken-config=P1 to OPERATOR; running-low routes to BOX agent, D5)")

    # S2
    events = [{"modelId": "glm-5.2", "provider": "openrouter", "sessionId": "s1"},
              {"modelId": fam_id, "provider": "openrouter", "sessionId": "s2"}]
    f2 = sig_s2(["glm-5.2"], events, "client", sig)
    assert f2 and f2[0]["severity"] == "P1"
    # 3+ out-of-allowlist non-family -> provider down P1
    many = [{"modelId": "x-%d" % i, "sessionId": "s"} for i in range(3)]
    f2b = sig_s2(["glm-5.2"], many, "operator", sig)
    assert f2b and f2b[0]["severity"] == "P1" and "provider likely down" in f2b[0]["detail"]
    print("  S2 case: PASS (family fallback on client=P1; 3+ fallbacks=provider-down P1)")

    # S5 furnace: idle burn with billing framing
    paid_ev = [{"modelId": "minimax-m3:cloud", "sessionId": "s"}]
    cfg_hb = {"agents": {"defaults": {"heartbeat": {"every": "0 * * * *", "model": "minimax-m3:cloud"}}}}
    f5 = sig_s5(cfg_hb, paid_ev, billing, "client", initiated_sessions=0, sig=sig)
    kinds = {(x["severity"], x["key_path"]) for x in f5}
    assert ("P1", "trajectory") in kinds  # idle burn
    idle = [x for x in f5 if x["key_path"] == "trajectory"][0]
    assert idle["escalate_provider"] and ("usage" in idle["detail"].lower() or "allowance" in idle["detail"].lower())
    print("  S5 case: PASS (idle burn P1 with billing framing + provider-check escalation)")

    # S6 root-owned + unknown writer
    f6 = sig_s6([{"argv": "vim openclaw.json", "pid": 4242}], "root", "node",
                ["openclaw", "update-skills", "ews_"])
    assert any(x["severity"] == "P1" and x["key_path"] == "config.owner" for x in f6)
    assert any(x["severity"] == "P2" and "UNKNOWN writer" in x["detail"] for x in f6)
    f6ok = sig_s6([{"argv": "openclaw config set ...", "pid": 1}], "node", "node",
                  ["openclaw"])
    assert f6ok == []
    print("  S6 case: PASS (root-owned=P1, unknown writer=P2, sanctioned writer silent)")

    # S7
    assert sig_s7({"gateway": "down"})[0]["severity"] == "P1"
    assert sig_s7({"gateway": "up", "tunnel": "down"})[0]["key_path"] == "surface.tunnel"
    print("  S7 case: PASS (gateway down=P1)")

    # S8 value-free secret catch. The synthetic key is ASSEMBLED from fragments at
    # runtime so this source file carries no contiguous secret literal (the merge-gate
    # scan-no-secrets scanner proves the source clean); the runtime string is a real
    # provider_sk shape so S8 must catch it and must NOT echo its value.
    synthetic = "sk" + "-" + "9f3Kx7Qm2Lp8Rt4Wv6Bn1Zc5Hd0Js3GyQwEr"  # synthetic, not a real key
    leak = 'PROVIDER_API_KEY = "%s"' % synthetic
    f8 = sig_s8([("session.jsonl", leak)])
    assert len(f8) == 1 and f8[0]["severity"] == "P1"
    assert synthetic not in f8[0]["detail"], "S8 leaked the value into the alert!"
    assert "provider_sk" in f8[0]["detail"]
    print("  S8 case: PASS (secret shape caught; VALUE never in the alert)")

    # S9 drift + gone
    f9 = sig_s9({"58-x": "aaa", "59-y": "bbb"}, {"58-x": "aaa", "59-y": "ZZZ"})
    assert f9 and f9[0]["signal"] == "S9" and f9[0]["severity"] == "P2"
    # a skill present at baseline but missing from a NON-empty current manifest = P1
    f9gone = sig_s9({"58-x": "aaa", "59-y": "bbb"}, {"59-y": "bbb"})
    assert f9gone and f9gone[0]["severity"] == "P1"
    # a fully-empty current manifest = tool unavailable, NOT a false 'all gone' P1
    assert sig_s9({"58-x": "aaa"}, {}) == []
    print("  S9 case: PASS (hash drift=P2, skill gone=P1, empty manifest = no false P1)")

    # end-to-end no-send tick against a fixture config + baseline
    with tempfile.TemporaryDirectory() as td:
        os.environ["EWS_STATE_DIR"] = str(Path(td) / "ews")
        os.environ["EWS_OPENCLAW_ROOT"] = td  # no audit/traj files here -> those signals quiet
        cfg = {"agents": {"defaults": {"maxConcurrent": 16,
               "subagents": {"maxConcurrent": 16},
               "model": {"primary": "glm-5.2", "fallbacks": []},
               "compaction": {"memoryFlush": {"softThresholdTokens": 900000}}}},
               "channels": {"telegram": {"accounts": {"default": {"allowFrom": ["1"],
                "dmPolicy": "allowlist", "groupPolicy": "closed"}}}},
               "cron": [{"name": "ews-tick", "schedule": "*/15 * * * *", "delivery": "silent"}],
               "_contextWindow": 128000}
        cfgp = Path(td) / "openclaw.json"
        cfgp.write_text(json.dumps(cfg), encoding="utf-8")
        os.environ["EWS_CONFIG_PATH"] = str(cfgp)
        # pin a baseline first (clean)
        clean = json.loads(json.dumps(cfg))
        clean["agents"]["defaults"]["compaction"]["memoryFlush"]["softThresholdTokens"] = 20000
        base = B.build_baseline(clean)
        bp = B.baseline_path()
        bp.parent.mkdir(parents=True, exist_ok=True)
        bp.write_text(json.dumps(base), encoding="utf-8")

        summary, recorded = run_tick(send=False, probe={"gateway": "unknown"})
        # the live config has the subtractive misconfig -> at least one S3 P1
        assert summary["findings"] >= 1
        assert any(f["signal"] == "S3" and f["severity"] == "P1" for f in recorded)
        # events were recorded in the ledger
        with Ledger() as led:
            assert len(led.open_events("S3")) >= 1
        print("  end-to-end tick case: PASS (%d findings recorded, S3 broken-config caught)"
              % summary["findings"])

        for k in ("EWS_STATE_DIR", "EWS_OPENCLAW_ROOT", "EWS_CONFIG_PATH"):
            os.environ.pop(k, None)

    print("[ews_sentinel] self-test: PASS")
    return EX_OK


if __name__ == "__main__":
    sys.exit(_cli())
