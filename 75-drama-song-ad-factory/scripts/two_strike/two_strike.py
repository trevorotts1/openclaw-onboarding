#!/usr/bin/env python3
"""DEL-17 two-strike anti-reverse-engineering gate (shared module).

One module, one policy, every wired skill. Stdlib only.

Policy (operator order 2026-10-09 13:35 item 5, carried out with the three
defaults Trevor chose for decision D-6 on 2026-11-13):
  * The strike counter lives OUTSIDE every skill folder. Nothing under a
    skill directory is ever used as state, so a client cannot read, edit or
    reset a counter by poking at the skill they are trying to unpack.
  * A turn only spends a strike when the extraction phrase is ABOUT this
    assistant: the phrase must sit in the same sentence as "you", "your" or
    "this skill". Text typed as an answer to an intake card question is
    never tested. An ordinary sentence about a client's own product is not
    an extraction attempt.
  * Every strike writes one silent notice recording client, box and skill.
    Silent means the client never sees it; it is an operator audit record.
  * Strike one answers with a refusal containing STRIKE_ONE_WARNING.
  * Strike two zeroes the offending skill folder down to a stub whose only
    content is STRIKE_TWO_STUB. While paid work is in flight the strike is
    recorded and the reply blocked at once, and the wipe runs at the next
    park or completion (apply_pending_wipe).
  * Unlock is operator-only: restore the skill from GitHub, then run the
    operator-only command ``python3 two_strike.py operator-clear`` to clear
    the count for that client|box|skill so the restored folder is not wiped
    by the next match. It refuses without BLACKCEO_TWO_STRIKE_OPERATOR=1.
  * The wipe touches only the one skill's own files. It never follows a
    symlink out of the skill folder and never reaches client data, client
    keys or client settings.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

TOOL_NAME = "two_strike"
TOOL_VERSION = "1.1.0"

# --- the two exact strings (contract; do not reword) -----------------------
STRIKE_ONE_WARNING = (
    "Please do not ask me that question again in the future."
)
STRIKE_TWO_STUB = (
    "Hey, you need to contact BlackCEO to find out why your system has been disabled."
)
# The stub file that replaces the whole skill folder. SKILL.md is the file
# every runtime reads first, so the disabled message is what loads.
STUB_FILENAME = "SKILL.md"

# Strike counter + notice log live here by default, never under a skill.
ENV_STATE_ROOT = "BLACKCEO_TWO_STRIKE_HOME"
_DEFAULT_STATE_ROOT = Path(".blackceo") / "two_strike"

# The operator-only clear refuses unless the operator's restore shell sets
# this marker. There is no client-facing path that sets it.
ENV_OPERATOR = "BLACKCEO_TWO_STRIKE_OPERATOR"
_OPERATOR_ON = frozenset({"1", "true", "yes", "on"})

# Path components that mark a directory as somebody's skill tree or as the
# skills root. A state root carrying any of these is refused.
_SKILL_DIR_COMPONENT = re.compile(r"^\d{2}-[a-z0-9].*")
_SKILLS_ROOT_COMPONENTS = frozenset({"skills", "skill"})
# Path fragments a skill folder must never sit in.
_SECRET_PATH_FRAGMENTS = ("/secrets/", "/credentials/", "/.env/")


class TwoStrikeError(Exception):
    """Refused operation. ``code`` is the stable machine reason."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


# --- state root (outside every skill folder) -------------------------------
def state_root() -> Path:
    """Resolved state root. Env override wins; never inside a skill folder."""
    raw = os.environ.get(ENV_STATE_ROOT) or str(Path.home() / _DEFAULT_STATE_ROOT)
    root = Path(raw).expanduser().resolve()
    assert_state_root_outside_skill_folders(root)
    return root


