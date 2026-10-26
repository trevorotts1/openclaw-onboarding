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

The QC layer also pins the NEGATIVE paths, because a maintenance installer
that reports success it did not verify is the bug class under repair:
unreadable/garbage listings never register, a failed add is never DONE, a
`--no-deliver` the CLI silently drops is repaired (or FAILed) instead of
blessed, duplicate names stop the installer, and an auto-disabled job
(`enabled:false` + `state.autoDisabled`, the live shape) is a tombstone.

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
        assert "--enable" not in src, (
            f"{INSTALLERS[label][0]} can re-enable a job — a tombstone is never "
            "resurrected by an installer (finding 30)")

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
        assert 'job.get("enabled") is False' in lib, (
            "helper no longer detects the disabled (tombstone) shape the live "
            "CLI emits (enabled:false, also the auto-disabled shape)")
        assert "sys.exit(2)" in lib, (
            "helper lost its UNKNOWN return path (D10: a failed/unparsable or "
            "ambiguous listing must never read as absent)")


# ---------------------------------------------------------------------------
# Behavioural — real installer, fake CLI.
# ---------------------------------------------------------------------------

class TestInstallerAgainstFakeCli:
    def _stub(self, tmp_path):
        """Fake openclaw: `cron list` without --all hides disabled jobs (live
        CLI behaviour); with --all shows everything. Records every call.
        OC_FAKE_MODE injects failure: list-fails, list-garbage, add-fails,
        ignore-add-flag (add drops --no-deliver), ignore-both-flags (add AND
        edit drop it)."""
        bin_dir = tmp_path / "fakebin"
        bin_dir.mkdir()
        state = tmp_path / "cron-state.json"
        log = tmp_path / "calls.log"
        script = bin_dir / "openclaw"
        script.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            f"STATE = {str(state)!r}\n"
            f"LOG = {str(log)!r}\n"
            "MODE = os.environ.get('OC_FAKE_MODE', '')\n"
            "args = sys.argv[1:]\n"
            "with open(LOG, 'a') as fh:\n"
            "    fh.write(' '.join(args) + '\\n')\n"
            "def load():\n"
            "    return json.load(open(STATE))\n"
            "def save(d):\n"
            "    json.dump(d, open(STATE, 'w'))\n"
            "if args[:2] == ['cron', 'list']:\n"
            "    if MODE == 'list-fails':\n"
            "        sys.stderr.write('gateway not reachable\\n')\n"
            "        sys.exit(1)\n"
            "    if MODE == 'list-garbage':\n"
            "        print('Gateway is starting, please retry shortly...')\n"
            "        sys.exit(0)\n"
            "    jobs = load().get('jobs', [])\n"
            "    if '--all' not in args:\n"
            "        jobs = [j for j in jobs if j.get('enabled', True) is not False]\n"
            "    print(json.dumps({'jobs': jobs}))\n"
            "    sys.exit(0)\n"
            "if args[:2] == ['cron', 'add']:\n"
            "    if MODE == 'add-fails':\n"
            "        sys.exit(1)\n"
            "    name = args[args.index('--name') + 1] if '--name' in args else ''\n"
            "    d = load()\n"
            "    silent = ('--no-deliver' in args\n"
            "              and MODE not in ('ignore-add-flag', 'ignore-both-flags'))\n"
            "    d.setdefault('jobs', []).append({\n"
            "        'id': 'job-new', 'name': name, 'enabled': True,\n"
            "        'delivery': {'mode': 'none' if silent else 'announce'},\n"
            "    })\n"
            "    save(d)\n"
            "    sys.exit(0)\n"
            "if args[:2] == ['cron', 'edit']:\n"
            "    d = load()\n"
            "    for j in d.get('jobs', []):\n"
            "        if j.get('id') == args[2] or j.get('name') == args[2]:\n"
            "            if '--no-deliver' in args and MODE != 'ignore-both-flags':\n"
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

    def _run(self, tmp_path, label, bin_dir, mode="", evidence_base=None):
        # Spaced HOME on purpose: the SK6001/2 staleness scan must survive
        # paths containing spaces (the mandated TMPDIR has them).
        home = tmp_path / "home dir"
        home.mkdir(exist_ok=True)
        env = dict(os.environ)
        env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
        env["HOME"] = str(home)
        env["OC_FAKE_MODE"] = mode
        env["SKILL6_EVIDENCE_BASE"] = str(evidence_base or (tmp_path / "evidence-base"))
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
    def test_auto_disabled_job_is_a_tombstone(self, tmp_path, label):
        """The live shape a job gets when the CLI auto-disables it after
        consecutive failures (verified on the operator box 2026-10-25:
        `enabled: false` plus a `state.autoDisabled` record). Same rule as a
        deliberate tombstone — never resurrected by an installer."""
        state, bin_dir, log = self._stub(tmp_path)
        name = _entry_name(label)
        self._seed(state, {"id": "job-auto", "name": name, "enabled": False,
                           "state": {"autoDisabled": {"reason": "consecutive-failures",
                                                     "atMs": 1789272004180}},
                           "delivery": {"mode": "none"}})

        result = self._run(tmp_path, label, bin_dir)

        assert result.returncode == 0, result.stdout + result.stderr
        assert not self._calls(log, "cron add"), "resurrected an auto-disabled job"
        assert not self._calls(log, "cron edit"), "edited an auto-disabled job"
        assert "DISABLED" in result.stdout

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
        assert json.load(open(state))["jobs"][0]["delivery"]["mode"] == "none", (
            "the registered job reads back announcing")

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

    # -- negative paths: no false success, ever ------------------------------

    @pytest.mark.parametrize("label", _LABELS)
    @pytest.mark.parametrize("mode", ["list-fails", "list-garbage"])
    def test_unreadable_listing_never_registers(self, tmp_path, label, mode):
        """D10 contract: a failed or non-JSON `cron list` is UNKNOWN, never
        "absent" — registering on it stacks duplicates."""
        state, bin_dir, log = self._stub(tmp_path)
        self._seed(state, None)

        result = self._run(tmp_path, label, bin_dir, mode=mode)

        assert result.returncode == 3, result.stdout + result.stderr
        assert not self._calls(log, "cron add"), (
            f"{INSTALLERS[label][0]} registered on an unreadable listing ({mode})")
        assert "FAIL" in result.stdout

    @pytest.mark.parametrize("label", _LABELS)
    def test_add_failure_is_reported_not_done(self, tmp_path, label):
        state, bin_dir, log = self._stub(tmp_path)
        self._seed(state, None)

        result = self._run(tmp_path, label, bin_dir, mode="add-fails")

        assert result.returncode == 3, result.stdout + result.stderr
        assert len(self._calls(log, "cron add")) == 1
        assert "FAIL" in result.stdout
        assert "DONE" not in result.stdout, "DONE logged after a failed add"
        assert json.load(open(state))["jobs"] == []

    @pytest.mark.parametrize("label", _LABELS)
    def test_add_that_ignores_no_deliver_is_repaired_before_done(self, tmp_path, label):
        """A CLI that accepts `--no-deliver` and silently drops it (the
        silent-no-op class) must not get a green install: the fresh job has
        to read back silent, repaired in place if not."""
        state, bin_dir, log = self._stub(tmp_path)
        self._seed(state, None)

        result = self._run(tmp_path, label, bin_dir, mode="ignore-add-flag")

        assert result.returncode == 0, result.stdout + result.stderr
        edits = self._calls(log, "cron edit")
        assert any("--no-deliver" in e for e in edits), (
            f"announcing fresh job never repaired; calls: {edits}")
        assert json.load(open(state))["jobs"][0]["delivery"]["mode"] == "none"

    @pytest.mark.parametrize("label", _LABELS)
    def test_unfixable_announcing_job_is_never_reported_done(self, tmp_path, label):
        """When neither add nor edit honours `--no-deliver`, the installer
        must FAIL (3), never DONE — the job would announce into client chat."""
        state, bin_dir, log = self._stub(tmp_path)
        self._seed(state, None)

        result = self._run(tmp_path, label, bin_dir, mode="ignore-both-flags")

        assert result.returncode == 3, result.stdout + result.stderr
        assert "FAIL" in result.stdout
        assert "DONE" not in result.stdout, (
            "DONE logged while the registered job still announces")
        assert json.load(open(state))["jobs"][0]["delivery"]["mode"] == "announce", (
            "test premise broken: stub should still be announcing")

    @pytest.mark.parametrize("label", _LABELS)
    def test_duplicate_names_stop_installer_without_touching_anything(
            self, tmp_path, label):
        """Pre-fix reinstallers stacked duplicates. With two same-named jobs
        (a tombstone and an enabled announcer) first-match-wins would report
        OK while the twin announces — the installer must refuse to guess."""
        state, bin_dir, log = self._stub(tmp_path)
        name = _entry_name(label)
        state.write_text(json.dumps({"jobs": [
            {"id": "job-a", "name": name, "enabled": False,
             "delivery": {"mode": "none"}},
            {"id": "job-b", "name": name, "enabled": True,
             "delivery": {"mode": "announce"}},
        ]}))

        result = self._run(tmp_path, label, bin_dir)

        assert result.returncode == 3, result.stdout + result.stderr
        assert "FAIL" in result.stdout
        assert not self._calls(log, "cron add"), "added on ambiguous (duplicate) names"
        assert not self._calls(log, "cron edit"), "edited with ambiguous (duplicate) names"

    # -- archive installer: the SK6001/2 in-place repair path ----------------

    def test_archive_broken_job_repair_is_verified_before_done(self, tmp_path):
        """The repair path used to claim "delivery silent" from the edit's rc
        alone. With a CLI that drops --no-deliver on edit too, the repair must
        FAIL instead of blessing an announcing job."""
        state, bin_dir, log = self._stub(tmp_path)
        self._seed(state, {"id": "job-broken", "name": _entry_name("github-archive"),
                           "enabled": True, "delivery": {"mode": "announce"},
                           "payload": {"kind": "command", "argv": [
                               "sh", "-lc",
                               "python3 reconcile.py --sweep-base --idempotent"]}})

        result = self._run(tmp_path, "github-archive", bin_dir,
                           mode="ignore-both-flags")

        assert result.returncode == 3, result.stdout + result.stderr
        assert "FAIL" in result.stdout
        assert "DONE" not in result.stdout, (
            "DONE logged while the repaired job still announces")
        assert self._calls(log, "cron edit"), "the broken job was never repaired at all"
        assert json.load(open(state))["jobs"][0]["delivery"]["mode"] == "announce"

    def test_archive_broken_job_repair_reads_back_silent(self, tmp_path):
        state, bin_dir, log = self._stub(tmp_path)
        self._seed(state, {"id": "job-broken", "name": _entry_name("github-archive"),
                           "enabled": True, "delivery": {"mode": "announce"},
                           "payload": {"kind": "command", "argv": [
                               "sh", "-lc",
                               "python3 reconcile.py --sweep-base --idempotent"]}})

        result = self._run(tmp_path, "github-archive", bin_dir)

        assert result.returncode == 0, result.stdout + result.stderr
        assert not self._calls(log, "cron add"), "installer stacked a duplicate"
        assert json.load(open(state))["jobs"][0]["delivery"]["mode"] == "none"

    def test_archive_sweep_base_path_with_spaces_is_still_repaired(self, tmp_path):
        """The staleness scan used `\\S*` after --sweep-base, which truncates
        a quoted path at its first space and silently skips the repair
        (false OK) — the two SK6002 suite failures under the space-containing
        TMPDIR. A stale spaced --sweep-base must still be detected."""
        state, bin_dir, log = self._stub(tmp_path)
        home = tmp_path / "home dir"
        want = home / ".openclaw" / "clawd" / "skill6-fix"
        self._seed(state, {"id": "job-sp", "name": _entry_name("github-archive"),
                           "enabled": True, "delivery": {"mode": "none"},
                           "payload": {"command":
                               f'python3 x.py --sweep-base "{home}/clawd/skill6-fix" '
                               "--retry"}})

        result = self._run(tmp_path, "github-archive", bin_dir, evidence_base=want)

        assert result.returncode == 0, result.stdout + result.stderr
        edits = self._calls(log, "cron edit job-sp")
        assert edits, (
            "stale --sweep-base with a spaced path was never detected/repaired")
        assert str(want) in edits[0], f"repair did not use the persistent path: {edits}"
        assert not self._calls(log, "cron add"), "installer stacked a duplicate"


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
