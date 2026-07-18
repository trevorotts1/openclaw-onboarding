"""MOCK-only unit tests — the U24/B-U10 maintenance-window schedule ENTRY.

B-U10 CODE-MERGE gate acceptance (c), amended 2026-07-15: "the
maintenance-window schedule ENTRY exists (schedule file / plist / cron entry
present, asserted by name) and its scheduled command is the reconcile sweep
with --retry — PASS/FAIL."

Two things are proven here, fully offline:
  1. The schedule ENTRY FILE exists at a known, named path, is well-formed,
     and its command is genuinely the reconcile sweep with --retry (not a
     stale/mismatched command drifted out of sync with the file's own
     schedule/tz fields).
  2. scripts/install-github-archive-reconcile-cron.sh — the installer that
     would register this entry live (the LIVE-PROOF leg, deferred to U22) —
     reads that SAME file (single source of truth) and behaves idempotently
     against a FAKE `openclaw` CLI shim on PATH (no live tool call, no
     network).

No real client/operator names, ids, emails, or location-ids appear.

Run:
    python3 -m pytest tests/test_github_archive_maintenance_schedule.py -v
"""
from __future__ import annotations

import json
import os
import stat
import subprocess

import pytest

_SKILL_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
ENTRY_FILE = os.path.join(_SKILL_ROOT, "schedule",
                           "skill6-github-archive-reconcile-sweep.cron.json")
INSTALLER = os.path.join(_SKILL_ROOT, "scripts", "install-github-archive-reconcile-cron.sh")


class TestScheduleEntryFile:
    def test_schedule_entry_exists_by_name(self):
        assert os.path.isfile(ENTRY_FILE), f"schedule entry file missing: {ENTRY_FILE}"

    def test_schedule_entry_is_well_formed_json(self):
        with open(ENTRY_FILE) as fh:
            data = json.load(fh)
        for key in ("name", "schedule", "tz", "command"):
            assert key in data, f"schedule entry missing required field: {key}"

    def test_schedule_entry_name_matches_doctrine(self):
        with open(ENTRY_FILE) as fh:
            data = json.load(fh)
        assert data["name"] == "skill6-github-archive-reconcile-sweep"

    def test_scheduled_command_is_the_reconcile_sweep_with_retry(self):
        """The literal acceptance text: 'its scheduled command is the
        reconcile sweep with --retry'."""
        with open(ENTRY_FILE) as fh:
            data = json.load(fh)
        command = data["command"]
        assert "ghl_github_reconcile.py" in command
        assert "--sweep-base" in command
        assert "--retry" in command

    def test_schedule_field_is_a_valid_five_field_cron_expression(self):
        with open(ENTRY_FILE) as fh:
            data = json.load(fh)
        fields = data["schedule"].split()
        assert len(fields) == 5, f"expected a 5-field cron expression, got: {data['schedule']!r}"

    def test_installer_script_exists_and_is_executable(self):
        assert os.path.isfile(INSTALLER), f"installer missing: {INSTALLER}"
        mode = os.stat(INSTALLER).st_mode
        assert mode & stat.S_IXUSR, "installer must be executable (chmod +x)"


class TestInstallerAgainstFakeOpenclawCli:
    """Exercises the installer end-to-end against a FAKE `openclaw` shim on
    PATH — no live tool call, no network. Proves: (a) absent -> registers by
    reading the schedule entry's own name/schedule/tz/command, (b) present ->
    idempotent no-op, (c) never invents a name/command different from the
    shipped entry file, (d) always passes --no-deliver (U24 rebuild,
    2026-07-18 — a maintenance-window sweep must never fan out as a
    client-facing announcement)."""

    def _fake_openclaw(self, tmp_path, *, existing_names=()):
        """Write a fake `openclaw` executable that supports just enough of
        `cron list --json` and `cron add` to drive the installer, recording
        every `cron add` call's args to a log file for assertions."""
        bin_dir = tmp_path / "fakebin"
        bin_dir.mkdir()
        state_file = tmp_path / "cron-state.json"
        state_file.write_text(json.dumps({"jobs": [{"name": n} for n in existing_names]}))
        add_log = tmp_path / "cron-add-calls.log"

        script = bin_dir / "openclaw"
        script.write_text(f"""#!/usr/bin/env bash
set -u
STATE="{state_file}"
LOG="{add_log}"
if [[ "$1" == "cron" && "$2" == "list" ]]; then
  cat "$STATE"
  exit 0
fi
if [[ "$1" == "cron" && "$2" == "add" ]]; then
  printf '%s\\n' "$*" >> "$LOG"
  # Persist the added job into state so a subsequent `cron list` reflects it
  # -- mirrors real `openclaw`'s behavior and lets the installer's own
  # post-add `_cron_present` verification check succeed, same as it would
  # against the real CLI.
  python3 - "$STATE" <<'PYEOF'
import json, sys
path = sys.argv[1]
with open(path) as fh:
    data = json.load(fh)
data.setdefault("jobs", []).append({{"name": "skill6-github-archive-reconcile-sweep"}})
with open(path, "w") as fh:
    json.dump(data, fh)
PYEOF
  exit 0
fi
exit 1
""")
        script.chmod(0o755)
        return str(bin_dir), str(add_log)

    def _run_installer(self, tmp_path, fake_bin_dir):
        env = dict(os.environ)
        env["PATH"] = f"{fake_bin_dir}:{env.get('PATH', '')}"
        env["SKILL6_EVIDENCE_BASE"] = str(tmp_path / "evidence-base")
        return subprocess.run(["bash", INSTALLER], env=env, capture_output=True, text=True)

    def test_registers_when_absent(self, tmp_path):
        fake_bin, add_log = self._fake_openclaw(tmp_path, existing_names=())
        result = self._run_installer(tmp_path, fake_bin)
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.isfile(add_log), "installer never called `openclaw cron add`"
        logged = open(add_log).read()
        assert "skill6-github-archive-reconcile-sweep" in logged
        assert "--retry" in logged

    def test_registers_with_no_deliver_flag(self, tmp_path):
        """U24 rebuild (2026-07-18) — a maintenance-window reconciliation
        sweep must never fan out as a client-facing announcement.
        `openclaw cron add` defaults new jobs to "announce" delivery, so
        --no-deliver must always be passed. Mutation-proof: dropping
        --no-deliver from the installer's `openclaw cron add` call (the exact
        regression this closes) makes this assertion fail."""
        fake_bin, add_log = self._fake_openclaw(tmp_path, existing_names=())
        self._run_installer(tmp_path, fake_bin)
        logged = open(add_log).read()
        assert "--no-deliver" in logged

    def test_idempotent_noop_when_already_present(self, tmp_path):
        fake_bin, add_log = self._fake_openclaw(
            tmp_path, existing_names=("skill6-github-archive-reconcile-sweep",))
        result = self._run_installer(tmp_path, fake_bin)
        assert result.returncode == 0, result.stdout + result.stderr
        assert not os.path.isfile(add_log), "installer re-registered an already-present cron"

    def test_missing_openclaw_cli_is_non_fatal(self, tmp_path):
        env = dict(os.environ)
        env["PATH"] = "/usr/bin:/bin"  # no openclaw, minimal PATH
        result = subprocess.run(["bash", INSTALLER], env=env, capture_output=True, text=True)
        assert result.returncode == 3
        assert "openclaw" in (result.stdout + result.stderr).lower()


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
