#!/usr/bin/env python3
"""_harness.py — shared plumbing for the W10 acceptance scenario runners.

One runner per acceptance row under tests/w10-canary/scenarios/. Each runner
takes the tree under test as an argument, prints one check line per assertion,
and exits 0 only when every assertion held. Stdlib only, no pytest, no network,
no paid provider, no channel send.

Exit codes (identical for every runner):
    0  every assertion held
    1  at least one assertion failed
    2  tooling: the tree under test is missing the modules the row needs
    4  blocked: the remaining assertion needs a live provider/channel artifact
       (printed as BLOCKED_A11 — a distinct code, never a fake pass)
"""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

#: repo-relative location of the Skill 75 core modules
CORE_REL = Path("75-drama-song-ad-factory") / "scripts" / "core"
#: repo root, derived from this file (tests/w10-canary/scenarios/_harness.py)
REPO_ROOT = Path(__file__).resolve().parents[3]
SCRATCH_PREFIX = "skill75-repair-SFR-007-scenario-"


class Checks(object):
    """Collects and prints one line per assertion for one acceptance row."""

    def __init__(self, row, title):
        self.row = row
        self.title = title
        self.results = []

    def check(self, name, ok, detail=""):
        ok = bool(ok)
        self.results.append({"name": name, "ok": ok, "detail": str(detail)[:400]})
        print("  [%s] %s%s" % ("PASS" if ok else "FAIL", name,
                               (" — " + str(detail)[:300]) if detail else ""))
        return ok

    def passed(self):
        return [r for r in self.results if r["ok"]]

    def failed(self):
        return [r for r in self.results if not r["ok"]]

    def summary(self):
        """Print the tally line; return 0 when nothing failed."""
        ok, total = len(self.passed()), len(self.results)
        names = [r["name"] for r in self.failed()]
        print("%s: %d/%d checks passed%s"
              % (self.row, ok, total, ("" if not names
                                       else "; FAIL: " + ", ".join(names))))
        return 0 if not names else 1

    def finish(self, out=None):
        code = self.summary()
        if out:
            p = Path(out)
            p.mkdir(parents=True, exist_ok=True)
            (p / ("%s.scenario.json" % self.row.lower())).write_text(
                json.dumps({"schema": "blackceo.skill75.scenario-receipt/v1",
                            "row": self.row, "title": self.title,
                            "checks": self.results,
                            "passed": len(self.passed()),
                            "total": len(self.results),
                            "claims_now": "none"},
                           indent=2) + "\n", encoding="utf-8")
        return code


def add_args(parser=None, description=""):
    ap = parser or argparse.ArgumentParser(description=description)
    ap.add_argument("--tree", default=str(REPO_ROOT),
                    help="repo root of the tree/revision under test "
                         "(default: the worktree containing this harness)")
    ap.add_argument("--core-root", default=None,
                    help="explicit Skill 75 core dir (overrides --tree); "
                         "point at a mutated scratch copy to prove a failure")
    ap.add_argument("--out", default=None, help="optional receipt directory")
    return ap


def resolve_core(args):
    """The core module directory of the tree under test."""
    core = Path(args.core_root) if args.core_root else Path(args.tree) / CORE_REL
    if not (core / "state_store.py").is_file():
        print("TOOLING: Skill 75 core not found at %s" % core)
        raise SystemExit(2)
    return core


def load_file(path, name):
    """Load one module by file path (no package context needed)."""
    path = Path(path)
    if not path.is_file():
        print("TOOLING: missing module %s" % path)
        raise SystemExit(2)
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_pkg(core, dotted):
    """Import a package module of the tree under test (relative imports work).

    The core dir is prepended to sys.path only for the import, so the runner
    binds the tree under test and never the harness's own checkout.
    """
    core = str(core)
    sys.path.insert(0, core)
    try:
        return importlib.import_module(dotted)
    except ImportError as exc:
        print("TOOLING: cannot import %s from %s: %s" % (dotted, core, exc))
        raise SystemExit(2)
    finally:
        try:
            sys.path.remove(core)
        except ValueError:
            pass


class Scratch(object):
    """A disposable acceptance fixture dir under /tmp; removed on exit."""

    def __init__(self, keep=False):
        self.keep = keep
        self.dir = None

    def __enter__(self):
        self.dir = Path(tempfile.mkdtemp(prefix=SCRATCH_PREFIX, dir="/tmp"))
        return self.dir

    def __exit__(self, *exc):
        if not self.keep and self.dir:
            shutil.rmtree(self.dir, ignore_errors=True)
        return False


def write_json(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
    return str(p)


def tiny_png(path):
    """A real 1x1 PNG (no Pillow) so image gates see non-empty real bytes."""
    import struct
    import zlib

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    body = (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
            + chunk(b"IEND", b""))
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(body)
    return str(p)


def blocked(what):
    """A live provider/channel artifact is required; never fake the pass."""
    print("BLOCKED_A11: %s" % what)
    return 4
