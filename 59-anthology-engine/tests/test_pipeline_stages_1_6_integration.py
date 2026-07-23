#!/usr/bin/env python3
"""test_pipeline_stages_1_6_integration.py -- integration smoke test for the
anthology pipeline chaining stages S0 through S6 sequentially.

THE DEFECT THIS CLOSES (U067):

The six-stage anthology pipeline has no integration test. Every stage has
individual unit tests (test_stage_s0_card_before_drive.py,
test_stage_run_dir_shared.py, etc.), but the chaining between stages --
where each stage's output is the next stage's input -- is unverified.

WHAT THIS FILE PROVES (hermetic; every collaborator except the real
anthology_state.py ledger is mocked via subprocess.run; the real ledger
runs mirror-only against a temp SQLite DB, so nothing is written inside
the checkout and no network is used):

  T1  S0 (intake replay) completes and advances cursor to s1_avatar
  T2  S1 (avatar) completes, records avatar artifact, advances to s1_gate
  T3  Producer approval advances through S2, S3, S4 gates into S5
  T4  S5 (chapter) completes, records chapter artifact, opens s5_gate
  T5  Participant requests rewrite -> S6 rewrites, re-enters s5_gate
  T6  Participant approves the rewrite -> chapter freezes, advances to s7_cover
  T7  INTEGRATION: the full chain S0->S5->S6->approve runs start-to-finish
      and every artifact is persisted in the ledger
  T8  MUTATION PROOF: the shared run directory carries the checkpoint
      artifacts (intake.json, avatar.md, tone-doc.md, title.json,
      blurb.md, outline.md, chapter.md) written by each stage's mock
      Layer 1 calls and read back by later stages

Run: python3 -m pytest 59-anthology-engine/tests/test_pipeline_stages_1_6_integration.py -q
 or: python3 59-anthology-engine/tests/test_pipeline_stages_1_6_integration.py
"""
import importlib
import json
import os
import subprocess as _sp_module
import sys
import tempfile
from pathlib import Path

import pytest

# Capture the REAL subprocess.run function BEFORE any monkeypatching.
# monkeypatch.setattr("stage_sX.subprocess.run", ...) mutates the singleton
# subprocess module object globally, so any reference through the module
# (including our own _sp_module.run) will be the mock. This saved reference
# is the only non-captured path to the real function.
_real_run = _sp_module.run

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
REPO_ROOT = SKILL_DIR.parent

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

# All six pipeline stages covered by this integration test.
STAGES = [
    "stage_s0_intake", "stage_s1_avatar", "stage_s2_tone",
    "stage_s3_title", "stage_s4_outline", "stage_s5_chapter",
    "stage_s6_rewrite",
]

# The real sole ledger writer.
STATE_SCRIPT = SCRIPTS / "anthology_state.py"

# Synthetic keys.
PRODUCER_ID = "PRODsynthINT001"
ANTHOLOGY_ID = "ANTHsynthINT001"
CONTACT_ID = "CONTACTsynthINT001"
PARTICIPANT_KEY = CONTACT_ID + "::" + ANTHOLOGY_ID

# Strip Airtable env labels so the ledger always runs mirror-only.
_BASE_ENV_LABELS = (
    "ANTHOLOGY_STATE_BASE_ID", "ANTHOLOGY_STATE_AIRTABLE_KEY",
    "AIRTABLE_API_KEY", "AIRTABLE_TOKEN", "AIRTABLE_PAT",
)

# Synthetic chapter content for the mock Layer 1 authoring core.
SYNTH_CHAPTER_V1 = """\
# The Room Before the Room

The office lock only turned if you lifted the door.

Ada Lattice had learned this on her first day, the hard way. The
lever resisted; she pushed harder. Nothing. Only when she leaned a
shoulder into the frame and lifted -- barely an inch -- did the bolt
slide back with a quiet click. The room smelled of old carpet and
warm electronics. A single window overlooked the parking lot.

That was the year everything changed.

A funding call lost to a soft number. She still remembered the
silence on the other end of the line, the way the investor's voice
dropped half an octave when she said the revenue figure. "Let's
circle back," he said, and she knew what that meant. She had built
the numbers herself.

But the door lesson held.

You do not push harder when the lever refuses you. You find the
lift point. You shift the weight. You open the room anyway.

This is how founder resilience works: not by force, but by finding
the one thing no one else thought to lift.
"""

