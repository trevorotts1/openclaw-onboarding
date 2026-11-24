"""Compose render wrapper (row N-109, rules B1 to B3 of section 3D.8).

No agent starts HyperFrames, Remotion or a browser directly. This wrapper:

- starts the render in its own process group (``start_new_session``);
- gives it a fresh temp profile folder for that one render, tagged with the
  run id and render id (the tags also ride the command line through ``env``);
- on ANY exit -- success, error, crash or timeout -- kills the whole process
  group and deletes the folder, in a ``finally`` and on the wrapper's own
  termination signals;
- enforces a hard timeout per render: 3 minutes for an end card or a
  transition, 10 minutes for a caption layer (overridable from the run's
  time-budget file);
- enforces the browser cap: about one browser per 1.5 GB of free memory,
  never more than 6 per box, reduced by one only while a *fresh* reading
  (never older than 5 minutes) shows memory pressure above 85 percent and
  restored on the next fresh reading at or below 85 percent. A render that
  would exceed the cap waits; a running render is never killed for memory.

Stdlib only. Nothing here installs a tool or contacts a provider.
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

TOOL_NAME = "compose_render_wrapper"
TOOL_VERSION = "1.0.0"

#: Tag carried by every wrapper process, its command line and its folder.
WRAPPER_TAG = "dsaf-compose"
TAG_ENV = "DSAF_COMPOSE_TAG"
RUN_ENV = "DSAF_COMPOSE_RUN_ID"
RENDER_ENV = "DSAF_COMPOSE_RENDER_ID"

#: Hard timeouts in seconds (rule B2). The run's time-budget file may
#: override any key; values here are the plan's defaults.
TIME_BUDGETS = {
    "end_card": 180,
    "transition": 180,
    "caption_layer": 600,
    # A piece render is a short master section, not a card; one render of a
    # 3-minute final measured 4.6 minutes, so 10 minutes is the floor.
    "piece": 600,
}

#: Browser cap (rule B3).
MAX_BROWSERS = 6
GB_PER_BROWSER = 1.5
PRESSURE_LIMIT_PCT = 85.0
MAX_READING_AGE_S = 300.0

#: The one server-side shared tools path (row N-111, section 3D.9). Only
#: programs live here; a per-render temp profile folder never does.
SHARED_ROOT = os.environ.get("DSAF_SHARED_VIDEO_TOOLS",
                             "/opt/shared-video-tools")

#: Named failures (fail closed, always report what happened).
RENDER_TIMEOUT = "COMPOSE_RENDER_TIMEOUT"
RENDER_FAILED = "COMPOSE_RENDER_FAILED"
MEMORY_UNREADABLE = "COMPOSE_MEMORY_UNREADABLE"
STALE_MEMORY_READING = "COMPOSE_MEMORY_STALE"
BROWSER_CAP_REACHED = "COMPOSE_BROWSER_CAP_REACHED"
TEMP_UNDER_SHARED = "COMPOSE_TEMP_UNDER_SHARED_TOOLS"


class ComposeRenderError(RuntimeError):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message


def time_budget(kind, budgets=None):
    """Seconds for one render kind; the time-budget file wins when present."""
    table = dict(TIME_BUDGETS)
    if budgets:
        for key, value in budgets.items():
            if key in table and isinstance(value, (int, float)) and value > 0:
                table[key] = value
    if kind not in table:
        raise ComposeRenderError(RENDER_FAILED, "unknown render kind %r" % kind)
    return float(table[kind])


# ── memory reading (fresh, timestamped: never a stale number) ───────────────
def _darwin_memory():
    sysctl = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True,
                            text=True, timeout=10, check=False)
    vm = subprocess.run(["vm_stat"], capture_output=True, text=True,
                        timeout=10, check=False)
    if sysctl.returncode != 0 or vm.returncode != 0:
        return None
    total = int(sysctl.stdout.strip())
    page = int(re.search(r"page size of (\d+)", vm.stdout).group(1))
    pages = sum(int(re.search(r"Pages %s:\s+(\d+)" % key, vm.stdout).group(1))
                for key in ("free", "inactive", "speculative"))
    return pages * page, total


def _linux_memory():
    values = {}
    with open("/proc/meminfo", "r", encoding="utf-8") as handle:
        for line in handle:
            key, _, rest = line.partition(":")
            if key in ("MemAvailable", "MemTotal"):
                values[key] = int(rest.split()[0]) * 1024
    return values["MemAvailable"], values["MemTotal"]


def memory_reading(now=None):
    """Fresh reading: free GB, total GB, pressure percent, sample time."""
    try:
        if sys.platform == "darwin":
            pair = _darwin_memory()
        else:
            pair = _linux_memory()
    except (OSError, ValueError, AttributeError, subprocess.SubprocessError):
        pair = None
    if not pair or not pair[1]:
        return {"available": False, "sampled_at": now or time.time(),
                "error": MEMORY_UNREADABLE}
    free_bytes, total_bytes = pair
    free_gb = free_bytes / float(1024 ** 3)
    return {
        "available": True,
        "free_gb": round(free_gb, 3),
        "total_gb": round(total_bytes / float(1024 ** 3), 3),
        "pressure_pct": round(100.0 * (1.0 - free_bytes / float(total_bytes)), 2),
        "sampled_at": now or time.time(),
    }


def reading_is_fresh(reading, now=None, max_age_s=MAX_READING_AGE_S):
    if not reading or not reading.get("available"):
        return False
    stamp = reading.get("sampled_at")
    if not isinstance(stamp, (int, float)):
        return False
    return (now or time.time()) - stamp <= max_age_s


def browser_cap(reading, held_cap=None, now=None):
    """Rule B3 cap from one fresh reading; stale or unreadable refuses.

    ``held_cap`` carries the cap held while pressure stays above 85 percent,
    so the reduction is not lost between readings. A reading at or below
    85 percent restores the full cap.
    """
    if not reading_is_fresh(reading, now):
        raise ComposeRenderError(STALE_MEMORY_READING,
                                 "memory reading is missing or older than "
                                 "%d seconds" % MAX_READING_AGE_S)
    base = int(reading["free_gb"] // GB_PER_BROWSER)
    base = max(1, min(MAX_BROWSERS, base))
    if reading["pressure_pct"] > PRESSURE_LIMIT_PCT:
        reduced = max(1, base - 1)
        return min(reduced, held_cap) if held_cap else reduced
    return base


# ── wrapper ─────────────────────────────────────────────────────────────────
_LIVE = {}          # render_id -> (pgid, profile_dir)
_HANDLERS_INSTALLED = False


def _safe(text):
    return re.sub(r"[^A-Za-z0-9._-]+", "-", str(text))[:60] or "render"


def profile_dir(tmp_root, run_id, render_id):
    """Per-render tagged temp profile folder (rule B1).

    A temp profile folder is never created under the shared tools path
    (row N-111): client data and per-render profile state stay in the
    client's own container.
    """
    target = os.path.abspath(tmp_root)
    shared = os.path.abspath(SHARED_ROOT)
    if target == shared or target.startswith(shared + os.sep):
        raise ComposeRenderError(
            TEMP_UNDER_SHARED,
            "a temp profile folder is never created under %s" % shared)
    os.makedirs(tmp_root, exist_ok=True)
    name = "-".join((WRAPPER_TAG, _safe(run_id), _safe(render_id),
                     next(tempfile._get_candidate_names())))
    path = os.path.join(tmp_root, name)
    os.makedirs(path, exist_ok=False)
    return path


def tagged_argv(argv, run_id, render_id):
    """Tags on the command line without changing the adapter's own flags."""
    env_exe = shutil.which("env") or "/usr/bin/env"
    return [env_exe,
            "%s=%s" % (TAG_ENV, WRAPPER_TAG),
            "%s=%s" % (RUN_ENV, run_id),
            "%s=%s" % (RENDER_ENV, render_id),
            *argv]


