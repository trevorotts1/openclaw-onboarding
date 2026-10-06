#!/usr/bin/env python3
"""Hermetic interview-protocol acceptance harness.

This is deliberately not a live-provider claim.  It uses the real state writer,
step driver, content work-order/receipt paths and terminal driver commands, with
small deterministic stand-ins for model, judge, Fish, media, Podbean, Convert
and Flow, enrollment and Command Center boundaries.  The resulting counters
prove dispatch semantics that a live sandbox acceptance still has to repeat.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "podcast_state.py"
DRIVER = ROOT / "podcast_step_driver.py"
sys.path.insert(0, str(ROOT))
import cc_board  # noqa: E402


def run(path, *parts, env=None, ok=True):
    result = subprocess.run([sys.executable, str(path), "--db-path", str(DB), "--json", *map(str, parts)],
                            text=True, capture_output=True, env=env, check=False)
    if ok and result.returncode:
        raise AssertionError("%s failed: %s" % (parts, result.stderr or result.stdout))
    return result


def state(*parts, **kwargs):
    return run(STATE, *parts, **kwargs)


def driver(*parts, **kwargs):
    return run(DRIVER, *parts, **kwargs)


def data(result):
    return json.loads(result.stdout)


def output(job, field, value):
    state("output", "--job-id", job, "--field", field, "--value", value)


def claim(job, step):
    cp = data(driver("next", "--job-id", job))["checkpoint"]
    return data(state("receipt", "begin", "--job-id", job, "--step", str(step),
                      "--action", cp["action"], "--idempotency-key", cp["idempotency_key"]))


def complete(job, step, evidence):
    cp = data(driver("next", "--job-id", job))["checkpoint"]
    return data(state("receipt", "complete", "--job-id", job, "--step", str(step),
                      "--action", cp["action"], "--idempotency-key", cp["idempotency_key"],
                      "--result-file", str(evidence)))


def count(log, name):
    entries = json.loads(log.read_text()) if log.exists() else []
    entries.append(name)
    log.write_text(json.dumps(entries))


with tempfile.TemporaryDirectory(prefix="podcast-interview-harness-") as tmp:
    TMP = Path(tmp)
    DB = TMP / "state.db"
    log = TMP / "effects.json"
    payload = TMP / "payload.json"
    payload.write_text(json.dumps({"preset": "interview", "_test": True}), encoding="utf-8")
    created = data(state("create", "--client-id", "test-client", "--location-id", "test-location",
                         "--contact-id", "test-contact", "--mode", "interview_style_podcast",
                         "--style", "provocative", "--payload-file", str(payload)))
    job = created["job_id"]

    # Step 2 is a concrete receipt, then the real writer advances to research.
    assert data(driver("next", "--job-id", job))["step"] == 2
    assert claim(job, 2)["disposition"] == "acquired"
    e2 = TMP / "step2.json"; e2.write_text("{}")
    assert complete(job, 2, e2)["disposition"] == "completed"
    state("advance", "--job-id", job, "--to", "researching")

    # The real content persistence command is exercised for steps 3-8.
    content = {
        3: json.dumps({"research_package": {"finding": "verified"}, "sources": ["fixture"]}),
        4: json.dumps({"runtime_minutes": 10, "target_word_count": 1400, "rationale": "fixture"}),
        5: json.dumps({"title": "A Test Episode", "thesis": "Fixture truth"}),
        6: "This is a sufficiently long fixture draft for a spoken episode with enough words to persist safely.",
        7: "This is a sufficiently long improved fixture draft that keeps the approved title and thesis intact.",
        8: "This is a sufficiently long read aloud fixture draft that remains clean, speakable and deterministic.",
    }
    for step in range(3, 9):
        work_order = data(driver("next", "--job-id", job))
        assert work_order["step"] == step
        assert "model_router.py route" in work_order["command"]
        assert "record-content --job-id" in work_order["command"]
        assert claim(job, step)["disposition"] == "acquired"
        count(log, "model" if step != 8 else "judge-ready-script")
        result_file = TMP / ("step-%d-model.json" % step)
        result_file.write_text(json.dumps({"model": "fake-content", "text": content[step]}), encoding="utf-8")
        recorded = data(driver("record-content", "--job-id", job, "--step", step, "--file", result_file))
        assert recorded["recorded"] is True
        # Completed content is never re-dispatched on a later wakeup.
        assert data(driver("record-content", "--job-id", job, "--step", step, "--file", result_file))["disposition"] == "already_complete"
        if step == 3:
            state("advance", "--job-id", job, "--to", "writing")

    assert data(driver("next", "--job-id", job))["advance_to"] == "in_qc"
    state("advance", "--job-id", job, "--to", "in_qc")
    assert claim(job, 9)["disposition"] == "acquired"; count(log, "judge")
    qc = TMP / "qc.json"; qc.write_text("{}")
    complete(job, 9, qc)
    state("advance", "--job-id", job, "--to", "generating_art")
    assert claim(job, 10)["disposition"] == "acquired"; count(log, "cover")
    cover = TMP / "cover.json"; cover.write_text("{}")
    complete(job, 10, cover); output(job, "cover_image_url", "https://fixture/cover.jpg")
    state("advance", "--job-id", job, "--to", "producing_audio")
    assert claim(job, 11)["disposition"] == "acquired"; count(log, "fish")
    audio = TMP / "audio.json"; audio.write_text("{}")
    complete(job, 11, audio); output(job, "mp3_media_url", "https://fixture/audio.mp3")
    state("advance", "--job-id", job, "--to", "publishing")
    assert claim(job, 12)["disposition"] == "acquired"; count(log, "documents")
    docs = TMP / "docs.json"; docs.write_text("{}")
    complete(job, 12, docs)
    output(job, "episode_package_url", "https://fixture/package.pdf")
    output(job, "speech_script_url", "https://fixture/script.txt")

    # Step 12.5 uses its dedicated production persistence path.
    assert data(driver("next", "--job-id", job))["step"] == "12.5"
    assert claim(job, "12.5")["disposition"] == "acquired"
    notes = TMP / "notes.txt"; notes.write_text("N" * 800)
    assert data(driver("record-show-notes", "--job-id", job, "--file", notes))["recorded"] is True
    assert data(state("receipt", "begin", "--job-id", job, "--step", "12.5",
                      "--action", "show-notes", "--idempotency-key",
                      "podcast:%s:12.5:show-notes" % job))["disposition"] == "already_complete"
    assert data(driver("next", "--job-id", job))["step"] == 13
    assert claim(job, 13)["disposition"] == "acquired"; count(log, "teaser")
    teaser = TMP / "teaser.json"; teaser.write_text("{}")
    complete(job, 13, teaser); output(job, "book_teaser_url", "https://fixture/teaser.pdf")

    # The publish receipt makes an ambiguous remote success non-runnable.
    assert data(driver("next", "--job-id", job))["step"] == 15
    first_publish = claim(job, 15); assert first_publish["disposition"] == "acquired"
    count(log, "podbean")
    replay = claim(job, 15); assert replay["disposition"] == "in_progress"
    assert json.loads(log.read_text()).count("podbean") == 1
    publish = TMP / "publish.json"; publish.write_text("{}")
    assert complete(job, 15, publish)["disposition"] == "completed"
    output(job, "podbean_permalink", "https://fixture/published")
    assert data(state("receipt", "begin", "--job-id", job, "--step", "15",
                      "--action", "publish-to-podbean", "--idempotency-key",
                      "podcast:%s:15:publish-to-podbean" % job))["disposition"] == "already_complete"

    # Deterministic CAF and enrollment boundary stand-ins, invoked by the real driver.
    fake = TMP / "fake_boundary.py"
    fake.write_text("""import json, os, sys\nlog=os.environ['PODCAST_HARNESS_LOG']\na=json.loads(open(log).read()) if os.path.exists(log) else []\na.append(sys.argv[1]); open(log,'w').write(json.dumps(a))\nprint(json.dumps({'status':'ok','read_back_pass':True,'verified':True,'workflows':{'04':{'eligible':True},'06':{'verified':True}}}))\n""", encoding="utf-8")
    env = dict(os.environ, PODCAST_HARNESS_LOG=str(log),
               PODCAST_FIELD_LAYER_CMD="%s %s field" % (sys.executable, fake),
               PODCAST_ENROLLMENT_CMD="%s %s enroll" % (sys.executable, fake))
    step16_order = data(driver("next", "--job-id", job))
    assert step16_order["step"] == 16 and " link-back --job-id " in step16_order["command"]
    assert claim(job, 16)["disposition"] == "acquired"
    assert data(driver("link-back", "--job-id", job, "--state-dir", TMP / "client-state", env=env))["link_back_verified"] is True
    state("advance", "--job-id", job, "--to", "enrolling")
    step17_order = data(driver("next", "--job-id", job))
    assert step17_order["step"] == 17 and " terminal-action --job-id " in step17_order["command"]
    assert claim(job, 17)["disposition"] == "acquired"
    terminal = data(driver("terminal-action", "--job-id", job, "--state-dir", TMP / "client-state", env=env))
    assert terminal["kind"] == "workflow-enrollment"
    effects = json.loads(log.read_text())
    assert effects.count("field") == 1 and effects.count("enroll") == 1

    # Exercise the real CC adapter lifecycle against a deterministic HTTP
    # boundary: source-owned card creation, deliverable registration, then the
    # required backlog -> review -> done transition. This is not a direct
    # state shortcut and therefore catches an adapter contract drift.
    cc_requests = []
    original_request = cc_board._request_with_retry
    original_dir, original_file = cc_board._STATE_DIR, cc_board._STATE_FILE
    cc_board._STATE_DIR = TMP / "cc-state"
    cc_board._STATE_FILE = cc_board._STATE_DIR / "board-map.json"
    def fake_cc_request(method, url, payload, _cfg):
        cc_requests.append((method, url, payload))
        if method == "POST" and url.endswith("/api/tasks/ingest"):
            return 201, {"task_id": "cc-fixture-task"}
        if method == "POST" and url.endswith("/deliverables"):
            return 201, {"ok": True}
        if method == "GET":
            return 200, {"status": "backlog"}
        if method == "PATCH":
            return 200, {"ok": True}
        raise AssertionError("unexpected CC request: %s %s" % (method, url))
    cc_board._request_with_retry = fake_cc_request
    cc_env = {"CC_BASE_URL": "https://cc.fixture"}
    try:
        assert cc_board.create_board_card(job, "Test Client", "A Test Episode", env=cc_env) == "cc-fixture-task"
        assert cc_board.register_deliverable(job, permalink="https://fixture/published", env=cc_env)
        assert cc_board.patch_board_card(job, phase="complete", status="done", env=cc_env)
    finally:
        cc_board._request_with_retry = original_request
        cc_board._STATE_DIR, cc_board._STATE_FILE = original_dir, original_file
    assert cc_requests[0][2]["source"] == "podcast-engine"
    assert [request[2].get("status") for request in cc_requests if request[0] == "PATCH"] == ["review", "done"]
    count(log, "command-center-complete")
    # The real writer deliberately refuses a TEST job's terminal live state;
    # CC completion is therefore a fake boundary assertion here, not a claim
    # that the controlled run published or completed live.
    refused = state("advance", "--job-id", job, "--to", "complete", "--force-waiver",
                    "controlled test finish", ok=False)
    assert refused.returncode != 0 and "TEST" in (refused.stderr + refused.stdout)
    assert json.loads(log.read_text()).count("command-center-complete") == 1
    print("interview protocol harness: PASS (hermetic fakes only; no live-provider proof)")
