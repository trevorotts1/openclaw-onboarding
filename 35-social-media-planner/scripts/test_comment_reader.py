#!/usr/bin/env python3
"""test_comment_reader.py — fail-first proof for Skill 35 comment_reader (P3-08
Gap B, step 4).

These tests fail against the PRE-fix tree (no comment_reader.py existed — a
prospect who commented reached no pipeline) and pass with the module in place.
They prove the four contract properties P3-08 step 4 + the QC probe require:

  1. A supported-channel comment is HANDED OFF as a synthetic inbound turn into
     Skill 38's conversational-logs path, tagged with post/permalink context.
  2. A channel with NO comment-read surface is LEDGERED + skipped, NEVER
     fabricated (the honesty gate — no silent empty result, no invented feed).
  3. A malformed event is skipped with a reason, not crashed on.
  4. The whole run is deterministic and touches only the master-files dir.

Run: pytest 35-social-media-planner/scripts/test_comment_reader.py -q
"""
import importlib.util
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_HERE, "comment_reader.py")


def _load():
    spec = importlib.util.spec_from_file_location("comment_reader", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_module_exists():
    # Fail-first anchor: before P3-08 step 4 this file did not exist.
    assert os.path.exists(_MODULE_PATH), "comment_reader.py must exist (P3-08 step 4)"


def test_supported_channel_hands_off_with_permalink_context(tmp_path):
    cr = _load()
    events = [{
        "channel": "facebook",
        "post_id": "fb_post_123",
        "permalink": "https://facebook.com/brand/posts/123",
        "comment_id": "cmt_9",
        "author_id": "author_555",
        "author_name": "Jamie Rivers",
        "text": "How do I book a call?",
        "created_at": "2026-07-11T14:00:00Z",
    }]
    summary = cr.run(events, str(tmp_path))
    assert len(summary["handed_off"]) == 1, summary
    assert summary["skipped"] == [], summary
    handoff = summary["handed_off"][0]
    assert handoff["channel"] == "facebook"
    assert handoff["contact_ref"] == "author_555"

    log_path = handoff["log_path"]
    assert os.path.isfile(log_path)
    # Written under Skill 38's conversational-logs/ dir.
    assert os.path.basename(os.path.dirname(log_path)) == "conversational-logs"
    body = open(log_path, encoding="utf-8").read()
    # Tagged with post/permalink context + the prospect's text + a Skill-38 note.
    assert "https://facebook.com/brand/posts/123" in body
    assert "How do I book a call?" in body
    assert "public comment" in body.lower()
    assert "cmt_9" in body


def test_unsupported_channel_is_ledgered_not_fabricated(tmp_path):
    cr = _load()
    # linkedin has no comment-read surface wired (CHANNEL_COMMENT_SURFACE None).
    events = [{
        "channel": "linkedin",
        "post_id": "li_1",
        "permalink": "https://linkedin.com/feed/update/li_1",
        "comment_id": "c1",
        "author_id": "a1",
        "text": "interested",
    }]
    summary = cr.run(events, str(tmp_path))
    assert summary["handed_off"] == [], "must NOT fabricate a handoff for a channel with no surface"
    assert len(summary["skipped"]) == 1
    reason = summary["skipped"][0]["reason"]
    assert "no comment-read api surface" in reason.lower()
    assert summary["skipped"][0]["channel"] == "linkedin"
    # Nothing written for the unsupported channel.
    logs_dir = tmp_path / "conversational-logs"
    assert not logs_dir.exists() or not any(logs_dir.iterdir())


def test_malformed_event_skipped_with_reason_not_crash(tmp_path):
    cr = _load()
    events = [
        {"channel": "facebook", "author_id": "a", "text": ""},   # empty text
        {"channel": "facebook", "post_id": "p", "text": "hi"},   # no author_id
        "not-an-object",                                          # not a dict
        {"channel": "mystery", "author_id": "a", "text": "hi"},  # unknown channel
    ]
    summary = cr.run(events, str(tmp_path))
    assert summary["handed_off"] == []
    assert len(summary["skipped"]) == 4
    # Every skip carries a human reason (no silent drop).
    assert all("reason" in s and s["reason"] for s in summary["skipped"])


def test_dry_run_writes_nothing(tmp_path):
    cr = _load()
    events = [{"channel": "instagram", "post_id": "ig1", "comment_id": "c",
               "author_id": "a", "text": "info?"}]
    summary = cr.run(events, str(tmp_path), dry_run=True)
    assert len(summary["handed_off"]) == 1
    assert summary["handed_off"][0]["dry_run"] is True
    assert not (tmp_path / "conversational-logs").exists()


def test_cli_end_to_end(tmp_path):
    events = [{"channel": "facebook", "post_id": "p", "permalink": "https://x/p",
               "comment_id": "c", "author_id": "author_1", "text": "book me"}]
    infile = tmp_path / "events.json"
    infile.write_text(json.dumps(events))
    mfd = tmp_path / "master"
    proc = subprocess.run(
        [sys.executable, _MODULE_PATH, "--master-files-dir", str(mfd),
         "--input", str(infile)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert len(out["handed_off"]) == 1
    assert (mfd / "conversational-logs").is_dir()


if __name__ == "__main__":
    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-q"]))
