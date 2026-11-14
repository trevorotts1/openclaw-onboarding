#!/usr/bin/env python3
"""PD-201 — the run-folder marker no longer opens checks in production.

Acceptance row A1, verbatim from 01-BUILD-SPEC.md:

  "the PD-201 probe as a test: with only the marker file -> all three checks
   fail; with the environment variable -> pass, and the log file gains a line."

The three checks are the three engine-backed substance verifiers whose degraded
fallback goes through _degraded_allowed: P-0.5-RESEARCH, P4-COPY, P4-PROMPT.
"""
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import phase_verifiers as pv  # noqa: E402

CHECKS = ("P-0.5-RESEARCH", "P4-COPY", "P4-PROMPT")
ENV_KEY = "PRESENTATION_ALLOW_DEGRADED_VERIFIERS"


@pytest.fixture(autouse=True)
def _no_degraded_env(monkeypatch):
    for key in (ENV_KEY, "CI", "OPENCLAW_TEST"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def run_dir(tmp_path, monkeypatch):
    """Artifacts that PASS the existence floors; engines forced absent so every
    check reaches its degraded fallback."""
    (tmp_path / "working" / "research").mkdir(parents=True)
    (tmp_path / "working" / "research" / "brief-201.md").write_text("x" * 200)
    (tmp_path / "working" / "copy").mkdir(parents=True)
    (tmp_path / "working" / "copy" / "slides_copy.md").write_text("x" * 120)
    (tmp_path / "working" / "prompts").mkdir(parents=True)
    (tmp_path / "working" / "prompts" / "slide-01.txt").write_text("x" * 200)
    monkeypatch.setattr(pv, "_bd", None)
    monkeypatch.setattr(pv, "_crg", None)
    monkeypatch.setattr(pv, "_iec", None)
    monkeypatch.setattr(pv, "_pec", None)
    return tmp_path


def _marker(run_dir):
    p = run_dir / "working" / "checkpoints" / ".test-context"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("pd-201 probe")


def test_marker_file_alone_opens_nothing(run_dir):
    _marker(run_dir)
    for phase in CHECKS:
        ok, reasons = pv.verify(phase, run_dir)
        assert ok is False, f"{phase} passed on the marker file alone: {reasons}"
        assert reasons and not str(reasons[0]).startswith("NOTE"), reasons
    assert not (run_dir / "working" / "checkpoints" / "gate_log.jsonl").exists()


def test_env_variable_passes_and_logs_a_line(run_dir, monkeypatch):
    _marker(run_dir)  # the marker alone must not matter; the env var is the signal
    monkeypatch.setenv(ENV_KEY, "1")
    for phase in CHECKS:
        ok, reasons = pv.verify(phase, run_dir)
        assert ok is True, f"{phase} failed under {ENV_KEY}=1: {reasons}"
        assert any(str(r).startswith("NOTE") for r in reasons), reasons
    log = run_dir / "working" / "checkpoints" / "gate_log.jsonl"
    assert log.is_file(), "a degraded pass must append gate_log.jsonl"
    rows = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    assert [r["gate"] for r in rows] == list(CHECKS)
    assert all(r["result"] == "degraded_pass" and r["reason"] for r in rows)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
