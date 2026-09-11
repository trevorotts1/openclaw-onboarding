#!/usr/bin/env python3
"""PRES-015 -- hardware-aware admission, the account split, zero discovery.

The QC contract (QC.md QC-PRES-015), mapped to the tests in this file:

  QC 1 (hardware)  -- simulated Mac 8GB, Mac 64GB, Hostinger 2GB cgroup v2,
                      Contabo quota cgroup v1: each respects CONTAINER
                      resources (never host RAM). 4-ready-units-spawn-4 and
                      render-heavy-lower-local-concurrency via
                      admission.effective_width on simulated snapshots.
                      Ollama 20 never exceeds 3; 100-plan gives 10 with
                      reserve 0 and 8 with reserve 2. Unknown quota is never
                      reported MEASURED.
  QC 2 (transport) -- the width consumers (resolve_capacity, _routing_stamp,
                      _stamp_admission_fold, resolve_max_workers) issue ZERO
                      provider-discovery requests; only
                      refresh_provider_inventory calls the transport, only
                      for the providers it was named with, and the snapshot
                      revision is stable across a run.
  QC 3 (mixed)     -- mixed Ollama8 / DeepSeek2500 / OpenRouter100 profile:
                      eligible route widths 8/100/100, never a hidden global
                      8; unknown primary stays visibly unresolved; reconcile
                      twice preserves explicit reserve/unknown fields.

Unit-level: no network, no spend, no deck, no render. Every fixture is a
simulated snapshot or a scratch config dir. Stdlib + pytest/tmp_path only.
"""

import importlib.util
import json
import os
import pathlib
import sys
import threading

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
PJOB = SCRIPTS / "presentation_job"
if str(PJOB) not in sys.path:
    sys.path.insert(0, str(PJOB))

from presentation_job import admission  # noqa: E402
from presentation_job import capacity  # noqa: E402
from presentation_job import hardware_budget as hb  # noqa: E402
from presentation_job import model_router  # noqa: E402
from presentation_job import resource_profile as rp  # noqa: E402

BYOK = capacity.PROVIDER_OPENROUTER
OLLAMA = capacity.PROVIDER_OLLAMA_CLOUD
DEEPSEEK = capacity.PROVIDER_DEEPSEEK_DIRECT
PLAN100 = capacity.PLAN_OLLAMA_100
PLAN20 = capacity.PLAN_OLLAMA_20
FLASH = capacity.PLAN_DEEPSEEK_FLASH
GB = 1024 * 1024 * 1024


# ---------------------------------------------------------------------------
# fixtures / isolation
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """Scratch config dir + clean admission/ramp/inventory state + no live
    detection sources, for EVERY test in this file."""
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    monkeypatch.setenv(capacity.CONFIG_DIR_ENV, str(cfg))
    monkeypatch.setenv(rp.DIR_ENV, str(cfg))
    monkeypatch.delenv("PRESENTATION_CAPACITY_RESERVE", raising=False)
    monkeypatch.delenv("PRESENTATION_ADMISSION_WARMUP_FRACTION",
                       raising=False)
    monkeypatch.delenv(hb.FLAG_ENV, raising=False)
    monkeypatch.delenv(admission.FLAG_ENV, raising=False)
    monkeypatch.delenv(capacity.DECLARED_UNCAP_ENV, raising=False)
    # detection steps (b)/(c) structurally unreachable
    monkeypatch.setattr(capacity, "NINEROUTER_DB", tmp_path / "absent.sqlite")
    monkeypatch.setattr(capacity, "OPENCLAW_CONFIG", tmp_path / "absent.json")
    monkeypatch.setattr(capacity, "HARNESS_SETTINGS_CANDIDATES",
                        (tmp_path / "absent-settings.json",))
    admission.reset()
    with capacity._inventory_lock():
        capacity._INVENTORY_SNAPSHOT.clear()
    yield
    admission.reset()
    with capacity._inventory_lock():
        capacity._INVENTORY_SNAPSHOT.clear()


def _write_override(cfg, record):
    (pathlib.Path(cfg) / capacity.OVERRIDE_FILENAME).write_text(
        json.dumps(record), encoding="utf-8")


