#!/usr/bin/env python3
"""
test_fix14_agent_env.py — FIX-14 regression-guard test.

Proves the FIX-14 defense against Error 8 / D-8 (MC_API_TOKEN was NOT in the
gateway env -> every Command Center write silently 401'd for ~15 days):

  1. check_agent_env.probe() verdict matrix (hermetic, synthetic environ):
       PASS                     both labels resolve AND are in managed keys
       AF-AGENT-ENV-MISSING     a required label absent (exit 2)
       AF-AGENT-ENV-UNMANAGED   a label present but NOT in managed keys (exit 2)
     plus live-process-first precedence, stores_checked exhaustiveness, and the
     never-a-value guarantee (no token string in the report payload).

  2. check_agent_env.py CLI:
       --self-test -> exit 0
       --json -> parseable report.

  3. regenerate-gateway-env.sh (SVC_ENV test seam): wiring a synthetic gateway
     env file adds MC_API_TOKEN + MISSION_CONTROL_URL to the managed list AND
     exports each when the live process env carries it; re-run is a no-op.

  4. run_signature_deck.phase0_preflight() enforcement: with the probe returning
     AF-AGENT-ENV-UNMANAGED the preflight exits 4 naming the verdict; with a PASS
     report it proceeds past the guard.

Pytest-native (each test_* uses assert) AND directly runnable
(`python3 tests/test_fix14_agent_env.py`) via the main() wrapper below.

Run:  python3 tests/test_fix14_agent_env.py     # direct
      python3 -m pytest tests/test_fix14_agent_env.py -q
Exit: 0 = all assertions passed; 1 = a case failed.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import check_agent_env as cae  # noqa: E402

REAL_TOKEN = "MC-UNIT-TEST-" + "a1b2c3d4e5f6" * 2  # real-shaped, synthetic
URL = "https://cc.example.test"


def _env(**extra):
    base = {
        "MC_API_TOKEN": REAL_TOKEN,
        "MISSION_CONTROL_URL": URL,
        "OPENCLAW_SERVICE_MANAGED_ENV_KEYS":
            "KIE_API_KEY,MC_API_TOKEN,MISSION_CONTROL_URL,GHL_API_KEY",
    }
    base.update(extra)
    return base


# ---------------------------------------------------------------------------
# 1) probe() verdict matrix
# ---------------------------------------------------------------------------
def test_probe():
    # PASS.
    rep = cae.probe(environ=_env(), store_paths=[], extra_stores=[])
    assert rep["verdict"] == "PASS" and rep["exit_code"] == 0, rep
    assert rep["resolutions"]["MC_API_TOKEN"]["source"] == "process-env", rep
    blob = json.dumps(rep)
    assert REAL_TOKEN not in blob and URL not in blob, "value leaked into report"

    # MISSING.
    env = _env()
    del env["MC_API_TOKEN"]
    rep = cae.probe(environ=env, store_paths=[], extra_stores=[])
    assert rep["verdict"] == "AF-AGENT-ENV-MISSING" and rep["exit_code"] == 2, rep
    assert "MC_API_TOKEN" in rep["missing"], rep

    # UNMANAGED.
    env = _env(OPENCLAW_SERVICE_MANAGED_ENV_KEYS="KIE_API_KEY,GHL_API_KEY")
    rep = cae.probe(environ=env, store_paths=[], extra_stores=[])
    assert rep["verdict"] == "AF-AGENT-ENV-UNMANAGED" and rep["exit_code"] == 2, rep
    assert set(rep["unmanaged"]) == {"MC_API_TOKEN", "MISSION_CONTROL_URL"}, rep

    # Store resolution + live-process-first precedence + exhaustiveness.
    with tempfile.TemporaryDirectory() as td:
        store = Path(td) / "ai.openclaw.gateway.env"
        store.write_text(
            "MC_API_TOKEN=%s\nMISSION_CONTROL_URL=%s\n"
            "OPENCLAW_SERVICE_MANAGED_ENV_KEYS=MC_API_TOKEN,MISSION_CONTROL_URL\n"
            % (REAL_TOKEN, URL))
        env = {"OPENCLAW_SERVICE_MANAGED_ENV_KEYS":
               "MC_API_TOKEN,MISSION_CONTROL_URL"}
        rep = cae.probe(environ=env, store_paths=[str(store)], extra_stores=[])
        assert rep["verdict"] == "PASS", rep
        assert rep["resolutions"]["MC_API_TOKEN"]["source"] == str(store), rep
        assert any(str(store) in s for s in rep["stores_checked"]), rep
        # process-env wins over the store.
        env2 = _env(MC_API_TOKEN=REAL_TOKEN + "-proc")
        rep2 = cae.probe(environ=env2, store_paths=[str(store)], extra_stores=[])
        assert rep2["resolutions"]["MC_API_TOKEN"]["source"] == "process-env", rep2

    # Idempotent clean.
    c1 = cae.probe(environ=_env(), store_paths=[], extra_stores=[])
    c2 = cae.probe(environ=_env(), store_paths=[], extra_stores=[])
    assert c1["exit_code"] == c2["exit_code"] == 0, "not idempotent"


# ---------------------------------------------------------------------------
# 2) CLI
# ---------------------------------------------------------------------------
def test_cli():
    r = subprocess.run(
        [sys.executable, str(HERE / "check_agent_env.py"), "--self-test"],
        capture_output=True, text=True, cwd=str(HERE))
    assert r.returncode == 0, r.stderr
    assert "self-test: PASS" in r.stdout, r.stdout

    with tempfile.TemporaryDirectory() as td:
        store = Path(td) / "gw.env"
        store.write_text(
            "MC_API_TOKEN=%s\nMISSION_CONTROL_URL=%s\n"
            "OPENCLAW_SERVICE_MANAGED_ENV_KEYS=MC_API_TOKEN,MISSION_CONTROL_URL\n"
            % (REAL_TOKEN, URL))
        env = dict(os.environ)
        env["OPENCLAW_SERVICE_MANAGED_ENV_KEYS"] = "MC_API_TOKEN,MISSION_CONTROL_URL"
        env.pop("MC_API_TOKEN", None)
        env.pop("MISSION_CONTROL_URL", None)
        r = subprocess.run(
            [sys.executable, str(HERE / "check_agent_env.py"), "--json"],
            capture_output=True, text=True, cwd=str(HERE), env=env)
        rep = json.loads(r.stdout)
        assert "verdict" in rep and "resolutions" in rep and "stores_checked" in rep, rep


# ---------------------------------------------------------------------------
# 3) regenerate-gateway-env.sh
# ---------------------------------------------------------------------------
def test_regenerate():
    script = HERE / "regenerate-gateway-env.sh"
    assert script.is_file(), "regenerate-gateway-env.sh missing"
    with tempfile.TemporaryDirectory() as td:
        env_file = Path(td) / "ai.openclaw.gateway.env"
        env_file.write_text(
            "export KIE_API_KEY=kietest123\n"
            "export GHL_API_KEY=ghltest456\n"
            "export OPENCLAW_SERVICE_MANAGED_ENV_KEYS=KIE_API_KEY,GHL_API_KEY\n"
            "export MC_API_TOKEN=%s\n" % REAL_TOKEN)
        penv = dict(os.environ)
        penv["SVC_ENV"] = str(env_file)
        penv["MC_API_TOKEN"] = REAL_TOKEN
        penv["MISSION_CONTROL_URL"] = URL
        r = subprocess.run(["bash", str(script)], capture_output=True, text=True,
                           cwd=str(HERE), env=penv)
        assert r.returncode == 0, r.stderr
        assert "MC_API_TOKEN" in r.stderr and "MISSION_CONTROL_URL" in r.stderr, r.stderr
        text = env_file.read_text()
        assert ("OPENCLAW_SERVICE_MANAGED_ENV_KEYS=KIE_API_KEY,GHL_API_KEY,"
                "MC_API_TOKEN,MISSION_CONTROL_URL" in text), text
        assert "export MISSION_CONTROL_URL=" in text, text
        assert REAL_TOKEN not in r.stderr and REAL_TOKEN not in r.stdout, "value printed"

        # Idempotent re-run is a no-op.
        before = env_file.read_text()
        r2 = subprocess.run(["bash", str(script)], capture_output=True, text=True,
                            cwd=str(HERE), env=penv)
        assert r2.returncode == 0, r2.stderr
        assert "no-op" in r2.stderr, r2.stderr
        assert env_file.read_text() == before, "re-run changed the file"

        # Probe against the regenerated file (hermetic store_paths seam) passes.
        rep = cae.probe(environ={
            "MC_API_TOKEN": REAL_TOKEN,
            "MISSION_CONTROL_URL": URL,
            "OPENCLAW_SERVICE_MANAGED_ENV_KEYS":
                "KIE_API_KEY,GHL_API_KEY,MC_API_TOKEN,MISSION_CONTROL_URL",
        }, store_paths=[str(env_file)], extra_stores=[])
        assert rep["verdict"] == "PASS", rep


# ---------------------------------------------------------------------------
# 4) phase0_preflight enforcement
# ---------------------------------------------------------------------------
def _mk_run_dir(prefix):
    root = Path(tempfile.mkdtemp(prefix=prefix))
    (root / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (root / "slides.json").write_text(json.dumps([{"slide": 1}]))
    return root


def test_phase0_preflight():
    import run_signature_deck as rsd
    assert rsd._agent_env is not None, "run_signature_deck must see check_agent_env"

    orig_probe = cae.probe
    try:
        # UNMANAGED -> exit 4.
        def _bad():
            return {"verdict": "AF-AGENT-ENV-UNMANAGED", "exit_code": 2,
                    "missing": [], "unmanaged": ["MC_API_TOKEN", "MISSION_CONTROL_URL"]}
        cae.probe = _bad
        root = _mk_run_dir("deck_fix14_")
        try:
            rsd.phase0_preflight(root, root / "slides.json", platform_override="mac")
            raise AssertionError("UNMANAGED env should exit 4, but phase0_preflight returned")
        except SystemExit as e:
            assert e.code == 4, e.code
        finally:
            shutil.rmtree(root)

        # PASS -> proceeds (Kie-balance may then stop on a missing key; that is
        # NOT this test's assertion — we only require no exit-4 with the env verdict).
        def _good():
            return {"verdict": "PASS", "exit_code": 0, "missing": [], "unmanaged": []}
        cae.probe = _good
        root = _mk_run_dir("deck_fix14_pass_")
        try:
            try:
                rsd.phase0_preflight(root, root / "slides.json", platform_override="mac")
            except SystemExit as e:
                assert e.code != 4, e.code
        finally:
            shutil.rmtree(root)
    finally:
        cae.probe = orig_probe


# ---------------------------------------------------------------------------
# Direct-run wrapper (pytest uses the test_* functions above).
# ---------------------------------------------------------------------------
def _run_all():
    failures = []
    for fn in (test_probe, test_cli, test_regenerate, test_phase0_preflight):
        try:
            fn()
            print(f"  [PASS] {fn.__name__}")
        except AssertionError as exc:
            failures.append((fn.__name__, exc))
            print(f"  [FAIL] {fn.__name__}: {exc}")
    print("=" * 60)
    if failures:
        print("FIX-14 test: FAIL — %d case(s) failed" % len(failures))
        return 1
    print("FIX-14 test: PASS — probe, CLI, regenerate, and phase0 enforcement all green.")
    return 0


if __name__ == "__main__":
    sys.exit(_run_all())
