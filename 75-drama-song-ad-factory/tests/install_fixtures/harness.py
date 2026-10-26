#!/usr/bin/env python3
"""S75-T33 — supported-install fixtures and sandbox harness for Skill 75.

Ledger row this closes on the AUTHORING half: "Supported install fixtures 0/2,
UNVERIFIED". The fixtures encode each flavor's own declared install path; the
harness copies a CANDIDATE tree into a throwaway sandbox using that path's copy
semantics and then checks the INSTALLED copy. It never runs install.sh, never
installs a package, never touches a real config root, and never modifies either
repository.

Flavors (see flavor-onb.json / flavor-n999.json for the exact citations):

  ONB    trevorotts1/openclaw-onboarding
         install.sh Step 5 copies 75-drama-song-ad-factory/ into
         ${OC_SKILLS_DIR:-...:-$HOME/.openclaw}/skills/75-drama-song-ad-factory
  N999   trevorotts1/999-setup
         AGENT_INSTALL.md §5 copies .claude/skills/drama-song-ad-factory into
         <config root>/skills/, co-installs drama-studio (the shared-bridge
         symlink target), then sync-nine-skills.sh symlinks it into
         ~/.claude-nine/skills.

Usage:
  python3 harness.py --self-check --candidate-onb <repo> --candidate-n999 <repo>
  python3 harness.py --flavor onb|n999 --candidate <repo> [--sandbox <dir>] [--keep]

Exit 0 = every row ok; 1 = any FAIL; 2 = resolve/tooling failure (nothing ran).
Stdlib only, no network, no provider calls.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = {
    "onb": HERE / "flavor-onb.json",
    "n999": HERE / "flavor-n999.json",
}
ENVELOPE = "blackceo.intake-preflight/envelope/v1"
EXIT_OK, EXIT_FAIL, EXIT_TOOLING = 0, 1, 2
ROWS = []
CONTROL_MODE = {"on": False}   # injected breaks print as expected-fail


class SandboxError(RuntimeError):
    """A write was attempted outside the throwaway sandbox."""


def row(status, name, detail=""):
    if CONTROL_MODE["on"] and status == "FAIL":
        status = "EXPECTED-FAIL"
    ROWS.append((status, name, detail))
    line = f"{'expected-fail' if status == 'EXPECTED-FAIL' else status}: {name}"
    if detail and status != "ok":
        line += f" ({detail})"
    print(line, flush=True)


def check(name, ok, detail=""):
    row("ok" if ok else "FAIL", name, detail)


# --------------------------------------------------------------------------- #
# sandbox: every mutation in this file passes through guard()
class Sandbox:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.home = self.root / "home"
        self.tmp = self.root / "tmp"
        self.work = self.root / "work"
        self.written = []
        for d in (self.root, self.home, self.tmp, self.work):
            d.mkdir(parents=True, exist_ok=True)

    def guard(self, p):
        rp = Path(p).resolve(strict=False)
        if not (rp == self.root or self.root in rp.parents):
            raise SandboxError(f"write outside sandbox: {rp} (sandbox {self.root})")
        return rp

    def mkdir(self, p):
        self.guard(p)
        Path(p).mkdir(parents=True, exist_ok=True)
        self.written.append(str(Path(p).resolve()))

    def record(self, p):
        self.written.append(str(self.guard(p)))


def inside(root: Path, p: Path) -> bool:
    rp = Path(p).resolve(strict=False)
    return rp == root or root in rp.parents


# --------------------------------------------------------------------------- #
# install emulation (copy semantics declared by each repository)
def copy_link(item: Path, dest: Path, sb: Sandbox):
    sb.guard(dest)
    os.symlink(os.readlink(item), dest)
    sb.record(dest)


def copy_items(src: Path, dest: Path, skip: set, sb: Sandbox):
    """install.sh Step 5: per-item cp -r for dirs, cp for files."""
    sb.mkdir(dest)
    for item in sorted(src.iterdir()):
        if item.name in skip:
            continue
        out = dest / item.name
        if item.is_symlink():
            copy_link(item, out, sb)
        elif item.is_dir():
            sb.guard(out)
            shutil.copytree(item, out, symlinks=True, dirs_exist_ok=True)
            sb.record(out)
        else:
            sb.guard(out)
            shutil.copy2(item, out)
            sb.record(out)


def copy_tree(src: Path, dest: Path, sb: Sandbox):
    """AGENT_INSTALL.md §5: copy the whole skill directory."""
    sb.guard(dest)
    shutil.copytree(src, dest, symlinks=True, dirs_exist_ok=True)
    sb.record(dest)


def install(fx, candidate: Path, sb: Sandbox):
    c = fx["install_contract"]
    dest_root = sb.home / c["dest_root_rel_to_home"]
    dest = dest_root / c["dest_name"]
    src = candidate / c["source_rel"]
    if c["mode"] == "copy_tree_items":
        copy_items(src, dest, set(c.get("skip_items") or []), sb)
    else:
        copy_tree(src, dest, sb)

    for entry in c.get("co_install") or []:
        out = dest_root / entry["dest_name"]
        if entry.get("mode") == "copy_tree_items":
            copy_items(candidate / entry["source_rel"], out,
                       set(entry.get("skip_items") or []), sb)
        else:
            copy_tree(candidate / entry["source_rel"], out, sb)

    mirror = None
    m = c.get("mirror")
    if m:
        msrc = sb.home / m["source_rel_to_home"]
        mdst = sb.home / m["dest_rel_to_home"]
        sb.mkdir(mdst)
        for child in sorted(msrc.iterdir()):
            if not child.is_dir():
                continue
            out = mdst / child.name
            sb.guard(out)
            if not (out.exists() or out.is_symlink()):
                os.symlink(str(child), out)   # sync-nine-skills.sh links missing
                sb.record(out)
        mirror = mdst / c["dest_name"]
    return {"install_dir": dest, "mirror_dir": mirror}


# --------------------------------------------------------------------------- #
# subprocess environment: pinned to the sandbox, never the caller's config
def sandbox_env(sb: Sandbox, pythonpath: Path | None = None):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("OC_", "OPENCLAW_"))}
    env.pop("PYTHONPATH", None)
    env.pop("CLAUDE_CONFIG_DIR", None)
    env.update({
        "HOME": str(sb.home),
        "TMPDIR": str(sb.tmp),
        "XDG_CONFIG_HOME": str(sb.home / ".config"),
        "XDG_CACHE_HOME": str(sb.home / ".cache"),
        "XDG_DATA_HOME": str(sb.home / ".local/share"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONSAFEPATH": "1",
    })
    if pythonpath is not None:
        env["PYTHONPATH"] = str(pythonpath)
    return env


def run_py(sb, args, pythonpath=None):
    return subprocess.run(args, cwd=str(sb.work),
                          env=sandbox_env(sb, pythonpath),
                          capture_output=True, text=True)


# --------------------------------------------------------------------------- #
# checks
def marker_values(skill: Path, markers):
    vals = {}
    for m in markers:
        p = skill / m["file"]
        if m["kind"] == "plain":
            vals[m["file"]] = p.read_text(encoding="utf-8").strip() if p.is_file() else None
        elif m["kind"] == "frontmatter_version":
            text = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
            got = None
            if text.startswith("---"):
                end = text.find("\n---", 3)
                if end != -1:
                    hit = re.search(r"(?m)^version:\s*(\S+)\s*$", text[3:end])
                    got = hit.group(1) if hit else None
            vals[m["file"]] = got
        else:
            vals[m["file"]] = None
    return vals


def markers_agree(skill: Path, fx):
    vals = marker_values(skill, fx["version_markers"])
    present = [v for v in vals.values() if v]
    ok = bool(present) and len(present) == len(vals) and len(set(present)) == 1
    return ok, ", ".join(f"{k}={v}" for k, v in vals.items())


def shape_check(skill: Path, name: str, spec):
    p = skill / name
    kind = spec["kind"]
    if kind == "dir":
        if not p.is_dir() or p.is_symlink():
            return False, f"{name} is not a real directory"
        missing = [f for f in spec.get("must_contain", []) if not (p / f).is_file()]
        return (not missing), f"{name}: missing {','.join(missing)}" if missing else ""
    if kind == "symlink":
        if not p.is_symlink():
            return False, f"{name} is not a symlink"
        target = os.readlink(p)
        if target != spec.get("target"):
            return False, f"{name} -> {target!r}, expected {spec.get('target')!r}"
        if spec.get("must_resolve"):
            if not p.exists():
                return False, f"{name} dangles -> {target}"
            need = spec.get("target_must_contain")
            if need and not (p / need).is_file():
                return False, f"{name} target lacks {need}"
        return True, ""
    return False, f"unknown shape kind {kind!r}"


def pythonpath_for(skill: Path, probe):
    rels = probe["pythonpath_rel"]
    if isinstance(rels, str):
        rels = [rels]
    return os.pathsep.join(str(skill / r) for r in rels)


def entrypoint_check(fx, sb, skill: Path, tag: str):
    probe = fx["entrypoint_probe"]
    ep = skill / probe["rel"]
    if not ep.is_file():
        check(f"{tag}: installed entrypoint resolves", False, str(ep))
        return
    check(f"{tag}: installed entrypoint resolves", True, str(ep))
    p = run_py(sb, [sys.executable, str(ep)] + probe["args"],
               pythonpath=pythonpath_for(skill, probe))
    try:
        env = json.loads(p.stdout)
    except Exception:
        env = None
    if not isinstance(env, dict):
        check(f"{tag}: installed entrypoint emits the pinned envelope", False,
              f"rc={p.returncode} non-JSON: {(p.stderr or p.stdout).strip()[-240:]}")
        return
    failures = [f"{k}={env.get(k)!r} (want {v!r})"
                for k, v in probe["expect"].items() if env.get(k) != v]
    ok = p.returncode == probe["expect_rc"] and not failures
    if env.get("schema_version") != ENVELOPE and "schema_version" not in probe["expect"]:
        ok = False
        failures.append(f"schema_version={env.get('schema_version')!r}")
    check(f"{tag}: installed entrypoint emits the pinned envelope", ok,
          f"rc={p.returncode} " + ", ".join(failures))


def import_probe(sb, pythonpath: Path, modules):
    code = ("import importlib,json,sys\n"
            "print(json.dumps({m: getattr(importlib.import_module(m), '__file__', None)"
            " for m in sys.argv[1:]}))")
    p = run_py(sb, [sys.executable, "-c", code] + list(modules), pythonpath=pythonpath)
    try:
        return p.returncode, json.loads(p.stdout), (p.stderr or "").strip()[-300:]
    except Exception:
        return p.returncode, None, (p.stderr or p.stdout).strip()[-300:]


def import_check(fx, sb, skill: Path, candidate: Path, tag: str):
    core = skill / "scripts" / "core"
    rc, got, tail = import_probe(sb, core, fx["core_modules"])
    if rc != 0 or not isinstance(got, dict):
        check(f"{tag}: required modules import from the installed copy", False,
              f"rc={rc} {tail}")
        return False, []
    checkout, missing = [], []
    for mod, file in got.items():
        if not file:
            missing.append(mod)
            continue
        rp = Path(file).resolve()
        if inside(candidate.resolve(), rp):
            checkout.append(f"{mod}={rp}")
        elif not inside(core.resolve(), rp):
            missing.append(f"{mod}={rp}")
    ok = not checkout and not missing
    detail = ("from checkout: " + ",".join(checkout)) if checkout else \
             ("outside install: " + ",".join(missing)) if missing else ""
    check(f"{tag}: required modules import from the installed copy", ok, detail)
    return ok, checkout


def run_checks(fx, candidate: Path, sb: Sandbox, installed, sentinels=None):
    tag = fx["flavor_key"].lower()
    c = fx["install_contract"]
    src = candidate / c["source_rel"]
    skill = installed["install_dir"]

    check(f"{tag}: candidate source dir resolves", src.is_dir(), str(src))
    missing = [r for r in fx["required_files"] if not (src / r).is_file()]
    check(f"{tag}: candidate required files present", not missing, ",".join(missing))

    ok, detail = markers_agree(src, fx)
    check(f"{tag}: candidate version markers agree", ok, detail)

    for name, spec in (fx.get("flavor_only") or {}).items():
        ok, detail = shape_check(src, name, spec)
        check(f"{tag}: candidate {name} has the flavor's shape", ok, detail)

    check(f"{tag}: installed at the declared destination", skill.is_dir(), str(skill))
    missing = [r for r in fx["required_files"] if not (skill / r).is_file()]
    check(f"{tag}: installed required files present", not missing, ",".join(missing))

    entrypoint_check(fx, sb, skill, tag)
    import_check(fx, sb, skill, candidate, tag)

    ok, detail = markers_agree(skill, fx)
    check(f"{tag}: installed version markers agree", ok, detail)

    for name, spec in (fx.get("flavor_only") or {}).items():
        ok, detail = shape_check(skill, name, spec)
        check(f"{tag}: installed {name} keeps the flavor's shape", ok, detail)

    mirror = installed.get("mirror_dir")
    if c.get("mirror"):
        live = bool(mirror) and mirror.is_symlink()
        check(f"{tag}: claude-nine skills mirror is a symlink", live, str(mirror))
        resolves = live and mirror.exists() and (mirror / "SKILL.md").is_file()
        check(f"{tag}: mirror resolves the installed skill", resolves, str(mirror))

    bad = [w for w in sb.written if not inside(sb.root, Path(w))]
    check(f"{tag}: harness wrote only inside the sandbox", bool(sb.written) and not bad,
          ",".join(bad[:5]))

    if sentinels is not None:
        after = sentinel_snapshot()
        changed = [k for k in sentinels if sentinels[k] != after.get(k)]
        check("no-client: real client roots untouched", not changed,
              "changed: " + ",".join(changed))


# --------------------------------------------------------------------------- #
# no-client evidence: metadata-only sentinels of the real config roots
def sentinel_snapshot():
    home = Path.home()
    paths = [
        home / ".openclaw",
        home / ".claude" / "skills",
        home / ".claude-nine" / "skills",
        home / ".claude" / "settings.json",
    ]
    out = {}
    for p in paths:
        try:
            st = p.stat()
            out[str(p)] = {
                "exists": True,
                "mtime_ns": st.st_mtime_ns,
                "ino": st.st_ino,
                "size": st.st_size,
                "entries": len(os.listdir(p)) if p.is_dir() else None,
            }
        except OSError:
            out[str(p)] = {"exists": False}
    return out


# --------------------------------------------------------------------------- #
# negative controls: prove each real check discriminates
def control(parent: Path, label: str, fn):
    sb = Sandbox(tempfile.mkdtemp(dir=parent, prefix=f"control-{label}-"))
    fn(sb)


def control_checks(fx, candidate, sb, installed, expect):
    """Run real checks on a mutated install; return True when the targeted
    detector fires. The FAIL rows are the injected break, so they are relabelled
    EXPECTED-FAIL and never count toward the run's exit code."""
    start = len(ROWS)
    CONTROL_MODE["on"] = True
    try:
        run_checks(fx, candidate, sb, installed)
    finally:
        CONTROL_MODE["on"] = False
    return any(r[0] == "EXPECTED-FAIL" and expect in r[1] for r in ROWS[start:])