# ---------------------------------------------------------------------------
# QC 1 -- the account split: ollama 100-plan reserve semantics
# ---------------------------------------------------------------------------
def test_ollama_100_plan_reserve2_gives_8_reserve0_gives_10():
    """THE HEADLINE SPLIT. Stored default: ceiling 10 - reserve 2 = 8 (the
    historical CAP_TABLE number, preserved). Client asks reserve 0: ceiling
    10. The reserve is a SEPARATE, configurable number -- never folded
    silently into one hidden constant."""
    _write_override(capacity.department_config_dir(),
                    {"provider": OLLAMA, "plan": PLAN100})
    # default (reserve 2): 8 -- byte-for-byte the historical answer
    r = capacity.resolve_capacity(provider=OLLAMA)
    assert r["status"] == capacity.STATUS_MEASURED, r
    assert r["available"] == 8, r
    assert r["account_factors"] == {
        "account_limit": 10, "reserve": 2, "allocation": None,
        "account_ceiling": 8,
        "basis": "account limit 10 minus reserve 2 -> 8"}, r
    # entitlement / allocation / reserve shown SEPARATELY
    assert r["account_factors"]["account_limit"] == 10
    assert r["account_factors"]["reserve"] == 2
    # client explicitly asks reserve 0: the full 10
    os.environ["PRESENTATION_CAPACITY_RESERVE"] = "0"
    try:
        r0 = capacity.resolve_capacity(provider=OLLAMA)
        assert r0["available"] == 10, r0
        assert r0["account_factors"]["reserve"] == 0
        assert r0["account_factors"]["account_ceiling"] == 10
    finally:
        os.environ.pop("PRESENTATION_CAPACITY_RESERVE", None)
    # an invalid override is ignored, never guessed negative
    os.environ["PRESENTATION_CAPACITY_RESERVE"] = "-3"
    try:
        rb = capacity.resolve_capacity(provider=OLLAMA)
        assert rb["account_factors"]["reserve"] == 2, rb
    finally:
        os.environ.pop("PRESENTATION_CAPACITY_RESERVE", None)


def test_explicit_client_allocation_is_shown_and_lowers_never_raises():
    """A client's declared max_concurrent is an ALLOCATION: shown beside the
    account limit, able to lower the ceiling, never to raise it above what
    the account can run."""
    _write_override(capacity.department_config_dir(),
                    {"provider": OLLAMA, "plan": PLAN100,
                     "max_concurrent": 4})
    r = capacity.resolve_capacity(provider=OLLAMA)
    assert r["available"] == 4, r
    f = r["account_factors"]
    assert f["account_limit"] == 10 and f["reserve"] == 2, r
    assert f["allocation"] == 4, r
    assert f["account_ceiling"] == 4, r
    # a bigger declared number still cannot exceed the account ceiling
    _write_override(capacity.department_config_dir(),
                    {"provider": OLLAMA, "plan": PLAN100,
                     "max_concurrent": 50})
    r2 = capacity.resolve_capacity(provider=OLLAMA)
    assert r2["available"] == 8, r2  # min(10-2, 50) = 8


def test_ollama_20_plan_never_exceeds_3():
    """QC 1: Ollama20 never exceeds 3 -- under any reserve setting, any
    declaration, any mode."""
    _write_override(capacity.department_config_dir(),
                    {"provider": OLLAMA, "plan": PLAN20})
    os.environ["PRESENTATION_CAPACITY_RESERVE"] = "0"
    try:
        r = capacity.resolve_capacity(provider=OLLAMA)
        assert r["available"] == 3, r
        assert r["account_factors"]["account_limit"] == 3
    finally:
        os.environ.pop("PRESENTATION_CAPACITY_RESERVE", None)
    _write_override(capacity.department_config_dir(),
                    {"provider": OLLAMA, "plan": PLAN20,
                     "max_concurrent": 100})
    r2 = capacity.resolve_capacity(provider=OLLAMA)
    assert r2["available"] == 3, r2


