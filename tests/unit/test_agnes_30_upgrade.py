#!/usr/bin/env python3
"""AGN-001 — the Agnes 3.0 upgrade step is idempotent, backs up before writing,
and flags (never changes) a box with no Agnes key.

Hermetic: a temp OpenClaw root, a stubbed `openclaw` CLI that applies the
`config patch --stdin` payload to the file itself (like the real CLI does),
no network, no live Agnes call, no secret value. Run:

    python3 tests/unit/test_agnes_30_upgrade.py
"""
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "shared-utils"))
import fleet_refresh_runner as fr  # noqa: E402

# A claude-code statusline-style deep-path question, long enough to not matter.
FAKE_KEY = "sk-agnes-SENTINEL-MUST-NEVER-BE-PRINTED-0123456789"

BOX_CONFIG = {
    "gateway": {"port": 18789},
    "models": {"providers": {"agnes": {
        "apiKey": FAKE_KEY,
        "baseUrl": "https://apihub.agnes-ai.com/v1",
        "models": [
            {"id": "agnes-2.5-flash", "name": "Agnes 2.5 Flash", "input": ["text"]},
            {"id": "keep-me", "name": "Keep Me"},
        ],
    }}},
    "agents": {
        "defaults": {
            "models": {
                "agnes/agnes-2.5-flash": {"alias": "Agnes 2.5 Flash"},
                "ollama-cloud/kimi-k2.7-code": {"alias": "Kimi"},
            },
            "subagents": {"model": {"primary": "agnes/agnes-2.5-flash",
                                    "fallbacks": ["ollama-cloud/kimi-k2.7-code",
                                                  "agnes/agnes-2.5-flash"]}},
        },
        "entries": {
            "dept-ceo": {"model": {"primary": "agnes/agnes-2.5-flash",
                                   "fallbacks": ["agnes/agnes-2.5-flash"]}},
            "untouched": {"model": {"primary": "openrouter/deepseek/deepseek-v4-flash"}},
        },
    },
}


def merge(target: dict, patch: dict) -> None:
    """The real CLI merges objects recursively and REPLACES arrays; a null
    value deletes the key. Enough of that to exercise the step's read-back."""
    for k, v in patch.items():
        if v is None:
            target.pop(k, None)
        elif isinstance(v, dict) and isinstance(target.get(k), dict):
            merge(target[k], v)
        else:
            target[k] = v


