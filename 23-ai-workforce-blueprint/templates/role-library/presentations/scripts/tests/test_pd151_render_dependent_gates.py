"""PD-TEST-151 -- a preflight gate that NEEDS the rendered slides must WAIT for them.

WHY THIS EXISTS (the live defect this pins)
-------------------------------------------
`P-SHIFT-QC` declares `produces_artifact: working/qc/priority_shift_report.json`
and a `preflight` checker `_chk_priority_shift_ledger`. That checker opens with

    pngs = _gather_rendered_pngs(run_dir)
    if not pngs:
        return ""          # defer pre-render -- and WRITE NOTHING

so it only ever writes the report once `renders/slide-*.png` exist. Its
`preflight.label` says the same thing in words: "the ONLY phase where
copy+design+rendered images coexist ... DEFERS pre-render."

But the manifest gave `P-SHIFT-QC` only `consumes: [priority_shift_spec.json,
slides_copy.md]` -- NO render artifact. `execution_plan.build_edges()` builds the
DAG purely from `produces -> consumes` intersections, so with that omission there
was NO edge from `P4-RENDER` and the ready-queue scheduler admitted the phase as
soon as the copy existed, i.e. PRE-render. Measured live on run
`pres-operator-1d269693-ff54-4b1f-b45a-61dc7d8ca4d4`: prerequisites for
`P-SHIFT-QC` were `['P0B-PRIORITY', 'P4-COPY']`, zero slide PNGs existed, the
checker deferred and never wrote the report -- while the phase VERIFIER
(`runfacts.verify_priority_shift`, via `phase_verifiers`'s
`'P-SHIFT-QC': _registry_gate_verifier('qc:priority_shift')`) requires exactly
that report, in exactly `_chk_priority_shift_ledger`'s schema (`schema ==
'priority_shift_report/v1'`, `pass is True`, every ledger row `pass is True`).

The result was a gate that could not be earned: the phase spent its whole paid
retry budget and parked the entire run, offering only an `owner_skip_approval`
token as the way past it. That is the PD-TEST-113 class (a verifier enforcing a
rule its own consumer never reaches), except here it blocked delivery.

THE INVARIANT
-------------
If a phase's preflight checker cannot run before the render, the manifest must
make that phase WAIT for the render. This test derives both halves from the real
artifacts rather than restating the fix: it reads the call graph of
`build_deck.py` to find which checker functions transitively need
`_gather_rendered_pngs`, reads the real `PIPELINE-MANIFEST.json` to find which
phases dispatch those checkers, and asserts each of them transitively depends on
the phase that PRODUCES `renders/slide-*.png`.

It is deliberately general: a future phase wired to an image-reading checker
without a render dependency fails here, instead of parking a run weeks later.
"""
from __future__ import annotations

import ast
import json
import pathlib
import sys
from typing import Dict, List, Set

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import execution_plan as ep  # noqa: E402

REPO_ROOT = SCRIPTS.parents[4]
MANIFEST = REPO_ROOT / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
BUILD_DECK = SCRIPTS / "build_deck.py"

#: The artifact the render phase produces and every image-reading gate needs.
RENDER_ARTIFACT = "renders/slide-*.png"


def _load_phases() -> List[dict]:
    assert MANIFEST.is_file(), f"the manifest this guards is missing: {MANIFEST}"
    obj = json.loads(MANIFEST.read_text(encoding="utf-8"))
    phases = obj.get("phases")
    assert isinstance(phases, list) and phases, "manifest carries no phases[]"
    return phases


