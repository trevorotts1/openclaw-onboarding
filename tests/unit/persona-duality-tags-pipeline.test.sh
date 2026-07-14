#!/usr/bin/env bash
# tests/unit/persona-duality-tags-pipeline.test.sh
# ─────────────────────────────────────────────────────────────────────────────
# Hermetic tests for D6 (ONB22-DUALITY-TAGS): the Skill-22 book-to-persona
# pipeline (22-…/pipeline/orchestrator.py) now parses an OPTIONAL '## Duality
# Tags' block out of a synthesized persona-blueprint.md and, when well-formed,
# stamps audiences[]/topics[]/voice_style{}/usable_as[] into the persona's
# persona-categories.json entry — the fields the Skill-23 voice-first
# AUDIENCE+TOPIC blend matcher (persona_blend.py) reasons over. Before this
# fix NOTHING in the pipeline ever wrote these fields for a newly-synthesized
# persona, freezing the blend matcher's candidate universe at the 99
# one-time-backfilled personas (v6.17.0) forever.
#
# Invariants under test:
#   • absent block            -> NO-OP (pre-enrichment; core entry unaffected)
#   • well-formed block       -> audiences/topics/voice_style/usable_as land
#                                 on the entry, gated through
#                                 persona_blend.validate_catalog_tags (the SAME
#                                 rulebook the Skill-23 matcher enforces at
#                                 read-time — one rulebook, not two).
#   • malformed/rejected block -> reported LOUD (_DUALITY_TAG_WRITE_FAILURES)
#                                 and OMITTED — NEVER written half-valid, and
#                                 NEVER blocks the domain/perspective
#                                 registration (never-to-zero core routing).
#   • vocab-first             -> an audience/topic tag not already in a
#                                 POPULATED audienceTags/topicTags vocab is
#                                 rejected (no silent auto-extend, unlike
#                                 domain/perspective — matches persona_fleet.py
#                                 _validate_entry's existing publish-path rule).
#   • _synthesis_system()     -> dynamically injects the LIVE vocab into the
#                                 Phase-3 prompt when populated; omits the
#                                 block entirely when empty/absent.
#   • defensive fallback      -> when persona_blend isn't importable, a local
#                                 structural check still rejects bad shapes.
#
# No network, no aiohttp path exercised (functions imported directly). Real
# $HOME is preserved so aiohttp/idna user-site deps resolve at module import;
# sandbox paths are injected by monkeypatching orchestrator module globals
# AFTER import (mirrors tests/unit/phase6-categories-fail-loud.test.sh).
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SKILL="$REPO_ROOT/22-book-to-persona-coaching-leadership-system"
ORCH="$SKILL/pipeline/orchestrator.py"
PBLEND="$REPO_ROOT/23-ai-workforce-blueprint/scripts/persona_blend.py"

for f in "$ORCH" "$PBLEND"; do
    [ -f "$f" ] || { echo "FATAL: missing $f"; exit 2; }
done

SB="$(mktemp -d -t p6-duality.XXXXXX)"
trap 'rm -rf "$SB"' EXIT

PIPELINE_DIR="$SKILL/pipeline" SB="$SB" python3 - <<'PY'
import os, sys, json
sys.path.insert(0, os.environ["PIPELINE_DIR"])
SB = os.environ["SB"]

import orchestrator as o
from pathlib import Path

personas_dir = Path(SB) / "personas"
personas_dir.mkdir(parents=True, exist_ok=True)
catpath = Path(SB) / "persona-categories.json"
o.PERSONAS_DIR = personas_dir
o._persona_categories_path = lambda: catpath
o.LOG_FILE = Path(SB) / "pipeline-log.txt"
o.STATUS_FILE = Path(SB) / "pipeline-status.json"

PASS = 0; FAIL = 0
def check(cond, msg):
    global PASS, FAIL
    if cond:
        print("  PASS:", msg); PASS += 1
    else:
        print("  FAIL:", msg); FAIL += 1