class Agnes30Upgrade(unittest.TestCase):
    def _setup_box(self, config: dict):
        td = Path(tempfile.mkdtemp(prefix="agnes30-"))
        self.addCleanup(shutil.rmtree, td, True)
        root = td / "oc"
        root.mkdir()
        (root / "openclaw.json").write_text(json.dumps(config))
        bindir = td / "bin"
        bindir.mkdir()
        calls = td / "calls.log"
        stub = bindir / "openclaw"
        stub.write_text(
            "#!/usr/bin/env python3\n"
            "import json, sys\n"
            f"CALLS = r'{calls}'\n"
            f"CFG = r'{root / 'openclaw.json'}'\n"
            "args = sys.argv[1:]\n"
            "with open(CALLS, 'a') as f:\n"
            "    f.write(' '.join(args) + ' DRY=' + str('--dry-run' in args) + '\\n')\n"
            "if args[:2] != ['config', 'patch']:\n"
            "    print('unexpected command', file=sys.stderr); sys.exit(2)\n"
            "raw = sys.stdin.read()\n"
            "print('--' * 20)\n"
            "print(raw)\n"
            "print('--' * 20)\n"
            "if '--dry-run' in args:\n"
            "    sys.exit(0)\n"
            "cfg = json.load(open(CFG))\n"
            "def merge(t, p):\n"
            "    for k, v in p.items():\n"
            "        if v is None: t.pop(k, None)\n"
            "        elif isinstance(v, dict) and isinstance(t.get(k), dict): merge(t[k], v)\n"
            "        else: t[k] = v\n"
            "merge(cfg, json.loads(raw))\n"
            "open(CFG, 'w').write(json.dumps(cfg, indent=2))\n"
        )
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        env = mock.patch.dict(os.environ, {"PATH": f"{bindir}:{os.environ['PATH']}"})
        env.start()
        self.addCleanup(env.stop)
        return {"root": root, "skills": root / "skills"}, calls

    def _read(self, paths) -> dict:
        return json.loads((paths["root"] / "openclaw.json").read_text())

    def _run(self, paths):
        res = fr.BoxResult("fixture-box", dry_run=False)
        cap = mock.patch("sys.stdout")
        with cap:
            fr.step_agnes_30_upgrade(paths, res, dry_run=False)
        return res, cap

    def test_upgrades_wired_box_and_preserves_everything_else(self):
        paths, calls = self._setup_box(BOX_CONFIG)
        res, _ = self._run(paths)
        cfg = self._read(paths)

        # (a) provider model list moved, nothing else in the list touched
        ids = [m["id"] for m in cfg["models"]["providers"]["agnes"]["models"]]
        self.assertEqual(ids, ["agnes-3.0-flash", "keep-me"])
        self.assertEqual(cfg["models"]["providers"]["agnes"]["models"][0]["name"],
                         "Agnes 3.0 Flash")
        self.assertEqual(cfg["models"]["providers"]["agnes"]["apiKey"], FAKE_KEY)
        self.assertEqual(cfg["models"]["providers"]["agnes"]["baseUrl"],
                         "https://apihub.agnes-ai.com/v1")
        # (b) defaults entry moved key, alias followed, old key gone
        d_models = cfg["agents"]["defaults"]["models"]
        self.assertIn("agnes/agnes-3.0-flash", d_models)
        self.assertNotIn("agnes/agnes-2.5-flash", d_models)
        self.assertEqual(d_models["agnes/agnes-3.0-flash"]["alias"], "Agnes 3.0 Flash")
        self.assertEqual(d_models["ollama-cloud/kimi-k2.7-code"], {"alias": "Kimi"})
        # (c) references in the model blocks: fallbacks AND a primary that would
        # otherwise dangle on the just-moved allowlist key
        self.assertEqual(cfg["agents"]["defaults"]["subagents"]["model"]["primary"],
                         "agnes/agnes-3.0-flash")
        self.assertEqual(cfg["agents"]["defaults"]["subagents"]["model"]["fallbacks"],
                         ["ollama-cloud/kimi-k2.7-code", "agnes/agnes-3.0-flash"])
        self.assertEqual(cfg["agents"]["entries"]["dept-ceo"]["model"]["fallbacks"],
                         ["agnes/agnes-3.0-flash"])
        self.assertEqual(cfg["agents"]["entries"]["dept-ceo"]["model"]["primary"],
                         "agnes/agnes-3.0-flash")
        # ...and only the Agnes values moved
        self.assertEqual(cfg["agents"]["entries"]["untouched"]["model"]["primary"],
                         "openrouter/deepseek/deepseek-v4-flash")
        # receipt names the backup, the backup holds the pre-write config, and
        # neither the key nor any secret value reaches the output.
        step = res.steps["agnes-30-upgrade"]
        self.assertTrue(step.startswith("ok:"), step)
        bak = Path(step.split("backup: ", 1)[1].split(")")[0].split(";")[0])
        self.assertTrue(bak.is_file(), f"backup missing: {bak}")
        self.assertEqual(json.loads(bak.read_text())["models"]["providers"]["agnes"]
                         ["models"][0]["id"], "agnes-2.5-flash")
        self.assertEqual(stat.S_IMODE(bak.stat().st_mode), 0o600)
        self.assertNotIn("sk-", step)

    def test_second_run_is_a_no_op_with_no_write_and_no_backup(self):
        paths, calls = self._setup_box(BOX_CONFIG)
        self._run(paths)
        first = self._read(paths)
        before = sorted(p.name for p in paths["root"].iterdir())
        lines = calls.read_text().count("\n")
        res2, _ = self._run(paths)
        self.assertEqual(res2.steps["agnes-30-upgrade"],
                         "ok:already at agnes-3.0-flash (no change)")
        self.assertEqual(self._read(paths), first)
        self.assertEqual(sorted(p.name for p in paths["root"].iterdir()), before)
        self.assertEqual(calls.read_text().count("\n"), lines,
                         "second run must not call the CLI at all")

    def test_no_agnes_key_is_flagged_not_changed(self):
        cfg = json.loads(json.dumps(BOX_CONFIG))
        del cfg["models"]["providers"]["agnes"]["apiKey"]
        paths, calls = self._setup_box(cfg)
        res, _ = self._run(paths)
        self.assertEqual(res.steps["agnes-30-upgrade"],
                         "skip:FLAGGED: agnes provider has no key — nothing changed")
        self.assertNotIn("failed", res.steps["agnes-30-upgrade"])
        self.assertEqual(self._read(paths), cfg)
        self.assertFalse(calls.exists(), "flagging must not call the writer")

    def test_box_without_agnes_is_never_given_agnes(self):
        cfg = json.loads(json.dumps(BOX_CONFIG))
        del cfg["models"]["providers"]["agnes"]
        paths, calls = self._setup_box(cfg)
        res, _ = self._run(paths)
        self.assertEqual(res.steps["agnes-30-upgrade"],
                         "skip:no agnes provider on this box — nothing to upgrade")
        self.assertEqual(self._read(paths), cfg)
        self.assertFalse(calls.exists())

    def test_already_extended_fallback_list_is_left_byte_for_byte(self):
        cfg = json.loads(json.dumps(BOX_CONFIG))
        cfg["models"]["providers"]["agnes"]["models"][0]["id"] = "agnes-3.0-flash"
        cfg["models"]["providers"]["agnes"]["models"][0]["name"] = "Agnes 3.0 Flash"
        cfg["agents"]["defaults"]["models"]["agnes/agnes-3.0-flash"] = \
            cfg["agents"]["defaults"]["models"].pop("agnes/agnes-2.5-flash")
        cfg["agents"]["defaults"]["subagents"]["model"]["primary"] = "agnes/agnes-3.0-flash"
        cfg["agents"]["defaults"]["subagents"]["model"]["fallbacks"] = [
            "ollama-cloud/kimi-k2.7-code", "agnes/agnes-3.0-flash"]
        cfg["agents"]["entries"]["dept-ceo"]["model"]["primary"] = "agnes/agnes-3.0-flash"
        cfg["agents"]["entries"]["dept-ceo"]["model"]["fallbacks"] = \
            ["agnes/agnes-3.0-flash", "openrouter/deepseek/deepseek-v4-flash"]
        paths, calls = self._setup_box(cfg)
        res, _ = self._run(paths)
        self.assertIn("already at agnes-3.0-flash", res.steps["agnes-30-upgrade"])
        self.assertEqual(self._read(paths), cfg)
        self.assertFalse(calls.exists())

    def test_running_twice_on_a_2_0_box_moves_2_0_and_leaves_no_2x_id(self):
        cfg = json.loads(json.dumps(BOX_CONFIG))
        cfg["models"]["providers"]["agnes"]["models"][0]["id"] = "agnes-2.0-flash"
        cfg["models"]["providers"]["agnes"]["models"][0]["name"] = "Agnes 2.0 Flash"
        cfg["agents"]["defaults"]["models"]["agnes/agnes-2.0-flash"] = \
            cfg["agents"]["defaults"]["models"].pop("agnes/agnes-2.5-flash")
        cfg["agents"]["entries"]["dept-ceo"]["model"]["fallbacks"] = \
            ["agnes/agnes-2.5-flash", "agnes/agnes-2.0-flash"]
        paths, calls = self._setup_box(cfg)
        self._run(paths)
        after = self._read(paths)
        blob = json.dumps(after)
        for old in ("agnes-2.5-flash", "agnes-2.0-flash"):
            self.assertNotIn(old, blob)
        self.assertEqual(after["agents"]["entries"]["dept-ceo"]["model"]["fallbacks"],
                         ["agnes/agnes-3.0-flash"])
        lines = calls.read_text().count("\n")
        res2, _ = self._run(paths)
        self.assertEqual(res2.steps["agnes-30-upgrade"],
                         "ok:already at agnes-3.0-flash (no change)")
        self.assertEqual(calls.read_text().count("\n"), lines)

    def test_a_refused_write_changes_nothing_and_fails_nothing(self):
        paths, calls = self._setup_box(BOX_CONFIG)
        cfg_before = self._read(paths)
        stub = Path(os.environ["PATH"].split(":")[0]) / "openclaw"
        # A build that rejects the patch: --dry-run exits 0, the real call is refused.
        stub.write_text(
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "args = sys.argv[1:]\n"
            f"open(r'{calls}', 'a').write(' '.join(args) + '\\n')\n"
            "sys.stdin.read()\n"
            "if '--dry-run' not in args:\n"
            "    print('unknown config path agents.entries', file=sys.stderr)\n"
            "    sys.exit(2)\n"
        )
        res, _ = self._run(paths)
        self.assertEqual(self._read(paths), cfg_before)
        step = res.steps["agnes-30-upgrade"]
        self.assertTrue(step.startswith("skip:"), step)
        self.assertNotIn("failed", step)
        # The backup made right before the refused write is not left behind.
        self.assertEqual(sorted(p.name for p in paths["root"].iterdir()), ["openclaw.json"])

    def test_dry_run_records_the_skip_and_touches_nothing(self):
        paths, calls = self._setup_box(BOX_CONFIG)
        cfg_before = self._read(paths)
        res = fr.BoxResult("fixture-box", dry_run=True)
        cap = mock.patch("sys.stdout")
        with cap:
            fr.step_agnes_30_upgrade(paths, res, dry_run=True)
        self.assertEqual(res.steps["agnes-30-upgrade"], "skip:dry-run")
        self.assertEqual(self._read(paths), cfg_before)
        self.assertFalse(calls.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
