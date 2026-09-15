"""PD-TEST-081 — the producer for working/copy/slides.json.

WHY THIS FILE EXISTS. `working/copy/slides.json` is the artifact the renderer
hard-requires and the manifest's ONLY orphan consumed pattern:

  * `build_deck.py`'s P4-RENDER command passes it as `positional[0]`, and
    `main()` does `slides_path = Path(positional[0])` then
    `if not slides_path.exists(): print("FATAL: slides.json not found"); sys.exit(2)`
  * THREE phases declare it in `consumes` (P-STYLE-SPEC, P-STYLE-PREVIEW,
    P4-RENDER) and ZERO declare it in `produces_artifact`:
    `execution_plan.find_unproduced_consumed_artifacts` over all 62 phases of
    the real manifest returns exactly `['working/copy/slides.json']`.
  * `_is_intake_file` exempts ONLY `raw/source-brief.*` and
    `working/copy/intake.json`, so the engine's own rules say it is NOT a run
    input.

EVERY pre-existing test HAND-SUPPLIES slides.json (~20 sites in
test_preflight.py plus test_slide_craft.py and tests/unit/*.sh). That is
precisely why CI stayed green while the live pipeline could not render: no test
ever exercised a producer, because there was none.

THESE TESTS EXERCISE THE REAL PRODUCER. They build a run dir carrying only the
two artifacts the pipeline actually produces before render -- `slides_copy.md`
(P4-COPY) and `arc_allocation.json` (P3-ARC, in the LIVE `slide_allocations` +
`slide_number` + `arc_section` shape) -- and never write slides.json by hand.
Delete `presentation_job/slides_assembly.py` or the engine hook and they fail.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import slides_assembly as sa  # noqa: E402
import build_deck  # noqa: E402
from presentation_job import fanout  # noqa: E402

MANIFEST = (SCRIPTS.parent.parent.parent.parent.parent
            / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json")

#: The three consumers the defect report names, in manifest order.
EXPECTED_CONSUMERS = {"P-STYLE-SPEC", "P-STYLE-PREVIEW", "P4-RENDER"}


# ---------------------------------------------------------------------------
# Fixtures. Deliberately the LIVE P3-ARC spelling, not the canonical one: the
# live run's P3-ARC agent emitted `slide_allocations` with per-slot
# `slide_number` plus an `arc_section` label, and that is the shape the
# producer must survive (PD-TEST-067 documents the same divergence).
# ---------------------------------------------------------------------------
def _live_arc(n: int) -> dict:
    return {
        "deck_slug": "probe-deck",
        "arc_sections": ["Opening / Priority Stack", "The Proof"],
        "slide_allocations": [
            {
                "slide_number": i,
                "arc_section": "opening" if i <= 2 else "proof",
                "beat": "HOOK" if i == 1 else "ANCHOR",
            }
            for i in range(1, n + 1)
        ],
    }


def _copy_md(n: int) -> str:
    """slides_copy.md exactly as dispatcher._reduce_markdown_sections emits it:
    `SLIDE <n>` on its own line, then the block body."""
    blocks = []
    for i in range(1, n + 1):
        blocks.append(
            f"SLIDE {i}\n"
            f"<!-- ARC: {'HOOK' if i == 1 else 'ANCHOR'} -->\n"
            f"Headline for slide {i}.\n"
            f"Supporting line for slide {i} with a 42% figure.\n"
            f"HOOK_REFRAIN: {'yes' if i == 1 else 'no'}\n"
            f"LADDER: DROP1\n")
    return "".join(blocks)


def _seed_run(tmp_path: Path, n: int = 3, *, arc: bool = True,
              copy: bool = True) -> Path:
    run_dir = tmp_path / "run"
    (run_dir / "working" / "copy").mkdir(parents=True)
    if arc:
        (run_dir / "working" / "copy" / "arc_allocation.json").write_text(
            json.dumps(_live_arc(n), indent=2))
    if copy:
        (run_dir / "working" / "copy" / "slides_copy.md").write_text(_copy_md(n))
    # NOTE: slides.json is NEVER written here -- producing it is the thing
    # under test. Every assertion below reads the file the producer wrote.
    return run_dir


# ---------------------------------------------------------------------------
# (a) the assembly produces a valid slides.json from the two real inputs
# ---------------------------------------------------------------------------
def test_assembly_produces_valid_slides_json_from_live_arc_shape(tmp_path):
    run_dir = _seed_run(tmp_path, 5)
    assert not (run_dir / sa.SLIDES_JSON_REL).exists(), "precondition: no hand-supplied file"

    result = sa.ensure_slides_json(run_dir)

    assert result.status == "ok", result.reason
    assert result.written is True
    path = run_dir / sa.SLIDES_JSON_REL
    assert path.is_file(), "the producer must write the renderer's positional"

    slides = json.loads(path.read_text())
    # build_deck.main() requires a NON-EMPTY top-level JSON array...
    assert isinstance(slides, list) and slides
    assert len(slides) == 5
    # ...and requires slide/scene/copy on every entry, with unique int ordinals.
    seen = set()
    for s in slides:
        assert isinstance(s, dict)
        for req in ("slide", "scene", "copy"):
            assert req in s, f"missing required field {req}"
        assert isinstance(s["slide"], int) and not isinstance(s["slide"], bool)
        assert s["slide"] not in seen, "ordinals must be unique"
        seen.add(s["slide"])
        assert isinstance(s["scene"], str) and s["scene"].strip()
        assert isinstance(s["copy"], list) and s["copy"]
        assert all(isinstance(c, str) and c for c in s["copy"])
    assert seen == {1, 2, 3, 4, 5}

    # The copy is the writer's REAL text: engine metadata and ARC marker syntax
    # are stripped (they are not pixels), the prose survives VERBATIM.
    first = slides[0]
    assert first["copy"][0] == "Headline for slide 1."
    assert any("42%" in c for c in first["copy"])
    assert not any("ARC:" in c for c in first["copy"])
    assert not any(c.upper().startswith("LADDER") for c in first["copy"])
    assert not any(c.upper().startswith("HOOK_REFRAIN") for c in first["copy"])

    # The arc label is carried under EVERY spelling the two reader generations
    # accept, so neither the base section join nor PD-TEST-067's can drift.
    assert first["arc_section"] == "opening"
    assert first["arc"] == "opening"
    assert first["section"] == "opening"
    assert first["name"] == "opening"
    assert first["ordinal"] == 1


def test_assembly_is_deterministic_and_idempotent(tmp_path):
    run_dir = _seed_run(tmp_path, 4)
    first = sa.ensure_slides_json(run_dir)
    assert first.written is True
    body = (run_dir / sa.SLIDES_JSON_REL).read_text()

    second = sa.ensure_slides_json(run_dir)
    assert second.status == "up_to_date"
    assert second.written is False, "a no-op re-run must not rewrite the index"
    assert (run_dir / sa.SLIDES_JSON_REL).read_text() == body


# ---------------------------------------------------------------------------
# (b) arc_slides.load_slots and build_deck._count_output_slides agree on N
# ---------------------------------------------------------------------------
def test_count_output_slides_matches_the_arc_slide_count(tmp_path):
    run_dir = _seed_run(tmp_path, 6)
    arc_count = len(json.loads(
        (run_dir / sa.ARC_ALLOCATION_REL).read_text())["slide_allocations"])
    assert arc_count == 6

    sa.ensure_slides_json(run_dir)

    # build_deck's REAL coverage/rich-prompt gate count -- both call shapes:
    # the run-dir form and the H3 positional form (the exact file rendered).
    assert build_deck._count_output_slides(run_dir) == arc_count
    assert build_deck._count_output_slides(
        run_dir, run_dir / sa.SLIDES_JSON_REL) == arc_count

    # The verbatim-words-baked map reads the same N ordinals.
    copy_map = build_deck._load_slide_copy_map(run_dir, run_dir / sa.SLIDES_JSON_REL)
    assert len(copy_map) == arc_count
    assert sorted(copy_map) == list(range(1, arc_count + 1))


def test_prompt_slide_count_and_fanout_enumerator_agree(tmp_path):
    """The two engine readers that starved the live run must both see N."""
    from presentation_job import dispatcher

    run_dir = _seed_run(tmp_path, 5)
    sa.ensure_slides_json(run_dir)

    assert dispatcher._prompt_slide_count(run_dir) == 5
    units = fanout._slides_for_units(run_dir)
    assert len(units) == 5
    assert [u["ordinal"] for u in units] == [1, 2, 3, 4, 5]


def test_arc_slides_reader_agrees_when_that_module_is_present(tmp_path):
    """PD-TEST-067's single reader must accept the emitted shape.

    `presentation_job/arc_slides.py` is PD-TEST-067's module and is NOT on this
    branch's base (`origin/main`); it lands on its own branch. When it IS
    importable this asserts full agreement -- the emitted shape is accepted by
    the wide reader AND by build_deck, on the same N. When it is absent the test
    skips with that reason rather than pretending to have checked, and the
    always-run test below pins the same acceptance rules structurally.
    """
    arc_slides = pytest.importorskip(
        "presentation_job.arc_slides",
        reason="PD-TEST-067 (arc_slides.py) is not on this base; it lands on "
               "fix/pd067-arc-slide-shape-contract. Structural equivalence is "
               "pinned by test_emitted_shape_satisfies_pd067_acceptance_rules.")

    run_dir = _seed_run(tmp_path, 4)
    sa.ensure_slides_json(run_dir)

    slots = arc_slides.load_slots(run_dir)
    assert slots is not None
    assert len(slots) == 4
    assert [s["ordinal"] for s in slots] == [1, 2, 3, 4]
    assert [s["slide"] for s in slots] == [1, 2, 3, 4]
    assert arc_slides.load_slide_count(run_dir) == 4
    # Same N as build_deck's real gate, from the SAME file.
    assert build_deck._count_output_slides(run_dir) == arc_slides.load_slide_count(run_dir)
    # The section join resolves on both sides of PD-TEST-067's contract.
    assert arc_slides.section_names_from_obj(
        json.loads((run_dir / sa.SLIDES_JSON_REL).read_text())) == ["opening", "proof"]
    assert [arc_slides.slot_label(s) for s in slots] == \
        ["opening", "opening", "proof", "proof"]


def test_emitted_shape_satisfies_pd067_acceptance_rules(tmp_path):
    """Structural pin of the shared shape contract (always runs).

    Restates, against the produced file, the acceptance rules
    `presentation_job/arc_slides.py` declares: container keys
    slots|allocation|slides|slide_allocations, ordinal keys
    ordinal|slide|slide_number, label keys arc_section|arc|section|name. A bare
    top-level array is accepted by that reader AND by build_deck, which is why
    the producer emits one -- and why this test needs no dict envelope at all.
    """
    run_dir = _seed_run(tmp_path, 3)
    sa.ensure_slides_json(run_dir)
    obj = json.loads((run_dir / sa.SLIDES_JSON_REL).read_text())

    assert isinstance(obj, list), ("a bare top-level array is the ONE shape "
                                   "every reader accepts")
    for position, slot in enumerate(obj, start=1):
        ordinal = next((slot[k] for k in sa.ARC_ORDINAL_KEYS
                        if isinstance(slot.get(k), int)
                        and not isinstance(slot.get(k), bool)), None)
        assert ordinal == position, f"no accepted ordinal key on slot {position}"
        label = next((slot[k] for k in sa.ARC_LABEL_KEYS
                      if isinstance(slot.get(k), str) and slot[k].strip()), None)
        assert label is not None, f"no accepted arc label on slot {position}"


# ---------------------------------------------------------------------------
# (c) the produced file is what P4-RENDER's positional resolves to
# ---------------------------------------------------------------------------
def test_produced_file_is_p4_render_positional(tmp_path):
    """Read the REAL manifest's P4-RENDER command and resolve its positional.

    This is the wiring proof: the file the producer writes must be the exact
    path P4-RENDER hands build_deck as positional[0], or the render still fails.
    """
    assert MANIFEST.is_file(), f"manifest not found at {MANIFEST}"
    manifest = json.loads(MANIFEST.read_text())
    phase = next(p for p in manifest["phases"] if p["id"] == "P4-RENDER")
    cmd = phase["executor"]["cmd"]

    toks = cmd.split()
    assert toks[0] == "python3" and toks[1].endswith("build_deck.py")
    positional = toks[2]  # build_deck.py <slides.json> <out.pptx> ...

    run_dir = _seed_run(tmp_path, 3)
    resolved = Path(positional.replace("{run_dir}", str(run_dir)))
    assert resolved == run_dir / sa.SLIDES_JSON_REL, (
        f"P4-RENDER positional {positional!r} is not the produced artifact")

    # Before the producer runs, the renderer's positional does not exist --
    # this is the defect, reproduced end to end.
    assert not resolved.exists(), "defect precondition: no producer, no file"

    sa.ensure_slides_json(run_dir)
    assert resolved.is_file(), "the producer must create the renderer's positional"
    # ...and build_deck accepts it as a deck (not just as a file).
    assert build_deck._count_output_slides(run_dir, resolved) == 3


def test_producer_matches_every_manifest_consumer_of_the_index(tmp_path):
    """The trigger must fire for ALL real consumers of the artifact.

    Guards the regression that caused this defect: a manifest whose `consumes`
    names the index must be recognised by the producer's trigger. If a future
    manifest adds a consumer (or renames the path), this fails loudly instead of
    silently starving that phase the way the live run starved P4-RENDER.
    """
    assert MANIFEST.is_file(), f"manifest not found at {MANIFEST}"
    manifest = json.loads(MANIFEST.read_text())

    # Use the engine's OWN orphan finder as the authority on the defect.
    from presentation_job.execution_plan import find_unproduced_consumed_artifacts
    orphans = find_unproduced_consumed_artifacts(manifest["phases"])
    assert sa.SLIDES_JSON_REL in orphans, (
        "if this artifact is no longer the manifest's orphan, the producer's "
        "justification/siting must be revisited")

    consumers = {p["id"] for p in manifest["phases"]
                 if sa.SLIDES_JSON_REL in (p.get("consumes") or [])}
    assert consumers == EXPECTED_CONSUMERS, (
        f"the set of consumers changed: {sorted(consumers)}")

    for phase in manifest["phases"]:
        if sa.SLIDES_JSON_REL not in (phase.get("consumes") or []):
            continue
        assert sa.phase_consumes_slides_json(phase["consumes"]), (
            f"{phase['id']} consumes the index but does not trigger the producer")
        # And the producer is not accidentally triggered by near-miss names.
    assert not sa.phase_consumes_slides_json([sa.ARC_ALLOCATION_REL])
    assert not sa.phase_consumes_slides_json([sa.SLIDES_COPY_REL])
    assert not sa.phase_consumes_slides_json(["working/copy/style_preview_spec.json"])


def test_engine_hook_materialises_the_index_before_the_executor(tmp_path):
    """The ENGINE seam, not just the module: the hook writes the file.

    Constructs the real Engine class without its heavy __init__ and calls the
    one method the dispatch path calls, with the real Phase object resolved from
    the run's own manifest -- so a deleted/renamed hook fails here.
    """
    from presentation_job.phases import Engine

    run_dir = _seed_run(tmp_path, 3)
    manifest = json.loads(MANIFEST.read_text())
    consumer = next(p for p in manifest["phases"]
                    if p["id"] == "P4-RENDER")

    class _Phase:
        id = consumer["id"]
        consumes = consumer["consumes"]

    engine = Engine.__new__(Engine)
    engine.run_dir = run_dir

    events = []

    class _Report:
        def event(self, kind, message, **extra):
            events.append((kind, message))

    engine.report = _Report()

    assert not (run_dir / sa.SLIDES_JSON_REL).exists()
    engine._materialise_slides_index(_Phase())
    assert (run_dir / sa.SLIDES_JSON_REL).is_file(), (
        "the engine hook must produce the renderer's index")
    assert any(k == "phase.slides_index_produced" for k, _m in events), events

    # A phase that does NOT consume the index is untouched.
    other_run = _seed_run(tmp_path / "other", 3)

    class _Other:
        id = "P4-PROMPT"
        consumes = ["working/copy/slides_copy.md"]

    engine.run_dir = other_run
    engine._materialise_slides_index(_Other())
    assert not (other_run / sa.SLIDES_JSON_REL).exists()


# ---------------------------------------------------------------------------
# (d) empty/absent copy is reported honestly, never a silently-empty index
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("copy_text,expected_status", [
    (None, "no_copy_source"),          # absent
    ("", "no_copy_source"),            # zero bytes
    ("   \n\n\t\n", "no_copy_source"),  # whitespace only
    ("# Deck\n\nProse with no SLIDE blocks.\n", "no_slide_blocks"),
])
def test_absent_or_empty_copy_writes_nothing_and_says_so(
        tmp_path, copy_text, expected_status):
    run_dir = _seed_run(tmp_path, 3, copy=False)
    if copy_text is not None:
        (run_dir / sa.SLIDES_COPY_REL).write_text(copy_text)

    result = sa.ensure_slides_json(run_dir)

    assert result.status == expected_status, result.reason
    assert result.written is False
    assert result.slides == []
    assert result.reason.strip(), "an honest producer always explains itself"
    assert not (run_dir / sa.SLIDES_JSON_REL).exists(), (
        "a silently-empty slides.json is exactly the failure mode this module "
        "exists to prevent -- nothing may be written")


def test_empty_copy_never_yields_a_silently_empty_slides_json(tmp_path):
    """The strongest form of (d): if a file IS written it is never empty."""
    run_dir = _seed_run(tmp_path, 3, copy=False)

    result = sa.ensure_slides_json(run_dir)

    path = run_dir / sa.SLIDES_JSON_REL
    if path.exists():
        obj = json.loads(path.read_text())
        assert isinstance(obj, list) and len(obj) > 0
    assert not result.ok
    # The renderer's own gate must NOT report a deck here -- absence is absence.
    assert build_deck._count_output_slides(run_dir) is None


def test_count_mismatch_between_copy_and_arc_refuses_to_write(tmp_path):
    """copy(3) vs arc(4) is a real defect: neither side may be silently chosen."""
    run_dir = _seed_run(tmp_path, 4, copy=False)
    (run_dir / sa.SLIDES_COPY_REL).write_text(_copy_md(3))

    result = sa.ensure_slides_json(run_dir)

    assert result.status == "count_mismatch", result.reason
    assert result.written is False
    assert "4" in result.reason and "3" in result.reason
    assert not (run_dir / sa.SLIDES_JSON_REL).exists()


def test_slide_block_with_no_rendered_copy_refuses_to_write(tmp_path):
    """A block of ARC markers and engine fields carries no pixels."""
    run_dir = _seed_run(tmp_path, 1, arc=False, copy=False)
    (run_dir / sa.SLIDES_COPY_REL).write_text(
        "SLIDE 1\n<!-- ARC: HOOK -->\nHOOK_REFRAIN: yes\nLADDER: DROP1\n")

    result = sa.ensure_slides_json(run_dir)

    assert result.status == "no_copy_lines", result.reason
    assert result.written is False
    assert not (run_dir / sa.SLIDES_JSON_REL).exists()


def test_producer_works_without_an_arc_allocation(tmp_path):
    """The arc is metadata; the copy alone still yields a complete deck."""
    run_dir = _seed_run(tmp_path, 3, arc=False)

    result = sa.ensure_slides_json(run_dir)

    assert result.status == "ok", result.reason
    slides = json.loads((run_dir / sa.SLIDES_JSON_REL).read_text())
    assert [s["slide"] for s in slides] == [1, 2, 3]
    assert build_deck._count_output_slides(run_dir) == 3


def test_canonical_arc_shape_also_assembles(tmp_path):
    """The golden-quest `slots` + `slide` spelling must work too, not just live."""
    run_dir = tmp_path / "run"
    (run_dir / "working" / "copy").mkdir(parents=True)
    (run_dir / "working" / "copy" / "arc_allocation.json").write_text(json.dumps({
        "deck_slug": "golden",
        "slots": [{"slide": i, "arc_section": "Avatar"} for i in range(1, 4)],
    }))
    (run_dir / "working" / "copy" / "slides_copy.md").write_text(_copy_md(3))

    result = sa.ensure_slides_json(run_dir)

    assert result.status == "ok", result.reason
    slides = json.loads((run_dir / sa.SLIDES_JSON_REL).read_text())
    assert [s["arc_section"] for s in slides] == ["Avatar"] * 3
