"""PD-091 — client photos reach the image service as reference images.

Acceptance row A1 (01-BUILD-SPEC.md, section PD-091, quoted verbatim):

  "Acceptance (stubbed HTTP): a slide with two references posts three `input_urls`
   in order; an asset in no slide fails AF-MANIFEST-UNREFERENCED; slides with no
   references post the text-to-image payload unchanged (compare with a recorded
   payload from before the change)."

The proof is the WIRE, not a return value: every createTask body the stub service
receives is recorded, so the three assertions below read the payload KIE would
actually have been sent.

Before PD-091 a slide row's ``reference_urls`` was never read at all: the payload
carried no ``input_urls`` (no logo) or only ``[logo]`` (logo), the model was never
the image-to-image id for a photo-only slide, and an asset whose public_url was
wired to no slide passed the manifest gate on its consumed_by list alone. All three
assertions go RED on the pre-fix file.
"""
import json
import sys
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

import build_deck as bd  # noqa: E402

LOGO = "https://cdn.example.com/logo.png"
REF1 = "https://cdn.example.com/client-photo-1.png"
REF2 = "https://cdn.example.com/client-photo-2.png"


class _StubService:
    """createTask records the exact payload; recordInfo always succeeds."""

    def __init__(self):
        self.payloads = []
        self._seq = 0

    def createTask(self, body):
        self.payloads.append(body)
        self._seq += 1
        return {"code": 200, "data": {"taskId": f"task-{self._seq}"}}

    def recordInfo(self):
        return {"code": 200, "data": {
            "state": "success",
            "resultJson": json.dumps(
                {"resultUrls": [f"https://cdn.example.com/out-{self._seq}.png"]}),
        }}


def _install(monkeypatch):
    svc = _StubService()

    def _fake_http_json(method, url, api_key, body=None):
        if "recordInfo" in url:
            return svc.recordInfo()
        if "createTask" in url:
            return svc.createTask(body)
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr(bd, "_http_json", _fake_http_json)

    def _fake_download(url, dest, api_key=None):
        Path(dest).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)

    monkeypatch.setattr(bd, "download_image", _fake_download)
    monkeypatch.setattr(bd, "load_rich_prompt",
                        lambda slide, run_dir: f"prompt-{int(slide['slide'])}")
    monkeypatch.setattr(bd, "_verify_aspect_and_readback", lambda *a, **k: None)
    monkeypatch.setattr(bd, "SLIDE_BACKOFF_BASE", 0.0)
    monkeypatch.setattr(bd, "RATE_LIMIT_SLEEP_S", 0.0)
    return svc


def _run(tmp_path, slides, logo_url=None):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    return bd.render_slides_batch(
        slides, api_key="stub-key", renders_dir=tmp_path / "renders",
        run_dir=run_dir, logo_url=logo_url,
        submit_interval=0.0, poll_interval=0.01, max_seconds=30.0)


# ---------------------------------------------------------------------------
# A1 (row 1): a slide with two references posts THREE input_urls, in order
# ---------------------------------------------------------------------------
def test_two_references_post_three_input_urls_in_order(monkeypatch, tmp_path):
    svc = _install(monkeypatch)
    slides = [{"slide": 1, "scene": "s", "copy": ["H"],
               "reference_urls": [REF1, REF2]}]

    _run(tmp_path, slides, logo_url=LOGO)

    assert len(svc.payloads) == 1, f"expected one createTask, got {svc.payloads}"
    payload = svc.payloads[0]
    _t2i, i2i = bd._resolve_image_models()

    # Three images, logo first then the client's photos in the order the row names.
    assert payload["input"]["input_urls"] == [LOGO, REF1, REF2]
    # Image-to-image is the model that accepts input_urls at all.
    assert payload["model"] == i2i


def test_references_alone_still_use_the_image_to_image_model(monkeypatch, tmp_path):
    """No logo, one reference: the photo alone must still switch the model."""
    svc = _install(monkeypatch)
    slides = [{"slide": 1, "scene": "s", "copy": ["H"], "reference_urls": [REF1]}]

    _run(tmp_path, slides)

    payload = svc.payloads[0]
    _t2i, i2i = bd._resolve_image_models()
    assert payload["input"]["input_urls"] == [REF1]
    assert payload["model"] == i2i


# ---------------------------------------------------------------------------
# A1 (row 3): a slide with NO references posts the text-to-image payload unchanged
# ---------------------------------------------------------------------------
def test_no_references_posts_the_recorded_text_to_image_payload(monkeypatch, tmp_path):
    svc = _install(monkeypatch)
    slides = [{"slide": 1, "scene": "s", "copy": ["H"]}]

    _run(tmp_path, slides)

    payload = svc.payloads[0]
    t2i, _i2i = bd._resolve_image_models()
    # Recorded from the pre-change file: exactly these keys, no input_urls,
    # text-to-image model, prompt carrying the mandatory English pin.
    recorded = {
        "model": t2i,
        "input": {
            "prompt": bd._ensure_english_pin("prompt-1"),
            "aspect_ratio": bd.ASPECT_RATIO,
            "resolution": bd.RESOLUTION,
        },
    }
    assert payload == recorded
    assert "input_urls" not in payload["input"]


# ---------------------------------------------------------------------------
# A1 (row 2): an asset wired to no slide fails AF-MANIFEST-UNREFERENCED
# ---------------------------------------------------------------------------
def _manifest_run_dir(root: Path, reference_urls) -> Path:
    """A run with one provided asset whose public_url + consumed_by are present."""
    work = root / "working" / "copy"
    work.mkdir(parents=True, exist_ok=True)
    (work / "intake.json").write_text(json.dumps({
        "interview_confirmed": True, "presentation_mode": "general",
        "audience_mode": "STANDARD", "target_talk_minutes": 30,
        "asset_intake_question_asked": True, "pitch_included": True,
        "assets_provided": True}))
    (work / "assets_manifest.json").write_text(json.dumps({
        "asset_question_asked": True, "assets_provided": True,
        "assets": [{"kind": "photo", "public_url": REF1,
                    "consumed_by": ["brand-steward", "slide-image-creator"]}]}))
    slide = {"slide": 1, "scene": "s", "copy": ["H"]}
    if reference_urls is not None:
        slide["reference_urls"] = reference_urls
    (work / "slides.json").write_text(json.dumps([slide]))
    return root


def test_asset_in_no_slide_fails_the_manifest_gate(tmp_path):
    root = _manifest_run_dir(tmp_path / "unwired", ["https://cdn.example.com/other.png"])
    result = bd._chk_assets_manifest(root)
    assert "AF-MANIFEST-UNREFERENCED" in result
    assert "in no slide's reference_urls" in result


def test_asset_wired_to_a_slide_passes_the_manifest_gate(tmp_path):
    root = _manifest_run_dir(tmp_path / "wired", [REF1])
    assert bd._chk_assets_manifest(root) == ""


def test_no_slides_file_defers_on_the_new_half(tmp_path):
    """Pre-slides phase: the older consumed_by proof still stands alone."""
    root = _manifest_run_dir(tmp_path / "noslides", [REF1])
    (root / "working" / "copy" / "slides.json").unlink()
    assert bd._chk_assets_manifest(root) == ""
