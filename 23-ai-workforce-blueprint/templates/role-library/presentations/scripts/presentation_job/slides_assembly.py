from __future__ import annotations

"""presentation_job/slides_assembly.py -- THE PRODUCER for working/copy/slides.json.

WHY THIS MODULE EXISTS (PD-TEST-081, 2026-09-15).

``working/copy/slides.json`` is the artifact the RENDERER hard-requires and the
artifact THREE phases declare in ``consumes``:

    P-STYLE-SPEC      (manifest order 4.84, fanout by slide)
    P-STYLE-PREVIEW   (manifest order 4.85, executor: build_deck.py --sample)
    P4-RENDER         (manifest order 4.90, executor: build_deck.py <slides.json> ...)

and ZERO phases declare it in ``produces_artifact``. It is the manifest's ONLY
orphan consumed pattern: ``execution_plan.find_unproduced_consumed_artifacts``
over all 62 phases of ``universal-sops/presentation-slide-craft/
PIPELINE-MANIFEST.json`` returns exactly ``['working/copy/slides.json']``.

The render step therefore can never succeed on ANY run. ``build_deck.py``'s
P4-RENDER command is

    python3 scripts/build_deck.py {run_dir}/working/copy/slides.json ...

so ``slides_path = Path(positional[0])`` is that exact path, and

    if not slides_path.exists():
        print(f"FATAL: slides.json not found: {slides_path}", file=sys.stderr)
        sys.exit(2)

fires before a single render. The file was hand-supplied by ~20 TEST sites
(``test_preflight.py``, ``test_slide_craft.py``, ``tests/unit/*.sh``), which is
exactly why CI stayed green while the live pipeline could not render.

WHERE THE CONTENT LIVES. ``working/copy/arc_allocation.json`` (P3-ARC) carries
ordinals, sections and beat tags but NO copy. The per-slide copy exists only
inside ``working/copy/slides_copy.md`` (P4-COPY's markdown output). This module
is the missing deterministic link: it assembles slides.json from those two
(+ the owner's style choice when one has been picked).

WHY THE ENGINE OWNS IT, AND WHY THERE IS NO MANIFEST CHANGE. ``manifest.py``
already documents this file as engine-owned run-setup state:

    working/copy/slides.json -- the engine's positional build input: written at
    run setup by the P4 copy tooling + engine prep ... It is a build artifact of
    the run harness, not of any single declared phase, so it is exempt the same
    way intake files are.                       (manifest.py, V5 exemption note)

and ``manifest._ROOT_INPUTS`` exempts it from the no-producer check for exactly
that reason. This module implements that documented intent. It is called from
the engine's own executor choke point (``phases.py``, immediately before
``phase.executor_kind`` branches), so it reaches an IN-FLIGHT run on the next
phase dispatch with NO manifest change and therefore NO ``--repin``: the
manifest sha256 is byte-identical, so ``EXIT_MANIFEST_MISMATCH`` never fires.

Declaring a producer phase in ``produces_artifact`` instead would have changed
the manifest, forced a gated repin (PD-TEST-077), AND added artifact-DAG edges
that reschedule three phases -- a coordinator decision, not a silent side
effect. See the PR report for the full comparison.

THE SHAPE EMITTED, AND WHY IT IS NOT A THIRD SHAPE. ``slides.schema.json``
declares the renderer's input as a TOP-LEVEL JSON ARRAY of ``{slide, scene,
copy}``. That is the intersection every existing reader already accepts:

  * ``build_deck.main()``        -- ``isinstance(slides, list) and slides``,
                                    then requires ``slide``/``scene``/``copy``.
  * ``build_deck._count_output_slides._count_from``
                                 -- ``if isinstance(obj, list): return len(obj)``.
  * ``build_deck._load_slide_copy_map``
                                 -- ``obj if isinstance(obj, list) else ...``.
  * ``fanout._slides_for_units`` -- ``raw = obj if isinstance(obj, list) else ...``.
  * ``arc_slides.slots_from_obj`` (PD-TEST-067)
                                 -- ``if isinstance(obj, list): raw = obj``.

A bare list is therefore read by EVERY consumer including PD-TEST-067's new
single reader, so no reader has to widen and no third shape is invented. NOTE
that the two readers do NOT share a dict-container key set --
``arc_slides.SLIDE_LIST_KEYS`` accepts ``slots``/``allocation``/``slides``/
``slide_allocations`` while ``_count_output_slides`` reads ONLY ``slides`` -- so
a dict envelope would make them disagree for three of those four spellings. The
bare array has no such failure mode.

Per-slot keys are emitted in the union the readers already understand:
``slide`` AND ``ordinal`` (both spellings of the same ordinal, exactly as
``arc_slides.slots_from_obj`` normalises to), plus the arc label under
``arc_section`` (canonical, PD-TEST-067) AND ``arc``/``section``/``name``
(the legacy spellings this base's ``fanout._sections_for_units`` and
``dispatcher._section_ordinal_ranges`` still read). Emitting the label under
every accepted spelling is what makes the section join work on BOTH readers
without touching either -- the PD-TEST-067 defect class is a reader looking for
one spelling while the artifact carries another, and one producer emitting all
of them cannot reproduce it.

HONESTY CONTRACT (this is a gate input, so it fails closed and never guesses):

  * ``slides_copy.md`` absent, unreadable, or carrying ZERO ``SLIDE <n>``
    blocks -> NOTHING is written and the reason is returned. It never emits a
    silently-empty or fabricated slides.json. The phase's own verifier owns the
    loud failure, as it did before.
  * the copy's ordinal set and the arc's ordinal set DISAGREE -> NOTHING is
    written; the reason names the symmetric difference. A deck whose structure
    and copy disagree is a real defect and neither side may be silently
    preferred.
  * a slide block that yields no copy lines -> NOTHING is written.
  * ``scene`` is a required-but-unrendered index field: ``build_deck.
    load_rich_prompt`` renders ``working/prompts/slide-NN.txt`` VERBATIM and
    never composes from ``scene``/``copy``. It is therefore derived
    deterministically from the deck's own arc label + the slide's own headline
    (+ the picked style directive), never invented from nothing, and documented
    here as the index field it is.
"""

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Artifact locations. SLIDES_JSON_REL is the exact path P4-RENDER's executor
# passes as build_deck's positional[0], and the path all three consumers name.
# ---------------------------------------------------------------------------
SLIDES_JSON_REL = "working/copy/slides.json"
SLIDES_COPY_REL = "working/copy/slides_copy.md"
ARC_ALLOCATION_REL = "working/copy/arc_allocation.json"
STYLE_SPEC_REL = "working/copy/style_preview_spec.json"
STYLE_CHOICE_REL = "working/copy/style_preview_choice.json"

