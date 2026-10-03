#!/usr/bin/env python3
"""SKS-001 - Fixes 1, 2, 4 (mark-fixed sliver), 6 (code), 11: offline drills.

Hermetic: fixtures only, stub runner/launchctl/pm2/docker text injected, no network,
no real `openclaw`, no live process, no model call. Run:  python3 tests/test_october_feeds.py
(rc 0 = every case PASS).

Fixture shapes follow the October CLI contract documented in the installed OpenClaw
build (docs/cli/sessions.md, docs/cli/audit.md, dist/audit-activity schema):
  sessions --json  -> {"sessions":[{key,agentId,model,modelProvider,totalTokens,...}],
                       "hasMore":bool,"totalCount":n}
  audit --json     -> {"events":[{sequence,occurredAt(ms),runId,sessionKey,toolName,
                       action,status,redaction:"metadata_only",...}],"nextCursor"?:str}
CONTENT-FREE fields only. Nothing here carries a message, an argument or a result.
"""
import copy
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(SKILL / "scripts"))
os.environ["LOOP_NO_PROBES"] = "1"
os.environ["LOOP_ALLOW_ROOT"] = "1"

import loop_common as C            # noqa: E402
import loop_detectors as D         # noqa: E402
import loop_killcards as KC        # noqa: E402
import loop_watchdog as W          # noqa: E402
from loop_ledger import Ledger     # noqa: E402

FAILS = []
NOW = datetime(2026, 10, 3, 15, 30, 0, tzinfo=timezone.utc)
TH = C.load_skill_config("thresholds.json")


def check(name, ok, detail=""):
    print("  %s: %s%s" % ("PASS" if ok else "FAIL", name, (" (%s)" % detail) if detail else ""))
    if not ok:
        FAILS.append(name)


def ms(dt):
    return int(dt.timestamp() * 1000)


# --------------------------------------------------------------------------- #
# the three-tier signatures SHAPE (SKS-007's structure), inlined so this test does not
# depend on that lane having merged. Unknown/absent tier => UNDETERMINED.
# --------------------------------------------------------------------------- #
TIERED_SIG = {
    "anthropic_family_deny_prefixes": ["claude-", "anthropic/", "us.anthropic."],
    "paid_tier_markers": {
        "schema": 2,
        "normalize": {"lowercase": True, "strip_leading_slashes": True,
                      "strip_one_trailing_parenthesized_qualifier": True,
                      "router_prefix": "9router/"},
        "tiers": {
            "metered": {"counts_as_paid": True, "include_anthropic_family": True,
                        "providers": ["openrouter", "openai", "deepseek", "moonshot", "google"],
                        "provider_prefixes": ["atp-"]},
            "subscription_capped": {"counts_as_paid": False, "providers": ["ollama-cloud"],
                                    "providers_when_router_prefixed": ["ollama"],
                                    "name_suffixes": [":cloud", "-cloud"]},
            "local": {"counts_as_paid": False, "providers": ["ollama-local"],
                      "providers_when_not_router_prefixed": ["ollama"]},
        },
    },
}


def runner_for(sessions=None, audit=None, cron=None, fail=None):
    """An injectable stand-in for W._openclaw_json. `audit` maps kind -> list of pages
    (each a dict). `fail` maps a command word to a status string to simulate a miss.
    Records every argv so a test can prove only read-only commands were requested."""
    calls = []
    page_idx = {}

    def run(args, timeout=20):
        calls.append(list(args))
        word = args[0]
        if fail and word in fail:
            return None, fail[word]
        if word == "sessions":
            return (sessions if sessions is not None else {"sessions": []}), "ok"
        if word == "audit":
            kind = args[args.index("--kind") + 1]
            pages = (audit or {}).get(kind, [{"events": []}])
            i = page_idx.get(kind, 0)
            page_idx[kind] = i + 1
            return pages[min(i, len(pages) - 1)], "ok"
        if word == "cron":
            return (cron if cron is not None else {"jobs": []}), "ok"
        return None, "exit:1"
    run.calls = calls
    return run


def sess_row(key, total, model="deepseek-v4", prov="deepseek", upd_min=5, inter_min=None):
    r = {"key": key, "agentId": "main", "model": model, "modelProvider": prov,
         "totalTokens": total, "inputTokens": total // 2, "outputTokens": total // 2,
         "updatedAt": ms(NOW - timedelta(minutes=upd_min))}
    if inter_min is not None:
        r["lastInteractionAt"] = ms(NOW - timedelta(minutes=inter_min))
    return r


def ev(seq, kind, action, status, run="r1", sess="agent:main:main", tool=None, at_s=0):
    e = {"schemaVersion": 1, "eventId": "e%d" % seq, "sequence": seq,
         "sourceSequence": seq, "occurredAt": ms(NOW - timedelta(minutes=2)) + at_s * 1000,
         "redaction": "metadata_only", "eventType": kind, "kind": kind, "action": action,
         "status": status, "agentId": "main", "sessionKey": sess, "runId": run,
         "actor": {"type": "agent", "id": "main"}}
    if tool:
        e["toolName"] = tool
    return e


