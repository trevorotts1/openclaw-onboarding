#!/usr/bin/env python3
"""RF-014 routing safety switch: the mode store's writer, the tripwire, the event log.

Lives beside decision-engine.py (not inside decision_engine/, whose contract is
"no state writes"). Stdlib only. Never creates a box's OpenClaw root, never touches openclaw.json,
never reads or writes a key. Every writer here is the ONE place a routing-mode
change happens; scripts/decision-engine-mode.py (the existing referee) calls it.

THE STORE (unchanged shape): $OC_ROOT/decision-engine-mode.conf, ONE word on the
first line. Every reader (plugin, bridge, Command Center, verify-routing.sh,
fleet_refresh_runner, ceo_execution_policy) reads the FIRST line or word only, so
a marker on line 2 is invisible to all of them.

WHO CHOSE THE MODE (this is what "never flips an explicit choice" keys on):
  env    $OPENCLAW_DECISION_ENGINE_MODE is set          -> owner/automation pin
  file   file exists, no tripwire marker on line 2      -> owner pin (a hand-written
                                                           file from before RF-014
                                                           counts: it is explicit)
  trip   file exists, line 2 starts "# set-by: tripwire" -> the box flipped itself
  default no file, no env                                -> release default `auto`
The tripwire only ever acts on `default`. A pinned box (even pinned to `auto` or
`model`) is never moved; a tripped box stays `legacy` until the owner runs
`set <mode>` (pin) or `reset` (back to the release default, safety net re-armed).

FILES (all beside the mode store):
  routing-health.json     consecutive JEV routing failures + last ok/failure
  routing-tripwire.flag   one JSON line, present ONLY while tripped (health check
                          and Rescue Rangers read it; same shape as
                          rr-intake-auth.flag: {"class","ts",...})
  routing-events.jsonl    append-only: tripwire_tripped, mode_set, mode_reset,
                          model_mode_fallback_legacy. No task text, no secrets.
  routing-tripwire.conf   optional: one integer, failures in a row before the flip
                          (env $OPENCLAW_ROUTING_TRIPWIRE_FAILURES wins; default 5)
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path

try:  # POSIX only; the fleet is Mac + Linux. Without it, writes are unlocked.
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

STORE = "decision-engine-mode.conf"
ENV = "OPENCLAW_DECISION_ENGINE_MODE"
RELEASE_DEFAULT = "auto"
HEALTH = "routing-health.json"
FLAG = "routing-tripwire.flag"
EVENTS = "routing-events.jsonl"
THRESHOLD_STORE = "routing-tripwire.conf"
THRESHOLD_ENV = "OPENCLAW_ROUTING_TRIPWIRE_FAILURES"
NO_RECORD_ENV = "OPENCLAW_ROUTING_NO_RECORD"  # health probes set this: a health check changes nothing
DEFAULT_THRESHOLD = 5
TRIP_MARK = "# set-by: tripwire"
TRIP_TARGET = "legacy"
EVENTS_MAX_BYTES = 512 * 1024  # ponytail: one rotated generation, add real rotation when asked


# Mirror of decision_engine.modes.MODES for the one case the canonical module cannot
# load (the very failure the tripwire exists for). Parity is locked by test.
_FALLBACK_MODES = ("auto", "shadow", "legacy", "off", "model")


def mode_names():
    try:
        from decision_engine.modes import MODES  # the ONE mode authority
        return MODES
    except Exception:  # noqa: BLE001
        return _FALLBACK_MODES


def oc_root(oc_config=None) -> Path:
    """Same root the plugin reads: $OC_CONFIG (dir or the openclaw.json inside), else
    /data/.openclaw (VPS), else ~/.openclaw."""
    raw = oc_config or os.environ.get("OC_CONFIG")
    if raw:
        p = Path(raw)
        return p.parent if (p.is_file() or p.suffix == ".json") else p
    d = Path("/data/.openclaw")
    return d if d.is_dir() else Path.home() / ".openclaw"


def _now():
    t = time.time()
    return t, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def _clean(text, limit=80):
    """One printable line, so a caller-supplied reason can never break the store."""
    out = "".join(c if c.isprintable() else " " for c in str(text or ""))
    return " ".join(out.split())[:limit]


def _atomic(path: Path, text: str) -> None:
    tmp = path.with_name(".%s.%d.tmp" % (path.name, os.getpid()))
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(str(tmp), str(path))
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def _read_json(path: Path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _unlink(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


@contextmanager
def _lock(root: Path):
    handle = None
    try:
        if fcntl is not None and root.is_dir():
            handle = open(str(root / ".routing.lock"), "a")
            fcntl.flock(handle, fcntl.LOCK_EX)
        yield
    finally:
        if handle is not None:
            handle.close()


def resolve_mode(root) -> dict:
    """{"mode","source","pinned","tripped"}. Does not validate the word."""
    env = os.environ.get(ENV)
    if env is not None and env.strip():
        return {"mode": env.strip(), "source": "env", "pinned": True, "tripped": False}
    store = Path(root) / STORE
    if store.is_file():
        try:
            raw = store.read_text(encoding="utf-8", errors="replace")
        except OSError:
            raw = ""
        lines = raw.splitlines() or [""]
        tripped = any(ln.startswith(TRIP_MARK) for ln in lines[1:])
        return {"mode": lines[0].strip(), "source": "file",
                "pinned": not tripped, "tripped": tripped}
    return {"mode": RELEASE_DEFAULT, "source": "default", "pinned": False, "tripped": False}


def threshold(root) -> int:
    raw = os.environ.get(THRESHOLD_ENV) or ""
    if not raw.strip():
        try:
            raw = (Path(root) / THRESHOLD_STORE).read_text(encoding="utf-8").splitlines()[0]
        except (OSError, IndexError):
            raw = ""
    try:
        n = int(raw.strip())
    except ValueError:
        return DEFAULT_THRESHOLD
    return n if n >= 1 else DEFAULT_THRESHOLD


def log_event(root, event, dedupe_s=0, **fields):
    """Append one JSON line. Never raises; never creates the OC root. With
    dedupe_s, an identical (event, reason) inside that window is skipped."""
    path = Path(root) / EVENTS
    epoch, iso = _now()
    rec = dict(fields, event=event, ts=iso, epoch=int(epoch))
    try:
        if path.is_file():
            if dedupe_s:
                with open(str(path), "rb") as fh:
                    fh.seek(max(0, path.stat().st_size - 4096))
                    tail = fh.read().decode("utf-8", "replace").splitlines()
                last = json.loads(tail[-1]) if tail else {}
                if (last.get("event") == event and last.get("reason") == fields.get("reason")
                        and epoch - float(last.get("epoch", 0)) < dedupe_s):
                    return None
            if path.stat().st_size > EVENTS_MAX_BYTES:
                os.replace(str(path), str(path) + ".1")
        with open(str(path), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
    except (OSError, ValueError):
        return None
    return rec


def _last_event(root):
    path = Path(root) / EVENTS
    try:
        with open(str(path), "rb") as fh:
            fh.seek(max(0, path.stat().st_size - 4096))
            tail = fh.read().decode("utf-8", "replace").splitlines()
        return json.loads(tail[-1]) if tail else None
    except (OSError, ValueError):
        return None


def _clear_health(root: Path) -> None:
    _unlink(root / HEALTH)
    _unlink(root / FLAG)


def _alive(pid) -> bool:
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except (PermissionError, ValueError, TypeError, OverflowError):
        return True  # exists (not ours) or unparseable: do not blame it
    return True


def begin(root) -> None:
    """Mark one evaluation as started. If the PREVIOUS one never finished and its
    process is gone (killed by a caller timeout, crashed), that is one routing failure:
    the bridge cannot see its own kill, so the next start counts it. Never raises."""
    root = Path(root)
    try:
        if not root.is_dir() or (os.environ.get(NO_RECORD_ENV) or "").strip() not in ("", "0"):
            return
        pend = _read_json(root / HEALTH).get("pending")
        if isinstance(pend, dict) and pend.get("pid") != os.getpid() and not _alive(pend.get("pid")):
            record_outcome(root, False, "evaluation_did_not_finish")
        with _lock(root):
            health = _read_json(root / HEALTH)
            health["pending"] = {"pid": os.getpid(), "at": _now()[1]}
            _atomic(root / HEALTH, json.dumps(health, sort_keys=True) + "\n")
    except Exception:  # noqa: BLE001 -- the tripwire must never break an evaluation
        pass


def record_outcome(root, ok, reason="") -> dict:
    """Count one JEV routing outcome. N failures in a row on an UNPINNED box flip it
    to legacy. Success resets the count. Pinned boxes are counted, never moved."""
    root = Path(root)
    if (os.environ.get(NO_RECORD_ENV) or "").strip() not in ("", "0"):
        return {"recorded": False, "skipped": "recording_disabled", "tripped": False}
    if not root.is_dir():
        return {"recorded": False, "skipped": "no_oc_root", "tripped": False}
    if ok and not (root / HEALTH).is_file():
        return {"recorded": False, "skipped": "nothing_to_reset", "tripped": False}
    with _lock(root):
        health = _read_json(root / HEALTH)
        health.pop("pending", None)
        epoch, iso = _now()
        if ok:
            health.update(consecutiveFailures=0, lastOkAt=iso)
        else:
            health.update(consecutiveFailures=int(health.get("consecutiveFailures", 0)) + 1,
                          lastFailureAt=iso, lastFailureReason=_clean(reason))
        count, limit = health["consecutiveFailures"], threshold(root)
        res = {"recorded": True, "consecutiveFailures": count, "threshold": limit,
               "tripped": False}
        if not ok and count >= limit:
            cur = resolve_mode(root)
            if cur["source"] != "default":
                res["skipped"] = "already_tripped" if cur["tripped"] else "mode_pinned"
            else:
                why = _clean(reason)
                _atomic(root / STORE, (
                    "%s\n%s %s after %d consecutive routing failures (last: %s)\n"
                    "# owner: routing-mode.sh set auto|model (pin) or routing-mode.sh reset (re-arm)\n"
                    % (TRIP_TARGET, TRIP_MARK, iso, count, why or "unknown")))
                _atomic(root / FLAG, json.dumps({
                    "class": "ROUTING_TRIPWIRE_TRIPPED", "ts": iso, "failures": count,
                    "threshold": limit, "lastReason": why, "flippedTo": TRIP_TARGET,
                    "remedy": "owner: routing-mode.sh set auto|model, or routing-mode.sh reset"},
                    sort_keys=True) + "\n")
                log_event(root, "tripwire_tripped", failures=count, threshold=limit,
                          reason=why, flippedTo=TRIP_TARGET)
                res["tripped"] = True
        _atomic(root / HEALTH, json.dumps(health, sort_keys=True) + "\n")
    return res


def set_mode(root, mode) -> dict:
    """Owner pin. Validates against the canonical modes; clears tripwire state."""
    root = Path(root)
    if mode not in mode_names():
        raise ValueError("unknown mode %r (expected one of %s)" % (mode, "|".join(mode_names())))
    if not root.is_dir():
        raise FileNotFoundError("OpenClaw root not found: %s" % root)
    with _lock(root):
        before = resolve_mode(root)
        _atomic(root / STORE, mode + "\n")
        _clear_health(root)
    log_event(root, "mode_set", mode=mode, previous=before["mode"], by="owner")
    return {"mode": mode, "previous": before["mode"], "envOverrides": bool(
        (os.environ.get(ENV) or "").strip())}


def reset(root) -> dict:
    """Back to the release default (`auto`), safety net re-armed. Documented in the
    store's own CORRUPT message as the way to accept the release default."""
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError("OpenClaw root not found: %s" % root)
    with _lock(root):
        before = resolve_mode(root)
        _unlink(root / STORE)
        _clear_health(root)
    log_event(root, "mode_reset", previous=before["mode"], by="owner")
    return {"mode": RELEASE_DEFAULT, "previous": before["mode"], "envOverrides": bool(
        (os.environ.get(ENV) or "").strip())}


def status(root) -> dict:
    root = Path(root)
    cur = resolve_mode(root)
    health = _read_json(root / HEALTH)
    flag = _read_json(root / FLAG)
    net = "tripped" if cur["tripped"] else ("pinned" if cur["pinned"] else "armed")
    out = {
        "root": str(root), "mode": cur["mode"], "source": cur["source"],
        "valid": cur["mode"] in mode_names(), "safetyNet": net,
        "consecutiveFailures": int(health.get("consecutiveFailures", 0)),
        "threshold": threshold(root), "lastFailureAt": health.get("lastFailureAt"),
        "lastFailureReason": health.get("lastFailureReason"),
        "flag": flag or None, "lastEvent": _last_event(root),
    }
    if cur["mode"] == "model":
        try:
            from model_route import resolve_default_model
            out["defaultModel"] = resolve_default_model(root / "openclaw.json")
        except Exception:  # noqa: BLE001 -- status must always answer
            out["defaultModel"] = None
    return out
