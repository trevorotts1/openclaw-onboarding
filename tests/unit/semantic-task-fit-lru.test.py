#!/usr/bin/env python3
"""tests/unit/semantic-task-fit-lru.test.py

F2.4 — proves shared-utils/semantic_task_fit.py's task-embedding cache is
LRU-bounded (no unbounded growth if imported into a long-lived server) while
preserving the "embed the task once, share across N personas" contract:

  1. default cap is 256 (SEMANTIC_TASK_FIT_CACHE_MAX overrides it);
  2. the cache never exceeds the cap (oldest evicted first);
  3. a get() refreshes recency (MRU), so a touched key survives a later eviction;
  4. .clear() still empties it (the per-selection reset path).

Offline: exercises only the cache helpers, no embeddings / network.
Exit 0 = pass, 1 = fail.
"""
import importlib
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared-utils"))

PASS = 0
FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        print(f"  ✓ {msg}")
        PASS += 1
    else:
        print(f"  ✗ {msg}")
        FAIL += 1


# 1) default cap = 256 (env unset)
os.environ.pop("SEMANTIC_TASK_FIT_CACHE_MAX", None)
import semantic_task_fit as m  # noqa: E402
m = importlib.reload(m)
check(m._TASK_EMBED_CACHE_MAX == 256, f"default cap is 256 (got {m._TASK_EMBED_CACHE_MAX})")

# reconfigure with a tiny cap for the eviction tests
os.environ["SEMANTIC_TASK_FIT_CACHE_MAX"] = "3"
m = importlib.reload(m)
check(m._TASK_EMBED_CACHE_MAX == 3, f"env override sets cap to 3 (got {m._TASK_EMBED_CACHE_MAX})")

# 2) never exceeds cap; oldest evicted first
for i in range(5):
    m._task_cache_put(("task", f"q{i}"), [float(i)])
keys = [k[1] for k in m._TASK_EMBED_CACHE.keys()]
check(len(m._TASK_EMBED_CACHE) == 3, f"cache bounded to 3 (got {len(m._TASK_EMBED_CACHE)})")
check(keys == ["q2", "q3", "q4"], f"oldest evicted first (got {keys})")

# 3) get() refreshes recency → touched key survives next eviction
m._task_cache_get(("task", "q2"))          # q2 becomes MRU
m._task_cache_put(("task", "q5"), [9.0])   # evicts LRU (q3), not q2
keys = [k[1] for k in m._TASK_EMBED_CACHE.keys()]
check(keys == ["q4", "q2", "q5"], f"MRU-touched q2 survived; q3 evicted (got {keys})")
check(m._task_cache_get(("task", "q2")) == [2.0], "q2 still retrievable after touch+insert")
check(m._task_cache_get(("task", "q3")) is None, "q3 correctly evicted")

# 4) clear() empties the cache
m._TASK_EMBED_CACHE.clear()
check(len(m._TASK_EMBED_CACHE) == 0, "clear() empties the cache")

print(f"\n=== Results: {PASS} passed, {FAIL} failed ===")
if FAIL:
    print(f"FAIL: {FAIL} assertion(s) failed")
    sys.exit(1)
print("PASS: all assertions passed")
sys.exit(0)
