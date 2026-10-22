#!/usr/bin/env python3
"""S75-W02-U4: typed saved-state migration and remeasurement consumers.

Directive sections 8.2, 8.5; findings D26, D33. Proves against the REAL
reader and the REAL state store (real SQLite files in a temp dir, no
network, no providers):
 1. Reader coverage: valid QC-record lists, empty lists, malformed records,
    unknown fields, older supported schemas and unknown versions each get an
    explicit typed outcome from the actual reader.
 2. Wrong object at a boundary is a typed error: no silent migration and no
    tag stripping -- the wrong document comes back byte-identical.
 3. Version migration goes through the canonical request builder only,
    preserving performance tags and approved meaning exactly and reporting
    every semantic difference requiring review; a recipe that lacks
    provider-envelope fields is NOT obsolete.
 4. Remeasure and rejudge paths make ZERO music-generation calls (the
    module's refused-generation counter stays put), reuse valid cached
    analysis, and rejudge reads saved measurements only.
 5. Cache keys carry audio hash + evaluator version + policy version +
    approved-plan revision; invalidation kills only obsolete
    measurement/acceptance receipts and their descendants, keeping
    unrelated approvals and valid media.
 6. Replayed messages and webhooks acknowledge the existing decision and do
    no duplicate work; after a restart the pending continuation queue
    resumes the SAME run with ONE continuation and no duplicate paid
    attempt.

Run: python3 scripts/core/test_state_store_s75w02u4.py
"""
import copy
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import state_store as ss                     # noqa: E402  (module under test)

FAILS = []
TMPDIRS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def raises(name, fn, exc, code=None, contains=None):
    """fn() must raise `exc` (optionally with .code / message fragment)."""
    try:
        fn()
    except exc as e:
        ok = True
        detail = repr(e)
        if code is not None and getattr(e, "code", None) != code:
            ok = False
            detail = "code=%r want %r" % (getattr(e, "code", None), code)
        if contains is not None and contains not in str(e):
            ok = False
            detail = "message %r lacks %r" % (str(e), contains)
        check(name, ok, detail)
        return e
    except Exception as e:                       # noqa: BLE001
        check(name, False, "raised %s: %s" % (type(e).__name__, e))
        return None
    check(name, False, "no %s raised" % exc.__name__)
    return None


def tmp_store():
    d = tempfile.mkdtemp(prefix="s75w02u4-")
    TMPDIRS.append(d)
    return ss.Store(os.path.join(d, "state.sqlite3")), d


def qc_rec_v2(**over):
    rec = {"check_id": "chk-1", "category": "duration",
           "artifact_hash": "h1", "plan_revision": "rev-7",
           "evaluator_version": "ev-1", "evidence_source": "take-measure",
           "applicability": "take", "measured": "pass", "severity": "info"}
    rec.update(over)
    return rec


def recipe_v2(**over):
    doc = {"schema": ss.DOC_RECIPE_INPUT, "version": 2, "run_id": "r1",
           "style_id": "story-rap", "length_s": 90,
           "performance_tags": ["emotional build", "rap verse"],
           "approved_lyrics": "line one\nline two",
           "request_digest": "sha256:orig"}
    doc.update(over)
    return doc


def recipe_v1(**over):
    doc = {"schema": ss.DOC_RECIPE_INPUT, "version": 1, "run_id": "r1",
           "style": "Story Rap", "seconds": 90,
           "tags": ["emotional build", "rap verse"],
           "lyrics": "line one\nline two"}
    doc.update(over)
    return doc


# --------------------------------------------------------------------------
# 1. Reader coverage: lists, empty lists, malformed, unknown, older schemas
# --------------------------------------------------------------------------

def test_reader_valid_lists():
    wrapped = {"schema": ss.DOC_QC_RECORDS, "version": 2,
               "records": [qc_rec_v2(), qc_rec_v2(check_id="chk-2")]}
    out = ss.read_qc_records(wrapped)
    check("valid list: wrapper reads", out["records"][0]["check_id"] == "chk-1"
          and len(out["records"]) == 2)
    bare = ss.read_qc_records([qc_rec_v2()])
    check("valid list: bare list reads", bare["records"][0]["measured"]
          == "pass" and bare["_source_version"] == 2)
    check("valid list: typed record fields kept",
          out["records"][0]["plan_revision"] == "rev-7"
          and out["records"][0]["evidence_source"] == "take-measure")


