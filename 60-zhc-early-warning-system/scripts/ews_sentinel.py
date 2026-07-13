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


# --------------------------------------------------------------------------- #
# S3 live-usage helper - the missing half that made the 70%/85% branches dead
# code (they were only ever exercised by sig_s3's own self-test, never by a
# real tick). Zero model calls, zero network beyond an OPT-IN local-binary
# probe (see the CLI fallback below); deterministic file reads only.
# --------------------------------------------------------------------------- #

# CONFIRMED from the OpenClaw 2026.6.11 trajectory-writer source (read-only, no
# live box touched). A trajectory `model.completed` / `trace.artifacts` row carries
# its usage 3 LEVELS deep at row["data"]["usage"], = getUsageTotals(), the
# RUN-ACCUMULATED normalized usage object {input, output, cacheRead, cacheWrite,
# [reasoningTokens], total}:
#   writer  dist/selection-CVIPXpKT.js:14200-14216  recordEvent("model.completed",
#           {usage: attemptUsage, ...})  [attemptUsage = getUsageTotals(), :13848]
#   totals  dist/selection-CVIPXpKT.js:4310-4339  commitAssistantUsage() accumulates
#           usageTotals ACROSS the run; getUsageTotals() emits
#           {input, output, cacheRead, cacheWrite, [reasoningTokens], total}
#   norm    dist/usage-C67Kbb7n.js:44-64  normalizeUsage() EMITS exactly that shape
#           and only CONSUMES the raw provider aliases (input_tokens, total_tokens,
#           inputTokens, totalTokens, prompt_tokens, ...) - they are NEVER written to
#           the stream. That is why the old 2-level ("usage","input_tokens") /
#           ("usage","total_tokens") reader was DOUBLY blind: wrong depth (usage is
#           under data, not top-level) AND wrong field names (aliases never emitted).
#
# METRIC: this detector wants CONTEXT-WINDOW OCCUPANCY (how full the window is
# getting), NOT spend. Occupancy is the PROMPT / INPUT side - what is fed INTO the
# model - which OpenClaw ITSELF defines as prompt_tokens = input + cacheRead
# (dist/usage-C67Kbb7n.js:68-70, :83). We therefore sum input + cacheRead and
# DELIBERATELY exclude `output` (generation, not resident prompt) and the billed
# `total` (== input+output+cacheRead+cacheWrite - Skill 61's SPEND metric,
# loop_watchdog._usage_total, NOT occupancy). cacheWrite is excluded to match
# OpenClaw's own prompt_tokens accounting.
#
# CAVEAT (documented, never hidden): `data.usage` is RUN-ACCUMULATED, so input+
# cacheRead off the LATEST completion is an UPPER-BOUND proxy for single-turn
# occupancy on a long cached run - never an undercount, i.e. the conservative,
# fail-EARLY direction (the defect being fixed here is BLINDNESS, so warning a touch
# early is the safe side). The tight per-turn/current-context figure OpenClaw tracks
# (`contextTokens`) is persisted to the SESSION STORE, not the trajectory
# (dist/agent-runner.runtime-BriI2__w.js:2310-2377 persistSessionUsageUpdate), and is
# surfaced only by the opt-in CLI path below; the trajectory stream this detector
# tails carries `data.usage` alone.
_USAGE_PROMPT_FIELDS = ("input", "cacheRead")  # OpenClaw prompt_tokens = input + cacheRead

# Flat scalar occupancy candidates for a DIFFERENT shape than a trajectory row: the
# session-store view a CLI probe surfaces (see _context_usage_from_cli), and any
# already-flattened status dict. `contextTokens` is the session store's OWN
# current-context figure (dist/agent-runner.runtime-BriI2__w.js:2328) - the truest
# occupancy number when it is available; the rest are defensive aliases. These are
# tried ONLY after the confirmed data.usage prompt-side read misses, so a real
# trajectory row (which has no such flat field) never reaches them.
_CONTEXT_TOKEN_FIELDS = ("contextTokens", "context_tokens", "totalTokens", "promptTokens")


def _coerce_nonneg_int(value):
    """A finite, non-negative real -> int; a bool, None, or anything else -> None.
    Mirrors Skill 61 loop_watchdog._coerce_nonneg_int so the two skills share ONE
    fail-soft numeric reader convention."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value >= 0:
        return int(value)
    return None


def _prompt_side_tokens(usage):
    """Context-window OCCUPANCY off a normalized `usage` dict = the prompt/input
    side (input + cacheRead), per OpenClaw's own prompt_tokens definition. Sums the
    prompt-side buckets present; returns None when `usage` is not a dict or carries
    none of them. Fail-soft per bucket (a bool/odd value contributes nothing, never
    a crash) - the same posture as Skill 61's component-sum fallback."""
    if not isinstance(usage, dict):
        return None
    parts = [p for p in (_coerce_nonneg_int(usage.get(f)) for f in _USAGE_PROMPT_FIELDS)
             if p is not None]
    return sum(parts) if parts else None