def _kill_group(pgid):
    """True only when the process group is gone afterwards.

    No group means nothing was left behind, so that is true too. A group
    already gone is true; any other OS error is reported as not killed
    rather than guessed.
    """
    if not pgid:
        return True
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            return True
        except OSError:
            return False
        if sig == signal.SIGTERM:
            time.sleep(0.2)
    try:
        os.killpg(pgid, 0)          # signal 0 only checks existence
    except ProcessLookupError:
        return True
    except OSError:
        return False
    return False


def _cleanup(render_id, folder=None):
    """(group_gone, folder_gone) as observed, never assumed."""
    entry = _LIVE.pop(render_id, None)
    pgid = entry[0] if entry else None
    folder = entry[1] if entry else folder
    group_gone = _kill_group(pgid)
    if folder:
        shutil.rmtree(folder, ignore_errors=True)
    return group_gone, not (folder and os.path.exists(folder))


def _on_signal(signum, frame):  # pragma: no cover - signal path
    for render_id in list(_LIVE):
        _cleanup(render_id)
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)


def _install_handlers():
    global _HANDLERS_INSTALLED
    if _HANDLERS_INSTALLED:
        return
    for name in ("SIGINT", "SIGTERM", "SIGHUP"):
        sig = getattr(signal, name, None)
        if sig is not None:
            try:
                signal.signal(sig, _on_signal)
            except (ValueError, OSError):
                pass
    _HANDLERS_INSTALLED = True


