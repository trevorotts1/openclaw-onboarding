"""presentation_job/env_store.py -- the ONE env-store loader for this
department's SCHEDULER-INVOKED entry points.

THE ONE-SENTENCE PROBLEM THIS FIXES: a script started by launchd or by the
openclaw cron gets essentially NO environment, and nothing in
presentation-intake-poll.sh or presentation-watchdog.sh ever loaded the
box's env store -- so PRESENTATION_NOTIFY_CMD (present and non-blank in the
store) was absent from the poller's PROCESS environment, launcher.py's
notify_gate refused every dispatch with AF-NOTIFY-UNCONFIGURED, and the
pipeline was dead on arrival every five minutes.

THIS IS AN ENV-LOADING DEFECT, NOT A CREDENTIAL DEFECT. The credential was
there the whole time. Measured on the operator Mac 2026-09-06: 5,948
consecutive AF-NOTIFY-UNCONFIGURED refusals in
~/Library/Logs/openclaw/presentation-intake-poll.log while
PRESENTATION_NOTIFY_CMD was present and non-blank in all three stores.

IT IS A CLASS, NOT AN INSTANCE. Every credential a child of these entry
points needs travels the same way. OPENROUTER_API_KEY is the second
instance: shared-utils/llm_score.py resolves it from os.environ (falling
back only to openclaw.json's env block -- never to the secrets stores), so
a persona-selection pass spawned under an environment-less scheduler scores
nothing and logs "all models failed: OPENROUTER_API_KE...". Exporting the
store at the ENTRY POINT fixes every such reader at once, because every
reader is a CHILD of one.

WHY A PYTHON MODULE AND NOT A LINE OF SHELL. The candidate ORDER is
platform-aware and already owned by one authority
(presentation_job.oc_paths.secrets_env_candidates, FIX 68): on the docker
VPS /data/.openclaw/secrets/.env is first, on a Mac the ~/.openclaw stores
are. Re-deriving that order in sh would be a second, drifting copy of the
same vocabulary. This module reuses the authority and adds nothing to it.

PRECEDENCE -- THE PART THAT IS DELIBERATELY *NOT* THE `set -a` IDIOM.
The sanctioned shell idiom used elsewhere in this repo (bin/presentation
step 3, qc-*.sh, 38-conversational-ai-system/scripts/*) is::

    set -a; . "$SECRETS_ENV"; set +a

That idiom lets the FILE win over the process environment. Here the
requirement is the opposite and it matters: an operator must be able to
override a value for one invocation (`PRESENTATION_NOTIFY_CMD=... bash
presentation-intake-poll.sh`), and launchd's own EnvironmentVariables dict
must not be silently overwritten by a stale store. So:

    a name already set to a NON-BLANK value in the process environment WINS
    and is never re-assigned; a name set to a BLANK value does NOT win (a
    blank is the absence this whole fix is about, not an override).

Precedence below that is store order: the first candidate file that defines
a name wins, later files only fill gaps. That is the same
"first source that answers, wins" posture every reader in this package
already has (research_web._read_secret_named, model_router.provider_key_
resolves) and the same "search every store" posture AGENTS.md requires of
any credential claim.

PARSED, NEVER EXECUTED. `. file` runs the store as shell. This module parses
it instead, with the SAME line semantics the package's existing readers use
(strip the line, split on the first "=", strip surrounding double then
single quotes). A store file therefore cannot execute anything, which is
strictly safer than the idiom it replaces.

NO SECRET VALUE IS EVER PRINTED, LOGGED, OR PLACED IN AN ARGV.
  * --emit-shell writes `export NAME='value'` lines to STDOUT only. The
    caller consumes them through a command substitution (a pipe) and
    `eval`s them; they never reach a log, a file, or a process argument
    list. Values are quoted with shlex.quote, so a store value cannot break
    out of its assignment.
  * --report writes a REDACTED report: file paths, name COUNTS, and per
    watched-name presence plus LENGTH. Never a value, never a prefix of a
    value. redacted_report() is the only reporting surface and
    tests/test_poller_env_store.py asserts a sentinel value never appears
    in it.

ROLLBACK: PRESENTATION_ENV_STORE=0 makes the loader a documented no-op --
it resolves nothing and emits nothing, restoring the exact pre-fix
behaviour. It is never a silent no-op: the report says so.
"""
from __future__ import annotations

import argparse
import os
import re
import shlex
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

#: Documented rollback. "0" -> load nothing at all (pre-fix behaviour).
FLAG_ENV = "PRESENTATION_ENV_STORE"

#: Names this department's scheduler entry points cannot dispatch without.
#: PRESENTATION_NOTIFY_CMD is the transport notify_preflight.check_notify_config
#: gates on; its absence is the AF-NOTIFY-UNCONFIGURED refusal.
REQUIRED_NAMES: Tuple[str, ...] = ("PRESENTATION_NOTIFY_CMD",)