# ---------------------------------------------------------------------------
# Accepted input shapes. These tuples are the PD-TEST-067 contract
# (presentation_job/arc_slides.py) reproduced so this module reads the SAME
# spellings that module does. PD-TEST-067 landed the wide reader on its own
# branch; this module is deliberately tolerant of BOTH the canonical
# (golden-quest) spellings and the live P3-ARC spellings so the producer works
# with or without that branch. If arc_slides is importable, the emitter is
# cross-checked against it in tests/test_pd081_slides_json_producer.py.
# ---------------------------------------------------------------------------
ARC_SLIDE_LIST_KEYS = ("slots", "allocation", "slides", "slide_allocations")
ARC_ORDINAL_KEYS = ("ordinal", "slide", "slide_number")
ARC_LABEL_KEYS = ("arc_section", "arc", "section", "name")

#: The canonical per-slide ordinal/label spellings this module EMITS.
OUT_ORDINAL_KEY = "slide"
OUT_ORDINAL_ALIAS = "ordinal"
OUT_LABEL_KEY = "arc_section"
#: Legacy label spellings this base's fanout/_section_ordinal_ranges still read.
OUT_LABEL_ALIASES = ("arc", "section", "name")

#: P4-COPY's block delimiter, byte-identical to `dispatcher._iter_slide_blocks`
#: and the P4-COPY output contract ("a line containing ONLY `SLIDE <n>`").
_SLIDE_SPLIT_RE = re.compile(r"(?im)^\s*SLIDE\s+(\d+)\s*$")

