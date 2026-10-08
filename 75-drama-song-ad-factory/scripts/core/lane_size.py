#!/usr/bin/env python3
"""Swarm sizing for Skill 75 (manual 02 H4 + Part D1-D6 + B7 balance term). Stdlib only.

Run before each parallel stage (never once per session -- load changes) and start no
more workers than the printed "agents":

    python3 scripts/core/lane_size.py --runtime openclaw|claude-code --provider <id> \
        [--ollama-plan 20|100] [--balance N] [--max-job-price N] [--units N] \
        [--openclaw-config PATH]

It prints ONE JSON line:
    {"agents":N,"workflows":W,"agents_per_workflow":P,"kie_inflight":K,
     "ffmpeg_jobs":F,"ffmpeg_threads":T,"retry_in_s":15?,"inputs":{...}}
"workflows"/"agents_per_workflow" apply to Claude Code/claude-nine only (openclaw: null).
"retry_in_s" is present only under D4's load guard (caller decides to wait -- this
module never loops and never sleeps).

D4 load guard (library, not an infinite CLI loop): when load1 > HOT_LOAD*x cores_eff or
ram_avail_gb < RESERVE_GB + GB_PER_AGENT, callers get retry_in_s=15 and re-measure.
After 20 waits (5 minutes), continue with ONE lane and tell the client:
    "Your server is busy, so this ad will take longer."
Never wait forever; never start more than "agents".

The Ollama Cloud plan tier cannot be detected by a machine: ask the client once at setup
("Is your Ollama Cloud plan $20 or $100 a month?") and store it next to the style file.
With --ollama-plan omitted the tool assumes the $20 floor (agents <= 3). If any 429
error arrives during a stage, drop "agents" by one for the rest of the stage.

Container reader copied from 999's nine-router-setup/scripts/common/capacity_probe.py
(:66-86, self-test cases :101-111) per H4 step 1 -- function body copied, never imported
across repos -- and extended with memory.current for the Part D ram-availability rule.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import subprocess
import sys
from pathlib import Path

# ── D2 calibration constants (the one place; every one overridable per call) ──
DEFAULTS = {
    "RESERVE_GB": 2.0,          # OS + gateway + Command Center (capacity-monitor.sh:105)
    "GB_PER_AGENT": 1.5,        # capacity-monitor.sh:102, 999 capacity_probe.py:18
    "AGENT_PER_FREE_CORE": 2,   # language-model workers mostly wait on the network
    "HOT_LOAD": 0.85,           # fraction of cores_eff above which no new worker starts
}
RESERVE_GB = DEFAULTS["RESERVE_GB"]
GB_PER_AGENT = DEFAULTS["GB_PER_AGENT"]
AGENT_PER_FREE_CORE = DEFAULTS["AGENT_PER_FREE_CORE"]
HOT_LOAD = DEFAULTS["HOT_LOAD"]

GIB = 1024 ** 3
UNLIMITED = 1 << 60          # cgroup "no limit" sentinels sit far above any real host
RETRY_IN_S = 15              # D4: re-measure cadence
MAX_WAITS = 20               # D4: 20 waits x 15 s = 5 minutes, then continue with ONE lane
BUSY_MESSAGE = "Your server is busy, so this ad will take longer."
CC_RUNTIME_CAP = 10 * 50     # Claude Code/claude-nine: 10 per workflow, 50 workflows
KIE_BURST_MAX = 8            # keeps bursts under KIE's 20 new jobs / 10 s (B7)
KIE_PRICE_SAFETY = 1.3       # B7: balance must cover price x 1.3
FFMPEG_LOAD_DIVISOR = 4      # D3: ffmpeg_jobs = max(1, floor(cores_eff / 4))
PROVIDER_CAPS = {"ollama-cloud": {20: 3, 100: 10}}  # plan price -> agent cap
NO_CAP_PROVIDERS = frozenset({"openrouter", "deepseek-direct", "anthropic"})


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None


# ── D1 container reader (copied + extended) ──────────────────────────────────
def container_limits(read=_read):
    """Return (ram_max_gb|None, cores_eff|None, memory_current_gb|None, label).

    cgroup v2 first, then v1. "max"/unlimited sentinels are ignored.
    """
    ram = ram_now = cores = None
    label = []
    m = read("/sys/fs/cgroup/memory.max")
    if m is not None:  # v2
        if m.isdigit() and int(m) < UNLIMITED:
            ram = int(m) / GIB
        c = (read("/sys/fs/cgroup/cpu.max") or "").split()
        if len(c) == 2 and c[0].isdigit() and c[1].isdigit() and int(c[1]) > 0:
            cores = int(c[0]) / int(c[1])
        elif len(c) == 2 and c[0] == "max":  # cpu.max "max P" = no cpu quota
            cores = None
        cur = read("/sys/fs/cgroup/memory.current")
        if cur and cur.isdigit():
            ram_now = int(cur) / GIB
        label.append("cgroup-v2")
    else:  # v1
        m = read("/sys/fs/cgroup/memory/memory.limit_in_bytes")
        if m and m.isdigit() and int(m) < UNLIMITED:
            ram = int(m) / GIB
        q, p = read("/sys/fs/cgroup/cpu/cpu.cfs_quota_us"), read("/sys/fs/cgroup/cpu/cpu.cfs_period_us")
        if q and p and q.lstrip("-").isdigit() and p.isdigit() and int(q) > 0 and int(p) > 0:
            cores = int(q) / int(p)
        cur = read("/sys/fs/cgroup/memory/memory.usage_in_bytes")
        if cur and cur.isdigit():
            ram_now = int(cur) / GIB
        if m is not None or q is not None:
            label.append("cgroup-v1")
    return ram, cores, ram_now, "+".join(label)


def cores_eff(read=_read, system=None):
    """Effective cores: container limit beats host total (D1)."""
    system = system or platform.system()
    if system == "Darwin":
        return float(_sysctl_int("hw.physicalcpu")), "darwin"
    ram_max, cc, _ram_now, label = container_limits(read)
    if cc is not None:
        return cc, label or "cgroup"
    try:
        return float(len(os.sched_getaffinity(0))), "linux"
    except AttributeError:  # pragma: no cover
        return float(os.cpu_count() or 1), "linux"


def ram_avail_gb(read=_read, system=None):
    """Available RAM in GB per D1; container limit wins over host numbers."""
    system = system or platform.system()
    if system == "Darwin":
        avail = _darwin_vm_stat()
        if avail is not None:
            return avail
        return _sysctl_int("hw.memsize") / GIB * 0.5  # fallback: total x 0.5
    avail = _linux_mem_available(read)
    if avail is None:
        return 0.0
    ram_max, _c, ram_now, _label = container_limits(read)
    if ram_max is not None and ram_now is not None:
        avail = min(avail, max(0.0, ram_max - ram_now))
    return avail


def _linux_mem_available(read=_read):
    for line in (read("/proc/meminfo") or "").splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) / 1024  # kB -> GB
    return None


def _darwin_vm_stat():
    """(free + inactive + speculative) x page size, from vm_stat (D1)."""
    try:
        out = subprocess.run(["vm_stat"], capture_output=True, text=True,
                             timeout=5, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    page = None
    for line in out.splitlines():
        if "page size" in line and "bytes" in line:
            digits = "".join(ch for ch in line if ch.isdigit())
            if digits:
                page = int(digits)
    if not page:
        return None
    total = 0
    for key in ("Pages free", "Pages inactive", "Pages speculative"):
        for line in out.splitlines():
            if line.startswith(key + ":"):
                digits = line.split(":")[1].strip().rstrip(".")
                if digits.isdigit():
                    total += int(digits)
                break
        else:
            return None  # a missing bucket means the parse is untrustworthy
    return total * page / GIB


def _sysctl_int(name):
    return int(subprocess.run(["sysctl", "-n", name], capture_output=True, text=True,
                              timeout=5, check=True).stdout.strip())


# ── D2 constants resolved per call (overridable kwargs, defaults in one place) ──
def _cal(reserve_gb=RESERVE_GB, gb_per_agent=GB_PER_AGENT,
         agent_per_free_core=AGENT_PER_FREE_CORE, hot_load=HOT_LOAD):
    return reserve_gb, gb_per_agent, agent_per_free_core, hot_load


# ── D3 formulas ──────────────────────────────────────────────────────────────
def machine_cap(ram_avail, load1, cores, reserve_gb, gb_per_agent, agent_per_free_core):
    free_cores = max(0.5, cores - min(load1, cores))
    ram_side = math.floor((ram_avail - reserve_gb) / gb_per_agent)
    core_side = math.floor(free_cores * agent_per_free_core)
    return max(1, min(ram_side, core_side)), round(free_cores, 2)


def provider_cap(provider, ollama_plan=None):
    """Plan-tier cap by provider id; None = machine-only (D3). Mixed lanes: pass a list."""
    if isinstance(provider, (list, tuple)):  # mixed lanes: each provider caps its own users
        caps = [provider_cap(p, ollama_plan) for p in provider]
        caps = [c for c in caps if c is not None]
        return min(caps) if caps else None
    caps = PROVIDER_CAPS.get(_norm(provider))
    if caps is not None:
        return caps.get(int(ollama_plan or 20), caps[20])  # unknown plan -> $20 floor (conservative)
    if _norm(provider) in NO_CAP_PROVIDERS:
        return None
    return None  # unknown provider -> machine only


def _norm(provider):
    return str(provider).strip().lower()


def runtime_cap(runtime, openclaw_config=None, profile_dir=None):
    """OpenClaw: min(maxConcurrent keys found, config reachable only via path) - 1.
    Claude Code/claude-nine: fixed 10 x 50 = 500 (D3)."""
    if runtime == "claude-code":
        return CC_RUNTIME_CAP, {}
    keys = read_maxconcurrent(openclaw_config, profile_dir)
    caps = [v for v in keys.values() if isinstance(v, (int, float)) and v > 0]
    if not caps:
        return None, keys            # nothing reachable -> no runtime ceiling (machine only)
    return max(0, math.floor(min(caps)) - 1), keys


def _dig(obj, dotted):
    cur = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def read_maxconcurrent(openclaw_config=None, profile_dir=None):
    """maxConcurrent from the box's config (path argument only, no network) plus
    .capacity-profile.json maxConcurrentAgents next to the skill (and next to the
    config, when given). Both keys from capacity-monitor.sh."""
    keys = {}
    if openclaw_config:
        try:
            cfg = json.loads(Path(openclaw_config).read_text(encoding="utf-8"))
            for dotted in ("agents.defaults.subagents.maxConcurrent",
                           "agents.defaults.maxConcurrent"):
                v = _dig(cfg, dotted)
                if v is not None:
                    keys[dotted] = v
        except (OSError, ValueError):
            keys["config-read-error"] = openclaw_config
        prof = Path(openclaw_config).resolve().parent / ".capacity-profile.json"
        got = _profile_cap(prof)
        if got is not None:
            keys["profile"] = got
    if profile_dir:
        got = _profile_cap(Path(profile_dir) / ".capacity-profile.json")
        if got is not None:
            keys["profile"] = got
    return keys


def _profile_cap(path):
    try:
        prof = json.loads(Path(path).read_text(encoding="utf-8"))
        v = prof.get("maxConcurrentAgents")
        return v if isinstance(v, (int, float)) and v > 0 else None
    except (OSError, ValueError):
        return None


def kie_inflight(units_in_stage, balance=None, max_job_price=None):
    """min(units, 8) minus the B7 balance term when a balance is given."""
    cap = min(max(0, math.floor(units_in_stage)), KIE_BURST_MAX)
    if balance is not None and max_job_price is not None and max_job_price > 0:
        cap = min(cap, math.floor(max(0.0, balance) / (max_job_price * KIE_PRICE_SAFETY)))
    return max(0, cap)


def ffmpeg_pool(cores):
    jobs = max(1, math.floor(cores / FFMPEG_LOAD_DIVISOR))
    return jobs, max(1, math.floor((cores - 1) / jobs))


# ── D4 load guard (library; the caller waits and re-measures) ────────────────
def is_hot(load1, ram_avail, cores, hot_load=HOT_LOAD, reserve_gb=RESERVE_GB,
           gb_per_agent=GB_PER_AGENT):
    """True when a new worker/ffmpeg job must wait RETRY_IN_S and re-measure.

    After MAX_WAITS waits (MAX_WAITS x RETRY_IN_S = 20 x 15 s = 5 minutes), proceed
    with ONE lane and tell the client: BUSY_MESSAGE. Never wait forever; never
    start more than "agents".
    """
    return load1 > hot_load * cores or ram_avail < reserve_gb + gb_per_agent


def _num(v, nd=2):
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return round(v, nd) if isinstance(v, float) else v


def size(runtime, provider, ollama_plan=None, balance=None, max_job_price=None,
         units=999, openclaw_config=None, load1=None, ram_avail=None, cores=None, **cal_over):
    """One sizing decision. Returns the D3 line dict (retry_in_s absent unless hot).

    ram_avail / cores: inject a measured value directly (self-tests, or a caller that
    already re-measured for a D4 retry); when omitted they are probed on this box.
    """
    reserve_gb, gb_per_agent, agent_per_free_core, hot_load = _cal(**cal_over)
    if cores is None:
        cores, src_eff = cores_eff()
        src = src_eff
    else:
        src = "injected"
    if ram_avail is None:
        ram = ram_avail_gb()
    else:
        ram = float(ram_avail)
    if load1 is None:
        try:
            load1 = os.getloadavg()[0]
        except OSError:  # pragma: no cover
            load1 = 0.0
    load_used = min(load1, cores)
    machine, free_cores = machine_cap(ram, load_used, cores, reserve_gb, gb_per_agent,
                                      agent_per_free_core)
    prov = provider_cap(provider, ollama_plan)
    rt, mc_keys = runtime_cap(runtime, openclaw_config)
    caps = [c for c in (machine, prov, rt) if c is not None]
    agents = max(1, min(min(caps), max(1, math.floor(units))))
    agents_per_workflow = workflows = None
    if runtime == "claude-code":
        agents_per_workflow = min(10, agents)
        workflows = math.ceil(agents / agents_per_workflow)
    k = kie_inflight(units, balance, max_job_price)
    jobs, threads = ffmpeg_pool(cores)
    line = {
        "agents": agents, "workflows": workflows,
        "agents_per_workflow": agents_per_workflow, "kie_inflight": k,
        "ffmpeg_jobs": jobs, "ffmpeg_threads": threads,
        "inputs": {
            "runtime": runtime, "provider": provider,
            "ollama_plan": int(ollama_plan) if ollama_plan else None,
            "units_in_stage": max(1, math.floor(units)),
            "cores_eff": _num(cores), "ram_avail_gb": round(ram, 2),
            "load1": round(load1, 2), "load_used": round(load_used, 2),
            "free_cores": free_cores, "machine_cap": machine,
            "provider_cap": prov, "runtime_cap": rt,
            "maxConcurrent_keys": mc_keys or None, "balance": balance,
            "max_job_price": max_job_price, "source": src,
        },
    }
    if is_hot(load1, ram, cores, hot_load, reserve_gb, gb_per_agent):
        line["retry_in_s"] = RETRY_IN_S
    return line


# ── CLI (prints one JSON line, never loops) ───────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(description="Skill 75 swarm sizing (one JSON line)")
    ap.add_argument("--runtime", choices=["openclaw", "claude-code"])
    ap.add_argument("--provider")
    ap.add_argument("--ollama-plan", type=int, choices=[20, 100], default=None)
    ap.add_argument("--balance", type=float, default=None)
    ap.add_argument("--max-job-price", type=float, default=None)
    ap.add_argument("--units", type=float, default=999)
    ap.add_argument("--openclaw-config", default=None)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.runtime is None or args.provider is None:
        ap.error("--runtime and --provider are required (or use --selftest)")
    print(json.dumps(size(args.runtime, args.provider, args.ollama_plan, args.balance,
                          args.max_job_price, args.units, args.openclaw_config)))
    return 0


# ── self-test: assert-based, no framework ─────────────────────────────────────
def selftest():
    GIBV = GIB
    ok = []

    def check(name, actual, want):
        assert actual == want, f"{name}: got {actual!r}, want {want!r}"
        ok.append(name)

    # copied reader cases (capacity_probe.py:101-111 shapes) + memory.current
    rd = lambda files: (lambda p: files.get(p))
    check("cgroup v2 cpu 200000/100000 -> 2 cores",
          cores_eff(rd({"/sys/fs/cgroup/memory.max": "max",
                        "/sys/fs/cgroup/cpu.max": "200000 100000"}), "Linux")[0], 2.0)
    check("cgroup v2 'max 100000' -> falls through to affinity/host",
          cores_eff(rd({"/sys/fs/cgroup/cpu.max": "max 100000"}), "Linux")[0] >= 1.0, True)
    check("cgroup v1 400000/100000 -> 4 cores",
          cores_eff(rd({"/sys/fs/cgroup/cpu/cpu.cfs_quota_us": "400000",
                        "/sys/fs/cgroup/cpu/cpu.cfs_period_us": "100000"}), "Linux")[0], 4.0)
    check("cgroup v1 quota -1 ignored -> fallback",
          cores_eff(rd({"/sys/fs/cgroup/cpu/cpu.cfs_quota_us": "-1",
                        "/sys/fs/cgroup/cpu/cpu.cfs_period_us": "100000"}), "Linux")[0] >= 1.0, True)
    check("mac uses physicalcpu key",
          cores_eff(rd({}), "Darwin")[0] > 0, True)
    # ram rules
    check("linux MemAvailable",
          round(_linux_mem_available() or -0, 2) >= 0 if _read("/proc/meminfo") else True, True)
    check("cgroup v2 ram cap min(MemAvailable, max-current)",
          round(ram_avail_gb(rd({"/proc/meminfo": "MemAvailable: 8000000 kB\n",
                                 "/sys/fs/cgroup/memory.max": str(6 * GIBV),
                                 "/sys/fs/cgroup/memory.current": str(2 * GIBV)}), "Linux"), 2),
          round(min(8000000 / 1024, 4 * GIBV / GIB), 2))
    check("v2 memory.max 'max' sentinel ignored",
          round(ram_avail_gb(rd({"/proc/meminfo": "MemAvailable: 8000000 kB\n",
                                 "/sys/fs/cgroup/memory.max": "max",
                                 "/sys/fs/cgroup/memory.current": str(2 * GIBV)}), "Linux"), 2),
          round(8000000 / 1024, 2))
    # D2 formula cases (worked example: 10 cores, 8 GB free, load 2)
    mc, fc = machine_cap(8, 2, 10, RESERVE_GB, GB_PER_AGENT, AGENT_PER_FREE_CORE)
    check("machine_cap 10c/8GB/load2 -> 4", mc, 4)
    check("free_cores 10-2 = 8", fc, 8)
    check("provider ollama $20 -> 3", provider_cap("ollama-cloud", 20), 3)
    check("provider ollama $100 -> 10", provider_cap("ollama-cloud", 100), 10)
    check("provider ollama no plan -> $20 floor", provider_cap("ollama-cloud", None), 3)
    check("provider openrouter -> no cap", provider_cap("openrouter"), None)
    check("provider deepseek-direct -> no cap", provider_cap("deepseek-direct"), None)
    check("provider anthropic -> no cap", provider_cap("anthropic"), None)
    check("unknown provider -> machine only", provider_cap("mystery"), None)
    # agents: never below 1, never above machine_cap
    line = size("claude-code", "openrouter", units=999, load1=2.0, cores=10, ram_avail=20)
    check("injected cores reach the formulas", line["inputs"]["cores_eff"], 10)
    check("injected ram reaches the formulas", line["inputs"]["ram_avail_gb"], 20.0)
    check("agents >= 1", line["agents"] >= 1, True)
    check("agents <= machine_cap", line["agents"] <= line["inputs"]["machine_cap"], True)
    check("agents >= 1", line["agents"] >= 1, True)
    check("agents <= machine_cap", line["agents"] <= line["inputs"]["machine_cap"], True)
    # B7: balance 100, price 30 -> kie_inflight 2
    check("B7 balance 100 / price 30 -> 2", kie_inflight(999, 100, 30), 2)
    check("no balance -> cap 8 only", kie_inflight(999), 8)
    check("kie never below 0", kie_inflight(0, 0, 30), 0)
    # ffmpeg pools per worked-example column
    for cores, want in ((10, (2, 4)), (2, (1, 1)), (4, (1, 3)), (8, (2, 3)), (12, (3, 3))):
        check(f"ffmpeg {cores} cores -> {want[0]}x{want[1]}", ffmpeg_pool(cores), want)
    # D4 hot guard
    check("hot on load", is_hot(12, 10, 10), True)
    check("not hot when cool", is_hot(2, 8, 10), False)
    check("hot on ram floor", is_hot(1, 3.0, 10), True)
    check("ram floor exactly reserve+per-agent is not hot",
          is_hot(0, RESERVE_GB + GB_PER_AGENT, 10), False)
    # claude-code split
    check("agents_per_workflow = min(10, agents)",
          min(10, size("claude-code", "openrouter", units=999, load1=0.0,
                       cores=10, ram_avail=20)["agents"]),
          size("claude-code", "openrouter", units=999, load1=0.0,
               cores=10, ram_avail=20)["agents_per_workflow"])
    st = size("claude-code", "openrouter", units=25, load1=0.0, cores=10, ram_avail=20)
    check("25 agents -> ceil split",
          (st["agents_per_workflow"], st["workflows"]),
          (min(10, st["agents"]), math.ceil(st["agents"] / st["agents_per_workflow"])))
    st_oc = size("openclaw", "openrouter", units=1, load1=0.0, cores=10, ram_avail=20)
    check("openclaw line has null split keys",
          (st_oc["workflows"], st_oc["agents_per_workflow"]), (None, None))
    # runtime cap reads
    check("claude-code runtime cap 500",
          runtime_cap("claude-code")[0], CC_RUNTIME_CAP)
    keys, = [read_maxconcurrent(None, None)]
    check("no config -> no keys", keys, {})
    check("profile next to config dir",
          read_maxconcurrent(None, str(Path(__file__).resolve().parent)) is not None, True)
    print(f"selftest OK ({len(ok)} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())