#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_sp_structure.py — fail-closed deterministic prover for the Signature
Presentation SACRED-structure contract.

WHAT IT DOES
------------
Loads the sacred structure ledger (../structure/sp_structure.json) and enforces
EVERY rule in it against a deck's copy ledger (the working/copy/sp_structure.json
emitted by the Signature Presentation Architect / Slide Copywriter). A single
violation is fail-closed: the prover prints the named AF-* auto-fail code(s) and
`sys.exit(2)` — nonzero. A violating deck is NOT run, NOT rendered, NOT updated.

Rules enforced (all read out of the ledger, never hard-coded floors):
  * >= 100 slides UNLESS a client-exact count is declared, then EXACTLY that count
    (logged as an override).                                    -> AF-SP-SLIDE-FLOOR
  * per-phase slide floors (avatar 11 / story 13 / teaching 36 / pitch 40),
    contiguous-from-slide-1, in order avatar->story->teaching->pitch.
                                          -> AF-SP-PHASE-RANGE / AF-SP-PHASE-ORDER
  * each phase carries its label slide (name + purpose).        -> AF-SP-PHASE-LABEL
  * a non-empty suggested_image on EVERY slide.               -> AF-SP-IMG-SUGGESTION
  * <= 2 CASE_STUDY-tagged slides (floor 1); a missing tags key is itself a fail
    so the cap cannot be dodged by not tagging.               -> AF-SP-CASESTUDY-CAP
  * 3-7 teaching steps.                                          -> AF-SP-TEACH-STEPS
  * one central hook + four DISTINCT section hooks.                    -> AF-SP-HOOK
  * N.E.E.I.T. + 4-Quadrant markers present in phases 1/2/4.       -> AF-SP-QUADRANT
  * Movement + Message + Methodology markers present.                  -> AF-SP-MMM

STRIPPED-LENGTH CLONE (cited)
-----------------------------
The "empty / whitespace-only never satisfies a content floor" teeth are cloned
directly from the deterministic stripped-length prover in build_deck.py:
  * build_deck.py:1082-1089  ->  `if not prompt.strip(): raise ...`
                                  `length = len(prompt.strip())`
  * build_deck.py:2937-2941  ->  `raw = p.read_text(...); stripped = raw.strip()`
                                  `length = len(stripped)`
That approach measures the NON-WHITESPACE length so a value padded with spaces /
newlines (or one that is whitespace-only) can never pass a required-content floor.
Here it backs `_stripped_len()`, used for suggested_image, central_hook, and each
section_hook. See `_stripped_len` below.

stdlib only. Exit 0 = pass, exit 2 = contract violation, exit 3 = usage / IO error.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple


# ---------------------------------------------------------------------------
# Stripped-length teeth — CLONE of build_deck.py:1082-1089 and 2937-2941.
# ---------------------------------------------------------------------------
def _stripped_len(value: Any) -> int:
    """Return the NON-WHITESPACE length of ``value``.

    CLONE of build_deck.py's deterministic stripped-length gate:
      build_deck.py:1082  `if not prompt.strip(): raise ...`
      build_deck.py:1089  `length = len(prompt.strip())`
      build_deck.py:2940  `stripped = raw.strip()`
      build_deck.py:2941  `length = len(stripped)`
    Measuring ``len(str(value).strip())`` means "   \\n   " (whitespace padding)
    or a whitespace-only string can NEVER satisfy a required-content floor — the
    exact trick that stops a padded file from posing as a real prompt there, reused
    here to stop a padded suggested_image / hook from posing as real copy.
    """
    return len(str(value).strip())


def _norm_tag(tag: Any) -> str:
    """Uppercase + drop every non-alphanumeric char, so 'N.E.E.I.T.' -> 'NEEIT',
    '4-Quadrant' -> '4QUADRANT', 'STEP-3' -> 'STEP3'. Deterministic marker match."""
    return re.sub(r"[^A-Z0-9]", "", str(tag).upper())


def _norm_line(text: Any) -> str:
    """Collapse whitespace runs, strip, lowercase — the canonical form used to test
    hook lines for verbatim equality (distinct-from-central / distinct-from-each)."""
    return re.sub(r"\s+", " ", str(text).strip()).lower()


