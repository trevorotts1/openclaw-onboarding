#!/usr/bin/env python3
"""hostinger-wrapper-patch.py - persistent boot patcher (Trevor order 2026-10-11, FIX-PROTOCOL v2 H2).
Neutralises harmful writes of the image start-up wrapper /hostinger/server.mjs on every boot.
Idempotent, fail-soft (always exits 0). Test: HWP_TARGET=/path/to/copy python3 this.py
"""
import os, sys, subprocess, shutil, tempfile, time

TARGET = os.environ.get("HWP_TARGET", "/hostinger/server.mjs")
LOG = os.environ.get("HWP_LOG", "/data/.openclaw/logs/hostinger-wrapper-patch.log")
KNOWN_GOOD = "/data/.openclaw/tools/hostinger-server.known-good.mjs"
NODES = ["/data/.npm-global/bin/node", "/usr/local/bin/node", "node"]

# (name, old, new)
REPS = [
 ("1 agents.list", 'c(e,"agents->list",[{id:"main",name:"main"}])', "void 0"),
 ("2 meta.lastTouchedAt", 'c(e,"meta->lastTouchedAt",new Date().toISOString())', "void 0"),
 ("3 plugins.bundledDiscovery", 'r.plugins.bundledDiscovery="compat"', "void 0"),
 ("4 keep chosen primary model", '(!s||!w(s))&&(n.warn("No valid primary model found")', '(!s)&&(n.warn("No valid primary model found")'),
 ("5 retired auth-profiles.json write", "d.writeFileSync(q,JSON.stringify(t,null,2))", "void 0"),
 ("6 keep gateway.trustedProxies", "e.gateway?.trustedProxies&&process.env.TRAEFIK_HOST&&delete e.gateway.trustedProxies", "void 0"),
]

def log(msg):
    line = "%s %s" % (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), msg)
    print("hostinger-wrapper-patch:", msg)
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass

def node_check(path):
    for n in NODES:
        try:
            r = subprocess.run([n, "--check", path], capture_output=True, timeout=60)
            return r.returncode == 0
        except FileNotFoundError:
            continue
        except Exception:
            return False
    return False

def restore_known_good():
    try:
        if os.path.isfile(KNOWN_GOOD) and node_check(KNOWN_GOOD):
            shutil.copyfile(KNOWN_GOOD, TARGET)
            log("RESTORED known-good wrapper over %s" % TARGET)
        else:
            log("no usable known-good wrapper to restore")
    except Exception as e:
        log("restore failed: %s" % e)

def main():
    try:
        s = open(TARGET).read()
    except Exception as e:
        log("cannot read %s: %s" % (TARGET, e)); return
    out = s
    applied = []
    for name, old, new in REPS:
        c = out.count(old)
        if c:
            out = out.replace(old, new)
            applied.append("%s x%d" % (name, c))
    if out == s:
        log("already patched (nothing to change) target=%s" % TARGET); return
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(prefix="hwp-", suffix=".mjs", dir="/tmp")
        with os.fdopen(fd, "w") as f:
            f.write(out)
        if not node_check(tmp):
            log("node --check FAILED on patched text; not applying")
            restore_known_good(); return
        shutil.copyfile(tmp, TARGET)  # in place keeps owner/mode; dir may not be writable for rename
        log("PATCHED %s: %s" % (TARGET, "; ".join(applied)))
    except Exception as e:
        log("patch failed: %s" % e)
        restore_known_good()
    finally:
        try:
            if tmp and os.path.exists(tmp): os.remove(tmp)
        except Exception:
            pass

try:
    main()
except Exception as e:
    try: log("unexpected: %s" % e)
    except Exception: pass
sys.exit(0)
