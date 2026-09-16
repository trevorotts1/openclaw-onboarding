"""PD-TEST-156 -- a phase whose DISPATCH reads the slide index must DECLARE it.

THE DEFECT, measured on run pres-operator-1d269693-ff54-4b1f-b45a-61dc7d8ca4d4.

`working/copy/slides.json` is the renderer's structured index. NO manifest phase
declares it as `produces_artifact`; instead the ENGINE materialises it at dispatch
time, immediately before the executor branch, via

    presentation_job/slides_assembly.py::ensure_slides_json()   # phases.py:2516

and that seam is deliberately keyed on the phase's own declaration:

    if not slides_assembly.phase_consumes_slides_json(phase.consumes):
        return                      # no-op

So a phase that NEEDS the index but does not DECLARE it never gets one. `P4-PROMPT`
is exactly that phase: `_dispatch_prompt_phase_parallel` reads
`working/copy/slides.json` directly to normalize its per-slide payloads and refuses
with "P4-PROMPT parallel dispatch could not normalize any slide payloads from
slides.json/arc_allocation.json" when it is missing -- and the live ledger carries
that exact string.

The circle then closes. The only phases that DID declare the index were
`P-STYLE-PREVIEW`, `P-STYLE-SPEC` and `P4-RENDER` -- and every one of them consumes
`working/prompts/slide-*.txt`, which is what `P4-PROMPT` produces. So the phases
that could trigger the producer were all DOWNSTREAM of the phase that was failing
for want of the artifact: nothing could ever write the index, so `P4-PROMPT` could
never succeed, so the render could never be reached.

The producer itself is NOT missing code -- `test_pd081_slides_json_producer.py` is
17 passed / 1 failed, the one failure being the already-numbered PD-TEST-123
(`build_deck._count_output_slides` returns 3 on a run dir with no copy and no
slides.json, instead of None). This was a DECLARATION gap.

WHAT THESE TESTS PIN
  * the phase(s) named in the dispatcher's slide-normalizing fan-out path DECLARE
    the index -- derived from `dispatcher.py` itself, so a second phase added to
    that path is caught rather than silently deadlocked;
  * every declaring phase's declaration actually satisfies the seam's matcher, so
    a cosmetic rename cannot make the trigger a no-op;
  * the fix is DAG-NEUTRAL: because no phase PRODUCES the index, declaring it adds
    no artifact edge, so it cannot reorder or cycle the plan.
"""
from __future__ import annotations

import ast
import json
import pathlib
import re
import subprocess
import sys
from typing import Set

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import execution_plan as ep  # noqa: E402
from presentation_job import slides_assembly as sa  # noqa: E402

REPO_ROOT = SCRIPTS.parents[4]
MANIFEST = REPO_ROOT / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
DISPATCHER = SCRIPTS / "presentation_job" / "dispatcher.py"

#: The fan-out function that normalizes per-slide payloads straight out of the
#: index. Its refusal string is the live failure PD-TEST-156 was found on.
SLIDE_NORMALIZING_FUNCTION = "_dispatch_prompt_phase_parallel"


def _load_phases():
    assert MANIFEST.is_file(), f"the manifest this guards is missing: {MANIFEST}"
    obj = json.loads(MANIFEST.read_text(encoding="utf-8"))
    phases = obj.get("phases")
    assert isinstance(phases, list) and phases, "manifest carries no phases[]"
    return phases


def _phases_named_in(function_name: str) -> Set[str]:
    """Phase ids the named dispatcher function mentions in its own source.

    Derived from the CODE, not restated from the fix: if a second phase is ever
    routed through the slide-normalizing path, its id appears here and the
    assertion below demands it declare the index too."""
    src = DISPATCHER.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == function_name), None)
    assert fn is not None, (
        f"dispatcher.{function_name} no longer exists -- this guard is pinned to "
        "the function that reads working/copy/slides.json for a prompt fan-out; "
        "if that work moved, repoint this test rather than deleting it")
    lines = src.split("\n")[fn.lineno - 1:fn.end_lineno]
    # Only the LITERAL phase ids matter; the regex is deliberately narrow.
    return set(re.findall(r"\b(P4-[A-Z]+|P-[A-Z0-9.\-]+)\b", "\n".join(lines)))


def test_the_guard_is_not_vacuous():
    phases = _load_phases()
    assert sa.SLIDES_JSON_REL == "working/copy/slides.json", sa.SLIDES_JSON_REL
    named = _phases_named_in(SLIDE_NORMALIZING_FUNCTION)
    assert named, "the slide-normalizing function names no phase -- guard is vacuous"
    ids = {p["id"] for p in phases}
    assert named & ids, f"none of {sorted(named)} is a real manifest phase"

    declaring = [p["id"] for p in phases
                 if sa.phase_consumes_slides_json(p.get("consumes"))]
    assert declaring, (
        "NO phase declares the render index, so the engine's producer seam can "
        "never fire and the render index can never be written (PD-TEST-156)")


def test_every_slide_normalizing_phase_declares_the_index():
    phases = _load_phases()
    by_id = {p["id"]: p for p in phases}
    named = {pid for pid in _phases_named_in(SLIDE_NORMALIZING_FUNCTION) if pid in by_id}

    offenders = [pid for pid in sorted(named)
                 if not sa.phase_consumes_slides_json(by_id[pid].get("consumes"))]

    assert not offenders, (
        "these phases read working/copy/slides.json during DISPATCH but do not "
        f"DECLARE it in `consumes`: {offenders}. The engine materialises the index "
        "only for phases that declare it (slides_assembly.phase_consumes_slides_json, "
        "called from phases.py), so the producer is a NO-OP for them and their "
        "dispatch fails with 'could not normalize any slide payloads'. Add "
        f"{sa.SLIDES_JSON_REL!r} to their `consumes` in "
        "universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json (and restamp "
        "MANIFEST-SOURCE.txt + universal-sops/_content-manifest.json).")

    # Named explicitly so a change to the set is a deliberate, visible edit.
    assert named == {"P4-PROMPT"}, (
        f"the slide-normalizing fan-out path now names {sorted(named)} -- update "
        "this expectation deliberately (and confirm every member declares the index)")


def test_the_declaration_is_DAG_neutral():
    """No phase PRODUCES the index, so declaring it must add NO artifact edge.

    This is what makes the fix safe to ship: it turns the producer seam on without
    reordering the plan or creating a dependency (and therefore without any cycle
    risk)."""
    phases = _load_phases()
    producers = [p["id"] for p in phases
                 if p.get("produces_artifact") == sa.SLIDES_JSON_REL]
    assert producers == [], (
        f"a phase now PRODUCES {sa.SLIDES_JSON_REL} ({producers}) -- that changes "
        "the DAG, so this test's no-new-edge claim must be revisited")

    declaring = [p for p in phases if sa.phase_consumes_slides_json(p.get("consumes"))]
    reduced = json.loads(json.dumps(phases))
    for p in reduced:
        if sa.phase_consumes_slides_json(p.get("consumes")):
            p["consumes"] = [c for c in p["consumes"]
                             if str(c).strip().lower() != sa.SLIDES_JSON_REL]

    assert ep.build_edges(phases) == ep.build_edges(reduced), (
        "declaring the render index changed the artifact DAG -- it has no "
        "producer, so it must be edge-free; a diff here means either a producer "
        "appeared or the declaration is being matched as another artifact")

    assert len(declaring) >= 2, (
        "fewer than two phases declare the index -- check the fix is still present")
