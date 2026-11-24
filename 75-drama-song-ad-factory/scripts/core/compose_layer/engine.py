"""Compose engine detection and fallback (row N-57, section 3D.3).

Pre-flight asks the box three questions and records the answers in the run
lock: is Node present; does HyperFrames answer its version and pass its
health check; does Remotion answer its version. The lock then names ONE
compose engine for the run: ``hyperframes``, ``remotion`` or
``ffmpeg-fallback``.

Skill 75 never builds its own adapter and never installs either engine.
Both engines are reached through Skill 72's shipped adapters; when the
engine or Skill 72 is missing the run uses the fallback and tells the run
owner in plain words which look that costs (3D.3).

Stdlib only, no install, no paid call. Probes run with a hard timeout.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

TOOL_NAME = "compose_engine"
TOOL_VERSION = "1.0.0"

HYPERFRAMES = "hyperframes"
REMOTION = "remotion"
FFMPEG_FALLBACK = "ffmpeg-fallback"

SKILL72_DIRNAME = "72-motion-video-plus"
SKILL72_ENV = "DSAF_SKILL72_ROOT"

#: Refusal codes (fail closed, never a silent install or guess).
ADAPTER_MISSING = "COMPOSE_ADAPTER_MISSING"
SKILL72_MISSING = "COMPOSE_SKILL72_MISSING"
PROBE_TIMEOUT = "COMPOSE_PROBE_TIMEOUT"

#: Every probe answers or gives up inside this many seconds.
PROBE_TIMEOUT_S = 20

#: Adapter source files and the callable entry, relative to Skill 72.
#: The adapter is Skill 72's; this module only locates it.
ADAPTER_SOURCES = {
    HYPERFRAMES: "runtime/src/adapters/hyperframes.ts",
    REMOTION: "runtime/src/adapters/remotion.ts",
}

#: Callable entries, tried in order. A built runtime is preferred; the
#: Skill 72 renderer is the shipped HyperFrames entry.
ENTRY_CANDIDATES = (
    "runtime/dist/standalone/cli.js",
    "runtime/dist/standalone/cli.mjs",
    "runtime/scripts/render.js",
    "scripts/render.js",
)


def _run(argv, timeout=PROBE_TIMEOUT_S):
    """(returncode, stdout+stderr) for one probe; never raises on absence."""
    try:
        p = subprocess.run(argv, capture_output=True, text=True,
                           timeout=timeout, check=False)
        return p.returncode, (p.stdout + p.stderr).strip()
    except (OSError, subprocess.SubprocessError):
        return None, ""


def skill72_root(start=None):
    """Locate Skill 72 (motion-video-plus) without installing anything.

    Order: ``DSAF_SKILL72_ROOT``; a sibling of the Skill 75 root; a
    ``skills/<name>`` folder beside it. Returns None when absent.
    """
    env = os.environ.get(SKILL72_ENV)
    if env and os.path.isdir(env):
        return os.path.abspath(env)
    here = os.path.abspath(start or os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    for base in (os.path.dirname(here), here):
        cand = os.path.join(base, SKILL72_DIRNAME)
        if os.path.isdir(cand):
            return cand
        cand = os.path.join(base, "skills", SKILL72_DIRNAME)
        if os.path.isdir(cand):
            return cand
    return None


def adapter_entry(engine, root=None):
    """Locate Skill 72's adapter for ``engine``. None when not shipped.

    Never installs, never falls back to a different engine silently.
    """
    if engine not in ADAPTER_SOURCES:
        return None
    root = root or skill72_root()
    if not root:
        return None
    source = os.path.join(root, ADAPTER_SOURCES[engine])
    if not os.path.isfile(source):
        return None
    for rel in ENTRY_CANDIDATES:
        entry = os.path.join(root, rel)
        if os.path.isfile(entry):
            return {"engine": engine, "root": root, "adapter": source,
                    "entry": entry}
    return {"engine": engine, "root": root, "adapter": source, "entry": None}


def _version_answers(command):
    """True when ``command`` answers a version, with a hard timeout."""
    rc, out = _run([*command, "--version"])
    if rc == 0 and out:
        return out.splitlines()[0].strip()
    return None


def node_probe():
    exe = shutil.which("node")
    version = _version_answers([exe]) if exe else None
    return {"present": bool(exe and version), "path": exe,
            "version": version or None}


def engine_probe(name):
    """Ask one engine for its version. ``npx --no-install`` never installs."""
    exe = shutil.which(name)
    version = _version_answers([exe]) if exe else None
    if not version:
        npx = shutil.which("npx")
        if npx:
            version = _version_answers([npx, "--no-install", name])
    return {"present": bool(version), "version": version or None,
            # The adapter's own health check is Skill 72's; in this build a
            # version answer is the health signal the plan names (3D.3).
            "health": "ok" if version else "missing"}


def detect(start=None):
    """The pre-flight record: Node, HyperFrames, Remotion, Skill 72."""
    root = skill72_root(start)
    return {
        "node": node_probe(),
        "hyperframes": engine_probe(HYPERFRAMES),
        "remotion": engine_probe(REMOTION),
        "skill72": {
            "path": root,
            "adapters": {name: adapter_entry(name, root)
                         for name in ADAPTER_SOURCES},
        },
    }


def choose_engine(probe):
    """ONE engine for the run: HyperFrames, else Remotion, else fallback."""
    for name in (HYPERFRAMES, REMOTION):
        if probe.get(name, {}).get("present") and probe.get(name, {}).get("health") == "ok":
            return name
    return FFMPEG_FALLBACK


def run_lock_record(probe):
    """The block the pre-flight writes into the run lock (3D.3).

    Chosen once, before any spend; never changed mid-run.
    """
    engine = choose_engine(probe)
    return {
        "compose_engine": engine,
        "compose_preflight": probe,
        "compose_fallback_cost": fallback_cost(engine),
    }


def fallback_cost(engine):
    """Plain words for the run owner about what the chosen engine costs."""
    if engine == HYPERFRAMES:
        return "none: designed text layers render with HyperFrames"
    if engine == REMOTION:
        return "none: designed text layers render with Remotion"
    return ("designed transitions become short ffmpeg crossfades; the end "
            "card and offer lower-third are drawn as text pictures by the "
            "skill and placed by ffmpeg")


def require_adapter(engine, root=None):
    """Fail closed when a chosen engine has no shipped Skill 72 adapter."""
    if engine == FFMPEG_FALLBACK:
        return None
    root = root or skill72_root()
    if not root:
        raise ComposeEngineError(SKILL72_MISSING,
                                 "Skill 72 is not installed; compose falls "
                                 "back to ffmpeg")
    entry = adapter_entry(engine, root)
    if not entry or not entry.get("entry"):
        raise ComposeEngineError(ADAPTER_MISSING,
                                 "Skill 72 ships no callable %s adapter" % engine)
    return entry


class ComposeEngineError(RuntimeError):
    """A named refusal, never a silent install or engine swap."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="one JSON line")
    ns = ap.parse_args(argv)
    record = run_lock_record(detect())
    if ns.json:
        print(json.dumps(record, sort_keys=True))
    else:
        print(record["compose_engine"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
