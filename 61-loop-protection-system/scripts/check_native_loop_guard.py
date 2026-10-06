#!/usr/bin/env python3
# =============================================================================
# SKILL 61 - LOOP PROTECTION SYSTEM :: check_native_loop_guard.py
# "native guard off": is OpenClaw's OWN per-run tool-loop guard turned on?
#
# OpenClaw's built-in guard (tools.loopDetection) ends a run after the second
# critical loop block - it does, up front, what D5/LF-9 were built to do after
# the fact. But it is OFF BY DEFAULT, and a per-agent override at
# agents.entries.<id>.tools.loopDetection beats the global value. This check
# reads both and raises ONE WARN finding when the effective value is not
# enabled:true for the global setting or for ANY agent.
#
# LAW OF THIS FILE
#   - READ-ONLY. The only subprocesses it can start are `config get` and
#     `agents list` (enforced in _ro(), not by convention). No `config set` /
#     `config unset` exists anywhere in this module; the fix is rendered as TEXT
#     (Tier 2, PREPARED ONLY) for an operator to run on-box. It is never applied
#     by the unattended tick and never by a test.
#   - A read that FAILS is UNDETERMINED, never "ok" and never "off". Only the
#     documented missing-path message counts as "unset".
#   - Zero model calls. Never prints a config value other than the boolean
#     `enabled` it parsed.
#
# CADENCE: once per day, driven from the watchdog tick by the companion's tick
# route (`tick-hook`), stamped in the ledger meta table exactly like
# last_tick_ts. No new cron job.
#
#   check [--json]    read + verdict now. exit 0 ok / 4 WARN / 3 UNDETERMINED
#   tick-hook         daily-gated check + ledger finding. ALWAYS exit 0.
#   --self-test       offline, stubbed (unset / false / true + overrides)
# =============================================================================
"""check_native_loop_guard.py - read-only check of OpenClaw's native loop guard."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import loop_common as C  # noqa: E402
import loop_cron as CR  # noqa: E402
from loop_ledger import Ledger, now_utc  # noqa: E402

EX_OK, EX_ERR, EX_UNDETERMINED, EX_FINDINGS = 0, 1, 3, 4

LOOP_CLASS = "NATIVE-GUARD-OFF"   # not a kill-card class: fix_class_for() -> None
DEDUP_KEY = "native-guard-off|box"
GLOBAL_PATH = "tools.loopDetection"
AGENT_PATH = "agents.entries.%s.tools.loopDetection"
CADENCE_HOURS = 24
RETRY_HOURS = 1                    # a failed read retries hourly, not daily
META_RUN = "native_guard_last_run_ts"
META_ATTEMPT = "native_guard_last_attempt_ts"

# The ONLY argv prefixes this module may execute. Mutation is unreachable.
_ALLOWED = {("config", "get"), ("agents", "list")}
# ponytail: ids outside this set are reported UNDETERMINED, not guessed at;
# add bracket-notation paths if a fleet agent id ever needs a dot.
_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_UNSET_RE = re.compile(r"config path not found|unknown config path", re.I)


# --------------------------------------------------------------------------- #
# reading (the only place a subprocess starts)
# --------------------------------------------------------------------------- #
def _ro(binary, args):
    if tuple(args[:2]) not in _ALLOWED:
        raise RuntimeError("check_native_loop_guard is read-only; refused: %s"
                           % " ".join(args[:3]))
    return CR._run(binary, args)


def _first_line(text):
    # OpenClaw's --json error envelope is pretty-printed; a bare first line is "{".
    try:
        d = json.loads((text or "").strip())
        msg = ((d.get("issues") or [{}])[0].get("message")
               or (d.get("error") or {}).get("message"))
        if isinstance(msg, str) and msg.strip():
            return msg.strip()[:200]
    except (ValueError, AttributeError, IndexError, TypeError):
        pass
    for ln in (text or "").splitlines():
        if ln.strip():
            return ln.strip()[:200]
    return "(no output)"


def _parse(raw):
    raw = (raw or "").strip()
    try:
        return json.loads(raw)
    except ValueError:
        pass
    for opener in "{[":
        i = raw.find(opener)
        if i >= 0:
            try:
                return json.loads(raw[i:])
            except ValueError:
                pass
    raise ValueError("not JSON")


def read_path(binary, path):
    """{'kind': 'value', 'value': v} | {'kind': 'unset'} | {'kind': 'error', 'detail'}.
    rc != 0 is 'unset' ONLY for the documented missing-path messages; any other
    failure (offline maintenance, unreadable config, timeout, rc 127) is an error."""
    rc, out, err = _ro(binary, ["config", "get", path, "--json"])
    if rc == 0:
        try:
            val = _parse(out)
        except ValueError:
            return {"kind": "error", "detail":
                    "config get %s: rc 0 but stdout is not JSON (%d bytes)" % (path, len(out))}
        return {"kind": "unset"} if val is None else {"kind": "value", "value": val}
    if _UNSET_RE.search("%s\n%s" % (out, err)):
        return {"kind": "unset"}
    return {"kind": "error", "detail": "config get %s: rc=%s %s"
            % (path, rc, _first_line(out or err))}


def list_agent_ids(binary):
    """(ids, problems). A listing that fails or has an unknown shape is a PROBLEM,
    so the verdict cannot come out 'ok' on a guess."""
    rc, out, err = _ro(binary, ["agents", "list", "--json"])
    if rc != 0:
        return [], ["agents list --json: rc=%s %s" % (rc, _first_line(out or err))]
    try:
        data = _parse(out)
    except ValueError:
        return [], ["agents list --json: stdout is not JSON (%d bytes)" % len(out)]
    if isinstance(data, dict):
        data = data.get("agents")
    if not isinstance(data, list):
        return [], ["agents list --json: unexpected shape (no agent list)"]
    ids, problems = [], []
    for item in data:
        aid = item if isinstance(item, str) else (
            (item.get("id") or item.get("agentId")) if isinstance(item, dict) else None)
        if isinstance(aid, str) and _ID_RE.match(aid):
            ids.append(aid)
        else:
            problems.append("agents list --json: an agent id is missing or not path-safe")
    return sorted(set(ids)), sorted(set(problems))


# --------------------------------------------------------------------------- #
# the verdict (pure)
# --------------------------------------------------------------------------- #
def _enabled(value):
    """loopDetection value -> True / False / None (no `enabled` key). ValueError on
    any shape we do not understand - that is UNDETERMINED, not 'off'."""
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        if "enabled" not in value:
            return None
        if isinstance(value["enabled"], bool):
            return value["enabled"]
    raise ValueError("unexpected loopDetection shape")


def evaluate(g, agent_reads, problems=()):
    """g / agent_reads values are read_path() results. Returns the verdict dict.
    effective(agent) = per-agent override if present, else the global value."""
    und = list(problems)
    off = []
    gen = gprior = None
    if g["kind"] == "unset":
        gen, gprior = False, "unset"          # documented default: disabled
    elif g["kind"] == "value":
        try:
            e = _enabled(g["value"])
            gen = bool(e)                     # no `enabled` key -> default false
            gprior = "unset" if e is None else str(e).lower()
        except ValueError as exc:
            und.append("global: %s" % exc)
    else:
        und.append(g["detail"])
    if gen is False:
        off.append("global")

    agents = {}
    for aid, r in sorted(agent_reads.items()):
        ov, prior = None, "unset"
        if r["kind"] == "value":
            try:
                ov = _enabled(r["value"])
                prior = "unset" if ov is None else str(ov).lower()
            except ValueError as exc:
                und.append("agent %s: %s" % (aid, exc))
                agents[aid] = {"override": prior, "effective": None}
                continue
        elif r["kind"] == "error":
            und.append(r["detail"])
            agents[aid] = {"override": "unreadable", "effective": None}
            continue
        eff = ov if ov is not None else gen
        agents[aid] = {"override": prior, "effective": eff}
        if eff is False and ov is False:
            off.append("agent:%s" % aid)
    inheriting_off = sorted(a for a, v in agents.items()
                            if v["effective"] is False and v["override"] != "false")
    warn = gen is False or any(v["effective"] is False for v in agents.values())
    verdict = "warn" if warn else ("undetermined" if und else "ok")
    return {"verdict": verdict, "global": {"enabled": gen, "prior": gprior},
            "agents": agents, "off": off, "inheriting_off": inheriting_off,
            "undetermined": und}


def prepared_fix(res):
    """Tier 2, PREPARED ONLY. Text for an operator to run on-box; revert = prior
    value. Nothing here is ever executed by this module."""
    def cmd(*a):
        return shlex.join(["openclaw"] + list(a))

    def setb(path, val):
        return cmd("config", "set", path + ".enabled", val, "--strict-json")

    steps = []
    if res["global"]["enabled"] is False:
        prior = res["global"]["prior"]
        steps.append({"target": "global", "apply": setb(GLOBAL_PATH, "true"),
                      "revert": cmd("config", "unset", GLOBAL_PATH + ".enabled")
                      if prior == "unset" else setb(GLOBAL_PATH, prior)})
    for aid, v in sorted(res["agents"].items()):
        if v["override"] == "false":
            p = AGENT_PATH % aid
            steps.append({"target": "agent:%s" % aid, "apply": setb(p, "true"),
                          "revert": setb(p, "false")})
    return steps


def describe(res):
    """One honest paragraph for the finding / the terminal."""
    bits = []
    g = res["global"]
    if g["enabled"] is False:
        bits.append("global tools.loopDetection.enabled is %s (default is off)" % g["prior"])
    for a in res["off"]:
        if a.startswith("agent:"):
            bits.append("agent %s overrides it to false" % a[6:])
    if res["inheriting_off"]:
        bits.append("%d agent(s) inherit the off value" % len(res["inheriting_off"]))
    txt = "native guard off: " + "; ".join(bits) if bits else "native guard off"
    fixes = prepared_fix(res)
    if fixes:
        txt += (" | PREPARED, Tier 2, NOT applied: " + " ; ".join(s["apply"] for s in fixes)
                + " | revert (prior value): " + " ; ".join(s["revert"] for s in fixes))
    if res["undetermined"]:
        txt += " | also UNDETERMINED: " + " ; ".join(res["undetermined"])
    return txt


def resolve_binary():
    """(binary|None, probed, hermetic_skip). Under LOOP_NO_PROBES=1 with no explicit
    $LOOP_OPENCLAW_BIN the real gateway is unreachable by design."""
    if (os.environ.get("LOOP_NO_PROBES", "") == "1"
            and not os.environ.get("LOOP_OPENCLAW_BIN", "").strip()):
        return None, ["skipped: LOOP_NO_PROBES=1 and no $LOOP_OPENCLAW_BIN"], True
    b, probed = CR.find_openclaw()
    return b, probed, False


def run_check(binary):
    g = read_path(binary, GLOBAL_PATH)
    ids, problems = list_agent_ids(binary)
    reads = {i: read_path(binary, AGENT_PATH % i) for i in ids}
    res = evaluate(g, reads, problems)
    res["agent_ids"] = ids
    res["prepared_fix"] = prepared_fix(res)
    return res


def _unresolved(probed):
    return {"verdict": "undetermined", "global": {"enabled": None, "prior": None},
            "agents": {}, "off": [], "inheriting_off": [], "agent_ids": [],
            "prepared_fix": [], "undetermined": [
                "no `openclaw` binary resolved (probed: %s) - a RESOLUTION failure, "
                "not a statement about the guard" % " | ".join(probed)]}


# --------------------------------------------------------------------------- #
# the daily hook (ledger-stamped, like last_tick_ts)
# --------------------------------------------------------------------------- #
def _age_hours(led, key):
    dt = C.parse_iso8601(led.get_meta(key))
    if dt is None:
        return None
    age = (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
    return None if age < 0 else age       # a future stamp (clock skew) never blocks


def _due(led):
    run, attempt = _age_hours(led, META_RUN), _age_hours(led, META_ATTEMPT)
    if run is not None and run < CADENCE_HOURS:
        return False
    return not (attempt is not None and attempt < RETRY_HOURS)


def tick_hook():
    """Never raises, never changes the tick's exit code (caller also `|| true`)."""
    try:
        led = Ledger()
        try:
            if not _due(led):
                return EX_OK
            binary, probed, skipped = resolve_binary()
            if skipped:
                return EX_OK
            res = _unresolved(probed) if binary is None else run_check(binary)
            if res["verdict"] == "warn":
                led.record_finding(LOOP_CLASS, "WARN", unit="native-guard",
                                   detail=describe(res), tier=2, dedup_key=DEDUP_KEY)
                led.set_meta(META_RUN, now_utc())
                sys.stderr.write("WARN [check_native_loop_guard]: %s\n" % describe(res))
            elif res["verdict"] == "ok":
                for row in led.open_findings(LOOP_CLASS):
                    led.set_finding_state(row["finding_id"], "resolved")
                led.set_meta(META_RUN, now_utc())
            else:
                led.set_meta(META_ATTEMPT, now_utc())
                sys.stderr.write("UNDETERMINED [check_native_loop_guard]: %s (retry in %dh)\n"
                                 % (" ; ".join(res["undetermined"]), RETRY_HOURS))
        finally:
            led.close()
    except Exception as exc:  # noqa: BLE001 - reported, and the tick still lives
        sys.stderr.write("ERROR [check_native_loop_guard]: hook failed (%s: %s); tick "
                         "unaffected\n" % (type(exc).__name__, exc))
    return EX_OK