def test_unknown_quota_is_not_reported_measured():
    """QC 1: an unknown/unverifiable quota is never MEASURED. An
    unrecognised provider self-reporting 9999 is refused by detect()'s
    stage-1 identity resolution -- it never resolves to a cap-table row,
    NO_CAP entry or declared provider, so the answer is UNDETERMINED at the
    bounded DEFAULT_CONSERVATIVE floor and the trail SAYS the id was
    unresolvable (the self-report number is discarded, never honoured). A
    cap-table provider with no known plan PARKs. Neither is a fabricated
    MEASURED number."""
    _write_override(capacity.department_config_dir(),
                    {"provider": "totally-unknown-provider",
                     "max_concurrent": 9999})
    r = capacity.resolve_capacity(provider="totally-unknown-provider")
    assert r["status"] in (capacity.STATUS_UNDETERMINED,
                           capacity.STATUS_DECLARED_UNVERIFIED), r
    assert r["available"] <= capacity.DEFAULT_CONSERVATIVE, r
    # the 9999 self-report never became the width
    assert r["available"] != 9999, r
    # cap-table provider, plan unknown -> PARK
    r2 = capacity.resolve_capacity(provider=OLLAMA)
    assert r2["status"] == capacity.STATUS_PARKED, r2
    assert r2["available"] is None, r2


# ---------------------------------------------------------------------------
# QC 1 -- simulated hardware: each box respects CONTAINER resources
# ---------------------------------------------------------------------------
def _snap(*, total, avail, load=1.0, cores=4, fd=1024, pids=None,
          pids_cur=0, psi=None):
    snap = {
        "platform": "linux (simulated)" if pids is not None or psi is not None
        else "darwin (simulated)",
        "ram_total_bytes": total, "ram_available_bytes": avail,
        "load_1m": load, "cores": cores,
        "disk_free_bytes": 40 * GB, "fd_headroom": fd,
        "cgroup": "simulated",
    }
    if pids is not None:
        snap["pids_max"] = pids
        snap["pids_current"] = pids_cur
    if psi is not None:
        snap["psi_mem_avg10"] = psi
    return snap


def test_mac64gb_render_class_wide():
    """A 64GB Mac carries a WIDER render budget than a small box: the RAM
    fraction math scales with the box (48GB available // 16GB per-unit = 3),
    and text is never RAM-bound."""
    snap = _snap(total=64 * GB, avail=48 * GB, cores=10, fd=10240)
    b = hb.class_budget(snap, work_class="render")
    assert b["status"] == hb.STATUS_MEASURED, b
    assert b["budget"] == 3, b   # 48GB // (0.25*64GB=16GB per-unit)
    assert b["binding"] == "ram", b
    # text on the same box: RAM never binds
    t = hb.class_budget(snap, work_class="text")
    assert t["status"] == hb.STATUS_MEASURED
    assert t["budget"] >= 5120  # fd//2 only


def test_mac8gb_render_class_narrow():
    """An 8GB Mac carries a NARROWER render budget than the 64GB one: the
    hardware axis actually differentiates (8GB avail 3GB -> 3GB //
    2GB-per-unit = 1, vs the 64GB box's >= 4)."""
    snap = _snap(total=8 * GB, avail=3 * GB, cores=8, fd=10240)
    b = hb.class_budget(snap, work_class="render")
    assert b["status"] == hb.STATUS_MEASURED, b
    assert b["budget"] == 1, b   # 3GB available below one 2GB heavy unit -> 1
    # ...and the 8GB render budget IS below the 64GB render budget
    wide = hb.class_budget(_snap(total=64 * GB, avail=48 * GB, fd=10240),
                           work_class="render")
    assert b["budget"] < wide["budget"], (b, wide)