def _functions_needing_rendered_pngs() -> Set[str]:
    """Names of functions in build_deck.py that transitively call
    _gather_rendered_pngs -- the only way a checker can require rendered slides."""
    tree = ast.parse(BUILD_DECK.read_text(encoding="utf-8"))
    calls: Dict[str, Set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names: Set[str] = set()
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    f = sub.func
                    if isinstance(f, ast.Name):
                        names.add(f.id)
                    elif isinstance(f, ast.Attribute):
                        names.add(f.attr)
            calls[node.name] = names
    dependents: Set[str] = set()
    changed = True
    while changed:  # transitive closure over the intra-module call graph
        changed = False
        for fn, callees in calls.items():
            if fn in dependents:
                continue
            if "_gather_rendered_pngs" in callees or (callees & dependents):
                dependents.add(fn)
                changed = True
    return dependents


def _transitive_prerequisites(edges: Dict[str, List[str]]) -> Dict[str, Set[str]]:
    direct: Dict[str, Set[str]] = {}
    for producer, consumers in edges.items():
        for consumer in consumers:
            direct.setdefault(consumer, set()).add(producer)
    closure: Dict[str, Set[str]] = {}
    for phase, preds in direct.items():
        seen: Set[str] = set()
        stack = list(preds)
        while stack:
            p = stack.pop()
            if p in seen:
                continue
            seen.add(p)
            stack.extend(direct.get(p, ()))
        closure[phase] = seen
    return closure


def _required_checkers(phase: dict) -> List[str]:
    """Every checker the manifest makes REQUIRED for this phase.

    Both spellings count, and keeping them together is the point: the first
    version of this test read only `preflight.checker`, which silently skipped
    `additional_preflights[]` -- a SIBLING of `preflight`, not a child of it.
    `P-IMAGE-QC` carries `additional_preflights: [_chk_salience_apex]` and
    `_chk_salience_apex` reads rendered PNGs, so it was covered only by
    accident (its primary `_chk_image_qc` happens to read PNGs too, and the
    phase happens to depend on the render). An independent review caught that
    gap; this helper is the fix, so a phase whose ONLY render-reading checker
    sits in `additional_preflights` is now caught on its own merits."""
    out: List[str] = []
    pf = phase.get("preflight") or {}
    if pf.get("required") and pf.get("checker"):
        out.append(pf["checker"])
    for ap in phase.get("additional_preflights") or []:
        if isinstance(ap, dict) and ap.get("required") and ap.get("checker"):
            out.append(ap["checker"])
    return out


def _png_producers(phases: List[dict]) -> Set[str]:
    out = set()
    for p in phases:
        produced = p.get("produces_artifact")
        if produced == RENDER_ARTIFACT:
            out.add(p["id"])
    return out


def test_the_invariant_is_not_vacuous():
    """Both halves must find something, or the assertions below prove nothing."""
    needing = _functions_needing_rendered_pngs()
    assert "_gather_rendered_pngs" in BUILD_DECK.read_text(encoding="utf-8")
    assert needing, (
        "no function in build_deck.py reads rendered PNGs -- if that is genuinely "
        "true, this guard is obsolete and should be deleted deliberately, not "
        "silently emptied")

    phases = _load_phases()
    dispatched = {c for p in phases for c in _required_checkers(p)}
    assert dispatched & needing, (
        "no phase dispatches a render-reading preflight checker any more; the "
        f"guard would pass vacuously (checkers={sorted(c for c in dispatched if c)})")

    assert _png_producers(phases), (
        f"no phase produces {RENDER_ARTIFACT!r}, so 'wait for the render' is "
        "unsatisfiable and this guard would fail for the wrong reason")


def test_every_render_reading_preflight_gate_waits_for_the_render():
    phases = _load_phases()
    needing = _functions_needing_rendered_pngs()
    edges = ep.build_edges(phases)
    prereqs = _transitive_prerequisites(edges)
    producers = _png_producers(phases)

    offenders = []
    checked = []
    for p in phases:
        for checker in _required_checkers(p):
            if checker not in needing:
                continue
            checked.append((p["id"], checker))
            got = prereqs.get(p["id"], set())
            if not (got & producers):
                offenders.append(
                    f"{p['id']} dispatches {checker}() (transitively reads "
                    f"{RENDER_ARTIFACT}) but its prerequisites {sorted(got)} contain "
                    f"none of the producers {sorted(producers)}")

    assert checked, "no render-reading preflight gate found -- guard is vacuous"
    assert not offenders, (
        "a preflight gate cannot run before the artifact it reads, and nothing "
        "makes it wait:\n  " + "\n  ".join(offenders) +
        "\nAdd the render artifact to that phase's `consumes` in "
        "universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json (and "
        "restamp MANIFEST-SOURCE.txt + universal-sops/_content-manifest.json), or "
        "the phase will park the run on a gate it can never earn (PD-TEST-151).")

    # Both known members, named so a rename/removal is a visible test edit.
    # P-IMAGE-QC appears TWICE on purpose: its primary `_chk_image_qc` AND its
    # `additional_preflights` entry `_chk_salience_apex` both read rendered PNGs,
    # so both are asserted. Reading only the primary is the gap this pins shut.
    assert set(checked) == {
        ("P-IMAGE-QC", "_chk_image_qc"),
        ("P-IMAGE-QC", "_chk_salience_apex"),
        ("P-SHIFT-QC", "_chk_priority_shift_ledger"),
    }, ("the set of render-reading required gates changed: "
        f"{sorted(checked)} -- update this expectation deliberately (and confirm "
        "the new member waits for the render)")