# --------------------------------------------------------------------------- #
# stub gateway + self-test (offline, hermetic)
# --------------------------------------------------------------------------- #
_STUB = r"""#!/usr/bin/env bash
# Stub `openclaw` for check_native_loop_guard tests. Logs every argv; answers ONLY
# `config get` and `agents list`; refuses anything else with rc 9 (and logs it, so a
# test can PROVE no config set/unset was ever attempted).
echo "$*" >> "${STUB_LOG:?STUB_LOG required}"
mode_json() {
  case "$1" in
    unset) echo "{\"ok\": false, \"error\": {\"type\": \"cli_error\", \"message\": \"Unknown config path: $2. Run openclaw config schema\"}}"; return 1 ;;
    unset2) echo "Config path not found: $2. Nothing was changed." >&2; return 1 ;;
    false) echo '{"enabled": false}' ;;
    true) echo '{"enabled": true}' ;;
    empty) echo '{}' ;;
    maintenance) echo '{"ok": false, "error": {"type": "cli_error", "message": "OpenClaw config could not be read: ~/.openclaw/openclaw.json"}, "issues": [{"path": "<root>", "message": "read failed: Error: OpenClaw state is undergoing offline maintenance; retry when it finishes."}]}'; return 1 ;;
    garbage) echo 'definitely not json' ;;
    *) echo "stub: bad mode $1" >&2; return 9 ;;
  esac
}
case "$1 $2" in
  "config get")
    p="$3"
    case "$p" in
      tools.loopDetection) mode_json "${STUB_GLOBAL:-unset}" "$p" ;;
      agents.entries.*.tools.loopDetection)
        id="${p#agents.entries.}"; id="${id%.tools.loopDetection}"
        var="STUB_AGENT_${id//-/_}"; mode_json "${!var:-unset}" "$p" ;;
      *) echo "stub: unexpected path $p" >&2; exit 9 ;;
    esac ;;
  "agents list") if [ "${STUB_AGENTS:-}" = "FAIL" ]; then echo "boom" >&2; exit 1; fi
                 echo "${STUB_AGENTS:-[]}" ;;
  *) echo "stub: REFUSED $*" >&2; exit 9 ;;
esac
"""


