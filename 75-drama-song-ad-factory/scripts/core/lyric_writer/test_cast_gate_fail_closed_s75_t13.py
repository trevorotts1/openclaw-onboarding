#!/usr/bin/env python3
"""S75-T13 (S75-A13): absent foundations cannot bypass ``_cast_gate``.

The candidate makes the cast foundation a MANDATORY input on every authoring
entry: ``require_cast_manifest`` and ``validate_authored_lyrics`` never return
None and expose no argument that turns the gate off. A brief carrying the Skill
75 foundation envelope (``episode_cast_manifest``) is gated even through the
legacy ``validate_lyrics`` surface, so a caller cannot skip the gate by
omitting cast fields or by changing the brief's shape.

Preserved on purpose (no regression for existing callers): ``validate_lyrics``
with a plain brief and no cast declaration keeps reading exactly as WW-27 left
it -- already-authored copy is still validated, and only authoring entries are
forced to the required gate.

Stdlib only, no network, no provider call. Run: python3 -I <this file>
"""
import importlib.util
import inspect
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
for p in (CORE, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

_spec = importlib.util.spec_from_file_location(
    "lyric_writer_module", os.path.join(HERE, "lyric_writer.py"))
LW = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(LW)

SV_MARA = {"register": "warm alto", "timbre": "bright and open",
           "articulation": "clear clipped consonants", "delivery": "belted and forward",
           "emotional_progression": "guarded to soaring",
           "version_treatment": "lead take, doubled on the hook"}
SV_JONAS = {"register": "low bass-baritone", "timbre": "gravel and edge",
            "articulation": "hard clipped consonants", "delivery": "metered and cold",
            "emotional_progression": "cold to breaking",
            "version_treatment": "lead take, dry and close"}
SV_FOIL = {"register": "mid tenor", "timbre": "reedy and thin",
           "articulation": "soft consonants", "delivery": "plain and plainspoken",
           "emotional_progression": "nervous to certain",
           "version_treatment": "answering take, slightly behind the beat"}
LINES = [{"line_id": "v1", "text": "I walk out free"},
         {"line_id": "v2", "text": "I hold the light"}]


def _char(name, role, gender, sv):
    return {"name": name, "role": role, "gender": gender,
            "want": "to be free of the door",
            "wound": "a door closed on them young",
            "relationships": "the other characters in this scene",
            "consequential_action": "walks out and burns the list",
            "voice": "speaks plain and low", "voice_direction": dict(sv)}


def complete_cast():
    """The KNOWN-GOOD WW-27 ensemble: protagonist, speaking villain, foil."""
    return {"cast_mode": "ensemble",
            "characters": [_char("Mara", "protagonist", "female", SV_MARA),
                           _char("Jonas", "villain", "male", SV_JONAS),
                           _char("Tobin", "foil", "male", SV_FOIL)]}


def manifest_entry(cid):
    return {"character_id": cid, "identity_revision": 1,
            "identity_digest": "0" * 64, "episode_role": "protagonist",
            "scene_ids": ["s1"], "immediate_story_function": "opens the door",
            "choice_or_consequence": "leaves and does not return"}


def checks():
    out = []

    def check(name, cond, detail=""):
        out.append((name, bool(cond), detail))

    # 1. an ABSENT cast is a refusal, never None and never a pass.
    for label, brief in (("empty brief", {}), ("None brief", None),
                         ("unrelated brief", {"product_name": ""})):
        r = LW.require_cast_manifest(brief)
        check("require_cast_manifest(%s) is a FAIL receipt" % label,
              r is not None and r["verdict"] == "FAIL" and r["blocked"] is True,
              repr(r))
        check("require_cast_manifest(%s) names the missing foundation" % label,
              r is not None and r["reason_code"] == LW.CODE_CAST_FOUNDATION_MISSING
              and r["reasons"] and "missing input" in r["reasons"][0],
              repr(r))

    # 2. the foundation envelope cannot be emptied into an opt-out.
    for label, manifest in (("empty", {}), ("none", None), ("string", "cast"),
                            ("empty cast", {"cast": []})):
        r = LW.require_cast_manifest({"episode_cast_manifest": manifest})
        check("an %s episode_cast_manifest fails closed" % label,
              r is not None and r["verdict"] == "FAIL"
              and r["reason_code"] in (LW.CODE_CAST_FOUNDATION_MISSING,
                                       LW.CODE_CAST_FOUNDATION_INVALID),
              repr(r))

    # 3. a contract-valid manifest passes; a defectful one refuses, NOT bypasses.
    good = {"episode_cast_manifest": {"cast": [manifest_entry("c1"),
                                               manifest_entry("c2")]}}
    r = LW.require_cast_manifest(good)
    check("a valid episode cast manifest PASSES", r["verdict"] == "PASS"
          and r["characters_n"] == 2, repr(r))
    thin = {"episode_cast_manifest": {"cast": [{"character_id": "c1"}]}}
    r = LW.require_cast_manifest(thin)
    check("an under-specified cast manifest refuses (never a skip)",
          r["verdict"] == "FAIL"
          and r["reason_code"] == LW.CODE_CAST_FOUNDATION_INVALID
          and "identity_digest" in r["reasons"][0], repr(r))

    # 4. the WW-27 declaration keeps its own verdicts through the same gate.
    r = LW.require_cast_manifest(complete_cast())
    check("a complete WW-27 cast PASSES the required gate",
          r["verdict"] == "PASS" and r["reason_code"] == "ENSEMBLE_CAST_OK", repr(r))
    broken = {"cast_mode": "ensemble",
              "characters": [{"name": "Mara", "role": "protagonist"}]}
    r = LW.require_cast_manifest(broken)
    check("a declared-but-broken cast is REFUSED, not skipped",
          r["verdict"] == "FAIL"
          and r["reason_code"] in ("CAST_NOT_ENSEMBLE", "CAST_INCOMPLETE"), repr(r))

    # 5. the authoring entry fails closed BEFORE a line is judged.
    r = LW.validate_authored_lyrics(LINES, {})
    check("validate_authored_lyrics refuses an absent cast",
          r["outcome"] == "rejected"
          and r["reason_code"] == LW.CODE_CAST_FOUNDATION_MISSING, repr(r))
    check("the refusal precedes line judging (zero coverage)",
          r["coverage"]["covered"] == 0 and r["coverage"]["critical_words"] == 0,
          repr(r.get("coverage")))
    check("the refusal rides on the cast decision",
          r["cast_decision"]["reason_code"] == LW.CODE_CAST_FOUNDATION_MISSING,
          repr(r.get("cast_decision")))
    check("the authoring entry has NO cast-off parameter",
          "require_cast" not in inspect.signature(
              LW.validate_authored_lyrics).parameters,
          repr(inspect.signature(LW.validate_authored_lyrics)))
    r = LW.validate_authored_lyrics(LINES, complete_cast())
    check("the authoring entry still admits a complete cast",
          r["outcome"] in ("ok", "rejected") and r["reason_code"] !=
          LW.CODE_CAST_FOUNDATION_MISSING, repr(r))

    # 6. a foundation-envelope brief cannot bypass through the legacy surface.
    r = LW.validate_lyrics(LINES, {"episode_cast_manifest": {}})
    check("legacy validate_lyrics gates a foundation-envelope brief",
          r["outcome"] == "rejected"
          and r["reason_code"] == LW.CODE_CAST_FOUNDATION_MISSING, repr(r))

    # 7. the documented legacy surface is unchanged (no existing caller breaks).
    leg = LW.validate_lyrics([{"line_id": "v1", "text": "I walk out free"}],
                             {"product_name": ""})
    check("a plain cast-less legacy brief is judged as before",
          leg.get("cast_decision") is None and leg["outcome"] == "ok", repr(leg))
    leg2 = LW.validate_lyrics(
        [{"line_id": "v1", "text": "I walk out free"}],
        {"characters": ["Mara"], "packet_lines": ["I walk out free"]})
    check("an H7 names-only `characters` list is judged as before",
          leg2.get("cast_decision") is None and leg2["outcome"] == "ok", repr(leg2))
    declared = LW.validate_lyrics(
        [{"line_id": "v1", "text": "I walk out free"}], {"cast_mode": "ensemble",
                                                          "characters": []})
    check("a declared cast is still gated on the legacy surface",
          declared["outcome"] == "rejected"
          and declared["reason_code"] == "CAST_NOT_ENSEMBLE", repr(declared))

    # 8. no silent None path for a required call, on any input shape.
    for bad in ({}, {"cast": None}, {"characters": []}, "not-a-brief", 0, []):
        r = LW._cast_gate(bad, required=True)
        check("_cast_gate(%r, required=True) never returns None" % (bad,),
              r is not None and r["verdict"] == "FAIL", repr(r))

    return out


def main():
    results = checks()
    failed = [(n, d) for n, ok, d in results if not ok]
    for name, ok, detail in results:
        print("%s %s%s" % ("PASS" if ok else "FAIL", name,
                           "" if ok else " :: " + detail[:300]))
    print("\n%d checks, %d failed" % (len(results), len(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