def _extract_context_tokens(obj):
    """Best-effort CONTEXT-WINDOW occupancy (prompt-side tokens), off EITHER a raw
    trajectory ROW or a CLI/session-store status dict. Never raises; a wrong or
    absent shape returns None so the caller no-ops rather than guesses.

    Resolution order:
      (1) trajectory row -> data.usage prompt-side (input + cacheRead). This is the
          CONFIRMED real shape: usage lives 3 levels deep at row["data"]["usage"]
          (see the source-cited comment above), which is what the caller
          (_latest_trajectory_event) hands in - the FULL row, not an unwrapped event.
      (2) a flat occupancy scalar (contextTokens / ...) - the session-store view a
          CLI probe surfaces.
      (3) a TOP-LEVEL `usage` object's prompt-side - an already-unwrapped event or an
          odd status dict; last resort, so a real row (which has no top-level usage)
          never reaches it."""
    if not isinstance(obj, dict):
        return None
    data = obj.get("data")
    if isinstance(data, dict):
        v = _prompt_side_tokens(data.get("usage"))
        if v is not None:
            return v
    for key in _CONTEXT_TOKEN_FIELDS:
        v = _coerce_nonneg_int(obj.get(key))
        if v is not None:
            return v
    return _prompt_side_tokens(obj.get("usage"))


def _latest_trajectory_event(max_bytes=200_000):
    """The LAST JSON row of the box's newest *.trajectory.jsonl (by mtime), the
    same ground-truth stream S2 tails via _read_trajectory_events - but this is
    a bounded-tail PEEK, not a tick-offset consumer: it must never advance the
    ledger offsets S2 owns, so it re-reads the tail of the file directly rather
    than sharing S2's cursor. Returns None when no session file exists yet."""
    base = openclaw_root() / "agents"
    files = glob.glob(str(base / "*" / "sessions" / "*.trajectory.jsonl"))
    if not files:
        return None

    def _mtime(f):
        try:
            return os.path.getmtime(f)
        except OSError:
            return -1.0

    newest = max(files, key=_mtime)
    try:
        size = os.path.getsize(newest)
    except OSError:
        return None
    try:
        with open(newest, "r", encoding="utf-8", errors="replace") as fh:
            if size > max_bytes:
                fh.seek(size - max_bytes)
                fh.readline()  # drop a possibly-truncated partial first line
            tail = fh.read(max_bytes)
    except OSError:
        return None
    last = None
    for line in tail.splitlines():
        line = line.strip()
        if line:
            last = line
    if not last:
        return None
    try:
        return json.loads(last)
    except ValueError:
        return None


