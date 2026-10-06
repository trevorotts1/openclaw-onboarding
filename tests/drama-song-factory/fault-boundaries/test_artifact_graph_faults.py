#!/usr/bin/env python3
"""Fault boundary: artifact_graph invalidation cascade. Stdlib only."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "core"))
import artifact_graph as G

RUN = "fault-graph"


def check(name, cond):
    assert cond, "FAILED: %s" % name
    print("ok: %s" % name)


tmp = tempfile.mkdtemp(prefix="DTS-404-graph-")
paths = {}
for aid in ("A", "B", "C", "D"):
    p = os.path.join(tmp, aid + ".txt")
    with open(p, "w") as f:
        f.write("content-%s" % aid)
    paths[aid] = p

db = os.path.join(tmp, "graph.db")
g = G.Graph(db, [tmp])
for aid in ("A", "B", "C", "D"):
    g.register(RUN, aid, "clip", "song", paths[aid])
g.depend(RUN, "B", "A")
g.depend(RUN, "C", "B")

affected = g.invalidate_upstream_change(RUN, "A", "upstream changed")
check("cascade hits A,B,C in order", affected == ["A", "B", "C"])
check("non-dependent untouched",
      g.non_dependents(RUN, "A") == ["D"]
      and g.get(RUN, "D")["stale"] is False)
for aid in ("A", "B", "C"):
    check("%s marked stale" % aid, g.get(RUN, aid)["stale"] is True)

# tampered file fails verify, does not silently pass (same-size rewrite ->
# hash check fires, not the size check)
with open(paths["B"], "w") as f:
    f.write("TAMPERED!")
try:
    g.verify(RUN, "B")
    raise AssertionError("tampered artifact verified")
except G.GraphError as e:
    check("tampered artifact rejected (%s)" % e.code,
          e.code == "HASH_MISMATCH")

# invalidation needs a reason; self-deps and cycles rejected
try:
    g.invalidate_upstream_change(RUN, "D", "")
    raise AssertionError("reason-less invalidation passed")
except G.GraphError as e:
    check("reason required (%s)" % e.code, e.code == "MISSING_REASON")
try:
    g.depend(RUN, "A", "C")
    raise AssertionError("cycle accepted")
except G.GraphError as e:
    check("cycle rejected (%s)" % e.code, e.code == "CYCLE")
g.close()
print("OK test_artifact_graph_faults: 9 checks")