#: Literal ARC marker syntax (pitch_engines_check reads exactly these).
_ARC_MARKER_RE = re.compile(r"<!--\s*ARC:\s*[^>]*?-->|\[ARC:\s*[^\]]*?\]")

#: Engine metadata field lines that are NOT rendered copy. The P4-COPY contract
#: requires both on the slide block, but slides.schema.json defines copy[] as
#: "the EXACT text that must appear rendered on the slide" -- so these stay out.
#:
#: PD-TEST-158 (2026-09-16). The vocabulary below was INCOMPLETE, and that was not
#: cosmetic: `copy[]` drives `build_deck._load_slide_copy_map` -> the
#: AF-P-VERBATIM check, which FAILS a slide until every `copy[]` string is baked
#: verbatim into the image prompt. So any metadata left in `copy[]` is not merely
#: untidy -- the engine demands that its own bookkeeping be PAINTED ONTO THE
#: SLIDE. Measured live on run pres-operator-1d269693, whose
#: working/checkpoints/prompt-worker-results-attempts.jsonl carries:
#:
#:   AF-P-VERBATIM ... measured='copy not baked' required='SECTION: decision-rerank'
#:   AF-P-VERBATIM ... measured='copy not baked' required='PURPOSE: Force the
#:                     priority question out loud...'
#:
#: The list now matches the field vocabulary the P4-COPY contract actually
#: prescribes (sops/slide-copywriter-sops.md step 2, which every field is
#: mandatory in). Those NOT rendered on the slide, and therefore excluded:
#:
#:   SECTION        arc-section name (engine routing)
#:   PURPOSE        the one big idea, a brief addressed to the WRITER
#:   ARCHETYPE      A1-A5 layout id (design routing)
#:   LADDER         offer-ladder position (commercial routing)
#:   PROOF USED     proof-inventory item name
#:   RESEARCH_USED  research_map item_ids
#:   PEOPLE         yes/no + representation group
#:   HOOK_REFRAIN   yes/no + where the hook sits
#:   TEXT_ANCHOR    a layout token (bottom band | left block | ...)
#:   PRESENTER NOTE the SOP says these are "sentences the speaker says aloud that
#:                  are NOT on the slide"; demanding them be baked would put the
#:                  presenter's script ON the slide, which SOP step 1 forbids
#:   HOOK VARIANT   which hook variant was used (engine metadata)
#:   MOVE TAG       PD-TEST-173. Which of the eight build-move beats this slide
#:                  carries (PRIORITY_STACK | PRESENT_COST | HIGHER_PRIORITY |
#:                  VALUE_ANCHOR | URGENCY_SCARCITY | ABILITY_UNBLOCK |
#:                  RERANK_DEMAND | TRIGGER). build_deck.AF-NO-SHIFT REQUIRES
#:                  >=5 of those tags to appear in slides_copy.md, monotonic, so
#:                  the writer MUST record them in the copy file -- but the
#:                  copy-block template never said HOW, so the live run invented
#:                  `MOVE TAG: TRIGGER`. Nothing stripped it, so it became
#:                  copy[0] -- THE HEADLINE -- shifting every positional reader
#:                  by one for that slide.
#:
#:                  RETRACTED CLAIM (independent review): an earlier revision of
#:                  this comment said AF-P-VERBATIM then demanded the metadata be
#:                  PAINTED AS THE HEADLINE, citing slide-08.txt's single
#:                  occurrence of "MOVE TAG". That is FALSE. slide-08.txt:48 says
#:                  "This beat carries the structural tag MOVE TAG: TRIGGER. ...
#:                  Render nothing from that tag as visible artwork" -- the writer
#:                  mentioned it in a metadata section and expressly forbade
#:                  rendering it, and AF-P-VERBATIM is a substring-presence test,
#:                  so the mention SATISFIED it. The live run's checkpoints carry
#:                  56 AF-P-VERBATIM failures, ZERO of which name MOVE TAG.
#:
#:                  The real, measured harm is POSITIONAL, not verbatim:
#:                  slide_craft AF-OBI-1 counted the metadata line as a text block
#:                  (8 slides -> 2 with PD-TEST-169 -> 1 with this fix), and
#:                  build_deck AF-COPY-BAND graded slide 08's real subhead as an
#:                  over-long KICKER (5 -> 4 failing fields).
#:
#: Deliberately STILL RENDERED, and therefore still in `copy[]`: HEADLINE,
#: SUBHEAD and SUPPORTING (plus the bullets beneath SUPPORTING). Those are the
#: slide's words -- and, since PD-TEST-169, they appear WITHOUT their labels.
#:
#: EMPHASIS joined this set in PD-TEST-169. The engine's OWN P4-PROMPT contract
#: (dispatcher.py, the AF-C8 point) says the fields counting toward the on-slide
#: word total are "exactly: HEADLINE, SUBHEAD, and every line under SUPPORTING",
#: and that "SECTION, PURPOSE, ARCHETYPE, LADDER, EMPHASIS, PROOF USED, PEOPLE,
#: HOOK_REFRAIN, TEXT_ANCHOR, and HOOK VARIANT are internal production metadata
#: never rendered on the slide". The accent word already appears INSIDE the
#: headline, so the EMPHASIS entry is redundant for the renderer as well.
_FIELD_LINE_RE = re.compile(
    r"(?i)^\s*(?:HOOK_REFRAIN|LADDER|RESEARCH_USED|ARC|BEAT|TAG|TAGS"
    r"|SECTION|PURPOSE|ARCHETYPE|PROOF\s+USED|PEOPLE|TEXT_ANCHOR"
    r"|PRESENTER\s+NOTE|HOOK\s+VARIANT|EMPHASIS|MOVE\s+TAG)\s*:")

