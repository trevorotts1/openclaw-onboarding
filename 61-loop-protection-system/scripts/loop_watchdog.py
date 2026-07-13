#!/usr/bin/env python3
# =============================================================================
# SKILL 61 - LOOP PROTECTION SYSTEM :: loop_watchdog.py
# The per-box watchdog tick (spec Section 6.1). ONE tick, default every 15 min,
# jittered, host-level, OUTSIDE every OpenClaw session (the Box B law): it must
# survive the very wedges it treats (it does not depend on the gateway, the cron
# engine, or the agent loop - LP-B5 kills all three).
#
# ONE TICK:
#   collect evidence (D1-D4 inputs) ->
#   run detectors D1-D4 ->
#   read NEW Skill 60 ledger events (read-only; best-effort; 60's ledger keeps its
#      single writer, we write only OUR own) ->
#   for each finding: record -> route by fix tier (6.3) -> DRY_RUN plans / armed
#      Tier-1 applies -> verify -> ledger -> alert/escalate per Section 7
#
# DETERMINISTIC PYTHON, ZERO MODEL CALLS, no long-lived daemon, tick CPU < 5s.
# DRY_RUN (armed=false) is the DEFAULT for the first 7 days (observe-only burn-in).
# tick() takes an INJECTED evidence dict so the whole pipeline is testable offline;
# collect_evidence() is the best-effort box-reading layer (never fatal on a probe
# miss: a probe failure is DATA, never a crash - loop-detector.sh's exit-0-always
# law). The collectors read the box's OWN local streams, all verified against a
# real OpenClaw v2026.x box:
#   D1  collect_units()    pm2 jlist (filtered to name/status/pid/restarts ONLY)
#   D2  collect_windows()  trajectory `model.completed` cumulative usage -> hourly
#                          paid/local token windows + human-initiated-session counts
#   D3  collect_runs()     offset-tracked NEW-bytes trajectory slice ->
#                          (outcome class + tool sequence + target) signatures,
#                          for SUCCESSFUL turns ("OK") as well as failures
#   D4  collect_crons()    `openclaw cron list --json` + observed-fire counting;
#       collect_wedge()    demand-without-progress ticks + orphan :port listener
#                          vs the declared supervisor in the restart-handoff file
# The env seam LOOP_NO_PROBES=1 disables every subprocess probe (hermetic tests).
# =============================================================================
"""loop_watchdog.py - the per-box Loop Protection watchdog tick."""

from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import loop_common as C  # noqa: E402
import loop_detectors as D  # noqa: E402
import loop_killcards as KC  # noqa: E402
import loop_escalate as ESC  # noqa: E402
from loop_ledger import Ledger, openclaw_root  # noqa: E402


def run_detectors(evidence, thresholds, signatures):
    """Run D1-D4 over injected/collected evidence. Returns a flat findings list."""
    findings = []
    findings += D.d1_restart_velocity(evidence.get("units", []), thresholds,
                                      warn_streaks=evidence.get("warn_streaks", {}))
    findings += D.d2_token_burn_rate(evidence.get("windows", []), thresholds, signatures)
    findings += D.d3_identical_signature(evidence.get("runs", []), thresholds)
    findings += D.d4_timer_refire(evidence.get("crons", []), evidence.get("wedge", {}), thresholds)
    return findings


def _dedup_ok(led, finding, window_hours):
    """One alert per (class, box/unit) per window. Records the digest when clear."""
    key = finding.get("dedup_key") or ("%s|%s" % (finding["loop_class"], finding.get("unit")))
    if led.recent_digest(key, window_hours):
        return False
    led.record_digest("alert", key, payload=finding.get("severity"))
    return True