def test_reader_empty_lists():
    out = ss.read_qc_records([])
    check("empty list: bare [] accepted", out["records"] == [])
    out = ss.read_qc_records(
        {"schema": ss.DOC_QC_RECORDS, "version": 2, "records": []})
    check("empty list: wrapper with [] accepted", out["records"] == [])


def test_reader_malformed_records():
    e = raises("malformed: missing check_id -> MALFORMED_RECORD",
               lambda: ss.read_qc_records([{"category": "duration"}]),
               ss.MalformedRecordError, "MALFORMED_RECORD")
    if e is not None:
        check("malformed: names the failing record field", e.path
              == "records[0].check_id", "path=%r" % e.path)
    raises("malformed: non-object member -> MALFORMED_RECORD",
           lambda: ss.read_qc_records(["not-a-record"]),
           ss.MalformedRecordError, "MALFORMED_RECORD")
    raises("malformed: wrong-typed measured -> MALFORMED_RECORD",
           lambda: ss.read_qc_records(
               [qc_rec_v2(measured=["pass"])]),
           ss.MalformedRecordError, "MALFORMED_RECORD")
    raises("malformed: records not a list -> WRONG_SHAPE",
           lambda: ss.read_qc_records(
               {"schema": ss.DOC_QC_RECORDS, "version": 2,
                "records": {"a": 1}}),
           ss.WrongShapeError, "WRONG_SHAPE")
    raises("malformed: object doc missing version tag -> MALFORMED_RECORD",
           lambda: ss.read_execution_result(
               {"schema": ss.DOC_EXECUTION_RESULT, "run_id": "r1"}),
           ss.MalformedRecordError, "MALFORMED_RECORD")


def test_reader_unknown_fields():
    e = raises("unknown field: QC record field -> UNKNOWN_FIELD",
               lambda: ss.read_qc_records([qc_rec_v2(surprise=1)]),
               ss.UnknownFieldError, "UNKNOWN_FIELD")
    if e is not None:
        check("unknown field: error names the field",
              "surprise" in str(e), str(e))
    raises("unknown field: wrapper field -> UNKNOWN_FIELD",
           lambda: ss.read_qc_records(
               {"schema": ss.DOC_QC_RECORDS, "version": 2, "records": [],
                "extra": True}),
           ss.UnknownFieldError, "UNKNOWN_FIELD")
    raises("unknown field: recipe field -> UNKNOWN_FIELD",
           lambda: ss.read_recipe_input(recipe_v2(provider="kie")),
           ss.UnknownFieldError, "UNKNOWN_FIELD")


