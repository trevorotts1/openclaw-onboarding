"""Regression tests — Skill 6 maintenance-cron installers, findings 29 + 30
(oct-25 review), fully offline.

Two defects, one shape, four installers:

  29. install-routing-drift-check-cron.sh and
      install-selector-drift-probe-cron.sh registered jobs WITHOUT
      `--no-deliver`, so a newly installed maintenance tick announced into
      client chat (the archive/inventory installers already passed it). Fix:
      every `openclaw cron add` carries the flag, and an already-present job
      whose delivery mode is "announce" is validated and repaired in place
      with `openclaw cron edit <id> --no-deliver`.

  30. all four installers queried `openclaw cron list --json`, which HIDES
      DISABLED jobs (live box 2026-10-25: `--json` 17 jobs, `--all --json`
      55, 38 disabled). A reinstall therefore duplicated a job or resurrected
      one an operator deliberately disabled. Fix: every installer uses the
      shared helper (scripts/lib-cron-presence.sh) which queries
      `cron list --all --json` and treats a disabled match as a TOMBSTONE —
      report, change nothing, never re-enable.

Every behavioural assertion runs the REAL installer against a fake `openclaw`
on PATH: the stub hides disabled jobs from a bare `cron list`, shows them under
`--all`, and records every add/edit call. So these fail on the pre-fix
installers (they see "absent", add a duplicate, and never validate delivery)
and pass only when the fix is real. No live CLI, no cron store, no network.

Run:
    python3 -m pytest tests/test_skill6_cron_installers_full_visibility.py -v
"""
from __future__ import annotations

import json
import os
import re
import subprocess

import pytest

_SKILL_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_SCRIPTS = os.path.join(_SKILL_ROOT, "scripts")

# installer file -> schedule ENTRY file (its own source of truth for the name)
INSTALLERS = {
    "routing-drift": ("install-routing-drift-check-cron.sh",
                      "skill6-routing-drift-check.cron.json"),
    "selector-drift": ("install-selector-drift-probe-cron.sh",
                       "skill6-selector-drift-probe.cron.json"),
    "page-inventory": ("install-page-inventory-lifecycle-cron.sh",
                       "skill6-page-inventory-lifecycle.cron.json"),
    "github-archive": ("install-github-archive-reconcile-cron.sh",
                       "skill6-github-archive-reconcile-sweep.cron.json"),
}

_LABELS = list(INSTALLERS)


def _installer_path(label: str) -> str:
    return os.path.join(_SCRIPTS, INSTALLERS[label][0])


def _entry_name(label: str) -> str:
    entry = os.path.join(_SKILL_ROOT, "schedule", INSTALLERS[label][1])
    return json.load(open(entry))["name"]


def _collapsed_source(label: str) -> str:
    """Installer source with line continuations joined, so one logical
    `openclaw cron add ...` command is one string."""
    return open(_installer_path(label)).read().replace("\\\n", " ")


# ---------------------------------------------------------------------------
# Source contract — catches a revert even if the stub scenarios are skipped.
# ---------------------------------------------------------------------------

class TestSourceContract:
    @pytest.mark.parametrize("label", _LABELS)
    def test_presence_check_uses_shared_full_visibility_helper(self, label):
        src = _collapsed_source(label)
        assert "lib-cron-presence.sh" in src, (
            f"{INSTALLERS[label][0]} does not use the shared cron-presence helper")
        assert "_cron_state" in src, (
            f"{INSTALLERS[label][0]} does not call _cron_state")
        assert "cron list --json" not in src, (
            f"{INSTALLERS[label][0]} still queries the default `cron list --json` "
            "listing, which hides disabled jobs (finding 30)")

    @pytest.mark.parametrize("label", _LABELS)
    def test_every_cron_add_passes_no_deliver(self, label):
        # Command lines only — prose in comments may name `openclaw cron add`.
        adds = [line for line in _collapsed_source(label).splitlines()
                if re.match(r"\s*(?:if\s+)?openclaw cron add\b", line)]
        assert adds, f"{INSTALLERS[label][0]} has no `openclaw cron add` call"
        for line in adds:
            assert "--no-deliver" in line, (
                f"{INSTALLERS[label][0]} registers a maintenance job that can "
                f"announce into client chat (finding 29): {line.strip()}")

    def test_shared_helper_queries_all_and_reads_enabled(self):
        lib = open(os.path.join(_SCRIPTS, "lib-cron-presence.sh")).read()
        assert "cron list --all --json" in lib
        assert "enabled" in lib


# ---------------------------------------------------------------------------
# Behavioural — real installer, fake CLI.
# ---------------------------------------------------------------------------

