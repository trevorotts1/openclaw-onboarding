#!/usr/bin/env python3
"""ensure_cc_tenant_env: COMPANY_SLUG only when companies > 1, unset, and one company clearly owns the board; registry gaps are loud."""
import json, sqlite3, sys, tempfile, unittest
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "shared-utils"))
import ensure_cc_tenant_env as E
from service_env import read_env


def box(td, companies=(("c1", "alpha"), ("c2", "beta")), ws=(("c1", None), ("c1", None), ("c2", None)), env="MC_API_TOKEN='x'\n", dotenv=None):
    app = Path(td) / "app"; app.mkdir()
    if env is not None:                                                      # env=None: a box with no .env.local at all
        (app / ".env.local").write_text(env)
    if dotenv is not None:                                                   # <app>/.env, which Next.js reads under .env.local
        (app / ".env").write_text(dotenv)
    con = sqlite3.connect(app / "mission-control.db")
    con.execute("create table companies(id text primary key, slug text)")
    con.execute("create table workspaces(id integer primary key, company_id text, archived_at text)")
    con.executemany("insert into companies values(?,?)", companies)
    con.executemany("insert into workspaces(company_id, archived_at) values(?,?)", ws)
    con.commit(); con.close()
    return app


class Slug(unittest.TestCase):
    def test_writes_owner_slug_once_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as td:
            app = box(td)
            self.assertEqual(E.ensure_company_slug(app, True)[0], 3)         # --check: reports, writes nothing
            self.assertNotIn("COMPANY_SLUG", read_env(app / ".env.local"))
            self.assertEqual(E.ensure_company_slug(app)[0], 0)
            env = read_env(app / ".env.local")
            self.assertEqual((env["COMPANY_SLUG"], env["MC_API_TOKEN"]), ("alpha", "x"))
            before = (app / ".env.local").read_text()
            self.assertEqual(E.ensure_company_slug(app)[0], 0)
            self.assertEqual(before, (app / ".env.local").read_text())
    def test_existing_values_are_kept(self):
        for env in ("COMPANY_SLUG='beta'\n", "MC_ROUTE_COMPANY_ID='c2'\n"):
            with tempfile.TemporaryDirectory() as td:
                app = box(td, env=env)
                self.assertEqual(E.ensure_company_slug(app)[0], 0)
                self.assertEqual((app / ".env.local").read_text(), env)
        with tempfile.TemporaryDirectory() as td:                            # a stale slug is reported, never replaced
            app = box(td, env="COMPANY_SLUG='gone'\n")
            self.assertEqual(E.ensure_company_slug(app)[0], 3)
            self.assertEqual((app / ".env.local").read_text(), "COMPANY_SLUG='gone'\n")
    def test_undetermined_changes_nothing(self):
        cases = {"single company": dict(companies=(("c1", "alpha"),)),
                 "tie": dict(ws=(("c1", None), ("c2", None))),
                 "archived tie": dict(ws=(("c1", None), ("c1", "2026-01-01"), ("c1", "2026-01-01"), ("c2", None))),
                 "no workspaces": dict(ws=())}
        for name, kw in cases.items():
            with tempfile.TemporaryDirectory() as td:
                app = box(td, **kw)
                rc, msg = E.ensure_company_slug(app)
                self.assertEqual(rc, 0 if name == "single company" else 3, name)
                if rc == 3:
                    self.assertIn("CC_COMPANY_SLUG_UNDETERMINED", msg)
                self.assertNotIn("COMPANY_SLUG", read_env(app / ".env.local"), name)
    def test_archived_workspaces_do_not_count(self):
        with tempfile.TemporaryDirectory() as td:
            app = box(td, ws=(("c1", None), ("c1", "2026-01-01"), ("c1", "2026-01-01"), ("c2", None), ("c2", None)))
            self.assertEqual(E.ensure_company_slug(app)[0], 0)
            self.assertEqual(read_env(app / ".env.local")["COMPANY_SLUG"], "beta")
    def test_values_set_only_in_dotenv_are_honoured(self):
        for dotenv in ("COMPANY_SLUG='beta'\n", "MC_ROUTE_COMPANY_ID='c2'\n"):
            with tempfile.TemporaryDirectory() as td:
                app = box(td, dotenv=dotenv)
                before = (app / ".env.local").read_text()
                self.assertEqual(E.ensure_company_slug(app)[0], 0, dotenv)
                self.assertEqual((app / ".env.local").read_text(), before, dotenv)   # nothing written over the .env value
                self.assertEqual((app / ".env").read_text(), dotenv)
    def test_unparseable_dotenv_stops_the_step_without_writing(self):
        with tempfile.TemporaryDirectory() as td:
            app = box(td, dotenv="export COMPANY_SLUG=beta\n")                  # cannot be proven unset, so nothing is written
            before = (app / ".env.local").read_text()
            with self.assertRaises(ValueError):
                E.ensure_company_slug(app)
            self.assertEqual((app / ".env.local").read_text(), before)
            self.assertEqual(E.main(["--app", str(app)]), 3)                     # main() turns it into a loud rc 3, never a traceback
    def test_only_dotenv_box_is_checked_and_written_to_env_local_only(self):
        with tempfile.TemporaryDirectory() as td:
            app = box(td, env=None, dotenv="MC_API_TOKEN='x'\n")
            self.assertEqual(E.ensure_company_slug(app)[0], 0)
            self.assertEqual(read_env(app / ".env.local")["COMPANY_SLUG"], "alpha")
            self.assertEqual((app / ".env").read_text(), "MC_API_TOKEN='x'\n")      # .env itself is never written
    def test_not_applicable_without_env_or_database(self):
        with tempfile.TemporaryDirectory() as td:
            app = box(td, dotenv="MC_API_TOKEN='x'\n"); (app / "mission-control.db").unlink()
            self.assertEqual(E.ensure_company_slug(app)[0], 4)
            (app / ".env.local").unlink(); (app / ".env").unlink()               # neither env file: not applicable
            self.assertEqual(E.ensure_company_slug(app)[0], 4)
            self.assertEqual(E.check_tenant_registry(app)[0], 4)