def test_reader_older_supported_schemas():
    out = ss.read_qc_records(
        {"schema": ss.DOC_QC_RECORDS, "version": 1,
         "records": [{"check_id": "chk-9", "category": "loudness",
                      "artifact_hash": "h9", "evaluator_version": "ev-0",
                      "result": "warn", "severity": "advisory"}]})
    check("older schema: v1 QC list reads", out["records"][0]["measured"]
          == "warn")
    check("older schema: v1 read is flagged migrated",
          out["_migrated"] is True and out["_source_version"] == 1)
    check("older schema: unknown v1 fields stay explicitly unknown",
          out["records"][0]["plan_revision"] is None
          and out["records"][0]["evidence_source"] is None)
    check("older schema: difference reported for review",
          out["_semantic_differences"]
          and out["_semantic_differences"][0]["code"]
          == "QC_FIELDS_REMAIN_UNKNOWN")
    out = ss.read_recipe_input(recipe_v1())
    check("older schema: v1 recipe reads with tags and meaning preserved",
          out["performance_tags"] == ["emotional build", "rap verse"]
          and out["approved_lyrics"] == "line one\nline two")
    out = ss.read_approved_lyric_sheet(
        {"schema": ss.DOC_APPROVED_LYRIC_SHEET, "version": 1,
         "run_id": "r1", "approval_id": "ap-1",
         "approved_at": "2026-10-22T00:00:00Z", "text": "a\nb"})
    check("older schema: v1 sheet meaning preserved line for line",
          out["lines"] == ["a", "b"])
    out = ss.read_provider_envelope(
        {"schema": ss.DOC_PROVIDER_ENVELOPE, "version": 1, "run_id": "r1",
         "provider": "kie", "task_id": "t-1", "status": "complete",
         "takes": [{"take_id": "k1", "path": "music/k1.mp3"}]})
    check("older schema: v1 envelope takes migrate path -> audio_path",
          out["takes"][0]["audio_path"] == "music/k1.mp3")
    out = ss.read_lane_plan(
        {"schema": ss.DOC_LANE_PLAN, "version": 1, "run_id": "r1",
         "song_length_s": 130.0, "lanes": 2,
         "lanes_detail": [
             {"lane_index": 0, "song_start": 0.0, "song_end": 65.0,
              "shots": ["s1", "s2"]},
             {"lane_index": 1, "song_start": 65.0, "song_end": 130.0,
              "shots": ["s3"]}]})
    check("older schema: v1 lane plan keeps every planned shot",
          out["lanes_detail"][0]["shot_ids"] == ["s1", "s2"])
    out = ss.read_execution_result(
        {"schema": ss.DOC_EXECUTION_RESULT, "version": 1, "run_id": "r1",
         "stage": "music", "outcome": "ok", "attempt": "att-1"})
    check("older schema: v1 execution result keeps attempt identity",
          out["attempt_id"] == "att-1")
    check("older schema: unreported counts stay reserved-unknown",
          "counts" not in out
          and any(d["code"] == "COUNTS_RESERVED_UNKNOWN"
                  for d in out["_semantic_differences"]))


def test_reader_unknown_versions():
    raises("unknown version: version 3 -> UNSUPPORTED_VERSION",
           lambda: ss.read_qc_records(
               {"schema": ss.DOC_QC_RECORDS, "version": 3, "records": []}),
           ss.UnsupportedVersionError, "UNSUPPORTED_VERSION")
    raises("unknown version: non-int tag -> MALFORMED_RECORD",
           lambda: ss.read_recipe_input(recipe_v2(version="2")),
           ss.MalformedRecordError, "MALFORMED_RECORD")
    raises("unknown version: missing schema tag -> MALFORMED_RECORD",
           lambda: ss.read_recipe_input({"version": 2, "run_id": "r1"}),
           ss.MalformedRecordError, "MALFORMED_RECORD")


# --------------------------------------------------------------------------
# 2. Wrong object at a boundary: typed error, no silent migration/tag loss
# --------------------------------------------------------------------------

def test_wrong_object_at_boundary():
    envelope = {"schema": ss.DOC_PROVIDER_ENVELOPE, "version": 2,
                "run_id": "r1", "provider": "kie", "task_id": "t-1",
                "status": "complete",
                "takes": [{"take_id": "k1", "audio_path": "music/k1.mp3",
                           "audio_hash": "h1"}]}
    snapshot = copy.deepcopy(envelope)
    e = raises("wrong object: provider envelope at recipe boundary -> "
               "WRONG_KIND",
               lambda: ss.read_recipe_input(envelope),
               ss.WrongKindError, "WRONG_KIND")
    check("wrong object: input document byte-identical (no silent "
          "migration, no tag stripping)", envelope == snapshot)
    check("wrong object: schema tag untouched",
          envelope["schema"] == ss.DOC_PROVIDER_ENVELOPE)
    if e is not None:
        check("wrong object: error names both kinds",
              ss.DOC_RECIPE_INPUT in str(e)
              and ss.DOC_PROVIDER_ENVELOPE in str(e), str(e))
    raises("wrong object: recipe at QC-list boundary -> WRONG_KIND",
           lambda: ss.read_qc_records(recipe_v2()),
           ss.WrongKindError, "WRONG_KIND")
    raises("wrong object: QC list at lane-plan boundary -> WRONG_SHAPE",
           lambda: ss.read_lane_plan([qc_rec_v2()]),
           ss.WrongShapeError, "WRONG_SHAPE")


