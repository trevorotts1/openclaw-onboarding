#!/usr/bin/env python3
"""Skill 38 inbound-hooks auto-repair for boxes that installed Skill 38 before v2.0.9.

Runs from the shared front door (shared-utils/oct4_frontdoor.py) after every update, so
no one re-runs Skill 38 setup. Only touches a box whose hooks are ALREADY enabled:
  a) removes hooks.maxBodyBytes   (OpenClaw 2026.9.x rejects it: config INVALID)
  b) sets gateway.trustedProxies  (only when unset/empty; else 403 proxy_attribution_required)
  c) REWRITES a hooks.mappings body that diverges from the required shape, including
     REBINDING an agentId that is not a configured agent, and reports one line per
     changed key plus the agentId old -> new pair (G-01/G-02: before v2.0.24 a stale
     agentId was reported and never rebound, and a pre-upgrade body with nested
     sessionKey tokens and no send-directive / conversation-log directives survived
     forever)
Never enables hooks, adds mappings, creates tokens or prints secret values.
The pre-change mapping body is backed up next to the config before any rewrite, the
config is replaced by an atomic rename, and the run REFUSES to write when the file
changed under it.
Exit: 0 ok (INCLUDING a successful rewrite), 1 failed (validate rejected; backup
      restored), 2 needs-attention, 5 cannot-verify (unreadable, or the config
      changed under this run).
Fixture hook: S38_REPAIR_LIB points at a stub lib-docker-tenant.sh.
"""
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

def oc_root():
    env = os.environ.get("OPENCLAW_ROOT", "").strip()
    if env:
        return Path(env)
    if Path("/data/.openclaw").is_dir():
        return Path("/data/.openclaw")
    return Path.home() / ".openclaw"

def _lib():
    return os.environ.get("S38_REPAIR_LIB") or str(HERE.parent / "lib-docker-tenant.sh")

def _sh(script, *args):
    """Run a lib-docker-tenant.sh function ($1 = the lib, $2.. = its args)."""
    lib = _lib()
    if not Path(lib).is_file():
        return None
    return subprocess.run(["bash", "-c", '. "$1" && ' + script, "_", lib] + list(args),
                          capture_output=True, text=True)

def proxies():
    """Reuse the install-time detection (lib-docker-tenant.sh) so both paths agree."""
    r = _sh("s38_trusted_proxies")
    if r is None:
        return None
    out = [x.strip() for x in r.stdout.splitlines() if x.strip()]
    return out if r.returncode == 0 and out else None

def routing_agent(cfg_path, ids):
    """The agent a stale agentId is rebound to: the shared routing rule first,
    and only when that cannot resolve, the box's single configured agent."""
    r = _sh('s38_resolve_routing_agent "$2"', str(cfg_path))
    if r is not None and r.returncode == 0:
        out = r.stdout.strip()
        if out in ids:
            return out
    if len(ids) == 1:
        return next(iter(sorted(ids)))
    return None

def migrate_mapping_body(cfg_path, mapping):
    """Full content-addressed migration through lib-docker-tenant.sh (single source
    of the canonical body). Returns {"mapping":…, "changedKeys":[…]} or None."""
    if not mapping.get("id"):
        return None
    r = _sh('s38_migrate_mapping "$2" "$3" "$4"', str(cfg_path), json.dumps(mapping),
            json.dumps(sorted(_IDS)))
    if r is None or r.returncode != 0:
        return None
    try:
        out = json.loads(r.stdout.strip())
    except ValueError:
        return None
    return out if isinstance(out, dict) and "mapping" in out else None

_IDS = set()

def oc_cli(root):
    """The CLI is often not on the updater's PATH (docker tenants keep it under npm-global)."""
    for c in (os.environ.get("OC_CLI", ""), shutil.which("openclaw") or "",
              str(root / "npm-global" / "bin" / "openclaw")):
        if c and os.access(c, os.X_OK):
            return c
    return None

