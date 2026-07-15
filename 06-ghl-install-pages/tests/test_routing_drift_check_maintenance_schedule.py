"""MOCK-only unit tests — U23/B-U9 the monthly maintenance-window schedule
ENTRY for the routing-drift live proof.

B-U9 acceptance (d): "the monthly operator-box live proof writes a dated
receipt with render_check PASS." The CODE-MERGE gate for this offline unit
build proves the SCHEDULE ENTRY exists and correctly names the
routing-drift-check tool (asserted by name/well-formedness); actually
firing it live and confirming the first dated receipt is DEFERRED TO U22 —
the same per-repo/offline acceptance doctrine already used for
schedule/skill6-github-archive-reconcile-sweep.cron.json (U24/B-U10, see
tests/test_github_archive_maintenance_schedule.py, whose pattern this file
mirrors).

Two things are proven here, fully offline:
  1. The schedule ENTRY FILE exists at a known, named path, is well-formed,
     and its command genuinely invokes ghl_routing_drift_check.py (not a
     stale/mismatched command drifted out of sync with the file's own
     schedule/tz fields).
  2. scripts/install-routing-drift-check-cron.sh — the installer that would
     register this entry live (the LIVE-PROOF leg, deferred to U22) — reads
     that SAME file (single source of truth) and behaves idempotently
     against a FAKE `openclaw` CLI shim on PATH (no live tool call, no
     network).

No real client/operator names, ids, emails, or location-ids appear.

Run:
    python3 -m pytest tests/test_routing_drift_check_maintenance_schedule.py -v
"""
from __future__ import annotations

import json
import os
import stat
import subprocess

import pytest

_SKILL_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
ENTRY_FILE = os.path.join(_SKILL_ROOT, "schedule",
                           "skill6-routing-drift-check.cron.json")
INSTALLER = os.path.join(_SKILL_ROOT, "scripts", "install-routing-drift-check-cron.sh")
TOOL_FILE = os.path.join(_SKILL_ROOT, "tools", "ghl_routing_drift_check.py")


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
        assert data["name"] == "skill6-routing-drift-check"

    def test_scheduled_command_invokes_the_routing_drift_check_tool(self):
        """The literal acceptance intent: the scheduled command is the
        routing-drift-check tool, with both required args templated."""
        with open(ENTRY_FILE) as fh:
            data = json.load(fh)
        command = data["command"]
        assert "ghl_routing_drift_check.py" in command
        assert "--evidence-root" in command
        assert "--project-dir" in command

    def test_the_referenced_tool_file_actually_exists(self):
        """The schedule entry must not point at a tool that was never
        built."""
        assert os.path.isfile(TOOL_FILE), (
            f"schedule entry references tools/ghl_routing_drift_check.py "
            f"but it does not exist at {TOOL_FILE}"
        )

    def test_schedule_field_is_a_valid_five_field_cron_expression(self):
        with open(ENTRY_FILE) as fh:
            data = json.load(fh)
        fields = data["schedule"].split()
        assert len(fields) == 5, f"expected a 5-field cron expression, got: {data['schedule']!r}"

    def test_schedule_is_monthly_not_daily(self):
        """B-U9 explicitly calls for a MONTHLY proof (unlike B-U10's daily
        reconcile sweep) -- the day-of-month field must be pinned, not '*'."""
        with open(ENTRY_FILE) as fh:
            data = json.load(fh)
        day_of_month_field = data["schedule"].split()[2]
        assert day_of_month_field != "*", (
            "routing-drift-check must be scheduled MONTHLY (a pinned "
            "day-of-month), not '*' (which would make it daily)"
        )

    def test_installer_script_exists_and_is_executable(self):
        assert os.path.isfile(INSTALLER), f"installer missing: {INSTALLER}"
        mode = os.stat(INSTALLER).st_mode
        assert mode & stat.S_IXUSR, "installer must be executable (chmod +x)"


class TestInstallerAgainstFakeOpenclawCli:
    """Exercises the installer end-to-end against a FAKE `openclaw` shim on
    PATH — no live tool call, no network. Proves: (a) absent -> registers by
    reading the schedule entry's own name/schedule/tz/command, (b) present ->
    idempotent no-op, (c) never invents a name/command different from the
    shipped entry file."""

    def _fake_openclaw(self, tmp_path, *, existing_names=()):
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
  python3 - "$STATE" <<'PYEOF'
import json, sys
path = sys.argv[1]
with open(path) as fh:
    data = json.load(fh)
data.setdefault("jobs", []).append({{"name": "skill6-routing-drift-check"}})
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
        env["SKILL6_ROUTING_DRIFT_CHECK_PROJECT_DIR"] = str(tmp_path / "drift-project")
        return subprocess.run(["bash", INSTALLER], env=env, capture_output=True, text=True)

    def test_registers_when_absent(self, tmp_path):
        fake_bin, add_log = self._fake_openclaw(tmp_path, existing_names=())
        result = self._run_installer(tmp_path, fake_bin)
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.isfile(add_log), "installer never called `openclaw cron add`"
        logged = open(add_log).read()
        assert "skill6-routing-drift-check" in logged
        assert "ghl_routing_drift_check.py" in logged

    def test_registered_command_carries_substituted_paths(self, tmp_path):
        fake_bin, add_log = self._fake_openclaw(tmp_path, existing_names=())
        self._run_installer(tmp_path, fake_bin)
        logged = open(add_log).read()
        assert str(tmp_path / "evidence-base") in logged
        assert str(tmp_path / "drift-project") in logged
        # The raw ${...} template placeholders must never leak through unsubstituted.
        assert "${SKILL6_EVIDENCE_BASE}" not in logged
        assert "${SKILL6_ROUTING_DRIFT_CHECK_PROJECT_DIR}" not in logged

    def test_idempotent_noop_when_already_present(self, tmp_path):
        fake_bin, add_log = self._fake_openclaw(
            tmp_path, existing_names=("skill6-routing-drift-check",))
        result = self._run_installer(tmp_path, fake_bin)
        assert result.returncode == 0, result.stdout + result.stderr
        assert not os.path.isfile(add_log), "installer re-registered an already-present cron"

    def test_missing_openclaw_cli_is_non_fatal(self, tmp_path):
        env = dict(os.environ)
        env["PATH"] = "/usr/bin:/bin"  # no openclaw, minimal PATH
        result = subprocess.run(["bash", INSTALLER], env=env, capture_output=True, text=True)
        assert result.returncode == 3
        assert "openclaw" in (result.stdout + result.stderr).lower()

    def test_positional_args_override_env_vars(self, tmp_path):
        fake_bin, add_log = self._fake_openclaw(tmp_path, existing_names=())
        env = dict(os.environ)
        env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
        positional_evidence = str(tmp_path / "positional-evidence")
        positional_project = str(tmp_path / "positional-project")
        result = subprocess.run(
            ["bash", INSTALLER, positional_evidence, positional_project],
            env=env, capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        logged = open(add_log).read()
        assert positional_evidence in logged
        assert positional_project in logged


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
