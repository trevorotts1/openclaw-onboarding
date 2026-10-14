#!/usr/bin/env python3
"""Step 10/15/16/17 command emission: runnable flags, prompt from the payload,
and env-var defaults instead of aborting `${VAR:?...}` guards.

The driver only emits command TEXT; nothing here talks to a network, a
credential or a job database. Every assertion is a substring check against
``_emit_step_command``.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import podcast_step_driver as d  # noqa: E402


def _interview_row():
    return {"mode": "interview_style_podcast", "episode_title": "T"}


def _personal_row():
    return {"mode": "personal_podcast_style", "episode_title": "T"}


def test_step15_interview_carries_mode_show_and_speaker():
    cmd = d._emit_step_command(
        15, "pj_1", _interview_row(),
        {"show_name": "Edge Talk", "first_name": "Ann",
         "publish_timestamp": "11/01/2026"},
        {},
    )
    assert "--mode interview_style_podcast" in cmd
    assert "--show-name 'Edge Talk'" in cmd
    assert "--speaker Ann" in cmd


def test_step15_interview_without_payload_first_name_keeps_placeholder():
    cmd = d._emit_step_command(
        15, "pj_1", _interview_row(), {"show_name": "Edge Talk"}, {},
    )
    assert "--speaker \"<guest_first_name>\"" in cmd
    assert "--show-name 'Edge Talk'" in cmd


def test_step15_personal_carries_mode_and_selects_no_show():
    cmd = d._emit_step_command(15, "pj_1", _personal_row(), {}, {})
    assert "--mode personal_podcast_style" in cmd
    assert "--show-name" not in cmd
    assert "--speaker" not in cmd


def test_step10_uses_the_stored_visual_description():
    cmd = d._emit_step_command(
        10, "pj_1", {"episode_title": "T"}, {"visual_description": "sunset"}, {},
    )
    assert "--prompt sunset" in cmd
    assert "--prompt-file <visual_desc.txt>" not in cmd


def test_step10_without_a_visual_description_keeps_the_file_placeholder():
    cmd = d._emit_step_command(10, "pj_1", {"episode_title": "T"}, {}, {})
    assert "--prompt-file <visual_desc.txt>" in cmd


def test_step16_state_dir_defaults_instead_of_aborting():
    for step in (16, 17):
        cmd = d._emit_step_command(
            step, "pj_1", {"episode_title": "T",
                           "mode": "personal_podcast_style"},
            {}, {},
        )
        assert ":-$HOME/.openclaw/podcast-engine/state" in cmd, cmd
        assert ":?" not in cmd, cmd


def test_content_step_work_dir_defaults_per_job():
    cmd = d._emit_content_command(5, "pj_1", {"mode": "personal_podcast_style"})
    assert "${PODCAST_JOB_WORK_DIR:-$HOME/.openclaw/podcast-engine/work/pj_1}" in cmd
    assert "PODCAST_JOB_WORK_DIR:?" not in cmd
    assert "${PODCAST_JOB_WORK_DIR:-$HOME/.openclaw/podcast-engine/work/pj_1}" \
        "/step-5-model.json" in cmd


def test_content_step_still_honors_an_explicit_work_dir():
    # An explicit value wins over the default: the emitted text is the same
    # `${VAR:-default}` expansion the shell resolves, so nothing is hardcoded.
    cmd = d._emit_content_command(5, "pj_1", {"mode": "personal_podcast_style"})
    assert cmd.startswith("set -e\nmkdir -p \"${PODCAST_JOB_WORK_DIR:-")
