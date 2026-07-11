#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_e10_engine_drift_guard.py -- E10 coverage.

Two things are proved here, matching docs/E10-SHARED-SCRIPT-DRIFT-CLASSIFICATION.md:

1. engine_script_drift_guard.py's own baseline mechanism works (self-test wiring,
   exercised again here via pytest rather than only its own --self-test CLI).
2. The THREE genuinely-shared invariants identified by the classification --
   across pairs that are otherwise independently-designed, NOT drifted copies of
   one origin -- hold identically in both engines' real, unmodified files. Zero
   changes to either engine's runtime files: this is pure behavioral-parity
   verification, so it carries zero regression risk to either engine's own gates.

Run: python3 -m pytest shared-utils/test_e10_engine_drift_guard.py
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PODCAST_SCRIPTS = REPO_ROOT / "58-podcast-production-engine" / "scripts"
ANTHOLOGY_SCRIPTS = REPO_ROOT / "59-anthology-engine" / "scripts"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# 1. The baseline guard itself.
# ---------------------------------------------------------------------------
def test_drift_guard_self_test_passes():
    guard = REPO_ROOT / "shared-utils" / "engine_script_drift_guard.py"
    proc = subprocess.run([sys.executable, str(guard), "--self-test"],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_repo_currently_matches_recorded_baseline():
    """The live repo state must match the recorded baseline. If this fails, one of
    the four pairs has been edited since the baseline was last (consciously)
    updated -- read docs/E10-SHARED-SCRIPT-DRIFT-CLASSIFICATION.md, confirm the
    change is reviewed/intentional, then re-run
    `python3 shared-utils/engine_script_drift_guard.py --update-baseline`."""
    guard = REPO_ROOT / "shared-utils" / "engine_script_drift_guard.py"
    proc = subprocess.run([sys.executable, str(guard), "--json"],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, (
        "E10 baseline drift detected (unreviewed):\n" + proc.stdout + proc.stderr
    )


# ---------------------------------------------------------------------------
# 2a. guard-no-anthropic-runtime.py -- the six MODEL-ID-SHAPE patterns both
# engines independently implement and share (see classification doc: the
# sk-ant-/ANTHROPIC_API_KEY value shapes are NOT shared -- 58 folds them into
# this file, 59 delegates them to the sibling scan-no-secrets.sh -- so those are
# deliberately excluded from this battery).
# ---------------------------------------------------------------------------
ANTHROPIC_SHAPE_POSITIVES = [
    'model = "claude-opus-4-20260101"',
    "route via anthropic/claude-3-opus",
    "arn: us.anthropic.claude-v2:1",
    "import from '@anthropic-ai/sdk'",
    "POST https://api.anthropic.com/v1/messages",
    '"provider": "anthropic"',
]
ANTHROPIC_SHAPE_NEGATIVES = [
    "we never call anthropic or claude in this engine",
    "deny_patterns: [claude, anthropic, opus, sonnet, haiku]",
    "class AnthropicIdentifierError(ValueError): pass",
]


def _podcast_anthropic_guard():
    return _load(PODCAST_SCRIPTS / "guard-no-anthropic-runtime.py", "e10_g58_anthropic")


def _anthology_anthropic_guard():
    return _load(ANTHOLOGY_SCRIPTS / "guard-no-anthropic-runtime.py", "e10_g59_anthropic")


def test_anthropic_guard_shared_shapes_both_flag_every_positive():
    g58 = _podcast_anthropic_guard()
    g59 = _anthology_anthropic_guard()
    for text in ANTHROPIC_SHAPE_POSITIVES:
        assert bool(g58.scan_anthropic(text)), "58 guard missed a shared shape: %r" % text
        assert g59.deny(text), "59 guard missed a shared shape: %r" % text


def test_anthropic_guard_shared_shapes_both_clear_every_negative():
    g58 = _podcast_anthropic_guard()
    g59 = _anthology_anthropic_guard()
    for text in ANTHROPIC_SHAPE_NEGATIVES:
        assert not bool(g58.scan_anthropic(text)), "58 guard false-positived on: %r" % text
        assert not g59.deny(text), "59 guard false-positived on: %r" % text


# ---------------------------------------------------------------------------
# 2b. guard-cron-inventory.py -- the "exactly one recurring engine job passes,
# two or more fails" invariant, over each engine's OWN inventory shape (they are
# NOT interchangeable shapes -- that is the point; each is driven through its
# own real entry point).
# ---------------------------------------------------------------------------
def _podcast_cron_guard():
    return _load(PODCAST_SCRIPTS / "guard-cron-inventory.py", "e10_g58_cron")


def _anthology_cron_guard():
    return _load(ANTHOLOGY_SCRIPTS / "guard-cron-inventory.py", "e10_g59_cron")


def test_cron_guard_one_job_passes_both_engines():
    g58 = _podcast_cron_guard()
    ns58 = re.compile(g58._DEFAULT_NAMESPACE)
    cre58 = re.compile(r"[-_]([a-z0-9]+)$")
    one_58 = [{"name": "podcast-daily-smoke-acme", "schedule": "0 6 * * *", "kind": "cron"}]
    assert g58.audit_inventory(one_58, ns58, cre58) == []

    g59 = _anthology_cron_guard()
    one_59 = [{"name": "anthology-daily-tick",
              "schedule": {"kind": "cron", "expr": "0 6 * * *"}, "enabled": True}]
    result = g59.analyze(one_59, expect="one")
    assert result["ok"] is True, result["violations"]


def test_cron_guard_two_jobs_fails_both_engines():
    g58 = _podcast_cron_guard()
    ns58 = re.compile(g58._DEFAULT_NAMESPACE)
    cre58 = re.compile(r"[-_]([a-z0-9]+)$")
    two_58 = [
        {"name": "podcast-daily-smoke-acme", "schedule": "0 6 * * *", "kind": "cron"},
        {"name": "podcast-daily-smoke2-acme", "schedule": "0 7 * * *", "kind": "cron"},
    ]
    findings = g58.audit_inventory(two_58, ns58, cre58)
    assert any(code == "AF-PPE-SECOND-CRON" for code, _detail in findings), findings

    g59 = _anthology_cron_guard()
    two_59 = [
        {"name": "anthology-daily-tick",
         "schedule": {"kind": "cron", "expr": "0 6 * * *"}, "enabled": True},
        {"name": "anthology-daily-tick-2",
         "schedule": {"kind": "cron", "expr": "0 7 * * *"}, "enabled": True},
    ]
    result = g59.analyze(two_59, expect="one")
    assert result["ok"] is False
    assert any(v["code"] == "CRON-COUNT" for v in result["violations"]), result["violations"]


# ---------------------------------------------------------------------------
# 2c. alert-dedup.py -- "a second alert for the SAME identity within the dedup
# window is suppressed; a DIFFERENT identity is sent" -- driven through each
# engine's real CLI entry point (main()), in an isolated temp state dir, with
# the sole delivery seam stubbed so nothing ever leaves the box.
# ---------------------------------------------------------------------------
def _podcast_alert_dedup():
    return _load(PODCAST_SCRIPTS / "alert-dedup.py", "e10_g58_alertdedup")


def _anthology_alert_dedup():
    return _load(ANTHOLOGY_SCRIPTS / "alert-dedup.py", "e10_g59_alertdedup")


def test_alert_dedup_same_key_suppressed_both_engines(tmp_path, monkeypatch, capsys):
    ad58 = _podcast_alert_dedup()
    tmp58 = tmp_path / "ad58"
    tmp58.mkdir()
    monkeypatch.setattr(ad58, "_gateway_send", lambda target, text: (True, "ok"))
    monkeypatch.setenv("PODCAST_FOUNDER_ALERT_CHAT", "test-operator-chat")

    def _raise(client, service):
        return ad58.main(["raise", "--client", client, "--service", service,
                          "--failure-class", "timeout", "--message", "m",
                          "--state-dir", str(tmp58)])

    rc1 = _raise("c1", "s1")
    capsys.readouterr()
    rc2 = _raise("c1", "s1")  # same identity, same window -> suppressed
    out2 = capsys.readouterr().out
    rc3 = _raise("c1", "s2")  # different identity -> sent
    out3 = capsys.readouterr().out
    assert rc1 == 0
    assert rc2 == 0 and '"action": "suppressed"' in out2
    assert rc3 == 0 and '"action": "sent"' in out3

    ad59 = _anthology_alert_dedup()
    tmp59 = tmp_path / "ad59"
    tmp59.mkdir()
    r1, _c1 = ad59.do_send(dedup_key="k1", message="m1", state_dir=str(tmp59),
                           delivery_cmd="/usr/bin/true")
    r2, _c2 = ad59.do_send(dedup_key="k1", message="m1", state_dir=str(tmp59),
                           delivery_cmd="/usr/bin/true")
    r3, _c3 = ad59.do_send(dedup_key="k2", message="m1", state_dir=str(tmp59),
                           delivery_cmd="/usr/bin/true")
    assert r1["outcome"] == "sent"
    assert r2["outcome"] == "suppressed_window"
    assert r3["outcome"] == "sent"


if __name__ == "__main__":  # pragma: no cover
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
