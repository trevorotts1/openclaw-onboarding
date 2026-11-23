"""fanout.py - N-85: prompt-writing fan-out (10B).

Each writer writes 2 to 3 prompts (only the shot's own part) or 2 to 3 beat
rows. For N items, between N/3 and N/2 writers run at once. Every writer reads
the same story spine, beat sheet, Shot Router record and look lock; the
Prompt Builder stamps every prompt; one joiner collects the pieces.

Stdlib only; this is a planning helper, it launches nothing.
"""
import math

SHARED_INPUTS = ("spine", "beat_sheet", "shot_router_record", "look_lock")
PER_WRITER = 3


def writer_count(n):
    """The lower end of N/3 to N/2 writers, at least one."""
    return max(1, int(math.ceil(n / 3.0)))


def max_writers(n):
    """The upper end, N/2, at least one."""
    return max(1, n // 2)


def batches(items, per_writer=PER_WRITER):
    """Split items into chunks of 2 to 3, merging a lone remainder back."""
    items = list(items)
    if not items:
        return []
    size = max(2, min(3, int(per_writer)))
    chunks = [items[i:i + size] for i in range(0, len(items), size)]
    if len(chunks) > 1 and len(chunks[-1]) == 1:
        chunks[-1:] = [chunks[-2] + chunks[-1]]
        chunks.pop(-2)
    return chunks


def plan(items, inputs):
    """Plan one fan-out. ``inputs`` must carry all four shared records."""
    items = list(items or [])
    missing = [name for name in SHARED_INPUTS if not inputs or not inputs.get(name)]
    chunks = batches(items)
    writers = writer_count(len(items)) if items else 0
    if writers and writers > max_writers(len(items)):
        writers = max_writers(len(items))
    return {"ok": not missing and bool(items), "missing": missing,
            "items": len(items), "writers": writers, "batches": chunks,
            "joiner": 1 if items else 0, "shared_inputs": list(SHARED_INPUTS),
            "reason": None if not missing else
            "every writer must read the same %s" % ", ".join(missing)}
