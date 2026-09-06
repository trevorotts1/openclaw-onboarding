"""Regression: the department's SCHEDULER-INVOKED entry points must resolve
their required env from the box's env store, and must never print a value.

WHY THIS EXISTS (measured on the operator Mac, 2026-09-06). launchd hands a
job essentially no environment. presentation-intake-poll.sh loaded no env
store, and its LaunchAgent declared none, so PRESENTATION_NOTIFY_CMD was
absent from the poller's PROCESS environment -- while being PRESENT and
non-blank in all three of that box's env stores. launcher.py's fail-closed
notify gate then refused every dispatch:

    AF-NOTIFY-UNCONFIGURED: PRESENTATION_NOTIFY_CMD is unset or blank

5,948 consecutive refusals sat in the poller's own log. The credential was
never missing. This is an ENV-LOADING defect, and it is a CLASS: every
credential a child of these entry points needs travels the same way
(OPENROUTER_API_KEY, read by shared-utils/llm_score.py from os.environ only,
is the second instance -- a persona pass under an environment-less scheduler
logs "all models failed").

WHAT IS PINNED HERE:

  1. STATIC   -- both scheduler entry points (presentation-intake-poll.sh and
                 presentation-watchdog.sh) invoke the loader.
  2. FAILING-BEFORE / PASSING-AFTER on ONE INSTRUMENT -- the SAME shell
                 harness, against the SAME scratch store, run twice: once
                 WITHOUT the loader (the pre-fix shape: the variable does not
                 resolve) and once WITH the poller's OWN load_env_store()
                 extracted VERBATIM from the shipped script and executed (it
                 does). Executing the real function, not a stand-in, is the
                 point -- the reason this defect survived is that nothing
                 ever ran the real thing.
  3. PRECEDENCE -- a value already set in the process environment WINS over
                 the store, so an operator override and the plist's own
                 EnvironmentVariables still hold. A BLANK process value does
                 NOT win: blank is the absence this fix is about.
  4. REDACTION -- a sentinel value planted in the scratch store must appear
                 NOWHERE in the report, and NOWHERE in the log the entry
                 point writes. Presence and LENGTH are the only facts about a
                 value that may be reported.
  5. STORE SEMANTICS -- parse rules, store ordering, and the documented
                 PRESENTATION_ENV_STORE=0 rollback.

Every leg is hermetic: HOME is redirected into tmp_path and OPENCLAW_SECRETS
points at a scratch file, so no leg can read -- or print -- this box's real
secrets. Nothing here touches the network or spawns an engine.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent  # .../presentations/scripts
POLL_SCRIPT = _SCRIPTS_DIR / "presentation-intake-poll.sh"
WATCHDOG_SCRIPT = _SCRIPTS_DIR / "presentation-watchdog.sh"
MODULE = _SCRIPTS_DIR / "presentation_job" / "env_store.py"

if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from presentation_job import env_store  # noqa: E402

#: A value no real store would ever carry, long enough to survive any
#: placeholder heuristic. If this string appears in a report or a log, a
#: secret value leaked.
SENTINEL = "sk-or-v1-SENTINEL-MUST-NEVER-BE-PRINTED-0123456789"
NOTIFY_VALUE = "/dept/scripts/presentation-notify.py --json"

_LOADER_RE = re.compile(r"^load_env_store\(\) \{\n(?P<body>.*?)^\}\n", re.S | re.M)


def _extract_loader(src: str) -> str:
    """The poller's REAL load_env_store() definition, verbatim."""
    m = _LOADER_RE.search(src)
    assert m, (
        "could not find load_env_store() in presentation-intake-poll.sh -- "
        "has the env-store block been removed or reshaped?"
    )
    return "load_env_store() {\n" + m.group("body") + "}\n"


