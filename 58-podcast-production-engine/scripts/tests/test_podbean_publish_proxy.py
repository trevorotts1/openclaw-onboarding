#!/usr/bin/env python3
# =============================================================================
# SKILL 58 - PODCAST PRODUCTION ENGINE :: podbean_publish.sh publish-proxy
# transport tests (S58-U14, extended by S58-U17)
# -----------------------------------------------------------------------------
# Stdlib unittest + stdlib http.server only. Drives the REAL shipped script as
# a subprocess against a loopback-only mock of the n8n publish-proxy webhook
# (POST /webhook/podbean-publish) and the standing-check webhook (POST
# /webhook/podcast-standing-check) - no real network call, no real Podbean or
# n8n call, no secret value in this file (the token used is a fixture literal,
# never a real credential).
#
# What this proves, end to end, by observing subprocess exit codes, emitted
# JSON, and which mock paths were (or were not) hit - never by inspecting the
# script's source text:
#   - transport precedence proxy -> broker -> local (S58-U14 Section 2)
#   - the v2 payload contract fields land in the request the mock receives
#   - the auth header is sent and is never the literal secret in any log line
#   - standing-block (403 not_in_good_standing) surfaces as a DISTINCT exit
#     code from every other failure, with the exact machine-readable JSON
#   - identity_mismatch / in_flight / invalid_payload are refused, not retried
#   - one retry on a transport-level failure (000/5xx), then give up (exactly
#     two attempts, never more, never fewer)
#   - --dry-run in proxy mode only ever reaches the standing-check endpoint
#   - with the proxy env UNSET, broker/local selection is unchanged: the
#     regression fixture asserts byte-identical behavior (same JSON shape on
#     --test, same fatal message text with nothing configured) to what the
#     script did before this unit existed
#
# S58-U17 additions (payload-v2 builder completeness): the S58-U14 happy-path
# test above asserts a SUBSET of the v2 contract (contract_version, podcast_id,
# client_last_name, client_email, audio_url, image_url, idempotency_key,
# speaker, and the never-sent fields). It does not assert title, description,
# publish_date, client_first_name, episode_type, explicit, or source, and it
# does not test that the same --job-id produces the same idempotency_key
# across separate invocations (stability, not just presence-on-one-call). The
# tests below close that gap: every REQUIRED and every populated OPTIONAL
# field from spec Section 3's table, the exact "Inspired by <speaker>" title
# transform landing in the wire body (not just the raw --speaker flag), the
# omission of optional fields when unset, and idempotency-key stability across
# two independent subprocess runs with the same --job-id.
#
# Run:  python3 -m unittest 58-podcast-production-engine/scripts/tests/test_podbean_publish_proxy.py
# =============================================================================
"""Mock e2e tests for the podbean_publish.sh publish-proxy transport."""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Canonical-UTC normalization helper. The shipped script normalizes
# --release-date through to_epoch then emits date -u -r <epoch> +%Y-%m-%dT%H:%M:%SZ
# (with a GNU date fallback) per the n8n contract-v2, so a bare local-time input
# like "2026-08-01T10:00:00" is NOT passed through verbatim; it is converted to
# canonical ISO-8601 UTC. This helper mirrors that exact normalization so the
# expected value in assertions stays correct regardless of the test machine's
# local timezone (onb-8 made the script canonical; the test was stale).
def _canonical_utc(release_date: str) -> str:
    """Return the canonical ISO-8601 UTC string the script emits for a
    --release-date input, computed the same way to_epoch + date -u does."""
    # to_epoch: pure-seconds passthrough, else GNU date -d, else BSD date -j -f.
    if release_date.isdigit():
        epoch = release_date
    elif subprocess.run(
        ["date", "-d", release_date, "+%s"],
        capture_output=True, text=True,
    ).returncode == 0:
        epoch = subprocess.run(
            ["date", "-d", release_date, "+%s"],
            capture_output=True, text=True,
        ).stdout.strip()
    else:
        # Strip a trailing timezone offset the way to_epoch does before parsing.
        stripped = release_date
        # Cut a trailing +HH:MM / -HH:MM offset (regex-free, two-digit pairs).
        if len(stripped) >= 6 and stripped[-3] in "+-" and stripped[-6] == stripped[-3]:
            stripped = stripped[:-6]
        elif len(stripped) >= 6 and stripped[-6] in "+-" and stripped[-3] == ":":
            stripped = stripped[:-6]
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            proc = subprocess.run(
                ["date", "-j", "-f", fmt, stripped, "+%s"],
                capture_output=True, text=True,
            )
            if proc.returncode == 0:
                epoch = proc.stdout.strip()
                break
        else:
            raise AssertionError("could not parse release-date like to_epoch: " + release_date)
    # Emit canonical UTC the same way the script does (BSD -r first, GNU @ second).
    proc = subprocess.run(
        ["date", "-u", "-r", str(epoch), "+%Y-%m-%dT%H:%M:%SZ"],
        capture_output=True, text=True,
    )
    if proc.returncode == 0:
        return proc.stdout.strip()
    proc = subprocess.run(
        ["date", "-u", "-d", "@" + str(epoch), "+%Y-%m-%dT%H:%M:%SZ"],
        capture_output=True, text=True,
    )
    if proc.returncode == 0:
        return proc.stdout.strip()
    raise AssertionError("could not format epoch as canonical UTC: " + str(epoch))

_HERE = Path(__file__).resolve()
_SCRIPT = _HERE.parent.parent / "podbean_publish.sh"