def test_dict_only_helper_never_reads_lists():
    raises("dict-only helper refuses QC record list outright",
           lambda: ss.read_object(ss.DOC_QC_RECORDS, [qc_rec_v2()]),
           ss.WrongShapeError, "WRONG_SHAPE",
           contains="must never be asked to read a list of QC records")
    raises("dict-only kind reader refuses a list of QC records",
           lambda: ss.read_recipe_input([qc_rec_v2()]),
           ss.WrongShapeError, "WRONG_SHAPE",
           contains="must never be asked to read a list of QC records")
    raises("list-only helper refuses a single object kind",
           lambda: ss.read_list(ss.DOC_RECIPE_INPUT, recipe_v2()),
           ss.WrongShapeError, "WRONG_SHAPE")
    raises("list reader refuses an untagged dict-only document",
           lambda: ss.read_qc_records({"records": []}),
           ss.WrongShapeError, "WRONG_SHAPE")


def test_recipe_without_provider_fields_not_obsolete():
    doc = {"schema": ss.DOC_RECIPE_INPUT, "version": 1, "run_id": "r1",
           "style": "story-rap", "seconds": 90,
           "tags": ["emotional build"], "lyrics": "line one"}
    out = ss.read_recipe_input(doc)
    check("internal recipe lacking provider-envelope fields reads fine",
          out["style_id"] == "story-rap")
    report = ss.canonical_request_builder(ss.DOC_RECIPE_INPUT, doc)
    check("internal recipe lacking provider-envelope fields is not "
          "obsolete and migrates",
          report["migrated"]["version"] == 2
          and all(d["code"] != "OBSOLETE"
                  for d in report["semantic_differences"]))


# --------------------------------------------------------------------------
# 3. Migration through the canonical request builder (D26)
# --------------------------------------------------------------------------

def test_migration_preserves_tags_and_meaning():
    report = ss.canonical_request_builder(ss.DOC_RECIPE_INPUT, recipe_v1())
    migrated = report["migrated"]
    check("migration: performance tags preserved exactly, in order",
          migrated["performance_tags"] == ["emotional build", "rap verse"])
    check("migration: approved meaning preserved exactly",
          migrated["approved_lyrics"] == "line one\nline two")
    check("migration: derived digest reported for review",
          report["requires_review"] is True
          and any(d["code"] == "REQUEST_DIGEST_DERIVED"
                  for d in report["semantic_differences"]))
    report = ss.canonical_request_builder(
        ss.DOC_APPROVED_LYRIC_SHEET,
        {"schema": ss.DOC_APPROVED_LYRIC_SHEET, "version": 1,
         "run_id": "r1", "approval_id": "ap-1",
         "approved_at": "2026-10-22T00:00:00Z", "text": "a\nb"})
    check("migration: approved lyric sheet round-trips to its exact text",
          "\n".join(report["migrated"]["lines"]) == "a\nb"
          and report["requires_review"] is False)
    report = ss.migrate_document(ss.DOC_RECIPE_INPUT, recipe_v2())
    check("migration: current version passes through untouched",
          report["from_version"] == 2 and report["requires_review"] is False
          and report["migrated"]["request_digest"] == "sha256:orig")


def test_migration_reports_semantic_differences():
    report = ss.canonical_request_builder(
        ss.DOC_PROVIDER_ENVELOPE,
        {"schema": ss.DOC_PROVIDER_ENVELOPE, "version": 1, "run_id": "r1",
         "provider": "kie", "task_id": "t-1", "status": "complete",
         "takes": [{"take_id": "k1", "path": "music/k1.mp3"}]})
    check("migration: unknown audio hash reported, never invented",
          any(d["code"] == "AUDIO_HASH_UNKNOWN"
              for d in report["semantic_differences"])
          and report["migrated"]["takes"][0]["audio_hash"] is None)
    report = ss.canonical_request_builder(
        ss.DOC_EXECUTION_RESULT,
        {"schema": ss.DOC_EXECUTION_RESULT, "version": 1, "run_id": "r1",
         "stage": "music", "outcome": "ok", "attempt": "att-1"})
    check("migration: v1 execution counts reported reserved-unknown",
          any(d["code"] == "COUNTS_RESERVED_UNKNOWN"
              for d in report["semantic_differences"]))
    report = ss.canonical_request_builder(
        ss.DOC_LANE_PLAN,
        {"schema": ss.DOC_LANE_PLAN, "version": 1, "run_id": "r1",
         "song_length_s": 130.0, "lanes": 2,
         "lanes_detail": [
             {"lane_index": 0, "song_start": 0.0, "song_end": 65.0,
              "shots": ["s1"]},
             {"lane_index": 1, "song_start": 65.0, "song_end": 130.0,
              "shots": ["s2"]}]})
    check("migration: mechanical lane-plan rename needs no review",
          report["requires_review"] is False
          and report["migrated"]["lanes_detail"][1]["shot_ids"] == ["s2"])


