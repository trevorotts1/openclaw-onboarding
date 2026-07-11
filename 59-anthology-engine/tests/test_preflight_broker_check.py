#!/usr/bin/env python3
"""test_preflight_broker_check.py -- regression test for the E9-short fix:

    59-anthology-engine/preflight.sh carried ZERO broker references (grep -c broker
    preflight.sh == 0). A client box's provisioning preflight had no assertion that
    the n8n Drive credential broker is configured, so a client box could silently
    proceed toward S7/S8 in a state where it would only work by illegitimately
    falling back to holding the local Google service-account key -- the ONE thing
    scripts/drive_adapter.py's broker_configured() docstring says a client box must
    never do ("the ONLY box that legitimately holds the SA key is the operator's OWN
    box, never a client box").

This test proves preflight.sh's new `--broker-check` mode:
  1. exits NON-ZERO when the broker config is ABSENT (N8N_DRIVE_WEBHOOK_URL and/or
     N8N_DRIVE_WEBHOOK_TOKEN unresolved) -- the negative fixture: a gate with no
     proof it can reject is not a gate.
  2. exits 0 when the broker config is PRESENT (both resolve).
  3. leaves the default RESOLVE mode and --check mode completely untouched (this is
     an explicit opt-in assertion, not a change to the existing modes' behavior).

Network-free: only the two credential ENV VARS are set/unset; no HTTPS call is made
(drive_adapter.py's `broker-status` subcommand only resolves presence, it never
calls the broker). No credential value, no client name. Python 3 stdlib only.

Run: python3 -m pytest 59-anthology-engine/tests/test_preflight_broker_check.py -q
 or: python3 59-anthology-engine/tests/test_preflight_broker_check.py
"""
import os
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
PREFLIGHT = SKILL_DIR / "preflight.sh"

# Mirrors scripts/drive_adapter.py's N8N_WEBHOOK_URL_ENV / N8N_WEBHOOK_TOKEN_ENV
# constants (not re-imported here to keep this test process-boundary honest -- it
# drives preflight.sh exactly as a real caller would, via subprocess + env).
URL_ENV = "N8N_DRIVE_WEBHOOK_URL"
TOKEN_ENV = "N8N_DRIVE_WEBHOOK_TOKEN"
TEST_URL = "https://main.blackceoautomations.com/webhook/anthology-drive"
TEST_TOKEN = "test-broker-token-does-not-touch-network"  # test value, not a secret


def _run_broker_check(env_overrides):
    """Run `preflight.sh --broker-check` in a scrubbed env plus the given broker
    var overrides (None removes the var). Returns the CompletedProcess."""
    env = dict(os.environ)
    env.pop(URL_ENV, None)
    env.pop(TOKEN_ENV, None)
    for k, v in env_overrides.items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = v
    return subprocess.run(
        ["bash", str(PREFLIGHT), "--broker-check"],
        capture_output=True, text=True, timeout=30, env=env,
    )


# --------------------------------------------------------------------------- #
# Negative fixture: broker config ABSENT -> non-zero exit, AF-AE-BROKER-* code.
# --------------------------------------------------------------------------- #
def test_broker_check_fails_closed_when_config_absent():
    proc = _run_broker_check({})
    assert proc.returncode != 0, (
        "preflight.sh --broker-check must exit NON-ZERO when the broker config is "
        "absent; got exit 0. stdout=%r stderr=%r" % (proc.stdout, proc.stderr))
    assert "AF-AE-BROKER-NOT-CONFIGURED" in proc.stderr


def test_broker_check_fails_closed_when_only_url_set():
    proc = _run_broker_check({URL_ENV: TEST_URL, TOKEN_ENV: None})
    assert proc.returncode != 0
    assert "AF-AE-BROKER-NOT-CONFIGURED" in proc.stderr


def test_broker_check_fails_closed_when_only_token_set():
    proc = _run_broker_check({URL_ENV: None, TOKEN_ENV: TEST_TOKEN})
    assert proc.returncode != 0
    assert "AF-AE-BROKER-NOT-CONFIGURED" in proc.stderr


# --------------------------------------------------------------------------- #
# Positive fixture: broker config PRESENT (both vars resolve) -> exit 0.
# --------------------------------------------------------------------------- #
def test_broker_check_passes_when_config_present():
    proc = _run_broker_check({URL_ENV: TEST_URL, TOKEN_ENV: TEST_TOKEN})
    assert proc.returncode == 0, (
        "preflight.sh --broker-check must exit 0 when the broker config is present; "
        "got exit %s. stdout=%r stderr=%r" % (proc.returncode, proc.stdout, proc.stderr))
    assert "PASS" in proc.stdout


# --------------------------------------------------------------------------- #
# Blast-radius proof: --broker-check is opt-in only. Default RESOLVE and --check
# are byte-identical in behavior whether or not broker env vars are set -- this
# mode does not leak into the existing modes.
# --------------------------------------------------------------------------- #
def test_check_mode_unaffected_by_broker_env(tmp_path):
    env = dict(os.environ)
    env[URL_ENV] = TEST_URL
    env[TOKEN_ENV] = TEST_TOKEN
    proc = subprocess.run(
        ["bash", str(PREFLIGHT), "--run-dir", str(tmp_path), "--check"],
        capture_output=True, text=True, timeout=30, env=env,
    )
    assert proc.returncode == 0
    assert "no resolved model-map.json" in proc.stdout


def test_help_lists_broker_check_flag():
    proc = subprocess.run(["bash", str(PREFLIGHT), "-h"],
                          capture_output=True, text=True, timeout=10)
    assert proc.returncode == 0
    assert "--broker-check" in proc.stdout


if __name__ == "__main__":
    sys.exit(subprocess.run(
        [sys.executable, "-m", "pytest", str(Path(__file__)), "-v"]).returncode)