def control_missing_entrypoint(fx, candidate, parent):
    def body(sb):
        installed = install(fx, candidate, sb)
        ep = installed["install_dir"] / fx["entrypoint_probe"]["rel"]
        ep.unlink()
        hit = control_checks(fx, candidate, sb, installed, "entrypoint resolves")
        check("control: missing entrypoint detected", hit, "no FAIL row matched")
    control(parent, "missing-entrypoint", body)


def control_version_drift(fx, candidate, parent):
    def body(sb):
        installed = install(fx, candidate, sb)
        stamp = installed["install_dir"] / "skill-version.txt"
        stamp.write_text("v0.0.0-drift\n", encoding="utf-8")
        hit = control_checks(fx, candidate, sb, installed, "installed version markers agree")
        check("control: version drift detected", hit, "no FAIL row matched")
    control(parent, "version-drift", body)


def control_symlink_dereferenced(fx, candidate, parent):
    def body(sb):
        installed = install(fx, candidate, sb)
        link = installed["install_dir"] / "shared-bridge"
        target = link.resolve()
        link.unlink()
        shutil.copytree(target, link, symlinks=True)
        hit = control_checks(fx, candidate, sb, installed, "shared-bridge keeps the flavor's shape")
        check("control: dereferenced symlink detected", hit, "no FAIL row matched")
    control(parent, "symlink-dereferenced", body)