#: PD-TEST-169 -- the RENDERED fields carry a LABEL that must not be rendered.
#: slides.schema.json is explicit: copy[] is "the EXACT text that must appear
#: rendered on the slide, in reading order. Index 0 is treated as the HEADLINE"
#: and its own example is ["Northwind Co", "Three moves that doubled our
#: pipeline in 90 days"] -- BARE text, no `HEADLINE:` prefix. So the label is
#: stripped and the VALUE kept. A bare `SUPPORTING:` (label, no value) collapses
#: to nothing, which is right: its bullets are their own lines beneath it.
#:
#: This also puts copy[] into the shape its POSITIONAL consumers already assume:
#: build_deck._chk_copy_density reads fields[0] as the headline, [1] as the
#: subhead, [2] as the kicker and [3:] as bullets; slide_craft.AF-OBI-2
#: (check_obi_headline_words) grades copy[0] as the headline. With labels present
#: those reads were grading "HEADLINE: ..." and "EMPHASIS: ..." as slide text.
_LABEL_STRIP_RE = re.compile(r"(?i)^\s*(?:HEADLINE|SUBHEAD|SUPPORTING)\s*:\s*")

#: ANY HTML comment is engine bookkeeping, not pixels -- not just the ARC marker.
#: PD-TEST-158, review finding: the P4-COPY contract itself INSTRUCTS the writer
#: to "flag the gap in a comment in slides_copy.md" (slide-copywriter SOP 9.1), so
#: the live copy carries lines like
#:     <!-- QC-NOTE: AF-NO-BRANDED-METHOD -- intake.json has no named_methodology -->
#: `_ARC_MARKER_RE` matched ONLY `<!-- ARC: ... -->`, so those 12 comments survived
#: into copy[] and AF-P-VERBATIM then demanded them be BAKED INTO THE IMAGE PROMPT.
#: Measured on the live run: 12 QC-NOTE comments plus one `---` rule still reached
#: copy[] after the first version of this fix, and on slide 8 two of the six
#: remaining verbatim misses were these comments. Contract-sanctioned input, never
#: rendered text.
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)

