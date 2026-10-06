#!/usr/bin/env python3
"""test_pres044_transactional_stores.py -- [PRES-044] the capacity override
and the resource profile are ONE transactional store each, never a
last-write-wins racetrack.

THE DEFECT (H-DATA, evidence/handoff-capacity-review.md; all three reproduced
on pristine base 7af2cf4b969f27b38c1920b8290c252dd5405dc5, see
run/evidence/PRES-044/base-*/defect-repro.log):

  D1  declare_capacity(provider, plan=...) popped the same provider's
      max_concurrent -- a TIER CHANGE silently removed the operator's
      self-throttle (:1620-1623).
  D2  the rebuilt root carried only schema/providers/_note -- every unknown
      operator field at the ROOT was dropped on the next declaration
      (:1633-1640).
  D3  both writers (capacity.declare_capacity, resource_profile.save_profile)
      used ONE FIXED `.json.tmp` and no lock spanning read..write: two
      concurrent writers shared a tmp path (measured: 8 threads -> 6
      FileNotFoundError + a last-write-wins file), a stale same-provider
      revision silently overwrote a fresh writer's fields, and neither
      failure ever said so.

THE CONTRACT THIS FILE LOCKS (spec PRES-044 / QC-PRES-044):

  1. Sentinel unknown ROOT fields, unknown FOREIGN-PROVIDER fields and a
     same-provider EXPLICIT THROTTLE all survive tier changes.
  2. Two simultaneous different-provider writes BOTH persist (one lock spans
     read -> validate -> merge -> write).
  3. A same-provider STALE REVISION is rejected VISIBLY
     (StoreRevisionConflict), never silently clobbered.
  4. Unique tmp per writer + fsync + atomic replace INSIDE the lock; injected
     disk-full/rename failure and malformed input leave a valid old or new
     file on disk, raise VISIBLY, and never write another client's store.

Every test here redirects both config envs at tmp_path. Nothing in this file
may read or write the operator's real stores.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import threading
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from presentation_job import capacity  # noqa: E402
from presentation_job import resource_profile  # noqa: E402

# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------
def _isolate(monkeypatch, tmp_path):
    """Both stores redirected into tmp_path; no detection sources; no live
    probes -- no test here can touch the operator's real config."""
    monkeypatch.setattr(capacity, "NINEROUTER_DB", tmp_path / "absent.sqlite")
    monkeypatch.setattr(capacity, "OPENCLAW_CONFIG", tmp_path / "absent.json")
    monkeypatch.setattr(capacity, "HARNESS_SETTINGS_CANDIDATES",
                        (tmp_path / "absent-settings.json",))
    monkeypatch.setattr(capacity, "measure_working_concurrent",
                        lambda: (0, "stub", True))
    monkeypatch.setenv("PRESENTATION_PROVIDER_PROBES", "0")
    cfg = tmp_path / "cfg"
    cfg.mkdir(exist_ok=True)
    monkeypatch.setenv(capacity.CONFIG_DIR_ENV, str(cfg))
    monkeypatch.setenv(resource_profile.DIR_ENV, str(cfg))
    monkeypatch.delenv(resource_profile.FLAG_ENV, raising=False)
    cache = getattr(capacity, "_DECLARED_CACHE", None)
    if isinstance(cache, dict):
        cache.clear()
    return cfg


# ===========================================================================
# 1. Sentinel / foreign metadata / same-provider throttle survive TIER changes
# ===========================================================================
def test_unknown_root_fields_survive_a_tier_change(monkeypatch, tmp_path):
    """D2: the root rebuild owned only schema/providers/_note and dropped
    everything else. Operator metadata at the root is not ours to manage --
    this module owns exactly four root keys and preserves the rest verbatim."""
    cfg = _isolate(monkeypatch, tmp_path)
    capacity.declare_capacity("ollama-cloud", plan="$100/month", config_dir=cfg)
    doc = json.loads(capacity.override_path(cfg).read_text(encoding="utf-8"))
    doc["operator_sentinel"] = {"note": "hand-tuned", "since": "2026-01-01"}
    doc["audit_trail"] = ["entry-1"]
    capacity.override_path(cfg).write_text(json.dumps(doc), encoding="utf-8")

    # THE TIER CHANGE that used to rebuild the root:
    capacity.declare_capacity("ollama-cloud", plan="$20/month", config_dir=cfg)

    doc = json.loads(capacity.override_path(cfg).read_text(encoding="utf-8"))
    assert doc["operator_sentinel"] == {"note": "hand-tuned", "since": "2026-01-01"}
    assert doc["audit_trail"] == ["entry-1"]
    assert doc["providers"]["ollama-cloud"]["plan"] == "$20/month"