def run_render(kind, argv, run_id, render_id, tmp_root,
               budgets=None, cwd=None, env=None, popen=None):
    """Run one compose render and return its receipt.

    The receipt never claims a cleanup it did not perform.
    """
    timeout = time_budget(kind, budgets)
    folder = profile_dir(tmp_root, run_id, render_id)
    child_env = dict(os.environ if env is None else env)
    child_env[TAG_ENV] = WRAPPER_TAG
    child_env[RUN_ENV] = str(run_id)
    child_env[RENDER_ENV] = str(render_id)
    child_env.setdefault("TMPDIR", folder)          # browser writes here
    launched = tagged_argv(list(argv), run_id, render_id)
    starter = popen or subprocess.Popen
    started = time.time()
    proc = None
    timed_out = False
    output = b""
    try:
        _install_handlers()
        proc = starter(launched, cwd=cwd, env=child_env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       start_new_session=True)
        try:
            pgid = os.getpgid(proc.pid)
        except (ProcessLookupError, OSError):
            pgid = None
        _LIVE[str(render_id)] = (pgid, folder)
        try:
            output, _ = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_group(pgid)
            try:
                output, _ = proc.communicate(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                output, _ = proc.communicate()
        exit_code = None if timed_out else proc.returncode
    finally:
        group_gone, folder_gone = _cleanup(str(render_id), folder)
    text = (output or b"").decode("utf-8", "replace")[-8192:]
    status = "timeout" if timed_out else ("ok" if exit_code == 0 else "failed")
    receipt = {
        "render_id": str(render_id),
        "run_id": str(run_id),
        "kind": kind,
        "status": status,
        "exit_code": exit_code,
        "timeout_s": timeout,
        "duration_s": round(time.time() - started, 2),
        "group_killed": group_gone,
        "profile_deleted": folder_gone,
        "output_tail": text,
    }
    if timed_out:
        receipt["code"] = RENDER_TIMEOUT
    elif exit_code != 0:
        receipt["code"] = RENDER_FAILED
    return receipt


# ── browser slots (rule B3: a render that would exceed the cap waits) ───────
class BrowserSlots:
    """Counted browser starts on one box, capped by a fresh memory reading.

    The count is a list of living holder pids under an flock, so two
    processes cannot both read 0 and both take the last slot -- the exact
    way the cap was exceeded before. A holder that died without releasing
    is pruned when the file is next read, so a crashed render cannot wedge
    the box.
    """

    def __init__(self, lock_dir):
        self.path = os.path.join(lock_dir, WRAPPER_TAG + "-browsers.json")
        self.lock_path = self.path + ".lock"
        os.makedirs(lock_dir, exist_ok=True)

    @contextlib.contextmanager
    def _locked(self):
        handle = open(self.lock_path, "a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()

    @staticmethod
    def _alive(pid):
        try:
            os.kill(int(pid), 0)
            return True
        except ProcessLookupError:
            return False
        except (OSError, ValueError):
            return True          # cannot prove it is gone; do not free it

    def _holders(self):
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            pids = [int(p) for p in data.get("pids", [])]
        except (OSError, ValueError, TypeError):
            return []
        return [p for p in pids if self._alive(p)]

    def _write(self, pids):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump({"pids": pids, "tag": WRAPPER_TAG}, handle)
        os.replace(tmp, self.path)

    @contextlib.contextmanager
    def acquire(self, reader=memory_reading, wait_s=0.0, poll_s=2.0):
        deadline = time.time() + max(0.0, wait_s)
        me = os.getpid()
        while True:
            reading = reader()
            cap = browser_cap(reading)
            with self._locked():
                holders = self._holders()
                if len(holders) < cap:
                    holders.append(me)
                    self._write(holders)
                    break
            if time.time() >= deadline:
                raise ComposeRenderError(
                    BROWSER_CAP_REACHED,
                    "browser cap %d reached; this render waits" % cap)
            time.sleep(poll_s)
        try:
            yield cap
        finally:
            with self._locked():
                self._write([p for p in self._holders() if p != me])
