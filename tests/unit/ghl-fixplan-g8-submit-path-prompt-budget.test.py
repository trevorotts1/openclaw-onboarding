#!/usr/bin/env python3
"""G-8 (fix plan A3, unowned): Skill 49's submit path uses the SAME `prompt-budget --check`
Skill 74 already runs, and can only ADD refusals.

FAILS before the change: `_adapter_prompt_budget` / `_adapter_path` did not exist, so Skill
49's P2 gate never asked the paid transport's own command and the two skills could hold two
different bands. A transport refusal never reached Skill 49's verdict.
"""
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROVER = ROOT / "49-signature-funnel" / "scripts" / "prove_sf_prompt_floor.py"
MODEL = "gpt-image-2-6/sunburst-text-to-image"

FAKE_ADAPTER = r'''#!/usr/bin/env python3
import json, os, sys
with open(os.environ["BLD002_ARGV_FILE"], "w") as fh:
    fh.write(json.dumps(sys.argv[1:]))
code = int(os.environ.get("BLD002_EXIT", "0"))
print(json.dumps({
    "state": "validated" if code == 0 else "fail",
    "model_id": "x",
    "warnings": [],
    "data": {"exit_code": code, "status": "PASS" if code == 0 else "BELOW_FLOOR",
             "max": 20000, "floor": 19000},
    "error": None if code == 0 else {"code": "prompt_out_of_band", "msg": "fake refusal"},
}))
sys.exit(0)
'''


def load_prover():
    spec = importlib.util.spec_from_file_location("psf_g8", PROVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def clear_cache(psf):
    cache = getattr(psf, "_ADAPTER_CACHE", None)
    if isinstance(cache, dict):
        cache.clear()


def main() -> int:
    fails = []
    psf = load_prover()

    for name in ("_adapter_prompt_budget", "_adapter_path"):
        if not hasattr(psf, name):
            fails.append("G-8: %s does not exist — Skill 49's gate never asks the transport" % name)

    with tempfile.TemporaryDirectory(prefix="bld002-g8-") as d:
        adapter = Path(d) / "kie_live_adapter.py"
        adapter.write_text(FAKE_ADAPTER, encoding="utf-8")
        argv_file = Path(d) / "argv.json"
        os.environ["KIE_LIVE_ADAPTER_PATH"] = str(adapter)
        os.environ["BLD002_ARGV_FILE"] = str(argv_file)
        os.environ["BLD002_EXIT"] = "0"
        clear_cache(psf)

        got = (psf._adapter_prompt_budget(MODEL, "x" * 100)
               if hasattr(psf, "_adapter_prompt_budget") else None)
        if not got:
            fails.append("G-8: the adapter check did not run at all")
        else:
            argv = json.loads(argv_file.read_text(encoding="utf-8"))
            if "prompt-budget" not in argv:
                fails.append("G-8: the submit path did not invoke `prompt-budget`: %r" % (argv,))
            if "--check" not in argv:
                fails.append("G-8: the submit path did not pass `--check`: %r" % (argv,))
            if MODEL not in argv:
                fails.append("G-8: the submit path did not pass the model: %r" % (argv,))
            if "-" not in argv:
                fails.append("G-8: the submit path did not read the prompt from stdin: %r" % (argv,))

        # The transport can only ADD a refusal; it never clears what the policy refused.
        os.environ["BLD002_EXIT"] = "3"
        clear_cache(psf)
        rec = {"page_type": "main", "section": 1, "text_bearing": False,
               "prompt": psf._valid_photo_prompt()}
        got_fails, _receipt = psf.evaluate_prompt(rec)
        codes = [c for c, _m in got_fails]
        if "AF-FUN-PROMPT-FLOOR" not in codes:
            fails.append("G-8: a transport refusal (exit 3) did not become AF-FUN-PROMPT-FLOOR: %r"
                         % (codes,))

    for f in fails:
        print("FAIL: " + f)
    if fails:
        return 1
    print("PASS G-8: submit path runs Skill 74 `prompt-budget --check` and adds its refusals only")
    return 0


if __name__ == "__main__":
    sys.exit(main())