#: A standalone horizontal rule is markdown structure, not slide copy. The P4-COPY
#: template wraps each slide block in `---` fences; `_LEADING_MARKUP_RE` never
#: matched one, so a stray rule reached copy[] (live: slide 3) and was demanded
#: verbatim like any other line.
_RULE_LINE_RE = re.compile(r"^\s*-{3,}\s*$")

#: Optional per-slide art-direction line inside a copy block. When the writer
#: supplies one it is the honest scene; otherwise the scene is derived.
_SCENE_LINE_RE = re.compile(
    r"(?i)^\s*(?:SCENE|VISUAL|IMAGE|SHOT|PHOTO)\s*:\s*(.+?)\s*$")

#: Leading markdown decoration stripped from a copy line (headings, bullets,
#: blockquote). Emphasis markers are deliberately NOT stripped: the renderer
#: bakes words VERBATIM and _chk_research_map matches anchor substrings, so the
#: producer must not rewrite the writer's text.
_LEADING_MARKUP_RE = re.compile(r"^\s*(?:#{1,6}\s*|[-*+]\s+|\d+[.)]\s+|>\s*)+")


@dataclass
class AssemblyResult:
    """Outcome of one assembly attempt.

    ``status`` is one of:
      ``ok``            -- a complete, valid deck was assembled (``slides`` set)
      ``up_to_date``    -- the existing slides.json already equals the assembly
      ``no_copy_source``-- slides_copy.md absent/unreadable/empty (nothing written)
      ``no_slide_blocks``-- slides_copy.md present but declares no SLIDE blocks
      ``count_mismatch``-- copy ordinals != arc ordinals (nothing written)
      ``no_copy_lines`` -- a slide block yielded no rendered copy (nothing written)
    ``reason`` is the honest, human-readable explanation the caller logs.
    ``written`` is True only when this call actually created/updated the file.
    """

    status: str
    reason: str = ""
    slides: List[Dict[str, Any]] = field(default_factory=list)
    written: bool = False
    path: Optional[Path] = None
    sources: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status in ("ok", "up_to_date")

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return (f"AssemblyResult(status={self.status!r}, written={self.written}, "
                f"n={len(self.slides)}, reason={self.reason!r})")


def phase_consumes_slides_json(consumes: Any) -> bool:
    """True when a phase's declared ``consumes`` names the renderer's index.

    Matches the exact relative path, a bare ``slides.json`` basename, and the
    ``{run_dir}``-templated spelling, so a manifest that names it any of the
    three ways still triggers the producer. Deliberately does NOT match
    ``arc_allocation.json``/``slides_copy.md``: those have their own producers
    and must not be mistaken for the renderer's index.
    """
    if not isinstance(consumes, (list, tuple, set)):
        return False
    for raw in consumes:
        if not isinstance(raw, str):
            continue
        norm = raw.strip().replace("{run_dir}/", "").lstrip("/").lower()
        if norm == SLIDES_JSON_REL or norm.endswith("/" + SLIDES_JSON_REL):
            return True
        if norm == "slides.json" or norm == "working/slides.json":
            return True
    return False


def _read_json(path: Path) -> Any:
    """Parse one JSON file, or None when absent/unreadable/unparseable."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def iter_slide_copy_blocks(text: str) -> List[Tuple[int, str]]:
    """``[(ordinal, body)]`` from slides_copy.md's ``SLIDE <n>`` blocks.

    Same delimiter and same interleaved split as ``dispatcher.
    _iter_slide_blocks`` (the canonical reader the P4-COPY reducer writes for),
    so the producer and the reducer can never disagree about where a block
    starts. Order is document order.
    """
    out: List[Tuple[int, str]] = []
    parts = _SLIDE_SPLIT_RE.split(text)
    i = 1
    while i < len(parts) - 1:
        try:
            n = int(parts[i])
        except ValueError:
            i += 2
            continue
        out.append((n, parts[i + 1]))
        i += 2
    return out


def _ordinal_of(slot: Dict[str, Any], position: int) -> int:
    """A slot's declared ordinal, or its 1-based position (PD-TEST-067 rule)."""
    for key in ARC_ORDINAL_KEYS:
        value = slot.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return int(value)
    return position


