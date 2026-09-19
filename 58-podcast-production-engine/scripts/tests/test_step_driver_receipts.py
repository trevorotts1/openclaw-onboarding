#!/usr/bin/env python3
"""Hermetic worker-checkpoint regression for the Podcast step driver.

This is deliberately a controlled local dispatch test, not a production E2E
claim.  Its "provider" is a text file representing an already-returned model
response.  It proves the source contracts around a queued credit interruption:
the registered worker sees Step 12.5, claims it once, resumes the same claim,
persists the notes, and a conflicting duplicate cannot change its key.
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


def run(*parts, ok=True):
    completed = subprocess.run(
        [sys.executable, *map(str, parts)], text=True, capture_output=True,
        check=False,
    )
    if ok and completed.returncode:
        raise AssertionError("command failed (%s): %s" %
                             (completed.returncode, completed.stderr))
    return completed


def state(db, *parts, ok=True):
    return run(STATE, "--db-path", db, "--json", *parts, ok=ok)


def driver(db, *parts, ok=True):
    return run(DRIVER, "--db-path", db, "--json", *parts, ok=ok)


def output(db, job, field, value):
    state(db, "output", "--job-id", job, "--field", field, "--value", value)


def main():
    with tempfile.TemporaryDirectory(prefix="podcast-step-receipt-") as temp:
        temp = Path(temp)
        db = str(temp / "podcast.db")
        payload = temp / "payload.json"
        payload.write_text(json.dumps({"preset": "interview"}), encoding="utf-8")
        created = json.loads(state(
            db, "create", "--client-id", "client-test", "--location-id", "loc-test",
            "--contact-id", "contact-test", "--mode", "interview_style_podcast",
            "--style", "vulnerable", "--payload-file", payload,
        ).stdout)
        job = created["job_id"]

        # Walk to publishing with local stand-in artifacts. No provider is called.
        for target in ("researching", "writing", "in_qc", "generating_art"):
            state(db, "advance", "--job-id", job, "--to", target)
        output(db, job, "cover_image_url", "artifact:cover")
        state(db, "advance", "--job-id", job, "--to", "producing_audio")
        output(db, job, "mp3_media_url", "artifact:audio")
        state(db, "advance", "--job-id", job, "--to", "publishing")
        output(db, job, "episode_package_url", "artifact:package")

        work = json.loads(driver(db, "next", "--job-id", job).stdout)
        assert work["step"] == "12.5", work
        checkpoint = work["checkpoint"]
        key = checkpoint["idempotency_key"]

        # First dispatch claims the work, then a credit interruption occurs
        # before the local model response is persisted.
        claim = json.loads(state(
            db, "receipt", "begin", "--job-id", job, "--step", "12.5",
            "--action", "show-notes", "--idempotency-key", key,
        ).stdout)
        assert claim["disposition"] == "acquired", claim
        state(db, "hold", "--job-id", job, "--service", "fish_audio")
        state(db, "resume", "--job-id", job)
        recovered = json.loads(state(
            db, "receipt", "begin", "--job-id", job, "--step", "12.5",
            "--action", "show-notes", "--idempotency-key", key,
        ).stdout)
        assert recovered["disposition"] == "recovery", recovered

        # The fake provider result is local evidence only. record-show-notes
        # validates/persists it and closes the durable receipt.
        notes = temp / "show-notes.txt"
        notes.write_text("A" * 800, encoding="utf-8")
        recorded = json.loads(driver(
            db, "record-show-notes", "--job-id", job, "--file", notes,
        ).stdout)
        assert recorded["receipt"]["disposition"] == "completed", recorded
        after = json.loads(driver(db, "next", "--job-id", job).stdout)
        assert after["step"] == 13, after

        # A second worker with a different key cannot re-dispatch or overwrite.
        duplicate = state(
            db, "receipt", "begin", "--job-id", job, "--step", "12.5",
            "--action", "show-notes", "--idempotency-key", "podcast:wrong:key",
            ok=False,
        )
        assert duplicate.returncode == 3, duplicate.stderr
        assert "duplicate dispatch refused" in duplicate.stderr, duplicate.stderr

    print("step-driver receipt regression: PASS")


if __name__ == "__main__":
    main()
