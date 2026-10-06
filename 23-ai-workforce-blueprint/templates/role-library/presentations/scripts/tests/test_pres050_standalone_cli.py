"""PRES-050 regression: typed standalone CLI + repaired Skill51 wrapper.

Why this exists: bin/presentation (Skill 51) required an OpenClaw secrets
FILE even when the caller exported client credentials (exit 60), rebuilt
argv through a pipe-delimited string with unquoted re-split (spaces split,
literal pipes split, $HOME expanded), and the outbox transport guessed the
run dir from cwd (cross-client misdelivery). The new typed surface is
51-signature-presentation/bin/presentation-cli (verbs init/doctor/start/
status/resume/cancel/verify/export, stdlib only).

Legs (all hermetic: HOME redirected to tmp_path, scratch secrets/engines;
no network except loopback CC probes the tests themselves open; no real
secrets read or printed):

  1. STATIC — the pipe-delimited rebuild (`_newargs|`, `tr '|' ' '`,
     unquoted `$(...)` exec) is ABSENT from bin/presentation; the shell
     array (`_newargv+=(...)` + `"${_newargv[@]}"`) is present.
  2. DYNAMIC argv — repaired wrapper against a stub door preserves spaces,
     Unicode, literal pipes and dollar signs byte-identical.
  3. EXPORTED CREDS — exported PRESENTATION_CREDENTIAL_PROFILE passes the
     wrapper gate with NO secrets file on disk (old code: exit 60).
  4. OUTBOX — queue without PRESENTATION_RUN_DIR refuses (exit 4) and
     writes nothing to cwd; two runs cannot read each other's rows.
  5. CLI verbs — init/doctor/start/status/cancel/verify/export round-trip
     with hostile argv (pipes/dollars/unicode/spaces); wrong company
     refused (64) with no secret values in output; stated-but-wrong
     --scripts-dir refused (62); --cc-required against a dead port
     blocks start (63); local-only success is explicitly local.
  6. CONNECTED proof — a loopback fixture CC answering /api/health with a
     live status is PROVEN (doctor 0); a listener returning 401 is NOT
     proof (doctor nonzero). Liveness is authenticated identity, never a
     listening port.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parents[6] / "51-signature-presentation"
WRAPPER = SKILL_DIR / "bin" / "presentation"
OUTBOX = SKILL_DIR / "bin" / "presentation-outbox-queue"
CLI = SKILL_DIR / "bin" / "presentation-cli"
SCRIPTS_DIR = Path(__file__).resolve().parent.parent  # .../presentations/scripts

SENTINEL = "sk-pres050-SENTINEL-MUST-NEVER-BE-PRINTED-0123456789"

BASE_ENV_KEYS = ("OPENCLAW_SECRETS", "OPENCLAW_ROOT", "OC_ROOT",
                 "OPENCLAW_WORKSPACE", "SCRIPTS_DIR", "PYTHONPATH",
                 "COMMAND_CENTER_URL", "MISSION_CONTROL_URL",
                 "CC_API_TOKEN", "MC_API_TOKEN", "WEBHOOK_SECRET",
                 "CC_WEBHOOK_SECRET")


def _clean_env(**overrides: str) -> dict:
    env = dict(os.environ)
    for key in BASE_ENV_KEYS:
        env.pop(key, None)
    env["PATH"] = os.pathsep.join(
        p for p in env.get("PATH", "").split(os.pathsep) if p) or "/usr/bin:/bin"
    env.update(overrides)
    return env


def _stub_dept(root: Path) -> Path:
    """Materialize a stub department (stub door records argv as JSON)."""
    dept = root / ".openclaw" / "workspace" / "departments" / "Presentations" / "scripts"
    dept.mkdir(parents=True, exist_ok=True)
    for name in ("build_deck.py", "run_signature_deck.py"):
        (dept / name).write_text("# stub\n", encoding="utf-8")
    door = dept / "presentation-canonical-entry.sh"
    door.write_text(
        "#!/usr/bin/env bash\n"
        'python3 -c "import sys,json; print(json.dumps(sys.argv[1:]))" "$@"\n',
        encoding="utf-8")
    door.chmod(0o755)
    return dept


def _copy_engine_scripts(dest: Path) -> None:
    """Copy the REAL engine (presentation_job + sentinels) so the CLI's
    worker-ack probe runs real code, not a stub."""
    for name in ("presentation_job.py", "presentation_job", "build_deck.py",
                 "run_signature_deck.py", "presentation-canonical-entry.sh"):
        src = SCRIPTS_DIR / name
        dst = dest / name
        if src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst, symlinks=True)
        elif src.is_file():
            shutil.copy2(src, dst)


# ---------------------------------------------------------------------------
# 1. STATIC — pipe rebuild gone, shell array present.
# ---------------------------------------------------------------------------

def test_wrapper_has_no_pipe_delimited_argv_rebuild():
    src = WRAPPER.read_text(encoding="utf-8", errors="replace")
    assert "_newargs|" not in src and '|$_a' not in src, \
        "pipe-delimited argv rebuild is back in bin/presentation"
    assert "tr '|' ' '" not in src, \
        "pipe-to-space argv re-split is back in bin/presentation"
    assert "_newargv+=(" in src and '"${_newargv[@]}"' in src, \
        "shell-array argv exec missing from bin/presentation"


def test_wrapper_honors_exported_credentials_without_secrets_file():
    src = WRAPPER.read_text(encoding="utf-8", errors="replace")
    assert "PRESENTATION_CREDENTIAL_PROFILE" in src, \
        "wrapper must accept an explicitly exported credential profile"
    assert "OPENCLAW_SECRETS" in src, \
        "wrapper must honor the OPENCLAW_SECRETS explicit pin"


def test_outbox_has_no_cwd_guessing():
    src = OUTBOX.read_text(encoding="utf-8", errors="replace")
    assert 'os.getcwd()' not in src, \
        "cwd guessing is back in presentation-outbox-queue"
    assert "PRESENTATION_RUN_DIR" in src


# ---------------------------------------------------------------------------
# 2. DYNAMIC argv through the repaired wrapper.
# ---------------------------------------------------------------------------

def test_wrapper_preserves_hostile_argv(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    _stub_dept(home)
    env = _clean_env(HOME=str(home), OPENCLAW_PLATFORM="mac",
                     PRESENTATION_NOTIFY_CMD="true",
                     PRESENTATION_CREDENTIAL_PROFILE="acme-test")
    rundir = str(tmp_path / "run dir ünïcodé")
    argv = ["--run-dir", rundir, "--slides", "a|b $HOME", "--out", "o.pptx"]
    proc = subprocess.run(["bash", str(WRAPPER)] + argv, capture_output=True,
                          text=True, env=env, cwd=str(tmp_path), timeout=60)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert json.loads(proc.stdout.strip()) == argv


def test_wrapper_normalizes_run_dir_equals_form(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    _stub_dept(home)
    env = _clean_env(HOME=str(home), OPENCLAW_PLATFORM="mac",
                     PRESENTATION_NOTIFY_CMD="true",
                     PRESENTATION_CREDENTIAL_PROFILE="acme-test")
    rundir = str(tmp_path / "r")
    proc = subprocess.run(
        ["bash", str(WRAPPER), "--run-dir=" + rundir, "--slides", "x"],
        capture_output=True, text=True, env=env, cwd=str(tmp_path),
        timeout=60)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert json.loads(proc.stdout.strip()) == ["--run-dir", rundir, "--slides", "x"]


# ---------------------------------------------------------------------------
# 3. Exported credentials pass the wrapper gate with no secrets file.
# ---------------------------------------------------------------------------

def test_wrapper_exported_credentials_need_no_secrets_file(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    _stub_dept(home)
    assert not (home / ".openclaw" / "secrets" / ".env").exists()
    env = _clean_env(HOME=str(home), OPENCLAW_PLATFORM="mac",
                     PRESENTATION_NOTIFY_CMD="true",
                     PRESENTATION_CREDENTIAL_PROFILE="acme-test")
    proc = subprocess.run(
        ["bash", str(WRAPPER), "--run-dir", str(tmp_path / "r"),
         "--slides", "s", "--out", "o"],
        capture_output=True, text=True, env=env, cwd=str(tmp_path),
        timeout=60)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "no secrets env found" not in proc.stderr


# ---------------------------------------------------------------------------
# 4. Outbox: refusal without RUN_DIR; tenant isolation with it.
# ---------------------------------------------------------------------------

def test_outbox_refuses_without_run_dir_and_writes_nothing(tmp_path):
    env = _clean_env()
    env.pop("PRESENTATION_RUN_DIR", None)
    proc = subprocess.run(
        [sys.executable, str(OUTBOX)], input='{"chat_id":"1","kind":"x","m":"hi"}',
        capture_output=True, text=True, env=env, cwd=str(tmp_path),
        timeout=60)
    assert proc.returncode == 4, proc.stderr
    assert not (tmp_path / "working" / "outbox.jsonl").exists()


def test_outbox_runs_are_isolated(tmp_path):
    run_a = tmp_path / "runA"
    run_b = tmp_path / "runB"
    for run in (run_a, run_b):
        (run / "working").mkdir(parents=True)
    for tag, run in (("runA", run_a), ("runB", run_b)):
        env = _clean_env(PRESENTATION_RUN_DIR=str(run))
        proc = subprocess.run(
            [sys.executable, str(OUTBOX)],
            input=json.dumps({"chat_id": tag, "kind": "progress",
                              "message": "m-" + tag}),
            capture_output=True, text=True, env=env, cwd=str(tmp_path),
            timeout=60)
        assert proc.returncode == 0, proc.stderr
    text_a = (run_a / "working" / "outbox.jsonl").read_text(encoding="utf-8")
    text_b = (run_b / "working" / "outbox.jsonl").read_text(encoding="utf-8")
    assert "runB" not in text_a and "runA" not in text_b


# ---------------------------------------------------------------------------
# 5. CLI verbs incl. hostile argv, wrong-client, scripts-dir, CC gates.
# ---------------------------------------------------------------------------

COMPANY = "acme pipe|co $HOME ünï"
PRESENT = "deck | $X ünï"


def _ws_with_engine(tmp_path: Path) -> Path:
    ws = tmp_path / ("ws**| $HOME ünï")
    dept = ws / "departments" / "Presentations" / "scripts"
    dept.mkdir(parents=True, exist_ok=True)
    _copy_engine_scripts(dept)
    return ws


def _cli_base(ws: Path, features: str | None = None) -> list:
    base = [sys.executable, str(CLI), "--workspace", str(ws),
            "--company-id", COMPANY, "--presentation-id", PRESENT,
            "--credential-profile", "p|p $X"]
    if features is not None:
        base += ["--features", features]
    return base


def _run_cli(args: list, env: dict, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, env=env,
                          cwd=str(cwd), timeout=180)


def test_cli_full_lifecycle_with_hostile_argv(tmp_path):
    ws = _ws_with_engine(tmp_path)
    env = _clean_env(PRESENTATION_NOTIFY_CMD="true",
                     PRESENTATION_CREDENTIAL_PROFILE="p|p $X")
    base = _cli_base(ws)
    assert _run_cli(base + ["init"], env, tmp_path).returncode == 0
    proc = _run_cli(base + ["doctor"], env, tmp_path)
    assert proc.returncode == 0, proc.stdout[-2000:]
    assert json.loads(proc.stdout)["credentials"]["secrets_file_required"] is False
    proc = _run_cli(base + ["start"], env, tmp_path)
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-1000:]
    started = json.loads(proc.stdout)
    assert started["result"] == "accepted"
    assert started["mode"] == "standalone-local"
    run_id = started["run_id"]
    proc = _run_cli(base + ["status", "--run-id", run_id], env, tmp_path)
    assert proc.returncode == 0, proc.stdout[-2000:]
    local = json.loads(proc.stdout)["local"]
    assert local["company_id"] == COMPANY
    assert local["presentation_id"] == PRESENT
    proc = _run_cli(base + ["export", "--run-id", run_id], env, tmp_path)
    assert proc.returncode == 0, proc.stdout[-2000:]
    assert "not delivery" in proc.stdout
    proc = _run_cli(base + ["cancel", "--run-id", run_id,
                            "--reason", "test done"], env, tmp_path)
    assert proc.returncode == 0, proc.stdout[-1000:]
    proc = _run_cli(base + ["resume", "--run-id", run_id], env, tmp_path)
    assert proc.returncode != 0, "cancelled run must refuse resume"
    assert "cancellation wins" in proc.stdout


def test_cli_optional_delivery_does_not_block_unrelated_production(tmp_path):
    """QC-PRES-050 check 2, second half: GHL declined (default features)
    starts fine with no GHL creds; GHL selected without creds refuses (60);
    --allow-missing-feature-creds records the decline and proceeds."""
    ws = _ws_with_engine(tmp_path)
    env = _clean_env(PRESENTATION_NOTIFY_CMD="true",
                     PRESENTATION_CREDENTIAL_PROFILE="t")
    assert "GHL_API_KEY" not in env and "GHL_LOCATION_ID" not in env
    base = [sys.executable, str(CLI), "--workspace", str(ws),
            "--company-id", "c", "--presentation-id", "p",
            "--credential-profile", "t"]
    assert _run_cli(base + ["init"], env, tmp_path).returncode == 0
    proc = _run_cli(base + ["start"], env, tmp_path)
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-1000:]
    assert json.loads(proc.stdout)["result"] == "accepted"
    ghl = [sys.executable, str(CLI), "--workspace", str(ws),
           "--company-id", "c", "--presentation-id", "p",
           "--credential-profile", "t", "--features", "notify,ghl"]
    proc = _run_cli(ghl + ["start"], env, tmp_path)
    assert proc.returncode == 60, proc.stdout
    assert "GHL_API_KEY" in proc.stdout
    proc = _run_cli(ghl + ["start", "--allow-missing-feature-creds"],
                    env, tmp_path)
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-1000:]


def test_cli_wrong_client_refused_without_secret_values(tmp_path):
    ws = _ws_with_engine(tmp_path)
    env = _clean_env(PRESENTATION_NOTIFY_CMD="true",
                     PRESENTATION_CREDENTIAL_PROFILE="acme-test",
                     GHL_API_KEY=SENTINEL, OPENROUTER_API_KEY=SENTINEL)
    base = [sys.executable, str(CLI), "--workspace", str(ws),
            "--company-id", "acme", "--presentation-id", "deck1",
            "--credential-profile", "acme-test"]
    assert _run_cli(base + ["init"], env, tmp_path).returncode == 0
    evil = [sys.executable, str(CLI), "--workspace", str(ws),
            "--company-id", "EVIL-CORP", "--presentation-id", "deck1",
            "--credential-profile", "acme-test"]
    proc = _run_cli(evil + ["status", "--run-id", "run_nope"], env, tmp_path)
    assert proc.returncode == 64, proc.stdout
    assert SENTINEL not in proc.stdout and SENTINEL not in proc.stderr


def test_cli_stated_but_wrong_scripts_dir_refused(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    env = _clean_env(PRESENTATION_NOTIFY_CMD="true",
                     PRESENTATION_CREDENTIAL_PROFILE="acme-test")
    base = [sys.executable, str(CLI), "--workspace", str(ws),
            "--company-id", "acme", "--presentation-id", "deck1",
            "--credential-profile", "acme-test",
            "--scripts-dir", str(tmp_path / "definitely-not-a-dept")]
    proc = _run_cli(base + ["doctor"], env, tmp_path)
    assert proc.returncode == 62, proc.stdout
    assert json.loads(proc.stdout)["scripts_dir"]["stated_but_wrong"] is True


def test_cli_connected_mode_blocked_on_dead_cc(tmp_path):
    ws = _ws_with_engine(tmp_path)
    env = _clean_env(PRESENTATION_NOTIFY_CMD="true",
                     PRESENTATION_CREDENTIAL_PROFILE="acme-test")
    base = [sys.executable, str(CLI), "--workspace", str(ws),
            "--company-id", "acme", "--presentation-id", "deck1",
            "--credential-profile", "acme-test"]
    assert _run_cli(base + ["init"], env, tmp_path).returncode == 0
    proc = _run_cli(base + ["start", "--cc-url", "http://127.0.0.1:9",
                            "--cc-required"], env, tmp_path)
    assert proc.returncode == 63, proc.stdout
    assert "blocked" in proc.stdout


# ---------------------------------------------------------------------------
# 6. CONNECTED proof: live health proves; anonymous 401 does not.
# ---------------------------------------------------------------------------

class _HealthOK(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/api/health":
            body = json.dumps({"status": "ok",
                               "migrations": {"pending": 0}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a: object) -> None:
        pass


class _Health401(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(401)
        self.end_headers()

    def log_message(self, *a: object) -> None:
        pass


def _serve(handler: type[BaseHTTPRequestHandler]) -> tuple[HTTPServer, int]:
    server = HTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def test_cli_connected_proof_live_health_vs_anonymous_401(tmp_path):
    ws = _ws_with_engine(tmp_path)
    env = _clean_env(PRESENTATION_NOTIFY_CMD="true",
                     PRESENTATION_CREDENTIAL_PROFILE="acme-test")
    base = [sys.executable, str(CLI), "--workspace", str(ws),
            "--company-id", "acme", "--presentation-id", "deck1",
            "--credential-profile", "acme-test"]
    assert _run_cli(base + ["init"], env, tmp_path).returncode == 0
    live, live_port = _serve(_HealthOK)
    try:
        proc = _run_cli(base + ["doctor", "--cc-url",
                                "http://127.0.0.1:%d" % live_port,
                                "--cc-required"], env, tmp_path)
        assert proc.returncode == 0, (proc.stdout + proc.stderr)[-2000:]
        assert json.loads(proc.stdout)["cc"]["proven"] is True
    finally:
        live.shutdown()
        live.server_close()
    dead, dead_port = _serve(_Health401)
    try:
        proc = _run_cli(base + ["doctor", "--cc-url",
                                "http://127.0.0.1:%d" % dead_port,
                                "--cc-required"], env, tmp_path)
        assert proc.returncode != 0, proc.stdout
        assert json.loads(proc.stdout)["cc"]["proven"] is False
    finally:
        dead.shutdown()
