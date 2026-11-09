#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_legacy_runner_authority.py — ENF-16 / ENF-17 / ENF-25 (U-enforcement-02).

The legacy Skill 49 funnel certificate ("process proven end to end") must not be producible
without the front door, with an invented model, or with a key the AI chose; the delegation
receipt store must be harness-written; the persona gate must fail closed on a 999 layout.

Run: python3 -m pytest 49-signature-funnel/scripts/test_legacy_runner_authority.py -q
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
for _p in (str(HERE), str(SKILL)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import delegation_receipt  # noqa: E402
import prove_sf_cert  # noqa: E402
import prove_sf_intake  # noqa: E402
import run_signature_funnel as runner  # noqa: E402

KEY = "operator-key-0123456789-abcdefghijklmnop"
ORCH = SKILL / "run_signature_funnel.py"


def _env(home: Path, **extra: str) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("SF_",)) and k != "SHARED_UTILS_DIR"}
    env["HOME"] = str(home)
    env["OPENCLAW_PLATFORM"] = "mac"      # an empty HOME has no ~/.openclaw to detect
    env.update(extra)
    return env


def _key_file(tmp_path: Path) -> Path:
    kf = tmp_path / "keys" / "operator.key"
    kf.parent.mkdir()
    kf.write_text(KEY + "\n", encoding="utf-8")
    kf.chmod(0o600)
    return kf


@pytest.fixture()
def home(tmp_path: Path) -> Path:
    h = tmp_path / "home"
    h.mkdir()
    return h