def assert_state_root_outside_skill_folders(root: Path) -> None:
    """Refuse a state root that sits in, or under, a skill folder."""
    parts = root.parts
    for part in parts:
        if part.lower() in _SKILLS_ROOT_COMPONENTS:
            raise TwoStrikeError(
                "STATE_ROOT_INSIDE_SKILLS_ROOT",
                f"state root {root} sits under a skills folder; the strike "
                "counter must live outside every skill folder",
            )
        if _SKILL_DIR_COMPONENT.match(part):
            raise TwoStrikeError(
                "STATE_ROOT_INSIDE_SKILL_FOLDER",
                f"state root {root} sits inside skill folder {part!r}; the "
                "strike counter must live outside every skill folder",
            )
    for parent in [root, *root.parents]:
        if (parent / "SKILL.md").is_file():
            raise TwoStrikeError(
                "STATE_ROOT_INSIDE_SKILL_FOLDER",
                f"state root {root} sits inside a skill folder (ancestor "
                f"{parent} carries SKILL.md); the strike counter must live "
                "outside every skill folder",
            )


def _counter_path(root: Path) -> Path:
    return root / "strikes.json"


def _notice_path(root: Path) -> Path:
    return root / "notices.jsonl"


def _key(client: str, box: str, skill: str) -> str:
    return "|".join((client, box, skill))


def _load_counters(root: Path) -> dict:
    path = _counter_path(root)
    if not path.is_file():
        return {"version": 1, "strikes": {}}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {"version": 1, "strikes": {}}
    if not isinstance(data, dict) or not isinstance(data.get("strikes"), dict):
        return {"version": 1, "strikes": {}}
    return data


def _save_counters(root: Path, data: dict) -> None:
    root.mkdir(parents=True, exist_ok=True)
    path = _counter_path(root)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


def _append_notice(root: Path, notice: dict) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = _notice_path(root)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(notice, sort_keys=True) + "\n")
    return path


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _set_row_field(
    client: str, box: str, skill: str, *, root: Path | None = None, **fields
) -> dict | None:
    """Update named fields on one counter row. None when there is no row."""
    base = root or state_root()
    store = _load_counters(base)
    key = _key(client, box, skill)
    row = store["strikes"].get(key)
    if not isinstance(row, dict):
        return None
    row.update(fields)
    store["strikes"][key] = row
    _save_counters(base, store)
    return dict(row)


def current_count(client: str, box: str, skill: str, *, root: Path | None = None) -> int:
    """Strikes recorded so far for this client|box|skill triple."""
    store = _load_counters(root or state_root())
    row = store["strikes"].get(_key(client, box, skill))
    if not isinstance(row, dict):
        return 0
    try:
        return int(row.get("count", 0))
    except (TypeError, ValueError):
        return 0


# --- the two exact answers -------------------------------------------------
def refusal_text(strike: int) -> str:
    """What the wired skill puts in front of the client for this strike."""
    return STRIKE_ONE_WARNING if strike <= 1 else STRIKE_TWO_STUB


def stub_bytes() -> bytes:
    """Exact bytes the wiped skill folder is left with. Nothing else."""
    return STRIKE_TWO_STUB.encode("utf-8")


# --- silent notice + strike accounting -------------------------------------
def record_strike(
    client: str,
    box: str,
    skill: str,
    *,
    reason: str | None = None,
    deferred: bool = False,
    root: Path | None = None,
) -> dict:
    """Count one strike and log one silent notice. Returns the strike row.

    ``deferred`` marks a strike two whose wipe waits for the paid run to
    park, so the notice says so instead of claiming a wipe that has not
    happened yet.
    """
    if not client or not box or not skill:
        raise TwoStrikeError(
            "MISSING_IDENTITY",
            "record_strike needs client, box and skill so the silent notice "
            "can name all three",
        )
    base = root or state_root()
    store = _load_counters(base)
    key = _key(client, box, skill)
    row = store["strikes"].get(key)
    if not isinstance(row, dict):
        row = {"count": 0, "first": None, "last": None, "wiped": False,
               "pending_wipe": False}
    strike = int(row.get("count", 0)) + 1
    now = _now()
    row["count"] = strike
    row["last"] = now
    if not row.get("first"):
        row["first"] = now
    store["strikes"][key] = row
    _save_counters(base, store)
    _append_notice(
        base,
        {
            "ts": now,
            "client": client,
            "box": box,
            "skill": skill,
            "strike": strike,
            "action": (
                "defer_wipe" if (strike >= 2 and deferred)
                else "refusal" if strike < 2
                else "wipe"
            ),
            "reason": reason,
        },
    )
    return dict(row, client=client, box=box, skill=skill)