def _context_usage_from_cli():
    """Opt-in fallback probe that shells `openclaw session status --json`. VERDICT
    (verified read-only against the installed OpenClaw 2026.6.11 dist, no live box):
    there is NO `session status` subcommand on this build - the CLI command group is
    `sessions` (list-only: `sessions` / `sessions list` / `sessions tail`), and
    `openclaw sessions --json` is the read-only surface that carries the session
    store's per-session `contextTokens` / `totalTokens` (the tight occupancy figure
    the trajectory stream does not emit; see _extract_context_tokens's source note).
    So THIS exact invocation is UNVERIFIED for 2026.6.11 and stays OFF by default
    (requires the explicit EWS_CONTEXT_CLI_FALLBACK=1) - a separate, still-unverified
    shape, NOT the confirmed trajectory-reader defect. The extractor's flat-field
    reader IS aligned to the real session-store field names (`contextTokens` first),
    so a confirmed status shape parses correctly; wiring the exact active-session
    command (`sessions --json` returns a LIST, needing active-session resolution) is
    deferred to canary burn-in rather than guessed here. Never a model call; the only
    egress is the local binary, the same injectable seam ews_alert.py's gateway sender
    uses. Any failure (binary missing, unknown subcommand -> non-zero exit,
    unparseable output) is a silent None, never a crash and never a guessed number."""
    if os.environ.get("EWS_CONTEXT_CLI_FALLBACK", "") != "1":
        return None
    openclaw = os.environ.get("OPENCLAW_BIN")
    if not openclaw:
        from shutil import which
        openclaw = which("openclaw")
    if not openclaw:
        return None
    try:
        proc = subprocess.run([openclaw, "session", "status", "--json"],
                              capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        return None
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _context_usage(config, led):
    """Return (usage_pct, context_window) for the box's ACTIVE session, or
    (None, None) when it cannot be determined. Deterministic: reads the newest
    session *.trajectory.jsonl (the same ground-truth stream S2 already tails
    via _read_trajectory_events) and takes the LATEST event's prompt-side
    occupancy (data.usage input + cacheRead, CONFIRMED from the OpenClaw
    trajectory-writer source - see _extract_context_tokens); ceiling =
    contextWindow minus SUBTRACTIVE softThresholdTokens, reusing
    ews_common.subtractive_broken's own ceiling arithmetic so S3's two halves
    (broken-config, running-low) never compute the ceiling two different ways.
    `led` is accepted for signature parity with the spec and as a hook for a
    future active-session lookup; the confirmed data.usage prompt-side read does
    not require ledger state to resolve.
    A missing signal returns (None, None) - never 0%, never a guess - so a box
    with no trajectory data yet simply gets no running-low finding, exactly
    today's (dead-code) behavior."""
    cw = C.context_window_hint(config)
    tokens = None
    ev = _latest_trajectory_event()
    if ev is not None:
        tokens = _extract_context_tokens(ev)
    if tokens is None:
        cli = _context_usage_from_cli()
        if isinstance(cli, dict):
            tokens = _extract_context_tokens(cli)
            if cw is None:
                for key in ("contextWindow", "context_window"):
                    v = cli.get(key)
                    if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
                        cw = int(v)
                        break
    if tokens is None or cw is None:
        return None, None
    broken, ceiling, _reason = C.subtractive_broken(config, cw)
    if broken or ceiling is None or ceiling <= 0:
        # the broken-config P1 already covers this box; never also guess a pct
        return None, None
    pct = int(round((tokens / ceiling) * 100))
    return max(0, pct), cw


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
            u_pct, ctx_win = _context_usage(config, led)
            findings += sig_s3(config, thresholds, usage_pct=u_pct, context_window=ctx_win)

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

    # _extract_context_tokens: the token reader at the heart of S3's running-low
    # path. Proves the CONFIRMED 3-level data.usage prompt-side read (input +
    # cacheRead), a fail-old/pass-new regression against the pre-fix reader, the flat
    # session-store shape, and fail-soft.
    real_row = {"type": "model.completed", "sessionId": "sess-x", "modelId": "glm-5.2",
                "data": {"usage": {"input": 82880, "output": 50000, "cacheRead": 10000,
                                   "cacheWrite": 5000, "total": 147880}}}
    # PASS-NEW: occupancy = input(82880) + cacheRead(10000) = 92880 - NOT output,
    # NOT the billed total(147880). The exact number a spend/total read gets wrong.
    assert _extract_context_tokens(real_row) == 92880, _extract_context_tokens(real_row)

    # FAIL-OLD: the pre-fix reader was a 2-level obj["usage"][...] lookup on raw
    # provider aliases (input_tokens/total_tokens) the writer NEVER emits -> it is
    # blind (None) on this REAL row. Replayed inline so the regression is self-proving.
    def _old_extract(obj):
        old_flat = ("contextTokens", "cumulativeContextTokens", "contextUsedTokens",
                    "totalTokens", "cumulativeInputTokens", "inputTokens", "promptTokens")
        old_nested = (("usage", "input_tokens"), ("usage", "total_tokens"),
                      ("usage", "context_tokens"), ("tokenUsage", "total"))
        if not isinstance(obj, dict):
            return None
        for key in old_flat:
            v = obj.get(key)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0:
                return int(v)
        for outer, inner in old_nested:
            sub = obj.get(outer)
            if isinstance(sub, dict):
                v = sub.get(inner)
                if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0:
                    return int(v)
        return None
    assert _old_extract(real_row) is None, "old 2-level/alias reader must be blind on a real row"

    # flat session-store / CLI shape (the opt-in `sessions --json` view): contextTokens
    assert _extract_context_tokens({"contextTokens": 54000}) == 54000
    # top-level usage (already-unwrapped event) -> prompt-side last resort (output ignored)
    assert _extract_context_tokens({"usage": {"input": 40000, "cacheRead": 2000,
                                              "output": 9}}) == 42000
    # fail-soft: non-dict, empty, bool/negative buckets -> None, never a crash
    assert _extract_context_tokens(None) is None
    assert _extract_context_tokens({"data": {"usage": {}}}) is None
    assert _extract_context_tokens({"data": {"usage": {"input": True,
                                                       "cacheRead": -5}}}) is None
    print("  _extract_context_tokens case: PASS (real data.usage input+cacheRead=92880; "
          "old 2-level/alias reader blind=None; flat + fail-soft)")

    # _context_usage: the live-usage computation that feeds S3's running-low
    # branches (D1/D2 fix - these branches were dead code before this function).
    # (tempfile was already imported above, in the S4 case.)
    with tempfile.TemporaryDirectory() as ctd:
        os.environ["EWS_OPENCLAW_ROOT"] = ctd
        os.environ.pop("EWS_CONTEXT_CLI_FALLBACK", None)
        cfg_cw = {"agents": {"defaults": {"compaction": {"memoryFlush":
                  {"softThresholdTokens": 20000}}}}, "_contextWindow": 128000}

        # (a) no trajectory file yet -> clean (None, None), never a guess
        assert _context_usage(cfg_cw, None) == (None, None)

        # (b) a REAL model.completed row -> data.usage prompt-side occupancy
        # (input + cacheRead), 3 levels deep. ceiling = 128000 - 20000 = 108000;
        # input(82880)+cacheRead(10000)=92880 -> 92880/108000 = 0.86 -> 86%. output
        # (50000) and the billed total(147880 -> 137%) are DELIBERATELY not what
        # occupancy uses; a `total`/spend read here would compute the wrong pct.
        sess_dir = Path(ctd) / "agents" / "main" / "sessions"
        sess_dir.mkdir(parents=True, exist_ok=True)
        traj = sess_dir / "sess-example.trajectory.jsonl"
        traj.write_text(
            json.dumps({"ts": "2026-07-10T12:00:00Z", "type": "model.completed",
                       "sessionId": "sess-example", "modelId": "glm-5.2",
                       "provider": "openrouter",
                       "data": {"usage": {"input": 30000, "output": 8000,
                                          "cacheRead": 10000, "cacheWrite": 0,
                                          "total": 48000}}}) + "\n" +
            json.dumps({"ts": "2026-07-10T12:05:00Z", "type": "model.completed",
                       "sessionId": "sess-example", "modelId": "glm-5.2",
                       "provider": "openrouter",
                       "data": {"usage": {"input": 82880, "output": 50000,
                                          "cacheRead": 10000, "cacheWrite": 5000,
                                          "total": 147880}}}) + "\n",
            encoding="utf-8")
        pct, cw = _context_usage(cfg_cw, None)
        assert pct == 86 and cw == 128000, (pct, cw)
        print("  _context_usage case: PASS (REAL data.usage prompt-side -> 86% of 128000)")

        # (c) ceiling broken (threshold >= window) -> never guess a pct even
        # though tokens are present; the broken-config P1 already covers it
        cfg_broken = {"agents": {"defaults": {"compaction": {"memoryFlush":
                      {"softThresholdTokens": 900000}}}}, "_contextWindow": 128000}
        assert _context_usage(cfg_broken, None) == (None, None)
        print("  _context_usage case: PASS (broken ceiling never guesses a pct)")

        # (d) CLI fallback OFF by default -> even with no trajectory data, it
        # never shells out (proven by NOT setting OPENCLAW_BIN to anything that
        # would answer, and still getting a clean None instead of a hang/crash)
        empty_dir = Path(ctd) / "empty"
        empty_dir.mkdir(exist_ok=True)
        os.environ["EWS_OPENCLAW_ROOT"] = str(empty_dir)
        assert _context_usage(cfg_cw, None) == (None, None)
        print("  _context_usage case: PASS (CLI fallback OFF by default = no shell-out)")

        # (e) CLI fallback ON (explicit opt-in) + a fake local binary -> proves
        # the fallback path itself works once verified/enabled, without ever
        # touching a real openclaw binary
        fake_bin = Path(ctd) / "fake-openclaw.sh"
        fake_bin.write_text(
            "#!/bin/sh\n"
            'echo \'{"contextTokens": 54000, "contextWindow": 128000}\'\n',
            encoding="utf-8")
        fake_bin.chmod(0o755)
        os.environ["EWS_CONTEXT_CLI_FALLBACK"] = "1"
        os.environ["OPENCLAW_BIN"] = str(fake_bin)
        cfg_no_hint = {"agents": {"defaults": {"compaction": {"memoryFlush":
                       {"softThresholdTokens": 20000}}}}}  # no _contextWindow hint
        pct_cli, cw_cli = _context_usage(cfg_no_hint, None)
        # ceiling = 128000 - 20000 = 108000; 54000/108000 = 0.50 -> 50%
        assert pct_cli == 50 and cw_cli == 128000, (pct_cli, cw_cli)
        print("  _context_usage case: PASS (opt-in CLI fallback resolves tokens + window)")

        for k in ("EWS_CONTEXT_CLI_FALLBACK", "OPENCLAW_BIN"):
            os.environ.pop(k, None)
    os.environ.pop("EWS_OPENCLAW_ROOT", None)

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
