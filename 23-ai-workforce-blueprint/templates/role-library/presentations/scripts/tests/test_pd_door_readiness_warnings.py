"""PD-043 — the door says BEFORE any spend what this box cannot do.

Acceptance row A1 (unit PD-043, FINAL spec): each of the three readiness
warnings appears with its log row when its name is unset and is absent when
set; no dummy value appears in captured output.

  A1a  every name set to a dummy -> none of the three WARN lines, no rows.
  A1b  one Cloudflare name unset -> TELEPROMPTER-PUBLISH warning + log row.
  A1c  no speech key set         -> SPEECH-KEY warning + log row.
  A1d  audio key unset           -> AUDIO-KEY warning + log row.
  A1e  the dummy strings never appear in stdout or stderr.
  A1f  negative control: with every name set the same assertion that looks for
       the warning fails, so the row can go RED.

Stub trees only; --plan stops the door before any render spend.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
_ENTRY_DEPLOYED = SCRIPTS / "presentation-canonical-entry.sh"
_ENTRY_REPO = SCRIPTS.parents[3] / "scripts" / "presentation-canonical-entry.sh"
ENTRY = _ENTRY_DEPLOYED if _ENTRY_DEPLOYED.is_file() else _ENTRY_REPO
assert ENTRY.is_file(), f"canonical entry script not found ({ENTRY})"

ENVELOPE = {
    "format": "sp-intake-transcript-v1",
    "driver_signature": "fixture-signed",
    "qid_sequence": ["q1", "q2"],
    "turns": [{"q": "What topic?", "a": "A long answer " * 20},
              {"q": "Who for?", "a": "A fixture audience"}],
}

CLOUDFLARE = ("CLOUDFLARE_ZHW_APPS_API_TOKEN", "CLOUDFLARE_ZHW_ACCOUNT_ID")
SPEECH = ("SPEECH_LLM_API_KEY", "OLLAMA_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY")
AUDIO = ("FISH_AUDIO_API_KEY",)
ALL_NAMES = CLOUDFLARE + SPEECH + AUDIO

DUMMY = {
    "CLOUDFLARE_ZHW_APPS_API_TOKEN": "dummy-cf-token-DO-NOT-PRINT",
    "CLOUDFLARE_ZHW_ACCOUNT_ID": "dummy-cf-account-DO-NOT-PRINT",
    "SPEECH_LLM_API_KEY": "dummy-speech-DO-NOT-PRINT",
    "OLLAMA_API_KEY": "dummy-ollama-DO-NOT-PRINT",
    "OPENROUTER_API_KEY": "dummy-openrouter-DO-NOT-PRINT",
    "OPENAI_API_KEY": "dummy-openai-DO-NOT-PRINT",
    "FISH_AUDIO_API_KEY": "dummy-fish-DO-NOT-PRINT",
}

WARN = {
    "TELEPROMPTER-PUBLISH":
        "WARN [TELEPROMPTER-PUBLISH]: this box cannot publish the teleprompter "
        "link; the teleprompter will not be hosted and the client will get the "
        "teleprompter file with no web link",
    "SPEECH-KEY":
        "WARN [SPEECH-KEY]: no key the speech builder accepts is set on this "
        "box; the speech step will stop after the deck is rendered",
    "AUDIO-KEY":
        "WARN [AUDIO-KEY]: the audio key is not set on this box; the audio step "
        "will stop after the deck is rendered",
}


def make_run_dir(base: Path) -> Path:
    run_dir = base / "run"
    (run_dir / "working" / "checkpoints").mkdir(parents=True)
    (run_dir / "working" / "interview").mkdir(parents=True)
    (run_dir / "working" / "checkpoints" / ".test-context").write_text("")
    (run_dir / "working" / "interview" / "intake_ledger.json").write_text(
        json.dumps({"status": "complete", "complete": True}))
    (run_dir / "working" / "interview" / "intake_transcript.json").write_text(
        json.dumps(ENVELOPE))
    (run_dir / "slides.json").write_text("{}")
    return run_dir


def make_scripts_dir(base: Path) -> Path:
    d = base / "fake-scripts"
    d.mkdir(exist_ok=True)
    (d / "build_deck.py").write_text("import sys\nsys.exit(0)\n")
    (d / "run_signature_deck.py").write_text("import sys\nsys.exit(0)\n")
    (d / "ghl_media.py").write_text(
        "def upload_media(*a, **k): pass\n"
        "def list_media(*a, **k): return {'data': []}\n"
        "def create_media_folder(*a, **k): pass\n")
    (d / "sync_check.py").write_text(
        "import json, sys\n"
        "print(json.dumps({'in_sync': True, 'manifest_version': 39, 'drift': [],\n"
        "                  'drift_summary': {'total': 0, 'render_path': 0, 'library_only': 0}}))\n"
        "sys.exit(0)\n")
    return d


def _env(set_names) -> dict:
    """Every readiness NAME scrubbed from a clean copy, then `set_names` set to
    its dummy. A key present in the operator environment can never leak into a
    row."""
    env = dict(os.environ)
    for name in ALL_NAMES:
        env.pop(name, None)
    env["QC_SKIP_PRESENTATION_DEPS"] = "1"
    for name in set_names:
        env[name] = DUMMY[name]
    return env


def _run(run_dir: Path, scripts: Path, set_names=ALL_NAMES):
    env = _env(set_names)
    env["OPENCLAW_WORKSPACE"] = str(run_dir.parent / "no-ws")
    cmd = ["/bin/bash", str(ENTRY), "--run-dir", str(run_dir),
           "--scripts-dir", str(scripts), "--plan"]
    return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)


def _rows(run_dir: Path):
    log = run_dir / "working" / "checkpoints" / "gate_log.jsonl"
    if not log.is_file():
        return []
    out = []
    for line in log.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("gate") == "READINESS":
            out.append(row)
    return out


def _assert_no_dummies(r):
    for value in DUMMY.values():
        assert value not in r.stdout, f"dummy value leaked to stdout\n{r.stdout}"
        assert value not in r.stderr, f"dummy value leaked to stderr\n{r.stderr}"


# ---------------------------------------------------------------------------
# A1a / A1e — everything set: no warning, no row, no value on the wire.
# ---------------------------------------------------------------------------
def test_a1a_all_set_emits_no_readiness_warning(tmp_path):
    run_dir = make_run_dir(tmp_path)
    scripts = make_scripts_dir(tmp_path)
    r = _run(run_dir, scripts, set_names=ALL_NAMES)

    for tag, text in WARN.items():
        assert text not in r.stderr, (
            f"{tag} warned although every name was set\nstderr:{r.stderr}")
        assert f"WARN [{tag}]" not in r.stdout, r.stdout
    assert _rows(run_dir) == [], f"unexpected readiness rows: {_rows(run_dir)}"
    _assert_no_dummies(r)


# ---------------------------------------------------------------------------
# A1b — one Cloudflare name unset: the teleprompter warning and its row.
# ---------------------------------------------------------------------------
def test_a1b_missing_cloudflare_name_warns_and_logs(tmp_path):
    run_dir = make_run_dir(tmp_path)
    scripts = make_scripts_dir(tmp_path)
    r = _run(run_dir, scripts, set_names=set(ALL_NAMES) - {"CLOUDFLARE_ZHW_ACCOUNT_ID"})

    assert WARN["TELEPROMPTER-PUBLISH"] in r.stderr, r.stderr
    assert WARN["SPEECH-KEY"] not in r.stderr, r.stderr
    assert WARN["AUDIO-KEY"] not in r.stderr, r.stderr
    rows = _rows(run_dir)
    assert {row["warning"] for row in rows} == {"TELEPROMPTER-PUBLISH"}, rows
    assert rows[0]["missing"] == ["CLOUDFLARE_ZHW_ACCOUNT_ID"], rows[0]
    _assert_no_dummies(r)


# ---------------------------------------------------------------------------
# A1c — no speech key set: the speech warning and its row.
# ---------------------------------------------------------------------------
def test_a1c_no_speech_key_warns_and_logs(tmp_path):
    run_dir = make_run_dir(tmp_path)
    scripts = make_scripts_dir(tmp_path)
    r = _run(run_dir, scripts, set_names=set(ALL_NAMES) - set(SPEECH))

    assert WARN["SPEECH-KEY"] in r.stderr, r.stderr
    assert WARN["TELEPROMPTER-PUBLISH"] not in r.stderr, r.stderr
    rows = _rows(run_dir)
    assert {row["warning"] for row in rows} == {"SPEECH-KEY"}, rows
    assert sorted(rows[0]["missing"]) == sorted(SPEECH), rows[0]
    _assert_no_dummies(r)


# ---------------------------------------------------------------------------
# A1d — audio key unset: the audio warning and its row.
# ---------------------------------------------------------------------------
def test_a1d_missing_audio_key_warns_and_logs(tmp_path):
    run_dir = make_run_dir(tmp_path)
    scripts = make_scripts_dir(tmp_path)
    r = _run(run_dir, scripts, set_names=set(ALL_NAMES) - set(AUDIO))

    assert WARN["AUDIO-KEY"] in r.stderr, r.stderr
    rows = _rows(run_dir)
    assert {row["warning"] for row in rows} == {"AUDIO-KEY"}, rows
    _assert_no_dummies(r)


# ---------------------------------------------------------------------------
# A1f — negative control. The A1b assertion must be able to go RED.
# ---------------------------------------------------------------------------
def test_a1f_negative_control_same_assertion_fails_when_key_is_set(tmp_path):
    run_dir = make_run_dir(tmp_path)
    scripts = make_scripts_dir(tmp_path)
    r = _run(run_dir, scripts, set_names=ALL_NAMES)
    assert WARN["TELEPROMPTER-PUBLISH"] not in r.stderr, (
        "control: the warning is present with every name set, so A1b could not fail")


# ---------------------------------------------------------------------------
# A1g — non-blocking: the door still reaches its plan/exit with a key missing.
# ---------------------------------------------------------------------------
def test_a1g_readiness_never_blocks_the_door(tmp_path):
    run_dir = make_run_dir(tmp_path)
    scripts = make_scripts_dir(tmp_path)
    r = _run(run_dir, scripts, set_names=())
    assert "WARN [TELEPROMPTER-PUBLISH]" in r.stderr
    assert "WARN [SPEECH-KEY]" in r.stderr
    assert "WARN [AUDIO-KEY]" in r.stderr
    assert "PRESENTATION_READINESS" not in r.stderr, r.stderr
    # --plan is read-only; a readiness warning must not change the exit code.
    assert r.returncode == 0, f"{r.returncode}\n{r.stdout}\n{r.stderr}"
