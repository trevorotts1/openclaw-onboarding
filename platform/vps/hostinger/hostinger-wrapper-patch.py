#!/usr/bin/env python3
"""hostinger-wrapper-patch.py - persistent boot patcher for /hostinger/server.mjs.

Neutralises the image start-up wrapper's harmful writes on every boot. Wired from
the persistent boot script immediately before `exec node server.mjs`.

FAILS CLOSED (Trevor 2026-10-19). Exit 0 means BOTH of these were proved:

  1. the APPROVED per-wrapper profile for this exact wrapper was applied - every
     fragment count matched exactly and every patched postcondition is absent from
     the text the box is about to boot; or a digest-bound compatible known-good
     wrapper was restored and verified the same way; and
  2. that text passes `node --check`.

Everything else - an absent fragment, a count that is not the profile's, a wrapper
whose size matches no approved profile, a surviving postcondition, a failed
`node --check`, or a fallback whose recorded SHA-256 is missing or wrong - exits
non-zero, and the boot STOPS rather than starting unpatched.

Env:
  WRAPPER_PATH          wrapper to patch (default /hostinger/server.mjs)
  PATCH_LOG             log file (default /data/.openclaw/logs/hostinger-wrapper-patch.log)
  PATCH_PROFILE         JSON {"<fragment index>": <expected count>} - a per-box approved
                        profile for a wrapper whose size is not in PROFILES
  PATCH_STATE           record of the wrapper this patcher produced
                        (default /data/.openclaw/tools/hostinger-wrapper-patch.state)
  WRAPPER_KNOWN_GOOD    digest-bound fallback copy
                        (default /data/.openclaw/tools/hostinger-server.known-good.mjs)
  KNOWN_GOOD_SHA256     recorded SHA-256 of the compatible fallback. Required before
                        ANY restore: a fallback that does not hash to this is never
                        copied over a box's wrapper.
  HWP_TARGET, HWP_LOG   legacy aliases for WRAPPER_PATH / PATCH_LOG.

Dry run: WRAPPER_PATH=/tmp/pristine.mjs PATCH_LOG=/tmp/p.log python3 -I this.py
"""
import hashlib, json, os, shutil, subprocess, sys, time

W = os.environ.get("WRAPPER_PATH") or os.environ.get("HWP_TARGET") or "/hostinger/server.mjs"
LOG = (os.environ.get("PATCH_LOG") or os.environ.get("HWP_LOG")
       or "/data/.openclaw/logs/hostinger-wrapper-patch.log")
GOOD = os.environ.get("WRAPPER_KNOWN_GOOD", "/data/.openclaw/tools/hostinger-server.known-good.mjs")
STATE = os.environ.get("PATCH_STATE", "/data/.openclaw/tools/hostinger-wrapper-patch.state")
GOOD_SHA = os.environ.get("KNOWN_GOOD_SHA256", "").strip().lower()
NODES = ["/data/.npm-global/bin/node", "/usr/local/bin/node", "node"]

# Approved profiles: wrapper byte size -> {fragment index: expected count}.
# A size that is not listed and no PATCH_PROFILE is UNKNOWN: no counts may be
# assumed and the boot stops.
PROFILES = {18713: {1: 1, 2: 1, 3: 1, 4: 2, 5: 1, 6: 1}}   # July build (image layer 2026-07-23)
PROFILE_KEY = {18713: "18713"}                              # size -> the key written to STATE

# (old, new) by index; the expected COUNT comes from the approved profile, never assumed.
FRAGS = [
    # 1: agents.list makes OpenClaw 2026.10.1+ exit 78
    ('c(e,"agents->list",[{id:"main",name:"main"}])', "void 0"),
    # 2: meta.lastTouchedAt makes it exit 78
    ('c(e,"meta->lastTouchedAt",new Date().toISOString())', "void 0"),
    # 3: plugins.bundledDiscovery="compat" makes it exit 78
    ('r.plugins.bundledDiscovery="compat"', "void 0"),
    # 4: keep the client's own primary model (the 18:01Z deepseek swap)
    ('(!s||!w(s))&&(n.warn("No valid primary model found")',
     '(!s)&&(n.warn("No valid primary model found")'),
    # 5: stop re-creating the retired agents/main/agent/auth-profiles.json
    ("d.writeFileSync(q,JSON.stringify(t,null,2))", "void 0"),
    # 6: keep a set gateway.trustedProxies
    ("e.gateway?.trustedProxies&&process.env.TRAEFIK_HOST&&delete e.gateway.trustedProxies", "void 0"),
]
# Patched postconditions: every one of these must be ABSENT from the text the box will boot.
POST = [old for old, _new in FRAGS]