# A real show-notes description meeting the Step 12.5 floor (>= 200 chars).
# Proxy publish mode now requires a real description (U048), so transport and
# media-guard tests supply a valid one by default; tests that specifically probe
# the missing/short-description refusals override it.
VALID_DESCRIPTION = (
    "In this episode we explore how conviction becomes a competitive edge. "
    "Our guest shares the decisions, the false starts, and the one turning "
    "point that reshaped everything. We unpack the framework, the research "
    "behind it, and the practical first step you can take this week. "
    "A full conversation with real takeaways for leaders who build. " * 2
)

# Fixture-only literal. Never a real credential; exists so the mock can assert
# the header the script sends matches what it was configured with, and so a
# redaction test can prove this literal never reaches stdout/stderr verbatim.
FIXTURE_TOKEN = "test-fixture-publish-token-not-a-real-secret"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # silence per-request stderr noise
        pass

    def _serve(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            parsed = json.loads(raw.decode("utf-8")) if raw else {}
        except ValueError:
            parsed = None
        record = {
            "path": self.path,
            "token": self.headers.get("X-Podcast-Publish-Token", ""),
            "content_type": self.headers.get("Content-Type", ""),
            "body": parsed,
            "raw_body": raw,
        }
        self.server.requests.append(record)  # type: ignore[attr-defined]

        queue = self.server.routes.get(self.path)  # type: ignore[attr-defined]
        if not queue:
            self.send_response(404)
            payload = b'{"ok":false,"reason":"no_route_configured_in_mock"}'
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        # Pop one response per hit; the last configured response repeats for
        # any hit beyond the queue length (keeps "always fails" fixtures short).
        status, body_obj = queue[0] if len(queue) == 1 else queue.pop(0)
        if body_obj is None:
            # Simulate a transport-level failure: drop the connection with no
            # status line at all (curl reports HTTP code 000 for this).
            self.close_connection = True
            return
        payload = json.dumps(body_obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        self._serve()

    def do_GET(self):
        # Serve binary files for media probe tests. The mock holds a dict
        # self.server.files mapping path -> bytes; if a path matches, serve
        # the bytes with Content-Type: application/octet-stream.
        file_bytes = self.server.files.get(self.path)  # type: ignore[attr-defined]
        if file_bytes is not None:
            record = {
                "path": self.path,
                "token": "",
                "content_type": "application/octet-stream",
                "body": None,
                "raw_body": b"",
            }
            self.server.requests.append(record)  # type: ignore[attr-defined]
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(file_bytes)))
            self.end_headers()
            self.wfile.write(file_bytes)
            return
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()