def mark_wiped(client: str, box: str, skill: str, *, root: Path | None = None) -> None:
    """Flag the triple as wiped in the counter store."""
    base = root or state_root()
    store = _load_counters(base)
    key = _key(client, box, skill)
    row = store["strikes"].get(key)
    if isinstance(row, dict):
        row["wiped"] = True
        row["pending_wipe"] = False
        store["strikes"][key] = row
        _save_counters(base, store)


# --- operator-only clear (decision D-6, default 2) -------------------------
def operator_enabled() -> bool:
    """True only in the operator's restore shell, never on a client path."""
    return os.environ.get(ENV_OPERATOR, "").strip().lower() in _OPERATOR_ON


def clear_strikes(
    client: str, box: str, skill: str, *, root: Path | None = None
) -> dict:
    """Clear the count for one client|box|skill triple. Operator only.

    The restore procedure runs this after pulling the good bytes back from
    GitHub, so the restored folder is not wiped again by the next match.
    Without the operator marker the call is refused; no client-facing code
    path sets that marker.
    """
    if not operator_enabled():
        raise TwoStrikeError(
            "OPERATOR_ONLY",
            f"operator-clear is operator only; run it from the restore shell "
            f"with {ENV_OPERATOR}=1 set",
        )
    if not client or not box or not skill:
        raise TwoStrikeError(
            "MISSING_IDENTITY",
            "operator-clear needs client, box and skill so exactly one "
            "counter row is cleared",
        )
    base = root or state_root()
    store = _load_counters(base)
    key = _key(client, box, skill)
    existed = isinstance(store["strikes"].pop(key, None), dict)
    _save_counters(base, store)
    _append_notice(
        base,
        {
            "ts": _now(),
            "client": client,
            "box": box,
            "skill": skill,
            "strike": 0,
            "action": "operator_clear",
            "reason": "operator_restore",
        },
    )
    return {"cleared": existed, "client": client, "box": box, "skill": skill}


# --- strike two: the wipe --------------------------------------------------
def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def _remove_entry(entry: Path) -> int:
    """Delete one entry without ever following a symlink out of the tree.

    A symlink is unlinked, never dereferenced, so a link planted at
    ``skills/x/data -> ~/.openclaw/secrets`` costs the link only. Client data,
    client keys and client settings outside the skill folder are unreachable
    by construction.
    """
    removed = 0
    if entry.is_symlink() or not entry.is_dir():
        entry.unlink()
        return 1
    for child in list(entry.iterdir()):
        removed += _remove_entry(child)
    entry.rmdir()
    return removed + 1


