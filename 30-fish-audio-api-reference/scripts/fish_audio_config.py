#!/usr/bin/env python3
"""Client-scoped Fish Audio preflight and TTS. Never print credentials or voice IDs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request

SKILL_DIR = Path(__file__).resolve().parents[1]
POLICY = json.loads((SKILL_DIR / "production-policy.json").read_text())
KEYS = ("FISH_AUDIO_API_KEY", "FISH_AUDIO_VOICE_ID", "FISH_AUDIO_MODEL",
        "MC_COMPANY_ID", "FISH_AUDIO_VOICE_BINDING_FILE")


class ConfigError(ValueError):
    pass


def value_present(value):
    return isinstance(value, str) and bool(value.strip()) and not re.search(r"[<>\r\n]", value)


def load_env(root, environ=None):
    """Live env wins. Read only this selected installation; never execute dotenv."""
    result = dict(os.environ if environ is None else environ)
    for file in (root / "secrets/.env", root / ".env"):
        if not file.is_file():
            continue
        values = {}
        for line in file.read_text().splitlines():
            match = re.match(r"^\s*(?:export\s+)?([A-Z_][A-Z_0-9]*)\s*=\s*(.*?)\s*$", line)
            if match and match[1] in KEYS:
                value = match[2]
                if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
                    value = value[1:-1]
                values[match[1]] = value
        for key, value in values.items():
            if key not in result:
                result[key] = value
    config = root / "openclaw.json"
    if config.is_file():
        try:
            values = json.loads(config.read_text()).get("env", {}).get("vars", {})
            for key in KEYS:
                if key not in result and isinstance(values.get(key), str):
                    result[key] = values[key]
        except (ValueError, AttributeError, TypeError):
            raise ConfigError("OpenClaw env configuration is invalid") from None
    return result


def validate(env, binding, voice_override=None):
    api_key = env.get("FISH_AUDIO_API_KEY", "").strip()
    voice = env.get("FISH_AUDIO_VOICE_ID", "").strip()
    company = env.get("MC_COMPANY_ID", "").strip()
    model = env.get("FISH_AUDIO_MODEL", POLICY["default_model"]).strip()
    for name, value in (("FISH_AUDIO_API_KEY", api_key), ("FISH_AUDIO_VOICE_ID", voice),
                        ("MC_COMPANY_ID", company)):
        if not value_present(value):
            raise ConfigError(name + " is missing or invalid")
    if company.lower() in POLICY["invalid_company_ids"]:
        raise ConfigError("MC_COMPANY_ID must identify a provisioned client")
    if model not in POLICY["allowed_models"]:
        raise ConfigError("FISH_AUDIO_MODEL is not an approved production model")
    if not isinstance(binding, dict) or type(binding.get("schema_version")) is not int or binding["schema_version"] != 1:
        raise ConfigError("Fish Audio voice approval is missing or invalid")
    if not value_present(binding.get("approval_ref")):
        raise ConfigError("Fish Audio voice approval needs an independent approval reference")
    if binding.get("company_id") != company:
        raise ConfigError("Fish Audio voice approval belongs to a different company")
    expected = binding.get("voice_id_sha256", "")
    if not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected):
        raise ConfigError("Fish Audio approved voice fingerprint is invalid")
    if hashlib.sha256(voice.encode()).hexdigest() != expected:
        raise ConfigError("FISH_AUDIO_VOICE_ID does not match the independently approved client voice")
    if voice_override is not None and hashlib.sha256(voice_override.encode()).hexdigest() != expected:
        raise ConfigError("Fish Audio voice override does not match the approved client voice")
    return {"api_key": api_key, "voice_id": voice, "model": model}


def resolve(root, env):
    configured = env.get("FISH_AUDIO_VOICE_BINDING_FILE")
    binding_path = Path(configured) if configured is not None else root / POLICY["voice_binding_file"]
    if not binding_path.is_absolute():
        raise ConfigError("FISH_AUDIO_VOICE_BINDING_FILE must be an absolute path")
    try:
        binding = json.loads(binding_path.read_text())
    except (OSError, ValueError):
        raise ConfigError("Fish Audio voice approval file is missing or invalid") from None
    return validate(env, binding)


def request_parts(text, settings, use_case="phone"):
    return ({"Authorization": "Bearer " + settings["api_key"],
             "Content-Type": "application/json", POLICY["model_header"]: settings["model"]},
            {"text": text, "reference_id": settings["voice_id"], "format": "mp3",
             "mp3_bitrate": 192 if use_case == "content" else 64,
             "normalize": True, "latency": "normal"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "tts"))
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--text-file", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--use-case", choices=("phone", "content"), default="phone")
    args = parser.parse_args()
    try:
        if not args.root.is_absolute():
            raise ConfigError("OpenClaw root must be absolute")
        env = load_env(args.root)
        if args.command == "check":
            for key in ("FISH_AUDIO_API_KEY", "FISH_AUDIO_VOICE_ID"):
                print(("PASS" if value_present(env.get(key)) else "FAIL") + " - " + key + " set")
        settings = resolve(args.root, env)
        if args.command == "check":
            print("PASS - independently approved client voice matches")
            print("PASS - explicit production model header: " + settings["model"])
            return 0
        if args.text_file is None or args.output is None:
            raise ConfigError("TTS needs --text-file and --output")
        text = args.text_file.read_text().strip()
        if not text or len(text) > 4000:
            raise ConfigError("TTS text must contain 1 to 4000 characters; split longer scripts")
        headers, body = request_parts(text, settings, args.use_case)
        request = urllib.request.Request("https://api.fish.audio/v1/tts", data=json.dumps(body).encode(), headers=headers)
        with urllib.request.urlopen(request, timeout=60) as response:
            audio = response.read()
            if not response.headers.get("Content-Type", "").startswith("audio/") or not audio:
                raise ConfigError("Fish Audio did not return nonempty audio")
        args.output.write_bytes(audio)
        print("PASS - audio written using the approved client voice")
        return 0
    except urllib.error.HTTPError as error:
        print("FAIL - Fish Audio HTTP " + str(error.code) + "; no model or voice fallback", file=sys.stderr)
    except urllib.error.URLError:
        print("FAIL - Fish Audio unavailable; no model or voice fallback", file=sys.stderr)
    except (ConfigError, OSError, UnicodeError) as error:
        print("FAIL - " + (str(error) if isinstance(error, ConfigError) else "Fish Audio input or output could not be read"), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