def tick(evidence, led, armed=None, escalate_transport=None, box="box"):
    """One deterministic tick over INJECTED evidence. Returns a summary dict:
      {armed, findings, applied, planned, escalated, alerts}
    Zero model calls. With armed False (DRY_RUN) NOTHING is mutated outside OUR ledger
    (findings are still recorded - observing is the whole point of burn-in)."""
    thresholds = C.load_skill_config("thresholds.json")
    signatures = C.load_signatures()
    if armed is None:
        armed = led.is_armed()
    window_hours = thresholds["alert"]["dedup_window_hours"]

    summary = {"armed": armed, "findings": 0, "applied": 0, "planned": 0,
               "escalated": 0, "alerts": 0, "by_class": {}}

    findings = run_detectors(evidence, thresholds, signatures)
    for f in findings:
        fid = led.record_finding(f["loop_class"], f["severity"], unit=f.get("unit"),
                                 evidence_path=f.get("evidence_path"),
                                 detail=f.get("detail"), tier=f.get("tier"),
                                 dedup_key=f.get("dedup_key"))
        f["finding_id"] = fid
        summary["findings"] += 1
        summary["by_class"][f["loop_class"]] = summary["by_class"].get(f["loop_class"], 0) + 1

        kc = KC.plan({"loop_class": f["loop_class"], "finding_id": fid}, box=box)
        kc["unit"] = f.get("unit")
        # Route by tier. Tier-1 auto-applies ONLY when armed; else it plans. Tier 2/3
        # never auto-apply. The ONE safe in-tick mechanical act is parking a crash-
        # looping PROCESS unit via the process breaker (LF-6: STOP + park, visible-red,
        # never respawns) - it touches NO client config. Only a CONFIRMED loop (a P1 D1
        # finding, which is exactly a process-breaker trip: >=10/tick or >=40/day) parks
        # in-tick; a WARN plans only. Every config-touching kill card (LF-1/2/4/5/7)
        # stays plan-only in the unattended tick and is applied SOLELY by an explicit
        # operator `fix`, so the tick never touches client config unattended. DRY_RUN =>
        # LF-6 plans (mutates nothing - the D-DRYRUN invariant); armed => LF-6 trips the
        # process breaker + parks the unit. Escalation stays an ADD-ON (the P1 operator
        # alert below, plus Tier-3 / healer-breaker escalation) - never a substitute for
        # the park (the old empty-executors bug ESCALATED instead of parking).
        in_tick_executors = {}
        if f.get("severity") == "P1" and kc.get("fix_class") == "LF-6" and f.get("unit"):
            _park_unit = f["unit"]
            in_tick_executors["LF-6"] = (
                lambda dry_run, _u=_park_unit: KC.lf6_park_process(_u, led, dry_run=dry_run))
        result = KC.apply(kc, led, armed=armed, executors=in_tick_executors,
                          verify_failed_last=False)
        if result["status"] == "applied":
            summary["applied"] += 1
            led.record_fix(fid, kc.get("fix_class"), unit=f.get("unit"),
                           what=result.get("detail"), verify_outcome="applied",
                           revert_cmd=kc.get("revert_cmd"), dry_run=False)
            led.set_finding_state(fid, "fixed")
        else:
            summary["planned"] += 1

        # escalate Tier-3 and any healer-breaker escalation via Rescue Rangers
        if result.get("escalate"):
            payload = ESC.build_payload(
                box=box, loop_class=f["loop_class"], finding=f.get("detail"),
                evidence_path=f.get("evidence_path"),
                proposed_fix=kc.get("what"), why=result.get("detail"),
                action_needed="operator decision / approve fix",
                finding_id=fid, killcard_cmd=kc.get("killcard_cmd"),
                revert_cmd=kc.get("revert_cmd"))
            ESC.send(payload, transport=escalate_transport)
            led.set_finding_state(fid, "escalated")
            summary["escalated"] += 1

        # operator alert (deduped). P1 bypasses batching but not dedup.
        if f["severity"] in ("P1", "P2") and _dedup_ok(led, f, window_hours):
            summary["alerts"] += 1

    return summary


# --------------------------------------------------------------------------- #
# collect_*() - the best-effort box-reading layer (never fatal)
# ---------------------------------------------------------------------------
# THE STUB THAT MISSED THE STAR INCIDENT LIVED HERE: collect_evidence() used to
# return {"windows": [], "runs": [], "crons": [], "wedge": {}} - so even a fully
# armed watchdog handed D2/D3/D4 EMPTY evidence on a real box (fix design
# 2026-07-13 SS4, finding 2: "the single most important repo finding"). Every
# collector below reads a REAL local stream, verified field-by-field against a
# live box, and fails SOFT: a missing/unreadable source contributes no findings
# (never a crash, never a guess). No secret VALUE is ever read, stored, or
# printed - these streams carry counts, ids, model ids, tool NAMES, and
# timestamps only, and the pm2 path stays behind filter_pm2_record.
# --------------------------------------------------------------------------- #
_PROBES_OFF_ENV = "LOOP_NO_PROBES"  # =1 disables every subprocess probe (tests)

# session.started `data.trigger` values that count as HUMAN-initiated (verified
# live values: user / cron / heartbeat / memory). Only 'user' is a human.
_HUMAN_TRIGGERS = ("user",)

# candidate last-run marker fields on a cron job's `state` block (verified live:
# state.lastRunAtMs; the rest are defensive candidates, tried in order).
_CRON_LAST_RUN_FIELDS = ("lastRunAtMs", "lastRunAt", "lastFireAtMs", "lastRun")


def _probes_off():
    return os.environ.get(_PROBES_OFF_ENV, "") == "1"


def collect_units():
    """Best-effort pm2 jlist -> filtered units (name/status/pid/restarts ONLY). Returns
    [] on any miss (no pm2, not JSON, no git). NEVER dumps env. A probe miss is DATA."""
    if _probes_off():
        return []
    try:
        out = subprocess.run(["pm2", "jlist"], capture_output=True, text=True, timeout=5)
        recs = json.loads(out.stdout or "[]")
    except Exception:  # noqa: BLE001 - probe failure is data, never a crash
        return []
    units = []
    for rec in recs if isinstance(recs, list) else []:
        f = C.filter_pm2_record(rec)
        if f.get("name"):
            f["delta"] = f["restarts"]  # first-seen delta = current count; ledger refines
            units.append(f)
    return units


