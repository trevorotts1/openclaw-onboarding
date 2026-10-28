#!/usr/bin/env python3
"""ensure_cc_tenant_env.py -- keep the Command Center's company and tenant env resolvable.

  ensure_cc_tenant_env.py [--app DIR] [--check]

1. COMPANY_SLUG. Command Center task creation (taskRequestCompany) needs exactly one company, or
   COMPANY_SLUG to pick one. A box with more than one row in `companies` (repeat installs) and no
   COMPANY_SLUG rejects every task ("A unique company context is required to create this task").
   Only when companies > 1 and neither COMPANY_SLUG nor MC_ROUTE_COMPANY_ID is set in <app>/.env.local,
   this writes COMPANY_SLUG=<slug of the company owning the most non-archived workspaces>, and only
   when that company is a strict winner and its slug is unique in `companies`. Otherwise it reports
   loudly and changes nothing. An existing value is never overwritten.
2. Tenant registry (read-only). A non-loopback `kind: self` entry in MC_TENANT_REGISTRY_JSON with no
   issuer / audience / subjects locks the owner out after Cloudflare sign-in (tenant_access_required).
   Boxes hold no Cloudflare credentials, so the roll cannot fill them; it reports the gap on a
   CC_TENANT_REGISTRY_ACCESS_MISSING line instead. Counts and field names only, never a host or value.

Never prints env values. The file is rewritten atomically (0600) and re-read to verify.

Exit: 0 nothing to do / written, 3 undetermined or registry gap (the roll output says so loudly),
4 no Command Center .env.local or database on this box (not applicable).
"""
import argparse, json, os, sqlite3, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ensure_cc_interview_flag import cc_db_path  # noqa: E402
from resolve_db import is_db_found  # noqa: E402
from service_env import read_env, encode_assignment  # noqa: E402

LOOPBACK = ("localhost", "127.0.0.1", "[::1]", "::1")


def ensure_company_slug(app, check_only=False):
    envf = app / ".env.local"
    if not envf.is_file():
        return 4, "no .env.local at %s (no Command Center service env)" % app
    env = read_env(envf)
    db = cc_db_path(app)
    if not is_db_found(db):
        return 4, "no Command Center database found"
    con = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
    try:
        companies = con.execute("SELECT id, slug FROM companies").fetchall()
        if len(companies) <= 1:
            return 0, "%d company row(s); COMPANY_SLUG not needed" % len(companies)
        slug = (env.get("COMPANY_SLUG") or "").strip()
        if slug:
            if any(s == slug for _, s in companies):
                return 0, "COMPANY_SLUG already set (kept)"
            return 3, "CC_COMPANY_SLUG_UNDETERMINED: COMPANY_SLUG is set but matches none of the %d companies; left unchanged" % len(companies)
        if (env.get("MC_ROUTE_COMPANY_ID") or "").strip():
            return 0, "MC_ROUTE_COMPANY_ID already set (kept)"
        cols = {r[1] for r in con.execute("PRAGMA table_info(workspaces)")}
        if "company_id" not in cols:
            ranked = []
        else:
            live = " AND w.archived_at IS NULL" if "archived_at" in cols else ""
            ranked = con.execute("SELECT c.slug, COUNT(*) FROM workspaces w JOIN companies c ON c.id = w.company_id "
                                 "WHERE 1 = 1" + live + " GROUP BY c.id ORDER BY 2 DESC").fetchall()
    finally:
        con.close()
    tie = len(ranked) > 1 and ranked[0][1] == ranked[1][1]
    owner = (ranked[0][0] or "").strip() if ranked else ""
    if not owner or tie or sum(1 for _, s in companies if s == owner) != 1:
        return 3, ("CC_COMPANY_SLUG_UNDETERMINED: %d companies and COMPANY_SLUG unset, but no single company owns the most "
                   "non-archived workspaces (or its slug is not unique); tasks will be rejected until an operator sets COMPANY_SLUG. "
                   "Nothing written." % len(companies))
    if check_only:
        return 3, "MISSING: %d companies and COMPANY_SLUG unset; would set it to the company owning the most workspaces" % len(companies)
    text = envf.read_text()
    fd, tmp = tempfile.mkstemp(dir=str(app), prefix=".company-slug-")
    with os.fdopen(fd, "w", encoding="utf-8") as h:
        h.write(text + ("" if text.endswith("\n") or not text else "\n") + encode_assignment("COMPANY_SLUG", owner) + "\n")
        h.flush(); os.fsync(h.fileno())
    os.chmod(tmp, 0o600)
    os.replace(tmp, envf)
    if read_env(envf).get("COMPANY_SLUG") != owner:
        return 3, "wrote but verification FAILED"
    return 0, "COMPANY_SLUG written for the company owning the most workspaces (%d companies); verified (restart Command Center to load it)" % len(companies)


def registry_access_gaps(env):
    """(entries missing Access identity, sorted missing field names) over the non-loopback kind=self registry entries."""
    raw = (env.get("MC_TENANT_REGISTRY_JSON") or "").strip()
    if not raw:
        return 0, []
    try:
        registry = json.loads(raw)
    except ValueError:
        registry = None
    if not isinstance(registry, dict):
        return -1, []
    bad, missing = 0, set()
    for host, reg in registry.items():
        if host.lower() in LOOPBACK or not isinstance(reg, dict) or reg.get("kind") != "self":
            continue
        gaps = {f for f in ("issuer", "audience", "subjects") if not reg.get(f)}
        if gaps:
            bad += 1
            missing |= gaps
    return bad, sorted(missing)


def check_tenant_registry(app):
    envf = app / ".env.local"
    if not envf.is_file():
        return 4, "no .env.local at %s (no Command Center service env)" % app
    bad, missing = registry_access_gaps(read_env(envf))
    if bad < 0:
        return 3, "CC_TENANT_REGISTRY_ACCESS_MISSING: MC_TENANT_REGISTRY_JSON is not a JSON object keyed by hostname"
    if bad:
        return 3, ("CC_TENANT_REGISTRY_ACCESS_MISSING: %d public host registration(s) lack %s -- the owner is locked out after "
                   "Cloudflare sign-in (tenant_access_required). Create the Cloudflare Access app, then run "
                   "32-command-center-setup/scripts/interview-launch.py register-access (see TENANT-CONFIGURATION.md)."
                   % (bad, ", ".join(missing)))
    return 0, "public host registrations carry issuer, audience and subjects (or none registered)"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--app")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    app = Path(a.app or os.environ.get("CC_APP_DIR") or Path.home() / "projects/command-center")
    rcs = []
    for name, fn in (("cc-company-slug", lambda: ensure_company_slug(app, a.check)),
                     ("cc-tenant-registry", lambda: check_tenant_registry(app))):
        try:
            rc, msg = fn()
        except Exception as e:  # never raise into an update
            rc, msg = 3, "error: %s" % type(e).__name__
        print(msg if msg.startswith("CC_") else "%s: %s" % (name, msg))  # loud lines start with their greppable token
        rcs.append(rc)
    return 3 if 3 in rcs else (4 if set(rcs) == {4} else 0)


if __name__ == "__main__":
    sys.exit(main())
