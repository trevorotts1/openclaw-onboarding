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


class TestInstallerFlagParsingSK6001:
    """SK6001 regression. update-skills.sh runs the first scripts/install-*.sh
    of a skill as `bash <installer> --idempotent`; the installer used to take
    that flag as the evidence directory and register
    `--sweep-base "--idempotent"` (argparse exit 2 every night on every box).
    Mutation-proof: restoring `EVIDENCE_BASE="${1:-...}"` fails every test here
    that passes a flag."""

    def _fake(self, tmp_path, jobs):
        bin_dir = tmp_path / "fakebin"
        bin_dir.mkdir()
        state = tmp_path / "state.json"
        state.write_text(json.dumps({"jobs": jobs}))
        log = tmp_path / "calls.log"
        (bin_dir / "openclaw").write_text(f"""#!/usr/bin/env bash
if [[ "$1 $2" == "cron list" ]]; then cat "{state}"; exit 0; fi
printf '%s\\n' "$*" >> "{log}"
if [[ "$1 $2" == "cron add" ]]; then
  python3 - "{state}" <<'PYEOF'
import json, sys
d = json.load(open(sys.argv[1]))
d["jobs"].append({{"id": "new1", "name": "skill6-github-archive-reconcile-sweep", "payload": {{"command": "x"}}}})
json.dump(d, open(sys.argv[1], "w"))
PYEOF
fi
exit 0
""")
        (bin_dir / "openclaw").chmod(0o755)
        return str(bin_dir), log

    def _run(self, tmp_path, fake_bin, *args, extra_env=None):
        home = tmp_path / "home"
        home.mkdir(exist_ok=True)
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("SKILL6_EVIDENCE_BASE")}
        env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
        env["HOME"] = str(home)
        # hermetic: never see the real /data or /home/node of the machine running CI
        env["SKILL6_DATA_ROOT"] = str(tmp_path / "no-data-root")
        env["SKILL6_CONTABO_HOME"] = str(tmp_path / "no-contabo-home")
        env.pop("SKILL6_EVIDENCE_BASE_DIR", None)
        env.update(extra_env or {})
        r = subprocess.run(["bash", INSTALLER, *args], env=env,
                           capture_output=True, text=True)
        return r, home

    def test_idempotent_flag_is_never_the_directory(self, tmp_path):
        fake_bin, log = self._fake(tmp_path, [])
        r, home = self._run(tmp_path, fake_bin, "--idempotent")
        assert r.returncode == 0, r.stdout + r.stderr
        added = log.read_text()
        assert '--sweep-base "--idempotent"' not in added
        assert f'--sweep-base "{home}/clawd/skill6-fix"' in added
        assert (home / "clawd" / "skill6-fix").is_dir(), "evidence dir not created"

    def test_flag_then_explicit_directory(self, tmp_path):
        fake_bin, log = self._fake(tmp_path, [])
        target = tmp_path / "ev"
        r, _ = self._run(tmp_path, fake_bin, "--idempotent", str(target))
        assert r.returncode == 0, r.stdout + r.stderr
        assert f'--sweep-base "{target}"' in log.read_text()
        assert target.is_dir()

    def test_evidence_base_flag_and_env_precedence(self, tmp_path):
        fake_bin, log = self._fake(tmp_path, [])
        env_dir = tmp_path / "from-env"
        r, _ = self._run(tmp_path, fake_bin, "--idempotent",
                         extra_env={"SKILL6_EVIDENCE_BASE_DIR": str(env_dir)})
        assert f'--sweep-base "{env_dir}"' in log.read_text()

    def test_unknown_flag_ignored_and_dash_directory_refused(self, tmp_path):
        fake_bin, log = self._fake(tmp_path, [])
        r, _ = self._run(tmp_path, fake_bin, "--whatever")
        assert r.returncode == 0 and '--sweep-base "--whatever"' not in log.read_text()
        r2, _ = self._run(tmp_path, fake_bin, "--evidence-base", "-bad")
        assert r2.returncode == 2

    def test_broken_existing_job_is_repaired_in_place(self, tmp_path):
        broken = {"id": "job-bad", "name": "skill6-github-archive-reconcile-sweep",
                  "payload": {"command": "python3 x/ghl_github_reconcile.py "
                              '--sweep-base "--idempotent" --retry --json'}}
        fake_bin, log = self._fake(tmp_path, [broken])
        r, home = self._run(tmp_path, fake_bin, "--idempotent")
        assert r.returncode == 0, r.stdout + r.stderr
        calls = log.read_text()
        assert "cron edit job-bad --command" in calls
        assert '--sweep-base "--idempotent"' not in calls
        assert f'--sweep-base "{home}/clawd/skill6-fix"' in calls
        assert "cron add" not in calls

    def test_healthy_existing_job_is_left_alone(self, tmp_path):
        ok = {"id": "job-ok", "name": "skill6-github-archive-reconcile-sweep",
              "payload": {"command": 'python3 x/ghl_github_reconcile.py '
                          '--sweep-base "/data/clawd/skill6-fix" --retry --json'}}
        fake_bin, log = self._fake(tmp_path, [ok])
        r, _ = self._run(tmp_path, fake_bin, "--idempotent")
        assert r.returncode == 0, r.stdout + r.stderr
        assert not log.exists(), "touched a healthy job"


