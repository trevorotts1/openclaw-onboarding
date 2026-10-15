"""story_arc.py: twelve-beat arc validator (directive 11.1). stdlib only.

Contract: exactly the twelve canonical beat IDs, each once, in canonical
order (subsequence check so a single missing beat still fails on identity,
not on order noise), and the product reveal never lands before stage 8 —
beat 8 is Gift / Mechanism / Product Introduction.

QC fixtures: valid, one file per beat missing, duplicate, reordered,
early reveal.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

SCHEMA_VERSION = "blackceo.story-arc/v1"
TOOL_VERSION = "0.1.0"

# Directive 11.1 (L1138-1149), canonical order is the contract.
BEATS = (
    "ordinary_world",        # 1  Ordinary World
    "humiliation",           # 2  Humiliation / Emotional Wound
    "wound_deepens",         # 3  Wound Deepens
    "frozen",                # 4  Frozen
    "seeing_it_too",         # 5  Seeing It Too
    "failed_solutions",      # 6  Failed Solutions
    "mentor",                # 7  Mentor / Trusted Guide
    "product_intro",         # 8  Gift / Mechanism / Product Introduction
    "doubt",                 # 9  Doubt
    "climb",                 # 10 Climb / Transformation
    "vindication",           # 11 Vindication
    "return_cta",            # 12 Return / Pitch / CTA
)

PRODUCT_REVEAL_MIN = 8   # reveal stage >= 8: product intro is beat 8
PRODUCT_REVEAL_MAX = len(BEATS)
STORY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
EXIT = {"ok": 0, "rejected": 4, "error": 1}
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def _res(outcome, reason_code, errors, story, ids, reveal):
    return {
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "outcome": outcome,
        "reason_code": reason_code,
        "errors": errors,
        "beat_count": len(ids),
        "beats": ids,
        "product_reveal": reveal,
        "next_action": (
            "Proceed to storyboard." if outcome == "ok"
            else "Fix the listed beat errors and re-run validate_story."
        ),
        "story_id": story.get("story_id") if isinstance(story, dict) else None,
    }


def validate_story(story, purpose=None):
    """Validate a twelve-beat story record.

    Story record: {"story_id": ..., "beats": [beat_id x12], "product_reveal": int}
    Returns outcome/reason_code/errors/beat_count/beats/product_reveal/next_action.

    ``purpose`` (optional, a method run's SPEC B1 purpose) adds two rules and
    nothing else; with no purpose, or any value outside ``METHOD_PURPOSES``,
    the record is judged exactly as before:

    * ``lesson`` -- beat 8 may be ``lesson_intro`` instead of ``product_intro``
      (accepted in place of it, at beat 8, never elsewhere).
    * ``testimonial`` -- every product beat present carries a non-blank
      ``claim_source`` in the record's ``story_beats`` rows; a claim with no
      source is refused as CLAIM_UNSOURCED.
    """
    if not isinstance(story, dict):
        return _res("error", "story-not-an-object",
                    [{"error": "story-not-an-object", "detail": "story must be a JSON object"}],
                    {}, [], None)

    errors = []
    beats = story.get("beats")
    if not isinstance(beats, list) or not beats:
        errors.append({"error": "beats-missing",
                       "detail": "beats must be a non-empty list"})
        return _res("rejected", "beats-missing", errors, story, [], None)

    ids = []
    for i, b in enumerate(beats):
        if not isinstance(b, str) or not b.strip():
            errors.append({"error": "beat-not-a-string",
                           "detail": "index %d: %r" % (i, b)})
        else:
            ids.append(b.strip())

    # A method run passes its purpose. A lesson may name beat 8
    # ``lesson_intro``; ``check`` is that purpose's canonical view of the ids
    # (a lesson_intro misplaced off beat 8 lands on beat-order/beat-duplicate),
    # while ``ids`` -- what the result reports -- never changes.
    purp = str(purpose or "").strip().lower()
    if purp not in METHOD_PURPOSES:
        purp = ""              # no purpose, or none of the five: judged as before
    check = ([b if b != LESSON_INTRO else BEATS[PRODUCT_REVEAL_MIN - 1] for b in ids]
             if purp == "lesson" else list(ids))

    known = set(BEATS)
    unknown = sorted({b for b in check if b not in known})
    if unknown:
        errors.append({"error": "beat-unknown", "detail": unknown})

    seen, dups = set(), []
    for b in check:
        if b in seen and b not in dups:
            dups.append(b)
        seen.add(b)
    if dups:
        errors.append({"error": "beat-duplicate", "detail": sorted(dups)})

    missing = [b for b in BEATS if b not in seen]
    if missing:
        errors.append({"error": "beat-missing", "detail": missing})

    if len(check) != len(BEATS):
        errors.append({"error": "beat-count",
                       "detail": "got %d, want %d" % (len(check), len(BEATS))})

    if not unknown:  # order: every known beat must advance in canonical order
        order = [BEATS.index(b) for b in check if b in known]
        if any(order[i] > order[i + 1] for i in range(len(order) - 1)):
            errors.append({"error": "beat-order", "detail": list(ids)})

    # Testimonial: every product beat carries the client's own words behind it.
    if purp == "testimonial":
        rows = story.get("story_beats")
        by_beat = {str(r.get("story_beat_id") or r.get("beat") or ""): r
                   for r in (rows if isinstance(rows, list) else [])
                   if isinstance(r, dict)}
        for beat in PRODUCT_BEATS:
            if beat in seen and _blank((by_beat.get(beat) or {}).get("claim_source")):
                errors.append({
                    "error": "claim-source-missing",
                    "detail": "CLAIM_UNSOURCED: testimonial beat %r carries no claim_source "
                              "traced to a phrase in the client's own words" % beat})

    reveal = story.get("product_reveal")
    if "product_reveal" not in story:
        errors.append({"error": "reveal-missing",
                       "detail": "product_reveal (beat index of product first appearance) is required"})
    elif not isinstance(reveal, int) or isinstance(reveal, bool):
        errors.append({"error": "reveal-invalid",
                       "detail": "product_reveal must be an int, got %r" % (reveal,)})
    elif reveal < PRODUCT_REVEAL_MIN:
        errors.append({"error": "reveal-early",
                       "detail": "product_reveal=%d, must be >= %d (product intro is beat 8)"
                                 % (reveal, PRODUCT_REVEAL_MIN)})
    elif reveal > PRODUCT_REVEAL_MAX:
        errors.append({"error": "reveal-out-of-range",
                       "detail": "product_reveal=%d, must be <= %d" % (reveal, PRODUCT_REVEAL_MAX)})

    if "story_id" in story and not (
            isinstance(story["story_id"], str) and STORY_ID_RE.match(story["story_id"])):
        errors.append({"error": "story-id-invalid", "detail": repr(story.get("story_id"))})

    # WW-28: the causal craft gate, BEFORE budgeting. It runs on a record
    # that declares causal content: the chain, the fiction/testimonial split,
    # the reconstruction from the exact lyrics, the hook line and the closing
    # call are WW-28's pre-generation acceptance rules -- never a sixth audio
    # gate (D1-D5 stay the only delivered-audio gates).
    if declares_causal(story):
        for _e in check_causal_story(story)["errors"]:
            if _e not in errors:
                errors.append(_e)

    if errors:
        return _res("rejected", errors[0]["error"], errors, story, ids, reveal)
    return _res("ok", "story-valid", [], story, ids, reveal)


def load_fixture(name):
    with open(FIXTURE_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def selftest():
    """Run every QC fixture: valid passes, each defect rejects with its code."""
    checks, fails = [], []

    def expect(name, want_outcome, want_reason):
        try:
            story = load_fixture(name)
        except (OSError, json.JSONDecodeError) as e:
            checks.append(name)
            fails.append("%s: unreadable (%s)" % (name, e))
            return
        r = validate_story(story)
        ok = r["outcome"] == want_outcome and (
            want_reason is None or r["reason_code"] == want_reason)
        checks.append(name)
        if not ok:
            fails.append("%s: outcome=%s reason=%s, want %s/%s"
                         % (name, r["outcome"], r["reason_code"],
                            want_outcome, want_reason))

    expect("valid.json", "ok", "story-valid")
    for beat in BEATS:                       # each-beat-missing cases
        expect("missing-%s.json" % beat, "rejected", "beat-missing")
    expect("duplicate.json", "rejected", "beat-duplicate")
    expect("reordered.json", "rejected", "beat-order")
    expect("reveal-early.json", "rejected", "reveal-early")
    expect("reveal-missing.json", "rejected", "reveal-missing")

    for bad in (None, [], "x", {"beats": [], "product_reveal": 8},
                {"beats": list(BEATS), "product_reveal": 13},
                {"beats": list(BEATS), "product_reveal": "8"}):
        r = validate_story(bad)
        checks.append("inline:%r" % (bad if not isinstance(bad, list) else bad[:2],))
        if r["outcome"] == "ok":
            fails.append("inline %r accepted, want reject" % (bad,))

    # canonical identity: BEATS order matches directive 11.1 word for word
    want = ["ordinary_world", "humiliation", "wound_deepens", "frozen",
            "seeing_it_too", "failed_solutions", "mentor", "product_intro",
            "doubt", "climb", "vindication", "return_cta"]
    checks.append("beats-identity")
    if list(BEATS) != want or len(BEATS) != 12:
        fails.append("BEATS drifted from directive 11.1: %r" % (list(BEATS),))

    print("story_arc selftest: %s (%d checks, %d failures)"
          % ("PASS" if not fails else "FAIL", len(checks), len(fails)))
    for f in fails:
        print(" -", f)
    return 0 if not fails else 1


# =====================================================================
# WW-03 / WW-15: the performed-beat manifest, the creative fingerprint
# and the story gate that refuses a paper arc.
#
# WW-03 (WW-PREVENT-RECURRENCE-SPEC section 3, Unit U1): a performed-beat
# manifest is generated from ONE source for all twelve canonical beats -- the
# approved line identifiers and text that must be heard IN ORDER, with the
# delivery, the hook placement and the pace cues. A creative fingerprint over
# lines, delivery, beat map, hook and pace is stored with the take and compared
# against the fingerprinted revision actually submitted, so a take whose
# fingerprint does not match the approved sheet is refused, a metadata-only
# twelve-identifier list does not pass, and the shipped take carrying only one
# of the seven approved devices is refused.
#
# WW-15's binding half: the chosen master revision is bound by that fingerprint
# and an existing take is NEVER retroactively bound to an edited sheet. The
# ARRANGEMENT CHOICE ITSELF is NOT made here and must not be read as made: it
# stays with the owner.
# =====================================================================

MANIFEST_SCHEMA = "blackceo.performed-beat-manifest/v1"
FINGERPRINT_SCHEMA = "blackceo.creative-fingerprint/v1"
FINGERPRINT_COMPONENTS = ("lines", "delivery", "beat_map", "hook", "pace")

#: The SOURCE METHOD is the fifteen-beat Resilia arc (SOP
#: `SOP--drama-song-ad-pipeline.md` DS-4 step 1: "cold-open teaser through direct
#: pitch"). Its stage names are authored per campaign -- only three are written
#: in the tree today (named below) -- so this module preserves the METHOD and its
#: FIFTEEN count, and maps each CANONICAL beat to a source-method position and to
#: one of the eight coarse timing stages BY NAME. The two counts are never
#: relabelled as one another (WW-03: "never by relabelling one count as another").
SOURCE_METHOD_NAME = "fifteen-beat Resilia arc"
SOURCE_METHOD_STAGE_COUNT = 15
SOURCE_METHOD_NAMED_EXAMPLES = ("cold_open_teaser", "converts", "direct_pitch")

#: The EIGHT coarse timing stages (FU-U16 doctrine; the same eight
#: length_formula.STORY_ARC_U16 carries). Kept as literal names so this module
#: stays stdlib-only and free of a length_formula import.
TIMING_STAGES = ("hook", "the_world", "villain_arrives", "pain_deepens",
                 "lowest_point", "the_turn", "the_rise", "call_to_action")

#: Canonical beat -> coarse timing stage, by NAME (monotonic in canonical order).
BEAT_TO_TIMING = {
    "ordinary_world": "hook",
    "humiliation": "the_world",
    "wound_deepens": "villain_arrives",
    "frozen": "pain_deepens",
    "seeing_it_too": "lowest_point",
    "failed_solutions": "the_turn",
    "mentor": "the_turn",
    "product_intro": "the_turn",
    "doubt": "the_rise",
    "climb": "the_rise",
    "vindication": "the_rise",
    "return_cta": "call_to_action",
}

# =====================================================================
# Drama-to-Demand METHOD anchors (conflict C6/C10; METHOD-INTEGRATION F6).
# Inert until wired: they are read on a method run, the run that carries
# ``control/method.json``; a run without one is judged exactly as before.
# =====================================================================

#: Canonical beat -> the music cue that anchors it on a method run, beside
#: ``BEAT_TO_TIMING`` (which stays the non-method mapping, unchanged). The ERM
#: apex is not a beat of its own -- it lands at the END of ``wound_deepens``
#: (``METHOD_ERM_APEX``), where the first sung line enters -- so no beat maps
#: to ``ERM_DROP``.
METHOD_ANCHORS = {
    "ordinary_world": "BASELINE",
    "humiliation": "PAIN_BUILD",
    "wound_deepens": "PAIN_BUILD",
    "frozen": "PAIN_DEEPEN",
    "seeing_it_too": "PAIN_DEEPEN",
    "failed_solutions": "PAIN_DEEPEN",
    "mentor": "HERO_SHIFT",
    "product_intro": "HERO_SHIFT",
    "doubt": "BREAKTHROUGH",
    "climb": "BREAKTHROUGH",
    "vindication": "SOLUTION_HOOK",
    "return_cta": "COMMERCIAL_CONTINUATION",
}

#: The ERM apex anchor: the end of ``wound_deepens``, where singing begins.
METHOD_ERM_APEX = {"beat": "wound_deepens", "position": "end"}

#: Method purposes (SPEC B1). ``validate_story`` applies its two method rules
#: only to one of these, so a caller that passes no purpose behaves as before.
METHOD_PURPOSES = ("campaign", "testimonial", "lesson", "paid_ad", "short_post")

#: A lesson names the point instead of a product at beat 8. Accepted IN PLACE
#: of ``product_intro``; no existing beat is renamed and ``BEATS`` is untouched.
LESSON_INTRO = "lesson_intro"

#: The product beats: the ones a testimonial claim must be sourced from.
PRODUCT_BEATS = ("product_intro", LESSON_INTRO)

#: Hook-from for a method run, Trevor 2026-10-13: the hook exists to make
#: viewers remember the solution, so the build toward it may start once the
#: solution has at least been introduced (Hero Shift = ``the_turn``), never
#: before it. The 60 s golden sheet's ``lowest_point`` hook moves to
#: ``the_turn`` too -- one value at every length, never ``lowest_point``.
METHOD_TRUE_AT_BEAT = "the_turn"


def method_true_at_beat(length_s=None):
    """``hook_plan.true_at_beat`` for a METHOD run (``hook_placement`` reads it,
    unchanged): the solution-introduction beat, at every length including 60 s.

    ``length_s`` is accepted so a caller can ask per length and get the same
    answer; the method has one hook-from beat, never the older ``lowest_point``.
    """
    return METHOD_TRUE_AT_BEAT


#: Canonical beat -> its position (1..15) in the fifteen-stage source method,
#: monotonic. product_intro (the reveal) is authored at source position 9 of 15.
BEAT_TO_SOURCE_POSITION = {
    "ordinary_world": 1, "humiliation": 2, "wound_deepens": 3, "frozen": 4,
    "seeing_it_too": 5, "failed_solutions": 6, "mentor": 7, "product_intro": 9,
    "doubt": 10, "climb": 12, "vindication": 14, "return_cta": 15,
}


class StoryArcError(ValueError):
    """Malformed manifest or binding; a gate that cannot read its input never passes."""


def _norm(text):
    """Fold for comparison: lowercase, keep alphanumerics and apostrophes."""
    return " ".join(re.findall(r"[a-z0-9']+", str(text or "").lower()))


def _tok(word):
    """One token for order matching: lowercase, keep alphanumerics and
    apostrophes, and keep intra-word underscores so an id like ``beat_1`` is
    ONE token (never silently split into two)."""
    return re.sub(r"[^a-z0-9'_]", "", str(word or "").lower())


def _tokens(text):
    return [t for t in (_tok(w) for w in str(text or "").split()) if t]


def stage_mapping_report():
    """The explicit named mapping between the three counts: fifteen source-method
    stages, eight coarse timing stages, twelve canonical beats. Distinct counts,
    named stages -- never one count relabelled as another."""
    counts = {"source_method_stages": SOURCE_METHOD_STAGE_COUNT,
              "timing_stages": len(TIMING_STAGES), "canonical_beats": len(BEATS)}
    distinct = len(set(counts.values())) == len(counts)
    return {
        "source_method": SOURCE_METHOD_NAME,
        "source_method_stage_count": SOURCE_METHOD_STAGE_COUNT,
        "source_method_named_examples": list(SOURCE_METHOD_NAMED_EXAMPLES),
        "timing_stages": list(TIMING_STAGES),
        "timing_stage_count": len(TIMING_STAGES),
        "canonical_beats": list(BEATS),
        "canonical_beat_count": len(BEATS),
        "beat_to_timing": dict(BEAT_TO_TIMING),
        "beat_to_source_position": dict(BEAT_TO_SOURCE_POSITION),
        "counts": counts,
        "counts_are_distinct": distinct,
        "mapped_by_name_not_by_count": True,
    }


def build_manifest(source):
    """ONE source -> the performed-beat manifest for all twelve canonical beats.

    ``source`` is either a mapping keyed by canonical beat id, or a manifest /
    list already carrying ``beat`` keys. Each beat record carries the approved
    lines that must be heard IN ORDER, the delivery, the approved line ids, the
    measured window, the approved devices it must carry, the hook placement and
    the pace cue. Every canonical beat is emitted; a beat with no performed
    content is recorded as missing -- never silently dropped."""
    if isinstance(source, dict) and "beats" in source:
        src = source["beats"]
    else:
        src = source
    if isinstance(src, list):
        src = {b.get("beat") or b.get("beat_id"): b
               for b in src if isinstance(b, dict)}
    if not isinstance(src, dict):
        src = {}
    rows, missing = [], []
    for beat in BEATS:
        raw = src.get(beat) or {}
        if not isinstance(raw, dict):
            raw = {"lines": [raw]}
        lines = raw.get("lines")
        if isinstance(lines, str):
            lines = [lines]
        lines = [str(x) for x in (lines or []) if str(x).strip()]
        line_ids = [str(x) for x in (raw.get("line_ids") or [])]
        window = None
        win = raw.get("window")
        if isinstance(win, (list, tuple)) and len(win) == 2:
            try:
                window = [float(win[0]), float(win[1])]
            except (TypeError, ValueError):
                window = None
        row = {"beat": beat, "delivery": raw.get("delivery"),
               "line_ids": line_ids, "lines": lines, "window": window,
               "devices": [str(d) for d in (raw.get("devices") or [])],
               "hook": raw.get("hook"), "pace": raw.get("pace")}
        row["present"] = bool(lines or line_ids)
        if not row["present"]:
            missing.append(beat)
        rows.append(row)
    manifest = {"schema": MANIFEST_SCHEMA, "beat_count": len(BEATS), "beats": rows,
                "present_count": sum(1 for r in rows if r["present"]),
                "missing": missing,
                "source_method": SOURCE_METHOD_NAME,
                "source_method_stage_count": SOURCE_METHOD_STAGE_COUNT}
    manifest["fingerprint"] = creative_fingerprint(manifest)["sha256"]
    return manifest


def creative_fingerprint(manifest):
    """The creative fingerprint over the FIVE components WW-03 names: lines,
    delivery, beat map, hook and pace. Stable, order-independent JSON -> sha256."""
    rows = (manifest or {}).get("beats") if isinstance(manifest, dict) else None
    rows = rows or []
    comp = {k: [] for k in FINGERPRINT_COMPONENTS}
    for r in rows:
        b = r.get("beat")
        comp["lines"].append([b, [_norm(ln) for ln in (r.get("lines") or [])]])
        comp["delivery"].append([b, r.get("delivery")])
        comp["beat_map"].append([b, list(r.get("line_ids") or []), r.get("window")])
        comp["hook"].append([b, None if r.get("hook") is None else bool(r.get("hook"))])
        comp["pace"].append([b, r.get("pace")])
    blob = json.dumps(comp, sort_keys=True, separators=(",", ":"), default=str)
    return {"schema": FINGERPRINT_SCHEMA,
            "sha256": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
            "components": list(FINGERPRINT_COMPONENTS)}


def bind_revision(revision_id, manifest):
    """Bind ONE chosen master revision id to the manifest's fingerprint. This is
    the binding record stored with the take; it does NOT choose the revision --
    that is the owner's decision and is never made here."""
    fp = creative_fingerprint(manifest)
    return {"schema": FINGERPRINT_SCHEMA, "revision_id": str(revision_id),
            "fingerprint": fp["sha256"], "components": fp["components"]}


def _heard_tokens(aligned_words):
    ws = [w for w in (aligned_words or [])
          if isinstance(w, dict) and w.get("startS") is not None]
    ws.sort(key=lambda w: float(w.get("startS") or 0.0))
    return [(_tok(w.get("word")), float(w.get("startS") or 0.0),
             float(w.get("endS") or 0.0)) for w in ws]


def _find_line(tokens, line_tokens, window):
    """The index where ``line_tokens`` sits contiguously in ``tokens`` (inside
    ``window`` when one is given), or None. Order is the contract."""
    n = len(line_tokens)
    if not n or n > len(tokens):
        return None
    for i in range(len(tokens) - n + 1):
        if [t[0] for t in tokens[i:i + n]] == list(line_tokens):
            if window is None or window[0] <= tokens[i][1] <= window[1]:
                return i
    return None


def check_performed_manifest(manifest, binding, aligned_words, duration_s=None,
                             required_devices=None):
    """The performed-content story gate. FAILS when a required beat has no heard
    mapped line inside its measured window, when a line is reordered, when a
    required approved device is absent, or when the take's fingerprint does not
    match the fingerprinted revision actually submitted. A metadata-only
    twelve-identifier list never passes; missing heard evidence is UNAVAILABLE,
    never PASS."""
    if not isinstance(manifest, dict) or not manifest.get("beats"):
        return {"verdict": "UNAVAILABLE", "reason_code": "NO_MANIFEST",
                "failed": ["NO_MANIFEST"], "detail": "no performed-beat manifest"}
    failed = []
    present = [r for r in manifest["beats"] if r.get("present")]
    if not present:
        failed.append("MANIFEST_METADATA_ONLY")
    manifest_fp = creative_fingerprint(manifest)["sha256"]
    bind_fp = (binding or {}).get("fingerprint") if isinstance(binding, dict) else binding
    if not bind_fp:
        failed.append("TAKE_UNBOUND")
    elif bind_fp != manifest_fp:
        failed.append("FINGERPRINT_MISMATCH")
    tokens = _heard_tokens(aligned_words)
    positions = []
    # ORCH-DEFECTS-0710 (a): EVERY required beat whose ``present`` is False is
    # NAMED in the failed list -- one ``BEAT_MISSING:<beat>`` entry per absent
    # beat, and one for EVERY entry in ``manifest["missing"]``. A summary count
    # (``missing_beats``) never stands in for a named missing beat.
    for r in manifest["beats"]:
        if not r.get("present"):
            name = "BEAT_MISSING:%s" % r.get("beat")
            if name not in failed:
                failed.append(name)
    for _beat in (manifest.get("missing") or []):
        name = "BEAT_MISSING:%s" % _beat
        if name not in failed:
            failed.append(name)
    for r in manifest["beats"]:
        if not r.get("present"):
            continue
        line_tokens = _tokens(" ".join(r.get("lines") or []))
        if not line_tokens:
            if "MANIFEST_METADATA_ONLY" not in failed:
                failed.append("MANIFEST_METADATA_ONLY")
            continue
        idx = _find_line(tokens, line_tokens, r.get("window"))
        if idx is None:
            failed.append("BEAT_NOT_HEARD:%s" % r["beat"])
        else:
            positions.append((r["beat"], idx))
    order = [i for _, i in positions]
    if any(order[k] > order[k + 1] for k in range(len(order) - 1)):
        failed.append("BEAT_REORDERED")
    for d in (required_devices or []):
        if _tokens(d) and _find_line(tokens, _tokens(d), None) is None:
            failed.append("DEVICE_MISSING:%s" % d)
    if failed:
        verdict, reason = "FAIL", "PERFORMED_STORY_REJECTED"
    elif not tokens:
        verdict, reason = "UNAVAILABLE", "NOTHING_HEARD_TO_JUDGE"
    else:
        verdict, reason = "PASS", "PERFORMED_STORY_COVERED"
    return {"verdict": verdict, "reason_code": reason, "failed": failed,
            "heard_beats": [b for b, _ in positions],
            "missing_beats": list(manifest.get("missing") or []),
            "fingerprint": manifest_fp, "binding_fingerprint": bind_fp,
            "beat_count": len(manifest["beats"]),
            "detail": ("every required beat is heard in order and the take matches "
                       "the approved revision" if verdict == "PASS"
                       else "performed story rejected: %s" % ", ".join(failed))}


def assert_take_bound(take, manifest):
    """Never retroactively bind an existing take to an edited sheet.

    A take that carries a fingerprint different from the approved sheet's is
    refused; a take that carries none is UNAVAILABLE. Nothing here re-stamps a
    take -- an edited later draft can never certify earlier paid audio."""
    stored = take.get("fingerprint") if isinstance(take, dict) else take
    fp = creative_fingerprint(manifest)["sha256"]
    if not stored:
        return {"verdict": "UNAVAILABLE", "reason_code": "TAKE_UNBOUND",
                "fingerprint": fp, "detail": "the take carries no revision fingerprint"}
    if stored != fp:
        return {"verdict": "FAIL", "reason_code": "FINGERPRINT_MISMATCH",
                "fingerprint": fp, "take_fingerprint": stored,
                "detail": "the take does not match the approved sheet revision; an "
                          "edited sheet never re-binds an existing take"}
    return {"verdict": "PASS", "reason_code": "FINGERPRINT_MATCH", "fingerprint": fp,
            "detail": "the take matches the fingerprinted approved revision"}


def revision_provenance(binding, take):
    """Which approved revision a delivered take came from (WW-15). Records the
    binding's revision id and the take's stored fingerprint; never asserts a
    match it cannot prove."""
    stored = take.get("fingerprint") if isinstance(take, dict) else take
    bind_fp = (binding or {}).get("fingerprint") if isinstance(binding, dict) else None
    return {"revision_id": (binding or {}).get("revision_id") if isinstance(binding, dict) else None,
            "binding_fingerprint": bind_fp, "take_fingerprint": stored,
            "matched": bool(stored) and stored == bind_fp,
            "determined": bool(binding) and bool(stored)}


# =====================================================================
# WW-28: causal plot and earned hook. BEFORE budgeting, the script must
# declare a CAUSAL chain -- scene, inciting event, opposing action,
# escalation, cost, choice, product mechanism, consequence and commercial
# action -- built from FICTION separated from TESTIMONIAL fact, with an
# exact hook LINE defined against the refrain BEFORE any counting, and a
# closing that carries an approved commercial call, never a summary-only
# promise, an interchangeable slogan or a magical unsupported cure. An
# independent NON-MAKER reconstructs the causal story from the EXACT
# lyrics, never from a scene summary. This is a PRE-GENERATION craft gate:
# it adds NO delivered-audio craft gate (D1-D5 stay the only audio gates).
# Every threshold below is a NEW PROPOSED ACCEPTANCE RULE (WW-28), never a
# measured limit of an earlier run and NOT a number Trevor set.
# =====================================================================

CAUSAL_SCHEMA = "blackceo.causal-story/v1"
#: The nine causal fields, in causal order. Each must be declared and
#: non-empty BEFORE budgeting: an ad whose plot is not causal is not planned.
CAUSAL_FIELDS = ("scene", "inciting_event", "opposing_action", "escalation",
                 "cost", "choice", "product_mechanism", "consequence",
                 "commercial_action")
#: A scene is invented (fiction) or a real client fact (testimonial). The two
#: are never mixed: a claim shown as the client's real life is not a scene.
SCENE_KINDS = ("fiction", "testimonial")
#: A real commercial call: an action the viewer can take. PROPOSED list.
COMMERCIAL_ACTIONS = ("book", "order", "assessment", "schedule", "call",
                      "apply", "enroll", "enrol", "reserve", "checkout", "buy",
                      "sign up")
#: A closing that promises but never asks for anything.
_PROMISE_RE = re.compile(r"\b(will (?:change|transform)|your (?:life|world)|a new you|"
                         r"believing in yourself|the answer is within|everything you ever|"
                         r"nothing (?:can|will) stop)\b", re.I)
#: A magical, unsupported cure: a claim of a fix with no mechanism.
_CURE_RE = re.compile(r"\b(miraculous|instantly (?:cures?|fixes?|heals?)|"
                      r"permanently (?:cures?|fixes?|heals?)|cures? you|"
                      r"(?:guaranteed|always) works|fixes? (?:you|it all))\b", re.I)
_COMMERCIAL_RE = re.compile(r"\b(%s)\b" % "|".join(re.escape(a) for a in COMMERCIAL_ACTIONS),
                            re.I)
#: a block tagged as the closing call.
_CTA_TAG_RE = re.compile(r"\b(?:cta|call ?to ?action|offer|book|assessment|"
                         r"next ?step|closing|pitch)\b", re.I)
_SECTION_RE = re.compile(r"\[[^\]]*\]")
_BLOCK_RE = re.compile(r"^\[([^\]]*)\]\s*$")
_COST_RE = re.compile(r"\b(lost|lose|losing|cost|costs|hurt|hurts|failed|fail|debt|"
                      r"broke|broken|alone|pain|ache|empty|tired|scared|afraid|wound|"
                      r"wounded|nothing left|gave up)\b", re.I)
_SPEAKER_RE = re.compile(r"^(?P<who>[A-Z][A-Za-z'’\-]{1,20})\s*:\s*\S")
_LINK_RE = re.compile(r"\b(cause|causes|caused|effect|because|so|then|leads?|led|"
                      r"result|therefore|which made|and that)\b", re.I)


def _blank(v):
    """True when a declared value carries nothing: None, empty string/list/dict."""
    if v is None:
        return True
    if isinstance(v, str):
        return not v.strip()
    if isinstance(v, (list, tuple, dict, set)):
        return len(v) == 0
    return False


def declares_causal(story):
    """True when the record declares causal content (a ``causal`` block or any
    of the nine causal fields on the record). A record with none is judged by
    the legacy beat contract alone."""
    if not isinstance(story, dict):
        return False
    if isinstance(story.get("causal"), dict):
        return True
    return any(f in story for f in CAUSAL_FIELDS)


def _causal_block(story):
    blk = dict(story.get("causal")) if isinstance(story.get("causal"), dict) else {}
    for f in CAUSAL_FIELDS + ("lyrics", "maker", "approved_by"):
        if f in story and f not in blk:
            blk[f] = story[f]
    return blk


def _scene_links(scene):
    """True when a scene row carries a causal link (a cause/effect key or a
    linking word in its text). A flat list of images carries none."""
    if not isinstance(scene, dict):
        return bool(_LINK_RE.search(str(scene or "")))
    for k in ("cause", "effect", "because", "then", "leads", "result"):
        if not _blank(scene.get(k)):
            return True
    return bool(_LINK_RE.search(" ".join(str(scene.get(k) or "")
                                          for k in ("text", "line", "then", "effect"))))


def _contains(seq, sub):
    """True when ``sub`` sits contiguously in ``seq`` (both token lists)."""
    n = len(sub)
    if not n or n > len(seq):
        return False
    return any(seq[i:i + n] == list(sub) for i in range(len(seq) - n + 1))


_CB_MOD = None


def _cast_model():
    """character_bible.character_bible, loaded once (WW-27's ensemble cast model).

    WW-28's reconstruction gate judges the 'exchanged replies' leg against this
    cast model whenever the story declares a cast. Lazy so a story with no
    declared cast never imports it (base behaviour unchanged)."""
    global _CB_MOD
    if _CB_MOD is None:
        try:
            import character_bible.character_bible as _cb    # noqa: PLC0415
        except Exception:
            try:
                from character_bible import character_bible as _cb   # noqa: PLC0415
            except Exception:
                return None
        _CB_MOD = getattr(_cb, "character_bible", _cb)
    return _CB_MOD


def _rec(determined, reason_code, detail, **extra):
    out = {"determined": bool(determined), "reason_code": reason_code, "detail": detail,
           "stakes": None, "exchanged_replies": None, "earned_hook": None,
           "hook_line": None, "cast_model": "base-structures"}
    out.update(extra)
    return out


def reconstruct_causal_story(lyrics, hook_line=None, cast=None):
    """An independent NON-MAKER reads the EXACT lyrics -- never a scene
    summary -- and reconstructs the causal story. Returns
    {"determined", "reason_code", "detail", "stakes", "exchanged_replies",
     "earned_hook", "hook_line", "cast_model", "traded_reply"}.

    The exact lyrics carry SECTION TAGS; a scene summary does not. With NO cast
    declared the 'exchanged replies' leg is judged against the character
    structures already on the base (speaker prefixes and quoted replies). When
    the story DECLARES a cast -- WW-27's ensemble character bible -- the leg is
    judged against THAT cast model instead: a villain or foil must SPEAK and
    receive a consequential reply from another declared character
    (``character_bible.traded_replies`` over ``character_bible.speaker_turns``),
    and the receipt carries ``cast_model: "ww27-ensemble-cast"`` plus the traded
    reply. This is WW-28's DEPENDS-ON-WW-27 clause, finished on WW-27's model."""
    text = str(lyrics or "")
    if not text.strip():
        return _rec(False, "causal-lyrics-missing",
                    "the exact approved lyrics are required to reconstruct the story")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    body = [ln for ln in lines if not _SECTION_RE.search(ln)]
    if not _SECTION_RE.search(text) or not body:
        return _rec(False, "SCENE_SUMMARY_NOT_LYRICS",
                    "no section tags: this is a scene summary, not the exact lyrics; the "
                    "story is reconstructed from the lyrics alone")
    stakes = any(_COST_RE.search(ln) for ln in body)
    speakers = [m.group("who").lower() for m in (_SPEAKER_RE.match(ln) for ln in body) if m]
    quoted = sum(1 for ln in body if ln.count('"') >= 2 or ln.count("“") >= 1)
    exchanged = (len(set(speakers)) >= 2) or (quoted >= 2) or any(
        body[i].endswith("?") and i + 1 < len(body) and not body[i + 1].endswith("?")
        for i in range(len(body)))
    # WW-27's cast model, when the story declares one: a villain or foil must
    # speak AND be answered. Only the 'exchanged replies' leg moves; stakes and
    # the earned hook are unchanged.
    cast_model = "base-structures"
    traded = None
    if cast is not None:
        cb = _cast_model()
        if cb is not None:
            cast_model = "ww27-ensemble-cast"
            resolved = cb.resolve_cast(cast)
            opponents = [c["name"] for c in (resolved.get("characters") or [])
                         if c.get("role") in cb.OPPOSING_ROLES]
            traded = (cb.traded_replies(cb.speaker_turns(text), opponents)
                      if opponents else None)
            exchanged = traded is not None
    hook = str(hook_line or "").strip()
    earned = None
    if hook:
        htoks = _tokens(hook)
        hit = next((i for i, ln in enumerate(body) if _contains(_tokens(ln), htoks)), None)
        earned = hit is not None and any(_COST_RE.search(ln) for ln in body[:hit])
    missing = []
    if not stakes:
        missing.append("stakes")
    if not exchanged:
        missing.append("exchanged replies")
    if hook and not earned:
        missing.append("earned hook")
    if missing:
        return _rec(False, "CAUSAL_CHAIN_INCOMPLETE",
                    "the exact lyrics do not reconstruct a causal story (missing: %s)"
                    % ", ".join(missing), stakes=stakes, exchanged_replies=exchanged,
                    earned_hook=earned, hook_line=hook or None, cast_model=cast_model,
                    traded_reply=traded)
    return _rec(True, "causal-reconstructed",
                "the causal story reconstructs from the exact lyrics",
                stakes=stakes, exchanged_replies=exchanged, earned_hook=earned,
                hook_line=hook or None, cast_model=cast_model, traded_reply=traded)


def check_causal_story(story):
    """The causal craft gate: refuse a non-causal, mood-board, self-approved or
    slogan-closed story BEFORE budgeting. Only runs on a record that declares
    causal content (``declares_causal``). Never raises."""
    if not isinstance(story, dict):
        return {"schema": CAUSAL_SCHEMA, "outcome": "error", "reason_code": "story-not-an-object",
                "errors": [{"error": "story-not-an-object"}], "declared": []}
    blk = _causal_block(story)
    errors = []
    declared = sorted(f for f in CAUSAL_FIELDS if not _blank(blk.get(f)))
    missing = [f for f in CAUSAL_FIELDS if _blank(blk.get(f))]
    if missing:
        errors.append({"error": "causal-incomplete",
                       "detail": "before budgeting every causal field must be declared; missing: %s"
                                 % ", ".join(missing)})
    scenes = story.get("scenes")
    if scenes is None and isinstance(blk.get("scene"), list):
        scenes = blk["scene"]
    if scenes is not None:
        if not isinstance(scenes, list) or not scenes:
            errors.append({"error": "scene-kind-undeclared",
                           "detail": "scenes must be a non-empty list of {kind, text}"})
        else:
            bad = [i for i, s in enumerate(scenes)
                   if not isinstance(s, dict)
                   or str(s.get("kind", "")).lower() not in SCENE_KINDS]
            if bad:
                errors.append({"error": "scene-kind-undeclared",
                               "detail": "scene index %s: kind must be one of %s -- a fiction is "
                                         "never told as a testimonial fact" % (bad, list(SCENE_KINDS))})
            elif len(scenes) > 1 and not any(_scene_links(s) for s in scenes):
                errors.append({"error": "mood-board-plot",
                               "detail": "scenes carry no causal link (cause/effect/because/then): "
                                         "a mood board, not a plot"})
    contra = []
    ca_have = str(blk.get("commercial_action") or "").strip()
    lyrics_text = str(blk.get("lyrics") or story.get("lyrics") or "")
    if ca_have and lyrics_text.strip():
        if closing_block(lyrics_text) is None:
            contra.append("the story declares the closing call %r but the payload has no closing "
                          "block to carry it" % ca_have)
        else:
            cl = check_payload_closing(lyrics_text, commercial_action=ca_have, require_cta=True)
            if cl.get("outcome") == "rejected":
                contra.append("the story closes on %r but the payload closing does not carry it "
                              "(%s)" % (ca_have, cl["reason_code"]))
    if isinstance(story.get("beats"), list) and "product_intro" in story["beats"]:
        pi = story["beats"].index("product_intro") + 1
        rev = story.get("product_reveal")
        if isinstance(rev, int) and not isinstance(rev, bool) and pi < rev:
            contra.append("product_intro appears at beat %d, before the reveal stage %d"
                          % (pi, rev))
    if contra:
        errors.append({"error": "causal-contradiction", "detail": "; ".join(contra)})
    ca = str(blk.get("commercial_action") or "")
    if ca:
        if _CURE_RE.search(ca):
            errors.append({"error": "magical-cure",
                           "detail": "commercial action promises a cure with no mechanism: %r" % ca})
        elif not _COMMERCIAL_RE.search(ca):
            errors.append({"error": "summary-only-promise",
                           "detail": "commercial action %r asks for no real step "
                                     "(book/order/assessment/schedule/call/apply)" % ca})
    maker = str(story.get("maker") or blk.get("maker") or "").strip().lower()
    approver = str(story.get("approved_by") or blk.get("approved_by") or "").strip().lower()
    if maker and approver and maker == approver:
        errors.append({"error": "maker-self-approval",
                       "detail": "the maker %r cannot approve their own script" % maker})
    hook = story.get("hook") if isinstance(story.get("hook"), dict) else None
    hline = str((hook or {}).get("line") or "").strip()
    refrain = str((hook or {}).get("refrain") or "").strip()
    if hook is None or not hline:
        errors.append({"error": "hook-line-undefined",
                       "detail": "define the EXACT hook line against the refrain before any counting"})
    elif refrain and _norm(hline) == _norm(refrain):
        errors.append({"error": "hook-line-undefined",
                       "detail": "the hook line and the refrain are the same text; the exact hook "
                                 "line is defined separately from the refrain"})
    lyrics = blk.get("lyrics") or story.get("lyrics")
    cast = blk.get("cast")
    if cast is None and (blk.get("characters") or blk.get("cast_mode")):
        cast = blk
    rec = reconstruct_causal_story(lyrics, hook_line=hline or None, cast=cast)
    if not rec["determined"]:
        errors.append({"error": rec["reason_code"], "detail": rec["detail"]})
    if errors:
        return {"schema": CAUSAL_SCHEMA, "outcome": "rejected", "reason_code": errors[0]["error"],
                "errors": errors, "declared": declared, "reconstruction": rec}
    return {"schema": CAUSAL_SCHEMA, "outcome": "ok", "reason_code": "causal-ok",
            "errors": [], "declared": declared, "reconstruction": rec}


def _blocks(text):
    out, cur = [], None
    for ln in str(text or "").splitlines():
        s = ln.strip()
        if not s:
            continue
        m = _BLOCK_RE.match(s)
        if m:
            cur = {"tag": m.group(1), "lines": []}
            out.append(cur)
        elif cur is not None:
            cur["lines"].append(s)
    return out


def closing_block(sheet_text):
    """The closing block: the last non-[End], non-instrumental section, or None."""
    blocks = [b for b in _blocks(sheet_text)
              if not re.search(r"\bend\b|instrumental", b["tag"], re.I)]
    return blocks[-1] if blocks else None


def check_payload_closing(sheet_text, commercial_action=None, require_cta=False):
    """The payload CLOSING must carry an approved commercial call (book order /
    assessment call) -- never a summary-only promise, a slogan or a magical
    unsupported cure. Fires when the closing block is tagged as a call
    (``[CTA ...]``/``[Offer ...]``), when a call is required, or when an
    approved commercial action is supplied; otherwise it stands aside and
    reports ``skipped`` so it never refuses a sheet it was never pointed at."""
    blk = closing_block(sheet_text)
    if blk is None:
        return {"outcome": "skipped", "reason_code": "no-closing", "detail": ""}
    if not (_CTA_TAG_RE.search(blk["tag"]) or require_cta or commercial_action is not None):
        return {"outcome": "skipped", "reason_code": "not-a-call-block", "detail": "",
                "tag": blk["tag"]}
    body = " ".join(blk["lines"])
    out = {"tag": blk["tag"], "body": body, "commercial_action": commercial_action}
    if _CURE_RE.search(body):
        out.update(outcome="rejected", reason_code="magical-cure",
                   detail="the closing promises a cure with no mechanism")
        return out
    if not _COMMERCIAL_RE.search(body):
        out.update(outcome="rejected", reason_code="summary-only-promise",
                   detail="the closing asks for no commercial action "
                          "(book/order/assessment/schedule/call/apply)")
        return out
    if commercial_action is not None:
        want = _COMMERCIAL_RE.search(str(commercial_action))
        if want and not re.search(r"\b%s\b" % re.escape(want.group(1)), body, re.I):
            out.update(outcome="rejected", reason_code="closing-not-approved-call",
                       detail="the closing lacks the approved action %r" % want.group(1))
            return out
    out.update(outcome="ok", reason_code="closing-ok",
               detail="the closing carries the commercial call")
    return out


def count_hook_occurrences(sheet_text, hook):
    """Audition the hook on the approved script: the EXACT hook line is counted,
    the refrain and any companion line are NOT. Returns
    {"hook_line", "refrain", "declared", "counted_exact", "counted_with_companions",
     "companion_substitution"}.

    ``declared`` is the number of hook occurrences the sheet declares (the
    number of hook blocks); ``counted_with_companions`` adds any line that
    shares the hook's opening words but is a DIFFERENT line, so a promised two
    occurrences can never be reported as four through companion lines."""
    hook = hook or {}
    hline = str(hook.get("line") or "").strip()
    refrain = str(hook.get("refrain") or "").strip()
    htoks = _tokens(hline)
    blocks = _blocks(sheet_text)
    lines = [ln for b in blocks for ln in b["lines"]]
    exact = sum(1 for ln in lines if _norm(ln) == _norm(hline)) if hline else 0
    with_comp = exact
    if htoks:
        head = htoks[0]
        for ln in lines:
            toks = _tokens(ln)
            if not toks or toks[0] != head:
                continue
            if _norm(ln) == _norm(hline):
                continue
            shared = len(set(toks) & set(htoks))
            if shared >= max(1, len(htoks) // 2):
                with_comp += 1
    declared = int(hook.get("declared_occurrences") or exact)
    return {"hook_line": hline or None, "refrain": refrain or None, "declared": declared,
            "counted_exact": exact, "counted_with_companions": with_comp,
            "companion_substitution": with_comp > declared and with_comp > exact}


def check_hook_declaration(sheet_text, hook):
    """Refuse a hook whose declared occurrences are inflated by companion-line
    substitution. Returns {"outcome", "reason_code", "detail", "counts"}."""
    counts = count_hook_occurrences(sheet_text, hook)
    if not counts["hook_line"]:
        return {"outcome": "rejected", "reason_code": "hook-line-undefined",
                "detail": "no exact hook line is defined against the refrain", "counts": counts}
    if counts["companion_substitution"]:
        return {"outcome": "rejected", "reason_code": "hook-companion-substitution",
                "detail": "%d declared hook occurrence(s) would be counted as %d through "
                          "companion lines" % (counts["declared"], counts["counted_with_companions"]),
                "counts": counts}
    return {"outcome": "ok", "reason_code": "hook-counted",
            "detail": "%d hook occurrence(s), counted on the exact hook line" % counts["declared"],
            "counts": counts}


def assert_mappings_intact():
    """The three counts are preserved and mapped by name: twelve canonical beats,
    eight timing stages, fifteen source-method stages. Returns the mapping report
    after asserting the counts have not drifted (WW-28: 'preserve explicit
    mappings')."""
    report = stage_mapping_report()
    assert report["canonical_beat_count"] == 12, "canonical beat count drifted"
    assert report["timing_stage_count"] == 8, "timing stage count drifted"
    assert report["source_method_stage_count"] == 15, "source-method stage count drifted"
    assert report["counts_are_distinct"], "the three counts were relabelled as one another"
    assert set(report["beat_to_timing"]) == set(BEATS), "beat->timing mapping is incomplete"
    assert set(report["beat_to_source_position"]) == set(BEATS), \
        "beat->source-position mapping is incomplete"
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(prog="story_arc.py",
                                 description="Twelve-beat story arc validator (directive 11.1).")
    ap.add_argument("--selftest", action="store_true", help="Run QC fixtures.")
    ap.add_argument("--story", default=None, help="Story record as a JSON file.")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.story:
        ap.error("one of --selftest or --story is required")
    try:
        with open(a.story, encoding="utf-8") as f:
            story = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        r = {"schema_version": SCHEMA_VERSION, "tool_version": TOOL_VERSION,
             "outcome": "error", "reason_code": "story-unreadable",
             "errors": [{"error": "story-unreadable", "detail": str(e)[:200]}],
             "beat_count": 0, "beats": [], "product_reveal": None,
             "next_action": "Supply a readable JSON story record."}
    else:
        r = validate_story(story)
    json.dump(r, sys.stdout, indent=2, sort_keys=True, default=str)
    sys.stdout.write("\n")
    return EXIT[r["outcome"]]


if __name__ == "__main__":
    sys.exit(main())
