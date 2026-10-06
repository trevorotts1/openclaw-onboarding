#!/usr/bin/env python3
"""test_kie_embedded_client_hashlock.py - the embedded Skill 74 client in kie_image.py
cannot drift from Skill 74's source, and both adapters behave the same on either path.

The OpenMontage clone and the Docker image carry only the two files under kie-adapters/,
so a copy of Skill 74's client travels inside kie_image.py (kie_video.py reads it from
there). scripts/embed_kie_client.py generates that block. This test is the lock:

  1. The block in kie_image.py equals what the generator builds from the CURRENT
     74-kie-live-adapter/scripts/kie_live_adapter.py, byte for byte.
  2. The sha256 stamped in the block equals the sha256 of the section text, and that
     text appears verbatim, contiguously, in Skill 74's source (it starts at the
     `import argparse` line and ends with the Adapter class, before the CLI banner).
  3. Mutation proof: flipping one character in the block, or in a copy of Skill 74's
     source, makes the verifier fail (the check can fail).
  4. Both adapters take the embedded path when Skill 74 is absent, and the Skill 74 path
     when it is present, and the createTask bodies they send are identical either way.
  5. kie-adapters holds exactly two .py files.

Run:  python3 47-movie-producer/scripts/test_kie_embedded_client_hashlock.py
Exit: 0 = all pass; 1 = a failure.
"""
from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import embed_kie_client as gen  # noqa: E402
import test_kie_adapter_resultjson_decode as base  # noqa: E402

_PASS = 0
_FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {label}")
    else:
        _FAIL += 1
        print(f"  FAIL  {label}  {detail}")


def verify(target_text: str, source_text: str, version: str) -> list[str]:
    """Problems found (empty = the embedded copy is locked to the source)."""
    problems = []
    block = gen.current_block(target_text)
    if block is None:
        return ["no embedded block in kie_image.py"]
    if block != gen.build_block(source_text, version):
        problems.append("block differs from the generator output for the current Skill 74 source")
    body = block.split("\n", 4)[4].rsplit(gen.END, 1)[0]
    stamped = next((ln.split('"')[1] for ln in block.split("\n") if ln.startswith("_EMBEDDED_CLIENT_SHA256")), "")
    if stamped != hashlib.sha256(body.encode("utf-8")).hexdigest():
        problems.append("stamped sha256 does not match the embedded text")
    if body not in source_text:
        problems.append("embedded text is not a verbatim slice of Skill 74's source")
    return problems