@pytest.fixture()
def store(tmp_path: Path) -> Path:
    """A scratch env store carrying the transport and the sentinel."""
    path = tmp_path / "secrets" / ".env"
    path.parent.mkdir(parents=True)
    path.write_text(
        "# scratch store\n"
        f"PRESENTATION_NOTIFY_CMD={NOTIFY_VALUE}\n"
        f"export OPENROUTER_API_KEY={SENTINEL}\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def _hermetic_env(tmp_path: Path, store: Path, **extra) -> dict:
    """An environment that can only ever see the scratch store: HOME is
    redirected into tmp_path (so oc_paths' ~-relative Mac candidates all
    resolve to non-existent scratch paths) and OPENCLAW_SECRETS names the
    scratch file. No leg can read this box's real secrets."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tmp_path / "home"),
        "OPENCLAW_PLATFORM": "mac",
        "OPENCLAW_SECRETS": str(store),
    }
    env.update(extra)
    return env


def _run_shell(script: str, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", "-c", script], cwd=str(_SCRIPTS_DIR),
                          env=env, capture_output=True, text=True, timeout=60)


def _harness(tmp_path: Path, loader: str, call_loader: bool) -> str:
    """The SAME harness for the before and after legs -- the only difference
    is whether load_env_store is called. It echoes a REPORT LINE about
    PRESENTATION_NOTIFY_CMD that carries presence and length only, never the
    value, so the harness itself cannot leak."""
    log_file = tmp_path / "poll.log"
    return "\n".join([
        "set -uo pipefail",
        "PROG=presentation-intake-poll.sh",
        f'LOG_FILE="{log_file}"',
        'log() { echo "[$PROG] $*" >> "$LOG_FILE"; }',
        f'SCRIPTS_DIR="{_SCRIPTS_DIR}"',
        loader,
        ("load_env_store || true" if call_loader
         else "# pre-fix shape: the loader is never called"),
        # `${#var}` has no :- form, so take a defaulted copy first -- the
        # harness runs under `set -u` exactly like the real script does, and
        # an unbound read here would abort the control leg rather than
        # measure it.
        '_v="${PRESENTATION_NOTIFY_CMD:-}"',
        'printf "RESOLVED=%s LEN=%s\\n" "${_v:+yes}" "${#_v}"',
        'printf "OPENROUTER=%s\\n" "${OPENROUTER_API_KEY:+yes}"',
        "",
    ])


# ---------------------------------------------------------------------------
# 1. STATIC
# ---------------------------------------------------------------------------

def test_loader_module_exists():
    assert MODULE.is_file(), f"env_store.py not found at {MODULE}"


@pytest.mark.parametrize("script", [POLL_SCRIPT, WATCHDOG_SCRIPT],
                         ids=["intake-poll", "watchdog"])
def test_scheduler_entry_points_invoke_the_loader(script: Path):
    """Both launchd/cron entry points must load the store. A scheduler entry
    point that does not is the defect, by definition."""
    src = script.read_text(encoding="utf-8")
    assert "presentation_job.env_store --emit-shell" in src, (
        f"{script.name} never invokes the env-store loader -- under launchd "
        "it will run with no credentials and every dispatch will be refused "
        "(AF-NOTIFY-UNCONFIGURED)."
    )
    assert "presentation_job.env_store --report" in src, (
        f"{script.name} loads the store but logs no report -- a silent load "
        "cannot be audited when it fails."
    )


def test_entry_points_never_log_the_emit_shell_output():
    """--emit-shell is the ONLY surface carrying values. It must be captured
    in a command substitution and eval'd, never redirected into the log."""
    for script in (POLL_SCRIPT, WATCHDOG_SCRIPT):
        src = script.read_text(encoding="utf-8")
        for line in src.splitlines():
            # CODE only -- the block's own comments legitimately discuss both
            # --emit-shell and logging in the same sentence.
            if line.lstrip().startswith("#"):
                continue
            if "--emit-shell" not in line:
                continue
            assert "LOG" not in line, (
                f"{script.name} appears to send --emit-shell output toward a "
                f"log: {line.strip()!r}"
            )
            assert 'eval "$' not in line, (
                f"{script.name} evals the loader inline instead of capturing "
                f"it first: {line.strip()!r}"
            )


# ---------------------------------------------------------------------------
# 2. FAILING-BEFORE / PASSING-AFTER, one instrument.
# ---------------------------------------------------------------------------

def test_without_the_loader_the_transport_does_not_resolve(tmp_path, store):
    """CONTROL for the leg below: the identical harness, identical store, and
    the loader simply not called -- the pre-fix shape. The variable must NOT
    resolve. If this leg ever passes with RESOLVED=yes, the harness is
    leaking the value in from somewhere and the next leg proves nothing."""
    loader = _extract_loader(POLL_SCRIPT.read_text(encoding="utf-8"))
    result = _run_shell(_harness(tmp_path, loader, call_loader=False),
                        _hermetic_env(tmp_path, store))
    assert result.returncode == 0, result.stderr
    assert "RESOLVED= LEN=0" in result.stdout, (
        "the pre-fix shape resolved PRESENTATION_NOTIFY_CMD anyway -- this "
        "control is not isolated, so the after-leg would prove nothing.\n"
        + result.stdout
    )
    assert "OPENROUTER=\n" in result.stdout or "OPENROUTER=" in result.stdout


def test_with_the_loader_the_transport_resolves_from_the_store(tmp_path, store):
    """The poller's OWN load_env_store(), extracted verbatim and executed,
    must make PRESENTATION_NOTIFY_CMD resolve from the store -- and
    OPENROUTER_API_KEY with it, because the whole store is exported and every
    reader of either variable is a CHILD of this process."""
    loader = _extract_loader(POLL_SCRIPT.read_text(encoding="utf-8"))
    result = _run_shell(_harness(tmp_path, loader, call_loader=True),
                        _hermetic_env(tmp_path, store))
    assert result.returncode == 0, result.stderr
    assert f"RESOLVED=yes LEN={len(NOTIFY_VALUE)}" in result.stdout, (
        "PRESENTATION_NOTIFY_CMD did not resolve from the store, or resolved "
        "to the wrong length.\n" + result.stdout
    )
    assert "OPENROUTER=yes" in result.stdout, (
        "OPENROUTER_API_KEY did not resolve -- the persona-selector half of "
        "this defect class is not fixed.\n" + result.stdout
    )


# ---------------------------------------------------------------------------
# 3. PRECEDENCE
# ---------------------------------------------------------------------------

def test_process_env_overrides_the_store(tmp_path, store):
    """An operator override (or the LaunchAgent's own EnvironmentVariables)
    must WIN over the file, so a one-off invocation can still be steered."""
    override = "/tmp/override-transport.sh --one-off"
    loader = _extract_loader(POLL_SCRIPT.read_text(encoding="utf-8"))
    env = _hermetic_env(tmp_path, store, PRESENTATION_NOTIFY_CMD=override)
    result = _run_shell(
        _harness(tmp_path, loader, call_loader=True)
        + '\nprintf "VALUE=%s\\n" "$PRESENTATION_NOTIFY_CMD"\n',
        env,
    )
    assert result.returncode == 0, result.stderr
    assert f"VALUE={override}" in result.stdout, (
        "the store CLOBBERED a value already set in the process env -- an "
        "operator override cannot be relied on.\n" + result.stdout
    )
    assert NOTIFY_VALUE not in result.stdout


def test_blank_process_value_does_not_win(tmp_path, store):
    """A BLANK process value is the absence this fix exists to close, not an
    override -- so the store must still fill it. This matters concretely: the
    LaunchAgent may render PRESENTATION_NOTIFY_CMD empty when the transport
    file is not found at install time."""
    loader = _extract_loader(POLL_SCRIPT.read_text(encoding="utf-8"))
    env = _hermetic_env(tmp_path, store, PRESENTATION_NOTIFY_CMD="")
    result = _run_shell(_harness(tmp_path, loader, call_loader=True), env)
    assert result.returncode == 0, result.stderr
    assert f"RESOLVED=yes LEN={len(NOTIFY_VALUE)}" in result.stdout, (
        "a BLANK process value shadowed the store -- an empty plist entry "
        "would re-create the original outage.\n" + result.stdout
    )


# ---------------------------------------------------------------------------
# 4. REDACTION -- no value may reach a report or a log.
# ---------------------------------------------------------------------------

def test_report_never_contains_a_value(tmp_path, store):
    """The report is the only loader output that is ever logged. It must
    carry presence and LENGTH and nothing else."""
    result = subprocess.run(
        [sys.executable, "-m", "presentation_job.env_store", "--report"],
        cwd=str(_SCRIPTS_DIR), env=_hermetic_env(tmp_path, store),
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    combined = result.stdout + result.stderr
    assert SENTINEL not in combined, "a secret VALUE leaked into the report"
    assert NOTIFY_VALUE not in combined, "the transport VALUE leaked into the report"
    # ... and the control: it did report the FACTS about those same values,
    # so the absence above is redaction, not an empty report.
    assert "PRESENTATION_NOTIFY_CMD: PRESENT" in combined
    assert f"len {len(NOTIFY_VALUE)}" in combined
    assert "OPENROUTER_API_KEY: PRESENT" in combined


def test_entry_point_log_never_contains_a_value(tmp_path, store):
    """End-to-end redaction: run the REAL extracted loader and then read the
    log file it wrote. No value may be in it."""
    loader = _extract_loader(POLL_SCRIPT.read_text(encoding="utf-8"))
    result = _run_shell(_harness(tmp_path, loader, call_loader=True),
                        _hermetic_env(tmp_path, store))
    assert result.returncode == 0, result.stderr
    log_text = (tmp_path / "poll.log").read_text(encoding="utf-8")
    assert SENTINEL not in log_text, (
        "a secret VALUE was written to the entry point's log file:\n" + log_text
    )
    assert NOTIFY_VALUE not in log_text, (
        "the transport VALUE was written to the log file:\n" + log_text
    )
    # Control: the log is not empty and DID report the load.
    assert "[env-store]" in log_text, (
        "no env-store report reached the log at all, so the assertions above "
        "are vacuous:\n" + log_text
    )
    assert "PRESENT (len" in log_text


# ---------------------------------------------------------------------------
# 5. STORE SEMANTICS (module-level unit legs)
# ---------------------------------------------------------------------------

def test_parse_store_semantics(tmp_path):
    path = tmp_path / "s.env"
    path.write_text(
        "# comment\n"
        "\n"
        'QUOTED="double"\n'
        "SINGLE='single'\n"
        "export EXPORTED=value\n"
        "WITH_EQUALS=a=b=c\n"
        "not a legal name=skipped\n"
        "FIRST=one\n"
        "FIRST=two\n",
        encoding="utf-8",
    )
    parsed = env_store.parse_store(path)
    assert parsed["QUOTED"] == "double"
    assert parsed["SINGLE"] == "single"
    assert parsed["EXPORTED"] == "value"
    assert parsed["WITH_EQUALS"] == "a=b=c", "split must be on the FIRST '='"
    assert not any(" " in k for k in parsed), "an illegal name was accepted"
    assert parsed["FIRST"] == "one", "the FIRST occurrence in a file must win"


def test_parse_store_missing_file_is_empty_not_an_exception(tmp_path):
    """An unreadable store answers nothing; it never kills a poll tick."""
    assert env_store.parse_store(tmp_path / "nope.env") == {}


def test_earlier_store_wins_and_blank_never_blocks_a_later_store(tmp_path):
    """Store order decides, and a BLANK in an earlier store must NOT block a
    real value in a later one -- that would be the original defect wearing a
    different hat."""
    first = tmp_path / "first.env"
    second = tmp_path / "second.env"
    first.write_text("A=from-first\nPRESENTATION_NOTIFY_CMD=\n", encoding="utf-8")
    second.write_text("A=from-second\nPRESENTATION_NOTIFY_CMD=real\n",
                      encoding="utf-8")
    assignments, report = env_store.resolve(environ={"PATH": "/usr/bin"},
                                            paths=[first, second])
    assert assignments["A"] == "from-first", "the earlier store must win"
    assert assignments["PRESENTATION_NOTIFY_CMD"] == "real", (
        "a blank in the first store blocked the real value in the second"
    )
    assert SENTINEL not in env_store.redacted_report(report)


def test_rollback_flag_is_a_documented_no_op_not_a_silent_one(tmp_path, store):
    """PRESENTATION_ENV_STORE=0 must load nothing AND say so."""
    assignments, report = env_store.resolve(
        environ={"PATH": "/usr/bin", "PRESENTATION_ENV_STORE": "0"},
        paths=[store],
    )
    assert assignments == {}, "the rollback flag did not disable the load"
    text = env_store.redacted_report(report)
    assert "PRESENTATION_ENV_STORE=0" in text, (
        "the rollback happened silently -- a silent no-op is indistinguishable "
        "from a broken loader"
    )
    assert SENTINEL not in text


def test_emit_shell_quotes_values_so_eval_cannot_execute(tmp_path):
    """A hostile store value must not be able to run anything when the
    caller evals the emitted assignments."""
    path = tmp_path / "hostile.env"
    marker = tmp_path / "PWNED"
    path.write_text(f"EVIL=$(touch {marker})`touch {marker}`; touch {marker}\n",
                    encoding="utf-8")
    assignments, _ = env_store.resolve(environ={"PATH": "/usr/bin"},
                                       paths=[path])
    emitted = env_store.emit_shell(assignments)
    # The emitted text goes to a FILE and is read back exactly the way the
    # entry points do it (command substitution into a variable, then eval of
    # that variable). Interpolating it straight into the `bash -c` string
    # instead would expand `$(...)` and backticks at the OUTER level, before
    # eval ever ran -- the harness would then "prove" a breakout that the
    # real call shape cannot produce.
    emitted_file = tmp_path / "emitted.sh"
    emitted_file.write_text(emitted, encoding="utf-8")
    result = subprocess.run(
        ["bash", "-c",
         f'_ENV_SH="$(cat {emitted_file})"; eval "$_ENV_SH"; printf "%s" "$EVIL"'],
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert not marker.exists(), (
        "eval of the emitted assignments EXECUTED a store value -- shlex "
        "quoting is not holding"
    )
    assert "touch" in result.stdout, "the value should survive intact as text"