def control_import_from_checkout(fx, candidate, parent):
    def body(sb):
        core = candidate / fx["install_contract"]["source_rel"] / "scripts" / "core"
        rc, got, tail = import_probe(sb, core, fx["core_modules"])
        offenders = []
        if rc == 0 and isinstance(got, dict):
            offenders = [m for m, f in got.items()
                         if f and inside(candidate.resolve(), Path(f).resolve())]
        check("control: import-from-checkout detected", bool(offenders),
              f"rc={rc} {tail} offenders={offenders[:3]}")
    control(parent, "import-from-checkout", body)


# --------------------------------------------------------------------------- #
# drivers
def load_fixture(key):
    with open(FIXTURES[key], encoding="utf-8") as fh:
        return json.load(fh)


def finish(exit_code=EXIT_OK):
    fails = [r for r in ROWS if r[0] == "FAIL"]
    print(f"\n{len(ROWS)} rows, {len(fails)} FAIL", flush=True)
    if fails:
        return EXIT_FAIL
    return exit_code


def run_one(fx, candidate: Path, sandbox_root: Path | None, keep: bool):
    before = sentinel_snapshot()
    root = sandbox_root or Path(tempfile.mkdtemp(prefix="s75t33-install-"))
    sb = Sandbox(root)
    print(f"sandbox: {sb.root}", flush=True)
    try:
        installed = install(fx, candidate, sb)
        run_checks(fx, candidate, sb, installed, sentinels=before)
    finally:
        if not keep:
            shutil.rmtree(sb.root, ignore_errors=True)
    return finish()


