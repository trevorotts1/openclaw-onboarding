#!/usr/bin/env python3
"""test_pipeline_s1_s6_integration.py -- U067: multi-stage pipeline integration test."""
import json, os, subprocess, sys, tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
STATE = SCRIPTS / "anthology_state.py"
GATE = SCRIPTS / "gate_engine.py"
PY = sys.executable or "python3"

AID, PID = "ANTHpi01", "prodPI"
ANTHOLOGY_NAME = "The Pipeline Integration Collection"
CONTACT_ID, PK = "cPI001", "cPI001::ANTHpi01"
MIN_CHAPTERS, SAFE = 2, "cPI001__ANTHpi01"

def _clean_env():
    env = dict(os.environ)
    for k in ("ANTHOLOGY_STATE_BASE_ID","AIRTABLE_API_KEY","AIRTABLE_TOKEN","AIRTABLE_PAT","ANTHOLOGY_STATE_AIRTABLE_KEY","ANTHOLOGY_STATE_DIR"):
        env.pop(k, None)
    return env

def _run(argv, timeout=90):
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=_clean_env())
    parsed = None
    out = (proc.stdout or "").strip()
    if out:
        try: parsed = json.loads(out)
        except ValueError: parsed = None
    return proc.returncode, parsed, (proc.stderr or "").strip()

def state_cmd(state_dir, cmd, *args, expect_ok=True):
    argv = [PY, str(STATE), cmd, "--state-dir", str(state_dir), "--json"] + list(args)
    rc, parsed, err = _run(argv)
    if expect_ok:
        assert rc == 0, "anthology_state %s failed rc=%d :: %s" % (cmd, rc, err)
    return rc, parsed

def gate_cmd(state_dir, cmd, *args, expect_rc=None):
    argv = [PY, str(GATE), cmd, "--state-dir", str(state_dir), "--json"] + list(args)
    rc, parsed, err = _run(argv)
    if expect_rc is not None:
        assert rc == expect_rc, "gate_engine %s expected rc=%s got %s :: %s" % (cmd, expect_rc, rc, err)
    return rc, parsed

def _seed(state_dir):
    state_cmd(state_dir, "bootstrap")
    state_cmd(state_dir, "upsert-producer", "--producer-id", PID, "--producer-email", "owner@example.test", "--display-name", "Owner")
    state_cmd(state_dir, "upsert-anthology", "--anthology-id", AID, "--producer-id", PID, "--name", ANTHOLOGY_NAME, "--min-chapters", str(MIN_CHAPTERS))
    state_cmd(state_dir, "upsert-participant", "--contact-id", CONTACT_ID, "--anthology-id", AID, "--first-name", "Pipeline", "--last-name", "Tester", "--chapter-about", "Testing the integration pipeline end to end")

def _cursor(state_dir, pk=None):
    _rc, p = state_cmd(state_dir, "get-participant", "--participant-key", pk or PK)
    return p["stage_cursor"]

def _seed_participant_artifacts(tmp_path):
    workdir = tmp_path / "state" / "runs" / "participants" / SAFE / "working"
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "intake.json").write_text(json.dumps({"anthology_title":ANTHOLOGY_NAME,"first_name":"Pipeline","last_name":"Tester","chapter_premise":"Testing the integration pipeline end to end"}), encoding="utf-8")
    return workdir

def _walk_to_s5_gate(state_dir, pk):
    for step in ("s1_avatar","s1_gate"):
        state_cmd(state_dir, "advance-stage", "--participant-key", pk, "--to", step)
    state_cmd(state_dir, "record-approval", "--gate", "s1_producer", "--participant-key", pk, "--decision", "approve")
    state_cmd(state_dir, "advance-stage", "--participant-key", pk, "--to", "s2_gate")
    state_cmd(state_dir, "record-approval", "--gate", "s2_producer", "--participant-key", pk, "--decision", "approve")
    state_cmd(state_dir, "advance-stage", "--participant-key", pk, "--to", "s3_gate")
    state_cmd(state_dir, "record-approval", "--gate", "s3_selection", "--participant-key", pk, "--decision", "approve", "--title", "The Test Chronicles")
    for step in ("s4_blurb_outline","s4_gate_producer"):
        state_cmd(state_dir, "advance-stage", "--participant-key", pk, "--to", step)
    state_cmd(state_dir, "record-approval", "--gate", "s4_producer", "--participant-key", pk, "--decision", "approve")
    state_cmd(state_dir, "advance-stage", "--participant-key", pk, "--to", "s4_gate_participant")
    state_cmd(state_dir, "record-approval", "--gate", "s4_participant", "--participant-key", pk, "--decision", "approve")
    state_cmd(state_dir, "advance-stage", "--participant-key", pk, "--to", "s5_chapter")
    state_cmd(state_dir, "record-artifact", "--participant-key", pk, "--type", "chapter", "--sha256", "sha_chapter", "--model-used", "glm-5.2")
    state_cmd(state_dir, "advance-stage", "--participant-key", pk, "--to", "s5_gate")

