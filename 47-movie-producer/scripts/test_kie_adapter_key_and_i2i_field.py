#!/usr/bin/env python3
"""Skill 47 adapter contracts (no network, no real key):
  1. A placeholder KIE_API_KEY (the installer writes YOUR_CLIENT_KIE_API_KEY_HERE) is
     NOT-SET for BOTH adapters and for the driver loader (shared secret canon decides).
  2. kie_image sends the documented sunburst image-to-image field `input_urls`, never the
     Nano Banana field `image_input` (checked on the createTask body Skill 74 submits).
  3. The adapter folder still holds exactly two .py files.
Run: python3 47-movie-producer/scripts/test_kie_adapter_key_and_i2i_field.py
"""
import os
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import test_kie_adapter_resultjson_decode as base  # noqa: E402  (reuse its stub + loader)

base._install_base_tool_stub()

img = base._load_module(base.IMAGE_PY, "kie_image_t")
vid = base._load_module(base.VIDEO_PY, "kie_video_t")

fails = []
def check(label, ok):
    print(("PASS " if ok else "FAIL ") + label)
    if not ok:
        fails.append(label)

PLACEHOLDER = "YOUR_CLIENT_KIE_API_KEY_HERE"
REALISH = "".join("ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"[(i * 37 + 11) % 57] for i in range(32))
old = os.environ.get("KIE_API_KEY")
try:
    os.environ["KIE_API_KEY"] = PLACEHOLDER
    check("kie_image: placeholder key is NOT-SET", img.KieImage()._get_api_key() is None)
    check("kie_video: placeholder key is NOT-SET", vid.KieVideo()._get_api_key() is None)
    os.environ["KIE_API_KEY"] = REALISH
    check("kie_image: real-shaped key accepted", img.KieImage()._get_api_key() == REALISH)
    check("kie_video: real-shaped key accepted", vid.KieVideo()._get_api_key() == REALISH)

    import video_build_check as vbc
    check("driver loader: placeholder -> not set", vbc.real_kie_key(PLACEHOLDER) is None)
    check("driver loader: real-shaped -> set", vbc.real_kie_key(REALISH) == REALISH)

    ft = base.FakeKieTransport()
    tool = base.fresh_tool(img, "KieImage", ft)
    res = tool.execute({"prompt": "p", "image_url": "https://example.invalid/ref.png",
                        "output_path": "/tmp/kie_i2i_test.png"})
    body = ft.create_calls[0] if ft.create_calls else {}
    inp = body.get("input", {})
    check("i2i run succeeded through Skill 74 (%s)" % getattr(res, "error", ""), res.success is True)
    check("i2i uses model gpt-image-2-5-sunburst-image-to-image",
          body.get("model") == "gpt-image-2-5-sunburst-image-to-image")
    check("i2i sends documented field input_urls", inp.get("input_urls") == ["https://example.invalid/ref.png"])
    check("i2i does not send Nano Banana field image_input", "image_input" not in inp)
    declared = set(img._DECLARED_INPUT_FIELDS["gpt-image-2-5-sunburst-image-to-image"])
    check("i2i input holds only schema-declared fields", set(inp) <= declared)
    check("i2i does not send undeclared output_format", "output_format" not in inp)
    ft2 = base.FakeKieTransport()
    tool = base.fresh_tool(img, "KieImage", ft2)
    tool.execute({"prompt": "p", "output_path": "/tmp/kie_t2i_test.png"})
    tin = (ft2.create_calls[0] if ft2.create_calls else {}).get("input", {})
    check("t2i input holds only schema-declared fields",
          set(tin) <= set(img._DECLARED_INPUT_FIELDS["gpt-image-2-5-sunburst-text-to-image"]))
    check("t2i does not send output_format or input_urls", "output_format" not in tin and "input_urls" not in tin)
    ft3 = base.FakeKieTransport()
    tool = base.fresh_tool(img, "KieImage", ft3)
    local = Path("/tmp/kie_local_ref_test.png")
    local.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    tool.execute({"prompt": "p", "image_path": str(local), "output_path": "/tmp/kie_i2i_local_test.png"})
    check("a local reference is uploaded through Skill 74 (authenticated base64 upload) and its URL becomes input_urls",
          bool(ft3.uploads) and ft3.create_calls[0]["input"]["input_urls"] == ["https://fixtures.example/up-kie_local_ref_test.png"])
finally:
    if old is None:
        os.environ.pop("KIE_API_KEY", None)
    else:
        os.environ["KIE_API_KEY"] = old

count = len(list(base.ADAPTERS.rglob("*.py")))
check("kie-adapters holds exactly two .py files", count == 2)
sys.exit(1 if fails else 0)