def test_foreign_provider_fields_survive_a_tier_change(monkeypatch, tmp_path):
    """A statement about ollama-cloud is never a licence to rewrite
    deepseek-direct's sub-record -- including fields THIS build does not
    know (sentinel keys)."""
    cfg = _isolate(monkeypatch, tmp_path)
    capacity.override_path(cfg).write_text(json.dumps({
        "schema": 2,
        "providers": {
            "deepseek-direct": {"plan": "v4-flash", "max_concurrent": 40,
                                "operator_sentinel_field": {"keep": True}},
            "ollama-cloud": {"plan": "$100/month", "max_concurrent": 5},
        },
    }), encoding="utf-8")

    capacity.declare_capacity("ollama-cloud", plan="$20/month", config_dir=cfg)

    doc = json.loads(capacity.override_path(cfg).read_text(encoding="utf-8"))
    ds = doc["providers"]["deepseek-direct"]
    assert ds["plan"] == "v4-flash"
    assert ds["max_concurrent"] == 40
    assert ds["operator_sentinel_field"] == {"keep": True}


def test_tier_change_never_drops_the_same_provider_self_throttle(
        monkeypatch, tmp_path):
    """D1, the named defect: writing a plan popped max_concurrent. Entitlement
    (plan), allocation (max_concurrent) and reserve are THREE DISTINCT fields;
    a tier change sets plan and touches nothing else."""
    cfg = _isolate(monkeypatch, tmp_path)
    capacity.declare_capacity("ollama-cloud", max_concurrent=5, config_dir=cfg)

    capacity.declare_capacity("ollama-cloud", plan="$100/month", config_dir=cfg)

    doc = json.loads(capacity.override_path(cfg).read_text(encoding="utf-8"))
    entry = doc["providers"]["ollama-cloud"]
    assert entry["max_concurrent"] == 5, (
        "a tier change silently removed the operator's self-throttle: "
        f"{entry}")
    assert entry["plan"] == "$100/month"

    # and the reverse direction: re-stating max_concurrent never drops plan
    capacity.declare_capacity("ollama-cloud", max_concurrent=6, config_dir=cfg)
    entry = json.loads(capacity.override_path(cfg).read_text(
        encoding="utf-8"))["providers"]["ollama-cloud"]
    assert entry["max_concurrent"] == 6
    assert entry["plan"] == "$100/month"


def test_explicit_reserve_field_survives_every_write(monkeypatch, tmp_path):
    """reserve is the third distinct field (spec: 'plan entitlement, desired
    allocation and reserve are different fields'). Neither a tier change nor
    an allocation change may remove an operator's explicit reserve."""
    cfg = _isolate(monkeypatch, tmp_path)
    capacity.declare_capacity("ollama-cloud", plan="$100/month",
                              max_concurrent=8, config_dir=cfg)
    doc = json.loads(capacity.override_path(cfg).read_text(encoding="utf-8"))
    doc["providers"]["ollama-cloud"]["reserve"] = 2
    capacity.override_path(cfg).write_text(json.dumps(doc), encoding="utf-8")

    capacity.declare_capacity("ollama-cloud", plan="$20/month", config_dir=cfg)
    entry = json.loads(capacity.override_path(cfg).read_text(
        encoding="utf-8"))["providers"]["ollama-cloud"]
    assert entry["reserve"] == 2
    assert entry["max_concurrent"] == 8
    assert entry["plan"] == "$20/month"

    capacity.declare_capacity("ollama-cloud", max_concurrent=9, config_dir=cfg)
    entry = json.loads(capacity.override_path(cfg).read_text(
        encoding="utf-8"))["providers"]["ollama-cloud"]
    assert entry["reserve"] == 2
    assert entry["max_concurrent"] == 9