#: Names whose absence DEGRADES a pass rather than refusing it -- reported so
#: a silent degradation is visible in the poller log. OPENROUTER_API_KEY is
#: the persona-selector instance of this same class.
WATCHED_NAMES: Tuple[str, ...] = ("OPENROUTER_API_KEY", "PRESENTATION_RUNS_DIR")

#: A legal POSIX shell / environment variable name. Anything else in a store
#: file is skipped rather than exported -- a name that cannot be exported
#: safely is not exported at all.
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

#: Last-resort candidate order used ONLY when presentation_job.oc_paths is not
#: importable (a partial deploy). It is a deliberate copy of oc_paths' Mac
#: list, mirroring the identical `except ImportError` fallbacks in
#: research_web._read_secret_named and model_router._secrets_env_files -- the
#: package's established posture for a standalone/partial deploy. oc_paths
#: stays the authority whenever it can be imported.
_FALLBACK_CANDIDATES: Tuple[str, ...] = (
    "~/.openclaw/secrets/.env",
    "~/.openclaw/secrets/secrets.env",
    "~/.openclaw/.env",
    "~/.openclaw/workspace/.env",
    "~/clawd/secrets/.env",
)


def enabled(environ: Optional[Dict[str, str]] = None) -> bool:
    """PRESENTATION_ENV_STORE default ON ("1"); "0" is the documented
    rollback to the pre-fix no-load behaviour. Any value other than "0" is
    ON -- the safe default is to load, never to fail open on a typo."""
    view = os.environ if environ is None else environ
    return str(view.get(FLAG_ENV, "1") or "").strip() != "0"


def candidate_files() -> List[Path]:
    """The ordered store-file candidates, from the FIX 68 authority.

    A tree where presentation_job.oc_paths cannot be imported prints a LOUD
    line on stderr and falls back to the documented Mac list -- the same
    posture presentation-intake-poll.sh's read_run_mode uses for a partial
    deploy. Silence is never an option here: a wrong candidate order on a
    VPS is exactly the FIX 68 defect."""
    try:
        from presentation_job.oc_paths import secrets_env_candidates
        return [Path(p) for p in secrets_env_candidates()]
    except Exception as exc:  # noqa: BLE001 -- a partial deploy must be LOUD
        print(
            f"[env-store] could not import presentation_job.oc_paths "
            f"({exc.__class__.__name__}: {exc}) -- falling back to the "
            f"documented Mac candidate list. On a VPS this is the WRONG "
            f"order (/data/.openclaw is first there). Fix the deploy.",
            file=sys.stderr,
        )
        return [Path(os.path.expanduser(spec)) for spec in _FALLBACK_CANDIDATES]


def parse_store(path: Path) -> Dict[str, str]:
    """NAME -> VALUE for ONE store file. Returns {} for a file that does not
    exist or cannot be read -- an unreadable store is a store that answers
    nothing, never an exception that kills a poll tick.

    Parse semantics are the package's existing ones (research_web.
    _read_secret_named, model_router.provider_key_resolves): strip the line,
    skip blanks and #-comments, accept an optional `export ` prefix, split on
    the FIRST "=", strip surrounding double then single quotes. The FIRST
    occurrence of a name in a file wins, matching those readers' "return on
    the first matching line" behaviour.

    The file is PARSED. It is never sourced, so it cannot execute anything.
    """
    out: Dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip()
        if not _NAME_RE.match(name):
            continue
        out.setdefault(name, value.strip().strip('"').strip("'"))
    return out


def resolve(environ: Optional[Dict[str, str]] = None,
            paths: Optional[Sequence[Path]] = None) -> Tuple[Dict[str, str], dict]:
    """Decide what to export. Returns ``(assignments, report)``.

    ``assignments`` maps NAME -> VALUE for the names that must be exported.
    A name already set to a NON-BLANK value in ``environ`` is NOT in it --
    that is the precedence guarantee: the process environment wins.

    ``report`` is REDACTED by construction: it carries paths, counts and
    per-name presence/length, and no value ever enters it. Every caller that
    logs anything logs this, never ``assignments``.
    """
    view = dict(os.environ if environ is None else environ)
    files = list(candidate_files() if paths is None else paths)

    report: dict = {
        "enabled": enabled(view),
        "files": [],
        "exported_names": [],
        "already_in_process_env": [],
        "names": {},
    }

    if not report["enabled"]:
        report["rollback"] = (
            f"{FLAG_ENV}=0 -- the env store was NOT loaded (documented "
            f"rollback). This is a deliberate no-op, not a failure."
        )
        _describe_names(view, {}, report)
        return {}, report

    assignments: Dict[str, str] = {}
    for path in files:
        exists = path.is_file()
        entry = {"path": str(path), "exists": exists, "names": 0, "used": 0}
        if exists:
            parsed = parse_store(path)
            entry["names"] = len(parsed)
            for name, value in parsed.items():
                if not value.strip():
                    # A BLANK value in a store is the absence this whole fix
                    # is about, exactly as a blank in the process env is --
                    # so it is not recorded. Recording it would let an empty
                    # `PRESENTATION_NOTIFY_CMD=` line in the FIRST store
                    # block the real value a LATER store carries, which is
                    # the original defect wearing a different hat.
                    continue
                if str(view.get(name) or "").strip():
                    # Already set NON-BLANK in the process env: it wins.
                    if name not in report["already_in_process_env"]:
                        report["already_in_process_env"].append(name)
                    continue
                if name in assignments:
                    continue  # an earlier store already answered
                assignments[name] = value
                entry["used"] += 1
        report["files"].append(entry)

    report["exported_names"] = sorted(assignments)
    _describe_names(view, assignments, report)
    return assignments, report