def _label_of(slot: Dict[str, Any]) -> Optional[str]:
    """A slot's arc-section label under any accepted spelling (PD-TEST-067)."""
    for key in ARC_LABEL_KEYS:
        value = slot.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def arc_slots(run_dir: Path) -> Optional[List[Dict[str, Any]]]:
    """The arc allocation's per-slide slots, under every accepted shape.

    Returns None when the artifact is absent/unreadable/declares no array --
    "not determinable", kept distinct from "determinable and empty" so the
    caller never invents a deck from a broken arc.
    """
    obj = _read_json(run_dir / ARC_ALLOCATION_REL)
    if obj is None:
        return None
    if isinstance(obj, list):
        raw: Any = obj
    elif isinstance(obj, dict):
        raw = None
        for key in ARC_SLIDE_LIST_KEYS:
            value = obj.get(key)
            if isinstance(value, list):
                raw = value
                break
        if raw is None:
            return None
    else:
        return None

    slots: List[Dict[str, Any]] = []
    for position, entry in enumerate(raw, start=1):
        slot = dict(entry) if isinstance(entry, dict) else {"slot": entry}
        slot["_ordinal"] = _ordinal_of(slot, position)
        slots.append(slot)
    return sorted(slots, key=lambda s: s["_ordinal"])


def style_directive(run_dir: Path) -> Optional[str]:
    """The owner-picked style directive, or None when no pick is resolvable.

    The choice file records WHICH variant was picked (``chosen_variant``); the
    directive text lives in the spec's ``variants[]``. Both must be present and
    agree before a directive is used, so an unknown/absent pick yields None
    rather than an invented style.
    """
    choice = _read_json(run_dir / STYLE_CHOICE_REL)
    if not isinstance(choice, dict):
        return None
    picked = str(choice.get("chosen_variant") or "").strip().upper()
    if not picked:
        return None
    spec = _read_json(run_dir / STYLE_SPEC_REL)
    if not isinstance(spec, dict):
        return None
    variants = spec.get("variants")
    if not isinstance(variants, list):
        return None
    for variant in variants:
        if not isinstance(variant, dict):
            continue
        if str(variant.get("id") or "").strip().upper() != picked:
            continue
        directive = str(variant.get("style_directive") or "").strip()
        if directive:
            return directive
    return None


def copy_lines(body: str) -> List[str]:
    """The RENDERED copy lines of one slide block, in reading order.

    Strips ONLY what is not pixels: ARC marker syntax and ALL other HTML
    comments (engine bookkeeping -- the P4-COPY contract tells the writer to
    leave QC notes in comments), standalone `---` rules (block structure),
    engine field lines (HOOK_REFRAIN/LADDER/RESEARCH_USED/SECTION/PURPOSE/
    PRESENTER NOTE/... -- the vocabulary the contract prescribes and the
    engine's own P4-PROMPT contract calls "internal production metadata never
    rendered on the slide"), and leading markdown decoration. Every other
    character is preserved, because ``_chk_research_map`` condition 3 matches
    research anchors as SUBSTRINGS of the render copy and ``build_deck`` bakes
    these words verbatim.
    """
    out: List[str] = []
    for raw_line in body.splitlines():
        line = _HTML_COMMENT_RE.sub("", _ARC_MARKER_RE.sub("", raw_line))
        if _RULE_LINE_RE.match(line):
            continue
        if _FIELD_LINE_RE.match(line):
            continue
        line = _LABEL_STRIP_RE.sub("", line)
        line = _LEADING_MARKUP_RE.sub("", line).strip()
        if line:
            out.append(line)
    return out