def seed_categories(audience_tags=None, topic_tags=None):
    catpath.write_text(json.dumps({
        "schemaVersion": "1.3",
        "domainTags": ["leadership", "coaching", "marketing"],
        "perspectiveTags": ["mens-challenges", "womens-challenges"],
        "audienceTags": audience_tags or [],
        "topicTags": topic_tags or [],
        "personas": {},
    }, indent=2))

def mk_blueprint(folder, duality_json=None, body="leadership leadership coaching",
                  raw_duality_text=None):
    d = personas_dir / folder
    d.mkdir(parents=True, exist_ok=True)
    text = f"# {folder}\n\n{body}\n"
    if raw_duality_text is not None:
        text += "\n" + raw_duality_text + "\n"
    elif duality_json is not None:
        text += (
            "\n## Duality Tags (Machine-Readable)\n\n```json\n"
            + json.dumps(duality_json, indent=2) + "\n```\n"
        )
    (d / "persona-blueprint.md").write_text(text)

def read_cats():
    return json.loads(catpath.read_text())

_ORIG_APPEND = o._append_persona_to_categories

def reset(**kw):
    o._DUALITY_TAG_WRITE_FAILURES.clear()
    o._CATEGORIES_WRITE_FAILURES.clear()
    o._append_persona_to_categories = _ORIG_APPEND
    seed_categories(**kw)

book = {"author": "Test Author", "title": "Test Book"}

# ── Case 1: no Duality Tags block -> pre-enrichment NO-OP ─────────────────────
print("── Case 1: no block present -> NO-OP, core entry unaffected ──")
reset()
mk_blueprint("case1-noop")  # plain blueprint, no duality section
outcome = o._phase6_register_categories(book, "case1-noop", appendix_status="COMPLETE")
cats = read_cats()
entry = cats["personas"].get("case1-noop")
check(outcome == "ok", f"outcome == 'ok' (got {outcome!r})")
check(entry is not None and entry.get("domain"), "core domain[] present")
for f in ("audiences", "topics", "voice_style", "usable_as"):
    check(f not in entry, f"'{f}' NOT written when no block present")
check(o.pipeline_had_duality_tag_failures() is False, "no duality failure recorded (absence is not a failure)")

# ── Case 2: well-formed block, EMPTY vocab -> enriched clean ──────────────────
print("── Case 2: well-formed block + empty vocab -> entry enriched ──")
reset()  # audienceTags/topicTags default to []
mk_blueprint("case2-clean", duality_json={
    "audiences": ["small-business-owners"],
    "topics": ["direct-response-marketing"],
    "voice_style": {"summary": "Blunt, plain-spoken, pragmatic."},
    "usable_as": ["audience", "topic", "task"],
    # A-U3 (schema-1.4) scalar fields ride the SAME block:
    "emotional_register": "tough-love",
    "audience_resonance": "challenged-to-rise",
    "conversion_style": "challenge-close",
})
outcome = o._phase6_register_categories(book, "case2-clean", appendix_status="COMPLETE")
cats = read_cats()
entry = cats["personas"].get("case2-clean")
check(outcome == "ok", f"outcome == 'ok' (got {outcome!r})")
check(entry is not None and entry.get("audiences") == ["small-business-owners"], "audiences[] landed")
check(entry is not None and entry.get("topics") == ["direct-response-marketing"], "topics[] landed")
check(entry is not None and entry.get("voice_style", {}).get("summary") == "Blunt, plain-spoken, pragmatic.",
      "voice_style.summary landed")
check(entry is not None and entry.get("usable_as") == ["audience", "topic", "task"], "usable_as landed")
check(entry is not None and entry.get("emotional_register") == "tough-love", "emotional_register landed (A-U3)")
check(entry is not None and entry.get("audience_resonance") == "challenged-to-rise", "audience_resonance landed (A-U3)")
check(entry is not None and entry.get("conversion_style") == "challenge-close", "conversion_style landed (A-U3)")
check(o.pipeline_had_duality_tag_failures() is False, "no duality failure recorded on a clean enrich")