class TestInstallerAgainstFakeCli:
    def _stub(self, tmp_path):
        """Fake openclaw: `cron list` without --all hides disabled jobs (live
        CLI behaviour); with --all shows everything. Records every call."""
        bin_dir = tmp_path / "fakebin"
        bin_dir.mkdir()
        state = tmp_path / "cron-state.json"
        log = tmp_path / "calls.log"
        script = bin_dir / "openclaw"
        script.write_text(
            "#!/usr/bin/env python3\n"
            "import json, sys\n"
            f"STATE = {str(state)!r}\n"
            f"LOG = {str(log)!r}\n"
            "args = sys.argv[1:]\n"
            "with open(LOG, 'a') as fh:\n"
            "    fh.write(' '.join(args) + '\\n')\n"
            "def load():\n"
            "    return json.load(open(STATE))\n"
            "def save(d):\n"
            "    json.dump(d, open(STATE, 'w'))\n"
            "if args[:2] == ['cron', 'list']:\n"
            "    jobs = load().get('jobs', [])\n"
            "    if '--all' not in args:\n"
            "        jobs = [j for j in jobs if j.get('enabled', True) is not False]\n"
            "    print(json.dumps({'jobs': jobs}))\n"
            "    sys.exit(0)\n"
            "if args[:2] == ['cron', 'add']:\n"
            "    name = args[args.index('--name') + 1] if '--name' in args else ''\n"
            "    d = load()\n"
            "    d.setdefault('jobs', []).append({\n"
            "        'id': 'job-new', 'name': name, 'enabled': True,\n"
            "        'delivery': {'mode': 'none' if '--no-deliver' in args else 'announce'},\n"
            "    })\n"
            "    save(d)\n"
            "    sys.exit(0)\n"
            "if args[:2] == ['cron', 'edit']:\n"
            "    d = load()\n"
            "    for j in d.get('jobs', []):\n"
            "        if j.get('id') == args[2] or j.get('name') == args[2]:\n"
            "            if '--no-deliver' in args:\n"
            "                j['delivery'] = {'mode': 'none'}\n"
            "            if '--enable' in args:\n"
            "                j['enabled'] = True\n"
            "            if '--disable' in args:\n"
            "                j['enabled'] = False\n"
            "    save(d)\n"
            "    sys.exit(0)\n"
            "sys.exit(1)\n"
        )
        script.chmod(0o755)
        return state, str(bin_dir), log

    def _seed(self, state, job):
        state.write_text(json.dumps({"jobs": [job] if job else []}))

    def _run(self, tmp_path, label, bin_dir):
        home = tmp_path / "home"
        home.mkdir(exist_ok=True)
        env = dict(os.environ)
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home)
        env["SKILL6_EVIDENCE_BASE"] = str(tmp_path / "evidence-base")
        env["SKILL6_ROUTING_DRIFT_CHECK_PROJECT_DIR"] = str(tmp_path / "drift-project")
        return subprocess.run(["bash", _installer_path(label)],
                              env=env, capture_output=True, text=True)

    def _calls(self, log, prefix):
        if not log.exists():
            return []
        return [ln for ln in log.read_text().splitlines() if ln.startswith(prefix)]

    @pytest.mark.parametrize("label", _LABELS)
    def test_disabled_job_is_a_tombstone_not_resurrected(self, tmp_path, label):
        """The exact finding-30 regression: a deliberately disabled job is
        invisible to the default listing, so a reinstall re-creates it."""
        state, bin_dir, log = self._stub(tmp_path)
        name = _entry_name(label)
        self._seed(state, {"id": "job-dis", "name": name, "enabled": False,
                           "delivery": {"mode": "none"}})

        result = self._run(tmp_path, label, bin_dir)

        assert result.returncode == 0, result.stdout + result.stderr
        assert not self._calls(log, "cron add"), (
            f"{INSTALLERS[label][0]} re-registered a DELIBERATELY DISABLED job "
            "(would stack a duplicate / resurrect it ENABLED)")
        assert not self._calls(log, "cron edit"), (
            f"{INSTALLERS[label][0]} edited a disabled (tombstoned) job")
        assert "DISABLED" in result.stdout
        assert json.load(open(state))["jobs"][0]["enabled"] is False, (
            "installer re-enabled a deliberately disabled schedule")

    @pytest.mark.parametrize("label", _LABELS)
    def test_absent_job_registers_silently(self, tmp_path, label):
        state, bin_dir, log = self._stub(tmp_path)
        self._seed(state, None)

        result = self._run(tmp_path, label, bin_dir)

        assert result.returncode == 0, result.stdout + result.stderr
        adds = self._calls(log, "cron add")
        assert len(adds) == 1, f"expected exactly one add, got: {adds}"
        assert "--no-deliver" in adds[0], (
            f"{INSTALLERS[label][0]} registered a job that can announce into "
            f"client chat (finding 29): {adds[0]}")
        assert _entry_name(label) in adds[0]

    @pytest.mark.parametrize("label", _LABELS)
    def test_existing_announce_delivery_is_repaired_in_place(self, tmp_path, label):
        """Finding 29: validate existing delivery configuration — an already
        installed job left on the "announce" default is repaired, not left
        free to message client chat."""
        state, bin_dir, log = self._stub(tmp_path)
        name = _entry_name(label)
        self._seed(state, {"id": "job-live", "name": name, "enabled": True,
                           "delivery": {"mode": "announce"}})

        result = self._run(tmp_path, label, bin_dir)

        assert result.returncode == 0, result.stdout + result.stderr
        assert not self._calls(log, "cron add"), "installer stacked a duplicate"
        edits = self._calls(log, "cron edit")
        assert any("--no-deliver" in e for e in edits), (
            f"{INSTALLERS[label][0]} left an existing announcing job alone "
            f"(finding 29); calls: {edits}")
        assert json.load(open(state))["jobs"][0]["delivery"]["mode"] == "none"

    @pytest.mark.parametrize("label", _LABELS)
    def test_enabled_silent_job_is_left_alone(self, tmp_path, label):
        state, bin_dir, log = self._stub(tmp_path)
        name = _entry_name(label)
        self._seed(state, {"id": "job-ok", "name": name, "enabled": True,
                           "delivery": {"mode": "none"}})

        result = self._run(tmp_path, label, bin_dir)

        assert result.returncode == 0, result.stdout + result.stderr
        assert not self._calls(log, "cron add"), "installer stacked a duplicate"
        assert not self._calls(log, "cron edit"), "installer edited a healthy job"


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