# ---------------------------------------------------------------------------
# The prover core. verify() is pure: (structure, deck) -> (violations, notes).
# Nothing here exits; callers decide the exit code. This is what --self-test
# drives in-process against fixtures.
# ---------------------------------------------------------------------------
def verify(structure: Dict[str, Any], deck: Dict[str, Any]) -> Tuple[List[Tuple[str, str]], List[str]]:
    """Enforce the sacred structure contract on a deck copy ledger.

    Returns (violations, notes). ``violations`` is a list of (AF-code, message);
    empty means the deck clears every rule. ``notes`` carries logged facts such as
    the client-exact slide-floor override (surfaced on the process certificate).
    """
    violations: List[Tuple[str, str]] = []
    notes: List[str] = []

    def fail(code: str, msg: str) -> None:
        violations.append((code, msg))

    # --- pull the contract out of the ledger (never hard-code the floors) -----
    phases_spec = structure.get("phases") or []
    if not isinstance(phases_spec, list) or not phases_spec:
        fail("AF-SP-PHASE-ORDER", "structure ledger carries no 'phases' block")
        return violations, notes

    phase_by_id: Dict[str, Dict[str, Any]] = {}
    for p in phases_spec:
        if isinstance(p, dict) and p.get("id"):
            phase_by_id[str(p["id"])] = p
    valid_phases = set(phase_by_id)

    ordering = structure.get("phase_ordering") or {}
    required_order = [str(x) for x in ordering.get("must_be_in_order", []) if isinstance(x, str)]
    if not required_order:
        required_order = [str(p.get("id")) for p in phases_spec]

    slide_floor = structure.get("slide_floor") or {}
    default_min = int(slide_floor.get("default_minimum", 100))
    override_spec = slide_floor.get("client_exact_override") or {}
    override_flag = override_spec.get("flag", "client_overrode_slide_floor")
    override_count_field = override_spec.get("count_field", "client_exact_slide_count")

    case_spec = structure.get("case_studies") or {}
    case_cap = int(case_spec.get("cap", 2))
    case_floor = int(case_spec.get("floor", 1))
    case_tag = _norm_tag(case_spec.get("tag", "CASE_STUDY"))

    img_field = (structure.get("suggested_image") or {}).get("field", "suggested_image")

    hooks_spec = structure.get("hooks") or {}
    central_required = bool(hooks_spec.get("central_hook_required", True))
    section_count = int(hooks_spec.get("section_hooks_count", 4))
    section_distinct = bool(hooks_spec.get("section_hooks_distinct_from_central", True))

    nq_spec = structure.get("neeit_quadrant") or {}
    nq_required_phases = [str(x) for x in nq_spec.get("required_in_phases", []) if isinstance(x, str)]

    mmm_markers = [str(x) for x in (structure.get("movement_message_methodology") or {}).get(
        "required_markers", []) if isinstance(x, str)]

    teach_spec = phase_by_id.get("teaching", {}).get("teaching_steps") or {"min": 3, "max": 7}
    teach_min = int(teach_spec.get("min", 3))
    teach_max = int(teach_spec.get("max", 7))

    # --- slides array present? ------------------------------------------------
    slides = deck.get("slides")
    if not isinstance(slides, list) or not slides:
        fail("AF-SP-PHASE-ORDER", "deck ledger has no non-empty 'slides' array")
        return violations, notes

    # === CHECK A: per-slide shape + suggested_image + tags presence ===========
    numbers: List[int] = []
    for i, s in enumerate(slides):
        if not isinstance(s, dict):
            fail("AF-SP-PHASE-ORDER", f"slide entry #{i} is not an object")
            continue
        num = s.get("slide")
        label = num if isinstance(num, int) else f"#{i}"
        if isinstance(num, int):
            numbers.append(num)
        else:
            fail("AF-SP-PHASE-ORDER", f"slide entry #{i}: missing/invalid integer 'slide'")
        if s.get("phase") not in valid_phases:
            fail("AF-SP-PHASE-ORDER",
                 f"slide {label}: invalid/missing 'phase' {s.get('phase')!r} "
                 f"(must be one of {sorted(valid_phases)})")
        # suggested_image — stripped-length teeth (clone).
        if _stripped_len(s.get(img_field, "")) == 0:
            fail("AF-SP-IMG-SUGGESTION",
                 f"slide {label}: empty / whitespace-only '{img_field}' "
                 f"(every slide must carry a non-empty suggested_image)")
        # tags — a MISSING tags key is itself a fail (cannot dodge the cap).
        if not isinstance(s.get("tags"), list):
            fail("AF-SP-CASESTUDY-CAP",
                 f"slide {label}: missing 'tags' array — a missing tags section is a "
                 f"FAIL so the case-study cap cannot be dodged by not tagging")

    # === CHECK B: slide numbers contiguous 1..N, unique =======================
    n_total = len(slides)
    if len(numbers) == n_total:
        if sorted(numbers) != list(range(1, n_total + 1)):
            fail("AF-SP-PHASE-ORDER",
                 f"slide numbers are not contiguous 1..{n_total} unique "
                 f"(got sorted {sorted(numbers)[:5]}... )")

    # === CHECK C: phase contiguity + order (avatar->story->teaching->pitch) ====
    ordered = [s for s in slides
               if isinstance(s, dict) and isinstance(s.get("slide"), int)
               and s.get("phase") in valid_phases]
    ordered.sort(key=lambda s: s["slide"])
    phase_seq = [s["phase"] for s in ordered]
    if phase_seq:
        runs = [p for j, p in enumerate(phase_seq) if j == 0 or p != phase_seq[j - 1]]
        if runs != required_order:
            fail("AF-SP-PHASE-ORDER",
                 f"phase sequence {runs} != required contiguous order {required_order} "
                 f"(phases must run in order, each contiguous, starting at slide 1)")

    # === CHECK D: per-phase min_slides floor ==================================
    counts = Counter(s.get("phase") for s in slides if isinstance(s, dict))
    for pid, p in phase_by_id.items():
        floor = int(p.get("min_slides", 0))
        have = int(counts.get(pid, 0))
        if have < floor:
            fail("AF-SP-PHASE-RANGE",
                 f"phase '{pid}' has {have} slides, under its floor of {floor}")

    # === CHECK E: each phase carries its label slide ==========================
    for pid, p in phase_by_id.items():
        if not p.get("requires_label_slide", True):
            continue
        has_label = any(isinstance(s, dict) and s.get("phase") == pid and bool(s.get("label_slide"))
                        for s in slides)
        if not has_label:
            fail("AF-SP-PHASE-LABEL",
                 f"phase '{pid}' has no label_slide carrying its name + purpose (Directive 10)")

    # === CHECK F: slide floor / client-exact override =========================
    override = bool(deck.get(override_flag))
    if override:
        exact = deck.get(override_count_field)
        if not isinstance(exact, int) or exact <= 0:
            fail("AF-SP-SLIDE-FLOOR",
                 f"'{override_flag}' is true but '{override_count_field}' is missing/invalid "
                 f"(must be a positive integer)")
        elif n_total != exact:
            fail("AF-SP-SLIDE-FLOOR",
                 f"client-exact override declares EXACTLY {exact} slides but the deck has "
                 f"{n_total} (client-exact count is honored exactly, never floored)")
        else:
            notes.append(
                f"OVERRIDE: {override_flag}=true, {override_count_field}={exact}; the >= "
                f"{default_min} floor is waived, exact count honored, logged on the certificate")
    else:
        if n_total < default_min:
            fail("AF-SP-SLIDE-FLOOR",
                 f"deck has {n_total} slides, under the {default_min}-slide floor and no "
                 f"logged client-exact override")

    # === CHECK G: case-study band [floor, cap] ================================
    case_hits = sum(
        1 for s in slides
        if isinstance(s, dict) and isinstance(s.get("tags"), list)
        and any(_norm_tag(t) == case_tag for t in s["tags"])
    )
    if case_hits > case_cap:
        fail("AF-SP-CASESTUDY-CAP",
             f"{case_hits} CASE_STUDY-tagged slides exceed the cap of {case_cap} (Directive 12)")
    if case_hits < case_floor:
        fail("AF-SP-CASESTUDY-CAP",
             f"{case_hits} CASE_STUDY-tagged slides, under the proof-battery floor of {case_floor}")

    # === CHECK H: teaching steps 3-7 =========================================
    steps_field = deck.get("teaching_steps")
    if isinstance(steps_field, int):
        step_count = steps_field
    elif isinstance(steps_field, list):
        step_count = len(steps_field)
    else:
        step_nums = set()
        for s in slides:
            if isinstance(s, dict) and s.get("phase") == "teaching" and isinstance(s.get("tags"), list):
                for t in s["tags"]:
                    m = re.match(r"^(?:TEACHING)?STEP(\d+)$", _norm_tag(t))
                    if m:
                        step_nums.add(int(m.group(1)))
        step_count = len(step_nums)
    if not (teach_min <= step_count <= teach_max):
        fail("AF-SP-TEACH-STEPS",
             f"teaching steps = {step_count}, outside the required [{teach_min}, {teach_max}]")

    # === CHECK I: hooks (central + N distinct section hooks) ===================
    hp = deck.get("hook_package") or {}
    central = hp.get("central_hook")
    sections = hp.get("section_hooks")
    if central_required and (not isinstance(central, str) or _stripped_len(central) == 0):
        fail("AF-SP-HOOK", "hook_package is missing a non-empty 'central_hook'")
    good_sections = [x for x in sections if isinstance(x, str) and _stripped_len(x) > 0] \
        if isinstance(sections, list) else []
    if len(good_sections) != section_count:
        fail("AF-SP-HOOK",
             f"hook_package must carry EXACTLY {section_count} non-empty section_hooks "
             f"(one per phase); found {len(good_sections)}")
    else:
        normed = [_norm_line(x) for x in good_sections]
        if section_distinct and isinstance(central, str) and _norm_line(central) in normed:
            fail("AF-SP-HOOK",
                 "a section_hook is verbatim-equal to the central_hook (section hooks must be "
                 "DISTINCT lines so they never trip the verbatim-hook-elsewhere battery)")
        if len(set(normed)) != len(normed):
            fail("AF-SP-HOOK", "section_hooks are not all distinct (need 4 distinct lines, one per phase)")

    # === CHECK J: N.E.E.I.T. + 4-Quadrant markers in phases 1/2/4 =============
    for pid in nq_required_phases:
        tagset = set()
        for s in slides:
            if isinstance(s, dict) and s.get("phase") == pid and isinstance(s.get("tags"), list):
                for t in s["tags"]:
                    tagset.add(_norm_tag(t))
        if "NEEIT" not in tagset:
            fail("AF-SP-QUADRANT", f"phase '{pid}' is missing the N.E.E.I.T. marker")
        if not tagset.intersection({"QUADRANT", "4QUADRANT", "FOURQUADRANT"}):
            fail("AF-SP-QUADRANT", f"phase '{pid}' is missing the 4-Quadrant marker")

    # === CHECK K: Movement + Message + Methodology markers =====================
    all_tags = set()
    for s in slides:
        if isinstance(s, dict) and isinstance(s.get("tags"), list):
            for t in s["tags"]:
                all_tags.add(_norm_tag(t))
    for marker in mmm_markers:
        if _norm_tag(marker) not in all_tags:
            fail("AF-SP-MMM",
                 f"missing '{marker}' marker (Movement + Message + Methodology = Manifestation)")

    return violations, notes


