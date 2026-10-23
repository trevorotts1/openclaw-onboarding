#!/usr/bin/env python3
"""Runnable self-check for shared-utils/browser/browser_manager.py (W3A-U1).

``python3 -I shared-utils/browser/browser_manager_selfcheck.py``

Asserts, no pass banner that could hide a skip: every check calls ``assert``;
the final line is the record it proved. All state lands in a private
``/tmp/ghl-delivery-W3A-U1-*`` root (never the real reaper lockdir), and every
process it spawns is an owned disposable one.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # .../shared-utils/browser

import browser_manager as bm  # noqa: E402

SLEEPER = "import time; time.sleep(60)"
checks = 0

# Private root — the self-check never touches ${TMPDIR}/agent-browser.
tmp = tempfile.mkdtemp(prefix="ghl-delivery-W3A-U1-", dir="/tmp")
root = os.path.join(tmp, "agent-browser")
profile_a = os.path.join(tmp, "profile-a")
profile_b = os.path.join(tmp, "profile-b")
os.makedirs(profile_a)
os.makedirs(profile_b)

try:
    # 1. D6 headless guard: headed refused, clean/off accepted.
    try:
        bm.headless_guard({"AGENT_BROWSER_HEADED": "1"})
        raise AssertionError("headed config was NOT refused")
    except bm.HeadlessRefused:
        pass
    bm.headless_guard({})
    bm.headless_guard({"AGENT_BROWSER_HEADED": "0"})
    checks += 1

    # 2. Trust-boundary validation of writer keys.
    for bad_kind, bad_target in (("Bad Kind!", "t"), ("session", "")):
        try:
            bm.WriterLease(bad_kind, bad_target, root=root)
            raise AssertionError("bad writer key %r/%r accepted"
                                 % (bad_kind, bad_target))
        except ValueError:
            pass
    checks += 1

    # 3. ONE writer per mutable target: second writer refused after a BOUNDED
    #    wait; different targets coexist.
    w1 = bm.WriterLease("location", "loc-1", root=root,
                        profile_path=profile_a).acquire()
    t0 = time.time()
    try:
        bm.WriterLease("location", "loc-1", root=root, wait_s=0.5).acquire()
        raise AssertionError("second writer on the same location was admitted")
    except bm.WriterBusy:
        pass
    elapsed = time.time() - t0
    assert 0.4 <= elapsed < 3.0, "wait was not bounded: %.2fs" % elapsed
    w_other = bm.WriterLease("session", "sess-1", root=root).acquire()
    assert w_other._held and w1._held
    w_other.release()
    checks += 1

    # 4. Lease is visible and healthy while held; release removes BOTH the
    #    lease file and the lock dir (owned cleanup of the exclusion state).
    lease = bm.lease_read(w1.lease_file)
    assert lease is not None and bm.lease_healthy(lease), "lease not healthy"
    assert lease["owner_pid"] == os.getpid()
    report = w1.release()
    assert set(report) == {"terminated", "killed"}
    assert not os.path.exists(w1.lease_file), "lease file survived release"
    assert not os.path.exists(w1.lock_path), "lock dir survived release"
    checks += 1

    # 5. Owned cleanup: the owned child (cmdline carries the EXACT profile
    #    path) is stopped on release; a process without that path survives.
    owned = subprocess.Popen(
        [sys.executable, "-I", "-c", SLEEPER, profile_a])
    decoy = subprocess.Popen(
        [sys.executable, "-I", "-c", SLEEPER])
    time.sleep(0.3)
    w2 = bm.WriterLease("session", "sess-owned", root=root,
                        profile_path=profile_a).acquire()
    w2.register_owned(owned.pid)
    report = w2.release()
    time.sleep(0.3)
    assert owned.poll() is not None, "owned child survived teardown"
    assert owned.pid in report["terminated"] or owned.pid in report["killed"]
    assert decoy.poll() is None, "unowned process was signaled"
    decoy.kill()
    decoy.wait()
    checks += 1

    # 6. Owner guard: a non-owner can never release someone else's writer.
    w3 = bm.WriterLease("location", "loc-2", root=root).acquire()
    with open(os.path.join(w3.lock_path, "owner.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"pid": 999999999, "pid_start": "x",
                   "kind": "location", "target_id": "loc-2"}, fh)
    try:
        w3.release()
        raise AssertionError("non-owner release succeeded")
    except bm.NotOwner:
        pass
    assert os.path.exists(w3.lock_path), "non-owner release dropped the lock"
    w3._write_owner()  # restore our real owner record
    w3.release()
    checks += 1

    # 7. Explicit deadlines: an expired lease is unhealthy and sweep() reclaims
    #    it; a lock whose owner died is reclaimed by the next acquire.
    w4 = bm.WriterLease("session", "sess-ttl", root=root,
                        ttl_sec=0.3).acquire()
    time.sleep(0.5)
    assert not bm.lease_healthy(bm.lease_read(w4.lease_file)), "expired lease healthy"
    swept = bm.sweep(root=root)
    assert "session/sess-ttl" in swept["reclaimed"], swept
    assert not os.path.exists(w4.lease_file), "expired lease survived sweep"
    w4._reclaim_lock_dir()  # the dead writer's exclusion state, via sweep path
    w5 = bm.WriterLease("location", "loc-stale", root=root, wait_s=1.0).acquire()
    os.utime(w5.lock_path, (time.time() - 5, time.time() - 5))
    with open(os.path.join(w5.lock_path, "owner.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"pid": 999999999, "pid_start": "x",
                   "kind": "location", "target_id": "loc-stale"}, fh)
    w6 = bm.WriterLease("location", "loc-stale", root=root,
                        wait_s=2.0).acquire()  # reclaims the stale lock
    assert w6._held
    w6.release()
    checks += 1

    # 8. sweep() reclaims a dead-owner lease AND its owned child processes
    #    (graceful-then-force, scoped to the exact profile path).
    victim = subprocess.Popen(
        [sys.executable, "-I", "-c", SLEEPER, profile_b])
    time.sleep(0.3)
    starter = subprocess.Popen(
        [sys.executable, "-I", "-c", "import time; time.sleep(0.3)"])
    starter.wait()
    bm.lease_write(root, "session", "sess-dead",
                   owner_pid=starter.pid, owner_start="gone",
                   profile_path=profile_b,
                   owned_pids={victim.pid: bm.proc_start_time(victim.pid)},
                   ttl_sec=600)
    swept = bm.sweep(root=root)
    assert "session/sess-dead" in swept["reclaimed"], swept
    time.sleep(0.3)
    assert victim.poll() is not None, "orphaned owned child survived sweep"
    checks += 1

    # Record proved (never a bare pass banner).
    print(json.dumps({"selfcheck": "browser_manager", "version":
                      bm.BROWSER_MANAGER_VERSION, "checks_passed": checks,
                      "root": "private tmp (removed)"}, sort_keys=True))
finally:
    shutil.rmtree(tmp, ignore_errors=True)