# ── Case 2b: A-U3 vocab-first — out-of-vocab emotional_register rejects the WHOLE block ──
print("── Case 2b: A-U3 vocab-first, emotional_register NOT a vocab member -> whole block rejected ──")
reset()  # empty vocab baseline, then hand-seed ONLY the schema-1.4 register vocab
_c = read_cats()
_c["emotionalRegisterTags"] = ["warm-encouragement"]  # does NOT include 'tough-love'
catpath.write_text(json.dumps(_c, indent=2))
mk_blueprint("case2b-badregister", duality_json={
    "audiences": [], "topics": ["direct-response-marketing"],
    "voice_style": {"summary": "x"},
    "emotional_register": "tough-love",  # not in the seeded emotionalRegisterTags
})
outcome = o._phase6_register_categories(book, "case2b-badregister", appendix_status="COMPLETE")
entry = read_cats()["personas"].get("case2b-badregister")
check(outcome == "ok", "core registration must survive a schema-1.4 rejection")
check(entry is not None and "emotional_register" not in entry, "emotional_register omitted after out-of-vocab rejection")
check(entry is not None and "topics" not in entry, "all-or-nothing: in-vocab topics[] also omitted")
check("case2b-badregister" in o._DUALITY_TAG_WRITE_FAILURES, "out-of-vocab register rejection recorded")

# ── Case 3: vocab-first — tag IS in a populated vocab -> passes ───────────────
print("── Case 3: vocab-first, tag IS a vocab member -> passes ──")
reset(audience_tags=["small-business-owners"], topic_tags=["direct-response-marketing"])
mk_blueprint("case3-invocab", duality_json={
    "audiences": ["small-business-owners"],
    "topics": ["direct-response-marketing"],
    "voice_style": {"summary": "x"},
})
o._phase6_register_categories(book, "case3-invocab", appendix_status="COMPLETE")
entry = read_cats()["personas"].get("case3-invocab")
check(entry is not None and entry.get("audiences") == ["small-business-owners"],
      "in-vocab audience tag accepted")

# ── Case 4: vocab-first — tag is NOT in a populated vocab -> rejected ─────────
print("── Case 4: vocab-first, tag NOT a vocab member -> rejected (core unaffected) ──")
reset(audience_tags=["some-other-audience"], topic_tags=["some-other-topic"])
mk_blueprint("case4-outofvocab", duality_json={
    "audiences": ["small-business-owners"],  # not in the seeded vocab
    "topics": ["direct-response-marketing"],  # not in the seeded vocab
    "voice_style": {"summary": "x"},
})
outcome = o._phase6_register_categories(book, "case4-outofvocab", appendix_status="COMPLETE")
cats = read_cats()
entry = cats["personas"].get("case4-outofvocab")
check(outcome == "ok", f"outcome still 'ok' — duality rejection never demotes core outcome (got {outcome!r})")
check(entry is not None and entry.get("domain"), "core domain[] still present (never-to-zero)")
for f in ("audiences", "topics", "voice_style", "usable_as"):
    check(f not in entry, f"'{f}' omitted after an out-of-vocab rejection")
check("case4-outofvocab" in o._DUALITY_TAG_WRITE_FAILURES, "folder recorded in _DUALITY_TAG_WRITE_FAILURES")
check(o.pipeline_had_duality_tag_failures() is True, "pipeline_had_duality_tag_failures() True after a rejection")
check("case4-outofvocab" not in o._CATEGORIES_WRITE_FAILURES,
      "duality rejection does NOT feed the (unrelated) PHASE6_CATEGORIES_EXIT_CODE accumulator")

# ── Case 5: malformed JSON in the block -> rejected, core unaffected ──────────
print("── Case 5: malformed JSON body -> rejected, core unaffected ──")
reset()
mk_blueprint("case5-badjson", raw_duality_text=(
    "## Duality Tags (Machine-Readable)\n\n```json\n{not valid json,,,}\n```"
))
outcome = o._phase6_register_categories(book, "case5-badjson", appendix_status="COMPLETE")
cats = read_cats()
entry = cats["personas"].get("case5-badjson")
check(outcome == "ok", "outcome still 'ok' on malformed JSON")
check(entry is not None and entry.get("domain"), "core domain[] still present")
check("audiences" not in entry, "no audiences[] written from malformed JSON")
check("case5-badjson" in o._DUALITY_TAG_WRITE_FAILURES, "malformed-JSON folder recorded")

