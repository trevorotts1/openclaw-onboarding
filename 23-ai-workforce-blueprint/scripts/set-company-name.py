#!/usr/bin/env python3
"""set-company-name.py - rename the company DISPLAY NAME everywhere (STD001 edit path).

Updates, only with --apply (default is a dry run):
  1. build-state companyName (under the workforce_state lock)
  2. company-config.json "name" in the company root, if the file exists
  3. Command Center companies.name row (by companyId, falling back to companySlug)
  4. COMPANY_NAME= in the Command Center .env.local (that key only, encoded by
     shared-utils/service_env.py, written via temp file + os.replace, mode 0600)

NEVER touches the slug (it is immutable). Exit: 0 ok, 1 failure, 2 bad input.
"""
import argparse, json, os, re, sqlite3, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def clean_name(value):
    """Same validation as scripts/onboarding-identity.py name(), plus: the name must fit one
    lossless COMPANY_NAME line of the Command Center .env.local (checked before any write)."""
    v = value.strip() if isinstance(value, str) else ""
    if not v or len(v) > 200 or any(ord(c) < 32 for c in v):
        raise ValueError("name must be one non-empty line of at most 200 characters")
    _encoded_company_name(v)
    return v


def default_state_path():
    root = os.environ.get("OPENCLAW_ROOT") or ("/data/.openclaw" if os.path.isdir("/data/.openclaw")
                                               else str(Path.home() / ".openclaw"))
    return str(Path(root) / "workspace" / ".workforce-build-state.json")


def _cc_dir():
    if os.environ.get("CC_APP_DIR"):
        return Path(os.environ["CC_APP_DIR"])
    home = Path.home()
    for c in (home / "projects" / "command-center", Path("/data/projects/command-center"),
              home / "projects" / "blackceo-command-center", Path("/data/projects/blackceo-command-center"),
              home / "projects" / "mission-control", home / "blackceo-command-center"):
        if (c / "package.json").is_file():
            return c
    return None


def _env_get(path, key):
    try:
        for line in path.read_text().splitlines():
            m = re.match(rf"\s*{key}\s*=\s*(.*)$", line)
            if m:
                return m.group(1).strip().strip("'\"")
    except OSError:
        pass
    return None


def _encoded_company_name(name):
    """COMPANY_NAME=<value> in the shared service-env format that service_env.read_env reads back."""
    shared = str(Path(__file__).resolve().parents[2] / "shared-utils")
    if shared not in sys.path:
        sys.path.append(shared)  # appended, so it never shadows this script's own modules
    from service_env import encode_assignment
    return encode_assignment("COMPANY_NAME", name)


def _write_env_line(env_path, assignment):
    """Replace every COMPANY_NAME= line (append one if absent): temp file, os.replace, mode 0600."""
    # ponytail: no .env.local lock. A lock file created here by a root run would be root-owned
    # and block interview-launch.py's lock(target) later; os.replace already makes the swap
    # atomic. Add a lock when a rename can race a launch stage on the same box.
    target = env_path.resolve()  # write through a symlink, as write_text did
    st = target.stat()
    lines, done = target.read_text().splitlines(), False
    for i, l in enumerate(lines):
        if re.match(r"\s*COMPANY_NAME\s*=", l):
            lines[i], done = assignment, True
    if not done:
        lines.append(assignment)
    fd, tmp = tempfile.mkstemp(prefix=".company-name-env-", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write("\n".join(lines) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        if os.geteuid() == 0:  # a root run must not hand the service a root-owned file
            os.chown(tmp, st.st_uid, st.st_gid)
        os.replace(tmp, target)
        os.chmod(target, 0o600)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def set_company_name(name, state_path=None, apply_=False, db_path=None, cc_dir=None):
    """Returns a dict of what was (or would be) changed. Raises ValueError on bad input."""
    name = clean_name(name)
    from workforce_state import lock, read, atomic_write
    state_path = state_path or default_state_path()
    out = {"name": name, "apply": apply_, "steps": {}}
    st = read(state_path)
    out["priorName"] = st.get("companyName")
    cc_dir = Path(cc_dir) if cc_dir else _cc_dir()
    env_path = cc_dir / ".env.local" if cc_dir else None

    if apply_:
        with lock(state_path):
            st = read(state_path)
            st["companyName"] = name
            st["stateRevision"] = int(st.get("stateRevision", 0)) + 1
            atomic_write(state_path, st)
    out["steps"]["build-state"] = "updated" if apply_ else "would update"

    root = st.get("companyRoot")
    cfg = Path(root) / "company-config.json" if root else None
    if cfg and cfg.is_file():
        if apply_:
            data = json.loads(cfg.read_text())
            data["name"] = name
            cfg.write_text(json.dumps(data, indent=2) + "\n")
        out["steps"]["company-config.json"] = "updated" if apply_ else "would update"
    else:
        out["steps"]["company-config.json"] = "skipped (no file)"

    db = db_path or (_env_get(env_path, "DATABASE_PATH") if env_path else None)
    if db and Path(db).is_file():
        if apply_:
            con = sqlite3.connect(db)
            try:
                cur = con.execute("UPDATE companies SET name=? WHERE id=?", (name, st.get("companyId")))
                if cur.rowcount == 0 and st.get("companySlug"):
                    cur = con.execute("UPDATE companies SET name=? WHERE slug=?", (name, st.get("companySlug")))
                con.commit()
                out["steps"]["command-center-db"] = f"updated {cur.rowcount} row(s)"
            finally:
                con.close()
        else:
            out["steps"]["command-center-db"] = "would update"
    else:
        out["steps"]["command-center-db"] = "skipped (no database found)"

    if env_path and env_path.is_file():
        if apply_:
            _write_env_line(env_path, _encoded_company_name(name))
        out["steps"]["env.local"] = "updated" if apply_ else "would update"
    else:
        out["steps"]["env.local"] = "skipped (no .env.local)"
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--name", required=True)
    ap.add_argument("--build-state-file", default=None)
    ap.add_argument("--db", default=None, help="override the Command Center database path")
    ap.add_argument("--cc-dir", default=None, help="override the Command Center directory")
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        r = set_company_name(a.name, a.build_state_file, a.apply, a.db, a.cc_dir)
    except ValueError as e:
        print(f"set-company-name: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001
        print(f"set-company-name: FAILED: {e}", file=sys.stderr)
        return 1
    print(json.dumps(r, indent=2) if a.json else
          f"set-company-name: {'APPLIED' if a.apply else 'DRY-RUN'} '{r['name']}' " + ", ".join(f"{k}={v}" for k, v in r["steps"].items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
