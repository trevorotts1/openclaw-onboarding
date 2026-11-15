"""Headless regression tests; synthetic IDs only, all provider I/O mocked."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SKILL = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("fish_audio_config", SKILL / "scripts/fish_audio_config.py")
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)
VOICE = "synthetic-approved-voice"


def environment():
    return {"FISH_AUDIO_API_KEY": "synthetic-key", "FISH_AUDIO_VOICE_ID": VOICE, "MC_COMPANY_ID": "test-company"}


def approval():
    return {"schema_version": 1, "company_id": "test-company",
            "voice_id_sha256": hashlib.sha256(VOICE.encode()).hexdigest(), "approval_ref": "fixture-owner-message-1"}


class ProductionConfigTests(unittest.TestCase):
    def test_missing_wrong_and_right_voice(self):
        for value in ("", "another-clients-voice", "<placeholder>", " \n "):
            with self.subTest(value=value), self.assertRaises(config.ConfigError):
                config.validate({**environment(), "FISH_AUDIO_VOICE_ID": value}, approval())
        self.assertEqual(config.validate(environment(), approval())["voice_id"], VOICE)

    def test_matching_voice_override_only(self):
        config.validate(environment(), approval(), VOICE)
        with self.assertRaises(config.ConfigError):
            config.validate(environment(), approval(), "other-voice")

    def test_approval_must_be_independent_and_company_bound(self):
        for binding in (None, [], {}, {**approval(), "company_id": "other-company"},
                        {**approval(), "schema_version": True}, {**approval(), "approval_ref": ""},
                        {**approval(), "approval_ref": "<pending>"}, {**approval(), "voice_id_sha256": VOICE}):
            with self.subTest(binding=binding), self.assertRaises(config.ConfigError):
                config.validate(environment(), binding)

    def test_expected_voice_env_cannot_self_certify(self):
        with self.assertRaises(config.ConfigError):
            config.validate({**environment(), "FISH_AUDIO_EXPECTED_VOICE_ID": VOICE}, {})

    def test_missing_key_or_company_fails(self):
        for key in ("FISH_AUDIO_API_KEY", "MC_COMPANY_ID"):
            with self.subTest(key=key), self.assertRaises(config.ConfigError):
                config.validate({**environment(), key: ""}, approval())

    def test_placeholder_company_cannot_approve_a_voice(self):
        for company in ("default", "command-center", "<client-id>"):
            with self.subTest(company=company), self.assertRaises(config.ConfigError):
                config.validate({**environment(), "MC_COMPANY_ID": company}, {**approval(), "company_id": company})

    def test_models_are_explicit_and_never_in_body(self):
        for selected, expected in ((None, "drama-3"), ("drama-3", "drama-3"), ("s2.1-pro", "s2.1-pro")):
            env = environment()
            if selected is not None:
                env["FISH_AUDIO_MODEL"] = selected
            headers, body = config.request_parts("Hello", config.validate(env, approval()))
            self.assertEqual(headers["model"], expected)
            self.assertNotIn("model", body)
            self.assertEqual(body["reference_id"], VOICE)
            self.assertEqual(body["mp3_bitrate"], 64)
        for selected in ("", "s1", "s2-pro", "s2.1-pro-free", "drama-typo", "unknown"):
            with self.subTest(selected=selected), self.assertRaises(config.ConfigError):
                config.validate({**environment(), "FISH_AUDIO_MODEL": selected}, approval())
        self.assertEqual(config.request_parts("Hi", config.validate(environment(), approval()), "content")[1]["mp3_bitrate"], 192)

    def test_selected_root_stores_and_live_env_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "secrets").mkdir()
            (root / "secrets/.env").write_text("export FISH_AUDIO_API_KEY='stored-key'\nFISH_AUDIO_VOICE_ID=stored-voice\nFISH_AUDIO_MODEL=drama-3\n")
            (root / ".env").write_text("MC_COMPANY_ID=test-company\nFISH_AUDIO_VOICE_ID=other-store\n")
            (root / "openclaw.json").write_text(json.dumps({"env": {"vars": {"FISH_AUDIO_VOICE_BINDING_FILE": "/fixture/approval.json"}}}))
            env = config.load_env(root, {"FISH_AUDIO_VOICE_ID": "wrong-live-voice"})
            self.assertEqual(env["FISH_AUDIO_API_KEY"], "stored-key")
            self.assertEqual(env["MC_COMPANY_ID"], "test-company")
            self.assertEqual(env["FISH_AUDIO_VOICE_ID"], "wrong-live-voice")
            self.assertEqual(env["FISH_AUDIO_VOICE_BINDING_FILE"], "/fixture/approval.json")
            self.assertEqual(config.load_env(root, {"FISH_AUDIO_VOICE_ID": ""})["FISH_AUDIO_VOICE_ID"], "")
            self.assertNotIn("FISH_AUDIO_API_KEY", config.load_env(root / "another-installation", {}))

    def test_dotenv_is_data_not_shell(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "must-not-exist"
            (root / ".env").write_text("FISH_AUDIO_API_KEY=$(touch " + str(target) + ")\n")
            config.load_env(root, {})
            self.assertFalse(target.exists())

    def test_missing_malformed_and_foreign_record_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(config.ConfigError):
                config.resolve(root, environment())
            (root / "config").mkdir()
            record = root / "config/fish-audio-voice.json"
            for data in ("broken json", "null", json.dumps({**approval(), "company_id": "foreign"})):
                record.write_text(data)
                with self.assertRaises(config.ConfigError):
                    config.resolve(root, environment())
            record.write_text(json.dumps(approval()))
            self.assertEqual(config.resolve(root, environment())["voice_id"], VOICE)
            with self.assertRaises(config.ConfigError):
                config.resolve(root, {**environment(), "FISH_AUDIO_VOICE_BINDING_FILE": "relative.json"})

    def test_qc_exit_and_secret_redaction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "config/fish-audio-voice.json").write_text(json.dumps(approval()))
            for voice, expected in (("", 1), ("wrong-voice", 1), (VOICE, 0)):
                env = {"HOME": directory, "PATH": os.environ["PATH"], "OPENCLAW_ROOT": directory,
                       **environment(), "FISH_AUDIO_VOICE_ID": voice}
                run = subprocess.run(["bash", str(SKILL / "qc-fish-audio-api-reference.sh")], env=env, text=True, capture_output=True)
                self.assertEqual(run.returncode, expected, run.stdout + run.stderr)
                for secret in ("synthetic-key", VOICE, "wrong-voice", approval()["voice_id_sha256"]):
                    self.assertNotIn(secret, run.stdout + run.stderr)

    def test_paid_helper_rejects_before_network_and_does_not_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "config/fish-audio-voice.json").write_text(json.dumps(approval()))
            text = root / "text.txt"
            text.write_text("approved text")
            argv = ["fish_audio_config.py", "tts", "--root", directory, "--text-file", str(text), "--output", str(root / "audio.mp3")]
            for env, count in (({**environment(), "FISH_AUDIO_VOICE_ID": "wrong"}, 0), (environment(), 1)):
                error = config.urllib.error.HTTPError("https://api.fish.audio/v1/tts", 503, "synthetic-key", {}, None)
                with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(sys, "argv", argv), \
                     mock.patch.object(config.urllib.request, "urlopen", side_effect=error) as network, \
                     contextlib.redirect_stderr(io.StringIO()) as output:
                    self.assertEqual(config.main(), 1)
                    self.assertEqual(network.call_count, count)
                    self.assertNotIn("synthetic-key", output.getvalue())
                self.assertFalse((root / "audio.mp3").exists())

    def test_paid_helper_sends_guarded_request_and_writes_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "config/fish-audio-voice.json").write_text(json.dumps(approval()))
            (root / "text.txt").write_text("Approved script")
            response = mock.MagicMock()
            response.__enter__.return_value = response
            response.headers = {"Content-Type": "audio/mpeg"}
            response.read.return_value = b"synthetic-audio"
            argv = ["fish_audio_config.py", "tts", "--root", directory, "--text-file", str(root / "text.txt"), "--output", str(root / "audio.mp3")]
            with mock.patch.dict(os.environ, environment(), clear=True), mock.patch.object(sys, "argv", argv), \
                 mock.patch.object(config.urllib.request, "urlopen", return_value=response) as network, \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(config.main(), 0)
                request = network.call_args.args[0]
                self.assertEqual(request.get_header("Model"), "drama-3")
                self.assertNotIn("model", json.loads(request.data))
                self.assertEqual(json.loads(request.data)["reference_id"], VOICE)
                self.assertEqual((root / "audio.mp3").read_bytes(), b"synthetic-audio")


if __name__ == "__main__":
    unittest.main()