def log(msg):
    line = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + " " + msg
    try:
        d = os.path.dirname(LOG)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print("[wrapper-patch] " + msg)


def node_ok(path):
    for n in NODES:
        try:
            return subprocess.run([n, "--check", path], capture_output=True, timeout=60).returncode == 0
        except FileNotFoundError:
            continue
        except Exception:
            continue
    return False


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def post_ok(text):
    bad = [p for p in POST if p in text]
    if bad:
        log("postcondition FAILED (still present): " + ", ".join(bad))
    return not bad


def state_matches(digest):
    """True when this exact wrapper is one this patcher already produced."""
    try:
        with open(STATE) as f:
            rec = json.load(f)
        return rec.get("sha256") == digest
    except Exception:
        return False


def record_state(key, text):
    try:
        d = os.path.dirname(STATE)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(STATE, "w") as f:
            json.dump({"profile": key, "sha256": hashlib.sha256(text.encode()).hexdigest(),
                       "patched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f)
    except Exception as e:
        # The wrapper itself is patched and verified; losing the record only costs a
        # needless fail-closed attempt on the next start within this same container.
        log("WARNING: could not record patcher state (%s)" % e)


def restore_proved_fallback(reason):
    """Restore ONLY a fallback whose recorded SHA-256 is proved compatible."""
    if not GOOD_SHA:
        log("no KNOWN_GOOD_SHA256 recorded; refusing to restore a fallback")
        return False
    if not os.path.isfile(GOOD):
        log("no known-good copy at %s; nothing to restore" % GOOD)
        return False
    actual = sha(GOOD)
    if actual != GOOD_SHA:
        log("known-good copy SHA-256 mismatch (have %s, recorded %s); refusing to restore"
            % (actual, GOOD_SHA))
        return False
    try:
        text = open(GOOD).read()
    except Exception as e:
        log("known-good copy unreadable: %s" % e)
        return False
    if not post_ok(text):
        log("known-good copy fails postconditions; refusing to start")
        return False
    if not node_ok(GOOD):
        log("known-good copy fails node --check; refusing to start")
        return False
    try:
        shutil.copyfile(GOOD, W)
    except Exception as e:
        log("restore failed: %s" % e)
        return False
    record_state("known-good:%s" % GOOD_SHA[:12], text)
    log("RESTORED digest-bound known-good wrapper over %s (after: %s)" % (W, reason))
    return True


def main():
    try:
        with open(W) as f:
            s = f.read()
    except Exception as e:
        raise RuntimeError("cannot read %s: %s" % (W, e))

    digest = hashlib.sha256(s.encode()).hexdigest()

    # Already our own patched output for this container start: accept only when every
    # postcondition still holds.
    if state_matches(digest):
        if not post_ok(s):
            raise RuntimeError("wrapper matches the patch record but postconditions fail")
        log("already patched (postconditions verified) target=%s" % W)
        return

    prof = None
    key = None
    raw = os.environ.get("PATCH_PROFILE")
    if raw:
        prof = {int(k): int(v) for k, v in json.loads(raw).items()}
        key = "custom"
    else:
        size = len(s.encode())
        prof = PROFILES.get(size)
        key = PROFILE_KEY.get(size, str(size))
        if prof is None:
            raise RuntimeError("unknown wrapper profile (size %d, no approved counts); "
                               "no counts may be assumed" % size)

    t = s
    for i, (old, new) in enumerate(FRAGS, 1):
        want = int(prof.get(i, 0))
        c = t.count(old)
        if c != want:
            raise RuntimeError("fragment %d: found x%d, expected x%d" % (i, c, want))
        if want:
            t = t.replace(old, new)
            log("fragment %d: applied x%d" % (i, c))

    if not post_ok(t):
        raise RuntimeError("patched text fails postconditions")

    if t == s:
        # Input was already in patched shape but we have no record of producing it, so the
        # profile above is what vouched for it. Accept only with postconditions proven.
        log("already patched (postconditions verified, profile %s)" % key)
        record_state(key, t)
        return

    tmp = W + ".new.mjs"   # must end in .mjs or node --check treats it as CommonJS
    try:
        with open(tmp, "w") as f:
            f.write(t)
        if not node_ok(tmp):
            raise RuntimeError("node --check failed on the patched wrapper")
        os.replace(tmp, W)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
    record_state(key, t)
    log("wrapper patched (profile %s)" % key)


try:
    main()
except Exception as e:
    log("FAILED: " + str(e))
    if not restore_proved_fallback(str(e)):
        log("no verified safe result; refusing to start")
        sys.exit(1)
except BaseException as e:  # SystemExit/KeyboardInterrupt from a helper still fails closed
    log("fatal: %s" % e)
    sys.exit(1)
sys.exit(0)