# ── Case 6: heading present but NO fenced json block -> rejected ──────────────
print("── Case 6: heading with no ```json fence -> rejected ──")
reset()
mk_blueprint("case6-nofence", raw_duality_text=(
    "## Duality Tags (Machine-Readable)\n\nI forgot the fenced block.\n"
))
o._phase6_register_categories(book, "case6-nofence", appendix_status="COMPLETE")
entry = read_cats()["personas"].get("case6-nofence")
check(entry is not None and "audiences" not in entry, "no audiences[] written with no fence")
check("case6-nofence" in o._DUALITY_TAG_WRITE_FAILURES, "no-fence folder recorded")

# ── Case 7: usable_as has a non-enum value -> rejected ────────────────────────
print("── Case 7: usable_as non-enum value -> rejected ──")
reset()
mk_blueprint("case7-badenum", duality_json={
    "audiences": [], "topics": ["direct-response-marketing"],
    "voice_style": {"summary": "x"}, "usable_as": ["reader"],
})
o._phase6_register_categories(book, "case7-badenum", appendix_status="COMPLETE")
entry = read_cats()["personas"].get("case7-badenum")
check(entry is not None and "usable_as" not in entry, "usable_as omitted on a non-enum value")
check("case7-badenum" in o._DUALITY_TAG_WRITE_FAILURES, "bad-enum folder recorded")

# ── Case 8: voice_style present without required .summary -> rejected ─────────
print("── Case 8: voice_style.summary missing -> rejected ──")
reset()
mk_blueprint("case8-nosummary", duality_json={
    "audiences": [], "topics": [], "voice_style": {"tone": ["blunt"]},
})
o._phase6_register_categories(book, "case8-nosummary", appendix_status="COMPLETE")
entry = read_cats()["personas"].get("case8-nosummary")
check(entry is not None and "voice_style" not in entry, "voice_style omitted when summary is missing")
check("case8-nosummary" in o._DUALITY_TAG_WRITE_FAILURES, "missing-summary folder recorded")

# ── Case 9: defensive fallback when persona_blend isn't importable ────────────
print("── Case 9: persona_blend unavailable -> local structural fallback still gates ──")
reset()
_orig_avail = o._PERSONA_BLEND_AVAILABLE
o._PERSONA_BLEND_AVAILABLE = False
try:
    mk_blueprint("case9-fallback-bad", duality_json={"usable_as": ["reader"]})
    o._phase6_register_categories(book, "case9-fallback-bad", appendix_status="COMPLETE")
    entry = read_cats()["personas"].get("case9-fallback-bad")
    check(entry is not None and "usable_as" not in entry,
          "fallback structural check rejects a bad enum with persona_blend unavailable")

    mk_blueprint("case9-fallback-ok", duality_json={
        "audiences": ["x-audience"], "topics": ["x-topic"],
        "voice_style": {"summary": "ok"}, "usable_as": ["topic", "task"],
    })
    o._phase6_register_categories(book, "case9-fallback-ok", appendix_status="COMPLETE")
    entry = read_cats()["personas"].get("case9-fallback-ok")
    check(entry is not None and entry.get("audiences") == ["x-audience"],
          "fallback structural check accepts a well-formed block with persona_blend unavailable")
finally:
    o._PERSONA_BLEND_AVAILABLE = _orig_avail

# ── Case 10: multi-book aggregation ────────────────────────────────────────────
print("── Case 10: module-level accumulator aggregates >1 rejected folder ──")
reset(audience_tags=["in-vocab-audience"])
for slug in ("case10-a", "case10-b"):
    mk_blueprint(slug, duality_json={"audiences": ["not-in-vocab"], "topics": []})
    o._phase6_register_categories(book, slug, appendix_status="COMPLETE")