def _parse_ts(s):
    """ISO-8601 -> aware UTC datetime, or None. Naive stamps are treated as UTC."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _traj_files(max_files=24, max_age_hours=26.0):
    """Newest trajectory files (by mtime, bounded) under <openclaw_root>/agents/
    */sessions/*.trajectory.jsonl - the same ground-truth stream Skill 60's S2
    tails. Bounded so the tick stays CPU-cheap on boxes with thousands of old
    session files. [] when the stream does not exist (probe miss = data)."""
    try:
        files = glob.glob(str(openclaw_root() / "agents" / "*" / "sessions"
                              / "*.trajectory.jsonl"))
    except OSError:
        return []
    import time
    now = time.time()
    scored = []
    for f in files:
        try:
            mt = os.path.getmtime(f)
        except OSError:
            continue
        if now - mt <= max_age_hours * 3600.0:
            scored.append((mt, f))
    scored.sort(reverse=True)
    return [f for _, f in scored[:max_files]]


def _iter_jsonl_tail(path, max_bytes):
    """Parsed JSON rows from the last max_bytes of a JSONL file (bounded tail
    PEEK - advances no offset). A truncated first line is dropped; a bad line is
    skipped, never fatal."""
    try:
        size = os.path.getsize(path)
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            if size > max_bytes:
                fh.seek(size - max_bytes)
                fh.readline()  # drop the (possibly partial) first line
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except ValueError:
                    continue
    except OSError:
        return


def _usage_total(data):
    """`data.usage.total` off a trajectory event, or None. Never a guess."""
    usage = data.get("usage") if isinstance(data, dict) else None
    total = usage.get("total") if isinstance(usage, dict) else None
    if isinstance(total, (int, float)) and not isinstance(total, bool) and total >= 0:
        return int(total)
    return None


def _paid_event(row, sig):
    """Paid-tier classification of one trajectory event via signatures data
    (provider slug + model-id markers; e.g. a :cloud suffix)."""
    mid = "%s/%s" % (row.get("provider") or "", row.get("modelId") or "")
    return C.model_id_flags(mid, sig)["paid"]


def collect_windows(now=None, max_files=24, max_bytes=750_000):
    """D2 evidence: hourly token windows for the trailing 24h, oldest first, from
    the trajectory stream. Token source is `model.completed` data.usage.total,
    which is CUMULATIVE PER RUN (verified live: successive completions in one run
    carry increasing totals), so each completion contributes its DELTA - this is
    what makes a burn visible MID-RUN, while the looping run is still alive (the
    Star furnace burned ~466 completions inside ONE run; a run-end-only source
    sees nothing until it is over). `trace.artifacts` run totals back-fill only
    runs whose completions carried no usage (older schema). initiated_sessions
    counts `session.started` rows with a HUMAN trigger ('user'), so cron/
    heartbeat activity stays idle-classified, per the D2 contract. Extra key
    `completions` (per-window completion count) is carried for the D5
    completion-rate detector to consume when it lands (fix design SS4) - D2
    ignores it. Returns [] when no trajectory stream exists."""
    files = _traj_files(max_files=max_files)
    if not files:
        return []
    now = now or datetime.now(timezone.utc)
    first_hour = (now - timedelta(hours=23)).replace(minute=0, second=0, microsecond=0)
    sig = C.load_signatures()
    zero = {"paid": 0, "local": 0, "initiated": 0, "completions": 0}
    buckets = {}
    prev_total = {}      # runId -> last cumulative usage.total seen
    counted_runs = set()  # runIds with >=1 usage-bearing completion
    artifact_rows = []   # (hour, paid?, total, runId) fallback candidates
    for f in files:
        for row in _iter_jsonl_tail(f, max_bytes):
            rtype = row.get("type")
            if rtype not in ("session.started", "model.completed", "trace.artifacts"):
                continue
            ts = _parse_ts(row.get("ts"))
            if ts is None or ts < first_hour:
                continue
            hour = ts.replace(minute=0, second=0, microsecond=0)
            b = buckets.setdefault(hour, dict(zero))
            data = row.get("data") if isinstance(row.get("data"), dict) else {}
            if rtype == "session.started":
                if str(data.get("trigger") or "") in _HUMAN_TRIGGERS:
                    b["initiated"] += 1
            elif rtype == "model.completed":
                b["completions"] += 1
                total = _usage_total(data)
                if total is not None:
                    rid = row.get("runId") or f
                    prev = prev_total.get(rid)
                    # cumulative-per-run: charge the delta; a decrease = a fresh
                    # accumulation baseline (compaction/branch), charge the new total
                    delta = total - prev if (prev is not None and total >= prev) else total
                    prev_total[rid] = total
                    counted_runs.add(rid)
                    b["paid" if _paid_event(row, sig) else "local"] += max(0, delta)
            else:  # trace.artifacts
                total = _usage_total(data)
                if total:
                    artifact_rows.append((hour, _paid_event(row, sig), total,
                                          row.get("runId") or f))
    for hour, paid, total, rid in artifact_rows:
        if rid in counted_runs:
            continue  # already charged via its completions - never double-count
        b = buckets.setdefault(hour, dict(zero))
        b["paid" if paid else "local"] += total
    out = []
    idle_streak = 0
    hour = first_hour
    while hour <= now:
        b = buckets.get(hour, zero)
        idle = b["initiated"] == 0
        idle_streak = idle_streak + 1 if idle else 0
        nxt = hour + timedelta(hours=1)
        out.append({"label": "%s-%sZ" % (hour.strftime("%Y-%m-%d %H:00"),
                                         nxt.strftime("%H:00")),
                    "paid_tokens": b["paid"], "local_tokens": b["local"],
                    "initiated_sessions": b["initiated"],
                    "idle_consecutive": idle_streak if idle else 0,
                    "completions": b["completions"]})
        hour = nxt
    return out


def _read_new_trajectory_rows(led=None, max_files=40, max_bytes=2_000_000):
    """The NEW-bytes-since-last-tick trajectory slice (the D3 slice pattern;
    ledger offsets under 'loop-traj:<path>'). Returns (rows, stats) where stats
    counts demand ('starts': prompt.submitted/session.started) vs progress
    ('completions': model.completed/trace.artifacts/session.ended) for the D4
    wedge probe. Offsets only ever land on line boundaries. With led=None (the
    read-only audit path) this PEEKS at the bounded tail and advances NOTHING.
    First sight of a large file starts near its tail - history is Skill 60's
    job, the watchdog's job is the last slice."""
    rows = []
    stats = {"starts": 0, "completions": 0}
    for f in _traj_files(max_files=max_files, max_age_hours=48.0):
        key = "loop-traj:%s" % f
        try:
            size = os.path.getsize(f)
        except OSError:
            continue
        fresh_cut = False
        off = led.get_offset(key) if led is not None else 0
        if off > size:
            off = 0  # rotated/truncated: start over
        if off == 0 and size > max_bytes:
            off = size - max_bytes  # not a line boundary: drop the first line below
            fresh_cut = True
        try:
            with open(f, "rb") as fh:
                fh.seek(off)
                chunk = fh.read(max_bytes)
        except OSError:
            continue
        end = chunk.rfind(b"\n")
        if end < 0:
            continue  # no complete line yet; do not advance, wait for more bytes
        lines = chunk[:end].split(b"\n")
        if fresh_cut and lines:
            lines = lines[1:]  # partial first line from a mid-file cut
        new_off = off + end + 1
        for raw in lines:
            raw = raw.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                continue
            if not isinstance(row, dict):
                continue
            rtype = row.get("type")
            if rtype in ("prompt.submitted", "session.started"):
                stats["starts"] += 1
            elif rtype in ("model.completed", "trace.artifacts", "session.ended"):
                stats["completions"] += 1
            row["_file"] = f
            rows.append(row)
        if led is not None:
            led.set_offset(key, new_off)
    return rows, stats


def _outcome_class_of(data):
    """The outcome class of one finished run, for the D3 signature. SUCCESSFUL
    runs return "OK" - repeated identical successful turns are a loop face too
    (the Star correction wave was 'successful' sends end to end; D3 hashing
    failures only is exactly why it stayed silent). No message content and no
    secret enters the class: structural flags and enum values only."""
    if not isinstance(data, dict):
        return "OK"
    if data.get("timedOutDuringCompaction"):
        return "CompactionTimeout"
    if data.get("timedOut"):
        return "TimedOut"
    if data.get("idleTimedOut"):
        return "IdleTimeout"
    if data.get("aborted") or data.get("externalAbort"):
        return "Aborted"
    status = str(data.get("finalStatus") or data.get("status") or "").lower()
    if status in ("", "success", "ok", "completed"):
        return "OK"
    src = data.get("promptErrorSource")
    return "Error:%s" % src if src else "Error"


def collect_runs(rows):
    """D3 evidence from the new-bytes slice: one entry per finished run, BOTH
    failures and successes. Source of truth is `trace.artifacts` (per-run
    summary: outcome flags + ordered tool NAMES in data.toolMetas); a run that
    ended without artifacts but with an erroring `session.ended` is synthesized
    from that. Entries are ordered per unit (unit-contiguous, then time) so
    interleaved sessions never break a same-unit streak - D3 counts CONSECUTIVE
    identical signatures. Tool NAMES only; arguments/content never collected."""
    runs = []
    ended = {}
    have_artifacts = set()
    for row in rows:
        rtype = row.get("type")
        if rtype not in ("trace.artifacts", "session.ended"):
            continue
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        unit = "session:%s" % (row.get("sessionKey") or row.get("sessionId") or "unknown")
        target = str(row.get("sessionKey") or row.get("sessionId") or "unknown")
        if rtype == "trace.artifacts":
            metas = data.get("toolMetas") if isinstance(data.get("toolMetas"), list) else []
            seq = [str(m.get("toolName")) for m in metas
                   if isinstance(m, dict) and m.get("toolName")]
            runs.append({"unit": unit, "error_class": _outcome_class_of(data),
                         "tool_sequence": seq, "target": target,
                         "_ts": str(row.get("ts") or ""), "_seq": row.get("seq") or 0})
            have_artifacts.add(row.get("runId"))
        else:
            ended[row.get("runId")] = (unit, target, data, str(row.get("ts") or ""),
                                       row.get("seq") or 0)
    for rid, (unit, target, data, ts, seq_no) in ended.items():
        if rid in have_artifacts:
            continue
        klass = _outcome_class_of(data)
        if klass == "OK":
            continue  # a clean end with no artifacts row carries no signature
        runs.append({"unit": unit, "error_class": klass, "tool_sequence": [],
                     "target": target, "_ts": ts, "_seq": seq_no})
    runs.sort(key=lambda r: (r["unit"], r["_ts"], r["_seq"]))
    for r in runs:
        r.pop("_ts", None)
        r.pop("_seq", None)
    return runs


def _cron_jobs_via_cli(timeout=15):
    """Best-effort `openclaw cron list --json` -> jobs list. [] on ANY miss (no
    binary, non-zero exit, bad JSON) - a probe miss is DATA. Read-only command;
    output shape verified against a saved gateway cron-list capture."""
    if _probes_off():
        return []
    from shutil import which
    binpath = os.environ.get("OPENCLAW_BIN") or which("openclaw")
    if not binpath:
        return []
    try:
        proc = subprocess.run([binpath, "cron", "list", "--json"],
                              capture_output=True, text=True, timeout=timeout,
                              check=False)
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        return []
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        return []
    jobs = data.get("jobs") if isinstance(data, dict) else data
    return jobs if isinstance(jobs, list) else []


def collect_crons(led=None, jobs=None, now=None):
    """D4 cron evidence: {name, declared_schedule, actual_fires_per_day, announce}
    per enabled recurring job. Fire counting is OBSERVED, not guessed: each tick
    the job's last-run marker (state.lastRunAtMs) is compared with the previous
    tick's (persisted in ledger meta 'd4_cron_fires', trailing 24h) and each
    transition counts one fire - a strict LOWER BOUND at the 15-minute cadence
    (max ~96 observations/day), which still catches any @daily job firing every
    few minutes. Until a fire has been observed actual_fires_per_day is None and
    D4's over-fire branch stays silent (never a false P1 on first tick). With
    led=None nothing is persisted. `jobs` is injectable for offline tests."""
    if jobs is None:
        jobs = _cron_jobs_via_cli()
    if not jobs:
        return []
    now = now or datetime.now(timezone.utc)
    hist = {}
    if led is not None:
        try:
            hist = json.loads(led.get_meta("d4_cron_fires", "{}") or "{}")
        except (ValueError, TypeError):
            hist = {}
        if not isinstance(hist, dict):
            hist = {}
    cutoff = (now - timedelta(hours=24)).isoformat()
    out = []
    for j in jobs:
        if not isinstance(j, dict) or j.get("enabled") is False:
            continue
        sched = j.get("schedule") if isinstance(j.get("schedule"), dict) else {}
        kind = str(sched.get("kind") or "")
        if kind == "at":
            continue  # one-shot: no cadence to over-fire
        declared = sched.get("expr")
        if not declared and isinstance(sched.get("everyMs"), (int, float)):
            declared = "%ds" % max(1, int(sched["everyMs"] / 1000))
        name = str(j.get("name") or j.get("id") or "<cron>")
        key = str(j.get("id") or name)
        state = j.get("state") if isinstance(j.get("state"), dict) else {}
        marker = None
        for fld in _CRON_LAST_RUN_FIELDS:
            if state.get(fld) is not None:
                marker = str(state[fld])
                break
        rec = hist.get(key) if isinstance(hist.get(key), dict) else {}
        fires = [t for t in rec.get("fires", []) if isinstance(t, str) and t >= cutoff]
        if marker is not None and rec.get("marker") is not None \
                and marker != rec.get("marker"):
            fires.append(now.replace(microsecond=0).isoformat())
        hist[key] = {"marker": marker if marker is not None else rec.get("marker"),
                     "fires": fires}
        delivery = j.get("delivery") if isinstance(j.get("delivery"), dict) else {}
        out.append({"name": name, "declared_schedule": declared,
                    "actual_fires_per_day": len(fires) if fires else None,
                    "announce": delivery.get("mode") == "announce"})
    if led is not None:
        led.set_meta("d4_cron_fires", json.dumps(hist, sort_keys=True))
    return out


def _proc_up(pattern):
    """pgrep-based process presence: 'up' / 'down' / 'unknown' (a probe we cannot
    run is 'unknown', never a guessed 'down' - Skill 60's conservative probe law)."""
    if _probes_off():
        return "unknown"
    try:
        r = subprocess.run(["pgrep", "-f", pattern], capture_output=True,
                           text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            return "up"
        if r.returncode == 1:
            return "down"
    except (OSError, subprocess.SubprocessError):
        pass
    return "unknown"


def _listener_pid_on(port):
    """First pid LISTENing on TCP :port via `lsof -t`, or None on any miss."""
    if _probes_off():
        return None
    try:
        r = subprocess.run(["lsof", "-nP", "-t", "-iTCP:%d" % int(port),
                            "-sTCP:LISTEN"], capture_output=True, text=True,
                           timeout=10)
        pids = [int(x) for x in r.stdout.split() if x.strip().isdigit()]
        return pids[0] if pids else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _read_handoff():
    """The gateway supervisor restart-handoff marker (<openclaw_root>/
    gateway-supervisor-restart-handoff.json; verified live keys include pid,
    createdAt, expiresAt). None when absent/unreadable. Structural fields only."""
    p = openclaw_root() / "gateway-supervisor-restart-handoff.json"
    try:
        if not p.is_file():
            return None
        h = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(h, dict):
            h["_mtime"] = p.stat().st_mtime
            return h
    except (OSError, ValueError):
        pass
    return None


def _handoff_epoch(value):
    """createdAt/expiresAt -> aware datetime; accepts ISO strings or epoch ms."""
    if isinstance(value, str):
        return _parse_ts(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        try:
            return datetime.fromtimestamp(float(value) / 1000.0, timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    return None


def collect_wedge(led=None, slice_stats=None, gateway_up=None,
                  handoff=C.MISSING, listener_pid=C.MISSING):
    """D4 wedge evidence. Two probes, both fail-soft:

    (1) hung-but-alive: the no-progress counter increments ONLY when the slice
        shows DEMAND (prompt.submitted / session.started) with ZERO completions
        while the gateway process is up; any completion (or a down gateway)
        resets it; a fully idle box HOLDS it - idleness is never a wedge (no
        false P1 every quiet night). Persisted in ledger meta
        'd4_no_progress_ticks'; with led=None nothing is persisted.
    (2) orphan listener: reported ONLY on a definitive supervisor claim - a
        restart-handoff file that is EXPIRED or >=1h old (a fresh handoff is a
        restart in progress, not an orphan) whose pid differs from the live
        listener on the gateway port. Kill-list semantics stay D4's: the finding
        names only the orphan.

    `gateway_up`/`handoff`/`listener_pid` are injectable for offline tests."""
    th = C.load_skill_config("thresholds.json")["d4_timer_refire"]
    wedge = {}
    st = slice_stats or {}
    if gateway_up is None:
        gateway_up = _proc_up("openclaw")
    ticks = 0
    if led is not None:
        try:
            ticks = int(led.get_meta("d4_no_progress_ticks", "0") or 0)
        except (TypeError, ValueError):
            ticks = 0
    if int(st.get("completions", 0) or 0) > 0 or gateway_up == "down":
        ticks = 0
    elif int(st.get("starts", 0) or 0) > 0 and gateway_up == "up":
        ticks += 1
    # else: no demand observed - hold the counter (an idle box is not a wedge)
    if led is not None:
        led.set_meta("d4_no_progress_ticks", ticks)
    if ticks:
        wedge["gateway_healthy_no_progress_ticks"] = ticks

    h = _read_handoff() if handoff is C.MISSING else handoff
    if isinstance(h, dict) and h.get("pid"):
        now = datetime.now(timezone.utc)
        created = _handoff_epoch(h.get("createdAt"))
        if created is None and h.get("_mtime"):
            try:
                created = datetime.fromtimestamp(float(h["_mtime"]), timezone.utc)
            except (OverflowError, OSError, ValueError):
                created = None
        age_h = (now - created).total_seconds() / 3600.0 if created else None
        expires = _handoff_epoch(h.get("expiresAt"))
        stale = (expires is not None and expires < now) or \
                (age_h is not None and age_h >= 1.0)
        if stale:
            lp = _listener_pid_on(th["gateway_port"]) \
                if listener_pid is C.MISSING else listener_pid
            try:
                sup = int(h["pid"])
            except (TypeError, ValueError):
                sup = None
            if lp and sup and int(lp) != sup:
                wedge["orphan_listener_pid"] = int(lp)
                wedge["supervisor_pid"] = sup
                if age_h is not None:
                    wedge["handoff_age_hours"] = round(age_h, 1)
    return wedge


def collect_evidence(led=None):
    """Assemble the evidence dict from the box, best-effort. Detectors run over
    whatever is available; a missing source contributes no findings, never an
    error. With a Ledger (the tick path): the D3 slice is offset-tracked and the
    D4 counters persist. With led=None (the read-only audit path): bounded tail
    PEEK, nothing persisted, no offset advanced.

    D5/D6 attach HERE when they land (fix design 2026-07-13 SS4): a
    collect_sessions() over the gateway log's model-fetch starts feeds
    d5_completion_rate (windows already carry per-hour `completions` for it),
    and a collect_sends() over the sendguard ledger feeds
    d6_outbound_send_rate; both then ride the 60s pulse lane."""
    rows, slice_stats = _read_new_trajectory_rows(led)
    return {"units": collect_units(),
            "windows": collect_windows(),
            "runs": collect_runs(rows),
            "crons": collect_crons(led),
            "wedge": collect_wedge(led, slice_stats)}


def self_test():
    import tempfile
    print("[loop_watchdog] self-test: DRY_RUN records+plans-nothing, armed-parks, escalate offline")

    storm = {"units": [{"name": "cc-app", "delta": 12, "day_restarts": 900}],
             "windows": [], "runs": [], "crons": [], "wedge": {}}

    def dead_tx(url, body):
        raise OSError("offline self-test: no network")

    with tempfile.TemporaryDirectory() as td:
        os.environ["LOOP_STATE_DIR"] = os.path.join(td, "loop-protection")
        led = Ledger()
        # DRY_RUN (armed False): the storm is a P1 finding, RECORDED, but nothing applied.
        s = tick(storm, led, armed=False, escalate_transport=dead_tx, box="box-example")
        assert s["findings"] == 1 and s["applied"] == 0 and s["planned"] == 1
        assert s["by_class"].get("LP-B1") == 1
        assert len(led.open_findings("LP-B1")) == 1
        assert led.list_fixes() == []  # DRY_RUN mutated nothing
        print("  DRY_RUN case: PASS (P1 recorded; zero fixes applied; observe-only)")

        # A working box produces zero findings (no noise).
        s2 = tick({"units": [{"name": "gw", "delta": 0}]}, led, armed=False, box="box-example")
        assert s2["findings"] == 0 and s2["alerts"] == 0
        print("  quiet case: PASS (no findings, no alerts on a healthy box)")

        # Tier-3 class escalates offline (UNSENT fallback), never tight-loops.
        empty = {"units": [], "crons": [{"name": "noop", "declared_schedule": "@daily",
                 "actual_fires_per_day": 300}], "windows": [], "runs": [], "wedge": {}}
        s3 = tick(empty, led, armed=True, escalate_transport=dead_tx, box="box-example")
        assert s3["findings"] >= 1
        print("  escalate case: PASS (offline escalation via UNSENT fallback, no crash)")

        led.close()
        os.environ.pop("LOOP_STATE_DIR", None)

    # ---- the collect layer: a synthetic loop trajectory yields REAL evidence --
    # Regression case for the Star incident: the old collect_evidence() STUB
    # returned {"windows": [], "runs": [], "crons": [], "wedge": {}} so D2/D3/D4
    # analyzed NOTHING even fully armed. This proves a loop on disk becomes
    # findings, hermetically (LOOP_NO_PROBES=1: zero subprocess, zero network).
    with tempfile.TemporaryDirectory() as td:
        os.environ["LOOP_STATE_DIR"] = os.path.join(td, "loop-protection")
        os.environ["LOOP_OPENCLAW_ROOT"] = os.path.join(td, "openclaw")
        os.environ[_PROBES_OFF_ENV] = "1"
        sess_dir = Path(td) / "openclaw" / "agents" / "main" / "sessions"
        sess_dir.mkdir(parents=True)
        now = datetime.now(timezone.utc)
        t0 = (now - timedelta(minutes=90)).replace(microsecond=0)
        rows = [{"type": "session.started", "ts": t0.isoformat(), "sessionId": "s1",
                 "sessionKey": "agent:main:main", "runId": "r0",
                 "modelId": "minimax-m3:cloud", "provider": "ollama",
                 "data": {"trigger": "cron"}}]
        for i in range(12):  # 12 identical SUCCESSFUL runs, 300k paid tokens each
            common = {"ts": (t0 + timedelta(minutes=2 * i)).isoformat(),
                      "sessionId": "s1", "sessionKey": "agent:main:main",
                      "runId": "r%d" % (i + 1), "seq": i,
                      "modelId": "minimax-m3:cloud", "provider": "ollama"}
            rows.append(dict(common, type="model.completed",
                             data={"usage": {"input": 250000, "output": 50000,
                                             "total": 300000}}))
            rows.append(dict(common, type="trace.artifacts",
                             data={"finalStatus": "success",
                                   "usage": {"total": 300000},
                                   "toolMetas": [{"toolName": "exec"},
                                                 {"toolName": "message"}]}))
        (sess_dir / "s1.trajectory.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

        led = Ledger()
        ev = collect_evidence(led)
        assert ev["windows"], "collect_windows EMPTY over a real trajectory stream"
        assert any(w["paid_tokens"] > 0 for w in ev["windows"])  # D2 sees usage now
        assert all(w["initiated_sessions"] == 0 for w in ev["windows"])  # cron != human
        okr = [r for r in ev["runs"] if r["error_class"] == "OK"]
        assert len(okr) >= 12 and okr[0]["tool_sequence"] == ["exec", "message"]
        thr = C.load_skill_config("thresholds.json")
        fnd = run_detectors(ev, thr, C.load_signatures())
        assert any(f["loop_class"] == "LP-A2" and f["severity"] == "P1"
                   for f in fnd), "D2 must flag the idle paid burn"
        assert any(f["detector"] == "D3" and f["severity"] == "P1"
                   for f in fnd), "D3 must flag the repeated identical SUCCESSFUL turn"
        ev2 = collect_evidence(led)
        assert ev2["runs"] == []  # the slice was offset-consumed
        print("  collect case: PASS (stub replaced: synthetic loop -> real windows/"
              "runs; D2+D3 fire; slice offset-consumed)")

        # crons: observed-fire counting via last-run marker transitions
        jobs_fx = [{"id": "j1", "name": "resume", "enabled": True,
                    "schedule": {"kind": "cron", "expr": "0 9 * * *"},
                    "state": {"lastRunAtMs": 1000}, "delivery": {"mode": "none"}}]
        c1 = collect_crons(led, jobs=jobs_fx)
        assert c1[0]["declared_schedule"] == "0 9 * * *"
        assert c1[0]["actual_fires_per_day"] is None  # first sight: never a guess
        jobs_fx[0]["state"]["lastRunAtMs"] = 2000
        c2 = collect_crons(led, jobs=jobs_fx)
        jobs_fx[0]["state"]["lastRunAtMs"] = 3000
        c3 = collect_crons(led, jobs=jobs_fx)
        assert c2[0]["actual_fires_per_day"] == 1 and c3[0]["actual_fires_per_day"] == 2
        print("  collect-crons case: PASS (marker transitions counted, persisted, "
              "first-sight None)")

        # wedge: demand-without-progress counts; progress resets; idle holds;
        # a stale handoff + foreign listener = orphan; a fresh handoff never is.
        w1 = collect_wedge(led, {"starts": 2, "completions": 0}, gateway_up="up",
                           handoff=None)
        collect_wedge(led, {"starts": 1, "completions": 0}, gateway_up="up",
                      handoff=None)
        w3 = collect_wedge(led, {"starts": 3, "completions": 0}, gateway_up="up",
                           handoff=None)
        assert w1["gateway_healthy_no_progress_ticks"] == 1
        assert w3["gateway_healthy_no_progress_ticks"] == 3  # D4 P1 threshold
        wr = collect_wedge(led, {"starts": 0, "completions": 4}, gateway_up="up",
                           handoff=None)
        assert "gateway_healthy_no_progress_ticks" not in wr  # progress resets
        stale_handoff = {"pid": 222,
                         "createdAt": (now - timedelta(hours=30)).isoformat()}
        wo = collect_wedge(led, {}, gateway_up="up", handoff=stale_handoff,
                           listener_pid=111)
        assert wo["orphan_listener_pid"] == 111 and wo["supervisor_pid"] == 222
        fresh_handoff = {"pid": 222, "createdAt": now.isoformat()}
        wf = collect_wedge(led, {}, gateway_up="up", handoff=fresh_handoff,
                           listener_pid=111)
        assert "orphan_listener_pid" not in wf  # mid-restart is not an orphan
        print("  collect-wedge case: PASS (demand-gated counter; reset on progress; "
              "stale-handoff orphan only)")

        led.close()
        for k in ("LOOP_STATE_DIR", "LOOP_OPENCLAW_ROOT", _PROBES_OFF_ENV):
            os.environ.pop(k, None)

    print("[loop_watchdog] self-test: PASS")
    return 0


def _cli(argv=None):
    ap = argparse.ArgumentParser(description="Loop Protection per-box watchdog tick.")
    ap.add_argument("cmd", nargs="?", default="tick", choices=["tick"])
    ap.add_argument("--no-send", action="store_true",
                    help="do not deliver alerts/escalations (still records findings)")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    led = Ledger()
    try:
        box = led.get_meta("box", "box")
        evidence = collect_evidence(led)
        tx = (lambda url, body: True) if a.no_send else None
        summary = tick(evidence, led, escalate_transport=tx, box=box)
        print(json.dumps(summary, sort_keys=True))
        return 0
    finally:
        led.close()


if __name__ == "__main__":
    sys.exit(_cli())
