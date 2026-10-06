#!/usr/bin/env python3
"""R16: ensure_persona_contexts writes the key once, verifies, never overwrites a valid value, fails loud when undeterminable."""
import json, sqlite3, sys, tempfile, unittest
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "shared-utils"))
import ensure_persona_contexts as E
from service_env import read_env


def box(td, cfg_id="co-1", with_catalog=True):
    td = Path(td); app = td / "app"; oc = td / "oc"; app.mkdir(); (oc / "workspace/data/coaching-personas").mkdir(parents=True)
    root = oc / "workspace/zero-human-company/acme"; root.mkdir(parents=True)
    (root / "company-config.json").write_text(json.dumps({"companyId": cfg_id, "slug": "acme"}))
    if with_catalog:
        (oc / "workspace/data/coaching-personas/persona-categories.json").write_text("{}")
    (app / ".env.local").write_text("MC_API_TOKEN='x'\nZERO_HUMAN_COMPANY_DIR='%s'\n" % root)
    con = sqlite3.connect(app / "mission-control.db"); con.execute("create table workspaces(id,company_id)"); con.execute("insert into workspaces values(1,'co-1')"); con.commit(); con.close()
    return app, oc


class T(unittest.TestCase):
    def test_write_verify_idempotent_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            app, oc = box(td)
            self.assertEqual(E.run(app, oc, True)[0], 3)           # missing -> fails loudly
            rc, _ = E.run(app, oc); self.assertEqual(rc, 0)
            v = json.loads(read_env(app / ".env.local")["MC_PERSONA_COMPANY_CONTEXTS_JSON"])
            self.assertEqual(v["co-1"]["companySlug"], "acme")
            self.assertEqual(read_env(app / ".env.local")["MC_API_TOKEN"], "x")
            before = (app / ".env.local").read_text()
            self.assertEqual(E.run(app, oc)[0], 0); self.assertEqual(before, (app / ".env.local").read_text())
            self.assertEqual(E.run(app, oc, True)[0], 0)
    def test_mismatched_config_id_refused(self):
        with tempfile.TemporaryDirectory() as td:
            app, oc = box(td, cfg_id="other")
            rc, _ = E.run(app, oc); self.assertEqual(rc, 3)
            self.assertNotIn("MC_PERSONA_COMPANY_CONTEXTS_JSON", read_env(app / ".env.local"))
    def test_missing_catalog_refused(self):
        with tempfile.TemporaryDirectory() as td:
            app, oc = box(td, with_catalog=False)
            self.assertEqual(E.run(app, oc)[0], 3)

if __name__ == "__main__":
    unittest.main()
