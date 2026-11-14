"""PD-215 -- honest infographic status, a real logo web address or a clear stop, no adopted strays.

What is pinned here, all offline (every paid call is stubbed, and the HTTP transport
is asserted never reached):

  1. the status record says `render_verified`; it never says `qc_passed` -- a script
     that grades itself "QC passed" is a lie the next phase learns to trust;
  2. a logo named as a LOCAL file with no web address anywhere exits 1 and writes
     nothing, before any paid call is set up (Kie image-to-image takes URLs, not paths);
  3. that same local logo IS used once working/copy/assets_manifest.json records its
     public_url;
  4. a PNG sitting at the output path with no completed task record is re-rendered,
     never adopted as a prior render -- and a render whose sha256 IS recorded is still
     reused, so idempotency is not simply switched off;
  5. a measured shape outside the 9:16 tolerance exits 1 AFTER the file and the status
     are written, with the measured size and dimensions on disk.

Nothing here calls a live service or needs a key.
"""
from __future__ import annotations

import json
import struct
import sys
import zlib
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_infographic as bi  # noqa: E402


def _png(width: int, height: int, floor: int = bi.PNG_MIN_BYTES) -> bytes:
    """A structurally real PNG header (signature + IHDR) padded past the 102,400-byte
    floor: enough for verify_png's magic/floor gates and prompt_gate's IHDR read."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    pad = chunk(b"tEXt", b"pad\x00" + b"x" * max(0, floor))
    return b"\x89PNG\r\n\x1a\n" + ihdr + pad + chunk(b"IEND", b"")


def _seed_run(tmp_path: Path) -> Path:
    """A run dir with a prompt that clears the shared rich-prompt gate (the built-in
    selftest prompt is the fixture the script itself proves passes)."""
    rd = tmp_path / "run"
    for sub in ("working/prompts", "working/copy", "working/checkpoints"):
        (rd / sub).mkdir(parents=True, exist_ok=True)
    (rd / "working" / "prompts" / "infographic-prompt.txt").write_text(
        bi.selftest_prompt())
    return rd


def _out_path(rd: Path) -> Path:
    return rd / "working" / "deliverables" / "infographic.png"


def _stub_transport(monkeypatch, png_bytes: bytes) -> list:
    """Replace the whole paid path. Returns the list of submissions, so a test can
    assert a render happened (or never happened)."""
    calls: list = []

    def never(*_a, **_k):  # the raw transport must never be reached
        raise AssertionError("the paid HTTP transport was reached")

    def submit(prompt, api_key, logo_url=None, model_t2i=None, model_i2i=None,
               aspect_ratio=None):
        calls.append({"logo_url": logo_url})
        return "stub-task"

    def download(url, dest, api_key):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(png_bytes)
        return dest.stat().st_size

    monkeypatch.setattr(bi, "_http_json", never)
    monkeypatch.setattr(bi, "load_api_key", lambda: "stub-key")
    monkeypatch.setattr(bi, "_resolve_image_models", lambda: ("stub-t2i", "stub-i2i"))
    monkeypatch.setattr(bi, "submit_task", submit)
    monkeypatch.setattr(bi, "poll_task", lambda task_id, api_key: "https://cdn.example/i.png")
    monkeypatch.setattr(bi, "download_image", download)
    return calls


# 1 -- the status says what the script proved, not a QC verdict it never received.
def test_status_records_render_verified_and_never_qc_passed(tmp_path):
    rd = _seed_run(tmp_path)
    out = _out_path(rd)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(_png(1440, 2560))

    bi._write_status(rd, fmt="checklist", deliverable=out,
                     shape=bi.verify_infographic_shape(out),
                     size_bytes=out.stat().st_size)

    status = json.loads((rd / bi.STATUS_REL).read_text())
    assert status["render_verified"] is True
    assert status["status"] == "ready"
    assert "qc_passed" not in status
    assert status["size_bytes"] == out.stat().st_size
    assert status["actual_width_px"] == 1440


# 2 -- a local logo with no web address is a clear stop, not a silent text-to-image.
def test_local_logo_with_no_web_address_exits_1_before_any_paid_call(
        tmp_path, monkeypatch, capsys):
    rd = _seed_run(tmp_path)
    local = tmp_path / "client-logo.png"
    local.write_bytes(_png(512, 512))
    (rd / "working" / "copy" / "intake.json").write_text(
        json.dumps({"brand": {"logo_image_path": str(local)}}))
    calls = _stub_transport(monkeypatch, _png(1440, 2560))

    with pytest.raises(SystemExit) as exc:
        bi.run(rd)

    assert exc.value.code == 1
    assert calls == [], "no render may be submitted when the logo has no web address"
    assert not (rd / bi.STATUS_REL).exists(), "nothing was produced, so nothing is claimed"
    assert bi._read_pending_tasks(rd) == {}
    assert not _out_path(rd).exists()
    err = capsys.readouterr().err
    assert "the infographic needs the logo as a web address" in err
    assert "none is recorded for this run" in err


# 3 -- the recorded public_url is the web address the local logo rides.
def test_local_logo_uses_the_assets_manifest_public_url(tmp_path, monkeypatch):
    rd = _seed_run(tmp_path)
    local = tmp_path / "client-logo.png"
    local.write_bytes(_png(512, 512))
    (rd / "working" / "copy" / "intake.json").write_text(
        json.dumps({"brand": {"logo_image_path": str(local)}}))
    (rd / "working" / "copy" / "assets_manifest.json").write_text(json.dumps({
        "assets_provided": True,
        "assets": [{"kind": "brand-logo",
                    "public_url": "https://cdn.example/logo.png",
                    "consumed_by": ["slide-image-creator"]}],
    }))

    assert bi.resolve_logo(rd) == "https://cdn.example/logo.png"

    calls = _stub_transport(monkeypatch, _png(1440, 2560))
    assert bi.run(rd) == 0
    assert calls and calls[0]["logo_url"] == "https://cdn.example/logo.png"


# 4a -- a stray PNG at the output path proves nothing and is re-rendered.
def test_stray_png_with_no_task_record_is_rendered_again(tmp_path, monkeypatch):
    rd = _seed_run(tmp_path)
    out = _out_path(rd)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(_png(1440, 2560, floor=200_000))  # big and valid-looking, not ours
    stray = out.read_bytes()
    calls = _stub_transport(monkeypatch, _png(1440, 2560, floor=150_000))

    assert bi.run(rd) == 0
    assert calls, "no completed task record -> the run must render, not adopt the stray"
    assert out.read_bytes() != stray


# 4b -- control: a recorded sha256 still means reuse, no paid call.
def test_a_recorded_completed_render_is_reused_without_a_paid_call(tmp_path, monkeypatch):
    rd = _seed_run(tmp_path)
    out = _out_path(rd)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(_png(1440, 2560))
    (rd / "working" / "checkpoints" / "pending_tasks.json").write_text(json.dumps({
        "infographic": {"task_id": "stub-task", "completed": True,
                        "sha256": bi.hashlib_sha256(out)}}))
    calls = _stub_transport(monkeypatch, _png(1440, 2560, floor=150_000))

    assert bi.run(rd) == 0
    assert calls == [], "a proven render must not be re-bought"


# 5 -- the wrong shape is refused, but only after the file and the status exist.
def test_shape_outside_tolerance_exits_1_after_writing_file_and_status(
        tmp_path, monkeypatch, capsys):
    rd = _seed_run(tmp_path)
    calls = _stub_transport(monkeypatch, _png(1920, 1080))  # 16:9, not the 9:16 poster

    assert bi.run(rd) == 1
    assert calls, "the render happened; only its shape is refused"

    out = _out_path(rd)
    assert out.is_file(), "the file is written before the shape verdict is acted on"
    status = json.loads((rd / bi.STATUS_REL).read_text())
    assert status["actual_width_px"] == 1920
    assert status["actual_height_px"] == 1080
    assert status["actual_ratio_ok"] is False
    assert status["render_verified"] is False
    assert status["size_bytes"] == out.stat().st_size
    assert "outside" in capsys.readouterr().err
    # A refused render is never recorded complete, so a resume re-renders it.
    assert bi._read_pending_tasks(rd).get(bi.PENDING_KEY, {}).get("completed") is not True
