"""FIX-PLAN Item 33b: the Skill 38 conversational layer, presentations side.

WHAT IS BEING PINNED. Item 33b wires Skill 38's conversational machinery
into exactly three human-facing seams of the presentation pipeline, with
Skill 51's gated intake explicitly out of scope:

  PARK SURFACES -- each park class produces the correct client surface:
  client_action parks produce a plain-words client message built ONLY
  from Item 10's client-safe park record (label / needed / waiting_on);
  operator_action and transient_infra parks produce NO client message
  (the client is never told a wait is theirs when it is not), and the
  raw blocked reason appears in no client-facing artifact.

  REPLY ROUTING -- a qualified client reply produces EXACTLY ONE resume
  signal, through the sanctioned writer for that need: the style pick
  through deck-intake-driver.py --style-pick plus one dispatch of the
  existing launcher resume argv; the resource-plan answer through
  capacity.record_plan_answer, whose locked profile entry is the signal
  auto_resume's known-plan fall-through honors. Unqualified replies
  (bad pick, unknown tier, a kind with no sanctioned writer, a reply to
  a run that is not parked) produce NO signal. Duplicate message ids
  never route twice.

  FRONT DOOR -- the hand-off token carries NO intake answers (closed
  key set, answer-shaped keys refused) and the layer writes no intake
  state of its own.

  DELIVERY -- the follow-up brief is composed only from a VERIFIED
  delivery record; an unverified delivery refuses.

  AGREEMENT -- the Skill 38 doctrine file, the department templates, and
  this module's constants name the same seams, classes, files, and
  literals (doctrine text and code agree).

EVERY LEG IS OFFLINE: scratch run dirs, a stub notify transport, a fake
resume dispatch where the launcher itself is not the subject. The style
pick legs run the REAL driver CLI (the sanctioned writer) as a
subprocess, the same way the adapter does.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent  # .../presentations/scripts
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import conversation_layer as cl  # noqa: E402
from presentation_job import resource_profile as rp  # noqa: E402

REPO_ROOT = _SCRIPTS_DIR.parents[4]
SKILL38_PROTOCOL = (REPO_ROOT / "38-conversational-ai-system" / "protocols"
                    / "presentations-conversational-layer-protocol.md")

RAW_REASON_TOKEN = "ZZRAWREASONZZ"

CLIENT_PARK = {
    "park_class": "client_action",
    "label": "Waiting for you",
    "waiting_on": "client",
    "needed": ("We need your style pick: reply A, B or C for the style "
               "samples you were sent. The deck continues as soon as "
               "you pick."),
    "phase": "P-STYLE-PICK",
    "since": "2026-10-14T00:00:00+00:00",
    "recorded_at": "2026-10-14T00:01:00+00:00",
    "auto_resume": False,
    "by": "presentation_job.auto_resume",
}


def make_run(tmp_path: Path, *, terminal: str = "BLOCKED",
             park: dict | None = CLIENT_PARK,
             phase: str = "P-STYLE-PICK", name: str = "run-33b",
             extra: dict | None = None) -> Path:
    run_dir = tmp_path / name
    run_dir.mkdir(parents=True, exist_ok=True)
    state = {"job_id": "pj_33b", "run_dir": str(run_dir),
             "terminal": terminal, "phases": [],
             "requester": {"chat_id": "4242"}}
    if terminal == "BLOCKED":
        state["blocked"] = {"phase": phase,
                            "reason": f"internal detail {RAW_REASON_TOKEN}",
                            "at": "2026-10-14T00:00:00+00:00"}
    if park is not None:
        state["park_status"] = park
    if extra:
        state.update(extra)
    (run_dir / "state.json").write_text(json.dumps(state, indent=2))
    return run_dir


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def receipts(run_dir: Path) -> list:
    doc = read_json(run_dir / "conversation-receipt.json")
    return doc["records"]


# ---------------------------------------------------------------------------
# Park surfaces: one class, one correct client surface
# ---------------------------------------------------------------------------

def test_client_action_park_produces_a_plain_words_brief(tmp_path):
    run = make_run(tmp_path)
    result = cl.park_notice(run, layer_available=True)
    assert result["status"] == "brief_issued"
    brief = read_json(run / "conversation-brief.json")
    assert brief["seam"] == "park-notice"
    message = brief["copy_points"]["client_message"]
    assert CLIENT_PARK["needed"] in message
    assert RAW_REASON_TOKEN not in json.dumps(brief)
    for token in cl.FORBIDDEN_CLIENT_TOKENS:
        assert token not in message
    assert receipts(run)[-1]["outcome"] == "brief_issued"


@pytest.mark.parametrize("park_class,label,waiting_on", [
    ("operator_action", "Waiting for our team", "operator"),
    ("transient_infra", "Paused by a temporary problem, retrying on its own",
     "system"),
])
def test_other_classes_are_silent_to_the_client(tmp_path, park_class, label,
                                                waiting_on):
    park = {**CLIENT_PARK, "park_class": park_class, "label": label,
            "waiting_on": waiting_on,
            "needed": "Nothing is needed from you."}
    run = make_run(tmp_path, park=park)
    result = cl.park_notice(run, layer_available=True)
    assert result["status"] == "client_silent"
    assert not (run / "conversation-brief.json").exists()
    assert receipts(run)[-1]["outcome"] == "client_silent"


def test_fallback_notify_when_the_layer_is_unavailable(tmp_path):
    run = make_run(tmp_path)
    sent = []
    result = cl.park_notice(
        run, layer_available=False,
        dispatch_fn=lambda chat, kind, msg: sent.append((chat, kind, msg)) or True)
    assert result["status"] == "fallback_notify"
    assert result["delivered"] is True
    assert sent and sent[0][0] == "4242" and sent[0][1] == "blocked"
    assert CLIENT_PARK["needed"] in sent[0][2]
    record = receipts(run)[-1]
    assert record["outcome"] == "fallback_notify"
    assert "not available" in record["detail"]


def test_park_seam_reports_unavailable_without_a_park_record(tmp_path):
    # This base tree (ea22ed88) carries neither state["park_status"] nor
    # a park classifier in auto_resume: the seam must say so, not guess.
    run = make_run(tmp_path, park=None)
    result = cl.park_notice(run, layer_available=True)
    assert result["status"] == "layer_unavailable"
    assert not (run / "conversation-brief.json").exists()
    assert receipts(run)[-1]["outcome"] == "layer_unavailable"


# ---------------------------------------------------------------------------
# Reply routing: exactly one signal, only for qualified replies
# ---------------------------------------------------------------------------

class FakeDispatch:
    def __init__(self):
        self.calls = []

    def __call__(self, run_dir):
        self.calls.append(run_dir)
        return {"argv": ["fake-launcher"], "returncode": 0}


def style_run(tmp_path, name="run-style"):
    run = make_run(tmp_path, name=name)
    samples = run / "working" / "style-preview"
    samples.mkdir(parents=True)
    (samples / "style_samples_manifest.json").write_text(
        json.dumps({"variants": ["A", "B", "C"]}))
    return run


def test_qualified_style_pick_records_once_and_dispatches_once(tmp_path):
    run = style_run(tmp_path)
    fake = FakeDispatch()
    result = cl.route_reply(run, message_id="msg-1", kind="style_pick",
                            value="B", resume_dispatch=fake)
    assert result["status"] == "reply_routed"
    choice = read_json(run / "working" / "copy" / "style_preview_choice.json")
    assert choice["chosen_variant"] == "B"
    assert choice["owner_msg_id"] == "msg-1"
    assert choice["owner_approved"] is True
    assert "auto_pick" not in choice
    assert len(fake.calls) == 1
    again = cl.route_reply(run, message_id="msg-1", kind="style_pick",
                           value="C", resume_dispatch=fake)
    assert again["duplicate"] is True
    assert len(fake.calls) == 1
    assert read_json(run / "working" / "copy" / "style_preview_choice.json")["chosen_variant"] == "B"


def test_unqualified_style_pick_produces_no_signal(tmp_path):
    run = style_run(tmp_path)
    fake = FakeDispatch()
    result = cl.route_reply(run, message_id="msg-2", kind="style_pick",
                            value="purple", resume_dispatch=fake)
    assert result["status"] == "writer_refused"
    assert not (run / "working" / "copy" / "style_preview_choice.json").exists()
    assert fake.calls == []


def test_style_pick_against_the_wrong_park_is_a_mismatch(tmp_path):
    run = make_run(tmp_path, phase="P4-COPY")
    fake = FakeDispatch()
    result = cl.route_reply(run, message_id="msg-3", kind="style_pick",
                            value="B", resume_dispatch=fake)
    assert result["status"] == "kind_mismatch"
    assert fake.calls == []


def test_reply_to_an_unparked_run_produces_no_signal(tmp_path):
    run = make_run(tmp_path, terminal="DONE", park=None)
    result = cl.route_reply(run, message_id="msg-4", kind="style_pick",
                            value="B", resume_dispatch=FakeDispatch())
    assert result["status"] == "not_parked"


def _profile_owing_plan(tmp_path: Path) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    profile = rp.new_profile()
    rp.upsert_provider(profile, "ollama-cloud")
    rp.save_profile(profile, config_dir)
    return config_dir


def _exploding_dispatch(run_dir):  # the plan path must never dispatch
    raise AssertionError("the resource-plan path dispatched a resume")


def test_qualified_plan_answer_locks_and_is_the_signal(tmp_path):
    run = make_run(tmp_path, phase="P2-PLAN")
    config_dir = _profile_owing_plan(tmp_path)
    result = cl.route_reply(run, message_id="msg-5", kind="resource_plan",
                            value="$100/month", config_dir=config_dir,
                            resume_dispatch=_exploding_dispatch)
    assert result["status"] == "reply_routed"
    assert rp.is_plan_locked("ollama-cloud", config_dir=config_dir)
    entry = rp.get_provider(rp.load_profile(config_dir), "ollama-cloud")
    assert entry["plan_tier"] == "$100/month"
    signal = result["record"]["resume_signal"]
    assert signal["type"] == "plan_answer_recorded"
    # A second answer, even under a new message id, is never re-asked
    # and never overwrites the locked first answer.
    again = cl.route_reply(run, message_id="msg-6", kind="resource_plan",
                           value="$20/month", config_dir=config_dir,
                           resume_dispatch=_exploding_dispatch)
    assert again["status"] == "not_owed"
    entry = rp.get_provider(rp.load_profile(config_dir), "ollama-cloud")
    assert entry["plan_tier"] == "$100/month"


def test_unknown_plan_tier_is_refused_before_any_write(tmp_path):
    run = make_run(tmp_path, phase="P2-PLAN")
    config_dir = _profile_owing_plan(tmp_path)
    result = cl.route_reply(run, message_id="msg-7", kind="resource_plan",
                            value="$999/month", config_dir=config_dir,
                            resume_dispatch=_exploding_dispatch)
    assert result["status"] == "writer_refused"
    assert not rp.is_plan_locked("ollama-cloud", config_dir=config_dir)


def test_plan_decline_locks_the_decline_and_resumes_nothing(tmp_path):
    run = make_run(tmp_path, phase="P2-PLAN")
    config_dir = _profile_owing_plan(tmp_path)
    result = cl.route_reply(run, message_id="msg-8", kind="resource_plan",
                            value="use conservative default",
                            config_dir=config_dir,
                            resume_dispatch=_exploding_dispatch)
    assert result["status"] == "reply_routed"
    assert result["record"]["resume_signal"] is None
    entry = rp.get_provider(rp.load_profile(config_dir), "ollama-cloud")
    assert entry["locked"] is True
    assert entry["locked_choice"] == "use conservative default"


def test_a_kind_with_no_sanctioned_writer_is_escalated_not_routed(tmp_path):
    run = make_run(tmp_path, phase="P2-PLAN")
    fake = FakeDispatch()
    result = cl.route_reply(run, message_id="msg-9", kind="owner_decision",
                            value="skip the gate", resume_dispatch=fake)
    assert result["status"] == "escalated"
    assert result["record"]["resume_signal"] in (None,)
    assert result["record"]["reply_text"] == "skip the gate"
    assert fake.calls == []
    assert not (run / "working" / "copy" / "style_preview_choice.json").exists()


def test_a_reply_without_a_message_id_is_refused(tmp_path):
    run = style_run(tmp_path)
    with pytest.raises(ValueError):
        cl.route_reply(run, message_id="", kind="style_pick", value="B",
                       resume_dispatch=FakeDispatch())


# ---------------------------------------------------------------------------
# The front door: the hand-off carries no intake answers
# ---------------------------------------------------------------------------

def test_frontdoor_handoff_carries_no_answers_and_no_intake_state(tmp_path):
    run = make_run(tmp_path, terminal="", park=None, name="run-door")
    state_before = (run / "state.json").read_text()
    out = cl.frontdoor_handoff(run, ghl_contact_id="contact-1",
                               intake_link="/s/token-abc", channel="sms",
                               consent_posture="captured: conversation + follow-up")
    token = out["token"]
    assert cl.validate_handoff(token) == []
    blob = json.dumps(token).lower()
    for fragment in ("answer", "sp_intake", "deck_brief", "transcript"):
        assert fragment not in blob
    assert token["scope"] == "skill51-gated-intake"
    assert not (run / "working" / "interview").exists()
    assert not (run / "working" / "copy" / "intake.json").exists()
    assert (run / "state.json").read_text() == state_before
    brief = read_json(run / "conversation-brief.json")
    assert brief["seam"] == "intake-frontdoor"
    assert "/s/token-abc" in brief["copy_points"]["handoff_message"]


def test_handoff_validator_refuses_answer_shaped_keys(tmp_path):
    run = make_run(tmp_path, terminal="", park=None, name="run-door-2")
    out = cl.frontdoor_handoff(run, ghl_contact_id="c", intake_link="/s/x",
                               channel="sms", consent_posture="captured")
    bad = dict(out["token"])
    bad["answers"] = {"sp_mode": "QUICK"}
    assert cl.validate_handoff(bad) != []
    bad2 = dict(out["token"])
    bad2["qualification"] = {**out["token"]["qualification"],
                            "intent_confirmed": False}
    assert cl.validate_handoff(bad2) != []


# ---------------------------------------------------------------------------
# Delivery follow-up: only ever about a verified delivery
# ---------------------------------------------------------------------------

def _delivered_run(tmp_path, *, complete=True, verified=True, name="run-del"):
    run = make_run(tmp_path, terminal="DONE", park=None, name=name)
    checkpoints = run / "working" / "checkpoints"
    checkpoints.mkdir(parents=True)
    (checkpoints / "media_library.json").write_text(json.dumps({
        "delivery_complete": complete,
        "delivery_verified_at": "2026-10-14T01:00:00+00:00",
        "delivery_destinations": [
            {"type": "mac_downloads", "path": "~/Downloads/deck_final.pptx",
             "verified": verified},
            {"type": "ghl", "ghl_media_id": "m-1", "verified": True},
        ]}))
    qc_dir = run / "working" / "qc"
    qc_dir.mkdir(parents=True)
    (qc_dir / "final_deck_qc.json").write_text(json.dumps({"qc_score": 9.4}))
    return run


def test_delivery_brief_renders_the_bounded_sequence(tmp_path):
    run = _delivered_run(tmp_path)
    result = cl.delivery_followup_brief(run)
    assert result["status"] == "brief_issued"
    brief = read_json(run / "conversation-brief.json")
    assert brief["seam"] == "delivery-followup"
    touches = brief["copy_points"]["sequence"]
    assert [t["id"] for t in touches] == ["T1", "T2", "T3"]
    assert "9.4" in touches[0]["text"]
    assert "review call" in brief["copy_points"]["review_call_booking"]["ask"]
    assert "33c" in brief["copy_points"]["boundary"]


def test_delivery_brief_refuses_an_unverified_delivery(tmp_path):
    run = _delivered_run(tmp_path, verified=False)
    result = cl.delivery_followup_brief(run)
    assert result["status"] == "refused"
    assert not (run / "conversation-brief.json").exists()


# ---------------------------------------------------------------------------
# Receipts: Skill 38's return path lands in the run record, validated
# ---------------------------------------------------------------------------

def test_skill38_receipt_record_lands_validated(tmp_path):
    run = make_run(tmp_path)
    saved = cl.append_receipt(run, {
        "seam": "park-notice", "kind": "receipt", "outcome": "replied",
        "playbook_id": "pb-1", "workflow_id": "wf-1",
        "memory_log_pointer": "conversational-logs/contact-1.md",
        "messages_sent": 2})
    assert saved["outcome"] == "replied"
    assert receipts(run)[-1]["playbook_id"] == "pb-1"
    with pytest.raises(ValueError):
        cl.append_receipt(run, {"seam": "park-notice", "kind": "receipt",
                                "outcome": "vanished"})


# ---------------------------------------------------------------------------
# Doctrine / code agreement
# ---------------------------------------------------------------------------

def test_doctrine_text_and_code_agree():
    doctrine = SKILL38_PROTOCOL.read_text(encoding="utf-8")
    for seam in cl.SEAMS:
        assert seam in doctrine
    for park_class in (cl.PARK_CLIENT_ACTION, cl.PARK_OPERATOR_ACTION,
                       cl.PARK_TRANSIENT_INFRA):
        assert park_class in doctrine
    for filename in ("conversation-brief.json", "conversation-receipt.json",
                     "conversation_templates.json", "conversation_layer.py"):
        assert filename in doctrine
    # The scope bound is stated in the doctrine and in the module alike.
    assert "never asks the intake questions" in doctrine
    assert "never asks the intake questions" in cl.__doc__
    # The decline literal the adapter matches is the literal the profile
    # writer records (one vocabulary, two readers).
    rp_source = (_SCRIPTS_DIR / "presentation_job" / "resource_profile.py").read_text()
    assert f'"{cl.DECLINE_LITERAL}"' in rp_source
    # The resume argv the adapter dispatches is the launcher resume argv.
    import inspect
    source = inspect.getsource(cl._default_resume_dispatch)
    assert "presentation_job.launcher" in source and "--resume" in source
    # Templates carry a silence rule for exactly the two non-client classes.
    templates = cl.load_templates()
    assert set(templates["park_notice"]["silent_classes"]) == {
        "operator_action", "transient_infra"}
    assert set(templates["park_notice"]["by_need"]) == {
        "style_pick", "resource_plan"}
