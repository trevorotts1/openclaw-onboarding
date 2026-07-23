#!/usr/bin/env python3
# =============================================================================
# SKILL 58 - PODCAST PRODUCTION ENGINE :: podcast dry-run / publish-draft (U044)
# -----------------------------------------------------------------------------
# Stdlib unittest only. No network: a mock curl on PATH scripts the HTTP
# responses AND captures the `status=` form field of the episode-create call,
# so the test can prove the draft path creates with status=draft (and verifies
# + deletes the draft) while the normal path still publishes with
# status=publish. Proves:
#   1. --draft creates the episode with status=draft, fetches it back, deletes
#      it, and reports status=draft-verified (never goes live).
#   2. Without --draft, the normal publish path is unchanged (status=publish,
#      result status=published, no delete call).
# Run:  python3 -m unittest 58-podcast-production-engine/scripts/tests/test_podbean_draft_mode.py
# =============================================================================
"""Deterministic tests for the podcast --draft verification mode (U044)."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_SCRIPT = _HERE.parent.parent / "podbean_publish.sh"

# Mock curl: parses the -K config for method + url, captures any `status=`
# --data-urlencode field, logs each call, and prints "<json body>\n<status>".
MOCK_CURL = r'''#!/usr/bin/env bash
url=""; method=""; prev=""; statusfield=""
for a in "$@"; do
  if [ "$prev" = "-K" ] && [ -r "$a" ]; then
    while IFS= read -r line; do
      case "$line" in
        'url = '*)     url="${line#url = \"}"; url="${url%\"}" ;;
        'request = '*) method="${line#request = \"}"; method="${method%\"}" ;;
      esac
    done < "$a"
  fi
  case "$a" in
    status=*) statusfield="$a" ;;
  esac
  prev="$a"
done
[ -n "${MOCK_CALL_LOG:-}" ] && printf '%s|%s|%s|%s\n' "$(date +%s)" "$method" "$url" "$statusfield" >> "$MOCK_CALL_LOG"
status=""
if [ -n "${MOCK_SCRIPT:-}" ] && [ -f "$MOCK_SCRIPT" ]; then
  status="$(head -1 "$MOCK_SCRIPT" 2>/dev/null)"
  sed -i.bak '1d' "$MOCK_SCRIPT" 2>/dev/null; rm -f "$MOCK_SCRIPT.bak"
fi
status="${status:-200}"
body="{}"
case "$method $url" in
  'POST '*oauth/token*)     body='{"access_token":"mock-token"}' ;;
  'GET '*'/podcasts?'*)     body='{"podcasts":[{"id":"12345"}]}' ;;
  'GET '*'/episodes/'*)     body='{"episode":{"status":"draft"}}' ;;
  'DELETE '*'/episodes/'*)  body='{}' ;;
  'GET '*'/episodes?'*)     body='{"count":0}' ;;
  'GET '*uploadAuthorize*)  body='{"presigned_url":"http://mock.invalid/presigned","file_key":"mock-key"}' ;;
  'PUT '*)                  body='' ;;
  'POST '*'/episodes'*)     body='{"episode":{"permalink_url":"https://mock.podbean.com/ep/1","id":"ep-1"}}' ;;
esac
printf '%s\n%s' "$body" "$status"
'''


class TestPodbeanDraftMode(unittest.TestCase):
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
        self.status_file.write_text("\n")  # all calls default to 200

    def run_publish(self, extra_args):
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
        })
        for k in ("PODBEAN_PUBLISH_WEBHOOK_URL", "PODBEAN_PUBLISH_TOKEN",
                  "PODBEAN_BROKER_WEBHOOK_URL", "PODBEAN_BROKER_TOKEN"):
            env.pop(k, None)
        return subprocess.run(
            ["bash", str(_SCRIPT), "--audio", str(self.audio),
             "--title", "Test Episode", *extra_args],
            env=env, capture_output=True, text=True, timeout=120,
        )

    def calls(self):
        if not self.call_log.exists():
            return []
        out = []
        for ln in self.call_log.read_text().splitlines():
            if not ln.strip():
                continue
            parts = ln.split("|")
            out.append({"ts": parts[0], "method": parts[1], "url": parts[2],
                        "status": parts[3] if len(parts) > 3 else ""})
        return out

    def create_call(self):
        for c in self.calls():
            if c["method"] == "POST" and "/episodes" in c["url"] and "oauth" not in c["url"]:
                return c
        return None

    def test_draft_creates_draft_verifies_and_deletes(self):
        """AC#2 + AC#3 + AC#4: --draft creates with status=draft, fetches it
        back, deletes it, and reports draft-verified (never goes live)."""
        r = self.run_publish(["--draft"])
        self.assertEqual(r.returncode, 0, f"stderr: {r.stderr}")
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(out["status"], "draft-verified")
        self.assertTrue(out["draft"])
        self.assertEqual(out["publish_status"], "draft")
        self.assertTrue(out["deleted"], "the verification draft must be deleted")

        # The create call must carry status=draft (not publish).
        cc = self.create_call()
        self.assertIsNotNone(cc, "no episode-create call was made")
        self.assertEqual(cc["status"], "status=draft",
                         "draft mode must create the episode with status=draft")

        # A fetch-back (GET /episodes/<id>) and a DELETE /episodes/<id> happened.
        methods_urls = [(c["method"], c["url"]) for c in self.calls()]
        self.assertTrue(any(m == "GET" and "/episodes/ep-1" in u for m, u in methods_urls),
                        "draft must be fetched back for verification")
        self.assertTrue(any(m == "DELETE" and "/episodes/ep-1" in u for m, u in methods_urls),
                        "draft must be deleted after verification")

    def test_without_draft_normal_publish_unchanged(self):
        """AC#5: without --draft the normal publish path is used (status=publish,
        result published, and NO delete call)."""
        r = self.run_publish([])
        self.assertEqual(r.returncode, 0, f"stderr: {r.stderr}")
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(out["status"], "published")
        self.assertNotIn("draft", out.get("status", ""))

        cc = self.create_call()
        self.assertIsNotNone(cc)
        self.assertEqual(cc["status"], "status=publish",
                         "normal mode must create the episode with status=publish")

        # No DELETE call in the normal path.
        self.assertFalse(any(c["method"] == "DELETE" for c in self.calls()),
                         "normal publish must not delete anything")

    def test_draft_wins_over_status_override(self):
        """--draft wins over an explicit --status publish (a draft can never go
        live by accident)."""
        r = self.run_publish(["--draft", "--status", "publish"])
        self.assertEqual(r.returncode, 0, f"stderr: {r.stderr}")
        cc = self.create_call()
        self.assertEqual(cc["status"], "status=draft")


if __name__ == "__main__":
    unittest.main(verbosity=2)
