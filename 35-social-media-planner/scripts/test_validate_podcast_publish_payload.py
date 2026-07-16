#!/usr/bin/env python3
"""Offline CLI tests for validate_podcast_publish_payload.py.

Run:
    python3 test_validate_podcast_publish_payload.py
    pytest test_validate_podcast_publish_payload.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
VALIDATOR = HERE / "validate_podcast_publish_payload.py"

REQUIRED_FIELDS = (
    "podcast_id",
    "audio_url",
    "image_url",
    "title",
    "description",
    "publish_date",
    "client_email",
)

VALID_PAYLOAD = {
    "podcast_id": "channel-reference",
    "audio_url": "https://media.example.invalid/episode.mp3",
    "image_url": "https://media.example.invalid/cover.jpg",
    "title": "Episode title",
    "description": "Episode description",
    "publish_date": "2030-01-02T09:00:00-05:00",
    "client_email": "recipient@example.invalid",
}


def run_stdin(payload: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


class TestPodcastPublishPayloadValidator(unittest.TestCase):
    def test_all_seven_present_passes_silently(self) -> None:
        result = run_stdin(VALID_PAYLOAD)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_each_required_field_missing_fails_and_names_field(self) -> None:
        for field in REQUIRED_FIELDS:
            with self.subTest(field=field):
                payload = dict(VALID_PAYLOAD)
                del payload[field]
                result = run_stdin(payload)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("missing:", result.stderr)
                self.assertIn(field, result.stderr)

    def test_each_required_field_null_or_empty_fails_and_names_field(self) -> None:
        for field in REQUIRED_FIELDS:
            for invalid_value in (None, ""):
                with self.subTest(field=field, invalid_value=invalid_value):
                    payload = dict(VALID_PAYLOAD)
                    payload[field] = invalid_value
                    result = run_stdin(payload)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("null/empty:", result.stderr)
                    self.assertIn(field, result.stderr)

    def test_extra_unknown_keys_pass_via_file_argument(self) -> None:
        payload = dict(VALID_PAYLOAD)
        payload["unknown_future_field"] = "accepted"
        with tempfile.TemporaryDirectory() as tmpdir:
            payload_path = Path(tmpdir) / "payload.json"
            payload_path.write_text(json.dumps(payload), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(VALIDATOR), str(payload_path)],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_whitespace_only_value_fails(self) -> None:
        payload = dict(VALID_PAYLOAD)
        payload["description"] = "   \t\n"
        result = run_stdin(payload)
        self.assertEqual(result.returncode, 1)
        self.assertIn("description", result.stderr)

    def test_invalid_json_and_non_object_inputs_fail_closed(self) -> None:
        invalid_json = subprocess.run(
            [sys.executable, str(VALIDATOR)],
            input="{not-json",
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(invalid_json.returncode, 2)
        self.assertIn("input error", invalid_json.stderr)

        non_object = run_stdin(["not", "an", "object"])
        self.assertEqual(non_object.returncode, 2)
        self.assertIn("must be an object", non_object.stderr)


if __name__ == "__main__":
    unittest.main()
