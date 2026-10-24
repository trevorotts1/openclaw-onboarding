#!/usr/bin/env python3
"""compat_guard.py - version-transition safeguards for on-disk records (T-39).

Contract basis: Purple-Billboard DATA-CONTRACTS.md section 10 ("Compatibility
records schema/protocol/reader-writer versions, migration checkpoint, writer
generation and config revision. Rollback compares the revision the upgrade
wrote; a newer client fix causes conflict/forward repair. Never roll back sent
effects, contact facts, consent/suppression, counters or unknown-send
reconciliation."). Python 3 standard library only.

One versioned JSON record on disk:

    {"version": 3, "writer_generation": 7, "data": {...}}

Four boring safeguards. Each one refuses rather than guesses:

  cas_update()      compare-and-swap on writer_generation. A writer holding a
                    stale generation is refused; it never overwrites a newer
                    client fix. The write is atomic (temp file + os.replace).

  migrate()         applies only migration steps ABOVE the record's version
                    and at or below the version this code knows. Re-running it
                    on a migrated record applies nothing and does not touch the
                    file, so the bytes are identical. Migrations that remove or
                    change a protected data key are refused before any write.

  assert_compatible()
                    a record NEWER than this code understands is refused with
                    NewerThanKnownError naming both versions. There is no
                    silent downgrade path.

  forward_repair()  the upgrade entry point. It reports: corrupt, newer than
                    known, missing, protected-state, or migrated. A corrupt
                    record is reported with its named problems and left
                    byte-for-byte untouched; nothing is repaired silently and
                    nothing is swallowed.

Protected data keys carry irreversible customer state (sent effects, contact
facts, consent/suppression, counters, unknown-send reconciliation). They are
never dropped or rewritten by a migration.

Assert-based self-check:  python3 -I compat_guard.py
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Tuple

# ── vocabulary ──────────────────────────────────────────────────────────────

PROTECTED_DATA_KEYS: Tuple[str, ...] = (
    "sent_effects",
    "contact_facts",
    "consent",
    "suppression",
    "counters",
    "unknown_sends",
)

_NEWLINE = "\n"


# ── errors (each names what it refused) ─────────────────────────────────────

class CompatError(ValueError):
    """Base class for every refusal in this module."""


class CorruptRecordError(CompatError):
    """The record is not a usable versioned record. `.problems` names why."""

    def __init__(self, problems: Iterable[str]):
        self.problems = tuple(problems)
        super().__init__("corrupt record: " + "; ".join(self.problems))


class NewerThanKnownError(CompatError):
    """On-disk version is newer than this code understands. Never downgrade."""

    def __init__(self, on_disk: int, known: int):
        self.on_disk = on_disk
        self.known = known
        super().__init__(
            "record version %r is newer than known version %r; refusing to downgrade"
            % (on_disk, known)
        )


class StaleWriteError(CompatError):
    """A writer holds an outdated generation; its write is refused."""

    def __init__(self, expected: int, actual: int):
        self.expected = expected
        self.actual = actual
        super().__init__(
            "stale writer: expected generation %r, on-disk generation %r is newer"
            % (expected, actual)
        )


class ProtectedStateError(CompatError):
    """A change would roll back irreversible customer state."""

    def __init__(self, keys: Iterable[str]):
        self.keys = tuple(keys)
        super().__init__(
            "refused: protected state would change: " + ", ".join(self.keys)
        )


# ── record IO ───────────────────────────────────────────────────────────────

def _validate(record: Any) -> List[str]:
    """Return named problems. Empty list means the record is usable."""
    if not isinstance(record, dict):
        return ["root: not a JSON object"]
    problems: List[str] = []
    version = record.get("version")
    if type(version) is not int or version < 1:
        problems.append("version: required int >= 1")
    generation = record.get("writer_generation")
    if type(generation) is not int or generation < 0:
        problems.append("writer_generation: required int >= 0")
    if not isinstance(record.get("data"), dict):
        problems.append("data: required JSON object")
    return problems


def canonical_bytes(record: Mapping[str, Any]) -> bytes:
    """The one deterministic encoding used for every write."""
    return (
        json.dumps(record, sort_keys=True, indent=2, ensure_ascii=False) + _NEWLINE
    ).encode("utf-8")


def read_record(path: os.PathLike | str) -> Dict[str, Any]:
    """Read and validate a record. Raises FileNotFoundError or CorruptRecordError."""
    raw = Path(path).read_text(encoding="utf-8")
    try:
        record = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CorruptRecordError(["root: not valid JSON (%s)" % exc.msg]) from exc
    problems = _validate(record)
    if problems:
        raise CorruptRecordError(problems)
    return record


def _write_record(path: os.PathLike | str, record: Mapping[str, Any]) -> None:
    """Atomic replace. A crash leaves either the old bytes or the new bytes."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=".compat-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(canonical_bytes(record))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def assert_compatible(record: Mapping[str, Any], known_version: int) -> None:
    """Refuse a record newer than this code understands. No silent downgrade."""
    on_disk = record.get("version")
    if type(on_disk) is not int:
        raise CorruptRecordError(["version: required int >= 1"])
    if on_disk > known_version:
        raise NewerThanKnownError(on_disk, known_version)


def _assert_protected_unchanged(before: Mapping[str, Any], after: Mapping[str, Any]) -> None:
    changed = [
        key for key in PROTECTED_DATA_KEYS
        if key in before and (key not in after or after[key] != before[key])
    ]
    if changed:
        raise ProtectedStateError(changed)


# ── compare-and-swap ────────────────────────────────────────────────────────