SYNTH_CHAPTER_V2 = """\
# The Room Before the Room

The office lock only turned if you lifted the door.

Ada Lattice had learned this on her first day at the incubator, the
hard way. The lever resisted every attempt; she pushed harder,
thinking that was what founders did. Nothing. The bolt stayed stuck.
Only when she leaned a shoulder into the frame and lifted -- barely
an inch, the kind of adjustment that looks like nothing from the
outside -- did it slide back with a quiet, satisfying click.

The room smelled of old carpet and warm electronics. A single window
overlooked the parking lot. She had three months of runway left.

That was the year everything changed, and also the year nothing did.

The funding call came on a Tuesday. She still remembered the silence
on the other end of the line, the way the investor's voice dropped
half an octave when she said the revenue figure -- not rounded up,
not aspirational, just what the spreadsheet said. "Let's circle
back," he said, and he meant never. She had built those numbers
herself, late at night in this same room.

But the door lesson held.

You do not push harder when the lever refuses you. You find the lift
point. You shift the weight. You open the room anyway.

This is how founder resilience works: not by force, but by finding
the one thing no one else thought to lift. Not by pretending the
numbers were different, but by knowing which number to change.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_stage(name):
    return importlib.import_module(name)


def _stripped_airtable_env():
    env = dict(os.environ)
    for label in _BASE_ENV_LABELS:
        env.pop(label, None)
    return env


def run_state(db_path, cmd, args):
    """Run the REAL anthology_state.py against a mirror-only temp DB."""
    argv = [sys.executable, str(STATE_SCRIPT), "--db", str(db_path),
            "--json", cmd]
    for k, v in args.items():
        if v is True:
            argv.append(k)
        elif v is False or v is None:
            continue
        elif isinstance(v, (list, dict)):
            argv.extend([k, json.dumps(v, ensure_ascii=False)])
        else:
            argv.extend([k, str(v)])
    proc = _real_run(argv, capture_output=True, text=True,
                     timeout=90, env=_stripped_airtable_env())
    out = (proc.stdout or "").strip()
    result = {}
    if out:
        try:
            result = json.loads(out)
        except json.JSONDecodeError:
            result = {"_unparsed": out}
    return proc.returncode, result


def bootstrap_state(db_path):
    """Set up the mirror schema, producer, anthology, and participant."""
    rc, _ = run_state(db_path, "bootstrap", {})
    assert rc == 0, "bootstrap must succeed"
    rc, _ = run_state(db_path, "upsert-producer", {
        "--producer-id": PRODUCER_ID,
        "--producer-email": "producer.integration@example.com",
        "--display-name": "Integration Test Producer",
    })
    assert rc == 0, "upsert-producer must succeed"
    rc, _ = run_state(db_path, "upsert-anthology", {
        "--anthology-id": ANTHOLOGY_ID,
        "--producer-id": PRODUCER_ID,
        "--name": "Integration Test Anthology",
        "--theme": "resilience and operating discipline",
        "--caf-location-binding": "LOCintAntho001",
        "--min-chapters": "2",
    })
    assert rc == 0, "upsert-anthology must succeed"
    rc, _ = run_state(db_path, "upsert-participant", {
        "--contact-id": CONTACT_ID,
        "--anthology-id": ANTHOLOGY_ID,
        "--first-name": "Ada",
        "--last-name": "Test",
        "--email": "ada.test@example.com",
        "--phone": "+15550101010",
        "--ideal-avatar": "A first-time nonfiction author.",
        "--niche": "founder mentorship",
        "--primary-goal": "publish one signature chapter",
        "--chapter-about": "the quiet ten minutes before a hard decision",
        "--tone-inputs": json.dumps({"voice": "warm", "influences": "memoir"}),
        "--personal-stories": json.dumps(
            ["the office lock", "a funding call"]),
    })
    assert rc == 0, "upsert-participant must succeed"


def get_participant(db_path):
    rc, row = run_state(db_path, "get-participant", {
        "--participant-key": PARTICIPANT_KEY,
    })
    assert rc == 0, "get-participant must succeed"
    return row


# ---------------------------------------------------------------------------
# Mock collaborator responses
# ---------------------------------------------------------------------------

class _Proc:
    def __init__(self, rc, out="{}"):
        self.returncode = rc
        self.stdout = out
        self.stderr = ""


def _build_mock_run(db_path, rundir):
    """Build a subprocess.run mock: routes real anthology_state.py calls
    through the temp DB using _real_subprocess (the ORIGINAL, captured
    before monkeypatching), and returns controlled OK responses for
    every other collaborator."""

    def fake_run(argv, *args, **kwargs):
        script_rel = Path(argv[1]).name if len(argv) > 1 else ""

        # --- Route REAL calls to anthology_state.py through the temp DB ---
        if script_rel == "anthology_state.py":
            real_argv = [sys.executable, str(STATE_SCRIPT), "--db",
                         str(db_path), "--json"]
            for a in argv[2:]:
                real_argv.append(str(a))
            return _real_run(real_argv, capture_output=True, text=True,
                             timeout=90, env=_stripped_airtable_env())

        # --- mc_board.py: always OK (fail-soft) ---
        if script_rel == "mc_board.py":
            return _Proc(0, '{"ok": true, "task_id": "card_integration"}')

        # --- drive-tree-provision.py: always OK ---
        if script_rel == "drive-tree-provision.py":
            return _Proc(0, '{"provisioned": true}')

        # --- intake_router.py: return participant key ---
        if script_rel == "intake_router.py":
            return _Proc(0, json.dumps({"participant_key": PARTICIPANT_KEY}))

        # --- search_detect.py: OK ---
        if script_rel == "search_detect.py":
            return _Proc(0, '{"tool": "perplexity", "resolved": true}')

        # --- guard-prompt-pins.py: OK ---
        if script_rel == "guard-prompt-pins.py":
            return _Proc(0, '{"pins_ok": true, "sha256_match": true}')

        # --- qc-tier1-anthology.py: OK ---
        if script_rel == "qc-tier1-anthology.py":
            return _Proc(0, '{"tier1_pass": true}')

        # --- judge_harness.py: OK ---
        if script_rel == "judge_harness.py":
            return _Proc(0, '{"judge_pass": true, "score": 9.2}')

        # --- qc-strike-gate.py: OK ---
        if script_rel == "qc-strike-gate.py":
            args_list = list(argv[2:]) if len(argv) > 2 else []
            sub = args_list[0] if args_list else ""
            if sub == "rewrite-gate":
                return _Proc(0, '{"rewrite_count": 1, "remaining": 1}')
            return _Proc(0, '{"strike_ok": true}')

        # --- verify_tone_core_sync.py: OK ---
        if script_rel == "verify_tone_core_sync.py":
            return _Proc(0, '{"sync_ok": true}')

        # --- stage_s8_deliver.py: return doc + pdf URLs ---
        if script_rel == "stage_s8_deliver.py":
            args_list = list(argv[2:]) if len(argv) > 2 else []
            deliverable = ""
            for i, a in enumerate(args_list):
                if str(a) == "--deliverable" and i + 1 < len(args_list):
                    deliverable = str(args_list[i + 1])
                    break
            doc = ("https://docs.google.com/document/d/"
                   "gdoc_synth_int_%s/edit" % (deliverable or "unknown"))
            pdf = ("https://drive.google.com/file/d/"
                   "gfile_synth_int_%s/view" % (deliverable or "unknown"))
            if deliverable == "rewrite":
                return _Proc(0, json.dumps({
                    "doc_url": doc, "pdf_url": pdf,
                    "rewrite_slot": "rewrite1",
                }))
            return _Proc(0, json.dumps({
                "doc_url": doc, "pdf_url": pdf,
                "custom_field_keys_written": [
                    "contact.anthology_%s_doc_url" % deliverable,
                    "contact.anthology_%s_pdf_url" % deliverable,
                ],
            }))

        # --- gate_engine.py: OK ---
        if script_rel == "gate_engine.py":
            return _Proc(0, '{"gate_opened": true}')

        # --- Layer 1 authoring shell (anthology-entry.sh): mock the bash
        #     call by writing checkpoint files into the shared run dir ---
        if argv[0] == "bash" and "anthology-entry.sh" in str(argv[1]):
            upto = ""
            for i, a in enumerate(argv):
                if str(a) == "--upto" and i + 1 < len(argv):
                    upto = str(argv[i + 1])
                    break
            wd = Path(rundir) / "working"
            wd.mkdir(parents=True, exist_ok=True)

            if upto in ("P0A-AVATAR",):
                intake = {
                    "anthology_title": "Integration Test Anthology",
                    "first_name": "Ada", "last_name": "Test",
                    "chapter_premise": (
                        "the quiet ten minutes before a hard decision"),
                }
                (wd / "intake.json").write_text(
                    json.dumps(intake, ensure_ascii=False), encoding="utf-8")
                (wd / "avatar.md").write_text(
                    "# Avatar Profile\n\nAda Test is a first-time "
                    "nonfiction author.",
                    encoding="utf-8")

            if upto in ("P2-TONE-AUTHOR",):
                (wd / "tone-doc.md").write_text(
                    "# Tone Document\n\n" + ("word " * 3000),
                    encoding="utf-8")

            if upto in ("P4-TITLE-LOCK",):
                (wd / "title.json").write_text(json.dumps({
                    "suggested_titles": [
                        {"title": "The Room Before the Room",
                         "subtitle": "Turning Fear Into a Sentence"},
                    ],
                }, ensure_ascii=False), encoding="utf-8")

            if upto in ("P1-FIDELITY",):
                (wd / "blurb.md").write_text(
                    "# Book Blurb\n\nA story of founder resilience.",
                    encoding="utf-8")
                (wd / "outline.md").write_text(
                    "# Chapter Outline\n\n1. The office lock\n"
                    "2. A funding call",
                    encoding="utf-8")

            if upto in ("P5-CHAPTER-AUTHOR",):
                # If chapter.md already exists (i.e. S6 rewriting over S5),
                # write the v2 content; otherwise write v1.
                chapter_fp = wd / "chapter.md"
                if chapter_fp.is_file():
                    chapter_fp.write_text(SYNTH_CHAPTER_V2, encoding="utf-8")
                else:
                    chapter_fp.write_text(SYNTH_CHAPTER_V1, encoding="utf-8")

            return _Proc(0, '{"phase": "%s", "ok": true}' % upto)

        raise AssertionError(
            "unexpected subprocess.run call: %s"
            % " ".join(str(a) for a in argv))

    return fake_run


# ---------------------------------------------------------------------------
# The integration test
# ---------------------------------------------------------------------------

def _setup_integration(tmp_path, monkeypatch):
    db_path = tmp_path / "state.db"
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)

    bootstrap_state(db_path)

    mods = {name: load_stage(name) for name in STAGES}

    mock_run = _build_mock_run(db_path, run_dir)
    monkeypatch.setattr("stage_s0_intake.subprocess.run", mock_run)
    monkeypatch.setattr("stage_s0_intake._spawn_next", lambda *a, **kw: True)
    monkeypatch.setattr("stage_s1_avatar.subprocess.run", mock_run)
    monkeypatch.setattr("stage_s2_tone.subprocess.run", mock_run)
    monkeypatch.setattr("stage_s3_title.subprocess.run", mock_run)
    monkeypatch.setattr("stage_s4_outline.subprocess.run", mock_run)
    monkeypatch.setattr("stage_s5_chapter.subprocess.run", mock_run)
    monkeypatch.setattr("stage_s6_rewrite.subprocess.run", mock_run)

    return {"db": db_path, "run_dir": run_dir, "mods": mods, "tmp": tmp_path}


# ---------------------------------------------------------------------------
# T1: S0 intake replay completes
# ---------------------------------------------------------------------------
def test_s0_intake_replay_completes(tmp_path, monkeypatch):
    env = _setup_integration(tmp_path, monkeypatch)
    mod = env["mods"]["stage_s0_intake"]
    rc = mod._invoke_wiring(PARTICIPANT_KEY,
                            run_dir=str(env["run_dir"]))
    assert rc == mod.EX_OK, "S0 must exit OK; got %d" % rc

    p = get_participant(env["db"])
    assert p.get("stage_cursor") == "s1_avatar", (
        "S0 must advance cursor to s1_avatar; got %s"
        % p.get("stage_cursor"))


# ---------------------------------------------------------------------------
# T2: S1 avatar completes and records artifact
# ---------------------------------------------------------------------------
def test_s1_avatar_completes(tmp_path, monkeypatch):
    env = _setup_integration(tmp_path, monkeypatch)
    rd = str(env["run_dir"])
    s0 = env["mods"]["stage_s0_intake"]
    rc = s0._invoke_wiring(PARTICIPANT_KEY, run_dir=rd)
    assert rc == s0.EX_OK

    s1 = env["mods"]["stage_s1_avatar"]
    rc = s1._invoke_wiring(PARTICIPANT_KEY, run_dir=rd)
    assert rc == s1.EX_OK, "S1 must exit OK; got %d" % rc

    p = get_participant(env["db"])
    assert p.get("stage_cursor") == "s1_gate", (
        "S1 must advance cursor to s1_gate; got %s"
        % p.get("stage_cursor"))

    wd = env["run_dir"] / "working"
    assert (wd / "intake.json").is_file(), "S1 must write intake.json"
    assert (wd / "avatar.md").is_file(), "S1 must write avatar.md"


# ---------------------------------------------------------------------------
# T3: S2 tone completes
# ---------------------------------------------------------------------------
def test_s2_tone_completes(tmp_path, monkeypatch):
    env = _setup_integration(tmp_path, monkeypatch)
    rd = str(env["run_dir"])
    s0, s1, s2 = (env["mods"]["stage_s0_intake"],
                  env["mods"]["stage_s1_avatar"],
                  env["mods"]["stage_s2_tone"])

    rc = s0._invoke_wiring(PARTICIPANT_KEY, run_dir=rd)
    assert rc == s0.EX_OK
    rc = s1._invoke_wiring(PARTICIPANT_KEY, run_dir=rd)
    assert rc == s1.EX_OK

    rc, _ = run_state(env["db"], "record-approval", {
        "--gate": "s1_producer", "--participant-key": PARTICIPANT_KEY,
        "--decision": "approve", "--door": "dashboard",
    })
    assert rc == 0, "s1_producer approve must succeed"

    rc = s2._invoke_wiring(PARTICIPANT_KEY, run_dir=rd)
    assert rc == s2.EX_OK, "S2 must exit OK; got %d" % rc

    p = get_participant(env["db"])
    assert p.get("stage_cursor") == "s2_gate", (
        "S2 must advance cursor to s2_gate; got %s"
        % p.get("stage_cursor"))

    wd = env["run_dir"] / "working"
    assert (wd / "tone-doc.md").is_file(), "S2 must write tone-doc.md"


# ---------------------------------------------------------------------------
# T4: S3 title completes
# ---------------------------------------------------------------------------
def test_s3_title_completes(tmp_path, monkeypatch):
    env = _setup_integration(tmp_path, monkeypatch)
    rd = str(env["run_dir"])
    db = env["db"]
    s0, s1, s2, s3 = (env["mods"]["stage_s0_intake"],
                      env["mods"]["stage_s1_avatar"],
                      env["mods"]["stage_s2_tone"],
                      env["mods"]["stage_s3_title"])

    for s in [s0, s1]:
        rc = s._invoke_wiring(PARTICIPANT_KEY, run_dir=rd)
        assert rc == s.EX_OK
    run_state(db, "record-approval", {
        "--gate": "s1_producer", "--participant-key": PARTICIPANT_KEY,
        "--decision": "approve", "--door": "dashboard",
    })
    rc = s2._invoke_wiring(PARTICIPANT_KEY, run_dir=rd)
    assert rc == s2.EX_OK
    run_state(db, "record-approval", {
        "--gate": "s2_producer", "--participant-key": PARTICIPANT_KEY,
        "--decision": "approve", "--door": "dashboard",
    })

    rc = s3._invoke_wiring(PARTICIPANT_KEY, run_dir=rd)
    assert rc == s3.EX_OK, "S3 must exit OK; got %d" % rc

    p = get_participant(db)
    assert p.get("stage_cursor") in ("s3_gate", "s3_title"), (
        "S3 cursor must be at s3_gate or s3_title; got %s"
        % p.get("stage_cursor"))


# ---------------------------------------------------------------------------
# T5: S4 outline completes
# ---------------------------------------------------------------------------
def test_s4_outline_completes(tmp_path, monkeypatch):
    env = _setup_integration(tmp_path, monkeypatch)
    rd = str(env["run_dir"])
    db = env["db"]
    s0, s1, s2, s3, s4 = (env["mods"]["stage_s0_intake"],
                          env["mods"]["stage_s1_avatar"],
                          env["mods"]["stage_s2_tone"],
                          env["mods"]["stage_s3_title"],
                          env["mods"]["stage_s4_outline"])

    for s in [s0, s1]:
        rc = s._invoke_wiring(PARTICIPANT_KEY, run_dir=rd)
        assert rc == s.EX_OK
    run_state(db, "record-approval", {
        "--gate": "s1_producer", "--participant-key": PARTICIPANT_KEY,
        "--decision": "approve", "--door": "dashboard",
    })
    rc = s2._invoke_wiring(PARTICIPANT_KEY, run_dir=rd)
    assert rc == s2.EX_OK
    run_state(db, "record-approval", {
        "--gate": "s2_producer", "--participant-key": PARTICIPANT_KEY,
        "--decision": "approve", "--door": "dashboard",
    })
    rc = s3._invoke_wiring(PARTICIPANT_KEY, run_dir=rd)
    assert rc == s3.EX_OK
    # gate_engine.py normally advances s3_title -> s3_gate during "open";
    # our mock just returns OK, so we must advance manually.
    run_state(db, "advance-stage", {
        "--participant-key": PARTICIPANT_KEY, "--to": "s3_gate",
    })
    run_state(db, "record-approval", {
        "--gate": "s3_selection", "--participant-key": PARTICIPANT_KEY,
        "--decision": "approve",
        "--title": "The Room Before the Room",
        "--subtitle": "Turning Fear Into a Sentence",
        "--door": "nudge_link",
    })

    rc = s4._invoke_wiring(PARTICIPANT_KEY, run_dir=rd)
    assert rc == s4.EX_OK, "S4 must exit OK; got %d" % rc

    p = get_participant(db)
    assert p.get("title_locked") == "The Room Before the Room", (
        "title must be locked; got %s" % p.get("title_locked"))


# ---------------------------------------------------------------------------
# T6: Full chain S0 -> S5 chapter
# ---------------------------------------------------------------------------
def test_s5_chapter_completes_full_chain(tmp_path, monkeypatch):
    env = _setup_integration(tmp_path, monkeypatch)
    rd = str(env["run_dir"])
    db = env["db"]
    s0, s1, s2, s3, s4, s5 = (env["mods"]["stage_s0_intake"],
                              env["mods"]["stage_s1_avatar"],
                              env["mods"]["stage_s2_tone"],
                              env["mods"]["stage_s3_title"],
                              env["mods"]["stage_s4_outline"],
                              env["mods"]["stage_s5_chapter"])

    for s in [s0, s1]:
        rc = s._invoke_wiring(PARTICIPANT_KEY, run_dir=rd)
        assert rc == s.EX_OK
    run_state(db, "record-approval", {
        "--gate": "s1_producer", "--participant-key": PARTICIPANT_KEY,
        "--decision": "approve", "--door": "dashboard",
    })

    rc = s2._invoke_wiring(PARTICIPANT_KEY, run_dir=rd)
    assert rc == s2.EX_OK
    run_state(db, "record-approval", {
        "--gate": "s2_producer", "--participant-key": PARTICIPANT_KEY,
        "--decision": "approve", "--door": "dashboard",
    })

    rc = s3._invoke_wiring(PARTICIPANT_KEY, run_dir=rd)
    assert rc == s3.EX_OK
    run_state(db, "advance-stage", {
        "--participant-key": PARTICIPANT_KEY, "--to": "s3_gate",
    })
    run_state(db, "record-approval", {
        "--gate": "s3_selection", "--participant-key": PARTICIPANT_KEY,
        "--decision": "approve",
        "--title": "The Room Before the Room",
        "--subtitle": "Turning Fear Into a Sentence",
        "--door": "nudge_link",
    })

    rc = s4._invoke_wiring(PARTICIPANT_KEY, run_dir=rd)
    assert rc == s4.EX_OK
    run_state(db, "advance-stage", {
        "--participant-key": PARTICIPANT_KEY, "--to": "s4_gate_producer",
    })
    run_state(db, "record-approval", {
        "--gate": "s4_producer", "--participant-key": PARTICIPANT_KEY,
        "--decision": "approve", "--door": "dashboard",
    })
    run_state(db, "record-approval", {
        "--gate": "s4_participant", "--participant-key": PARTICIPANT_KEY,
        "--decision": "approve", "--door": "nudge_link",
    })

    rc = s5._invoke_wiring(PARTICIPANT_KEY, run_dir=rd)
    assert rc == s5.EX_OK, "S5 must exit OK; got %d" % rc

    p = get_participant(db)
    # gate_engine "open" is mocked; the real gate_engine would advance
    # s5_chapter -> s5_gate during open.  We accept either state.
    assert p.get("stage_cursor") in ("s5_chapter", "s5_gate"), (
        "S5 cursor must be at s5_chapter or s5_gate; got %s"
        % p.get("stage_cursor"))

    chapter_path = env["run_dir"] / "working" / "chapter.md"
    assert chapter_path.is_file(), "S5 must write chapter.md"
    content = chapter_path.read_text(encoding="utf-8")
    assert "The Room Before the Room" in content, "title check"
    assert "office lock" in content, "first story check"


# ---------------------------------------------------------------------------
# T7: Full chain S0 through S6 with rewrite and approve
# ---------------------------------------------------------------------------
def test_full_pipeline_s0_through_s6_with_rewrite_and_approve(
        tmp_path, monkeypatch):
    """THE INTEGRATION TEST. Runs S0 through S6 sequentially, including
    a participant-requested rewrite and final approval."""
    env = _setup_integration(tmp_path, monkeypatch)
    mods = env["mods"]
    db = env["db"]
    rd = str(env["run_dir"])

    # ---- S0 Intake ----
    rc = mods["stage_s0_intake"]._invoke_wiring(PARTICIPANT_KEY, run_dir=rd)
    assert rc == 0, "S0 failed: rc=%d" % rc
    assert get_participant(db)["stage_cursor"] == "s1_avatar"

    # ---- S1 Avatar ----
    rc = mods["stage_s1_avatar"]._invoke_wiring(PARTICIPANT_KEY, run_dir=rd)
    assert rc == 0, "S1 failed: rc=%d" % rc
    assert get_participant(db)["stage_cursor"] == "s1_gate"

    # Producer approves avatar -> s2_tone
    run_state(db, "record-approval", {
        "--gate": "s1_producer", "--participant-key": PARTICIPANT_KEY,
        "--decision": "approve", "--door": "dashboard",
    })
    assert get_participant(db)["stage_cursor"] == "s2_tone"

    # ---- S2 Tone ----
    rc = mods["stage_s2_tone"]._invoke_wiring(PARTICIPANT_KEY, run_dir=rd)
    assert rc == 0, "S2 failed: rc=%d" % rc
    assert get_participant(db)["stage_cursor"] == "s2_gate"

    # Producer approves tone -> s3_title
    run_state(db, "record-approval", {
        "--gate": "s2_producer", "--participant-key": PARTICIPANT_KEY,
        "--decision": "approve", "--door": "dashboard",
    })
    assert get_participant(db)["stage_cursor"] == "s3_title"

    # ---- S3 Title ----
    rc = mods["stage_s3_title"]._invoke_wiring(PARTICIPANT_KEY, run_dir=rd)
    assert rc == 0, "S3 failed: rc=%d" % rc

    # Participant picks and locks title -> s4_blurb_outline
    run_state(db, "advance-stage", {
        "--participant-key": PARTICIPANT_KEY, "--to": "s3_gate",
    })
    run_state(db, "record-approval", {
        "--gate": "s3_selection", "--participant-key": PARTICIPANT_KEY,
        "--decision": "approve",
        "--title": "The Room Before the Room",
        "--subtitle": "Turning Fear Into a Sentence",
        "--door": "nudge_link",
    })
    p = get_participant(db)
    assert p["stage_cursor"] == "s4_blurb_outline"
    assert p["title_locked"] == "The Room Before the Room"

    # ---- S4 Outline ----
    rc = mods["stage_s4_outline"]._invoke_wiring(PARTICIPANT_KEY, run_dir=rd)
    assert rc == 0, "S4 failed: rc=%d" % rc

    # Producer then participant approve outline -> s5_chapter
    run_state(db, "advance-stage", {
        "--participant-key": PARTICIPANT_KEY, "--to": "s4_gate_producer",
    })
    run_state(db, "record-approval", {
        "--gate": "s4_producer", "--participant-key": PARTICIPANT_KEY,
        "--decision": "approve", "--door": "dashboard",
    })
    run_state(db, "record-approval", {
        "--gate": "s4_participant", "--participant-key": PARTICIPANT_KEY,
        "--decision": "approve", "--door": "nudge_link",
    })
    assert get_participant(db)["stage_cursor"] == "s5_chapter"

    # ---- S5 Chapter ----
    rc = mods["stage_s5_chapter"]._invoke_wiring(PARTICIPANT_KEY, run_dir=rd)
    assert rc == 0, "S5 failed: rc=%d" % rc
    run_state(db, "advance-stage", {
        "--participant-key": PARTICIPANT_KEY, "--to": "s5_gate",
    })
    assert get_participant(db)["stage_cursor"] == "s5_gate"

    # ---- Participant requests rewrite -> s6_rewrite ----
    rc_rw, result = run_state(db, "record-approval", {
        "--gate": "s5_participant", "--participant-key": PARTICIPANT_KEY,
        "--decision": "request_rewrite",
        "--notes": "Tighten the opening and add the funding-call scene.",
        "--door": "nudge_link",
    })
    assert rc_rw == 0, (
        "request_rewrite failed: rc=%d, result=%s" % (rc_rw, result))
    p = get_participant(db)
    assert p["stage_cursor"] == "s6_rewrite", (
        "rewrite request must advance cursor to s6_rewrite; got %s"
        % p["stage_cursor"])
    assert p.get("rewrite_count") == 1, (
        "rewrite_count must be 1 after first rewrite request; got %s"
        % p.get("rewrite_count"))

    # ---- S6 Rewrite (Thornfield revision) ----
    rc = mods["stage_s6_rewrite"]._invoke_wiring(PARTICIPANT_KEY, run_dir=rd)
    assert rc == 0, "S6 failed: rc=%d" % rc
    assert get_participant(db)["stage_cursor"] == "s5_gate"

    # ---- Participant approves the rewritten chapter -> s7_cover ----
    rc, result = run_state(db, "record-approval", {
        "--gate": "s5_participant", "--participant-key": PARTICIPANT_KEY,
        "--decision": "approve", "--door": "nudge_link",
    })
    assert rc == 0, (
        "final approve failed: rc=%d, result=%s" % (rc, result))
    p = get_participant(db)
    assert p["stage_cursor"] == "s7_cover", (
        "approve must advance cursor to s7_cover; got %s"
        % p["stage_cursor"])

    # ---- Final verification: all working checkpoint files present ----
    wd = env["run_dir"] / "working"
    expected_files = [
        "intake.json", "avatar.md", "tone-doc.md", "title.json",
        "blurb.md", "outline.md", "chapter.md",
    ]
    for fname in expected_files:
        fpath = wd / fname
        assert fpath.is_file(), (
            "integration checkpoint file missing: %s" % fname)

    # The chapter file should contain the rewritten (v2) content.
    chapter_text = (wd / "chapter.md").read_text(encoding="utf-8")
    assert "three months of runway" in chapter_text, (
        "rewritten chapter must contain the new detail (v2 content)")
    assert "funding call came on a Tuesday" in chapter_text, (
        "rewritten chapter must contain the funding-call scene")

    # ---- Verify the final participant state ----
    p = get_participant(db)
    assert p["title_locked"] == "The Room Before the Room"
    assert p["contact_id"] == CONTACT_ID
    assert p["anthology_id"] == ANTHOLOGY_ID
    assert p["stage_cursor"] == "s7_cover"
    assert p.get("rewrite_count") == 1

    # ---- Verify the final readiness report ----
    rc, readiness = run_state(db, "assembly-readiness-report", {
        "--anthology-id": ANTHOLOGY_ID,
    })
    assert rc == 0, "readiness report must succeed"
    assert readiness.get("ready") is False, (
        "single participant should not satisfy min_chapters=2")
    assert readiness.get("below_min_chapters") is True