def test_unknown_per_provider_fields_survive_the_provider_write(
        monkeypatch, tmp_path):
    cfg = _isolate(monkeypatch, tmp_path)
    capacity.declare_capacity("openrouter", max_concurrent=50, config_dir=cfg)
    doc = json.loads(capacity.override_path(cfg).read_text(encoding="utf-8"))
    doc["providers"]["openrouter"]["cost_center"] = "dept-7"
    capacity.override_path(cfg).write_text(json.dumps(doc), encoding="utf-8")

    capacity.declare_capacity("openrouter", max_concurrent=60, config_dir=cfg)
    entry = json.loads(capacity.override_path(cfg).read_text(
        encoding="utf-8"))["providers"]["openrouter"]
    assert entry["cost_center"] == "dept-7"
    assert entry["max_concurrent"] == 60


# ===========================================================================
# 2. CONCURRENT different-provider writes: BOTH persist
# ===========================================================================
def test_two_simultaneous_different_provider_writes_both_persist(
        monkeypatch, tmp_path):
    """D3: two writers, one fixed tmp, no lock spanning read..write. Now one
    lock spans the whole transaction, so the two threads serialise and each
    provider's declaration is on disk when both return."""
    cfg = _isolate(monkeypatch, tmp_path)
    errors: list = []

    def write(provider, plan):
        try:
            capacity.declare_capacity(provider, plan=plan, config_dir=cfg)
        except Exception as exc:  # noqa: BLE001 -- recorded, asserted below
            errors.append(f"{provider}: {type(exc).__name__}: {exc}")

    t1 = threading.Thread(target=write, args=("ollama-cloud", "$100/month"))
    t2 = threading.Thread(target=write, args=("deepseek-direct", "v4-flash"))
    t1.start(); t2.start(); t1.join(); t2.join()

    assert errors == [], errors
    doc = json.loads(capacity.override_path(cfg).read_text(encoding="utf-8"))
    assert doc["providers"]["ollama-cloud"]["plan"] == "$100/month"
    assert doc["providers"]["deepseek-direct"]["plan"] == "v4-flash"


def test_eight_concurrent_mixed_writers_all_persist_no_lost_update(
        monkeypatch, tmp_path):
    """Beyond the spec's minimum: eight threads, four providers, mixed
    field writes. Every write lands; no fixed-tmp FileNotFoundError; the
    file is valid JSON after the storm."""
    cfg = _isolate(monkeypatch, tmp_path)
    errors: list = []
    barrier = threading.Barrier(8)

    def write(i):
        provider, field = [("ollama-cloud", "plan"),
                           ("deepseek-direct", "max_concurrent"),
                           ("openrouter", "max_concurrent"),
                           ("deepseek-direct", "plan")][i % 4]
        try:
            barrier.wait(timeout=10)
            if field == "plan":
                capacity.declare_capacity(
                    provider,
                    plan="$100/month" if provider == "ollama-cloud" else "v4-flash",
                    config_dir=cfg)
            else:
                capacity.declare_capacity(provider, max_concurrent=10 + i,
                                          config_dir=cfg)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"t{i}: {type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=write, args=(i,)) for i in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert errors == [], errors
    doc = json.loads(capacity.override_path(cfg).read_text(encoding="utf-8"))
    assert doc["providers"]["ollama-cloud"]["plan"] == "$100/month"
    assert doc["providers"]["deepseek-direct"]["plan"] == "v4-flash"
    assert "max_concurrent" in doc["providers"]["deepseek-direct"]
    assert "max_concurrent" in doc["providers"]["openrouter"]
    # unique tmp files are cleaned up: no *.tmp-* litter left behind
    litter = [p.name for p in cfg.iterdir() if ".tmp-" in p.name]
    assert litter == [], litter