def main() -> int:
    base._install_base_tool_stub()
    target_text = gen.TARGET.read_text(encoding="utf-8")
    if not gen.SRC.is_file() or not gen.SECRET_SRC.is_file():
        # An installed Skill 47 without Skill 74 beside it: only the stamp can be checked here.
        print("== Skill 74 or shared-utils not present beside this skill: checking the stamps only ==")
        block = gen.current_block(target_text) or ""
        body = block.split("\n", 4)[4].rsplit(gen.END, 1)[0] if block else ""
        stamped = next((ln.split('"')[1] for ln in block.split("\n") if ln.startswith("_EMBEDDED_CLIENT_SHA256")), "")
        check("stamped sha256 equals the sha256 of the embedded text", bool(body) and stamped == hashlib.sha256(body.encode("utf-8")).hexdigest())
        sblock = gen.current_block(target_text, gen.SECRET_BEGIN, gen.SECRET_END) or ""
        sbody = sblock.split("\n", 7)[7].rsplit(gen.SECRET_END, 1)[0] if sblock else ""
        sstamp = next((ln.split('"')[1] for ln in sblock.split("\n") if ln.startswith("_EMBEDDED_SECRET_HELPER_SHA256")), "")
        check("secret-helper stamp equals the sha256 of its embedded text", bool(sbody) and sstamp == hashlib.sha256(sbody.encode("utf-8")).hexdigest())
        print(f"\n{_PASS} passed, {_FAIL} failed")
        return 1 if _FAIL else 0
    src_text = gen.SRC.read_text(encoding="utf-8")
    version = gen.VERSION_FILE.read_text().strip()

    print("== the embedded block is locked to Skill 74's source ==")
    problems = verify(target_text, src_text, version)
    check("block equals the generator output; hash stamp and verbatim-slice checks hold " + (str(problems) if problems else ""), not problems)
    section = gen.extract_section(src_text)
    check("section starts at the import line and ends inside the Adapter class region (no CLI code)",
          section.startswith("import argparse") and "def main(" not in section and "class Adapter:" in section)
    check("--check mode exits 0 (client and secret helper)", gen.main(["--check"]) == 0)

    print("== mutation proof: the lock can fail ==")
    mutated_block = target_text.replace("MAX_UPLOAD = 512 * 1024 * 1024", "MAX_UPLOAD = 513 * 1024 * 1024", 1)
    check("a one-character change inside the embedded block is caught", bool(verify(mutated_block, src_text, version)))
    mutated_src = src_text.replace("CATALOG_TTL = 6 * 3600", "CATALOG_TTL = 7 * 3600", 1)
    check("a change to Skill 74's source (copy not regenerated) is caught", bool(verify(target_text, mutated_src, version)))

    print("== the embedded secret helper is locked to shared-utils/secret_helper.py ==")
    sec_src = gen.SECRET_SRC.read_text(encoding="utf-8")
    sec_block = gen.current_block(target_text, gen.SECRET_BEGIN, gen.SECRET_END)
    check("secret-helper block equals the generator output for the current shared-utils source",
          sec_block == gen.build_secret_block(sec_src))
    sec_body = gen.extract_secret_section(sec_src)
    stamped = next((ln.split('"')[1] for ln in (sec_block or "").split("\n") if ln.startswith("_EMBEDDED_SECRET_HELPER_SHA256")), "")
    check("secret-helper stamp equals the sha256 of the verbatim slice, and the slice sits in the source",
          stamped == hashlib.sha256(sec_body.encode("utf-8")).hexdigest() and sec_body in sec_src and sec_body in (sec_block or ""))
    check("a one-character change in the embedded secret helper is caught",
          gen.build_secret_block(sec_src) != (sec_block or "").replace("(?:test|xxx|example|replace)", "(?:test|xxx|example|replaced)", 1))
    check("a change to shared-utils/secret_helper.py (copy not regenerated) is caught",
          gen.build_secret_block(sec_src.replace("3.0 bits/char", "2.0 bits/char", 1).replace("< 3.0", "< 2.0", 1)) != sec_block)
    sys.path.insert(0, str(gen.REPO / "shared-utils"))
    import secret_helper as shared  # noqa: E402
    ns = base._load_module(Path(gen.TARGET), "kie_image_parity")
    gate = ns.looks_like_real_key
    battery = [base.FIXTURE_KEY, "YOUR_CLIENT_KIE_API_KEY_HERE", "short", "", "aaaaaaaaaaaaaaaaaaaaaaaaaaaa", "PASTE_REAL_TOKEN",
               "sk-" + base.FIXTURE_KEY, "demo" + base.FIXTURE_KEY, base.FIXTURE_KEY + "-your_key", "<TODO>", "x" * 40, base.FIXTURE_KEY[:20]]
    check("the embedded gate agrees with shared-utils looks_like_real_key on the whole battery",
          all(gate(v, "KIE_API_KEY") == shared.looks_like_real_key(v, "KIE_API_KEY") for v in battery))

    print("== both adapters pick the right path and send identical bodies on either ==")
    img = base._load_module(base.IMAGE_PY, "kie_image_hashlock")
    vid = base._load_module(base.VIDEO_PY, "kie_video_hashlock")
    tmp = Path(tempfile.mkdtemp(prefix="kie47-hashlock-"))
    sent = {}
    for label, skill74_dir in (("skill74", None), ("embedded", "")):
        ft = base.FakeKieTransport()
        r1 = base.fresh_tool(img, "KieImage", ft, skill74_dir).execute({"prompt": "a red barn", "output_path": str(tmp / f"{label}.png")})
        path_img = img._kie_client()[1]
        ft2 = base.FakeKieTransport()
        r2 = base.fresh_tool(vid, "KieVideo", ft2, skill74_dir).execute({
            "prompt": "a calm lake", "model": "bytedance/seedance-1.5-pro", "output_path": str(tmp / f"{label}.mp4")})
        path_vid = vid._kie_client()[1]
        check(f"[{label}] image and video both ran on the {label} path", path_img == label and path_vid == label and r1.success and r2.success,
              detail=f"{path_img}/{path_vid} {getattr(r1, 'error', '')} {getattr(r2, 'error', '')}")
        check(f"[{label}] ToolResult.data names the client path", r1.data.get("kie_client_path") == label and r2.data.get("kie_client_path") == label)
        sent[label] = (ft.create_calls, ft2.create_calls)
    check("createTask bodies are identical on the skill74 and embedded paths", sent["skill74"] == sent["embedded"])

    print("== clone / Docker layout: only the two copied files, no Skill 74 on the box ==")
    clone = Path(tempfile.mkdtemp(prefix="kie47-clone-"))
    (clone / "tools" / "graphics").mkdir(parents=True)
    (clone / "tools" / "video").mkdir(parents=True)
    (clone / "tools" / "graphics" / "kie_image.py").write_text(base.IMAGE_PY.read_text(encoding="utf-8"), encoding="utf-8")
    (clone / "tools" / "video" / "kie_video.py").write_text(base.VIDEO_PY.read_text(encoding="utf-8"), encoding="utf-8")
    cimg = base._load_module(clone / "tools" / "graphics" / "kie_image.py", "clone_kie_image")
    cvid = base._load_module(clone / "tools" / "video" / "kie_video.py", "clone_kie_video")
    ft = base.FakeKieTransport()
    ri = base.fresh_tool(cimg, "KieImage", ft, "").execute({"prompt": "a red barn", "output_path": str(clone / "i.png")})
    rv = base.fresh_tool(cvid, "KieVideo", base.FakeKieTransport(), "").execute({"prompt": "a calm lake", "output_path": str(clone / "v.mp4")})
    check("the copied kie_image.py runs on the embedded client alone (%s)" % getattr(ri, "error", ""), ri.success and ri.data["kie_client_path"] == "embedded")
    check("the copied kie_video.py finds the embedded client in its sibling kie_image.py (%s)" % getattr(rv, "error", ""),
          rv.success and rv.data["kie_client_path"] == "embedded")

    print("== no second HTTP client in the wrappers ==")
    for name, path in (("kie_video.py", base.VIDEO_PY), ("kie_image.py", base.IMAGE_PY)):
        text = path.read_text(encoding="utf-8")
        check(f"{name} does not import requests", "import requests" not in text)
    check("kie_video.py has no urllib/http client of its own (Skill 74 Adapter.call is the only transport)",
          "urllib.request" not in base.VIDEO_PY.read_text(encoding="utf-8"))

    count = len(list(base.ADAPTERS.rglob("*.py")))
    check("kie-adapters holds exactly two .py files", count == 2)

    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
