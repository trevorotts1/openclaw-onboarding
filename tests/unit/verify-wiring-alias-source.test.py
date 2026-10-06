#!/usr/bin/env python3
"""Regression test: verify-wiring.sh connection hooks may name their alias canon by
reference (alias_source) instead of restating cfg_key_aliases.

Cases (all against a temp tree holding a copy of the real embedded python block):
  1. no KIE key anywhere                     -> FAIL
  2. alias-only key (KIE_KEY)                -> OK "via alias"
  3. canonical key (KIE_API_KEY)             -> OK, no alias
  4. canon file missing + alias-only key     -> FAIL (fail-closed)
"""
import json, os, subprocess, sys, tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = (REPO / "23-ai-workforce-blueprint/scripts/verify-wiring.sh").read_text(encoding="utf-8")
i = SRC.index("def _alias_source_keys")
start = SRC.rfind("<<'PYEOF' 2>&1\n", 0, i) + len("<<'PYEOF' 2>&1\n")
end = SRC.index("\nPYEOF", i)
BLOCK = SRC[start:end] + "\n"

CANON = {"canonical_names": {"KIE_API_KEY": ["KIE_API_KEY", "KIE_KEY", "KIE_AI_API_KEY"]}}
MANIFEST = {"dept": "t", "connection_points": [{
    "name": "kie-api-key", "description": "kie", "cfg_key": "env.vars.KIE_API_KEY",
    "alias_source": "shared-utils/secret_names.json", "required": True}]}
VAL = "zzTESTvalue0123456789"


def run(vars_, with_canon):
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        (t / "home").mkdir()
        mdir = t / "tree/role-library/t"
        mdir.mkdir(parents=True)
        if with_canon:
            (t / "tree/shared-utils").mkdir()
            (t / "tree/shared-utils/secret_names.json").write_text(json.dumps(CANON))
        (mdir / "connection-manifest.json").write_text(json.dumps(MANIFEST))
        (t / "cfg.json").write_text(json.dumps({"env": {"vars": vars_}}))
        (t / "blk.py").write_text(BLOCK, encoding="utf-8")
        p = subprocess.run([sys.executable, str(t / "blk.py"), str(mdir / "connection-manifest.json"),
                            str(t / "cfg.json"), "t"], capture_output=True, text=True,
                           env={"HOME": str(t / "home"), "PATH": os.environ.get("PATH", "")})
        return p.stdout + p.stderr


def verdict(out):
    return json.loads([l for l in out.splitlines() if l.startswith("{")][-1])["pass"]


fails = []
o = run({}, True)
if verdict(o): fails.append("1 no key should fail")
o = run({"KIE_KEY": VAL}, True)
if not verdict(o) or "via alias env.vars.KIE_KEY" not in o: fails.append("2 alias-only should pass via alias: " + o)
o = run({"KIE_API_KEY": VAL}, True)
if not verdict(o) or "via alias" in o: fails.append("3 canonical should pass without alias: " + o)
o = run({"KIE_KEY": VAL}, False)
if verdict(o): fails.append("4 missing canon + alias-only should fail")
if fails:
    print("FAIL", *fails, sep="\n  "); sys.exit(1)
print("PASS: verify-wiring alias_source (4/4)")
