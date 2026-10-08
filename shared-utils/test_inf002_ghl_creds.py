"""INF002: one Convert and Flow credential lookup. Location id under every name in every
store; else the pit- token -> its location through the GHL API (cached, never printed);
neither -> status missing (install with a note). Hermetic: temp stores, fake http."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ghl_creds as g  # noqa: E402

LOC = "Zq7Lk2Mx9Pd4Rt6Vb8Nc"
PIT = "pit-" + "0a1b2c3d-4e5f-6789-abcd-ef0123456789"


def _res(files, env=None, http=None, cache=None, use_api=True):
    with tempfile.TemporaryDirectory() as d:
        paths = []
        for rel, body in files.items():
            p = Path(d) / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body)
            paths.append(str(p))
        g._MEMO.clear()
        return g.resolve(environ=env or {}, stores=paths, http=http,
                         cache_path=cache, use_api=use_api)


def _one_location(pit_seen):
    def http(url, pit):
        pit_seen.append(pit)
        return 200, json.dumps({"locations": [{"id": LOC, "name": "x"}]})
    return http


class Names(unittest.TestCase):
    def test_every_name_in_every_store(self):
        for name in ("GHL_LOCATION_ID", "GOHIGHLEVEL_LOCATION_ID", "GOHIGHLEVEL_ALLOWED_LOCATION_IDS",
                     "CONVERT_AND_FLOW_LOCATION_ID", "convert_and_flow_location"):
            for store in ("secrets/.env", ".env", "workspace/.env", "workspace/secrets/.env",
                          "workspace/secrets.env", "clawd/secrets/.env",
                          "service-env/ai.openclaw.gateway.env"):
                with self.subTest(name=name, store=store):
                    r = _res({store: f"export {name}='{LOC}'\n"}, use_api=False)
                    self.assertEqual((r["status"], r["location_id"]), ("ok", LOC))
                    self.assertIn(name, r["location_source"])

    def test_allowed_list_takes_first_id(self):
        r = _res({".env": f"GOHIGHLEVEL_ALLOWED_LOCATION_IDS={LOC},Other0000000000000\n"}, use_api=False)
        self.assertEqual(r["location_id"], LOC)

    def test_env_wins_and_real_store_value_beats_placeholder(self):
        r = _res({".env": f"GHL_LOCATION_ID={LOC}\n"}, env={"GOHIGHLEVEL_LOCATION_ID": "short"}, use_api=False)
        self.assertEqual(r["location_id"], LOC)

    def test_store_list_has_container_and_mac_roots(self):
        sp = g.store_paths()
        for frag in ("/data/.openclaw/secrets/.env", "/home/node/.openclaw/.env",
                     "/workspace/secrets.env", "/workspace/secrets/.env",
                     "clawd/secrets/.env", "service-env/ai.openclaw.gateway.env"):
            self.assertTrue(any(p.endswith(frag) for p in sp), frag)


class PitFallback(unittest.TestCase):
    def test_pit_resolves_its_location_once_and_caches_without_the_token(self):
        seen = []
        with tempfile.TemporaryDirectory() as d:
            cache = str(Path(d) / "state" / "c.json")
            r = _res({"secrets/.env": f"CONVERT_AND_FLOW_API_KEY={PIT}\n"}, http=_one_location(seen), cache=cache)
            self.assertEqual((r["status"], r["location_id"]), ("ok", LOC))
            self.assertIn("api:/locations/search", r["location_source"])
            self.assertEqual(seen, [PIT])
            txt = Path(cache).read_text()
            self.assertIn(LOC, txt)
            self.assertNotIn(PIT, txt)
            # second call: memory/state, no second API call
            g._MEMO.clear()
            r2 = g.resolve(environ={}, stores=[], http=lambda *a: self.fail("api called"),
                           cache_path=cache)
            self.assertEqual(r2["status"], "missing")      # no PIT in this call -> nothing to look up
            r3 = g.resolve(environ={"GHL_PRIVATE_TOKEN": PIT}, stores=[], http=lambda *a: self.fail("api called"),
                           cache_path=cache)
            self.assertEqual(r3["location_id"], LOC)
            self.assertEqual(r3["location_source"], "state-cache")

    def test_every_pit_name(self):
        for name in ("GHL_API_KEY", "GOHIGHLEVEL_API_KEY", "GHL_PRIVATE_TOKEN", "GOHIGHLEVEL_CF_PIT",
                     "CONVERT_AND_FLOW_API_KEY"):
            with self.subTest(name=name):
                r = _res({".env": f"{name}={PIT}\n"}, http=_one_location([]), cache=None)
                self.assertEqual(r["location_id"], LOC)

    def test_agency_token_or_offline_or_denied_is_unresolved_not_a_guess(self):
        many = lambda u, p: (200, json.dumps({"locations": [{"id": LOC}, {"id": "B" * 20}]}))
        for http in (many, lambda u, p: (0, ""), lambda u, p: (403, "")):
            r = _res({".env": f"GHL_API_KEY={PIT}\n"}, http=http, cache=None)
            self.assertEqual((r["status"], r["location_id"]), ("unresolved", None))
            self.assertIn("GOHIGHLEVEL_LOCATION_ID", r["note"])

    def test_placeholder_token_is_not_a_token(self):
        for bad in ("pit-abc123", "pit-your-token-here-xxxxxxxxxxxxxx", "not-a-pit-token-0123456789"):
            r = _res({".env": f"GHL_API_KEY={bad}\n"}, http=lambda *a: self.fail("api called"), cache=None)
            self.assertEqual(r["status"], "missing")

    def test_agency_pit_names_are_never_used(self):
        r = _res({".env": f"GOHIGHLEVEL_AGENCY_PIT={PIT}\n"}, http=lambda *a: self.fail("api called"), cache=None)
        self.assertEqual(r["status"], "missing")

    def test_neither_is_missing_with_the_note(self):
        r = _res({".env": "OTHER=1\n"}, cache=None)
        self.assertEqual(r["status"], "missing")
        self.assertIn("needed", r["note"])


class ShellFace(unittest.TestCase):
    def _run(self, home, extra=""):
        script = f'. "{HERE}/ghl-creds.sh"; ghl_creds_resolve; echo "S=$GHL_CREDS_STATUS L=${{GOHIGHLEVEL_LOCATION_ID:-}}"; {extra}'
        env = {"PATH": os.environ["PATH"], "HOME": home}
        return subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True)

    def test_keyless_home_is_missing(self):
        with tempfile.TemporaryDirectory() as d:
            r = self._run(d)
            self.assertIn("S=missing L=", r.stdout)

    def test_stored_location_is_exported_and_pit_never_printed(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".openclaw").mkdir()
            (Path(d) / ".openclaw" / ".env").write_text(f"GHL_LOCATION_ID={LOC}\nGHL_API_KEY={PIT}\n")
            r = self._run(d)
            self.assertIn(f"S=ok L={LOC}", r.stdout)
            self.assertNotIn(PIT, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