def repair(cfg, cfg_path):
    """Mutates cfg. Returns (changes, attention, backups), or (None, None, None)
    when out of scope. backups is [(mapping-id, pre-change body)]."""
    changes, attention, backups = [], [], []
    hooks = cfg.get("hooks")
    if not isinstance(hooks, dict) or hooks.get("enabled") is not True:
        return None, None, None
    if "maxBodyBytes" in hooks:
        del hooks["maxBodyBytes"]
        changes.append("remove hooks.maxBodyBytes")
    gw = cfg.get("gateway")
    if not isinstance(gw, dict):
        gw = {}
    if not gw.get("trustedProxies"):
        p = proxies()
        if p:
            gw["trustedProxies"] = p
            cfg["gateway"] = gw
            changes.append("set gateway.trustedProxies=%s" % p)
        else:
            attention.append("gateway.trustedProxies unset and the proxy hop could not be detected")
    ag = cfg.get("agents") or {}
    ids = set((ag.get("entries") or {}).keys()) | {
        a.get("id") for a in (ag.get("list") or []) if isinstance(a, dict)}
    ids.discard(None)
    global _IDS
    _IDS = set(ids)
    if ids:
        for i, m in enumerate(hooks.get("mappings") or []):
            if not isinstance(m, dict):
                continue
            before = json.loads(json.dumps(m))   # the pre-change body, kept verbatim
            res = migrate_mapping_body(cfg_path, m)
            if res is not None:
                new, changed = res.get("mapping") or {}, list(res.get("changedKeys") or [])
            else:
                # No canonical body available (id-less mapping, or the lib/jq is
                # absent): still rebind a stale agentId rather than only report it.
                new, changed = dict(before), []
                aid = new.get("agentId")
                if aid and aid not in ids:
                    tgt = routing_agent(cfg_path, ids)
                    if tgt:
                        new["agentId"] = tgt
                        changed.append("agentId")
                    else:
                        attention.append(
                            "hooks mapping %r agentId %r is not a configured agent and no "
                            "rebind target could be resolved — set ROUTING_AGENT_ID to one of %s"
                            % (new.get("id"), aid, sorted(ids)))
                        continue
                else:
                    continue
            if not changed:
                continue
            hooks["mappings"][i] = new
            backups.append((before.get("id") or ("index-%d" % i), before))
            mid = before.get("id") or ("index-%d" % i)
            # PER-KEY REPORTING: one line per changed key, plus the agentId
            # old -> new pair. A rewrite that succeeded reports SUCCESS — exit 2
            # is reserved for work that genuinely needs attention.
            changes.append("hooks mapping %s: rewrite body" % mid)
            for k in changed:
                if k == "agentId":
                    changes.append("hooks mapping %s: changed key: agentId %r -> %r"
                                   % (mid, before.get("agentId"), new.get("agentId")))
                else:
                    changes.append("hooks mapping %s: changed key: %s" % (mid, k))
            if "agentId" not in changed:
                changes.append("hooks mapping %s: agentId %r -> %r (unchanged)"
                               % (mid, before.get("agentId"), new.get("agentId")))
    return changes, attention, backups

def run(root, dry):
    path = root / "openclaw.json"
    try:
        st_before = path.stat()
        cfg = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        print("skill38 inbound hooks: cannot read %s: %s" % (path, type(e).__name__), file=sys.stderr)
        return 5
    changes, attention, backups = repair(cfg, path)
    if changes is None:
        print("skill38 inbound hooks not configured on this box; nothing to repair")
        return 0
    for c in changes:
        print(("would " if dry else "") + c)
    for a in attention:
        print("NEEDS ATTENTION: " + a)
    if changes and not dry:
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        for mid, body in backups:
            mk = path.with_name("openclaw.json.hooks-mapping-%s.bak-%s.json" % (mid, ts))
            mk.write_text(json.dumps(body, indent=2) + "\n")
            os.chmod(str(mk), 0o600)
            print("backed up pre-change mapping %s -> %s" % (mid, mk.name))
        bak = path.with_name("openclaw.json.bak-skill38-repair-" + ts)
        shutil.copy2(path, bak)
        fd, tmp = tempfile.mkstemp(dir=str(root), prefix=".openclaw.json.")
        with os.fdopen(fd, "w") as f:
            json.dump(cfg, f, indent=2)
            f.write("\n")
        shutil.copymode(path, tmp)
        st = path.stat()
        if os.geteuid() == 0:  # a root-owned config freezes a gateway running as the box user
            os.chown(tmp, st.st_uid, st.st_gid)
        # Refuse to clobber a file that changed while we worked on it.
        try:
            st_now = path.stat()
        except OSError:
            os.unlink(tmp)
            print("skill38 inbound hooks: %s vanished under this run; nothing written" % path,
                  file=sys.stderr)
            return 5
        if (st_now.st_mtime_ns, st_now.st_size) != (st_before.st_mtime_ns, st_before.st_size):
            os.unlink(tmp)
            print("REFUSED: %s changed under this repair run (another writer touched it while "
                  "we worked) — leaving it untouched. Re-run." % path, file=sys.stderr)
            return 5
        os.replace(tmp, path)
        cli = oc_cli(root)
        if cli:
            v = subprocess.run([cli, "config", "validate"], capture_output=True, text=True)
            if v.returncode != 0:
                shutil.copy2(bak, path)
                print("config validate failed; restored %s" % bak.name, file=sys.stderr)
                return 1
        else:
            print("NOTE: openclaw CLI not found; change written without validation", file=sys.stderr)
    return 2 if attention else 0