def scene_line(body: str) -> Optional[str]:
    """An explicit per-slide art-direction line from the block, if supplied."""
    for raw_line in body.splitlines():
        m = _SCENE_LINE_RE.match(_ARC_MARKER_RE.sub("", raw_line))
        if m:
            text = m.group(1).strip()
            if text:
                return text
    return None


def derive_scene(arc_label: Optional[str], headline: str,
                 directive: Optional[str], explicit: Optional[str]) -> str:
    """A deterministic, non-empty photographic direction for one slide.

    Precedence: the writer's own SCENE/VISUAL line, else a composition of the
    picked style directive (palette/lighting direction) with the deck's own arc
    band and this slide's own headline. Never a fabricated claim about the
    content: every element comes from the deck's own artifacts. This is the
    required-but-unrendered index field -- ``build_deck.load_rich_prompt``
    renders ``working/prompts/slide-NN.txt`` verbatim and never reads it.
    """
    if explicit:
        return explicit
    parts: List[str] = []
    if directive:
        parts.append(directive.rstrip("."))
    band = arc_label or "the deck"
    parts.append(f"photographic background for the {band} section")
    head = headline.strip().rstrip(".")
    if head:
        parts.append(f"framing \"{head}\"")
    parts.append("editorial photography, cinematic lighting, shallow depth of field")
    return ", ".join(parts)


def assemble(run_dir: Path) -> AssemblyResult:
    """Build the renderer's index from slides_copy.md + arc_allocation.json.

    Pure: reads only, writes nothing, never raises. Returns an AssemblyResult
    whose ``status``/``reason`` are the honest account of what was possible.
    """
    run_dir = Path(run_dir)
    copy_path = run_dir / SLIDES_COPY_REL
    if not copy_path.is_file():
        return AssemblyResult(
            "no_copy_source",
            f"{SLIDES_COPY_REL} is absent -- P4-COPY has not written the deck's "
            "copy yet, so no render index can be assembled (nothing written).")

    try:
        text = copy_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return AssemblyResult(
            "no_copy_source",
            f"{SLIDES_COPY_REL} is unreadable ({exc}) -- nothing written.")

    if not text.strip():
        return AssemblyResult(
            "no_copy_source",
            f"{SLIDES_COPY_REL} is empty -- refusing to write an empty render "
            "index (the renderer would render zero slides).")

    blocks = iter_slide_copy_blocks(text)
    if not blocks:
        return AssemblyResult(
            "no_slide_blocks",
            f"{SLIDES_COPY_REL} carries no `SLIDE <n>` block -- the P4-COPY "
            "output contract was not met, so there is no per-slide copy to "
            "assemble (nothing written).")

    slots = arc_slots(run_dir)
    label_by_ordinal: Dict[int, Optional[str]] = {}
    if slots is not None:
        for slot in slots:
            label_by_ordinal[slot["_ordinal"]] = _label_of(slot)

    copy_ordinals = [n for n, _b in blocks]
    if len(set(copy_ordinals)) != len(copy_ordinals):
        dupes = sorted({n for n in copy_ordinals if copy_ordinals.count(n) > 1})
        return AssemblyResult(
            "count_mismatch",
            f"{SLIDES_COPY_REL} repeats slide ordinal(s) {dupes} -- a deck "
            "cannot render one slide twice (nothing written).")

    if slots is not None:
        arc_ordinals = sorted(label_by_ordinal)
        if set(arc_ordinals) != set(copy_ordinals):
            missing_copy = sorted(set(arc_ordinals) - set(copy_ordinals))
            missing_arc = sorted(set(copy_ordinals) - set(arc_ordinals))
            detail = []
            if missing_copy:
                detail.append(f"arc declares {len(missing_copy)} slide(s) with no "
                              f"copy block: {missing_copy[:12]}"
                              + (" ..." if len(missing_copy) > 12 else ""))
            if missing_arc:
                detail.append(f"copy declares {len(missing_arc)} slide(s) the arc "
                              f"does not: {missing_arc[:12]}"
                              + (" ..." if len(missing_arc) > 12 else ""))
            return AssemblyResult(
                "count_mismatch",
                f"{SLIDES_COPY_REL} ({len(copy_ordinals)} slides) and "
                f"{ARC_ALLOCATION_REL} ({len(arc_ordinals)} slides) disagree; "
                + "; ".join(detail)
                + ". Neither side is silently preferred (nothing written).")

    directive = style_directive(run_dir)
    slides: List[Dict[str, Any]] = []
    for ordinal, body in sorted(blocks, key=lambda b: b[0]):
        lines = copy_lines(body)
        if not lines:
            return AssemblyResult(
                "no_copy_lines",
                f"slide {ordinal} in {SLIDES_COPY_REL} carries no rendered copy "
                "lines (only markers/metadata) -- refusing to emit a slide with "
                "an empty copy[] (nothing written).")
        label = label_by_ordinal.get(ordinal)
        slide: Dict[str, Any] = {
            OUT_ORDINAL_KEY: ordinal,
            OUT_ORDINAL_ALIAS: ordinal,
            "scene": derive_scene(label, lines[0], directive, scene_line(body)),
            "copy": lines,
        }
        if label:
            for key in (OUT_LABEL_KEY,) + OUT_LABEL_ALIASES:
                slide[key] = label
        slides.append(slide)

    sources = [SLIDES_COPY_REL]
    if slots is not None:
        sources.append(ARC_ALLOCATION_REL)
    if directive:
        sources.append(STYLE_SPEC_REL)
    return AssemblyResult(
        "ok",
        f"assembled {len(slides)} slide(s) from " + " + ".join(sources),
        slides=slides, sources=sources)