# ---------------------------------------------------------------------------
# IO helpers
# ---------------------------------------------------------------------------
def _default_structure_path() -> Path:
    return Path(__file__).resolve().parent.parent / "structure" / "sp_structure.json"


def _load_json(path: str) -> Any:
    if path == "-":
        return json.loads(sys.stdin.read())
    return json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))


def _load_structure(path_arg: str | None) -> Dict[str, Any]:
    p = Path(path_arg) if path_arg else _default_structure_path()
    return json.loads(p.read_text(encoding="utf-8", errors="replace"))


def _report(violations: List[Tuple[str, str]], notes: List[str]) -> None:
    for note in notes:
        print(f"NOTE: {note}")
    if not violations:
        print("PASS: deck clears every rule in the SACRED signature-presentation structure contract.")
        return
    print(f"FAIL: {len(violations)} structure violation(s) — deck is NOT run, NOT rendered, NOT updated.")
    for code, msg in violations:
        print(f"  VIOLATION [{code}] {msg}")


# ---------------------------------------------------------------------------
# Self-test fixtures — a VALID deck and one single-defect mutation per rule.
# ---------------------------------------------------------------------------
def _valid_fixture() -> Dict[str, Any]:
    """A minimal but fully-compliant 100-slide deck ledger (avatar 1-11, story
    12-24, teaching 25-60, pitch 61-100)."""
    ranges = [("avatar", 1, 11), ("story", 12, 24), ("teaching", 25, 60), ("pitch", 61, 100)]
    slides: List[Dict[str, Any]] = []
    for pid, lo, hi in ranges:
        for n in range(lo, hi + 1):
            slides.append({
                "slide": n,
                "phase": pid,
                "label_slide": False,
                "suggested_image": f"seed image concept for slide {n}",
                "tags": [],
            })
    by_num = {s["slide"]: s for s in slides}
    # phase label slides (name + purpose)
    for n in (1, 12, 25, 61):
        by_num[n]["label_slide"] = True
    # N.E.E.I.T. + 4-Quadrant markers in phases 1/2/4
    for n in (1, 12, 61):
        by_num[n]["tags"] += ["N.E.E.I.T.", "4-Quadrant"]
    # Movement + Message + Methodology markers
    by_num[1]["tags"].append("MOVEMENT")
    by_num[12]["tags"].append("MESSAGE")
    by_num[25]["tags"].append("METHODOLOGY")
    # 5 teaching steps across the teaching phase
    for i, n in enumerate(range(25, 30), start=1):
        by_num[n]["tags"].append(f"STEP-{i}")
    # one case study (band floor 1, cap 2)
    by_num[90]["tags"].append("CASE_STUDY")
    return {
        "deck_type": "signature_presentation",
        "client_overrode_slide_floor": False,
        "slides": slides,
        "hook_package": {
            "central_hook": "You were built for more than this.",
            "section_hooks": [
                "See yourself in their struggle.",
                "My lowest day became the map.",
                "Here is the method, one step at a time.",
                "The door is open — walk through it.",
            ],
        },
    }