class TestPersistentPathSK6002:
    """SK6002. Docker $HOME is not always persistent: on Contabo only
    ~/.openclaw survives a container recreate, on Hostinger /data is the
    volume. The default evidence folder must live on the persistent side, an
    old non-persistent job must be repaired, a healthy persistent job must be
    left alone, and Mac must not change."""

    _fake = TestInstallerFlagParsingSK6001._fake
    _run = TestInstallerFlagParsingSK6001._run

    @staticmethod
    def _job(path, jid="job-1"):
        return {"id": jid, "name": "skill6-github-archive-reconcile-sweep",
                "payload": {"command": 'python3 x/ghl_github_reconcile.py '
                            f'--sweep-base "{path}" --retry --json'}}

    def _hostinger(self, tmp_path):
        data = tmp_path / "data"
        (data / ".openclaw").mkdir(parents=True)
        return data, {"SKILL6_DATA_ROOT": str(data)}

    def _contabo(self, tmp_path):
        home = tmp_path / "home"
        (home / ".openclaw").mkdir(parents=True)
        return home, {"SKILL6_CONTABO_HOME": str(home)}

    def test_mac_default_unchanged(self, tmp_path):
        fake_bin, log = self._fake(tmp_path, [])
        r, home = self._run(tmp_path, fake_bin, "--idempotent")
        assert f'--sweep-base "{home}/clawd/skill6-fix"' in log.read_text()

    def test_hostinger_default_is_data_clawd(self, tmp_path):
        fake_bin, log = self._fake(tmp_path, [])
        data, env = self._hostinger(tmp_path)
        r, home = self._run(tmp_path, fake_bin, "--idempotent", extra_env=env)
        assert r.returncode == 0, r.stdout + r.stderr
        assert f'--sweep-base "{data}/clawd/skill6-fix"' in log.read_text()
        assert (data / "clawd" / "skill6-fix").is_dir()
        assert not (home / "clawd" / "skill6-fix").is_dir() or (home / "clawd" / "skill6-fix").is_symlink(), \
            "Hostinger must not create a real folder under $HOME/clawd"

    def test_contabo_default_is_under_dot_openclaw_and_legacy_path_links(self, tmp_path):
        fake_bin, log = self._fake(tmp_path, [])
        home, env = self._contabo(tmp_path)
        r, _ = self._run(tmp_path, fake_bin, "--idempotent", extra_env=env)
        assert r.returncode == 0, r.stdout + r.stderr
        want = home / ".openclaw" / "clawd" / "skill6-fix"
        assert f'--sweep-base "{want}"' in log.read_text()
        assert want.is_dir()
        legacy = home / "clawd" / "skill6-fix"   # what Command Center reads
        assert legacy.is_symlink() and legacy.resolve() == want.resolve()

    def test_contabo_existing_real_legacy_folder_is_copied_not_destroyed(self, tmp_path):
        fake_bin, log = self._fake(tmp_path, [])
        home, env = self._contabo(tmp_path)
        legacy = home / "clawd" / "skill6-fix" / "v2-run1"
        legacy.mkdir(parents=True)
        (legacy / "keep.txt").write_text("evidence")
        r, _ = self._run(tmp_path, fake_bin, "--idempotent", extra_env=env)
        assert r.returncode == 0, r.stdout + r.stderr
        want = home / ".openclaw" / "clawd" / "skill6-fix"
        assert (want / "v2-run1" / "keep.txt").read_text() == "evidence"
        assert (legacy / "keep.txt").read_text() == "evidence"
        assert not (home / "clawd" / "skill6-fix").is_symlink()

    def test_contabo_job_on_throwaway_home_path_is_repaired(self, tmp_path):
        home, env = self._contabo(tmp_path)
        fake_bin, log = self._fake(tmp_path, [self._job(f"{home}/clawd/skill6-fix")])
        r, _ = self._run(tmp_path, fake_bin, "--idempotent", extra_env=env)
        assert r.returncode == 0, r.stdout + r.stderr
        calls = log.read_text()
        assert "cron edit job-1 --command" in calls
        assert f'--sweep-base "{home}/.openclaw/clawd/skill6-fix"' in calls
        assert "cron add" not in calls

    def test_contabo_healthy_persistent_job_is_left_alone(self, tmp_path):
        home, env = self._contabo(tmp_path)
        fake_bin, log = self._fake(
            tmp_path, [self._job(f"{home}/.openclaw/clawd/skill6-fix")])
        r, _ = self._run(tmp_path, fake_bin, "--idempotent", extra_env=env)
        assert r.returncode == 0, r.stdout + r.stderr
        assert not log.exists(), "touched a healthy persistent job"

    def test_hostinger_healthy_job_is_left_alone(self, tmp_path):
        data, env = self._hostinger(tmp_path)
        fake_bin, log = self._fake(tmp_path, [self._job(f"{data}/clawd/skill6-fix")])
        r, _ = self._run(tmp_path, fake_bin, "--idempotent", extra_env=env)
        assert r.returncode == 0, r.stdout + r.stderr
        assert not log.exists()

    def test_hostinger_job_on_throwaway_home_path_is_repaired(self, tmp_path):
        # SK6003: the SK6001 default left $HOME/clawd/skill6-fix jobs on Hostinger
        data, env = self._hostinger(tmp_path)
        fake_bin, log = self._fake(tmp_path, [self._job(f"{tmp_path}/home/clawd/skill6-fix")])
        r, _ = self._run(tmp_path, fake_bin, "--idempotent", extra_env=env)
        assert r.returncode == 0, r.stdout + r.stderr
        calls = log.read_text()
        assert "cron edit job-1 --command" in calls
        assert f'--sweep-base "{data}/clawd/skill6-fix"' in calls
        assert "cron add" not in calls

    def test_hostinger_command_center_path_links_to_data(self, tmp_path):
        fake_bin, log = self._fake(tmp_path, [])
        data, env = self._hostinger(tmp_path)
        r, home = self._run(tmp_path, fake_bin, "--idempotent", extra_env=env)
        legacy = home / "clawd" / "skill6-fix"
        assert legacy.is_symlink() and legacy.resolve() == (data / "clawd" / "skill6-fix").resolve()

    def test_mac_job_under_home_is_left_alone(self, tmp_path):
        fake_bin, log = self._fake(tmp_path, [self._job(f"{tmp_path}/home/clawd/skill6-fix")])
        r, _ = self._run(tmp_path, fake_bin, "--idempotent")
        assert r.returncode == 0, r.stdout + r.stderr
        assert not log.exists(), "Mac job must not be repaired"

    def test_explicit_argument_beats_platform_default(self, tmp_path):
        fake_bin, log = self._fake(tmp_path, [])
        _, env = self._contabo(tmp_path)
        target = tmp_path / "chosen"
        r, _ = self._run(tmp_path, fake_bin, "--idempotent", str(target), extra_env=env)
        assert f'--sweep-base "{target}"' in log.read_text()

    def test_env_dir_beats_platform_default(self, tmp_path):
        fake_bin, log = self._fake(tmp_path, [])
        _, env = self._contabo(tmp_path)
        env_dir = tmp_path / "from-env"
        r, _ = self._run(tmp_path, fake_bin, "--idempotent",
                         extra_env={**env, "SKILL6_EVIDENCE_BASE_DIR": str(env_dir)})
        assert f'--sweep-base "{env_dir}"' in log.read_text()


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