def test_migration_never_strips_tags_or_meaning():
    before = recipe_v1()
    after = {"run_id": "r1", "style_id": "story-rap", "length_s": 90,
             "performance_tags": ["emotional build"],   # tag stripped
             "approved_lyrics": "line one\nline two"}
    raises("tag stripping -> SEMANTIC_LOSS",
           lambda: ss.verify_preserved(ss.DOC_RECIPE_INPUT, before, after),
           ss.SemanticLossError, "SEMANTIC_LOSS")
    after = dict(after, performance_tags=list(before["tags"]),
                 approved_lyrics="rewritten meaning")
    raises("approved-meaning rewrite -> SEMANTIC_LOSS",
           lambda: ss.verify_preserved(ss.DOC_RECIPE_INPUT, before, after),
           ss.SemanticLossError, "SEMANTIC_LOSS")
    ss.verify_preserved(ss.DOC_RECIPE_INPUT, before,
                        dict(after, approved_lyrics=before["lyrics"]))
    check("preservation proof passes when tags and meaning survive", True)


# --------------------------------------------------------------------------
# 4. Non-generating operations: validate, migrate, remeasure, rejudge,
#    reconcile -- zero music-generation calls (D26)
# --------------------------------------------------------------------------

def test_nongenerating_ops_registry():
    check("ops registry names all five non-generating operations",
          ss.NON_GENERATING_OPS == ("validate", "migrate", "remeasure",
                                    "rejudge", "reconcile"))
    st, _ = tmp_store()
    raises("unknown op -> UNKNOWN_OP",
           lambda: st.non_generating_op("generate"),
           ss.StoreError, "UNKNOWN_OP")
    res = st.non_generating_op("validate", kind=ss.DOC_RECIPE_INPUT,
                               doc=recipe_v2())
    check("validate op runs the real reader",
          res["ok"] is True and res["version"] == 2)
    report = st.non_generating_op("migrate", kind=ss.DOC_RECIPE_INPUT,
                                  doc=recipe_v1())
    check("migrate op routes through the canonical request builder",
          report["from_version"] == 1 and report["to_version"] == 2)
    st.close()


def test_remeasure_rejudge_zero_generation():
    st, _ = tmp_store()
    calls = {"measure": 0, "judge": 0}

    def measure(audio_hash, evaluator_version, provenance):
        calls["measure"] += 1
        return {"loudness_lufs": -14.0, "audio_hash": audio_hash,
                "provenance_task": provenance.get("task_id")}

    def judge(measurement):
        calls["judge"] += 1
        return {"verdict": "pass", "loudness_lufs":
                measurement["measurement"]["loudness_lufs"]}

    before = ss.generation_calls()
    m1 = st.non_generating_op(
        "remeasure", run_id="r1", stage="music", audio_hash="h1",
        evaluator_version="ev-1", policy_version="pol-1",
        plan_revision="rev-7", measure=measure,
        provenance={"task_id": "t-1", "provider": "kie"})
    check("remeasure: saved audio measured once",
          m1["cached"] is False and calls["measure"] == 1)
    m2 = st.non_generating_op(
        "remeasure", run_id="r1", stage="music", audio_hash="h1",
        evaluator_version="ev-1", policy_version="pol-1",
        plan_revision="rev-7", measure=measure,
        provenance={"task_id": "t-1", "provider": "kie"})
    check("remeasure: valid cached analysis reused, measure not re-run",
          m2["cached"] is True and calls["measure"] == 1)
    j1 = st.non_generating_op(
        "rejudge", run_id="r1", stage="music", audio_hash="h1",
        evaluator_version="ev-1", policy_version="pol-1",
        plan_revision="rev-7", judge=judge)
    check("rejudge: verdict computed from the saved measurement only",
          j1["receipt"]["verdict"]["verdict"] == "pass"
          and calls["judge"] == 1)
    check("remeasure+rejudge made ZERO music-generation calls",
          ss.generation_calls() == before,
          "generation counter moved %d -> %d"
          % (before, ss.generation_calls()))
    raises("rejudge without a measurement -> MISSING_MEASUREMENT",
           lambda: st.non_generating_op(
               "rejudge", run_id="r1", stage="music", audio_hash="h9",
               evaluator_version="ev-1", policy_version="pol-1",
               plan_revision="rev-7", judge=judge),
           ss.StoreError, "MISSING_MEASUREMENT")
    st.close()


