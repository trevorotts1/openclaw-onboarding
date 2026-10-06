#!/usr/bin/env python3
"""Skill 38 inbound-hooks auto-repair for boxes that installed Skill 38 before v2.0.9.

Runs from the shared front door (shared-utils/oct4_frontdoor.py) after every update, so
no one re-runs Skill 38 setup. Only touches a box whose hooks are ALREADY enabled:
  a) removes hooks.maxBodyBytes   (OpenClaw 2026.9.x rejects it: config INVALID)
  b) sets gateway.trustedProxies  (only when unset/empty; else 403 proxy_attribution_required)
  c) reports a mapping agentId that is not a configured agent (never edits it)
Never enables hooks, adds mappings, creates tokens or prints secret values.
Exit: 0 ok, 1 failed (validate rejected; backup restored), 2 needs-attention, 5 cannot-verify.
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


def proxies():
    """Reuse the install-time detection (lib-docker-tenant.sh) so both paths agree."""
    lib = os.environ.get("S38_REPAIR_LIB") or str(HERE.parent / "lib-docker-tenant.sh")
    if not Path(lib).is_file():
        return None
    r = subprocess.run(["bash", "-c", '. "$1" && s38_trusted_proxies', "_", lib],
                       capture_output=True, text=True)
    out = [x.strip() for x in r.stdout.splitlines() if x.strip()]
    return out if r.returncode == 0 and out else None


def oc_cli(root):
    """The CLI is often not on the updater's PATH (docker tenants keep it under npm-global)."""
    for c in (os.environ.get("OC_CLI", ""), shutil.which("openclaw") or "",
              str(root / "npm-global" / "bin" / "openclaw")):
        if c and os.access(c, os.X_OK):
            return c
    return None


def repair(cfg):
    """Mutates cfg. Returns (changes, attention), or (None, None) when out of scope."""
    changes, attention = [], []
    hooks = cfg.get("hooks")
    if not isinstance(hooks, dict) or hooks.get("enabled") is not True:
        return None, None
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
    if ids:
        for m in hooks.get("mappings") or []:
            aid = m.get("agentId") if isinstance(m, dict) else None
            if aid and aid not in ids:
                attention.append("hooks mapping agentId %r is not a configured agent" % aid)
    return changes, attention


def run(root, dry):
    path = root / "openclaw.json"
    try:
        cfg = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        print("skill38 inbound hooks: cannot read %s: %s" % (path, type(e).__name__), file=sys.stderr)
        return 5
    changes, attention = repair(cfg)
    if changes is None:
        print("skill38 inbound hooks not configured on this box; nothing to repair")
        return 0
    for c in changes:
        print(("would " if dry else "") + c)
    for a in attention:
        print("NEEDS ATTENTION: " + a)
    if changes and not dry:
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
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

    def go(name, cfg, lib="docker", dry=False, stub=None):
        d = T / name
        d.mkdir()
        (d / "openclaw.json").write_text(json.dumps(cfg))
        (d / "lib.sh").write_text("s38_trusted_proxies(){ %s; }\n" % (
            "echo 172.19.0.1" if lib == "docker" else "printf '127.0.0.1\\n::1\\n'"))
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
    rc, c, d, r = go("agent", {"hooks": {"enabled": True, "mappings": [{"agentId": "zz"}]},
                               "agents": agents, "gateway": {"trustedProxies": ["1.1.1.1"]}})
    assert rc == 2 and c["hooks"]["mappings"][0]["agentId"] == "zz" and not baks(d)
    rc, c, d, r = go("dry", {"hooks": on(), "agents": agents}, dry=True)
    assert "maxBodyBytes" in c["hooks"] and not baks(d)
    rc, c, d, r = go("bad", {"hooks": on(), "agents": agents}, stub=1)
    assert rc == 1 and "maxBodyBytes" in c["hooks"] and "gateway" not in c
    rc, c, d, r = go("good", {"hooks": on(), "agents": agents}, stub=0)
    assert rc == 0 and "maxBodyBytes" not in c["hooks"]
    nofile = subprocess.run([sys.executable, me], env=dict(os.environ, OPENCLAW_ROOT=str(T / "none")),
                            capture_output=True, text=True)
    assert nofile.returncode == 5
    shutil.rmtree(T)
    print("selftest ok")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    sys.exit(run(oc_root(), "--dry-run" in sys.argv))