@pytest.fixture()
def keyed_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A run dir every phase accepts, built the way the harness would: operator-key-signed model
    receipt and harness-signed provider receipts. Returns (run_dir, key_file)."""
    kf = _key_file(tmp_path)
    monkeypatch.setenv("SF_OPERATOR_KEY_FILE", str(kf))
    # Skill 6 run-nonce files (the sealed verify run P7 re-reads) live outside the run dir; the
    # orchestrator subprocess inherits this dir through os.environ (see _env).
    monkeypatch.setenv("GHL_VERIFY_NONCE_DIR", str(tmp_path / "ghl-nonces"))
    rd = tmp_path / "run-legacy"
    rd.mkdir()
    runner._write_valid_run(rd, KEY)
    monkeypatch.delenv("SF_OPERATOR_KEY_FILE")
    return rd, kf


def _orch(rd: Path, home: Path, *extra: str, **env: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(ORCH), "--run-dir", str(rd), *extra],
                          capture_output=True, text=True, env=_env(home, **env), timeout=300)


# ---------------------------------------------------------------- ENF-16: the front door
def test_nonce_file_and_nonce_are_refused_even_when_self_made(keyed_run, home):
    rd, kf = keyed_run
    nonce = "a-nonce-the-ai-made-0123456789"
    (rd / ".sf_run_nonce").write_text(nonce, encoding="utf-8")        # self-made nonce file
    for extra in (("--nonce", nonce), ("--nonce-file", str(rd / ".sf_run_nonce")),
                  ("--nonce", nonce, "--nonce-file", str(rd / ".sf_run_nonce"))):
        # even WITH the operator key present: a caller-supplied nonce is never an input
        r = _orch(rd, home, *extra, SF_OPERATOR_KEY_FILE=str(kf))
        assert r.returncode == runner.EXIT_FRONT_DOOR, r.stdout + r.stderr
        assert "AF-FUN-FRONT-DOOR" in r.stdout
        assert not (rd / "PROCESS-CERTIFICATE.json").exists()


def test_sf_run_nonce_env_is_refused(keyed_run, home):
    rd, kf = keyed_run
    r = _orch(rd, home, SF_RUN_NONCE="a-nonce-the-ai-made-0123456789", SF_OPERATOR_KEY_FILE=str(kf))
    assert r.returncode == runner.EXIT_FRONT_DOOR, r.stdout + r.stderr
    assert "AF-FUN-FRONT-DOOR" in r.stdout and "SF_RUN_NONCE" in r.stdout
    assert not (rd / "PROCESS-CERTIFICATE.json").exists()


def test_direct_call_with_self_made_nonce_file_and_no_operator_key_exits_front_door(keyed_run, home):
    rd, _ = keyed_run
    nonce = "a-nonce-the-ai-made-0123456789"
    (rd / ".sf_run_nonce").write_text(nonce, encoding="utf-8")
    # the pre-fix front door accepted exactly this call
    for extra in ((), ("--nonce", nonce)):
        r = _orch(rd, home, *extra)
        assert r.returncode == runner.EXIT_FRONT_DOOR, r.stdout + r.stderr
        assert "AF-FUN-FRONT-DOOR" in r.stdout
        assert not (rd / "PROCESS-CERTIFICATE.json").exists()


def test_operator_key_inside_run_dir_or_loose_mode_is_refused(keyed_run, home, tmp_path):
    rd, kf = keyed_run
    inside = rd / "operator.key"
    inside.write_text(KEY, encoding="utf-8")
    inside.chmod(0o600)
    loose = tmp_path / "loose.key"
    loose.write_text(KEY, encoding="utf-8")
    loose.chmod(0o644)
    short = tmp_path / "short.key"
    short.write_text("short", encoding="utf-8")
    short.chmod(0o600)
    for bad in (inside, loose, short):
        r = _orch(rd, home, SF_OPERATOR_KEY_FILE=str(bad))
        assert r.returncode == runner.EXIT_FRONT_DOOR, (bad.name, r.stdout + r.stderr)
        assert "AF-FUN-FRONT-DOOR" in r.stdout


def test_model_receipt_is_not_taken_from_sf_content_model_env(keyed_run, home):
    rd, kf = keyed_run
    (rd / prove_sf_cert.MODEL_RECEIPT_REL).unlink()
    r = _orch(rd, home, SF_OPERATOR_KEY_FILE=str(kf), SF_CONTENT_MODEL="deepseek-v3-chat",
              SF_CONTENT_PROVIDER="deepseek", SF_CONTENT_TIER="content")
    assert r.returncode == runner.EXIT_FRONT_DOOR, r.stdout + r.stderr
    assert "AF-FUN-MODEL-TIER" in r.stdout
    assert not (rd / "PROCESS-CERTIFICATE.json").exists()
    # the pre-fix entry shell wrote an env-reported receipt like this one: refused
    (rd / prove_sf_cert.MODEL_RECEIPT_REL).write_text(json.dumps(
        {"role": "content", "resolved_from": "client-provider-chain", "model": "deepseek-v3-chat",
         "provider": "deepseek", "tier": "content"}), encoding="utf-8")
    r = _orch(rd, home, SF_OPERATOR_KEY_FILE=str(kf), SF_CONTENT_MODEL="deepseek-v3-chat")
    assert r.returncode == runner.EXIT_FRONT_DOOR and "AF-FUN-MODEL-TIER" in r.stdout


def test_model_receipt_mint_reads_the_harness_record_and_ignores_env(tmp_path, home, monkeypatch):
    kf = _key_file(tmp_path)
    rd = tmp_path / "run-mint"
    rd.mkdir()
    record = tmp_path / "routing-record.json"
    record.write_text(json.dumps({"model": "harness-chosen-model", "provider": "harness-prov",
                                  "tier": "content"}), encoding="utf-8")
    cli = [sys.executable, str(HERE / "prove_sf_cert.py"), "--mint-model-receipt", str(record),
           "--run-dir", str(rd)]
    r = subprocess.run(cli, capture_output=True, text=True, env=_env(home))
    assert r.returncode == prove_sf_cert.EXIT_FAILCLOSED          # no operator key -> cannot mint
    r = subprocess.run(cli, capture_output=True, text=True,
                       env=_env(home, SF_OPERATOR_KEY_FILE=str(kf), SF_CONTENT_MODEL="env-invented-model"))
    assert r.returncode == 0, r.stdout + r.stderr
    receipt = json.loads((rd / prove_sf_cert.MODEL_RECEIPT_REL).read_text(encoding="utf-8"))
    assert receipt["model"] == "harness-chosen-model" and "env-invented" not in json.dumps(receipt)
    assert not prove_sf_cert.evaluate_model_receipt(receipt, KEY, rd.name)
    assert prove_sf_cert.evaluate_model_receipt(receipt, "another-key-0123456789abcdefghij", rd.name)


def test_certificate_is_minted_with_the_operator_key_and_verifies_only_with_it(keyed_run, home):
    rd, kf = keyed_run
    r = _orch(rd, home, SF_OPERATOR_KEY_FILE=str(kf))
    assert r.returncode == runner.EXIT_OK, r.stdout + r.stderr
    cert_path = rd / "PROCESS-CERTIFICATE.json"
    cert = json.loads(cert_path.read_text(encoding="utf-8"))
    assert "nonce_fingerprint" not in cert and cert["model_receipt"]["resolved_from"] == "harness-routing-record"
    verify = [sys.executable, str(HERE / "prove_sf_cert.py"), "--cert", str(cert_path)]
    ok = subprocess.run(verify, capture_output=True, text=True, env=_env(home, SF_OPERATOR_KEY_FILE=str(kf)))
    assert ok.returncode == 0, ok.stdout
    # certificate verify FAILS without the operator key ...
    nokey = subprocess.run(verify, capture_output=True, text=True, env=_env(home))
    assert nokey.returncode == prove_sf_cert.EXIT_VIOLATION and "AF-FUN-CERT-SIGNATURE" in nokey.stdout
    # ... and with a key the AI chose (a forged cert signed with a self-made key)
    forged = dict(cert)
    forged["signature"] = prove_sf_cert.sign(prove_sf_cert.canonical_payload(forged),
                                             "the-ai-chose-this-key-0123456789abcdef")
    forged_path = rd / "FORGED.json"
    forged_path.write_text(json.dumps(forged), encoding="utf-8")
    bad = subprocess.run([sys.executable, str(HERE / "prove_sf_cert.py"), "--cert", str(forged_path)],
                         capture_output=True, text=True, env=_env(home, SF_OPERATOR_KEY_FILE=str(kf)))
    assert bad.returncode == prove_sf_cert.EXIT_VIOLATION and "AF-FUN-CERT-SIGNATURE" in bad.stdout
    # the verifier no longer takes --nonce / SF_RUN_NONCE at all
    n1 = subprocess.run(verify + ["--nonce", "x"], capture_output=True, text=True,
                        env=_env(home, SF_OPERATOR_KEY_FILE=str(kf)))
    n2 = subprocess.run(verify, capture_output=True, text=True,
                        env=_env(home, SF_OPERATOR_KEY_FILE=str(kf), SF_RUN_NONCE="x"))
    assert n1.returncode == prove_sf_cert.EXIT_FAILCLOSED and n2.returncode == prove_sf_cert.EXIT_FAILCLOSED


# ---------------------------------------------------------------- ENF-17: receipt store
def _write_unsigned_store(rd: Path, ids) -> None:
    with (rd / delegation_receipt.RECEIPTS_REL).open("w", encoding="utf-8") as fh:
        for i in ids:
            fh.write(json.dumps({"phase": "P3-IMAGES", "provider": "kie", "operation": "createTask",
                                 "provider_response_id": f"kie-resp-{i}", "http_status": 200,
                                 "remote_id": i, "covers": [i], "recorded_by": "kie_image_adapter",
                                 "at": "2026-11-02T00:00:00Z"}) + "\n")


def test_absent_receipt_store_fails_a_client_delivery(tmp_path, monkeypatch):
    monkeypatch.setenv("SF_OPERATOR_KEY_FILE", str(_key_file(tmp_path)))
    rd = tmp_path / "run-a"
    rd.mkdir()
    ok, detail = delegation_receipt.verify_delivery_store(rd, ["P3-IMAGES"])
    assert not ok and "ABSENT" in detail
    ok, detail = delegation_receipt.require_signed(rd, "P3-IMAGES")
    assert not ok and "ABSENT" in detail
    # the delegated legacy seam used to attest 'absent' and record it; it now fails
    (rd / "media_ledger.json").write_text(json.dumps({"images": [
        {"page_type": "main", "section": "1", "kie_task_id": "kie-1",
         "media_url": "https://storage.gohighlevel.com/x.png"}]}), encoding="utf-8")
    ok, detail = runner._gate_p3_images(rd)
    assert not ok and "ABSENT" in detail


def test_self_written_receipt_store_fails_a_client_delivery(tmp_path, monkeypatch):
    monkeypatch.setenv("SF_OPERATOR_KEY_FILE", str(_key_file(tmp_path)))
    rd = tmp_path / "run-b"
    rd.mkdir()
    _write_unsigned_store(rd, ["img-a"])                  # honest-looking, hand-appended
    ok, detail = delegation_receipt.verify_delivery_store(rd, ["P3-IMAGES"])
    assert not ok and "UNSIGNED" in detail
    assert delegation_receipt.store_state(rd) == "unsigned"
    # the transitional validator accepted this; the delivery form does not
    assert delegation_receipt.validate_if_present(rd, "P3-IMAGES", must_cover=["img-a"])[0]
    assert not delegation_receipt.require_signed(rd, "P3-IMAGES", must_cover=["img-a"])[0]
    # a line the harness signed, then edited by hand, fails too
    delegation_receipt.reset(rd)
    import stub_provider_adapter
    stub_provider_adapter.emit(rd, "P3-IMAGES", ["img-a"])
    assert delegation_receipt.verify_delivery_store(rd, ["P3-IMAGES"])[0]
    line = json.loads((rd / delegation_receipt.RECEIPTS_REL).read_text(encoding="utf-8"))
    line["covers"] = ["img-a", "img-ghost"]
    (rd / delegation_receipt.RECEIPTS_REL).write_text(json.dumps(line) + "\n", encoding="utf-8")
    assert not delegation_receipt.verify_delivery_store(rd)[0]


def test_delivery_store_cli_exit_codes(tmp_path, home):
    kf = _key_file(tmp_path)
    rd = tmp_path / "run-c"
    rd.mkdir()
    cli = [sys.executable, str(HERE / "delegation_receipt.py"), "--run-dir", str(rd), "--verify-delivery"]
    assert subprocess.run(cli, capture_output=True, text=True,
                          env=_env(home, SF_OPERATOR_KEY_FILE=str(kf))).returncode == 2   # absent
    rec = [sys.executable, str(HERE / "delegation_receipt.py"), "--run-dir", str(rd), "--record",
           "--adapter", "kie_image_adapter", "--phase", "P3-IMAGES", "--provider", "kie",
           "--response-id", "kie-resp-1", "--http-status", "200", "--remote-id", "img-a",
           "--covers", "img-a"]
    assert subprocess.run(rec, capture_output=True, text=True, env=_env(home)).returncode == 0
    assert subprocess.run(cli + ["P3-IMAGES"], capture_output=True, text=True,
                          env=_env(home, SF_OPERATOR_KEY_FILE=str(kf))).returncode == 2   # unsigned
    (rd / delegation_receipt.RECEIPTS_REL).unlink()
    assert subprocess.run(rec, capture_output=True, text=True,
                          env=_env(home, SF_OPERATOR_KEY_FILE=str(kf))).returncode == 0   # adapter holds key
    ok = subprocess.run(cli + ["P3-IMAGES"], capture_output=True, text=True,
                        env=_env(home, SF_OPERATOR_KEY_FILE=str(kf)))
    assert ok.returncode == 0, ok.stdout


# ---------------------------------------------------------------- ENF-25: persona registry
def _brief(rd: Path, slug: str) -> Path:
    rd.mkdir(parents=True, exist_ok=True)
    (rd / "brief.json").write_text(json.dumps(prove_sf_intake._valid_runtime(3)), encoding="utf-8")
    (rd / "persona-selection-log.md").write_text(f"- selected_persona: {slug}\n", encoding="utf-8")
    return rd / "brief.json"


def _prove_intake(skill_dir: Path, brief: Path, home: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(skill_dir / "scripts" / "prove_sf_intake.py"), str(brief)],
                          capture_output=True, text=True, env=_env(home))


def test_p0_with_unregistered_slug_fails_in_a_999_layout(tmp_path, home):
    # 999 layout: Skill 49 installed alone, no Skill 22/23 persona registry beside it or under HOME.
    box = tmp_path / "skills999"
    shutil.copytree(SKILL, box / "49-signature-funnel",
                    ignore=shutil.ignore_patterns("__pycache__", "working", "*.pyc"))
    for slug in ("totally-invented-persona", "hormozi-100m-offers"):
        r = _prove_intake(box / "49-signature-funnel", _brief(tmp_path / f"rd-{slug}", slug), home)
        assert r.returncode == prove_sf_intake.EXIT_AUTOFAIL, r.stdout + r.stderr
        assert "AF-FUN-INTAKE-PERSONA-LOG" in r.stdout and "registry unresolved" in r.stdout


def test_p0_control_repo_layout_still_accepts_a_registered_slug_and_refuses_an_invented_one(tmp_path, home):
    good = _prove_intake(SKILL, _brief(tmp_path / "rd-ok", "hormozi-100m-offers"), home)
    assert good.returncode == 0, good.stdout + good.stderr
    bad = _prove_intake(SKILL, _brief(tmp_path / "rd-bad", "totally-invented-persona"), home)
    assert bad.returncode == prove_sf_intake.EXIT_AUTOFAIL and "not a registered persona" in bad.stdout


def test_p0_installed_registry_under_home_resolves(tmp_path, home):
    box = tmp_path / "skills999"
    shutil.copytree(SKILL, box / "49-signature-funnel",
                    ignore=shutil.ignore_patterns("__pycache__", "working", "*.pyc"))
    reg = home / ".openclaw" / "skills" / "22-book-to-persona-coaching-leadership-system" / "personas"
    (reg / "hormozi-100m-offers").mkdir(parents=True)
    ok = _prove_intake(box / "49-signature-funnel", _brief(tmp_path / "rd-h", "hormozi-100m-offers"), home)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    bad = _prove_intake(box / "49-signature-funnel", _brief(tmp_path / "rd-i", "totally-invented-persona"), home)
    assert bad.returncode == prove_sf_intake.EXIT_AUTOFAIL


# ---------------------------------------------------------------- ENF-17: consumer that loads by file path
_BYPATH = (
    "import importlib.util, json, sys, pathlib\n"
    "spec = importlib.util.spec_from_file_location('dr_bypath', sys.argv[1])\n"
    "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
    "assert str(pathlib.Path(sys.argv[1]).parent) not in sys.path\n"
    "m._CLI_ADAPTER = 'kie_image_adapter'\n"      # a separate adapter process naming itself
    "rd = pathlib.Path(sys.argv[2])\n"
    "e = m.record(rd, phase='P3-IMAGES', provider='kie', operation='createTask',\n"
    "             provider_response_id='task-123', http_status=200, remote_id='media-456', covers=['img-1'])\n"
    "print(json.dumps({'signed': 'harness_sig' in e, 'ok': m.verify_delivery_store(rd, ['P3-IMAGES'])[0],\n"
    "                  'state': m.store_state(rd)}))\n"
)


def _bypath(tmp_path: Path, home: Path, name: str, **env: str) -> dict:
    rd = tmp_path / name
    rd.mkdir()
    r = subprocess.run([sys.executable, "-I", "-c", _BYPATH, str(HERE / "delegation_receipt.py"), str(rd)],
                       capture_output=True, text=True, cwd=str(tmp_path), env=_env(home, **env), timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout)


def test_receipt_module_loaded_by_file_path_still_finds_the_operator_key(tmp_path, home):
    kf = _key_file(tmp_path)
    keyed = _bypath(tmp_path, home, "run-keyed", SF_OPERATOR_KEY_FILE=str(kf))
    assert keyed == {"signed": True, "ok": True, "state": "present"}
    unkeyed = _bypath(tmp_path, home, "run-unkeyed")
    assert unkeyed == {"signed": False, "ok": False, "state": "unsigned"}
