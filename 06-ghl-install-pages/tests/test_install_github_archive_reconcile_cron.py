"""tests/test_install_github_archive_reconcile_cron.py — U24/B-U10 item 2.

Proves ``scripts/install-github-archive-reconcile-cron.sh`` actually builds a
WORKING ``openclaw cron add`` invocation, by stubbing ``openclaw`` on PATH and
asserting the EXACT argv the installer produces — the same class of bug this
unit exists to fix: the PRIOR build's SKILL.md snippet used a flag
(``--schedule``) that does not exist on the real CLI and omitted
``--no-deliver``, and nothing caught either mistake before it reached an
operator's box. `openclaw cron add --help` (this repo, this box) is the
ground truth for which flags are real; this suite pins the installer against
a fabricated help text so a future CLI rename is caught here, not at 4am.

No live cron is created by these tests — the stub records argv to a log file
and never touches the real Gateway.

Run:
    python3 -m pytest tests/test_install_github_archive_reconcile_cron.py -v
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SKILL_DIR = os.path.normpath(os.path.join(_HERE, ".."))
INSTALLER = os.path.join(_SKILL_DIR, "scripts", "install-github-archive-reconcile-cron.sh")

_STUB_TEMPLATE = r"""#!/usr/bin/env bash
# Fake `openclaw` — records `cron add` invocations, never touches a real Gateway.
LOGFILE="$STUB_LOG"
MARKER="$STUB_MARKER"

if [[ "$1" == "cron" && "$2" == "list" ]]; then
  if [[ -f "$MARKER" ]]; then
    echo "id  {cron_name}  cron 0 4 * * * (exact)  ok"
  fi
  exit 0
fi

if [[ "$1" == "cron" && "$2" == "add" && "$3" == "--help" ]]; then
{help_body}
  exit 0
fi

if [[ "$1" == "cron" && "$2" == "add" ]]; then
  # Log the REAL argv (not a space-joined $* string, which loses quote
  # boundaries and would make a --command-argv JSON payload unparseable) as
  # one JSON array per line.
  python3 -c 'import json,sys; print(json.dumps(sys.argv[1:]))' "$@" >> "$LOGFILE"
  touch "$MARKER"
  echo '{{"uuid":"fake-uuid-123"}}'
  exit 0
fi

echo "unstubbed openclaw invocation: $*" >&2
exit 9
"""

_HELP_WITH_NO_DELIVER = """  cat <<'HELPEOF'
Options:
  --name <name>          Job name
  --cron <expr>           Cron expression
  --tz <iana>             Timezone
  --session <target>      Session target
  --command-argv <json>   Command payload argv as JSON array of strings
  --no-deliver            Disable runner fallback delivery
  --json                  Output JSON
HELPEOF"""

_HELP_WITHOUT_NO_DELIVER = """  cat <<'HELPEOF'
Options:
  --name <name>          Job name
  --cron <expr>           Cron expression
  --tz <iana>             Timezone
  --session <target>      Session target
  --command-argv <json>   Command payload argv as JSON array of strings
  --json                  Output JSON