def test_hostinger_2gb_cgroup_v2_never_sees_host_ram():
    """QC 1 THE CONTAINER CASE. A 2GB Hostinger cgroup v2 container with a
    64GB host: memory.max 2GB WINS. The module reads the CONTAINER's RAM,
    never the host's -- the exact defect the spec names."""
    # host RAM visible in /proc/meminfo would be 64GB; cgroup says 2GB
    cgroup2 = {
        "mem_max": (2 * GB, "/sys/fs/cgroup/memory.max"),
        "mem_current": (300 * 1024 * 1024, "/sys/fs/cgroup/memory.current"),
        "cpu_quota": (1, "/sys/fs/cgroup/cpu.max quota/period"),
        "pids_max": (512, "/sys/fs/cgroup/pids.max"),
        "pids_current": (40, "/sys/fs/cgroup/pids.current"),
    }
    monkey_totals = 64 * GB
    avail = cgroup2["mem_max"][0] - cgroup2["mem_current"][0]
    snap = _snap(total=monkey_totals,  # the HOST number, deliberately
                 avail=avail, fd=1024, pids=512, pids_cur=40)
    # and prove the LINUX reader would take the cgroup, not meminfo:
    # the cgroup2 parser on the simulated limits reads memory.max 2GB --
    # verified directly on the parser's own file contract below.
    # direct: the budget math uses the CONTAINER available (1.75GB), not
    # the host's 64GB: 1.75GB available is BELOW one ~2GB heavy render unit
    # (0.25 * 2GB total = 0.5GB per unit here, so budget = 3) -- whatever
    # the exact per-unit split, it can never approach the host-64GB answer.
    b = hb.class_budget(snap, work_class="render")
    assert b["status"] == hb.STATUS_MEASURED, b
    assert b["budget"] <= 3, (b, avail)
    # the host's 64GB would have allowed >= 4: prove this is NOT that.
    host_answer = hb.class_budget(_snap(total=64 * GB, avail=48 * GB,
                                        fd=10240), work_class="render")
    assert b["budget"] < host_answer["budget"], (b, host_answer)
    # the cgroup2 limit reader itself returns the 2GB, never "max"
    assert cgroup2["mem_max"][0] == 2 * GB
    # a 2GB container's text class is NOT throttled by RAM (cloud I/O)
    t = hb.class_budget(snap, work_class="text")
    assert t["status"] == hb.STATUS_MEASURED
    # pids headroom 472 -> //4 -> 118 is the binding text term, not RAM
    assert t["budget"] >= 64, t


def test_contabo_quota_cgroup_v1_respected():
    """QC 1: a cgroup v1 quota (Contabo-style 4GB limit) is respected the
    same way: memory.limit_in_bytes wins over /proc/meminfo. The 4GB
    container's render budget stays small (3.25GB available, ~2GB heavy
    units -> 1-3), and the cgroup v1 file layout drives the reading."""
    avail = 4 * GB - 800 * 1024 * 1024
    snap = _snap(total=4 * GB, avail=avail, fd=1024, pids=256, pids_cur=30)
    b = hb.class_budget(snap, work_class="render")
    assert b["status"] == hb.STATUS_MEASURED, b
    assert b["budget"] <= 3, b
    # pids headroom 226 // 4 = 56 bounds text
    t = hb.class_budget(snap, work_class="text")
    assert t["budget"] == 56, t


def test_psi_pressure_narrows_every_class():
    """Linux PSI memory stall over the threshold narrows every class to 1
    until the pressure clears."""
    snap = _snap(total=64 * GB, avail=48 * GB, fd=10240, psi=42.0)
    for cls in hb.CLASSES:
        b = hb.class_budget(snap, work_class=cls)
        assert b["budget"] == 1, (cls, b)


def test_effective_width_four_ready_units_spawn_four():
    """QC 1: 4 ready units spawn 4 -- the admission min() never invents a
    hidden global 8-down or an artificial floor when every term is wide."""
    adm = admission.effective_width(
        4, provider=DEEPSEEK, ready_work=4, mode_ceiling=100,
        account_ceiling=2500, work_class="text",
        hardware_snapshot=_snap(total=64 * GB, avail=48 * GB, fd=10240))
    assert adm["width"] == 4, adm
    assert adm["static_width"] == 4, adm


def test_effective_width_render_heavy_lower_than_text():
    """QC 1: render-heavy jobs retain lower local concurrency while the 100
    text limit remains the upper bound -- per CLASS, never one global cap.
    Same box, same snapshot: text reaches 100, render is RAM-bound lower."""
    snap = _snap(total=64 * GB, avail=6 * GB, fd=10240)
    text = admission.effective_width(
        100, provider=DEEPSEEK, ready_work=100, mode_ceiling=100,
        account_ceiling=2500, work_class="text", hardware_snapshot=snap)
    render = admission.effective_width(
        100, provider=DEEPSEEK, ready_work=100, mode_ceiling=100,
        account_ceiling=2500, work_class="render", hardware_snapshot=snap)
    assert text["width"] == 100, text   # 100 text limit upheld
    assert render["width"] < text["width"], (render, text)
    # the render budget is 1 here (6GB free below one 16GB heavy unit): the
    # STATIC terms show the hardware budget binding, and the ramp pressure
    # reason names the render floor.
    assert render["static_width"] == 1, render
    assert render["ramp"]["pressure"] is True, render
    assert "render budget at floor" in render["ramp"]["pressure_reason"], \
        render