def cas_update(
    path: os.PathLike | str,
    expected_generation: int,
    mutate: Callable[[Dict[str, Any]], Dict[str, Any]],
    *,
    known_version: int,
) -> Dict[str, Any]:
    """Apply `mutate(data)` only if the caller holds the current generation."""
    record = read_record(path)
    assert_compatible(record, known_version)
    actual = record["writer_generation"]
    if actual != expected_generation:
        raise StaleWriteError(expected_generation, actual)
    new_data = mutate(copy.deepcopy(record["data"]))
    if not isinstance(new_data, dict):
        raise CompatError("mutate must return a dict, got %r" % type(new_data).__name__)
    _assert_protected_unchanged(record["data"], new_data)
    new_record = dict(record)
    new_record["writer_generation"] = actual + 1
    new_record["data"] = new_data
    _write_record(path, new_record)
    return new_record


# ── migration ───────────────────────────────────────────────────────────────

def migrate(
    path: os.PathLike | str,
    migrations: Mapping[int, Callable[[Dict[str, Any]], Dict[str, Any]]],
    *,
    known_version: int,
) -> Dict[str, Any]:
    """Apply the pending steps, if any. Re-running is a byte-identical no-op."""
    record = read_record(path)
    assert_compatible(record, known_version)
    current = record["version"]
    pending = sorted(step for step in migrations if current < step <= known_version)
    report: Dict[str, Any] = {
        "status": "ok",
        "from_version": current,
        "to_version": current,
        "applied": [],
        "noop": True,
        "bytes_written": False,
    }
    if not pending:
        return report

    new_record = dict(record)
    data = copy.deepcopy(record["data"])
    for step in pending:
        result = migrations[step](data)
        if not isinstance(result, dict):
            raise CompatError(
                "migration %r must return a dict, got %r"
                % (step, type(result).__name__)
            )
        data = result
    _assert_protected_unchanged(record["data"], data)
    new_record["version"] = pending[-1]
    new_record["data"] = data
    _write_record(path, new_record)
    report.update(
        to_version=pending[-1],
        applied=pending,
        noop=False,
        bytes_written=True,
    )
    return report


# ── forward repair (reports, never guesses) ─────────────────────────────────

def forward_repair(
    path: os.PathLike | str,
    migrations: Mapping[int, Callable[[Dict[str, Any]], Dict[str, Any]]],
    *,
    known_version: int,
) -> Dict[str, Any]:
    """Advance an old record or report why it cannot be advanced.

    Never raises for a record it refused, and never writes in those cases: the
    caller gets a status, the named issues, and wrote=False. Only status "ok"
    means the file was advanced (and report["bytes_written"] says whether bytes
    actually changed).
    """
    try:
        record = read_record(path)
    except FileNotFoundError:
        return {"status": "missing", "action": "none", "wrote": False}
    except CorruptRecordError as exc:
        return {
            "status": "corrupt",
            "action": "none",
            "wrote": False,
            "issues": list(exc.problems),
        }

    try:
        assert_compatible(record, known_version)
    except NewerThanKnownError as exc:
        return {
            "status": "newer_than_known",
            "action": "none",
            "wrote": False,
            "on_disk_version": exc.on_disk,
            "known_version": exc.known,
            "issues": [str(exc)],
        }

    try:
        report = migrate(path, migrations, known_version=known_version)
    except ProtectedStateError as exc:
        return {
            "status": "protected_state",
            "action": "none",
            "wrote": False,
            "issues": ["protected state would change: " + ", ".join(exc.keys)],
        }
    report["action"] = "migrated" if report["bytes_written"] else "none"
    report["wrote"] = report["bytes_written"]
    return report


# ── assert-based self-check (stdlib only) ───────────────────────────────────

def _selfcheck() -> int:
    import hashlib

    passed = 0

    def ok(cond: bool, label: str) -> None:
        nonlocal passed
        if not cond:
            raise AssertionError("FAIL: " + label)
        passed += 1

    with tempfile.TemporaryDirectory(prefix="compat-selfcheck-") as td:
        path = Path(td) / "record.json"
        _write_record(path, {"version": 1, "writer_generation": 0,
                             "data": {"consent": "granted", "note": "old"}})

        def add_note(data: Dict[str, Any]) -> Dict[str, Any]:
            data["note"] = "new"
            return data

        migrate(path, {2: add_note}, known_version=2)
        first = hashlib.sha256(path.read_bytes()).hexdigest()
        second_report = migrate(path, {2: add_note}, known_version=2)
        ok(second_report["noop"] is True, "second migration run is a no-op")
        ok(hashlib.sha256(path.read_bytes()).hexdigest() == first,
           "second migration run leaves identical bytes")

        updated = cas_update(path, 0, lambda data: {**data, "x": 1}, known_version=2)
        ok(updated["writer_generation"] == 1, "cas bumps the generation")
        try:
            cas_update(path, 0, lambda data: data, known_version=2)
        except StaleWriteError:
            pass
        else:
            raise AssertionError("FAIL: stale writer accepted")

        try:
            assert_compatible({"version": 9}, 2)
        except NewerThanKnownError:
            pass
        else:
            raise AssertionError("FAIL: newer record accepted")

        bad = Path(td) / "bad.json"
        bad.write_text('{"version": "x"}', encoding="utf-8")
        before = bad.read_bytes()
        report = forward_repair(bad, {}, known_version=2)
        ok(report["status"] == "corrupt" and report["wrote"] is False,
           "corrupt record reported, not written")
        ok(bad.read_bytes() == before, "corrupt record left untouched")

    print("compat_guard self-check: %d/%d PASS" % (passed, passed))
    return 0


if __name__ == "__main__":
    raise SystemExit(_selfcheck())