class Registry(unittest.TestCase):
    def registry_env(self, registry):
        return "MC_TENANT_REGISTRY_JSON='%s'\n" % json.dumps(registry, separators=(",", ":"))
    def test_public_host_without_access_identity_is_loud(self):
        ident = dict(kind="self", tenantId="t", companyId="c1", installationId="i")
        with tempfile.TemporaryDirectory() as td:
            app = box(td, env=self.registry_env({"client.example.test": ident, "localhost": ident}))
            rc, msg = E.check_tenant_registry(app)
            self.assertEqual(rc, 3)
            self.assertTrue(msg.startswith("CC_TENANT_REGISTRY_ACCESS_MISSING"))
            self.assertIn("audience, issuer, subjects", msg)
            self.assertNotIn("client.example.test", msg)                     # counts and field names only, never a host
    def test_registry_set_only_in_dotenv_is_checked_and_env_local_wins(self):
        ident = dict(kind="self", tenantId="t", companyId="c1", installationId="i")
        full = dict(ident, issuer="https://x.cloudflareaccess.com", audience="a", subjects=["o@example.test"])
        with tempfile.TemporaryDirectory() as td:                            # registry only in .env, no .env.local at all
            rc, msg = E.check_tenant_registry(box(td, env=None, dotenv=self.registry_env({"client.example.test": ident})))
            self.assertEqual(rc, 3); self.assertTrue(msg.startswith("CC_TENANT_REGISTRY_ACCESS_MISSING"))
        with tempfile.TemporaryDirectory() as td:                            # .env.local overrides .env, as Next.js does
            app = box(td, env=self.registry_env({"client.example.test": full}), dotenv=self.registry_env({"client.example.test": ident}))
            self.assertEqual(E.check_tenant_registry(app)[0], 0)
    def test_complete_or_absent_registry_is_quiet(self):
        full = dict(kind="self", tenantId="t", companyId="c1", installationId="i", issuer="https://x.cloudflareaccess.com", audience="a", subjects=["o@example.test"])
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(E.check_tenant_registry(box(td, env=self.registry_env({"client.example.test": full})))[0], 0)
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(E.check_tenant_registry(box(td, env="MC_API_TOKEN='x'\n"))[0], 0)

if __name__ == "__main__":
    unittest.main()