def main():
    # ===================================================================== #
    # FIX 1 - D2: session token DELTAS, tiers read from signatures data
    # ===================================================================== #
    print("== Fix 1 / D2 sessions feed: deltas + tiers ==")
    with tempfile.TemporaryDirectory() as td:
        led = Ledger(os.path.join(td, "lp"))
        rows1 = [sess_row("agent:main:cron:a", 5_000_000, "deepseek-v4", "deepseek"),
                 sess_row("agent:main:cron:b", 7_000_000, "glm-5:cloud", "ollama-cloud"),
                 sess_row("agent:main:cron:c", 9_000_000, "qwen3", "ollama-local"),
                 sess_row("agent:main:cron:d", 3_000_000, "mystery", "acme")]
        n1 = []
        w1 = W.collect_session_windows(rows1, led, NOW, signatures=TIERED_SIG, notes=n1)
        check("first sight charges ZERO (lifetime counts are never a tick of burn)",
              all(w["paid_tokens"] == 0 and w["subscription_tokens"] == 0 for w in w1))
        rows2 = [dict(r, totalTokens=r["totalTokens"] + 400_000) for r in rows1]
        n2 = []
        w2 = W.collect_session_windows(rows2, led, NOW, signatures=TIERED_SIG, notes=n2)
        cur = w2[-1]
        check("second run charges the DELTA per tier: metered=paid, ollama-cloud="
              "subscription, ollama-local=local, unknown tier=undetermined",
              cur["paid_tokens"] == 400_000 and cur["subscription_tokens"] == 400_000
              and cur["local_tokens"] == 400_000 and cur["undetermined_tokens"] == 400_000,
              json.dumps({k: cur[k] for k in ("paid_tokens", "subscription_tokens",
                                              "local_tokens", "undetermined_tokens")}))
        check("an unclassifiable model is NAMED undetermined, not guessed", any("UNDETERMINED" in x for x in n2))
        f2 = D.d2_token_burn_rate(w2, TH, TIERED_SIG)
        check("D2 fires nothing for local / unknown tier and counts only metered as paid",
              [x for x in f2 if x["severity"] == "P1"] == [] or all(
                  "400000" in x["detail"] for x in f2 if x["severity"] == "P1"))
        # a backwards counter re-baselines to 0, never a negative or a spike
        rows3 = [dict(r, totalTokens=100) for r in rows1]
        w3 = W.collect_session_windows(rows3, led, NOW, signatures=TIERED_SIG, notes=[])
        check("a counter that goes BACKWARDS re-baselines to 0 (no spike)",
              w3[-1]["paid_tokens"] == 400_000)  # unchanged from the previous run's sum
        led.close()

        # human-interaction session = working burn, not idle burn
        led = Ledger(os.path.join(td, "lp2"))
        W.collect_session_windows([sess_row("agent:main:main", 1_000_000, inter_min=2)],
                                  led, NOW, signatures=TIERED_SIG, notes=[])
        wk = W.collect_session_windows([sess_row("agent:main:main", 2_000_000, inter_min=2)],
                                       led, NOW, signatures=TIERED_SIG, notes=[])
        check("a session with a RECENT human interaction charges no idle burn and "
              "counts as an initiated session",
              wk[-1]["paid_tokens"] == 0 and wk[-1]["initiated_sessions"] == 1)
        led.close()

        # pre-tier signatures (no `tiers` block): UNDETERMINED, fires nothing
        legacy_sig = {"paid_tier_markers": {"suffix_deny": [":cloud"],
                                            "metered_provider_slugs": ["openai"]}}
        led = Ledger(os.path.join(td, "lp3"))
        W.collect_session_windows([sess_row("k", 1_000_000, "x:cloud", "ollama")],
                                  led, NOW, signatures=legacy_sig, notes=[])
        nl = []
        wl = W.collect_session_windows([sess_row("k", 9_000_000, "x:cloud", "ollama")],
                                       led, NOW, signatures=legacy_sig, notes=nl)
        check("a signatures.json with NO tier block is UNDETERMINED: nothing counted paid, "
              "nothing fired",
              wl[-1]["paid_tokens"] == 0 and wl[-1]["undetermined_tokens"] == 8_000_000
              and not D.d2_token_burn_rate(wl, TH, legacy_sig))
        led.close()

        # idle metered burn really does reach D2 P1; subscription tier is WARN at most
        idle = [{"label": "w", "paid_tokens": 9_000_000, "subscription_tokens": 0,
                 "local_tokens": 0, "initiated_sessions": 0, "idle_consecutive": 1}]
        check("idle METERED burn over the P1 line = D2 P1",
              any(x["severity"] == "P1" for x in D.d2_token_burn_rate(idle, TH, TIERED_SIG)))
        sub_only = {"windows": [{"label": "w", "paid_tokens": 0, "subscription_tokens": 9_000_000,
                                 "local_tokens": 0, "initiated_sessions": 0,
                                 "idle_consecutive": 1}]}
        fs = W.run_detectors(sub_only, TH, TIERED_SIG)
        check("idle SUBSCRIPTION burn is WARN, labelled usage-window, never P1, never escalated",
              fs and all(x["severity"] == "WARN" and "usage-window" in x["detail"]
                         and x.get("escalate") is False for x in fs))

    # ===================================================================== #
    # FIX 1 - audit feed: cursor persistence, first sight, backwards sequence
    # ===================================================================== #
    print("== Fix 1 / audit feed: cursor persisted under loop-audit:<kind> ==")
    with tempfile.TemporaryDirectory() as td:
        led = Ledger(os.path.join(td, "lp"))
        page = {"events": [ev(7, "tool_action", "tool.action.finished", "failed", tool="exec"),
                           ev(6, "tool_action", "tool.action.finished", "succeeded", tool="read"),
                           ev(5, "tool_action", "tool.action.finished", "succeeded", tool="read")]}
        r1 = W.fetch_audit("tool_action", led, NOW, runner_for(audit={"tool_action": [page]}))
        check("first run consumes the new events oldest-first", [e["sequence"] for e in r1["events"]] == [5, 6, 7])
        check("cursor PERSISTED in the offsets table under loop-audit:tool_action",
              led.get_offset("loop-audit:tool_action") == 7)
        r2 = W.fetch_audit("tool_action", led, NOW, runner_for(audit={"tool_action": [page]}))
        check("second run over the same records yields NOTHING new (cursor honoured) "
              "but raw_count still sees them (the blind control needs that)",
              r2["events"] == [] and r2["raw_count"] == 3)
        page2 = {"events": [ev(9, "tool_action", "tool.action.finished", "succeeded", tool="read")] + page["events"]}
        r3 = W.fetch_audit("tool_action", led, NOW, runner_for(audit={"tool_action": [page2]}))
        check("a later run sees only the records ABOVE the stored cursor",
              [e["sequence"] for e in r3["events"]] == [9] and led.get_offset("loop-audit:tool_action") == 9)
        # sequence goes BACKWARDS (rebuilt state database): rewind, never discard
        page_low = {"events": [ev(2, "tool_action", "tool.action.finished", "succeeded", tool="read"),
                               ev(1, "tool_action", "tool.action.finished", "succeeded", tool="read")]}
        r4 = W.fetch_audit("tool_action", led, NOW, runner_for(audit={"tool_action": [page_low]}))
        check("a sequence that goes BACKWARDS rewinds the cursor instead of discarding every record",
              [e["sequence"] for e in r4["events"]] == [1, 2])
        led.close()

        # first sight with an old backlog: only the last first_sight minutes are consumed
        led = Ledger(os.path.join(td, "lp2"))
        old = ev(3, "agent_run", "agent.run.finished", "failed")
        old["occurredAt"] = ms(NOW - timedelta(minutes=50))
        new = ev(4, "agent_run", "agent.run.finished", "failed")
        rf = W.fetch_audit("agent_run", led, NOW, runner_for(audit={"agent_run": [{"events": [new, old]}]}))
        check("FIRST SIGHT never replays an hour of history into D3 (only the recent slice)",
              [e["sequence"] for e in rf["events"]] == [4])
        led.close()

        # paging: nextCursor followed; a feed miss is a NAMED status, not an empty list
        pg1 = {"events": [ev(20, "tool_action", "tool.action.finished", "failed", tool="exec")], "nextCursor": "19"}
        pg2 = {"events": [ev(19, "tool_action", "tool.action.finished", "failed", tool="exec")]}
        rp = W.fetch_audit("tool_action", None, NOW, runner_for(audit={"tool_action": [pg1, pg2]}))
        check("nextCursor paging is followed", rp["raw_count"] == 2)
        rm = W.fetch_audit("tool_action", None, NOW, runner_for(fail={"audit": "cli-error:cli_error"}))
        check("a CLI failure is a NAMED status with no rows - never a silent empty success",
              rm["status"] == "cli-error:cli_error" and rm["events"] == [])

    # ===================================================================== #
    # FIX 1 - detectors rebuilt over audit evidence (D3, D5, D6)
    # ===================================================================== #
    print("== Fix 1 / D3 D5 D6 over audit evidence ==")
    fin = [ev(100 + i, "agent_run", "agent.run.finished", "failed", run="run%d" % i,
              sess="agent:main:cron:x") for i in range(5)]
    tools = [ev(200 + i, "tool_action", "tool.action.finished", "failed", run="run%d" % i,
                sess="agent:main:cron:x", tool="exec") for i in range(5)]
    ae = W.audit_evidence(fin, tools, TH)
    check("D3: the same run status repeated 5x in one session = P1 loop-confirmed",
          any(x["severity"] == "P1" and x["detector"] == "D3" for x in D.d3_identical_signature(ae["runs"], TH)))
    ok_fin = [ev(300 + i, "agent_run", "agent.run.finished", "succeeded", run="o%d" % i,
                 sess="agent:main:main") for i in range(2)]
    check("D3: two ordinary successful runs stay silent (silence rule)",
          D.d3_identical_signature(W.audit_evidence(ok_fin, [], TH)["runs"], TH) == [])

    blk = [ev(400 + i, "tool_action", "tool.action.finished", "blocked", run="rB",
              sess="agent:main:cron:y", tool="read", at_s=i) for i in range(12)]
    ae5 = W.audit_evidence([], blk, TH)
    f5 = D.d5_transcript_poison(ae5["sessions"], TH)
    check("D5: `tool_action status=blocked` burst of 12 in ONE runId = P1 LP-A8, per runId",
          len(f5) == 1 and f5[0]["severity"] == "P1" and f5[0]["loop_class"] == "LP-A8"
          and f5[0]["unit"] == "run:rB")
    blk_spread = [ev(500 + i, "tool_action", "tool.action.finished", "blocked", run="rS%d" % i,
                     sess="agent:main:cron:z", tool="read") for i in range(12)]
    check("D5: the same 12 blocks spread over 12 DIFFERENT runs never forms a burst",
          D.d5_transcript_poison(W.audit_evidence([], blk_spread, TH)["sessions"], TH) == [])

    fails = [ev(600 + i, "tool_action", "tool.action.finished", "failed", run="rF",
                sess="agent:main:cron:q", tool="exec", at_s=i * 2) for i in range(15)]
    ae6 = W.audit_evidence([], fails, TH)
    f6 = D.d6_futile_retry_burst(ae6["bursts"], TH)
    check("D6 (failing-burst face only): 15 failed `exec` calls in 30s = P1 LP-A9; failclosed is "
          "always 0 because audit carries no result text",
          any(x["severity"] == "P1" and x["loop_class"] == "LP-A9" for x in f6)
          and all(b["failclosed"] == 0 for b in ae6["bursts"]))
    slow = [ev(700 + i, "tool_action", "tool.action.finished", "failed", run="rG",
               sess="agent:main:cron:q", tool="exec", at_s=i * 61) for i in range(15)]
    check("D6: the same 15 failures spaced past the 60-second window never burst",
          D.d6_futile_retry_burst(W.audit_evidence([], slow, TH)["bursts"], TH) == [])
    healthy = [ev(800 + i, "tool_action", "tool.action.finished", "succeeded", run="rH",
                  sess="agent:main:main", tool="exec", at_s=i) for i in range(300)]
    check("D6: a 300-call fully SUCCESSFUL burst stays silent (volume alone is never a loop)",
          D.d6_futile_retry_burst(W.audit_evidence([], healthy, TH)["bursts"], TH) == [])
    check("D5/D6 evidence carries no content: only whitelisted keys",
          all(set(b) <= {"unit", "path", "tool", "calls", "errors", "failclosed", "span_seconds"}
              for b in ae6["bursts"]))

    # ===================================================================== #
    # FIX 1 - BLIND-COLLECTOR CONTROL: zero rows while sessions are active
    # ===================================================================== #
    print("== Fix 1 / blind-collector control ==")
    live_sessions = {"sessions": [sess_row("agent:main:main", 100, upd_min=3)]}
    with tempfile.TemporaryDirectory() as td:
        led = Ledger(os.path.join(td, "lp"))
        # the instrument returns NOTHING while a session updated 3 minutes ago
        ev_blind = W.collect_evidence(led, runner=runner_for(sessions=live_sessions), now=NOW)
        check("zero audit rows while sessions are ACTIVE => 'audit:agent_run' is named BLIND",
              "audit:agent_run" in ev_blind["blind"])
        fb = W.run_detectors(ev_blind, TH, TIERED_SIG)
        blind_f = [x for x in fb if x["detector"] == "FEED"]
        check("...and becomes a P2 finding 'watchdog blind: <collector>' that never escalates",
              blind_f and blind_f[0]["severity"] == "P2" and "watchdog blind" in blind_f[0]["detail"]
              and blind_f[0].get("escalate") is False)
        # known-good CONTROL: the identical box with the audit feed healthy is NOT blind
        good = {"agent_run": [{"events": [ev(1, "agent_run", "agent.run.started", "started")]}],
                "tool_action": [{"events": []}]}
        ev_ok = W.collect_evidence(led, runner=runner_for(sessions=live_sessions, audit=good), now=NOW)
        check("CONTROL: same active box, audit feed returning rows => NOT blind", ev_ok["blind"] == [])
        # a truly idle box (no active sessions, no rows) is not blind either
        ev_idle = W.collect_evidence(led, runner=runner_for(sessions={"sessions": []}), now=NOW)
        check("CONTROL: a genuinely idle box (no active sessions, no rows) is NOT blind", ev_idle["blind"] == [])
        # a FAILED feed is UNDETERMINED, never blind and never healthy
        ev_fail = W.collect_evidence(led, runner=runner_for(sessions=live_sessions,
                                     fail={"audit": "cli-error:cli_error"}), now=NOW)
        check("a feed that could not be READ is named UNDETERMINED, not blind and not healthy",
              ev_fail["blind"] == [] and any("UNDETERMINED" in n for n in ev_fail["undetermined"]))
        led.close()
    # the blind finding travels the WHOLE tick: it has no kill card, so it must be recorded
    # and alerted but never handed to Rescue Rangers (an instrument fault is not an incident)
    with tempfile.TemporaryDirectory() as td2:
        led2 = Ledger(os.path.join(td2, "lp"))
        sent = []
        evb = W.collect_evidence(led2, runner=runner_for(sessions=live_sessions), now=NOW)
        sb = W.tick(evb, led2, armed=True, escalate_transport=lambda u, b: sent.append(1) or True,
                    box="box-example")
        rows = [r for r in led2.all_findings() if r["loop_class"] == "LP-WD1"]
        check("the blind finding survives a whole armed tick: recorded P2, alerted, NEVER sent to "
              "Rescue Rangers, tick raised no error",
              len(rows) == 1 and rows[0]["severity"] == "P2" and sent == [] and sb["errors"] == 0
              and sb["alerts"] >= 1 and any("D7" in n for n in sb["undetermined"]),
              "sent=%s errors=%s" % (sent, sb["errors"]))
        led2.close()
    hc = W.feed_health_check(runner=runner_for(sessions=live_sessions), now=NOW)
    check("verify.sh --live control (feed_health_check): blind verdict + names the collector",
          hc["verdict"] == "blind" and hc["blind"] == ["audit:agent_run"] and hc["active_60"] == 1)
    hc2 = W.feed_health_check(runner=runner_for(sessions=live_sessions, audit=good), now=NOW)
    check("feed_health_check: healthy when the audit feed returns records", hc2["verdict"] == "healthy")
    hc3 = W.feed_health_check(runner=runner_for(sessions={"sessions": []}), now=NOW)
    check("feed_health_check: idle box => 'idle', not blind", hc3["verdict"] == "idle")
    hc4 = W.feed_health_check(runner=runner_for(fail={"sessions": "no-binary"}), now=NOW)
    check("feed_health_check: unreadable control => 'undetermined' (never folded into healthy)",
          hc4["verdict"] == "undetermined")
    rr = runner_for(sessions=live_sessions, audit=good)
    W.collect_evidence(None, runner=rr, now=NOW)
    check("only READ-ONLY commands were requested (sessions / audit / cron list)",
          all(c[0] in ("sessions", "audit", "cron") for c in rr.calls)
          and not any(x in c for c in rr.calls for x in ("delete", "archive", "reset", "abort", "compact")))

    # ===================================================================== #
    # FIX 2 - orphan gateway: three cases, never the handoff file
    # ===================================================================== #
    print("== Fix 2 / orphan gateway uses the SUPERVISOR pid ==")
    alive = lambda p: p in (30208, 31000)
    # case 1: equal -> silent
    w = W.collect_wedge(None, {}, gateway_up="up", supervisor_pid=30208, listener_pid=30208, pid_alive=alive)
    check("listener pid == supervisor pid: SILENT (the real operator-box case)", "orphan_listener_pid" not in w
          and D.d4_timer_refire([], w, TH) == [])
    # case 2: differs, supervisor live -> P1, and the finding names ONLY the listener
    w = W.collect_wedge(None, {}, gateway_up="up", supervisor_pid=30208, listener_pid=31000, pid_alive=alive)
    f = [x for x in D.d4_timer_refire([], w, TH) if x["loop_class"] == "LP-B3"]
    check("listener pid != LIVE supervisor pid: P1 LP-B3", len(f) == 1 and f[0]["severity"] == "P1")
    check("the P1 names the stray listener, never the supervisor's own pid as the orphan",
          "orphan listener pid 31000" in f[0]["detail"] and "pid 30208 on" not in f[0]["detail"])
    # case 3: supervisor unreadable -> silent + UNDETERMINED note
    notes = []
    w = W.collect_wedge(None, {}, gateway_up="up", supervisor_pid=None, listener_pid=31000, notes=notes, pid_alive=alive)
    check("supervisor pid unreadable: SILENT and named UNDETERMINED (never a finding)",
          "orphan_listener_pid" not in w and any("UNDETERMINED" in n for n in notes))
    # the legacy JSON handoff file is IGNORED, never read, never deleted
    with tempfile.TemporaryDirectory() as td:
        os.environ["LOOP_OPENCLAW_ROOT"] = td
        hp = Path(td) / "gateway-supervisor-restart-handoff.json"
        hp.write_text(json.dumps({"pid": 1166, "createdAt": "2026-07-04T00:00:00Z"}))
        before = hp.read_bytes()
        w = W.collect_wedge(None, {}, gateway_up="up", supervisor_pid=30208, listener_pid=30208, pid_alive=alive)
        check("a stale July handoff file (pid 1166 vs live listener 30208) raises NO LP-B3 "
              "and is left byte-identical (disabled, never deleted)",
              "orphan_listener_pid" not in w and hp.read_bytes() == before and hp.exists())
        os.environ.pop("LOOP_OPENCLAW_ROOT", None)
    check("a DEAD supervisor pid is no evidence (nothing to compare against): silent",
          "orphan_listener_pid" not in W.collect_wedge(None, {}, gateway_up="up", supervisor_pid=999,
                                                       listener_pid=31000, pid_alive=alive))
    # supervisor sources, environment-free
    tbl = "PID\tStatus\tLabel\n-\t0\tcom.apple.x\n30208\t0\tai.openclaw.gateway\n-\t1\tai.openclaw.gateway-watchdog\n"
    parsed = W._parse_launchctl_table(tbl)
    check("launchctl TABLE parse: PID/Status/Label by header, ai.openclaw.* only, '-' = no live pid",
          parsed == {"ai.openclaw.gateway": 30208, "ai.openclaw.gateway-watchdog": None})
    check("launchctl output whose header is not PID/Status/Label is UNDETERMINED (None), not empty",
          W._parse_launchctl_table("garbage\n1 2 ai.openclaw.gateway\n") is None)
    src = (SKILL / "scripts" / "loop_watchdog.py").read_text()
    check("the watchdog never issues `launchctl print` / `ps eww` / a pm2 JSON listing / full docker inspect",
          not any(bad in "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#")
                                   and '"""' not in l and "NEVER" not in l and "never" not in l)
                  for bad in ('"print"', '"jlist"', '"describe"', "eww")))

    # ===================================================================== #
    # FIX 11 - scheduler-aware cron evidence + hasMore
    # ===================================================================== #
    print("== Fix 11 / cron: scheduler-managed jobs + hasMore ==")
    base_job = lambda n, **st: {"id": n, "name": n, "enabled": True,
                                "schedule": {"kind": "cron", "expr": "0 9 * * *"},
                                "state": dict({"lastRunAtMs": 1000}, **st), "delivery": {"mode": "none"}}
    with tempfile.TemporaryDirectory() as td:
        led = Ledger(os.path.join(td, "lp"))
        managed = []
        jobs = [base_job("ok-job"),
                base_job("backing-off", consecutiveErrors=4, lastRunStatus="error"),
                base_job("dead-job", autoDisabled=True)]
        W.collect_crons(led, jobs=jobs, now=NOW, managed=managed)
        for j in jobs:
            j["state"]["lastRunAtMs"] = 2000
        managed = []
        notes = []
        crons = W.collect_crons(led, jobs=jobs, now=NOW + timedelta(minutes=15), managed=managed, notes=notes)
        by = {c["name"]: c for c in crons}
        check("a normally-firing job still reports an observed fire", by["ok-job"]["actual_fires_per_day"] == 1)
        check("a job the scheduler is BACKING OFF reports no fire count (D4 stays silent) and "
              "carries the reason", by["backing-off"]["actual_fires_per_day"] is None
              and "backing off" in by["backing-off"]["scheduler_managed"])
        check("an AUTO-DISABLED job is evidence only (not even a cron row)",
              "dead-job" not in by and any(m["name"] == "dead-job" for m in managed))
        # a backing-off job that WOULD over-fire raises no LP-A4 P1
        crons2 = [dict(c, actual_fires_per_day=300) if c["name"] == "backing-off" else c for c in crons]
        crons2[[c["name"] for c in crons2].index("backing-off")]["actual_fires_per_day"] = None
        check("D4 raises NO P1/escalation for a scheduler-managed job",
              not [x for x in D.d4_timer_refire(crons2, {}, TH) if x["unit"] == "backing-off"])
        led.close()
    nh = []
    W.collect_crons(None, jobs=[base_job("a")], now=NOW, has_more=True, notes=nh)
    check("hasMore:true => D4 is named UNDETERMINED for the unseen jobs (never silently partial)",
          any("hasMore" in n and "UNDETERMINED" in n for n in nh))
    jobs_l, more, st = W._cron_list_via_cli(runner=runner_for(cron={"jobs": [base_job("a")], "hasMore": True}))
    check("_cron_list_via_cli surfaces hasMore", more is True and st == "ok" and len(jobs_l) == 1)
    j2, m2, s2 = W._cron_list_via_cli(runner=runner_for(fail={"cron": "timeout"}))
    check("a cron CLI miss is a NAMED status, never a silent empty list", j2 == [] and s2 == "timeout")

    # ===================================================================== #
    # FIX 6 (code parts) - D1 sources are environment-free
    # ===================================================================== #
    print("== Fix 6 / D1 without pm2 jlist: pm2 list table, launchctl, docker ==")
    PM2 = ("┌────┬──────────────┬─────────┬──────┬────────┬───┬────────┐\n"
           "│ id │ name         │ mode    │ pid  │ uptime │ ↺ │ status │\n"
           "├────┼──────────────┼─────────┼──────┼────────┼───┼────────┤\n"
           "│ 0  │ cc-app       │ fork    │ 4242 │ 10h    │ 4 │ online │\n"
           "│ 1  │ worker-two   │ fork    │ 0    │ 0      │ 31│ errored│\n"
           "└────┴──────────────┴─────────┴──────┴────────┴───┴────────┘\n"
           "Module\n"
           "┌────┬──────────────┬─────────┬──────┬────────┬───┬────────┐\n"
           "│ id │ module       │ version │ pid  │ status │ ↺ │ cpu    │\n"
           "│ 0  │ pm2-logrotate│ 3.0     │ 99   │ online │ 0 │ 0%     │\n"
           "└────┴──────────────┴─────────┴──────┴────────┴───┴────────┘\n")
    tbl = W._parse_pm2_table(PM2)
    check("pm2 list TABLE parsed BY HEADER NAME: name/pid/restarts/status; module table ignored",
          tbl and {t["name"]: (t["pid"], t["restart_time"], t["status"]) for t in tbl}
          == {"cc-app": (4242, 4, "online"), "worker-two": (None, 31, "errored")})
    check("an unparseable table returns None (UNDETERMINED), never an empty/zero list",
          W._parse_pm2_table("pm2: command output changed\n") is None and W._parse_pm2_table("") is None)
    with tempfile.TemporaryDirectory() as td:
        led = Ledger(os.path.join(td, "lp"))
        n = []
        u1 = W.collect_units(led, pm2_text=PM2, launchctl_text=None, docker_recs=None, notes=n, now=NOW)
        check("first sight of every pm2 unit is delta 0", all(u["delta"] == 0 for u in u1))
        PM2b = PM2.replace("│ 4 │", "│ 16│")
        u2 = W.collect_units(led, pm2_text=PM2b, launchctl_text=None, docker_recs=None, notes=n, now=NOW)
        d = {u["name"]: u["delta"] for u in u2}
        check("a real delta of 12 restarts is seen (and is a P1 for D1)",
              d["cc-app"] == 12 and any(x["severity"] == "P1" for x in D.d1_restart_velocity(u2, TH)))
        base_before = led.get_meta("d1_restart_baseline")
        n2 = []
        W.collect_units(led, pm2_text="not a table at all", launchctl_text=None, docker_recs=None, notes=n2, now=NOW)
        check("an UNPARSEABLE pm2 table is named UNDETERMINED, the baseline is left untouched, "
              "and it is NOT read as zero restarts",
              any("UNDETERMINED" in x for x in n2) and led.get_meta("d1_restart_baseline") == base_before)
        led.close()
    # launchctl pid delta = one restart; gateway findings are alert-only unit names
    with tempfile.TemporaryDirectory() as td:
        led = Ledger(os.path.join(td, "lp"))
        L1 = "PID\tStatus\tLabel\n100\t0\tai.openclaw.gateway\n200\t0\tai.openclaw.rescue-receiver\n"
        L2 = "PID\tStatus\tLabel\n101\t0\tai.openclaw.gateway\n200\t0\tai.openclaw.rescue-receiver\n"
        W.collect_units(led, pm2_text=None, launchctl_text=L1, docker_recs=None, notes=[], now=NOW)
        u = W.collect_units(led, pm2_text=None, launchctl_text=L2, docker_recs=None, notes=[], now=NOW)
        by = {x["name"]: x for x in u}
        check("launchctl: a live pid replaced by a different live pid counts as ONE restart; "
              "an unchanged pid counts none",
              by["ai.openclaw.gateway"]["delta"] == 1 and by["ai.openclaw.rescue-receiver"]["delta"] == 0
              and by["ai.openclaw.gateway"]["restarts"] == 1)
        L3 = "PID\tStatus\tLabel\n-\t0\tai.openclaw.gateway\n200\t0\tai.openclaw.rescue-receiver\n"
        u3 = W.collect_units(led, pm2_text=None, launchctl_text=L3, docker_recs=None, notes=[], now=NOW)
        check("a pid going to '-' (stopped / interval job idle) is NOT a restart",
              {x["name"]: x["delta"] for x in u3}["ai.openclaw.gateway"] == 0)
        nb = []
        W.collect_units(led, pm2_text=None, launchctl_text="Label Only\nx\n", docker_recs=None, notes=nb, now=NOW)
        check("a launchctl table with the wrong header is UNDETERMINED", any("UNDETERMINED" in x for x in nb))
        led.close()
    # docker: format-limited only
    seen_argv = []

    def fake_run_text(argv, timeout=10, env=None):
        seen_argv.append(list(argv))
        if argv[1] == "ps":
            return "openclaw-gw\nunrelated\n", "ok"
        return "/openclaw-gw 7\n", "ok"
    real_rt, real_which = W._run_text, None
    os.environ["LOOP_NO_PROBES"] = "0"
    os.environ["LOOP_DOCKER_BIN"] = "/usr/bin/true"
    W._run_text = fake_run_text
    try:
        recs, st = W._docker_restart_recs()
    finally:
        W._run_text = real_rt
        os.environ["LOOP_NO_PROBES"] = "1"
        os.environ.pop("LOOP_DOCKER_BIN", None)
    insp = [a for a in seen_argv if a[1] == "inspect"][0]
    check("docker: `inspect -f '{{.Name}} {{.RestartCount}}' <ctr>` is the ONLY inspect form used "
          "(format-limited, never a full inspect) and RestartCount is parsed",
          insp[2] == "-f" and insp[3] == "{{.Name}} {{.RestartCount}}"
          and recs == [{"name": "docker:openclaw-gw", "restart_time": 7, "status": "running"}])

    # ===================================================================== #
    # FIX 4 sliver - a ledger-only park NEVER marks the finding fixed
    # ===================================================================== #
    print("== Fix 4 sliver / parked-flag keeps the finding OPEN ==")
    with tempfile.TemporaryDirectory() as td:
        led = Ledger(os.path.join(td, "lp"))
        flag_exec = {"LF-6": lambda dry_run: {"applied": False, "state": "parked-flag",
                                              "reason": "ledger flag only; NOTHING stopped"}}
        real_apply = KC.apply

        def fake_apply(kc, ledger, armed, executors, verify_failed_last=False):
            return {"status": "refused", "detail": "parked-flag: a ledger flag only", "escalate": False,
                    "state": "parked-flag"}
        KC.apply = fake_apply
        try:
            s = W.tick({"units": [{"name": "cc-app", "delta": 12, "day_restarts": 900}], "windows": [],
                        "runs": [], "crons": [], "wedge": {}}, led, armed=True,
                       escalate_transport=lambda u, b: True, box="box-example")
        finally:
            KC.apply = real_apply
        fx = led.list_fixes()
        opn = led.open_findings("LP-B1")
        check("a `parked-flag` outcome records the fix as parked-flag and leaves the finding OPEN "
              "(never `fixed`)",
              s["applied"] == 0 and s.get("parked_flag") == 1 and len(opn) == 1
              and fx and fx[0]["verify_outcome"] == "parked-flag"
              and not [r for r in led.all_findings() if r["state"] == "fixed"])
        led.close()

    # ===================================================================== #
    # SECRET-LEAK DRILL (tests/secret-leak-test.sh pattern): poisoned stub env
    # ===================================================================== #
    print("== secret-leak drill: a poisoned stub environment never reaches ledger or stdout ==")
    TRACERS = ["TRACERPM2ENVsk11deadbeef", "TRACERLAUNCHDENVhunter2", "TRACERDOCKERENVservicerole",
               "TRACERSESSIONmessagebody", "TRACERAUDITargument"]
    with tempfile.TemporaryDirectory() as td:
        bindir = Path(td) / "bin"
        bindir.mkdir()
        # stub pm2: `list` prints a clean table; ANY other verb (jlist/describe) prints a tracer env
        (bindir / "pm2").write_text("#!/bin/sh\nif [ \"$1\" = \"list\" ]; then\ncat <<'EOF'\n%s\nEOF\nelse\n"
                                    "echo '{\"pm2_env\":{\"STRIPE_SECRET_KEY\":\"%s\"}}'\nfi\n"
                                    % (PM2.replace("\n", "\n"), TRACERS[0]))
        # stub launchctl: `list` is a clean table; `print` dumps an environment
        (bindir / "launchctl").write_text("#!/bin/sh\nif [ \"$1\" = \"list\" ]; then\nprintf 'PID\\tStatus\\tLabel\\n"
                                          "100\\t0\\tai.openclaw.gateway\\n'\nelse\necho 'environment = { TOKEN => %s }'\nfi\n"
                                          % TRACERS[1])
        # stub docker: format-limited inspect is clean; a bare inspect would dump Env
        (bindir / "docker").write_text("#!/bin/sh\nif [ \"$1\" = \"ps\" ]; then echo openclaw-gw; exit 0; fi\n"
                                       "if [ \"$1\" = \"inspect\" ] && [ \"$2\" = \"-f\" ]; then echo '/openclaw-gw 3'; exit 0; fi\n"
                                       "echo '\"Env\": [\"SUPABASE_SERVICE_ROLE_KEY=%s\"]'\n" % TRACERS[2])
        # stub openclaw: records are content-free, but EXTRA fields carry tracers that a
        # careless reader would copy into a finding
        sess = {"sessions": [dict(sess_row("agent:main:cron:leak", 9_000_000), messagePreview=TRACERS[3])]}
        aud = {"events": [dict(ev(1, "tool_action", "tool.action.finished", "failed", tool="exec"),
                               arguments=TRACERS[4], result=TRACERS[4])]}
        (bindir / "openclaw").write_text("#!/bin/sh\ncase \"$1\" in\nsessions) cat <<'EOF'\n%s\nEOF\n;;\n"
                                         "audit) cat <<'EOF'\n%s\nEOF\n;;\ncron) echo '{\"jobs\":[]}';;\nesac\n"
                                         % (json.dumps(sess), json.dumps(aud)))
        for f in bindir.iterdir():
            f.chmod(0o755)
        for k, v in (("LOOP_STATE_DIR", str(Path(td) / "lp")), ("LOOP_NO_PROBES", "0"),
                     ("OPENCLAW_BIN", str(bindir / "openclaw")), ("LOOP_PM2_BIN", str(bindir / "pm2")),
                     ("LOOP_LAUNCHCTL_BIN", str(bindir / "launchctl")),
                     ("LOOP_DOCKER_BIN", str(bindir / "docker")), ("LOOP_PLATFORM", "darwin")):
            os.environ[k] = v
        try:
            led = Ledger()
            # two ticks so a delta is real; tracers live ONLY in the stub environment surface
            for _ in range(2):
                evd = W.collect_evidence(led)
                W.tick(evd, led, armed=False, escalate_transport=lambda u, b: True, box="box-example")
            dump = json.dumps(evd, default=str, sort_keys=True)
            ledger_text = ""
            for tbl in ("findings", "fix_actions", "meta", "digests", "offsets", "breaker_state", "backoff_state"):
                for row in led.conn.execute("SELECT * FROM %s" % tbl).fetchall():
                    ledger_text += json.dumps([str(x) for x in tuple(row)]) + "\n"
            led.close()
            proc = subprocess.run([sys.executable, str(SKILL / "scripts" / "loop_watchdog.py"), "tick",
                                   "--dry-run", "--no-send"], capture_output=True, text=True,
                                  env=dict(os.environ))
            blob = dump + ledger_text + proc.stdout + proc.stderr
            leaked = [t for t in TRACERS if t in blob]
            check("no tracer from the poisoned stub environment reached the evidence, the ledger, "
                  "stdout or stderr", not leaked, "leaked=%s" % leaked)
            check("the tick over the poisoned stubs still ran to completion (rc 0)", proc.returncode == 0,
                  (proc.stderr or "")[-200:])
        finally:
            for k in ("LOOP_STATE_DIR", "OPENCLAW_BIN", "LOOP_PM2_BIN", "LOOP_LAUNCHCTL_BIN",
                      "LOOP_DOCKER_BIN", "LOOP_PLATFORM"):
                os.environ.pop(k, None)
            os.environ["LOOP_NO_PROBES"] = "1"

    # ===================================================================== #
    # captured-shape fixtures: REAL October field names, synthetic values
    # ===================================================================== #
    print("== fixtures in the real October CLI shape ==")
    fx = HERE / "fixtures"
    fx_s = json.loads((fx / "october-sessions.active.json").read_text())
    fx_r = json.loads((fx / "october-audit.agent_run.json").read_text())
    fx_t = json.loads((fx / "october-audit.tool_action.json").read_text())
    fnow = datetime.fromtimestamp(1790000000, timezone.utc)
    check("fixtures are content-free: only whitelisted audit keys, redaction metadata_only",
          all(e["redaction"] == "metadata_only" for e in fx_r["events"] + fx_t["events"])
          and not any(k in e for e in fx_r["events"] + fx_t["events"]
                      for k in ("arguments", "result", "content", "message", "text")))
    with tempfile.TemporaryDirectory() as td:
        led = Ledger(os.path.join(td, "lp"))
        rn = runner_for(sessions=fx_s, audit={"agent_run": [fx_r], "tool_action": [fx_t]})
        e1 = W.collect_evidence(led, runner=rn, now=fnow)
        check("fixture drill: the sessions + audit shapes parse end to end, nothing blind, no feed errors",
              e1["blind"] == [] and not any("unreadable" in n for n in e1["undetermined"]))
        found = W.run_detectors(e1, TH, TIERED_SIG)
        classes = {(f["detector"], f["severity"]) for f in found}
        check("fixture drill: D3 (5 failed runs), D5 (12 blocked), D6 (15 failed exec) all fire P1",
              {("D3", "P1"), ("D5", "P1"), ("D6", "P1")} <= classes, str(sorted(classes)))
        led.close()

    print()
    if FAILS:
        print("FAILED: %d case(s): %s" % (len(FAILS), FAILS))
        return 4
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
