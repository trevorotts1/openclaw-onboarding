#!/usr/bin/env python3
# =============================================================================
# SKILL 58 - PODCAST PRODUCTION ENGINE :: podbean_publish.sh publish-proxy tests
# -----------------------------------------------------------------------------
# Exercises the publish-proxy transport (mode precedence proxy -> broker ->
# local; contract v2 payload; response handling for happy path, standing-block,
# identity-mismatch, idempotent replay, network retry, 409 in_flight, 5xx
# exhaustion, and 422 invalid_payload) end to end as a real subprocess, with a
# mocked `curl` on PATH so nothing touches the network. No shell logic is
# reimplemented in Python - every assertion reads podbean_publish.sh's actual
# stdout JSON, exit code, and the mocked curl's call log.
#
# The mock curl also proves mode precedence (which URL was actually posted to)
# and secret hygiene (the shared header token never appears in the mock's
# argv-based call log, because podbean_publish.sh passes it through a curl -K
# config file via process substitution, never argv).
#
# Run:  python3 -m unittest 58-podcast-production-engine/scripts/tests/test_podbean_publish_proxy.py
#   or: python3 -m pytest 58-podcast-production-engine/scripts/tests/test_podbean_publish_proxy.py
# =============================================================================
"""Tests for podbean_publish.sh's publish-proxy transport (precedence proxy -> broker -> local)."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_SCRIPT = _HERE.parent.parent / "podbean_publish.sh"

_MOCK_CURL = r'''#!/usr/bin/env python3
import os
import sys

argv = sys.argv[1:]
calllog_path = os.environ.get("MOCK_CURL_CALLLOG")
bodylog_path = os.environ.get("MOCK_CURL_BODYLOG")
queue_path = os.environ.get("MOCK_CURL_QUEUE")

cfg_path = None
if "-K" in argv:
    cfg_path = argv[argv.index("-K") + 1]

if calllog_path and cfg_path and os.path.exists(cfg_path):
    with open(cfg_path) as f:
        cfg = f.read()
    method = ""
    url = ""
    has_header = False
    for line in cfg.splitlines():
        line = line.strip()
        if line.startswith("request ="):
            method = line.split("=", 1)[1].strip().strip('"')
        elif line.startswith("url ="):
            url = line.split("=", 1)[1].strip().strip('"')
        elif line.startswith("header =") and "Token" in line:
            has_header = True
    with open(calllog_path, "a") as f:
        f.write("%s %s header_present=%s\n" % (method, url, has_header))
elif calllog_path:
    with open(calllog_path, "a") as f:
        f.write(" ".join(argv) + "\n")

# Record the JSON body passed via --data (argv) so tests can assert the
# CONTENTS of the outgoing payload, not just that a call happened. The shared
# auth token is never here - it only ever appears in the -K config file above,
# which this mock reads for method/url/header-presence only and never logs.
if bodylog_path and "--data" in argv:
    body_value = argv[argv.index("--data") + 1]
    with open(bodylog_path, "a") as f:
        f.write(body_value + "\n===BODYEND===\n")

if not queue_path or not os.path.exists(queue_path):
    sys.exit(0)

with open(queue_path) as f:
    content = f.read()

blocks = content.split("\n---\n")
if not blocks or blocks == [""]:
    sys.exit(0)

this_block = blocks[0]
remaining = blocks[1:]
with open(queue_path, "w") as f:
    f.write("\n---\n".join(remaining))

nl_idx = this_block.find("\n")
if nl_idx == -1:
    status, body = this_block, ""
else:
    status, body = this_block[:nl_idx], this_block[nl_idx + 1:]

if status == "NETFAIL":
    sys.exit(7)

sys.stdout.write(body)
if not body.endswith("\n"):
    sys.stdout.write("\n")
sys.stdout.write(status)
sys.exit(0)
'''

_SECRET_TOKEN = "unit-test-secret-token-do-not-leak-9f8e7d6c"


class PodbeanPublishProxyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="podbean-proxy-test-"))
        self.mockbin = self.tmp / "mockbin"
        self.mockbin.mkdir()
        curl_path = self.mockbin / "curl"
        curl_path.write_text(_MOCK_CURL)
        curl_path.chmod(curl_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

        self.queue_path = self.tmp / "queue"
        self.calllog_path = self.tmp / "calllog"
        self.bodylog_path = self.tmp / "bodylog"

        self.audio = self.tmp / "audio.mp3"
        self.audio.write_bytes(b"fake mp3 bytes")

        real_path = os.environ.get("PATH", "/usr/bin:/bin")
        self.base_env = {
            "PATH": f"{self.mockbin}:{real_path}",
            "HOME": os.environ.get("HOME", str(self.tmp)),
            "MOCK_CURL_QUEUE": str(self.queue_path),
            "MOCK_CURL_CALLLOG": str(self.calllog_path),
            "MOCK_CURL_BODYLOG": str(self.bodylog_path),
        }

    def _set_queue(self, *blocks: str) -> None:
        self.queue_path.write_text("\n---\n".join(blocks))

    def _calllog_lines(self) -> list[str]:
        if not self.calllog_path.exists():
            return []
        return [ln for ln in self.calllog_path.read_text().splitlines() if ln.strip()]

    def _sent_payloads(self) -> list[dict]:
        """Every JSON body actually POSTed to the mock, in call order."""
        if not self.bodylog_path.exists():
            return []
        raw = self.bodylog_path.read_text()
        chunks = [c for c in raw.split("\n===BODYEND===\n") if c.strip()]
        return [json.loads(c) for c in chunks]

    def _run(self, extra_env: dict, args: list[str]) -> subprocess.CompletedProcess:
        env = dict(self.base_env)
        env.update(extra_env)
        cmd = ["bash", str(_SCRIPT), "--audio", str(self.audio), "--title", "Unit Test Episode"] + args
        return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)

    def _proxy_env(self, **overrides) -> dict:
        env = {
            "PODBEAN_PODCAST_ID": "chan-abc123",
            "PODBEAN_PUBLISH_WEBHOOK_URL": "https://n8n.example/webhook/podbean-publish",
            "PODBEAN_PUBLISH_TOKEN": _SECRET_TOKEN,
            "PODCAST_CLIENT_LAST_NAME": "Smith",
            "PODCAST_CLIENT_EMAIL": "smith@example.com",
        }
        env.update(overrides)
        return env

    def _proxy_args(self, **overrides) -> list[str]:
        args = {
            "--audio-url": "https://media.example.com/ep1.mp3",
            "--image-url": "https://media.example.com/cover.jpg",
            "--idempotency-key": "idem-key-1",
        }
        args.update(overrides)
        out = []
        for k, v in args.items():
            if v is None:
                continue
            out += [k, v]
        return out

    # -- happy path --------------------------------------------------------
    def test_proxy_happy_path_publishes_and_records_permalink(self):
        self._set_queue(
            '200\n{"ok":true,"permalink_url":"https://x.podbean.com/e/ep1",'
            '"episode_id":"ep_1","episode_number":7,"idempotent_replay":false}'
        )
        r = self._run(self._proxy_env(), self._proxy_args())
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(out["status"], "published")
        self.assertEqual(out["transport"], "publish-proxy")
        self.assertEqual(out["permalink_url"], "https://x.podbean.com/e/ep1")
        self.assertEqual(out["episode_number"], 7)
        self.assertFalse(out["idempotent_replay"])
        self.assertEqual(len(self._calllog_lines()), 1)

    def test_proxy_payload_carries_all_contract_v2_required_fields(self):
        self._set_queue('200\n{"ok":true,"permalink_url":"https://x.podbean.com/e/ep1"}')
        r = self._run(
            self._proxy_env(),
            self._proxy_args() + ["--description", "show notes here", "--release-date", "1234567890"],
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        payloads = self._sent_payloads()
        self.assertEqual(len(payloads), 1)
        body = payloads[0]
        required = [
            "contract_version", "podcast_id", "client_last_name", "client_email",
            "title", "description", "audio_url", "image_url", "publish_date",
            "idempotency_key",
        ]
        for field in required:
            self.assertIn(field, body, f"contract v2 payload missing required field {field!r}")
        self.assertEqual(body["contract_version"], "2")
        self.assertEqual(body["podcast_id"], "chan-abc123")
        self.assertEqual(body["client_last_name"], "Smith")
        self.assertEqual(body["client_email"], "smith@example.com")
        self.assertEqual(body["audio_url"], "https://media.example.com/ep1.mp3")
        self.assertEqual(body["image_url"], "https://media.example.com/cover.jpg")
        self.assertEqual(body["idempotency_key"], "idem-key-1")
        self.assertEqual(body["episode_type"], "full")
        self.assertEqual(body["explicit"], "clean")
        # never sent, per the contract's "never sent" rule
        for banned in ("episode_number", "client_id", "client_secret", "access_token",
                       "PODBEAN_PUBLISH_TOKEN"):
            self.assertNotIn(banned, body)

    def test_proxy_payload_carries_optional_fields_when_supplied(self):
        self._set_queue('200\n{"ok":true,"permalink_url":"https://x.podbean.com/e/ep1"}')
        r = self._run(
            self._proxy_env(PODCAST_CLIENT_FIRST_NAME="Jane"),
            self._proxy_args()
            + ["--speaker", "Guest Name", "--episode-type", "trailer", "--explicit", "explicit",
               "--season-number", "3"],
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        body = self._sent_payloads()[0]
        self.assertEqual(body["client_first_name"], "Jane")
        self.assertEqual(body["speaker"], "Guest Name")
        self.assertEqual(body["episode_type"], "trailer")
        self.assertEqual(body["explicit"], "explicit")
        self.assertEqual(body["season_number"], 3)

    def test_proxy_posts_to_the_proxy_url_with_auth_header(self):
        self._set_queue('200\n{"ok":true,"permalink_url":"https://x.podbean.com/e/ep1"}')
        self._run(self._proxy_env(), self._proxy_args())
        lines = self._calllog_lines()
        self.assertEqual(len(lines), 1)
        self.assertIn("POST https://n8n.example/webhook/podbean-publish", lines[0])
        self.assertIn("header_present=True", lines[0])

    def test_proxy_never_leaks_the_token_value_into_argv_or_output(self):
        self._set_queue('200\n{"ok":true,"permalink_url":"https://x.podbean.com/e/ep1"}')
        r = self._run(self._proxy_env(), self._proxy_args())
        haystacks = [r.stdout, r.stderr] + self._calllog_lines()
        for h in haystacks:
            self.assertNotIn(_SECRET_TOKEN, h)

    # -- title/speaker semantics (n8n appends, not this script) -----------
    def test_proxy_sends_raw_title_not_speaker_appended_title(self):
        self._set_queue('200\n{"ok":true,"permalink_url":"https://x.podbean.com/e/ep1"}')
        r = self._run(self._proxy_env(), self._proxy_args() + ["--speaker", "Jane Doe"])
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(out["episode_title"], "Unit Test Episode")
        self.assertNotIn("Inspired by", out["episode_title"])

    # -- good-standing / identity refusals (terminal, exactly one call) ---
    def test_proxy_not_in_good_standing_blocks_with_distinct_exit_code(self):
        self._set_queue(
            '403\n{"ok":false,"reason":"not_in_good_standing",'
            '"message":"you are not in good standing"}'
        )
        r = self._run(self._proxy_env(), self._proxy_args())
        self.assertEqual(r.returncode, 3, r.stderr)
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(out, {"status": "blocked", "reason": "not_in_good_standing"})
        self.assertEqual(len(self._calllog_lines()), 1, "a refusal must not be retried")

    def test_proxy_identity_mismatch_blocks_without_retry(self):
        self._set_queue('403\n{"ok":false,"reason":"identity_mismatch"}')
        r = self._run(self._proxy_env(), self._proxy_args())
        self.assertEqual(r.returncode, 3, r.stderr)
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(out, {"status": "blocked", "reason": "identity_mismatch"})
        self.assertEqual(len(self._calllog_lines()), 1)

    def test_proxy_identity_unknown_blocks_without_retry(self):
        self._set_queue('403\n{"ok":false,"reason":"identity_unknown"}')
        r = self._run(self._proxy_env(), self._proxy_args())
        self.assertEqual(r.returncode, 3, r.stderr)
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(out, {"status": "blocked", "reason": "identity_unknown"})

    # -- idempotent replay ---------------------------------------------------
    def test_proxy_idempotent_replay_reports_true_and_reuses_permalink(self):
        self._set_queue(
            '200\n{"ok":true,"idempotent_replay":true,"permalink_url":"https://x.podbean.com/e/ep1"}'
        )
        r = self._run(self._proxy_env(), self._proxy_args())
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertTrue(out["idempotent_replay"])
        self.assertEqual(out["permalink_url"], "https://x.podbean.com/e/ep1")

    # -- network / 5xx / 409 retry classification --------------------------
    def test_proxy_retries_once_on_network_failure_then_succeeds(self):
        self._set_queue("NETFAIL\n", '200\n{"ok":true,"permalink_url":"https://x.podbean.com/e/ep1","episode_number":1}')
        r = self._run(self._proxy_env(), self._proxy_args())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self._calllog_lines()), 2, "exactly one retry expected")

    def test_proxy_retries_on_5xx_then_succeeds(self):
        self._set_queue(
            '500\n{"ok":false,"reason":"publish_failed"}',
            '200\n{"ok":true,"permalink_url":"https://x.podbean.com/e/ep1","episode_number":1}',
        )
        r = self._run(self._proxy_env(), self._proxy_args())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self._calllog_lines()), 2)

    def test_proxy_gives_up_after_retries_exhausted_on_persistent_5xx(self):
        self._set_queue(
            '500\n{"ok":false}', '500\n{"ok":false}', '500\n{"ok":false}', '500\n{"ok":false}'
        )
        r = self._run(self._proxy_env(), self._proxy_args())
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(len(self._calllog_lines()), 3, "must stop after RETRIES=3 attempts, not loop forever")

    def test_proxy_409_in_flight_exhausts_retries_and_reports_conflict(self):
        self._set_queue(
            '409\n{"ok":false,"reason":"in_flight"}',
            '409\n{"ok":false,"reason":"in_flight"}',
            '409\n{"ok":false,"reason":"in_flight"}',
        )
        r = self._run(self._proxy_env(), self._proxy_args())
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("in_flight", r.stderr)
        self.assertEqual(len(self._calllog_lines()), 3)

    # -- terminal, non-retried failure ---------------------------------------
    def test_proxy_422_invalid_payload_fails_immediately_without_retry(self):
        self._set_queue('422\n{"ok":false,"reason":"invalid_payload","missing":["title"]}')
        r = self._run(self._proxy_env(), self._proxy_args())
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(len(self._calllog_lines()), 1, "invalid_payload is a caller bug, not retry-worthy")

    # -- required-field fail-loud (U15 doctrine) -----------------------------
    def test_proxy_dies_loudly_when_last_name_missing(self):
        env = self._proxy_env()
        del env["PODCAST_CLIENT_LAST_NAME"]
        r = self._run(env, self._proxy_args())
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("PODCAST_CLIENT_LAST_NAME", r.stderr)
        self.assertEqual(len(self._calllog_lines()), 0, "must fail before any network call")

    def test_proxy_dies_loudly_when_email_missing(self):
        env = self._proxy_env()
        del env["PODCAST_CLIENT_EMAIL"]
        r = self._run(env, self._proxy_args())
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("PODCAST_CLIENT_EMAIL", r.stderr)
        self.assertEqual(len(self._calllog_lines()), 0)

    def test_proxy_dies_loudly_when_audio_url_missing(self):
        r = self._run(self._proxy_env(), self._proxy_args(**{"--audio-url": None}))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--audio-url", r.stderr)
        self.assertEqual(len(self._calllog_lines()), 0)

    def test_proxy_dies_loudly_when_image_url_missing(self):
        r = self._run(self._proxy_env(), self._proxy_args(**{"--image-url": None}))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--image-url", r.stderr)

    def test_proxy_dies_loudly_when_idempotency_key_and_job_id_both_absent(self):
        r = self._run(self._proxy_env(), self._proxy_args(**{"--idempotency-key": None}))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("idempotency", r.stderr.lower())

    def test_proxy_idempotency_key_falls_back_to_job_id(self):
        self._set_queue('200\n{"ok":true,"permalink_url":"https://x.podbean.com/e/ep1"}')
        r = self._run(
            self._proxy_env(),
            self._proxy_args(**{"--idempotency-key": None}) + ["--job-id", "job-fallback-99"],
        )
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_proxy_dies_loudly_when_only_one_of_the_pair_is_set(self):
        env = self._proxy_env()
        del env["PODBEAN_PUBLISH_TOKEN"]
        r = self._run(env, self._proxy_args())
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("PODBEAN_PUBLISH_TOKEN", r.stderr)
        self.assertEqual(len(self._calllog_lines()), 0)

    # -- precedence: proxy always wins when all three pairs are set ---------
    def test_proxy_wins_precedence_over_broker_and_local_when_all_are_set(self):
        self._set_queue('200\n{"ok":true,"permalink_url":"https://x.podbean.com/e/ep1"}')
        env = self._proxy_env(
            PODBEAN_BROKER_WEBHOOK_URL="https://n8n.example/webhook/podbean-broker",
            PODBEAN_BROKER_TOKEN="broker-tok",
            PODBEAN_CLIENT_ID="local-client-id-1234567890",
            PODBEAN_CLIENT_SECRET="local-client-secret-1234567890",
        )
        r = self._run(env, self._proxy_args())
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = self._calllog_lines()
        self.assertEqual(len(lines), 1)
        self.assertIn("podbean-publish", lines[0])
        self.assertNotIn("podbean-broker", lines[0])

    # -- dry-run: validates and never touches the network --------------------
    def test_proxy_dry_run_never_calls_curl(self):
        r = self._run(self._proxy_env(), self._proxy_args() + ["--dry-run"])
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(out["status"], "dry-run")
        self.assertEqual(out["transport"], "publish-proxy")
        self.assertEqual(self._calllog_lines(), [])

    # -- test flag: still validates required proxy fields, no network -------
    def test_proxy_test_flag_short_circuits_before_any_network_call(self):
        r = self._run(self._proxy_env(), self._proxy_args() + ["--test"])
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(out["status"], "test-skipped")
        self.assertEqual(self._calllog_lines(), [])

    def test_proxy_test_flag_still_dies_loudly_on_missing_identity(self):
        env = self._proxy_env()
        del env["PODCAST_CLIENT_EMAIL"]
        r = self._run(env, self._proxy_args() + ["--test"])
        self.assertNotEqual(r.returncode, 0)

    # -- regression: proxy env UNSET behaves exactly as before this fix -----
    def test_regression_proxy_unset_broker_mode_test_flag_unaffected(self):
        env = {
            "PODBEAN_PODCAST_ID": "chan-abc123",
            "PODBEAN_BROKER_WEBHOOK_URL": "https://n8n.example/webhook/podbean-broker",
            "PODBEAN_BROKER_TOKEN": "broker-tok",
        }
        r = self._run(env, ["--test"])
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(out["status"], "test-skipped")
        self.assertEqual(out["episode_title"], "Unit Test Episode")
        self.assertEqual(self._calllog_lines(), [])

    def test_regression_proxy_unset_local_mode_missing_creds_dies_as_before(self):
        env = {"PODBEAN_PODCAST_ID": "chan-abc123"}
        r = self._run(env, ["--test"])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("PODBEAN_CLIENT_ID", r.stderr)


if __name__ == "__main__":
    unittest.main()