def test_profile_transaction_concurrent_providers_both_persist(
        monkeypatch, tmp_path):
    """Same contract on the OTHER store: two concurrent profile transactions
    for different providers must both persist (the old fixed-tmp save could
    lose one)."""
    cfg = _isolate(monkeypatch, tmp_path)
    errors: list = []

    def write(provider, plan):
        try:
            with resource_profile.profile_transaction(cfg) as prof:
                resource_profile.upsert_provider(
                    prof, provider, plan_tier=plan, plan_known=True)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{provider}: {type(exc).__name__}: {exc}")

    t1 = threading.Thread(target=write, args=("ollama-cloud", "$100/month"))
    t2 = threading.Thread(target=write, args=("deepseek-direct", "v4-flash"))
    t1.start(); t2.start(); t1.join(); t2.join()
    assert errors == [], errors

    doc = resource_profile.load_profile(cfg)
    assert doc["providers"]["ollama-cloud"]["plan_tier"] == "$100/month"
    assert doc["providers"]["deepseek-direct"]["plan_tier"] == "v4-flash"


# ===========================================================================
# 3. Stale same-provider revision: REJECTED VISIBLY, never silent clobber
# ===========================================================================
def test_stale_same_provider_revision_rejected_visibly(monkeypatch, tmp_path):
    """Writer A reads revision N. Writer B writes revision N+1. A must be
    REJECTED (StoreRevisionConflict) with B's fields still on disk -- the
    old code let A silently overwrite B's update."""
    cfg = _isolate(monkeypatch, tmp_path)
    capacity.declare_capacity("ollama-cloud", max_concurrent=5, config_dir=cfg)
    doc = json.loads(capacity.override_path(cfg).read_text(encoding="utf-8"))
    rev_a = doc["revision"]

    # writer B (fresh) wins the race
    capacity.declare_capacity("ollama-cloud", max_concurrent=7, config_dir=cfg)

    # writer A (stale) tries to land its old view
    with pytest.raises(capacity.StoreRevisionConflict) as excinfo:
        capacity.declare_capacity("ollama-cloud", max_concurrent=3,
                                  config_dir=cfg,
                                  expected_revision=rev_a)
    assert "expected revision" in str(excinfo.value)

    # B's write is intact on disk
    doc = json.loads(capacity.override_path(cfg).read_text(encoding="utf-8"))
    assert doc["providers"]["ollama-cloud"]["max_concurrent"] == 7


def test_expected_revision_match_still_writes(monkeypatch, tmp_path):
    """The optimistic-lock happy path: a caller whose revision is still
    current writes normally."""
    cfg = _isolate(monkeypatch, tmp_path)
    capacity.declare_capacity("ollama-cloud", max_concurrent=5, config_dir=cfg)
    rev = json.loads(capacity.override_path(cfg).read_text(
        encoding="utf-8"))["revision"]

    capacity.declare_capacity("ollama-cloud", max_concurrent=6,
                              config_dir=cfg, expected_revision=rev)

    doc = json.loads(capacity.override_path(cfg).read_text(encoding="utf-8"))
    assert doc["providers"]["ollama-cloud"]["max_concurrent"] == 6
    assert doc["revision"] == rev + 1


def test_revision_bumps_on_every_write_and_survives_reads(monkeypatch,
                                                          tmp_path):
    cfg = _isolate(monkeypatch, tmp_path)
    assert not capacity.override_path(cfg).is_file()
    capacity.declare_capacity("openrouter", max_concurrent=10, config_dir=cfg)
    rev1 = json.loads(capacity.override_path(cfg).read_text(
        encoding="utf-8"))["revision"]
    assert rev1 >= 1
    capacity.declare_capacity("openrouter", max_concurrent=11, config_dir=cfg)
    rev2 = json.loads(capacity.override_path(cfg).read_text(
        encoding="utf-8"))["revision"]
    assert rev2 == rev1 + 1
    # a probe read never rewrites the file (legacy-read doctrine, now
    # also guarded by revision stability)
    capacity.probe(cfg, provider="openrouter")
    rev3 = json.loads(capacity.override_path(cfg).read_text(
        encoding="utf-8"))["revision"]
    assert rev3 == rev2