def _existing_is_current(path: Path, slides: List[Dict[str, Any]]) -> bool:
    """True when the on-disk index already equals this assembly byte-for-byte."""
    try:
        return json.loads(path.read_text(encoding="utf-8")) == slides
    except (OSError, ValueError, json.JSONDecodeError):
        return False


def ensure_slides_json(run_dir: Path, *, force: bool = False) -> AssemblyResult:
    """Materialise ``working/copy/slides.json`` from the run's own artifacts.

    Called by the engine just before a phase that declares the index in
    ``consumes`` runs. Writes ATOMICALLY, and only when a complete valid deck
    was assembled -- an incomplete assembly writes NOTHING and returns the
    reason, so a broken run fails loudly on the real cause instead of
    inheriting a silently-wrong index.

    Idempotent and monotonic: the file is rewritten only when the assembly
    differs from what is on disk (``force=True`` skips that check). Never
    raises -- a producer failure must not take the engine down, and the
    consumer's own verifier remains the authority on whether the deck is good.
    """
    result = assemble(run_dir)
    if not result.ok:
        return result

    path = Path(run_dir) / SLIDES_JSON_REL
    result.path = path
    if not force and path.is_file() and _existing_is_current(path, result.slides):
        result.status = "up_to_date"
        result.written = False
        return result

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(result.slides, indent=2, ensure_ascii=False)
                       + "\n", encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        return AssemblyResult(
            "no_copy_source",
            f"could not write {SLIDES_JSON_REL} ({exc}) -- nothing changed.",
            slides=result.slides, written=False, path=path)
    result.written = True
    return result


def main(argv: Optional[List[str]] = None) -> int:
    """Operator/engine entry point: ``python3 -m presentation_job.slides_assembly
    <run_dir> [--force]``. Exit 0 when the index exists afterwards, 2 otherwise,
    printing the honest reason either way."""
    args = list(sys.argv[1:] if argv is None else argv)
    force = "--force" in args
    args = [a for a in args if a != "--force"]
    if len(args) != 1:
        print("usage: python3 -m presentation_job.slides_assembly <run_dir> [--force]",
              file=sys.stderr)
        return 2
    result = ensure_slides_json(Path(args[0]), force=force)
    stream = sys.stdout if result.ok else sys.stderr
    print(f"slides.json: {result.status} ({result.reason})", file=stream)
    return 0 if result.ok else 2


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
