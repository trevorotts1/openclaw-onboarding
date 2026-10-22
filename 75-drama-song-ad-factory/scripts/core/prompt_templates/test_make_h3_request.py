#!/usr/bin/env python3
"""Guard: the H3 request builder is the only supported H3 path.

Asserts the whole chain end to end on the golden fixture: assemble_h3 ->
band PASS -> receipt -> a request object that kie_dispatch's own gates accept
(prompt cap, prompt receipt, model lock family), and that the builder refuses
to substitute another model. A regression that re-caps H3 as Hailuo, drops the
receipt, or silently swaps the model fails here.

Stdlib only, offline, no spend.
Run: python3 scripts/core/prompt_templates/test_make_h3_request.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(CORE))
FIX = os.path.join(ROOT, "references", "prompt-templates", "fixtures", "h3-specs")
CLI = os.path.join(HERE, "make_h3_request.py")

for p in (CORE, os.path.join(CORE, "kie_dispatch"), HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

FS = []


def check(name, cond, detail=""):
    print(("ok " if cond else "FAIL ") + name + ((" -- %s" % (detail,)) if detail and not cond else ""))
    if not cond:
        FS.append(name)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


spec_path = os.path.join(FIX, "talking-closeup-S07.json")
chars_path = os.path.join(FIX, "sample-characters.json")
out = "/tmp/h3-guard-request.json"

rc = subprocess.run([sys.executable, CLI, "--spec", spec_path,
                     "--characters", chars_path,
                     "--first-frame-url", "https://example.com/frame.webp",
                     "--out", out], capture_output=True, text=True)
check("1: builder exits 0 on a golden H3 spec", rc.returncode == 0, rc.stdout + rc.stderr)
req = json.load(open(out)) if os.path.exists(out) else {}
prompt = (req.get("input") or {}).get("prompt") or ""

check("2: model is the canonical H3 id", req.get("model") == "minimax-h3/image-to-video", req.get("model"))
check("3: prompt is inside the H3 band 5000-6800", 5000 <= len(prompt) <= 6800, len(prompt))
check("4: request carries a prompt receipt", isinstance(req.get("prompt_receipt"), dict))

import hashlib
sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
check("5: receipt sha matches the prompt",
      (req.get("prompt_receipt") or {}).get("prompt_sha256") == sha)

KD = load("kd_h3_guard", os.path.join(CORE, "kie_dispatch", "kie_dispatch.py"))
cap_ref, _rows = KD.prompt_cap_rows("minimax-h3/image-to-video", req)
check("6: H3 prompt cap gate passes", cap_ref is None, cap_ref)
tpl = KD.prompt_templated_refusal("minimax-h3/image-to-video", req, prompt)
check("7: prompt receipt gate passes", tpl is None, tpl)

# 8. The receipt gate still bites when the prompt changes after assembly.
tampered = json.loads(json.dumps(req))
tampered["input"]["prompt"] = prompt[:-1] + "X"
check("8: a changed prompt is refused",
      (KD.prompt_templated_refusal("minimax-h3/image-to-video", tampered,
                                   tampered["input"]["prompt"]) or {}).get("reason_code")
      == "PROMPT_NOT_TEMPLATED")

# 9. The builder refuses a non-H3 model instead of substituting one.
spec = json.load(open(spec_path))
spec["model"] = "hailuo/02-image-to-video-standard"
open("/tmp/h3-guard-bad-spec.json", "w").write(json.dumps(spec))
rc2 = subprocess.run([sys.executable, CLI, "--spec", "/tmp/h3-guard-bad-spec.json",
                      "--characters", chars_path,
                      "--first-frame-url", "https://example.com/frame.webp",
                      "--out", "/tmp/h3-guard-bad.json"], capture_output=True, text=True)
check("9: a Hailuo model id is refused, never silently used", rc2.returncode == 2, rc2.stdout)

print()
if FS:
    print("%d FAILED: %s" % (len(FS), ", ".join(FS)))
    raise SystemExit(1)
print("ALL PASS")