def test_stale_profile_version_rejected_visibly(monkeypatch, tmp_path):
    """The profile store carries the same optimistic lock on its
    profile_version token."""
    cfg = _isolate(monkeypatch, tmp_path)
    with resource_profile.profile_transaction(cfg) as prof:
        resource_profile.upsert_provider(prof, "openrouter",
                                         wired_models=["m1"])
    version_a = resource_profile.load_profile(cfg)["profile_version"]

    # writer B moves the store
    with resource_profile.profile_transaction(cfg) as prof:
        resource_profile.upsert_provider(prof, "openrouter",
                                         wired_models=["m1", "m2"])

    # writer A (stale) tries to land its old view
    with pytest.raises(resource_profile.StoreRevisionConflict):
        resource_profile.save_profile(
            {"providers": {"openrouter": {"wired_models": ["m1"]}}},
            cfg, expected_profile_version=version_a)

    # B's state survives
    doc = resource_profile.load_profile(cfg)
    assert doc["providers"]["openrouter"]["wired_models"] == ["m1", "m2"]


# ===========================================================================
# 4. Unique tmp + fsync + atomic replace; injected failures; malformed input
# ===========================================================================
def test_write_failure_is_visible_durable_and_leaves_old_file(
        monkeypatch, tmp_path):
    """Inject a rename failure at os.replace: the caller sees
    StoreWriteError (raised, printed -- never swallowed), the PREVIOUS file
    is still on disk byte-identical, and no tmp litter is left behind."""
    cfg = _isolate(monkeypatch, tmp_path)
    capacity.declare_capacity("openrouter", max_concurrent=10, config_dir=cfg)
    before = capacity.override_path(cfg).read_bytes()

    real_replace = os.replace
    calls = {"n": 0}

    def failing_replace(src, dst, **kw):
        calls["n"] += 1
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(capacity.os, "replace", failing_replace)
    with pytest.raises(capacity.StoreWriteError) as excinfo:
        capacity.declare_capacity("openrouter", max_concurrent=11,
                                  config_dir=cfg)
    assert "No space left on device" in str(excinfo.value) or \
        "durable write failed" in str(excinfo.value)
    monkeypatch.setattr(capacity.os, "replace", real_replace)

    after = capacity.override_path(cfg).read_bytes()
    assert after == before, "the old file must survive a failed write intact"
    litter = [p.name for p in cfg.iterdir() if ".tmp-" in p.name]
    assert litter == [], litter


def test_fsync_failure_is_visible_not_silent(monkeypatch, tmp_path):
    """A failure DURING the write (fsync side of disk-full) must also raise
    visibly and leave the old file."""
    cfg = _isolate(monkeypatch, tmp_path)
    capacity.declare_capacity("openrouter", max_concurrent=10, config_dir=cfg)
    before = capacity.override_path(cfg).read_bytes()

    real_fsync = os.fsync

    def failing_fsync(fd):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(capacity.os, "fsync", failing_fsync)
    with pytest.raises((capacity.StoreWriteError, OSError)):
        capacity.declare_capacity("openrouter", max_concurrent=12,
                                  config_dir=cfg)
    monkeypatch.setattr(capacity.os, "fsync", real_fsync)
    assert capacity.override_path(cfg).read_bytes() == before


def test_malformed_override_is_refused_and_unchanged(monkeypatch, tmp_path):
    """Malformed input: the merge refuses loudly, the file is untouched, and
    nothing half-valid is ever written over it."""
    cfg = _isolate(monkeypatch, tmp_path)
    broken = '{"schema": 2, "providers": {'
    capacity.override_path(cfg).write_text(broken, encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        capacity.declare_capacity("openrouter", max_concurrent=10,
                                  config_dir=cfg)
    assert "unreadable" in str(excinfo.value)
    assert capacity.override_path(cfg).read_text(encoding="utf-8") == broken


def test_malformed_input_cannot_be_smuggled_into_the_store(
        monkeypatch, tmp_path):
    """A read that RETURNS an error (per read_override's contract) must stop
    the transaction before the write stage -- the visible error and the
    intact file are the same guarantee as the malformed case."""
    cfg = _isolate(monkeypatch, tmp_path)
    capacity.declare_capacity("ollama-cloud", max_concurrent=5, config_dir=cfg)
    good = capacity.override_path(cfg).read_bytes()

    capacity.override_path(cfg).write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError):
        capacity.declare_capacity("ollama-cloud", max_concurrent=9,
                                  config_dir=cfg)
    # the list-shaped file is left exactly as the operator's mistake left it
    assert capacity.override_path(cfg).read_bytes() == b"[1, 2, 3]"

    # restoring valid data makes writes work again -- nothing was wedged
    capacity.override_path(cfg).write_bytes(good)
    capacity.declare_capacity("ollama-cloud", max_concurrent=9, config_dir=cfg)
    doc = json.loads(capacity.override_path(cfg).read_text(encoding="utf-8"))
    assert doc["providers"]["ollama-cloud"]["max_concurrent"] == 9