def test_generation_forbidden_is_typed():
    st, _ = tmp_store()
    before = ss.generation_calls()

    def rogue_measure(audio_hash, evaluator_version, provenance):
        ss.request_generation("suno", "buy a new song")
        return {}

    raises("a generation attempt from a non-generating path -> "
           "GENERATION_FORBIDDEN",
           lambda: st.non_generating_op(
               "remeasure", run_id="r1", stage="music", audio_hash="h1",
               evaluator_version="ev-1", policy_version="pol-1",
               plan_revision="rev-7", measure=rogue_measure),
           ss.GenerationForbiddenError, "GENERATION_FORBIDDEN")
    check("refused generation attempt is counted",
          ss.generation_calls() == before + 1)
    check("rogue remeasure wrote no receipt",
          st.get_receipt("measurement", "h1", "ev-1", "pol-1", "rev-7")
          is None)
    st.close()


# --------------------------------------------------------------------------
# 5. Cache keys and scoped invalidation (8.5)
# --------------------------------------------------------------------------

def test_cache_key_components():
    key = ss.cache_key("measurement", "h1", "ev-1", "pol-1", "rev-7")
    check("cache key carries all four components",
          all(part in key for part in ("h1", "ev-1", "pol-1", "rev-7")))
    raises("cache key rejects a missing component",
           lambda: ss.cache_key("measurement", "", "ev-1", "pol-1", "rev-7"),
           ss.MalformedRecordError, "MALFORMED_RECORD")
    check("measurement and acceptance keys never collide",
          ss.cache_key("measurement", "h1", "ev-1", "pol-1", "rev-7")
          != ss.cache_key("acceptance", "h1", "ev-1", "pol-1", "rev-7"))


def test_receipt_save_idempotent():
    st, _ = tmp_store()
    a = st.save_receipt("r1", "music", "measurement", "h1", "ev-1",
                        "pol-1", "rev-7", {"m": 1})
    b = st.save_receipt("r1", "music", "measurement", "h1", "ev-1",
                        "pol-1", "rev-7", {"m": 2})
    check("receipt save is idempotent on the cache key",
          a["created"] is True and b["created"] is False
          and b["receipt"] == {"m": 1})
    st.close()