def _write_stub(path):
    Path(path).write_text(_STUB, encoding="utf-8")
    os.chmod(path, 0o755)


def _self_test():
    td = tempfile.mkdtemp(prefix="loop-nativeguard-")
    fails = []

    def check(name, cond):
        print("  %s: %s" % ("PASS" if cond else "FAIL", name))
        if not cond:
            fails.append(name)

    saved = {k: os.environ.get(k) for k in (
        "LOOP_OPENCLAW_BIN", "LOOP_STATE_DIR", "LOOP_NO_PROBES", "STUB_LOG",
        "STUB_GLOBAL", "STUB_AGENTS")}
    try:
        stub = os.path.join(td, "openclaw")
        log = os.path.join(td, "calls.log")
        _write_stub(stub)
        os.environ.update(LOOP_OPENCLAW_BIN=stub, LOOP_STATE_DIR=os.path.join(td, "state"),
                          STUB_LOG=log)
        for k in [k for k in os.environ if k.startswith("STUB_AGENT_")]:
            del os.environ[k]
        os.environ["LOOP_NO_PROBES"] = "1"      # explicit bin still honoured

        def run(glob, agents="[]", **per_agent):
            os.environ["STUB_GLOBAL"], os.environ["STUB_AGENTS"] = glob, agents
            for k in [k for k in os.environ if k.startswith("STUB_AGENT_")]:
                del os.environ[k]
            for aid, mode in per_agent.items():
                os.environ["STUB_AGENT_" + aid] = mode
            return run_check(stub)

        # 1. the three shapes, global only: unset / false / true = WARN / WARN / ok
        check("shape unset -> WARN", run("unset")["verdict"] == "warn")
        check("shape unset (alt message) -> WARN", run("unset2")["verdict"] == "warn")
        check("shape false -> WARN", run("false")["verdict"] == "warn")
        check("shape {} (no enabled key) -> WARN", run("empty")["verdict"] == "warn")
        check("shape true -> ok", run("true")["verdict"] == "ok")

        # 2. effective value = per-agent override, else global
        ag = '[{"id": "alpha"}, {"id": "beta"}]'
        check("global on, no overrides -> ok", run("true", ag)["verdict"] == "ok")
        check("global on, override {} inherits -> ok",
              run("true", ag, alpha="empty")["verdict"] == "ok")
        check("global on, override true -> ok",
              run("true", ag, alpha="true", beta="true")["verdict"] == "ok")
        r = run("true", ag, beta="false")
        check("global on, one agent override false -> WARN naming it",
              r["verdict"] == "warn" and r["off"] == ["agent:beta"])
        r = run("false", ag, alpha="true")
        check("global off, alpha override true, beta inherits off -> WARN",
              r["verdict"] == "warn" and r["inheriting_off"] == ["beta"]
              and r["agents"]["alpha"]["effective"] is True)
        check("agent id list as bare strings parses",
              run("true", '["alpha", "beta"]')["agent_ids"] == ["alpha", "beta"])
        check("agents wrapped in {agents: [...]} parses",
              run("true", '{"agents": [{"id": "alpha"}]}')["agent_ids"] == ["alpha"])

        # 3. a failed read is UNDETERMINED - never ok, never off
        check("offline maintenance (real captured shape) -> undetermined",
              run("maintenance")["verdict"] == "undetermined")
        check("maintenance detail carries the real message, not a bare '{'",
              "offline maintenance" in " ".join(run("maintenance")["undetermined"]))
        check("rc 0 non-JSON -> undetermined", run("garbage")["verdict"] == "undetermined")
        check("agent read fails -> undetermined",
              run("true", ag, alpha="maintenance")["verdict"] == "undetermined")
        check("agents list fails -> undetermined, not ok",
              run("true", "FAIL")["verdict"] == "undetermined")
        check("agents list wrong shape -> undetermined",
              run("true", '"nope"')["verdict"] == "undetermined")
        check("path-unsafe agent id -> undetermined",
              run("true", '[{"id": "a.b"}]')["verdict"] == "undetermined")
        check("proven off beats an unreadable agent",
              run("false", ag, alpha="maintenance")["verdict"] == "warn")

        # 4. prepared fix: text only, revert = prior value
        fx = {s["target"]: s for s in run("unset")["prepared_fix"]}
        check("global fix is the spec command",
              fx["global"]["apply"] ==
              "openclaw config set tools.loopDetection.enabled true --strict-json")
        check("unset prior -> revert is `config unset`",
              fx["global"]["revert"] == "openclaw config unset tools.loopDetection.enabled")
        fx = {s["target"]: s for s in run("false", ag, beta="false")["prepared_fix"]}
        check("false prior -> revert re-sets false",
              fx["global"]["revert"] ==
              "openclaw config set tools.loopDetection.enabled false --strict-json")
        check("agent override false -> per-agent fix reverts to false",
              fx["agent:beta"]["apply"].startswith(
                  "openclaw config set agents.entries.beta.tools.loopDetection.enabled true")
              and fx["agent:beta"]["revert"].endswith("false --strict-json"))
        check("ok verdict prepares nothing", run("true", ag)["prepared_fix"] == [])

        # 5. nothing mutating is reachable
        try:
            _ro(stub, ["config", "set", "tools.loopDetection.enabled", "true"])
            check("_ro refuses config set", False)
        except RuntimeError:
            check("_ro refuses config set", True)
        try:
            _ro(stub, ["config", "unset", "tools.loopDetection.enabled"])
            check("_ro refuses config unset", False)
        except RuntimeError:
            check("_ro refuses config unset", True)
        calls = Path(log).read_text().splitlines()
        check("stub log: only `config get` / `agents list` ever ran (no set/unset/other)",
              calls and all(c.startswith(("config get ", "agents list")) for c in calls))
        src = Path(__file__).read_text()
        check("source carries no shell-out of config set",
              "subprocess.run" not in src.split("# stub gateway")[0].replace(
                  "import subprocess", ""))

        # 6. daily cadence + ledger finding (stamp like last_tick_ts)
        def hook():
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                rc = tick_hook()
            return rc, buf.getvalue()

        def ncalls():
            return len(Path(log).read_text().splitlines())

        def led_do(fn):
            led = Ledger()
            try:
                return fn(led)
            finally:
                led.close()

        os.environ["STUB_GLOBAL"], os.environ["STUB_AGENTS"] = "unset", "[]"
        base = ncalls()
        rc, err = hook()
        check("hook: WARN reported on stderr, rc 0",
              rc == 0 and "native guard off" in err and "NOT applied" in err)
        check("hook: one open WARN finding, tier 2",
              led_do(lambda L: [(r["severity"], r["loop_class"]) for r in L.open_findings(LOOP_CLASS)])
              == [("WARN", LOOP_CLASS)])
        n1 = ncalls()
        check("hook: first run probed the box", n1 > base)
        rc, err = hook()
        check("hook: second run within 24h is skipped (no probes, silent)",
              rc == 0 and ncalls() == n1 and err == "")
        old = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        led_do(lambda L: L.set_meta(META_RUN, old))
        hook()
        check("hook: runs again after 24h", ncalls() > n1)
        check("hook: repeat WARN dedups to ONE finding",
              led_do(lambda L: len(L.open_findings(LOOP_CLASS))) == 1)
        os.environ["STUB_GLOBAL"] = "true"
        led_do(lambda L: L.set_meta(META_RUN, old))
        rc, err = hook()
        check("hook: ok is silent and resolves the open finding",
              rc == 0 and err == "" and led_do(lambda L: len(L.open_findings(LOOP_CLASS))) == 0)
        os.environ["STUB_GLOBAL"] = "maintenance"
        led_do(lambda L: L.set_meta(META_RUN, old))
        rc, err = hook()
        check("hook: UNDETERMINED reported, rc 0", rc == 0 and "UNDETERMINED" in err)
        n2 = ncalls()
        hook()
        check("hook: failed read does not re-probe inside 1h", ncalls() == n2)
        led_do(lambda L: L.set_meta(META_ATTEMPT,
               (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()))
        hook()
        check("hook: failed read retries after 1h (not 24h)", ncalls() > n2)
        led_do(lambda L: L.set_meta(META_RUN, (datetime.now(timezone.utc)
                                               + timedelta(days=400)).isoformat()))
        led_do(lambda L: L.set_meta(META_ATTEMPT, old))
        n3 = ncalls()
        hook()
        check("hook: a future-dated stamp never blocks the check", ncalls() > n3)
        os.environ.pop("LOOP_OPENCLAW_BIN")
        n4 = ncalls()
        led_do(lambda L: L.set_meta(META_RUN, old))
        led_do(lambda L: L.set_meta(META_ATTEMPT, old))
        rc, err = hook()
        check("hook: LOOP_NO_PROBES=1 with no explicit bin never reaches a gateway",
              rc == 0 and err == "" and ncalls() == n4)
        calls = Path(log).read_text().splitlines()
        check("stub log still shows no mutating call after the hook paths",
              all(c.startswith(("config get ", "agents list")) for c in calls))
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        for k in [k for k in os.environ if k.startswith("STUB_AGENT_")]:
            del os.environ[k]
        shutil.rmtree(td, ignore_errors=True)
    if fails:
        sys.stderr.write("[check_native_loop_guard] self-test FAIL: %d case(s): %s\n"
                         % (len(fails), "; ".join(fails)))
        return EX_ERR
    print("[check_native_loop_guard] self-test: PASS")
    return EX_OK


def _cli(argv=None):
    ap = argparse.ArgumentParser(
        prog="check_native_loop_guard.py",
        description="Read-only: is OpenClaw's native tool-loop guard on?")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--emit-stub", metavar="PATH", help=argparse.SUPPRESS)  # tests only
    sub = ap.add_subparsers(dest="cmd")
    sp = sub.add_parser("check", help="read and report now (read-only)")
    sp.add_argument("--json", action="store_true")
    sub.add_parser("tick-hook", help="daily-gated check from the watchdog tick; exit 0")
    a = ap.parse_args(argv)
    if a.emit_stub:
        _write_stub(a.emit_stub)
        return EX_OK
    if a.self_test:
        return _self_test()
    if a.cmd == "tick-hook":
        return tick_hook()
    if a.cmd != "check":
        ap.error("a subcommand is required (or --self-test)")
    binary, probed, _skipped = resolve_binary()
    res = _unresolved(probed) if binary is None else run_check(binary)
    if a.json:
        print(json.dumps(res, sort_keys=True))
    elif res["verdict"] == "warn":
        print("WARN: " + describe(res))
    elif res["verdict"] == "undetermined":
        print("UNDETERMINED: " + " ; ".join(res["undetermined"]))
    else:
        print("ok: native loop guard enabled for global and %d agent(s)"
              % len(res["agent_ids"]))
    return {"ok": EX_OK, "warn": EX_FINDINGS}.get(res["verdict"], EX_UNDETERMINED)


if __name__ == "__main__":
    sys.exit(_cli())