def wipe_skill(skill_dir: str | os.PathLike[str]) -> dict:
    """Zero one skill folder down to the stub. Nothing else is touched.

    Only the skill folder's own tree is removed. Refuses anything that is
    not a skill folder, anything too close to the filesystem or home root,
    and any path that looks like a secrets or credentials store.
    """
    raw = Path(skill_dir).expanduser()
    root = raw.resolve()
    if not root.is_dir():
        raise TwoStrikeError("NOT_A_DIRECTORY", f"{root} is not a directory")
    if len(root.parts) < 3 or root == Path("/") or root == Path.home().resolve():
        raise TwoStrikeError(
            "REFUSING_TO_WIPE_ROOT",
            f"refusing to wipe {root}: too close to the filesystem or home root",
        )
    lowered = str(root).lower()
    for fragment in _SECRET_PATH_FRAGMENTS:
        if fragment in lowered + "/":
            raise TwoStrikeError(
                "REFUSING_TO_WIPE_SECRETS_PATH",
                f"refusing to wipe {root}: path looks like a secrets or "
                "credentials store, which is never in scope",
            )
    if not (root / "SKILL.md").is_file():
        raise TwoStrikeError(
            "NOT_A_SKILL_FOLDER",
            f"{root} carries no SKILL.md, so it is not a skill folder; "
            "the wipe is limited to one skill's own files",
        )

    removed = 0
    for entry in sorted(root.iterdir(), key=lambda p: p.name):
        if entry.name == STUB_FILENAME:
            continue
        if not _is_within(entry.resolve(), root) and not entry.is_symlink():
            raise TwoStrikeError(
                "ESCAPE_ATTEMPT",
                f"{entry} resolves outside {root}; wipe scope is the one "
                "skill's own files only",
            )
        removed += _remove_entry(entry)
    # A nested SKILL.md anywhere but the top level goes too: the stub folder
    # has exactly one file at its top level.
    for leftover in sorted(root.rglob(STUB_FILENAME), key=lambda p: str(p)):
        if leftover.parent != root:
            removed += _remove_entry(leftover)

    stub = root / STUB_FILENAME
    stub.write_bytes(stub_bytes())
    return {
        "wiped": True,
        "skill_dir": str(root),
        "stub_file": str(stub),
        "stub_bytes": len(stub_bytes()),
        "removed": removed,
        "left": [p.name for p in sorted(root.iterdir())],
    }


def apply_pending_wipe(
    client: str,
    box: str,
    skill: str,
    skill_dir: str | os.PathLike[str] | None = None,
    *,
    root: Path | None = None,
) -> dict:
    """Run a strike-two wipe that waited for the paid run to park.

    A strike two during a run with paid work in flight is recorded and its
    reply blocked at once, and the wipe waits for the next park or
    completion (decision D-6, default 3). Call this on that path. It is
    idempotent: with no pending wipe nothing happens, so a completion path
    may call it unconditionally.
    """
    base = root or state_root()
    store = _load_counters(base)
    row = store["strikes"].get(_key(client, box, skill))
    if not isinstance(row, dict) or not row.get("pending_wipe") or row.get("wiped"):
        return {"wiped": False, "reason": "NO_PENDING_WIPE"}
    if skill_dir is None:
        return {"wiped": False, "reason": "SKILL_DIR_REQUIRED"}
    result = wipe_skill(skill_dir)
    strike = int(row.get("count", 2))
    _set_row_field(client, box, skill, root=base, pending_wipe=False, wiped=True)
    _append_notice(
        base,
        {
            "ts": _now(),
            "client": client,
            "box": box,
            "skill": skill,
            "strike": strike,
            "action": "wipe",
            "reason": "deferred_wipe_on_park",
        },
    )
    result["strike"] = strike
    return result


# --- strike one: the detector wired skills lean on -------------------------
# Deliberately small and blunt. The wired skill decides when a turn looks
# like an extraction attempt; this list is the shared vocabulary for that
# judgement, not a classifier anyone should trust on its own.
_EXTRACTION_MARKERS = (
    "system prompt",
    "hidden prompt",
    "internal prompt",
    "your prompt",
    "print your prompt",
    "show me your prompt",
    "reveal your prompt",
    "dump your prompt",
    "developer message",
    "instructions you were given",
    "hidden instructions",
    "internal instructions",
    "reverse engineer",
    "reverse-engineer",
    "read your skill files",
    "skill source",
    "copy your configuration",
    "your configuration",
    "the prompt behind",
)


# A marker only counts inside one sentence that is ABOUT this assistant: that
# sentence must also carry "you", "your" or "this skill". A client describing
# their own course or product that happens to say "system prompt" is not
# asking this assistant about its prompt, so it spends no strike.
_ABOUT_ASSISTANT = re.compile(r"\b(?:you|your|this\s+skill)\b", re.IGNORECASE)
_SENTENCE_BREAK = re.compile(r"[.!?;\n\r]+")