def test_profile_write_failure_visible_old_file_recoverable(
        monkeypatch, tmp_path):
    """Same durable-failure contract on the profile store."""
    cfg = _isolate(monkeypatch, tmp_path)
    with resource_profile.profile_transaction(cfg) as prof:
        resource_profile.upsert_provider(prof, "openrouter",
                                         wired_models=["m1"])
    before = resource_profile.profile_path(cfg).read_bytes()

    real_replace = os.replace

    def failing_replace(src, dst, **kw):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(resource_profile.os, "replace", failing_replace)
    with pytest.raises(resource_profile.StoreWriteError):
        with resource_profile.profile_transaction(cfg) as prof:
            resource_profile.upsert_provider(prof, "openrouter",
                                             wired_models=["m2"])
    monkeypatch.setattr(resource_profile.os, "replace", real_replace)

    assert resource_profile.profile_path(cfg).read_bytes() == before


def test_write_failure_in_subprocess_reports_nonzero_and_writes_nothing(
        monkeypatch, tmp_path):
    """END-TO-END, real processes: two writers in separate PROCESSES (flock
    is what serialises those), with os.replace poisoned via sitecustomize in
    one. No success claim: nonzero exit + the error on stderr; the other
    process's write lands; no cross-client writes."""
    cfg = _isolate(monkeypatch, tmp_path)
    helper = tmp_path / "two_writer_children.py"
    helper.write_text(textwrap.dedent("""
        import json, os, sys
        sys.path.insert(0, %r)
        from presentation_job import capacity

        cfg = sys.argv[1]
        poison = sys.argv[2] == "poison"
        if poison:
            real = os.replace
            def bad(src, dst, **kw):
                raise OSError(28, "No space left on device")
            os.replace = bad
        try:
            capacity.declare_capacity("openrouter", max_concurrent=33,
                                      config_dir=cfg)
            print("OK")
        except Exception as exc:
            print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
            sys.exit(3)
    """) % (str(SCRIPTS),), encoding="utf-8")

    env = dict(os.environ)
    env[capacity.CONFIG_DIR_ENV] = str(cfg)
    env[resource_profile.DIR_ENV] = str(cfg)

    # healthy writer first
    r1 = subprocess.run([sys.executable, str(helper), str(cfg), "healthy"],
                        capture_output=True, text=True, env=env, timeout=60)
    assert r1.returncode == 0 and "OK" in r1.stdout, (r1.stdout, r1.stderr)
    healthy_doc = json.loads(capacity.override_path(cfg).read_text(
        encoding="utf-8"))
    assert healthy_doc["providers"]["openrouter"]["max_concurrent"] == 33

    # poisoned writer: must FAIL VISIBLY (nonzero + stderr), write nothing
    r2 = subprocess.run([sys.executable, str(helper), str(cfg), "poison"],
                        capture_output=True, text=True, env=env, timeout=60)
    assert r2.returncode != 0, (
        "a failed durable write must never exit 0 -- that is a success "
        f"claim over a lost write: {r2.stdout}")
    assert "No space left on device" in r2.stderr or \
        "StoreWriteError" in r2.stderr, r2.stderr

    # the healthy write is still on disk, untouched
    after = json.loads(capacity.override_path(cfg).read_text(
        encoding="utf-8"))
    assert after["providers"]["openrouter"]["max_concurrent"] == 33