check(set(o._DUALITY_TAG_WRITE_FAILURES) == {"case10-a", "case10-b"},
      f"both rejected folders aggregated (got {o._DUALITY_TAG_WRITE_FAILURES})")

# ── Case 11: _synthesis_system() vocab injection ──────────────────────────────
print("── Case 11: _synthesis_system() dynamically injects the LIVE vocab ──")
reset(audience_tags=["small-business-owners"], topic_tags=["direct-response-marketing"])
prompt = o._synthesis_system()
_LIVE_MARKER = "(LIVE, read-only)"  # only the DYNAMIC injection uses this exact marker
check(_LIVE_MARKER in prompt, "dynamic vocab block present when vocab is populated")
check("small-business-owners" in prompt, "audienceTags member present in the injected prompt")
check("direct-response-marketing" in prompt, "topicTags member present in the injected prompt")
check("Duality Tags" in prompt, "template's own Duality Tags instructions are present")

reset()  # empty vocab
prompt_empty = o._synthesis_system()
check(_LIVE_MARKER not in prompt_empty,
      "dynamic vocab block OMITTED when audienceTags/topicTags are empty")
# NOTE: the static template's OWN worked example legitimately contains
# 'small-business-owners' as sample JSON — so we assert on the LIVE-only
# marker (above), not on tag-string absence, to avoid a false positive here.
check("Duality Tags" in prompt_empty,
      "template's own Duality Tags instructions still present with empty vocab")

# ── Case 11b: A-U3 — _synthesis_system() injects the schema-1.4 register vocab ──
print("── Case 11b: _synthesis_system() dynamically injects the LIVE schema-1.4 vocab ──")
reset()
_c = read_cats()
_c["emotionalRegisterTags"] = ["tough-love"]
_c["audienceResonanceTags"] = ["challenged-to-rise"]
_c["conversionStyleTags"] = ["challenge-close"]
catpath.write_text(json.dumps(_c, indent=2))
prompt_s14 = o._synthesis_system()
check(_LIVE_MARKER in prompt_s14, "dynamic schema-1.4 vocab block present when populated")
check("tough-love" in prompt_s14, "emotionalRegisterTags member present in the injected prompt")
check("challenged-to-rise" in prompt_s14, "audienceResonanceTags member present in the injected prompt")
check("challenge-close" in prompt_s14, "conversionStyleTags member present in the injected prompt")
check("Schema-1.4 Voice-Register Fields" in prompt_s14, "the new heading is present")

reset()  # empty vocab (including schema-1.4 fields)
prompt_s14_empty = o._synthesis_system()
# NOTE: the static template's OWN VOCAB-FIRST prose legitimately NAMES the
# heading "Schema-1.4 Voice-Register Fields — Current Controlled Vocabulary"
# (telling the model what to look for IF present) — exactly the same reason
# Case 11 above asserts on the LIVE-only marker rather than "Duality Tags —
# Current Controlled Vocabulary" bare text. Assert on the heading+marker
# COMBINED (only the dynamic injection emits both together).
check("Schema-1.4 Voice-Register Fields — Current Controlled Vocabulary (LIVE, read-only)"
      not in prompt_s14_empty,
      "schema-1.4 vocab block OMITTED when emotionalRegisterTags/audienceResonanceTags/"
      "conversionStyleTags are all empty")
check("Duality Tags" in prompt_s14_empty,
      "template's own Duality Tags instructions still present with empty vocab")

print(f"\n{'='*60}")
print(f"persona-duality-tags-pipeline: PASS={PASS} FAIL={FAIL}")
print(f"{'='*60}")
sys.exit(1 if FAIL else 0)
PY
rc=$?
if [ "$rc" -eq 0 ]; then
    echo "ALL PERSONA-DUALITY-TAGS PIPELINE TESTS PASSED"
else
    echo "PERSONA-DUALITY-TAGS PIPELINE TESTS FAILED (rc=$rc)"
fi
exit "$rc"
