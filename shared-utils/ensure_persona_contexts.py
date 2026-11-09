#!/usr/bin/env python3
"""ensure_persona_contexts.py -- write and verify MC_PERSONA_COMPANY_CONTEXTS_JSON.

Command Center (v7.4.0+) needs this key in its persisted service env
(<app>/.env.local). Without it every new task has no persona and sticks on the
triad gate ("Missing: persona"). Only a fresh interview launch ever wrote it, so
boxes provisioned earlier never had it. Every update/roll runs this.

  ensure_persona_contexts.py [--app DIR] [--oc-root DIR] [--check]

Rules: keyed by each company_id in use (workspaces table, else MC_COMPANY_ID);
validity is the Command Center's own rule (personaCompanyContext): a company
config with no id fields, or whose id fields ALL equal the key, is valid; one
whose id fields name a different company is not. A config therefore serves ONE
company id: this script never adds an id to a config, and a second id that maps
to the same company folder is reported, never "fixed" by adding it. The config's
slug is the context slug; an existing VALID entry is never overwritten; nothing
is guessed (no discovery by newest folder); the file is rewritten atomically
(0600) and re-read to verify. Never prints env values.

Exit: 0 present-valid or written, 3 missing/undetermined (the roll check fails
loudly), 4 no Command Center .env.local on this box (not applicable).
"""
import argparse, json, os, sqlite3, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from service_env import read_env, encode_assignment  # noqa: E402

KEY = "MC_PERSONA_COMPANY_CONTEXTS_JSON"


def _cfg_ids(cfg):
    return [cfg[k] for k in ("company_id", "companyId", "id") if isinstance(cfg.get(k), str) and cfg[k].strip()]


def _cfg_ok(cfg, cid):
    """The Command Center's rule: every id the config carries must equal cid (an id-less config is bound by the context map)."""
    return all(i == cid for i in _cfg_ids(cfg))


def _cfg_slug(cfg, root):
    for k in ("companySlug", "company_slug", "slug"):
        if isinstance(cfg.get(k), str) and cfg[k].strip():
            return cfg[k].strip()
    return root.name


def _valid(ctx, cid):
    try:
        root, conf = Path(ctx["companyRoot"]), Path(ctx["companyConfig"])
        if not (root.is_absolute() and conf.is_absolute() and Path(ctx["personaCatalog"]).is_absolute()):
            return False
        if not (root.is_dir() and conf.is_file() and Path(ctx["personaCatalog"]).is_file()):
            return False
        cfg = json.loads(conf.read_text())
        return bool(ctx.get("companySlug")) and _cfg_ok(cfg, cid)
    except (KeyError, OSError, ValueError, TypeError, AttributeError):
        return False


def _company_ids(app, env):
    db = Path(env.get("DATABASE_PATH") or "mission-control.db")
    db = db if db.is_absolute() else app / db
    ids = []
    if db.is_file():
        try:
            con = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
            cols = [r[1] for r in con.execute("PRAGMA table_info(workspaces)")]
            if "company_id" in cols:
                where = " WHERE archived_at IS NULL" if "archived_at" in cols else ""
                ids = [r[0] for r in con.execute("SELECT DISTINCT company_id FROM workspaces" + where) if r[0]]
            con.close()
        except sqlite3.Error:
            pass
    if not ids and env.get("MC_COMPANY_ID"):
        ids = [env["MC_COMPANY_ID"]]
    return sorted(set(ids))


def run(app, oc_root, check_only=False):
    envf = app / ".env.local"
    if not envf.is_file():
        return 4, "no .env.local at %s (no Command Center service env)" % app
    env = read_env(envf)
    try:
        contexts = json.loads(env.get(KEY) or "{}")
        if not isinstance(contexts, dict):
            contexts = {}
    except ValueError:
        contexts = {}
    ids = _company_ids(app, env)
    if not ids:
        return 3, "cannot tell which company_id is in use (no workspaces rows, no MC_COMPANY_ID)"
    todo = [i for i in ids if not _valid(contexts.get(i) or {}, i)]
    if not todo:
        return 0, "present-valid for %d company id(s)" % len(ids)
    if check_only:
        return 3, "MISSING/invalid for company id(s): %s" % ", ".join(todo)

    ws = Path(env.get("OPENCLAW_WORKSPACE_PATH") or oc_root / "workspace")
    root = env.get("ZERO_HUMAN_COMPANY_DIR")
    if root:
        root = Path(root)
    else:
        found = [p for p in (ws / "zero-human-company").glob("*") if p.is_dir()] if (ws / "zero-human-company").is_dir() else []
        if len(found) != 1:
            return 3, "company root undetermined (set ZERO_HUMAN_COMPANY_DIR): %d candidates" % len(found)
        root = found[0]
    root = root.resolve()
    conf = root / "company-config.json"
    catalog = oc_root / "workspace/data/coaching-personas/persona-categories.json"
    if not conf.is_file():
        return 3, "company config not found: %s" % conf
    if not catalog.is_file():
        return 3, "persona catalog not found: %s" % catalog
    try:
        cfg = json.loads(conf.read_text())
    except ValueError:
        return 3, "company config is not valid JSON: %s" % conf
    slug = _cfg_slug(cfg, root)
    wrote = [i for i in todo if _cfg_ok(cfg, i)]
    bad = [i for i in todo if i not in wrote]
    refused = ("company config %s names a different company than id(s) %s -- nothing written for them "
               "(never add a second id to a config; give each company its own company folder and config)" % (conf, ", ".join(bad)))
    if not wrote:
        return 3, refused
    for cid in wrote:
        contexts[cid] = {"companyRoot": str(root), "companyConfig": str(conf),
                         "companySlug": slug, "personaCatalog": str(catalog.resolve())}
    lines = [l for l in envf.read_text().split("\n") if l.split("=", 1)[0].strip() != KEY]
    while lines and not lines[-1].strip():
        lines.pop()
    lines.append(encode_assignment(KEY, json.dumps(contexts, separators=(",", ":"))))
    fd, tmp = tempfile.mkstemp(dir=str(app), prefix=".persona-ctx-")
    with os.fdopen(fd, "w", encoding="utf-8") as h:
        h.write("\n".join(lines) + "\n"); h.flush(); os.fsync(h.fileno())
    os.chmod(tmp, 0o600)
    os.replace(tmp, envf)
    after = json.loads(read_env(envf)[KEY])
    if not all(_valid(after.get(i) or {}, i) for i in wrote):
        return 3, "wrote but verification FAILED"
    done = "written for %d company id(s); verified (restart Command Center to load it)" % len(wrote)
    return (3, done + "; " + refused) if bad else (0, done)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--app")
    ap.add_argument("--oc-root")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    oc = Path(a.oc_root or os.environ.get("OPENCLAW_ROOT") or Path.home() / ".openclaw")
    app = Path(a.app or os.environ.get("CC_APP_DIR") or Path.home() / "projects/command-center")
    try:
        rc, msg = run(app, oc, a.check)
    except Exception as e:  # never raise into an update
        rc, msg = 3, "error: %s" % type(e).__name__
    print("persona-contexts: " + msg)
    return rc


if __name__ == "__main__":
    sys.exit(main())
