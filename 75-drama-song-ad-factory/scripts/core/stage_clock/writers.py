"""writers.py - N-85: prompt-writing fan-out (section 10B, binding).

One writer writes 2 to 3 prompts, and only its shot's own part (or 2 to 3 beat
rows). For N prompts, N/3 to N/2 writers run at once; every writer reads the
same spine, beat sheet, Shot Router record and lock; the Prompt Builder stamps
every prompt; one joiner collects them.

This module only decides the plan: how many writers, which items each carries,
and what each must read. It never calls a model.
"""
import math

ITEMS_PER_WRITER = (2, 3)
SHARED_INPUTS = ("spine", "beat-sheet", "shot-router-record", "look-lock")

def writer_plan(items, items_per_writer=ITEMS_PER_WRITER):
    """Split ``items`` into writers of 2 to 3 each -> {"writers": [[...], ...],
    "count": n, "items_per_writer": (2,3), "fanout_in_range": bool,
    "reads": SHARED_INPUTS, "joiner": "one"}.

    N/3 is the most writers; N/2 the fewest. Splitting evenly inside that band
    means ceil(N/3) writers, which is the plan's own upper bound."""
    items = list(items or [])
    low, high = int(items_per_writer[0]), int(items_per_writer[1])
    if high < low or low < 1:
        raise ValueError("items_per_writer must be a low-to-high pair of at least 1")
    if not items:
        return {"writers": [], "count": 0, "items_per_writer": [low, high],
                "fanout_in_range": True, "reads": list(SHARED_INPUTS),
                "joiner": "one", "reason_code": None}
    count = int(math.ceil(len(items) / float(high)))
    writers = [[] for _ in range(count)]
    for at, item in enumerate(items):          # deal round-robin, keeps order stable
        writers[at % count].append(item)
    # A tail writer carrying a single item is folded into its neighbour when the
    # neighbour can still take it; a lone item is legal but the plan prefers pairs.
    while len(writers) > 1 and len(writers[-1]) < low \
            and len(writers[-2]) + len(writers[-1]) <= high:
        writers[-2].extend(writers.pop())
    biggest = max(len(w) for w in writers)
    problem = None
    if biggest > high:
        problem = "A_WRITER_OVERLOADED"
    elif len(writers) > 1 and min(len(w) for w in writers) < low:
        problem = "A_WRITER_UNDERLOADED"
    return {"writers": writers, "count": len(writers),
            "items_per_writer": [low, high],
            "fanout_in_range": math.ceil(len(items) / float(high)) <= len(writers) <= len(items),
            "reads": list(SHARED_INPUTS), "joiner": "one", "reason_code": problem}

def fanout_bounds(item_count):
    """The band the plan names: N/3 (most writers) to N/2 (fewest)."""
    n = max(0, int(item_count or 0))
    return {"most": int(math.ceil(n / 3.0)) if n else 0,
            "fewest": int(math.ceil(n / 2.0)) if n else 0,
            "n": n}

def selftest():
    proofs = []
    plan = writer_plan(["p%02d" % i for i in range(10)])
    proofs.append(("10 prompts -> 4 writers of 2 to 3",
                   plan["count"] == 4 and all(2 <= len(w) <= 3 for w in plan["writers"])))
    bounds = fanout_bounds(10)
    proofs.append(("10 prompts: N/3 is 4 and N/2 is 5",
                   bounds == {"most": 4, "fewest": 5, "n": 10}))
    proofs.append(("every writer reads the same four inputs",
                   plan["reads"] == list(SHARED_INPUTS) and plan["joiner"] == "one"))
    proofs.append(("no item is lost or duplicated",
                   sorted(x for w in plan["writers"] for x in w)
                   == ["p%02d" % i for i in range(10)]))
    proofs.append(("an empty sheet plans no writers",
                   writer_plan([])["count"] == 0))
    for name, ok in proofs:
        print(("ok   " if ok else "FAIL ") + name)
    return 0 if all(ok for _, ok in proofs) else 1

if __name__ == "__main__":
    import sys
    sys.exit(selftest())
