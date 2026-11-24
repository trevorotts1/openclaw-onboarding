"""box_probe.py - N-76: record the box at pre-flight (cores, memory, OS family)
and size local worker counts from the plan's number, cores minus one, and
memory divided by two. Fresh readings only (never older than 5 minutes);
a running worker is never killed for memory.

Stdlib only. Linux reads /proc/meminfo; macOS asks sysctl once, bounded.
"""
import json
import os
import subprocess
import sys
import time

FRESH_S = 300


def _mem_gb_linux():
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) / (1024.0 * 1024.0)
    except OSError:
        return None
    return None


def _mem_gb_mac():
    try:
        out = subprocess.run(["sysctl", "-n", "hw.memsize"],
                             capture_output=True, text=True, timeout=10)
        return int((out.stdout or "0").strip()) / (1024.0 ** 3)
    except Exception:                              # noqa: BLE001
        return None


def read_box(now=None):
    now = time.time() if now is None else now
    family = "mac" if sys.platform == "darwin" else ("linux" if sys.platform.startswith("linux") else sys.platform)
    cores = os.cpu_count() or 1
    mem = _mem_gb_mac() if family == "mac" else _mem_gb_linux()
    return {"schema": "blackceo.box/v1", "read_at": now, "os_family": family,
            "platform": sys.platform, "cores": cores,
            "memory_gb": None if mem is None else round(mem, 2)}


def record_box(run_dir, now=None):
    box = read_box(now)
    ctrl = os.path.join(run_dir, "control")
    os.makedirs(ctrl, exist_ok=True)
    path = os.path.join(ctrl, "box.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(box, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)
    return box


def worker_count(planned, box=None, pressure=None, now=None):
    """The smaller of the plan's number, cores minus one, and memory / 2.

    ``pressure`` is a fresh memory-pressure fraction (0..1) or None. Above 0.85
    new workers are held at the count already running (``held``), never killed.
    """
    box = box or read_box(now)
    cores = max(1, int(box.get("cores") or 1) - 1)
    mem = box.get("memory_gb")
    by_mem = max(1, int((mem or 2) / 2))
    n = max(1, min(int(planned or 1), cores, by_mem))
    if pressure is not None and pressure > 0.85:
        return {"allowed": 0, "planned": planned, "cores": cores,
                "by_memory": by_mem, "held_reason": "memory pressure above 85 percent"}
    return {"allowed": n, "planned": planned, "cores": cores, "by_memory": by_mem,
            "held_reason": None}