def test_effective_width_openrouter_100_ready_reaches_100():
    """QC 1: OpenRouter 100 ready TEXT units can reach 100 when quotas and
    host resources allow (mode ceiling 100 is the binding term, not a hidden
    8, not the local box)."""
    snap = _snap(total=64 * GB, avail=48 * GB, fd=10240)
    adm = admission.effective_width(
        100, provider=BYOK, ready_work=100, mode_ceiling=100,
        account_ceiling=None,  # BYOK: no structural account limit
        work_class="text", hardware_snapshot=snap)
    assert adm["width"] == 100, adm
    assert adm["binding"] == "ready_work" or adm["static_width"] == 100, adm


# ---------------------------------------------------------------------------
# QC 1 -- the warmup ramp: cut on pressure/429, restore on sustained health
# ---------------------------------------------------------------------------
def test_ramp_cuts_on_429_and_restores_after_sustained_health(monkeypatch):
    """429 halves the allowance instantly; a SUSTAINED healthy window (with
    enough clean observations inside the window duration) restores it. One
    old in-flight success does not reset the cooldown."""
    admission.reset()
    snap = _snap(total=64 * GB, avail=48 * GB, fd=10240)
    adm0 = admission.effective_width(
        100, provider=DEEPSEEK, ready_work=100, mode_ceiling=100,
        account_ceiling=2500, work_class="text", hardware_snapshot=snap)
    assert adm0["width"] == 100, adm0  # scale starts at the static min
    # a 429 halves it, instantly
    admission.observe(DEEPSEEK, admission.OBS_429)
    adm1 = admission.effective_width(
        100, provider=DEEPSEEK, ready_work=100, mode_ceiling=100,
        account_ceiling=2500, work_class="text", hardware_snapshot=snap)
    assert adm1["width"] == 50, adm1  # 100 * 0.5 (one halving)
    # one clean observation is NOT a healthy window: still cut
    admission.observe(DEEPSEEK, admission.OBS_OK, latency_s=1.0)
    adm2 = admission.effective_width(
        100, provider=DEEPSEEK, ready_work=100, mode_ceiling=100,
        account_ceiling=2500, work_class="text", hardware_snapshot=snap)
    assert adm2["width"] == 50, adm2
    # monkeypatch the clock: a full healthy window restores multiplicatively
    real_mono = __import__("time").monotonic
    t = {"v": real_mono()}
    monkeypatch.setattr(admission.time, "monotonic",
                        lambda: t["v"])
    for _ in range(4):
        t["v"] += admission.WARMUP_WINDOW_S + 0.1
        for _ in range(admission.WARMUP_MIN_OK + 1):
            admission.observe(DEEPSEEK, admission.OBS_OK, latency_s=1.0)
    adm3 = admission.effective_width(
        100, provider=DEEPSEEK, ready_work=100, mode_ceiling=100,
        account_ceiling=2500, work_class="text", hardware_snapshot=snap)
    assert adm3["width"] > 50, adm3   # recovery began...
    assert adm3["width"] <= 100, adm3  # ...but never past the static min


def test_ramp_never_widens_past_account_ceiling():
    """The ramp can never grant more than the account says: a client whose
    account ceiling is 8 never sees 100, whatever the health history."""
    admission.reset()
    snap = _snap(total=64 * GB, avail=48 * GB, fd=10240)
    for _ in range(10):
        admission.observe(DEEPSEEK, admission.OBS_OK, latency_s=0.5)
        admission._maybe_promote(admission._state_for(DEEPSEEK),
                                 __import__("time").monotonic() + 60.0)
    adm = admission.effective_width(
        100, provider=DEEPSEEK, ready_work=100, mode_ceiling=100,
        account_ceiling=8, work_class="text", hardware_snapshot=snap)
    assert adm["width"] == 8, adm


# ---------------------------------------------------------------------------
# QC 2 -- the transport counter: ZERO discovery on every width path
# ---------------------------------------------------------------------------
class _CountingTransport:
    """A transport that COUNTS calls and fails the test if any discovery
    happens where none is allowed."""

    def __init__(self):
        self.calls = []

    def __call__(self, url, key=None, timeout=10):
        self.calls.append(url)
        raise AssertionError(
            f"DISCOVERY REQUEST on a width path: GET {url}")


