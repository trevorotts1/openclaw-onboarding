#!/usr/bin/env python3
"""Working-set memory guard checks (D8/A9): reclaimable page cache must not
count as used RAM, and host free memory must be reported in GiB.

Run: cd scripts/core && HOME=$(mktemp -d) python3 test_lane_size_working_set_s75.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lane_size as L

GIB = 1024 ** 3
MEM_AVAIL_KB = 11534336          # 11 GiB


def rd(files):
    return lambda p: files.get(p)


def check(name, got, want, tol=0.01):
    assert abs(got - want) <= tol, "%s: got %r, want %r" % (name, got, want)


# v2: 16 GiB cap, 14 GiB current, 9 GiB inactive_file -> working set 5 GiB -> 11 free.
# MemAvailable is 11 GiB, so the answer is 11 (never 2 from raw current).
read_v2 = rd({
    "/proc/meminfo": "MemAvailable: %d kB\n" % MEM_AVAIL_KB,
    "/sys/fs/cgroup/memory.max": str(16 * GIB),
    "/sys/fs/cgroup/memory.current": str(14 * GIB),
    "/sys/fs/cgroup/cpu.max": "max 100000",
    "/sys/fs/cgroup/memory.stat": "anon 1024\ninactive_file %d\nactive_file 1024\n" % (9 * GIB),
})
check("v2 reclaimable cache -> 11 GiB", L.ram_avail_gb(read=read_v2, system="Linux"), 11.0)

# No memory.stat: no subtraction, so 16 - 14 = 2 GiB.
read_nostat = rd({
    "/proc/meminfo": "MemAvailable: %d kB\n" % MEM_AVAIL_KB,
    "/sys/fs/cgroup/memory.max": str(16 * GIB),
    "/sys/fs/cgroup/memory.current": str(14 * GIB),
    "/sys/fs/cgroup/cpu.max": "max 100000",
})
check("v2 without memory.stat -> 2 GiB",
      L.ram_avail_gb(read=read_nostat, system="Linux"), 2.0)

# v1: same behaviour via total_inactive_file.
read_v1 = rd({
    "/proc/meminfo": "MemAvailable: %d kB\n" % MEM_AVAIL_KB,
    "/sys/fs/cgroup/memory/memory.limit_in_bytes": str(16 * GIB),
    "/sys/fs/cgroup/memory/memory.usage_in_bytes": str(14 * GIB),
    "/sys/fs/cgroup/cpu/cpu.cfs_quota_us": "max",
    "/sys/fs/cgroup/cpu/cpu.cfs_period_us": "100000",
    "/sys/fs/cgroup/memory/memory.stat": "total_inactive_file %d\n" % (9 * GIB),
})
check("v1 reclaimable cache -> 11 GiB", L.ram_avail_gb(read=read_v1, system="Linux"), 11.0)

# v1 without the stat: no subtraction.
read_v1_nostat = rd({
    "/proc/meminfo": "MemAvailable: %d kB\n" % MEM_AVAIL_KB,
    "/sys/fs/cgroup/memory/memory.limit_in_bytes": str(16 * GIB),
    "/sys/fs/cgroup/memory/memory.usage_in_bytes": str(14 * GIB),
})
check("v1 without memory.stat -> 2 GiB",
      L.ram_avail_gb(read=read_v1_nostat, system="Linux"), 2.0)

# Clamp: inactive_file larger than usage never yields negative RAM.
read_clamp = rd({
    "/proc/meminfo": "MemAvailable: %d kB\n" % MEM_AVAIL_KB,
    "/sys/fs/cgroup/memory.max": str(16 * GIB),
    "/sys/fs/cgroup/memory.current": str(1 * GIB),
    "/sys/fs/cgroup/memory.stat": "inactive_file %d\n" % (4 * GIB),
})
check("working set clamps at 0", L.ram_avail_gb(read=read_clamp, system="Linux"), 11.0)

# A9: host MemAvailable in GiB, not MiB.
check("MemAvailable kB -> GiB", L._linux_mem_available(read_v2), 11.0)
assert L._linux_mem_available(rd({})) is None, "MemAvailable missing -> None"

print("test_lane_size_working_set_s75 OK")