def selftest():
    T = Path(tempfile.mkdtemp())
    me = os.path.abspath(__file__)

    def go(name, cfg, lib="docker", dry=False, stub=None, agents=None):
        d = T / name
        d.mkdir()
        (d / "openclaw.json").write_text(json.dumps(cfg))
        (d / "lib.sh").write_text("s38_trusted_proxies(){ %s; }\n"
                                 "s38_resolve_routing_agent(){ %s; }\n"
                                 "s38_migrate_mapping(){ return 1; }\n" % (
            "echo 172.19.0.1" if lib == "docker" else "printf '127.0.0.1\\n::1\\n'",
            "echo ${FIXED_ROUTER:-dept-communications}"))
        # Always a stub CLI: never validate the real config of the machine running the test.
        (d / "bin").mkdir()
        (d / "bin" / "openclaw").write_text("#!/bin/sh\nexit %d\n" % (stub or 0))
        (d / "bin" / "openclaw").chmod(0o755)
        env = dict(os.environ, OPENCLAW_ROOT=str(d), S38_REPAIR_LIB=str(d / "lib.sh"),
                   OC_CLI=str(d / "bin" / "openclaw"))
        r = subprocess.run([sys.executable, me] + (["--dry-run"] if dry else []), env=env,
                           capture_output=True, text=True)
        return r.returncode, json.loads((d / "openclaw.json").read_text()), d, r

    def on():
        return {"enabled": True, "token": "s3cret", "maxBodyBytes": 5, "mappings": [{"agentId": "a"}]}
    agents = {"entries": {"a": {}}}
    baks = lambda d: list(d.glob("*.bak-skill38-repair-*"))
    mbaks = lambda d: list(d.glob("*.hooks-mapping-*.json"))
    rc, c, d, r = go("off", {"hooks": {"enabled": False}})
    assert rc == 0 and "gateway" not in c and not baks(d)
    rc, c, d, r = go("dock", {"hooks": on(), "agents": agents})
    assert rc == 0 and "maxBodyBytes" not in c["hooks"] and c["gateway"]["trustedProxies"] == ["172.19.0.1"]
    assert "s3cret" not in r.stdout + r.stderr and len(baks(d)) == 1
    again = subprocess.run([sys.executable, me], env=dict(os.environ, OPENCLAW_ROOT=str(d),
                           S38_REPAIR_LIB=str(d / "lib.sh"), OC_CLI=str(d / "bin" / "openclaw")),
                           capture_output=True, text=True)
    assert again.returncode == 0 and len(baks(d)) == 1, "second run must be a no-op"
    rc, c, d, r = go("host", {"hooks": on(), "agents": agents}, lib="host")
    assert c["gateway"]["trustedProxies"] == ["127.0.0.1", "::1"]
    rc, c, d, r = go("keep", {"hooks": on(), "agents": agents, "gateway": {"trustedProxies": ["10.0.0.1"]}})
    assert c["gateway"]["trustedProxies"] == ["10.0.0.1"]

    # G-02: a stale agentId is REBOUND, not merely reported. One configured agent
    # is the unambiguous rebind target.
    rc, c, d, r = go("agent", {"hooks": {"enabled": True, "mappings": [{"agentId": "zz"}]},
                               "agents": agents, "gateway": {"trustedProxies": ["1.1.1.1"]}})
    assert c["hooks"]["mappings"][0]["agentId"] == "a", "stale agentId must be rebound"
    assert rc == 0 and not r.stdout.startswith("NEEDS ATTENTION"), rc
    assert any("agentId" in line for line in r.stdout.splitlines()), r.stdout
    assert baks(d) and mbaks(d), "pre-change mapping and config must be backed up"

    # ... and when no rebind target exists it says so instead of guessing.
    rc, c, d, r = go("agent2", {"hooks": {"enabled": True, "mappings": [{"agentId": "zz"}]},
                                "agents": {"entries": {"x": {}, "y": {}}},
                                "gateway": {"trustedProxies": ["1.1.1.1"]}}, stub=0)
    assert rc == 2 and c["hooks"]["mappings"][0]["agentId"] == "zz", "must not guess between agents"
    assert "ROUTING_AGENT_ID" in r.stdout

    rc, c, d, r = go("dry", {"hooks": on(), "agents": agents}, dry=True)
    assert "maxBodyBytes" in c["hooks"] and not baks(d)
    rc, c, d, r = go("bad", {"hooks": on(), "agents": agents}, stub=1)
    assert rc == 1 and "maxBodyBytes" in c["hooks"] and "gateway" not in c
    rc, c, d, r = go("good", {"hooks": on(), "agents": agents}, stub=0)
    assert rc == 0 and "maxBodyBytes" not in c["hooks"]
    nofile = subprocess.run([sys.executable, me], env=dict(os.environ, OPENCLAW_ROOT=str(T / "none")),
                            capture_output=True, text=True)
    assert nofile.returncode == 5

    # The real lib-docker-tenant.sh path: a full body migration, run twice.
    lib = os.environ.get("S38_FIXTURE_LIB") or str(HERE.parent / "lib-docker-tenant.sh")
    if Path(lib).is_file() and shutil.which("jq") and shutil.which("bash"):
        d = T / "body"
        d.mkdir()
        body = {"id": "hook-ghl-sms", "match": {"path": "hook-ghl-sms"}, "action": "agent",
                "agentId": "retired-bot", "wakeMode": "now", "name": "GHL Inbound",
                "sessionKey": "{{contact.id}}",
                "messageTemplate": "INBOUND MESSAGE FROM GOHIGHLEVEL — Contact ID: {{contact_id}} "
                                   "Customer message body: {{message_body}}. Reply to the customer.",
                "deliver": False, "timeoutSeconds": 900}
        cfg = {"agents": {"entries": {"dept-communications": {}, "main": {}}},
               "hooks": {"enabled": True, "mappings": [body]}}
        (d / "openclaw.json").write_text(json.dumps(cfg))
        (d / "bin").mkdir()
        (d / "bin" / "openclaw").write_text("#!/bin/sh\nexit 0\n")
        (d / "bin" / "openclaw").chmod(0o755)
        env = dict(os.environ, OPENCLAW_ROOT=str(d), S38_REPAIR_LIB=lib,
                   OC_CLI=str(d / "bin" / "openclaw"), ROUTING_AGENT_ID="")
        r = subprocess.run([sys.executable, me], env=env, capture_output=True, text=True)
        got = json.loads((d / "openclaw.json").read_text())["hooks"]["mappings"][0]
        assert got["agentId"] == "dept-communications", got["agentId"]
        assert got["sessionKey"] == "{{session_key}}", got["sessionKey"]
        assert "MANDATORY" in got["messageTemplate"] and "conversational-logs" in got["messageTemplate"]
        assert got["timeoutSeconds"] == 900, "operator value must survive"
        assert "changed key: agentId 'retired-bot' -> 'dept-communications'" in r.stdout, r.stdout
        assert "changed key: messageTemplate" in r.stdout, r.stdout
        assert "changed key: sessionKey" in r.stdout, r.stdout
        assert "NEEDS ATTENTION" not in r.stdout, r.stdout
        assert mbaks(d) and json.loads(mbaks(d)[0].read_text())["agentId"] == "retired-bot"
        r2 = subprocess.run([sys.executable, me], env=env, capture_output=True, text=True)
        assert r2.returncode == 0 and "rewrite body" not in r2.stdout, r2.stdout
        assert len(mbaks(d)) == 1, "second run must write no second mapping backup"

        # A SUCCESSFUL rewrite whose agentId needs no rebind reports success and
        # exits 0 — never "NEEDS ATTENTION" exit 2.
        d2 = T / "body2"
        d2.mkdir()
        body2 = dict(body, agentId="dept-communications")
        cfg2 = {"agents": {"entries": {"dept-communications": {}, "main": {}}},
                "hooks": {"enabled": True, "mappings": [body2]}}
        (d2 / "openclaw.json").write_text(json.dumps(cfg2))
        (d2 / "bin").mkdir()
        (d2 / "bin" / "openclaw").write_text("#!/bin/sh\nexit 0\n")
        (d2 / "bin" / "openclaw").chmod(0o755)
        env2 = dict(os.environ, OPENCLAW_ROOT=str(d2), S38_REPAIR_LIB=lib,
                    OC_CLI=str(d2 / "bin" / "openclaw"), ROUTING_AGENT_ID="")
        r3 = subprocess.run([sys.executable, me], env=env2, capture_output=True, text=True)
        got2 = json.loads((d2 / "openclaw.json").read_text())["hooks"]["mappings"][0]
        assert r3.returncode == 0, "successful rewrite must not report needs-attention: %s" % r3.stdout
        assert "NEEDS ATTENTION" not in r3.stdout, r3.stdout
        assert got2["agentId"] == "dept-communications", got2["agentId"]
        assert got2["sessionKey"] == "{{session_key}}", got2["sessionKey"]
        assert "changed key: messageTemplate" in r3.stdout and "changed key: sessionKey" in r3.stdout, r3.stdout
        assert "agentId 'dept-communications' -> 'dept-communications' (unchanged)" in r3.stdout, r3.stdout

    shutil.rmtree(T)
    print("selftest ok")
    return 0

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    sys.exit(run(oc_root(), "--dry-run" in sys.argv))