def test_invalidation_scoped():
    st, _ = tmp_store()
    k_ma = st.save_receipt("r1", "music", "measurement", "audioA", "ev-1",
                           "pol-1", "rev-1", {"m": 1})["cache_key"]
    k_ka = st.save_receipt("r1", "music", "acceptance", "audioA", "ev-1",
                           "pol-1", "rev-1", {"v": "pass"},
                           parent_key=k_ma)["cache_key"]
    k_apr1 = st.save_receipt("r1", "music", "approval", "audioA", "ev-1",
                             "pol-1", "rev-1", {"approved": True},
                             parent_key=k_ka)["cache_key"]
    k_med = st.save_receipt("r1", "music", "media", "audioA", "ev-1",
                            "pol-1", "rev-1",
                            {"file": "music/k1.mp3"})["cache_key"]
    k_mb = st.save_receipt("r1", "music", "measurement", "audioB", "ev-2",
                           "pol-1", "rev-1", {"m": 2})["cache_key"]
    k_apr2 = st.save_receipt("r1", "music", "approval", "audioB", "ev-2",
                             "pol-1", "rev-1", {"approved": True},
                             parent_key=k_mb)["cache_key"]
    # an approval from an OLDER plan revision, unrelated to the chain above:
    # approvals never age out on component drift, only as descendants
    k_apr3 = st.save_receipt("r1", "music", "approval", "audioA", "ev-1",
                             "pol-1", "rev-0", {"approved": True})["cache_key"]
    res = st.invalidate_receipts("r1", evaluator_version="ev-2")
    check("invalidation: obsolete measurement and acceptance die",
          set(res["invalidated"]) == {k_ma, k_ka}, str(res))
    check("invalidation: affected approval descendant dies",
          res["descendants"] == [k_apr1], str(res))
    check("invalidation: unrelated approvals and valid media survive",
          set(res["kept"]) == {k_med, k_mb, k_apr2, k_apr3}, str(res))
    check("invalidation: dead receipt reads absent",
          st.get_receipt("measurement", "audioA", "ev-1", "pol-1", "rev-1")
          is None)
    check("invalidation: current measurement and media still readable",
          st.get_receipt("measurement", "audioB", "ev-2", "pol-1", "rev-1")
          == {"m": 2}
          and st.get_receipt("media", "audioA", "ev-1", "pol-1", "rev-1")
          == {"file": "music/k1.mp3"})
    raises("invalidation without any current component is refused",
           lambda: st.invalidate_receipts("r1"),
           ss.MalformedRecordError, "MALFORMED_RECORD")
    st.close()


# --------------------------------------------------------------------------
# 6. Replay, webhook ack, restart resume (8.2)
# --------------------------------------------------------------------------

DECISION = {"answer": "keep_one", "approval_id": "ap-1"}


def test_replay_decision_acknowledges_no_duplicate_work():
    st, _ = tmp_store()
    first = st.record_decision(
        "r1", "msg-1", DECISION, stage="music", op="rejudge",
        request_digest="sha256:paid-1", attempt_id="att-1")
    check("decision: first delivery does the work",
          first["duplicate"] is False
          and first["continuation"]["attempt_id"] == "att-1")
    second = st.record_decision(
        "r1", "msg-1", DECISION, stage="music", op="rejudge",
        request_digest="sha256:paid-1", attempt_id="att-1")
    check("replay: acknowledged with the existing receipt",
          second["duplicate"] is True
          and second["receipt"] == first["receipt"])
    check("replay: returns the one existing continuation",
          second["continuation"]["id"] == first["continuation"]["id"]
          and second["continuation"]["attempt_id"] == "att-1")
    n_dec = st.con.execute(
        "SELECT COUNT(*) FROM decisions WHERE run_id='r1'").fetchone()[0]
    n_cont = st.con.execute(
        "SELECT COUNT(*) FROM continuations WHERE run_id='r1'").fetchone()[0]
    check("replay: one decision row, one continuation, one paid attempt",
          n_dec == 1 and n_cont == 1, "decisions=%d continuations=%d"
          % (n_dec, n_cont))
    st.close()


def test_webhook_replay_idempotent():
    st, _ = tmp_store()
    a = st.acknowledge_webhook(
        "r1", "wh-42", event_kind="provider.complete", stage="music",
        op="resume", request_digest="sha256:paid-2", attempt_id="att-2")
    b = st.acknowledge_webhook(
        "r1", "wh-42", event_kind="provider.complete", stage="music",
        op="resume", request_digest="sha256:paid-2", attempt_id="att-2")
    check("webhook replay: existing decision acknowledged, no duplicate",
          a["duplicate"] is False and b["duplicate"] is True
          and b["receipt"] == a["receipt"]
          and b["continuation"]["id"] == a["continuation"]["id"])
    n_cont = st.con.execute(
        "SELECT COUNT(*) FROM continuations WHERE run_id='r1'").fetchone()[0]
    check("webhook replay: still one continuation",
          n_cont == 1, "continuations=%d" % n_cont)
    st.close()