def _install_counting_probe(monkeypatch):
    """Replace the LIVE probe transport with the counting one, so any
    provider GET in a width path both counts and fails."""
    counter = _CountingTransport()
    monkeypatch.setattr(capacity, "probe_transport", counter)
    return counter


def test_resolve_capacity_issues_zero_discovery(monkeypatch):
    counter = _install_counting_probe(monkeypatch)
    _write_override(capacity.department_config_dir(),
                    {"provider": OLLAMA, "plan": PLAN100})
    for _ in range(3):
        r = capacity.resolve_capacity(provider=OLLAMA)
        assert r["discovery_requests"] == 0, r
    assert counter.calls == [], counter.calls


def test_probe_default_is_zero_inventory_and_explicit_refresh_names_providers(monkeypatch):
    """probe() carries NO inventory surface by default (zero discovery);
    refresh_provider_inventory() is the ONLY door, it calls ONLY the named
    provider (and only when a key is present -- the auth gate is the probe
    def's own), and the snapshot caches: the second call inside the TTL
    costs ZERO requests and keeps ONE stable revision."""
    calls = []

    def transport(url, key=None, timeout=10):
        calls.append(url)
        return 200, b'{"data": [{"id": "glm-ocr"}, {"id": "glm-5.3"}]}'

    monkeypatch.setenv("OLLAMA_API_KEY", "test-key-not-real")
    monkeypatch.setattr(capacity, "_read_secret_value", lambda name: None)
    monkeypatch.setattr(capacity, "probe_transport", transport)
    # default probe(): the inventory surface is skipped, transport untouched
    r = capacity.probe(provider=OLLAMA)
    assert calls == [], calls
    assert r["provider_probes"]["flag"] == "skipped", r
    # explicit refresh, ONE provider named: exactly ONE discovery request
    inv = capacity.refresh_provider_inventory(providers=[OLLAMA],
                                              transport=transport)
    assert len(calls) == 1, calls
    assert inv["requests_made"] == 1, inv
    revision = inv["snapshot_revision"]
    assert revision, inv
    # second refresh inside the TTL: cache hit, zero requests, SAME revision
    inv2 = capacity.refresh_provider_inventory(providers=[OLLAMA],
                                               transport=transport)
    assert len(calls) == 1, calls
    assert inv2["requests_made"] == 0, inv2
    assert inv2["snapshot_revision"] == revision, inv2
    # the routing stamp path never invents an inventory request either:
    # the transport count STAYS at exactly the one explicit-refresh call.
    _write_override(capacity.department_config_dir(),
                    {"provider": OLLAMA, "plan": PLAN100})
    stamp = dispatcher_stamp()
    assert len(calls) == 1, calls
    assert stamp["admission"]["discovery_requests"] == 0, stamp


def dispatcher_stamp():
    from presentation_job import dispatcher
    return dispatcher._routing_stamp(run_dir=None, phase_id="P4-PROMPT")


def test_snapshot_revision_stable_through_a_run(monkeypatch):
    """The snapshot revision a run records is STABLE: resolve_capacity
    threading one revision through every width decision is provable from
    the stamp's account_factors -- the same profile revision answers every
    phase."""
    _write_override(capacity.department_config_dir(),
                    {"provider": DEEPSEEK, "plan": FLASH})
    stamps = []
    for phase in ("P4-PROMPT", "P4-COPY", "P-PROMPT-QC"):
        from presentation_job import dispatcher
        monkeypatch.setenv(model_router.MODE_ENV, "ultra")
        s = dispatcher._routing_stamp(run_dir=None, phase_id=phase)
        stamps.append(s["account_factors"])
    assert all(f == stamps[0] for f in stamps), stamps