def resolve_onb_default():
    for p in (Path(__file__).resolve().parents[3],
              Path.home() / "openclaw-onboarding"):
        if (p / "75-drama-song-ad-factory").is_dir():
            return p
    return None


def self_check(args):
    onb = Path(args.candidate_onb).expanduser().resolve() if args.candidate_onb \
        else resolve_onb_default()
    n999_env = args.candidate_n999 or os.environ.get("DSAF_N999_CANDIDATE")
    n999 = Path(n999_env).expanduser().resolve() if n999_env else None
    missing = [k for k, p in (("ONB", onb), ("N999", n999)) if p is None]
    if missing:
        print("resolve-failure: no candidate for " + ", ".join(missing)
              + " (pass --candidate-onb/--candidate-n999 or set DSAF_N999_CANDIDATE)",
              file=sys.stderr)
        return 2
    for key, cand in (("onb", onb), ("n999", n999)):
        fx = load_fixture(key)
        if not (cand / fx["install_contract"]["source_rel"]).is_dir():
            print(f"resolve-failure: {fx['candidate_repo']} candidate at {cand} "
                  f"has no {fx['install_contract']['source_rel']}", file=sys.stderr)
            return 2

    parent = Path(tempfile.mkdtemp(prefix="s75t33-selfcheck-"))
    print(f"sandbox parent: {parent}", flush=True)
    before = sentinel_snapshot()
    try:
        for key, cand in (("onb", onb), ("n999", n999)):
            fx = load_fixture(key)
            sb = Sandbox(tempfile.mkdtemp(dir=parent, prefix=f"{key}-positive-"))
            installed = install(fx, cand, sb)
            run_checks(fx, cand, sb, installed, sentinels=before)

        control_missing_entrypoint(load_fixture("onb"), onb, parent)
        control_version_drift(load_fixture("onb"), onb, parent)
        control_import_from_checkout(load_fixture("onb"), onb, parent)
        control_symlink_dereferenced(load_fixture("n999"), n999, parent)

        after = sentinel_snapshot()
        changed = [k for k in before if before[k] != after.get(k)]
        check("no-client: real client roots untouched after all runs", not changed,
              "changed: " + ",".join(changed))
    finally:
        if not args.keep:
            shutil.rmtree(parent, ignore_errors=True)
    return finish()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--self-check", action="store_true")
    ap.add_argument("--flavor", choices=sorted(FIXTURES))
    ap.add_argument("--candidate")
    ap.add_argument("--candidate-onb")
    ap.add_argument("--candidate-n999")
    ap.add_argument("--sandbox")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args(argv)

    if args.self_check:
        return self_check(args)
    if not args.flavor or not args.candidate:
        ap.error("--flavor and --candidate are required without --self-check")
    fx = load_fixture(args.flavor)
    cand = Path(args.candidate).expanduser().resolve()
    if not (cand / fx["install_contract"]["source_rel"]).is_dir():
        print(f"resolve-failure: {cand} has no "
              f"{fx['install_contract']['source_rel']}", file=sys.stderr)
        return 2
    return run_one(fx, cand, Path(args.sandbox).resolve() if args.sandbox else None,
                   args.keep)


if __name__ == "__main__":
    sys.exit(main())
