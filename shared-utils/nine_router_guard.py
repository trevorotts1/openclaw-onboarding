#!/usr/bin/env python3
"""9Router-safe 999-setup step for the fleet roll: detect, skills-only, guard.

A box that already runs 9Router must NEVER get the 999 link/installer path (it
replaces ~/.claude/skills/nine-router-setup and can rewire the router). On such
a box the roll runs the 999 installer with exactly `--skills-only` (999-setup
PR 24, nine-router-setup v1.22.0) and checks, before and after, that no 9Router
config/database file and no claude-nine launcher file changed.

Detection (same three signals the NSR-001 list used; installer's own
--skills-only detection is the same, read-only):
  dir        ~/.9router is a directory
  launcher   ~/.local/bin/claude-nine is a file
  answering  GET http://127.0.0.1:${NINEROUTER_PORT:-20128}/api/health is 2xx
  class: 9router = all three, partial = one or two, none = zero.
  Partial is treated as a 9Router box too (a router that is briefly down must
  not fall onto the link path); only `none` keeps the existing behavior.

Guard: sha256 of each file/table, held in memory only. Hash values are never
printed or written; only counts and the LABEL of anything that changed.

Stdlib only. CLI (used by shared-utils/lib-frontdoor.sh):
  nine_router_guard.py detect                 exit 0 skills-only box, 1 none
  nine_router_guard.py skills-only --repo P   exit 0 ok, 1 failed, 3 MISMATCH, 4 unavailable
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import urllib.request
from pathlib import Path

# The ONLY arguments the 9Router path may hand the 999 installer.
SKILLS_ONLY_ARGS = ["--skills-only"]
INSTALLER_REL = ".claude/skills/nine-router-setup/scripts/setup-macos.sh"
LAUNCHER_FILES = ("claude-nine", "claude-codex", "claude-code-lib.sh", "get-9router-key.sh")

# Runtime state the router rewrites by itself (token refresh, rate-limit locks,
# error counters). Not config: excluded so a live router cannot fake a MISMATCH.
_VOLATILE = re.compile(r"^(modelLock_|last|backoff|error|test|expires|accessToken$|refreshToken$|idToken$)|At$")

# ponytail: config tables hashed whole except providerConnections/proxyPools
# (runtime keys filtered above) and _meta.totalRequestsLifetime (a counter).
# usageHistory/requestDetails/usageDaily are traffic logs, not config, never read.
# Add a table here if a new config table appears in a router release.


def health_url() -> str:
    port = os.environ.get("NINEROUTER_PORT", "").strip()
    return f"http://127.0.0.1:{port if port.isdigit() else '20128'}/api/health"


def _answering(timeout: float) -> bool:
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(health_url(), timeout=timeout) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


def detect(home, timeout: float = 3.0, probe: bool = True) -> dict:
    """probe=False skips the live-port GET (fixture homes must never reach the real router)."""
    home = Path(home)
    sig = {"dir": (home / ".9router").is_dir(),
           "launcher": (home / ".local/bin/claude-nine").is_file(),
           "answering": probe and _answering(timeout)}
    n = sum(sig.values())
    return {"signals": sig, "class": "9router" if n == 3 else ("partial" if n else "none"),
            "skills_only": n > 0}


def _sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha_text(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _stable(data):
    try:
        d = json.loads(data) if isinstance(data, (str, bytes)) else data
    except ValueError:
        return data
    return {k: v for k, v in d.items() if not _VOLATILE.search(k)} if isinstance(d, dict) else d


def _db_digests(db: Path) -> dict:
    out = {}
    try:
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error as e:
        return {"db": f"unreadable:{type(e).__name__}"}
    try:
        tables = [r[0] for r in c.execute("select name from sqlite_master where type='table' order by name")]
        skip = {"usageHistory", "requestDetails", "usageDaily", "sqlite_sequence"}
        for t in tables:
            if t in skip:
                continue
            try:
                if t == "providerConnections":
                    q = 'select id,provider,authType,name,email,priority,isActive,data from "providerConnections" order by id'
                    rows = [r[:7] + (_stable(r[7]),) for r in c.execute(q)]
                elif t == "proxyPools":
                    rows = [(r[0], r[1], _stable(r[2])) for r in c.execute('select id,isActive,data from "proxyPools" order by id')]
                elif t == "_meta":
                    rows = list(c.execute('select * from "_meta" where key != ? order by key', ("totalRequestsLifetime",)))
                else:
                    rows = list(c.execute(f'select * from "{t}" order by 1,2' if t == "kv" else f'select * from "{t}" order by 1'))
                out[f"db:{t}"] = _sha_text(json.dumps(rows, sort_keys=True, default=str))
            except sqlite3.Error as e:
                out[f"db:{t}"] = f"unreadable:{type(e).__name__}"
    except sqlite3.Error as e:
        out["db"] = f"unreadable:{type(e).__name__}"
    finally:
        c.close()
    return out


def snapshot(home) -> dict:
    """label -> sha256 (or 'absent'/'unreadable:...'). In memory only."""
    home = Path(home)
    s = {}

    def add(label: str, p: Path):
        try:
            if p.is_symlink():
                s[label + "@link"] = _sha_text(os.readlink(p))
            s[label] = _sha_file(p) if p.is_file() else "absent"
        except OSError as e:
            s[label] = f"unreadable:{type(e).__name__}"

    nr = home / ".9router"
    for d, prefix in ((nr, "9router"), (nr / "auth", "9router/auth")):
        if d.is_dir():
            for p in sorted(d.iterdir()):
                if p.is_file() and not p.name.endswith(".log"):
                    add(f"{prefix}/{p.name}", p)
    binp = home / ".local/bin"
    names = list(LAUNCHER_FILES)
    if binp.is_dir():
        names += sorted(p.name for p in binp.glob("fix-9router-*.mjs"))
    for n in names:
        add(f"launcher/{n}", binp / n)
    add("claude-nine/settings.json", home / ".claude-nine/settings.json")
    db = nr / "db/data.sqlite"
    if db.is_file():
        s.update(_db_digests(db))
    else:
        s["db"] = "absent"
    return s


def compare(before: dict, after: dict):
    """-> (match_count, [labels that differ]). Prints nothing, returns no values."""
    bad = [k for k in sorted(set(before) | set(after)) if before.get(k, "absent") != after.get(k, "absent")]
    return len(set(before) | set(after)) - len(bad), bad


def skills_only_guarded(repo, home, bash: str = "bash", timeout: int = 300) -> dict:
    """Run the 999 installer with --skills-only between two snapshots.
    status: ok | failed | mismatch | unavailable (installer predates the flag)."""
    installer = Path(repo) / INSTALLER_REL
    try:
        text = installer.read_text(errors="replace")
    except OSError as e:
        return {"status": "unavailable", "detail": f"999 installer unreadable: {e}"}
    if "--skills-only" not in text:
        return {"status": "unavailable",
                "detail": "999 installer predates --skills-only; not run (the full installer is never used on a 9Router box)"}
    argv = [bash, str(installer), *SKILLS_ONLY_ARGS]
    before = snapshot(home)
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                           env={**os.environ, "HOME": str(home)})
        rc, out = p.returncode, (p.stdout + p.stderr).strip()[-400:]
    except subprocess.TimeoutExpired:
        rc, out = 124, f"skills-only timed out after {timeout}s"
    match, bad = compare(before, snapshot(home))
    return {"status": "mismatch" if bad else ("ok" if rc == 0 else "failed"),
            "rc": rc, "match": match, "mismatch": len(bad), "mismatched": bad,
            "argv": [os.path.basename(argv[0]), *argv[1:]], "output": out}


def _main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("detect")
    so = sub.add_parser("skills-only")
    so.add_argument("--repo", required=True)
    a = ap.parse_args(argv)
    home = Path(os.environ.get("HOME", str(Path.home())))
    d = detect(home)
    sig = " ".join(f"{k}={int(v)}" for k, v in d["signals"].items())
    if a.cmd == "detect":
        print(f"[9router-guard] class={d['class']} {sig}")
        return 0 if d["skills_only"] else 1
    print(f"[9router-guard] class={d['class']} {sig}")
    if not d["skills_only"]:
        print("[9router-guard] no 9Router signal: skills-only not applicable")
        return 1
    g = skills_only_guarded(a.repo, home)
    if g["status"] == "unavailable":
        print(f"[9router-guard] UNAVAILABLE: {g['detail']}")
        return 4
    print(f"[9router-guard] ran: {' '.join(g['argv'])} (rc={g['rc']})")
    print(f"[9router-guard] checksums: {g['match']} MATCH, {g['mismatch']} MISMATCH")
    if g["mismatch"]:
        print("[9router-guard] MISMATCH: " + ", ".join(g["mismatched"]))
        return 3
    if g["status"] != "ok":
        print(f"[9router-guard] skills-only failed rc={g['rc']}: {g['output'][-200:]}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_main())