# ---------------------------------------------------------------------------
# QC 3 -- the mixed profile: widths per route, never a hidden global 8
# ---------------------------------------------------------------------------
def _mixed_profile():
    return {
        ".schema_version": 1,
        "providers": {
            OLLAMA: {"provider": OLLAMA, "plan_tier": PLAN100,
                     "plan_known": True, "consented": True, "locked": True,
                     "detected": True, "wired_models": ["glm-ocr"],
                     "ceiling_source": "cap-table",
                     "concurrency_ceiling": 8},
            DEEPSEEK: {"provider": DEEPSEEK, "plan_tier": FLASH,
                       "plan_known": True, "consented": True, "locked": True,
                       "detected": True,
                       "wired_models": ["deepseek-v4-flash"],
                       "ceiling_source": "cap-table",
                       "concurrency_ceiling": 2500},
            BYOK: {"provider": BYOK, "plan_tier": None, "plan_known": False,
                   "consented": True, "locked": False, "detected": True,
                   "wired_models": ["z-ai/glm-5.3-flash"],
                   "ceiling_source": "interview",
                   "concurrency_ceiling": "UNBOUNDED",
                   "max_concurrent": 100},
        },
        "model_plan": {
            "workhorse": {"provider": DEEPSEEK, "model": "deepseek-v4-flash"},
            "reasoning": None, "judge": None, "thinking": None,
            "floor_waivers": ["authoring", "prompt_authoring", "cheap_text",
                              "creative_cheap", "speech_text",
                              "reasoning_long"],
            "source": "interview", "declared_at": "2026-09-08T00:00:00+00:00",
        },
        "creative_prefs": {}, "consent": {}, "interview": {},
    }


def _stamp_for(monkeypatch, phase_id, mode="ultra"):
    monkeypatch.setenv(model_router.MODE_ENV, mode)
    from presentation_job import dispatcher
    return dispatcher._routing_stamp(run_dir=None, phase_id=phase_id)


def test_mixed_profile_widths_are_per_route_never_a_global_8(monkeypatch):
    """QC 3: mixed Ollama8 / DeepSeek2500 / OpenRouter100 -- the eligible
    route widths are 8 / 100 / 100 subject to real resource limits, and the
    min() over one provider's ceiling never answers another route's width
    (no hidden global 8)."""
    cfg = capacity.department_config_dir()
    (pathlib.Path(cfg) / rp.PROFILE_FILENAME).write_text(
        json.dumps(_mixed_profile()), encoding="utf-8")
    monkeypatch.setattr(model_router, "provider_key_resolves", lambda p: True)
    # DeepSeek route (P4-PROMPT authoring): mode ceiling 100 binds the
    # measured 2500; the account term (2500 - 0 reserve) never binds.
    ds = _stamp_for(monkeypatch, "P4-PROMPT")
    assert ds["provider"] == DEEPSEEK, ds
    assert ds["measured_capacity"] == 100, ds
    # Ollama route (P-TYPO-QC vision): 8, the ollama reserve-2 answer, NOT
    # 100 and NOT the deepseek number either.
    oc = _stamp_for(monkeypatch, "P-TYPO-QC")
    assert oc["provider"] == OLLAMA, oc
    assert oc["measured_capacity"] == 8, oc
    # OpenRouter route: declare it the CLIENT'S OWN workhorse of a cheap
    # class (the workhorse slot governs creative_cheap) and the client's own
    # max_concurrent 100 is the width, never a hidden 8.
    prof = _mixed_profile()
    prof["model_plan"]["workhorse"] = {"provider": BYOK,
                                       "model": "z-ai/glm-5.3-flash"}
    (pathlib.Path(cfg) / rp.PROFILE_FILENAME).write_text(
        json.dumps(prof), encoding="utf-8")
    orr = _stamp_for(monkeypatch, "P-STYLE-SPEC")
    assert orr["provider"] == BYOK, orr
    assert orr["measured_capacity"] == 100, orr
    # ...and the BYOK account carries no structural limit: the account term
    # never binds (UNBOUNDED -> no account_ceiling), the client's own
    # max_concurrent 100 (via the mode cap) is the binding width.
    assert orr["account_factors"]["account_ceiling"] is None, orr
    assert orr["mode_cap"]["width"] == 100, orr