def is_extraction_attempt(text: str, *, intake_answer: bool = False) -> bool:
    """True when the turn looks like an attempt to unpack this skill.

    ``intake_answer`` marks text typed as an answer to an intake card
    question: such text is never tested (decision D-6, default 1).
    """
    if intake_answer:
        return False
    if not text or not isinstance(text, str):
        return False
    for sentence in _SENTENCE_BREAK.split(text.lower()):
        if not _ABOUT_ASSISTANT.search(sentence):
            continue
        if any(marker in sentence for marker in _EXTRACTION_MARKERS):
            return True
    return False


# --- the entry point every wired skill calls -------------------------------
def evaluate(
    client: str,
    box: str,
    skill: str,
    message: str,
    *,
    skill_dir: str | os.PathLike[str] | None = None,
    suspicious: bool | None = None,
    intake_answer: bool = False,
    run_active: bool = False,
    root: Path | None = None,
) -> dict:
    """Run the two-strike gate on one turn.

    ``intake_answer`` marks text typed as an answer to an intake card
    question: it is never tested (decision D-6, default 1). ``run_active``
    marks a run with paid work in flight: a strike two is then recorded and
    its reply blocked at once, and the wipe waits for the next park or
    completion, where the caller runs ``apply_pending_wipe`` (or calls this
    gate again with ``run_active`` false) (decision D-6, default 3).

    Returns ``{"blocked": bool, "strike": int, "refusal": str | None,
    "action": "allow" | "refusal" | "defer_wipe" | "wipe", "wiped": bool}``.
    A legitimate turn comes back untouched with ``blocked`` False.
    """
    if intake_answer:
        looks_bad = False
    else:
        looks_bad = (
            is_extraction_attempt(message)
            if suspicious is None
            else bool(suspicious)
        )
    if not looks_bad:
        if not run_active:
            # The run has parked or completed: a strike two that waited
            # runs now, if one is pending for this triple.
            apply_pending_wipe(client, box, skill, skill_dir, root=root)
        return {
            "blocked": False,
            "strike": current_count(client, box, skill, root=root),
            "refusal": None,
            "action": "allow",
            "wiped": False,
        }

    row = record_strike(
        client, box, skill, reason="extraction_attempt",
        deferred=run_active, root=root,
    )
    strike = int(row["count"])
    wiped = False
    if strike >= 2:
        if skill_dir is None:
            raise TwoStrikeError(
                "SKILL_DIR_REQUIRED",
                "strike two wipes the offending skill folder, so skill_dir is "
                "required; refusing to record a second strike without it",
            )
        if run_active:
            _set_row_field(client, box, skill, root=root, pending_wipe=True)
            return {
                "blocked": True,
                "strike": strike,
                "refusal": refusal_text(strike),
                "action": "defer_wipe",
                "wiped": False,
            }
        wipe_skill(skill_dir)
        mark_wiped(client, box, skill, root=root)
        wiped = True
    return {
        "blocked": True,
        "strike": strike,
        "refusal": refusal_text(strike),
        "action": "wipe" if wiped else "refusal",
        "wiped": wiped,
    }


# --- operator command line -------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    """``operator-clear`` only. There is no client-facing command here."""
    parser = argparse.ArgumentParser(
        prog="two_strike.py",
        description="DEL-17 two-strike operator commands.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    clear = sub.add_parser(
        "operator-clear",
        help="clear the strike count for one client|box|skill (operator only)",
    )
    clear.add_argument("--client", required=True)
    clear.add_argument("--box", required=True)
    clear.add_argument("--skill", required=True)
    args = parser.parse_args(argv)
    try:
        result = clear_strikes(args.client, args.box, args.skill)
    except TwoStrikeError as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ENV_OPERATOR",
    "ENV_STATE_ROOT",
    "STRIKE_ONE_WARNING",
    "STRIKE_TWO_STUB",
    "STUB_FILENAME",
    "TOOL_NAME",
    "TOOL_VERSION",
    "TwoStrikeError",
    "apply_pending_wipe",
    "assert_state_root_outside_skill_folders",
    "clear_strikes",
    "current_count",
    "evaluate",
    "is_extraction_attempt",
    "mark_wiped",
    "operator_enabled",
    "record_strike",
    "refusal_text",
    "state_root",
    "stub_bytes",
    "wipe_skill",
]