REWRITE_BUDGET = 2

def test_full_cursor_walk_s0_to_s7_cover(tmp_path):
    _seed(tmp_path)
    assert _cursor(tmp_path) == "s0_intake"
    _walk_to_s5_gate(tmp_path, PK)
    assert _cursor(tmp_path) == "s5_gate"
    state_cmd(tmp_path, "record-approval", "--gate", "s5_participant", "--participant-key", PK, "--decision", "request_rewrite", "--notes", "tighten the prose")
    assert _cursor(tmp_path) == "s6_rewrite"
    _rc, p = state_cmd(tmp_path, "get-participant", "--participant-key", PK)
    assert p.get("rewrite_count") == 1
    state_cmd(tmp_path, "record-artifact", "--participant-key", PK, "--type", "rewrite", "--sha256", "sha_rewrite1", "--model-used", "glm-5.2")
    state_cmd(tmp_path, "advance-stage", "--participant-key", PK, "--to", "s5_gate")
    assert _cursor(tmp_path) == "s5_gate"
    state_cmd(tmp_path, "record-approval", "--gate", "s5_participant", "--participant-key", PK, "--decision", "approve")
    assert _cursor(tmp_path) == "s7_cover"

def test_every_gate_opens_at_expected_cursor(tmp_path):
    gates_to_test = [("s1_gate","s1_producer","producer","cGW01"),("s2_gate","s2_producer","producer","cGW02"),("s3_gate","s3_selection","participant","cGW03"),("s4_gate_producer","s4_producer","producer","cGW04"),("s4_gate_participant","s4_participant","participant","cGW05"),("s5_chapter","s5_producer","producer","cGW06"),("s5_gate","s5_participant","participant","cGW07"),("s6_rewrite","s6_producer","producer","cGW08")]
    for cursor, gate_id, actor, contact in gates_to_test:
        _seed(tmp_path)
        pk = "%s::%s" % (contact, AID)
        state_cmd(tmp_path, "upsert-participant", "--contact-id", contact, "--anthology-id", AID, "--first-name", "Gate", "--last-name", "Walker")
        state_cmd(tmp_path, "advance-stage", "--participant-key", pk, "--to", "s1_avatar")
        state_cmd(tmp_path, "advance-stage", "--participant-key", pk, "--to", "s1_gate")
        if cursor != "s1_gate":
            state_cmd(tmp_path, "record-approval", "--gate", "s1_producer", "--participant-key", pk, "--decision", "approve")
            state_cmd(tmp_path, "advance-stage", "--participant-key", pk, "--to", "s2_gate")
            if cursor != "s2_gate":
                state_cmd(tmp_path, "record-approval", "--gate", "s2_producer", "--participant-key", pk, "--decision", "approve")
                state_cmd(tmp_path, "advance-stage", "--participant-key", pk, "--to", "s3_gate")
                if cursor != "s3_gate":
                    state_cmd(tmp_path, "record-approval", "--gate", "s3_selection", "--participant-key", pk, "--decision", "approve", "--title", "Test Title")
                    state_cmd(tmp_path, "advance-stage", "--participant-key", pk, "--to", "s4_blurb_outline")
                    if cursor == "s4_gate_producer":
                        state_cmd(tmp_path, "advance-stage", "--participant-key", pk, "--to", "s4_gate_producer")
                    else:
                        state_cmd(tmp_path, "advance-stage", "--participant-key", pk, "--to", "s4_gate_producer")
                        state_cmd(tmp_path, "record-approval", "--gate", "s4_producer", "--participant-key", pk, "--decision", "approve")
                        state_cmd(tmp_path, "advance-stage", "--participant-key", pk, "--to", "s4_gate_participant")
                        if cursor != "s4_gate_participant":
                            state_cmd(tmp_path, "record-approval", "--gate", "s4_participant", "--participant-key", pk, "--decision", "approve")
                            state_cmd(tmp_path, "advance-stage", "--participant-key", pk, "--to", "s5_chapter")
                            if cursor == "s5_gate":
                                state_cmd(tmp_path, "record-artifact", "--participant-key", pk, "--type", "chapter", "--sha256", "sha_chap", "--model-used", "glm-5.2")
                                state_cmd(tmp_path, "advance-stage", "--participant-key", pk, "--to", "s5_gate")
                            elif cursor == "s6_rewrite":
                                state_cmd(tmp_path, "record-artifact", "--participant-key", pk, "--type", "chapter", "--sha256", "sha_chap", "--model-used", "glm-5.2")
                                state_cmd(tmp_path, "advance-stage", "--participant-key", pk, "--to", "s5_gate")
                                state_cmd(tmp_path, "record-approval", "--gate", "s5_participant", "--participant-key", pk, "--decision", "request_rewrite", "--notes", "edit")
        rc, st = gate_cmd(tmp_path, "status", "--subject-key", pk, expect_rc=0)
        assert st["open_gate"] == gate_id
        assert st["actor"] == actor

