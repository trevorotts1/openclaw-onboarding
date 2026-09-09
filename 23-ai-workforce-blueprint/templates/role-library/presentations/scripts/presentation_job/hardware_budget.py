#!/usr/bin/env python3
"""hardware_budget.py -- CLASS-SPECIFIC HARDWARE ADMISSION (PRES-015).

WHAT THIS IS
------------
The LOCAL half of the effective-admission min(). capacity.py answers "how wide
can this client's ACCOUNT run"; this module answers "how wide can THIS BOX
carry the work class the route is about to spend". The dispatch path has never
had that half: capacity observation enumerated process names only
(capacity.measure_working_concurrent), and no RAM/CPU/cgroup/disk/fd pressure
reading existed anywhere in a reviewed decision path. A 2GB Hostinger
container was therefore offered the same local width as a 64GB Mac, because
nothing on the admission path knew the difference.

CLASSES (the axis the spec names, cheapest to heaviest locally)
---------------------------------------------------------------
    text        -- cheap cloud text I/O: one HTTPS round trip, negligible
                   local memory. Essentially never the binding hardware term.
    browser     -- a headless browser session (OCR/visual QC): RAM-heavy.
    render      -- renderer / FFmpeg: RAM + CPU heavy.
    image       -- image decode / generation I/O: RAM-moderate.
    local_model -- a LOCAL model inference (ollama-local): the whole model
                   resident in RAM while serving.
An UNCLASSIFIED route defaults to "text" -- the least-harmful assumption, and
the cloud routes are the majority. Callers that know better pass class=.

MEASUREMENT PER PLATFORM
------------------------
    macOS  -- psutil when importable, else sysctl/vm_stat/uptime subprocesses:
             total/available RAM (VM statistics, NOT host-RAM-as-seen-by-a
             container -- on a container this is the VM's RAM, which is the
             point), load average vs core count, disk free, fd headroom.
    Linux  -- cgroup v2 (/sys/fs/cgroup/memory.max, cpu.max, pids.max) or
             cgroup v1 (/sys/fs/cgroup/memory/..., cpu.cfs_*) WHEN they exist,
             else the same host-level readers. cgroup memory.current is the
             CONTAINER's usage -- on a 2GB container this module reads 2GB,
             never the host's 64GB, which is the defect class the spec names
             ("do not use hostRAM on a 2GB container").

EVERY reading carries a `source` string; a reading that cannot be taken is
`UNMEASURED` and contributes NO budget term of its own (an absence is never
evidence for a lower width -- the same doctrine capacity.py's unmeasured
branch states). The verdict names the BINDING limiter so the client report can
say which term of the min() decided.

ADMISSION MODEL
---------------
effective_local_concurrency(class) is a CLASS BUDGET, not a global pool cap.
Two different routes' budgets are enforced independently; a text route on a
2GB box is not throttled by a render class' scarcity. Within one class the
budget is:

    min(class hardware terms by their own formulas, below)

and the caller (admission.py) folds it into the full admission min() together
with the account/allocation/permits terms. Warmup/pressure ramp lives in
admission.py (it needs the run's own success/error telemetry); this module is
the pure measurement + static-budget half and NEVER mutates global state.

NEVER RAISES on the measurement paths: a broken /sys, an absent psutil, a
permission error are all UNMEASURED readings, recorded, and the admission
answer degrades to the documented default floor -- labelled, never silent.

Rollout flag: PRESENTATION_HARDWARE_BUDGET=0 is the documented rollback:
every probe returns status UNMEASURED and every budget resolves to the
unmeasured default -- byte-for-byte the pre-PRES-015 behaviour of "no local
admission term at all".
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

FLAG_ENV = "PRESENTATION_HARDWARE_BUDGET"
FLAG_DEFAULT = "1"

#: The classes, least locally-expensive first. Anything not listed here is
#: treated as "text" (never as "local_model" -- an unclassified route must
#: never be punished by the heaviest budget).
CLASSES: Tuple[str, ...] = ("text", "image", "browser", "render", "local_model")
DEFAULT_CLASS = "text"

#: When the local box's true width cannot be measured, this is the budget the
#: class degrades to -- labelled UNMEASURED, never a fabricated reading. 3 is
#: capacity.DEFAULT_CONSERVATIVE's own doctrine applied to the local axis;
#: duplicated here (not imported) so this module stays import-standalone and
#: capacity.py can import this one without a cycle.
DEFAULT_UNMEASURED_BUDGET = 3

#: A single render/browser/local_model task is assumed to want at least this
#: fraction of the measured RAM pool before more than one is admitted
#: concurrently. Deliberately conservative: measured pressure (admission.py's
#: ramp) may lower it further, never this static term raise it.
HEAVY_CLASS_RAM_FRACTION = 0.25

#: cgroup v2 /proc-style pressure thresholds. memory pressure above these
#: percentages of time-someone-was-waiting says the container is already
#: thrashing: admission narrows regardless of what the static budget says.
PSI_MEM_SOME_STALL_PCT = 20.0
PSI_CPU_SOME_STALL_PCT = 60.0

STATUS_MEASURED = "MEASURED"
STATUS_UNMEASURED = "UNMEASURED"

#: How far below its limit a cgroup must sit (free bytes / free fds) before
#: the budget is not the binding term. Not load-bearing arithmetic -- the
#: formulas below are -- but the record says which term BOUND.
BINDING_TIE_EPS = 1e-9


def flag_enabled() -> bool:
    """True unless PRESENTATION_HARDWARE_BUDGET=0 (documented rollback)."""
    return os.environ.get(FLAG_ENV, FLAG_DEFAULT) != "0"


# ---------------------------------------------------------------------------
# primitive readers -- every one returns (value, source) or (None, reason)
# ---------------------------------------------------------------------------
def _sysctl_int(name: str) -> Tuple[Optional[int], str]:
    try:
        out = subprocess.run(["sysctl", "-n", name], capture_output=True,
                             text=True, timeout=10)
    except Exception as exc:  # noqa: BLE001 -- a measurement must never raise
        return None, f"sysctl {name} failed: {exc.__class__.__name__}"
    if out.returncode != 0:
        return None, f"sysctl -n {name} exited {out.returncode}"
    try:
        return int(out.stdout.strip()), f"sysctl -n {name}"
    except ValueError:
        return None, f"sysctl -n {name} unparseable: {out.stdout.strip()!r}"


def _mac_ram_bytes() -> Tuple[Optional[int], str]:
    try:
        import psutil  # optional dependency
        vm = psutil.virtual_memory()
        return int(vm.total), "psutil.virtual_memory().total"
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001
        return None, f"psutil virtual_memory failed: {exc.__class__.__name__}"
    return _sysctl_int("hw.memsize")


def _mac_available_ram_bytes() -> Tuple[Optional[int], str]:
    try:
        import psutil
        vm = psutil.virtual_memory()
        return int(vm.available), "psutil.virtual_memory().available"
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001
        return None, f"psutil available failed: {exc.__class__.__name__}"
    # vm_stat: read the page size it prints (4096 or 16384 on supported Macs)
    # and count "free" + "inactive" + "speculative" (memory an allocator can
    # take back). Never "active"/"wired" -- that is the memory in use.
    try:
        out = subprocess.run(["vm_stat"], capture_output=True, text=True,
                             timeout=10)
        if out.returncode == 0:
            page = 4096
            m_page = re.search(r"page size of (\d+) bytes", out.stdout)
            if m_page:
                page = int(m_page.group(1))
            vals: Dict[str, int] = {}
            for line in out.stdout.splitlines():
                m = re.match(r'^"?([^":]+)"?:\s+(\d+)\.?$', line.strip())
                if m:
                    vals[m.group(1).strip()] = int(m.group(2)) * page
            free = vals.get("Pages free", 0) + vals.get("Pages inactive", 0) \
                + vals.get("Pages speculative", 0)
            if free > 0:
                return free, "vm_stat free+inactive+speculative"
    except Exception as exc:  # noqa: BLE001
        return None, f"vm_stat failed: {exc.__class__.__name__}"
    return None, "vm_stat unavailable"


def _mac_load() -> Tuple[Optional[float], str]:
    try:
        return (float(os.getloadavg()[0]),
                "os.getloadavg (1-minute)")
    except Exception as exc:  # noqa: BLE001
        return None, f"loadavg failed: {exc.__class__.__name__}"


def _mac_core_count() -> Tuple[Optional[int], str]:
    n = os.cpu_count()
    if n and n > 0:
        return n, "os.cpu_count()"
    return _sysctl_int("hw.ncpu")


def _read_int_file(path: str) -> Tuple[Optional[int], str]:
    try:
        raw = Path(path).read_text(encoding="utf-8").strip()
    except OSError as exc:
        return None, f"{path} unreadable: {exc.__class__.__name__}"
    if raw == "max":  # cgroup v2 memory.max / pids.max "max"
        return None, f"{path} = max (no limit)"
    try:
        return int(raw), path
    except ValueError:
        return None, f"{path} unparseable: {raw!r}"


def _cgroup2_root() -> Optional[str]:
    """The cgroup v2 root of THIS process, via /proc/self/cgroup + mountinfo.

    A container typically reads `0::/<id>` -- the unified hierarchy line.
    The mount line names where the hierarchy is mounted (often /sys/fs/cgroup,
    sometimes a nested path inside the container)."""
    try:
        line = ""
        with open("/proc/self/cgroup", "r", encoding="utf-8") as fh:
            for row in fh:
                parts = row.rstrip("\n").split(":", 2)
                if len(parts) == 3 and parts[1] == "" and parts[0] == "0":
                    line = parts[2]
                    break
        if not line:
            return None
        rel = line.lstrip("/")
        mount = "/sys/fs/cgroup"
        try:
            with open("/proc/self/mountinfo", "r", encoding="utf-8") as fh:
                for row in fh:
                    cols = row.split()
                    # mountinfo column layout: ... <sep> <root> <mountpoint>
                    # <fstype> ... -- fstype "cgroup2" sits 4 columns after
                    # the mountpoint; find it by fstype, take the mountpoint.
                    if len(cols) > 6 and cols[4 + 4] == "cgroup2":
                        mount = cols[4]
                        break
        except (OSError, IndexError):
            pass
        cand = Path(mount) / rel if rel else Path(mount)
        if cand.is_dir():
            return str(cand)
        # last resort: the plain mount root
        if (Path(mount) / "cgroup.controllers").is_file():
            return mount
        return None
    except Exception:  # noqa: BLE001 -- probing must never raise
        return None


def _cgroup2_dir() -> Optional[str]:
    """Best-effort cgroup v2 directory for THIS process."""
    root = _cgroup2_root()
    if root:
        return root
    if Path("/sys/fs/cgroup/cgroup.controllers").is_file():
        return "/sys/fs/cgroup"
    return None


def _cgroup2_limits() -> Dict[str, Tuple[Optional[int], str]]:
    out: Dict[str, Tuple[Optional[int], str]] = {}
    d = _cgroup2_dir()
    if not d:
        return out
    out["mem_max"] = _read_int_file(f"{d}/memory.max")
    out["mem_current"] = _read_int_file(f"{d}/memory.current")
    out["pids_max"] = _read_int_file(f"{d}/pids.max")
    out["pids_current"] = _read_int_file(f"{d}/pids.current")
    # cpu.max = "$MAX $PERIOD" (v2). $MAX may be "max".
    try:
        raw = Path(f"{d}/cpu.max").read_text(encoding="utf-8").split()
        if len(raw) >= 2:
            if raw[0] == "max":
                out["cpu_quota"] = (None, f"{d}/cpu.max = max")
            else:
                quota, period = int(raw[0]), int(raw[1])
                if quota > 0 and period > 0:
                    # cores the cgroup may use on average
                    out["cpu_quota"] = (
                        max(1, quota // period), f"{d}/cpu.max quota/period")
    except OSError as exc:
        out["cpu_quota"] = (None, f"cpu.max unreadable: {exc.__class__.__name__}")
    except Exception as exc:  # noqa: BLE001
        out["cpu_quota"] = (None, f"cpu.max parse failed: {exc.__class__.__name__}")
    return out


def _cgroup1_limits() -> Dict[str, Tuple[Optional[int], str]]:
    out: Dict[str, Tuple[Optional[int], str]] = {}
    mem = "/sys/fs/cgroup/memory"
    if Path(f"{mem}/memory.limit_in_bytes").is_file():
        out["mem_max"] = _read_int_file(f"{mem}/memory.limit_in_bytes")
        out["mem_current"] = _read_int_file(f"{mem}/memory.usage_in_bytes")
    cpu = "/sys/fs/cgroup/cpu"
    if Path(f"{cpu}/cpu.cfs_quota_us").is_file():
        quota_v, _src = _read_int_file(f"{cpu}/cpu.cfs_quota_us")
        period_v, _src2 = _read_int_file(f"{cpu}/cpu.cfs_period_us")
        if quota_v and quota_v > 0 and period_v and period_v > 0:
            out["cpu_quota"] = (max(1, quota_v // period_v),
                                f"{cpu}/cpu.cfs_quota_us // cpu.cfs_period_us")
        else:
            out["cpu_quota"] = (None, "cpu.cfs_quota_us = unlimited")
    pids = "/sys/fs/cgroup/pids"
    if Path(f"{pids}/pids.max").is_file():
        out["pids_max"] = _read_int_file(f"{pids}/pids.max")
    return out


def _linux_ram() -> Tuple[Optional[int], Optional[int], List[str]]:
    """(total_bytes_seen, available_bytes_seen, sources) on Linux.

    A cgroup limit SMALLER than host RAM wins: that is the container's real
    RAM, and the reason this function exists. Reads are cgroup v2 first, v1
    second, /proc/meminfo last."""
    sources: List[str] = []
    lims: Dict[str, Tuple[Optional[int], str]] = {}
    try:
        lims = _cgroup2_limits()
    except Exception as exc:  # noqa: BLE001
        sources.append(f"cgroup v2 probe failed: {exc.__class__.__name__}")
    if "mem_max" not in lims:
        try:
            lims = _cgroup1_limits()
            if lims:
                sources.append("cgroup v1 memory files")
        except Exception as exc:  # noqa: BLE001
            sources.append(f"cgroup v1 probe failed: {exc.__class__.__name__}")
    total = None
    if lims.get("mem_max", (None, ""))[0] is not None:
        total = lims["mem_max"][0]
        sources.append(lims["mem_max"][1])
    if total is None:
        try:
            with open("/proc/meminfo", "r", encoding="utf-8") as fh:
                for row in fh:
                    if row.startswith("MemTotal:"):
                        kb = int(row.split()[1])
                        total = kb * 1024
                        sources.append("/proc/meminfo MemTotal")
                        break
        except (OSError, ValueError) as exc:
            sources.append(f"/proc/meminfo unreadable: {exc.__class__.__name__}")
    available = None
    cur = lims.get("mem_current", (None, ""))
    if total is not None and cur[0] is not None:
        available = max(0, total - cur[0])
        sources.append(f"cgroup memory.current -> available {available}")
    if available is None:
        try:
            with open("/proc/meminfo", "r", encoding="utf-8") as fh:
                for row in fh:
                    if row.startswith("MemAvailable:"):
                        available = int(row.split()[1]) * 1024
                        sources.append("/proc/meminfo MemAvailable")
                        break
        except (OSError, ValueError, IndexError) as exc:
            sources.append(f"MemAvailable unreadable: {exc.__class__.__name__}")
    return total, available, sources


def _psi_stall_pct(kind: str) -> Tuple[Optional[float], str]:
    """Read /proc/pressure/<kind> "some avg10" as a percentage."""
    path = f"/proc/pressure/{kind}"
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for row in fh:
                if row.startswith("some "):
                    m = re.search(r"avg10=([\d.]+)", row)
                    if m:
                        return float(m.group(1)), f"{path} some avg10"
    except OSError as exc:
        return None, f"{path} unreadable: {exc.__class__.__name__}"
    except Exception as exc:  # noqa: BLE001
        return None, f"{path} parse failed: {exc.__class__.__name__}"
    return None, f"{path} carried no 'some' row"


def _linux_load() -> Tuple[Optional[float], str]:
    try:
        return float(os.getloadavg()[0]), "os.getloadavg (1-minute)"
    except Exception as exc:  # noqa: BLE001
        return None, f"loadavg failed: {exc.__class__.__name__}"


def _linux_core_count() -> Tuple[Optional[int], str]:
    lims = {}
    try:
        lims = _cgroup2_limits()
    except Exception:  # noqa: BLE001
        pass
    if not lims:
        try:
            lims = _cgroup1_limits()
        except Exception:  # noqa: BLE001
            pass
    if lims.get("cpu_quota", (None, ""))[0] is not None:
        return lims["cpu_quota"][0], lims["cpu_quota"][1]
    n = os.cpu_count()
    if n and n > 0:
        return n, "os.cpu_count()"
    return None, "no core count source"


def _disk_free_bytes() -> Tuple[Optional[int], str]:
    try:
        st = os.statvfs(os.getcwd() if os.path.isdir(os.getcwd()) else "/")
        return int(st.f_bavail) * int(st.f_frsize), "os.statvfs f_bavail*f_frsize"
    except Exception as exc:  # noqa: BLE001
        return None, f"statvfs failed: {exc.__class__.__name__}"


def _fd_headroom() -> Tuple[Optional[int], str]:
    """(fds we may still open, source). macOS: sysctl kern.maxfilesperproc vs
    current soft limit. Linux: /proc/self/limits soft 'open files' minus
    /proc/self/fd count."""
    try:
        import resource
        soft, _hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        if soft != resource.RLIM_INFINITY:
            used = 0
            try:
                used = len(os.listdir("/proc/self/fd"))
            except OSError:
                pass
            if used:
                return max(0, int(soft) - used), \
                    f"RLIMIT_NOFILE soft {soft} - /proc/self/fd {used}"
            return int(soft), f"RLIMIT_NOFILE soft {soft}"
    except Exception:  # noqa: BLE001
        pass
    return None, "fd headroom unmeasured"


# ---------------------------------------------------------------------------
# the measured snapshot
# ---------------------------------------------------------------------------
def _snapshot() -> Dict[str, Any]:
    """One measured picture of THIS box. Pure read; never raises."""
    snap: Dict[str, Any] = {"platform": sys.platform}
    if sys.platform == "darwin":
        total, t_src = _mac_ram_bytes()
        avail, a_src = _mac_available_ram_bytes()
        load, l_src = _mac_load()
        cores, c_src = _mac_core_count()
        psi_mem = None
        psi_cpu = None
        cgroup = "none (macOS host)"
    else:
        total_raw, avail_raw, srcs = _linux_ram()
        total, avail = total_raw, avail_raw
        load, l_src = _linux_load()
        cores, c_src = _linux_core_count()
        psi_mem, psi_mem_src = _psi_stall_pct("memory")
        psi_cpu, psi_cpu_src = _psi_stall_pct("cpu")
        cgroup = "cgroup" if any(
            k in s for s in srcs for k in ("cgroup",)) else "host (/proc/meminfo)"
        snap["psi_mem_avg10"] = psi_mem
        snap["psi_mem_source"] = psi_mem_src
        snap["psi_cpu_avg10"] = psi_cpu
        snap["psi_cpu_source"] = psi_cpu_src
        snap["linux_sources"] = srcs
    disk, d_src = _disk_free_bytes()
    fds, f_src = _fd_headroom()
    snap.update({
        "ram_total_bytes": total, "ram_total_source": t_src if sys.platform == "darwin" else "cgroup/procmeminfo",
        "ram_available_bytes": avail, "ram_available_source": a_src if sys.platform == "darwin" else "cgroup/procmeminfo",
        "load_1m": load, "load_source": l_src,
        "cores": cores, "cores_source": c_src,
        "disk_free_bytes": disk, "disk_source": d_src,
        "fd_headroom": fds, "fd_source": f_src,
        "cgroup": cgroup,
    })
    return snap


def snapshot(flag: Optional[bool] = None) -> Dict[str, Any]:
    """Public snapshot with the rollback flag applied. Never raises."""
    enabled = flag_enabled() if flag is None else flag
    if not enabled:
        return {"platform": sys.platform, "status": STATUS_UNMEASURED,
                "detail": f"{FLAG_ENV}=0 rollback: hardware budget inert",
                "budgets": {}}
    try:
        snap = _snapshot()
    except Exception as exc:  # noqa: BLE001 -- measurement must never raise
        return {"platform": sys.platform, "status": STATUS_UNMEASURED,
                "detail": f"snapshot failed: {exc.__class__.__name__}: {exc}",
                "budgets": {}}
    snap["status"] = STATUS_UNMEASURED if snap.get("ram_available_bytes") is None \
        else STATUS_MEASURED
    snap["budgets"] = {cls: class_budget(snap, work_class=cls)
                       for cls in CLASSES}
    return snap


# ---------------------------------------------------------------------------
# PRES-015 cached snapshot -- the width path's one measurement, never per unit
# ---------------------------------------------------------------------------
#: How long a cached hardware snapshot stays authoritative for scheduling
#: decisions. Pressure is visible quickly through this window because the
#: ramp layer (admission.py) re-reads the live budget for every admission and
#: snapshots are refreshed at least this often -- the window bounds how STALE
#: a measured reading can be, it never inflates a budget.
SNAPSHOT_TTL_S = 10.0

_SNAPSHOT_CACHE: Dict[str, Any] = {}
_SNAPSHOT_CACHE_LOCK = None  # created lazily; a threading import here is fine


def _cache_lock():
    global _SNAPSHOT_CACHE_LOCK
    if _SNAPSHOT_CACHE_LOCK is None:
        import threading
        _SNAPSHOT_CACHE_LOCK = threading.Lock()
    return _SNAPSHOT_CACHE_LOCK


def cached_snapshot(max_age_s: float = SNAPSHOT_TTL_S,
                    force_refresh: bool = False) -> Dict[str, Any]:
    """A process-wide CACHED snapshot, refreshed at most once per TTL.

    PRES-015's split: measuring the box is like measuring an account -- it is
    a deliberate, bounded read, not something every one of 100 unit
    admissions repeats (on the operator Mac one `snapshot()` costs real
    subprocess time when psutil is absent). Admission paths call THIS; an
    explicit `refresh=True` (or a TTL expiry) is the only thing that
    re-measures. The cache is process-local state, never persisted.

    The cached dict is returned BY REFERENCE but treated as immutable by
    convention; callers that must mutate copy it. Never raises."""
    lock = _cache_lock()
    now = time.monotonic()
    with lock:
        cached = _SNAPSHOT_CACHE.get("snap")
        ts = _SNAPSHOT_CACHE.get("ts") or 0.0
        if cached is not None and not force_refresh \
                and (now - ts) < max(0.0, max_age_s):
            return cached
    snap = snapshot()
    with lock:
        _SNAPSHOT_CACHE["snap"] = snap
        _SNAPSHOT_CACHE["ts"] = time.monotonic()
    return snap


def refresh_snapshot() -> Dict[str, Any]:
    """Force a re-measure of the local box (the hardware half of PRES-015's
    explicit-refresh seam). Never raises."""
    return cached_snapshot(force_refresh=True)


# ---------------------------------------------------------------------------
# class budgets
# ---------------------------------------------------------------------------
def _min_int(values: List[Optional[int]]) -> Optional[int]:
    nums = [v for v in values if isinstance(v, int) and not isinstance(v, bool)]
    return min(nums) if nums else None


def class_budget(snap: Optional[Dict[str, Any]] = None, *,
                 work_class: str = DEFAULT_CLASS) -> Dict[str, Any]:
    """The static local budget for ONE class on ONE box snapshot.

    Returns {class, budget, status, binding, terms, detail}. `budget` is a
    positive int -- the width THIS class may run at, from local hardware
    alone. UNMEASURED degrades to DEFAULT_UNMEASURED_BUDGET, labelled.

    Terms (all min()'d, never max()'d):
      heavy classes  -- RAM-bound: budget = max(1, available_ram // 1GB * 4)
                        ... bounded by the RAM fraction rule for multi-GB
                        models/sessions. Concretely: one heavy unit is assumed
                        to want HEAVY_CLASS_RAM_FRACTION of the available RAM;
                        budget = floor(available / (HEAVY_CLASS_RAM_FRACTION *
                        total or 4GB, whichever smaller)).
      text           -- RAM is not the binding term; budget is high (the
                        account and mode ceilings govern instead) but NOT
                        unbounded: fd headroom still caps it.
      all            -- fd headroom / 2 as an absolute term (each unit holds
                        sockets + file handles).
      all (Linux)    -- pids.max headroom // 4 (each unit is roughly a thread
                        + sockets; 4 is the documented slack).
      pressure       -- PSI mem some-avg10 >= PSI_MEM_SOME_STALL_PCT narrows
                        every class to 1 until pressure clears (admission.py
                        re-reads each admission; this is the static floor it
                        enforces).
    """
    cls = work_class if work_class in CLASSES else DEFAULT_CLASS
    if snap is None:
        try:
            snap = _snapshot()
        except Exception as exc:  # noqa: BLE001
            return {"class": cls, "budget": DEFAULT_UNMEASURED_BUDGET,
                    "status": STATUS_UNMEASURED,
                    "binding": "snapshot-failed",
                    "detail": f"{exc.__class__.__name__}: {exc}"}
    terms: List[Tuple[str, int]] = []
    reasons: List[str] = []

    avail = snap.get("ram_available_bytes")
    total = snap.get("ram_total_bytes")
    if cls == "text":
        # Cheap cloud I/O: RAM gives no reason to hold it below a wide width.
        # fd and pid terms below still bound it.
        ram_budget = None
        reasons.append("text class: local RAM not binding")
    elif avail is None:
        ram_budget = None
        reasons.append("RAM unmeasured: no RAM term")
    else:
        if cls == "local_model":
            per_unit = max(1, int(total or avail))
            per_unit = min(per_unit, max(1, int(avail)))
        else:
            # A heavy unit's working set scales with the box's INSTALLED
            # memory (a render/browser session on a big box is a big
            # session), NOT with what happens to be free right now. Capping
            # per_unit at a fraction of AVAILABLE here would collapse the
            # budget to ~1/HEAVY_CLASS_RAM_FRACTION on EVERY box -- a 2GB
            # container and a 64GB Mac answering the same width, which is
            # exactly the defect this module exists to remove. The
            # available-pool check below still guarantees the budget can
            # never exceed what is actually free.
            per_unit = max(1, int(HEAVY_CLASS_RAM_FRACTION * (total or avail)))
        if avail >= per_unit:
            ram_budget = max(1, int(avail // per_unit))
            reasons.append(f"{cls}: ~{per_unit}B/unit against "
                           f"{avail}B available -> {ram_budget}")
        else:
            ram_budget = 1
            reasons.append(f"{cls}: {avail}B available below one "
                           f"{per_unit}B unit -> 1")
        terms.append(("ram", ram_budget))

    fds = snap.get("fd_headroom")
    if isinstance(fds, int) and fds > 0:
        fd_budget = max(1, fds // 2)
        terms.append(("fd", fd_budget))
        reasons.append(f"fd headroom {fds} -> {fd_budget} (//2 per unit)")

    pids = snap.get("pids_max")
    pids_cur = snap.get("pids_current")
    if isinstance(pids, int) and pids > 0:
        used = pids_cur if isinstance(pids_cur, int) else 0
        head = max(0, pids - used)
        terms.append(("pids", max(1, head // 4)))
        reasons.append(f"pids headroom {head} -> {max(1, head // 4)} (//4)")

    pressure = snap.get("psi_mem_avg10")
    if isinstance(pressure, (int, float)) and pressure >= PSI_MEM_SOME_STALL_PCT:
        terms.append(("psi-mem-pressure", 1))
        reasons.append(
            f"memory PSI some avg10 {pressure}% >= {PSI_MEM_SOME_STALL_PCT}% "
            f"-> width 1 until pressure clears")

    if not terms:
        return {"class": cls, "budget": DEFAULT_UNMEASURED_BUDGET,
                "status": STATUS_UNMEASURED, "binding": None,
                "terms": [], "reason": "; ".join(reasons) or "no term measured",
                "detail": ("no hardware term was measurable; "
                           f"DEFAULT_UNMEASURED_BUDGET={DEFAULT_UNMEASURED_BUDGET}")}
    budget = min(v for _n, v in terms)
    binding = next(n for n, v in terms if v == budget)
    return {"class": cls, "budget": int(budget), "status": STATUS_MEASURED,
            "binding": binding,
            "terms": [{"term": n, "value": v} for n, v in terms],
            "reason": "; ".join(reasons), "detail": ""}


def probe_snapshot(config_dir: Optional[Path] = None) -> Dict[str, Any]:
    """The capacity.py-shaped surface: snapshot + budgets + redaction note.

    Never carries a credential (it never reads one). Never raises."""
    snap = snapshot()
    snap["flag_env"] = FLAG_ENV
    snap["default_unmeasured_budget"] = DEFAULT_UNMEASURED_BUDGET
    return snap


def budget_for_class(work_class: str,
                     snap: Optional[Dict[str, Any]] = None) -> int:
    """One-call accessor: the int budget for a class (floor 1)."""
    return int(class_budget(snap, work_class=work_class)["budget"])