def _describe_names(view: Dict[str, str], assignments: Dict[str, str],
                    report: dict) -> None:
    """Per-name presence and LENGTH for the required/watched names. Length is
    the ONLY thing about a value that is ever reported -- never the value,
    never a prefix of it."""
    for name in REQUIRED_NAMES + WATCHED_NAMES:
        raw = assignments.get(name)
        source = "env-store"
        if raw is None:
            raw = str(view.get(name) or "")
            source = "process-env" if raw.strip() else "UNRESOLVED"
        report["names"][name] = {
            "required": name in REQUIRED_NAMES,
            "resolved": bool(str(raw).strip()),
            "length": len(str(raw).strip()),
            "source": source,
        }


def emit_shell(assignments: Dict[str, str]) -> str:
    """`export NAME='value'` lines, one per assignment, shell-quoted.

    THIS IS THE ONLY SURFACE THAT CARRIES A VALUE, and it goes to STDOUT so
    the caller can capture it in a command substitution and `eval` it. Never
    redirect this into a log. shlex.quote guarantees each value is a single
    inert POSIX token, so `eval` on this output cannot execute anything the
    store did not literally assign -- strictly safer than the `. "$file"`
    idiom it replaces, which executes the whole file."""
    lines = []
    for name in sorted(assignments):
        if not _NAME_RE.match(name):
            continue
        lines.append(f"export {name}={shlex.quote(assignments[name])}")
    return "\n".join(lines)


def redacted_report(report: dict) -> str:
    """Human-readable, VALUE-FREE. Safe to send straight to a log file."""
    out: List[str] = []
    if report.get("rollback"):
        out.append(report["rollback"])
    for entry in report.get("files", []):
        if entry["exists"]:
            out.append(f"store {entry['path']}: {entry['names']} names, "
                       f"{entry['used']} exported")
        else:
            out.append(f"store {entry['path']}: absent")
    if not report.get("files"):
        out.append("no candidate store files were considered")
    # WORDED CAREFULLY. The entry points run --report AFTER they have eval'd
    # --emit-shell, so by then the loaded names are ALREADY in the process env
    # and this line correctly says "0 to export, N already set". Read without
    # that context, "exported 0 names" looks like a failed load -- and a
    # summary line that reads as the opposite of what happened is the very
    # defect this change set exists to remove. So say which case is which.
    out.append(f"{len(report.get('exported_names', []))} name(s) still to "
               f"export from the stores; "
               f"{len(report.get('already_in_process_env', []))} already set "
               f"in the process env and NOT overwritten (process env wins). "
               f"After a successful load the loaded names are in the second "
               f"group -- that is what success looks like here; judge the "
               f"outcome by the per-name lines below, not by these counts.")
    for name, info in sorted(report.get("names", {}).items()):
        tag = "REQUIRED" if info["required"] else "watched "
        if info["resolved"]:
            out.append(f"{tag} {name}: PRESENT (len {info['length']}, "
                       f"source {info['source']})")
        else:
            out.append(f"{tag} {name}: NOT RESOLVED from the process env or "
                       f"any candidate store -- a child that needs it will "
                       f"refuse")
    return "\n".join(out)


def unresolved_required(report: dict) -> List[str]:
    """The REQUIRED names that resolved from nowhere. A non-empty list is the
    caller's cue that a dispatch is about to be refused downstream."""
    return sorted(
        name for name, info in report.get("names", {}).items()
        if info["required"] and not info["resolved"]
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="presentation_job.env_store",
        description="Load the box's env store for a scheduler-invoked entry "
                    "point. Process env wins; no value is ever logged.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--emit-shell", action="store_true",
        help="print `export NAME='value'` lines on STDOUT for the caller to "
             "eval. Capture through a command substitution; NEVER log it.")
    group.add_argument(
        "--report", action="store_true",
        help="print the REDACTED report (paths, counts, presence+length) on "
             "STDOUT. Contains no values and is safe to log.")
    parser.add_argument(
        "--require-resolved", action="store_true",
        help="with --report, exit 8 when a REQUIRED name resolved from "
             "nowhere (the same exit notify_preflight uses).")
    args = parser.parse_args(list(argv) if argv is not None else None)

    assignments, report = resolve()

    if args.emit_shell:
        text = emit_shell(assignments)
        if text:
            sys.stdout.write(text + "\n")
        return 0

    sys.stdout.write(redacted_report(report) + "\n")
    if args.require_resolved and unresolved_required(report):
        return 8
    return 0


if __name__ == "__main__":  # pragma: no cover -- CLI entry
    raise SystemExit(main())