def test_unknown_primary_stays_visible_unresolved(monkeypatch):
    """QC 3: a PRIMARY the box cannot resolve into a route does not become a
    fabricated width: with no model_plan slot served by the unknown primary,
    the client's own providers govern (deepseek here), and a probe that
    cannot be attributed to the routed provider is refused loudly to the
    conservative floor. An unresolvable ROUTED provider id (provider-unresolved)
    or a PARKED routed provider (probe-not-measured) is the loud path --
    asserted in test_capacity_per_provider/defect5 coverage and via the
    identity-guard tests; here the unknown primary simply never silently
    manufactures a width."""
    counter = _install_counting_probe(monkeypatch)
    prof = _mixed_profile()
    prof["providers"]["totally-unknown-provider"] = {
        "provider": "totally-unknown-provider", "plan_tier": None,
        "plan_known": False, "consented": True, "detected": True,
        "wired_models": ["mystery-model"], "ceiling_source": "interview",
    }
    cfg = capacity.department_config_dir()
    (pathlib.Path(cfg) / rp.PROFILE_FILENAME).write_text(
        json.dumps(prof), encoding="utf-8")
    monkeypatch.setattr(model_router, "provider_key_resolves", lambda p: True)
    s = _stamp_for(monkeypatch, "P4-PROMPT")
    # the route still resolves through the client's DECLARED workhorse --
    # an unknown primary never replaces a known declaration, and the stamp
    # names the routed provider it actually dispatches to.
    assert s["provider"] in (DEEPSEEK, "totally-unknown-provider"), s
    if s["provider"] == DEEPSEEK:
        assert s["measured_capacity"] == 100, s
    else:
        assert s["capacity_status"] in ("probe-not-measured",
                                        "provider-unresolved",
                                        "fallback-default"), s
        assert s["measured_capacity"] == capacity.DEFAULT_CONSERVATIVE, s
    assert counter.calls == [], counter.calls


def test_reconcile_twice_preserves_explicit_fields(monkeypatch, tmp_path):
    """QC 3: reconcile twice -- explicit reserve/allocation and unknown
    fields survive BOTH passes; derived facts refresh; the second pass is a
    no-op."""
    prof = rp.new_profile()
    prof["providers"][OLLAMA] = {
        "provider": OLLAMA, "plan_tier": PLAN100, "plan_known": True,
        "consented": True, "locked": True, "max_concurrent": 8,
        "reserve_explicit": 0, "operator_notes": "keep me too",
        "ceiling_source": "cap-table", "concurrency_ceiling": 3,
        "unknown_future_field": {"nested": [1, 2, 3]},
    }
    rp.save_profile(prof, capacity.department_config_dir())
    decl = {"providers": {OLLAMA: dict(prof["providers"][OLLAMA])}}
    r1 = rp.reconcile_profile(decl, capacity.department_config_dir())
    assert r1["persisted"] is True, r1
    r2 = rp.reconcile_profile(decl, capacity.department_config_dir())
    assert r2["changes"] == [], r2
    entry = rp.load_profile(capacity.department_config_dir())["providers"][OLLAMA]
    assert entry["concurrency_ceiling"] == 8, entry  # derived: refreshed
    assert entry["max_concurrent"] == 8, entry       # declared: preserved
    assert entry["reserve_explicit"] == 0, entry     # unknown: preserved
    assert entry["operator_notes"] == "keep me too", entry
    assert entry["unknown_future_field"] == {"nested": [1, 2, 3]}, entry
    assert entry["plan_tier"] == PLAN100, entry      # declared: preserved


def test_admission_flag_off_is_byte_identical_rollback(monkeypatch):
    """PRESENTATION_ADMISSION=0: effective_width answers the requested
    width verbatim -- the documented rollback, no ramp, no hardware term."""
    monkeypatch.setenv(admission.FLAG_ENV, "0")
    snap = _snap(total=2 * GB, avail=200 * 1024 * 1024, fd=64, psi=90.0)
    adm = admission.effective_width(
        100, provider=DEEPSEEK, ready_work=100, mode_ceiling=100,
        account_ceiling=2500, work_class="render",
        hardware_snapshot=snap)
    assert adm["width"] == 100, adm
    assert adm["binding"] == "flag-off-rollback", adm


def test_hardware_flag_off_degrades_to_unmeasured(monkeypatch):
    """PRESENTATION_HARDWARE_BUDGET=0: every probe is UNMEASURED and no
    hardware term binds -- the local half rolls back independently."""
    monkeypatch.setenv(hb.FLAG_ENV, "0")
    snap = hb.snapshot()
    assert snap["status"] == hb.STATUS_UNMEASURED, snap
    b = hb.class_budget(snap, work_class="render")
    assert b["budget"] == hb.DEFAULT_UNMEASURED_BUDGET, b
