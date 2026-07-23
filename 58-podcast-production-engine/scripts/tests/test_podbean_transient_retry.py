#!/usr/bin/env python3
# =============================================================================
# SKILL 58 - PODCAST PRODUCTION ENGINE :: Podbean transient-error retry (U036)
# -----------------------------------------------------------------------------
# Stdlib unittest only. No network: a mock curl on PATH scripts the HTTP status
# sequence (via PODBEAN_API_BASE + a status file). Proves:
#   1. A transient 503 twice, then 200: the publish SUCCEEDS after retry, with
#      bounded exponential backoff between attempts (>= 1s then >= 2s at base 1).
#   2. A transient 503 three times: the script exits with the DISTINCT
#      transient-failure code (5), not the terminal code (1).
#   3. A terminal 401: the script fails IMMEDIATELY with exit 1 and makes
#      exactly ONE call (no retry on a non-transient error).
# Run:  python3 -m unittest 58-podcast-production-engine/scripts/tests/test_podbean_transient_retry.py
# =============================================================================
"""Deterministic tests for Podbean API transient-error retry (U036)."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_SCRIPT = _HERE.parent.parent / "podbean_publish.sh"

EXIT_TERMINAL = 1
EXIT_TRANSIENT = 5

# Mock curl: reads the -K config to learn the method + url, consumes the next
# scripted status from $MOCK_SCRIPT (one per line; empty/absent -> 200), logs
# each call to $MOCK_CALL_LOG, and prints "<json body>\n<status>" the way the
# script's `-w '\n%{http_code}'` parser expects.
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
  'GET '*'/episodes?'*)    body='{"count":0}' ;;
  'GET '*uploadAuthorize*) body='{"presigned_url":"http://mock.invalid/presigned","file_key":"mock-key"}' ;;
  'PUT '*)                 body='' ;;
  'POST '*'/episodes'*)    body='{"episode":{"permalink_url":"https://mock.podbean.com/ep/1","id":"ep-1"}}' ;;
esac
printf '%s\n%s' "$body" "$status"
'''


class TestPodbeanTransientRetry(unittest.TestCase):
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

    def run_publish(self, statuses):
        self.status_file.write_text("\n".join(statuses) + "\n")
        env = dict(os.environ)
        env.update({
            "PATH": f"{self.bindir}:{env.get('PATH', '')}",
            "PODBEAN_API_BASE": "http://mock.invalid/v1",
            "PODBEAN_PODCAST_ID": "12345",
            "PODBEAN_CLIENT_ID": "test-client-id",
            "PODBEAN_CLIENT_SECRET": "test-client-secret",
            "PODBEAN_RETRY_BASE_DELAY": "1",   # shrink backoff: 1s, 2s (bounded)
            "MOCK_SCRIPT": str(self.status_file),
            "MOCK_CALL_LOG": str(self.call_log),
        })
        # Force LOCAL mode: proxy and broker variables must be unset.
        for k in ("PODBEAN_PUBLISH_WEBHOOK_URL", "PODBEAN_PUBLISH_TOKEN",
                  "PODBEAN_BROKER_WEBHOOK_URL", "PODBEAN_BROKER_TOKEN"):
            env.pop(k, None)
        return subprocess.run(
            ["bash", str(_SCRIPT), "--audio", str(self.audio),
             "--title", "Test Episode"],
            env=env, capture_output=True, text=True, timeout=120,
        )

    def calls(self):
        if not self.call_log.exists():
            return []
        return [ln.split() for ln in self.call_log.read_text().splitlines() if ln.strip()]

    def oauth_calls(self):
        return [c for c in self.calls() if "oauth/token" in c[2]]

    def test_503_twice_then_200_succeeds_after_retry(self):
        """AC#2 + AC#5: transient 503 is retried with bounded exponential
        backoff; the publish succeeds once the API recovers."""
        r = self.run_publish(["503", "503"])  # remaining calls default to 200
        self.assertEqual(r.returncode, 0, f"stderr: {r.stderr}")
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(out["status"], "published")
        oauth = self.oauth_calls()
        self.assertEqual(len(oauth), 3, "oauth must be attempted 3 times (2 fails + 1 success)")
        # Bounded exponential backoff at base 1: gap1 >= 1s, gap2 >= 2s, and the
        # whole sequence stays well under any unbounded growth.
        t0, t1, t2 = (int(c[0]) for c in oauth)
        self.assertGreaterEqual(t1 - t0, 1, "first backoff must be >= 1s (base 1)")
        self.assertGreaterEqual(t2 - t1, 2, "second backoff must be >= 2s (exponential)")
        self.assertLessEqual(t2 - t0, 20, "backoff must be bounded, not unbounded")

    def test_503_three_times_exits_distinct_transient_code(self):
        """AC#3: after the retry budget is exhausted on a transient error, the
        script exits with the distinct transient code (5), not terminal (1)."""
        r = self.run_publish(["503", "503", "503"])
        self.assertEqual(r.returncode, EXIT_TRANSIENT,
                         f"expected exit {EXIT_TRANSIENT}; stderr: {r.stderr}")
        self.assertNotEqual(r.returncode, EXIT_TERMINAL)
        self.assertIn("transient", r.stderr.lower())
        self.assertEqual(len(self.oauth_calls()), 3, "exactly RETRIES attempts, then stop")

    def test_401_fails_immediately_without_retry(self):
        """AC#4: a non-transient error (401) fails immediately with the
        terminal exit code and makes exactly ONE call."""
        r = self.run_publish(["401"])
        self.assertEqual(r.returncode, EXIT_TERMINAL, f"stderr: {r.stderr}")
        self.assertNotEqual(r.returncode, EXIT_TRANSIENT)
        self.assertEqual(len(self.oauth_calls()), 1, "401 must NOT be retried")

    def test_429_is_transient_and_retried(self):
        """AC#2: 429 (rate limit) is classified transient and retried."""
        r = self.run_publish(["429", "429", "429"])
        self.assertEqual(r.returncode, EXIT_TRANSIENT, f"stderr: {r.stderr}")
        self.assertEqual(len(self.oauth_calls()), 3, "429 must be retried up to RETRIES")


if __name__ == "__main__":
    unittest.main(verbosity=2)
