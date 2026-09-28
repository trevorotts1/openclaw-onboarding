"""Fix 3 (PRES-035 regression) — the poller and the launcher load the env store.

The regression: `load_env_store()` was defined in presentation-intake-poll.sh
but called nowhere, so PRESENTATION_NOTIFY_CMD stayed empty in the poller's
process env and every --resume was refused with AF-NOTIFY-UNCONFIGURED (plus
OPENROUTER_API_KEY missing for everything the tick spawned). launcher.main()
had the same gap.

The fix: the poller calls `load_env_store || true` after log() is defined and
before RUNS_ROOT=; launcher.main() calls load_into_process() first thing.

This test is hermetic: HOME is redirected into tmp_path and OPENCLAW_SECRETS
points at a scratch store, so no leg can read this box's real secrets. The
process env carries PRESENTATION_NOTIFY_CMD="" (the empty plist value); the
scratch store carries the sentinel. It proves, with the REAL code:
  poller:   the shipped script calls the loader at top level between log()
            and RUNS_ROOT=; the verbatim-extracted loader writes [env-store]
            lines to the log and resolves the sentinel over the empty value,
            with no AF-NOTIFY-UNCONFIGURED anywhere.
  launcher:  main() loads the env store before argparse; running the REAL
            main(["--check", ...]) resolves the sentinel from the store.
No engine is spawned, no network is touched, no value is ever printed.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
POLL_SCRIPT = _SCRIPTS_DIR / "presentation-intake-poll.sh"
LAUNCHER = _SCRIPTS_DIR / "presentation_job" / "launcher.py"

#: Fake transport command no real store would carry. Only presence/length
#: are ever asserted; the value itself is never printed.
NOTIFY_VALUE = "/scratch/presentations/bin/notify --json"

_LOADER_RE = re.compile(r"^load_env_store\(\) \{\n(?P<body>.*?)^\}\n", re.S | re.M)


def _extract_loader(src: str) -> str:
    m = _LOADER_RE.search(src)
    assert m, "load_env_store() not found in presentation-intake-poll.sh"
    return "load_env_store() {\n" + m.group("body") + "}\n"


@pytest.fixture()
def store(tmp_path: Path) -> Path:
    path = tmp_path / "secrets" / ".env"
    path.parent.mkdir(parents=True)
    path.write_text(
        "# scratch store\n"
        f"PRESENTATION_NOTIFY_CMD={NOTIFY_VALUE}\n"
        "OPENROUTER_API_KEY=<redacted>\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def _hermetic_env(tmp_path: Path, store: Path) -> dict:
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tmp_path / "home"),
        "OPENCLAW_SECRETS": str(store),
        # The empty plist value: launchd hands the job a blank variable.
        "PRESENTATION_NOTIFY_CMD": "",
    }


def test_env_store_restored_poller_and_launcher(tmp_path, store):
    poll_src = POLL_SCRIPT.read_text()

    # ---- static: poller wires the call between log() and RUNS_ROOT= ----
    log_line = next(
        i for i, l in enumerate(poll_src.splitlines()) if l.startswith("log()")
    )
    runs_line = next(
        i for i, l in enumerate(poll_src.splitlines()) if l.startswith("RUNS_ROOT=")
    )
    call_lines = [
        i
        for i, l in enumerate(poll_src.splitlines())
        if l.strip() == "load_env_store || true"
    ]
    assert call_lines, "no top-level 'load_env_store || true' in the poll script"
    assert any(log_line < i < runs_line for i in call_lines), (
        "the loader call must sit after log() is defined and before RUNS_ROOT="
    )

    # ---- dynamic: the REAL loader resolves the sentinel over the empty value ----
    log_file = tmp_path / "poll.log"
    harness = "\n".join(
        [
            "set -uo pipefail",
            "PROG=presentation-intake-poll.sh",
            f'LOG_FILE="{log_file}"',
            'log() { echo "[$PROG] $*" >> "$LOG_FILE"; }',
            f'SCRIPTS_DIR="{_SCRIPTS_DIR}"',
            _extract_loader(poll_src),
            "load_env_store || true",
            '_v="${PRESENTATION_NOTIFY_CMD:-}"',
            'printf "RESOLVED=%s LEN=%s\\n" "${_v:+yes}" "${#_v}"',
            "",
        ]
    )
    res = subprocess.run(
        ["bash", "-c", harness],
        cwd=str(_SCRIPTS_DIR),
        env=_hermetic_env(tmp_path, store),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert "RESOLVED=yes" in res.stdout, (
        "loader did not resolve PRESENTATION_NOTIFY_CMD from the store:\n"
        + res.stdout
        + res.stderr
    )
    assert f"LEN={len(NOTIFY_VALUE)}" in res.stdout, res.stdout + res.stderr
    log_text = log_file.read_text()
    assert "[env-store]" in log_text, f"log shows no [env-store] lines:\n{log_text}"
    assert "AF-NOTIFY-UNCONFIGURED" not in log_text, log_text
    assert "AF-NOTIFY-UNCONFIGURED" not in res.stdout + res.stderr

    # ---- static: launcher.main() loads the store before argparse ----
    launch_src = LAUNCHER.read_text()
    main_at = launch_src.index("def main(")
    parse_at = launch_src.index("args = p.parse_args(argv)", main_at)
    head = launch_src[main_at:parse_at]
    assert "from .env_store import load_into_process" in head, (
        "launcher.main() must import load_into_process before argparse"
    )
    assert "load_into_process()" in head, (
        "launcher.main() must call load_into_process() before argparse"
    )

    # ---- dynamic: the REAL launcher.main() resolves the sentinel ----
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    driver = (
        "import os, sys; "
        f"sys.path.insert(0, {str(_SCRIPTS_DIR)!r}); "
        "from presentation_job.launcher import main; "
        f"rc = main(['--check', '--run-dir', {str(run_dir)!r}]); "
        "_v = os.environ.get('PRESENTATION_NOTIFY_CMD', ''); "
        "print('NOTIFY_SET=' + ('yes' if _v else 'no')); "
        "print('NOTIFY_LEN=' + str(len(_v))); "
        "print('MAIN_RC=' + str(rc))"
    )
    res2 = subprocess.run(
        [sys.executable, "-c", driver],
        cwd=str(_SCRIPTS_DIR),
        env=_hermetic_env(tmp_path, store),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert "NOTIFY_SET=yes" in res2.stdout, (
        "launcher.main() did not load PRESENTATION_NOTIFY_CMD from the store:\n"
        + res2.stdout
        + res2.stderr
    )
    assert f"NOTIFY_LEN={len(NOTIFY_VALUE)}" in res2.stdout, res2.stdout + res2.stderr
    assert "AF-NOTIFY-UNCONFIGURED" not in res2.stdout + res2.stderr, (
        res2.stdout + res2.stderr
    )