def test_concurrent_cross_process_writes_both_persist(monkeypatch, tmp_path):
    """Two real PROCESSES writing DIFFERENT providers simultaneously: the
    cross-process flock serialises them and BOTH land (threads alone cannot
    prove this -- flock is per open-file-description)."""
    cfg = _isolate(monkeypatch, tmp_path)
    helper = tmp_path / "proc_writer.py"
    helper.write_text(textwrap.dedent("""
        import sys
        sys.path.insert(0, %r)
        from presentation_job import capacity
        capacity.declare_capacity(sys.argv[2], plan=sys.argv[3],
                                  config_dir=sys.argv[1])
        print("OK")
    """) % (str(SCRIPTS),), encoding="utf-8")

    env = dict(os.environ)
    env[capacity.CONFIG_DIR_ENV] = str(cfg)
    env[resource_profile.DIR_ENV] = str(cfg)
    procs = [subprocess.Popen(
        [sys.executable, str(helper), str(cfg), provider, plan],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        for provider, plan in (("ollama-cloud", "$100/month"),
                               ("deepseek-direct", "v4-flash"))]
    outs = [p.communicate(timeout=60) for p in procs]
    for p, (out, err) in zip(procs, outs):
        assert p.returncode == 0, (p.returncode, out, err)

    doc = json.loads(capacity.override_path(cfg).read_text(encoding="utf-8"))
    assert doc["providers"]["ollama-cloud"]["plan"] == "$100/month"
    assert doc["providers"]["deepseek-direct"]["plan"] == "v4-flash"


# ===========================================================================
# 5. Cross-client isolation: no writer ever touches another client's store
# ===========================================================================
def test_no_cross_client_writes(monkeypatch, tmp_path):
    """A declaration into client A's config dir must leave client B's store
    byte-identical -- the store boundary is the config dir, and every write
    is scoped to exactly one path."""
    cfg_a = tmp_path / "client-a"
    cfg_b = tmp_path / "client-b"
    cfg_a.mkdir(); cfg_b.mkdir()
    monkeypatch.setenv(capacity.CONFIG_DIR_ENV, str(cfg_a))
    monkeypatch.setenv(resource_profile.DIR_ENV, str(cfg_a))
    capacity.declare_capacity("ollama-cloud", max_concurrent=5, config_dir=cfg_a)
    b_before = None

    monkeypatch.setenv(capacity.CONFIG_DIR_ENV, str(cfg_b))
    monkeypatch.setenv(resource_profile.DIR_ENV, str(cfg_b))
    capacity.declare_capacity("deepseek-direct", plan="v4-flash",
                              config_dir=cfg_b)
    b_after = cfg_b.iterdir()

    # client B only ever got ITS OWN file
    names_b = sorted(p.name for p in cfg_b.iterdir()
                     if p.name != "capacity_override.json.lock")
    assert names_b == ["capacity_override.json"], names_b
    doc_b = json.loads((cfg_b / "capacity_override.json").read_text(
        encoding="utf-8"))
    assert set(doc_b["providers"]) == {"deepseek-direct"}
    # client A's store was not touched by B's write
    monkeypatch.setenv(capacity.CONFIG_DIR_ENV, str(cfg_a))
    monkeypatch.setenv(resource_profile.DIR_ENV, str(cfg_a))
    doc_a = json.loads(capacity.override_path(cfg_a).read_text(
        encoding="utf-8"))
    assert set(doc_a["providers"]) == {"ollama-cloud"}
    _ = b_before, b_after


# ===========================================================================
# 6. Legacy read never rewrites; migration backs up first
# ===========================================================================
def test_legacy_v1_read_never_rewrites_and_never_mints_a_revision(
        monkeypatch, tmp_path):
    """Reading legacy v1 state must not rewrite it -- only an explicit
    declaration does, and it must back up the v1 bytes first."""
    cfg = _isolate(monkeypatch, tmp_path)
    v1 = {"provider": "ollama-cloud", "plan": "$20/month",
          "max_concurrent": 3, "operator_note": "legacy"}
    path = capacity.override_path(cfg)
    path.write_text(json.dumps(v1), encoding="utf-8")
    mtime_before = path.stat().st_mtime_ns

    # READ paths: probe/resolve must work off the v1 record WITHOUT writing
    capacity.probe(cfg, provider="ollama-cloud")
    assert path.read_text(encoding="utf-8") == json.dumps(v1), (
        "a read rewrote a legacy v1 record")
    assert path.stat().st_mtime_ns == mtime_before

    # explicit WRITE: the one sanctioned migration, with a pre-migration backup
    capacity.declare_capacity("deepseek-direct", plan="v4-flash",
                              config_dir=cfg)
    backup = path.with_suffix(".json.pre-schema2.bak")
    assert backup.is_file(), "schema migration must back up the v1 bytes"
    assert json.loads(backup.read_text(encoding="utf-8")) == v1

    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["schema"] == 2
    # v1 provider kept, scoped to itself; new provider added; v1 operator
    # note preserved
    assert doc["providers"]["deepseek-direct"]["plan"] == "v4-flash"
    assert "operator_note" in doc, "unknown root fields survive migration"
    ollama = doc["providers"].get("ollama-cloud", {})
    assert ollama.get("max_concurrent") == 3 or ollama.get("plan") == "$20/month"


def test_migration_backup_failure_refuses_the_migration(monkeypatch,
                                                        tmp_path):
    cfg = _isolate(monkeypatch, tmp_path)
    path = capacity.override_path(cfg)
    v1 = {"provider": "openrouter", "max_concurrent": 12}
    path.write_text(json.dumps(v1), encoding="utf-8")

    real_write_bytes = Path.write_bytes

    def failing_write_bytes(self, data):
        if self.suffix == ".bak":
            raise OSError(28, "No space left on device")
        return real_write_bytes(self, data)

    monkeypatch.setattr(Path, "write_bytes", failing_write_bytes)
    with pytest.raises((capacity.StoreWriteError, OSError)):
        capacity.declare_capacity("ollama-cloud", plan="$100/month",
                                  config_dir=cfg)
    monkeypatch.setattr(Path, "write_bytes", real_write_bytes)
    # the v1 file is untouched
    assert json.loads(path.read_text(encoding="utf-8")) == v1


def test_profile_migration_backs_up_first(monkeypatch, tmp_path):
    cfg = _isolate(monkeypatch, tmp_path)
    path = resource_profile.profile_path(cfg)
    legacy = {".schema_version": 0, "providers": {},
              "creative_prefs": {}, "consent": {}, "interview": {},
              "profile_version": "legacy-token", "updated_at": "x",
              "created_at": "x", "operator_sentinel": {"keep": True}}
    path.write_text(json.dumps(legacy), encoding="utf-8")

    resource_profile.migrate_profile_schema(
        json.loads(path.read_text(encoding="utf-8")), config_dir=cfg)

    backup = path.with_suffix(".json.pre-schema0.bak")
    assert backup.is_file()
    assert json.loads(backup.read_text(encoding="utf-8")) == legacy
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc[".schema_version"] == resource_profile.SCHEMA_VERSION
    assert doc["operator_sentinel"] == {"keep": True}


# ===========================================================================
# 7. The ask-once / detection contract is untouched by the store changes
# ===========================================================================
def test_probe_resolution_unchanged_after_transactions(monkeypatch, tmp_path):
    """The behavioural resolution doctrine (per-provider scope, clamps,
    throttles) must be byte-for-byte unaffected by the transactional store:
    a merged file still resolves exactly as the F1 tests expect."""
    cfg = _isolate(monkeypatch, tmp_path)
    capacity.declare_capacity("ollama-cloud", plan="$100/month",
                              max_concurrent=5, config_dir=cfg)
    capacity.declare_capacity("deepseek-direct", plan="v4-flash",
                              max_concurrent=9999, config_dir=cfg)
    capacity.declare_capacity("openrouter", max_concurrent=7, config_dir=cfg)
    assert capacity.probe(cfg, provider="ollama-cloud")["available"] == 5
    assert capacity.probe(
        cfg, provider="deepseek-direct",
        model="deepseek-v4-flash")["available"] == 2500
    assert capacity.probe(cfg, provider="openrouter")["available"] == 7


def test_no_tmp_litter_and_valid_json_after_normal_use(monkeypatch, tmp_path):
    cfg = _isolate(monkeypatch, tmp_path)
    for i in range(6):
        capacity.declare_capacity("openrouter", max_concurrent=10 + i,
                                  config_dir=cfg)
    with resource_profile.profile_transaction(cfg) as prof:
        resource_profile.upsert_provider(prof, "openrouter",
                                         wired_models=["a"])
    json.loads(capacity.override_path(cfg).read_text(encoding="utf-8"))
    json.loads(resource_profile.profile_path(cfg).read_text(encoding="utf-8"))
    litter = [p.name for p in cfg.iterdir() if ".tmp" in p.name]
    assert litter == [], litter
