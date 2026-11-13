"""PD-003 -- the manifest's `order` numbers must agree with the real dependencies.

`no phase may run before the phase that produces what it consumes`, and `order`
is the number the runner sorts on (`declare_plan()`, SOP-SLIDE-05 §2). Seven
phases carried an order LOWER than the phase that produces one of their inputs:
P8-ASSEMBLE (8) consumed the speech written at 8.5; P-U-GHL-SALES (6.2) and
P-U-GHL-VSL (6.4) consumed the sales/checkout/VSL pages built at 8.75-8.93;
P-U-FORM-GATE (5.6) consumed the VSL page built at 8.93; P-U-COLLATERAL (8.8)
consumed all four of those; P9.2-GHL-UPLOAD (8.9) and P9.6-WEBINAR-VIDEO (8.92)
consumed the audio produced by P9-DELIVER (9). The artifact DAG carried the
run, but the numbers -- the dispatch order an operator and every role file
reads -- said the opposite.

This file asserts the ordering property itself, for EVERY edge, computed from
the manifest: for each phase, each artifact it consumes, and each distinct
phase that produces that artifact, the producer's order is strictly lower.
Edges with no producer are not this test's business (that is the NO_PRODUCER
check in scripts/ci/pd_manifest_order_check.py); a phase consuming its own
product is not an edge between two phases; and an artifact named in
EXTERNAL_INPUTS is written before the phase graph starts, so it is not a
producer edge either (P-0.5-RESEARCH legitimately runs BEFORE P0A-INTAKE while
reading the intake the driver already wrote -- test_af_intake_gate.py pins it
as a pre-intake phase).

CONTROL: set PD_MANIFEST_PATH to another manifest's path to run against that
file instead. `PD_MANIFEST_PATH=<the pre-PD-003 manifest> python3 -m pytest
test_pd_manifest_order.py` FAILS on 9 late-producer edges (26 rows across the
four election sets) -- that is what makes the pass on the edited manifest mean
something.

Manifest location resolves the way the deployed tree carries it FIRST
(scripts/../sops/PIPELINE-MANIFEST.json), then by walking up to a repo
checkout, mirroring manifest_source.resolve_manifest's installed-then-cluster
tiering. If neither resolves this file FAILS rather than skipping -- a skipped
manifest test is a green suite that proved nothing.

Standard library plus pytest. No network, no model, no paid call.
"""
from __future__ import annotations

import fnmatch
import json
import os
import pathlib

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
PRESENTATIONS = SCRIPTS.parent                      # .../presentations

MANIFEST_REL = pathlib.Path("universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json")

# Artifacts written BEFORE the phase graph starts. Mirrors
# scripts/ci/pd_manifest_order_check.py:EXTERNAL_INPUTS (the authoritative
# list; the comment beside each entry there names the writer). An artifact on
# this list is an input, not an edge between two phases.
EXTERNAL_INPUTS = {
    "raw/*",                                          # client upload
    "working/copy/slides.json",                       # engine-owned (slides_assembly.py)
    "working/copy/intake.json",                       # deck-intake-driver.py --complete
    "working/copy/sp_intake.json",                    # deck-intake-driver.py --signature
    "working/prompts/infographic-prompt.txt",         # agent-authored (role slide-image-creator)
}

def _find_root(start: pathlib.Path) -> pathlib.Path | None:
    """Directory holding the manifest: deployed sops/ beside the scripts dir,
    else the first ancestor that carries the repo layout."""
    if (PRESENTATIONS / "sops" / "PIPELINE-MANIFEST.json").is_file():
        return PRESENTATIONS
    cur = start.resolve()
    seen = set()
    while cur not in seen:
        seen.add(cur)
        if (cur / MANIFEST_REL).is_file():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return None

def _manifest_path() -> pathlib.Path:
    override = os.environ.get("PD_MANIFEST_PATH")
    if override:
        p = pathlib.Path(override)
        if not p.is_file():
            pytest.fail(f"PD_MANIFEST_PATH is set but {p} is not a file")
        return p
    root = _find_root(pathlib.Path(__file__).parent)
    if root is None:
        pytest.fail(
            "manifest could not be resolved: looked for "
            f"{PRESENTATIONS / 'sops' / 'PIPELINE-MANIFEST.json'} and for an "
            f"ancestor of this test file containing {MANIFEST_REL}. This is a "
            "FAIL, never a skip.")
    if (root / "PIPELINE-MANIFEST.json").is_file():
        return root / "PIPELINE-MANIFEST.json"
    return root / MANIFEST_REL

def _manifest() -> dict:
    return json.loads(_manifest_path().read_text(encoding="utf-8"))

def _as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value]

def _same_artifact(a: str, b: str) -> bool:
    """Same matching rule the manifest's own order checker uses: exact, or a
    glob in either direction (`working/prompts/slide-*.txt` vs `slide-1.txt`)."""
    return a == b or fnmatch.fnmatch(a, b) or fnmatch.fnmatch(b, a)

def _edges(manifest: dict):
    """Yield (producer, consumer, artifact) for every distinct-phase edge.

    A declared consumer artifact with no producer is not an edge (the checker
    in scripts/ci owns NO_PRODUCER); a phase consuming its own product is not
    an edge between two phases; an EXTERNAL_INPUTS artifact is written before
    the phase graph and is not an edge either."""
    phases = manifest["phases"]
    for consumer in phases:
        own = _as_list(consumer.get("produces_artifact"))
        for need in _as_list(consumer.get("consumes")):
            if any(_same_artifact(need, ext) for ext in EXTERNAL_INPUTS):
                continue
            for producer in phases:
                if producer["id"] == consumer["id"]:
                    continue
                if any(_same_artifact(need, out) for out in _as_list(producer.get("produces_artifact"))):
                    yield producer, consumer, need

def test_external_inputs_are_still_consumed():
    """The carve-out is not a dumping ground: every entry must still be an
    artifact some phase actually declares it consumes."""
    consumed = [need for p in _manifest()["phases"] for need in _as_list(p.get("consumes"))]
    unused = [
        ext for ext in EXTERNAL_INPUTS
        if not any(_same_artifact(need, ext) for need in consumed)
    ]
    assert not unused, f"EXTERNAL_INPUTS entries no phase consumes any more: {unused}"

def test_every_phase_has_a_numeric_order():
    """The ordering assertion below compares numbers; a missing or string order
    must fail loudly here rather than silently pass a different test."""
    bad = [
        f"{p.get('id')}={p.get('order')!r}"
        for p in _manifest()["phases"]
        if isinstance(p.get("order"), bool)
        or not isinstance(p.get("order"), (int, float))
    ]
    assert not bad, f"phase(s) with no finite numeric order: {bad}"

def test_every_producer_comes_before_its_consumer():
    """PD-003: for EVERY edge, producer order < consumer order."""
    late = []
    for producer, consumer, artifact in _edges(_manifest()):
        if not producer["order"] < consumer["order"]:
            late.append(
                f"{consumer['id']} (order {consumer['order']}) consumes {artifact} "
                f"produced by {producer['id']} (order {producer['order']})")
    assert not late, (
        f"{len(late)} edge(s) where the producer's order is not lower than the "
        "consumer's:\n  " + "\n  ".join(late))