def _mut(fn):
    """Return a fresh valid fixture mutated by fn."""
    d = _valid_fixture()
    fn(d)
    return d


def _by_num(deck: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    return {s["slide"]: s for s in deck["slides"]}


def _violation_cases() -> List[Tuple[str, str, Any]]:
    """(name, expected_af_code, deck_builder). Each builder returns an otherwise-valid
    deck with exactly one intentional defect (co-tripping is tolerated; the assertion
    only requires the EXPECTED code to be present)."""
    def slide_floor_override_mismatch(d):
        d["client_overrode_slide_floor"] = True
        d["client_exact_slide_count"] = 120  # deck has 100 -> mismatch
    def slide_floor_under(d):
        d["slides"] = [s for s in d["slides"] if s["slide"] != 100]
    def phase_range(d):
        _by_num(d)[24]["phase"] = "teaching"  # story drops to 12 (< 13)
    def phase_order(d):
        _by_num(d)[50]["phase"] = "avatar"    # avatar re-appears mid-teaching
    def phase_label(d):
        _by_num(d)[12]["label_slide"] = False  # story loses its only label
    def img_blank(d):
        _by_num(d)[50]["suggested_image"] = "   \n  "  # whitespace-only (stripped-len teeth)
    def case_over(d):
        for n in (90, 91, 92):
            _by_num(d)[n]["tags"].append("CASE_STUDY")  # 3 > cap 2
    def tags_missing(d):
        del _by_num(d)[50]["tags"]
    def teach_over(d):
        for i, n in enumerate(range(30, 33), start=6):
            _by_num(d)[n]["tags"].append(f"STEP-{i}")  # -> 8 distinct steps
    def teach_under_explicit(d):
        d["teaching_steps"] = 2  # explicit field path, 2 < 3
    def hook_no_central(d):
        d["hook_package"]["central_hook"] = "   "
    def hook_dup_central(d):
        d["hook_package"]["section_hooks"][0] = d["hook_package"]["central_hook"]
    def hook_wrong_count(d):
        d["hook_package"]["section_hooks"] = d["hook_package"]["section_hooks"][:3]
    def neeit_missing(d):
        _by_num(d)[12]["tags"] = [t for t in _by_num(d)[12]["tags"] if t != "N.E.E.I.T."]
    def mmm_missing(d):
        _by_num(d)[25]["tags"] = [t for t in _by_num(d)[25]["tags"] if t != "METHODOLOGY"]

    return [
        ("slide_floor_override_mismatch", "AF-SP-SLIDE-FLOOR", lambda: _mut(slide_floor_override_mismatch)),
        ("slide_floor_under_100",         "AF-SP-SLIDE-FLOOR", lambda: _mut(slide_floor_under)),
        ("phase_range_below_floor",       "AF-SP-PHASE-RANGE", lambda: _mut(phase_range)),
        ("phase_out_of_order",            "AF-SP-PHASE-ORDER", lambda: _mut(phase_order)),
        ("phase_missing_label",           "AF-SP-PHASE-LABEL", lambda: _mut(phase_label)),
        ("suggested_image_whitespace",    "AF-SP-IMG-SUGGESTION", lambda: _mut(img_blank)),
        ("case_study_over_cap",           "AF-SP-CASESTUDY-CAP", lambda: _mut(case_over)),
        ("tags_key_missing",              "AF-SP-CASESTUDY-CAP", lambda: _mut(tags_missing)),
        ("teaching_steps_over_7",         "AF-SP-TEACH-STEPS", lambda: _mut(teach_over)),
        ("teaching_steps_under_3",        "AF-SP-TEACH-STEPS", lambda: _mut(teach_under_explicit)),
        ("hook_missing_central",          "AF-SP-HOOK", lambda: _mut(hook_no_central)),
        ("hook_section_dup_central",      "AF-SP-HOOK", lambda: _mut(hook_dup_central)),
        ("hook_wrong_section_count",      "AF-SP-HOOK", lambda: _mut(hook_wrong_count)),
        ("neeit_marker_missing",          "AF-SP-QUADRANT", lambda: _mut(neeit_missing)),
        ("mmm_marker_missing",            "AF-SP-MMM", lambda: _mut(mmm_missing)),
    ]


def run_self_test(structure: Dict[str, Any]) -> int:
    """(a) assert the VALID fixture PASSES (no violations), and (b) assert each
    single-defect fixture produces a NONZERO result carrying its expected AF code.
    Returns 0 only when every assertion holds; nonzero (1) signals a broken prover."""
    ok = True

    # (a) valid fixture must clear every rule.
    v, notes = verify(structure, _valid_fixture())
    if v:
        ok = False
        print(f"SELF-TEST FAIL: valid fixture produced {len(v)} violation(s): {v}")
    else:
        print("SELF-TEST ok: valid fixture PASSES (0 violations).")

    # (b) every violation fixture must fail with the expected code.
    for name, expected, build in _violation_cases():
        vio, _ = verify(structure, build())
        codes = {c for c, _ in vio}
        if not vio:
            ok = False
            print(f"SELF-TEST FAIL: '{name}' produced NO violations (expected {expected}).")
        elif expected not in codes:
            ok = False
            print(f"SELF-TEST FAIL: '{name}' -> {sorted(codes)} (expected {expected}).")
        else:
            print(f"SELF-TEST ok: '{name}' -> nonzero, carries {expected}.")

    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def run_demo_violation(structure: Dict[str, Any]) -> int:
    """Run the REAL verify() against a deliberately-broken deck and exit nonzero.
    Used to demonstrate the fail-closed exit path end-to-end without writing any
    external fixture file."""
    d = _valid_fixture()
    _by_num(d)[1]["suggested_image"] = "   "  # whitespace-only -> AF-SP-IMG-SUGGESTION
    violations, notes = verify(structure, d)
    _report(violations, notes)
    if not violations:
        print("DEMO ERROR: expected a violation but got none (prover bug).")
        return 4
    return 2


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(
        description="Fail-closed deterministic prover for the SACRED signature-presentation "
                    "structure contract (sp_structure.json). Exit 0 = pass, 2 = violation, 3 = usage/IO.")
    ap.add_argument("--deck", help="path to the deck copy-ledger JSON to enforce ('-' reads stdin)")
    ap.add_argument("--structure", help="path to sp_structure.json (defaults to ../structure/sp_structure.json)")
    ap.add_argument("--self-test", action="store_true",
                    help="construct a valid fixture (must PASS) and each violation fixture (must FAIL)")
    ap.add_argument("--demo-violation", action="store_true",
                    help="run verify() on a deliberately-broken deck and exit nonzero (fail-closed demo)")
    args = ap.parse_args(argv)

    if args.self_test:
        try:
            structure = _load_structure(args.structure)
        except Exception as exc:  # noqa: BLE001
            print(f"USAGE/IO ERROR: cannot load structure ledger: {exc}")
            return 3
        return run_self_test(structure)

    if args.demo_violation:
        try:
            structure = _load_structure(args.structure)
        except Exception as exc:  # noqa: BLE001
            print(f"USAGE/IO ERROR: cannot load structure ledger: {exc}")
            return 3
        return run_demo_violation(structure)

    if not args.deck:
        print("USAGE ERROR: pass --deck <ledger.json> (or --self-test / --demo-violation).")
        return 3

    try:
        structure = _load_structure(args.structure)
    except Exception as exc:  # noqa: BLE001
        print(f"USAGE/IO ERROR: cannot load structure ledger: {exc}")
        return 3
    try:
        deck = _load_json(args.deck)
    except Exception as exc:  # noqa: BLE001
        print(f"USAGE/IO ERROR: cannot load deck ledger {args.deck!r}: {exc}")
        return 3
    if not isinstance(deck, dict):
        print("USAGE/IO ERROR: deck ledger must be a JSON object.")
        return 3

    violations, notes = verify(structure, deck)
    _report(violations, notes)
    return 0 if not violations else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