HELPEOF"""

CRON_NAME = "skill6-github-archive-reconcile-sweep"


def _make_stub(tmp_path, *, help_body: str) -> tuple[str, str, str]:
    """Write the fake `openclaw` to a tmp dir and return (bin_dir, log, marker)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub_path = bin_dir / "openclaw"
    stub_path.write_text(_STUB_TEMPLATE.format(cron_name=CRON_NAME, help_body=help_body))
    st = os.stat(stub_path)
    os.chmod(stub_path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    log = tmp_path / "cron-add-calls.log"
    marker = tmp_path / "created.marker"
    return str(bin_dir), str(log), str(marker)


def _run_installer(tmp_path, *, help_body: str, real_tools_dir: bool = True):
    bin_dir, log, marker = _make_stub(tmp_path, help_body=help_body)
    env = dict(os.environ)
    env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
    env["STUB_LOG"] = log
    env["STUB_MARKER"] = marker
    # Run the installer FROM a copy of the real scripts/tools layout so its
    # own-dir-first resolution finds the real ghl_github_reconcile.py (proves
    # the installer targets the actual shipped tool, not a fabricated path).
    proc = subprocess.run(
        ["bash", INSTALLER], env=env, cwd=_SKILL_DIR,
        capture_output=True, text=True, timeout=15,
    )
    calls = []
    if os.path.isfile(log):
        with open(log) as fh:
            calls = [json.loads(line) for line in fh if line.strip()]
    return proc, calls


class TestInstallerBuildsCorrectArgv:
    def test_installer_is_syntactically_valid_bash(self):
        proc = subprocess.run(["bash", "-n", INSTALLER], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr

    def test_uses_real_cron_flag_not_schedule(self, tmp_path):
        """The regression this unit exists to fix: `--schedule` is not a real
        OpenClaw CLI flag (the real one is `--cron`). Proof this assertion is
        live, not a tautology: swap INSTALLER for the ORIGINAL SKILL.md-only
        (undocumented-as-script) approach and there is no argv to inspect at
        all — this test would fail to find ANY logged call, which is exactly
        what happened before this unit shipped a real installer."""
        proc, calls = _run_installer(tmp_path, help_body=_HELP_WITH_NO_DELIVER)
        assert proc.returncode == 0, proc.stderr
        assert len(calls) == 1, f"expected exactly one cron-add call, got: {calls}"
        argv = calls[0]
        assert "--cron" in argv, argv
        assert "--schedule" not in argv, "the fake CLI flag this unit exists to stop shipping"

    def test_passes_no_deliver_when_cli_advertises_it(self, tmp_path):
        """Fleet doctrine: 'cron add → delivery=announce unless --no-deliver
        is passed' — operator-verbose, never client. Proof: assert the flag
        is actually IN the logged argv, not merely documented in a comment."""
        proc, calls = _run_installer(tmp_path, help_body=_HELP_WITH_NO_DELIVER)
        assert proc.returncode == 0, proc.stderr
        assert "--no-deliver" in calls[0], calls[0]

    def test_command_argv_uses_bare_sweep_base_no_hardcoded_evidence_path(self, tmp_path):
        """The installer must never bake a specific operator's evidence-base
        directory into the cron's argv — `--sweep-base` bare lets
        ghl_github_reconcile.py auto-resolve it per-box at RUN time (env
        override or $HOME/clawd/skill6-fix), so the same installer script
        works unmodified on every fleet box."""
        proc, calls = _run_installer(tmp_path, help_body=_HELP_WITH_NO_DELIVER)
        assert proc.returncode == 0, proc.stderr
        argv = calls[0]
        assert "--command-argv" in argv
        payload_json = argv[argv.index("--command-argv") + 1]
        payload = json.loads(payload_json)
        assert payload[0] == "sh" and payload[1] == "-lc"
        inner_cmd = payload[2]
        assert "ghl_github_reconcile.py" in inner_cmd
        assert "--sweep-base" in inner_cmd
        assert "--retry" in inner_cmd
        # Bare --sweep-base: nothing but a flag/space/flag follows it — no
        # hardcoded directory argument.
        after = inner_cmd.split("--sweep-base", 1)[1].strip()
        assert after.startswith("--"), f"--sweep-base must be bare (no hardcoded dir), got trailing: {after!r}"

    def test_warns_but_still_creates_when_cli_predates_no_deliver(self, tmp_path):
        """A stale CLI without --no-deliver must never block installation
        (plumbing, not a build gate) — it degrades to a printed warning."""
        proc, calls = _run_installer(tmp_path, help_body=_HELP_WITHOUT_NO_DELIVER)
        assert proc.returncode == 0, proc.stderr
        assert "WARNING" in proc.stdout or "WARNING" in proc.stderr
        assert len(calls) == 1
        assert "--no-deliver" not in calls[0]

    def test_idempotent_second_run_skips(self, tmp_path):
        bin_dir, log, marker = _make_stub(tmp_path, help_body=_HELP_WITH_NO_DELIVER)
        env = dict(os.environ)
        env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
        env["STUB_LOG"] = log
        env["STUB_MARKER"] = marker

        proc1 = subprocess.run(["bash", INSTALLER], env=env, cwd=_SKILL_DIR,
                                capture_output=True, text=True, timeout=15)
        proc2 = subprocess.run(["bash", INSTALLER], env=env, cwd=_SKILL_DIR,
                                capture_output=True, text=True, timeout=15)
        assert proc1.returncode == 0
        assert proc2.returncode == 0
        assert "skipping (idempotent)" in proc2.stdout
        with open(log) as fh:
            calls = [line for line in fh if line.strip()]
        assert len(calls) == 1, "second run must NOT re-register the cron"

    def test_missing_openclaw_cli_is_an_honest_skip_not_a_failure(self, tmp_path):
        # Real system PATH (so `bash`/`python3` still resolve for the
        # installer's own shebang-free `bash INSTALLER` invocation and its
        # internal python3 calls) with an empty dir prepended so `openclaw`
        # itself resolves to nothing.
        empty_bin = tmp_path / "empty-bin"
        os.makedirs(empty_bin, exist_ok=True)
        env = dict(os.environ)
        real_path_dirs = [d for d in env.get("PATH", "").split(os.pathsep)
                           if not os.path.isfile(os.path.join(d, "openclaw"))]
        env["PATH"] = os.pathsep.join([str(empty_bin), *real_path_dirs])
        proc = subprocess.run(["bash", INSTALLER], env=env, cwd=_SKILL_DIR,
                               capture_output=True, text=True, timeout=15)
        assert proc.returncode == 0
        assert "skipping" in proc.stdout.lower()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
