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


def validate_story(story):
    """Validate a twelve-beat story record.

    Story record: {"story_id": ..., "beats": [beat_id x12], "product_reveal": int}
    Returns outcome/reason_code/errors/beat_count/beats/product_reveal/next_action.
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

    known = set(BEATS)
    unknown = sorted({b for b in ids if b not in known})
    if unknown:
        errors.append({"error": "beat-unknown", "detail": unknown})

    seen, dups = set(), []
    for b in ids:
        if b in seen and b not in dups:
            dups.append(b)
        seen.add(b)
    if dups:
        errors.append({"error": "beat-duplicate", "detail": sorted(dups)})

    missing = [b for b in BEATS if b not in seen]
    if missing:
        errors.append({"error": "beat-missing", "detail": missing})

    if len(ids) != len(BEATS):
        errors.append({"error": "beat-count",
                       "detail": "got %d, want %d" % (len(ids), len(BEATS))})

    if not unknown:  # order: every known beat must advance in canonical order
        order = [BEATS.index(b) for b in ids if b in known]
        if any(order[i] > order[i + 1] for i in range(len(order) - 1)):
            errors.append({"error": "beat-order", "detail": list(ids)})

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