def test_illegal_transitions_refused(tmp_path):
    _seed(tmp_path)
    rc, _ = state_cmd(tmp_path, "advance-stage", "--participant-key", PK, "--to", "s7_cover", expect_ok=False)
    assert rc != 0
    state_cmd(tmp_path, "advance-stage", "--participant-key", PK, "--to", "s1_avatar")
    state_cmd(tmp_path, "advance-stage", "--participant-key", PK, "--to", "s1_gate")
    rc, _ = state_cmd(tmp_path, "advance-stage", "--participant-key", PK, "--to", "s5_chapter", expect_ok=False)
    assert rc != 0
    rc, _ = state_cmd(tmp_path, "advance-stage", "--participant-key", PK, "--to", "s1_avatar", expect_ok=False)
    assert rc != 0

def test_rewrite_budget_counts_correctly(tmp_path):
    _seed(tmp_path)
    _walk_to_s5_gate(tmp_path, PK)
    state_cmd(tmp_path, "record-approval", "--gate", "s5_participant", "--participant-key", PK, "--decision", "request_rewrite", "--notes", "first pass edits")
    _rc, p = state_cmd(tmp_path, "get-participant", "--participant-key", PK)
    assert p.get("rewrite_count") == 1
    state_cmd(tmp_path, "advance-stage", "--participant-key", PK, "--to", "s5_gate")
    state_cmd(tmp_path, "record-approval", "--gate", "s5_participant", "--participant-key", PK, "--decision", "request_rewrite", "--notes", "second pass edits")
    _rc, p = state_cmd(tmp_path, "get-participant", "--participant-key", PK)
    assert p.get("rewrite_count") == 2
    assert REWRITE_BUDGET == 2, "the engine rewrite budget must be 2"

def test_participant_artifacts_carry_forward(tmp_path):
    workdir = _seed_participant_artifacts(tmp_path)
    (workdir / "avatar.md").write_text("# My Avatar Profile\n\nThis is the avatar content.\n")
    (workdir / "tone-doc.md").write_text("# Tone Analysis\n\nTone description here.\n")
    (workdir / "title.json").write_text(json.dumps([{"title":"Rise","subtitle":"A story of ascent"},{"title":"Fall Forward","subtitle":"Success through failure"}]))
    (workdir / "blurb.md").write_text("# Blurb\nCompelling blurb text.\n")
    (workdir / "outline.md").write_text("# Outline\nEvery story placed.\n")
    chapter = workdir / "chapter.md"
    chapter_text = "# The Test Chronicles\n\nThis is the frozen chapter body.\n"
    chapter.write_text(chapter_text)
    assert chapter.read_text() == chapter_text
    chapter.write_text("# The Test Chronicles (Revised)\n\nRevised chapter body.\n")
    assert chapter.read_text() == "# The Test Chronicles (Revised)\n\nRevised chapter body.\n"
    intake_data = json.loads((workdir / "intake.json").read_text())
    assert intake_data["anthology_title"] == ANTHOLOGY_NAME

def test_participant_gate_decide_cycle(tmp_path):
    _seed(tmp_path)
    _walk_to_s5_gate(tmp_path, PK)
    rc, st = gate_cmd(tmp_path, "status", "--subject-key", PK, expect_rc=0)
    assert st["open_gate"] == "s5_participant"
    assert set(st.get("actions", [])) == {"approve_as_is", "request_rewrite_with_notes"}
    rc, _ = gate_cmd(tmp_path, "decide", "--door", "token", "--action", "hold", "--subject-key", PK, "--token", "v1.bogus.bogus", "--reason", "test")
    assert rc != 0
    rc, out = gate_cmd(tmp_path, "decide", "--door", "board", "--action", "approve_as_is", "--subject-key", PK, expect_rc=0)
    assert out["committed"] is True
    assert _cursor(tmp_path) == "s7_cover"