def test_restart_resumes_same_run_once():
    st, d = tmp_store()
    first = st.record_decision(
        "r1", "msg-1", DECISION, stage="music", op="rejudge",
        request_digest="sha256:paid-1", attempt_id="att-1")
    st.close()
    st = ss.Store(os.path.join(d, "state.sqlite3"))     # process restart
    pending = st.scan_pending_continuations("r1")
    check("restart: pending continuation queue holds the same one row",
          len(pending) == 1
          and pending[0]["request_digest"] == "sha256:paid-1"
          and pending[0]["attempt_id"] == "att-1")
    check("restart: existing receipt comes back unchanged",
          st.record_decision("r1", "msg-1", DECISION)["receipt"]
          == first["receipt"])
    resumed = st.resume_continuations("r1", "worker-2")
    check("restart: same run resumed with exactly one continuation",
          len(resumed) == 1
          and resumed[0]["id"] == first["continuation"]["id"]
          and resumed[0]["attempt_id"] == "att-1")
    again = st.resume_continuations("r1", "worker-2")
    check("restart: nothing to resume twice", again == [])
    n_paid = st.con.execute(
        "SELECT COUNT(*) FROM continuations WHERE run_id='r1'"
        " AND request_digest='sha256:paid-1'").fetchone()[0]
    attempts = {r[0] for r in st.con.execute(
        "SELECT attempt_id FROM continuations WHERE run_id='r1'")}
    check("restart: no duplicate paid attempts",
          n_paid == 1 and attempts == {"att-1"},
          "rows=%d attempts=%r" % (n_paid, attempts))
    rec = st.non_generating_op("reconcile", run_id="r1")
    check("reconcile op reports the queue read-only",
          rec["pending_continuations"] == [] and rec["decision_count"] == 1,
          str(rec))
    st.close()


# --------------------------------------------------------------------------
# 7. Legacy stage-store API stays intact (factory.py compatibility)
# --------------------------------------------------------------------------

def test_legacy_store_api_untouched():
    st, _ = tmp_store()
    st.init_run("r1", ["music"])
    row = st.get("r1", "music")
    check("legacy: init_run/get work", row["state"] == "NOT_STARTED")
    st.transition("r1", "music", "READY", "w1", expected_version=row["version"])
    row = st.claim("r1", "music", "w1", lease_s=60)
    check("legacy: transition/claim work", row["state"] == "RUNNING")
    row = st.transition("r1", "music", "COMPLETE", "w1",
                        expected_version=row["version"])
    check("legacy: complete clears the owner", row["owner"] is None)
    check("legacy: events recorded", len(st.events("r1")) >= 3)
    st.close()


TESTS = [
    test_reader_valid_lists,
    test_reader_empty_lists,
    test_reader_malformed_records,
    test_reader_unknown_fields,
    test_reader_older_supported_schemas,
    test_reader_unknown_versions,
    test_wrong_object_at_boundary,
    test_dict_only_helper_never_reads_lists,
    test_recipe_without_provider_fields_not_obsolete,
    test_migration_preserves_tags_and_meaning,
    test_migration_reports_semantic_differences,
    test_migration_never_strips_tags_or_meaning,
    test_nongenerating_ops_registry,
    test_remeasure_rejudge_zero_generation,
    test_generation_forbidden_is_typed,
    test_cache_key_components,
    test_receipt_save_idempotent,
    test_invalidation_scoped,
    test_replay_decision_acknowledges_no_duplicate_work,
    test_webhook_replay_idempotent,
    test_restart_resumes_same_run_once,
    test_legacy_store_api_untouched,
]


def main():
    for t in TESTS:
        try:
            t()
        except Exception as e:                          # noqa: BLE001
            check("%s raised" % t.__name__, False,
                  "%s: %s" % (type(e).__name__, e))
    for d in TMPDIRS:
        shutil.rmtree(d, ignore_errors=True)
    print("\n%d checks failed" % len(FAILS))
    if FAILS:
        for f in FAILS:
            print("  FAILED: %s" % f)
        return 1
    print("all %d S75-W02-U4 typed-state groups passed" % len(TESTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