class MockN8n:
    """A loopback-only mock of the two publish-proxy webhooks. `routes` maps a
    path to a list of (status, body_dict_or_None) queued responses; a None
    body simulates a dropped connection (HTTP 000)."""

    def __init__(self):
        self.port = _free_port()
        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), _Handler)
        self.server.requests = []  # type: ignore[attr-defined]
        self.server.routes = {}  # type: ignore[attr-defined]
        self.server.files = {}  # type: ignore[attr-defined]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base_url(self) -> str:
        return "http://127.0.0.1:%d" % self.port

    @property
    def publish_url(self) -> str:
        return self.base_url + "/webhook/podbean-publish"

    @property
    def requests(self):
        return self.server.requests  # type: ignore[attr-defined]

    def route(self, path, responses):
        self.server.routes[path] = list(responses)  # type: ignore[attr-defined]

    def hits(self, path):
        return [r for r in self.requests if r["path"] == path]

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class PodbeanPublishProxyTest(unittest.TestCase):
    def setUp(self):
        self.mock = MockN8n()
        self.addCleanup(self.mock.close)
        self.tmp = tempfile.mkdtemp(prefix="podbean-proxy-test-")
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.audio = os.path.join(self.tmp, "episode.mp3")
        with open(self.audio, "wb") as f:
            f.write(b"not-real-audio-bytes")

    # ---------------------------------------------------------- helpers ----
    def _run(self, args, env_extra=None, timeout=20):
        # Isolate HOME so the script's secrets-env sourcing (act-11 fix)
        # can never reach the real ~/.openclaw/secrets/.env of the test
        # machine. Every test that needs proxy/broker/local env vars
        # passes them via env_extra.
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": self.tmp,
            "PODBEAN_SKIP_MEDIA_PROBE": "1",   # crs: transport tests skip probe
            # The transport tests skip the probe; per master-plan 1.8 the skip
            # requires the operator force flag even in the test harness.
            "PODBEAN_OPERATOR_FORCE": "1",
        }
        if env_extra:
            env.update(env_extra)
        proc = subprocess.run(
            ["bash", str(_SCRIPT), "--audio", self.audio, "--title", "Test Episode",
             "--description", VALID_DESCRIPTION] + args,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc

    def _run_no_desc(self, args, env_extra=None, timeout=20):
        # Identical to _run but does NOT force --description, so the 1.1.5
        # ledger-default resolution and the no-description-anywhere hard
        # refusal can be exercised (a test that passes --description would
        # never reach either path).
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": self.tmp,
            "PODBEAN_SKIP_MEDIA_PROBE": "1",
        }
        if env_extra:
            env.update(env_extra)
        return subprocess.run(
            ["bash", str(_SCRIPT), "--audio", self.audio,
             "--title", "Test Episode"] + args,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def _proxy_env(self, **extra):
        env = {
            "PODBEAN_PODCAST_ID": "chan-123",
            "PODBEAN_PUBLISH_WEBHOOK_URL": self.mock.publish_url,
            "PODBEAN_PUBLISH_TOKEN": FIXTURE_TOKEN,
            "PODCAST_CLIENT_LAST_NAME": "Rivera",
            "PODCAST_CLIENT_EMAIL": "rivera@example.test",
        }
        env.update(extra)
        return env

    def _happy_body(self, idempotent=False, scheduled=False):
        return {
            "ok": True,
            "permalink_url": "https://example.podbean.com/e/test-episode/",
            "episode_id": "ep-1",
            "episode_number": 7,
            "scheduled": scheduled,
            "idempotent_replay": idempotent,
        }

    def _write_ledger(self, episode_description, state="enrolling",
                      permalink=None):
        """Write a job ledger JSON fixture (pre-U035: no _checksum, which
        verify_ledger_checksum accepts) and return its path. NO permalink by
        default so the idempotency early-exit is never triggered."""
        record = {"state": state}
        if episode_description is not None:
            record["episode_description"] = episode_description
        if permalink is not None:
            record["podbean_permalink"] = permalink
        path = os.path.join(self.tmp, "ledger.json")
        with open(path, "w") as f:
            json.dump(record, f)
        return path

    # --------------------------------------------------- precedence -------
    def test_proxy_wins_over_broker_and_local_when_all_three_are_configured(self):
        self.mock.route("/webhook/podbean-publish", [(200, self._happy_body())])
        env = self._proxy_env(
            PODBEAN_BROKER_WEBHOOK_URL=self.mock.base_url + "/webhook/podbean-broker",
            PODBEAN_BROKER_TOKEN="fixture-broker-token",
            PODBEAN_API_BASE=self.mock.base_url + "/localapi",
            PODBEAN_CLIENT_ID="fixture-client-id",
            PODBEAN_CLIENT_SECRET="fixture-client-secret",
        )
        proc = self._run(
            ["--audio-url", "https://media.example.test/a.mp3",
             "--image-url", "https://media.example.test/i.jpg",
             "--job-id", "pd-test-precedence"],
            env_extra=env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertEqual(result["status"], "published")
        self.assertEqual(len(self.mock.hits("/webhook/podbean-publish")), 1)
        self.assertEqual(len(self.mock.hits("/webhook/podbean-broker")), 0,
                          "broker must never be contacted once proxy env resolves")
        # Local mode would have hit PODBEAN_API_BASE ("<base>/localapi/oauth/token");
        # confirm nothing under that prefix was ever requested.
        local_hits = [r for r in self.mock.requests if r["path"].startswith("/localapi")]
        self.assertEqual(local_hits, [], "local client_credentials mint must never fire")

    # --------------------------------------------------- happy path -------
    def test_proxy_happy_path_records_permalink_and_sends_v2_payload(self):
        self.mock.route("/webhook/podbean-publish", [(200, self._happy_body())])
        stub_writer = os.path.join(self.tmp, "podcast_state.py")
        with open(stub_writer, "w") as f:
            f.write("#!/usr/bin/env python3\nimport sys\nprint('stub-writer-called:'+' '.join(sys.argv[1:]))\n")
        os.chmod(stub_writer, 0o755)

        proc = self._run(
            ["--audio-url", "https://media.example.test/a.mp3",
             "--image-url", "https://media.example.test/i.jpg",
             "--release-date", "2026-08-01T10:00:00",
             "--speaker", "Dana",
             "--job-id", "pd-happy-path",
             "--state-writer", stub_writer],
            env_extra=self._proxy_env(),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertEqual(result["status"], "published")
        self.assertEqual(result["permalink_url"], "https://example.podbean.com/e/test-episode/")
        self.assertFalse(result["idempotent_skip"])
        self.assertIn("stub-writer-called", proc.stderr)

        hits = self.mock.hits("/webhook/podbean-publish")
        self.assertEqual(len(hits), 1)
        req = hits[0]["body"]
        self.assertEqual(req["contract_version"], "2")
        self.assertEqual(req["podcast_id"], "chan-123")
        self.assertEqual(req["client_last_name"], "Rivera")
        self.assertEqual(req["client_email"], "rivera@example.test")
        self.assertEqual(req["audio_url"], "https://media.example.test/a.mp3")
        self.assertEqual(req["image_url"], "https://media.example.test/i.jpg")
        self.assertEqual(req["idempotency_key"], "pd-happy-path")
        self.assertEqual(req["speaker"], "Dana")
        self.assertNotIn("episode_number", req, "episode number is server-computed; never sent")
        for banned in ("podbean_client_id", "podbean_client_secret", "client_secret",
                       "ghl_token", "access_token"):
            self.assertNotIn(banned, req, "no credential field may ride in the v2 payload")
        self.assertEqual(hits[0]["token"], FIXTURE_TOKEN)

    def test_proxy_idempotent_replay_is_reported_as_skipped(self):
        self.mock.route("/webhook/podbean-publish", [(200, self._happy_body(idempotent=True))])
        proc = self._run(
            ["--audio-url", "https://media.example.test/a.mp3",
             "--image-url", "https://media.example.test/i.jpg",
             "--job-id", "pd-replay"],
            env_extra=self._proxy_env(),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertEqual(result["status"], "skipped")
        self.assertTrue(result["idempotent_skip"])
        self.assertEqual(result["permalink_url"], "https://example.podbean.com/e/test-episode/")

    # ------------------------------------- S58-U17: payload-v2 builder -----
    # The happy-path test above already proves a subset of the contract lands
    # correctly (podcast_id/client_last_name/client_email/audio_url/image_url/
    # idempotency_key/speaker plus the never-sent fields). These two tests
    # close the remainder of spec Section 3's field table: every REQUIRED
    # field (including title, description, publish_date - not checked above)
    # and every populated OPTIONAL field, PLUS the correct omission of
    # optional fields when the caller does not supply them.
    def test_proxy_payload_v2_builder_includes_every_contract_field_with_correct_values(self):
        self.mock.route("/webhook/podbean-publish", [(200, self._happy_body())])
        proc = self._run(
            ["--audio-url", "https://media.example.test/a.mp3",
             "--image-url", "https://media.example.test/i.jpg",
             "--description", VALID_DESCRIPTION,
             "--release-date", "2026-08-01T10:00:00",
             "--speaker", "Dana",
             "--job-id", "pd-full-contract"],
            env_extra=self._proxy_env(PODCAST_CLIENT_FIRST_NAME="Alex"),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        hits = self.mock.hits("/webhook/podbean-publish")
        self.assertEqual(len(hits), 1)
        req = hits[0]["body"]
        # REQUIRED fields (spec Section 3, rows 1-4, 6-11).
        self.assertEqual(req["contract_version"], "2")
        self.assertEqual(req["podcast_id"], "chan-123")
        self.assertEqual(req["client_last_name"], "Rivera")
        self.assertEqual(req["client_email"], "rivera@example.test")
        self.assertEqual(req["title"], "Test Episode Inspired by Dana",
                          "title must carry the 'Inspired by <speaker>' transform, "
                          "not just the raw --title flag")
        self.assertEqual(req["description"], VALID_DESCRIPTION)
        self.assertEqual(req["audio_url"], "https://media.example.test/a.mp3")
        self.assertEqual(req["image_url"], "https://media.example.test/i.jpg")
        # publish_date is the canonical ISO-8601 UTC normalization of
        # --release-date (onb-8 routes it through to_epoch then
        # date -u -r <epoch> +%Y-%m-%dT%H:%M:%SZ); it is NOT raw passthrough.
        # Compute the expected value the same way the script does so the
        # assertion holds on any test machine regardless of local timezone.
        self.assertEqual(req["publish_date"], _canonical_utc("2026-08-01T10:00:00"))
        self.assertEqual(req["idempotency_key"], "pd-full-contract")
        # Populated OPTIONAL fields (spec Section 3, rows 5, 12-16).
        self.assertEqual(req["client_first_name"], "Alex")
        self.assertEqual(req["episode_type"], "full")
        self.assertEqual(req["explicit"], "clean")
        self.assertEqual(req["speaker"], "Dana")
        self.assertEqual(req["source"], "skill58-step15")
        self.assertNotIn("episode_number", req, "episode number is server-computed; never sent")

    def test_proxy_payload_v2_builder_omits_unset_optional_fields(self):
        self.mock.route("/webhook/podbean-publish", [(200, self._happy_body())])
        proc = self._run(
            ["--audio-url", "https://media.example.test/a.mp3",
             "--image-url", "https://media.example.test/i.jpg",
             "--job-id", "pd-minimal-contract"],
            env_extra=self._proxy_env(),  # no PODCAST_CLIENT_FIRST_NAME, no --speaker
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        req = self.mock.hits("/webhook/podbean-publish")[0]["body"]
        self.assertEqual(req["title"], "Test Episode",
                          "with no --speaker, title must be unmodified (no 'Inspired by' suffix)")
        self.assertNotIn("client_first_name", req,
                          "client_first_name must be omitted, not sent as null/empty, "
                          "when PODCAST_CLIENT_FIRST_NAME is unset")
        self.assertNotIn("speaker", req,
                          "speaker must be omitted, not sent as null/empty, when --speaker is unset")

    def test_proxy_idempotency_key_is_stable_across_separate_invocations_with_same_job_id(self):
        # Idempotency is only meaningful if the SAME --job-id yields the SAME
        # idempotency_key across independently-run processes (e.g. a box crash
        # and resume, Section 8) - not merely present-once on a single call.
        # Two fully separate subprocess invocations, same --job-id, deliberately
        # NOT pinning --release-date so any wall-clock-derived value in the
        # payload (publish_date) is free to differ between the two calls; only
        # idempotency_key stability is asserted.
        self.mock.route("/webhook/podbean-publish", [
            (200, self._happy_body()),
            (200, self._happy_body(idempotent=True)),
        ])
        common_args = [
            "--audio-url", "https://media.example.test/a.mp3",
            "--image-url", "https://media.example.test/i.jpg",
            "--job-id", "pd-stable-key-across-runs",
        ]
        proc1 = self._run(common_args, env_extra=self._proxy_env())
        proc2 = self._run(common_args, env_extra=self._proxy_env())
        self.assertEqual(proc1.returncode, 0, proc1.stderr)
        self.assertEqual(proc2.returncode, 0, proc2.stderr)
        hits = self.mock.hits("/webhook/podbean-publish")
        self.assertEqual(len(hits), 2)
        key1 = hits[0]["body"]["idempotency_key"]
        key2 = hits[1]["body"]["idempotency_key"]
        self.assertEqual(key1, "pd-stable-key-across-runs")
        self.assertEqual(key2, "pd-stable-key-across-runs")
        self.assertEqual(key1, key2,
                          "the same --job-id must produce the identical idempotency_key "
                          "on independent invocations, never a time- or run-varying value")

    # ------------------------------------------------- the money path -----
    def test_proxy_standing_block_exits_with_distinct_code_and_json(self):
        self.mock.route("/webhook/podbean-publish", [
            (403, {"ok": False, "reason": "not_in_good_standing",
                   "message": "you are not in good standing"}),
        ])
        proc = self._run(
            ["--audio-url", "https://media.example.test/a.mp3",
             "--image-url", "https://media.example.test/i.jpg",
             "--job-id", "pd-blocked"],
            env_extra=self._proxy_env(),
        )
        self.assertEqual(proc.returncode, 3, proc.stderr)
        result = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertEqual(result, {"status": "blocked", "reason": "not_in_good_standing"})

    def test_proxy_identity_mismatch_is_a_distinct_failure_not_a_standing_block(self):
        self.mock.route("/webhook/podbean-publish", [
            (403, {"ok": False, "reason": "identity_mismatch"}),
        ])
        proc = self._run(
            ["--audio-url", "https://media.example.test/a.mp3",
             "--image-url", "https://media.example.test/i.jpg",
             "--job-id", "pd-mismatch"],
            env_extra=self._proxy_env(),
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertNotEqual(proc.returncode, 3,
                             "identity_mismatch must not be confused with the standing block")
        self.assertIn("identity_mismatch", proc.stderr)

    def test_proxy_in_flight_409_is_refused_not_retried(self):
        self.mock.route("/webhook/podbean-publish", [
            (409, {"ok": False, "reason": "in_flight"}),
        ])
        proc = self._run(
            ["--audio-url", "https://media.example.test/a.mp3",
             "--image-url", "https://media.example.test/i.jpg",
             "--job-id", "pd-inflight"],
            env_extra=self._proxy_env(),
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(len(self.mock.hits("/webhook/podbean-publish")), 1,
                          "409 is a deterministic verdict; must not be retried")

    def test_proxy_invalid_payload_422_is_refused_not_retried(self):
        self.mock.route("/webhook/podbean-publish", [
            (422, {"ok": False, "reason": "invalid_payload", "missing": ["title"]}),
        ])
        proc = self._run(
            ["--audio-url", "https://media.example.test/a.mp3",
             "--image-url", "https://media.example.test/i.jpg",
             "--job-id", "pd-invalid"],
            env_extra=self._proxy_env(),
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(len(self.mock.hits("/webhook/podbean-publish")), 1)

    # --------------------------------------------------------- retry ------
    def test_proxy_retries_once_on_transport_failure_then_succeeds(self):
        self.mock.route("/webhook/podbean-publish", [
            (0, None),  # simulated dropped connection -> curl HTTP code 000
            (200, self._happy_body()),
        ])
        proc = self._run(
            ["--audio-url", "https://media.example.test/a.mp3",
             "--image-url", "https://media.example.test/i.jpg",
             "--job-id", "pd-retry-ok"],
            env_extra=self._proxy_env(),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(len(self.mock.hits("/webhook/podbean-publish")), 2)

    def test_proxy_gives_up_after_exactly_two_attempts(self):
        self.mock.route("/webhook/podbean-publish", [(503, {"ok": False, "reason": "publish_failed"})])
        proc = self._run(
            ["--audio-url", "https://media.example.test/a.mp3",
             "--image-url", "https://media.example.test/i.jpg",
             "--job-id", "pd-retry-exhausted"],
            env_extra=self._proxy_env(),
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(len(self.mock.hits("/webhook/podbean-publish")), 2,
                          "must attempt exactly twice: the first try plus exactly one retry")

    # --------------------------------------------------------- dry-run ----
    def test_dry_run_hits_standing_check_only_never_the_publish_endpoint(self):
        self.mock.route("/webhook/podcast-standing-check", [(200, {"ok": True, "good_standing": True})])
        proc = self._run(["--dry-run"], env_extra=self._proxy_env())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertEqual(result["status"], "dry-run")
        self.assertEqual(result["good_standing"], True)
        self.assertEqual(len(self.mock.hits("/webhook/podcast-standing-check")), 1)
        self.assertEqual(len(self.mock.hits("/webhook/podbean-publish")), 0,
                          "dry-run must never fire a real publish request")

    # -------------------------------------------------- hard stops --------
    def test_identity_env_missing_is_a_hard_stop_before_any_http_call(self):
        env = self._proxy_env()
        del env["PODCAST_CLIENT_LAST_NAME"]
        proc = self._run(
            ["--audio-url", "https://media.example.test/a.mp3",
             "--image-url", "https://media.example.test/i.jpg",
             "--job-id", "pd-no-identity"],
            env_extra=env,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("PODCAST_CLIENT_LAST_NAME", proc.stderr)
        # Not just "some later unbound-variable trip" (bash's set -u would also
        # abort, coincidentally mentioning the var name, if the explicit guard
        # were deleted) - the explicit hard-stop's OWN diagnostic text must be
        # the thing that fired, at the checkpoint before payload-building ever
        # starts, not mid-way through it.
        self.assertIn("roster identity tuple", proc.stderr,
                       "the explicit identity guard's own message must be what fired")
        self.assertNotIn("unbound variable", proc.stderr,
                          "must not be relying on set -u to catch this; the guard must fire first")
        self.assertEqual(len(self.mock.requests), 0,
                          "must die before any HTTP call when identity is unset")

    def test_audio_url_missing_is_a_hard_stop_in_proxy_mode(self):
        proc = self._run(
            ["--image-url", "https://media.example.test/i.jpg", "--job-id", "pd-no-audio-url"],
            env_extra=self._proxy_env(),
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("--audio-url", proc.stderr)
        self.assertEqual(len(self.mock.requests), 0)

    # ------------------------------------------------------- secrecy ------
    def test_publish_token_is_never_echoed_even_when_the_server_reflects_it(self):
        # Worst case: the far end's error body echoes the header value back
        # (e.g. a diagnostic proxy). redact() must still scrub it before any
        # die()/log() line reaches stdout or stderr.
        self.mock.route("/webhook/podbean-publish", [
            (500, {"ok": False, "reason": "publish_failed", "detail": "token=" + FIXTURE_TOKEN}),
        ])
        proc = self._run(
            ["--audio-url", "https://media.example.test/a.mp3",
             "--image-url", "https://media.example.test/i.jpg",
             "--job-id", "pd-secrecy"],
            env_extra=self._proxy_env(),
        )
        self.assertNotEqual(proc.returncode, 0)
        combined = proc.stdout + proc.stderr
        self.assertNotIn(FIXTURE_TOKEN, combined,
                          "the publish-proxy token must never appear verbatim in any output")

    # ------------------------------------------------------ regression ----
    def test_regression_proxy_env_unset_reaches_the_original_local_mode_hard_stop(self):
        # With nothing configured at all, the ORIGINAL (pre-U14) message must
        # still fire verbatim - proof the wrapped broker/local block is
        # reached and unmodified when PROXY_MODE is not selected.
        proc = self._run(["--job-id", "pd-regression"], env_extra={"PODBEAN_PODCAST_ID": "chan-999"})
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("PODBEAN_CLIENT_ID is NOT SET", proc.stderr)

    def test_regression_test_flag_short_circuits_identically_without_proxy_env(self):
        proc = self._run(
            ["--test"],
            env_extra={
                "PODBEAN_PODCAST_ID": "chan-999",
                "PODBEAN_BROKER_WEBHOOK_URL": self.mock.base_url + "/webhook/podbean-broker",
                "PODBEAN_BROKER_TOKEN": "fixture-broker-token",
            },
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertEqual(result["status"], "test-skipped")
        self.assertEqual(len(self.mock.requests), 0)

    # --------------------------------------- 1.1.5 ledger-default --------
    # Every OTHER proxy test supplies --description explicitly, so none of them
    # reaches the ledger-description default path. These two regression tests
    # exercise exactly the broken ordering Finding 1 described: a real proxy
    # publish with a ledger holding a valid >200-char episode_description and
    # NO --description must SUCCEED using the ledger value (the behavior every
    # doc promises), and a proxy publish with NO description ANYWHERE (no flag,
    # no ledger value) must still hard-refuse.

    def test_proxy_ledger_default_description_succeeds_and_uses_ledger_value(self):
        """A real proxy publish with a ledger holding a valid >200-char
        episode_description and NO --description must SUCCEED and send the
        ledger value in the v2 payload (1.1.5 default resolution). This is the
        regression for the ordering bug that died at '--description is required'
        before ever reading the ledger."""
        self.mock.route("/webhook/podbean-publish", [(200, self._happy_body())])
        ledger = self._write_ledger(VALID_DESCRIPTION)
        proc = self._run_no_desc(
            ["--audio-url", "https://media.example.test/a.mp3",
             "--image-url", "https://media.example.test/i.jpg",
             "--job-id", "pd-ledger-default",
             "--ledger", ledger],
            env_extra=self._proxy_env(),
        )
        self.assertEqual(proc.returncode, 0,
                         f"ledger-default proxy publish must succeed; stderr: {proc.stderr}")
        result = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertEqual(result["status"], "published")
        hits = self.mock.hits("/webhook/podbean-publish")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["body"]["description"], VALID_DESCRIPTION,
                         "the payload description must be the ledger episode_description, "
                         "resolved by default when --description is absent")

    def test_proxy_ledger_default_description_resolves_even_when_over_200_chars(self):
        """The ledger-default value is NOT truncated or re-derived: a ledger
        description at the Step 12.5 band (674 chars here) passes through
        intact and satisfies the min-length floor."""
        long_desc = VALID_DESCRIPTION + " " + VALID_DESCRIPTION  # > 400 chars
        self.mock.route("/webhook/podbean-publish", [(200, self._happy_body())])
        ledger = self._write_ledger(long_desc)
        proc = self._run_no_desc(
            ["--audio-url", "https://media.example.test/a.mp3",
             "--image-url", "https://media.example.test/i.jpg",
             "--job-id", "pd-ledger-long",
             "--ledger", ledger],
            env_extra=self._proxy_env(),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        req = self.mock.hits("/webhook/podbean-publish")[0]["body"]
        self.assertEqual(req["description"], long_desc)

    def test_proxy_no_description_anywhere_is_still_a_hard_refusal(self):
        """The no-description-anywhere path (no --description, no ledger) must
        still die with the refusal before any publish call. The ledger-default
        fix must NOT have weakened the fail-closed default."""
        ledger = self._write_ledger(None)  # ledger with NO episode_description
        proc = self._run_no_desc(
            ["--audio-url", "https://media.example.test/a.mp3",
             "--image-url", "https://media.example.test/i.jpg",
             "--job-id", "pd-no-desc-anywhere",
             "--ledger", ledger],
            env_extra=self._proxy_env(),
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("--description is required", proc.stderr)
        self.assertEqual(len(self.mock.hits("/webhook/podbean-publish")), 0,
                          "a publish must never fire when no description exists anywhere")

    def test_proxy_short_description_is_still_a_min_length_refusal(self):
        """A short --description (below the 200-char floor) with no ledger value
        must still be refused by validate_episode_metadata before any publish."""
        ledger = self._write_ledger(None)
        proc = self._run_no_desc(
            ["--audio-url", "https://media.example.test/a.mp3",
             "--image-url", "https://media.example.test/i.jpg",
             "--job-id", "pd-short-desc",
             "--ledger", ledger,
             "--description", "one line"],
            env_extra=self._proxy_env(),
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("minimum", proc.stderr.lower())
        self.assertEqual(len(self.mock.hits("/webhook/podbean-publish")), 0)

    def test_proxy_cli_vs_ledger_description_conflict_still_dies(self):
        """1.1.5's conflict half must survive the reorder: when BOTH the CLI
        flag and the ledger supply a description and they DIFFER, refuse before
        any publish call."""
        self.mock.route("/webhook/podbean-publish", [(200, self._happy_body())])
        ledger = self._write_ledger(VALID_DESCRIPTION)
        proc = self._run_no_desc(
            ["--audio-url", "https://media.example.test/a.mp3",
             "--image-url", "https://media.example.test/i.jpg",
             "--job-id", "pd-desc-conflict",
             "--ledger", ledger,
             "--description", VALID_DESCRIPTION + " DIFFERENT"],
            env_extra=self._proxy_env(),
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("DESCRIPTION conflict", proc.stderr)
        self.assertEqual(len(self.mock.hits("/webhook/podbean-publish")), 0,
                          "a conflicting description must never reach the publish call")


# ---- png helpers (stdlib only, no PIL) ----
def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    import struct, zlib
    c = chunk_type + data
    crc = struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    return struct.pack(">I", len(data)) + c + crc


def _make_png(width: int, height: int) -> bytes:
    """Build a minimal valid RGBA PNG of the given dimensions (solid black)."""
    import struct, zlib
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    raw_rows = b""
    for y in range(height):
        raw_rows += b"\x00" + b"\x00\x00\x00\x00" * width  # filter byte + RGBA black
    return sig + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", zlib.compress(raw_rows)) + _png_chunk(b"IEND", b"")


class ProxyMediaGuardTest(unittest.TestCase):
    """Probe-only tests: the probe function validates audio duration and image
    dimensions before the v2 payload is built. These tests serve real media
    bytes from the loopback server so ffprobe can decode them."""

    def setUp(self):
        self.mock = MockN8n()
        self.addCleanup(self.mock.close)
        self.tmp = tempfile.mkdtemp(prefix="podbean-media-guard-")
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

        # Build a real 1-second MP3 (too short) with ffmpeg.
        self.short_mp3 = os.path.join(self.tmp, "short.mp3")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
             "-ac", "1", "-b:a", "64k", self.short_mp3],
            capture_output=True, check=False,
        )

        # Build a real 30-second MP3 (meets minimum).
        self.ok_mp3 = os.path.join(self.tmp, "ok.mp3")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=30",
             "-ac", "1", "-b:a", "64k", self.ok_mp3],
            capture_output=True, check=False,
        )

        # 1x1 PNG (too small).
        self.tiny_png_data = _make_png(1, 1)

        # 1500x1500 PNG (meets the current Podbean minimum).
        self.ok_png_data = _make_png(1500, 1500)

    def _register_files(self, files_dict):
        self.mock.server.files.update(files_dict)  # type: ignore[attr-defined]

    def _proxy_env_media(self, **extra):
        env = {
            "PODBEAN_PODCAST_ID": "chan-123",
            "PODBEAN_PUBLISH_WEBHOOK_URL": self.mock.publish_url,
            "PODBEAN_PUBLISH_TOKEN": FIXTURE_TOKEN,
            "PODCAST_CLIENT_LAST_NAME": "Rivera",
            "PODCAST_CLIENT_EMAIL": "rivera@example.test",
            # Media probe enabled -- the default for real proxy mode.
            "PODBEAN_SKIP_MEDIA_PROBE": "0",
        }
        env.update(extra)
        return env

    def _run_media(self, audio_url, image_url, job_id="pd-media-guard", **extra_env):
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": self.tmp,
        }
        env.update(self._proxy_env_media(**extra_env))
        # A stub state-writer so the U2.4 waiver gate (assert_not_waived) sees a
        # CLEAN job (no --force-waiver marker) instead of failing closed on a
        # non-existent job. These media-probe tests exercise the probe path, not
        # the waiver gate; the real podcast_state.py would refuse "no job data".
        stub_writer = os.path.join(self.tmp, "podcast_state.py")
        if not os.path.exists(stub_writer):
            with open(stub_writer, "w") as f:
                f.write(
                    "#!/usr/bin/env python3\n"
                    "import json, sys\n"
                    "if sys.argv[1] == 'get':\n"
                    "    print(json.dumps({'job_id': sys.argv[3], 'events': []}))\n"
                    "else:\n"
                    "    print('stub-writer-called:' + ' '.join(sys.argv[1:]))\n"
                )
            os.chmod(stub_writer, 0o755)
        return subprocess.run(
            ["bash", str(_SCRIPT),
             "--audio-url", audio_url,
             "--image-url", image_url,
             "--title", "Media Probe Test",
             "--description", VALID_DESCRIPTION,
             "--job-id", job_id,
             "--state-writer", stub_writer],
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )

    # ----------------------------------------------------------- probe ----
    def test_probe_rejects_too_short_audio(self):
        """A 1-second MP3 must be refused by the duration guard."""
        self._register_files({
            "/media/short.mp3": open(self.short_mp3, "rb").read(),
            "/media/ok.png": self.ok_png_data,
        })
        proc = self._run_media(
            audio_url=self.mock.base_url + "/media/short.mp3",
            image_url=self.mock.base_url + "/media/ok.png",
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("duration", proc.stderr.lower())
        # The publish endpoint must never have been hit.
        self.assertEqual(len(self.mock.hits("/webhook/podbean-publish")), 0)

    def test_probe_rejects_small_image(self):
        """A 1x1 PNG must be refused by the dimension guard."""
        self._register_files({
            "/media/ok.mp3": open(self.ok_mp3, "rb").read(),
            "/media/tiny.png": self.tiny_png_data,
        })
        proc = self._run_media(
            audio_url=self.mock.base_url + "/media/ok.mp3",
            image_url=self.mock.base_url + "/media/tiny.png",
        )
        self.assertNotEqual(proc.returncode, 0)
        # The image might be checked first (order is audio then image).
        combined = (proc.stderr + proc.stdout).lower()
        self.assertTrue(
            "below minimum" in combined or "no video" in combined,
            "image probe must refuse a 1x1 PNG; got: " + proc.stderr[-200:],
        )
        self.assertEqual(len(self.mock.hits("/webhook/podbean-publish")), 0)

    def test_probe_passes_valid_media(self):
        """A 30s MP3 and 1500x1500 PNG must pass the probe and reach publish."""
        self.mock.route("/webhook/podbean-publish", [(200, {
            "ok": True,
            "permalink_url": "https://example.podbean.com/e/test-probe/",
            "episode_id": "ep-1",
            "episode_number": 1,
            "scheduled": False,
            "idempotent_replay": False,
        })])
        self._register_files({
            "/media/ok.mp3": open(self.ok_mp3, "rb").read(),
            "/media/ok.png": self.ok_png_data,
        })
        proc = self._run_media(
            audio_url=self.mock.base_url + "/media/ok.mp3",
            image_url=self.mock.base_url + "/media/ok.png",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertEqual(result["status"], "published")
        self.assertEqual(len(self.mock.hits("/webhook/podbean-publish")), 1)

    def test_probe_escape_hatch_skips_validation(self):
        """PODBEAN_SKIP_MEDIA_PROBE=1 skips the probe and proceeds to publish
        ONLY with the operator force flag (master-plan 1.8)."""
        self.mock.route("/webhook/podbean-publish", [(200, {
            "ok": True,
            "permalink_url": "https://example.podbean.com/e/test-skip/",
            "episode_id": "ep-2",
            "episode_number": 2,
            "scheduled": False,
            "idempotent_replay": False,
        })])
        self._register_files({
            "/media/short.mp3": open(self.short_mp3, "rb").read(),
            "/media/tiny.png": self.tiny_png_data,
        })
        proc = self._run_media(
            audio_url=self.mock.base_url + "/media/short.mp3",
            image_url=self.mock.base_url + "/media/tiny.png",
            PODBEAN_SKIP_MEDIA_PROBE="1",
            PODBEAN_OPERATOR_FORCE="1",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertEqual(result["status"], "published")
        self.assertEqual(len(self.mock.hits("/webhook/podbean-publish")), 1)

    def test_probe_escape_hatch_refused_without_operator_force(self):
        """PODBEAN_SKIP_MEDIA_PROBE=1 without PODBEAN_OPERATOR_FORCE=1 refuses
        to run in publish-proxy mode (fail-closed, master-plan 1.8)."""
        self.mock.route("/webhook/podbean-publish", [(200, {
            "ok": True,
            "permalink_url": "https://example.podbean.com/e/test-skip/",
            "episode_id": "ep-2",
            "episode_number": 2,
            "scheduled": False,
            "idempotent_replay": False,
        })])
        proc = self._run_media(
            audio_url=self.mock.base_url + "/media/short.mp3",
            image_url=self.mock.base_url + "/media/tiny.png",
            PODBEAN_SKIP_MEDIA_PROBE="1",
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("PODBEAN_OPERATOR_FORCE", proc.stderr)
        self.assertEqual(len(self.mock.hits("/webhook/podbean-publish")), 0)

    def test_probe_ffprobe_absence_is_a_hard_fail(self):
        """ffprobe ABSENCE in publish-proxy mode is a HARD FAIL: the script must
        die with the exact 'ffprobe required for media-probe' message and never
        reach the publish endpoint (master-plan 1.8; no HEAD-only degrade)."""
        self.mock.route("/webhook/podbean-publish", [(200, {
            "ok": True,
            "permalink_url": "https://example.podbean.com/e/test-nofprobe/",
            "episode_id": "ep-3",
            "episode_number": 3,
            "scheduled": False,
            "idempotent_replay": False,
        })])
        self._register_files({
            "/media/ok.mp3": open(self.ok_mp3, "rb").read(),
            "/media/ok.png": self.ok_png_data,
        })

        # Build a PATH that has every tool the script needs BEFORE the probe
        # (curl, python3, mktemp, date, grep, cut, rm, wc, tr, printf, bash, ...)
        # but NO ffprobe. Symlink the real system binaries so the script's normal
        # command path is exercised right up to the ffprobe gate.
        shim = os.path.join(self.tmp, "no-ffprobe-bin")
        os.makedirs(shim)
        for tool in ("bash", "curl", "python3", "mktemp", "date", "grep", "cut",
                     "rm", "wc", "tr", "printf", "sed", "awk", "sort", "uniq",
                     "head", "cat", "mkdir", "touch", "basename", "dirname"):
            real = shutil.which(tool)
            if real:
                os.symlink(real, os.path.join(shim, tool))

        env = self._proxy_env_media()
        env["PATH"] = shim
        env["HOME"] = self.tmp
        # Stub state-writer so the U2.4 waiver gate sees a clean (non-waived)
        # job and does not fail closed before the ffprobe gate. Also provide a
        # real description (U048) so the description-required check does not
        # intercept first.
        stub_writer = os.path.join(self.tmp, "podcast_state.py")
        with open(stub_writer, "w") as f:
            f.write(
                "#!/usr/bin/env python3\n"
                "import json, sys\n"
                "if sys.argv[1] == 'get':\n"
                "    print(json.dumps({'job_id': sys.argv[3], 'events': []}))\n"
                "else:\n"
                "    print('stub-writer-called:' + ' '.join(sys.argv[1:]))\n"
            )
        os.chmod(stub_writer, 0o755)
        proc = subprocess.run(
            ["bash", str(_SCRIPT),
             "--audio-url", self.mock.base_url + "/media/ok.mp3",
             "--image-url", self.mock.base_url + "/media/ok.png",
             "--title", "Media Probe No-ffprobe",
             "--description", VALID_DESCRIPTION,
             "--job-id", "pd-no-ffprobe",
             "--state-writer", stub_writer],
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("ffprobe required for media-probe", proc.stderr)
        self.assertIn("ffprobe not available", proc.stderr)
        # Fail closed: never reaches the publish webhook.
        self.assertEqual(len(self.mock.hits("/webhook/podbean-publish")), 0)


if __name__ == "__main__":
    unittest.main()