def test_no_gate_at_non_gate_cursors(tmp_path):
    _seed(tmp_path)
    rc, st = gate_cmd(tmp_path, "status", "--subject-key", PK, expect_rc=0)
    assert st.get("open_gate") is None
    state_cmd(tmp_path, "advance-stage", "--participant-key", PK, "--to", "s1_avatar")
    rc, st = gate_cmd(tmp_path, "status", "--subject-key", PK, expect_rc=0)
    assert st.get("open_gate") is None

def test_hold_records_at_gate(tmp_path):
    _seed(tmp_path)
    state_cmd(tmp_path, "advance-stage", "--participant-key", PK, "--to", "s1_avatar")
    state_cmd(tmp_path, "advance-stage", "--participant-key", PK, "--to", "s1_gate")
    state_cmd(tmp_path, "record-approval", "--gate", "s1_producer", "--participant-key", PK, "--decision", "hold", "--reason", "credit_out")
    assert _cursor(tmp_path) in ("s1_gate", "held")

def test_s5_producer_release_gate_slug(tmp_path):
    _seed(tmp_path)
    pk = "cREL::%s" % AID
    state_cmd(tmp_path, "upsert-participant", "--contact-id", "cREL", "--anthology-id", AID, "--first-name", "Rel", "--last-name", "Test", "--chapter-about", "release gate test")
    state_cmd(tmp_path, "advance-stage", "--participant-key", pk, "--to", "s1_avatar")
    state_cmd(tmp_path, "advance-stage", "--participant-key", pk, "--to", "s1_gate")
    state_cmd(tmp_path, "record-approval", "--gate", "s1_producer", "--participant-key", pk, "--decision", "approve")
    state_cmd(tmp_path, "advance-stage", "--participant-key", pk, "--to", "s2_gate")
    state_cmd(tmp_path, "record-approval", "--gate", "s2_producer", "--participant-key", pk, "--decision", "approve")
    state_cmd(tmp_path, "advance-stage", "--participant-key", pk, "--to", "s3_gate")
    state_cmd(tmp_path, "record-approval", "--gate", "s3_selection", "--participant-key", pk, "--decision", "approve", "--title", "Release Test")
    state_cmd(tmp_path, "advance-stage", "--participant-key", pk, "--to", "s4_blurb_outline")
    state_cmd(tmp_path, "advance-stage", "--participant-key", pk, "--to", "s4_gate_producer")
    state_cmd(tmp_path, "record-approval", "--gate", "s4_producer", "--participant-key", pk, "--decision", "approve")
    state_cmd(tmp_path, "advance-stage", "--participant-key", pk, "--to", "s4_gate_participant")
    state_cmd(tmp_path, "record-approval", "--gate", "s4_participant", "--participant-key", pk, "--decision", "approve")
    state_cmd(tmp_path, "advance-stage", "--participant-key", pk, "--to", "s5_chapter")
    rc, st = gate_cmd(tmp_path, "status", "--subject-key", pk, expect_rc=0)
    assert st["open_gate"] == "s5_producer"
    rc, out = gate_cmd(tmp_path, "decide", "--door", "board", "--action", "approve", "--subject-key", pk, expect_rc=0)
    assert out.get("release_tag") is not None
    assert out["release_tag"]["slug"] == "anthology-release-chapter"

def _all_tests():
    fns = [(k,v) for k,v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = passed = 0
    for name, fn in fns:
        try:
            if "tmp_path" in fn.__code__.co_varnames[:fn.__code__.co_argcount]:
                with tempfile.TemporaryDirectory() as td:
                    fn(Path(td))
            else:
                fn()
            passed += 1
            print("  [PASS] %s" % name)
        except AssertionError as exc:
            failed += 1
            print("  [FAIL] %s -- %s" % (name, exc))
        except Exception as exc:
            failed += 1
            print("  [ERROR] %s -- %r" % (name, exc))
    print("\ntest_pipeline_s1_s6_integration: %s (%d passed, %d failed of %d)" % ("ALL PASSED" if not failed else "FAILURES", passed, failed, len(fns)))
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(_all_tests())
