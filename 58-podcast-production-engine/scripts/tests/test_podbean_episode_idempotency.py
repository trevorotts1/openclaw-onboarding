#!/usr/bin/env python3
"""Deterministic tests for the U034 episode-count idempotency guard."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

_SCRIPT = Path("/Users/blackceomacmini/July-23-Fixes/repos/openclaw-onboarding/58-podcast-production-engine/scripts/podbean_publish.sh")

EXIT_TERMINAL = 1
EXIT_EPISODE_COUNT_MISMATCH = 6

MOCK_CURL = r'''#!/usr/bin/env bash
url=""; method=""; prev=""
for a in "$@"; do
  if [ "$prev" = "-K" ] && [ -r "$a" ]; then
    while IFS= read -r line; do
      case "$line" in
        'url = '*)     url="${line#url = \"}"; url="${url%\"}" ;;
        'request = '*) method="${line#request = \"}"; method="${method%\"}" ;;
      esac
    done < "$a"
  fi
  prev="$a"
done
[ -n "${MOCK_CALL_LOG:-}" ] && printf '%s %s %s\n' "$(date +%s)" "$method" "$url" >> "$MOCK_CALL_LOG"
status=""
if [ -n "${MOCK_SCRIPT:-}" ] && [ -f "$MOCK_SCRIPT" ]; then
  status="$(head -1 "$MOCK_SCRIPT" 2>/dev/null)"
  sed -i.bak '1d' "$MOCK_SCRIPT" 2>/dev/null; rm -f "$MOCK_SCRIPT.bak"
fi
status="${status:-200}"
body="{}"
case "$method $url" in
  'POST '*oauth/token*)    body='{"access_token":"mock-token"}' ;;
  'GET '*'/podcasts?'*)    body='{"podcasts":[{"id":"12345"}]}' ;;
  'GET '*'/episodes?'*)    count=0
    if [ -n "${MOCK_COUNT_FILE:-}" ] && [ -f "$MOCK_COUNT_FILE" ]; then
      count="$(head -1 "$MOCK_COUNT_FILE")"
    fi
    body='{"count":'"${count}"'}' ;;
  'GET '*uploadAuthorize*) body='{"presigned_url":"http://mock.invalid/presigned","file_key":"mock-key"}' ;;
  'PUT '*)                 body='' ;;
  'POST '*'/episodes'*)    body='{"episode":{"permalink_url":"https://mock.podbean.com/ep/1","id":"ep-1"}}' ;;
esac
printf '%s\n%s' "$body" "$status"
'''


class TestPodbeanEpisodeIdempotency(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        bindir = self.dir / "bin"
        bindir.mkdir()
        mock = bindir / "curl"
        mock.write_text(MOCK_CURL)
        mock.chmod(0o755)
        self.bindir = bindir
        self.audio = self.dir / "episode.mp3"
        self.audio.write_bytes(b"fake mp3 bytes" * 100)
        self.call_log = self.dir / "calls.log"
        self.status_file = self.dir / "statuses.txt"
        self.count_file = self.dir / "mock_count.txt"

    def _base_env(self):
        env = dict(os.environ)
        env.update({
            "PATH": f"{self.bindir}:{env.get('PATH', '')}",
            "PODBEAN_API_BASE": "http://mock.invalid/v1",
            "PODBEAN_PODCAST_ID": "12345",
            "PODBEAN_CLIENT_ID": "test-client-id",
            "PODBEAN_CLIENT_SECRET": "test-client-secret",
            "PODBEAN_RETRY_BASE_DELAY": "1",
            "MOCK_SCRIPT": str(self.status_file),
            "MOCK_CALL_LOG": str(self.call_log),
            "MOCK_COUNT_FILE": str(self.count_file),
        })
        for k in ("PODBEAN_PUBLISH_WEBHOOK_URL", "PODBEAN_PUBLISH_TOKEN",
                  "PODBEAN_BROKER_WEBHOOK_URL", "PODBEAN_BROKER_TOKEN"):
            env.pop(k, None)
        return env

    def run_publish(self, statuses=None, extra_args=None):
        if statuses is not None:
            self.status_file.write_text("\n".join(statuses) + "\n")
        env = self._base_env()
        args = ["bash", str(_SCRIPT), "--audio", str(self.audio),
                "--title", "Test Episode"]
        if extra_args:
            args.extend(extra_args)
        return subprocess.run(
            args, env=env, capture_output=True, text=True, timeout=120,
        )

    def test_mismatched_count_refuses_to_publish_with_distinct_exit_code(self):
        """Mock API returns 7 episodes; roster claims 5. Script must exit 6."""
        self.count_file.write_text("7\n")
        r = self.run_publish(statuses=[], extra_args=["--roster-episode-count", "5"])
        self.assertEqual(r.returncode, EXIT_EPISODE_COUNT_MISMATCH,
                         f"roster=5 vs server=7 must exit 6; stderr: {r.stderr}")
        self.assertIn("episode_count_mismatch", r.stdout)
        result = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "episode_count_mismatch")
        self.assertEqual(result["roster_count"], 5)
        self.assertEqual(result["server_count"], 7)
        self.assertNotEqual(r.returncode, EXIT_TERMINAL, "mismatch must use exit 6, not 1")

    def test_matching_count_proceeds_to_publish(self):
        """Mock API returns 5 episodes; roster claims 5. Script must succeed."""
        self.count_file.write_text("5\n")
        r = self.run_publish(statuses=[], extra_args=["--roster-episode-count", "5"])
        self.assertEqual(r.returncode, 0, f"roster=5 matches server=5; stderr: {r.stderr}")
        result = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(result["status"], "published")
        self.assertIn("matches roster", r.stderr)
        self.assertIn("episode_number", result)

    def test_omitting_flag_skips_guard_and_publishes_normally(self):
        """Without --roster-episode-count, guard is skipped entirely."""
        self.count_file.write_text("7\n")
        r = self.run_publish(statuses=[], extra_args=[])
        self.assertEqual(r.returncode, 0, f"must publish without guard flag; stderr: {r.stderr[-300:]}")
        result = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(result["status"], "published")
        self.assertNotIn("matches roster", r.stderr)
        self.assertNotIn("EPISODE COUNT MISMATCH", r.stderr)

    def test_non_integer_roster_count_is_rejected(self):
        """--roster-episode-count=abc must exit 1."""
        self.count_file.write_text("0\n")
        r = self.run_publish(statuses=[], extra_args=["--roster-episode-count", "abc"])
        self.assertEqual(r.returncode, EXIT_TERMINAL, f"stderr: {r.stderr[-300:]}")
        self.assertIn("must be a non-negative integer", r.stderr)

    def test_mismatch_does_not_upload_audio(self):
        """Mismatch must abort BEFORE uploadAuthorize."""
        self.count_file.write_text("99\n")
        r = self.run_publish(statuses=[], extra_args=["--roster-episode-count", "0"])
        self.assertEqual(r.returncode, EXIT_EPISODE_COUNT_MISMATCH)
        calls = []
        if self.call_log.exists():
            calls = self.call_log.read_text().splitlines()
        upload_hits = [c for c in calls if "uploadAuthorize" in c]
        self.assertEqual(len(upload_hits), 0, "mismatch guard must fire before upload")

    def test_test_flag_short_circuits_before_podbean_call(self):
        """--test skips Podbean entirely; guard also short-circuits."""
        self.count_file.write_text("99\n")
        r = self.run_publish(statuses=[], extra_args=["--roster-episode-count", "0", "--test"])
        self.assertEqual(r.returncode, 0, f"stderr: {r.stderr[-300:]}")
        result = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(result["status"], "test-skipped")
        calls = []
        if self.call_log.exists():
            calls = self.call_log.read_text().splitlines()
        self.assertEqual(len(calls), 0, "--test must not call curl")

    def test_matching_count_still_increments_for_next_episode(self):
        """Episode number = server count + 1."""
        self.count_file.write_text("3\n")
        r = self.run_publish(statuses=[], extra_args=["--roster-episode-count", "3"])
        self.assertEqual(r.returncode, 0, f"stderr: {r.stderr[-300:]}")
        result = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(result["episode_number"], 4, "number must be 3+1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
